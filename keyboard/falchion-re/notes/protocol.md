# ROG Falchion Ace HFX — historical protocol notebook

Device: `0b05:1b7e`, firmware `bcdDevice = 1.59`
Last synchronized: 2026-08-29

Current project status and safety decisions live in [`../FINDINGS.md`](../FINDINGS.md).
This notebook preserves earlier Windows capture and device-test observations; it
is not a preservation-safe command procedure. The cited raw PCAP files are absent
from the repository, so `[V]` and `[C]` below mean *recorded as verified/captured
during the earlier work*, not independently reproducible from the current checkout.
The current Linux descriptor logs do independently confirm the USB transport
layout.

Every claim below is tagged:
**[V]** verified on hardware · **[C]** from a packet capture · **[S]** static analysis of ASUS's DLL · **[?]** unresolved

---

## 1. Transport **[V]**

Armoury Crate talks to the keyboard on **interface 1 / usage page 0xFF00**.

| property | value |
|---|---|
| Windows instance | `HID\VID_0B05&PID_1B7E&MI_01` |
| Usage page / usage | `0xFF00` / `0x01` |
| Report descriptor | 34 bytes, **declares no Report ID** |
| Payload | 64 bytes IN, 64 bytes OUT |
| Linux endpoints | `0x85` IN, `0x0d` OUT |

### Full interface map **[V]**

```
MI_01          UP=0xFF00  U=0x01   in=65  out=65  feat=0    <- config channel (this doc)
MI_02&COL01    UP=0x000C  U=0x01   in=4   out=0   feat=0    consumer / media
MI_02&COL02    UP=0x0001  U=0x80   in=2   out=0   feat=0    system control
MI_02&COL03    UP=0xFFC0  U=0x01   in=21  out=0   feat=0    vendor, input-only (key events/stats)
MI_04          UP=0x0059  U=0x01   in=0   out=0   feat=51   HID LampArray (Windows Dynamic Lighting)
MI_00, MI_03   keyboard collections                          boot keyboard + NKRO
```

### How to write a report

The descriptor declares no Report ID, so both platforms need a **leading `0x00`
placeholder byte**:

- **Windows** — write **65** bytes: `0x00` + 64-byte payload. (This is why `HidP_GetCaps`
  reports `in=65 out=65` while the descriptor says 64.)
- **Linux hidraw** — same: prepend `0x00`, then 64 payload bytes.

Getting this wrong is the most common reason a hand-built report is silently dropped.

### Corroborating device table in `AacKbHal_x64.dll` **[S]**

At file offset `0x153DF4`, 0x40-byte records:

```
offset      VID     PID    ?    usagePg  usage  usagePg2  variant  ?
0x153CEC   0x0B05  0x1B3F  1    0xFF00   0x01   0xFFC0    0x10     6
0x153D2C   0x0B05  0x1B42  1    0xFF00   0x01   0xFFC0    0x10     6
0x153D6C   0x0B05  0x1B78  1    0xFF00   0x01   0xFFC0    0x13     6
0x153DAC   0x0B05  0x1B7A  1    0xFF00   0x01   0xFFC0    0x13     6
0x153DEC   0x0B05  0x1B7E  1    0xFF00   0x01   0xFFC0    0x10     6   <- Falchion Ace HFX
0x153E2C   0x0B05  0x1C5E  1    0xFF00   0x01   0xFFC0    0x13     6
0x153E6C   0x0B05  0x1C60  1    0xFF00   0x01   0xFFC0    0x13     6
                                              (terminated by 0xFFFFFFFF)
```

`usagePg2 = 0xFFC0` is the `MI_02&COL03` event channel — the HAL opens **two** channels per
device. `variant` (0x10 vs 0x13) selects a device class. A `cmp ecx, 0x1B7E` dispatch sits at
file offset `0x05C005`, so this board is handled inside `AacKbHal_x64.dll` itself, not a
separate plugin.

---

## 2. Command set

The device **echoes the request header back** on every command. See §5 — the echo is a
receipt of *delivery*, not of *effect*.

| Opcode | Meaning | Source |
|---|---|---|
| `12 <sub>` | GET / query. Reply echoes `12 <sub>` then appends data. | [C][V] |
| `22 01` | init handshake (echo only) | [C] |
| `25 00`, `25 01` | init handshake (echo only) | [C] |
| `51 21 ...` | **set Fn-layer key binding** | [C][V] |
| `51 22 ...` | set — exact function unconfirmed, seen with `C8` (200) payload | [C] |
| `50 55` | **commit to flash.** Reply ~220 ms later. | [C][V] |

### Startup handshake, in order **[C]**

```
OUT 12 03      IN 12 03 00...
OUT 12 00      IN 12 00 00 00 59 00 01 00 06 00 03 00     <- version: 0x59=89 minor, 01 major = 1.59
OUT 22 01      IN 22 01 00...
OUT 12 12      IN 12 12 00 00 01 01 00...
OUT 12 08      IN 12 08 00 00 01 00...
OUT 12 16      IN 12 16 00...
OUT 12 14      IN 12 14 00...
OUT 25 00      IN 25 00 00...
OUT 25 01      IN 25 01 00...
```

`12 00` was recorded as a standalone version query. Do not send it merely as a
liveness probe during preservation; it is still an undocumented vendor-HID
transaction:

```powershell
.\tools\send.ps1 -Bytes '12 00'
# IN  12 00 00 00 59 00 01 00 06 00 03 00
```

---

## 3. `51 21` — remap a key on the Fn layer

### Wire format **[C][V]**

```
byte:  0    1    2         3    4         5    6           7    8..63
      51   21   <src>     9F   <tgt>     00   <actuation> 00   00 ...

  src        source key index   (see §4)
  9F         constant in every sample observed
  tgt        target key index   [?] see §4
  actuation  0x0A = 10, matches the config file default
```

Captured from Armoury Crate, with the resulting config-file change:

| action | packet | config entry changed |
|---|---|---|
| M → 1 | `51 21 34 9F 02 00 0A 00` | `keyfunction_55_4` |
| M → 2 | `51 21 34 9F 03 00 0A 00` | `keyfunction_55_4` |
| N → 1 | `51 21 33 9F 02 00 0A 00` | `keyfunction_54_4` |
| ? → ? | `51 21 3D 9F 04 00 0A 00` | `keyfunction_53_5` |
| ? → ? | `51 21 0F 9F 05 00 0A 00` | `keyfunction_56_7` |
| ? → ? | `51 21 2B 9F 06 00 0A 00` | `keyfunction_57_2` |
| ? → ? | `51 21 19 9F 07 00 0A 00` | `keyfunction_57_7` |

**`51 21` writes the Fn layer.** Confirmed empirically: after `M → 2`, plain `M` still types
`m` while **`Fn+M` types `2`**. [V]

### `50 55` is NOT required to activate **[V]**

An uncommitted `51 21` takes effect **immediately in RAM**. Verified: sent
`51 21 34 9F 04 00 0A 00` with no commit, `Fn+M` changed straight away.

`50 55` was observed to persist configuration to flash. Without it, `51 21` still
changes live device state immediately. Replugging was observed to revert those
uncommitted changes, but that does **not** make the command read-only or
preservation-safe.

---

## 4. Key indices

### Source index — VERIFIED **[V][C]**

A **1-based row-major count** over the 68 physical keys, reading the layout left-to-right,
top-to-bottom.

```
row 1   Esc=1   1=2   2=3   3=4   4=5   5=6   6=7   7=8   8=9   9=10
        0=11    -=12  +=13  Bksp=14  Ins=15
row 2   Tab=16  Q=17  W=18  E=19  R=20  T=21  Y=22  U=23  I=24  O=25
        P=26    [=27  ]=28  \=29  Del=30
row 3   Caps=31 A=32  S=33  D=34  F=35  G=36  H=37  J=38  K=39  L=40
        ;=41    '=42  Enter=43  PgUp=44
row 4   LShift=45  Z=46  X=47  C=48  V=49  B=50  N=51  M=52
        ,=53    .=54  /=55  RShift=56  Up=57  PgDn=58
row 5   Ctrl=59  Win=60  Alt=61  Space=62  Alt=63  Fn=64  ROG=65
        Left=66  Down=67  Right=68
```

Directly confirmed: **Backspace=14, Q=17, I=24, O=25, Enter=43, N=51, M=52.**
Digits confirmed on the target side (see below).

### Target index — runtime-table encoding partly resolved **[S][?]**

Candidate B static analysis shows that bytes 4-5 form a 16-bit target. Values
through `0x00bc` are passed through the same runtime translation table used for
the source index (table base `0x1801bff6`). Special values `0x00ff`, `0x00c7`,
`0x00c8`, and `0x00d3` take separate paths and are stored in an internal
`0xA000`-class encoding. This proves the target is not simply copied into the
active key record, but the runtime table contents have not yet been recovered.

Contradictory observations, all from `51 21`:

| target byte | result |
|---|---|
| `0x09` on src 24 (I) | typed `8` (`vk=0x38`) |
| `0x04` on src 14 (Backspace) | typed `4` |
| `0x04` on src 52 (M) | typed `3` |

The last two conflict: **the same target byte produced different characters on different
source keys.** That should not happen for a simple position lookup, so either the target
field is not a plain key index, or Armoury Crate interactions between tests mutated state.

**Deferred experiment:** a clean series varying only the target byte on one source
key could resolve this, but it requires settings resets and vendor-HID writes. It
must not be attempted during preservation and requires a separate explicit test
plan and approval.

---

## 5. THE TRAP — echo does not mean effect **[V]**

**The device echoes the request header verbatim even when it discards the write.**

Controlled A/B — two commands differing only in the source byte, sent back to back, neither
committed, no Armoury Crate interaction between them:

```
51 21 11 9F 09 00 0A 00    src 17 = Q   (reserved: Fn+Q = Play/Pause)  -> ACK, NO EFFECT
51 21 18 9F 09 00 0A 00    src 24 = I   (not reserved)                 -> ACK, APPLIED (vk 0x38)
```

Same for `src 2` (the `1` key, reserved as F1): ACKed, `Fn+1` stayed F1, while `src 14` in
the same batch applied normally.

**`FF AA` was never observed** in any test. The firmware does not *reject* reserved-key
remaps — it silently ignores them. The `FF AA` strings in `AacKbHal_x64.dll` [S] presumably
cover some other error path we never triggered.

> **Any tool built on this protocol must verify by reading back or observing the key.
> Never treat the echo as success.**

### Static explanation of the silent ignore **[S]**

The `0x51/0x21` command handler at Candidate B `0x2662-0x27d4` validates the
source/layer fields, updates the translated per-key record, marks state dirty,
and calls the 64-byte response sender. It does not call the reserved-key check.

A separate function at `0x1f6e` searches one of two runtime policy arrays. The
base path has 6 32-bit entries; the Fn/other path has 57. Configuration-load and
apply code calls it before activating a mapping and skips matches, alongside the
strings `R_NSK_M` and `R_NSK_FnM`. Thus the static firmware structure supports
the historical result: packet acceptance/echo and effective binding policy are
separate decisions.

The arrays begin at RAM `0x1801c810`. Their values are not yet available in the
offline image, so the manual-derived list below has not been matched
entry-for-entry to firmware data.

---

## 6. Reserved keys (historically observed device-side filtering)

From the official manual. These are the ones the firmware silently refuses to remap:

```
Fn + Esc                     Backtick (`)
Fn + Shift + Esc             Tilde (~)
Fn + 1/2/3/4/5/6/7/8/9/-/=   Function key switch (F1-F12)
Fn + Ins                     Fn lock / unlock
Fn + Windows                 Windows lock
Fn + Tab                     Speed Tap
Fn + Left-Alt                On-the-fly macro record start/stop
Fn + A/S/D/F/G/H             Profile switch (H = default)
Fn + Caps                    Factory default (hold until LEDs blink green)
Fn + Q/W/E/R/T/Y             Play-Pause / Prev / Next / Mute / Vol- / Vol+
Fn + U                       Stealth mode
Fn + P                       Print screen
Fn + Del                     Scroll Lock
Fn + PgUp / PgDn             Home / End
Fn + Left / Right            Light effect switch
Fn + Up / Down               Brightness up / down
Fn + R-Ctrl (Copilot)        Menu
```

`Fn + Caps` is a hardware-triggered **settings factory reset**. It does not require
Armoury Crate, but it is not firmware or bootloader recovery.

---

## 7. The Armoury Crate config file

`C:\ProgramData\ASUS\Framework\keyboard\ROG FALCHION ACE HFX\fp_<profile>_config_<model>.xml`
(model = `024080600167`). Encoding: **base64 → percent-decode → JSON**.

```powershell
$b64  = ([xml](Get-Content $f -Raw)).root.device_type.device.function.file_data
$json = [uri]::UnescapeDataString([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64)))
```

Top-level: `nationCode`, `button`, `lighting`, `performance`, `lever`.
`button.keyboardButton` holds **136 entries** = 68 keys x 2 layers, named
`keyfunction_<col>_<row>`.

### `source_key` encoding **[V]**

```
source_key = (row << 8) | col
```

Verified on **135 of 136** entries. Sole exception: row 1 / col 0 stores `0x0000` instead of
`0x0100` (its Fn twin stores the expected `0x0132`).

- `col` 0–11 → **base layer**
- `col` 50–61 → **Fn layer** of the same key (`col + 50`)

Layer assignment confirmed on hardware: editing `keyfunction_55_4` changed `Fn+M`, not `M`. [V]

Populated matrix positions — 68 of a 7x12 grid, identical on both layers:

```
      col: 0  1  2  3  4  5  6  7  8  9 10 11
row 1:      X  X  X  X  X  X  X  X  X  X  X  .
row 2:      X  X  X  X  X  X  X  X  X  X  X  .
row 3:      X  X  X  X  X  X  X  X  X  X  .  .
row 4:      X  X  X  X  X  X  X  X  X  .  X  X
row 5:      X  X  .  X  .  .  .  X  X  .  X  X
row 6:      X  X  X  .  X  .  .  X  X  .  X  X
row 7:      X  X  X  X  X  .  X  X  X  .  X  X
```

**Note:** this `(row, col)` space is *not* the same as the wire's flat source index (§4), and
the two have not been reconciled. M is `row 4 / col 55` in the file but index `52` on the wire.

### Field semantics **[V]**

| field | factory | after a user remap |
|---|---|---|
| `selectedmode` | `"0"` base / `"7"` Fn | `1` |
| `button_function` | `0` base / `7` Fn | `1` |
| `target_key` | same as `source_key` | the target's `(row<<8)\|col` |
| `keydata_1` | `-1` | mirrors `target_key` |
| `actuation` | `10` | `10` |
| `trigger_type` | `0` | `0` |

So `mode` is the **binding type**: 0 = base-layer default, 7 = Fn-layer default,
1 = user-assigned key.

> Two hypotheses were tested and **disproved** during this work, recorded so nobody retries them:
> - "`mode == 7` marks a locked key" — **false.** All 68 Fn entries carry mode 7 uniformly,
>   including freely-remappable ones. It just means "Fn layer default".
> - "matrix row-major order matches ascending `lamp_id` in the LED CSV" — **false.** The
>   resulting key-name table was wrong; M is at `row 4 / col 5`, not where that predicted.

---

## 8. HAL API surface **[S]**

`AacKbHal_x64.dll` is a COM in-proc server — only `DllGetClassObject`, `DllRegisterServer`,
`DllInstall`, `DllUnregisterServer`, `DllCanUnloadNow` are exported, so there are no callable
report-builder symbols. But it logs every call via `OutputDebugString` as `[<Class>][<Method>]`,
which leaks the whole API.

Methods relevant here:

```
ChangeKey, ChangeKey_Normal, ChangeKey_DKS, ChangeKey_ModTap, ChangeKey_Toggle
WriteMacroFlash, WriteMacroFlash_SupportFn
SetActuation_AllKey / _PreKey        SetRapidTrigger_AllKey / _PreKey
SetDeadZone_AllKey / _PreKey         Reset_Actuation_RapidTrigger, Reset
SetSpeedTap, SwitchSpeedTap, ResetSpeedTap
SetProfile, IsDefaultProfile
GetDeviceInfo, GetVersion, GetMultiLayout, GetLanguage
SetLeverMode / SetLeverSwitch / SetLeverChange / GetLeverMode
GetKeyEvent, ReadEvent, InitReadEvent, SetKeyLog, GetKeyStats
SetPollingRate, GetPollingRate
```

Device classes: `AacM601/602/603/605`, `AacM701/702`, `AacMA01/MA02`, `AacRA06-RA10`,
`AacX801-X807`, `AacX901/X902`, `AacXA01-XA13`, `AacTUFK1/3/5/7`, `AacClaymore`,
`AacRogKb_Base`, `AacKbFunction_*`.

The HAL mirrors live device state into the registry at
`HKCR\WOW6432Node\CLSID\{EB2FD7A7-8173-43F0-92E7-16A191FA9277}\0B051B7E`:
`Keyboard_IsAlive`, `Keyboard_IsDefaultProfile`, `Keyboard_Keypad`, `Keyboard_InBTMode`,
`Matrix_OnOff`.

Capture these logs live with `tools/haltrace.ps1` to label packets by method name.

---

## 9. Still unknown

- **Target index encoding** (§4) — the one real blocker for a complete remap implementation.
- Opcodes for actuation, rapid trigger, dead zone, speed tap, profile switch, polling rate.
  All have known HAL method names; none captured yet.
- What `51 22` does (seen once with `C8` = 200 — plausibly a brightness or percentage).
- Whether a base-layer write uses a different subcommand than `51 21`.
- The `9F` constant in byte 3 — never varied, meaning unknown.
- How the file's `(row, col)` space maps to the wire's flat index.
- `12 03 / 12 12 / 12 08 / 12 16 / 12 14` query meanings.
- The `0xFFC0` event channel payload format (21-byte input reports).
- Current hardware markings are SNC73270 plus ZB25VQ32BTIG external SPI NOR; pad
  mapping and safe readback wiring remain unresolved.
- No DFU interface is exposed in normal mode. The official updater instead
  describes proprietary HID bootloader PID `0b05:1b7f`.
- The raw PCAP files cited by the earlier capture work are not preserved in this
  repository.
