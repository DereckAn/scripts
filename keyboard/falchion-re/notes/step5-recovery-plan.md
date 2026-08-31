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

The bootloader exposes a **READ** command over 64-byte vendor-HID reports (usage
page `0xFF01`, no report ID). The exact wire framing is decoded in FINDINGS
"Bootloader vendor-HID wire framing (READ path)" (log 82).

**Important scope limit (corrected):** the READ execute-trigger enforces
`0x10000 <= addr <= 0x7bfff` and `length <= 0x30` per transfer. So the USB read
covers **only the application region `[0x10000, 0x7c000)`** (SN_FWIN header, both
candidates, and the backup-container area) — it **cannot** read the bootloader
region `[0x0, 0x10000)`. That is acceptable for recovery: the bootloader region
is also *unwritable* over USB (erase/program are guarded to the same range), so it
cannot be corrupted by any flash we could perform and therefore never needs
restoring. A USB read of `[0x10000, 0x7c000)` is a sufficient recovery backup for
app-region modifications. (Only a hardware read, Approach B, can also capture the
bootloader.)

Sequence (each item is a device interaction — do not run until authorised). No
unlock is needed for READ (only erase/program require the `ASUSHIDFWU` unlock):
1. Enter bootloader mode (jump-to-bootloader, see the app path below) so the
   device re-enumerates as PID `1b7f` ("Gaming Keyboard Bootloader2"). Reversible:
   a power-cycle re-verifies and boots the intact app.
2. Query status (`report[0]=0x8f`) to confirm bootloader mode / idle.
3. For each chunk across `0x10000..0x7c000` (chunk `<= 0x30` bytes):
   - `report[0]=0x20`, payload = addr as 4 bytes little-endian — set address.
   - `report[0]=0x21`, payload = length u16 LE (`<= 0x30`) — set length.
   - `report[0]=0x1f`, payload[0]=`0x05` — execute READ.
   - Poll `report[0]=0x8f` until idle / check error byte.
   - `report[0]=0xaa` (query `0x2a`) — read back the data bytes.
4. Assemble; repeat the whole dump **at least 3 times**; require identical SHA-256.
5. Power-cycle to return to the application; confirm normal enumeration
   (VID:PID `0b05:1b7e`, v1.59).

Entering bootloader mode (app side): the application vendor-HID dispatcher writes
the magic `0x73207320` to RAM `0x20000ffc` and triggers an AIRCR system reset; the
bootloader's `FUN_00002a44` reads that flag on boot, and when it matches it stays
in service mode (and clears the flag). This is what the updater labels "Jump to
Bootloader". (An app command `0xb0` + payload `"reset"` performs a plain reboot
without the flag — that is a normal reset, not bootloader entry.)

Risks / caveats:
- Entering bootloader mode is a real command and a state change (low risk, but it
  *is* the first control transfer sent to the device).
- The read covers only `[0x10000, 0x7c000)` (see above); the bootloader region is
  not backed up by this path.
- We trust the bootloader's own read path; a hardware read (Approach B) is more
  independent. If Approach A and B ever disagree, trust B.
- Do **not** send erase (execute opcode `0x01`) or program (`0x51`), and do **not**
  send the `ASUSHIDFWU` unlock, at any point during preservation.

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

## Readiness status (2026-08-30)

- **Host access: confirmed.** The keyboard enumerates as `0b05:1b7e` (application
  mode) and `/dev/hidraw1-4` are world read/write, so no elevated privilege is
  needed. `hidapi`/`pyusb` are not installed; the tool uses raw hidraw instead.
- **Read-only tool: built and self-checked** — `tool/backup_firmware.py` (log 83).
  Its default `--dry-run` validates the whole dump plan and proves erase/program/
  unlock reports are unconstructable; `--run` opens a device only if it is already
  in bootloader mode (`1b7f`) and refuses to talk to the application (`1b7e`).
- **Still not done / not yet safe to execute:** the device is in application mode,
  so nothing can be dumped yet; entering bootloader mode is the first real device
  interaction and needs an explicit decision. The hidraw transfer type and
  report-ID prefix in the tool are conservative defaults to confirm on first use.

## Only after a verified backup

With a verified 1.59 backup in hand, a modified image built and validated offline
by `tool/build_modified_image.py` (integrity + boot gate) could be flashed via the
step-4 protocol — and if anything goes wrong, the backup is the recovery image.
That flashing procedure is intentionally **not** part of this plan.
