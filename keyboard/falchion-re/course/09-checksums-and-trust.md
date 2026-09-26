# Lesson 09 — Checksums and trust

> **In one sentence:** The firmware protects itself with ordinary checksums, a CRC-32 per region and a simple word-sum over whole areas, not with a cryptographic signature; working out exactly *how* the bootloader adds them up is what turned an "impossible" number into a reproducible one.
>
> **You will learn:**
> - what a checksum is, starting from a simple sum and building up to CRC-32 and its polynomial `0xedb88320`
> - how the `SN_FWIN` record table at `0x10024` lists each region with its stored check value
> - why record A matched a plain CRC-32 and record B (`0x1a76c116`) did not, and every variant log 74 ruled out
> - how reading the bootloader's verify routines (`FUN_0000511c`, `FUN_00005028`, `FUN_000026d0`) resolved it
> - why "no signature found" is a search result and not a proof, and why the builder round trip was overclaimed
>
> **Time:** ~75 minutes · **Prerequisites:** [Lesson 2](02-how-computers-count.md), [Lesson 6](06-the-firmware-file.md), [Lesson 8](08-ghidra.md)

## 1. The story (kid version)

When you buy groceries, the receipt lists every item and a total at the bottom. If someone changes one price after