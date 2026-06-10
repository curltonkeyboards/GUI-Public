# Settings Menu (OLED) — Implementation Plan

Goal: add an on-keyboard Settings menu (new keycode `MI_SETTINGS_MENU`) that
mirrors the GUI "MIDI settings" / "ThruLoop" tabs, plus a dedicated
`MI_LOAD_MENU` keycode that only opens the Load picker and auto-exits.

All persistence already exists — we are only building the OLED UI and wiring
it to the existing globals + `save_keyboard_settings_to_slot()` /
`save_loop_settings()` / `load_keyboard_settings_from_slot()`.

## Scope / answered design questions

- **Q1 (sync_midi_mode semantics)** — option (a): the existing single
  `sync_midi_mode` bool is the "send restart messages" switch. Thruloop >
  Basic has "Send Restart Msgs" wired to it; the Loop menu has "Sync MIDI
  Mode" ALSO wired to it (same variable, same state — just two entry points,
  two different labels for the same underlying concept).
- **Q2 (ThruLoop channel / Loop messaging channel)** — consolidated.
  ONLY exposed under Thruloop > Basic > "ThruLoop Channel". Editing it
  writes `loop_messaging_channel` + calls `save_loop_settings()`. The Loop
  menu does NOT expose it.
- **Q3 (Sync Macros→Loop)** — dropped entirely. Per-macro sync is set per
  keycode from the Vial GUI (`macro_per_sync[]`), and the global master
  override (`macro_sync_to_loop`) is not useful to expose as a flat toggle
  on the OLED. Thruloop > Basic therefore has THREE items: ThruLoop Channel,
  Send Restart Msgs, Alternate Restart.

## Keycodes

Free range — `0xCA10/0xCA11` collide with `CPROG_SLOT_1/2`, and
`0xC9FE/0xC9FF` are taken by a quick-build keycode and progression octave
reset. First free slot after `CPROG_SLOT_END (0xCA23)`:

- `MI_SETTINGS_MENU = 0xCA24` — open full settings tree.
- `MI_LOAD_MENU    = 0xCA25` — open Load picker only, auto-exit on select.

## Architecture (modeled on cprog_menu / clear_menu / genre_menu)

State lives as file-static variables in `orthomidi5x14.c`:

```c
static bool    settings_menu_active = false;
static bool    settings_menu_oled_active = false;   // oled_clear bookkeeping
static uint8_t settings_menu_level = 0;              // current screen id
static uint8_t settings_menu_item  = 0;              // selected row
static uint8_t settings_menu_scroll = 0;             // scroll offset
// back-nav stack so every submenu returns to wherever we came from.
// Depth 6 is plenty (Main → Thruloop → Main Ops → Start Rec → Loop N → CC edit).
static uint8_t settings_menu_back_stack[8];
static uint8_t settings_menu_back_depth = 0;
static bool    settings_menu_dirty = false;          // unsaved edits?
static bool    settings_menu_editing = false;        // encoder in value-edit mode
static bool    settings_menu_load_only = false;      // opened via MI_LOAD_MENU
static bool    settings_menu_save_prompt = false;    // "Save changes?" overlay
static uint8_t settings_menu_confirm_kind = 0;       // 0=none 1=save 2=load
static uint8_t settings_menu_confirm_slot = 0;       // which slot for confirm
static uint8_t active_settings_slot = 0;             // last slot loaded (0..4)

// For CC editors that long-press-step by 10
static uint32_t settings_menu_hold_start = 0;
static bool     settings_menu_hold_fast = false;
```

`active_settings_slot` starts at 0, updated inside
`load_keyboard_settings_from_slot()` whenever the user loads. The Load
picker renders a `*` next to `active_settings_slot`.

## Level IDs

```
0  MAIN       Base / Loop / Thruloop / MIDI Routing / Display / Advanced /
              Save / Load
1  BASE           Channel / Transpose / Vel curve / Sustain / Keysplit> /
                  Triplesplit>
2  KEYSPLIT       KS Channel Enable / KS Trans Enable / KS Vel Enable /
                  Channel / Transpose / Vel curve / Sustain
3  TRIPLESPLIT    Channel / Transpose / Vel curve / Sustain
4  LOOP           Loop Messaging / Sync MIDI Mode / Alternate Restart /
                  CC Loop Recording
5  THRULOOP       Basic> / Loop Chop> / Main:Start Rec> / Main:Stop Rec> /
                  Main:Start Play> / Main:Stop Play> / Main:Clear> /
                  Main:Restart> / OD:Start Rec> / OD:Stop Rec> /
                  OD:Start Play> / OD:Stop Play> / OD:Clear> / OD:Restart>
6  THRULOOP_BASIC ThruLoop Channel / Send Restart Msgs / Alternate Restart
7  LOOP_CHOP      Separate CCs / Master CC / 0/8 CC .. 7/8 CC
8  MAIN_START_REC Loop 1..8 CC
9  MAIN_STOP_REC  Loop 1..8 CC
10 MAIN_START_PLAY Loop 1..8 CC
11 MAIN_STOP_PLAY Loop 1..8 CC
12 MAIN_CLEAR     Loop 1..8 CC
13 MAIN_RESTART   Loop 1..8 CC
14 OD_START_REC   Overdub 1..8 CC
15 OD_STOP_REC    Overdub 1..8 CC
16 OD_START_PLAY  Overdub 1..8 CC
17 OD_STOP_PLAY   Overdub 1..8 CC
18 OD_CLEAR       Overdub 1..8 CC
19 OD_RESTART     Overdub 1..8 CC
20 MIDI_ROUTING   (10 items — see full spec)
21 DISPLAY        OLED Keyboard cycle
22 ADVANCED       7 items — see full spec
23 SAVE           Default / Slot 1..4
24 LOAD           Default / Slot 1..4  (shows * next to active_settings_slot)
25 CONFIRM        "Save to Slot N?" / "Load Slot N?"  Yes / No
26 SAVE_PROMPT    "Save changes?"  Yes / No / Cancel   (ESC from MAIN w/ dirty)
27 SAVE_PICK      slot picker shown when user answers Yes to SAVE_PROMPT
```

## Input model (follows cprog_menu)

- **Top-knob rotate** (`KEYLOC_ENCODER_{CW,CCW}`, col 0): if `editing==true`,
  change the selected field's value; otherwise move selection up/down, adjust
  scroll. CC editors treat long-hold (>400ms since last rotation) as ×10 step.
- **Top-knob click** (row 5, col 1): "select" — enter submenu, toggle
  `editing` for leaf values, or answer Yes on CONFIRM/SAVE_PROMPT overlays.
- **Bottom-knob click** (row 5, col 0): consumed, no-op (matches cprog).
- **ESC key**: pop the back stack; if we're at level 0 and `dirty==true`,
  jump to SAVE_PROMPT. If `load_only==true`, ESC always closes.

### Encoder-suppression points (copy pattern from cprog)

Places to add `|| settings_menu_active` at the existing suppression checks:

- `orthomidi5x14.c:12995` block — route to `settings_menu_encoder(cw)` and
  return.
- `orthomidi5x14.c:19397` high-priority intercept — add us so user-assigned
  encoder keycodes don't leak through.
- `orthomidi5x14.c:22820` final "encoder event consumed" suppression.
- Top-knob click at `orthomidi5x14.c:19835` block — route to
  `settings_menu_click()` and return false.
- Bottom-knob at `orthomidi5x14.c:19840` — swallow and return false.
- ESC handler at `orthomidi5x14.c:19365` — call `settings_menu_back()`.

## Render helpers reused

- `oled_write_line(row, text)`  (c:23064)
- `oled_write_line_centered(row, text)`  (c:23091)
- `oled_write_big_centered(row, text)`
- 21-char wide × 16-row canvas.

Menu rendering skeleton (per level):

```
[0] Title (centered)
[1] ---------------------
[2] ... items with ">"/" " marker and " *" for currently-selected value ...
[13] blank
[14] Turn: scroll  Click: sel
[15] ESC: back
```

When `editing==true` on a list:

```
[13] >> value <<
[14] turn: change
[15] click: confirm
```

## Value editors per field

Pattern: each leaf field has a descriptor `{ name, type, get_fn, set_fn,
min, max, formatter }`. Rotation in edit mode clamps to range; click
commits and clears `editing`. Toggle fields (bool) click-toggles without
entering edit mode.

### Base
| Item | Variable | Range | Format |
|------|----------|-------|--------|
| Channel | `channel_number` | 0..15 | "Ch %d" (1..16) |
| Transpose | `transpose_number` | -12..+12 | "%+d" |
| Vel curve | `he_velocity_curve` | 0..4 | Softest/Soft/Med/Hard/Hardest |
| Sustain | `base_sustain` | 0/1 | Off/On |

### Base > Keysplit
| Item | Variable | Range |
|------|----------|-------|
| KS Channel Enable | `keysplitstatus` | 0..3 = Off/KS/TS/Both |
| KS Transpose Enable | `keysplittransposestatus` | 0..3 same |
| KS Velocity Enable | `keysplitvelocitystatus` | 0..3 same |
| Channel | `keysplitchannel` | 0..15 |
| Transpose | `transpose_number2` | -12..+12 |
| Vel curve | `keysplit_he_velocity_curve` | 0..4 |
| Sustain | `keysplit_sustain` | 0/1 |

### Base > Triplesplit
| Item | Variable | Range |
|------|----------|-------|
| Channel | `keysplit2channel` | 0..15 |
| Transpose | `transpose_number3` | -12..+12 |
| Vel curve | `triplesplit_he_velocity_curve` | 0..4 |
| Sustain | `triplesplit_sustain` | 0/1 |

### Loop
| Item | Variable | Notes |
|------|----------|-------|
| Loop Messaging | `loop_messaging_enabled` | Off/On (keyboard_settings) |
| Sync MIDI Mode | `sync_midi_mode` | Off/On (loop_settings) |
| Alternate Restart | `alternate_restart_mode` | Off/On (loop_settings) |
| CC Loop Recording | `cclooprecording` | 0=Off 1=AT 2=CC 3=Both |

### Thruloop > Basic
| Item | Variable |
|------|----------|
| ThruLoop Channel | `loop_messaging_channel` (1..16) |
| Send Restart Msgs | `sync_midi_mode` (Off/On) |
| Alternate Restart | `alternate_restart_mode` (Off/On) |

### Thruloop > Loop Chop
| Item | Variable |
|------|----------|
| Separate CCs | `loop_navigate_use_master_cc` inverted (On ↔ false) |
| Master CC | `loop_navigate_master_cc` 0..128 (128="None") |
| 0/8 CC | `loop_navigate_0_8_cc` |
| 1/8..7/8 CC | `loop_navigate_{1..7}_8_cc` |

### Thruloop > Main Ops  (6 leaf levels; each shows Loop 1..8)
Backed by `loop_start_recording_cc[8]` / `loop_stop_recording_cc[8]` /
`loop_start_playing_cc[8]` / `loop_stop_playing_cc[8]` / `loop_clear_cc[8]`
/ `loop_restart_cc[8]`.

### Thruloop > OD Ops  (6 leaf levels; each shows Overdub 1..8)
Backed by `overdub_start_recording_cc[8]` / `overdub_stop_recording_cc[8]`
/ `overdub_start_playing_cc[8]` / `overdub_stop_playing_cc[8]`
/ `overdub_clear_cc[8]` / `overdub_restart_cc[8]`.

### CC editor value model
- Canonical sentinel `128` = "None" (firmware default, see
  `process_dynamic_macro.c:254`).
- Rotation: decrement below 0 → 128 ("None"); increment above 127 → 128.
  So "None" sits on both ends of the dial, which is a common pattern.
- Long-press rotation (>400ms continuous same-direction rotation within
  150ms of previous tick) → step 10 instead of 1.
- Display: `"CC %d"` for 0..127, `"None"` for 128.

### MIDI Routing (10 items)
| Item | Variable | Range |
|------|----------|-------|
| MIDI IN Mode | `midi_in_mode` | 0..3 Process/Thru/ClockOnly/Ignore |
| USB MIDI Mode | `usb_midi_mode` | 0..3 same |
| Clock Source | `midi_clock_source` | 0..2 Local/USB/MIDI IN |
| Channel Override | `channeloverride` | 0/1 |
| Velocity Override | `velocityoverride` | 0/1 |
| Transpose Override | `transposeoverride` | 0/1 |
| Macro Override Live Notes | `macro_override_live_notes` | 0/1 |
| SmartChord Mode | `smartchord_mode` | 0=Hold 1=Toggle |
| Base SmartChord Ignore | `base_smartchord_ignore` | 0/1 |
| Keysplit SmartChord Ignore | `keysplit_smartchord_ignore` | 0/1 |
| Triplesplit SmartChord Ignore | `triplesplit_smartchord_ignore` | 0/1 |

### Display
| Item | Variable | Range |
|------|----------|-------|
| OLED Keyboard | `oledkeyboard` | Keyboard 1 / 2 / Guitar Low/Med/High — cycles via `apply_oledkeyboard()` |

### Advanced
| Item | Variable |
|------|----------|
| True Sustain | `truesustain` 0/1 |
| Sample Mode | `sample_mode_active` 0/1 |
| Unsynced Mode | `unsynced_mode_active` (cycle 0..5) |
| Custom Layer Animations | `custom_layer_animations_enabled` 0/1 |
| Guide Lights Mode | `smartchordlightmode` cycle 0→2→1→3→4→0 (All/Basic/Off/EADGB/ADGBE per existing handler at c:14058) |
| Seq Preview Mode | `seq_preview_mode` 0/1 |
| DAW Mode | `current_daw` (cycle through `daw_names[]`, persist via existing `daw_save_to_eeprom()`) |

## Save / Load flows

### Save tab (level 23)
Rows: Default / Slot 1 / Slot 2 / Slot 3 / Slot 4. Click → CONFIRM
(level 25) with `confirm_kind = SAVE`, `confirm_slot = row`.
Confirm Yes:

```
copy_all_globals_to_keyboard_settings();    // existing pattern, c:15579..
save_keyboard_settings_to_slot(slot);
save_loop_settings();                       // writes loop_settings_t too
settings_menu_dirty = false;
pop back to SAVE list
```

Confirm No → pop back to SAVE list, no write.

### Load tab (level 24)
Rows: Default / Slot 1 / Slot 2 / Slot 3 / Slot 4, with `*` on
`active_settings_slot`. Click → CONFIRM with `confirm_kind = LOAD`.
Confirm Yes:

```
load_keyboard_settings_from_slot(slot);
active_settings_slot = slot;
load_loop_settings();                       // refresh loop vars
analog_matrix_refresh_settings();           // if needed
settings_menu_dirty = false;
if (settings_menu_load_only)
    close the whole menu
else
    pop back to LOAD list (star now moves to `slot`)
```

### MI_LOAD_MENU keycode
Opens the menu with `level=24, load_only=true, dirty=false`. Same rendering
as above but CONFIRM Yes auto-closes the menu.

### ESC from level 0 with dirty==true
Enter SAVE_PROMPT (level 26) with items: Yes / No / Cancel.
- Yes → go to SAVE_PICK (level 27) — slot picker. On pick → CONFIRM (Yes/No).
  CONFIRM Yes → save + close menu entirely. CONFIRM No → return to SAVE_PICK.
- No → close menu, discard changes (nothing special — we never mutated
  EEPROM, the globals are the live state; "discard" means we flag the menu
  as closed without saving. Note: globals ARE mutated live — see note below).
- Cancel → pop back to level 0.

### "Discard changes" subtlety
The globals are the live state, so edits take effect immediately as the
user turns the knob. "Discard" therefore means: on entry to the menu we
snapshot the current state; on "No" we restore the snapshot. Simpler
alternative: treat "No" as "don't save to EEPROM" — user keeps the
in-session changes until reboot. **Plan: implement the simple version
(no save) first, add snapshot/revert later if you want it.** Will flag
in-code so we can upgrade.

## EEPROM touches

- `save_keyboard_settings_to_slot(slot)` — already exists.
- `save_loop_settings()` — already exists (called per-field-edit for any
  `loop_settings_t` fields edited from Thruloop screens, matching the GUI
  HID handlers which also save after each packet).
- On Save tab confirm: call both in sequence, as well as
  `daw_save_to_eeprom()` if DAW changed (we'll set a local flag).
- Display > OLED Keyboard: already persisted by `apply_oledkeyboard()`
  write-through to `keyboard_settings.oledkeyboard` (mutated globals are
  saved on the next Save tab confirm).

## Phasing

Build in this order so each phase is testable:

1. **Scaffolding** — keycodes, state variables, `settings_menu_active`
   plumbing (priority in `oled_task_user`, encoder/click/ESC intercepts),
   `active_settings_slot` tracking, stub `render_settings_menu()` showing
   just the Main tab list, a placeholder submenu that says "TODO".
2. **Save / Load + CONFIRM overlay** — so the user can already save a slot
   and load a slot at this point. `MI_LOAD_MENU` works. `*` marker works.
3. **Base + Keysplit + Triplesplit**.
4. **Loop + Thruloop > Basic**.
5. **MIDI Routing + Display + Advanced**.
6. **Thruloop > Loop Chop + 12 CC-array submenus** (Main × 6, OD × 6) —
   biggest chunk but all the same pattern, so one helper handles all.
7. **SAVE_PROMPT on ESC** (dirty-tracking polish).
8. **Long-press ×10 CC stepping** (refinement).

Each phase = one commit, each commit pushed to
`claude/add-settings-menu-7xIKR`. We won't open a PR; the user asks when
ready.

## Risks / gotchas

- **The existing GUI advanced-packet handler also writes every "keyboard
  settings" global when the user edits them in the GUI.** We're doing the
  same: touch the global directly, then mirror into `keyboard_settings.*`
  on Save. This mirrors the existing `save_keyboard_settings_to_slot()`
  pattern (orthomidi5x14.c:15579..15733).
- **Loop chop CC values 0..128** vs display "None at 128" — keep the
  encoder range 0..128 inclusive; display logic swaps to "None" at 128.
- **File size** — `orthomidi5x14.c` is 25k lines. We'll keep the new code
  in a single contiguous block near the other menu renderers
  (~line 23700 area) and its handlers adjacent so it's easy to find.
- **`apply_oledkeyboard()` side-effects** — changing `oledkeyboard`
  triggers display refresh. Fine for live preview but avoid calling it on
  every encoder tick — only on value commit. Probably cycle ad hoc.

## Definition of done

- `MI_SETTINGS_MENU` opens the menu. Full tree navigable. Every field
  editable. Save/Load confirm dialogs work. ESC with dirty triggers
  Save-changes prompt. `MI_LOAD_MENU` opens Load only and auto-exits.
- `*` marker next to active slot on Load page.
- Encoder suppression correct — rotating the top knob in the menu doesn't
  also fire CC/Transpose/Velocity/Channel encoder handlers.
- No regressions to cprog_menu, genre_menu, clear_menu, quick_build. All
  four menus must still open and behave identically.
