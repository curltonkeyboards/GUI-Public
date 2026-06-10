# Rapid Trigger & Per-Key Actuation Implementation Plan

## Overview
Implementing advanced HE keyboard features: per-key rapid trigger, deadzones, and velocity curves.

---

## PHASE 1: DATA STRUCTURE CHANGES ✅ COMPLETED

### 1.1 Define New Per-Key Structure (process_midi.h)
- [x] Define `per_key_actuation_t` structure (8 bytes per key)
  - `uint8_t actuation` (0-100 = 0-2.5mm)
  - `uint8_t deadzone_top` (0-100 = 0-2.5mm, max 0.5mm)
  - `uint8_t deadzone_bottom` (0-100 = 0-2.5mm, max 0.5mm)
  - `uint8_t velocity_curve` (0-4: SOFTEST to HARDEST)
  - `uint8_t rapidfire_enabled` (0=off, 1=on)
  - `uint8_t rapidfire_press_sens` (0-100 = 0-2.5mm)
  - `uint8_t rapidfire_release_sens` (0-100 = 0-2.5mm)
  - `int8_t rapidfire_velocity_mod` (-64 to +64)

- [ ] Update `layer_key_actuations_t` to use new structure
  - Change from `uint8_t actuation[70]` to `per_key_actuation_t keys[70]`
  - Total: 8 bytes × 70 keys × 12 layers = 6,720 bytes

### 1.2 Remove Deprecated Fields
- [ ] From `layer_actuations[12]`:
  - Remove `midi_rapidfire_sensitivity`
  - Remove `midi_rapidfire_velocity`
  - Remove `rapidfire_sensitivity`
  - Remove `LAYER_ACTUATION_FLAG_MIDI_RAPIDFIRE_ENABLED` flag
  - Remove `LAYER_ACTUATION_FLAG_RAPIDFIRE_ENABLED` flag
  - KEEP `normal_actuation`, `midi_actuation`, `velocity_mode`, `velocity_speed_scale`

- [ ] From `keyboard_settings_t`:
  - Remove `keysplit_he_velocity_curve`
  - Remove `triplesplit_he_velocity_curve`
  - KEEP all velocity min/max fields

### 1.3 Update EEPROM Addresses
- [ ] Calculate new EEPROM size for per_key_actuations (6,720 bytes)
- [ ] Update EEPROM address definitions in process_dynamic_macro.h
- [ ] Update per_key_mode_enabled flag storage

---

## PHASE 2: MATRIX & RAPIDFIRE LOGIC ✓/✗

### 2.1 Update analog_key_t Structure (matrix.c)
- [ ] Add rapidfire state tracking:
  - `uint8_t base_velocity` (stored first-press velocity)
  - `bool rapid_cycle_active` (flag for RT mode)
  - `bool awaiting_release` (flag: waiting for release_sens)
  - `uint8_t last_direction` (0=none, 1=up, 2=down)

### 2.2 Implement Deadzone Logic
- [ ] Add `calculate_active_range()` function
  - Top deadzone: Ignore travel < deadzone_top
  - Bottom deadzone: Ignore travel > (max_travel - deadzone_bottom)
  - Return active travel range

- [ ] Update key state machine to apply deadzones before processing

### 2.3 Implement Per-Key Rapid Trigger
- [ ] Update `process_midi_key_analog()` to:
  - Read per-key RT settings from `per_key_actuations[layer][key_index]`
  - Implement RT state machine:
    1. **Initial Press**: Travel crosses actuation point → ACTUATE (calculate velocity, store as base)
    2. **Awaiting Release**: Set `awaiting_release = true`, require release by `rapidfire_release_sens`
    3. **Release Detected**: Travel decreased by ≥ release_sens → set `awaiting_release = false`
    4. **Re-trigger**: Travel increased by ≥ press_sens (after release) → ACTUATE (velocity = base + mod, update base)
  - Apply deadzones: Disable RT in top/bottom deadzones
  - Accumulate velocity: `new_velocity = base_velocity + rapidfire_velocity_mod`
  - Clamp velocity to 1-127

- [ ] Remove old MIDI-specific rapidfire code (lines 484-516)

### 2.4 Update Key Actuation Point Retrieval
- [ ] Modify `get_key_actuation_point()` to:
  - If `per_key_mode_enabled == false`: Return layer-wide `midi_actuation`
  - If `per_key_mode_enabled == true`: Return `per_key_actuations[layer][key_index].actuation`

---

## PHASE 3: VELOCITY CALCULATION ✓/✗

### 3.1 Update get_he_velocity_from_position()
- [ ] Modify to read per-key curve when `per_key_mode_enabled == true`:
  ```c
  uint8_t layer = get_highest_layer(layer_state);
  uint8_t key_index = row * 14 + col;
  uint8_t curve = per_key_actuations[layer].keys[key_index].velocity_curve;
  ```
- [ ] Keep global `keyboard_settings.he_velocity_min/max`
- [ ] Apply per-key curve to travel value

### 3.2 Update get_keysplit_he_velocity_from_position()
- [ ] Change curve source:
  ```c
  uint8_t layer = get_highest_layer(layer_state);
  uint8_t key_index = row * 14 + col;
  uint8_t curve = per_key_actuations[layer].keys[key_index].velocity_curve;
  ```
- [ ] KEEP `keyboard_settings.keysplit_he_velocity_min/max`

### 3.3 Update get_triplesplit_he_velocity_from_position()
- [ ] Change curve source (same as keysplit):
  ```c
  uint8_t curve = per_key_actuations[layer].keys[key_index].velocity_curve;
  ```
- [ ] KEEP `keyboard_settings.triplesplit_he_velocity_min/max`

### 3.4 Handle per_key_mode_enabled Flag
- [ ] Add fallback logic for when per_key_mode is disabled:
  - Read curve from layer_actuations (need to add velocity_curve field back?)
  - OR use global keyboard_settings.he_velocity_curve
  - **CLARIFICATION NEEDED**: Where should curve come from when per_key_mode = false?

---

## PHASE 4: PERSISTENCE & EEPROM ✓/✗

### 4.1 Initialize Per-Key Defaults
- [ ] Update `initialize_per_key_actuations()`:
  ```c
  actuation: 60              // 1.5mm
  deadzone_top: 4            // 0.1mm
  deadzone_bottom: 4         // 0.1mm
  velocity_curve: 2          // MEDIUM
  rapidfire_enabled: 0       // Off
  rapidfire_press_sens: 4    // 0.1mm
  rapidfire_release_sens: 4  // 0.1mm
  rapidfire_velocity_mod: 0  // No offset
  ```

### 4.2 EEPROM Save/Load
- [ ] Update `save_per_key_actuations()` for new structure size
- [ ] Update `load_per_key_actuations()` for new structure size
- [ ] Implement migration: Detect old structure, convert to new defaults

### 4.3 Reset Functions
- [ ] Update `reset_per_key_actuations()` to use new defaults
- [ ] Update `reset_layer_actuations()` to remove deprecated fields

---

## PHASE 5: HID PROTOCOL ✓/✗

### 5.1 Update HID Commands (vial.c)
- [ ] `handle_set_per_key_actuation()`: Update to receive 8 bytes per key
- [ ] `handle_get_per_key_actuation()`: Update to send 8 bytes per key
- [ ] Update layer actuation HID to remove rapidfire fields

### 5.2 Update Layer Actuation Structure
- [ ] Modify `set_layer_actuation()` signature (remove rapid params)
- [ ] Modify `get_layer_actuation()` signature (remove rapid params)
- [ ] Update HID packet sizes

---

## PHASE 6: PYTHON GUI UPDATES ✓/✗

### 6.1 Remove Deprecated UI Elements
- [ ] Remove keysplit velocity curve selector
- [ ] Remove triplesplit velocity curve selector
- [ ] Remove MIDI rapidfire toggle from layer settings
- [ ] Remove MIDI rapidfire sensitivity slider

### 6.2 Add Per-Key Controls
- [ ] Add per-key deadzone top slider (0-20 = 0-0.5mm)
- [ ] Add per-key deadzone bottom slider (0-20 = 0-0.5mm)
- [ ] Add per-key velocity curve dropdown (5 options)
- [ ] Add per-key rapidfire enable checkbox
- [ ] Add per-key rapidfire press sensitivity slider (0-100)
- [ ] Add per-key rapidfire release sensitivity slider (0-100)
- [ ] Add per-key rapidfire velocity modifier slider (-64 to +64)

### 6.3 Update Communication Protocol
- [ ] Update `keyboard_comm.py` for new per-key structure (8 bytes)
- [ ] Update layer actuation packet parsing (remove rapid fields)
- [ ] Update keyboard settings packet (remove keysplit/triplesplit curves)

### 6.4 Add "Set All Keys" Helper
- [ ] Button to copy current key settings to all 70 keys
- [ ] Confirmation dialog for bulk operations

---

## VALIDATION CHECKLIST ✓/✗

- [ ] Normal actuation works without per-key mode
- [ ] Per-key actuation works with per_key_mode_enabled
- [ ] Top deadzone prevents ghost triggers (0-0.1mm)
- [ ] Bottom deadzone prevents wobble (3.7-4.0mm)
- [ ] Rapid trigger requires release THEN press
- [ ] Velocity accumulates correctly (100→95→90→85)
- [ ] Velocity clamps at 1-127
- [ ] Keysplit uses per-key curve + keysplit min/max
- [ ] Triplesplit uses per-key curve + triplesplit min/max
- [ ] EEPROM save/load preserves all 8 fields
- [ ] GUI displays all new controls correctly

---

## IMPORTANT NOTES

**Encoding Scale (All use 0-100 = 0-2.5mm):**
- actuation: 60 = 1.5mm
- deadzone_top: 4 = 0.1mm
- deadzone_bottom: 4 = 0.1mm
- rapidfire_press_sens: 4 = 0.1mm
- rapidfire_release_sens: 4 = 0.1mm

**Rapidfire State Machine:**
1. Initial actuation at actuation_point (e.g., 1.5mm)
2. Set awaiting_release = true
3. Monitor for release: travel decreases by ≥ release_sens
4. Set awaiting_release = false
5. Monitor for press: travel increases by ≥ press_sens
6. Re-trigger: velocity = base + mod, update base
7. Repeat from step 2

**Deadzones Disable RT:**
- If travel < deadzone_top: RT inactive
- If travel > (max_travel - deadzone_bottom): RT inactive

**Velocity Curve Fallback:**
- per_key_mode_enabled = true: Use per_key_actuations[layer][key].velocity_curve
- per_key_mode_enabled = false: Use ??? (layer setting or global?)
  - **TODO: Add velocity_curve to layer_actuations OR use global keyboard_settings.he_velocity_curve**

---

## FILES TO MODIFY

### Firmware (C):
1. `vial-qmk - ryzen/quantum/process_keycode/process_midi.h`
2. `vial-qmk - ryzen/quantum/process_keycode/process_midi.c`
3. `vial-qmk - ryzen/quantum/matrix.c`
4. `vial-qmk - ryzen/keyboards/orthomidi5x14/orthomidi5x14.c`
5. `vial-qmk - ryzen/quantum/process_keycode/process_dynamic_macro.h`
6. `vial-qmk - ryzen/quantum/vial.c`

### GUI (Python):
7. `src/main/python/protocol/keyboard_comm.py`
8. `src/main/python/editor/trigger_settings.py` (or equivalent UI file)

---

## OPEN QUESTIONS

1. **Velocity curve when per_key_mode_enabled = false:**
   - Should we add `velocity_curve` field to `layer_actuations[12]`?
   - OR use global `keyboard_settings.he_velocity_curve`?
   - **DECISION NEEDED**

