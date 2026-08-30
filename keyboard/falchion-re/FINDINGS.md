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

This does **not** prove that USB backup is impossible. The keyboard could have a separate bootloader mode or a proprietary vendor-HID readback command. Neither was tested because entering another mode may reset/re-enumerate the device, and undocumented vendor commands could change configuration or firmware. The current evidence therefore supports: **standard USB backup unavailable; proprietary/bootloader USB backup unresolved**.

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

- Candidate payload A is described by flash address `0x60011000`, length
  `0x58ac`, and stored value `0x5e75c17a`. Standard IEEE CRC-32 over the mapped
  file bytes matches that value exactly.
- Candidate payload B appears to use address `0x60021000`, length `0x1e754`, and
  stored value `0x1a76c116`, but standard CRC-32 over that apparent range is
  `0x60c95a7b`. No natural prefix through `0x40000` matches the stored value.
  The record interpretation or checksum process is therefore unresolved.
- Terminal values `0xfb665ae3` (present in both bootloader copies) and
  `0x5d27c5a9` do not match the common CRC-32 variants over obvious enclosing
  ranges tested.
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
| `0x1801c37c` | `0x1c37c` | `0x3d37c` | per-layout/per-profile key-index map |
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
`logs/65-ghidra-candidate-b-rebased-key-policy-report.txt`. Reproducible decoder:
`tool/analyze_candidate_b_tables.py`.

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
source from `0x00` through `0xbc` reaches the same runtime-table translation.
This agrees with the historical observation that a reserved remap could be
echoed without becoming effective.

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
and per-key index mapping at `0x1801c37c`.

Evidence: `logs/47-ghidra-candidate-b-opcode-search.txt` through
`logs/54-ghidra-protocol-labels.txt`. Reproducible reports and conservative label
script are under `ghidra/scripts/`. All work was offline; no USB command was sent.

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

- **USB backup via proprietary HID:** unresolved. Interface 1 can transport 64-byte vendor reports, but no safe claim about flash-read commands can be made from descriptors alone.
- **Separate USB bootloader mode:** unresolved. No key combination or detach command was attempted.
- **Older `0xFF32` report descriptor:** `keyboard/falchion-re/notes/report-desc-0.txt` contains a 63-byte input/output report on vendor page `0xFF32`, but its provenance is not recorded strongly enough to associate it with the currently enumerated interface 4. Current direct enumeration identifies interface 4 as page `0x59` with a different 327-byte descriptor. Treat the older mapping as historical/unverified, not a current fact.
- **Firmware version:** `bcdDevice 1.59` is verified; equating it with the version of every code image or external-flash region is an assumption.
- **Current device-node permissions:** not verified because `/dev/hidraw*` and `/dev/bus/usb/*` are hidden inside the managed sandbox. No permission changes were made. Prior notes claiming mode `0666` are historical, not re-verified here.

## Commands run

Exact command groups and their output files are recorded in `logs/COMMANDS.md`. Important device-facing commands were limited to:

```text
lsusb -d 0b05:1b7e -v    # standard read-only descriptor/status queries
dfu-util -l              # DFU enumeration only
```

All other probes read sysfs, udev metadata, package metadata, kernel logs, repository files, or the saved logs. `usbhid-dump` was invoked only with `--help`; it was never pointed at the keyboard.

## Recommended next steps

1. **Look for the exact installed release without touching the keyboard:** obtain the exact ASUS updater package for VID:PID `0b05:1b7e` / release 1.59, hash the original download, and extract/analyze it offline. This may yield a recovery candidate even if chip readout is unavailable. The official 1.00.58 image is now preserved locally but is not an installed-firmware backup.
2. **Decide whether to install fwupd:** installation changes the host, so ask first. Its value is limited because the current descriptors do not advertise DFU, but it can confirm whether a supported fwupd plugin recognizes the device.
3. **Research bootloader entry offline first:** the updater establishes PID `1b7f`
   and contains a jump-to-bootloader path, but its exact command and any physical
   boot-key method remain unresolved. Do not send a detach/vendor command merely
   to experiment.
4. **Preserve passive protocol evidence:** if the earlier Windows PCAPs still
   exist, copy and hash them. Future captures should observe enumeration and
   Armoury Crate traffic without replaying commands. This may reveal the updater
   handshake and whether readback commands exist.
5. **Plan hardware preservation before modification:** acquire a suitable 3.3 V SPI programmer and MCU debug probe, map power/isolation requirements, and make verified read-only dumps. Never issue SPI Write Enable (`0x06`), Program, or Erase commands. Multiple identical reads plus SHA-256 comparison should be required before accepting a dump.
6. **Do not assume U5 is sufficient:** determine whether executable code also resides inside the SNC73270 and whether its debug/readout protection permits a non-destructive backup.
7. **Continue from the corrected Candidate B mapping:** decode the complete
   `0x1801c37c` layout/profile map and relate every translation-table value to
   wire source/target semantics. Keep Candidate B's true entry/call path and
   integrity calculation separate—they remain unresolved.

## Evidence integrity

`logs/SHA256SUMS` contains hashes for all raw `.txt` logs produced in this investigation.
