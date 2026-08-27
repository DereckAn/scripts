# ROG Falchion Ace HFX — findings

Device: `0b05:1b7e` · ASUS model **M605** · firmware `bcdDevice = 1.59` · 68 keys, 65% layout
HAL class: **`AacM605Function`** (model code M605 confirmed from the official manual title)
Linux host: CachyOS · Windows capture host: Windows 11 LTSC
Last updated: 2026-08-27

**Full protocol spec: [protocol.md](protocol.md).** This file is the summary and status.

---

## THE ANSWER

The original goal was to unlock the Fn keys ASUS won't let you remap.

> **There are two independent locks, and both are real.**
>
> 1. **Armoury Crate UI lock** — refuses client-side and sends nothing on the wire.
> 2. **Firmware lock** — the keyboard *also* filters reserved keys. It accepts the packet,
>    echoes the header back, and silently discards the write.
>
> **Unlocking the reserved Fn keys requires Phase 4 (firmware modification).** There is no
> protocol-level route; this was tested directly, not inferred.
>
> Everything *else* is reachable today with no firmware work: all non-reserved keys on both
> layers, actuation, rapid trigger, dead zone, speed tap, profiles, polling rate, lighting.
> That is the large majority of what Armoury Crate does.

### How it was proven

A controlled A/B. Two hand-crafted commands differing **only in the source-index byte**, sent
back to back via `tools/send.ps1`, neither committed to flash, no Armoury Crate interaction
in between:

```
51 21 11 9F 09 00 0A 00    src 17 = Q  (reserved: Fn+Q = Play/Pause)  -> ACK, NO EFFECT
51 21 18 9F 09 00 0A 00    src 24 = I  (not reserved)                 -> ACK, APPLIED (vk 0x38)
```

Same result for `src 2` (the `1` key, reserved as F1): ACKed, `Fn+1` stayed F1, while `src 14`
in the same batch applied normally.

Supporting evidence for the UI lock, from `captures/01-first-launch.pcapng`: across a 403-second
session the vendor OUT endpoint carried **exactly 19 commands**, all accounted for as handshake,
three settings writes, and their commits. Every remap attempt Armoury Crate refused with a
dialog produced **zero bytes** on the wire.

### The trap this exposed

**The device echoes the request header verbatim even when it discards the write.** The echo is
a receipt of delivery, not of effect. `FF AA` never appeared in any test — the firmware does
not reject reserved-key remaps, it silently ignores them.

Any tool built on this protocol **must verify by readback or by observing the key.** Trusting
the ACK will produce a tool that silently does nothing.

---

## Hardware

- MCU: **unknown** — case never opened.
- Flash size, SWD pads, HE sensing ICs: unknown.
- **No DFU interface.** `dfu-util -l` finds nothing; no USB bootloader is exposed.
  Implication: a chip dump via DFU is out. Any Phase 4 backup path is ASUS updater extraction
  and/or SWD.
- **Hardware factory reset exists:** `Fn + Caps`, hold until the LEDs blink green. Documented
  in the manual. This is the recovery path that does not require Armoury Crate.

## USB

5 interfaces, all `bInterfaceClass 3` (HID). Verified from both `lsusb` on Linux and
`HidP_GetCaps` on Windows:

| iface | usage page | reports | role |
|---|---|---|---|
| 0 | keyboard | 8B IN, EP 0x81 | boot keyboard |
| **1** | **0xFF00** | 64B IN + 64B OUT, no Report ID, EP 0x85 / 0x0d | **config channel** |
| 2 | 0x0C top-level; COL03 = **0xFFC0** | 21B IN, input-only | media keys + vendor event channel |
| 3 | keyboard | 19B IN, EP 0x8e | NKRO |
| 4 | `0x0059` LampArray | 51B feature only | Windows Dynamic Lighting |

> **Correction to an earlier note.** Interface 4 was originally recorded as usage page
> `0xFF32`, Report ID 2, 63B in/out, citing `report-desc-0.txt`. That does not hold:
> `report-desc-0.txt` is 39 bytes and **no** interface on this device has
> `wDescriptorLength = 39` (they are 68, 34, 182, 23, 327). Interface 4's descriptor is 327
> bytes and Windows reports it as `0x0059` with feature reports only. `report-desc-0.txt`
> decodes cleanly on its own, so it evidently **belongs to a different device** — the Linux
> box also has a ROG OMNI RECEIVER attached. Re-dump it matching by usage page, not `hidrawN`.

Linux access: udev rule `/etc/udev/rules.d/99-asus-keyboard.rules` sets `MODE=0666` for
`0b05:1b7e` (usb + hidraw). Verified.

---

## Phase 2 — backup and recovery: BLOCKED ON HARDWARE

Investigated 2026-08-27. Conclusion first: **Phase 2 cannot produce a working recovery path
without an SWD programmer.** A firmware image you have no way to write is not a safety net.

### 2.1 — dump from the chip: NOT POSSIBLE

- No DFU interface. `dfu-util -l` finds nothing.
- `AacKbHal_x64.dll` contains **no bootloader / DFU / ISP / erase / flash entry points** for
  keyboards (searched its full string table). Firmware update for this device is handled by
  some separate ASUS tool, not the HAL.
- `deviceinfo.ini` does carry a **`BootloaderMode=false`** flag for `0B051B7E`, so a bootloader
  state exists and ASUS software tracks it — but nothing found so far can trigger entry into it.

### 2.2 — official firmware image: NOT PUBLISHED

ASUS's support page for this keyboard offers **no standalone firmware file**. Downloads are:

| item | version | size |
|---|---|---|
| Armoury Crate Gear – ROG Falchion Ace HFX | 1.0.1.15 | 227.4 MB |
| Armoury Crate & Aura Creator Installer | 3.3.6.0 | 2.2 MB |
| Armoury Crate Uninstall Tool | 2.3.7.0 | 1.21 MB |
| Gear Link Log Tool | 1.0.0.3 | 21 KB |

Firmware ships *inside* Armoury Crate. Confirmed nothing is staged locally: the installed AC
Store package contains no firmware-shaped files, and neither do the RLS / Update caches. The
one remaining candidate is the **227 MB device-specific "Armoury Crate Gear" package** —
unexamined.

For reference, ASUS *does* ship firmware in these packages for other devices — e.g.
`...\ArmouryDevice\dll\ShareFromArmouryIII\Mouse\ROG Strix Impact\Upgrade_P303\FW.hex`. So the
pattern exists; it just isn't present for this keyboard.

### 2.2b — Gear Link KB Companion 3.1.0.3: searched, NO FIRMWARE

Installed 2026-08-27 specifically to check for a firmware blob. Package is InstallShield
(`ISc(` cabs — 7-Zip cannot open them, and `setup.exe /extract_all` / `/stage_only` return 0
but extract nothing; only a real install unpacks it).

Result: **no firmware image anywhere in the package.** `ArmouryLiveUpdate.exe`,
`ArmouryUpdate.exe` and `AsusLiveUpdateDeEncrypt.dll` contain only certificate-authority URLs
— no firmware download endpoint and no embedded image. They also live under `.../ROGMS/`
(ROG mouse), so they are generic.

What it *did* yield, useful for other reasons:

| artifact | value |
|---|---|
| `C:\Program Files (x86)\ASUS\ArmouryDevice\View\7038\` | **the complete Armoury Crate UI bundle for this device** (`7038` = `0x1B7E`), 514 files / 24 MB of webpack JS + all language XML |
| `C:\Program Files (x86)\ASUS\Gear Link\KB\GearLink_KBApi\GearLink_KBApi.dll` | 763 KB **managed .NET assembly** — the keyboard API layer. Decompilable, but needs the .NET **SDK** (only the runtime is installed, so `dotnet tool install -g ilspycmd` fails). |

**The UI lock, located in source.** `1509-bundle-bfb3b.js` gates key editing on:

```js
function(e){ try { return !m.includes(e) } catch(e) { return !1 } }(j)
```

If the key is in `m`, the UI renders `row_1894` — *"This key combination is already assigned
to a fixed function and cannot be changed"* — instead of the assignment control. `m` is not a
literal array in the bundle, so the list itself is either fetched from device data or built at
runtime; not yet extracted.

Note this is only the **UI** lock. It is independent of the firmware lock proven in the
VERDICT section, which no amount of UI patching would bypass.

### 2.3 — SWD programmer: NOT ACQUIRED. This is the real blocker.

Because there is no DFU and no published image, **SWD is the only route to both a dump and a
restore.** Needed:

- ST-Link V2 clone (~$5-8) or a Raspberry Pi Pico flashed as a debug probe
- `openocd`
- The case opened to locate SWD pads and identify the MCU (Phase 1.4, also still undone)

Even with SWD, a dump may return all `0x00`/`0xFF` if read-out protection is enabled — that
outcome is unknown until tried.

### What this means for Phase 4

**Phase 4 currently has no recovery path.** Do not start it until 2.3 is resolved. The
existing hardware factory reset (`Fn + Caps`) restores *settings*, not firmware — it will not
save a bad flash.

## Status by phase

| phase | status |
|---|---|
| 0 — setup | done, both hosts |
| 1 — identify hardware | done except MCU part number (needs case opened) |
| 2 — backup / recovery | **not done.** No DFU, so no chip dump. Firmware image not extracted. |
| 3 — protocol RE | **done.** Transport, handshake, remap command, source indices all verified. Target index encoding open. |
| 3.6 — the key test | **done. Firmware lock confirmed.** |
| 4 — firmware modification | not started, and deliberately deferred |
| 5 — build the tool | not started; unblocked for the non-reserved feature set |

**Phase 2 is now the gating item if Phase 4 is ever attempted.** There is no verified firmware
backup and no exposed bootloader, so Phase 4 currently has no recovery path beyond SWD. Do not
start Phase 4 without resolving that.

---

## Open questions

- **Target index encoding** — the one real blocker for a complete remap implementation.
  Contradictory results: `tgt 4` produced `4` on one source key and `3` on another. See
  protocol.md §4 for the clean experiment that would settle it.
- **LEAD: Gear Link (`gearlink.asus.com`) is a browser-based config tool** — it must drive the keyboard over WebHID, so its JavaScript likely contains the full protocol in readable form, including the target-index encoding. Cheapest route to finishing the spec.
- Opcodes for actuation, rapid trigger, dead zone, speed tap, profile, polling rate — all have
  known HAL method names, none captured yet.
- What `51 22` does (seen once with `C8` = 200).
- Whether base-layer writes use a different subcommand than `51 21`.
- Meaning of the `9F` constant in byte 3 — never varied.
- How the config file's `(row, col)` space relates to the wire's flat key index.
- `0xFFC0` event-channel payload format.
- MCU part number, flash size, SWD pad locations.
- Why config entry row 1 / col 0 stores `source_key = 0x0000` instead of `0x0100`.

## Disproved — do not retry

- **"`mode == 7` marks a locked key."** False. All 68 Fn-layer entries carry mode 7 uniformly,
  including freely-remappable ones. It means "Fn-layer default".
- **"Matrix row-major order matches ascending `lamp_id` in the LED CSV."** False. The key-name
  table it produced was wrong — M is at `row 4 / col 5`, not where that predicted.
- **"No `FF AA` observed means the lock is UI-only."** False, and the reasoning was circular:
  no rejectable command had been sent, so the absence of a NAK carried no information.

---

## Files

```
notes/
  findings.md                  this file — summary and status
  protocol.md                  full protocol spec
  key-matrix.md                key index map + config file format
  ac-profile3-decoded.json     decoded AC profile 3 (factory defaults baseline)
  ac-profile3-keys.csv         all 136 config entries, flattened
  usb-descriptors.txt          lsusb -v output (Linux)
  report-desc-ff00.txt         iface 1 report descriptor (34B) — correct
  report-desc-0.txt            39B, 0xFF32 — belongs to a DIFFERENT device, see above
tools/                         see tools/README.md
captures/                      gitignored (**/*.pcapng)
snapshots/                     config snapshots for diffing
```
