# SPDX-License-Identifier: GPL-2.0-or-later
"""Keymap tuning presets for the orthomidi5x14 keyboard (5 rows x 14 columns).

Each preset defines a musical tuning layout mapping MIDI note keycodes
to the 70-key grid. Presets are designed for different playing styles
and musical theory concepts.

Grid convention:
  - Row 0 = top row (visually / matrix), Row 4 = bottom row
  - User-facing labels use 1-5 (Row 1 = top, Row 5 = bottom)
  - Lower notes are placed at the bottom, higher at top
  - Col 0 = leftmost, Col 13 = rightmost

Preset types:
  - TUNING: Multi-row note layouts that scale to selected rows
  - SINGLE_ROW: Function key rows (loop, arp, etc.) applied to one row
  - ENCODER: Encoder assignments (separate from the grid)

Zone prefixes:
  - Base zone:       MI_*        (e.g. MI_C_3)
  - KeySplit zone:   MI_SPLIT_*  (e.g. MI_SPLIT_C_3)
  - TripleSplit zone: MI_SPLIT2_* (e.g. MI_SPLIT2_C_3)
"""

# Chromatic note names matching QMK MI_* keycode naming
CHROMATIC_NAMES = ['C', 'Cs', 'D', 'Ds', 'E', 'F', 'Fs', 'G', 'Gs', 'A', 'As', 'B']

ROWS = 5
COLS = 14

# Preset type constants
PRESET_TYPE_TUNING = "tuning"
PRESET_TYPE_SINGLE_ROW = "single_row"
PRESET_TYPE_KEYBOARD = "keyboard"


# ── Helper Functions ──────────────────────────────────────────────────────────


def note_to_keycode(note_index, zone="base"):
    """Convert 0-71 note index to MI_* keycode string.

    Note indices: 0=C0, 1=C#0, ..., 11=B0, 12=C1, ..., 71=B5.
    zone: "base" for MI_*, "ks" for MI_SPLIT_*, "ts" for MI_SPLIT2_*
    Returns KC_NO if out of the valid 0-71 range.
    """
    if note_index < 0 or note_index > 71:
        return "KC_NO"
    octave = note_index // 12
    note = note_index % 12
    name = CHROMATIC_NAMES[note]
    if zone == "ks":
        prefix = "MI_SPLIT_"
    elif zone == "ts":
        prefix = "MI_SPLIT2_"
    else:
        prefix = "MI_"
    if octave == 0:
        return "{}{}".format(prefix, name)
    return "{}{}_{}".format(prefix, name, octave)


def _remap_to_zone(keycode, zone):
    """Remap a MI_* note keycode to keysplit or triplesplit zone."""
    if keycode == "KC_NO" or zone == "base":
        return keycode
    if not keycode.startswith("MI_") or keycode.startswith("MI_SPLIT"):
        return keycode
    suffix = keycode[3:]  # strip "MI_"
    if zone == "ks":
        return "MI_SPLIT_" + suffix
    elif zone == "ts":
        return "MI_SPLIT2_" + suffix
    return keycode


def _make_grid(num_rows):
    """Create a num_rows x 14 grid filled with KC_NO."""
    return [["KC_NO"] * COLS for _ in range(num_rows)]


def _fill_grid_continuous(notes, num_rows):
    """Fill grid bottom-to-top, left-to-right with given note indices."""
    grid = _make_grid(num_rows)
    idx = 0
    for row in range(num_rows - 1, -1, -1):  # bottom to top
        for col in range(COLS):
            if idx < len(notes):
                grid[row][col] = note_to_keycode(notes[idx])
                idx += 1
    return grid


def _generate_scale_notes(root, intervals, start_octave=1, end_octave=5):
    """Generate all note indices for a scale across an octave range."""
    notes = []
    for octave in range(start_octave, end_octave + 1):
        for interval in intervals:
            note = octave * 12 + root + interval
            if 0 <= note <= 71:
                notes.append(note)
    return sorted(notes)


# ── Zone Mapping Helpers ──────────────────────────────────────────────────────


def _apply_zone_lr(grid, split_col=7):
    """Left/Right KeySplit: left cols = base, right cols = KS."""
    for row in grid:
        for col in range(split_col, len(row)):
            row[col] = _remap_to_zone(row[col], "ks")
    return grid


def _apply_zone_tb(grid):
    """Top/Bottom KeySplit: bottom rows = base, top rows = KS."""
    split_row = len(grid) // 2
    for r in range(0, split_row):
        for col in range(len(grid[r])):
            grid[r][col] = _remap_to_zone(grid[r][col], "ks")
    return grid


def _apply_zone_triple(grid, split_col=7):
    """TripleSplit: top rows = base, bottom-left = KS, bottom-right = TS."""
    split_row = len(grid) // 2
    for r in range(split_row, len(grid)):
        for col in range(len(grid[r])):
            if col < split_col:
                grid[r][col] = _remap_to_zone(grid[r][col], "ks")
            else:
                grid[r][col] = _remap_to_zone(grid[r][col], "ts")
    return grid


# ── Piano Helpers ─────────────────────────────────────────────────────────────


def _piano_white_row(start_octave, zone="base"):
    """Generate 14 white keys covering 2 octaves of naturals."""
    major = [0, 2, 4, 5, 7, 9, 11]
    row = []
    for oct_offset in range(2):
        octave = start_octave + oct_offset
        for interval in major:
            note = octave * 12 + interval
            row.append(note_to_keycode(note, zone))
    return row


def _piano_black_row_left(start_octave, zone="base"):
    """Black key row, left-aligned: C# above C column.

    Pattern per octave (7 cols):
      col 0=C#, 1=D#, 2=--, 3=F#, 4=G#, 5=A#, 6=--
    """
    row = ["KC_NO"] * 14
    sharps_at_col = [0, 1, 3, 4, 5]
    sharp_semitones = [1, 3, 6, 8, 10]
    for oct_offset in range(2):
        octave = start_octave + oct_offset
        base_col = oct_offset * 7
        for i, col_off in enumerate(sharps_at_col):
            note = octave * 12 + sharp_semitones[i]
            row[base_col + col_off] = note_to_keycode(note, zone)
    return row


def _piano_black_row_right(start_octave, zone="base"):
    """Black key row, right-aligned: C# above D column.

    Pattern per octave (7 cols):
      col 0=--, 1=C#, 2=D#, 3=--, 4=F#, 5=G#, 6=A#
    """
    row = ["KC_NO"] * 14
    sharps_at_col = [1, 2, 4, 5, 6]
    sharp_semitones = [1, 3, 6, 8, 10]
    for oct_offset in range(2):
        octave = start_octave + oct_offset
        base_col = oct_offset * 7
        for i, col_off in enumerate(sharps_at_col):
            note = octave * 12 + sharp_semitones[i]
            row[base_col + col_off] = note_to_keycode(note, zone)
    return row


# ── Tuning Preset Generators ─────────────────────────────────────────────────
# All tuning generators accept num_rows (1-5) and scale accordingly.


def preset_chromatic(num_rows=5):
    """Linear chromatic: every semitone from C1 upward."""
    notes = list(range(12, 72))  # C1 through B5 (60 notes)
    return _fill_grid_continuous(notes, num_rows)


def preset_octave_rows(num_rows=5):
    """Each row is one complete chromatic octave starting on C."""
    grid = _make_grid(num_rows)
    for i in range(num_rows):
        row = num_rows - 1 - i
        octave = i + 1
        base = octave * 12
        for col in range(12):
            note = base + col
            if note <= 71:
                grid[row][col] = note_to_keycode(note)
    return grid


def preset_guitar_standard(num_rows=5):
    """Standard guitar tuning: EADGB strings from bottom to top."""
    all_bases = [16, 21, 26, 31, 35]
    bases = all_bases[:num_rows]
    grid = _make_grid(num_rows)
    for i, base in enumerate(bases):
        row = num_rows - 1 - i
        for col in range(COLS):
            grid[row][col] = note_to_keycode(base + col)
    return grid


def preset_guitar_fourths(num_rows=5):
    """All-fourths tuning: EADGC strings from bottom to top."""
    grid = _make_grid(num_rows)
    for i in range(num_rows):
        row = num_rows - 1 - i
        base = 16 + i * 5
        for col in range(COLS):
            grid[row][col] = note_to_keycode(base + col)
    return grid


def preset_wicki_hayden(num_rows=5):
    """Wicki-Hayden isomorphic layout.
    Columns: +2 (whole tone). Rows up: +5 (perfect fourth)."""
    grid = _make_grid(num_rows)
    base = 24  # C2
    for i in range(num_rows):
        row = num_rows - 1 - i
        row_base = base + i * 5
        for col in range(COLS):
            grid[row][col] = note_to_keycode(row_base + col * 2)
    return grid


def preset_janko(num_rows=5):
    """Janko keyboard isomorphic layout.
    Whole tones per row, odd rows offset by one semitone."""
    grid = _make_grid(num_rows)
    for i in range(num_rows):
        row = num_rows - 1 - i
        pair = i // 2
        offset = i % 2
        base = 24 + pair * 12 + offset
        for col in range(COLS):
            grid[row][col] = note_to_keycode(base + col * 2)
    return grid


def preset_c_major(num_rows=5):
    """C Major diatonic scale with overlapping octave rows."""
    major = [0, 2, 4, 5, 7, 9, 11]
    grid = _make_grid(num_rows)
    for i in range(num_rows):
        row = num_rows - 1 - i
        start_octave = i + 1
        notes = _generate_scale_notes(0, major, start_octave, start_octave + 1)
        for col in range(min(COLS, len(notes))):
            grid[row][col] = note_to_keycode(notes[col])
    return grid


def preset_fifths(num_rows=5):
    """Chromatic rows separated by perfect fifths (+7 semitones)."""
    grid = _make_grid(num_rows)
    base = 12  # C1
    for i in range(num_rows):
        row = num_rows - 1 - i
        row_base = base + i * 7
        for col in range(COLS):
            grid[row][col] = note_to_keycode(row_base + col)
    return grid


def preset_major_thirds(num_rows=5):
    """Chromatic rows separated by major thirds (+4 semitones)."""
    grid = _make_grid(num_rows)
    base = 12  # C1
    for i in range(num_rows):
        row = num_rows - 1 - i
        row_base = base + i * 4
        for col in range(COLS):
            grid[row][col] = note_to_keycode(row_base + col)
    return grid


# ── Piano Presets ─────────────────────────────────────────────────────────────
# Row 0,2 = black keys (sharps), Row 1,3 = white keys (naturals), Row 4 = extra


def _build_piano(black_row_fn, num_rows=5):
    """Build piano layout with the given black key row function.

    Layout (5 rows):
      Row 0 (black): sharps for octaves 3-4
      Row 1 (white): naturals for octaves 3-4
      Row 2 (black): sharps for octaves 1-2
      Row 3 (white): naturals for octaves 1-2
      Row 4 (white): naturals for octave 5
    """
    grid = _make_grid(num_rows)

    if num_rows >= 4:
        # Lower pair (rows 2-3): octaves 1-2
        grid[3] = _piano_white_row(1)
        grid[2] = black_row_fn(1)
        # Upper pair (rows 0-1): octaves 3-4
        grid[1] = _piano_white_row(3)
        grid[0] = black_row_fn(3)
        if num_rows == 5:
            # Extra white row at bottom: octave 5
            major = [0, 2, 4, 5, 7, 9, 11]
            for idx, interval in enumerate(major):
                note = 5 * 12 + interval
                if note <= 71:
                    grid[4][idx] = note_to_keycode(note)
    elif num_rows == 3:
        grid[2] = _piano_white_row(1)
        grid[1] = black_row_fn(1)
        grid[0] = _piano_white_row(3)
    elif num_rows == 2:
        grid[1] = _piano_white_row(2)
        grid[0] = black_row_fn(2)
    elif num_rows == 1:
        grid[0] = _piano_white_row(2)
    return grid


def preset_piano_left(num_rows=5):
    """Piano (left-aligned): C# sits above C column."""
    return _build_piano(_piano_black_row_left, num_rows)


def preset_piano_right(num_rows=5):
    """Piano (right-aligned): C# sits above D column."""
    return _build_piano(_piano_black_row_right, num_rows)


# ── KeySplit (KS) Presets ─────────────────────────────────────────────────────


def preset_chromatic_ks(num_rows=5):
    """Chromatic with left/right KeySplit."""
    return _apply_zone_lr(preset_chromatic(num_rows))


def preset_octave_rows_ks(num_rows=5):
    """Octave Rows with left/right KeySplit."""
    return _apply_zone_lr(preset_octave_rows(num_rows))


def preset_guitar_standard_ks(num_rows=5):
    """Guitar Standard with left/right KeySplit."""
    return _apply_zone_lr(preset_guitar_standard(num_rows))


def preset_c_major_ks_lr(num_rows=5):
    """C Major with left/right KeySplit."""
    return _apply_zone_lr(preset_c_major(num_rows))


def preset_c_major_ks_tb(num_rows=5):
    """C Major with top/bottom KeySplit. Bottom = base, top = KS."""
    return _apply_zone_tb(preset_c_major(num_rows))


def preset_fifths_ks(num_rows=5):
    """Fifths with left/right KeySplit."""
    return _apply_zone_lr(preset_fifths(num_rows))


def preset_piano_left_ks(num_rows=5):
    """Piano Left-aligned with left/right KeySplit."""
    return _apply_zone_lr(preset_piano_left(num_rows))


def preset_piano_right_ks(num_rows=5):
    """Piano Right-aligned with left/right KeySplit."""
    return _apply_zone_lr(preset_piano_right(num_rows))


# ── TripleSplit (TS) Presets ──────────────────────────────────────────────────


def preset_chromatic_ts(num_rows=5):
    """Chromatic with TripleSplit: top=base, bottom-left=KS, bottom-right=TS."""
    return _apply_zone_triple(preset_chromatic(num_rows))


def preset_octave_rows_ts(num_rows=5):
    """Octave Rows with TripleSplit."""
    return _apply_zone_triple(preset_octave_rows(num_rows))


def preset_guitar_standard_ts(num_rows=5):
    """Guitar Standard with TripleSplit."""
    return _apply_zone_triple(preset_guitar_standard(num_rows))


def preset_c_major_ts(num_rows=5):
    """C Major with TripleSplit: top=base, bottom-left=KS, bottom-right=TS."""
    return _apply_zone_triple(preset_c_major(num_rows))


def preset_fifths_ts(num_rows=5):
    """Fifths with TripleSplit."""
    return _apply_zone_triple(preset_fifths(num_rows))


# ── Single-Row Function Presets ───────────────────────────────────────────────
# Each returns a single list of 14 keycodes.


def preset_row_loop_control():
    """Loop/macro control row."""
    return [
        "DM_MACRO_1", "DM_MACRO_2", "DM_MACRO_3", "DM_MACRO_4",
        "DM_MUTE", "DM_OVERDUB", "DM_PLAY_PAUSE", "DM_UNSYNC",
        "DM_SPEED_ALL", "DM_SLOW_ALL", "DM_RESET_SPEED",
        "DM_SAVE_ALL", "DM_COPY", "DM_SAMPLE",
    ]


def preset_row_smart_chord():
    """Smart chord row - 13 chord presets + cycle down."""
    return [
        "MI_CHORD_0", "MI_CHORD_1", "MI_CHORD_2", "MI_CHORD_3",
        "MI_CHORD_4", "MI_CHORD_5", "MI_CHORD_6", "MI_CHORD_7",
        "MI_CHORD_8", "MI_CHORD_9", "MI_CHORD_10", "MI_CHORD_11",
        "MI_CHORD_12", "SMARTCHORD_DOWN",
    ]


def preset_row_arpeggiator():
    """Arpeggiator control row."""
    return [
        "ARP_PLAY", "ARP_NEXT_PRESET", "ARP_PREV_PRESET",
        "ARP_RATE_UP", "ARP_RATE_DOWN", "ARP_GATE_UP", "ARP_GATE_DOWN",
        "ARP_RATE_EIGHTH", "ARP_RATE_SIXTEENTH", "ARP_RATE_QUARTER",
        "ARP_MODE_SINGLE", "ARP_MODE_CHORD_BASIC",
        "ARP_SYNC_MODE", "ARP_RESET_OVERRIDES",
    ]


def preset_row_step_sequencer():
    """Step sequencer control row."""
    return [
        "SEQ_PLAY", "SEQ_STOP_ALL", "SEQ_NEXT_PRESET", "SEQ_PREV_PRESET",
        "SEQ_RATE_UP", "SEQ_RATE_DOWN", "SEQ_GATE_UP", "SEQ_GATE_DOWN",
        "SEQ_RATE_EIGHTH", "SEQ_RATE_SIXTEENTH", "SEQ_RATE_QUARTER",
        "SEQ_SYNC_MODE", "SEQ_RESET_OVERRIDES",
    ]


def preset_row_ear_training():
    """Ear training row - grouped by type, levels 1-3."""
    return [
        "MI_ET_1", "MI_ET_2", "MI_ET_13",
        "MI_ET_4", "MI_ET_5", "MI_ET_14",
        "MI_ET_7", "MI_ET_8", "MI_ET_15",
        "MI_ET_10", "MI_ET_11", "MI_ET_16",
        "KC_NO", "KC_NO",
    ]


def preset_row_chord_training():
    """Chord training row - grouped by type, levels 1-4."""
    return [
        "MI_CET_1", "MI_CET_6", "MI_CET_11", "MI_CET_16",
        "MI_CET_2", "MI_CET_7", "MI_CET_12", "MI_CET_17",
        "MI_CET_3", "MI_CET_8", "MI_CET_13", "MI_CET_18",
        "MI_CET_4", "MI_CET_9",
    ]


def preset_row_transport():
    """Transport / utility control row."""
    return [
        "MI_ALLOFF", "MI_SUS", "MI_SOFT", "MI_SOST",
        "MI_PORT", "MI_LEG",
        "MI_OCTU", "MI_OCTD", "MI_TRNSU", "MI_TRNSD",
        "MI_CHU", "MI_CHD", "MI_BENDU", "MI_BENDD",
    ]


# ── Encoder Presets ───────────────────────────────────────────────────────────
# Each entry: (name, description, enc1_cw, enc1_ccw, enc1_press,
#              enc2_cw, enc2_ccw, enc2_press)

INDIVIDUAL_ENCODER_PRESETS = [
    # Each entry: (name, description, enc_cw, enc_ccw, enc_press)
    (
        "Volume",
        "Volume Up/Down, press for Mute.",
        "KC_VOLU", "KC_VOLD", "KC_MUTE",
    ),
    (
        "Octave",
        "Octave Up/Down, press for All Notes Off.",
        "MI_OCTU", "MI_OCTD", "MI_ALLOFF",
    ),
    (
        "Transpose",
        "Transpose Up/Down, press for Reset.",
        "MI_TRNSU", "MI_TRNSD", "MI_TRNS_0",
    ),
    (
        "BPM",
        "BPM Up/Down, press for Play/Pause.",
        "BPM_UP", "BPM_DOWN", "DM_PLAY_PAUSE",
    ),
    (
        "Arp Rate",
        "Arp Rate Up/Down, press for Arp Play.",
        "ARP_RATE_UP", "ARP_RATE_DOWN", "ARP_PLAY",
    ),
    (
        "Program Change",
        "Program Change Up/Down, press for All Notes Off.",
        "MI_PROG_UP", "MI_PROG_DWN", "MI_ALLOFF",
    ),
    (
        "Bank Select",
        "Bank Up/Down, press for Mute.",
        "MI_BANK_UP", "MI_BANK_DWN", "KC_MUTE",
    ),
    (
        "MIDI Channel",
        "MIDI Channel Up/Down, press for All Notes Off.",
        "MI_CHU", "MI_CHD", "MI_ALLOFF",
    ),
    (
        "Velocity",
        "Velocity Up/Down, press for Mute.",
        "MI_VELOCITY_UP", "MI_VELOCITY_DOWN", "KC_MUTE",
    ),
    (
        "Pitch Bend",
        "Pitch Bend Up/Down, press for All Notes Off.",
        "MI_BENDU", "MI_BENDD", "MI_ALLOFF",
    ),
    (
        "Mod Wheel",
        "Mod Speed Up/Down, press for Mod toggle.",
        "MI_MODSU", "MI_MODSD", "MI_MOD",
    ),
]

ENCODER_PRESETS = [
    (
        "Volume + Octave",
        "Enc 1: Volume Up/Down/Mute. Enc 2: Octave Up/Down/All Notes Off.",
        "KC_VOLU", "KC_VOLD", "KC_MUTE",
        "MI_OCTU", "MI_OCTD", "MI_ALLOFF",
    ),
    (
        "Octave + Transpose",
        "Enc 1: Octave Up/Down/All Notes Off. Enc 2: Transpose Up/Down/Reset.",
        "MI_OCTU", "MI_OCTD", "MI_ALLOFF",
        "MI_TRNSU", "MI_TRNSD", "MI_TRNS_0",
    ),
    (
        "BPM + Arp Rate",
        "Enc 1: BPM Up/Down/Play-Pause. Enc 2: Arp Rate Up/Down/Play.",
        "BPM_UP", "BPM_DOWN", "DM_PLAY_PAUSE",
        "ARP_RATE_UP", "ARP_RATE_DOWN", "ARP_PLAY",
    ),
    (
        "Program + Bank",
        "Enc 1: Program Change Up/Down/All Off. Enc 2: Bank Up/Down/Mute.",
        "MI_PROG_UP", "MI_PROG_DWN", "MI_ALLOFF",
        "MI_BANK_UP", "MI_BANK_DWN", "KC_MUTE",
    ),
    (
        "Channel + Velocity",
        "Enc 1: MIDI Channel Up/Down/All Off. Enc 2: Velocity Up/Down/Mute.",
        "MI_CHU", "MI_CHD", "MI_ALLOFF",
        "MI_VELOCITY_UP", "MI_VELOCITY_DOWN", "KC_MUTE",
    ),
    (
        "Pitch Bend + Mod",
        "Enc 1: Pitch Bend Up/Down/All Off. Enc 2: Mod Speed Up/Down/Mod.",
        "MI_BENDU", "MI_BENDD", "MI_ALLOFF",
        "MI_MODSU", "MI_MODSD", "MI_MOD",
    ),
]


# ── Keyboard Layout Presets ──────────────────────────────────────────────────
# Standard keyboard layouts mapped to the 5x14 ortholinear grid.
# Row 0 = number row, Row 1 = top alpha, Row 2 = home row,
# Row 3 = bottom alpha, Row 4 = modifier/space row.


def preset_keyboard_qwerty(num_rows=5):
    """Standard QWERTY keyboard layout for 5x14 ortholinear grid."""
    full_grid = [
        # Row 0: Number row
        ["KC_ESCAPE", "KC_1", "KC_2", "KC_3", "KC_4", "KC_5",
         "KC_6", "KC_7", "KC_8", "KC_9", "KC_0", "KC_MINUS",
         "KC_EQUAL", "KC_BSPACE"],
        # Row 1: QWERTY row
        ["KC_TAB", "KC_Q", "KC_W", "KC_E", "KC_R", "KC_T",
         "KC_Y", "KC_U", "KC_I", "KC_O", "KC_P", "KC_LBRACKET",
         "KC_RBRACKET", "KC_DELETE"],
        # Row 2: Home row
        ["KC_CAPSLOCK", "KC_A", "KC_S", "KC_D", "KC_F", "KC_G",
         "KC_H", "KC_J", "KC_K", "KC_L", "KC_SCOLON", "KC_QUOTE",
         "KC_NONUS_HASH", "KC_ENTER"],
        # Row 3: Bottom alpha row
        ["KC_LSHIFT", "KC_LSHIFT", "KC_Z", "KC_X", "KC_C", "KC_V",
         "KC_B", "KC_N", "KC_M", "KC_COMMA", "KC_DOT", "KC_SLASH",
         "KC_UP", "KC_GRAVE"],
        # Row 4: Modifier/space row
        ["KC_LCTRL", "KC_LGUI", "KC_LALT", "KC_SPACE", "KC_SPACE",
         "KC_SPACE", "KC_SPACE", "KC_SPACE", "KC_RALT",
         "KC_APPLICATION", "KC_RCTRL", "KC_LEFT", "KC_DOWN", "KC_RIGHT"],
    ]
    if num_rows >= 5:
        return full_grid
    # For partial rows, return bottom-up slice (most useful rows first)
    return full_grid[5 - num_rows:]


def preset_keyboard_qwerty_split(num_rows=5):
    """QWERTY Split: left hand letters on left, right hand on right,
    modifiers (Tab, Caps, etc.) in the center two columns."""
    full_grid = [
        # Row 0: Numbers split with Esc/Bksp in center
        ["KC_1", "KC_2", "KC_3", "KC_4", "KC_5", "KC_ESCAPE",
         "KC_BSPACE", "KC_6", "KC_7", "KC_8", "KC_9", "KC_0",
         "KC_MINUS", "KC_EQUAL"],
        # Row 1: QWERT | Tab Del | YUIOP
        ["KC_Q", "KC_W", "KC_E", "KC_R", "KC_T", "KC_TAB",
         "KC_DELETE", "KC_Y", "KC_U", "KC_I", "KC_O", "KC_P",
         "KC_LBRACKET", "KC_RBRACKET"],
        # Row 2: ASDFG | Caps # | HJKL;' Enter
        ["KC_A", "KC_S", "KC_D", "KC_F", "KC_G", "KC_CAPSLOCK",
         "KC_NONUS_HASH", "KC_H", "KC_J", "KC_K", "KC_L", "KC_SCOLON",
         "KC_QUOTE", "KC_ENTER"],
        # Row 3: ZXCVB | Shift Shift | NM,./
        ["KC_LSHIFT", "KC_Z", "KC_X", "KC_C", "KC_V", "KC_LSHIFT",
         "KC_RSHIFT", "KC_B", "KC_N", "KC_M", "KC_COMMA", "KC_DOT",
         "KC_SLASH", "KC_GRAVE"],
        # Row 4: Modifiers and space
        ["KC_LCTRL", "KC_LGUI", "KC_LALT", "KC_SPACE", "KC_SPACE",
         "KC_APPLICATION", "KC_SPACE", "KC_SPACE", "KC_SPACE",
         "KC_RALT", "KC_RCTRL", "KC_LEFT", "KC_DOWN", "KC_RIGHT"],
    ]
    if num_rows >= 5:
        return full_grid
    return full_grid[5 - num_rows:]


def preset_keyboard_dvorak(num_rows=5):
    """Dvorak keyboard layout for 5x14 ortholinear grid."""
    full_grid = [
        # Row 0: Number row (Dvorak swaps some punctuation)
        ["KC_ESCAPE", "KC_1", "KC_2", "KC_3", "KC_4", "KC_5",
         "KC_6", "KC_7", "KC_8", "KC_9", "KC_0", "KC_LBRACKET",
         "KC_RBRACKET", "KC_BSPACE"],
        # Row 1: ',.PYFGCRL/=
        ["KC_TAB", "KC_QUOTE", "KC_COMMA", "KC_DOT", "KC_P", "KC_Y",
         "KC_F", "KC_G", "KC_C", "KC_R", "KC_L", "KC_SLASH",
         "KC_EQUAL", "KC_DELETE"],
        # Row 2: AOEUIDHTNS-
        ["KC_CAPSLOCK", "KC_A", "KC_O", "KC_E", "KC_U", "KC_I",
         "KC_D", "KC_H", "KC_T", "KC_N", "KC_S", "KC_MINUS",
         "KC_NONUS_HASH", "KC_ENTER"],
        # Row 3: ;QJKXBMWVZ
        ["KC_LSHIFT", "KC_LSHIFT", "KC_SCOLON", "KC_Q", "KC_J", "KC_K",
         "KC_X", "KC_B", "KC_M", "KC_W", "KC_V", "KC_Z",
         "KC_UP", "KC_GRAVE"],
        # Row 4: Modifiers and space
        ["KC_LCTRL", "KC_LGUI", "KC_LALT", "KC_SPACE", "KC_SPACE",
         "KC_SPACE", "KC_SPACE", "KC_SPACE", "KC_RALT",
         "KC_APPLICATION", "KC_RCTRL", "KC_LEFT", "KC_DOWN", "KC_RIGHT"],
    ]
    if num_rows >= 5:
        return full_grid
    return full_grid[5 - num_rows:]


def preset_keyboard_colemak(num_rows=5):
    """Colemak keyboard layout for 5x14 ortholinear grid."""
    full_grid = [
        # Row 0: Number row (same as QWERTY)
        ["KC_ESCAPE", "KC_1", "KC_2", "KC_3", "KC_4", "KC_5",
         "KC_6", "KC_7", "KC_8", "KC_9", "KC_0", "KC_MINUS",
         "KC_EQUAL", "KC_BSPACE"],
        # Row 1: QWFPGJLUY;
        ["KC_TAB", "KC_Q", "KC_W", "KC_F", "KC_P", "KC_G",
         "KC_J", "KC_L", "KC_U", "KC_Y", "KC_SCOLON", "KC_LBRACKET",
         "KC_RBRACKET", "KC_DELETE"],
        # Row 2: ARSTDHNEIO
        ["KC_BSPACE", "KC_A", "KC_R", "KC_S", "KC_T", "KC_D",
         "KC_H", "KC_N", "KC_E", "KC_I", "KC_O", "KC_QUOTE",
         "KC_NONUS_HASH", "KC_ENTER"],
        # Row 3: ZXCVBKM,./
        ["KC_LSHIFT", "KC_LSHIFT", "KC_Z", "KC_X", "KC_C", "KC_V",
         "KC_B", "KC_K", "KC_M", "KC_COMMA", "KC_DOT", "KC_SLASH",
         "KC_UP", "KC_GRAVE"],
        # Row 4: Modifiers and space
        ["KC_LCTRL", "KC_LGUI", "KC_LALT", "KC_SPACE", "KC_SPACE",
         "KC_SPACE", "KC_SPACE", "KC_SPACE", "KC_RALT",
         "KC_APPLICATION", "KC_RCTRL", "KC_LEFT", "KC_DOWN", "KC_RIGHT"],
    ]
    if num_rows >= 5:
        return full_grid
    return full_grid[5 - num_rows:]


# ── Preset Registries ─────────────────────────────────────────────────────────

TUNING_PRESETS = [
    ("Chromatic",
     "Linear chromatic from C1. Every semitone in order, bottom-to-top.",
     preset_chromatic),
    ("Octave Rows",
     "Each row is one chromatic octave (C to B). C1 through B5.",
     preset_octave_rows),
    ("Piano (Left-aligned)",
     "Piano layout: C# above C. Rows 1,3=black, Rows 2,4=white, Row 5=extra.",
     preset_piano_left),
    ("Piano (Right-aligned)",
     "Piano layout: C# above D. Rows 1,3=black, Rows 2,4=white, Row 5=extra.",
     preset_piano_right),
    ("Guitar Standard",
     "Guitar fretboard: EADGB tuning. 14 frets per string.",
     preset_guitar_standard),
    ("Guitar All Fourths",
     "All-fourths tuning (EADGC). Consistent intervals between strings.",
     preset_guitar_fourths),
    ("Wicki-Hayden",
     "Isomorphic: whole tones horizontal, fourths vertical. Same shapes in all keys.",
     preset_wicki_hayden),
    ("Janko",
     "Janko keyboard: whole tones per row, offset by semitone. Uniform fingering.",
     preset_janko),
    ("C Major Scale",
     "Diatonic C major (white notes). Overlapping 2-octave rows. No wrong notes.",
     preset_c_major),
    ("Fifths",
     "Chromatic rows separated by perfect fifths. Circle of fifths = vertical line.",
     preset_fifths),
    ("Major Thirds",
     "Chromatic rows separated by major thirds. 3 rows up = 1 octave.",
     preset_major_thirds),
]

KS_PRESETS = [
    ("Chromatic (KS)",
     "Chromatic with KeySplit: left 7 cols = base, right 7 cols = KS zone.",
     preset_chromatic_ks),
    ("Octave Rows (KS)",
     "Octave Rows with KeySplit: left = base, right = KS zone.",
     preset_octave_rows_ks),
    ("Guitar Standard (KS)",
     "Guitar Standard with KeySplit: left = base, right = KS zone.",
     preset_guitar_standard_ks),
    ("C Major L/R (KS)",
     "C Major with left/right KeySplit: left octave = base, right octave = KS.",
     preset_c_major_ks_lr),
    ("C Major T/B (KS)",
     "C Major with top/bottom KeySplit: bottom rows = base, top rows = KS.",
     preset_c_major_ks_tb),
    ("Fifths (KS)",
     "Fifths with KeySplit: left = base, right = KS zone.",
     preset_fifths_ks),
    ("Piano Left (KS)",
     "Piano Left-aligned with KeySplit: left octave = base, right octave = KS.",
     preset_piano_left_ks),
    ("Piano Right (KS)",
     "Piano Right-aligned with KeySplit: left octave = base, right octave = KS.",
     preset_piano_right_ks),
]

TS_PRESETS = [
    ("Chromatic (TS)",
     "Chromatic with TripleSplit: top = base, bottom-left = KS, bottom-right = TS.",
     preset_chromatic_ts),
    ("Octave Rows (TS)",
     "Octave Rows with TripleSplit: top = base, bottom-left = KS, bottom-right = TS.",
     preset_octave_rows_ts),
    ("Guitar Standard (TS)",
     "Guitar Standard with TripleSplit: top = base, bottom-left = KS, bottom-right = TS.",
     preset_guitar_standard_ts),
    ("C Major (TS)",
     "C Major with TripleSplit: top = base, bottom-left = KS, bottom-right = TS.",
     preset_c_major_ts),
    ("Fifths (TS)",
     "Fifths with TripleSplit: top = base, bottom-left = KS, bottom-right = TS.",
     preset_fifths_ts),
]

SINGLE_ROW_PRESETS = [
    ("Loop Control",
     "Loop macros 1-4, mute, overdub, play/pause, sync, speed, save.",
     preset_row_loop_control),
    ("Smart Chord",
     "13 smart chord presets (one per root note) + cycle chord type.",
     preset_row_smart_chord),
    ("Arpeggiator",
     "Arp play, preset nav, rate/gate controls, modes, sync.",
     preset_row_arpeggiator),
    ("Step Sequencer",
     "Seq play/stop, preset nav, rate/gate controls, sync, mod.",
     preset_row_step_sequencer),
    ("Ear Training",
     "12 ear training modes: Basic/Octave/Extended/All intervals, levels 1-3.",
     preset_row_ear_training),
    ("Chord Training",
     "14 chord training modes: Triads/7ths/All 7ths/Combined, levels 1-4.",
     preset_row_chord_training),
    ("Transport / Utility",
     "All notes off, sustain, soft, sostenuto, octave, transpose, channel, bend.",
     preset_row_transport),
]

KEYBOARD_LAYOUT_PRESETS = [
    ("QWERTY",
     "Standard QWERTY keyboard layout. Esc+numbers on top, arrows on bottom-right.",
     preset_keyboard_qwerty),
    ("QWERTY Split",
     "Ergonomic split: QWERT on left, YUIOP on right, Tab/Caps/Enter in center.",
     preset_keyboard_qwerty_split),
    ("Dvorak",
     "Dvorak layout: optimized for English typing efficiency. AOEUIDHTNS home row.",
     preset_keyboard_dvorak),
    ("Colemak",
     "Colemak layout: modern alternative to QWERTY. ARSTDHNEIO home row, Backspace on Caps.",
     preset_keyboard_colemak),
]

# Nested menu structure: (category_name, [(name, description, generator, preset_type), ...])
PRESET_CATEGORIES = [
    ("Typing", [
        (name, desc, gen, PRESET_TYPE_KEYBOARD)
        for name, desc, gen in KEYBOARD_LAYOUT_PRESETS
    ]),
    ("Music", [
        (name, desc, gen, PRESET_TYPE_TUNING)
        for name, desc, gen in TUNING_PRESETS
    ]),
    ("KeySplit", [
        (name, desc, gen, PRESET_TYPE_TUNING)
        for name, desc, gen in KS_PRESETS
    ]),
    ("TripleSplit", [
        (name, desc, gen, PRESET_TYPE_TUNING)
        for name, desc, gen in TS_PRESETS
    ]),
    ("Single Row", [
        (name, desc, gen, PRESET_TYPE_SINGLE_ROW)
        for name, desc, gen in SINGLE_ROW_PRESETS
    ]),
]

# Flat list kept for backwards compatibility (used by apply logic)
KEYMAP_PRESETS = []
for _cat_name, _entries in PRESET_CATEGORIES:
    for entry in _entries:
        KEYMAP_PRESETS.append(entry)
