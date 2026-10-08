# Falchion keyboard investigation handoff

Updated on 2026-10-08 for the next Codex conversation. The Windows feature
captures have been reviewed on Linux, the five reported review findings have
been addressed, and 190 relevant offline tests pass, including the follow-up
profile-pairing corrections below. The next research task is
to reconcile the complete rapid-trigger handler with the captured behavior.
Several other keyboard features remain unverified.

## Prompt for the next conversation

Paste this into a new conversation opened in the same repository:

```text
Read keyboard/falchion-re/CODEX-HANDOFF.md in full, then inspect the current
Git status and the referenced findings, source logs, decoder and command-map
generator. Preserve the existing working-tree changes; they contain the fixes
from the 2026-10-08 review and restored original Windows evidence bytes.

Verify the relevant offline checks described in the handoff. Then continue
the next offline research task: reconcile the entire 51 54 rapid-trigger
handler and determine what the static 51 59 setter actually controls. Trace
the preserved installed firmware and compare with the preserved vendor image
and the Windows captures. Separate captured behavior from static conclusions
and hypotheses. Update the generator before regenerating its reports.

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

At handoff creation, branch `main` has HEAD
`ebd077f38d8303f1612002e3333e390dcf887ce9`:
`Enhance keyboard feature capture documentation and tools`. Its parent is
`4bd9a30`, which added the guided Windows feature capture script. The review
fixes are **uncommitted working-tree changes**. Reinspect Git state on resuming:
the owner may have committed or moved the work by then.

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

On 2026-10-08, the following combined suite passed **190 tests**, with tshark
installed and the capture tests executed:

```sh
cd /home/dereck/Documents/GIT/scripts/keyboard/falchion-re/tool
python3 -B -m unittest test_decode_capture test_decode_feature_capture test_feature_evidence test_map_vendor_commands test_profile_diff
```

| Module | Tests |
|---|---:|
| `test_decode_capture` | 41 |
| `test_decode_feature_capture` | 28 |
| `test_feature_evidence` | 6 |
| `test_map_vendor_commands` | 62 |
| `test_profile_diff` | 53 |

This is the relevant suite, not a claim that every repository test was run.
Without tshark, capture tests can skip; report those skips explicitly instead
of treating them as successful capture validation.

These checks also passed:

```sh
cd /home/dereck/Documents/GIT/scripts/keyboard/falchion-re
python3 -B tool/map_vendor_commands.py --check
git diff --check
```

The generator reports `reports_current=True stale=0`. To change generated
reports, edit and test `tool/map_vendor_commands.py`, then run:

```sh
python3 -B tool/map_vendor_commands.py --write
python3 -B tool/map_vendor_commands.py --check
```

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
Investigate the firmware reply construction before deciding whether Windows
needs a focused follow-up capture.

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

## Next offline research task

Trace the entire `51 54` handler and its callees in the preserved installed
application, then reconcile every captured field with its actual stores and
consumers. The current static description proves a mode-bit store at per-key
record `+0x0a` bits 14–15, but does not fully explain selector byte 2 and value
byte 6 or every branch controlled by byte 8.

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

For `51 59`, retain the proven static two-value setter and override behavior.
Its shared helper with the dead-zone command makes its actual role worth
investigating; no `51 59` appears in captures 03–03d. Do not restore the old
per-key rapid-trigger label merely because the helper shape looks familiar.

Record exact request offsets, ranges, storage offsets, bits, and relevant
control-flow conditions. Identify which conclusions come from instructions,
which come from AC actions/profile files, and which remain hypotheses. Do not
merge addresses from the installed and vendor releases into one unscoped
census. Correct generated models through their owning tools and add meaningful
regressions for new conclusions. Add a new research log rather than rewriting
135–137; inspect the current log sequence before choosing its number.

## Other unresolved work

| Question | Next useful evidence | Environment |
|---|---|---|
| Fn, ROG and physical backslash remap source | Inspect existing traffic and static translation first; if needed, capture a supported AC action. Reserved keys may emit no configurable command | Linux first, Windows only if needed |
| `51 55` byte 8 and `51 56` scope | Inspect handlers and consumers; the existing pair rewrite is not an owner-controlled enable/reset experiment | Linux first, targeted Windows test if unresolved |
| `12 00` reply byte 5 changing between 09 and 00 | Trace its producer and correlate existing profile/launch traffic | Linux |
| Animated lighting fields | Correlate captured bytes and profiles; then isolate one UI property per new action if needed | Linux first |
| `51 18 01` before macro uploads | Trace the named `=MS_A` handler and consumers; adjacency alone does not establish its full role | Linux |
| Keyboard-originated `03 61` and `03 70` | Decode and correlate existing traffic; do not call them profile events or Fn hotkeys without proof | Linux first |
| Macro decoder support beyond observed events | Mouse release, other buttons, wheel events and unseen key names remain unsupported; derive additions from actual captures | Linux with new evidence as needed |
| Decoder robustness outside preserved captures | Continuation integrity, malformed/truncated records and a required terminator are not fully validated by the current parser. The 190-test result does not cover arbitrary damaged captures | Linux, future hardening if requested |

These are pending research or robustness tasks, not claims that the five
original review fixes failed. Continue with the rapid-trigger static analysis
first unless the owner changes the priority.

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

The next offline task is complete when the `51 54` captured fields have a
supported static explanation, or a precisely documented unresolved boundary
after tracing the available evidence; `51 59` has a supported role or an
explicit remaining hypothesis; affected generators and reports agree; relevant
tests pass; and the findings, timeline and this handoff describe the new state.
Unanswered hardware questions must stay visible rather than being guessed.
