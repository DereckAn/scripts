# Step 5 — Recovery backup of the installed firmware (plan only)

**Status: PLAN. No device interaction has occurred. Nothing here has been
executed.** This document is written so that a verified backup of the *installed*
firmware exists before any erase/program command is ever considered.

## Why this step exists

- The keyboard runs firmware **v1.59** (USB `bcdDevice`).
- The only full image we hold is `dumps/vendor/M605_V01_00_58.bin` (**v1.00.58**),
  a vendor reference that is **older** and is **not** a readback of this unit.
- Every write operation (roadmap step 4: erase `0x01`, program `0x51`) is
  destructive. Without a verified copy of the installed 1.59 image, a bad flash
  has **no guaranteed recovery**.

So step 5 = obtain and verify a byte-exact backup of what is on the keyboard now.
This is the gate that turns "bricked" into "restore from backup."

## Important: this is the first device interaction

Steps 1–4 were entirely offline (reading files we already had). Step 5 is the
first action that reads *from the keyboard*. Do not begin it without an explicit
decision to cross that line, and only after the safety rules below are in place.

## Two approaches

### Approach A — USB read-back via the bootloader (least invasive; recommended first)

The bootloader exposes a **READ** command (byte `0x05`, handler `FUN_00003b64`,
see FINDINGS "Bootloader write/erase/program protocol"). Unlike erase/program, the
read handler has **no `0x10000..0x7c000` address guard**, so it can read the whole
memory-mapped flash (`addr | 0x60000000`). A full dump of the installed image is
therefore possible over USB, with no disassembly.

Sequence (each item is a device interaction — do not run until authorised):
1. `Jump to Bootloader` so the device re-enumerates as PID `1b7f`
   ("Gaming Keyboard Bootloader2"). This is a reversible state change: on
   power-cycle the bootloader re-verifies and boots the intact app.
2. Read `Bootloader Version` to confirm bootloader mode.
3. Loop the READ command across `0x00000..0x7c000` (and up to the true chip size),
   assembling a full image.
4. Repeat the entire dump **at least 3 times** and require identical SHA-256.
5. Power-cycle to return to the application; confirm normal enumeration
   (VID:PID `0b05:1b7e`, v1.59).

Risks / caveats:
- Entering bootloader mode is a real command and a state change (low risk, but
  it *is* the first device write of any kind — a control transfer).
- We are trusting the bootloader's own read path; a hardware read (Approach B) is
  more independent. If Approach A and B ever disagree, trust B.
- Do **not** send erase (`0x01`) or program (`0x51`) at any point.

### Approach B — Hardware read-back (gold standard; independent of device firmware)

The firmware lives in memory-mapped flash at `0x60000000` — an **external SPI NOR
(U5)** on the board. A direct SPI read is fully independent of the running
firmware and is the authoritative backup.

Hardware:
- A **3.3 V** SPI flash reader (e.g. a Pi/FT2232 + `flashrom`, or a known-good
  3.3 V programmer). **Not** an unmodified 5 V CH341A.
- SOIC-8 test clip (in-circuit) or hot-air to desolder U5 if in-circuit reads are
  contended.
- Multimeter to confirm Vcc = 3.3 V and to verify the pinout before connecting.

Procedure (all read-only):
1. Identify U5: package, markings, and JEDEC ID via the read-only `0x9F` command
   only. Confirm capacity ≥ image size.
2. Prevent bus contention: hold the MCU in reset (or remove its power / desolder
   U5) so the MCU is not driving the SPI bus during the read.
3. Connect the programmer; read JEDEC ID first, then dump the **full chip**.
4. Dump **at least 3 times**; require all SHA-256 identical before accepting.
5. **Never** issue Write Enable (`0x06`), Page Program (`0x02`), or any Erase
   (`0x20` / `0x52` / `0xD8` / `0xC7`). Read/JEDEC-ID only.

## Acceptance criteria for the backup (either approach)

- **≥ 3 identical full reads** (SHA-256 match) — a single dump is not trusted.
- JEDEC ID and chip size recorded and consistent.
- The dump **parses** as a valid boot container: run
  `python3 tool/analyze_boot_structures.py <dump>` — the `SNC7320A` / `SN_BCFG` /
  `SN_FWIN` magics and the boot-gate must all pass.
- The dump's integrity fields reproduce: run
  `python3 tool/analyze_candidate_integrity.py <dump>` — records and word-sums
  must self-verify.
- It should reflect **v1.59** and therefore differ from the 1.00.58 reference;
  record the exact differences.
- Store the backup with its SHA-256, in at least two independent locations, and
  add its hash to the artifact manifest (do **not** commit the raw image if it
  exceeds hosting limits — treat it like the preserved ZIP).

## Hard rules (apply to both approaches)

1. Read-only only. No erase, program, Write-Enable, or `Programming Success`
   path is ever exercised during preservation.
2. Never accept a single read; require ≥ 3 identical dumps.
3. Confirm 3.3 V and pinout before any hardware connection.
4. Do not proceed to any flashing (a separate, later, still-gated procedure)
   until this backup exists, verifies, and is stored redundantly.

## Only after a verified backup

With a verified 1.59 backup in hand, a modified image built and validated offline
by `tool/build_modified_image.py` (integrity + boot gate) could be flashed via the
step-4 protocol — and if anything goes wrong, the backup is the recovery image.
That flashing procedure is intentionally **not** part of this plan.
