''' Implements container-like access to file/memory objects.
/proc/PID/mem files do not support mmap, hence manual simulator for this behavior.
'''

import os

class Memory:
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

  def byte(self, address):
    return int.from_bytes(self[address])

  def word_le(self, address):
    return int.from_bytes(self[address:address+2], 'little')

  def word_be(self, address):
    return int.from_bytes(self[address:address+2], 'big')

  def dword_le(self, address):
    return int.from_bytes(self[address:address+4], 'little')

  def dword_be(self, address):
    return int.from_bytes(self[address:address+4], 'big')

  def close(self):
    self.handle.close()
