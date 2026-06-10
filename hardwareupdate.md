# Hardware Update — new PCB bring-up (branch `claude/review-oled-orthomidi-hXBzn`)

Branch goal: get the new orthomidi5x14 PCB *connecting and basically working*
so you can verify hardware, then iterate on features.

This file documents what changed, why, and where, so a future pass can
properly implement the placeholder paths.

Toggle for the whole new-PCB build:

```make
# keyboards/orthomidi5x14/rules.mk
LUNA_QP_ENABLE = yes      # new PCB — ST7789 + remapped pins + inverted sensors
LUNA_QP_ENABLE = no       # legacy PCB — unchanged behaviour
```

Every change below is gated under `#ifdef LUNA_QP_ENABLE` or
`ifeq ($(LUNA_QP_ENABLE), yes)`. With it set to `no` the firmware is
byte-identical to the legacy build.

---

## 1. Pin remap

Chip is STM32F412 LQFP-48. Functions that changed pins between the legacy
and new PCBs:

| Chip pin | GPIO | Legacy function | New function |
|---:|---|---|---|
| 2 | PC13 | encoder 0 pad B | **LCD RST** |
| 3 | PC14 | encoder 0 pad A | **LCD CS** |
| 4 | PC15 | encoder 1 pad A | **LCD RS (D/C)** |
| 15 | PA5 | ADG706_A0 (MUXA) | **SPI1_SCK (AF5)** |
| 17 | PA7 | ADG706_A2 (MUXC) | **SPI1_MOSI (AF5)** |
| 18 | PB0 | ADG706_A3 (MUXD) | **Encoder switch** |
| 21 | PB10 | unused | **MUX A** |
| 25 | PB12 | unused | **MUX B** |
| 26 | PB13 | unused | **MUX D** |
| 27 | PB14 | encoder 0 click | **MUX C** |
| 28 | PB15 | encoder 1 click | (free) |
| 40 | PB4 | encoder 1 pad B | **Encoder A** |
| 41 | PB5 | unused | **Encoder B** |
| 46 | PB9 | unused | **Backlight (GPIO high; TIM4_CH4 PWM later)** |

Functions that **did NOT move** (same pin, same purpose):

| Chip pin | GPIO | Function |
|---:|---|---|
| 10-14 | PA0-PA4 | Matrix ADC rows |
| 30 | PA9 | Sustain pedal / footswitch |
| 38 | PA15 | MIDI OUT (USART1_TX, AF7) |
| 39 | PB3 | MIDI IN (USART1_RX, AF7) |
| 42 | PB6 | I²C1 SCL — was OLED+EEPROM, now EEPROM only |
| 43 | PB7 | I²C1 SDA — same |
| 45 | PB8 | WS2812 LED data |

Mux address pins now: `ADG706_A0=PB10`, `A1=PB12`, `A2=PB14`, `A3=PB13`.
**Critical fix during bring-up:** the legacy `keyboard_post_init_user`
called `setPinInputHigh(B14)` / `setPinInputHigh(B15)` for the old
encoder clicks. On the new PCB B14 is MUX C; that init reconfigured B14
as input-with-pullup and held bit 2 of the mux address HIGH, which made
columns 1-4 duplicate to 5-8 and 9-10 to 13-14. Both that init and the
matching `readPin(B14)` polling are now gated on `!LUNA_QP_ENABLE`.

---

## 2. SPI peripheral swap (SPI2 → SPI1)

`mcuconf.h` previously enabled SPI2 with DMA1 streams 3/4. Nothing in the
firmware actually called any SPI API against SPID2 — it was dead /
preparatory config. With LCD pins committed to PA5/PA7 (SPI1's only
alt-function pins on F412) we MUST use SPI1.

Under `LUNA_QP_ENABLE` the active SPI config is:

| Setting | Value |
|---|---|
| `STM32_SPI_USE_SPI1` | `TRUE` |
| `STM32_SPI_SPI1_TX_DMA_STREAM` | DMA2 Stream 3 |
| SPI1 RX DMA | **deliberately not assigned** (LCD is write-only; default DMA2 Stream 0 would collide with the ADC matrix scan) |
| `SPI_USE_WAIT` in `halconf.h` | `TRUE` (required for QMK's `spi_master.c` synchronous primitives) |

SPI1 lives on APB2 (96 MHz at our PLL settings) vs SPI2 on APB1 (48 MHz),
so panel clock can run up to ~24 MHz with divisor 4 — comfortable for the
240×320 ST7789.

I²C1 (PB6/PB7) is unchanged. EEPROM (CAT24C512 @ 0x50) keeps working on
that bus — the OLED that used to share it (address 0x3C) is just gone.

---

## 3. Encoder consolidation

Legacy PCB had two encoders. New PCB has one:

```c
#ifdef LUNA_QP_ENABLE
#define ENCODERS_PAD_A      { B4 }
#define ENCODERS_PAD_B      { B5 }
#define ENCODER_CLICK_PINS  { B0 }
#else
#define ENCODERS_PAD_A      { C14, C15 }
#define ENCODERS_PAD_B      { C13, B4 }
#define ENCODER_CLICK_PINS  { B14, B15 }
#endif
```

`keymaps/vial/keymap.c` similarly gates the `encoder_map[]` shape:
one `ENCODER_CCW_CW(KC_VOLD, KC_VOLU)` per layer under `LUNA_QP_ENABLE`,
two on legacy.

---

## 4. ADC / sensor direction change

New sensors press the ADC **upward** (rest ~1700-1800 physical, pressed
~3000+ physical). Legacy code is built around "press lowers ADC" (rest
~2000, pressed ~1100). Rather than rewrite the matrix / distance / RT /
velocity / calibration logic to be direction-agnostic, the new build
inverts at the ADC source so everything downstream sees the legacy
orientation.

```c
// quantum/matrix.c — both adcConvert call sites
#ifdef HALL_SENSOR_PRESS_RAISES_ADC
for (uint8_t i = 0; i < ADC_GRP_NUM_CHANNELS; i++) {
    samples[i] = 4095 - samples[i];
}
#endif
```

After inversion the firmware sees: rest ~2300, typical press ~1095, hard
press ~800 — the same shape (rest > bottom) the legacy code expects.

### Calibration policy

| Source | Behaviour | Defined by |
|---|---|---|
| Rest position | Auto-calibrates the same way the legacy code did (5 s stability hold, 2% jitter tolerance, 10% near-rest window) | unchanged — `update_calibration()` rest-drift block runs as before |
| Bottom-out | **Hardcoded**. Does NOT drift. | `HALL_HARDCODE_BOTTOM 1100` overrides the warm-up estimate. `HALL_LOCK_BOTTOM_OUT` gates the bottom-drift block in `update_calibration()` |

Why bottom hardcoded but rest dynamic: locking the bottom matches the
old PCB's "nominal range" feel (DEFAULT_ZERO_TRAVEL_VALUE 2000 -
DEFAULT_FULL_RANGE 900 = 1100), prevents the actuation boundary from
drifting under-foot, and `distance_lut.h`'s `if (adc <= bottom_out)
return 255;` clamp handles harder-than-bottom presses cleanly.

### Valid-ADC bounds widened

The legacy matrix had a hard `if (adc < 1000 || adc > 2500) force_release;`
to reject empty-socket readings. On the new sensors, hard presses
legitimately drop firmware-internal ADC to ~800 — which the 1000 floor
treated as "broken sensor" and force-released the key.

Bounds are now `VALID_ANALOG_RAW_VALUE_MIN` / `_MAX` macros (definable
via `config.h` override; defaults preserved for legacy). New PCB uses:

```c
#define VALID_ANALOG_RAW_VALUE_MIN 500
#define VALID_ANALOG_RAW_VALUE_MAX 2900
```

### Summary of new-PCB ADC defines (`keyboards/orthomidi5x14/config.h`)

```c
#ifdef LUNA_QP_ENABLE
#define HALL_SENSOR_PRESS_RAISES_ADC      // invert raw samples at ADC source
#define HALL_LOCK_BOTTOM_OUT              // skip bottom-out drift in update_calibration
#define HALL_HARDCODE_BOTTOM 1100         // override warm-up bottom estimate
#define VALID_ANALOG_RAW_VALUE_MIN 500    // widen ghost-press rejection floor
#define VALID_ANALOG_RAW_VALUE_MAX 2900   // (and ceiling)
#endif
```

`DEFAULT_ZERO_TRAVEL_VALUE` and `DEFAULT_FULL_RANGE` are untouched —
they describe what the firmware sees *after* inversion, which is
essentially the legacy sensor model.

Also: `DEFAULT_ACTUATION_VALUE` was bumped 127 → 255 in `process_midi.h`
(separate cherry-pick from the bring-up branch — applies to both PCBs).
Blank-EEPROM fast-path in `start_chunked_eeprom_load_all()` was added
on the same cherry-pick.

---

## 5. Bootmagic

`BOOTMAGIC_ENABLE = yes` in `rules.mk`, configured key is row 0 col 0
(top-left) via `BOOTMAGIC_LITE_ROW`/`_COLUMN`.

Stock `bootmagic_lite()` reads the matrix bitmap which only sets when
`distance >= per_key_actuation` (255 = full 4mm press). Combined with
the analog warm-up loop capturing whatever-ADC-at-boot as "rest" — if
the user held the boot key while plugging in, the firmware locked the
pressed ADC as rest and distance read 0 forever.

A strong override of `bootmagic_lite()` lives in
`keyboards/orthomidi5x14/orthomidi5x14.c`. It runs several extra
analog scans, then reads the raw ADC directly via
`analog_matrix_get_raw_value(0, 0)`. If the post-inversion raw is
below ~1545 (= physical > ~2550, > halfway from rest to bottom) it
calls `eeconfig_disable` + `bootloader_jump`. Bypasses both the
actuation point AND the warm-up calibration.

**To enter bootloader: hold the top-left key while plugging in.**

---

## 6. LCD scaffolding

Driver: ST7789 via Quantum Painter. Built when `LUNA_QP_ENABLE=yes`:

```make
QUANTUM_PAINTER_ENABLE = yes
QUANTUM_PAINTER_DRIVERS += st7789_spi
```

### Init (`keyboard_post_init_user`)

```c
setPinOutput(LCD_BL_PIN);        // PB9 — backlight as GPIO, always-on
writePinHigh(LCD_BL_PIN);        //   (PWM via TIM4_CH4 is a follow-up)
spi_init();                      // bring up SPID1
luna_lcd = qp_st7789_make_spi_device(
    240, 320,                    // panel native dimensions
    LCD_CS_PIN, LCD_DC_PIN, LCD_RST_PIN,
    4,                           // SPI divisor — ~24MHz at APB2=96MHz
    3);                          // ST7789 SPI mode 3
qp_init(luna_lcd, QP_ROTATION_0);
qp_clear(luna_lcd);
qp_flush(luna_lcd);
luna_qp_init(luna_lcd);          // hands the device to the luna_qp module
lcd_show_layer();                // initial paint so the screen isn't blank
```

### Current render path (proof-of-life only)

Only one thing renders on the LCD right now: **"Layer X"** text near
the top-left, in cyan, redrawn whenever the active layer changes
(debounced 100 ms — see below).

Text renderer (`lcd_draw_char` / `lcd_draw_string` /
`lcd_paint_pixel_rect` / `lcd_show_layer` in `orthomidi5x14.c` near
the top of the file) uses QMK's bundled OLED font
(`drivers/oled/glcdfont.c`) and emits one `qp_rect` per lit pixel at
`scale=5` (30 × 40 px glyphs). For "Layer N" that's ~150 `qp_rect`
calls per repaint — fires once per layer change, never per frame.

Layer is read with `get_highest_layer(layer_state | default_layer_state)`
— same expression `oled_task_user` uses for the legacy header line, so
the data source is identical.

### Debounce

`housekeeping_task_user` polls the layer every main-loop iteration but
only calls `lcd_show_layer()` when the layer has been stable for
≥ 100 ms (`LCD_LAYER_DEBOUNCE_MS`). Prevents transient matrix flicker
(if it ever happens) from flooding the SPI bus with repaint storms.

Idle cost per iteration: one `get_highest_layer` call + one uint8_t
compare + one timer-subtraction. No SPI traffic between layer settles.

### What's deliberately NOT done yet

- The full OLED render pipeline (`render_luna`, `render_tab`,
  `oled_render_keylog`, menus, quick build, feature rows) is **left
  intact and untouched**. It still writes to QMK's `oled_buffer`. With
  no SH1107 on the I²C bus the buffer never gets flushed anywhere —
  but the data is ready to tap into when we want to surface it on the
  LCD.
- The native Quantum Painter virtual-keyboard renderer
  (`keyboards/orthomidi5x14/luna_qp/luna_qp.c` —
  `luna_qp_render_delta`) is **not called from `oled_task_user`**.
  Producing random-color streaks + freezes during testing; needs
  separate SPI diagnosis before re-enabling.
- A proper LCD render of channel / playing style / transposition /
  chord name / loop interface / menus is **not implemented**. The
  scaffolding is here; future work is to either (a) blit the OLED
  framebuffer to the LCD with appropriate throttling, or (b)
  reimplement those renderers natively against QP with QFF fonts.
- Backlight PWM dimming via TIM4_CH4 on PB9 is **not wired**.
  Backlight is GPIO-high (always on).

### Why no per-frame SPI traffic

QP `qp_rect` calls block the calling thread until the SPI DMA
completes. ADC and SPI use different DMA streams (DMA2 Stream 0 vs
Stream 3) so the hardware doesn't fight, but the main loop is serial.
Many small `qp_rect` calls per frame starve the matrix scan and make
keypresses feel queued/delayed. The OLED never had this problem because
its calls wrote to a local RAM framebuffer (fast) and the I²C flush was
async + throttled to 50 ms.

The Luna keyboard renderer fell into exactly this trap and produced
both visual artifacts and matrix lag. Until that's resolved, the LCD
path is kept to one repaint per layer-change-settle, ~10-20 ms each,
fires at most a few times a minute during normal use.

---

## 7. Quick-reference build switch

```make
# keyboards/orthomidi5x14/rules.mk

# new hardware:
LUNA_QP_ENABLE = yes

# legacy hardware (everything reverts to pre-bring-up):
LUNA_QP_ENABLE = no
```

When `no`:

- `OLED_ENABLE = yes` block stays active, OLED works on legacy I²C
- ADG706 mux address pins are A5/A6/A7/PB0 (legacy)
- Two encoders on legacy pins
- SPI2 enabled in `mcuconf.h` (legacy, unused)
- No QP, no LCD render, no Hall inversion, no hardcoded bottom-out,
  no `VALID_ANALOG_RAW_VALUE_*` override
- Legacy bootmagic check (matrix-bitmap based)

When `yes`:

- OLED driver still compiled in (legacy renderers leave data in
  `oled_buffer` for future blit) but the SH1107 isn't on the bus so
  init fails and no I²C flush happens
- Quantum Painter + ST7789 driver linked
- Single encoder
- SPI1 active with DMA2 Stream 3 TX
- Mux on PB10/PB12/PB14/PB13
- Hall direction inverted at source
- Bottom-out locked at firmware ADC 1100, rest auto-calibrates
- Valid ADC range 500-2900
- Custom bootmagic checks raw ADC directly
- Single-encoder `encoder_map[]`
- LCD shows "Layer X" only, debounced on layer change

---

## 8. Files touched

| File | What changed |
|---|---|
| `keyboards/orthomidi5x14/rules.mk` | `LUNA_QP_ENABLE` master toggle, conditional QP enable, OLED kept compiled, BOOTMAGIC re-enabled, MIDI serial UART pull-in |
| `keyboards/orthomidi5x14/config.h` | Gated encoder pins, gated mux pins, SPI pin macros, LCD pin macros, QP sizing knobs, ADC direction + hardcoded bottom + lock-bottom + valid-range overrides, USART control regs |
| `keyboards/orthomidi5x14/mcuconf.h` | SPI2 → SPI1 swap with DMA2 Stream 3 TX (RX intentionally absent) |
| `keyboards/orthomidi5x14/halconf.h` | `SPI_USE_WAIT TRUE` |
| `keyboards/orthomidi5x14/orthomidi5x14.c` | Includes, QP device creation, backlight on, encoder click pin gating (B14/B15 → B0), `bootmagic_lite()` strong override, `lcd_show_layer` + text helpers, debounced `housekeeping_task_user`, `cprog_voices_snapshot()` accessor, all 42 `LUNA_ZONE_SET` press-site insertions |
| `keyboards/orthomidi5x14/keymaps/vial/keymap.c` | Single vs dual `encoder_map[]` |
| `keyboards/orthomidi5x14/luna_qp/` (new dir) | Full module — geometry table, state collector, voice tracker, QP renderer, colors, README, tests (not currently called from runtime) |
| `quantum/matrix.c` | Hall inversion at adcConvert sites, `HALL_LOCK_BOTTOM_OUT` gate, `HALL_HARDCODE_BOTTOM` override, `VALID_ANALOG_RAW_VALUE_*` macros, blank-EEPROM fast-path |
| `quantum/matrix.h` | `VALID_ANALOG_RAW_VALUE_*` made overridable |
| `quantum/process_keycode/process_midi.h` | `DEFAULT_ACTUATION_VALUE 127 → 255` (cherry-picked; applies to both PCBs) |
| `quantum/process_keycode/process_midi.c` | `LUNA_BG_ON/OFF` hooks in the 6 central note-emit wrappers — write to `voice_paint` for arp/seq/delay/dynchord rendering when Luna virtual keyboard comes online |
