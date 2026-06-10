# Implementation Status - Rapid Trigger & Per-Key Actuation

## Summary

**Firmware Implementation: COMPLETE** ✅
**Python Communication Layer: COMPLETE** ✅
**Python UI Layer: PARTIAL** ⚠️ (Communication protocol complete, UI controls pending)

---

## Completed ✅

### Phase 1: Data Structures
**Files:** `process_midi.h`, `process_dynamic_macro.h`, `orthomidi5x14.h`

- ✅ Defined `per_key_actuation_t` structure (8 bytes per key):
  - `uint8_t actuation` (0-100 = 0-2.5mm)
  - `uint8_t deadzone_top` (0-100 = 0-2.5mm)
  - `uint8_t deadzone_bottom` (0-100 = 0-2.5mm)
  - `uint8_t velocity_curve` (0-4: SOFTEST to HARDEST)
  - `uint8_t rapidfire_enabled` (0=off, 1=on)
  - `uint8_t rapidfire_press_sens` (0-100 = 0-2.5mm)
  - `uint8_t rapidfire_release_sens` (0-100 = 0-2.5mm)
  - `int8_t rapidfire_velocity_mod` (-64 to +64)

- ✅ Updated `layer_key_actuations_t` to use new structure (70 keys × 12 layers = 6,720 bytes)

- ✅ Removed deprecated fields from `layer_actuation_t`:
  - Removed `rapidfire_sensitivity`
  - Removed `midi_rapidfire_sensitivity`
  - Removed `midi_rapidfire_velocity`
  - Removed `LAYER_ACTUATION_FLAG_RAPIDFIRE_ENABLED` flag
  - Removed `LAYER_ACTUATION_FLAG_MIDI_RAPIDFIRE_ENABLED` flag

- ✅ Added `LAYER_ACTUATION_FLAG_USE_PER_KEY_VELOCITY_CURVE` flag (bit 3)

- ✅ Removed `keysplit_he_velocity_curve` and `triplesplit_he_velocity_curve` from `keyboard_settings_t`

- ✅ Reorganized EEPROM layout:
  - Per-Key Actuation: 67000-73721 (6,722 bytes)
  - Layer Actuation: 74000-74059 (60 bytes)
  - Gaming Settings: 74100-74199 (100 bytes)

### Phase 2: Matrix.c Rapid Trigger Implementation
**File:** `matrix.c`

- ✅ Added per-key rapid trigger state to `analog_key_t`:
  - `uint8_t base_velocity` (stored first-press velocity)
  - `bool rapid_cycle_active` (flag for RT mode)
  - `bool awaiting_release` (flag: waiting for release_sens)
  - `uint8_t last_direction` (0=none, 1=up, 2=down)

- ✅ Updated `active_settings` cache (removed rapidfire fields)

- ✅ Added `is_in_deadzone()` helper function

- ✅ Implemented new per-key rapid trigger state machine in `process_midi_key_analog()`:
  1. Initial press: Travel crosses actuation → ACTUATE (calculate velocity, store as base)
  2. Awaiting release: Set `awaiting_release = true`
  3. Release detected: Travel decreased by ≥ `rapidfire_release_sens` → `awaiting_release = false`
  4. Re-trigger: After release, travel increased by ≥ `rapidfire_press_sens` → ACTUATE
  5. Velocity: `new_vel = base_velocity + rapidfire_velocity_mod` (accumulate and clamp 1-127)
  6. Deadzones: Disable RT when in top or bottom deadzone
  7. Full release: Reset state when travel < deadzone_top

- ✅ Deleted old rapid trigger code

### Phase 3: Velocity Calculation Functions
**File:** `orthomidi5x14.c`

- ✅ Added helper functions:
  - `layer_use_per_key_velocity_curve(uint8_t layer)` - checks flag bit 3
  - `get_key_velocity_curve(uint8_t layer, uint8_t row, uint8_t col)` - returns per-key or global curve

- ✅ Updated velocity functions to use per-key curves:
  - `get_he_velocity_from_position()` - uses per-key curve, keeps global min/max
  - `get_keysplit_he_velocity_from_position()` - uses per-key curve, keeps keysplit min/max
  - `get_triplesplit_he_velocity_from_position()` - uses per-key curve, keeps triplesplit min/max

- ✅ Fallback logic: When `use_per_key_velocity_curve` flag is OFF, uses global `keyboard_settings.he_velocity_curve`

### Phase 4: EEPROM & Persistence Functions
**Files:** `orthomidi5x14.c`, `process_midi.c`

- ✅ Updated `initialize_per_key_actuations()` to initialize all 8 fields with defaults:
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

- ✅ Updated `get_key_actuation_point()` to use new structure (`.keys[index].actuation`)

- ✅ Added `get_key_settings()` helper function to return pointer to per-key settings

- ✅ Updated layer actuation functions:
  - `set_layer_actuation()` - signature changed (removed 3 rapidfire params)
  - `get_layer_actuation()` - signature changed (removed 3 rapidfire params)
  - Removed `layer_rapidfire_enabled()` and `layer_midi_rapidfire_enabled()` helpers

- ✅ Updated `handle_set_layer_actuation()` to use 6-byte packet

### Phase 5: HID Protocol
**Files:** `vial.c`, `process_midi.h`, `process_dynamic_macro.c`

- ✅ Updated `handle_set_layer_actuation()`:
  - Packet format: 6 bytes `[layer, normal_actuation, midi_actuation, velocity_mode, velocity_speed_scale, flags]`
  - Updated packet size check in vial.c (≥ 8 bytes total with header)

- ✅ Updated `handle_get_layer_actuation()`:
  - Added `uint8_t* response` parameter to function signature
  - Returns 6 bytes: `[success, normal, midi, velocity_mode, vel_speed, flags]`
  - Updated declaration in `process_midi.h`
  - Updated weak implementation in `process_dynamic_macro.c`

- ✅ Updated `handle_set_per_key_actuation()`:
  - Packet format: 10 bytes `[layer, key_index, actuation, deadzone_top, deadzone_bottom, velocity_curve, rapidfire_enabled, rapidfire_press_sens, rapidfire_release_sens, rapidfire_velocity_mod]`
  - Changed from (layer, row, col, actuation) to (layer, key_index, 8 fields)
  - Updated packet size check in vial.c (≥ 12 bytes total with header)

- ✅ Updated `handle_get_per_key_actuation()`:
  - Changed input from (layer, row, col) to (layer, key_index)
  - Returns 8 bytes with all per-key fields
  - Updated packet size check in vial.c (≥ 4 bytes total with header)

### Phase 6: Python GUI (src/main/python/)

**Part 1: Communication Layer** - `keyboard_comm.py`
- ✅ Updated `set_layer_actuation()`:
  - New packet format: 6 bytes `[layer, normal_actuation, midi_actuation, velocity_mode, velocity_speed_scale, flags]`
  - Removed rapidfire parameters from docstring

- ✅ Updated `get_layer_actuation()`:
  - Parses 6-byte response (5 params + success)
  - Returns dict: `{normal, midi, velocity, vel_speed, use_per_key_velocity_curve}`
  - Removed rapidfire fields from returned dict

- ✅ Updated `set_per_key_actuation()`:
  - New signature: `set_per_key_actuation(self, layer, key_index, settings)`
  - Changed from (layer, row, col, actuation) to (layer, key_index, settings dict)
  - Sends 10-byte packet with all 8 per-key fields
  - Properly handles signed-to-unsigned conversion for `rapidfire_velocity_mod`

- ✅ Updated `get_per_key_actuation()`:
  - New signature: `get_per_key_actuation(self, layer, key_index)`
  - Changed from (layer, row, col) to (layer, key_index)
  - Parses 8-byte response with all per-key fields
  - Properly handles unsigned-to-signed conversion for `rapidfire_velocity_mod`

**Part 2: UI Layer** - `trigger_settings.py`
- ✅ Updated per_key_values cache: Changed from single values to dicts with 8 fields
- ✅ Updated layer_data cache: Removed rapidfire fields, added `use_per_key_velocity_curve`
- ✅ Deleted old layer-wide rapidfire UI (create_rapidfire_tab method)
- ✅ Created new per-key controls tab with all 8 fields:
  - Per-Key Actuation slider (0-100 = 0-2.5mm)
  - Velocity Curve dropdown (5 options)
  - Enable Deadzone checkbox
  - Top/Bottom Deadzone sliders (greyed when disabled)
  - Enable Rapidfire checkbox
  - Rapidfire Press/Release Sens sliders (greyed when disabled)
  - Rapidfire Velocity Mod slider (greyed when disabled)
- ✅ Added layer-level "Use Per-Key Velocity Curve" checkbox (flag bit 3)
- ✅ Updated all handler methods for new controls
- ✅ Updated data management methods (copy, reset, rebuild, refresh)
- ✅ Updated device communication to use new packet formats

---

## Completed! ✅

**All phases (1-6) are now complete!**

The firmware and GUI now support full per-key configuration with:
- 8 per-key settings fields
- Deadzones to prevent ghost triggers and wobble
- Per-key rapid trigger with velocity accumulation
- Per-key velocity curves with global fallback
- Layer flag to toggle per-key vs global velocity curves

---

## Testing Checklist 📋

Firmware and GUI are complete. Verify functionality:

- [ ] Normal actuation works without per-key mode
- [ ] Per-key actuation works with `per_key_mode_enabled`
- [ ] Top deadzone prevents ghost triggers (0-0.1mm)
- [ ] Bottom deadzone prevents wobble (3.7-4.0mm)
- [ ] Rapid trigger requires release THEN press (state machine)
- [ ] Velocity accumulates correctly (e.g., 100→95→90→85 with mod=-5)
- [ ] Velocity clamps at 1-127
- [ ] Per-key velocity curves work when flag is enabled
- [ ] Global velocity curve used when flag is disabled
- [ ] Keysplit uses per-key curve + keysplit min/max
- [ ] Triplesplit uses per-key curve + triplesplit min/max
- [ ] EEPROM save/load preserves all 8 fields
- [ ] GUI displays all new controls correctly
- [ ] "Copy from Layer" button works
- [ ] "Copy to All Layers" button works
- [ ] Layer flag "Use Per-Key Velocity Curve" toggles correctly

---

## Technical Notes

**Encoding Scale (All use 0-100 = 0-2.5mm):**
- actuation: 60 = 1.5mm
- deadzone_top: 4 = 0.1mm
- deadzone_bottom: 4 = 0.1mm
- rapidfire_press_sens: 4 = 0.1mm
- rapidfire_release_sens: 4 = 0.1mm

**Internal Conversion:**
- `TRAVEL_SCALE = 6`
- `FULL_TRAVEL_UNIT = 40`
- Internal units: 0-240 (user 0-100 = 0-240 internally)

**Rapidfire State Machine:**
1. Initial actuation at actuation_point (e.g., 1.5mm)
2. Set `awaiting_release = true`
3. Monitor for release: travel decreases by ≥ release_sens
4. Set `awaiting_release = false`
5. Monitor for press: travel increases by ≥ press_sens
6. Re-trigger: velocity = base + mod, update base, clamp 1-127
7. Repeat from step 2

**Deadzones Disable RT:**
- If travel < deadzone_top: RT inactive, reset state
- If travel > (max_travel - deadzone_bottom): RT inactive

**Velocity Curve Fallback:**
- Flag enabled: Use `per_key_actuations[layer].keys[key].velocity_curve`
- Flag disabled: Use global `keyboard_settings.he_velocity_curve`

---

## Commits

All changes committed to branch `claude/add-rapid-trigger-feature-Hl76g`:

1. Phase 1: Data structure changes
2. Phase 2: Matrix.c rapid trigger implementation
3. Phase 3: Velocity calculation updates
4. Phase 4: EEPROM persistence updates
5. Phase 5: HID protocol updates
6. Phase 6 (Part 1): keyboard_comm.py updates
7. Phase 6 (Part 2): trigger_settings.py UI updates

**Implementation is 100% complete!**
