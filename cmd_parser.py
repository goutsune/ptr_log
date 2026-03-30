import argparse
import re

from resolvers import (
  PointerResolver,
  WordStackResolver,
  HiLoStackResolver,
  TableResolver,
  OrderTableResolver,
)

from printers import (
  HexPrinter,
  BarPrinter,
  LinePrinter,
  MappedPrinter,
)

from util import int_autobase


def subargs_parser(tokens):
  # Handle no args case gracefully
  if not tokens:
    return [], {}

  parts = tokens.split(':')
  args = []
  kwargs = {}

  for part in parts:
    if '=' not in part:
      args.append(part)
    else:
      key, value = part.split('=', 1)
      kwargs[key] = value

  return args, kwargs


def parse_addr(tokens):
  regex = (
    r'(@)?'                          # is this a pointer to addr?
    r'((?:0x)?[0-9a-fA-F]+)'         # what's the addr?
    r'(?:,([dq]))?'                  # is this dword or qword?
    r'(?:\+((?:0x)?[0-9a-fA-F]+))?'  # add some more bytes to that addr?
  )
  result = re.match(regex, tokens)
  resolve, addr, width, offset = result.groups()

  # Normalize a bit
  resolve = bool(resolve)
  addr = int_autobase(addr)  # Fail for None
  width = 32 if width == 'd' else 64
  offset = int_autobase(offset) if offset else 0

  return resolve, addr, width, offset


class CustomFormatter(
  argparse.RawTextHelpFormatter,
  argparse.ArgumentDefaultsHelpFormatter,):

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._max_help_position = 8


RESOLVER_MAP = {
  'ptr': (
    PointerResolver,
    'Read single pointer, optionally add offset it by index.\n'
    '    Format: POINTER[:INDEX][:FLAGS], e.g. 0xfc,v,5:0xfe\n'
    '    Flags: m - Combine offset and pointer address in output'
    '    Defaults: pointer: w , index: b\n'),

  'table': (
    TableResolver,
    'Get the data pointer from lookup table, \n'
    '  index in this table and offset inside that data index.\n'
    '  Table is assumed to contain WORD LE pointers.\n'
    '    Format: TABLE_POINTER:TABLE_INDEX:OFFSET_POINTER[:FLAGS]\n'
    '    Flags: w - Index is word, W - Offset is word, d - Index is pointer\n'
    '           o - Print final offset\n'
    '    Example: 0x66ec:0xef:0xf3:d will read data for CH1 of Outrun Europa.\n'),

  'order': (
    OrderTableResolver,
    'Get the data pointer from order lookup table, data lookup table, \n'
    '  index in this table and offset inside that data index.\n'
    '  Table is assumed to contain WORD LE pointers.\n'
    '    Format: ORDER_TABLE:DATA_TABLE:ORDER_INDEX:OFFSET_POINTER[:FLAGS]\n'
    '    Flags: W - Offset is word, o - Print final offset in info\n'),

  'stack': (
    WordStackResolver,
    'Read single 16-pointer referenced at sequencer stack.\n'
    '    Format: STACK:HEAD, e.g. 0x5ba:0x528\n'),

  'stackhl': (
    HiLoStackResolver,
    'Read single 16-pointer referenced at sequencer stack.\n'
    '    Format: STACKH:STACKL:HEAD, e.g. 0x5ca:0x5ba:0x528\n'),
}

PRINTER_MAP = {
  'hex': (
    HexPrinter,
    'Generic hex dump printer, uses global arguments\n'),
  'bar': (
    BarPrinter,
    'Hex printer extension that plots values below 0x20 as a bar\n'),
  'line': (
    LinePrinter,
    'Hex printer extension that plots both positive and negative values\n'),
  'map': (
    MappedPrinter,
    'Prints parsed commands from definition file, \n'
    '    falling back to hexdump otherwise\n'),
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
    type=parse_addr,
    help='Emulator/player RAM offset used for analysis.\n'
         'Should point to internal address 0x0 or segment start\n'
         'Format: [@]0x123123[,d|q][+offset]\n'
         '  @ - resolve actual address from this pointer\n'
         '  q - pointer is 64 bits (default)\n'
         '  d - pointer is 32 bits\n'
         '  + - add this much after resolving address OR add offset static pointer\n'
         'Example: @0x1025100,d+0x100\n')

  resolver_help = '\n'.join(
    f'{key}: {value[1]}' for key, value in RESOLVER_MAP.items())

  printer_help = '\n'.join(
    f'{key}: {value[1]}' for key, value in PRINTER_MAP.items())

  parser.add_argument(
    '-M', '--resolve-method',
    type=str,
    default='ptr',
    choices=RESOLVER_MAP,
    help='Class for resolving driver-specific data into memory offset.\n'
        + resolver_help + (
        '\nAll pointer values support configurable TYPE:\n'
        'ADDRESS[,TYPE][,TYPE_ARGS] where type is one of:\n'
        'b - 8-bit Word; p - x86 Paragraph; w/W - 16-bit Word in LE or BE\n'
        'v/V{,STRIDE} - 16-bit LE/BE word with components STRIDE bytes apart\n'
        'd/D - 32-bit Word in LE or BE; q/Q - 64-bit Word in LE or BE\n'
        'Example: 0x700,v,8 - LE word with low byte at 0x700 and hi at 0x708\n\n'
        ))

  parser.add_argument(
    '-P', '--printer-class',
    type=str,
    default='hex',
    choices=PRINTER_MAP,
    help=f'Class used to provide per-row result printout:\n'
         + printer_help)

  parser.add_argument(
    'resolver_settings',
    type=str,
    help='Arguments for resolver function, it is a colon-separated\n'
        '    list of values or key=value pairs. See resolver class\n'
        '    sources for actual argument order and names\n')

  parser.add_argument(
    '-e',
    '--shift',
    type=int_autobase,
    default=0,
    help='Global static offset when dereferencing pointers')
  parser.add_argument(
    '-r',
    '--data-ptr',
    type=parse_addr,
    help='Use this memory location to read data segment, \n'
          'same format as main pointer')
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
    '-p',
    '--printer_settings',
    type=str,
    default='',
    help='Colon separated string of printer parameters,\n'
         '    see resolver settings for format')
  parser.add_argument(
    '-b',
    '--look-behind',
    action='store_true',
    help='Print values before new pointer after jump')
  parser.add_argument(
    '-f',
    '--frequency',
    type=int_autobase,
    default=120,
    help='Pointer refresh frequency in Hz')

  return parser
