
# Six distinct step modes, REST = go to 0 of 0xFFFF
FWRD = 0
BKWD = 1  # Same as BJMP for the time being
FJMP = 2
BJMP = 3
REST = 4
PREV = 5  # Preview mode
LKUP = 6  # Preview for backward lookup

# Colors
GRAY  = "\033[90m"
BGRAY = "\033[37m"
RED   = "\033[31m"
GOLD  = "\033[33m"
BRED  = "\033[91m"
BLUE  = "\033[34m"
BBLUE = "\033[94m"
RESET = "\033[0m"

# Pre-cook suffixes
FJMP_PFX = '► ' + BRED
BJMP_PFX = '◄ ' + BBLUE
PREV_PFX = '  ' + GRAY
LKUP_PFX = '▲ ' + GOLD
TAIL_SFX = '~' + RESET

class HexPrinter:
  '''The default printer class, interface emits hexdump of read bytes according given action
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
    # The caller is supposed to update buffers before calling. Then we check action and format required
    # buffer according to lookup / width buffer and return 3 items:
    # 1. Prefix string (e.g color set sequence)
    # 2. A list of printouts split according to width
    # 3. Suffix string (e.g. color reset sequence)
    # The caller is then supposed to print each result line as it sees suitable.

    seq_end_found = False
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
      self.prefix = '• '
      self.suffix = ''

    elif action == PREV:
      self.prefix = PREV_PFX

    elif action == LKUP:
      self.prefix = LKUP_PFX

