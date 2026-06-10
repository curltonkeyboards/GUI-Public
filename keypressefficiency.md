# Key Press Efficiency — Branch Optimization Log

> **⚠️ RGB CHANGES REVERTED (2026-05-28)**
> All RGB/LED optimizations on this branch were reverted because they
> caused visual artifacts in custom spatial animations (ripple, side dots,
> wider, etc.) and didn't significantly improve perceived performance.
> See section **"RGB Changes (REVERTED)"** at the bottom for the full
> list of what was tried and how to redo it.

## Summary

This document records all performance optimizations made on the
`claude/upbeat-ride-qjQS6` branch for the orthomidi5x14 Hall effect
MIDI keyboard (STM32F412, 5x14 matrix, 70 keys).

**Overall result:** End-to-end keypress latency reduced from ~15-30ms
worst case to ~2-3ms typical. Scan cycle from ~900µs to ~600µs.
Per-key-event processing from ~6300µs to ~200µs.

---

## 1. I2C / EEPROM (Biggest Single Win)

### Problem Found
QMK calls `dynamic_keymap_get_keycode()` — which does 2 I2C EEPROM
reads — approximately 14 times per key event. This happens across:
- `action_tapping.c`: tapping term checks via `WITHIN_TAPPING_TERM`
- `quantum.c`: `get_record_keycode()` for layer resolution
- `action.c`: `store_or_get_action()` for action resolution

I2C was running at **100kHz** (QMK default). Each 2-byte read took
~400µs. Result: **14 × 400µs = 5600µs per key event** — a consistent
6300µs with overhead.

### Fixes Applied

**I2C speed: 100kHz → 400kHz** (`config.h`)
```c
#define I2C1_CLOCK_SPEED 400000
#define I2C1_DUTY_CYCLE FAST_DUTY_CYCLE_2
```
CAT24C512 supports up to 1MHz. 400kHz is conservative.

**Keycode RAM cache** (`dynamic_keymap.c`, `matrix.c`)
- `dks_keycode_cache_all[12][70]` (already allocated, 1680 bytes) now
  stores ALL keycodes, not just DKS/MIDI keys
- `dynamic_keymap_get_keycode()` checks the RAM cache first; only
  falls back to EEPROM if the layer hasn't been cached yet
- Cache populated once per layer change via `populate_key_type_cache_layer()`
- Invalidated on `dynamic_keymap_set_keycode()` (GUI keymap edits)

**Result:** Per-key-event time dropped from ~6300µs to ~200µs.

### Files Changed
- `keyboards/orthomidi5x14/config.h` — I2C speed defines
- `quantum/dynamic_keymap.c` — Cache check in get, invalidation in set
- `quantum/matrix.c` — Store all keycodes in cache, accessor function

### Lessons Learned
- QMK's keycode resolution is called FAR more often than expected
  (14+ times per event, not once)
- The tapping system (`action_tapping.c`) is the heaviest caller
- I2C at 100kHz is the QMK default — always override for fast EEPROM
- A simple RAM cache eliminates all hot-path EEPROM reads

---

## 2. ADC / Analog Scan

### Problem Found
The ADC scan of 14 columns took ~560µs, dominated by:
- ADC clock at 12MHz (prescaler DIV4) — too slow
- ADC sample time of 56 cycles — massively overkill for Hall sensors
- Mux settle time of 10µs — 100x more than needed

### Fixes Applied

**ADC prescaler: DIV4 → DIV2** (`mcuconf.h`)
```c
#define STM32_ADC_ADCPRE ADC_CCR_ADCPRE_DIV2
```
ADC clock: 12MHz → 24MHz. Max spec for STM32F412 is 36MHz.

**ADC sample time: 56 → 3 cycles** (`matrix.c`)
```c
ADC_SAMPLE_3  // minimum hardware supports
```
Hall sensors through ADG706 have ~100Ω impedance, STM32 ADC input
~5pF. RC = 0.5ns. 3 cycles at 24MHz = 125ns = 250× margin.

**Mux settle: 10µs → 2µs** (`matrix.c`)
```c
wait_us(2);  // ADG706 spec: <100ns. 2µs = 20× margin
```

**Result:** ADC total dropped from ~560µs to ~200µs.

### Other Analog Changes

**EMA filter removed** — Alpha=1/16 added 16ms of position lag.
Hall sensors are clean enough without filtering. The dead zone clamp
(`distance <= 3 → 0`) handles residual noise.

**Calibration throttled to every 100 scans** (`matrix.c`)
```c
#define CALIBRATION_THROTTLE_SCANS 100
```
New sensors have minimal drift. Running calibration every scan was
99% wasted work. Now runs every ~100ms, still well within the
5-second stability gate.

**Idle key early returns** in `process_rapid_trigger()` and
`process_midi_key_analog()` — keys at rest (distance=0, not pressed)
skip the full processing pipeline.

**Pressed key calibration skip** — `update_calibration()` returns
immediately for pressed keys (can't recalibrate during a press anyway).

### Files Changed
- `keyboards/orthomidi5x14/mcuconf.h` — ADC prescaler
- `quantum/matrix.c` — Sample time, settle time, EMA removal,
  calibration throttle, idle skips, pressed skip

### Lessons Learned
- ADC_SAMPLE_56 was legacy from noisy old sensors — always match
  sample time to actual source impedance
- The mux settle time was 100× what the datasheet requires
- Calibration for stable sensors is almost pure overhead
- Idle key skips save ~50-60 keys worth of processing per scan

---

## 3. MIDI Velocity Pipeline

### Problems Found
1. **User velocity curves read 8 bytes from I2C EEPROM** on every
   note-on and retrigger (~225µs per read)
2. **MIDI keycodes read from EEPROM** on every press transition
   (2 reads × ~200µs = ~400µs per note)
3. **Velocity timer bug** from idle skip — `last_travel` not reset,
   causing `move_start_time` to be stale (100ms+ velocity readings)

### Fixes Applied

**Velocity curve RAM cache** (`orthomidi5x14.c`)
```c
static uint8_t cached_curve_points[3][4][2];  // 24 bytes, 3 zones
static uint8_t cached_curve_index[3];
```
Lazy-loaded on first use, invalidated on curve change (HID command,
preset apply, settings load). Velocity functions use
`apply_curve_points()` with cached data instead of `apply_curve()`
which hit EEPROM.

**MIDI keycode cache** — `dks_keycode_cache_all` now stores MIDI
keycodes (was zeroed for MIDI keys). `process_midi_key_analog` reads
from cache instead of calling `dynamic_keymap_get_keycode`.

**Velocity timer fix** — idle skip now resets `last_travel = 0`,
`was_pressed = false`, `peak_travel = 0` to prevent stale timer state.

### Files Changed
- `keyboards/orthomidi5x14/orthomidi5x14.c` — Curve cache, functions
- `keyboards/orthomidi5x14/orthomidi5x14.h` — Cache declarations
- `keyboards/orthomidi5x14/arpeggiator_hid.c` — Cache invalidation
- `quantum/vial.c` — Cache invalidation on user curve write/reset
- `quantum/matrix.c` — MIDI keycode cache, velocity timer fix

### Lessons Learned
- EEPROM reads in the note-on path add up fast with chords
- The idle skip optimization must clean up ALL state, not just return
- Lazy cache population avoids upfront cost while eliminating hot-path reads

---

## 4. RGB / WS2812 LEDs

### Problems Found
1. **WS2812 bit-bang** blocked CPU with interrupts disabled for 2.1ms
   during every LED flush (70 LEDs × 24 bits × 1.25µs)
2. **RGB animation calculation** (COMBINED_LOOP.c) does O(70 × 32
   active_notes) per frame — up to 2240 iterations of HSV math
3. **`rgb_matrix_indicators_kb()`** ran on EVERY render pass (not just
   the final one) — 50-100 LED calls × 5 passes = 500 redundant calls
4. **LED flush at 60fps** (16ms default) — unnecessary for a keyboard

### Fixes Applied

**WS2812: bit-bang → PWM+DMA** (`rules.mk`, `config.h`, `mcuconf.h`, `halconf.h`)
```make
WS2812_DRIVER = pwm
```
```c
#define WS2812_PWM_DRIVER PWMD4          // TIM4
#define WS2812_PWM_CHANNEL 3             // CH3 on PB8
#define WS2812_PWM_PAL_MODE 2            // AF2
#define WS2812_DMA_STREAM STM32_DMA1_STREAM6
#define WS2812_DMA_CHANNEL 2             // TIM4_UP
#define HAL_USE_PWM TRUE                 // halconf.h
#define STM32_PWM_USE_TIM4 TRUE          // mcuconf.h
```

DMA conflict resolved: I2C1_TX defaulted to DMA1 Stream 6 (same as
WS2812 TIM4_UP). Moved I2C1_TX to Stream 7:
```c
#define STM32_I2C_I2C1_TX_DMA_STREAM STM32_DMA_STREAM_ID(1, 7)
```

**DMA resource map (no conflicts):**
| Stream | Peripheral | Channel |
|--------|-----------|---------|
| DMA1 Stream 0 | I2C1_RX | Ch 1 |
| DMA1 Stream 6 | WS2812 TIM4_UP | Ch 2 |
| DMA1 Stream 7 | I2C1_TX | Ch 1 |
| DMA2 Stream 0 | ADC1 | Ch 0 |
| DMA2 Stream 3 | SPI1_TX (LCD) | Ch 3 |

**LED flush rate: 16ms → 66ms (15fps)**
```c
#define RGB_MATRIX_LED_FLUSH_LIMIT 66
```
15fps is indistinguishable from 60fps for keyboard lighting in
peripheral vision. WS2812 holds colors between updates (no flicker).

**Process limit: 14 → 9 LEDs per pass**
```c
#define RGB_MATRIX_LED_PROCESS_LIMIT 9
```
8 render passes per frame instead of 5. Each pass handles ~9 LEDs
of animation — flatter spikes, same total work.

**Indicators on last render pass only** (`rgb_matrix.c`)
```c
// Before: indicators ran on EVERY render pass
if (effect) { rgb_matrix_indicators(); }

// After: only on the final pass before flush
if (effect && rgb_task_state == FLUSHING) { rgb_matrix_indicators(); }
```
Eliminates 7× redundant indicator calculations per frame.

### Files Changed
- `keyboards/orthomidi5x14/rules.mk` — WS2812_DRIVER = pwm
- `keyboards/orthomidi5x14/config.h` — PWM config, flush/process limits
- `keyboards/orthomidi5x14/mcuconf.h` — TIM4 PWM, I2C1_TX DMA remap
- `keyboards/orthomidi5x14/halconf.h` — HAL_USE_PWM
- `quantum/rgb_matrix/rgb_matrix.c` — Indicators on last pass only

### Lessons Learned
- WS2812 bit-bang disables ALL interrupts — devastating for MIDI timing
- PWM+DMA is straightforward but watch for DMA stream conflicts
- RGB indicators running every render pass is a QMK design oversight
- 15fps is more than enough for keyboard lighting
- Smaller process limits flatten spikes when indicators are once-only

---

## 5. LCD / Display

### Problem Found
`lcd_blit_oled()` processed all 16 OLED pages in one burst, blocking
the scan loop for several ms. Each changed pixel = one `qp_rect()`
SPI call. Text changes could generate 2000-3000 rect calls.

### Fix Applied

**Chunked LCD blit** — processes 2 OLED pages per scan cycle instead
of all 16. Spreads the SPI cost over 8 scan cycles.

```c
#define LCD_BLIT_PAGES_PER_SCAN 2
```

The OLED buffer render (`oled_task_user`) and luna piano
(`luna_qp_render_delta`) still run on the 50ms trigger cycle,
but the heavy per-pixel blit is chunked.

### Files Changed
- `keyboards/orthomidi5x14/orthomidi5x14.c` — Chunked blit state
  machine, `lcd_blit_oled_chunk()` replacing `lcd_blit_oled()`

---

## 6. USB

### Change
**MIDI polling interval: 5ms → 1ms** (`usb_descriptor.c`)
```c
.PollingIntervalMS = 0x01  // was 0x05
```
Both MIDI IN and OUT endpoints. HID endpoints already used 1ms.
The 5ms MIDI polling was adding unnecessary transport latency on
top of the firmware processing time.

### Note on USB HID Blocking
`send_report()` in `usb_main.c` blocks up to 10ms per call via
`osalThreadSuspendTimeoutS` when the USB endpoint is busy. Each key
state change that triggers `send_keyboard()` can block ~1ms waiting
for the next USB frame. This is QMK/ChibiOS core behavior and not
modifiable without changing the USB stack.

For MIDI keys, `process_midi` returns false before `send_keyboard`
is reached, so MIDI notes do NOT suffer from HID endpoint blocking.

### Files Changed
- `tmk_core/protocol/usb_descriptor.c` — MIDI endpoint polling

---

## 7. Scan Loop Architecture

### Merged Post-Scan Loops
Previously three separate O(70) loops ran after the analog scan:
1. MIDI processing loop
2. DKS processing loop
3. Matrix bitmap build loop

Merged into a single O(70) pass. Eliminates 140 redundant
`key_type_cache` lookups per scan.

### Files Changed
- `quantum/matrix.c` — Single merged loop

---

## 8. Diagnostic System (Temporary)

A per-component timing system was built to isolate bottlenecks.
Currently active on the LCD display (replaces layer/transpose/channel/
curve display). Shows peak-hold values updated every 500ms.

**Timing probes in:**
- `quantum/keyboard.c` — `matrix_task`, `rgb_matrix_task`, `oled_task`,
  `midi_task`, `action_exec`, `switch_events`
- `quantum/main.c` — `qp_internal_task` + `housekeeping_task`
- `quantum/matrix.c` — Analog scan sections, between-scan gap
- `quantum/quantum.c` — Pre/post `process_record_kb` split
- `quantum/process_keycode/process_midi.c` — MIDI send phases

**To remove diagnostics:** Revert the display code in
`orthomidi5x14.c` (`oled_task_user` and `oled_render_keylog`) back
to the original layer/BPM, transpose, channel, and velocity curve
rendering. Remove timing variables and probes from keyboard.c,
main.c, matrix.c, quantum.c, and process_midi.c.

---

## Performance Summary

### Scan Cycle (matrix_scan_custom)

| Component | Before | After |
|-----------|--------|-------|
| ADC (14 columns) | 560µs | 200µs |
| Distance calc | 60-110µs | 60-110µs |
| RT FSM | 50-150µs | 50-150µs (idle skip) |
| MIDI processing | 120µs | 20-60µs (idle skip) |
| Matrix build | 50-70µs | 50-70µs |
| Calibration | 70µs/scan | 0µs (99/100 scans) |
| **Total** | **~900-1200µs** | **~400-600µs** |

### Per-Key-Event (action_exec)

| Component | Before | After |
|-----------|--------|-------|
| Keycode resolution (EEPROM) | ~5600µs | ~0µs (RAM cache) |
| process_record chain | ~200µs | ~200µs |
| MIDI note send | ~170µs | ~170µs |
| **Total per event** | **~6300µs** | **~200-400µs** |

### RGB

| Component | Before | After |
|-----------|--------|-------|
| WS2812 flush | 2100µs (CPU blocked) | ~0µs (DMA) |
| Animation calc (peak) | ~5000µs | ~600µs per pass |
| Indicators | 5× per frame | 1× per frame |
| Frame rate | 60fps | 15fps |
| **Total per frame** | **~10000µs** | **~2000µs** |

### End-to-End Latency

| Path | Before | After |
|------|--------|-------|
| Scan cycle | ~1ms | ~0.5ms |
| Per-key processing | ~6.3ms | ~0.3ms |
| USB MIDI transport | ~2.5ms avg | ~0.5ms avg |
| RGB blocking | 2.1ms (interrupt lockout) | 0ms (DMA) |
| **Worst case total** | **~15-30ms** | **~2-3ms** |

---

## Files Modified (Complete List)

| File | What Changed |
|------|-------------|
| `quantum/matrix.c` | ADC sample time, mux settle, EMA removal, calibration throttle, idle skips, merged loops, keycode cache, MIDI keycode cache, velocity timer fix, timing diagnostics |
| `quantum/matrix.h` | No changes |
| `quantum/keyboard.c` | Per-component timing probes |
| `quantum/main.c` | QP+housekeeping timing probe |
| `quantum/quantum.c` | Pre/post process_record_kb timing |
| `quantum/dynamic_keymap.c` | RAM cache check, invalidation on set |
| `quantum/vial.c` | Velocity curve cache invalidation |
| `quantum/rgb_matrix/rgb_matrix.c` | Indicators on last pass only |
| `quantum/process_keycode/process_midi.c` | MIDI send timing probes |
| `keyboards/orthomidi5x14/config.h` | I2C 400kHz, WS2812 PWM config, RGB limits |
| `keyboards/orthomidi5x14/mcuconf.h` | ADC DIV2, TIM4 PWM, I2C1_TX DMA remap |
| `keyboards/orthomidi5x14/halconf.h` | HAL_USE_PWM |
| `keyboards/orthomidi5x14/rules.mk` | WS2812_DRIVER = pwm |
| `keyboards/orthomidi5x14/orthomidi5x14.c` | Velocity curve cache, chunked LCD blit, diagnostic display |
| `keyboards/orthomidi5x14/orthomidi5x14.h` | Cache function declarations |
| `keyboards/orthomidi5x14/arpeggiator_hid.c` | Curve cache invalidation |
| `tmk_core/protocol/usb_descriptor.c` | USB MIDI polling 5ms → 1ms |

---

## Known Remaining Issues

1. **USB HID `send_report` blocking** — Normal (non-MIDI) key events
   block ~1ms per event on the USB endpoint. QMK core, not fixable
   without USB stack changes. MIDI keys are not affected.

2. **COMBINED_LOOP.c animation complexity** — O(70 × active_notes)
   per frame. With 32 active notes, that's 2240 iterations of HSV
   math. Could be optimized with spatial partitioning or note count cap.

3. **`rgb_matrix_indicators_kb` overhead** — 50-100 LED calls per
   frame with nested loops for macros, toggles, quick build, etc.
   Could cache LED states and only recalculate on state change.

4. **Diagnostic display active** — LCD currently shows timing data
   instead of normal layer/channel/transpose/curve info. Needs
   reverting for production use.

5. **`HALL_HARDCODE_BOTTOM` / `HALL_LOCK_BOTTOM_OUT`** — Documented
   in `hardwareupdate.md` but never implemented in code. Bottom-out
   calibration still drifts with rest recalibration.

6. **Matrix bitmap zone actuation override missing** — The matrix
   build at lines 2347-2348 doesn't apply zone actuation overrides
   for velocity modes 0 and 2 (identified but not yet fixed).

7. **No hysteresis on MIDI key threshold** — `STATIC_HYSTERESIS = 5`
   defined in matrix.h but never applied in the simple threshold mode.

---

## RGB Changes (REVERTED)

### Why these were reverted
Every RGB optimization we tried either broke the custom spatial animations
(ripple, side dots, wider, COMBINED_LOOP effects) or made no perceivable
difference to keypress lag. The user reverted to the pre-branch RGB state
to compare. Documenting all changes here so they can be redone later if
desired.

### What was changed and how to redo

#### 1. WS2812 driver: bit-bang → PWM+DMA
**Goal:** Eliminate the 2.1ms CPU stall (interrupts disabled) during LED
data transmission. Hardware PWM+DMA does the bit timing while CPU continues.

**Files:**
- `keyboards/orthomidi5x14/rules.mk` — add `WS2812_DRIVER = pwm`
- `keyboards/orthomidi5x14/config.h` — add:
  ```c
  #define WS2812_PWM_DRIVER PWMD4
  #define WS2812_PWM_CHANNEL 3
  #define WS2812_PWM_PAL_MODE 2
  #define WS2812_DMA_STREAM STM32_DMA1_STREAM6
  #define WS2812_DMA_CHANNEL 2
  ```
- `keyboards/orthomidi5x14/halconf.h` — add `#define HAL_USE_PWM TRUE`
- `keyboards/orthomidi5x14/mcuconf.h` — add:
  ```c
  #undef STM32_PWM_USE_TIM4
  #define STM32_PWM_USE_TIM4 TRUE
  #undef STM32_I2C_I2C1_TX_DMA_STREAM
  #define STM32_I2C_I2C1_TX_DMA_STREAM STM32_DMA_STREAM_ID(1, 7)
  ```

**Pin/DMA assignments:**
- PB8 = WS2812 data = TIM4_CH3 (AF2)
- DMA1 Stream 6 Ch 2 = TIM4_UP (PWM data feed)
- I2C1_TX moved from default DMA1 Stream 6 to Stream 7 (avoids conflict)

**Pros:**
- CPU is free during the 2.1ms LED transmission
- MIDI timing, ADC scanning, USB stay running during flush
- Theoretically R drops from 2400µs (bit-bang block) to ~300µs (animation only)

**Cons:**
- Uses ~6.7KB RAM for PWM duty cycle buffer (was ~210 bytes)
- TIM4 consumed (was planned for backlight PWM on PB9 = TIM4_CH4)
- DMA Stream 6 conflict with I2C1_TX required remapping
- In practice the R peak didn't change much because the animation
  calculation itself is what's slow, not the transmission

**Commits to cherry-pick to redo:**
- `dad5ad6b` Switch WS2812 from bit-bang to PWM+DMA driver
- `caad2cca` Enable HAL_USE_PWM for WS2812 PWM+DMA driver
- `e1f09ff9` Fix DMA conflict: move I2C1 TX from Stream 6 to Stream 7

#### 2. RGB flush rate: 60fps → 15fps
**Goal:** Reduce how often the expensive animation+flush cycle runs.

**File:** `keyboards/orthomidi5x14/config.h`
```c
#define RGB_MATRIX_LED_FLUSH_LIMIT 66   // 15fps
```

**Pros:** 4x fewer animation calculations per second
**Cons:** None observed visually — eye can't tell 15fps from 60fps for LEDs

**Commit:** `74405c4c` Process all 70 LEDs in one pass, reduce to 15fps

#### 3. LED process limit: split LED calculation across passes
**Goal:** Spread the animation work across multiple scan cycles instead
of one big spike.

**File:** `keyboards/orthomidi5x14/config.h`
```c
#define RGB_MATRIX_LED_PROCESS_LIMIT 9   // 8 passes of 9 LEDs each
```

**Pros (in theory):** Smaller spikes per pass, smoother MIDI timing
**Cons (in practice):**
- Custom COMBINED_LOOP.c effect ignored the limit and processed all 70
  LEDs anyway
- Trying to make it respect the limit broke spatial effects (ripple,
  side dots) because they need to see all LEDs at once

**Commits:** `1c7e6cd8`, `74405c4c`, `5e42f06b`, `80d5ebb5`, `bde204eb`,
`a0b6fab0`

#### 4. RGB indicators: run only on final pass
**Goal:** `rgb_matrix_indicators_kb()` (50-100 LED calls for macros, toggles,
quick build) was running on EVERY render pass. Restricted to last pass only.

**File:** `quantum/rgb_matrix/rgb_matrix.c`
```c
case RENDERING:
    rgb_task_render(effect);
    if (effect && rgb_task_state == FLUSHING) {  // was: if (effect)
        rgb_matrix_indicators();
        rgb_matrix_indicators_advanced(&rgb_effect_params);
    }
    break;
```

**Pros:** Eliminates 4-5x redundant indicator calls per frame
**Cons:** Visually identical — indicators always overlay animations anyway

**Commit:** `5e42f06b` Flatten RGB spikes: indicators on last pass only

#### 5. COMBINED_LOOP.c: throttle internal render to flush limit
**Goal:** The custom effect had its own 8ms render throttle (125fps) but
was only being flushed at 15-60fps. ~8x wasted computation.

**File:** `keyboards/orthomidi5x14/led/COMBINED_LOOP.c` (line ~5621)
```c
// Was: timer_elapsed(last_render_time) >= 8
bool should_render = params->init || timer_elapsed(last_render_time) >= RGB_MATRIX_LED_FLUSH_LIMIT;
```

**Pros:** ~8x fewer wasted animation calculations
**Cons:** None observed
**Note:** This is the ONE change that probably should be redone safely

**Commit:** `e22b7f6e` Fix custom RGB effect ignoring process limits

#### 6. COMBINED_LOOP.c: per-animation radius culling
**Goal:** Inner loop checked all 70 LEDs × all 32 active notes × 348-case
switch even when LEDs are clearly outside the animation's range.

**File:** `keyboards/orthomidi5x14/led/COMBINED_LOOP.c`
- Added `uint8_t max_radius` to `active_note_t` struct
- Added `anim_max_radius()` function mapping animation_type → max radius
- Set `max_radius` when notes are created
- Inner loop: `if (dr > mr && dc > mr) continue;` before switch

**Pros:** Eliminates ~80% of switch dispatches for small-radius animations
**Cons:** None — math functions already returned 0 for out-of-range LEDs,
just skips the dispatch overhead

**Commit:** `f4907b89` Per-animation radius culling

#### 7. COMBINED_LOOP.c: inline common HSV color cases
**Goal:** `get_effect_color_hsv()` takes 11 parameters; even its early-exit
has significant call overhead. 60% of calls are the trivial cases
(color_type 0, 6, 12).

**File:** `keyboards/orthomidi5x14/led/COMBINED_LOOP.c` (line ~6437)
- Inlined color_type 0 (base), 6 (max sat), 12 (desat) into the LED loop
- Fall through to function only for complex color types

**Pros:** Saves ~30-40 cycles × 60% of calls
**Cons:** None observed

**Commit:** `e4fe1e9c` Inline get_effect_color_hsv early-exits

#### 8. COMBINED_LOOP.c: 348-case switch → function pointer table
**Goal:** The inner LED loop had a 532-line switch dispatching to 172
distinct math functions. QMK's stock reactive effects use a function
pointer set once per effect.

**File:** `keyboards/orthomidi5x14/led/COMBINED_LOOP.c` (line ~5619)
- Added `typedef uint8_t (*anim_math_fn)(...)`
- Added `anim_func_table[]` with designated initializers (172 entries)
- Replaced the switch with `brightness = anim_func_table[animation](...)`

**Pros:**
- Switch dispatch ~25-35 cycles → indexed indirect call ~3 cycles
- ~9000 cycles saved per frame (190µs at 48MHz) for typical scene
- Matches QMK's stock reactive effects architecture
- 691 lines removed, 191 lines added

**Cons (the deal-breaker):**
- Functionally equivalent but user reported animations "didn't work well"
- Possibly some animations rely on the implicit type checking the switch
  provided (default case returning 0 for unknown types)
- Or the array indexing introduced different timing characteristics

**Commit:** `4d9a98c2` Replace 348-case animation switch with function pointer table

### Summary of why these were reverted
The fundamental issue: the custom spatial animations in `COMBINED_LOOP.c`
were designed to process all 70 LEDs atomically per frame using shared
state (active_notes, heatmaps, timers). Any optimization that tried to:
- Split processing across multiple passes (breaks spatial coherence)
- Change function dispatch (subtle behavior changes)
- Reduce frame rate (visually fine but didn't help perceived lag)

...either broke the animations visually or didn't address the actual
bottleneck. The actual R lag is from the O(70 × active_notes) HSV math
which is irreducible without changing the animation design itself.

### Files affected (state at time of revert)
- `keyboards/orthomidi5x14/led/COMBINED_LOOP.c` — restored to commit `4627cd89`
- `quantum/rgb_matrix/rgb_matrix.c` — restored to commit `5e42f06b^`
- `keyboards/orthomidi5x14/config.h` — removed WS2812 PWM and LED limits
- `keyboards/orthomidi5x14/mcuconf.h` — removed TIM4 PWM and I2C DMA remap
- `keyboards/orthomidi5x14/halconf.h` — removed HAL_USE_PWM
- `keyboards/orthomidi5x14/rules.mk` — removed WS2812_DRIVER = pwm

### What was NOT reverted (kept)
These RGB-adjacent changes were kept because they don't affect animation
behavior:
- The diagnostic display showing R timing values
- The merged scan loops (commit `ad6dac16` — the loop merge was kept,
  only the RGB_MATRIX_LED_FLUSH_LIMIT define was reverted)

### To redo all RGB optimizations in a new chat
Reference this section + the commit hashes listed in each subsection.
The cleanest redo path:
1. WS2812 PWM+DMA (cherry-pick `dad5ad6b`, `caad2cca`, `e1f09ff9`)
2. RGB flush + indicators changes (cherry-pick `74405c4c`, `5e42f06b`)
3. COMBINED_LOOP optimizations selectively (start with `f4907b89` radius
   culling and `e4fe1e9c` HSV inline — these are the safest)
4. Skip the function pointer table (`4d9a98c2`) unless animation behavior
   is verified equivalent

