# Prompt — polling-rate capture analysis (paste into a new Claude Code session)

## Owner checklist — while capturing (fill these in; Claude will ask for them)

- [ ] Wall-clock time of EACH rate change (1000 / 2000 / 4000 / 8000),
      as precisely as you can note it. These anchor the timeline.
- [ ] Armoury Crate version shown in its UI.
- [ ] Did AC show any firmware-update prompt? (You must have declined
      it — note if anything unexpected appeared.)
- [ ] Any accidental changes (other settings touched)? Say what and when —
      those windows will be analysed too, not discarded.
- [ ] Did the keyboard visibly reconnect (LED flash, OS reconnect sound)
      after a rate change? That is re-enumeration evidence.
- [ ] Final capture filename(s) copied into `captures/`.
- [ ] Optional second capture (one lighting color change): yes/no.

Keep the capture session SHORT and focused: USBPcap records the whole
bus, including storage and other devices, and long sessions make huge
files and noisy timelines.

## The prompt (paste everything inside the code block)

```text
Work in /home/dereck/Documents/GIT/scripts/keyboard/falchion-re.

MISSION
A USB capture of Armoury Crate changing the keyboard's polling rate now
exists in captures/. Decode it completely and produce the polling-rate
protocol document the owner needs for their own host-side application,
then cross-reference whatever the command touches in the firmware. This
is a host-protocol and evidence-analysis task. The capture was the only
live part; everything you do is offline file analysis.

READ FIRST, COMPLETELY
- logs/124-polling-rate-path.txt — the negative result this capture
  breaks: no polling-rate command was ever captured before; nothing in
  the firmware was found to consume a rate value; protocol.md records
  SetPollingRate/GetPollingRate as host HAL names.
- notes/protocol.md — the historical command record (startup query
  12 00, config family 51 xx, commit 50 55; the HAL opcode list).
- logs/107-phase5b-usb-routing.txt — the transport: interface 1,
  usage page 0xFF00, 64-byte unnumbered reports, OUT on EP 0x0d, IN on
  EP 0x85; the descriptor table; bInterval values (EP 0x81 = 1 =
  125 us = 8000 Hz, EP 0x8e = 4 = 1000 Hz).
- logs/125-profile-format.txt — the profile/settings format and the
  commit path, so you can recognise a commit if one follows a rate
  change.
- logs/82-ghidra-bootloader-framing.txt and FINDINGS.md "Bootloader
  vendor-HID wire framing" — the response-framing rules (query/echo
  shapes) as a model for interpreting responses.
- notes/ac-profile3-decoded.json — the historical profile decode;
  "performance": {"pollingRate": "3"} is the only known data point:
  rate is probably an INDEX, and "3" is one value of it.
- logs/92-full-app-region-backup.txt is context only — do not re-verify
  the backup; the capture is your subject.

STEP 0 — ENVIRONMENT VERIFICATION (before anything else)
- Run tshark --version and record it in the log. If tshark is missing,
  STOP and tell the owner; do NOT install anything and do NOT fall back
  to pip/scapy. No package installation of any kind.
- USBPcap field names vary by Wireshark version. Discover them rather
  than assuming: tshark -G fields | grep -i '^usb\|usb\.' and record
  which of usb.transfer_type, usb.endpoint_number,
  usb.bInterfaceNumber, usb.src, usb.dst, usb.capdata,
  usb.data_fragment, frame.time_epoch exist in this build. Use only
  fields that exist; document the ones you used.

OWNER-PROVIDED FACTS
The owner was asked to record: wall-clock times of the four rate
changes, the Armoury Crate version, whether any firmware-update prompt
appeared (it must have been declined — if it was not, STOP and report),
any accidental setting changes, whether the keyboard visibly
reconnected after a change, and whether a second (lighting) capture
exists. Read these from the owner's message accompanying the capture.
If they are absent, proceed using traffic landmarks instead, and record
which anchor method you used.

OPEN UNCERTAINTIES — resolve each explicitly, do not assume
U1. Command transport: the rate command may arrive as an interrupt-OUT
    report on interface 1 (EP 0x0d) OR as a SET_REPORT class request on
    EP0 (HID-class apps often use control transfers for config).
    Analyse BOTH paths for every window before concluding anything.
U2. Encoding direction: the value may ascend (1000->small,
    8000->large) or descend (index 0 = 8000). Check both directions
    against the owner's stated change order.
U3. Carrier shape: the rate may be a dedicated command OR one byte
    inside a larger profile-sync blob. For the blob case: align
    same-length frames from before and after each window and diff byte
    positions; a single changing byte with a plausible value mapping is
    a candidate — verify it repeats across at least two windows.
U4. Application timing: the change may apply immediately, only after a
    commit (50 55), or only on re-enumeration. The wire decides; record
    which, with frames.
U5. Re-enumeration: the device may reset and re-enumerate with NEW
    descriptors. If it does, extract the new configuration descriptor
    and diff bInterval per endpoint against log 107's (1,1,1,4,1). A
    bInterval change is a first-class protocol fact for the owner's
    app. Absence of re-enumeration is also a fact — record it.
U6. Background traffic: AC may poll the device periodically (battery,
    status, sync). Classify every periodic frame as
    required-for-function or ignorable-keepalive, with its period, so
    the owner's app knows what it must tolerate.
U7. Coalescing: if AC applied several changes at once (e.g. on window
    close) and fewer than four change-events are visible, say so and
    decode what IS there rather than inventing four.
U8. tshark output quirks: truncated payloads, reassembled control
    transfers split across URBs, and header-vs-data framing differ by
    version. Cross-check any surprising value against the raw frame
    bytes before accepting it.

INPUT DISCIPLINE
- The capture file(s) in captures/ are evidence. Never modify, move,
  or delete them. Record each file's sha256 in your log BEFORE
  analysing (sha256sum). If a file is large (> 50 MB), add its path to
  .gitignore instead of staging it, and say so.
- If the owner placed more than one capture (e.g. a lighting capture),
  analyse each for its stated purpose and keep the two strictly
  separate.
- The capture is in USBPcap/Wireshark pcapng format. tshark is
  installed. Do NOT install any package (no scapy, no pip, no apt) —
  parse with tshark -T fields / -T json and your own code.

STEP 1 — INVENTORY AND DEVICE IDENTIFICATION
- List every USB device address in the capture (tshark -T fields -e
  usb.src -e usb.dst | sort -u, or the pcapng interface list).
- Identify the Falchion: VID:PID 0b05:1b7e appears in GET_DESCRIPTOR
  control responses if the capture includes enumeration; otherwise
  identify it by traffic shape (periodic 64-byte interrupt reports on
  two endpoints plus 8-byte keyboard reports on a third). Note that the
  device address changes across replugs and across any re-enumeration —
  track ALL of its addresses.
- Beware other devices: mice, other keyboards, hubs. State explicitly
  how you separated them, and never merge another device's traffic into
  the analysis.
- Produce a timeline histogram of packet counts per second per device/
  endpoint, so the four deliberate rate changes are visible landmarks.
  Anchor it with the owner's wall-clock times when provided; otherwise
  use the traffic landmarks themselves and say which anchor method was
  used. Correlate each change with the owner's stated order:
  1000 -> 2000 -> 4000 -> 8000. If the visible landmarks do not match
  the stated order/count, resolve U7 before proceeding.

STEP 2 — THE POLLING-RATE COMMAND
For each of the four rate changes:
- Isolate the host->device frames in a +-2 s window around the change,
  on every interface (interrupt OUT on interface 1, and ALL control
  transfers — SET_REPORT and SET_CONFIGURATION included — on every
  interface).
- Diff each window against the steady-state traffic before it: which
  frames are NEW (not part of the periodic background)?
- For each candidate command frame record: timestamp, device address,
  transfer type, interface, endpoint, direction, the full 64-byte (or
  actual-length) payload in hex, and the device's response frame(s)
  with the same detail.
- Determine the encoding: which byte(s) change between the four
  commands, and what values they take for 1000/2000/4000/8000. Test
  whether the value is an index (0,1,2,3...), Hz/1000 (1,2,4,8), raw Hz
  (0x3e8, 0x7d0, 0xfa0, 0x1f40), a divisor, or something else. The
  historical profile's pollingRate "3" is a hint, not a rule — the wire
  wins any disagreement, and if "3" meant 8000, say what that implies
  for the index mapping.
- Determine whether a persistent commit (50 55 family) follows the
  rate change, and whether the device re-enumerates (new device
  address, fresh descriptors). If it re-enumerates, extract the NEW
  configuration descriptor and compare bInterval per endpoint against
  log 107's table (1,1,1,4,1) — a changed bInterval is a protocol fact
  of the highest importance for the owner's app.
- If NO frame visibly carries the rate (e.g. the change is a no-op on
  the wire, or rides inside a larger profile blob), say so precisely
  and show the evidence; do not force an interpretation.

STEP 3 — THE REST OF THE CONVERSATION (do not skip)
The owner needs the whole protocol surface, not just the rate command:
- Decode the startup handshake after enumeration: every query/response
  pair in the first 30 s, with the same per-frame detail. The
  historical record says the startup query is 12 00 — confirm or
  correct it from the wire.
- Identify periodic background traffic (keepalives, status polls) and
  classify it as ignorable or required, with its period.
- Decode any other command Armoury Crate sent unsolicited (version
  queries, capability reads, profile syncs) — each gets the same
  byte-level decode and a confidence label.
- If a second (lighting) capture exists, decode the lighting command
  the same way and cross-check it against the log-125 profile-format
  map (which profile-block fields the command writes).

STEP 4 — FIRMWARE CROSS-REFERENCE
Armed with the actual command bytes:
- Find the handler in the installed application: search for the
  command's opcode/subcommand in the vendor-HID dispatcher
  (0x18001fbe) and its branches. Trace where the rate value is stored
  and what consumes it (the candidates log 124 left open: a timer
  register, the prescaler, the mailbox to the second context, the
  descriptor table, or nothing visible).
- If you now find the consumer that log 124 could not, record it with
  the same evidence standards (listing citations, confidence,
  kind_basis) and note that log 124's negative stands for the
  pre-capture evidence state — do not rewrite log 124.
- Whether or not the consumer is found, state what the firmware does
  with the rate as far as the evidence reaches, and whether real Hz
  now attach to the tick (they may not — say so if they don't).

STEP 5 — DELIVERABLES
- notes/polling-rate-protocol.md + notes/polling-rate-protocol.json —
  THE document for the owner's app: the transport (interfaces,
  endpoints, report sizes), the startup sequence, the polling-rate
  command with exact byte offsets and the value mapping for
  1000/2000/4000/8000, the response shape, whether a commit is required
  to persist, whether re-enumeration occurs and what changes, the
  periodic traffic an app must tolerate, and an explicit NEVER-SEND
  list (50 55 commit, any erase/program/unlock framing) marked as
  owner-approval-only. Machine-readable JSON + generated Markdown from
  one data model with a --check mode, following the repo's existing
  tool conventions.
- A parser tool (tool/) that reproduces every decoded frame from the
  capture deterministically, with fail-closed unit tests (unknown
  device, truncated frame, wrong report size, the four rate windows,
  the re-enumeration branch if present). tshark may be invoked as a
  subprocess; no new dependencies.
- logs/126-polling-rate-capture-analysis.txt with raw command output
  (the tshark commands and their real output for every claim), the
  capture's sha256, and the full reasoning. Finalize it, add its
  sha256 to logs/SHA256SUMS, describe it in logs/COMMANDS.md.
- Update FINDINGS.md and TIMELINE.md only with demonstrated facts.
  Update the dependency map ONLY if the firmware consumer was actually
  found.

SAFETY AND BOUNDARIES
- Offline only: no /dev/hidraw, no USB/sysfs access, no sudo, no
  package install, no network access, no probe/backup/bootloader
  tools, and NEVER construct, transmit, or suggest transmitting any
  frame to the device — the protocol document describes frames as data
  for the owner's future app, each carry-capable command marked
  "owner approval required before use". The 50 55 commit and all
  unlock/erase/program/reset/SPI constructions are forbidden in code,
  tests, and prose examples.
- Do not modify: either evidence binary, any historical log,
  opencode.json, or the capture file. No staging, unstaging, or
  committing — the owner handles git. Preserve every pre-existing
  uncommitted change (logs 118-125's work exists in the tree; do not
  revert any of it).
- Distinguish observed-on-the-wire (this capture), historical
  observation (protocol.md, AC decode), and static firmware analysis
  in every claim's confidence label.

VERIFICATION (all must pass)
- sha256 of both evidence binaries before and after (must equal
  fc6128ab089e4fd712b172c54cd88b7f28476b55bdac688134e052281ded637b and
  6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d).
- python3 -m py_compile on all changed Python files.
- The FULL suite from the repository directory with exactly:
  python3 -m unittest discover -s "$PWD/tool" -t "$PWD/tool"
- Every --check script (all existing ones plus your new one):
  reports_current=True stale=0.
- sha256sum -c logs/SHA256SUMS — all OK.
- git diff --check — clean.

FINAL REPORT MUST INCLUDE
- files changed; exact commands run; test counts;
- the capture inventory (files, hashes, device addresses, packet
  counts) and the tshark version plus the field names used;
- an explicit answer to EVERY uncertainty U1-U8 (resolved how, or
  blocked on what evidence);
- the polling-rate command decode (frames, bytes, value mapping,
  response, commit?, re-enumeration?);
- the startup/background/other-command decodes;
- the firmware cross-reference result with confidences;
- whether real Hz attach to anything now, and what still needs hardware
  evidence;
- assumptions and unresolved items;
- an explicit statement that no device was accessed and no frame was
  constructed for transmission.
Leave everything uncommitted for review.
```
