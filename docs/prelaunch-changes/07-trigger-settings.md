# 07 — Trigger Settings tab (`midi-controller-audit-xps8uj`)

**Date:** 2026-07-10 · **Commits:** 1 · **Session:** `01BH8aNt…`

The newest GUI branch (tip `9330976`). A focused pass on the Trigger Settings tab
and the surfaces it shares state with (Quick-Actuation in the keymap editor, Matrix
Test, the Velocity tab).

---

## `9330976` — Fix RT-on-MIDI, actuation scale, reset clobber, save UX

- **Rapid Trigger on MIDI keys.** The firmware never runs per-key RT on MIDI note
  keys, so the GUI now **disables the RT controls** and shows a notice when a MIDI
  note key is selected, and skips setting the inert RT flag on MIDI keys during
  multi-select edits. (Prevents the user "enabling" a feature that does nothing.)
- **Actuation scale mismatch.** Quick-Actuation (keymap editor) and Matrix Test used
  a **0-100** slider labelled 0.025 mm/unit (max 2.5 mm, and 80 mislabelled as
  2.0 mm), while Trigger Settings and the firmware use **0-255 = 0-4.0 mm**. Unified
  all of them to **0-255 with `value*4/255` mm** and a 127 (2.0 mm) default, so the
  same value reads the same everywhere and the full actuation range is reachable.
- **Reset All to Default no longer clobbers velocity.** It no longer wipes per-key
  velocity curves (owned by the Velocity tab) or the per-key-velocity flag; it writes
  the **preserved** values per key instead of the blanket firmware reset that cleared
  them. Dialog text updated to describe what it actually resets.
- **Bulk writes no longer freeze the UI.** Layer-wide apply, disable-per-key, and
  reset now write through a **batched writer with a modal progress dialog** and
  `processEvents` (up to 840 keys) instead of a synchronous blocking loop.
- **One Save covers everything.** The main Save now also persists pending **SOCD /
  Null Bind** changes; null-bind edits enable it; switching away from the tab prompts
  to save unsaved trigger/SOCD changes.
- **Honest labels.** Default value labels now match the real defaults (0.09 mm /
  1.99 mm) instead of hardcoded 0.10/2.00 placeholders; stale 0-100 range docstrings
  in `keyboard_comm` corrected to 0-255; `rapidfire_velocity_mod` documented as
  currently inert in firmware.

---

### Why this branch matters
The actuation **scale mismatch** is the subtle one: the same physical setting read
as a different number (and a different millimetre label) depending on which tab you
opened it in, and two of the surfaces couldn't even reach the top ~1.5 mm of travel.
Unifying every surface on the firmware's 0-255 / 0-4 mm contract means a value means
one thing everywhere. The rest is UX honesty — don't offer RT on keys that ignore
it, don't let a "reset" wipe a tab it doesn't own, and don't freeze on a bulk write.
