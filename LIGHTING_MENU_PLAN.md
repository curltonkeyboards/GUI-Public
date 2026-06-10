# OLED Settings Menu — Lighting Submenu Plan

Extending the in-firmware settings menu (opened by `MI_SETTINGS_MENU` /
`0xCA24`) with a new top-level **Lighting** entry that mirrors the GUI's
three lighting tabs (Basic / Advanced / Custom Lights). All editing happens
on the keyboard's OLED via the encoders and back/click controls; the
keyboard LEDs themselves are repurposed as a live colour preview because the
OLED is monochrome.

All changes live in `vial-qmk - ryzen/keyboards/orthomidi5x14/orthomidi5x14.c`
(plus a tiny include of `functional_led_config.h`). No GUI changes.

---

## Anchors in the existing menu code

| Where | What |
|-------|------|
| ~line 350 | `SM_LEVEL_*` IDs — add new level IDs here. |
| ~line 24064 | `sm_main_items[]` — add `"Lighting"` entry. |
| ~line 24102 | `sm_field_type_t` enum — add new field types. |
| ~line 24158+ | Per-level `sm_field_t` tables — add `sm_lighting_*_fields[]`. |
| ~line 24422 | `sm_fields_for_level()` — register new tables. |
| ~line 24455 | `sm_level_title()` — add titles. |
| ~line 24487 / 24513 | `sm_field_get/set()` — handle new field types. |
| ~line 24662 | `sm_field_step()` — encoder behaviour for new types. |
| ~line 25009 | `sm_item_count_for_level()` — return counts for non-table levels. |
| ~line 25258 | `render_settings_menu()` — render any non-table levels. |
| ~line 25313 | `settings_menu_encoder()` — already generic. |
| ~line 25359 | `settings_menu_click()` — add `SM_LEVEL_MAIN` case for the new entry, plus any list-style picker levels. |

---

## Final menu layout

```
SETTINGS  (SM_LEVEL_MAIN)
├── Basic Settings
├── Playing Styles
├── Advanced Settings
└── Lighting                          ← new (SM_MAIN_LIGHTING)
    ├── Basic                         (SM_LEVEL_LIGHTING_BASIC)
    │   ├── Effect          ▸ RGB matrix mode
    │   ├── Color           ▸ 19-preset hue/sat picker (live preview)
    │   ├── Brightness      ▸ 0..255 (rgb_matrix_set_val)
    │   ├── Speed           ▸ 0..255 (rgb_matrix_set_speed)
    │   ├── Randomize       ▸ randomise effect/colour/brightness/speed
    │   ├── Save Settings   ▸ same as GUI's "Save Settings" button
    │   └── Save to Layer ▸ → layer picker (12 layers, names from custom_names_get)
    ├── Advanced                      (SM_LEVEL_LIGHTING_ADV)
    │   ├── Arpeggiator      ▸ sub-page (FLED_QB_*, FLED_PLAY_*, FLED_PRESET_*)
    │   ├── Step Sequencer  ▸ sub-page (FLED_SEQ_*)
    │   ├── Chord Progression ▸ sub-page (FLED_CPROG_*)
    │   ├── Macros          ▸ sub-page (FLED_VMACRO_*, FLED_HMACRO_*)
    │   ├── Loop Pedal      ▸ sub-page (FLED_LOOP_OD_*)
    │   ├── Toggle Keys     ▸ sub-page (FLED_TOGGLE_*)
    │   ├── Delay Slots     ▸ sub-page (FLED_DELAY_*, FLED_DELAY_QB_*)
    │   ├── SmartChord      ▸ sub-page (FLED_SC_*, FLED_CHORD_QB_*, FLED_DYNCHORD_QB_*)
    │   ├── Other Indicators ▸ sub-page (FLED_CAPS_LOCK, FLED_GAMING_MODE, FLED_TAP_*)
    │   └── Save Settings   ▸ writes func_led_config to EEPROM
    │
    │   Each feature sub-page lists every constituent FLED_* state with three
    │   editable fields per state: Color (preset picker), Brightness (V 0..255),
    │   Blink Mode (Solid / Slow Blink / Fast Blink).
    │
    └── Custom Lights                 (SM_LEVEL_LIGHTING_CUSTOM)
        ├── Slot                ▸ 1..50 picker; switching a slot also sets it
        │                         as the active RGB matrix custom-slot effect
        │                         so you can see the animation live.
        ├── Live Animation     ▸ effect / position / brightness / speed
        ├── Macro Animation    ▸ effect / position / brightness / speed
        ├── Background         ▸ effect / brightness / speed
        ├── Base Color         ▸ effect_hue (preset picker)
        ├── Color Scheme       ▸ color_type (Basic / Modular / Modular Desat / …)
        ├── Randomize          ▸ randomise current slot like Random 2
        ├── Save to Slot ▸ → 1..50 slot picker (saves current edit buffer)
        └── Load from Slot ▸ → 1..50 slot picker (loads slot into edit buffer
                                  AND sets it as the active RGB effect)
```

---

## New level IDs (added to the block ~line 380)

```
SM_LEVEL_LIGHTING_MAIN     31  // top of Lighting
SM_LEVEL_LIGHTING_BASIC    32
SM_LEVEL_LIGHTING_ADV      33
SM_LEVEL_LIGHTING_CUSTOM   34

// Picker-style screens (list, not field-table)
SM_LEVEL_LIGHTING_LAYER_PICK   35  // "Save to Layer" → 12 layer slots
SM_LEVEL_LIGHTING_SLOT_PICK_S  36  // Custom Lights: "Save to Slot"
SM_LEVEL_LIGHTING_SLOT_PICK_L  37  // Custom Lights: "Load from Slot"

// Custom Lights sub-pages
SM_LEVEL_LIGHTING_CL_LIVE      38
SM_LEVEL_LIGHTING_CL_MACRO     39
SM_LEVEL_LIGHTING_CL_BG        40

// Advanced > feature sub-pages
SM_LEVEL_LIGHTING_ADV_ARP      41
SM_LEVEL_LIGHTING_ADV_SEQ      42
SM_LEVEL_LIGHTING_ADV_CPROG    43
SM_LEVEL_LIGHTING_ADV_MACROS   44
SM_LEVEL_LIGHTING_ADV_LOOP     45
SM_LEVEL_LIGHTING_ADV_TOGGLE   46
SM_LEVEL_LIGHTING_ADV_DELAY    47
SM_LEVEL_LIGHTING_ADV_SC       48
SM_LEVEL_LIGHTING_ADV_OTHER    49
```

---

## New field types (`sm_field_type_t`)

```
SM_FT_RGB_EFFECT_BASIC     // QMK rgb_matrix_mode — cycles available modes
SM_FT_RGB_EFFECT_LIVE      // live_animation_t — custom-slot live effect
SM_FT_RGB_EFFECT_MACRO     // macro_animation_t — custom-slot macro effect
SM_FT_RGB_EFFECT_BG        // background_mode_t — custom-slot background
SM_FT_LIVE_POS             // live_note_positioning_t
SM_FT_MACRO_POS            // macro_note_positioning_t
SM_FT_COLOR_PRESET         // 19-preset HSV picker; backs onto two adjacent
                           //   uint8_t fields (hue, sat) via a small wrapper
SM_FT_BLINK_MODE           // FUNC_LED_SOLID / SLOW_BLINK / FAST_BLINK
SM_FT_COLOR_SCHEME         // color_type 0..N (Basic / Modular / …)
SM_FT_ACTION               // "button"-style row; click invokes f->post_set
                           //   (used by Save / Randomize / Save-to-Layer)
SM_FT_LIGHTING_SLOT        // 1..50 slot id with side-effect on change
                           //   (sets active RGB effect to that custom slot)
```

`SM_FT_COLOR_PRESET` stores the picked palette index in a `uint8_t*` and
writes through to two backing variables (hue + sat) via a small struct
referenced by `f->var`. Enables both Basic RGB (writes through to
`rgb_matrix_sethsv`) and Custom Lights (writes to `effect_hue` /
`effect_sat`) and Advanced (writes to `func_led_config.states[idx].h/.s`).

---

## Color palette (19 presets)

Index → (hue, sat):

| # | Name        | Hue | Sat |
|---|-------------|-----|-----|
| 0 | Red         | 0   | 255 |
| 1 | Orange      | 21  | 255 |
| 2 | Amber       | 32  | 255 |
| 3 | Yellow      | 43  | 255 |
| 4 | Lime        | 64  | 255 |
| 5 | Green       | 85  | 255 |
| 6 | Mint        | 106 | 200 |
| 7 | Cyan        | 128 | 255 |
| 8 | Aqua        | 128 | 200 |
| 9 | Teal        | 138 | 220 |
|10 | Azure       | 150 | 255 |
|11 | Blue        | 170 | 255 |
|12 | Indigo      | 180 | 255 |
|13 | Violet      | 196 | 255 |
|14 | Purple      | 213 | 255 |
|15 | Magenta     | 224 | 255 |
|16 | Pink        | 234 | 200 |
|17 | Rose        | 245 | 220 |
|18 | White       | 0   | 0   |

(Warm White removed per request.)

---

## Live colour preview

When an `SM_FT_COLOR_PRESET` field enters edit mode:

1. Snapshot current `rgb_matrix_get_mode()`, `_get_hue()`, `_get_sat()`,
   `_get_val()`, `_get_speed()` into a static `sm_preview_snap`.
2. Force `rgb_matrix_mode_noeeprom(RGB_MATRIX_SOLID_COLOR)` and
   `rgb_matrix_sethsv_noeeprom(palette[i].h, palette[i].s, current_val)`.
3. While editing, every encoder turn updates the preview HSV via
   `_noeeprom` calls (cheap, no flash writes).
4. **Click** commits: writes the picked hue/sat into the field's backing
   variable. For Basic the snapshot of the original effect is *not*
   restored (the new colour stays live). For Advanced / Custom Lights, the
   prior RGB effect is restored from the snapshot.
5. **ESC** cancels: backing variable unchanged, snapshot fully restored.

The same snap/restore pattern applies to `SM_FT_RGB_EFFECT_*` while
editing (so you see the new effect live) and to `SM_FT_LIGHTING_SLOT`
(switching slots immediately swaps the active custom slot animation).

---

## Persistence rules

| Where | Strategy |
|-------|----------|
| Lighting > Basic > Save Settings | `eeconfig_update_rgb_matrix()` (mirror of `id_lighting_save`). |
| Lighting > Basic > Save to Layer | Writes the current Basic RGB block (mode, hue, sat, val, speed, set-flag) to that layer's RAM cache + EEPROM via the existing `apply_layer_block` / layer-block save path. |
| Lighting > Advanced > Save Settings | `func_led_save_to_eeprom()`. |
| Lighting > Custom Lights > Save to Slot | `save_custom_slot_to_eeprom(slot)`. Edit buffer = `custom_slots[current_custom_slot]`. |
| Lighting > Custom Lights > Load from Slot | `current_custom_slot = slot` (already set), reapply the active RGB effect to that slot. |
| All other field edits | Write through to RAM globals immediately. The dirty flag (`settings_menu_dirty`) is **not** flipped by Lighting edits — the Lighting submenu manages its own persistence via the explicit Save buttons (consistent with the GUI). |

---

## Phases

### Phase 1 — Scaffold (this commit)
- Add level IDs (`SM_LEVEL_LIGHTING_*`).
- Add `SM_MAIN_LIGHTING` constant + "Lighting" item to `sm_main_items[]`.
- Add stub `sm_lighting_main_fields[]` (3 submenu entries).
- Add empty stub field tables for Basic / Advanced / Custom Lights so the
  submenus render with a "TODO: implemented in later phase" placeholder.
- Wire `sm_fields_for_level`, `sm_item_count_for_level`, `sm_level_title`.
- Add `SM_LEVEL_MAIN` click case for the new entry.
- Verify firmware still compiles and the menu renders the Lighting node.
- No new field types yet, no preview, no save buttons.

### Phase 2 — Lighting > Basic
- Add field types: `SM_FT_RGB_EFFECT_BASIC`, `SM_FT_COLOR_PRESET`,
  `SM_FT_ACTION`.
- Add the 19-colour palette table.
- Implement live preview snap/restore.
- Add `sm_lighting_basic_fields[]` with Effect / Color / Brightness /
  Speed / Randomize / Save Settings / Save to Layer.
- Add Layer Picker level (`SM_LEVEL_LIGHTING_LAYER_PICK`) using
  `custom_names_get(CN_CAT_LAYER, i)` for the per-slot label, falling
  back to `Layer N` when unset.
- Wire Save Settings → `eeconfig_update_rgb_matrix()`.
- Wire Save to Layer → write to `layer_rgb_cache[i][0..5]` + EEPROM.
- Wire Randomize → pick a random effect index from the QMK mode list,
  random palette colour, brightness 80..255, speed 100..220.

### Phase 3 — Lighting > Custom Lights
- Add field types: `SM_FT_RGB_EFFECT_LIVE/MACRO/BG`, `SM_FT_LIVE_POS`,
  `SM_FT_MACRO_POS`, `SM_FT_COLOR_SCHEME`, `SM_FT_LIGHTING_SLOT`.
- Add `sm_lighting_custom_fields[]` (top page) and the three sub-pages
  (`SM_LEVEL_LIGHTING_CL_LIVE/MACRO/BG`).
- Editing Slot field: snap previous effect, set
  `current_custom_slot = i`, switch RGB matrix mode to that slot's
  custom-anim effect for live preview.
- Save to Slot picker → `save_custom_slot_to_eeprom(slot)`.
- Load from Slot picker → `current_custom_slot = slot`, set RGB effect
  to that slot for visual confirmation.
- Randomize → call the same `randomize_with_criteria(slot)` path used by
  the firmware's Random 2 effect, on `current_custom_slot`.

### Phase 4 — Lighting > Advanced
- Add field type: `SM_FT_BLINK_MODE`.
- Build the 9 feature sub-pages mapping `FLED_*` index ranges from
  `functional_led_config.h` to (Color, Brightness, Blink) rows.
- Each row's three fields point at the same `func_led_config.states[i]`
  via three small adapter structs (one per role — H+S, V, Blink).
- Save Settings → `func_led_save_to_eeprom()`.

### Phase 5 — Polish
- Preview snap/restore on ESC at every level (not just per-field).
- Re-test back-stack interactions and dirty-flag semantics.
- Adjust marquee scroll for long FLED state names.
- Manual run-through of every menu path.
- Optional: tighten the field tables / share helpers if duplication is
  excessive.

---

### Phase 6 — Percent display + Custom Lights global brightness/speed

- New helper `sm_format_pct255(v, out, outsz)` writes `"N%"` where
  `N = (v * 100 + 127) / 255`. Used for every brightness / speed field
  backed by a 0-255 value.
- Fields that already store a 0-100 percentage (background_brightness)
  display as `"N%"` directly.
- Encoder stepping for percent-display fields: 1 raw unit fine, 10 raw
  units coarse (≈4% / ≈40% per click). Keeps the internal 0-255
  resolution; the display just rounds for the user.
- Add two new rows to `sm_lighting_custom_fields[]` below Slot:
  - **Brightness** → `SM_FT_LIGHTING_BASIC_BRIGHT`
  - **Speed** → `SM_FT_LIGHTING_BASIC_SPEED`
  These are the same QMK-global field types used on the Basic page and
  therefore share the existing snap/restore machinery.

### Phase 7 — Hierarchical picker menus for enum fields

Replaces the existing encoder-stepped `SM_FT_CUSTOM_LIVE_ANIM`,
`SM_FT_CUSTOM_MACRO_ANIM`, `SM_FT_CUSTOM_BG_MODE`, `SM_FT_CUSTOM_LIVE_POS`,
`SM_FT_CUSTOM_MACRO_POS`, `SM_FT_CUSTOM_COLOR_TYPE` with "click opens a
dedicated 2-level menu" behaviour. The Basic page's `Effect` picker also
routes through the same framework (flat list, single category).

**Generic framework** (added once, reused by all 6 pickers):

```c
typedef struct { uint8_t value; const char *name; } sm_picker_item_t;
typedef struct { const char *name; uint16_t first; uint16_t count; } sm_picker_cat_t;
typedef struct {
    const char              *title;       // OLED header text
    const sm_picker_cat_t   *cats;        // category list (L1)
    uint8_t                  cat_count;
    const sm_picker_item_t  *items;       // flat item list (L2)
    uint16_t                 item_count;
    bool                     flat;        // true -> skip L1, go straight
                                          //   to a single L2 listing all
                                          //   items (used for Basic Effect)
} sm_picker_t;

// Two new levels, generic across all pickers
#define SM_LEVEL_PICKER_L1  50
#define SM_LEVEL_PICKER_L2  51

// Active picker context (set when a field opens the picker)
static const sm_picker_t *sm_active_picker = NULL;
static uint8_t            sm_active_cat    = 0;
static void             (*sm_picker_commit)(uint8_t value) = NULL;
static uint8_t          (*sm_picker_get)(void) = NULL;  // current value
```

**Click flow**:

1. Click on a picker field → sets `sm_active_picker`, `sm_picker_commit`,
   `sm_picker_get`, and pushes `SM_LEVEL_PICKER_L1` (or L2 if `flat`).
2. L1 lists each category name; click pushes L2 with `sm_active_cat`.
3. L2 lists each item in the active category; cursor starts on the item
   matching the current value (via `sm_picker_get()`).
4. Encoder in L2 moves the cursor and ALSO live-applies the value via
   `sm_picker_commit()` — so the user sees each option rendered on the
   keyboard as they scroll. Matches the GUI's "apply on change" behaviour.
5. Click in L2 commits and pops back twice (past L1 to the caller's
   sub-page). ESC restores the value captured at L1 entry.

**Pickers defined** (data from GUI rgb_configurator.py):

| Picker | Source | Items | Categories |
|--------|--------|-------|------------|
| `sm_picker_live_anim` | `LIVE_EFFECTS_HIERARCHY` (l.219) | 172 | 25 |
| `sm_picker_macro_anim` | alias to above (shared)        | 172 | 25 |
| `sm_picker_background` | `BACKGROUNDS_HIERARCHY` (l.458) | 121 | 13 |
| `sm_picker_live_pos` | `LIVE_STYLES_HIERARCHY` (l.627) | 34 | 7 |
| `sm_picker_macro_pos` | `MACRO_STYLES_HIERARCHY` (l.679) | 47 | 8 |
| `sm_picker_color_scheme` | `CUSTOM_LIGHT_COLOR_TYPES_HIERARCHY` (l.749) | 85 | 11 |
| `sm_picker_basic_effect` | curated list (flat) | 36 | 1 |

Totals align with the firmware enum sizes (Phase 3's earlier 174/84
estimates are corrected to 172/85).

**Additional Custom Lights hooks**:

- Entering `SM_LEVEL_LIGHTING_CUSTOM` via submenu click forces
  `rgb_matrix_mode_noeeprom(sm_custom_slot_mode_for(current_custom_slot))`
  so the keyboard always shows the slot being edited as soon as you
  arrive, not just after touching the Slot field.
- Any L2 scroll or commit on Custom Lights pickers also writes through
  to `custom_slots[current_custom_slot]` before the keyboard's next
  render cycle, giving the same "live apply" feedback the GUI provides.

**Snap/restore for pickers**:

- L1 entry captures the picker's current value via `sm_picker_get()`.
- L2 encoder scroll live-applies each visited value.
- Click in L2 commits + releases snap.
- ESC from L1 or L2 restores the captured value via `sm_picker_commit()`.
