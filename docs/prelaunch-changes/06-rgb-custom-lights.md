# 06 — RGB configurator + Custom Lights (`midi-controller-prelaunch-audit-zpmsns`)

**Date:** 2026-07-10 · **Commits:** 2 · **Session:** `01DdLM95…`

The GUI half of the firmware's LED/animation branch (`vial-gui-custom` §08).
Fixes the RGB configurator's slot routing and read-back, and adds the
edit-the-slot-you-see live preview.

---

## `e61c5ee` — RGB configurator fixes: slot routing, effect_sat, layer flag, debounce

- **Slot routing.** Route custom-light live edits to the **edited tab's slot**
  instead of the device's currently-rendering slot — editing one slot no longer
  clobbers another.
- **`effect_sat` round-trip.** Return all 16 custom-anim payload bytes
  (`data[3:19]`) so `effect_sat` round-trips on load/save instead of always
  resetting to 255.
- **Per-layer RGB enable flag.** Read it from `status[0]` rather than the
  truthiness of the whole status buffer (the checkbox no longer always shows ON).
- **Active slot read.** Read the active slot from `status[1]` and disable the bogus
  randomize read that drove spurious color changes while the RGB tab was open.
- **Debounce.** Speed/brightness sliders (tracking off) to avoid a per-tick HID
  write storm during drags.

## `abc5be1` — Custom Lights: preview slot on tab select + throttle sliders

- **Live preview.** Selecting a Custom Lights tab tells the device to live-preview
  that slot (new `activate_custom_slot_preview` → HID **`0xED`**, non-persistent —
  the firmware side of this is §08 `3a984b1`), so the slot you edit is the one shown
  on the keyboard.
- **Throttle instead of emit-on-release.** Replace the "emit only on release" slider
  debounce with a shared throttle (`_connect_throttled`): speed/brightness sliders
  send at most ~1 HID write/second while dragging **and** always send the final value
  on release — live feedback without a per-tick write storm.

---

### Why this branch matters
The RGB tab had a "which slot am I even editing?" problem: live edits went to the
device's rendering slot, the enable checkbox was always on, and `effect_sat` reset
on every load. This branch makes the tab **address the slot it's showing**, read
back what it wrote, and preview it on the hardware — closing the same edit-loop gap
the firmware's `0xED` preview opens from the other side.
