# SPDX-License-Identifier: GPL-2.0-or-later
"""SmartChord Sets: what each of the keyboard's 12 sets plays, and up to 8
custom sets of your own: a chord and an inversion for every note, saved on the
keyboard as you change them. The built-in sets need no connection; custom sets
need firmware with the custom-set command (AppConfig.cset_get / cset_set)."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QScrollArea,
                             QFrame, QPushButton, QMenu, QMessageBox, QSizePolicy)

from editor.qb_pages.common import TITLE_STYLE, DESCRIPTION_STYLE, SECTION_STYLE, HINT_STYLE, Combo
from editor.smartchord_sets import (SETS, KEY_NAMES, CUSTOM_SET_COUNT, CHORD_NONE, CHORD_CUSTOM, CHORDS,
                                    CHORD_GROUPS, NEW_SET, MAX_INVERSION, custom_set_name, chord_label,
                                    chord_intervals, voicing, notes_text)
from protocol.app_config import SC_SLOTS
from util import tr

INVERSION_NAMES = ["Root position", "1st inversion", "2nd inversion", "3rd inversion", "4th inversion",
                   "5th inversion", "6th inversion", "7th inversion", "8th inversion"]
NOTES_HEADER = "Notes (C key at C3)"
BUILTIN, CUSTOM, ADD = "builtin", "custom", "add"


def _t(text):
    return tr("SmartChordSetsPage", text)


class SmartChordSetsPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.app_config = None
        self.custom_ok = False          # the keyboard has the custom-set command
        self.csets = {}                 # custom set index -> [(chord, inversion)] x 12 (made sets only)
        self.custom_chords = {}         # custom chord slot -> intervals (made ones only)
        self.current = (BUILTIN, 0)     # what the right-hand side shows

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)

        title = QLabel(_t("SmartChord Sets"))
        title.setStyleSheet(TITLE_STYLE)
        layout.addWidget(title)
        description = QLabel(_t(
            "A SmartChord Set gives every key its own chord. Press a set's key to turn it on (press it "
            "again to turn it off): the white keys then play the set's main chords and the black keys "
            "its colour chords. The C key always plays a C chord and the A key an A chord, whether "
            "you play in C major or A minor; transpose moves the whole set (the C key on +2 plays "
            "the C chord a tone up). Every chord plays in root position on its key, so the chords "
            "climb as you go up the keys; a chord built over its key (A7/C#, G/B) keeps that key in "
            "the bass. Choose an inversion on the set's QuickBuild to invert every chord alike; with "
            "voice leading on, voice leading chooses. The screen names each chord as it sounds. "
            "With + Custom SmartChord Set you can make up to 8 sets of your own."))
        description.setWordWrap(True)
        description.setStyleSheet(DESCRIPTION_STYLE)
        layout.addWidget(description)
        where = QLabel(_t(
            "Put a set on a key in the keymap (the SmartChord tab, Sets column), or on a QuickBuild: "
            "rebind its function to SmartChord Set in the QuickBuild list, or on the keyboard under "
            "Smartchord > Sets."))
        where.setWordWrap(True)
        where.setStyleSheet(HINT_STYLE)
        layout.addWidget(where)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.list = QListWidget()
        self.list.setFixedWidth(235)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentItemChanged.connect(lambda item, _: self.on_item(item))
        self.list.itemClicked.connect(self.on_click)
        row.addWidget(self.list, 0, Qt.AlignTop)

        right = QVBoxLayout()
        head = QHBoxLayout()
        self.name_label = QLabel("")
        self.name_label.setStyleSheet(SECTION_STYLE)
        head.addWidget(self.name_label)
        head.addStretch(1)
        self.delete_button = QPushButton(_t("Delete this set"))
        self.delete_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.delete_button.clicked.connect(self.delete_set)
        head.addWidget(self.delete_button)
        right.addLayout(head)
        self.blurb_label = QLabel("")
        self.blurb_label.setWordWrap(True)
        self.blurb_label.setStyleSheet(DESCRIPTION_STYLE)
        right.addWidget(self.blurb_label)
        self.table = QTableWidget(len(KEY_NAMES), 3)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        right.addWidget(self.table)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(HINT_STYLE)
        right.addWidget(self.status_label)
        right.addStretch(1)
        row.addLayout(right, 1)
        layout.addLayout(row)
        layout.addStretch(1)

        self.rebuild_list()

    # ---- keyboard ---------------------------------------------------------------

    def set_app_config(self, app_config):
        self.app_config = app_config
        self.custom_ok = False
        self.csets = {}
        self.custom_chords = {}
        self.set_status("")
        self.rebuild_list(self.current if self.current[0] == BUILTIN else (BUILTIN, 0))
        if app_config is not None and self.isVisible():
            self.shown()

    def shown(self):
        """Read the custom sets (and the custom chords they can use) each time
        the page comes into view: the chords may have changed on the SmartChord tab."""
        if self.app_config is None:
            return
        first = self.app_config.cset_get(0) if self.app_config.supported() else None
        if first is None:
            self.custom_ok = False
            self.csets = {}
            self.rebuild_list(self.current if self.current[0] == BUILTIN else (BUILTIN, 0))
            return
        self.custom_ok = True
        csets = {}
        for index in range(CUSTOM_SET_COUNT):
            reply = first if index == 0 else self.app_config.cset_get(index)
            if reply is not None and reply["used"]:
                csets[index] = list(reply["entries"])
        chords = {}
        for slot in range(SC_SLOTS):
            reply = self.app_config.sc_get(slot)
            if reply and reply["intervals"]:
                chords[slot] = list(reply["intervals"])
        self.csets, self.custom_chords = csets, chords
        current = self.current
        if current[0] == CUSTOM and current[1] not in self.csets:
            current = (BUILTIN, 0)
        self.rebuild_list(current)

    def set_status(self, text):
        self.status_label.setText(text)

    # ---- the list -----------------------------------------------------------------

    def _add_item(self, text, data):
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, data)
        self.list.addItem(item)
        return item

    def rebuild_list(self, select=(BUILTIN, 0)):
        self.list.blockSignals(True)
        self.list.clear()
        for index, (name, _, _) in enumerate(SETS):
            self._add_item(_t(name), (BUILTIN, index))
        for index in sorted(self.csets):
            self._add_item(_t(custom_set_name(index)), (CUSTOM, index))
        add = self._add_item(_t("+ Custom SmartChord Set"), (ADD, None))
        font = add.font()
        font.setBold(True)
        add.setFont(font)
        add.setForeground(self.palette().highlight().color())
        if not self.custom_ok:
            add.setFlags(Qt.NoItemFlags)
            add.setToolTip(_t("Connect a keyboard with up-to-date firmware to make custom sets.")
                           if self.app_config is not None else _t("Connect the keyboard to make custom sets."))
        elif len(self.csets) >= CUSTOM_SET_COUNT:
            add.setFlags(Qt.NoItemFlags)
            add.setToolTip(_t("All 8 custom sets are made: delete one to make another."))
        else:
            add.setFlags(Qt.ItemIsEnabled)          # clicked, never selected
            add.setToolTip(_t("Make a new set of your own."))
        self.list.setFixedHeight(self.list.sizeHintForRow(0) * self.list.count()
                                 + 2 * self.list.frameWidth() + 4)
        row = 0
        for index in range(self.list.count()):
            if self.list.item(index).data(Qt.UserRole) == select:
                row = index
        self.list.setCurrentRow(row)
        self.list.blockSignals(False)
        self.on_item(self.list.item(row))

    def on_item(self, item):
        if item is None:
            return
        kind, index = item.data(Qt.UserRole)
        if kind == ADD:
            return
        self.current = (kind, index)
        if kind == BUILTIN:
            self.show_builtin(index)
        else:
            self.show_custom(index)

    def on_click(self, item):
        if item is not None and item.data(Qt.UserRole)[0] == ADD and (item.flags() & Qt.ItemIsEnabled):
            self.add_set()

    # ---- the table ----------------------------------------------------------------

    def _reset_table(self, headers):
        self.table.clearContents()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels([_t(text) for text in headers])
        header = self.table.horizontalHeader()
        for column in range(len(headers)):
            header.setSectionResizeMode(column, QHeaderView.Stretch if column == len(headers) - 1
                                        else QHeaderView.ResizeToContents)

    def _fit_table(self):
        self.table.resizeRowsToContents()
        height = self.table.horizontalHeader().height() + 4
        for key in range(self.table.rowCount()):
            height += self.table.rowHeight(key)
        self.table.setFixedHeight(height)

    def _note_item(self, key, bold=False):
        item = QTableWidgetItem(KEY_NAMES[key])
        if "#" in KEY_NAMES[key]:
            item.setForeground(self.palette().highlight().color())
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        return item

    def show_builtin(self, index):
        name, blurb, chords = SETS[index]
        self.name_label.setText(_t(name))
        self.blurb_label.setText(_t(blurb))
        self.delete_button.hide()
        self._reset_table(["Note", "Chord", NOTES_HEADER])
        for key, (chord, notes) in enumerate(chords):
            black = "#" in KEY_NAMES[key]
            items = (self._note_item(key), QTableWidgetItem(chord), QTableWidgetItem(notes))
            for column, item in enumerate(items):
                if black:       # the colour chords, on the black keys
                    item.setForeground(self.palette().highlight().color())
                if column == 1:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(key, column, item)
        self._fit_table()

    def show_custom(self, index):
        entries = self.csets[index]
        self.name_label.setText(_t(custom_set_name(index)))
        self.blurb_label.setText(_t(
            "Your own set: choose a chord for each note (it plays on that note) and the inversion it "
            "plays in. Each change is saved on the keyboard straight away. Transpose moves the whole "
            "set; a QuickBuild's Inversion adds to these."))
        self.delete_button.show()
        self._reset_table(["Note", "Chord", "Inversion", NOTES_HEADER])
        for key, (chord, inversion) in enumerate(entries):
            self.table.setItem(key, 0, self._note_item(key, bold=True))
            button = QPushButton(_t("None (the note alone)") if chord == CHORD_NONE else chord_label(key, chord))
            button.setToolTip(_t("Choose the chord this note plays."))
            button.clicked.connect(lambda _, k=key: self.pick_chord(k))
            self.table.setCellWidget(key, 1, button)
            combo = Combo()
            combo.setMinimumContentsLength(12)
            count = len(chord_intervals(chord, self.custom_chords)) + 1
            for n in range(max(count, inversion + 1) if count > 1 else 1):
                combo.addItem(_t(INVERSION_NAMES[min(n, MAX_INVERSION)]), n)
            combo.setCurrentIndex(max(0, combo.findData(inversion)))
            combo.setEnabled(count > 1)
            combo.currentIndexChanged.connect(lambda _, k=key, c=combo: self.set_entry(k, inversion=c.currentData()))
            self.table.setCellWidget(key, 2, combo)
            self.table.setItem(key, 3, QTableWidgetItem(notes_text(voicing(key, chord, inversion, self.custom_chords))))
        self._fit_table()

    # ---- editing a custom set -------------------------------------------------------

    def pick_chord(self, key):
        kind, index = self.current
        if kind != CUSTOM or index not in self.csets:
            return
        menu = QMenu(self)
        none = menu.addAction(_t("None (the note alone)"))
        none.setData(CHORD_NONE)
        menu.addSeparator()
        for title, chords in CHORD_GROUPS:
            sub = menu.addMenu(_t(title))
            for chord in chords:
                action = sub.addAction("{}    {}".format(chord_label(key, chord), CHORDS[chord][2]))
                action.setData(chord)
        custom = menu.addMenu(_t("Custom"))
        for slot in sorted(self.custom_chords):
            notes = notes_text(voicing(key, CHORD_CUSTOM + slot, 0, self.custom_chords))
            action = custom.addAction(_t("Custom {}: {}").format(slot + 1, notes))
            action.setData(CHORD_CUSTOM + slot)
        if not self.custom_chords:
            custom.setTitle(_t("Custom (make one on the SmartChord tab)"))
            custom.setEnabled(False)
        button = self.table.cellWidget(key, 1)
        chosen = menu.exec_(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen is not None and chosen.data() is not None:
            self.set_entry(key, chord=chosen.data())

    def set_entry(self, key, chord=None, inversion=None):
        kind, index = self.current
        if kind != CUSTOM or index not in self.csets or self.app_config is None:
            return
        entries = list(self.csets[index])
        old_chord, old_inversion = entries[key]
        new_chord = old_chord if chord is None else chord
        new_inversion = old_inversion if inversion is None else inversion
        if chord is not None:       # a smaller chord keeps the inversion it can play
            new_inversion = min(new_inversion, len(chord_intervals(new_chord, self.custom_chords)))
        if (new_chord, new_inversion) == (old_chord, old_inversion):
            return
        entries[key] = (new_chord, new_inversion)
        reply = self.app_config.cset_set(index, True, entries)
        if reply is None:
            self.set_status(_t("The keyboard did not save that."))
            reply = self.app_config.cset_get(index)
            if reply is not None and reply["used"]:
                self.csets[index] = list(reply["entries"])
        else:
            self.csets[index] = list(reply["entries"])
            self.set_status(_t("Saved {}: {} plays {}.").format(
                _t(custom_set_name(index)), KEY_NAMES[key],
                _t("the note alone") if new_chord == CHORD_NONE else chord_label(key, new_chord)))
        self.show_custom(index)

    def add_set(self):
        if not self.custom_ok or self.app_config is None:
            return
        free = [index for index in range(CUSTOM_SET_COUNT) if index not in self.csets]
        if not free:
            return
        index = free[0]
        reply = self.app_config.cset_set(index, True, NEW_SET)
        if reply is None or not reply["used"]:
            self.set_status(_t("The keyboard did not make the new set."))
            return
        self.csets[index] = list(reply["entries"])
        self.rebuild_list((CUSTOM, index))
        self.set_status(_t("{} made: the white keys start as the triads of C major, the black keys "
                           "as the note alone. Choose a chord and an inversion for each note.")
                        .format(_t(custom_set_name(index))))

    def delete_set(self):
        kind, index = self.current
        if kind != CUSTOM or index not in self.csets or self.app_config is None:
            return
        name = _t(custom_set_name(index))
        answer = QMessageBox.question(
            self, _t("Delete set"),
            _t("Delete {}? Keys and QuickBuilds that play it then play the notes alone, "
               "until a new set is made in its place.").format(name))
        if answer != QMessageBox.Yes:
            return
        reply = self.app_config.cset_set(index, False, [(0, 0)] * 12)
        if reply is None:
            self.set_status(_t("The keyboard did not delete it."))
            return
        del self.csets[index]
        self.rebuild_list((BUILTIN, 0))
        self.set_status(_t("{} deleted.").format(name))
