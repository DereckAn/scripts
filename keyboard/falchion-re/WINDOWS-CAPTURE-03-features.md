# Capture 03 — Windows runbook (feature validation)

Self-contained. Follow top to bottom on the Windows machine. ~5 minutes.

## ⚠️ The one rule that matters most

**DECLINE every firmware-update prompt in Armoury Crate.** If anything
that looks like an update starts, cancel it and stop. Settings changes
are fine; firmware updates are not.

## Pre-flight (once)

1. Wireshark **with USBPcap** installed (USBPcap is a separate
   component/download — if Wireshark shows no USBPcap interfaces,
   install USBPcap and reboot).
2. Keyboard plugged in, Armoury Crate installed and working.
3. A text file open (Notepad) to note times, in this format:

   ```text
   ACTION 1 profile switch 1->2     time: __:__:__
   ACTION 2 profile switch back->1  time: __:__:__
   ACTION 3 actuation change        time: __:__:__
   ACTION 4 rapid trigger change    time: __:__:__
   ACTION 5 remap one key           time: __:__:__
   ACTION 6 record one macro        time: __:__:__
   ACTION 7 lighting brightness     time: __:__:__
   AC version: ______
   update prompt appeared? Y/N: ___
   anything unexpected: ____________
   ```

## The capture

1. Open Wireshark, start capturing on a **USBPcap** interface.
2. Wait ~15 s of idle traffic.
3. Do each action below, **waiting ~15 seconds between actions** and
   writing down the wall-clock time of each. Do them in order — the
   order is how we tell them apart:

   | # | Do this in Armoury Crate | Notes |
   |---|--------------------------|-------|
   | 1 | Switch profile: 1 → 2 | stay ~15 s |
   | 2 | Switch profile: 2 → 1 | |
   | 3 | Actuation: change global value one step (note from/to) | e.g. 2.0 → 2.5 mm |
   | 4 | Rapid trigger: change press and/or release value (note from/to) | |
   | 5 | Remap ONE ordinary key to something harmless (note which key and what you mapped it to) | e.g. Caps Lock → Left Ctrl; avoid Fn-layer and reserved keys |
   | 6 | Record ONE tiny macro on one key: sequence `a, b, c` (note which key) | if AC has a macro editor; if it does not, write "no macro UI" |
   | 7 | Lighting: change brightness once (note from/to) | |

4. Wait ~15 s more, then **stop the capture**.
5. Save as `03-features.pcap` (pcap format, not pcapng, is fine either way).
6. Fill in the Notepad answers (AC version, update prompt Y/N, anything
   unexpected).

## After, back on Linux

1. Copy the file to `keyboard/falchion-re/captures/03-features.pcap`.
2. Paste your Notepad notes to the session when you run the log-129
   validation prompt (it asks for the action order and times).
3. Do not rename or edit the pcap after saving it — its hash goes into
   the evidence log.

## If something goes wrong

- **AC applied a firmware update anyway:** say so immediately. Do not
  unplug mid-update. Tell the review session — the installed baseline
  changed and we plan around it.
- **Keyboard disconnected/reconnected during an action:** note the time
  and keep going; a re-enumeration is itself valuable data.
- **AC did nothing visible on an action:** note "no visible effect" and
  keep going — that is a finding too.
