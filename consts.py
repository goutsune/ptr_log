# Terminal colors
GRAY  = "\033[90m"
BGRAY = "\033[37m"
RED   = "\033[31m"
GOLD  = "\033[33m"
BRED  = "\033[91m"
BLUE  = "\033[34m"
BBLUE = "\033[94m"
RESET = "\033[0m"


# Six distinct step modes, REST = go to 0 of 0xFFFF
FWRD = 0
BKWD = 1  # Same as BJMP for the time being
FJMP = 2
BJMP = 3
REST = 4
PREV = 5  # Preview mode
LKUP = 6  # Preview for backward lookup
