# SPDX-License-Identifier: GPL-2.0-or-later
"""DrumLIVE: the 48 QuickBuild slots, each remembering which of the drum
machine's 28 voicings play and how loud."""

from PyQt5.QtCore import QRegExp, QTimer
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QLineEdit, QWidget

from editor.qb_pages.common import (QbPage, Combo, ModeGrid, Loader, hint_label, section_label, divider)
from protocol.app_config import DL_SLOTS, DL_VOICINGS
from util import tr


def _t(text):
    return tr("DrumLivePage", text)


class DrumLivePage(QbPage):

    TITLE = "DrumLIVE"
    DESCRIPTION = ("DrumLIVE chooses which drum sounds of the playing pattern are heard: each one can be "
                   "On, Off, Quiet or Loud. Each slot remembers one set-up, so a QuickBuild key can "
                   "bring it back with one press. A slot is only changed when you press Save slot.")

    def build(self, layout):
        self._state = None
        self._drafts = {}           # slot -> (snapshot, name) edited here but not saved yet
        self._slot_loader = Loader(self, lambda slot: self.call("dl_slot_get", slot), batch=6)
        self._slot_loader.loaded.connect(self._on_slot_loaded)
        self._poll = QTimer(self)
        self._poll.setSingleShot(True)
        self._poll.setInterval(1000)
        self._poll.timeout.connect(self._poll_state)

        # ---- what is playing now ----
        preset_row = QHBoxLayout()
        preset_label = QLabel(_t("Preset"))
        self.preset_combo = Combo()
        self.preset_combo.setMinimumContentsLength(16)
        preset_label.setBuddy(self.preset_combo)
        self.apply_button = QPushButton(_t("Apply"))
        self.apply_button.setToolTip(_t("Set every drum sound the way this preset has it."))
        self.apply_button.clicked.connect(self._on_apply_preset)
        preset_row.addWidget(preset_label)
        preset_row.addWidget(self.preset_combo)
        preset_row.addWidget(self.apply_button)
        preset_row.addSpacing(12)
        self.live_note = QLabel("")
        self.live_note.setWordWrap(True)
        self.live_note.setStyleSheet("font-weight: bold;")
        preset_row.addWidget(self.live_note, 1)
        self.live_grid = ModeGrid()
        self.live_grid.changed.connect(self._on_live_changed)

        # What is playing now is still read (Copy uses it) but is not shown:
        # the page is the QuickBuild slots alone.
        self._live_holder = QWidget(self)
        self._live_holder.hide()
        preset_row.addWidget(self.live_grid)
        self._live_holder.setLayout(preset_row)

        # ---- the QuickBuild slots ----
        layout.addWidget(section_label(_t("QuickBuild slots")))
        slot_row = QHBoxLayout()
        slot_label = QLabel(_t("Slot"))
        self.slot_combo = Combo()
        self.slot_combo.setMinimumContentsLength(24)
        self.slot_combo.setMaxVisibleItems(16)
        for slot in range(DL_SLOTS):
            self.slot_combo.addItem(self._slot_text(slot), slot)
        self.slot_combo.currentIndexChanged.connect(self._on_slot_selected)
        slot_label.setBuddy(self.slot_combo)
        name_label = QLabel(_t("Name"))
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(15)
        self.name_edit.setValidator(QRegExpValidator(QRegExp("[ -~]{0,15}"), self.name_edit))
        self.name_edit.setFixedWidth(190)
        self.name_edit.setToolTip(_t("Up to 15 letters, numbers or symbols."))
        self.name_edit.textEdited.connect(self._on_slot_edited)
        name_label.setBuddy(self.name_edit)
        slot_row.addWidget(slot_label)
        slot_row.addWidget(self.slot_combo)
        slot_row.addSpacing(12)
        slot_row.addWidget(name_label)
        slot_row.addWidget(self.name_edit)
        slot_row.addStretch(1)
        layout.addLayout(slot_row)

        self.slot_grid = ModeGrid()
        self.slot_grid.changed.connect(self._on_slot_edited)
        layout.addWidget(self.slot_grid)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton(_t("Copy current state into this slot"))
        self.copy_button.setToolTip(_t("Fill the slot with the way the drum sounds are set on the "
                                       "keyboard right now. Press Save slot to keep it."))
        self.copy_button.clicked.connect(self._on_copy_live)
        self.save_button = QPushButton(_t("Save slot"))
        self.save_button.clicked.connect(self._on_save_slot)
        self.clear_button = QPushButton(_t("Clear slot"))
        self.clear_button.setToolTip(_t("Empty this slot on the keyboard."))
        self.clear_button.clicked.connect(self._on_clear_slot)
        self.slot_note = hint_label("")
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.clear_button)
        buttons.addWidget(self.slot_note, 1)
        layout.addLayout(buttons)

    # ---- data -------------------------------------------------------------------

    def forget(self):
        self._poll.stop()
        self._slot_loader.reset()
        self._state = None
        self._drafts = {}
        self.preset_combo.clear()
        for slot in range(DL_SLOTS):
            self.slot_combo.setItemText(slot, self._slot_text(slot))
        self.live_note.setText("")
        self.slot_note.setText("")

    def load(self):
        state = self.call("dl_get")
        if state is None:
            return False
        names = self.call("dl_preset_names") or []
        chosen = max(0, self.preset_combo.currentIndex())
        self.preset_combo.clear()
        for number, name in enumerate(names):
            self.preset_combo.addItem(name or _t("Preset {}").format(number + 1), number)
        if names:
            self.preset_combo.setCurrentIndex(min(chosen, len(names) - 1))
        self._show_state(state)

        self._slot_loader.reset()
        self._drafts = {}
        for slot in range(DL_SLOTS):
            self.slot_combo.setItemText(slot, self._slot_text(slot))
        self._show_slot(self._slot())
        self._slot_loader.start(DL_SLOTS)
        return True

    # ---- playing now ------------------------------------------------------------

    def _show_state(self, state):
        self._state = state
        with self.quiet():
            self.live_grid.set_modes(state["edit"])
        authoring = state["authoring"]
        self.live_grid.setEnabled(not authoring)
        self.apply_button.setEnabled(not authoring and self.preset_combo.count() > 0)
        self.preset_combo.setEnabled(not authoring and self.preset_combo.count() > 0)
        if authoring:
            self.live_note.setText(_t("The keyboard's own DrumLIVE menu is open, so editing here is "
                                      "paused until it is closed."))
        elif state["pending"]:
            self.live_note.setText(_t("Waiting for the next loop to apply"))
        else:
            self.live_note.setText("")
        if authoring or state["pending"]:
            self._poll.start()
        else:
            self._poll.stop()

    def _poll_state(self):
        """While a change is waiting (or the keyboard's menu is open), look again."""
        if self.app_config is None or self._state is None:
            return
        if not self.isVisible():
            return
        state = self.call("dl_get")
        if state is not None:
            self._show_state(state)

    def _on_apply_preset(self):
        if not self.ready() or self.preset_combo.currentData() is None:
            return
        state = self.call("dl_apply_preset", self.preset_combo.currentData())
        self._after_live_write(state)

    def _on_live_changed(self):
        if not self.ready() or self._state is None:
            return
        state = self.call("dl_set", self.live_grid.modes())
        self._after_live_write(state)

    def _after_live_write(self, state):
        if state is None:
            self.refused()
            fresh = self.call("dl_get")         # show what the keyboard really has
            if fresh is not None:
                self._show_state(fresh)
            elif self._state is not None:
                self._show_state(self._state)
        else:
            self._show_state(state)
            self.saved()

    # ---- slots ------------------------------------------------------------------

    def _slot(self):
        return max(0, self.slot_combo.currentIndex())

    def _slot_text(self, slot):
        text = _t("Slot {}").format(slot + 1)
        loader = getattr(self, "_slot_loader", None)
        data = loader.values.get(slot) if loader is not None else None
        if data is not None:
            text += "  —  " + (data["name"] or (_t("Unnamed") if data["configured"] else _t("Empty")))
        if slot in getattr(self, "_drafts", {}):
            text += "  " + _t("(not saved)")
        return text

    def _on_slot_loaded(self, slot):
        self.slot_combo.setItemText(slot, self._slot_text(slot))

    def _on_slot_selected(self, _row):
        if self.is_quiet():
            return
        self._show_slot(self._slot())

    def _show_slot(self, slot):
        data = self._slot_loader.get(slot) if self.app_config is not None else None
        draft = self._drafts.get(slot)
        with self.quiet():
            if draft is not None:
                self.slot_grid.set_modes(draft[0])
                self.name_edit.setText(draft[1])
            elif data is not None:
                self.slot_grid.set_modes(data["snapshot"])
                self.name_edit.setText(data["name"])
            else:
                self.slot_grid.set_modes([0] * DL_VOICINGS)
                self.name_edit.setText("")
        self._show_slot_note(slot)

    def _show_slot_note(self, slot):
        data = self._slot_loader.values.get(slot)
        if slot in self._drafts:
            self.slot_note.setText(_t("Not saved yet. Press Save slot to keep these changes."))
        elif data is not None and not data["configured"]:
            self.slot_note.setText(_t("This slot is empty."))
        else:
            self.slot_note.setText("")
        self.clear_button.setEnabled(slot in self._drafts or (data is not None and data["configured"]))

    def _on_slot_edited(self, *_):
        if self.is_quiet():
            return
        slot = self._slot()
        self._drafts[slot] = (self.slot_grid.modes(), self.name_edit.text())
        self.slot_combo.setItemText(slot, self._slot_text(slot))
        self._show_slot_note(slot)

    def _on_copy_live(self):
        if self.is_quiet():
            return
        state = self.call("dl_get")             # the keyboard's set-up as it is this moment
        if state is None:
            self.set_status(_t("The keyboard did not answer."), problem=True)
            return
        self._show_state(state)
        # "edit" is how the sounds are set (what the grid above shows; it takes
        # effect at the next loop when a change is waiting). While a slot is
        # being made in the keyboard's own menu, though, "edit" is that
        # unfinished slot, and how the sounds are set now is "active".
        with self.quiet():
            self.slot_grid.set_modes(state["active"] if state["authoring"] else state["edit"])
        self._on_slot_edited()

    def _on_save_slot(self):
        if not self.ready():
            return
        slot = self._slot()
        result = self.call("dl_slot_set", slot, self.slot_grid.modes(), self.name_edit.text().strip())
        if result is None:
            self.refused()
            return
        self._drafts.pop(slot, None)
        self._slot_loader.put(slot, result)
        self._show_slot(slot)
        self.saved()

    def _on_clear_slot(self):
        if not self.ready():
            return
        slot = self._slot()
        result = self.call("dl_slot_set", slot, [0] * DL_VOICINGS, "")     # all On, no name = empty
        if result is None:
            self.set_status(_t("The keyboard did not clear the slot. If the slot is open in the "
                               "keyboard's own DrumLIVE menu, close the menu and try again."), problem=True)
            return
        self._drafts.pop(slot, None)
        self._slot_loader.put(slot, result)
        self._show_slot(slot)
        self.set_status(_t("The slot is now empty."))
