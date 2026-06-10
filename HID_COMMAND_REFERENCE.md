# HID Command Reference — orthomidi5x14 (PRODUCTION)

> Generated from code analysis of firmware and GUI sources. All byte positions verified against
> `via.c`, `vial.c`, `arpeggiator_hid.c`, `process_dynamic_macro.c`, and `keyboard_comm.py`.

---

## Table of Contents

1. [Packet Format](#1-packet-format)
2. [Routing Chain](#2-routing-chain)
3. [Path 1 — VIA Standard Commands (0x01–0x14)](#3-path-1--via-standard-commands)
4. [Path 2 — Vial Commands (0xFE prefix)](#4-path-2--vial-commands-0xfe-prefix)
5. [Path 3 — Custom HID Commands (0x7D/0x00/0x4D prefix)](#5-path-3--custom-hid-commands)
6. [Command ID Map (Complete)](#6-command-id-map)
7. [Dual-Path Commands (Same ID, Different Paths)](#7-dual-path-commands)

---

## 1. Packet Format

All HID packets are **32 bytes** (`VIAL_RAW_EPSIZE` / `HID_PACKET_SIZE`).

### Path 1 — VIA Standard (no prefix)
```
Byte 0:    Command ID (0x01–0x14)
Bytes 1-31: Command data (referred to as command_data[0-30] in via.c)
```

### Path 2 — Vial Prefix
```
Byte 0:    0xFE (CMD_VIA_VIAL_PREFIX)
Byte 1:    Vial command ID
Bytes 2-31: Payload (referred to as msg[2-31] in vial.c)
```

### Path 3 — Custom HID
```
Byte 0:    0x7D (HID_MANUFACTURER_ID)
Byte 1:    0x00 (HID_SUB_ID)
Byte 2:    0x4D (HID_DEVICE_ID)
Byte 3:    Command ID
Bytes 4-31: Payload
```

**Custom HID sub-path A (0xA0–0xBB):** Handled by `dynamic_macro_hid_receive()` in `process_dynamic_macro.c`
- Byte 4: macro_num / slot
- Byte 5: status (response only)
- Bytes 6-31: data payload (up to 26 bytes)

**Custom HID sub-path B (0xC0–0xFB):** Handled by `raw_hid_receive_kb()` in `arpeggiator_hid.c`
- Bytes 4-5: usually unused/reserved
- Bytes 6-31: data payload (up to 26 bytes)

---

## 2. Routing Chain

Entry point: `raw_hid_receive()` in `via.c` (line 210)

```
raw_hid_receive(data, length)
│
├─ data[0]==0x7D && data[1]==0x00 && data[2]==0x4D ?
│  ├─ cmd (data[3]) in 0xA0–0xBB → dynamic_macro_hid_receive(data, length)    [Path 3A]
│  ├─ cmd (data[3]) in 0xC0–0xFB → raw_hid_receive_kb(data, length)           [Path 3B]
│  └─ else → error response
│
├─ data[0]==0xFE ?
│  └─ vial_handle_cmd(data, length)                                             [Path 2]
│
└─ else: VIA standard switch on data[0]                                         [Path 1]
   ├─ 0x01: get protocol version
   ├─ 0x02: get keyboard value (sub-switch on data[1])
   ├─ 0x03: set keyboard value (sub-switch on data[1])
   ├─ 0x04: get keycode
   ├─ 0x05: set keycode
   ├─ 0x06: reset keymap
   ├─ 0x07: lighting set value
   ├─ 0x08: lighting get value
   ├─ 0x09: lighting save
   ├─ 0x0B: bootloader jump (requires vial_unlocked)
   ├─ 0x0C: macro get count
   ├─ 0x0D: macro get buffer size
   ├─ 0x0E: macro get buffer
   ├─ 0x0F: macro set buffer (requires vial_unlocked)
   ├─ 0x10: macro reset
   ├─ 0x11: get layer count
   ├─ 0x12: keymap get buffer
   ├─ 0x13: keymap set buffer
   └─ default → raw_hid_receive_kb(data, length)
```

**Response behavior:**
- Path 1: via.c modifies data[] in-place, then calls `raw_hid_send(data, length)` at end of function
- Path 2: vial.c modifies msg[] in-place, response sent by caller (via.c) after `vial_handle_cmd()` returns
- Path 3A: `dynamic_macro_hid_receive` sends its own response via `send_hid_response()`, returns before via.c sends
- Path 3B: `raw_hid_receive_kb` sends its own response via `raw_hid_send()`, returns before via.c sends

---

## 3. Path 1 — VIA Standard Commands

File: `via.c` lines 297–532

### 0x01 — Get Protocol Version
```
GUI sends:   [0x01]
FW returns:  [0x01] [version_hi] [version_lo]
```
GUI method: `reload_via_protocol()` (retries=20)

### 0x02 — Get Keyboard Value
```
GUI sends:   [0x02] [value_id] ...
FW returns:  varies by value_id
```

| Sub-ID | Name | Request | Response |
|--------|------|---------|----------|
| 0x00 | id_uptime | `[0x02, 0x00]` | `[0x02, 0x00, time_b3, time_b2, time_b1, time_b0]` (32-bit BE) |
| 0x02 | id_switch_matrix_state | `[0x02, 0x02]` | `[0x02, 0x02, row0_bytes..., row1_bytes..., ...]` (requires vial_unlocked) |
| 0x04 | id_layout_options | `[0x02, 0x04]` | `[0x02, 0x04, opts_b3, opts_b2, opts_b1, opts_b0]` (32-bit BE) |
| other | | | Forwarded to `raw_hid_receive_kb()` |

GUI method: `matrix_poll()` uses `[0x02, 0x03]` for VIA_SWITCH_MATRIX_STATE (retries=3)

### 0x03 — Set Keyboard Value
```
GUI sends:   [0x03] [value_id] [data...]
FW returns:  [0x03] [value_id] [echo data]
```

| Sub-ID | Name | Request |
|--------|------|---------|
| 0x04 | id_layout_options | `[0x03, 0x04, opts_b3, opts_b2, opts_b1, opts_b0]` (32-bit BE) |
| other | | Forwarded to `raw_hid_receive_kb()` |

### 0x04 — Get Keycode
```
GUI sends:   [0x04, layer, row, col]
FW returns:  [0x04, layer, row, col, keycode_hi, keycode_lo]
```
GUI method: Part of `reload_keymap()` (retries=20)

### 0x05 — Set Keycode
```
GUI sends:   [0x05, layer, row, col, keycode_hi, keycode_lo]
FW returns:  [0x05, layer, row, col, keycode_hi, keycode_lo]
```
GUI method: `set_key()` (retries=20)

### 0x06 — Reset Keymap
```
GUI sends:   [0x06]
FW returns:  [0x06]
```
Calls `dynamic_keymap_reset()`

### 0x07 — Lighting Set Value
```
GUI sends:   [0x07, light_sub_id, value_data...]
```
Dispatches to active lighting backend. For this keyboard (VIALRGB_ENABLE):
- Calls `vialrgb_set_value(data, length)`

| Sub-ID | Name | Format | GUI Method |
|--------|------|--------|------------|
| 0x41 | VIALRGB_SET_MODE | `[0x07, 0x41, mode_lo, mode_hi, speed, h, s, v]` | `_vialrgb_set_mode()` |

### 0x08 — Lighting Get Value
```
GUI sends:   [0x08, light_sub_id]
```

| Sub-ID | Name | Response |
|--------|------|----------|
| 0x40 | VIALRGB_GET_INFO | `[0x08, 0x40, version, max_brightness_lo, max_brightness_hi, num_leds_lo, num_leds_hi]` |
| 0x41 | VIALRGB_GET_MODE | `[0x08, 0x41, mode_lo, mode_hi, speed, h, s, v]` |
| 0x42 | VIALRGB_GET_SUPPORTED | `[0x08, 0x42, effect_lo, effect_hi, supported_flag]` (per-effect query) |

GUI method: `reload_persistent_rgb()` / `reload_rgb()` (retries=20)

### 0x09 — Lighting Save
```
GUI sends:   [0x09]
FW returns:  [0x09]
```
Persists RGB settings to EEPROM. GUI method: `save_rgb()` (retries=20)

### 0x0B — Bootloader Jump
```
GUI sends:   [0x0B]
```
Requires `vial_unlocked`. Sends response, waits 100ms, then jumps to bootloader.

### 0x0C — Macro Get Count
```
GUI sends:   [0x0C]
FW returns:  [0x0C, count]
```

### 0x0D — Macro Get Buffer Size
```
GUI sends:   [0x0D]
FW returns:  [0x0D, size_hi, size_lo]
```

### 0x0E — Macro Get Buffer
```
GUI sends:   [0x0E, offset_hi, offset_lo, size]     (size <= 28)
FW returns:  [0x0E, offset_hi, offset_lo, size, data[0..27]]
```

### 0x0F — Macro Set Buffer
```
GUI sends:   [0x0F, offset_hi, offset_lo, size, data[0..27]]    (requires vial_unlocked)
FW returns:  [0x0F, offset_hi, offset_lo, size, data echo]
```

### 0x10 — Macro Reset
```
GUI sends:   [0x10]
FW returns:  [0x10]
```

### 0x11 — Get Layer Count
```
GUI sends:   [0x11]
FW returns:  [0x11, layer_count]
```
GUI method: `reload_layers()` (retries=20)

### 0x12 — Keymap Get Buffer
```
GUI sends:   [0x12, offset_hi, offset_lo, size]     (size <= 28)
FW returns:  [0x12, offset_hi, offset_lo, size, data[0..27]]
```

### 0x13 — Keymap Set Buffer
```
GUI sends:   [0x13, offset_hi, offset_lo, size, data[0..27]]
FW returns:  [0x13, offset_hi, offset_lo, size, data echo]
```

---

## 4. Path 2 — Vial Commands (0xFE prefix)

File: `vial.c`, `vial_handle_cmd()` (line 151)

All packets: `msg[0] = 0xFE`, `msg[1] = command`, switch on `msg[1]`.

### Standard Vial Protocol

#### 0x00 — Get Keyboard ID
```
GUI sends:   [0xFE, 0x00]
FW returns:  [protocol_v0, protocol_v1, protocol_v2, protocol_v3,
              uid0, uid1, uid2, uid3, uid4, uid5, uid6, uid7,
              vialrgb_flag]
```
- `msg[0-3]`: Protocol version (32-bit LE)
- `msg[4-11]`: 8-byte keyboard UID
- `msg[12]`: VialRGB enabled (1=yes, 0=no)

GUI method: `reload_layout()` (retries=20)

#### 0x01 — Get Definition Size
```
GUI sends:   [0xFE, 0x01]
FW returns:  [size_b0, size_b1, size_b2, size_b3]    (32-bit LE)
```

#### 0x02 — Get Definition Block
```
GUI sends:   [0xFE, 0x02, page_lo, page_hi]
FW returns:  [32 bytes of LZMA-compressed keyboard definition]
```
Page = block index. Each block is 32 bytes. GUI reads all blocks to reconstruct full definition.

GUI method: `reload_layout()` block loop (retries=20)

#### 0x03 — Get Encoder (ENCODER_MAP_ENABLE)
```
GUI sends:   [0xFE, 0x03, layer, encoder_idx]
FW returns:  [kc1_hi, kc1_lo, kc2_hi, kc2_lo]    (big-endian keycodes)
```
Returns both CW and CCW keycodes for the encoder.

#### 0x04 — Set Encoder (ENCODER_MAP_ENABLE)
```
GUI sends:   [0xFE, 0x04, layer, encoder_idx, direction, kc_hi, kc_lo]
```
GUI method: `set_encoder()` (retries=20)

#### 0x05 — Get Unlock Status
```
GUI sends:   [0xFE, 0x05]
FW returns:  [unlocked, in_progress, row0, col0, row1, col1, ...]
```
- `msg[0]`: 1=unlocked, 0=locked
- `msg[1]`: 1=unlock in progress
- `msg[2+]`: Unlock combo key positions (row, col pairs)

#### 0x06 — Unlock Start
```
GUI sends:   [0xFE, 0x06]
```
Begins unlock sequence. Sets `vial_unlock_counter = VIAL_UNLOCK_COUNTER_MAX`.

#### 0x07 — Unlock Poll
```
GUI sends:   [0xFE, 0x07]
FW returns:  [unlocked, in_progress, counter]
```

#### 0x08 — Lock
```
GUI sends:   [0xFE, 0x08]
```

#### 0x09 — QMK Settings Query
```
GUI sends:   [0xFE, 0x09, qsid_lo, qsid_hi]
FW returns:  [settings query result]
```
Returns settings with QSID greater than the threshold.

#### 0x0A — QMK Settings Get
```
GUI sends:   [0xFE, 0x0A, qsid_lo, qsid_hi]
FW returns:  [status, value_data...]
```

#### 0x0B — QMK Settings Set
```
GUI sends:   [0xFE, 0x0B, qsid_lo, qsid_hi, value_data...]
FW returns:  [status]
```

#### 0x0C — QMK Settings Reset
```
GUI sends:   [0xFE, 0x0C]
```

#### 0x0D — Dynamic Entry Operations
```
GUI sends:   [0xFE, 0x0D, sub_op, ...]
```

| Sub-op | Name | Request | Response |
|--------|------|---------|----------|
| 0x00 | get_number_of_entries | `[0xFE, 0x0D, 0x00]` | `[tap_dance_count, combo_count, key_override_count]` |
| 0x01 | tap_dance_get | `[0xFE, 0x0D, 0x01, idx]` | `[status, td_entry_struct...]` |
| 0x02 | tap_dance_set | `[0xFE, 0x0D, 0x02, idx, td_entry_struct...]` | `[status]` |
| 0x03 | combo_get | `[0xFE, 0x0D, 0x03, idx]` | `[status, combo_entry_struct...]` |
| 0x04 | combo_set | `[0xFE, 0x0D, 0x04, idx, combo_entry_struct...]` | `[status]` |
| 0x05 | key_override_get | `[0xFE, 0x0D, 0x05, idx]` | `[status, ko_entry_struct...]` |
| 0x06 | key_override_set | `[0xFE, 0x0D, 0x06, idx, ko_entry_struct...]` | `[status]` |

### Layer RGB (0xBC–0xBF)

#### 0xBC — Layer RGB Save
```
GUI sends:   [0xFE, 0xBC, layer]
FW returns:  msg[0] = 0x01 (success) / 0x00 (error)
```
Saves current RGB settings to EEPROM for specified layer.

#### 0xBD — Layer RGB Load
```
GUI sends:   [0xFE, 0xBD, layer]
FW returns:  msg[0] = 0x01 / 0x00
```
Applies stored RGB settings for specified layer.

#### 0xBE — Layer RGB Enable
```
GUI sends:   [0xFE, 0xBE, enabled]    (0=disable, 1=enable)
FW returns:  msg[0] = 0x01
```

#### 0xBF — Layer RGB Get Status
```
GUI sends:   [0xFE, 0xBF]
FW returns:  msg[0] = enabled (0/1), msg[1] = NUM_LAYERS
```

### Custom Animation (0xC0–0xC9)

#### 0xC0 — Set Animation Parameter
```
GUI sends:   [0xFE, 0xC0, slot, param_id, value]
FW returns:  msg[0] = 0x01 / 0x00
```

| param_id | Name | Range |
|----------|------|-------|
| 0 | live_positioning | enum |
| 1 | macro_positioning | enum |
| 2 | live_animation | enum |
| 3 | macro_animation | enum |
| 4 | use_influence | bool |
| 5 | background_mode | enum |
| 6 | pulse_mode | 0-255 |
| 7 | color_type | enum |
| 8 | enabled | bool |
| 9 | background_brightness | 0-255 |
| 10 | live_speed | 0-255 |
| 11 | macro_speed | 0-255 |

#### 0xC1 — Get Animation Parameter
```
GUI sends:   [0xFE, 0xC1, slot, param_id]
FW returns:  msg[0] = 0x01, msg[4] = value
```

#### 0xC2 — Set All Animation Parameters
```
GUI sends:   [0xFE, 0xC2, slot, p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11]
FW returns:  msg[0] = 0x01
```
`msg[3-14]`: 12 parameter bytes (same order as param_id table above)

#### 0xC3 — Get All Animation Parameters
```
GUI sends:   [0xFE, 0xC3, slot, source]    (source: 0=RAM, 1=EEPROM)
FW returns:  msg[0] = 0x01, msg[3-14] = 12 parameter bytes
```

#### 0xC4 — Save Custom Animations
```
GUI sends:   [0xFE, 0xC4]
FW returns:  msg[0] = 0x01
```
Saves all animation slots to EEPROM.

#### 0xC5 — Load Custom Animations
```
GUI sends:   [0xFE, 0xC5]
FW returns:  msg[0] = 0x01
```

#### 0xC6 — Reset Custom Slot
```
GUI sends:   [0xFE, 0xC6, slot]
FW returns:  msg[0] = 0x01
```
Resets slot to defaults and saves to EEPROM.

#### 0xC7 — Get Custom Animation Status
```
GUI sends:   [0xFE, 0xC7]
FW returns:
  msg[0]  = 0x01 (success)
  msg[1]  = NUM_CUSTOM_SLOTS (50)
  msg[2]  = current_custom_slot
  msg[3-9]  = 7 bytes of enabled flags (1 bit per slot, LSB first)
  msg[10] = NUM_CUSTOM_PARAMETERS (12)
```

#### 0xC8 — Rescan LED Positions (EEPROM-based, slow)
```
GUI sends:   [0xFE, 0xC8]
FW returns:  msg[0] = 0x01
```
Calls `scan_keycode_categories()` + `scan_current_layer_midi_leds()`.
**WARNING:** Triggers slow I2C EEPROM reads (~250-750ms blocking). Use 0xE9 RAM-based rescan instead.

#### 0xC9 — Get Custom Animation RAM State
```
GUI sends:   [0xFE, 0xC9, slot]
FW returns:  msg[0] = 0x01, msg[3-14] = 12 parameter bytes from RAM
```

### Per-Key RGB (0xD3–0xD8)

**NOTE:** These command IDs overlap with Custom HID path commands (0xD3=velocity poll, 0xD4=velocity time, 0xD5=calibration debug). They are separate because they use the 0xFE prefix path.

#### 0xD3 — Get Palette Colors
```
GUI sends:   [0xFE, 0xD3, offset, count]    (count max 10)
FW returns:  msg[0] = 0x01, msg[1+] = HSV data (3 bytes per color: H, S, V)
```

#### 0xD4 — Set Palette Color
```
GUI sends:   [0xFE, 0xD4, palette_idx, h, s, v]
FW returns:  msg[0] = 0x01 / 0x00
```

#### 0xD5 — Get Preset Data
```
GUI sends:   [0xFE, 0xD5, preset, offset, count]    (count max 31)
FW returns:  msg[0] = 0x01, msg[1+] = LED preset data
```

#### 0xD6 — Set LED Color
```
GUI sends:   [0xFE, 0xD6, preset, led_idx, palette_idx]
FW returns:  msg[0] = 0x01 / 0x00
```

#### 0xD7 — Save Per-Key RGB
```
GUI sends:   [0xFE, 0xD7]
FW returns:  msg[0] = 0x01
```

#### 0xD8 — Load Per-Key RGB
```
GUI sends:   [0xFE, 0xD8, reset_flag]    (0xFF = force reset to defaults, else normal load)
FW returns:  msg[0] = 0x01
```

### Vial Path — Per-Key Actuation (0xE0–0xE6)

These are ALSO handled on the Vial path in `vial_handle_cmd()`. The GUI primarily uses the Custom HID path (see Section 5), but these handlers exist as an alternate access path.

#### 0xE0 — Set Per-Key Actuation (Vial path)
```
msg[2]:  layer
msg[3]:  key_index (0-69)
msg[4]:  actuation (0-255)
msg[5]:  deadzone_top (0-51)
msg[6]:  deadzone_bottom (0-51)
msg[7]:  velocity_curve (0-16)
msg[8]:  flags (bit 0=RT, bit 1=per-key velocity, bit 2=continuous RT)
msg[9]:  rapidfire_press_sens (0-100)
msg[10]: rapidfire_release_sens (0-100)
msg[11]: rapidfire_velocity_mod (-64 to +64, signed)
```

#### 0xE1 — Get Per-Key Actuation (Vial path)
```
Request:  msg[2]=layer, msg[3]=key_index
Response: msg[0]=0x01, msg[1-8]=8 config bytes
```

#### 0xE3 — Reset Per-Key Actuations (Vial path)
```
Response: msg[0] = 0x01
```

#### 0xE6 — Copy Layer Actuations (Vial path)
```
msg[2]: source_layer, msg[3]: dest_layer
Response: msg[0] = 0x01
```

### Vial Path — Keyboard Param Single (0xE8)
```
GUI sends:   [0xFE, 0xE8, param_id, value_lo, value_hi]
FW returns:  msg[0]=status, msg[1]=param_id, msg[2]=value_echo
```
16-bit params use `value_lo | (value_hi << 8)` (little-endian).

See Section 5 (0xE8) for full parameter ID table — both paths use the same handler.

### Vial Path — Keymap RAM Rescan (0xE9)

**NEW** — Replaces slow EEPROM-based rescan (0xC8) for keymap change scenarios.

#### Sub-command 0x00 — Receive Keymap Chunk
```
GUI sends:   [0xFE, 0xE9, 0x00, chunk_index, keycode_data[28]]
FW returns:  msg[0] = 0x01 (success) / 0x00 (error)
```
- `chunk_index`: 0 to `(12 * MATRIX_ROWS - 1)` = 0-71
  - `chunk_index = layer * MATRIX_ROWS + row`
- `msg[4-31]`: 28 bytes = 14 keycodes x 2 bytes each (big-endian per keycode)

#### Sub-command 0x01 — Trigger Rescan
```
GUI sends:   [0xFE, 0xE9, 0x01]
FW returns:  msg[0] = 0x01
```
Calls `rescan_from_ram()` which:
1. Sets `keymap_ram_valid = true`
2. Calls `scan_keycode_categories()`
3. Calls `scan_current_layer_midi_leds()`
4. Sets `keymap_ram_valid = false`

GUI method: `send_keymap_for_ram_rescan()` — sends 72 chunks then triggers rescan (retries=5)

### Vial Path — Gaming (0xCE–0xD2)

These are also in `vial_handle_cmd()`. Note byte positions differ from Custom HID path (data starts at msg[2] vs data[6]).

#### 0xCE — Set Gaming Mode
```
msg[2]: enabled (0/1)
Response: msg[0] = 0x01
```

#### 0xCF — Set Gaming Key Map
```
msg[2]: control_id (0-25), msg[3]: row, msg[4]: col, msg[5]: enabled
Response: msg[0] = 0x01
```

#### 0xD0 — Set Gaming Analog Config
```
msg[2]: ls_min, msg[3]: ls_max, msg[4]: rs_min, msg[5]: rs_max, msg[6]: trig_min, msg[7]: trig_max
Response: msg[0] = 0x01
```

#### 0xD1 — Get Gaming Settings
```
Response: msg[0]=0x01, msg[6]=mode, msg[7-12]=analog config (ls_min, ls_max, rs_min, rs_max, trig_min, trig_max)
```

#### 0xD2 — Reset Gaming Settings
```
Response: msg[0] = 0x01
```

### Vial Path — User Curves (0xD9–0xDE)

#### 0xD9 — Set User Curve
```
msg[2]: slot (0-9), msg[3-10]: 8 point bytes (4 control points), msg[11-26]: 16-char name
Response: msg[0] = 0x01
```

#### 0xDA — Get User Curve
```
msg[2]: slot (0-9)
Response: msg[0]=0x01, msg[1]=slot, msg[2-9]=8 point bytes, msg[10-25]=16-char name
```

#### 0xDB — Get All Curve Names
```
Response: msg[0]=0x01, msg[1-100]=10 names (10 chars each)
```
**NOTE:** Only 31 bytes available in 32-byte packet, so names are truncated.

#### 0xDC — Reset User Curves
```
Response: msg[0] = 0x01
```

#### 0xDD — Set Gaming Response
```
msg[2]: angle_adj_enabled, msg[3]: diagonal_angle, msg[4]: square_output,
msg[5]: snappy_joystick, msg[6]: curve_index (0-16)
Response: msg[0] = 0x01
```

#### 0xDE — Get Gaming Response
```
Response: msg[0]=0x01, msg[1]=angle_adj, msg[2]=diagonal_angle, msg[3]=square_output,
          msg[4]=snappy_joystick, msg[5]=curve_index
```

### Deprecated Vial Commands

| ID | Name | Status |
|----|------|--------|
| 0xCA | Layer Actuation Set | Dead code — intercepted by arpeggiator path |
| 0xCB | Layer Actuation Get | Dead code |
| 0xCC | Layer Actuation Get All | Dead code |
| 0xCD | Layer Actuation Reset | Active (calls `handle_reset_layer_actuations()`) |
| 0xE4 | Set Per-Key Mode | No-op (always per-key per-layer now) |
| 0xE5 | Get Per-Key Mode | Returns [1, 1] always |

---

## 5. Path 3 — Custom HID Commands

All commands use header: `[0x7D, 0x00, 0x4D, cmd_id, ...]`

### 5A. Dynamic Macro / ThruLoop / Keyboard Config (0xA0–0xBB)

File: `process_dynamic_macro.c`, `dynamic_macro_hid_receive()` (line 12079)

Response format: `send_hid_response(command, macro_num, status, data, data_len)`
```
Response: [0x7D, 0x00, 0x4D, command, macro_num, status, data[0..25]]
```
`status`: 0=success, 1=error

#### Macro Save/Load (0xA0–0xA6)

Multi-packet protocol for macro data transfer.

| CMD | Name | Input | Notes |
|-----|------|-------|-------|
| 0xA0 | SAVE_START | `[hdr, 0xA0, macro_num, status, -, -, expected_packets_lo, expected_packets_hi]` | Initiates save from FW to GUI |
| 0xA1 | SAVE_CHUNK | `[hdr, 0xA1, macro_num, -, -, -, chunk_data[22]]` | Chunked macro data (22 bytes/chunk) |
| 0xA2 | SAVE_END | `[hdr, 0xA2, macro_num]` | End of save |
| 0xA3 | LOAD_START | `[hdr, 0xA3, macro_num, -, -, -, expected_packets_lo, expected_packets_hi]` | Begin multi-packet load to FW |
| 0xA4 | LOAD_CHUNK | `[hdr, 0xA4, macro_num, -, -, -, -, -, chunk_len_lo, chunk_len_hi, chunk_data[22]]` | Receive chunk |
| 0xA5 | LOAD_END | `[hdr, 0xA5, macro_num]` | Finalize load + deserialize |
| 0xA6 | LOAD_OVERDUB_START | Same as 0xA3 | Load overdub layer only |

#### Macro Utility (0xA7–0xA9)

| CMD | Name | Input | Response |
|-----|------|-------|----------|
| 0xA7 | CLEAR_ALL_LOOPS | `[hdr, 0xA7]` | ACK (status=0) |
| 0xA8 | REQUEST_SAVE | `[hdr, 0xA8, macro_num]` | Triggers multi-packet save sequence |
| 0xA9 | TRIGGER_SAVE_ALL | `[hdr, 0xA9]` | Saves all 4 macros sequentially |

#### DKS — Dynamic Key Splitting (0xAA–0xAF)

| CMD | Name | Input | Response |
|-----|------|-------|----------|
| 0xAA | DKS_GET_SLOT | `data[6]=slot_num` | 32-byte `dks_slot_t` structure |
| 0xAB | DKS_SET_ACTION | `data[6]=slot, data[7]=is_press, data[8]=action_idx, data[9-10]=keycode(LE), data[11]=actuation, data[12]=behavior` | ACK |
| 0xAC | DKS_SAVE_EEPROM | (none) | ACK |
| 0xAD | DKS_LOAD_EEPROM | (none) | ACK (status=0 success, 1 error) |
| 0xAE | DKS_RESET_SLOT | `data[6]=slot_num` | ACK |
| 0xAF | DKS_RESET_ALL | (none) | ACK + saves to EEPROM |

#### ThruLoop Configuration (0xB0–0xB5)

| CMD | Name | Min Length | Data (starting at data[6]) | Response |
|-----|------|-----------|---------------------------|----------|
| 0xB0 | SET_LOOP_CONFIG | 13 | channel(1), sync(1), alt_restart(1), restart_cc[4] | ACK |
| 0xB1 | SET_MAIN_LOOP_CCS | 26 | 20 bytes: 5 CC arrays × 4 macros each (start_rec, stop_rec, start_play, stop_play, clear) | ACK |
| 0xB2 | SET_OVERDUB_CCS | 30 | 24 bytes: 6 CC arrays × 4 macros each (start_rec, stop_rec, start_play, stop_play, clear, restart) | ACK |
| 0xB3 | SET_NAVIGATION_CONFIG | 16 | use_master_cc(1), master_cc(1), nav_ccs[8] (per 1/8th position) | ACK |
| 0xB4 | GET_ALL_CONFIG | 7 | macro_num(1) | **4 response packets** with 5ms delay between them |
| 0xB5 | RESET_LOOP_CONFIG | 7 | (none) | ACK |

**GET_ALL_CONFIG response (4 packets):**
1. Packet with cmd=0xB0: loop config (7 bytes)
2. Packet with cmd=0xB1: main loop CCs (20 bytes)
3. Packet with cmd=0xB2: overdub CCs (24 bytes)
4. Packet with cmd=0xB3: navigation config (10 bytes)

#### Keyboard Configuration (0xB6–0xBB)

**Two-packet protocol:** Basic config (0xB6) + Advanced config (0xBB) must be sent as a pair for slot saves.

##### 0xB6 — Set Keyboard Config (Basic, Packet 1)
```
data[6-9]:   velocity_sensitivity (int32, LE)
data[10-13]: cc_sensitivity (int32, LE)
data[14]:    channel_number (0-15)
data[15]:    transpose_number (signed)
data[16]:    octave_number (signed)
data[17]:    transpose_number2
data[18]:    octave_number2
data[19]:    transpose_number3
data[20]:    octave_number3
data[21]:    dynamic_range (0-127)
data[22-25]: oledkeyboard (int32, LE)
data[26]:    overdub_advanced_mode (bool)
data[27]:    smartchordlightmode
```
Min packet length: 28

##### 0xBB — Set Keyboard Config (Advanced, Packet 2)
```
data[6]:  keysplitchannel
data[7]:  keysplit2channel
data[8]:  keysplitstatus (0=disabled, 1=enabled)
data[9]:  keysplittransposestatus
data[10]: keysplitvelocitystatus
data[11]: custom_layer_animations_enabled (bool)
data[12]: unsynced_mode_active
data[13]: sample_mode_active (bool)
data[14]: loop_messaging_enabled (bool)
data[15]: colorblindmode
data[16]: cclooprecording (bool)
data[17]: truesustain (bool)
data[18]: channeloverride (bool)
data[19]: velocityoverride (bool)
data[20]: transposeoverride (bool)
data[21]: midi_in_mode (enum)
data[22]: usb_midi_mode (enum)
data[23]: midi_clock_source (enum)
data[24]: macro_override_live_notes (bool)
data[25]: smartchord_mode (0=Hold, 1=Toggle)
data[26]: base_smartchord_ignore
data[27]: keysplit_smartchord_ignore
data[28]: triplesplit_smartchord_ignore
```
Min packet length: 29. If `pending_slot_save != 255`: saves to slot on receipt of this packet.

##### 0xB7 — Get Keyboard Config
```
data[6-31]: unused
Response: 2 packets (5ms delay between):
  Packet 1 (cmd=0xB6): Basic config (22 bytes at data[6+])
  Packet 2 (cmd=0xBB): Advanced config (23 bytes at data[6+])
```

##### 0xB8 — Reset Keyboard Config
```
Response: ACK
```
Resets all global MIDI settings to factory defaults.

##### 0xB9 — Save Keyboard Slot
```
data[6]:    slot (0-4)
data[7-28]: basic config (same as 0xB6)
```
Sets `pending_slot_save = slot`. **Waits for 0xBB packet** to complete the save.

##### 0xBA — Load Keyboard Slot
```
data[6]: slot (0-4)
Response: 2 packets (same format as 0xB7 GET)
```

### 5B. Keyboard-Level Handlers (0xC0–0xFB)

File: `arpeggiator_hid.c`, `raw_hid_receive_kb()` (line 545)

All responses sent via `raw_hid_send()`. Data payload starts at `data[6]` (bytes 4-5 usually reserved).
Status byte at `data[5]`: 0x00=success, 0x01=error.

#### Arpeggiator (0xC0–0xCC)

All forwarded to `arp_hid_receive(data, length)`.

| CMD | Name |
|-----|------|
| 0xC0 | ARP_CMD_GET_PRESET |
| 0xC1 | ARP_CMD_SET_PRESET |
| 0xC2 | ARP_CMD_SAVE_PRESET |
| 0xC3 | ARP_CMD_LOAD_PRESET |
| 0xC4 | ARP_CMD_CLEAR_PRESET |
| 0xC5 | ARP_CMD_COPY_PRESET |
| 0xC6 | ARP_CMD_RESET_ALL |
| 0xC7 | ARP_CMD_GET_STATE |
| 0xC8 | ARP_CMD_SET_STATE |
| 0xC9 | ARP_CMD_GET_INFO |
| 0xCA | ARP_CMD_SET_NOTE |
| 0xCB | ARP_CMD_SET_NOTES_CHUNK |
| 0xCC | ARP_CMD_SET_MODE |

#### Gaming/Joystick (0xCE–0xD2)

##### 0xCE — Set Gaming Mode
```
data[6]: enabled (0 or 1)
Response: data[5]=0x00 (success) or 0x01 (no JOYSTICK_ENABLE)
```

##### 0xCF — Set Gaming Key Map
```
data[6]:  control_id (0-25: 0-3=LS, 4-7=RS, 8-9=triggers, 10-25=buttons)
data[7]:  row (0-4)
data[8]:  col (0-13)
data[9]:  enabled (0/1)
Response: data[5]=0x00
```

##### 0xD0 — Set Gaming Analog Config
```
data[6]:  LS min travel (mm × 10)
data[7]:  LS max travel (mm × 10)
data[8]:  RS min travel
data[9]:  RS max travel
data[10]: trigger min travel
data[11]: trigger max travel
Response: data[5]=0x00
```

##### 0xD1 — Get Gaming Settings
```
Response:
  data[5]=0x00 (success)
  data[6]=gaming_mode_active
  data[7-12]: analog config (ls_min, ls_max, rs_min, rs_max, trig_min, trig_max)
```

##### 0xD2 — Reset Gaming Settings
```
Response: data[5]=0x00
```

#### Velocity Matrix Poll (0xD3)
```
data[6]:   num_keys (max 6)
data[7]:   row0
data[8]:   col0
data[9]:   row1
data[10]:  col1
...

Response per key (4 bytes each):
  data[6 + i*4]:   final_velocity (0-127, post-curve)
  data[7 + i*4]:   travel_time_lo (ms)
  data[8 + i*4]:   travel_time_hi (ms)
  data[9 + i*4]:   raw_velocity (0-255, pre-curve)
```
GUI method: `velocity_matrix_poll()` (retries=1)

#### Velocity Time Settings (0xD4)
```
Sub-command at data[6]:
  0 = GET:  Returns current min/max press times
  1 = SET:  data[7-8]=min_press_time(LE), data[9-10]=max_press_time(LE)
  2 = SAVE: Saves to EEPROM

Response (all sub-cmds):
  data[4]=0x01, data[5-6]=min_press_time(LE), data[7-8]=max_press_time(LE)
```
GUI methods: `get_velocity_time_settings()`, `set_velocity_time_settings()`, `save_velocity_time_settings()`

#### Calibration Debug (0xD5)
```
data[6]:   num_keys (max 4)
data[7]:   row0
data[8]:   col0
...

Response per key (6 bytes each, starting at data[6]):
  [rest_adc_lo, rest_adc_hi, bottom_adc_lo, bottom_adc_hi, raw_adc_lo, raw_adc_hi]
```
All 16-bit values are little-endian. GUI method: `calibration_debug_poll()` (retries=1)

#### User Curve Commands (0xD9–0xDD)

##### 0xD9 — Set Velocity Preset (Chunked, 4 packets)

**Chunk 0 (Name + Zone Flags):**
```
data[6]:    slot (0-9)
data[7]:    chunk_id (0)
data[8-23]: name (16 bytes, null-terminated)
data[24]:   zone_flags (bitmap)
data[25]:   reserved
```

**Chunks 1-3 (Zone Settings):** Chunk 1=base zone, 2=keysplit, 3=triplesplit
```
data[6]:     slot
data[7]:     chunk_id (1, 2, or 3)
data[8-15]:  4 control points (8 bytes)
data[16]:    velocity_min
data[17]:    velocity_max
data[18-19]: slow_press_time (LE 16-bit)
data[20-21]: fast_press_time (LE 16-bit)
data[22]:    aftertouch_mode
data[23]:    aftertouch_cc
data[24]:    vibrato_sensitivity
data[25-26]: vibrato_decay (LE 16-bit)
data[27]:    flags
data[28]:    actuation_point
data[29]:    speed_peak_ratio
data[30]:    retrigger_distance
```
EEPROM save triggers on final chunk (chunk 3). Response: `data[5]=0x01`

##### 0xDA — Get Velocity Preset (4 response packets)
```
Request: data[6]=slot (0-9)
Response: 4 packets (same layout as set chunks, data[5]=0x01)
```

##### 0xDB — Get All Preset Names
```
Response: data[5]=0x01, data[6-25]=10 names (2 chars each, truncated)
```

##### 0xDC — Reset User Curves
```
Response: data[5]=0x01
```

##### 0xDD — Toggle Velocity Preset Debug
```
Response: data[5]=0x01, data[6]=current debug state
```

#### ADC Matrix (0xDF)
```
data[4]: row_index (0-4)

Response:
  data[4]=row (echoed), data[5]=0x01 (success)
  data[6 + col*2]:     adc_lo (for each column)
  data[6 + col*2 + 1]: adc_hi
```
14 columns × 2 bytes = 28 bytes. 16-bit little-endian ADC values (0-4095).
GUI method: `adc_matrix_poll()` (retries=1)

#### Per-Key Actuation (0xE0–0xE6)

##### 0xE0 — Set Per-Key Actuation
```
data[6]:  layer (0-11)
data[7]:  key_index (0-69)
data[8]:  actuation (0-255, default 127 = 2.0mm)
data[9]:  deadzone_top (0-51, default 6)
data[10]: deadzone_bottom (0-51, default 6)
data[11]: velocity_curve (0-16: 0-6 factory, 7-16 user)
data[12]: flags (bit0=RT enabled, bit1=per-key velocity, bit2=continuous RT)
data[13]: rapidfire_press_sens (0-100, default 6)
data[14]: rapidfire_release_sens (0-100, default 6)
data[15]: rapidfire_velocity_mod (-64 to +64, signed, default 0)

Response: data[4]=0x01
```
GUI method: `set_per_key_actuation()` via `_create_hid_packet(0xE0, ...)` (retries=20)

##### 0xE1 — Get Per-Key Actuation
```
data[6]: layer, data[7]: key_index

Response: data[4]=0x01, data[5-12]=8 config bytes (same order as set)
```
GUI method: `get_per_key_actuation()` (retries=3)

##### 0xE2 — Get All Per-Key Actuations (Bulk, 24 packets)
```
data[6]: layer

Response (24 packets, 3 keys per packet):
  data[4]=0x01, data[5]=layer, data[6]=packet_num(0-23), data[7]=total_packets(24)
  data[8-31]: 3 keys × 8 bytes each (last packet has 1 key)
```
70 keys / 3 per packet = 24 packets.

##### 0xE3 — Reset Per-Key Actuations
```
Response: data[4]=0x01
```

##### 0xE4 — Set Per-Key Mode (DEPRECATED)
```
data[6]: per_key_enabled, data[7]: per_layer_enabled
Response: data[4]=0x01 (no-op, firmware always uses per-key per-layer)
```

##### 0xE5 — Get Per-Key Mode (DEPRECATED)
```
Response: returns [1, 1] always
```

##### 0xE6 — Copy Layer Actuations
```
data[6]: source_layer, data[7]: dest_layer
Response: data[4]=0x01
```

#### Distance Matrix (0xE7)
```
data[6]:   num_keys (max 8)
data[7]:   row0
data[8]:   col0
...

Response per key (2 bytes each, starting at data[6]):
  [distance_lo, distance_hi]    (0.01mm units, 0-400 = 0-4.0mm, 16-bit LE)
```
GUI method: `distance_matrix_poll()` (retries=1)

#### Set Keyboard Param Single (0xE8)

Real-time parameter updates. Calls `analog_matrix_refresh_settings()` on success.

```
data[6]: param_id
data[7]: value_lo (8-bit param or low byte of 16-bit param)
data[8]: value_hi (high byte for 16-bit params only)

Response: data[5]=0x01, data[6]=param_id echo, data[7]=value echo
```

**Complete Parameter ID Table:**

| ID | Name | Bytes | Range | Effect |
|----|------|-------|-------|--------|
| 4 | HE_VELOCITY_CURVE | 1 | 0-16 | Active velocity curve. Applies preset via `velocity_preset_apply()` |
| 5 | HE_VELOCITY_MIN | 1 | 1-127 | Base zone min velocity |
| 6 | HE_VELOCITY_MAX | 1 | 1-127 | Base zone max velocity |
| 7 | KEYSPLIT_HE_VELOCITY_CURVE | 1 | 0-16 | Keysplit zone velocity curve |
| 8 | KEYSPLIT_HE_VELOCITY_MIN | 1 | 1-127 | Keysplit min velocity |
| 9 | KEYSPLIT_HE_VELOCITY_MAX | 1 | 1-127 | Keysplit max velocity |
| 10 | TRIPLESPLIT_HE_VELOCITY_CURVE | 1 | 0-16 | Triplesplit zone velocity curve |
| 11 | TRIPLESPLIT_HE_VELOCITY_MIN | 1 | 1-127 | Triplesplit min velocity |
| 12 | TRIPLESPLIT_HE_VELOCITY_MAX | 1 | 1-127 | Triplesplit max velocity |
| 13 | VELOCITY_MODE | 1 | 0-3 | **DEPRECATED** — firmware fixed at mode 3 (Speed+Peak), request ignored |
| 14 | AFTERTOUCH_MODE | 1 | 0-8 | See aftertouch modes table in CLAUDE.md |
| 39 | AFTERTOUCH_CC | 1 | 0-127, 255 | CC number for aftertouch (255=off/channel pressure) |
| 40 | VIBRATO_SENSITIVITY | 1 | 50-200 | Vibrato detection sensitivity |
| 41 | VIBRATO_DECAY_TIME | 2 (LE) | 0-2000 | Vibrato leaky integrator decay (ms) |
| 42 | MIN_PRESS_TIME | 2 (LE) | 50-500 | Slowest meaningful press (ms) → velocity 255 |
| 43 | MAX_PRESS_TIME | 2 (LE) | 5-100 | Fastest press (ms) → velocity 1 |
| 44 | SPEED_PEAK_RATIO | 1 | 0-100 | Speed vs peak blend (100=all speed, 0=all peak) |
| 45 | MACRO_OVERRIDE_LIVE_NOTES | 1 | 0-1 | Macro playback overrides live notes |
| 46 | SMARTCHORD_MODE | 1 | 0-1 | 0=Hold, 1=Toggle |
| 47 | BASE_SMARTCHORD_IGNORE | 1 | 0-1 | Base zone ignores smartchord |
| 48 | KEYSPLIT_SMARTCHORD_IGNORE | 1 | 0-1 | Keysplit zone ignores smartchord |
| 49 | TRIPLESPLIT_SMARTCHORD_IGNORE | 1 | 0-1 | Triplesplit zone ignores smartchord |
| 50 | VELOCITY_AS_AT | 1 | 0-1 | Pre-load aftertouch from velocity value |

GUI method: `set_keyboard_param_single()` via `_create_hid_packet(0xE8, ...)` (retries=1)

#### EQ Curve Tuning (0xE9)

**NOTE:** This is on the **Custom HID path** (0x7D prefix). The same command ID 0xE9 on the **Vial path** (0xFE prefix) is the Keymap RAM Rescan. No conflict — different routing paths.

```
data[6-7]:   range_low (16-bit LE)
data[8-9]:   range_high (16-bit LE)
data[10-14]: range 0 bands (5 bytes) — low rest sensors (<1745)
data[15-19]: range 1 bands (5 bytes) — mid rest sensors (1745-2082)
data[20-24]: range 2 bands (5 bytes) — high rest sensors (>=2082)
data[25]:    range 0 scale multiplier
data[26]:    range 1 scale multiplier
data[27]:    range 2 scale multiplier

Response: data[4]=0x01
```
GUI method: `set_eq_curve_settings()` (retries=1)

#### EQ Curve Save (0xEA)
```
Response: data[4]=0x01
```
Calls `eq_curve_save_to_eeprom()` + `save_keyboard_settings()`.
GUI method: `save_eq_to_eeprom()` (retries=1)

#### Layer Actuation (0xEB–0xEE)

##### 0xEB — Get Layer Actuation
```
data[6]: layer (0-11)

Response: data[4]=0x01 / 0x00
  data[5]:    normal_actuation
  data[6]:    midi_base_actuation
  data[7]:    velocity_mode
  data[8]:    speed_peak_ratio
  data[9]:    flags
  data[10]:   aftertouch_mode
  data[11]:   aftertouch_cc
  data[12]:   vibrato_sensitivity
  data[13-14]: vibrato_decay_time (16-bit LE)
```
GUI method: `get_layer_actuation()` (retries=3)

##### 0xEC — Set Layer Actuation
```
data[6-15]: 10 bytes (same layout as GET response at data[5-14])

Response: data[4]=0x01
```
GUI method: `set_layer_actuation()` (retries=3)

##### 0xED — Get All Layer Actuations (Bulk, 6 packets)
```
Response (6 packets, 2 layers per packet):
  data[4]=0x01, data[5]=packet_num(0-5), data[6]=total_packets(6)
  data[7-16]:  layer N settings (10 bytes)
  data[17-26]: layer N+1 settings (10 bytes)
```
12 layers / 2 per packet = 6 packets.

##### 0xEE — Reset Layer Actuations
```
Response: data[4]=0x01
```

#### Get EQ Settings (0xEF)
```
Response:
  data[4-5]:   range_low (16-bit LE)
  data[6-7]:   range_high (16-bit LE)
  data[8-22]:  15 EQ bands (3 ranges × 5 bands)
  data[23-25]: 3 range scale multipliers
  data[26]:    LUT correction strength (0-100)
```
GUI method: `get_eq_settings()` (retries=1)

#### Null Bind (0xF0–0xF4)

| CMD | Name | Input | Handler |
|-----|------|-------|---------|
| 0xF0 | GET_GROUP | `data[6]=group_num` | `handle_nullbind_get_group()` |
| 0xF1 | SET_GROUP | `data[6]=group, data[7]=behavior, data[8]=key_count, data[9-16]=keys[8]` | `handle_nullbind_set_group()` |
| 0xF2 | SAVE_EEPROM | (none) | `handle_nullbind_save_eeprom()` |
| 0xF3 | LOAD_EEPROM | (none) | `handle_nullbind_load_eeprom()` |
| 0xF4 | RESET_ALL | (none) | `handle_nullbind_reset_all()` |

#### Toggle Keys (0xF5–0xF9)

| CMD | Name | Input | Handler |
|-----|------|-------|---------|
| 0xF5 | GET_SLOT | `data[6]=slot_num` | `handle_toggle_get_slot()` |
| 0xF6 | SET_SLOT | `data[6]=slot, data[7-8]=target_keycode(LE)` | `handle_toggle_set_slot()` |
| 0xF7 | SAVE_EEPROM | (none) | `handle_toggle_save_eeprom()` |
| 0xF8 | LOAD_EEPROM | (none) | `handle_toggle_load_eeprom()` |
| 0xF9 | RESET_ALL | (none) | `handle_toggle_reset_all()` |

#### EEPROM Diagnostics (0xFA–0xFB)

| CMD | Name | Handler |
|-----|------|---------|
| 0xFA | DIAG_RUN | `handle_eeprom_diag_run(response)` |
| 0xFB | DIAG_GET | `handle_eeprom_diag_get(response)` |

---

## 6. Command ID Map

### Complete ID Allocation

```
PATH 1 — VIA Standard (data[0] = cmd)
  0x01  Get Protocol Version
  0x02  Get Keyboard Value (sub-IDs: 0x00=uptime, 0x02=matrix, 0x04=layout_opts)
  0x03  Set Keyboard Value (sub-ID: 0x04=layout_opts)
  0x04  Get Keycode
  0x05  Set Keycode
  0x06  Reset Keymap
  0x07  Lighting Set Value (sub-ID: 0x41=VIALRGB_SET_MODE)
  0x08  Lighting Get Value (sub-IDs: 0x40=info, 0x41=mode, 0x42=supported)
  0x09  Lighting Save
  0x0B  Bootloader Jump
  0x0C  Macro Get Count
  0x0D  Macro Get Buffer Size
  0x0E  Macro Get Buffer
  0x0F  Macro Set Buffer
  0x10  Macro Reset
  0x11  Get Layer Count
  0x12  Keymap Get Buffer
  0x13  Keymap Set Buffer

PATH 2 — Vial (msg[0]=0xFE, msg[1] = cmd)
  0x00  Get Keyboard ID
  0x01  Get Definition Size
  0x02  Get Definition Block
  0x03  Get Encoder
  0x04  Set Encoder
  0x05  Get Unlock Status
  0x06  Unlock Start
  0x07  Unlock Poll
  0x08  Lock
  0x09  QMK Settings Query
  0x0A  QMK Settings Get
  0x0B  QMK Settings Set
  0x0C  QMK Settings Reset
  0x0D  Dynamic Entry Operations (sub-ops: 0x00-0x06)
  ---
  0xBC  Layer RGB Save
  0xBD  Layer RGB Load
  0xBE  Layer RGB Enable
  0xBF  Layer RGB Get Status
  0xC0  Custom Anim Set Param
  0xC1  Custom Anim Get Param
  0xC2  Custom Anim Set All
  0xC3  Custom Anim Get All
  0xC4  Custom Anim Save
  0xC5  Custom Anim Load
  0xC6  Custom Anim Reset Slot
  0xC7  Custom Anim Get Status
  0xC8  Rescan LED Positions (EEPROM, SLOW — prefer 0xE9)
  0xC9  Custom Anim Get RAM State
  0xCA  [DEPRECATED] Layer Actuation Set
  0xCB  [DEPRECATED] Layer Actuation Get
  0xCC  [DEPRECATED] Layer Actuation Get All
  0xCD  Layer Actuation Reset
  0xCE  Gaming Set Mode
  0xCF  Gaming Set Key Map
  0xD0  Gaming Set Analog Config
  0xD1  Gaming Get Settings
  0xD2  Gaming Reset
  0xD3  Per-Key RGB Get Palette
  0xD4  Per-Key RGB Set Palette Color
  0xD5  Per-Key RGB Get Preset Data
  0xD6  Per-Key RGB Set LED Color
  0xD7  Per-Key RGB Save
  0xD8  Per-Key RGB Load
  0xD9  User Curve Set
  0xDA  User Curve Get
  0xDB  User Curve Get All Names
  0xDC  User Curve Reset
  0xDD  Gaming Response Set
  0xDE  Gaming Response Get
  0xE0  Per-Key Actuation Set
  0xE1  Per-Key Actuation Get
  0xE3  Per-Key Actuation Reset
  0xE4  [DEPRECATED] Per-Key Mode Set
  0xE5  [DEPRECATED] Per-Key Mode Get
  0xE6  Copy Layer Actuations
  0xE8  Keyboard Param Single
  0xE9  Keymap RAM Rescan (NEW)

PATH 3A — Custom HID → dynamic_macro_hid_receive (data[3] = cmd)
  0xA0  Macro Save Start
  0xA1  Macro Save Chunk
  0xA2  Macro Save End
  0xA3  Macro Load Start
  0xA4  Macro Load Chunk
  0xA5  Macro Load End
  0xA6  Macro Load Overdub Start
  0xA7  Clear All Loops
  0xA8  Request Save
  0xA9  Trigger Save All
  0xAA  DKS Get Slot
  0xAB  DKS Set Action
  0xAC  DKS Save EEPROM
  0xAD  DKS Load EEPROM
  0xAE  DKS Reset Slot
  0xAF  DKS Reset All
  0xB0  ThruLoop Set Config
  0xB1  ThruLoop Set Main CCs
  0xB2  ThruLoop Set Overdub CCs
  0xB3  ThruLoop Set Navigation
  0xB4  ThruLoop Get All Config
  0xB5  ThruLoop Reset Config
  0xB6  Keyboard Config Set (Basic)
  0xB7  Keyboard Config Get
  0xB8  Keyboard Config Reset
  0xB9  Keyboard Config Save Slot
  0xBA  Keyboard Config Load Slot
  0xBB  Keyboard Config Set (Advanced)

PATH 3B — Custom HID → raw_hid_receive_kb (data[3] = cmd)
  0xC0-0xCC  Arpeggiator (forwarded to arp_hid_receive)
  0xCE  Gaming Set Mode
  0xCF  Gaming Set Key Map
  0xD0  Gaming Set Analog Config
  0xD1  Gaming Get Settings
  0xD2  Gaming Reset
  0xD3  Velocity Matrix Poll
  0xD4  Velocity Time Settings
  0xD5  Calibration Debug
  0xD9  Velocity Preset Set (Chunked)
  0xDA  Velocity Preset Get
  0xDB  Velocity Preset Get All Names
  0xDC  Velocity Preset Reset
  0xDD  Velocity Preset Debug Toggle
  0xDF  ADC Matrix
  0xE0  Per-Key Actuation Set
  0xE1  Per-Key Actuation Get
  0xE2  Per-Key Actuation Get All (Bulk)
  0xE3  Per-Key Actuation Reset
  0xE4  [DEPRECATED] Per-Key Mode Set
  0xE5  [DEPRECATED] Per-Key Mode Get
  0xE6  Copy Layer Actuations
  0xE7  Distance Matrix
  0xE8  Keyboard Param Single
  0xE9  EQ Curve Tuning Set
  0xEA  EQ Curve Save EEPROM
  0xEB  Layer Actuation Get
  0xEC  Layer Actuation Set
  0xED  Layer Actuation Get All (Bulk)
  0xEE  Layer Actuation Reset
  0xEF  Get EQ Settings
  0xF0  Null Bind Get Group
  0xF1  Null Bind Set Group
  0xF2  Null Bind Save EEPROM
  0xF3  Null Bind Load EEPROM
  0xF4  Null Bind Reset All
  0xF5  Toggle Get Slot
  0xF6  Toggle Set Slot
  0xF7  Toggle Save EEPROM
  0xF8  Toggle Load EEPROM
  0xF9  Toggle Reset All
  0xFA  EEPROM Diag Run
  0xFB  EEPROM Diag Get
```

---

## 7. Dual-Path Commands (Same ID, Different Paths)

Several command IDs exist on **both** the Vial path (0xFE prefix) and the Custom HID path (0x7D prefix). They handle the same logical function but with different byte offsets due to different packet headers.

| CMD ID | Vial Path (0xFE prefix) | Custom HID Path (0x7D prefix) | GUI Uses |
|--------|------------------------|-------------------------------|----------|
| 0xCE | Gaming Set Mode (msg[2]) | Gaming Set Mode (data[6]) | Custom HID |
| 0xCF | Gaming Set Key Map (msg[2-5]) | Gaming Set Key Map (data[6-9]) | Custom HID |
| 0xD0 | Gaming Set Analog (msg[2-7]) | Gaming Set Analog (data[6-11]) | Custom HID |
| 0xD1 | Gaming Get Settings | Gaming Get Settings | Custom HID |
| 0xD2 | Gaming Reset | Gaming Reset | Custom HID |
| 0xD9 | User Curve Set (simple) | Velocity Preset Set (chunked) | Custom HID |
| 0xDA | User Curve Get (simple) | Velocity Preset Get (chunked) | Custom HID |
| 0xDB | User Curve Get All Names | Velocity Preset Get All Names | Custom HID |
| 0xDC | User Curve Reset | Velocity Preset Reset | Custom HID |
| 0xDD | Gaming Response Set (msg[2-6]) | Velocity Preset Debug Toggle | Custom HID (both used!) |
| 0xDE | Gaming Response Get | (not in arpeggiator_hid.c) | Vial path |
| 0xE0 | Per-Key Set (msg[2-11]) | Per-Key Set (data[6-15]) | Custom HID |
| 0xE1 | Per-Key Get (msg[2-3]) | Per-Key Get (data[6-7]) | Custom HID |
| 0xE3 | Per-Key Reset | Per-Key Reset | Custom HID |
| 0xE6 | Copy Layer Actuations (msg[2-3]) | Copy Layer Actuations (data[6-7]) | Custom HID |
| 0xE8 | Keyboard Param Single (msg[2-4]) | Keyboard Param Single (data[6-8]) | Custom HID |

**IMPORTANT: Same ID, different meaning:**

| CMD ID | Vial Path (0xFE prefix) | Custom HID Path (0x7D prefix) |
|--------|------------------------|-------------------------------|
| **0xD3** | Per-Key RGB Get Palette | Velocity Matrix Poll |
| **0xD4** | Per-Key RGB Set Palette Color | Velocity Time Settings |
| **0xD5** | Per-Key RGB Get Preset Data | Calibration Debug |
| **0xE9** | **Keymap RAM Rescan** (NEW) | **EQ Curve Tuning Set** |

These do NOT conflict because the routing in `via.c` separates packets by prefix before any handler sees them. A packet starting with `0xFE` never reaches `raw_hid_receive_kb()`, and a packet starting with `0x7D` never reaches `vial_handle_cmd()`.

---

## GUI Python Method → HID Command Quick Reference

| GUI Method | Path | CMD | File |
|------------|------|-----|------|
| `reload_via_protocol()` | VIA | 0x01 | keyboard_comm.py |
| `matrix_poll()` | VIA | 0x02/0x03 | keyboard_comm.py |
| `set_key()` | VIA | 0x05 | keyboard_comm.py |
| `reload_keymap()` | VIA | 0x12 | keyboard_comm.py |
| `reload_layout()` | Vial | 0x00, 0x01, 0x02 | keyboard_comm.py |
| `set_encoder()` | Vial | 0x04 | keyboard_comm.py |
| `get_unlock_status()` | Vial | 0x05 | keyboard_comm.py |
| `reload_rgb()` | VIA | 0x08 | keyboard_comm.py |
| `save_rgb()` | VIA | 0x09 | keyboard_comm.py |
| `_vialrgb_set_mode()` | VIA | 0x07/0x41 | keyboard_comm.py |
| `get_layer_rgb_status()` | Vial | 0xBF | keyboard_comm.py |
| `set_layer_rgb_enable()` | Vial | 0xBE | keyboard_comm.py |
| `save_rgb_to_layer()` | Vial | 0xBC | keyboard_comm.py |
| `load_rgb_from_layer()` | Vial | 0xBD | keyboard_comm.py |
| `get_custom_animation_status()` | Vial | 0xC7 | keyboard_comm.py |
| `get_custom_slot_config()` | Vial | 0xC3 | keyboard_comm.py |
| `set_custom_slot_parameter()` | Vial | 0xC0 | keyboard_comm.py |
| `set_custom_slot_all_parameters()` | Vial | 0xC2 | keyboard_comm.py |
| `save_custom_slot()` | Vial | 0xC4 | keyboard_comm.py |
| `reset_custom_slot()` | Vial | 0xC6 | keyboard_comm.py |
| `rescan_led_positions()` | Vial | 0xC8 | keyboard_comm.py |
| `send_keymap_for_ram_rescan()` | Vial | 0xE9 | keyboard_comm.py |
| `set_per_key_actuation()` | Custom | 0xE0 | keyboard_comm.py |
| `get_per_key_actuation()` | Custom | 0xE1 | keyboard_comm.py |
| `get_all_per_key_actuations()` | Custom | 0xE2 | keyboard_comm.py |
| `reset_per_key_actuations()` | Custom | 0xE3 | keyboard_comm.py |
| `copy_layer_actuations()` | Custom | 0xE6 | keyboard_comm.py |
| `set_layer_actuation()` | Custom | 0xEC | keyboard_comm.py |
| `get_layer_actuation()` | Custom | 0xEB | keyboard_comm.py |
| `get_all_layer_actuations()` | Custom | 0xED | keyboard_comm.py |
| `reset_layer_actuations()` | Custom | 0xEE | keyboard_comm.py |
| `set_keyboard_param_single()` | Custom | 0xE8 | keyboard_comm.py |
| `set_midi_config()` | Custom | 0xB6 | keyboard_comm.py |
| `set_midi_advanced_config()` | Custom | 0xBB | keyboard_comm.py |
| `get_midi_config()` | Custom | 0xB7 | keyboard_comm.py |
| `save_midi_slot()` | Custom | 0xB9 | keyboard_comm.py |
| `load_midi_slot()` | Custom | 0xBA | keyboard_comm.py |
| `reset_midi_config()` | Custom | 0xB8 | keyboard_comm.py |
| `set_thruloop_config()` | Custom | 0xB0 | keyboard_comm.py |
| `set_thruloop_main_ccs()` | Custom | 0xB1 | keyboard_comm.py |
| `set_thruloop_overdub_ccs()` | Custom | 0xB2 | keyboard_comm.py |
| `set_thruloop_navigation()` | Custom | 0xB3 | keyboard_comm.py |
| `get_thruloop_config()` | Custom | 0xB4 | keyboard_comm.py |
| `reset_thruloop_config()` | Custom | 0xB5 | keyboard_comm.py |
| `clear_all_loops()` | Custom | 0xA7 | keyboard_comm.py |
| `set_gaming_mode()` | Custom | 0xCE | keyboard_comm.py |
| `set_gaming_key_map()` | Custom | 0xCF | keyboard_comm.py |
| `set_gaming_analog_config()` | Custom | 0xD0 | keyboard_comm.py |
| `get_gaming_settings()` | Custom | 0xD1 | keyboard_comm.py |
| `reset_gaming_settings()` | Custom | 0xD2 | keyboard_comm.py |
| `set_gaming_response()` | Custom | 0xDD | keyboard_comm.py |
| `get_gaming_response()` | Custom | 0xDE | keyboard_comm.py |
| `set_velocity_preset()` | Custom | 0xD9 | keyboard_comm.py |
| `get_velocity_preset()` | Custom | 0xDA | keyboard_comm.py |
| `get_all_user_curve_names()` | Custom | 0xDB | keyboard_comm.py |
| `reset_user_curves()` | Custom | 0xDC | keyboard_comm.py |
| `adc_matrix_poll()` | Custom | 0xDF | keyboard_comm.py |
| `distance_matrix_poll()` | Custom | 0xE7 | keyboard_comm.py |
| `calibration_debug_poll()` | Custom | 0xD5 | keyboard_comm.py |
| `velocity_matrix_poll()` | Custom | 0xD3 | keyboard_comm.py |
| `get_velocity_time_settings()` | Custom | 0xD4 | keyboard_comm.py |
| `set_velocity_time_settings()` | Custom | 0xD4 | keyboard_comm.py |
| `set_eq_curve_settings()` | Custom | 0xE9 | keyboard_comm.py |
| `save_eq_to_eeprom()` | Custom | 0xEA | keyboard_comm.py |
| `get_eq_settings()` | Custom | 0xEF | keyboard_comm.py |

---

*Document generated from code analysis. Source files: via.c, vial.c, arpeggiator_hid.c, process_dynamic_macro.c, keyboard_comm.py, constants.py*
