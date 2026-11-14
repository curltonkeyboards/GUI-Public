# SPDX-License-Identifier: GPL-2.0-or-later
"""Rhythm Engine: twenty slots, each a chord progression played in a rhythm."""

from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QFormLayout, QGroupBox, QListWidget, QLabel

from editor.qb_pages.common import (QbPage, Combo, CategoryCombo, ValueSlider, Loader, channel_combo,
                                    left, factory_curve_combo, hint_label, SECTION_STYLE)
from protocol.app_config import RE_SLOTS
from util import tr

KEYS = ["C / Am", "Db / Bbm", "D / Bm", "Eb / Cm", "E / C#m", "F / Dm", "Gb / Ebm", "G / Em",
        "Ab / Fm", "A / F#m", "Bb / Gm", "B / G#m"]
VOICE_LEADS = ["Basic", "Ascending", "Descending", "Random", "Alternating", "Tight"]
INSTRUMENTS = ["Chords", "Arp", "Bass", "Lead"]

# The keyboard's own menu sorts the progressions into these folders
# (cprog_categories[] in the firmware's chord_progressions.c): name, first, count.
PROGRESSION_CATEGORIES = [("Basic", 0, 13), ("Medium", 13, 14), ("Hard", 27, 15), ("Jazz", 42, 20),
                          ("Funk", 62, 20), ("Latin", 82, 20), ("R&B", 102, 20), ("Soul", 122, 20),
                          ("Major", 142, 41), ("Minor", 183, 52), ("Modal", 235, 68)]

# ...and the rhythms into these (cprog_rhythm_genres[] in the same file), in the
# keyboard's order. The first five are at the top of its menu, the rest are
# inside "Genres". A rhythm can be in more than one folder.
RHYTHM_MAIN_CATEGORIES = 5
RHYTHM_CATEGORIES = [
    ("Arpeggios", [295, 7, 8, 141, 286, 287, 288, 289, 291, 294, 292, 306, 318, 319, 293, 309, 312, 315,
                   316, 320, 211, 220, 308, 219, 314, 317, 307, 313, 310, 9, 140, 209, 212, 214, 215, 216,
                   221, 222, 290, 38, 28, 311, 33, 213, 217, 37, 12, 14, 24, 39, 210, 133]),
    ("Basslines", [67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 161, 107, 93, 162, 170, 106, 113, 176, 166, 96,
                   87, 104, 114, 180, 84, 103, 89, 95, 97, 179, 163, 164, 165, 168, 169, 171, 83, 85, 86,
                   90, 92, 99, 100, 111, 116, 175, 88, 105, 109, 82, 94, 112, 174, 77, 91, 78, 80, 102,
                   110, 177, 115, 167, 101, 172, 173, 79, 98, 108, 81, 178]),
    ("Chords", [0, 127, 5, 129, 223, 11, 1, 2, 6, 3, 218, 276, 128, 10, 279, 130, 274, 277, 273, 285, 4,
                131, 224, 272, 280, 275, 284, 271, 278, 281, 282, 283, 132]),
    ("Chords+Arp", [296, 297, 299, 301, 300, 298, 330, 244, 305, 242, 332, 230, 325, 226, 235, 239, 302,
                    238, 304, 231, 245, 335, 336, 240, 228, 243, 338, 339, 227, 337, 340, 237, 241, 232,
                    225, 233, 234, 236, 247, 250, 229]),
    ("Arp+Chord", [321, 334, 328, 265, 322, 331, 252, 255, 263, 267, 323, 248, 303, 324, 329, 251, 249,
                   253, 266, 256, 326, 257, 269, 254, 262, 261, 264, 259, 327, 258, 270, 333, 260, 268,
                   246]),
    ("Afro", [37, 38, 39, 40, 41, 190, 191, 192, 193]),
    ("Funk", [198, 26, 27, 29, 30, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126]),
    ("Jazz", [205, 206, 17, 18, 19, 20, 21, 181, 182, 183, 184, 185, 47, 48, 49, 50, 51, 52, 53, 54, 55,
              56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66]),
    ("Latin", [203, 31, 32, 33, 34, 35, 36, 186, 187, 188, 189]),
    ("Soul", [201, 202, 24, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160]),
    ("Pop", [207, 208, 13, 15, 16, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142]),
    ("R&B", [199, 200, 22, 23, 25, 143, 144, 145, 146, 147, 148, 149, 150]),
    ("Reggae", [204, 42, 43, 44, 45, 46, 194, 195, 196, 197]),
]


def _t(text):
    return tr("RhythmEnginePage", text)


class RhythmEnginePage(QbPage):

    TITLE = "Rhythm Engine"
    DESCRIPTION = ("Each of the 20 slots plays a chord progression in a rhythm of your choice. Pick a "
                   "slot on the left and set it up on the right. Every change is saved to the keyboard "
                   "straight away.")

    def build(self, layout):
        self._slots = {}
        self._progressions = Loader(self, self._fetch_progression, batch=10)
        self._progressions.loaded.connect(self._on_progression_loaded)
        self._rhythms = Loader(self, self._fetch_rhythm, batch=10)
        self._rhythms.loaded.connect(self._on_rhythm_loaded)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.slot_list = QListWidget()
        self.slot_list.setFixedWidth(150)
        self.slot_list.setMinimumHeight(360)
        for slot in range(RE_SLOTS):
            self.slot_list.addItem(_t("Slot {}").format(slot + 1))
        self.slot_list.currentRowChanged.connect(self._on_slot_selected)
        row.addWidget(self.slot_list)

        right = QVBoxLayout()
        self.slot_title = QLabel("")
        self.slot_title.setStyleSheet(SECTION_STYLE)
        right.addWidget(self.slot_title)

        box = QGroupBox()
        form = QFormLayout(box)
        self.key = Combo()
        for index, name in enumerate(KEYS):
            self.key.addItem(name, index)
        self.progression = CategoryCombo()
        self.rhythm = CategoryCombo()
        self.voicing = Combo()
        for index, name in enumerate(VOICE_LEADS):
            self.voicing.addItem(_t(name), index)
        self.channel = channel_combo(first_is_master=False)
        self.curve = factory_curve_combo()
        self.octave = Combo()
        for octave in range(-3, 4):
            self.octave.addItem(_t("Octave {}").format("{:+d}".format(octave) if octave else "0"), octave * 12)
        self.humanize = ValueSlider(0, 20)
        self.humanize.setToolTip(_t("How much the loudness of each note varies, so it sounds less "
                                    "mechanical. 0 is off."))
        self.instrument = Combo()
        for index, name in enumerate(INSTRUMENTS):
            self.instrument.addItem(_t(name), index)

        form.addRow(_t("Key"), self.key)
        form.addRow(_t("Progression"), self.progression)
        form.addRow(_t("Rhythm"), self.rhythm)
        form.addRow(_t("Voice Lead"), self.voicing)
        form.addRow(_t("Instrument"), self.instrument)
        form.addRow(_t("Channel"), self.channel)
        form.addRow(_t("Articulation"), self.curve)
        form.addRow(_t("Transpose"), self.octave)
        form.addRow(_t("Humanize"), left(self.humanize))
        box.setMaximumWidth(620)
        right.addWidget(box)
        self.names_note = hint_label("")
        right.addWidget(self.names_note)
        right.addStretch(1)
        row.addLayout(right, 1)
        row.addStretch(1)
        layout.addLayout(row)

        self._combos = {"key": self.key, "progression": self.progression, "rhythm": self.rhythm,
                        "voicing": self.voicing, "channel": self.channel, "velocity_curve": self.curve,
                        "transpose": self.octave, "instrument": self.instrument}
        for combo in self._combos.values():
            if isinstance(combo, CategoryCombo):
                combo.changed.connect(self._on_edited)
            else:
                combo.currentIndexChanged.connect(self._on_edited)
        self.humanize.changed.connect(self._on_edited)

        with self.quiet():
            self.slot_list.setCurrentRow(0)
        self.slot_title.setText(_t("Slot {}").format(1))

    # ---- names read in the background -------------------------------------------

    def _fetch_progression(self, index):
        info = self.call("re_progression", index)
        if info is None:
            return None
        name = info["name"] or _t("Progression {}").format(index + 1)
        return _t("{} ({} chords)").format(name, info["length"])

    def _fetch_rhythm(self, index):
        name = self.call("re_rhythm_name", index)
        if name is None:
            return None
        return name or _t("Rhythm {}").format(index + 1)

    def _on_progression_loaded(self, index):
        self.progression.set_label(index, self._progressions.values[index])
        self._show_names_note()

    def _on_rhythm_loaded(self, index):
        self.rhythm.set_label(index, self._rhythms.values[index])
        self._show_names_note()

    def _show_names_note(self):
        missing = (self._progressions.count - len(self._progressions.values)
                   + self._rhythms.count - len(self._rhythms.values))
        self.names_note.setText(_t("Reading names from the keyboard...") if missing > 0 else "")

    # ---- data -------------------------------------------------------------------

    def forget(self):
        self._slots = {}
        self._progressions.reset()
        self._rhythms.reset()
        self.progression.clear()
        self.rhythm.clear()
        self.names_note.setText("")

    def load(self):
        info = self.call("re_info")
        if info is None:
            return False
        if self.progression.item_count() == 0 or self._progressions.count != info["progressions"] \
                or self._rhythms.count != info["rhythms"]:
            self._progressions.reset()
            self._rhythms.reset()
            self.progression.clear()
            self.rhythm.clear()
            self._fill_progressions(info["progressions"])
            self._fill_rhythms(info["rhythms"])
        self._slots = {}
        slot = self._slot()
        config = self.call("re_get", slot)
        if config is None:
            return False
        self._slots[slot] = config
        # the counts are known before the slot is shown, so the names it shows
        # are read first (see _show); the rest follow in the background
        self._progressions.count = info["progressions"]
        self._rhythms.count = info["rhythms"]
        self._show(slot)
        self._progressions.start(info["progressions"])
        self._rhythms.start(info["rhythms"])
        self._show_names_note()
        return True

    def _fill_progressions(self, count):
        """The progressions in the keyboard's folders; any it has beyond them go in "Other"."""
        placed = set()
        for name, first, length in PROGRESSION_CATEGORIES:
            for index in range(first, min(first + length, count)):
                self.progression.add_item(_t(name), _t("Progression {}").format(index + 1), index)
                placed.add(index)
        for index in range(count):
            if index not in placed:
                self.progression.add_item(_t("Other"), _t("Progression {}").format(index + 1), index)

    def _fill_rhythms(self, count):
        placed = set()
        for number, (name, rhythms) in enumerate(RHYTHM_CATEGORIES):
            category = _t(name) if number < RHYTHM_MAIN_CATEGORIES else (_t("Genres"), _t(name))
            for index in rhythms:
                if index < count:
                    self.rhythm.add_item(category, _t("Rhythm {}").format(index + 1), index)
                    placed.add(index)
        for index in range(count):
            if index not in placed:
                self.rhythm.add_item(_t("Other"), _t("Rhythm {}").format(index + 1), index)

    def _slot(self):
        return max(0, self.slot_list.currentRow())

    def _show(self, slot):
        self.slot_title.setText(_t("Slot {}").format(slot + 1))
        config = self._slots.get(slot)
        if config is None:
            return
        with self.quiet():
            # the names this slot shows come first, the rest follow in the background
            if config["progression"] < self._progressions.count:
                self._progressions.get(config["progression"])
            if config["rhythm"] < self._rhythms.count:
                self._rhythms.get(config["rhythm"])
            self.key.set_data(config["key"], _t("Key {}"))
            self.progression.set_data(config["progression"], _t("Progression {}"))
            self.rhythm.set_data(config["rhythm"], _t("Rhythm {}"))
            self.voicing.set_data(config["voicing"], _t("Style {}"))
            self.channel.set_data(config["channel"], _t("Channel {}"))
            self.curve.set_data(config["velocity_curve"], _t("Curve {}"))
            self.octave.set_data(config["transpose"], _t("{} semitones"))
            self.humanize.setValue(config["humanize"])
            self.instrument.set_data(config["instrument"], _t("Instrument {}"))

    # ---- the user's edits -------------------------------------------------------

    def _on_slot_selected(self, row):
        if row < 0 or self.is_quiet():
            return
        if row not in self._slots and self.app_config is not None:
            config = self.call("re_get", row)
            if config is None:
                self.set_status(_t("The keyboard did not answer. Check the connection, then press "
                                   "Read from keyboard."), problem=True)
            else:
                self._slots[row] = config
        self._show(row)

    def _on_edited(self, *_):
        slot = self._slot()
        if not self.ready() or slot not in self._slots:
            return
        config = dict(self._slots[slot])
        for field, combo in self._combos.items():
            if combo.currentData() is not None:
                config[field] = combo.currentData()
        config["humanize"] = self.humanize.value()
        result = self.call("re_set", slot, config)
        if result is None:
            self.refused()
        else:
            self._slots[slot] = result
            self.saved()
        self._show(slot)
