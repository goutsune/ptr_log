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

# Main processing loop
def mainloop(
  filename,
  data_base,
  rom_base,
  lo_ptr,
  hi_ptr,
  emu_offset,
  size,
  jump_thr=0x20,
  lookup=0x4,
  update_mem=False,
  frequency=120):

  # This will be file_h for the pointer lookup
  data_h = open(filename, 'rb', buffering=0)
  data_h.seek(data_base, os.SEEK_SET)

  # This one is for memory image update.
  mem_h = open(filename, 'rb', buffering=0)
  mem_h.seek(rom_base, os.SEEK_SET)

  mem_image = mem_h.read(size)
  mem_h.seek(rom_base, os.SEEK_SET)

  # read once to prepare 0 ztep pointer
  data_h.seek(data_base + lo_ptr, os.SEEK_SET)
  lo_byte = data_h.read(1)
  data_h.seek(data_base + hi_ptr, os.SEEK_SET)
  hi_byte = data_h.read(1)

  # Setup global state
  old_ptr_val = int.from_bytes(hi_byte+lo_byte)
  ptr_val = old_ptr_val
  step = 0
  old_step = 0

  while True:
    # calculate pointer
    data_h.seek(data_base + lo_ptr, os.SEEK_SET)
    lo_byte = data_h.read(1)
    data_h.seek(data_base + hi_ptr, os.SEEK_SET)
    hi_byte = data_h.read(1)
    ptr_val = int.from_bytes(hi_byte+lo_byte)

    # Skip nops
    if old_ptr_val == ptr_val:
      sleep(1/frequency)
      continue

    step = ptr_val - old_ptr_val

    # Print from whence we read data
    print('{:04X}{:+5X}│'.format(old_ptr_val, step), end='')

    # Update memory image on jumps
    if update_mem and (step > jump_thr or step < 0):
      mem_image = mem_h.read(size)
      if mem_image is None or len(mem_image) < size:
        print('! READ FAIL')
      mem_h.seek(rom_base, os.SEEK_SET)

    # On forward jump display data after old pointer and before new pointer for inspection
    if step > jump_thr:
      print('►{{{:s}}}'.format(
        mem_image[old_ptr_val+emu_offset:old_ptr_val+emu_offset+lookup].hex(' ')))
      print('         │▴{{{:s}}}'.format(
        mem_image[ptr_val+emu_offset-lookup:ptr_val+emu_offset].hex(' ')))

    # Main print routine
    elif step > 0:
      print('∙ {:s}'.format(
        mem_image[old_ptr_val+emu_offset:old_ptr_val+emu_offset+step].hex(' ')))

      # Extra debug output.

      # This will print values around old pointer
      #print('             _ {:s}|{:s}'.format(
      #  mem_image[old_ptr_val+emu_offset-lookup:old_ptr_val+emu_offset].hex(' '),
      #  mem_image[old_ptr_val+emu_offset:old_ptr_val+emu_offset+lookup].hex(' ')))

      # This will print values around new pointer
      #print('             _ {:s}|{:s}'.format(
      #  mem_image[ptr_val+emu_offset-lookup:ptr_val+emu_offset].hex(' '),
      #  mem_image[ptr_val+emu_offset:ptr_val+emu_offset+lookup].hex(' ')))

    # We jumped backward, display what's behind old pointer and before new pointer
    else:
      print('◄{{{:s}}}'.format(
        mem_image[old_ptr_val+emu_offset:old_ptr_val+emu_offset+lookup].hex(' ')))

      print('         │▴{{{:s}}}'.format(
        mem_image[ptr_val+emu_offset-lookup:ptr_val+emu_offset].hex(' ')))

    old_ptr_val = ptr_val
    old_step = step


# Prepare and parse arguments here
def main():
  parser = argparse.ArgumentParser(
    description='Monitor RAM pointer for changes and print bytes at old pointer with measured step.')

  parser.add_argument('filename', type=str,
    help='Memory file to read from (this can be normal file too, if it is updated frequently')
  parser.add_argument('base_offset', type=str,
    help='Global memory offset for RAM file, this denotes beginning of emulator RAM')
  parser.add_argument('lo_ptr', type=str,
    help='Virtual pointer lo byte')
  parser.add_argument('hi_ptr', type=str,
    help='Virtual pointer hi byte')

  parser.add_argument('-e', '--emu-offset', type=str, default="0x0",
    help='Pointer offset when dereferencing emulator memory')
  parser.add_argument('-r', '--rom-offset', type=str, default="0x0",
    help='Use this memory offset to read ROM image, defaults base offset')
  parser.add_argument('-j', '--jump-threshold', type=str, default="0x8",
    help='Threshold for detecting forward jumps.')
  parser.add_argument('-l', '--lookup', type=str, default="0x4",
    help='Explore this many bytes when jump is detected')
  parser.add_argument('-u', '--update-mem', type=int, default=0,
    help='Refresh memory image on every jump [0/1]')
  parser.add_argument('-f', '--frequency', type=int, default=120,
    help='Pointer test frequency in Hz. Defaults to 120')
  parser.add_argument('-s', '--size', type=str, default="0x10000",
    help='Memory snapshot size, default is 64KiB')

  args = parser.parse_args()

  # Can't bother with proper argparse type now
  filename = args.filename
  base_offset = int(args.base_offset, 0)
  size = int(args.size, 0)
  lo_ptr = int(args.lo_ptr, 0)
  hi_ptr = int(args.hi_ptr, 0)
  emu_offset = int(args.emu_offset, 0)
  jump_threshold = int(args.jump_threshold, 0)
  lookup = int(args.lookup, 0)
  update_mem = bool(args.update_mem)
  rom_offset = int(args.rom_offset, 0)
  if rom_offset == 0:
    rom_offset = base_offset

  # Print all the metadata
  print('FILE: {}'.format(filename))
  print('RAM: {:08x}, ROM: {:08x}, SIZE: {:04x}'.format(base_offset, rom_offset, size))
  print('PTR@: {:04x}:{:04x}, OFFSET: {:04x}'.format(lo_ptr, hi_ptr, emu_offset))
  print('═════════╤════════════════')

  # Start the main loop
  try:
    mainloop(
      filename,
      base_offset,
      rom_offset,
      lo_ptr,
      hi_ptr,
      emu_offset,
      size,
      jump_thr=jump_threshold,
      lookup=lookup,
      update_mem=update_mem,
      frequency=args.frequency)
  except KeyboardInterrupt:
    exit(0)

if __name__ == '__main__':
  main()
