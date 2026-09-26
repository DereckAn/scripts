# Lesson 00: Glossary

Every word the course uses, explained simply, with an example from **this** keyboard wherever one exists. Terms are in alphabetical order. Lessons link here using `00-glossary.md#term`.

[Course home](README.md)

---

### ADC
**Analog-to-Digital Converter.** A circuit that measures a voltage and turns it into a number. It works like a thermometer that says "72" instead of showing a colour. The keyboard's Hall sensors produce voltages, and a converter turns each voltage into a number the chip can compare. The SNC7320 series brief lists a 10-bit, six-channel SAR ADC ([notes/references.md](../notes/references.md)). The converter loop the firmware actually uses was found in the second execution context (log 118).

### Actuation
The moment a key counts as "pressed". On this keyboard the firmware turns each key's travel into a number from 0 to 200. `travel >= 100` means down, `travel == 0` means up, and values from 1 to 99 leave the key as it was, which is the **hold band** (logs 110, 119).

### Address
A number that names one byte of memory. It's like a house number on a very long street. `0x18000000` is the address where the application's code starts in RAM.

### AIRCR
**Application Interrupt and Reset Control Register** (`0xe000ed0c`). It's a built-in ARM register. Writing `0x05fa0004` to it asks the chip to reset itself. `0x05fa` is the "key" that proves you meant it (log 100).

### Allowlist
A list of the only things that are allowed. The offline tools refuse to modify any file whose SHA-256, base, and size don't match an allowlisted source (log 94).

### Armoury Crate
ASUS's Windows app for configuring the keyboard. Watching what it sends over USB taught us the vendor commands (Lesson 5, log 126).

### Back-reference
In compression, an instruction that says "copy N bytes from earlier in the output" instead of storing the bytes again. See [LZ77](#lz77).

### Base address
The address where a piece of code expects to live in memory. If you load code at the wrong base, every pointer in it points to the wrong place. It's like reading a map with the wrong starting point. Candidate B's base is `0x18000000` (logs 62–70).

### bcdDevice
A USB descriptor field that holds the device's release number. This keyboard reports `0x0159`, which is version 1.59 (log 04).

### Big-endian
Storing the **most** significant byte first. ARM Cortex-M normally uses the opposite order. See [little-endian](#little-endian).

### bInterval
A USB endpoint field that says how often the host should check it. At high speed, `bInterval = 1` means every 125 µs (log 107, log 126).

### Bit
The smallest piece of information: 0 or 1.

### Bootloader
The small program that runs first. It checks the main firmware and starts it, or it stays in a service mode where new firmware can be written. On this keyboard it lives in flash `[0x0, 0x10000)` and appears on USB as PID `1b7f`, "Gaming Keyboard Bootloader2" (log 81).

### Brick
A device that no longer starts and can't easily be repaired. Avoiding a brick is the reason for every safety rule in [Lesson 3](03-the-detectives-rules.md).

### Byte
8 bits. It can hold a number from 0 to 255 (`0x00`–`0xff`).

### Candidate A / Candidate B
The names the investigation gave to the two code payloads it found in the firmware before it knew what they did. **A** (file `0x11000`) turned out to be the entry image, or first-stage loader. **B** (file `0x21000`) is the keyboard application (logs 36, 79–80).

### Checksum
A small number calculated from a larger block of data. If one byte changes, the checksum almost always changes too. It's like adding up all the prices on a receipt to check that nothing was altered. This keyboard uses [CRC-32](#crc) sums and additive [word-sums](#word-sum) (logs 74–76).

### Control transfer
A USB message sent on endpoint 0, which is the "front desk" every USB device has. `GET_DESCRIPTOR`, `SET_REPORT`, and `GET_REPORT` are control transfers.

### Cortex-M3
The ARM processor core inside the SONiX chip. The SNC7320 series has **two** of them (the product brief, [Lesson 7](07-arm-cortex-m3.md)).

### CRC
**Cyclic Redundancy Check**, a strong checksum. The keyboard uses the standard IEEE CRC-32, whose reflected polynomial `0xedb88320` appears in the bootloader (log 74). The bootloader computes one CRC for each `0x10000`-byte chunk and **adds the results together** (log 75).

### Decompiler
A tool that turns machine instructions back into C-like code a person can read. Ghidra includes one. Its output is a guess, so the investigation checked important results against the raw **listing** (the instructions themselves).

### Descriptor
A small block of data a USB device sends to describe itself: who made it, what it is, and how to talk to it. The main kinds are device, configuration, interface, endpoint, HID, and report descriptors ([Lesson 4](04-usb-and-hid.md)).

### DFU
**Device Firmware Upgrade**, the standard USB method for updating firmware. This keyboard does **not** offer it: `dfu-util -l` found nothing (log 16).

### Dispatcher
A function that reads a command byte and jumps to the right handler, like a receptionist routing phone calls. The vendor command dispatcher is at `0x18001fbe` (log 48).

### Dry run
Running a tool so it shows what it *would* do without doing it. The device tools default to dry run and need explicit flags before they act (log 83).

### Dump
A copy of a memory's contents saved to a file. The verified dump of the installed application region is `dumps/device/ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin` (log 92).

### Endpoint
A numbered channel on a USB interface, like a numbered mail slot. `0x81` means endpoint 1, direction IN (device to host). `0x0d` means endpoint 13, direction OUT (host to device). The top bit (`0x80`) gives the direction.

### Entropy
A measure of how random the data looks. Encrypted or compressed data has high entropy, close to 8 bits per byte. This firmware measured about 4.82, which means it is not globally encrypted (log 33).

### Enumeration
What happens when you plug in a USB device: the host asks for its descriptors, gives it an address, and loads drivers.

### Feature report
A HID report that is read or written with control transfers (`GET_REPORT` or `SET_REPORT`) rather than through an interrupt endpoint. Interface 4 (lighting) uses only feature reports (log 112).

### Firmware
The software that is permanently stored inside a device and runs on its own chip.

### Flash
Memory that keeps its contents when the power is off. The board has an external SPI flash chip, U5 (a ZB25VQ32, 4 MiB). The chip may also contain internal storage.

### Fn layer
A second set of key meanings that is active while Fn is held. `51 21` remaps a key on it (Lesson 5).

### Function
A named piece of code that does one job and then returns. Ghidra names the functions it finds `FUN_<address>`, for example `FUN_000029d4`.

### Ghidra
A free reverse-engineering tool from the NSA. It disassembles and decompiles machine code ([Lesson 8](08-ghidra.md)).

### Hall effect
A magnet near a Hall sensor changes the sensor's voltage. The closer the magnet, the bigger the change. Each key on this keyboard has a magnet, so the chip can measure *how far* a key is pressed instead of only whether it is on or off ([Lesson 1](01-what-is-a-keyboard.md), [Lesson 15](15-inside-keys-and-magnets.md)).

### Handshake
An agreed sequence of messages that proves both sides are in sync. The backup tool's sample→status→confirm handshake guarantees that a read chunk is complete (log 86).

### Hash
A fingerprint of a file. See [SHA-256](#sha-256).

### Hex
**Hexadecimal**, counting in base 16 with the digits `0–9` and `a–f`. One hex digit is 4 bits, so two hex digits make one byte. `0x10` = 16, `0xff` = 255, `0x10000` = 65,536 ([Lesson 2](02-how-computers-count.md)).

### HID
**Human Interface Device**, the USB class for keyboards, mice, and similar devices. Because the OS already has HID drivers, HID devices need no special driver. All five of this keyboard's interfaces are HID (class `0x03`).

### hidraw
A Linux device file (`/dev/hidrawN`) that gives raw access to one HID interface. **Writing to it sends data to the keyboard**, so the course never does that.

### Interface
One "function" of a USB device. This keyboard has five: boot keyboard, vendor channel, media/system/mouse, NKRO, and lighting (log 15).

### Interrupt (IRQ)
A hardware signal that makes the CPU pause, run a handler, and then continue. It's like a doorbell. `IRQ38` is the tick that drives key scanning (logs 109, 127).

### KBID
**Keyboard ID**, an internal selector (effective range 0–2) that picks which key-index map variant the firmware uses (log 67).

### KiB / MiB
1 KiB = 1,024 bytes (`0x400`). 1 MiB = 1,048,576 bytes. The firmware file is 496 KiB = `0x7c000` bytes.

### LampArray
The standard HID usage page (`0x59`, Lighting and Illumination) for RGB lighting. Interface 4 uses it (log 112).

### Listing
Ghidra's view of the raw instructions, one per line, with their addresses and bytes. It's more trustworthy than the decompiler's output.

### Literal pool
Constants that ARM code stores next to a function and loads with `ldr rX,[pc,#…]`. Many addresses in the firmware are found by reading these.

### Little-endian
Storing the **least** significant byte first. The 32-bit number `0x60011000` is stored as the bytes `00 10 01 60`. ARM Cortex-M uses this order ([Lesson 2](02-how-computers-count.md)).

### LZ77
A family of compression methods that mix plain **literal** bytes with **back-references** ("copy N bytes from D bytes ago"). The keyboard's USB descriptors are stored compressed this way and unpacked at boot (log 105).

### Mailbox
Shared memory that two programs use to pass messages. Here, it's a ring buffer at `0x20000000` between the application and the second execution context (log 118).

### Memory map
The table of which address ranges hold which things: flash, RAM, and hardware registers. It's like the floor plan of a building.

### MMIO
**Memory-Mapped I/O.** Hardware registers that appear at addresses. Reading or writing such an address controls the hardware directly. The USB controller is at `0x40100000` (log 107).

### Mermaid
A text syntax for drawing diagrams. VS Code's Markdown preview renders it.

### NKRO
**N-Key Rollover**, meaning any number of keys can be reported at once. Interface 3 sends a 152-bit bitmap with one bit per key (log 109).

### NVIC
**Nested Vectored Interrupt Controller**, the ARM block that enables interrupts and orders them by priority. Software enables IRQ6 and IRQ38 through it (log 100).

### Offset
A distance from a starting point. "File offset `0x21000`" means 0x21000 bytes from the start of the file.

### Opcode
The byte that says which command or instruction this is. For example, bootloader execute opcode `0x05` = READ (log 81).

### PCAP / pcapng
Files that store captured network or USB traffic, readable with Wireshark or tshark. See `captures/`.

### PID / VID
**Product ID** and **Vendor ID**, the pair of 16-bit numbers that identify a USB device. ASUS is VID `0x0b05`. Normal mode is PID `0x1b7e`, and bootloader mode is PID `0x1b7f`.

### Pointer
A value that is an address. It "points at" something else in memory.

### Polling rate
How often the keyboard offers a new report to the computer. On this keyboard the options are 1000 Hz or 8000 Hz. The command is `51 31` ([Lesson 17](17-polling-rate.md)).

### Preservation
Keeping an exact, verified copy of the original before changing anything.

### Profile
A saved set of settings. The firmware keeps six (log 125).

### RAM
Fast working memory that is lost when the power goes off. The application runs in RAM at `0x18000000`.

### Race condition
A bug whose outcome depends on which of two things happens first. The bootloader READ had one: the tool could read the buffer before the new data arrived (logs 85–86, [Lesson 12](12-the-race-and-the-backup.md)).

### Reachability
Whether any code path leads to a function. A function nobody calls might be dead code, or it might be called in a way the tool can't see (logs 104–106).

### Register (CPU)
One of the CPU's own tiny storage slots: `r0`–`r12`, `sp` (stack pointer), `lr` (link register), and `pc` (program counter) ([Lesson 7](07-arm-cortex-m3.md)).

### Register (hardware)
A memory-mapped address that controls hardware. See [MMIO](#mmio).

### Report
One HID message. The boot keyboard report is 8 bytes: a modifier byte, a reserved byte, and six key codes.

### Report descriptor
A HID descriptor that describes the layout of every report, in a small item language (`05 01 09 06 a1 01 …`).

### Reset handler
The first function the CPU runs after reset. Its address is the second word of the vector table.

### Reverse engineering
Working out how something was built by studying the finished product.

### RTOS
**Real-Time Operating System**, a small scheduler that runs several tasks. The application creates `INIT_TASK`, `OEM_MAIN_SERVICE_TASK`, `IDLE`, `Tmr Svc`, and `usbd_wdt` (log 106).

### Scatter-load
ARM's standard startup step: copy code and data from flash to RAM, decompress anything compressed, and zero-fill the rest. Candidate A does this for Candidate B (log 73).

### SHA-256
A cryptographic fingerprint of a file, 64 hex characters long. If two files have the same SHA-256, they are byte-identical for every practical purpose. The installed dump's is `fc6128ab…637b` (log 92).

### SN_FWIN
The magic text at file offset `0x10000` that marks the SONiX application header and its checksum record table (log 74).

### SNC73270 / SNC7320
The SONiX microcontroller on the board (marking SNC73270). It belongs to the SNC7320 series of dual Cortex-M3 chips. `SNC7320A` is the container marker at the start of the firmware file.

### SPI
**Serial Peripheral Interface**, a simple four-wire bus. The external flash chip U5 is an SPI NOR flash.

### Stack pointer (SP)
The register that points to the top of the stack, the area where functions keep local data. The first word of a vector table is the initial SP.

### SysTick
The ARM core's built-in timer. In the bootloader, its tick decides when a queued READ actually runs (log 85).

### Thumb-2
The compact instruction set that Cortex-M3 runs. Instructions are 2 or 4 bytes long. A pointer to Thumb code has bit 0 set, so `0x14a9` means "code at `0x14a8`".

### tshark
Wireshark's command-line version. It's used here to decode the USB captures (log 126).

### Veneer
A tiny piece of code that only jumps somewhere else, often to a different image. Veneers link the entry image and the application (logs 109, 119).

### Vector table
The table at the start of an ARM image: word 0 is the initial stack pointer, word 1 is the reset handler, and the rest are interrupt handlers. The entry image's table has 80 slots (log 100).

### VTOR
**Vector Table Offset Register** (`0xe000ed08`), which tells the CPU where the vector table is (log 101, log 123).

### Watchdog
A timer that resets the chip unless software "feeds" it regularly. It rescues a program that has frozen. The magic values `0x5afa…` unlock the two watchdog blocks at `0x40008000` and `0x40009000` (logs 113–114).

### Word
32 bits (4 bytes) on this CPU. A halfword is 16 bits.

### Word-sum
A simple checksum: add every 32-bit word together, keeping only the lowest 32 bits of the result. The last word of the region stores the sum. `0x5d27c5a9` at `0x7bffc` guards the application region (log 75).

### XIP
**Execute In Place**, running code directly from flash without copying it to RAM first. The flash window starts at `0x60000000`.

### Zero-init
The part of the scatter-load that fills a RAM region with zeros (see [scatter-load](#scatter-load)).
