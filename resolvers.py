'''Various resolver techniques are to be defined in this file.
'''


class WordResolver:
  ''' Single pointer value resolver + dynamic offset.
  We have static or dynamic track start value and driver optionally stores offset into it.
  The pointer is stored as LE word at specified memory location and index is a byte.
  '''

  base_ptr = None
  offset_ptr = None

  def __init__(self, base_ptr, offset_ptr=None):
    self.base_ptr = int(base_ptr, 0)
    self.offset_ptr = int(offset_ptr, 0)

  def __call__(self, memory):
    base = int.from_bytes(memory[self.base_ptr:self.base_ptr + 2], 'little')
    if self.offset_ptr is not None:
      offset = int.from_bytes(memory[self.offset_ptr])
    else:
      offset = 0
    return base + offset


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


# TODO: Rewrite this crap after some sleep, only order resolver is working now
class TableResolver:
  ''' Table[Index] + Offset resolver.
  This seems to be a common case in C64 music scene. The driver does not store
  direct pointer to the next command, instead, data is organized into table of
  pointers, each containing a block of commands. The data is then referenced in
  relation to this block.
  '''

  data_table_ptr = None
  data_index_ptr = None
  data_offset_ptr = None
  data_offset_size = None
  data_index_step = None

  # Extra flags for tinkering
  index_is_pointer = False  # Some drivers store data table offset directly, resolve as-is
  index_is_word = False  # in case your index is 16 bit wide
  offset_is_word = False  # in case your offset is 16 bit wide

  def __init__(
    self,
    data_table_ptr,
    data_index_ptr,
    data_offset_ptr,
    flags=''):

    self.data_table_ptr = int(data_table_ptr, 0)
    self.data_index_ptr = int(data_index_ptr, 0)
    self.data_offset_ptr = int(data_offset_ptr, 0)

    if 'w' in flags: self.index_is_word = True
    if 'W' in flags: self.offset_is_word = True
    if 'd' in flags: self.index_is_pointer = True

  def __call__(self, memory):

    # Get data index, assume it's 1 byte, support stepping for interleaved data
    index = int.from_bytes(memory[self.data_index_ptr]) * self.data_index_step

    # Get table offset, assume it's LE word
    table_ptr = self.data_table_ptr + index * 2
    table_offset = int.from_bytes(memory[self.data_offset_ptr:self.data_offset_ptr+2], 'little')

    # Get table data offset, assume it's 1 byte as well
    data_offset = int.from_bytes(memory[self.data_offset_ptr])

    # Get our data pointer from data table and offset.
    command_offset = table_offset + data_offset

    return command_offset


# TODO: Generalize implementation over TableResolver
class OrderTableResolver:
  ''' Table[Orders[OrderIndex]] + Offset resolver.
  A more convoluted example, where order is also an offset to order table
  '''

  order_table_ptr = None
  data_table_ptr = None
  order_index_ptr = None
  data_offset_ptr = None
  data_offset_size = None

  def __init__(
    self,
    order_table_ptr,
    data_table_ptr,
    order_index_ptr,
    data_offset_ptr,
    data_offset_size='b'):

    self.order_table_ptr = int(order_table_ptr, 0)
    self.data_table_ptr = int(data_table_ptr, 0)
    self.order_index_ptr = int(order_index_ptr, 0)
    self.data_offset_ptr = int(data_offset_ptr, 0)

    if data_offset_size == 'b':
      self.data_offset_size = 1
    elif data_offset_size == 'w':
      self.data_offset_size = 2
    else:
      raise ValueError('Expected either "b" or "w" argument for offset pointer')

  def __call__(self, memory):

    # Get order index
    index = int.from_bytes(memory[self.order_index_ptr])
    # Get pattern number in order list
    order = int.from_bytes(memory[self.order_table_ptr + index])
    # Get pattern offset for this number, assume it's LE word in table
    data_ptr_ptr = self.data_table_ptr + order*2
    data_ptr = int.from_bytes(memory[data_ptr_ptr:data_ptr_ptr+2], 'little')
    # Get data offset for this pattern
    if self.data_offset_size == 1:
      data_offset = int.from_bytes(memory[self.data_offset_ptr])
    else:
      data_offset = int.from_bytes(memory[self.data_offset_ptr:self.data_offset_ptr+2], 'little')

    command_offset = data_ptr + data_offset

    return command_offset
