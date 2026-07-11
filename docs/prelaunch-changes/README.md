# Pre-launch changes — GUI (GUI-Public)

This folder documents the bug-fix and feature work done across the **most recent
branches** of `GUI-Public` (the PyQt5 desktop configurator for the orthomidi5x14
keyboard) during the pre-launch hardening push. It is the GUI-side companion to
`vial-gui-custom/docs/prelaunch-changes/` (the firmware side); the two repos were
audited in the same sessions, so findings cross-reference by session and by the
firmware's `C`/`H`/`M` finding tags.

The GUI is a thin HID client over a **custom protocol that does not correlate
responses to commands** (`hid_send` just reads the next packet). That single fact
is behind most of the bugs here: stale packets get parsed as the wrong reply,
zero-payload "read" packets get executed as writes, re-sends duplicate slow
commands, and background pollers steal a transfer's packets. The recurring fix is
to **validate the echoed command byte, count packets, and never re-send or
double-read**.

## Branches (newest → oldest)

| # | Branch | Date | Theme | Doc |
|---|--------|------|-------|-----|
| 7 | `claude/midi-controller-audit-xps8uj` | 07-10 | Trigger Settings tab: RT-on-MIDI, actuation scale, reset, save UX | [07](07-trigger-settings.md) |
| 6 | `claude/midi-controller-prelaunch-audit-zpmsns` | 07-10 | RGB configurator + Custom Lights (slot routing, preview, throttle) | [06](06-rgb-custom-lights.md) |
| 5 | `claude/midi-controller-audit-hbwmw6` | 07-09 | Slot-load clobber, settings parity, editor I/O robustness | [05](05-slot-load-settings-parity.md) |
| 4 | `claude/midi-controller-audit-i4wm2p` | 07-09 | Clear-All-Loops, MIDI div0, loops 5-8, truncated save | [04](04-loop-manager-midi.md) |
| 3 | `claude/orthomidi5x14-audit-report-dk35jy` | 07-07…08 | HID resend desync, truncated saves, poller/transfer contention | [03](03-hid-transfer-contention.md) |
| 2 | `claude/pre-launch-audit-pcyvzi` | 07-05…06 | Destructive read-fallbacks, disconnect freeze, stale-packet desync | [02](02-read-fallbacks-stale-packets.md) |
| 1 | `claude/pre-launch-audit-306ft9` | 07-05 | Port GUI to current firmware; all-8-loops; ugly-path hardening | [01](01-port-and-ugly-paths.md) |

(The doc branch `claude/gui-custom-changes-doc-wklyq0` is the 8th; it only adds
this documentation.)

## The one root cause to know: no request/response correlation

`hid_send()` writes a command and reads whatever packet comes back next. There is
no sequence number. The firmware **does** echo the command byte at `response[3]`
for most subsystems, so the durable fix pattern used throughout these branches is:

1. **Validate `response[3] == the command you sent`** (and the slot/index where
   applicable) before parsing a reply. Reject stale packets. (§01, §02, §03 H4)
2. **Never re-send on a read timeout** — slow EEPROM commands reply *after* the
   500 ms window; a re-send makes the firmware execute twice and permanently
   offsets the stream. Extend the read window instead. (§03 H4)
3. **Never use a zero-payload SET packet as a read fallback** — the firmware
   executes it as a real write, zeroing and persisting config on connect. (§02 C1)
4. **Pause background pollers during a bulk transfer** so they can't steal the
   transfer's packets. (§03 H3)
5. **Block Qt signals while loading a config** so live `send_param_update` handlers
   don't overwrite the value just loaded. (§05 P0)

## Related earlier GUI work (referenced by firmware round-1)

The firmware's round-1 branch (`vial-gui-custom` §01) pairs with GUI features that
landed on slightly earlier branches (`aftertouch-cc-multibutton`, `festive-carson`,
`loop-pedal-burst-notes`). Kept here for a complete cross-reference:

- **Aftertouch Mode/Style/Sustain combos** (`306bb72`) — three controls packing the
  0-16 `aftertouch_mode` byte; **Velocity-as-AT locked ON for Post Actuation**
  (`8a59088`).
- **Mod Press keycodes** (`306bb72`, registered in `40b0af9`) + **grouped with MIDI**
  for the actuation/deadzone sliders (`fd6e25d`).
- **Instant Start rebrand** (`a5c3886`) of the obsolete "Thruloop" combo; earlier
  **ThruLoop toggle hidden** (`126d806`).
- **Connect-time per-key read burst paced** (`a9e4d43`) — the GUI half of the
  loop-machine-gun-on-connect fix (firmware §01 C).
- **ThruLoop keycodes + banked-CC wire-order fix** (`429fc02`, `086f0f0`).
