# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared drum-voice binding names + GM default notes.

Single source of truth for the Drum Settings tab (editor/matrix_test.py) and the
Step Sequencer drum-binding note picker (editor/arpeggiator.py). Keep in lockstep
with firmware `factory_seq_gm_default_notes` / `drum_live.c` `dl_extra_defs`.
"""

# 12 primary sequenced drum voices (note + velocity in Drum Settings)
DRUM_VOICE_NAMES = ["Kick", "Snare", "Closed HH", "Open HH", "Clap",
                    "Rimshot", "Cowbell", "Cymbal", "Low Tom", "Mid Tom",
                    "Hi Tom", "Shaker"]
DRUM_GM_DEFAULT_NOTES = [36, 38, 42, 46, 39, 37, 56, 51, 45, 47, 50, 54]
DRUM_GM_DEFAULT_VELS = [100] * 12
DRUM_GM_DEFAULT_CHANNEL = 9  # 0-indexed (channel 10 = GM drums)

# 16 extra DrumLIVE-only voicings (notes only)
DRUM_EXTRA_NAMES = ["Crash", "Crash 2", "Splash", "China", "Ride Bell",
                    "Pedal HH", "Elec Snare", "Hi-Mid Tom", "Floor Tom L",
                    "Floor Tom H", "Hi Bongo", "Lo Bongo", "Maracas",
                    "Vibraslap", "Claves", "Triangle"]
DRUM_EXTRA_CATS = ["Cymbal", "Cymbal", "Cymbal", "Cymbal", "Cymbal",
                   "Hats", "Snare", "Toms", "Toms", "Toms",
                   "Perc", "Perc", "Perc", "Perc", "Perc", "Perc"]
DRUM_EXTRA_DEFAULT_NOTES = [49, 57, 55, 52, 53, 44, 40, 48, 41, 43,
                            60, 61, 70, 58, 75, 81]

# 28 combined bindings (12 core + 16 extra) — a 4x7 grid for the step-seq picker.
DRUM_BINDING_NAMES = DRUM_VOICE_NAMES + DRUM_EXTRA_NAMES
DRUM_BINDING_NOTES = DRUM_GM_DEFAULT_NOTES + DRUM_EXTRA_DEFAULT_NOTES

# note number -> binding name (the 28 default notes are all distinct).
DRUM_NOTE_TO_NAME = {n: nm for n, nm in zip(DRUM_BINDING_NOTES, DRUM_BINDING_NAMES)}
