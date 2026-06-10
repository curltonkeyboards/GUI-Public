# SPDX-License-Identifier: GPL-2.0-or-later
import json

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QPushButton, QGridLayout, QHBoxLayout, QToolButton, QVBoxLayout,
    QWidget, QScrollArea, QLabel, QGroupBox, QComboBox, QInputDialog, QCheckBox, QMessageBox)

from keycodes.keycodes import Keycode
from macro.macro_action import ActionTap
from macro.macro_action_ui import ActionTextUI, ActionTapUI, ui_action, tag_to_action
from macro.macro_line import MacroLine
from protocol.constants import VIAL_PROTOCOL_EXT_MACROS
from tabbed_keycodes import keycode_filter_masked
from util import tr
from textbox_window import TextboxWindow
from constants import KEY_SIZE_RATIO


class MacroTab(QVBoxLayout):

    changed = pyqtSignal()
    name_changed = pyqtSignal()
    save_clicked = pyqtSignal()
    revert_clicked = pyqtSignal()
    key_selected = pyqtSignal(object)  # Emits the selected key widget
    widget_deleted = pyqtSignal(object)  # Emits when a widget is about to be deleted

    def __init__(self, parent, enable_recorder, macro_index=0):
        super().__init__()

        self.parent = parent
        self.macro_index = macro_index
        self.lines = []

        self.setSpacing(8)
        self.setContentsMargins(16, 16, 16, 16)

        # Header row: title, rename button, description
        header_layout = QHBoxLayout()
        self.title_label = QLabel(f"<b>M{macro_index}</b>")
        self.title_label.setStyleSheet("font-size: 14pt;")
        header_layout.addWidget(self.title_label)

        self.btn_rename = QPushButton("Rename")
        self.btn_rename.setMaximumHeight(24)
        self.btn_rename.setMaximumWidth(60)
        self.btn_rename.setStyleSheet("QPushButton { font-size: 8pt; border-radius: 3px; padding: 2px 6px; }")
        self.btn_rename.clicked.connect(self._on_rename)
        header_layout.addWidget(self.btn_rename)

        header_layout.addSpacing(12)

        desc = QLabel("Configure actions to send when this macro is triggered. "
                      "Assign this macro to a key in your keymap using the Macro tab in keycodes.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray; font-size: 9pt;")
        header_layout.addWidget(desc, 1)

        self.addLayout(header_layout)

        # Actions group box
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout()

        # Container for macro lines
        self.container = QGridLayout()

        actions_layout.addLayout(self.container)

        # "+" button below actions (10px smaller than the old one) with "Add Action" label
        add_row_layout = QHBoxLayout()
        self.btn_add_key = QToolButton()
        self.btn_add_key.setText("+")
        btn_size = int(self.btn_add_key.fontMetrics().height() * KEY_SIZE_RATIO) - 10
        self.btn_add_key.setFixedWidth(btn_size)
        self.btn_add_key.setFixedHeight(btn_size)
        self.btn_add_key.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_add_key.clicked.connect(self.on_add_tap_key)
        add_row_layout.addWidget(self.btn_add_key)

        add_label = QLabel("\u2190 Add Action")
        add_label.setStyleSheet("color: gray; font-style: italic;")
        add_row_layout.addWidget(add_label)
        add_row_layout.addStretch()

        actions_layout.addLayout(add_row_layout)

        # Loop mode - below Add Action, stretch pushes both to bottom together
        loop_layout = QHBoxLayout()
        self.loop_enable_cb = QCheckBox("Enable Macro repeats/looping")
        self.loop_enable_cb.stateChanged.connect(self._on_loop_enable_toggle)
        loop_layout.addWidget(self.loop_enable_cb)

        self.loop_mode_combo = QComboBox()
        self.loop_mode_combo.addItems(["Loop", "Reverse", "Reverse Loop"])
        self.loop_mode_combo.setMinimumWidth(110)
        self.loop_mode_combo.setEnabled(False)
        self.loop_mode_combo.currentIndexChanged.connect(self.on_loop_mode_change)
        loop_layout.addWidget(self.loop_mode_combo)

        self.sync_to_bpm_cb = QCheckBox("Sync start to loop/BPM")
        self.sync_to_bpm_cb.setToolTip("Defer macro start until the next loop trigger boundary")
        self.sync_to_bpm_cb.stateChanged.connect(self.on_sync_change)
        loop_layout.addWidget(self.sync_to_bpm_cb)
        loop_layout.addStretch()

        actions_layout.addLayout(loop_layout)

        actions_group.setLayout(actions_layout)

        # Scroll area for actions
        scroll = QScrollArea()
        scroll.setWidget(actions_group)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.addWidget(scroll)

        # Bottom buttons: Open Text Editor, stretch, Clear, Save, Revert
        self.btn_text_window = QPushButton(tr("MacroRecorder", "Open Text Editor..."))
        self.btn_text_window.setMinimumHeight(30)
        self.btn_text_window.setMaximumHeight(30)
        self.btn_text_window.setStyleSheet("QPushButton { border-radius: 5px; }")
        self.btn_text_window.clicked.connect(self.on_text_window)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setMinimumHeight(30)
        self.btn_clear.setMaximumHeight(30)
        self.btn_clear.setMinimumWidth(80)
        self.btn_clear.setStyleSheet("QPushButton { border-radius: 5px; }")
        self.btn_clear.clicked.connect(self.on_clear)

        self.btn_save = QPushButton(tr("MacroRecorder", "Save"))
        self.btn_save.setMinimumHeight(30)
        self.btn_save.setMaximumHeight(30)
        self.btn_save.setMinimumWidth(80)
        self.btn_save.setStyleSheet("QPushButton { border-radius: 5px; }")
        self.btn_save.clicked.connect(lambda: self.save_clicked.emit())

        self.btn_revert = QPushButton(tr("MacroRecorder", "Revert"))
        self.btn_revert.setMinimumHeight(30)
        self.btn_revert.setMaximumHeight(30)
        self.btn_revert.setMinimumWidth(80)
        self.btn_revert.setStyleSheet("QPushButton { border-radius: 5px; }")
        self.btn_revert.clicked.connect(lambda: self.revert_clicked.emit())

        layout_buttons = QHBoxLayout()
        layout_buttons.addWidget(self.btn_text_window)
        layout_buttons.addStretch()
        layout_buttons.addWidget(self.btn_clear)
        layout_buttons.addWidget(self.btn_save)
        layout_buttons.addWidget(self.btn_revert)

        self.addLayout(layout_buttons)

        self.dlg_textbox = None

    def _on_loop_enable_toggle(self):
        enabled = self.loop_enable_cb.isChecked()
        self.loop_mode_combo.setEnabled(enabled)
        self.changed.emit()

    def set_save_enabled(self, enabled):
        self.btn_save.setEnabled(enabled)

    def set_macro_index(self, index):
        """Update the macro index shown in the header"""
        self.macro_index = index
        from protocol.feature_names import get_feature_name_manager, FEATURE_MACRO
        name = get_feature_name_manager().get_name(FEATURE_MACRO, index)
        self.title_label.setText(f"<b>{name}</b>")

    def _on_rename(self):
        """Open rename dialog for this macro"""
        from protocol.feature_names import get_feature_name_manager, FEATURE_MACRO, MAX_NAME_LENGTH
        mgr = get_feature_name_manager()
        current = mgr.get_name(FEATURE_MACRO, self.macro_index)
        new_name, ok = QInputDialog.getText(
            None, "Rename Macro",
            f"Name for M{self.macro_index} (max {MAX_NAME_LENGTH} chars):",
            text=current
        )
        if ok:
            new_name = new_name.strip()[:MAX_NAME_LENGTH]
            if not new_name:
                new_name = ""  # will revert to default
            mgr.set_name(FEATURE_MACRO, self.macro_index, new_name)
            display = mgr.get_name(FEATURE_MACRO, self.macro_index)
            self.title_label.setText(f"<b>{display}</b>")
            self.name_changed.emit()  # trigger save enable + tab title update
            self.changed.emit()  # trigger tab title update

    def add_action(self, act):
        if self.parent.keyboard.vial_protocol < VIAL_PROTOCOL_EXT_MACROS:
            act.set_keycode_filter(keycode_filter_masked)
        line = MacroLine(self, act)
        line.changed.connect(self.on_change)
        line.key_selected.connect(self.on_key_selected)
        self.lines.append(line)
        line.insert(len(self.lines) - 1)
        self.changed.emit()

    def on_key_selected(self, widget):
        """Bubble up key selection to parent MacroRecorder"""
        self.key_selected.emit(widget)

    def on_add(self):
        self.add_action(ActionTextUI(self.container))

    def on_add_tap_key(self):
        """Add a new tap action with KC_NO"""
        self.add_action(ActionTapUI(self.container, ActionTap(["KC_NO"])))

    def on_remove(self, obj):
        # Emit widget_deleted for all key widgets in this line before deletion
        if hasattr(obj.action, 'widgets'):
            for widget in obj.action.widgets:
                self.widget_deleted.emit(widget)

        for line in self.lines:
            if line == obj:
                line.remove()
                line.delete()
        self.lines.remove(obj)
        for line in self.lines:
            line.remove()
        for x, line in enumerate(self.lines):
            line.insert(x)
        self.changed.emit()

    def clear(self):
        for line in self.lines[:]:
            self.on_remove(line)

    def on_clear(self):
        """Clear macro with confirmation dialog"""
        reply = QMessageBox.question(
            None, "Clear Macro",
            "Are you sure you want to clear all actions in this macro?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.clear()

    def on_move(self, obj, offset):
        if offset == 0:
            return
        index = self.lines.index(obj)
        if index + offset < 0 or index + offset >= len(self.lines):
            return
        other = self.lines.index(self.lines[index + offset])
        self.lines[index].remove()
        self.lines[other].remove()
        self.lines[index], self.lines[other] = self.lines[other], self.lines[index]
        self.lines[index].insert(index)
        self.lines[other].insert(other)
        self.changed.emit()

    def on_text_window(self):
        # serialize all actions in this tab to a json
        macro_text = json.dumps([act.save() for act in self.actions()])

        self.dlg_textbox = TextboxWindow(macro_text, "vim", "Vial macro")
        self.dlg_textbox.setModal(True)
        self.dlg_textbox.finished.connect(self.on_dlg_finished)
        self.dlg_textbox.show()

    def on_dlg_finished(self, res):
        if res > 0:
            macro_text = self.dlg_textbox.getText()
            if len(macro_text) < 6:
                macro_text = "[]"
            macro_load = json.loads(macro_text)

            # ensure a list exists
            if not isinstance(macro_load, list):
                return

            # clear the actions from this tab
            self.clear()

            # add each action from the json to this tab
            for act in macro_load:
                if act[0] in tag_to_action:
                    obj = tag_to_action[act[0]]()
                    actionUI = ui_action[type(obj)]
                    obj.restore(act)
                    self.add_action(actionUI(self.container, obj))

    def on_change(self):
        self.changed.emit()

    def get_loop_mode(self):
        """Return loop mode: 0=None (checkbox unchecked), 1-3=Loop/Reverse/ReverseLoop"""
        if not self.loop_enable_cb.isChecked():
            return 0  # None
        return self.loop_mode_combo.currentIndex() + 1  # +1 because "None" removed from combo

    def set_loop_mode(self, mode):
        """Set loop mode: 0=None, 1=Loop, 2=Reverse, 3=Reverse Loop"""
        self.loop_enable_cb.blockSignals(True)
        self.loop_mode_combo.blockSignals(True)
        if mode == 0:
            self.loop_enable_cb.setChecked(False)
            self.loop_mode_combo.setEnabled(False)
            self.loop_mode_combo.setCurrentIndex(0)
        else:
            self.loop_enable_cb.setChecked(True)
            self.loop_mode_combo.setEnabled(True)
            self.loop_mode_combo.setCurrentIndex(mode - 1)  # -1 because "None" removed
        self.loop_enable_cb.blockSignals(False)
        self.loop_mode_combo.blockSignals(False)

    def get_sync_to_bpm(self):
        return self.sync_to_bpm_cb.isChecked()

    def set_sync_to_bpm(self, sync):
        self.sync_to_bpm_cb.blockSignals(True)
        self.sync_to_bpm_cb.setChecked(sync)
        self.sync_to_bpm_cb.blockSignals(False)

    def on_loop_mode_change(self):
        self.changed.emit()

    def on_sync_change(self):
        self.changed.emit()

    def actions(self):
        return [line.action.act for line in self.lines]
