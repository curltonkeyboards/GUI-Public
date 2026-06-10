# DrumLIVE v2 — Implementation Plan (2 Phases)

This document tracks the DrumLIVE expansion. **Phase 1** reworks the DrumLIVE
menu/filter and adds sync + a QB‑Master preset. **Phase 2** restructures Drum
Settings (Channel / Preset Layout / Custom Layout) and adds the separate
DrumLIVE‑only voicing bindings.

The drum *pattern* data and the existing 12‑voice `factory_seq_config_t` are
**not** changed by either phase. Phase 2's extra voicings live in a brand‑new,
notes‑only array read solely by the DrumLIVE filter.

---

## Mode model (both phases)

Per‑target state is one of **On / Off / Quiet / Loud** (Solo removed):

| Mode | Meaning |
|------|---------|
| On   | pass note through unchanged (default) |
| Off  | block the note (mute) |
| Quiet| velocity ×0.5 |
| Loud | velocity ×1.5 (clamp 127) |

"Solo" is achieved with **Set All → Off**, then turn the one target **On**.

Two state buffers:
- `drum_live_active[18]`  — what the note filter reads (6 categories + 12 voices).
- `drum_live_edit[18]`    — what the menu/keycodes edit; committed to `active`.

A per‑voice setting overrides its category (when the voice ≠ On).

---

## Phase 1 — DrumLIVE menu rework + sync + QB preset  ← THIS PHASE

1. **Filter/state rework** (`drum_live.c/.h`)
   - Flat 18‑byte `edit` + `active` buffers; modes On/Off/Quiet/Loud.
   - Remove Solo everywhere (filter, keycodes, OLED field type, GUI).
   - `drum_live_commit()`: edit→active immediately, **unless** seq sync mode is
     on *and* something is playing → stage and apply at the next loop boundary.

2. **Sync deferral**
   - Hook `drum_live_on_loop_boundary()` into `dynamic_macro_handle_loop_trigger()`
     (the universal pattern/bar/loop boundary pulse). Commits any staged change.

3. **OLED menu = Presets / Basic / Advanced**
   - `SM_LEVEL_DRUM_LIVE` becomes a 3‑row chooser.
   - **Presets**: one‑click combos ("Kicks Only", "No Hats", "Quiet Hats",
     "Kicks & Snares", …). Applies + closes.
   - **Basic**: `Set All` + 6 categories (Kick/Snare/Hats/Cymbal/Toms/Perc).
   - **Advanced**: `Set All` + 12 voices. Each row cycles On/Off/Quiet/Loud.

4. **Keycodes** (`0xF140‑0xF18F`, re‑laid out)
   - `DRUMLIVE_MENU`, `DRUMLIVE_RESET` (all On), `DRUMLIVE_ALL_OFF`.
   - Per‑category Off/Quiet/Loud (6×3) and per‑voice Off/Quiet/Loud (12×3).
   - Toggle semantics (press a mode again → On). Sync‑aware via `commit`.

5. **QB Master "DrumLIVE Preset"**
   - New category in `master_menu_categories[]`.
   - Configure: opens the DrumLIVE menu in *capture* mode; a **Done** row saves
     the authored 18‑byte snapshot to a per‑master EEPROM region
     (`QB_DRUMLIVE_EEPROM_BASE`, mirrors the Fader extra‑data precedent).
   - Invoke (tap configured master): **toggle** — first tap applies the snapshot,
     next tap clears (all On). Sync‑aware.

6. **GUI** (`keycodes*.py`, `tabbed_keycodes.py`)
   - Update the DrumLIVE palette: Off/Quiet/Loud per target, Menu, Clear, All Off.
     Remove the Solo buttons.

---

## Phase 2 — Drum Settings restructure + voicing bindings  (FIRMWARE DONE)

Firmware status: implemented and host-tested. GUI mirroring + commercial preset
maps are the remaining follow-ups (see "Remaining" below).


1. **Drum Settings menu = Channel / Preset Layout / Custom Layout**
   - **Channel**: the existing default drum channel field.
   - **Preset Layout**: General MIDI / EZDrummer / Superior Drummer / BFD /
     Addictive Drums. Sets the note map. Where exact maps are known they're saved
     to EEPROM; otherwise a **Reset to Default** (GM‑based) entry is provided.
   - **Custom Layout**: per‑voice rows; selecting a voice opens a submenu with
     **Note / Velocity / Learn**. *Learn* arms a one‑shot capture of the next MIDI
     note (assigns its note + velocity).

2. **Extra DrumLIVE voicings (notes‑only)**
   - A new array (e.g. `drum_live_extra_notes[]`) stored in its own EEPROM region,
     **no velocity persisted**. Read by the DrumLIVE filter so extra GM
     percussion (crash, splash, china, pedal HH, electric snare, floor toms, …)
     can be muted/quieted/loudened. Appears in the same Custom Layout list.
   - Pattern data + the 12 sequenced voices are untouched.

3. **GUI** mirrors the new Drum Settings layout (Channel / Preset Layout / Custom
   Layout incl. extra voicings + Learn).  *(Remaining — see below.)*

### Phase 2 implementation notes (firmware)

- **OLED menu** (`orthomidi5x14.c`): `SM_LEVEL_DRUM_KEYBINDS` ("DRUM SETTINGS")
  is now a 3-row root — Def Channel, Preset Layout, Custom Layout.
  - `SM_LEVEL_DRUM_PRESET_LAYOUT`: General MIDI + Reset to Default (both apply the
    GM map today; commercial maps slot in as extra rows).
  - `SM_LEVEL_DRUM_CUSTOM_LAYOUT`: 12 sequenced voices + 16 extra voicings, each
    opening `SM_LEVEL_DRUM_VOICE_EDIT` (Note / Velocity / Learn — extras omit
    Velocity since it isn't persisted).
- **Extra voicings** (`drum_live.c`): `drum_live_extra_notes[16]` (Crash, Splash,
  China, Ride Bell, Pedal HH, Elec Snare, floor/mid toms, bongos, maracas, …),
  each fixed to a category, notes persisted at `DL_EXTRA_EEPROM_BASE` (63500,
  magic `0xDB06`). The filter maps these notes → category so category filters
  catch them; they have no per-voice DrumLIVE override (category only).
- **Learn**: `drum_live_learn_arm()` captures the next outgoing note-on via the
  `midi_send_noteon` hook (any channel), writes note (+velocity for sequenced
  voices) into the binding, and swallows the note. Regular keys still emit MIDI
  while the menu is open, so playing a key captures it; ESC/close cancels.
- **Save**: `sm_drum_kb_save_if_dirty()` now also flushes extra-voicing edits.

### GUI mirroring + HID (DONE)

- **HID**: extra-voicing notes reuse the existing drum family `0xE9/0xEA` with a
  new sub-mode `data[4] == 2` (16 notes at bytes 6..21); `0xEF` reset now also
  restores extras. No new command byte — conflict-free (used bytes are
  `0xC0–0xFD`; sub-mode keeps extras inside the drum command).
- **GUI** (`matrix_test.py`): Drum Settings tab restructured to **Default Channel
  / Preset Layout (General MIDI, Reset to Default) / Custom Layout** (12 voices
  with Note+Velocity, then the 16 extra voicings with Note + category label).
  `keyboard_comm.py` gains `get_drum_extra_notes()` / `set_drum_extra_notes()`.

### Remaining (follow-ups)

- **GUI Learn**: the device has on-OLED Learn; a GUI Learn button would need GUI
  MIDI-in (python-rtmidi) wiring — deferred.
- **Commercial preset maps**: EZDrummer / Superior Drummer / BFD / Addictive
  Drums — add as dedicated `sm_drum_preset_layout_fields[]` rows + GUI buttons +
  note tables once exact maps are sourced (they match GM for our core voices).

---

## Key integration points (from research)

- Sync boundary pulse: `dynamic_macro_handle_loop_trigger()`
  (`quantum/process_keycode/process_dynamic_macro.h`), called on every seq
  pattern/bar wrap and loop restart. Sync flag: `seq_state[0].sync_mode`.
  "Is anything playing": `seq_is_any_active()`, `dynamic_macro_is_playing()`,
  `progression_is_active()`.
- QB Master: `master_menu_categories[]` (`arpeggiator.c`), config dispatch
  `qb_master_open_target_setup()` switch, invoke via `process_record_user`
  QB‑master intercept (`orthomidi5x14.c`), per‑slot extra data precedent =
  `QB_FADER_EEPROM_BASE`.
- Drum bindings: `factory_seq_global_defaults` / `factory_seq_configs[]`
  (`seq_drum_patterns.c`), save `factory_seq_save_all_to_eeprom()`. Patterns use a
  4‑bit voice index → `drum_voice_note_table[]` (max 16 voices, untouched).
