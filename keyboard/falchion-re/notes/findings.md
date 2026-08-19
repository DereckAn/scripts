# Falchion Ace HFX — Findings

Device: ROG Falchion Ace HFX 65% — USB `0b05:1b7e`
Host: CachyOS. Firmware `bcdDevice = 1.59`.

## Hardware
- MCU: **TODO (Phase 1.4 — open case)**
- Flash size: TODO
- SWD pads located: TODO (yes/no, where)
- HE sensing IC(s): TODO

## USB (Phase 1.1 / 1.2)
- 5 interfaces total (`bNumInterfaces = 5`), all bInterfaceClass 3 (HID).
- Vendor config-channel candidates (node numbers reshuffle on every replug — match by usage page, not hidrawN):

| iface | usage page | reports | endpoints | file |
|-------|-----------|---------|-----------|------|
| 1.0   | 0x0501 (kbd) | 8B IN | 0x81 | — boot keyboard |
| 1.1   | **0xFF00** | 64B IN + 64B OUT, no report ID | 0x85 IN / 0x0d OUT | report-desc-ff00.txt |
| 1.2   | 0x0C (consumer) | 21B IN | 0x8c | — media keys |
| 1.3   | 0x0501 (kbd) | 19B IN | 0x8e | — |
| 1.4   | **0xFF32** | Report ID 2, 63B IN + 63B OUT | 0x0f OUT | report-desc-0.txt |

- Report size: 64 bytes on both vendor channels.
- DFU available: **NO** — `dfu-util -l` finds nothing; no USB bootloader exposed.
  - Implication: Phase 2.1 chip dump via DFU is out. Backup path = ASUS updater extraction (2.2) and/or SWD (2.3).

## Access (Phase 0.3)
- udev rule `/etc/udev/rules.d/99-asus-keyboard.rules` sets MODE=0666 for 0b05:1b7e (usb + hidraw). Verified all Falchion hidraw nodes are crw-rw-rw-.

## Protocol
| Opcode | Meaning | Payload layout | Verified? |
|--------|---------|----------------|-----------|
|        |         |                |           |

## Open questions
- Which vendor iface (0xFF00 vs 0xFF32) does Armoury Crate use? → Phase 3 capture decides.
- Are the Fn keys locked in UI or firmware? → Phase 3.6.
