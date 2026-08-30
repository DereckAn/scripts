# ROG Falchion Ace HFX — protocol research summary

Last synchronized: 2026-08-29

The authoritative project status is [`../FINDINGS.md`](../FINDINGS.md). This file
summarizes the earlier Windows/Armoury Crate protocol work and reconciles it with
the later USB, hardware, updater, firmware, and Ghidra analysis.

## Evidence levels

- **Current verified:** reproduced from the preserved artifacts or current raw
  logs under `../logs/`.
- **Historical hardware observation:** recorded during earlier device experiments,
  but the cited PCAP files are not present in this repository and do not appear in
  reachable Git history.
- **Unresolved:** plausible, but not established strongly enough to rely on for a
  firmware modification or recovery procedure.

The decoded Armoury Crate profile snapshots, key-map notes, protocol notes, and
PowerShell tools are preserved. Missing raw captures mean exact packet counts and
behavioral A/B results cannot currently be independently re-derived.

## Current answer

- Normal mode is `0b05:1b7e`, USB `bcdDevice 1.59`, ASUS model M605.
- No standard DFU interface or standard USB firmware-upload path is exposed in
  normal mode.
- A proprietary ASUS updater exists and expects bootloader PID `0b05:1b7f`, but
  no updater executable has been run and its jump command has not been replayed.
- The official ASUS Gear package contains firmware `M605_V01_00_58.bin`. It is an
  authentic older vendor image, not a backup of the installed 1.59 firmware.
- No exact installed-firmware dump, U5 dump, or proven recovery workflow exists.
- Offline firmware reverse engineering has started. Modified firmware must not be
  flashed until integrity fields, update regions, downgrade behavior, and recovery
  are understood.

## Hardware

User-supplied physical markings:

- main MCU: SONiX SNC73270;
- U5: Zbit ZB25VQ32BTIG SPI NOR, 32 Mbit / 4,194,304 bytes;
- expected U5 JEDEC ID: `5E 40 16`;
- U7: `DIO322 2403 2F3`, likely a USB signal switch;
- U12: `C3NC V0006`, unidentified.

No SWD probe, Bus Pirate, or SPI programmer is connected. The SONiX SNC7320
family documentation describes dual Cortex-M3 cores, SWD, shared SRAM/mailbox RAM,
memory remapping, and external SPI-NOR XIP. This does not prove that U5 alone holds
all installed executable state.

`Fn + Caps` performs a settings factory reset. It is not firmware recovery and
cannot repair a failed flash or bootloader.

## USB

Current read-only enumeration verifies five HID interfaces:

| iface | usage | reports/endpoints | current interpretation |
|---|---|---|---|
| 0 | keyboard | 8-byte IN, `0x81` | boot keyboard |
| 1 | `0xFF00` | 64-byte IN/OUT, `0x85` / `0x0d` | proprietary config/updater transport candidate |
| 2 | consumer/system plus `0xFFC0` | 21-byte maximum IN, `0x8c` | media/system/vendor events |
| 3 | keyboard | 19-byte IN, `0x8e` | NKRO keyboard |
| 4 | HID page `0x59` | feature reports and OUT `0x0f` | LampArray / lighting; unbound on Linux |

The older 39-byte `report-desc-0.txt` on page `0xFF32` does not match any current
Falchion interface and must not be attributed to interface 4. The prior `MODE=0666`
udev claim is historical and was not re-verified in the managed environment.

## Preserved official firmware

- Official ZIP: `../vendor/asus/original/ROG_FALCHION_ACE_HFX.zip`
- Firmware: `../dumps/vendor/M605_V01_00_58.bin`
- Firmware size: 507,904 bytes (`0x7c000`)
- Firmware SHA-256:
  `6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d`
- Normal PID: `1b7e`; configured bootloader PID: `1b7f`
- Updater regions: 64 KiB bootloader plus 432 KiB application, 4 KiB pages

The image contains SONiX headers, Cortex-M Thumb code, a duplicated bootloader,
two application payload candidates, and an executable RAM image. Candidate A's
CRC-32 is understood; Candidate B's integrity field remains unresolved. See the
authoritative findings and `../ghidra/README.md` for the current memory map.

## Earlier protocol observations

Interface 1 / page `0xFF00` was historically used with a leading report-ID
placeholder followed by a 64-byte payload. Recorded commands include:

| bytes | recorded meaning | evidence status |
|---|---|---|
| `12 00` | version query returning 1.59 | historical capture/device observation |
| `51 21 ...` | live Fn-layer binding change | historical device observation |
| `50 55` | persistent configuration commit | historical capture/device observation |

A controlled historical A/B reportedly sent equivalent `51 21` commands to a
reserved and an ordinary Fn-layer source. The ordinary binding changed while the
reserved one remained unchanged, even though both responses echoed their request
headers. Armoury Crate's UI was also reported to block reserved combinations
without sending a packet.

This is strong prior evidence for both a UI restriction and device-side filtering,
but the raw PCAP evidence is missing. Treat it as a historical observation pending
capture preservation or offline identification of the same check in firmware.

Offline Candidate B analysis now independently identifies that device-side
check. `VendorHID_CommandDispatcher` at `0x1fbe` accepts `0x51/0x21` sources
through `0xbc`, maps the source through an effective-KBID-selected record-index
window, translates ordinary targets through a separate 189-byte table, updates
a per-key record, and builds an echoed 64-byte response. It does not consult the
reserved-key list on this path. The effective selector is `0`, `1`, or `2`; the
three 189-byte source windows advance by `0x86` and therefore overlap by 55
bytes. A separate three-row scan-position table at `0x1801c50e` uses a `0x100`
stride.

`IsKeyUnsupportedForLayer` at Candidate B offset `0x1f6e` (runtime
`0x18001f6e`) separately searches a 6-entry list for
base selectors and a 57-entry list for Fn/other selectors. Configuration-load
code skips matching mappings and contains the diagnostic strings `R_NSK_M` and
`R_NSK_FnM`. This statically explains how a command can be echoed but later have
no effective Fn binding. Candidate B is now strongly mapped at runtime base
`0x18000000`, making the list at `0x1801c810` embedded slice offset `0x1c810`
(full BIN `0x3d810`). All 63 entries are recovered; the 57-entry Fn list closely
matches the manual's locked function families.

An echoed response is not proof that a change took effect. Ordinary target IDs
`0x00..0xbc` now have a recovered static translation rule, but earlier live tests
reported inconsistent effects and the active unit's effective KBID is not known.

### Preservation safety

Do not replay these commands during firmware preservation. `51 21` changes live
device state even without `50 55`; absence of a persistent commit does not make it
read-only or risk-free. `50 55`, updater commands, bootloader entry, erase, program,
and reset operations remain prohibited unless explicitly planned and approved.

## Current status by phase

| phase | current status |
|---|---|
| USB identification | complete for normal mode and both physical connectors |
| Hardware identification | main MCU and external flash marked; pads/signals not mapped |
| Exact installed backup | not obtained |
| Official recovery/reference image | authentic 1.00.58 image preserved; downgrade/recovery unproven |
| Protocol reverse engineering | useful historical mapping exists; raw PCAPs missing; several fields unresolved |
| Firmware reverse engineering | started offline in Ghidra; no device write performed |
| Firmware modification/flash | blocked by unresolved integrity, loading, and recovery questions |
| Cross-platform tool | not started; write-capable behavior must remain gated |

## Open questions

- Can the exact installed 1.59 package be obtained and analyzed offline?
- Does either proprietary HID mode support firmware readback?
- What exact command enters PID `1b7f`, and is there a physical recovery method?
- What does U5 contain on this unit, and can it be read repeatedly without powering
  or driving the board incorrectly?
- Does SNC73270 SWD permit read-only access, and which probe/software supports it?
- What is Candidate B's true entry/call path and integrity calculation? Its
  runtime base is now strongly supported as `0x18000000`.
- Which effective KBID (`0`, `1`, or `2`) does this exact Falchion Ace HFX unit
  select at runtime? Determining it from USB would require a separately reviewed
  read-only method; no vendor query has been sent.
- What runtime behavior does frequent record index `0x4b` represent: a dummy,
  fallback, or valid shared record?
- Which loader function verifies Candidate B and transfers control to its true
  entry point, and how is integrity value `0x1a76c116` calculated?
- Can the missing PCAP files be recovered from the Windows capture system and
  preserved with hashes?

## Related files

- [`protocol.md`](protocol.md): detailed historical command/protocol notebook
- [`key-matrix.md`](key-matrix.md): key-index and Armoury Crate profile mapping
- [`../FINDINGS.md`](../FINDINGS.md): authoritative current investigation status
- [`../vendor/asus/ARTIFACTS.md`](../vendor/asus/ARTIFACTS.md): preserved artifact manifest
- [`../ghidra/README.md`](../ghidra/README.md): current offline Ghidra workspace
