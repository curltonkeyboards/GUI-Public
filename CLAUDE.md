# CLAUDE.md - Project Knowledge Base

## Project Overview

This is a custom Vial GUI + QMK firmware for the **orthomidi5x14** Hall effect MIDI keyboard (5 rows x 14 columns = 70 keys). It combines a Python/PyQt5 desktop configurator with a ChibiOS-based QMK firmware fork that implements analog Hall effect sensing, MIDI velocity, aftertouch, rapid trigger, and per-key calibration.

## Repository Structure

```
vial-gui-custom/
├── src/main/python/              # PyQt5 GUI application
│   ├── main.py                   # Entry point
│   ├── main_window.py            # Main application window
│   ├── editor/
│   │   ├── velocity_tab.py       # Velocity config, preset management, live visualization
│   │   ├── trigger_settings.py   # Per-key actuation/RT/deadzone configuration
│   │   ├── matrix_test.py        # Matrix testing/debugging
│   │   ├── keymap_editor.py      # Keymap layout editor
│   │   └── rgb_configurator.py   # LED configuration
│   └── widgets/
│       └── curve_editor.py       # Interactive 4-point velocity curve editor (300x300 canvas)
├── vial-qmk - ryzen/            # Firmware (QMK fork)
│   ├── quantum/
│   │   ├── matrix.c              # Core analog matrix (2660+ lines) - calibration, RT, MIDI, velocity
│   │   ├── matrix.h              # Constants, structs, public API
│   │   └── distance_lut.h        # 1024-entry measured-curve linearization LUT
│   └── keyboards/orthomidi5x14/
│       └── config.h              # Hardware config (ADC defaults, pin mappings)
├── requirements.txt              # Python deps (PyQt5==5.9.2, fbs==0.9.0, python-rtmidi)
└── *.md                          # Various implementation/analysis docs
```

## Build System

- **GUI:** Python 3.6+ with PyQt5, built via `fbs` (Flask-Based Setup)
- **Firmware:** QMK build system (ChibiOS-based for ARM)
- **Entry point:** `src/main/python/main.py`

---

## Firmware Architecture (matrix.c)

### Scan Cycle Pipeline

Every scan cycle, each key goes through this pipeline (matrix.c ~line 2180):

```
1. Read raw ADC sample
2. Filter: 3-sample EMA, alpha = 1/2 (calibrated keys only; uncalibrated keys
   pass raw so the late-seed stability check sees the true sensor)
3. Update calibration (continuous auto-calibration)
4. Calculate distance: adc_to_distance(filtered, rest, bottom) → 0-255
5. Apply rest dead zone: distance <= 3 → 0  (prevents ADC noise residuals)
6. Process rapid trigger state machine (3-state FSM)
7. Process MIDI key (velocity modes, aftertouch, retrigger)
```

### Key State Structure (`key_state_t`, line 110)

```c
typedef struct {
    uint16_t adc_raw;               // Raw ADC (no filtering)
    uint16_t adc_filtered;          // Filtered ADC (3-sample EMA, alpha = 1/2)
    uint16_t adc_rest_value;        // Calibrated rest position
    uint16_t adc_bottom_out_value;  // Calibrated bottom-out position
    uint8_t  distance;              // 0-255 (0=rest, 255=full press)
    uint8_t  extremum;              // Peak/trough for RT FSM
    key_dir_t key_dir;              // KEY_DIR_INACTIVE / DOWN / UP
    bool     is_pressed;            // Logical pressed state
    bool     calibrated;            // Has been bottom-out calibrated
    uint8_t  base_velocity;         // For RT velocity accumulation
    uint16_t last_adc_value;        // Previous ADC (stability detection)
    uint16_t stable_start_adc;      // ADC when stability was first detected
    uint32_t stable_time;           // Timestamp when key became stable
    bool     is_stable;             // Currently stable
} key_state_t;
```

### Hardware Constants (matrix.h)

| Constant | Value | Meaning |
|----------|-------|---------|
| `MATRIX_ROWS` x `MATRIX_COLS` | 5 x 14 = 70 keys | Physical matrix |
| `FULL_TRAVEL_UNIT` | 40 | 4.0mm max travel (0.1mm per unit) |
| `TRAVEL_SCALE` | 6 | Internal precision multiplier |
| `DISTANCE_MAX` | 255 | Full-range distance scale |
| `DEFAULT_ZERO_TRAVEL_VALUE` | 3000 | Default rest ADC (overridden per-key at boot) |
| `HALL_REST_TO_BOTTOM_DELTA` | 674 | Measured rest-to-bottom ADC range (4mm travel) |
| `VALID_ANALOG_RAW_VALUE_MIN/MAX` | 1000 / 2500 | Valid ADC bounds |
| `CALIBRATION_EPSILON` | 5 | Minimum meaningful ADC movement |
| `AUTO_CALIB_ZERO_TRAVEL_JITTER` | 50 | Minimum stability threshold |
| `AUTO_CALIB_STABILITY_PERCENT` | 2 | Must be within 2% of stable value |
| `AUTO_CALIB_MAX_REST_DRIFT_PERCENT` | 10 | Only recalibrate if within 10% of rest |
| `AUTO_CALIB_VALID_RELEASE_TIME` | 5000 | 5 seconds stability required for recalibration |

### Hall Effect Sensor Characteristics

- **Inverted operation:** Higher ADC = more released, lower ADC = more pressed
- **Typical rest ADC:** 1650-2250
- **Typical pressed ADC:** 1100-1350
- **Warm-up estimation:** `bottom = rest * 0.52 + 200` (linear fit from measured data)

---

## Calibration System (matrix.c, `update_calibration()` ~line 882)

### How It Works

Auto-calibration continuously tracks the true rest and bottom-out positions:

1. **Stability Detection:** Key must stay within 2% of a stable reference value. If it drifts beyond 2% or moves more than `CALIBRATION_EPSILON` (5 ADC units), stability resets.

2. **Rest Recalibration:** When the key is:
   - Stable (not jittering)
   - Not pressed (`is_pressed == false`)
   - Near rest (raw ADC within 10% of current `adc_rest_value`)
   - Stable for **5 seconds** (`AUTO_CALIB_VALID_RELEASE_TIME`)
   - ADC has drifted more than `CALIBRATION_EPSILON` from current rest

   Then `adc_rest_value` is updated to the current filtered ADC.

3. **Bottom-out Recalibration:** Whenever a new minimum ADC is seen (below current `adc_bottom_out_value - CALIBRATION_EPSILON`), the bottom is updated immediately. This expands the range continuously.

### Critical Design Decision: Both Directions Require 5s Wait

**Both** "away from pressed" (upward ADC) **and** "toward pressed" (downward ADC) drift require the 5-second stability wait before recalibrating rest. This was changed because the previous instant upward recalibration allowed transient ADC spikes (20-30 units) to be immediately locked in as the new rest position, creating persistent 0.1-0.2mm residual readings.

### Initialization (Warm-up, ~line 2270)

During the first 5 scan cycles:
- `adc_rest_value` = actual ADC reading (post inversion)
- `adc_bottom_out_value` = `rest - HALL_REST_TO_BOTTOM_DELTA` (674 ADC units = measured 4mm range)
- `adc_filtered` = actual ADC reading

Bottom-out is never independently auto-calibrated; if rest drifts later, bottom moves with it (same delta).

---

## Distance Calculation (distance_lut.h)

### Pipeline: ADC → Distance (0-255)

```
1. Normalize: (rest - adc) * 1023 / (rest - bottom)  → 0-1023
2. Calculate linear distance: normalized * 255 / 1023  → 0-255
3. Look up LUT-corrected distance: distance_lut[normalized] → 0-255
4. Blend: linear * (100 - strength) + lut * strength) / 100
```

**Boundary behavior:**
- `adc >= rest` → distance = 0 (at or above rest)
- `adc <= bottom` → distance = 255 (at or below bottom)

### Rest Dead Zone (matrix.c, after `adc_to_distance()`)

After distance calculation: `if (distance <= 3) distance = 0`

This eliminates 1-2 ADC unit noise residuals (~0.05mm) that would otherwise produce non-zero distance at rest and break the `last_travel == 0 && travel > 0` velocity timer gate.

### Linearization LUT (distance_lut.h)

Single 1024-entry piecewise-linear table mapping normalized ADC position
(0-1023) to physical-mm distance (0-255). Built from the five measured
sensor anchors:

| Travel | ADC (rest 1904) | Normalized | Distance |
|--------|----------------:|-----------:|---------:|
| 0 mm   | 1904            |    0       |     0    |
| 1 mm   | 1800            |  158       |    64    |
| 2 mm   | 1650            |  386       |   128    |
| 3 mm   | 1450            |  689       |   192    |
| 4 mm   | 1230            | 1023       |   255    |

All keys share one curve — the new sensor cohort sits within ~40 ADC
units of each other, so the legacy per-rest-range EQ system (3 ranges,
5 bands, quadratic blending) is gone. Per-key calibration still scales
each sensor's `(rest - adc)` into the shared 0-1023 input range using
its own rest. Default `lut_correction_strength` is 100; a user-tunable
strength slider blends back toward raw linear (sensor non-linearity)
if desired.

---

## Rapid Trigger State Machine (matrix.c, `process_rapid_trigger()` ~line 1003)

3-state FSM inspired by libhmk:

```
KEY_DIR_INACTIVE → (distance > actuation_point) → KEY_DIR_DOWN [pressed]
KEY_DIR_DOWN     → (distance <= reset_point)     → KEY_DIR_INACTIVE [released]
KEY_DIR_DOWN     → (distance + rt_up < extremum) → KEY_DIR_UP [released by RT]
KEY_DIR_UP       → (distance <= reset_point)     → KEY_DIR_INACTIVE [released]
KEY_DIR_UP       → (extremum + rt_down < distance) → KEY_DIR_DOWN [re-pressed by RT]
```

Both modes gate the **first** activation on the fixed actuation point
(`distance > actuation_point`) — continuous does **not** actuate from rest. The
modes differ only in the **reset point**:

- **Standard RT** (`reset_point = actuation_point`): the key is "ready" only
  within the actuation→bottom range. RT (`rt_up`/`rt_down`) dynamics apply there;
  rising back above the actuation point resets to `INACTIVE` (must re-cross
  actuation to fire again).
- **Continuous RT** (`reset_point = 0`, `PER_KEY_FLAG_CONTINUOUS_RT`): once
  activated at the actuation point, the key stays RT-live across the **entire**
  travel (even above the actuation point, up toward rest) and only resets at full
  release (`distance <= 0`).

### Threshold-mode press hysteresis (non-RT keys)

When RT is **disabled** (plain threshold mode), `is_pressed` used to be a bare
`distance >= actuation_point`. With the EMA filter bypassed (raw ADC), a slow
press hovering at the actuation line let scan-to-scan jitter flip the latch
true→false→true and fire the key many times. Both key types now latch with a
`max(50% of actuation, floor)` retrigger band — press at actuation, release
only after receding that far below it (or reaching rest):

- **MIDI keys:** floor = 0.5mm (`REARM_MIN_RECEDE_DIST` = 32).
- **Non-MIDI keys:** floor = 1mm (`NORMAL_KEY_MIN_RECEDE_DIST` = 64). For a 2mm+
  actuation the 50% term dominates (reset at 50% of actuation); below 2mm the
  1mm floor takes over (e.g. 1mm actuation must return to rest). Tunable via the
  `#define` in `matrix.c`.

(The RT-enabled FSM has its own `rt_up`/`rt_down`/`reset_point` dynamics and is
left as-is.)

### Deadzone Remapping (inside `process_rapid_trigger()`)

Before RT logic, distance is remapped through per-key deadzones:
- `distance <= dz_bottom` → 0
- `distance >= 255 - dz_top` → 255
- Otherwise: linearly rescaled `[dz_bottom, 255-dz_top]` → `[0, 255]`

**Hidden 0.1mm bottom-deadzone floor (ship guard, 2026-07):** the effective
deadzones are read through `get_effective_deadzones()` (`matrix.c`), the single
place holding the (#9) >51 corruption clamp **and** a hidden minimum bottom
deadzone `HIDDEN_MIN_DZ_BOTTOM = 6` (the value the GUI labels "0.1mm"; 0-51 =
0-0.8mm). Any configured bottom deadzone below 0.1mm (e.g. 0.05mm = 3, or 0)
is silently raised to 0.1mm at read time — the stored per-key setting and its
GUI round-trip are untouched, so the floor is invisible to the user and the
GUI needs NO change (it may keep offering values below 0.1mm; the device
ignores them). The velocity deadzone-compensation ranges (`dz_effective_range`
in `process_midi_key_analog`) read through the same helper so compensation
always matches the remap actually applied. The top (bottom-out side) deadzone
has no floor — it does not gate presses.

---

## Velocity Modes (matrix.c, `process_midi_key_analog()` ~line 1230)

### Mode 0: Fixed Velocity
Raw velocity = 255. The velocity curve determines actual output.

### Mode 1: Peak Travel (Direction Reversal)
- Triggers at max velocity when actuation point is crossed
- OR triggers on direction reversal (key starts moving up after pressing down)
- Velocity = peak travel depth (deeper = louder)
- Min peak: 12 units (~0.2mm), reversal threshold: 18 units (~0.3mm)
- Note off at travel < 30 (~0.5mm)

### Mode 2: Speed-Based (Rest to Actuation)
- Timer starts when `last_travel == 0 && travel > 0` (key starts moving from rest)
- Velocity captured when travel crosses the actuation threshold
- Linear interpolation: `max_press_time` → velocity 255, `min_press_time` → velocity 1
- Supports partial re-press with midpoint velocity scaling
- Deadzone compensation scales elapsed time by `255 / effective_range`

### Mode 3: Speed + Peak Combined
- Blends speed-based and peak travel velocity using `zone_speed_peak_ratio`
- Triggers on direction reversal (blended) OR actuation point (blended)
- `blended = (speed * ratio + peak * (100 - ratio)) / 100`

### Critical: `last_travel` Reset on Release

In all speed-based modes (1, 2, 3), when a note-off condition triggers, `last_travel` is set to 0 and the `last_travel = travel` update is **skipped that cycle** (via an else branch). This ensures the `last_travel == 0 && travel > 0` gate fires correctly on the next press. Previously, `last_travel = travel` at the bottom of each mode unconditionally overwrote the 0 with residual travel, preventing the speed timer from ever restarting.

### Anti-Jitter Guards (reversal modes 1 & 3) and Note Re-arm

Because the EMA filter is bypassed (raw ADC), scan-to-scan noise was faking
"upstrokes" and machine-gunning notes near rest (e.g. a slow press to ~0.5mm
with a 3mm actuation would trigger). Two guards, tuned in `matrix.c`:

- **Reversal must be a real upstroke** — a reversal only fires when travel has
  dropped `REV_MIN_DROP_TRAVEL` (18 units ≈ 0.3mm) below the running peak
  **and** the key has been moving up for `REV_MIN_DOWN_SCANS` (3) consecutive
  scans (`down_scan_count`). Each key is sampled once per scan (~500µs), so 3
  scans ≈ 1.5ms. The old single-sample, 3-unit threshold caught noise.
- **Note re-arm hysteresis** — after a note fires (`armed` cleared), it cannot
  fire again until the key recedes by `max(50% of actuation, 0.5mm)` from the
  actuation point, or returns to rest. `REARM_MIN_RECEDE_DIST` (32, 0-255
  scale) is the floor in `process_rapid_trigger()` (modes 0 & 2 via
  `is_pressed`); `REARM_MIN_RECEDE_TRAVEL` (30, 0-240 scale) is the floor in
  `process_midi_key_analog()` (modes 1 & 3 via `armed`). For a 3mm actuation
  the 50% term (1.5mm) dominates; for sub-1mm actuations the 0.5mm floor does.

---

## Aftertouch Modes (matrix.c ~line 1850)

| Mode | Name | Formula | Sustain Suppression |
|------|------|---------|-------------------|
| 0 | Off | None | - |
| 1 | Bottom-out | `travel * 127 / 240` | Yes |
| 2 | Bottom-out (NS) | `travel * 127 / 240` | No |
| 3 | Reverse | `127 - (travel * 127 / 240)` | Yes |
| 4 | Reverse (NS) | `127 - (travel * 127 / 240)` | No |
| 5 | Post-actuation | `extra_travel * 127 / (240 - actuation)` | Yes |
| 6 | Post-actuation (NS) | Same | No |
| 7 | Vibrato | Leaky integrator of travel deltas | Yes |
| 8 | Vibrato (NS) | Same | No |

When aftertouch is active, the retrigger byte is repurposed as smoothness (0-100%) which acts as a slew rate limiter.

---

## Per-Key Configuration

### Full Structure (8 bytes, EEPROM/HID)
```
actuation (0-255, default 127 = 2.0mm)
deadzone_top (0-51, default 6)
deadzone_bottom (0-51, default 6)
velocity_curve (0-16: 0-6 factory, 7-16 user)
flags (bit 0: RT enabled, bit 1: per-key velocity, bit 2: continuous RT)
rapidfire_press_sens (0-100, default 6)
rapidfire_release_sens (0-100, default 6)
rapidfire_velocity_mod (-64 to +64, default 0)
```

### Optimized Cache (6 bytes, RAM - `per_key_config_lite_t`)
```
actuation, rt_down, rt_up, flags, dz_bottom, dz_top
```
70 keys x 6 bytes = 420 bytes per layer, fits in L1 cache.

---

## Drum Machine / Step Sequencer Buttons

The drum machine buttons are the `SEQ_PRESET` keycodes starting at **`0xED98`**
(`SEQ_PRESET_BASE`). The handler accepts 88 keycodes (`0xED98`–`0xEDEF`), but the
first **20** (`0xED98`–`0xEDAB`) are the persistent **factory seq / drum machine
slots** (`MAX_FACTORY_SEQ_SLOTS = 20`); buttons 20–87 are factory/user step-seq
presets. Each drum slot has its own config (`factory_seq_config_t`): pattern,
channel, velocity curve, humanize, and 12 `voice_notes` + `voice_velocities`.

- **Tap** an unconfigured drum slot → opens the genre/config menu
  (`drum_machine_open_menu()`). (Previously fell through to `seq_select_preset()`
  which played factory step-seq preset 0 — the "C Major Scale" — hence the old
  "plays a chromatic scale" bug. Fixed in `orthomidi5x14.c` tap handler.)
- **Hold** (2s) → opens the genre/config menu (pauses any running pattern first).

### Global "Drum Settings" (default channel + voice bindings)

`factory_seq_global_defaults` (12 notes + 12 velocities) is the global default
drum-voice map, and `factory_seq_default_channel` (uint8_t, default 9 = ch 10,
EEPROM `FACTORY_SEQ_DEFAULT_CHANNEL_ADDR = 59502`) is the global default channel.

- **Default channel:** changing it forces **ALL** 20 drum slots to that channel
  (`factory_seq_set_default_channel()` / `factory_seq_apply_default_channel_to_all()`).
- **Voice bindings (linked):** a drum slot whose bindings still **exactly match**
  the global default is "uncustomized" and follows changes to the default;
  manually-edited slots keep their own bindings (whole-set match).
- Firmware helpers (`seq_drum_patterns.c`): `factory_seq_capture_follow_snapshot()`,
  `factory_seq_push_global_to_followers()`, `factory_seq_set_global_bindings()`
  (linked set + save), `factory_seq_reset_all_bindings()` (reset all slots +
  global bindings + channel to GM factory + save).
- **OLED:** Settings menu (`0xCA24`) → "Drum Settings" (`SM_LEVEL_DRUM_KEYBINDS`),
  a field list with "Def Channel" + 12 note/velocity pairs + "Reset ALL to
  default". Follow-snapshot captured on entry; EEPROM saved once on exit
  (`sm_drum_kb_save_if_dirty`).
- **GUI:** MIDI Settings → "Drum Settings" tab
  (`MIDIswitchSettingsConfigurator.setup_drum_keybinds_tab`).
- **HID:** `0xE9` get / `0xEA` set / `0xEF` reset (former EQ command bytes,
  routed to `raw_hid_receive_kb`). Payload/response: bytes 6–17 = 12 notes,
  18–29 = 12 velocities, byte 30 = default channel. For `0xEA`, `data[4]`
  selects the sub-mode: 0 = bindings (linked), 1 = default channel (`data[6]`),
  2 = 16 extra DrumLIVE voicing notes (`data[6..21]`). `0xE9` GET with `data[4]=2`
  returns the 16 extra notes; `0xEF` reset also restores the extras (no new
  command byte — extras live inside the existing drum family).

### DrumLIVE v2 (live drum note filter) — `drum_live.c/.h`

Filter on the outgoing note-on path (`midi_send_noteon` hook). 18 targets (6
categories + 12 voices), each On / Off / Quiet (-50%) / Loud (+50%); per-voice
overrides category. `drum_live_edit[]` (menu/keycodes) commits to
`drum_live_active[]` (filter) — sync-aware, deferring to the next loop boundary
(`drum_live_on_loop_boundary` from `dynamic_macro_handle_loop_trigger`) when seq
sync mode is on and something is playing. OLED `SM_LEVEL_DRUM_LIVE` =
Presets/Basic/Advanced (+ Set All) and, while authoring a QB master, **Toggles**.
**34 targets**: 6 categories + 12 voices + 16 extra voicings (each
voice/extra-voicing overrides its category). Keycodes `0xF140–0xF183` (cat+voice
only). A QB-master DrumLIVE button is either a **SNAPSHOT** (Preset / Basic+Done /
Advanced+Done — full 34-mode state) or a **TOGGLE** (one category cycled by a
toggle type: On/Off, Articulation = On/Quiet/Loud, All = On/Off/Quiet/Loud).
Configs stored per sub-slot at `DL_QB_EEPROM_BASE` (61600, magic 0xDB07, 64×37).
Tap a SNAPSHOT master = apply/clear (overrides toggles); tap a TOGGLE master =
advance that category one step reading the live state (so toggles stack).
**Double-tap** an On/Off toggle = solo its category (others Off); double-tap a
soloed one = un-solo (all On). Articulation/All toggles ignore double-tap. Extra
GM voicings `drum_live_extra_notes[16]` (notes-only) at `DL_EXTRA_EEPROM_BASE`
(64000, magic 0xDB06); Learn captures the next outgoing note-on. Drum Settings
menu = Channel / Preset Layout / Custom Layout (per-voice Note/Velocity/Learn).
**Tap** activates, **hold** re-opens the menu to edit; ESC there opens a deferred
"Re-Bind Button?" confirm (Yes = picker, No/ESC = keep). When any ACTIVE target
is filtered, `collect_feature_boxes()`/`feature_box_count()` show a red "DLive"
status box (`FBOX_ID_DRUMLIVE`, via `drum_live_is_filtering()`).

### Settings menu (0xCA24) list label width

Value-less list rows (main menu, Advanced, Save/Load, pickers) render the label
across the full width (cols 1–20, up to 20 chars) via `sm_format_row` —
field-list rows that show a value still cap the label at `SM_LABEL_MAX` (14) so
the value column stays aligned.

## Loop QuickBuild Master (per-loop menu + Copy)

The QB-master picker has a **"Loop"** category (`MM_TOP_LOOP` → categories
`MM_CAT_LOOP` = 19, `MM_CAT_LOOP_HOLD` = 20 in `arpeggiator.c`). The on-device
picker is two-level:

- **Loop 1–8** — assign the loop's record/play keycode (`0xCC08-0B` / `0xCC79-7C`,
  `mm_slots_loop[]`). A configured Loop master **taps** to record/play and
  **holds 1 s** to open the per-loop settings menu (it no longer clears on hold —
  Clear lives in the menu). Decided in `process_record_user` (swallows the press,
  defers the toggle to a quick release via `dynamic_macro_loop_qb_tap`) +
  `matrix_scan_user` (opens the menu at `LOOP_MASTER_HOLD_MS`). ESC out of the
  menu runs the post-esc hook → "Re-Bind Key?"; confirming **Yes** also runs
  `dynamic_macro_clear_loop` on the loop that master points to (same full reset
  as the menu's "Clear" / holding the loop keycode) before opening the picker.
- **Hold Buttons** (sub-picker) — Loop 1–8 **Modifier** (`0xCC18-1B`/`0xCC89-8C`),
  **Overdub** (`0xCC15`), **Mute** (`0xCC10`) (`mm_slots_loop_hold[]`). These are
  momentary keys that fall through to fire normally; assigning one first shows a
  **HOLD-key warning** (`QUICK_BUILD_MASTER_LOOP_HOLD_WARN`). Rebinding needs a
  **tap-then-hold** gesture (tracked by `lh_*` statics; `matrix_scan_user` opens
  the Re-Bind confirm at `LOOP_HOLD_REBIND_MS`).

### Per-loop settings menu (`SM_LEVEL_LOOP_QB`, modeled on `SM_LEVEL_QBFN`)

`loop_qb_settings_open(loop_num)` opens it; `sm_loopqb_num` is the active loop.
Rows: **Clear** (→ `SM_LEVEL_LOOP_QB_CLEAR` confirm → `dynamic_macro_clear_loop`),
**Velocity Curve** (`SM_FT_LOOP_VCURVE`, full preset list incl. USER via
`next_configured_curve`; Linear shown as **"Normal"**), **Transpose**
(`SM_FT_LOOP_TRANSPOSE`, ±36), **Force Channel** (`SM_FT_LOOP_CHANNEL`,
Off/1–16), **Octave Double** (`SM_FT_LOOP_OCTAVE`, Off/+1/+2/−1 oct),
**Clear All Mods** (`reset_macro_transformations`), **Copy** (→
`SM_LEVEL_LOOP_QB_COPY`: pick Loop 1–8, `dynamic_macro_copy_loop` copies content
+ mods, overwrites, no auto-play), **Global Loop** (→ `SM_LEVEL_LOOP_QB_GLOBAL`),
**Done**.

### Global Loop Settings (`SM_LEVEL_LOOP_QB_GLOBAL`)

Shared (not per-loop) settings reached from the per-loop menu: **Sync Mode**
(`unsynced_mode_active` 0–5), **Thruloop** (`loop_messaging_enabled`), **Sample
Mode** (`sample_mode_active`), **CC/AT Recording** (`cclooprecording` 0–3),
**Live Note Prio** (`macro_override_live_notes`), **Reset Default**, **Done**.
They edit the live keyboard-settings globals (active immediately) and are
persisted to **settings slot 0** on exit (Done/ESC) via
`sm_loopqb_global_save_to_slot0` (`sm_copy_globals_to_struct` +
`save_keyboard_settings_to_slot(0)`).

All modifiers are **volatile** (RAM only, reset on power cycle / Clear) — they
drive the existing looper transforms (`set_macro_transpose_target`,
`set_macro_channel_absolute_target`, `set_macro_octave_doubler_target`,
`set_macro_recording_curve_target`) applied live in the TIM5 playback worker. The
velocity-curve ceiling in `set_macro_recording_curve_target` was widened from 16
to `CURVE_USER_END` (56) so all configured user presets are reachable.

`dynamic_macro_clear_loop` / `dynamic_macro_copy_loop` / `dynamic_macro_loop_qb_tap`
live in `process_dynamic_macro.c`. `copy_loop` is the shared body the on-keyboard
Copy button (paste path) now also calls; it additionally carries velocity
curve/min/max so the menu's "content + mods" copy is complete. (No EEPROM/GUI
changes — assignment is on-device via the existing `QB_MASTER_N` keycodes.)

## CC QuickBuild Master (CC / Bank / Program + per-button channel)

The QB-master picker has a **"CC"** category (`MM_TOP_CC` → `MM_CAT_CC` = 21).
Unlike slot-indexed categories, a CC master's target is a full 16-bit keycode
(CC value = 16384 combos) + a per-button MIDI channel override, so it can't fit
the 1-byte slot. Instead `cc_master_cfg[QB_MASTER_COUNT]` = `{uint16 keycode,
uint8 channel}` (own EEPROM region `CC_MASTER_EEPROM_BASE` 64018, magic 0xCC01),
indexed by QB master id; `qb_master[id].category = MM_CAT_CC` marks it and
`qb_master_target_keycode` special-cases it to return `cc_master_cfg[id].keycode`.

### Sub-picker + build wizard (`arpeggiator.c`)

"CC" opens `QUICK_BUILD_MASTER_CC_SUBMENU`: **CC** / **CC Up** / **CC Down** /
**CC Toggle** / **CC Multi-Tog** / **CC Hold** / **Bank** / **Program**.
Bank/Program open their own sub-pickers (LSB/MSB/Up/Down,
Value/Up/Down). Each leaf runs a small multi-page wizard (`cc_build_*` in
`arpeggiator.c`): a generic 0-127 number page (`QUICK_BUILD_MASTER_CC_NUMBER`,
encoder scroll **or** type digits via layer-0 number keys — fed by
`quick_build_master_cc_feed_digit` from `process_record_user`), chained per type
and ending in a Channel page (`QUICK_BUILD_MASTER_CC_CHANNEL`, Master / 1-16).
`cc_build_resolve_keycode` maps `{type, cc, value}` → keycode (CC value
`0x8180+cc*128+val`, up `0x8080+cc`, down `0x8100+cc`, toggle `0x8000+cc`, hold
= touch dial `0xC961+cc`, bank LSB `0xC200+val` / MSB `0xC180+val` / up `0xC301`
/ down `0xC302`, program `0xC280+val` / up `0xC303` / down `0xC304`).

**CC Multi-Toggle** (`cc_multitoggle_author_and_commit` in `orthomidi5x14.c`):
pick a toggle slot (`QUICK_BUILD_MASTER_CC_TOGSLOT`, all 100, CONFIGURED markers
via `toggle_slot_configured`) → #toggles (1-8) → CC# (1-127) → N value pages →
Channel → name editor (`oled_naming`, default `Toggle CC<nn>`, first keystroke
clears it via `oled_naming_arm_replace`). Authors the toggle slot as a multi-key
cycle of N CC-value keycodes on one CC# (N==1 stores 2 identical steps since the
multi-key player clamps to ≥2), sets its `CN_CAT_TOGGLE` name, and points the
master at `TOGGLE_KEY_BASE+slot`. The name editor is rendered/committed/cancelled
through the quick-build OLED takeover (glue in `process_record_user`).

CC Hold (touch dial, momentary) shows a HOLD-key warning
(`QUICK_BUILD_MASTER_CC_HOLD_WARN`) before committing. **Rebind** for every CC
master = **tap-then-hold** (`cc_rebind_*` tracking → `quick_build_open_master_confirm`,
mirrors the loop Hold-Buttons), then rebuild via the picker (channel/value are
not edited in place).

### Dispatch + channel override (`process_record_user`)

A configured CC master falls through to fire `cc_master_cfg[id].keycode`. The
per-button channel override uses the "Hold Channel" pattern: on press, if
`channel != 0` save `channel_number` and force it to `channel-1` (0-15); restore
on release. This also covers the touch-dial's held encoder turns. All CC keycodes
send on the (overridden) `channel_number`.

## QB-master rebind model (menu "Rebind Key" row; ESC just closes)

Rebinding a configured QB master is moving to an explicit **"Rebind Key"** row on
each master's settings menu (→ the existing "Re-Bind Key?" confirm via
`qb_master_rebind_from_menu()`), replacing the old "ESC opens the rebind confirm"
behavior. **Stage 1 (done):**

- **ESC just closes** for categories that have the row (gated by
  `qb_master_menu_has_rebind_row()` at the central ESC handler in
  `process_record_user`): arp/seq/delay/dynchord/fader/loop/CC.
- **"Rebind Key" row** added to the `sm_field` menus: QBFN
  (`sm_qbfn_fields`, delay/dynchord/fader + scratch arp/seq), per-loop
  (`sm_loopqb_fields`), and a new minimal **`SM_LEVEL_QB_INFO`** menu
  (Info title + Rebind Key + Done) via shared action `sm_rebind_key_action`.
- **Gesture changes:** Arp/Seq preset masters and **non-touch-dial CC** masters
  now **hold → open the minimal menu** (`qbinfo_hold_*`; the tap still fires the
  preset/CC via fall-through). **Touch-dial CC** (`0xC961-0xC9E0`, momentary)
  uses **tap-then-hold** (`cc_rebind_*` repurposed to open the menu, not the
  confirm directly). `cc_master_is_touch_dial()` distinguishes them.

**Stage 2 (done for 4 of 5):** the bespoke menus now carry their own "Rebind
Key" row and are in `qb_master_menu_has_rebind_row` (ESC just closes):
- **SmartChord** `vl_menu`: `VL_ROW_REBIND` (root level, master ctx only).
- **Rhythm** `cprog_menu`: `CPROG_LANDING_REBIND` on the landing page.
- **Ear Trainer**: 3rd row on the `ET_SETUP_MODE` setup root.
- **Drum Machine** `genre_menu`: "Rebind Key" appended after the genres on
  level 0 (index `GENRE_MENU_TOP_GENRES + genre_count`).

Each bespoke menu's ESC routes through the central handler (`cprog_menu_back`,
`ear_trainer_esc`, `vl_menu_esc`, inline genre close), so the same
`has_rebind_row` gate makes ESC just-close (clearing the invocation only once
the menu fully closes).

**DrumLIVE** is the fifth and is handled specially because its
`SM_LEVEL_DRUM_LIVE` chooser is shared between the QB-master capture flow and the
global Settings DrumLIVE editor, and it tracks its master in `sm_dl_reedit_master`
(it deliberately clears the shared invocation tag in the master-hold handler).
So the "Rebind Key" row is added **conditionally** (only when
`sm_dl_reedit_master != 0xFF`, i.e. re-editing a configured master) via
`sm_drumlive_rebind_action`, and the old deferred ESC rebind
(`sm_dl_pending_rebind`) is removed so ESC just cancels+closes. No
`has_rebind_row` entry is needed for DrumLIVE because the cleared tag already
makes the central `post_esc_hook` a no-op for it.

## QB-master slot picker (choose slot instead of auto-assign)

Selecting a slot-indexed category (Arp/Seq/Delay/Smartchord-Custom/Dynchord/
Drum/Ear, and the BT Chord/Bass/Lead banks) now opens a generic slot picker
(`QUICK_BUILD_MASTER_SLOT_PICKER`, `arpeggiator.c`) instead of auto-grabbing the
first free slot. Each row shows `Slot N` + **CFG** (configured) + **BND** (bound
to another master). `qb_slot_is_configured()` maps each category to its data
flag (`quick_build_state.has_saved_*_build[]` for arp/seq/delay/chord/dynchord;
`factory_seq_configs[slot].pattern_index != 0xFFFF` for drum; Ear/BT show BND
only). `qb_slot_is_bound()` scans `qb_master[]`. Picking a **configured** slot
just binds to it (no overwrite); an **empty** slot drops into its setup screen.
Fader and Smartchord-default keycodes keep their existing dedicated pickers;
DrumLIVE still auto-assigns its snapshot slot. ESC returns to the top menu (cursor
on the category) or the BT/SC sub-picker it came from (`mm_slotpick_return_mode`).

### Rhythm Engine (replaces the BT Chord/Bass/Lead picker)

The old "Backing Track" sub-picker (3 banks of 8/6/6) is replaced in the on-device
picker by one **"Rhythm Engine"** category — a *virtual* category `MM_CAT_RHYTHM`
(22, like CC: not a `master_menu_categories[]` entry) covering all 20 cprog slots
(slot i → keycode `CPROG_SLOT_BASE+i`). Each slot's type (**Chords / Arp / Bass /
Lead**) is its own stored `cprog_slot_config_t.rhythm_layer`, set in the config
menu — the keycode only selects the slot, and the action bar already reads the
type from the slot. The slot picker shows `Slot N <Type>` (+ BND); clicking always
opens `cprog_open_menu(slot)` (cprog slots always have a default progression, so
the menu doubles as setup + edit). Legacy BT categories 7/8/9 stay defined so any
existing assignments still resolve; the GUI keeps the raw cprog keycodes.
`qb_cat_slot_count()` returns 20 for the virtual category.

### Delay: Factory / Custom (48 + 50 real slots, replaces the 4-slot QB delay)

Clicking **Delay** opens a **Factory / Custom** chooser (`QUICK_BUILD_MASTER_DELAY_SUBMENU`).
Both are virtual categories over the real delay slots (`DELAY_SLOT_BASE+slot`):
**`MM_CAT_DELAY_FACTORY`** (23, 48 read-only presets, slot i → `0xEF90+i`) and
**`MM_CAT_DELAY_CUSTOM`** (24, 50 user slots, slot i → `0xEF90+48+i`). The slot
picker names rows via `get_delay_slot_name()` (factory: "1/4 Note Short" etc.;
custom: "User Delay N" + `*` if built). Factory = bind only (read-only); Custom =
build wizard on an empty slot (the old `quick_build_start_delay`, clamp lifted
4→`DELAY_USER_SLOT_COUNT`), bind if already built. A delay master **taps** to
toggle its slot (`midi_delay_toggle_slot`) and **holds** to edit (Custom →
`qb_function_settings_open(QBFN_DELAY, slot)`) or rebind (Factory). The legacy
4 QB-delay keycodes / category 2 stay defined for back-compat; `has_saved_delay_build[]`
and `delay_active[]` grew to 50. The GUI keeps the raw delay keycodes.

## Arp/Seq QB: Factory + User preset slots (persist via the EEPROM user pool)

Arp QB → **Factory / User** chooser (`QUICK_BUILD_MASTER_ARP_SUBMENU`); Seq QB →
straight to the **User** slot picker (no factory). Virtual categories (like
Rhythm/CC/Delay): `MM_CAT_ARP_FACTORY` (25, 48 read-only → `ARP_PRESET_BASE+id`),
`MM_CAT_ARP_USER` (26, 40 → `ARP_PRESET_BASE+48+i`), `MM_CAT_SEQ_USER` (27, 40 →
`SEQ_PRESET_BASE+48+i`). QB and user/factory presets share the **identical 3-byte
`arp_preset_note_t`** note format, so building into an empty User slot serializes
the QB pool (`pool_preset_t` + `note_pool`) into a fixed `arp_preset_t`/`seq_preset_t`
(`qb_save_arp_to_user`/`qb_save_seq_to_user` in `quick_build_finish`, via
`qb_user_save_slot`) and saves it with `arp_save_preset_to_eeprom` /
`seq_save_preset_to_eeprom` — so it **persists across power-cycle and appears in the
GUI**. The User slot picker shows configured (`*`) + a **"Space: N notes free"**
footer from `arp_seq_pool_free()` (the shared ~11,692-byte EEPROM user pool, capped
at 64 arp / 128 seq notes per preset). **Factory** masters fire the preset on tap
and **hold** → minimal Info/Rebind menu (`SM_LEVEL_QB_INFO`, `qbinfo_hold`).
Legacy cats 0/1 (the 4 arp / 8 seq QB keycodes) stay for back-compat; GUI keycodes
unchanged.

### User-slot edit menu + gestures (leverage QB to author the 40 user slots)

The 40 user arp / 40 user seq EEPROM slots are full quick-build slots that
save/load to EEPROM. The on-device **edit menu** reuses the QBFN settings menu via
two features `QBFN_ARP_USER` / `QBFN_SEQ_USER` (`qbfn_is_user()`), which edit the
pool **directory** entry (`arp_pool_dir`/`seq_pool_dir`) in **RAM** for live
preview and persist **once on exit** (save-on-exit, Done *or* ESC, via
`sm_qbfn_user_save_on_exit` → `arp_user_preset_flush`/`seq_user_preset_flush`).

- **Rows:** arp = Mode / Sync / Rate / Gate; seq = Rate / Gate; both add **Clear**,
  **Clear and Rebuild** (`sm_qbfn_clear_rebuild`), Rebind Key, Done.
- **Rate** (`note_value`+`timing_mode`) and **Gate** (`gate_length_percent`) live
  in the dir entry. **Mode/Sync** (arp only, `arp_mode_t` 0-4 encoding both) is
  stored in the dir's spare byte `pool_dir_entry_t.reserved` — zero EEPROM cost,
  no migration (`reserved==0` → Single Synced). `arp_user_preset_get_mode/set_mode`.
  `arp_start` applies a user preset's stored mode on playback (previously user
  presets inherited the global mode).
- **Gestures** (user masters, `uaseq_hold` tracker, separate from `qbinfo_hold`):
  tap a **configured** slot = play; tap an **empty/cleared** slot = enter the build
  flowchart (`qb_user_slot_build`); **hold** = rich edit menu (configured) or a slim
  **Build / Rebind / Done** menu (empty, `SM_LEVEL_USER_ASEQ_EMPTY`). "configured"
  = `qb_slot_is_configured` (`note_count > 0`).
- **Clear** empties the EEPROM preset (`arp_clear_preset`/`seq_clear_preset`) so the
  bound master taps into the flowchart afterwards; **Clear and Rebuild** wipes then
  drops straight into the flowchart for the same slot.
- **GUI parity:** `SET_PRESET`/`GET_PRESET` carry the arp mode in **params[8]**
  (`arpeggiator_hid.c`); `SAVE_PRESET` applies it via `arp_user_preset_set_mode`
  (staged in `hid_edit_arp_mode`). The GUI Mode dropdown now persists per user
  preset (save sends it; load restores it with signals blocked so it doesn't fire
  a live `SET_MODE`). `SET_MODE` (0xCC) still works for live preview.

## Zone System

Three independent zones for split keyboard configurations:
- **ZONE_TYPE_BASE (0):** Main zone (MI_* keycodes)
- **ZONE_TYPE_KEYSPLIT (1):** Left/right split (MI_SPLIT_* keycodes, 0xC600-0xC647)
- **ZONE_TYPE_TRIPLESPLIT (2):** Three zones (MI_SPLIT2_* keycodes, 0xC670-0xC6B7)

Each zone can have independent velocity curves, actuation overrides, retrigger distances, and speed/peak blend ratios. Controlled by `keysplitvelocitystatus`: 0=all same, 1=keysplit only, 2=triplesplit only, 3=both.

---

## GUI: Velocity Curve Editor (widgets/curve_editor.py)

- 300x300 canvas with 10x10 grid
- 4 draggable control points connected by polyline
- Points 0 and 3 are x-constrained (x=0 and x=255)
- X axis: input (time/travel), Y axis: output (velocity)
- Factory curves: Softest, Soft, Linear, Hard, Hardest, Aggro, Digital (indices 0-6)
- User curves: 10 slots (indices 7-16)
- Current labels: 0%/100% at corners

## GUI: Preset Settings Layout (editor/velocity_tab.py ~line 1005)

Two side-by-side boxes:
- **Presets list** (left): `maxWidth(180)`, contains scrollable list of factory + user presets
- **Preset Settings** (right): Contains zone tabs with embedded curve editors + controls

---

## Bugs Fixed in This Session

### 1. Instant Upward Rest Recalibration (Root Cause of 0.1-0.2mm Residual)
**File:** `matrix.c` line 952
**Problem:** When ADC drifted "away from pressed" (upward for inverted Hall sensors), `adc_rest_value` was updated **instantly** with no stability wait. Random ADC spikes of 20-30 units were immediately locked in as the new rest, creating a persistent gap between calibrated rest and actual rest.
**Fix:** Both drift directions now require the 5-second stability wait (`AUTO_CALIB_VALID_RELEASE_TIME`).

### 2. `last_travel` Overwrite in Velocity Modes 1, 2, 3
**File:** `matrix.c` lines ~1389, ~1483, ~1618
**Problem:** On release, each mode set `state->last_travel = 0`, but the unconditional `state->last_travel = travel` at the bottom of each case block immediately overwrote it with the residual travel value. The `last_travel == 0 && travel > 0` speed timer gate could never fire on the next press.
**Fix:** Wrapped `state->last_travel = travel` in an `else` branch so it's skipped on the same cycle as the release reset.

### 3. Distance Dead Zone at Rest
**File:** `matrix.c` line ~2202
**Problem:** 1-2 ADC unit noise produced distance 1-3 (non-zero) at rest, even with correct calibration.
**Fix:** Added `if (key->distance <= 3) key->distance = 0` after `adc_to_distance()`. Eliminates ~0.05mm noise residuals.

---

## Shared Loop Pool System (process_dynamic_macro.c)

### Overview
The loop pedal's 4 loop slots share a single 80KB memory pool (`loop_pool[]`) instead of fixed 20KB-per-slot allocations. This allows a user to record a small loop 1 and use the freed space for a much larger loop 2.

### Architecture
```
loop_pool[LOOP_POOL_EVENTS]  (80KB total = 10,240 events)
├── [slot A main+overdub]     ← variable size
├── [slot B main+overdub]     ← variable size
└── [free space]              ← available for new recordings/growth
```

Each slot has a `loop_pool_header_t` tracking:
- `pool_offset_events` — start position in the pool
- `pool_capacity_events` — allocated capacity
- `allocated` — whether the slot has space

### Pool Operations
| Operation | When | Behavior |
|-----------|------|----------|
| `loop_pool_alloc` | Recording start, HID load | Bump allocator, grabs all available space |
| `loop_pool_trim` | After recording ends | Shrinks to used + overdub headroom |
| `loop_pool_free` | Loop clear/delete | Marks slot as freed, sets compaction flag |
| `loop_pool_compact` | Opportunistically (scan loop), on clear | Slides allocations down to fill gaps |
| `loop_pool_grow` | Overdub merge overflow | Extends in-place or relocates to end |

### Safety Guarantees — ISR-Lock Protocol
Compaction and relocation are safe **even while loops are playing**. The TIM5 ISR (1kHz) drives playback by reading pointers from `macro_playback[i]` and `overdub_playback[i]`. The existing lock mechanism (`lt_macro_locked[i]` / `lt_overdub_locked[i]`) makes the ISR skip a slot while locked.

**Relocation protocol (used by both compact and grow):**
1. **Copy** data to new pool location (old data still valid — ISR reads it safely)
2. **Lock** the slot's ISR processing (both macro and overdub)
3. **Update** all pointers: `macro_ends`, `overdub_buffers/ends`, and all 6 playback state pointers (`buffer_start`, `current`, `end` for both main and overdub)
4. **Unlock** — ISR resumes using updated pointers at the new location

The lock window is only the pointer updates (~nanoseconds). The ISR misses at most 1 tick (~1ms), which is imperceptible for MIDI playback.

- **Compaction while playing:** `loop_pool_compact()` slides allocations down to fill gaps from freed slots, locking each slot individually during its pointer update.
- **Overdub growth while playing:** `loop_pool_grow()` extends in-place (if at end of pool) or relocates to the end using the lock protocol. No need to stop playback.
- **No lag:** Recording always gets all remaining pool space upfront, then trims after. Overdub temp events still use backwards-write within the slot's allocation.

### Incremental Overdub Insert

Overdub events are inserted **directly** into the permanent overdub buffer as they are recorded — no temp buffer, no batch merge.

- **INDEPENDENT mode:** Append at end (events arrive chronologically)
- **SYNCED mode:** Binary search + memmove to insert in timestamp-sorted order
- **Capacity:** `overdub_ensure_capacity()` calls `loop_pool_grow()` on demand. No fixed limit.
- **ISR safety:** ISR is locked during the memmove + pointer update (~microseconds). The ISR's `current` pointer is adjusted if it falls in the shifted range.
- **Removed:** `overdub_temp_count`, backwards-write temp buffer, `merge_overdub_buffer`, `auto_segment_overdub_if_needed`, `process_pending_overdub_merge` (all no-ops or dead code)

### Capacity Examples
| Scenario | Old (Fixed) | New (Shared) |
|----------|-------------|--------------|
| 1 loop, 3 empty | 20KB max | ~80KB max |
| 2 equal loops | 20KB each | ~40KB each |
| 1 tiny + 1 large | 20KB each | ~2KB + ~78KB |
| 4 equal loops | 20KB each | ~20KB each |

---

## EEPROM Memory Map

Hardware: **CAT24C512** external I2C EEPROM (`EEPROM_I2C_CAT24C512`) = **64 KB**,
usable 0–65535. (The `WEAR_LEVELING_*` defines in config.h are vestigial/unused.)

Audited + de-overlapped 2026-06 (see "EEPROM de-overlap" below).

| Address | Size | Content |
|---------|------|---------|
| 0-4508 | ~4.5 KB | QMK/VIA base (keymap, encoders, combos, key overrides) |
| 4509-20000 | ~15 KB | VIA text macros (`DYNAMIC_KEYMAP_EEPROM_MAX_ADDR`) |
| 21000-21359 | 360 bytes | Null-bind / SOCD (`NULLBIND_EEPROM_ADDR`) |
| 22000-22399 | 400 bytes | Toggle-key config (`TOGGLE_EEPROM_ADDR`) |
| 23000-35339 | 12,340 bytes | Arp/Seq preset pool (header 8B + arp dir 320B + seq dir 320B + note pool ~11,692B) |
| 36000-36749 | 750 bytes | Custom animations (50 × 15B) |
| 37000-37199 | 200 bytes | Loop settings (`LOOP_SETTINGS_EEPROM_ADDR`) |
| 37200-37827 | 628 bytes | Factory-seq (drum-slot) configs (`FACTORY_SEQ_EEPROM_ADDR`, moved from 59500) |
| 38000-38249 | 5 x 250 bytes | Keyboard settings (5 slots, `SETTINGS_BASE_ADDR`) |
| 38500 | 2 bytes | RGB defaults magic |
| 39000-39107 | 108 bytes | Layer RGB settings |
| 39108-39791 | 684 bytes | Factory-seq chains (`FACTORY_SEQ_CHAIN_EEPROM_ADDR`, moved from 60128) |
| 40000-40059 | 60 bytes | Layer actuation settings (deprecated) |
| 40100-40301 | 202 bytes | Factory-arp QB-master rate/gate (magic 0xAE01 + 100×2: rate index 0-9 + gate % 0/5-100, `ARP_MASTER_RG_EEPROM_BASE`) |
| 40500-42501 | 2,002 bytes | User velocity curves (50 × 40 + magic) |
| 42600-42699 | 100 bytes | Gaming settings (`GAMING_SETTINGS_EEPROM_ADDR`) |
| 42800-42825 | 26 bytes | EQ curve (legacy, unused after sensor swap) |
| 42826-42987 | 162 bytes | User step-seq modifiers (magic 0x5A01 + 40×4: channel/transpose/curve/octave, `USEQ_MODS_EEPROM_BASE`) |
| 43000-43889 | 890 bytes | Per-key RGB (`PER_KEY_RGB_EEPROM_ADDR`) |
| 44000-44801 | 802 bytes | Delay settings (50 user × 16 + magic, `DELAY_EEPROM_ADDR`) |
| 45000-51719 | 6,720 bytes | Per-key actuations (70 x 8 x 12 layers) |
| 52000-53603 | 1,604 bytes | DKS configurations (`EEPROM_DKS_BASE`) |
| 54000-55401 | 1,402 bytes | Toggle multi-key keycodes |
| 56000-60273 | 4,274 bytes | Custom names (OLED display names for macros/arp/seq/delay/toggles/**layers**). Magic 0x4E41 @56000; macros 56002, arp 56402, seq 57042, delay 57682, toggle 58482, layer 60082. |
| 60274-60811 | 538 bytes | Free (was Factory-seq chains, relocated to 39108) |
| 60812-61051 | 240 bytes | Ear trainer (`ET_EEPROM_BASE`, moved from 60284) |
| 61052-61055 | 4 bytes | DAW selection (magic 0xDA01 + index + os, `EEPROM_DAW_BASE`, moved from 60280) |
| 61100-61541 | 442 bytes | QB fader configs (40 x 11B, magic 0xFA01) |
| 61600-63969 | 2,370 bytes | DrumLIVE QB-master configs (magic 0xDB07 + 64×37) |
| 64000-64017 | 18 bytes | DrumLIVE extra-voicing notes (magic 0xDB06 + 16 notes) |
| 64018-64319 | 302 bytes | CC QB-master configs (magic 0xCC01 + 100×3) |
| 64320-64721 | 402 bytes | Functional LED config (`FUNC_LED_EEPROM_ADDR`, moved from 60274) |
| 64722-65023 | 302 bytes | QB master slot assignments (magic 0xDB04 + 100×3, moved from 60524) |
| 65024-65247 | 224 bytes | Chord progression slots (`CPROG_EEPROM_ADDR`, moved from 60800) |
| 65248-65263 | 16 bytes | Voice leading config (`VL_EEPROM_BASE`, moved from 60900) |
| 65264-65405 | 142 bytes | Custom smartchord QB (magic 0x5C14 + 20 × 7: count + 6 intervals, `SMARTCHORD_EEPROM_BASE`) |
| 65406-65407 | 2 bytes | LCD theme (magic 0x7C + index, `LCD_THEME_EEPROM_BASE`) |
| 65408-65426 | 19 bytes | Channel Articulations (`CHANNEL_ARTIC_EEPROM_BASE`: magic 0xCB + enable + 16-ch map + Articulation CC) |
| 65428-65429 | 2 bytes | Curve-index migration marker (`CURVE_MIGRATION_MAGIC_ADDR`, word 0xCA11; moved from 65410 — it overlapped the channel-artic map there) |
| 65430-65527 | 98 bytes | Free |
| 65528-65535 | 8 bytes | Boot-magic shadow (`EECONFIG_MAGIC_SHADOW_ADDR`) |

### EEPROM de-overlap (2026-06)

The cluster 59,500–61,024 had **seven live, mutually-overlapping regions**:
factory-seq-chain had grown to 60,811 (after `CHAIN_MAX_BEATS` 8→16, but its END
marker still used ×33), and func-LED (60,274–60,675), DAW (60,280), ear-trainer
(60,284–60,523), QB-master (60,524–60,825), CPROG (60,800–61,023) and
voice-leading (60,900–60,915) all stomped each other. This corrupted data on
every save — notably func-LED saves overwriting QB-master assignments, which is
why QB-master targets didn't survive power cycles. All six non-chain regions
were relocated to clean addresses above 60,812 / in the top free block; the
chain END marker was corrected to ×34. Each relocated region reinitializes to
defaults once on the first boot after this change (magic-mismatch at the new
address). The factory-seq/chain regions stayed put (chain now correctly sized).

### Layer-name corruption fix — custom-names vs factory-seq overlap (2026-06)

The custom-names region (`CN_EEPROM_BASE` 56000) was budgeted 3,442 bytes but
`CN_TOGGLE_COUNT` grew 48→100, pushing the real layout to **4,274 bytes** (ends
60273): toggle names 58482–60081, layer names **60082–60273** — directly on top
of the factory-seq drum configs (59500–60127) and chains (60128–60811). Every
layer-name save corrupted factory-seq data and vice versa. **Fix:** relocated
both factory-seq regions out of the custom-names footprint — drum configs
59500→**37200** (ends 37827), chains 60128→**39108** (ends 39791); magic bumped
to force a clean one-time re-init. Custom names now own 56000–60273 with no
overlap; 60274–60811 is free. (One-time first-boot effect: drum-slot configs +
chains reset to GM defaults; previously-corrupt layer/high-toggle names must be
re-entered.)

## EMA Filter Status

**ACTIVE** (2026-07): a light **3-sample EMA** (`MATRIX_EMA_ALPHA_EXPONENT 1`,
alpha = 1/2 → effective window N = 2/alpha − 1 = 3):
```c
key->adc_filtered = (uint16_t)EMA(raw_value, key->adc_filtered);  // (raw + prev) / 2
```
- Applied only to **calibrated** keys; uncalibrated keys pass raw so the (#24)
  late-seed stability check sees the true sensor (`seed_key_calibration()`
  re-seeds `adc_filtered` from the validated rest sample).
- **Latency:** step response 50%/75%/87.5% after 1/2/3 scans; group delay ≈ 1
  scan ≈ **0.5-1ms** added to threshold crossings — imperceptible for MIDI.
- The previous alpha = 1/16 (exponent 4) filter was bypassed because it lagged
  ~16 scans (≈8ms). The raw-ADC anti-jitter guards (reversal confirm, re-arm
  hysteresis, threshold-mode retrigger band) are **kept** as defense in depth.

---

## Scan Cycle Performance Optimizations

Tracked efficiency improvements to the firmware scan loop. Each scan processes 70 keys (5 rows × 14 columns).

| # | Optimization | Savings Estimate | Scope | Status |
|---|-------------|-----------------|-------|--------|
| 0 | **OLED update throttle:** Set `OLED_UPDATE_INTERVAL` ~5ms in `config.h` or use `OLED_UPDATE_PROCESS_LIMIT` to prevent OLED redraws from stalling every scan cycle | 1 stall avoided per scan | 1 line in `config.h` | **TODO** |
| 1 | **Reduce mux settle time:** Lower ADC mux settle delay from 40µs → 10µs | ~420µs/scan (47% of mux overhead) | 1 line | **TODO** |
| 2 | **Precomputed inverse range for distance calc:** Cache `(1023 << 16) / (rest - bottom)` in `key_state_t.inv_range`, recompute only on calibration change. Hot path uses multiply+shift instead of division. Also replaced `(n * 255) / 1023` with `(n * 255 + 512) >> 10` | ~30µs/scan (eliminates 70+ divisions) | `matrix.c`, `distance_lut.h` | **DONE** |
| 3 | **Skip LUT/blend for idle keys:** Early return from `adc_to_distance_corrected()` when `normalized == 0` (key at rest), bypasses LUT lookup + blend math | ~50-60 calls skipped/scan | `distance_lut.h` | **DONE** |
| 4 | **Remove dead normal-orientation path:** Deleted unreachable `rest < bottom_out` branch from `adc_to_distance_corrected()` — Hall sensors are always inverted. Smaller inlined footprint improves icache | Reduced code size | `distance_lut.h` | **DONE** |

### Implementation Details

**#2 — Inverse range cache:**
- `key_state_t` gained `uint32_t inv_range` field
- `update_inv_range(key)` called from: `matrix_init_custom()`, warm-up init, `update_calibration()` (both rest and bottom-out paths), and both reset functions
- Normalization: `(rest - adc) * inv_range >> 16` replaces `(rest - adc) * 1023 / (rest - bottom)`

**#3 — EQ skip:**
- Inserted `if (normalized == 0) return 0;` before `apply_eq_curve_adjustment()` call
- `apply_eq_curve_adjustment()` contains loops, quadratic blending, cumulative boundaries — ~30+ arithmetic ops per call
- Typical typing: ~50-60 of 70 keys idle at any moment

---

## Stop Mode (GUI, MIDI Settings tab) — per-function Mute/Stop

The firmware's per-function **Stop Mode** (bitmask `loop_stop_mode`, one bit per
transport family; **bit clear = Mute, DEFAULT** / bit set = Stop) is exposed in
the MIDI Settings tab as its own **"Stop Mode" group** (mirroring the on-device
Advanced Settings > Stop Mode menu):

- **Instant Start** — the pre-existing combo, MOVED here from the Loop Settings
  group (same `self.instant_loop_start` widget; still rides advanced packet 2
  byte 8). It dictates whether the mute/stop toggles resolve on the key press
  or defer to the loop trigger.
- **Loop / ThruLoop / Step Sequencer / Drum Machine / Rhythm Engine** — one
  `Mute`/`Stop` combo each (`self.stop_mode_combos`, keyed by the firmware
  `STOP_MODE_*` bit; class constants `STOP_MODE_LOOP=0x01, THRULOOP=0x02,
  SEQ=0x04, DRUM=0x08, CPROG=0x10` on `MIDIswitchSettingsConfigurator`).

**HID:** the mask rides keyboard-config **packet 1 payload offset 20** (the old
reserved/`overdub_advanced_mode` byte, formerly the hidden always-0
`smart_chord_light` widget — that widget is now removed) as **`0x80 | mask`** in
BOTH directions. Bit 7 is the validity/feature-detect marker:

- **GET** (`get_midi_config`): byte 20 parses to `stop_mode_supported`
  (bit 7) + `stop_mode` (low 5 bits). Old firmware sends 0 → the 5 combos are
  shown all-Mute and **disabled** (`_apply_stop_mode`).
- **SET/save** (`pack_basic_data`): packs `0x80 | mask` when supported, else 0
  — the firmware ignores the byte without bit 7, so a legacy GUI (or this GUI
  talking to a pre-detect state) can never reset the on-device setting.
- Applied on the normal "Save Settings" flow (slot save `0xB9` routes through
  the same firmware parser); the firmware persists on-device edits to slot 0
  itself, so "Load Active Settings" round-trips it.

## LCD Theme (GUI, MIDI Settings > Advanced grid)

**LCD Theme** combo (Orange / Matrix Green / White / Light Blue — keep in sync
with `lcd_themes[]` in the firmware) + the renamed **Virtual Instrument** combo
(formerly "OLED Keyboard"; Keyboard 1/2/3 + Guitar Low/Med/High). The theme is
a global setting with its own EEPROM region, carried over the dedicated HID
command `HID_CMD_LCD_THEME = 0xFE` (`data[4]` 0=GET/1=SET, `data[6]`=index;
response status@4, index@5, count@6) via `keyboard_comm.get_lcd_theme()` /
`set_lcd_theme()` — it applies + persists instantly on change (not part of the
per-slot settings packet). `apply_settings` fetches it on every config load.

---

## Articulation / AT-CC bugfix round (2026-07) — GUI side

- **GUI shows AT/CC preset settings (velocity_tab.py):** new `_ATCC_ART_PARAMS`
  + `atcc_zone_settings()` mirror the firmware `atcc_mode_zones[]` table
  (display-only; keep in sync with the firmware `ART_*` macros). Selecting or
  loading an enabled AT/CC preset now populates the settings panel (aftertouch
  mode/CC, vibrato, smoothness, legato, curve points) instead of leaving stale
  "Off" values.
- **Channel Articulations tab:** edits (enable + 16 dropdowns) are now local
  until the tab's own single **Save** button pushes them to the device; the
  preset New/Save/Save As/Export row moved INTO the Preset Settings tab so it no
  longer shows under Channel Articulations. Firmware side now applies the
  current channel's mapping immediately on a HID SET (previously only on a
  channel transition). Enable defaults to OFF.
- **Articulation dropdowns:** channel-articulation combos are ArrowComboBox
  (editable/read-only lineEdit, centered, `setMaxVisibleItems(15)` scrollable
  popup) at 220px; keymap Articulation combos widened (70→140 / 120→180). The
  preset list separators and the channel dropdowns carry greyed non-selectable
  dividers "User Articulations" / "CC Articulations" / "AT Articulations"
  (`_fill_artic_combo` disables divider rows).
- **Legato semantics (matches firmware):** with the sustain pedal down a
  released legato note keeps ringing until ANOTHER key is pressed; tooltip
  updated.
