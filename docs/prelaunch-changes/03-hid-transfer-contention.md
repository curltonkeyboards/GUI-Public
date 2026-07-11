# 03 — HID resend desync + poller/transfer contention (`orthomidi5x14-audit-report-dk35jy`)

**Dates:** 2026-07-07 → 07-08 · **Commits:** 2 · **Session:** `01HKFSGJ…`

Two commits about **who is allowed to read the HID handle, and when** — the
GUI-side companion to the firmware's loop-pool/transfer hardening.

---

## `77a79bb` — HID resend desync, truncated saves, transfer wedge, silent save failure (H4, M1, M4, M16)

- **H4 — resend desync.** `hid_send` re-wrote the command on every 500 ms read
  timeout. Commands that do slow synchronous EEPROM work reply *after* that window,
  so the re-write made the firmware execute a **second** time and queue a duplicate
  response, permanently offsetting the request/response stream (the GUI then showed,
  and could save back, garbage). Send the command exactly once; only extend the read
  window; never re-send on a read timeout.
- **M1 — truncated saves.** `handle_save_end` wrote the `.loop`/`.midi` file whenever
  `status == 0` with no completeness check, so a dropped/stolen packet produced a
  silently truncated file with a "Saved" message. Verify received packets/bytes
  match the expected totals before writing; otherwise warn and don't save. (Also
  catches the truncation caused by the H3 cross-thread contention below.)
- **M4 — transfer wedge.** A loop transfer had no watchdog, so an unplug or lost
  final packet left `current_transfer` active forever and every later transfer was
  rejected as "already in progress" until restart. Arm a 20 s watchdog on transfer
  start (cleared on completion) that force-resets and warns.
- **M16 — silent trigger-save failure.** Trigger-settings Save ignored
  `set_per_key_actuation`'s return value and cleared all pending edits
  unconditionally, so a busy/unplugged device dropped edits while the GUI showed
  "saved". Keep the failed keys pending and warn.

## `22a6e37` — H3: pause live pollers during loop transfers (exclusive HID access)

During a loop save/load a background **listener thread** continuously reads the
device handle, while the matrix/velocity **live pollers** read the *same* raw
handle from the Qt main thread via `hid_send` with no correlation. Switching to
Matrix Test / Velocity mid-transfer let those pollers **steal the transfer's
packets** (→ truncated file) and read stolen transfer packets as garbage
telemetry.

Added a shared util flag (`set_hid_transfer_active` / `is_hid_transfer_active`):
the loop manager sets it around the listener's lifetime, and the three
`matrix_test` pollers + the velocity poll skip their tick while it's set (timers
keep running, so polling resumes automatically when the transfer finishes). Both
run on the Qt main thread, so the flag is race-free relative to the pollers, and
the listener thread becomes the sole reader during a transfer.

---

### Why this branch matters
With no request/response correlation, **two readers of one handle is
data-corruption by construction**. This branch makes bulk transfers *exclusive*
(pause the pollers), stops the timeout-resend that duplicated slow commands, and
refuses to write a file it can't prove is complete — turning "silently truncated,
labelled Saved" into an honest warning.
