# 02 — Destructive read-fallbacks, disconnect freeze, stale-packet desync (`pre-launch-audit-pcyvzi`)

**Dates:** 2026-07-05 → 07-06 · **Commits:** 2 · **Session:** `01Jrqhz1…`

The most dangerous GUI-side bug of the launch is here: a **read that silently
writes**. Plus the disconnect-freeze and stale-packet-desync classes.

---

## `3174ef0` — Destructive read-fallbacks, disconnect freeze, stale-packet (C1, H4, H5, M2)

- **C1 — reads that zero the device.** `get_thruloop_config` / `get_midi_config`
  sent a **zero-payload SET packet as a read fallback**. The firmware executed
  those as real writes, so every GUI connect **zeroed and persisted** the
  loop/advanced-MIDI config. Fixed: count the packet `usb_send` already consumed so
  collection can complete, and **fail the read** on an incomplete response instead
  of parsing partial data — never send a SET as a read.
- **H4 — disconnect freeze.** `hid_send` retried on `OSError` (device unplugged)
  with 0.5 s sleeps **on the Qt main thread**, freezing the UI ~10 s per call
  (minutes across multi-call flows). Fail fast on `OSError` instead.
- **H5 — stale bulk packets.** `get_all_per_key_actuations` returned early on a bad
  packet, leaving the rest of the bulk response in the FIFO to be parsed as the
  reply to the *next* command. Drain the remaining packets instead.
- **M2 — silent default substitution.** `get_velocity_preset` validated neither the
  command byte nor the slot and silently substituted factory defaults on a missing
  chunk 1 — so a re-save would overwrite the user's real preset with defaults. Now
  validates command + slot on both chunks and fails on a missing chunk.

## `509d9af` — Validate command byte on DKS/toggle/nullbind slot reads (v2 M1)

Same defect class as the two already fixed in `keyboard_comm.py`: a stale packet
left in the HID FIFO (e.g. from an interrupted bulk read) could be parsed as a
DKS/toggle/nullbind slot reply — the editor would display **garbage as the user's
saved config**, and a save would write that garbage back. Each single-packet read
validated only the status byte; now they also verify `response[3] == the requested
command` (the firmware echoes it for all three subsystems), rejecting stale
packets.

---

### Why this branch matters
`get_*` should never mutate the device — but two of them did, on **every connect**,
because a "read fallback" reused a SET packet. That's the worst possible GUI bug:
just opening the app quietly wiped your loop/MIDI config. This branch establishes
the two rules the rest of the audit enforces everywhere: **a read never writes**,
and **a reply is only trusted if its echoed command byte matches**.
