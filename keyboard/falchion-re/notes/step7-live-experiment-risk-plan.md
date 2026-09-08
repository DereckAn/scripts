# Step 7 — Live-experiment risk plan (flash of an offline-built image)

**Status: DRAFT FOR OWNER REVIEW. THIS DOCUMENT AUTHORIZES NOTHING.**

No device access, no firmware installation, no updater invocation, and no
write-capable command is approved by this document. It becomes effective only
if the owner explicitly approves it in a separate decision, and even then only
for the single experiment it names. It is not part of the step-6 plan; step 6
explicitly withheld this authorization (see
`notes/step6-offline-custom-firmware-plan.md`, Phase 9).

This plan exists because Phase 8 produced a structurally validated,
checksum-correct `UNTESTED` image. "Exists and validates offline" is not
"safe to flash". This document is the gap between the two.

## 1. The candidate experiment

Two candidate images exist under `generated/` (git-ignored), both built by the
Phase 7 builder and independently validated in log 117:

| artefact | content | purpose |
|---|---|---|
| no-op build, installed adapter | byte-identical to the installed 1.59 application region (SHA-256 `fc6128ab…ded637b`) | exercises the entire write path with **zero behavioural delta** — the bytes flashed equal the bytes already on the device |
| product-string build, installed adapter | same image with 20 literal bytes changed (`ROG FALCHION ACE HFX` → `UNTESTED FALCHION FW`), both integrity fields recomputed | the first behavioural test: a host would display a different product string |

Rollback material: the verified installed 1.59 application backup
(`dumps/device/ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin`,
three identical read passes, log 92) and the vendor 1.00.58 image (a restore
source that is a **downgrade**, not a byte-for-byte return to the observed
state).

**Sequencing is mandatory:** the no-op build flashes first. It proves entry,
unlock, erase, program, checksum-readback and re-enumeration against a
known-good image. The product-string build is considered only after the no-op
build completes cleanly and the device re-enumerates normally.

## 2. Risk model

### Case 1 — the image is rejected (LOW)

A checksum or boot-gate failure leaves the device in bootloader mode, where it
can be re-flashed. Recovery is the rollback procedure in §6. No permanent
effect. Note: the claim "a failed candidate leaves the device in bootloader
mode" rests on the decompiled selection logic (logs 75, 78, 101) — both boot
slots point at the *same* SN_FWIN header, so there is no backup *application*
to fall back to. It has never been live-tested and is recorded here as an
assumption, not a fact.

### Case 2 — a checksum-correct image that does not enumerate (HIGH, the binding risk)

This is the dangerous case identified in the ADR. The image passes every boot
check, the device leaves bootloader mode — and then the USB route back is
gone, because the jump-to-bootloader command is an *application* command and
the application no longer enumerates. The remaining documented route is the
bootloader's own recovery key poll, `FUN_000029d4` (log 101), and **the
physical keys it matches are unresolved**. If they remain unresolved at flash
time, a Case-2 failure has *no documented software recovery*. The bootloader
itself cannot be erased through this write path (self-protection range, log
81), so the device is not bricked in principle — it is unreachable in
practice until the key combination or a hardware path is found.

### Case 3 — power loss mid-erase or mid-program (MEDIUM)

The erase/program protocol operates per 4 KiB page with ≤`0x30`-byte data
transfers. A power loss leaves a partially written application region. Because
the region's integrity fields would then be wrong, this degrades to Case 1
*under the same unproven assumption* recorded there. Mitigations in §5.

### What is NOT protected

- The bootloader region `[0, 0x10000)` can be neither written nor read over
  USB (logs 81, 92). It is safe from this protocol and invisible to it.
- The rest of the 4 MiB U5 (beyond `0x7c000`) is unreachable by this protocol
  and has never been dumped. Its contents are unknown; nothing in this
  experiment touches them.
- No internal-MCU nonvolatile state (if any exists) is backed up.

## 3. Prerequisites — hard gates, all must pass before any flash

- **G1 — physical recovery keys resolved.** Trace `FUN_000029d4` statically
  (the bootloader is preserved): which GPIO/matrix state it samples, which key
  positions the pattern corresponds to. This is offline work on existing
  artifacts. If it cannot be resolved statically, G3 becomes mandatory, not
  optional, and this plan does not proceed on software recovery alone.
- **G2 — artefact frozen.** The exact image to be flashed is named by SHA-256
  and rebuilt once more from source; the rebuild must be byte-identical to the
  reviewed artefact. Any different patch is a new Phase 8, not this plan.
- **G3 — hardware recovery decision.** No SPI programmer, SWD probe or test
  wiring exists today. The owner must decide, in writing, either to accept
  software-only recovery after G1, or to acquire hardware read/write capability
  first. This plan recommends: if G1 fails, stop; do not proceed.
- **G4 — write tool exists and is reviewed.** Today there is no host tool that
  sends erase/program. `enter_bootloader.py` and `backup_firmware.py --run`
  perform entry and READ only, under their own prior authorization. A program
  path must be written, reviewed against the exact-bytes appendix (§7), and
  testable up to the point of the first irreversible frame with a dry-run mode
  that stops before any erase. The tool is itself a review gate.
- **G5 — environment.** Direct motherboard USB port (no hub), stable power, no
  suspend/screensaver, no other HID software running, and a second person or a
  written checklist for the abort conditions.
- **G6 — abort conditions rehearsed (§6).**

## 4. Power-loss behaviour

- Erase granularity is the page; program is chunked. Total window is short but
  nonzero; treat any interruption as Case 3.
- Before the first frame: charge/stabilise power, disable suspend
  (`systemd-inhibit` or equivalent documented in the run log), and confirm the
  device does not share a bus with a power-hungry peripheral.
- If power or USB drops at any point: do not replug repeatedly. One careful
  power-cycle, then assess enumeration state exactly once, then follow the
  decision tree in §6.

## 5. Execution protocol (only after G1–G6 pass and owner approval)

1. Enter bootloader mode via the application jump command; confirm
   re-enumeration as PID `1b7f`. (Reversible: power-cycle boots the intact
   app, as in logs 88–92.)
2. Read back one application page and compare against the backup — proves the
   READ path before any write.
3. Dry-run the write tool through every frame *except* the first erase;
   review the log against §7.
4. Erase, program, and read the checksum for the **no-op image only**.
5. Reset; confirm enumeration as `0b05:1b7e`, `bcdDevice 1.59`, five HID
   interfaces; confirm typing works (boot keyboard interface).
6. Only then, and only with a separate go/no-go, repeat steps 1–5 for the
   product-string image and check the displayed product string.
7. Restore: flash the verified 1.59 backup; confirm enumeration.

## 6. Abort conditions and decision tree

Abort immediately and do not retry blindly if any of these occur:

- re-enumeration to an unexpected PID, or no re-enumeration within the
  documented window;
- any nonzero status/error byte in a bootloader status reply;
- a checksum-readback mismatch after programming;
- any host-side error, disconnect, or hesitation mid-sequence.

Decision tree after an abort:

1. Device enumerates as `1b7f` (bootloader): flash the verified backup. End.
2. Device enumerates as `1b7e` (application): power-cycle once; if the
   application works, stop and review before any further attempt.
3. Device enumerates as nothing, or wrongly: power-cycle **with the recovery
   key combination from G1 held**. If G1 was not resolved, this branch was the
   reason this plan should not have run. Record everything.

## 7. Appendix — the exact bytes that could be sent (for review; not instructions)

Statically recovered (logs 81, 82, 85, 89); the READ path is live-validated,
the **write path has never been exercised**. Transport: two unnumbered 64-byte
vendor-HID interfaces; commands to usage page `0xFF01` interface 0 (EP6),
replies from usage page `0xFF00` interface 1 (EP5).

| `report[0]` | payload | effect |
|---|---|---|
| `0x10` | `"ASUSHIDFWU"` | unlock — required for erase/program only |
| `0x20` | addr u32 LE | set target address (guarded to `[0x10000, 0x7c000)`) |
| `0x21` | length u16 LE | set length |
| `0x22` | `[count≤0x3c][off u16][data…]` | load program data into the buffer |
| `0x1f` | `0x01` / `0x05` / `0x51` | execute: erase / read / program |
| `0x11` | — | system reset |
| `0x8e` | — | query whole-image CRC result (`0xfa` pass / `0xfe` fail) |
| `0x8f` | — | query status (busy/error bits per log 82) |
| `0xaa` | — | query read-back data |

Per 4 KiB page the sequence is: unlock (once) → set address → erase → per
chunk: set address/length, load data, program → whole-image CRC query →
reset. Any host tool must reproduce this framing exactly and log every frame
both directions.

## 8. Non-authorization and owner sign-off

This document is a risk analysis. Nothing in it, in step 6, or in the Phase-8
artefact's existence authorizes writing to the device. Approval, if ever
given, must name: the exact artefact hash, the date window, the operator, the
confirmed state of gates G1–G6, and which single sequence from §5 is approved.

- Owner decision: ☐ rejected ☐ deferred ☐ approved as written
- Artefact hash approved (if any):
- Gates confirmed (initials): G1 ☐ G2 ☐ G3 ☐ G4 ☐ G5 ☐ G6 ☐
- Date / signature:
