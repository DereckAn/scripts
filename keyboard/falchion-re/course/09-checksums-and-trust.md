# Lesson 09 — Checksums and trust

> **In one sentence:** A checksum is a small number computed from a big block of data so you can tell if the block changed; this keyboard uses CRC-32 and simple word-sums, and the story of this lesson is how one "impossible" checksum turned out to be two CRC-32s added together.
>
> **You will learn:**
> - what a checksum is, from a receipt total up to [CRC-32](00-glossary.md#crc) with its reflected polynomial `0xedb88320`
> - the `SN_FWIN` record table at file `0x10024`: record A matched plain CRC-32, record B did not
> - how the "impossible" value `0x1a76c116` was cracked by reading the bootloader's verify routine
> - the additive **word-sums** at `0x0fffc`, `0x70ffc` and `0x7bffc`, and why `0x61000` is not a checksum offset
> - the eight-slot record table, the hole-versus-terminator correction, and why "no signature found" is not "no signature exists"
> - the offline builder that recomputes every field, and why its first "proves the checks are live" wording was an overclaim
>
> **Time:** ~75 minutes · **Prerequisites:** [Lesson 2](02-how-computers-count.md), [Lesson 6](06-the-firmware-file.md), [Lesson 8](08-ghidra.md)

## 1. The story (kid version)

You buy a basket of groceries. At the bottom of the receipt is a total. You don't need the total to know what you bought, but it lets you check: add up the prices yourself, and if your sum matches the printed total, nothing was mistyped. If someone secretly changed the price of the milk, the total would no longer match. That is the whole idea of a checksum: **a receipt total for data.**

A plain sum is a weak total, though. If the shop raises the milk by a dollar and lowers the bread by a dollar, the total is unchanged. A better total would care about *which* item changed, not just the grand amount. [CRC-32](00-glossary.md#crc) is that better total. It is still just arithmetic over the bytes, but it is built so that almost any change, even swapping two bytes, produces a different result.

Now imagine the shop keeps two receipts stapled together, and prints one grand total on top that is the sum of both receipts' totals. If you only knew about one receipt, that grand total would look impossible: it wouldn't match either receipt on its own. You would only understand it once you saw that it was two totals added. That is exactly the puzzle of this lesson.

**How the analogy maps to the real thing**

| In the shop | In the firmware |
|---|---|
| A receipt | A region of the firmware image |
| Adding up the prices | Computing a [checksum](00-glossary.md#checksum) over the bytes |
| The printed total | The stored checksum in the `SN_FWIN` record |
| A weak "just add it up" total | A [word-sum](00-glossary.md#word-sum) |
| A total that catches any change | CRC-32 |
| One grand total = two receipts' totals added | Record B = CRC-32(chunk 0) + CRC-32(chunk 1) |
| Checking the total yourself | Recomputing the checksum offline |

## 2. Why we needed this

By log 74 the investigation could disassemble the firmware (Lesson 8), knew the container layout, and had a real reason to care about checksums. The long-term goal was a *recoverable* modification workflow: could a changed firmware be made acceptable to the keyboard? That question splits in two:

1. **Is there a signature?** If the firmware were signed with a private key, no amount of editing could produce a valid image, because you don't have the key. Editing would be pointless.
2. **If it's only checksums, can we recompute them?** A checksum is not a secret. Anyone can recompute it. If the only integrity fields are checksums, an edited image can be made self-consistent offline.

The firmware/update path contained "CRC/checksum language but no identified firmware signature-verification string, embedded public key, or crypto-library dependency" (FINDINGS, "Integrity and authentication"). That was encouraging but not enough. To be sure, every integrity field had to be **reproduced**: computed independently and shown to match the stored value. A field you can reproduce is a field with no secret in it.

This lesson is the reproduction. It is also a good example of the project's discipline, because the first serious attempt *failed*, and the failure was the clue.

## 3. The real thing

### 3.1 A checksum, from the ground up

The simplest checksum is a running sum. Take every byte, add them, keep the low bits. In Python:

```python
total = 0
for b in data:
    total = (total + b) & 0xffffffff
```

This catches typos but is easy to fool, as the milk-and-bread trick showed. The keyboard actually uses this idea in one place, on **32-bit words** instead of bytes: the [word-sum](00-glossary.md#word-sum) (Section 3.6).

**CRC-32** is stronger. Instead of adding, it treats the data as one enormous binary number and takes the remainder after dividing by a fixed special number called the **polynomial**. You do not need the algebra. The gentle version is this: CRC feeds each bit through a shift-and-XOR machine, and the polynomial decides which bits get XORed at each step. A good polynomial spreads any single change through the whole result, so two different inputs almost never give the same CRC.

The keyboard uses the standard IEEE CRC-32, the same one in ZIP files and Ethernet. Its polynomial in "reflected" form is **`0xedb88320`**. "Reflected" means the bits are processed least-significant-first; it is just a convention, and it is the one Python's `zlib.crc32` uses. The proof that this is the right algorithm is that the constant `0xedb88320` appears in the bootloader itself, at program offset `0xc78c` (log 74). The firmware carries its own CRC table.

You never have to implement CRC-32. Python's standard library has it:

```python
import zlib
print(hex(zlib.crc32(b"hello")))   # 0x3610a686
```

### 3.2 The `SN_FWIN` record table

At file offset `0x10000` the container has the header `SN_FWIN\0v1.0.00\0` (the [glossary](00-glossary.md#sn_fwin) notes that `v1.0.00` is the container-format string, not the ASUS release). Right after it, at file `0x10024`, is a table of four-word records: `(flash_addr, length, crc32, ram_dest)`. Here is the raw header and the start of the table:

```
$ xxd -s 0x10000 -l 0x60 dumps/vendor/M605_V01_00_58.bin
00010000: 534e 5f46 5749 4e00 7631 2e30 2e30 3000  SN_FWIN.v1.0.00.
00010010: 0010 0160 ffff ffff 0100 0000 ffff ffff  ...`............
00010020: 0000 0000 0010 0160 ac58 0000 7ac1 755e  .......`.X..z.u^
00010030: 0000 0018 0010 0260 54e7 0100 16c1 761a  .......`T.....v.
00010040: 0000 0018 0010 0260 0000 0000 0000 0000  .......`........
```

The tool `analyze_candidate_integrity.py` decodes the table for us (Section 6). The active records are:

| Record | flash_addr | length | crc32 | ram_dest |
|---|---|---|---|---|
| A | `0x60011000` | `0x000058ac` | `0x5e75c17a` | `0x18000000` |
| B | `0x60021000` | `0x0001e754` | `0x1a76c116` | `0x18000000` |

The mapping `file = flash - 0x60000000` from Lesson 7 turns record A's flash range into file `0x11000..0x168ac` (Candidate A) and record B's into file `0x21000..0x3f754` (Candidate B plus its compressed tail).

### 3.3 Record A: a plain CRC-32 that matched

Record A verified immediately. IEEE CRC-32 over its file bytes equals the stored value exactly (log 74):

```
A_RANGE file 0x11000..0x168ac
A_CRC32 calc=0x5e75c17a stored=0x5e75c17a match=True
```

That single match did two jobs at once. It confirmed the algorithm was standard IEEE CRC-32, and it **locked the flash→file mapping** (`file = flash - 0x60000000`). If either had been wrong, A would not have matched. The tool asserts this as a hard self-check, so it cannot silently drift (FINDINGS, "SN_FWIN integrity record table").

### 3.4 Record B: the impossible checksum

Record B refused to match. CRC-32 over its whole file range gave `0x60c95a7b`, not the stored `0x1a76c116`. Log 74 then ruled out every reasonable variant, one at a time:

```
B_STORED 0x1a76c116
  B ieee_crc32(B)                    0x60c95a7b
  B crc32(B, init=A_crc)             0x8b76fde3
  B crc32(A+B)                       0x8b76fde3
  B crc32(recB + B)                  0x7775017d
  B crc32(B, init=len)               0xf44349dc
  B crc32(copy-region 0x1e354)       0x9f556233
B_RANGE_SWEEP ieee-crc32 hits over whole file: 0 []
```

It tried CRC with different starting values, CRC seeded with A's result, CRC of A and B joined, CRC over just the copy region, and a **sweep** that computed the CRC of every start-and-end range in the whole file looking for `0x1a76c116`. Zero hits (log 74). The honest conclusion at that point:

> "Candidate B's stored `0x1a76c116` is not an IEEE CRC-32 (or tested variant/seed/range) of the container's B bytes; the verified byte-source for B differs and must be read from the bootloader verify routine." (log 74)

Notice what the investigation did **not** do. It did not guess "maybe it's encrypted" or "maybe it's a signature". It said: our search failed, so we must go read the code that actually checks it. **When a checksum won't reproduce, read the verifier.**

### 3.5 Reading the verifier

Log 75 decompiled the bootloader's whole verify chain, read-only. The orchestrator `FUN_00007ec8` selects an image and requires the check to pass before jumping. The chain of functions:

- `FUN_00008000` walks the boot-priority table, checks the `SN_FWIN` magic, then calls `FUN_0000511c`. Its strings include `"[BLD] CRC Verify PASS!"` and `"[BLD] CRC mismatch at region %d"` (log 75).
- `FUN_0000511c` loops over the record slots and, for each active one, calls `FUN_00005028` and compares the result with the stored checksum word.
- `FUN_00005028` is the checksum itself. Its decompile (log 75):

```c
undefined4 FUN_00005028(int *param_1,int param_2,uint param_3,undefined4 param_4,uint param_5)
{
  iVar3 = 0;
  while( true ) {
    if (param_3 == 0) { *param_1 = iVar3; return 0; }
    uVar1 = param_3;
    if (param_5 <= param_3) { uVar1 = param_5; }     // clamp chunk to param_5 = 0x10000
    FUN_0000059c(param_4,param_2,uVar1);             // copy chunk to RAM 0x18000000
    iVar2 = FUN_000028e8(5,param_4,uVar1);           // hardware CRC-32 over the chunk
    ...
    iVar2 = FUN_000028c4();                          // read the CRC result
    iVar3 = iVar3 + iVar2;                            // ADD it to the running total
    param_2 = param_2 + (uVar1 & 0xfffffffc);
    param_3 = param_3 - uVar1;
  }
}
```

Read the shape, not the decompiler's variable names. The routine walks the region in chunks of at most `param_5 = 0x10000` bytes. For each chunk it runs the hardware CRC-32 engine and **adds** the result to a running total. So:

- **One chunk** (region ≤ `0x10000`): the total is a single plain CRC-32.
- **Two chunks**: the total is `CRC32(chunk 0) + CRC32(chunk 1)`, added as 32-bit numbers.

Record A is `0x58ac` bytes, one chunk, so it is a plain CRC-32, which is why it matched in Section 3.3. Record B is `0x1e754` bytes, which is more than `0x10000`, so it spans **two** chunks. Its stored value is the *sum of the two chunk CRCs*. That is the stapled-receipts total from the story.

### 3.6 The word-sums

A second routine, `FUN_000026d0`, is a different, simpler integrity pass. It reads a region in `0x1000`-byte pages and adds up every 32-bit word, requiring the last word of the region to equal the sum of all the words before it (log 75). That is the [word-sum](00-glossary.md#word-sum).

There are three word-sum guard words in the vendor image:

| Guard word at | Covers | Stored value |
|---|---|---|
| `0x0fffc` | bootloader region `0x00000..0x10000` | `0xfb665ae3` |
| `0x70ffc` | duplicate bootloader copy `0x61000..0x71000` | `0xfb665ae3` |
| `0x7bffc` | whole application region `0x10000..0x7c000` | `0x5d27c5a9` |

The application word-sum is verified live at boot: `FUN_000026d0(0x6c000)` sums from base `0x60010000`, so it guards exactly `0x10000..0x7c000` with the guard at `0x7bffc` (log 101, Lesson 10).

**Why `0x61000` is not a checksum offset.** An early draft called `0x61000` a "duplicate checksum offset". It is not. `0x61000` is where the *duplicated bootloader region begins*; that region's word-sum guard sits at its own final word, `0x70ffc`. The correction is recorded in log 84 and again in FINDINGS: "`0x61000` is the start of the duplicated region, not a checksum offset". The bytes at `0x61000` are just the start of another `SNC7320A` container copy, which you can see with `xxd`.

### 3.7 The eight-slot table, and the hole-versus-terminator correction

How many records are there, and how does the bootloader know when to stop reading them? The first reading (log 74) treated the table as a list ending in a zero **terminator**: record A, record B, then a zero record. That gave the right two records, but for the wrong reason.

Log 95 read the loop in `FUN_0000511c` and found no terminator at all:

```
for (uVar1 = 0; uVar1 < 8; uVar1 = uVar1 + 1) {
  if (*(int *)(param_1 + uVar1 * 0x10 + 0x28) != 0) {   // only the LENGTH field is tested
    ...
  }
}
```

The loop always runs **eight** slots and processes each one whose *length* is non-zero. There is no "stop at the first zero". The full table, as the bootloader sees it (log 95):

```
vendor
  slot0 active addr=0x60011000 len=0x58ac   crc=0x5e75c17a dst=0x18000000
  slot1 active addr=0x60021000 len=0x1e754  crc=0x1a76c116 dst=0x18000000
  slot2 hole   addr=0x60021000 len=0x0      crc=0x00000000 dst=0x00000000
  slot3 hole   addr=0x00000000 len=0x0      crc=0x00000000 dst=0x00000000
  ... slots 4-7 also holes
```

Slot 2 carries a stale non-zero *address* but a zero *length*. Under the terminator rule the loop would have stopped there. Under the real rule it is an inactive **hole**: skipped, but the loop keeps scanning slots 3 to 7. On both preserved images slots 3–7 are all zero, so the old rule "produced the right two records for the wrong reason" (FINDINGS, "SN_FWIN integrity record table", log 95).

Why the correction matters for anyone building a modified image: a non-zero-length slot with a zero address is an *active slot with a bad address*, an active slot *behind* a hole still contributes a checksum dependency, and a fully populated eight-slot table is legal. The tool `falchion_image.py` was rewritten to model the fixed eight-slot, length-gated scan, and a test asserts the divergence on a holed table so the mistake cannot come back (log 95).

### 3.8 The absence of signatures, stated honestly

Log 101 searched the whole bootloader for cryptographic constants (SHA, MD5, RSA, AES, TEA seeds) and for version, signature, key, auth, rollback and device strings. The only matches were the reflected CRC-32 polynomial at `0xc78c` and a reflected CRC-16 polynomial at `0xc76c`, both already explained by the CRC engine. No crypto, no version string, no device-ID gate (log 101).

But look at how the finding is worded. Log 102 corrected an earlier "None exist" to a scoped statement:

> "no cryptographic constant found... reach: a search over a fixed constant list. It does not exclude a check whose constants are computed rather than stored." (log 102)

and

> "no version, signature, key, auth or rollback string found... reach: a search over strings. A numeric version or rollback comparison would leave no string at all, so this says nothing about one." (log 102)

This is the single most important habit in this lesson. **"Not found by a search" is not "proven absent".** A constant-and-string search cannot see a check whose constants are computed at runtime, or a numeric version compare that uses no string. The evidence supports the hypothesis that a modified image can be accepted, but it does not *prove* there is no signature (FINDINGS: "This supports—but does not prove—the hypothesis").

### 3.9 The offline builder, and an overclaim it taught

If every integrity field is a recomputable checksum, an edited image can be made self-consistent. `build_modified_image.py` does exactly that: it applies a byte patch to a copy of the preserved image, recomputes all four fields, and re-verifies. Log 77's run patched one byte inside Candidate B (`0x3f66f: 0x52 -> 0x72`, changing an `R` to an `r` in a string) and showed:

- **Idempotent:** recomputing the *unmodified* image reproduces it byte-for-byte, so the builder's method matches the vendor's.
- **Naive patch fails:** without recompute, record B's checksum and the application word-sum both fail.
- **Rebuilt passes:** after recompute, all four fields pass.

That is genuinely useful. But log 77's conclusion line went too far. It said the run was "proving the checks are live". Log 84 caught the overclaim:

> "the run shows the four fields are reproducible offline. It does not show the bootloader accepts the image or that it boots." (log 84)

The difference is real. Reproducing a checksum offline proves *you understand the checksum*. It does **not** prove the device runs the checksum, accepts the image, or boots it, because two of the four boot gates are environmental and were still unresolved at the time (Lesson 10). Log 84 marked log 77's conclusion **superseded**, without editing the raw log. That is the correction culture: the mistake stays on the record, with a note pointing to the fix.

## 4. Decisions and why

| Decision | Why | Alternative rejected | Evidence (log) |
|---|---|---|---|
| Verify record A as plain CRC-32 first | A single match locks both the algorithm and the flash→file mapping | Assume the algorithm and mapping | 74 |
| When B wouldn't reproduce, read the verifier | Every reasonable CRC variant was ruled out; the code has the answer | Guess "encrypted" or "signed" | 74–75 |
| Model the table as a fixed eight-slot, length-gated scan | That is what `FUN_0000511c` actually does | Keep the "zero terminator" reading | 95 |
| State "no signature found" as a scoped search result | A constant/string search cannot prove absence | Say "None exist" | 101–102 |
| Build a recompute-and-verify tool offline | Proves the fields are reproducible, and supports a modification workflow | Flash a test and see | 77 |
| Downgrade "proves the checks are live" | Offline reproduction is not device acceptance | Leave the overclaim standing | 84 |

## 5. What went wrong, and how it was caught

**Record B looked impossible.**
- *Believed:* record B should be a plain CRC-32 of its file bytes, like record A.
- *True:* it is the sum of two per-`0x10000`-chunk CRC-32s, because the region spans two chunks (`0x1a76c116 = 0x35530359 + 0xe523bdbd`).
- *Caught by:* ruling out every CRC variant offline (log 74), then reading `FUN_00005028` (log 75).
- *Lesson:* when a checksum won't reproduce, the algorithm is in the verifier. Read it before inventing theories.

**The record table had an invented terminator.**
- *Believed:* the table was a list ending at the first zero record (log 74).
- *True:* `FUN_0000511c` scans a fixed eight slots and gates only on non-zero length; slot 2 is an inactive hole with a stale address (log 95).
- *Caught by:* reading the loop bound `uVar1 < 8` and the single length test.
- *Lesson:* getting the right answer for the wrong reason is still a bug. The reviewer reproduced a holed table that the old parser mis-read.

**`0x61000` was called a checksum offset.**
- *Believed:* `0x61000` held a duplicate bootloader checksum.
- *True:* `0x61000` is the *start* of the duplicated bootloader region; its word-sum is at `0x70ffc` (log 84).
- *Caught by:* the correction audit in log 84.
- *Lesson:* the start of a region and the location of its guard word are different addresses.

**"Proving the checks are live" (log 77).**
- *Believed:* recomputing the fields offline proved the checks were live.
- *True:* it proved the fields are reproducible offline; device acceptance and booting were still open (log 84).
- *Caught by:* the correction audit, which marked the conclusion superseded.
- *Lesson:* separate "I can reproduce this" from "the device enforces this". They are different claims with different evidence.

## 6. Try it yourself

Run everything from `keyboard/falchion-re/`.

**1. Check the integrity fields on the vendor image.** The tool decodes the record table and reproduces every field.

```
$ python3 tool/analyze_candidate_integrity.py
PROGRAM analyze_candidate_integrity
...
RECORDS
  [0] addr=0x60011000 len=0x58ac dst=0x18000000 stored=0x5e75c17a calc=0x5e75c17a match=True
  [1] addr=0x60021000 len=0x1e754 dst=0x18000000 stored=0x1a76c116 calc=0x1a76c116 match=True

WORD_SUMS
  bootloader: stored=0xfb665ae3 calc=0xfb665ae3 match=True
  application: stored=0x5d27c5a9 calc=0x5d27c5a9 match=True
  PASS SN_FWIN magic
  PASS record[0] checksum
  PASS record[1] checksum
  PASS bootloader word-sum
  PASS application word-sum

RESULT integrity_checks_ok=True
```

**2. Check the device dump.** The USB backup captured the application region only, starting at flash `0x10000`, so the tool needs `--base 0x10000`. Check `--help` first (the safety sheet says to):

```
$ python3 tool/analyze_candidate_integrity.py --help
usage: analyze_candidate_integrity.py [-h] [--base BASE] [image]
...
  --base BASE  flash offset represented by image byte zero (USB app dump: 0x10000)
$ python3 tool/analyze_candidate_integrity.py dumps/device/ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin --base 0x10000
...
RECORDS
  [0] addr=0x60011000 len=0x58ac dst=0x18000000 stored=0x7d552485 calc=0x7d552485 match=True
  [1] addr=0x60021000 len=0x1e780 dst=0x18000000 stored=0xeb0a9879 calc=0xeb0a9879 match=True

WORD_SUMS
  bootloader: SKIP (region absent from this partial image)
  application: stored=0x2d7486db calc=0x2d7486db match=True
  ...
RESULT integrity_checks_ok=True
```

The installed 1.59 checksums differ from the vendor 1.00.58 ones (the firmware is different), but they reproduce just as exactly, and the bootloader word-sum is skipped because that region isn't in the app-only dump.

**3. Reproduce the "impossible" checksum yourself.** This 10-line snippet uses only the standard library. It shows A, the failed whole-range CRC of B, the two-chunk sum that works, and the application word-sum:

```python
import zlib, struct
d = open('dumps/vendor/M605_V01_00_58.bin', 'rb').read()
a = zlib.crc32(d[0x11000:0x168ac])
b0 = zlib.crc32(d[0x21000:0x31000]); b1 = zlib.crc32(d[0x31000:0x3f754])
print('A      ', hex(a))
print('B whole', hex(zlib.crc32(d[0x21000:0x3f754])))
print('B sum  ', hex(b0), '+', hex(b1), '=', hex((b0 + b1) & 0xffffffff))
w = struct.unpack_from('<%dI' % (0x6c000 // 4), d, 0x10000)
print('app sum', hex(sum(w[:-1]) & 0xffffffff), 'stored', hex(w[-1]))
```

Real output:

```
A       0x5e75c17a
B whole 0x60c95a7b
B sum   0x35530359 + 0xe523bdbd = 0x1a76c116
app sum 0x5d27c5a9 stored 0x5d27c5a9
```

Line 2 is the "impossible" value `0x60c95a7b`. Line 3 splits B at the `0x10000` chunk boundary (file `0x31000`) and adds the two CRCs to get the stored `0x1a76c116`. Line 4 sums all but the last word of the application region and matches the guard word `0x5d27c5a9`.

**4. See the three word-sum guard words, and that `0x61000` is not one.**

```
$ python3 -c "
import struct;d=open('dumps/vendor/M605_V01_00_58.bin','rb').read()
for o in (0x0fffc,0x70ffc,0x7bffc,0x61000): print(hex(o), hex(struct.unpack_from('<I',d,o)[0]))"
0xfffc 0xfb665ae3
0x70ffc 0xfb665ae3
0x7bffc 0x5d27c5a9
0x61000 0x37434e53
```

`0x0fffc` and `0x70ffc` hold the same bootloader word-sum, because `0x61000..0x71000` is a copy of the bootloader. `0x7bffc` is the application guard. But `0x61000` holds `0x37434e53`, which is the ASCII `SNC7` of `SNC7320A`: it is the start of a container, not a checksum.

**5. Confirm the record table is eight slots, most of them holes.**

```
$ python3 -c "import struct
d = open('dumps/vendor/M605_V01_00_58.bin', 'rb').read()
for i in range(8):
    a, l, c, x = struct.unpack_from('<4I', d, 0x10024 + i*0x10)
    print('slot%d %-6s addr=0x%08x len=0x%-6x crc=0x%08x' % (i, 'active' if l else 'hole', a, l, c))"
slot0 active addr=0x60011000 len=0x58ac   crc=0x5e75c17a
slot1 active addr=0x60021000 len=0x1e754  crc=0x1a76c116
slot2 hole   addr=0x60021000 len=0x0      crc=0x00000000
slot3 hole   addr=0x00000000 len=0x0      crc=0x00000000
slot4 hole   addr=0x00000000 len=0x0      crc=0x00000000
slot5 hole   addr=0x00000000 len=0x0      crc=0x00000000
slot6 hole   addr=0x00000000 len=0x0      crc=0x00000000
slot7 hole   addr=0x00000000 len=0x0      crc=0x00000000
```

Slot 2 keeps a non-zero address with a zero length: the "hole" that the terminator reading mistook for the end.

## 7. Check your understanding

1. Record A matched a plain CRC-32 but record B did not. Why?

<details><summary>Answer</summary>

Record A is `0x58ac` bytes, which fits in one `0x10000`-byte chunk, so its checksum is a single CRC-32. Record B is `0x1e754` bytes, more than one chunk, so its checksum is `CRC32(chunk 0) + CRC32(chunk 1) = 0x35530359 + 0xe523bdbd = 0x1a76c116`. A plain CRC over B's whole range gives the unrelated `0x60c95a7b` (logs 74–76).
</details>

2. When the CRC of record B would not reproduce, what did the investigation do, and what did it *not* do?

<details><summary>Answer</summary>

It ruled out every CRC variant, seed and range offline (log 74), then read the bootloader's verify routine `FUN_00005028` to find the real algorithm (log 75). It did *not* jump to "it must be encrypted" or "it must be signed".
</details>

3. Is `0x61000` a checksum offset?

<details><summary>Answer</summary>

No. `0x61000` is the start of the duplicated bootloader region (its first bytes are `SNC7...`). That region's word-sum guard is at its final word, `0x70ffc`. Calling `0x61000` a checksum offset was an error corrected in log 84.
</details>

4. The bootloader has no SHA, RSA or AES constants and no signature string. Does that prove the firmware is unsigned?

<details><summary>Answer</summary>

No. It is a search result, not a proof. A check could compute its constants at runtime rather than store them, and a numeric version or rollback compare would leave no string. The evidence *supports* the no-signature hypothesis but does not prove it (logs 101–102, FINDINGS).
</details>

5. The offline builder recomputed every field and passed. What did that prove, and what did it not prove?

<details><summary>Answer</summary>

It proved the four integrity fields are reproducible offline, so they contain no secret. It did not prove the device accepts the image or boots it, because two boot gates are environmental. Log 77's "proving the checks are live" wording was an overclaim, corrected in log 84.
</details>

## 8. Sources

- [../FINDINGS.md](../FINDINGS.md): "Integrity and authentication", "SN_FWIN integrity record table and Candidate B checksum status (log 74)", "Bootloader integrity/verify path recovered (logs 75–76)"
- [../TIMELINE.md](../TIMELINE.md): "SN_FWIN record table and Candidate B checksum status", "Bootloader verify path read; all integrity fields resolved", "Corrections retained for auditability"
- [../logs/74-candidate-integrity-crc-analysis.txt](../logs/74-candidate-integrity-crc-analysis.txt), [../logs/75-ghidra-bootloader-verify-report.txt](../logs/75-ghidra-bootloader-verify-report.txt), [../logs/76-candidate-integrity-resolved.txt](../logs/76-candidate-integrity-resolved.txt)
- [../logs/77-image-builder-roundtrip.txt](../logs/77-image-builder-roundtrip.txt), [../logs/84-correction-audit.txt](../logs/84-correction-audit.txt)
- [../logs/95-phase1-record-scan-correction.txt](../logs/95-phase1-record-scan-correction.txt), [../logs/101-boot-acceptance-resolved.txt](../logs/101-boot-acceptance-resolved.txt), [../logs/102-phase4-and-phase5-review-corrections.txt](../logs/102-phase4-and-phase5-review-corrections.txt)
- [../tool/analyze_candidate_integrity.py](../tool/analyze_candidate_integrity.py), [../tool/falchion_image.py](../tool/falchion_image.py), [../tool/build_modified_image.py](../tool/build_modified_image.py)

[← Previous](08-ghidra.md) · [Course home](README.md) · [Next →](10-how-it-boots.md)
