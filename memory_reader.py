''' Implements container-like access to file/memory objects.
/proc/PID/mem files do not support mmap, hence manual simulator for this behavior.
'''

import os
import ctypes
import ctypes.util

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


class IOVec(ctypes.Structure):
    _fields_ = [
        ("iov_base", ctypes.c_void_p),
        ("iov_len", ctypes.c_size_t),
    ]

libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
process_vm_readv = libc.process_vm_readv
process_vm_readv.argtypes = [
    ctypes.c_int,                     # pid_t pid
    ctypes.POINTER(IOVec), ctypes.c_ulong,  # const struct iovec *local_iov, ulong liovcnt
    ctypes.POINTER(IOVec), ctypes.c_ulong,  # const struct iovec *remote_iov, ulong riovcnt
    ctypes.c_ulong                    # flags
]
process_vm_readv.restype = ctypes.c_ssize_t

class MemoryReadV(Memory):
  def __init__(self, filename, base_offset):
    self.pid = int(filename.split('/')[2])
    self.base = base_offset
    self.local_iov = IOVec()
    self.remote_iov = IOVec()
    self.buf = bytearray(0x10000)
    self.c_buf = (ctypes.c_char * 0x10000).from_buffer(self.buf)
    self.local_iov.iov_base = ctypes.cast(self.c_buf, ctypes.c_void_p)

  def __getitem__(self, index):
    if isinstance(index, slice):
      start = index.start
      stop = index.stop
    else:
      start = index
      stop = index + 1

    size = stop - start

    self.local_iov.iov_len = size
    self.remote_iov.iov_base = self.base + start
    self.remote_iov.iov_len = size

    nread = process_vm_readv(self.pid,
                             ctypes.byref(self.local_iov), 1,
                             ctypes.byref(self.remote_iov), 1,
                             0)

    if nread < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))

    return self.buf[:nread]
