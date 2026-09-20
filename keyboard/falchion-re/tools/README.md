# Tools

Windows-side tooling for the Falchion Ace HFX work. See `../notes/protocol.md` for what the
bytes mean, and `../notes/windows-behavior-capture-plan.md` before running any experiment.

These tools preserve earlier protocol work; they are not all approved for the
current firmware-preservation phase. Passive capture, offline decode, config-file
snapshotting, and key observation do not send keyboard commands. `send.ps1` does
and must not be used without a separate explicit write-test plan and approval.

| script | elevated? | writes to keyboard? | purpose |
|---|---|---|---|
| `snap-config.ps1` | no | no | snapshot + recursively diff every Armoury Crate profile |
| `keywatch.ps1` | no | no | show the real vk/scan code of a keypress |
| `decode.ps1` | no | no | pull the 64-byte vendor reports out of a capture, annotate, diff |
| `haltrace.ps1` | **yes** | no | live capture of the ASUS HAL's `[Class][Method]` debug log |
| `capture.ps1` | **yes** | no | start a passive USBPcap capture |
| `send.ps1` | no | **YES** | send a raw 64-byte command on the 0xFF00 channel |

## Offline twins, and what they do and do not prove

PowerShell cannot be executed in this repository's Linux environment, so three of these
scripts have an offline counterpart under `../tool/` that the unit suite runs. The
counterpart owns the rules; the `.ps1` implements them; a `--check` fails if they drift.

| PowerShell script | offline twin | what the suite actually proves |
|---|---|---|
| `decode.ps1` | `tool/decode_capture.py` | the twin's **own** decode of `captures/02-polling-rate.pcap` reproduces log 126: subject found by VID:PID at bus 3 addresses 6 **and** 7, endpoints 0x0d/0x85 only, 74 requests and 74 replies, twenty `51 31`, twenty `50 55`; plus row-level fixtures for two buses sharing one address, and address reuse |
| `capture.ps1`, `haltrace.ps1` | `tool/windows_tools.py` | the **rules** execute: collision refusal, unenumerated-interface refusal, native-failure handling, zero-byte and non-capture output handling, DBWIN `ERROR_ALREADY_EXISTS` detection. The `.ps1` files themselves are only checked *structurally*, including the order of those guards |
| `snap-config.ps1` | `tool/profile_diff.py` | the twin's **own** recursive diff detects a mutation in each required category of `notes/ac-profile3-decoded.json`, distinguishes JSON number/string/Boolean/null, and reports "NO CHANGE" only when the whole model is equal |

### What the twins do NOT prove

**They do not execute any PowerShell.** For `capture.ps1`, `haltrace.ps1` and
`snap-config.ps1` the `--check` modes are *token and ordering checks over the script
text*. They catch a guard being deleted, reordered, or a constant drifting. They are not
an equivalence proof: nothing here shows that `Get-Flat` in PowerShell and `flatten()` in
Python produce the same result for the same input, or that `Get-Canonical` and
`canonical()` agree on a given number. Those are **open Windows-only validation items**.

`decode.ps1` is the same situation with one difference: the Python twin genuinely decodes
the preserved capture, so the *rules* are proven against real evidence. The PowerShell
transcription of those rules is still unexecuted.

```bash
python3 tool/decode_capture.py captures/02-polling-rate.pcap
python3 tool/decode_capture.py --check
python3 tool/windows_tools.py --check
python3 tool/profile_diff.py --categories
python3 tool/profile_diff.py --check
```

**STILL REQUIRES A WINDOWS HOST.** The twins prove the rules and the scripts' structure,
not the PowerShell runtime. Not yet executed anywhere:

- the actual refusal of an existing `-Out` in all three scripts;
- `Get-PnpDevice` enumeration and the USBPcap extcap launch;
- `Get-FileHash` output and the `saved:` gate;
- `Get-SubjectKey`'s bus-scoped identity parsing against a real multi-bus capture, and
  its descriptor-identity-conflict refusal;
- `Get-Flat` / `Get-Canonical` agreeing with `flatten()` / `canonical()` on real profiles;
- `-AllProfiles` against a real `C:\ProgramData\ASUS\...` folder;
- the DBWIN P/Invoke path, including the `ERROR_ALREADY_EXISTS` branch and the
  header-only zero-event artifact.

**Every `.ps1` in this directory is Windows-unvalidated.** Record the first Windows run
of each in the log for that session.

---

## send.ps1 — quarantined device-write tool

Opens `MI_01` (usage page 0xFF00) and writes a 65-byte report (`0x00` placeholder + 64-byte
payload), then reads the reply.

The script is retained for reproducibility, but command examples are intentionally
not presented as instructions to run. Recorded traffic associates `12 00` with a
version query, `51 21` with a live binding change, and optional `-Commit` with
`50 55` persistent storage. All are undocumented vendor-HID transactions.

**Safety model:**

- By default it does **not** send the recorded `0x50 0x55` persistent commit, but a
  configuration command still changes live device state. It is not read-only.
- `-Commit` is a known persistent settings write and is prohibited during
  preservation.
- `Fn + Caps` resets settings only. It is not recovery from damaged firmware or a
  failed bootloader.
- The echoed reply does not establish that a command was accepted or harmless.

**Do not trust the ACK.** The device echoes the request header verbatim even when it discards
the write. Always verify with `keywatch.ps1` or by observing the key. See protocol.md §5.

## keywatch.ps1

Small always-on-top window logging the virtual-key code of each keypress. Necessary because
"F1", "9" and "nothing" are indistinguishable in a text box.

```powershell
.\keywatch.ps1     # focus the window, press the key, Esc to quit
```

## snap-config.ps1

```powershell
.\snap-config.ps1 -AllProfiles -Save ..\snapshots\before.json
# change ONE thing in Armoury Crate, Apply
.\snap-config.ps1 -AllProfiles -Save ..\snapshots\after.json -Diff ..\snapshots\before.json
```

`-AllProfiles` preserves every `fp_*_config_*.xml` in the folder with its source filename,
full path, mtime and SHA-256 beside the decoded JSON, so the diff can say *which profile
file* changed — which is what a profile-switch experiment needs.

The diff is a deterministic recursive comparison of every path in the decoded model. It
catches global rapid trigger, per-key rapid trigger, actuation, polling rate, Speed Tap,
dead zones, lighting and lever settings, not only `keyfunction_<col>_<row>` entries.
`NO CHANGE` therefore means the complete compared model is equal.

An existing `-Save` path is refused; use `-Unique` for a timestamped name.

## capture.ps1 / decode.ps1 / haltrace.ps1

```powershell
.\capture.ps1 -List
.\capture.ps1 -Out ..\captures\03-profile-switch.pcapng          # refuses a collision
.\capture.ps1 -Out ..\captures\03-profile-switch.pcapng -Unique  # timestamped name
.\decode.ps1  -Path ..\captures\03-profile-switch.pcapng
.\decode.ps1  -Path ..\captures\03b.pcapng -Diff ..\captures\03a.pcapng
.\haltrace.ps1 -Out ..\captures\03-haltrace.log -Unique -FilterAsus
```

Run `haltrace.ps1` alongside a capture to label packets by HAL method name instead of
guessing what an opcode does.

`capture.ps1` refuses an existing `-Out` and has **no** `-Force`. After tshark exits it
checks tshark's own exit status, that the file exists, is non-empty and starts with a pcap
or pcapng magic number, and only then prints `saved:` with the size and SHA-256. A failed
run prints `FAILED` and removes the zero-byte stub.

`haltrace.ps1` requires elevation (it exits rather than warning), uses `Global\` only, and
refuses to start if `ERROR_ALREADY_EXISTS` says another listener already owns DBWIN. Its
remaining limitation is inherent to DBWIN and is not fixable here: the buffer has one slot
and no queue, so messages emitted before the listener starts, or between its `Wait` calls,
are lost. **A missing line is not evidence that a HAL call did not happen.**

---

## Environment gotchas

Each of these cost real time. Written down so they don't again.

**USBPcap needs a reboot after install.** It attaches as an upper filter to the USB hub
stacks, and existing hubs only pick it up when they restart. Symptom: `UpperFilters = USBPcap`
present in the registry, driver file present, service Running — but no `\\.\USBPcapN` control
devices exist.

**USBPcap is an *extcap* interface.** `dumpcap -D` will **never** list it. Use `tshark -D` to
enumerate and `tshark -i` to capture. This looks exactly like a broken driver if you don't
know it.

**Elevation causes false negatives.** `\\.\USBPcapN` and the USBPcap interface list are
invisible to non-admin processes. When probing, distinguish `UnauthorizedAccessException`
("exists, needs elevation") from `FileNotFoundException` ("genuinely absent") — otherwise a
working install reads as a missing one.

**Payloads are in `usbhid.data`, not `usb.capdata`.** For USBPcap captures dissected by
Wireshark 4.6/4.7, `usb.capdata` is empty on the vendor endpoints; the offline suite
re-derives that from the preserved capture rather than quoting it. Note that the device
address is **not** stable: the same keyboard is address 2 in `01-first-launch.pcapng` and
addresses 6 **and** 7 in `02-polling-rate.pcap`, which spans a replug. Identify it by
VID:PID and read the addresses off the wire:

**A USB address is scoped to a bus**, and `capture.ps1` records every USBPcap interface
into one file. In `01-first-launch.pcapng`, address 1 is an ASMedia hub on bus 2 *and* a
Logitech receiver on bus 3, on two different capture interfaces. Identity is therefore
`(frame.interface_id, usb.bus_id, usb.device_address)`, and the report filter uses the
same scoped key:

```
usb.idVendor                                  # -> (interface, bus, address) -> 0b05:1b7e
((usb.bus_id==3 && usb.device_address==6) || (usb.bus_id==3 && usb.device_address==7))
  && (usb.endpoint_address==0x0d || usb.endpoint_address==0x85)
  && usb.data_len==64
```

`decode.ps1` and `tool/decode_capture.py` build that second filter themselves from the
first query, re-check the scope on every row, and **refuse the capture** on a
**descriptor-identity conflict**: one interface/bus/address key that reported more than
one `(idVendor, idProduct, bcdDevice)` tuple. Both implementations use those same three
fields, and a `--check` fails if either drops `usb.bcdDevice`.

**That is not full address-reuse detection, and is not claimed to be.** An address reused
by a device with an *identical* descriptor — two units of the same model at the same
firmware revision — is invisible to this method. USBPcap gives no reset or enumeration
epoch that would separate them reliably, so the limitation stands and is Windows-only to
investigate further.

**Correlating a capture with a HAL trace needs absolute time.** `frame.time_relative` is
relative to the first frame of its own file. Both decoders now carry `frame.time_epoch`,
and `haltrace.ps1` stamps every line and its session header in UTC. The alignment is
still approximate and manual: they are two different clocks.

**PowerShell execution policy.** `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force`
per session, or `-Scope CurrentUser -ExecutionPolicy RemoteSigned` permanently.

**`capture.ps1` used to overwrite `-Out` without asking**, and the original first-launch
capture was lost that way. It now refuses, and there is deliberately no override switch.

**Armoury Crate mutates state between tests.** It rewrites the config and can re-apply
settings, which invalidates a controlled experiment. For any A/B, do not open AC between the
two writes. `notes/windows-behavior-capture-plan.md` makes that an abort condition.
