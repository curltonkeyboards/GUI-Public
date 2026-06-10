from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtWidgets import (QLineEdit, QToolButton, QWidget, QSizePolicy, QSpinBox, QComboBox,
                              QLabel, QHBoxLayout, QVBoxLayout, QCheckBox)

from constants import KEY_SIZE_RATIO
from widgets.flowlayout import FlowLayout
from widgets.combo_box import ArrowComboBox, ArrowSpinBox
from macro.macro_action import (ActionText, ActionSequence, ActionDown, ActionUp, ActionTap,
                                ActionDelay, ActionBPMDelay,
                                ActionMixingControl, MIXING_CURRENT_VALUE)
from widgets.key_widget import KeyWidget


class MacroKeyWidget(KeyWidget):
    """Custom KeyWidget that doesn't open tray - parent will handle keycode selection"""

    selected = pyqtSignal(object)  # Emits self when clicked

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_selected = False
        self.setFocusPolicy(Qt.ClickFocus)

    def mousePressEvent(self, ev):
        # Set active_key to the actual widget so KeyboardWidget draws the highlight
        if len(self.widgets) > 0:
            self.active_key = self.widgets[0]
            self.active_mask = False

        # Emit that we're selected (don't call parent which opens tray)
        self.selected.emit(self)
        self.update()  # Force repaint to show highlight
        ev.accept()

    def mouseReleaseEvent(self, ev):
        # Override to prevent any tray behavior
        ev.accept()

    def set_selected(self, selected):
        """Visual feedback for selection"""
        self.is_selected = selected
        if selected:
            # Set active_key to show native KeyboardWidget highlighting
            if len(self.widgets) > 0:
                self.active_key = self.widgets[0]
                self.active_mask = False
        else:
            # Clear active_key to remove highlighting
            self.active_key = None
        self.update()

    def keyReleaseEvent(self, ev):
        # remove this keycode from the sequence when delete is pressed
        if ev.key() == Qt.Key_Delete:
            self.set_keycode(0)


class DeletableKeyWidget(MacroKeyWidget):
    """MacroKeyWidget with a small red X overlay at top-right for removal"""

    remove_clicked = pyqtSignal(object)  # Emits self when X is clicked

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Small red X button overlaid at top-right
        self.btn_x = QToolButton(self)
        self.btn_x.setText("\u00d7")
        self.btn_x.setFixedSize(14, 14)
        self.btn_x.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_x.setStyleSheet("""
            QToolButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 3px;
                font-weight: bold;
                font-size: 9px;
                padding: 0px;
            }
            QToolButton:hover { background-color: #c82333; }
        """)
        self.btn_x.clicked.connect(lambda: self.remove_clicked.emit(self))
        self.btn_x.raise_()
        self._position_x_button()

    def _position_x_button(self):
        """Position X button at top-right using the widget's width/height attributes"""
        # KeyboardWidget stores size in self.width (int attribute), not QWidget.width() method
        w = self.width if isinstance(self.width, int) else 40
        self.btn_x.move(max(0, w - self.btn_x.width() - 1), 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_x_button()

    def set_keycode(self, kc):
        super().set_keycode(kc)
        # Reposition after keycode change may resize the widget
        self._position_x_button()


class BasicActionUI(QObject):

    changed = pyqtSignal()
    key_selected = pyqtSignal(object)  # Emits the selected key widget
    actcls = None

    def __init__(self, container, act=None):
        super().__init__()
        self.container = container
        if act is None:
            act = self.actcls()
        if not isinstance(act, self.actcls):
            raise RuntimeError("{} was initialized with {}, expecting {}".format(self, act, self.actcls))
        self.act = act

    def set_keycode_filter(self, keycode_filter):
        pass


class ActionTextUI(BasicActionUI):

    actcls = ActionText

    def __init__(self, container, act=None):
        super().__init__(container, act)
        self.text = QLineEdit()
        self.text.setText(self.act.text)
        self.text.textChanged.connect(self.on_change)

    def insert(self, row):
        self.container.addWidget(self.text, row, 3)

    def remove(self):
        self.container.removeWidget(self.text)

    def delete(self):
        self.text.deleteLater()

    def on_change(self):
        self.act.text = self.text.text()
        self.changed.emit()


def _make_thruloop_combo():
    """Create a combo box styled like ThruLoop dropdowns - restricted height, scrollbar"""
    combo = ArrowComboBox()
    combo.setMaximumHeight(30)
    combo.setEditable(True)
    combo.lineEdit().setReadOnly(True)
    combo.lineEdit().setAlignment(Qt.AlignCenter)
    return combo


class ActionSequenceUI(BasicActionUI):

    actcls = ActionSequence

    def __init__(self, container, act=None):
        super().__init__(container, act)

        # Square + button matching key widget size
        self.btn_plus = QToolButton()
        self.btn_plus.setText("+")
        self.btn_plus.setFixedWidth(30)
        self.btn_plus.setFixedHeight(30)
        self.btn_plus.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_plus.clicked.connect(self.on_add)

        self.layout = FlowLayout()
        self.layout_container = QWidget()
        self.layout_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.layout_container.setLayout(self.layout)
        self.widgets = []
        self.keycode_filter = None
        self.recreate_sequence()

    def set_keycode_filter(self, keycode_filter):
        if keycode_filter != self.keycode_filter:
            self.keycode_filter = keycode_filter
            for w in self.widgets:
                w.set_keycode_filter(self.keycode_filter)

    def recreate_sequence(self):
        self.layout.removeWidget(self.btn_plus)
        for w in self.widgets:
            self.layout.removeWidget(w)
            w.deleteLater()
        self.widgets.clear()

        for kc in self.act.sequence:
            w = DeletableKeyWidget(self.keycode_filter)
            w.set_keycode(kc)
            w.changed.connect(self.on_change)
            w.selected.connect(self._on_key_selected)
            w.remove_clicked.connect(self.on_remove_widget)
            self.layout.addWidget(w)
            self.widgets.append(w)
        self.layout.addWidget(self.btn_plus)

    def _on_key_selected(self, widget):
        """Handle key widget selection - bubble up to parent"""
        self.key_selected.emit(widget)

    def insert(self, row):
        self.container.addWidget(self.layout_container, row, 3)

    def remove(self):
        self.container.removeWidget(self.layout_container)

    def delete(self):
        for w in self.widgets:
            w.deleteLater()
        self.btn_plus.deleteLater()
        self.layout_container.deleteLater()

    def on_add(self):
        self.act.sequence.append("KC_TRNS")
        self.recreate_sequence()
        self.changed.emit()

    def on_remove_widget(self, widget):
        """Remove a specific keycode widget by its X button"""
        try:
            idx = self.widgets.index(widget)
            del self.act.sequence[idx]
            self.recreate_sequence()
            self.changed.emit()
        except ValueError:
            pass

    def on_change(self):
        for x in range(len(self.act.sequence)):
            if x >= len(self.widgets):
                break
            kc = self.widgets[x].keycode
            if kc == 0:
                # asked to remove this item
                del self.act.sequence[x]
                self.recreate_sequence()
                break
            else:
                self.act.sequence[x] = kc
        self.changed.emit()


class ActionDownUI(ActionSequenceUI):
    actcls = ActionDown


class ActionUpUI(ActionSequenceUI):
    actcls = ActionUp


class ActionTapUI(ActionSequenceUI):
    actcls = ActionTap


class ActionDelayUI(BasicActionUI):

    actcls = ActionDelay

    def __init__(self, container, act=None):
        super().__init__(container, act)
        self.value = ArrowSpinBox()
        self.value.setMinimum(0)
        self.value.setMaximum(64000)  # up to 64s
        self.value.setValue(self.act.delay)
        self.value.valueChanged.connect(self.on_change)

        self.layout = FlowLayout()
        self.layout_container = QWidget()
        self.layout_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.layout_container.setLayout(self.layout)

        self.layout.addWidget(self.value)

    def insert(self, row):
        self.container.addWidget(self.layout_container, row, 3)

    def remove(self):
        self.container.removeWidget(self.layout_container)

    def delete(self):
        self.value.deleteLater()
        self.layout_container.deleteLater()

    def on_change(self):
        self.act.delay = self.value.value()
        self.changed.emit()


class ActionBPMDelayUI(BasicActionUI):

    actcls = ActionBPMDelay

    # Extended note values: indices 0-4 = original (1/1..1/16), 5-8 = multi-bar (2/1..16/1)
    NOTE_DISPLAY_ORDER = [
        (8, "16/1"), (7, "8/1"), (6, "4/1"), (5, "2/1"),
        (0, "1/1"), (1, "1/2"), (2, "1/4"), (3, "1/8"), (4, "1/16")
    ]

    def __init__(self, container, act=None):
        super().__init__(container, act)

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self.layout_container = QWidget()
        self.layout_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        self.layout.addWidget(QLabel("Rate:"))
        self.note_combo = _make_thruloop_combo()
        for _, label in self.NOTE_DISPLAY_ORDER:
            self.note_combo.addItem(label)
        # Find display index for current note_value
        display_idx = next((i for i, (val, _) in enumerate(self.NOTE_DISPLAY_ORDER)
                           if val == self.act.note_value), 4)  # default to 1/1
        self.note_combo.setCurrentIndex(display_idx)
        self.note_combo.setMinimumWidth(70)
        self.note_combo.currentIndexChanged.connect(self.on_note_change)
        self.layout.addWidget(self.note_combo)

        self.layout_container.setLayout(self.layout)

    def insert(self, row):
        self.container.addWidget(self.layout_container, row, 3)

    def remove(self):
        self.container.removeWidget(self.layout_container)

    def delete(self):
        self.note_combo.deleteLater()
        self.layout_container.deleteLater()

    def on_note_change(self):
        display_idx = self.note_combo.currentIndex()
        self.act.note_value = self.NOTE_DISPLAY_ORDER[display_idx][0]
        self.act.timing_mode = 0  # Always straight
        self.changed.emit()


class ActionMixingControlUI(BasicActionUI):

    actcls = ActionMixingControl

    def __init__(self, container, act=None):
        super().__init__(container, act)

        self._initializing = True  # Guard against on_change during init

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(2)
        self.layout_container = QWidget()
        self.layout_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        # CC Number
        lbl_cc = QLabel("CC#")
        self.layout.addWidget(lbl_cc)
        self.cc_spin = ArrowSpinBox()
        self.cc_spin.setMinimum(0)
        self.cc_spin.setMaximum(127)
        self.cc_spin.setValue(self.act.cc_num)
        self.cc_spin.setFixedWidth(60)
        self.cc_spin.valueChanged.connect(self.on_change)
        self.layout.addWidget(self.cc_spin)

        self.layout.addSpacing(10)

        # Channel
        lbl_ch = QLabel("Channel")
        self.layout.addWidget(lbl_ch)
        self.channel_combo = _make_thruloop_combo()
        self.channel_combo.addItem("Master Channel (default)")
        for i in range(1, 17):
            self.channel_combo.addItem(str(i))
        self.channel_combo.setCurrentIndex(self.act.channel)
        self.channel_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.channel_combo.currentIndexChanged.connect(self.on_change)
        self.layout.addWidget(self.channel_combo)

        self.layout.addSpacing(10)

        # Start value (dropdown with Live Value + 0-127)
        lbl_start = QLabel("Starting Value:")
        self.layout.addWidget(lbl_start)
        self.start_combo = _make_thruloop_combo()
        self.start_combo.addItem("Live Value")
        for i in range(128):
            self.start_combo.addItem(str(i))
        if self.act.start_val == MIXING_CURRENT_VALUE:
            self.start_combo.setCurrentIndex(0)
        else:
            self.start_combo.setCurrentIndex(self.act.start_val + 1)
        self.start_combo.setFixedWidth(80)
        self.start_combo.currentIndexChanged.connect(self.on_start_change)
        self.layout.addWidget(self.start_combo)

        self.layout.addSpacing(10)

        # End value (dropdown with conditional Live Value + 0-127)
        lbl_end = QLabel("End Value:")
        self.layout.addWidget(lbl_end)
        self.end_combo = _make_thruloop_combo()
        self._rebuild_end_combo()
        self.end_combo.setFixedWidth(80)
        self.end_combo.currentIndexChanged.connect(self.on_change)
        self.layout.addWidget(self.end_combo)

        self.layout.addSpacing(10)

        # Duration - defaults to BPM, with "Unsynced (ms)" checkbox to switch
        lbl_dur = QLabel("Duration")
        self.layout.addWidget(lbl_dur)

        # Duration value (BPM mode) - shown by default
        self.dur_note_combo = _make_thruloop_combo()
        for _, label in ActionBPMDelayUI.NOTE_DISPLAY_ORDER:
            self.dur_note_combo.addItem(label)
        self.dur_note_combo.setFixedWidth(60)
        self.dur_note_combo.currentIndexChanged.connect(self.on_change)
        self.layout.addWidget(self.dur_note_combo)

        # Duration value (ms mode) - hidden by default
        self.dur_ms_spin = ArrowSpinBox()
        self.dur_ms_spin.setMinimum(20)
        self.dur_ms_spin.setMaximum(64000)
        self.dur_ms_spin.setSingleStep(100)
        if self.act.duration_type == 0:
            self.dur_ms_spin.setValue(self.act.duration)
        else:
            self.dur_ms_spin.setValue(1000)
        self.dur_ms_spin.setFixedWidth(75)
        self.dur_ms_spin.valueChanged.connect(self.on_change)
        self.layout.addWidget(self.dur_ms_spin)

        self.dur_ms_cb = QCheckBox("Unsynced (ms)")
        self.dur_ms_cb.stateChanged.connect(self._on_dur_ms_toggle)
        self.layout.addWidget(self.dur_ms_cb)

        # Push everything left so widgets don't stretch across the row
        self.layout.addStretch()

        # Restore BPM params if in BPM mode
        if self.act.duration_type == 1:
            note_val = (self.act.duration >> 8) & 0xFF
            display_idx = next((i for i, (val, _) in enumerate(ActionBPMDelayUI.NOTE_DISPLAY_ORDER)
                               if val == note_val), 4)
            self.dur_note_combo.setCurrentIndex(display_idx)
            self.dur_ms_cb.setChecked(False)
        else:
            # ms mode - check the box
            self.dur_ms_cb.setChecked(True)

        # Default BPM note to 1/1 for new actions (index 4 in NOTE_DISPLAY_ORDER)
        if not act:
            self.dur_note_combo.setCurrentIndex(4)

        self._update_dur_visibility()
        self.layout_container.setLayout(self.layout)
        self._initializing = False

    def _rebuild_end_combo(self):
        """Rebuild end combo - 'Live Value' not allowed if start is 'Live Value'"""
        self.end_combo.blockSignals(True)
        old_val = self.act.end_val
        self.end_combo.clear()
        start_is_current = (self.start_combo.currentIndex() == 0)
        if not start_is_current:
            self.end_combo.addItem("Live Value")
        for i in range(128):
            self.end_combo.addItem(str(i))
        # Restore selection
        if start_is_current:
            idx = min(old_val, 127)
            self.end_combo.setCurrentIndex(idx)
        else:
            if old_val == MIXING_CURRENT_VALUE:
                self.end_combo.setCurrentIndex(0)
            else:
                self.end_combo.setCurrentIndex(old_val + 1)
        self.end_combo.blockSignals(False)

    def _update_dur_visibility(self):
        is_ms = self.dur_ms_cb.isChecked()
        self.dur_ms_spin.setVisible(is_ms)
        self.dur_note_combo.setVisible(not is_ms)

    def on_start_change(self):
        self._rebuild_end_combo()
        self.on_change()

    def _on_dur_ms_toggle(self):
        self._update_dur_visibility()
        self.on_change()

    def insert(self, row):
        self.container.addWidget(self.layout_container, row, 3)

    def remove(self):
        self.container.removeWidget(self.layout_container)

    def delete(self):
        self.cc_spin.deleteLater()
        self.channel_combo.deleteLater()
        self.start_combo.deleteLater()
        self.end_combo.deleteLater()
        self.dur_ms_cb.deleteLater()
        self.dur_ms_spin.deleteLater()
        self.dur_note_combo.deleteLater()
        self.layout_container.deleteLater()

    def on_change(self):
        if self._initializing:
            return

        self.act.cc_num = self.cc_spin.value()
        self.act.channel = self.channel_combo.currentIndex()

        # Start value
        if self.start_combo.currentIndex() == 0:
            self.act.start_val = MIXING_CURRENT_VALUE
        else:
            self.act.start_val = self.start_combo.currentIndex() - 1

        # End value
        start_is_current = (self.start_combo.currentIndex() == 0)
        if start_is_current:
            self.act.end_val = self.end_combo.currentIndex()
        else:
            if self.end_combo.currentIndex() == 0:
                self.act.end_val = MIXING_CURRENT_VALUE
            else:
                self.act.end_val = self.end_combo.currentIndex() - 1

        # Duration
        if self.dur_ms_cb.isChecked():
            self.act.duration_type = 0
            self.act.duration = self.dur_ms_spin.value()
        else:
            self.act.duration_type = 1
            display_idx = self.dur_note_combo.currentIndex()
            note_val = ActionBPMDelayUI.NOTE_DISPLAY_ORDER[display_idx][0]
            self.act.duration = (note_val << 8) | 0

        self.changed.emit()


tag_to_action = {
    "down": ActionDown,
    "up": ActionUp,
    "tap": ActionTap,
    "text": ActionText,
    "delay": ActionDelay,
    "bpm_delay": ActionBPMDelay,
    "bpm_delay_repeat": ActionBPMDelay,  # Convert old repeat type to plain BPM delay
    "mixing_control": ActionMixingControl,
}

ui_action = {
    ActionText: ActionTextUI,
    ActionUp: ActionUpUI,
    ActionDown: ActionDownUI,
    ActionTap: ActionTapUI,
    ActionDelay: ActionDelayUI,
    ActionBPMDelay: ActionBPMDelayUI,
    ActionMixingControl: ActionMixingControlUI,
}
