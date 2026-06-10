# LCDlayout.md — orthomidi5x14 main-page LCD architecture

A working-knowledge dump of how the 240×320 LCD is composed, rendered,
and themed on this keyboard. Written so a future change to a row, font,
colour, or split mode doesn't require re-deriving the whole pipeline
from scratch.

---

## 1. Physical layout

| Item | Value |
|---|---|
| Panel | ST7789 240×320 SPI LCD |
| Driver | QMK Quantum Painter (`qp_*`) via `luna_lcd` |
| Address | `luna_lcd` = the only panter_device used outside menus |
| `LCD_OLED_BLIT_W` | 240 (pixels per OLED row) |
| `LCD_OLED_PAGE_STRIDE` | 240 bytes (one OLED page) |
| `LCD_OLED_BLIT_PAGES` | 40 (8 px each → 320 px tall = full LCD) |

The entire LCD is treated as a virtual OLED buffer that is delta-blitted
into the LCD framebuffer once per LCD cycle. **The OLED conceptually
covers the entire 240×320 LCD area**, not just the top portion.

`oled_buffer` (provided by QMK's OLED driver) is `40 × 240 = 9600` bytes.

---

## 2. Y / page coordinate system

```
LCD Y     OLED page (8 px each)        User row (16 px each, 1-indexed)
0..7      page 0                        row 1 (top half)
8..15     page 1                        row 1 (bottom half)
16..23    page 2                        row 2 (top half)
24..31    page 3                        row 2 (bottom half)
...
112..127  pages 14..15                  row 8
128..143  pages 16..17                  row 9   ← luna piano starts here
144..159  pages 18..19                  row 10
...
192..207  pages 24..25                  row 13
208..223  pages 26..27                  row 14
...
288..303  pages 36..37                  row 19
304..319  pages 38..39                  row 20  ← bottom of LCD
```

- One **user row** = 16 px tall = 2 OLED pages.
- One **OLED page** = 8 px tall = 1 byte per X column.
- Bit 0 of a page byte is the *topmost* pixel of that page; bit 7 is
  the *bottom-most*.
- The LCD is 320 / 16 = **20 user rows tall** in 1-indexed counting.

The QP painter and the OLED-blit both use the same Y coordinate. There
is no offset; OLED Y maps 1:1 to LCD Y in the OLED area, and QP draws
to LCD Y directly.

`oled_set_cursor(0, P)` sets the OLED cursor to (X=0, page=P). A
subsequent `oled_write_raw(buf, N)` writes `N` bytes starting at that
page in OLED column order (left to right, then page by page).

---

## 3. Region map (current main page, no-split, not midiswitch)

```
LCD Y      Content
0..15      row 1: small TR sign on the right + dotted CH/TR box tops
16..31     row 2: big CH (left), big TR digits (right),
                  small "Style" label (centre), dotted box bottom
32..47     row 3: small playing-style value (centre)
48..63     row 4: small vel range "MIN-MAX" (centre) when edited
64..95     rows 5-6: chord display (big 2x scaled when ≤10 chars)
96..111    row 7: keylog
112..127   row 8: covered by luna piano
112..193   luna piano, FULL (82px) — used with 0–4 boxes
112..158   luna piano, COMPACT (47px, Lunapianolite) — used with 5–8 boxes
...        feature-box rows below the piano (see below)
288..303   row 19: BPM (left), beat squares (x~42..90), Layer name (right)
```

Four **beat-counter squares** are painted via QP just right of the BPM
number (`beat_squares_qp_render`): 4×4 px each, the current beat's square
grows to 10×10, advancing 1-2-3-4 with `bpm_beat_count`. They share the
exact beat state the BPM-background RGB effects use, so they stay in
lockstep. **Beat-sync fix:** the BPM RGB effects used to each call
`update_bpm_flash()` themselves, which fought `midi_clock_task()` and made
the beat drift on BPM / effect changes; now the beat has a single authority
per scan (`midi_clock_task()` when a clock runs, else an `update_bpm_flash()`
fallback), and the effects only *read* `bpm_flash_state` / `bpm_beat_count`.

`LUNA_LCD_BASE_Y` = **112**.

The piano **never moves** (anchored at y=112) — it only changes **height**.
Feature boxes (§13) are 51×51 (≈50) rounded squares with a 2px ring, below
it with ≥7px gaps:

- **0–4 boxes** → **full piano** (112..193) + 7px + one row
  (`LCQ_ROW_CY_1ROW` = 226 → y 201..251).
- **5–8 boxes** → **compact piano** (112..158, `Lunapianolite.png` — white-key
  tail trimmed) + 7px + row 0 (`LCQ_ROW0_CY_2ROW` = 191 → y 166..216) + 7px +
  row 1 (`LCQ_ROW1_CY_2ROW` = 249 → y 224..274).

The piano hides entirely only for menus / tab view / 8-track loop mode. On
any layout change (row count / hide), the painter blacks the whole luna+box
region (112..287) once (`lcd_frame.region_reset`) and the piano + boxes
full-repaint. Compact height is set via `luna_qp_set_compact()`.

---

## 4. The OLED blit pipeline (`lcd_blit_oled_chunk`)

This is the only path that gets monochrome OLED bytes onto the colour
LCD.

1. Iterate pages 0..39, XOR-diffing the current `oled_buffer` against
   `lcd_prev_oled` snapshot.
2. For each page with any diff, scan its 240 columns and emit
   horizontal runs of identical pixel value (0 or 255).
3. Vertically merge identical adjacent runs across pages (a single
   long `qp_rect` instead of N short ones).
4. Each emitted `qp_rect` uses the **single text colour**
   `(OLED_TEXT_HUE, OLED_TEXT_SAT, v)` — currently `(17, 255, *)` =
   orange. `v` is 255 (lit) or 0 (background = black).
5. After the page is drained, `memcpy(prev_oled, oled_buffer)` so the
   next pass sees a fresh baseline.

Implications:

- The OLED text area is always rendered in *one* colour. Per-pixel
  colour requires going *around* the blit (see "QP overlay" below).
- The blit only emits *changed* pixels. If we never touch a region, it
  stays as-is on the LCD forever. That's what allows the
  luna piano (drawn via QP) to coexist below the OLED area.
- Order of operations per LCD cycle:
  1. Pre-paint blackout (luna_blackout, loop_clear) via QP.
  2. Drain `lcd_blit_oled_chunk` (OLED → LCD orange).
  3. `draw_main_frame_qp_on_lcd` (currently a no-op stub).
  4. `luna_qp_render_delta` (paints luna piano via QP).
  5. `loop_circles_qp_render` (paints loop rings via QP).

Steps 4 and 5 paint *over* the OLED area in non-orange colours. The
OLED area is below this in the same SPI write sequence.

---

## 5. Fonts

| Font | Cell | Use |
|---|---|---|
| 12×16 Meadow | `lib/glcdfont.c`, 24 bytes per glyph | Standard small text on OLED |
| 24×32 (2x of above) | Computed at render time | Big numbers, MIDIswitch label, big chord |

`OLED_FONT_HEIGHT = 16`, `OLED_FONT_WIDTH = 12`. There is no smaller
font available — all small text uses the Meadow 12×16 face. **One
12-px column = "one column" in the layout vernacular**, so 6 cols = 72 px
and the "big number" cells are 2 cols wide (24 px) per digit.

### `render_small_into_buf(buf, start_x, page_top, text)`

Writes 12×16 glyphs into a 4-page buffer at `(start_x, page_top..page_top+1)`.
Bits are mapped:
- Glyph byte `0..11` → page `page_top` byte at `start_x + col`
- Glyph byte `12..23` → page `page_top + 1` byte at `start_x + col`

### `render_big_into_buf(buf, start_x, text)`

Writes 24×32 glyphs into pages **0..3** of the passed buffer (hard-coded).
Each input column expands to two output columns; each input bit expands
to two output bits (one in the top output page, one in the bottom).

To write big text into a different band of pages, pass a *pointer-offset*
buffer: `render_big_into_buf(&buf[K * W], start_x, text)` shifts the
output by K pages.

### `oled_write_big_centered(row, text)`

Public helper. Writes 12×16 → 24×32 text horizontally centered, occupying
OLED pages `row*2 .. row*2 + 3` (= 2 user rows). Used by the chord big
display and the midiswitch fallback.

### `render_small_into_buf` for stacked stuff

To stack two small lines in one band, call twice with `page_top=0` and
`page_top=2`. The wrapper `oled_write_two_small_centered` does this.

---

## 6. Main-page rendering (no-split path)

Everything below assumes none of `keysplittransposestatus`,
`keysplitstatus`, `keysplitvelocitystatus` is non-zero. Split mode
falls back to the old per-row layout + dashes (kept for compatibility,
shifted up 1 row alongside the no-split rework).

### Block 1 — pages 0..5 (rows 1..3)

Renders into a single static `buf6[LCD_OLED_BLIT_W * 6]` (1440 bytes,
**`.bss`, not stack** — see footgun #1).

| Layer (paint order) | Where | What |
|---|---|---|
| Big CH | band pages 0..3, X=0 (≥2-dig) or X=12 (1-dig) | Channel number, 24×32 |
| Big TR digits | band pages 0..3, right-aligned to X=239 | Transpose number |
| Small TR prefix | band page 0..1, just left of big TR | "+" / "-" / "*" |
| Small TR suffix | band page 0..1, just right of big TR | "*" / "**" |
| Small "Style" | band pages 2..3, centred to 240 px | Static label |
| Small playing-style value | band pages 4..5, centred to 240 px | "SOFTEST", "LINEAR", etc. |
| Dotted CH box | OR-merged onto pages 0..3 | Left vert + right vert + bottom |
| Dotted TR box | OR-merged onto pages 0..3 | Mirror of CH box |

Then `oled_set_cursor(0, 0); oled_write_raw(buf6, 1440)` ships it.

#### Dotted box geometry

```
Box height : Y=0..31 (rows 1-2)
Box top    : open (no horizontal line at Y=0)
Verticals  : page byte |= 0x55 = bits 0,2,4,6 lit (= Y=0,2,4,6 within page)
Bottom     : page 3 bit 7 |= 0x80 alternating every other X column
Corners    : naturally fall OFF in the dotted pattern (rounded look)

CH content cols   : 1-dig = 3 (1 blank + 2 big) ; 2-dig = 4 ; 3-dig = 6
CH box width      : content_cols + 1 columns × 12 px
                    1-dig = 48 px (X=0..47)
                    2-dig = 60 px (X=0..59)
TR content cols   : pi + di*2 + si
TR box width      : content_cols × 12 px (NO +1 — TR sign on the medial
                    side already supplies padding)
                    "+0"   → 3 cols → 36 px → X=204..239
                    "+12"  → 5 cols → 60 px → X=180..239
                    "+12*" → 6 cols → 72 px → X=168..239
```

### Block 2 — pages 6..7 (row 4)

Static `buf2[LCD_OLED_BLIT_W * 2]` (480 bytes, `.bss`).

Vel range "MIN-MAX" centred when the live `keyboard_settings.he_velocity_min/max`
differ from the preset default (cached in `main_rc.layout_def_min/max`).
Otherwise blank.

**Always re-rendered when the curve changes** (`cu_changed` flag) so the
firmware-side reset of vmn/vmx on style change can't leave stale text.

### Chord + keylog — pages 8..13

Chord renders 2x scaled (`oled_write_big_centered(4, ...)`) when the chord
string is ≤ 10 chars; otherwise small text via `WRITE_ROW(8, row)`. The
"blank line" between chord and keylog at row 6 is `oled_clear_row(5)`
(which clears 2 pages starting at page 10).

Keylog is plain `oled_write` at `oled_set_cursor(0, 12)`.

### BPM / Layer — pages 36..37 (row 19)

Static `bpmlayer_buf[LCD_OLED_BLIT_W * 2]`. BPM left-aligned at X=0,
Layer name right-aligned at X=239. Both use the same Meadow 12×16 font
and get the orange OLED-text colour.

Rendered from a *different* function (`oled_task_user` in
`housekeeping_task_user`'s flow), not from `oled_render_keylog`, because
it tracks `r0_layer/r0_bpm/r0_layer_name/r0_msg` separately and
participates in the `mode_display_msg` overlay system.

---

## 7. MIDIswitch fallback

When the active layer has no MIDI / custom keycodes (no keycode > 0x7000
except 0xC9FE = spacebar), `layer_has_midi_keys(cur_layer)` returns
false and `midiswitch_mode = true`.

In that mode:
- Pages 0..11 (= rows 1..6, the upper main page) are replaced with the
  word **`midiswitch`** rendered at 2x scale across rows 1..2 (it fits
  exactly: 10 chars × 24 px = 240 px).
- Chord row (pages 8..11) is suppressed.
- Keylog (pages 12..13) and BPM / Layer (pages 36..37) keep rendering.

`main_rc.layout_midiswitch` tracks the last computed state. When it
flips, `ms_changed` folds into the local `force` flag and re-renders
every gated block (Block 1, Block 2, chord, keylog, midiswitch text).

---

## 8. Theming (`luna_qp_colors.h`)

```
LUNA_TEXT_HUE   = 17    ← single anchor for the whole palette
LUNA_TEXT_SAT   = 255
LUNA_TEXT_VAL   = 255
LUNA_SHIFT      = 55    ← lighter / darker step magnitude
LUNA_LOOP_DROP  = 20    ← small S-drop for white-key LOOP press
```

Derived (white-key family pinned at `V = LUNA_TEXT_VAL`):

| Key | HSV |
|---|---|
| WHITE_IDLE | `(HUE, SAT - SHIFT, VAL)` |
| LIVE press | `(HUE + 128, WHITE_IDLE_S, WHITE_IDLE_V)` ← complement hue, same for white + black |
| LOOP press white | `(HUE, SAT - LOOP_DROP, VAL)` |
| LOOP press black | `(HUE, SAT, SHIFT * 2)` |

`OLED_TEXT_HUE` and `OLED_TEXT_SAT` in `orthomidi5x14.c` are bound to
`LUNA_TEXT_HUE` / `LUNA_TEXT_SAT` via `#include "luna_qp/luna_qp_colors.h"`
so the OLED-blit text colour follows the keyboard hue automatically.

**Changing `LUNA_TEXT_HUE` retheme both the font and the luna piano in
one edit.**

### LCD HSV → RGB

`drivers/painter/tft_panel/qp_tft_panel.c` uses `hsv_to_rgb_nocie_no_scale`
(in `quantum/color.c`) for the LCD palette converter. The default
`hsv_to_rgb_nocie` runs `apply_brightness_scaling` which knocks
`rgb_sum >= 250` down ~70 % to limit RGB-LED power; on the LCD that
would render bright colours as dim, cool-tinted greys. The no-scale
variant skips that step. RGB-LED paths still use the scaled version.

---

## 9. Dirty-flag gating (`main_rc`)

```c
typedef struct {
    bool init;                              // false = force-rerender every block
    uint8_t r0_mode;                        // 0 = Layer/BPM, 1 = mode_display
    uint8_t r0_layer;
    uint16_t r0_bpm;
    const char *r0_layer_name;
    const char *r0_msg;
    uint8_t r1_status; int16_t r1_v1..v3;   // transposition inputs (split mode)
    int8_t r1_d1..d3;
    int16_t r1_temp;
    uint8_t r2_status; uint8_t r2_c1..c3;   // channel inputs (split mode)
    uint8_t r3_status; uint8_t r3_c1..c3;   // curve inputs (also tracks cu for no-split)
    uint8_t r3_min, r3_max;                 // last vel min/max sent to OLED
    char r5_text[33];                       // last chord string painted
    char r7_copy[24];                       // last keylog string painted
    bool layout_any_split;                  // last computed any_split state
    uint8_t layout_cu;                      // cu used to fill def_min/def_max
    uint8_t layout_def_min, layout_def_max; // preset's default vmin/vmax
    bool layout_vel_edited;                 // last vel_edited state
    bool layout_midiswitch;                 // last computed midiswitch state
} main_render_cache_t;
```

Each block in `oled_render_keylog` compares its inputs against the
cache and only re-renders when something changed (or `force` is set).
This is the gating that keeps the SPI bus quiet when nothing is moving.

`oled_render_keylog_invalidate()` sets `init = false`, forcing a full
re-render on the next call. Called after every `oled_clear()` in
`oled_task_user` so the cache doesn't claim "no change" against an
empty buffer.

`ms_changed`, `cu_changed`, and `layout_changed` (= any-split flip)
are derived flags that get folded into the per-block `if (force || ...
|| flag)` conditions to invalidate Block 1 / Block 2 / chord / keylog
across layout transitions.

---

## 10. Footguns

### Footgun 1 — `.bss` not stack

The 1440-byte `buf6` and 480-byte `buf2` (and the 1920-byte ms_buf and
2880-byte bpmlayer_buf) **must** be `static`. The QMK main task stack
is small (~2-4 KB). A 1440-byte local will silently overflow on some
configurations and the firmware boots to a black screen with no
matrix activity. There is no soft-fault warning — the stack just
ends up under-water.

Forward declaration / definition mismatch: helpers defined low in the
file (`render_small_into_buf`, `render_big_into_buf`,
`draw_main_frame_qp_on_lcd`) need static forward declarations near
the top of the file, *above* every call site, or the compiler will
infer a non-static prototype at the call and conflict with the later
static definition.

### Footgun 2 — Order of writes vs OR-merge

`render_big_into_buf` and `render_small_into_buf` use plain assignment
(`buf[k] = byte`), not OR. So if you render text *after* OR-merging a
frame line, the text wipes the frame line in its columns. **Always
draw the dotted boxes (OR-merge) after the text, never before.**

### Footgun 3 — Chord big spans 2 user rows

`oled_write_big_centered(4, chord)` writes pages 8..11, which is **two**
user rows (5 and 6). When chord shrinks back to small text on row 5,
page 10-11 (row 6) still holds the previous big-bottom half pixels.
That's why there's an explicit `oled_clear_row(5)` to wipe row 6 when
not in big-chord mode.

### Footgun 4 — Forward declaration site matters

Forward declarations placed *below* a call site (anywhere in the file)
are useless — the compiler scans top-down and infers the implicit
prototype at the call site before it reaches the explicit declaration.
For something called from `lcd_painter_thread` (line ~474), the
declaration must live above the thread definition, not next to the
function body 7000 lines down.

### Footgun 5 — `layer_state` is for live layer

The active layer used by the MIDIswitch detection is
`get_highest_layer(layer_state | default_layer_state)`, not just
`layer_state`. The OR-with-`default_layer_state` matters when the
keyboard boots into a non-zero default layer.

### Footgun 6 — Loop pedal preserves the main page

Pre-current behaviour: the `else` branch in `oled_task_user` (loop
active) used to `memset` pages 8..11 and 12..15 to zero, blanking the
chord and keylog. That was leftover from when loop circles were
painted at the OLED Y range; circles now paint at LCD Y=128..191 (=
pages 16..23), so the OLED text area is safe to keep intact. The 8-track
text interface (`render_interface(0, 8)`) still intentionally overrides
rows 4..7 -- power-user mode.

---

## 11. Useful greps

```
# Find the main-page rendering
grep -n "void oled_render_keylog" orthomidi5x14.c

# Find the LCD render loop
grep -n "lcd_painter_thread" orthomidi5x14.c

# Locate the OLED-to-LCD blit
grep -n "lcd_blit_oled_chunk" orthomidi5x14.c

# Find where text colour is set
grep -n "OLED_TEXT_HUE\|OLED_TEXT_SAT" orthomidi5x14.c

# Find where luna piano is positioned
grep -n "LUNA_LCD_BASE_Y\|lcd_frame.luna_y" orthomidi5x14.c
```

---

## 12. Recap, in one sentence

The OLED buffer covers the **entire 240×320 LCD**, gets diff-blitted as
single-colour orange text at LCD Y=OLED Y, and is supplemented at
specific Y ranges by direct QP paints (luna piano always at 112..193;
feature boxes below it at 194..287; nothing else). Every row in the
layout is page-aligned, rendered through one of
three primitives (`render_small_into_buf`, `render_big_into_buf`, plain
`oled_write`), and gated by a small dirty-flag cache.

---

## 13. Painted feature boxes (`loop_circles_qp.c`)

The painted band is a **descriptor-driven, two-row grid of feature
boxes** — a generalization of the old fixed 4-track loop ring UI. The
file owns only painting + per-slot delta caching; it knows nothing about
*which* feature a box represents.

### Box geometry
| Constant | Value | Meaning |
|---|---|---|
| `LCQ_OUTER_HALF` | 25 | box is 51×51 px (≈50) |
| `LCQ_INNER_HALF` | 23 | 47×47 well → 2 px ring (thin border) |
| row centers | 226 (1-row) / 191,249 (2-row) | depend on full vs compact piano above |
| `LCQ_OUTER_CHAMFER` | 5 | 5 px corner cut (rounded look) |
| `LCQ_RING_CENTER_Y` / `LCQ_ROW2_CENTER_Y` | 217 / 264 | row centers (y 194..240 / 241..287) |
| `LCQ_BAND_TOP_Y` / `LCQ_BAND_BOTTOM_Y` | 194 / 287 | band fully below the fixed piano, above BPM |
| `LCQ_TRACK_PITCH_X` / `LCQ_FIRST_CENTER_X` | 60 / 30 | 4 columns: x=30/90/150/210 |
| `LCQ_BOX_MAX` | 8 | 2 rows × 4 |

### Data flow
1. `collect_feature_boxes()` (in `orthomidi5x14.c`) builds an `lcq_box_t[]`
   every painter frame in **priority order**:
   - **P1 loops with content** (`state != EMPTY`), track order — loop 1
     highest .. loop 4.
   - **P2 chord progressions** (voice order).
   - **P3 everything else** — SMARTCHORD, octave-doubler, SEQ / ARP /
     DynChord / Quick-chord / Fader / Delay — sorted by **when each was
     turned on** (oldest first; tracked via a small first-seen table).
2. `loop_circles_qp_render_boxes(boxes, count)` paints them compactly into
   slots `0..count-1` (row 0 then row 1). Each slot caches its last
   descriptor keyed by `feat_id`; a slot whose `feat_id` changes (or
   `>= count`) is blacked out and (re)painted. Heavy ring fills are
   rate-limited to `LCQ_FULL_PER_FRAME` (3) per call.

### Per-box content
- **Ring**: solid in a state/category colour; for **progressing** boxes
  (loops, SEQ, chord progressions) it *empties clockwise* per
  `progress_elapsed` (0..`LCQ_PROGRESS_STEPS`=90), refilling on wrap.
  Progress sources: loop `pos/len`; SEQ `current_position_16ths /
  pattern_length_16ths`; progression `chord_index / prog->length`
  **interpolated within the current chord** (via `next_chord_time` +
  `progression_compute_beat_offset`) so the sweep is smooth, not one
  jump per chord; **fader** = CC ramp (`dynamic_keymap_cc_ramp_progress`,
  slot 240+s) sweeping over its duration — Loop keeps looping, and a
  Reverse / Reverse-Loop fader sets the descriptor's `reverse_fill` so the
  ring *re-fills* (re-colors spokes) on the reverse leg instead of emptying.
- **Legend**: loops keep their digit / ▶ / ‖ / REC / DUB / SOLO symbols;
  every other feature uses `LCQ_BOX_LEGEND_LABEL` — a free-text label
  auto-wrapped to ≤2 lines of ≤6 chars in the 5×7 box font (case-sensitive:
  full lowercase a–z plus `J K Q V W Z / ( ) # >`). Category labels:
  melodic step sequencer → `SEQ1`; **factory drum machine → "Drums"**
  (`seq_state[].factory_seq_button >= 0`); **chord progression → "Chords" /
  "Arp" / "Bass" / "Lead"** by the voice's `rhythm_layer` (0/1/2; a future layer 3
  shows "Lead"); ARP/Fader/Delay → their `collect_active_features` label.

The whole luna+box region is only blacked + repainted (`region_reset`) when
the **piano** changes (full↔compact, i.e. crossing 4↔5 boxes, or hide) — NOT
when a box is merely added/removed within a row (those are per-slot, so a
fader press no longer flashes the screen). `loop_render` stays true one extra
frame after the last box leaves so `render_boxes(0)` can clear it.
- **Loop identity / mods**: a loop shows "Loop N" above its legend. With
  exactly one modification (transpose/channel/speed/…) the mod drops below
  the legend and "Loop N" stays on top; with two or more, the cycling mod
  pair takes both rows and "Loop N" is hidden until back to ≤1 mod.
- **Octave doubler**: each zone with `octave_doubler_mode != 0` gets its
  own box — "Octave" legend, the amount (`+1`/`+2`/`-1`) below, and a
  zone tag ("KSplit"/"TSplit") above for the split zones. This replaces
  the old `*` / `**` markers on the transpose number (now removed).
- **Modifiers**: held Shift / Ctrl / Alt (`get_mods()`) and Caps Lock
  (`host_keyboard_led_state().caps_lock`) each show a white box ("Shift" /
  "Ctrl" / "Alt" / "Caps") while active, vanishing on release.

### Liveness / removal (per-feature, not "sticky until all idle")
A box exists only while its feature is live: a loop while it has content
(stays when paused/muted, vanishes when cleared); SMARTCHORD while
`smartchordstatus` is set (updates in place when the chord changes);
SEQ/ARP/DynChord/Quick-chord/Fader/Delay/Progression while active
(removed on toggle-off, replaced in place when superseded).

### Layout / row-transition handling
`housekeeping_task_user` drives the layout from `feature_box_count()`:
1–4 boxes → one row, 5–8 → two rows. The piano **always** stays at
`LUNA_LCD_BASE_Y` (112) — it never shifts or hides for boxes (only for
menus / tab / 8-track). Because the band (194..287) sits entirely below
the piano and above the BPM strip, in a region the OLED blit never
writes, boxes can't punch holes into the piano and need no prev-cache or
luna juggling. Row GROW → `loop_invalidate` (full repaint); row SHRINK /
exit → `loop_clear` (black the band + reset slots). The two are mutually
exclusive (painter runs `clear` via `else-if`).
