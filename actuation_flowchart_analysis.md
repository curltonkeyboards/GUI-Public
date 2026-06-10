# Actuation Point Flowchart Analysis
## orthomidi5x14 Firmware - Per-Key vs Non Per-Key Actuation

This document provides detailed flowcharts showing how the firmware handles actuation differently when per-key actuation mode is enabled versus disabled.

---

## Key Data Structures

### 1. Layer-Wide Actuation (Traditional Mode)
```c
typedef struct {
    uint8_t normal_actuation;      // 0-100 (0-2.5mm) - for normal keys
    uint8_t midi_actuation;        // 0-100 (0-2.5mm) - for MIDI keys
    uint8_t velocity_mode;         // 0=Fixed, 1=Peak, 2=Speed, 3=Speed+Peak
    uint8_t velocity_speed_scale;  // 1-20 (velocity scale multiplier)
    uint8_t flags;                 // Various flags
} layer_actuation_t;

layer_actuation_t layer_actuations[12];  // One per layer
```

### 2. Per-Key Actuation (Advanced Mode)
```c
typedef struct {
    uint8_t actuation;              // 0-100 (0-2.5mm) - actuation point
    uint8_t deadzone_top;           // 0-100 (0-2.5mm) - top deadzone
    uint8_t deadzone_bottom;        // 0-100 (0-2.5mm) - bottom deadzone
    uint8_t velocity_curve;         // 0-16 (curve index)
    uint8_t flags;                  // Bit 0: rapidfire_enabled, Bit 1: use_per_key_velocity_curve
    uint8_t rapidfire_press_sens;   // 0-100 (0-2.5mm)
    uint8_t rapidfire_release_sens; // 0-100 (0-2.5mm)
    int8_t  rapidfire_velocity_mod; // -64 to +64 (velocity offset)
} per_key_actuation_t;  // 8 bytes per key

typedef struct {
    per_key_actuation_t keys[70];  // 70 keys × 8 bytes = 560 bytes per layer
} layer_key_actuations_t;

layer_key_actuations_t per_key_actuations[12];  // 6720 bytes total (12 layers)
```

### 3. Global Mode Flags
```c
bool per_key_mode_enabled = false;        // Master switch for per-key mode
bool per_key_per_layer_enabled = false;   // Use different settings per layer
```

---

## FLOWCHART 1: NON PER-KEY ACTUATION MODE
**Condition: `per_key_mode_enabled == false`**

```
┌─────────────────────────────────────────────────────────────┐
│                 MATRIX SCAN (Every Cycle)                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
          ┌──────────────────────────────┐
          │  For each key (row, col)     │
          └──────────┬───────────────────┘
                     │
                     ↓
          ┌──────────────────────────────┐
          │  Read analog travel value    │
          │  (0-100 range, 0-2.5mm)      │
          └──────────┬───────────────────┘
                     │
                     ↓
          ┌──────────────────────────────┐
          │  Get current layer number    │
          │  layer = get_highest_layer() │
          └──────────┬───────────────────┘
                     │
                     ↓
╔═════════════════════════════════════════════════════════════╗
║     CALL: get_key_actuation_point(layer, row, col)         ║
╠═════════════════════════════════════════════════════════════╣
║                                                             ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  Check: if (!per_key_mode_enabled)              │      ║
║  │         TRUE → NON PER-KEY MODE                 │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  RETURN: layer_actuations[layer].midi_actuation │      ║
║  │                                                  │      ║
║  │  ** This is the SAME value for ALL keys **      │      ║
║  │  ** on this layer **                            │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
╚═══════════════════════╪═════════════════════════════════════╝
                        │
                        ↓ (returns actuation_point)
          ┌──────────────────────────────┐
          │  Compare travel vs actuation │
          │                              │
          │  if (travel > actuation):    │
          │      Key is PRESSED          │
          │  else:                       │
          │      Key is RELEASED         │
          └──────────┬───────────────────┘
                     │
                     ↓
     ┌───────────────┴────────────────┐
     │                                │
     ↓ PRESSED                        ↓ RELEASED
┌─────────────────┐           ┌─────────────────┐
│  Trigger Note   │           │  Release Note   │
│  ON event       │           │  OFF event      │
└─────────┬───────┘           └─────────┬───────┘
          │                             │
          ↓                             ↓
┌─────────────────────────────────────────────────┐
│  Get Velocity (if MIDI key)                     │
│  velocity = get_he_velocity_from_position()     │
│                                                 │
│  ** Uses layer_actuations[layer] settings **   │
│  ** for velocity calculation mode **           │
└─────────────────────────────────────────────────┘
```

### Key Characteristics of Non Per-Key Mode:
1. **Single Actuation Point**: All 70 keys on a layer use `layer_actuations[layer].midi_actuation`
2. **No Per-Key Customization**: Cannot set different actuation points for individual keys
3. **Simpler Logic**: Fast lookup, minimal memory access
4. **Global Layer Settings**: All keys share velocity mode, velocity scaling, and other settings
5. **Memory Efficient**: Only 12 layer_actuation_t structs (small memory footprint)

---

## FLOWCHART 2: PER-KEY ACTUATION MODE
**Condition: `per_key_mode_enabled == true`**

```
┌─────────────────────────────────────────────────────────────┐
│                 MATRIX SCAN (Every Cycle)                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
          ┌──────────────────────────────┐
          │  For each key (row, col)     │
          └──────────┬───────────────────┘
                     │
                     ↓
          ┌──────────────────────────────┐
          │  Read analog travel value    │
          │  (0-100 range, 0-2.5mm)      │
          └──────────┬───────────────────┘
                     │
                     ↓
          ┌──────────────────────────────┐
          │  Get current layer number    │
          │  layer = get_highest_layer() │
          └──────────┬───────────────────┘
                     │
                     ↓
╔═════════════════════════════════════════════════════════════╗
║     CALL: get_key_actuation_point(layer, row, col)         ║
╠═════════════════════════════════════════════════════════════╣
║                                                             ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  Check: if (!per_key_mode_enabled)              │      ║
║  │         FALSE → PER-KEY MODE ACTIVE             │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  Calculate key_index = row * 14 + col           │      ║
║  │  (Maps 2D position to linear array index)       │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
║                       ↓                                     ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  Check: if (per_key_per_layer_enabled)          │      ║
║  └────────────┬────────────────────┬────────────────┘      ║
║               │                    │                        ║
║          TRUE │                    │ FALSE                  ║
║               ↓                    ↓                        ║
║  ┌──────────────────────┐  ┌─────────────────────┐        ║
║  │ target_layer = layer │  │ target_layer = 0    │        ║
║  │                      │  │ (always use layer 0)│        ║
║  │ (use current layer) │  │                     │        ║
║  └──────────┬───────────┘  └──────────┬──────────┘        ║
║             │                         │                    ║
║             └──────────┬──────────────┘                    ║
║                        │                                    ║
║                        ↓                                    ║
║  ┌─────────────────────────────────────────────────┐      ║
║  │  RETURN: per_key_actuations[target_layer]       │      ║
║  │                    .keys[key_index]              │      ║
║  │                    .actuation                    │      ║
║  │                                                  │      ║
║  │  ** Unique value for THIS specific key **       │      ║
║  └────────────────────┬────────────────────────────┘      ║
║                       │                                     ║
╚═══════════════════════╪═════════════════════════════════════╝
                        │
                        ↓ (returns per-key actuation_point)
          ┌──────────────────────────────┐
          │  Compare travel vs actuation │
          │                              │
          │  if (travel > actuation):    │
          │      Key is PRESSED          │
          │  else:                       │
          │      Key is RELEASED         │
          └──────────┬───────────────────┘
                     │
                     ↓
     ┌───────────────┴────────────────┐
     │                                │
     ↓ PRESSED                        ↓ RELEASED
┌─────────────────┐           ┌─────────────────┐
│  Trigger Note   │           │  Release Note   │
│  ON event       │           │  OFF event      │
└─────────┬───────┘           └─────────┬───────┘
          │                             │
          ↓                             ↓
┌──────────────────────────────────────────────────────────┐
│  Get Velocity (if MIDI key)                              │
│  velocity = get_he_velocity_from_position()              │
│                                                          │
│  ** Can use per-key velocity curve if enabled **        │
│                                                          │
│  Check per_key_actuations[target_layer]                 │
│        .keys[key_index].flags                           │
│                                                          │
│  if (PER_KEY_FLAG_USE_PER_KEY_VELOCITY_CURVE):          │
│      curve = per_key_actuations[...].velocity_curve     │
│  else:                                                   │
│      curve = keyboard_settings.he_velocity_curve        │
│                                                          │
│  Apply curve to travel value → velocity                 │
└──────────────────────────────────────────────────────────┘
```

### Additional Per-Key Features (Beyond Actuation):

```
┌─────────────────────────────────────────────────────────────┐
│          ADDITIONAL PER-KEY SETTINGS (When Enabled)         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  For key_index = row * 14 + col:                           │
│  target_layer = per_key_per_layer_enabled ? layer : 0      │
│                                                             │
│  per_key_actuations[target_layer].keys[key_index]:         │
│                                                             │
│  ┌─────────────────────────────────────────────┐          │
│  │ .actuation              → Actuation point   │          │
│  │ .deadzone_top           → Top deadzone      │          │
│  │ .deadzone_bottom        → Bottom deadzone   │          │
│  │ .velocity_curve         → Custom curve      │          │
│  │ .rapidfire_press_sens   → Rapidfire trigger │          │
│  │ .rapidfire_release_sens → Rapidfire release │          │
│  │ .rapidfire_velocity_mod → Velocity modifier │          │
│  │ .flags:                                      │          │
│  │    Bit 0: Rapidfire enabled for this key    │          │
│  │    Bit 1: Use per-key velocity curve        │          │
│  └─────────────────────────────────────────────┘          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Key Characteristics of Per-Key Mode:
1. **Individual Actuation Points**: Each of 70 keys can have unique actuation (0-2.5mm)
2. **Deadzones**: Top and bottom deadzones prevent bouncing/noise
3. **Rapidfire**: Per-key rapidfire with custom sensitivity settings
4. **Velocity Curves**: Each key can use a different velocity curve
5. **Per-Layer Option**: Can have different settings per layer OR share across all layers
6. **Memory Usage**: 6720 bytes (560 bytes × 12 layers) vs ~100 bytes for non per-key

---

## COMPARISON TABLE

| Feature                      | Non Per-Key Mode                   | Per-Key Mode                         |
|------------------------------|------------------------------------|------------------------------------- |
| **Actuation Point**          | Same for all keys on layer         | Unique per key                       |
| **Function Called**          | `layer_actuations[layer].midi_actuation` | `per_key_actuations[layer].keys[idx].actuation` |
| **Deadzone Support**         | No                                 | Yes (top and bottom per key)         |
| **Rapidfire**                | No                                 | Yes (per key, with sensitivity)      |
| **Velocity Curve**           | Layer-wide                         | Per-key or layer-wide                |
| **Memory Usage**             | ~100 bytes (12 layers)             | 6720 bytes (12 layers × 70 keys)     |
| **CPU Overhead**             | Minimal (array lookup)             | Slightly higher (index calculation)  |
| **Configurability**          | 2 values per layer                 | 8 values per key per layer           |
| **Per-Layer Settings**       | Always                             | Optional (via per_key_per_layer_enabled) |
| **Use Case**                 | Simple, uniform keyboard behavior  | Advanced, customizable per-key feel  |

---

## CODE PATHS - CRITICAL FUNCTION

### `get_key_actuation_point(uint8_t layer, uint8_t row, uint8_t col)` - orthomidi5x14.c:3113

```c
uint8_t get_key_actuation_point(uint8_t layer, uint8_t row, uint8_t col) {
    // ========== PATH 1: NON PER-KEY MODE ==========
    if (!per_key_mode_enabled) {
        // Return layer-wide setting (use midi_actuation as the default)
        // NOTE: Since per-key mode uses a single value for both MIDI and normal keys,
        // we use midi_actuation as the default when per-key mode is off
        return layer_actuations[layer].midi_actuation;

        // ✓ Same value for ALL keys
        // ✓ Fast lookup
        // ✓ Simple logic
    }

    // ========== PATH 2: PER-KEY MODE ==========
    // Calculate key index (0-69)
    uint8_t key_index = row * 14 + col;  // 14 columns per row
    if (key_index >= 70) return DEFAULT_ACTUATION_VALUE;

    // Determine which layer's settings to use
    if (per_key_per_layer_enabled) {
        // Use settings specific to this layer
        return per_key_actuations[layer].keys[key_index].actuation;
    }

    // Use global settings (layer 0) for all layers
    return per_key_actuations[0].keys[key_index].actuation;

    // ✓ Unique value per key
    // ✓ Can be layer-specific or global
    // ✓ Allows fine-grained control
}
```

---

## FUNCTION CALL HIERARCHY

```
matrix_scan_user()                           (orthomidi5x14.c:14167)
    └→ [Matrix scanning logic]
        └→ analog_matrix_get_travel_normalized(row, col)  [Gets 0-100 travel value]
            └→ get_key_actuation_point(layer, row, col)   (orthomidi5x14.c:3113)
                ├→ NON PER-KEY: return layer_actuations[layer].midi_actuation
                │                 ↓
                │              [Same for all 70 keys]
                │
                └→ PER-KEY: return per_key_actuations[target_layer].keys[key_index].actuation
                              ↓
                          [Unique per key]
                              ↓
                          Compare travel > actuation
                              ↓
                        ┌─────┴─────┐
                        │           │
                  PRESS event   RELEASE event
                        │           │
                        └──→ Send MIDI Note ON/OFF
```

---

## VELOCITY CALCULATION FLOW

### Non Per-Key Mode
```
get_he_velocity_from_position(row, col)  (orthomidi5x14.c:446)
    ├→ Check layer_actuations[layer].flags
    │   └→ Use fixed velocity OR
    │       └→ Apply velocity_mode from layer settings
    │           └→ Use GLOBAL velocity curve
    │               (keyboard_settings.he_velocity_curve)
    └→ Return velocity (1-127)
```

### Per-Key Mode
```
get_he_velocity_from_position(row, col)  (orthomidi5x14.c:446)
    ├→ Check layer_actuations[layer].flags
    │   └→ Use fixed velocity OR
    │       └→ Check per_key_actuations[...].keys[idx].flags
    │           ├→ PER_KEY_FLAG_USE_PER_KEY_VELOCITY_CURVE set?
    │           │   └→ YES: Use per_key_actuations[...].keys[idx].velocity_curve
    │           │   └→ NO:  Use keyboard_settings.he_velocity_curve
    │           └→ Apply curve to travel
    └→ Return velocity (1-127)
```

---

## SUMMARY

### When per_key_mode_enabled == FALSE:
- All keys use `layer_actuations[layer].midi_actuation`
- Simple, fast, memory-efficient
- Suitable for uniform keyboard behavior

### When per_key_mode_enabled == TRUE:
- Each key uses `per_key_actuations[layer].keys[key_index].actuation`
- Supports deadzones, rapidfire, per-key velocity curves
- Can be configured per-layer or globally (via per_key_per_layer_enabled)
- Higher memory usage but extreme customizability

The main divergence point is **line 3115** in `get_key_actuation_point()`:
```c
if (!per_key_mode_enabled) {
    return layer_actuations[layer].midi_actuation;  // ← All keys share this
}
```

vs
```c
// Per-key mode
return per_key_actuations[target_layer].keys[key_index].actuation;  // ← Each key has its own
```

This single boolean flag completely changes how actuation points (and related settings like velocity curves) are retrieved throughout the firmware's matrix scanning and MIDI processing pipeline.

---

## DKS Keys: A Third Pathway

In addition to per-key and non per-key actuation modes, the firmware also supports **DKS (Dynamic Keystroke)** keys, which represent a completely different approach:

### DKS vs Actuation Modes

| Feature | Regular Keys (Per-Key or Non Per-Key) | DKS Keys |
|---------|---------------------------------------|----------|
| **Purpose** | Single action with configurable actuation | Multi-action based on travel depth |
| **Actuation System** | Uses get_key_actuation_point() | Uses zone-based thresholds |
| **Actions per key** | 1 | Up to 8 (4 press + 4 release) |
| **Matrix Processing** | Normal (sets pressed/released state) | Bypassed (DKS manages own keycodes) |
| **Integration Point** | `get_key_actuation_point()` in actuation check | `dks_process_key()` in matrix_scan_custom() |
| **Keycode Range** | All regular/MIDI keycodes | 0xED00-0xED31 (50 slots) |

### DKS Processing in Matrix Scan (quantum/matrix.c)

```c
// After normal actuation processing...
for (uint8_t row = 0; row < MATRIX_ROWS; row++) {
    for (uint8_t col = 0; col < MATRIX_COLS; col++) {
        uint16_t keycode = dynamic_keymap_get_keycode(current_layer, row, col);

        if (is_dks_keycode(keycode)) {  // 0xED00-0xED31
            // DKS key detected!
            analog_key_t *key = &keys[row][col];
            dks_process_key(row, col, key->travel, keycode);

            // Later, DKS keys are marked as NOT pressed in matrix
            // (They handle their own keycode registration internally)
        }
    }
}
```

**See `DKS_complete_flowchart.md` for full DKS implementation details.**

### Key Differences:

1. **Per-Key Actuation**: Fine-tunes WHERE a key actuates (single threshold)
2. **DKS Keys**: Defines WHAT happens at MULTIPLE depths (8 thresholds with different actions)

Both systems coexist in the firmware:
- Regular keys use `get_key_actuation_point()` → per-key or layer-wide
- DKS keys use `dks_process_key()` → multi-zone actions

They don't interfere with each other - if a keycode is in the DKS range (0xED00-0xED31), it uses DKS processing; otherwise, it uses normal actuation processing.
