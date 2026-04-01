import re
import json
from types import SimpleNamespace

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


class MappedPrinter(HexPrinter):

  note_prefixes = ['C-', 'C#', 'D-', 'D#', 'E-', 'F-', 'F#', 'G-', 'G#', 'A-', 'A#', 'B-']
  note_lo = None
  note_hi = None
  drum_lo = None
  drum_hi = None
  commands = None
  cmd_buckets = None
  cmd_buckets_high = None
  parse_preview = False

  def parse_configuration(self, cfg):
    # Parse note and drum ranges
    self.note_lo, self.note_hi = [int(x, 0) for x in cfg['notes']]
    self.drum_lo, self.drum_hi = [int(x, 0) for x in cfg['drums']]

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
        endianess = 'big' if 'B' in pflags else 'little'
        fmt = '0x{:x}' if 'h' in pflags else '{:d}'
        signature_length += length

        parser = lambda x, f=fmt, e=endianess, s=signed: f.format(int.from_bytes(x, byteorder=e, signed=s))

        parameter = SimpleNamespace(
          name=param_name,
          parser=parser,
          length=length)

        parameters.append(parameter)

      command = SimpleNamespace(
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

  def note(self, value):
    if value > self.note_hi or value < self.note_lo:
      return None

    note = value - self.note_lo
    return '{}{}'.format(
      self.note_prefixes[note % 12],
      note // 12)

  def drum(self, value):
    if value > self.drum_hi or value < self.drum_lo:
      return None

    drum = value - self.drum_lo
    return 'drum({:02d})'.format(drum)

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
        line = self.note(tokens[0] if direction else tokens[-1])

        if line:
          tokens = tokens[1:] if direction else tokens[:-1]
          to_process -= 1

      # Finally as drum
      if line is None:
        line = self.drum(tokens[0] if direction else tokens[-1])

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
            result[-1] += f", {line}"
          else:
            result[0] += f", {line}"
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
