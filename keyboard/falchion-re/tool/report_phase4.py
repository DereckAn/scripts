#!/usr/bin/env python3
"""Write the Step 6 Phase 4 report artifacts.

A repository-tracked generator, so the note is reproducible. Re-running it must
produce byte-identical files, and `--check` fails if the committed files have
drifted.

Artifacts written under `notes/`:

  boot-acceptance-conditions.md    the four boot gates, the rules, the negatives
  boot-acceptance-conditions.json  the same, machine-readable

No device access. Examples:
    python3 tool/report_phase4.py
    python3 tool/report_phase4.py --check
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_boot_acceptance as ba
import falchion_image as fi

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"

ARTIFACTS = ("boot-acceptance-conditions.md",
             "boot-acceptance-conditions.json")

PROSE = r"""# Boot-acceptance conditions of the installed bootloader

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

"""


def render():
    acceptance = ba.analyze(fi.ImageView(ba.INSTALLED.read_bytes(), 0x10000))
    body = PROSE + "## Raw tool output\n\n```text\n"
    body += "\n".join(ba.report_lines(acceptance))
    body += "\n```\n"
    return {
        "boot-acceptance-conditions.md": body,
        "boot-acceptance-conditions.json": json.dumps(
            ba.to_dict(acceptance), indent=2, sort_keys=True) + "\n",
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify the artifacts on disk match a fresh render")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        rendered = render()
    except (OSError, ValueError, fi.ImageFormatError) as exc:
        print(f"RESULT reports_written=0 error={exc}")
        return 1
    stale = []
    for name, text in rendered.items():
        path = NOTES / name
        if args.check:
            current = path.read_text() if path.exists() else None
            if current != text:
                stale.append(name)
            continue
        path.write_text(text)
        print(f"WROTE notes/{name} ({len(text)} bytes)")
    if args.check:
        for name in ARTIFACTS:
            print(f"  {'STALE' if name in stale else 'CURRENT'} notes/{name}")
        print(f"RESULT reports_current={not stale} stale={len(stale)}")
        return 1 if stale else 0
    print(f"RESULT reports_written={len(rendered)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
