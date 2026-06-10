# Smartchord + Voice Leading — Phased Implementation Plan

This document captures the plan for the second, larger tranche of changes
that follows the quickbuild-menu rename / 100-slot expansion already on
branch `claude/update-quickbuild-menu-zH37z`. Smartchord work is split
into 5 sequential phases so each phase can be built, flashed, and
validated on-device before moving on.

Design decisions captured from user spec:

- Voice leading is **global**, not per-key. Holding *any* smartchord key
  opens the same global menu.
- Scales/Modes/Intervals keycodes are **immune**: they play bare, and
  when they fire they **clear the last-chord memory**.
- "Alternating" = flip direction every other smartchord press (asc,
  desc, asc, desc).
- "Tight" = minimize total semitone voice movement vs. previous chord.
- Priority list = strict ranking over the 6 voices; satisfy in order,
  drop lower-priority rules when they conflict.
- Third/Fifth/Ext1/Ext2 are positional (lowest-of-middle, 2nd lowest,
  etc.), not interval-based. Ignored if the previous chord had fewer
  middle voices.
- Smartchord buttons are modifiers: *holding* a smartchord key disables
  that modifier (so the hold-to-menu only triggers from smartchords
  routed through a QB_MASTER slot that we already own; pressing+holding
  a bare MI_CHORD key just turns the chord off per existing behavior).
- Tap-off same key = clear VL memory. Tap-off by switching to a
  different smartchord = keep VL memory.
- `Ignore Voice Leading` masters still update the last-chord memory.

---

## Phase 1 — Remove smartchord hold-mode (cleanup)

**Goal:** strip the `smartchord_mode` (0=Hold / 1=Toggle) branching that
the new voice-leading model replaces. Land this first so subsequent
phases don't need to worry about the legacy path.

- Delete all `if (smartchord_mode == 1 ...)` / `smartchord_mode == 0`
  branches in `orthomidi5x14.c` (around lines 22307, 22622, 22988 plus
  any guards elsewhere).
- Remove the variable declaration and every reference to it.
- Remove the "SmartChord Mode" row from the on-device Settings menu
  (see `SETTINGS_MENU_PLAN.md` line 245).
- Remove the GUI toggle in the MIDI-settings tab (`tabbed_keycodes.py`
  around line 770–784, plus any HID round-trip byte in
  `protocol/keyboard_comm.py`).
- Reclaim the 1 EEPROM byte previously holding `smartchord_mode` — mark
  it reserved for Phase 2's VL config. Don't bump any magic yet
  (reserved byte stays at 0, existing boards tolerate).

**Cost:** ~300–500 bytes flash reclaimed. No RAM or EEPROM growth.

**Done when:** firmware builds, toggle-mode is the only smartchord
behaviour, no regression in existing smartchord keycodes.

---

## Phase 2 — Global Voice Leading config + storage

**Goal:** add the data model and hold-to-open menu, but keep the VL
engine *off* by default. No chord-playback changes in this phase.

### EEPROM layout (new, at the reclaimed byte + extension)

```
struct __attribute__((packed)) vl_config_t {
    uint8_t  magic_lo;             // 0xVL (2-byte magic)
    uint8_t  magic_hi;
    uint8_t  voice_rule[6];        // per-voice: 0=None 1=Asc 2=Desc 3=Alt 4=Tight
    uint8_t  priority_order[6];    // voice indices ranked highest→lowest priority
    uint8_t  reserved[4];
} // = 16 bytes total
```

Voices (indices 0..5): `HIGHEST, LOWEST, THIRD, FIFTH, EXT1, EXT2`.

**Placement:** reuse the byte freed in Phase 1; extend into the
currently-unused 5.1 KB region starting at ~60285 per CLAUDE.md. New
magic (e.g. `0x56 0x4C` = "VL") so first boot of new firmware seeds
defaults cleanly.

### RAM state (new, `~20 bytes`)

```
struct last_chord_state_t {
    uint8_t  notes[6];        // MIDI note numbers of voices in last chord
    uint8_t  roles[6];        // voice index (HIGHEST..EXT2) assigned to each slot
    uint8_t  voice_count;     // 0 = memory cleared
    uint8_t  alt_state;       // for Alternating: 0 or 1, flips each press
    bool     last_was_same_keycode;  // suppress re-inversion on repeat press
    uint16_t last_keycode;
};
```

### Hold-to-open menu

- On any smartchord keycode press, start a 1 s hold timer.
- If held past 1 s: fire `smartchord_open_voice_leading_menu()` and
  cancel the note trigger.
- Menu renders two tabs:
  1. **Rules**  → one row per voice with its rule.
  2. **Priority** → drag-reorder list (encoder scroll + click toggle).
- ESC closes; changes persist immediately via `eeprom_update_byte`.
- For `QB_MASTER` smartchord masters, the menu later grows 2 extra rows
  (Phase 5). For now, hold behaviour is identical for bare MI_CHORD and
  QB_MASTER-routed smartchords.
- ESC-back integrates with existing `qb_master_post_esc_hook` so a
  QB_MASTER-invoked VL menu can route back to the master picker when
  the user wants to reassign — pattern already exists for other menus.

**Cost:** ~15 bytes EEPROM, ~20 bytes RAM, ~600 bytes flash for the
menu renderer + hold timer hook.

**Done when:** hold opens the menu, settings save/restore, no effect
on playback yet.

---

## Phase 3 — Voice Leading engine

**Goal:** wire the rules into smartchord note selection.

### Algorithm outline

```
on smartchord_press(keycode, root_note):
    if keycode is Scales/Modes/Intervals:
        play_raw(); last_chord_state = CLEARED; return

    candidate_voicings = enumerate_inversions(keycode, root_note)
        // 3-note chord → 3 voicings; 4-note → 4; etc. Each voicing is
        // a sorted list of absolute MIDI notes across the chord's
        // displayed octave range.

    if last_chord_state.voice_count == 0:
        chosen = default_voicing(root_position)
    else if last_keycode == keycode:
        chosen = last_chord_state.notes  // grace period: no re-invert
    else:
        chosen = score_and_pick(candidate_voicings, last_chord_state)

    play(chosen); update_last_chord_state(chosen, keycode)
```

### Scoring function

For each candidate voicing, compute a constraint-satisfaction score:

```
score_voicing(v, prev):
    // Iterate priority list. For each voice (H, L, 3rd, ...):
    //   if rule = None → skip
    //   if previous chord didn't have this voice → skip
    //   evaluate_rule(rule, v.voices[role], prev.voices[role])
    //     Asc:   new > prev
    //     Desc:  new < prev
    //     Alt:   direction matches alt_state, then flip
    //     Tight: always passes; accumulate |new - prev| into movement_cost
    // Return (constraints_satisfied_in_priority_order, -movement_cost)
```

Tie-break by movement cost; lowest wins among candidates with equal
priority satisfaction depth.

### Integration point

Hook `process_midi_chord()` / `midi_play_chord()` (whatever function
emits the current smartchord note set) to consult the VL engine before
sending note-on events. The engine runs in ~50 µs — no scan-cycle
concern.

### Memory tracking rules

- Tap-off same key → clear last_chord_state.
- Tap-off by switching to another smartchord → keep last_chord_state.
- Scales/Modes/Intervals → clear.
- "Ignore VL" QB_MASTER → still updates last_chord_state, but picks
  voicing from its stored inversion instead of running the scorer.

**Cost:** ~1–1.5 KB flash for scorer + candidate enumeration. Zero new
RAM (reuses state from Phase 2). Zero EEPROM.

**Done when:** Ascending/Descending/Tight/Alt/None + priority all work.
Regression test: with all rules set to None, playback is identical to
pre-Phase-1 tap-toggle behaviour.

---

## Phase 4 — Smartchord submenu in master picker

**Goal:** extend the "Smartchord" top-level row in the master picker
into 8 sub-categories so users can assign default smartchord keycodes
(0xC38B..0xC64E) to QB_MASTER slots, not just the 8 Custom QB slots.

### Sub-categories

| Sub-category  | Keycode range   | Count |
| ------------- | --------------- | ----: |
| Custom        | 0xEF8D + 0xEFF5-0xEFFB (existing QB slots) | 8 |
| Intervals     | 0xC38B-0xC395   | 11 |
| 3 Note Chords | 0xC396-0xC3A1   | 12 |
| 4 Note Chords | 0xC3A2-0xC3B1   | 16 |
| 5 Note Chords | 0xC3B2-0xC3C1   | 16 |
| 6 Note Chords | 0xC3C2-0xC3FE   | 61 |
| Extended      | 0xC3FF-0xC416   | 24 |
| Scales/Modes  | 0xC640-0xC64E   | 15 |

### Implementation

- Add `QUICK_BUILD_MASTER_SMARTCHORD_SUBMENU` state (mirror of
  `QUICK_BUILD_MASTER_BT_SUBMENU` just shipped).
- Top-level "Smartchord" row opens the 8-item sub-picker.
- Selecting one of the 7 default categories opens a scrollable chord
  picker (paged; 6-note chords alone are 61 entries — needs paging).
- Picking a chord commits `{category = SMARTCHORD_DEFAULT, slot = kc -
  CAT_BASE}` to the qb_master entry. Needs a new dedicated category
  scheme or a keycode-direct variant: storing a 16-bit absolute keycode
  per master would be cleanest but requires extending the master entry
  to 3+ bytes (coincides with Phase 5).
- "Custom" sub-option → falls through to existing Smartchord QB slot
  picker (current behaviour).

**Recommended:** defer this phase until Phase 5 lands so we only
extend `qb_master_slot_t` once.

**Cost:** ~600–800 bytes flash; no new RAM; minor EEPROM depending on
representation choice.

---

## Phase 5 — Per-QB-master inversion + Ignore-VL flag

**Goal:** let QB_MASTER-routed smartchords override VL with a fixed
inversion, and let multiple masters pointing at the same smartchord
carry different overrides.

### Extend `qb_master_slot_t`

```c
typedef struct __attribute__((packed)) {
    uint8_t category;   // unchanged
    uint8_t slot;       // unchanged
    uint8_t flags;      // bits 0-3: inversion (0=root, 1-8=positions)
                        // bit 4:    ignore_voice_leading
                        // bits 5-7: reserved
} qb_master_slot_t;   // 3 bytes
```

### EEPROM

- Current: 2 + 100×2 = 202 bytes at 60524 (post-Phase-0 expansion).
- New: 2 + 100×3 = 302 bytes. Ends at 60825. Well within the free
  region per CLAUDE.md.
- Bump `QB_MASTER_EEPROM_MAGIC` 0xDB03 → 0xDB04.
- Per user decision: **reset on magic bump, no migration.**

### Hold-menu extensions (QB_MASTER smartchord only)

Add 2 rows above the global VL menu when entered from a QB_MASTER:

- `Inversion:` Root / 1st / 2nd / ... / 8th
- `Ignore Voice Leading:` Off / On

Both persist in the master's `flags` byte. `qb_master_save_slot()` is
already per-slot so this is a 1-byte write.

### Integration

`qb_master_target_keycode()` gains a sibling
`qb_master_target_inversion(slot_id)` returning 0 (default) or 1..8.
When `process_record_user()` translates a QB_MASTER press to its
target keycode, it also pushes the override into a small RAM variable
the VL engine checks:

```
if (current_invocation_has_override):
    chosen = voicing_with_inversion(keycode, root, override)
    update_last_chord_state(chosen, keycode)   // still update memory
else:
    chosen = vl_engine_pick(...)
```

**Cost:** +100 bytes EEPROM (100 masters × 1 flag byte), +0 RAM (flags
stream from EEPROM-cached `qb_master[]`), ~300–500 bytes flash for
override plumbing.

---

## Budget summary (Phases 1–5)

| Resource | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | **Total** |
| -------- | ------: | ------: | ------: | ------: | ------: | --------: |
| Flash    | **-400** | +600 | +1200 | +700 | +400 | **~+2500 B** |
| RAM      | 0 | +20 | 0 | 0 | 0 | **+20 B** |
| EEPROM   | **-1** | +15 | 0 | 0 | +100 | **+114 B** |

All well inside headroom (~5 KB free in EEPROM, flash still has the
DAW / chord-prog gains to spare).

## Order of operations

1. **Phase 1 first** — mechanical cleanup with immediate size win.
2. **Phase 2 + 3 together** — they land the full VL system; splitting
   them leaves a broken hold-menu on-device mid-phase.
3. **Phase 5 before Phase 4** — Phase 4 depends on the extended
   `qb_master_slot_t` layout if we store absolute keycodes. If we keep
   Phase 4's storage inside the existing 2-byte layout (using category
   IDs per sub-picker instead), Phase 4 can ship independently.
4. **Phase 4 last** — cosmetic/functional expansion, doesn't block
   anything.
