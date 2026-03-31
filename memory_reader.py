''' Implements container-like access to file/memory objects.
/proc/PID/mem files do not support mmap, hence manual simulator for this behavior.
'''

import os
import ctypes
import ctypes.util
from functools import partial
from util import int_autobase

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

  # Vertically aligned word, common on 6502
  def vword_le(self, address, stride):
    return int.from_bytes((self[address]+self[address + stride]), 'little')

  def vword_be(self, address, stride):
    return int.from_bytes((self[address]+self[address + stride]), 'big')

  # Used on x86 CPUs in 16-bit mode
  def segment(self, address):
    return int.from_bytes(self[address:address+2], 'little') << 4

  def dword_le(self, address):
    return int.from_bytes(self[address:address+4], 'little')

  def dword_be(self, address):
    return int.from_bytes(self[address:address+4], 'big')

  def qword_le(self, address):
    return int.from_bytes(self[address:address+8], 'little')

  def qword_be(self, address):
    return int.from_bytes(self[address:address+8], 'big')

  def close(self):
    self.handle.close()


class MemoryReadV(Memory):

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

  def __init__(self, filename, base_offset):
    self.pid = int(filename.split('/')[2])
    self.base = base_offset
    self.local_iov = IOVec()
    self.remote_iov = IOVec()
    self.buf = bytearray(0x10000)  # allow reading up to this amount of bytes
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

    nread = self.process_vm_readv(self.pid,
                             ctypes.byref(self.local_iov), 1,
                             ctypes.byref(self.remote_iov), 1,
                             0)

    if nread < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))

    return self.buf[:nread]


class Pointer():
  # Shorthands that will be passed into kind argument
  mapping = {
    'b': ('byte',     '{:02x}'),
    'w': ( 'word_le', '{:04x}'), 'W': ( 'word_be', '{:04x}'),
    'v': ('vword_le', '{:04x}'), 'V': ('vword_be', '{:04x}'),
    'd': ('dword_le', '{:04x}'), 'D': ('dword_be', '{:04x}'),
    'q': ('qword_le', '{:08x}'), 'Q': ('qword_be', '{:08x}'),
    's': ('segment',  '{:05x}'),
  }

  value = None
  partial = None
  reader = None
  address = None
  extra = None
  fmt = '{:x}'

  def __init__(self, reader, address_str, *args, default_kind="w", **kwargs):

    # Extract address specification to pass into memory reader
    spec = address_str.split(',')

    address = int_autobase(spec[0])
    kind = spec[1] if len(spec) > 1 else default_kind
    # Might need to rethink argument parsing here, I don't want to make resolvers aware of pointer internals,
    # but this means I can't pass these as normal arguments. For now, it's only stride for vword, use autoint
    extra = [int_autobase(x) for x in spec[2:]]

    attr, fmt = self.mapping[kind]

    # Pre-bake resolver function
    bound = getattr(reader, attr)
    func = partial(bound, address, *extra)  # extra args needed by e.g. vword readers
    self.partial = func
    self.fmt = fmt

    # In case we have to dynamically adjust address on the fly
    self.reader = bound
    self.address = address
    self.extra = extra

  def __invert__(self):
    '''Using ~pointer instead of pointer() will return last read value
    without accessing external process memory.
    '''
    return self.value

  def __call__(self, addr=None):

    if addr is None: self.value = self.partial()
    else: self.value = self.reader(addr, *self.extra)

    return self.value
