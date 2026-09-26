# Lesson 12 — The race condition and the backup

> **In one sentence:** The bootloader's READ happens *later* than the command that asks for it, so the investigation had to prove, step by step, a way of asking that can never return a half-finished answer, and only then read the whole application region three times over.
>
> **You will learn:**
> - what a race condition is, and why this bootloader has one (the RAM blocks T, S and W, the `0x30` buffer cap, and SysTick-gated dispatch)
> - the three wrong beliefs, in order: batched queries (log 84), busy-bit polling (log 85), and status-before-sample (log 86)
> - the zero-init bootstrap and the sample→status→confirm rule, with its proof
> - the leftover risks: a liveness bug, and "nothing else may talk to hidraw"
> - how the one-block read (log 91) and the three-pass backup (log 92) were done, and what the backup does **not** cover
>
> **Time:** ~75 minutes · **Prerequisites:** Lesson 11 (the bootloader door), Lesson 7 (ARM crash course)

---

## 1. The story (kid version)

You're waiting for a letter from your grandma. Every few minutes you run out and look in the mailbox.

One afternoon the carrier is still standing at the mailbox, halfway through putting in a stack of pages. You open the lid, grab what's inside, and run back in. You have **the first half of grandma's letter and the second half of yesterday's newspaper**. You didn't notice, because it's "different from what was there this morning". That's a **race condition**: the answer depends on who gets there first, you or the carrier.

How do you fix it without a clock and without asking the carrier anything clever? You use a rule:

1. Look in the mailbox and remember what you saw.
2. **Then** look down the street. Is the carrier's van gone?
3. If the van is gone *and* what you saw is different from this morning's stuff, go back and take out what's in the mailbox **now**. That second look is the real letter.

Why does this work? If the van was gone *after* your first look and something had changed, the carrier must have come and **finished** before you looked down the street. So the mailbox is complete now and will stay that way.

One more thing: you can only use the rule if you know what "this morning's stuff" was. On a brand-new mailbox, you know it's **empty**. That's your starting point.

### How the analogy maps to the real thing

| In the story | In the keyboard |
|---|---|
| The mailbox | The 48-byte READ response buffer at `S+4` in bootloader RAM |
| The carrier putting pages in | `FUN_00003b64` copying flash into `S+4` |
| The carrier starts on their own schedule | The READ only starts on a SysTick tick, not when you ask |
| The van still in the street | Status flags bit 1 (READ busy) set |
| Grabbing what's in the box | An `0xaa` query ("give me the buffer") |
| Looking down the street | A `0x8f` status query |
| Half letter, half newspaper | 24 new bytes followed by 24 old bytes (log 86) |
| The empty new mailbox | The zero-initialised buffer: 48 zero bytes after startup |
| A neighbour who also sends the carrier | Another program talking to the same hidraw node |

---

## 2. Why we needed this

By log 83 the investigation had a backup tool, `tool/backup_firmware.py`. It knew the READ framing from Lesson 11: set length, set address, execute READ, then ask for the buffer. On paper the full dump is simple (log 83):

```text
region 0x10000..0x7c000  chunks=9216 chunk_max=0x30  bytes=0x6c000
```

`0x6c000` bytes is 442,368 bytes. Divided into `0x30` = 48-byte chunks, that's exactly 9,216 chunks.

But one question kept coming back in each correction pass: **when you ask for the buffer, how do you know it holds the chunk you just requested, complete, and not the previous one or a mixture?**

This had to be answered *before* any live read, for two reasons:

- A wrong backup is worse than no backup. You'd trust it.
- "Three identical passes" don't save you from a systematic error. If the tool always returns the previous chunk, all three passes are wrong in exactly the same way. Log 84 names that risk: "three identical-but-wrong passes would have been accepted."

The alternative would have been to add a fixed delay ("wait 10 ms after each execute"). Log 85 rejected that: "A fixed delay is not recommended and is not used: the tick period is not a static constant in this image."

---

## 3. The real thing

### 3.1 What a race condition is, precisely

A [race condition](00-glossary.md#race-condition) is a bug whose outcome depends on which of two things happens first. Here the two things are:

- **the host** (Linux, our tool) sending the `0xaa` "give me the buffer" query, and
- **the bootloader's main loop** copying flash into that buffer.

These run in different "execution contexts". An [interrupt](00-glossary.md#interrupt-irq) is a hardware signal that makes the CPU pause what it's doing and run a handler. USB reports are handled when a USB interrupt arrives. The READ runs in the main loop. The main loop and the interrupt handler share memory but not a schedule.

### 3.2 The memory layout: T, S and W

Log 85 resolved the bootloader's protocol state by the **values in the literal pools**, not by guessing offsets. There are three RAM objects:

| Base | Contents |
|---|---|
| `T = 0x18011a8c` | `T+0`: 32-bit target address (set by `0x20`). `T+4..T+0x1003`: a `0x1000`-byte buffer used by programming. |
| `S = 0x18012a8c` (exactly `T + 0x1000`) | `S+4..S+0x33`: the **48-byte READ response buffer**. `S+0x34`: pending command. `S+0x35`: error. `S+0x36`: 16-bit length. `S+0x38`: flags. `S+0x39`: a scratch byte nothing reads. |
| `W = 0x18010bd4` | `W+0`: the SysTick tick flag. `W+4`: the "flash work requested" flag. |

The flags byte `S+0x38` holds: bit 0 = erase/program busy, bit 1 = **READ busy**, bit 7 = unlocked.

Log 85 cross-checked the layout three ways instead of assuming it. One example: the READ function takes its address from `*(u32 *)(S - 0x1000)`, which is `T+0`. That only makes sense if `S == T + 0x1000`.

As a picture:

```text
            T = 0x18011a8c                         S = 0x18012a8c
            |                                      |
  RAM:  ... [addr][ 0x1000-byte program buffer ... ][....][ 48-byte READ buffer ][34][35][36 37][38][39] ...
            T+0   T+4                     T+0x1003  S+0   S+4               S+0x33 pend err  len   flags
                                                ^ = S+3
```

#### Why the READ cap is `0x30`

`S+4 + 0x30 = S+0x34`. The buffer ends exactly where the pending byte begins. A READ longer than 48 bytes would overwrite the bootloader's own bookkeeping. **So the cap is the buffer size, not an arbitrary limit** (log 85).

#### The host can't write into the buffer

The only host command that writes into this area is the program-data loader, and its last reachable byte is `T+0x1003 == S+3`, one byte short of the buffer (log 85). So everything that appears at `S+4` was put there by the bootloader's READ. That fact is **F1** in the proof below.

### 3.3 SysTick-gated dispatch: the READ happens later

[SysTick](00-glossary.md#systick) is the ARM core's built-in timer. It fires an interrupt at a steady rate. Here is how an accepted execute turns into a real READ, using listings saved in log 85 section G.

**Step 1: the execute parser only raises a flag.** You saw this in Lesson 11:

```text
00003972  strb.w r1,[r0,#0x34]       ; S+0x34 = pending opcode
0000397c  movs r0,#0x1
0000397e  ldr r1,[0x00003a78]        ; r1 = W
00003980  str r0,[r1,#0x4]           ; W+4 = 1  ("flash work requested")
```

No flash access. Log 85's first fact: the parser "sets S+0x34 and W+4, and never W+0".

**Step 2: the SysTick handler is four instructions long.**

```text
000048d0  movs r0,#0x1
000048d2  ldr r1,[0x000048d8]        ; r1 = W = 0x18010bd4
000048d4  str r0,[r1,#0x0]           ; W+0 = 1  ("a tick happened")
000048d6  bx lr
000048d8  .word 0x18010bd4
```

That's all it does: it sets `W+0`. Log 85 checked every word in the image equal to `0x18010bd4`. This handler is **the only writer of `W+0`**.

**Step 3: the service loop runs its body only when `W+0` is set.**

```text
00003a7c  push {r4,lr}
00003a7e  b 0x00003aa8               ; jump straight to the W+0 test
00003a80  ldr r0,[0x00003ab4]        ; r0 = W
00003a82  ldr r0,[r0,#0x4]           ; W+4 set?
00003a84  cbz r0,0x00003a94          ;   no -> skip
00003a86  cpsid i                    ; interrupts off
00003a88  movs r0,#0x0
00003a8a  ldr r1,[0x00003ab4]
00003a8c  str r0,[r1,#0x4]           ; W+4 = 0
00003a8e  cpsie i                    ; interrupts on
00003a90  bl 0x00002db8              ; do the flash work
...
00003aa8  ldr r0,[0x00003ab4]
00003aaa  ldr r0,[r0,#0x0]           ; W+0 (the tick flag)
00003aac  cmp r0,#0x0
00003aae  bne 0x00003a80             ; only then run the body
00003ab0  pop {r4,pc}
```

The very first thing it does (`b 0x00003aa8`) is test the tick flag. So a set `W+4` on its own does nothing. The work waits for the next tick.

**Step 4: the dispatcher sets busy, reads, clears busy, clears pending.** This is the READ branch of `FUN_00002db8`:

```text
00002dfc  ldr r0,[0x00002e60]        ; r0 = S
00002dfe  ldrb.w r0,[r0,#0x38]
00002e02  bic r0,r0,#0x2
00002e06  adds r0,r0,#0x2
00002e08  ldr r1,[0x00002e60]
00002e0a  strb.w r0,[r1,#0x38]       ; flags bit 1 SET   (READ busy)
00002e0e  bl 0x00003b64              ; the READ: flash -> S+4
00002e12  ldr r0,[0x00002e60]
00002e14  ldrb.w r0,[r0,#0x38]
00002e18  bic r1,r0,#0x2
00002e1c  ldr r0,[0x00002e60]
00002e1e  strb.w r1,[r0,#0x38]       ; flags bit 1 CLEAR
00002e22  movs r1,#0x0
00002e24  strb.w r1,[r0,#0x34]       ; pending = 0
```

`bic r0,r0,#0x2` means "clear bit 1"; `adds r0,r0,#0x2` then sets it. The pair means "force bit 1 on". The two important addresses are `0x00002e0a` (busy set) and `0x00002e1e` (busy clear). **Every write to the buffer happens between them.** That's **F2** in the proof.

**Conclusion (log 85, as corrected by log 86):** an accepted execute waits for the next SysTick tick before the READ starts. The race is **proven possible**.

What the static analysis can and can't tell us about timing:

- `SYST_RVR` (the SysTick reload register) is the constant `0x278d0 - 1 = 161999`, so one tick is 162,000 core clock cycles.
- The **wall-clock** time of a tick is *not* statically determined, because `FUN_00004910` selects the core clock at runtime. The duration of one 48-byte flash transfer isn't recovered either.
- So **no claim is made about how often the race is hit**, only that it can happen.

### 3.4 Three wrong beliefs, in order

This is the heart of the lesson. Each wrong belief was more subtle than the one before.

#### Wrong belief 1 (log 84): "You can send all the requests, then read once"

The first version of the tool queued all five reports for a chunk and then did **one** `read()`. Log 84's correction audit, defect 1, marked FATAL:

> the per-chunk sequence queued all five reports and then performed a single read(), so the 0x8f status reply was consumed as if it were the 0xaa read data. Every chunk would have been wrong and no response was validated at all.

Replies come back in order. If you ask "status?" and "data?" and then read one reply, you get the **status** reply and treat it as data. The fix is in today's `query()`:

```python
def query(transport, sub, expect_code, timeout=RESP_TIMEOUT):
    """One immediate request-response exchange: send, then read its reply.

    Queries are never batched. Sending 0x8f and 0xaa back to back and then
    reading once would consume the status report as if it were read data.
    """
```

And `read_response()` checks that the reply code is the one expected (`0x0f` or `0x2a`) and that the reply is exactly 64 bytes, and raises otherwise.

- **Lesson:** *one question, one answer, checked.*

Log 84 also noted the race for the first time, as **unresolved**: "Nothing recovered proves the service loop has run before the host's first 0x8f."

#### Wrong belief 2 (log 85): "Wait until the busy bit clears, then the data is ready"

Log 84's tool polled status and waited for bit 1 (READ busy) to be clear. That sounds sensible. Log 85 proved it can't work, for a structural reason that needs no timing at all:

> a clear `state+0x38` bit 1 is also exactly what "not started yet" looks like, so **polling bit 1 cannot sequence a READ**.

Think about the timeline. Before the tick, the READ hasn't started: bit 1 is **clear**. During the READ: bit 1 is **set**. After: bit 1 is **clear** again. If you look and see "clear", you can't tell "before" from "after". And the `0x8f` responder never advances the service loop, so asking doesn't make the READ happen sooner. The following `0xaa` can therefore return the **previous** chunk's buffer.

Log 85 removed `wait_read_done()`. It also searched for anything else that would say "done": a counter, an address echo, a completion byte, a sequence number. It found none. The pending byte `S+0x34` would do the job, but "`S+0x34` is exposed by no query."

Log 85 also went too far in its language. It said the race "is the default outcome", that the busy window is "orders of magnitude" shorter than a host round trip, that it lasts "microseconds", and that every chunk after the first "would have" been stale. **Log 86 withdrew all of those**, because log 85 itself recorded that neither the tick's wall-clock period nor the transfer duration