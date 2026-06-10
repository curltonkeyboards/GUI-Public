# Chord Progression & Step Sequencer System

## Overview

The orthomidi5x14 keyboard has three main generative music systems:

1. **Chord/Bass/Lead Machines** (20 slots) — plays chord progressions with rhythmic patterns
2. **Drum Machine / Step Sequencer** (8 slots) — plays note sequences (melodic or drum patterns)
3. **Arpeggiator** (1 slot) — arpeggiation of held notes

All three share a global BPM clock and can sync to each other via loop triggers at bar boundaries.

---

## Chord / Bass / Lead Machines

### Keycodes & Slot Mapping

There are 20 chord progression slots. The first 18 are divided into three "machine" types with different default settings. Tap to play/stop, hold 2 seconds to open the OLED config menu.

**Chord Machine 1-6** (slots 0-5) — Default: Full layer, MIDI ch1, octave 0
| GUI Label | QMK Define | Hex | Slot Index |
|-----------|------------|-----|------------|
| Chord Machine 1 | `CPROG_SLOT_1` | 0xCA10 | 0 |
| Chord Machine 2 | `CPROG_SLOT_2` | 0xCA11 | 1 |
| Chord Machine 3 | `CPROG_SLOT_3` | 0xCA12 | 2 |
| Chord Machine 4 | `CPROG_SLOT_4` | 0xCA13 | 3 |
| Chord Machine 5 | `CPROG_SLOT_5` | 0xCA14 | 4 |
| Chord Machine 6 | `CPROG_SLOT_6` | 0xCA15 | 5 |

**Bass Machine 1-6** (slots 6-11) — Default: Bass layer, MIDI ch2, octave 0
| GUI Label | QMK Define | Hex | Slot Index |
|-----------|------------|-----|------------|
| Bass Machine 1 | `CPROG_SLOT_7` | 0xCA16 | 6 |
| Bass Machine 2 | `CPROG_SLOT_8` | 0xCA17 | 7 |
| Bass Machine 3 | `CPROG_SLOT_9` | 0xCA18 | 8 |
| Bass Machine 4 | `CPROG_SLOT_10` | 0xCA19 | 9 |
| Bass Machine 5 | `CPROG_SLOT_11` | 0xCA1A | 10 |
| Bass Machine 6 | `CPROG_SLOT_12` | 0xCA1B | 11 |

**Lead Machine 1-6** (slots 12-17) — Default: Chord layer, MIDI ch3, octave +1
| GUI Label | QMK Define | Hex | Slot Index |
|-----------|------------|-----|------------|
| Lead Machine 1 | `CPROG_SLOT_13` | 0xCA1C | 12 |
| Lead Machine 2 | `CPROG_SLOT_14` | 0xCA1D | 13 |
| Lead Machine 3 | `CPROG_SLOT_15` | 0xCA1E | 14 |
| Lead Machine 4 | `CPROG_SLOT_16` | 0xCA1F | 15 |
| Lead Machine 5 | `CPROG_SLOT_17` | 0xCA20 | 16 |
| Lead Machine 6 | `CPROG_SLOT_18` | 0xCA21 | 17 |

**Extra slots** (slots 18-19) — User-configurable
| GUI Label | QMK Define | Hex | Slot Index |
|-----------|------------|-----|------------|
| Chord Prog 19 | `CPROG_SLOT_19` | 0xCA22 | 18 |
| Chord Prog 20 | `CPROG_SLOT_20` | 0xCA23 | 19 |

### Per-Slot Config (EEPROM-persisted, 9 bytes per slot)
```c
typedef struct {
    uint8_t  key;              // Root key signature (0=C/Am .. 11=B/G#m)
    uint8_t  progression_id;   // Index into cprog_progressions[]
    uint8_t  rhythm_id;        // Index into cprog_rhythms[]
    uint8_t  voicing;          // Voice leading mode (Basic/Ascending/Descending/Random/Alternating/Tight)
    uint8_t  channel;          // MIDI channel (0-15)
    uint8_t  velocity_curve;   // 0-16 (playing style / volume curve)
    int8_t   transpose;        // Octave transpose in semitones (-36 to +36, steps of 12)
    uint8_t  humanize;         // Velocity jitter ±0-20
    uint8_t  rhythm_layer;     // Full(0) / Chord(1) / Bass(2)
} cprog_slot_config_t;
```

### Rhythm Layer System
- **Full**: plays all steps as authored (bass + chord + indexed notes)
- **Chord**: silences all `BASS_*` note-type steps, plays only chord voicings
- **Bass**: auto-derives a monophonic bass line from the rhythm's bass steps (via `cprog_derive_bass_from_rhythm()`)

### OLED Menu Structure
```
Landing Page (level 7):
  > Quick Build ->        (full progression → rhythm picker flow)
  > Prog: [name]          (opens progression category picker, returns here)
  > Rhythm: [name]        (opens rhythm genre picker, returns here)
  > Key: C/Am             (opens key picker)
  > Settings ->           (opens settings submenu)

Settings Submenu (level 13):
  > Channel: 1
  > Volume: Linear
  > Octave: 0
  > Instrument: Full      (Full / Chord / Bass)
  > Humanize: OFF
  > Voice Lead: Basic
  > Restore Defaults      (resets based on machine type: Chords/Bass/Lead)

Title bar shows: "Chords 1: [prog name]" or "Bass 2: [prog name]" etc.
```

### Progressions Database
- **318 progressions** in `cprog_progressions[]` across 11 categories:
  Basic, Medium, Hard, Jazz, Funk, Latin, R&B, Soul, Major, Minor, Modal
- Major/Minor/Modal categories (176 progressions) sourced from
  github.com/ldrolez/free-midi-chords (MIT license), mood-tagged
- Jazz standards (IDs 42-61) renamed "Jazz 1" through "Jazz 20", trimmed to 8 bars max
- Each chord has: type (e.g. `CPROG_MAJOR`, `CPROG_MIN7`), interval (semitones from root), duration (beats)
- Jazz standards also have direct-MIDI event lists for baked 8-bar accompaniments (bass + chord)
- `CPROG_MAX_CHORDS = 16` per progression (but current max used = 8)

### Rhythm Patterns
- **~198 patterns** in the `cprog_rhythms[]` array (flat array, indexed 0-197+)
- Each pattern: `{ name, step_count, pattern_beats, steps[96] }`
- Each step: `{ position (16th notes), gate_pct, velocity, note_type }`
- `pattern_beats` = length in quarter-note beats (e.g. 4 = 1 bar, 8 = 2 bars, 3 = waltz)
- Position is in 16th notes within the pattern (0-15 for a 4-beat bar)

### Rhythm Genres (alphabetized in OLED menu)
| Genre | Count | Sources |
|-------|-------|---------|
| Arpeggios | 14 | Monophonic single-note patterns |
| Afro | 9 | Collins "Highlife Time", Spiro "BatuCada", Leake |
| Basics | 15 | Foundational patterns (was "Classic") |
| Funk | 14 | Real-world transcriptions (Levine, Friedland) |
| Jazz | 30 | Levine "Jazz Piano Book", Baker + 20 jazz standard rhythms |
| Latin | 10 | Mauleón "101 Montunos", Stagnaro "Latin Bass Book" |
| Neo Soul | 11 | Martin "Neo Soul Guide" |
| Pop | 13 | Real-world transcriptions (Hal Leonard) |
| R&B | 11 | Harrison "R&B Keyboard" |
| Reggae | 9 | Hitchins "Vibe Merchants", Manuel "Caribbean Currents" |
| Basslines | 60 | Friedland "Walking Bass Lines", Rainey, Kaye |

### Note Types for Rhythm Steps
```
Chord types (polyphonic):
  CHORD_BLOCK     — all chord tones simultaneously
  CHORD_UPPER     — chord tones without root (lighter voicing)

Bass types (monophonic, all in bass register = root - 12 semitones):
  BASS_ROOT       — root
  BASS_FIFTH      — perfect 5th above root
  BASS_THIRD      — chord-aware: minor 3rd for minor/dim, major 3rd otherwise
  BASS_SECOND     — major 2nd (scale passing tone)
  BASS_FOURTH     — perfect 4th (scale passing tone)
  BASS_SIXTH      — chord-aware: minor 6th for minor, major 6th otherwise
  BASS_SEVENTH    — chord-aware: maj7 for maj7/maj9, dim7 for dim7, dom/min 7th otherwise
  BASS_OCT_UP     — root at chord register (no -12, for octave pumps / slap pops)
  BASS_APPROACH   — chromatic leading tone (root - 1 semitone)

Special:
  REST            — silence (releases prior note, plays nothing)

Individual tones:
  INDEX_0..7      — specific chord tone by index (wraps with +12 if chord is smaller)
```

### Bassline Detection
Two ranges in `cprog_rhythms[]` are detected as dedicated basslines:
- Block A: indices 67-116 (50 original genre-flavoured variants)
- Block B: indices 161-180 (20 essential basslines with extended bass types)
Function: `cprog_is_bassline_rhythm(rhythm_id)` returns true for these ranges.
When selected, plays as-is regardless of the layer setting.

### Multi-Voice Playback
Up to `CPROG_MAX_VOICES` (8) can play simultaneously. Each voice has its own:
- Chord tones, root, chord type
- Rhythm step index, repeat count, timing
- Voice leading state (anchor, previous highest/lowest)
- Direct-MIDI cursor for jazz standards
Context is swapped in/out via `cprog_voice_load()` / `cprog_voice_save()`.

---

## Step Sequencer / Drum Machine

### Architecture
- **8 simultaneous slots** (`MAX_SEQ_SLOTS`)
- **48 factory presets** (Drum Machine presets) + **40 user presets** = 88 total
- Factory melodic presets: `arp_factory_presets.c` (C Major Scale, Bass Line, Techno Kick, Melody 1)
- Factory drum presets: `seq_drum_patterns.c` (241 patterns across 25 genres)
- User presets: stored in shared pool in EEPROM (addresses 23000-35339)

### Keycodes
- Base: `SEQ_PRESET_BASE` (0xED98), offset maps to firmware ID 68+offset
- Transport: `SEQ_PLAY` (0xEE80), `SEQ_STOP_ALL` (0xEE81)
- Rate: `SEQ_RATE_QUARTER` through `SEQ_RATE_SIXTEENTH_TRIP`, `SEQ_RATE_RESET`
- Gate: `SEQ_GATE_1_UP` through `SEQ_GATE_10_DOWN`, `SEQ_GATE_RESET`
- Double time: `SEQ_DOUBLE_TIME` (0xEEAD)
- Quick build: `SEQ_QUICK_BUILD_1` through `SEQ_QUICK_BUILD_8`

### Preset Structure
```c
typedef struct {
    uint8_t preset_type;            // PRESET_TYPE_STEP_SEQUENCER
    uint8_t note_count;             // Number of notes (steps with notes)
    uint8_t pattern_length_16ths;   // Total steps in pattern (loops at this count)
    uint8_t gate_length_percent;    // Gate as % of step duration (0-100)
    uint8_t timing_mode;            // TIMING_MODE_STRAIGHT / TRIPLET / DOTTED
    uint8_t note_value;             // NOTE_VALUE_QUARTER(0) / EIGHTH(1) / SIXTEENTH(2)
    uint8_t magic;                  // ARP_PRESET_MAGIC validation
    arp_preset_note_t notes[];      // Note data (3 bytes each)
} seq_preset_t;
```

### Timing System
- `note_value` determines milliseconds per step via multiplier:
  - `NOTE_VALUE_QUARTER` (0): multiplier 4 → 500ms at 120 BPM
  - `NOTE_VALUE_EIGHTH` (1): multiplier 2 → 250ms at 120 BPM
  - `NOTE_VALUE_SIXTEENTH` (2): multiplier 1 → 125ms at 120 BPM
- Formula: `ms = step × 6,000,000,000 × multiplier / (4 × bpm)`
- `pattern_length_16ths` = number of steps (NOT actual 16th notes despite the name)
- Notes play when `unpacked.timing == current_position_16ths`

### Double Time Setting
- Global `seq_double_time` (bool) — saved in `keyboard_settings_t` EEPROM
- When ON: `seq_compute_step_time()` divides all step durations by 2 (2x speed)
- Toggle keycode: `SEQ_DOUBLE_TIME` (0xEEAD) — shows "DOUBLE TIME ON/OFF" on OLED
- Only affects step sequencer, NOT arpeggiator or chord progressions

### Runtime State (`seq_state_t`)
```c
typedef struct {
    bool active;
    bool sync_mode;
    uint8_t current_preset_id;
    uint8_t loaded_preset_id;
    uint32_t next_note_time;
    uint16_t current_position_16ths;   // Current step index (0 to pattern_length-1)
    uint8_t rate_override;             // 0=use preset, else NOTE_VALUE_* | TIMING_MODE_*
    uint8_t master_gate_override;      // 0=use preset, else 1-100%
    uint32_t pattern_start_time;
    uint8_t locked_channel;            // Captured at play start
    uint8_t locked_velocity_min;
    uint8_t locked_velocity_max;
    int8_t locked_transpose;
    uint8_t locked_velocity_curve;
    bool has_looped;
    bool deferred_start_pending;
    bool deferred_stop_pending;
    int8_t factory_seq_button;         // Which factory button owns this slot (-1=none)
} seq_state_t;
```

---

## BPM System
- Stored internally as `BPM × 100,000` (e.g. 120.00 BPM = 12,000,000)
- Range: 30-300 BPM (clamped)
- Default: 120 BPM (auto-set when chord progression starts with no clock running)
- Sources: tap tempo, MIDI clock input, USB MIDI clock, manual set
- Shared globally — seq, arp, and chord progressions all use the same clock
- Bar triggers emitted every 16 sixteenth notes (= 4 quarter beats = 1 bar) for sync

---

## Key Source Files

### Firmware (`vial-qmk - ryzen/keyboards/orthomidi5x14/`)
| File | Contents |
|------|----------|
| `orthomidi5x14.c` | Chord progression engine, OLED menu rendering + click/encoder/back handlers, voice system, keycode handlers, keyboard settings save/load |
| `orthomidi5x14.h` | All keycode defines (CPROG_SLOT_*, SEQ_*, ARP_*), struct definitions, constants |
| `chord_progressions.c` | Progression database (142 entries), rhythm patterns (~198 entries), genre tables, direct-MIDI jazz standard event arrays, `cprog_get_step_note()` resolver |
| `chord_progressions.h` | Types (`cprog_note_type_t`, `cprog_rhythm_genre_t`, slot config struct), API declarations, bassline range constants |
| `arpeggiator.c` | Arp + step sequencer playback engine, timing functions (`compute_step_time_offset`, `seq_compute_step_time`), preset loading, note-on/off scheduling |
| `arp_factory_presets.c` | 4 factory melodic seq presets + 8 factory arp presets |
| `seq_drum_patterns.c` | 241 drum patterns across 25 genres, `seq_drum_load_pattern()` |
| `seq_drum_genres.c/.h` | Genre grouping for drum pattern OLED menu |
| `process_dynamic_macro.h` | `keyboard_settings_t` (EEPROM struct with `seq_double_time` and all global settings) |

### Python GUI (`src/main/python/`)
| File | Contents |
|------|----------|
| `keycodes/keycodes.py` | Keycode definitions with GUI labels: `KEYCODES_CPROG_SLOTS` (Chord/Bass/Lead Machine labels), `KEYCODES_STEP_SEQUENCER`, `KEYCODES_STEP_SEQUENCER_PRESETS` |
| `keycodes/keycodes_v5.py` | QMK name → hex value mapping (protocol v5) |
| `keycodes/keycodes_v6.py` | QMK name → hex value mapping (protocol v6) |
| `tabbed_keycodes.py` | Tab layouts: `ChordProgressionTab`, `StepSequencerTab`, `ArpeggiatorTab` |

---

## EEPROM Layout (relevant addresses)
| Address | Size | Content |
|---------|------|---------|
| 23000-35339 | 12,340B | Arp/Seq preset pool (shared pool headers + note data) |
| 38000-39249 | 1,250B | Keyboard settings (5 slots × ~250B each, includes `seq_double_time`) |
| 45000-51719 | 6,720B | Per-key actuation configs |
| 60472-60656 | 184B | Chord progression slot configs (20 × 9B + 4B magic header) |

---

## Sync & Loop Integration
- Chord progressions emit bar triggers every 16 sixteenths via `dynamic_macro_handle_loop_trigger()`
- Step sequencer emits bar triggers at pattern loop boundaries (every `steps_per_cycle` steps)
- Deferred starts: a new seq/arp/prog can wait for the next bar boundary before starting
- Factory seq buttons support chain mode (advance to next pattern at loop boundary)
- Loop pedal integrates with the same trigger system for recording quantisation
