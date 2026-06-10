# Arpeggiator/Sequencer Note Data Flow Architecture

## Overview
This document describes the complete data flow for arpeggiator and step sequencer preset notes, from GUI editing through HID transmission, firmware storage, EEPROM persistence, and final MIDI playback.

---

## Complete Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          GUI (Python/Qt)                                │
│                     arpeggiator.py                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ User edits notes in GUI
                                  │ (timing, velocity, note_index, octave)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  NOTE PACKING (GUI)                                                     │
│  arpeggiator.py:2594  pack_note_data()                                 │
│                                                                         │
│  Input: Dictionary with note fields                                    │
│    - timing: 0-127 (position in 16ths)                                 │
│    - velocity: 0-255                                                    │
│    - note_index: -11 to +11 (arp) or 0-11 (seq)                        │
│    - octave_offset: -8 to +7                                            │
│                                                                         │
│  Packing Logic:                                                         │
│    1. packed_timing_vel (uint16_t):                                     │
│       bits 0-6:   timing (0-127)                                        │
│       bits 7-13:  velocity / 2 (0-127)                                  │
│       bit 14:     sign bit (1 if note_index < 0, arp only)              │
│       bit 15:     reserved                                              │
│                                                                         │
│    2. note_octave (uint8_t):                                            │
│       bits 0-3:   abs(note_index) (0-11)                                │
│       bits 4-7:   octave_offset as 4-bit signed (-8 to +7)              │
│                                                                         │
│  Output: 3 bytes per note [byte0, byte1, byte2]                        │
│    byte0: packed_timing_vel & 0xFF                                      │
│    byte1: (packed_timing_vel >> 8) & 0xFF                               │
│    byte2: note_octave                                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ All notes packed (up to 128 notes)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  3-STAGE SAVE PROCESS                                                   │
│  arpeggiator.py:2741  save_preset()                                    │
│                                                                         │
│  STAGE 1: Send Metadata (8 bytes)                                      │
│    Command: ARP_CMD_SET_PRESET (0xC0)                                  │
│    Parameters:                                                          │
│      [0] preset_id                                                      │
│      [1] preset_type (0=arp, 1=seq)                                     │
│      [2] note_count                                                     │
│      [3] pattern_length_16ths (high byte)                               │
│      [4] pattern_length_16ths (low byte)                                │
│      [5] gate_length_percent                                            │
│      [6] timing_mode (0=straight, 1=triplet, 2=dotted)                  │
│      [7] note_value (0=quarter, 1=eighth, 2=sixteenth)                  │
│                                                                         │
│    Wait 50ms ────────────────────────────┐                              │
│                                          │                              │
│  STAGE 2: Send Notes in Chunks           │                              │
│    arpeggiator.py:2641  send_notes_chunked()                           │
│    Command: ARP_CMD_SET_NOTES_CHUNK (0xCB)                             │
│                                          │                              │
│    Chunking: 9 notes per 32-byte HID packet                             │
│    Total packets needed: ceil(note_count / 9)                           │
│                                          │                              │
│    For each chunk:                       │                              │
│      Parameters:                         │                              │
│        [0] preset_id                     │                              │
│        [1] start_index                   │                              │
│        [2] chunk_count (max 9)           │                              │
│        [3..29] note data (3 bytes × 9 = 27 bytes)                       │
│                                          │                              │
│      10ms delay between chunks ──────────┤                              │
│                                          │                              │
│    Wait 100ms ───────────────────────────┤                              │
│                                          │                              │
│  STAGE 3: Save to EEPROM                 │                              │
│    Command: ARP_CMD_SAVE_PRESET (0xC1)   │                              │
│    Parameters:                           │                              │
│      [0] preset_id                       │                              │
└──────────────────────────────────────────┼──────────────────────────────┘
                                          │
                                          │ HID Raw (32-byte packets)
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    FIRMWARE (C/QMK)                                     │
│                 VIA/Vial HID Routing                                    │
│                    vial.c / via.c                                       │
│                                                                         │
│  HID Packet Format (32 bytes):                                         │
│    [0] manufacturer_id                                                  │
│    [1] sub_id (0x43 for arpeggiator)                                    │
│    [2] device_id                                                        │
│    [3] command (0xC0-0xCB)                                              │
│    [4..31] parameters (28 bytes)                                        │
│                                                                         │
│  Routes to: arpeggiator_hid_handler()                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  HID COMMAND HANDLERS                                                   │
│  arpeggiator_hid.c                                                      │
│                                                                         │
│  HANDLER: ARP_CMD_SET_PRESET (0xC0)                                     │
│    Line 148-195                                                         │
│    - Validates preset_id (48-63 for user presets)                       │
│    - Extracts metadata from params                                      │
│    - Stores in arp_presets[preset_id]:                                  │
│        preset_type, note_count, pattern_length_16ths,                   │
│        gate_length_percent, timing_mode, note_value                     │
│    - Sets magic number for validation                                   │
│    - Does NOT save to EEPROM yet                                        │
│                                                                         │
│  HANDLER: ARP_CMD_SET_NOTES_CHUNK (0xCB)                                │
│    Line 268-327                                                         │
│    - Validates preset_id, start_index, chunk_count                      │
│    - Limits chunk_count to max 9 notes                                  │
│    - Checks bounds: start_index + chunk_count <= 128                    │
│    - Extracts note data from params[3..29]                              │
│    - For each note in chunk:                                            │
│        offset = i * 3                                                   │
│        packed_timing_vel = note_data[offset] | (note_data[offset+1]<<8) │
│        note_octave = note_data[offset + 2]                              │
│        preset->notes[note_idx].packed_timing_vel = packed_timing_vel    │
│        preset->notes[note_idx].note_octave = note_octave                │
│    - Stores directly in RAM (arp_presets array)                         │
│    - Does NOT save to EEPROM yet                                        │
│                                                                         │
│  HANDLER: ARP_CMD_SAVE_PRESET (0xC1)                                    │
│    Line 197-220                                                         │
│    - Calls arp_save_preset_to_eeprom(preset_id)                         │
│    - Triggers persistence to EEPROM                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  EEPROM STORAGE                                                         │
│  arpeggiator.c:986  arp_save_preset_to_eeprom()                        │
│                                                                         │
│  Storage Layout:                                                        │
│    Base Address: 65800                                                  │
│    Preset Size: sizeof(arp_preset_t) = 8 + (128 * 3) = 392 bytes       │
│    Preset Address: 65800 + ((preset_id - 48) * 392)                     │
│                                                                         │
│  Structure Written (392 bytes):                                         │
│    [0]      preset_type (uint8_t)                                       │
│    [1]      note_count (uint8_t)                                        │
│    [2-3]    pattern_length_16ths (uint16_t)                             │
│    [4]      gate_length_percent (uint8_t)                               │
│    [5]      timing_mode (uint8_t)                                       │
│    [6]      note_value (uint8_t)                                        │
│    [7-8]    magic (uint16_t) = 0xA89F                                   │
│    [9-392]  notes[128] (arp_preset_note_t × 128)                        │
│                Each note: 3 bytes                                       │
│                  [0-1] packed_timing_vel (uint16_t)                     │
│                  [2]   note_octave (uint8_t)                            │
│                                                                         │
│  Validation: Checks magic number (0xA89F) and bounds                    │
│  Persistence: eeprom_update_block() writes entire struct                │
└─────────────────────────────────────────────────────────────────────────┘
                                          │
                                          │ At keyboard power-on
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  EEPROM LOADING                                                         │
│  arpeggiator.c:1011  arp_load_preset_from_eeprom()                     │
│                                                                         │
│  On Initialization (arp_init):                                          │
│    - Factory presets (0-47): Hardcoded in firmware                      │
│    - User presets (48-63): Loaded from EEPROM                           │
│                                                                         │
│  Loading Process:                                                       │
│    1. Read 392 bytes from EEPROM into temp buffer                       │
│    2. Validate magic number (0xA89F)                                    │
│    3. Validate bounds (note_count <= 128, etc.)                         │
│    4. If valid: memcpy to arp_presets[preset_id]                        │
│    5. If invalid: Skip (preset remains uninitialized)                   │
│                                                                         │
│  Result: All presets loaded into RAM (arp_presets array)                │
└─────────────────────────────────────────────────────────────────────────┘
                                          │
                                          │ User selects preset
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PRESET ACTIVATION                                                      │
│  arpeggiator.c:513  arp_start()                                        │
│                                                                         │
│  When user presses ARP button with preset selected:                     │
│    - Sets arp_state.current_preset_id                                   │
│    - Gets pointer to preset: &arp_presets[preset_id]                    │
│    - Resets playback state:                                             │
│        current_position_16ths = 0                                       │
│        current_note_in_chord = 0                                        │
│        next_note_time = timer_read32()                                  │
│    - Sets arp_state.active = true                                       │
│                                                                         │
│  Notes remain in packed format in RAM                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                          │
                                          │ Every matrix scan (~1ms)
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PLAYBACK ENGINE                                                        │
│  arpeggiator.c:580  arp_update()                                       │
│                                                                         │
│  Called repeatedly during playback:                                     │
│                                                                         │
│  1. Check timing:                                                       │
│     if (current_time < next_note_time) return;                          │
│                                                                         │
│  2. Special case - Random preset (id=3):                                │
│     arpeggiator.c:607-619                                               │
│     - Randomizes note_index values on-the-fly                           │
│     - Extracts octave: NOTE_GET_OCTAVE(preset->notes[i].note_octave)    │
│     - Generates random: rand() % 12                                     │
│     - Repacks: NOTE_PACK_NOTE_OCTAVE(random_note_index, octave)         │
│                                                                         │
│  3. Find notes at current position:                                     │
│     arpeggiator.c:621-628                                               │
│     - Iterate through preset->note_count notes                          │
│     - Unpack each note to check timing                                  │
│     - Collect notes matching current_position_16ths                     │
└─────────────────────────────────────────────────────────────────────────┘
                                          │
                                          │ For each note to play
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  NOTE UNPACKING                                                         │
│  arpeggiator.c:418  unpack_note()                                      │
│                                                                         │
│  Input: Packed note (arp_preset_note_t)                                │
│    - packed_timing_vel (uint16_t)                                       │
│    - note_octave (uint8_t)                                              │
│                                                                         │
│  Unpacking Logic:                                                       │
│    timing = NOTE_GET_TIMING(packed_timing_vel)                          │
│           = packed_timing_vel & 0x7F                                    │
│                                                                         │
│    velocity = NOTE_GET_VELOCITY(packed_timing_vel)                      │
│             = (packed_timing_vel >> 7) & 0x7F                           │
│                                                                         │
│    note_val = NOTE_GET_NOTE(note_octave)                                │
│             = note_octave & 0x0F                                        │
│                                                                         │
│    octave_offset = NOTE_GET_OCTAVE(note_octave)                         │
│                  = (int8_t)((note_octave << 4) >> 4)  [sign extend]     │
│                                                                         │
│  For Arpeggiator:                                                       │
│    sign = NOTE_GET_SIGN(packed_timing_vel)                              │
│         = (packed_timing_vel >> 14) & 0x01                              │
│    note_index = sign ? -note_val : note_val  (signed interval)          │
│                                                                         │
│  For Step Sequencer:                                                    │
│    note_index = note_val  (unsigned 0-11)                               │
│                                                                         │
│  Output: Unpacked note (unpacked_note_t)                                │
│    - timing (uint8_t)                                                   │
│    - velocity (uint8_t)                                                 │
│    - note_index (int8_t)                                                │
│    - octave_offset (int8_t)                                             │
└─────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  MIDI NOTE CALCULATION                                                  │
│  arpeggiator.c:640-787                                                 │
│                                                                         │
│  STEP SEQUENCER MODE (absolute notes):                                  │
│    Line 642-667                                                         │
│    - midi_note = (octave_offset * 12) + note_index                      │
│    - Clamp to 0-127                                                     │
│    - Send directly to MIDI                                              │
│                                                                         │
│  ARPEGGIATOR MODE (relative intervals):                                 │
│    Depends on playback mode:                                            │
│                                                                         │
│    ARP_MODE_SINGLE_NOTE (Line 676-709):                                 │
│      - master_note = lowest held note                                   │
│      - final_note = master_note + note_index + (octave_offset * 12)     │
│      - Clamp to 0-127                                                   │
│                                                                         │
│    ARP_MODE_CHORD_BASIC (Line 712-745):                                 │
│      - For each held note:                                              │
│          final_note = held_note + note_index + (octave_offset * 12)     │
│      - Plays all held notes with offset                                 │
│                                                                         │
│    ARP_MODE_CHORD_ADVANCED (Line 747-782):                              │
│      - Rotates through held notes                                       │
│      - note_to_play = arp_state.current_note_in_chord % live_note_count │
│      - final_note = rotated_note + note_index + (octave_offset * 12)    │
│                                                                         │
│  Velocity Scaling:                                                      │
│    raw_travel = velocity * 2  (0-127 → 0-254)                           │
│                                                                         │
│  Gate Timing:                                                           │
│    ms_per_16th = 60000 / (BPM * note_value_multiplier)                  │
│    gate_duration = ms_per_16th * (gate_length_percent / 100)            │
│    note_off_time = current_time + gate_duration                         │
└─────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  MIDI OUTPUT                                                            │
│  orthomidi5x14.c  midi_send_noteon_arp()                               │
│                                                                         │
│  Note On Transmission:                                                  │
│    - Send MIDI Note On: (channel, note, velocity)                       │
│    - Add to arp_notes[] array for gate tracking                         │
│                                                                         │
│  Gate Tracking:                                                         │
│    - Each note stores: channel, note, velocity, note_off_time           │
│    - process_arp_note_offs() checks note_off_time                       │
│    - When time reached: Send MIDI Note Off                              │
│                                                                         │
│  Pattern Advancement:                                                   │
│    - current_position_16ths++                                           │
│    - If position >= pattern_length_16ths: loop to 0                     │
│    - next_note_time = current_time + ms_per_16th                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Structure Summary

### Packed Format (Storage/Transmission)
**`arp_preset_note_t` (3 bytes per note)**
```c
typedef struct {
    uint16_t packed_timing_vel;
      // bits 0-6:   timing_16ths (0-127)
      // bits 7-13:  velocity (0-127)
      // bit 14:     interval_sign (arpeggiator only)
      // bit 15:     reserved

    uint8_t note_octave;
      // bits 0-3:   note_index (0-11) or interval magnitude
      // bits 4-7:   octave_offset (signed -8 to +7)
} arp_preset_note_t;
```

### Unpacked Format (Runtime Playback)
**`unpacked_note_t` (4 bytes per note)**
```c
typedef struct {
    uint8_t timing;           // 0-127 (position in 16ths)
    uint8_t velocity;         // 0-127
    int8_t note_index;        // For arp: interval with sign; For seq: note 0-11
    int8_t octave_offset;     // -8 to +7
} unpacked_note_t;
```

---

## Key Functions by File

### GUI (arpeggiator.py)
- **`pack_note_data()`** (line 2594): Packs GUI note dict to 3-byte format
- **`send_notes_chunked()`** (line 2641): Sends notes in 9-note chunks
- **`save_preset()`** (line 2741): Orchestrates 3-stage save process

### Firmware HID (arpeggiator_hid.c)
- **`arpeggiator_hid_handler()`** (line 30): Routes HID commands
- **Handler 0xC0** (line 148): Receives preset metadata
- **Handler 0xCB** (line 268): Receives note chunks (NEW)
- **Handler 0xC1** (line 197): Triggers EEPROM save

### Firmware Storage (arpeggiator.c)
- **`arp_save_preset_to_eeprom()`** (line 986): Writes preset to EEPROM
- **`arp_load_preset_from_eeprom()`** (line 1011): Reads preset from EEPROM
- **`arp_validate_preset()`** (line 951): Checks magic number and bounds

### Firmware Playback (arpeggiator.c)
- **`arp_start()`** (line 513): Activates preset playback
- **`arp_update()`** (line 580): Main playback loop
- **`unpack_note()`** (line 418): Unpacks packed note to runtime format
- **MIDI calculation** (line 640-787): Converts intervals to MIDI notes

---

## Critical Implementation Details

### 1. Why 3 Bytes Per Note?
- **Minimal storage**: 128 notes × 3 bytes = 384 bytes (fits in EEPROM)
- **Sufficient precision**: 7 bits for timing/velocity is adequate for MIDI
- **Sign bit support**: Arpeggiator intervals can be negative

### 2. Why Chunked Transmission?
- **HID packet limit**: 32 bytes total, 28 bytes usable
- **Chunk size**: 3 bytes/note × 9 notes = 27 bytes (fits in 28 bytes)
- **Full preset**: 128 notes ÷ 9 = 15 packets

### 3. Why 3-Stage Save?
1. **Metadata first**: Prepares preset structure
2. **Notes second**: Populates note array in chunks
3. **EEPROM last**: Persists entire preset atomically

### 4. Arpeggiator vs Step Sequencer
| Aspect | Arpeggiator | Step Sequencer |
|--------|-------------|----------------|
| note_index | Semitone interval (-11 to +11) | Absolute note (0-11) |
| Sign bit | Used (bit 14) | Unused |
| Playback | Relative to held notes | Absolute MIDI notes |
| Master note | Required | Not used |

### 5. Random Preset Special Case
- **Preset ID 3**: "Random 8ths"
- **Behavior**: Randomizes note_index on each playback cycle
- **Implementation** (line 607-619):
  - Preserves timing, velocity, octave
  - Randomizes only note_index (0-11)
  - Uses packed field accessors to avoid compilation errors

---

## Fixed Compilation Error

### Original Error (Line 610)
```c
preset->notes[i].note_index = rand() % live_note_count;  // ❌ WRONG
```
**Problem**: Tries to access `note_index` as direct field, but struct uses packed bits.

### Fixed Implementation (Line 610-617)
```c
// Extract current octave_offset from packed field
int8_t current_octave = NOTE_GET_OCTAVE(preset->notes[i].note_octave);

// Generate random semitone offset (0-11 for notes within an octave)
uint8_t random_note_index = rand() % 12;

// Repack note_octave with new random note_index, preserving octave_offset
preset->notes[i].note_octave = NOTE_PACK_NOTE_OCTAVE(random_note_index, current_octave);
```
**Solution**: Uses macro accessors to extract/pack packed fields properly.

---

## Verification Checklist

✅ **GUI Note Packing**: `pack_note_data()` correctly packs all fields
✅ **Chunked Transmission**: `send_notes_chunked()` sends 9 notes/packet
✅ **HID Reception**: `ARP_CMD_SET_NOTES_CHUNK` handler validates and stores
✅ **EEPROM Storage**: Full 392-byte preset written atomically
✅ **EEPROM Loading**: Validation checks magic number
✅ **Note Unpacking**: `unpack_note()` reverses packing correctly
✅ **MIDI Calculation**: Different modes apply intervals correctly
✅ **Random Preset**: Fixed to use packed field accessors
✅ **No Direct Field Access**: Only line 610 had the error (now fixed)

---

## Testing Recommendations

1. **Save/Load Test**: Create user preset with 128 notes, save, power cycle, verify notes intact
2. **Chunking Test**: Monitor HID packets with 128 notes (should send 15 chunks)
3. **Random Preset Test**: Play preset 3, verify notes randomize each cycle
4. **Arpeggiator Test**: Verify intervals apply correctly in all 3 modes
5. **Step Sequencer Test**: Verify absolute notes play correctly
6. **EEPROM Validation Test**: Corrupt magic number, verify load fails gracefully

---

## File References

| File | Path | Purpose |
|------|------|---------|
| GUI Editor | `/home/user/vial-gui-custom/src/main/python/editor/arpeggiator.py` | Note packing, HID transmission |
| HID Handlers | `/home/user/vial-gui-custom/vial-qmk - ryzen/keyboards/orthomidi5x14/arpeggiator_hid.c` | HID command processing |
| Playback Engine | `/home/user/vial-gui-custom/vial-qmk - ryzen/keyboards/orthomidi5x14/arpeggiator.c` | Note unpacking, MIDI output |
| Data Structures | `/home/user/vial-gui-custom/vial-qmk - ryzen/keyboards/orthomidi5x14/orthomidi5x14.h` | Packed/unpacked note definitions |

---

*Last updated: 2025-12-08*
*Fix: Compilation error at arpeggiator.c:610 resolved using packed field accessors*
