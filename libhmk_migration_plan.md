# libhmk Architecture Migration Plan
## Adopting libhmk's Matrix Scanning with orthomidi5x14's Features

---

## Table of Contents

1. [RT vs Rapidfire Comparison](#1-rt-vs-rapidfire-comparison)
2. [Current orthomidi5x14 Architecture Issues](#2-current-orthomidi5x14-architecture-issues)
3. [Target Architecture](#3-target-architecture)
4. [Implementation Plan](#4-implementation-plan)
5. [Data Structure Migration](#5-data-structure-migration)
6. [Code Migration Details](#6-code-migration-details)
7. [Testing Strategy](#7-testing-strategy)

---

## 1. RT vs Rapidfire Comparison

### libhmk Rapid Trigger (Clean 3-State FSM)

```
                    ┌───────────────────────────────────────────────────────┐
                    │              KEY_DIR_INACTIVE                         │
                    │  • Key at rest or below actuation point               │
                    │  • is_pressed = false                                 │
                    └───────────────────┬───────────────────────────────────┘
                                        │
                    Press down past actuation_point
                                        │
                                        ↓
                    ┌───────────────────────────────────────────────────────┐
                    │              KEY_DIR_DOWN                             │
                    │  • Key moving down (pressed)                          │
                    │  • is_pressed = true                                  │
                    │  • extremum = deepest point reached                   │
                    └───────────────────┬───────────────────────────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
                    │                                       │
          Release past reset_point          Release by rt_up from extremum
                    │                                       │
                    ↓                                       ↓
          KEY_DIR_INACTIVE              ┌───────────────────────────────────┐
                                        │              KEY_DIR_UP           │
                                        │  • Key moving up (released)       │
                                        │  • is_pressed = false             │
                                        │  • extremum = highest point       │
                                        └───────────────────┬───────────────┘
                                                            │
                                        ┌───────────────────┴───────────────┐
                                        │                                   │
                              Release past reset_point    Press by rt_down from extremum
                                        │                                   │
                                        ↓                                   ↓
                              KEY_DIR_INACTIVE                      KEY_DIR_DOWN
```

**libhmk State Machine Code:**
```c
switch (key_matrix[i].key_dir) {
    case KEY_DIR_INACTIVE:
        if (distance > actuation_point) {
            extremum = distance;
            key_dir = KEY_DIR_DOWN;
            is_pressed = true;
        }
        break;

    case KEY_DIR_DOWN:
        if (distance <= reset_point) {
            // Full release to inactive
            extremum = distance;
            key_dir = KEY_DIR_INACTIVE;
            is_pressed = false;
        } else if (distance + rt_up < extremum) {
            // Released by RT sensitivity
            extremum = distance;
            key_dir = KEY_DIR_UP;
            is_pressed = false;
        } else if (distance > extremum) {
            extremum = distance;  // Track deeper press
        }
        break;

    case KEY_DIR_UP:
        if (distance <= reset_point) {
            extremum = distance;
            key_dir = KEY_DIR_INACTIVE;
            is_pressed = false;
        } else if (extremum + rt_down < distance) {
            // Re-pressed by RT sensitivity
            extremum = distance;
            key_dir = KEY_DIR_DOWN;
            is_pressed = true;
        } else if (distance < extremum) {
            extremum = distance;  // Track higher release
        }
        break;
}
```

**Key Features:**
- **3 states**: INACTIVE, DOWN, UP
- **Single extremum value**: Tracks peak (DOWN) or trough (UP) position
- **Separate rt_down/rt_up**: Can have different sensitivities for press vs release
- **Continuous mode**: Optional (reset_point = 0 or actuation_point)
- **Clean transitions**: No ambiguous states

---

### orthomidi5x14 Rapidfire (Current Implementation)

```
                    ┌───────────────────────────────────────────────────────┐
                    │           AKS_REGULAR_RELEASED                        │
                    │  • Key at rest                                        │
                    │  • mode can be AKM_REGULAR or AKM_RAPID               │
                    └───────────────────┬───────────────────────────────────┘
                                        │
                                        ├── (AKM_REGULAR mode)
                                        │   └── Press past actuation → AKS_REGULAR_PRESSED
                                        │
                                        └── (AKM_RAPID mode)
                                            └── Press past actuation → AKS_RAPID_PRESSED
                                                (also updates dynamic thresholds)

┌─────────────────────────────────────────────────────────────────────────────┐
│                           AKM_RAPID MODE LOGIC                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  if (state == AKS_RAPID_RELEASED) {                                        │
│      if (travel >= rapid.actn_pt && travel > ZERO_DEAD_ZONE) {             │
│          state = AKS_RAPID_PRESSED;                                        │
│          rapid.actn_pt = travel;        // Update to current               │
│          rapid.deactn_pt = travel - rpd_trig_sen_release;                  │
│      } else if (travel < rapid.deactn_pt) {                                │
│          rapid.actn_pt = travel + rpd_trig_sen;  // Update for re-trigger  │
│          rapid.deactn_pt = travel;                                         │
│      }                                                                      │
│  } else { // AKS_RAPID_PRESSED                                             │
│      if (travel <= regular.deactn_pt && near top deadzone) {               │
│          state = AKS_REGULAR_RELEASED;   // Full release                   │
│      } else if (travel <= rapid.deactn_pt && not at bottom) {              │
│          state = AKS_RAPID_RELEASED;     // RT release                     │
│          update thresholds for re-trigger                                   │
│      } else if (travel > rapid.actn_pt) {                                  │
│          update thresholds (pressing deeper)                                │
│      }                                                                      │
│  }                                                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**orthomidi5x14 State Machine Code:**
```c
case AKM_RAPID:
    if (key->state == AKS_RAPID_RELEASED) {
        if (key->travel >= key->rapid.actn_pt &&
            key->travel > ZERO_TRAVEL_DEAD_ZONE * TRAVEL_SCALE) {
            key->state = AKS_RAPID_PRESSED;
            changed = true;
            key->rapid.actn_pt = key->travel;
            key->rapid.deactn_pt = key->travel > key->rpd_trig_sen_release ?
                                  key->travel - key->rpd_trig_sen_release : 0;
        } else if (key->travel < key->rapid.deactn_pt) {
            key->rapid.actn_pt = key->travel + key->rpd_trig_sen;
            key->rapid.deactn_pt = key->travel;
        }
    } else {
        if (key->travel <= key->regular.deactn_pt &&
            key->travel < ZERO_TRAVEL_DEAD_ZONE * TRAVEL_SCALE + key->rpd_trig_sen) {
            key->state = AKS_REGULAR_RELEASED;
            changed = true;
        } else if (key->travel <= key->rapid.deactn_pt &&
                  key->travel < BOTTOM_DEAD_ZONE * TRAVEL_SCALE - key->rpd_trig_sen_release) {
            key->state = AKS_RAPID_RELEASED;
            changed = true;
            key->rapid.deactn_pt = key->travel;
            key->rapid.actn_pt = key->travel + key->rpd_trig_sen;
        } else if (key->travel > key->rapid.actn_pt) {
            key->rapid.deactn_pt = key->travel > key->rpd_trig_sen_release ?
                                  key->travel - key->rpd_trig_sen_release : 0;
            key->rapid.actn_pt = key->travel;
        }
    }
    break;
```

**Issues:**
- **4+ states**: REGULAR_RELEASED, REGULAR_PRESSED, RAPID_RELEASED, RAPID_PRESSED (plus mode flags)
- **Dynamic threshold updates**: `rapid.actn_pt` and `rapid.deactn_pt` constantly change
- **Complex conditionals**: Multiple edge case checks (deadzones, boundaries)
- **Additional tracking**: Separate `rapid_cycle_active`, `awaiting_release`, `base_velocity` for MIDI
- **Redundant state**: Both `mode` and `state` variables need to be checked

---

### Side-by-Side Comparison

| Aspect | libhmk RT | orthomidi5x14 Rapidfire |
|--------|-----------|-------------------------|
| **States** | 3 (INACTIVE, DOWN, UP) | 4+ (REGULAR_RELEASED, REGULAR_PRESSED, RAPID_RELEASED, RAPID_PRESSED) |
| **Direction tracking** | Single `key_dir` enum | Implicit in state + thresholds |
| **Position tracking** | Single `extremum` value | Dynamic `actn_pt` + `deactn_pt` pair |
| **Re-trigger detection** | `extremum + rt_down < distance` | `travel >= rapid.actn_pt` (which updates) |
| **Release detection** | `distance + rt_up < extremum` | `travel <= rapid.deactn_pt` (which updates) |
| **Reset point** | Configurable (0 or actuation) | Fixed (uses `regular.deactn_pt`) |
| **Separate sensitivities** | `rt_down` and `rt_up` | `rpd_trig_sen` and `rpd_trig_sen_release` |
| **Code clarity** | High (explicit FSM) | Lower (threshold juggling) |
| **Edge case handling** | Minimal | Multiple deadzone checks |
| **MIDI velocity** | Not integrated | Integrated (`base_velocity`, etc.) |

### Why libhmk's Approach is Better

1. **Clearer Mental Model**: Direction (DOWN/UP) is explicit, not derived from thresholds
2. **Single Tracking Value**: `extremum` vs. updating both `actn_pt` and `deactn_pt`
3. **Predictable Transitions**: No threshold juggling, just compare to extremum
4. **Continuous Mode Support**: Built-in via reset_point configuration
5. **Easier Debugging**: State and direction are directly inspectable
6. **Fewer Edge Cases**: No special handling for "near top/bottom deadzone"

---

## 2. Current orthomidi5x14 Architecture Issues

### Issue 1: 2D Matrix Structure (Cache Unfriendly)
```c
// Current: 2D nested arrays
static analog_key_t  keys[MATRIX_ROWS][MATRIX_COLS];
static calibration_t calibration[MATRIX_ROWS][MATRIX_COLS];
static midi_key_state_t midi_key_states[MATRIX_ROWS][MATRIX_COLS];

// Nested loops
for (row = 0; row < MATRIX_ROWS; row++) {
    for (col = 0; col < MATRIX_COLS; col++) {
        analog_key_t *key = &keys[row][col];  // Scattered memory access
    }
}
```

### Issue 2: No ADC Filtering
```c
// Current: Raw ADC value used directly
key->raw_value = raw_value;
key->travel = calculate_travel(row, col, raw_value);  // No filtering
```

### Issue 3: Split Calibration Logic
```c
// Calibration is separate from key state
static calibration_t calibration[MATRIX_ROWS][MATRIX_COLS];

// Calibration doesn't auto-save after inactivity
static void update_calibration(...) {
    // Updates values but no automatic persistence
}
```

### Issue 4: Mode Switching Complexity
```c
// Current: per_key_mode_enabled and per_key_per_layer_enabled flags
if (!per_key_mode_enabled) {
    return layer_actuations[layer].midi_actuation;
}
// ... complex per-key lookup
```

### Issue 5: Redundant RT State Variables
```c
typedef struct {
    uint8_t  base_velocity;        // For MIDI RT
    bool     rapid_cycle_active;   // Separate from state
    bool     awaiting_release;     // Separate from state
    uint8_t  last_direction;       // Redundant with state
} analog_key_t;
```

---

## 3. Target Architecture

### New Unified Key State Structure (libhmk-inspired)

```c
// Target: Single flat array with unified state
typedef struct {
    // ADC/Calibration (from libhmk)
    uint16_t adc_filtered;         // EMA-filtered ADC value
    uint16_t adc_rest_value;       // Calibrated rest position
    uint16_t adc_bottom_out_value; // Calibrated bottom-out

    // Distance/Travel (from libhmk)
    uint8_t  distance;             // 0-255 (libhmk style) or keep 0-240

    // Rapid Trigger State (from libhmk)
    uint8_t  extremum;             // Peak/trough position for RT
    uint8_t  key_dir;              // KEY_DIR_INACTIVE/DOWN/UP
    bool     is_pressed;           // Logical pressed state

    // Per-Key Configuration (kept from orthomidi5x14)
    uint8_t  actuation_point;      // Per-key actuation (0-255)
    uint8_t  rt_down;              // RT press sensitivity
    uint8_t  rt_up;                // RT release sensitivity (optional different)
    bool     rt_continuous;        // Continuous RT mode (reset to 0)

    // MIDI-specific (kept from orthomidi5x14)
    uint8_t  base_velocity;        // For RT velocity tracking
    uint8_t  velocity_curve;       // Per-key velocity curve index

    // DKS-specific (kept from orthomidi5x14)
    // (DKS uses separate dks_states array - unchanged)
} key_state_t;

// Single flat array
key_state_t key_matrix[NUM_KEYS];  // NUM_KEYS = MATRIX_ROWS * MATRIX_COLS
```

### New Actuation Configuration (Per-Key, Layer-Aware)

```c
// Per-key actuation stored per layer (simplified from current)
typedef struct {
    uint8_t actuation_point;       // 0-255 distance
    uint8_t rt_down;               // RT press sensitivity (0 = disabled)
    uint8_t rt_up;                 // RT release sensitivity (0 = same as rt_down)
    uint8_t flags;                 // Bit 0: continuous RT, Bit 1: custom velocity curve
    uint8_t velocity_curve;        // Curve index if enabled
} actuation_t;  // 5 bytes per key

// Storage: Per-key settings for each layer
actuation_t actuation_map[NUM_LAYERS][NUM_KEYS];

// Or: Current layer's actuation cached for fast access
actuation_t *current_actuation_map;  // Points to actuation_map[current_layer]
```

### EMA Filter Macro (from libhmk)

```c
// Exponential Moving Average filter
// Alpha = 1 / (2^ALPHA_EXPONENT)
// With ALPHA_EXPONENT = 4: alpha = 1/16 = 0.0625
#define MATRIX_EMA_ALPHA_EXPONENT 4

#define EMA(new_sample, old_filtered) \
    (((uint32_t)(new_sample) + \
      ((uint32_t)(old_filtered) * ((1 << MATRIX_EMA_ALPHA_EXPONENT) - 1))) >> \
     MATRIX_EMA_ALPHA_EXPONENT)
```

### Distance Calculation (from libhmk)

```c
// Option 1: Keep linear (current orthomidi5x14)
static inline uint8_t adc_to_distance(uint16_t adc, uint16_t rest, uint16_t bottom) {
    if (adc <= rest) return 0;
    if (adc >= bottom) return 255;
    return ((adc - rest) * 255) / (bottom - rest);
}

// Option 2: Adopt logarithmic LUT (libhmk) - better resolution near actuation
// Requires 1KB LUT but provides better feel
static const uint8_t distance_lut[1024] = { ... };
```

---

## 4. Implementation Plan

### Phase 1: Data Structure Migration (Week 1)

**Step 1.1: Define New Structures**
- Create `key_state_t` unified structure
- Create `actuation_t` per-key configuration
- Define flat `key_matrix[NUM_KEYS]` array
- Add helper macros: `KEY_INDEX(row, col)`, `KEY_ROW(idx)`, `KEY_COL(idx)`

**Step 1.2: Add EMA Filter**
- Implement `EMA()` macro
- Add `adc_filtered` field to key state
- Update ADC reading to apply filter

**Step 1.3: Migrate Calibration**
- Move calibration into key_state_t
- Add `adc_rest_value` and `adc_bottom_out_value`
- Implement continuous calibration (from libhmk)
- Add inactivity-based EEPROM save

### Phase 2: Rapid Trigger Overhaul (Week 2)

**Step 2.1: Implement libhmk RT State Machine**
- Add `key_dir` enum (INACTIVE, DOWN, UP)
- Add `extremum` field
- Implement clean 3-state FSM
- Remove old rapid state variables

**Step 2.2: Add RT Configuration**
- Per-key `rt_down` and `rt_up`
- Continuous mode flag
- Remove `rapid.actn_pt`/`rapid.deactn_pt` dynamic thresholds

**Step 2.3: Integrate with MIDI Velocity**
- Keep `base_velocity` for RT velocity tracking
- Update velocity calculation to use new state

### Phase 3: Layer-Aware Per-Key System (Week 3)

**Step 3.1: Remove Mode Switching**
- Remove `per_key_mode_enabled` flag
- Always use per-key actuation
- Keep layer awareness

**Step 3.2: Implement Layer Caching**
- Cache current layer's actuation map pointer
- Update cache on layer change
- Optimize hot path

**Step 3.3: Migrate Existing Settings**
- Convert old `layer_actuations[]` to new format
- Convert old `per_key_actuations[][]` to new format
- Update EEPROM layout

### Phase 4: Matrix Scan Optimization (Week 4)

**Step 4.1: Flatten Main Loop**
```c
// Target loop structure
void matrix_scan(void) {
    for (uint32_t i = 0; i < NUM_KEYS; i++) {
        // 1. Filter ADC
        key_matrix[i].adc_filtered = EMA(read_adc(i), key_matrix[i].adc_filtered);

        // 2. Calculate distance
        key_matrix[i].distance = adc_to_distance(...);

        // 3. Update calibration
        update_calibration(i);

        // 4. RT state machine
        process_rapid_trigger(i);
    }
}
```

**Step 4.2: Separate MIDI/DKS Processing**
- Process MIDI keys in separate loop (or flag-based skip)
- Process DKS keys in separate loop
- Keep these modular for maintainability

**Step 4.3: Optimize Hot Path**
- Inline critical functions
- Use `__attribute__((always_inline))`
- Profile and benchmark

### Phase 5: DKS Integration (Week 5)

**Step 5.1: Keep DKS Implementation**
- DKS uses separate `dks_states[]` array (unchanged)
- DKS processing uses new `key_matrix[i].distance`
- No changes to DKS logic

**Step 5.2: Update DKS Interface**
- `dks_process_key(key_index, distance)` instead of `(row, col, travel)`
- Helper to get row/col from index if needed

### Phase 6: GUI/Protocol Updates (Week 6)

**Step 6.1: Update HID Protocol**
- New commands for unified actuation settings
- Remove mode switching commands
- Update per-key configuration commands

**Step 6.2: Update Vial GUI**
- Update trigger_settings.py for new model
- Simplify UI (remove mode toggle)
- Update keymap_editor.py if needed

---

## 5. Data Structure Migration

### Current → Target Mapping

```
CURRENT                              TARGET
─────────────────────────────────────────────────────────────────

analog_key_t keys[ROWS][COLS]  ───→  key_state_t key_matrix[NUM_KEYS]
  .travel                      ───→    .distance
  .raw_value                   ───→    .adc_filtered (filtered)
  .mode (REGULAR/RAPID)        ───→    (removed - RT always available)
  .state (4 states)            ───→    .key_dir (3 states) + .is_pressed
  .rapid.actn_pt               ───→    (removed - use extremum)
  .rapid.deactn_pt             ───→    (removed - use extremum)
  .rpd_trig_sen                ───→    .rt_down (from actuation_t)
  .rpd_trig_sen_release        ───→    .rt_up (from actuation_t)
  .base_velocity               ───→    .base_velocity (kept)
  .rapid_cycle_active          ───→    (removed - derivable from key_dir)
  .awaiting_release            ───→    (removed - derivable from key_dir)

calibration_t calibration[][]  ───→  Merged into key_state_t
  .value.zero_travel           ───→    .adc_rest_value
  .value.full_travel           ───→    .adc_bottom_out_value
  .calibrated                  ───→    (derivable from values)

layer_actuations[12]           ───→  (removed - use per-key)
per_key_actuations[12][70]     ───→  actuation_map[NUM_LAYERS][NUM_KEYS]

per_key_mode_enabled           ───→  (removed)
per_key_per_layer_enabled      ───→  (always per-layer now)
```

### Memory Comparison

```
CURRENT MEMORY USAGE:
─────────────────────────────────────────────────────────────────
analog_key_t:     ~20 bytes × 70 keys           = 1,400 bytes
calibration_t:    ~16 bytes × 70 keys           = 1,120 bytes
midi_key_state_t: ~20 bytes × 70 keys           = 1,400 bytes
layer_actuations: ~8 bytes × 12 layers          =    96 bytes
per_key_actuations: 8 bytes × 70 × 12           = 6,720 bytes
                                          TOTAL ≈ 10,736 bytes

TARGET MEMORY USAGE:
─────────────────────────────────────────────────────────────────
key_state_t:      ~24 bytes × 70 keys           = 1,680 bytes
actuation_map:    5 bytes × 70 × 12 layers      = 4,200 bytes
midi_state (if kept separate): ~12 × 70         =   840 bytes
                                          TOTAL ≈ 6,720 bytes

SAVINGS: ~4,000 bytes (37% reduction)
```

---

## 6. Code Migration Details

### New matrix_scan() Implementation

```c
// ============================================================================
// CONSTANTS
// ============================================================================

#define NUM_KEYS (MATRIX_ROWS * MATRIX_COLS)
#define KEY_INDEX(row, col) ((row) * MATRIX_COLS + (col))
#define KEY_ROW(idx) ((idx) / MATRIX_COLS)
#define KEY_COL(idx) ((idx) % MATRIX_COLS)

#define MATRIX_EMA_ALPHA_EXPONENT 4
#define EMA(x, y) \
    (((uint32_t)(x) + ((uint32_t)(y) * ((1 << MATRIX_EMA_ALPHA_EXPONENT) - 1))) >> \
     MATRIX_EMA_ALPHA_EXPONENT)

#define CALIBRATION_EPSILON 5
#define INACTIVITY_TIMEOUT_MS 3000

// ============================================================================
// KEY DIRECTION ENUM (from libhmk)
// ============================================================================

typedef enum {
    KEY_DIR_INACTIVE = 0,
    KEY_DIR_DOWN     = 1,
    KEY_DIR_UP       = 2
} key_dir_t;

// ============================================================================
// UNIFIED KEY STATE
// ============================================================================

typedef struct {
    // ADC state
    uint16_t adc_filtered;
    uint16_t adc_rest_value;
    uint16_t adc_bottom_out_value;

    // Distance (0-255)
    uint8_t distance;

    // RT state machine (libhmk style)
    uint8_t extremum;
    key_dir_t key_dir;
    bool is_pressed;

    // MIDI
    uint8_t base_velocity;
} key_state_t;

key_state_t key_matrix[NUM_KEYS];

// ============================================================================
// PER-KEY ACTUATION (layer-aware)
// ============================================================================

typedef struct {
    uint8_t actuation_point;   // 0-255
    uint8_t rt_down;           // 0 = RT disabled
    uint8_t rt_up;             // 0 = same as rt_down
    uint8_t flags;             // Bit 0: continuous
    uint8_t velocity_curve;
} actuation_t;

actuation_t actuation_map[NUM_LAYERS][NUM_KEYS];

// Cached pointer to current layer's actuation
static actuation_t *current_actuation;
static uint8_t cached_layer = 0xFF;
static uint32_t last_calibration_change;

// ============================================================================
// ADC TO DISTANCE
// ============================================================================

static inline uint8_t adc_to_distance(uint16_t adc,
                                       uint16_t rest,
                                       uint16_t bottom) {
    if (adc <= rest) return 0;
    if (adc >= bottom) return 255;
    return ((uint32_t)(adc - rest) * 255) / (bottom - rest);
}

// ============================================================================
// MATRIX SCAN (libhmk style)
// ============================================================================

void matrix_scan(void) {
    // Update layer cache
    uint8_t current_layer = get_highest_layer(layer_state | default_layer_state);
    if (current_layer != cached_layer) {
        current_actuation = actuation_map[current_layer];
        cached_layer = current_layer;
    }

    // Single loop over flat array
    for (uint32_t i = 0; i < NUM_KEYS; i++) {
        key_state_t *key = &key_matrix[i];
        actuation_t *act = &current_actuation[i];

        // 1. Read and filter ADC
        uint16_t raw_adc = read_adc_for_key(i);
        key->adc_filtered = EMA(raw_adc, key->adc_filtered);

        // 2. Auto-calibrate bottom-out
        if (key->adc_filtered >= key->adc_bottom_out_value + CALIBRATION_EPSILON) {
            key->adc_bottom_out_value = key->adc_filtered;
            last_calibration_change = timer_read();
        }

        // 3. Calculate distance
        key->distance = adc_to_distance(key->adc_filtered,
                                         key->adc_rest_value,
                                         key->adc_bottom_out_value);

        // 4. RT state machine
        if (act->rt_down == 0) {
            // RT disabled - simple threshold
            key->is_pressed = (key->distance >= act->actuation_point);
            key->key_dir = KEY_DIR_INACTIVE;
        } else {
            // RT enabled - 3-state FSM
            uint8_t reset_point = (act->flags & 0x01) ? 0 : act->actuation_point;
            uint8_t rt_up = (act->rt_up == 0) ? act->rt_down : act->rt_up;

            switch (key->key_dir) {
                case KEY_DIR_INACTIVE:
                    if (key->distance > act->actuation_point) {
                        key->extremum = key->distance;
                        key->key_dir = KEY_DIR_DOWN;
                        key->is_pressed = true;
                    }
                    break;

                case KEY_DIR_DOWN:
                    if (key->distance <= reset_point) {
                        key->extremum = key->distance;
                        key->key_dir = KEY_DIR_INACTIVE;
                        key->is_pressed = false;
                    } else if (key->distance + rt_up < key->extremum) {
                        key->extremum = key->distance;
                        key->key_dir = KEY_DIR_UP;
                        key->is_pressed = false;
                    } else if (key->distance > key->extremum) {
                        key->extremum = key->distance;
                    }
                    break;

                case KEY_DIR_UP:
                    if (key->distance <= reset_point) {
                        key->extremum = key->distance;
                        key->key_dir = KEY_DIR_INACTIVE;
                        key->is_pressed = false;
                    } else if (key->extremum + act->rt_down < key->distance) {
                        key->extremum = key->distance;
                        key->key_dir = KEY_DIR_DOWN;
                        key->is_pressed = true;
                    } else if (key->distance < key->extremum) {
                        key->extremum = key->distance;
                    }
                    break;
            }
        }
    }

    // Save calibration after inactivity
    if (timer_elapsed(last_calibration_change) >= INACTIVITY_TIMEOUT_MS) {
        save_calibration_to_eeprom();
        last_calibration_change = timer_read();  // Prevent repeated saves
    }
}
```

### Helper: ADC Reading for Key Index

```c
// Map key index to physical ADC reading
// (Depends on your hardware - column mux, row ADC)
static uint16_t read_adc_for_key(uint32_t key_idx) {
    uint8_t row = KEY_ROW(key_idx);
    uint8_t col = KEY_COL(key_idx);

    // Select column via multiplexer
    select_column(col);
    wait_us(40);

    // Read row's ADC channel
    uint16_t value = adc_read_channel(row);

    unselect_column();
    return value;
}

// Or batch read (more efficient):
static void read_all_adc_for_column(uint8_t col, uint16_t *out) {
    select_column(col);
    wait_us(40);
    adc_convert_all_rows(out);  // Reads all row channels at once
    unselect_column();
}
```

---

## 7. Testing Strategy

### Unit Tests

1. **EMA Filter Test**
   - Verify convergence behavior
   - Test step response
   - Test noise rejection

2. **Distance Calculation Test**
   - Verify 0 at rest, 255 at bottom
   - Test boundary conditions
   - Test with various calibration values

3. **RT State Machine Test**
   - Test all state transitions
   - Test continuous vs non-continuous mode
   - Test asymmetric rt_down/rt_up

### Integration Tests

1. **Calibration Test**
   - Verify auto-calibration updates
   - Test EEPROM persistence
   - Test recalibration command

2. **Layer Switching Test**
   - Verify actuation changes with layer
   - Test layer cache invalidation
   - Test held keys during layer change

3. **MIDI Velocity Test**
   - Verify velocity calculation with new state
   - Test RT velocity accumulation
   - Test per-key velocity curves

4. **DKS Test**
   - Verify DKS still works with new distance values
   - Test threshold crossings
   - Test all behaviors (TAP/PRESS/RELEASE)

### Performance Benchmarks

1. **Scan Rate Test**
   - Measure matrix_scan() time
   - Compare before/after migration
   - Target: <1ms per full scan

2. **Latency Test**
   - Measure key press to USB report latency
   - Compare with libhmk reference
   - Target: <5ms end-to-end

---

## Summary

This migration plan transforms the orthomidi5x14 firmware from a complex, mode-switchable system to a clean, efficient, always-per-key system inspired by libhmk. Key changes:

1. **Flat array structure** for cache efficiency
2. **EMA filtering** for noise reduction
3. **libhmk 3-state RT** replacing complex rapidfire logic
4. **Continuous calibration** with auto-save
5. **Layer-aware per-key actuation** (always, no mode switching)
6. **Keep DKS implementation** as-is

The result will be a more maintainable, efficient, and robust firmware while preserving the MIDI features and DKS capabilities that make orthomidi5x14 unique.
