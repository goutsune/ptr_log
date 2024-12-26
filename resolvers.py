'''Various resolver techniques are to be defined in this file.
'''


class WordResolver:
  ''' Single pointer value resolver.
  Probably the simpliest case possible.
  The pointer is stored as LE word at specified memory location.
  '''

  pointer = None

  def __init__(self, pointer):
    self.pointer = int(pointer, 0)

  def __call__(self, memory):
    lo_byte, hi_byte = memory[self.pointer:self.pointer + 2]
    return int.from_bytes((hi_byte, lo_byte))


class HiLoResolver:
  ''' Lo + Hi byte pointer resolver.
  A very common case, we have non-linear memory location for 16-bit pointer.
  It will take pointer offsets for those 2 bytes, read these byte values
  from code segment and combine them.
  '''

  high = None
  low = None

  def __init__(self, hi_ptr, lo_ptr):
    self.high = int(hi_ptr, 0)
    self.low = int(lo_ptr, 0)

  def __call__(self, memory):

    hi_byte = memory[self.high]
    lo_byte = memory[self.low]

    return int.from_bytes(hi_byte + lo_byte)
