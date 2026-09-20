# Controlled Windows behaviour-capture plan

Status: **plan only**. Written 2026-09-20 (log 131). Nothing here has been executed.

## What this authorises, and what it does not

This plan covers **passive observation of normal Armoury Crate use**. The host watches;
the operator drives Armoury Crate exactly as a normal owner would; USBPcap records what
Armoury Crate itself puts on the wire.

**It is not firmware-flashing authorisation and it is not authorisation to use
`tools/send.ps1`.**

> **Armoury Crate's Apply button normally sends state-changing configuration commands, and
> it may send a persistent `50 55` commit.** That is not a side effect of this plan; it is
> what Armoury Crate does. Every experiment below therefore changes live device settings
> and probably writes them to the keyboard's non-volatile storage. The final experiment
> exists to put the settings back. Accept that before starting, or do not start.

### Prohibited outright, in every experiment here

- `tools/send.ps1`, or any other tool that writes a report to the device
- raw replay of a captured frame, in whole or in part
- "restore factory defaults" / `Fn`+`Caps` reset
- any firmware update, from Armoury Crate, the ASUS updater or anything else
- bootloader entry (PID `1b7f`), `dfu-util`, or any vendor update mode
- erase, program, unlock, reset or SPI commands of any kind
- declining, dismissing or postponing a firmware-update prompt and continuing anyway —
  see the abort conditions

Everything this plan produces is **observation of Armoury Crate's traffic**, never traffic
this project generated.

## Per-capture rules

Every capture, without exception:

1. **A unique filename.** `capture.ps1` refuses a collision and has no override; use
   `-Unique` when in doubt. The same goes for the HAL trace and both snapshots.
2. **Raw PCAP preserved.** Keep exactly what USBPcapCMD wrote. Do not `editcap`, filter,
   trim or re-save the primary file. Derived files are additional, never replacements.
3. **A HAL trace alongside it**, started before the capture and stopped after it
   (`haltrace.ps1 -Unique -FilterAsus`). This applies to **every** experiment, including
   experiment 3 with Armoury Crate closed. `haltrace.ps1` writes its session header
   before it starts listening, so a run in which nothing logs still produces a file with
   a start time, an end time, a line count of zero and a SHA-256. **A zero-event trace is
   the expected result of experiment 3 and is itself evidence** — that the keyboard
   changed profile with no HAL call at all. Record it like any other artifact.
4. **Complete before/after profile snapshots**, both with `-AllProfiles`, so every
   `fp_*_config_*.xml` is preserved with its filename, mtime and SHA-256.
5. **Screenshots** of the Armoury Crate pane immediately before and immediately after the
   change, showing the control and its value.
6. **Action timestamps**, written down by hand, to the second, from the **Windows wall
   clock**: capture start, AC launch, the click, the Apply, capture stop.

   > **The three clocks are not the same clock.** USBPcap frames are stamped by the
   > capture engine, `haltrace.ps1` stamps lines from the Windows wall clock, and the
   > hand-written times are whatever the operator read off the screen. Nothing aligns
   > them automatically. Correlate on **absolute** time only — `frame.time_epoch` or
   > `frame.time` from the capture against the UTC stamps in the HAL trace header and
   > lines. `decode.ps1` and `tool/decode_capture.py` carry `frame.time_epoch` for
   > exactly this. `frame.time_relative` is relative to the first frame of its own file
   > and cannot be compared with anything outside it. Treat every cross-artifact
   > alignment as **approximate and manual**, and never present a HAL line and a USB
   > frame as simultaneous on the strength of the arithmetic alone.
7. **SHA-256 of every artefact** — pcap, HAL trace, both snapshots, every screenshot —
   recorded in the log for that session before anything else is done with them.
8. **Exactly one controlled change per capture.** If a second setting moves, the capture is
   spoiled; record it as spoiled and redo it. Do not analyse a two-change capture.

Stop the capture before starting the next experiment. One experiment, one file set.

## The experiments

Run in this order. Each is a complete capture with its own file set.

| # | Experiment | The one change | Purpose |
|---|---|---|---|
| 1 | Armoury Crate startup, no change | none | the baseline conversation, so every later capture can subtract it |
| 2 | Profile switch in Armoury Crate | select a different profile, Apply | isolate the profile-switch command |
| 3 | Onboard/`Fn` profile switch, Armoury Crate **closed** | the key combination only | what the keyboard does with no host software involved. **A zero-event HAL trace is the expected outcome here**, and the header-only artifact is still captured and hashed |
| 4 | Reopen Armoury Crate after experiment 3 | launch AC, change nothing | does AC read the onboard state, or overwrite it? |
| 5 | All-key Rapid Trigger off → on | the global Rapid Trigger toggle | isolate the all-key rapid-trigger command |
| 6 | All-key press distance | press distance only | separate press from release |
| 7 | All-key release distance | release distance only | separate release from press |
| 8 | One per-key Rapid Trigger override | one key, rapid trigger on | per-key versus all-key encoding |
| 9 | All-key actuation | actuation only | isolate the all-key actuation command |
| 10 | One per-key actuation override | one key, actuation only | per-key versus all-key encoding |
| 11 | Restoration | put every setting back to the experiment-1 values | leave the device as it was found |

Experiment 11 is not optional and is not a formality: diff its after-snapshot against
experiment 1's before-snapshot and record any path that did not come back.

## Hypotheses to test — static, NOT wire-proven

These come from the firmware images and from log 128's command map. **None of them has been
observed on the wire for the operation named.** They are what the captures are for; a
capture that contradicts one is a result, not a mistake.

| Hypothesis | Opcode | Standing |
|---|---|---|
| profile switch | `51 00` | static only — from the firmware's command map |
| all-key actuation | `51 50` | static only |
| per-key actuation | `51 4f` | static only |
| all-key rapid trigger | `51 58` | static only |
| per-key rapid trigger | `51 59` | static only |
| persistent commit | `50 55` | **observed** in `captures/02-polling-rate.pcap`, twenty times, following every `51 31` — but observed as *a* commit, not proven to be the commit for any of the rows above |

The one fully wire-proven member of this family is `51 31`, the polling rate, with a
one-byte index at payload offset 4 (log 126). Treat that as the template for what
"proven" means here, and do not promote a row above until a capture shows it.

## Configuration protocol versus physical behaviour

These are two different investigations and the captures only serve the first.

- **USB traffic proves what configuration was sent.** It shows the opcode, the operand and
  whether a commit followed. That is the protocol.
- **It does not measure Hall travel, actuation depth or rapid-trigger thresholds.** A
  capture showing `51 58 ... 07` does not establish that the key now actuates at 0.7 mm; it
  establishes that Armoury Crate asked for whatever `07` means. Millimetres are a physical
  claim and need a physical measurement — a reference travel gauge, or at minimum a
  repeatable keypress-depth rig — which this plan does not include and must not pretend to.

Write protocol findings and behaviour findings in separate sections of the session log, and
never let a protocol observation carry a millimetre figure.

## Abort conditions

Stop immediately, stop the capture, write down what happened, and do not continue:

- **a firmware-update prompt appears** anywhere in Armoury Crate, however dismissible
- **unexpected re-enumeration**, or the PID changes from `1b7e` (in particular to `1b7f`,
  the bootloader)
- **the capture failed** — `capture.ps1` printed `FAILED`, or no `saved:` line with a size
  and SHA-256 appeared
- **the decoder refused the capture** — `decode.ps1` reported a *descriptor-identity
  conflict*: one interface/bus/address key reported more than one
  `(idVendor, idProduct, bcdDevice)` tuple, so no filter can separate the traffic. Note the
  converse is not a guarantee: an address reused by a device with an identical descriptor
  is undetectable, so a capture that passes has not been proven free of address reuse
- **a snapshot is missing** — either the before or the after `-AllProfiles` snapshot was not
  taken, or it refused to write and the refusal was not resolved before the change
- **more than one UI change was made**, including one made by accident and undone
- **Armoury Crate applied something unrelated** — the after-snapshot shows changed paths
  outside the setting under test, e.g. it re-applied lighting or rewrote another profile
- the HAL trace refused to start because another listener owned DBWIN, and the run
  continued without it (a *zero-event* trace is not this: that is a result, and the
  artifact still exists)

An aborted run is preserved, not deleted: keep the files, hash them, and label the log
entry ABORTED with the reason.
