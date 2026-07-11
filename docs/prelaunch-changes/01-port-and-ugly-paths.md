# 01 — Port to current firmware + ugly-path hardening (`pre-launch-audit-306ft9`)

**Date:** 2026-07-05 · **Commits:** 3 · **Session:** `01FMVp3g…`

Brings the GUI back in sync with the firmware's protocol (command bytes, keycodes,
IDs had drifted) and hardens the disconnect / bad-input / double-submit paths.

---

## `21ebe97` — Port GUI to current firmware (audit H1, H2, H6, M2)

- **H1 — HID command collisions.** Gaming-curve commands `0xD6/0xD7` and the
  active-layer / firmware-version queries all sent the same header on `0xD6/0xD7`
  as the **MIDI Delay slot** commands, so the gaming block shadowed the others —
  killing the Delay tab load/save, the About-box firmware version, and the
  active-layer readout. Moved gaming curves to `0x90/0x91` and the layer/version
  queries to `0x92/0x93`; Delay keeps `0xD6/0xD7/0xD8`.
- **H2/H6 — arp preset renumber.** Match current firmware: keycode base
  `0xED40 → 0xF200`, factory count `88 → 159`, user arp preset IDs `48-87 →
  119-158`, factory-preset save guard `48 → 119`. Ported the factory rhythm-arp
  label generator so the 200 factory patterns show real names.
- **Delay persistence.** The Delay tab now calls `save_to_eeprom()` after
  `set_slot()` so user delay slots survive a power cycle.
- **M2 — chunk overrun.** Read/write at most 8 notes per HID chunk (a 9-note chunk
  ran past the 32-byte packet — mirrors firmware §01 M2).

## `47ee18a` — Loop manager: all 8 loops + validate loop numbers (audit H3, H4)

- **H3** — Save All Loops and the file import/export loops iterate all 8 firmware
  slots (`NUM_LOOPS`) instead of stopping at 4, so loops 5-8 are no longer
  silently dropped.
- **H4** — loop numbers read from a `.loop` file are validated against
  `1..NUM_LOOPS` before use as a slot selector (both the parser and
  `load_loop_data_to_device`), so a hand-edited/corrupt file can't target an
  invalid slot.

## `cc7a404` — Harden ugly paths (audit M3-M11)

Everything that happens when the user does something unexpected:
- **M3/M9** — File → Load layout guards for no connected keyboard and catches
  malformed/wrong-version `.vil` files with a message instead of crashing.
- **M4** — trigger settings track whether the per-key device read succeeded; if it
  failed (values are display defaults), Save is **refused** and offers a reload, so
  defaults can't overwrite the real config.
- **M5** — loop save/load buttons are non-re-entrant; starting a transfer while one
  is active warns instead of clobbering the transfer state.
- **M6** — unplugging mid-unlock rejects the unlock dialog so the modal wait loop
  resolves instead of soft-locking the app.
- **M7** — a device-open failure resets to no-device and reports instead of leaving
  a frozen/stale UI.
- **M8** — the autorefresh device-polling `QThread` gets a stop flag and is
  stopped + joined on window close (was a bare `while True`).
- **M10** — `SEQ_PRESET_0-19` relabeled as **drum-machine slots** (they open drum
  slots, not sequencer presets).
- **M11** — add the missing Virtual Instrument "Keyboard 3" (firmware value 5) and
  raise the load clamp 4 → 5 so mode 5 isn't clobbered.

---

### Why this branch matters
The GUI and firmware had drifted apart: the same HID header meant three different
things, arp IDs were off by a full renumber, and Delay didn't persist. This branch
is the **re-sync** — after it, the two speak the same protocol again. The ugly-path
hardening is the first pass at "the app should never crash or soft-lock because the
device disappeared or the file was bad."
