#!/usr/bin/env -S python3 -u
'''This little utility will repeatedly read an emulated-system specific pointer defined by 2 bytes and print
how did this pointer value change. This will give you an idea how the data is consumed by an unknown software.

The next step from here is to write down this information for later use.

TODO:
 * Add 16-bit pointer support
 * Make a map of commands and their sizes?
 * Add timestamp?
 * Rewrite in ncurses
 * And allow watching multiple pointers as defined by config in json
 * Add support for double-pointers from known pointer subroutine commmands
'''

import argparse
import time
from time import sleep
from shutil import get_terminal_size

from resolvers import HiLoResolver, WordResolver, DwordResolver, TableResolver, OrderTableResolver
from printers import HexPrinter
from printers import FWRD, BKWD, FJMP, BJMP, REST, PREV, LKUP  # Our lookup states
from memory_reader import Memory

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
    '           o - Print final offset'
    '    Example: 0x66ec:0xef:0xf3:d will read data for CH1 of Outrun Europa.'),

  'order': (
    OrderTableResolver,
    'Get the data pointer from order lookup table, data lookup table, \n'
    '  index in this table and offset inside that data index.\n'
    '  Table is assumed to contain WORD LE pointers.\n'
    '    Format: ORDER_TABLE:DATA_TABLE:ORDER_INDEX:OFFSET_POINTER[:FLAGS]\n'
    '    Flags: W - Offset is word, o - Print final offset in info\n'),
}

GRAY  = "\033[90m"
BGRAY = "\033[37m"
RED   = "\033[31m"
GOLD  = "\033[33m"
BRED  = "\033[91m"
BLUE  = "\033[34m"
BBLUE = "\033[94m"
RESET = "\033[0m"

# Main processing loop
def mainloop(
  filename,
  code_offset,
  data_offset,
  resolver,
  emu_offset,
  size,
  jump_thr,
  lookup,
  track_end_seq,
  look_behind,
  wrap,
  update_mem,
  frequency):

  code = Memory(filename, code_offset)  # Code block, read every time when resolving pointers
  data = Memory(filename, data_offset)  # Data block, static by default, defaults to code block
  printer = HexPrinter(wrap, end_pattern=track_end_seq)

  # Setup global state
  data_image = data[0:size]
  old_ptr_val = resolver(code) + emu_offset
  ptr_val = old_ptr_val
  step = 0
  old_step = 0
  old_info = resolver.info
  info = resolver.info
  print_width = len(old_info) + 5  # 5 spaces always reserved for offset display
  blanks = ' ' * print_width

  period = 1 / frequency
  next_time = time.perf_counter()


  # Print preview line from the current location
  printer(PREV, data_image[ptr_val:ptr_val+lookup])
  print(f'{GRAY}{info}   **{RESET}│{printer.prefix}{printer.result[0]}{printer.suffix}', end='')

  while True:

    # We want info from previous calculation since we display data post-factum
    # So, do this now, calling resolver will update printout information.
    old_info = resolver.info
    # Calculate pointer
    ptr_val = resolver(code) + emu_offset
    info = resolver.info
    # Skip nops
    next_time += period
    if old_ptr_val == ptr_val:
      while time.perf_counter() < next_time: sleep(0)
      continue

    step = ptr_val - old_ptr_val
    seq_end_found = False
    jump_detected = step > jump_thr or step < 0
    jump_directon = FJMP if step > 0 else BJMP
    jump_char = '►' if step > 0 else '◄'

    if jump_detected:
      # Update memory image on jumps
      if update_mem:
        data_image = data[0:size]
        if data_image is None or len(data_image) < size:
          exit(1)  # Exit on read failure

    # On forward jump display data after old pointer and before new pointer for inspection
    if jump_detected:
      printer(jump_directon, data_image[old_ptr_val:old_ptr_val+lookup])

    # Main print routine
    else:
      printer(FWRD, data_image[old_ptr_val:old_ptr_val+step])

    # Erase current line for the preview
    print('\033[2K\r', end='')

    # Print what we have gathered from this pass
    prefix = f'{GOLD}{old_info}{GRAY}{step:+5X}{RESET}'
    for idx, row in enumerate(printer.result):
      if idx:
        prefix = blanks
      print(f'{prefix}│{printer.prefix}{row}{printer.suffix}')

    # If enabled, print what we got inside track just before jump head
    if jump_detected and look_behind:
      printer(LKUP, data_image[ptr_val-lookup:ptr_val])
      for row in printer.result:
        print(f'{blanks}│{printer.prefix}{row}{printer.suffix}')

    # Print preview line from the current location
    printer(PREV, data_image[ptr_val:ptr_val+lookup])
    print(f'{GRAY}{info}   **{RESET}│{printer.prefix}{printer.result[0]}{printer.suffix}', end='')

    old_ptr_val = ptr_val
    old_step = step


# Prepare and parse arguments here
def main():
  parser = argparse.ArgumentParser(
    description='Monitor RAM pointer for changes and print bytes at old pointer with measured step.',
    formatter_class=argparse.RawTextHelpFormatter)

  parser.add_argument('filename', type=str,
    help='Memory file to read from (this can be normal file too, if it is updated frequently')
  parser.add_argument('code_offset', type=str,
    help='Global memory offset for RAM file, this denotes beginning of emulator RAM')
  parser.add_argument('resolver_settings', type=str,
    help='Arguments for resolver function')

  resolver_help = '\n'.join(f'{key}: {value[1]}' for key, value in RESOLVER_MAP.items())
  parser.add_argument('-M', '--resolve-method', type=str, default='hilo', choices=RESOLVER_MAP,
    help=f'Function to resolve driver-specific data into memory offset:\n{resolver_help}')
  parser.add_argument('-e', '--emu-offset', type=str, default="0x0",
    help='Pointer offset when dereferencing emulator memory')
  parser.add_argument('-r', '--data-offset', type=str, default="0x0",
    help='Use this memory offset to read data segment, defaults base offset')
  parser.add_argument('-j', '--jump-threshold', type=str, default="0x8",
    help='Threshold for detecting forward jumps.')
  parser.add_argument('-l', '--lookup', type=str, default="0x4",
    help='Explore this many bytes when jump is detected')
  parser.add_argument('-E', '--track-end-seq', type=str, default="",
    help='Look for these bytes in lookup buffer to find tack end.')
  parser.add_argument('-b', '--look-behind', action='store_true',
    help='Print values before new pointer after jump')
  parser.add_argument('-w', '--wrap', type=str, default="0x40",
    help='Wrap hex output after this many bytes')
  parser.add_argument('-u', '--update-mem', action='store_true',
    help='Refresh memory image on every jump')
  parser.add_argument('-f', '--frequency', type=int, default=120,
    help='Pointer test frequency in Hz. Defaults to 120')
  parser.add_argument('-s', '--size', type=str, default="0x10000",
    help='Memory snapshot size, default is 64KiB')

  args = parser.parse_args()

  # Can't bother with proper argparse type now
  filename = args.filename
  code_offset = int(args.code_offset, 0)
  size = int(args.size, 0)
  resolver = RESOLVER_MAP[args.resolve_method][0]
  resolver_args = args.resolver_settings.split(':')
  resolver_instance = resolver(*resolver_args)
  emu_offset = int(args.emu_offset, 0)
  jump_threshold = int(args.jump_threshold, 0)
  lookup = int(args.lookup, 0)
  track_end_seq = bytes.fromhex(args.track_end_seq.replace(',',' '))
  look_behind = args.look_behind
  wrap = int(args.wrap, 0)
  update_mem = args.update_mem
  data_offset = int(args.data_offset, 0)
  if data_offset == 0:
    data_offset = code_offset

  term_h, _ = get_terminal_size()
  print(f'\033[2J\033[{term_h};1H\033[?7l', end='')

  # Print all the metadata
  print('FILE: {}'.format(filename))
  print('RAM: {:08x}'.format(code_offset))
  print('ROM: {:08x}'.format(data_offset))
  print('ARGS: {:s}'.format(args.resolver_settings))
  print('══════════════════════════')
  print('\033[?25l', end='')  # Hide cursor
  # Start the main loop
  try:
    mainloop(
      filename,
      code_offset,
      data_offset,
      resolver_instance,
      emu_offset,
      size,
      jump_thr=jump_threshold,
      lookup=lookup,
      track_end_seq=track_end_seq,
      look_behind=look_behind,
      wrap=wrap,
      update_mem=update_mem,
      frequency=args.frequency)
  except KeyboardInterrupt:
    print('\033[?25h\033[?7h', end='')  # Show cursor
    exit(0)

if __name__ == '__main__':
  main()
