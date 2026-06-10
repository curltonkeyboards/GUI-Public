# Plan: Quick Build Delay, Smart Chord & Dynamic Chord

## Overview

Three new quick build features that extend the existing quick build framework (arp/seq):

1. **Quick Build Delay** — Build delay presets on-the-fly (rate + decay selection via encoder)
2. **Quick Build Smart Chord** — Build a static chord (like a 1-step non-repeating arp, sets chordkey intervals)
3. **Quick Build Dynamic Chord** — Record a timed chord phrase with per-note velocity and dynamic timing (loop-pedal style)

---

## Feature 1: Quick Build Delay

### Concept
Press the Quick Build Delay button → OLED shows parameter selection (rate, then decay) → confirm → delay slot is active. Same OLED setup flow as arp/seq quick build but with only 2 params. No recording phase needed — delay is parameter-only.

### Parameters (setup phase, encoder cycles through options)
1. **Rate** (note value): 1/1, 1/2, 1/4, 1/8, 1/16 (same as arp/seq speed param)
2. **Decay**: Short (38%), Medium (20%), Long (11%) — 3 presets matching factory delay pattern

### How It Works
- Quick build delay configures an existing user delay slot (e.g. user slot 0 = unified index 48) with the selected params and activates it
- The delay system already has 50 user slots in RAM (`delay_system.user_configs[]`)
- On confirm: writes rate + decay into the user slot config, sets BPM-synced mode + straight timing, toggles it active
- If already built: button press toggles delay on/off
- Hold + clear modifier: erases the QB delay

### Implementation
- Extend `quick_build_mode_t` enum: add `QUICK_BUILD_DELAY_SETUP`
- Extend `quick_build_state_t`: add `setup_delay_rate` (uint8_t), `setup_delay_decay` (uint8_t)
- Add `quick_build_start_delay()` function in `arpeggiator.c`
- Reuse encoder/confirm flow from arp/seq setup (same `quick_build_handle_encoder` / `quick_build_confirm_param` pattern)
- OLED: add rendering branch in `render_quick_build_setup()` for delay title + params
- On finish: no summary screen needed (delay is instant), go straight to QUICK_BUILD_NONE and activate

### RAM Cost: ~2 bytes (2 state fields in quick_build_state_t)

---

## Feature 2: Quick Build Smart Chord

### Concept
Records chord intervals from the keyboard, writes them to `chordkey2`-`chordkey7`. This is a 1-step non-repeating arpeggiator — the chord plays instantly when any MIDI note is pressed. Uses the existing smartchord mechanism (`smartchordaddnotes()` in orthomidi5x14.c).

### Flow
1. Press Quick Build Smart Chord button → OLED: "SMART CHORD BUILD"
2. "Select root note" — play a key, then confirm with encoder click/button (same as arp root flow)
3. "Record chord tones" — user plays notes, each stored as interval from root
4. Press button again → finish: intervals written to `chordkey2`-`chordkey7`, `smartchordstatus = 1`
5. Smart chord is now active — any MIDI key plays root + intervals (existing smartchord behavior)

### Storage
- **chordkey2-chordkey7**: existing `int` globals in `orthomidi5x14.c` (6 interval slots, already in RAM)
- No new EEPROM needed — chord keys are part of `keyboard_settings_t` (saved/loaded with keyboard settings)
- Up to 6 harmony tones matching existing smartchord limit
- All chord tones get the root note's velocity (existing `smartchordaddnotes()` behavior — passes the root's velocity arg to all `midi_send_noteon_smartchord()` calls)

### Implementation
- Extend `quick_build_mode_t`: add `QUICK_BUILD_CHORD_ROOT`, `QUICK_BUILD_CHORD_RECORD`
- No setup params (no speed/gate/mode — it's an instant chord, not a pattern)
- In `quick_build_handle_note()`: store `note - root_note` into temp interval array (max 6)
- In `quick_build_finish()`: copy intervals to `chordkey2`-`chordkey7`, clear unused slots to 0
- OLED: show root note name, recorded intervals as note names, count

### RAM Cost: ~8 bytes (6-byte temp interval array + 2 bytes state)

---

## Feature 3: Quick Build Dynamic Chord

### Concept
Records a timed musical phrase (notes with individual velocities AND timing) that plays back relative to whatever MIDI note triggers it. Like a loop pedal, but stored as intervals + timestamps.

### Flow
1. Press Quick Build Dynamic Chord button → OLED: "DYN CHORD BUILD"
2. "Select root note" (same root selection flow as arp/smart chord)
3. Confirm root → "PRIMED" — OLED shows primed indicator, waiting for first note
4. Play a MIDI note → recording starts immediately (this first note included as interval=0 with its velocity)
5. Play more notes — each note-on and note-off is recorded with:
   - Timestamp (ms from recording start)
   - Interval from root (semitones)
   - Velocity (note-on) or 0 (note-off)
6. Press the Quick Build Dynamic Chord button again to stop recording:
   - **Without sustain pedal held**: phrase ends, all-notes-off appended at end timestamp → on playback, notes will release when phrase ends
   - **With sustain pedal held**: phrase ends without note-offs at the end → on playback, notes sustain until next trigger or dynamic chord mode disabled

### Playback Behavior
- Dynamic chord mode is active after build. Any MIDI note triggers the phrase.
- **Trigger note**: `transpose = trigger_note - recorded_root`
- Walk through event buffer on a timer, playing each event at its timestamp offset
- **Re-trigger**: pressing a new note while phrase is playing:
  1. Immediately send note-offs for all sounding dynamic chord notes
  2. Start new phrase from beginning, transposed to new root
- **Mode off**: pressing the QB button (when not building) toggles dynamic chord mode on/off. When toggled off, all sounding notes get note-off.

### Event Storage Format

```c
typedef struct __attribute__((packed)) {
    uint16_t timestamp_ms;    // ms offset from phrase start (0-65535 = ~65 sec max)
    int8_t   interval;        // semitones from root (-127 to +127)
    uint8_t  velocity;        // 0 = note-off, 1-127 = note-on
} dynamic_chord_event_t;      // 4 bytes per event
```

### Playback State

```c
typedef struct {
    dynamic_chord_event_t events[MAX_DYNCHORD_EVENTS];  // 128 events × 4 = 512 bytes
    uint8_t  event_count;        // Events recorded
    uint8_t  recorded_root;      // Root note used during recording
    bool     sustain_end;        // true = no note-offs at phrase end
    bool     active;             // Dynamic chord mode on/off
    bool     playing;            // Currently playing a phrase
    uint8_t  play_index;         // Current event index during playback
    uint8_t  play_root;          // Current playback transposition root
    uint32_t play_start_time;    // When current playback started
    uint32_t phrase_length_ms;   // Total phrase duration
    bool     has_build;          // A phrase has been recorded
    // Active sounding notes (for cleanup on retrigger/stop)
    uint8_t  sounding_notes[16]; // MIDI note numbers currently sounding
    uint8_t  sounding_channels[16];
    uint8_t  sounding_count;
} dynamic_chord_state_t;
```

### Leveraging Existing Frameworks
- **Recording hooks**: Same pattern as `quick_build_handle_note()` in `process_midi.c` — the existing hooks already intercept note-on events. We add a branch for dynamic chord recording that also captures note-offs and timestamps.
- **Playback tick**: Same pattern as `midi_delay_tick()` — called from scan loop, checks timer, fires events.
- **Note sending**: Uses `midi_send_noteon_smartchord()` / `midi_send_noteoff_smartchord()` — these already handle live note tracking, delay scheduling, loop recording, and LED updates.
- **OLED rendering**: Same framework as existing quick build phases.
- **Button interaction**: Same state machine pattern as arp QB (button press cycles through: start build → confirm param → finish recording → toggle playback).

### RAM Budget
| Component | Size |
|-----------|------|
| Event buffer (128 events × 4 bytes) | 512 bytes |
| Playback state | ~44 bytes |
| Sounding notes (16 × 2) | 32 bytes |
| **Total** | **~588 bytes** |

Very modest — existing macro buffers are 20KB total, note pool is 12KB.

---

## Implementation Plan (Ordered Steps)

### Step 1: Header Changes (`orthomidi5x14.h`)
- Add keycodes: `DELAY_QUICK_BUILD (0xEF8C)`, `CHORD_QUICK_BUILD (0xEF8D)`, `DYNCHORD_QUICK_BUILD (0xEF8E)`
- Extend `quick_build_mode_t` enum with new modes
- Extend `quick_build_state_t` with new fields
- Add dynamic chord type declarations

### Step 2: New File — Dynamic Chord Engine (`dynamic_chord.c` / `dynamic_chord.h`)
- Event buffer, recording functions, playback tick
- Note-on/off tracking for cleanup
- Init/reset functions

### Step 3: Quick Build State Machine Extensions (`arpeggiator.c`)
- `quick_build_start_delay()`, `quick_build_start_chord()`, `quick_build_start_dynchord()`
- Extend `quick_build_enter_recording()` for chord modes
- Extend `quick_build_finish()` for all 3 new types
- Extend `quick_build_cancel()` for cleanup
- Extend `quick_build_handle_note()` for chord interval recording
- New `quick_build_handle_note_off()` for dynamic chord (only feature that needs note-offs)
- Extend `quick_build_handle_encoder()` / `quick_build_confirm_param()` for delay params
- Extend `quick_build_is_active/setup/recording()` helper predicates

### Step 4: Keycode Handling (`orthomidi5x14.c`)
- Handle `DELAY_QUICK_BUILD`: start delay QB / toggle delay / clear
- Handle `CHORD_QUICK_BUILD`: start chord QB / toggle smartchord / clear
- Handle `DYNCHORD_QUICK_BUILD`: start dynchord QB / toggle mode / finish recording / clear
- Add LED category assignments for the 3 new keycodes

### Step 5: MIDI Hooks (`process_midi.c`)
- Add dynamic chord recording hook for note-offs (note-ons already intercepted by existing QB hook)
- Add dynamic chord playback trigger: when mode active + note-on, start phrase playback
- Hook `dynamic_chord_tick()` into the scan cycle

### Step 6: OLED Rendering (`orthomidi5x14.c`)
- Extend `render_quick_build_setup()`: delay setup screen (rate/decay params), chord root selection, dynchord root selection
- Extend `render_quick_build_recording()`: chord tone display, dynchord recording status (event count, elapsed time)
- Extend `render_quick_build_summary()`: delay confirmation, chord summary (intervals), dynchord summary (phrase length, event count)
- Add "PRIMED" indicator for dynchord primed state

### Step 7: GUI Keycodes (optional, follow-up)
- Register new keycode names in `keycodes.py` / `keycodes_v6.py`
- Add to keycode picker in `tabbed_keycodes.py`

---

## Keycode Summary

| Keycode | Value | Purpose |
|---------|-------|---------|
| `DELAY_QUICK_BUILD` | `0xEF8C` | Quick build delay (rate + decay) |
| `CHORD_QUICK_BUILD` | `0xEF8D` | Quick build smart chord (interval recording) |
| `DYNCHORD_QUICK_BUILD` | `0xEF8E` | Quick build dynamic chord (timed phrase recording) |

All 3 fit in the gap at 0xEF8C-0xEF8E (between existing keycodes 0xEF8B and 0xEF8F).

---

## Total RAM Impact

| Feature | RAM | Notes |
|---------|-----|-------|
| Delay QB | ~2 bytes | State fields only; uses existing delay_system user slot |
| Smart Chord QB | ~8 bytes | Temp interval array; writes to existing chordkey globals |
| Dynamic Chord | ~588 bytes | New event buffer + playback state |
| **Grand Total** | **~598 bytes** | < 0.6KB additional |

---

## Questions for Clarification

1. **Delay QB — single slot or multiple?** I'm proposing 1 slot since the delay system already has 50 user slots. The QB just quick-configures one. Want multiple?

2. **Dynamic chord — EEPROM persistence?** Current plan is RAM-only (matches existing QB arp/seq pattern — lost on power cycle). Want it saved to EEPROM?

3. **Dynamic chord — 128 events enough?** That's ~64 note-on + 64 note-off (a complex multi-note phrase). Need more capacity?

4. **Smart chord QB — overwrite warning?** It overwrites chordkey2-7 directly. Should it warn if smartchord is already configured, or just overwrite?

5. **Dynamic chord + arpeggiator interaction?** When dynchord mode is active and arp is also active, should dynchord take priority? I'm proposing dynchord suppresses direct note output (like arp does) but doesn't affect the arp itself.

6. **LED feedback?** Should the new QB buttons get LED category assignments for visual feedback? (Proposing yes, categories 51-53.)
