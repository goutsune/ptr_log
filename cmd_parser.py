import argparse

from resolvers import (
  HiLoResolver,
  WordResolver,
  DwordResolver,
  TableResolver,
  OrderTableResolver
)


def int_autobase(i):
  if type(i) is int:
    return i
  else:
    return int(i, 0)


class CustomFormatter(
  argparse.RawTextHelpFormatter,
  argparse.ArgumentDefaultsHelpFormatter,):

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._max_help_position = 8


RESOLVER_MAP = {
  'word': (
    WordResolver,
    'Read single 16-pointer from memory and\n'
    '  optionally offset it by 8-bit index.\n'
    '    Format: POINTER[:FLAGS:INDEX], e.g. 0xfc::0xfe\n'
    '    Flags: b - pointer is Big Endian\n'),

  'dword': (
    DwordResolver,
    'Read single 32-pointer from memory and\n'
    '  optionally offset it by 8-bit index.\n'
    '    Format: POINTER[:FLAGS:INDEX], e.g. 0xfc::0xfe\n'
    '    Flags: b - pointer is Big Endian\n'),

  'hilo': (
    HiLoResolver,
    'Read 2 16-bit pointers from separate\n'
    '  memory locations.\n'
    '    Format: HI_BYTE_PTR:LO_BYTE_PTR e.g. 0x324:0x314\n'),

  'table': (
    TableResolver,
    'Get the data pointer from lookup table, \n'
    '  index in this table and offset inside that data index.\n'
    '  Table is assumed to contain WORD LE pointers.\n'
    '    Format: TABLE_POINTER:TABLE_INDEX:OFFSET_POINTER[:FLAGS]\n'
    '    Flags: w - Index is word, W - Offset is word, d - Index is pointer\n'
    '           o - Print final offset\n'
    '    Example: 0x66ec:0xef:0xf3:d will read data for CH1 of Outrun Europa.'),

  'order': (
    OrderTableResolver,
    'Get the data pointer from order lookup table, data lookup table, \n'
    '  index in this table and offset inside that data index.\n'
    '  Table is assumed to contain WORD LE pointers.\n'
    '    Format: ORDER_TABLE:DATA_TABLE:ORDER_INDEX:OFFSET_POINTER[:FLAGS]\n'
    '    Flags: W - Offset is word, o - Print final offset in info\n'),
}


def get_parser():

  parser = argparse.ArgumentParser(
    description='Dereference and monitor RAM pointer for changes, '
                'then format extracted bytes.',
    formatter_class=CustomFormatter)

  parser.add_argument(
    'filename',
    type=str,
    help='Memory file to read from (can be mmap too)')
  parser.add_argument(
    'ram_ptr',
    type=int_autobase,
    help='Emulator/player RAM offset used for analysis.\n'
         'Should point to internal address 0x0000')

  resolver_help = '\n'.join(
    f'{key}: {value[1]}' for key, value in RESOLVER_MAP.items())
  parser.add_argument(
    '-M', '--resolve-method',
    type=str,
    default='word',
    choices=RESOLVER_MAP,
    help=f'Function to resolve driver-specific data into memory offset:\n'
         + resolver_help)

  parser.add_argument(
    'resolver_settings',
    type=str,
    help='Arguments for resolver function')

  parser.add_argument(
    '-e',
    '--shift',
    type=int_autobase,
    default=0,
    help='Global offset when dereferencing pointers')
  parser.add_argument(
    '-r',
    '--data-ptr',
    type=int_autobase,
    help='Use this memory location to read data segment')
  parser.add_argument(
    '-j',
    '--jump-threshold',
    type=int_autobase,
    default=0x10,
    help='Threshold for detecting forward jumps.')
  parser.add_argument(
    '-l',
    '--preview',
    type=int_autobase,
    default=4,
    help='Explore this many bytes when step is unknown')
  parser.add_argument(
    '-E',
    '--end_pattern',
    type=str,
    default="",
    help='Comma separated bytes list to find tack end.')
  parser.add_argument(
    '-b',
    '--look-behind',
    action='store_true',
    help='Print values before new pointer after jump')
  parser.add_argument(
    '-w',
    '--max_octets',
    type=int_autobase,
    default=0x40,
    help='Wrap hex output after this many bytes')
  parser.add_argument(
    '-u',
    '--update-mem',
    action='store_true',
    help='Refresh data image on every jump')
  parser.add_argument(
    '-f',
    '--frequency',
    type=int_autobase,
    default=120,
    help='Pointer refresh frequency in Hz')
  parser.add_argument(
    '-s',
    '--buffer_len',
    type=int_autobase,
    default=0x10000,
    help='Memory snapshot size')

  return parser
