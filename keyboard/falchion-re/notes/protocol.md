# Falchion Ace HFX — protocol notes

Status: **transport confirmed, opcodes not yet known.** Everything below comes from static
analysis of ASUS's own HAL plus live HID queries. No packets captured yet, nothing written
to the device, no firmware touched.

---

## 1. Transport — CONFIRMED

Armoury Crate talks to the keyboard over **interface 1**:

| property | value |
|---|---|
| Windows instance | `HID\VID_0B05&PID_1B7E&MI_01` |
| Usage page / usage | **0xFF00 / 0x01** |
| Report descriptor | 34 bytes (`report-desc-ff00.txt`), matches `wDescriptorLength=34` on iface 1 |
| Report ID | **none declared** |
| Payload | 64 bytes IN, 64 bytes OUT |
| Linux endpoints | `0x85` IN, `0x0d` OUT |

Two independent sources agree.

**(a) Live HID query** (`HidP_GetCaps` on each interface of the running device):

```
MI_01          UP=0xFF00  U=0x01   in=65  out=65  feat=0     <- config channel
MI_02&COL01    UP=0x000C  U=0x01   in=4   out=0   feat=0     consumer / media
MI_02&COL02    UP=0x0001  U=0x80   in=2   out=0   feat=0     system control
MI_02&COL03    UP=0xFFC0  U=0x01   in=21  out=0   feat=0     vendor, input-only
MI_04          UP=0x0059  U=0x01   in=0   out=0   feat=51    HID LampArray
```

**(b) A device table inside `AacKbHal_x64.dll`** at file offset `0x153DF4`, 0x40-byte
records. Our entry and its neighbours:

```
offset      VID     PID    ?    usagePg  usage  usagePg2  variant  ?
0x153CEC   0x0B05  0x1B3F  1    0xFF00   0x01   0xFFC0    0x10     6
0x153D2C   0x0B05  0x1B42  1    0xFF00   0x01   0xFFC0    0x10     6
0x153D6C   0x0B05  0x1B78  1    0xFF00   0x01   0xFFC0    0x13     6
0x153DAC   0x0B05  0x1B7A  1    0xFF00   0x01   0xFFC0    0x13     6
0x153DEC   0x0B05  0x1B7E  1    0xFF00   0x01   0xFFC0    0x10     6   <- Falchion Ace HFX
0x153E2C   0x0B05  0x1C5E  1    0xFF00   0x01   0xFFC0    0x13     6
0x153E6C   0x0B05  0x1C60  1    0xFF00   0x01   0xFFC0    0x13     6
                                              (table ends with 0xFFFFFFFF)
```

The table's `usagePg2 = 0xFFC0` is exactly the `MI_02&COL03` input-only channel above, so
the HAL opens **two** channels per device: `0xFF00` for command/response and `0xFFC0` for
unsolicited input events. The `variant` field (0x10 vs 0x13) selects a device class; the
Falchion shares 0x10 with PIDs 0x1B3F and 0x1B42.

There is also a `cmp ecx, 0x1B7E` / `jne` at file offset `0x05C005`, right after a
`mov ecx, 0x1E0` (allocate 480 bytes) — the per-device dispatch. So the Falchion is handled
inside `AacKbHal_x64.dll` itself, not by a separate plugin DLL.

### Practical write format

The 0xFF00 report descriptor declares **no Report ID**, so:

- **Windows** — write **65** bytes: a leading `0x00` report-ID placeholder, then 64 payload
  bytes. (That is why `HidP_GetCaps` says `in=65 out=65` while the descriptor says 64.)
- **Linux hidraw** — same convention: prepend `0x00`, then the 64 payload bytes.

Getting this wrong is the most common reason a hand-built report is silently dropped.

---

## 2. Correction to the earlier interface table

`findings.md` originally listed interface 4 as usage page `0xFF32`, Report ID 2, 63B in/out,
citing `report-desc-0.txt`. That attribution does not hold up:

- `report-desc-0.txt` is **39 bytes**. No interface on this device has
  `wDescriptorLength = 39` (they are 68, 34, 182, 23, 327).
- Interface 4's descriptor is **327 bytes**, and Windows reports it as usage page `0x0059`
  (HID Lighting And Illumination / LampArray) with 51-byte **feature** reports and no input
  or output reports — consistent with a large LampArray descriptor, not a 63-byte vendor pipe.

`report-desc-0.txt` does decode cleanly on its own — usage page `0xFF32`, usage `0x74`,
Report ID 2, 63B IN (usage 0x75) / 63B OUT (usage 0x76) — it just appears to **belong to a
different device**. The Linux box also has a `ROG OMNI RECEIVER` and other ASUS hardware;
the likeliest explanation is that the hidraw node was misidentified when it was dumped.

**Action:** re-dump the iface-4 descriptor on Linux, matching by usage page rather than
`hidrawN`. Treat `0xFF32` as not-part-of-this-device until that is redone.

---

## 3. HAL API surface (from debug strings)

`AacKbHal_x64.dll` is a COM in-proc server — only `DllGetClassObject`, `DllRegisterServer`,
`DllInstall`, `DllUnregisterServer`, `DllCanUnloadNow` are exported, so there are no
callable report-builder symbols. But it logs every method via `OutputDebugString` as
`[<Class>][<Method>] ...`, which leaks the entire API.

Device classes seen: `AacM601/602/603/605`, `AacM701/702`, `AacMA01/MA02`, `AacRA06-RA10`,
`AacX801-X807`, `AacX901/X902`, `AacXA01-XA13`, `AacTUFK1/3/5/7`, `AacClaymore`,
`AacRogKb_Base`, `AacKbFunction_*` (BLE / RF / Remake variants).

Methods relevant to this project:

| method | relevance |
|---|---|
| `ChangeKey`, `ChangeKey_Normal`, `ChangeKey_DKS`, `ChangeKey_ModTap`, `ChangeKey_Toggle` | **key remapping — the primary target** |
| `WriteMacroFlash`, **`WriteMacroFlash_SupportFn`** | persist to flash; the `_SupportFn` variant is a direct hint that Fn-layer writes are a distinct, explicitly-supported path |
| `SetActuation_AllKey`, `SetActuation_PreKey` | actuation point, global and per-key |
| `SetRapidTrigger_AllKey`, `SetRapidTrigger_PreKey` | rapid trigger |
| `SetDeadZone_AllKey`, `SetDeadZone_PreKey` | dead zone |
| `Reset_Actuation_RapidTrigger`, `Reset` | restore defaults |
| `SetSpeedTap`, `SwitchSpeedTap`, `ResetSpeedTap` | SOCD / speed tap |
| `SetProfile`, `IsDefaultProfile` | profile switching |
| `GetDeviceInfo`, `GetVersion`, `GetMultiLayout`, `GetLanguage` | handshake / identification |
| `SetLeverMode`, `SetLeverSwitch`, `SetLeverChange`, `GetLeverMode` | the "lever" (touch strip / wheel) |
| `GetKeyEvent`, `ReadEvent`, `InitReadEvent`, `SetKeyLog`, `GetKeyStats` | the 0xFFC0 input channel |
| `SetPollingRate`, `GetPollingRate` | polling rate |

`GetDeviceInfo` also mirrors device state into the registry at
`HKCR\WOW6432Node\CLSID\{EB2FD7A7-8173-43F0-92E7-16A191FA9277}\0B051B7E`:
`Keyboard_IsAlive`, `Keyboard_IsDefaultProfile`, `Keyboard_Keypad`, `Keyboard_InBTMode`,
`Matrix_OnOff`. `Keyboard_IsAlive = 1` right now, i.e. the HAL is actively polling the board.

### `FF AA`

Nearly every method has three log strings: `[Class][Method]`, `[Class][Method] Timeout`,
and `[Class][Method] FF AA`. The consistent pairing of `FF AA` with `Timeout` as the two
failure paths suggests **`FF AA` is the device's error/NAK response prefix** — the first two
bytes of a rejected command's reply. Not observed on the wire yet, but if it holds it is
exactly the signal Phase 3.6 needs: a firmware-level refusal to remap a locked key should
come back as `FF AA`.

---

## 4. Opcodes — STILL UNKNOWN

| Opcode | Meaning | Payload layout | Verified? |
|--------|---------|----------------|-----------|
| ? | ChangeKey | probably `(row<<8)\|col` source + target keycode | no |
| ? | SetActuation_PreKey | | no |
| ? | WriteMacroFlash (commit) | | no |
| `FF AA`? | error / NAK response | | no — inferred from log strings only |

Recovering these needs either a USBPcap capture of Armoury Crate or disassembly of the
`AacM*Function` methods. The capture is far cheaper and is the next step.

---

## 5. What this already rules in / out

- **No blind fuzzing needed.** Channel, report size, and framing are known, so the first
  capture will be immediately interpretable.
- **No firmware work implied yet.** Nothing here suggests the Fn lock is in firmware. That
  `WriteMacroFlash_SupportFn` exists as a *separate supported entry point* is mild evidence
  the firmware can write Fn-layer bindings, which would put the lock in the UI.
- **The `0xFFC0` channel is a bonus.** Input-only, carrying key events and stats — probably
  how AC builds its per-key heatmap. Not needed for remapping.
