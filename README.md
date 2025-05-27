This little utility will repeatedly read an emulated-system specific pointer defined by 2 bytes and print
how did this pointer value change. This will give you an idea how the data is consumed by an unknown software.

The next step from here is to write down this information for later use.

TODO
====

 * Make a map of commands and their sizes?
 * And allow watching multiple pointers as defined by config in json
 * Add support for emulator nested pointers, possibly helping with banking
 * Define a few driver-specific printers to refine interface
