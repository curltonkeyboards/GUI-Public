# DKS (Dynamic Keystroke) Complete Implementation Analysis
## orthomidi5x14 Firmware

## Status: ✓ **FULLY IMPLEMENTED AND OPERATIONAL**

I was initially incorrect - DKS is **fully implemented** in both the QMK quantum layer and integrated into the orthomidi5x14 firmware!

---

## What are DKS Keys?

**DKS (Dynamic Keystroke)** keys are **multi-action analog keys** that can trigger up to **8 different actions** based on analog travel depth:
- **4 press actions** (triggered on downstroke at different travel depths)
- **4 release actions** (triggered on upstroke at different travel depths)

### Key Files:
- **`quantum/process_keycode/process_dks.c`** - Core DKS processing logic
- **`quantum/process_keycode/process_dks.h`** - DKS API and data structures
- **`quantum/matrix.c`** - Analog matrix scanning with DKS integration (lines 893-894, 923-934, 947-953)

---

## DKS Data Structures

### 1. DKS Slot Configuration (32 bytes per slot, 50 slots total)

```c
typedef struct {
    // Press actions (downstroke) - 16 bytes
    uint16_t press_keycode[4];      // Keycodes to send at each threshold
    uint8_t  press_actuation[4];    // Actuation points (0-100 = 0-2.5mm)

    // Release actions (upstroke) - 16 bytes
    uint16_t release_keycode[4];    // Keycodes to send at each threshold
    uint8_t  release_actuation[4];  // Actuation points (0-100 = 0-2.5mm)

    // Behaviors - 2 bytes (bit-packed: 2 bits × 8 actions = 16 bits)
    uint16_t behaviors;             // TAP, PRESS, or RELEASE for each action

    // Reserved - 6 bytes
    uint8_t  reserved[6];
} dks_slot_t;  // Exactly 32 bytes
```

**Total Memory:** 50 slots × 32 bytes = **1,600 bytes**

### 2. DKS Behavior Types

```c
typedef enum {
    DKS_BEHAVIOR_TAP     = 0,  // Press + immediate release (default)
    DKS_BEHAVIOR_PRESS   = 1,  // Press and hold until key released
    DKS_BEHAVIOR_RELEASE = 2,  // Release only (for upstroke actions)
    DKS_BEHAVIOR_NONE    = 3   // Reserved/disabled
} dks_behavior_t;
```

### 3. DKS State Tracking (Per Physical Key Position)

```c
typedef struct {
    uint8_t  dks_slot;              // Which DKS slot (0-49)
    uint8_t  last_travel;           // Last travel position (0-240 internal units)
    uint8_t  press_triggered;       // Bitmask: which press actions triggered
    uint8_t  release_triggered;     // Bitmask: which release actions triggered
    uint16_t active_keycodes;       // Bitmask: which keycodes are held down
    bool     is_dks_key;            // Is this physical key a DKS key?
    bool     key_was_down;          // Was key down on last scan?
} dks_state_t;
```

**State Array:** `dks_state_t dks_states[MATRIX_ROWS][MATRIX_COLS]`

---

## COMPLETE DKS PATHWAY FLOWCHART

```
┌─────────────────────────────────────────────────────────────┐
│              KEYBOARD INITIALIZATION (Boot)                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
          ┌──────────────────────────────┐
          │  matrix_init_custom()        │
          │  (quantum/matrix.c:797)      │
          └──────────┬───────────────────┘
                     │
                     ↓
          ┌──────────────────────────────┐
          │  dks_init()                  │
          │  (line 894)                  │
          ├──────────────────────────────┤
          │  • Clear all DKS states      │
          │  • Load configs from EEPROM  │
          │  • If not found, set defaults│
          └──────────┬───────────────────┘
                     │
                     ↓
          ┌──────────────────────────────┐
          │  DKS System Ready            │
          │  • 50 slots initialized      │
          │  • States cleared            │
          └──────────────────────────────┘

═══════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────┐
│           EVERY MATRIX SCAN CYCLE (~1-5ms)                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
          ┌──────────────────────────────┐
          │  matrix_scan_custom()        │
          │  (quantum/matrix.c:897)      │
          └──────────┬───────────────────┘
                     │
                     ↓
          ┌──────────────────────────────┐
          │  analog_matrix_task_internal()│
          │  • Read all ADC values       │
          │  • Calculate travel for all  │
          │  • Update key states         │
          └──────────┬───────────────────┘
                     │
                     ↓
          ┌──────────────────────────────┐
          │  Get current layer           │
          └──────────┬───────────────────┘
                     │
                     ↓
          ┌──────────────────────────────┐
          │  For each key (row, col):    │
          └──────────┬───────────────────┘
                     │
                     ↓
╔═════════════════════════════════════════════════════════════╗
║              DKS KEY DETECTION (lines 923-934)              ║
╠═════════════════════════════════════════════════════════════╣
║                                                             ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  keycode = get_keycode(layer, row, col)         │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  if (is_dks_keycode(keycode))                   │      ║
║  │     // keycode >= 0xED00 && <= 0xED31          │      ║
║  └────────────┬────────────────────┬────────────────┘      ║
║               │ NO                 │ YES                    ║
║               │                    │                        ║
║               ↓                    ↓                        ║
║  [Skip - Regular Key]  ┌───────────────────────────┐      ║
║                        │  This is a DKS key!       │      ║
║                        │  Call dks_process_key()   │      ║
║                        │  (line 931)               │      ║
║                        └────────────┬──────────────┘      ║
║                                     │                       ║
╚═════════════════════════════════════╪═══════════════════════╝
                                      │
                                      ↓
╔═════════════════════════════════════════════════════════════╗
║          DKS_PROCESS_KEY (process_dks.c:391)                ║
╠═════════════════════════════════════════════════════════════╣
║  Parameters:                                                ║
║  • row, col: Physical position                              ║
║  • travel: Current travel (0-240 internal units)            ║
║  • keycode: DKS keycode (0xED00-0xED31)                     ║
╠═════════════════════════════════════════════════════════════╣
║                                                             ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  slot_num = keycode - 0xED00  (0-49)            │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  state = &dks_states[row][col]                  │      ║
║  │  slot = &dks_slots[slot_num]                    │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  if (!state->is_dks_key)                        │      ║
║  │     // First time seeing this key               │      ║
║  │     Initialize state, return                    │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  Determine direction:                           │      ║
║  │  going_down = (travel > last_travel)            │      ║
║  │  going_up = (travel < last_travel)              │      ║
║  └────────────┬────────────────┬────────────────────┘      ║
║               │                │                            ║
║      going_down│                │going_up                   ║
║               ↓                ↓                            ║
║  ┌──────────────────┐  ┌──────────────────────┐          ║
║  │  Process Press   │  │  Process Release     │          ║
║  │  Actions         │  │  Actions             │          ║
║  │  (downstroke)    │  │  (upstroke)          │          ║
║  └────────┬─────────┘  └─────────┬────────────┘          ║
║           │                      │                         ║
╚═══════════╪══════════════════════╪═════════════════════════╝
            │                      │
            ↓                      ↓
   [Process Press Actions]  [Process Release Actions]

═══════════════════════════════════════════════════════════════

╔═════════════════════════════════════════════════════════════╗
║           PROCESS PRESS ACTIONS (downstroke)                ║
║           (process_dks.c:292)                               ║
╠═════════════════════════════════════════════════════════════╣
║                                                             ║
║  For each of 4 press actions (i = 0 to 3):                 ║
║                                                             ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  if (already triggered)                         │      ║
║  │     skip                                        │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │ not triggered                       ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  if (keycode == KC_NO)                          │      ║
║  │     skip (disabled action)                      │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │ enabled                             ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  threshold = convert(press_actuation[i])        │      ║
║  │  // User value 0-100 → internal 0-240          │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  if (last_travel < threshold &&                 │      ║
║  │      travel >= threshold)                       │      ║
║  │     // Crossed threshold going down!            │      ║
║  └────────────┬────────────────────┬────────────────┘      ║
║               │ NO                 │ YES                    ║
║               ↓                    ↓                        ║
║     [Skip to next action]  ┌──────────────────────┐       ║
║                            │  Get behavior from   │       ║
║                            │  packed uint16_t     │       ║
║                            └─────────┬────────────┘       ║
║                                      │                     ║
║                                      ↓                     ║
║                            ┌──────────────────────┐       ║
║                            │  trigger_action()    │       ║
║                            │  (process_dks.c:249) │       ║
║                            └─────────┬────────────┘       ║
║                                      │                     ║
╚══════════════════════════════════════╪═══════════════════════╝
                                       │
                                       ↓
╔═════════════════════════════════════════════════════════════╗
║              TRIGGER_ACTION (process_dks.c:249)             ║
╠═════════════════════════════════════════════════════════════╣
║  Parameters:                                                ║
║  • keycode: What to send (e.g., KC_A, MI_C, etc.)          ║
║  • behavior: How to send it (TAP/PRESS/RELEASE)            ║
╠═════════════════════════════════════════════════════════════╣
║                                                             ║
║  switch (behavior):                                         ║
║                                                             ║
║  ┌─────────────────────┐                                   ║
║  │  DKS_BEHAVIOR_TAP   │                                   ║
║  ├─────────────────────┤                                   ║
║  │  tap_code16(keycode)│  ← Press + Immediate Release     ║
║  │  // Instant tap     │                                   ║
║  └─────────────────────┘                                   ║
║                                                             ║
║  ┌─────────────────────┐                                   ║
║  │  DKS_BEHAVIOR_PRESS │                                   ║
║  ├─────────────────────┤                                   ║
║  │  register_code16()  │  ← Press and HOLD                ║
║  │  // Stays pressed   │     (Released when travel goes   ║
║  │  // Track as active │      back above threshold OR     ║
║  │                     │      on full key release)        ║
║  └─────────────────────┘                                   ║
║                                                             ║
║  ┌─────────────────────┐                                   ║
║  │  DKS_BEHAVIOR_RELEASE│                                  ║
║  ├─────────────────────┤                                   ║
║  │  unregister_code16()│  ← Release only (for upstrokes)  ║
║  │  // Release keycode │                                   ║
║  └─────────────────────┘                                   ║
║                                                             ║
║  After triggering:                                          ║
║  • Mark action as triggered                                 ║
║  • If PRESS behavior, track as active keycode               ║
║                                                             ║
╚═════════════════════════════════════════════════════════════╝

═══════════════════════════════════════════════════════════════

╔═════════════════════════════════════════════════════════════╗
║          PROCESS RELEASE ACTIONS (upstroke)                 ║
║          (process_dks.c:327)                                ║
╠═════════════════════════════════════════════════════════════╣
║                                                             ║
║  For each of 4 release actions (i = 0 to 3):               ║
║                                                             ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  threshold = convert(release_actuation[i])      │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  if (last_travel > threshold &&                 │      ║
║  │      travel <= threshold)                       │      ║
║  │     // Crossed threshold going UP!              │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │ YES                                 ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  behavior = get_behavior(slot, i + 4)           │      ║
║  │  // Release actions are indices 4-7             │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  trigger_action(release_keycode[i], behavior)   │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  Mark release action as triggered               │      ║
║  └─────────────────────────────────────────────────┘      ║
║                                                             ║
╚═════════════════════════════════════════════════════════════╝

═══════════════════════════════════════════════════════════════

╔═════════════════════════════════════════════════════════════╗
║          CLEANUP PRESS ACTIONS (process_dks.c:362)          ║
╠═════════════════════════════════════════════════════════════╣
║  When going up, check if any PRESS actions should release: ║
║                                                             ║
║  For each press action with PRESS behavior:                 ║
║                                                             ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  if (travel < threshold)                        │      ║
║  │     // Went back above threshold                │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │ YES                                 ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  unregister_code16(press_keycode[i])            │      ║
║  │  Clear triggered and active flags               │      ║
║  └─────────────────────────────────────────────────┘      ║
║                                                             ║
║  This allows held keys to release when you ease off       ║
╚═════════════════════════════════════════════════════════════╝

═══════════════════════════════════════════════════════════════

╔═════════════════════════════════════════════════════════════╗
║          FULL RELEASE DETECTION (process_dks.c:436-443)     ║
╠═════════════════════════════════════════════════════════════╣
║                                                             ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  key_is_down = (travel > 0.125mm)               │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  if (was_down && !is_down)                      │      ║
║  │     // Key fully released!                      │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │ YES                                 ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  Reset all triggered flags                      │      ║
║  │  • press_triggered = 0                          │      ║
║  │  • release_triggered = 0                        │      ║
║  │  (Keep active_keycodes for held PRESS actions) │      ║
║  └─────────────────────────────────────────────────┘      ║
║                                                             ║
║  This allows actions to re-trigger on next press          ║
╚═════════════════════════════════════════════════════════════╝
```

---

## DKS Integration with Actuation System

### Matrix Processing Priority (quantum/matrix.c:947-965)

```
For each key:
1. Get keycode at current layer position
2. Check if keycode is DKS (0xED00-0xED31)

   ├─ YES: DKS Key
   │   ├─ Call dks_process_key()
   │   ├─ DKS handles all actions internally
   │   └─ Set matrix pressed = FALSE (DKS manages its own keycodes)
   │
   └─ NO: Regular Key
       ├─ Check if MIDI key
       │   └─ Use MIDI velocity processing
       └─ Use normal actuation point
           └─ Use per-key actuation if enabled
```

**Key Point:** DKS keys **bypass normal matrix processing** entirely! They don't use per-key actuation settings - they have their own zone-based system.

---

## Example: DKS_00 Configuration

Let's configure DKS slot 0 (keycode DKS_00 = 0xED00) as a progressive chord pad:

```c
dks_slot_t config = {
    // Press actions (downstroke)
    .press_keycode = {
        KC_A,        // Action 0: Send 'A'
        MI_C,        // Action 1: Send MIDI C note
        MI_E,        // Action 2: Send MIDI E note
        MI_G         // Action 3: Send MIDI G note
    },
    .press_actuation = {
        24,          // Action 0: 0.6mm
        48,          // Action 1: 1.2mm
        72,          // Action 2: 1.8mm
        96           // Action 3: 2.4mm
    },

    // Release actions (upstroke)
    .release_keycode = {
        KC_Z,        // Action 0: Send 'Z' when releasing from 2.4mm
        KC_Y,        // Action 1: Send 'Y' when releasing from 1.8mm
        KC_X,        // Action 2: Send 'X' when releasing from 1.2mm
        KC_W         // Action 3: Send 'W' when releasing from 0.6mm
    },
    .release_actuation = {
        96,          // Action 0: 2.4mm
        72,          // Action 1: 1.8mm
        48,          // Action 2: 1.2mm
        24           // Action 3: 0.6mm
    },

    // Behaviors (bit-packed in uint16_t)
    // Press actions: TAP, PRESS, PRESS, TAP
    // Release actions: TAP, TAP, TAP, RELEASE
    .behaviors = 0x0065  // Binary: 0000 0000 0110 0101
    // Bits 0-1:   01 = PRESS  (A held down)
    // Bits 2-3:   01 = PRESS  (MI_C held)
    // Bits 4-5:   01 = PRESS  (MI_E held)
    // Bits 6-7:   00 = TAP    (MI_G tapped)
    // Bits 8-9:   00 = TAP    (Z tapped)
    // Bits 10-11: 00 = TAP    (Y tapped)
    // Bits 12-13: 00 = TAP    (X tapped)
    // Bits 14-15: 10 = RELEASE (W released only)
};

dks_set_slot(0, &config);
```

### What Happens When You Press DKS_00:

```
Press downstroke:
  0.6mm  → 'A' registers and HOLDS
  1.2mm  → MIDI C registers and HOLDS
  1.8mm  → MIDI E registers and HOLDS
  2.4mm  → MIDI G taps instantly

Now you're holding: A, MI_C, MI_E (creating C major chord!)

Release upstroke:
  2.4mm  → 'Z' taps
  1.8mm  → 'Y' taps
  1.2mm  → 'X' taps
  0.6mm  → All PRESS actions auto-release (A, MI_C, MI_E)
  0.6mm  → 'W' unregisters (but it was never registered - RELEASE only)

Total: 8 different actions from one keypress!
```

---

## Comparison: DKS vs Per-Key Actuation vs Regular Keys

| Feature | Regular Key | Per-Key Actuation | DKS Key |
|---------|-------------|-------------------|---------|
| **Actions per key** | 1 | 1 | Up to 8 |
| **Actuation points** | Layer-wide | 1 per key | 4 press + 4 release |
| **Behaviors** | TAP only | TAP only | TAP, PRESS, RELEASE |
| **Direction aware** | No | No | Yes (press/release) |
| **Deadzones** | No | Yes (per-key) | No (uses thresholds) |
| **Rapidfire** | No | Yes (per-key) | No (DKS actions are discrete) |
| **Velocity** | Yes (MIDI keys) | Yes (per-key curve) | No (DKS sends keycodes) |
| **Memory per key** | 0 bytes | 8 bytes | 0 (stored in slot, not per-key) |
| **Use case** | Simple keys | Fine-tuned feel | Multi-action expression |
| **Status** | ✓ Implemented | ✓ Implemented | ✓ Implemented |

---

## Configuration and EEPROM

### EEPROM Layout:
- **Base Address:** 75000
- **Magic Number:** 0xDC57
- **Version:** 0x01
- **Total Size:** 4 bytes (header) + 1600 bytes (50 × 32) = **1604 bytes**

### Functions:
- `dks_save_to_eeprom()` - Save all 50 slots
- `dks_load_from_eeprom()` - Load all 50 slots
- `dks_reset_all_slots()` - Reset to defaults

### Default Configuration:
All slots initialized with:
- Press actuations: 24, 48, 72, 96 (0.6mm, 1.2mm, 1.8mm, 2.4mm)
- Release actuations: 96, 72, 48, 24 (mirror)
- All keycodes: KC_NO (disabled)
- All behaviors: TAP

---

## When DKS Keys are Processed

From `quantum/matrix.c:923-934`:

```c
// Process DKS keys
for (uint8_t row = 0; row < MATRIX_ROWS; row++) {
    for (uint8_t col = 0; col < MATRIX_COLS; col++) {
        uint16_t keycode = dynamic_keymap_get_keycode(current_layer, row, col);

        // Check if this is a DKS keycode
        if (is_dks_keycode(keycode)) {
            analog_key_t *key = &keys[row][col];
            dks_process_key(row, col, key->travel, keycode);
        }
    }
}
```

**Processing Order per Matrix Scan:**
1. Analog matrix read (all ADCs)
2. Travel calculation (all keys)
3. State updates (all keys)
4. MIDI key analog processing
5. **DKS key processing** ← HERE
6. Matrix generation (for QMK)

**Frequency:** Every matrix scan (~1-5ms depending on scan rate)

---

## Summary

### DKS Keys are FULLY OPERATIONAL with:

✓ **50 configurable slots** (DKS_00 through DKS_49)
✓ **8 actions per slot** (4 press + 4 release)
✓ **3 behavior types** (TAP, PRESS, RELEASE)
✓ **Analog threshold detection** (0-2.5mm travel)
✓ **Direction awareness** (downstroke vs upstroke)
✓ **State tracking** (per physical key position)
✓ **EEPROM persistence** (save/load configurations)
✓ **Matrix integration** (called every scan cycle)
✓ **Bypasses normal processing** (manages own keycodes)

### Use Cases:
- **Progressive chords**: Build chords as you press deeper
- **Expression pads**: Different sounds at different depths
- **Gaming triggers**: Light = walk, deep = sprint
- **Macro sequences**: Different macros per zone
- **Layer switching**: Change layers mid-press
- **Creative workflows**: Depth-sensitive shortcuts

### Next Steps for Users:
1. Assign a DKS keycode (0xED00-0xED31) to a physical key
2. Configure the slot via HID commands (requires GUI support)
3. Set actuation thresholds for each of 8 actions
4. Assign keycodes (or MIDI notes) to each action
5. Choose behaviors (TAP/PRESS/RELEASE)
6. Save to EEPROM

**DKS keys represent a completely different paradigm from traditional keyboards - true analog multi-action keys!**
