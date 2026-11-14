# SPDX-License-Identifier: GPL-2.0-or-later
"""KeySplit presets: ten sets of per-zone overrides the keyboard can switch on."""

import copy

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QFormLayout, QGroupBox, QCheckBox, QLabel,
                             QListWidget, QWidget)

from editor.articulation_options import populate_articulation_combo, apply_articulation_visibility
from editor.qb_pages.common import QbPage, Combo, SignedSpin, channel_combo, SECTION_STYLE
from protocol.app_config import KSP_COUNT
from util import tr
from widgets.toggle_switch import ToggleSwitch

ZONE_NAMES = ["Normal", "KeySplit", "TripleSplit"]
CURVE_MASTER = 255


def _t(text):
    return tr("KeySplitPage", text)


class ZonePanel(QGroupBox):
    """One zone of a preset."""

    changed = pyqtSignal()

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        layout = QVBoxLayout(self)
        self.use_check = QCheckBox(_t("Use zone"))
        self.use_check.setToolTip(_t("When off, this preset leaves the zone alone."))
        layout.addWidget(self.use_check)

        self.fields = QWidget()
        form = QFormLayout(self.fields)
        form.setContentsMargins(0, 4, 0, 0)

        self.channel = channel_combo(first_is_master=True)
        form.addRow(_t("Channel"), self.channel)

        transpose_row = QHBoxLayout()
        self.transpose_mode = Combo()
        self.transpose_mode.setMinimumContentsLength(6)
        self.transpose_mode.addItem(_t("Master"), False)
        self.transpose_mode.addItem(_t("Shift by"), True)
        self.transpose = SignedSpin(-64, 64)
        self.transpose.setMinimumWidth(66)
        self.transpose.setToolTip(_t("Semitones up or down."))
        transpose_row.addWidget(self.transpose_mode, 1)
        transpose_row.addWidget(self.transpose)
        form.addRow(_t("Transpose"), transpose_row)

        self.curve = Combo()
        populate_articulation_combo(self.curve, include_none=True, none_label=_t("Master"),
                                    none_index=CURVE_MASTER)
        apply_articulation_visibility(self.curve)
        form.addRow(_t("Articulation"), self.curve)

        self.auto_notes = Combo()
        self.sustain = Combo()
        for combo in (self.auto_notes, self.sustain):
            combo.addItem(_t("Master"), 0)
            combo.addItem(_t("Allow"), 1)
            combo.addItem(_t("Ignore"), 2)
        form.addRow(_t("Auto Notes"), self.auto_notes)
        form.addRow(_t("Sustain"), self.sustain)
        layout.addWidget(self.fields)
        layout.addStretch(1)

        self.use_check.toggled.connect(self._edited)
        self.transpose_mode.currentIndexChanged.connect(self._edited)
        self.transpose.valueChanged.connect(self._edited)
        for combo in (self.channel, self.curve, self.auto_notes, self.sustain):
            combo.currentIndexChanged.connect(self._edited)

    def _edited(self, *_):
        self._sync_enabled()
        self.changed.emit()

    def _sync_enabled(self):
        self.fields.setEnabled(self.use_check.isChecked())
        self.transpose.setEnabled(bool(self.transpose_mode.currentData()))

    def show_zone(self, zone, used):
        self.use_check.setChecked(bool(used))
        self.channel.set_data(zone["channel"], _t("Channel {}"))
        self.transpose_mode.setCurrentIndex(0 if zone["transpose"] is None else 1)
        self.transpose.setValue(zone["transpose"] or 0)
        self.curve.set_data(CURVE_MASTER if zone["curve"] is None else zone["curve"], _t("Curve {}"))
        apply_articulation_visibility(self.curve)
        self.auto_notes.set_data(zone["auto_notes"], _t("Setting {}"))
        self.sustain.set_data(zone["sustain"], _t("Setting {}"))
        self._sync_enabled()

    def zone(self):
        curve = self.curve.currentData()
        return {"channel": self.channel.currentData() or 0,
                "transpose": self.transpose.value() if self.transpose_mode.currentData() else None,
                "curve": None if curve in (None, CURVE_MASTER) else curve,
                "auto_notes": self.auto_notes.currentData() or 0,
                "sustain": self.sustain.currentData() or 0}


class KeySplitPage(QbPage):

    TITLE = "KeySplit Presets"
    DESCRIPTION = ("While a preset is on, it overrides the keyboard's channel, transpose, articulation, "
                   "auto notes and sustain for each zone it uses. \"Master\" leaves that setting alone. "
                   "Every change is saved to the keyboard straight away.")

    def build(self, layout):
        self._presets = [None] * KSP_COUNT

        row = QHBoxLayout()
        row.setSpacing(12)
        self.preset_list = QListWidget()
        self.preset_list.setFixedWidth(150)
        self.preset_list.setMinimumHeight(330)
        for p in range(KSP_COUNT):
            self.preset_list.addItem(self._preset_name(p))
        self.preset_list.currentRowChanged.connect(self._on_preset_selected)
        row.addWidget(self.preset_list)

        right = QVBoxLayout()
        head = QHBoxLayout()
        self.preset_title = QLabel("")
        self.preset_title.setStyleSheet(SECTION_STYLE)
        head.addWidget(self.preset_title)
        head.addSpacing(16)
        self.on_switch = ToggleSwitch(_t("Preset"))
        self.on_switch.setToolTip(_t("Turn this preset on or off on the keyboard."))
        self.on_switch.switched.connect(self._on_switch)
        head.addWidget(self.on_switch)
        head.addStretch(1)
        right.addLayout(head)

        zones = QHBoxLayout()
        zones.setSpacing(8)
        self.zone_panels = []
        for name in ZONE_NAMES:
            panel = ZonePanel(_t(name))
            panel.changed.connect(self._on_zone_changed)
            zones.addWidget(panel, 1)
            self.zone_panels.append(panel)
        right.addLayout(zones)
        right.addStretch(1)
        row.addLayout(right, 1)
        layout.addLayout(row)

        with self.quiet():
            self.preset_list.setCurrentRow(0)

    # ---- data -------------------------------------------------------------------

    @staticmethod
    def _preset_name(p):
        return _t("KeySplit {}").format(p + 1)

    def forget(self):
        self._presets = [None] * KSP_COUNT
        for p in range(KSP_COUNT):
            self.preset_list.item(p).setText(self._preset_name(p))

    def load(self):
        for p in range(KSP_COUNT):
            preset = self.call("ksp_get", p)
            if preset is None:
                return False
            self._store(p, preset)
        self._show(self._current())
        return True

    def _current(self):
        return max(0, self.preset_list.currentRow())

    def _store(self, p, preset):
        self._presets[p] = preset
        text = self._preset_name(p)
        if preset["active"]:
            text += "  —  " + _t("On")
        self.preset_list.item(p).setText(text)

    def _show(self, p):
        preset = self._presets[p]
        self.preset_title.setText(self._preset_name(p))
        if preset is None:
            self.on_switch.set_on(False)
            return
        with self.quiet():
            self.on_switch.set_on(preset["active"])
            for z, panel in enumerate(self.zone_panels):
                panel.show_zone(preset["zones"][z], preset["zone_en"] & (1 << z))

    # ---- the user's edits -------------------------------------------------------

    def _on_preset_selected(self, row):
        if row < 0:
            return
        if self.is_quiet():
            self.preset_title.setText(self._preset_name(row))
            return
        if self._presets[row] is None and self.app_config is not None:
            preset = self.call("ksp_get", row)
            if preset is not None:
                self._store(row, preset)
        self._show(row)

    def _on_zone_changed(self):
        p = self._current()
        if not self.ready() or self._presets[p] is None:
            return
        config = copy.deepcopy(self._presets[p])
        config["zone_en"] = sum(1 << z for z, panel in enumerate(self.zone_panels)
                                if panel.use_check.isChecked())
        config["zones"] = [panel.zone() for panel in self.zone_panels]
        result = self.call("ksp_set", p, config)
        if result is None:
            self.refused()
        else:
            self._store(p, result)
            self.saved()
        self._show(p)

    def _on_switch(self, on):
        p = self._current()
        if not self.ready() or self._presets[p] is None:
            self._show(p)
            return
        result = self.call("ksp_switch", p, on)
        nothing_to_do = _t("The keyboard left this preset off: it would not change anything yet. "
                           "Tick \"Use zone\" on at least one zone and set something in that zone "
                           "to other than Master first.")
        if result is None:
            # The keyboard refuses to turn on a preset that changes nothing.
            # Read the preset again to tell that from a keyboard that is not
            # answering at all.
            fresh = self.call("ksp_get", p)
            if fresh is None:
                self.set_status(_t("The keyboard did not answer. Check the connection, then press "
                                   "Read from keyboard."), problem=True)
            else:
                self._store(p, fresh)
                if on and not fresh["active"]:
                    self.set_status(nothing_to_do, problem=True)
                else:
                    self.refused()
        else:
            self._store(p, result)
            if on and not result["active"]:
                self.set_status(nothing_to_do, problem=True)
            else:
                self.set_status(_t("The preset is now on.") if result["active"]
                                else _t("The preset is now off."))
        self._show(p)
