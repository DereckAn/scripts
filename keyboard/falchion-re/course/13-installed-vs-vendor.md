# Lesson 13 — Installed vs vendor firmware

> **In one sentence:** Once there was a verified copy of what the keyboard actually runs (1.59), the investigation compared it byte by byte with the ASUS reference file (1.00.58), found that most of the "differences" are just everything sliding 44 bytes along, and paired every function across the two releases without ever trusting an address on its own.
>
> **You will learn:**
> - why every offline tool now goes through one shared parser, with an allowlist of the only two images it will vouch for
> - what changed between releases: the +44-byte record growth, 22.90% of bytes differing, no string changing, and a bootloader copy that is identical three ways
> - why one small insertion makes thousands of bytes "differ", and how the `+0x2c` shift was measured instead of assumed
> - the identical / structural / tentative matching tiers, and the rule "an address is never the sole signal"
> - the review corrections in logs 95, 97, 99 and 100, and why the function counts in the notes keep changing
>
> **Time:** ~60 minutes · **Prerequisites:** Lesson 6 (the firmware file), Lesson 8 (Ghidra), Lesson 10 (how it boots). Lesson 12 is where the installed dump came from.

---

## 1. The story (kid version)

You own two editions of the same book: the 2019 edition and the 2021 edition. Your teacher says "the 2021 edition changed a lot". You lay them side by side and compare page 1 with page 1, word 1 with word 1.

At first it looks terrible. From chapter 3 onwards almost **every** word is in a different place. But then you notice something: in chapter 3 the publisher added one short sentence. Everything after it just moved along by that sentence. The rest of the book is the same text, only shifted.

So you change how you compare. Instead of "word number 5,000 against word number 5,000", you match **paragraphs**: "this paragraph in 2019 says exactly the same as that paragraph in 2021". You match them by what they *say*, never only by their page number, because the page numbers are exactly what moved. Once every paragraph has a partner, the real change turns out to be tiny.

Before any of that, you check that you really have the two books you think you have. A photocopy of an unknown book with the same cover isn't allowed on the desk.

### How the analogy maps to the real thing

| In the story | In the keyboard |
|---|---|
| 2019 edition | Vendor file `dumps/vendor/M605_V01_00_58.bin`, release 1.00.58 |
| 2021 edition | The installed dump from the keyboard, release 1.59 |
| "Is this really the book?" | The allowlist: SHA-256, base and size must match (`falchion_image.py`) |
| The added sentence | Record slot 1 is 44 bytes (`0x2c`) longer |
| Everything after it moves | The measured shift `+0x2c` in Candidate B |
| Word-for-word comparison | Log 96's raw byte diff: 101,297 bytes differ |
| Matching paragraphs by content | Pairing functions by body bytes and instruction shape (log 98) |
| Never trusting page numbers alone | "An address is never the sole signal" |

---

## 2. Why we needed this

After log 92 the project had, for the first time, a verified copy of the installed application region: `dumps/device/ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin`, 442,368 bytes, SHA-256 `fc6128ab089e…637b` (Lesson 12).

Nearly all the analysis in Lessons 6–10 had been done on the **vendor** file, 1.00.58. The keyboard runs **1.59**. So an important question was open: **which of our vendor findings still apply to the firmware that is really on the keyboard?** Log 91 had already given a warning sign: the first 48 bytes matched except the checksum field at `0x2c`, "evidence that the installed record payload differs."

The plan for this stage is `notes/step6-offline-custom-firmware-plan.md` (log 93). It split the work into phases:

- **Phase 1** (log 94): one shared image-format library.
- **Phase 2** (log 96): a byte-exact comparison of the two images.
- **Phase 3** (log 98): a runtime map of the installed image and a function-by-function correspondence.

The alternative, simply reusing every vendor address on the installed image, would have been wrong in a way that's easy to miss. You'll see why in section 3.4.

---

## 3. The real thing

### 3.1 One parser for everything (log 94)

Before log 94, several tools each had their own way of reading the `SN_FWIN` header and its records. That's risky: two parsers can disagree quietly. Phase 1 added `tool/falchion_image.py`, "one shared parser, validation model and mutation-source gate for every later offline tool", with 38 tests.

It keeps three jobs separate (FINDINGS, log 94 section):

| Job | Function | What it does |
|---|---|---|
| Parsing | `parse` | May inspect **any** image. Reports what the bytes say. Fails closed with `ImageFormatError`. |
| Validation | `validate` | Reports the known constraints and **names every region it could not check**, so a partial image is never mistaken for a full one. |
| Source policy | `require_supported_source` | Refuses any image whose SHA-256, base and size are not on the [allowlist](00-glossary.md#allowlist). |

#### The allowlist

This is the whole list, copied from the tool:

```python
SUPPORTED_SOURCES = (
    SourceSpec(
        "vendor-1.00.58-full",
        "6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d",
        0x0, 0x7C000),
    SourceSpec(
        "installed-1.59-application",
        "fc6128ab089e4fd712b172c54cd88b7f28476b55bdac688134e052281ded637b",
        0x10000, 0x6C000),
)
```

Two images, each named by its [SHA-256](00-glossary.md#sha-256), its [base address](00-glossary.md#base-address), and its size. Change one byte of either file and the tools that need a trusted source refuse it.

#### Logical offsets, translated in one place

The vendor file starts at flash offset `0`. The installed dump starts at flash offset `0x10000`, because USB READ can't reach the bootloader region below it (Lesson 11). So "byte 0 of the dump" is really "flash `0x10000`".

`falchion_image.py` always talks in **logical flash offsets** and converts to a file position in exactly one function:

```python
def index(self, flash_off, size=1):
    """Translate a logical flash offset to a file index, or fail closed."""
    if not self.has(flash_off, size):
        raise ImageFormatError(...)
    return flash_off - self.base
```

`file position = flash offset − base`. If you ask for a range the image doesn't contain, it raises an error instead of reading the wrong place.

#### Three layout facts from log 94

1. **The installed application record grew.** Record[1]'s length is `0x1e780` in 1.59 against `0x1e754` in 1.00.58. `0x1e780 − 0x1e754 = 0x2c` = **44 bytes**. Record[0] (`0x58ac`) and both load addresses (`0x60011000`, `0x60021000`) didn't change. So "any tool that reuses a vendor length for the installed image mis-slices it", and record lengths are now read per image.
2. **The bootloader under study exists on the device.** The installed dump's logical range `[0x61000, 0x71000)` is byte-identical to the vendor file's `[0x61000, 0x71000)` *and* to the vendor's primary bootloader region `[0, 0x10000)`. All three hash to `4a4568b61bc245397b0ede6f285eb1bd8a7fa2018bc1373bc05e73eabb0f686a`. This mirrored copy also checks out against its own [word-sum](00-glossary.md#word-sum), `0xfb665ae3` at `0x70ffc`. **What this does not show:** that the unread installed primary region `[0, 0x10000)` is identical, which container the device actually booted, or anything about ROM behaviour.
3. **`SN_FWIN +0x8` reads `v1.0.00` in both images.** It's the container format version and doesn't track the ASUS release number.

### 3.2 Phase 2: what changed, byte by byte (log 96)

`tool/compare_firmware_images.py` is built on the Phase-1 parser, "so no second SN_FWIN parser or offset policy exists", with 41 tests. It compares the installed dump against the **same logical range** of the vendor file, `[0x10000, 0x7c000)`. It never compares byte 0 with byte 0.

It also follows a strict rule: "A changed byte range is a fact; its purpose is a Phase-3-onward hypothesis." It reports *what* changed and never guesses *why*.

#### The headline numbers

| Measure | Value |
|---|---|
| Differing bytes | **101,297** of 442,368 (**22.90%**) |
| Contiguous differing ranges | 3,509 |
| Changed `0x1000` pages | 39 of 108 |
| First difference | `0x1002c`, inside the SN_FWIN header |
| Last differing range ends at | `0x7c000` |

`0x1002c` is flash `0x10000 + 0x2c`: byte 44 of the header, exactly where log 91 saw the first 48 bytes stop matching.

#### Every change is in three runs

The comparator's region map (you'll reproduce it in section 6):

| Logical range | Pages | Changed? | Contents |
|---|---|---|---|
| `0x10000..0x17000` | 7 | **yes** | data (header, records, entry image) |
| `0x17000..0x21000` | 10 | no | `0xff` fill |
| `0x21000..0x40000` | 31 | **yes** | data (the application record) |
| `0x40000..0x60000` | 32 | no | zero fill |
| `0x60000..0x71000` | 17 | no | backup container and bootloader copy |
| `0x71000..0x74000` | 3 | no | zero |
| `0x74000..0x79000` | 5 | no | a separate RAM image |
| `0x79000..0x7b000` | 2 | no | zero |
| `0x7b000..0x7c000` | 1 | **yes** | data (contains the application word-sum at `0x7bffc`) |

The last page changing makes sense: the application [word-sum](00-glossary.md#word-sum) stored at `0x7bffc` covers the whole region, so any change anywhere changes it.

#### The records

| Slot | Source | Runtime destination | Installed length | Vendor length | Δ | Differing bytes |
|---|---|---|---|---|---|---|
| 0 | `0x60011000` | `0x18000000` | `0x58ac` | `0x58ac` | +0 | 131 in 106 ranges |
| 1 | `0x60021000` | `0x18000000` | `0x1e780` | `0x1e754` | **+44** | 101,112 in 3,399 ranges |

Neither record moved, and neither destination changed. Both stored checksums changed. Slot 1's extra 44 bytes are reported as an explicit installed-only span, `0x3f754..0x3f780`, "which has no vendor counterpart to differ from".

#### No string changed

The comparator collected every run of six or more printable ASCII characters in each image. Both have **603 distinct values in 802 occurrences**, and the two **multisets are equal**: the same strings, each appearing the same number of times. "Nothing was added, removed, rewritten, or duplicated a different number of times."

A *multiset* is a list where counting matters. `{a, a, b}` and `{a, b, b}` have the same distinct values but are different multisets. Log 97 made the tool compare multisets (section 5).

FINDINGS is careful here: no changed string "is consistent with slot 1 being compressed but is not by itself evidence of that." And strings are compared by **value**, not position. "An equal multiset does not mean identical placement."

#### The bootloader copy, identical three ways

Log 96 confirmed log 94 with an independent code path: installed `[0x61000, 0x71000)`, vendor `[0x61000, 0x71000)` and vendor `[0, 0x10000)` all hash to `4a4568b6…686a`, "with zero differing ranges in either pairing."

### 3.3 Seeing the shift with your own eyes

Here are the first 48 bytes of each image at logical `0x10000`. In the dump that's file position 0. In the vendor file it's file position `0x10000`:

```text
installed 00000000: 534e 5f46 5749 4e00 7631 2e30 2e30 3000  SN_FWIN.v1.0.00.
installed 00000010: 0010 0160 ffff ffff 0100 0000 ffff ffff  ...`............
installed 00000020: 0000 0000 0010 0160 ac58 0000 8524 557d  .......`.X...$U}

vendor    00010000: 534e 5f46 5749 4e00 7631 2e30 2e30 3000  SN_FWIN.v1.0.00.
vendor    00010010: 0010 0160 ffff ffff 0100 0000 ffff ffff  ...`............
vendor    00010020: 0000 0000 0010 0160 ac58 0000 7ac1 755e  .......`.X..z.u^
```

Everything matches until offset `0x2c`: `85 24 55 7d` installed against `7a c1 75 5e` vendor. Read little-endian, that's `0x7d552485` and `0x5e75c17a`: the two record[0] checksums the comparator reports.

Now look for a string. The product name `ROG FALCHION ACE HFX` sits at:

| File | File offset | Logical offset |
|---|---|---|
| vendor | `0x3f66f` | `0x3f66f` (base 0) |
| installed dump | `0x2f69b` | `0x2f69b + 0x10000` = **`0x3f69b`** |

`0x3f69b − 0x3f66f = 0x2c`. **The same string, 44 bytes further along.** Same value, different place: exactly why comparing strings by value found no change while the byte diff found thousands.

(One more thing you can check yourself: both positions lie in the last `0x400` bytes of record slot 1, and both are `0x31b` bytes after the start of that tail: `0x3f354 + 0x31b` in the vendor file and `0x3f380 + 0x31b` installed. Section 3.4 explains that tail.)

### 3.4 Phase 3: the installed runtime map (log 98)

Phase 3 added `tool/extract_installed_records.py`, `tool/match_functions.py` and a Ghidra script, `FalchionFunctionInventory.java`. The rule: "Nothing below is taken from the vendor image or from a vendor address."

#### Where things go in RAM

Candidate A's scatter-region table (Lesson 10) was found by **structure**: "the first descriptor whose source and destination match the SN_FWIN record it loads". It lands at flash `0x16750` in both releases. For the installed image:

| Region | Flash source | Runtime destination | Size | Handler |
|---|---|---|---|---|
| 0 | `0x21000..0x3f380` | `0x18000000..0x1801e380` | `0x1e380` | `__scatterload_copy` |
| 1 | `0x3f380..0x3f780` (`0x400` in) | `0x1801e380..0x1801ee84` (`0xb04` out) | `0xb04` | `__scatterload_decompress` |
| 2 | none | `0x1801ee84..0x18036168` | `0x172e4` | `__scatterload_zeroinit` |

Three cross-checks, all from installed bytes:

- **The zero-init end equals the entry image's initial stack pointer** in both releases: installed `0x18036168`, vendor `0x18036140`. Two independent structures agree on the top of RAM.
- **Slot 1 is exactly the copy region plus the `0x400` compressed input**: `0x1e380 + 0x400 = 0x1e780` installed, `0x1e354 + 0x400 = 0x1e754` vendor. So the +44 is entirely in the copy region. The compressed input and output sizes didn't change.
- `0x18036168 − 0x18036140 = 0x28`. The zero-init shrank by 4, "moving the RAM top by `+0x28`".

The compressed region turned out to be the USB/HID descriptor set, not code (log 105, Lesson 14). That's why the product-name string lives there.

Every byte of the installed dump is accounted for, "with no gaps or overlap", and each slice is proved to round-trip against its source before anything is written.

#### Pairing functions across releases

Four slices were imported into a separate Ghidra project, `ghidra/project-step6/`: Candidate A at base `0` and Candidate B at base `0x18000000`, both from each release. A [function](00-glossary.md#function) found by Ghidra is then paired with its partner using several signals: body bytes, masked instruction shape, constants, strings, size, instruction and block counts, and call degree.

The tiers, from the docstring of `match_functions.py`:

| Tier | Meaning |
|---|---|
| **identical** | same body bytes; the entry address may or may not agree |
| **structural** | same instruction shape (mnemonics and operand kinds, with every scalar and address masked), and that shape is unique on both sides |
| **tentative** | no shape match, but size, counts, constants, strings and call degree agree closely, and the best candidate is clearly ahead of the runner-up |
| **unmatched** | nothing left that clears the bar |

"Masked" means numbers inside instructions are blanked out before comparing. If a function calls another function that moved 44 bytes, its bytes change (the call target changed), but its shape doesn't.

#### "An address is never the sole signal"

This is the key rule, quoted from FINDINGS:

> the identical and structural tiers use no address at all, and the one tentative rule that uses the measured shift also requires body-byte equality and can never promote a pairing above tentative. So no vendor symbol crosses over on an address alone.

Why so strict? Because addresses are **exactly** what changed. After the 44-byte growth, "vendor function at `X`" is usually *not* at `X` in the installed image. A tool that reused vendor addresses would silently name the wrong functions.

#### The `+0x2c` shift is measured, not assumed

The matcher computes the dominant shift **from the identical and structural matches only**, then reports it. For Candidate A it's `0x0` (it didn't move). For Candidate B it's `+0x2c`. Ambiguous duplicates that happen to fit the shift are marked *tentative*, never promoted.

#### Log 98's first numbers

| Program | Vendor | Installed | Identical | Structural | Tentative | Unmatched | Shift |
|---|---|---|---|---|---|---|---|
| Candidate A | 80 | 80 | 78 | 0 | 2 | 0 | `0x0` |
| Candidate B | 293 | 293 | 260 | 24 | 9 | 0 | `+0x2c` |

#### Discontiguous bodies

A Ghidra function's body isn't always one continuous block of bytes. The compiler can place parts of it elsewhere. Log 99 found this was common: **15 of 80** bodies in Candidate A and **61 of 293** in Candidate B were discontiguous. So `entry..entry+size` isn't the body. Every byte-level figure now uses Ghidra's real ordered body ranges (section 5).

#### The real change is much smaller than the raw diff

Once functions were paired, Phase 3 compared the spans that no function covers, pairing them in order. As regenerated after log 99:

- **Candidate A** changed 131 bytes, "all of them data and none of them instruction bytes". That equals log 96's raw count exactly, because A didn't move.
- **Candidate B** changed **1,230 bytes** (253 in bodies, 977 in data spans) plus one 44-byte insertion. So "roughly 99,880 of log 96's 101,112 raw differing bytes for slot 1 are the relocation, not content."

Log 100 later corrected two parts of this (section 5): the insertion and the span pairing.

#### Two limits carried forward

- The SN_FWIN record word at `+0xc` (`0x18000000` in both slots) is never read by `FUN_0000511c`, so treating it as a RAM destination is an **assumption**. The slice names use the base the loader evidence supports instead: `0` for Candidate A.
- The RAM image at flash `0x74000..0x7c000` is referenced by no SN_FWIN record and no scatter region on this path, so **how it is loaded is unestablished**.

And one honest caveat: "Function sets come from Ghidra's auto-analysis, so the counts are 'functions Ghidra found', not a completeness proof."

### 3.5 Why the function counts keep changing

If you open `notes/vendor-to-installed-functions.md` today, you won't see 80 and 293. You'll see this:

| Program | Vendor | Installed | Identical | Structural | Tentative | Unmatched | Shift |
|---|---|---|---|---|---|---|---|
| Candidate A | 141 | 141 | 127 | 5 | 9 | 0 | `0x0` |
| Candidate B | 616 | 616 | 531 | 56 | 29 | 0 | `0x2c` |

And the aligned change now reads Candidate A 131 bytes (7 in bodies, 124 in data, 91/91 spans compared), Candidate B 1,073 bytes, with **18** spans that couldn't be paired safely.

Nothing is contradictory here. The note is **regenerated** by `tool/report_phase3.py` whenever the function inventories change, and they changed several times:

| When | Candidate A | Candidate B | Unpaired B spans |
|---|---|---|---|
| Logs 98–99 | 80 | 293 | (pairing by order) |
| Log 100 (after seeding vector handlers) | 97 | 530 | 20 |
| Log 106 (task entries seeded) | 114 | 616 | |
| Log 132 (a boundary repair) | 141 | | |
| Committed note today | 141 | 616 | 18 |

Each later phase found more real functions and **seeded** them into Ghidra, meaning it told Ghidra "a function starts here" at addresses the auto-analysis had missed. Every time, the correspondence was recomputed. **The baseline changes each time**, so a figure from one log shouldn't be compared directly with a figure from another. Log 106 made the same point about reachability: its "146 of 573 and 281 of 616 are not comparable" because the denominators changed.

`report_phase3.py --check` proves the committed notes are a fresh render of the current inputs (section 6).

A small observation: the current note still contains the sentence "With 530 functions per side instead of 293…", from the log-100 regeneration, while its own headline table says 616. The tables are regenerated; that sentence of prose wasn't updated. Trust the tables.

---

## 4. Decisions and why

| Decision | Why | Alternative rejected | Evidence |
|---|---|---|---|
| One shared parser for every offline tool | Two parsers can disagree silently | Each tool parsing SN_FWIN itself | log 94 |
| Allowlist by SHA-256, base and size | A tool that mutates images must know exactly what it started from | Accept any file that parses | log 94 |
| Convert logical offsets to file positions in one function | The installed dump starts at `0x10000`; a second conversion is a second chance to get it wrong | Ad-hoc `- 0x10000` everywhere | log 94 |
| Read record lengths per image | Slot 1 grew by 44 bytes | Reuse vendor lengths | log 94 |
| Compare the same **logical** range | Byte 0 of the dump is flash `0x10000` | Compare file offset with file offset | log 96 |
| Report changes, assign no meaning | A changed range is a fact; its purpose is a hypothesis | Label changes as "bug fixes" | log 96 |
| Refuse when a record slot appears in only one image, or a record's address moved | The comparator doesn't model those layouts | Guess an alignment | log 96 |
| Never pair functions on an address alone | Addresses are exactly what moved | Transfer vendor names by address | log 98 |
| Measure the shift from identical/structural matches only | A shift assumed from the header growth could be wrong in places | Assume `+0x2c` everywhere | log 98 |
| Keep the full correspondence in tracked JSON and a tracked generator | Transient output can't be audited | Ephemeral scripts | log 99 |

---

## 5. What went wrong, and how it was caught

### Log 95 (after independent review): the record table has no terminator

- **Believed:** log 94's `parse_records` stopped at the first slot with a zero address or zero length.
- **True:** the bootloader's `FUN_0000511c` loops over a fixed **eight** slots, and its only per-slot condition is "length ≠ 0". Log 95 quoted the decompile: `for (uVar1 = 0; uVar1 < 8; uVar1 = uVar1 + 1)`.
- **Consequences, reproduced by the reviewer:** a nonzero-length record with address zero was ignored; an active record behind an empty slot was ignored; a full eight-slot table was rejected. The reviewer built an in-memory image with an active slot 3 behind the empty slot 2, and the old parser returned `known_checks_ok=True` while omitting slot 3.
- **Why it hadn't shown up:** slot 2 of both real images holds address `0x60021000` with length `0`, "so the old rule happened to stop for the right number of records by the wrong reason."
- **Lesson:** *copy the firmware's loop, not your idea of it.* A parser that gets the right answer on your two files can still be wrong.

Log 95 also noted that `analyze_candidate_integrity.py`, `analyze_boot_structures.py` and `build_modified_image.py` "still carry the terminator assumption"; a test pins the difference.

### Log 97 (after independent review): five comparator defects

1. **Record destinations were parsed but not reported**, so a changed runtime load address could have passed unnoticed. Now both images' full record fields are shown, with `addr_changed`, `dst_changed` and `checksum_changed` flags.
2. **Provenance was checked after comparing**, contrary to the plan. The allowlist gate now runs before any parsing, hashing or diffing.
3. **`--analysis-only --json` printed its warning on stdout** before the JSON, making it unparseable. The warning now goes to stderr and is also recorded under a `provenance` key.
4. **Strings were compared as distinct values**, described as "603 ASCII runs". Now multisets: 603 distinct values in 802 occurrences, "so a changed duplicate count cannot vanish".
5. **Slot 1's extra 44 bytes were only a length delta.** Now they're an explicit span.

- **Lesson:** *a check that runs after the thing it guards isn't a guard.* And *if you don't print a field, you can't notice it changing.*

### Log 99 (after independent review): contiguous bodies, and tracked outputs

- **Believed:** a function's body is `entry..entry+size`.
- **True:** bodies are often discontiguous (15/80 in A, 61/293 in B). That invalidated the body hashes, the body-versus-data split, and log 98's 21/446 body-byte totals. Everything was regenerated from real ordered ranges.
- Also fixed: slot 1 had been extracted only as its loadable copy region, leaving the `0x400` compressed tail unextracted; the complete correspondence existed only in transient JSON; the notes came from an ephemeral script; the claim that an address was "only ever reported" was inaccurate; and `--write` could emit slices before the aggregate check was enforced.
- **Lesson:** *a picture of the data isn't the data.* Ghidra's "size" field summarises a body; the ranges are the body.

### Log 100: spans paired by list index, and the "single insertion"

This correction was found by the investigation itself while regenerating Phase 3 after new functions were seeded.

- **Believed:** data spans could be paired by position in the list ("the k-th uncovered span in vendor ↔ the k-th in installed"), guarded by equal span counts.
- **True:** with the larger function set, the counts still matched **while the k-th spans described different regions**. Spans are now keyed to the matched function before them, and a pair is compared only when that anchor, the distance past it, and the length all agree.
- **Regenerated:** Candidate A 97/97, still zero changed function-body bytes and still exactly 131 data bytes; Candidate B 530/530, shift still `+0x2c`, aligned change 1,073 bytes, but 20 spans couldn't be paired safely, so the total is a **lower bound**.
- **Also corrected:** logs 98 and 99 had reported slot 1's growth as one 44-byte insertion at vendor `0x180047f8`. It's actually **distributed** across matched function bodies and several spans. The single gap "was an artifact of the shallower function set: before the vector handlers were seeded, a large unanalysed region read as one uncovered span."
- **Lesson:** *an equal count is not an equal meaning.* A guard that checks only the number of items can pass while every item is paired wrong. And a result that depends on how much you've analysed will change when you analyse more.

---

## 6. Try it yourself

All offline. Run from `keyboard/falchion-re/`. None of these touches the keyboard.

### Exercise 1: confirm you have the right two files

```bash
cd dumps/device && sha256sum -c SHA256SUMS; cd ../..
sha256sum dumps/vendor/M605_V01_00_58.bin
```

Output:

```text
ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin: OK
6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d  dumps/vendor/M605_V01_00_58.bin
```

`sha256sum -c` must run inside `dumps/device/`, because `SHA256SUMS` lists a bare filename. Compare the vendor hash with the allowlist in section 3.1.

### Exercise 2: the first 48 bytes, side by side

```bash
xxd -l 48 dumps/device/ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin
xxd -s 0x10000 -l 48 dumps/vendor/M605_V01_00_58.bin
```

Output:

```text
00000000: 534e 5f46 5749 4e00 7631 2e30 2e30 3000  SN_FWIN.v1.0.00.
00000010: 0010 0160 ffff ffff 0100 0000 ffff ffff  ...`............
00000020: 0000 0000 0010 0160 ac58 0000 8524 557d  .......`.X...$U}
00010000: 534e 5f46 5749 4e00 7631 2e30 2e30 3000  SN_FWIN.v1.0.00.
00010010: 0010 0160 ffff ffff 0100 0000 ffff ffff  ...`............
00010020: 0000 0000 0010 0160 ac58 0000 7ac1 755e  .......`.X..z.u^
```

Notice the vendor needs `-s 0x10000` and the dump doesn't. That's the logical-offset rule.

### Exercise 3: find the 44-byte shift in a string

```bash
grep -abo 'ROG FALCHION ACE HFX' dumps/vendor/M605_V01_00_58.bin
grep -abo 'ROG FALCHION ACE HFX' dumps/device/ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin
printf '%x %x\n' 259695 194203
printf '%x\n' $((0x2f69b + 0x10000))
```

Output:

```text
259695:ROG FALCHION ACE HFX
194203:ROG FALCHION ACE HFX
3f66f 2f69b
3f69b
```

`grep -abo` prints decimal file offsets. Convert, add the dump's base, and subtract: `0x3f69b − 0x3f66f = 0x2c`.

### Exercise 4: run the comparator

```bash
python3 tool/compare_firmware_images.py | sed -n '/Whole-range result/,/changed `0x1000` pages/p'
```

Output:

```text
## Whole-range result

- installed range SHA-256: `fc6128ab089e4fd712b172c54cd88b7f28476b55bdac688134e052281ded637b`
- vendor range SHA-256: `b9c35b2339b2d6316bdab5bb2799e28b89454fd5c2c133b89827902b7a2403c1`
- ranges equal: **False**
- differing bytes: **101297** of 442368 (22.90%)
- contiguous differing ranges: **3509**
- changed `0x1000` pages: **39** of 108
```

Scroll the full output for the record table, the three-way bootloader check, the region map, and "multisets equal … **True**".

### Exercise 5: the shared parser on the installed dump

```bash
python3 tool/falchion_image.py dumps/device/ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin --base 0x10000 | grep -E '^(SOURCE|RECORD|WORD_SUM|RESULT)'
```

Output:

```text
SOURCE installed-1.59-application
RECORD 0 addr=0x60011000 flash=0x11000..0x168ac len=0x58ac checksum=0x7d552485 dst=0x18000000
RECORD 1 addr=0x60021000 flash=0x21000..0x3f780 len=0x1e780 checksum=0xeb0a9879 dst=0x18000000
WORD_SUM application range=0x10000..0x7c000 stored=0x2d7486db computed=0x2d7486db match=True
WORD_SUM bootloader_mirror range=0x61000..0x71000 stored=0xfb665ae3 computed=0xfb665ae3 match=True
RESULT known_checks_ok=True checks_run=18 containers_skipped=1 word_sums_skipped=1
```

`SOURCE installed-1.59-application` is the allowlist recognising the file. Log 95 recorded `checks_run=16` for this dump. Log 101 later added two boot-acceptance checks, and the count is now 18.

### Exercise 6: the installed runtime map

```bash
python3 tool/extract_installed_records.py | grep -E '^(ENTRY|REGION)'
```

Output:

```text
ENTRY pointer=0x60011000 initial_sp=0x18036168 reset=0x000014a9
REGION_TABLE flash=0x16750
REGION 0 src=0x60021000 (flash 0x21000) dst=0x18000000..0x1801e380 size=0x1e380 handler=0x1d8 __scatterload_copy
REGION 1 src=0x6003f380 (flash 0x3f380) dst=0x1801e380..0x1801ee84 size=0xb04 handler=0x17c __scatterload_decompress
REGION 2 src=0x6003f780 (flash 0x3f780) dst=0x1801ee84..0x18036168 size=0x172e4 handler=0x1f4 __scatterload_zeroinit
```

Without `--write` it writes nothing. Check that region 2's end equals `initial_sp`.

### Exercise 7: match Candidate B's functions

```bash
python3 tool/match_functions.py --program app_b \
  --vendor-inventory ghidra/inventories/vendor_b.txt \
  --installed-inventory ghidra/inventories/installed_b.txt \
  | grep -E '^(COUNTS|TIERS|DOMINANT_SHIFT|RESULT)'
```

Output:

```text
COUNTS vendor=616 installed=616
TIERS identical=531 structural=56 tentative=29 unmatched=0
DOMINANT_SHIFT 0x2c (+44 bytes), measured from the identical and structural matches only
RESULT matched=616 unmatched=0
```

That's the current baseline, not log 98's 293 (section 3.5).

### Exercise 8: prove the notes are current

```bash
python3 tool/report_phase3.py --check
```

Output:

```text
  CURRENT notes/installed-record-load-map.md
  CURRENT notes/installed-record-load-map.json
  CURRENT notes/vendor-to-installed-functions.md
  CURRENT notes/vendor-to-installed-functions-app-a.json
  CURRENT notes/vendor-to-installed-functions-app-b.json
RESULT reports_current=True stale=0
```

This one takes a little while.

---

## 7. Check your understanding

1. The raw diff says 101,112 bytes of slot 1 differ, but Phase 3 says Candidate B changed about 1,073–1,230 bytes. How can both be true?
   <details><summary>Answer</summary>The raw diff compares byte `N` with byte `N`. Slot 1 grew by 44 bytes, so after the first growth point almost everything is compared against a neighbour 44 bytes away and "differs". Pairing functions by content and comparing aligned spans removes the relocation. Roughly 99,880 of the raw bytes are relocation, not content (log 98). The current aligned figure, 1,073, is a lower bound because 18 spans couldn't be paired safely.</details>

2. Why does the product name appear at `0x3f66f` in one file and `0x3f69b` in the other, yet the string comparison reports no change?
   <details><summary>Answer</summary>Strings are compared as a multiset of values, not by position. The value is the same; only its place moved, by `+0x2c`. The byte diff is what carries position.</details>

3. What would go wrong if `match_functions.py` paired functions by vendor address alone?
   <details><summary>Answer</summary>Addresses are exactly what moved. In Candidate B most functions are `0x2c` further along, so "the function at the vendor address" would often be a different function, and vendor names would be transferred to the wrong code. That's why the identical and structural tiers use no address, and the only address-aware rule stays at "tentative".</details>

4. The old record parser gave the right answer on both real images. Why was it still rejected?
   <details><summary>Answer</summary>It stopped at the first zero, but the bootloader scans all eight slots and skips only zero-length ones. It worked here only because slot 2 happened to be an empty hole. An image with an active record behind a hole would have lost that record and its checksum dependency (log 95).</details>

5. Does the three-way bootloader match prove the keyboard's own bootloader region `[0, 0x10000)` is the same as the vendor's?
   <details><summary>Answer</summary>No. USB can't read that region. The match shows the mirrored copy at `[0x61000, 0x71000)` on the device equals the vendor's bootloader. FINDINGS says explicitly that it doesn't show the unread primary region is identical, which container the device booted, or anything about ROM behaviour.</details>

6. Log 98 said 293 functions in Candidate B; the note says 616. Which is wrong?
   <details><summary>Answer</summary>Neither. They're different baselines. Later phases seeded functions that Ghidra's auto-analysis had missed (530 at log 100, 616 at log 106), and the correspondence was regenerated each time. Figures from different baselines shouldn't be compared directly.</details>

---

## 8. Sources

- [../FINDINGS.md](../FINDINGS.md): "Shared image-format library and installed-versus-vendor layout facts (log 94)", "Installed 1.59 versus vendor 1.00.58, byte-exact (log 96)", "Installed runtime map and cross-release function correspondence (log 98)", and the "Phase 3 was regenerated" paragraph in "Installed hardware and runtime interface map (log 100)"
- [../TIMELINE.md](../TIMELINE.md)
- [../logs/91-one-block-read-validation.txt](../logs/91-one-block-read-validation.txt)
- [../logs/92-full-app-region-backup.txt](../logs/92-full-app-region-backup.txt)
- [../logs/93-step6-offline-custom-firmware-plan.txt](../logs/93-step6-offline-custom-firmware-plan.txt)
- [../logs/94-version-aware-image-format-library.txt](../logs/94-version-aware-image-format-library.txt)
- [../logs/95-phase1-record-scan-correction.txt](../logs/95-phase1-record-scan-correction.txt)
- [../logs/96-installed-vs-vendor-comparison.txt](../logs/96-installed-vs-vendor-comparison.txt)
- [../logs/97-phase2-review-corrections.txt](../logs/97-phase2-review-corrections.txt)
- [../logs/98-installed-code-map-and-function-matching.txt](../logs/98-installed-code-map-and-function-matching.txt)
- [../logs/99-phase3-review-corrections.txt](../logs/99-phase3-review-corrections.txt)
- [../logs/100-installed-hardware-interface-map.txt](../logs/100-installed-hardware-interface-map.txt)
- [../logs/101-boot-acceptance-resolved.txt](../logs/101-boot-acceptance-resolved.txt)
- [../logs/106-phase5a-task-entries-and-new-baseline.txt](../logs/106-phase5a-task-entries-and-new-baseline.txt)
- [../logs/132-provenance-boundary-repair-and-bus-scoped-decode.txt](../logs/132-provenance-boundary-repair-and-bus-scoped-decode.txt)
- [../notes/step6-offline-custom-firmware-plan.md](../notes/step6-offline-custom-firmware-plan.md)
- [../notes/installed-vs-vendor.md](../notes/installed-vs-vendor.md)
- [../notes/installed-record-load-map.md](../notes/installed-record-load-map.md)
- [../notes/vendor-to-installed-functions.md](../notes/vendor-to-installed-functions.md)
- [../dumps/device/README.md](../dumps/device/README.md)
- [../tool/falchion_image.py](../tool/falchion_image.py), [../tool/compare_firmware_images.py](../tool/compare_firmware_images.py), [../tool/extract_installed_records.py](../tool/extract_installed_records.py), [../tool/match_functions.py](../tool/match_functions.py), [../tool/report_phase3.py](../tool/report_phase3.py)

[← Previous](12-the-race-and-the-backup.md) · [Course home](README.md) · [Next →](14-inside-tasks-and-usb.md)
