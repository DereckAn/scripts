# ROG Falchion Ace HFX — Reverse Engineering Guide

> ## STATUS — synchronized 2026-08-29
>
> **Current results live in
> [`falchion-re/FINDINGS.md`](falchion-re/FINDINGS.md). Read that first. This file
> is a roadmap and historical plan, not the authoritative findings or a command
> checklist.**
>
> - [`notes/findings.md`](falchion-re/notes/findings.md) — summary, status, open questions
> - [`notes/protocol.md`](falchion-re/notes/protocol.md) — full protocol spec
> - [`notes/key-matrix.md`](falchion-re/notes/key-matrix.md) — key indices + config format
> - [`tools/README.md`](falchion-re/tools/README.md) — tooling + environment gotchas
>
> Earlier device testing recorded both an Armoury Crate UI restriction and
> device-side filtering of reserved Fn remaps. The cited raw PCAPs are missing, so
> this remains a strong historical observation rather than a result independently
> reproducible from the current checkout.
>
> An authentic ASUS 1.00.58 image is preserved and offline Ghidra work has begun.
> It is not an exact backup of installed version 1.59, and neither USB downgrade,
> SWD recovery, nor external-flash restoration has been proven. Do not flash.

**Goal:** Replace Armoury Crate with a cross-platform config tool, and unlock the Fn keys that ASUS won't let you remap.

**Device:** ROG Falchion Ace HFX 65% — USB VID `0x0B05`, PID `0x1B7E`

**Host:** CachyOS (Arch-based)

---

## Guiding principle

Do the **non-destructive** work first. Enumeration, passive capture, and offline
analysis can be read-only. Replaying HID reports, changing settings, factory
resetting, entering a bootloader, and changing host permissions are not read-only
and require separate approval. Do not touch firmware without an exact backup and a
proven recovery path.

**Never flash anything before completing Phase 2.**

---

## Phase 0 — Setup

The commands in this phase change the host by installing packages, loading kernel
modules, changing group membership, or creating permissions. They are retained as
historical setup notes, not pre-approved actions. Use the narrowest access rule
possible and explain each host change before applying it.

### 0.1 Install tools

```bash
# USB inspection + HID access
sudo pacman -S usbutils hidapi libusb dfu-util

# Packet capture
sudo pacman -S wireshark-qt
sudo usermod -aG wireshark $USER

# Rust HID work (you already have rustup presumably)
# cargo add hidapi  -- later, in the project

# Python for quick prototyping
sudo pacman -S python python-pip
pip install --user hidapi pyusb
```

Log out/in for the `wireshark` group to take effect.

### 0.2 Enable usbmon

```bash
sudo modprobe usbmon
# make it persistent
echo usbmon | sudo tee /etc/modules-load.d/usbmon.conf
```

### 0.3 udev rule for non-root HID access

Create `/etc/udev/rules.d/99-asus-keyboard.rules`:

```
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0b05", ATTRS{idProduct}=="1b7e", TAG+="uaccess"
```

Then:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Replug the keyboard.

### 0.4 Set up a project repo

```bash
mkdir -p ~/projects/falchion-re/{captures,dumps,notes,tool}
cd ~/projects/falchion-re
git init
echo "captures/*.pcapng" >> .gitignore  # these get large
```

Keep a `notes/findings.md` as you go. This work is slow and you WILL forget what byte 7 meant three days later.

---

## Phase 1 — Identify the hardware (non-destructive)

### 1.1 Enumerate the USB device

```bash
lsusb -d 0b05:1b7e -v > notes/usb-descriptors.txt
```

Look for and record in your notes:
- Number of interfaces (there will be several — keyboard, mouse-ish, vendor-specific)
- Which interface is **vendor-defined** (usually `bInterfaceClass: 3 (HID)` with a vendor usage page like `0xFF00`) — this is almost certainly the config channel Armoury Crate uses
- Endpoint addresses and max packet sizes (tells you report sizes, likely 64 bytes)
- `bcdDevice` — the firmware version

### 1.2 List HID report descriptors

```bash
ls -l /sys/class/hidraw/
# for each hidrawN that maps to your device:
sudo cat /sys/class/hidraw/hidraw0/device/report_descriptor | xxd > notes/report-desc-0.txt
```

Confirm which hidraw node is yours:

```bash
for d in /sys/class/hidraw/hidraw*; do
  echo "== $d"
  cat $d/device/uevent | grep HID_NAME
done
```

### 1.3 Check for DFU / bootloader mode

```bash
sudo dfu-util -l
```

Also check whether ASUS exposes a DFU interface only after a magic command, or via a physical key combo (check the manual — some ROG boards use a hold-key-while-plugging sequence).

### 1.4 Identify the MCU

Two routes:

**Software route (try first):**
- If a DFU interface appears, `dfu-util -l` will often print the chip/alt-settings which hint at the family
- Check ASUS's firmware updater package (Phase 2.2) — updater binaries often name the target chip

**Physical route:**
- Open the case (Falchion Ace HFX: remove keycaps, unscrew plate, watch for the touch panel ribbon cable — be gentle with it)
- Photograph the main IC markings, and any secondary ICs (the HE sensing ADC/multiplexers)
- Record: MCU part number, flash size, any SWD test pads (look for `SWDIO` / `SWCLK` / `RST` / `GND` labels or a 4–5 pad cluster near the MCU)

**Record findings before continuing.** The MCU family determines everything downstream.

---

## Phase 2 — Backup and recovery prep (DO THIS BEFORE ANY WRITE)

### 2.1 Installed-firmware backup status

Normal mode exposes no DFU interface, so the generic DFU upload experiment does
not apply to this keyboard. An error or an all-zero/all-`0xFF` result would not by
itself identify a specific readout-protection state.

No installed-1.59 dump exists. Proprietary HID readback is unresolved. Future
hardware readback must start with a wiring/power/isolation plan for U5 and the
SNC73270, then use repeated read-only dumps with identical hashes. Never issue SPI
Write Enable, Program, or Erase commands during preservation.

### 2.2 Official firmware reference — completed offline

The official ASUS Armoury Crate Gear 1.0.1.15 ZIP is preserved locally with its
published hash. It contains `M605_V01_00_58.bin`, a 507,904-byte combined
bootloader/application image. The BIN is version 1.00.58, while the connected
keyboard reports 1.59. It is valuable reference/recovery material, but it is not
an installed-firmware backup and downgrade acceptance is unknown.

See `falchion-re/vendor/asus/ARTIFACTS.md` and the authoritative findings. Never
run the packaged updater during preservation.

### 2.3 Plan hardware readback and recovery

The SONiX family advertises SWD, but probe compatibility, pad locations, target
support, readout protection, and safe connection procedure are not established.
Do not assume a generic ST-Link/OpenOCD configuration can read or restore this
MCU. U5 may be approachable with a suitable 3.3 V SPI programmer, but it must not
be powered or driven against the board without a verified isolation plan.

Acquiring a probe is not itself a recovery path. Recovery is established only
after a non-destructive read, repeated identical dumps, understood writable
regions, and a tested restore method on an acceptable setup.

---

## Phase 3 — Protocol reverse engineering

Passive capture and offline decoding do not write the keyboard. Replaying packets,
changing Armoury Crate settings, and sending raw reports do write live or persistent
configuration and are outside the preservation-safe phase. Earlier experiments are
documented in `falchion-re/notes/protocol.md`; do not repeat them by default.

### 3.1 Set up capture on the Armoury Crate side

**Chosen path: capture on a separate Windows PC with USBPcap + Wireshark.**
Armoury Crate is Windows-only, so we run it on the Windows machine, capture the USB
traffic there, then copy the `.pcapng` files back to Linux for analysis (Phase 3.4+).

On the **Windows PC**:

1. **Install Wireshark for Windows** (https://www.wireshark.org/download.html).
   During install, **check the "Install USBPcap" box** — that's the USB capture
   driver Wireshark needs. **Reboot** afterward (USBPcap installs a kernel driver).
2. **Install Armoury Crate only on a deliberately chosen capture host.** Disable or
   decline firmware updates. Do not let it update or normalize the keyboard while
   the installed firmware is being preserved.
3. **Plug the keyboard directly into a USB port** on the Windows PC (avoid hubs — one
   less layer in the capture). Confirm Armoury Crate sees it and you can change settings.

> Alternatives, if this PC ever becomes unavailable: a Windows VM with USB passthrough
> (capture on the Linux host with usbmon), or dual-boot. Both are more setup; the
> separate-PC route above is the simplest and most reliable.

### 3.2 Capture a baseline

On the **Windows PC**, in Wireshark:

1. In the interface list, pick the **`USBPcapN`** entry for the root hub your keyboard
   is on. USBPcap captures per-root-hub, so if you have several, start capture on each
   briefly and watch which one shows `0b05:1b7e` traffic — that's the one. (Unplug/replug
   the keyboard; the enumeration burst tells you which USBPcap interface it's on.)
2. Once capturing, set the display filter to isolate the keyboard:
   ```
   usb.idVendor == 0x0b05 && usb.idProduct == 0x1b7e
   ```
   That matches from the descriptor exchange on. To follow it reliably afterward, note
   the device address Wireshark assigns and switch to:
   ```
   usb.device_address == X
   ```
3. **Capture ~30s completely idle** (don't touch Armoury Crate or the keys). Save as
   `captures/00-baseline-idle.pcapng`. This is your noise floor — polling and keepalives
   you'll subtract out when diffing real changes.

> **Transfer:** copy every `.pcapng` to this repo's `captures/` on the Linux box
> (they're git-ignored via `**/*.pcapng`). All decoding in Phase 3.4 (`tshark`) runs on
> Linux — USBPcap's captured HID payloads land in the same `usb.capdata` field, so those
> commands work unchanged.

### 3.3 Capture single-variable changes

This is the methodical part. For each change:

1. Start capture
2. In Armoury Crate, change **exactly one thing**
3. Hit apply
4. Stop capture, save as `captures/<description>.pcapng`
5. Log in `notes/findings.md` what you changed

Changes to capture, in this order:

**Key remapping (your primary goal):**
- Remap a normal key (e.g. `F1`) to `A`
- Same key to `B` (one byte should differ — this identifies the keycode field)
- Same key to `Z`
- A *different* key to `A` (identifies the key-index field)
- Attempt to remap one of the **locked Fn keys** — capture whether Armoury Crate sends anything at all, or blocks it client-side

That last one is diagnostic gold: if Armoury Crate sends *nothing* when you try, the lock is pure UI. If it sends a packet and the keyboard ignores/reverts it, the lock is in firmware.

**Other settings (capture these too, you'll want them in your tool):**
- Actuation point: set to min, then max, then a middle value
- Rapid trigger: on/off, sensitivity min/max
- Per-key actuation if supported
- Profile switching
- Any lighting (even if you don't care, it helps map the command byte space)

### 3.4 Decode the packets

Export each capture's HID output reports:

```bash
tshark -r captures/remap-f1-to-a.pcapng -Y "usbhid" -T fields -e usb.capdata > notes/remap-f1-a.hex
```

Then diff systematically:

```bash
diff <(xxd -r -p notes/remap-f1-a.hex | xxd) <(xxd -r -p notes/remap-f1-b.hex | xxd)
```

Typical structure you're looking for (64-byte reports are common):

```
[0]     Report ID
[1]     Command / opcode      <- differs between "remap" vs "set actuation"
[2]     Sub-command or index
[3..]   Payload               <- key index, keycode, values
[n-2:]  Checksum (maybe)
```

Build up a table in `notes/protocol.md` as you identify fields. Watch for:
- A **checksum/CRC** at the end; test candidate algorithms offline against multiple
  captured packets rather than probing the keyboard
- A **"commit"/"save to EEPROM"** command sent after config changes
- Sequence numbers or handshake/init packets sent at app startup

### 3.5 Replay and verify — deferred write phase

This section describes the historical method, not an approved current action.
Any HID write can change device state; an undocumented packet may do more than its
observed example. Do not run a replay until preservation/recovery gates and a
specific packet-level test plan are approved.

The historical write tool is retained as `falchion-re/tools/send.ps1`, clearly
quarantined in its README and help text. A future approved replay plan must specify
the exact report bytes, expected effect, restoration method, and stop conditions.

### 3.6 Historical key-lock test

Earlier work recorded an echoed-but-ignored reserved-key write and a successful
ordinary Fn-layer write. The raw PCAP is missing, so preserve the result as a
historical hardware observation. Repeating the test is a device-write experiment,
not a read-only diagnostic.

Future confirmation should preferably come from recovering the original PCAPs or
locating the filtering logic offline in Candidate B. A new hardware write test is
not required merely to continue static analysis.

---

## Phase 4 — Offline firmware reverse engineering

Offline analysis has started; device modification has not. Ghidra 12.1.2 and JDK
21 are installed, and the prepared project is documented in
`falchion-re/ghidra/README.md`.

### Current image map

- primary bootloader code after the first container page: file `0x01000`, runtime
  base `0x00000000`;
- application candidate A: file `0x11000`, vector at its start, reset
  `0x000014a9`;
- application candidate B: file `0x21000`, valid Thumb code and keyboard/USB data,
  provisional base zero and no verified entry vector;
- RAM image: file `0x74000`, runtime base `0x18038000`, reset `0x180381c1`.

The firmware uses SONiX `0x600xxxxx` flash/XIP references and memory-remapping
features. Generic STM32 base addresses, targets, flash algorithms, and OpenOCD
commands are invalid for this device and have been removed from this guide.

### Safe offline goals

1. Map the bootloader's container validation and update-region selection.
2. Resolve Candidate B's load/call path and integrity calculation.
3. Locate the vendor-HID configuration dispatcher and the recorded `51 21`
   handling path.
4. Identify the reserved-Fn filtering logic and distinguish code from embedded
   tables/data.
5. Produce candidate patches only as separate offline artifacts with exact source
   offsets, original bytes, and recalculated integrity metadata.

### Flashing remains blocked

Do not create or run a flashing command yet. Before any device modification, all
of the following must be true:

- exact installed firmware or equivalent recoverable state is preserved;
- every relevant integrity field is understood;
- updater erase/program regions and downgrade behavior are known;
- a bootloader-independent recovery method is demonstrated;
- the user explicitly approves the exact write operation and target.

The ASUS 1.00.58 image is reference/recovery material, not proof that recovery
works. `Fn + Caps` resets settings only.

---

## Phase 5 — Build the cross-platform tool

Once the protocol is understood, this is straightforward engineering.

### Suggested stack

- **Rust + `hidapi` crate** for the core library — cross-platform (Linux/Mac/Windows) out of the box
- **CLI first** (`falchionctl set-key F1 A`, `falchionctl rapid-trigger on --sensitivity 0.3`) — fastest path to actually using it
- **GUI later** via Tauri if you want it, reusing the same Rust core
- Config file format: TOML, so layouts are version-controllable

### Structure

```
tool/
  falchion-proto/     # protocol encoding/decoding, no I/O — unit testable
  falchion-hid/       # transport layer over hidapi
  falchion-cli/       # binary
  falchion-gui/       # optional, later
```

Keeping the protocol layer I/O-free means you can unit test packet construction against your captured `.pcapng` bytes without hardware attached.

### Ship it

Publish the repo and the protocol documentation. Every other Falchion Ace HFX owner who dislikes Armoury Crate — and there are certainly some — benefits, and you'll get bug reports from people with hardware variants you don't have.

---

## Quick reference — decision tree

```
Identify MCU + normal-mode USB interfaces
  │
  ├─ Preserve exact installed state if a safe read path is proven
  │      └─ no proven path yet; official 1.00.58 image is not an exact backup
  │
  ├─ Preserve passive Armoury Crate captures (raw PCAPs currently missing)
  ├─ Decode packet structure offline
  ├─ Keep report replay behind a separate write-test approval
  │
  └─ Analyze official firmware offline in Ghidra
         ├─ resolve integrity + load paths
         ├─ locate reserved-Fn filtering
         └─ do not flash until exact backup and recovery are proven
```

---

## Notes template

Keep `notes/findings.md` structured like this:

```markdown
## Hardware
- MCU:
- Flash size:
- SWD pads located: yes/no, where:
- HE sensing IC(s):

## USB
- Vendor HID interface: hidrawN, usage page 0x____
- Report size: __ bytes
- DFU available: yes/no

## Protocol
| Opcode | Meaning | Payload layout | Verified? |
|--------|---------|----------------|-----------|
| 0x__   |         |                |           |

## Open questions
-
```

---

## Realistic expectations

- **Phase 1–3 is a weekend or two** of methodical work if the protocol is simple, longer if there's a checksum or handshake to figure out.
- **Phase 4 is a different scale entirely** — ARM firmware RE is genuinely hard, and could be weeks. Given your low-level background it's tractable, but don't start it casually.
- **Good odds you never need Phase 4.** Manufacturer key-remap restrictions are frequently UI-side, because it's cheaper to enforce in an app than in firmware.
