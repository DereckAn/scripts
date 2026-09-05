# Does the firmware show dual-core participation?

The SNC7320-series product brief states the series has **dual Cortex-M3 cores**
(`notes/references.md`). That raises a specific question about this firmware:
do the multiple executable images, the shared-RAM accesses and the interrupt
layout indicate two cores participating, or one core running stages in sequence?

Offline and read-only; no device was accessed. Every claim below carries its own
confidence.

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

## The unexplained image is the better candidate

**Confidence: hypothesis.** Phase 3 (log 98) established that the RAM image at
flash `0x74000..0x7c000`, which log 43 mapped at runtime `0x18038000`, is
reachable from **no SN_FWIN record and no scatter region** on the recovered boot
path. It has its own vector table and its own reset vector (`0x180381c1`).

An image with its own vector table that the primary boot path never loads is
exactly what a second core's firmware would look like. That makes it the
strongest dual-core candidate in the flash. It is a hypothesis and nothing more:
nothing recovered so far shows anything *starting* it, and an unused or
factory-test image would look the same.

What would settle it: finding the register write that releases a second core
from reset, or finding a load of `0x18038000` as a code entry. Neither has been
found. `map_hardware_interfaces` reports no access to `0x18038000` from either
analysed image.

## Shared-RAM accesses that could be mailboxes

**Confidence: observed accesses, hypothesis as to purpose.**

- The entry image holds **48 words pointing into application RAM outside the
  application's own code range** (log 100). Those are shared variables between
  two sequential stages on one core, which is the simpler explanation, but the
  same shape would serve a mailbox.
- The bootloader polls a scan buffer at `0x18012ac8` and reads a one-shot flag
  at `0x20000ffc` (log 101). Both are cross-*stage* channels, again on one core.
- `0x20000ffc` sits in the second RAM range. A word that survives a system reset
  and is read by the next stage is a reset-surviving mailbox in the general
  sense, but its two known users — application and bootloader — are stages, not
  cores.

No access pattern recovered so far has the shape of a core-to-core mailbox:
there is no doorbell register write paired with a matching poll in a *different*
image, and no interrupt whose handler exists in one image while its trigger is
written by another.

## Interrupts

**Confidence: observed.** Nine external interrupt slots are live. Software
enables exactly two of them, IRQ6 and IRQ38, through `NVIC_ISER0/1`, and both
hold non-default handlers. Every live handler lives in either the entry image or
the application, both of which run on the core that owns that NVIC. Nothing
points at the `0x18038000` image.

## Answer, as far as the evidence reaches

**One core is doing everything the recovered boot path describes.** The multiple
images are sequential stages, the shared RAM is inter-stage, and the interrupts
belong to a single NVIC.

**Dual-core participation is neither shown nor excluded.** The brief says the
silicon has two cores; the unexplained `0x18038000` image is a plausible second
core payload; and no start mechanism for it has been found. That is the precise
state of the question, and it is a named blocker rather than a conclusion.
