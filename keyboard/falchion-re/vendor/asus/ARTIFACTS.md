# Preserved ASUS artifacts

These files were copied byte-for-byte from the original ASUS package sources on
2026-08-29. No packaged executable was run, and the keyboard was not accessed
during the copy or verification.

| Preserved path | Size | SHA-256 | Meaning |
|---|---:|---|---|
| `original/ROG_FALCHION_ACE_HFX.zip` | 238,446,426 bytes | `a3e895dd4389e6725b15b0c0af6d6644a470a8359c4086a206490b74e9e9d7b9` | Complete official ASUS Armoury Crate Gear 1.0.1.15 distribution ZIP |
| `../../dumps/vendor/M605_V01_00_58.bin` | 507,904 bytes | `6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d` | ASUS-supplied combined firmware image, version 1.00.58 |

Original source paths:

- `/home/dereck/Downloads/ROG_FALCHION_ACE_HFX.zip`
- `/home/dereck/Downloads/ROG_FALCHION_ACE_HFX/Firmware/Bin/Firmware/7038/FW/M605_V01_00_58.bin`

The BIN is a vendor recovery/reference image. It is **not** a readback of this
keyboard and is one version older than the installed USB-reported version 1.59.
Do not flash it during preservation work.

The ZIP is intentionally ignored by the nested `.gitignore` because it exceeds
GitHub's normal per-file size limit. It remains locally preserved in this working
tree; its manifest and checksum remain trackable. Use Git LFS or external archival
storage deliberately if the full ZIP must be replicated through Git hosting.
