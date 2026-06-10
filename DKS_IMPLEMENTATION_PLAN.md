# Dynamic Keystroke (DKS) Implementation Plan

## Overview
Implement multi-action Dynamic Keystroke (DKS) feature using existing keycode/matrix patterns, allowing up to 4 actions at different actuation points with configurable press/release/tap behaviors.

---

## 1. KEYCODE RANGE ALLOCATION

### Keycode Definition
```c
// In orthomidi5x14.c
#define DKS_KEY_BASE    0xED00  // Base for DKS keycodes
#define DKS_KEY_MAX     0xED45  // 70 keys (5×14 matrix)

// DKS keycodes: DKS_00 through DKS_69
// DKS_00 = 0xED00, DKS_01 = 0xED01, ... DKS_69 = 0xED45
```

**Detection Pattern** (similar to MI_CC_TOG_0):
```c
if (keycode >= DKS_KEY_BASE && keycode <= DKS_KEY_MAX) {
    uint8_t dks_index = keycode - DKS_KEY_BASE;  // 0-69
    // Handle DKS key
}
```

---

## 2. DATA STRUCTURES

### DKS Configuration (Per-Key, Per-Layer)

```c
// Behavior modes for each action
typedef enum {
    DKS_BEHAVIOR_TAP     = 0,  // Press + Release (default)
    DKS_BEHAVIOR_PRESS   = 1,  // Press only (hold)
    DKS_BEHAVIOR_RELEASE = 2,  // Release only
    DKS_BEHAVIOR_RESERVED = 3  // Future use
} dks_behavior_t;

// Single DKS action binding
typedef struct {
    uint16_t keycode;          // What keycode to send (0 = disabled)
    uint8_t behavior;          // dks_behavior_t (2 bits)
    uint8_t actuation_point;   // 0-100 (0-2.5mm, same encoding as per_key_actuation)
} dks_action_t;

// DKS configuration for one key
typedef struct {
    bool enabled;              // Is DKS enabled for this key?
    dks_action_t press[4];     // 4 actions on key press (downstroke)
    dks_action_t release[4];   // 4 actions on key release (upstroke)
} dks_config_t;

// Storage: Per-layer DKS configurations
typedef struct {
    dks_config_t keys[70];     // 70 keys
} layer_dks_config_t;

// Global array (1 layer for now, expandable to 12)
layer_dks_config_t dks_configs[1];  // Start with layer 0
```

**Memory Calculation:**
```
Per action:  2 bytes (keycode) + 1 byte (behavior+actuation) = 3 bytes
Per key:     1 byte (enabled) + (4 press × 3) + (4 release × 3) = 1 + 24 = 25 bytes
Per layer:   70 keys × 25 bytes = 1,750 bytes
All 12 layers: 1,750 × 12 = 21,000 bytes (21KB)
```

**Start with 1 layer** (1.75KB) for initial implementation.

---

## 3. EEPROM STORAGE

### Address Allocation
```c
#define EEPROM_DKS_BASE     75000  // After gaming settings (74200)
#define EEPROM_DKS_SIZE     1750   // For 1 layer
#define EEPROM_DKS_MAGIC    0xDC57 // "DKS" magic number
```

### Layout
```
Address    Size    Usage
---------------------------------------------
75000      2       Magic number (0xDC57)
75002      1       Number of layers configured (1-12)
75003      1       Reserved
75004      1750    Layer 0 DKS config (70 keys × 25 bytes)
75754      ...     Layer 1-11 (future expansion)
```

---

## 4. STATE TRACKING (Runtime)

### Per-Key DKS State
```c
typedef struct {
    uint8_t last_travel;       // Last travel position (0-240)
    uint8_t current_stage;     // Which press/release actions have been triggered
    bool press_active[4];      // Which press actions are currently active
    bool release_active[4];    // Which release actions are currently active
    bool key_down;             // Is physical key currently down?
} dks_state_t;

// Global state array
static dks_state_t dks_states[70];
```

---

## 5. MATRIX SCANNING INTEGRATION

### Detection Logic (in matrix.c)

Similar to MIDI key detection, add DKS detection:

```c
// After line 152 in matrix.c
static midi_key_state_t midi_key_states[MATRIX_ROWS][MATRIX_COLS];
static dks_state_t      dks_key_states[MATRIX_ROWS][MATRIX_COLS];  // NEW
static bool             dks_states_initialized = false;             // NEW
```

### Initialization (during matrix_init())

```c
// Similar to midi_key_states initialization around line 754
void init_dks_states(void) {
    for (uint8_t row = 0; row < MATRIX_ROWS; row++) {
        for (uint8_t col = 0; col < MATRIX_COLS; col++) {
            uint16_t keycode = dynamic_keymap_get_keycode(current_layer, row, col);

            if (keycode >= DKS_KEY_BASE && keycode <= DKS_KEY_MAX) {
                uint8_t dks_index = keycode - DKS_KEY_BASE;
                dks_state_t *state = &dks_key_states[row][col];

                state->is_dks_key = true;
                state->dks_index = dks_index;
                state->last_travel = 0;
                state->current_stage = 0;
                // ... init other fields
            }
        }
    }
    dks_states_initialized = true;
}
```

### Scanning Logic (in matrix_scan())

```c
// Add after MIDI processing (around line 910-913)
if (dks_states_initialized) {
    for (uint8_t row = 0; row < MATRIX_ROWS; row++) {
        for (uint8_t col = 0; col < MATRIX_COLS; col++) {
            if (dks_key_states[row][col].is_dks_key) {
                process_dks_key_analog(row, col);
            }
        }
    }
}
```

---

## 6. DKS PROCESSING ALGORITHM

### Core Logic

```c
static void process_dks_key_analog(uint8_t row, uint8_t col) {
    dks_state_t *state = &dks_key_states[row][col];
    analog_key_t *key = &keys[row][col];

    uint8_t travel = key->travel;
    uint8_t current_layer = get_highest_layer(layer_state);
    dks_config_t *config = &dks_configs[0].keys[state->dks_index];  // Layer 0 for now

    if (!config->enabled) return;

    bool is_going_down = (travel > state->last_travel);
    bool is_going_up = (travel < state->last_travel);

    // Process PRESS actions (downstroke)
    if (is_going_down) {
        for (uint8_t i = 0; i < 4; i++) {
            dks_action_t *action = &config->press[i];
            if (action->keycode == 0) continue;  // Disabled slot

            // Convert actuation point to internal travel units
            uint8_t threshold = (action->actuation_point * FULL_TRAVEL_UNIT * TRAVEL_SCALE) / 100;

            // Check if we crossed this threshold
            if (state->last_travel < threshold && travel >= threshold) {
                // Trigger this action!
                trigger_dks_action(action, true, row, col, i);
                state->press_active[i] = true;
            }
        }
    }

    // Process RELEASE actions (upstroke)
    if (is_going_up) {
        for (uint8_t i = 0; i < 4; i++) {
            dks_action_t *action = &config->release[i];
            if (action->keycode == 0) continue;

            uint8_t threshold = (action->actuation_point * FULL_TRAVEL_UNIT * TRAVEL_SCALE) / 100;

            // Check if we crossed this threshold going UP
            if (state->last_travel > threshold && travel <= threshold) {
                trigger_dks_action(action, false, row, col, i);
                state->release_active[i] = true;
            }
        }

        // Also handle PRESS action releases (for TAP and PRESS behaviors)
        for (uint8_t i = 0; i < 4; i++) {
            if (!state->press_active[i]) continue;

            dks_action_t *action = &config->press[i];
            uint8_t threshold = (action->actuation_point * FULL_TRAVEL_UNIT * TRAVEL_SCALE) / 100;

            // If going back up past this threshold, release it
            if (travel < threshold) {
                release_dks_action(action, row, col, i);
                state->press_active[i] = false;
            }
        }
    }

    state->last_travel = travel;
}
```

### Action Triggering

```c
static void trigger_dks_action(dks_action_t *action, bool is_press, uint8_t row, uint8_t col, uint8_t action_idx) {
    switch (action->behavior) {
        case DKS_BEHAVIOR_TAP:
            // Send both press AND release immediately
            tap_code16(action->keycode);
            break;

        case DKS_BEHAVIOR_PRESS:
            // Send press only (hold)
            register_code16(action->keycode);
            break;

        case DKS_BEHAVIOR_RELEASE:
            // Only send release (for upstroke actions)
            unregister_code16(action->keycode);
            break;
    }
}

static void release_dks_action(dks_action_t *action, uint8_t row, uint8_t col, uint8_t action_idx) {
    // Only matters for PRESS behavior
    if (action->behavior == DKS_BEHAVIOR_PRESS) {
        unregister_code16(action->keycode);
    }
}
```

---

## 7. GUI IMPLEMENTATION

### Python Side (matrix_test.py or new dks_editor.py)

Create a DKS configuration UI similar to Wooting's interface:

```python
class DKSEditor(QWidget):
    def __init__(self, keyboard):
        # ...
        self.create_dks_interface()

    def create_dks_interface(self):
        # Key selector dropdown
        self.key_selector = QComboBox()
        for i in range(70):
            self.key_selector.addItem(f"Key {i} (Row {i//14}, Col {i%14})")

        # Enable/disable checkbox
        self.dks_enabled = QCheckBox("Enable DKS for this key")

        # Press actions (4 bindings)
        self.press_group = self.create_action_group("Key Press", 4)

        # Release actions (4 bindings)
        self.release_group = self.create_action_group("Key Release", 4)

    def create_action_group(self, title, num_actions):
        group = QGroupBox(title)
        layout = QVBoxLayout()

        for i in range(num_actions):
            action_row = QHBoxLayout()

            # Actuation point slider (with mm display)
            actuation = QSlider(Qt.Horizontal)
            actuation.setRange(0, 100)  # 0-2.5mm
            actuation_label = QLabel("1.5mm")

            # Keycode selector
            keycode_combo = QComboBox()
            keycode_combo.addItems(["None", "KC_A", "KC_B", ...])

            # Behavior selector
            behavior_combo = QComboBox()
            behavior_combo.addItems(["Tap", "Press", "Release"])

            action_row.addWidget(QLabel(f"Action {i+1}:"))
            action_row.addWidget(actuation)
            action_row.addWidget(actuation_label)
            action_row.addWidget(keycode_combo)
            action_row.addWidget(behavior_combo)

            layout.addLayout(action_row)

        group.setLayout(layout)
        return group
```

### HID Protocol

Add new HID commands:

```c
// In process_dynamic_macro.c (HID command section)
#define HID_CMD_SET_DKS_CONFIG      0xDF  // Set DKS config for a key
#define HID_CMD_GET_DKS_CONFIG      0xE0  // Get DKS config for a key
#define HID_CMD_ENABLE_DKS_KEY      0xE1  // Enable/disable DKS for a key
#define HID_CMD_RESET_DKS           0xE2  // Reset all DKS configs
#define HID_CMD_SAVE_DKS_EEPROM     0xE3  // Save DKS to EEPROM
#define HID_CMD_LOAD_DKS_EEPROM     0xE4  // Load DKS from EEPROM
```

**Packet Format (HID_CMD_SET_DKS_CONFIG):**
```
Byte 0:    Key index (0-69)
Byte 1:    Action index (0-7: 0-3=press, 4-7=release)
Byte 2-3:  Keycode (uint16_t)
Byte 4:    Actuation point (0-100)
Byte 5:    Behavior (0=tap, 1=press, 2=release)
```

---

## 8. ADVANTAGES OF THIS APPROACH

### ✅ **Leverages Existing Patterns**
- Uses same flag-based detection as MIDI keys
- Same EEPROM pattern as per-key actuation
- Same keycode range detection as custom keycodes

### ✅ **Minimal Matrix Impact**
- DKS keys are excluded from normal actuation (like MIDI keys)
- No keycode collision with normal keys
- Clean separation of concerns

### ✅ **Scalable**
- Start with 1 layer (1.75KB)
- Expand to 12 layers when needed (21KB total)
- Can reduce to 2 actions/stage if memory constrained

### ✅ **Wooting-Compatible Features**
- 4 actions on press (like Wooting's 4 bindings)
- 4 actions on release (EXCEEDS Wooting - they only have 2 release points)
- Per-action behavior control (tap/press/release)
- Visual actuation point configuration

---

## 9. IMPLEMENTATION PHASES

### Phase 1: Core Infrastructure
1. Define keycode range (DKS_KEY_BASE)
2. Create data structures (dks_config_t, dks_state_t)
3. Add EEPROM layout and save/load functions
4. Implement init_dks_states() in matrix.c

### Phase 2: Processing Logic
1. Implement process_dks_key_analog()
2. Implement trigger_dks_action() and release_dks_action()
3. Add state tracking and threshold crossing detection
4. Test with simple 1-action configuration

### Phase 3: GUI
1. Create DKS editor UI in Python
2. Implement HID protocol commands
3. Add visual actuation point sliders
4. Test full configuration workflow

### Phase 4: Polish
1. Add EEPROM persistence
2. Add per-layer support (expand to 12 layers)
3. Add preset system (save/load DKS profiles)
4. Documentation and testing

---

## 10. QUESTIONS FOR YOU

Before implementation, I need clarification on:

### A. **Layer Scope**
- Should DKS configurations be **per-layer** (like per-key actuation)?
- Or **global** (same DKS config regardless of layer)?
- **Recommendation:** Start with global (simpler), add per-layer later if needed

### B. **Keycode Assignment**
- How will users assign DKS keycodes to physical keys?
- Via Vial GUI keymap editor? Or via dedicated DKS editor?
- **Recommendation:** DKS editor assigns the DKS_XX keycode automatically when you enable DKS for a key

### C. **Memory Constraints**
- Current EEPROM has 32KB total. We're using ~15KB currently.
- 21KB for all 12 layers might be tight.
- **Options:**
  - Start with 1-2 layers (3.5KB)
  - Reduce to 2 actions per stage (10.5KB for 12 layers)
  - Compress actuation points (use 4 bits instead of 8)

### D. **Interaction with MIDI Keys**
- Can a key be BOTH a MIDI key AND a DKS key?
- **Recommendation:** Mutually exclusive - either MIDI or DKS, not both

### E. **Rapid Trigger Interaction**
- Should DKS keys support Rapid Trigger?
- **Recommendation:** No - DKS handles its own re-triggering logic via multiple actuation points

### F. **Visual Representation**
- Should the GUI show a visual "travel bar" like Wooting?
- With 4 press + 4 release markers on it?
- **Recommendation:** Yes - very helpful for understanding actuation points

---

## 11. ALTERNATE APPROACH (If Memory Constrained)

If 25 bytes/key is too much, we can use a **compact encoding**:

```c
typedef struct {
    uint16_t keycodes[4];      // 4 keycodes (8 bytes)
    uint8_t actuation_press;   // Packed: 4×2 bits for 4 press points (0-3 scale)
    uint8_t actuation_release; // Packed: 4×2 bits for 4 release points
    uint8_t behaviors;         // Packed: 8×2 bits for behaviors (4 press + 4 release)
    uint8_t enabled_mask;      // 8 bits for which actions are enabled
} compact_dks_config_t;  // 12 bytes instead of 25
```

This reduces storage to:
- 12 bytes/key × 70 keys = **840 bytes/layer**
- 12 layers × 840 bytes = **10KB total** (much more manageable!)

Trade-off: Only 4 discrete actuation points (0.0mm, 0.83mm, 1.67mm, 2.5mm) instead of full 0-100 range.

---

## 12. FINAL RECOMMENDATION

**Start with FULL PRECISION approach:**
- 1 layer only (1.75KB)
- Full 0-100 actuation point range
- 4 press + 4 release actions
- TAP/PRESS/RELEASE behaviors
- Simple GUI with sliders

**Then expand based on user feedback:**
- Add more layers if memory allows
- Optimize to compact encoding if needed
- Add visual travel display
- Add preset save/load

---

Ready to proceed with implementation? Please answer the questions in Section 10, and I'll start coding!
