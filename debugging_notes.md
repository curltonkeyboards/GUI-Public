# HE Keyboard USB Disconnection - Debugging Notes

## Issue Summary

After switching from normal key switches to Hall Effect (HE) switches, the keyboard would:
- Connect successfully (Windows plays connection sound)
- Show no functionality (no keys working, no visual feedback)
- Disconnect after a couple of minutes (Windows plays disconnection sound)
- Device Manager would show it as connected, then it would disappear

## Diagnosis Process

### Step 1: Disable All ADC Scanning
**Result**: USB stayed connected

This confirmed the issue was in the ADC/HE scanning code, not in USB enumeration or other subsystems.

### Step 2: Re-enable ADC Initialization Only
- Re-enabled `adcStart(&ADCD1, NULL)`
- Re-enabled `SYSCFG->PMC |= SYSCFG_PMC_ADC1DC2`
- Kept scanning disabled

**Result**: USB stayed connected

ADC peripheral initialization is fine.

### Step 3: Re-enable ADC Warm-up Loop
- Re-enabled the 5-iteration warm-up scan at init

**Result**: USB stayed connected

The warm-up ADC conversions work fine.

### Step 4: Re-enable Continuous ADC Scanning
- Re-enabled `analog_matrix_task_internal()` with full processing

**Result**: USB DISCONNECTS

The continuous scanning loop is where the problem lies.

### Step 5: Minimal ADC Scanning (ADC + EMA only)
- Enabled ADC conversion
- Enabled EMA filtering
- Disabled: calibration, distance calculation, RT processing, MIDI, DKS

**Result**: USB stayed connected

The ADC reading itself is not the problem.

### Step 6: Add Calibration + Distance Calculation
- Re-enabled `update_calibration()`
- Re-enabled `adc_to_distance()`

**Result**: USB stayed connected

Calibration and distance calculation are fine.

### Step 7: Add Rapid Trigger Processing
- Re-enabled `process_rapid_trigger()` with full RT state machine

**Result**: USB DISCONNECTS

The problem is in `process_rapid_trigger()`.

### Step 7b: Disable Null Bind Calls in RT
- Commented out all `nullbind_*` function calls

**Result**: USB still disconnects

Null bind is not the problem.

### Step 7c: Simplified RT (Fixed Threshold Only)
```c
static void process_rapid_trigger(uint32_t key_idx, uint8_t current_layer) {
    key_state_t *key = &key_matrix[key_idx];
    uint8_t actuation_point = 50;  // Fixed value
    key->is_pressed = (key->distance >= actuation_point);
}
```

**Result**: USB stayed connected

The problem is not the RT state machine logic itself.

### Step 7d: Add Per-Key Config Lookup
- Re-enabled `get_key_actuation_config()` call

**Result**: USB DISCONNECTS

The problem is in `get_key_actuation_config()`.

### Step 7e: Test `actuation_to_distance()` Without Array Access
```c
uint8_t actuation_point = actuation_to_distance(DEFAULT_ACTUATION_VALUE);
```

**Result**: USB stayed connected

The math function is fine. The problem is accessing the array.

## Root Cause

**The `per_key_actuations[]` array access causes USB disconnection.**

The function `get_key_actuation_config()` reads from:
```c
per_key_actuation_t *settings = &per_key_actuations[layer].keys[key_idx];
```

This is called for all 70 keys on every scan cycle (thousands of times per second). The array is:
- 12 layers × 70 keys × sizeof(per_key_actuation_t)
- Loaded from EEPROM at startup via `load_per_key_actuations()`

### Likely Causes

1. **Uninitialized/Corrupted EEPROM Data**: The per-key actuation data in EEPROM may contain garbage values (0xFF for uninitialized EEPROM)

2. **Memory Access Issues**: Reading from this large array so frequently may cause:
   - Cache thrashing
   - Memory bus contention
   - Stack/heap issues

3. **Array Not Properly Initialized**: The initialization check only looks at the first key:
   ```c
   if (per_key_actuations[0].keys[0].actuation == 0xFF) {
       initialize_per_key_actuations();
   }
   ```
   Other keys may still contain garbage.

## Solution

Modify `get_key_actuation_config()` to use layer-level actuation settings instead of per-key settings:

```c
static inline void get_key_actuation_config(uint32_t key_idx, uint8_t layer,
                                            uint8_t *actuation_point,
                                            uint8_t *rt_down,
                                            uint8_t *rt_up,
                                            uint8_t *flags) {
    if (layer >= 12) layer = 0;

    // Use layer-level normal actuation setting (from layer_actuations[])
    *actuation_point = actuation_to_distance(layer_actuations[layer].normal_actuation);

    // Disable RT for now
    *rt_down = 0;
    *rt_up = 0;
    *flags = 0;
}
```

This uses the already-working `layer_actuations[]` array instead of the problematic `per_key_actuations[]` array.

## Recommendations for Future Fix

To properly fix the per-key actuation feature:

1. **Initialize All Keys**: Ensure all 70 keys × 12 layers are properly initialized, not just the first key

2. **Validate EEPROM Data**: Add bounds checking when loading from EEPROM:
   ```c
   if (settings->actuation > 100) settings->actuation = DEFAULT_ACTUATION_VALUE;
   ```

3. **Consider Caching**: Instead of reading from the array on every scan, cache the current layer's settings

4. **Memory Optimization**: Consider reducing the array size or using a different data structure

5. **Lazy Loading**: Only load per-key settings when actually needed (e.g., when user changes settings)

## Files Modified During Debugging

- `vial-qmk - ryzen/quantum/matrix.c`

## Testing Notes

- The keyboard had only 3 switches installed out of 70 during testing
- Empty sockets should not cause issues (HE sensors should read consistent values even without switches)
- The issue occurred regardless of how many switches were installed

## Date

January 2026
