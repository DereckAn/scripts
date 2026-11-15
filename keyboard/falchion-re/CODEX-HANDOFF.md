# Falchion keyboard investigation handoff

Updated on 2026-10-08 for the next Codex conversation. The Windows feature
captures have been reviewed on Linux, the five reported review findings have
been addressed. Log 138 now reconciles the complete `51 54` rapid-trigger
handler and identifies `51 59` as per-key dead-zone overrides through their
shared consumers. Log 139 traces the physical switch through global bit 5 to
`03 76` status and `25 00` readback. The expanded suite passes 262 offline tests.
The next research task is the complete `51 52` reset flow. Physical timing,
power-loss persistence and several other physical behaviors remain
unverified; see the completed static task and remaining boundaries below.

## Prompt for the next conversation

Paste this into a new conversation opened in the same repository:

```text
Read keyboard/falchion-re/CODEX-HANDOFF.md in full, then inspect the current
Git status and the referenced findings, source logs, decoder and command-map
generator. Preserve the existing working-tree changes; they contain the fixes
from the 2026-10-08 review and restored original Windows evidence bytes.

Read logs 138 and 139 and the trigger_configuration / rapid_trigger_lever
sections of the generated command map. The 51 54 handler, 51 59 consumer
relationship and physical-switch/global-bit-5 path are completed within their
documented limits; do not repeat them as though still open.
Continue offline with all five 51 52 reset selector paths, helper 1800f474,
the third reset field and mutation order. Constrain the result with captured
selectors 01/03, and keep uncaptured UI labels unassigned. Compare releases.
Prepare a focused physical experiment only for a question the existing
firmware and captures cannot resolve. Keep
installed/vendor addresses separate and update generators before their reports.

Keep progress updates concise. Finish authorized offline work before asking
for more information. Use Windows only for a new experiment that existing
evidence cannot answer, with a concrete capture plan. Follow the existing
firmware-preservation and evidence rules in the handoff. Report findings,
validation and unresolved questions precisely.
```

## Workspace and Git state

The Linux repository is `/home/dereck/Documents/GIT/scripts`; the investigation
is in `keyboard/falchion-re/`. Commands below assume that investigation directory
unless they explicitly change directories.

The review baseline was branch `main` at HEAD
`ebd077f38d8303f1612002e3333e390dcf887ce9`:
`Enhance keyboard feature capture documentation and tools`. Its parent is
`4bd9a30`, which added the guided Windows feature capture script. The review
fixes and pairing follow-up were subsequently committed by the owner as
`bdf3a76` (`Add comprehensive tests for feature capture decoding and evidence
validation`). The Ghidra continuation in logs 138–139 is new, uncommitted work.
Reinspect Git state on resuming; the owner may have committed or moved it.

Do not discard, overwrite or reapply the existing fixes. This handoff is a
continuation record; it does not request a commit, push, firmware update or
new live device command.

The implementation changes are in:

- `tool/decode_feature_capture.py` and `tool/test_decode_feature_capture.py`.
- `tool/map_vendor_commands.py` and `tool/test_map_vendor_commands.py`.
- New `tool/test_feature_evidence.py` and `.gitattributes`.
- Generated `notes/vendor-command-map.md` and `.json`.
- `FINDINGS.md`, `TIMELINE.md`, `tools/README.md`, `notes/key-matrix.md`,
  `notes/protocol.md`, course lessons 05 and 18, and Appendix C.
- The 31 evidence files whose original line endings were restored, listed
  by group under evidence preservation below.

## Read these sources first

1. `FINDINGS.md`, section **Armoury Crate on the wire**, including its
   **Offline review correction** paragraph.
2. `TIMELINE.md`, the 2026-09-29 feature sessions and 2026-10-08 offline review.
3. `logs/135-feature-capture-validation.txt`.
4. `logs/136-deep-capture-key-ids-and-corrections.txt`.
5. `logs/137-finish-capture-per-key-actuation-and-lever.txt`.
6. The corresponding `captures/*-notes.txt` and `*-owner-facts.txt` files.
7. `tool/decode_feature_capture.py`, the feature tests, and the generated map.
8. `logs/138-trigger-handler-reconciliation.txt`, generated
   `notes/vendor-command-map.md`'s reconciliation section, and the corrected
   `notes/profile-format.md`, and `logs/139-rapid-trigger-physical-switch.txt`.
   Logs 138–139 record the new static evidence.

Log 135's rapid-trigger and key-row interpretations were corrected in 136;
137 clarifies the actuation UI and remaining key numbers. Preserve these logs
as historical evidence. Older course tables are retained with correction
notices; they are not the current authoritative key map.

`PROMPT-polling-rate-analysis.md` and `NOTE-to-paste-with-prompt.md` describe
the older polling-rate capture. They are useful context, but they are not
the current continuation prompt. `WINDOWS-CAPTURE-03-features.md` records the
first feature run; subsequent runs used `tools/feature-session.ps1`.

## The five review findings and their fixes

| Finding | Current fix | Regression evidence |
|---|---|---|
| Replies were paired to the next IN within three records, allowing wrong commands and reused replies | `request_reply_results()` matches interface, bus, device address and command header; each IN is consumed once. Competing `51 00` requests use the profile echo where available; identical retries remain `ambiguous`. `reply_warning()` and the CLI flag raw profile disagreements. The old two-tuple API remains as a compatibility view | Unit tests exercise wrong-command replies, retries, profile echoes and mismatches, device scopes, interleaving and the `12 12` success reply `12 13`; capture tests verify all four files |
| Macro `MATCH` ignored key identity; Macro04's mouse click could not match | Comparison checks key encoding, action, delay and event count. Known aliases include macro Enter 108, backslash 42 and Comma 53. Captured `f0 12` means a left-click press. Unsupported encodings return a row result of `None` and cannot match | Changed keys, actions, delays, missing/extra events and unsupported mouse events are tested; all five captured uploads match their appropriate GMAC files |
| Macro03's byte hash failed because Git had converted CRLF to LF | Restored original CRLF only where the resulting bytes reproduced the original recorded SHA-256 exactly. Added attributes preserving archived evidence bytes | Original Macro03 hash passes; all 68 snapshot-manifest entries match hashes and sizes; evidence paths quoted in logs 135–137 match their hashes |
| Documentation claimed one commit for every setting write | Documentation now describes batches followed by one `50 55` commit | In 03d, frames 250438 and 250475 are P/L actuation writes, followed by commit frame 250511 |
| Documentation claimed every key was tested | Updated coverage statements distinguish observed keys and historical Enter evidence | Log 137 explicitly leaves Fn, ROG and the physical backslash remap source unobserved |

The generated command map was also updated through its generator. It corrects
the `51 58` dead-zone label, withdraws the former `51 59` per-key rapid-trigger
assignment, and adds independent `wire-observed` records with reconciliation
status and source logs. Static grades are retained where the instruction
analysis supports them; observing a UI effect does not complete a handler trace.

## Validation and commands

On 2026-10-08, the expanded combined suite passed **262 tests**, with tshark
installed and the capture tests executed:

```sh
cd /home/dereck/Documents/GIT/scripts/keyboard/falchion-re/tool
python3 -B -m unittest test_decode_capture test_decode_feature_capture test_feature_evidence test_map_vendor_commands test_profile_diff test_map_profile_format
```

| Module | Tests |
|---|---:|
| `test_decode_capture` | 41 |
| `test_decode_feature_capture` | 28 |
| `test_feature_evidence` | 8 |
| `test_map_vendor_commands` | 83 |
| `test_profile_diff` | 53 |
| `test_map_profile_format` | 49 |

This is the relevant suite, not a claim that every repository test was run.
Without tshark, capture tests can skip; report those skips explicitly instead
of treating them as successful capture validation.

These checks also passed:

```sh
cd /home/dereck/Documents/GIT/scripts/keyboard/falchion-re
python3 -B tool/map_vendor_commands.py --check
python3 -B tool/map_profile_format.py --check
git diff --check
```

The generator reports `reports_current=True stale=0`. To change generated
reports, edit and test `tool/map_vendor_commands.py`, then run:

```sh
python3 -B tool/map_vendor_commands.py --write
python3 -B tool/map_vendor_commands.py --check
```

The profile-format generator also changed in log 138: global bits 17–19 and
20–22 and record +6/+7 carry dead zone, while rapid-trigger sensitivity lives
at record +0x0a. Update its generator before using `--write`; the command map
consumes its generated JSON. Log 139 additionally maps bit 5 to the physical
rapid-trigger enable. Regenerate profile format before the command map
when both change.

Useful capture decodes are:

```sh
python3 -B tool/decode_feature_capture.py --utc-offset -6 pairs captures/03-features.pcap --op 5100
python3 -B tool/decode_feature_capture.py --utc-offset -6 pairs captures/03c-deep.pcap --op 5154 --op 5158
python3 -B tool/decode_feature_capture.py --utc-offset -6 pairs captures/03d-finish.pcap --op 514f --op 5152
python3 -B tool/decode_feature_capture.py --utc-offset -6 macro captures/03b-features.pcap snapshots/03b-features-macros/Macro04.GMAC --all
python3 -B tool/decode_feature_capture.py --utc-offset -6 macro captures/03c-deep.pcap snapshots/03c-deep-after-raw/macros/ROWS.GMAC
python3 -B tool/decode_feature_capture.py --utc-offset -6 macro captures/03d-finish.pcap snapshots/03d-finish-after-raw/macros/KEYS2.GMAC
python3 -B tool/decode_feature_capture.py --utc-offset -6 lever captures/03d-finish.pcap
python3 -B tool/decode_feature_capture.py profiles snapshots/03c-deep-before-raw snapshots/03c-deep-after-raw --all
```

The UTC offset is a global argument before the subcommand. The logs use
UTC-06:00. `profiles --all` includes per-key actuation entries otherwise hidden
by that command's default filter. Comparing one GMAC against a capture with
multiple uploads can legitimately show nonmatches before its matching upload;
the CLI succeeds if any upload matches.

The current pairing results are:

| Capture | OUT | IN | Matched requests | Unanswered | Ambiguous | Profile warnings within matched |
|---|---:|---:|---:|---:|---:|---:|
| `03-features` | 237 | 233 | 232 | 3 | 2 | 1 |
| `03b-features` | 172 | 172 | 172 | 0 | 0 | 0 |
| `03c-deep` | 544 | 544 | 544 | 0 | 0 | 0 |
| `03d-finish` | 111 | 111 | 111 | 0 | 0 | 0 |

Follow-up review confirmed both observations supplied by Claude. In 03, the
three profile `03` requests (frames 102363, 103199, 104069) stay unanswered;
the profile `02` request at 04:23:49.905 (106057) pairs with 106067 because it
is the only pending request echoing that reply's profile. Identical profile
`01` retries (107185, 108173) still have ambiguous ownership of reply 108212.

At 04:23:50.345, request 106237 contains profile `01`, while its associated
reply 106277 contains `02`. The CLI now prints a warning. This establishes a
raw byte disagreement; it does not establish the applied profile or explain
whether the reply is stale, reports existing state, or has another meaning.
Log 138 traced reply construction: the storage state machine sends the current
device-header profile at completion, normalising internal 0 to wire 6. The
dispatcher does not replace a profile request when opcode 2 is already pending.
These paths support asynchronous/state-reporting explanations, but the exact
runtime cause of this captured mismatch is still unconfirmed.

Pairing uses a documented heuristic: each reply closes the same command's
pending group, and a unique profile echo can distinguish different pending
profile values. A profile byte is not a transaction identifier, especially
given the observed mismatch. There is no elapsed-time cutoff; the decoder
does not force every OUT to have a reply. `matched` describes association,
not proof that the requested configuration was applied.

## Evidence preservation

The four captures retain their original hashes:

| File under captures | SHA-256 |
|---|---|
| `03-features.pcap` | `bb4bf7cc7df317a69c858dc09481d4bf10fc5691dacf9c08b5fe05b9606cce06` |
| `03b-features.pcap` | `522299eb340e576ad547c79c0f28815c2280044c1d23d16abd27d626c2dc15e8` |
| `03c-deep.pcap` | `d9aa029d5531df00fba587e455b449c6ef704cc3812fadf17b9121c95fa2e029` |
| `03d-finish.pcap` | `6c2abea3f6b60b5c7b1e1099333f32f09514f4d66e08e8aad482dfca83dace6e` |

Restored files comprise four macros in `snapshots/03b-features-macros/`, five
macros each in the before/after raw snapshots of 03c, five macros in 03d's
before raw snapshot, and six in 03d's after raw snapshot: **24 macro copies**.
The other seven files are the 03b/03c/03d action-note files and the before/after
JSON snapshots for 03c and 03d. The earlier 03b JSON snapshots did not need
restoration. All 31 changes were verified to affect only line endings.

`.gitattributes` marks `captures/**` and `snapshots/**` as `binary`, which
disables text normalization, textual diffs and automatic text merges. Larger
or binary-looking Git changes here reflect preserved evidence bytes. Use
decoders to inspect content. Keep the attributes together with the restored
bytes when carrying this work to another checkout.

Original logs and hash manifests were not edited. Do not change expected hashes
to make a failing test pass. Diagnose provenance and recover original bytes
only when the recorded hash proves the recovery. Source logs contain the
original firmware hashes; current preserved image paths are:

- `dumps/device/ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin`:
  `fc6128ab089e4fd712b172c54cd88b7f28476b55bdac688134e052281ded637b`.
- `dumps/vendor/M605_V01_00_58.bin`:
  `6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d`.

The installed image is firmware 1.59; the preserved official vendor image is
1.00.58. Keep their provenance separate. Firmware revision `REV_0159` was
recorded before and after the Windows feature runs; it has not been newly
queried from hardware in this Linux review.

## Confirmed feature behavior

These statements apply to the preserved sessions using Armoury Crate 6.5.14.0:

| Command or report | Observed meaning |
|---|---|
| `51 00` | Profile switch, request byte 4 profile number |
| `51 50` | Global actuation, byte 4 mm multiplied by 10 |
| `51 4f` | Per-key actuation, byte 4 key and byte 6 mm multiplied by 10 |
| `51 21` | Base-layer remap, byte 2 source, bytes 4–5 target, `00ff` default, byte 6 current actuation. Fn layer `9f` is historical evidence |
| `51 54` | Per-key rapid trigger: byte 2 combined/press/release selector `00/01/02`, byte 4 key, byte 6 sensitivity, byte 8 on/off |
| `51 58` | Global dead zone: byte 4 top and byte 5 bottom, each in 0.1 mm |
| `51 52` | Trigger-page Reset: selector 01 actuation, 03 actuation plus rapid trigger. Other selectors and a third reset field remain open |
| `51 55` | A/D pair matching AC's Speed Tap binding, with byte 8 changing 00 to 01; no deliberate owner Speed Tap action in that sample |
| `54` | Macro upload on assignment; saving in the editor alone produced no upload in these sessions |
| `03 76` on endpoint `0x8c` | Keyboard reports rapid-trigger lever state in byte 4: 01 on, 00 off |

Observed wire key numbers follow AT-101 positions: A 31, Space 61,
Backspace 15, Ins 75 and Esc 110. They are not AC profile coordinates or GMAC
scan-code numbers. Macro Enter is 108 and backslash is 42. Physical Enter 43
comes from historical remap evidence. Do not infer an unobserved physical
backslash source number from its macro encoding.

## Completed offline task: rapid trigger and dead zone (log 138)

`51 54` resolves through `0x180026e4 -> 0x18002ee4 -> 0x18002fe4`.
All captured fields now have an instruction-derived explanation:

| Input | Static effect |
|---|---|
| LE16 bytes 2–3 = 0/1/2 | Update both / press / release sensitivity |
| Byte 4 | Wire key <= bc translated through the KBID table to a record index |
| Byte 5 = 00/9f | Base/Fn layer |
| Byte 6 | Low seven bits stored; no handler range clamp |
| Byte 7 and byte 8 | Mode = 0 if byte 8 is zero, otherwise `(byte 7 + 1) & 3` |
| Record +0x0a | Bits 0–6 release, 7–13 press, 14–15 mode |

Disabling still stores sensitivity. Mode is written before selector validation,
so an invalid selector can partially mutate state without marking the layer
dirty. Valid writes mark `0x1801e6b9 + layer` dirty and echo 60 payload bytes.
The consumer in installed `FUN_18004a7e` uses these fields under record-type,
alternate-path and global-bit-5 gates, multiplies sensitivities by five, and
maintains directional extrema with strict delta comparisons. At travel <40,
the relevant delta threshold has a floor of 8. Mode 1 has a distinct initial
release threshold. See log 138 for branch details and release-specific addresses.

All 346 captured `51 54` writes fit: 18 combined, 164 press, 164 release;
330 enabled, 16 disabled. All use base layer and byte 7 = 0. Other modes and
Fn-layer physical behavior remain unobserved.

The shared dead-zone setter proves the argument order:

| UI label/counterpart | Global `51 58` byte / bits | Per-key `51 59` byte / record offset |
|---|---|---|
| Top | byte 4 / bits 17–19 | byte 6 / +7 |
| Bottom | byte 5 / bits 20–22 | byte 7 / +6 |

Wire 0 maps to internal 6; wire 1–5 is accepted, 6+ rejected. Per-key bytes
use bits 0–2 for the value and bit 7 for override. Both setters feed the same
cache builder and second-context raw-sample thresholds. This establishes the
static per-key dead-zone relationship; it does not establish UI availability
or physical effects for `51 59`, which never appears in the four captures.

Keep the UI labels and numeric consumer behavior separate. Bottom-labelled
values feed shared +0x5b4 and the branch that produces travel 0; top-labelled
values feed +0x64a and the branch that saturates travel to 200. This looks
opposite to intuitive physical-edge naming; record it as unresolved instead
of swapping the labels. The two raw-unit lookup tables end in zero at internal
value 6, and the converters use `value - 1` as the table index.

The full `51 54` handler is identical across preserved releases. Setter
`0x1800f948` (installed) corresponds to `0x1800f91c` (vendor); cache builder
`0x1800f7fe` corresponds to `0x1800f7d2`. Their instruction bodies match.
The scan function starts at `0x18004a7e` in both releases but differs internally;
do not apply a blanket relocation delta. The second-context image matches
except for its final checksum word. Source hashes and import round trips are
checked by the command-map generator.

## Completed offline task: physical rapid-trigger switch (log 139)

Installed `FUN_180068aa` reads GPIO code `0x47`, group 4 bit 7. A zero
sample means enabled; one means disabled. It compares the inverted sample
with current-profile global bit 5 and counts consecutive mismatches in the
shared counter `0x1801e778`. The entry-image caller `FUN_00000516` supplies
threshold 9 via veneer `0x409e`, once per eight service ticks and only when
`*(0x1801e810)==1`. The tenth mismatch is accepted; a matching sample resets
the count. The GPIO is sampled again at acceptance, so a bounce can report an
unchanged state. Exact mechanical latency and milliseconds remain unknown.

Acceptance updates only bit 5, queues `FUN_18004498(0x76,0,0,bit5)` and calls
runtime refresh `FUN_180089a8`. The sender adds report ID 3, yielding the
21-byte `03 76 00 00 <state>` input on endpoint `0x8c`. All 14 reports fit,
eight on and six off. The existing `25 00` query reads the same bit into reply
byte 4: all nine captured readbacks match, five on and four off.

Global storage restore can replace the table; factory resets start with bit 5
clear. Profile selection picks another global word, and the periodic poll
reconciles it with the physical switch. This can explain reports after profile
switching without new motion; it does not mean every switch forces a resend.
The poll has no direct persistence call. Other whole-block saves can include
the bit, so lever-only persistence across power loss is unproven. Writer scope
is GPIO, reset and restore paths inspected, not every possible indirect write.

Vendor counterpart `FUN_1800687e` uses globals `0x18024ee0`, selection
`0x1801e6aa`, counter `0x1801e74c`, reader `0x180109ec` and refresh
`0x1800897c`. Its 106-byte body differs only in one byte of the relocated call
to `0x18004498`; both call targets are verified. The bodies are not identical.
Keep `HALSetLever*` attribution unresolved: these names may describe the other
multifunction side control, and similarity of names does not identify carriers.

## Next offline research task

Trace `51 52` reset selectors 0..4 through installed helper `0x1800f474`,
identify the third reset field, and record all stores, conditions and mutation
order. Compare the vendor counterpart through the caller and actual function
map. Captured selectors 01/03 constrain the result. Other UI labels stay
unassigned unless code or existing actions establish them. Preserve timing,
persistence and uncaptured physical questions in the table below.

### Useful anchors retained from the completed task

Start with these inputs and anchors in `tool/map_vendor_commands.py`:

- Dispatcher `0x18001fbe`, request buffer `0x180233a8`.
- `SUB_TBB = (0x180024ec, 0x180024f0, 0x50, 5)`; resolve the `0x54` branch
  through its stub instead of assuming its final handler address.
- Existing `51 54` citations around `0x18002fe8` through `0x1800302c`.
- The shared `51 58`/`51 59` helper at `0x1800f948` and the respective calls
  at `0x1800334c` and `0x1800338c`.
- Installed slice `ghidra/imports/installed_app_b_slot1_flash21000_dst18000000_len1e380_be463863.bin`.
- Vendor slice `ghidra/imports/vendor_app_b_slot1_flash21000_dst18000000_len1e354_aafcf2fd.bin`.
- The pre-existing inventories and peripheral exports under `ghidra/`, using
  the installed export scope `installed_b.txt` where the generator does so.

For `51 59`, retain the supported static per-key dead-zone relationship and
the unobserved UI/physical boundaries; do not restore the old rapid-trigger label.

Record exact request offsets, ranges, storage offsets, bits, and relevant
control-flow conditions. Identify which conclusions come from instructions,
which come from AC actions/profile files, and which remain hypotheses. Do not
merge addresses from the installed and vendor releases into one unscoped
census. Correct generated models through their owning tools and add meaningful
regressions for new conclusions. Add a new research log rather than rewriting
135–139; inspect the current log sequence before choosing its number.

## Other unresolved work

| Question | Next useful evidence | Environment |
|---|---|---|
| `51 52` reset paths and third field | Trace all five selectors and helper `0x1800f474`, constrained by 01/03 captures | Linux, next task |
| Physical-switch milliseconds and power-loss persistence | The bit/report path is proven; absolute IRQ38 timing and lever-only saving are not | Further static work or a focused physical experiment |
| `51 59` UI availability and physical edge mapping | Inspect existing AC profile fields and UI/curve code; only then prepare isolated top/bottom and per-key captures if needed | Linux first, targeted Windows if needed |
| Rapid-trigger modes 2/3 and Fn layer | Trace existing mode-control producers and layer selection; no such `51 54` writes were captured | Linux first |
| Fn, ROG and physical backslash remap source | Inspect existing traffic and static translation first; if needed, capture a supported AC action. Reserved keys may emit no configurable command | Linux first, Windows only if needed |
| `51 55` byte 8 and `51 56` scope | Inspect handlers and consumers; the existing pair rewrite is not an owner-controlled enable/reset experiment | Linux first, targeted Windows test if unresolved |
| `12 00` reply byte 5 changing between 09 and 00 | Trace its producer and correlate existing profile/launch traffic | Linux |
| Animated lighting fields | Correlate captured bytes and profiles; then isolate one UI property per new action if needed | Linux first |
| `51 18 01` before macro uploads | Trace the named `=MS_A` handler and consumers; adjacency alone does not establish its full role | Linux |
| Keyboard-originated `03 61` and `03 70` | Decode and correlate existing traffic; do not call them profile events or Fn hotkeys without proof | Linux first |
| Macro decoder support beyond observed events | Mouse release, other buttons, wheel events and unseen key names remain unsupported; derive additions from actual captures | Linux with new evidence as needed |
| Decoder robustness outside preserved captures | Continuation integrity, malformed/truncated records and a required terminator are not fully validated by the current parser. The 262-test result does not cover arbitrary damaged captures | Linux, future hardening if requested |

These are pending research or robustness tasks, not claims that the five
original review fixes failed. Continue with the global enable/lever trace
unless the owner changes the priority.

## Windows capture guidance

Linux contains the files needed for the review fixes and the next static task.
A new Windows session is useful only for an experiment that needs Armoury
Crate or a physical action not already captured. Prepare the action sequence
before requesting a switch.

Use `tools/feature-session.ps1` as the reference capture workflow. Its default
`finish` plan was already completed; do not rerun it under an existing capture
name. The script refuses existing outputs. A future targeted plan needs a new
name and actions appropriate to the unresolved question; changing only `-Name`
does not change a plan's action list.

The established workflow captures passively while the owner uses AC, records
action times and before/after firmware revision, copies raw profiles/macros,
and hashes evidence. Retain the root-hub capture and descriptor injection,
identify the keyboard by VID:PID `0b05:1b7e` and bus-scoped identity, and read
USBPcap payloads from `usbhid.data`. Close AC and allow its delayed file writes
before ending the capture. Action-note times mark Enter pressed after the
action; they are not the exact instant of the physical action.

Keep the existing constraint to decline keyboard firmware-update prompts.
This continuation concerns offline analysis and passive capture planning;
it does not authorize replaying configuration packets, flashing, erasing,
unlocking, or entering the bootloader. Normal owner-driven AC setting changes
in an agreed capture plan are the established way to observe feature traffic.

## Completion criteria for the next task

The handler and physical-switch tasks are complete within the boundaries above.
The next task is complete when all five `51 52` selector paths and the third
reset field have a supported explanation or a precise unresolved boundary;
affected generators and reports agree; relevant tests pass; and the findings,
timeline and this handoff describe the new state.
Unanswered hardware questions must stay visible rather than being guessed.
