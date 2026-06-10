# SPDX-License-Identifier: GPL-2.0-or-later
import json
from collections import defaultdict

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal, QObject, Qt
from PyQt5.QtWidgets import QVBoxLayout, QCheckBox, QGridLayout, QLabel, QWidget, QSizePolicy, QTabWidget, QSpinBox, \
    QHBoxLayout, QPushButton, QMessageBox, QScrollArea, QGroupBox

from editor.basic_editor import BasicEditor
from protocol.constants import VIAL_PROTOCOL_QMK_SETTINGS
from util import tr
from vial_device import VialKeyboard


class GenericOption(QObject):

    changed = pyqtSignal()

    def __init__(self, option, container):
        super().__init__()

        self.row = container.rowCount()
        self.option = option
        self.qsid = self.option["qsid"]
        self.container = container

        self.lbl = QLabel(option["title"])
        self.container.addWidget(self.lbl, self.row, 0)

    def reload(self, keyboard):
        return keyboard.settings.get(self.qsid)

    def delete(self):
        self.lbl.hide()
        self.lbl.deleteLater()

    def on_change(self):
        self.changed.emit()


class BooleanOption(GenericOption):

    def __init__(self, option, container):
        super().__init__(option, container)

        self.qsid_bit = self.option["bit"]

        self.checkbox = QCheckBox()
        self.checkbox.stateChanged.connect(self.on_change)
        self.container.addWidget(self.checkbox, self.row, 1)

    def reload(self, keyboard):
        value = super().reload(keyboard)
        # Handle case where firmware advertises setting but doesn't return a value
        if value is None:
            value = 0
        checked = value & (1 << self.qsid_bit)

        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked != 0)
        self.checkbox.blockSignals(False)

    def value(self):
        checked = int(self.checkbox.isChecked())
        return checked << self.qsid_bit

    def delete(self):
        super().delete()
        self.checkbox.hide()
        self.checkbox.deleteLater()


class IntegerOption(GenericOption):

    def __init__(self, option, container):
        super().__init__(option, container)

        self.spinbox = QSpinBox()
        self.spinbox.setMinimum(option["min"])
        self.spinbox.setMaximum(option["max"])
        self.spinbox.valueChanged.connect(self.on_change)
        self.container.addWidget(self.spinbox, self.row, 1)

    def reload(self, keyboard):
        value = super().reload(keyboard)
        # Handle case where firmware advertises setting but doesn't return a value
        if value is None:
            value = 0
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(value)
        self.spinbox.blockSignals(False)

    def value(self):
        return self.spinbox.value()

    def delete(self):
        super().delete()
        self.spinbox.hide()
        self.spinbox.deleteLater()


class QmkSettings(BasicEditor):

    def __init__(self):
        super().__init__()
        self.keyboard = None

        self.tabs_widget = QTabWidget()
        self.addWidget(self.tabs_widget)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_save = QPushButton(tr("QmkSettings", "Save"))
        self.btn_save.setMinimumHeight(30)
        self.btn_save.setMaximumHeight(30)
        self.btn_save.setMinimumWidth(80)
        self.btn_save.setStyleSheet("QPushButton { border-radius: 5px; }")
        self.btn_save.clicked.connect(self.save_settings)
        buttons.addWidget(self.btn_save)
        self.btn_undo = QPushButton(tr("QmkSettings", "Undo"))
        self.btn_undo.setMinimumHeight(30)
        self.btn_undo.setMaximumHeight(30)
        self.btn_undo.setMinimumWidth(80)
        self.btn_undo.setStyleSheet("QPushButton { border-radius: 5px; }")
        self.btn_undo.clicked.connect(self.reload_settings)
        buttons.addWidget(self.btn_undo)
        btn_reset = QPushButton(tr("QmkSettings", "Reset"))
        btn_reset.setMinimumHeight(30)
        btn_reset.setMaximumHeight(30)
        btn_reset.setMinimumWidth(80)
        btn_reset.setStyleSheet("QPushButton { border-radius: 5px; }")
        btn_reset.clicked.connect(self.reset_settings)
        buttons.addWidget(btn_reset)
        self.addLayout(buttons)

        self.tabs = []
        self.misc_widgets = []

    def populate_tab(self, tab, container):
        options = []
        for field in tab["fields"]:
            if field["qsid"] not in self.keyboard.supported_settings:
                continue
            if field["type"] == "boolean":
                opt = BooleanOption(field, container)
                options.append(opt)
                opt.changed.connect(self.on_change)
            elif field["type"] == "integer":
                opt = IntegerOption(field, container)
                options.append(opt)
                opt.changed.connect(self.on_change)
            else:
                raise RuntimeError("unsupported field type: {}".format(field))
        return options

    def recreate_gui(self):
        # Tab descriptions based on QMK/Vial documentation
        tab_descriptions = {
            "Magic": "Swap and modify key behavior globally. Changes apply system-wide\n"
                     "without modifying your keymap layout.",
            "Grave Escape": "Configure the Grave Escape key to send Escape when combined\n"
                            "with specific modifiers, or Grave (`) otherwise.",
            "Tap-Hold": "Configure dual-function key timing. Tap for one action,\n"
                        "hold for another. Adjust timing thresholds and behavior.",
            "Auto Shift": "Automatically send shifted characters when keys are held\n"
                          "longer than the timeout. No need to hold Shift.",
            "Combo": "Configure combo key timing. Combos trigger actions when\n"
                     "multiple keys are pressed simultaneously.",
            "One Shot Keys": "Configure sticky modifiers that remain active for only\n"
                             "the next keypress. Reduces finger strain.",
            "Mouse keys": "Control mouse cursor and scroll using keyboard keys.\n"
                          "Configure movement speed, acceleration, and delays."
        }

        # delete old GUI
        for tab in self.tabs:
            for field in tab:
                field.delete()
        self.tabs.clear()
        for w in self.misc_widgets:
            w.hide()
            w.deleteLater()
        self.misc_widgets.clear()
        while self.tabs_widget.count() > 0:
            self.tabs_widget.removeTab(0)

        # create new GUI
        for tab in self.settings_defs["tabs"]:
            # don't bother creating tabs that would be empty - i.e. at least one qsid in a tab should be supported
            use_tab = False
            for field in tab["fields"]:
                if field["qsid"] in self.keyboard.supported_settings:
                    use_tab = True
                    break
            if not use_tab:
                continue

            # Main layout with centered content
            main_v_layout = QVBoxLayout()
            main_v_layout.setSpacing(15)

            # Add stretch to push content to center
            main_v_layout.addStretch()

            # Top: Title (centered)
            title_label = QLabel(tab["name"])
            title_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
            title_label.setAlignment(QtCore.Qt.AlignCenter)
            main_v_layout.addWidget(title_label)

            # Description (centered)
            desc_text = tab_descriptions.get(tab["name"], "Configure settings for this feature.")
            desc_label = QLabel(desc_text)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: gray; font-size: 9pt;")
            desc_label.setAlignment(QtCore.Qt.AlignCenter)
            main_v_layout.addWidget(desc_label)

            # Bottom: Settings in a group box (centered)
            settings_group = QGroupBox("Settings")
            w = QWidget()
            w.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
            container = QGridLayout()
            w.setLayout(container)

            group_layout = QVBoxLayout()
            group_layout.addWidget(w)
            group_layout.setAlignment(w, QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
            settings_group.setLayout(group_layout)

            # Create a centered container for the settings group
            center_h_layout = QHBoxLayout()
            center_h_layout.addStretch()
            center_h_layout.addWidget(settings_group)
            center_h_layout.addStretch()
            main_v_layout.addLayout(center_h_layout)

            main_v_layout.addStretch()

            # Create widget for layout
            content_widget = QWidget()
            content_widget.setLayout(main_v_layout)

            # Wrap in scroll area
            w2 = QScrollArea()
            w2.setWidget(content_widget)
            w2.setWidgetResizable(True)
            w2.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            w2.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

            self.misc_widgets += [w, content_widget, w2, settings_group]
            self.tabs_widget.addTab(w2, tab["name"])
            self.tabs.append(self.populate_tab(tab, container))

    def reload_settings(self):
        self.keyboard.reload_settings()
        self.recreate_gui()

        for tab in self.tabs:
            for field in tab:
                field.reload(self.keyboard)

        self.on_change()

    def on_change(self):
        changed = False
        qsid_values = self.prepare_settings()

        for x, tab in enumerate(self.tabs):
            tab_changed = False
            for opt in tab:
                # Handle case where firmware advertises setting but doesn't return a value
                stored_value = self.keyboard.settings.get(opt.qsid, 0)
                if qsid_values[opt.qsid] != stored_value:
                    changed = True
                    tab_changed = True
            title = self.tabs_widget.tabText(x).rstrip("*")
            if tab_changed:
                self.tabs_widget.setTabText(x, title + "*")
            else:
                self.tabs_widget.setTabText(x, title)

        self.btn_save.setEnabled(changed)
        self.btn_undo.setEnabled(changed)

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            self.reload_settings()

    def prepare_settings(self):
        qsid_values = defaultdict(int)
        for tab in self.tabs:
            for field in tab:
                qsid_values[field.qsid] |= field.value()
        return qsid_values

    def save_settings(self):
        qsid_values = self.prepare_settings()
        for qsid, value in qsid_values.items():
            self.keyboard.qmk_settings_set(qsid, value)
        self.on_change()

    def reset_settings(self):
        if QMessageBox.question(self.widget(), "",
                                tr("QmkSettings", "Reset all settings to default values?"),
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.keyboard.qmk_settings_reset()
            self.reload_settings()

    def valid(self):
        return isinstance(self.device, VialKeyboard) and \
               (self.device.keyboard and self.device.keyboard.vial_protocol >= VIAL_PROTOCOL_QMK_SETTINGS
                and len(self.device.keyboard.supported_settings))

    @classmethod
    def initialize(cls, appctx):
        cls.qsid_fields = defaultdict(list)
        with open(appctx.get_resource("qmk_settings.json"), "r") as inf:
            cls.settings_defs = json.load(inf)
        for tab in cls.settings_defs["tabs"]:
            for field in tab["fields"]:
                cls.qsid_fields[field["qsid"]].append(field)

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
