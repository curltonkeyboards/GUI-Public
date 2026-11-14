# SPDX-License-Identifier: GPL-2.0-or-later
"""SmartChord: how chords move from one to the next (voice leading), and the
twenty chord shapes of your own."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QFormLayout, QGroupBox, QListWidget,
                             QListWidgetItem, QLabel, QPushButton)

from editor.qb_pages.common import (QbPage, Combo, SignedSpin, hint_label, section_label, divider,
                                    NOTE_NAMES, SECTION_STYLE)
from protocol.app_config import SC_SLOTS
from util import tr

VOICES = ["Highest", "Lowest", "3rd", "5th", "Ext 1", "Ext 2"]
RULES = ["None", "Ascending", "Descending", "Alternating", "Tight"]
MAX_NOTES = 6
NEW_INTERVALS = [4, 7, 10, 14, 17, 21, 2, 5, 9, 11]      # what "Add note" offers, in this order


def _t(text):
    return tr("SmartChordPage", text)


def chord_notes(intervals):
    """The notes of a shape on a C root: [3, 7, 10] -> "C Eb G Bb"."""
    pitches = sorted(set([0] + list(intervals)))
    if all(0 <= pitch <= 11 for pitch in pitches):
        return " ".join(NOTE_NAMES[pitch] for pitch in pitches)
    # wider than an octave, or below the root: say which octave (the root is C3)
    return " ".join("{}{}".format(NOTE_NAMES[pitch % 12], 3 + pitch // 12) for pitch in pitches)


class IntervalSpin(SignedSpin):
    """Semitones from the root, never 0 (that is the root itself). The range
    is everything the keyboard can hold (a signed byte), so a chord made
    elsewhere is always shown, and saved back, as it is."""

    def __init__(self, parent=None):
        super().__init__(-128, 127, parent)
        self.setKeyboardTracking(True)
        self.setToolTip(_t("Semitones above the root (or below it, with a minus)."))

    def stepBy(self, steps):
        target = self.value() + steps
        if target == 0:
            target += 1 if steps > 0 else -1
        self.setValue(target)


class SmartChordPage(QbPage):

    TITLE = "SmartChord"
    DESCRIPTION = ("Voice leading decides how the notes of one chord move to the next; it is only "
                   "changed when you press Save. A custom chord is only changed when you press Save chord.")
    CHORDS = True               # False: the voice leading part alone (VoiceLeadingPage)

    def build(self, layout):
        self._vl = None
        self._vl_dirty = False      # rules / priority changed here but not saved yet
        self._chords = {}           # slot -> intervals on the keyboard
        self._drafts = {}           # slot -> intervals edited here but not saved yet

        # ---- voice leading ----
        if self.CHORDS:
            layout.addWidget(section_label(_t("Voice leading")))
        layout.addWidget(hint_label(_t("Give each voice of the chord a rule. \"None\" on Highest turns "
                                       "voice leading off. When two rules disagree, the voice higher up "
                                       "the priority list wins.")))
        vl_row = QHBoxLayout()
        vl_row.setSpacing(12)
        rules_box = QGroupBox(_t("Rules"))
        rules_form = QFormLayout(rules_box)
        self.rule_combos = []
        for voice in VOICES:
            combo = Combo()
            combo.setMinimumContentsLength(11)
            for index, rule in enumerate(RULES):
                combo.addItem(_t(rule), index)
            combo.currentIndexChanged.connect(self._on_vl_edited)
            rules_form.addRow(_t(voice), combo)
            self.rule_combos.append(combo)
        vl_row.addWidget(rules_box)

        priority_box = QGroupBox(_t("Priority (most important first)"))
        priority_layout = QHBoxLayout(priority_box)
        self.priority_list = QListWidget()
        self.priority_list.setFixedWidth(170)
        self.priority_list.setMinimumHeight(190)
        self.priority_list.currentRowChanged.connect(self._sync_priority_buttons)
        priority_layout.addWidget(self.priority_list)
        moves = QVBoxLayout()
        self.up_button = QPushButton(_t("Up"))
        self.up_button.setToolTip(_t("Make the selected voice more important."))
        self.up_button.clicked.connect(lambda: self._move_priority(-1))
        self.down_button = QPushButton(_t("Down"))
        self.down_button.setToolTip(_t("Make the selected voice less important."))
        self.down_button.clicked.connect(lambda: self._move_priority(1))
        moves.addWidget(self.up_button)
        moves.addWidget(self.down_button)
        moves.addStretch(1)
        priority_layout.addLayout(moves)
        vl_row.addWidget(priority_box)

        reset_column = QVBoxLayout()
        self.vl_save_button = QPushButton(_t("Save"))
        self.vl_save_button.setToolTip(_t("Store these rules and this priority on the keyboard."))
        self.vl_save_button.clicked.connect(self._on_vl_save)
        self.vl_read_button = QPushButton(_t("Read from keyboard"))
        self.vl_read_button.setToolTip(_t("Show what the keyboard has now, dropping changes that "
                                          "were not saved."))
        self.vl_read_button.clicked.connect(self._on_vl_read)
        self.reset_button = QPushButton(_t("Reset to defaults"))
        self.reset_button.setToolTip(_t("Put the rules and the priority back the way the keyboard "
                                        "came."))
        self.reset_button.clicked.connect(self._on_vl_reset)
        self.vl_note = hint_label("")
        reset_column.addSpacing(8)
        reset_column.addWidget(self.vl_save_button)
        reset_column.addWidget(self.vl_read_button)
        reset_column.addWidget(self.reset_button)
        reset_column.addWidget(self.vl_note)
        reset_column.addStretch(1)
        vl_row.addLayout(reset_column)
        vl_row.addStretch(1)
        layout.addLayout(vl_row)
        self._set_vl_dirty(False)

        if not self.CHORDS:
            with self.quiet():
                self._show_priority([0, 1, 2, 3, 4, 5])
            return
        layout.addWidget(divider())

        # ---- custom chords ----
        layout.addWidget(section_label(_t("Custom SmartChords")))
        layout.addWidget(hint_label(_t("Build a chord from the notes above (or below) its root, counted "
                                       "in semitones. A minor 7th is +3, +7, +10.")))
        chord_row = QHBoxLayout()
        chord_row.setSpacing(12)
        self.chord_list = QListWidget()
        self.chord_list.setFixedWidth(230)
        self.chord_list.setMinimumHeight(300)
        for slot in range(SC_SLOTS):
            self.chord_list.addItem(self._chord_text(slot))
        self.chord_list.currentRowChanged.connect(self._on_chord_selected)
        chord_row.addWidget(self.chord_list)

        editor = QVBoxLayout()
        self.chord_title = QLabel(_t("Chord {}").format(1))
        self.chord_title.setStyleSheet(SECTION_STYLE)
        editor.addWidget(self.chord_title)

        notes_row = QHBoxLayout()
        notes_row.addWidget(QLabel(_t("Notes")))
        self.interval_spins = []
        for _ in range(MAX_NOTES):
            spin = IntervalSpin()
            spin.setMinimumWidth(72)
            spin.valueChanged.connect(self._on_chord_edited)
            notes_row.addWidget(spin)
            self.interval_spins.append(spin)
        self.add_button = QPushButton(_t("Add note"))
        self.add_button.clicked.connect(self._on_add_note)
        self.remove_button = QPushButton(_t("Remove last"))
        self.remove_button.clicked.connect(self._on_remove_note)
        notes_row.addWidget(self.add_button)
        notes_row.addWidget(self.remove_button)
        notes_row.addStretch(1)
        editor.addLayout(notes_row)

        self.result_label = QLabel("")
        self.result_label.setStyleSheet("font-size: 11pt;")
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        editor.addWidget(self.result_label)
        self.chord_note = hint_label("")
        editor.addWidget(self.chord_note)

        buttons = QHBoxLayout()
        self.save_button = QPushButton(_t("Save chord"))
        self.save_button.clicked.connect(self._on_save_chord)
        self.clear_button = QPushButton(_t("Clear chord"))
        self.clear_button.setToolTip(_t("Empty this chord on the keyboard."))
        self.clear_button.clicked.connect(self._on_clear_chord)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        editor.addLayout(buttons)
        editor.addStretch(1)
        chord_row.addLayout(editor, 1)
        layout.addLayout(chord_row)

        self._count = 0
        with self.quiet():
            self._show_priority([0, 1, 2, 3, 4, 5])
            self.chord_list.setCurrentRow(0)
            self._show_intervals([])

    # ---- data -------------------------------------------------------------------

    def forget(self):
        self._vl = None
        self._set_vl_dirty(False)
        if not self.CHORDS:
            return
        self._chords = {}
        self._drafts = {}
        for slot in range(SC_SLOTS):
            self.chord_list.item(slot).setText(self._chord_text(slot))

    def load(self):
        vl = self.call("vl_get")
        if vl is None:
            return False
        self._show_vl(vl)
        if not self.CHORDS:
            return True
        self._chords = {}
        self._drafts = {}
        for slot in range(SC_SLOTS):
            chord = self.call("sc_get", slot)
            if chord is None:
                return False
            self._chords[slot] = list(chord["intervals"])
        for slot in range(SC_SLOTS):
            self.chord_list.item(slot).setText(self._chord_text(slot))
        self._show_chord(self._slot())
        return True

    # ---- voice leading ----------------------------------------------------------

    def _set_vl_dirty(self, dirty):
        self._vl_dirty = dirty
        self.vl_save_button.setEnabled(dirty)
        self.vl_note.setText(_t("Not saved yet.") if dirty else "")

    def _show_vl(self, vl):
        self._vl = vl
        self._set_vl_dirty(False)
        with self.quiet():
            for combo, rule in zip(self.rule_combos, vl["rules"]):
                combo.set_data(rule, _t("Rule {}"))
            self._show_priority(vl["priority"])

    def _show_priority(self, priority):
        keep = self.priority_list.currentItem().data(Qt.UserRole) if self.priority_list.currentItem() else None
        self.priority_list.clear()
        for place, voice in enumerate(priority):
            name = _t(VOICES[voice]) if voice < len(VOICES) else _t("Voice {}").format(voice + 1)
            item = QListWidgetItem("{}.  {}".format(place + 1, name))
            item.setData(Qt.UserRole, voice)
            self.priority_list.addItem(item)
            if voice == keep:
                self.priority_list.setCurrentRow(place)
        if self.priority_list.currentRow() < 0 and self.priority_list.count():
            self.priority_list.setCurrentRow(0)
        self._sync_priority_buttons()

    def _priority(self):
        return [self.priority_list.item(row).data(Qt.UserRole) for row in range(self.priority_list.count())]

    def _sync_priority_buttons(self, *_):
        row = self.priority_list.currentRow()
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < self.priority_list.count() - 1)

    def _on_vl_save(self):
        if not self.ready() or self._vl is None:
            return
        result = self.call("vl_set", [combo.currentData() or 0 for combo in self.rule_combos],
                           self._priority())
        if result is None:
            self.refused()
        else:
            self._show_vl(result)
            self.saved()

    def _on_vl_read(self):
        if not self.ready():
            return
        vl = self.call("vl_get")
        if vl is None:
            self.set_status(_t("The keyboard did not answer. Check the connection, then press "
                               "Read from keyboard."), problem=True)
        else:
            self._show_vl(vl)
            self.set_status(_t("Read from the keyboard."))

    def _on_vl_edited(self, *_):
        if not self.ready() or self._vl is None:
            return
        self._set_vl_dirty(True)

    def _move_priority(self, step):
        row = self.priority_list.currentRow()
        target = row + step
        if not self.ready() or self._vl is None or row < 0 or not 0 <= target < self.priority_list.count():
            return
        priority = self._priority()
        priority[row], priority[target] = priority[target], priority[row]
        with self.quiet():
            self._show_priority(priority)
            self.priority_list.setCurrentRow(target)
        self._sync_priority_buttons()
        self._set_vl_dirty(True)

    def _on_vl_reset(self):
        if not self.ready():
            return
        result = self.call("vl_reset")
        if result is None:
            self.refused()
        else:
            self._show_vl(result)
            self.set_status(_t("Voice leading is back to its defaults."))

    # ---- custom chords ----------------------------------------------------------

    def _slot(self):
        return max(0, self.chord_list.currentRow())

    def _chord_text(self, slot):
        text = _t("Chord {}").format(slot + 1)
        if slot in getattr(self, "_drafts", {}):
            return text + "  —  " + _t("not saved")
        intervals = getattr(self, "_chords", {}).get(slot)
        if intervals is None:
            return text
        return text + "  —  " + (chord_notes(intervals) if intervals else _t("Empty"))

    def _intervals(self):
        return [spin.value() for spin in self.interval_spins[:self._count]]

    def _problem(self, intervals):
        if 0 in intervals:
            return _t("0 is the root itself, which is always part of the chord. Use another number.")
        if len(set(intervals)) != len(intervals):
            return _t("Each note can only be used once.")
        return ""

    def _show_intervals(self, intervals):
        with self.quiet():
            self._count = min(len(intervals), MAX_NOTES)
            for index, spin in enumerate(self.interval_spins):
                spin.setVisible(index < self._count)
                if index < self._count:
                    spin.setValue(intervals[index])
        self._show_result()

    def _show_result(self):
        slot = self._slot()
        intervals = self._intervals()
        problem = self._problem(intervals)
        if not intervals:
            self.result_label.setText(_t("Empty. Press Add note to start a chord."))
        elif problem:
            self.result_label.setText(problem)
        else:
            self.result_label.setText(_t("On a C root: {}").format(chord_notes(intervals)))
        self.chord_note.setText(_t("Not saved yet. Press Save chord to keep these changes.")
                                if slot in self._drafts else "")
        self.add_button.setEnabled(self._count < MAX_NOTES)
        self.remove_button.setEnabled(self._count > 0)
        self.save_button.setEnabled(bool(intervals) and not problem)
        self.clear_button.setEnabled(bool(self._chords.get(slot)) or slot in self._drafts)

    def _show_chord(self, slot):
        self.chord_title.setText(_t("Chord {}").format(slot + 1))
        intervals = self._drafts.get(slot)
        if intervals is None:
            intervals = self._chords.get(slot, [])
        self._show_intervals(intervals)

    def _on_chord_selected(self, row):
        if row < 0 or self.is_quiet():
            return
        self._show_chord(row)

    def _on_chord_edited(self, *_):
        if self.is_quiet():
            return
        slot = self._slot()
        self._drafts[slot] = self._intervals()
        self.chord_list.item(slot).setText(self._chord_text(slot))
        self._show_result()

    def _on_add_note(self):
        if self._count >= MAX_NOTES:
            return
        used = set(self._intervals())
        new = next((value for value in NEW_INTERVALS if value not in used), None)
        if new is None:
            new = next(value for value in range(1, 37) if value not in used)
        self._show_intervals(self._intervals() + [new])
        self._on_chord_edited()
        self.interval_spins[self._count - 1].setFocus()

    def _on_remove_note(self):
        if self._count <= 0:
            return
        self._show_intervals(self._intervals()[:-1])
        self._on_chord_edited()

    def _store_chord(self, slot, result):
        self._drafts.pop(slot, None)
        self._chords[slot] = list(result["intervals"])
        self.chord_list.item(slot).setText(self._chord_text(slot))
        self._show_chord(slot)

    def _on_save_chord(self):
        slot = self._slot()
        intervals = self._intervals()
        if not self.ready() or not intervals or self._problem(intervals):
            return
        result = self.call("sc_set", slot, intervals)
        if result is None:
            self.refused()
            return
        self._store_chord(slot, result)
        self.saved()

    def _on_clear_chord(self):
        slot = self._slot()
        if not self.ready():
            return
        result = self.call("sc_set", slot, [])
        if result is None:
            self.refused()
            return
        self._store_chord(slot, result)
        self.set_status(_t("The chord is now empty."))


class VoiceLeadingPage(SmartChordPage):
    """The voice leading part on its own (Settings > Voice Leading)."""

    TITLE = "Voice Leading"
    DESCRIPTION = ("Voice leading decides how the notes of one SmartChord move to the next. Nothing "
                   "is changed on the keyboard until you press Save.")
    CHORDS = False

    def build(self, layout):
        super().build(layout)
        self.read_button.hide()         # the Read from keyboard beside Save does the same
