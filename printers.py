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

  end_pattern = None
  prefix = ''
  result = ''
  suffix = ''

  def __init__(self, width, **kwargs):
    self.width = width

    if 'end_pattern' in kwargs:
      self.end_pattern = kwargs['end_pattern']

  def format_tokens(self, tokens):
      return [
        tokens[pos : self.width+pos].hex(' ')
        for pos in range(0, len(tokens), self.width)
      ]

  def __call__(self, action, tokens):
    # The caller is supposed to pass resulting buffer (either extracted or
    # lookup limit) and action that is happening. Printer then updates its
    # state which is to be expected by caller.

    self.result = self.format_tokens(tokens)
    self.suffix = RESET

    # On detected jump, let's see if track end sequence is within lookup area
    if (action == FJMP or action == BJMP) and self.end_pattern:
      if (pos := tokens.find(self.end_pattern)) >= 0:
        self.result = self.format_tokens(tokens[0:pos+1])
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
