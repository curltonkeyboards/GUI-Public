# libhmk vs orthomidi5x14 Implementation Comparison
## Matrix Scanning, Efficiency, and DKS Analysis

This document compares the implementation approaches of **libhmk** (by peppapighs) with the **orthomidi5x14** firmware documented in our flowchart analyses.

---

## Table of Contents

1. [Matrix Scanning Architecture](#1-matrix-scanning-architecture)
2. [Efficiency Comparison](#2-efficiency-comparison)
3. [DKS Implementation Comparison](#3-dks-implementation-comparison)
4. [Key Design Philosophy Differences](#4-key-design-philosophy-differences)
5. [Technical Deep Dive](#5-technical-deep-dive)
6. [Summary & Recommendations](#6-summary--recommendations)

---

## 1. Matrix Scanning Architecture

### libhmk Approach

```
┌─────────────────────────────────────────────────────────────┐
│                    MAIN LOOP (main.c)                       │
│  while (1) {                                                │
│      tud_task();        // USB handling                     │
│      analog_task();     // ADC reading                      │
│      matrix_scan();     // Process all keys                 │
│      layout_task();     // Handle key events                │
│      xinput_task();     // Gamepad support                  │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
```

**Key Characteristics:**
- **Flat array structure**: `key_state_t key_matrix[NUM_KEYS]` - single dimension
- **Per-key actuation from profile**: `CURRENT_PROFILE.actuation_map[i]`
- **EMA filtering built-in**: `EMA(x, y)` macro for noise reduction
- **Dynamic calibration**: Continuous bottom-out threshold updates
- **Three-state direction tracking**: `KEY_DIR_INACTIVE`, `KEY_DIR_DOWN`, `KEY_DIR_UP`

```c
// libhmk matrix_scan core loop
for (uint32_t i = 0; i < NUM_KEYS; i++) {
    const uint16_t new_adc_filtered = EMA(matrix_analog_read(i), key_matrix[i].adc_filtered);
    const actuation_t *actuation = &CURRENT_PROFILE.actuation_map[i];

    key_matrix[i].adc_filtered = new_adc_filtered;
    key_matrix[i].distance = adc_to_distance(new_adc_filtered,
                                              key_matrix[i].adc_rest_value,
                                              key_matrix[i].adc_bottom_out_value);
    // ... state machine processing
}
```

### orthomidi5x14 Approach

```
┌─────────────────────────────────────────────────────────────┐
│                  matrix_scan_user() (QMK)                   │
│  for (row = 0; row < MATRIX_ROWS; row++) {                  │
│      for (col = 0; col < MATRIX_COLS; col++) {              │
│          travel = analog_matrix_get_travel_normalized()     │
│          actuation = get_key_actuation_point(layer, row, col)│
│          if (is_dks_keycode) → dks_process_key()            │
│          else → normal processing                           │
│      }                                                       │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
```

**Key Characteristics:**
- **2D matrix structure**: `analog_key_t keys[MATRIX_ROWS][MATRIX_COLS]`
- **Per-key or per-layer actuation**: Dual mode system with `per_key_mode_enabled` flag
- **Layer-aware actuation**: `get_key_actuation_point(layer, row, col)`
- **Separate DKS pathway**: Special handling for keycodes 0xED00-0xED31
- **MIDI integration**: Velocity curves, MIDI note processing

---

## 2. Efficiency Comparison

### Memory Layout

| Aspect | libhmk | orthomidi5x14 |
|--------|--------|---------------|
| **Key state array** | `key_state_t[NUM_KEYS]` (flat) | `analog_key_t[ROWS][COLS]` (2D) |
| **Actuation storage** | Per-profile: `actuation_map[NUM_KEYS]` | Dual: layer-wide OR per-key arrays |
| **State per key** | ~12 bytes (ADC, distance, direction, extremum) | ~6-8 bytes + 8 bytes if per-key mode |
| **DKS storage** | Part of `advanced_keys[]` array | Separate `dks_slots[50]` × 32 bytes |
| **Total DKS memory** | ~64 bytes per advanced key | 1,600 bytes (50 slots × 32) |

### Actuation Configuration Memory

```
libhmk actuation_t (4 bytes per key):
┌────────────────────────────────────────┐
│ actuation_point  │ rt_down   │ rt_up  │ continuous │
│     uint8_t      │  uint8_t  │ uint8_t│   bool     │
└────────────────────────────────────────┘

orthomidi5x14 per_key_actuation_t (8 bytes per key):
┌────────────────────────────────────────────────────────────────┐
│ actuation │ deadzone_top │ deadzone_bottom │ velocity_curve   │
│  uint8_t  │    uint8_t   │     uint8_t     │     uint8_t      │
├────────────────────────────────────────────────────────────────┤
│ flags │ rapidfire_press │ rapidfire_release │ rapidfire_vel_mod│
│uint8_t│     uint8_t     │      uint8_t      │      int8_t      │
└────────────────────────────────────────────────────────────────┘
```

### Scanning Efficiency

#### libhmk: O(n) Single Pass
```c
// Single loop over flat array
for (uint32_t i = 0; i < NUM_KEYS; i++) {
    // Direct array access - cache friendly
    key_matrix[i].adc_filtered = ...;
    actuation = &CURRENT_PROFILE.actuation_map[i];  // Direct lookup
    // State machine (switch statement)
}
```

**Advantages:**
- Cache-friendly linear memory access
- No conditional branching for actuation lookup
- Profile switching changes entire actuation map at once
- EMA filter is inline macro (no function call overhead)

#### orthomidi5x14: O(n) with Branching
```c
// Nested loops over 2D matrix
for (row = 0; row < MATRIX_ROWS; row++) {
    for (col = 0; col < MATRIX_COLS; col++) {
        // Multiple conditionals per key:
        if (!per_key_mode_enabled) {
            actuation = layer_actuations[layer].midi_actuation;
        } else {
            key_index = row * 14 + col;  // Index calculation
            if (per_key_per_layer_enabled) {
                actuation = per_key_actuations[layer].keys[key_index].actuation;
            } else {
                actuation = per_key_actuations[0].keys[key_index].actuation;
            }
        }

        // Additional DKS check
        if (is_dks_keycode(keycode)) {
            dks_process_key(...);
        }
    }
}
```

**Trade-offs:**
- More branch predictions per key
- Index calculation overhead
- Separate DKS code path
- However: More flexible (layer-aware, mode-switchable)

### Rapid Trigger Implementation Comparison

#### libhmk: Clean State Machine
```c
switch (key_matrix[i].key_dir) {
    case KEY_DIR_INACTIVE:
        if (distance > actuation_point) {
            key_dir = KEY_DIR_DOWN;
            is_pressed = true;
        }
        break;

    case KEY_DIR_DOWN:
        if (distance <= reset_point) {
            key_dir = KEY_DIR_INACTIVE;
            is_pressed = false;
        } else if (distance + rt_up < extremum) {
            key_dir = KEY_DIR_UP;
            is_pressed = false;
        } else if (distance > extremum) {
            extremum = distance;  // Update peak
        }
        break;

    case KEY_DIR_UP:
        if (distance <= reset_point) {
            key_dir = KEY_DIR_INACTIVE;
            is_pressed = false;
        } else if (extremum + rt_down < distance) {
            key_dir = KEY_DIR_DOWN;
            is_pressed = true;
        } else if (distance < extremum) {
            extremum = distance;  // Update trough
        }
        break;
}
```

**Design Pattern:** Explicit 3-state FSM with separate rt_down/rt_up sensitivities.

#### orthomidi5x14: Integrated with Per-Key Features
The orthomidi5x14 implementation includes rapidfire as part of the per-key structure, with additional features:
- `rapidfire_press_sens` and `rapidfire_release_sens`
- `rapidfire_velocity_mod` for MIDI velocity adjustment
- Per-key enable flag

---

## 3. DKS Implementation Comparison

### libhmk: "Dynamic Keystroke" (Simplified)

```c
// From advanced_keys.h
typedef struct {
    uint8_t keycodes[4];      // Up to 4 keycodes
    uint8_t actions;          // 8-bit bitmap for press/bottom-out/release behaviors
} dynamic_keystroke_t;

// Behavior flags (actions bitmap):
// Bit 0-1: Press action
// Bit 2-3: Bottom-out action
// Bit 4-5: Release from bottom-out action
// Bit 6-7: Release action
```

**Processing Flow:**
```
┌─────────────────────────────────────────────────────────────┐
│           libhmk Dynamic Keystroke                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Events:                                                    │
│  1. PRESS          → When first actuated                    │
│  2. BOTTOM_OUT     → When reaching bottom                   │
│  3. RELEASE_FROM_BOTTOM_OUT → When lifting from bottom      │
│  4. RELEASE        → When fully released                    │
│                                                             │
│  Each event can trigger 0-4 keycodes from the keycodes[]   │
│  array based on the actions bitmap                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Characteristics:**
- **4 keycodes maximum** per advanced key
- **4 events** (press, bottom-out, release-from-bottom, release)
- **Fixed thresholds**: Bottom-out is dynamically detected, not configurable
- **Simpler state machine**: Binary pressed/released with bottom-out detection
- **Memory efficient**: ~6 bytes per advanced key

### orthomidi5x14: Full DKS (Multi-Zone)

```c
// From DKS_complete_flowchart.md
typedef struct {
    uint16_t press_keycode[4];      // 4 press keycodes (8 bytes)
    uint8_t  press_actuation[4];    // 4 press thresholds (4 bytes)

    uint16_t release_keycode[4];    // 4 release keycodes (8 bytes)
    uint8_t  release_actuation[4];  // 4 release thresholds (4 bytes)

    uint16_t behaviors;             // Bit-packed TAP/PRESS/RELEASE (2 bytes)
    uint8_t  reserved[6];           // Padding (6 bytes)
} dks_slot_t;  // Total: 32 bytes
```

**Processing Flow:**
```
┌─────────────────────────────────────────────────────────────┐
│           orthomidi5x14 DKS                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Press Actions (downstroke):                                │
│  ├── Threshold 1 (e.g., 0.6mm) → Keycode 1                 │
│  ├── Threshold 2 (e.g., 1.2mm) → Keycode 2                 │
│  ├── Threshold 3 (e.g., 1.8mm) → Keycode 3                 │
│  └── Threshold 4 (e.g., 2.4mm) → Keycode 4                 │
│                                                             │
│  Release Actions (upstroke):                                │
│  ├── Threshold 1 (e.g., 2.4mm) → Keycode 5                 │
│  ├── Threshold 2 (e.g., 1.8mm) → Keycode 6                 │
│  ├── Threshold 3 (e.g., 1.2mm) → Keycode 7                 │
│  └── Threshold 4 (e.g., 0.6mm) → Keycode 8                 │
│                                                             │
│  Each action has: TAP, PRESS, or RELEASE behavior          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### DKS Feature Comparison

| Feature | libhmk Dynamic Keystroke | orthomidi5x14 DKS |
|---------|-------------------------|-------------------|
| **Max keycodes** | 4 | 8 (4 press + 4 release) |
| **Thresholds** | 2 (actuation + bottom-out) | 8 (4 configurable per direction) |
| **Threshold config** | Fixed (auto-detected) | Fully configurable (0-2.5mm) |
| **Behaviors** | Binary (on/off) | TAP/PRESS/RELEASE per action |
| **Direction aware** | Partial (events) | Full (separate press/release zones) |
| **Memory per slot** | ~6 bytes | 32 bytes |
| **Total slots** | Shared with other advanced keys | 50 dedicated slots |
| **MIDI support** | No | Yes (can send MIDI notes) |
| **State tracking** | Minimal | Full (triggered/active bitmasks) |

### DKS Processing Efficiency

#### libhmk
```c
void advanced_key_dynamic_keystroke(uint8_t key_idx, ak_event_type_t event) {
    // Single switch on event type
    switch (event) {
        case AK_EVENT_PRESS:
            // Register keycodes based on actions bitmap
            break;
        case AK_EVENT_BOTTOM_OUT:
            // Handle bottom-out action
            break;
        // ... etc
    }
}
```
- Called per-event (not per-scan)
- Simple bitmap-based keycode selection
- O(1) per event

#### orthomidi5x14
```c
void dks_process_key(uint8_t row, uint8_t col, uint8_t travel, uint16_t keycode) {
    // Called every scan cycle for each DKS key
    // Check all 4 press thresholds
    for (int i = 0; i < 4; i++) {
        if (crossed_threshold_going_down(i)) {
            trigger_action(press_keycode[i], behavior);
        }
    }
    // Check all 4 release thresholds
    for (int i = 0; i < 4; i++) {
        if (crossed_threshold_going_up(i)) {
            trigger_action(release_keycode[i], behavior);
        }
    }
}
```
- Called every scan cycle
- Checks 8 thresholds per cycle
- O(8) threshold comparisons per DKS key per scan

---

## 4. Key Design Philosophy Differences

### libhmk Philosophy: "Clean, Efficient, Modern"

1. **Flat data structures**: Single-dimension arrays for cache efficiency
2. **Profile-based configuration**: Switch entire configuration at once
3. **Minimal branching**: State machines over nested conditionals
4. **Dynamic calibration**: Self-adjusting rest/bottom-out values
5. **Hardware abstraction**: Clean separation between MCU-specific and generic code
6. **Integrated advanced keys**: Null-bind, Dynamic Keystroke, Tap-Hold, Toggle in unified system

### orthomidi5x14 Philosophy: "Feature-Rich, MIDI-Focused"

1. **Layer-aware everything**: Actuation, velocity, DKS all respect layers
2. **Dual-mode system**: Simple (layer-wide) or advanced (per-key) modes
3. **MIDI-first design**: Velocity curves, per-key MIDI settings
4. **Maximum configurability**: More options, more memory, more flexibility
5. **Dedicated DKS system**: Full multi-zone analog keystroke support
6. **QMK integration**: Built on existing QMK infrastructure

---

## 5. Technical Deep Dive

### ADC to Distance Conversion

#### libhmk
```c
// Uses 1024-entry lookup table with logarithmic scaling
// Formula: 255 * log(1 + ax) / log(1 + 1023*x)
// Calibrated for GEON Raw HE switches + OH49E-S Hall sensors
#define DISTANCE_LUT_SIZE 1024

static inline uint8_t adc_to_distance(uint16_t adc,
                                       uint16_t rest,
                                       uint16_t bottom_out) {
    if (adc <= rest) return 0;
    if (adc >= bottom_out) return 255;

    // Linear interpolation into LUT
    uint32_t index = ((adc - rest) * (DISTANCE_LUT_SIZE - 1)) /
                     (bottom_out - rest);
    return distance_lut[index];
}
```

**Advantage:** Logarithmic curve provides better resolution near actuation points where precision matters most.

#### orthomidi5x14
```c
// Linear normalization to 0-100 range (0-2.5mm)
uint8_t travel = analog_matrix_get_travel_normalized(row, col);
// Returns: (raw_adc - rest) * 100 / (bottom - rest)
```

**Advantage:** Simple, predictable linear mapping. Easy for users to understand "50 = 1.25mm".

### Calibration Strategy

#### libhmk: Continuous Auto-Calibration
```c
// During scan:
if (new_adc_filtered >= adc_bottom_out_value + MATRIX_CALIBRATION_EPSILON) {
    key_matrix[i].adc_bottom_out_value = new_adc_filtered;
    last_bottom_out_threshold_changed = timer_read();
}

// Periodic save after inactivity:
if (timer_elapsed(last_bottom_out_threshold_changed) >= MATRIX_INACTIVITY_TIMEOUT) {
    matrix_save_bottom_out_threshold();
}
```

**Pros:**
- Adapts to switch wear over time
- No manual calibration needed
- Handles temperature drift

**Cons:**
- May cause inconsistency during aggressive typing
- EEPROM wear from periodic saves

#### orthomidi5x14: Manual/Triggered Calibration
Calibration is typically triggered manually through VIA/Vial or at boot.

**Pros:**
- Predictable behavior
- User control over calibration timing
- No unexpected changes during use

**Cons:**
- Requires periodic manual recalibration
- May drift with temperature/wear

### EMA Filter Implementation

#### libhmk
```c
#define EMA(x, y) \
    (((uint32_t)(x) + \
      ((uint32_t)(y) * ((1 << MATRIX_EMA_ALPHA_EXPONENT) - 1))) >> \
     MATRIX_EMA_ALPHA_EXPONENT)

// With MATRIX_EMA_ALPHA_EXPONENT = 4:
// Alpha = 1/16 = 0.0625
// new_filtered = (new_sample + old_filtered * 15) / 16
```

**Analysis:**
- Very aggressive smoothing (alpha = 0.0625)
- Reduces noise effectively
- May introduce ~4-5 samples of latency
- Implemented as bitshift (fast)

---

## 6. Summary & Recommendations

### When to Use libhmk Approach

| Use Case | Reason |
|----------|--------|
| Gaming keyboards | Lower latency, efficient RT |
| Simple layouts | Profile-based switching is cleaner |
| Resource-constrained MCUs | Lower memory footprint |
| Clean codebase priority | Better structured, more maintainable |
| Rapid Trigger focus | Clean state machine implementation |

### When to Use orthomidi5x14 Approach

| Use Case | Reason |
|----------|--------|
| MIDI keyboards | Built-in velocity, MIDI support |
| Complex multi-action keys | Full 8-action DKS |
| Layer-heavy workflows | Per-layer actuation settings |
| Maximum configurability | More options per key |
| QMK ecosystem | Built on established platform |

### Hybrid Recommendations

1. **Adopt libhmk's flat array structure** if refactoring - better cache performance
2. **Adopt libhmk's EMA filtering** - hardware-efficient noise reduction
3. **Keep orthomidi5x14's DKS richness** - more expressive for music/gaming
4. **Consider libhmk's continuous calibration** - less user maintenance
5. **Keep orthomidi5x14's layer awareness** - important for complex layouts

### Performance Estimates (Per Scan Cycle)

| Operation | libhmk | orthomidi5x14 |
|-----------|--------|---------------|
| ADC reading | O(n) | O(n) |
| Filtering | O(n) inline | Varies |
| Actuation lookup | O(1) per key | O(1) + branches |
| RT state machine | O(1) per key | O(1) per key |
| DKS processing | O(1) per event | O(8) per DKS key |
| **Total per key** | ~15-20 cycles | ~20-40 cycles |

### Code Quality Comparison

| Aspect | libhmk | orthomidi5x14 |
|--------|--------|---------------|
| Structure | Clean, modular | Monolithic (single file focus) |
| Comments | Minimal but clear | Extensive documentation |
| Testability | Easier to unit test | Tightly coupled to QMK |
| Portability | Multi-MCU support | QMK-dependent |
| Maintainability | High | Medium (complexity) |

---

## Conclusion

**libhmk** represents a clean, efficient modern implementation optimized for gaming keyboards with rapid trigger. Its flat data structures, profile-based configuration, and continuous calibration make it well-suited for performance-critical applications.

**orthomidi5x14** prioritizes maximum feature flexibility, especially for MIDI and music applications. Its layer-aware per-key system and full DKS implementation provide unmatched configurability at the cost of some computational overhead.

For a MIDI keyboard project, the orthomidi5x14 approach is more appropriate despite being less computationally optimal. For a pure gaming keyboard, libhmk's cleaner architecture would be preferable.

The ideal implementation would combine:
- libhmk's data structure efficiency and calibration
- orthomidi5x14's DKS richness and MIDI support
- libhmk's hardware abstraction for multi-MCU support
- orthomidi5x14's layer-aware flexibility
