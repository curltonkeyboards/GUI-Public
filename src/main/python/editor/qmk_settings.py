# SPDX-License-Identifier: GPL-2.0-or-later
"""The three firmware timing settings that survived the QMK Settings tab.

The old "QMK Settings" tab (Magic / Grave Escape / Tap-Hold / Auto Shift /
Combo / One Shot Keys / Mouse keys) is gone. Only three values are still
user-facing, as the "Macro Settings" group of MIDI Settings > Advanced
Settings:

    Key press duration for hold in Tap/Hold Keys (ms)   qsid 7   (tapping term)
    Gap between Macro keys (ms)                         qsid 18  (tap code delay)
    Mouse click delay on macro (ms)                     app id 0x1001
    Mouse double click speed (ms)                       app id 0x1002
    One shot key timeout (ms)                           qsid 6   (one shot timeout)

The two mouse settings are not device setting ids: they ride the Macro
Settings command's feature-detected mouse fields (protocol/msw_protocol.py).

The other qsids stay at their firmware defaults; the firmware still supports
them (stage 1 of the migration is GUI-only), they just have no UI.

`QmkSettingsDefs` keeps the class-level definition/serialisation helpers the
comm layer (`keyboard_comm.py`) and layout-file restore rely on.
"""
import json
from collections import defaultdict

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QGridLayout, QLabel, QSpinBox, QHBoxLayout, QPushButton, QMessageBox, QGroupBox, \
    QVBoxLayout

from protocol.constants import VIAL_PROTOCOL_QMK_SETTINGS
from util import tr
from vial_device import VialKeyboard


class QmkSettingsDefs:
    """Setting definitions loaded from qmk_settings.json + (de)serialisation."""

    qsid_fields = defaultdict(list)
    settings_defs = {"tabs": []}

    @classmethod
    def initialize(cls, appctx):
        cls.qsid_fields = defaultdict(list)
        with open(appctx.get_resource("qmk_settings.json"), "r") as inf:
            cls.settings_defs = json.load(inf)
        for tab in cls.settings_defs["tabs"]:
            for field in tab["fields"]:
                cls.qsid_fields[field["qsid"]].append(field)

    @classmethod
    def fields(cls):
        out = []
        for tab in cls.settings_defs["tabs"]:
            out += tab["fields"]
        return out

    @classmethod
    def is_qsid_supported(cls, qsid):
        """ Return whether this qsid is supported by the settings editor """
        return qsid in cls.qsid_fields

    @classmethod
    def qsid_serialize(cls, qsid, data):
        """ Serialize from internal representation into binary that can be sent to the firmware """
        fields = cls.qsid_fields[qsid]
        if fields[0]["type"] == "boolean":
            assert isinstance(data, int)
            return data.to_bytes(fields[0].get("width", 1), byteorder="little")
        elif fields[0]["type"] == "integer":
            assert isinstance(data, int)
            assert len(fields) == 1
            return data.to_bytes(fields[0]["width"], byteorder="little")

    @classmethod
    def qsid_deserialize(cls, qsid, data):
        """ Deserialize from binary received from firmware into internal representation """
        fields = cls.qsid_fields[qsid]
        if fields[0]["type"] == "boolean":
            return int.from_bytes(data[0:fields[0].get("width", 1)], byteorder="little")
        elif fields[0]["type"] == "integer":
            assert len(fields) == 1
            return int.from_bytes(data[0:fields[0]["width"]], byteorder="little")
        else:
            raise RuntimeError("unsupported field")


class MacroSettingsGroup(QGroupBox):
    """'Macro Settings' group box: the three integer settings with explicit
    Save / Undo / Reset, hosted by MIDI Settings > Advanced Settings.

    Call rebuild(device) whenever the connected device changes."""

    changed = pyqtSignal()

    def __init__(self):
        super().__init__(tr("QmkSettings", "Macro Settings"))
        self.keyboard = None
        self.spinboxes = {}   # qsid -> QSpinBox

        layout = QVBoxLayout()
        grid = QGridLayout()
        grid.setHorizontalSpacing(15)
        for row, field in enumerate(QmkSettingsDefs.fields()):
            if field["type"] != "integer":
                continue
            lbl = QLabel(field["title"])
            grid.addWidget(lbl, row, 0)
            sb = QSpinBox()
            if field.get("tooltip"):
                lbl.setToolTip(field["tooltip"])
                sb.setToolTip(field["tooltip"])
            sb.setMinimum(field["min"])
            sb.setMaximum(field["max"])
            sb.setMinimumWidth(90)
            sb.valueChanged.connect(self.on_change)
            grid.addWidget(sb, row, 1)
            self.spinboxes[field["qsid"]] = sb
        layout.addLayout(grid)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_save = QPushButton(tr("QmkSettings", "Save"))
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_undo = QPushButton(tr("QmkSettings", "Undo"))
        self.btn_undo.clicked.connect(self.reload_settings)
        self.btn_reset = QPushButton(tr("QmkSettings", "Reset"))
        self.btn_reset.clicked.connect(self.reset_settings)
        for b in (self.btn_save, self.btn_undo, self.btn_reset):
            b.setMinimumHeight(30)
            b.setMaximumHeight(30)
            b.setMinimumWidth(80)
            b.setStyleSheet("QPushButton { border-radius: 5px; }")
            buttons.addWidget(b)
        layout.addLayout(buttons)
        self.setLayout(layout)
        self.setEnabled(False)

    # ---- device -----------------------------------------------------------

    def valid(self, device):
        return isinstance(device, VialKeyboard) and device.keyboard and \
            device.keyboard.vial_protocol >= VIAL_PROTOCOL_QMK_SETTINGS and \
            any(qsid in device.keyboard.supported_settings for qsid in self.spinboxes)

    def rebuild(self, device):
        if not self.valid(device):
            self.keyboard = None
            self.setEnabled(False)
            return
        self.keyboard = device.keyboard
        self.setEnabled(True)
        for qsid, sb in self.spinboxes.items():
            sb.setEnabled(qsid in self.keyboard.supported_settings)
        self.reload_settings()

    def reload_settings(self):
        if self.keyboard is None:
            return
        self.keyboard.reload_settings()
        for qsid, sb in self.spinboxes.items():
            value = self.keyboard.settings.get(qsid)
            if value is None:
                value = 0
            sb.blockSignals(True)
            sb.setValue(value)
            sb.blockSignals(False)
        self.on_change()

    def on_change(self):
        if self.keyboard is None:
            return
        changed = any(sb.value() != self.keyboard.settings.get(qsid, 0)
                      for qsid, sb in self.spinboxes.items() if sb.isEnabled())
        self.btn_save.setEnabled(changed)
        self.btn_undo.setEnabled(changed)
        self.changed.emit()

    def save_settings(self):
        if self.keyboard is None:
            return
        for qsid, sb in self.spinboxes.items():
            if sb.isEnabled():
                self.keyboard.qmk_settings_set(qsid, sb.value())
        self.on_change()

    def reset_settings(self):
        if self.keyboard is None:
            return
        if QMessageBox.question(self, "",
                                tr("QmkSettings", "Reset all Macro Settings to default values?"),
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.keyboard.qmk_settings_reset()
            self.reload_settings()
