#!/usr/bin/env -S python3 -u
'''This little utility will repeatedly read an emulated-system specific pointer
defined by resolver class and print memory bytes when this pointer changes.

This will give you an idea how the data is consumed by an unknown software.

The next step from here is to write down this information for later use.

'''

import time
from shutil import get_terminal_size
from sys import stdout
from time import sleep
from traceback import print_exc

from cmd_parser import get_parser, RESOLVER_MAP
from memory_reader import Memory
from printers import HexPrinter
from consts import FWRD, BKWD, FJMP, BJMP, REST, PREV, LKUP
from consts import GRAY, GOLD, RESET


# Main processing loop
def mainloop(filename, ram_ptr, data_ptr, resolver, shift, jump_threshold,
             preview, end_patterns, look_behind, max_octets, frequency):

  # Code block, read every time when resolving pointers
  code = Memory(filename, ram_ptr)
  # Data block, static by default, defaults to code block
  data = Memory(filename, data_ptr)
  # Printer class which consumes extracted bytes
  printer = HexPrinter(max_octets, end_pattern=end_pattern)

  # Setup global state
  ptr = resolver(code, data) + shift
  info = resolver.info

  old_ptr = ptr
  old_info = resolver.info

  # 5 spaces always reserved for offset display
  print_width = len(old_info) + 5
  blanks = ' ' * print_width

  period = 1 / frequency
  next_time = time.perf_counter()

  # Print preview line from the current location
  printer(PREV, data[ptr:ptr + preview])
  stdout.write(
    f'{GRAY}{info}   **{RESET}│'
    f'{printer.prefix}{printer.result[0]}{printer.suffix}')

  while True:

    # We want info from previous calculation since we display data post-factum
    # So, do this now, calling resolver will update printout information.
    old_info = resolver.info

    # Calculate new pointer
    ptr = resolver(code, data) + shift
    info = resolver.info

    # Wait for period before checking if something changes
    next_time += period
    if old_ptr == ptr:
      while time.perf_counter() < next_time:
        sleep(0)
      continue

    diff = ptr - old_ptr
    jump_detected = diff > jump_threshold or diff < 0
    jmp_dir = FJMP if diff > 0 else BJMP

    # On forward jump display data after old pointer
    # and before new pointer for inspection
    if jump_detected:
      printer(jmp_dir, data[old_ptr: old_ptr+preview])

    # Main print routine
    else:
      printer(FWRD, data[old_ptr: old_ptr+diff])

    # Erase current line for the preview
    stdout.write('\033[2K\r')

    # Print what we have gathered from this pass
    prefix = f'{GOLD}{old_info}{GRAY}{diff:+5X}{RESET}'
    for idx, row in enumerate(printer.result):
      if idx:
        prefix = blanks
      stdout.write(
        f'{prefix}│'
        f'{printer.prefix}{row}{printer.suffix}\n')

    # If enabled, print what we got inside track just before jump head
    if jump_detected and look_behind:
      printer(LKUP, data[ptr-preview: ptr])
      for row in printer.result:
        stdout.write(
          f'{blanks}│'
          f'{printer.prefix}{row}{printer.suffix}\n')

    # Print preview line from the current location
    printer(PREV, data[ptr: ptr+preview])
    stdout.write(
      f'{GRAY}{info}   **{RESET}│'
      f'{printer.prefix}{printer.result[0]}{printer.suffix}')

    old_ptr = ptr


# Prepare and parse arguments here
def main():

  args = get_parser().parse_args()
  args_dict = vars(args)

  # Pre-cook some more complex settings here
  args_dict['data_ptr'] = args.ram_ptr \
    if args.data_ptr is None else args.data_ptr
  args_dict['resolver'] = RESOLVER_MAP[args.resolve_method][0](
    *args.resolver_settings.split(':'))
  args_dict['end_pattern'] = bytes.fromhex(
    args.end_pattern.replace(',', ' '))

  # Clear screen, disable cursor, disable wrap
  term_h, term_w = get_terminal_size()
  stdout.write(f'\033[2J\033[{term_h};1H\033[?7l\033[?25l')

  # Print some settings
  print(
    'RAM:  {:x}\n'.format(args_dict['ram_ptr']) +
    'ROM:  {:x}\n'.format(args_dict['data_ptr']) +
    '{:s}: {:s}\n'.format(args_dict['resolve_method'].upper(),
                          args_dict['resolver_settings']) +
    '═'*term_w)

  # We don't need these anymore
  args_dict.pop('resolve_method')
  args_dict.pop('resolver_settings')

  # Start the main loop
  try:
    mainloop(**args_dict)

  except KeyboardInterrupt:
    # Show cursor, enable wrapping
    stdout.write('\033[?25h\033[?7h')
    exit(0)
  except OSError:
    # Show cursor, enable wrapping
    print_exc()
    stdout.write('\033[?25h\033[?7h')
    exit(1)


if __name__ == '__main__':
  main()
