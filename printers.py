import re
import json
from types import SimpleNamespace as SN
from functools import partial

# Pre-cook suffixes
from consts import BRED, BBLUE, GRAY, GOLD, RESET
from consts import FJMP, BJMP, FWRD, PREV, LKUP

FJMP_PFX = '► ' + BRED
BJMP_PFX = '◄ ' + BBLUE
PREV_PFX = '  ' + GRAY
LKUP_PFX = '▲ ' + GOLD
FWRD_PFX = '• '
TAIL_SFX = '~' + RESET


# TODO: Define AbstractPrinter interface
class HexPrinter:
  '''The default printer class, emits hexdump of read bytes according to action
  '''

  end_patterns = None
  prefix = ''
  result = []
  suffix = ''
  action = None

  # Not the best place, but in case parser determined new jump position,
  # it is to be stored here. Otherwise this is to be reset to None
  jump_addr = None

  def __init__(self, width='4', end_patterns=None, *args, **kwargs):
    self.width = int(width, 0)

    if end_patterns is not None:
      # Build a list of regex patterns which we can use for matching
      regexes = [
        b''.join(
          b'.' if x == '??'
          else bytes.fromhex(x) for x in y.split(',')
        )
        for y in end_patterns.split('/')
      ]

      # Now build a list of tuples containing pattern length and compiled pattern
      patterns = [
        (re.compile(x, re.DOTALL), len(x))
        for x in regexes]

      self.end_patterns = patterns

  def format_tokens(self, tokens):
      return [
        tokens[pos : self.width+pos].hex(' ')
        for pos in range(0, len(tokens), self.width)
      ]

  def pattern_search(self, tokens, direction=True):
    # Direction determines if we return first match position or last
    best_pos = len(tokens) if direction else -1
    best_sz = 0

    for pattern, size in self.end_patterns:
      matches = list(pattern.finditer(tokens))
      if matches:
        pos = matches[0] if direction else matches[-1]
        if direction:
          if pos.start() < best_pos:
            best_pos = pos.start()
            best_sz = size
        else:
          if pos.start() > best_pos:
            best_pos = pos.start()
            best_sz = size

    if (direction and best_pos == len(tokens)) or (not direction and best_pos == -1):
      return -1, 0

    return best_pos, best_sz

  def __call__(self, action, tokens):
    # The caller is supposed to pass resulting buffer (either extracted or
    # lookup limit) and action that is happening. Printer then updates its
    # state which is to be expected by caller.

    self.suffix = RESET
    self.action = action
    self.result = self.format_tokens(tokens)
    self.jump_addr = None

    # On detected jump, let's see if track end sequence is within lookup area
    if (action == FJMP or action == BJMP) and self.end_patterns:
      pos, sz = self.pattern_search(tokens)
      if pos >= 0:
        self.result = self.format_tokens(tokens[0:pos + sz])
        self.suffix = TAIL_SFX

    # Forward jump
    if action == FJMP:
      self.prefix = FJMP_PFX

    # Backward jump
    elif action == BJMP:
      self.prefix = BJMP_PFX

    # Normal step
    elif action == FWRD:
      self.prefix = FWRD_PFX
      self.suffix = ''

    # Preview line
    elif action == PREV:
      self.prefix = PREV_PFX

    # Backward lookup on jump
    elif action == LKUP:
      self.prefix = LKUP_PFX

      if self.end_patterns:
        pos, sz = self.pattern_search(tokens, direction=False)
        if pos >= 0:
          self.result = self.format_tokens(tokens[pos:])


class BarPrinter(HexPrinter):

  limit = None

  def __init__(self, limit='0x20', *args, **kwargs):
    self.limit = int(limit, 0)
    super().__init__(*args, **kwargs)

  def format_tokens(self, tokens):

    if self.action  in (FWRD, PREV):
      val = int.from_bytes(tokens[:1], signed=True)
      if abs(val) < self.limit:
        return ['█'*val]

    return super().format_tokens(tokens)


class LinePrinter(HexPrinter):

  shift = None

  def __init__(self, shift='0x10', mult='1',*args, **kwargs):
    self.shift = int(shift, 0)
    self.multiplier = float(mult)
    super().__init__(*args, **kwargs)

  def format_tokens(self, tokens):

    if self.action in (FWRD, PREV):
      val = int.from_bytes(tokens[:1], signed=True)
      pos = self.shift + round(val*self.multiplier)
      return [f'{' '*pos}|']

    return super().format_tokens(tokens)


class AsciiPrinter(HexPrinter):

    def format_tokens(self, tokens):
        results = []
        ascii_chars = []
        hex_start = None

        for i in range(len(tokens)):
            token_slice = tokens[i:i+1]
            val = int.from_bytes(token_slice, byteorder='big')

            if 0x20 <= val <= 0x7f:
                if hex_start is not None:
                    results.extend(super().format_tokens(tokens[hex_start:i]))
                    hex_start = None
                ascii_chars.append(chr(val))
            else:
                if ascii_chars:
                    results.append(''.join(ascii_chars))
                    ascii_chars = []
                if hex_start is None:
                    hex_start = i

        # Flush any remaining buffers at the end of the sequence
        if hex_start is not None:
            results.extend(super().format_tokens(tokens[hex_start:]))
        if ascii_chars:
            results.append(''.join(ascii_chars))

        return results


class MappedPrinter(HexPrinter):

  ranges = None
  notes = None
  commands = None
  cmd_buckets = None
  cmd_buckets_high = None
  parse_preview = False

  @staticmethod
  def _format_command_parameter(stream, fmt, byteorder, signed):
    return fmt.format(
      int.from_bytes(
        stream,
        byteorder=byteorder,
        signed=signed))

  def parse_configuration(self, cfg):
    # Parse note range
    if 'notes' in cfg:
      # Support note suffixes/prefixes, notably velocity and length.
      # Arg is tri-state, None disables, "post" set's to True
      arg = cfg['notes']['arg'] if 'arg' in cfg['notes'] else None
      if arg is not None:
        arg = True if arg == "post" else False

      self.notes = SN(
        lo=int(cfg['notes']['lo'], 0),
        hi=int(cfg['notes']['hi'], 0),
        prefixes=cfg['notes']['prefixes'],
        length=len(cfg['notes']['prefixes']),
        arg=arg)

    if 'ranges' in cfg:
      self.ranges = [SN(
        name=k,
        lo=int(v[0], 0),
        hi=int(v[1], 0))
        for k, v in cfg['ranges'].items()]

    # Parse command grammar. Base format looks like this:
    # <code>: <"disp_name[,rflags]", [param1[,pflags], ..., paramN[,pflags]]>
    # rflags:
    #  e - This command is final and jump is always expected, this adds it to the list of end patterns
    #  p - This command should be displayed as property, i.e. just name, no (), arguments will be after ","
    #  t - This command should be attached to whatever command preceeded it, useful for note length and koff
    # pflags:
    #  b - parameter is unsigned byte (default)
    #  s - parameter is signed byte
    #  w - parameter is unsigned LE word
    #  h - format as hex instead of decimal

    commands = {}  # Command map by command code
    cmd_buckets = {}  # Also command map by command code, also grouped by argument length
    buckets_high = 0  # Longest command length for the bucket set

    for code, (disp_name, *params) in cfg['commands'].items():

      code = int(code, 0)
      disp_name, *rflags = disp_name.split(',')
      if rflags:
        rflags = rflags.pop()

      is_final = 'e' in rflags
      is_property = 'p' in rflags
      is_tail = 't' in rflags
      signature_length = 1
      parameters = []

      for param in params:
        param_name, *pflags = param.split(',')
        if pflags:
          pflags = pflags.pop()  # Extract arguments as string, if any

        length = 2 if 'w' in pflags else 1
        signed = True if 's' in pflags else False
        byteorder = 'big' if 'B' in pflags else 'little'
        fmt = '0x{:x}' if 'h' in pflags else '{:d}'
        signature_length += length

        parameter = SN(
          name=param_name,
          parser=partial(
            self._format_command_parameter,
            fmt=fmt,
            byteorder=byteorder,
            signed=signed),
          length=length)

        parameters.append(parameter)

      command = SN(
        name=disp_name,
        is_final=is_final,
        is_property=is_property,
        is_tail=is_tail,
        parameters=parameters,
        length=signature_length)

      commands[code] = command
      if signature_length not in cmd_buckets:
        cmd_buckets[signature_length] = {code: command}
      else:
        cmd_buckets[signature_length][code] = command

      buckets_high = max(buckets_high, command.length)

    self.commands = commands
    self.cmd_buckets = cmd_buckets
    self.cmd_buckets_high = buckets_high

  def __init__(self, defs, *args, preview_cmd=False, **kwargs):
    super().__init__(*args, **kwargs)

    if preview_cmd:
      preview_cmd = int(preview_cmd, 0)
      self.parse_preview = bool(preview_cmd)

    with open(defs, 'r', encoding='utf-8') as handle:
      cfg = json.load(handle)
    self.parse_configuration(cfg)

  def note(self, value, arg=None):
    '''Find and tokenize note with octave, lo and high values are INCLUSIVE.
    '''
    if self.notes is None:
      return None

    if value > self.notes.hi or value < self.notes.lo:
      return None

    # Remove command offset
    n = value - self.notes.lo
    if arg is not None:

      return '{note}{octave}, {arg}'.format(
        note=self.notes.prefixes[n % self.notes.length],
        octave=n // self.notes.length,
        arg=arg)
    else:
      return '{note}{octave}'.format(
        note=self.notes.prefixes[n % self.notes.length],
        octave=n // self.notes.length)

  def ranged(self, value):
    '''Find and tokenize single range parameter, lo and high values are INCLUSIVE.
    '''
    if self.ranges is None:
      return None

    range_def = None

    for candidate in self.ranges:
      if value <= candidate.hi and value >= candidate.lo:
        range_def = candidate
        break

    if range_def is None:
      return None

    # Remove command offset
    n = value - range_def.lo
    return '{}({:02d})'.format(range_def.name, n)

  def command(self, bucket, values):
    '''Tokenizer for single vcmd.
    Returns string representation, command object and number of consumed bytes
    '''

    # If command was unknown, skip that byte and let parser decide what to do,
    # report how many bytes were consumed though. Also fail fast if sized
    # command bucket was empty, meaning no commands match that size
    if values[0] not in bucket:
      return None, None, 0

    vcmd_code, args = values[0], values[1:]  # Unpacking auto-converts to ints
    vcmd = bucket[vcmd_code]
    repr_format = '{} {}' if vcmd.is_property else '{}({})'

    # Parser always passes bytes as-is, so it's possible we didn't get enough.
    # In this case just print vcmd name and remaining bytes, if any
    if len(values) >= vcmd.length:
      pos = 0
      representations = []

      if vcmd.parameters:
        for parameter in vcmd.parameters:
          # TODO: Extend printers to objects that store length, print format and parser separately
          parameter_argument = parameter.parser(args[pos:pos+parameter.length])
          if parameter.name:
            # Only works for 16-bit LE words for now
            if parameter.name == 'addr':
              self.jump_addr = int.from_bytes(args[pos:pos+parameter.length], 'little')
            representations.append('{}={}'.format(parameter.name, parameter_argument))
          else:
            representations.append(str(parameter_argument))
          pos += parameter.length

        return repr_format.format(vcmd.name, ', '.join(representations)), vcmd, vcmd.length
      else:
        return vcmd.name if vcmd.is_property else '{}()'.format(vcmd.name), vcmd, vcmd.length

    else:
      repr_format = '{} {}…' if vcmd.is_property else '{}({}…'

      return repr_format.format(vcmd.name, args.hex(' ')), vcmd, len(values)

  def format_vcmds(self, tokens, action, direction):
    to_process = len(tokens)
    result = []

    while True:  # do-while, see epilogue

      # Try to parse as command, iterate over buckets and break if we found a matching vcmd
      for cmd_size in (
          range(self.cmd_buckets_high + 1) if direction
          else range(self.cmd_buckets_high, 0, -1)
      ):
        if cmd_size not in self.cmd_buckets: continue

        if direction:
          token_slice = tokens[:cmd_size]
        else:
          token_slice = tokens[len(tokens) - cmd_size:]

        line, vcmd, consumed = self.command(self.cmd_buckets[cmd_size], token_slice)

        # Break and update to_process if we found something
        if line is not None:
          # Skip parsing any existing commands if this one was control flow
          # or something that results in jump.
          if vcmd.is_final and action in (FJMP, BJMP, LKUP):
            # TODO: Perhaps figure out a way to extract and pass back that address
            #  way back inside logger for actual jump start detection
            to_process = 0
          elif vcmd:
            to_process -= consumed

          break

      # Update token buffer if we found something, either chop from start or from end.
      tokens = tokens[consumed:] if direction else tokens[:-consumed or None]

      # Try parsing as note if we didn't find anything yet
      if line is None:
        # Note only
        if self.notes.arg is None:
          note_byte = tokens[0] if direction else tokens[-1]
          arg_byte = None
        # Post-note argument
        elif self.notes.arg:
          note_byte = tokens[0] if direction else tokens[-1]
          try:
            arg_byte = tokens[1] if direction else tokens[-2]
          except IndexError:
            arg_byte = None
        # Pre-note argument
        else:
          arg_byte = tokens[0] if direction else tokens[-1]
          try:
            note_byte = tokens[1] if direction else tokens[-2]
          except IndexError:
            note_byte = arg_byte
            arg_byte = None

        line = self.note(note_byte, arg_byte)

        if line:
          if arg_byte is not None:
            tokens = tokens[2:] if direction else tokens[:-2]
            to_process -= 2
          else:
            tokens = tokens[1:] if direction else tokens[:-1]
            to_process -= 1

      # Finally as a range
      if line is None:
        line = self.ranged(tokens[0] if direction else tokens[-1])

        if line:
          tokens = tokens[1:] if direction else tokens[:-1]
          to_process -= 1

      # Fallback to hex otherwise, don't try to detect anything else after first printed byte either
      if line is None:
        line = self.format_tokens(tokens)
        to_process = 0

      # Original hex tokenizer returns list, not string
      if type(line) == str:
        # For tails, append them to last print result instead of adding new line
        if vcmd and vcmd.is_tail and result:
          if direction:
            result[-1] += f', {line}'
          else:
            result[0] += f', {line}'
        else:
          result.append(line) if direction else result.insert(0, line)
      else:
        if direction:
          result.extend(line)
        else:
          line.extend(result)
          result = line

      if to_process <= 0: break

    return result

  def __call__(self, action, tokens):
    self.suffix = RESET
    self.action = action
    self.jump_addr = None

    # Only lookup needs backward parsing
    if action == LKUP:
      self.result = self.format_vcmds(tokens, action, direction=False)
    # Skip tokenizer for preview line, it will always be just hex
    elif action != PREV or (self.parse_preview):
      self.result = self.format_vcmds(tokens, action, direction=True)

    # Forward jump
    if action == FJMP:
      self.prefix = FJMP_PFX

    # Backward jump
    elif action == BJMP:
      self.prefix = BJMP_PFX

    # Normal step
    elif action == FWRD:
      self.prefix = FWRD_PFX
      self.suffix = ''

    # Preview line
    elif action == PREV:
      self.prefix = PREV_PFX
      if not self.parse_preview:
        self.result = self.format_tokens(tokens)

    # Backward lookup on jump
    elif action == LKUP:
      self.prefix = LKUP_PFX


class FushigiPrinter(HexPrinter):
  '''Parses Namco's tracker-like format seen in Fushigi no Umi no Nadia.
  Format is inherently stateful, not possible to parse mid-pattern due to stored cmd masks
  '''
  NOTES = ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#", "B-"]

  def __init__(self, *args, **kwargs):

    self.note_masks = [x for x in range (0b10_000000, 0b11_000000)]
    self.wait_masks = [x for x in range (0b11_000000, 0b11_010000)]
    self.mask = 0

    return super().__init__(*args, **kwargs)

  def _format_note(self, val):

    if val == 0xFF:
      return "==="
    if 0x00 <= val <= 0x7F:
      return f"{self.NOTES[val % 12]}{val // 12}"

    return f"{val:02x} "

  def _read_slice(self, tokens, start, length):
      # Raise exception if we read less then supposed to
      if start + length > len(tokens):
        raise IndexError
      return tokens[start : start+length]

  def _apply_channel_mask(self, mask_byte, data_bytes, formatter_cb, empty_str="..."):
    """
    Generic mask processor.
    Consumes bytes from data_bytes based on bits set in mask_byte.
    """
    channel_cols = []
    consumed = 0

    for i in range(1, 7):
      if ((mask_byte << i) & 0x100) and consumed < len(data_bytes):
        val = data_bytes[consumed]
        channel_cols.append(formatter_cb(val))
        consumed += 1
      else:
        channel_cols.append(empty_str)

    return " ".join(channel_cols), consumed

  def _masked_channel_cmd(self, mask, prefix, tokens):
    return self._apply_channel_mask(
      mask,
      tokens,
      lambda v: f'{prefix}{v:02X}'
    )

  def format_tokens(self, tokens):
    if not tokens:
      return []

    result = []
    idx = 0
    mask = self.mask

    while idx < len(tokens):
      try:
        cmd_byte = tokens[idx]
        pref = cmd_byte & 0b11000000
        cmd = cmd_byte & 0b00111111

        match pref:

          # Empty row
          case 0b11_000000:
            cols, _ = self._apply_channel_mask(0, [], None)
            result.append(f'{cmd_byte:08b} {cols} *{cmd_byte&0b00_111111}')
            idx += 1

          # Note rows
          case 0b10_000000:
            note_mask = cmd_byte << 2 & 0xFF
            cols, consumed = self._apply_channel_mask(
              note_mask, tokens[idx+1:], self._format_note
            )
            result.append(f'{cmd_byte:08b} {cols}')
            idx += 1 + consumed

          # Full commands
          case 0b00_000000 | 0b01_000000:

            match cmd:

              case 0x01 if pref == 0b00_000000: # Speed
                result.append(f'{cmd_byte:08b} Speed={tokens[idx+1]}')
                idx += 2

              case 0x02 if pref == 0b00_000000: # Go to
                addr = int.from_bytes(self._read_slice(tokens, idx+1, 2), 'big')
                self.jump_addr = addr
                result.append(f'{cmd_byte:08b} Goto {addr:X}h')
                idx += 3

              case 0x03 if pref == 0b00_000000: # Play phrase
                addr = int.from_bytes(self._read_slice(tokens, idx+1, 2), 'big')
                self.jump_addr = addr
                result.append(f'{cmd_byte:08b} Call {addr:X}h')
                idx += 3

              case 0x04 if pref == 0b00_000000: # Loop
                count = tokens[idx+1]
                addr = int.from_bytes(self._read_slice(tokens, idx+2, 2), 'big')
                self.jump_addr = addr
                result.append(f'{cmd_byte:08b} Loop A {count} to {addr:X}h')
                idx += 4

              case 0x06 if pref == 0b00_000000: # Loop?
                count = tokens[idx+1]
                addr = int.from_bytes(self._read_slice(tokens, idx+2, 2), 'big')
                self.jump_addr = addr
                result.append(f'{cmd_byte:08b} Loop B {count} to {addr:X}h')
                idx += 4

              case 0x08 if pref == 0b00_000000: # Return / Stop
                result.append(f'{cmd_byte:08b} BRK')
                idx += 1

              case 0x09 if pref == 0b00_000000: # Play Drum on Z80
                result.append(f'{cmd_byte:08b} Sample={tokens[idx+1]}')
                idx += 2

              case 0x20 if pref == 0b00_000000: # Reset tracks
                mask = tokens[idx+1]
                cols = f'{mask >> 2:06b}'.replace('0', '... ').replace('1', '^^^ ')
                result.append(f'{cmd_byte:08b} {cols}<- {cmd_byte:02X}h')
                idx += 2

              # Whatever these are will become apparent later
              case 0x0b | 0x0c | 0x0d | 0x0e | 0x0f | 0x10 | 0x11 | 0x12 | 0x13 | 0x14 | 0x15:

                # pref will be 0 for full cmd
                mask = mask if pref else tokens[idx+1]
                offset = 1 if pref else 2

                name = chr(0x37 + cmd)
                cols, consumed = self._masked_channel_cmd(
                  mask, name, tokens[idx+offset:]
                )
                result.append(f'{cmd_byte:08b} {cols} {"%" if pref else ""}')
                idx += offset + consumed

              case _:
                self.mask = mask  # Update global mask state
                bin_head = f'{cmd_byte:08b}'
                remainder = tokens[idx+1:]

                if remainder:
                  hex_chunks = [
                    remainder[p : self.width+p].hex(' ')
                    for p in range(0, len(remainder), self.width)
                  ]
                  result.append(f'{bin_head} {hex_chunks[0]} ${cmd_byte:02X}')
                  result.extend(hex_chunks[1:])
                else:
                  result.append(bin_head)

                break

      except IndexError:
        # Dump whatever is left at the playhead
        remainder = tokens[idx:]

        # Format the remaining garbage as hex
        if isinstance(remainder, bytes) or isinstance(remainder, bytearray):
          dump = remainder.hex(' ')
        else:
          dump = ' '.join(f'{b:02x}' for b in remainder)

        result.append(f'{tokens[idx]:08b} {dump} <- TRNC')
        break

    self.mask = mask  # Update global mask state
    return result
