# Key indices and the config file format

Last synchronized: 2026-08-29. The hardware-test results in this file were
recorded during earlier protocol work. The cited raw PCAPs are not present in the
repository; see [`../FINDINGS.md`](../FINDINGS.md) for current evidence and safety
status.

Two **different** key-addressing schemes are in play. They have not been reconciled.

| scheme | used by | form | status |
|---|---|---|---|
| flat index | the wire protocol (`51 21`) | 1-based row-major, 1..68 | **verified** |
| `(row, col)` | the Armoury Crate config file | `(row << 8) \| col` | **verified** |

Example of the mismatch: **M** is index `52` on the wire but `row 4 / col 55` in the file.

---

## 1. Wire key index — VERIFIED

1-based, row-major over the 68 physical keys, left-to-right, top-to-bottom.

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

**Directly confirmed:** Backspace=14, Q=17, I=24, O=25, Enter=43, N=51, M=52.

How each was established:

| index | key | evidence |
|---|---|---|
| 14 | Backspace | sent `51 21 0E ...`, `Fn+Backspace` changed |
| 17 | Q | sent `51 21 11 ...`, `Fn+Q` unchanged (reserved — see protocol.md §5) |
| 24 | I | sent `51 21 18 ...`, `Fn+I` produced `vk=0x38` |
| 25 | O | captured from Armoury Crate remapping O |
| 43 | Enter | captured from Armoury Crate remapping Enter |
| 51, 52 | N, M | captured from Armoury Crate remapping N and M |

The remaining 61 entries are extrapolated from the same row-major rule and are consistent with
all seven confirmed points, but have not each been individually exercised.

## 2. Target index — UNRESOLVED

The target byte of `51 21` does **not** map onto the scale above cleanly:

| target byte | source key | resulting character |
|---|---|---|
| `0x09` | 24 (I) | `8` |
| `0x04` | 14 (Backspace) | `4` |
| `0x04` | 52 (M) | `3` |

The last two conflict — the same target byte gave different characters on different source
keys. Either the field is not a plain key index, or Armoury Crate interactions between those
two tests mutated state.

**Deferred write experiment that could settle it:**

1. Establish a separate approved settings-test plan outside firmware preservation.
2. Record a baseline and understand how settings will be restored.
3. Vary only the target byte on one source and observe each result.
4. Keep Armoury Crate closed so it cannot mutate state between samples.

This experiment sends vendor-HID writes and may reset settings. It is not
read-only. Earlier testing found that uncommitted changes cleared on replug, but
that observation is not a firmware-recovery guarantee.

---

## 3. Config file format

`C:\ProgramData\ASUS\Framework\keyboard\ROG FALCHION ACE HFX\fp_<profile>_config_<model>.xml`
Model id: `024080600167`. Encoding: **base64 → percent-decode → JSON**.

```powershell
$b64  = ([xml](Get-Content $f -Raw)).root.device_type.device.function.file_data
$json = [uri]::UnescapeDataString([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64)))
```

Use `tools/snap-config.ps1` to decode and diff snapshots.

Top-level keys: `nationCode`, `button`, `lighting`, `performance`, `lever`.
`button.keyboardButton` holds **136 entries** = 68 keys x 2 layers, named `keyfunction_<col>_<row>`.

### `source_key` — VERIFIED

```
source_key = (row << 8) | col
```

Holds for **135 of 136** entries. Sole exception: row 1 / col 0 stores `0x0000` rather than
`0x0100`; its Fn twin stores the expected `0x0132`.

- `col` 0–11 → **base layer**
- `col` 50–61 → **Fn layer** of the same key (`col + 50`)

Layer assignment confirmed on hardware: editing `keyfunction_55_4` changed `Fn+M`, while plain
`M` still typed `m`.

Populated positions — 68 of a 7x12 grid, identical on both layers:

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

### Entry fields — VERIFIED

Factory default (base layer) vs. after a user remap:

```json
"keyfunction_5_4":  {"selectedmode":"0","defaultKey":"1029","keydata_1":"-1","keydata_2":"-1","keydata_3":"-1",
                     "button":{"source_key":"1029","trigger_type":0,
                               "normal":{"button_function":"0","target_key":"1029","actuation":10}}}

"keyfunction_55_4": {"selectedmode":"1","defaultKey":"1079","keydata_1":"1792","keydata_2":"-1","keydata_3":"-1",
                     "button":{"source_key":"1079","trigger_type":0,
                               "normal":{"button_function":1,"target_key":"1792","actuation":10}}}
```

| field | factory | after remap |
|---|---|---|
| `selectedmode` | `"0"` base / `"7"` Fn | `1` |
| `button_function` | `0` base / `7` Fn | `1` |
| `target_key` | same as `source_key` | target's `(row<<8)\|col` |
| `keydata_1` | `-1` | mirrors `target_key` |
| `actuation` | `10` | `10` |
| `trigger_type` | `0` | `0` |

`mode` is the **binding type**: 0 = base-layer default, 7 = Fn-layer default, 1 = user-assigned.

**Parser note:** `button_function` is a JSON **string** on factory base entries and a JSON
**int** on modified ones, in the same file. Accept both.

### Related files

| path | contents |
|---|---|
| `...\config_<model>.xml` | profile list — 6 firmware profiles (Default + 1–5), all `FIRMWARE_PROFILE` |
| `C:\ProgramData\ASUS\ArmourySDK\Keyboard\ROG FALCHION ACE HFX\<model>\Key\<n>\*.xml` | per-key XML, one file per `source_key`, UTF-16LE |
| `C:\ProgramData\ASUS\ROG Live Service\DeviceContent\0B051B7E\0B051B7E.csv` | 24x11 LED grid, physical mm coords, `lamp_id` + `virtual_key` per LED |

The LED CSV has 84 `exist=1` LEDs: `lamp_id` 0–15 are the underglow strip, 16–83 are the 68
key LEDs. 11 of those 68 have `virtual_key = NULL` — the punctuation keys, which ASUS leaves
unnamed because they are locale-dependent (cf. `nationCode`).

---

## 4. Disproved hypotheses

Recorded so nobody spends time on them again.

**"`mode == 7` marks a locked key."** False. All 68 Fn-layer entries carry mode 7 uniformly at
factory, including keys Armoury Crate remaps freely. It simply means "Fn-layer default".

**"Matrix row-major order matches ascending `lamp_id` in the LED CSV."** False. Zipping the 68
matrix positions against `lamp_id` 16–83 produced a tidy-looking key-name table that was
wrong — it placed M at `row 6 / col 1`, but the real position is `row 4 / col 55` (Fn) /
`row 4 / col 5` (base). The tidiness was an artifact of the zip, not evidence for it. The old
`ac-keymap-hypothesis.csv` has been removed.
