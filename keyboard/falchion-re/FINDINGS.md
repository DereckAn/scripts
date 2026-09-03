# ASUS ROG Falchion Ace HFX — Findings

Investigation date: 2026-08-29 (America/Mexico_City)
Host: CachyOS Linux, kernel 7.2.0-1-cachyos

This is the authoritative current status document. Files under `notes/` preserve
earlier protocol work and are synchronized to this document, but some of their
hardware observations cannot be independently replayed because the cited PCAP
captures are not present in the repository.

For a chronological account of the work, decisions, corrections, and evidence,
see `TIMELINE.md`.

Safety scope for the 2026-08-29 investigation: USB-only, read-only diagnostics.
No firmware update, HID data/feature report request, vendor control command, DFU
detach/upload/download, USB reset, driver detach, permission change, erase,
program, or SPI transaction was performed. Earlier protocol research recorded
device-writing HID experiments; those were not repeated here and are not part of
the preservation-safe procedure.

## Current answer: can the installed firmware be backed up through USB?

**No standard USB firmware-readback path is exposed in the keyboard's current operating mode.** The device exposes five HID interfaces and no DFU-class interface. A direct, read-only `dfu-util -l` enumeration completed successfully but listed no DFU targets.

This does **not** prove that USB backup is impossible. Later static analysis
(logs 81-82) **supports the existence of a proprietary bootloader READ path**:
the PID-`1b7f` bootloader implements a vendor-HID READ (execute opcode `0x05`)
over the application region `[0x10000, 0x7c000)` in ≤`0x30`-byte chunks.

Status as of the 2026-08-31 correction pass:

- **Statically recovered:** the bootloader READ path, the full write/erase/
  program protocol, the 64-byte vendor-HID wire framing, Candidate B's runtime
  entry, and both integrity mechanisms. All of this comes from decompiling
  preserved artifacts.
- **Not established:** none of it has been exercised. There has been **no live
  validation of any command**, no bootloader-mode entry, and **no installed-
  firmware backup exists**. `dumps/vendor/M605_V01_00_58.bin` is a vendor
  reference image (v1.00.58), not a readback of this unit (v1.59).

So: **standard USB backup unavailable; a proprietary bootloader READ path is
supported by static analysis but unvalidated in practice.**

No firmware backup was created during this session.

## Verified USB identity

- VID:PID: `0b05:1b7e`
- Manufacturer: `ASUSTeK`
- Product: `ROG FALCHION ACE HFX`
- Current sysfs path: `/sys/bus/usb/devices/6-2`
- Current address after the second-connector retry: bus 006, device 008 (address changes after replug)
- USB version: 2.00; negotiated high speed, 480 Mb/s
- Device-release descriptor: `bcdDevice 1.59` (`0x0159`). This is firmware-facing version metadata, but USB does not guarantee it uniquely identifies all firmware components.
- One configuration, five interfaces, all class `0x03` HID
- Bus-powered, remote-wakeup capable; declared maximum current 500 mA
- Serial string contains spaces and is not a useful unique identifier.

Authoritative logs: `logs/04-usb-sysfs-devices.txt`, `logs/07-falchion-usb-descriptors-sysfs-xxd.txt`, and `logs/15-lsusb-falchion-verbose.txt`.

## Interfaces, reports, endpoints, and bindings

| Interface | HID function / usage | Reports | Interrupt endpoints | Linux binding |
|---|---|---|---|---|
| 0 | Generic Desktop / Keyboard; boot keyboard | 8-byte input (modifiers, reserved byte, six keycodes); 1-byte LED output | `0x81` IN, 8 B, 125 us | `usbhid` → `hid-generic`, `hidraw0` |
| 1 | Vendor-defined page `0xFF00`, usage 1 | 64-byte input and 64-byte output, no report ID | `0x85` IN, 64 B, 125 us; `0x0d` OUT, 64 B, 1 ms | `usbhid` → `hid-generic`, `hidraw1` |
| 2 | Consumer/System/Mouse plus vendor page `0xFFC0` | IDs 1–4; largest is ID 3 with 20-byte payload (21 B including ID) | `0x8c` IN, 21 B, 125 us | `usbhid` → `hid-generic`, `hidraw2` |
| 3 | Generic Desktop / Keyboard bitmap | 152 input bits = 19 B, no report ID | `0x8e` IN, 19 B, 1 ms | `usbhid` → `hid-generic`, `hidraw3` |
| 4 | HID Usage Page `0x59` (Lighting and Illumination) | Feature-report IDs 1–6; largest descriptor-defined report is 51 B including ID; no HID Input item | `0x0f` OUT, 64 B, 1 ms | Unbound; kernel: `couldn't find an input interrupt endpoint` |

Interface 1 is the strongest candidate for the proprietary ASUS configuration channel. Its existence alone does not show that firmware readback is supported.

Interface 4's descriptor was retrieved with the standard HID `GET_DESCRIPTOR` operation performed by `lsusb -v`. No feature value (`GET_REPORT`) or output report was requested. Its lighting usage and feature reports are not a DFU interface.

Raw evidence: `logs/08-falchion-endpoints-sysfs.txt`, `logs/09-falchion-hid-report-descriptors-xxd.txt`, `logs/13-interface-4-and-kernel-log.txt`, and `logs/15-lsusb-falchion-verbose.txt`.

## DFU and fwupd

### DFU

- No interface has DFU class/subclass (`0xFE/0x01`); all five are HID (`0x03`).
- Direct `dfu-util 0.11 -l` succeeded and produced no `Found DFU:` entry.
- Conclusion: no DFU target is exposed in the current operating mode.

The first sandboxed attempt failed at libusb initialization; that failure was environmental and is retained in `logs/11-dfu-util-list.txt`. The approved direct read-only result is `logs/16-dfu-util-list-direct.txt`.

### fwupd

- `fwupdmgr` and `fwupdtool` are not installed.
- The package database reports `package 'fwupd' was not found`.
- Therefore fwupd detection could not be tested on this host without installing software. Nothing was installed or started.

Evidence: `logs/03-tool-availability.txt` and `logs/12-fwupd-availability.txt`.

## Retry through the keyboard's other connector

At 2026-08-29 02:29:56 -06:00, the keyboard was reconnected through its other physical connector and the read-only inspection was repeated.

- It re-enumerated from bus 006 device 002 to bus 006 device 008.
- The host sysfs port remained `6-2`.
- VID:PID remained `0b05:1b7e`; `bcdDevice` remained 1.59.
- It still exposed exactly five HID interfaces with the same classes, endpoints, and driver bindings.
- The 159-byte kernel-cached USB device/configuration descriptor blob was byte-for-byte identical.
- HID report descriptors for interfaces 0–3 were byte-for-byte identical.
- The complete `lsusb -v` output differed only in the transient device address.
- Interface 4 still exposed the same 327-byte Lighting and Illumination report descriptor and remained unbound.
- A second direct `dfu-util -l` completed successfully and again listed no DFU target.

**Conclusion:** the other keyboard connector does not expose additional USB access, a different PID, DFU, or a different report layout in normal operating mode.

Retry evidence: `logs/19-port-retry-sysfs-devices.txt` through `logs/24-port-retry-cached-descriptors.txt`, plus the authoritative comparison in `logs/26-port-retry-corrected-comparison.txt`. The intermediate `logs/25-port-retry-comparison.txt` contains a false `DIFFERENT` result caused by parsing the ASCII column of an `xxd` line; it is retained for auditability and superseded by log 26.

## User-supplied hardware facts (not re-verified by USB diagnostics)

- Main MCU marking: SONiX SNC73270.
- U5: Zbit ZB25VQ32BTIG external flash.
- U5 nominal capacity: 32 Mbit / 4,194,304 bytes.
- Expected U5 JEDEC ID: `5E 40 16`.
- U7 marking: `DIO322 2403 2F3`, likely a USB signal switch.
- U12 marking: `C3NC V0006`, unidentified.
- No Bus Pirate, SWD probe, or SPI programmer is connected.

These facts must not be treated as proof that U5 contains the complete executable firmware. It could hold firmware, assets, configuration, calibration data, or a subset. The SNC73270 may also contain internal nonvolatile memory; that remains unresolved.

## Earlier protocol research and evidence status

The earlier Windows/Armoury Crate work in `notes/protocol.md` adds useful evidence
that is independent of the 2026-08-29 firmware-container analysis:

- interface 1 / usage page `0xFF00` was used as a 64-byte vendor HID transport;
- startup query and configuration opcodes were recorded, including `12 00`,
  `51 21`, and the persistent commit command `50 55`;
- a controlled historical test reportedly changed an ordinary Fn-layer binding
  while reserved Fn bindings were silently ignored despite an echoed response;
- Armoury Crate's UI was reported to block those reserved bindings before sending
  USB traffic.

The current USB descriptor logs independently confirm the transport shape, but
the cited PCAP files are absent from the repository and do not appear in reachable
Git history. Therefore the exact command counts, packet sequences, and behavioral
A/B results are retained as **previously observed on hardware**, not as results
that can currently be reproduced from repository evidence alone. The decoded
profile snapshots, key map, notes, and PowerShell tools are present.

None of the recorded HID write commands are preservation-safe. In particular,
omitting `50 55` only avoids the known persistent commit; `51 21` still changes
live device state. `Fn + Caps` is a settings factory reset, not firmware recovery.

## Historical audit of the earlier Claude Code work

Reviewed sources:

- `keyboard/falchion-ace-hfx-re-guide.md`
- `keyboard/falchion-re/notes/findings.md`
- `keyboard/falchion-re/notes/usb-descriptors.txt`
- `keyboard/falchion-re/notes/report-desc-0.txt`
- `keyboard/falchion-re/notes/report-desc-ff00.txt`
- Commits `307e921` and `f28a7a2`

### Progress that is valid

- Correctly identified VID:PID `0b05:1b7e`, product name, `bcdDevice 1.59`, five HID interfaces, and the endpoint layout.
- Correctly captured interface 1's vendor-defined `0xFF00` report descriptor: 64-byte input and output reports without a report ID.
- Correctly observed that normal-mode `dfu-util -l` finds no DFU target.
- Created a sensible high-level research sequence: enumerate, preserve firmware, capture the vendor protocol, then consider firmware modification only if necessary.
- Selected Windows USBPcap/Wireshark as the intended Armoury Crate observation path.

### Incorrect, stale, or overclaimed items identified by the audit

- `report-desc-0.txt` is a 39-byte vendor-page `0xFF32` descriptor, but the USB descriptor saved two minutes earlier declares interface 4's HID report descriptor length as 327 bytes. It therefore cannot be interface 4 from that enumeration.
- That 39-byte descriptor matches none of the currently connected hidraw devices. Its source is unknown, most likely a different device selected when `hidraw0` was used without first resolving VID:PID and interface ancestry.
- The notes' claim that interface 4 is a 63-byte `0xFF32` input/output channel is superseded. Direct current enumeration identifies interface 4 as HID Usage Page `0x59` (Lighting and Illumination), feature-report IDs 1–6, and one 64-byte OUT endpoint.
- “No USB bootloader exposed” is too broad. Verified: no DFU target in normal mode. Unresolved: a separate bootloader mode or proprietary updater protocol.
- The prior `MODE=0666` permission claim was not re-verified in the managed environment and is broader than necessary for a future tool.

### Safety problems identified by the audit (now corrected in the guide)

- The instruction to let Armoury Crate “apply any pending firmware/config update” directly conflicts with preserving the installed original firmware. Do not follow it.
- Phases 1–3 are described as read-only/reversible, but Phase 3 includes changing settings, replaying HID writes, and remapping keys. Those are writes and must be moved behind a backup/recovery gate.
- The example `d.write(report)` and remap replay are placeholders that could write persistent configuration; they must not be run during the read-only stage.
- The STM32 load address `0x08000000`, STM32 OpenOCD target, and ST-Link flashing example are generic placeholders, not validated for the SONiX SNC73270. They must not be used unless the actual architecture, memory map, debug transport, and flash algorithm are verified.
- The DFU upload outcome table is oversimplified: a protected or unsupported target may fail in several ways, and all-zero/all-`0xFF` output alone does not establish a specific readout-protection level.

### Current gaps after later work

The original missing-work snapshot is preserved in `logs/28-claude-progress-audit.txt`.
The package, firmware image, analyzer, hardware markings, and Ghidra work now exist.
Remaining gaps are:

- no exact installed-1.59 firmware dump or external U5 dump;
- no raw Windows PCAP preserved in this repository;
- no verified firmware-readback command;
- no test-pad/signal map or safe hardware readback wiring plan;
- no tested probe/programmer or bootloader-independent recovery path;
- unresolved Candidate B integrity and true entry/call path.

### Offline-analysis readiness at the 2026-08-29 notes audit (superseded)

- Available locally: `7z`, `file`, `strings`, `objdump`, `tshark`, and Wireshark.
- At the time of that audit, `binwalk`, Ghidra, and OpenOCD were not installed.
  Ghidra and JDK 21 were installed and verified later the same day; see the
  current Ghidra status below.
- At that time the missing tools were not blockers because no updater or firmware
  artifact had yet been examined. This statement is superseded by the preserved
  package, firmware image, and current Ghidra installation.

Audit evidence: `logs/27-claude-notes-report-desc-provenance.txt` and `logs/28-claude-progress-audit.txt`.

## Offline ASUS updater analysis

Source supplied at:

- `/home/dereck/Downloads/ROG_FALCHION_ACE_HFX.zip`
- Extracted directory: `/home/dereck/Downloads/ROG_FALCHION_ACE_HFX/`

No executable from the package was run.

### Package authenticity

- ZIP size: 238,446,426 bytes.
- Computed SHA-256: `a3e895dd4389e6725b15b0c0af6d6644a470a8359c4086a206490b74e9e9d7b9`.
- This exactly matches the SHA-256 published by ASUS for Armoury Crate Gear – ROG Falchion Ace HFX version 1.0.1.15.

### Firmware artifact

- Path: `Firmware/Bin/Firmware/7038/FW/M605_V01_00_58.bin`.
- Declared firmware version: 1.00.58.
- Size: 507,904 bytes = `0x7c000` = 496 KiB.
- SHA-256: `6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d`.
- This is the only firmware BIN found in the package.
- The installed keyboard reports `bcdDevice 1.59`, so the bundled 1.00.58 image is a one-version-older recovery candidate, not an exact backup of the installed firmware.
- No indexed official ASUS result for `M605_V01_00_59.bin` was found during the 2026-08-29 search.

### Updater configuration and transport

The package configuration declares:

```text
Vid = 0x0b05
Pid = 0x1B7E
UsagePage = 0xff00
BootloaderPID = 0B051B7F
Cmd 1 = m 1B7E 1B7F 64 432 FF00 FF00 4
```

The updater's own usage string maps those values to:

- normal application PID: `1b7e`;
- bootloader PID: `1b7f`;
- bootloader region: 64 KiB;
- application region: 432 KiB;
- total: 496 KiB, exactly equal to the BIN size;
- application and bootloader HID usage pages: `ff00`;
- page size: 4 KiB.

Static imports show Windows HID discovery plus `ReadFile`/`WriteFile` interrupt transfers. Updater strings include “Jump to Bootloader,” “Start Erase,” “Programming Success,” and “Read checksum.” This is a proprietary HID firmware protocol, not DFU.

No full-flash readback/upload operation was identified in the static string/import review. This does not prove readback is impossible, but the supplied updater is designed around erase/program/checksum rather than backup.

**Never run `FW_Update_Tool_M605.exe` or `peripheral_fwu_pro.exe` against the keyboard during preservation.** They are confirmed writers and would attempt bootloader entry, erase, and programming.

### Firmware format and architecture

- Offset `0x00000`: container marker `SNC7320A`.
- Offset `0x00200`: `SN_BCFG`.
- Offset `0x10000`: application marker `SN_FWIN`, matching the 64 KiB bootloader boundary.
- The image contains ARM Thumb-looking code and explicit Cortex fault strings.
- Header address fields and code references use the `0x600xxxxx` address range, not the STM32-style `0x08000000` assumed in the old guide.
- The image includes SONiX strings, flash-ID handling, USB HID code, keyboard/macro/Fn-related symbols, bootloader code, and CRC verification strings.
- Entropy is approximately 4.82 bits/byte, with large zero/`0xFF` areas; the image is not globally encrypted or compressed.
- Additional SONiX container/header markers appear within the application region. Their exact purpose remains unresolved.

The header string `SNC7320A` likely identifies a SONiX firmware/container family. It does not by itself contradict the physical MCU marking SNC73270, but the relationship needs authoritative documentation.

### Preservation status after offline analysis

- We now have an authentic ASUS-provided 1.00.58 combined bootloader/application image.
- We still do not have the installed 1.59 image.
- We still do not have a dump of U5 or the MCU's installed nonvolatile contents.
- On 2026-08-29, the original ZIP and extracted 1.00.58 firmware were copied into this workspace without running any packaged executable or accessing the keyboard.
- The preserved ZIP is `vendor/asus/original/ROG_FALCHION_ACE_HFX.zip`; the preserved BIN is `dumps/vendor/M605_V01_00_58.bin`.
- Both workspace copies compare byte-for-byte equal to their sources. Their SHA-256 hashes are recorded in `vendor/asus/ARTIFACTS.md` and `logs/35-official-artifact-preservation.txt`.
- The ZIP is locally present but narrowly ignored from normal Git staging because its 238,446,426-byte size exceeds GitHub's normal per-file limit. The firmware BIN and text manifest are not ignored.

Evidence: `logs/29-asus-package-original-metadata.txt` through `logs/35-official-artifact-preservation.txt`.

## Firmware architecture and modification feasibility (2026-08-29)

### Verified platform facts

The official SONiX SNC7320 Series Product Brief identifies this family as a
dual-core SoC with two independently programmable ARM Cortex-M3 processors, an
SWD port, shared SRAM/mailbox RAM, ROM and RAM remapping, and an external SPI-NOR
controller with execute-in-place support. This agrees with both the SNC7320A
container marker and the two code payloads observed in the ASUS image.

Primary source: `https://www.sonix.com.tw/webapi/fl218645/snc7320_brief_data_sheet_V2.3.pdf`.

### Observed image layout

The image is a structured 496 KiB SONiX container, not a single flat program:

| File range | Verified or strongly supported role |
|---|---|
| `0x00000-0x0ffff` | Primary bootloader/container, USB stack, flash handling, boot selection, and CRC verification |
| `0x10000` | `SN_FWIN` application header (`v1.0.00` is the container-format string, not the ASUS release version) |
| `0x11000-0x168ab` | Candidate payload A; Cortex-M vector table, USB/system coordination, RTOS/fault code, flash-ID handling |
| `0x17000-0x20fff` | `0xFF` padding |
| `0x21000-0x3f753` | Candidate payload B; valid Thumb-2 code and the bulk of keyboard behavior, Fn, macros, profiles, power management, and USB identity |
| `0x40000-0x5ffff` | `0x00` reserved/padding area |
| `0x60000-0x60fff` | Additional `SNC7320A` wrapper/header |
| `0x61000-0x70fff` | Exact byte-for-byte copy of the first 64 KiB bootloader region |
| `0x71000-0x73fff` | `0x00` padding |
| `0x74000-0x7bfff` | Independently executable RAM image mapped at runtime to `0x18038000`; includes vector table, Thumb-2 startup/code/data, padding, and unresolved terminal integrity metadata |

Verified Cortex-M vector candidates:

- `0x01000`: initial SP `0x1802b230`, reset handler `0x000002f5`;
- `0x11000`: initial SP `0x18036140`, reset handler `0x000014a9`;
- `0x62000`: exact duplicate of the first bootloader vector table;
- `0x74000`: initial SP `0x1803e458`, reset handler `0x180381c1`.

The `0x74000` vector values map exactly into the image when the slice is loaded
at `0x18038000`; its reset code begins at file offset `0x741c0`. All sampled
handlers decode as valid Cortex-M3 Thumb-2 code.

### Integrity and authentication

- **Both SN_FWIN per-record checksums are now fully reproduced offline** (logs
  75/76). The bootloader routine `FUN_00005028` copies each region to RAM in
  `0x10000`-byte chunks, takes an independent IEEE CRC-32 of each chunk, and
  **sums the per-chunk CRC-32 results mod 2³²**. Candidate A (`0x60011000`,
  `0x58ac`) fits one chunk, so its stored value `0x5e75c17a` is a plain CRC-32.
  Candidate B (`0x60021000`, `0x1e754`) spans two chunks, so its stored value
  `0x1a76c116` equals `CRC32(file 0x21000..0x31000) + CRC32(file 0x31000..0x3f754)`
  `= 0x35530359 + 0xe523bdbd`. This is why plain CRC-32 over B's whole range
  (`0x60c95a7b`) never matched.
- **The terminal values are additive 32-bit word-sums**, not CRCs (bootloader
  `FUN_000026d0`): the last word of a region equals the 32-bit sum of every
  preceding word. `0xfb665ae3` is the sum over the bootloader region
  `0x00000..0x10000`, stored in that region's final word at offset **`0x0fffc`**;
  the duplicate bootloader copy at `0x61000..0x71000` stores the same value in
  its own final word at **`0x70ffc`**. (`0x61000` is the start of the duplicated
  region, not a checksum offset — an earlier draft cited it as one.)
  `0x5d27c5a9` is the sum over the whole application region `0x10000..0x7c000`,
  stored at `0x7bffc`. All reproduce exactly.
- The firmware/update path contains CRC/checksum language but no identified
  firmware signature-verification string, embedded public key, or crypto-library
  dependency. Certificate strings in the Windows executables are their own
  Authenticode signatures. This supports—but does not prove—the hypothesis that
  modified firmware may be accepted after correcting non-cryptographic integrity
  fields.

### Concrete patchability evidence

The firmware is neither globally encrypted nor compressed. It contains normal
Thumb-2 code and plain data tables. The application USB identity is directly
visible near the end of payload B:

- `0x3f4f3`: little-endian VID:PID `0b05:1b7e`;
- `0x3f665`: `ASUSTeK`;
- `0x3f66f`: `ROG FALCHION ACE HFX`.

Therefore, offline binary modification is technically possible. Three levels of
work should be distinguished:

1. **Data patching:** descriptors, strings, tables, or known constants. This is
   easiest to create offline, but still requires all affected checksums before it
   can be safely flashed.
2. **Behavior patching:** changing existing Thumb functions, branches, key logic,
   or feature handling. This is feasible with a Cortex-M3 disassembler/decompiler
   once load addresses and cross-core calls are mapped.
3. **Replacement/custom firmware:** possible in principle, but substantially
   harder because startup, ROM APIs, memory remapping, inter-core mailbox use,
   USB, Hall-effect scanning, board GPIO/power control, and the boot protocol are
   not yet documented.

The vendor updater checks exact binary size, can skip equal versions, sends a
proprietary jump-to-bootloader command that causes re-enumeration at PID `1b7f`,
erases, programs, reads a checksum, and then checks the reported version.
It also contains a `Programming Success! (no check checksum)` path. No updater
executable was run.

### Current safety conclusion

**Do not flash a modified image yet.** Being able to edit the BIN is not the same
as having a recoverable modification workflow. Before a device test, we need:

- a complete interpretation/recalculation method for every integrity field;
- confirmation of which regions the updater erases and whether it rewrites the
  primary bootloader;
- a proven downgrade/recovery path independent of the application firmware;
- preferably verified hardware readback of U5 and any relevant MCU state;
- a sacrificial or externally recoverable test setup.

The preserved 1.00.58 image is useful recovery material, but it does not by
itself prove that downgrade is accepted or that a failed update can recover over
USB.

Evidence: `logs/36-firmware-layout-analyzer.txt` and
`logs/37-firmware-modification-feasibility.txt`. Reproducible parser:
`tool/analyze_sonix_firmware.py`.

### Ghidra installation and project status

Ghidra 12.1.2-2.1 and `jdk21-openjdk` 21.0.11.u10-2 are installed and verified.
Headless analysis works with `JAVA_HOME=/usr/lib/jvm/java-21-openjdk` and
temporary XDG state under `/tmp`, avoiding changes to the user's normal Ghidra
preferences.

Four derived slices of the preserved vendor image were imported as
`ARM:LE:32:Cortex` / compiler `default` into the local ignored project
`ghidra/project/falchion-hfx`:

- primary bootloader at runtime base `0x00000000`;
- application candidate A at `0x00000000`;
- application candidate B at the original provisional base `0x00000000`;
- a byte-identical Candidate B comparison program mapped at its now-supported
  runtime base `0x18000000`;
- the RAM image at runtime base `0x18038000`.

The preserved source BIN was not modified. Verified vector/entry labels were
added only to the Ghidra database. Ghidra created the previously missing
`CandidateA_Reset_Handler` at `0x14a8` and the evidence-bounded
`CandidateB_Start_Function` at Candidate B offset `0x0` (runtime
`0x18000000`). Candidate B begins with a valid Thumb function prologue, but no
vector or call path yet proves it is the payload's true entry point. For the bootloader and RAM image, the exact reset addresses fall inside existing
auto-created functions, so those functions were preserved and exact entry
labels were added instead. Candidate B reanalysis emitted one isolated p-code
decode warning at `0x24f2`, but analysis completed and saved successfully.

Evidence: `logs/38-ghidra-preinstall-check.txt` through
`logs/45-ghidra-synchronized-project-report.txt`; workspace instructions:
`ghidra/README.md`.

### Candidate B runtime mapping and recovered tables

Candidate B's runtime base is now strongly supported as `0x18000000`, resolving
the earlier provisional base-zero interpretation. The `SN_FWIN` record at full
firmware offset `0x10030` contains the sequence `0x18000000`, `0x60021000`,
length `0x1e754`, and stored integrity value `0x1a76c116`, followed by another
`0x18000000` / `0x60021000` pair. More decisively, every runtime pointer used by
the key-policy code maps to coherent data inside the Candidate B slice when
`0x18000000` is subtracted.

Recovered mappings include:

| Runtime address | Candidate B offset | Full BIN offset | Contents |
|---:|---:|---:|---|
| `0x1801bff6` | `0x1bff6` | `0x3cff6` | 189-byte source/target translation table |
| `0x1801c37c` | `0x1c37c` | `0x3d37c` | three effective-KBID wire-ID-to-record-index windows |
| `0x1801c50e` | `0x1c50e` | `0x3d50e` | three effective-KBID scan-position maps |
| `0x1801c810` | `0x1c810` | `0x3d810` | 6 base-policy words followed by 57 Fn/other-policy words |

The exact base-policy values are `e8, 53, 39, 47, e3, e2`. The exact Fn-policy
list contains 57 standard HID or vendor usages. It includes the manual's locked
function families: F1-F12; digits and `-`/`=`; all four arrows; Escape, Tab,
Insert, Delete, Page Up, and Page Down; left/right Ctrl and Shift; left Alt/GUI
and right Alt; Q/W/E/R/T/Y/U/P; A/S/D/F/G/H; Caps Lock; and vendor/custom
`0xe8`. This is substantially stronger than the earlier inference from runtime
pointers alone.

The corrected-base Ghidra program has memory block `0x18000000-0x1801e753`.
It resolves the dispatcher accesses directly to the embedded translation and
index tables and the policy predicate directly to `0x1801c810` and
`0x1801c828`. The original base-zero program is retained for audit/comparison.

Evidence: `logs/57-ghidra-runtime-key-table-reference-scan.txt` through
`logs/69-ghidra-candidate-b-corrected-kbid-map-report.txt`. Reproducible decoder:
`tool/analyze_candidate_b_tables.py`.

#### KBID selection and key-index-map structure

The former “layout/profile” interpretation is now narrowed to an effective
keyboard-ID (KBID) selector, not a user profile. Candidate B function
`FUN_180088ea` obtains an input ID in the range `0..25`, translates it through a
26-byte lookup at runtime address `0x00004fcd`, and stores the result at
`0x1801ee6c`. That lookup is embedded in Candidate A at full BIN offset
`0x15fcd`. Its only raw outputs are `0`, `1`, and `4`; the same function
immediately normalizes `4` to `2`. Therefore the effective selector range is
exactly `0..2`.

For a wire source ID below `0xbd`, the dispatcher uses:

```text
record_index = byte[0x1801c37c + effective_kbid * 0x86 + wire_source]
record        = 0x180202ac + layer * 0xd84 + record_index * 0x20
```

Each effective KBID consequently has a 189-byte logical window, but adjacent
windows begin only `0x86` bytes apart and overlap by `0x37` (55) bytes. Their
ranges are `0x1801c37c-0x1801c438`, `0x1801c402-0x1801c4be`, and
`0x1801c488-0x1801c544`. This overlap is intentional code behavior, not three
independent 134-byte rows.

A separate scan-position table starts at `0x1801c50e` and uses three
`0x100`-byte rows selected by the same effective KBID. The last 55 bytes of the
third logical wire window share storage with the first 55 bytes of scan row 0.
The scan rows end at `0x1801c80d`, followed by two zero padding bytes before the
policy list. Fixed and dynamic references in `FUN_18000466` and
`FUN_180057d2` establish the scan table's `0x100` stride.

The analyzer now lists all 189 wire IDs with their translated internal code,
record index for each KBID, and computed base/Fn record address. It also lists
the 68 historical physical-key labels separately. Those names came from earlier
protocol captures and must not be projected onto every KBID variant; several
special/navigation positions do not align directly with the translation table.
Record index `0x4b` occurs 67-68 times per logical window and is a strong
fallback/dummy-record candidate, but its live runtime semantics remain
unproven.

### Candidate B vendor-HID and key-policy analysis

Offline Ghidra analysis identifies Candidate B offset `0x1fbe`, runtime
`0x18001fbe`, as the high-confidence
vendor-HID command dispatcher. It reads the 64-byte request buffer at
`0x1802337c`, dispatches top-level opcode `0x50` to a branch containing
subcommand `0x55`, and dispatches opcode `0x51` to the keyboard-configuration
handlers. The local Ghidra project labels this function
`VendorHID_CommandDispatcher`.

The `0x51/0x21` and `0x51/0x22` path is now bounded statically:

- source byte 2 must be at most `0xbc`; byte 3 must be `0x00` or `0x9f`;
- the 16-bit target in bytes 4-5 is translated through a runtime key table when
  it is at most `0xbc`; special targets `0xff`, `0xc7`, `0xc8`, and `0xd3` have
  separate internal encodings;
- `0x21` clears a per-key mode byte, while `0x22` sets it and stores the
  actuation value from bytes 7-8 divided by 10;
- the handler marks profile state dirty and constructs a 64-byte response that
  echoes opcode `0x51`, the subcommand, source, and payload.

There is no explicit reserved-source rejection in this packet handler. Every
source from `0x00` through `0xbc` reaches the KBID-selected record-index map.
This agrees with the historical observation that a reserved remap could be
echoed without becoming effective.

The target translation is now recovered from the official BIN. Ordinary target
IDs `0x00..0xbc` use the 189-byte table at `0x1801bff6`; target `0xff` reuses the
source translation; and `0xc7`, `0xc8`, and `0xd3` are stored with an
`0xa000`-class internal encoding. Other values remain command-specific or
rejected and must not be generalized.

Candidate B contains a separate predicate at offset `0x1f6e`, runtime
`0x18001f6e`, now labeled
`IsKeyUnsupportedForLayer`. It copies and searches one of two runtime lists: 6
32-bit entries for layer selectors 0 or 2, and 57 entries for other selectors.
The configuration-load state machine calls it with selector 0 for base mappings
and selector 1 for Fn mappings; when it returns true, the mapping is skipped and
the firmware uses diagnostic strings `R_NSK_M` or `R_NSK_FnM`. This is verified
device-side reserved/unsupported-key policy logic and is the strongest current
explanation for the historical "ACK but no effect" behavior.

The 63 list entries at `0x1801c810` are embedded in Candidate B and have now been
recovered. Their standard HID usages agree closely with the manual's reserved Fn
combinations. The remaining `0xe8` value is vendor/custom. Other handler tables
include the key translation table at `0x1801bff6`, key records at `0x18021db4`,
the remap-record base at `0x180202ac`, and per-key index mapping at
`0x1801c37c`.

Evidence: `logs/47-ghidra-candidate-b-opcode-search.txt` through
`logs/54-ghidra-protocol-labels.txt`. Reproducible reports and conservative label
script are under `ghidra/scripts/`. All work was offline; no USB command was sent.

### Candidate A reset, scatter-load, and RAM base (logs 72–73)

Offline read-only disassembly and decompilation of `app_candidate_a.bin` recovered
Candidate A's startup and image-copy path. This is the boot/loader baseline that
precedes the Candidate B integrity check; it does **not** itself contain or
compute Candidate B's integrity field `0x1a76c116` (that is done by the
bootloader — now resolved below, logs 75–76).

- **Reset handler** `CandidateA_Reset_Handler @ 0x14a8`: loads the stack pointer
  from the VTOR table (`0xe000ed08` → table[0] → `sp`), calls the C-runtime/clock
  init `FUN_00001216` (via literal `DAT_000014ec = 0x1217`), then branches to
  `0x140` (via literal `DAT_000014f0 = 0x141`).
- **`0x140`** calls the scatter loader `FUN_00000148 (0x148)`, then `bl 0x2c8`
  (application/`__rt_entry`, not analyzed here).
- **Scatter loader `FUN_00000148`** is the standard ARM `__scatterload`: it walks a
  region-descriptor table at `0x5750`, each entry `(src, dst, size, handler)`,
  dispatching via `bx r3` to the region handler. Three regions were recovered:

  | src | dst | size | handler @ | kind |
  |---|---|---|---|---|
  | `0x60021000` | `0x18000000` | `0x1e354` | `0x1d8` | `__scatterload_copy` |
  | `0x6003f354` | `0x1801e354` | `0x0b04` | `0x17c` | `__scatterload_decompress` |
  | `0x6003f754` | `0x1801ee58` | `0x172e8` | `0x1f4` | `__scatterload_zeroinit` |

  The three handlers at `0x17c`/`0x1d8`/`0x1f4` were confirmed by ephemeral
  disassembly to be the standard block-copy, LZ77-style decompress, and zero-init
  routines. The read-only project was discarded (no database change).
- **Corroboration of the runtime base:** Candidate A copies its image from source
  region `0x60021000` (external/XIP flash window) into RAM at `0x18000000`. This
  independently confirms the `0x18000000` runtime base already used to rebase and
  decode Candidate B's tables in logs 62–70.
- **`FUN_00001216`** performs low-level clock/PLL and power setup against the
  system-control block at `0x45000000`, then bounds-checks the main stack pointer
  to `[0x18000000, DAT_000014a4]` and faults via `FUN_00000dbc(7)` if it is out of
  range — a startup integrity guard, distinct from Candidate B image verification.

Evidence: `logs/72-ghidra-candidate-a-loader-report.txt`,
`logs/73-ghidra-candidate-a-scatter-handler-report.txt`, and
`ghidra/scripts/FalchionCandidateALoaderReport.java`. Both runs used
`-readOnly -noanalysis`; the source BIN and keyboard were untouched. The next
offline target remains Candidate B's loader/verification path and the derivation
of `0x1a76c116`.

### SN_FWIN integrity record table and Candidate B checksum status (log 74)

The `SN_FWIN` header at file `0x10000` (`SN_FWIN\0v1.0.00\0`) contains a table of
four-word records, each `(flash_addr, length, crc32, ram_dest)`, starting at file
`0x10024`:

| record | flash_addr | length | crc32 | ram_dest |
|---|---|---|---|---|
| A | `0x60011000` | `0x000058ac` | `0x5e75c17a` | `0x18000000` |
| B | `0x60021000` | `0x0001e754` | `0x1a76c116` | `0x18000000` |
| — | `0x60021000` | `0x00000000` | `0x00000000` | `0x00000000` (terminator) |

- **Record A reproduces exactly.** IEEE CRC-32 over the mapped file bytes
  `0x11000..0x168ac` equals the stored `0x5e75c17a`. This locks both the
  flash→file mapping (`file = flash − 0x60000000`) and the algorithm; the analysis
  tool asserts it as a hard self-check.
- **Both records target RAM `0x18000000`.** Combined with logs 72–73 (Candidate A
  scatter-loads flash `0x60021000` into `0x18000000`), Candidate A is a
  first-stage loader for Candidate B; the two records are the loader's own image
  and the application image it pulls in, both destined for the same runtime base.
- **Record B's length is the exact flash footprint of B.**
  `0x1e754 = 0x1e354` (Candidate A's copy region) `+ 0x400` (the compressed source
  of A's decompress region), i.e. file `0x21000..0x3f754`.
- **Record B does not match any file-byte checksum.** Over that range the IEEE
  CRC-32 is `0x60c95a7b`, not `0x1a76c116`. Ruled out offline: CRC-32 variants
  (init/xorout/reflect/forward), CRC seeded with A's value, running CRC across
  `A+B`, record-prefixed CRC, simple sum/xor/adler accumulators, the copy-region
  length `0x1e354`, and full-file range sweeps (fixed-start-vary-end and
  fixed-length-vary-start, step 4) — zero hits.
- The bootloader slice contains the reflected CRC-32 constant `0xedb88320`
  (`bootloader_primary.bin` offset `0xc78c`), consistent with the reflected IEEE
  CRC-32 that reproduces A.

Log 74 established (before the verifier was read) that B's value is not a plain
CRC-32 of the container's B bytes under any tested variant/seed/range. Reading
the bootloader verify routine (below, logs 75/76) then resolved exactly why.

Evidence: `logs/74-candidate-integrity-crc-analysis.txt`. Read-only; no device
access.

### Bootloader integrity/verify path recovered (logs 75–76)

Read-only decompilation of `bootloader_primary.bin` recovered the whole boot
verify chain. The boot orchestrator `FUN_00007ec8` selects a candidate via
`FUN_00002af0 → FUN_00008000(0x60000000)`, then requires `FUN_000026d0(0x6c000)`
to pass before jumping to the loaded image.

- **`FUN_00008000`** scans the boot-priority pointer table at flash
  `0x60000208`, checks each target's `SN_FWIN` magic, validates the entry
  address (`FUN_00005240`), then verifies the records with `FUN_0000511c`
  (strings `"[BLD] CRC Verify PASS!"`, `"[BLD] CRC mismatch at region %d"`,
  `"On Flash: 0x%08X, Actually: 0x%x"`).
- **`FUN_0000511c`** loops up to 8 region records (`+0x24` addr, `+0x28` len,
  `+0x2c` stored checksum, `0x10`-byte stride), computes each region's checksum
  with `FUN_00005028`, and compares it to the stored `+0x2c` word.
- **`FUN_00005028(out, addr, len, 0x18000000, 0x10000)`** is the checksum:
  it copies the region to RAM `0x18000000` in `0x10000`-byte chunks, runs the
  hardware CRC-32 engine (`FUN_000028e8` mode 5, result read by `FUN_000028c4`)
  over each chunk independently, and **accumulates the per-chunk CRC results by
  32-bit addition**. One chunk ⇒ plain CRC-32 (Candidate A); two chunks ⇒ the
  CRC sum (Candidate B). This exactly reproduces `0x5e75c17a` and `0x1a76c116`.
- **`FUN_000026d0`** is a separate whole-region integrity pass: it reads the
  region in `0x1000`-byte pages and 32-bit-sums every word, requiring the final
  word to equal the running sum. This produces the terminal values `0xfb665ae3`
  (bootloader) and `0x5d27c5a9` (application region).

`tool/analyze_candidate_integrity.py` reproduces all four fields (A, B, and both
word-sums) from the preserved BIN and asserts each against its stored value.

Patchability consequence: the SN_FWIN integrity is a chunked-CRC **sum**, not a
cryptographic signature, and the container-wide guard is an additive word-sum —
both are recomputable offline. A modified Candidate B image can, in principle,
be given a correct `+0x2c` record value (sum of its per-`0x10000`-chunk CRC-32s)
and a corrected application word-sum. The safety conclusion is unchanged: this
lowers the integrity barrier but flashing still depends on the unverified
bootloader write protocol and recovery path, so no modified image should be
flashed yet.

Evidence: `logs/75-ghidra-bootloader-verify-report.txt` (read-only decompiles),
`logs/76-candidate-integrity-resolved.txt`,
`ghidra/scripts/FalchionBootloaderVerifyReport.java`,
`tool/analyze_candidate_integrity.py`. Read-only; no device access.

### Boot container structures and boot gate (logs 75, 78)

The bootloader walks a layered container format before it CRC-verifies and jumps.
Decoded offline and cross-checked against the decompiles in log 75:

```
SNC7320A wrapper  (primary @flash 0x60000000 / file 0x0;
                   backup  @flash 0x60060000 / file 0x60000)
  +0x10 bootloader_ptr (0x60001000 / 0x60062000)   +0x14 size 0x10000
  +0x200 "SN_BCFG\0" boot-config
    +0x208 boot-priority pointer table: slot0=0x60010000, slot1=0x00000000
             -> SN_FWIN header @flash 0x60010000 (file 0x10000)
                  +0x10 entry_ptr 0x60011000   +0x18 CRC-enable gate (=1)
                  +0x24.. per-region records (A loader, B application)
```

Key facts:

- **There is no populated second boot slot.** Slot 1 is `0`, and both the primary
  and backup `SN_BCFG` point at the same `SN_FWIN` header. So "Candidate A/B" are
  two *regions* of one firmware (loader + application), not two boot images. The
  redundancy is a backup *container/bootloader* copy at `0x60060000`, which
  re-references the same application header.
- **`FUN_00008000`** selects a candidate by: reading each boot slot, checking
  `SN_FWIN` magic, validating the entry image's initial SP (`FUN_00005240`),
  then CRC-verifying the records (`FUN_0000511c`). It returns entry `0x60011000`.
- **The `SN_FWIN +0x18` gate controls whether records are CRC-checked at all.**
  It is `1` here, so the records are verified; a `0` there would bypass the CRC
  loop entirely.
- **`FUN_00005240`** dereferences the entry pointer and requires the image's
  *initial stack pointer* (first word at `0x60011000`, here `0x18036140`) to lie
  in valid RAM (`0x18000001..0x18040000` or `0x20000001..0x20001000`).
- **Known constraints for a modified image:** the `SNC7320A`/`SN_BCFG`/`SN_FWIN`
  magics, the slot-0 pointer, the `+0x18` gate, and the entry SP must all remain
  valid, *in addition to* the recomputed integrity fields. A Candidate-B data
  patch touches none of them, so the builder's rebuilt image satisfies every
  constraint we have actually read.

These are **necessary conditions we have observed, not a sufficient set.** Two
things in this path are unresolved: `FUN_000029d4` is not decompiled, and the
top-level comparison applied to the selected entry value before the jump has not
been recovered, so the caller's accept/reject rule is unknown. Any ROM or
first-stage condition ahead of the bootloader is also unexamined. Passing these
checks therefore does not establish that an edited image boots.

`tool/analyze_boot_structures.py` decodes this and reports the checks together
with the unresolved points; the builder (`tool/build_modified_image.py`) checks
the same constraints on its output.

### Candidate B runtime entry and full boot chain (logs 79–80)

Candidate B has no vector table — RAM `0x18000000` (file `0x21000`) begins with a
function prologue (`push`), not an initial-SP/reset pair. It is entered by a
direct call from the loader, and that call was found:

- Candidate A's post-scatter C-runtime `FUN_000002c8` (invoked from the reset
  handler after `__scatterload`) calls the veneer `thunk_EXT_FUN_1800023a`, i.e.
  **Candidate B's true runtime entry is `0x1800023a`**.
- `CandidateB_Entry@0x1800023a` is the application `main`: it emits the literal
  string **"welcome to main"**, initialises clocks/GPIO/USB, creates the RTOS
  task **`INIT_TASK`** (entry `0x1800004d`, stack `0x100`, priority `0x14`),
  starts the scheduler (`func_0x180136be`), and enters the idle loop. It reaches
  the already-identified `VendorHID_CommandDispatcher@0x18001fbe`.

The boot chain is therefore complete end to end:

```
ROM/first-stage
  -> bootloader FUN_00007ec8: select + verify (chunked-CRC records + word-sum)
     -> Candidate A reset 0x14a8 -> __scatterload copies B to RAM 0x18000000
        -> FUN_000002c8 -> call B entry 0x1800023a (main)
           -> RTOS INIT_TASK -> VendorHID dispatcher 0x18001fbe
```

Consequence for modification: a Candidate-B behaviour patch targets code at
`0x18000000`-relative addresses (file `0x21000`-relative), and its entry/main and
dispatcher are now known, so a change can be traced from the vendor-HID command
down to the affected handler. This does not affect the integrity/boot-gate
recompute — those remain as recovered above.

### Bootloader write/erase/program protocol (log 81, cross-checked with log 34)

The `1b7f` "Gaming Keyboard Bootloader2" service loop (`FUN_00003a7c`) polls two
USB flags; the OUT-report path (`FUN_00002db8`) dispatches on a command byte at
report offset `0x34`:

| cmd byte | handler | operation |
|---|---|---|
| `0x01` | `FUN_00003ab8` → `FUN_00003ca8(0, addr, 1)` | **ERASE** (flash-controller erase command `0xa`) |
| `0x05` | `FUN_00003b64` → `FUN_00003f08` | **READ** flash into the report buffer |
| `0x51` | `FUN_00003afc` → `FUN_000040a4(0, addr, len, data, 1)` | **PROGRAM** flash (loops over the range) |

- **Self-protection:** both the erase and program handlers require
  `0xffff < addr < 0x7c000`. The primary bootloader region `[0x0, 0x10000)` is
  therefore **not** erasable or programmable through these commands; the SN_FWIN
  header, both candidates, and the backup container region are writable.
- Flash access is via a hardware flash/DMA controller, not raw SPI opcodes:
  erase writes a command code (`8`/`9`/`10` for different granularities) to the
  controller; program/read use `FUN_00002f0c` with a descriptor (`+0x0c` address,
  `+0x04` data pointer, direction byte `0`=write / `1`=read). Read reuses the
  same engine as the CRC verifier (`FUN_000026d0`).
- Host side (updater, log 34) matches exactly: `Jump to Bootloader` →
  re-enumerate as `1b7f` → `Bootloader Version` → `Start Erase...` (per page) →
  program (`Programming Success! (no check checksum)`) → `Read checksum...`. The
  transport is HID reports (`REPORT_ID`/`USAGEPAGE`/`OutputReportByteLength`); the
  updater CLI takes `PAGE_SIZE` and `APP_PKT_LEN`/`BOOT_PKT_LEN`.

Notably the program path has a **"no check checksum"** mode, and **no signature
verification was found in the code paths that were decompiled** — consistent
with the integrity being a recomputable checksum rather than a cryptographic
signature. This is an absence of evidence in the paths examined, not proof that
no signature check exists anywhere in the device. This maps the write protocol
**as statically recovered**; **it does not authorise sending any of these
commands**, and none has been sent. Erase/program remain destructive and must not
be issued until a verified recovery backup exists (roadmap step 5).

### Bootloader vendor-HID wire framing (READ path) — logs 82 and 89

Transport uses **two distinct unnumbered 64-byte vendor-HID interfaces**:
commands are written to usage page `0xFF01`, interface 0, physical endpoint 6
(`/dev/hidraw6` during the log-88 enumeration); replies are read from usage page
`0xFF00`, interface 1, physical endpoint 5 (`/dev/hidraw7` then). The endpoint
numbers come from the bootloader's controller-channel initialization and handler
table, not from descriptor proximity: OUT channel 0 maps to EP6 and calls router
`FUN_0000bd40`; responder `FUN_00004f7c` sends on IN channel 1, which maps to
EP5. Log 82's single-FF01 transport conclusion used descriptor presence alone
and is superseded by this instruction-level mapping in log 89.

The router reads `report[0]` as a sub-command (top bit `0x80` = query/IN vs
action/OUT; low 7 bits = code) and passes `report[1..63]` as the payload to the
OUT parser `FUN_0000380c` or the IN responder `FUN_00003740`.

OUT sub-commands (`report[0]`, top bit clear):

| `report[0]` | payload | effect |
|---|---|---|
| `0x10` | `"ASUSHIDFWU"` | unlock (sets a flag; required only for erase/program) |
| `0x20` | addr, 4 bytes little-endian | set target address |
| `0x21` | length, u16 LE | set length |
| `0x22` | `[count≤0x3c][off u16][data…]` | load program data into the buffer |
| `0x1f` | `[opcode]` | execute: `0x01`=erase, `0x05`=read, `0x51`=program |
| `0x11` | — | system reset (reboot) |

IN/query sub-commands (`report[0]` with top bit set, answered by `FUN_00003740`):
`0x8e` → whole-image CRC verify result (`0xfa` pass / `0xfe` fail); `0x8f` →
status; `0xaa` → the read-back data.

**Response framing (log 82 `FUN_00003740`).** The responder writes
`resp[0] = query & 0x7f`, so `0x8f` is answered by `0x0f` and `0xaa` by `0x2a`.
For the `0x0f` status it returns `resp[1] = state+0x38` (flags) and
`resp[2] = state+0x35` (error: `1` address out of range, `2` not unlocked,
`3` bad length). For `0x2a` it memcpy's the data starting at `resp[1]` for the
previously set length — so `response[1:1+length]` skips the **response code**,
which is a protocol field, not a hidraw report-ID prefix.

**READ-busy is statically exposed (log 81 `FUN_00002db8`).** On command byte
`0x05` the dispatcher sets `state+0x38` bit 1 (`(+0x38 & 0xfd) + 2`), calls the
synchronous READ `FUN_00003b64`, then clears bit 1 (`+0x38 & 0xfd`) and clears
the pending byte `+0x34`. Erase (`0x01`) and program (`0x51`) use bit 0 the same
way. `state+0x34` is the pending-command byte, cleared **after** the busy bit, so
`+0x34 == 0` is the strictly stronger completion signal. Bit 7 of `resp[1]` is
the unlock flag, bit 0 erase/program-busy.

### Bootloader READ scheduling — log 85 (race resolved)

**RAM layout, resolved by literal-pool value rather than by offset.** Three
distinct objects, cross-checked three ways (log 85 §1):

| base | contents |
|---|---|
| `T = 0x18011a8c` | `T+0` u32 target address (OUT `0x20`); `T+4..T+0x1003` the `0x1000`-byte PROGRAM source buffer (OUT `0x22`) |
| `S = 0x18012a8c` (`== T + 0x1000`) | `S+4..S+0x33` the **`0x30`-byte READ response buffer**; `S+0x34` pending; `S+0x35` error; `S+0x36` u16 length; `S+0x38` flags; `S+0x39` host scratch (written by OUT `0x7f`, read by nothing) |
| `W = 0x18010bd4` | `W+0` SysTick tick flag; `W+4` flash-operation request flag |

This explains the `0x30` READ cap: `S+4 + 0x30 == S+0x34`, so the cap is the
buffer size, not an arbitrary limit. It also shows the host has **no** write path
into the response buffer — OUT `0x22`'s last reachable byte is `T+0x1003 == S+3`.

**The post-EXEC scheduling race is PROVEN POSSIBLE.** Three instruction-level
facts chain:

1. the `0x1f` parser sets `S+0x34` and `W+4` (`str r0,[r1,#0x4]` at `0x0000397e`)
   and **never** `W+0`; it performs no flash access;
2. `FUN_00002db8` — the only code that sets the busy bit or performs the READ —
   is reachable only from `FUN_00003a7c`, whose loop body is guarded by `W+0`
   (`b 0x00003aa8` at `0x00003a7e` jumps straight to the `W+0` test, so a set
   `W+4` alone does nothing);
3. `W+0` is written **only** by the SysTick handler at `0x000048d0`
   (`movs r0,#1; ldr r1,[0x000048d8]; str r0,[r1,#0x0]; bx lr`), confirmed by an
   exhaustive scan of every image word equal to `0x18010bd4`.

So an accepted EXEC waits for the next SysTick tick before the READ starts.
`SYST_RVR` is the static constant `0x278d0 - 1 = 161999`, i.e. 162000 core
clocks; the wall time is *not* statically determined, because `FUN_00004910`
selects the core clock at runtime. The duration of one 48-byte flash transfer is
not recovered either. **No claim is made about how often the race is hit** — only
that it is possible. What does follow, and needs no timing at all, is structural:
a clear `state+0x38` bit 1 is also exactly what "not started yet" looks like, so
**polling bit 1 cannot sequence a READ**. Answering `0x8f` never advances the
service loop (`FUN_00003740` touches neither `W` nor `S+0x34`), so the following
`0xaa` can return the previous chunk's buffer.

> **Superseded by log 86.** An earlier version of this section said the race "is
> the default outcome", that the busy window is "orders of magnitude" shorter
> than a host round trip and lasts "microseconds", and that every chunk after the
> first "would have" been stale. All of those are withdrawn: log 85 itself
> records that neither the tick period in wall-clock terms nor the flash-transfer
> duration is statically determined. The defensible result is "proven possible".

**No observable completion marker exists.** Log 85 §5 searched for and ruled out
a generation counter, address echo, completion byte, and sequence number; `S+0x34`
is exposed by no query. Over-reading `S+0x34` through `0xaa` was examined and
**rejected**: it needs a set-length above `0x30` while a READ may still be
pending, and every such value either misaligns the flash engine (`FUN_00002f0c`
rejects a length with `& 3`, while `FUN_00003f08` ignores that return and spins)
or corrupts `S+0x36` into the responder's unclamped `memcpy` length. A locked
`1f 01`/`1f 51` probe *would* work — with bit 7 clear those handlers write
exactly `S+0x35 = 2` and reach no flash code (`0x000038f0`/`0x0000398e`) — but it
is not adopted, because it would require the backup tool to be able to construct
an execute-ERASE report.

### What closes it — corrected handshake, log 86

An earlier attempt at this (log 85 §6) was **unsound**, and log 86 records the
counterexample. It read the status *before* the data query and accepted any
sample differing from the baseline. But `FUN_00003b64` does **not** mask
interrupts (unlike `FUN_00003ab8`/`FUN_00003afc`, which bracket themselves with
`cpsid`/`cpsie`), so the `0xaa` responder can run while `S+4` is only partly
written — and a status taken *before* the sample does not exclude that, because a
whole READ can start and finish between two host reports with the fetch landing
inside it. The reviewer reproduced it: 24 new bytes followed by 24 baseline bytes,
accepted.

**Two pieces close it properly.**

*Bootstrap (new static evidence, log 86 §2).* The reset path
`0x000002f4` → `__scatterload` `0x00000148` → `__rt_entry` `0x000002d4` walks an
ARM `Region$$Table` at `0x0000cca0..0x0000ccd0`. Its third entry
(`dst=0x18011168 len=0x1a0c8 fn=0x000001fc`, whose handler begins
`movs r3,#0; movs r4,#0; movs r5,#0; movs r6,#0; … stm r1!,{r3-r6}` —
`__scatterload_zeroinit`) covers `T`, `S`, `S+0x34`, `S+0x36`, `S+0x38` and
`S+4`. So a freshly started bootloader has **no pending operation** and an
**all-zero response buffer**: the first baseline is *known*, not guessed. The
tool now refuses to start unless `S+4` reads `0x30` zero bytes.

*The rule (log 86 §3).* Per chunk: `0x21` length, `0x20` address, one `0x1f/0x05`;
then repeat `0xaa` (sample) **then** `0x8f` (status), and accept only when that
*following* status reports bit 1 clear and the sample differs from the baseline —
returning a **second** `0xaa`, not the sample. The proof: every write to `S+4`
happens while bit 1 is set (`FUN_00003b64` is called strictly between the stores
at `0x00002e0a` and `0x00002e1e`); `FUN_00003b64` takes its address at dispatch
time, so from the set-address report onward every episode writes `content(A)`,
while any earlier episode re-writes the previous chunk's content, which is the
baseline itself. A status with bit 1 clear therefore lies outside every transfer
interval; if the preceding sample differed from the baseline it cannot lie before
the first post-set-address episode, so it lies after it, and `S+4` holds the
complete `content(A)` from then on. No timing assumption, no unexposed state.

Re-arming the `0x1f` (needed because the parser drops an EXEC while `S+0x34` is
non-zero) stops once a sample differs from the baseline — otherwise it can lock
in step with the dispatch cadence and starve the busy-clear observation. That was
a liveness bug only; it produced refusals, never wrong acceptances.

Also verified and used: the status **error** byte *is* trustworthy for the EXEC's
own verdict, because it is written by the same interrupt-context parser that
consumed the EXEC report.

**Residual, not closed.** A foreign READ queued by another process but not yet
dispatched is invisible — `S+0x34` is exposed by no query and `S+4` still reads
zero. If it lands between this tool's bootstrap fetch and its first set-address,
it publishes an unrelated address's bytes. That is closed only by an operational
precondition the protocol cannot enforce: **nothing else may talk to the hidraw
node during the dump**. The handshake is also undecidable when a chunk's content
equals the previously proven buffer; it re-bases through an anchor of proven,
different content and aborts if none exists yet.

The Linux framing and split channel are validated live (log 90), and log 91
validates exactly one 48-byte execute-READ at `0x10000` plus the corrected
sample/status/confirm freshness handshake. It returned a complete `SN_FWIN`
header. Bytes `0x00..0x2b` match the preserved 1.00.58 image; the u32 field at
`0x2c` differs (`85 24 55 7d` installed versus `7a c1 75 5e` preserved), evidence
that the installed record payload differs. Multi-chunk sequencing, anchor
rebasing, repeated passes, and the full backup remain unvalidated. No
installed-firmware backup exists; backup-tool `--run` remains unauthorised.

**Correction to an earlier note:** the READ path *is* address-guarded. The `0x1f`
execute-trigger requires, for read (`opcode 5`), `0x10000 <= addr <= 0x7bfff` and
`0 < length <= 0x30`; erase (`1`) and program (`0x51`) additionally require the
`ASUSHIDFWU` unlock and the same address range. So USB READ covers only the
application region `[0x10000, 0x7c000)`, in ≤`0x30`-byte chunks — not the
bootloader region. (An earlier draft incorrectly stated the read handler had no
address guard; the guard lives in the execute-trigger, not in `FUN_00003b64`.)

Force-bootloader entry (resolved offline in log 87): the bootloader
`FUN_00002a44` checks RAM `0x20000ffc`
against magic `0x73207320`; if set, it stays in service mode and clears the flag.
Candidate B `FUN_180160d8` accepts a 64-byte application-interface payload whose
first seven bytes are `7b aa 41 53 55 53 aa`, writes the magic, and resets. The
official `peripheral_fwu_pro.exe` independently builds that exact payload for
selector 4 in the configured lower-case `m` mode: those seven bytes followed by
57 zero bytes. `HidInterruptHandle.dll` proves the Windows write prepends the
separate report-number byte; because application interface 1 declares no Report
ID, the equivalent Linux hidraw write is `00` plus the 64-byte payload (65 bytes,
SHA-256 `de6cfe16cc4639b2593bdfe86dade88e4e282a9ad6552b5684fbd35ef50506d8`).
A separate app command `0xb0` + `"reset"` performs a plain reboot without the
flag. `tool/enter_bootloader.py` implements only the exact allowlisted reset
frame, defaults to dry-run and requires two live flags. On 2026-09-02, after
explicit approval, it sent that frame exactly once to `/dev/hidraw7`; the
keyboard successfully re-enumerated from `0b05:1b7e` to `0b05:1b7f`. Live
bootloader entry is therefore validated (log 88). One bootloader status query
`0x8f` was later sent on FF01; its reply was not captured because the probe was
then listening on the wrong node. No other bootloader probe report and no flash
operation was sent (log 89).

This documents the exact read-only dump recipe on paper
(`notes/step5-recovery-plan.md`, Approach A). It has not been executed.

### Firmware modification roadmap (offline-first)

Now that both integrity mechanisms are recomputable, a modified image that passes
the checks we have read can be built entirely offline. The following steps are
ordered so that everything with device risk comes last, and nothing is flashed
until a verified recovery path exists.

1. **Offline image builder + round-trip verifier** (done, `tool/build_modified_image.py`,
   log 77, **conclusion superseded by log 84**). Applies byte patches to a copy of
   the preserved BIN, recomputes the SN_FWIN per-record CRC-sum (`record+0x8`) and
   the additive word-sum guards (`0x0fffc`, `0x7bffc`), and re-verifies the
   rebuilt image. Self-checked: recompute of the unmodified image is idempotent
   (matches the vendor method byte-for-byte), a naive one-byte patch fails, and
   the rebuilt image reproduces all four fields. The builder is now version-locked
   to the preserved 1.00.58 SHA-256, restricts patches to non-empty
   non-overlapping ranges inside Candidate B, refuses to overwrite an existing
   output, and re-validates the scatter-compressed stream after patching. Log 77's
   wording ("passes every integrity field the bootloader checks... proving the
   checks are live") overstated the result: it shows the fields are *reproducible
   offline*, not that a rebuilt image boots. The preserved BIN is never modified.
2. **Decode the remaining boot structures** — done (see "Boot container
   structures and boot gate" above, log 78). The boot-priority table has one
   populated slot (no A/B image scheme), the `+0x18` gate enables CRC checking,
   `FUN_00005240` checks the entry SP, and the container magics/backup copy are
   mapped. A Candidate-B data patch preserves all of these, so a CRC-valid
   rebuilt image also satisfies **the constraints we have read** — which are
   necessary but not known to be sufficient (`FUN_000029d4` and the top-level
   selected-entry comparison remain unresolved).
3. **Find Candidate B's true runtime entry** — done (see "Candidate B runtime
   entry and full boot chain" above, logs 79–80). Entry is `0x1800023a`
   (application main), called by Candidate A's `FUN_000002c8` after scatter-load.
4. **Reverse the bootloader write/erase/program protocol** — done, read-only
   (see "Bootloader write/erase/program protocol" above, log 81). Command bytes
   `0x01` erase / `0x05` read / `0x51` program, guarded to `[0x10000, 0x7c000)`,
   cross-checked against the updater strings. Documented on paper only; no
   command has been or should be sent.
5. **Recovery prerequisite — a verified backup of the installed 1.59 image**
   (plan written: `notes/step5-recovery-plan.md`; **not done**). This is the
   first step that reads *from the device*, so it is not offline. Two approaches:
   (A) USB read-back via the bootloader READ command — application region
   `[0x10000, 0x7c000)` only, base `0x10000` size `0x6c000`, ≤`0x30`
   bytes/transfer, no unlock needed (least invasive), see the wire framing above
   — or (B) a hardware 3.3 V SPI read of the external flash U5 (gold standard).
   Either way: ≥3 identical dumps, validate with
   `analyze_candidate_integrity.py --base 0x10000` and
   `analyze_boot_structures.py --base 0x10000`, store redundantly. No
   erase/program is ever issued during preservation, and nothing is flashed until
   this backup exists and verifies.

   Approach A covers only the application region, so it is **not** a complete
   device image; the bootloader region `[0x0, 0x10000)` is unreadable over USB.
   It is adequate for recovering app-region modifications only because that same
   range is the only range erase/program can reach. Only Approach B captures the
   bootloader.

Steps 1–4 are pure static analysis and are complete on paper only. Do not send
any step-4 command to the device or flash any image until step 5 exists.

### Documentation synchronization

After integrating earlier commit `87e22df`, the historical protocol notes were
reconciled with the later hardware, updater, firmware, and Ghidra evidence. The
original reverse-engineering guide now points here as authoritative, generic
STM32/DFU flashing recipes were removed, device-write tools are clearly
quarantined, missing-PCAP provenance is explicit, and obsolete claims about the
MCU, firmware availability, and SWD-only recovery were replaced. No historical raw
log was rewritten.

Evidence: `logs/46-documentation-synchronization-audit.txt`.

## Uncertain or superseded assumptions

- **USB backup via proprietary HID:** static bootloader analysis supports a
  proprietary HID READ operation for application region `0x10000..0x7bfff`.
  Commands use the FF01/EP6 node and replies use the distinct FF00/EP5 node.
  That split, the status/zero-buffer queries, and one fresh 48-byte READ at
  `0x10000` are live-validated (logs 90–91); no backup has been obtained.
- **Separate USB bootloader mode:** validated live in log 88. One authorized
  reset-only report caused re-enumeration as `0b05:1b7f`, bcdDevice `1.05`, with
  four HID interfaces. At that enumeration, interface 0 `/dev/hidraw6` was the
  FF01 command channel and interface 1 `/dev/hidraw7` was the FF00 response
  channel; both were 64-byte-IN/OUT and unnumbered. No physical boot-key method
  is known.
- **Older `0xFF32` report descriptor:** `keyboard/falchion-re/notes/report-desc-0.txt` contains a 63-byte input/output report on vendor page `0xFF32`, but its provenance is not recorded strongly enough to associate it with the currently enumerated interface 4. Current direct enumeration identifies interface 4 as page `0x59` with a different 327-byte descriptor. Treat the older mapping as historical/unverified, not a current fact.
- **Firmware version:** `bcdDevice 1.59` is verified; equating it with the version of every code image or external-flash region is an assumption.
- **Device-node permissions during log 89:** the owner granted user `dereck`
  read/write access to FF01 `/dev/hidraw6`; FF00 `/dev/hidraw7` remained
  root-only, and neither node had a reported holder. A sandboxed `ls` later
  reported both paths absent, but direct read-only enumeration proved the device
  was still in bootloader mode and the same paths still existed; the sandbox
  result was not a device result.

## Commands run

Exact command groups and their output files are recorded in `logs/COMMANDS.md`. Important device-facing commands were limited to:

```text
lsusb -d 0b05:1b7e -v    # standard read-only descriptor/status queries
dfu-util -l              # DFU enumeration only
tool/enter_bootloader.py --run --acknowledge-reset
                           # two separately authorized reset-only entries total
probe_bootloader.py --run --acknowledge-volatile-length
                           # first attempt stopped after 0x8f; corrected retry passed
probe_flash_read.py --run --acknowledge-one-read
                           # exactly one 48-byte execute-READ at 0x10000
```

All other probes read sysfs, udev metadata, package metadata, kernel logs, repository files, or the saved logs. `usbhid-dump` was invoked only with `--help`; it was never pointed at the keyboard.

## Recommended next steps

1. **Look for the exact installed release without touching the keyboard:** obtain the exact ASUS updater package for VID:PID `0b05:1b7e` / release 1.59, hash the original download, and extract/analyze it offline. This may yield a recovery candidate even if chip readout is unavailable. The official 1.00.58 image is now preserved locally but is not an installed-firmware backup.
2. **Decide whether to install fwupd:** installation changes the host, so ask first. Its value is limited because the current descriptors do not advertise DFU, but it can confirm whether a supported fwupd plugin recognizes the device.
3. **USB readback is validated for one chunk (logs 90–91).** The next device
   phase would be the full app-region backup: three passes, byte-for-byte and
   SHA-256 agreement, then structural validation. That remains a separate,
   longer live operation requiring explicit approval.
4. **Preserve passive protocol evidence:** if the earlier Windows PCAPs still
   exist, copy and hash them. Future captures should observe enumeration and
   Armoury Crate traffic without replaying commands. This may reveal the updater
   handshake and whether readback commands exist.
5. **Plan hardware preservation before modification:** acquire a suitable 3.3 V SPI programmer and MCU debug probe, map power/isolation requirements, and make verified read-only dumps. Never issue SPI Write Enable (`0x06`), Program, or Erase commands. Multiple identical reads plus SHA-256 comparison should be required before accepting a dump.
6. **Do not assume U5 is sufficient:** determine whether executable code also resides inside the SNC73270 and whether its debug/readout protection permits a non-destructive backup.
7. **Candidate B integrity is solved (logs 75–76) and the runtime entry is
   recovered (logs 79–80).** The SN_FWIN checksum is a sum of per-`0x10000`-chunk
   IEEE CRC-32 and the container guard is an additive word-sum, both recomputable
   offline. The remaining static targets are `FUN_000029d4` and the top-level
   comparison applied to the selected entry value before the jump; until those
   are resolved, the set of conditions a modified image must satisfy is known to
   be incomplete.
8. **Do not treat one block as a backup.** Log 91 validates one READ and its
   freshness proof only. No installed-firmware backup exists. Live use of
   `tool/backup_firmware.py` remains unauthorised pending a separate decision.

## Evidence integrity

`logs/SHA256SUMS` contains hashes for all raw `.txt` logs produced in this investigation.
