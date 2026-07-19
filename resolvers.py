'''Various resolver techniques are to be defined in this file.
'''

from memory_reader import Pointer
from util import int_autobase

class PointerResolver:
  ''' Single pointer value resolver + dynamic offset.
  We have static or dynamic track start value and driver optionally stores offset into it.
  '''

  base_ptr = None
  offset_ptr = None
  merge_print = None
  info = ''

  def __init__(self, reader, base, offset='', flags=''):
    self.base_ptr = Pointer(reader, base)

    try: self.offset_ptr = Pointer(reader, offset, default_kind='b')
    except ValueError: pass

    self.merge_print = 'm' in flags

  def __call__(self, _memory, _data):

    addr = self.base_ptr()

    if self.offset_ptr is not None:
      offset = self.offset_ptr()
      addr += self.offset_ptr()

    if self.offset_ptr is None or self.merge_print:
      self.info = self.base_ptr.fmt.format(addr)
    else:
      self.info = f'{self.base_ptr.fmt}:{self.offset_ptr.fmt}'.format(~self.base_ptr, offset)

    return addr


class StackResolver:
  ''' Single pointer located at stack offset counting from the stack base
  '''

  stack = None
  stack_head = None
  shift = None
  low = None
  high = None
  direction = None
  conditional_shift = False
  info = ''

  def __init__(self, reader, stack, depth, flags='', shift='0', low=None, high=None):

    self.stack = Pointer(reader, stack, 'w')
    self.depth = Pointer(reader, depth, 'b')
    self.shift = int_autobase(shift)
    self.direction = -1 if 'n' in flags else +1
    if low is not None and high is not None:
      self.low  = int_autobase(low)
      self.high = int_autobase(high)
      self.conditional_shift = True


  def __call__(self, _memory, _data):

    if self.conditional_shift:
      ptr = self.stack(offset=self.depth()*self.direction)
      if ptr < self.low or ptr > self.high:
        ptr = self.stack(offset=self.depth()*self.direction + self.shift)
    else:
      ptr = self.stack(offset=self.depth()*self.direction + self.shift)

    self.info = f'{self.stack.fmt},{self.depth.fmt}'.format(ptr, ~self.depth)

    return ptr


class TableResolver:
  ''' Table[Index] + Offset resolver.
  This seems to be a common case in C64 music scene. The driver does not store
  direct pointer to the next command, instead, data is organized into table of
  pointers, each pointing to a block of commands. The data is then referenced
  in relation to this block.
  '''

  table_ptr = None
  tbl_index_ptr = None
  data_offset_ptr = None
  info = ''

  # Extra flags for tinkering
  index_is_pointer = False  # Some drivers store data table offset directly, resolve as-is
  print_offset = False    # Display resulting addres for track data

  def __init__(
    self,
    reader,
    table_ptr,
    tbl_index_ptr,
    data_offset_ptr,
    flags=''):

    self.table_ptr = Pointer(reader, table_ptr, default_kind='w')
    self.tbl_index_ptr = Pointer(reader, tbl_index_ptr, default_kind='b')
    self.data_offset_ptr = Pointer(reader, data_offset_ptr, default_kind='b')

    if 'd' in flags: self.index_is_pointer = True
    if 'o' in flags: self.print_offset = True

  def __call__(self, memory, data):
    # Get table index
    table_index = self.tbl_index_ptr()

    # Get data pointer
    if self.index_is_pointer:
      data_ptr = self.table_ptr(offset=table_index*2)
    else:
      data_ptr = self.table_ptr(offset=table_index)

    # Get data offset
    data_offset = self.data_offset_ptr()

    command_offset = data_ptr + data_offset

    self.info = f'{self.tbl_index_ptr.fmt},{self.data_offset_ptr.fmt}'.format(
      table_index,
      data_offset)

    if self.print_offset:
      self.info += ':{:04X}'.format(command_offset)

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
  data_table_stride = None
  info = ''

  offset_is_word = False  # in case your offset is 16 bit wide, no vword support
  print_offset = False    # Display resulting addres for track data
  table_ptr_be = False    # When stride is given, assume first value is high byte

  def __init__(
    self,
    reader,
    order_table_ptr,
    data_table_ptr,
    order_index_ptr,
    data_offset_ptr,
    flags='',
    data_table_stride=0):

    if 'o' in flags: self.print_offset = True
    if 'W' in flags: self.offset_is_word = True
    if 'B' in flags: self.table_ptr_be = True

    self.order_table_ptr = int(order_table_ptr, 0)
    self.data_table_ptr = int(data_table_ptr, 0)
    self.order_index_ptr = int(order_index_ptr, 0)
    self.data_offset_ptr = int(data_offset_ptr, 0)

    if data_table_stride:
      self.data_table_stride = int(data_table_stride, 0)

  def __call__(self, memory, data):
    # Get order index
    order = memory.byte(self.order_index_ptr)
    # Get pattern number in order list
    pattern = data.byte(self.order_table_ptr + order)

    # In case our index points into "vertical" table of known size
    if self.data_table_stride:
      if self.table_ptr_be:
        data_ptr = data.vword_be(self.data_table_ptr + pattern, self.data_table_stride)
      else:
        data_ptr = data.vword_le(self.data_table_ptr + pattern, self.data_table_stride)

    else:
      # Get pattern offset for this number, assume it's LE word in table
      data_ptr = data.word_le(self.data_table_ptr + pattern*2)

    # Get data offset for this pattern
    if self.offset_is_word: data_offset = memory.word_le(self.data_offset_ptr)
    else: data_offset = memory.byte(self.data_offset_ptr)

    command_offset = data_ptr + data_offset
    if self.print_offset:
      self.info = '{:02X}:{:02X},{:02X}:{:04X}'.format(order, pattern, data_offset, command_offset)
    else:
      self.info = '{:02X}:{:02X},{:02X}'.format(order, pattern, data_offset)

    return command_offset
