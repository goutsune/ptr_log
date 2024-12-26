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

def lohi_pointer_resolver(memory, global_offset, lo_ptr, hi_ptr):
  ''' Lo + Hi byte pointer resolver.
  This is the most simple resolver here. It will take pointer offsets for 2 bytes,
  read these byte values from code segment and returns the pointer offset to analyze.
  '''

  memory.seek(global_offset + lo_ptr, os.SEEK_SET)
  lo_byte = memory.read(1)
  memory.seek(global_offset + hi_ptr, os.SEEK_SET)
  hi_byte = memory.read(1)

  return int.from_bytes(hi_byte + lo_byte)


# Main processing loop
def mainloop(
  filename,
  code_offset,
  data_offset,
  lo_ptr,
  hi_ptr,
  emu_offset,
  size,
  jump_thr=0x20,
  lookup=0x4,
  wrap=0x40,
  update_mem=False,
  frequency=120):

  # Code block, read every time when resolving pointers
  code_h = open(filename, 'rb', buffering=0)
  code_h.seek(code_offset, os.SEEK_SET)

  # Data block, static by default, defaults to code block
  data_h = open(filename, 'rb', buffering=0)
  data_h.seek(data_offset, os.SEEK_SET)

  data_image = data_h.read(size)
  data_h.seek(data_offset, os.SEEK_SET)

  # Setup global state
  old_ptr_val = lohi_pointer_resolver(code_h, code_offset, lo_ptr, hi_ptr)
  ptr_val = old_ptr_val
  step = 0
  old_step = 0

  while True:
    # calculate pointer
    ptr_val = lohi_pointer_resolver(code_h, code_offset, lo_ptr, hi_ptr)

    # Skip nops
    if old_ptr_val == ptr_val:
      sleep(1/frequency)
      continue

    step = ptr_val - old_ptr_val

    # Print from whence we read data
    print('{:04X}{:+5X}│'.format(old_ptr_val, step), end='')

    # Update memory image on jumps
    if update_mem and (step > jump_thr or step < 0):
      data_image = data_h.read(size)
      if data_image is None or len(data_image) < size:
        print('! READ FAIL')
      data_h.seek(data_offset, os.SEEK_SET)

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
    description='Monitor RAM pointer for changes and print bytes at old pointer with measured step.')

  parser.add_argument('filename', type=str,
    help='Memory file to read from (this can be normal file too, if it is updated frequently')
  parser.add_argument('code_offset', type=str,
    help='Global memory offset for RAM file, this denotes beginning of emulator RAM')
  parser.add_argument('lo_ptr', type=str,
    help='Virtual pointer lo byte')
  parser.add_argument('hi_ptr', type=str,
    help='Virtual pointer hi byte')

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
  lo_ptr = int(args.lo_ptr, 0)
  hi_ptr = int(args.hi_ptr, 0)
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
  print('PTR@: {:04x}:{:04x}, OFFSET: {:04x}'.format(lo_ptr, hi_ptr, emu_offset))
  print('═════════╤════════════════')

  # Start the main loop
  try:
    mainloop(
      filename,
      code_offset,
      data_offset,
      lo_ptr,
      hi_ptr,
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
