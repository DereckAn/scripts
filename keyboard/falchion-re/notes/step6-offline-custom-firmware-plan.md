# Step 6 — Offline analysis and custom-firmware development plan

Status: **PLAN ONLY**. This document authorizes no device access and no firmware
installation. Work through one phase at a time, then stop for independent review.

## Goal and realistic outcome

There are two related goals:

1. Build a reliable offline toolkit that understands, compares, extracts,
   modifies, repacks, and validates Falchion Ace HFX application images.
2. Use the recovered hardware and software interfaces to investigate a genuinely
   custom application that follows the boot container and integrity rules.

The first goal is achievable with the artifacts already preserved. The second
is plausible, but it is not yet proven: checks in the boot path remain unresolved
and important hardware behavior—especially Hall-effect sensing, calibration,
watchdog/clock setup, RGB, and nonvolatile configuration—still needs mapping.

The verified USB backup protects the range that the recovered USB updater can
erase/program, but it is not a complete 4 MiB U5 or internal-MCU backup. No live
test of a modified image should be planned until the offline gates in this
document pass and a separate recovery/risk plan is approved.

## Immutable inputs

Treat these as read-only evidence. Never edit or overwrite them:

- Installed application backup:
  `dumps/device/ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin`
  - logical base: `0x10000`
  - size: `0x6c000` / 442,368 bytes
  - SHA-256:
    `fc6128ab089e4fd712b172c54cd88b7f28476b55bdac688134e052281ded637b`
- Official ASUS 1.00.58 reference:
  `dumps/vendor/M605_V01_00_58.bin`
  - logical base: `0`
  - size: `0x7c000`
  - SHA-256:
    `6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d`
- Acquisition and validation record: `logs/92-full-app-region-backup.txt`.

Before and after every phase, verify the two hashes above. Any mismatch is a
hard stop.

## Non-negotiable safety boundary

All work in this plan is offline and host-only.

- Do not open `/dev/hidraw*`, USB device nodes, or sysfs USB nodes.
- Do not invoke `lsusb`, `dfu-util`, `fwupd`, Armoury Crate, ASUS update tools,
  Wine, or any program that could discover or communicate with the keyboard.
- Do not run `enter_bootloader.py`, `probe_bootloader.py`,
  `probe_flash_read.py`, or `backup_firmware.py --run`.
- Do not use `sudo`, change ACLs/permissions, detach drivers, reset the device,
  or install packages.
- Never construct or transmit unlock, erase, program, reset, SPI Write Enable,
  SPI Program, or SPI Erase commands.
- Never overwrite an evidence file. Derived binaries must use exclusive-create
  behavior and visibly include `UNTESTED` in their filename.
- Do not claim a modified image boots merely because its checksums pass.
- Do not silently reinterpret old conclusions. Record contradictions and cite
  the evidence that resolves them.

If a task appears to require the keyboard, network access, new packages, elevated
permissions, or a write-capable device command, stop and document the blocker.

## Execution and review model

Claude Code should execute **one phase only per invocation**. At the end of each
phase it must stop, summarize exactly what changed, list every assumption, and
leave the work uncommitted. Codex then reviews the diff, reruns the tests, checks
the claims against raw evidence, and either accepts the phase or gives a narrow
correction prompt.

Every phase must:

1. Read `FINDINGS.md`, the current-status portions of `TIMELINE.md`, this plan,
   and the directly relevant scripts/logs before editing.
2. Run `git status --short` first and preserve unrelated/user changes.
3. Use deterministic tools and tests; do not hand-edit generated results.
4. Save raw command output in the next numbered `logs/NN-*.txt` file.
5. Add that log's SHA-256 to `logs/SHA256SUMS` only after the log is final.
6. Add its command/result description to `logs/COMMANDS.md`.
7. Update `FINDINGS.md` and `TIMELINE.md` only for conclusions actually proven.
8. Run `python3 -m py_compile` on changed Python files, the complete unit-test
   suite, `sha256sum -c logs/SHA256SUMS`, and `git diff --check`.
9. State explicitly that no device was accessed.

Historical raw logs are immutable. A later correction gets a new log; it does
not rewrite the old one.

## Phase 0 — Preserve the backup redundantly (owner action)

Purpose: avoid a single disk or repository mistake destroying the only installed
application backup.

Actions:

1. Keep the repository copy unchanged.
2. Copy the binary and `dumps/device/SHA256SUMS` to independent storage.
3. On the independent storage, run `sha256sum -c SHA256SUMS` from the directory
   containing the file.
4. Record only the date, medium label, and successful hash verification in a
   private inventory. Do not store private mount paths or device serial numbers
   in this public repository.

Exit gate: at least two independently stored copies verify to the expected hash.
This phase is for the owner; Claude must not choose or write to external media.

## Phase 1 — Compare installed application 1.59 with vendor 1.00.58

Purpose: establish precisely what changed before interpreting either image.

Required implementation:

- Add `tool/compare_firmware_images.py` as an offline, read-only comparator.
- Treat the installed file as logical range `[0x10000,0x7c000)` and compare it
  with the same slice of the full vendor file. Do not compare misaligned offsets.
- Verify both input size/hash tuples before analysis; refuse unknown inputs unless
  an explicit analysis-only option prints a strong warning.
- Report:
  - whole-range SHA-256 and equality;
  - total differing bytes and contiguous difference ranges;
  - per-`0x1000` page hashes and changed-page list;
  - parsed SN_FWIN fields and record table for each image;
  - each record payload's length, SHA-256, and differing ranges;
  - application word-sum fields and recomputed values;
  - regions that are identical, all-zero, all-`0xff`, or changed;
  - strings added, removed, or changed, while avoiding misleading substring spam.
- Emit both a human-readable report and deterministic JSON from one underlying
  data model.
- Add unit tests for identical images, one-byte differences, differences crossing
  a page boundary, partial-image base translation, malformed/truncated records,
  and deterministic JSON ordering.

Required outputs:

- `tool/compare_firmware_images.py`
- `tool/test_compare_firmware_images.py`
- `notes/installed-vs-vendor.md`
- `logs/94-installed-vs-vendor-comparison.txt` (log 93 is reserved for this plan)

Do not infer function meaning in this phase. A byte range being changed is a
fact; its purpose is a later hypothesis.

Exit gate:

- Both source hashes still match.
- Comparator tests and the full suite pass.
- Counts/ranges in Markdown, JSON, and raw log agree.
- Existing analyzers still accept both source images with their correct bases.

## Phase 2 — Create a version-aware image-format library

Purpose: remove hard-coded 1.00.58 assumptions from parsing while retaining
strict version locks for mutation.

Required implementation:

- Add a small shared module such as `tool/falchion_image.py` containing immutable
  models for logical image base, containers, SN_FWIN header, payload records,
  checksums, and validation results.
- Separate parsing from policy:
  - parsing may inspect an unknown image safely;
  - validation reports known constraints and skipped unavailable regions;
  - mutation refuses any source hash/layout not explicitly supported.
- Refactor existing analyzers only when covered by regression tests. Preserve
  their CLI output or document intentional changes.
- Express every offset as a logical flash offset translated through image base;
  do not mix file offsets, mapped `0x60000000` addresses, and runtime addresses.
- Parse record lengths from each image. Do not reuse vendor 1.00.58 lengths for
  the installed dump.
- Provide machine-readable validation results so later builders cannot parse
  human-formatted stdout.

Tests must cover full images, base-`0x10000` partial images, absent containers,
out-of-range records, unterminated tables, checksum failure, and integer/bounds
edge cases.

Exit gate: old known-good results are unchanged, installed-image results match
log 92, and malformed inputs fail closed without tracebacks or partial output.

## Phase 3 — Extract and map the installed code images

Purpose: create an evidence-based installed-firmware memory map without assuming
that vendor addresses, lengths, or functions stayed unchanged.

Required work:

1. Extract each installed SN_FWIN record using the Phase-2 parser. Name slices
   with record number, logical source address, runtime destination, length, and
   short source hash. Generated slices belong under an ignored Ghidra/import
   area, not in `dumps/device/`.
2. Reconstruct the installed Candidate A scatter-load behavior from installed
   bytes. Confirm or correct the copied and decompressed ranges.
3. Import the installed programs at bases supported by their own records and
   loader behavior. Do not transfer vendor symbols by address alone.
4. Match functions between releases using multiple signals: normalized
   instruction bytes, constants, callers/callees, strings, and control flow.
5. Produce a mapping table with confidence levels: exact, strong structural
   match, tentative, or unmatched.
6. Add reproducible Ghidra scripts for reports. Existing project inspection must
   use `-readOnly -noanalysis`; creating a new ignored project for the installed
   image is allowed, but document it and never modify source dumps.

Required reports:

- installed record/load/scatter map;
- vendor-to-installed function correspondence;
- changed functions and data regions ranked for manual review;
- explicit list of addresses that must no longer be assumed equal.

Exit gate: every extracted byte maps back to a source range, every runtime range
has a cited loader/record basis, and a second script run reproduces the reports.

## Phase 4 — Resolve the remaining boot-acceptance checks

Purpose: determine the full set of bootloader conditions visible in the preserved
vendor bootloader before any generated image is called structurally acceptable.

Primary targets:

- `FUN_000029d4`: decompile it, enumerate all callers, inputs, outputs, referenced
  state, and every accept/reject path.
- The top-level comparison applied to the selected entry before the jump: recover
  both operands, signedness/width, and consequences of each branch.
- Reconfirm the call chain from container selection through record validation,
  scatter-load, initial-SP/reset-vector checks, and final transfer of control.
- Search for additional hashes, signatures, monotonic versions, rollback rules,
  device IDs, and configuration-dependent gates.

Evidence rules:

- Use instruction listings and decompiler output together.
- Cite program name, runtime address, and instruction span for every conclusion.
- Label ROM/first-stage behavior as unresolved unless evidence exists; do not
  infer it from the external-flash bootloader.
- Add new checks to `analyze_boot_structures.py` only after their semantics are
  proven and tested.

Exit gate: both named unknowns are either resolved with reproducible evidence or
remain explicitly blocked with a precise reason. No “probably” result may become
a builder acceptance rule.

## Phase 5 — Map the application hardware and runtime interfaces

Purpose: identify the minimum platform support a custom application requires.

Analyze in this priority order:

1. Vector/interrupt table, reset path, clock tree, memory initialization,
   watchdog, and fault behavior.
2. USB device controller, descriptors, endpoint initialization, HID reports,
   and report-routing tasks.
3. GPIO and keyboard scan scheduling.
4. Hall-effect sensor acquisition, ADC/analog peripheral use, calibration,
   filtering, actuation thresholds, rapid-trigger behavior, and safety bounds.
5. Nonvolatile settings format and write paths. Map them statically; never replay
   them on the device.
6. RGB controller/bus, timing, and frame buffers.
7. RTOS/task initialization, queues, timers, and synchronization.

For every peripheral/register claim, record the address, access width, read/write
sites, initialization value, task/IRQ context, and confidence. Separate observed
register behavior from guessed peripheral names, because a public SNC73270
reference manual is not yet available in the repository.

Exit gate: produce a dependency map showing which original services a minimal
custom firmware must replace, which may be omitted, and which are still unknown.

## Phase 6 — Choose the development strategy

Purpose: make an evidence-based choice rather than jumping directly to a full
replacement.

Evaluate two paths:

### Path A: controlled patching

Keep the original loader/application and change a narrowly understood function
or table. This is the fastest way to test format knowledge, but it remains
dependent on proprietary code and available code/data space.

### Path B: clean-room application replacement

Keep only the device's existing immutable boot path and provide a newly built
application record with compatible load address, vector/entry convention, and
container metadata. This better matches “our own firmware” but requires enough
hardware initialization, USB, scan, and Hall-effect knowledge to avoid unsafe or
nonfunctional behavior.

The decision report must compare recovery risk, unknown hardware dependencies,
required toolchain/linker support, size/layout constraints, debugging options,
and what code remains vendor-derived. The default recommendation is Path A for
offline format validation, followed by Path B only after the platform map is
credible.

Exit gate: a written architecture decision record, with no generated live-use
instructions and no device interaction.

## Phase 7 — Build an installed-image offline builder

Purpose: produce reproducible experimental images without weakening evidence or
silently accepting unsupported layouts.

Requirements:

- Extend or replace `build_modified_image.py` so source adapters are explicit:
  official full image versus installed app-only image.
- Lock mutation to an allowlisted source SHA-256 and parsed layout.
- Require every patch to include expected original bytes; abort on mismatch.
- Reject overlapping, empty, out-of-record, metadata, bootloader, and
  structurally unsafe patches unless a later reviewed policy explicitly permits
  them.
- Recompute only proven dependent integrity fields.
- Run all known boot/layout checks after construction and list unresolved checks.
- No-op rebuild must be byte-identical to its source.
- Write with exclusive create, never overwrite, and never create partial output.
- Derived filenames must contain `UNTESTED` and a manifest must record source
  hash, tool version, patch list, output hash, validations, and unresolved risks.
- The builder must contain no USB enumeration or flashing code.

Tests must prove fail-closed behavior by mutation testing: change each guarded
field, truncate inputs, use a wrong base/hash, overlap patches, request an
out-of-bounds patch, and force an output-path collision.

Exit gate: deterministic no-op and patched builds, complete tests, and independent
validation by scripts that do not import the builder's mutation functions.

## Phase 8 — First offline experimental firmware artifact

Purpose: demonstrate the build pipeline without risking the keyboard.

Do not choose the patch target until Phases 3–6 identify a behavior with:

- a fully understood control/data path;
- a small and precisely bounded change;
- no clock, watchdog, flash-write, calibration, USB-boot, or recovery effect;
- an observable result if a future live test is ever approved;
- exact original-byte assertions and a clear rollback image.

Produce the artifact under a generated/ignored location with `UNTESTED` in the
name. Do not produce or document an executable flashing command. The phase is
successful when the offline builder and independent validators agree—not when
anyone claims the artifact will boot.

## Phase 9 — Independent review before any live experiment

Codex should audit:

- source and output hashes;
- logical/file/runtime address translations;
- diff-range arithmetic and record bounds;
- independence of builder and validator;
- all checksum implementations against both preserved images and synthetic
  tests;
- Ghidra claims against instruction listings;
- whether tests can express each claimed failure mode;
- absence of `/dev`, USB, updater, reset, unlock, erase, program, and SPI paths;
- documentation for overclaims, hidden assumptions, and stale conclusions.

Before any future live test, write a new, separate plan covering complete U5/MCU
preservation, power-loss behavior, recovery tooling, exact bytes that could be
sent, and abort conditions. That future plan requires explicit owner approval;
this document does not grant it.

## Claude Code prompt — use for Phase 1 only

Copy the following prompt into Claude Code. Do not ask it to execute all phases
at once.

```text
Work in /home/dereck/Documents/GIT/scripts/keyboard/falchion-re.

Read completely:
- notes/step6-offline-custom-firmware-plan.md
- FINDINGS.md
- the current-status and 2026-09-02 log-91/log-92 sections of TIMELINE.md
- logs/92-full-app-region-backup.txt
- dumps/device/README.md and dumps/device/SHA256SUMS
- tool/analyze_candidate_integrity.py
- tool/analyze_boot_structures.py
- tool/analyze_sonix_firmware.py
- relevant existing tests

Execute Phase 1 ONLY: compare the installed base-0x10000 application dump with
the aligned 0x10000..0x7bfff slice of vendor 1.00.58. Implement the deterministic
offline comparator, tests, human report, and raw log required by the plan. Do not
start Phase 2 and do not commit.

Safety is absolute: no USB/sysfs device inspection, /dev/hidraw access, sudo,
permission changes, package installation, network access, bootloader entry,
probe tools, backup_firmware.py --run, vendor updater, reset, unlock, erase,
program, update, or SPI command. Do not modify either source binary. If anything
would require device or network access, stop.

Before editing, show git status and preserve all pre-existing changes. Verify
both immutable source hashes before and after. Use logical-base translation; do
not compare the installed byte 0 with vendor byte 0. Do not infer function
semantics from byte differences. Use apply_patch for edits. Keep generated output
deterministic. Finalize the new raw log before adding its SHA-256 to
logs/SHA256SUMS. Update FINDINGS.md and TIMELINE.md only with demonstrated facts.

Run py_compile for changed Python, the full unittest suite, both existing
analyzers on the appropriate images/bases, sha256sum -c logs/SHA256SUMS, and git
diff --check. At the end report: files changed, exact commands, test counts,
source hashes before/after, key factual results, assumptions/unresolved items,
and an explicit statement that no device was accessed. Leave everything
uncommitted for Codex review.
```

## Prompt template for later phases

After Codex accepts a phase, use this shorter controller prompt with the next
phase number substituted:

```text
Work in /home/dereck/Documents/GIT/scripts/keyboard/falchion-re. Read
notes/step6-offline-custom-firmware-plan.md completely and execute Phase N ONLY.
Read the accepted outputs from earlier phases first. Obey the offline safety
boundary. Preserve existing changes, do not commit, do not modify evidence
binaries or historical logs, and stop if device/network/elevated access would be
needed. Produce every required deliverable and exit-gate check for Phase N, add a
new hashed raw log, run the complete offline test/validation suite, and finish
with an evidence/assumptions/change summary for Codex review. Do not begin the
next phase.
```

## Definition of success

Step 6 is not “successful” merely because a checksum-valid binary exists. It is
successful when we have:

- a reproducible understanding of the installed image layout;
- evidence-backed boot and hardware-interface specifications;
- a deterministic, fail-closed, source-locked offline builder;
- an independent validator;
- an experimental artifact clearly marked untested;
- a reviewed recovery plan strong enough to justify a separate decision about a
  live experiment.

