# 04 — Loop manager & MIDI import/export robustness (`midi-controller-audit-i4wm2p`)

**Date:** 2026-07-09 · **Commits:** 1 · **Session:** `01Lyp2y6…`

One commit (`a70e1f7`) clearing the loop-manager and MIDI-conversion findings, plus
the command-byte move that matches firmware §04 #24.

---

## `a70e1f7` — Clear-All-Loops, MIDI div0, loop import, robustness

### loop_manager.py
- **#2 — "Clear All Loops" always reported failure.** It referenced non-existent
  attributes (`main_loop_btns`/`overdub_btns`), so the success path raised
  `AttributeError` *after* the loops were in fact cleared. Use the real names
  (`main_assign_btns`/`overdub_assign_btns`) and reset each button to its empty
  state.
- **#14 — divide-by-zero on MIDI export/import** when `bpm` or `TPQN` is 0. Guarded
  in `create_midi_track`, `ticks_to_ms`/`ms_to_ticks`, `calculate_loop_timing`, and
  the imported tempo meta.
- **#28 — loops 5-8 unreachable.** The single-`.loop` picker capped at 1-4 and MIDI
  import used `tracks[:4]`. Both now use `NUM_LOOPS` (8). (Companion to §01 H3.)
- **#13 — truncated SAVE_START written as "Saved".** A truncated `SAVE_START` left
  `expected_packets`/`total_size` at 0, defeating the completeness check. Flag the
  transfer invalid and fail it at `SAVE_END`.

### keyboard_comm.py
- **#11 — infinite settings-reload spin.** `reload_settings()`'s `0xFFFF` query loop
  could spin forever on a malformed/empty response (no progress, no terminator).
  Break on no-progress with an iteration backstop; added the missing `logging`
  import.
- **#24 — Gaming SET_MODE `0xCE → 0xBC`** to match firmware (0xCE collided with the
  arp `GET_NOTES_CHUNK` handler, so gaming-mode toggle from the GUI was a no-op).
  Pairs with firmware §04 #24.

### arpeggiator.py
- **#8 — correlate the HID reply to the sent command** (the protocol echoes it at
  `response[3]`) so a stale/out-of-order reply isn't applied as this command's
  data. Same class as §02/§03.

---

### Why this branch matters
Two user-facing embarrassments hide here: "Clear All Loops" that *worked* but always
said it failed, and loops 5-8 that couldn't be saved to or imported from a file at
all. The div0 guards make MIDI import/export safe against a 0-tempo file, and the
`0xCE → 0xBC` move restores a completely dead feature (gaming-mode toggle).
