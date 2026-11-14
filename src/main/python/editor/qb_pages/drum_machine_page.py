# SPDX-License-Identifier: GPL-2.0-or-later
"""Drum Machine: twenty slots, each a drum pattern and the notes its sounds send."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QFormLayout, QGridLayout, QGroupBox, QListWidget,
                             QLabel, QCheckBox, QWidget, QSpacerItem, QSizePolicy)

from editor.qb_pages.common import (QbPage, Combo, CategoryCombo, ValueSlider, NoteSpin, Loader,
                                    channel_combo, left, factory_curve_combo, hint_label, SECTION_STYLE,
                                    HINT_STYLE, SEQUENCED_VOICES)
from protocol.app_config import DM_SLOTS, DM_CHAIN_MAX
from util import tr

PATTERN_NONE = 0xFFFF
CHAIN_COLUMNS = 4
CHAIN_BAR_WIDTH = 162       # room for "Repeat previous"
CHAIN_NUMBER_WIDTH = 18
CHAIN_MIN = 2               # one bar is not a chain

# The keyboard's own menu sorts the patterns into these folders (genres[] and
# the sub_*[] tables in the firmware's seq_drum_patterns.c): folder, folder
# inside it (None = the patterns sit in the folder itself), first, count.
PATTERN_CATEGORIES = [
    ("Funk", None, 0, 101),
    ("Latin", "Afro-Cuban", 101, 30), ("Latin", "Bossa Nova", 131, 16), ("Latin", "Samba", 147, 18),
    ("Latin", "Cha-Cha", 165, 9), ("Latin", "Latin Misc", 174, 6),
    ("Pop", "Pop", 180, 34), ("Pop", "Misc", 214, 4), ("Pop", "Ballad", 218, 15), ("Pop", "Slow", 233, 18),
    ("Rock", "Rock", 251, 46), ("Rock", "Twist", 297, 12),
    ("Reggae & Ska", "Reggae", 309, 36), ("Reggae & Ska", "Ska", 345, 9),
    ("Reggae & Ska", "Reggaeton", 354, 4),
    ("Endings", "Drum Rolls", 358, 7), ("Endings", "Endings", 365, 5),
    ("Hip Hop", "Hip Hop", 370, 26), ("Hip Hop", "Dub", 396, 4),
    ("Disco", None, 400, 37),
    ("Blues & Shuffle", "Blues", 437, 15), ("Blues & Shuffle", "Shuffle", 452, 15),
    ("Blues & Shuffle", "Boogie", 467, 6),
    ("R&B", None, 473, 33),
    ("Electronic", "Electro", 506, 9), ("Electronic", "House", 515, 8), ("Electronic", "D&B", 523, 13),
    ("Electronic", "Misc", 536, 13),
    ("Jazz & Swing", "Jazz", 549, 9), ("Jazz & Swing", "Swing", 558, 20),
]


# The user's own step sequences can be used as drum patterns too. They are
# numbered from here up, one per user sequence, well clear of the factory
# patterns (the firmware's DRUM_USER_PATTERN_BASE and NUM_USER_SEQ_PRESETS).
USER_PATTERN_FIRST = 0x8000
USER_PATTERN_COUNT = 40


def is_user_pattern(index):
    return USER_PATTERN_FIRST <= index < USER_PATTERN_FIRST + USER_PATTERN_COUNT


def _t(text):
    return tr("DrumMachinePage", text)


class DrumMachinePage(QbPage):

    TITLE = "Drum Machine"
    DESCRIPTION = ("Each of the 20 slots holds a drum pattern, and the note and loudness every drum "
                   "sound is sent with. Pick a slot on the left and set it up on the right. Every "
                   "change is saved to the keyboard straight away.")

    def build(self, layout):
        self._slots = {}
        self._chains = {}           # slot -> the chain the keyboard holds ([] = no chain)
        self._set_aside = {}        # slot -> the chain it had when chain mode was last turned off
        self._user_listed = set()   # the user's sequences added to the dropdowns so far
        self._patterns = Loader(self, self._fetch_pattern, batch=10)
        self._patterns.loaded.connect(self._on_pattern_loaded)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.slot_list = QListWidget()
        self.slot_list.setFixedWidth(150)
        self.slot_list.setMinimumHeight(360)
        for slot in range(DM_SLOTS):
            self.slot_list.addItem(_t("Slot {}").format(slot + 1))
        self.slot_list.currentRowChanged.connect(self._on_slot_selected)
        row.addWidget(self.slot_list)

        right = QVBoxLayout()
        self.slot_title = QLabel(_t("Slot {}").format(1))
        self.slot_title.setStyleSheet(SECTION_STYLE)
        right.addWidget(self.slot_title)

        box = QGroupBox(_t("Pattern"))
        form = QFormLayout(box)
        self.chain_on = QCheckBox(_t("Enable chain mode"))
        self.chain_on.setToolTip(_t("A chain plays several patterns one after another, one per bar."))
        self.chain_note = hint_label("")
        chain_row = QHBoxLayout()
        chain_row.addWidget(self.chain_on)
        chain_row.addSpacing(12)
        chain_row.addWidget(self.chain_note, 1)
        form.addRow(chain_row)

        # either the one pattern or the chain, in the same place
        self.pattern_label = QLabel(_t("Pattern"))
        self.pattern = CategoryCombo()
        self.bars = Combo()
        self.bars.setMinimumContentsLength(4)
        for bars in range(CHAIN_MIN, DM_CHAIN_MAX + 1):
            self.bars.addItem(str(bars), bars)
        self.bars.setToolTip(_t("How many bars the chain has. Each bar plays one pattern."))
        self.chain_holder = QWidget()
        chain_grid = QGridLayout(self.chain_holder)
        chain_grid.setContentsMargins(0, 0, 0, 0)
        chain_grid.setHorizontalSpacing(8)
        chain_grid.setVerticalSpacing(6)
        self.chain_labels, self.chain_bars = [], []
        for bar in range(DM_CHAIN_MAX):
            line, column = divmod(bar, CHAIN_COLUMNS)
            label = QLabel(str(bar + 1))
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            label.setMinimumWidth(CHAIN_NUMBER_WIDTH)
            combo = CategoryCombo()
            combo.setMinimumContentsLength(11)
            label.setBuddy(combo)
            chain_grid.addWidget(label, line, column * 2)
            chain_grid.addWidget(combo, line, column * 2 + 1)
            chain_grid.setColumnStretch(column * 2 + 1, 1)
            chain_grid.setColumnMinimumWidth(column * 2 + 1, CHAIN_BAR_WIDTH)
            self.chain_labels.append(label)
            self.chain_bars.append(combo)
        place = QVBoxLayout()
        place.setContentsMargins(0, 0, 0, 0)
        place.setSpacing(6)
        place.addWidget(self.pattern)
        place.addLayout(left(self.bars))
        place.addWidget(self.chain_holder)
        # as wide with the chain off as with it on, so the page does not jump
        width = CHAIN_COLUMNS * (CHAIN_BAR_WIDTH + CHAIN_NUMBER_WIDTH) + (CHAIN_COLUMNS * 2 - 1) * 8
        place.addItem(QSpacerItem(width, 0, QSizePolicy.Minimum, QSizePolicy.Fixed))
        form.addRow(self.pattern_label, place)

        # the rest is the same either way
        self.channel = channel_combo(first_is_master=False)
        self.curve = factory_curve_combo()
        self.curve.setToolTip(_t("How hard the drums are played."))
        humanize_row = QHBoxLayout()
        self.humanize_on = QCheckBox(_t("On"))
        self.humanize = ValueSlider(0, 127)
        self.humanize.setToolTip(_t("How much the loudness of each hit varies, so it sounds less "
                                    "mechanical."))
        humanize_row.addWidget(self.humanize_on)
        humanize_row.addSpacing(8)
        humanize_row.addWidget(self.humanize)
        humanize_row.addStretch(1)
        form.addRow(_t("Channel"), self.channel)
        form.addRow(_t("Articulation"), self.curve)
        form.addRow(_t("Humanize"), humanize_row)
        right.addWidget(box)
        self.names_note = hint_label("")
        right.addWidget(self.names_note)

        voices = QGroupBox(_t("Drum sounds"))
        grid = QGridLayout(voices)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(3)
        half = (len(SEQUENCED_VOICES) + 1) // 2
        for block in range(2):
            for column, text in enumerate((_t("Sound"), _t("Note"), _t("Loudness"))):
                header = QLabel(text)
                header.setStyleSheet(HINT_STYLE)
                grid.addWidget(header, 0, block * 4 + column)
        grid.setColumnMinimumWidth(3, 24)
        self.notes, self.velocities = [], []
        for voice, name in enumerate(SEQUENCED_VOICES):
            block, line = divmod(voice, half)
            label = QLabel(_t(name))
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            note = NoteSpin()
            note.setToolTip(_t("The MIDI note this sound sends. Type a number (36) or a name (C1)."))
            velocity = ValueSlider(0, 127, width=110)       # the keyboard takes 0 to 127
            velocity.setToolTip(_t("How loud this sound is, 0 to 127."))
            label.setBuddy(note)
            grid.addWidget(label, line + 1, block * 4)
            grid.addWidget(note, line + 1, block * 4 + 1)
            grid.addWidget(velocity, line + 1, block * 4 + 2)
            self.notes.append(note)
            self.velocities.append(velocity)
        grid.setColumnStretch(8, 1)
        right.addWidget(voices)
        right.addStretch(1)
        right.setContentsMargins(0, 0, 0, 0)
        holder = QWidget()
        holder.setLayout(right)
        holder.setMaximumWidth(880)
        row.addWidget(holder, 1)
        row.addStretch(1)
        layout.addLayout(row)

        # left block top to bottom, then the right block
        order = [self.chain_on, self.pattern, self.bars] + self.chain_bars
        order += [self.channel, self.curve, self.humanize_on, self.humanize]
        for voice in range(len(SEQUENCED_VOICES)):
            order += [self.notes[voice], self.velocities[voice]]
        for first, second in zip(order, order[1:]):
            self.setTabOrder(first, second)

        self.pattern.changed.connect(self._on_edited)
        for combo in (self.channel, self.curve):
            combo.currentIndexChanged.connect(self._on_edited)
        self.humanize_on.toggled.connect(self._on_edited)
        self.humanize.changed.connect(self._on_edited)
        for spin in self.notes:
            spin.valueChanged.connect(self._on_edited)
        for slider in self.velocities:
            slider.changed.connect(self._on_edited)
        self.chain_on.toggled.connect(self._on_chain_toggled)
        self.bars.currentIndexChanged.connect(self._on_bars_changed)
        for bar, combo in enumerate(self.chain_bars):
            combo.changed.connect(lambda bar=bar: self._on_bar_changed(bar))

        with self.quiet():
            self.slot_list.setCurrentRow(0)

    # ---- names read in the background -------------------------------------------

    def _fetch_pattern(self, index):
        name = self.call("dm_pattern_name", index)
        if name is None:
            return None
        if is_user_pattern(index):
            return name or _t("User Seq {}").format(index - USER_PATTERN_FIRST + 1)
        return name or _t("Pattern {}").format(index + 1)

    def _on_pattern_loaded(self, index):
        for combo in [self.pattern] + self.chain_bars:
            combo.set_label(index, self._patterns.values[index])
        self._show_names_note()

    def _show_names_note(self):
        known = sum(1 for index in self._patterns.values if index < self._patterns.count)
        missing = self._patterns.count - known
        self.names_note.setText(_t("Reading pattern names from the keyboard...") if missing > 0 else "")

    def _name_pattern(self, index):
        """Make sure the pattern a slot or chain bar holds is shown by name,
        ahead of the names still being read in the background. One of the
        user's own sequences is not in the factory list: it is added to the
        dropdowns, under "User"."""
        if index == PATTERN_NONE:
            return
        user = is_user_pattern(index)
        if not user and index >= self._patterns.count:
            return                              # not a pattern this keyboard has
        name = self._patterns.get(index)        # tells the dropdowns that hold it (_on_pattern_loaded)
        if user and index not in self._user_listed:
            self._user_listed.add(index)
            label = name or _t("User Seq {}").format(index - USER_PATTERN_FIRST + 1)
            for combo in [self.pattern] + self.chain_bars:
                combo.add_item(_t("User"), label, index)

    # ---- data -------------------------------------------------------------------

    def forget(self):
        self._slots = {}
        self._chains = {}
        self._set_aside = {}
        self._user_listed = set()
        self._patterns.reset()
        self.pattern.clear()
        for combo in self.chain_bars:
            combo.clear()
        self.names_note.setText("")
        self._show_chain(self._slot())

    def load(self):
        count = self.call("dm_pattern_count")
        if count is None:
            return False
        if self.pattern.item_count() == 0 or self._patterns.count != count:
            self._patterns.reset()
            self._user_listed = set()
            folders = self._folders(count)
            for number, combo in enumerate([self.pattern] + self.chain_bars):
                combo.clear()
                if number == 0:
                    combo.add_item(None, _t("None"), PATTERN_NONE)
                elif number > 1:                # bars after the first can repeat the one before
                    combo.add_item(None, _t("Repeat previous"), PATTERN_NONE)
                for folder, index in folders:
                    combo.add_item(folder, _t("Pattern {}").format(index + 1), index)
        # the user can rename their own sequences: ask for those names afresh
        for index in [index for index in self._patterns.values if is_user_pattern(index)]:
            del self._patterns.values[index]
        self._slots = {}
        self._chains = {}
        self._set_aside = {}
        slot = self._slot()
        config = self.call("dm_get", slot)
        if config is None:
            return False
        self._slots[slot] = config
        chain = self.call("dm_chain_get", slot)
        if chain is not None:
            self._chains[slot] = chain
        # how many patterns there are is known before the slot is shown, so the
        # names it shows are read first; the rest follow in the background
        self._patterns.count = count
        self._show(slot)
        self._patterns.start(count)
        self._show_names_note()
        return True

    @staticmethod
    def _folders(count):
        """(folder, pattern) for every pattern, in the keyboard's folders; any
        it has beyond them go in "Other"."""
        out, placed = [], set()
        for name, inner, first, length in PATTERN_CATEGORIES:
            folder = (_t(name), _t(inner)) if inner else _t(name)
            for index in range(first, min(first + length, count)):
                out.append((folder, index))
                placed.add(index)
        out += [(_t("Other"), index) for index in range(count) if index not in placed]
        return out

    def _slot(self):
        return max(0, self.slot_list.currentRow())

    def _show(self, slot):
        self.slot_title.setText(_t("Slot {}").format(slot + 1))
        self._show_chain(slot)
        config = self._slots.get(slot)
        if config is None:
            return
        with self.quiet():
            self._name_pattern(config["pattern"])
            self.pattern.set_data(config["pattern"], _t("Pattern {}"))
            self.channel.set_data(config["channel"], _t("Channel {}"))
            self.curve.set_data(config["velocity_curve"], _t("Curve {}"))
            self.humanize_on.setChecked(bool(config["humanize_on"]))
            self.humanize.setValue(config["humanize"])
            self.humanize.setEnabled(bool(config["humanize_on"]))
            for voice in range(len(SEQUENCED_VOICES)):
                self.notes[voice].setValue(config["notes"][voice])
                self.velocities[voice].setValue(config["velocities"][voice])

    def _show_chain(self, slot):
        """The chain as the keyboard holds it. The keyboard has no separate
        "chain mode" setting: a slot is in chain mode when it holds a chain."""
        chain = self._chains.get(slot)
        bars = len(chain) if chain else 0
        with self.quiet():
            self.chain_on.setChecked(bars > 0)
            self.chain_on.setEnabled(chain is not None)
            self.pattern_label.setText(_t("Bars") if bars else _t("Pattern"))
            self.pattern_label.setBuddy(self.bars if bars else self.pattern)
            self.pattern.setVisible(bars == 0)
            self.bars.setVisible(bars > 0)
            self.chain_holder.setVisible(bars > 0)
            if bars:
                self.bars.set_data(bars)
            for bar, combo in enumerate(self.chain_bars):
                used = bar < bars
                if used:
                    self._name_pattern(chain[bar])
                    combo.set_data(chain[bar], _t("Pattern {}"))
                combo.setVisible(used)
                self.chain_labels[bar].setVisible(used)
        if chain is None:
            self.chain_note.setText(_t("The keyboard did not answer. Check the connection, then press "
                                       "Read from keyboard.") if self.app_config is not None else "")
        elif bars:
            self.chain_note.setText(_t("The slot plays these patterns one after another, one per bar."))
        else:
            self.chain_note.setText(_t("A chain plays several patterns one after another, one per bar."))

    # ---- the user's edits -------------------------------------------------------

    def _on_slot_selected(self, row):
        if row < 0 or self.is_quiet():
            return
        if row not in self._slots and self.app_config is not None:
            config = self.call("dm_get", row)
            if config is None:
                self.set_status(_t("The keyboard did not answer. Check the connection, then press "
                                   "Read from keyboard."), problem=True)
            else:
                self._slots[row] = config
        if row in self._slots and row not in self._chains:
            chain = self.call("dm_chain_get", row)
            if chain is not None:
                self._chains[row] = chain
        self._show(row)

    def _on_edited(self, *_):
        slot = self._slot()
        if not self.ready() or slot not in self._slots:
            return
        config = dict(self._slots[slot])
        if self.pattern.current_data() is not None:
            config["pattern"] = self.pattern.current_data()
        if self.channel.currentData() is not None:
            config["channel"] = self.channel.currentData()
        if self.curve.currentData() is not None:
            config["velocity_curve"] = self.curve.currentData()
        config["humanize_on"] = self.humanize_on.isChecked()
        config["humanize"] = self.humanize.value()
        config["notes"] = [spin.value() for spin in self.notes]
        config["velocities"] = [slider.value() for slider in self.velocities]
        ok = self.call("dm_set", slot, config)
        fresh = self.call("dm_get", slot)       # dm_set only says yes or no: read back what was kept
        if fresh is not None:
            self._slots[slot] = fresh
        if ok:
            self.saved()
        else:
            self.refused()
        self._show(slot)

    def _on_chain_toggled(self, on):
        slot = self._slot()
        if not self.ready() or slot not in self._chains:
            return
        if not on:
            self._set_aside[slot] = list(self._chains[slot])    # ticking the box again brings it back
            self._write_chain(slot, [])
            return
        first = self._slots.get(slot, {}).get("pattern", PATTERN_NONE)
        if first == PATTERN_NONE and self._patterns.count > 0:
            first = 0
        chain = list(self._set_aside.get(slot) or [])
        if len(chain) < CHAIN_MIN:              # a new chain starts as the slot's own pattern, twice
            chain = [first] * CHAIN_MIN
        chain[0] = first                        # bar 1 is always the slot's pattern
        self._write_chain(slot, chain)

    def _on_bars_changed(self, *_):
        slot = self._slot()
        if not self.ready() or not self._chains.get(slot):
            return
        bars = self.bars.currentData() or CHAIN_MIN
        chain = list(self._chains[slot])[:bars]
        while len(chain) < bars:                # a new bar starts as a copy of the one before it
            chain.append(chain[-1])
        if chain != self._chains[slot]:
            self._write_chain(slot, chain)

    def _on_bar_changed(self, bar):
        slot = self._slot()
        if not self.ready() or slot not in self._chains or bar >= len(self._chains[slot]):
            return
        value = self.chain_bars[bar].current_data()
        if value is None or value == self._chains[slot][bar]:
            return
        chain = list(self._chains[slot])
        chain[bar] = value
        self._write_chain(slot, chain)

    def _write_chain(self, slot, chain):
        kept = self.call("dm_chain_set", slot, chain)
        if kept is None:
            self.refused()
            fresh = self.call("dm_chain_get", slot)     # show what the keyboard really has
            if fresh is not None:
                self._chains[slot] = fresh
        else:
            self._chains[slot] = kept
            config = self.call("dm_get", slot)          # a chain makes its bar 1 the slot's pattern
            if config is not None:
                self._slots[slot] = config
            self.saved()
        self._show(slot)
