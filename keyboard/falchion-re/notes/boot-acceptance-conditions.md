# Boot-acceptance conditions of the installed bootloader

Generated from `tool/analyze_boot_acceptance.py`, with the decompiles under
`ghidra/decompiles/` as supporting evidence. Offline and read-only; no device
was accessed and no dump was modified.

Every constant here is read out of the **mirrored bootloader copy inside the
installed dump** — logical `[0x61000,0x71000)`, which log 100 proved
byte-identical to the vendor 1.00.58 primary and backup bootloader. The
bootloader code image is `[0x62000,0x71000)`, `0xf000` bytes, SHA-256
`c244aef0…d870c`, which is the same byte range the earlier analysis called
`bootloader_primary.bin`. So these rules come from bytes that are on the device,
not from the vendor file alone.

## The two unknowns this phase set out to resolve

Both are resolved, and neither turned out to be an integrity check.

### `FUN_000029d4` — a recovery key-combination poll

```c
undefined4 FUN_000029d4(void) {
  for (i = 0; i < 100; i++) {          /* settle: tick the scan 100 times */
    FUN_00005272(1); FUN_00002d4a(); FUN_00005272(0); FUN_00003732(1000);
  }
  streak = 0;
  for (i = 0; i <= 99; i++) {
    FUN_00005272(1); FUN_00002d4a(); FUN_00005272(0);
    if (*DAT_00002a40 == 0xa0 && DAT_00002a40[4] == 0x100) {
      if (streak == 0x1e) return 1;    /* 31st match -> block boot */
      streak++;
    } else streak = 0;
    FUN_00003732(1000);
  }
  return 0;                            /* not held -> allow boot */
}
```

`FUN_00005272` is enable/disable-IRQ (`isCurrentModePrivileged` then
`enableIRQinterrupts`), `FUN_00002d4a` is the bootloader's own four-call scan
tick, and `DAT_00002a40` is `0x18012ac8`, a RAM buffer inside the region the
bootloader's scatter table zero-initialises. So the function polls the key scan
and returns 1 — blocking the boot — when a fixed pattern is held for **31
consecutive samples**: `streak` starts at zero and the `cmp r5,#0x1e` at
`0x2a20` is tested *before* the increment, so the return happens on the 31st
match.

**It is not a check on the image.** A custom image needs to satisfy nothing
here; it only needs the recovery combination not to be held at power-on.

### The top-level comparison — `iVar2 == DAT_00007f98`

`DAT_00007f98` is **`0x60011000`**. The orchestrator compares the entry value
returned by the container scan against that constant, so the SN_FWIN `+0x10`
entry pointer must be exactly `0x60011000`. **The entry image cannot be
relocated.**

## A third gate nobody had named

`FUN_00002a44` reads `0x20000ffc` and compares it with `0x73207320` (the bytes
`" s s"`). When they match it clears the word and returns 1, blocking the boot.
It is a **one-shot, software-requested bootloader entry flag**: the application
writes the magic to that RAM word and resets, and the bootloader then stays in
its updater instead of booting. That is consistent with the reset-only entry
report recovered in logs 87 and 88.

## The complete accept expression

`FUN_00007ec8` jumps only when all four gates pass. Two are environmental and
two are properties of the image.

## The transfer of control is a copy and a reset, not a branch

`FUN_00007fa8(entry)` is `ldr r1,[ptr]; ldr r1,[r1]; str r0,[r1,#0x1c]`, so it
dereferences VTOR **before** adding the offset: the entry lands at
**`*(VTOR) + 0x1c`**, slot 7 (the first Reserved slot) of whatever vector table
VTOR points at when it runs. It is *not* written to `0xe000ed08 + 0x1c`, which
would be SCB SHCSR. The concrete address depends on VTOR at runtime and is
therefore not a static property of the image. Then
`BootHandoff(0, entry, 0x10000)` runs — a `0x50`-byte routine the
bootloader scatter-loads from program offset `0xcdfc` to RAM `0x18010000`:

```
msr primask, #1                  mask interrupts
copy (len >> 2) words from src to dst      -> 0x10000 bytes from 0x60011000 to 0
dsb
AIRCR = (AIRCR & 0x700) | 0x05fa0000 + 4   VECTKEY | SYSRESETREQ, PRIGROUP kept
dsb
b .                              spin until the reset lands
```

**Observed:** the bootloader copies a fixed 64 KiB window from the entry
address to address 0 and then requests a system reset. That much is in the
instructions.

**Not established:** what executes after that reset. Address 0 must be backed by
writable storage for the copy to mean anything, but the register or strap that
aliases a RAM or remap window there is unidentified, and any ROM or first-stage
behaviour ahead of the bootloader is unexamined. So "the application runs from
address zero" is an *inference*, not a recovered fact, and log 103 downgraded
the earlier wording that stated it flatly.

What the handoff does settle, and what it only supports:

- **Settled:** the SN_FWIN record's `+0xc` word is not a load destination. The
  destination is the constant `0` in the orchestrator's call, and
  `FUN_0000511c` never reads `+0xc`.
- **Settled:** the `0xff` fill from `0x168ac` to `0x21000` is inside the copied
  window, because the copy length is fixed at `0x10000` regardless of record
  slot 0's `0x58ac`.
- **Strongly supported, not proven:** that Candidate A is linked at base `0`
  because it executes there. Its literals, reset vector and region table are all
  base-0 consistent, and the copy destination is 0, which fits — but the alias
  that would make address 0 executable is still unresolved.

## Searches that returned nothing

The plan asked for additional hashes, signatures, monotonic versions, rollback
rules, device IDs and configuration-dependent gates. **These are search results,
not proofs of absence** — log 103 corrected the earlier "None exist". A
constant-and-string search cannot establish that no check exists: constants can
be computed rather than stored, and a numeric comparison leaves no string at
all. What was searched, and how far each result reaches, is listed in the tool
output below. In summary, no indicator was found by these searches:

- **no cryptographic constant found** among the twelve searched at every byte
  offset. The only checksum constants present are the reflected CRC-32
  polynomial `0xedb88320` at program `0xc78c` and a reflected CRC-16 polynomial
  at `0xc76c`, both accounted for by the CRC engine recovered in log 75. This
  does not exclude a check whose constants are computed.
- **no version, signature, key, authentication or rollback string found.** The
  matching strings are all USB HID descriptor text plus `[BLD] CRC Verify
  PASS!!`. A numeric version or rollback comparison would leave no string.
- **no device-ID gate found in the accept expression.** The only USB identity
  words present are the bootloader's own vendor and bootloader product IDs, and
  none of the four gates reads an identity. Call paths outside those four gates
  were not exhaustively traced.
- **no configuration-dependent gate found in the accept expression.** The accept
  expression is the four gates above and nothing else. That is complete for the
  accept expression and silent about the rest of the bootloader.

## What a builder must satisfy, and what it cannot buy

The image rules are listed in the tool output below. Five are marked *proven*;
one — keeping the entry image inside the copied 64 KiB window — is marked
*policy*, because no bootloader branch tests it and a longer record would simply
have its tail left uncopied (log 103 downgraded it from proven).

Two structural caveats. **Two of the four gates are environmental**, so an image
that satisfies every rule can still be refused because the recovery combination
is held or the RAM flag is set. And satisfying the rules says nothing about
whether the image then runs: it means the bootloader will copy it to address 0
and request a reset, and what happens after that reset depends on the
unresolved address-0 alias.

## Still unresolved

- What makes address 0 writable, and therefore what actually executes after the
  reset. `BootHandoff` copies there and resets, so a RAM or remap window must be
  aliased at 0, but the register that arranges it is not identified. This is the
  one remaining gap in the boot path, and it is what keeps "the application runs
  from address zero" an inference.
- Which physical keys produce the recovery pattern. Only the RAM buffer and the
  matched values are known.
- Any ROM or first-stage condition ahead of this bootloader.

## Raw tool output

```text
PROGRAM analyze_boot_acceptance
PURPOSE the bootloader's boot-acceptance conditions, from installed bytes
IMAGE_SHA256 fc6128ab089e4fd712b172c54cd88b7f28476b55bdac688134e052281ded637b
BOOTLOADER_SHA256 c244aef0a92424cc92354a8cebd312be3098780d1ec062e05e5d5333e38d870c (mirrored copy at logical 0x62000, 0xf000 bytes, program base 0)
LITERAL backup_container @prog 0x2b0c = 0x60060000  DAT_00002b0c, the second container FUN_00002af0 falls back to
LITERAL ram_entry_flag_pointer @prog 0x2a60 = 0x20000ffc  DAT_00002a60, the RAM word FUN_00002a44 reads
LITERAL ram_entry_magic @prog 0x2a64 = 0x73207320  DAT_00002a64, the magic FUN_00002a44 looks for in RAM
LITERAL recovery_scan_buffer @prog 0x2a40 = 0x18012ac8  DAT_00002a40, the RAM scan buffer FUN_000029d4 polls
LITERAL selected_entry_constant @prog 0x7f98 = 0x60011000  DAT_00007f98, the value the selected entry must equal before the jump
LITERAL systick_reload @prog 0x7f9c = 0x000278d0  DAT_00007f9c, the reload the service loop programs when no image is booted
LITERAL vtor_pointer @prog 0x7fb0 = 0xe000ed08  DAT_00007fb0, the register FUN_00007fa8 writes the entry into
LITERAL word_sum_base @prog 0x277c = 0x60010000  DAT_0000277c, the base FUN_000026d0 sums from

ACCEPT EXPRESSION — FUN_00007ec8 jumps only when all four pass
  GATE 1 [environment] recovery key combination
    function: FUN_000029d4
    requirement: must return 0
    evidence: polls the scan buffer at 0x18012ac8 up to 100 times, enabling and disabling interrupts around a scan tick each time, and returns 1 once the pattern (+0x0 == 0xa0 and +0x10 == 0x100) has held for 31 consecutive samples: the counter starts at zero and the cmp r5,#0x1e at 0x2a20 is tested before the increment, so the return happens on the 31st match
    blocks boot when: the combination is held at power-on
  GATE 2 [image] selected entry equals the bootloader's constant
    function: iVar2 == DAT_00007f98 (0x60011000)
    requirement: the SN_FWIN entry pointer must be exactly 0x60011000
    evidence: a literal-pool word in the orchestrator, compared with the value FUN_00002af0 returned from the container scan
    blocks boot when: the image declares any other entry address
  GATE 3 [environment] software bootloader-entry flag
    function: FUN_00002a44
    requirement: must return 0
    evidence: reads 0x20000ffc and compares it with 0x73207320; when equal it clears the word and returns 1, so the flag is one-shot
    blocks boot when: the application set the magic and reset
  GATE 4 [image] application-region word-sum
    function: FUN_000026d0(0x6c000)
    requirement: must return 0
    evidence: sums every 32-bit word of 0x10000..0x7c000 in 0x1000-byte pages and requires the final word to equal the sum; an all-0xff first page also fails
    blocks boot when: the stored guard word does not equal the sum

TRANSFER OF CONTROL
  copy_destination: 0x0
  copy_length: 0x10000
  entry_parked_in: *(uint32_t *)0xe000ed08 + 0x1c
  entry_parked_in_basis: vector slot 7, the first Reserved slot, of the table VTOR points at when FUN_00007fa8 runs. The runtime value of VTOR is not a static property of the image, so no fixed address is claimed.
  mechanism: copy then system reset, not a branch
  reset_request: AIRCR = (AIRCR & 0x700) | 0x05fa0000 + 4, i.e. VECTKEY with SYSRESETREQ, preserving PRIGROUP
  routine_length: 0x50
  routine_program_offset: 0xcdfc
  routine_runtime_address: 0x18010000

IMAGE RULES A BUILDER MUST SATISFY
  [proven] entry pointer is fixed
    SN_FWIN +0x10 must be exactly 0x60011000. The entry image cannot be relocated.
    evidence: orchestrator gate 2, a constant comparison against DAT_00007f98
  [policy — no control-flow dependency demonstrated] POLICY: keep the entry image inside the copied window
    0x10000 bytes are copied from the entry address to 0x0 regardless of the record length. No bootloader branch tests whether the record fits: a longer record would simply have its tail left uncopied. Keeping the image inside the window is therefore a conservative policy for a builder, not a recovered bootloader requirement.
    evidence: BootHandoff, scatter-loaded from bootloader program 0xcdfc to 0x18010000, called as (0, entry, 0x10000). The absence of a length test is what makes this a policy rather than a rule.
  [proven] application word-sum must be correct
    the final word of the application region must equal the 32-bit sum of every preceding word in it.
    evidence: orchestrator gate 4; base and length both read from bootloader constants rather than assumed
  [proven] every active record's chunked-CRC sum must be correct
    FUN_0000511c scans all eight record slots and verifies each slot whose length is nonzero.
    evidence: log 75 decompile, confirmed by log 95
  [proven] the entry image's initial SP must be in RAM
    FUN_00005240 dereferences the entry pointer and requires the first word to fall in an observed RAM range.
    evidence: log 75 decompile
  [proven] SN_FWIN magic and the container chain must be intact
    FUN_00008000 walks the boot-priority table, checks the SN_FWIN magic and only then validates the entry and records.
    evidence: log 75 decompile

SEARCHES THAT RETURNED NOTHING
  Search results, not proofs of absence.
  no cryptographic constant found
    searched: Searched the 0xf000-byte bootloader at every byte offset for the 32-bit constants 0x428a2f98, 0x6a09e667, 0x67452301, 0xefcdab89, 0xd76aa478, 0x5a827999, 0xedb88320, 0x04c11db7, 0x1021, 0x8408, 0x63636363 and 0x9e3779b9. Only 0xedb88320 at program 0xc78c and 0x8408 at 0xc76c are present, both accounted for by the CRC engine of log 75.
    reach: a search over a fixed constant list. It does not exclude a check whose constants are computed rather than stored.
  no version, signature, key, auth or rollback string found
    searched: Extracted every ASCII run of five or more printable bytes and matched them against ver/sign/rsa/sha/key/auth/roll/devi case variants. The only hits are USB HID descriptor text and '[BLD] CRC Verify PASS!!'.
    reach: a search over strings. A numeric version or rollback comparison would leave no string at all, so this says nothing about one.
  no device-ID gate found in the accept expression
    searched: The only USB identity words in the bootloader are 0x0b05 and 0x1b7f, its own vendor and bootloader product IDs, and none of the four gates decompiled for this phase reads an identity.
    reach: complete for the four gates, which were read in full. Call paths elsewhere in the bootloader were not exhaustively traced.
  no configuration-dependent gate found
    searched: The accept expression in FUN_00007ec8 is the four gates listed above and nothing else, and none of the four reads stored configuration.
    reach: complete for the accept expression, silent about the rest of the bootloader.

  PASS the mirrored bootloader copy is the analysed image — c244aef0a92424cc92354a8cebd312be3098780d1ec062e05e5d5333e38d870c
  PASS the image's SN_FWIN entry pointer equals the bootloader's constant — 0x60011000 vs 0x60011000
  PASS the word-sum region the bootloader checks is the application region — 0x10000..0x7c000 vs 0x10000..0x7c000
  PASS the fixed handoff copy window lies inside the application region — 0x11000..0x21000 inside 0x10000..0x7c000
  PASS record slot 0 begins at the copy window's start — 0x11000 vs 0x11000
  PASS record slot 0 fits inside the copy window — 0x168ac <= 0x21000
  PASS the handoff routine is the analysed 0x50-byte block — 1e4183918235efcdd7a0ded8055742bc9e51015e8da874f4604dd6861df7dee8
  PASS the RAM bootloader-entry magic is printable ASCII — b' s s'
  PASS integrity: backup SNC7320A magic
  PASS integrity: backup SN_BCFG magic
  PASS integrity: backup bootloader pointer
  PASS integrity: backup declared size
  PASS integrity: backup slot0 -> SN_FWIN
  PASS integrity: backup slot1 empty
  PASS integrity: SN_FWIN magic
  PASS integrity: SN_FWIN CRC-enable gate nonzero
  PASS integrity: entry equals record[0] address
  PASS integrity: record ranges inside application region
  PASS integrity: entry pointer equals the bootloader constant
  PASS integrity: policy: entry record lies inside the fixed handoff copy window
  PASS integrity: record[0] checksum
  PASS integrity: record[1] checksum
  PASS integrity: entry initial-SP in observed RAM ranges
  PASS integrity: entry reset vector is Thumb and within record[0] length
  PASS integrity: application word-sum
  PASS integrity: bootloader_mirror word-sum
  PASS integrity: application word-sum recomputes — stored 0x2d7486db vs computed 0x2d7486db
  PASS integrity: bootloader_mirror word-sum recomputes — stored 0xfb665ae3 vs computed 0xfb665ae3
RESULT image_rules_ok=True checks_run=28 gates=4 rules=6
RESULT_MEANING image_rules_ok covers only the two IMAGE gates and the integrity checks they rest on. The two environmental gates cannot be evaluated from an image at all, so this is never a statement that the bootloader would accept this image, let alone that it would run.
UNRESOLVED What makes address 0 writable is not established from these bytes. BootHandoff copies there and then resets, so a RAM or remap window must be aliased at 0, but the register that arranges it is not identified.
UNRESOLVED The recovery scan pattern (+0x0 == 0xa0, +0x10 == 0x100) is read from a RAM buffer the bootloader's own scan tick fills. Which physical keys produce it is not established.
UNRESOLVED Any ROM or first-stage condition ahead of this bootloader is still unexamined.
LIMITATION Two of the four gates are environmental, so an image that satisfies every rule here can still be refused because the recovery combination is held or the RAM entry flag is set. Passing the image rules is necessary, not sufficient, and says nothing about whether the image then runs correctly.
```
