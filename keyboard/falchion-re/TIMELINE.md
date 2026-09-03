# ASUS ROG Falchion Ace HFX reverse-engineering timeline

Last updated: 2026-09-03 (America/Mexico_City)

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

The initial preservation boundary was strict: no device write or state change.
Every later device action was individually owner-authorized: the first
reset-only bootloader entry (log 88), the first status request (log 89), the
successful status/zero-buffer probe (log 90), and a second reset-only entry plus
one 48-byte flash READ (log 91), followed by the fresh entry and three-pass
application-region READ backup in log 92. No firmware update, DFU operation, driver
detach, erase, program, unlock, persistent configuration write, or SPI
transaction was performed. No SPI Write Enable (`0x06`) was sent. Offline
analysis scripts never communicated with the keyboard.

Earlier protocol experiments did send configuration-changing HID reports. They
are retained as historical evidence and were not repeated during preservation.

## Current status at a glance

- Normal USB identity: ASUS `0b05:1b7e`, device release `1.59`.
- Five normal-mode HID interfaces; no DFU-class interface.
- Both physical keyboard connectors expose the same normal-mode USB layout.
- Standard USB firmware backup is not exposed. A proprietary bootloader-mode
  READ path is supported by static analysis. Bootloader entry and split-channel
  framing are live-validated. Three complete application-region passes were
  byte-identical and structurally valid (log 92).
- Official ASUS firmware 1.00.58 is preserved and hashed, but it is not a dump
  of the installed 1.59 firmware.
- The vendor updater is a proprietary HID erase/program tool using normal PID
  `1b7e` and bootloader PID `1b7f`; it was never executed.
- Candidate B contains the vendor-HID dispatcher and device-side unsupported-key
  policy logic.
- A verified installed application-region readback now exists. No complete U5,
  bootloader, or internal-MCU readback has been obtained.

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
that forbidden reports raise. The device remains in application mode; no firmware
read has been performed and no report was sent.

> **Correction (2026-08-31, log 84).** This entry originally claimed the `--run`
> refusal was "verified by a run against the current app-mode device, which
> correctly refused and wrote nothing." That is unsupported: log 83 contains
> dry-run output only and does not support that claim. During the later
> correction audit, log 84 exercised only the new flag-gated refusal path; it
> returned before device selection. The live path was never entered. The old
> claim has been removed above; the raw log is unchanged.

## 2026-08-31 — Correction pass over the backup tool and documentation (log 84)

A review of the previous four commits found overstated conclusions and one
functional defect. Nothing in this pass touched the device.

**Backup tool.** `tool/backup_firmware.py` had a fatal sequencing bug: it sent
all five reports of a chunk and then performed a single `read()`, so the `0x8f`
status reply was consumed as if it were the `0xaa` read data, and every chunk was
silently wrong. It also validated no response at all. It now performs immediate
request-response exchanges — send `0x8f`, read its reply, validate
`resp[0] == 0x0f` and that `resp[2]` (`state+0x35` error) is zero, poll
`resp[1]` bit 1 (`state+0x38`, the proven READ-busy bit, log 81 `FUN_00002db8`)
within bounded attempts, then send `0xaa`, read its reply, require
`resp[0] == 0x2a`, and only then take `resp[1:1+length]`. Any timeout, short
report, wrong code, status error, or busy-timeout aborts the dump, and no image
is written after a failure.

Device selection no longer takes the first PID-matching node: it requires
exactly one `1b7f` hidraw whose report descriptor declares usage page `0xFF01`,
64-byte IN and OUT reports, and no report ID, and refuses on zero, several, or a
descriptor mismatch. Output is labelled as the app region (base `0x10000`, size
`0x6c000`) and requires three passes agreeing on both raw bytes and SHA-256.

A second review pass added three more corrections. **A post-EXEC scheduling race
was identified and documented rather than papered over:** the `0x1f` parser only
sets the pending byte `state+0x34`, and the service loop is what sets busy bit 1
and performs the READ, so a status query that arrives before the service loop
runs would see bit 1 clear and could return the previous chunk's buffer. Status
does not expose `state+0x34`, so the host cannot close this window. No timing
guarantee is claimed. **As a mitigation, every completed dump is now re-parsed in
memory before anything is written** — exact size `0x6c000`, SN_FWIN record
checksums, application word-sum, and container/entry constraints must all
reproduce at base `0x10000`, with the primary-bootloader checks reported as
explicitly skipped. Any failure rejects all passes. Finally, the output is
published through an exclusive temp file, `fsync`, and `os.link`, so an existing
backup is never overwritten and a failed write leaves no partial file; transport
open and write errors are reported without tracebacks, and a failing
`transport.close()` can no longer mask the protocol error that preceded it.

`--run` remains gated behind `--force-unreviewed`: the scheduling race, the
assumed hidraw transfer convention, and the absence of any hardware validation
are all unresolved. *(The scheduling race was resolved afterwards — see
"Bootloader READ scheduling resolved" below.)*

**Analyzers and builder.** Both analyzers now take an explicit `argv`, support a
full image at base 0 and the app-only dump at base `0x10000`, and state which
checks were skipped rather than silently dropping them. The builder is
version-locked to the preserved 1.00.58 SHA-256
(`6d410ee0…e19f1d`), restricts patches to non-empty non-overlapping ranges inside
Candidate B, refuses to overwrite an output, and re-validates the scatter stream
after patching. The scatter emulator for `0x3f354..0x3f754` now asserts its
observed shape (output `0xb04`, consumed `0x3fe`, two zero padding bytes) and
maps literals to runtime addresses; the demo offset `0x3f66f` resolves to
decompressed index `0x882`, runtime `0x1801ebd6`.

**Claims withdrawn.** "Boots if and only if", "will boot", "complete
authentication", "no signature anywhere", "sufficient recovery", and
"unconstructable" were removed or narrowed to what the evidence supports. The
duplicate bootloader checksum offset was corrected to `0x0fffc` and `0x70ffc`
(`0x61000` is the start of the duplicated region, not a checksum offset). The
unsupported claim of a live `--run` refusal was withdrawn. `FUN_000029d4` and the
top-level selected-entry comparison are recorded as unresolved.

85 offline tests were added (`tool/test_backup_firmware.py` 51,
`tool/test_build_modified_image.py` 34), all mocked or file-based; none touches a
device. Logs 77 and 83 keep their raw text; their conclusions are marked
superseded in `logs/COMMANDS.md`.

## Bootloader READ scheduling resolved (log 85)

The last open question in the read-back protocol is closed: **the post-EXEC
scheduling race is real — proven possible.** Everything below is
instruction-level from the preserved bootloader image; no device was touched.
*(This section originally also claimed the race was "the default outcome" and
described the busy window in microseconds. Both were withdrawn in log 86; see
"Correction: the first fix was wrong too" below.)*

First, the RAM layout was resolved by literal-pool *value* rather than by offset,
which turned three loosely-described "state bytes" into three concrete objects:
the flash-transaction block at `0x18011a8c`, the protocol state block at
`0x18012a8c` (exactly `0x1000` above it), and the service-loop flag pair at
`0x18010bd4`. That immediately explained two things the earlier logs had only
described: the `0x30` READ length cap is the response buffer's size
(`state+4 + 0x30 == state+0x34`, so a longer READ would overwrite the pending
byte), and the host has no write path into the response buffer at all.

Then the scheduling. The `0x1f` EXEC parser runs in USB-interrupt context and
does two things: it sets the pending byte `state+0x34` and it sets the
flash-operation request flag at `0x18010bd8`. It never touches the *other* flag
at `0x18010bd4`. But `FUN_00003a7c` — the whole of `main()`'s loop — tests that
other flag as its loop condition, before executing any of its body, and the only
code in the image that writes it is the four-instruction SysTick handler at
`0x000048d0`. So an accepted READ does not start when the EXEC is parsed; it
starts on the next SysTick tick. `SYST_RVR` is a static `161999`, i.e. 162000
core clocks, while the READ itself is one 48-byte flash transfer. Neither the tick period in wall-clock terms nor the
duration of one flash transfer is recoverable from this image, so no claim is
made about how often the race is hit — only that it is possible.

The consequence is that **polling `state+0x38` bit 1 cannot sequence a READ.**
The host reads "clear" and takes it to mean "finished" when it actually means
"not started". This was exactly what `tool/backup_firmware.py` did. The earlier
characterisation — "unresolved, mitigated by end-of-dump validation" — was too
generous: the busy poll cannot sequence a READ under *any* timing, so the tool
was wrong, not merely unproven. How often it would have returned stale bytes is
not determined, and log 86 withdraws the claim that it always would have.

A search for an observable completion marker came back negative: no generation
counter, no address echo, no completion byte, no sequence number, and
`state+0x34` is exposed by no query. Two ways to expose it were examined and
rejected. Over-reading `state+0x34` through `0xaa` requires raising the length
above `0x30` while a READ may still be pending; every such value either
misaligns the flash engine (which the transfer engine rejects while the caller
spins on it anyway) or corrupts the length field into the responder's unclamped
`memcpy` size. A locked `1f 01`/`1f 51` probe genuinely would work — with the
unlock bit clear those handlers write exactly one byte and reach no flash code —
but adopting it would mean the backup tool could construct an execute-ERASE
report, and that is the one property the tool exists to guarantee.

What does close it needs no new opcode and no timing assumption. The response
buffer is written only by the READ handler, which takes its address from the
shared struct *at dispatch time*. So once the host has set an address and not
changed it, every subsequent write to that buffer is the content of that address.
Observe the buffer *before* setting the address to get a baseline; any later
value that differs from the baseline is provably the requested content. The one
gap — content that happens to equal the baseline, common in padding runs — is
closed by re-basing through an anchor chunk of already-proven, different content,
and the tool aborts rather than accept unproven bytes if no anchor exists yet.

`tool/backup_firmware.py` was changed accordingly: `wait_read_done()` is gone,
replaced by `check_status()` / `fetch()` / `read_fresh()` and a re-basing
`read_chunk()`. The status **error** byte is still trusted, and now for a stated
reason: it is written by the same interrupt-context parser that consumed the EXEC
report. The busy bit keeps one legitimate use — the READ handler does not mask
interrupts, unlike erase and program, so the responder can observe a half-written
buffer, and the handshake skips the fetch while bit 1 is set. The tool also now
refuses to continue against a bootloader that reports itself unlocked or
mid-erase. The mocked test suite grew from 85 to 95 tests; `FakeBootloader` was
rewritten to model the real scheduling — a persistent buffer, EXEC dropped while
pending, and a tick that fires after a configurable number of query
opportunities — so the stale-buffer failure is now reproducible in the tests
rather than assumed away.

What remains unresolved is unchanged and still gates `--run`: the Linux hidraw
report-number and framing conventions are assumed rather than observed, no live
validation of any kind has been performed, and no installed-firmware backup
exists. Nothing here says the protocol works on hardware; it says the host-side
logic is no longer known to be wrong.

## Correction: the first fix was wrong too (log 86)

An independent review took the log-85 handshake apart, and it was right to. The
replacement was unsound for a reason log 85 had itself written down two
paragraphs earlier and then failed to apply: `FUN_00003b64` does not mask
interrupts, so the `0xaa` responder can run while the response buffer is only
half written. The handshake read the status *before* the data query — which
excludes nothing, because a whole READ can start and finish between two host
reports with the fetch landing inside it. The reviewer reproduced it in memory:
the implementation accepted 24 new bytes followed by 24 baseline bytes and called
them a chunk. The test suite could not have caught it, because the fake device
replaced its buffer atomically and its "busy" knob only toggled a status flag
without being connected to any incremental write. A model that cannot express the
failure cannot test for it.

The fix is an ordering one, and it is small: sample first, *then* read the status,
and if that status says not-busy and the sample differs from the baseline, return
a **second** fetch rather than the sample. The proof is short enough to state
here. Every write to the buffer happens while bit 1 is set, because
`FUN_00003b64` is called strictly between the stores at `0x00002e0a` and
`0x00002e1e`. The read handler takes its address at dispatch time, so from the
set-address report onward every episode writes the requested content, while any
episode that dispatched earlier merely re-writes the previous chunk's content —
which is the baseline itself, so it changes nothing. A status with bit 1 clear
therefore lies outside every transfer interval. If the sample that preceded it
differed from the baseline, that status cannot lie before the first
post-set-address episode; so it lies after it, and the buffer holds the complete
value from that instant on. The next fetch is safe. No timing assumption enters
anywhere.

The bootstrap needed separate evidence, and it turned out to exist. The reset
vector does not go straight to `__rt_entry`: it goes through `__scatterload` at
`0x00000148`, which walks a `Region$$Table` at `0x0000cca0`. The third of its
three entries zero-initialises `0x18011168..0x1802b230` with
`__scatterload_zeroinit`, and that range covers the pending byte, the length, the
flags and the response buffer. So a freshly started bootloader has no pending
operation and an all-zero buffer — the first baseline is *known*, not observed
and hoped about. The tool now refuses to start unless the buffer reads as those
48 zero bytes, which is a real check: it fails exactly when a READ has already
run in this bootloader session and the first baseline could not be trusted.

One residual is genuinely not closable from the host side, and it is now written
down rather than glossed. A foreign READ queued by another process but not yet
dispatched is invisible — the pending byte is exposed by no query and the buffer
still reads zero. If it lands between this tool's bootstrap fetch and its first
set-address report, it publishes an unrelated address's bytes and the handshake
accepts them, because from the outside that is indistinguishable from our own
read completing. The only thing that closes it is an operational precondition the
protocol cannot enforce: nothing else may talk to the node during the dump. There
is a test that asserts the hole rather than hiding it, so anyone who later
believes they have fixed it will hear about it.

Log 85's timing language went too far and has been withdrawn: "the default
outcome", "orders of magnitude", "microseconds", "almost always". Log 85 itself
records that the core clock is selected at runtime and that the flash-transfer
duration is unrecovered, so none of those followed from anything. The defensible
result is "proven possible", and — usefully — nothing in the corrected design
depends on the timing either way. Log 85 is preserved unedited; log 86 supersedes
the specific claims.

Re-arming the execute report also changed, for liveness rather than soundness. It
can lock in step with the dispatch cadence, starting a new transfer at every
sample so that the status never catches a quiet moment; it now stops as soon as a
sample differs from the baseline, at which point an episode is already under way
and no further execute is needed. The old behaviour produced refusals, never
wrong acceptances.

The mocked suite went from 95 to 108 tests. `FakeBootloader` now writes the
buffer incrementally, holds bit 1 for exactly the transfer, lets the main loop
run between any two reports rather than only around queries, starts from a
zero-initialised buffer, and can be given a foreign pending operation. `--run`
remains gated behind `--force-unreviewed`, which was not used.

## 2026-09-02 — Exact bootloader-entry report recovered offline (log 87)

The previously unresolved application-to-bootloader transition was traced from
both sides. Candidate B `FUN_180160d8`, installed through the low-level USB
endpoint callback table by `FUN_18016908`, recognizes the seven-byte prefix
`7b aa 41 53 55 53 aa`. On a match it writes `0x73207320` to RAM
`0x20000ffc`, delays, and resets. This is different from the application
dispatcher's `0xb0` + `"reset"` branch, which performs an ordinary AIRCR reset
without the force-boot flag.

The official .NET front end was statically decoded and found to be only a
wrapper. Its `UpdateFW` method launches `FW/peripheral_fwu_pro.exe` with the
official `m 1B7E 1B7F 64 432 FF00 FF00 4` arguments. Native Ghidra analysis of
that child recovered the "Jump to Bootloader" block at
`0x00407231..0x0040735c`: it zero-fills a 64-byte vector, calls packet-builder
selector 4, sends once, and waits for PID `1b7f`. Selector 4 writes exactly the
same seven-byte prefix. The remaining 57 bytes stay zero.

The DLL's `InterruptTransfer_WriteLen` independently resolved host framing: it
prepends the separate report-number argument to the payload. Since the current
interface-1 FF00 report descriptor has no Report ID, the Linux hidraw write is
65 bytes: `00` plus the 64-byte payload. Its SHA-256 is
`de6cfe16cc4639b2593bdfe86dade88e4e282a9ad6552b5684fbd35ef50506d8`.

`tool/enter_bootloader.py` was added with a one-frame equality guard, exact
VID:PID/descriptor selection, default dry-run, two required live flags and no
retry or generic command path. The full mocked suite now has 115 passing tests.
A passive preflight found the normal keyboard at `0b05:1b7e`, selected only
`/dev/hidraw7`, verified mode `0666`, and found no process holding that node.
No device node was opened and no report was sent during that preflight; the live
reset still required explicit informed approval.

## 2026-09-02 — Live bootloader entry succeeds (log 88)

The owner explicitly authorized the one reset-only report. The reviewed tool
revalidated `/dev/hidraw7`, emitted the exact 65-byte hidraw frame once with no
retry, and closed it. The keyboard immediately re-enumerated from application
PID `0b05:1b7e` to `Gaming Keyboard Bootloader` PID `0b05:1b7f`, bcdDevice
`1.05`. This validates the application-side entry command and host framing.

Passive enumeration found four HID interfaces. The firmware channel is
interface 0 / `/dev/hidraw6`, usage page `0xFF01`, with unnumbered 64-byte IN
and OUT reports on endpoints `0x81` and `0x06`. Interface 1 is a separate FF00
64-byte channel; interfaces 2 and 3 are mouse and keyboard. All use `usbhid`.
`dfu-util -l` found no DFU target. fwupd is not installed (`fwupdmgr` and
`fwupdtool` absent; pacman reports no `fwupd` package).

The bootloader nodes reappeared root-only (`0600`), and `/dev/hidraw6` had no
reported holder. No permission was changed. No bootloader report—including a
status query or READ—was sent, and no flash operation occurred. The next phase
requires separate approval for privileged, read/query-only access.

## 2026-09-02 — First status probe exposes split HID routing (log 89)

After the owner granted user `dereck` read/write access to FF01
`/dev/hidraw6`, the separately authorized minimal probe selected that interface
and wrote exactly its first allowlisted report: `0x8f` status. It then timed out
waiting for a reply on the same node. Its exact-sequence guard stopped the run,
so it sent no `0x21` set-length, no `0xaa` buffer query, no address, no
execute-READ, and no flash operation.

Read-only Ghidra analysis resolved the timeout. `FUN_000076ac` passes physical
OUT channel 0 (EP6, FF01 interface 0) to router `FUN_0000bd40`. Response sender
`FUN_00004f7c` transmits on physical IN channel 1 (EP5, FF00 interface 1).
Therefore commands must be written to FF01 while replies must be read from the
distinct FF00 node. Log 82 had inferred a single FF01 transport from descriptor
presence; that conclusion is superseded.

`tool/probe_bootloader.py` and `tool/backup_firmware.py` now share a split
transport that opens FF00 read-only first and FF01 write-only second. The full
offline suite passes 130 tests, including distinct-file-descriptor framing and
selection. The corrected live probe has not run. A sandboxed `ls` initially
reported the paths absent; direct passive enumeration then proved the keyboard
remained at `0b05:1b7f` and the selectors still resolved `/dev/hidraw6` and
`/dev/hidraw7`. That absence was a sandbox artifact, not re-enumeration. FF01
retained the owner's ACL; FF00 remained root-only, and neither had a reported
holder.

## 2026-09-02 — Corrected split-channel probe passes (log 90)

The owner granted `dereck` read-only access to FF00 `/dev/hidraw7` and explicitly
authorized the exact four-report retry. The tool revalidated both descriptors,
opened FF00 read-only before FF01 write-only, and completed its byte-for-byte
allowlisted sequence. The initial and final `0x8f` queries returned 64-byte
`0x0f` replies with flags 0 and error 0. After the RAM-only length setter,
`0xaa` returned `0x2a` plus exactly 48 zero bytes, matching the bootloader's
statically proven reset initialization.

This validates Linux bootloader report framing, FF01/EP6 command routing,
FF00/EP5 response routing, response codes, and the zero-buffer bootstrap. It did
not set an address or send execute-READ, so it does not validate flash readback,
the freshness handshake, the full backup tool, or any installed-firmware byte.
No unlock, erase, program, reset, update, or SPI command occurred.

## 2026-09-02 — One installed-flash block read successfully (log 91)

The owner authorized one 48-byte read at `0x10000`. A dedicated tool and six
tests were added first; the full suite increased to 136 passing tests. Its guard
fixes the address and length, permits exactly one `0x1f/0x05` execute-READ, and
cannot construct another address, a second execute, unlock, erase, program, or
reset. Unlike the eventual backup tool, it does not re-arm EXEC.

The first preflight found that the bootloader had automatically returned to
application mode, so it stopped before opening a protocol node. After separate
approval, the exact reset-only entry report was sent once more. Re-enumeration
removed the temporary ACLs; the owner restored write-only access to FF01 and
read-only access to FF00. Descriptor and holder checks passed.

The live probe then sent exactly one 48-byte flash READ at `0x10000`. The
sample/status/confirm handshake returned a complete fresh block beginning
`SN_FWIN\0`; its SHA-256 is
`5ed6cf849410a373aa7f64c2c3ac8e3e6b710d1c52da3c4124e1510f51ad5815`.
The first 44 bytes match the preserved 1.00.58 image, while the last u32 record
checksum differs (`85 24 55 7d` installed, `7a c1 75 5e` preserved), evidence
that their record payloads differ. No other flash address or write-capable
operation was used. Multi-chunk sequencing and a full backup remain untested.

## 2026-09-02 — Three-pass application-region backup completed (log 92)

The owner physically power-cycled the keyboard, separately authorized one exact
reset-only bootloader-entry report, and restored narrow temporary ACLs after
re-enumeration: write-only for the FF01 command node and read-only for the FF00
response node. Descriptor selection and holder checks passed before the dump.

The authorized backup read `[0x10000,0x7c000)` three times through the
read-only bootloader path. All three 442,368-byte passes produced the identical
SHA-256
`fc6128ab089e4fd712b172c54cd88b7f28476b55bdac688134e052281ded637b`.
The tool then accepted and atomically published
`dumps/device/ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin`.

Independent offline validation confirmed both SN_FWIN record checksums, the
application word-sum, and all 12 boot-structure checks applicable to an image
whose base is `0x10000`. No unlock, erase, program, update, persistent
configuration, driver detach, or SPI operation occurred.

This completes the USB application-region preservation objective, but it is not
a complete physical-flash dump. The protocol cannot read the bootloader
`[0,0x10000)` or the remainder of the 4 MiB U5 address space.

## 2026-09-02 — Step 6 offline custom-firmware plan written (log 93)

`notes/step6-offline-custom-firmware-plan.md` defines a nine-phase, offline-only
path from installed-versus-vendor comparison through a version-aware parser,
installed-code mapping, boot-gate recovery, hardware-interface mapping, strategy
selection, a fail-closed image builder, and an explicitly untested experimental
artifact. Each Claude Code invocation is limited to one phase and must stop for
independent Codex review. The plan includes a ready-to-paste Phase 1 prompt,
deliverables, exit gates, evidence-handling rules, and a strict prohibition on
device, USB, updater, reset, unlock, erase, program, update, and SPI access.

This was documentation work only. No binary was generated or modified, and no
device was accessed.

## 2026-09-03 — Plan review and Step 6 Phase 1: shared image-format library (log 94)

The plan was reviewed against the evidence before execution. The review confirmed
both immutable hashes, the `[0x10000,0x7c000)` range arithmetic, the log
numbering, and that `sha256sum -c logs/SHA256SUMS` passes. It produced four
corrections, all applied to `notes/step6-offline-custom-firmware-plan.md`: the
parser phase now runs before the comparator so SN_FWIN parsing is not written
twice; the exact complete-suite invocation
`python3 -m unittest discover -s "$PWD/tool" -t "$PWD/tool"` is pinned, because
running it from inside `tool/` discovers only 130 tests and then fails to import
`test_enter_bootloader.py`; Phase 7 now names the three additive word-sum guards
(`0x7bffc`, `0x70ffc`, and the unavailable `0x0fffc`) instead of saying
"dependent integrity fields"; and the Phase 1 prompt no longer tells Claude Code
to use `apply_patch`, which it does not have. The review also found the plan's
Phase 4 too pessimistic about the bootloader, which log 94 then settled.

Phase 1 added `tool/falchion_image.py` and `tool/test_falchion_image.py` (38
tests). The library separates parsing, validation and mutation-source policy,
expresses every offset as a logical flash offset with a single translation point,
reads record lengths from the image being parsed, and returns a deterministic
machine-readable result so later phases never parse stdout. No existing analyzer
was refactored: the plan permits that only where regression tests preserve known
output, `analyze_sonix_firmware.py` and `analyze_candidate_b_tables.py` have no
tests at all, and the two covered analyzers are the reference implementations
logs 74–92 were produced with. Four parity tests prove agreement instead, leaving
a refactor as a separate reviewed change.

Three facts came out of it. The installed record[1] length is `0x1e780` against
vendor `0x1e754`, so the application record grew by 44 bytes while record[0] and
both load addresses stayed the same. The installed dump's logical
`[0x61000,0x71000)` is byte-identical to the vendor 1.00.58 backup range and to
its primary bootloader region `[0,0x10000)` — all three hash to
`4a4568b6…686a` — and that mirrored copy validates its own word-sum `0xfb665ae3`
at `0x70ffc`, so the bootloader already under static analysis is proven to exist
on the device. The unread installed primary region, which container the device
actually booted, and ROM/first-stage behavior all remain unresolved. `SN_FWIN
+0x8` is `v1.0.00` in both images, confirming it is the container format version
rather than the ASUS release version.

174 offline tests pass under the pinned invocation, both evidence hashes are
unchanged, both accepted analyzers still produce their published results, the
installed-dump results still match log 92, and malformed inputs fail closed with
one line and no partial report. No device was accessed. Phase 2 was not started
and the work was left uncommitted for Codex review.

**Independent review rejected the first cut of Phase 1 (log 95).** The record
parser had invented a terminator: it stopped at the first slot with a zero
address or zero length, while `FUN_0000511c` in log 75 loops `uVar1 < 8` and
processes every slot whose length field is nonzero. The reviewer built an
in-memory image with an active slot 3 behind the empty slot 2, corrected the
application word-sum, and the library returned `known_checks_ok=True` while
omitting slot 3 — a checksum dependency the Phase-2 comparator and the Phase-7
builder would both have missed. `parse_records` now scans all eight slots, skips
only zero-length holes, keeps physical slot indices, bounds-checks every active
slot, and fails closed on a zero address with a nonzero length, a truncated
table, or no active slot. The plan's Phase 1 wording and test list were corrected
to the proven eight-slot behavior and Phase 2's log moved to 96.

The earlier "zero terminator" reading of the record table (log 74) is corrected
rather than quietly replaced: slot 2 carries a stale nonzero address with a zero
length, so it is an inactive hole. Slots 3 to 7 are all-zero in both preserved
images, which is why the old rule produced the right two records for the wrong
reason, and why no published result moves. `analyze_candidate_integrity.py`,
`analyze_boot_structures.py` and `build_modified_image.py` still carry the
assumption; a test pins the divergence and reconciling them is now a Phase 7
prerequisite. The review also found the log-94 row in `logs/COMMANDS.md` stating
37 new / 173 total tests where the raw log correctly said 38 / 174; the row is
fixed and log 94 is unedited. 179 offline tests pass, both evidence hashes are
unchanged, and no device was accessed.

## 2026-09-03 — Step 6 Phase 2: installed 1.59 compared with vendor 1.00.58 (log 96)

`tool/compare_firmware_images.py` and 41 tests. The comparator is built on the
Phase-1 parser, so there is no second SN_FWIN parser and no second copy of the
offset or checksum rules. It reads both images over the same logical range,
`[0x10000,0x7c000)`, through the single translation point, refuses inputs whose
SHA-256/base/size tuple is not allowlisted unless `--analysis-only` is passed
with a warning, and renders one model as a Markdown note and a complete
deterministic JSON result. The 25 longest differing ranges are tabled in the
note, which says so; all 3,509 are in the JSON along with all 108 page hashes.

The two releases differ in 101,297 of 442,368 bytes, 22.90%, across 3,509
contiguous ranges and 39 of 108 pages, first at `0x1002c` and last ending at
`0x7c000`. The useful result is how contained that is: every change falls in
`[0x10000,0x17000)`, `[0x21000,0x40000)` or `[0x7b000,0x7c000)`. The container
and bootloader-copy area `[0x60000,0x71000)`, both fill regions, and the RAM
image `[0x74000,0x79000)` are byte-identical between releases. Record slot 0
keeps length `0x58ac` and differs in 131 bytes over 106 ranges; slot 1 grows
`0x1e754` to `0x1e780` and differs in 101,112 bytes over 3,399 ranges; neither
moved. All 603 ASCII strings appear in both images with nothing added, removed or
rewritten. The three-way bootloader-copy identity from log 94 reproduced through
an independent code path.

No meaning is assigned to any changed range, and the report repeats the three
open unresolved items so a reader cannot mistake a clean comparison for boot
evidence. The comparator refuses rather than guesses on a slot active in only one
image or a record whose address moved. 220 offline tests pass under the pinned
invocation, the Markdown note, the JSON and the raw log agree on every count, two
`--json` runs hash identically, both evidence hashes are unchanged, and no device
was accessed. Phase 3 was not started and the work was left uncommitted.

Phase 1 had been corrected under independent review (log 95) but not formally
re-accepted when this phase was executed at the owner's direction.

**Independent review withheld Phase 2 over five findings, all now fixed (log
97).** Record destinations were parsed by the Phase-1 model but never reported,
so a synthetic `dst` change to `0x18001000` was invisible in both Markdown and
JSON — a runtime-load-address change could have passed unreported. Provenance
was verified *after* `compare()` had already parsed, hashed and diffed, contrary
to the plan's "verify both tuples before analysis". `--analysis-only --json`
printed its warning to stdout ahead of the document and so emitted unparseable
JSON. The string comparison compared sets rather than multisets, so a value
appearing a different number of times would have shown nothing, and the result
was described as "603 ASCII runs" when the images hold 802 occurrences of 603
distinct values. Slot 1's extra 44 bytes were disclosed only as a scalar length
delta.

The comparator now reports both images' complete record fields with explicit
`addr_changed`, `dst_changed` and `checksum_changed` flags; gates on the
allowlist before any parsing, hashing or diffing, pinned by a test that trips if
`compare()` is entered for a default unknown source; sends the analysis-only
warning to stderr and records the waiver structurally under a `provenance` key;
compares string multisets and reports distinct values and occurrences separately
with a `count_changed` list; and represents a one-sided record tail as its own
span, `0x3f754..0x3f780` for slot 1. Every measurement in log 96 survives
unchanged — the fixes add fields and tighten ordering rather than moving any
number. 232 offline tests pass, the regenerated note and JSON agree with the log
on every count, both evidence hashes are unchanged, and no device was accessed.

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
| SN_FWIN record-table “zero terminator” | `FUN_0000511c` scans a fixed eight slots and gates only on a nonzero length; slot 2 is an inactive hole, not a terminator (log 95) |
| First binary-pointer search | Shell escaping was malformed; log 50 was regenerated byte-safely |
| Generic STM32 recipes | Removed; not valid evidence for SNC73270 |
| Eight `0x86` rows at `0x1801c37c` | Corrected to three overlapping 189-byte logical wire windows plus a separate three-row `0x100` scan map |
| Duplicate bootloader checksum "at `0x61000`" | `0x61000` is the start of the duplicated region; the stored word-sums are at `0x0fffc` and `0x70ffc` (log 84) |
| Claimed live `--run` refusal against the app-mode device | Unsupported; log 83 is dry-run only. Log 84 later exercised only the new flag-gated CLI refusal, which returned before device selection; the live path was never entered |
| Backup tool batched its queries | Fatal: the `0x8f` status reply was consumed as read data. Fixed to immediate request-response exchanges (log 84) |
| "Erase/program/unlock are unconstructable" | Narrowed to "the guard rejected every write/unlock/reset form in the self-check" (log 84) |
| Boot-gate framing implying sufficiency | Reframed as necessary-but-incomplete; `FUN_000029d4` and the top-level selected-entry comparison are unresolved (log 84) |
| Busy poll treated as proof of READ completion | Narrowed: bit 1 clear means "not currently reading". The post-EXEC scheduling race is unresolved and documented; end-of-dump self-validation is a mitigation, not a fix (log 84) |
| Busy poll used to sequence a READ at all | Wrong, not merely unproven: log 85 proves dispatch is SysTick-gated, so bit 1 reads clear for "not started yet" and the poll exits immediately. Replaced by a buffer-change handshake; the race is now resolved as PROVEN POSSIBLE (log 85) |
| Log 85's replacement handshake | Also wrong: it read the status *before* the data query, which does not exclude a READ that starts and finishes between two reports, so it could accept a half-old/half-new buffer (24 new + 24 baseline bytes, reproduced). Corrected to sample-then-status-then-confirming-fetch, with an interleaving proof (log 86) |
| Log 85's timing language | "the default outcome", "orders of magnitude", "microseconds", "almost always" withdrawn: the core clock is selected at runtime and the flash-transfer duration is unrecovered, so no rate follows. The result is "proven possible" (log 86) |
| `FakeBootloader` replaced the response buffer atomically | The model could not express a partially written buffer, so no test could catch the defect above. Rewritten with incremental transfers and a foreign-pending injector (log 86) |
| "Polling `resp[1]` bit 1 is the READ-in-progress test" | Narrowed: it is a *mid-transfer* test only, useful for avoiding a half-written buffer. It is not a completion test (log 85) |
| Log 82 treated FF01 as a bidirectional protocol node | Descriptor presence did not prove response routing. Instruction-level endpoint tables show commands on FF01/EP6 and replies on FF00/EP5; the first live status probe timed out because it listened on FF01 (log 89) |

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

- captured a complete 4 MiB U5 image, the bootloader region, or internal MCU
  storage; the verified log-92 artifact is application-region only;
- read U5 or verified its JEDEC ID electrically;
- connected SWD, SPI, Bus Pirate, or another hardware probe;
- executed the ASUS updater;
- used `fwupd` to update or modify the keyboard;
- sent any persistent configuration command;
- erased, programmed, unlocked, or detached a driver;
- proven that the official 1.00.58 image is a safe downgrade or recovery path;
- sent any erase, program, or flash-unlock command, or flashed anything;
- built or flashed custom firmware.

## Recommended continuation

The integrity calculation is now solved (logs 75–76): SN_FWIN per-record values
are a sum of per-`0x10000`-chunk IEEE CRC-32, and the container guard is an
additive word-sum, both recomputable offline. Candidate B's runtime entry, the
bootloader protocol and the exact reset-only entry report are also recovered.
The USB-readable application region is now preserved and verified (log 92), and
the shared version-aware image-format library is in place (log 94). Work should
remain offline: make a redundant copy of the dump and checksum, then Phase 2's
installed-versus-vendor comparison, then improve the code/data map and resolve
`FUN_000029d4` plus the top-level selected-entry comparison before designing a
minimal patch. The controlled sequence is documented in
`notes/step6-offline-custom-firmware-plan.md`. Any flashing remains a separately
reviewed and explicitly authorized phase.

Before any hardware modification, prepare a separate reviewed preservation
plan for U5 and MCU readback: correct voltage, board-power isolation, bus
contention prevention, exact pin mapping, read-only commands, multiple identical
dumps, and independent hashes. Never proceed from an official updater image
alone as if it were the installed-device backup.
