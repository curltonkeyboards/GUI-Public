# Velocity & Aftertouch Calculation Analysis (Updated Implementation)

## Executive Summary

This document describes the updated velocity and aftertouch calculation methods for the orthomidi5x14 Hall effect keyboard firmware. The velocity modes have been **fixed to properly connect matrix.c calculations to the MIDI output path**.

### Key Changes Made

1. **Velocity modes now store raw values (0-255)** instead of final velocities (1-127)
2. **`get_he_velocity_from_position()` now uses pre-calculated velocity** from matrix.c
3. **Curves are applied to the velocity mode output**, not just current travel
4. **Mode 1, 2, and 3 work as intended** with proper apex detection and speed measurement

---

## Updated Data Flow Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        UPDATED SYSTEM ARCHITECTURE                                │
└──────────────────────────────────────────────────────────────────────────────────┘

                            ┌─────────────────────┐
                            │     Raw ADC         │
                            │  (Hall Effect)      │
                            └──────────┬──────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │    EMA Filter       │
                            └──────────┬──────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │  LUT Linearization  │
                            │     (0-255)         │
                            └──────────┬──────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │   key->distance     │
                            │     (0-255)         │
                            └──────────┬──────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
         ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
         │   VELOCITY      │ │   AFTERTOUCH    │ │   KEY STATE     │
         │   MODES 0-3     │ │   MODES 1-4     │ │   (RT, press)   │
         │   (matrix.c)    │ │   (matrix.c)    │ │                 │
         └────────┬────────┘ └────────┬────────┘ └─────────────────┘
                  │                   │
                  ▼                   ▼
         ┌─────────────────┐ ┌─────────────────┐
         │  raw_velocity   │ │ aftertouch_cc   │
         │    (0-255)      │ │    (0-127)      │
         └────────┬────────┘ └─────────────────┘
                  │
                  ▼
         ┌─────────────────────────────────────┐
         │  analog_matrix_get_velocity_raw()   │
         │        (matrix.c API)               │
         └────────────────┬────────────────────┘
                          │
                          ▼
         ┌─────────────────────────────────────┐
         │   get_he_velocity_from_position()   │
         │        (orthomidi5x14.c)            │
         │                                     │
         │   1. Get raw_velocity (0-255)       │
         │   2. apply_curve(raw, curve_idx)    │
         │   3. Scale to [min_vel, max_vel]    │
         └────────────────┬────────────────────┘
                          │
                          ▼
         ┌─────────────────────────────────────┐
         │      Final MIDI Velocity (1-127)    │
         └─────────────────────────────────────┘
```

---

## Velocity Mode Implementations

### Mode 0: Fixed Velocity

No measurement - returns configured fixed velocity.

```
raw_velocity = 255 (max, curve determines actual output)
```

---

### Mode 1: Peak Travel at Apex

**What it measures:** The peak (maximum) travel distance reached during the keystroke, captured when the key speed drastically slows down (apex detection).

```
┌─────────────────────────────────────────────────────────────────┐
│                MODE 1: PEAK TRAVEL AT APEX                       │
└─────────────────────────────────────────────────────────────────┘

Time ──────────────────────────────────────────────────────────────►

Travel
(0-240)     Peak tracked during descent
                    │
                    ▼
            ●───────●───────●   ← Peak travel = raw_velocity
           ╱         ╲       ╲
          ╱           ╲       ╲
         ╱ Fast        ╲Apex   ╲ Release
        ╱  movement     ╲detect ╲
       ╱                 ╲       ╲
──────●───────────────────●───────●─────────────────────────────────
      │                   │
      │                   └── Speed drops below threshold
      │                       → Capture raw_velocity = (peak_travel * 255) / 240
      │
      └── Speed exceeds threshold (20 units/ms)
          → Start tracking peak

BEHAVIOR:
- Push key 30% and release → raw_velocity ≈ 77 (30% of 255)
- Push key 80% and release → raw_velocity ≈ 204 (80% of 255)
- raw_velocity then goes through velocity curve

IGNORES: Actuation point (just uses deadzone to avoid misstriggers)
```

---

### Mode 2: Speed-Based (Deadzone to Actuation)

**What it measures:** Average speed from when the key starts moving (crosses deadzone) to when it crosses the actuation point.

```
┌─────────────────────────────────────────────────────────────────┐
│           MODE 2: SPEED-BASED (DEADZONE TO ACTUATION)            │
└─────────────────────────────────────────────────────────────────┘

Time ──────────────────────────────────────────────────────────────►

            ◄────── time_delta ──────►
Travel
(0-240)                               Actuation Point
                                             │
            ●───────────────────────────────●│─────────────●
           ╱                                 ╲             ╲
          ╱                                   ╲             ╲
         ╱ Key starts                          ╲             ╲
        ╱  moving                               ╲             ╲
       ╱   │                                     ╲             ╲
──────●────│──────────────────────────────────────●─────────────●───
      │    │                                      │
      │    └── t_start: Key crosses deadzone      │
      │        (last_time recorded)               │
      │                                           │
      └── Velocity captured when actuation crossed:
          avg_speed = (midi_threshold * 1000) / time_delta
          raw_velocity = (avg_speed * velocity_speed_scale) / 100

NOTE: Use deeper actuation point for more reliable speed measurement
      (more travel distance = more consistent time measurement)
```

---

### Mode 3: Speed + Peak Combined (70/30 Blend)

**What it measures:** Both peak speed and peak travel until apex, then blends them 70% speed + 30% travel.

```
┌─────────────────────────────────────────────────────────────────┐
│            MODE 3: SPEED + PEAK COMBINED (70/30)                 │
└─────────────────────────────────────────────────────────────────┘

Time ──────────────────────────────────────────────────────────────►

Travel
(0-240)     Peak speed & travel tracked
                    │
                    ▼
            ●───────●───────●   ← peak_travel captured
           ╱│        ╲       ╲
          ╱ │         ╲       ╲
         ╱  │ peak     ╲Apex   ╲
        ╱   │ speed     ╲detect ╲
       ╱    ▼            ╲       ╲
──────●───────────────────●───────●─────────────────────────────────
                          │
                          └── Speed drops below threshold
                              → Calculate blend:
                                speed_raw = (peak_speed * scale) / 10
                                travel_raw = (peak_travel * 255) / 240
                                raw_velocity = (speed_raw * 70 + travel_raw * 30) / 100

BEHAVIOR: Combines how FAST and how FAR the key was pressed
```

---

## Aftertouch Modes (Unchanged)

| Mode | What it Measures | Formula |
|------|------------------|---------|
| **1: Reverse** | Inverted travel position | `127 - (travel * 127) / 240` |
| **2: Bottom-Out** | Travel position | `(travel * 127) / 240` |
| **3: Post-Actuation** | Travel beyond actuation | `((travel - threshold) * 127) / (240 - threshold)` |
| **4: Vibrato** | Movement speed | `min((travel_delta * 100) / time_delta, 127)` |

---

## Code Changes Summary

### matrix.c

**New fields in `midi_key_state_t`:**
```c
bool velocity_captured;      // True when velocity has been captured
uint8_t peak_speed;          // Peak instantaneous speed
uint8_t travel_at_actuation; // Travel when actuation crossed
uint8_t raw_velocity;        // Raw velocity value (0-255)
```

**New API functions:**
```c
uint8_t analog_matrix_get_velocity_raw(uint8_t row, uint8_t col);
uint8_t analog_matrix_get_velocity_mode(void);
```

### orthomidi5x14.c

**Modified `get_he_velocity_from_position()`:**
```c
uint8_t get_he_velocity_from_position(uint8_t row, uint8_t col) {
    // ...
    uint8_t velocity_mode = analog_matrix_get_velocity_mode();

    uint8_t raw_value;
    if (velocity_mode == 0) {
        raw_value = analog_matrix_get_travel_normalized(row, col);
    } else {
        // Use pre-calculated velocity from matrix.c
        raw_value = analog_matrix_get_velocity_raw(row, col);
        if (raw_value == 0) {
            raw_value = analog_matrix_get_travel_normalized(row, col);
        }
    }

    // Apply curve and scale to velocity range
    uint8_t curved_value = apply_curve(raw_value, curve_index);
    int16_t velocity = min_vel + ((int16_t)curved_value * range) / 255;
    // ...
}
```

---

## Velocity Curve Application

Curves are now applied to the **velocity mode output** (not just current travel):

| Mode | Input to Curve | Curve Effect |
|------|---------------|--------------|
| 0 | Current travel | Shapes response based on position |
| 1 | Peak travel at apex | Shapes response based on how far key was pressed |
| 2 | Average speed | Shapes response based on how fast key was pressed |
| 3 | 70% speed + 30% travel | Shapes response based on combined measurement |

---

## Testing Recommendations

1. **Mode 1 (Peak Travel)**:
   - Slow press to 30% → should get ~30% velocity
   - Fast press to 80% → should get ~80% velocity
   - Verify apex detection triggers correctly

2. **Mode 2 (Speed)**:
   - Fast press → high velocity
   - Slow press → low velocity
   - Test with different actuation depths

3. **Mode 3 (Combined)**:
   - Fast press to bottom → highest velocity
   - Slow press to bottom → medium velocity (30% travel component)
   - Fast press halfway → medium velocity (less travel component)

4. **Curve application**:
   - Switch between curves and verify all modes respond
   - Test min/max velocity range settings

---

## Files Modified

| File | Changes |
|------|---------|
| `quantum/matrix.c` | Added raw_velocity field, rewrote velocity modes, added API functions |
| `quantum/matrix.h` | Added function declarations |
| `keyboards/orthomidi5x14/orthomidi5x14.c` | Modified velocity functions to use raw_velocity |
