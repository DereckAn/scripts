# Device readbacks

This directory is reserved for byte-exact readbacks from the owner's keyboard.
Device dumps are not interchangeable with official ASUS updater images under
`../vendor/`.

Current USB scope: application flash only, base `0x10000`, size `0x6c000`. The
bootloader region `0x00000..0x0ffff` is not readable through the recovered USB
command. Every accepted dump must come from at least three identical passes,
have a recorded SHA-256, and pass the repository's structural analyzers.

## Accepted readback — 2026-09-02

- File: `ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin`
- Logical base/range: `0x10000`, `[0x10000,0x7c000)`
- Size: 442,368 bytes (`0x6c000`)
- SHA-256: `fc6128ab089e4fd712b172c54cd88b7f28476b55bdac688134e052281ded637b`
- Acquisition: three sequential, byte-identical USB READ passes (log 92)
- Validation: both SN_FWIN record checksums, the application word-sum, and all
  12 boot-structure checks applicable to a base-`0x10000` image passed.

This is recovery material for the USB-readable and USB-writable application
range. It is not a complete 4 MiB U5 dump and does not contain the bootloader.
