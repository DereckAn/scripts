# ASUS ROG Falchion Ace HFX reverse-engineering timeline

Last updated: 2026-08-29 (America/Mexico_City)

This document is the chronological record of the investigation. It explains
what was done, why it was done, what changed, and where the supporting evidence
is stored. Use [`FINDINGS.md`](FINDINGS.md) for the authoritative current
technical conclusions and [`logs/COMMANDS.md`](logs/COMMANDS.md) for the exact
command-to-log index.

## Evidence and safety conventions

- **Verified current evidence** means reproduced from the connected keyboard,
  preserved ASUS files, or saved offline analysis during the 2026-08-29 work.
- **Historical observation** means recorded by the earlier Windows/Armoury Crate
  investigation. The notes and decoded snapshots exist, but the cited raw PCAP
  files are not currently present in the repository.
- **Inference** means a conclusion supported by several facts but not yet proven
  directly.
- **Unresolved** means the available evidence does not support a safe answer.

The preservation boundary for the current work was strict: no firmware update,
vendor-HID write, feature-value request, DFU upload/download/detach, USB reset,
driver detach, permission change, bootloader transition, erase, program, or SPI
transaction was performed. No SPI Write Enable (`0x06`) was sent. Offline
analysis scripts never communicated with the keyboard.

Earlier protocol experiments did send configuration-changing HID reports. They
are retained as historical evidence and were not repeated during preservation.

## Current status at a glance

- Normal USB identity: ASUS `0b05:1b7e`, device release `1.59`.
- Five normal-mode HID interfaces; no DFU-class interface.
- Both physical keyboard connectors expose the same normal-mode USB layout.
- Standard USB firmware backup is not exposed. Proprietary or bootloader-mode
  readback remains unresolved.
- Official ASUS firmware 1.00.58 is preserved and hashed, but it is not a dump
  of the installed 1.59 firmware.
- The vendor updater is a proprietary HID erase/program tool using normal PID
  `1b7e` and bootloader PID `1b7f`; it was never executed.
- Candidate B contains the vendor-HID dispatcher and device-side unsupported-key
  policy logic.
- No installed-firmware, U5, or MCU readback has yet been obtained.

## 2026-08-17 — Initial USB investigation

Commit `307e921` began the repository investigation and preserved an early USB
descriptor capture plus a report descriptor. This established the initial plan
to identify the device and eventually investigate firmware modification.

What survived and remains useful:

- a large USB descriptor record in `notes/usb-descriptors.txt`;
- the first report-descriptor artifact in `notes/report-desc-0.txt`.

Later review found that the small `report-desc-0.txt` artifact could not be
reliably attributed to Falchion interface 4. It remains preserved for provenance
but is not treated as current interface evidence.

## 2026-08-18 — Component and interface notes

Commit `f28a7a2` added early findings and the vendor-page `0xFF00` report
descriptor. The important lasting observation was that one interface transports
64-byte vendor input and output reports, making it the likely ASUS configuration
channel.

The investigation also recorded the user-observed board hardware:

- SONiX SNC73270 main MCU;
- Zbit ZB25VQ32BTIG U5 external flash, 32 Mbit / 4 MiB;
- expected U5 JEDEC ID `5E 40 16`;
- U7 `DIO322 2403 2F3`, likely a USB signal switch;
- unidentified U12 `C3NC V0006`.

These markings have not yet been electrically traced. No programmer or debug
probe was connected.

## 2026-08-26 — Armoury Crate protocol and key-map work

Commit `f53b293` added decoded Armoury Crate profile data, a baseline snapshot,
key-matrix notes, protocol notes, and PowerShell observation/decoding tools.
Historical experiments associated interface 1 with 64-byte ASUS configuration
traffic and recorded commands including:

- `12 00`: version query;
- `51 21`: live Fn-layer remap;
- `50 55`: persistent configuration commit.

The work mapped the 68 physical keys to one-based row-major source indices and
showed that a `51 21` change can take effect immediately without `50 55`.
Therefore an uncommitted remap is still a device write and is not
preservation-safe.

The raw USBPcap/PCAP files cited by these notes are absent from the repository
and reachable Git history. The decoded JSON/CSV artifacts and behavioral notes
remain valuable, but exact packet sequences must be treated as historical until
the captures are recovered.

## 2026-08-26 — Reserved Fn-key behavior

Commit `205ef8f` expanded the protocol work with a controlled historical A/B
observation: ordinary Fn-layer remaps became effective, while reserved Fn
functions such as `Fn+Q` and `Fn+1` remained unchanged even though the device
echoed the request. Armoury Crate also reportedly blocked these combinations in
its UI before sending traffic.

This established the practical warning that an echoed response is not proof a
binding became active. The later offline firmware analysis independently found
the device-side policy mechanism that explains this behavior.

## 2026-08-26 — Backup and recovery assessment

Commit `87e22df` documented the Phase 2 preservation problem. It correctly
separated an official firmware package from a true installed-device backup and
identified missing prerequisites: a readback method, recovery path, hardware
signal map, and verified tooling.

Some early guide content still contained generic STM32 assumptions and unsafe
write examples. Those were removed or quarantined during the later
documentation synchronization.

## 2026-08-29 02:11–02:29 — Read-only Linux USB inspection

The current evidence-driven investigation began by recording the host context
and inspecting the connected keyboard with standard descriptors, sysfs, udev,
and read-only enumeration. Raw evidence is in logs `00–18`.

Verified results:

- VID:PID `0b05:1b7e`, manufacturer `ASUSTeK`, product
  `ROG FALCHION ACE HFX`, device release `1.59`;
- one configuration containing five HID interfaces;
- interface 0: boot keyboard, interrupt IN `0x81`;
- interface 1: vendor page `0xFF00`, 64-byte IN `0x85` and OUT `0x0d`;
- interface 2: consumer/system/mouse and vendor reports, IN `0x8c`;
- interface 3: keyboard bitmap, IN `0x8e`;
- interface 4: Lighting and Illumination page `0x59`, OUT `0x0f`, unbound because
  it has no input interrupt endpoint;
- no DFU-class interface and no target reported by direct `dfu-util -l`.

`fwupd` was not installed at the time of this check, so no fwupd detection claim
was made. Installing it was considered optional and low-value because the device
does not advertise DFU in normal mode.

Two environmental failures were preserved rather than hidden:

- `logs/01-lsusb.txt`: the first sandboxed libusb call failed;
- `logs/11-dfu-util-list.txt`: the first sandboxed DFU enumeration failed.

Approved direct read-only retries succeeded in `logs/15` and `16`. No device
node permission was changed.

## 2026-08-29 02:29–02:34 — Other connector retry

The keyboard was reconnected through its other physical connector and the same
safe inspection was repeated. Evidence is in logs `19–26`.

It re-enumerated with a new transient device address but retained the same
sysfs port, VID:PID, release number, five HID interfaces, endpoint layout,
report descriptors, and lack of DFU. The second connector therefore provides no
additional normal-mode USB access.

`logs/25-port-retry-comparison.txt` initially reported a descriptor difference
because its parser included an `xxd` ASCII column. The mistake was retained for
auditability and corrected with strict byte parsing in log 26, which showed the
descriptor bytes were identical.

## 2026-08-29 02:34–02:45 — Earlier-work audit

Logs `27–28` compared prior notes, captures, commits, scripts, and present USB
evidence.

Corrections made or queued from this audit:

- the old `0xFF32` descriptor could not be assigned to current interface 4;
- “no USB bootloader” was narrowed to “no DFU/bootloader interface in normal
  mode”;
- historical mode `0666` permission claims were not reasserted;
- generic STM32 load addresses, OpenOCD targets, and flashing commands were
  declared invalid for this SONiX target;
- configuration writes were separated from genuinely read-only phases;
- missing raw PCAP provenance was made explicit.

No historical raw artifact was deleted or silently rewritten.

## 2026-08-29 02:46–03:06 — Official ASUS package analysis and preservation

The user supplied the official package at
`/home/dereck/Downloads/ROG_FALCHION_ACE_HFX/`. No executable from it was run.
Logs `29–35` contain the original metadata, archive inventory, extracted-file
inventory, firmware-focused inventory, updater analysis, and preservation
verification.

Verified official artifacts:

- ASUS distribution ZIP: 238,446,426 bytes, SHA-256
  `a3e895dd4389e6725b15b0c0af6d6644a470a8359c4086a206490b74e9e9d7b9`;
- firmware `M605_V01_00_58.bin`: 507,904 bytes, SHA-256
  `6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d`.

The ZIP hash matched ASUS publication metadata. The firmware is version 1.00.58,
one release behind the keyboard's USB-reported 1.59. It is authentic recovery
material, not an installed-device backup.

Workspace preservation:

- ZIP: `vendor/asus/original/ROG_FALCHION_ACE_HFX.zip`;
- BIN: `dumps/vendor/M605_V01_00_58.bin`;
- manifest: `vendor/asus/ARTIFACTS.md`.

Both copies were compared byte-for-byte with their sources. The large ZIP is
locally preserved but ignored from ordinary Git staging because it exceeds
GitHub's normal file-size limit.

Static updater inspection found a proprietary HID update design:

- normal PID `1b7e`, bootloader PID `1b7f`;
- 64 KiB bootloader plus 432 KiB application;
- 4 KiB pages;
- Windows HID `ReadFile`/`WriteFile` transport;
- strings for bootloader entry, erase, programming, success, and checksum.

The updater executables are confirmed writers and were never launched. No
full-firmware readback function was established.

## 2026-08-29 03:06–03:22 — Firmware structure and modification feasibility

Logs `36–37` and `tool/analyze_sonix_firmware.py` established a reproducible
offline map of the 496 KiB SONiX container.

Major regions:

| File range | Current interpretation |
|---|---|
| `0x00000–0x0ffff` | Primary bootloader/container |
| `0x10000` | `SN_FWIN` application header |
| `0x11000–0x168ab` | Candidate application A |
| `0x17000–0x20fff` | `0xFF` padding |
| `0x21000–0x3f753` | Candidate application B |
| `0x40000–0x5ffff` | zero padding/reserved |
| `0x60000–0x70fff` | wrapper plus duplicated bootloader |
| `0x71000–0x73fff` | zero padding |
| `0x74000–0x7bfff` | executable RAM image at `0x18038000` |

Candidate A's standard CRC-32 matches its header value. Candidate B's apparent
stored integrity value does not match standard CRC-32 over the obvious range;
its exact integrity interpretation remains unresolved.

The image contains plain Thumb-2 code, strings, tables, and USB identity data;
it is not globally encrypted or compressed. That makes modification technically
plausible, but safe flashing remains blocked by unresolved integrity, loading,
backup, and recovery questions.

The SONiX SNC7320 family documentation supports a dual Cortex-M3 design with
shared SRAM/mailbox, SWD, remapping, and external SPI-NOR support. This makes it
unsafe to assume U5 alone contains everything required for recovery.

One temporary analysis loop initially decoded the firmware header instead of
the intended offsets because it passed an empty offset to `xxd`. It did not
modify any file and was immediately corrected.

## 2026-08-29 03:22–04:02 — Ghidra setup and first project

Logs `38–45` record the Ghidra setup and analysis. Ghidra 12.1.2 and JDK 21 were
installed by the user and verified. Four derived slices were imported as ARM
Cortex little-endian programs:

- primary bootloader at base `0x00000000`;
- Candidate A at base `0x00000000`;
- Candidate B at provisional base `0x00000000`;
- RAM image at base `0x18038000`.

The project resides under ignored `ghidra/project/falchion-hfx`; derived imports
are also ignored. The preserved ASUS BIN was not modified.

Verified vector/reset labels were added to the local project. Candidate B begins
with a valid Thumb function, but no vector or call path proves that address zero
is the true payload entry. Its initial label was therefore corrected from the
overconfident `CandidateB_Entry` to `CandidateB_Start_Function`. One isolated
Ghidra p-code warning near `0x24f2` was recorded; analysis otherwise completed.

The `.java` files in `ghidra/scripts/` run inside Ghidra's Java API. They inspect
Ghidra's program database and decompiler results; they are not firmware and are
never uploaded to the keyboard.

## 2026-08-29 04:02 — Documentation synchronization

Commit `d034c31` and log 46 synchronized the newly pulled historical commits
with the current evidence.

Changes included:

- making `FINDINGS.md` authoritative;
- rewriting condensed notes to distinguish verified and historical evidence;
- removing generic STM32 flashing recipes;
- quarantining write-capable PowerShell tools with explicit warnings;
- correcting Candidate B's provisional label;
- documenting missing PCAPs and the official artifact status;
- verifying all then-existing raw log hashes.

No keyboard access occurred during synchronization.

## 2026-08-29 21:55–22:06 — Candidate B vendor protocol analysis

Logs `47–55` and seven reproducible Ghidra scripts extended the static analysis.
All report runs used the local firmware/Ghidra project. No USB command was sent.

### Dispatcher identification

`0x00001fbe` was identified and labeled `VendorHID_CommandDispatcher`. It reads
the 64-byte request buffer at RAM `0x1802337c` and dispatches top-level commands,
including:

- `0x50`, with a `0x55` subcommand path consistent with the historical commit
  command;
- `0x51`, containing keyboard-configuration subcommands.

The only raw adjacent bytes `51 21` elsewhere in Candidate B were an instruction
encoding (`movs r1,#0x51`), not a packet table. This prevented a misleading
byte-pattern conclusion.

### `0x51/0x21` and `0x51/0x22`

The handler at `0x2662–0x27d4`:

- accepts source values through `0xbc`;
- accepts layer byte `0x00` or `0x9f`;
- treats bytes 4–5 as a 16-bit target;
- translates ordinary source/target indices through runtime RAM tables;
- gives special treatment to target values `0xff`, `0xc7`, `0xc8`, and `0xd3`;
- updates per-key records and dirty state;
- makes `0x22` store the actuation value divided by 10;
- calls the labeled `VendorHID_SendResponse64` routine to echo the request
  fields in a 64-byte reply.

There is no reserved-source rejection in this command handler. This statically
supports the historical observation that a reserved remap can receive an echo
without becoming effective.

### Unsupported-key policy

`0x00001f6e` was identified and labeled `IsKeyUnsupportedForLayer`. It copies
and searches one of two runtime arrays:

- 6 32-bit entries for selectors 0 or 2;
- 57 32-bit entries for other selectors, including the Fn load path.

The configuration-load state machine calls this predicate with selector 0 for
base mappings and selector 1 for Fn mappings. A match skips the mapping and uses
diagnostic strings `R_NSK_M` or `R_NSK_FnM`. This is the first static firmware
evidence explaining the historical “ACK but no effect” behavior.

At this stage, the 63 policy entries were known to begin at RAM `0x1801c810`,
but their values had not yet been recovered. Related runtime tables included:

- key translation: `0x1801bff6`;
- key-index mapping: `0x1801c37c`;
- key records: `0x18021db4`;
- vendor-HID buffer: `0x1802337c`.

Three high-confidence labels were saved only in the ignored Ghidra database and
confirmed by reopening it read-only:

- `0x00000a70` — `VendorHID_SendResponse64`;
- `0x00001f6e` — `IsKeyUnsupportedForLayer`;
- `0x00001fbe` — `VendorHID_CommandDispatcher`.

All logs `00–55` passed SHA-256 verification, no raw `.txt` log was missing from
the manifest, and the source BIN retained its original hash.

## 2026-08-29 22:06–22:27 — Candidate B runtime base and exact policy recovery

The next offline pass tested whether Candidate B's apparent RAM pointers were
actually offsets into the payload when loaded at `0x18000000`. The firmware
header contains that runtime address beside flash source `0x60021000` and length
`0x1e754`. Subtracting `0x18000000` from the key-table pointers produced valid
offsets inside Candidate B.

This recovered the tables directly from the official BIN:

- translation table: runtime `0x1801bff6`, full BIN `0x3cff6`;
- key-index map: runtime `0x1801c37c`, full BIN `0x3d37c`;
- unsupported lists: runtime `0x1801c810`, full BIN `0x3d810`.

The unsupported data contains exactly the 6 base-policy words and 57 Fn-policy
words used by `IsKeyUnsupportedForLayer`. Standard HID decoding shows the Fn
list covers the same locked-function families documented in the ASUS manual.

A byte-identical derived Candidate B program was imported into Ghidra at
`0x18000000`, leaving the historical base-zero import intact. Corrected-base
analysis resolves the earlier external pointers directly into the payload's
data block and preserves the same dispatcher/remap behavior. The script
`tool/analyze_candidate_b_tables.py` makes the table extraction reproducible
from the preserved vendor BIN.

Candidate B's runtime base/loading location is therefore strongly supported.
Its true entry/call path and integrity calculation remain unresolved.

## 2026-08-29 — Effective-KBID and overlapping key-map recovery

The next offline target was the data beginning at `0x1801c37c`. An initial
visual split into consecutive `0x86` chunks was retained in log 67, but code
references disproved the idea that they were eight independent rows.
`FUN_180088ea` calls a function returning `0x1a`, then indexes a 26-byte table at
runtime `0x00004fcd`. That table is in Candidate A at full BIN offset `0x15fcd`
and contains only selectors `0`, `1`, and `4`; Candidate B immediately converts
`4` to `2`. The effective KBID range is therefore exactly `0..2`.

The dispatcher accepts wire IDs `0x00..0xbc`, uses 189-byte logical windows, and
advances their base by only `0x86`. The three windows consequently overlap by
`0x37` bytes. The last window ends at `0x1801c544`. A separate scan-position map
starts at `0x1801c50e`; key initialization and scan code index its three rows
with a `0x100` stride. Its first 55 bytes are deliberately shared with the tail
of the third logical wire window.

The source-to-record calculation is now recovered as:

```text
record_index = byte[0x1801c37c + effective_kbid * 0x86 + wire_source]
record        = 0x180202ac + layer * 0xd84 + record_index * 0x20
```

The separate translation table at `0x1801bff6` supplies the internal code for
ordinary wire targets `0x00..0xbc`. Target `0xff` reuses the source translation;
targets `0xc7`, `0xc8`, and `0xd3` receive an `0xa000`-class special encoding.
The frequent record index `0x4b` is left as a fallback/dummy candidate because
its live RAM behavior is not yet proven.

The analyzer was extended to print the KBID lookup, all 189 source/target
translations, computed record addresses for all three selectors, the
capture-derived 68-key view, and hashes/full bytes for the three scan rows.
Logs 68 and 69 contain the deterministic analyzer output and the corrected
read-only Ghidra report. No USB access or firmware execution occurred.

## 2026-08-29 23:08–23:10 — Candidate A reset and scatter-load baseline

Toward the outstanding Candidate B loader/integrity target, the boot path of
`app_candidate_a.bin` was recovered first as a baseline. A read-only
`-noanalysis` run of `FalchionCandidateALoaderReport.java` disassembled and
decompiled the reset handler at `0x14a8`, the standard ARM `__scatterload`
routine at `0x148`, and the region-descriptor table at `0x5750`.

Three scatter regions were recovered: a block copy of `0x1e354` bytes from
`0x60021000` to `0x18000000`, a `0x0b04`-byte decompress from `0x6003f354` to
`0x1801e354`, and a `0x172e8`-byte zero-init at `0x1801ee58`. The copy source
`0x60021000` → destination `0x18000000` independently corroborates the
`0x18000000` runtime base used to rebase Candidate B in logs 62–70. The
clock/PLL init `FUN_00001216` also bounds-checks the stack pointer to
`[0x18000000, DAT_000014a4]` and faults otherwise — a startup guard, not
Candidate B image verification. Candidate A's loader does not contain or compute
`0x1a76c116`, which remains the next offline target.

Logs 72 and 73 hold the loader report and the ephemeral scatter-handler
disassembly. The read-only project was discarded; the source BIN and keyboard
were untouched.

## 2026-08-30 — SN_FWIN record table and Candidate B checksum status

With the loader baseline in hand, the integrity path was pursued offline against
the preserved BIN. The `SN_FWIN` header at file `0x10000` was decoded into a
four-word record table `(flash_addr, length, crc32, ram_dest)` at `0x10024`:
record A `(0x60011000, 0x58ac, 0x5e75c17a, 0x18000000)` and record B
`(0x60021000, 0x1e754, 0x1a76c116, 0x18000000)`, followed by a zero terminator.

Record A's IEEE CRC-32 over file `0x11000..0x168ac` reproduces `0x5e75c17a`
exactly, locking the flash→file mapping and the algorithm (the reflected
`0xedb88320` constant is present in `bootloader_primary.bin` at `0xc78c`).
Record B's length `0x1e754` equals Candidate A's copy region `0x1e354` plus the
`0x400` compressed decompress-source — B's full flash footprint, file
`0x21000..0x3f754`. Standard CRC-32 over that range is `0x60c95a7b`, not the
stored `0x1a76c116`; and B matched none of the tested variants, seeds, running
CRCs, accumulators, or full-file range sweeps.

The conclusion at that point was that Candidate B is not verified over the
container's stored B bytes as a plain CRC — unlike A, which verifies verbatim.
Reading the bootloader verify routine next resolved exactly why. Log 74 and
`tool/analyze_candidate_integrity.py` capture that intermediate analysis. No USB
access or firmware execution occurred.

## 2026-08-30 — Bootloader verify path read; all integrity fields resolved

A read-only decompilation of `bootloader_primary.bin` recovered the full boot
verify chain. The orchestrator `FUN_00007ec8` selects a candidate through
`FUN_00002af0 → FUN_00008000(0x60000000)`, then requires the whole-region check
`FUN_000026d0(0x6c000)` to pass before jumping to the image.

`FUN_00008000` walks the boot-priority `SN_FWIN` headers, checks magic, validates
the entry address, and calls `FUN_0000511c`, which loops the region records and
compares each stored checksum (`record+0x2c`) against `FUN_00005028`. That
routine copies the region to RAM `0x18000000` in `0x10000`-byte chunks, runs the
hardware CRC-32 engine over each chunk, and sums the per-chunk CRC-32 results by
32-bit addition. One chunk yields a plain CRC-32 (Candidate A, `0x5e75c17a`); two
chunks yield the sum (Candidate B, `0x1a76c116 = 0x35530359 + 0xe523bdbd`). A
separate routine `FUN_000026d0` word-sums each region and requires the final word
to equal the running sum, producing the terminal values `0xfb665ae3`
(bootloader) and `0x5d27c5a9` (application region).

`tool/analyze_candidate_integrity.py` now reproduces and asserts all four fields
from the preserved BIN. The SN_FWIN integrity is a recomputable chunked-CRC sum
rather than a signature, and the container guard is an additive word-sum — both
correctable offline for a modified image. This lowers the integrity barrier but
does not by itself make flashing safe: the bootloader write protocol and recovery
path remain unverified. Logs 75–76 and
`ghidra/scripts/FalchionBootloaderVerifyReport.java` capture the evidence. No USB
access or firmware execution occurred; the do-not-flash conclusion stands.

## 2026-08-30 — Offline image builder (roadmap step 1)

A five-step offline-first modification roadmap was recorded in `FINDINGS.md`, and
its first step was built: `tool/build_modified_image.py`. It applies byte patches
to a copy of the preserved BIN, recomputes the SN_FWIN per-record chunked-CRC sum
and the additive word-sum guards, and re-verifies the result. The self-check
(log 77) confirms three things: recomputing the unmodified image reproduces it
byte-for-byte (our method matches the vendor's), a naive one-byte Candidate B
patch fails both B's record checksum and the application word-sum, and the
rebuilt image passes all four fields. This demonstrates a modified image can be
made self-consistent entirely offline. The preserved BIN was not modified and no
device was touched; flashing remains gated on the unverified write protocol
(step 4) and a real recovery backup (step 5).

## 2026-08-30 — Boot container structures decoded (roadmap step 2)

The layered boot format the bootloader walks before verifying and jumping was
decoded from the preserved BIN and cross-checked against log 75: an `SNC7320A`
wrapper (primary at flash `0x60000000`, backup at `0x60060000`) holds an
`SN_BCFG` boot-config at `+0x200` whose `+0x208` boot-priority table has slot 0 →
`0x60010000` (the `SN_FWIN` header) and slot 1 empty. Both containers point at
the same `SN_FWIN` header, so the two candidates are loader + application regions
of one firmware, not an A/B image pair; the redundancy is a backup bootloader
copy. `FUN_00005240` requires the entry image's initial SP (`0x18036140`) to be
valid RAM, and the `SN_FWIN +0x18` gate (`1`) enables the record CRC checks.

`tool/analyze_boot_structures.py` decodes this and asserts the boot-gate
invariants (log 78), and `tool/build_modified_image.py` now checks the same
invariants on its rebuilt output. A Candidate-B data patch preserves every
invariant — magics, slot table, gate, and entry SP are untouched — so a rebuilt
image passes both the integrity fields and the boot gate. Read-only; no device
was touched. Remaining roadmap: Candidate B runtime entry (3), the write/erase
protocol (4), and a real recovery backup (5).

## 2026-08-30 — Candidate B runtime entry found (roadmap step 3)

Candidate B has no vector table: RAM `0x18000000` starts with a function
prologue, not an initial-SP/reset pair, so it is entered by a direct call. That
call was traced in Candidate A: the post-scatter C-runtime `FUN_000002c8`
(reached from the reset handler after `__scatterload`) calls the veneer
`thunk_EXT_FUN_1800023a`, so Candidate B's true entry is `0x1800023a`.
Decompiling it in the rebased B program confirmed the application `main`: it
prints "welcome to main", initialises clocks/GPIO/USB, creates the RTOS task
`INIT_TASK` (entry `0x1800004d`), starts the scheduler, and reaches the
vendor-HID dispatcher `0x18001fbe`.

The boot chain is now complete: bootloader verify → Candidate A reset `0x14a8` →
scatter-load B to `0x18000000` → `FUN_000002c8` → B main `0x1800023a` → RTOS →
dispatcher. Logs 79–80 and the two read-only Ghidra scripts capture the evidence;
`ghidra/README.md` was corrected. No device was touched. Remaining roadmap: the
write/erase protocol (4) and a real recovery backup (5).

## 2026-08-30 — Bootloader write protocol reversed, read-only (roadmap step 4)

The PID-`1b7f` "Gaming Keyboard Bootloader2" write path was decompiled from
`bootloader_primary.bin`. Its service loop `FUN_00003a7c` dispatches received
OUT reports through `FUN_00002db8`, which switches on a command byte at report
offset `0x34`: `0x01` erases (flash-controller command `0xa`), `0x05` reads, and
`0x51` programs. Both erase and program require `0x10000 <= addr < 0x7c000`, so
the primary bootloader region cannot be overwritten through these commands.
Flash access is via a hardware flash/DMA controller (`FUN_00002f0c` descriptor,
direction byte 0=write/1=read), not raw SPI opcodes. The host side matches the
preserved updater strings in log 34 (`Jump to Bootloader`, `Start Erase...`,
`Programming Success! (no check checksum)`, `Read checksum...`) over HID reports.

There is no signature check in the path — consistent with the recomputable
checksum integrity. Log 81 and `ghidra/scripts/FalchionBootloaderProtocol.java`
capture the evidence. This documents the protocol on paper only; no erase,
program, or jump command was sent, and none should be until a verified recovery
backup exists (step 5). No device was touched.

## 2026-08-30 — Step 5 recovery-backup plan written (no device interaction)

The recovery prerequisite was written up as `notes/step5-recovery-plan.md`. It is
a plan only; nothing was executed and the keyboard was not touched. Step 5 differs
from steps 1–4 in that it is the first action that reads *from the device*: it
produces a verified byte-exact backup of the *installed* v1.59 image, which the
project does not currently have (the on-disk `M605_V01_00_58.bin` is the older
v1.00.58 reference, not a readback of this unit). The plan documents two
approaches — a USB read-back via the bootloader `0x05` READ command, or a
hardware 3.3 V SPI read of external flash U5 — with the same acceptance criteria
(≥3 identical dumps, validate with `analyze_boot_structures.py` and
`analyze_candidate_integrity.py`, redundant storage) and hard read-only rules.
Nothing is to be flashed until this backup exists and verifies.

## 2026-08-30 — USB wire framing decoded for the read-back path (offline)

To make Approach A reviewable before any device contact, the exact vendor-HID
wire framing was decoded read-only (log 82). Transport is usage page `0xFF01`,
64-byte reports with no report ID; the router `FUN_0000bd40` treats `report[0]`
as a sub-command (top bit = query vs action) and `report[1..]` as payload. OUT
sub-commands: `0x10` unlock (`ASUSHIDFWU`), `0x20` set address (4 B LE), `0x21`
set length (u16), `0x22` load data, `0x1f` execute (`0x01` erase / `0x05` read /
`0x51` program), `0x11` reset. Queries `0x8e`/`0x8f`/`0xaa` return CRC result /
status / read data.

This corrected an earlier note: the READ path **is** address-guarded — the
execute-trigger requires `0x10000 <= addr <= 0x7bfff` and length `<= 0x30`, so a
USB read covers only the application region, not the bootloader (which is also
unwritable, so it never needs restoring). Force-bootloader entry was confirmed:
the bootloader `FUN_00002a44` checks RAM `0x20000ffc` against magic `0x73207320`,
which the application writes (Candidate B, near the `"boot"` string) before an
AIRCR reset — the updater's "Jump to Bootloader". `notes/step5-recovery-plan.md`
Approach A now carries the exact read-only dump recipe. Still entirely offline;
no report was sent to the device.

## 2026-08-30 — Read-only backup tool built; host access confirmed

Two preparatory items for step 5 were completed without sending anything to the
device. (1) Host access was checked read-only: the keyboard is present as
`0b05:1b7e` (application mode) and `/dev/hidraw1-4` are world read/write, so the
device is reachable without elevated privilege; `hidapi`/`pyusb` are absent, so
raw hidraw is used. (2) `tool/backup_firmware.py` was written — a strictly
read-only backup tool whose only constructable reports are read/query/
set-address/set-length; erase (`0x01`), program (`0x51`), unlock (`ASUSHIDFWU`),
load-data (`0x22`), and reset (`0x11`) have no code path. Its default dry-run
(log 83) validated all 46080 dump-plan reports against the guard and self-checked
that forbidden reports raise; `--run` opens a device only when it is already in
bootloader mode (`1b7f`) and refuses the application (`1b7e`) — verified by a
run against the current app-mode device, which correctly refused and wrote
nothing. The device remains in application mode; no firmware read has been
performed and no report was sent.

## Corrections retained for auditability

The investigation deliberately records mistakes and superseded interpretations:

| Item | Correction |
|---|---|
| Sandboxed `lsusb` failure | Not a device result; direct read-only retry succeeded |
| Sandboxed `dfu-util` failure | Not a DFU result; direct enumeration succeeded with no target |
| Port comparison in log 25 | Parser included `xxd` ASCII; log 26 proved equality |
| Old interface-4 `0xFF32` claim | Provenance unsupported; current interface 4 is page `0x59` |
| “No USB bootloader” | Narrowed to no DFU/bootloader interface in normal mode |
| `CandidateB_Entry` label | Corrected to evidence-bounded `CandidateB_Start_Function`; runtime base later resolved separately |
| Raw `51 21` byte hit | Identified as an instruction constant, not a command table |
| First binary-pointer search | Shell escaping was malformed; log 50 was regenerated byte-safely |
| Generic STM32 recipes | Removed; not valid evidence for SNC73270 |
| Eight `0x86` rows at `0x1801c37c` | Corrected to three overlapping 189-byte logical wire windows plus a separate three-row `0x100` scan map |

## Files and review order

For a future review, read in this order:

1. [`TIMELINE.md`](TIMELINE.md) — chronological narrative and corrections.
2. [`FINDINGS.md`](FINDINGS.md) — authoritative present conclusions.
3. [`vendor/asus/ARTIFACTS.md`](vendor/asus/ARTIFACTS.md) — preserved vendor
   artifacts and hashes.
4. [`ghidra/README.md`](ghidra/README.md) — current Ghidra memory map and labels.
5. [`notes/protocol.md`](notes/protocol.md) — detailed protocol history and
   static corroboration.
6. [`notes/key-matrix.md`](notes/key-matrix.md) — physical/wire/profile key maps.
7. [`logs/COMMANDS.md`](logs/COMMANDS.md) — exact command-to-log manifest.
8. [`logs/SHA256SUMS`](logs/SHA256SUMS) — raw text-log integrity.

The large official ZIP is local-only unless deliberately archived with Git LFS
or another storage system. The 1.00.58 BIN, analyzer, documentation, scripts,
and text evidence are normal repository artifacts.

## Work not performed

For clarity, this investigation has not:

- backed up the installed 1.59 firmware;
- read U5 or verified its JEDEC ID electrically;
- connected SWD, SPI, Bus Pirate, or another hardware probe;
- entered PID `1b7f` bootloader mode;
- executed the ASUS updater;
- used `fwupd` to update or modify the keyboard;
- sent vendor-HID configuration or firmware commands during preservation;
- erased, programmed, reset, or detached any device;
- proven that the official 1.00.58 image is a safe downgrade or recovery path;
- sent any erase, program, or jump-to-bootloader command, or flashed anything
  (the write protocol is now understood on paper — logs 75–76, 79–81 — but no
  command has been issued to the device);
- built or flashed custom firmware.

## Recommended continuation

The integrity calculation is now solved (logs 75–76): SN_FWIN per-record values
are a sum of per-`0x10000`-chunk IEEE CRC-32, and the container guard is an
additive word-sum, both recomputable offline. The safest high-value continuation
is now Candidate B's true runtime entry/dispatch after scatter-load (it still has
no verified vector), and — before any flashing — a read-only study of the
bootloader's write/erase/program protocol and recovery path. Controlled firmware
modification remains blocked on those, not on integrity.

Before any hardware modification, prepare a separate reviewed preservation
plan for U5 and MCU readback: correct voltage, board-power isolation, bus
contention prevention, exact pin mapping, read-only commands, multiple identical
dumps, and independent hashes. Never proceed from an official updater image
alone as if it were the installed-device backup.
