# coding: utf-8
# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtWidgets import QHBoxLayout, QToolButton, QComboBox

from widgets.combo_box import ArrowComboBox
from macro.macro_action_ui import (ActionTextUI, ActionDownUI, ActionUpUI, ActionTapUI,
                                   ActionDelayUI, ActionBPMDelayUI,
                                   ActionMixingControlUI)
from protocol.constants import VIAL_PROTOCOL_ADVANCED_MACROS


class MacroLine(QObject):

    changed = pyqtSignal()
    key_selected = pyqtSignal(object)  # Emits the selected key widget

    types = ["Keypress (press + release)", "Hold Key (press only)", "Release Key (release only)", "Text"]
    type_to_cls = [ActionTapUI, ActionDownUI, ActionUpUI, ActionTextUI]

    def __init__(self, parent, action):
        super().__init__()

        self.parent = parent
        self.container = parent.container

        if self.parent.parent.keyboard.vial_protocol >= VIAL_PROTOCOL_ADVANCED_MACROS:
            self.types = self.types[:] + ["Wait (ms)", "Wait (BPM)", "Fader"]
            self.type_to_cls = self.type_to_cls[:] + [ActionDelayUI, ActionBPMDelayUI,
                                                       ActionMixingControlUI]

        self.arrows = QHBoxLayout()
        self.btn_up = QToolButton()
        self.btn_up.setText("▲")
        self.btn_up.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_up.clicked.connect(self.on_move_up)
        self.btn_down = QToolButton()
        self.btn_down.setText("▼")
        self.btn_down.clicked.connect(self.on_move_down)
        self.btn_down.setToolButtonStyle(Qt.ToolButtonTextOnly)

        self.arrows.addWidget(self.btn_up)
        self.arrows.addWidget(self.btn_down)
        self.arrows.setSpacing(0)

        self.select_type = ArrowComboBox()
        self.select_type.addItems(self.types)
        self.select_type.setCurrentIndex(self.type_to_cls.index(type(action)))
        self.select_type.currentIndexChanged.connect(self.on_change_type)

        self.action = action
        self.action.changed.connect(self.on_change)
        self.action.key_selected.connect(self.on_key_selected)
        self.row = -1

        self.btn_remove = QToolButton()
        self.btn_remove.setText("×")
        self.btn_remove.setFixedWidth(20)
        self.btn_remove.setFixedHeight(20)
        self.btn_remove.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_remove.setStyleSheet("""
            QToolButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 3px;
                font-weight: bold;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: #c82333;
            }
            QToolButton:pressed {
                background-color: #bd2130;
            }
        """)
        self.btn_remove.clicked.connect(self.on_remove_clicked)

    def insert(self, row):
        self.row = row
        # Layout: [×] [▲▼] [Type] [Keys/Action]
        self.container.addWidget(self.btn_remove, row, 0)
        self.container.addLayout(self.arrows, row, 1)
        self.container.addWidget(self.select_type, row, 2)
        self.action.insert(row)

    def remove(self):
        self.container.removeItem(self.arrows)
        self.container.removeWidget(self.select_type)
        self.container.removeWidget(self.btn_remove)
        self.action.remove()

    def delete(self):
        self.action.delete()
        self.btn_remove.deleteLater()
        self.select_type.deleteLater()
        self.arrows.deleteLater()
        self.btn_up.deleteLater()
        self.btn_down.deleteLater()

    def on_change_type(self):
        self.action.remove()
        self.action.delete()
        self.action = self.type_to_cls[self.select_type.currentIndex()](self.container)
        self.action.changed.connect(self.on_change)
        self.action.key_selected.connect(self.on_key_selected)
        self.action.insert(self.row)
        self.changed.emit()

    def on_remove_clicked(self):
        self.parent.on_remove(self)

    def on_move_up(self):
        self.parent.on_move(self, -1)

    def on_move_down(self):
        self.parent.on_move(self, 1)

    def on_change(self):
        self.changed.emit()

    def on_key_selected(self, widget):
        """Bubble up key selection to parent"""
        self.key_selected.emit(widget)
