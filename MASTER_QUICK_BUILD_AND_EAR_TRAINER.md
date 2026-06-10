# Master Quick Build + Ear Trainer

Reference doc for the two new systems added on `claude/master-quickbuild-menu-dZcYG`. Implementation lives in `vial-qmk - ryzen/keyboards/orthomidi5x14/` plus the GUI in `src/main/python/`.

---

## 1. Master Quick Build (`QB_MASTER_1..QB_MASTER_50` = `0xECB6..0xECE7`)

Fifty programmable keycodes. Each master slot owns a `{category, slot}` assignment stored in EEPROM. Tapping an unconfigured master opens a picker; tapping a configured master acts as the assigned target keycode (Arp QB, Seq QB, drum machine, chord prog, ear trainer, etc.) transparently.

### Why 50 keycodes instead of one
Earlier design used a single `QB_MASTER_MENU` keycode that scanned the entire dynamic keymap on every picker render (~6 KB of EEPROM reads per frame) and rewrote itself via `dynamic_keymap_set_keycode`. That froze the OLED on open. The new design:

- **50 distinct keycodes**: place as many as you like in the keymap; each one programmable on-device.
- **RAM-backed assignment table**: `qb_master[50]` of `{category, slot}`, loaded at boot, saved to EEPROM per-slot on change.
- **O(50) lookups**: picker render counts per-category usage in RAM; press-handler resolves target keycode from the same array. No keymap scan, no EEPROM reads on the hot path.
- **No keymap mutation**: the master keycode stays `QB_MASTER_N` in the keymap forever. Changing assignments only touches `qb_master[]`, not the Vial keymap.

### Categories and ranges (unchanged)
| Category | Slots | Target keycode range |
|---|---|---|
| Arp QB | 4 | `0xEF74, 0xEF7D-0xEF7F` |
| Seq QB | 8 | `0xEF75-0xEF7C` |
| Delay QB | 4 | `0xEF8C, 0xEFF2-0xEFF4` |
| SmartChord | 8 | `0xEF8D, 0xEFF5-0xEFFB` |
| DynChord | 4 | `0xEF8E, 0xEFFC-0xEFFE` |
| Fader QB | 8 | `0xEEA5-0xEEAC` |
| Drum Machine | 20 | `0xED98-0xEDAB` |
| Chord Prog | 20 | `0xCA10-0xCA23` |
| Ear Trainer | 10 | `0xEDF0-0xEDF9` |

### EEPROM layout
- `QB_MASTER_EEPROM_BASE = 60524`
- 2 B magic (`0xDB02`) + 50 × 2 B (`{category, slot}`) = 102 bytes total.

### Firmware touchpoints
- `orthomidi5x14.h` — `QB_MASTER_BASE` / `QB_MASTER_END` / `QB_MASTER_COUNT` defines; `qb_master_slot_t` typedef; extern `qb_master[]`; `qb_master_init()`, `qb_master_save_slot()`, `qb_master_target_keycode()` prototypes.
- `arpeggiator.c` — category table, `qb_master[]` with EEPROM load/save, `qb_master_find_free_sub_slot()` allocator, picker open/encoder/click. No keymap scan anywhere.
- `orthomidi5x14.c` — `QB_MASTER_BASE..END` range check in `process_record_user`: unconfigured opens picker; configured remaps the `keycode` variable to the target and falls through so the target's normal handler runs both press and release. `qb_master_init()` called at `keyboard_post_init_user`. `render_quick_build_master_menu` counts used categories from the RAM array.
- GUI: `src/main/python/keycodes/keycodes_v6.py` (hex for 50), `keycodes.py` (`KEYCODES_QB_MASTER` with 50 entries), `tabbed_keycodes.py` ("Master" group in Quick Build tab).

### UX
- **Tap unconfigured master**: opens the picker. Encoder scrolls categories; click assigns the next free sub-slot in that category and exits.
- **Tap configured master**: fires the assigned target keycode (as if you'd pressed `ARP_QB_2` directly). Release passes through to the target's release handler.
- **Cancel**: ESC closes the picker without saving. No state changes.
- **Full categories**: show `FULL N/N`; picking is a no-op.
- **Reassignment** (ESC-to-picker routing): when a QB_MASTER_N press triggers a target whose menu later opens on screen, ESC from that menu closes it normally (state cleanup, preview stops, EEPROM saves) and then — on the last ESC that would have closed the chain to idle — opens the master picker for that same slot. The user picks a new category, click saves, and the master now diverts to something different. No Vial edit, no keymap mutation.

### How the ESC-to-picker tag works
A single global tag `qb_master_invocation_id` is set on master press and cleared either (a) when the ESC post-hook opens the picker, or (b) when `matrix_scan_user` observes that every menu flag is down *and* the master key is no longer physically held. This means:
- Non-master presses never trigger the picker on ESC.
- Going up one menu level (ESC in a deep sub-menu that's still active afterwards) leaves the tag alone.
- Closing the last open menu to idle triggers the picker exactly once.
- Exiting by any non-ESC path (click-to-save, auto-advance) lets the tick quietly drop the tag so a later unrelated ESC doesn't surprise-open the picker.

---

## 2. Ear Trainer Quick Build (`ET_QB_1..10 = 0xEDF0..0xEDF9`)

Ten per-key slots. Each stores a mode, preset or custom selection, and difficulty in EEPROM.

- **Tap** while idle → start a training session.
- **Tap** while active → stop & cancel.
- **Hold 2 s** → open the setup walker for that slot (mode / preset / custom / difficulty).
- **ESC** → stop & cancel the session or setup.

All business logic lives in `ear_trainer.c`. The file is registered in `rules.mk` and `ear_trainer_init()` is called from `keyboard_post_init_user()` in `orthomidi5x14.c`.

### Per-slot config (EEPROM)
`ear_trainer_config_t` (24 B, packed). 10 slots × 24 B = 240 B at EEPROM base `60284`. A 2-byte magic word at `60284` guards first-boot seeding; subsequent boots just load the saved slots.

Fields:
- `mode` — `ET_CFG_MODE_INTERVAL` / `ET_CFG_MODE_CHORD`
- `preset` — `0..N-1` or `ET_CFG_PRESET_CUSTOM` (`0xFF`)
- `difficulty` — `EASY / MEDIUM / HARD / EXPERT` (Expert only for chord mode)
- `inversions_allowed` — auto-set when difficulty = Expert + mode = Chord
- `interval_mask[5]` — 37 bits, bit `(semitone + 24)` for the custom interval selection
- `chord_mask_3n / 4n / 5n` — one bit per chord id within each note-count bucket
- `valid` — nonzero once the user has saved a real config (defaults until then)

### Session state machine (`ear_trainer_state_t`)
Owns everything alive for one trainer lifecycle.

| Phase | Purpose | Exits to |
|---|---|---|
| `IDLE` | No session | — |
| `SETUP` | Hold-triggered parameter walk | `IDLE` (save or cancel) |
| `COUNTDOWN` | 3-2-1 via `oled_write_big_centered` | `PLAYING` at 3s |
| `PLAYING` | Blind playback (timeline fires note-on/off) | `ANSWER` when timeline ends |
| `ANSWER` | Picker list + 2-s replay loop until click | `RESULT` on submit |
| `RESULT` | CORRECT/WRONG + streak + reveal + one last playback | `COUNTDOWN` (5 s auto-advance or click) |

`quick_build_state.mode == QUICK_BUILD_ET_ACTIVE` whenever the trainer owns the screen so ESC / encoder hijacks / OLED dispatch flow through the existing Quick Build plumbing.

### Catalog (reused from SmartChord)
- `et_chords[]` — 43 entries mirror the offsets in `orthomidi5x14.c:18841`. Names come through the existing `getSmartChordNameForKeycode()` lookup so we do not duplicate chord-name strings.
- Buckets: 3-note (triads), 4-note, 5-note. `et_chord_bucket(id)` returns the bucket, `et_chord_bucket_bit(id)` the bit position within its bucket mask.
- Interval labels: `et_format_interval_label()` emits short tokens (`m3`, `P5`, `+8va+M3`, `-2x8va`, …).

### Preset semantics
Preserves the original `MI_ET_*` / `MI_CET_*` semantics so the old keycodes can be retired without losing function.

| Mode | Preset IDs |
|---|---|
| Intervals | 0 Basic (±P5) · 1 Octave (±8va) · 2 Extended (−24..+12) · 3 All (+unison) · 4 Custom |
| Chords | 0 Triads · 1 Basic 7ths · 2 All 7ths · 3 Triads+Basic 7ths · 4 Triads+All 7ths · 5 Custom |

### Playback engine
- **Non-blocking**: `ear_trainer_tick()` (called from `matrix_scan_user` via `quick_build_update`) fires events whose scheduled time has elapsed. Notes hit the MIDI layer via `midi_send_noteon_trainer` / `midi_send_noteoff_trainer` on `channel_number`.
- **Event timeline**: up to 40 `{time_ms, note, velocity}` events; built in `et_build_timeline()` using the round's note list + the difficulty-driven timing rules.
- **Difficulty mapping** (folds "raw vs arpeggiated-then-raw" into the difficulty ladder):

| Difficulty | Style |
|---|---|
| Easy | slow sequential + simultaneous (most informative) |
| Medium | sequential + simultaneous at normal pace |
| Hard | simultaneous only — pick it out from one chord |
| Expert (chords) | simultaneous + random octave inversion |

- **Random root**: `rand() % [48..60]` each round so compound intervals stay in MIDI range. RNG is seeded from `timer_read32()` on the first tap (not at boot) to avoid the near-zero boot clock.

### Answer picker + result
- `et_build_picker()` walks the same preset/custom masks used for the random pick and stashes every eligible answer id into `picker_items[]`. The correct index is recorded before playback starts.
- During `ANSWER`, encoder CW/CCW scrolls a 7-row visible window; click submits.
- `RESULT` reveals the label in all cases (CORRECT shows "Answer: X" too so the user reinforces the name), updates the streak (+1 correct, 0 wrong), and replays the answer once more.
- Auto-advance after 5 s, or encoder click skips.

### Keyboard/guitar-tab backdrop
`render_luna` / `render_tab` live at the bottom of the OLED (rows 10-15). `ear_trainer_paint_backdrop()` (in `orthomidi5x14.c`, so it can call the static renderers) is invoked by `ear_trainer_render()` for the `ANSWER` and `RESULT` phases. The picker/result text sits on rows 0-9; the user's default keyboard view shows the live note-ons as the timeline plays.

### Setup walker (hold to open)
Linear page walk, edit-buffer pattern — changes go live in `et_configs[slot]` + EEPROM only on the final "Difficulty" click.

| Page | Items | Advances to |
|---|---|---|
| Mode | Intervals / Chords | Preset |
| Preset | 4 or 5 presets + Custom | Difficulty (or Custom_IV / Custom_CH_Menu) |
| Custom_IV | toggle list for 37 semitones + Done | Difficulty |
| Custom_CH_Menu | 3-note / 4-note / 5-note / Done | Custom_CH_List (or Difficulty) |
| Custom_CH_List | toggle list of chord names + Done | back to Custom_CH_Menu |
| Difficulty | Easy / Medium / Hard (+ Expert on chord) | saves + exits |

First-time Custom for intervals seeds the mask from the user's previous preset so they don't start blank.

### GUI
- `keycodes_v6.py` — hex values.
- `keycodes.py` — `KEYCODES_EARTRAINER_QB` with labels `"Ear\nTrainer\n1"..10`; included in the global `KEYCODES` assembly.
- `tabbed_keycodes.py` — optional `ear_trainer_qb` list threaded into `QuickBuildTab`; rendered as a new "Ear Trainer" group at the bottom of the Quick Build tab.

### Where to extend
- **Max events**: `ET_MAX_EVENTS` in `ear_trainer.c` (currently 40; a 5-note Easy round uses ~20).
- **Root range**: `ET_ROOT_MIN / ET_ROOT_MAX` (currently `[48, 60]`). Widen for more variety.
- **Difficulty timings**: constants inside `et_build_timeline()` — one central switch.
- **Chord catalog**: append rows to `et_chords[]` (keep bucket consistent, update masks if you need more than 32 chords per bucket).

---

## Relationship to the rest of the codebase
- Extends the pre-existing `quick_build_mode_t` FSM; no new global state machine.
- Shares the existing ESC / encoder hijack / OLED dispatch plumbing — new code only adds branches, never rewires.
- Reuses `getSmartChordNameForKeycode()`, `midi_send_noteon/off_trainer`, `channel_number`, `oled_write_line / _centered / _big_centered`, `render_luna / render_tab`.
- Persists in a previously-unused EEPROM band (`60284..60524`) so it does not collide with the layouts documented in `CLAUDE.md`.
