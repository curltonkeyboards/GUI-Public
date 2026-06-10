# Scan Pipeline Optimization Log

## Overview

Systematic optimization of the orthomidi5x14 Hall effect MIDI keyboard's
matrix scanning and MIDI processing pipeline. Target: minimize latency
from physical keypress to MIDI note output.

Hardware: STM32F412 @ 48MHz SYSCLK, 5x14 matrix (70 keys), ADG706 mux,
ST7789 LCD, 70x WS2812 LEDs, serial MIDI (31250 baud) + USB MIDI.

---

## Bugs Found

### 1. Matrix bitmap missing zone actuation override
**File:** `matrix.c` lines 2347-2348
**Impact:** Preset actuation changes ignored for velocity modes 0 and 2.
The zone actuation override was applied in `process_rapid_trigger` and
`process_midi_key_analog` but NOT in the matrix bitmap build. Keys only
registered at `DEFAULT_ACTUATION_VALUE = 255` (full bottom-out).

### 2. No hysteresis on MIDI key threshold
**File:** `matrix.c` line 1002
**Impact:** Double key registration. `STATIC_HYSTERESIS = 5` defined in
`matrix.h` but never applied. Raw ADC noise of 10-20 units caused
`is_pressed` toggling around the actuation threshold.

### 3. EMA filter adding 16ms latency
**File:** `matrix.c` line 2114
**Impact:** Alpha=1/16 EMA filter was adding ~16ms of position lag.
Removed entirely — Hall sensors are clean enough without filtering.

### 4. Velocity timer stale from idle skip
**File:** `matrix.c` line 1143-1146
**Impact:** 100ms+ velocity readings on fast presses. The idle MIDI key
early-return didn't reset `last_travel`, so the speed timer gate
`last_travel == 0 && travel > 0` never fired. `move_start_time` stayed
stale from a previous press.

### 5. EEPROM reads on every MIDI note-on
**File:** `matrix.c` line 1669, `dynamic_keymap.c` lines 152-153
**Impact:** 2 I2C EEPROM reads (~200us each) per key on every press
transition. 10 simultaneous presses = 20 reads = ~4000us spike.
Fixed by caching MIDI keycodes in `dks_keycode_cache_all[]`.

### 6. EEPROM reads on every velocity curve application
**File:** `orthomidi5x14.c` line 7511
**Impact:** User velocity curves (indices 7-56) read 8 bytes from I2C
EEPROM (~225us) on every note-on and retrigger. Fixed by caching active
curve points in RAM (24 bytes for 3 zones).

### 7. HALL_HARDCODE_BOTTOM / HALL_LOCK_BOTTOM_OUT not implemented
**File:** `hardwareupdate.md` vs actual `config.h` and `matrix.c`
**Impact:** Documented defines never added to code. Bottom-out value
still uses `rest - 674` from warm-up and drifts with rest calibration.

---

## Optimizations Applied

### ADC / Analog Scan

| Change | Before | After | Savings |
|--------|--------|-------|---------|
| Mux settle time | 10us x14 = 140us | 2us x14 = 28us | ~112us/scan |
| ADC prescaler | DIV4 (12MHz) | DIV2 (24MHz) | ~50% faster ADC |
| ADC sample time | 56 cycles | 3 cycles (minimum) | ~80% faster per channel |
| ADC total | ~560us | ~200us | **~360us/scan** |

ADC_SAMPLE_3 at 24MHz = 125ns sample time. ADG706 mux output impedance
~100ohm, STM32 ADC input ~5pF. RC = 0.5ns. 125ns = 250x margin.

### Per-Key Processing

| Change | Before | After | Savings |
|--------|--------|-------|---------|
| EMA filter | 1/16 alpha (16ms lag) | Removed | 0 latency |
| Idle RT skip | No skip | Early return if distance=0 + inactive | ~50-60 keys skipped |
| Idle MIDI skip | No skip | Early return with state cleanup | ~50-60 keys skipped |
| Calibration throttle | Every scan (70 keys) | Every 100 scans | 99% reduction |
| Merged post-scan loops | 3 x O(70) | 1 x O(70) | 140 fewer iterations |

### Velocity Pipeline

| Change | Before | After | Savings |
|--------|--------|-------|---------|
| Velocity curve EEPROM reads | ~225us/note-on | 0 (RAM cache) | **225us/note** |
| MIDI keycode EEPROM reads | ~400us/note-on | 0 (cache) | **400us/note** |
| idle skip state cleanup | last_travel stale | Resets last_travel, was_pressed, peak_travel | Fixes 100ms+ readings |

### Display / RGB

| Change | Before | After | Savings |
|--------|--------|-------|---------|
| LCD blit | All 16 pages in one shot | 2 pages per scan (chunked) | Spreads load over 8 cycles |
| RGB flush limit | 16ms (60fps) | 50ms (20fps) | Fewer 2.4ms blocking flushes |
| USB MIDI polling | 5ms | 1ms | 2ms avg latency reduction |

---

## Current Performance (Post-Optimization)

### Scan Cycle Breakdown (inside matrix_scan_custom)

| Component | Typical (us) | Notes |
|-----------|-------------|-------|
| ADC (14 columns) | 200-300 | 3-cycle sample, DIV2 prescaler |
| Distance calc (70 keys) | 60-110 | LUT lookup + dead zone |
| RT FSM (70 keys) | 50-150 | Idle keys skip in ~0.1us |
| MIDI processing | 20-120 | Idle keys skip entirely |
| Matrix bitmap build | 50-70 | Single merged pass |
| **Total S** | **600-800** | Down from ~900-1200 |

### Main Loop Component Timing

| Component | Typical (us) | Peak (us) | Notes |
|-----------|-------------|-----------|-------|
| M (matrix_task) | 780-840 | **10000** | Includes scan + process_record + USB send |
| R (rgb_matrix_task) | 20-1030 | 6000 | Animation calc (PWM+DMA handles transmission in background) |
| Q (qp + housekeeping) | 40-60 | 180 | Chunked LCD blit |
| I (midi_task) | 10-20 | 20 | Serial MIDI polling |
| **G (total gap)** | **1200** | **7000-14000** | Sum of above + USB/quantum |

### End-to-End Latency (Keypress to MIDI Output)

| Path | Average | Worst Case |
|------|---------|------------|
| Firmware (scan + process) | ~0.8ms | ~1.2ms |
| USB MIDI transport | ~0.5ms | ~1ms |
| Serial MIDI wire time | ~1ms | ~1ms |
| **Total (USB)** | **~1.3ms** | **~2.2ms** |
| **Total (Serial)** | **~1.8ms** | **~2.2ms** |

Note: Worst case can spike to 10-14ms when USB send_report blocks
waiting for endpoint (10ms timeout) or RGB animation calc is heavy.

---

## Root Cause: M = 10000µs Spikes

**Found in:** `tmk_core/protocol/chibios/usb_main.c` line 874

```c
void send_report(uint8_t endpoint, void *report, size_t size) {
    osalSysLock();
    if (usbGetTransmitStatusI(&USB_DRIVER, endpoint)) {
        // BLOCKS UP TO 10ms waiting for USB endpoint to drain
        osalThreadSuspendTimeoutS(..., TIME_MS2I(10));
    }
    usbStartTransmitI(&USB_DRIVER, endpoint, report, size);
    osalSysUnlock();
}
```

USB Full Speed endpoints can only transmit one report per 1ms USB
frame. When multiple keys change state in one scan cycle, each triggers
`send_keyboard()` → `send_report()`. The second (and subsequent) calls
hit the endpoint busy and block up to 10ms (or until the next 1ms USB
frame drains it).

This is QMK/ChibiOS core behavior — not modifiable without changing
the USB stack. The spike magnitude depends on how many keys change
state simultaneously. Typically 1-3ms for normal typing, up to 10ms
for key-spam scenarios.

**Tested:** Bypassing `set_keylog()` (50+ snprintf calls) did NOT
reduce M spikes. The USB blocking is the dominant factor.

## Root Cause: R = 1000-6000µs (RGB Animation)

After switching WS2812 to PWM+DMA, R no longer includes LED
transmission time (2.1ms). The remaining R cost is pure animation
calculation:

1. **COMBINED_LOOP.c** custom effect: O(70 LEDs × 32 active notes)
   per frame with HSV math = up to 2240 iterations
2. **rgb_matrix_indicators_kb()**: 50-100+ LED function calls per
   frame with nested loops for macros, toggles, quick build, etc.

The PWM+DMA change eliminated the 2.1ms interrupt-locked bit-bang
block, but the animation math is still CPU-bound.

---

## Remaining Bottlenecks

### 1. WS2812 Bit-Bang (R = 2400us barrier)

The WS2812 driver uses GPIO bit-bang with interrupts disabled
(`chSysLock`). 70 LEDs x 24 bits x 1.25us = 2100us of CPU-blocking
transmission. During this time, no matrix scanning or MIDI processing
can occur.

The 2400us R value IS the transmission time (2100us data + 300us reset
+ overhead). When R drops to 20us, the flush timer hasn't elapsed.
Animations like ripple push R above 2400 because animation calculation
adds to the flush time.

**Fix:** Switch to PWM+DMA WS2812 driver. Uses TIM2 + DMA1 Stream 2
(no conflicts with ADC DMA2 Stream 0 or LCD SPI1 DMA2 Stream 3). LED
data transmitted by DMA while CPU continues scanning. Would eliminate
the 2.1ms blocking period entirely.

Config change:
```make
# rules.mk
WS2812_DRIVER = pwm
```
```c
// config.h
#define WS2812_PWM_DRIVER PWMD2
#define WS2812_PWM_CHANNEL 1
// mcuconf.h
#define STM32_PWM_USE_TIM2 TRUE
```

### 2. process_record Spikes (M = 10000us)

`matrix_task()` includes both our scan (~700us) AND QMK's
`process_record` for all changed keys. The full chain per key event:

1. `matrix_task()` detects changed keys, calls `action_exec()` per key
2. `action_exec()` → `process_record_quantum()` runs **~30 handler
   functions sequentially** (tap-dance, combos, leader, steno,
   process_midi, process_rgb, etc.)
3. `process_midi()` triggers `trigger_rgb_for_midi_note()` in
   `qmk_midi.c` — does **504 comparisons per note** (6 LED positions ×
   6 rows × 14 cols nested loop) plus RGB reactive effect processing
4. `midi_send_noteon()` → `send_midi_packet()` → `chnWrite()` which
   **blocks synchronously** waiting for USB endpoint to drain

With 10 simultaneous note-ons: 5040 comparisons + 10 blocking USB
writes + 10 × 30 handler calls = 10000us spike.

**MIDI is NOT on a separate thread** — everything runs synchronously
on the main thread. USB MIDI sends block until the packet is queued.

### 3. Nullbind O(20) per pressed key

`nullbind_should_null_key()` iterates 20 groups per pressed key in the
matrix build. A 70-byte key-to-group lookup table would make this O(1).

---

## Diagnostic Display (Temporary)

Currently showing peak-hold values updated every 500ms:

```
Row 1: M<matrix_task>  R<rgb_task>
Row 2: S<scan>         Q<qp+housekeeping>
Row 3: I<midi_task>    G<gap_between_scans>
Row 4: PEAKS OVER 500ms
```

Replaces: layer/BPM, transpose, channel, velocity curve display.
All diagnostic code is in the scan timing sections of matrix.c and
orthomidi5x14.c oled_render_keylog / oled_task_user.

---

## Files Modified

| File | Changes |
|------|---------|
| `quantum/matrix.c` | ADC sample time, mux settle, EMA removal, calibration throttle, idle skips, merged loops, MIDI keycode cache, timing diagnostics |
| `quantum/matrix.h` | No changes (constants already correct) |
| `quantum/keyboard.c` | Per-component timing around matrix_task, rgb_matrix_task, oled_task, midi_task |
| `quantum/main.c` | Timing around qp_internal_task + housekeeping_task |
| `quantum/vial.c` | Velocity curve cache invalidation on user curve write/reset |
| `keyboards/orthomidi5x14/config.h` | RGB_MATRIX_LED_FLUSH_LIMIT = 50 |
| `keyboards/orthomidi5x14/mcuconf.h` | ADC prescaler DIV4 -> DIV2 |
| `keyboards/orthomidi5x14/orthomidi5x14.c` | Velocity curve RAM cache, diagnostic display, chunked LCD blit, curve cache invalidation in preset apply/load |
| `keyboards/orthomidi5x14/orthomidi5x14.h` | Velocity curve cache function declarations |
| `keyboards/orthomidi5x14/arpeggiator_hid.c` | Curve cache invalidation on HID parameter changes |
| `tmk_core/protocol/usb_descriptor.c` | USB MIDI polling 5ms -> 1ms |
