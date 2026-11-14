# SPDX-License-Identifier: GPL-2.0-or-later
"""AutoFader: forty slots, each a controller (CC) sweep that a key starts."""

from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QFormLayout, QGroupBox, QListWidget, QLabel,
                             QCheckBox, QPushButton, QWidget)

from editor.qb_pages.common import (QbPage, Combo, Spin, Loader, channel_combo, hint_label, left,
                                    SECTION_STYLE)
from protocol.app_config import FD_SLOTS
from util import tr

FLAG_SAVED, FLAG_SYNCED, FLAG_DEFER = 1, 2, 4
START_LIVE = 128
STYLES = ["One Shot", "One Shot + Reverse", "Loop", "Loop + Reverse"]
RATES = ["16 bars", "8 bars", "4 bars", "2 bars", "1 bar", "1/2 bar", "1/4 bar", "1/8 bar", "1/16 bar"]
NEW_SLOT = {"cc": 1, "channel": 0, "start": 0, "end": 127, "style": 0, "rate": 4, "duration_ms": 1000}


def _t(text):
    return tr("AutoFaderPage", text)


class AutoFaderPage(QbPage):

    TITLE = "AutoFader"
    DESCRIPTION = ("Each of the 40 slots moves a controller (CC) smoothly from one value to another when "
                   "its key is pressed. Pick a slot on the left and set it up on the right. Nothing is "
                   "sent to the keyboard until you press Save slot.")

    def build(self, layout):
        self._drafts = {}           # slot -> settings edited here but not saved yet
        self._loader = Loader(self, lambda slot: self.call("fd_get", slot), batch=8)
        self._loader.loaded.connect(self._on_slot_loaded)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.slot_list = QListWidget()
        self.slot_list.setFixedWidth(210)
        self.slot_list.setMinimumHeight(380)
        for slot in range(FD_SLOTS):
            self.slot_list.addItem(self._slot_text(slot))
        self.slot_list.currentRowChanged.connect(self._on_slot_selected)
        row.addWidget(self.slot_list)

        right = QVBoxLayout()
        self.slot_title = QLabel(_t("Fader {}").format(1))
        self.slot_title.setStyleSheet(SECTION_STYLE)
        right.addWidget(self.slot_title)
        self.slot_note = hint_label("")
        right.addWidget(self.slot_note)

        box = QGroupBox()
        form = QFormLayout(box)
        self.cc = Spin(0, 127)
        self.cc.setToolTip(_t("The controller number to move, 0 to 127."))
        self.channel = channel_combo(first_is_master=True)

        start_row = QHBoxLayout()
        self.start_mode = Combo()
        self.start_mode.setMinimumContentsLength(10)
        self.start_mode.addItem(_t("Live value"), True)
        self.start_mode.addItem(_t("Fixed value"), False)
        self.start_mode.setToolTip(_t("Live value starts from wherever the controller is at that moment."))
        self.start = Spin(0, 127)
        start_row.addWidget(self.start_mode)
        start_row.addWidget(self.start)
        start_row.addStretch(1)
        self.end = Spin(0, 127)
        self.style = Combo()
        self.style.setMinimumContentsLength(18)
        for index, name in enumerate(STYLES):
            self.style.addItem(_t(name), index)

        self.synced = QCheckBox(_t("Follow the tempo"))
        self.synced.setToolTip(_t("On: the sweep lasts a number of bars. Off: it lasts a set time."))
        self.rate = Combo()
        for index, name in enumerate(RATES):
            self.rate.addItem(_t(name), index)
        self.duration = Spin(50, 64000, step=50, suffix=" ms")
        self.duration.setMinimumWidth(120)
        self.defer = QCheckBox(_t("Wait for the next loop to start"))
        self.defer.setToolTip(_t("On: after the key is pressed, the sweep starts together with the "
                                 "next loop instead of immediately."))

        form.addRow(_t("Controller (CC)"), left(self.cc))
        form.addRow(_t("Channel"), self.channel)
        form.addRow(_t("Start"), start_row)
        form.addRow(_t("End"), left(self.end))
        form.addRow(_t("Style"), self.style)
        form.addRow(_t("Timing"), self.synced)
        length_row = QHBoxLayout()
        length_row.addWidget(self.rate)
        length_row.addWidget(self.duration)
        length_row.addStretch(1)
        form.addRow(_t("Length"), length_row)
        form.addRow("", self.defer)
        right.addWidget(box)

        buttons = QHBoxLayout()
        self.save_button = QPushButton(_t("Save slot"))
        self.save_button.clicked.connect(self._on_save)
        self.clear_button = QPushButton(_t("Clear slot"))
        self.clear_button.setToolTip(_t("Empty this slot on the keyboard."))
        self.clear_button.clicked.connect(self._on_clear)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        right.addLayout(buttons)
        right.addStretch(1)
        holder = QWidget()
        holder.setLayout(right)
        holder.setMaximumWidth(560)
        right.setContentsMargins(0, 0, 0, 0)
        row.addWidget(holder, 1)
        row.addStretch(1)
        layout.addLayout(row)

        for spin in (self.cc, self.start, self.end, self.duration):
            spin.valueChanged.connect(self._on_edited)
        for combo in (self.channel, self.start_mode, self.style, self.rate):
            combo.currentIndexChanged.connect(self._on_edited)
        for check in (self.synced, self.defer):
            check.toggled.connect(self._on_edited)

        with self.quiet():
            self.slot_list.setCurrentRow(0)
            self._sync_visibility()

    # ---- data -------------------------------------------------------------------

    def forget(self):
        self._loader.reset()
        self._drafts = {}
        for slot in range(FD_SLOTS):
            self.slot_list.item(slot).setText(self._slot_text(slot))
        self.slot_note.setText("")

    def load(self):
        self._loader.reset()
        self._drafts = {}
        for slot in range(FD_SLOTS):
            self.slot_list.item(slot).setText(self._slot_text(slot))
        slot = self._slot()
        if self._loader.get(slot) is None:
            return False
        self._show(slot)
        self._loader.start(FD_SLOTS)
        return True

    def _slot(self):
        return max(0, self.slot_list.currentRow())

    def _slot_text(self, slot):
        text = _t("Fader {}").format(slot + 1)
        loader = getattr(self, "_loader", None)
        data = loader.values.get(slot) if loader is not None else None
        if slot in getattr(self, "_drafts", {}):
            text += "  —  " + _t("not saved")
        elif data is not None:
            text += "  —  " + (_t("CC {}").format(data["cc"]) if data["flags"] & FLAG_SAVED else _t("Empty"))
        return text

    def _on_slot_loaded(self, slot):
        self.slot_list.item(slot).setText(self._slot_text(slot))

    @staticmethod
    def _shown_settings(data):
        """What the controls show for a slot: an empty one starts from sensible values."""
        settings = dict(data)
        if not data["flags"] & FLAG_SAVED:
            settings.update(NEW_SLOT)
            settings["flags"] = data["flags"] & ~(FLAG_SYNCED | FLAG_DEFER)
        return settings

    def _show(self, slot):
        self.slot_title.setText(_t("Fader {}").format(slot + 1))
        data = self._loader.values.get(slot)
        settings = self._drafts.get(slot)
        if settings is None and data is not None:
            settings = self._shown_settings(data)
        if settings is not None:
            with self.quiet():
                self.cc.setValue(settings["cc"])
                self.channel.set_data(settings["channel"], _t("Channel {}"))
                live = settings["start"] >= START_LIVE
                self.start_mode.setCurrentIndex(0 if live else 1)
                if not live:
                    self.start.setValue(settings["start"])
                self.end.setValue(settings["end"])
                self.style.set_data(settings["style"], _t("Style {}"))
                self.synced.setChecked(bool(settings["flags"] & FLAG_SYNCED))
                self.rate.set_data(settings["rate"], _t("Length {}"))
                self.duration.setValue(settings["duration_ms"])
                self.defer.setChecked(bool(settings["flags"] & FLAG_DEFER))
                self._sync_visibility()
        self._show_note(slot)

    def _show_note(self, slot):
        data = self._loader.values.get(slot)
        if slot in self._drafts:
            self.slot_note.setText(_t("Not saved yet. Press Save slot to keep these changes."))
        elif data is not None and not data["flags"] & FLAG_SAVED:
            self.slot_note.setText(_t("This slot is empty. Set it up, then press Save slot."))
        else:
            self.slot_note.setText("")
        self.clear_button.setEnabled(data is not None and bool(data["flags"] & FLAG_SAVED))

    def _sync_visibility(self):
        synced = self.synced.isChecked()
        self.rate.setVisible(synced)
        self.duration.setVisible(not synced)
        self.start.setEnabled(not self.start_mode.currentData())

    def _settings(self, slot):
        """The slot as the controls have it. What the page does not show (the
        keyboard's own note-length fields) goes back as it was read."""
        base = self._drafts.get(slot) or self._loader.values.get(slot)
        if base is None:
            return None
        settings = dict(base)
        flags = (base["flags"] & ~(FLAG_SYNCED | FLAG_DEFER)) | FLAG_SAVED
        if self.synced.isChecked():
            flags |= FLAG_SYNCED
        if self.defer.isChecked():
            flags |= FLAG_DEFER
        settings["flags"] = flags
        settings["cc"] = self.cc.value()
        settings["channel"] = self.channel.currentData() or 0
        settings["start"] = START_LIVE if self.start_mode.currentData() else self.start.value()
        settings["end"] = self.end.value()
        settings["style"] = self.style.currentData() or 0
        settings["rate"] = self.rate.currentData() or 0
        settings["duration_ms"] = max(50, min(64000, int(round(self.duration.value() / 50.0)) * 50))
        return settings

    # ---- the user's edits -------------------------------------------------------

    def _on_slot_selected(self, row):
        if row < 0 or self.is_quiet():
            return
        if self.app_config is not None and self._loader.get(row) is None:
            self.set_status(_t("The keyboard did not answer. Check the connection, then press "
                               "Read from keyboard."), problem=True)
        self._show(row)

    def _on_edited(self, *_):
        if self.is_quiet():
            return
        self._sync_visibility()
        slot = self._slot()
        settings = self._settings(slot)
        if settings is None:
            return
        self._drafts[slot] = settings
        self.slot_list.item(slot).setText(self._slot_text(slot))
        self._show_note(slot)

    def _on_save(self):
        slot = self._slot()
        if not self.ready():
            return
        settings = self._settings(slot)
        if settings is None:
            self.refused()
            return
        result = self.call("fd_set", slot, settings)
        if result is None:
            self.refused()
            return
        self._drafts.pop(slot, None)
        self._loader.put(slot, result)
        self._show(slot)
        self.saved()

    def _on_clear(self):
        slot = self._slot()
        if not self.ready():
            return
        base = self._loader.values.get(slot)
        if base is None:
            self.refused()
            return
        settings = dict(base)
        settings["flags"] = 0
        result = self.call("fd_set", slot, settings)
        if result is None:
            self.refused()
            return
        self._drafts.pop(slot, None)
        self._loader.put(slot, result)
        self._show(slot)
        self.set_status(_t("The slot is now empty."))
