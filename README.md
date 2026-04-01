## Generic sequence data lookup utility


```
usage: pointer_logger.py [-h] [-M {ptr,table,order,stack}]
                         [-P {hex,bar,line,map}] [-p PRINTER_SETTINGS]
                         [-e SHIFT] [-r DATA_PTR] [-j JUMP_THRESHOLD]
                         [-l PREVIEW] [-b] [-f FREQUENCY]
                         filename ram_ptr resolver_settings

Dereference and monitor RAM pointer for changes, then format extracted bytes.

positional arguments:
  filename
        Memory file to read from (can be mmap too)
  ram_ptr
        Emulator/Player/Program RAM offset used for analysis.
        Should point to internal address 0x0 or segment start
        Format: [@]0x123123[,d|q][+offset]
          @ - resolve actual address from this pointer
          q - pointer is 64 bits (default)
          d - pointer is 32 bits
          + - add this much after resolving address OR add offset static pointer
        Example: @0x1025100,d+0x100
  resolver_settings
        Arguments for resolver function, it is a colon-separated
            list of values or key=value pairs. See resolver class
            sources for actual argument order and names

options:
  -h, --help
        show this help message and exit
  -M {ptr,table,order,stack}, --resolve-method {ptr,table,order,stack}
        Class for resolving driver-specific data into memory offset.
        ptr: Read single pointer, optionally add offset it by index.
            Format: POINTER[:INDEX][:FLAGS], e.g. 0xfc,v,5:0xfe
            Flags: m - Combine offset and pointer address in output
            Defaults: pointer: w , index: b

        table: Get the data pointer from lookup table,
          index in this table and offset inside that data index.
          Table is assumed to contain WORD LE pointers.
            Format: TABLE_POINTER:TABLE_INDEX:OFFSET_POINTER[:FLAGS]
            Flags: w - Index is word, W - Offset is word, d - Index is pointer
                   o - Print final offset
            Example: 0x66ec:0xef:0xf3:d will read data for CH1 of Outrun Europa.

        order: Get the data pointer from order lookup table, data lookup table,
          index in this table and offset inside that data index.
          Table is assumed to contain WORD LE pointers.
            Format: ORDER_TABLE:DATA_TABLE:ORDER_INDEX:OFFSET_POINTER[:FLAGS]
            Flags: W - Offset is word, o - Print final offset in info

        stack: Read data inside stack pointer that is offset by stack depth
            Format: STACK:DEPTH[:FLAGS][:SHIFT][:LOW:HIGH], e.g. 0x5ba:0x528::1
            Defaults: stack: w , depth: b
            Flags: n - substract depth value instead of adding
            SHIFT: Offset pointer by this many bytes. Useful when reference
                   points at loop counter followed by pointer
            LOW/HIGH: Shift only if discovered pointer is outside this region

        All pointer values support configurable TYPE:
            ADDRESS[,TYPE][,TYPE_ARGS] where type is one of:
            b - 8-bit Word; p - x86 Paragraph; w/W - 16-bit Word in LE or BE
            v/V{,STRIDE} - 16-bit LE/BE word with components STRIDE bytes apart
            d/D - 32-bit Word in LE or BE; q/Q - 64-bit Word in LE or BE
            Example: 0x700,v,8 - LE word with low byte at 0x700 and hi at 0x708

         (default: ptr)
  -P {hex,bar,line,map}, --printer-class {hex,bar,line,map}
        Class used to provide per-row result printout:
        hex:  Generic hex dump printer, uses global arguments
        bar:  Hex printer extension, plots values below 0x20 as a bar
        line: Hex printer extension, plots both positive and negative values
        map:  Prints parsed commands from definition file, falls back to hex
         (default: hex)
  -p PRINTER_SETTINGS, --printer_settings PRINTER_SETTINGS
        Colon separated string of printer parameters (default: )
  -e SHIFT, --shift SHIFT
        Globally add this offset when doing lookup (default: 0)
  -r DATA_PTR, --data-ptr DATA_PTR
        Memory location to read data segment (default: None)
  -j JUMP_THRESHOLD, --jump-threshold JUMP_THRESHOLD
        Threshold for detecting forward jumps. (default: 16)
  -l PREVIEW, --preview PREVIEW
        Look up this many bytes when for jump or preview (default: 4)
  -b, --look-behind
        Print values before new pointer after jump (default: False)
  -f FREQUENCY, --frequency FREQUENCY
        Polling rate in Hz (default: 120)

```
