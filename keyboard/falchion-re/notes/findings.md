# Falchion Ace HFX — Findings

Device: ROG Falchion Ace HFX 65% — USB `0b05:1b7e`
Host: CachyOS. Firmware `bcdDevice = 1.59`.
Capture host: Windows 11 LTSC box (Phase 3).

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
| 1.1   | **0xFF00** | 64B IN + 64B OUT, no report ID | 0x85 IN / 0x0d OUT | report-desc-ff00.txt — **CONFIRMED as the AC channel**, see protocol.md |
| 1.2   | 0x0C top-level; **COL03 = 0xFFC0** | 21B IN, input-only | 0x8c | media keys + vendor event channel |
| 1.3   | 0x0501 (kbd) | 19B IN | 0x8e | — |
| 1.4   | `0x0059` (LampArray) | 51B feature reports only | 0x0f OUT | ~~0xFF32~~ — earlier entry was misattributed, see protocol.md §2 |

- Report size: 64 bytes on both vendor channels.
- DFU available: **NO** — `dfu-util -l` finds nothing; no USB bootloader exposed.
  - Implication: Phase 2.1 chip dump via DFU is out. Backup path = ASUS updater extraction (2.2) and/or SWD (2.3).

### Windows view (cross-check, 2026-08-27)
Windows enumerates the same 5 interfaces and independently agrees on which are vendor-defined:

```
HID\VID_0B05&PID_1B7E&MI_01            HID-compliant vendor-defined device   <- 0xFF00
HID\VID_0B05&PID_1B7E&MI_04            HID-compliant device                  <- 0xFF32
HID\VID_0B05&PID_1B7E&MI_02&COL03      HID-compliant vendor-defined device   <- 3rd vendor collection
HID\VID_0B05&PID_1B7E&MI_00 / MI_03    HID Keyboard Device
HID\VID_0B05&PID_1B7E&MI_02&COL01/02   consumer control / system controller
HID\VID_0B05&PID_1B7E&MI_02&COL04      ROG FALCHION ACE HFX (mouse)
```

Note iface 2 is multi-collection on Windows (COL01–COL04); Linux `lsusb` reports only its
top-level usage page (0x0C). COL03 is a third vendor channel not obvious from the Linux side.

## Access (Phase 0.3)
- udev rule `/etc/udev/rules.d/99-asus-keyboard.rules` sets MODE=0666 for 0b05:1b7e (usb + hidraw). Verified all Falchion hidraw nodes are crw-rw-rw-.

---

## Phase 3 environment (Windows capture host) — 2026-08-27

| Component | Version | Notes |
|---|---|---|
| Wireshark | 4.6.8 x64 | must be launched **as Administrator** or USBPcap ifaces are hidden |
| USBPcap | 1.5.4.0 | `USBPcap.sys` loaded, service Running |
| Npcap | 1.88 | bundled with Wireshark |
| Armoury Crate | 5.9.14 | Microsoft Store package `B9ECED6F.ArmouryCrate` |
| ROG FALCHION ACE HFX module | 4.03.70 | AC per-device plugin |
| ASUS Keyboard HAL | 1.2.97.0 | `AacKbHal_x64.dll` — implements the HID protocol |

Gotcha: a non-elevated `dumpcap -D` lists only Ethernet/loopback. Elevation is what exposes
the `USBPcapN` interfaces. Not a broken install.

---

## AC on-disk artifacts (free intel, no capture needed)

Installing Armoury Crate dumped the keyboard's whole config to disk. Encoding is
**base64 → URL-encoded (percent) → JSON**.

| Path | What |
|---|---|
| `C:\ProgramData\ASUS\Framework\keyboard\ROG FALCHION ACE HFX\fp_3_config_024080600167.xml` | full profile 3: 136 key entries + lighting / performance / lever |
| `...\config_024080600167.xml` | profile list — 6 firmware profiles (Default + 1–5), all `FIRMWARE_PROFILE`, no SW profiles |
| `C:\ProgramData\ASUS\ArmourySDK\Keyboard\ROG FALCHION ACE HFX\024080600167\Key\3\*.xml` | per-key XML, one file per `source_key` (UTF-16LE) |
| `C:\ProgramData\ASUS\ROG Live Service\DeviceContent\0B051B7E\0B051B7E.csv` | 24x11 LED grid, phys mm coords, `lamp_id` + `virtual_key` per LED |
| `C:\Program Files\ASUS\Aac_Keyboard\AacKbHal_x64.dll` | 1.5 MB, Nov 2024 — builds the actual HID reports |

`024080600167` = AC's model/config ID for this board. `device key="7038"` (= 0x1B7E) and
`device_type key="2"` (keyboard) appear in the XML wrappers.

Decode one-liner (PowerShell):

```powershell
$b64  = ([xml](Get-Content $f -Raw)).root.device_type.device.function.file_data
$json = [uri]::UnescapeDataString([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64)))
```

### Per-key record shape

Top-level keys of the profile blob: `nationCode`, `button`, `lighting`, `performance`, `lever`.
`button.keyboardButton` holds 136 entries named `keyfunction_<idx>_<grp>`:

```json
"keyfunction_0_1":  {"selectedmode":"0","defaultKey":"0",  "keydata_1":"-1","keydata_2":"-1","keydata_3":"-1",
                     "button":{"source_key":"0","trigger_type":0,
                               "normal":{"button_function":"0","target_key":"0","actuation":10}}}

"keyfunction_50_1": {"selectedmode":"7","defaultKey":"306","keydata_1":"-1","keydata_2":"-1","keydata_3":"-1",
                     "button":{"source_key":"306","trigger_type":0,
                               "normal":{"button_function":7,"target_key":"306","actuation":10}}}
```

Observed so far (see **[key-matrix.md](key-matrix.md)** for the full decode):
- Entry name is `keyfunction_<col>_<row>`; `col` < 50 = base layer, `col+50` = Fn layer.
- **`source_key = (row << 8) | col`** — verified on 135/136 entries. Sole exception is
  row 1 / col 0, which stores `0x0000` instead of `0x0100`.
- 68 keys, each with both a base and an Fn entry (68 + 68 = 136). Populated matrix
  positions are 68 of a 7x12 grid.
- At defaults `source_key == defaultKey == target_key` everywhere; `actuation: 10`,
  `trigger_type: 0`, `keydata_1..3: -1` on every entry.
- `button_function` is a JSON string on base entries and a JSON int on Fn entries — a
  parser must tolerate both.

**Superseded:** an earlier reading of this file guessed that `selectedmode == 7` flagged
locked keys. It does not — all 68 Fn-layer entries carry mode 7 uniformly, including
freely-remappable ones. Mode 7 just means "Fn layer". A defaults-only dump does not reveal
the lock.

**Next, and it needs no capture:** change one key in AC, re-decode
`fp_3_config_024080600167.xml`, and diff against `ac-profile3-decoded.json`. The entry that
changes gives that key's true matrix coordinate. Then try the same against a locked Fn key —
if the file is untouched, the lock is client-side and Phase 3.6 passes. Details in
key-matrix.md.

---

## Protocol
| Opcode | Meaning | Payload layout | Verified? |
|--------|---------|----------------|-----------|
|        |         |                |           |

## Open questions
- ~~Which vendor iface does Armoury Crate use?~~ **Solved: iface 1, usage page 0xFF00.** Confirmed by the device table in `AacKbHal_x64.dll` and by live `HidP_GetCaps`. See protocol.md §1.
- Are the Fn keys locked in UI or firmware? → Phase 3.6.
- ~~What is the `source_key` encoding?~~ **Solved:** `(row << 8) | col`. See key-matrix.md.
- Does matrix row-major order match ascending `lamp_id`? The key-name table in key-matrix.md assumes so and is unverified.
- Why does row 1 / col 0 store `source_key = 0x0000` instead of `0x0100`?
- What are `actuation` units — raw ADC counts, 0.1 mm steps, or a 0–40 index?
- ~~Does `AacKbHal_x64.dll` expose report builders as named exports?~~ **No** — COM in-proc server, 5 stock exports only. But its `OutputDebugString` logs leak the full method list; see protocol.md §3.
- What are the actual command opcodes? → needs the capture. protocol.md §4.
- Is `FF AA` really the device NAK prefix? → inferred from log strings, unverified.
- `lever` top-level key — the volume/scroll wheel? Not yet examined.
