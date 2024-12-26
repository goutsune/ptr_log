#!/usr/bin/env python3
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

import os, sys, io
import argparse
from time import sleep

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


RESOLVER_MAP = {
  'hilo': (
    HiLoResolver,
    'Read 2 16-bit pointers from separate\n'
    '  memory locations.\n'
    '    Format: HI_BYTE_PTR:LO_BYTE_PTR e.g. 0x324:0x314\n'),

  'word': (
    WordResolver,
    'Read single 16-pointer from memory,\n'
    '  LE is assumed.\n'
    '    Format: POINTER, e.g. 0x14\n'
  ),

  'table': (
    'TableResolver',
    'Get the data pointer from lookup table, \n'
    '  index in this table and offset inside that data index.\n'
    '  Table is assumed to contain WORD LE pointers, index\n'
    '  and offset are assumed to be 8-bit values.\n'
    '    Format: TABLE_POINTER:TABLE_INDEX:OFFSET_POINTER\n'
  )
}


class Memory:
  ''' Class to provide byte getter from a relative memory offset.
  '''
  base = None
  handle = None

  def __init__(self, filename, base_offset):

    handle = open(filename, 'rb', buffering=0)
    handle.seek(base_offset, os.SEEK_SET)

    self.base = base_offset
    self.handle = handle

  # Implement index-like file access with very basic slicing support
  def __getitem__(self, index):

    if type(index) == slice:
      amount = index.stop - index.start
      offset = index.start
    else:
      amount = 1
      offset = index

    if amount < 1:
      raise IndexError('Can\'t read nothing!')

    self.handle.seek(self.base + offset, os.SEEK_SET)
    data = self.handle.read(amount)
    return data

  def close(self):
    self.handle.close()


# Main processing loop
def mainloop(
  filename,
  code_offset,
  data_offset,
  resolver,
  emu_offset,
  size,
  jump_thr=0x20,
  lookup=0x4,
  wrap=0x40,
  update_mem=False,
  frequency=120):

  code = Memory(filename, code_offset)  # Code block, read every time when resolving pointers
  data = Memory(filename, data_offset)  # Data block, static by default, defaults to code block

  # Setup global state
  data_image = data[0:size]
  old_ptr_val = resolver(code)
  ptr_val = old_ptr_val
  step = 0
  old_step = 0

  while True:
    # calculate pointer
    ptr_val = resolver(code)

    # Skip nops
    if old_ptr_val == ptr_val:
      sleep(1/frequency)
      continue

    step = ptr_val - old_ptr_val

    # Print from whence we read data
    print('{:04X}{:+5X}│'.format(old_ptr_val, step), end='')

    # Update memory image on jumps
    if update_mem and (step > jump_thr or step < 0):
      data_image = data[0:size]
      if data_image is None or len(data_image) < size:
        print('! READ FAIL')

    # On forward jump display data after old pointer and before new pointer for inspection
    if step > jump_thr:
      print('►{{{:s}}}'.format(
        data_image[old_ptr_val+emu_offset:old_ptr_val+emu_offset+lookup].hex(' ')))
      print('         │▴{{{:s}}}'.format(
        data_image[ptr_val+emu_offset-lookup:ptr_val+emu_offset].hex(' ')))

    # Main print routine
    elif step > 0:
      from_o = old_ptr_val + emu_offset
      to_ofc = old_ptr_val + emu_offset + step
      tokens = data_image[from_o:to_ofc]

      old_pos = 0
      for pos in range(0, len(tokens), wrap):
        if pos:  # For consecutive lines
          print('         │', end='')
        print('∙ {:s}'.format(tokens[pos:wrap+pos].hex(' ')))
        old_pos = pos

      # Extra debug output.

      # This will print values around old pointer
      #print('             _ {:s}|{:s}'.format(
      #  data_image[old_ptr_val+emu_offset-lookup:old_ptr_val+emu_offset].hex(' '),
      #  data_image[old_ptr_val+emu_offset:old_ptr_val+emu_offset+lookup].hex(' ')))

      # This will print values around new pointer
      #print('             _ {:s}|{:s}'.format(
      #  data_image[ptr_val+emu_offset-lookup:ptr_val+emu_offset].hex(' '),
      #  data_image[ptr_val+emu_offset:ptr_val+emu_offset+lookup].hex(' ')))

    # We jumped backward, display what's behind old pointer and before new pointer
    else:
      print('◄{{{:s}}}'.format(
        data_image[old_ptr_val+emu_offset:old_ptr_val+emu_offset+lookup].hex(' ')))

      print('         │▴{{{:s}}}'.format(
        data_image[ptr_val+emu_offset-lookup:ptr_val+emu_offset].hex(' ')))

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
  parser.add_argument('-w', '--wrap', type=str, default="0x40",
    help='Wrap hex output after this many bytes')
  parser.add_argument('-u', '--update-mem', type=int, default=0,
    help='Refresh memory image on every jump [0/1]')
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
  wrap = int(args.wrap, 0)
  update_mem = bool(args.update_mem)
  data_offset = int(args.data_offset, 0)
  if data_offset == 0:
    data_offset = code_offset

  # Print all the metadata
  print('FILE: {}'.format(filename))
  print('RAM: {:08x}, ROM: {:08x}, SIZE: {:04x}'.format(code_offset, data_offset, size))
  print('═════════╤════════════════')

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
      wrap=wrap,
      update_mem=update_mem,
      frequency=args.frequency)
  except KeyboardInterrupt:
    exit(0)

if __name__ == '__main__':
  main()
