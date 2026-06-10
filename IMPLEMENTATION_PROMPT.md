# Implementation Prompt: libhmk Architecture Migration

## Context

You are helping migrate the orthomidi5x14 Hall Effect keyboard firmware from its current architecture to a cleaner, libhmk-inspired architecture. The goal is to adopt libhmk's proven matrix scanning system while preserving our unique features (DKS, MIDI velocity, layer-aware per-key settings).

**Key Documentation Files (read these first):**
- `libhmk_migration_plan.md` - Complete migration plan with code examples
- `libhmk_comparison_analysis.md` - Detailed comparison between architectures
- `DKS_complete_flowchart.md` - DKS implementation (keep unchanged)
- `actuation_flowchart_analysis.md` - Current actuation system (being replaced)

**Current Firmware Location:**
- `vial-qmk - ryzen/quantum/matrix.c` - Main matrix scanning (primary file to rewrite)
- `vial-qmk - ryzen/quantum/process_keycode/process_dks.c` - DKS processing (keep, update interface)

---

## What We're Changing

### REMOVE (Current Architecture)
- 2D arrays: `keys[MATRIX_ROWS][MATRIX_COLS]`
- Mode switching: `per_key_mode_enabled`, `per_key_per_layer_enabled`
- Complex rapidfire with dynamic thresholds: `rapid.actn_pt`, `rapid.deactn_pt`
- Separate calibration array: `calibration[MATRIX_ROWS][MATRIX_COLS]`
- Redundant state variables: `rapid_cycle_active`, `awaiting_release`, `last_direction`
- 4-state rapidfire: `AKS_REGULAR_RELEASED`, `AKS_REGULAR_PRESSED`, `AKS_RAPID_RELEASED`, `AKS_RAPID_PRESSED`

### ADOPT (libhmk Architecture)
- Flat array: `key_state_t key_matrix[NUM_KEYS]`
- EMA filtering: `EMA(new_sample, old_filtered)` macro
- Continuous auto-calibration with EEPROM save after inactivity
- Clean 3-state RT: `KEY_DIR_INACTIVE`, `KEY_DIR_DOWN`, `KEY_DIR_UP`
- Single `extremum` value for RT tracking
- Unified key state structure

### KEEP (orthomidi5x14 Features)
- Layer-aware per-key actuation (always enabled, no mode toggle)
- Full DKS implementation (50 slots, 8 actions per slot)
- MIDI velocity calculation and per-key velocity curves
- `base_velocity` tracking for RT velocity accumulation
- All MIDI aftertouch modes

---

## Target Data Structures

```c
// ============================================================================
// CONSTANTS
// ============================================================================

#define NUM_KEYS (MATRIX_ROWS * MATRIX_COLS)  // 70 for 5x14 matrix
#define KEY_INDEX(row, col) ((row) * MATRIX_COLS + (col))
#define KEY_ROW(idx) ((idx) / MATRIX_COLS)
#define KEY_COL(idx) ((idx) % MATRIX_COLS)

// EMA filter: alpha = 1/16 = 0.0625
#define MATRIX_EMA_ALPHA_EXPONENT 4
#define EMA(x, y) \
    (((uint32_t)(x) + ((uint32_t)(y) * ((1 << MATRIX_EMA_ALPHA_EXPONENT) - 1))) >> \
     MATRIX_EMA_ALPHA_EXPONENT)

#define CALIBRATION_EPSILON 5
#define INACTIVITY_TIMEOUT_MS 3000

// ============================================================================
// KEY DIRECTION ENUM (libhmk style)
// ============================================================================

typedef enum {
    KEY_DIR_INACTIVE = 0,  // Key at rest or below actuation
    KEY_DIR_DOWN     = 1,  // Key pressed, tracking deepest point
    KEY_DIR_UP       = 2   // Key released by RT, tracking highest point
} key_dir_t;

// ============================================================================
// UNIFIED KEY STATE (replaces analog_key_t + calibration_t)
// ============================================================================

typedef struct {
    // ADC state (with EMA filtering)
    uint16_t adc_filtered;          // EMA-filtered ADC value
    uint16_t adc_rest_value;        // Calibrated rest position
    uint16_t adc_bottom_out_value;  // Calibrated bottom-out position

    // Distance (0-255 scale, like libhmk)
    uint8_t distance;

    // RT state machine (libhmk 3-state)
    uint8_t extremum;               // Peak (DOWN) or trough (UP) position
    key_dir_t key_dir;              // Current direction state
    bool is_pressed;                // Logical pressed state for matrix

    // MIDI velocity (kept from orthomidi5x14)
    uint8_t base_velocity;          // For RT velocity accumulation
} key_state_t;

// Single flat array
key_state_t key_matrix[NUM_KEYS];

// ============================================================================
// PER-KEY ACTUATION CONFIG (layer-aware, always per-key)
// ============================================================================

typedef struct {
    uint8_t actuation_point;   // 0-255 distance threshold
    uint8_t rt_down;           // RT press sensitivity (0 = RT disabled)
    uint8_t rt_up;             // RT release sensitivity (0 = same as rt_down)
    uint8_t flags;             // Bit 0: continuous RT mode
    uint8_t velocity_curve;    // Per-key velocity curve index
} actuation_t;

// Per-key settings for each layer
actuation_t actuation_map[NUM_LAYERS][NUM_KEYS];

// Cached pointer to current layer (for hot path optimization)
static actuation_t *current_actuation;
static uint8_t cached_layer = 0xFF;
```

---

## Target matrix_scan() Implementation

```c
void matrix_scan(void) {
    // Update layer cache if changed
    uint8_t current_layer = get_highest_layer(layer_state | default_layer_state);
    if (current_layer != cached_layer) {
        current_actuation = actuation_map[current_layer];
        cached_layer = current_layer;
    }

    // Single flat loop (cache-friendly)
    for (uint32_t i = 0; i < NUM_KEYS; i++) {
        key_state_t *key = &key_matrix[i];
        actuation_t *act = &current_actuation[i];

        // 1. Read and filter ADC
        uint16_t raw_adc = read_adc_for_key(i);
        key->adc_filtered = EMA(raw_adc, key->adc_filtered);

        // 2. Continuous calibration (bottom-out only)
        if (key->adc_filtered >= key->adc_bottom_out_value + CALIBRATION_EPSILON) {
            key->adc_bottom_out_value = key->adc_filtered;
            last_calibration_change = timer_read();
        }

        // 3. Calculate distance (0-255)
        key->distance = adc_to_distance(key->adc_filtered,
                                         key->adc_rest_value,
                                         key->adc_bottom_out_value);

        // 4. RT state machine (libhmk 3-state)
        if (act->rt_down == 0) {
            // RT disabled - simple threshold
            key->is_pressed = (key->distance >= act->actuation_point);
            key->key_dir = KEY_DIR_INACTIVE;
        } else {
            // RT enabled
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

    // Auto-save calibration after inactivity
    if (timer_elapsed(last_calibration_change) >= INACTIVITY_TIMEOUT_MS) {
        save_calibration_to_eeprom();
        last_calibration_change = timer_read();
    }
}
```

---

## Implementation Tasks

### Task 1: Rewrite matrix.c Core
1. Replace 2D arrays with flat `key_matrix[NUM_KEYS]`
2. Implement EMA filtering in ADC reading
3. Implement libhmk 3-state RT FSM
4. Add continuous calibration with auto-save
5. Remove all mode-switching logic (`per_key_mode_enabled`, etc.)

### Task 2: Update Calibration System
1. Merge calibration into `key_state_t`
2. Implement `matrix_init()` with rest value calibration
3. Implement continuous bottom-out calibration during scan
4. Add EEPROM save after inactivity timeout

### Task 3: Update MIDI Processing
1. Keep `base_velocity` tracking for RT
2. Update `process_midi_key_analog()` to use new state
3. Use `key->is_pressed` and `key->key_dir` instead of old states
4. Keep all velocity modes and aftertouch

### Task 4: Update DKS Integration
1. Update `dks_process_key()` call to use `key_matrix[i].distance`
2. Keep DKS state tracking separate (unchanged)
3. Update any row/col references to use `KEY_ROW(i)`, `KEY_COL(i)`

### Task 5: Update matrix_scan_custom() Return
1. Build matrix rows from `key_matrix[i].is_pressed`
2. Handle DKS keys (force `is_pressed = false`, DKS manages own keycodes)
3. Handle MIDI keys with velocity modes

### Task 6: Update Public API Functions
1. Update `analog_matrix_get_travel()` → use `key_matrix[KEY_INDEX(row,col)].distance`
2. Update `analog_matrix_set_actuation_point()` → update `actuation_map`
3. Update `analog_matrix_set_rapid_trigger()` → update `actuation_map` rt_down/rt_up
4. Remove `analog_matrix_set_key_mode()` (no more mode switching)

---

## Files to Modify

1. **`vial-qmk - ryzen/quantum/matrix.c`** - Complete rewrite of core scanning
2. **`vial-qmk - ryzen/quantum/matrix.h`** - Update structures and declarations
3. **`vial-qmk - ryzen/quantum/process_keycode/process_dks.c`** - Update interface only
4. **`vial-qmk - ryzen/quantum/vial.c`** - Update HID commands for new actuation format
5. **Python GUI files** - Update after firmware is working

---

## Important Constraints

1. **Keep DKS unchanged** - Only update the interface to use new distance values
2. **Keep MIDI velocity modes** - All 4 modes (fixed, peak, speed, speed+peak) must work
3. **Keep aftertouch** - All 4 aftertouch modes must work
4. **Layer-aware always** - Per-key actuation respects current layer (no global mode)
5. **Backward compatible EEPROM** - Or provide migration path for existing settings

---

## Testing Checklist

- [ ] Basic key press/release works
- [ ] RT triggers on small movements (test with rt_down = 10)
- [ ] RT continuous mode resets to 0
- [ ] RT asymmetric mode (different rt_down vs rt_up)
- [ ] Layer switching changes actuation points
- [ ] MIDI velocity mode 0 (fixed) works
- [ ] MIDI velocity mode 2 (speed) works
- [ ] DKS keys trigger at correct thresholds
- [ ] Calibration persists after power cycle
- [ ] Auto-calibration updates bottom-out

---

## Start Implementation

Begin with Task 1: Rewrite the core of `matrix.c` with the new data structures and RT state machine. The MIDI and DKS integration can be added incrementally after the core scanning works.

Read `libhmk_migration_plan.md` for the complete implementation details and code examples.
