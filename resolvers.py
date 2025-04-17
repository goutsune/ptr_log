'''Various resolver techniques are to be defined in this file.
'''


class WordResolver:
  ''' Single pointer value resolver + dynamic offset.
  We have static or dynamic track start value and driver optionally stores offset into it.
  The pointer is stored as LE word at specified memory location and index is a byte.
  '''

  base_ptr = None
  offset_ptr = None
  big_endian = False
  info = ''

  def __init__(self, base_ptr, flags='', offset_ptr=None):
    self.base_ptr = int(base_ptr, 0)
    try:
      self.offset_ptr = int(offset_ptr, 0)
    except TypeError:
      pass

    if 'b' in flags:
      self.big_endian = True

  def __call__(self, memory):

    if self.big_endian: base = memory.word_be(self.base_ptr)
    else: base = memory.word_le(self.base_ptr)

    if self.offset_ptr is not None:
      offset = memory.byte(self.offset_ptr)
      self.info = '{:04X}+{:02X}'.format(base, offset)
    else:
      offset = 0
      self.info = '{:04X}'.format(base)

    return base + offset


class DwordResolver(WordResolver):
  '''Same as word resolver, but we have 32 bits to deal with.
  '''

  def __call__(self, memory):

    if self.big_endian: base = memory.dword_be(self.base_ptr)
    else: base = memory.dword_le(self.base_ptr)

    if self.offset_ptr is not None:
      offset = memory.byte(self.offset_ptr)
      self.info = '{:08X}+{:02X}'.format(base, offset)
    else:
      offset = 0
      self.info = '{:08X}'.format(base)

    return base + offset


class HiLoResolver:
  ''' Lo + Hi byte pointer resolver.
  A very common case, we have non-linear memory location for 16-bit pointer.
  It will take pointer offsets for those 2 bytes, read these byte values
  from code segment and combine them.
  '''

  high = None
  low = None
  offset_ptr = None
  info = ''

  def __init__(self, hi_ptr, lo_ptr, offset_ptr=None):
    self.high = int(hi_ptr, 0)
    self.low = int(lo_ptr, 0)
    try:
      self.offset_ptr = int(offset_ptr, 0)
    except TypeError:
      pass

  def __call__(self, memory):

    hi_addr = memory.byte(self.high) * 0x100
    lo_addr = memory.byte(self.low)

    if self.offset_ptr is not None:
      offset = memory.byte(self.offset_ptr)
    else:
      offset = 0

    if lo_addr > offset:
      final_lo_addr = lo_addr + offset
    else:
      final_lo_addr = offset - lo_addr

    address = hi_addr + final_lo_addr
    self.info = '{:04X}'.format(address)

    return address


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
  data_index_step = None  # Useful when our offset table is vertical, causing lo and hi bytes to apart
  info = ''

  # Extra flags for tinkering
  index_is_pointer = False  # Some drivers store data table offset directly, resolve as-is
  index_is_word = False   # in case your index is 16 bit wide
  offset_is_word = False  # in case your offset is 16 bit wide
  print_offset = False    # Display resulting addres for track data

  def __init__(
    self,
    data_table_ptr,
    data_index_ptr,
    data_offset_ptr,
    data_index_step=0,
    flags=''):

    self.data_table_ptr = int(data_table_ptr, 0)
    self.data_index_ptr = int(data_index_ptr, 0)
    self.data_offset_ptr = int(data_offset_ptr, 0)
    if data_index_step:  # Branch on empty string
      self.data_index_step = int(data_index_step, 0)

    if 'w' in flags: self.index_is_word = True
    if 'W' in flags: self.offset_is_word = True
    if 'd' in flags: self.index_is_pointer = True
    if 'o' in flags: self.print_offset = True

  def __call__(self, memory):

    # Get data index
    if self.index_is_word: data_index = memory.word_le(self.data_index_ptr)
    else: data_index = memory.byte(self.data_index_ptr)

    # In case our index points into "vertical" table of known size, we want to get lo and hi bytes separately.
    if self.data_index_step:

      # High byte is normal
      ptr_hi = memory[self.data_table_ptr + data_index]
      # Low byte offset by table length
      ptr_lo = memory[self.data_table_ptr + self.data_index_step + data_index]

      data_ptr = int.from_bytes(ptr_hi + ptr_lo)

    # Otherwise proceed normally,
    else:
      # Get data pointer
      if self.index_is_pointer: data_ptr_ptr = self.data_table_ptr + data_index

      # In this mode we assume it's index to word array
      else: data_ptr_ptr = self.data_table_ptr + data_index*2

      # Get table offset
      data_ptr = memory.word_le(data_ptr_ptr)

    # Get data offset
    if self.offset_is_word: data_offset = memory.word_le(self.data_offset_ptr)
    else: data_offset = memory.byte(self.data_offset_ptr)

    command_offset = data_ptr + data_offset

    if self.print_offset:
      self.info = '{:02X},{:02X}:{:04X}'.format(data_index, data_offset, command_offset)
    else:
      self.info = '{:02X},{:04X}+{:02X}'.format(data_index, data_ptr, data_offset)

    return command_offset


# TODO: Generalize implementation over TableResolver?
class OrderTableResolver:
  ''' Table[Orders[OrderIndex]] + Offset resolver.
  A more convoluted example, where order is also an offset to order table
  '''

  order_table_ptr = None
  data_table_ptr = None
  order_index_ptr = None
  data_offset_ptr = None
  info = ''

  offset_is_word = False  # in case your offset is 16 bit wide
  print_offset = False    # Display resulting addres for track data

  def __init__(
    self,
    order_table_ptr,
    data_table_ptr,
    order_index_ptr,
    data_offset_ptr,
    flags=''):

    self.order_table_ptr = int(order_table_ptr, 0)
    self.data_table_ptr = int(data_table_ptr, 0)
    self.order_index_ptr = int(order_index_ptr, 0)
    self.data_offset_ptr = int(data_offset_ptr, 0)

    if 'o' in flags: self.print_offset = True
    if 'W' in flags: self.offset_is_word = True

  def __call__(self, memory):

    # Get order index
    index = memory.byte(self.order_index_ptr)
    # Get pattern number in order list
    order = memory.byte(self.order_table_ptr + index)
    # Get pattern offset for this number, assume it's LE word in table
    data_ptr_ptr = self.data_table_ptr + order*2
    data_ptr = memory.word_le(data_ptr_ptr)

    # Get data offset for this pattern
    if self.offset_is_word: data_offset = memory.word_le(self.data_offset_ptr)
    else: data_offset = memory.byte(self.data_offset_ptr)

    command_offset = data_ptr + data_offset
    if self.print_offset:
      self.info = '{:02X}:{:02X},{:02X}:{:04X}'.format(index, order, data_offset, command_offset)
    else:
      self.info = '{:02X}:{:02X},{:02X}'.format(index, order, data_offset)

    return command_offset
