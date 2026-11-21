# SPDX-License-Identifier: GPL-2.0-or-later
"""SmartChord Sets: what each of the keyboard's 12 sets plays, and what the
custom sets are made of. A set gives every key its own chord: the white keys
the set's main chords (written over C major / A minor, so the C key always
plays a C chord), the black keys its colour chords. Transpose moves the whole
set. Every chord of a built-in set plays in root position on its key (a chord
built over its key, like A7/C#, keeps the key in the bass), so the chords climb
with the keys; a QuickBuild's Inversion inverts them all alike. The built-in
chords are fixed in the firmware (orthomidi5x14.c, sc_set_table); this is their
description for the app. Notes are named with the C key at C3 (MIDI 60)."""

SET_KEYCODE_FIRST = 0xC3E4          # set i is keycode 0xC3E4 + i (MI_CHORD_78 + i)
CUSTOM_KEYCODE_FIRST = 0xC3F0       # custom set i is keycode 0xC3F0 + i (MI_CHORD_90 + i)
QB_CATEGORY = 34                    # the QuickBuild category: the 12 sets, then the 8 custom ones
CUSTOM_SET_COUNT = 8
KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# (name, what it sounds like, [(chord, notes) for the keys C, C#, D ... B])
SETS = [
    ("Chilling", "Warm pop chords with added ninths: bright, easy, hard to get wrong.",
     [("Cadd9", "C3 E3 G3 D4"),
      ("A7/C#", "C#3 E3 G3 A3"),
      ("Dm7", "D3 F3 A3 C4"),
      ("Ebmaj7", "Eb3 G3 Bb3 D4"),
      ("Em7", "E3 G3 B3 D4"),
      ("Fadd9", "F3 A3 C4 G4"),
      ("D/F#", "F#3 A3 D4"),
      ("Gadd9", "G3 B3 D4 A4"),
      ("Abadd9", "Ab3 C4 Eb4 Bb4"),
      ("Am7", "A3 C4 E4 G4"),
      ("Bbadd9", "Bb3 D4 F4 C5"),
      ("G/B", "B3 D4 G4")]),
    ("Jazz", "Ninths and thirteenths, with passing diminished chords on the black keys.",
     [("Cmaj9", "C3 E3 G3 B3 D4"),
      ("C#dim7", "C#3 E3 G3 A#3"),
      ("Dm9", "D3 F3 A3 C4 E4"),
      ("D9", "D3 F#3 A3 C4 E4"),
      ("Em7(11)", "E3 G3 B3 D4 A4"),
      ("Fmaj7(#11)", "F3 A3 C4 E4 B4"),
      ("F#m7b5", "F#3 A3 C4 E4"),
      ("G9(13)", "G3 B3 D4 F4 A4 E5"),
      ("G#dim7", "G#3 B3 D4 F4"),
      ("Am9", "A3 C4 E4 G4 B4"),
      ("Bb7(13)", "Bb3 D4 F4 Ab4 G5"),
      ("Bm7b5", "B3 D4 F4 A4")]),
    ("Neo Soul", "Lush ninths and elevenths, a sus dominant on G and borrowed colours.",
     [("Cmaj9(13)", "C3 E3 G3 B3 D4 A4"),
      ("Dbmaj9", "Db3 F3 Ab3 C4 Eb4"),
      ("Dm11", "D3 F3 A3 C4 E4 G4"),
      ("E7#9", "E3 G#3 B3 D4 G4"),
      ("Em7(11)", "E3 G3 B3 D4 A4"),
      ("Fmaj9", "F3 A3 C4 E4 G4"),
      ("F#m7b5", "F#3 A3 C4 E4"),
      ("G9sus4", "G3 C4 D4 F4 A4"),
      ("Abmaj9", "Ab3 C4 Eb4 G4 Bb4"),
      ("Am11", "A3 C4 E4 G4 B4 D5"),
      ("Bb9", "Bb3 D4 F4 Ab4 C5"),
      ("Gadd9/B", "B3 D4 G4 A4")]),
    ("Lo-fi", "Dusty sevenths and ninths; the minor iv (Fm9) waits on F#.",
     [("Cmaj7", "C3 E3 G3 B3"),
      ("C#m7b5", "C#3 E3 G3 B3"),
      ("Dm9", "D3 F3 A3 C4 E4"),
      ("Ebmaj7", "Eb3 G3 Bb3 D4"),
      ("Em7", "E3 G3 B3 D4"),
      ("Fmaj9", "F3 A3 C4 E4 G4"),
      ("Fm9", "F3 G#3 C4 D#4 G4"),
      ("G9", "G3 B3 D4 F4 A4"),
      ("Abmaj7", "Ab3 C4 Eb4 G4"),
      ("Am9", "A3 C4 E4 G4 B4"),
      ("Bb9", "Bb3 D4 F4 Ab4 C5"),
      ("Bm7b5", "B3 D4 F4 A4")]),
    ("Rainy Day", "Gospel sixes and nines, with passing diminished chords on the black keys.",
     [("C6/9", "C3 E3 G3 A3 D4"),
      ("C#dim7", "C#3 E3 G3 A#3"),
      ("Dm9", "D3 F3 A3 C4 E4"),
      ("D#dim7", "D#3 F#3 A3 C4"),
      ("Em7", "E3 G3 B3 D4"),
      ("Fmaj9", "F3 A3 C4 E4 G4"),
      ("F#dim7", "F#3 A3 C4 D#4"),
      ("G9(13)", "G3 B3 D4 F4 A4 E5"),
      ("G#dim7", "G#3 B3 D4 F4"),
      ("Am9", "A3 C4 E4 G4 B4"),
      ("Bb7(13)", "Bb3 D4 F4 Ab4 G5"),
      ("G/B", "B3 D4 G4")]),
    ("Anime", "The royal road (F, G7, Em7, Am7) and the dominants that lead into it.",
     [("Cmaj7", "C3 E3 G3 B3"),
      ("A7/C#", "C#3 E3 G3 A3"),
      ("Dm7", "D3 F3 A3 C4"),
      ("E7", "E3 G#3 B3 D4"),
      ("Em7", "E3 G3 B3 D4"),
      ("Fmaj7", "F3 A3 C4 E4"),
      ("D7/F#", "F#3 A3 C4 D4"),
      ("G7", "G3 B3 D4 F4"),
      ("Ab", "Ab3 C4 Eb4"),
      ("Am7", "A3 C4 E4 G4"),
      ("Bb", "Bb3 D4 F4"),
      ("Bm7b5", "B3 D4 F4 A4")]),
    ("Bossa", "The six-nines, thirteenths and minor sixes of bossa nova.",
     [("C6/9", "C3 E3 G3 A3 D4"),
      ("C#dim7", "C#3 E3 G3 A#3"),
      ("Dm9", "D3 F3 A3 C4 E4"),
      ("D7(13)", "D3 F#3 A3 C4 B4"),
      ("Em7", "E3 G3 B3 D4"),
      ("Fmaj7(13)", "F3 A3 C4 E4 D5"),
      ("Fm6", "F3 G#3 C4 D4"),
      ("G7(13)", "G3 B3 D4 F4 E5"),
      ("Ab7(#11)", "Ab3 C4 Eb4 Gb4 D5"),
      ("Am9", "A3 C4 E4 G4 B4"),
      ("Bbmaj7", "Bb3 D4 F4 A4"),
      ("Bm7b5", "B3 D4 F4 A4")]),
    ("Bluesy", "Sevenths and ninths everywhere, with the sharp-four diminished on F#.",
     [("C7", "C3 E3 G3 A#3"),
      ("Db9", "Db3 F3 Ab3 B3 Eb4"),
      ("Dm7", "D3 F3 A3 C4"),
      ("Eb7", "Eb3 G3 Bb3 Db4"),
      ("C7/E", "E3 G3 A#3 C4"),
      ("F9", "F3 A3 C4 D#4 G4"),
      ("F#dim7", "F#3 A3 C4 D#4"),
      ("G9", "G3 B3 D4 F4 A4"),
      ("Ab9", "Ab3 C4 Eb4 Gb4 Bb4"),
      ("A7", "A3 C#4 E4 G4"),
      ("Bb7", "Bb3 D4 F4 Ab4"),
      ("G7/B", "B3 D4 F4 G4")]),
    ("Cinematic", "Open add9 chords and the epic borrowed flats.",
     [("Cadd9", "C3 E3 G3 D4"),
      ("Dbmaj7", "Db3 F3 Ab3 C4"),
      ("Dm(add9)", "D3 F3 A3 E4"),
      ("Ebadd9", "Eb3 G3 Bb3 F4"),
      ("Em7", "E3 G3 B3 D4"),
      ("Fadd9", "F3 A3 C4 G4"),
      ("Fm(add9)", "F3 G#3 C4 G4"),
      ("Gadd9", "G3 B3 D4 A4"),
      ("Abadd9", "Ab3 C4 Eb4 Bb4"),
      ("Am(add9)", "A3 C4 E4 B4"),
      ("Bbadd9", "Bb3 D4 F4 C5"),
      ("Gadd9/B", "B3 D4 G4 A4")]),
    ("Sad", "Wistful sevenths, the minor iv (Fm6) and E7 leaning into A minor.",
     [("Cmaj7", "C3 E3 G3 B3"),
      ("A7/C#", "C#3 E3 G3 A3"),
      ("Dm7", "D3 F3 A3 C4"),
      ("Ebmaj7", "Eb3 G3 Bb3 D4"),
      ("Em7", "E3 G3 B3 D4"),
      ("Fmaj7", "F3 A3 C4 E4"),
      ("Fm6", "F3 G#3 C4 D4"),
      ("G6", "G3 B3 D4 E4"),
      ("E7/G#", "G#3 B3 D4 E4"),
      ("Am7", "A3 C4 E4 G4"),
      ("Bbadd9", "Bb3 D4 F4 C5"),
      ("G/B", "B3 D4 G4")]),
    ("Trance", "Big plain triads round A minor, with the epic flat chords (Eb, Ab, Bb).",
     [("C", "C3 E3 G3"),
      ("A/C#", "C#3 E3 A3"),
      ("Dm", "D3 F3 A3"),
      ("Eb", "Eb3 G3 Bb3"),
      ("Em", "E3 G3 B3"),
      ("F", "F3 A3 C4"),
      ("D/F#", "F#3 A3 D4"),
      ("G", "G3 B3 D4"),
      ("Ab", "Ab3 C4 Eb4"),
      ("Am", "A3 C4 E4"),
      ("Bb", "Bb3 D4 F4"),
      ("E/B", "B3 E4 G#4")]),
    ("House", "Deep house minor-eleven stabs and sus chords.",
     [("Cmaj9", "C3 E3 G3 B3 D4"),
      ("C#m7(11)", "C#3 E3 G#3 B3 F#4"),
      ("Dm7(11)", "D3 F3 A3 C4 G4"),
      ("Ebmaj9", "Eb3 G3 Bb3 D4 F4"),
      ("Em7(11)", "E3 G3 B3 D4 A4"),
      ("Fmaj9", "F3 A3 C4 E4 G4"),
      ("F#m7(11)", "F#3 A3 C#4 E4 B4"),
      ("G7sus4", "G3 C4 D4 F4"),
      ("Abmaj9", "Ab3 C4 Eb4 G4 Bb4"),
      ("Am7(11)", "A3 C4 E4 G4 D5"),
      ("Bb9sus4", "Bb3 Eb4 F4 Ab4 C5"),
      ("Bm7b5", "B3 D4 F4 A4")]),
]
SET_NAMES = [entry[0] for entry in SETS]

# ---- custom sets ---------------------------------------------------------------
# A custom set gives each key a chord on that key and the inversion it plays
# in, stored on the keyboard as one byte each (MSW_APPCFG_CSET_GET / _SET).
CHORD_NONE = 0                      # the note alone
CHORD_CUSTOM = 0x80                 # + custom chord slot (0..19)
CUSTOM_CHORD_SLOTS = 20
MAX_INVERSION = 8
# chord byte -> (the firmware's name, intervals above the root, the keymap's name)
# Byte b is SmartChord keycode 0xC396 + b - 1 (MI_CHORD_<b - 1>).
CHORDS = {
    1: ("Major", [4, 7], "Major"),
    2: ("Minor", [3, 7], "Minor"),
    3: ("Diminished", [3, 6], "Diminished"),
    4: ("Augmented", [4, 8], "Augmented"),
    5: ("b5", [4, 6], "b5"),
    6: ("sus2", [2, 7], "Sus2"),
    7: ("sus4", [5, 7], "Sus4"),
    8: ("7no3", [7, 10], "7 no 3"),
    9: ("maj7no3", [7, 11], "Major 7 no 3"),
    10: ("7no5", [4, 10], "7 no 5"),
    11: ("m7no5", [3, 10], "Minor 7 no 5"),
    12: ("maj7no5", [4, 11], "Major 7 no 5"),
    13: ("6", [4, 7, 9], "Major 6"),
    14: ("m6", [3, 7, 9], "Minor 6"),
    15: ("add2", [2, 4, 7], "Add2"),
    16: ("m(add2)", [2, 3, 7], "Minor Add2"),
    17: ("add4", [4, 5, 7], "Add4"),
    18: ("m(add4)", [3, 5, 7], "Minor Add4"),
    19: ("7", [4, 7, 10], "7"),
    20: ("maj7", [4, 7, 11], "Major 7"),
    21: ("m7", [3, 7, 10], "Minor 7"),
    22: ("m7b5", [3, 6, 10], "Minor 7 b5"),
    23: ("dim7", [3, 6, 9], "Diminished 7"),
    24: ("minMaj7", [3, 7, 11], "Minor Major 7"),
    25: ("7sus4", [5, 7, 10], "7 Sus4"),
    26: ("add9", [4, 7, 14], "Add9"),
    27: ("m(add9)", [3, 7, 14], "Minor Add9"),
    28: ("add11", [4, 7, 17], "Add11"),
    29: ("m(add11)", [3, 7, 17], "Minor Add11"),
    30: ("9", [4, 7, 10, 14], "9"),
    31: ("m9", [3, 7, 10, 14], "Minor 9"),
    32: ("maj9", [4, 7, 11, 14], "Major 9"),
    33: ("6/9", [4, 7, 9, 14], "6/9"),
    34: ("m6/9", [3, 7, 9, 14], "Minor 6/9"),
    35: ("7b9", [4, 7, 10, 13], "7 b9"),
    36: ("7(11)", [4, 7, 10, 17], "7(11)"),
    37: ("7(#11)", [4, 7, 10, 18], "7(#11)"),
    38: ("m7(11)", [3, 7, 10, 17], "Minor 7(11)"),
    39: ("maj7(11)", [4, 7, 11, 17], "Major 7(11)"),
    40: ("maj7(#11)", [4, 7, 11, 18], "Major 7(#11)"),
    41: ("7(13)", [4, 7, 10, 21], "7(13)"),
    42: ("m7(13)", [3, 7, 10, 21], "Minor 7(13)"),
    43: ("maj7(13)", [4, 7, 11, 21], "Major 7(13)"),
    44: ("11", [4, 7, 10, 14, 17], "11"),
    45: ("m11", [3, 7, 10, 14, 17], "Minor 11"),
    46: ("maj11", [4, 7, 11, 14, 17], "Major 11"),
    47: ("7(11)(13)", [4, 7, 10, 17, 21], "7(11)(13)"),
    48: ("m7(11)(13)", [3, 7, 10, 17, 21], "Minor 7(11)(13)"),
    49: ("maj7(11)(13)", [4, 7, 11, 17, 21], "Major 7(11)(13)"),
    50: ("9(13)", [4, 7, 10, 14, 21], "9(13)"),
    51: ("m9(13)", [3, 7, 10, 14, 21], "Minor 9(13)"),
    52: ("maj9(13)", [4, 7, 11, 14, 21], "Major 9(13)"),
    53: ("13", [4, 7, 10, 14, 17, 21], "13"),
    54: ("m13", [3, 7, 10, 14, 17, 21], "Minor 13"),
    55: ("maj13", [4, 7, 11, 14, 17, 21], "Major 13"),
    56: ("7b9(11)", [4, 7, 10, 13, 17], "7 b9(11)"),
    57: ("7sus2", [2, 7, 10], "7 Sus2"),
    58: ("7#5", [4, 8, 10], "7 #5"),
    59: ("7b5", [4, 6, 10], "7 b5"),
    60: ("7#9", [4, 7, 10, 15], "7 #9"),
    61: ("7b5b9", [4, 6, 10, 13], "7 b5 b9"),
    62: ("7b5#9", [4, 6, 10, 15], "7 b5 #9"),
    63: ("7b9(13)", [4, 7, 10, 13, 21], "7 b9(13)"),
    64: ("7#9(13)", [4, 7, 10, 15, 21], "7 #9(13)"),
    65: ("7#5b9", [4, 8, 10, 13], "7 #5 b9"),
    66: ("7#5#9", [4, 8, 10, 15], "7 #5 #9"),
    67: ("7b5(11)", [4, 6, 10, 17], "7 b5(11)"),
    68: ("maj7sus4", [5, 7, 11], "Major 7 Sus4"),
    69: ("maj7#5", [4, 8, 11], "Major 7 #5"),
    70: ("maj7b5", [4, 6, 11], "Major 7 b5"),
    71: ("minMaj7(11)", [3, 7, 11, 17], "Minor Major 7(11)"),
    72: ("(add#11)", [4, 6, 7], "Add #11"),
    73: ("9#11", [4, 7, 10, 14, 18], "9 #11"),
    74: ("9b5", [4, 6, 10, 14], "9 b5"),
    75: ("9#5", [4, 8, 10, 14], "9 #5"),
    76: ("m9b5", [3, 6, 10, 14], "Minor 9 b5"),
    77: ("m9#11", [3, 7, 10, 14, 18], "Minor 9 #11"),
    78: ("9sus4", [5, 7, 10, 14], "9 Sus4"),
}
# The chord picker's groups: the keymap SmartChord tab's columns.
CHORD_GROUPS = [
    ("3 Note Chords", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]),
    ("4 Note Chords", [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29]),
    ("5 Note Chords", [30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43]),
    ("6 Note Chords", [44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55]),
    ("Other", [56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78]),
]
# A new custom set: the white keys play the triads of C major, the black keys
# the note alone (to fill in).
NEW_SET = [(1, 0), (0, 0), (2, 0), (0, 0), (2, 0), (1, 0), (0, 0), (1, 0), (0, 0), (2, 0), (0, 0), (3, 0)]
_SUFFIX = {"Major": "", "Minor": "m", "Diminished": "dim", "Augmented": "aug"}


def custom_set_name(index):
    return "Custom Set {}".format(index + 1)


def note_name(note):
    """A MIDI note's name with the C key at C3 (60 = C3)."""
    return KEY_NAMES[note % 12] + str(note // 12 - 2)


def notes_text(notes):
    return " ".join(note_name(note) for note in notes)


def fold_intervals(intervals):
    """A custom chord as a set plays it: every note above the root, no
    repeats, lowest first (firmware sc_cset_chord)."""
    out = []
    for interval in intervals:
        while interval <= 0:
            interval += 12
        if interval not in out:
            out.append(interval)
    return sorted(out)


def chord_intervals(chord, custom_chords=None):
    """Semitones above the root for a chord byte ([] for none / an empty custom chord)."""
    if chord in CHORDS:
        return list(CHORDS[chord][1])
    if CHORD_CUSTOM <= chord < CHORD_CUSTOM + CUSTOM_CHORD_SLOTS:
        return fold_intervals((custom_chords or {}).get(chord - CHORD_CUSTOM) or [])
    return []


def chord_label(key, chord):
    """What a custom set's key plays, by name: "Dm7", "Custom 3", "None"."""
    if chord in CHORDS:
        name = _SUFFIX.get(CHORDS[chord][0], CHORDS[chord][0])
        if name[:1] in ("b", "#"):          # "D(b5)", not "Db5"
            name = "(" + name + ")"
        return KEY_NAMES[key] + name
    if CHORD_CUSTOM <= chord < CHORD_CUSTOM + CUSTOM_CHORD_SLOTS:
        return "Custom {}".format(chord - CHORD_CUSTOM + 1)
    return "None"


def voicing(key, chord, inversion, custom_chords=None):
    """The notes a custom set's key plays (the C key = MIDI 60), voiced as the
    firmware does: the chord on the key, then `inversion` voices raised an
    octave, lowest first."""
    root = 60 + key
    notes = sorted([root] + [root + interval for interval in chord_intervals(chord, custom_chords)])
    if len(notes) > 1:
        for step in range(inversion):
            index = step % len(notes)
            if notes[index] + 12 <= 127:
                notes[index] += 12
    return sorted(notes)
