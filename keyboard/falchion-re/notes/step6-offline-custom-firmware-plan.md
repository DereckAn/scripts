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

The installed dump nevertheless contains important bootloader evidence. Its
file range `[0x51000,0x61000)`, corresponding to logical flash
`[0x61000,0x71000)`, has SHA-256
`4a4568b61bc245397b0ede6f285eb1bd8a7fa2018bc1373bc05e73eabb0f686a`
and is byte-identical to both the vendor 1.00.58 backup bootloader at
`[0x61000,0x71000)` and its primary bootloader at `[0,0x10000)`. Therefore the
bootloader image already under static analysis is proven to exist as the
installed backup copy. This does not prove that the unread installed primary
bootloader `[0,0x10000)` is identical, that the backup copy was the one active
during log 92, or that ROM/first-stage checks are known.

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
   suite from the repository directory using exactly
   `python3 -m unittest discover -s "$PWD/tool" -t "$PWD/tool"`,
   `sha256sum -c logs/SHA256SUMS`, and `git diff --check`. Do not run the suite
   from inside `tool/`: that discovers only 130 tests and then fails to import
   `test_enter_bootloader.py` because `from tool import enter_bootloader` cannot
   resolve the top-level `tool` package.
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

## Phase 1 — Create a version-aware image-format library

Purpose: establish one shared parser before comparison or later extraction, and
remove hard-coded 1.00.58 assumptions while retaining strict version locks for
mutation.

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
- Model the record table as the fixed eight-slot table the bootloader actually
  scans. `FUN_0000511c` (log 75) loops `uVar1 < 8` and processes every slot whose
  length field is nonzero; there is no terminator. A zero-length slot is a hole
  to skip, not the end of the table; a zero address with a nonzero length is an
  active slot with an invalid address and must fail rather than be dropped; a
  fully populated eight-slot table is legal. Preserve physical slot indices and
  bounds-check every active slot.
- Provide machine-readable validation results so later comparators and builders
  cannot parse human-formatted stdout.

Required outputs:

- `tool/falchion_image.py`
- `tool/test_falchion_image.py`
- `logs/94-version-aware-image-format-library.txt`
- `logs/95-phase1-record-scan-correction.txt` (added after independent review
  found the record-table parser inconsistent with `FUN_0000511c`)

Tests must cover full images, base-`0x10000` partial images, absent containers,
out-of-range records, a zero-length hole followed by an active record, a zero
address with a nonzero length, all eight slots populated, a truncated eight-slot
table, checksum failure, and integer/bounds edge cases.

Exit gate: old known-good results are unchanged, installed-image results match
log 92, the exact complete-suite command passes, and malformed inputs fail
closed without tracebacks or partial output.

## Phase 2 — Compare installed application 1.59 with vendor 1.00.58

Purpose: establish precisely what changed before interpreting either image.

Required implementation:

- Add `tool/compare_firmware_images.py` as an offline, read-only comparator.
- Use the Phase-1 `falchion_image.py` parser and validation models; do not add a
  second SN_FWIN parser or duplicate offset/checksum policy in the comparator.
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
  - the three-way bootloader-copy relationship: installed logical
    `[0x61000,0x71000)`, vendor backup `[0x61000,0x71000)`, and vendor primary
    `[0,0x10000)`, including hashes and any differing ranges;
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
- `notes/installed-vs-vendor.json`
- `logs/96-installed-vs-vendor-comparison.txt` (log 95 is the Phase-1 correction)

Do not infer function meaning in this phase. A byte range being changed is a
fact; its purpose is a later hypothesis.

Exit gate:

- Both source hashes still match.
- Comparator tests and the full suite pass.
- Counts/ranges in Markdown, JSON, and raw log agree.
- Existing analyzers still accept both source images with their correct bases.

## Phase 3 — Extract and map the installed code images

Purpose: create an evidence-based installed-firmware memory map without assuming
that vendor addresses, lengths, or functions stayed unchanged.

Required work:

1. Extract each installed SN_FWIN record using the Phase-1 parser. Name slices
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

Purpose: determine the full set of bootloader conditions visible in the
installed backup bootloader copy before any generated image is called
structurally acceptable. The installed logical range `[0x61000,0x71000)` is
byte-identical to the vendor 1.00.58 primary and backup bootloader slices, so the
existing vendor-derived Ghidra program is a valid analysis view of those bytes.
Treat the unread installed primary bootloader and any ROM/first-stage behavior
as separate unresolved questions.

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
- Generated Markdown must express the same result as the raw analyzer output;
  `--check` proves deterministic generation, not that the generator's prose is
  semantically correct. In particular, render the complete 31-sample handoff
  search, describe the load as `*(uint32_t *)VTOR + 0x1c`, and scope every
  negative search conclusion to the searched program/range and method.
- Do not say the application "executes at zero" while address-zero aliasing and
  ROM/first-stage mapping remain unresolved. Distinguish a linked/runtime address
  model from a proved physical execution mapping.
- A builder may conservatively require the entry record to fit inside the fixed
  `0x10000`-byte copy window, but this is not a proven bootloader acceptance rule
  unless control flow demonstrates that record verification depends on that fit.
  Keep proven boot checks and conservative construction policy separate in code,
  JSON, Markdown, and tests.
- Label ROM/first-stage behavior as unresolved unless evidence exists; do not
  infer it from the external-flash bootloader.
- Add new checks to `analyze_boot_structures.py` only after their semantics are
  proven and tested.
- Historical logs remain immutable even when a recorded reproduction command
  contains a syntax or transcription error. Preserve the correction, working
  command, output, and affected claim in a new numbered log rather than silently
  relying on later output. This specifically applies to the two failed `%%`
  commands in log 102.

Exit gate: both named unknowns are either resolved with reproducible evidence or
remain explicitly blocked with a precise reason. No “probably” result may become
a builder acceptance rule.

## Phase 5 — Map the application hardware and runtime interfaces

Purpose: recover the hardware and compatibility contract that a safe custom
application requires. Reproducing every vendor implementation detail is not the
goal. A replacement may use its own scheduler, fault logger, filtering code, and
service structure, but it must initialize or safely neutralize the hardware it
inherits and reproduce every externally required behavior.

Phase 5 is an umbrella phase. Execute and review **one numbered subphase below
per invocation**. An MMIO census, decoded vector table, or address-space map is a
useful first pass, not completion: the final map must connect registers and RAM
state to named services and data flow.

The existing first-pass artifacts—`logs/100-installed-hardware-interface-map.txt`,
`logs/102-phase4-and-phase5-review-corrections.txt`,
`notes/installed-hardware-interfaces.{md,json}`, and their generating scripts—are
inputs to these subphases, not a completed Phase 5 result. Preserve their valid
measurements and record every correction in a later immutable log.

### Evidence boundary and external architectural reference

No public register-level SNC73270 reference manual or exact-device CMSIS-SVD is
preserved in the repository. A public SONiX **SNC7320-series product brief** has
been identified at:

`https://www.sonix.com.tw/webapi/fl218645/snc7320_brief_data_sheet_V2.3.pdf`

The brief describes a series-level dual Cortex-M3 design with an inter-core
interrupt, SWD, ROM/PRAM/shared SRAM/mailbox RAM, GPIO, timers/PWM, two watchdogs,
SPI NOR, USB host/device, and a 10-bit SAR ADC with up to six channels. These are
architectural leads only. They do not prove that this exact SNC73270 variant
implements every listed feature, identify any register address or bit field, or
show which core owns a peripheral. Do not fetch the document during an offline
phase invocation; preserving a local copy, URL, retrieval date, and SHA-256 is a
separate owner-authorized evidence-acquisition action.

The series brief creates an additional mandatory question: determine whether
Candidate A, Candidate B, the independent RAM image, any mailbox-like state, and
the observed interrupts involve one core or both. Do not assume that multiple
images imply multiple cores, but do not design a replacement until possible ROM,
second-core, mailbox, and inter-core dependencies are accounted for.

For every claim, preserve:

- exact address, access width, and direction;
- every known read/write site and the real Ghidra function body containing it;
- stored values and initialization values as separate fields;
- direct caller plus computed task, callback, reset-reachable, and IRQ contexts;
- the data-flow path that gives the access meaning;
- installed/vendor correspondence and any release-specific difference;
- confidence as `observed`, `strongly-inferred`, `hypothesis`, or `unresolved`;
- a `kind_basis` explaining whether the name comes from ARM architecture, an
  exact descriptor/protocol correlation, the series brief, or code behavior.

Call-graph reachability is not execution timing. In particular, a write in a
function reachable from reset is a **reset-reachable write**, not necessarily a
write performed during initialization. Use `reset-write` or `initialization
value` only after tracing an executed reset-to-site path or establishing an
explicit initialization boundary.

Ghidra is the primary analysis environment. Use the prepared installed and
vendor programs at their proven runtime bases, and keep all repeatable analysis
in tracked scripts. Improve Ghidra's model before drawing conclusions: create
functions at validated odd Thumb pointers, apply evidence-supported signatures
and data types, resolve callback/task/dispatcher tables, and rerun analysis.
Decompiler output alone is not proof; confirm conclusions against listings,
xrefs, function bodies, and raw bytes. P-code emulation may be used for bounded
pure routines such as parsers, filters, checksums, and dispatchers, but whole-chip
emulation is not evidence unless every relevant MMIO/ROM/inter-core behavior is
explicitly modelled.

### Phase 5A — Resolve indirect control flow and RTOS primitives

Purpose: recover the execution roots currently hidden behind task, callback, and
dispatcher tables before trying to classify their peripherals.

- Begin with Candidate B `main` at `0x1800023a`, the observed task-creation call
  `FUN_18012fa4(0x1800004d, "INIT_TASK", 0x100, 0, 0x14, 0)`, the scheduler-like
  call at `0x180136be`, every populated vector, and the two non-vector entry-image
  pointers already recovered.
- Infer and apply conservative signatures for task create/start, delay, queue,
  semaphore, timer, and callback-registration APIs from repeated call shapes.
- Find every call to each recovered primitive; preserve task-name strings, entry
  pointers, stack sizes, priorities, arguments, and creation order.
- Decode function-pointer tables and indirect `CALLIND`/branch sites. Validate a
  candidate destination as mapped executable Thumb code before seeding it; never
  turn every odd word into a function indiscriminately.
- Recompute reachability from vector entries, task entries, registered callbacks,
  timers, and proven dispatcher entries. Report unresolved indirect sites and why
  they remain unresolved rather than silently omitting their callees.
- Produce a task/callback graph and identify which contexts can touch each shared
  RAM object and MMIO block. Do not require a custom firmware to reproduce the
  vendor RTOS itself; identify the scheduling and synchronization semantics the
  hardware services actually require.

Exit gate: all recoverable indirect roots are seeded with their provenance, the
remaining unresolved indirect calls are enumerated, and later subphases can cite
task/callback/IRQ contexts instead of a reset-reachability approximation.

### Phase 5B — Recover USB ownership, endpoints, and report routing

Use the read-only USB evidence already preserved in logs 07/09 and
`notes/usb-descriptors.txt` as ground truth:

- interface 0: boot keyboard, 8-byte IN report, endpoint `0x81`;
- interface 1: vendor page `0xFF00`, 64-byte IN/OUT reports, endpoints `0x85`
  and `0x0d`;
- interface 2: consumer/system plus vendor events, maximum 21-byte IN report,
  endpoint `0x8c`;
- interface 3: keyboard/NKRO, 19-byte IN report, endpoint `0x8e`;
- interface 4: HID page `0x59` LampArray/lighting, feature reports and 64-byte
  OUT endpoint `0x0f`.

Actions:

- Search every loaded image for exact descriptor bytes and distinctive fragments;
  if they are absent, test whether they are constructed at runtime or supplied by
  ROM/the other core rather than claiming the search proves no descriptor exists.
- Trace descriptor/table references, USB initialization, endpoint configuration,
  callback registration, control requests, and report-buffer ownership.
- Trace the `0x40100000` block and IRQ6 in both directions: initialization to the
  handler, and handler reads/writes through RAM buffers to consumers. Treat it as
  an unnamed block until descriptor, endpoint, or buffer flow identifies it.
- Connect the vendor channel to `VendorHID_CommandDispatcher@0x18001fbe` and
  `VendorHID_SendResponse64@0x18000a70`; recover the receive and transmit paths,
  not just the already known command parser.
- Map each endpoint/report to its task/IRQ/callback context and record packet
  size, buffering, ownership, completion/error handling, and any DMA behavior.

Exit gate: every required HID interface/report is either linked to a static
descriptor and firmware route or carries a precise unresolved boundary such as
ROM/second-core ownership. A minimal USB-keyboard path must be distinguished from
optional vendor, media/NKRO, and lighting compatibility.

### Phase 5C — Recover GPIO and keyboard scan scheduling

Analyze from both ends: periodic IRQ/task functions that read unnamed MMIO, and
functions that consume or produce the recovered key maps and HID state.

- Find fixed-count row/column or key loops, GPIO bit masks, mux/drive sequences,
  delays, timer triggers, DMA completion, and repeated byte/halfword reads.
- Trace raw state through previous/current arrays, debounce counters, edge/state
  transitions, rollover policy, key-map lookup, layer processing, and HID report
  generation.
- Identify scan cadence and its timing source, including what can pre-empt or
  block a scan and how shared scan buffers are synchronized.
- Do not equate the 189-entry wire-ID translation with the physical key count;
  prove every physical dimension independently.

Exit gate: a reproducible scan-to-HID data-flow graph names the scheduling source,
physical indexing, state buffers, debounce/state transition logic, and the handoff
to report generation, with every unnamed hardware boundary explicit.

### Phase 5D — Recover Hall-effect acquisition and actuation behavior

This is mandatory and safety-critical for a useful replacement. The series brief
makes a SAR ADC plausible but does not identify the ADC block or prove that the
keyboard uses it directly.

Trace this candidate pipeline without assuming any stage exists:

`MMIO/IRQ/DMA -> raw samples -> calibration -> filtering -> position/travel ->`
`press/release or rapid-trigger comparison -> per-key state -> HID`

- Search for arrays of byte/halfword samples, range clamps, saturating arithmetic,
  per-key baseline/min/max values, calibration tables, and channel/key multiplexing.
- Recover filter equations and history depth: moving average, IIR, median-like,
  outlier rejection, hysteresis, or other observed behavior.
- Trace configuration fields modified by known vendor-HID commands into threshold,
  press/release, dead-zone, and direction-dependent comparisons. Identify any
  rapid-trigger state machine from actual state/data flow, not feature names.
- Record bounds, defaults, invalid-calibration behavior, timeout/fault behavior,
  and the conversion from raw values to any travel unit.
- Keep raw numeric behavior separate from physical interpretation. Static code can
  recover formulas, but cannot alone prove sensor polarity, voltage limits, noise
  margin, physical distance, or a safe scan rate.

Exit gate: the raw-sample-to-key-state algorithm is reproduced as deterministic
pseudocode/tests with all constants and state identified, or each missing boundary
is precisely recorded. No custom-firmware Hall drive or live experiment is
authorized by completing this offline analysis.

### Phase 5E — Recover nonvolatile settings without replaying writes

Start at the historically observed vendor-HID persistent-commit command `50 55`
and trace its dispatcher branch and callees statically. Never transmit it.

- Determine whether the path directly programs storage, queues a storage task,
  invokes ROM/another core, or dispatches through a function table.
- Recover the settings structure, magic/version, defaults, length, CRC/checksum,
  calibration versus user-profile fields, and migration behavior.
- Map erase/program granularity, slotting, journaling/wear levelling, completion
  checks, power-loss behavior, and every address range the path may modify.
- Distinguish internal storage, external U5/SPI NOR, and RAM mirrors; do not infer
  storage identity merely from an address-space label.

Exit gate: the format and write call graph are documented well enough either to
implement safe persistence or deliberately omit all writes while proving the
prototype cannot corrupt existing configuration.

### Phase 5F — Recover RGB/LampArray routing

Use interface 4's 327-byte HID page `0x59` descriptor, report IDs `1..6`, and
endpoint `0x0f` as fingerprints.

- Search for the descriptor/fragments and trace feature/OUT report handlers into
  LampArray parsing, LED addressing, brightness/color conversion, frame buffers,
  update scheduling, and the final SPI/PWM/GPIO/other hardware interface.
- Record LED count/topology, color order and width, frame layout, timing, DMA or
  double buffering, and interaction with keyboard scanning or power management.
- If the first custom firmware deliberately omits RGB, determine the safe idle
  state and any shared clock/pin/controller initialization it must still perform.

Exit gate: RGB is classified as implemented or safely omitted, with its report
route and final hardware boundary mapped or precisely blocked.

### Phase 5G — Revisit clocks, watchdogs, faults, and multicore behavior

Return to reset-reachable anonymous blocks after downstream consumers have been
identified. Correlate write order, unlock keys, polling loops, delays, clock
dependencies, periodic refreshes, and IRQ use with the services recovered above.

- Identify or conservatively preserve the clock/reset/pinmux sequence needed by
  mandatory services. Record frequency conclusions only when constants and timing
  relationships support them.
- Determine whether each watchdog is disabled, configured, or fed, from where it
  is serviced, and the safe replacement policy. A periodic magic write is a lead,
  not proof by itself.
- Preserve NMI/fault/reset behavior and distinguish useful diagnostics from
  hardware requirements.
- Investigate mailbox RAM, the inter-core interrupt, second-core start/stop/reset,
  ROM calls, and ownership of USB/ADC/storage. Treat any inaccessible ROM service
  as an explicit platform dependency.
- Keep the current vector-table extent and IRQ63 conclusion as strongly supported
  inference unless exact-device evidence proves the implemented interrupt count.

Exit gate: mandatory services have a clock/reset/watchdog/multicore policy, and
no reset-reachable write is called an initialization requirement solely because
of graph reachability.

### Phase 5 final dependency and prototype gates

Classify each service, not merely each address space, as one of:

- **must implement** — needed for reset, Hall/scan, key-state generation, or the
  chosen USB compatibility target;
- **must neutralize/configure** — watchdog, reset, clock, pin, second-core, or
  inherited hardware whose unsafe default cannot be ignored;
- **may omit** — optional vendor configuration, persistence, RGB, media/NKRO, or
  diagnostics whose omission and safe idle state are proven;
- **unresolved** — evidence is insufficient; this is a blocker, not permission to
  omit the service.

At minimum, a first safe typing prototype requires understood reset/clock/RAM
behavior, a safe watchdog policy, GPIO plus Hall/sample acquisition, calibrated
key-state generation, and one USB keyboard-IN route. It does **not** have to copy
the vendor RTOS, fault logger, proprietary configuration channel, persistence,
RGB, media reports, or NKRO if their omission is explicitly safe.

Required outputs across the Phase 5 subphases:

- deterministic task/callback/IRQ graph;
- USB interface/endpoint/report routing map;
- scan and Hall raw-sample-to-HID data-flow model;
- static nonvolatile format/write map;
- RGB route or safe-omission proof;
- clock/watchdog/fault/multicore dependency map;
- machine-readable JSON plus generated Markdown, tests, and a hashed raw log for
  each reviewed subphase.

Final exit gate: the dependency map names the original services a minimal custom
firmware must implement, neutralize/configure, or may safely omit. Any remaining
unknown is attached to an exact evidence boundary and blocks the affected custom
firmware feature. Five unanalysed service areas plus an MMIO census do not satisfy
this gate.

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
- Recompute only these proven dependent integrity fields, in dependency order:
  - each affected SN_FWIN record's chunked-CRC sum in its `record+0x8` field;
  - if a later reviewed policy ever permits a change in the backup bootloader
    region `[0x61000,0x71000)`, its additive word-sum at logical `0x70ffc`;
  - the application-region additive word-sum at logical `0x7bffc` after all
    other dependent fields are final. It covers `[0x10000,0x7bffc)`, so changes
    to record checksum fields or the backup-copy word-sum also affect it.
- The primary-bootloader word-sum at logical `0x0fffc` covers
  `[0,0x0fffc)`. It is absent from an installed app-only source and outside the
  USB-readable/writable range, so that builder mode must report it unavailable,
  must not claim to recompute it, and must refuse any operation that would
  require changing it. An application-region patch does not depend on it.
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
- tool/build_modified_image.py
- relevant existing tests

Execute Phase 1 ONLY: create the shared version-aware `tool/falchion_image.py`
library, tests, and raw log required by the plan. Consolidate SN_FWIN parsing,
logical-base translation, records, checksums, and machine-readable validation
models there. Refactor an existing analyzer only when regression tests preserve
its known output. Do not implement the installed-versus-vendor comparator, start
Phase 2, or commit.

Safety is absolute: no USB/sysfs device inspection, /dev/hidraw access, sudo,
permission changes, package installation, network access, bootloader entry,
probe tools, backup_firmware.py --run, vendor updater, reset, unlock, erase,
program, update, or SPI command. Do not modify either source binary. If anything
would require device or network access, stop.

Before editing, show git status and preserve all pre-existing changes. Verify
both immutable source hashes before and after. Express offsets through explicit
logical-base translation, parse record lengths from each image, fail closed on
malformed inputs, and keep generated output deterministic. Finalize the new raw
log before adding its SHA-256 to `logs/SHA256SUMS`. Update `FINDINGS.md` and
`TIMELINE.md` only with demonstrated facts.

Run `py_compile` for changed Python; from the repository directory run the full
suite using exactly
`python3 -m unittest discover -s "$PWD/tool" -t "$PWD/tool"`; run the existing
analyzers on the appropriate images/bases; then run
`sha256sum -c logs/SHA256SUMS` and `git diff --check`. At the end report: files
changed, exact commands, test counts, source hashes before/after, key factual
results, assumptions/unresolved items, and an explicit statement that no device
was accessed. Leave everything uncommitted for Codex review.
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
