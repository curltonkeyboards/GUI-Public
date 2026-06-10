# SPDX-License-Identifier: GPL-2.0-or-later
"""
MIDI Delay Settings Editor

Configures delay slots (DELAY_01 - DELAY_100) that repeat MIDI notes
with configurable timing, decay, channel routing, and transposition.
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QComboBox, QGroupBox, QMessageBox, QSpinBox, QSlider,
                              QCheckBox, QSizePolicy, QScrollArea, QTabWidget, QToolTip,
                              QInputDialog)
from PyQt5.QtCore import Qt

from editor.basic_editor import BasicEditor
from protocol.delay_protocol import (ProtocolDelay, DelaySlot,
                                      DELAY_NUM_SLOTS, DELAY_FACTORY_COUNT,
                                      DELAY_USER_SLOT_COUNT,
                                      RATE_MODE_BPM, RATE_MODE_FIXED_MS,
                                      TRANSPOSE_FIXED, TRANSPOSE_CUMULATIVE)
from vial_device import VialKeyboard


# Repeats slider: positions 0-9 map to [1,2,3,4,5,6,7,8,9,255]
REPEATS_VALUES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 255]
REPEATS_LABELS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "No Limit"]

# Max active notes slider: positions 0-12 where 1-12=limit, 13=no limit (rightmost)
# Slider range 0-12: position 0=1 note, position 11=12 notes, position 12=no limit
MAX_ACTIVE_SLIDER_LABELS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "No Limit"]

# Combined BPM Rate items: note_value * 3 + timing_mode
# 5 note values (1/1, 1/2, 1/4, 1/8, 1/16) x 3 timings (Straight, Triplet, Dotted) = 15
RATE_BPM_ITEMS = [
    "1/1", "1/1 Triplet", "1/1 Dotted",
    "1/2", "1/2 Triplet", "1/2 Dotted",
    "1/4", "1/4 Triplet", "1/4 Dotted",
    "1/8", "1/8 Triplet", "1/8 Dotted",
    "1/16", "1/16 Triplet", "1/16 Dotted",
]


def rate_combo_to_note_timing(index):
    """Convert combined rate combo index to (note_value, timing_mode)"""
    return index // 3, index % 3


def note_timing_to_rate_combo(note_value, timing_mode):
    """Convert separate note_value and timing_mode to combined rate combo index"""
    return note_value * 3 + timing_mode


def repeats_to_slider(val):
    """Convert max_repeats value to slider position"""
    if val >= 255 or val == 0:
        return 9  # Infinite
    if val < 1:
        return 0
    if val > 9:
        return 9
    return val - 1


def slider_to_repeats(pos):
    """Convert slider position to max_repeats value"""
    if pos < 0:
        pos = 0
    if pos >= len(REPEATS_VALUES):
        pos = len(REPEATS_VALUES) - 1
    return REPEATS_VALUES[pos]


def max_active_to_slider(val):
    """Convert max_active_notes firmware value to slider position.
    Firmware: 0=no limit, 1-12=limit. Slider: 0-11=1-12, 12=no limit."""
    if val == 0 or val > 12:
        return 12  # No Limit (rightmost)
    return val - 1  # 1->0, 2->1, ... 12->11


def slider_to_max_active(pos):
    """Convert slider position to max_active_notes firmware value.
    Slider: 0-11=1-12, 12=no limit. Firmware: 0=no limit, 1-12=limit."""
    if pos >= 12:
        return 0  # No limit
    return pos + 1  # 0->1, 1->2, ... 11->12


def _make_help_label(tooltip_text):
    """Create a small question mark button with tooltip for help"""
    help_btn = QPushButton("?")
    help_btn.setStyleSheet("""
        QPushButton {
            color: #888;
            font-weight: bold;
            font-size: 9pt;
            border: 1px solid #888;
            border-radius: 9px;
            min-width: 16px;
            max-width: 16px;
            min-height: 16px;
            max-height: 16px;
            padding: 0px;
            margin: 0px;
            background: transparent;
        }
        QPushButton:hover {
            color: #fff;
            background-color: #555;
        }
    """)
    help_btn.setToolTip(tooltip_text)
    help_btn.setCursor(Qt.WhatsThisCursor)
    return help_btn


class DelaySlotEditor(QWidget):
    """Editor widget for a single delay slot's settings"""

    def __init__(self, slot_index=0, parent=None):
        super().__init__(parent)
        self.slot = DelaySlot()
        self.slot_index = slot_index
        self._building = False

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Header row: title, rename button, description (matching macro tab layout)
        from protocol.feature_names import get_feature_name_manager, FEATURE_DELAY
        header_layout = QHBoxLayout()
        name = get_feature_name_manager().get_name(FEATURE_DELAY, slot_index)
        self.title_label = QLabel(f"<b>{name}</b>")
        self.title_label.setStyleSheet("font-size: 14pt;")
        header_layout.addWidget(self.title_label)

        self.btn_rename = QPushButton("Rename")
        self.btn_rename.setMaximumHeight(24)
        self.btn_rename.setMaximumWidth(60)
        self.btn_rename.setStyleSheet("QPushButton { font-size: 8pt; border-radius: 3px; padding: 2px 6px; }")
        self.btn_rename.clicked.connect(self._on_rename)
        header_layout.addWidget(self.btn_rename)

        header_layout.addSpacing(12)

        desc = QLabel("Configure delay effects for MIDI notes played/passed through the "
                      "MIDIswitch. Assign these to the keymap using the User Delay Buttons "
                      "which can be renamed.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray; font-size: 9pt;")
        header_layout.addWidget(desc, 1)

        layout.addLayout(header_layout)

        # ---- Centered content area (max 600px) ----
        center_outer = QHBoxLayout()
        center_outer.addStretch()

        center_widget = QWidget()
        center_widget.setMaximumWidth(600)
        center_layout = QVBoxLayout()
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)

        # ---- Rate & Decay (no group title) ----
        rate_group = QGroupBox()
        rate_layout = QVBoxLayout()
        rate_layout.setSpacing(6)

        # Row 1: Mode + Rate (BPM) or Mode + Delay ms (Fixed)
        row = QHBoxLayout()
        row.addWidget(QLabel("Mode:"))
        self.rate_mode_combo = QComboBox()
        self.rate_mode_combo.addItems(["BPM Synced", "Fixed ms"])
        self.rate_mode_combo.setMinimumWidth(110)
        self.rate_mode_combo.currentIndexChanged.connect(self._on_rate_mode_changed)
        row.addWidget(self.rate_mode_combo)

        # BPM combined Rate dropdown (note value + timing combined)
        self.rate_label = QLabel("  Rate:")
        row.addWidget(self.rate_label)
        self.rate_combo = QComboBox()
        self.rate_combo.addItems(RATE_BPM_ITEMS)
        self.rate_combo.setMinimumWidth(130)
        row.addWidget(self.rate_combo)

        # Fixed ms control (inline, hidden by default)
        self.fixed_ms_label = QLabel("  Delay:")
        self.fixed_ms_label.setVisible(False)
        row.addWidget(self.fixed_ms_label)
        self.fixed_ms_spin = QSpinBox()
        self.fixed_ms_spin.setRange(10, 5000)
        self.fixed_ms_spin.setSuffix(" ms")
        self.fixed_ms_spin.setSingleStep(10)
        self.fixed_ms_spin.setMinimumWidth(110)
        self.fixed_ms_spin.setVisible(False)
        row.addWidget(self.fixed_ms_spin)

        row.addStretch()
        rate_layout.addLayout(row)

        # Row 2: Decay slider
        row = QHBoxLayout()
        row.addWidget(QLabel("Decay:"))
        row.addWidget(_make_help_label(
            "Velocity reduction per repeat.\n"
            "Higher values = echoes fade faster.\n"
            "0% = all repeats at full velocity."))
        self.decay_slider = QSlider(Qt.Horizontal)
        self.decay_slider.setRange(0, 100)
        self.decay_slider.setTickInterval(25)
        self.decay_slider.setTickPosition(QSlider.TicksBelow)
        row.addWidget(self.decay_slider)
        self.decay_label = QLabel("50%")
        self.decay_label.setMinimumWidth(36)
        row.addWidget(self.decay_label)
        self.decay_slider.valueChanged.connect(
            lambda v: self.decay_label.setText(f"{v}%"))
        rate_layout.addLayout(row)

        # Row 3: Max Repeats slider
        row = QHBoxLayout()
        row.addWidget(QLabel("Repeats:"))
        row.addWidget(_make_help_label(
            "Maximum number of delay echoes per note.\n"
            "\u221E = unlimited (echoes continue until\n"
            "velocity decays to zero)."))
        self.repeats_slider = QSlider(Qt.Horizontal)
        self.repeats_slider.setRange(0, 9)
        self.repeats_slider.setTickInterval(1)
        self.repeats_slider.setTickPosition(QSlider.TicksBelow)
        row.addWidget(self.repeats_slider)
        self.repeats_label = QLabel("3")
        self.repeats_label.setMinimumWidth(20)
        row.addWidget(self.repeats_label)
        self.repeats_slider.valueChanged.connect(self._on_repeats_changed)
        rate_layout.addLayout(row)

        # Row 4: Max Active Notes slider
        row = QHBoxLayout()
        row.addWidget(QLabel("Max Notes:"))
        row.addWidget(_make_help_label(
            "Limits how many notes can have active\n"
            "delay echoes at once in this slot.\n"
            "When exceeded, the oldest note's delays\n"
            "are cancelled. 'No Limit' allows all notes\n"
            "to echo freely (polyphonic delay)."))
        self.max_active_slider = QSlider(Qt.Horizontal)
        self.max_active_slider.setRange(0, 12)
        self.max_active_slider.setTickInterval(1)
        self.max_active_slider.setTickPosition(QSlider.TicksBelow)
        row.addWidget(self.max_active_slider)
        self.max_active_label = QLabel("No Limit")
        self.max_active_label.setMinimumWidth(52)
        row.addWidget(self.max_active_label)
        self.max_active_slider.valueChanged.connect(self._on_max_active_changed)
        rate_layout.addLayout(row)

        rate_group.setLayout(rate_layout)
        center_layout.addWidget(rate_group)

        # ---- Channel Delay ----
        channel_group = QGroupBox("Channel Delay")
        channel_layout = QVBoxLayout()
        channel_layout.setSpacing(4)

        self.channel_check = QCheckBox("Send delay to different channel")
        self.channel_check.stateChanged.connect(self._on_channel_check_changed)
        channel_layout.addWidget(self.channel_check)

        # Single channel controls (hidden until checkbox ticked)
        self.channel_controls = QWidget()
        channel_controls_layout = QVBoxLayout()
        channel_controls_layout.setContentsMargins(0, 4, 0, 0)
        channel_controls_layout.setSpacing(4)

        # Channel 1 row
        row = QHBoxLayout()
        row.addWidget(QLabel("Output Channel:"))
        self.channel_combo = QComboBox()
        for i in range(1, 17):
            self.channel_combo.addItem(f"Channel {i}")
        self.channel_combo.setMinimumWidth(140)
        row.addWidget(self.channel_combo)
        row.addStretch()
        channel_controls_layout.addLayout(row)

        # Multi-channel checkbox
        self.multi_channel_check = QCheckBox("Allow multiple channels (repeats cycle through channels)")
        self.multi_channel_check.stateChanged.connect(self._on_multi_channel_check_changed)
        channel_controls_layout.addWidget(self.multi_channel_check)

        # Extra channel rows (hidden until multi-channel ticked)
        self.multi_channel_widget = QWidget()
        multi_layout = QVBoxLayout()
        multi_layout.setContentsMargins(0, 2, 0, 0)
        multi_layout.setSpacing(4)

        self.channel_combos_extra = []
        self.channel_rows = []
        self.add_channel_buttons = []
        self.remove_channel_buttons = []

        for idx in range(2, 5):
            row_widget = QWidget()
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(QLabel(f"Channel {idx}:"))
            combo = QComboBox()
            for i in range(1, 17):
                combo.addItem(f"Channel {i}")
            combo.setMinimumWidth(140)
            row_layout.addWidget(combo)

            remove_btn = QPushButton("\u00d7")
            remove_btn.setFixedSize(24, 24)
            remove_btn.setToolTip(f"Remove channel {idx}")
            remove_btn.setStyleSheet(
                "QPushButton { background-color: #cc3333; color: white; "
                "font-weight: bold; font-size: 14px; border: none; border-radius: 3px; }"
                "QPushButton:hover { background-color: #ee4444; }"
            )
            remove_btn.setVisible(False)
            remove_btn.clicked.connect(lambda _, i=idx: self._on_remove_channel(i))
            row_layout.addWidget(remove_btn)
            self.remove_channel_buttons.append(remove_btn)

            row_layout.addStretch()
            row_widget.setLayout(row_layout)
            row_widget.setVisible(False)
            multi_layout.addWidget(row_widget)
            self.channel_combos_extra.append(combo)
            self.channel_rows.append(row_widget)

            if idx < 4:
                add_btn = QPushButton("+ Add Channel")
                add_btn.setMaximumWidth(120)
                add_btn.setVisible(False)
                add_btn.clicked.connect(lambda _, i=idx: self._on_add_channel(i))
                multi_layout.addWidget(add_btn)
                self.add_channel_buttons.append(add_btn)

        self.multi_channel_widget.setLayout(multi_layout)
        self.multi_channel_widget.setVisible(False)
        channel_controls_layout.addWidget(self.multi_channel_widget)

        self.channel_controls.setLayout(channel_controls_layout)
        self.channel_controls.setVisible(False)
        channel_layout.addWidget(self.channel_controls)

        channel_group.setLayout(channel_layout)
        center_layout.addWidget(channel_group)

        # ---- Pitch Delay ----
        pitch_group = QGroupBox("Pitch Delay")
        pitch_layout = QVBoxLayout()
        pitch_layout.setSpacing(6)

        self.pitch_check = QCheckBox("Enable pitch delay")
        self.pitch_check.stateChanged.connect(self._on_pitch_check_changed)
        pitch_layout.addWidget(self.pitch_check)

        # Pitch controls container (hidden by default)
        self.pitch_controls = QWidget()
        pitch_controls_layout = QVBoxLayout()
        pitch_controls_layout.setContentsMargins(0, 4, 0, 0)
        pitch_controls_layout.setSpacing(6)

        # Transpose slider
        row = QHBoxLayout()
        row.addWidget(QLabel("Semitones:"))
        self.transpose_slider = QSlider(Qt.Horizontal)
        self.transpose_slider.setRange(-24, 24)
        self.transpose_slider.setTickInterval(12)
        self.transpose_slider.setTickPosition(QSlider.TicksBelow)
        row.addWidget(self.transpose_slider)
        self.transpose_label = QLabel("0")
        self.transpose_label.setMinimumWidth(32)
        row.addWidget(self.transpose_label)
        self.transpose_slider.valueChanged.connect(self._on_transpose_changed)
        pitch_controls_layout.addLayout(row)

        # Tick labels for -24, -12, 0, +12, +24
        tick_row = QHBoxLayout()
        tick_row.addSpacing(72)
        for lbl in ["-24", "-12", "0", "+12", "+24"]:
            t = QLabel(lbl)
            t.setStyleSheet("font-size: 9px; color: gray;")
            tick_row.addWidget(t)
            if lbl != "+24":
                tick_row.addStretch()
        tick_row.addSpacing(40)
        pitch_controls_layout.addLayout(tick_row)

        # Transpose mode
        row = QHBoxLayout()
        row.addWidget(QLabel("Mode:"))
        row.addWidget(_make_help_label(
            "Fixed: every echo is shifted by the same\n"
            "amount from the original note.\n"
            "  e.g. +3 semitones: C -> Eb, Eb, Eb, Eb...\n\n"
            "Cumulative: each echo shifts further from\n"
            "the previous one (stacking).\n"
            "  e.g. +3 semitones: C -> Eb, Gb, A, C..."))
        self.transpose_mode_combo = QComboBox()
        self.transpose_mode_combo.addItems(["Fixed", "Cumulative"])
        self.transpose_mode_combo.setMinimumWidth(120)
        row.addWidget(self.transpose_mode_combo)
        row.addStretch()
        pitch_controls_layout.addLayout(row)

        self.pitch_controls.setLayout(pitch_controls_layout)
        self.pitch_controls.setVisible(False)
        pitch_layout.addWidget(self.pitch_controls)

        pitch_group.setLayout(pitch_layout)
        center_layout.addWidget(pitch_group)

        # ---- Action buttons (below Pitch Delay, left-aligned) ----
        button_row = QHBoxLayout()
        self.save_btn = QPushButton("Save Slot")
        button_row.addWidget(self.save_btn)

        self.save_new_btn = QPushButton("Save As New Slot")
        button_row.addWidget(self.save_new_btn)

        self.load_btn = QPushButton("Load Slot")
        button_row.addWidget(self.load_btn)

        button_row.addStretch()
        center_layout.addLayout(button_row)

        center_layout.addStretch()

        center_widget.setLayout(center_layout)
        center_outer.addWidget(center_widget)
        center_outer.addStretch()
        layout.addLayout(center_outer, 1)

        self.setLayout(layout)

        # Initial visibility
        self._on_rate_mode_changed(0)

    def _on_rate_mode_changed(self, index):
        """Show/hide rate controls based on mode"""
        is_bpm = (index == RATE_MODE_BPM)
        self.rate_label.setVisible(is_bpm)
        self.rate_combo.setVisible(is_bpm)
        self.fixed_ms_label.setVisible(not is_bpm)
        self.fixed_ms_spin.setVisible(not is_bpm)

    def _on_channel_check_changed(self, state):
        """Show/hide channel controls based on checkbox"""
        self.channel_controls.setVisible(state == Qt.Checked)

    def _on_multi_channel_check_changed(self, state):
        """Show/hide extra channel dropdowns with incremental add"""
        checked = (state == Qt.Checked)
        self.multi_channel_widget.setVisible(checked)
        if checked:
            self.channel_rows[0].setVisible(True)
            if self.add_channel_buttons:
                self.add_channel_buttons[0].setVisible(True)
            self.channel_rows[1].setVisible(False)
            self.channel_rows[2].setVisible(False)
            if len(self.add_channel_buttons) > 1:
                self.add_channel_buttons[1].setVisible(False)
            self._update_remove_buttons()

    def _update_remove_buttons(self):
        """Show x only on the highest visible channel row"""
        highest_visible = -1
        for i in range(len(self.channel_rows) - 1, -1, -1):
            if self.channel_rows[i].isVisible():
                highest_visible = i
                break

        for i, btn in enumerate(self.remove_channel_buttons):
            btn.setVisible(i == highest_visible and highest_visible >= 0)

    def _on_add_channel(self, channel_idx):
        """Show the next channel row and update add/remove buttons"""
        row_idx = channel_idx - 1
        self.channel_rows[row_idx].setVisible(True)

        btn_idx = channel_idx - 2
        if btn_idx < len(self.add_channel_buttons):
            self.add_channel_buttons[btn_idx].setVisible(False)

        next_btn_idx = btn_idx + 1
        if next_btn_idx < len(self.add_channel_buttons):
            self.add_channel_buttons[next_btn_idx].setVisible(True)

        self._update_remove_buttons()

    def _on_remove_channel(self, channel_idx):
        """Remove the highest channel and update add/remove buttons"""
        row_idx = channel_idx - 2
        self.channel_rows[row_idx].setVisible(False)

        for btn in self.add_channel_buttons:
            btn.setVisible(False)

        if row_idx == 0:
            self.multi_channel_check.setChecked(False)
        else:
            btn_idx = row_idx - 1
            if btn_idx < len(self.add_channel_buttons):
                self.add_channel_buttons[btn_idx].setVisible(True)

        self._update_remove_buttons()

    def _on_pitch_check_changed(self, state):
        """Show/hide pitch controls based on checkbox"""
        self.pitch_controls.setVisible(state == Qt.Checked)

    def _on_repeats_changed(self, pos):
        """Update repeats label from slider position"""
        self.repeats_label.setText(REPEATS_LABELS[pos])

    def _on_max_active_changed(self, val):
        """Update max active notes label from slider position"""
        self.max_active_label.setText(MAX_ACTIVE_SLIDER_LABELS[val])

    def _on_transpose_changed(self, val):
        """Update transpose label"""
        self.transpose_label.setText(f"{val:+d}" if val != 0 else "0")

    def set_tab_widget(self, tab_widget):
        """Store reference to parent tab widget for updating tab titles on rename"""
        self._tab_widget = tab_widget

    def refresh_title(self):
        """Refresh the title label from the feature name manager (call after device connect)"""
        from protocol.feature_names import get_feature_name_manager, FEATURE_DELAY
        name = get_feature_name_manager().get_name(FEATURE_DELAY, self.slot_index)
        self.title_label.setText(f"<b>{name}</b>")

    def _on_rename(self):
        """Open rename dialog for this delay slot"""
        from protocol.feature_names import get_feature_name_manager, FEATURE_DELAY, MAX_NAME_LENGTH
        mgr = get_feature_name_manager()
        current = mgr.get_name(FEATURE_DELAY, self.slot_index)
        new_name, ok = QInputDialog.getText(
            self, "Rename Delay Slot",
            f"Name for Delay {self.slot_index + 1} (max {MAX_NAME_LENGTH} chars):",
            text=current
        )
        if ok:
            mgr.set_name(FEATURE_DELAY, self.slot_index, new_name.strip()[:MAX_NAME_LENGTH])
            display = mgr.get_name(FEATURE_DELAY, self.slot_index)
            self.title_label.setText(f"<b>{display}</b>")
            if hasattr(self, '_tab_widget') and self._tab_widget:
                self._tab_widget.setTabText(self.slot_index, display)

    def load_from_slot(self, slot):
        """Load settings from a DelaySlot object"""
        self._building = True
        self.slot = slot

        self.rate_mode_combo.setCurrentIndex(slot.rate_mode)

        # Combined rate dropdown: note_value * 3 + timing_mode
        rate_idx = note_timing_to_rate_combo(slot.note_value, slot.timing_mode)
        if 0 <= rate_idx < len(RATE_BPM_ITEMS):
            self.rate_combo.setCurrentIndex(rate_idx)

        self.fixed_ms_spin.setValue(slot.fixed_delay_ms)
        self.decay_slider.setValue(slot.decay_percent)
        self.decay_label.setText(f"{slot.decay_percent}%")
        self.repeats_slider.setValue(repeats_to_slider(slot.max_repeats))
        self._on_repeats_changed(repeats_to_slider(slot.max_repeats))

        # Max active notes
        slider_pos = max_active_to_slider(slot.max_active_notes)
        self.max_active_slider.setValue(slider_pos)
        self._on_max_active_changed(slider_pos)

        # Channel
        if slot.channel == 0:
            self.channel_check.setChecked(False)
            self.channel_combo.setCurrentIndex(0)
            self.multi_channel_check.setChecked(False)
        else:
            self.channel_check.setChecked(True)
            self.channel_combo.setCurrentIndex(slot.channel - 1)
            if slot.channel_count >= 2:
                self.multi_channel_check.setChecked(True)
                if slot.channel2 > 0:
                    self.channel_combos_extra[0].setCurrentIndex(slot.channel2 - 1)
                if slot.channel3 > 0:
                    self.channel_combos_extra[1].setCurrentIndex(slot.channel3 - 1)
                if slot.channel4 > 0:
                    self.channel_combos_extra[2].setCurrentIndex(slot.channel4 - 1)
                self.channel_rows[0].setVisible(True)
                self.channel_rows[1].setVisible(slot.channel_count >= 3)
                self.channel_rows[2].setVisible(slot.channel_count >= 4)
                for btn in self.add_channel_buttons:
                    btn.setVisible(False)
                if slot.channel_count == 2 and self.add_channel_buttons:
                    self.add_channel_buttons[0].setVisible(True)
                elif slot.channel_count == 3 and len(self.add_channel_buttons) > 1:
                    self.add_channel_buttons[1].setVisible(True)
                self._update_remove_buttons()
            else:
                self.multi_channel_check.setChecked(False)

        # Pitch delay
        has_pitch = (slot.transpose_semi != 0)
        self.pitch_check.setChecked(has_pitch)
        self.transpose_slider.setValue(slot.transpose_semi)
        self._on_transpose_changed(slot.transpose_semi)
        self.transpose_mode_combo.setCurrentIndex(slot.transpose_mode)

        self._on_rate_mode_changed(slot.rate_mode)
        self._building = False

    def save_to_slot(self):
        """Save current settings to a DelaySlot object"""
        slot = DelaySlot()
        slot.rate_mode = self.rate_mode_combo.currentIndex()

        # Extract note_value and timing_mode from combined rate dropdown
        note_value, timing_mode = rate_combo_to_note_timing(self.rate_combo.currentIndex())
        slot.note_value = note_value
        slot.timing_mode = timing_mode

        slot.fixed_delay_ms = self.fixed_ms_spin.value()
        slot.decay_percent = self.decay_slider.value()
        slot.max_repeats = slider_to_repeats(self.repeats_slider.value())

        slot.max_active_notes = slider_to_max_active(self.max_active_slider.value())

        # Channel
        if self.channel_check.isChecked():
            slot.channel = self.channel_combo.currentIndex() + 1
            if self.multi_channel_check.isChecked():
                visible_count = sum(1 for row in self.channel_rows if row.isVisible())
                slot.channel_count = 1 + visible_count
                slot.channel2 = self.channel_combos_extra[0].currentIndex() + 1 if visible_count >= 1 else 0
                slot.channel3 = self.channel_combos_extra[1].currentIndex() + 1 if visible_count >= 2 else 0
                slot.channel4 = self.channel_combos_extra[2].currentIndex() + 1 if visible_count >= 3 else 0
            else:
                slot.channel_count = 1
        else:
            slot.channel = 0
            slot.channel_count = 1

        # Pitch delay
        if self.pitch_check.isChecked():
            slot.transpose_semi = self.transpose_slider.value()
            slot.transpose_mode = self.transpose_mode_combo.currentIndex()
        else:
            slot.transpose_semi = 0
            slot.transpose_mode = 0

        return slot


class DelayTab(BasicEditor):
    """Main Delay settings editor tab - only shows user-configurable slots (50).
    Factory presets (48) are in firmware flash and not editable from the GUI."""

    def __init__(self):
        super().__init__()
        self.delay_protocol = None
        self.keyboard = None
        self.loaded_slots = {}  # user_index (0-49) -> DelaySlot
        self.slot_editors = []
        self.slot_scroll_widgets = []

        # Dynamic tab tracking (for user slots only)
        self._visible_tab_count = 1
        self._manually_expanded_count = 0

        # Tab widget for user delay slots
        self.tabs = QTabWidget()

        # Create editors for user slots only (50)
        for i in range(DELAY_USER_SLOT_COUNT):
            editor = DelaySlotEditor(slot_index=i)
            self.slot_editors.append(editor)

            scroll = QScrollArea()
            scroll.setWidget(editor)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.slot_scroll_widgets.append(scroll)

        # Set tab widget references and connect buttons
        for i, editor in enumerate(self.slot_editors):
            editor.set_tab_widget(self.tabs)
            editor.save_btn.clicked.connect(lambda _, idx=i: self._on_save_slot(idx))
            editor.save_new_btn.clicked.connect(lambda _, idx=i: self._on_save_as_new_slot(idx))
            editor.load_btn.clicked.connect(lambda _, idx=i: self._on_load_slot(idx))

        self.addWidget(self.tabs)

        # Connect tab changes for lazy loading and "+" tab handling
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _user_to_unified(self, user_index):
        """Convert user slot index (0-49) to unified index (48-97)"""
        return DELAY_FACTORY_COUNT + user_index

    def valid(self):
        """Tab is valid when a Vial keyboard is connected"""
        return isinstance(self.device, VialKeyboard)

    def rebuild(self, device):
        """Rebuild when device changes"""
        super().rebuild(device)

        if self.valid():
            self.keyboard = device.keyboard
            self.delay_protocol = ProtocolDelay(self.keyboard)
            self.loaded_slots.clear()

            # Reset manual expansion and scan for used user slots
            self._manually_expanded_count = 0
            self._scan_and_update_visible_tabs()

    def _scan_and_update_visible_tabs(self):
        """Scan user slots to find which have non-default config"""
        if not self.delay_protocol:
            return

        last_used = -1
        for i in range(DELAY_USER_SLOT_COUNT):
            unified = self._user_to_unified(i)
            slot = self.delay_protocol.get_slot(unified)
            if slot:
                self.loaded_slots[i] = slot
                self.slot_editors[i].load_from_slot(slot)
                if not slot.is_default():
                    last_used = i

        # Refresh title labels from feature name manager (names loaded after construction)
        for editor in self.slot_editors:
            editor.refresh_title()

        self._update_visible_tabs_with_last_used(last_used)

    def _update_visible_tabs_with_last_used(self, last_used):
        """Update visible tabs given the last used user index"""
        base_visible = max(1, last_used + 1)
        self._visible_tab_count = min(DELAY_USER_SLOT_COUNT, base_visible + self._manually_expanded_count)

        # Remove all tabs
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)

        # Add visible user delay tabs
        from protocol.feature_names import get_feature_name_manager, FEATURE_DELAY
        mgr = get_feature_name_manager()
        for x in range(self._visible_tab_count):
            self.tabs.addTab(self.slot_scroll_widgets[x], mgr.get_name(FEATURE_DELAY, x))

        # Add "+" tab if not all tabs are visible
        if self._visible_tab_count < DELAY_USER_SLOT_COUNT:
            plus_widget = QWidget()
            self.tabs.addTab(plus_widget, "+")

    def _on_tab_changed(self, index):
        """Handle tab change - lazy load and handle '+' tab"""
        # Check if "+" tab was clicked
        if self._visible_tab_count < DELAY_USER_SLOT_COUNT and index == self._visible_tab_count:
            self._manually_expanded_count += 1
            self._update_visible_tabs()
            self.tabs.setCurrentIndex(self._visible_tab_count - 1)
            return

        # Lazy load: Only load slot data when first viewing the tab
        if 0 <= index < DELAY_USER_SLOT_COUNT:
            if self.delay_protocol and index not in self.loaded_slots:
                unified = self._user_to_unified(index)
                slot = self.delay_protocol.get_slot(unified)
                if slot:
                    self.loaded_slots[index] = slot
                    self.slot_editors[index].load_from_slot(slot)

    def _find_last_used_index(self):
        """Find the index of the last user slot that has non-default config"""
        for idx in range(DELAY_USER_SLOT_COUNT - 1, -1, -1):
            if idx in self.loaded_slots and not self.loaded_slots[idx].is_default():
                return idx
        return -1

    def _update_visible_tabs(self):
        """Update which tabs are visible based on content and manual expansion"""
        last_used = self._find_last_used_index()
        self._update_visible_tabs_with_last_used(last_used)

    def _on_save_slot(self, editor_index=None):
        """Save current user slot settings to keyboard"""
        if not self.delay_protocol:
            return

        index = editor_index if editor_index is not None else self.tabs.currentIndex()
        if index < 0 or index >= DELAY_USER_SLOT_COUNT:
            return

        unified = self._user_to_unified(index)
        slot = self.slot_editors[index].save_to_slot()
        if self.delay_protocol.set_slot(unified, slot):
            self.loaded_slots[index] = slot
        else:
            QMessageBox.warning(None, "Error", f"Failed to save user delay slot {index + 1}")

    def _on_save_as_new_slot(self, source_index):
        """Save current settings as a new slot (next available)"""
        if not self.delay_protocol:
            return

        # Find next empty slot
        target = None
        for i in range(DELAY_USER_SLOT_COUNT):
            if i not in self.loaded_slots or self.loaded_slots[i].is_default():
                target = i
                break

        if target is None:
            QMessageBox.warning(None, "No Space", "All delay slots are in use.")
            return

        # Copy settings from source editor to target slot
        slot = self.slot_editors[source_index].save_to_slot()
        unified = self._user_to_unified(target)

        if self.delay_protocol.set_slot(unified, slot):
            self.loaded_slots[target] = slot
            self.slot_editors[target].load_from_slot(slot)

            # Ensure the new tab is visible
            if target >= self._visible_tab_count:
                self._manually_expanded_count = max(
                    self._manually_expanded_count,
                    target - max(1, self._find_last_used_index() + 1) + 1
                )
                self._update_visible_tabs()

            # Switch to the new tab
            self.tabs.setCurrentIndex(target)
        else:
            QMessageBox.warning(None, "Error", f"Failed to save to delay slot {target + 1}")

    def _on_load_slot(self, editor_index=None):
        """Reload slot from keyboard"""
        index = editor_index if editor_index is not None else self.tabs.currentIndex()
        if 0 <= index < DELAY_USER_SLOT_COUNT:
            self.loaded_slots.pop(index, None)
            if self.delay_protocol:
                unified = self._user_to_unified(index)
                slot = self.delay_protocol.get_slot(unified)
                if slot:
                    self.loaded_slots[index] = slot
                    self.slot_editors[index].load_from_slot(slot)
