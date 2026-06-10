# libhmk Architecture Migration Changelog

## Overview

This document describes the architectural migration of the orthomidi5x14 Hall Effect keyboard firmware from its original architecture to a cleaner, libhmk-inspired architecture.

## Summary of Changes

| Component | Before | After |
|-----------|--------|-------|
| Key Storage | 2D arrays `keys[ROWS][COLS]` | Flat array `key_matrix[NUM_KEYS]` |
| ADC Filtering | None (raw values) | EMA low-pass filter |
| RT States | 4+ states with dynamic thresholds | Clean 3-state FSM |
| RT Tracking | `rapid.actn_pt` + `rapid.deactn_pt` | Single `extremum` value |
| Calibration | Separate array, manual save | Integrated, auto-save after inactivity |
| Per-key Mode | Optional via `per_key_mode_enabled` | Always enabled |

---

## Data Structure Changes

### Old: Separate Structures
```c
// Old architecture had separate arrays
static analog_key_t  keys[MATRIX_ROWS][MATRIX_COLS];
static calibration_t calibration[MATRIX_ROWS][MATRIX_COLS];
static midi_key_state_t midi_key_states[MATRIX_ROWS][MATRIX_COLS];
```

### New: Unified Flat Array
```c
// New architecture uses single flat array
typedef struct {
    uint16_t adc_filtered;          // EMA-filtered ADC value
    uint16_t adc_rest_value;        // Calibrated rest position
    uint16_t adc_bottom_out_value;  // Calibrated bottom-out position
    uint8_t distance;               // 0-255 scale (libhmk style)
    uint8_t extremum;               // Peak/trough for RT
    key_dir_t key_dir;              // 3-state direction
    bool is_pressed;                // Logical pressed state
    bool calibrated;                // Calibration status
    uint8_t base_velocity;          // For MIDI RT velocity
    // ... calibration tracking fields
} key_state_t;

static key_state_t key_matrix[NUM_KEYS];  // NUM_KEYS = 70
```

### Benefits
- **Cache Efficiency**: Single contiguous memory block for all key data
- **Simpler Iteration**: Single flat loop instead of nested row/col loops
- **Unified State**: All key information in one place

---

## EMA Filtering

### What Changed
Added Exponential Moving Average (EMA) filtering to ADC readings for noise reduction.

### Implementation
```c
#define MATRIX_EMA_ALPHA_EXPONENT 4  // alpha = 1/16
#define EMA(x, y) \
    (((uint32_t)(x) + ((uint32_t)(y) * ((1 << MATRIX_EMA_ALPHA_EXPONENT) - 1))) >> \
     MATRIX_EMA_ALPHA_EXPONENT)

// Usage in scan loop:
key->adc_filtered = EMA(raw_value, key->adc_filtered);
```

### Effect on Features
- **Actuation Detection**: More stable, less prone to false triggers from noise
- **MIDI Velocity**: Smoother speed calculations, less jitter
- **Calibration**: More reliable rest/bottom-out detection
- **RT Response**: Slightly smoothed but still responsive (alpha = 0.0625)

---

## Rapid Trigger State Machine

### Old: 4+ States with Dynamic Thresholds
```c
// Old states
enum { AKS_REGULAR_RELEASED, AKS_REGULAR_PRESSED,
       AKS_RAPID_RELEASED, AKS_RAPID_PRESSED };

// Old tracking - constantly updated thresholds
key->rapid.actn_pt = key->travel;
key->rapid.deactn_pt = key->travel - key->rpd_trig_sen_release;
```

### New: Clean 3-State FSM with Single Extremum
```c
typedef enum {
    KEY_DIR_INACTIVE = 0,  // Key at rest or below actuation
    KEY_DIR_DOWN     = 1,  // Key pressed, tracking deepest point
    KEY_DIR_UP       = 2   // Key released by RT, tracking highest point
} key_dir_t;

// Single extremum value tracks peak (DOWN) or trough (UP)
key->extremum = key->distance;
```

### State Transitions
```
                    ┌───────────────────────────┐
                    │    KEY_DIR_INACTIVE       │
                    │    is_pressed = false     │
                    └─────────────┬─────────────┘
                                  │
                    Press past actuation_point
                                  │
                                  ↓
                    ┌───────────────────────────┐
                    │      KEY_DIR_DOWN         │
                    │    is_pressed = true      │
                    │  extremum = deepest point │
                    └─────────────┬─────────────┘
                                  │
              ┌───────────────────┴───────────────────┐
              │                                       │
    Full release to               RT release: moved up
    reset_point                   by rt_up from extremum
              │                                       │
              ↓                                       ↓
    KEY_DIR_INACTIVE             ┌───────────────────────────┐
                                 │       KEY_DIR_UP          │
                                 │    is_pressed = false     │
                                 │ extremum = highest point  │
                                 └─────────────┬─────────────┘
                                               │
                       ┌───────────────────────┴─────────────┐
                       │                                     │
             Full release to                    RT re-press: moved down
             reset_point                        by rt_down from extremum
                       │                                     │
                       ↓                                     ↓
             KEY_DIR_INACTIVE                         KEY_DIR_DOWN
```

### Effect on Features
- **RT Behavior**: Identical functionality, cleaner implementation
- **Predictable Transitions**: No threshold juggling, just compare to extremum
- **Easier Debugging**: State is directly inspectable via `analog_matrix_get_key_direction()`

---

## Calibration System

### Old: Separate, Manual
```c
static calibration_t calibration[MATRIX_ROWS][MATRIX_COLS];
// Manual calibration tracking
// No auto-save
```

### New: Integrated, Continuous with Auto-Save
```c
// Integrated into key_state_t
uint16_t adc_rest_value;        // Auto-updates when stable
uint16_t adc_bottom_out_value;  // Auto-updates on deeper press

// Auto-save after inactivity
#define INACTIVITY_TIMEOUT_MS 3000
if (calibration_dirty && timer_elapsed(last_calibration_change) >= INACTIVITY_TIMEOUT_MS) {
    save_calibration_to_eeprom();
}
```

### Effect on Features
- **User Experience**: No manual calibration needed, keyboard self-calibrates
- **Persistence**: Calibration auto-saves after 3 seconds of no changes
- **Hall Effect Support**: Handles both normal and inverted ADC orientations

---

## Distance Scale Change

### Old: 0-240 Travel Units
```c
#define FULL_TRAVEL_UNIT 40
#define TRAVEL_SCALE 6
// Max travel = 40 * 6 = 240
```

### New: 0-255 Distance (with backward compatibility)
```c
#define DISTANCE_MAX 255

// Conversion for backward compatibility
static inline uint8_t distance_to_travel_compat(uint8_t distance) {
    return (uint8_t)(((uint32_t)distance * 240) / 255);
}
```

### Effect on Features
- **DKS**: Uses `distance_to_travel_compat()` - no change in behavior
- **MIDI Velocity**: Uses converted travel values - no change in behavior
- **Actuation Points**: Still use 0-100 scale, converted internally
- **New API**: `analog_matrix_get_distance()` returns 0-255

---

## Per-Key Actuation

### Old: Optional Mode Toggle
```c
extern bool per_key_mode_enabled;
extern bool per_key_per_layer_enabled;

if (!per_key_mode_enabled) {
    return layer_actuations[layer].midi_actuation;  // Global fallback
}
```

### New: Always Per-Key
```c
// Always use per-key settings (no more mode toggle)
uint8_t target_layer = per_key_per_layer_enabled ? layer : 0;
per_key_actuation_t *settings = &per_key_actuations[target_layer].keys[key_idx];
```

### Effect on Features
- **Per-Key Settings**: Always respected, no global override mode
- **Layer Awareness**: Still respects `per_key_per_layer_enabled` flag
- **Existing Configs**: Work unchanged via `per_key_actuations[]` arrays

---

## New Public API Functions

### Added Functions
```c
// Get key distance (0-255 scale, libhmk compatible)
uint8_t analog_matrix_get_distance(uint8_t row, uint8_t col);

// Get RT direction state (KEY_DIR_INACTIVE, KEY_DIR_DOWN, KEY_DIR_UP)
uint8_t analog_matrix_get_key_direction(uint8_t row, uint8_t col);

// Get RT extremum value (peak or trough being tracked)
uint8_t analog_matrix_get_extremum(uint8_t row, uint8_t col);

// Get EMA-filtered ADC value
uint16_t analog_matrix_get_filtered_adc(uint8_t row, uint8_t col);

// Refresh cached layer settings (call when layer actuations change)
void analog_matrix_refresh_settings(void);
```

### Unchanged Functions (Backward Compatible)
```c
uint8_t analog_matrix_get_travel(uint8_t row, uint8_t col);      // Returns 0-240
uint8_t analog_matrix_get_travel_normalized(uint8_t row, uint8_t col);  // Returns 0-255
bool analog_matrix_get_key_state(uint8_t row, uint8_t col);
uint16_t analog_matrix_get_raw_value(uint8_t row, uint8_t col);  // Now returns filtered
```

---

## Feature Compatibility Matrix

| Feature | Status | Notes |
|---------|--------|-------|
| Basic Key Press/Release | Working | Uses `key->is_pressed` |
| Rapid Trigger | Working | 3-state FSM with single extremum |
| RT Asymmetric (different press/release) | Working | Uses `rt_down` / `rt_up` from per-key settings |
| RT Continuous Mode | Working | Via reset_point configuration |
| MIDI Velocity Mode 0 (Fixed) | Working | Unchanged |
| MIDI Velocity Mode 1 (Peak) | Working | Uses converted travel values |
| MIDI Velocity Mode 2 (Speed) | Working | Uses EMA-filtered values |
| MIDI Velocity Mode 3 (Speed+Peak) | Working | Combination mode unchanged |
| Aftertouch (all 4 modes) | Working | Uses converted travel values |
| DKS (Dynamic Keystroke) | Working | Interface unchanged, uses converted travel |
| Per-Key Actuation | Working | Always enabled, respects layer settings |
| Auto-Calibration | Improved | Continuous with auto-save |
| EEPROM Persistence | Improved | Auto-save after inactivity |

---

## Memory Impact

### Before
```
analog_key_t:     ~20 bytes × 70 keys           = 1,400 bytes
calibration_t:    ~16 bytes × 70 keys           = 1,120 bytes
midi_key_state_t: ~20 bytes × 70 keys           = 1,400 bytes
                                          TOTAL ≈ 3,920 bytes (state only)
```

### After
```
key_state_t:      ~24 bytes × 70 keys           = 1,680 bytes
midi_key_state_t: ~24 bytes × 70 keys           = 1,680 bytes
                                          TOTAL ≈ 3,360 bytes (state only)
```

**Savings**: ~560 bytes (14% reduction in state memory)

---

## Migration Checklist for Developers

If you're extending this code, note these changes:

1. **Key Access Pattern**
   - Old: `keys[row][col]`
   - New: `key_matrix[KEY_INDEX(row, col)]`

2. **Travel Values**
   - Old: Direct `key->travel` (0-240)
   - New: `key->distance` (0-255) or `distance_to_travel_compat()` for old scale

3. **Pressed State**
   - Old: `key->state == AKS_REGULAR_PRESSED || key->state == AKS_RAPID_PRESSED`
   - New: `key->is_pressed`

4. **RT Direction**
   - Old: Derived from state and threshold comparisons
   - New: Explicit `key->key_dir` (KEY_DIR_INACTIVE/DOWN/UP)

5. **Calibration Access**
   - Old: `calibration[row][col].value.zero_travel`
   - New: `key_matrix[KEY_INDEX(row, col)].adc_rest_value`

---

## Files Modified

- `vial-qmk - ryzen/quantum/matrix.c` - Complete rewrite
- `vial-qmk - ryzen/quantum/matrix.h` - Added new API declarations and key_dir_t enum
