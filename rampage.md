# RAM Usage Analysis — orthomidi5x14 Firmware

**MCU:** STM32F412 (256KB RAM total)
**Date:** 2026-03-22

---

## Summary

| Category | Bytes | % of 256KB |
|----------|------:|:----------:|
| Macro buffers (loop pedal) | 81,920 | 31.3% |
| ~~Transfer buffer (xfer_buffer)~~ | ~~40,960~~ | **ELIMINATED** |
| Streaming transfer structs (sser+sdes) | ~180 | 0.07% |
| Note pool (arp/seq/dynchord) | 24,576 | 9.4% |
| Per-key config caches | 7,560 | 2.9% |
| Key state arrays (matrix) | ~5,600 | 2.1% |
| Custom names cache | 2,672 | 1.0% |
| Delay system | ~2,176 | 0.8% |
| Keymap RAM cache | 1,680 | 0.6% |
| MIDI tracking (live/sustain) | ~480 | 0.2% |
| Sysex buffer | 1,024 | 0.4% |
| Arp/seq active presets | ~3,700 | 1.4% |
| Dynamic chord state | ~400 | 0.2% |
| LED/RGB/OLED caches | ~3,000 | 1.2% |
| MIDI/sustain key arrays | ~200 | 0.1% |
| Early overdub buffers | 1,024 | 0.4% |
| ChibiOS kernel + USB + stack | ~20,000+ | 7.8%+ |
| **Estimated firmware total** | **~197,000** | **~75%** |

---

## Detailed Breakdown

### 1. Macro System (Loop Pedal) — `process_dynamic_macro.c`

| Variable | Formula | Bytes |
|----------|---------|------:|
| `macro_buffer[]` | 4 macros x 20,480B = `TOTAL_BUFFER_SIZE` | 81,920 |
| `xfer_buffer[]` | `MACRO_BUFFER_SIZE * 2` = 20,480 x 2 | **40,960** |
| `macro_speed_factor[]` | 4 x float | 16 |
| `macro_manual_speed[]` | 4 x float | 16 |
| `macro_speed_before_pause[]` | 4 x float | 16 |
| `macro_playback[]` | 4 x `macro_playback_state_t` (large) | ~800 |
| `recording_suspended[]` | 4 x bool | 4 |
| `early_overdub_buffer[][]` | 4 x 32 x `midi_event_t`(8B) | 1,024 |
| `preroll_buffer[]` | 32 x `midi_event_t`(8B) | 256 |
| **Subtotal** | | **~125,000** |

#### `midi_event_t` (8 bytes)
```c
typedef struct {
    uint8_t type;          // note-on/off/CC
    uint8_t channel;
    uint8_t note;
    uint8_t raw_travel;    // 0-255
    uint32_t timestamp;    // ms
} midi_event_t;
```

#### `MACRO_BUFFER_SIZE` = 20,480 bytes per macro
- Each `midi_event_t` = 8 bytes → 2,560 events per macro
- 4 macros → 81,920 bytes total

---

### 2. Transfer Buffer Deep Dive — `xfer_buffer[]`

```c
static uint8_t xfer_buffer[MACRO_BUFFER_SIZE * 2];  // 40,960 bytes
```

**This is the single largest optimization target in the firmware.**

#### What It Does

The `xfer_buffer` serves three purposes (mutually exclusive via `xfer_buffer_mode_t`):

| Mode | Purpose | Max Data Size |
|------|---------|--------------|
| `XFER_SERIALIZING` | Serialize macro → send to GUI via HID | Up to 40KB (two 20KB macros: main + overdub) |
| `XFER_RECEIVING` | Accumulate HID chunks from GUI → deserialize into macro | Up to 40KB |
| `XFER_COPY_HELD` | Copy macro data locally (copy/paste between slots) | Up to 40KB |

#### How Serialization Works

```
serialize_macro_data(macro_num, xfer_buffer)
  → Header: 4 bytes (magic 0xAA55, version, macro_num)
  → Main events: 2-byte size + N * 8-byte midi_event_t
  → Overdub events: 2-byte size + N * 8-byte midi_event_t
  → Transform settings: 7 bytes (transpose, channel, velocity, etc.)
  → Timing: 8 bytes (loop_length, loop_gap)
  → BPM: 5 bytes (is_source, bpm u32)
  → Total: ~26 bytes overhead + (main_events + overdub_events) * 8
```

The **maximum serialized size** is bounded by `MACRO_BUFFER_SIZE * 2` because one macro has:
- Main buffer: up to 20,480 bytes (2,560 events x 8B)
- Overdub buffer: up to 20,480 bytes (shares space within the same 20KB macro slot, so actual max is less)
- Overhead: ~26 bytes

#### How HID Transfer Works

USB HID packets are only **32 bytes** (`VIAL_RAW_EPSIZE`). The firmware uses chunked transfer:

```
GUI → Firmware (LOAD):
  Packet 1: [CMD_LOAD_START, macro_num, total_packets, total_len]
  Packet 2..N: [CMD_LOAD_CHUNK, packet_idx, chunk_len, ...data(~22 bytes)...]
  Last: [CMD_LOAD_END]
  → Chunks accumulated into xfer_buffer until complete
  → Then deserialize_macro_data() processes the full buffer

Firmware → GUI (SAVE):
  serialize_macro_data() fills xfer_buffer
  send_hid_multi_packet_data() chunks it out:
    Start: [CMD_SAVE_START, total_packets, total_len]
    Chunks: [CMD_SAVE_CHUNK, packet_idx, chunk_len, ...data...]
    End: [CMD_SAVE_END]
```

---

### 3. Can We Reduce the Transfer Buffer?

#### Option A: Streaming Serialization (No Buffer)

**Save direction (firmware → GUI):** Instead of serializing the entire macro into `xfer_buffer` first, serialize directly into 32-byte HID packets:

```
// Current: serialize all → chunk and send
serialize_macro_data(macro_num, xfer_buffer);  // fills 40KB
send_hid_multi_packet_data(..., xfer_buffer, data_size);  // chunks out

// Proposed: streaming serializer
// Walk macro_buffer[] directly, format each event into HID packet
// No intermediate buffer needed
```

**This eliminates the xfer_buffer for SAVE entirely.** The serializer would track its position (event index + overdub index) and emit 2-3 events per HID packet directly from `macro_buffer[]`.

**Load direction (GUI → firmware):** Instead of accumulating all chunks into `xfer_buffer` then deserializing, deserialize incrementally as chunks arrive:

```
// Current: accumulate all → deserialize
memcpy(&xfer_buffer[pos], chunk, len);  // repeat for all packets
deserialize_macro_data(xfer_buffer, total_len, macro_num);  // processes 40KB

// Proposed: streaming deserializer
// Parse header from first packet
// Write events directly into macro_buffer[] as they arrive
// Track write position across packets
```

**Savings: 40,960 bytes (entire xfer_buffer eliminated)**

**Complexity:** Medium. The serialization format is simple (header + events + footer). A state machine tracking {phase, event_index, byte_offset} would work. The main challenge is the speed adjustment (timestamps are divided by `current_speed` during serialization) — but this can be done per-event as they're emitted.

#### Option B: Staggered Buffer (Smaller Window)

Use a smaller buffer (e.g., 2KB) as a sliding window:

```c
static uint8_t xfer_buffer[2048];  // 2KB instead of 40KB
```

**Save:** Serialize 2KB at a time, send that chunk, then serialize the next 2KB.
**Load:** Accumulate 2KB, deserialize that batch into `macro_buffer[]`, then receive the next 2KB.

**Savings: ~39,000 bytes**

**Complexity:** Low-medium. Requires the serializer/deserializer to be restartable (save/restore position between batches). The copy/paste (`XFER_COPY_HELD`) mode would need to serialize-then-deserialize instead of holding a raw copy.

#### Option C: Eliminate Copy/Paste Buffer

The `XFER_COPY_HELD` mode holds an entire serialized macro in RAM for local copy/paste. Instead:
- Copy: serialize directly from source `macro_buffer[src]` into destination `macro_buffer[dst]` with a `memcpy` + metadata copy
- No serialization needed for local copy since both sides are `midi_event_t[]`

This alone doesn't eliminate the buffer (still needed for HID transfer) but removes one use case.

#### Option D: Split Buffer (Recommended)

Separate the HID transfer from the copy/paste:

```c
#define XFER_CHUNK_SIZE 512   // Small window for HID streaming
static uint8_t xfer_chunk[XFER_CHUNK_SIZE];  // 512 bytes
// Copy/paste uses direct memcpy between macro_buffer[] slots
```

**Savings: ~40,400 bytes**

#### Verdict

| Approach | Savings | Complexity | Risk |
|----------|--------:|:----------:|:----:|
| **A: Streaming** | 40,960B | Medium | Low (format is simple) |
| **B: Staggered (2KB)** | ~39,000B | Low-medium | Low |
| **C: No copy buffer** | 0 (partial) | Low | None |
| **D: Split + stream** | ~40,400B | Medium | Low |

**Recommendation:** Option B (staggered 2KB) is the easiest win. The serialization format is linear — just events written sequentially — so batching 256 events at a time (256 x 8B = 2KB) is straightforward.

---

### 4. Key State Arrays — `matrix.c`

| Variable | Formula | Bytes |
|----------|---------|------:|
| `key_matrix[]` | 70 x `key_state_t` (~28B padded) | ~1,960 |
| `midi_key_states[]` | 70 x `midi_key_state_t` (~28B padded) | ~1,960 |
| `all_layer_per_key_cache[][]` | 12 layers x 70 keys x 6B (`per_key_config_lite_t`) | 5,040 |
| `key_type_cache_all[][]` | 12 x 70 x 1B | 840 |
| `dks_keycode_cache_all[][]` | 12 x 70 x 2B | 1,680 |
| `keymap_ram_cache[][][]` | 12 x 5 x 14 x 2B | 1,680 |
| EQ bands/scales | 15 + 3 + misc | ~25 |
| **Subtotal** | | **~13,185** |

#### `key_state_t` (~26 bytes, 28 padded)
```c
uint16_t adc_raw, adc_filtered, adc_rest_value, adc_bottom_out_value;  // 8B
uint32_t inv_range;                    // 4B
uint8_t distance, extremum;           // 2B
key_dir_t key_dir; bool is_pressed, calibrated;  // 3B
uint8_t base_velocity;                // 1B
uint16_t last_adc_value, stable_start_adc;  // 4B
uint32_t stable_time;                 // 4B
bool is_stable;                       // 1B → total ~27B
```

#### `midi_key_state_t` (~36 bytes)
```c
bool is_midi_key, pressed, was_pressed, note_active;  // 4B
uint8_t note_index, zone_type;         // 2B
uint8_t peak_travel; bool send_on_release, velocity_captured;  // 3B
uint8_t retrigger_distance, retrigger_extremum; bool retrigger_active;  // 3B
uint8_t last_travel; uint32_t press_start_time;  // 5B
uint8_t raw_velocity; uint16_t travel_time_ms; uint8_t final_velocity;  // 4B
uint8_t last_aftertouch, smoothed_aftertouch;  // 2B
uint16_t slew_last_time, slew_accum;  // 4B
uint8_t note_channel, midi_note;      // 2B
uint8_t vibrato_value; uint16_t vibrato_last_time;  // 3B
uint8_t vibrato_last_travel; uint16_t vibrato_decay_accum;  // 3B → ~35B
```

---

### 5. Note Pool (Arp/Seq/Dynchord) — `arpeggiator.c`

| Variable | Formula | Bytes |
|----------|---------|------:|
| `note_pool[]` | `NOTE_POOL_BYTE_SIZE` | 24,576 |
| `arp_pool_headers[]` | 4 x `pool_preset_t` (~12B) | 48 |
| `seq_pool_headers[]` | 8 x `pool_preset_t` (~12B) | 96 |
| `dynchord_pool_headers[]` | 4 x `pool_preset_t` (~12B) | 48 |
| `arp_notes[]` | 32 x `arp_note_t` (~16B) | 512 |
| `arp_state` | `arp_state_t` | ~48 |
| `seq_state[]` | 8 x `seq_state_t` (~32B) | ~256 |
| `arp_active_preset` | `arp_preset_t` (~200B) | ~200 |
| `seq_active_presets[]` | 8 x `seq_preset_t` (~392B) | ~3,136 |
| `step_scratch[]` | 16 x `unpacked_note_t` (~16B) | 256 |
| `quick_build_state` | `quick_build_state_t` (~200B) | ~200 |
| `live_note_sequence[]` | 32 x uint32_t | 128 |
| **Subtotal** | | **~29,504** |

---

### 6. MIDI Delay System — `midi_delay.c` / `midi_delay.h`

| Variable | Formula | Bytes |
|----------|---------|------:|
| `delay_system.user_configs[]` | 50 x `delay_slot_config_t` (16B) | 800 |
| `delay_system.runtime[]` | 98 x `delay_slot_runtime_t` (1B) | 98 |
| `delay_system.queue[]` | 64 x `delay_event_t` (16B) | 1,024 |
| `delay_sounding[]` | 32 x `delay_sounding_note_t` (6B) | 192 |
| `note_on_times[]` | 32 x `note_on_tracker_t` (~8B) | ~256 |
| **Subtotal** | | **~2,370** |

---

### 7. Dynamic Chord System — `dynamic_chord.c`

| Variable | Formula | Bytes |
|----------|---------|------:|
| `dynchord_state` | `dynamic_chord_state_t` | ~100 |
| `.phrases[4]` | 4 x `dynamic_chord_phrase_t` (~12B) | 48 |
| `.held_notes/channels[16]` | 16 + 16 | 32 |
| `.sounding_notes/channels[16]` | 16 + 16 | 32 |
| (Events stored in note_pool, not separate RAM) | | 0 |
| **Subtotal** | | **~212** |

---

### 8. MIDI Tracking — `process_midi.c`

| Variable | Formula | Bytes |
|----------|---------|------:|
| `live_notes[][3]` | 32 x 3 | 96 |
| `sustain_notes[][3]` | 64 x 3 | 192 |
| `sysex_buffer[]` | 1024 | 1,024 |
| **Subtotal** | | **~1,312** |

---

### 9. Custom Names — `custom_names.c`

| Variable | Formula | Bytes |
|----------|---------|------:|
| `cn_macro_names[][]` | 25 x 16 | 400 |
| `cn_arp_names[][]` | 40 x 16 | 640 |
| `cn_seq_names[][]` | 40 x 16 | 640 |
| `cn_delay_names[][]` | 50 x 16 | 800 |
| `cn_layer_names[][]` | 12 x 16 | 192 |
| **Subtotal** | | **2,672** |

---

### 10. LED/Display Caches — `orthomidi5x14.c`

| Variable | Formula | Bytes |
|----------|---------|------:|
| `layer_rgb_cache[][]` | 12 x 9 | 108 |
| `frozen_chord_leds[]` | 42 | 42 |
| `CCValue[]` | 128 | 128 |
| `tone_status` arrays | 6 x 2 x ~128 | ~1,536 |
| `nullbind_key_travel[]` | 70 | 70 |
| `mode3/4_positions[][]` | 2 x 72 x 6 | 864 |
| `toggle/delay_led_caches` | ~960 | ~960 |
| **Subtotal** | | **~3,708** |

---

## RAM Map (Sorted by Size)

| # | Allocation | Bytes | Reducible? |
|---|-----------|------:|:----------:|
| 1 | `macro_buffer[]` (4 loop macros) | 81,920 | Maybe (reduce per-macro size) |
| 2 | **`xfer_buffer[]`** (HID transfer) | **40,960** | **YES — see Section 3** |
| 3 | `note_pool[]` (arp/seq/dynchord) | 24,576 | Unlikely (shared pool) |
| 4 | `all_layer_per_key_cache[][]` | 5,040 | No (perf critical) |
| 5 | `seq_active_presets[]` (8 seq slots) | 3,136 | Maybe (lazy load) |
| 6 | Custom names cache | 2,672 | Maybe (lazy load from EEPROM) |
| 7 | `key_matrix[]` (70 keys) | ~1,960 | No (core scan loop) |
| 8 | `midi_key_states[]` (70 keys) | ~1,960 | No (core scan loop) |
| 9 | `dks_keycode_cache_all[][]` | 1,680 | No (perf critical) |
| 10 | `keymap_ram_cache[][][]` | 1,680 | No (perf critical) |
| 11 | Tone status arrays | ~1,536 | Maybe |
| 12 | `delay_system.queue[]` | 1,024 | Unlikely |
| 13 | `sysex_buffer[]` | 1,024 | Unlikely (MIDI standard) |
| 14 | `early_overdub_buffer[][]` | 1,024 | Maybe (reduce per-macro) |
| 15 | LED caches | ~960 | Maybe |
| 16 | `key_type_cache_all[][]` | 840 | No (perf critical) |
| 17 | `delay_system.user_configs[]` | 800 | No (runtime config) |

---

## Top 3 Optimization Opportunities

### 1. Eliminate `xfer_buffer[]` — Save 40,960 bytes

Use **streaming serialization** (Option A or B from Section 3):
- SAVE: Walk `macro_buffer[]` directly, emit events into HID packets without intermediate copy
- LOAD: Write events directly into `macro_buffer[]` as HID chunks arrive
- COPY/PASTE: Direct `memcpy` between `macro_buffer[]` slots (no serialization needed)

### 2. Reduce `MACRO_BUFFER_SIZE` — Save up to 40,960 bytes

Current: 20,480 bytes per macro (2,560 events). At 8 bytes/event and typical recording rates of ~10 events/second (note-on + note-off), this allows ~4.3 minutes per macro. If 2.1 minutes is sufficient:
- 10,240 bytes per macro → saves 40,960 bytes total (4 macros)

### 3. Lazy-load custom names — Save 2,672 bytes

Load names from EEPROM on-demand for OLED display instead of caching all 167 names in RAM. Only 1-2 names are displayed at a time.

---

## Transfer Buffer Recommendation

**The 40KB `xfer_buffer` is NOT needed at its current size.** The actual maximum data per transfer equals one macro's worth of events (~20KB worst case), and even that can be streamed without buffering.

**Minimum viable approach (staggered, 2KB window):**
```c
#define XFER_WINDOW_SIZE 2048
static uint8_t xfer_window[XFER_WINDOW_SIZE];  // Replaces 40KB buffer
```

This works because:
1. HID packets are only 32 bytes — data arrives/leaves in tiny chunks
2. The serialization format is linear (header → events → footer)
3. Events can be processed in batches of ~256 (2KB / 8B per event)
4. Copy/paste between macro slots can use direct `memcpy` (same struct layout)

**Net savings: ~39,000 bytes of RAM.**
