# Windows capture runbook

Everything here is read-only with respect to the keyboard. Nothing writes to the device and
nothing touches firmware.

## Scripts

| script | elevated? | what it does |
|---|---|---|
| `snap-config.ps1` | no | decode + diff Armoury Crate's on-disk profile |
| `haltrace.ps1` | **yes** | live capture of the ASUS HAL's own `[Class][Method]` debug log |
| `capture.ps1` | **yes** | start a USBPcap capture on the right root hub |
| `decode.ps1` | no | pull HID reports out of a `.pcapng`, annotate, diff two captures |

Elevation matters: USBPcap interfaces are **invisible** to non-admin processes, and the
DBWIN buffer needs `Global\` access to see the Armoury Crate service. `capture.ps1` and
`haltrace.ps1` both refuse to run unelevated rather than silently capturing nothing.

---

## The run — about 10 minutes

Open **two Administrator PowerShell windows**, both `cd` to `keyboard\falchion-re`.

### Window 1 — HAL trace

```powershell
.\tools\haltrace.ps1 -Out captures\haltrace.log -FilterAsus
```

This is the high-value one. Every time Armoury Crate does anything, the HAL logs the exact
method name (`[AacM605Function][ChangeKey_Normal]`, etc.) with a timestamp. Match those
timestamps against the pcap and you get method-to-packet labelling for free instead of
guessing what an opcode means.

If it errors about the buffer, close DebugView / any other Sysinternals listener first.

### Window 2 — USB capture

```powershell
.\tools\capture.ps1 -List                                     # confirm the interface
.\tools\capture.ps1 -Out captures\01-ac-first-launch.pcapng
```

If several `USBPcapN` interfaces are listed, start a short capture on each and unplug/replug
the keyboard — the one that records the enumeration burst is yours. Then pass
`-Interface \\.\USBPcapN`.

### Then, with both running

1. **Launch Armoury Crate for the first time.** Let it find the keyboard. This captures the
   init/handshake, which you only get once cleanly.
2. Baseline the config:
   ```powershell
   .\tools\snap-config.ps1 -Save snapshots\before.json
   ```
3. **Remap one normal key** — `F1` → `A`. Apply.
4. ```powershell
   .\tools\snap-config.ps1 -Save snapshots\after-f1a.json -Diff snapshots\before.json
   ```
   The `keyfunction_<col>_<row>` that changed **is** F1's matrix coordinate. That verifies
   (or kills) the key-name table in `notes/key-matrix.md`.
5. Repeat for 2–3 more keys spread across the board, saving a new snapshot each time.

### The one that matters — Phase 3.6

6. Try to remap a **locked Fn key**. Apply. Then:
   ```powershell
   .\tools\snap-config.ps1 -Save snapshots\after-fn.json -Diff snapshots\before.json
   ```

Three possible outcomes, and each one decides the project:

| what you see | meaning |
|---|---|
| config unchanged **and** no new packets in the pcap | lock is **client-side UI only**. Best case — build the tool, skip Phase 4 entirely. |
| config changed and packets sent, but the key doesn't work after a replug | firmware silently ignores it. |
| a reply starting `FF AA` in the capture | firmware actively rejected it (see protocol.md §3). |

Record which in `notes/findings.md`.

---

## Afterwards

```powershell
.\tools\decode.ps1 -Path captures\01-ac-first-launch.pcapng
.\tools\decode.ps1 -Path captures\remap-f1-a.pcapng -Diff captures\remap-f1-b.pcapng
```

`decode.ps1` prints an opcode histogram and, in `-Diff` mode, only the reports unique to
each capture — which is how you isolate the one byte that changed.

Captures are gitignored (`**/*.pcapng`). Copy them to the Linux box if you prefer `tshark`
there; USBPcap payloads land in the same `usb.capdata` field, so the guide's Linux commands
work unchanged.
