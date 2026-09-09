# Note to paste alongside PROMPT-polling-rate-analysis.md

The capture exists. Read `captures/02-polling-rate-owner-facts.txt` FIRST — it is
the owner-provided facts file the prompt's "OWNER-PROVIDED FACTS" section refers
to, and it also pre-answers parts of STEP 0 and U8.

## Owner checklist

- **Wall-clock time of each rate change:** NOT recorded. Use traffic landmarks and
  record that as the anchor method. Note the polling rate is NOT visible as a
  packet-rate change — an idle HID keyboard emits almost nothing, so there is no
  8x staircase to find. The rate changes appear only as vendor command frames.
- **Armoury Crate version:** 6.5.7.0 (appx `B9ECED6F.ArmouryCrate`), installed
  2026-09-09, the capture day. AURA stack reinstalled the same day.
- **Firmware-update prompt:** none accepted. Keyboard firmware verified UNCHANGED
  after the AC update: `USB\VID_0B05&PID_1B7E&REV_0159` -> bcdDevice 1.59, still
  matching `dumps/device/...bcdDevice_1.59...bin` (`fc6128ab...`).
- **Accidental changes:** none reported by the owner. Only the polling rate was
  touched.
- **Did the keyboard visibly reconnect after a rate change?** Not observed /
  not noted by the owner. Treat re-enumeration-after-rate-change as a question
  for the wire, not as answered here. (A deliberate replug DID occur early in
  the capture and is a separate, expected re-enumeration: address 6 -> 7.)
- **Capture filenames:** `captures/02-polling-rate.pcap` (original, primary) and
  `captures/02-polling-rate.pcapng` (editcap format conversion).
- **Optional second lighting capture:** NO. None was taken. Skip the lighting
  branch of STEP 3 entirely and say so.

## Two deviations from the prompt's premises

1. **There is no 2000 or 4000 Hz.** Armoury Crate 6.5.7.0 exposes ONLY 1000 and
   8000 Hz for this keyboard, confirmed on a fully updated and rebooted install.
   The prompt's `1000 -> 2000 -> 4000 -> 8000` sequence was impossible. U7 is the
   clause that governs this: decode what is there, do not invent four values.
   The owner toggled 1000 <-> 8000 repeatedly instead — more times than the four
   originally planned, so every alternation in the capture is a genuine user
   action.

2. **The capture is `.pcap`, not `.pcapng`.** It was taken with `USBPcapCMD.exe`
   rather than Wireshark, because `--inject-descriptors` is a USBPcapCMD flag and
   is not exposed in the Wireshark GUI. Exact command:

       USBPcapCMD.exe -d \.\USBPcap3 -A --inject-descriptors -s 65535 \
         -b 134217728 -o captures\02-polling-rate.pcap

   `-A` with NO `--devices` address filter was deliberate: a rate change may
   re-enumerate the device onto a new address, and an address filter would have
   dropped it at exactly the wrong moment (U5).

## Head start on STEP 0 / U8, from the Windows host

Verified with TShark 4.6.8:

- `usbhid.data` carries the 64-byte vendor payload as hex. **Use this.**
- `usb.capdata`, `data.data`, `usb.data_fragment`, `usb.payload` all return EMPTY.
- The USBPcap pseudo-header is 27 bytes (0x1b); payload begins at offset 27.
- Working: `usb.device_address`, `usb.endpoint_address`, `usb.transfer_type`,
  `usb.data_len`, `frame.time_relative`, `frame.time_epoch`.

Re-verify these on your own tshark build rather than trusting them.

## Important caution

The facts file contains smoke-check observations made while confirming the
capture was usable, including a candidate byte offset and a hypothesis about its
encoding. **That hypothesis was written down BEFORE the capture as a prediction
to test.** Do not treat it as a result. Derive the decode from the wire with raw
command output per the prompt's evidence standards, and say plainly if the wire
disagrees with it.
