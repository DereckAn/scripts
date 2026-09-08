# Does the firmware show dual-core participation?

The SNC7320-series product brief states the series has **dual Cortex-M3 cores**
(`notes/references.md`). That raises a specific question about this firmware:
do the multiple executable images, the shared-RAM accesses and the interrupt
layout indicate two cores participating, or one core running stages in sequence?

Offline and read-only; no device was accessed. Every claim below carries its own
confidence.

> **Updated by log 118.** The `0x18038000` image has now been imported and
> analysed. Sections marked *superseded* are kept rather than deleted, because
> the question moved and the record should show how.

## The two images that were the obvious candidate are *not* two cores

**Confidence: observed.** Phase 4 (log 101) settled this. The bootloader does
not start a second core and hand it an image. It compares the selected entry
against the constant `0x60011000`, copies a fixed `0x10000` bytes from there to
address 0, writes `AIRCR` with `VECTKEY | SYSRESETREQ`, and spins until the
reset lands. That is a **sequential stage handoff on one core**, not a launch.

The entry image (Candidate A) and the application (Candidate B) are likewise
sequential on one core: Candidate A's own scatter table copies Candidate B from
flash into RAM at `0x18000000` and then branches into it through one of two
code pointers at entry-image offsets `0x1994` and `0x19cc`. Both run in the same
vector table — the application owns seven of the live interrupt handlers while
the table itself lives in the entry image.

So the count of executable images is **not** evidence of dual-core operation.

## The unexplained image is the better candidate — and it is no longer unexplained

**Superseded in part.** Phase 3 (log 98) established that the RAM image at flash
`0x74000..0x7c000`, runtime `0x18038000`, is reachable from no SN_FWIN record
and no scatter region. Log 113 then found what starts it. Log 118 imported it.

An earlier version of this note said "nothing recovered so far shows anything
*starting* it" and "`map_hardware_interfaces` reports no access to `0x18038000`
from either analysed image". **The first half is withdrawn** — log 113 step 4
recovered the start. The second half stands and is not a contradiction: the
application never *accesses* that RAM, it hands the *flash* address `0x60074000`
to a start routine.

What log 118 adds, all **observed**:

- the image is **byte-identical in 1.00.58 and 1.59**. Over the whole range the
  two releases differ in four bytes, and all four are the application region's
  additive word-sum at logical `0x7bffc`, which merely falls inside the range.
  This is live, maintained firmware that simply did not change, not a stale
  factory leftover — and the image's real extent ends at `0x7bffb`.
- it has a **73-entry vector table**, 57 external slots, of which 56 share one
  default handler. Exactly one external interrupt, **IRQ3**, has its own
  handler, and that handler reads and writes `0x45000300`.
- its reset handler reads **VTOR** (`0xe000ed08`) and loads SP from it, then
  runs one init function and falls into an endless loop. It has fault handlers
  with `printf`-style diagnostics naming `SCB->BFAR`.
- it is a **service payload, not an application**: no scheduler, no task table,
  no USB and no storage code.

## The mailbox is real, and both halves are now recovered

**Confidence: observed.** This supersedes the old section's conclusion that "no
access pattern recovered so far has the shape of a core-to-core mailbox".

The shared word log 113 found is one field of a ring buffer:

| address | role | owner |
|---|---|---|
| `0x20000000` | head index | the client |
| `0x20000004` | tail index | the second context |
| `0x20000008` | 8 records of `0x2c` bytes | shared |

The server at `0x1803af90` writes `0x12345678` to the head word **once**, as a
server-is-up signal, before that same word starts being used as the head index.
It then spins while head equals tail and dispatches record byte 0 through a
16-entry `tbb` table, 10 of whose opcodes have their own handler. It advances
the tail after each record.

The client is entry-image `0x1b7c`, inside the `0x1854..0x20be` block Ghidra had
never disassembled because nothing reaches it. It fills a record, writes opcode
`0x0f`, advances the head modulo 8, and spins until the tail catches up.

**That is a doorbell paired with a matching poll in a different image** — the
exact shape the old version of this note said was missing.

## Interrupts

**Confidence: observed.** Nine external interrupt slots are live in the entry
image and the application. Software enables exactly two of them, IRQ6 and IRQ38,
through `NVIC_ISER0/1`, and both hold non-default handlers.

The second context has its **own** table with its own single live external
handler, IRQ3, and it reads VTOR at reset. Two tables, each with its own live
handler, is consistent with two NVICs — but a single core that relocates VTOR
between stages would look the same, so this is not decisive on its own.

## Answer, as far as the evidence reaches

**The mechanism is settled; the silicon is not.**

**Confidence: observed** — there are two execution contexts with a real
producer/consumer channel between them, a start register, and separate vector
tables. The second context is a command server with its own hardware territory:
`0x40040000`, `0x40018000` and `0x4001c000` appear in its census and in neither
the application's nor the entry image's.

**Confidence: unresolved** — whether they run *concurrently*. Nothing recovered
shows the application still executing while the second context runs. The client
spins waiting for the tail, which is equally consistent with a second core and
with a coroutine on one core that switches at the spin. Settling it needs
evidence that both contexts make progress at once, and no such evidence exists.

**What would settle it:** identifying `0x45000100` bit 15 as a core-release
control rather than a clock or reset gate for a peripheral, or finding an
interrupt whose handler lives in one image while its trigger is written by
another. Neither has been found.

## What it does *not* own

Recorded here because the tempting conclusion is wrong. The second context is
the leading candidate owner of the Hall acquisition — that producer was never
found in either analysed image — and it does run a real converter loop. But:

- its 240-iteration write-strobe-readback loop stores results to an **in-image**
  array, and the only three references to that array are all inside the image;
- its only demonstrated write into application RAM is a 150-byte `memset` to
  `0xff` at `pointer+0x3f2`, which is the 150 bytes **immediately after** the
  travel array at `pointer+0x35c`, not the array itself;
- the travel array's address still appears in **no aligned word of any image**,
  this one now included.

So the acquisition gate is **narrowed, not closed**. See
`notes/second-context.md` for the full analysis and
`notes/platform-dependencies.md` for the gate's current state.
