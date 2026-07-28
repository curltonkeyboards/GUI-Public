# SPDX-License-Identifier: GPL-2.0-or-later

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt5.QtWidgets import QTabWidget, QWidget, QScrollArea, QApplication, QVBoxLayout, QHBoxLayout, QComboBox, QSizePolicy, QLabel, QGridLayout, QStyleOptionComboBox, QDialog, QLineEdit, QFrame, QListView, QScrollBar, QPushButton, QSlider, QGroupBox, QMessageBox, QStackedWidget
from PyQt5.QtGui import QPalette, QPainter, QPolygon, QPen, QColor, QBrush, QPixmap, QPainterPath, QRegion

from constants import KEYCODE_BTN_RATIO
from widgets.display_keyboard import DisplayKeyboard
from widgets.display_keyboard_defs import ansi_100, ansi_80, ansi_70, iso_100, iso_80, iso_70, mods, mods_narrow, midi_layout
from widgets.combo_box import ArrowComboBox
from widgets.flowlayout import FlowLayout
from keycodes.keycodes import KEYCODES_BASIC, KEYCODES_ISO, KEYCODES_MACRO, KEYCODES_MACRO_BASE, KEYCODES_LAYERS, KEYCODES_QUANTUM, \
    KEYCODES_BOOT, KEYCODES_MODIFIERS, KEYCODES_CLEAR, KEYCODES_RGB_KC_CUSTOM, KEYCODES_RGB_KC_CUSTOM2, KEYCODES_RGBSAVE, KEYCODES_EXWHEEL, KEYCODES_RGB_KC_COLOR, KEYCODES_MIDI_SPLIT_BUTTONS, KEYCODES_SETTINGS1, KEYCODES_SETTINGS2, KEYCODES_SETTINGS3, KEYCODES_BASIC, KEYCODES_SHIFTED, KEYCODES_CHORD_PROG_CONTROLS, KEYCODES_MIDI_CHANNEL_OS, KEYCODES_MIDI_CHANNEL_HOLD, KEYCODES_CPROG_SLOTS, \
    KEYCODES_BACKLIGHT, KEYCODES_MEDIA, KEYCODES_SPECIAL, KEYCODES_SHIFTED, KEYCODES_USER, Keycode, KEYCODES_LAYERS_DF, KEYCODES_LAYERS_MO, KEYCODES_LAYERS_TG, KEYCODES_LAYERS_TT, KEYCODES_LAYERS_OSL, KEYCODES_LAYERS_TO, KEYCODES_LAYERS_LT, KEYCODES_VELOCITY_SHUFFLE, KEYCODES_CC_ENCODERVALUE, KEYCODES_LOOP_BUTTONS, KEYCODES_DRUMLIVE, KEYCODES_GAMING, \
    KEYCODES_DAW, \
    KEYCODES_TAP_DANCE, KEYCODES_MIDI, KEYCODES_MIDI_SPLIT, KEYCODES_MIDI_SPLIT2, KEYCODES_MIDI_CHANNEL_KEYSPLIT, KEYCODES_KEYSPLIT_BUTTONS, KEYCODES_MIDI_CHANNEL_KEYSPLIT2, KEYCODES_BASIC_NUMPAD, KEYCODES_BASIC_NAV, KEYCODES_ISO_KR, BASIC_KEYCODES, \
    KEYCODES_ARPEGGIATOR, KEYCODES_ARPEGGIATOR_PRESETS, KEYCODES_STEP_SEQUENCER, KEYCODES_STEP_SEQUENCER_PRESETS, KEYCODES_DRUM_SLOTS, KEYCODES_DKS, KEYCODES_TOGGLE, KEYCODES_TOGGLE_ACTIONS, KEYCODES_DELAY_CLEAR, KEYCODES_DELAY, KEYCODES_DELAY_FACTORY, KEYCODES_DELAY_USER, KEYCODES_DELAY_QB, KEYCODES_CHORD_QB, KEYCODES_DYNCHORD_QB, KEYCODES_FADER_QB, KEYCODES_QB_MASTER, KEYCODES_EARTRAINER_QB, \
    KEYCODES_MIDI_CC, KEYCODES_MIDI_BANK, KEYCODES_Program_Change, KEYCODES_CC_STEPSIZE, KEYCODES_MIDI_VELOCITY, KEYCODES_Program_Change_UPDOWN, KEYCODES_MIDI_BANK, KEYCODES_MIDI_BANK_LSB, KEYCODES_MIDI_BANK_MSB, KEYCODES_MIDI_CC_FIXED, KEYCODES_OLED, KEYCODES_EARTRAINER, KEYCODES_SAVE, KEYCODES_CHORDTRAINER, \
    KEYCODES_MIDI_OCTAVE2, KEYCODES_MIDI_OCTAVE3, KEYCODES_MIDI_KEY2, KEYCODES_MIDI_KEY3, KEYCODES_MIDI_VELOCITY2, KEYCODES_MIDI_VELOCITY3, KEYCODES_MIDI_ADVANCED, KEYCODES_MIDI_SMARTCHORDBUTTONS, KEYCODES_VELOCITY_STEPSIZE, KEYCODES_MIDI_CHANNEL_OS, KEYCODES_MIDI_CHANNEL_HOLD, \
    KEYCODES_HE_VELOCITY_CURVE, KEYCODES_HE_VELOCITY_RANGE, \
    KEYCODES_MIDI_CHANNEL, KEYCODES_MULTICHANNEL, KEYCODES_MIDI_UPDOWN, KEYCODES_MIDI_CHORD_0, KEYCODES_MIDI_CHORD_1, KEYCODES_MIDI_CHORD_2, KEYCODES_MIDI_CHORD_3, KEYCODES_MIDI_CHORD_4, KEYCODES_MIDI_CHORD_5, KEYCODES_MIDI_INVERSION, KEYCODES_MIDI_SCALES, KEYCODES_MIDI_TRANSPOSE_SELECT, KEYCODES_MIDI_CC_UP, KEYCODES_MIDI_CC_DOWN, KEYCODES_MIDI_PEDAL, KEYCODES_MIDI_INOUT, \
    KEYCODES_OCTAVE_DOUBLER, KEYCODES
from widgets.square_button import SquareButton
from widgets.big_square_button import BigSquareButton
from util import tr, KeycodeDisplay
import widgets.resources  # Import Qt resources for controller images


def clear_layout_widgets(layout):
    """Remove and schedule deletion of every widget/sub-layout in ``layout``.

    Uses ``takeAt(0)`` (which removes the item synchronously) in a while-loop
    instead of the old ``for i in reversed(range(layout.count())):
    layout.itemAt(i).widget()`` pattern. That pattern cached ``count()`` up
    front, but a ``deleteLater()`` from a *previous* rebuild can be processed
    while this loop runs (any nested event processing), shrinking the real
    count below the cached range — so ``itemAt(i)`` returned ``None`` and the
    following ``.widget()`` raised
    ``AttributeError: 'NoneType' object has no attribute 'widget'`` (seen e.g.
    when renaming a macro, which triggers a full keycode-button rebuild).
    Re-reading the live count each iteration removes that race entirely.
    """
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        else:
            child = item.layout()
            if child is not None:
                clear_layout_widgets(child)


def iter_layout_widgets(layout):
    """Yield each widget currently in ``layout``, skipping missing/None items.

    A None-safe replacement for ``for i in range(layout.count()):
    layout.itemAt(i).widget()`` in relabel loops — guards against the same
    mid-loop count shrink that made ``itemAt(i)`` return ``None``.
    """
    if layout is None:
        return
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is None:
            continue
        w = item.widget()
        if w is not None:
            yield w


class AsyncValueDialog(QDialog):
    def __init__(self, parent, title, min_val, max_val, callback):
        super().__init__(parent)
        self.callback = callback
        self.setWindowTitle(title)
        self.setFixedSize(300, 150)

        layout = QVBoxLayout(self)
        
        label_widget = QLabel(f"Enter value ({min_val}-{max_val}):")
        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText(f"Enter a number between {min_val} and {max_val}")
        
        self.min_val = min_val
        self.max_val = max_val
        self.value_input.textChanged.connect(self.validate_input)
        
        confirm_button = QPushButton("Confirm")
        confirm_button.clicked.connect(self.accept)
        
        layout.addWidget(label_widget)
        layout.addWidget(self.value_input)
        layout.addWidget(confirm_button)

        self.finished.connect(self.on_finished)

    def validate_input(self, text):
        if text and (not text.isdigit() or not (self.min_val <= int(text) <= self.max_val)):
            self.value_input.clear()
            
    def on_finished(self, result):
        if result == QDialog.Accepted and self.value_input.text():
            self.callback(self.value_input.text())
        self.deleteLater()

class AsyncCCDialog(QDialog):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.setWindowTitle("Enter CC Value")
        self.setFixedHeight(170)

        layout = QVBoxLayout(self)

        cc_x_label = QLabel("CC(0-127):")
        self.cc_x_input = QLineEdit()
        self.cc_x_input.textChanged.connect(lambda text: self.validate_input(text, self.cc_x_input))

        cc_y_label = QLabel("Value(0-127):")
        self.cc_y_input = QLineEdit()
        self.cc_y_input.textChanged.connect(lambda text: self.validate_input(text, self.cc_y_input))

        layout.addWidget(cc_x_label)
        layout.addWidget(self.cc_x_input)
        layout.addWidget(cc_y_label)
        layout.addWidget(self.cc_y_input)

        confirm_button = QPushButton("Confirm")
        confirm_button.clicked.connect(self.accept)
        layout.addWidget(confirm_button)

        self.finished.connect(self.on_finished)

    def validate_input(self, text, input_field):
        if text and (not text.isdigit() or not (0 <= int(text) <= 127)):
            input_field.clear()

    def on_finished(self, result):
        if result == QDialog.Accepted:
            x_value = self.cc_x_input.text()
            y_value = self.cc_y_input.text()
            if x_value and y_value:
                self.callback(int(x_value), int(y_value))
        self.deleteLater()

class AsyncHERangeDialog(QDialog):
    """Dialog for setting HE velocity min and max range"""
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.setWindowTitle("Set Dynamic Velocity Range")
        self.setFixedSize(350, 200)

        layout = QVBoxLayout(self)

        # Instructions
        instructions = QLabel("Set the velocity range (1-127):")
        layout.addWidget(instructions)

        # Min value input
        min_label = QLabel("Minimum Velocity:")
        self.min_input = QLineEdit()
        self.min_input.setPlaceholderText("Enter min value (1-127)")
        self.min_input.textChanged.connect(lambda text: self.validate_input(text, self.min_input))

        layout.addWidget(min_label)
        layout.addWidget(self.min_input)

        # Max value input
        max_label = QLabel("Maximum Velocity:")
        self.max_input = QLineEdit()
        self.max_input.setPlaceholderText("Enter max value (1-127)")
        self.max_input.textChanged.connect(lambda text: self.validate_input(text, self.max_input))

        layout.addWidget(max_label)
        layout.addWidget(self.max_input)

        # Confirm button
        confirm_button = QPushButton("Confirm")
        confirm_button.clicked.connect(self.accept)
        layout.addWidget(confirm_button)

        self.finished.connect(self.on_finished)

    def validate_input(self, text, input_field):
        """Validate that input is a number between 1 and 127"""
        if text and (not text.isdigit() or not (1 <= int(text) <= 127)):
            input_field.clear()

    def on_finished(self, result):
        if result == QDialog.Accepted:
            min_val = self.min_input.text()
            max_val = self.max_input.text()
            if min_val and max_val:
                if int(min_val) <= int(max_val):
                    self.callback(min_val, max_val)
        self.deleteLater()

class HERangeDialog(QDialog):
    """Sync version of HE Range Dialog for desktop"""
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.setWindowTitle("Set Dynamic Velocity Range")
        self.setFixedSize(350, 200)

        layout = QVBoxLayout(self)

        # Instructions
        instructions = QLabel("Set the velocity range (1-127):")
        layout.addWidget(instructions)

        # Min value input
        min_label = QLabel("Minimum Velocity:")
        self.min_input = QLineEdit()
        self.min_input.setPlaceholderText("Enter min value (1-127)")

        layout.addWidget(min_label)
        layout.addWidget(self.min_input)

        # Max value input
        max_label = QLabel("Maximum Velocity:")
        self.max_input = QLineEdit()
        self.max_input.setPlaceholderText("Enter max value (1-127)")

        layout.addWidget(max_label)
        layout.addWidget(self.max_input)

        # Confirm button
        confirm_button = QPushButton("Confirm")
        confirm_button.clicked.connect(self.on_confirm)
        layout.addWidget(confirm_button)

    def on_confirm(self):
        min_val = self.min_input.text()
        max_val = self.max_input.text()
        if min_val and max_val and min_val.isdigit() and max_val.isdigit():
            min_int = int(min_val)
            max_int = int(max_val)
            if 1 <= min_int <= 127 and 1 <= max_int <= 127 and min_int <= max_int:
                self.callback(min_val, max_val)
                self.accept()

def show_value_dialog(parent, title, min_val, max_val, callback):
    """Factory function that handles both web and desktop environments"""
    try:
        # Check if we're in web environment
        import emscripten
        # For web, show non-modal dialog
        dialog = AsyncValueDialog(parent, title, min_val, max_val, callback)
        dialog.show()
    except ImportError:
        # For desktop, use traditional modal dialog
        dialog = AsyncValueDialog(parent, title, min_val, max_val, callback)
        dialog.exec_()

class PianoButton(SquareButton):
    def __init__(self, key_type='white', color_scheme='default'):
        super().__init__()
        if color_scheme == 'default':
            self.setStyleSheet(self.GLASS_WHITE if key_type == 'white' else self.GLASS_BLACK)
        elif color_scheme == 'keysplit':
            self.setStyleSheet(self.KS_WHITE if key_type == 'white' else self.KS_BLACK)
        elif color_scheme == 'triplesplit':
            self.setStyleSheet(self.TS_WHITE if key_type == 'white' else self.TS_BLACK)

    # Original styles
    GLASS_WHITE = """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255, 255, 255, 240), 
                stop:0.5 rgba(240, 240, 240, 240),
                stop:1 rgba(230, 230, 230, 240));
            border: 1px solid rgba(200, 200, 200, 180);
            border-radius: 4px;
            color: #303030;
            padding: 2px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255, 255, 255, 255),
                stop:1 rgba(240, 240, 240, 255));
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(230, 230, 230, 255),
                stop:1 rgba(220, 220, 220, 255));
        }
    """

    # KeySplit styles
    KS_WHITE = """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(243, 209, 209, 240),
                stop:0.5 rgba(238, 204, 204, 240),
                stop:1 rgba(233, 199, 199, 240));
            border: 1px solid rgba(128, 87, 87, 180);
            border-radius: 4px;
            color: rgba(128, 87, 87, 255);
            padding: 2px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(248, 214, 214, 255),
                stop:1 rgba(243, 209, 209, 255));
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(238, 204, 204, 255),
                stop:1 rgba(233, 199, 199, 255));
        }
    """

    GLASS_BLACK = """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(40, 40, 40, 255),
                stop:0.5 rgba(30, 30, 30, 255),
                stop:1 rgba(20, 20, 20, 255));
            border: 1px solid rgba(0, 0, 0, 255);
            border-radius: 4px;
            color: #FFFFFF;
            padding: 2px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(50, 50, 50, 255),
                stop:1 rgba(40, 40, 40, 255));
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(30, 30, 30, 255),
                stop:1 rgba(20, 20, 20, 255));
        }
    """

    KS_BLACK = """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(128, 87, 87, 255),
                stop:0.5 rgba(118, 77, 77, 255),
                stop:1 rgba(108, 67, 67, 255));
            border: 1px solid rgba(88, 47, 47, 255);
            border-radius: 4px;
            color: rgba(243, 209, 209, 255);
            padding: 2px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(138, 97, 97, 255),
                stop:1 rgba(128, 87, 87, 255));
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(118, 77, 77, 255),
                stop:1 rgba(108, 67, 67, 255));
        }
    """

    TS_BLACK = """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(128, 128, 87, 255),
                stop:0.5 rgba(118, 118, 77, 255),
                stop:1 rgba(108, 108, 67, 255));
            border: 1px solid rgba(88, 88, 47, 255);
            border-radius: 4px;
            color: rgba(209, 243, 215, 255);
            padding: 2px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(138, 138, 97, 255),
                stop:1 rgba(128, 128, 87, 255));
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(118, 118, 77, 255),
                stop:1 rgba(108, 108, 67, 255));
        }
    """

    # TripleSplit styles
    TS_WHITE = """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(209, 243, 215, 240),
                stop:0.5 rgba(204, 238, 210, 240),
                stop:1 rgba(199, 233, 205, 240));
            border: 1px solid rgba(128, 128, 87, 180);
            border-radius: 4px;
            color: rgba(128, 128, 87, 255);
            padding: 2px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(214, 248, 220, 255),
                stop:1 rgba(209, 243, 215, 255));
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(204, 238, 210, 255),
                stop:1 rgba(199, 233, 205, 255));
        }
    """


class AlternativeDisplay(QWidget):

    keycode_changed = pyqtSignal(str)

    def __init__(self, kbdef, keycodes, prefix_buttons):
        super().__init__()

        self.kb_display = None
        self.keycodes = keycodes
        self.buttons = []

        self.key_layout = FlowLayout()

        if prefix_buttons:
            for title, code in prefix_buttons:
                btn = SquareButton()
                btn.setRelSize(KEYCODE_BTN_RATIO)
                btn.setText(title)
                btn.clicked.connect(lambda st, k=code: self.keycode_changed.emit(title))
                self.key_layout.addWidget(btn)

        layout = QVBoxLayout()
        if kbdef:
            self.kb_display = DisplayKeyboard(kbdef)
            self.kb_display.keycode_changed.connect(self.keycode_changed)
            layout.addWidget(self.kb_display)
            layout.setAlignment(self.kb_display, Qt.AlignHCenter)
        layout.addLayout(self.key_layout)
        self.setLayout(layout)

    def recreate_buttons(self, keycode_filter):
        for btn in self.buttons:
            btn.deleteLater()
        self.buttons = []

        for keycode in self.keycodes:
            if not keycode_filter(keycode.qmk_id):
                continue
            btn = SquareButton()
            btn.setRelSize(KEYCODE_BTN_RATIO)
            btn.setToolTip(Keycode.tooltip(keycode.qmk_id))
            btn.clicked.connect(lambda st, k=keycode: self.keycode_changed.emit(k.qmk_id))
            btn.keycode = keycode
            self.key_layout.addWidget(btn)
            self.buttons.append(btn)

        self.relabel_buttons()

    def relabel_buttons(self):
        if self.kb_display:
            self.kb_display.relabel_buttons()

        KeycodeDisplay.relabel_buttons(self.buttons)

    def required_width(self):
        return self.kb_display.sizeHint().width() if self.kb_display else 0

    def has_buttons(self):
        return len(self.buttons) > 0


class Tab(QScrollArea):

    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, alts, prefix_buttons=None):
        super().__init__(parent)

        self.label = label
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.alternatives = []
        for kb, keys in alts:
            alt = AlternativeDisplay(kb, keys, prefix_buttons)
            alt.keycode_changed.connect(self.keycode_changed)
            self.layout.addWidget(alt)
            self.alternatives.append(alt)

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setWidgetResizable(True)

        w = QWidget()
        w.setLayout(self.layout)
        self.setWidget(w)

    def recreate_buttons(self, keycode_filter):
        for alt in self.alternatives:
            alt.recreate_buttons(keycode_filter)
        self.setVisible(self.has_buttons())

    def relabel_buttons(self):
        for alt in self.alternatives:
            alt.relabel_buttons()

    def has_buttons(self):
        for alt in self.alternatives:
            if alt.has_buttons():
                return True
        return False

    def select_alternative(self):
        # hide everything first
        for alt in self.alternatives:
            alt.hide()

        # then display first alternative which fits on screen w/o horizontal scroll
        for alt in self.alternatives:
            if self.width() - self.verticalScrollBar().width() > alt.required_width():
                alt.show()
                break

    def resizeEvent(self, evt):
        super().resizeEvent(evt)
        self.select_alternative()        
        
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QGridLayout, QSpacerItem, QSizePolicy, QPushButton
from PyQt5.QtCore import pyqtSignal

class CenteredComboBox(ArrowComboBox):
    """ComboBox with centered text and arrow drawn programmatically"""

    def paintEvent(self, event):
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)

        painter = QPainter(self)
        self.style().drawComplexControl(self.style().CC_ComboBox, opt, painter, self)

        # Center the text horizontally
        text_rect = self.style().subControlRect(self.style().CC_ComboBox, opt, self.style().SC_ComboBoxEditField, self)
        painter.drawText(text_rect, Qt.AlignCenter, self.currentText())

        # Draw dropdown arrow (from ArrowComboBox)
        arrow_rect = self.style().subControlRect(self.style().CC_ComboBox, opt, self.style().SC_ComboBoxArrow, self)
        arrow_center_x = arrow_rect.center().x()
        arrow_center_y = arrow_rect.center().y()

        arrow_size = 4
        arrow = QPolygon([
            QPoint(arrow_center_x - arrow_size, arrow_center_y - 2),
            QPoint(arrow_center_x + arrow_size, arrow_center_y - 2),
            QPoint(arrow_center_x, arrow_center_y + 3)
        ])

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.palette().color(QPalette.Text)))
        painter.drawPolygon(arrow)

    def wheelEvent(self, event):
        # Ignore the wheel event to prevent changing selection
        event.ignore()

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem, 
    QVBoxLayout, QWidget, QComboBox, QHBoxLayout, QScrollArea, QAction
)
from PyQt5.QtCore import Qt, pyqtSignal

class SmartChordTab(QScrollArea):
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, smartchord_keycodes_0, smartchord_keycodes_1, smartchord_keycodes_2, smartchord_keycodes_3, smartchord_keycodes_4, smartchord_keycodes_5, scales_modes_keycodes, inversion_keycodes, chord_qb_keycodes=None, dynchord_qb_keycodes=None):
        super().__init__(parent)
        self.label = label
        self.smartchord_keycodes_0 = smartchord_keycodes_0
        self.smartchord_keycodes_1 = smartchord_keycodes_1
        self.smartchord_keycodes_2 = smartchord_keycodes_2
        self.smartchord_keycodes_3 = smartchord_keycodes_3
        self.smartchord_keycodes_4 = smartchord_keycodes_4
        self.smartchord_keycodes_5 = smartchord_keycodes_5
        self.scales_modes_keycodes = scales_modes_keycodes
        self.inversion_keycodes = inversion_keycodes
        self.chord_qb_keycodes = chord_qb_keycodes or []
        self.dynchord_qb_keycodes = dynchord_qb_keycodes or []

        # Store all tree widgets for managing selections
        self.trees = []

        # Create a widget for the scroll area content
        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)

        # Set the scroll area properties
        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        # Create a horizontal layout to hold the QTreeWidgets
        self.tree_layout = QHBoxLayout()
        self.tree_layout.setSpacing(1)
        self.populate_tree()

        # Add the QTreeWidget layout to the main layout
        self.main_layout.addLayout(self.tree_layout)

        # Layout for inversion buttons
        self.button_layout = QGridLayout()
        
        # Center the button layout
        button_container = QHBoxLayout()
        button_container.addStretch(1)  # Left spacer
        button_container.addLayout(self.button_layout)
        button_container.addStretch(1)  # Right spacer
        
        self.main_layout.addLayout(button_container)

        # Populate the inversion buttons
        self.recreate_buttons()

        # Quick Build Smart Chord buttons
        if self.chord_qb_keycodes:
            chord_qb_group = QGroupBox("Quick Build Smart Chord")
            chord_qb_layout = FlowLayout()
            for keycode in self.chord_qb_keycodes:
                btn = SquareButton()
                btn.setFixedSize(50, 50)
                btn.setText(str(keycode.label))
                btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
                btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = keycode
                chord_qb_layout.addWidget(btn)
            chord_qb_group.setLayout(chord_qb_layout)
            self.main_layout.addWidget(chord_qb_group)

        # Quick Build Dynamic Chord buttons
        if self.dynchord_qb_keycodes:
            dynchord_qb_group = QGroupBox("Quick Build Dynamic Chord")
            dynchord_qb_layout = FlowLayout()
            for keycode in self.dynchord_qb_keycodes:
                btn = SquareButton()
                btn.setFixedSize(50, 50)
                btn.setText(str(keycode.label))
                btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
                btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = keycode
                dynchord_qb_layout.addWidget(btn)
            dynchord_qb_group.setLayout(dynchord_qb_layout)
            self.main_layout.addWidget(dynchord_qb_group)

        # Spacer to push everything to the top
        self.main_layout.addStretch()

    def populate_tree(self):
        """Populate the QTreeWidget with categories and keycodes."""
        # Create the QTreeWidgetItems for each category
        self.create_keycode_tree(self.smartchord_keycodes_0, "Intervals")
        self.create_keycode_tree(self.smartchord_keycodes_1, "3 Note Chords")
        self.create_keycode_tree(self.smartchord_keycodes_2, "4 Note Chords")
        self.create_keycode_tree(self.smartchord_keycodes_3, "5 Note Chords")
        self.create_keycode_tree(self.smartchord_keycodes_4, "6 Note Chords")
        self.create_keycode_tree(self.smartchord_keycodes_5, "Other")
        self.create_keycode_tree(self.scales_modes_keycodes, "Scales/Modes")

    def create_keycode_tree(self, keycodes, title):
        """Create a QTreeWidget and add keycodes under it."""
        tree = QTreeWidget()
        tree.setHeaderLabel(title)
        self.add_keycode_group(tree, title, keycodes)
        tree.setFixedHeight(300)
        tree.setStyleSheet("border: 2px;")
        tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Set selection mode to single selection
        tree.setSelectionMode(QTreeWidget.SingleSelection)
        
        # Connect itemClicked signal to on_item_selected
        tree.itemClicked.connect(self.on_item_selected)
        
        # Add tree to our list of trees
        self.trees.append(tree)

        # Add the QTreeWidget instance to the horizontal layout
        self.tree_layout.addWidget(tree)

    def add_keycode_group(self, tree, title, keycodes):
        """Helper function to add keycodes to a QTreeWidget."""
        for keycode in keycodes:
            # Use the third value (description) and replace newlines with spaces
            try:
                # For table items, use the third element (description) with newlines replaced
                label_text = str(Keycode.description(keycode.qmk_id)).replace("\n", "  ")
            except Exception:
                # Fallback to QMK ID if anything fails
                label_text = str(keycode.qmk_id)
            
            keycode_item = QTreeWidgetItem(tree, [label_text])
            keycode_item.setData(0, Qt.UserRole, keycode.qmk_id)  # Store qmk_id for easy access

            # Force text to be on one line and left-aligned
            keycode_item.setTextAlignment(0, Qt.AlignLeft)
            
            # Ensure the text is set
            keycode_item.setText(0, label_text)

    def on_item_selected(self, clicked_item, column):
        """Handle tree item selection and clear other trees' selections."""
        # Get the tree that was clicked
        clicked_tree = clicked_item.treeWidget()
        
        # Block signals temporarily to prevent recursion
        for tree in self.trees:
            tree.blockSignals(True)
            
        try:
            # Clear selection in all other trees
            for tree in self.trees:
                if tree != clicked_tree:
                    tree.clearSelection()
                    tree.setCurrentItem(None)
            
            # Ensure the clicked item is selected
            clicked_item.setSelected(True)
            
            # Get the data from the clicked item
            qmk_id = clicked_item.data(0, Qt.UserRole)
            if qmk_id:
                self.keycode_changed.emit(qmk_id)
                
        finally:
            # Restore signals
            for tree in self.trees:
                tree.blockSignals(False)

    def recreate_buttons(self, keycode_filter=None):
        """Recreates the buttons for the inversion keycodes."""
        clear_layout_widgets(self.button_layout)

        row = 0
        col = 0
        max_columns = 15  # Limit columns for better appearance
        
        for keycode in self.inversion_keycodes:
            if keycode_filter is None or keycode_filter(keycode.qmk_id):
                btn = SquareButton()
                btn.setFixedSize(50, 50)  # Set fixed size to 50x50 as requested
                
                # For inversion buttons, use the second element (label) instead of description
                try:
                    # Try to access the second element directly (the label with preserved newlines)
                    button_text = str(keycode.label)  # Use label property instead of description
                except Exception:
                    # If there's no direct access, try alternative approach
                    try:
                        # Fallback 1: Try to get label via a method if it exists
                        button_text = str(Keycode.label(keycode.qmk_id))
                    except Exception:
                        # Fallback 2: Use QMK ID if all else fails
                        button_text = str(keycode.qmk_id)
                
                btn.setText(button_text)
                btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = keycode

                self.button_layout.addWidget(btn, row, col)
                col += 1
                if col >= max_columns:
                    col = 0
                    row += 1

    def on_selection_change(self, index):
        selected_qmk_id = self.sender().itemData(index)
        if selected_qmk_id:
            self.keycode_changed.emit(selected_qmk_id)

    def relabel_buttons(self):
        """Relabel buttons based on keycodes."""
        for widget in iter_layout_widgets(self.button_layout):
            if isinstance(widget, SquareButton) and hasattr(widget, 'keycode'):
                keycode = widget.keycode
                if keycode:
                    # For inversion buttons, use the second element (label) instead of description
                    try:
                        # Try to access the second element directly (the label with preserved newlines)
                        button_text = str(keycode.label)  # Use label property instead of description
                    except Exception:
                        # If there's no direct access, try alternative approach
                        try:
                            # Fallback 1: Try to get label via a method if it exists
                            button_text = str(Keycode.label(keycode.qmk_id))
                        except Exception:
                            # Fallback 2: Use QMK ID if all else fails
                            button_text = str(keycode.qmk_id)
                    
                    widget.setText(button_text)

    def has_buttons(self):
        """Check if buttons exist in the layout."""
        return self.button_layout.count() > 0

from PyQt5.QtWidgets import (
    QScrollArea, QVBoxLayout, QGridLayout, QLabel, QMenu, QPushButton, QHBoxLayout, QWidget, QDialog, QLineEdit, QComboBox
)
from PyQt5.QtCore import pyqtSignal, Qt
class midiadvancedTab(QScrollArea):
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, inversion_keycodes, smartchord_program_change, smartchord_LSB, smartchord_MSB, smartchord_CC_toggle, CCfixed, CCup, CCdown, velocity_multiplier_options, cc_multiplier_options, channel_options, velocity_options, channel_oneshot, channel_hold, smartchord_octave_1, smartchord_key, ksvelocity2, ksvelocity3, kskey2, kskey3, ksoctave2, ksoctave3, kschannel2, kschannel3, inversion_keycodes2, CCencoder, velocityshuffle, inversion_keycodesspecial, KEYCODES_SETTINGS1, KEYCODES_SETTINGS2, KEYCODES_SETTINGS3, keycodes_midi_inout=None, include_sections=None, external_sections=None):
        super().__init__(parent)
        self.label = label

        # Initialize dictionaries first
        self.buttons = {}

        # Store all the parameters as instance variables
        self.inversion_keycodes = inversion_keycodes
        self.inversion_keycodes2 = inversion_keycodes2
        self.inversion_keycodesspecial = inversion_keycodesspecial
        self.smartchord_program_change = smartchord_program_change
        self.smartchord_LSB = smartchord_LSB
        self.smartchord_MSB = smartchord_MSB
        self.smartchord_CC_toggle = smartchord_CC_toggle
        self.CCfixed = CCfixed
        self.CCup = CCup
        self.CCdown = CCdown
        self.CCencoder = CCencoder
        self.velocityshuffle = velocityshuffle
        self.velocity_multiplier_options = velocity_multiplier_options
        self.cc_multiplier_options = cc_multiplier_options
        self.channel_options = channel_options
        self.velocity_options = velocity_options
        self.channel_oneshot = channel_oneshot
        self.channel_hold = channel_hold
        self.smartchord_octave_1 = smartchord_octave_1
        self.smartchord_key = smartchord_key
        self.ksvelocity2 = ksvelocity2
        self.ksvelocity3 = ksvelocity3
        self.kskey2 = kskey2
        self.kskey3 = kskey3
        self.ksoctave2 = ksoctave2
        self.ksoctave3 = ksoctave3
        self.kschannel2 = kschannel2
        self.kschannel3 = kschannel3
        self.keycodes_settings1 = KEYCODES_SETTINGS1
        self.keycodes_settings2 = KEYCODES_SETTINGS2
        self.keycodes_settings3 = KEYCODES_SETTINGS3
        self.keycodes_midi_inout = keycodes_midi_inout if keycodes_midi_inout is not None else KEYCODES_MIDI_INOUT

        # Create scroll area content
        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # Define sections (display_name, section_key). include_sections filters
        # the standard set by display name; external_sections appends fully
        # self-contained tab widgets as extra side-tab sections.
        all_sections = [
            ("Channel", "Show\nChannel\nOptions"),
            ("CC Options", "Show\nCC Options"),
            ("Transposition", "Show\nTransposition\nSettings"),
            ("KeySplit", "Show\nKeySplit\nOptions"),
            ("Advanced MIDI", "Show\nAdvanced MIDI\nOptions"),
            ("Velocity", "Show\nVelocity\nOptions"),
            ("In/Out", "Show\nIn/Out\nOptions"),
            ("Touch Dial", "Show\nTouch Dial\nOptions"),
            ("Presets", "Show\nSetting\nPresets"),
            ("Advanced Keys", "Show\nAdvanced\nKeys")
        ]
        if include_sections is not None:
            all_sections = [s for s in all_sections if s[0] in include_sections]
        self.external_widgets = {}
        if external_sections:
            for _ext_name, _ext_widget in external_sections:
                all_sections.append((_ext_name, _ext_name))
                self.external_widgets[_ext_name] = _ext_widget
        self.sections = all_sections

        # Create horizontal layout: side tabs on left, content box on right (VIA style)
        main_layout_h = QHBoxLayout()
        main_layout_h.setSpacing(0)
        main_layout_h.setContentsMargins(0, 0, 0, 0)

        # Create side tabs container with border
        side_tabs_container = QWidget()
        side_tabs_container.setObjectName("side_tabs_container")
        side_tabs_container.setStyleSheet("""
            QWidget#side_tabs_container {
                background: palette(window);
                border: 1px solid palette(mid);
                border-right: none;
            }
        """)
        side_tabs_layout = QVBoxLayout(side_tabs_container)
        side_tabs_layout.setSpacing(0)
        side_tabs_layout.setContentsMargins(0, 0, 0, 0)

        self.side_tab_buttons = {}
        for display_name, section_key in self.sections:
            btn = QPushButton(display_name)
            btn.setCheckable(True)
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)
            btn.setStyleSheet("""
                QPushButton {
                    border: 1px solid palette(mid);
                    border-radius: 0px;
                    border-right: none;
                    background: palette(button);
                    text-align: left;
                    padding-left: 15px;
                    font-size: 9pt;
                }
                QPushButton:hover:!checked {
                    background: palette(light);
                }
                QPushButton:checked {
                    background: palette(base);
                    font-weight: 600;
                    border-right: 1px solid palette(base);
                }
            """)
            btn.clicked.connect(lambda checked, sk=section_key: self.show_section(sk))
            side_tabs_layout.addWidget(btn)
            self.side_tab_buttons[section_key] = btn

        side_tabs_layout.addStretch(1)
        main_layout_h.addWidget(side_tabs_container)
        if len(self.sections) <= 1:
            side_tabs_container.hide()

        # Create content container with border
        self.content_wrapper = QWidget()
        self.content_wrapper.setObjectName("content_wrapper")
        self.content_wrapper.setStyleSheet("""
            QWidget#content_wrapper {
                border: 1px solid palette(mid);
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 0.1,
                                           stop: 0 palette(alternate-base),
                                           stop: 1 palette(base));
            }
        """)
        self.content_layout = QVBoxLayout(self.content_wrapper)
        self.content_layout.setSpacing(10)
        self.content_layout.setContentsMargins(15, 15, 15, 15)

        # Create layouts for sections
        # Advanced MIDI grid
        self.advanced_h_layout = QHBoxLayout()
        self.advanced_h_layout.addStretch(1)
        self.advanced_grid = QGridLayout()
        self.advanced_h_layout.addLayout(self.advanced_grid)
        self.advanced_h_layout.addStretch(1)

        # KeySplit grid
        self.keysplit_h_layout = QHBoxLayout()
        self.keysplit_h_layout.addStretch(1)
        self.keysplit_grid = QGridLayout()
        self.keysplit_h_layout.addLayout(self.keysplit_grid)
        self.keysplit_h_layout.addStretch(1)

        # Create wrapper widgets for each section
        self.section_widgets = {}
        _wanted_keys = {sk for _, sk in self.sections if sk not in self.external_widgets}
        self.section_layouts = {}
        if "Show\nAdvanced MIDI\nOptions" in _wanted_keys:
            self.section_layouts["Show\nAdvanced MIDI\nOptions"] = self.advanced_h_layout
        if "Show\nKeySplit\nOptions" in _wanted_keys:
            self.section_layouts["Show\nKeySplit\nOptions"] = self.keysplit_h_layout

        # Create VBoxLayouts for other sections
        for display_name, section_key in self.sections:
            if section_key not in self.section_layouts and section_key not in self.external_widgets:
                section_layout = QVBoxLayout()
                section_layout.setSpacing(10)
                self.section_layouts[section_key] = section_layout

        # Wrap each layout in a QWidget container
        for section_key, section_layout in self.section_layouts.items():
            wrapper = QWidget()
            wrapper.setObjectName("section_wrapper")
            # Make wrapper border invisible - use ID selector to avoid affecting children
            wrapper.setStyleSheet("""
                QWidget#section_wrapper {
                    border: none;
                }
            """)
            wrapper.setLayout(section_layout)
            wrapper.hide()  # Hide all initially
            self.content_layout.addWidget(wrapper)
            self.section_widgets[section_key] = wrapper

        # External section widgets are full tab objects: hide, add, wire signal
        for _ext_key, _ext_widget in self.external_widgets.items():
            _ext_widget.hide()
            _ext_widget.keycode_changed.connect(self.keycode_changed.emit)
            self.content_layout.addWidget(_ext_widget)
            self.section_widgets[_ext_key] = _ext_widget

        self.content_layout.addStretch(1)
        main_layout_h.addWidget(self.content_wrapper)
        self.main_layout.addLayout(main_layout_h)

        # Populate the standard sections that are present
        _populators = {
            "Show\nChannel\nOptions": self.populate_channel_section,
            "Show\nCC Options": self.populate_cc_velocity_section,
            "Show\nTransposition\nSettings": self.populate_transposition_section,
            "Show\nKeySplit\nOptions": self.populate_keysplit_section,
            "Show\nAdvanced MIDI\nOptions": self.populate_advanced_section,
            "Show\nVelocity\nOptions": self.populate_velocity_section,
            "Show\nIn/Out\nOptions": self.populate_inout_section,
            "Show\nTouch Dial\nOptions": self.populate_expression_wheel_section,
            "Show\nSetting\nPresets": self.populate_settings_presets_section,
            "Show\nAdvanced\nKeys": self.populate_advanced_keys_section,
        }
        for _sk, _populate in _populators.items():
            if _sk in self.section_layouts:
                _populate()

        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        # Show first section by default
        if self.sections:
            self.show_section(self.sections[0][1])
        
    def populate_settings_presets_section(self):
        """Populate the Setting Presets section with three rows of buttons."""
        layout = self.section_layouts["Show\nSetting\nPresets"]

        # First row - KEYCODES_SETTINGS1 (centered)
        row1_layout = QHBoxLayout()
        row1_layout.addStretch(1)

        for keycode in self.keycodes_settings1:
            btn = SquareButton()
            btn.setFixedSize(50, 50)
            btn.setText(Keycode.label(keycode.qmk_id))
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode
            row1_layout.addWidget(btn)

        row1_layout.addStretch(1)
        layout.addLayout(row1_layout)

        # Second row - KEYCODES_SETTINGS2
        row2_layout = QHBoxLayout()
        row2_layout.addStretch(1)

        for keycode in self.keycodes_settings2:
            btn = SquareButton()
            btn.setFixedSize(50, 50)
            btn.setText(Keycode.label(keycode.qmk_id))
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode
            row2_layout.addWidget(btn)

        row2_layout.addStretch(1)
        layout.addLayout(row2_layout)

        # Third row - KEYCODES_SETTINGS3
        row3_layout = QHBoxLayout()
        row3_layout.addStretch(1)

        for keycode in self.keycodes_settings3:
            btn = SquareButton()
            btn.setFixedSize(50, 50)
            btn.setText(Keycode.label(keycode.qmk_id))
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode
            row3_layout.addWidget(btn)

        row3_layout.addStretch(1)
        layout.addLayout(row3_layout)

        layout.addStretch()

    # Category definitions: (display_name, keycode_list, search_terms, widget_type, value_template)
    # widget_type: "dropdown" = combo box, "value_input" = type-a-number button, "cc_xy" = CC X,Y dialog, "range" = min/max dialog
    # value_template: format string for value_input (e.g. "MI_CC_{}_TOG"), or None
    _ADV_CATEGORIES = None  # Built lazily

    def _get_dropdown_categories(self):
        """Build categories lazily (needs keycode lists to be populated)."""
        if self._ADV_CATEGORIES is not None:
            return self._ADV_CATEGORIES
        from keycodes.keycodes import (
            KEYCODES_MIDI_CC, KEYCODES_MIDI_CC_UP, KEYCODES_MIDI_CC_DOWN, KEYCODES_MIDI_CC_FIXED,
            KEYCODES_MOD_PRESS,
            KEYCODES_QB_MASTER, KEYCODES_DRUM_SLOTS,
            KEYCODES_MIDI_CHANNEL, KEYCODES_MIDI_CHANNEL_OS, KEYCODES_MIDI_CHANNEL_HOLD,
            KEYCODES_MIDI_VELOCITY, KEYCODES_VELOCITY_STEPSIZE, KEYCODES_VELOCITY_SHUFFLE,
            KEYCODES_CC_ENCODERVALUE, KEYCODES_MIDI_TRANSPOSE_SELECT, KEYCODES_MIDI_KEY2, KEYCODES_MIDI_KEY3,
            KEYCODES_MIDI_OCTAVE2, KEYCODES_MIDI_OCTAVE3,
            KEYCODES_MIDI_CHANNEL_KEYSPLIT, KEYCODES_MIDI_CHANNEL_KEYSPLIT2,
            KEYCODES_MIDI_BANK_LSB, KEYCODES_MIDI_BANK_MSB,
            KEYCODES_Program_Change,
            KEYCODES_ARPEGGIATOR_PRESETS, KEYCODES_STEP_SEQUENCER_PRESETS,
            KEYCODES_DELAY_FACTORY, KEYCODES_DELAY_USER,
            KEYCODES_MIDI_VELOCITY2, KEYCODES_MIDI_VELOCITY3,
            KEYCODES_CC_STEPSIZE,
        )
        # (display_name, kc_list, search_terms, widget_type, value_template_or_None)
        self._ADV_CATEGORIES = [
            # Value-input selectors (type a number 0-127, opens dialog)
            ("CC On/Off", KEYCODES_MIDI_CC, "cc toggle on off", "value_input", "MI_CC_{}_TOG"),
            ("CC Up", KEYCODES_MIDI_CC_UP, "cc up increment", "value_input", "MI_CC_{}_UP"),
            ("CC Down", KEYCODES_MIDI_CC_DOWN, "cc down decrement", "value_input", "MI_CC_{}_DWN"),
            ("Dynamic CC", KEYCODES_MOD_PRESS, "dynamic cc mod press key depth analog expression", "value_input", "MI_MOD_PRESS_{}"),
            ("Quickbuild", KEYCODES_QB_MASTER, "quickbuild quick build master qb slot", "value_input", "QB_MASTER_{}"),
            ("CC Value", KEYCODES_MIDI_CC_FIXED, "cc fixed value set", "cc_xy", None),
            ("Touch Dial CC", KEYCODES_CC_ENCODERVALUE, "cc encoder touch dial", "value_input", "MI_CCENCODER_{}"),
            ("Program Change", KEYCODES_Program_Change, "program change", "value_input", "MI_PROG_{}"),
            ("Bank Select LSB", KEYCODES_MIDI_BANK_LSB, "bank lsb select", "value_input", "MI_BANK_LSB_{}"),
            ("Bank Select MSB", KEYCODES_MIDI_BANK_MSB, "bank msb select", "value_input", "MI_BANK_MSB_{}"),
            ("Set Velocity (Main)", KEYCODES_MIDI_VELOCITY, "velocity set main", "value_input", "MI_VELOCITY_{}"),
            ("Set Velocity (KeySplit)", KEYCODES_MIDI_VELOCITY2, "velocity keysplit ks", "value_input", "MI_VELOCITY2_{}"),
            ("Set Velocity (TripleSplit)", KEYCODES_MIDI_VELOCITY3, "velocity triplesplit ts", "value_input", "MI_VELOCITY3_{}"),
            # Range dialog (two inputs: min and max)
            ("Set Dynamic Velocity Range", KEYCODES_HE_VELOCITY_RANGE, "dynamic velocity range he min max", "range", None),
            # Dropdowns (select from list)
            ("MIDI Channel", KEYCODES_MIDI_CHANNEL, "midi channel set", "dropdown", None),
            ("Multi Channel", KEYCODES_MULTICHANNEL, "multi channel echo multichannel", "dropdown", None),
            ("Temporary MIDI Channel", KEYCODES_MIDI_CHANNEL_OS, "temporary channel oneshot", "dropdown", None),
            ("Hold MIDI Channel", KEYCODES_MIDI_CHANNEL_HOLD, "hold channel", "dropdown", None),
            ("KeySplit Channel", KEYCODES_MIDI_CHANNEL_KEYSPLIT, "keysplit channel ks", "dropdown", None),
            ("TripleSplit Channel", KEYCODES_MIDI_CHANNEL_KEYSPLIT2, "triplesplit channel ts", "dropdown", None),
            ("Velocity Increment", KEYCODES_VELOCITY_STEPSIZE, "velocity increment stepsize step size", "dropdown", None),
            ("Dynamic Velocity Range", KEYCODES_VELOCITY_SHUFFLE, "dynamic range velocity shuffle", "dropdown", None),
            ("CC Increment", KEYCODES_CC_STEPSIZE, "cc increment stepsize step size", "dropdown", None),
            ("Set Transpose (Main)", KEYCODES_MIDI_TRANSPOSE_SELECT, "transpose transposition set main key octave semitone", "dropdown", None),
            ("Set Key (KeySplit)", KEYCODES_MIDI_KEY2, "key transposition keysplit ks", "dropdown", None),
            ("Set Key (TripleSplit)", KEYCODES_MIDI_KEY3, "key transposition triplesplit ts", "dropdown", None),
            ("Set Octave (KeySplit)", KEYCODES_MIDI_OCTAVE2, "octave keysplit ks", "dropdown", None),
            ("Set Octave (TripleSplit)", KEYCODES_MIDI_OCTAVE3, "octave triplesplit ts", "dropdown", None),
            ("Arpeggiator Presets", KEYCODES_ARPEGGIATOR_PRESETS, "arpeggiator arp preset", "dropdown", None),
            ("Sequencer Presets", KEYCODES_STEP_SEQUENCER_PRESETS, "sequencer seq user preset", "dropdown", None),
            ("Drum Machine Slots", KEYCODES_DRUM_SLOTS, "drum machine slot", "dropdown", None),
            ("Delay Factory Presets", KEYCODES_DELAY_FACTORY, "delay factory preset", "dropdown", None),
            ("Delay User Presets", KEYCODES_DELAY_USER, "delay user preset slot", "dropdown", None),
        ]
        # Build set of qmk_ids that belong to categories (skip from button display)
        self._adv_dropdown_ids = set()
        for _, kc_list, _, _, _ in self._ADV_CATEGORIES:
            for kc in kc_list:
                self._adv_dropdown_ids.add(kc.qmk_id)
        return self._ADV_CATEGORIES

    # Search synonyms: common terms mapped to what appears in labels/ids
    _SEARCH_SYNONYMS = {
        "up": ["\u25b2", "▲", "_up", "_octu", "_trnsu", "_chu", "increase"],
        "down": ["\u25bc", "▼", "_down", "_octd", "_trnsd", "_chd", "decrease"],
        "increment": ["stepsize", "step size", "step_size"],
        "transpose": ["trns", "transposition"],
        "channel": ["channel", "midi_ch", "_ch_", "mi_ch"],
        "velocity": ["vel", "velocity"],
        "octave": ["oct", "octave"],
        "smart chord": ["smartchord", "chord_99", "quickchord"],
        "bpm": ["bpm", "tap", "mi_tap"],
        "loop": ["dm_macro", "dm_rec", "loop"],
        "mute": ["mute"],
        "overdub": ["overdub"],
        "sustain": ["sus", "pedal"],
        "split": ["keysplit", "triplesplit", "ks_", "ts_"],
    }

    # Tab/section synonyms: when ANY of these terms appear in search,
    # force-include ALL keycodes from that section (by qmk_id).
    # Maps frozenset of search trigger words → list of qmk_ids.
    _TAB_SECTION_MAP = None  # Built lazily

    def _get_tab_section_map(self):
        """Build mapping of tab search terms → qmk_ids belonging to that tab. Lazy."""
        if self._TAB_SECTION_MAP is not None:
            return self._TAB_SECTION_MAP

        m = {}

        # Channel tab
        chan_ids = set()
        for kc_list in [self.channel_options, self.channel_oneshot, self.channel_hold]:
            for kc in kc_list:
                chan_ids.add(kc.qmk_id)
        for term in ["channel", "chan", "midi channel"]:
            m[term] = chan_ids

        # CC Options tab
        cc_ids = set()
        for kc_list in [self.smartchord_CC_toggle, self.CCup, self.CCdown,
                        self.CCencoder, self.cc_multiplier_options,
                        self.smartchord_program_change, self.smartchord_LSB, self.smartchord_MSB]:
            for kc in kc_list:
                cc_ids.add(kc.qmk_id)
        for kc in KEYCODES_MIDI_CC_FIXED:
            cc_ids.add(kc.qmk_id)
        for term in ["cc", "cc options", "control change", "midi cc", "program change", "bank"]:
            m[term] = cc_ids

        # Transposition tab
        trans_ids = set()
        for kc_list in [self.smartchord_octave_1, self.smartchord_key]:
            for kc in kc_list:
                trans_ids.add(kc.qmk_id)
        for term in ["transpose", "transposition", "key selector", "octave selector"]:
            m[term] = trans_ids

        # KeySplit tab
        ks_ids = set()
        for kc in self.inversion_keycodes2:
            ks_ids.add(kc.qmk_id)
        ks_ids.update(["KS_TOGGLE", "KS_VELOCITY_TOGGLE", "KS_TRANSPOSE_TOGGLE"])
        for term in ["keysplit", "key split", "triplesplit", "triple split", "split"]:
            m[term] = ks_ids

        # Advanced MIDI (inversions)
        inv_ids = set()
        for kc in self.inversion_keycodes:
            inv_ids.add(kc.qmk_id)
        for term in ["inversion", "inversions", "advanced midi", "chord inversion"]:
            m[term] = inv_ids

        # Velocity tab
        vel_ids = set()
        for kc_list in [self.velocity_multiplier_options]:
            for kc in kc_list:
                vel_ids.add(kc.qmk_id)
        vel_ids.update(["MI_VELOCITY_UP", "MI_VELOCITY_DOWN"])
        for kc in KEYCODES_HE_VELOCITY_CURVE:
            vel_ids.add(kc.qmk_id)
        # Note: KEYCODES_HE_VELOCITY_RANGE (8128 items) excluded - use range dialog instead
        for term in ["velocity", "vel", "playing style", "velocity curve", "articulation"]:
            m[term] = vel_ids

        # In/Out tab
        inout_ids = set()
        for kc in self.keycodes_midi_inout:
            inout_ids.add(kc.qmk_id)
        for term in ["in/out", "inout", "in out", "routing", "midi routing", "override"]:
            m[term] = inout_ids

        # Touch Dial tab
        td_ids = set()
        for kc in self.inversion_keycodesspecial:
            td_ids.add(kc.qmk_id)
        for kc_list in [self.CCencoder, self.velocity_multiplier_options, self.cc_multiplier_options]:
            for kc in kc_list:
                td_ids.add(kc.qmk_id)
        for term in ["touch dial", "expression", "wheel", "encoder"]:
            m[term] = td_ids

        # Presets tab
        preset_ids = set()
        for kc_list in [self.keycodes_settings1, self.keycodes_settings2, self.keycodes_settings3]:
            for kc in kc_list:
                preset_ids.add(kc.qmk_id)
        for term in ["preset", "presets", "settings", "save settings", "load settings", "factory"]:
            m[term] = preset_ids

        self._TAB_SECTION_MAP = m
        return m

    def populate_advanced_keys_section(self):
        """Populate the Advanced Keys section with search bar + all keycodes."""
        layout = self.section_layouts["Show\nAdvanced\nKeys"]

        # Search bar
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_label.setFixedWidth(50)
        self.adv_search_bar = QLineEdit()
        self.adv_search_bar.setPlaceholderText("Type to filter keycodes (e.g. transpose up, CC increment, loop, channel)...")
        self.adv_search_bar.setFixedHeight(30)
        # Debounce timer - wait 400ms after user stops typing before updating
        self._adv_search_timer = QTimer()
        self._adv_search_timer.setSingleShot(True)
        self._adv_search_timer.setInterval(400)
        self._adv_search_timer.timeout.connect(self._on_search_debounced)
        self.adv_search_bar.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.adv_search_bar)
        layout.addLayout(search_layout)

        # Result count + pagination label
        self._adv_current_page = 0
        count_page_layout = QHBoxLayout()
        self.adv_count_label = QLabel("")
        self.adv_count_label.setStyleSheet("font-size: 8pt; color: palette(mid);")
        count_page_layout.addWidget(self.adv_count_label)
        count_page_layout.addStretch(1)
        # Pagination controls
        self.adv_prev_btn = QPushButton("< Prev")
        self.adv_prev_btn.setFixedSize(70, 24)
        self.adv_prev_btn.clicked.connect(self._adv_prev_page)
        self.adv_prev_btn.hide()
        self.adv_page_label = QLabel("")
        self.adv_page_label.setStyleSheet("font-size: 8pt;")
        self.adv_next_btn = QPushButton("Next >")
        self.adv_next_btn.setFixedSize(70, 24)
        self.adv_next_btn.clicked.connect(self._adv_next_page)
        self.adv_next_btn.hide()
        count_page_layout.addWidget(self.adv_prev_btn)
        count_page_layout.addWidget(self.adv_page_label)
        count_page_layout.addWidget(self.adv_next_btn)
        layout.addLayout(count_page_layout)

        # Container for dropdowns + buttons
        self.adv_keys_container = QWidget()
        self.adv_keys_layout = QVBoxLayout(self.adv_keys_container)
        self.adv_keys_layout.setSpacing(6)
        self.adv_keys_layout.setContentsMargins(0, 0, 0, 0)

        # Dropdown area
        self.adv_dropdown_container = QWidget()
        self.adv_dropdown_flow = FlowLayout()
        self.adv_dropdown_container.setLayout(self.adv_dropdown_flow)
        self.adv_keys_layout.addWidget(self.adv_dropdown_container)

        # Button area
        self.adv_btn_container = QWidget()
        self.adv_keys_flow = FlowLayout()
        self.adv_btn_container.setLayout(self.adv_keys_flow)
        self.adv_keys_layout.addWidget(self.adv_btn_container)

        layout.addWidget(self.adv_keys_container)
        layout.addStretch()

        # Cache for matched buttons (used by pagination)
        self._adv_matched_keycodes = []

        # Initial populate
        self._update_advanced_keys("")

    def _expand_search_words(self, words):
        """Expand search words with synonyms for better matching."""
        expanded = list(words)
        for word in words:
            for key, synonyms in self._SEARCH_SYNONYMS.items():
                if word in key.split() or word == key:
                    expanded.extend(synonyms)
                    break
                for syn in synonyms:
                    if word == syn:
                        expanded.append(key)
                        expanded.extend(synonyms)
                        break
        return expanded

    def _on_search_text_changed(self, text):
        """Called on every keystroke - restarts the debounce timer."""
        self._adv_search_timer.start()

    def _on_search_debounced(self):
        """Called after 400ms of no typing - triggers the actual search update."""
        self._adv_current_page = 0
        self._update_advanced_keys(self.adv_search_bar.text())

    def _adv_prev_page(self):
        if self._adv_current_page > 0:
            self._adv_current_page -= 1
            self._update_advanced_keys(self.adv_search_bar.text())

    def _adv_next_page(self):
        self._adv_current_page += 1
        self._update_advanced_keys(self.adv_search_bar.text())

    def _update_advanced_keys(self, search_text):
        """Rebuild advanced keys display based on search filter."""
        # Clear dropdowns
        while self.adv_dropdown_flow.count():
            child = self.adv_dropdown_flow.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        # Clear buttons
        while self.adv_keys_flow.count():
            child = self.adv_keys_flow.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        categories = self._get_dropdown_categories()
        search = search_text.strip().lower()
        words = search.split() if search else []

        PAGE_SIZE = 100
        shown_dropdowns = 0

        def matches_search(haystack):
            """Check if ALL original search words match (using expanded synonyms)."""
            if not words:
                return True
            h = haystack.lower()
            for word in words:
                # Check the word itself or any of its synonyms
                word_matched = word in h
                if not word_matched:
                    for key, synonyms in self._SEARCH_SYNONYMS.items():
                        if word in key.split() or word == key:
                            word_matched = any(s in h for s in synonyms) or key in h
                            break
                        if word in synonyms:
                            word_matched = any(s in h for s in synonyms) or key in h
                            break
                if not word_matched:
                    return False
            return True

        # Show matching categories (dropdown / value_input / cc_xy / range)
        for cat_name, kc_list, search_terms, widget_type, val_template in categories:
            cat_haystack = cat_name + " " + search_terms
            if not matches_search(cat_haystack):
                continue

            shown_dropdowns += 1

            if widget_type == "value_input":
                wrapper = QWidget()
                wl = QVBoxLayout(wrapper)
                wl.setSpacing(2)
                wl.setContentsMargins(4, 4, 4, 4)
                btn = QPushButton(cat_name)
                btn.setFixedSize(200, 36)
                tmpl = val_template
                lo, hi = (1, 100) if tmpl == "QB_MASTER_{}" else (0, 127)
                def make_handler(t=tmpl, lo=lo, hi=hi):
                    def handler(value):
                        if value and value.isdigit() and lo <= int(value) <= hi:
                            self.keycode_changed.emit(t.format(int(value)))
                    return handler
                btn.clicked.connect(lambda _, n=cat_name, h=make_handler(), lo=lo, hi=hi: show_value_dialog(
                    self, "Set Value for {}".format(n), lo, hi, h))
                wl.addWidget(btn)
                self.adv_dropdown_flow.addWidget(wrapper)

            elif widget_type == "cc_xy":
                wrapper = QWidget()
                wl = QVBoxLayout(wrapper)
                wl.setSpacing(2)
                wl.setContentsMargins(4, 4, 4, 4)
                btn = QPushButton(cat_name)
                btn.setFixedSize(200, 36)
                btn.clicked.connect(self.open_cc_xy_dialog)
                wl.addWidget(btn)
                self.adv_dropdown_flow.addWidget(wrapper)

            elif widget_type == "range":
                wrapper = QWidget()
                wl = QVBoxLayout(wrapper)
                wl.setSpacing(2)
                wl.setContentsMargins(4, 4, 4, 4)
                btn = QPushButton(cat_name)
                btn.setFixedSize(200, 36)
                def range_handler(min_val, max_val):
                    if min_val and max_val and min_val.isdigit() and max_val.isdigit():
                        mn, mx = int(min_val), int(max_val)
                        if 1 <= mn <= 127 and 1 <= mx <= 127 and mn <= mx:
                            self.keycode_changed.emit("HE_VEL_RANGE_{}_{}".format(mn, mx))
                btn.clicked.connect(lambda: self.open_he_range_dialog(range_handler))
                wl.addWidget(btn)
                self.adv_dropdown_flow.addWidget(wrapper)

            elif widget_type == "dropdown" and kc_list:
                wrapper = QWidget()
                wl = QVBoxLayout(wrapper)
                wl.setSpacing(2)
                wl.setContentsMargins(4, 4, 4, 4)
                label = QLabel(cat_name)
                label.setStyleSheet("font-weight: bold; font-size: 8pt;")
                dropdown = CenteredComboBox()
                dropdown.setFixedWidth(220)
                dropdown.setFixedHeight(28)
                dropdown.addItem("Select...")
                dropdown.model().item(0).setEnabled(False)
                for kc in kc_list:
                    dropdown.addItem(Keycode.label(kc.qmk_id), kc.qmk_id)
                def on_change(idx, dd=dropdown):
                    qmk_id = dd.itemData(idx)
                    if qmk_id:
                        self.keycode_changed.emit(qmk_id)
                    dd.setCurrentIndex(0)
                dropdown.currentIndexChanged.connect(on_change)
                wl.addWidget(label)
                wl.addWidget(dropdown)
                self.adv_dropdown_flow.addWidget(wrapper)

        # Build set of qmk_ids force-included from matched tab sections
        tab_force_ids = set()
        if words:
            tab_map = self._get_tab_section_map()
            full_search = " ".join(words)
            for term, id_set in tab_map.items():
                # Match if the full search equals a term, or any single word matches a term
                if full_search == term or term in words:
                    tab_force_ids.update(id_set)
                # Also match synonyms: e.g. "chan" → channel tab
                for word in words:
                    for key, synonyms in self._SEARCH_SYNONYMS.items():
                        if word == key or word in key.split():
                            if key == term or term in synonyms:
                                tab_force_ids.update(id_set)
                        elif word in synonyms:
                            if key == term or term in synonyms:
                                tab_force_ids.update(id_set)

        # Build list of ALL matching keycodes (for pagination)
        self._adv_matched_keycodes = []
        seen_ids = set()
        for keycode in KEYCODES:
            if not keycode.qmk_id or keycode.qmk_id == "KC_NO":
                continue
            if keycode.qmk_id in seen_ids:
                continue

            # Force-include if keycode belongs to a matched tab section
            if keycode.qmk_id in tab_force_ids:
                self._adv_matched_keycodes.append(keycode)
                seen_ids.add(keycode.qmk_id)
                continue

            # Normal search: skip dropdown category keycodes
            if keycode.qmk_id in self._adv_dropdown_ids:
                continue
            haystack = keycode.qmk_id + " " + (keycode.label or "").replace("\n", " ") + " " + (keycode.tooltip or "")
            if matches_search(haystack):
                self._adv_matched_keycodes.append(keycode)
                seen_ids.add(keycode.qmk_id)

        total_buttons = len(self._adv_matched_keycodes)
        total_pages = max(1, (total_buttons + PAGE_SIZE - 1) // PAGE_SIZE)

        # Clamp page
        if self._adv_current_page >= total_pages:
            self._adv_current_page = total_pages - 1
        if self._adv_current_page < 0:
            self._adv_current_page = 0

        # Show current page of buttons
        start = self._adv_current_page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total_buttons)
        for keycode in self._adv_matched_keycodes[start:end]:
            btn = SquareButton()
            btn.setRelSize(KEYCODE_BTN_RATIO)
            btn.setText(keycode.label if keycode.label else keycode.qmk_id)
            btn.setToolTip("{}\n{}".format(keycode.qmk_id, keycode.tooltip or ""))
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode
            self.adv_keys_flow.addWidget(btn)

        # Update count label
        parts = []
        if shown_dropdowns:
            parts.append("{} dropdown{}".format(shown_dropdowns, "s" if shown_dropdowns != 1 else ""))
        if total_buttons > 0:
            if total_buttons > PAGE_SIZE:
                parts.append("{}-{} of {} buttons".format(start + 1, end, total_buttons))
            else:
                parts.append("{} button{}".format(total_buttons, "s" if total_buttons != 1 else ""))
        if search:
            self.adv_count_label.setText("Showing " + ", ".join(parts) if parts else "No results")
        else:
            self.adv_count_label.setText(("Showing " + ", ".join(parts) + " - type to search") if parts else "Type to search")

        # Show/hide pagination controls
        if total_pages > 1:
            self.adv_prev_btn.setVisible(self._adv_current_page > 0)
            self.adv_next_btn.setVisible(self._adv_current_page < total_pages - 1)
            self.adv_page_label.setText("Page {} of {}".format(self._adv_current_page + 1, total_pages))
            self.adv_page_label.show()
        else:
            self.adv_prev_btn.hide()
            self.adv_next_btn.hide()
            self.adv_page_label.setText("")

    def populate_channel_section(self):
        """Populate the Channel Options section with a single row of dropdowns."""
        layout = self.section_layouts["Show\nChannel\nOptions"]

        row_layout = QHBoxLayout()
        row_layout.addStretch(1)  # Left spacer

        # Create and add dropdowns with fixed width of 200 pixels
        self.add_header_dropdown("MIDI Channel", self.channel_options, row_layout, 200)
        self.add_header_dropdown("Temporary MIDI Channel", self.channel_oneshot, row_layout, 200)
        self.add_header_dropdown("Hold MIDI Channel", self.channel_hold, row_layout, 200)
        self.add_header_dropdown("Multi Channel", KEYCODES_MULTICHANNEL, row_layout, 200)

        row_layout.addStretch(1)  # Right spacer
        layout.addLayout(row_layout)
        layout.addStretch()

    def populate_cc_velocity_section(self):
        """Populate the CC Options section with three rows of buttons/dropdowns."""
        layout = self.section_layouts["Show\nCC Options"]

        # First row
        row1_layout = QHBoxLayout()
        row1_layout.addStretch(1)  # Left spacer

        # Add CC Value, CC On/Off, CC Up, and CC Down buttons
        self.add_cc_x_y_menu(row1_layout, 200)
        self.add_value_button("CC On/Off", self.smartchord_CC_toggle, row1_layout, 200)
        self.add_value_button("CC Up", self.CCup, row1_layout, 200)
        self.add_value_button("CC Down", self.CCdown, row1_layout, 200)

        row1_layout.addStretch(1)  # Right spacer
        layout.addLayout(row1_layout)

        # Spacer between rows
        row_spacer1 = QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Fixed)
        layout.addItem(row_spacer1)

        # Second row
        row2_layout = QHBoxLayout()
        row2_layout.addStretch(1)  # Left spacer

        # Add Touch Dial CC and CC Increment buttons/dropdowns
        self.add_value_button("Touch Dial CC", self.CCencoder, row2_layout, 200)
        self.add_value_button("Dynamic CC", None, row2_layout, 200)
        self.add_header_dropdown("CC Increment", self.cc_multiplier_options, row2_layout, 200)

        row2_layout.addStretch(1)  # Right spacer
        layout.addLayout(row2_layout)

        # Spacer between rows
        row_spacer2 = QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Fixed)
        layout.addItem(row_spacer2)

        # Third row
        row3_layout = QHBoxLayout()
        row3_layout.addStretch(1)  # Left spacer

        # Add Program Change, Bank LSB, and Bank MSB buttons
        self.add_value_button("Program Change", self.smartchord_program_change, row3_layout, 200)
        self.add_value_button("Bank LSB", self.smartchord_LSB, row3_layout, 200)
        self.add_value_button("Bank MSB", self.smartchord_MSB, row3_layout, 200)

        row3_layout.addStretch(1)  # Right spacer
        layout.addLayout(row3_layout)

        layout.addStretch()

    def populate_transposition_section(self):
        """Populate the Transposition Settings section with a single row of dropdowns."""
        layout = self.section_layouts["Show\nTransposition\nSettings"]

        row_layout = QHBoxLayout()
        row_layout.addStretch(1)  # Left spacer

        # One combined Transpose selector (-64..+64) — replaces the old separate
        # Octave and Key selector dropdowns (Octave/Transpose up-down keys remain
        # in the Up/Down section).
        self.add_header_dropdown("Transpose Selector", self.smartchord_octave_1, row_layout, 200)

        row_layout.addStretch(1)  # Right spacer
        layout.addLayout(row_layout)
        layout.addStretch()

    def populate_keysplit_section(self):
        """Populate the KeySplit Options section with dropdowns and buttons."""
        # Add buttons to the grid (grid was already created and added to container in __init__)
        row = 0
        col = 0
        max_cols = 8

        for keycode in self.inversion_keycodes2:
            btn = SquareButton()
            btn.setFixedSize(55, 55)
            btn.setText(Keycode.label(keycode.qmk_id))
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode

            self.keysplit_grid.addWidget(btn, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        # Add KeySplit modifier buttons below the grid
        modifiers_layout = QHBoxLayout()
        modifiers_layout.addStretch(1)

        split_buttons = [
            ("Enable\nChannel\nKeySplit", "KS_TOGGLE"),
            ("Enable\nVelocity\nKeySplit", "KS_VELOCITY_TOGGLE"),
            ("Enable\nTranspose\nKeySplit", "KS_TRANSPOSE_TOGGLE")
        ]

        for text, code in split_buttons:
            btn = QPushButton(text)
            btn.setFixedSize(60, 60)
            btn.setStyleSheet("""
                QPushButton {
                    background: palette(button);
                    border: 1px solid palette(mid);
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background: palette(light);
                }
                QPushButton:pressed {
                    background: palette(highlight);
                    color: palette(highlighted-text);
                }
            """)
            btn.clicked.connect(lambda _, k=code: self.keycode_changed.emit(k))
            modifiers_layout.addWidget(btn)

        modifiers_layout.addStretch(1)

        # Add modifiers layout to the keysplit section layout
        if hasattr(self, 'keysplit_h_layout'):
            # Create a vertical layout to hold both grid and modifiers
            keysplit_section_layout = self.section_layouts.get("Show\nKeySplit\nOptions")
            if keysplit_section_layout:
                # keysplit_section_layout is the keysplit_h_layout from __init__
                # We need to add the modifiers below it
                # Since we can't easily restructure, add a wrapper
                pass

        # Since the keysplit_h_layout is already set, we need to add the modifiers after the grid
        # Add a spacer and then the modifiers row
        self.keysplit_grid.addItem(QSpacerItem(0, 20, QSizePolicy.Minimum, QSizePolicy.Fixed), row+1, 0, 1, max_cols)

        # Create container for modifier buttons and add to grid
        modifiers_widget = QWidget()
        modifiers_widget.setLayout(modifiers_layout)
        self.keysplit_grid.addWidget(modifiers_widget, row+2, 0, 1, max_cols)

    def populate_advanced_section(self):
        """Populate the Advanced MIDI Options section with buttons."""
        # Clear existing buttons
        clear_layout_widgets(self.advanced_grid)

        # Add buttons in a grid layout
        row = 0
        col = 0
        max_cols = 8

        for keycode in self.inversion_keycodes:
            btn = SquareButton()
            btn.setFixedSize(55, 55)
            btn.setText(Keycode.label(keycode.qmk_id))
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode

            self.advanced_grid.addWidget(btn, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def populate_velocity_section(self):
        """Populate the Velocity Options section with HE velocity controls."""
        layout = self.section_layouts["Show\nVelocity\nOptions"]

        # First row - Velocity Up/Down buttons + Velocity Increment dropdown
        row_layout = QHBoxLayout()
        row_layout.addStretch(1)  # Left spacer

        # Velocity Up button
        vel_up_kc = Keycode.find("MI_VELOCITY_UP")
        if vel_up_kc:
            btn_up = SquareButton()
            btn_up.setFixedSize(70, 50)
            btn_up.setText("Velocity\n▲")
            btn_up.clicked.connect(lambda _, k="MI_VELOCITY_UP": self.keycode_changed.emit(k))
            btn_up.keycode = vel_up_kc
            row_layout.addWidget(btn_up)
            self.buttons["MI_VELOCITY_UP"] = btn_up

        # Velocity Down button
        vel_down_kc = Keycode.find("MI_VELOCITY_DOWN")
        if vel_down_kc:
            btn_down = SquareButton()
            btn_down.setFixedSize(70, 50)
            btn_down.setText("Velocity\n▼")
            btn_down.clicked.connect(lambda _, k="MI_VELOCITY_DOWN": self.keycode_changed.emit(k))
            btn_down.keycode = vel_down_kc
            row_layout.addWidget(btn_down)
            self.buttons["MI_VELOCITY_DOWN"] = btn_down

        # Velocity Increment dropdown
        self.add_header_dropdown("Velocity Increment", self.velocity_multiplier_options, row_layout, 200)

        row_layout.addStretch(1)  # Right spacer
        layout.addLayout(row_layout)

        # Second row - HE Velocity controls (replaces fixed velocity and shuffle)
        he_row_layout = QHBoxLayout()
        he_row_layout.addStretch(1)  # Left spacer

        # HE Velocity Range button (replaces fixed velocity)
        self.add_he_velocity_range_button(he_row_layout, 200)

        # Playing Style dropdown (all 29: 5 classic + 14 new factory + 10 user)
        # Hold loop modifier + select to target a specific loop, or overdub modifier for overdub
        self.add_header_dropdown("Articulation", KEYCODES_HE_VELOCITY_CURVE, he_row_layout, 200)

        he_row_layout.addStretch(1)  # Right spacer
        layout.addLayout(he_row_layout)

        layout.addStretch()

    def populate_inout_section(self):
        """Populate the In/Out Options section with MIDI routing and override toggles."""
        layout = self.section_layouts["Show\nIn/Out\nOptions"]

        # Section 1: MIDI Routing Controls
        routing_label = QLabel("MIDI Routing")
        routing_label.setStyleSheet("font-weight: bold; font-size: 10pt; margin-top: 5px;")
        layout.addWidget(routing_label)

        routing_row_layout = QHBoxLayout()
        routing_row_layout.addStretch(1)

        # MIDI routing keycodes from KEYCODES_MIDI_INOUT
        routing_keycodes = [kc for kc in self.keycodes_midi_inout if kc.qmk_id in [
            "MIDI_IN_MODE_TOG", "USB_MIDI_MODE_TOG", "MIDI_CLOCK_SRC_TOG"
        ]]
        for keycode in routing_keycodes:
            btn = SquareButton()
            btn.setFixedSize(70, 50)
            btn.setText(Keycode.label(keycode.qmk_id))
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode
            routing_row_layout.addWidget(btn)
            self.buttons[keycode.qmk_id] = btn

        routing_row_layout.addStretch(1)
        layout.addLayout(routing_row_layout)

        # Section 2: Override Toggles
        override_label = QLabel("Override Toggles")
        override_label.setStyleSheet("font-weight: bold; font-size: 10pt; margin-top: 15px;")
        layout.addWidget(override_label)

        override_row_layout = QHBoxLayout()
        override_row_layout.addStretch(1)

        override_keycodes = [kc for kc in self.keycodes_midi_inout if kc.qmk_id in [
            "MI_CH_OVR_TOG", "MI_VEL_OVR_TOG", "MI_TRNS_OVR_TOG"
        ]]
        for keycode in override_keycodes:
            btn = SquareButton()
            btn.setFixedSize(70, 50)
            btn.setText(Keycode.label(keycode.qmk_id))
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode
            override_row_layout.addWidget(btn)
            self.buttons[keycode.qmk_id] = btn

        override_row_layout.addStretch(1)
        layout.addLayout(override_row_layout)

        # Section 3: Additional MIDI Toggles
        additional_label = QLabel("Additional MIDI Toggles")
        additional_label.setStyleSheet("font-weight: bold; font-size: 10pt; margin-top: 15px;")
        layout.addWidget(additional_label)

        additional_row_layout = QHBoxLayout()
        additional_row_layout.addStretch(1)

        additional_keycodes = [kc for kc in self.keycodes_midi_inout if kc.qmk_id in [
            "MI_TRUE_SUS_TOG", "MI_CC_LOOP_TOG"
        ]]
        for keycode in additional_keycodes:
            btn = SquareButton()
            btn.setFixedSize(70, 50)
            btn.setText(Keycode.label(keycode.qmk_id))
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode
            additional_row_layout.addWidget(btn)
            self.buttons[keycode.qmk_id] = btn

        additional_row_layout.addStretch(1)
        layout.addLayout(additional_row_layout)

        layout.addStretch()

    def populate_expression_wheel_section(self):
        """Populate the Touch Dial Options section with buttons and dropdowns."""
        layout = self.section_layouts["Show\nTouch Dial\nOptions"]
        
        # First row: Touch Dial controls
        top_row_layout = QHBoxLayout()
        top_row_layout.addStretch(1)  # Left spacer
        
        # Create grid layout for the Touch Dial buttons
        button_grid = QGridLayout()
        button_grid.setSpacing(4)
        
        # Create Touch Dial CC button
        cc_button = QPushButton("Touch\nDial\nCC")
        cc_button.setFixedSize(80, 80)
        cc_button.clicked.connect(lambda: self.open_value_dialog("Touch Dial CC", self.CCencoder))
        button_grid.addWidget(cc_button, 0, 0)
        
        # Add the three special inversion buttons
        col = 1
        for keycode in self.inversion_keycodesspecial:
            btn = SquareButton()
            btn.setFixedSize(80, 80)
            btn.setText(Keycode.label(keycode.qmk_id))
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode
            button_grid.addWidget(btn, 0, col)
            col += 1
        
        top_row_layout.addLayout(button_grid)
        top_row_layout.addStretch(1)  # Right spacer
        layout.addLayout(top_row_layout)
        
        # Spacer between rows
        spacer = QSpacerItem(0, 20, QSizePolicy.Minimum, QSizePolicy.Fixed)
        layout.addItem(spacer)
        
        # Second row: Dropdowns
        bottom_row_layout = QHBoxLayout()
        bottom_row_layout.addStretch(1)  # Left spacer
        
        # Add dropdowns with fixed width of 200 pixels
        self.add_header_dropdown("Velocity Increment", self.velocity_multiplier_options, bottom_row_layout, 200)
        self.add_header_dropdown("CC Increment", self.cc_multiplier_options, bottom_row_layout, 200)
        
        bottom_row_layout.addStretch(1)  # Right spacer
        layout.addLayout(bottom_row_layout)
        
        layout.addStretch()

    def show_section(self, section_name):
        """Show the specified section and update tab button states"""
        # Hide all section widgets
        for widget in self.section_widgets.values():
            widget.hide()

        # Uncheck all tab buttons
        for btn in self.side_tab_buttons.values():
            btn.setChecked(False)

        # Show the selected section widget and check its tab button
        if section_name in self.section_widgets:
            self.section_widgets[section_name].show()
            if section_name in self.side_tab_buttons:
                self.side_tab_buttons[section_name].setChecked(True)

    def add_cc_x_y_menu(self, layout, width=None):
        button = QPushButton("CC Value")
        button.setFixedHeight(40)
        if width:
            button.setFixedWidth(width)
        button.clicked.connect(self.open_cc_xy_dialog)
        layout.addWidget(button)

    def open_cc_xy_dialog(self):
        def handle_cc_values(x, y):
            self.keycode_changed.emit(f"MI_CC_{x}_{y}")

        try:
            import emscripten
            dialog = AsyncCCDialog(self, handle_cc_values)
            dialog.show()
        except ImportError:
            dialog = AsyncCCDialog(self, handle_cc_values)
            dialog.exec_()

    def add_value_button(self, label_text, keycode_set, layout, width=None):
        """Create a button that opens a dialog to input a value for the corresponding keycode."""
        button = QPushButton(label_text)
        button.setFixedHeight(40)
        if width:
            button.setFixedWidth(width)
        
        def handle_value(value):
            if value and value.isdigit() and 0 <= int(value) <= 127:
                keycode_map = {
                    "CC On/Off": f"MI_CC_{value}_TOG",
                    "CC Up": f"MI_CC_{value}_UP",
                    "CC Down": f"MI_CC_{value}_DWN",
                    "Dynamic CC": f"MI_MOD_PRESS_{value}",
                    "Touch Dial CC": f"MI_CCENCODER_{value}",
                    "Program Change": f"MI_PROG_{value}",
                    "Bank LSB": f"MI_BANK_LSB_{value}",
                    "Bank MSB": f"MI_BANK_MSB_{value}",
                    "Set Velocity": f"MI_VELOCITY_{value}",
                    "Set Fixed Velocity": f"MI_VELOCITY_{value}",
                    "Key Switch\nVelocity": f"MI_VELOCITY2_{value}",
                    "Triple Switch\nVelocity": f"MI_VELOCITY3_{value}"
                }
                
                if label_text in keycode_map:
                    self.keycode_changed.emit(keycode_map[label_text])
        
        button.clicked.connect(lambda: show_value_dialog(
            self,
            f"Set Value for {label_text}",
            0,
            127,
            handle_value
        ))
        layout.addWidget(button)

    def add_value_button2(self, label_text, keycode_set, layout, width=None):
        """Create a button for keysplit section with specific height."""
        button = QPushButton(label_text)
        button.setFixedHeight(60)
        if width:
            button.setFixedWidth(width)
        
        def handle_value(value):
            if value and value.isdigit() and 0 <= int(value) <= 127:
                keycode_map = {
                    "Key Switch\nVelocity": f"MI_VELOCITY2_{value}",
                    "Triple Switch\nVelocity": f"MI_VELOCITY3_{value}"
                }
                
                if label_text in keycode_map:
                    self.keycode_changed.emit(keycode_map[label_text])
        
        button.clicked.connect(lambda: show_value_dialog(
            self,
            f"Set Value for {label_text}",
            0,
            127,
            handle_value
        ))
        layout.addWidget(button)

    def add_he_velocity_range_button(self, layout, width=None):
        """Create a button that opens a dialog to set HE velocity min and max range."""
        button = QPushButton("Set Dynamic Velocity Range")
        button.setFixedHeight(40)
        if width:
            button.setFixedWidth(width)

        def handle_range_values(min_val, max_val):
            if min_val and max_val and min_val.isdigit() and max_val.isdigit():
                min_int = int(min_val)
                max_int = int(max_val)
                if 1 <= min_int <= 127 and 1 <= max_int <= 127 and min_int <= max_int:
                    self.keycode_changed.emit(f"HE_VEL_RANGE_{min_int}_{max_int}")

        button.clicked.connect(lambda: self.open_he_range_dialog(handle_range_values))
        layout.addWidget(button)

    def open_he_range_dialog(self, callback):
        """Open a dialog to input HE velocity min and max values."""
        try:
            import emscripten
            # Async dialog for web version
            dialog = AsyncHERangeDialog(self, callback)
            dialog.show()
        except ImportError:
            # Sync dialog for desktop version
            dialog = HERangeDialog(self, callback)
            dialog.exec_()

    def open_value_dialog(self, label, keycode_set):
        """Open a dialog to input a value between 0 and 127."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Set Value for {label}")
        dialog.setFixedSize(300, 150)

        layout = QVBoxLayout(dialog)
        label_widget = QLabel(f"Enter value for {label} (0-127):")
        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("Enter a number between 0 and 127")
        self.value_input.textChanged.connect(self.validate_value_input)

        layout.addWidget(label_widget)
        layout.addWidget(self.value_input)

        confirm_button = QPushButton("Confirm")
        confirm_button.clicked.connect(lambda: self.confirm_value(dialog, label, keycode_set))
        layout.addWidget(confirm_button)

        dialog.exec_()

    def confirm_value(self, dialog, label, keycode_set):
        """Confirm the value input and emit the corresponding keycode."""
        value = self.value_input.text()
        if value.isdigit() and 0 <= int(value) <= 127:
            keycode_map = {
                "CC On/Off": f"MI_CC_{value}_TOG",
                "CC Up": f"MI_CC_{value}_UP",
                "CC Down": f"MI_CC_{value}_DWN",
                "Touch Dial CC": f"MI_CCENCODER_{value}",
                "Program Change": f"MI_PROG_{value}",
                "Bank LSB": f"MI_BANK_LSB_{value}",
                "Bank MSB": f"MI_BANK_MSB_{value}",
                "Set Velocity": f"MI_VELOCITY_{value}",
                "Key Switch\nVelocity": f"MI_VELOCITY2_{value}",
                "TS Velocity": f"MI_VELOCITY3_{value}"
            }
        
            # Construct the keycode using the label as a key
            if label in keycode_map:
                selected_keycode = keycode_map[label]
                self.keycode_changed.emit(selected_keycode)
                dialog.accept()

    def validate_value_input(self, text):
        if text and (not text.isdigit() or not (0 <= int(text) <= 127)):
            self.value_input.clear()

    def add_header_dropdown(self, header_text, keycodes, layout, width=None):
        """Add a dropdown with optional fixed width."""
        vbox = QVBoxLayout()

        # Create dropdown
        dropdown = CenteredComboBox()
        dropdown.setFixedHeight(40)
        if width:
            dropdown.setFixedWidth(width)

        # Add a placeholder item as the first item
        dropdown.addItem(f"{header_text}")

        # Add the keycodes as options
        for keycode in keycodes:
            dropdown.addItem(Keycode.label(keycode.qmk_id), keycode.qmk_id)

        # Prevent the first item from being selected again
        dropdown.model().item(0).setEnabled(False)

        dropdown.currentIndexChanged.connect(self.on_selection_change)
        dropdown.currentIndexChanged.connect(lambda: self.reset_dropdown(dropdown, header_text))
        vbox.addWidget(dropdown)

        # Add the vertical box to the provided layout
        layout.addLayout(vbox)
        
    def add_header_dropdown2(self, header_text, keycodes, layout, width=None):
        """Add a dropdown for keysplit section with specific height."""
        vbox = QVBoxLayout()

        # Create dropdown
        dropdown = CenteredComboBox()
        dropdown.setFixedHeight(60)
        if width:
            dropdown.setFixedWidth(width)

        # Add a placeholder item as the first item
        dropdown.addItem(f"{header_text}")

        # Add the keycodes as options
        for keycode in keycodes:
            dropdown.addItem(Keycode.label(keycode.qmk_id), keycode.qmk_id)

        # Prevent the first item from being selected again
        dropdown.model().item(0).setEnabled(False)

        dropdown.currentIndexChanged.connect(self.on_selection_change)
        dropdown.currentIndexChanged.connect(lambda: self.reset_dropdown(dropdown, header_text))
        vbox.addWidget(dropdown)

        # Add the vertical box to the provided layout
        layout.addLayout(vbox)
        
    def reset_dropdown(self, dropdown, header_text):
        """Reset the dropdown to show default text while storing the selected value."""
        selected_index = dropdown.currentIndex()

        if selected_index > 0:
            selected_value = dropdown.itemData(selected_index)

        # Reset the visible text to the default
        dropdown.setCurrentIndex(0)
    
    def recreate_buttons(self, keycode_filter=None):
        """Update to include both advanced and keysplit section buttons."""
        # Clear and recreate the advanced section
        clear_layout_widgets(self.advanced_grid)

        # Clear and recreate the keysplit section
        clear_layout_widgets(self.keysplit_grid)

        # Repopulate advanced section
        row = 0
        col = 0
        max_cols = 8

        for keycode in self.inversion_keycodes:
            if keycode_filter is None or keycode_filter(keycode.qmk_id):
                btn = SquareButton()
                btn.setFixedSize(55, 55)
                btn.setText(Keycode.label(keycode.qmk_id))
                btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = keycode
                
                self.advanced_grid.addWidget(btn, row, col)
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1

        # Repopulate keysplit section
        row = 0
        col = 0

        for keycode in self.inversion_keycodes2:
            if keycode_filter is None or keycode_filter(keycode.qmk_id):
                btn = SquareButton()
                btn.setFixedSize(55, 55)
                btn.setText(Keycode.label(keycode.qmk_id))
                btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = keycode
                
                self.keysplit_grid.addWidget(btn, row, col)
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1

        # Recreate any external section tabs (DAW / DrumLIVE / Arp / Seq / Delay)
        for _ext_widget in getattr(self, 'external_widgets', {}).values():
            _ext_widget.recreate_buttons(keycode_filter if keycode_filter is not None else keycode_filter_any)

    def relabel_buttons(self):
        # Relabel buttons in the advanced section
        for widget in iter_layout_widgets(self.advanced_grid):
            if isinstance(widget, SquareButton) and hasattr(widget, 'keycode'):
                widget.setText(Keycode.label(widget.keycode.qmk_id))
                
        # Relabel buttons in the keysplit section
        for widget in iter_layout_widgets(self.keysplit_grid):
            if isinstance(widget, SquareButton) and hasattr(widget, 'keycode'):
                widget.setText(Keycode.label(widget.keycode.qmk_id))

        for _ext_widget in getattr(self, 'external_widgets', {}).values():
            _ext_widget.relabel_buttons()

    def has_buttons(self):
        return True

    def on_selection_change(self, index):
        selected_qmk_id = self.sender().itemData(index)
        if selected_qmk_id:
            self.keycode_changed.emit(selected_qmk_id)
        
class ModernButton(QPushButton):
    def __init__(self, text, color="#4a90e2"):
        super().__init__(text)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: none;
                border-radius: 6px;
                color: white;
                padding: 10px;
                font-weight: bold;
                min-height: 40px;
            }}
            QPushButton:hover {{
                background-color: {self.lighten_color(color, 20)};
            }}
            QPushButton:pressed {{
                background-color: {self.darken_color(color, 20)};
            }}
        """)
        
    def lighten_color(self, color, amount):
        # Convert hex to RGB and lighten
        c = color.lstrip('#')
        rgb = tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
        rgb = tuple(min(255, x + amount) for x in rgb)
        return '#{:02x}{:02x}{:02x}'.format(*rgb)
        
    def darken_color(self, color, amount):
        c = color.lstrip('#')
        rgb = tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
        rgb = tuple(max(0, x - amount) for x in rgb)
        return '#{:02x}{:02x}{:02x}'.format(*rgb)

import math

class LoopTab(QScrollArea):
    """Loop Control tab with simplified layout"""
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, loop_keycodes):
        super().__init__(parent)
        self.label = label
        self.loop_keycodes = loop_keycodes
        self.current_keycode_filter = None

        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setSpacing(20)
        self.main_layout.setContentsMargins(20, 15, 20, 15)
        self.main_layout.setAlignment(Qt.AlignTop)

        # Create initial buttons
        self.recreate_buttons(keycode_filter_any)

        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def recreate_buttons(self, keycode_filter):
        self.current_keycode_filter = keycode_filter

        # Clear existing layout
        while self.main_layout.count():
            child = self.main_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        def _make_loop_btn(keycode):
            btn = SquareButton()
            btn.setRelSize(KEYCODE_BTN_RATIO)
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode
            btn.setText(keycode.label)
            btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
            return btn

        # Row 1: Basic Loop Controls (loop keys + mute + overdub)
        basic_group = QGroupBox("Basic Loop Controls")
        basic_layout = FlowLayout()
        for keycode in self.loop_keycodes:
            if keycode_filter(keycode) and keycode.qmk_id in ["DM_MACRO_1", "DM_MACRO_2", "DM_MACRO_3", "DM_MACRO_4", "DM_REC5", "DM_REC6", "DM_REC7", "DM_REC8", "DM_NEXT_LOOP_REC", "DM_MUTE", "DM_OVERDUB", "OCT_DBL_TOGGLE"]:
                btn = SquareButton()
                btn.setRelSize(KEYCODE_BTN_RATIO)
                btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = keycode
                btn.setText(keycode.label)
                btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
                basic_layout.addWidget(btn)
        basic_group.setLayout(basic_layout)
        self.main_layout.addWidget(basic_group)

        # Extra Loop Buttons section - combines overdub loop, mute loop, overdub mute, and octave doubler
        extra_loop_group = QGroupBox("Extra Loop Buttons")
        extra_loop_layout = FlowLayout()
        # Order: Overdub Loop, Mute Loop, Overdub Mute, Octave Doubler
        button_order = []
        # Overdub Loop buttons
        modifier_ids = ["DM_LOOP_MOD_1", "DM_LOOP_MOD_2", "DM_LOOP_MOD_3", "DM_LOOP_MOD_4", "DM_SPEED_MOD", "DM_SLOW_MOD"]
        for keycode in self.loop_keycodes:
            if keycode_filter(keycode) and keycode.qmk_id in modifier_ids:
                extra_loop_layout.addWidget(_make_loop_btn(keycode))
        # Advanced Overdub, Sync Mode, Sample Mode
        mode_ids = ["DM_ADVANCED_OVERDUB", "DM_UNSYNC", "DM_SAMPLE", "LOOP_QUANTIZE", "LOOP_BPM_DOUBLE"]
        for keycode in self.loop_keycodes:
            if keycode_filter(keycode) and keycode.qmk_id in mode_ids:
                extra_loop_layout.addWidget(_make_loop_btn(keycode))
        # BeatSkip buttons
        for keycode in self.loop_keycodes:
            if keycode_filter(keycode) and keycode.qmk_id.startswith("DM_SKIP_"):
                extra_loop_layout.addWidget(_make_loop_btn(keycode))
        # Extra loop buttons: Overdub loops, Mute loops, Overdub Mute, Octave Doublers
        for keycode in self.loop_keycodes:
            if keycode.qmk_id.startswith("DM_OCT_"):
                button_order.append(keycode)
        # Add all buttons to layout
        for keycode in button_order:
            if keycode_filter(keycode):
                qid = keycode.qmk_id
                is_extra = (
                    (qid.startswith("DM_OVERDUB_") and not qid.startswith("DM_OVERDUB_MUTE_") and qid != "DM_OVERDUB") or
                    (qid.startswith("DM_MUTE_") and qid != "DM_MUTE") or
                    qid.startswith("DM_OVERDUB_MUTE_") or
                    (qid.startswith("DM_OCT_") and qid != "DM_OCT_MOD") or
                    qid in ["DM_EDIT_MOD", "DM_COPY"]
                )
                if is_extra:
                    extra_loop_layout.addWidget(_make_loop_btn(keycode))
        extra_loop_group.setLayout(extra_loop_layout)
        self.main_layout.addWidget(extra_loop_group)

        # Save buttons
        modifier_group = QGroupBox("Modifiers")
        modifier_layout = FlowLayout()
        for keycode in self.loop_keycodes:
            if keycode_filter(keycode) and keycode.qmk_id in ["DM_LOOP_MOD_1", "DM_LOOP_MOD_2", "DM_LOOP_MOD_3", "DM_LOOP_MOD_4", "DM_LOOP_MOD_5", "DM_LOOP_MOD_6", "DM_LOOP_MOD_7", "DM_LOOP_MOD_8", "OCT_DBL_TOGGLE", "DM_SPEED_MOD", "DM_SLOW_MOD", "DM_MUTE", "DM_OVERDUB"]:
                btn = SquareButton()
                btn.setRelSize(KEYCODE_BTN_RATIO)
                btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = keycode
                btn.setText(keycode.label)
                btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
                modifier_layout.addWidget(btn)
        modifier_group.setLayout(modifier_layout)
        self.main_layout.addWidget(modifier_group)

        # BeatSkip section
        beatskip_group = QGroupBox("BeatSkip")
        beatskip_layout = FlowLayout()
        for keycode in self.loop_keycodes:
            if keycode_filter(keycode) and keycode.qmk_id.startswith("DM_SKIP_"):
                btn = SquareButton()
                btn.setRelSize(KEYCODE_BTN_RATIO)
                btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = keycode
                btn.setText(keycode.label)
                btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
                beatskip_layout.addWidget(btn)
        beatskip_group.setLayout(beatskip_layout)
        self.main_layout.addWidget(beatskip_group)

        # Speed Controls section - only individual speed/slow buttons and reset
        speed_group = QGroupBox("Speed Controls")
        speed_layout = FlowLayout()
        for keycode in self.loop_keycodes:
            if keycode_filter(keycode) and (keycode.qmk_id.startswith("DM_SPEED_") or keycode.qmk_id.startswith("DM_SLOW_") or keycode.qmk_id == "DM_RESET_SPEED") and keycode.qmk_id not in ["DM_SPEED_MOD", "DM_SLOW_MOD"]:
                btn = SquareButton()
                btn.setRelSize(KEYCODE_BTN_RATIO)
                btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = keycode
                btn.setText(keycode.label)
                btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
                speed_layout.addWidget(btn)
        speed_group.setLayout(speed_layout)
        self.main_layout.addWidget(speed_group)

        # Row 3: Navigation - play/pause + speed controls + navigation combined
        nav_group = QGroupBox("Navigation")
        nav_layout = FlowLayout()
        # Play/Pause first
        for keycode in self.loop_keycodes:
            if keycode_filter(keycode) and keycode.qmk_id == "DM_PLAY_PAUSE":
                nav_layout.addWidget(_make_loop_btn(keycode))
        # Speed controls (individual speed/slow buttons and reset, not modifiers)
        for keycode in self.loop_keycodes:
            if keycode_filter(keycode):
                qid = keycode.qmk_id
                is_speed = ((qid.startswith("DM_SPEED_") or qid.startswith("DM_SLOW_") or qid == "DM_RESET_SPEED")
                           and qid not in ["DM_SPEED_MOD", "DM_SLOW_MOD"])
                if is_speed:
                    nav_layout.addWidget(_make_loop_btn(keycode))
        # Navigation buttons
        for keycode in self.loop_keycodes:
            if keycode_filter(keycode) and keycode.qmk_id.startswith("DM_NAV_"):
                nav_layout.addWidget(_make_loop_btn(keycode))
        nav_group.setLayout(nav_layout)
        self.main_layout.addWidget(nav_group)

        self.main_layout.addStretch(1)

    def has_buttons(self):
        return len(self.loop_keycodes) > 0

    def relabel_buttons(self):
        pass  # Implement if needed


class DrumLIVETab(QScrollArea):
    """DrumLIVE — live drum note filter keycode palette.

    Mirrors the Loop Control / Ear Training subtabs: a palette of keycodes the
    user assigns to keys. The device holds the live filter state; these keycodes
    toggle it (Mute / Quiet -50% / Loud +50% / Solo) per category or per voice,
    plus a Menu key to open the on-device picker and a Clear key.
    """
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, drumlive_keycodes):
        super().__init__(parent)
        self.label = label
        self.drumlive_keycodes = drumlive_keycodes
        self.current_keycode_filter = None

        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setSpacing(20)
        self.main_layout.setContentsMargins(20, 15, 20, 15)
        self.main_layout.setAlignment(Qt.AlignTop)

        self.recreate_buttons(keycode_filter_any)

        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def _make_btn(self, keycode):
        btn = SquareButton()
        btn.setRelSize(KEYCODE_BTN_RATIO)
        btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
        btn.keycode = keycode
        btn.setText(keycode.label)
        btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
        return btn

    def _add_group(self, title, predicate, keycode_filter):
        group = QGroupBox(title)
        layout = FlowLayout()
        added = False
        for keycode in self.drumlive_keycodes:
            if keycode_filter(keycode) and predicate(keycode.qmk_id):
                layout.addWidget(self._make_btn(keycode))
                added = True
        group.setLayout(layout)
        if added:
            self.main_layout.addWidget(group)

    def recreate_buttons(self, keycode_filter):
        self.current_keycode_filter = keycode_filter
        while self.main_layout.count():
            child = self.main_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Menu + global On/Off
        self._add_group(
            "DrumLIVE",
            lambda q: q in ("DRUMLIVE_MENU", "DRUMLIVE_RESET", "DRUMLIVE_ALL_OFF"),
            keycode_filter)
        # Category-group filters (Kicks / Snares / Hats / Cymbals / Toms / Perc)
        self._add_group(
            "Category Filters",
            lambda q: q.startswith("DRUMLIVE_CAT_"),
            keycode_filter)
        # Individual drum-voice filters
        self._add_group(
            "Per-Voice Filters",
            lambda q: q.startswith("DRUMLIVE_VOICE_"),
            keycode_filter)

        self.main_layout.addStretch(1)

    def has_buttons(self):
        return len(self.drumlive_keycodes) > 0

    def relabel_buttons(self):
        pass


class LayerTab(QScrollArea):
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, smartchord_DF, smartchord_MO, smartchord_OSL):
        super().__init__(parent)
        self.label = label
        self.smartchord_DF = smartchord_DF
        self.smartchord_MO = smartchord_MO
        self.smartchord_OSL = smartchord_OSL

        self.scroll_content = QWidget(self)
        self.main_layout = QVBoxLayout(self.scroll_content)

        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        # Add a spacer at the top to push everything down by 100 pixels
        top_spacer = QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.main_layout.addItem(top_spacer)

        # Add "Layer Controls" title
        self.lighting_controls_label = QLabel("Layer Selection")
        self.lighting_controls_label.setAlignment(Qt.AlignCenter)
        self.lighting_controls_label.setStyleSheet("font-size: 13px;")
        self.main_layout.addWidget(self.lighting_controls_label)

        # Add another spacer (10px)
        top_spacer2 = QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.main_layout.addItem(top_spacer2)

        # Row 1: Three Layer dropdowns
        self.row1_layout = QHBoxLayout()
        self.row1_layout.addStretch()  # Left spacer

        # Create and add dropdowns with fixed width
        self.default_layer_dropdown = self.create_default_layer_dropdown()
        self.default_layer_dropdown.setFixedWidth(200)
        self.row1_layout.addWidget(self.default_layer_dropdown)

        self.hold_layer_dropdown = self.create_hold_layer_dropdown()
        self.hold_layer_dropdown.setFixedWidth(200)
        self.row1_layout.addWidget(self.hold_layer_dropdown)

        self.oneshot_layer_dropdown = self.create_oneshot_layer_dropdown()
        self.oneshot_layer_dropdown.setFixedWidth(200)
        self.row1_layout.addWidget(self.oneshot_layer_dropdown)

        self.row1_layout.addStretch()  # Right spacer
        self.main_layout.addLayout(self.row1_layout)

        # Spacer to push everything to the top
        self.main_layout.addStretch()

    def create_default_layer_dropdown(self, keycode_filter=None):
        dropdown = CenteredComboBox()
        dropdown.setFixedHeight(40)
        dropdown.addItem("Default Layer")

        for keycode in self.smartchord_DF:
            if keycode_filter is None or keycode_filter(keycode.qmk_id):
                label = Keycode.label(keycode.qmk_id)
                tooltip = Keycode.description(keycode.qmk_id)
                dropdown.addItem(label, keycode.qmk_id)
                item = dropdown.model().item(dropdown.count() - 1)
                item.setToolTip(tooltip)

        dropdown.model().item(0).setEnabled(False)
        dropdown.currentIndexChanged.connect(self.on_selection_change)
        dropdown.currentIndexChanged.connect(lambda _: self.reset_dropdown(dropdown, "Default Layer"))

        return dropdown

    def create_hold_layer_dropdown(self, keycode_filter=None):
        dropdown = CenteredComboBox()
        dropdown.setFixedHeight(40)
        dropdown.addItem("Hold Layer")

        for keycode in self.smartchord_MO:
            if keycode_filter is None or keycode_filter(keycode.qmk_id):
                label = Keycode.label(keycode.qmk_id)
                tooltip = Keycode.description(keycode.qmk_id)
                dropdown.addItem(label, keycode.qmk_id)
                item = dropdown.model().item(dropdown.count() - 1)
                item.setToolTip(tooltip)

        dropdown.model().item(0).setEnabled(False)
        dropdown.currentIndexChanged.connect(self.on_selection_change)
        dropdown.currentIndexChanged.connect(lambda _: self.reset_dropdown(dropdown, "Hold Layer"))

        return dropdown

    def create_oneshot_layer_dropdown(self, keycode_filter=None):
        dropdown = CenteredComboBox()
        dropdown.setFixedHeight(40)
        dropdown.addItem("One Shot Layer")

        for keycode in self.smartchord_OSL:
            if keycode_filter is None or keycode_filter(keycode.qmk_id):
                label = Keycode.label(keycode.qmk_id)
                tooltip = Keycode.description(keycode.qmk_id)
                dropdown.addItem(label, keycode.qmk_id)
                item = dropdown.model().item(dropdown.count() - 1)
                item.setToolTip(tooltip)

        dropdown.model().item(0).setEnabled(False)
        dropdown.currentIndexChanged.connect(self.on_selection_change)
        dropdown.currentIndexChanged.connect(lambda _: self.reset_dropdown(dropdown, "One Shot Layer"))

        return dropdown

    def recreate_buttons(self, keycode_filter=None):
        # Clear and recreate all three dropdowns
        self.row1_layout.removeWidget(self.default_layer_dropdown)
        self.row1_layout.removeWidget(self.hold_layer_dropdown)
        self.row1_layout.removeWidget(self.oneshot_layer_dropdown)

        self.default_layer_dropdown.deleteLater()
        self.hold_layer_dropdown.deleteLater()
        self.oneshot_layer_dropdown.deleteLater()

        self.default_layer_dropdown = self.create_default_layer_dropdown(keycode_filter)
        self.default_layer_dropdown.setFixedWidth(200)
        self.row1_layout.insertWidget(1, self.default_layer_dropdown)

        self.hold_layer_dropdown = self.create_hold_layer_dropdown(keycode_filter)
        self.hold_layer_dropdown.setFixedWidth(200)
        self.row1_layout.insertWidget(2, self.hold_layer_dropdown)

        self.oneshot_layer_dropdown = self.create_oneshot_layer_dropdown(keycode_filter)
        self.oneshot_layer_dropdown.setFixedWidth(200)
        self.row1_layout.insertWidget(3, self.oneshot_layer_dropdown)

    def reset_dropdown(self, dropdown, header_text):
        selected_index = dropdown.currentIndex()
        if selected_index > 0:
            selected_value = dropdown.itemData(selected_index)
        dropdown.setCurrentIndex(0)

    def on_selection_change(self, index):
        selected_qmk_id = self.sender().itemData(index)
        if selected_qmk_id:
            self.keycode_changed.emit(selected_qmk_id)

    def relabel_buttons(self):
        # No buttons to relabel in this simplified version
        pass

    def has_buttons(self):
        return True  # Always has dropdowns

class ScrollableComboBox(CenteredComboBox):
    def showPopup(self):
        popup = self.findChild(QFrame)
        if popup:
            popup.setFixedHeight(300)
            view = popup.findChild(QListView)
            if view:
                view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
                view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                view.verticalScrollBar().setValue(0)
        super().showPopup()
        
class LightingTab(QScrollArea):
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, inversion_keycodes, inversion_keycodes4, smartchord_LSB, smartchord_MSB, smartchord_LSB2):
        super().__init__(parent)
        self.label = label     
        self.inversion_keycodes = inversion_keycodes
        self.inversion_keycodes4 = inversion_keycodes4
        self.smartchord_LSB = smartchord_LSB
        self.smartchord_MSB = smartchord_MSB
        self.smartchord_LSB2 = smartchord_LSB2
        
        # Import QFrame if it's not already imported
        from PyQt5.QtWidgets import QFrame, QListView, QScrollBar

        # Create a widget for the scroll area content
        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)
        
        # Set the scroll area properties
        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        
        # Add a spacer at the top (20px)
        top_spacer1 = QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.main_layout.addItem(top_spacer1)
        
        # Add "Lighting Controls" title
        self.lighting_controls_label = QLabel("Lighting Controls")
        self.lighting_controls_label.setAlignment(Qt.AlignCenter)
        self.lighting_controls_label.setStyleSheet("font-size: 13px;")
        self.main_layout.addWidget(self.lighting_controls_label)
        
        # Add another spacer (10px)
        top_spacer2 = QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.main_layout.addItem(top_spacer2)

        # Row 1: RGB Mode and RGB Color dropdowns
        self.row1_layout = QHBoxLayout()
        self.row1_layout.addStretch()  # Left spacer
        
        # Create and add dropdowns with fixed width
        self.rgb_mode_dropdown = self.create_rgb_mode_dropdown()
        self.rgb_mode_dropdown.setFixedWidth(200)
        self.row1_layout.addWidget(self.rgb_mode_dropdown)
        
        self.rgb_color_dropdown = self.create_rgb_color_dropdown()
        self.rgb_color_dropdown.setFixedWidth(200)
        self.row1_layout.addWidget(self.rgb_color_dropdown)
        
        self.row1_layout.addStretch()  # Right spacer
        self.main_layout.addLayout(self.row1_layout)
        
        # Row 2: Buttons from inversion_keycodes
        self.buttons1_container = QWidget()
        self.buttons1_layout = QGridLayout(self.buttons1_container)
        self.buttons1_layout.setHorizontalSpacing(5)
        self.buttons1_layout.setVerticalSpacing(5)
        
        # Create a horizontal layout for the button container with spacers
        self.centered_buttons1_layout = QHBoxLayout()
        self.centered_buttons1_layout.addStretch()  # Left spacer
        self.centered_buttons1_layout.addWidget(self.buttons1_container)
        self.centered_buttons1_layout.addStretch()  # Right spacer
        
        # Add the centered button layout to the main layout
        self.main_layout.addLayout(self.centered_buttons1_layout)
        
        # Add a small spacer between rows
        row_spacer2 = QSpacerItem(0, 20, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.main_layout.addItem(row_spacer2)
        
        # Add "Layer Lighting Controls" label
        self.layer_lighting_label = QLabel("Layer Lighting Controls")
        self.layer_lighting_label.setAlignment(Qt.AlignCenter)
        self.layer_lighting_label.setStyleSheet("font-size: 13px;")
        self.main_layout.addWidget(self.layer_lighting_label)
        
        # Small spacer after the label - REDUCED from 10 to 2 pixels
        label_spacer = QSpacerItem(0, 2, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.main_layout.addItem(label_spacer)
        
        # Row 3: Record Layer RGB dropdown and buttons from inversion_keycodes4
        self.row3_layout = QHBoxLayout()
        self.row3_layout.addStretch()  # Left spacer
        
        # Add Record Layer RGB dropdown
        self.rgb_layer_dropdown = self.create_rgb_layer_dropdown()
        self.rgb_layer_dropdown.setFixedWidth(200)
        self.row3_layout.addWidget(self.rgb_layer_dropdown)
        
        # Create a container for the second set of buttons
        self.buttons2_container = QWidget()
        self.buttons2_layout = QGridLayout(self.buttons2_container)
        self.buttons2_layout.setHorizontalSpacing(5)
        self.buttons2_layout.setVerticalSpacing(5)
        
        self.row3_layout.addWidget(self.buttons2_container)
        self.row3_layout.addStretch()  # Right spacer
        
        self.main_layout.addLayout(self.row3_layout)

        # Populate all buttons
        self.populate_buttons()

        # Spacer to push everything to the top
        self.main_layout.addStretch()

    def create_rgb_mode_dropdown(self):
        dropdown = ScrollableComboBox()
        dropdown.setFixedHeight(40)
        dropdown.addItem("RGB Mode")
        for keycode in self.smartchord_LSB:
            label = Keycode.label(keycode.qmk_id)
            tooltip = Keycode.description(keycode.qmk_id)
            dropdown.addItem(label, keycode.qmk_id)
            item = dropdown.model().item(dropdown.count() - 1)
            item.setToolTip(tooltip)
        dropdown.model().item(0).setEnabled(False)
        dropdown.currentIndexChanged.connect(self.on_selection_change)
        dropdown.currentIndexChanged.connect(lambda _: self.reset_dropdown(dropdown, "RGB Mode"))
        return dropdown

    def create_rgb_color_dropdown(self):
        dropdown = ScrollableComboBox()
        dropdown.setFixedHeight(40)
        dropdown.addItem("RGB Color")
        for keycode in self.smartchord_MSB:
            label = Keycode.label(keycode.qmk_id)
            tooltip = Keycode.description(keycode.qmk_id)
            dropdown.addItem(label, keycode.qmk_id)
            item = dropdown.model().item(dropdown.count() - 1)
            item.setToolTip(tooltip)
        dropdown.model().item(0).setEnabled(False)
        dropdown.currentIndexChanged.connect(self.on_selection_change)
        dropdown.currentIndexChanged.connect(lambda _: self.reset_dropdown(dropdown, "RGB Color"))
        return dropdown

    def create_rgb_layer_dropdown(self):
        dropdown = ScrollableComboBox()
        dropdown.setFixedHeight(40)
        dropdown.addItem("Record Layer RGB")
        for keycode in self.smartchord_LSB2:
            label = Keycode.label(keycode.qmk_id)
            tooltip = Keycode.description(keycode.qmk_id)
            dropdown.addItem(label, keycode.qmk_id)
            item = dropdown.model().item(dropdown.count() - 1)
            item.setToolTip(tooltip)
        dropdown.model().item(0).setEnabled(False)
        dropdown.currentIndexChanged.connect(self.on_selection_change)
        dropdown.currentIndexChanged.connect(lambda _: self.reset_dropdown(dropdown, "RGB Layer Save"))
        return dropdown

    def populate_buttons(self, keycode_filter=None):
        # Clear previous widgets in both button layouts
        clear_layout_widgets(self.buttons1_layout)
        clear_layout_widgets(self.buttons2_layout)

        # Add buttons from inversion_keycodes to the first button grid
        row = 0
        col = 0
        max_columns = 15  # Maximum number of columns
        
        for keycode in self.inversion_keycodes:
            if keycode_filter is None or keycode_filter(keycode.qmk_id):
                btn = SquareButton()
                btn.setFixedHeight(50)
                btn.setFixedWidth(50)
                btn.setText(Keycode.label(keycode.qmk_id))
                btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = keycode

                self.buttons1_layout.addWidget(btn, row, col)
                col += 1
                # Move to the next row if we reach max columns
                if col >= max_columns:
                    col = 0
                    row += 1
        
        # Add buttons from inversion_keycodes4 to the second button grid
        row = 0
        col = 0
        
        for keycode in self.inversion_keycodes4:
            if keycode_filter is None or keycode_filter(keycode.qmk_id):
                btn = SquareButton()
                btn.setFixedHeight(50)
                btn.setFixedWidth(50)
                btn.setText(Keycode.label(keycode.qmk_id))
                btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = keycode

                self.buttons2_layout.addWidget(btn, row, col)
                col += 1
                # Move to the next row if we reach max columns
                if col >= max_columns:
                    col = 0
                    row += 1

    def recreate_buttons(self, keycode_filter=None):
        # Clear and recreate the dropdowns in row 1
        self.row1_layout.removeWidget(self.rgb_mode_dropdown)
        self.row1_layout.removeWidget(self.rgb_color_dropdown)
        
        self.rgb_mode_dropdown.deleteLater()
        self.rgb_color_dropdown.deleteLater()
        
        self.rgb_mode_dropdown = self.create_rgb_mode_dropdown()
        self.rgb_mode_dropdown.setFixedWidth(200)
        self.row1_layout.insertWidget(1, self.rgb_mode_dropdown)
        
        self.rgb_color_dropdown = self.create_rgb_color_dropdown()
        self.rgb_color_dropdown.setFixedWidth(200)
        self.row1_layout.insertWidget(2, self.rgb_color_dropdown)
        
        # Clear and recreate the dropdown in row 3
        self.row3_layout.removeWidget(self.rgb_layer_dropdown)
        self.rgb_layer_dropdown.deleteLater()
        
        self.rgb_layer_dropdown = self.create_rgb_layer_dropdown()
        self.rgb_layer_dropdown.setFixedWidth(200)
        self.row3_layout.insertWidget(1, self.rgb_layer_dropdown)
        
        # Repopulate all buttons
        self.populate_buttons(keycode_filter)

    def reset_dropdown(self, dropdown, header_text):
        selected_index = dropdown.currentIndex()
        if selected_index > 0:
            selected_value = dropdown.itemData(selected_index)
        dropdown.setCurrentIndex(0)

    def on_selection_change(self, index):
        selected_qmk_id = self.sender().itemData(index)
        if selected_qmk_id:
            self.keycode_changed.emit(selected_qmk_id)

    def relabel_buttons(self):
        # Handle relabeling for buttons in first grid
        for widget in iter_layout_widgets(self.buttons1_layout):
            if isinstance(widget, SquareButton):
                keycode = widget.keycode
                if keycode:
                    widget.setText(Keycode.label(keycode.qmk_id))
                    
        # Handle relabeling for buttons in second grid
        for widget in iter_layout_widgets(self.buttons2_layout):
            if isinstance(widget, SquareButton):
                keycode = widget.keycode
                if keycode:
                    widget.setText(Keycode.label(keycode.qmk_id))

    def has_buttons(self):
        """Check if there are buttons or dropdown items."""
        return (self.buttons1_layout.count() > 0 or self.buttons2_layout.count() > 0)

class LightingTab2(QScrollArea):
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, smartchord_DF, smartchord_MO, smartchord_OSL):
        super().__init__(parent)
        self.label = label
        self.smartchord_DF = smartchord_DF
        self.smartchord_MO = smartchord_MO
        self.smartchord_OSL = smartchord_OSL

        # Import QFrame if it's not already imported
        from PyQt5.QtWidgets import QFrame, QListView, QScrollBar

        # Create a widget for the scroll area content
        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)

        # Set the scroll area properties
        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        # Add a spacer at the top (20px)
        top_spacer1 = QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.main_layout.addItem(top_spacer1)

        # Add "Layer Controls" title
        self.lighting_controls_label = QLabel("Layer Controls")
        self.lighting_controls_label.setAlignment(Qt.AlignCenter)
        self.lighting_controls_label.setStyleSheet("font-size: 13px;")
        self.main_layout.addWidget(self.lighting_controls_label)

        # Add another spacer (10px)
        top_spacer2 = QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.main_layout.addItem(top_spacer2)

        # Row 1: Three Layer dropdowns
        self.row1_layout = QHBoxLayout()
        self.row1_layout.addStretch()  # Left spacer

        # Create and add dropdowns with fixed width
        self.default_layer_dropdown = self.create_default_layer_dropdown()
        self.default_layer_dropdown.setFixedWidth(200)
        self.row1_layout.addWidget(self.default_layer_dropdown)

        self.hold_layer_dropdown = self.create_hold_layer_dropdown()
        self.hold_layer_dropdown.setFixedWidth(200)
        self.row1_layout.addWidget(self.hold_layer_dropdown)

        self.oneshot_layer_dropdown = self.create_oneshot_layer_dropdown()
        self.oneshot_layer_dropdown.setFixedWidth(200)
        self.row1_layout.addWidget(self.oneshot_layer_dropdown)

        self.row1_layout.addStretch()  # Right spacer
        self.main_layout.addLayout(self.row1_layout)

        # Spacer to push everything to the top
        self.main_layout.addStretch()

    def create_default_layer_dropdown(self):
        dropdown = ScrollableComboBox()
        dropdown.setFixedHeight(40)
        dropdown.addItem("Default Layer")
        for keycode in self.smartchord_DF:
            label = Keycode.label(keycode.qmk_id)
            tooltip = Keycode.description(keycode.qmk_id)
            dropdown.addItem(label, keycode.qmk_id)
            item = dropdown.model().item(dropdown.count() - 1)
            item.setToolTip(tooltip)
        dropdown.model().item(0).setEnabled(False)
        dropdown.currentIndexChanged.connect(self.on_selection_change)
        dropdown.currentIndexChanged.connect(lambda _: self.reset_dropdown(dropdown, "Default Layer"))
        return dropdown

    def create_hold_layer_dropdown(self):
        dropdown = ScrollableComboBox()
        dropdown.setFixedHeight(40)
        dropdown.addItem("Hold Layer")
        for keycode in self.smartchord_MO:
            label = Keycode.label(keycode.qmk_id)
            tooltip = Keycode.description(keycode.qmk_id)
            dropdown.addItem(label, keycode.qmk_id)
            item = dropdown.model().item(dropdown.count() - 1)
            item.setToolTip(tooltip)
        dropdown.model().item(0).setEnabled(False)
        dropdown.currentIndexChanged.connect(self.on_selection_change)
        dropdown.currentIndexChanged.connect(lambda _: self.reset_dropdown(dropdown, "Hold Layer"))
        return dropdown

    def create_oneshot_layer_dropdown(self):
        dropdown = ScrollableComboBox()
        dropdown.setFixedHeight(40)
        dropdown.addItem("One Shot Layer")
        for keycode in self.smartchord_OSL:
            label = Keycode.label(keycode.qmk_id)
            tooltip = Keycode.description(keycode.qmk_id)
            dropdown.addItem(label, keycode.qmk_id)
            item = dropdown.model().item(dropdown.count() - 1)
            item.setToolTip(tooltip)
        dropdown.model().item(0).setEnabled(False)
        dropdown.currentIndexChanged.connect(self.on_selection_change)
        dropdown.currentIndexChanged.connect(lambda _: self.reset_dropdown(dropdown, "One Shot Layer"))
        return dropdown

    def recreate_buttons(self, keycode_filter=None):
        # Clear and recreate all three dropdowns
        self.row1_layout.removeWidget(self.default_layer_dropdown)
        self.row1_layout.removeWidget(self.hold_layer_dropdown)
        self.row1_layout.removeWidget(self.oneshot_layer_dropdown)

        self.default_layer_dropdown.deleteLater()
        self.hold_layer_dropdown.deleteLater()
        self.oneshot_layer_dropdown.deleteLater()

        self.default_layer_dropdown = self.create_default_layer_dropdown()
        self.default_layer_dropdown.setFixedWidth(200)
        self.row1_layout.insertWidget(1, self.default_layer_dropdown)

        self.hold_layer_dropdown = self.create_hold_layer_dropdown()
        self.hold_layer_dropdown.setFixedWidth(200)
        self.row1_layout.insertWidget(2, self.hold_layer_dropdown)

        self.oneshot_layer_dropdown = self.create_oneshot_layer_dropdown()
        self.oneshot_layer_dropdown.setFixedWidth(200)
        self.row1_layout.insertWidget(3, self.oneshot_layer_dropdown)

    def reset_dropdown(self, dropdown, header_text):
        selected_index = dropdown.currentIndex()
        if selected_index > 0:
            selected_value = dropdown.itemData(selected_index)
        dropdown.setCurrentIndex(0)

    def on_selection_change(self, index):
        selected_qmk_id = self.sender().itemData(index)
        if selected_qmk_id:
            self.keycode_changed.emit(selected_qmk_id)

    def relabel_buttons(self):
        # No buttons to relabel in this simplified version
        pass

    def has_buttons(self):
        """Check if there are buttons or dropdown items."""
        return True  # Always has dropdowns

class MacroSubTab(QScrollArea):
    """Sub-tab for displaying keycode buttons (Macro, Tapdance, DKS, or Toggle)"""
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, tab_type):
        super().__init__(parent)
        self.tab_type = tab_type  # "macro", "tapdance", "dks", "toggle"
        self.buttons = []
        self.button_count = 0
        self.current_keycode_filter = None

        # Create scroll content
        self.scroll_content = QWidget()
        self.flow_layout = FlowLayout()
        self.flow_layout.setContentsMargins(10, 10, 10, 10)
        self.scroll_content.setLayout(self.flow_layout)

        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def set_button_count(self, count):
        """Set the number of buttons to display"""
        self.button_count = count

    def recreate_buttons(self, keycode_filter=None):
        """Recreate buttons based on the current count"""
        self.current_keycode_filter = keycode_filter

        # Clear existing buttons
        while self.flow_layout.count():
            child = self.flow_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.buttons.clear()

        # Get the appropriate keycodes based on tab type
        if self.tab_type == "macro":
            keycodes = KEYCODES_MACRO[:self.button_count] if self.button_count > 0 else []
        elif self.tab_type == "tapdance":
            keycodes = KEYCODES_TAP_DANCE[:self.button_count] if self.button_count > 0 else []
        elif self.tab_type == "dks":
            keycodes = KEYCODES_DKS[:self.button_count] if self.button_count > 0 else []
        elif self.tab_type == "toggle":
            keycodes = KEYCODES_TOGGLE[:self.button_count] if self.button_count > 0 else []
            keycodes = keycodes + KEYCODES_TOGGLE_ACTIONS  # bulk-reset actions always shown
        else:
            keycodes = []

        # Create buttons for each keycode
        for keycode in keycodes:
            if keycode_filter is None or keycode_filter(keycode):
                btn = SquareButton()
                btn.setRelSize(KEYCODE_BTN_RATIO)
                btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = keycode
                # Use custom name if available
                custom = KeycodeDisplay.get_custom_name_label(keycode.qmk_id)
                btn.setText(custom if custom else keycode.label)
                btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.qmk_id)
                self.flow_layout.addWidget(btn)
                self.buttons.append(btn)

        # Add "All Macros Off" button at end of macro subtab
        if self.tab_type == "macro":
            all_off_kc = Keycode.find_by_qmk_id("QK_MACRO_ALL_OFF")
            if all_off_kc and (keycode_filter is None or keycode_filter(all_off_kc)):
                btn = SquareButton()
                btn.setRelSize(KEYCODE_BTN_RATIO)
                btn.clicked.connect(lambda _, k=all_off_kc.qmk_id: self.keycode_changed.emit(k))
                btn.keycode = all_off_kc
                btn.setText(all_off_kc.label)
                btn.setToolTip(all_off_kc.tooltip if all_off_kc.tooltip else all_off_kc.qmk_id)
                self.flow_layout.addWidget(btn)
                self.buttons.append(btn)

    def has_buttons(self):
        return len(self.buttons) > 0

    def relabel_buttons(self):
        for btn in self.buttons:
            if hasattr(btn, 'keycode') and btn.keycode:
                custom = KeycodeDisplay.get_custom_name_label(btn.keycode.qmk_id)
                btn.setText(custom if custom else btn.keycode.label)


class MacroTab(QScrollArea):
    """Macros tab: Macro / Tapdance / DKS / Toggle shown as stacked sections in
    a single scrolling window (no inner side-tabs). Layers is its own side-tab
    under Keyboard now, so callers pass include_layer=False; the optional Layers
    section is retained for back-compat but is unused by the Keyboard tab."""
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, inversion_keycodes, smartchord_LSB, smartchord_MSB,
                 layer_df=None, layer_mo=None, layer_osl=None, include_layer=True):
        super().__init__(parent)
        self.label = label
        self.inversion_keycodes = inversion_keycodes
        self.smartchord_LSB = smartchord_LSB
        self.smartchord_MSB = smartchord_MSB
        self.layer_df = layer_df if layer_df is not None else []
        self.layer_mo = layer_mo if layer_mo is not None else []
        self.layer_osl = layer_osl if layer_osl is not None else []
        self.include_layer = include_layer
        self.keyboard = None
        self.current_keycode_filter = None

        # Editor references (will be set via set_editors())
        self.macro_recorder = None
        self.tap_dance_editor = None
        self.dks_settings = None
        self.toggle_settings = None
        self.delay_settings = None

        # Default counts (will be updated when editors are set)
        self.macro_count = 1
        self.tapdance_count = 1
        self.dks_count = 1
        self.toggle_count = 1
        self.delay_count = 50

        self.buttons = []

        # Single scrolling content area holding stacked group sections
        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Layer dropdown references (rebuilt in recreate_buttons)
        self.default_layer_dropdown = None
        self.hold_layer_dropdown = None
        self.oneshot_layer_dropdown = None

        # Build initial contents
        self.update_counts()
        self.recreate_buttons(None)

    def set_keyboard(self, keyboard):
        """Set the keyboard reference and update counts from it"""
        self.keyboard = keyboard
        self.refresh_buttons()

    def set_editors(self, macro_recorder=None, tap_dance_editor=None, dks_settings=None, toggle_settings=None, delay_settings=None):
        """Set references to the editors to query their visible tab counts"""
        self.macro_recorder = macro_recorder
        self.tap_dance_editor = tap_dance_editor
        self.dks_settings = dks_settings
        self.toggle_settings = toggle_settings
        self.delay_settings = delay_settings
        self.refresh_buttons()

    def refresh_buttons(self):
        """Force refresh all sections with current counts"""
        self.update_counts()
        self.recreate_buttons(self.current_keycode_filter)

    def showEvent(self, event):
        """Refresh buttons when tab becomes visible"""
        super().showEvent(event)
        if self.keyboard is not None or self.macro_recorder is not None:
            self.refresh_buttons()

    def update_counts(self):
        """Update button counts from editors' visible tab counts"""
        if self.macro_recorder is not None and hasattr(self.macro_recorder, '_visible_tab_count'):
            self.macro_count = max(1, self.macro_recorder._visible_tab_count)
        elif self.keyboard is not None:
            self.macro_count = getattr(self.keyboard, 'macro_count', 1)
        else:
            self.macro_count = 1

        if self.tap_dance_editor is not None and hasattr(self.tap_dance_editor, '_visible_tab_count'):
            self.tapdance_count = max(1, self.tap_dance_editor._visible_tab_count)
        elif self.keyboard is not None:
            self.tapdance_count = getattr(self.keyboard, 'tap_dance_count', 1)
        else:
            self.tapdance_count = 1

        if self.dks_settings is not None and hasattr(self.dks_settings, '_visible_tab_count'):
            self.dks_count = max(1, self.dks_settings._visible_tab_count)
        else:
            self.dks_count = 1

        if self.toggle_settings is not None and hasattr(self.toggle_settings, '_visible_tab_count'):
            self.toggle_count = max(1, self.toggle_settings._visible_tab_count)
        else:
            self.toggle_count = 1

        if self.delay_settings is not None and hasattr(self.delay_settings, '_visible_tab_count'):
            self.delay_count = max(1, self.delay_settings._visible_tab_count)
        else:
            self.delay_count = 50

    def _make_button(self, keycode):
        btn = SquareButton()
        btn.setRelSize(KEYCODE_BTN_RATIO)
        btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
        btn.keycode = keycode
        custom = KeycodeDisplay.get_custom_name_label(keycode.qmk_id)
        btn.setText(custom if custom else keycode.label)
        btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.qmk_id)
        return btn

    def _add_button_section(self, title, keycodes, keycode_filter, extra_keycodes=None):
        group = QGroupBox(title)
        flow = FlowLayout()
        flow.setContentsMargins(10, 10, 10, 10)
        for keycode in keycodes:
            if keycode_filter is None or keycode_filter(keycode):
                btn = self._make_button(keycode)
                flow.addWidget(btn)
                self.buttons.append(btn)
        if extra_keycodes:
            for keycode in extra_keycodes:
                if keycode is not None and (keycode_filter is None or keycode_filter(keycode)):
                    btn = self._make_button(keycode)
                    flow.addWidget(btn)
                    self.buttons.append(btn)
        group.setLayout(flow)
        self.main_layout.addWidget(group)
        return group

    def _make_layer_dropdown(self, header, keycodes, keycode_filter):
        dropdown = CenteredComboBox()
        dropdown.setFixedHeight(40)
        dropdown.setFixedWidth(200)
        dropdown.addItem(header)
        for keycode in keycodes:
            if keycode_filter is None or keycode_filter(keycode.qmk_id):
                label = Keycode.label(keycode.qmk_id)
                tooltip = Keycode.description(keycode.qmk_id)
                dropdown.addItem(label, keycode.qmk_id)
                item = dropdown.model().item(dropdown.count() - 1)
                item.setToolTip(tooltip)
        dropdown.model().item(0).setEnabled(False)
        dropdown.currentIndexChanged.connect(self._on_layer_selection_change)
        dropdown.currentIndexChanged.connect(lambda _, d=dropdown: d.setCurrentIndex(0))
        return dropdown

    def _on_layer_selection_change(self, index):
        selected_qmk_id = self.sender().itemData(index)
        if selected_qmk_id:
            self.keycode_changed.emit(selected_qmk_id)

    def recreate_buttons(self, keycode_filter=None):
        self.current_keycode_filter = keycode_filter
        self.update_counts()

        # Clear existing sections
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.buttons = []
        self.default_layer_dropdown = None
        self.hold_layer_dropdown = None
        self.oneshot_layer_dropdown = None

        # Macro section (+ "All Macros Off")
        macro_kcs = KEYCODES_MACRO[:self.macro_count] if self.macro_count > 0 else []
        all_off_kc = Keycode.find_by_qmk_id("QK_MACRO_ALL_OFF")
        self._add_button_section("Macro", macro_kcs, keycode_filter,
                                 extra_keycodes=[all_off_kc] if all_off_kc else None)

        # Layers section (folded in here, directly below Macro; no standalone side tab)
        if self.include_layer:
            layer_group = QGroupBox("Layers")
            layer_row = QHBoxLayout()
            layer_row.addStretch()
            self.default_layer_dropdown = self._make_layer_dropdown("Default Layer", self.layer_df, keycode_filter)
            layer_row.addWidget(self.default_layer_dropdown)
            self.hold_layer_dropdown = self._make_layer_dropdown("Hold Layer", self.layer_mo, keycode_filter)
            layer_row.addWidget(self.hold_layer_dropdown)
            self.oneshot_layer_dropdown = self._make_layer_dropdown("One Shot Layer", self.layer_osl, keycode_filter)
            layer_row.addWidget(self.oneshot_layer_dropdown)
            layer_row.addStretch()
            layer_group.setLayout(layer_row)
            self.main_layout.addWidget(layer_group)

        # Tapdance / DKS / Toggle sections
        td_kcs = KEYCODES_TAP_DANCE[:self.tapdance_count] if self.tapdance_count > 0 else []
        self._add_button_section("Tapdance", td_kcs, keycode_filter)
        dks_kcs = KEYCODES_DKS[:self.dks_count] if self.dks_count > 0 else []
        self._add_button_section("DKS", dks_kcs, keycode_filter)
        tog_kcs = KEYCODES_TOGGLE[:self.toggle_count] if self.toggle_count > 0 else []
        # Bulk-reset actions always shown alongside the slot buttons
        tog_kcs = tog_kcs + KEYCODES_TOGGLE_ACTIONS
        self._add_button_section("Toggle", tog_kcs, keycode_filter)

        self.main_layout.addStretch(1)

    def on_keycode_changed(self, code):
        self.keycode_changed.emit(code)

    def has_buttons(self):
        return True

    def relabel_buttons(self):
        for btn in self.buttons:
            if hasattr(btn, 'keycode') and btn.keycode:
                custom = KeycodeDisplay.get_custom_name_label(btn.keycode.qmk_id)
                btn.setText(custom if custom else btn.keycode.label)


class KeySplitTab(QScrollArea):
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, inversion_keycodes):
        super().__init__(parent)
        self.label = label
        self.inversion_keycodes = inversion_keycodes
        self.scroll_content = QWidget()
        
        # Main layout
        main_layout = QVBoxLayout(self.scroll_content)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Create horizontal tab buttons layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(0)
        button_layout.setContentsMargins(0, 0, 0, 0)

        self.toggle_button = QPushButton("KeySplit")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setProperty("inner_tab", "true")
        self.toggle_button.clicked.connect(self.toggle_midi_layouts)
        button_layout.addWidget(self.toggle_button)

        self.toggle_button2 = QPushButton("TripleSplit")
        self.toggle_button2.setCheckable(True)
        self.toggle_button2.setProperty("inner_tab", "true")
        self.toggle_button2.clicked.connect(self.toggle_midi_layouts2)
        button_layout.addWidget(self.toggle_button2)

        button_layout.addStretch(1)
        main_layout.addLayout(button_layout)

        # Create content wrapper with border (like QTabWidget::pane)
        content_wrapper = QWidget()
        content_wrapper.setStyleSheet("""
            QWidget {
                border: 1px solid palette(mid);
                border-top: 1px solid palette(mid);
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 0.1,
                                           stop: 0 palette(alternate-base),
                                           stop: 1 palette(base));
                margin-top: -1px;
            }
        """)
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(10, 10, 10, 10)

        # Piano keyboards
        self.keysplit_piano = PianoKeyboard(color_scheme='keysplit')
        self.keysplit_piano.keyPressed.connect(self.keycode_changed)
        content_layout.addWidget(self.keysplit_piano)

        self.triplesplit_piano = PianoKeyboard(color_scheme='triplesplit')
        self.triplesplit_piano.keyPressed.connect(self.keycode_changed)
        content_layout.addWidget(self.triplesplit_piano)
        self.triplesplit_piano.hide()

        # Control buttons
        self.ks_controls = QWidget()
        ks_control_layout = QHBoxLayout(self.ks_controls)
        ks_control_layout.setAlignment(Qt.AlignCenter)
        self.create_control_buttons(ks_control_layout, 'KS')
        content_layout.addWidget(self.ks_controls)

        # Control buttons for TripleSplit
        self.ts_controls = QWidget()
        ts_control_layout = QHBoxLayout(self.ts_controls)
        ts_control_layout.setAlignment(Qt.AlignCenter)
        self.create_control_buttons(ts_control_layout, 'TS')
        content_layout.addWidget(self.ts_controls)
        self.ts_controls.hide()

        # Add the modifier button at the bottom
        modifier_button_container = QWidget()
        modifier_button_layout = QHBoxLayout(modifier_button_container)
        modifier_button_layout.setAlignment(Qt.AlignCenter)

        modifier_btn = QPushButton("KeySplit\nModifier")
        modifier_btn.setFixedSize(80, 50)
        modifier_btn.setStyleSheet("background-color: rgba(243, 209, 209, 1); color: rgba(128, 87, 87, 1);")
        modifier_btn.clicked.connect(lambda: self.keycode_changed.emit("KS_MODIFIER"))
        modifier_button_layout.addWidget(modifier_btn)

        content_layout.addWidget(modifier_button_container)
        content_layout.addStretch(1)
        main_layout.addWidget(content_wrapper)

        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        # Show KeySplit by default
        self.toggle_button.setChecked(True)

    def relabel_buttons(self):
        """Relabel all piano keys and control buttons"""
        # Relabel KeySplit piano keys
        for key in self.keysplit_piano.white_keys + self.keysplit_piano.black_keys:
            if hasattr(key, 'midi_id'):
                key.setText(Keycode.label(key.midi_id))

        # Relabel TripleSplit piano keys
        for key in self.triplesplit_piano.white_keys + self.triplesplit_piano.black_keys:
            if hasattr(key, 'midi_id'):
                key.setText(Keycode.label(key.midi_id))

        # Relabel control buttons
        for controls in [self.ks_controls, self.ts_controls]:
            layout = controls.layout()
            for widget in iter_layout_widgets(layout):
                if isinstance(widget, QPushButton) and hasattr(widget, 'midi_id'):
                    widget.setText(Keycode.label(widget.midi_id))

    def create_control_buttons(self, layout, prefix):
        controls = [
            (f"{prefix}\nChannel\n-", f"{'KS2' if prefix == 'TS' else prefix}_CHAN_DOWN"),
            (f"{prefix}\nChannel\n+", f"{'KS2' if prefix == 'TS' else prefix}_CHAN_UP"),
            (f"{prefix}\nVelocity\n-", f"MI_VELOCITY{2 if prefix == 'KS' else 3}_DOWN"),
            (f"{prefix}\nVelocity\n+", f"MI_VELOCITY{2 if prefix == 'KS' else 3}_UP"),
            (f"{prefix}\nTranspose\n-", f"MI_TRANSPOSE{2 if prefix == 'KS' else 3}_DOWN"),
            (f"{prefix}\nTranspose\n+", f"MI_TRANSPOSE{2 if prefix == 'KS' else 3}_UP"),
            (f"{prefix}\nOctave\n-", f"MI_OCTAVE{2 if prefix == 'KS' else 3}_DOWN"),
            (f"{prefix}\nOctave\n+", f"MI_OCTAVE{2 if prefix == 'KS' else 3}_UP")
        ]

        for text, code in controls:
            btn = QPushButton(text)
            btn.setFixedSize(80, 50)
            btn.midi_id = code

            # Make buttons theme-related
            if prefix == 'KS':
                btn.setStyleSheet("background-color: rgba(243, 209, 209, 1); color: rgba(128, 87, 87, 1);")
            else:
                btn.setStyleSheet("background-color: rgba(209, 243, 215, 1); color: rgba(128, 128, 87, 1);")

            btn.clicked.connect(lambda _, k=code: self.keycode_changed.emit(k))
            layout.addWidget(btn)

    def toggle_midi_layouts(self):
        self.keysplit_piano.show()
        self.triplesplit_piano.hide()
        self.ks_controls.show()
        self.ts_controls.hide()
        self.toggle_button.setChecked(True)
        self.toggle_button2.setChecked(False)

    def toggle_midi_layouts2(self):
        self.keysplit_piano.hide()
        self.triplesplit_piano.show()
        self.ks_controls.hide()
        self.ts_controls.show()
        self.toggle_button2.setChecked(True)
        self.toggle_button.setChecked(False)

    def set_highlighted(self, button):
        button.setStyleSheet("""
            background-color: #f3d1d1;
            color: #805757;
        """)

    def set_highlighted2(self, button):
        button.setStyleSheet("""
            background-color: #808057;
            color: #d1f3d7;
        """)

    def set_normal(self, button):
        button.setStyleSheet("")

    def recreate_buttons(self, keycode_filter=None):
        self.keysplit_piano.create_piano_keys(self.inversion_keycodes, 'MI_SPLIT')
        self.triplesplit_piano.create_piano_keys(self.inversion_keycodes, 'MI_SPLIT2')

    def has_buttons(self):
        return True


class KeySplitOnlyTab(QScrollArea):
    """KeySplit tab - simplified to show only KeySplit"""
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, inversion_keycodes):
        super().__init__(parent)
        self.label = label
        self.inversion_keycodes = inversion_keycodes
        self.scroll_content = QWidget()

        # Main layout
        main_layout = QVBoxLayout(self.scroll_content)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Piano keyboard
        self.keysplit_piano = PianoKeyboard(color_scheme='keysplit')
        self.keysplit_piano.keyPressed.connect(self.keycode_changed)
        main_layout.addWidget(self.keysplit_piano)

        # Control buttons
        ks_control_layout = QHBoxLayout()
        ks_control_layout.setAlignment(Qt.AlignCenter)
        self.create_control_buttons(ks_control_layout, 'KS')
        main_layout.addLayout(ks_control_layout)

        # Modifier button at the bottom
        modifier_button_container = QWidget()
        modifier_button_layout = QHBoxLayout(modifier_button_container)
        modifier_button_layout.setAlignment(Qt.AlignCenter)

        modifier_btn = QPushButton("KeySplit\nModifier")
        modifier_btn.setFixedSize(80, 50)
        modifier_btn.setStyleSheet("background-color: rgba(243, 209, 209, 1); color: rgba(128, 87, 87, 1);")
        modifier_btn.clicked.connect(lambda: self.keycode_changed.emit("KS_MODIFIER"))
        modifier_button_layout.addWidget(modifier_btn)

        main_layout.addWidget(modifier_button_container)
        main_layout.addStretch(1)

        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

    def create_control_buttons(self, layout, prefix):
        controls = [
            (f"{prefix}\nChannel\n-", f"{prefix}_CHAN_DOWN"),
            (f"{prefix}\nChannel\n+", f"{prefix}_CHAN_UP"),
            (f"{prefix}\nVelocity\n-", "MI_VELOCITY2_DOWN"),
            (f"{prefix}\nVelocity\n+", "MI_VELOCITY2_UP"),
            (f"{prefix}\nTranspose\n-", "MI_TRANSPOSE2_DOWN"),
            (f"{prefix}\nTranspose\n+", "MI_TRANSPOSE2_UP"),
            (f"{prefix}\nOctave\n-", "MI_OCTAVE2_DOWN"),
            (f"{prefix}\nOctave\n+", "MI_OCTAVE2_UP")
        ]

        for text, code in controls:
            btn = QPushButton(text)
            btn.setFixedSize(80, 50)
            btn.setStyleSheet("background-color: rgba(243, 209, 209, 1); color: rgba(128, 87, 87, 1);")
            btn.clicked.connect(lambda _, k=code: self.keycode_changed.emit(k))
            layout.addWidget(btn)

    def recreate_buttons(self, keycode_filter=None):
        self.keysplit_piano.create_piano_keys(self.inversion_keycodes, 'MI_SPLIT')

    def has_buttons(self):
        return True

    def relabel_buttons(self):
        pass


class TripleSplitTab(QScrollArea):
    """TripleSplit tab - simplified to show only TripleSplit"""
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, inversion_keycodes):
        super().__init__(parent)
        self.label = label
        self.inversion_keycodes = inversion_keycodes
        self.scroll_content = QWidget()

        # Main layout
        main_layout = QVBoxLayout(self.scroll_content)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Piano keyboard
        self.triplesplit_piano = PianoKeyboard(color_scheme='triplesplit')
        self.triplesplit_piano.keyPressed.connect(self.keycode_changed)
        main_layout.addWidget(self.triplesplit_piano)

        # Control buttons
        ts_control_layout = QHBoxLayout()
        ts_control_layout.setAlignment(Qt.AlignCenter)
        self.create_control_buttons(ts_control_layout, 'TS')
        main_layout.addLayout(ts_control_layout)

        # Modifier button at the bottom
        modifier_button_container = QWidget()
        modifier_button_layout = QHBoxLayout(modifier_button_container)
        modifier_button_layout.setAlignment(Qt.AlignCenter)

        modifier_btn = QPushButton("TripleSplit\nModifier")
        modifier_btn.setFixedSize(80, 50)
        modifier_btn.setStyleSheet("background-color: rgba(209, 243, 215, 1); color: rgba(128, 128, 87, 1);")
        modifier_btn.clicked.connect(lambda: self.keycode_changed.emit("TS_MODIFIER"))
        modifier_button_layout.addWidget(modifier_btn)

        main_layout.addWidget(modifier_button_container)
        main_layout.addStretch(1)

        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

    def create_control_buttons(self, layout, prefix):
        controls = [
            ("TS\nChannel\n-", "KS2_CHAN_DOWN"),
            ("TS\nChannel\n+", "KS2_CHAN_UP"),
            ("TS\nVelocity\n-", "MI_VELOCITY3_DOWN"),
            ("TS\nVelocity\n+", "MI_VELOCITY3_UP"),
            ("TS\nTranspose\n-", "MI_TRANSPOSE3_DOWN"),
            ("TS\nTranspose\n+", "MI_TRANSPOSE3_UP"),
            ("TS\nOctave\n-", "MI_OCTAVE3_DOWN"),
            ("TS\nOctave\n+", "MI_OCTAVE3_UP")
        ]

        for text, code in controls:
            btn = QPushButton(text)
            btn.setFixedSize(80, 50)
            btn.setStyleSheet("background-color: rgba(209, 243, 215, 1); color: rgba(128, 128, 87, 1);")
            btn.clicked.connect(lambda _, k=code: self.keycode_changed.emit(k))
            layout.addWidget(btn)

    def recreate_buttons(self, keycode_filter=None):
        self.triplesplit_piano.create_piano_keys(self.inversion_keycodes, 'MI_SPLIT2')

    def has_buttons(self):
        return True

    def relabel_buttons(self):
        pass


class PianoKeyboard(QWidget):
    keyPressed = pyqtSignal(str)

    def __init__(self, parent=None, color_scheme='default'):
        super().__init__(parent)
        self.color_scheme = color_scheme
        
        # Key dimensions
        self.white_key_width = 45
        self.white_key_height = 80
        self.black_key_width = 31
        self.black_key_height = 55
        self.row_spacing = 15
        
        # Calculate size for two rows of 3 octaves each
        self.octaves_per_row = 3
        self.white_keys_per_octave = 7
        self.total_white_keys_per_row = self.octaves_per_row * self.white_keys_per_octave
        
        # Set fixed widget size
        total_width = self.total_white_keys_per_row * self.white_key_width
        total_height = (self.white_key_height * 2) + self.row_spacing
        
        # Create a container for centering
        self.container = QWidget(self)
        self.container.setFixedSize(total_width, total_height)
        
        # Center the container
        self.setMinimumSize(total_width + 40, total_height + 30)
        
        self.white_keys = []
        self.black_keys = []

    def resizeEvent(self, event):
        # Center the container in the widget
        x = (self.width() - self.container.width()) // 2
        y = (self.height() - self.container.height()) // 2
        self.container.move(x, y)
        super().resizeEvent(event)

    def create_piano_keys(self, midi_mappings, key_prefix='MI'):
        for key in self.white_keys + self.black_keys:
            key.deleteLater()
        self.white_keys.clear()
        self.black_keys.clear()

        key_pattern = [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0]
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

        for row in range(2):
            white_index = 0
            y_offset = row * (self.white_key_height + self.row_spacing)
            start_octave = 0 if row == 0 else 3

            # Create white keys first
            for octave in range(start_octave, start_octave + 3):
                for i, is_black in enumerate(key_pattern):
                    if not is_black:
                        x = white_index * self.white_key_width
                        key = PianoButton(key_type='white', color_scheme=self.color_scheme)
                        key.setParent(self.container)
                        key.setGeometry(x, y_offset, self.white_key_width, self.white_key_height)
                        
                        note = notes[i]
                        midi_id = f"{key_prefix}_{note}" if octave == 0 else f"{key_prefix}_{note}_{octave}"
                        display_text = f"\n\n\n\n{note}{octave}"
                        
                        key.setText(display_text)
                        key.clicked.connect(lambda checked, k=midi_id: self.keyPressed.emit(k))
                        self.white_keys.append(key)
                        white_index += 1

            # Create black keys on top
            white_index = 0
            for octave in range(start_octave, start_octave + 3):
                for i, is_black in enumerate(key_pattern):
                    if is_black:
                        x = white_index * self.white_key_width - (self.black_key_width // 2)
                        key = PianoButton(key_type='black', color_scheme=self.color_scheme)
                        key.setParent(self.container)
                        key.setGeometry(x, y_offset, self.black_key_width, self.black_key_height)
                        
                        note = notes[i].replace('#', 's')
                        midi_id = f"{key_prefix}_{note}" if octave == 0 else f"{key_prefix}_{note}_{octave}"
                        display_text = f"\n\n{notes[i]}{octave}"
                        
                        key.setText(display_text)
                        key.clicked.connect(lambda checked, k=midi_id: self.keyPressed.emit(k))
                        self.black_keys.append(key)
                    if not is_black:
                        white_index += 1
                        
class midiTab(QScrollArea):
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, inversion_keycodes):
        super().__init__(parent)
        self.label = label
        self.inversion_keycodes = inversion_keycodes
        self.scroll_content = QWidget()

        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setSpacing(12)
        self.main_layout.setContentsMargins(10, 8, 10, 8)
        self.main_layout.setAlignment(Qt.AlignTop)

        # Track current keyboard view: 0=basic, 1=keysplit, 2=triplesplit
        self._current_keyboard = 0

        self.recreate_buttons()

    def _make_big_btn(self, qmk_id, label_text):
        """Create a big 90x50 section button (original format)."""
        btn = QPushButton(label_text)
        btn.setFixedSize(90, 50)
        btn.clicked.connect(lambda _, k=qmk_id: self.keycode_changed.emit(k))
        return btn

    def _make_btn(self, qmk_id, label_text):
        """Create a button matching loop tab sizing (SquareButton with KEYCODE_BTN_RATIO)."""
        btn = SquareButton()
        btn.setRelSize(KEYCODE_BTN_RATIO)
        btn.setText(label_text)
        btn.clicked.connect(lambda _, k=qmk_id: self.keycode_changed.emit(k))
        return btn

    def _create_nav_arrow(self, text):
        """Create a navigation arrow button for keyboard switching."""
        btn = QPushButton(text)
        btn.setFixedSize(100, 80)
        btn.setStyleSheet("""
            QPushButton {
                font-size: 8pt;
                font-weight: bold;
                border: 1px solid palette(mid);
                border-radius: 4px;
                background: palette(button);
                padding: 4px;
            }
            QPushButton:hover {
                background: palette(light);
            }
        """)
        return btn

    def _update_keyboard_view(self, target):
        """Switch to a keyboard view: 0=basic, 1=keysplit, 2=triplesplit."""
        self._current_keyboard = target

        # Switch piano via stacked widget (no overlap)
        self.piano_stack.setCurrentIndex(target)

        # Update arrow labels based on current view
        # Layout: TripleSplit(2) <-- Basic(0) --> KeySplit(1)
        if target == 0:
            self.left_arrow.setText("\u25C0 Show\nTripleSplit")
            self.left_arrow.clicked.disconnect()
            self.left_arrow.clicked.connect(lambda: self._update_keyboard_view(2))
            self.right_arrow.setText("Show\nKeySplit \u25B6")
            self.right_arrow.clicked.disconnect()
            self.right_arrow.clicked.connect(lambda: self._update_keyboard_view(1))
        elif target == 1:
            # On KeySplit: left goes to Basic, right goes to TripleSplit
            self.left_arrow.setText("\u25C0 Show\nBasic Keys")
            self.left_arrow.clicked.disconnect()
            self.left_arrow.clicked.connect(lambda: self._update_keyboard_view(0))
            self.right_arrow.setText("Show\nTripleSplit \u25B6")
            self.right_arrow.clicked.disconnect()
            self.right_arrow.clicked.connect(lambda: self._update_keyboard_view(2))
        elif target == 2:
            # On TripleSplit: left goes to KeySplit, right goes to Basic
            self.left_arrow.setText("\u25C0 Show\nKeySplit")
            self.left_arrow.clicked.disconnect()
            self.left_arrow.clicked.connect(lambda: self._update_keyboard_view(1))
            self.right_arrow.setText("Show\nBasic Keys \u25B6")
            self.right_arrow.clicked.disconnect()
            self.right_arrow.clicked.connect(lambda: self._update_keyboard_view(0))

    def recreate_buttons(self, keycode_filter=None):
        # Clear existing layout - must handle both widgets and sub-layouts
        def clear_layout(layout):
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    clear_layout(child.layout())
        clear_layout(self.main_layout)

        # --- Keyboard row: [left arrow] [piano] [right arrow] ---
        keyboard_row = QHBoxLayout()
        keyboard_row.setSpacing(6)
        keyboard_row.setContentsMargins(0, 0, 0, 0)

        self.left_arrow = self._create_nav_arrow("\u25C0 Show\nTripleSplit")
        self.right_arrow = self._create_nav_arrow("Show\nKeySplit \u25B6")
        self.left_arrow.clicked.connect(lambda: self._update_keyboard_view(2))
        self.right_arrow.clicked.connect(lambda: self._update_keyboard_view(1))

        # Basic Piano Keyboard
        midi_mappings = {kc.qmk_id: kc for kc in self.inversion_keycodes
                        if keycode_filter is None or keycode_filter(kc.qmk_id)}
        self.piano = PianoKeyboard()
        self.piano.keyPressed.connect(self.keycode_changed)
        self.piano.create_piano_keys(midi_mappings)

        # KeySplit Piano Keyboard (hidden by default)
        self.keysplit_piano = PianoKeyboard(color_scheme='keysplit')
        self.keysplit_piano.keyPressed.connect(self.keycode_changed)
        self.keysplit_piano.create_piano_keys(self.inversion_keycodes, 'MI_SPLIT')

        # TripleSplit Piano Keyboard
        self.triplesplit_piano = PianoKeyboard(color_scheme='triplesplit')
        self.triplesplit_piano.keyPressed.connect(self.keycode_changed)
        self.triplesplit_piano.create_piano_keys(self.inversion_keycodes, 'MI_SPLIT2')

        # Use QStackedWidget so only one piano takes up space at a time
        self.piano_stack = QStackedWidget()
        self.piano_stack.addWidget(self.piano)          # index 0 = basic
        self.piano_stack.addWidget(self.keysplit_piano)  # index 1 = keysplit
        self.piano_stack.addWidget(self.triplesplit_piano)  # index 2 = triplesplit
        self.piano_stack.setCurrentIndex(0)

        keyboard_row.addStretch(1)
        keyboard_row.addWidget(self.left_arrow, 0, Qt.AlignVCenter)
        keyboard_row.addWidget(self.piano_stack, 0)
        keyboard_row.addWidget(self.right_arrow, 0, Qt.AlignVCenter)
        keyboard_row.addStretch(1)
        self.main_layout.addLayout(keyboard_row)

        # --- Top row of controls (no title, no container, centered) ---
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        top_row.addStretch(1)
        top_controls = [
            ("MI_CHORD_99", "Smart\nChord\nToggle"),
            ("MI_TAP", "Tap\nBPM"),
            ("MI_SUS", "Sustain\nPedal"),
            ("MI_ALLOFF", "All\nNotes\nOff"),
            ("OCT_DBL_TOGGLE", "Note\nDoubler"),
            ("KS_MODIFIER", "Key\nSplit\nToggle"),
            ("TS_MODIFIER", "Triple\nSplit\nToggle"),
            ("CLEAR_MENU", "Clear\nMenu"),
        ]
        for qmk_id, label in top_controls:
            top_row.addWidget(self._make_btn(qmk_id, label))
        top_row.addStretch(1)
        self.main_layout.addLayout(top_row)

        # --- Main controls: 4x2 grid of big buttons ---
        # Top row = up buttons, Bottom row = down buttons
        grid_container = QWidget()
        grid_layout = QGridLayout(grid_container)
        grid_layout.setSpacing(6)
        grid_layout.setAlignment(Qt.AlignCenter)

        grid_up = [
            ("MI_TRNSU", "Transpose\n\u25B2"),
            ("MI_OCTU", "Octave\n\u25B2"),
            ("MI_CHU", "Channel\n\u25B2"),
            ("SMARTCHORD_UP", "SmartChord\n\u25B2"),
            ("HE_VEL_CURVE_UP", "Articulation\n\u25B2"),
        ]
        grid_down = [
            ("MI_TRNSD", "Transpose\n\u25BC"),
            ("MI_OCTD", "Octave\n\u25BC"),
            ("MI_CHD", "Channel\n\u25BC"),
            ("SMARTCHORD_DOWN", "SmartChord\n\u25BC"),
            ("HE_VEL_CURVE_DOWN", "Articulation\n\u25BC"),
        ]
        for col, (qmk_id, label) in enumerate(grid_up):
            grid_layout.addWidget(self._make_big_btn(qmk_id, label), 0, col)
        for col, (qmk_id, label) in enumerate(grid_down):
            grid_layout.addWidget(self._make_big_btn(qmk_id, label), 1, col)
        self.main_layout.addWidget(grid_container)

        # --- Extra Buttons ---
        extras_group = QGroupBox("Extra Buttons")
        extras_layout = FlowLayout()
        extra_buttons = [
            # (Octave up/down moved into the main Transpose/Channel grid above)
            # BPM
            ("BPM_UP", "BPM\nUp"), ("BPM_DOWN", "BPM\nDown"),
            # Touch Dials
            ("EXWHEEL_TRA", "Touch\nDial\nTranspose"), ("EXWHEEL_VEL", "Touch\nDial\nDynamics"), ("EXWHEEL_CHA", "Touch\nDial\nChannel"), ("EXWHEEL_SC", "Touch\nDial\nSmartChord"), ("EXWHEEL_BPM", "Touch\nDial\nBPM"),
            # Loops
            ("DM_MACRO_1", "Loop\n1"), ("DM_MACRO_2", "Loop\n2"),
            ("DM_MACRO_3", "Loop\n3"), ("DM_MACRO_4", "Loop\n4"),
            ("DM_REC5", "Loop\n5"), ("DM_REC6", "Loop\n6"),
            ("DM_REC7", "Loop\n7"), ("DM_REC8", "Loop\n8"),
            ("DM_NEXT_LOOP_REC", "Next\nLoop\nRec"),
            ("DM_OVERDUB", "Overdub\nLoop"), ("DM_MUTE", "Mute\nLoop"),
            # ThruLoops (silent CC-only loop tracks)
            ("DM_THRULOOP_1", "Thru\n1"), ("DM_THRULOOP_2", "Thru\n2"),
            ("DM_THRULOOP_3", "Thru\n3"), ("DM_THRULOOP_4", "Thru\n4"),
            ("DM_THRULOOP_5", "Thru\n5"), ("DM_THRULOOP_6", "Thru\n6"),
            ("DM_THRULOOP_7", "Thru\n7"), ("DM_THRULOOP_8", "Thru\n8"),
            ("DM_NEXT_THRULOOP_REC", "Next\nThru\nRec"),
            # Clear / reset actions (individual keycodes; also in the Clear Menu)
            ("CLEAR_MENU", "Clear\nMenu"),
            ("CLEAR_MODIFIERS", "Clear\nModifiers"),
            ("CLEAR_LOOPS", "Clear\nAll Loops"),
            ("RESET_DEFAULT", "Reset to\nDefault"),
            ("RESET_QUICKBUILDS", "Reset All\nQuickbuilds"),
            ("RESET_FACTORY", "Reset\nFactory\nDefaults"),
        ]
        for qmk_id, label in extra_buttons:
            extras_layout.addWidget(self._make_btn(qmk_id, label))
        extras_group.setLayout(extras_layout)
        self.main_layout.addWidget(extras_group, 0, Qt.AlignCenter)

        # (The Quick Build Master chooser was moved out of MIDIswitch into
        # its own "Quickbuild" side-tab -- see MusicTab.)

        self.main_layout.addStretch(1)

        # Set initial view
        self._current_keyboard = 0

    def relabel_buttons(self):
        for kb in [self.piano, self.keysplit_piano, self.triplesplit_piano]:
            if hasattr(kb, 'white_keys'):
                for widget in kb.white_keys + kb.black_keys:
                    if hasattr(widget, 'keycode'):
                        widget.setText(Keycode.label(widget.keycode.qmk_id))

    def has_buttons(self):
        return True


class SimpleTab(Tab):

    def __init__(self, parent, label, keycodes):
        super().__init__(parent, label, [(None, keycodes)])


def keycode_filter_any(kc):
    return True


def keycode_filter_masked(kc):
    return Keycode.is_basic(kc)


class GamepadWidget(QWidget):
    """Custom widget that displays a gamepad image as background with buttons overlaid"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(750, 560)

        # Create QLabel to display the image - manually positioned instead of using layout
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # Detect theme and load appropriate controller image
        window_color = QApplication.palette().color(QPalette.Window)
        brightness = (window_color.red() * 0.299 + window_color.green() * 0.587 + window_color.blue() * 0.114)

        # Choose controller image based on brightness (light or dark theme)
        if brightness > 127:  # Threshold for light/dark theme
            pixmap = QPixmap(":/controllerlight")  # Light theme alias
        else:
            pixmap = QPixmap(":/controllerdark")  # Dark theme alias

        if not pixmap.isNull():
            # Scale the pixmap to fit width while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                750, 560,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setFixedSize(scaled_pixmap.size())
            # Position image label at top center, shifted up 50px to reduce gap
            x_offset = (750 - scaled_pixmap.width()) // 2
            self.image_label.move(x_offset, -50)
        else:
            # Set a fallback text if image doesn't load
            self.image_label.setFixedSize(750, 560)
            self.image_label.move(0, 0)
            self.image_label.setText("Controller Image\nNot Loaded")
            self.image_label.setStyleSheet("""
                QLabel {
                    background-color: palette(base);
                    border: 2px solid palette(mid);
                    color: palette(text);
                    font-size: 16px;
                }
            """)


class DpadButton(QPushButton):
    """Custom QPushButton that draws a border along its masked shape"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.border_path = None
        self.border_width = 3  # Increased from 2 to 3 (1px thicker)

    def set_border_path(self, path):
        """Set the path to draw the border along"""
        self.border_path = QPainterPath(path)

    def paintEvent(self, event):
        # Let the parent draw the button normally
        super().paintEvent(event)

        # Draw the border on top
        if self.border_path:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            # Use theme-related color from palette
            border_color = QApplication.palette().color(QPalette.Mid)
            pen = QPen(border_color, self.border_width)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(self.border_path)


class GamingTab(QScrollArea):
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, gaming_keycodes):
        super().__init__(parent)
        self.label = label
        self.gaming_keycodes = gaming_keycodes
        self.current_keycode_filter = None

        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setSpacing(20)
        self.main_layout.setContentsMargins(20, 0, 20, 20)  # Remove top margin to eliminate gap
        self.main_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.recreate_buttons()

    def get_keycode(self, qmk_id):
        """Helper to get keycode by qmk_id"""
        for kc in self.gaming_keycodes:
            if kc.qmk_id == qmk_id:
                return kc
        return None

    def create_button(self, qmk_id, width=50, height=50):
        """Create a button for a keycode"""
        kc = self.get_keycode(qmk_id)
        if not kc:
            return None

        btn = QPushButton(Keycode.label(kc.qmk_id))
        btn.setFixedSize(width, height)
        btn.clicked.connect(lambda: self.keycode_changed.emit(kc.qmk_id))
        btn.keycode = kc
        return btn

    def recreate_buttons(self, keycode_filter=None):
        """Recreate all buttons for the gaming controller layout"""
        self.current_keycode_filter = keycode_filter

        # Clear existing layout
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self.clear_layout(item.layout())

        # Create gamepad widget with drawn outline
        gamepad_widget = GamepadWidget()
        gamepad_widget.setFixedSize(750, 560)  # Increased height to accommodate repositioned buttons

        # Use absolute positioning for buttons on the gamepad
        # We'll position buttons using move() after creating them as children of gamepad_widget

        # Triggers (LT and RT) - LT moved 23px left, RT moved 13px right, both up 15px
        lt_btn = self.create_button("LT", 60, 35)
        if lt_btn:
            lt_btn.setParent(gamepad_widget)
            lt_btn.move(177, 25)  # Moved 23px left from 200, 15px up

        rt_btn = self.create_button("RT", 60, 35)
        if rt_btn:
            rt_btn.setParent(gamepad_widget)
            rt_btn.move(503, 25)  # Moved 13px right from 490, 15px up

        # Gaming Mode Toggle (in middle of shoulder buttons) - moved up 10px only
        gaming_mode_btn = self.create_button("GAMING_MODE", 100, 40)
        if gaming_mode_btn:
            gaming_mode_btn.setParent(gamepad_widget)
            gaming_mode_btn.move(325, 75)  # Moved up 10px from 85

        # Bumpers (LB and RB) - LB moved 23px left, RB moved 13px right, both up 15px
        lb_btn = self.create_button("XBOX_LB", 60, 30)
        if lb_btn:
            lb_btn.setParent(gamepad_widget)
            lb_btn.move(177, 65)  # Moved 23px left from 200, 15px up

        rb_btn = self.create_button("XBOX_RB", 60, 30)
        if rb_btn:
            rb_btn.setParent(gamepad_widget)
            rb_btn.move(503, 65)  # Moved 13px right from 490, 15px up

        # D-pad (left side) - tapered arrow-shaped buttons, moved up 60px
        # Create custom polygon buttons for dpad with tapered ends

        # D-pad up: curved top (outside), tapers to point at bottom (inside, 25px taper)
        kc = self.get_keycode("DPAD_UP")
        if kc:
            dpad_up = DpadButton(Keycode.label(kc.qmk_id))
            dpad_up.setFixedSize(56, 58)
            dpad_up.clicked.connect(lambda: self.keycode_changed.emit(kc.qmk_id))
            dpad_up.keycode = kc
            dpad_up.setText("↑")
            dpad_up.setParent(gamepad_widget)
            dpad_up.move(180, 105)  # 2px left, 3px down
            # Curved top edge (outside), point at bottom (inside) with 25px taper
            path = QPainterPath()
            path.moveTo(28, 58)  # Bottom point (inside)
            path.lineTo(3, 33)   # Left side of taper (58-25=33)
            path.lineTo(3, 8)    # Left straight section
            path.quadTo(8, 3, 15, 3)   # Curved top-left corner
            path.lineTo(41, 3)   # Top straight section (curved edge)
            path.quadTo(48, 3, 53, 8)  # Curved top-right corner
            path.lineTo(53, 33)  # Right straight section
            path.lineTo(28, 58)  # Back to bottom point
            path.closeSubpath()
            dpad_up.setMask(QRegion(path.toFillPolygon().toPolygon()))
            dpad_up.set_border_path(path)

        # D-pad down: curved bottom (outside), tapers to point at top (inside, 25px taper)
        kc = self.get_keycode("DPAD_DOWN")
        if kc:
            dpad_down = DpadButton(Keycode.label(kc.qmk_id))
            dpad_down.setFixedSize(56, 58)
            dpad_down.clicked.connect(lambda: self.keycode_changed.emit(kc.qmk_id))
            dpad_down.keycode = kc
            dpad_down.setText("↓")
            dpad_down.setParent(gamepad_widget)
            dpad_down.move(180, 163)  # 2px left, 3px down
            path = QPainterPath()
            path.moveTo(28, 0)   # Top point (inside)
            path.lineTo(3, 25)   # Left side of taper (25px from point)
            path.lineTo(3, 50)   # Left straight section
            path.quadTo(8, 55, 15, 55)  # Curved bottom-left corner
            path.lineTo(41, 55)  # Bottom straight section (curved edge)
            path.quadTo(48, 55, 53, 50)  # Curved bottom-right corner
            path.lineTo(53, 25)  # Right straight section
            path.lineTo(28, 0)   # Back to top point
            path.closeSubpath()
            dpad_down.setMask(QRegion(path.toFillPolygon().toPolygon()))
            dpad_down.set_border_path(path)

        # D-pad left: curved left (outside), tapers to point at right (inside, 25px taper)
        kc = self.get_keycode("DPAD_LEFT")
        if kc:
            dpad_left = DpadButton(Keycode.label(kc.qmk_id))
            dpad_left.setFixedSize(58, 56)
            dpad_left.clicked.connect(lambda: self.keycode_changed.emit(kc.qmk_id))
            dpad_left.keycode = kc
            dpad_left.setText("←")
            dpad_left.setParent(gamepad_widget)
            dpad_left.move(150, 135)  # 2px left, 3px down
            path = QPainterPath()
            path.moveTo(58, 28)  # Right point (inside)
            path.lineTo(33, 3)   # Top side of taper (58-25=33)
            path.lineTo(8, 3)    # Top straight section
            path.quadTo(3, 8, 3, 15)   # Curved top-left corner
            path.lineTo(3, 41)   # Left straight section (curved edge)
            path.quadTo(3, 48, 8, 53)  # Curved bottom-left corner
            path.lineTo(33, 53)  # Bottom straight section
            path.lineTo(58, 28)  # Back to right point
            path.closeSubpath()
            dpad_left.setMask(QRegion(path.toFillPolygon().toPolygon()))
            dpad_left.set_border_path(path)

        # D-pad right: curved right (outside), tapers to point at left (inside, 25px taper)
        kc = self.get_keycode("DPAD_RIGHT")
        if kc:
            dpad_right = DpadButton(Keycode.label(kc.qmk_id))
            dpad_right.setFixedSize(58, 56)
            dpad_right.clicked.connect(lambda: self.keycode_changed.emit(kc.qmk_id))
            dpad_right.keycode = kc
            dpad_right.setText("→")
            dpad_right.setParent(gamepad_widget)
            dpad_right.move(208, 135)  # 2px left, 3px down
            path = QPainterPath()
            path.moveTo(0, 28)   # Left point (inside)
            path.lineTo(25, 3)   # Top side of taper (25px from point)
            path.lineTo(50, 3)   # Top straight section
            path.quadTo(55, 8, 55, 15)  # Curved top-right corner
            path.lineTo(55, 41)  # Right straight section (curved edge)
            path.quadTo(55, 48, 50, 53)  # Curved bottom-right corner
            path.lineTo(25, 53)  # Bottom straight section
            path.lineTo(0, 28)   # Back to left point
            path.closeSubpath()
            dpad_right.setMask(QRegion(path.toFillPolygon().toPolygon()))
            dpad_right.set_border_path(path)

        # Left Analog Stick - moved 23px left, then 8px right and 25px up
        ls_up = self.create_button("LS_UP", 38, 38)
        if ls_up:
            ls_up.setParent(gamepad_widget)
            ls_up.move(275, 185)  # Moved 23px left from 290, then 8px right and 25px up

        ls_down = self.create_button("LS_DOWN", 38, 38)
        if ls_down:
            ls_down.setParent(gamepad_widget)
            ls_down.move(275, 261)  # Moved 23px left from 290, then 8px right and 25px up

        ls_left = self.create_button("LS_LEFT", 38, 38)
        if ls_left:
            ls_left.setParent(gamepad_widget)
            ls_left.move(237, 223)  # Moved 23px left from 252, then 8px right and 25px up

        ls_right = self.create_button("LS_RIGHT", 38, 38)
        if ls_right:
            ls_right.setParent(gamepad_widget)
            ls_right.move(313, 223)  # Moved 23px left from 328, then 8px right and 25px up

        l3_btn = self.create_button("XBOX_L3", 38, 38)
        if l3_btn:
            l3_btn.setParent(gamepad_widget)
            l3_btn.move(275, 223)  # Center - moved 23px left from 290, then 8px right and 25px up

        # Center buttons (Back and Start) - moved up 20px
        back_btn = self.create_button("XBOX_BACK", 50, 30)
        if back_btn:
            back_btn.setParent(gamepad_widget)
            back_btn.move(320, 170)  # Moved up 20px

        start_btn = self.create_button("XBOX_START", 50, 30)
        if start_btn:
            start_btn.setParent(gamepad_widget)
            start_btn.move(380, 170)  # Moved up 20px

        # Right Analog Stick - moved 13px right, then 25px up
        rs_up = self.create_button("RS_UP", 38, 38)
        if rs_up:
            rs_up.setParent(gamepad_widget)
            rs_up.move(439, 185)  # Moved 13px right from 426, then 25px up

        rs_down = self.create_button("RS_DOWN", 38, 38)
        if rs_down:
            rs_down.setParent(gamepad_widget)
            rs_down.move(439, 261)  # Moved 13px right from 426, then 25px up

        rs_left = self.create_button("RS_LEFT", 38, 38)
        if rs_left:
            rs_left.setParent(gamepad_widget)
            rs_left.move(401, 223)  # Moved 13px right from 388, then 25px up

        rs_right = self.create_button("RS_RIGHT", 38, 38)
        if rs_right:
            rs_right.setParent(gamepad_widget)
            rs_right.move(477, 223)  # Moved 13px right from 464, then 25px up

        r3_btn = self.create_button("XBOX_R3", 38, 38)
        if r3_btn:
            r3_btn.setParent(gamepad_widget)
            r3_btn.move(439, 223)  # Center - moved 13px right from 426, then 25px up

        # Face Buttons (right side) - Button 1-4, 20% bigger (50x50) and repositioned
        btn4 = self.create_button("XBOX_Y", 50, 50)
        if btn4:
            btn4.setText("Button\n4")
            btn4.setParent(gamepad_widget)
            btn4.setStyleSheet("border-radius: 25px;")  # Make circular
            btn4.move(517, 103)  # Centered between btn3 and btn2, up 4px

        btn3 = self.create_button("XBOX_X", 50, 50)
        if btn3:
            btn3.setText("Button\n3")
            btn3.setParent(gamepad_widget)
            btn3.setStyleSheet("border-radius: 25px;")  # Make circular
            btn3.move(481, 139)  # Size adjusted to keep center

        btn2 = self.create_button("XBOX_B", 50, 50)
        if btn2:
            btn2.setText("Button\n2")
            btn2.setParent(gamepad_widget)
            btn2.setStyleSheet("border-radius: 25px;")  # Make circular
            btn2.move(553, 139)  # Same vertical as btn3, size adjusted

        btn1 = self.create_button("XBOX_A", 50, 50)
        if btn1:
            btn1.setText("Button\n1")
            btn1.setParent(gamepad_widget)
            btn1.setStyleSheet("border-radius: 25px;")  # Make circular
            btn1.move(517, 178)  # Centered between btn3 and btn2, down 6px

        # Add gamepad widget centered
        self.main_layout.addWidget(gamepad_widget, alignment=Qt.AlignHCenter)
        self.main_layout.addStretch()

    def clear_layout(self, layout):
        """Helper to clear a layout recursively"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self.clear_layout(item.layout())

    def has_buttons(self):
        """Check if tab has any buttons"""
        return len(self.gaming_keycodes) > 0

    def relabel_buttons(self):
        """Relabel all buttons (called when keymap changes)"""
        self.recreate_buttons(self.current_keycode_filter)



class KeyboardTab(QWidget):
    """Nested tab container for Keyboard-related tabs with side-tab style"""

    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, include_layer=True):
        super().__init__(parent)
        self.label = "Keyboard"
        self.parent_widget = parent
        self.current_keycode_filter = keycode_filter_any

        # Create the individual tabs
        self.basic_tab = Tab(parent, "Basic", [
            (ansi_100, KEYCODES_SPECIAL + KEYCODES_SHIFTED),
            (ansi_80, KEYCODES_SPECIAL + KEYCODES_BASIC_NUMPAD + KEYCODES_SHIFTED),
            (ansi_70, KEYCODES_SPECIAL + KEYCODES_BASIC_NUMPAD + KEYCODES_BASIC_NAV + KEYCODES_SHIFTED),
            (None, KEYCODES_SPECIAL + KEYCODES_BASIC + KEYCODES_SHIFTED),
        ], prefix_buttons=[("Any", -1)])

        self.iso_tab = Tab(parent, "ISO/JIS", [
            (iso_100, KEYCODES_SPECIAL + KEYCODES_SHIFTED + KEYCODES_ISO_KR),
            (iso_80, KEYCODES_SPECIAL + KEYCODES_BASIC_NUMPAD + KEYCODES_SHIFTED + KEYCODES_ISO_KR),
            (iso_70, KEYCODES_SPECIAL + KEYCODES_BASIC_NUMPAD + KEYCODES_BASIC_NAV + KEYCODES_SHIFTED +
             KEYCODES_ISO_KR),
            (None, KEYCODES_ISO),
        ], prefix_buttons=[("Any", -1)])

        self.app_tab = SimpleTab(parent, "App", KEYCODES_MEDIA)
        self.advanced_tab = SimpleTab(parent, "Advanced", KEYCODES_BOOT + KEYCODES_MODIFIERS + KEYCODES_QUANTUM)

        # Feature tabs folded into Keyboard as side sections. Layers are their
        # own side-tab (directly below Macros), NOT folded into the Macros
        # window -- the MacroTab therefore never renders the Layers section.
        self.macro_tab = MacroTab(parent, "Macros", KEYCODES_MACRO_BASE, KEYCODES_MACRO, KEYCODES_TAP_DANCE,
                                  KEYCODES_LAYERS_DF, KEYCODES_LAYERS_MO, KEYCODES_LAYERS_OSL,
                                  include_layer=False)
        # include_layer gates the standalone Layers side-tab (the Toggle-settings
        # picker passes include_layer=False and supplies layers via LightingTab2).
        self.layer_tab = LayerTab(parent, "Layers", KEYCODES_LAYERS_DF, KEYCODES_LAYERS_MO,
                                  KEYCODES_LAYERS_OSL) if include_layer else None
        self.lighting_tab = LightingTab(parent, "Lighting", KEYCODES_BACKLIGHT, KEYCODES_RGBSAVE, KEYCODES_RGB_KC_CUSTOM, KEYCODES_RGB_KC_COLOR, KEYCODES_RGB_KC_CUSTOM2)
        self.gaming_tab = GamingTab(parent, "Gaming", KEYCODES_GAMING)

        # Connect signals
        self.basic_tab.keycode_changed.connect(self.on_keycode_changed)
        self.iso_tab.keycode_changed.connect(self.on_keycode_changed)
        self.app_tab.keycode_changed.connect(self.on_keycode_changed)
        self.advanced_tab.keycode_changed.connect(self.on_keycode_changed)
        self.macro_tab.keycode_changed.connect(self.on_keycode_changed)
        if self.layer_tab is not None:
            self.layer_tab.keycode_changed.connect(self.on_keycode_changed)
        self.lighting_tab.keycode_changed.connect(self.on_keycode_changed)
        self.gaming_tab.keycode_changed.connect(self.on_keycode_changed)

        # Define sections (tab_widget, display_name). Layers is its own side-tab
        # directly below Macros; ISO/App/Advanced sit below Gaming.
        self.sections = [
            (self.basic_tab, "Basic"),
            (self.macro_tab, "Macros"),
        ]
        if self.layer_tab is not None:
            self.sections.append((self.layer_tab, "Layers"))
        self.sections += [
            (self.lighting_tab, "Lighting"),
            (self.gaming_tab, "Gaming"),
            (self.iso_tab, "ISO/JIS"),
            (self.app_tab, "App"),
            (self.advanced_tab, "Advanced"),
        ]

        # Create horizontal layout: side tabs on left, content on right
        main_layout_h = QHBoxLayout()
        main_layout_h.setSpacing(0)
        main_layout_h.setContentsMargins(0, 0, 0, 0)

        # Create side tabs container
        side_tabs_container = QWidget()
        side_tabs_container.setObjectName("side_tabs_container")
        side_tabs_container.setStyleSheet("""
            QWidget#side_tabs_container {
                background: palette(window);
                border: 1px solid palette(mid);
                border-right: none;
            }
        """)
        side_tabs_layout = QVBoxLayout(side_tabs_container)
        side_tabs_layout.setSpacing(0)
        side_tabs_layout.setContentsMargins(0, 0, 0, 0)

        self.side_tab_buttons = {}
        for tab_widget, display_name in self.sections:
            btn = QPushButton(display_name)
            btn.setCheckable(True)
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)
            btn.setStyleSheet("""
                QPushButton {
                    border: 1px solid palette(mid);
                    border-radius: 0px;
                    border-right: none;
                    background: palette(button);
                    text-align: left;
                    padding-left: 15px;
                    font-size: 9pt;
                }
                QPushButton:hover:!checked {
                    background: palette(light);
                }
                QPushButton:checked {
                    background: palette(base);
                    font-weight: 600;
                    border-right: 1px solid palette(base);
                }
            """)
            btn.clicked.connect(lambda checked, dn=display_name: self.show_section(dn))
            side_tabs_layout.addWidget(btn)
            self.side_tab_buttons[display_name] = btn

        side_tabs_layout.addStretch(1)
        main_layout_h.addWidget(side_tabs_container)

        # Create content container
        self.content_wrapper = QWidget()
        self.content_wrapper.setObjectName("content_wrapper")
        self.content_wrapper.setStyleSheet("""
            QWidget#content_wrapper {
                border: 1px solid palette(mid);
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 0.1,
                                           stop: 0 palette(alternate-base),
                                           stop: 1 palette(base));
            }
        """)
        self.content_layout = QVBoxLayout(self.content_wrapper)
        self.content_layout.setSpacing(0)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        # Add all section widgets to content area
        self.section_widgets = {}
        for tab_widget, display_name in self.sections:
            tab_widget.hide()
            self.content_layout.addWidget(tab_widget)
            self.section_widgets[display_name] = tab_widget

        main_layout_h.addWidget(self.content_wrapper)
        self.setLayout(main_layout_h)

        # Show first section by default
        self.show_section("Basic")

    def show_section(self, section_name):
        """Show the specified section and update tab button states"""
        # Hide all section widgets
        for widget in self.section_widgets.values():
            widget.hide()

        # Uncheck all tab buttons
        for btn in self.side_tab_buttons.values():
            btn.setChecked(False)

        # Show the selected section widget and check its tab button
        if section_name in self.section_widgets:
            self.section_widgets[section_name].show()
            if section_name in self.side_tab_buttons:
                self.side_tab_buttons[section_name].setChecked(True)

    def on_keycode_changed(self, code):
        self.keycode_changed.emit(code)

    def recreate_buttons(self, keycode_filter):
        self.current_keycode_filter = keycode_filter

        # Store currently selected section before recreating
        current_section = None
        for section_name, widget in self.section_widgets.items():
            if widget.isVisible():
                current_section = section_name
                break

        # Recreate buttons for each tab
        for tab_widget, display_name in self.sections:
            tab_widget.recreate_buttons(keycode_filter)

        # Restore the previously selected section, or default to first
        if current_section and current_section in self.section_widgets:
            self.show_section(current_section)
        else:
            self.show_section("Basic")

    def has_buttons(self):
        return any(tab.has_buttons() for tab, _ in self.sections)

    def relabel_buttons(self):
        for tab_widget, _ in self.sections:
            tab_widget.relabel_buttons()

    def set_keyboard(self, keyboard):
        self.macro_tab.set_keyboard(keyboard)
        self.gaming_tab.keyboard = keyboard

    def set_editors(self, macro_recorder=None, tap_dance_editor=None, dks_settings=None, toggle_settings=None, delay_settings=None):
        self.macro_tab.set_editors(macro_recorder, tap_dance_editor, dks_settings, toggle_settings, delay_settings=delay_settings)

    def refresh_buttons(self):
        self.macro_tab.refresh_buttons()


class ArpeggiatorTab(QScrollArea):
    """Arpeggiator control tab"""
    keycode_changed = pyqtSignal(str)
    
    def __init__(self, parent, label, arp_keycodes, arp_preset_keycodes):
        super().__init__(parent)
        self.label = label
        self.arp_keycodes = arp_keycodes
        self.arp_preset_keycodes = arp_preset_keycodes
        self.user_count = 0
        self.current_keycode_filter = None
        
        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setSpacing(20)
        self.main_layout.setContentsMargins(20, 15, 20, 15)
        self.main_layout.setAlignment(Qt.AlignTop)
        
        # Create initial buttons
        self.recreate_buttons(keycode_filter_any)
        
        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    
    def recreate_buttons(self, keycode_filter):
        self.current_keycode_filter = keycode_filter
        
        # Clear existing layout
        while self.main_layout.count():
            child = self.main_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        def _make_arp_btn(keycode):
            btn = SquareButton()
            btn.setRelSize(KEYCODE_BTN_RATIO)
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode
            btn.setText(keycode.label)
            btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
            return btn

        # Arpeggiator Controls
        control_group = QGroupBox("Arpeggiator Controls")
        control_layout = FlowLayout()
        for keycode in self.arp_keycodes:
            if keycode_filter(keycode):
                if "GATE" not in keycode.qmk_id and "RATE" not in keycode.qmk_id and "MODE" not in keycode.qmk_id and "QUICK" not in keycode.qmk_id:
                    control_layout.addWidget(_make_arp_btn(keycode))
        control_group.setLayout(control_layout)
        self.main_layout.addWidget(control_group)

        # User Presets - only slots the connected keyboard reports configured.
        # (Factory rhythm patterns are managed via the Master Quick Build menu.)
        shown = min(self.user_count, len(self.arp_preset_keycodes))
        if shown > 0:
            user_preset_group = QGroupBox("User Presets ({} configured)".format(shown))
            user_preset_layout = FlowLayout()
            for keycode in self.arp_preset_keycodes[:shown]:
                if keycode_filter(keycode):
                    btn = SquareButton()
                    btn.setRelSize(KEYCODE_BTN_RATIO)
                    btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                    btn.keycode = keycode
                    custom = KeycodeDisplay.get_custom_name_label(keycode.qmk_id)
                    btn.setText(custom if custom else keycode.label)
                    btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
                    user_preset_layout.addWidget(btn)
            user_preset_group.setLayout(user_preset_layout)
            self.main_layout.addWidget(user_preset_group)

        # Extra Global Controls (Gate Length + Rate Overrides + Playback Modes)
        extra_group = QGroupBox("Extra Global Controls")
        extra_layout = FlowLayout()
        for keycode in self.arp_keycodes:
            if keycode_filter(keycode) and ("GATE" in keycode.qmk_id or "RATE" in keycode.qmk_id or "MODE" in keycode.qmk_id):
                extra_layout.addWidget(_make_arp_btn(keycode))
        extra_group.setLayout(extra_layout)
        self.main_layout.addWidget(extra_group)

        self.main_layout.addStretch(1)

    def set_user_count(self, count):
        """Show only the first `count` (configured) user preset slots."""
        count = max(0, int(count or 0))
        if count != self.user_count:
            self.user_count = count
            self.recreate_buttons(self.current_keycode_filter or keycode_filter_any)

    def has_buttons(self):
        return len(self.arp_keycodes) > 0

    def relabel_buttons(self):
        pass  # Implement if needed


class StepSequencerTab(QScrollArea):
    """Step Sequencer control tab"""
    keycode_changed = pyqtSignal(str)
    
    def __init__(self, parent, label, seq_keycodes, seq_preset_keycodes, drum_slot_keycodes=None):
        super().__init__(parent)
        self.label = label
        self.seq_keycodes = seq_keycodes
        self.seq_preset_keycodes = seq_preset_keycodes
        self.drum_slot_keycodes = drum_slot_keycodes or []
        self.user_count = 0
        self.current_keycode_filter = None
        
        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setSpacing(20)
        self.main_layout.setContentsMargins(20, 15, 20, 15)
        self.main_layout.setAlignment(Qt.AlignTop)
        
        # Create initial buttons
        self.recreate_buttons(keycode_filter_any)
        
        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    
    def recreate_buttons(self, keycode_filter):
        self.current_keycode_filter = keycode_filter
        
        # Clear existing layout
        while self.main_layout.count():
            child = self.main_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        def _make_seq_btn(keycode):
            btn = SquareButton()
            btn.setRelSize(KEYCODE_BTN_RATIO)
            btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
            btn.keycode = keycode
            btn.setText(keycode.label)
            btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
            return btn

        # Sequencer Controls
        control_group = QGroupBox("Sequencer Controls")
        control_layout = FlowLayout()
        for keycode in self.seq_keycodes:
            if keycode_filter(keycode):
                if "GATE" not in keycode.qmk_id and "RATE" not in keycode.qmk_id and "QUICK" not in keycode.qmk_id:
                    control_layout.addWidget(_make_seq_btn(keycode))
        control_group.setLayout(control_layout)
        self.main_layout.addWidget(control_group)

        # Drum Machine Slots (20 persistent slots, configured on-device)
        if self.drum_slot_keycodes:
            drum_group = QGroupBox("Drum Machine Slots (20)")
            drum_layout = FlowLayout()
            for keycode in self.drum_slot_keycodes:
                if keycode_filter(keycode):
                    btn = SquareButton()
                    btn.setRelSize(KEYCODE_BTN_RATIO)
                    btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                    btn.keycode = keycode
                    custom = KeycodeDisplay.get_custom_name_label(keycode.qmk_id)
                    btn.setText(custom if custom else keycode.label)
                    btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
                    drum_layout.addWidget(btn)
            drum_group.setLayout(drum_layout)
            self.main_layout.addWidget(drum_group)

        # User Presets - only slots the connected keyboard reports configured.
        # (Factory step-seq presets are managed via the Master Quick Build menu.)
        shown = min(self.user_count, len(self.seq_preset_keycodes))
        if shown > 0:
            user_preset_group = QGroupBox("User Presets ({} configured)".format(shown))
            user_preset_layout = FlowLayout()
            for keycode in self.seq_preset_keycodes[:shown]:
                if keycode_filter(keycode):
                    btn = SquareButton()
                    btn.setRelSize(KEYCODE_BTN_RATIO)
                    btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
                    btn.keycode = keycode
                    custom = KeycodeDisplay.get_custom_name_label(keycode.qmk_id)
                    btn.setText(custom if custom else keycode.label)
                    btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
                    user_preset_layout.addWidget(btn)
            user_preset_group.setLayout(user_preset_layout)
            self.main_layout.addWidget(user_preset_group)

        # Extra Global Controls (Gate Length + Rate Overrides)
        extra_group = QGroupBox("Extra Global Controls")
        extra_layout = FlowLayout()
        for keycode in self.seq_keycodes:
            if keycode_filter(keycode) and ("GATE" in keycode.qmk_id or "RATE" in keycode.qmk_id):
                extra_layout.addWidget(_make_seq_btn(keycode))
        extra_group.setLayout(extra_layout)
        self.main_layout.addWidget(extra_group)

        self.main_layout.addStretch(1)

    def set_user_count(self, count):
        """Show only the first `count` (configured) user preset slots."""
        count = max(0, int(count or 0))
        if count != self.user_count:
            self.user_count = count
            self.recreate_buttons(self.current_keycode_filter or keycode_filter_any)

    def has_buttons(self):
        return len(self.seq_keycodes) > 0

    def relabel_buttons(self):
        pass  # Implement if needed


class DelayMusicTab(QScrollArea):
    """MIDI Delay slot toggle tab - shows delay keycodes for keymap assignment.
    Factory presets (48) are always visible. User slots shown based on _visible_tab_count."""
    keycode_changed = pyqtSignal(str)

    def __init__(self, parent, label, factory_keycodes, user_keycodes, delay_clear_keycodes=None, delay_qb_keycodes=None):
        super().__init__(parent)
        self.label = label
        self.factory_keycodes = factory_keycodes  # 48 factory preset keycodes (always shown)
        self.user_keycodes = user_keycodes        # 50 user slot keycodes (limited by count)
        self.delay_clear_keycodes = delay_clear_keycodes or []
        self.delay_qb_keycodes = delay_qb_keycodes or []
        self.user_button_count = 0  # Only configured slots are shown (set_button_count)
        self.current_keycode_filter = None

        self.scroll_content = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setSpacing(20)
        self.main_layout.setContentsMargins(20, 15, 20, 15)
        self.main_layout.setAlignment(Qt.AlignTop)

        self.recreate_buttons(keycode_filter_any)

        self.setWidget(self.scroll_content)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def set_button_count(self, count):
        """Set the number of user delay slot buttons to display"""
        self.user_button_count = count

    def _make_btn(self, keycode, keycode_filter):
        """Helper to create a keycode button"""
        if not keycode_filter(keycode):
            return None
        btn = SquareButton()
        btn.setRelSize(KEYCODE_BTN_RATIO)
        btn.clicked.connect(lambda _, k=keycode.qmk_id: self.keycode_changed.emit(k))
        btn.keycode = keycode
        custom = KeycodeDisplay.get_custom_name_label(keycode.qmk_id)
        btn.setText(custom if custom else keycode.label)
        btn.setToolTip(keycode.tooltip if keycode.tooltip else keycode.label)
        return btn

    def recreate_buttons(self, keycode_filter):
        self.current_keycode_filter = keycode_filter

        # Clear existing layout
        while self.main_layout.count():
            child = self.main_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Delay Control
        if self.delay_clear_keycodes:
            clear_group = QGroupBox("Delay Control")
            clear_layout = FlowLayout()
            for keycode in self.delay_clear_keycodes:
                btn = self._make_btn(keycode, keycode_filter)
                if btn:
                    clear_layout.addWidget(btn)
            clear_group.setLayout(clear_layout)
            self.main_layout.addWidget(clear_group)

        # Factory Presets - ALWAYS fully visible (48 presets in flash)
        if self.factory_keycodes:
            factory_group = QGroupBox("Factory Delay Presets")
            factory_layout = FlowLayout()
            for keycode in self.factory_keycodes:
                btn = self._make_btn(keycode, keycode_filter)
                if btn:
                    factory_layout.addWidget(btn)
            factory_group.setLayout(factory_layout)
            self.main_layout.addWidget(factory_group)

        # User Delay Slots - only slots the delay editor reports configured
        if self.user_keycodes and self.user_button_count > 0:
            user_group = QGroupBox("User Delay Presets ({} configured)".format(min(self.user_button_count, len(self.user_keycodes))))
            user_layout = FlowLayout()
            for i, keycode in enumerate(self.user_keycodes):
                if i >= self.user_button_count:
                    break
                btn = self._make_btn(keycode, keycode_filter)
                if btn:
                    user_layout.addWidget(btn)
            user_group.setLayout(user_layout)
            self.main_layout.addWidget(user_group)

        self.main_layout.addStretch(1)

    def has_buttons(self):
        return len(self.factory_keycodes) > 0 or len(self.user_keycodes) > 0

    def relabel_buttons(self):
        pass


class MusicTab(QWidget):
    """Nested tab container for Music-related tabs with side-tab style"""

    keycode_changed = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.label = "Music"
        self.parent_widget = parent
        self.current_keycode_filter = keycode_filter_any

        # Create the individual tabs. (DrumLIVE, Arpeggiator, Step Sequencer
        # and Delay moved to the Advanced tab; Ear Training and Chord
        # Progressions are retired.) The Quickbuild side-tab holds all 100
        # Quickbuild slot buttons (formerly a single chooser button in
        # MIDIswitch).
        self.midiswitch_tab = midiTab(parent, "MIDIswitch", KEYCODES_MIDI_UPDOWN)
        self.loop_control_tab = LoopTab(parent, "Loop Control", KEYCODES_LOOP_BUTTONS)
        self.smartchord_tab = SmartChordTab(parent, "SmartChord", KEYCODES_MIDI_CHORD_0, KEYCODES_MIDI_CHORD_1,
                                           KEYCODES_MIDI_CHORD_2, KEYCODES_MIDI_CHORD_3, KEYCODES_MIDI_CHORD_4,
                                           KEYCODES_MIDI_CHORD_5, KEYCODES_MIDI_SCALES,
                                           KEYCODES_MIDI_SMARTCHORDBUTTONS+KEYCODES_MIDI_INVERSION)
        self.quickbuild_tab = SimpleTab(parent, "Quickbuild", KEYCODES_QB_MASTER)

        # Connect signals
        self.midiswitch_tab.keycode_changed.connect(self.on_keycode_changed)
        self.loop_control_tab.keycode_changed.connect(self.on_keycode_changed)
        self.smartchord_tab.keycode_changed.connect(self.on_keycode_changed)
        self.quickbuild_tab.keycode_changed.connect(self.on_keycode_changed)

        # Define sections (tab_widget, display_name)
        self.sections = [
            (self.midiswitch_tab, "MIDIswitch"),
            (self.loop_control_tab, "Loop Control"),
            (self.smartchord_tab, "SmartChord"),
            (self.quickbuild_tab, "Quick\nBuild")
        ]

        # Create horizontal layout: side tabs on left, content on right
        main_layout_h = QHBoxLayout()
        main_layout_h.setSpacing(0)
        main_layout_h.setContentsMargins(0, 0, 0, 0)

        # Create side tabs container
        side_tabs_container = QWidget()
        side_tabs_container.setObjectName("side_tabs_container")
        side_tabs_container.setStyleSheet("""
            QWidget#side_tabs_container {
                background: palette(window);
                border: 1px solid palette(mid);
                border-right: none;
            }
        """)
        side_tabs_layout = QVBoxLayout(side_tabs_container)
        side_tabs_layout.setSpacing(0)
        side_tabs_layout.setContentsMargins(0, 0, 0, 0)

        self.side_tab_buttons = {}
        for tab_widget, display_name in self.sections:
            btn = QPushButton(display_name)
            btn.setCheckable(True)
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)
            btn.setStyleSheet("""
                QPushButton {
                    border: 1px solid palette(mid);
                    border-radius: 0px;
                    border-right: none;
                    background: palette(button);
                    text-align: left;
                    padding-left: 15px;
                    font-size: 9pt;
                }
                QPushButton:hover:!checked {
                    background: palette(light);
                }
                QPushButton:checked {
                    background: palette(base);
                    font-weight: 600;
                    border-right: 1px solid palette(base);
                }
            """)
            btn.clicked.connect(lambda checked, dn=display_name: self.show_section(dn))
            side_tabs_layout.addWidget(btn)
            self.side_tab_buttons[display_name] = btn

        side_tabs_layout.addStretch(1)
        main_layout_h.addWidget(side_tabs_container)

        # Create content container
        self.content_wrapper = QWidget()
        self.content_wrapper.setObjectName("content_wrapper")
        self.content_wrapper.setStyleSheet("""
            QWidget#content_wrapper {
                border: 1px solid palette(mid);
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 0.1,
                                           stop: 0 palette(alternate-base),
                                           stop: 1 palette(base));
            }
        """)
        self.content_layout = QVBoxLayout(self.content_wrapper)
        self.content_layout.setSpacing(0)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        # Add all section widgets to content area
        self.section_widgets = {}
        for tab_widget, display_name in self.sections:
            tab_widget.hide()
            self.content_layout.addWidget(tab_widget)
            self.section_widgets[display_name] = tab_widget

        main_layout_h.addWidget(self.content_wrapper)
        self.setLayout(main_layout_h)

        # Show first section by default
        self.show_section("MIDIswitch")

    def show_section(self, section_name):
        """Show the specified section and update tab button states"""
        # Hide all section widgets
        for widget in self.section_widgets.values():
            widget.hide()

        # Uncheck all tab buttons
        for btn in self.side_tab_buttons.values():
            btn.setChecked(False)

        # Show the selected section widget and check its tab button
        if section_name in self.section_widgets:
            self.section_widgets[section_name].show()
            if section_name in self.side_tab_buttons:
                self.side_tab_buttons[section_name].setChecked(True)

    def on_keycode_changed(self, code):
        self.keycode_changed.emit(code)

    def recreate_buttons(self, keycode_filter):
        self.current_keycode_filter = keycode_filter

        # Store currently selected section before recreating
        current_section = None
        for section_name, widget in self.section_widgets.items():
            if widget.isVisible():
                current_section = section_name
                break

        # Recreate buttons for each tab
        for tab_widget, display_name in self.sections:
            tab_widget.recreate_buttons(keycode_filter)

        # Restore the previously selected section, or default to first
        if current_section and current_section in self.section_widgets:
            self.show_section(current_section)
        else:
            self.show_section("MIDIswitch")

    def has_buttons(self):
        return any(tab.has_buttons() for tab, _ in self.sections)

    def relabel_buttons(self):
        for tab_widget, _ in self.sections:
            tab_widget.relabel_buttons()


class MIDITab(midiadvancedTab):
    """The "Advanced" tab: all MIDI advanced sections plus the DAW, DrumLIVE,
    Arpeggiator, Step Sequencer and Delay sections as side tabs."""

    _STD_SECTIONS = ["Channel", "CC Options", "Transposition", "KeySplit",
                     "Advanced MIDI", "Velocity", "In/Out", "Touch Dial", "Presets"]

    def __init__(self, parent, label="Advanced", include_sections=None, with_external=True):
        external = []
        if with_external:
            self.daw_tab = DAWTab(parent)
            self.drumlive_tab = DrumLIVETab(parent, "DrumLIVE", KEYCODES_DRUMLIVE)
            self.arpeggiator_tab = ArpeggiatorTab(parent, "Arpeggiator", KEYCODES_ARPEGGIATOR, KEYCODES_ARPEGGIATOR_PRESETS)
            self.step_sequencer_tab = StepSequencerTab(parent, "Step Sequencer", KEYCODES_STEP_SEQUENCER, KEYCODES_STEP_SEQUENCER_PRESETS, KEYCODES_DRUM_SLOTS)
            self.delay_music_tab = DelayMusicTab(parent, "Delay", KEYCODES_DELAY_FACTORY, KEYCODES_DELAY_USER, KEYCODES_DELAY_CLEAR)
            external = [
                ("DAW", self.daw_tab),
                ("DrumLIVE", self.drumlive_tab),
                ("Arpeggiator", self.arpeggiator_tab),
                ("Step Sequencer", self.step_sequencer_tab),
                ("Delay", self.delay_music_tab),
            ]
        if include_sections is None:
            include_sections = list(self._STD_SECTIONS)
        super().__init__(parent, label, KEYCODES_MIDI_ADVANCED, KEYCODES_Program_Change,
                        KEYCODES_MIDI_BANK_LSB, KEYCODES_MIDI_BANK_MSB, KEYCODES_MIDI_CC,
                        KEYCODES_MIDI_CC_FIXED, KEYCODES_MIDI_CC_UP, KEYCODES_MIDI_CC_DOWN,
                        KEYCODES_VELOCITY_STEPSIZE, KEYCODES_CC_STEPSIZE, KEYCODES_MIDI_CHANNEL,
                        KEYCODES_MIDI_VELOCITY, KEYCODES_MIDI_CHANNEL_OS, KEYCODES_MIDI_CHANNEL_HOLD,
                        KEYCODES_MIDI_TRANSPOSE_SELECT, [], KEYCODES_MIDI_VELOCITY2,
                        KEYCODES_MIDI_VELOCITY3, KEYCODES_MIDI_KEY2, KEYCODES_MIDI_KEY3,
                        KEYCODES_MIDI_OCTAVE2, KEYCODES_MIDI_OCTAVE3, KEYCODES_MIDI_CHANNEL_KEYSPLIT,
                        KEYCODES_MIDI_CHANNEL_KEYSPLIT2, KEYCODES_MIDI_SPLIT_BUTTONS,
                        KEYCODES_CC_ENCODERVALUE, KEYCODES_VELOCITY_SHUFFLE, KEYCODES_EXWHEEL,
                        KEYCODES_SETTINGS1, KEYCODES_SETTINGS2, KEYCODES_SETTINGS3,
                        include_sections=include_sections, external_sections=external)
        self.label = label

    def set_keyboard(self, keyboard):
        """Fetch configured user arp/seq preset counts so those sections show
        only configured slots. keyboard may be None (no device)."""
        self.keyboard = keyboard
        counts = None
        if keyboard is not None and hasattr(keyboard, 'get_arp_seq_used'):
            try:
                counts = keyboard.get_arp_seq_used()
            except Exception:
                counts = None
        arp_used, seq_used = counts if counts else (0, 0)
        if hasattr(self, 'arpeggiator_tab'):
            self.arpeggiator_tab.set_user_count(arp_used)
        if hasattr(self, 'step_sequencer_tab'):
            self.step_sequencer_tab.set_user_count(seq_used)

    def set_editors(self, macro_recorder=None, tap_dance_editor=None, dks_settings=None, toggle_settings=None, delay_settings=None):
        """Delay editor reports how many user delay slots are configured."""
        if (delay_settings is not None and hasattr(delay_settings, '_visible_tab_count')
                and hasattr(self, 'delay_music_tab')):
            self.delay_music_tab.set_button_count(max(0, delay_settings._visible_tab_count))


class SearchTab(MIDITab):
    """Top-level Search tab: the searchable browser over every keycode."""

    def __init__(self, parent):
        super().__init__(parent, label="Search",
                         include_sections=["Advanced Keys"], with_external=False)


# =============================================================================
# DAW (Digital Audio Workstation) Shortcut Tabs
# =============================================================================

class DAWTab(QScrollArea):
    """Unified DAW shortcut tab - one set of keycodes that adapt to the selected DAW"""

    keycode_changed = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.label = "DAW"
        self.keycodes = KEYCODES_DAW
        self.buttons = []
        self.current_keycode_filter = None

        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setWidgetResizable(True)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(10, 10, 10, 10)
        self.container_layout.setSpacing(15)

        self.setWidget(self.container)

    def recreate_buttons(self, keycode_filter):
        self.current_keycode_filter = keycode_filter

        # Clear existing buttons
        for btn in self.buttons:
            btn.setParent(None)
            btn.deleteLater()
        self.buttons.clear()

        # Clear layout
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub_item = item.layout().takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()

        # 3 rows, each row is a group box with all its buttons in a horizontal flow
        # None entries insert a 50px spacer to visually separate sub-sections
        rows = [
            ("DAW Selector / Transport", [
                "DAW_SELECT", "DAW_PREV", "DAW_OS",
                None,
                "DAW_PLAY", "DAW_STOP", "DAW_RECORD", "DAW_LOOP", "DAW_REWIND", "DAW_METRONOME",
            ]),
            ("Editing / Track Control", [
                "DAW_UNDO", "DAW_REDO", "DAW_CUT", "DAW_COPY", "DAW_PASTE", "DAW_DUPLICATE", "DAW_DELETE", "DAW_SPLIT", "DAW_QUANTIZE", "DAW_JOIN", "DAW_SELECT_ALL",
                None,
                "DAW_SOLO", "DAW_MUTE", "DAW_ARM", "DAW_TRACK_UP", "DAW_TRACK_DOWN", "DAW_NEW_TRACK", "DAW_GROUP",
            ]),
            ("Navigation / Views / File", [
                "DAW_ZOOM_IN", "DAW_ZOOM_OUT", "DAW_ZOOM_FIT",
                None,
                "DAW_MIXER", "DAW_BROWSER", "DAW_PIANO_ROLL", "DAW_AUTOMATION",
                None,
                "DAW_SAVE", "DAW_SAVE_AS", "DAW_EXPORT",
            ]),
        ]

        group_box_style = """
            QGroupBox {
                font-weight: bold;
                border: 1px solid palette(mid);
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """

        # Build a fast lookup from qmk_id to Keycode object
        kc_lookup = {kc.qmk_id: kc for kc in self.keycodes}

        for row_label, kc_ids in rows:
            group = QGroupBox(row_label)
            group.setStyleSheet(group_box_style)
            flow = FlowLayout()
            flow.setSpacing(4)
            group.setLayout(flow)
            has_buttons = False

            for kc_id in kc_ids:
                if kc_id is None:
                    # Insert a 50px spacer to separate sub-sections
                    spacer = QWidget()
                    spacer.setFixedWidth(50)
                    spacer.setFixedHeight(1)
                    flow.addWidget(spacer)
                    continue

                kc = kc_lookup.get(kc_id)
                if kc is None:
                    continue
                if keycode_filter and not keycode_filter(kc.qmk_id):
                    continue

                btn = SquareButton()
                btn.setRelSize(KEYCODE_BTN_RATIO)
                btn.setToolTip(kc.tooltip)
                btn.clicked.connect(lambda _, k=kc: self.keycode_changed.emit(k.qmk_id))
                btn.keycode = kc
                self.buttons.append(btn)
                flow.addWidget(btn)
                has_buttons = True

            if has_buttons:
                self.container_layout.addWidget(group)

        self.container_layout.addStretch(1)
        self.relabel_buttons()

    def relabel_buttons(self):
        KeycodeDisplay.relabel_buttons(self.buttons)

    def has_buttons(self):
        return len(self.buttons) > 0


class FilteredTabbedKeycodes(QTabWidget):

    keycode_changed = pyqtSignal(str)
    anykey = pyqtSignal()

    def __init__(self, parent=None, keycode_filter=keycode_filter_any):
        super().__init__(parent)

        self.keycode_filter = keycode_filter

        self.tabs = [
            KeyboardTab(self),
            MusicTab(self),
            MIDITab(self),
            SearchTab(self),
            SimpleTab(self, " ", KEYCODES_CLEAR),
        ]

        for tab in self.tabs:
            tab.keycode_changed.connect(self.on_keycode_changed)

        self.recreate_keycode_buttons()
        KeycodeDisplay.notify_keymap_override(self)

    def on_keycode_changed(self, code):
        if code == "Any":
            self.anykey.emit()
        else:
            self.keycode_changed.emit(Keycode.normalize(code))

    def recreate_keycode_buttons(self):
        prev_tab = self.tabText(self.currentIndex()) if self.currentIndex() >= 0 else ""
        while self.count() > 0:
            self.removeTab(0)

        for tab in self.tabs:
            tab.recreate_buttons(self.keycode_filter)
            if tab.has_buttons():
                self.addTab(tab, tr("TabbedKeycodes", tab.label))
                if tab.label == prev_tab:
                    self.setCurrentIndex(self.count() - 1)

    def on_keymap_override(self):
        for tab in self.tabs:
            tab.relabel_buttons()

    def set_keyboard(self, keyboard):
        """Set keyboard reference for tabs that need it (e.g., GamingTab, MacroTab)"""
        for tab in self.tabs:
            if hasattr(tab, 'set_keyboard') and callable(tab.set_keyboard):
                tab.set_keyboard(keyboard)
            elif hasattr(tab, 'keyboard'):
                tab.keyboard = keyboard

    def set_editors(self, macro_recorder=None, tap_dance_editor=None, dks_settings=None, toggle_settings=None, delay_settings=None):
        """Set editor references for tabs that need them (e.g., MacroTab)"""
        for tab in self.tabs:
            if hasattr(tab, 'set_editors') and callable(tab.set_editors):
                tab.set_editors(macro_recorder, tap_dance_editor, dks_settings, toggle_settings, delay_settings=delay_settings)

    def refresh_macro_buttons(self):
        """Force refresh the MacroTab buttons"""
        for tab in self.tabs:
            if hasattr(tab, 'refresh_buttons') and callable(tab.refresh_buttons):
                tab.refresh_buttons()


class TabbedKeycodes(QWidget):

    keycode_changed = pyqtSignal(str)
    anykey = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.target = None
        self.is_tray = False

        self.layout = QVBoxLayout()

        # BOTH palettes (all + masked/basic) are expensive to construct
        # (thousands of buttons each), and ~8 TabbedKeycodes stacks exist at
        # startup, so neither is built until it is actually needed: the
        # palette for the current filter is created on the first showEvent
        # (i.e. the first time this widget's tab/tray becomes visible).
        # Keyboard/editor references and button-recreation requests that
        # arrive before a palette exists are recorded and replayed when it is
        # created.
        self.all_keycodes = None
        self.basic_keycodes = None
        self._current_filter = keycode_filter_any
        self._pal_kb = None
        self._pal_kb_pending = False
        self._pal_editors = None
        self._all_dirty = False
        self._basic_dirty = False

        self.setLayout(self.layout)

    def _replay_pending_state(self, palette, dirty):
        """Apply recorded keyboard/editor refs to a freshly built palette."""
        need_recreate = dirty
        if self._pal_kb_pending:
            palette.set_keyboard(self._pal_kb)
            need_recreate = True
        if self._pal_editors is not None:
            palette.set_editors(**self._pal_editors)
            need_recreate = True
        if need_recreate:
            palette.recreate_keycode_buttons()

    def _ensure_all_keycodes(self):
        """Create the full palette on first use."""
        if self.all_keycodes is not None:
            return self.all_keycodes

        self.all_keycodes = FilteredTabbedKeycodes(self)
        self.all_keycodes.keycode_changed.connect(self.keycode_changed)
        self.all_keycodes.anykey.connect(self.anykey)
        self.layout.addWidget(self.all_keycodes)
        self.all_keycodes.hide()

        self._replay_pending_state(self.all_keycodes, self._all_dirty)
        self._all_dirty = False
        return self.all_keycodes

    def _ensure_basic_keycodes(self):
        """Create the masked/basic palette on first use."""
        if self.basic_keycodes is not None:
            return self.basic_keycodes

        self.basic_keycodes = FilteredTabbedKeycodes(self, keycode_filter=keycode_filter_masked)
        self.basic_keycodes.keycode_changed.connect(self.keycode_changed)
        self.basic_keycodes.anykey.connect(self.anykey)
        self.layout.addWidget(self.basic_keycodes)
        self.basic_keycodes.hide()

        self._replay_pending_state(self.basic_keycodes, self._basic_dirty)
        self._basic_dirty = False
        return self.basic_keycodes

    def _apply_current_filter(self):
        """Build (if needed) and show the palette for the current filter,
        hiding the other one."""
        if self._current_filter == keycode_filter_masked:
            self._ensure_basic_keycodes()
            if self.all_keycodes is not None:
                self.all_keycodes.hide()
            self.basic_keycodes.show()
        else:
            self._ensure_all_keycodes()
            if self.basic_keycodes is not None:
                self.basic_keycodes.hide()
            self.all_keycodes.show()

    def showEvent(self, event):
        # First time the widget becomes visible: build the palette the
        # current filter needs. Subsequent shows are no-ops (ensure returns
        # the cached instance).
        self._apply_current_filter()
        super().showEvent(event)

    @classmethod
    def set_tray(cls, tray):
        cls.tray = tray

    @classmethod
    def open_tray(cls, target, keycode_filter=None):
        cls.tray.set_keycode_filter(keycode_filter)
        cls.tray.show()
        if cls.tray.target is not None and cls.tray.target != target:
            cls.tray.target.deselect()
        cls.tray.target = target

    @classmethod
    def close_tray(cls):
        if cls.tray.target is not None:
            cls.tray.target.deselect()
        cls.tray.target = None
        cls.tray.hide()

    def make_tray(self):
        self.is_tray = True
        TabbedKeycodes.set_tray(self)

        self.keycode_changed.connect(self.on_tray_keycode_changed)
        self.anykey.connect(self.on_tray_anykey)

    def on_tray_keycode_changed(self, kc):
        if self.target is not None:
            self.target.on_keycode_changed(kc)

    def on_tray_anykey(self):
        if self.target is not None:
            self.target.on_anykey()

    def recreate_keycode_buttons(self):
        if self.all_keycodes is not None:
            self.all_keycodes.recreate_keycode_buttons()
        else:
            self._all_dirty = True
        if self.basic_keycodes is not None:
            self.basic_keycodes.recreate_keycode_buttons()
        else:
            # Replayed when the basic palette is lazily created
            self._basic_dirty = True

    def set_keycode_filter(self, keycode_filter):
        self._current_filter = keycode_filter
        # Only materialize palettes while visible; a hidden widget defers to
        # its showEvent so startup never pays for palettes nobody is viewing.
        if self.isVisible():
            self._apply_current_filter()

    def set_keyboard(self, keyboard):
        """Set keyboard reference for all tab widgets"""
        self._pal_kb = keyboard
        self._pal_kb_pending = True
        if self.all_keycodes is not None:
            self.all_keycodes.set_keyboard(keyboard)
        if self.basic_keycodes is not None:
            self.basic_keycodes.set_keyboard(keyboard)

    def set_editors(self, macro_recorder=None, tap_dance_editor=None, dks_settings=None, toggle_settings=None, delay_settings=None):
        """Set editor references for all tab widgets"""
        self._pal_editors = dict(macro_recorder=macro_recorder, tap_dance_editor=tap_dance_editor,
                                 dks_settings=dks_settings, toggle_settings=toggle_settings,
                                 delay_settings=delay_settings)
        if self.all_keycodes is not None:
            self.all_keycodes.set_editors(macro_recorder, tap_dance_editor, dks_settings, toggle_settings, delay_settings=delay_settings)
        if self.basic_keycodes is not None:
            self.basic_keycodes.set_editors(macro_recorder, tap_dance_editor, dks_settings, toggle_settings, delay_settings=delay_settings)

    def refresh_macro_buttons(self):
        """Force refresh the macro tab buttons in all keycodes widgets"""
        if self.all_keycodes is not None:
            self.all_keycodes.refresh_macro_buttons()
        else:
            self._all_dirty = True
        if self.basic_keycodes is not None:
            self.basic_keycodes.refresh_macro_buttons()
        else:
            # A fresh instance rebuilds from current editor state anyway,
            # but mark dirty so replay recreates buttons to be safe.
            self._basic_dirty = True

