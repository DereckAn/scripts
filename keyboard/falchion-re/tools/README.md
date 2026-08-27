# Tools

Windows-side tooling for the Falchion Ace HFX work. See `../notes/protocol.md` for what the
bytes mean.

| script | elevated? | writes to keyboard? | purpose |
|---|---|---|---|
| `snap-config.ps1` | no | no | decode + diff Armoury Crate's on-disk profile |
| `keywatch.ps1` | no | no | show the real vk/scan code of a keypress |
| `decode.ps1` | no | no | pull HID reports out of a `.pcapng`, annotate, diff two captures |
| `haltrace.ps1` | **yes** | no | live capture of the ASUS HAL's `[Class][Method]` debug log |
| `capture.ps1` | **yes** | no | start a USBPcap capture |
| `send.ps1` | no | **YES** | send a raw 64-byte command on the 0xFF00 channel |

---

## send.ps1 — the important one

Opens `MI_01` (usage page 0xFF00) and writes a 65-byte report (`0x00` placeholder + 64-byte
payload), then reads the reply.

```powershell
.\send.ps1 -Bytes '12 00'                      # GetVersion — safe liveness probe
.\send.ps1 -Bytes '51 21 18 9F 09 00 0A 00'    # remap Fn+I
.\send.ps1 -Bytes '51 21 18 9F 09 00 0A 00' -Commit   # ...and persist to flash
```

**Safety model:**

- By default it does **not** send `0x50 0x55`, so nothing is written to flash. The change
  still takes effect immediately in RAM — **replug to revert.**
- `-Commit` persists. Recovery from a bad committed state: **`Fn + Caps`, hold until the LEDs
  blink green** (hardware factory reset, documented in the manual, no Armoury Crate needed).

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
.\snap-config.ps1 -Save snapshots\before.json
# change one thing in Armoury Crate, Apply
.\snap-config.ps1 -Save snapshots\after.json -Diff snapshots\before.json
```

Prints only the `keyfunction_<col>_<row>` entries that changed, decoding `source_key` into
row/col/layer.

## capture.ps1 / decode.ps1 / haltrace.ps1

```powershell
.\capture.ps1 -List
.\capture.ps1 -Out ..\captures\session.pcapng     # captures all root hubs; no guessing
.\decode.ps1  -Path ..\captures\session.pcapng
.\haltrace.ps1 -Out ..\captures\haltrace.log -FilterAsus
```

Run `haltrace.ps1` alongside a capture to label packets by HAL method name instead of
guessing what an opcode does.

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
Wireshark 4.6, `usb.capdata` is empty. Filtering the keyboard's config channel:

```
usb.bus_id==2 && usb.device_address==2 && (usb.endpoint_address==0x0d || usb.endpoint_address==0x85) && usb.data_len==64
```

**PowerShell execution policy.** `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force`
per session, or `-Scope CurrentUser -ExecutionPolicy RemoteSigned` permanently.

**Don't reuse `-Out` filenames.** `capture.ps1` overwrites without asking; the original
first-launch capture was lost that way.

**Armoury Crate mutates state between tests.** It rewrites the config and can re-apply
settings, which invalidates a controlled experiment. For any A/B, do not open AC between the
two writes.
