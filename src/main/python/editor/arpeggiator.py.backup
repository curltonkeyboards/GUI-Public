# SPDX-License-Identifier: GPL-2.0-or-later
import struct
import logging
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen, QFont
from PyQt5.QtWidgets import (QWidget, QPushButton, QHBoxLayout, QVBoxLayout,
                             QLabel, QGroupBox, QMessageBox, QGridLayout,
                             QComboBox, QSpinBox, QLineEdit, QScrollArea,
                             QFrame, QButtonGroup, QRadioButton, QCheckBox, QSlider,
                             QInputDialog)

from editor.basic_editor import BasicEditor
from util import tr
from vial_device import VialKeyboard
from widgets.combo_box import ArrowComboBox

logger = logging.getLogger(__name__)


class IntervalSelector(QWidget):
    """Custom interval selector with +/- buttons and editable value box"""

    valueChanged = pyqtSignal(int)

    # Interval names mapping (extended range)
    INTERVAL_NAMES = {
        -1: "Empty",
        0: "Root Note",
        1: "Minor Second",
        2: "Major Second",
        3: "Minor Third",
        4: "Major Third",
        5: "Perfect Fourth",
        6: "Tritone",
        7: "Perfect Fifth",
        8: "Minor Sixth",
        9: "Major Sixth",
        10: "Minor Seventh",
        11: "Major Seventh",
        12: "Octave",
        13: "Minor 9th",
        14: "Major 9th",
        15: "Minor 10th",
        16: "Major 10th",
        17: "Perfect 11th",
        18: "Augmented 11th",
        19: "Perfect 12th",
        20: "Minor 13th",
        21: "Major 13th",
        22: "Minor 14th",
        23: "Major 14th"
    }

    # Generate negative interval names (mirror positive ones)
    NEGATIVE_INTERVAL_NAMES = {
        -2: "-Major Second",
        -3: "-Minor Third",
        -4: "-Major Third",
        -5: "-Perfect Fourth",
        -6: "-Tritone",
        -7: "-Perfect Fifth",
        -8: "-Minor Sixth",
        -9: "-Major Sixth",
        -10: "-Minor Seventh",
        -11: "-Major Seventh",
        -12: "-Octave",
        -13: "-Minor 9th",
        -14: "-Major 9th",
        -15: "-Minor 10th",
        -16: "-Major 10th",
        -17: "-Perfect 11th",
        -18: "-Augmented 11th",
        -19: "-Perfect 12th",
        -20: "-Minor 13th",
        -21: "-Major 13th",
        -22: "-Minor 14th",
        -23: "-Major 14th"
    }

    # Combine mappings
    INTERVAL_NAMES.update(NEGATIVE_INTERVAL_NAMES)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = -1  # Default to None

        layout = QVBoxLayout()
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        # Interval name label (above the box)
        self.name_label = QLabel("Empty")
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setFont(QFont("Arial", 9, QFont.Bold))
        layout.addWidget(self.name_label)

        # Container for the value box with integrated +/- buttons
        container = QFrame()
        container.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        container.setMaximumWidth(120)

        box_layout = QHBoxLayout()
        box_layout.setSpacing(0)
        box_layout.setContentsMargins(2, 2, 2, 2)

        # Minus button (inside container, on left)
        self.btn_minus = QPushButton("-")
        self.btn_minus.setFixedSize(25, 25)
        self.btn_minus.clicked.connect(self.decrement)
        box_layout.addWidget(self.btn_minus)

        # Value box (center)
        self.value_box = QLabel("Empty")
        self.value_box.setAlignment(Qt.AlignCenter)
        self.value_box.setMinimumWidth(50)
        box_layout.addWidget(self.value_box, 1)

        # Plus button (inside container, on right)
        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedSize(25, 25)
        self.btn_plus.clicked.connect(self.increment)
        box_layout.addWidget(self.btn_plus)

        container.setLayout(box_layout)
        layout.addWidget(container, 0, Qt.AlignCenter)
        self.setLayout(layout)

        self.update_display()

    def get_value(self):
        """Get current interval value"""
        return self.value

    def set_value(self, value):
        """Set interval value"""
        # Clamp to valid range (-23 to +23)
        if value < -23:
            value = -23
        elif value > 23:
            value = 23

        if self.value != value:
            self.value = value
            self.update_display()
            self.valueChanged.emit(self.value)

    def increment(self):
        """Increment interval value"""
        if self.value < 23:
            self.set_value(self.value + 1)

    def decrement(self):
        """Decrement interval value"""
        if self.value > -23:
            self.set_value(self.value - 1)

    def update_display(self):
        """Update the display text"""
        # Update interval name
        self.name_label.setText(self.INTERVAL_NAMES.get(self.value, "Unknown"))

        # Update value box
        if self.value == -1:
            self.value_box.setText("Empty")
        elif self.value >= 0:
            self.value_box.setText(f"+{self.value}")
        else:
            self.value_box.setText(str(self.value))

        # Enable/disable buttons
        self.btn_minus.setEnabled(self.value > -23)
        self.btn_plus.setEnabled(self.value < 23)


class NoteSelector(QWidget):
    """Note selector for step sequencer (C-B dropdown)"""

    valueChanged = pyqtSignal(int)

    # Note names
    NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0  # Default to C

        layout = QVBoxLayout()
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        # Note dropdown
        self.combo_note = ArrowComboBox()
        self.combo_note.setEditable(True)
        self.combo_note.lineEdit().setReadOnly(True)
        self.combo_note.lineEdit().setAlignment(Qt.AlignCenter)
        self.combo_note.setMinimumWidth(60)
        for i, note_name in enumerate(self.NOTE_NAMES):
            self.combo_note.addItem(note_name, i)
        self.combo_note.currentIndexChanged.connect(self.on_value_changed)
        layout.addWidget(self.combo_note)

        self.setLayout(layout)

    def get_value(self):
        """Get current note value (0-11)"""
        return self.value

    def set_value(self, value):
        """Set note value (0-11)"""
        if value < 0:
            value = 0
        elif value > 11:
            value = 11

        if self.value != value:
            self.value = value
            self.combo_note.setCurrentIndex(value)
            self.valueChanged.emit(self.value)

    def on_value_changed(self, index):
        """Combo box selection changed"""
        if index >= 0:
            self.value = index
            self.valueChanged.emit(self.value)


class OctaveSelector(QWidget):
    """Custom octave selector with +/- buttons"""

    valueChanged = pyqtSignal(int)

    def __init__(self, min_octave=-2, max_octave=2, default_octave=0, parent=None):
        super().__init__(parent)
        self.min_octave = min_octave
        self.max_octave = max_octave
        self.value = default_octave  # Default

        layout = QVBoxLayout()
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        # Container for the value box with integrated +/- buttons
        container = QFrame()
        container.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        container.setMaximumWidth(120)

        box_layout = QHBoxLayout()
        box_layout.setSpacing(0)
        box_layout.setContentsMargins(2, 2, 2, 2)

        # Minus button (inside container, on left)
        self.btn_minus = QPushButton("-")
        self.btn_minus.setFixedSize(25, 25)
        self.btn_minus.clicked.connect(self.decrement)
        box_layout.addWidget(self.btn_minus)

        # Value box (center)
        self.value_box = QLabel("0")
        self.value_box.setAlignment(Qt.AlignCenter)
        self.value_box.setMinimumWidth(50)
        box_layout.addWidget(self.value_box, 1)

        # Plus button (inside container, on right)
        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedSize(25, 25)
        self.btn_plus.clicked.connect(self.increment)
        box_layout.addWidget(self.btn_plus)

        container.setLayout(box_layout)
        layout.addWidget(container, 0, Qt.AlignCenter)
        self.setLayout(layout)

        self.update_display()

    def get_value(self):
        """Get current octave value"""
        return self.value

    def set_value(self, value):
        """Set octave value"""
        # Clamp to valid range
        if value < self.min_octave:
            value = self.min_octave
        elif value > self.max_octave:
            value = self.max_octave

        if self.value != value:
            self.value = value
            self.update_display()
            self.valueChanged.emit(self.value)

    def increment(self):
        """Increment octave value"""
        if self.value < self.max_octave:
            self.set_value(self.value + 1)

    def decrement(self):
        """Decrement octave value"""
        if self.value > self.min_octave:
            self.set_value(self.value - 1)

    def update_display(self):
        """Update the display text"""
        # Update value box with + or - prefix (for arpeggiator) or absolute (for step seq)
        if self.min_octave < 0:
            # Arpeggiator mode (relative octaves)
            if self.value > 0:
                self.value_box.setText(f"+{self.value}")
            else:
                self.value_box.setText(str(self.value))
        else:
            # Step sequencer mode (absolute octaves)
            self.value_box.setText(str(self.value))

        # Enable/disable buttons
        self.btn_minus.setEnabled(self.value > self.min_octave)
        self.btn_plus.setEnabled(self.value < self.max_octave)


class VelocityBar(QWidget):
    """Interactive velocity bar for step sequencer - click height sets velocity"""

    clicked = pyqtSignal(int)  # Emits velocity value 0-255

    def __init__(self, parent=None):
        super().__init__(parent)
        self.velocity = 200  # Default velocity
        self.setMinimumSize(30, 120)
        self.setMaximumSize(40, 150)
        self.setSizePolicy(self.sizePolicy().Minimum, self.sizePolicy().Expanding)

    def set_velocity(self, velocity):
        """Set velocity value (0-255)"""
        self.velocity = max(0, min(255, velocity))
        self.update()

    def get_velocity(self):
        """Get current velocity"""
        return self.velocity

    def paintEvent(self, event):
        from PyQt5.QtGui import QPalette

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get theme colors from palette
        palette = self.palette()
        bg_color = palette.color(QPalette.Window)
        highlight_color = palette.color(QPalette.Highlight)

        # Background
        painter.fillRect(self.rect(), bg_color.darker(120))

        # Border
        painter.setPen(QPen(palette.color(QPalette.Mid), 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        # Velocity bar with theme highlight color
        if self.velocity > 0:
            bar_height = int((self.velocity / 255.0) * self.height())
            bar_y = self.height() - bar_height

            # Use theme highlight color with intensity based on velocity
            intensity = self.velocity / 255.0
            color = QColor(
                int(highlight_color.red() * (0.5 + 0.5 * intensity)),
                int(highlight_color.green() * (0.5 + 0.5 * intensity)),
                int(highlight_color.blue() * (0.5 + 0.5 * intensity))
            )

            painter.fillRect(1, bar_y, self.width() - 2, bar_height, color)

        # Velocity text (display half the value, rounded down)
        painter.setPen(palette.color(QPalette.Text))
        painter.setFont(QFont("Arial", 8))
        painter.drawText(self.rect(), Qt.AlignCenter, str(self.velocity // 2))

    def mousePressEvent(self, event):
        """Click to set velocity based on Y position"""
        if event.button() == Qt.LeftButton:
            # Invert Y (top = high velocity, bottom = low)
            relative_y = event.pos().y() / self.height()
            velocity = int((1.0 - relative_y) * 255)
            self.set_velocity(velocity)
            self.clicked.emit(self.velocity)

    def mouseMoveEvent(self, event):
        """Drag to set velocity based on Y position"""
        if event.buttons() & Qt.LeftButton:
            # Invert Y (top = high velocity, bottom = low)
            relative_y = max(0, min(1, event.pos().y() / self.height()))
            velocity = int((1.0 - relative_y) * 255)
            self.set_velocity(velocity)
            self.clicked.emit(self.velocity)


class NoteContainer(QFrame):
    """Single note within a step - contains velocity bar, note/interval selector, and octave selector"""

    removed = pyqtSignal()  # Signal when this note should be removed

    def __init__(self, is_step_sequencer=False, parent=None):
        super().__init__(parent)
        self.is_step_sequencer = is_step_sequencer

        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(2, 2, 2, 2)

        # Velocity bar with label below
        velocity_container = QWidget()
        velocity_full_layout = QVBoxLayout()
        velocity_full_layout.setContentsMargins(0, 0, 0, 0)
        velocity_full_layout.setSpacing(2)
        velocity_container.setLayout(velocity_full_layout)

        # Velocity bar centered
        velocity_bar_container = QWidget()
        velocity_bar_layout = QHBoxLayout()
        velocity_bar_layout.setContentsMargins(0, 0, 0, 0)
        velocity_bar_container.setLayout(velocity_bar_layout)

        velocity_bar_layout.addStretch()
        self.velocity_bar = VelocityBar()
        velocity_bar_layout.addWidget(self.velocity_bar)
        velocity_bar_layout.addStretch()

        velocity_full_layout.addWidget(velocity_bar_container, 1)

        # Velocity label
        velocity_label = QLabel("Velocity")
        velocity_label.setAlignment(Qt.AlignCenter)
        velocity_label.setFont(QFont("Arial", 8))
        velocity_full_layout.addWidget(velocity_label)

        layout.addWidget(velocity_container, 1)

        # Note/Interval selector
        if self.is_step_sequencer:
            # Step sequencer: absolute note selector (C-B)
            note_label = QLabel("Note")
            note_label.setAlignment(Qt.AlignCenter)
            note_label.setFont(QFont("Arial", 9, QFont.Bold))
            layout.addWidget(note_label)

            note_group = QGroupBox()
            note_layout = QVBoxLayout()
            note_layout.setContentsMargins(4, 4, 4, 4)
            self.note_selector = NoteSelector()
            note_layout.addWidget(self.note_selector)
            note_group.setLayout(note_layout)
            layout.addWidget(note_group)

            # Octave selector (0-7 for step sequencer)
            octave_label = QLabel("Octave")
            octave_label.setAlignment(Qt.AlignCenter)
            octave_label.setFont(QFont("Arial", 9, QFont.Bold))
            layout.addWidget(octave_label)

            octave_group = QGroupBox()
            octave_layout = QVBoxLayout()
            octave_layout.setContentsMargins(4, 4, 4, 4)
            self.octave_selector = OctaveSelector(min_octave=0, max_octave=7, default_octave=4)
            octave_layout.addWidget(self.octave_selector)
            octave_group.setLayout(octave_layout)
            layout.addWidget(octave_group)
        else:
            # Arpeggiator: interval selector (-24 to +24)
            interval_label = QLabel("Interval")
            interval_label.setAlignment(Qt.AlignCenter)
            interval_label.setFont(QFont("Arial", 9, QFont.Bold))
            layout.addWidget(interval_label)

            interval_group = QGroupBox()
            interval_layout = QVBoxLayout()
            interval_layout.setContentsMargins(4, 4, 4, 4)
            self.interval_selector = IntervalSelector()
            interval_layout.addWidget(self.interval_selector)
            interval_group.setLayout(interval_layout)
            layout.addWidget(interval_group)

            # Octave selector (-2 to +2 for arpeggiator)
            octave_label = QLabel("Octave")
            octave_label.setAlignment(Qt.AlignCenter)
            octave_label.setFont(QFont("Arial", 9, QFont.Bold))
            layout.addWidget(octave_label)

            octave_group = QGroupBox()
            octave_layout = QVBoxLayout()
            octave_layout.setContentsMargins(4, 4, 4, 4)
            self.octave_selector = OctaveSelector(min_octave=-2, max_octave=2, default_octave=0)
            octave_layout.addWidget(self.octave_selector)
            octave_group.setLayout(octave_layout)
            layout.addWidget(octave_group)

        # Remove button
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setStyleSheet("QPushButton { min-height: 25px; max-height: 25px; }")
        self.btn_remove.clicked.connect(self.removed.emit)
        layout.addWidget(self.btn_remove)

        self.setLayout(layout)
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(1)

    def get_note_data(self):
        """Return note data as dict"""
        data = {
            'velocity': self.velocity_bar.get_velocity(),
            'octave_offset': self.octave_selector.get_value()
        }

        if self.is_step_sequencer:
            data['note_index'] = self.note_selector.get_value()
        else:
            data['semitone_offset'] = self.interval_selector.get_value()

        return data

    def set_note_data(self, data):
        """Load note data from dict"""
        if 'velocity' in data:
            self.velocity_bar.set_velocity(data['velocity'])
        if 'octave_offset' in data:
            self.octave_selector.set_value(data['octave_offset'])

        if self.is_step_sequencer:
            if 'note_index' in data:
                self.note_selector.set_value(data['note_index'])
        else:
            if 'semitone_offset' in data:
                self.interval_selector.set_value(data['semitone_offset'])


class StepWidget(QFrame):
    """Single step in the sequencer - can contain multiple notes (up to 8)"""

    def __init__(self, step_num, is_step_sequencer=False, parent=None):
        super().__init__(parent)
        self.step_num = step_num
        self.is_step_sequencer = is_step_sequencer
        self.note_containers = []

        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # Step number label
        lbl_step = QLabel(f"Step {step_num + 1}")
        lbl_step.setAlignment(Qt.AlignCenter)
        lbl_step.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(lbl_step)

        # "Add Note" button
        self.btn_add_note = QPushButton("Add Note")
        self.btn_add_note.setStyleSheet("QPushButton { min-height: 30px; max-height: 30px; }")
        self.btn_add_note.clicked.connect(self.add_note)
        layout.addWidget(self.btn_add_note)

        # Scroll area for note containers
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setMinimumHeight(150)

        # Container for notes
        self.notes_container = QWidget()
        self.notes_layout = QVBoxLayout()
        self.notes_layout.setSpacing(4)
        self.notes_layout.setContentsMargins(0, 0, 0, 0)
        self.notes_container.setLayout(self.notes_layout)
        scroll_area.setWidget(self.notes_container)

        layout.addWidget(scroll_area, 1)

        self.setLayout(layout)
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(2)

    def add_note(self):
        """Add a new note container to this step"""
        if len(self.note_containers) >= 8:
            QMessageBox.warning(None, "Maximum Notes", "Maximum 8 notes per step reached")
            return

        note_container = NoteContainer(is_step_sequencer=self.is_step_sequencer)
        note_container.removed.connect(lambda: self.remove_note(note_container))
        self.note_containers.append(note_container)
        self.notes_layout.addWidget(note_container)

        # Update button state
        self.btn_add_note.setEnabled(len(self.note_containers) < 8)

    def remove_note(self, note_container):
        """Remove a note container from this step"""
        if note_container in self.note_containers:
            self.note_containers.remove(note_container)
            self.notes_layout.removeWidget(note_container)
            note_container.deleteLater()

        # Update button state
        self.btn_add_note.setEnabled(len(self.note_containers) < 8)

    def get_step_data(self):
        """Return step data as list of note dicts"""
        notes = []
        for container in self.note_containers:
            notes.append(container.get_note_data())
        return notes

    def set_step_data(self, notes_data):
        """Load step data from list of note dicts"""
        # Clear existing notes
        for container in self.note_containers[:]:
            self.remove_note(container)

        # Add notes from data
        for note_data in notes_data:
            self.add_note()
            if self.note_containers:
                self.note_containers[-1].set_note_data(note_data)


class Arpeggiator(BasicEditor):
    """Arpeggiator tab for creating and managing arpeggiator presets"""

    # HID Command constants for arpeggiator
    ARP_CMD_GET_PRESET = 0xC0
    ARP_CMD_SET_PRESET = 0xC1
    ARP_CMD_SAVE_PRESET = 0xC2
    ARP_CMD_LOAD_PRESET = 0xC3
    ARP_CMD_CLEAR_PRESET = 0xC4
    ARP_CMD_COPY_PRESET = 0xC5
    ARP_CMD_RESET_ALL = 0xC6
    ARP_CMD_GET_STATE = 0xC7
    ARP_CMD_SET_STATE = 0xC8
    ARP_CMD_GET_INFO = 0xC9

    MANUFACTURER_ID = 0x7D
    SUB_ID = 0x00
    DEVICE_ID = 0x4D

    # Signals
    hid_data_received = pyqtSignal(bytes)

    def __init__(self):
        super().__init__()

        logger.info("Arpeggiator tab initialized")

        self.current_preset_id = 0  # Presets 0-31 for arpeggiator
        self.is_step_sequencer = False  # This is the arpeggiator tab
        self.preset_data = {
            'name': 'User Preset',
            'preset_type': 0,  # PRESET_TYPE_ARPEGGIATOR
            'note_count': 0,
            'pattern_length_64ths': 64,
            'gate_length_percent': 80,
            'steps': []
        }

        # Initialize with 4 default empty steps
        for i in range(4):
            self.preset_data['steps'].append([])  # Empty list of notes per step

        self.step_widgets = []
        self.clipboard_preset = None  # Internal clipboard for copy/paste
        self.hid_data_received.connect(self.handle_hid_response)

        self.setup_ui()

    def setup_ui(self):
        """Build the UI"""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(0)

        # === Status ===
        self.lbl_status = QLabel("Ready. Select a preset to begin.")
        self.lbl_status.setStyleSheet("color: #00aaff; padding: 5px;")
        # === Header Section ===
        header_layout = QHBoxLayout()

        # Preset selector
        preset_group = QGroupBox("Preset")
        preset_layout = QGridLayout()

        # === Sequencer Section ===
        sequencer_group = QGroupBox("Step Sequencer")

        # Create scrollable area for steps
        self.step_scroll = QScrollArea()
        self.step_scroll.setWidgetResizable(True)
        self.step_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.step_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.step_scroll.setMinimumHeight(300)

        self.step_container = QWidget()
        self.step_layout = QHBoxLayout()
        self.step_layout.setSpacing(2)
        self.step_layout.setDirection(QHBoxLayout.LeftToRight)  # Ensure left-to-right
        self.step_container.setLayout(self.step_layout)
        self.step_scroll.setWidget(self.step_container)

        sequencer_layout = QVBoxLayout()
        sequencer_layout.addWidget(self.step_scroll)
        sequencer_group.setLayout(sequencer_layout)

        main_layout.addWidget(sequencer_group, 1)

        # === Bottom Section: Two containers side by side ===
        bottom_layout = QHBoxLayout()

        # Add left spacer to push containers closer together
        bottom_layout.addStretch(1)

        # Left Container: Preset Parameters (no title)
        params_group = QGroupBox()
        params_group.setMaximumWidth(500)
        params_layout = QGridLayout()

        # Arpeggiator Mode (moved from separate section)
        lbl_mode = QLabel("Arpeggiator Mode:")
        self.combo_mode = ArrowComboBox()
        self.combo_mode.setMinimumWidth(150)
        self.combo_mode.setMaximumHeight(30)
        self.combo_mode.setEditable(True)
        self.combo_mode.lineEdit().setReadOnly(True)
        self.combo_mode.lineEdit().setAlignment(Qt.AlignCenter)
        self.combo_mode.addItem("Single Note (Classic Arp)", 0)
        self.combo_mode.addItem("Chord Basic (All Notes)", 1)
        self.combo_mode.addItem("Chord Advanced (Rotation)", 2)
        self.combo_mode.setToolTip("Select how the arpeggiator plays notes")
        params_layout.addWidget(lbl_mode, 0, 0)
        params_layout.addWidget(self.combo_mode, 0, 1)

        # Pattern Rate (now a dropdown)
        lbl_pattern_rate = QLabel("Pattern Rate:")
        self.combo_pattern_rate = ArrowComboBox()
        self.combo_pattern_rate.setMinimumWidth(150)
        self.combo_pattern_rate.setMaximumHeight(30)
        self.combo_pattern_rate.setEditable(True)
        self.combo_pattern_rate.lineEdit().setReadOnly(True)
        self.combo_pattern_rate.lineEdit().setAlignment(Qt.AlignCenter)
        self.combo_pattern_rate.addItem("1/4", 0)
        self.combo_pattern_rate.addItem("1/8", 1)
        self.combo_pattern_rate.addItem("1/16", 2)
        self.combo_pattern_rate.addItem("1/32", 3)
        self.combo_pattern_rate.addItem("1/64", 4)
        self.combo_pattern_rate.setCurrentIndex(2)  # Default to 1/16
        self.combo_pattern_rate.setToolTip("Note subdivision for steps")
        self.combo_pattern_rate.currentIndexChanged.connect(self.on_pattern_rate_changed)
        params_layout.addWidget(lbl_pattern_rate, 1, 0)
        params_layout.addWidget(self.combo_pattern_rate, 1, 1)

        # Number of steps
        lbl_num_steps = QLabel("Number of Steps:")
        self.spin_num_steps = QSpinBox()
        self.spin_num_steps.setRange(1, 128)
        self.spin_num_steps.setValue(4)
        self.spin_num_steps.setButtonSymbols(QSpinBox.UpDownArrows)
        self.spin_num_steps.setToolTip("Number of steps in the pattern")
        self.spin_num_steps.valueChanged.connect(self.on_num_steps_changed)
        params_layout.addWidget(lbl_num_steps, 2, 0)
        params_layout.addWidget(self.spin_num_steps, 2, 1)

        # Pattern rhythm (auto-calculated, read-only display)
        lbl_rhythm = QLabel("Pattern Rhythm:")
        self.lbl_pattern_length = QLabel("4/16")
        self.lbl_pattern_length.setToolTip("Total pattern rhythm (auto-calculated from steps/rate)")
        params_layout.addWidget(lbl_rhythm, 3, 0)
        params_layout.addWidget(self.lbl_pattern_length, 3, 1)

        # Gate length
        lbl_gate = QLabel("Gate Length:")
        self.spin_gate = QSpinBox()
        self.spin_gate.setRange(10, 100)
        self.spin_gate.setValue(80)
        self.spin_gate.setSuffix("%")
        self.spin_gate.setButtonSymbols(QSpinBox.UpDownArrows)
        self.spin_gate.setToolTip("Note gate length percentage")
        params_layout.addWidget(lbl_gate, 4, 0)
        params_layout.addWidget(self.spin_gate, 4, 1)

        params_group.setLayout(params_layout)
        bottom_layout.addWidget(params_group)

        # Right Container: Preset Selection (no title)
        preset_group = QGroupBox()
        preset_group.setMaximumWidth(500)
        preset_layout = QGridLayout()

        lbl_preset = QLabel("Select Preset:")
        self.combo_preset = ArrowComboBox()
        self.combo_preset.setMinimumWidth(150)
        self.combo_preset.setMaximumHeight(30)
        self.combo_preset.setEditable(True)
        self.combo_preset.lineEdit().setReadOnly(True)
        self.combo_preset.lineEdit().setAlignment(Qt.AlignCenter)
        # Arpeggiator presets: 0-31
        for i in range(32):
            if i < 8:
                self.combo_preset.addItem(f"Factory Arp {i}", i)
            else:
                self.combo_preset.addItem(f"User Arp {i - 7}", i)
        self.combo_preset.currentIndexChanged.connect(self.on_preset_changed)

        preset_layout.addWidget(lbl_preset, 0, 0)
        preset_layout.addWidget(self.combo_preset, 0, 1, 1, 2)

        # Preset buttons - 30px tall
        button_style = "QPushButton { min-height: 30px; max-height: 30px; }"

        self.btn_load = QPushButton("Load from Device")
        self.btn_load.setStyleSheet(button_style)
        self.btn_load.clicked.connect(self.load_preset)
        self.btn_save = QPushButton("Save to Device")
        self.btn_save.setStyleSheet(button_style)
        self.btn_save.clicked.connect(self.save_preset)

        preset_layout.addWidget(self.btn_load, 1, 0, 1, 3)
        preset_layout.addWidget(self.btn_save, 2, 0, 1, 3)

        # Copy and Paste buttons - same size
        copy_paste_layout = QHBoxLayout()
        copy_paste_layout.setSpacing(5)

        self.btn_copy = QPushButton("Copy Preset")
        self.btn_copy.setStyleSheet(button_style)
        self.btn_copy.clicked.connect(self.copy_preset_to_clipboard)
        self.btn_paste = QPushButton("Paste Preset")
        self.btn_paste.setStyleSheet(button_style)
        self.btn_paste.clicked.connect(self.paste_preset_from_clipboard)

        copy_paste_layout.addWidget(self.btn_copy)
        copy_paste_layout.addWidget(self.btn_paste)

        preset_layout.addLayout(copy_paste_layout, 3, 0, 1, 3)

        # Reset All Steps button (replacing Clear All Steps)
        self.btn_reset_all = QPushButton("Reset All Steps")
        self.btn_reset_all.setStyleSheet(button_style)
        self.btn_reset_all.clicked.connect(self.reset_all_steps)
        preset_layout.addWidget(self.btn_reset_all, 4, 0, 1, 3)

        preset_group.setLayout(preset_layout)
        bottom_layout.addWidget(preset_group)

        # Add right spacer to push containers closer together
        bottom_layout.addStretch(1)

        main_layout.addLayout(bottom_layout)

        # Build initial steps
        self.rebuild_steps()

        # === Quick Actions ===
        actions_layout = QHBoxLayout()

        main_layout.addLayout(actions_layout)

        main_layout.addWidget(self.lbl_status)

        self.addLayout(main_layout)

    def rebuild_steps(self):
        """Rebuild step widgets based on step count"""
        # Clear existing steps
        for widget in self.step_widgets:
            self.step_layout.removeWidget(widget)
            widget.deleteLater()
        self.step_widgets.clear()

        # Remove stretch if it exists
        while self.step_layout.count() > 0:
            item = self.step_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Create new steps (they will be added from left to right)
        step_count = self.spin_num_steps.value()
        for i in range(step_count):
            step_widget = StepWidget(i, is_step_sequencer=self.is_step_sequencer)

            # Load existing step data if available
            if i < len(self.preset_data['steps']):
                step_widget.set_step_data(self.preset_data['steps'][i])

            self.step_widgets.append(step_widget)
            self.step_layout.addWidget(step_widget, 0, Qt.AlignLeft)  # Explicitly align left

        self.step_layout.addStretch()  # Add stretch at the end to push steps to the left
        self.update_pattern_length_display()
        self.update_status(f"Rebuilt sequencer with {step_count} steps")

    def on_pattern_rate_changed(self, index):
        """Pattern rate changed - update pattern length display"""
        rate_text = self.combo_pattern_rate.currentText()
        self.update_pattern_length_display()
        self.update_status(f"Pattern rate changed to {rate_text}")

    def on_num_steps_changed(self, value):
        """Number of steps changed - rebuild and update pattern length"""
        self.rebuild_steps()

    def update_pattern_length_display(self):
        """Update the pattern length display in x/y format with halving logic"""
        # Get rate_64ths from combo box value
        rate_map = {0: 64, 1: 32, 2: 16, 3: 8, 4: 4}  # /4, /8, /16, /32, /64
        rate_64ths = rate_map.get(self.combo_pattern_rate.currentData(), 16)

        num_steps = self.spin_num_steps.value()

        # Calculate pattern length in 64ths
        pattern_length_64ths = rate_64ths * num_steps

        # Calculate denominator from rate (y value)
        # rate_64ths = 64 means /4, 32 means /8, 16 means /16, etc.
        # Denominator: 64ths -> /4, 32 -> /8, 16 -> /16, 8 -> /32, 4 -> /64
        denominator_map = {64: 4, 32: 8, 16: 16, 8: 32, 4: 64}
        y = denominator_map.get(rate_64ths, 16)

        # x is the number of steps
        x = num_steps

        # Apply halving logic: keep halving both x and y if possible, stop at y=4
        import math
        while x % 2 == 0 and y % 2 == 0 and y > 4:
            x = x // 2
            y = y // 2

        self.lbl_pattern_length.setText(f"{x}/{y}")

    def reset_all_steps(self):
        """Reset all steps to empty (with confirmation)"""
        reply = QMessageBox.question(
            None,
            "Reset All Steps",
            "Are you sure you want to clear all notes from all steps?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            for widget in self.step_widgets:
                widget.set_step_data([])  # Empty list of notes
            self.update_status("All steps reset to empty")

    def copy_preset_to_clipboard(self):
        """Copy current preset data to internal clipboard"""
        self.gather_preset_data()
        self.clipboard_preset = self.preset_data.copy()
        self.clipboard_preset['steps'] = [step.copy() for step in self.preset_data['steps']]
        self.update_status("Preset copied to clipboard")

    def paste_preset_from_clipboard(self):
        """Paste preset data from internal clipboard"""
        if not hasattr(self, 'clipboard_preset') or self.clipboard_preset is None:
            self.update_status("No preset in clipboard", error=True)
            return

        self.preset_data = self.clipboard_preset.copy()
        self.preset_data['steps'] = [step.copy() for step in self.clipboard_preset['steps']]
        self.apply_preset_data()
        self.update_status("Preset pasted from clipboard")

    def gather_preset_data(self):
        """Gather current UI state into preset_data dict"""
        # Calculate pattern length from rate × steps
        rate_map = {0: 64, 1: 32, 2: 16, 3: 8, 4: 4}  # /4, /8, /16, /32, /64
        rate_64ths = rate_map.get(self.combo_pattern_rate.currentData(), 16)
        num_steps = self.spin_num_steps.value()
        self.preset_data['pattern_length_64ths'] = rate_64ths * num_steps
        self.preset_data['gate_length_percent'] = self.spin_gate.value()
        self.preset_data['preset_type'] = 0  # PRESET_TYPE_ARPEGGIATOR

        # Gather notes from all steps
        # Each step can have multiple notes, all at the same timing
        all_notes = []
        for i, widget in enumerate(self.step_widgets):
            step_notes = widget.get_step_data()  # Returns list of note dicts
            timing_64ths = i * rate_64ths

            for note_data in step_notes:
                # For arpeggiator: skip notes with semitone_offset = -1 (Empty)
                if not self.is_step_sequencer and note_data.get('semitone_offset', -1) == -1:
                    continue

                # Add timing to note
                note_data['timing_64ths'] = timing_64ths

                # Convert to firmware format
                if self.is_step_sequencer:
                    # Step sequencer: note_index already contains absolute note (0-11)
                    # octave_offset contains absolute octave (0-7)
                    pass  # Data is already in the right format
                else:
                    # Arpeggiator: semitone_offset -> note_index for firmware
                    note_data['note_index'] = note_data.get('semitone_offset', 0)

                # Raw travel is velocity
                note_data['raw_travel'] = note_data.get('velocity', 200)

                all_notes.append(note_data)

        self.preset_data['steps'] = all_notes
        self.preset_data['note_count'] = len(all_notes)

        # Keep name in data structure for firmware compatibility
        if 'name' not in self.preset_data:
            self.preset_data['name'] = 'User Preset'

    def apply_preset_data(self):
        """Apply preset_data to UI - convert flat note list to step-based structure"""
        self.spin_gate.setValue(self.preset_data.get('gate_length_percent', 80))

        # Convert flat note list back to step-based structure
        # Group notes by timing
        notes_by_timing = {}
        for note in self.preset_data.get('steps', []):
            timing = note.get('timing_64ths', 0)
            if timing not in notes_by_timing:
                notes_by_timing[timing] = []
            notes_by_timing[timing].append(note)

        # Determine number of steps from pattern length and rate
        rate_map = {0: 64, 1: 32, 2: 16, 3: 8, 4: 4}
        pattern_length = self.preset_data.get('pattern_length_64ths', 64)

        # Find rate that matches the pattern
        for rate_index, rate_64ths in rate_map.items():
            num_steps = pattern_length // rate_64ths
            if pattern_length % rate_64ths == 0 and 1 <= num_steps <= 128:
                self.combo_pattern_rate.setCurrentIndex(rate_index)
                self.spin_num_steps.setValue(num_steps)
                break
        else:
            # Fallback: use 1/16 notes
            self.combo_pattern_rate.setCurrentIndex(2)
            self.spin_num_steps.setValue(max(1, min(128, pattern_length // 16)))

        # Rebuild steps and populate with notes
        self.rebuild_steps()

        # Populate steps with notes
        rate_64ths = rate_map.get(self.combo_pattern_rate.currentData(), 16)
        for i, widget in enumerate(self.step_widgets):
            step_timing = i * rate_64ths
            step_notes = notes_by_timing.get(step_timing, [])
            widget.set_step_data(step_notes)

    def on_preset_changed(self, index):
        """Preset selection changed"""
        self.current_preset_id = index

        # Update UI state
        is_factory = (index < 8)
        self.btn_save.setEnabled(not is_factory)

        if is_factory:
            self.update_status(f"Factory preset {index} selected (read-only)")
        else:
            self.update_status(f"User preset {index} selected")

    def send_hid_command(self, cmd, params):
        """Send HID command to device"""
        if not isinstance(self.device, VialKeyboard):
            self.update_status("Error: Device not connected", error=True)
            return False

        # Build HID packet
        data = bytearray(32)
        data[0] = self.MANUFACTURER_ID
        data[1] = self.SUB_ID
        data[2] = self.DEVICE_ID
        data[3] = cmd

        # Add parameters
        for i, param in enumerate(params):
            if i + 4 < len(data):
                if isinstance(param, int):
                    data[i + 4] = param & 0xFF
                elif isinstance(param, str):
                    # String encoding
                    encoded = param.encode('ascii')[:16]
                    for j, byte in enumerate(encoded):
                        if i + 4 + j < len(data):
                            data[i + 4 + j] = byte
                    break

        try:
            self.device.keyboard.raw_hid_send(bytes(data))
            logger.info(f"Sent HID command: 0x{cmd:02X}")
            return True
        except Exception as e:
            logger.error(f"HID send error: {e}")
            self.update_status(f"HID error: {e}", error=True)
            return False

    def handle_hid_response(self, data):
        """Handle HID response from device"""
        if len(data) < 4:
            return

        cmd = data[3]
        status = data[4] if len(data) > 4 else 0xFF

        if status == 0:
            self.update_status("Command successful")

            if cmd == self.ARP_CMD_GET_PRESET:
                # Parse preset data
                name = data[5:21].decode('ascii', errors='ignore').rstrip('\x00')
                note_count = data[21] if len(data) > 21 else 0
                pattern_length = ((data[22] << 8) | data[23]) if len(data) > 23 else 64
                gate_length = data[24] if len(data) > 24 else 80

                self.preset_data['name'] = name
                self.preset_data['note_count'] = note_count
                self.preset_data['pattern_length_64ths'] = pattern_length
                self.preset_data['gate_length_percent'] = gate_length

                self.apply_preset_data()
                self.update_status(f"Loaded preset: {name}")
        else:
            error_msg = {
                1: "Error: Invalid preset or operation failed",
                0xFF: "Error: Unknown command"
            }.get(status, f"Error: Status code {status}")
            self.update_status(error_msg, error=True)

    def load_preset(self):
        """Load preset from device via HID"""
        self.gather_preset_data()

        preset_id = self.current_preset_id
        self.send_hid_command(self.ARP_CMD_GET_PRESET, [preset_id])
        self.update_status(f"Requesting preset {preset_id} from device...")

    def save_preset(self):
        """Save preset to device via HID"""
        if self.current_preset_id < 8:
            self.update_status("Cannot save to factory preset!", error=True)
            return

        self.gather_preset_data()

        # Build parameter list
        params = [self.current_preset_id]
        params.append(self.preset_data['name'])  # String will be encoded in send_hid_command
        params.extend([0] * (16 - len(self.preset_data['name'])))  # Padding
        params.append(self.preset_data['note_count'])
        params.append((self.preset_data['pattern_length_64ths'] >> 8) & 0xFF)
        params.append(self.preset_data['pattern_length_64ths'] & 0xFF)
        params.append(self.preset_data['gate_length_percent'])

        if self.send_hid_command(self.ARP_CMD_SET_PRESET, params):
            # Also save to EEPROM
            QTimer.singleShot(100, lambda: self.send_hid_command(
                self.ARP_CMD_SAVE_PRESET, [self.current_preset_id]))
            self.update_status(f"Saving preset {self.current_preset_id}...")

    def update_status(self, message, error=False):
        """Update status label"""
        logger.info(message)
        self.lbl_status.setText(message)
        if error:
            self.lbl_status.setStyleSheet("color: #ff4444; padding: 5px;")
        else:
            self.lbl_status.setStyleSheet("color: #00aaff; padding: 5px;")

    def valid(self):
        """Check if this tab should be visible"""
        return isinstance(self.device, VialKeyboard)

    def rebuild(self, device):
        """Rebuild for new device"""
        super().rebuild(device)

        if self.valid():
            self.update_status("Arpeggiator ready")
            # Request system info
            self.send_hid_command(self.ARP_CMD_GET_INFO, [])
        else:
            self.update_status("Connect a Vial device to use arpeggiator")

    def activate(self):
        """Tab activated"""
        logger.info("Arpeggiator tab activated")

    def deactivate(self):
        """Tab deactivated"""
        logger.info("Arpeggiator tab deactivated")


class StepSequencer(Arpeggiator):
    """Step Sequencer tab - plays absolute MIDI notes independently"""

    def __init__(self):
        # Call parent but override key attributes
        BasicEditor.__init__(self)

        logger.info("Step Sequencer tab initialized")

        self.current_preset_id = 32  # Presets 32-63 for step sequencer
        self.is_step_sequencer = True  # This is the step sequencer tab
        self.preset_data = {
            'name': 'User Seq',
            'preset_type': 1,  # PRESET_TYPE_STEP_SEQUENCER
            'note_count': 0,
            'pattern_length_64ths': 64,
            'gate_length_percent': 80,
            'steps': []
        }

        # Initialize with 4 default empty steps
        for i in range(4):
            self.preset_data['steps'].append([])  # Empty list of notes per step

        self.step_widgets = []
        self.clipboard_preset = None  # Internal clipboard for copy/paste
        self.hid_data_received.connect(self.handle_hid_response)

        self.setup_ui()

    def setup_ui(self):
        """Build the UI - override to customize preset selector"""
        # Call parent setup_ui first
        super().setup_ui()

        # Update preset selector for step sequencer range (32-63)
        self.combo_preset.clear()
        for i in range(32, 64):
            if i < 40:
                self.combo_preset.addItem(f"Factory Seq {i - 31}", i)
            else:
                self.combo_preset.addItem(f"User Seq {i - 39}", i)

        # Set default to first step sequencer preset
        self.combo_preset.setCurrentIndex(0)

    def gather_preset_data(self):
        """Override to set preset_type to step sequencer"""
        super().gather_preset_data()
        self.preset_data['preset_type'] = 1  # PRESET_TYPE_STEP_SEQUENCER

    def activate(self):
        """Tab activated"""
        logger.info("Step Sequencer tab activated")

    def deactivate(self):
        """Tab deactivated"""
        logger.info("Step Sequencer tab deactivated")
