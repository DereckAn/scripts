# External references

Sources outside this repository that bear on the analysis, with what each one
can and cannot be used for.

## SONiX SNC7320-series product brief (series-level)

- URL: https://www.sonix.com.tw/webapi/fl218645/snc7320_brief_data_sheet_V2.3.pdf
- Added: 2026-09-04, supplied by the repository owner.
- **Not fetched by the analysis tooling.** Every log in this project asserts
  that no network access occurred, and that stays true: the URL and the summary
  below were provided by the owner. Nothing in the repository downloads it.

### What it is stated to confirm, at series level

- dual Cortex-M3 cores
- USB host and device
- GPIO
- timers and PWM
- two watchdogs
- SPI NOR interface
- a 10-bit, six-channel SAR ADC

### What it may not be used for

It is a **product brief for the SNC7320 series**, not a register map for the
SNC73270. It carries no register addresses, no bit fields and no interrupt
assignment table.

**Therefore no register identity in this repository may be assigned from it
alone.** It can raise or lower the prior on a hypothesis — for example, "two
identical magic-key-protected blocks on the reset path" is consistent with the
brief's *two watchdogs*, and a six-channel SAR ADC is consistent with a
Hall-effect front end — but a consistency is not an identification. Any claim
that a given address is a given peripheral still needs data-flow evidence from
the image, and must carry its own confidence level.

### Where it is used

- `notes/dual-core-question.md` — the dual-core participation question it raises.
- Nowhere else. No tool reads it, and no register row cites it.
