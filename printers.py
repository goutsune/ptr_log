import re

# Pre-cook suffixes
from consts import BRED, BBLUE, GRAY, GOLD, RESET
from consts import FJMP, BJMP, FWRD, PREV, LKUP

FJMP_PFX = '► ' + BRED
BJMP_PFX = '◄ ' + BBLUE
PREV_PFX = '  ' + GRAY
LKUP_PFX = '▲ ' + GOLD
FWRD_PFX = '• '
TAIL_SFX = '~' + RESET


class HexPrinter:
  '''The default printer class, emits hexdump of read bytes  according given
  action
  '''

  end_patterns = None
  prefix = ''
  result = ''
  suffix = ''
  action = None

  def __init__(self, width, **kwargs):
    self.width = width
    if 'end_patterns' in kwargs:
      # Build a list of regex patterns which we can use for matching
      regexes = [
        b''.join(
          b'.' if x == '??'
          else bytes.fromhex(x) for x in y.split(',')
        )
        for y in kwargs['end_patterns']
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

    self.suffix = ''
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

  def format_tokens(self, tokens):

    if self.action == FWRD and len(tokens) == 1:
      val = int.from_bytes(tokens, signed=True)
      if abs(val) < 0x20:
        return ["█"*val]

    return super().format_tokens(tokens)


class LinePrinter(HexPrinter):

  def format_tokens(self, tokens):

    if self.action == FWRD and len(tokens) == 1:
      val = int.from_bytes(tokens, signed=True)
      shift = 0x10
      #if abs(val) < shift:
      pos = shift + val
      return [f'{" "*pos}|']

    return super().format_tokens(tokens)
