# 05 — Slot-load clobber, settings parity, editor I/O (`midi-controller-audit-hbwmw6`)

**Date:** 2026-07-09 · **Commits:** 1 · **Session:** `01R1JtUC…`

One commit (`3b5df13`) — the GUI half of the settings round-trip fixed on the
firmware in §05 (`vial-gui-custom`). The headline bug: **loading a slot silently
wiped device config.**

---

## `3b5df13` — Slot-load clobber, settings parity, editor I/O robustness

### Settings parity (matrix_test.py / protocol/keyboard_comm.py)
- **P0 — the load-clobber.** `set_combo_by_data` now **blocks signals** while
  applying a loaded config. Many combos fire a live `send_param_update` on index
  change, so loading a slot whose value the GET couldn't report (defaulting to 0/2)
  fired a PARAM write that **overwrote the value the device had just loaded** — a GUI
  "Load Slot" silently wiped the device's sustain / chord-display config.
- **GET parse alignment.** Read `chord_display_mode` + base/keysplit/triplesplit
  sustain from the basic packet's new bytes 22-25 (the firmware carries them there
  now — firmware §05), and drop the out-of-range `data[26]` chord read from the
  advanced packet that always pinned it to the default.

### Editor I/O robustness
- **delay_tab:** `_on_save_as_new_slot` checks `save_to_eeprom()` and warns / does
  not switch tabs on failure (matched its sibling handler).
- **dks_settings:** `_send_to_keyboard` returns success; drags debounced via a 75 ms
  single-shot timer; a persistent non-modal status label surfaces write failures
  once instead of silently reporting success.
- **trigger_settings:** `on_copy_to_all_layers` reports failure instead of
  unconditional success; adc/distance pollers stop their timer on unplug like
  `matrix_poller`; save/copy/reset/nullbind buttons disabled during transfers.
- **velocity_tab / delay_tab / dks_settings / trigger_settings:** busy/disable guards
  so rapid double-clicks and slider drags don't overlap transfers.
- **rgb_configurator:** func-LED SET/SAVE now check the device ack.

### Docs
Reconciled the stale EEPROM map in `CLAUDE.md` with the firmware map (factory-seq
@37200, chains @39108, `ARP_MASTER_RG`, `USEQ_MODS`; custom names now 56000-60273
incl. layer names).

---

### Why this branch matters
"Load Slot silently wipes the device" is the same shape as §02's "read that
writes", but from the opposite direction: here the *load* triggers live-edit
signals that overwrite the load. The fix — **block Qt signals during a
programmatic load** — is now the standard for every combo-driven config apply. The
editor-I/O guards close the "showed Saved but the write failed" gap across every
tab, matching the firmware's settings-parity change so a slot round-trips exactly.
