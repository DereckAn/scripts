# AC config — key matrix decode

Source: `C:\ProgramData\ASUS\Framework\keyboard\ROG FALCHION ACE HFX\fp_3_config_024080600167.xml`
(base64 → percent-decode → JSON). Decoded copy: `ac-profile3-decoded.json`.
All values below are **factory defaults** — nothing has been changed in Armoury Crate yet.

## Entry naming

`button.keyboardButton` has 136 entries named `keyfunction_<col>_<row>`.

- `row` = 1..7
- `col` = 0..11 for the **base layer**, `col+50` for the **Fn layer** of the same key
- 68 base + 68 Fn = 136. Every one of the 68 keys has both layers present.

## source_key encoding — SOLVED

```
source_key = (row << 8) | col
```

Verified against all 136 entries; **135/136 match exactly**.

The one exception is `keyfunction_0_1` (row 1, col 0), which stores `source_key = 0x0000`
instead of the predicted `0x0100`. Its Fn counterpart `keyfunction_50_1` *does* store the
predicted `0x0132`. So the base record for that one key is the odd one out — either a
sentinel, an off-by-one in AC, or that key is special-cased. Worth confirming before a
tool relies on it.

At defaults, `source_key == defaultKey == target_key` for every entry.

## Populated matrix positions

`.` = no key wired at that position. 7 rows x 12 cols = 84 slots, 68 populated.

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

The Fn layer populates **exactly** the same 68 positions — no key has a base binding
without an Fn binding or vice versa.

## Field semantics (defaults only — low confidence)

| field | observed values | reading |
|---|---|---|
| `selectedmode` | `"0"` on all 68 base, `"7"` on all 68 Fn | layer/binding type, not a per-key flag |
| `button_function` | `0` on all base, `7` on all Fn | mirrors `selectedmode` |
| `actuation` | `10` on all 136 | HE actuation point; units unknown |
| `trigger_type` | `0` on all 136 | — |
| `keydata_1..3` | `-1` on all 136 | probably macro / multi-key slots |

> **Correction to an earlier hypothesis.** `mode == 7` is *not* a "this key is locked"
> marker. It appears on all 68 Fn-layer entries uniformly, including keys that Armoury
> Crate lets you remap freely. It just means "Fn layer". The Fn lock is not visible in a
> defaults-only dump.

Type inconsistency to watch: `button_function` is a JSON **string** on base entries and a
JSON **int** on Fn entries, in the same file. A parser must accept both.

## Key-name alignment — HYPOTHESIS, NOT VERIFIED

`0B051B7E.csv` lists 84 LEDs with `exist=1`: lamp_id 0–15 are the underglow strip
(no `virtual_key`), and lamp_id **16–83 are exactly 68 key LEDs** — matching the 68 matrix
positions one-for-one. That count agreement is real evidence both files describe the same
68 keys.

`ac-keymap-hypothesis.csv` zips them together **assuming matrix row-major order
(row 1 col 0..10, row 2 col 0..10, …) corresponds to ascending lamp_id**. That assumption
is unproven, and the resulting table should be treated as a guess:

```
row col  base    fn      lamp  key(guess)
  1   0  0x0000  0x0032    16  Escape
  1   1  0x0101  0x0133    17  Number1
  ...
  2   2  0x0202  0x0234    29  Back
  2   4  0x0204  0x0236    31  Tab
  ...
  7  11  0x070B  0x073D    83  Right
```

Reason for doubt: the resulting matrix rows do **not** line up with physical keyboard rows
(matrix row 2 would span backspace/insert *and* Tab–Y). That is possible for an arbitrary
scan matrix, but the clean sequential result is an artifact of the zip, not evidence for it.

11 of the 68 keys have `virtual_key = NULL` in the CSV — almost certainly the punctuation
keys (`` ` ``, `-`, `=`, `[`, `]`, `\`, `;`, `'`, `,`, `.`, `/`), which ASUS leaves unnamed
because they are locale-dependent (cf. `nationCode` in the profile blob).

### Cheap way to verify (do this before trusting the table)

No packet capture needed:

1. Note the mtime of `fp_3_config_024080600167.xml`.
2. In Armoury Crate, remap **one** known key (e.g. `F1` → `A`). Apply.
3. Re-decode the file and diff against `ac-profile3-decoded.json`.
4. Whichever `keyfunction_<col>_<row>` changed **is** that key's true matrix coordinate.

Repeat for 3–4 keys spread across the board and the whole mapping falls out. Then repeat
targeting a **locked Fn key** — if the file does not change at all, the lock is client-side
(good news for Phase 3.6).
