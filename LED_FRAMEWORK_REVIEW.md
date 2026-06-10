# LED Framework Efficiency Review

## Architecture Overview

The LED system renders 70 WS2812 LEDs (one per key) through two main pipelines that run every scan cycle:

1. **COMBINED_LOOP.c** (7,801 lines) — Custom animation rendering: backgrounds, note-triggered animations, heatmaps, BPM sync
2. **orthomidi5x14.c:rgb_matrix_indicators_kb** (lines 8525-8868) — Functional LED indicators for macros, sequencers, arp, toggles, SmartChord, delay slots

### How LEDs Interact with Macros/Sequencers

- **Live MIDI notes** → `add_lighting_live_note(channel, note, velocity)` on key-on
- **Macro/Seq notes** → `add_lighting_macro_note(channel, note, track_id, velocity)` — track_id distinguishes sources
- **Keypress notes** → Synthetic `128 + row*14 + col` for non-MIDI key visualization
- **Functional indicators** → 76 configurable HSV+blink states covering arp QB (8 states), seq QB (8 states), macro playing/idle/deferred (4 states), toggle cycle steps (11 states), delay slots (2 states), SmartChord chord keys (15 states), etc.

### Per-Frame Render Pipeline (COMBINED_LOOP.c `run_efficient_effect()`, line 5679)

```
1. Timer cache update (every 5ms)
2. Heat decay (every 10ms) — live + macro heatmaps
3. Drain unified_lighting_notes[96] queue → active_notes[32]
4. Cleanup expired active notes (compaction)
5. Render background (121+ modes: BPM, static, autolight, math-based)
6. Render animations: for row(5) x col(14) x active_notes(32) → 170-case switch
7. Indicators overlay (orthomidi5x14.c) — functional LEDs for macros/seq/arp/toggles
```

---

## Efficiency Issues: Priority-Ranked

### 1. CRITICAL: No Frame-Rate Throttle

**File:** COMBINED_LOOP.c, line 5679
**Impact:** ~87% total LED CPU savings at 1kHz scan rate
**Effort:** Trivial (3 lines)

`run_efficient_effect()` runs the **full** render pipeline (background + 70 LEDs x 32 notes animation loop) on every single scan cycle. WS2812 LEDs typically refresh at 60-120Hz. At a 1kHz scan rate, 8-16x more rendering work is done than can be displayed.

**Fix:** Add at the top of `run_efficient_effect()`:
```c
static uint16_t last_render_time = 0;
if (!params->init && timer_elapsed(last_render_time) < 8) return false;  // ~120Hz cap
last_render_time = timer_read();
```

Note processing (lines 5823-5837) should still run every cycle to avoid dropped notes, but the expensive background + animation render should be throttled. This is the single highest-impact optimization.

---

### 2. CRITICAL: Floating-Point Math in ~30+ Animation Functions

**File:** COMBINED_LOOP.c, lines 3333-3505, 4468-5256
**Impact:** 200K-670K wasted cycles/frame under load
**Effort:** Medium (pattern already exists for forward variants)

On ARM Cortex-M with software FPU, each float op costs 20-50 cycles. Multiple animation families use `float` and `fabs()` in the innermost loop (70 LEDs x up to 32 active notes = 2,240 calls/frame):

| Family | Lines | Functions | Float ops/call |
|--------|-------|-----------|---------------|
| Reverse dots | 3333-3505 | 8 funcs | 5-6 float divides + `fabs()` |
| Bursts (row/col) | 4468-4558 | 4 funcs | 4-5 float divides + `fabs()` |
| Volume bars | 4654-4977 | 18 funcs | 3-4 float divides + `fabs()` |
| Peak volume | 4992-5256 | ~12 funcs | 3-4 float divides each |

Example — `row_burst_1_math` (line 4468):
```c
float distance = fabs((float)(led_col - note_col));
float radius = (elapsed_time / 150.0f) * (0.3f + (speed / 200.0f) * 4.1f);
float intensity = 1.0f - (distance / radius);
return (uint8_t)(255 * intensity * intensity);
```

The **forward** dot animations (lines 3085-3327) were already correctly converted to fixed-point 8.8 integer math. The reverse variants and burst/volume families were not. `moving_dots_all_orthogonal_reverse_math` (line 3434) shows a correctly-converted reverse variant — the same pattern should be applied to the remaining 30+ float functions.

---

### 3. HIGH: `sqrt16()` Recomputed Per-Frame for Constant Values

**File:** COMBINED_LOOP.c, line 2753
**Impact:** ~2,800 cycles/frame
**Effort:** Trivial

`run_background_math_dist()` computes `sqrt16(dx*dx + dy*dy)` for every LED every frame:
```c
for (uint8_t i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
    int16_t dx = g_led_config.point[i].x - k_rgb_matrix_center.x;
    int16_t dy = g_led_config.point[i].y - k_rgb_matrix_center.y;
    uint8_t dist = sqrt16(dx * dx + dy * dy);  // Constant — never changes!
```

**Fix:** Pre-compute `static uint8_t dist_from_center[70]` once during init.

---

### 4. HIGH: `rgb_matrix_map_row_column_to_led()` Called 70x Per Frame

**File:** COMBINED_LOOP.c, lines 5896-5897, 5880-5881, 2141, 2011, 2066
**Impact:** ~1,400+ cycles/frame
**Effort:** Trivial

The (row, col) → LED index mapping is static hardware configuration but is looked up every frame in multiple places:
- Main animation loop (line 5897): 70 calls
- Background NONE fallback (line 5881): 70 calls
- `apply_backlight` (line 2141): 70 calls
- BPM rendering (lines 2066, 2095): 70 calls each

**Fix:** Pre-compute `static uint8_t row_col_to_led[5][14]` once during init.

---

### 5. HIGH: `get_truekey_positions()` Reverse Lookup — O(420) Per Note

**File:** COMBINED_LOOP.c, lines 853-878
**Impact:** High when truekey positioning is active
**Effort:** Low

For each incoming note in truekey mode, this function scans all 70 positions for each of up to 6 LED indices:
```c
for (j = 0; j < 6; j++) {
    led_index = get_midi_led_position(...);
    for (row = 0; row < 5; row++) {
        for (col = 0; col < 14; col++) {
            rgb_matrix_map_row_column_to_led(row, col, led);
            if (led[0] == led_index) ...
```

**Fix:** Build `static led_to_rowcol[RGB_MATRIX_LED_COUNT]` reverse lookup once at init.

---

### 6. HIGH: Per-Note Speed Constants Recomputed Per-LED

**File:** COMBINED_LOOP.c, throughout animation functions
**Impact:** ~3,000-3,500 cycles/frame
**Effort:** High (architectural)

Every animation function recomputes speed-dependent values identically for all 70 LEDs. For example in `none_math` (~line 2935):
```c
uint16_t fade_time = 2000 - ((speed * 1800) / 255);  // Same for all 70 LEDs!
```

With 10 active notes, these calculations run 700 times instead of 10.

**Fix:** Split into per-note setup (compute once) + per-LED application, or hoist calculations before the LED loop. This requires restructuring since the current architecture calls math functions per-LED.

---

### 7. MEDIUM: `hsv_to_rgb()` in `apply_backlight()` for Uniform Color

**File:** COMBINED_LOOP.c, line 2147
**Impact:** ~500 cycles/frame
**Effort:** Trivial

`apply_backlight()` computes `hsv_to_rgb()` **inside** the 70-LED loop for a uniform color:
```c
for (uint8_t i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
    HSV hsv = {h, s, v};  // Same every iteration
    RGB rgb = hsv_to_rgb(hsv);  // 70 identical conversions
    rgb_matrix_set_color(i, rgb.r, rgb.g, rgb.b);
}
```

**Fix:** Hoist `hsv_to_rgb()` out of the loop. `render_autolight_with_params()` (line 1936) already does this correctly.

---

### 8. MEDIUM: Background Rendered for LEDs Overwritten by Animations

**File:** COMBINED_LOOP.c, lines 5861-5887 vs 6488-6494
**Impact:** ~500-1,000 cycles/frame
**Effort:** Low

Background is rendered first for all 70 LEDs, then the animation loop overwrites any LED with active notes. The background `hsv_to_rgb()` + `rgb_matrix_set_color()` for those LEDs is wasted work.

**Fix:** Build a bitmap of LEDs that will be animated, skip them during background render.

---

### 9. MEDIUM: Float `brightness_factor` in Indicators

**File:** orthomidi5x14.c, line 8538
**Impact:** ~500 cycles/frame
**Effort:** Trivial

```c
float brightness_factor = enhanced_brightness / 255.0f;
```

This float is used in every `func_led_set_color()` call and manual `(uint8_t)(r * brightness_factor)` multiplies throughout the 344-line indicators function.

**Fix:** Use integer scaling: `uint16_t bright256 = enhanced_brightness;` then `(r * bright256) >> 8`.

---

### 10. MEDIUM: 21 Linear Scans Per Frame in `get_special_key_led_index()`

**File:** orthomidi5x14.c, lines 8547-8763
**Impact:** ~1,470 comparisons/frame
**Effort:** Low

`get_special_key_led_index()` does a linear scan through `led_categories[layer].leds[]` (up to 70 entries) to find a category match. It is called 21 times per frame:

| Call site | Count | Categories |
|-----------|-------|-----------|
| Caps lock | 1 | 29 |
| Tap tempo | 1 | 30 |
| Macros | 4 | 31-34 |
| Gaming mode | 1 | 51 |
| Arp QB slots | 4 | 35, 48, 49, 50 |
| Seq QB slots | 8 | 36-43 |
| Arp/Seq play | 2 | 44, 45 |

Each also internally calls `get_highest_layer()`.

**Fix:** Cache results in a `static uint8_t category_to_led[60]` array, rebuild only on layer change.

---

### 11. MEDIUM: 4 Redundant `get_highest_layer()` Calls

**File:** orthomidi5x14.c, lines 8585, 8633, 8662, 8780
**Impact:** Low per-call, but accumulates
**Effort:** Trivial

`get_highest_layer(layer_state | default_layer_state)` is computed 4 times in separate block scopes within the same function, plus ~21 more times inside `get_special_key_led_index()`.

**Fix:** Compute once at the top of the function, pass as parameter.

---

### 12. MEDIUM: BPM Pulse Decay Uses Float

**File:** COMBINED_LOOP.c, lines 1917-1918
**Impact:** Low (~100 cycles/frame)
**Effort:** Trivial

```c
float progress = (float)elapsed / pulse_duration;
bpm_pulse_intensity = (uint8_t)(255 * (1.0f - progress) * (1.0f - progress));
```

**Fix:** Integer quadratic: `remaining = pulse_duration - elapsed; intensity = remaining * remaining * 255 / (pulse_duration * pulse_duration);`

---

### 13. MEDIUM-LOW: `rand()` in Hot Color Path

**File:** COMBINED_LOOP.c, lines 399, 432, 456, 494, 543, 594
**Impact:** Visible flicker + cycles wasted
**Effort:** Low

`rand()` is called inside `get_effect_color_hsv()` for Rainbow color types (types 3, 9, 15, 21, 27, 33). On embedded systems `rand()` uses a division-based LCG. Since this is called per-LED-per-note when brightness improves, it can produce visible flicker.

**Fix:** Use a faster LFSR-based PRNG or pre-compute random hues per-note once.

---

### 14. LOW-MEDIUM: Circular Buffer O(n) Shift

**File:** COMBINED_LOOP.c, lines 163-170, 194-200, 218-223
**Impact:** Low (rare overflow path, but remove runs every note-off)
**Effort:** Trivial

Buffer overflow shifts 96 entries element-by-element (6 individual byte copies per entry). `remove_lighting_macro_note` (line 218) shifts on every note-off event.

**Fix:** Use `memmove()` or a true ring buffer with head/tail indices.

---

### 15. BUG: Sustained Keys Cleanup Always Clears All Keys

**File:** COMBINED_LOOP.c, lines 5837 vs 5843-5858
**Impact:** Functional bug — sustain effect may not work correctly
**Effort:** Trivial

After `unified_lighting_count = 0` (line 5837), the sustained keys cleanup loop (line 5846) iterates `unified_lighting_count` which is now always 0. The `still_active` check never finds a match, so **all sustained keys are deactivated every frame**.

**Fix:** Move sustained keys cleanup BEFORE `unified_lighting_count = 0`, or check `active_notes[]` instead.

---

### 16. LOW: Redundant `calculate_distance()` in Color Cases 24-35

**File:** COMBINED_LOOP.c, lines 517-614
**Impact:** Low-medium (redundant work when these color types active)
**Effort:** Trivial

Cases 24-35 in `get_effect_color_hsv()` each call `calculate_distance()` locally, shadowing the pre-computed `distance` variable from line 477. The LUT value was already computed.

**Fix:** Use the pre-computed `distance` variable instead of recalculating.

---

## Existing Optimizations (Already Done Well)

- `distance_lookup[5][14][5][14]` — pre-computed distance table avoids per-call sqrt in ripple effects
- Early spatial rejection in most animations (`if (led_row != note_row) return 0`)
- Compacted `active_notes[]` array — no gaps in hot render loop
- 5ms timer cache — reduces `timer_read()` calls
- Fixed-point 8.8 math in forward dot animations (lines 3085-3327)
- `sqrt8_table[256]` — LUT for fast integer sqrt
- Per-layer LED caches for macros, arp presets, seq presets, toggles — avoids per-frame keycode scanning
- `smartchordlight == 2` early exit skips all indicators
- `rgb_matrix_indicators_user()` early exit for LAYERSETS mode

---

## Summary: Impact vs Effort Matrix

| # | Optimization | Est. Savings | Risk | Effort |
|---|-------------|-------------|------|--------|
| **1** | Frame-rate throttle (120Hz cap) | **~87% of total LED CPU** | Very low | 3 lines |
| **2** | Convert float animations to fixed-point | **200K-670K cycles/frame** | Low (pattern exists) | Medium (~30 funcs) |
| **3** | Pre-compute `dist_from_center[]` | ~2,800 cycles/frame | None | Trivial |
| **4** | Pre-compute `row_col_to_led[]` | ~1,400+ cycles/frame | None | Trivial |
| **5** | Reverse lookup table for truekey | ~420 scans/note avoided | None | Low |
| **6** | Hoist per-note speed calculations | ~3,000 cycles/frame | Low | High |
| **7** | Hoist `hsv_to_rgb()` in `apply_backlight` | ~500 cycles/frame | None | Trivial |
| **8** | Skip background for animated LEDs | ~500-1,000 cycles/frame | Low | Low |
| **9** | Integer brightness in indicators | ~500 cycles/frame | None | Trivial |
| **10** | Cache `get_special_key_led_index()` results | ~1,470 comparisons/frame | None | Low |
| **11** | Single `get_highest_layer()` call | Cleanliness | None | Trivial |
| **12** | Integer BPM pulse decay | ~100 cycles/frame | None | Trivial |
| **15** | Fix sustained keys cleanup bug | **Correctness** | None | Trivial |

**Recommended implementation order:** 15 (bug fix) → 1 (frame throttle) → 3, 4, 7, 9, 11, 12 (trivial wins) → 10, 5 (low effort) → 2 (medium effort, high payoff) → 8, 6 (architectural)
