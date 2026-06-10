# Plan: Dynchord Multi-Instance + Play Modes + End Modes

## Summary

Refactor dynamic chord to support 4 play modes and 3 end modes:

**Play Modes** (per-slot, OLED menu param "Play Mode"):
- 0: Single Synced — one phrase, new key transposes at current position (continue)
- 1: Single Unsynced — one phrase, new key restarts from beginning
- 2: Chord Synced — multiple phrases, new keys start at current elapsed time
- 3: Chord Unsynced — multiple phrases, each starts independently from beginning

**End Modes** (per-slot, OLED menu param "End Mode"):
- 0: Basic — phrase ends, sounding notes stop (current default)
- 1: Loop — phrase restarts from beginning when it finishes (independent per-instance)
- 2: Sustain — don't send note-offs at phrase end; notes ring until key release or retrigger

**Remove:** `sustain_end` sustain-pedal-during-recording feature (replaced by End Mode = Sustain)

## Architecture Changes

### 1. New Instance System (dynamic_chord.c / orthomidi5x14.h)

Replace single-playback state with a multi-instance array:

```c
#define MAX_DYNCHORD_INSTANCES 8
#define MAX_SOUNDING_PER_INSTANCE 8  // 8 instances × 8 = 64 total max sounding

typedef struct {
    bool     active;
    uint8_t  play_root;
    uint8_t  trigger_note;
    uint8_t  trigger_channel;
    uint16_t play_index;
    uint32_t play_start_time;
    uint8_t  sounding_notes[MAX_SOUNDING_PER_INSTANCE];
    uint8_t  sounding_channels[MAX_SOUNDING_PER_INSTANCE];
    uint8_t  sounding_count;
} dynchord_instance_t;  // ~22 bytes per instance, 176 bytes total for 8
```

In `dynamic_chord_state_t`:
- Remove: `playing`, `play_index`, `play_root`, `play_start_time`, `trigger_note`, `trigger_channel`, `sounding_notes[]`, `sounding_channels[]`, `sounding_count`
- Remove: `synced` (bool) — replaced by play_mode
- Add: `dynchord_instance_t instances[MAX_DYNCHORD_INSTANCES]`
- Add: `uint8_t play_mode` (0-3)
- Add: `uint8_t end_mode` (0-2)

### 2. Enum Definitions (orthomidi5x14.h)

```c
typedef enum {
    DYNCHORD_PLAY_SINGLE_SYNCED = 0,
    DYNCHORD_PLAY_SINGLE_UNSYNCED = 1,
    DYNCHORD_PLAY_CHORD_SYNCED = 2,
    DYNCHORD_PLAY_CHORD_UNSYNCED = 3,
} dynchord_play_mode_t;

typedef enum {
    DYNCHORD_END_BASIC = 0,
    DYNCHORD_END_LOOP = 1,
    DYNCHORD_END_SUSTAIN = 2,
} dynchord_end_mode_t;
```

### 3. Trigger Logic (dynamic_chord.c: `dynamic_chord_trigger()`)

**Single Synced (mode 0):** If already playing, kill existing instance sounding notes, update its root. If not playing, start new instance.

**Single Unsynced (mode 1):** Kill existing instance, start new instance from beginning.

**Chord Synced (mode 2):** Start a new instance for this key. Set its `play_start_time` to the FIRST active instance's start time (so it syncs to the same elapsed position). Set `play_index` by scanning forward to find the right event index for the current elapsed time.

**Chord Unsynced (mode 3):** Start a new instance for this key from beginning (play_index=0, play_start_time=now).

### 4. Tick Logic (dynamic_chord.c: `dynamic_chord_tick()`)

Loop over all active instances. For each:
- Calculate elapsed time from that instance's `play_start_time`
- Process events up to elapsed time
- When phrase completes:
  - **End Basic:** Send note-offs, deactivate instance
  - **End Loop:** Reset `play_index=0`, `play_start_time=now`, continue
  - **End Sustain:** Leave notes ringing, deactivate instance (notes cleaned up on key release)

### 5. Note-Off / Handle Release (dynamic_chord.c: `dynamic_chord_handle_note_off()`)

**Single modes (0, 1):** Same as current — fallback to previous held note or stop.

**Chord modes (2, 3):** Find the instance with `trigger_note == note`, kill its sounding notes, deactivate it. Other instances continue unaffected.

### 6. Remove sustain_end Feature

**Files to modify:**
- `orthomidi5x14.h`: Remove `sustain_end` from `dynamic_chord_phrase_t`, remove `dynchord_sustain_end` from `quick_build_state_t`
- `arpeggiator.c`: Remove `get_live_sustain_state()` call on recording end (~line 3667-3668), remove `sustain_end` logic in `quick_build_finish()` (~line 3677)
- `dynamic_chord.c`: Remove all `sustain_end` checks in tick and handle_note_off

### 7. Quick Build State Changes (orthomidi5x14.h / arpeggiator.c)

In `quick_build_state_t`:
- `setup_dynchord_mode` range expands to 0-3
- Add `setup_dynchord_end_mode` (0-2)
- `saved_dynchord_mode[4]` range expands to 0-3
- Add `saved_dynchord_end_mode[4]`
- Remove `dynchord_sustain_end`

### 8. OLED Menu Changes (arpeggiator.c)

**Param count:** Change from 1 to 2 (Play Mode + End Mode)

**Play Mode menu (param 0):**
- Names: `{"Sng Sync", "Sng Unsync", "Chd Sync", "Chd Unsync"}`
- Param name: "Play Mode"
- Description: "How chord responds to" / "multiple keys held"
- `NUM_DYNCHORD_MODES` → 4

**End Mode menu (param 1):**
- Names: `{"Basic", "Loop", "Sustain"}`
- Param name: "End Mode"
- Description: "What happens when" / "phrase ends"
- `NUM_DYNCHORD_END_MODES` → 3

**Cycle handler:** Two params now — mode cycles 0-3, end mode cycles 0-2

**Confirm handler:** Advance param index; on last param, enter root phase

### 9. Activation Path Updates

Both activation paths (orthomidi5x14.c:16338 and arpeggiator.c:quick_build_finish):
- Set `dynchord_state.play_mode` from `saved_dynchord_mode[slot]`
- Set `dynchord_state.end_mode` from `saved_dynchord_end_mode[slot]`
- Remove `synced` bool assignment

### 10. Helper Functions

- `dynchord_find_instance(note, channel)` — find instance by trigger note
- `dynchord_alloc_instance()` — find free instance slot
- `dynchord_kill_instance(idx)` — send note-offs for instance, deactivate
- `dynchord_kill_all_instances()` — replaces `dynamic_chord_all_notes_off()` + clears all
- `dynchord_is_any_playing()` — check if any instance active (replaces `playing` bool)
- `dynchord_seek_to_time(instance, elapsed_ms)` — advance play_index to correct position for synced chord mode

### 11. RAM Impact

Current: ~115 bytes
New: ~36 (phrases) + 1 (active) + 1 (active_slot) + 1 (play_mode) + 1 (end_mode) + 33 (held) + 176 (8 instances × 22 bytes) = ~249 bytes
Delta: +134 bytes (very manageable)

### 12. About MAX_SOUNDING

8 sounding notes per instance × 8 instances = 64 max total. Each sounding entry is 2 bytes (note + channel). The only cost of increasing is RAM (trivial at these sizes) and the linear scan in note-off cleanup (also trivial). No performance concern.

## File Change Summary

| File | Changes |
|------|---------|
| `orthomidi5x14.h` | New enums, instance struct, update state struct, update QB state |
| `dynamic_chord.c` | Rewrite trigger/tick/note-off for multi-instance, remove sustain_end |
| `arpeggiator.c` | OLED menu: 2 params, 4 play modes, 3 end modes; update finish/save |
| `orthomidi5x14.c` | Update activation to set play_mode + end_mode |

## Implementation Order

1. Define new types/structs in orthomidi5x14.h
2. Remove sustain_end from phrase struct and all references
3. Rewrite dynamic_chord.c with instance system
4. Update quick_build_state_t and OLED menu in arpeggiator.c
5. Update activation paths in orthomidi5x14.c and arpeggiator.c
6. Update seed_held_from_live and other callers for new API
