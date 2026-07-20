# SPDX-License-Identifier: GPL-2.0-or-later
import math
import struct
import json

from PyQt5.QtWidgets import (QVBoxLayout, QPushButton, QWidget, QHBoxLayout, QLabel,
                           QSizePolicy, QGroupBox, QGridLayout, QComboBox, QCheckBox,
                           QTableWidget, QHeaderView, QMessageBox, QFileDialog, QFrame,
                           QScrollArea, QSlider, QMenu, QInputDialog, QTabWidget, QSpinBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5 import QtCore
from PyQt5.QtGui import QPainterPath, QRegion, QPainter, QColor, QBrush, QPen, QFont, QLinearGradient

from widgets.combo_box import ArrowComboBox, ArrowSpinBox
from editor.basic_editor import BasicEditor
from editor.articulation_options import populate_articulation_combo, apply_articulation_visibility
from editor import drum_voices
from themes import Theme
from protocol.constants import VIAL_PROTOCOL_MATRIX_TESTER
from tabbed_keycodes import GamepadWidget, DpadButton
from protocol.keyboard_comm import (
    PARAM_CHANNEL_NUMBER, PARAM_TRANSPOSE_NUMBER, PARAM_TRANSPOSE_NUMBER2, PARAM_TRANSPOSE_NUMBER3,
    PARAM_HE_VELOCITY_CURVE,
    PARAM_KEYSPLIT_HE_VELOCITY_CURVE,
    PARAM_TRIPLESPLIT_HE_VELOCITY_CURVE,
    # PARAM_AFTERTOUCH_MODE and PARAM_AFTERTOUCH_CC removed - aftertouch is now per-layer
    PARAM_BASE_SUSTAIN, PARAM_KEYSPLIT_SUSTAIN, PARAM_TRIPLESPLIT_SUSTAIN,
    PARAM_KEYSPLITCHANNEL, PARAM_KEYSPLIT2CHANNEL, PARAM_KEYSPLITSTATUS,
    PARAM_KEYSPLITTRANSPOSESTATUS, PARAM_KEYSPLITVELOCITYSTATUS,
    # MIDI Routing Override Settings
    PARAM_CHANNEL_OVERRIDE, PARAM_VELOCITY_OVERRIDE, PARAM_TRANSPOSE_OVERRIDE,
    PARAM_MIDI_IN_MODE, PARAM_USB_MIDI_MODE, PARAM_MIDI_CLOCK_SOURCE,
    PARAM_MACRO_OVERRIDE_LIVE_NOTES,
    PARAM_SMARTCHORD_MODE, PARAM_BASE_SMARTCHORD_IGNORE,
    PARAM_KEYSPLIT_SMARTCHORD_IGNORE, PARAM_TRIPLESPLIT_SMARTCHORD_IGNORE,
    PARAM_CHORD_DISPLAY_MODE
)
from widgets.keyboard_widget import KeyboardWidget2, KeyboardWidgetSimple
from util import tr, is_hid_transfer_active
from vial_device import VialKeyboard
from unlocker import Unlocker


# The 13 AT/CC articulation base names (indices 73-85 = CC flavor, 86-98 =
# poly-AT flavor). Kept in sync with the firmware ATCC_MODE_NAMES /
# velocity_tab ATCC_NAMES.
_ATCC_ZONE_BASE_NAMES = ["Leg Vib Slow", "Leg Vib Fast", "Leg Vib Smooth",
                         "Vib Slow", "Vib Fast", "Vib Smooth",
                         "Fast Swell", "Slow Swell", "Reverse Swell",
                         "Fast Fall", "Slow Fall", "Shimmer Me", "Shimmer Leg"]


def _append_atcc_zone_items(combo):
    """Append the AT/CC articulation band (indices 73-98) to a zone
    Articulation combo, with greyed non-selectable section dividers. Without
    these entries a device sitting on an AT/CC articulation had no matching
    item, so loads fell back to Linear (and used to write that back)."""
    def _divider(label):
        combo.addItem(label)
        item = combo.model().item(combo.count() - 1)
        if item is not None:
            item.setEnabled(False)
    _divider("\u2500\u2500\u2500 CC Articulations \u2500\u2500\u2500")
    for i, name in enumerate(_ATCC_ZONE_BASE_NAMES):
        combo.addItem("{} (CC)".format(name), 73 + i)
    _divider("\u2500\u2500\u2500 AT Articulations \u2500\u2500\u2500")
    for i, name in enumerate(_ATCC_ZONE_BASE_NAMES):
        combo.addItem("{} (Poly)".format(name), 86 + i)


class ActuationVisualizer(QWidget):
    """Vertical bar widget that shows key travel distance in real-time"""

    def __init__(self, row, col, label=None, parent=None):
        super().__init__(parent)
        self.row = row
        self.col = col
        self.label = label if label else f"R{row}C{col}"
        self.distance_mm = 0.0  # Current distance in mm
        self.max_travel_mm = 4.0  # Maximum key travel in mm

        # Calibration debug values
        self.rest_adc = 0
        self.bottom_adc = 0
        self.raw_adc = 0

        # Widget size - compact but shows debug info
        self.setMinimumWidth(85)
        self.setMinimumHeight(280)
        self.setMaximumWidth(95)

    def set_distance(self, distance_hundredths_mm):
        """Set the current distance in 0.01mm units (0-400 for 0-4.0mm)"""
        self.distance_mm = distance_hundredths_mm / 100.0
        self.update()

    def set_calibration(self, rest, bottom, raw):
        """Set calibration debug values"""
        self.rest_adc = rest
        self.bottom_adc = bottom
        self.raw_adc = raw
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()

        # Check if light theme
        light_themes = ["Light", "Lavender Dream", "Mint Fresh", "Peachy Keen", "Sky Serenity", "Rose Garden"]
        is_light = Theme.get_theme() in light_themes

        # Margins - reduced for compact display
        margin_top = 20
        margin_bottom = 90  # Space for debug info
        margin_side = 5
        bar_width = width - 2 * margin_side
        bar_height = height - margin_top - margin_bottom

        # Draw label at top
        painter.setPen(QColor(60, 60, 60) if is_light else QColor(200, 200, 200))
        font = QFont()
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(0, 0, width, margin_top - 2, Qt.AlignCenter, self.label)

        # Draw outer frame (the track)
        track_rect = QtCore.QRectF(margin_side, margin_top, bar_width, bar_height)
        painter.setPen(QPen(QColor(150, 150, 150) if is_light else QColor(100, 100, 100), 2))
        painter.setBrush(QBrush(QColor(220, 220, 220) if is_light else QColor(40, 40, 40)))
        painter.drawRoundedRect(track_rect, 5, 5)

        # Calculate fill height based on distance (0mm = top, 4mm = bottom)
        fill_ratio = min(self.distance_mm / self.max_travel_mm, 1.0)
        fill_height = fill_ratio * (bar_height - 4)  # -4 for inner padding

        # Draw the fill bar (grows from top down as key is pressed)
        if fill_height > 0:
            fill_rect = QtCore.QRectF(
                margin_side + 2,
                margin_top + 2,
                bar_width - 4,
                fill_height
            )

            # Gradient color: green at top, yellow in middle, red at bottom
            gradient = QLinearGradient(0, margin_top, 0, margin_top + bar_height)
            gradient.setColorAt(0.0, QColor(0, 200, 0))      # Green at top (released)
            gradient.setColorAt(0.5, QColor(255, 200, 0))    # Yellow in middle
            gradient.setColorAt(1.0, QColor(255, 50, 50))    # Red at bottom (fully pressed)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(fill_rect, 3, 3)

        # Draw scale markers on the right side
        painter.setPen(QPen(QColor(100, 100, 100) if is_light else QColor(150, 150, 150), 1))
        small_font = QFont()
        small_font.setPointSize(7)
        painter.setFont(small_font)

        for mm in [0, 1, 2, 3, 4]:
            y_pos = margin_top + (mm / self.max_travel_mm) * bar_height
            # Draw tick mark
            painter.drawLine(int(width - margin_side + 2), int(y_pos),
                           int(width - margin_side + 6), int(y_pos))
            # Draw label
            painter.drawText(int(width - margin_side + 8), int(y_pos - 6),
                           30, 12, Qt.AlignLeft | Qt.AlignVCenter, f"{mm}")

        # Draw current distance value
        painter.setPen(QColor(0, 0, 0) if is_light else QColor(255, 255, 255))
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        distance_text = f"{self.distance_mm:.2f}mm"
        y_start = height - margin_bottom + 5
        painter.drawText(0, y_start, width, 18, Qt.AlignCenter, distance_text)

        # Draw calibration debug info
        small_font.setPointSize(7)
        small_font.setBold(False)
        painter.setFont(small_font)
        painter.setPen(QColor(80, 80, 80) if is_light else QColor(180, 180, 180))

        # Rest ADC
        painter.drawText(0, y_start + 20, width, 14, Qt.AlignCenter, f"Rest: {self.rest_adc}")
        # Bottom ADC
        painter.drawText(0, y_start + 34, width, 14, Qt.AlignCenter, f"Bot: {self.bottom_adc}")
        # Raw ADC (current)
        painter.setPen(QColor(100, 200, 255))  # Cyan for current reading
        painter.drawText(0, y_start + 48, width, 14, Qt.AlignCenter, f"Raw: {self.raw_adc}")
        # Calculated range
        painter.setPen(QColor(255, 200, 100))  # Orange for range
        range_val = self.rest_adc - self.bottom_adc if self.rest_adc > self.bottom_adc else 0
        painter.drawText(0, y_start + 62, width, 14, Qt.AlignCenter, f"Rng: {range_val}")


class EditableSlider(QSlider):
    """Custom slider with mousewheel step of 1"""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSingleStep(1)

    def wheelEvent(self, event):
        """Override wheel event to use step of 1"""
        delta = event.angleDelta().y()
        if delta > 0:
            self.setValue(self.value() + 1)
        elif delta < 0:
            self.setValue(self.value() - 1)
        event.accept()


class ClickableValueLabel(QLabel):
    """Label that opens input dialog on double-click to edit the value"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.linked_slider = None
        self.setCursor(Qt.PointingHandCursor)

    def set_linked_slider(self, slider):
        """Link this label to a slider for value editing"""
        self.linked_slider = slider

    def mouseDoubleClickEvent(self, event):
        """Open input dialog on double-click"""
        if self.linked_slider:
            value, ok = QInputDialog.getInt(
                self, "Set Value",
                "Enter percentage:",
                self.linked_slider.value(),
                self.linked_slider.minimum(),
                self.linked_slider.maximum(),
                1
            )
            if ok:
                self.linked_slider.setValue(value)
        event.accept()


class MatrixTest(BasicEditor):

    def __init__(self, layout_editor):
        super().__init__()

        self.layout_editor = layout_editor

        # Container for title, description, keyboard widget and buttons
        container = QWidget()
        container.setMinimumWidth(850)
        container_layout = QVBoxLayout()
        container_layout.setSpacing(10)
        container_layout.setContentsMargins(20, 20, 20, 20)
        container.setLayout(container_layout)

        # Title
        title_label = QLabel(tr("MatrixTest", "Matrix Tester"))
        title_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        container_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(tr("MatrixTest",
            "Test individual key switches by pressing them. Each key will light up when its switch\n"
            "is activated, helping identify faulty or stuck switches."))
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; font-size: 9pt;")
        desc_label.setAlignment(QtCore.Qt.AlignCenter)
        container_layout.addWidget(desc_label)

        self.KeyboardWidget2 = KeyboardWidgetSimple(layout_editor)
        self.KeyboardWidget2.set_enabled(False)

        self.unlock_btn = QPushButton("Unlock")
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setMinimumHeight(30)
        self.reset_btn.setMaximumHeight(30)
        self.reset_btn.setMinimumWidth(80)
        self.reset_btn.setStyleSheet("QPushButton { border-radius: 5px; }")

        # Vertical layout for keyboard widget then actuation visualizers below
        main_content_layout = QVBoxLayout()
        main_content_layout.setSpacing(15)

        # Keyboard widget centered
        self.KeyboardWidget2.setMinimumWidth(800)
        main_content_layout.addWidget(self.KeyboardWidget2, alignment=Qt.AlignCenter)

        # Show Advanced Tuning toggle button (above the hidden content)
        self.advanced_tuning_btn = QPushButton("Show Advanced Tuning")
        self.advanced_tuning_btn.setCheckable(True)
        self.advanced_tuning_btn.setMinimumWidth(200)
        self.advanced_tuning_btn.clicked.connect(self.toggle_advanced_tuning)
        main_content_layout.addWidget(self.advanced_tuning_btn, alignment=Qt.AlignCenter)

        # Combined container for key travel + EQ (both hidden by default)
        self.advanced_section_widget = QWidget()
        self.advanced_section_widget.setVisible(False)
        advanced_section_layout = QHBoxLayout()
        advanced_section_layout.setSpacing(30)
        advanced_section_layout.setContentsMargins(0, 10, 0, 0)
        self.advanced_section_widget.setLayout(advanced_section_layout)

        # Add stretch on left to center content
        advanced_section_layout.addStretch()

        # Actuation Visualizer section (in QGroupBox to align with EQ title)
        viz_group = QGroupBox(tr("MatrixTest", "Key Travel (mm)"))
        viz_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        visualizer_layout = QVBoxLayout()
        visualizer_layout.setSpacing(5)
        visualizer_layout.setContentsMargins(5, 5, 5, 5)
        viz_group.setLayout(visualizer_layout)

        # Create 4 visualizer slots with dropdown selectors
        self.actuation_visualizers = {}
        self.visualizer_widgets = []  # Store (viz, row_combo, col_combo) tuples
        self.distance_keys = []  # Will be populated dynamically

        visualizer_bars_layout = QHBoxLayout()
        visualizer_bars_layout.setSpacing(15)
        visualizer_bars_layout.setAlignment(Qt.AlignCenter)

        # Default keys to visualize (0-indexed internally, displayed as 1-indexed)
        default_keys = [(0, 0), (0, 3), (0, 11), (3, 0)]

        for idx, (default_row, default_col) in enumerate(default_keys):
            # Container for each visualizer + its dropdown
            viz_container = QWidget()
            viz_container.setFixedWidth(100)
            viz_layout = QVBoxLayout()
            viz_layout.setContentsMargins(0, 0, 0, 0)
            viz_layout.setSpacing(2)
            viz_container.setLayout(viz_layout)

            # Single key selector dropdown (Row X Col Y format)
            key_combo = QComboBox()
            key_combo.setStyleSheet("""
                QComboBox {
                    min-width: 85px;
                    max-width: 95px;
                    padding: 2px 2px 2px 4px;
                    font-size: 7pt;
                }
                QComboBox::drop-down {
                    width: 16px;
                }
            """)
            key_combo.setFixedWidth(95)
            key_combo.setMaximumHeight(22)
            key_combo.setMaxVisibleItems(10)

            # Add all row/col combinations (5 rows x 14 cols)
            default_index = 0
            for r in range(5):
                for c in range(14):
                    key_combo.addItem(f"Row {r+1} Col {c+1}", (r, c))
                    if r == default_row and c == default_col:
                        default_index = key_combo.count() - 1
            key_combo.setCurrentIndex(default_index)

            viz_layout.addWidget(key_combo)

            # Create the visualizer bar
            label = f"R{default_row + 1}C{default_col + 1}"
            viz = ActuationVisualizer(default_row, default_col, label)
            viz_layout.addWidget(viz)

            # Connect dropdown to update visualizer
            def make_key_updater(v, kc, i):
                def update():
                    row, col = kc.currentData()
                    v.row = row
                    v.col = col
                    v.label = f"R{row + 1}C{col + 1}"
                    self.update_distance_keys()
                return update

            key_combo.currentIndexChanged.connect(make_key_updater(viz, key_combo, idx))

            visualizer_bars_layout.addWidget(viz_container)

            self.visualizer_widgets.append((viz, key_combo))
            self.actuation_visualizers[(default_row, default_col)] = viz

        visualizer_layout.addLayout(visualizer_bars_layout)
        self.update_distance_keys()

        # Add visualizer to the advanced section
        advanced_section_layout.addWidget(viz_group)

        # Sensor Linearization group (to the right of key travel)
        lin_group = QGroupBox(tr("MatrixTest", "Sensor Linearization"))
        lin_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        lin_group.setMaximumWidth(320)
        lin_layout = QVBoxLayout()
        lin_layout.setSpacing(8)
        lin_group.setLayout(lin_layout)

        linearization_layout = QHBoxLayout()
        linearization_layout.setSpacing(10)

        linearization_label = QLabel("Strength:")
        linearization_label.setToolTip(
            "Blends between raw sensor ADC response and the calibrated\n"
            "physical-mm response derived from measured sensor data.\n"
            "0% = Raw linear ADC mapping (sensor non-linearity passes through)\n"
            "100% = Full measured linearization (each LUT step = real mm)"
        )
        linearization_layout.addWidget(linearization_label)

        self.lut_strength_slider = QSlider(Qt.Horizontal)
        self.lut_strength_slider.setMinimum(0)
        self.lut_strength_slider.setMaximum(100)
        self.lut_strength_slider.setValue(100)
        self.lut_strength_slider.setMaximumWidth(180)
        self.lut_strength_slider.setTickPosition(QSlider.TicksBelow)
        self.lut_strength_slider.setTickInterval(25)
        self.lut_strength_slider.valueChanged.connect(self.on_lut_strength_changed)
        linearization_layout.addWidget(self.lut_strength_slider)

        self.lut_strength_value_label = QLabel("100%")
        self.lut_strength_value_label.setStyleSheet("font-weight: bold; color: palette(highlight);")
        self.lut_strength_value_label.setMinimumWidth(35)
        linearization_layout.addWidget(self.lut_strength_value_label)

        linearization_layout.addStretch()
        lin_layout.addLayout(linearization_layout)
        lin_layout.addStretch()

        advanced_section_layout.addWidget(lin_group)

        # Add stretch on right to center content
        advanced_section_layout.addStretch()

        # Add the combined advanced section to main layout
        main_content_layout.addWidget(self.advanced_section_widget)

        # Add stretch to push content up when advanced section is hidden
        main_content_layout.addStretch()

        container_layout.addLayout(main_content_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.unlock_lbl = QLabel(tr("MatrixTest", "Unlock the keyboard before testing:"))
        btn_layout.addWidget(self.unlock_lbl)
        btn_layout.addWidget(self.unlock_btn)
        btn_layout.addWidget(self.reset_btn)
        container_layout.addLayout(btn_layout)

        # Wrap container in scroll area for resizable window
        scroll_area = QScrollArea()
        scroll_area.setWidget(container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.addWidget(scroll_area, stretch=1)

        self.keyboard = None
        self.device = None
        self.polling = False

        self.timer = QTimer()
        self.timer.timeout.connect(self.matrix_poller)

        # ADC polling timer - runs slower to avoid overloading HID
        self.adc_timer = QTimer()
        self.adc_timer.timeout.connect(self.adc_poller)
        self.adc_poll_half = 0  # 0 = first half of rows, 1 = second half

        # Distance polling timer for actuation visualizers - fast updates for real-time feel
        self.distance_timer = QTimer()
        self.distance_timer.timeout.connect(self.distance_poller)
        # Keys to poll for distance: [(row, col), ...]
        self.distance_keys = [(0, 0), (0, 3), (0, 11), (3, 0)]

        self.unlock_btn.clicked.connect(self.unlock)
        self.reset_btn.clicked.connect(self.reset_keyboard_widget)

        self.grabber = QWidget()

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard

            self.KeyboardWidget2.set_keys(self.keyboard.keys, self.keyboard.encoders)
        self.KeyboardWidget2.setEnabled(self.valid())

    def valid(self):
        # Check if vial protocol is v3 or later
        return isinstance(self.device, VialKeyboard) and \
               (self.device.keyboard and self.device.keyboard.vial_protocol >= VIAL_PROTOCOL_MATRIX_TESTER) and \
               ((self.device.keyboard.cols // 8 + 1) * self.device.keyboard.rows <= 28)

    def reset_keyboard_widget(self):
        # reset keyboard widget
        for w in self.KeyboardWidget2.widgets:
            w.setPressed(False)
            w.setOn(False)
            w.setAdcValue(None)  # Clear ADC values

        # Reset actuation visualizers
        for viz in self.actuation_visualizers.values():
            viz.set_distance(0)

        self.KeyboardWidget2.update_layout()
        self.KeyboardWidget2.update()
        self.KeyboardWidget2.updateGeometry()

    def matrix_poller(self):
        # A loop transfer owns the HID handle; skip this tick (timer keeps
        # running, so polling resumes when the transfer finishes). (H3)
        if is_hid_transfer_active():
            return
        if not self.valid():
            self.timer.stop()
            return

        try:
            unlocked = self.keyboard.get_unlock_status(3)
        except (RuntimeError, ValueError):
            self.timer.stop()
            return

        if not unlocked:
            self.unlock_btn.show()
            self.unlock_lbl.show()
            return

        # we're unlocked, so hide unlock button and label
        self.unlock_btn.hide()
        self.unlock_lbl.hide()

        # Get size for matrix
        rows = self.keyboard.rows
        cols = self.keyboard.cols
        # Generate 2d array of matrix
        matrix = [[None] * cols for x in range(rows)]

        # Get matrix data from keyboard
        try:
            data = self.keyboard.matrix_poll()
        except (RuntimeError, ValueError):
            self.timer.stop()
            return

        # Calculate the amount of bytes belong to 1 row, each bit is 1 key, so per 8 keys in a row,
        # a byte is needed for the row.
        row_size = math.ceil(cols / 8)

        for row in range(rows):
            # Make slice of bytes for the row (skip first 2 bytes, they're for VIAL)
            row_data_start = 2 + (row * row_size)
            row_data_end = row_data_start + row_size
            row_data = data[row_data_start:row_data_end]

            # Get each bit representing pressed state for col
            for col in range(cols):
                # row_data is array of bytes, calculate in which byte the col is located
                col_byte = len(row_data) - 1 - math.floor(col / 8)
                # since we select a single byte as slice of byte, mod 8 to get nth pos of byte
                col_mod = (col % 8)
                # write to matrix array
                matrix[row][col] = (row_data[col_byte] >> col_mod) & 1

        # write matrix state to keyboard widget
        for w in self.KeyboardWidget2.widgets:
            if w.desc.row is not None and w.desc.col is not None:
                row = w.desc.row
                col = w.desc.col

                if row < len(matrix) and col < len(matrix[row]):
                    w.setPressed(matrix[row][col])
                    if matrix[row][col]:
                        w.setOn(True)

        self.KeyboardWidget2.update_layout()
        self.KeyboardWidget2.update()
        self.KeyboardWidget2.updateGeometry()

    def adc_poller(self):
        """Poll ADC values for half the matrix rows each cycle"""
        if is_hid_transfer_active():  # transfer owns the HID handle; skip (H3)
            return
        if not self.valid():
            self.adc_timer.stop()
            return

        try:
            unlocked = self.keyboard.get_unlock_status(1)
        except (RuntimeError, ValueError):
            self.adc_timer.stop()  # device gone (e.g. unplug) — stop polling like matrix_poller does
            return

        if not unlocked:
            return

        rows = self.keyboard.rows
        cols = self.keyboard.cols

        # Determine which rows to poll this cycle (alternate between first and second half)
        half_rows = (rows + 1) // 2  # Round up for odd number of rows
        if self.adc_poll_half == 0:
            row_start = 0
            row_end = half_rows
        else:
            row_start = half_rows
            row_end = rows

        # Poll ADC values for the selected rows
        adc_matrix = {}
        for row in range(row_start, row_end):
            try:
                adc_values = self.keyboard.adc_matrix_poll(row)
                if adc_values:
                    adc_matrix[row] = adc_values
            except (RuntimeError, ValueError):
                continue

        # Poll final column (col 13) separately using calibration_debug_poll
        # since adc_matrix_poll is limited to 13 columns due to HID packet size
        if cols > 13:
            final_col = cols - 1  # Column 13 for 14-column keyboard
            # Build list of keys for final column in the rows we're polling
            final_col_keys = [(row, final_col) for row in range(row_start, row_end)]
            # Poll in batches of 4 (calibration_debug_poll limit)
            for i in range(0, len(final_col_keys), 4):
                batch = final_col_keys[i:i+4]
                try:
                    calib_data = self.keyboard.calibration_debug_poll(batch)
                    if calib_data:
                        for (row, col), data in calib_data.items():
                            if row not in adc_matrix:
                                adc_matrix[row] = [0] * cols
                            # Extend the list if needed
                            while len(adc_matrix[row]) <= col:
                                adc_matrix[row].append(0)
                            adc_matrix[row][col] = data['raw']
                except (RuntimeError, ValueError):
                    pass

        # Update keyboard widget with ADC values
        for w in self.KeyboardWidget2.widgets:
            if w.desc.row is not None and w.desc.col is not None:
                row = w.desc.row
                col = w.desc.col

                # Only update keys in the rows we just polled
                if row in adc_matrix and col < len(adc_matrix[row]):
                    w.setAdcValue(adc_matrix[row][col])

        # Alternate to the other half for next poll
        self.adc_poll_half = 1 - self.adc_poll_half

        self.KeyboardWidget2.update()

    def distance_poller(self):
        """Poll distance and calibration values for specific keys to update actuation visualizers"""
        if is_hid_transfer_active():  # transfer owns the HID handle; skip (H3)
            return
        if not self.valid():
            self.distance_timer.stop()
            return

        try:
            unlocked = self.keyboard.get_unlock_status(1)
        except (RuntimeError, ValueError):
            self.distance_timer.stop()  # device gone (e.g. unplug) — stop polling like matrix_poller does
            return

        if not unlocked:
            return

        # Poll distance values for the visualized keys
        try:
            distances = self.keyboard.distance_matrix_poll(self.distance_keys)
            if distances:
                for (row, col), distance in distances.items():
                    if (row, col) in self.actuation_visualizers:
                        self.actuation_visualizers[(row, col)].set_distance(distance)
        except (RuntimeError, ValueError):
            pass

        # Poll calibration debug values (less frequently - every other call)
        if not hasattr(self, '_calib_poll_counter'):
            self._calib_poll_counter = 0
        self._calib_poll_counter += 1

        if self._calib_poll_counter >= 4:  # Every 4th poll (~200ms)
            self._calib_poll_counter = 0
            try:
                calibration = self.keyboard.calibration_debug_poll(self.distance_keys)
                if calibration:
                    for (row, col), calib in calibration.items():
                        if (row, col) in self.actuation_visualizers:
                            self.actuation_visualizers[(row, col)].set_calibration(
                                calib['rest'], calib['bottom'], calib['raw']
                            )
            except (RuntimeError, ValueError):
                pass

    def toggle_advanced_tuning(self):
        """Toggle visibility of key travel and EQ tuning section"""
        visible = self.advanced_tuning_btn.isChecked()
        self.advanced_section_widget.setVisible(visible)
        if visible:
            self.advanced_tuning_btn.setText("Hide Advanced Tuning")
        else:
            self.advanced_tuning_btn.setText("Show Advanced Tuning")

    def on_lut_strength_changed(self, value):
        """Handle LUT correction strength slider change - immediate send to keyboard"""
        self.lut_strength_value_label.setText(f"{value}%")

        # Send immediately to keyboard (global setting, no save required)
        if self.device and isinstance(self.device, VialKeyboard):
            from protocol.keyboard_comm import PARAM_LUT_CORRECTION_STRENGTH
            self.device.keyboard.set_keyboard_param_single(PARAM_LUT_CORRECTION_STRENGTH, value)

    def update_distance_keys(self):
        """Update the distance_keys list and actuation_visualizers dict based on dropdown selections"""
        # Clear and rebuild
        self.distance_keys = []
        self.actuation_visualizers = {}

        for viz, key_combo in self.visualizer_widgets:
            key = key_combo.currentData()  # Returns (row, col) tuple
            self.distance_keys.append(key)
            self.actuation_visualizers[key] = viz

    def unlock(self):
        Unlocker.unlock(self.keyboard)

    def activate(self):
        self.grabber.grabKeyboard()
        self.timer.start(20)
        # Start ADC polling at 500ms intervals (slower to avoid HID overload)
        self.adc_poll_half = 0  # Reset to first half
        self.adc_timer.start(500)
        # Start distance polling at 50ms intervals for smooth visualization
        self.distance_timer.start(50)

    def deactivate(self):
        self.grabber.releaseKeyboard()
        self.timer.stop()
        self.adc_timer.stop()
        self.distance_timer.stop()
        # Clear ADC values when leaving the matrix tester
        for w in self.KeyboardWidget2.widgets:
            w.setAdcValue(None)
        # Reset actuation visualizers
        for viz in self.actuation_visualizers.values():
            viz.set_distance(0)


class ThruLoopConfigurator(BasicEditor):

    def __init__(self):
        super().__init__()

        self.single_loopchop_label = None
        self.master_cc = None
        self.single_loopchop_widgets = []
        self.nav_widget = None

        self.setup_ui()

    def setup_ui(self):
        # Create scroll area for better window resizing
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        main_widget = QWidget()
        outer_layout = QVBoxLayout()  # Outer layout for title + content
        outer_layout.setSpacing(15)
        main_widget.setLayout(outer_layout)

        scroll_area.setWidget(main_widget)
        self.addWidget(scroll_area, 1)

        # TOP: Title and Description (centered)
        title_container = QWidget()
        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_container.setLayout(title_layout)

        title_label = QLabel(tr("ThruLoopConfigurator", "ThruLoop"))
        title_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        title_layout.addWidget(title_label)

        desc_label = QLabel(tr("ThruLoopConfigurator",
            "Configure the 8 ThruLoop tracks (keycodes DM_THRULOOP_1-8) and LoopChop navigation. "
            "ThruLoop tracks are silent CC-only loops: they record their own timing and emit "
            "these CCs to sync external gear — the regular MIDI loops no longer send them. "
            "Each Thru column maps to one track; Overdub rows fire on the held Overdub button."))
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; font-size: 9pt;")
        desc_label.setAlignment(QtCore.Qt.AlignCenter)
        title_layout.addWidget(desc_label)

        outer_layout.addWidget(title_container)

        # COLUMNS: Left (Basic Settings + LoopChop) | Right (Main Functions)
        main_h_layout = QHBoxLayout()
        main_h_layout.setSpacing(15)
        outer_layout.addLayout(main_h_layout)

        # LEFT COLUMN: Basic Settings + LoopChop (400px width)
        left_column = QVBoxLayout()
        left_column.setSpacing(8)

        # Basic Settings Group
        self.basic_group = QGroupBox(tr("ThruLoopConfigurator", "Basic Settings"))
        self.basic_group.setFixedWidth(400)
        basic_layout = QGridLayout()
        self.basic_group.setLayout(basic_layout)
        left_column.addWidget(self.basic_group)

        # ThruLoop Channel
        basic_layout.addWidget(QLabel(tr("ThruLoopConfigurator", "ThruLoop Channel")), 0, 0)
        self.loop_channel = ArrowComboBox()
        self.loop_channel.setMinimumWidth(150)
        self.loop_channel.setMaximumHeight(30)
        self.loop_channel.setEditable(True)
        self.loop_channel.lineEdit().setReadOnly(True)
        self.loop_channel.lineEdit().setAlignment(Qt.AlignCenter)
        for i in range(1, 17):
            self.loop_channel.addItem(f"Channel {i}", i)
        self.loop_channel.setCurrentIndex(15)
        basic_layout.addWidget(self.loop_channel, 0, 1)

        # Send Restart Messages and Alternate Restart Mode (side by side)
        basic_layout.addWidget(QLabel(tr("ThruLoopConfigurator", "Restart Settings:")), 1, 0, 1, 2)

        self.sync_midi = QCheckBox(tr("ThruLoopConfigurator", "Send Restart Messages"))
        basic_layout.addWidget(self.sync_midi, 2, 0)

        self.alternate_restart = QCheckBox(tr("ThruLoopConfigurator", "Alternate Restart Mode"))
        basic_layout.addWidget(self.alternate_restart, 2, 1)

        self.macro_sync_to_loop = QCheckBox(tr("ThruLoopConfigurator", "Sync Macros"))
        self.macro_sync_to_loop.setToolTip("Global master override: when ON every macro defers until the next loop trigger, regardless of its per-macro sync bit (which is set from Vial per keycode)")
        self.macro_sync_to_loop.stateChanged.connect(self.on_macro_sync_changed)
        basic_layout.addWidget(self.macro_sync_to_loop, 3, 0, 1, 2)

        # LoopChop Settings (below Basic Settings in left column)
        self.loopchop_group = QGroupBox(tr("ThruLoopConfigurator", "LoopChop"))
        self.loopchop_group.setFixedWidth(400)
        loopchop_layout = QGridLayout()
        loopchop_layout.setSpacing(5)
        loopchop_layout.setContentsMargins(10, 10, 10, 10)
        self.loopchop_group.setLayout(loopchop_layout)
        left_column.addWidget(self.loopchop_group)

        # Separate CCs for LoopChop checkbox
        self.separate_loopchop = QCheckBox(tr("ThruLoopConfigurator", "Separate CCs for LoopChop"))
        loopchop_layout.addWidget(self.separate_loopchop, 0, 0, 1, 4)

        # Single LoopChop CC - Always visible
        self.single_loopchop_label = QLabel(tr("ThruLoopConfigurator", "Loop Chop"))
        loopchop_layout.addWidget(self.single_loopchop_label, 1, 0)
        self.master_cc = self.create_cc_combo(narrow=True)
        loopchop_layout.addWidget(self.master_cc, 1, 1, 1, 3, Qt.AlignLeft)

        # Individual LoopChop CCs (8 navigation CCs) - More compact layout
        nav_layout = QGridLayout()
        nav_layout.setSpacing(3)
        self.nav_combos = []
        for i in range(8):
            row = i // 4
            col = i % 4
            label = QLabel(f"{i}/8")
            label.setMaximumWidth(30)
            nav_layout.addWidget(label, row * 2, col)
            combo = self.create_cc_combo(narrow=True)
            nav_layout.addWidget(combo, row * 2 + 1, col)
            self.nav_combos.append(combo)

        self.nav_widget = QWidget()
        self.nav_widget.setLayout(nav_layout)
        loopchop_layout.addWidget(self.nav_widget, 2, 0, 1, 4)

        left_column.addStretch()
        main_h_layout.addLayout(left_column)

        # RIGHT COLUMN: Main Functions (1150px width, 8 columns)
        right_column = QVBoxLayout()
        right_column.setSpacing(8)

        self.main_group = QGroupBox(tr("ThruLoopConfigurator", "Main Functions"))
        self.main_group.setFixedWidth(1150)
        main_group_layout = QVBoxLayout()
        main_group_layout.setSpacing(5)
        main_group_layout.setContentsMargins(10, 8, 10, 10)
        self.main_group.setLayout(main_group_layout)

        # Main Functions grid
        main_grid = QGridLayout()
        main_grid.setSpacing(5)
        main_grid.setContentsMargins(0, 0, 0, 0)

        # Add column headers (one per ThruLoop track 1-8)
        for col in range(8):
            header = QLabel(f"Thru {col + 1}")
            header.setAlignment(QtCore.Qt.AlignCenter)
            header.setStyleSheet("font-weight: bold;")
            main_grid.addWidget(header, 0, col + 1)

        # Add function rows
        functions = ["Start Recording", "Stop Recording", "Start Playing", "Stop Playing", "Clear", "Restart"]
        self.main_combos = []
        for row_idx, func_name in enumerate(functions):
            # Row label
            label = QLabel(func_name)
            label.setStyleSheet("font-weight: bold;")
            main_grid.addWidget(label, row_idx + 1, 0)

            # Combo boxes for each loop
            row_combos = []
            for col_idx in range(8):
                combo = self.create_cc_combo(for_table=True)
                main_grid.addWidget(combo, row_idx + 1, col_idx + 1)
                row_combos.append(combo)
            self.main_combos.append(row_combos)

        main_group_layout.addLayout(main_grid)

        # Separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_group_layout.addWidget(separator)

        # Overdub Functions section
        overdub_grid = QGridLayout()
        overdub_grid.setSpacing(5)
        overdub_grid.setContentsMargins(0, 0, 0, 0)

        # Add column headers
        for col in range(8):
            header = QLabel(f"Overdub {col + 1}")
            header.setAlignment(QtCore.Qt.AlignCenter)
            header.setStyleSheet("font-weight: bold;")
            overdub_grid.addWidget(header, 0, col + 1)

        # Add function rows (same as main functions)
        self.overdub_combos = []
        for row_idx, func_name in enumerate(functions):
            # Row label
            label = QLabel(func_name)
            label.setStyleSheet("font-weight: bold;")
            overdub_grid.addWidget(label, row_idx + 1, 0)

            # Combo boxes for each loop
            row_combos = []
            for col_idx in range(8):
                combo = self.create_cc_combo(for_table=True)
                overdub_grid.addWidget(combo, row_idx + 1, col_idx + 1)
                row_combos.append(combo)
            self.overdub_combos.append(row_combos)

        main_group_layout.addLayout(overdub_grid)
        right_column.addWidget(self.main_group)
        right_column.addStretch()
        main_h_layout.addLayout(right_column)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        # Button style - bigger and less rounded
        button_style = "QPushButton { border-radius: 3px; padding: 8px 16px; }"

        save_btn = QPushButton(tr("ThruLoopConfigurator", "Save Configuration"))
        save_btn.setMinimumHeight(45)
        save_btn.setMinimumWidth(200)
        save_btn.setStyleSheet(button_style)
        save_btn.clicked.connect(self.on_save)
        buttons_layout.addWidget(save_btn)

        load_btn = QPushButton(tr("ThruLoopConfigurator", "Load from Keyboard"))
        load_btn.setMinimumHeight(45)
        load_btn.setMinimumWidth(210)
        load_btn.setStyleSheet(button_style)
        load_btn.clicked.connect(self.on_load_from_keyboard)
        buttons_layout.addWidget(load_btn)

        reset_btn = QPushButton(tr("ThruLoopConfigurator", "Reset to Defaults"))
        reset_btn.setMinimumHeight(45)
        reset_btn.setMinimumWidth(180)
        reset_btn.setStyleSheet(button_style)
        reset_btn.clicked.connect(self.on_reset)
        buttons_layout.addWidget(reset_btn)

        self.addLayout(buttons_layout)
        
        # Apply stylesheet to prevent bold focus styling and center combo box text
        main_widget.setStyleSheet("""
            QCheckBox:focus {
                font-weight: normal;
                outline: none;
            }
            QPushButton:focus {
                font-weight: normal;
                outline: none;
            }
            QComboBox {
                text-align: center;
            }
            QComboBox:focus {
                font-weight: normal;
                outline: none;
            }
        """)
        
        # Connect signals AFTER all widgets are created
        self.separate_loopchop.stateChanged.connect(self.on_separate_loopchop_changed)

        # Initialize UI state AFTER all widgets and connections are set up
        self.on_separate_loopchop_changed()
        
    def create_cc_combo(self, for_table=False, narrow=False):
        """Create a CC selector combobox

        Args:
            for_table: If True, creates a narrower combo for use in tables
            narrow: If True, creates an even narrower combo (80px max)
        """
        combo = ArrowComboBox()
        if narrow:
            # Override global stylesheet min-width and padding to allow 80px max
            combo.setStyleSheet("""
                QComboBox {
                    min-width: 0px;
                    max-width: 80px;
                    padding: 4px 6px;
                    padding-right: 20px;
                }
            """)
            combo.setMaximumWidth(80)
            combo.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        elif for_table:
            combo.setMaximumWidth(80)  # Narrower for tables to show arrow
        else:
            combo.setMinimumWidth(120)
        combo.setMaximumHeight(30)
        combo.setEditable(True)
        combo.lineEdit().setReadOnly(True)
        combo.lineEdit().setAlignment(Qt.AlignCenter)

        # Add "None" option
        combo.addItem("None", 128)

        # Add CC options
        for cc_num in range(128):
            combo.addItem(f"CC# {cc_num}", cc_num)

        combo.setCurrentIndex(0)
        return combo
    
    def get_cc_value(self, combo):
        """Get the current CC value from a CC combo"""
        return combo.currentData()
    
    def set_cc_value(self, combo, value):
        """Set the CC value for a combo"""
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)
    
    def on_separate_loopchop_changed(self):
        separate = self.separate_loopchop.isChecked()
        if self.single_loopchop_label:
            self.single_loopchop_label.setEnabled(not separate)
        if self.master_cc:
            self.master_cc.setEnabled(not separate)
        if self.nav_widget:
            self.nav_widget.setEnabled(separate)

    def on_macro_sync_changed(self):
        """Send macro sync to loop setting to keyboard in real-time"""
        if self.device and isinstance(self.device, VialKeyboard):
            from protocol.keyboard_comm import PARAM_MACRO_SYNC_TO_LOOP
            self.device.keyboard.set_keyboard_param_single(
                PARAM_MACRO_SYNC_TO_LOOP, 1 if self.macro_sync_to_loop.isChecked() else 0)

    def get_combos_cc_values(self, combos_array):
        """Get CC values from a 2D array of combos"""
        values = []
        for row_combos in combos_array:
            for combo in row_combos:
                values.append(self.get_cc_value(combo))
        return values

    def set_combos_cc_values(self, combos_array, values):
        """Set CC values to a 2D array of combos"""
        idx = 0
        for row_combos in combos_array:
            for combo in row_combos:
                if idx < len(values):
                    self.set_cc_value(combo, values[idx])
                    idx += 1

    def get_combos_cc_values_banked(self, combos_array):
        """Flatten a [function][track] combo grid into the firmware's BANKED
        wire order. The firmware (handle_set_main_loop_ccs / handle_set_overdub_ccs
        in process_dynamic_macro.c) reads each HID packet as one bank of 4 tracks
        laid out function-major: data[0..3]=func0 for those 4 tracks, data[4..7]=
        func1, etc. The full stream is bank0 (tracks 1-4) then bank1 (tracks 5-8).
        The plain row-major get_combos_cc_values() does NOT match this, which is
        what scrambled the ThruLoop CC assignments."""
        values = []
        for bank in range(2):                  # bank 0 = tracks 0-3, bank 1 = tracks 4-7
            for row_combos in combos_array:    # one row per function (function-major within a bank)
                for j in range(4):             # 4 tracks within the bank
                    values.append(self.get_cc_value(row_combos[bank * 4 + j]))
        return values

    def set_combos_cc_values_banked(self, combos_array, values):
        """Inverse of get_combos_cc_values_banked: scatter a firmware-order banked
        stream (bank0 tracks 1-4, then bank1 tracks 5-8; function-major within each
        bank) back into the [function][track] combo grid."""
        idx = 0
        for bank in range(2):
            for row_combos in combos_array:
                for j in range(4):
                    if idx < len(values):
                        self.set_cc_value(row_combos[bank * 4 + j], values[idx])
                        idx += 1

    def get_restart_cc_values(self):
        """Get restart CCs from the main combos (last row)"""
        restart_values = []
        for col in range(8):
            combo = self.main_combos[5][col]  # Row 5 is "Restart"
            restart_values.append(self.get_cc_value(combo))
        return restart_values

    def set_restart_cc_values(self, values):
        """Set restart CCs in the main combos (last row)"""
        for col in range(8):
            if col < len(values):
                combo = self.main_combos[5][col]  # Row 5 is "Restart"
                self.set_cc_value(combo, values[col])
    
    def on_save(self):
        """Save all configuration to keyboard"""
        try:
            if not self.device or not isinstance(self.device, VialKeyboard):
                raise RuntimeError("Device not connected")
            
            # 1. Send basic loop configuration
            # Note: loop_enabled and cc_loop_recording are now in MIDI Settings
            loop_config_data = [
                self.loop_channel.currentData(),
                1 if self.sync_midi.isChecked() else 0,
                1 if self.alternate_restart.isChecked() else 0,
            ]
            # Add restart CCs from main table
            restart_values = self.get_restart_cc_values()
            loop_config_data.extend(restart_values)
            
            if not self.device.keyboard.set_thruloop_config(loop_config_data):
                raise RuntimeError("Failed to set ThruLoop config")
            
            # 2. Send main loop CCs (excluding restart row - first 5 rows only, 5 rows x 8 cols = 40 values)
            #    Banked order so it matches the firmware's per-bank packet layout.
            main_values = self.get_combos_cc_values_banked(self.main_combos[:5])  # First 5 rows

            if not self.device.keyboard.set_thruloop_main_ccs(main_values):
                raise RuntimeError("Failed to set main CCs")

            # 3. Send overdub CCs (all 6 rows x 8 cols = 48 values total), banked order
            overdub_values = self.get_combos_cc_values_banked(self.overdub_combos)
            if not self.device.keyboard.set_thruloop_overdub_ccs(overdub_values):
                raise RuntimeError("Failed to set overdub CCs")
            
            # 4. Send navigation configuration
            nav_config_data = [
                1 if self.separate_loopchop.isChecked() else 0,
                self.get_cc_value(self.master_cc),
            ]
            for combo in self.nav_combos:
                nav_config_data.append(self.get_cc_value(combo))
            
            if not self.device.keyboard.set_thruloop_navigation(nav_config_data):
                raise RuntimeError("Failed to set navigation config")

            # 5. Send macro sync to loop setting via param single
            from protocol.keyboard_comm import PARAM_MACRO_SYNC_TO_LOOP
            self.device.keyboard.set_keyboard_param_single(
                PARAM_MACRO_SYNC_TO_LOOP, 1 if self.macro_sync_to_loop.isChecked() else 0)

        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to save configuration: {str(e)}")   
        
    def on_load_from_keyboard(self):
        """Load configuration from keyboard using multi-packet collection"""
        try:
            if not self.device or not isinstance(self.device, VialKeyboard):
                raise RuntimeError("Device not connected")
                
            # Request and collect multi-packet configuration
            config = self.device.keyboard.get_thruloop_config()
            
            if not config:
                raise RuntimeError("Failed to load config from keyboard")
            
            # Apply the configuration to the UI
            self.apply_config(config)
                
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to load from keyboard: {str(e)}")
    
    def apply_config(self, config):
        """Apply configuration dictionary to UI"""
        # Basic settings (loop_enabled and cc_loop_recording now in MIDI Settings)
        if 'loopChannel' in config:
            for i in range(self.loop_channel.count()):
                if self.loop_channel.itemData(i) == config.get("loopChannel", 16):
                    self.loop_channel.setCurrentIndex(i)
                    break
        
        if 'syncMidi' in config:
            self.sync_midi.setChecked(config.get("syncMidi", False))
        if 'alternateRestart' in config:
            self.alternate_restart.setChecked(config.get("alternateRestart", False))
        
        # LoopChop settings
        if 'separateLoopChopCC' in config:
            self.separate_loopchop.setChecked(config.get("separateLoopChopCC", False))
        if 'masterCC' in config:
            self.set_cc_value(self.master_cc, config.get("masterCC", 128))
        
        # Set restart CCs
        if 'restartCCs' in config:
            restart_ccs = config.get("restartCCs", [128] * 8)
            self.set_restart_cc_values(restart_ccs)

        # Set main combos CCs (first 5 rows only, 5 x 8 = 40 values).
        # config['mainCCs'] arrives in firmware banked order (bank0 then bank1),
        # so scatter it back with the banked setter.
        if 'mainCCs' in config:
            main_ccs = config.get("mainCCs", [128] * 40)
            self.set_combos_cc_values_banked(self.main_combos[:5], main_ccs)

        # Set overdub combos CCs (all 6 rows x 8 cols = 48 values), banked order
        if 'overdubCCs' in config:
            overdub_ccs = config.get("overdubCCs", [128] * 48)
            self.set_combos_cc_values_banked(self.overdub_combos, overdub_ccs)
        
        # Set navigation CCs
        if 'navCCs' in config:
            nav_ccs = config.get("navCCs", [128] * 8)
            for i, combo in enumerate(self.nav_combos):
                if i < len(nav_ccs):
                    self.set_cc_value(combo, nav_ccs[i])
        
        # Update UI state
        self.on_separate_loopchop_changed()
        
    def on_reset(self):
        """Reset ThruLoop configuration to defaults"""
        try:
            reply = QMessageBox.question(None, "Confirm Reset", 
                                       "Reset ThruLoop configuration to defaults? This cannot be undone.",
                                       QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                if not self.device or not isinstance(self.device, VialKeyboard):
                    raise RuntimeError("Device not connected")
                    
                if not self.device.keyboard.reset_thruloop_config():
                    raise RuntimeError("Failed to reset ThruLoop config")
                    
                self.reset_ui_to_defaults()
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to reset configuration: {str(e)}")
    
    def reset_ui_to_defaults(self):
        """Reset UI to default values"""
        self.loop_channel.setCurrentIndex(15)
        self.sync_midi.setChecked(False)
        self.alternate_restart.setChecked(False)
        self.separate_loopchop.setChecked(False)
        self.set_cc_value(self.master_cc, 128)

        # Reset all combos to None (128)
        for row_combos in self.main_combos:
            for combo in row_combos:
                self.set_cc_value(combo, 128)

        for row_combos in self.overdub_combos:
            for combo in row_combos:
                self.set_cc_value(combo, 128)

        for combo in self.nav_combos:
            self.set_cc_value(combo, 128)

        self.on_separate_loopchop_changed()
    
    def get_current_config(self):
        """Get current UI configuration as dictionary"""
        config = {
            "version": "1.0",
            "loopChannel": self.loop_channel.currentData(),
            "syncMidi": self.sync_midi.isChecked(),
            "alternateRestart": self.alternate_restart.isChecked(),
            "separateLoopChopCC": self.separate_loopchop.isChecked(),
            "masterCC": self.get_cc_value(self.master_cc),
            "restartCCs": self.get_restart_cc_values(),
            "mainCCs": self.get_combos_cc_values(self.main_combos[:5]),  # First 5 rows x 8 cols = 40 values
            "overdubCCs": self.get_combos_cc_values(self.overdub_combos),  # All 6 rows x 8 cols = 48 values
            "navCCs": [self.get_cc_value(combo) for combo in self.nav_combos]
        }
        return config
    
    def valid(self):
        return isinstance(self.device, VialKeyboard)

    def rebuild(self, device):
        super().rebuild(device)
        if not self.valid():
            return

        # Load ThruLoop configuration from keyboard
        if hasattr(self.device.keyboard, 'thruloop_config') and self.device.keyboard.thruloop_config:
            self.apply_config(self.device.keyboard.thruloop_config)

class MIDIswitchSettingsConfigurator(BasicEditor):

    # Per-function Stop Mode bits — mirror the firmware STOP_MODE_* defines
    # (process_dynamic_macro.h). Bit CLEAR = Mute (default), bit SET = Stop.
    STOP_MODE_LOOP     = 0x01
    STOP_MODE_THRULOOP = 0x02
    STOP_MODE_SEQ      = 0x04
    STOP_MODE_DRUM     = 0x08
    STOP_MODE_CPROG    = 0x10
    STOP_MODE_MASK_ALL = 0x1F

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def get_stop_mode_mask(self):
        """Build the 5-bit Stop Mode bitmask from the per-family combos."""
        mask = 0
        for bit, combo in self.stop_mode_combos.items():
            if combo.currentData():
                mask |= bit
        return mask & self.STOP_MODE_MASK_ALL

    def _apply_stop_mode(self, mask, supported):
        """Populate the Stop Mode combos from a firmware bitmask.

        supported=False means the connected firmware predates Stop Mode
        (GET byte 20 had bit 7 clear): show the all-Mute defaults and
        disable the combos so nothing misleading can be edited.
        """
        self.stop_mode_supported = bool(supported)
        if not supported:
            mask = 0
        for bit, combo in self.stop_mode_combos.items():
            combo.blockSignals(True)
            combo.setCurrentIndex(1 if (mask & bit) else 0)
            combo.blockSignals(False)
            combo.setEnabled(self.stop_mode_supported)

    def on_lcd_theme_changed(self, index):
        """LCD colour theme changed - apply immediately to the keyboard.

        Global setting (own EEPROM region + dedicated HID command), so it takes
        effect and persists right away without the Save button.
        """
        if self.device and isinstance(self.device, VialKeyboard):
            theme_idx = self.lcd_theme.currentData()
            if theme_idx is not None:
                self.device.keyboard.set_lcd_theme(theme_idx)

    def _on_channel_artic_enable_changed(self, index):
        """Enable Channel Articulations changed - write immediately to the device.

        Global setting (own EEPROM region + dedicated HID command). Reads the
        current channel->articulation map first so only the enable flag changes,
        then writes both back (the firmware persists it on-device).
        """
        if not (self.device and isinstance(self.device, VialKeyboard)):
            return
        enabled = bool(self.enable_channel_artic.currentData())
        try:
            cur = self.device.keyboard.get_channel_articulations()
            artic_map = cur['map'] if cur else [0xFF] * 16
            cc = cur['articulation_cc'] if cur else 1
            self.device.keyboard.set_channel_articulations(enabled, artic_map, cc)
        except Exception:
            pass

    def _on_articulation_cc_changed(self, index):
        """Global Articulation CC changed - write immediately (preserving the map
        + enable flag)."""
        if not (self.device and isinstance(self.device, VialKeyboard)):
            return
        cc = self.articulation_cc_combo.currentData()
        if cc is None:
            return
        try:
            cur = self.device.keyboard.get_channel_articulations()
            enabled = cur['enabled'] if cur else False
            artic_map = cur['map'] if cur else [0xFF] * 16
            self.device.keyboard.set_channel_articulations(enabled, artic_map, cc)
        except Exception:
            pass

    def create_help_label(self, tooltip_text):
        """Create a small question mark button with tooltip for help"""
        help_btn = QPushButton("?")
        help_btn.setStyleSheet("""
            QPushButton {
                color: #888;
                font-weight: bold;
                font-size: 10pt;
                border: 1px solid #888;
                border-radius: 9px;
                min-width: 18px;
                max-width: 18px;
                min-height: 18px;
                max-height: 18px;
                padding: 0px;
                margin: 0px;
                background: transparent;
            }
            QPushButton:hover {
                color: #fff;
                background-color: #555;
                border-color: #fff;
            }
        """)
        help_btn.setToolTip(tooltip_text)
        help_btn.setFocusPolicy(Qt.NoFocus)
        return help_btn

    def create_label_with_help(self, text, tooltip_text):
        """Create a horizontal layout with label and help icon"""
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        label = QLabel(text)
        help_icon = self.create_help_label(tooltip_text)

        layout.addWidget(help_icon)
        layout.addWidget(label)
        layout.addStretch()
        container.setLayout(layout)
        return container

    def setup_ui(self):
        # Create tab widget for MIDI Settings and ThruLoop sub-tabs
        self.tabs_widget = QTabWidget()
        self.addWidget(self.tabs_widget)

        # Tab 1: MIDI Settings
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        scroll_area.setWidget(main_widget)
        self.tabs_widget.addTab(scroll_area, "MIDI Settings")

        main_layout.addSpacing(10)

        # Global MIDI Settings Group - contains title/description on left, then base settings, keysplit, and triplesplit
        global_midi_group = QGroupBox()
        global_midi_group_layout = QHBoxLayout()
        global_midi_group_layout.setSpacing(15)
        global_midi_group.setLayout(global_midi_group_layout)

        # MIDI Settings title and description container (left side)
        midi_title_container = QWidget()
        midi_title_container.setMaximumWidth(200)
        midi_title_layout = QVBoxLayout()
        midi_title_layout.setContentsMargins(0, 0, 0, 0)
        midi_title_container.setLayout(midi_title_layout)

        title_label = QLabel(tr("MIDIswitchSettingsConfigurator", "MIDI Settings"))
        title_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        title_label.setAlignment(QtCore.Qt.AlignLeft)
        midi_title_layout.addWidget(title_label)

        desc_label = QLabel(tr("MIDIswitchSettingsConfigurator",
            "Configure global MIDI settings including channel, transpose, articulation, "
            "sustain behavior, and aftertouch options for your keyboard."))
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; font-size: 9pt;")
        desc_label.setAlignment(QtCore.Qt.AlignLeft)
        midi_title_layout.addWidget(desc_label)

        midi_title_layout.addSpacing(15)

        # Buttons in the title container with popup menus
        midi_btn_style = "QPushButton { border-radius: 5px; font-size: 9pt; }"

        # Save Settings button with popup menu
        save_settings_btn = QPushButton(tr("MIDIswitchSettingsConfigurator", "Save Settings"))
        save_settings_btn.setMinimumHeight(28)
        save_settings_btn.setMaximumHeight(28)
        save_settings_btn.setStyleSheet(midi_btn_style)
        save_settings_btn.setToolTip("Save current settings to a slot")

        save_menu = QMenu(save_settings_btn)
        save_menu.addAction(tr("MIDIswitchSettingsConfigurator", "Save as Default"), lambda: self.on_save_slot(0))
        save_menu.addSeparator()
        for i in range(1, 5):
            save_menu.addAction(tr("MIDIswitchSettingsConfigurator", f"Save to Slot {i}"), lambda checked=False, slot=i: self.on_save_slot(slot))
        save_settings_btn.setMenu(save_menu)
        midi_title_layout.addWidget(save_settings_btn)

        # Load Settings button with popup menu
        load_settings_btn = QPushButton(tr("MIDIswitchSettingsConfigurator", "Load Settings"))
        load_settings_btn.setMinimumHeight(28)
        load_settings_btn.setMaximumHeight(28)
        load_settings_btn.setStyleSheet(midi_btn_style)
        load_settings_btn.setToolTip("Load settings from a slot")

        load_menu = QMenu(load_settings_btn)
        load_menu.addAction(tr("MIDIswitchSettingsConfigurator", "Load Default"), lambda: self.on_load_slot(0))
        load_menu.addSeparator()
        for i in range(1, 5):
            load_menu.addAction(tr("MIDIswitchSettingsConfigurator", f"Load Slot {i}"), lambda checked=False, slot=i: self.on_load_slot(slot))
        load_settings_btn.setMenu(load_menu)
        midi_title_layout.addWidget(load_settings_btn)

        # Load Active Settings button (individual)
        load_active_btn = QPushButton(tr("MIDIswitchSettingsConfigurator", "Load Active Settings"))
        load_active_btn.setMinimumHeight(28)
        load_active_btn.setMaximumHeight(28)
        load_active_btn.setStyleSheet(midi_btn_style)
        load_active_btn.setToolTip("Refresh display with current keyboard settings.\nUpdates all fields to match the keyboard's active configuration.")
        load_active_btn.clicked.connect(self.on_load_current_settings)
        midi_title_layout.addWidget(load_active_btn)

        # Reset to Defaults button (individual)
        reset_btn = QPushButton(tr("MIDIswitchSettingsConfigurator", "Reset to Defaults"))
        reset_btn.setMinimumHeight(28)
        reset_btn.setMaximumHeight(28)
        reset_btn.setStyleSheet(midi_btn_style)
        reset_btn.setToolTip("Reset all MIDI settings to factory defaults.\nThis cannot be undone.")
        reset_btn.clicked.connect(self.on_reset)
        midi_title_layout.addWidget(reset_btn)

        midi_title_layout.addStretch()

        # Base MIDI Settings container (limited width like keysplit)
        base_settings_container = QGroupBox(tr("MIDIswitchSettingsConfigurator", "Base Settings"))
        base_settings_container.setMaximumWidth(300)
        base_layout = QGridLayout()
        base_layout.setVerticalSpacing(10)
        base_layout.setHorizontalSpacing(10)
        base_settings_container.setLayout(base_layout)

        row = 0

        # Channel with help
        channel_label_container = QWidget()
        channel_label_layout = QHBoxLayout()
        channel_label_layout.setContentsMargins(0, 0, 0, 0)
        channel_label_layout.setSpacing(5)
        channel_label_layout.addWidget(self.create_help_label("MIDI channel for note output (1-16)"))
        channel_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Channel:")))
        channel_label_layout.addStretch()
        channel_label_container.setLayout(channel_label_layout)
        base_layout.addWidget(channel_label_container, row, 0)

        self.global_channel = ArrowComboBox()
        self.global_channel.setMinimumWidth(80)
        self.global_channel.setMaximumWidth(120)
        self.global_channel.setMinimumHeight(25)
        self.global_channel.setMaximumHeight(25)
        for i in range(16):
            self.global_channel.addItem(f"{i + 1}", i)
        self.global_channel.setCurrentIndex(0)
        self.global_channel.setEditable(True)
        self.global_channel.lineEdit().setReadOnly(True)
        self.global_channel.lineEdit().setAlignment(Qt.AlignCenter)
        base_layout.addWidget(self.global_channel, row, 1)
        row += 1

        # Transpose with help
        transpose_label_container = QWidget()
        transpose_label_layout = QHBoxLayout()
        transpose_label_layout.setContentsMargins(0, 0, 0, 0)
        transpose_label_layout.setSpacing(5)
        transpose_label_layout.addWidget(self.create_help_label("Shift all notes up or down by semitones (-64 to +64)"))
        transpose_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Transpose:")))
        transpose_label_layout.addStretch()
        transpose_label_container.setLayout(transpose_label_layout)
        base_layout.addWidget(transpose_label_container, row, 0)

        self.global_transpose = ArrowComboBox()
        self.global_transpose.setMinimumWidth(80)
        self.global_transpose.setMaximumWidth(120)
        self.global_transpose.setMinimumHeight(25)
        self.global_transpose.setMaximumHeight(25)
        for i in range(-64, 65):
            self.global_transpose.addItem(f"{'+' if i >= 0 else ''}{i}", i)
        self.global_transpose.setCurrentIndex(64)
        self.global_transpose.setEditable(True)
        self.global_transpose.lineEdit().setReadOnly(True)
        self.global_transpose.lineEdit().setAlignment(Qt.AlignCenter)
        base_layout.addWidget(self.global_transpose, row, 1)
        row += 1

        # Velocity Curve with help
        velocity_curve_label_container = QWidget()
        velocity_curve_label_layout = QHBoxLayout()
        velocity_curve_label_layout.setContentsMargins(0, 0, 0, 0)
        velocity_curve_label_layout.setSpacing(5)
        velocity_curve_label_layout.addWidget(self.create_help_label(
            "How key press force maps to MIDI velocity.\n"
            "Factory articulations: Softest-Hardest response\n"
            "curves plus Sensitive, Fixed, Drums, Two Toned,\n"
            "Reverse and Random Highlights presets.\n"
            "User 1-50: Custom user-defined curves"
        ))
        velocity_curve_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Articulation:")))
        velocity_curve_label_layout.addStretch()
        velocity_curve_label_container.setLayout(velocity_curve_label_layout)
        base_layout.addWidget(velocity_curve_label_container, row, 0)

        self.global_velocity_curve = ArrowComboBox()
        self.global_velocity_curve.setMinimumWidth(80)
        self.global_velocity_curve.setMaximumWidth(120)
        self.global_velocity_curve.setMinimumHeight(25)
        self.global_velocity_curve.setMaximumHeight(25)
        populate_articulation_combo(self.global_velocity_curve)
        self.global_velocity_curve.setCurrentIndex(0)
        self.global_velocity_curve.setEditable(True)
        self.global_velocity_curve.lineEdit().setReadOnly(True)
        self.global_velocity_curve.lineEdit().setAlignment(Qt.AlignCenter)
        base_layout.addWidget(self.global_velocity_curve, row, 1)
        row += 1

        # Velocity min/max removed - now configured per velocity preset

        # Sustain with help
        sustain_label_container = QWidget()
        sustain_label_layout = QHBoxLayout()
        sustain_label_layout.setContentsMargins(0, 0, 0, 0)
        sustain_label_layout.setSpacing(5)
        sustain_label_layout.addWidget(self.create_help_label(
            "How the keyboard responds to sustain pedal:\n"
            "Ignore: Sustain pedal messages are ignored\n"
            "Allow: Sustain pedal affects note release"
        ))
        sustain_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Sustain:")))
        sustain_label_layout.addStretch()
        sustain_label_container.setLayout(sustain_label_layout)
        base_layout.addWidget(sustain_label_container, row, 0)

        self.base_sustain = ArrowComboBox()
        self.base_sustain.setMinimumWidth(80)
        self.base_sustain.setMaximumWidth(120)
        self.base_sustain.setMinimumHeight(25)
        self.base_sustain.setMaximumHeight(25)
        self.base_sustain.addItem("Ignore", 0)
        self.base_sustain.addItem("Allow", 1)
        self.base_sustain.setCurrentIndex(0)
        self.base_sustain.setEditable(True)
        self.base_sustain.lineEdit().setReadOnly(True)
        self.base_sustain.lineEdit().setAlignment(Qt.AlignCenter)
        base_layout.addWidget(self.base_sustain, row, 1)
        row += 1

        # SmartChord Ignore with help
        sc_ignore_label_container = QWidget()
        sc_ignore_label_layout = QHBoxLayout()
        sc_ignore_label_layout.setContentsMargins(0, 0, 0, 0)
        sc_ignore_label_layout.setSpacing(5)
        sc_ignore_label_layout.addWidget(self.create_help_label(
            "SmartChord behavior for base zone keys:\n"
            "Allow: SmartChord adds harmony notes\n"
            "Ignore: SmartChord has no effect on these keys"
        ))
        sc_ignore_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "SmartChord:")))
        sc_ignore_label_layout.addStretch()
        sc_ignore_label_container.setLayout(sc_ignore_label_layout)
        base_layout.addWidget(sc_ignore_label_container, row, 0)

        self.base_smartchord_ignore = ArrowComboBox()
        self.base_smartchord_ignore.setMinimumWidth(80)
        self.base_smartchord_ignore.setMaximumWidth(120)
        self.base_smartchord_ignore.setMinimumHeight(25)
        self.base_smartchord_ignore.setMaximumHeight(25)
        self.base_smartchord_ignore.addItem("Allow", 0)
        self.base_smartchord_ignore.addItem("Ignore", 1)
        self.base_smartchord_ignore.setCurrentIndex(0)
        self.base_smartchord_ignore.setEditable(True)
        self.base_smartchord_ignore.lineEdit().setReadOnly(True)
        self.base_smartchord_ignore.lineEdit().setAlignment(Qt.AlignCenter)
        base_layout.addWidget(self.base_smartchord_ignore, row, 1)

        # KeySplit Settings container
        self.keysplit_offshoot = QGroupBox()
        self.keysplit_offshoot.setMaximumWidth(350)
        keysplit_layout = QGridLayout()
        keysplit_layout.setVerticalSpacing(8)
        keysplit_layout.setHorizontalSpacing(8)
        self.keysplit_offshoot.setLayout(keysplit_layout)

        ks_row = 0

        # Channel: Value dropdown | On/Off
        ch_label = QWidget()
        ch_label_layout = QHBoxLayout()
        ch_label_layout.setContentsMargins(0, 0, 0, 0)
        ch_label_layout.setSpacing(3)
        ch_label_layout.addWidget(self.create_help_label("MIDI channel (1-16) for KeySplit keys"))
        ch_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Channel:")))
        ch_label_layout.addStretch()
        ch_label.setLayout(ch_label_layout)
        keysplit_layout.addWidget(ch_label, ks_row, 0)

        self.key_split_channel = ArrowComboBox()
        self.key_split_channel.setMinimumWidth(60)
        self.key_split_channel.setMaximumWidth(80)
        self.key_split_channel.setMinimumHeight(25)
        self.key_split_channel.setMaximumHeight(25)
        for i in range(16):
            self.key_split_channel.addItem(f"{i + 1}", i)
        self.key_split_channel.setEditable(True)
        self.key_split_channel.lineEdit().setReadOnly(True)
        self.key_split_channel.lineEdit().setAlignment(Qt.AlignCenter)
        keysplit_layout.addWidget(self.key_split_channel, ks_row, 1)

        self.keysplit_channel_enable = ArrowComboBox()
        self.keysplit_channel_enable.setMinimumWidth(50)
        self.keysplit_channel_enable.setMaximumWidth(60)
        self.keysplit_channel_enable.setMinimumHeight(25)
        self.keysplit_channel_enable.setMaximumHeight(25)
        self.keysplit_channel_enable.addItem("Off", 0)
        self.keysplit_channel_enable.addItem("On", 1)
        self.keysplit_channel_enable.setEditable(True)
        self.keysplit_channel_enable.lineEdit().setReadOnly(True)
        self.keysplit_channel_enable.lineEdit().setAlignment(Qt.AlignCenter)
        self.keysplit_channel_enable.currentIndexChanged.connect(self._on_split_enable_changed)
        keysplit_layout.addWidget(self.keysplit_channel_enable, ks_row, 2)
        ks_row += 1

        # Transpose: Value dropdown | On/Off
        tr_label = QWidget()
        tr_label_layout = QHBoxLayout()
        tr_label_layout.setContentsMargins(0, 0, 0, 0)
        tr_label_layout.setSpacing(3)
        tr_label_layout.addWidget(self.create_help_label("Semitone offset (-64 to +64) for KeySplit keys"))
        tr_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Transpose:")))
        tr_label_layout.addStretch()
        tr_label.setLayout(tr_label_layout)
        keysplit_layout.addWidget(tr_label, ks_row, 0)

        self.transpose_number2 = ArrowComboBox()
        self.transpose_number2.setMinimumWidth(60)
        self.transpose_number2.setMaximumWidth(80)
        self.transpose_number2.setMinimumHeight(25)
        self.transpose_number2.setMaximumHeight(25)
        for i in range(-64, 65):
            self.transpose_number2.addItem(f"{'+' if i >= 0 else ''}{i}", i)
        self.transpose_number2.setCurrentIndex(64)
        self.transpose_number2.setEditable(True)
        self.transpose_number2.lineEdit().setReadOnly(True)
        self.transpose_number2.lineEdit().setAlignment(Qt.AlignCenter)
        keysplit_layout.addWidget(self.transpose_number2, ks_row, 1)

        self.keysplit_transpose_enable = ArrowComboBox()
        self.keysplit_transpose_enable.setMinimumWidth(50)
        self.keysplit_transpose_enable.setMaximumWidth(60)
        self.keysplit_transpose_enable.setMinimumHeight(25)
        self.keysplit_transpose_enable.setMaximumHeight(25)
        self.keysplit_transpose_enable.addItem("Off", 0)
        self.keysplit_transpose_enable.addItem("On", 1)
        self.keysplit_transpose_enable.setEditable(True)
        self.keysplit_transpose_enable.lineEdit().setReadOnly(True)
        self.keysplit_transpose_enable.lineEdit().setAlignment(Qt.AlignCenter)
        self.keysplit_transpose_enable.currentIndexChanged.connect(self._on_split_enable_changed)
        keysplit_layout.addWidget(self.keysplit_transpose_enable, ks_row, 2)
        ks_row += 1

        # Velocity Curve: Curve dropdown | On/Off (merged)
        vc_label = QWidget()
        vc_label_layout = QHBoxLayout()
        vc_label_layout.setContentsMargins(0, 0, 0, 0)
        vc_label_layout.setSpacing(3)
        vc_label_layout.addWidget(self.create_help_label(
            "Velocity response curve for KeySplit keys.\n"
            "Factory articulations: Softest-Hardest response\n"
            "curves plus Sensitive, Fixed, Drums, Two Toned,\n"
            "Reverse and Random Highlights presets."
        ))
        vc_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Articulation:")))
        vc_label_layout.addStretch()
        vc_label.setLayout(vc_label_layout)
        keysplit_layout.addWidget(vc_label, ks_row, 0)

        self.velocity_curve2 = ArrowComboBox()
        self.velocity_curve2.setMinimumWidth(80)
        self.velocity_curve2.setMaximumWidth(100)
        self.velocity_curve2.setMinimumHeight(25)
        self.velocity_curve2.setMaximumHeight(25)
        populate_articulation_combo(self.velocity_curve2)
        self.velocity_curve2.setCurrentIndex(0)
        self.velocity_curve2.setEditable(True)
        self.velocity_curve2.lineEdit().setReadOnly(True)
        self.velocity_curve2.lineEdit().setAlignment(Qt.AlignCenter)
        keysplit_layout.addWidget(self.velocity_curve2, ks_row, 1)

        self.keysplit_velocity_enable = ArrowComboBox()
        self.keysplit_velocity_enable.setMinimumWidth(50)
        self.keysplit_velocity_enable.setMaximumWidth(60)
        self.keysplit_velocity_enable.setMinimumHeight(25)
        self.keysplit_velocity_enable.setMaximumHeight(25)
        self.keysplit_velocity_enable.addItem("Off", 0)
        self.keysplit_velocity_enable.addItem("On", 1)
        self.keysplit_velocity_enable.setEditable(True)
        self.keysplit_velocity_enable.lineEdit().setReadOnly(True)
        self.keysplit_velocity_enable.lineEdit().setAlignment(Qt.AlignCenter)
        self.keysplit_velocity_enable.currentIndexChanged.connect(self._on_split_enable_changed)
        keysplit_layout.addWidget(self.keysplit_velocity_enable, ks_row, 2)
        ks_row += 1

        # Velocity min/max removed - now configured per velocity preset

        # Sustain with help
        sus_label = QWidget()
        sus_label_layout = QHBoxLayout()
        sus_label_layout.setContentsMargins(0, 0, 0, 0)
        sus_label_layout.setSpacing(3)
        sus_label_layout.addWidget(self.create_help_label(
            "Sustain pedal behavior for KeySplit keys:\n"
            "Ignore: Sustain pedal has no effect\n"
            "Allow: Notes sustain when pedal is held"
        ))
        sus_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Sustain:")))
        sus_label_layout.addStretch()
        sus_label.setLayout(sus_label_layout)
        keysplit_layout.addWidget(sus_label, ks_row, 0)

        self.keysplit_sustain = ArrowComboBox()
        self.keysplit_sustain.setMinimumWidth(80)
        self.keysplit_sustain.setMaximumWidth(120)
        self.keysplit_sustain.setMinimumHeight(25)
        self.keysplit_sustain.setMaximumHeight(25)
        self.keysplit_sustain.addItem("Ignore", 0)
        self.keysplit_sustain.addItem("Allow", 1)
        self.keysplit_sustain.setCurrentIndex(0)
        self.keysplit_sustain.setEditable(True)
        self.keysplit_sustain.lineEdit().setReadOnly(True)
        self.keysplit_sustain.lineEdit().setAlignment(Qt.AlignCenter)
        keysplit_layout.addWidget(self.keysplit_sustain, ks_row, 1, 1, 2)
        ks_row += 1

        # SmartChord Ignore with help
        ks_sc_label = QWidget()
        ks_sc_label_layout = QHBoxLayout()
        ks_sc_label_layout.setContentsMargins(0, 0, 0, 0)
        ks_sc_label_layout.setSpacing(3)
        ks_sc_label_layout.addWidget(self.create_help_label(
            "SmartChord behavior for KeySplit keys:\n"
            "Allow: SmartChord adds harmony notes\n"
            "Ignore: SmartChord has no effect on these keys"
        ))
        ks_sc_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "SmartChord:")))
        ks_sc_label_layout.addStretch()
        ks_sc_label.setLayout(ks_sc_label_layout)
        keysplit_layout.addWidget(ks_sc_label, ks_row, 0)

        self.keysplit_smartchord_ignore = ArrowComboBox()
        self.keysplit_smartchord_ignore.setMinimumWidth(80)
        self.keysplit_smartchord_ignore.setMaximumWidth(120)
        self.keysplit_smartchord_ignore.setMinimumHeight(25)
        self.keysplit_smartchord_ignore.setMaximumHeight(25)
        self.keysplit_smartchord_ignore.addItem("Allow", 0)
        self.keysplit_smartchord_ignore.addItem("Ignore", 1)
        self.keysplit_smartchord_ignore.setCurrentIndex(0)
        self.keysplit_smartchord_ignore.setEditable(True)
        self.keysplit_smartchord_ignore.lineEdit().setReadOnly(True)
        self.keysplit_smartchord_ignore.lineEdit().setAlignment(Qt.AlignCenter)
        keysplit_layout.addWidget(self.keysplit_smartchord_ignore, ks_row, 1, 1, 2)

        # TripleSplit Settings container
        self.triplesplit_offshoot = QGroupBox()
        self.triplesplit_offshoot.setMaximumWidth(350)
        triplesplit_layout = QGridLayout()
        triplesplit_layout.setVerticalSpacing(8)
        triplesplit_layout.setHorizontalSpacing(8)
        self.triplesplit_offshoot.setLayout(triplesplit_layout)

        ts_row = 0

        # Channel: Value dropdown | On/Off
        ts_ch_label = QWidget()
        ts_ch_label_layout = QHBoxLayout()
        ts_ch_label_layout.setContentsMargins(0, 0, 0, 0)
        ts_ch_label_layout.setSpacing(3)
        ts_ch_label_layout.addWidget(self.create_help_label("MIDI channel (1-16) for TripleSplit keys"))
        ts_ch_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Channel:")))
        ts_ch_label_layout.addStretch()
        ts_ch_label.setLayout(ts_ch_label_layout)
        triplesplit_layout.addWidget(ts_ch_label, ts_row, 0)

        self.key_split2_channel = ArrowComboBox()
        self.key_split2_channel.setMinimumWidth(60)
        self.key_split2_channel.setMaximumWidth(80)
        self.key_split2_channel.setMinimumHeight(25)
        self.key_split2_channel.setMaximumHeight(25)
        for i in range(16):
            self.key_split2_channel.addItem(f"{i + 1}", i)
        self.key_split2_channel.setEditable(True)
        self.key_split2_channel.lineEdit().setReadOnly(True)
        self.key_split2_channel.lineEdit().setAlignment(Qt.AlignCenter)
        triplesplit_layout.addWidget(self.key_split2_channel, ts_row, 1)

        self.triplesplit_channel_enable = ArrowComboBox()
        self.triplesplit_channel_enable.setMinimumWidth(50)
        self.triplesplit_channel_enable.setMaximumWidth(60)
        self.triplesplit_channel_enable.setMinimumHeight(25)
        self.triplesplit_channel_enable.setMaximumHeight(25)
        self.triplesplit_channel_enable.addItem("Off", 0)
        self.triplesplit_channel_enable.addItem("On", 1)
        self.triplesplit_channel_enable.setEditable(True)
        self.triplesplit_channel_enable.lineEdit().setReadOnly(True)
        self.triplesplit_channel_enable.lineEdit().setAlignment(Qt.AlignCenter)
        self.triplesplit_channel_enable.currentIndexChanged.connect(self._on_split_enable_changed)
        triplesplit_layout.addWidget(self.triplesplit_channel_enable, ts_row, 2)
        ts_row += 1

        # Transpose: Value dropdown | On/Off
        ts_tr_label = QWidget()
        ts_tr_label_layout = QHBoxLayout()
        ts_tr_label_layout.setContentsMargins(0, 0, 0, 0)
        ts_tr_label_layout.setSpacing(3)
        ts_tr_label_layout.addWidget(self.create_help_label("Semitone offset (-64 to +64) for TripleSplit keys"))
        ts_tr_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Transpose:")))
        ts_tr_label_layout.addStretch()
        ts_tr_label.setLayout(ts_tr_label_layout)
        triplesplit_layout.addWidget(ts_tr_label, ts_row, 0)

        self.transpose_number3 = ArrowComboBox()
        self.transpose_number3.setMinimumWidth(60)
        self.transpose_number3.setMaximumWidth(80)
        self.transpose_number3.setMinimumHeight(25)
        self.transpose_number3.setMaximumHeight(25)
        for i in range(-64, 65):
            self.transpose_number3.addItem(f"{'+' if i >= 0 else ''}{i}", i)
        self.transpose_number3.setCurrentIndex(64)
        self.transpose_number3.setEditable(True)
        self.transpose_number3.lineEdit().setReadOnly(True)
        self.transpose_number3.lineEdit().setAlignment(Qt.AlignCenter)
        triplesplit_layout.addWidget(self.transpose_number3, ts_row, 1)

        self.triplesplit_transpose_enable = ArrowComboBox()
        self.triplesplit_transpose_enable.setMinimumWidth(50)
        self.triplesplit_transpose_enable.setMaximumWidth(60)
        self.triplesplit_transpose_enable.setMinimumHeight(25)
        self.triplesplit_transpose_enable.setMaximumHeight(25)
        self.triplesplit_transpose_enable.addItem("Off", 0)
        self.triplesplit_transpose_enable.addItem("On", 1)
        self.triplesplit_transpose_enable.setEditable(True)
        self.triplesplit_transpose_enable.lineEdit().setReadOnly(True)
        self.triplesplit_transpose_enable.lineEdit().setAlignment(Qt.AlignCenter)
        self.triplesplit_transpose_enable.currentIndexChanged.connect(self._on_split_enable_changed)
        triplesplit_layout.addWidget(self.triplesplit_transpose_enable, ts_row, 2)
        ts_row += 1

        # Velocity Curve: Curve dropdown | On/Off (merged)
        ts_vc_label = QWidget()
        ts_vc_label_layout = QHBoxLayout()
        ts_vc_label_layout.setContentsMargins(0, 0, 0, 0)
        ts_vc_label_layout.setSpacing(3)
        ts_vc_label_layout.addWidget(self.create_help_label(
            "Velocity response curve for TripleSplit keys.\n"
            "Factory articulations: Softest-Hardest response\n"
            "curves plus Sensitive, Fixed, Drums, Two Toned,\n"
            "Reverse and Random Highlights presets."
        ))
        ts_vc_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Articulation:")))
        ts_vc_label_layout.addStretch()
        ts_vc_label.setLayout(ts_vc_label_layout)
        triplesplit_layout.addWidget(ts_vc_label, ts_row, 0)

        self.velocity_curve3 = ArrowComboBox()
        self.velocity_curve3.setMinimumWidth(80)
        self.velocity_curve3.setMaximumWidth(100)
        self.velocity_curve3.setMinimumHeight(25)
        self.velocity_curve3.setMaximumHeight(25)
        populate_articulation_combo(self.velocity_curve3)
        self.velocity_curve3.setCurrentIndex(0)
        self.velocity_curve3.setEditable(True)
        self.velocity_curve3.lineEdit().setReadOnly(True)
        self.velocity_curve3.lineEdit().setAlignment(Qt.AlignCenter)
        triplesplit_layout.addWidget(self.velocity_curve3, ts_row, 1)

        self.triplesplit_velocity_enable = ArrowComboBox()
        self.triplesplit_velocity_enable.setMinimumWidth(50)
        self.triplesplit_velocity_enable.setMaximumWidth(60)
        self.triplesplit_velocity_enable.setMinimumHeight(25)
        self.triplesplit_velocity_enable.setMaximumHeight(25)
        self.triplesplit_velocity_enable.addItem("Off", 0)
        self.triplesplit_velocity_enable.addItem("On", 1)
        self.triplesplit_velocity_enable.setEditable(True)
        self.triplesplit_velocity_enable.lineEdit().setReadOnly(True)
        self.triplesplit_velocity_enable.lineEdit().setAlignment(Qt.AlignCenter)
        self.triplesplit_velocity_enable.currentIndexChanged.connect(self._on_split_enable_changed)
        triplesplit_layout.addWidget(self.triplesplit_velocity_enable, ts_row, 2)
        ts_row += 1

        # Velocity min/max removed - now configured per velocity preset

        # Sustain with help
        ts_sus_label = QWidget()
        ts_sus_label_layout = QHBoxLayout()
        ts_sus_label_layout.setContentsMargins(0, 0, 0, 0)
        ts_sus_label_layout.setSpacing(3)
        ts_sus_label_layout.addWidget(self.create_help_label(
            "Sustain pedal behavior for TripleSplit keys:\n"
            "Ignore: Sustain pedal has no effect\n"
            "Allow: Notes sustain when pedal is held"
        ))
        ts_sus_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Sustain:")))
        ts_sus_label_layout.addStretch()
        ts_sus_label.setLayout(ts_sus_label_layout)
        triplesplit_layout.addWidget(ts_sus_label, ts_row, 0)

        self.triplesplit_sustain = ArrowComboBox()
        self.triplesplit_sustain.setMinimumWidth(80)
        self.triplesplit_sustain.setMaximumWidth(120)
        self.triplesplit_sustain.setMinimumHeight(25)
        self.triplesplit_sustain.setMaximumHeight(25)
        self.triplesplit_sustain.addItem("Ignore", 0)
        self.triplesplit_sustain.addItem("Allow", 1)
        self.triplesplit_sustain.setCurrentIndex(0)
        self.triplesplit_sustain.setEditable(True)
        self.triplesplit_sustain.lineEdit().setReadOnly(True)
        self.triplesplit_sustain.lineEdit().setAlignment(Qt.AlignCenter)
        triplesplit_layout.addWidget(self.triplesplit_sustain, ts_row, 1, 1, 2)
        ts_row += 1

        # SmartChord Ignore with help
        ts_sc_label = QWidget()
        ts_sc_label_layout = QHBoxLayout()
        ts_sc_label_layout.setContentsMargins(0, 0, 0, 0)
        ts_sc_label_layout.setSpacing(3)
        ts_sc_label_layout.addWidget(self.create_help_label(
            "SmartChord behavior for TripleSplit keys:\n"
            "Allow: SmartChord adds harmony notes\n"
            "Ignore: SmartChord has no effect on these keys"
        ))
        ts_sc_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "SmartChord:")))
        ts_sc_label_layout.addStretch()
        ts_sc_label.setLayout(ts_sc_label_layout)
        triplesplit_layout.addWidget(ts_sc_label, ts_row, 0)

        self.triplesplit_smartchord_ignore = ArrowComboBox()
        self.triplesplit_smartchord_ignore.setMinimumWidth(80)
        self.triplesplit_smartchord_ignore.setMaximumWidth(120)
        self.triplesplit_smartchord_ignore.setMinimumHeight(25)
        self.triplesplit_smartchord_ignore.setMaximumHeight(25)
        self.triplesplit_smartchord_ignore.addItem("Allow", 0)
        self.triplesplit_smartchord_ignore.addItem("Ignore", 1)
        self.triplesplit_smartchord_ignore.setCurrentIndex(0)
        self.triplesplit_smartchord_ignore.setEditable(True)
        self.triplesplit_smartchord_ignore.lineEdit().setReadOnly(True)
        self.triplesplit_smartchord_ignore.lineEdit().setAlignment(Qt.AlignCenter)
        triplesplit_layout.addWidget(self.triplesplit_smartchord_ignore, ts_row, 1, 1, 2)

        # Create wrapper for keysplit with title above
        keysplit_wrapper = QWidget()
        keysplit_wrapper_layout = QVBoxLayout()
        keysplit_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        keysplit_wrapper_layout.setSpacing(5)
        keysplit_wrapper.setLayout(keysplit_wrapper_layout)

        # KeySplit title with help icon (above container)
        ks_header = QWidget()
        ks_header_layout = QHBoxLayout()
        ks_header_layout.setContentsMargins(0, 0, 0, 0)
        ks_header_layout.setSpacing(5)
        ks_header_title = QLabel(tr("MIDIswitchSettingsConfigurator", "KeySplit Settings"))
        ks_header_title.setStyleSheet("font-weight: bold;")
        ks_header_layout.addWidget(self.create_help_label(
            "KeySplit allows keys assigned to the KeySplit layer to use\n"
            "different MIDI settings than the base layer.\n\n"
            "Enable each parameter to apply separate settings for split keys."
        ))
        ks_header_layout.addWidget(ks_header_title)
        ks_header_layout.addStretch()
        ks_header.setLayout(ks_header_layout)
        keysplit_wrapper_layout.addWidget(ks_header)
        keysplit_wrapper_layout.addWidget(self.keysplit_offshoot)

        # Create wrapper for triplesplit with title above
        triplesplit_wrapper = QWidget()
        triplesplit_wrapper_layout = QVBoxLayout()
        triplesplit_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        triplesplit_wrapper_layout.setSpacing(5)
        triplesplit_wrapper.setLayout(triplesplit_wrapper_layout)

        # TripleSplit title with help icon (above container)
        ts_header = QWidget()
        ts_header_layout = QHBoxLayout()
        ts_header_layout.setContentsMargins(0, 0, 0, 0)
        ts_header_layout.setSpacing(5)
        ts_header_title = QLabel(tr("MIDIswitchSettingsConfigurator", "TripleSplit Settings"))
        ts_header_title.setStyleSheet("font-weight: bold;")
        ts_header_layout.addWidget(self.create_help_label(
            "TripleSplit allows keys assigned to the TripleSplit layer to use\n"
            "different MIDI settings than both base and KeySplit layers.\n\n"
            "Enable each parameter to apply separate settings for third split keys."
        ))
        ts_header_layout.addWidget(ts_header_title)
        ts_header_layout.addStretch()
        ts_header.setLayout(ts_header_layout)
        triplesplit_wrapper_layout.addWidget(ts_header)
        triplesplit_wrapper_layout.addWidget(self.triplesplit_offshoot)

        # Add all containers to the horizontal layout
        global_midi_group_layout.addWidget(midi_title_container)
        global_midi_group_layout.addStretch()
        global_midi_group_layout.addWidget(base_settings_container)
        global_midi_group_layout.addWidget(keysplit_wrapper)
        global_midi_group_layout.addWidget(triplesplit_wrapper)
        global_midi_group_layout.addStretch()

        # Add global MIDI group to main layout
        main_layout.addWidget(global_midi_group)

        # Loop Settings Group with title on left, container centered
        loop_row_container = QWidget()
        loop_row_layout = QHBoxLayout()
        loop_row_layout.setContentsMargins(0, 0, 0, 0)
        loop_row_container.setLayout(loop_row_layout)

        # Loop title container (left of centered container, vertically centered)
        loop_title_widget = QWidget()
        loop_title_widget.setFixedWidth(150)
        loop_title_layout = QVBoxLayout()
        loop_title_layout.setContentsMargins(0, 0, 0, 0)
        loop_title_widget.setLayout(loop_title_layout)

        loop_title_layout.addStretch()
        loop_title_label = QLabel(tr("MIDIswitchSettingsConfigurator", "Loop Settings"))
        loop_title_layout.addWidget(loop_title_label)
        loop_title_layout.addStretch()

        loop_group = QGroupBox()
        loop_layout = QGridLayout()
        loop_group.setLayout(loop_layout)
        loop_layout.setHorizontalSpacing(25)

        loop_row_layout.addStretch()
        loop_row_layout.addWidget(loop_title_widget)
        loop_row_layout.addWidget(loop_group)
        loop_row_layout.addStretch()
        main_layout.addWidget(loop_row_container)

        # Sync Mode with help
        sync_mode_label = QWidget()
        sync_mode_layout = QHBoxLayout()
        sync_mode_layout.setContentsMargins(0, 0, 0, 0)
        sync_mode_layout.setSpacing(5)
        sync_mode_layout.addWidget(self.create_help_label(
            "Loop: Free-running loop mode\n"
            "Sync Mode: Synced to external clock\n"
            "BPM Bar/Beat: Sync to BPM timing\n"
            "Note Prime On/Off: Whether notes prime the loop"
        ))
        sync_mode_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Sync Mode:")))
        sync_mode_label.setLayout(sync_mode_layout)
        loop_layout.addWidget(sync_mode_label, 0, 1)
        self.unsynced_mode = ArrowComboBox()
        self.unsynced_mode.setMinimumWidth(120)
        self.unsynced_mode.setMinimumHeight(25)
        self.unsynced_mode.setMaximumHeight(25)
        self.unsynced_mode.setEditable(True)
        self.unsynced_mode.lineEdit().setReadOnly(True)
        self.unsynced_mode.lineEdit().setAlignment(Qt.AlignCenter)
        self.unsynced_mode.addItem("Loop (Note Prime On)", 0)
        self.unsynced_mode.addItem("Loop (Note Prime Off)", 4)
        self.unsynced_mode.addItem("Sync Mode (Note Prime On)", 2)
        self.unsynced_mode.addItem("Sync Mode (Note Prime Off)", 5)
        self.unsynced_mode.addItem("BPM Bar", 1)
        self.unsynced_mode.addItem("BPM Beat", 3)
        loop_layout.addWidget(self.unsynced_mode, 0, 2)

        # Sample Mode with help
        sample_mode_label = QWidget()
        sample_mode_label_layout = QHBoxLayout()
        sample_mode_label_layout.setContentsMargins(0, 0, 0, 0)
        sample_mode_label_layout.setSpacing(5)
        sample_mode_label_layout.addWidget(self.create_help_label(
            "Enable one-shot sample playback mode.\n"
            "Off: Normal loop behavior\n"
            "On: Loops play once and stop"
        ))
        sample_mode_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Sample Mode:")))
        sample_mode_label.setLayout(sample_mode_label_layout)
        loop_layout.addWidget(sample_mode_label, 0, 3)
        self.sample_mode = ArrowComboBox()
        self.sample_mode.setMinimumWidth(120)
        self.sample_mode.setMinimumHeight(25)
        self.sample_mode.setMaximumHeight(25)
        self.sample_mode.setEditable(True)
        self.sample_mode.lineEdit().setReadOnly(True)
        self.sample_mode.lineEdit().setAlignment(Qt.AlignCenter)
        self.sample_mode.addItem("Off", False)
        self.sample_mode.addItem("On", True)
        loop_layout.addWidget(self.sample_mode, 0, 4)

        # Instant Start moved to the new "Stop Mode" group below (mirrors the
        # on-device Advanced Settings > Stop Mode menu, where it now lives).

        # CC Loop Recording with help
        cc_loop_rec_label = QWidget()
        cc_loop_rec_label_layout = QHBoxLayout()
        cc_loop_rec_label_layout.setContentsMargins(0, 0, 0, 0)
        cc_loop_rec_label_layout.setSpacing(5)
        cc_loop_rec_label_layout.addWidget(self.create_help_label(
            "Record CC messages in loop recordings.\n"
            "Off: Only note on/off recorded\n"
            "On: CC messages also recorded"
        ))
        cc_loop_rec_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Loop Recording:")))
        cc_loop_rec_label.setLayout(cc_loop_rec_label_layout)
        loop_layout.addWidget(cc_loop_rec_label, 1, 1)
        self.cc_loop_recording = ArrowComboBox()
        self.cc_loop_recording.setMinimumWidth(120)
        self.cc_loop_recording.setMinimumHeight(25)
        self.cc_loop_recording.setMaximumHeight(25)
        self.cc_loop_recording.setEditable(True)
        self.cc_loop_recording.lineEdit().setReadOnly(True)
        self.cc_loop_recording.lineEdit().setAlignment(Qt.AlignCenter)
        self.cc_loop_recording.addItem("Off", 0)
        self.cc_loop_recording.addItem("AT Only", 1)
        self.cc_loop_recording.addItem("CC Only", 2)
        self.cc_loop_recording.addItem("CC + AT", 3)
        loop_layout.addWidget(self.cc_loop_recording, 1, 2)

        # Live Note Priority with help
        macro_override_label = QWidget()
        macro_override_label_layout = QHBoxLayout()
        macro_override_label_layout.setContentsMargins(0, 0, 0, 0)
        macro_override_label_layout.setSpacing(5)
        macro_override_label_layout.addWidget(self.create_help_label(
            "Control how macro playback interacts with live notes.\n"
            "Off: Macro plays notes even when held live\n"
            "On: Live notes take priority, macro skips held notes"
        ))
        macro_override_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Live Note Priority:")))
        macro_override_label.setLayout(macro_override_label_layout)
        loop_layout.addWidget(macro_override_label, 1, 3)
        self.macro_override_live_notes = ArrowComboBox()
        self.macro_override_live_notes.setMinimumWidth(120)
        self.macro_override_live_notes.setMinimumHeight(25)
        self.macro_override_live_notes.setMaximumHeight(25)
        self.macro_override_live_notes.setEditable(True)
        self.macro_override_live_notes.lineEdit().setReadOnly(True)
        self.macro_override_live_notes.lineEdit().setAlignment(Qt.AlignCenter)
        self.macro_override_live_notes.addItem("Off", True)    # Off = live notes don't have priority = macro_override_live_notes=true
        self.macro_override_live_notes.addItem("On", False)    # On = live notes have priority = macro_override_live_notes=false
        loop_layout.addWidget(self.macro_override_live_notes, 1, 4)

        # =================================================================
        # Stop Mode Group — per-function Mute/Stop behavior of the stop key.
        # Mirrors the on-device Advanced Settings > Stop Mode menu.
        # The 5-bit mask rides keyboard-config packet 1 byte 20 as
        # 0x80 | mask (bit 7 = "field valid" feature-detect marker; old
        # firmware sends 0 there and ignores anything without bit 7 set).
        # =================================================================
        stopmode_row_container = QWidget()
        stopmode_row_layout = QHBoxLayout()
        stopmode_row_layout.setContentsMargins(0, 0, 0, 0)
        stopmode_row_container.setLayout(stopmode_row_layout)

        stopmode_title_widget = QWidget()
        stopmode_title_widget.setFixedWidth(150)
        stopmode_title_layout = QVBoxLayout()
        stopmode_title_layout.setContentsMargins(0, 0, 0, 0)
        stopmode_title_widget.setLayout(stopmode_title_layout)

        stopmode_title_layout.addStretch()
        stopmode_title_label = QLabel(tr("MIDIswitchSettingsConfigurator", "Stop Mode"))
        stopmode_title_layout.addWidget(stopmode_title_label)
        stopmode_title_layout.addStretch()

        stopmode_group = QGroupBox()
        stopmode_layout = QGridLayout()
        stopmode_layout.setHorizontalSpacing(25)
        stopmode_group.setLayout(stopmode_layout)

        stopmode_row_layout.addStretch()
        stopmode_row_layout.addWidget(stopmode_title_widget)
        stopmode_row_layout.addWidget(stopmode_group)
        stopmode_row_layout.addStretch()

        # Instant Start (moved here from Loop Settings — it dictates whether
        # the Mute/Stop toggles below, and loop play/stop generally, resolve
        # on the key press or defer to the next loop trigger).
        instant_start_label = QWidget()
        instant_start_label_layout = QHBoxLayout()
        instant_start_label_layout.setContentsMargins(0, 0, 0, 0)
        instant_start_label_layout.setSpacing(5)
        instant_start_label_layout.addWidget(self.create_help_label(
            "Instant Start for loop playback controls.\n"
            "Off: play/stop/mute wait for the next musical boundary\n"
            "On: loop, overdub and ThruLoop play/stop/mute (and the\n"
            "Mute/Stop toggles below) happen immediately and join in\n"
            "time with the other loops (resuming from the current\n"
            "position in the loop).\n\n"
            "Recording start/stop always stays synced to the boundary."
        ))
        instant_start_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Instant Start:")))
        instant_start_label.setLayout(instant_start_label_layout)
        stopmode_layout.addWidget(instant_start_label, 0, 1)
        self.instant_loop_start = ArrowComboBox()
        self.instant_loop_start.setMinimumWidth(120)
        self.instant_loop_start.setMinimumHeight(25)
        self.instant_loop_start.setMaximumHeight(25)
        self.instant_loop_start.setEditable(True)
        self.instant_loop_start.lineEdit().setReadOnly(True)
        self.instant_loop_start.lineEdit().setAlignment(Qt.AlignCenter)
        self.instant_loop_start.addItem("Off", False)
        self.instant_loop_start.addItem("On", True)
        stopmode_layout.addWidget(self.instant_loop_start, 0, 2)

        # One Mute/Stop combo per transport family. Bit values mirror the
        # firmware STOP_MODE_* defines (process_dynamic_macro.h):
        # bit CLEAR = Mute (default), bit SET = Stop.
        _stopmode_help = (
            "Mute: the stop key only silences this function while anything\n"
            "else is playing — it keeps running in time (timers, phase,\n"
            "chain beats, clock mastership) and the next press brings it\n"
            "back in phase. Stop: the stop key really stops it.\n\n"
            "Instant Start makes the mute/stop act on the key press instead\n"
            "of waiting for the loop trigger.\n\n"
            "Applied when settings are saved. Shared by every instance of\n"
            "the family (all 8 loops share the Loop setting, etc.)."
        )
        # (label, STOP_MODE_* bit, grid row, grid col-pair)
        _stopmode_families = [
            ("Loop",           self.STOP_MODE_LOOP,     0, 3),
            ("ThruLoop",       self.STOP_MODE_THRULOOP, 0, 5),
            ("Step Sequencer", self.STOP_MODE_SEQ,      1, 1),
            ("Drum Machine",   self.STOP_MODE_DRUM,     1, 3),
            ("Rhythm Engine",  self.STOP_MODE_CPROG,    1, 5),
        ]
        # Assume supported until a GET reports a byte without the bit-7
        # marker (old firmware) — apply_settings() then disables the combos.
        self.stop_mode_supported = True
        self.stop_mode_combos = {}
        for _sm_name, _sm_bit, _sm_row, _sm_col in _stopmode_families:
            _sm_label = QWidget()
            _sm_label_layout = QHBoxLayout()
            _sm_label_layout.setContentsMargins(0, 0, 0, 0)
            _sm_label_layout.setSpacing(5)
            _sm_label_layout.addWidget(self.create_help_label(_stopmode_help))
            _sm_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", _sm_name + ":")))
            _sm_label.setLayout(_sm_label_layout)
            stopmode_layout.addWidget(_sm_label, _sm_row, _sm_col)
            _sm_combo = ArrowComboBox()
            _sm_combo.setMinimumWidth(120)
            _sm_combo.setMinimumHeight(25)
            _sm_combo.setMaximumHeight(25)
            _sm_combo.setEditable(True)
            _sm_combo.lineEdit().setReadOnly(True)
            _sm_combo.lineEdit().setAlignment(Qt.AlignCenter)
            _sm_combo.addItem("Mute", 0)   # bit clear = Mute (firmware default)
            _sm_combo.addItem("Stop", 1)   # bit set = Stop (legacy behavior)
            stopmode_layout.addWidget(_sm_combo, _sm_row, _sm_col + 1)
            self.stop_mode_combos[_sm_bit] = _sm_combo

        # (The "Enable Aftertouch Modes" / "Enable CC Modes" toggles were moved
        # out of this Stop Mode grid into the Advanced Settings grid below — see
        # the AT/CC enable block after the Advanced grid is built. Their wiring
        # is unchanged.)

        main_layout.addWidget(stopmode_row_container)

        # Advanced Settings Group with title on left, container centered
        advanced_row_container = QWidget()
        advanced_row_layout = QHBoxLayout()
        advanced_row_layout.setContentsMargins(0, 0, 0, 0)
        advanced_row_container.setLayout(advanced_row_layout)

        # Advanced title container (left of centered container, vertically centered)
        advanced_title_widget = QWidget()
        advanced_title_widget.setFixedWidth(150)
        advanced_title_layout = QVBoxLayout()
        advanced_title_layout.setContentsMargins(0, 0, 0, 0)
        advanced_title_widget.setLayout(advanced_title_layout)

        advanced_title_layout.addStretch()
        advanced_title_label = QLabel(tr("MIDIswitchSettingsConfigurator", "Advanced Settings"))
        advanced_title_layout.addWidget(advanced_title_label)
        advanced_title_layout.addStretch()

        advanced_group = QGroupBox()
        advanced_layout = QGridLayout()
        advanced_layout.setHorizontalSpacing(25)
        advanced_group.setLayout(advanced_layout)

        advanced_row_layout.addStretch()
        advanced_row_layout.addWidget(advanced_title_widget)
        advanced_row_layout.addWidget(advanced_group)
        advanced_row_layout.addStretch()

        # Velocity Interval with help
        vel_interval_label = QWidget()
        vel_interval_label_layout = QHBoxLayout()
        vel_interval_label_layout.setContentsMargins(0, 0, 0, 0)
        vel_interval_label_layout.setSpacing(5)
        vel_interval_label_layout.addWidget(self.create_help_label(
            "Velocity step amount (1-10).\n"
            "When using velocity +/- keys, this is the\n"
            "amount velocity will increase or decrease."
        ))
        vel_interval_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Velocity Interval:")))
        vel_interval_label.setLayout(vel_interval_label_layout)
        advanced_layout.addWidget(vel_interval_label, 0, 1)
        self.velocity_sensitivity = ArrowComboBox()
        self.velocity_sensitivity.setMinimumWidth(120)
        self.velocity_sensitivity.setMinimumHeight(25)
        self.velocity_sensitivity.setMaximumHeight(25)
        self.velocity_sensitivity.setEditable(True)
        self.velocity_sensitivity.lineEdit().setReadOnly(True)
        self.velocity_sensitivity.lineEdit().setAlignment(Qt.AlignCenter)
        for i in range(1, 11):
            self.velocity_sensitivity.addItem(str(i), i)
        advanced_layout.addWidget(self.velocity_sensitivity, 0, 2)

        # CC Interval with help
        cc_interval_label = QWidget()
        cc_interval_label_layout = QHBoxLayout()
        cc_interval_label_layout.setContentsMargins(0, 0, 0, 0)
        cc_interval_label_layout.setSpacing(5)
        cc_interval_label_layout.addWidget(self.create_help_label(
            "CC step amount (1-16).\n"
            "When using CC +/- keys, this is the\n"
            "amount the CC value will increase or decrease."
        ))
        cc_interval_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "CC Interval:")))
        cc_interval_label.setLayout(cc_interval_label_layout)
        advanced_layout.addWidget(cc_interval_label, 0, 3)
        self.cc_sensitivity = ArrowComboBox()
        self.cc_sensitivity.setMinimumWidth(120)
        self.cc_sensitivity.setMinimumHeight(25)
        self.cc_sensitivity.setMaximumHeight(25)
        self.cc_sensitivity.setEditable(True)
        self.cc_sensitivity.lineEdit().setReadOnly(True)
        self.cc_sensitivity.lineEdit().setAlignment(Qt.AlignCenter)
        for i in range(1, 17):
            self.cc_sensitivity.addItem(str(i), i)
        advanced_layout.addWidget(self.cc_sensitivity, 0, 4)

        # Dynamic Range with help
        dynamic_range_label = QWidget()
        dynamic_range_label_layout = QHBoxLayout()
        dynamic_range_label_layout.setContentsMargins(0, 0, 0, 0)
        dynamic_range_label_layout.setSpacing(5)
        dynamic_range_label_layout.addWidget(self.create_help_label(
            "Random velocity variation amount (0-127).\n"
            "Adds human-like variation to velocity values.\n"
            "0 = No variation, higher = more randomness."
        ))
        dynamic_range_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Dynamic Range:")))
        dynamic_range_label.setLayout(dynamic_range_label_layout)
        advanced_layout.addWidget(dynamic_range_label, 1, 1)
        self.random_velocity_modifier = ArrowComboBox()
        self.random_velocity_modifier.setMinimumWidth(120)
        self.random_velocity_modifier.setMinimumHeight(25)
        self.random_velocity_modifier.setMaximumHeight(25)
        self.random_velocity_modifier.setEditable(True)
        self.random_velocity_modifier.lineEdit().setReadOnly(True)
        self.random_velocity_modifier.lineEdit().setAlignment(Qt.AlignCenter)
        for i in range(128):
            self.random_velocity_modifier.addItem(str(i), i)
        advanced_layout.addWidget(self.random_velocity_modifier, 1, 2)

        # Virtual Instrument with help (formerly "OLED Keyboard") — selects the
        # LCD display mode: piano keyboards or guitar-tab views.
        oled_label = QWidget()
        oled_label_layout = QHBoxLayout()
        oled_label_layout.setContentsMargins(0, 0, 0, 0)
        oled_label_layout.setSpacing(5)
        oled_label_layout.addWidget(self.create_help_label(
            "LCD virtual instrument / display style.\n"
            "Keyboard 1/2/3: piano keyboard at different octaves\n"
            "Guitar Low/Med/High: guitar tablature views"
        ))
        oled_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Virtual Instrument:")))
        oled_label.setLayout(oled_label_layout)
        advanced_layout.addWidget(oled_label, 1, 3)
        self.oled_keyboard = ArrowComboBox()
        self.oled_keyboard.setMinimumWidth(120)
        self.oled_keyboard.setMinimumHeight(25)
        self.oled_keyboard.setMaximumHeight(25)
        self.oled_keyboard.setEditable(True)
        self.oled_keyboard.lineEdit().setReadOnly(True)
        self.oled_keyboard.lineEdit().setAlignment(Qt.AlignCenter)
        self.oled_keyboard.addItem("Keyboard 1", 0)
        self.oled_keyboard.addItem("Keyboard 2", 1)
        self.oled_keyboard.addItem("Keyboard 3", 5)  # firmware enum value 5
        self.oled_keyboard.addItem("Guitar Low", 2)
        self.oled_keyboard.addItem("Guitar Med", 3)
        self.oled_keyboard.addItem("Guitar High", 4)
        advanced_layout.addWidget(self.oled_keyboard, 1, 4)

        # LCD Theme with help — global LCD colour theme. Lives in its own
        # EEPROM region on the keyboard and is synced over a dedicated HID
        # command (not the per-slot settings packet), so it applies and
        # persists immediately on change.
        lcd_theme_label = QWidget()
        lcd_theme_label_layout = QHBoxLayout()
        lcd_theme_label_layout.setContentsMargins(0, 0, 0, 0)
        lcd_theme_label_layout.setSpacing(5)
        lcd_theme_label_layout.addWidget(self.create_help_label(
            "LCD colour theme — recolours the text + keyboard on the LCD.\n"
            "Orange, Matrix Green, White, Light Blue (bright on black).\n"
            "Applies and saves to the keyboard instantly."
        ))
        lcd_theme_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "LCD Theme:")))
        lcd_theme_label.setLayout(lcd_theme_label_layout)
        advanced_layout.addWidget(lcd_theme_label, 3, 3)
        self.lcd_theme = ArrowComboBox()
        self.lcd_theme.setMinimumWidth(120)
        self.lcd_theme.setMinimumHeight(25)
        self.lcd_theme.setMaximumHeight(25)
        self.lcd_theme.setEditable(True)
        self.lcd_theme.lineEdit().setReadOnly(True)
        self.lcd_theme.lineEdit().setAlignment(Qt.AlignCenter)
        # Keep this list + order in sync with lcd_themes[] in the firmware
        # (keyboards/orthomidi5x14/orthomidi5x14.c). Foreground (text + piano)
        # colour on a black background.
        for _idx, _name in enumerate([
            "Orange", "Matrix Green", "White", "Light Blue",
        ]):
            self.lcd_theme.addItem(_name, _idx)
        self.lcd_theme.currentIndexChanged.connect(self.on_lcd_theme_changed)
        advanced_layout.addWidget(self.lcd_theme, 3, 4)

        # SC Light Mode with help
        guide_lights_label = QWidget()
        guide_lights_label_layout = QHBoxLayout()
        guide_lights_label_layout.setContentsMargins(0, 0, 0, 0)
        guide_lights_label_layout.setSpacing(5)
        guide_lights_label_layout.addWidget(self.create_help_label(
            "SmartChord guide light behavior.\n"
            "All Off: No guide lights\n"
            "SmartChord Off: Guide lights off for SmartChord\n"
            "All On: Dynamic: Lights follow chord changes\n"
            "Guitar EADGB/ADGBE: Guitar string tuning layouts"
        ))
        guide_lights_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Guide Lights:")))
        guide_lights_label.setLayout(guide_lights_label_layout)
        advanced_layout.addWidget(guide_lights_label, 2, 1)
        self.smart_chord_light_mode = ArrowComboBox()
        self.smart_chord_light_mode.setMinimumWidth(120)
        self.smart_chord_light_mode.setMinimumHeight(25)
        self.smart_chord_light_mode.setMaximumHeight(25)
        self.smart_chord_light_mode.setEditable(True)
        self.smart_chord_light_mode.lineEdit().setReadOnly(True)
        self.smart_chord_light_mode.lineEdit().setAlignment(Qt.AlignCenter)
        self.smart_chord_light_mode.addItem("All Off", 1)
        self.smart_chord_light_mode.addItem("SmartChord Off", 2)
        self.smart_chord_light_mode.addItem("All On: Dynamic", 0)
        self.smart_chord_light_mode.addItem("All on: Guitar EADGB", 3)
        self.smart_chord_light_mode.addItem("All on: Guitar ADGBE", 4)
        advanced_layout.addWidget(self.smart_chord_light_mode, 2, 2)

        # Colorblind Mode with help
        colorblind_label = QWidget()
        colorblind_label_layout = QHBoxLayout()
        colorblind_label_layout.setContentsMargins(0, 0, 0, 0)
        colorblind_label_layout.setSpacing(5)
        colorblind_label_layout.addWidget(self.create_help_label(
            "Enable colorblind-friendly LED colors.\n"
            "Off: Standard color scheme\n"
            "On: High-contrast colors for better visibility"
        ))
        colorblind_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Colorblind Mode:")))
        colorblind_label.setLayout(colorblind_label_layout)
        advanced_layout.addWidget(colorblind_label, 2, 3)
        self.colorblind_mode = ArrowComboBox()
        self.colorblind_mode.setMinimumWidth(120)
        self.colorblind_mode.setMinimumHeight(25)
        self.colorblind_mode.setMaximumHeight(25)
        self.colorblind_mode.setEditable(True)
        self.colorblind_mode.lineEdit().setReadOnly(True)
        self.colorblind_mode.lineEdit().setAlignment(Qt.AlignCenter)
        self.colorblind_mode.addItem("Off", 0)
        self.colorblind_mode.addItem("On", 1)
        advanced_layout.addWidget(self.colorblind_mode, 2, 4)

        # RGB Layer Mode with help
        rgb_layer_label = QWidget()
        rgb_layer_label_layout = QHBoxLayout()
        rgb_layer_label_layout.setContentsMargins(0, 0, 0, 0)
        rgb_layer_label_layout.setSpacing(5)
        rgb_layer_label_layout.addWidget(self.create_help_label(
            "Enable custom RGB animations per layer.\n"
            "Off: Use global RGB settings\n"
            "On: Each layer can have unique RGB animations"
        ))
        rgb_layer_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "RGB Layer Mode:")))
        rgb_layer_label.setLayout(rgb_layer_label_layout)
        advanced_layout.addWidget(rgb_layer_label, 3, 1)
        self.custom_layer_animations = ArrowComboBox()
        self.custom_layer_animations.setMinimumWidth(120)
        self.custom_layer_animations.setMinimumHeight(25)
        self.custom_layer_animations.setMaximumHeight(25)
        self.custom_layer_animations.setEditable(True)
        self.custom_layer_animations.lineEdit().setReadOnly(True)
        self.custom_layer_animations.lineEdit().setAlignment(Qt.AlignCenter)
        self.custom_layer_animations.addItem("Off", False)
        self.custom_layer_animations.addItem("On", True)
        advanced_layout.addWidget(self.custom_layer_animations, 3, 2)

        # True Sustain with help
        true_sustain_label = QWidget()
        true_sustain_label_layout = QHBoxLayout()
        true_sustain_label_layout.setContentsMargins(0, 0, 0, 0)
        true_sustain_label_layout.setSpacing(5)
        true_sustain_label_layout.addWidget(self.create_help_label(
            "Enable true sustain pedal behavior.\n"
            "Off: Standard sustain behavior\n"
            "On: More realistic piano-style sustain"
        ))
        true_sustain_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "True Sustain:")))
        true_sustain_label.setLayout(true_sustain_label_layout)
        advanced_layout.addWidget(true_sustain_label, 4, 1)
        self.true_sustain = ArrowComboBox()
        self.true_sustain.setMinimumWidth(120)
        self.true_sustain.setMinimumHeight(25)
        self.true_sustain.setMaximumHeight(25)
        self.true_sustain.setEditable(True)
        self.true_sustain.lineEdit().setReadOnly(True)
        self.true_sustain.lineEdit().setAlignment(Qt.AlignCenter)
        self.true_sustain.addItem("Off", False)
        self.true_sustain.addItem("On", True)
        advanced_layout.addWidget(self.true_sustain, 4, 2)

        # Chord Display with help — global setting controlling how the chord
        # progression OLED menu labels each progression.
        chord_display_label = QWidget()
        chord_display_label_layout = QHBoxLayout()
        chord_display_label_layout.setContentsMargins(0, 0, 0, 0)
        chord_display_label_layout.setSpacing(5)
        chord_display_label_layout.addWidget(self.create_help_label(
            "How the chord-progression OLED menu labels each progression.\n"
            "Chords: absolute chord names in the chosen key (e.g. C Am F G)\n"
            "Numerals: key-independent roman numerals (e.g. I vi IV V)\n"
            "Name: the progression's name (e.g. 50s Progression)"
        ))
        chord_display_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Chord Display:")))
        chord_display_label.setLayout(chord_display_label_layout)
        advanced_layout.addWidget(chord_display_label, 4, 3)
        self.chord_display_mode = ArrowComboBox()
        self.chord_display_mode.setMinimumWidth(120)
        self.chord_display_mode.setMinimumHeight(25)
        self.chord_display_mode.setMaximumHeight(25)
        self.chord_display_mode.setEditable(True)
        self.chord_display_mode.lineEdit().setReadOnly(True)
        self.chord_display_mode.lineEdit().setAlignment(Qt.AlignCenter)
        self.chord_display_mode.addItem("Chords", 0)
        self.chord_display_mode.addItem("Numerals", 1)
        self.chord_display_mode.addItem("Name", 2)
        self.chord_display_mode.setCurrentIndex(2)  # Default: Name (legacy behavior)
        advanced_layout.addWidget(self.chord_display_mode, 4, 4)

        # SmartChord Mode widget removed — only tap-toggle remains on the
        # firmware side.  A hidden ArrowComboBox pinned to "Toggle" stays
        # as a backing value so the existing save/load/HID plumbing (keyed
        # off `self.smartchord_mode`) continues to round-trip without a
        # wider protocol rewrite.
        self.smartchord_mode = ArrowComboBox()
        self.smartchord_mode.addItem("Toggle", 1)
        self.smartchord_mode.setCurrentIndex(0)
        self.smartchord_mode.setVisible(False)

        # Aftertouch is now per-layer (configured in Layer Actuation section)
        aftertouch_note = QLabel(tr("MIDIswitchSettingsConfigurator", "Aftertouch: Per-Layer"))
        aftertouch_note.setStyleSheet("QLabel { color: #888; font-style: italic; }")
        aftertouch_note.setToolTip(
            "Aftertouch settings are configured per-layer.\n"
            "Go to the Layer Actuation section to configure\n"
            "aftertouch mode and CC number for each layer."
        )
        advanced_layout.addWidget(aftertouch_note, 5, 1, 1, 2)  # Moved to row 5

        # AT/CC Mode enable flags — two global On/Off toggles that gate the
        # second factory velocity-preset band (curve indices 73-98). Placed in
        # the Advanced grid (row 6). They ride the SAME keyboard-config byte as
        # the Stop Mode mask (packet 1 byte 20): bit5 = Aftertouch Modes,
        # bit6 = CC Modes (bit7 = validity marker). All save/load wiring lives in
        # get_current_settings / apply_settings / pack_basic_data (byte 20) and
        # is unchanged by the move.
        _atcc_help = (
            "Unlock the AT/CC Mode velocity presets (a second factory band).\n"
            "Aftertouch Modes: Vibrato Slow/Fast, Rising, Slow Rise, Wind Chords.\n"
            "CC Modes: the same five as CC-flavored variants.\n"
            "While a group is Off, its presets stay locked in the Velocity tab."
        )
        for _atcc_name, _atcc_attr, _atcc_col in (
            ("Enable Aftertouch Modes", "enable_at_modes", 1),
            ("Enable CC Modes",         "enable_cc_modes", 3),
        ):
            _atcc_label = QWidget()
            _atcc_label_layout = QHBoxLayout()
            _atcc_label_layout.setContentsMargins(0, 0, 0, 0)
            _atcc_label_layout.setSpacing(5)
            _atcc_label_layout.addWidget(self.create_help_label(_atcc_help))
            _atcc_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", _atcc_name + ":")))
            _atcc_label.setLayout(_atcc_label_layout)
            advanced_layout.addWidget(_atcc_label, 6, _atcc_col)
            _atcc_combo = ArrowComboBox()
            _atcc_combo.setMinimumWidth(120)
            _atcc_combo.setMinimumHeight(25)
            _atcc_combo.setMaximumHeight(25)
            _atcc_combo.setEditable(True)
            _atcc_combo.lineEdit().setReadOnly(True)
            _atcc_combo.lineEdit().setAlignment(Qt.AlignCenter)
            _atcc_combo.addItem("Off", False)
            _atcc_combo.addItem("On", True)
            advanced_layout.addWidget(_atcc_combo, 6, _atcc_col + 1)
            setattr(self, _atcc_attr, _atcc_combo)
        # Toggling either enable live-updates which AT/CC band rows are shown in
        # the zone Articulation combos.
        self.enable_at_modes.currentIndexChanged.connect(self._on_atcc_enable_changed)
        self.enable_cc_modes.currentIndexChanged.connect(self._on_atcc_enable_changed)

        # Enable Channel Articulations (own dedicated HID region, not the stop-mode
        # byte). Toggling writes to the device immediately (reads the current map
        # first so only the enable flag changes) and the setting persists on-device.
        _ca_help = (
            "Channel Articulations: map each MIDI channel (1-16) to a velocity\n"
            "articulation in the Velocity tab's 'Channel Articulations' sub-tab.\n"
            "When On, changing a zone's MIDI channel switches that zone to the\n"
            "articulation mapped to the new channel."
        )
        _ca_label = QWidget()
        _ca_label_layout = QHBoxLayout()
        _ca_label_layout.setContentsMargins(0, 0, 0, 0)
        _ca_label_layout.setSpacing(5)
        _ca_label_layout.addWidget(self.create_help_label(_ca_help))
        _ca_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator",
                                             "Enable Channel Articulations:")))
        _ca_label.setLayout(_ca_label_layout)
        advanced_layout.addWidget(_ca_label, 7, 1)
        self.enable_channel_artic = ArrowComboBox()
        self.enable_channel_artic.setMinimumWidth(120)
        self.enable_channel_artic.setMinimumHeight(25)
        self.enable_channel_artic.setMaximumHeight(25)
        self.enable_channel_artic.setEditable(True)
        self.enable_channel_artic.lineEdit().setReadOnly(True)
        self.enable_channel_artic.lineEdit().setAlignment(Qt.AlignCenter)
        self.enable_channel_artic.addItem("Off", False)
        self.enable_channel_artic.addItem("On", True)
        self.enable_channel_artic.currentIndexChanged.connect(
            self._on_channel_artic_enable_changed)
        advanced_layout.addWidget(self.enable_channel_artic, 7, 2)

        # Articulation CC: the CC# that AT/CC articulations set to "CC Default"
        # send on. Global (rides the same dedicated HID region); writes immediately.
        _artcc_label = QWidget()
        _artcc_label_layout = QHBoxLayout()
        _artcc_label_layout.setContentsMargins(0, 0, 0, 0)
        _artcc_label_layout.setSpacing(5)
        _artcc_label_layout.addWidget(self.create_help_label(
            "The CC number that AT/CC articulations set to 'CC Default'\n"
            "actually send on. Change it to re-point every 'CC Default'\n"
            "articulation at once."))
        _artcc_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator",
                                                "Articulation CC:")))
        _artcc_label.setLayout(_artcc_label_layout)
        advanced_layout.addWidget(_artcc_label, 7, 3)
        self.articulation_cc_combo = ArrowComboBox()
        self.articulation_cc_combo.setMinimumWidth(120)
        self.articulation_cc_combo.setMinimumHeight(25)
        self.articulation_cc_combo.setMaximumHeight(25)
        self.articulation_cc_combo.setEditable(True)
        self.articulation_cc_combo.lineEdit().setReadOnly(True)
        self.articulation_cc_combo.lineEdit().setAlignment(Qt.AlignCenter)
        for _cc in range(128):
            self.articulation_cc_combo.addItem("CC#{}".format(_cc), _cc)
        self.articulation_cc_combo.currentIndexChanged.connect(
            self._on_articulation_cc_changed)
        advanced_layout.addWidget(self.articulation_cc_combo, 7, 4)

        # MIDI Routing Settings Group with title on left, container centered
        routing_row_container = QWidget()
        routing_row_layout = QHBoxLayout()
        routing_row_layout.setContentsMargins(0, 0, 0, 0)
        routing_row_container.setLayout(routing_row_layout)

        # Routing title container (left of centered container, vertically centered)
        routing_title_widget = QWidget()
        routing_title_widget.setFixedWidth(150)
        routing_title_layout = QVBoxLayout()
        routing_title_layout.setContentsMargins(0, 0, 0, 0)
        routing_title_widget.setLayout(routing_title_layout)

        routing_title_layout.addStretch()
        routing_title_label = QLabel(tr("MIDIswitchSettingsConfigurator", "MIDI Routing"))
        routing_title_layout.addWidget(routing_title_label)
        routing_title_layout.addStretch()

        midi_routing_group = QGroupBox()
        midi_routing_layout = QGridLayout()
        midi_routing_layout.setHorizontalSpacing(25)
        midi_routing_group.setLayout(midi_routing_layout)

        routing_row_layout.addStretch()
        routing_row_layout.addWidget(routing_title_widget)
        routing_row_layout.addWidget(midi_routing_group)
        routing_row_layout.addStretch()

        # Row 0: Override settings with help icons
        ch_override_label = QWidget()
        ch_override_layout = QHBoxLayout()
        ch_override_layout.setContentsMargins(0, 0, 0, 0)
        ch_override_layout.setSpacing(5)
        ch_override_layout.addWidget(self.create_help_label("Override channel for incoming MIDI"))
        ch_override_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Channel Override:")))
        ch_override_label.setLayout(ch_override_layout)
        midi_routing_layout.addWidget(ch_override_label, 0, 1)
        self.channel_override = ArrowComboBox()
        self.channel_override.setMinimumWidth(80)
        self.channel_override.setMinimumHeight(25)
        self.channel_override.setMaximumHeight(25)
        self.channel_override.setEditable(True)
        self.channel_override.lineEdit().setReadOnly(True)
        self.channel_override.lineEdit().setAlignment(Qt.AlignCenter)
        self.channel_override.addItem("Off", False)
        self.channel_override.addItem("On", True)
        midi_routing_layout.addWidget(self.channel_override, 0, 2)

        vel_override_label = QWidget()
        vel_override_label_layout = QHBoxLayout()
        vel_override_label_layout.setContentsMargins(0, 0, 0, 0)
        vel_override_label_layout.setSpacing(5)
        vel_override_label_layout.addWidget(self.create_help_label(
            "Override velocity for incoming MIDI notes.\n"
            "Off: Use incoming velocity values\n"
            "On: Apply keyboard velocity settings to input"
        ))
        vel_override_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Velocity Override:")))
        vel_override_label.setLayout(vel_override_label_layout)
        midi_routing_layout.addWidget(vel_override_label, 0, 3)
        self.velocity_override = ArrowComboBox()
        self.velocity_override.setMinimumWidth(80)
        self.velocity_override.setMinimumHeight(25)
        self.velocity_override.setMaximumHeight(25)
        self.velocity_override.setEditable(True)
        self.velocity_override.lineEdit().setReadOnly(True)
        self.velocity_override.lineEdit().setAlignment(Qt.AlignCenter)
        self.velocity_override.addItem("Off", False)
        self.velocity_override.addItem("On", True)
        midi_routing_layout.addWidget(self.velocity_override, 0, 4)

        trans_override_label = QWidget()
        trans_override_label_layout = QHBoxLayout()
        trans_override_label_layout.setContentsMargins(0, 0, 0, 0)
        trans_override_label_layout.setSpacing(5)
        trans_override_label_layout.addWidget(self.create_help_label(
            "Override transpose for incoming MIDI notes.\n"
            "Off: Use incoming note values\n"
            "On: Apply keyboard transpose settings to input"
        ))
        trans_override_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Transpose Override:")))
        trans_override_label.setLayout(trans_override_label_layout)
        midi_routing_layout.addWidget(trans_override_label, 0, 5)
        self.transpose_override = ArrowComboBox()
        self.transpose_override.setMinimumWidth(80)
        self.transpose_override.setMinimumHeight(25)
        self.transpose_override.setMaximumHeight(25)
        self.transpose_override.setEditable(True)
        self.transpose_override.lineEdit().setReadOnly(True)
        self.transpose_override.lineEdit().setAlignment(Qt.AlignCenter)
        self.transpose_override.addItem("Off", False)
        self.transpose_override.addItem("On", True)
        midi_routing_layout.addWidget(self.transpose_override, 0, 6)

        # Row 1: MIDI routing modes with help
        midi_in_label = QWidget()
        midi_in_label_layout = QHBoxLayout()
        midi_in_label_layout.setContentsMargins(0, 0, 0, 0)
        midi_in_label_layout.setSpacing(5)
        midi_in_label_layout.addWidget(self.create_help_label(
            "How incoming MIDI from DIN port is processed.\n"
            "Process All: Process all incoming MIDI\n"
            "Thru: Pass MIDI through unchanged\n"
            "Clock Only: Only process clock messages\n"
            "Ignore: Ignore all incoming MIDI"
        ))
        midi_in_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "MIDI IN Mode:")))
        midi_in_label.setLayout(midi_in_label_layout)
        midi_routing_layout.addWidget(midi_in_label, 1, 1)
        self.midi_in_mode = ArrowComboBox()
        self.midi_in_mode.setMinimumWidth(120)
        self.midi_in_mode.setMinimumHeight(25)
        self.midi_in_mode.setMaximumHeight(25)
        self.midi_in_mode.setEditable(True)
        self.midi_in_mode.lineEdit().setReadOnly(True)
        self.midi_in_mode.lineEdit().setAlignment(Qt.AlignCenter)
        self.midi_in_mode.addItem("Process All", 0)
        self.midi_in_mode.addItem("Thru", 1)
        self.midi_in_mode.addItem("Clock Only", 2)
        self.midi_in_mode.addItem("Ignore", 3)
        midi_routing_layout.addWidget(self.midi_in_mode, 1, 2)

        usb_midi_label = QWidget()
        usb_midi_label_layout = QHBoxLayout()
        usb_midi_label_layout.setContentsMargins(0, 0, 0, 0)
        usb_midi_label_layout.setSpacing(5)
        usb_midi_label_layout.addWidget(self.create_help_label(
            "How incoming USB MIDI is processed.\n"
            "Process All: Process all incoming MIDI\n"
            "Thru: Pass MIDI through unchanged\n"
            "Clock Only: Only process clock messages\n"
            "Ignore: Ignore all incoming USB MIDI"
        ))
        usb_midi_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "USB MIDI Mode:")))
        usb_midi_label.setLayout(usb_midi_label_layout)
        midi_routing_layout.addWidget(usb_midi_label, 1, 3)
        self.usb_midi_mode = ArrowComboBox()
        self.usb_midi_mode.setMinimumWidth(120)
        self.usb_midi_mode.setMinimumHeight(25)
        self.usb_midi_mode.setMaximumHeight(25)
        self.usb_midi_mode.setEditable(True)
        self.usb_midi_mode.lineEdit().setReadOnly(True)
        self.usb_midi_mode.lineEdit().setAlignment(Qt.AlignCenter)
        self.usb_midi_mode.addItem("Process All", 0)
        self.usb_midi_mode.addItem("Thru", 1)
        self.usb_midi_mode.addItem("Clock Only", 2)
        self.usb_midi_mode.addItem("Ignore", 3)
        midi_routing_layout.addWidget(self.usb_midi_mode, 1, 4)

        clock_source_label = QWidget()
        clock_source_label_layout = QHBoxLayout()
        clock_source_label_layout.setContentsMargins(0, 0, 0, 0)
        clock_source_label_layout.setSpacing(5)
        clock_source_label_layout.addWidget(self.create_help_label(
            "Where MIDI timing clock comes from.\n"
            "Local: Use internal clock\n"
            "USB: Sync to USB MIDI clock\n"
            "MIDI IN: Sync to DIN MIDI input clock"
        ))
        clock_source_label_layout.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Clock Source:")))
        clock_source_label.setLayout(clock_source_label_layout)
        midi_routing_layout.addWidget(clock_source_label, 1, 5)
        self.midi_clock_source = ArrowComboBox()
        self.midi_clock_source.setMinimumWidth(120)
        self.midi_clock_source.setMinimumHeight(25)
        self.midi_clock_source.setMaximumHeight(25)
        self.midi_clock_source.setEditable(True)
        self.midi_clock_source.lineEdit().setReadOnly(True)
        self.midi_clock_source.lineEdit().setAlignment(Qt.AlignCenter)
        self.midi_clock_source.addItem("Local", 0)
        self.midi_clock_source.addItem("USB", 1)
        self.midi_clock_source.addItem("MIDI IN", 2)
        midi_routing_layout.addWidget(self.midi_clock_source, 1, 6)

        # Add MIDI Routing before Advanced Settings (swapped order)
        main_layout.addWidget(routing_row_container)
        main_layout.addWidget(advanced_row_container)

        # Apply stylesheet to center combo box text and remove padding
        main_widget.setStyleSheet("""
            QComboBox {
                text-align: center;
                padding: 0px;
            }
            QComboBox::drop-down {
                padding: 0px;
            }
            QComboBox QAbstractItemView {
                padding: 0px;
            }
        """)

        # Connect widgets to real-time HID updates
        self.global_channel.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_CHANNEL_NUMBER, self.global_channel.currentData())
        )
        self.global_transpose.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_TRANSPOSE_NUMBER, self.global_transpose.currentData())
        )
        self.global_velocity_curve.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_HE_VELOCITY_CURVE, self.global_velocity_curve.currentData())
        )
        # Velocity min/max connections removed - now per velocity preset
        self.base_sustain.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_BASE_SUSTAIN, self.base_sustain.currentData())
        )
        # global_aftertouch connections removed - aftertouch is now per-layer

        # KeySplit widgets
        self.key_split_channel.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_KEYSPLITCHANNEL, self.key_split_channel.currentData())
        )
        self.transpose_number2.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_TRANSPOSE_NUMBER2, self.transpose_number2.currentData())
        )
        self.velocity_curve2.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_KEYSPLIT_HE_VELOCITY_CURVE, self.velocity_curve2.currentData())
        )
        # Velocity min/max connections removed - now per velocity preset
        self.keysplit_sustain.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_KEYSPLIT_SUSTAIN, self.keysplit_sustain.currentData())
        )

        # TripleSplit widgets
        self.key_split2_channel.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_KEYSPLIT2CHANNEL, self.key_split2_channel.currentData())
        )
        self.transpose_number3.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_TRANSPOSE_NUMBER3, self.transpose_number3.currentData())
        )
        self.velocity_curve3.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_TRIPLESPLIT_HE_VELOCITY_CURVE, self.velocity_curve3.currentData())
        )
        # Velocity min/max connections removed - now per velocity preset
        self.triplesplit_sustain.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_TRIPLESPLIT_SUSTAIN, self.triplesplit_sustain.currentData())
        )

        # Split status updates are now handled by _on_split_enable_changed connected to the on/off dropdowns

        # MIDI Routing Override Settings
        self.channel_override.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_CHANNEL_OVERRIDE, 1 if self.channel_override.currentData() else 0)
        )
        self.velocity_override.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_VELOCITY_OVERRIDE, 1 if self.velocity_override.currentData() else 0)
        )
        self.transpose_override.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_TRANSPOSE_OVERRIDE, 1 if self.transpose_override.currentData() else 0)
        )
        self.midi_in_mode.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_MIDI_IN_MODE, self.midi_in_mode.currentData())
        )
        self.usb_midi_mode.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_USB_MIDI_MODE, self.usb_midi_mode.currentData())
        )
        self.midi_clock_source.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_MIDI_CLOCK_SOURCE, self.midi_clock_source.currentData())
        )

        # Macro Override Live Notes
        self.macro_override_live_notes.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_MACRO_OVERRIDE_LIVE_NOTES, 1 if self.macro_override_live_notes.currentData() else 0)
        )

        # SmartChord Mode
        self.smartchord_mode.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_SMARTCHORD_MODE, self.smartchord_mode.currentData())
        )

        # SmartChord Ignore per zone
        self.base_smartchord_ignore.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_BASE_SMARTCHORD_IGNORE, self.base_smartchord_ignore.currentData())
        )
        self.keysplit_smartchord_ignore.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_KEYSPLIT_SMARTCHORD_IGNORE, self.keysplit_smartchord_ignore.currentData())
        )
        self.triplesplit_smartchord_ignore.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_TRIPLESPLIT_SMARTCHORD_IGNORE, self.triplesplit_smartchord_ignore.currentData())
        )

        # Chord Display (global): how the chord-progression OLED menu labels progressions
        self.chord_display_mode.currentIndexChanged.connect(
            lambda: self.send_param_update(PARAM_CHORD_DISPLAY_MODE, self.chord_display_mode.currentData())
        )

        # Drum Keybinds tab (global default drum-voice bindings for the drum machine)
        self.setup_drum_keybinds_tab()

    # =====================================================================
    # DRUM SETTINGS (global default drum-machine channel + voice bindings)
    # =====================================================================
    # A global default MIDI channel plus, per drum voice, a default MIDI note +
    # velocity. Changing the default channel forces ALL drum machines to it.
    # Changing a note/velocity default updates every drum machine slot that still
    # matches the previous default (uncustomized slots follow along); manually-
    # customized slots keep their own bindings. "Reset ALL bindings to default"
    # restores all slots AND the global default to GM factory.
    # Sourced from editor/drum_voices.py (shared with the step sequencer);
    # keep that module in lockstep with firmware factory_seq / drum_live defs.
    DRUM_VOICE_NAMES = drum_voices.DRUM_VOICE_NAMES
    DRUM_GM_DEFAULT_NOTES = drum_voices.DRUM_GM_DEFAULT_NOTES
    DRUM_GM_DEFAULT_VELS = drum_voices.DRUM_GM_DEFAULT_VELS
    DRUM_GM_DEFAULT_CHANNEL = drum_voices.DRUM_GM_DEFAULT_CHANNEL
    DRUM_EXTRA_NAMES = drum_voices.DRUM_EXTRA_NAMES
    DRUM_EXTRA_CATS = drum_voices.DRUM_EXTRA_CATS
    DRUM_EXTRA_DEFAULT_NOTES = drum_voices.DRUM_EXTRA_DEFAULT_NOTES

    @staticmethod
    def _midi_note_label(note):
        names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
        return "{}{} ({})".format(names[note % 12], (note // 12) - 1, note)

    def setup_drum_keybinds_tab(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout()
        container.setLayout(layout)
        scroll_area.setWidget(container)
        self.tabs_widget.addTab(scroll_area, tr("MIDIswitchSettingsConfigurator", "Drum Settings"))

        layout.addSpacing(8)
        title = QLabel(tr("MIDIswitchSettingsConfigurator", "Drum Settings"))
        title.setStyleSheet("font-weight: bold; font-size: 14pt;")
        layout.addWidget(title)
        desc = QLabel(tr("MIDIswitchSettingsConfigurator",
            "Global defaults for the drum machine. The default channel applies to ALL drum "
            "machines. The default note and velocity for each drum voice update every drum "
            "machine whose bindings still match the previous default; drum machines you have "
            "customized individually keep their own bindings."))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888;")
        layout.addWidget(desc)
        layout.addSpacing(6)

        self._drum_keybinds_loading = False

        # Default channel (applies to every drum machine)
        chan_row = QHBoxLayout()
        chan_row.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Default Channel")))
        self.drum_channel_combo = ArrowComboBox()
        for ch in range(16):
            self.drum_channel_combo.addItem("Ch {}".format(ch + 1), ch)
        self.drum_channel_combo.setCurrentIndex(self.DRUM_GM_DEFAULT_CHANNEL)
        self.drum_channel_combo.setFixedWidth(100)
        self.drum_channel_combo.currentIndexChanged.connect(self.on_drum_channel_changed)
        chan_row.addWidget(self.drum_channel_combo)
        chan_row.addStretch()
        layout.addLayout(chan_row)
        layout.addSpacing(6)

        # ---- Preset Layout -------------------------------------------------
        preset_group = QGroupBox(tr("MIDIswitchSettingsConfigurator", "Preset Layout"))
        preset_row = QHBoxLayout()
        preset_group.setLayout(preset_row)
        gm_btn = QPushButton(tr("MIDIswitchSettingsConfigurator", "General MIDI"))
        gm_btn.clicked.connect(self.on_drum_preset_gm)
        preset_row.addWidget(gm_btn)
        reset_btn = QPushButton(tr("MIDIswitchSettingsConfigurator", "Reset to Default"))
        reset_btn.clicked.connect(self.on_reset_drum_keybinds)
        preset_row.addWidget(reset_btn)
        preset_row.addStretch()
        layout.addWidget(preset_group)
        layout.addSpacing(6)

        # ---- Custom Layout: 12 sequenced voices (left: Note + Velocity) and
        #      the 16 DrumLIVE-only extra voicings (right: Note only) side by
        #      side. All dropdowns / velocity boxes are 100px and packed tight.
        W = 100
        custom_group = QGroupBox(tr("MIDIswitchSettingsConfigurator", "Custom Layout"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)
        custom_group.setLayout(grid)

        # Left panel headers (cols 0-2)
        grid.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Voice")), 0, 0)
        grid.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Note")), 0, 1)
        grid.addWidget(QLabel(tr("MIDIswitchSettingsConfigurator", "Velocity")), 0, 2)
        # Right panel header (cols 4-5): Extra Voicings
        extra_hdr = QLabel(tr("MIDIswitchSettingsConfigurator",
            "Extra Voicings (DrumLIVE filter only — notes, no velocity)"))
        extra_hdr.setStyleSheet("color: #888; font-style: italic;")
        grid.addWidget(extra_hdr, 0, 4, 1, 2)

        self.drum_note_combos = []
        self.drum_vel_spins = []
        for v in range(12):
            grid.addWidget(QLabel(self.DRUM_VOICE_NAMES[v]), v + 1, 0)

            note_combo = ArrowComboBox()
            for n in range(128):
                note_combo.addItem(self._midi_note_label(n), n)
            note_combo.setCurrentIndex(self.DRUM_GM_DEFAULT_NOTES[v])
            note_combo.setFixedWidth(W)
            note_combo.currentIndexChanged.connect(self.on_drum_keybinds_changed)
            grid.addWidget(note_combo, v + 1, 1)
            self.drum_note_combos.append(note_combo)

            vel_spin = ArrowSpinBox()
            vel_spin.setRange(0, 127)
            vel_spin.setValue(self.DRUM_GM_DEFAULT_VELS[v])
            vel_spin.setFixedWidth(W)
            # editingFinished (not valueChanged) to avoid an EEPROM write per tick
            vel_spin.editingFinished.connect(self.on_drum_keybinds_changed)
            grid.addWidget(vel_spin, v + 1, 2)
            self.drum_vel_spins.append(vel_spin)

        # Right panel: extra voicings (Name + Note only — no velocity, no category)
        self.drum_extra_note_combos = []
        for e in range(len(self.DRUM_EXTRA_NAMES)):
            r = e + 1
            grid.addWidget(QLabel(self.DRUM_EXTRA_NAMES[e]), r, 4)
            note_combo = ArrowComboBox()
            for n in range(128):
                note_combo.addItem(self._midi_note_label(n), n)
            note_combo.setCurrentIndex(self.DRUM_EXTRA_DEFAULT_NOTES[e])
            note_combo.setFixedWidth(W)
            note_combo.currentIndexChanged.connect(self.on_drum_extra_changed)
            grid.addWidget(note_combo, r, 5)
            self.drum_extra_note_combos.append(note_combo)

        # gap column between the two panels; keep everything left-packed
        grid.setColumnMinimumWidth(3, 24)
        grid.setColumnStretch(6, 1)

        layout.addWidget(custom_group)
        layout.addStretch()

    def _set_drum_keybinds_ui(self, notes, vels, channel=None):
        """Populate the Drum Settings widgets without emitting change events."""
        self._drum_keybinds_loading = True
        try:
            for v in range(12):
                n = notes[v] if v < len(notes) else self.DRUM_GM_DEFAULT_NOTES[v]
                self.drum_note_combos[v].setCurrentIndex(max(0, min(127, int(n))))
                vv = vels[v] if v < len(vels) else self.DRUM_GM_DEFAULT_VELS[v]
                self.drum_vel_spins[v].setValue(max(0, min(127, int(vv))))
            if channel is not None:
                self.drum_channel_combo.setCurrentIndex(max(0, min(15, int(channel))))
        finally:
            self._drum_keybinds_loading = False

    def on_drum_keybinds_changed(self, *args):
        if getattr(self, '_drum_keybinds_loading', False):
            return
        if not (self.valid() and isinstance(self.device, VialKeyboard)):
            return
        notes = [c.currentData() for c in self.drum_note_combos]
        vels = [s.value() for s in self.drum_vel_spins]
        try:
            self.device.keyboard.set_drum_keybinds(notes, vels)
        except Exception:
            pass

    def on_drum_channel_changed(self, *args):
        if getattr(self, '_drum_keybinds_loading', False):
            return
        if not (self.valid() and isinstance(self.device, VialKeyboard)):
            return
        try:
            self.device.keyboard.set_drum_default_channel(self.drum_channel_combo.currentData())
        except Exception:
            pass

    def _set_drum_extra_ui(self, notes):
        """Populate the extra-voicing note combos without emitting change events."""
        self._drum_keybinds_loading = True
        try:
            for e in range(len(self.drum_extra_note_combos)):
                n = notes[e] if e < len(notes) else self.DRUM_EXTRA_DEFAULT_NOTES[e]
                self.drum_extra_note_combos[e].setCurrentIndex(max(0, min(127, int(n))))
        finally:
            self._drum_keybinds_loading = False

    def on_drum_extra_changed(self, *args):
        if getattr(self, '_drum_keybinds_loading', False):
            return
        if not (self.valid() and isinstance(self.device, VialKeyboard)):
            return
        notes = [c.currentData() for c in self.drum_extra_note_combos]
        try:
            self.device.keyboard.set_drum_extra_notes(notes)
        except Exception:
            pass

    def on_drum_preset_gm(self):
        """Apply the General MIDI map to the 12 voices + extras (keeps channel)."""
        self._set_drum_keybinds_ui(self.DRUM_GM_DEFAULT_NOTES, self.DRUM_GM_DEFAULT_VELS)
        self._set_drum_extra_ui(self.DRUM_EXTRA_DEFAULT_NOTES)
        if not (self.valid() and isinstance(self.device, VialKeyboard)):
            return
        try:
            self.device.keyboard.set_drum_keybinds(self.DRUM_GM_DEFAULT_NOTES, self.DRUM_GM_DEFAULT_VELS)
            self.device.keyboard.set_drum_extra_notes(self.DRUM_EXTRA_DEFAULT_NOTES)
        except Exception:
            pass

    def on_reset_drum_keybinds(self):
        if not (self.valid() and isinstance(self.device, VialKeyboard)):
            self._set_drum_keybinds_ui(self.DRUM_GM_DEFAULT_NOTES, self.DRUM_GM_DEFAULT_VELS,
                                       self.DRUM_GM_DEFAULT_CHANNEL)
            self._set_drum_extra_ui(self.DRUM_EXTRA_DEFAULT_NOTES)
            return
        confirm = QMessageBox.question(
            self, tr("MIDIswitchSettingsConfigurator", "Reset Drum Settings"),
            tr("MIDIswitchSettingsConfigurator",
               "Reset ALL drum machine bindings, channel, and the global default to "
               "factory defaults?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        result = None
        try:
            result = self.device.keyboard.reset_drum_keybinds()
        except Exception:
            result = None
        if result:
            notes, vels, channel = result
            self._set_drum_keybinds_ui(notes, vels, channel)
        else:
            self._set_drum_keybinds_ui(self.DRUM_GM_DEFAULT_NOTES, self.DRUM_GM_DEFAULT_VELS,
                                       self.DRUM_GM_DEFAULT_CHANNEL)
        # Firmware reset also restores the extra voicings — reload them.
        try:
            extras = self.device.keyboard.get_drum_extra_notes()
        except Exception:
            extras = None
        self._set_drum_extra_ui(extras if extras else self.DRUM_EXTRA_DEFAULT_NOTES)

    def load_drum_keybinds_from_keyboard(self):
        if not (self.valid() and isinstance(self.device, VialKeyboard)):
            return
        try:
            result = self.device.keyboard.get_drum_keybinds()
        except Exception:
            result = None
        if result:
            notes, vels, channel = result
            self._set_drum_keybinds_ui(notes, vels, channel)
        try:
            extras = self.device.keyboard.get_drum_extra_notes()
        except Exception:
            extras = None
        if extras:
            self._set_drum_extra_ui(extras)

    def send_param_update(self, param_id, value):
        """Send real-time HID parameter update to keyboard"""
        # While apply_settings is populating the widgets from the device, the
        # combos' currentIndexChanged handlers fire — those must never echo the
        # (possibly defaulted) values back to the device. Without this guard a
        # connect/load could silently overwrite device state (e.g. reset the
        # active articulation to Linear).
        if getattr(self, '_loading_settings', False):
            return
        try:
            if self.device and isinstance(self.device, VialKeyboard):
                self.device.keyboard.set_keyboard_param_single(param_id, value)
        except Exception as e:
            # Silently fail - firmware may not support this parameter yet
            pass

    def _atcc_enabled_flags(self):
        """Current AT/CC-band enable state from the Advanced toggles (default On
        if the widgets aren't built yet)."""
        cc, at = True, True
        try:
            cc = bool(self.enable_cc_modes.currentData())
        except Exception:
            pass
        try:
            at = bool(self.enable_at_modes.currentData())
        except Exception:
            pass
        return cc, at

    def _refresh_zone_articulation_combos(self):
        """Rebuild the three zone Articulation combos with the device's user-slot
        names, then hide unconfigured user slots + disabled AT/CC bands. Each
        combo's current selection is preserved and kept visible."""
        user_names, user_configured = None, None
        try:
            if self.device and isinstance(self.device, VialKeyboard):
                res = self.device.keyboard.get_all_user_curve_names()
                if res:
                    user_names, user_configured = res
        except Exception:
            user_names, user_configured = None, None
        self._artic_user_names = user_names
        self._artic_user_configured = user_configured
        cc, at = self._atcc_enabled_flags()
        for combo in (self.global_velocity_curve, self.velocity_curve2, self.velocity_curve3):
            keep = combo.currentData()
            populate_articulation_combo(combo, user_names=user_names)
            blocked = combo.blockSignals(True)
            try:
                if keep is not None:
                    for i in range(combo.count()):
                        if combo.itemData(i) == keep:
                            combo.setCurrentIndex(i)
                            break
            finally:
                combo.blockSignals(blocked)
            apply_articulation_visibility(combo, user_configured=user_configured,
                                          cc_enabled=cc, at_enabled=at, keep_index=keep)

    def _refresh_zone_articulation_visibility(self):
        """Re-apply band visibility to the zone Articulation combos using the
        cached user-configured flags + the live Enable AT/CC toggles, keeping
        each combo's current index visible. Cheap (no device read / rebuild)."""
        cc, at = self._atcc_enabled_flags()
        cfg = getattr(self, '_artic_user_configured', None)
        for combo in (self.global_velocity_curve, self.velocity_curve2, self.velocity_curve3):
            apply_articulation_visibility(combo, user_configured=cfg,
                                          cc_enabled=cc, at_enabled=at,
                                          keep_index=combo.currentData())

    def _on_atcc_enable_changed(self, *args):
        """Live-update zone Articulation combos when an Enable AT/CC toggle flips."""
        if getattr(self, '_loading_settings', False):
            return
        self._refresh_zone_articulation_visibility()

    def _on_split_enable_changed(self):
        """Handle split enable changes - compute and send split status based on on/off combinations"""
        if getattr(self, '_loading_settings', False):
            return  # populating from device — don't echo back
        # Compute channel split status: 0=disabled, 1=keysplit, 2=triplesplit, 3=both
        channel_status = self._compute_split_status(
            self.keysplit_channel_enable.currentData(),
            self.triplesplit_channel_enable.currentData()
        )
        self.send_param_update(PARAM_KEYSPLITSTATUS, channel_status)

        # Compute transpose split status
        transpose_status = self._compute_split_status(
            self.keysplit_transpose_enable.currentData(),
            self.triplesplit_transpose_enable.currentData()
        )
        self.send_param_update(PARAM_KEYSPLITTRANSPOSESTATUS, transpose_status)

        # Compute velocity split status
        velocity_status = self._compute_split_status(
            self.keysplit_velocity_enable.currentData(),
            self.triplesplit_velocity_enable.currentData()
        )
        self.send_param_update(PARAM_KEYSPLITVELOCITYSTATUS, velocity_status)

    def _compute_split_status(self, keysplit_on, triplesplit_on):
        """Compute split status from keysplit and triplesplit enable states.
        Returns: 0=disabled, 1=keysplit only, 2=triplesplit only, 3=both"""
        if keysplit_on and triplesplit_on:
            return 3  # Both Splits On
        elif keysplit_on:
            return 1  # KeySplit On
        elif triplesplit_on:
            return 2  # TripleSplit On
        else:
            return 0  # Disable Keysplit

    def get_channel_split_status(self):
        """Get computed channel split status"""
        return self._compute_split_status(
            self.keysplit_channel_enable.currentData(),
            self.triplesplit_channel_enable.currentData()
        )

    def get_transpose_split_status(self):
        """Get computed transpose split status"""
        return self._compute_split_status(
            self.keysplit_transpose_enable.currentData(),
            self.triplesplit_transpose_enable.currentData()
        )

    def get_velocity_split_status(self):
        """Get computed velocity split status"""
        return self._compute_split_status(
            self.keysplit_velocity_enable.currentData(),
            self.triplesplit_velocity_enable.currentData()
        )

    def get_current_settings(self):
        """Get current UI settings as dictionary"""
        return {
            "velocity_sensitivity": self.velocity_sensitivity.currentData(),
            "cc_sensitivity": self.cc_sensitivity.currentData(),
            "transpose_number2": self.transpose_number2.currentData(),
            "transpose_number3": self.transpose_number3.currentData(),
            "random_velocity_modifier": self.random_velocity_modifier.currentData(),
            "oled_keyboard": self.oled_keyboard.currentData(),
            # Per-function Stop Mode bitmask (rides basic packet byte 20 as
            # 0x80 | mask; replaces the old reserved/overdub byte)
            "stop_mode": self.get_stop_mode_mask(),
            # AT/CC Mode enable flags (same packet byte 20, bit5/bit6)
            "enable_at_modes": self.enable_at_modes.currentData(),
            "enable_cc_modes": self.enable_cc_modes.currentData(),
            "smart_chord_light_mode": self.smart_chord_light_mode.currentData(),
            "key_split_channel": self.key_split_channel.currentData(),
            "key_split2_channel": self.key_split2_channel.currentData(),
            "key_split_status": self.get_channel_split_status(),
            "key_split_transpose_status": self.get_transpose_split_status(),
            "key_split_velocity_status": self.get_velocity_split_status(),
            # New enable flags for save/load
            "keysplit_channel_enable": self.keysplit_channel_enable.currentData(),
            "keysplit_transpose_enable": self.keysplit_transpose_enable.currentData(),
            "keysplit_velocity_enable": self.keysplit_velocity_enable.currentData(),
            "triplesplit_channel_enable": self.triplesplit_channel_enable.currentData(),
            "triplesplit_transpose_enable": self.triplesplit_transpose_enable.currentData(),
            "triplesplit_velocity_enable": self.triplesplit_velocity_enable.currentData(),
            "custom_layer_animations_enabled": self.custom_layer_animations.currentData(),
            "unsynced_mode_active": self.unsynced_mode.currentData(),
            "sample_mode_active": self.sample_mode.currentData(),
            "instant_loop_start": self.instant_loop_start.currentData(),
            "colorblindmode": self.colorblind_mode.currentData(),
            "cclooprecording": self.cc_loop_recording.currentData(),
            "truesustain": self.true_sustain.currentData(),
            # KeySplit/TripleSplit velocity settings (curve only - min/max now per velocity preset)
            "velocity_curve2": self.velocity_curve2.currentData(),
            "velocity_curve3": self.velocity_curve3.currentData(),
            # Global MIDI settings
            "global_transpose": self.global_transpose.currentData(),
            "global_channel": self.global_channel.currentData(),
            "global_velocity_curve": self.global_velocity_curve.currentData(),
            # global_aftertouch_cc removed - now per-layer
            # Sustain settings
            "base_sustain": self.base_sustain.currentData(),
            "keysplit_sustain": self.keysplit_sustain.currentData(),
            "triplesplit_sustain": self.triplesplit_sustain.currentData(),
            # MIDI Routing Override settings
            "channel_override": self.channel_override.currentData(),
            "velocity_override": self.velocity_override.currentData(),
            "transpose_override": self.transpose_override.currentData(),
            "midi_in_mode": self.midi_in_mode.currentData(),
            "usb_midi_mode": self.usb_midi_mode.currentData(),
            "midi_clock_source": self.midi_clock_source.currentData(),
            # Macro override live notes
            "macro_override_live_notes": self.macro_override_live_notes.currentData(),
            # SmartChord settings
            "smartchord_mode": self.smartchord_mode.currentData(),
            "base_smartchord_ignore": self.base_smartchord_ignore.currentData(),
            "keysplit_smartchord_ignore": self.keysplit_smartchord_ignore.currentData(),
            "triplesplit_smartchord_ignore": self.triplesplit_smartchord_ignore.currentData(),
            # Chord progression OLED display mode (global)
            "chord_display_mode": self.chord_display_mode.currentData()
        }

    def apply_settings(self, config):
        """Populate the tab's widgets from a device config dict. Wrapped in the
        _loading_settings guard so the widgets' live-send handlers can't echo
        values back to the device mid-population (see send_param_update)."""
        self._loading_settings = True
        try:
            self._apply_settings_inner(config)
        finally:
            self._loading_settings = False

    def _apply_settings_inner(self, config):
        """Apply settings dictionary to UI"""
        def set_combo_by_data(combo, value, default_value=None):
            # CRITICAL: block signals while populating from a loaded config.
            # Many of these combos have currentIndexChanged wired to a live
            # send_param_update() (e.g. sustain -> PARAM 15/16/17, chord display
            # -> PARAM 55). Without blocking, loading a slot whose value the GET
            # packet can't report (defaulting the combo to 0/2) fires a live
            # PARAM write that overwrites the value the device JUST loaded — so a
            # GUI "Load Slot" silently wiped the device's sustain / chord-display.
            combo.blockSignals(True)
            try:
                for i in range(combo.count()):
                    if combo.itemData(i) == value:
                        combo.setCurrentIndex(i)
                        return
                if default_value is not None:
                    for i in range(combo.count()):
                        if combo.itemData(i) == default_value:
                            combo.setCurrentIndex(i)
                            return
            finally:
                combo.blockSignals(False)
        
        set_combo_by_data(self.velocity_sensitivity, config.get("velocity_sensitivity"), 1)
        set_combo_by_data(self.cc_sensitivity, config.get("cc_sensitivity"), 1)
        set_combo_by_data(self.transpose_number2, config.get("transpose_number2"), 0)
        set_combo_by_data(self.transpose_number3, config.get("transpose_number3"), 0)
        set_combo_by_data(self.random_velocity_modifier, config.get("random_velocity_modifier"), 0)
        # Legacy migration: older firmware stored the "Screenboard 2" mode as 12.
        # Map any legacy value into the new 5-state enum before populating the combo.
        _oled_kbd_value = config.get("oled_keyboard", 0)
        if _oled_kbd_value == 12:
            _oled_kbd_value = 1
        elif _oled_kbd_value is None or _oled_kbd_value < 0 or _oled_kbd_value > 5:
            _oled_kbd_value = 0  # valid modes: 0-5 (5 = Keyboard 3)
        set_combo_by_data(self.oled_keyboard, _oled_kbd_value, 0)

        # Per-function Stop Mode (basic packet byte 20). A GET from real
        # hardware reports "stop_mode_supported" (bit 7 marker present);
        # local defaults dicts omit it, in which case we keep the current
        # support state and only reapply the mask.
        if "stop_mode_supported" in config:
            self._apply_stop_mode(config.get("stop_mode", 0),
                                  config.get("stop_mode_supported"))
        elif "stop_mode" in config:
            self._apply_stop_mode(config.get("stop_mode", 0),
                                  self.stop_mode_supported)

        # AT/CC Mode enable flags — same packet byte 20 as Stop Mode, so gate
        # their editability on the same feature-detect marker.
        set_combo_by_data(self.enable_at_modes, config.get("enable_at_modes"), False)
        set_combo_by_data(self.enable_cc_modes, config.get("enable_cc_modes"), False)
        self.enable_at_modes.setEnabled(self.stop_mode_supported)
        self.enable_cc_modes.setEnabled(self.stop_mode_supported)
        # Snapshot the byte-20 widget state as loaded, so the save flow can
        # detect "untouched since load" and prefer the device's live values
        # (the Velocity tab and the on-device menu also write these — a stale
        # Save must not silently revert them). See on_save_slot.
        self._byte20_loaded = (self.get_stop_mode_mask(),
                               bool(self.enable_at_modes.currentData()),
                               bool(self.enable_cc_modes.currentData()))

        # LCD colour theme is a global setting carried over a dedicated HID
        # command (not the per-slot config packet), so fetch it directly and
        # populate the combo without re-sending it back to the keyboard.
        if self.device and isinstance(self.device, VialKeyboard):
            theme_idx = self.device.keyboard.get_lcd_theme()
            if theme_idx is not None:
                self.lcd_theme.blockSignals(True)
                set_combo_by_data(self.lcd_theme, theme_idx, 0)
                self.lcd_theme.blockSignals(False)

            # Channel Articulations enable is a global carried over its own HID
            # command (not the per-slot packet); fetch + populate without echoing.
            ca = self.device.keyboard.get_channel_articulations()
            if ca is not None and hasattr(self, 'enable_channel_artic'):
                self.enable_channel_artic.blockSignals(True)
                set_combo_by_data(self.enable_channel_artic, bool(ca.get('enabled', False)), False)
                self.enable_channel_artic.blockSignals(False)
                if hasattr(self, 'articulation_cc_combo'):
                    self.articulation_cc_combo.blockSignals(True)
                    set_combo_by_data(self.articulation_cc_combo, ca.get('articulation_cc', 1), 1)
                    # Firmware without the Articulation CC byte (bit-7 marker
                    # absent) can't store it - grey the combo out.
                    self.articulation_cc_combo.setEnabled(
                        bool(ca.get('articulation_cc_supported', False)))
                    self.articulation_cc_combo.blockSignals(False)

        set_combo_by_data(self.smart_chord_light_mode, config.get("smart_chord_light_mode"), 0)
        set_combo_by_data(self.key_split_channel, config.get("key_split_channel"), 0)
        set_combo_by_data(self.key_split2_channel, config.get("key_split2_channel"), 0)

        # Handle new enable flags, with backward compatibility for old split status values
        def split_status_to_enables(status):
            """Convert split status (0-3) to keysplit_on, triplesplit_on tuple"""
            if status == 3:
                return (1, 1)  # Both on
            elif status == 2:
                return (0, 1)  # Triplesplit only
            elif status == 1:
                return (1, 0)  # Keysplit only
            else:
                return (0, 0)  # Both off

        # Channel enable flags
        if "keysplit_channel_enable" in config:
            set_combo_by_data(self.keysplit_channel_enable, config.get("keysplit_channel_enable"), 0)
            set_combo_by_data(self.triplesplit_channel_enable, config.get("triplesplit_channel_enable"), 0)
        else:
            ks, ts = split_status_to_enables(config.get("key_split_status", 0))
            set_combo_by_data(self.keysplit_channel_enable, ks, 0)
            set_combo_by_data(self.triplesplit_channel_enable, ts, 0)

        # Transpose enable flags
        if "keysplit_transpose_enable" in config:
            set_combo_by_data(self.keysplit_transpose_enable, config.get("keysplit_transpose_enable"), 0)
            set_combo_by_data(self.triplesplit_transpose_enable, config.get("triplesplit_transpose_enable"), 0)
        else:
            ks, ts = split_status_to_enables(config.get("key_split_transpose_status", 0))
            set_combo_by_data(self.keysplit_transpose_enable, ks, 0)
            set_combo_by_data(self.triplesplit_transpose_enable, ts, 0)

        # Velocity enable flags
        if "keysplit_velocity_enable" in config:
            set_combo_by_data(self.keysplit_velocity_enable, config.get("keysplit_velocity_enable"), 0)
            set_combo_by_data(self.triplesplit_velocity_enable, config.get("triplesplit_velocity_enable"), 0)
        else:
            ks, ts = split_status_to_enables(config.get("key_split_velocity_status", 0))
            set_combo_by_data(self.keysplit_velocity_enable, ks, 0)
            set_combo_by_data(self.triplesplit_velocity_enable, ts, 0)
        set_combo_by_data(self.custom_layer_animations, config.get("custom_layer_animations_enabled"), False)
        set_combo_by_data(self.unsynced_mode, config.get("unsynced_mode_active"), False)
        set_combo_by_data(self.sample_mode, config.get("sample_mode_active"), False)
        set_combo_by_data(self.instant_loop_start, config.get("instant_loop_start"), False)
        set_combo_by_data(self.colorblind_mode, config.get("colorblindmode"), 0)
        set_combo_by_data(self.cc_loop_recording, config.get("cclooprecording"), 0)
        set_combo_by_data(self.true_sustain, config.get("truesustain"), False)
        # KeySplit/TripleSplit velocity settings (curve only - min/max now per velocity preset)
        # NOTE: key names must match get_midi_config()'s parsed dict — the old
        # lookups ("velocity_curve2", "global_velocity_curve", ...) never
        # existed there, so these combos always showed the fallback instead of
        # the device's real values.
        # Rebuild the zone Articulation combos with the device's user-slot names
        # first (so set_combo_by_data can find AT/CC + user indices), hiding
        # unconfigured user slots + disabled AT/CC bands. Enable flags were
        # already applied above.
        self._refresh_zone_articulation_combos()
        set_combo_by_data(self.velocity_curve2,
                          config.get("keysplit_he_velocity_curve", config.get("velocity_curve2")), 2)
        set_combo_by_data(self.velocity_curve3,
                          config.get("triplesplit_he_velocity_curve", config.get("velocity_curve3")), 2)
        # Global MIDI settings
        set_combo_by_data(self.global_transpose,
                          config.get("transpose_number", config.get("global_transpose")), 0)
        set_combo_by_data(self.global_channel,
                          config.get("channel_number", config.get("global_channel")), 0)
        set_combo_by_data(self.global_velocity_curve,
                          config.get("he_velocity_curve", config.get("global_velocity_curve")), 2)
        # Re-apply band visibility now that each zone combo holds its final index
        # (so a just-selected AT/CC or user index stays visible).
        self._refresh_zone_articulation_visibility()
        # Sustain settings
        set_combo_by_data(self.base_sustain, config.get("base_sustain"), 0)
        set_combo_by_data(self.keysplit_sustain, config.get("keysplit_sustain"), 0)
        set_combo_by_data(self.triplesplit_sustain, config.get("triplesplit_sustain"), 0)
        # MIDI Routing Override settings
        set_combo_by_data(self.channel_override, config.get("channel_override"), False)
        set_combo_by_data(self.velocity_override, config.get("velocity_override"), False)
        set_combo_by_data(self.transpose_override, config.get("transpose_override"), False)
        set_combo_by_data(self.midi_in_mode, config.get("midi_in_mode"), 0)
        set_combo_by_data(self.usb_midi_mode, config.get("usb_midi_mode"), 0)
        set_combo_by_data(self.midi_clock_source, config.get("midi_clock_source"), 0)
        # Macro override live notes
        set_combo_by_data(self.macro_override_live_notes, config.get("macro_override_live_notes"), False)
        # SmartChord settings
        set_combo_by_data(self.smartchord_mode, config.get("smartchord_mode"), 0)
        set_combo_by_data(self.base_smartchord_ignore, config.get("base_smartchord_ignore"), 0)
        set_combo_by_data(self.keysplit_smartchord_ignore, config.get("keysplit_smartchord_ignore"), 0)
        set_combo_by_data(self.triplesplit_smartchord_ignore, config.get("triplesplit_smartchord_ignore"), 0)
        # Chord progression OLED display mode (default 2 = Name)
        set_combo_by_data(self.chord_display_mode, config.get("chord_display_mode"), 2)

    def pack_basic_data(self, settings):
        """Pack basic settings into 22-byte structure

        Layout:
        - Bytes 0-3: velocity_sensitivity (uint32)
        - Bytes 4-7: cc_sensitivity (uint32)
        - Byte 8: global_channel
        - Byte 9: global_transpose
        - Byte 10: octave_number (always 0)
        - Byte 11: transpose_number2
        - Byte 12: octave_number2 (always 0)
        - Byte 13: transpose_number3
        - Byte 14: octave_number3 (always 0)
        - Byte 15: random_velocity_modifier
        - Bytes 16-19: oled_keyboard (uint32)
        - Byte 20: Stop Mode bitmask, sent as 0x80 | mask (bit 7 = "field
                   valid" marker; was the reserved/overdub_advanced_mode
                   byte). When the firmware didn't advertise Stop Mode
                   support we send 0, which the firmware ignores — so the
                   GUI can never silently reset the on-device setting.
        - Byte 21: smart_chord_light_mode
        """
        data = bytearray(22)

        struct.pack_into('<I', data, 0, settings["velocity_sensitivity"])
        struct.pack_into('<I', data, 4, settings["cc_sensitivity"])

        offset = 8
        data[offset] = settings["global_channel"]; offset += 1  # global channel
        data[offset] = settings["global_transpose"] & 0xFF; offset += 1  # global transpose
        data[offset] = 0; offset += 1  # octave_number
        data[offset] = settings["transpose_number2"] & 0xFF; offset += 1
        data[offset] = 0; offset += 1  # octave_number2
        data[offset] = settings["transpose_number3"] & 0xFF; offset += 1
        data[offset] = 0; offset += 1  # octave_number3
        data[offset] = settings["random_velocity_modifier"]; offset += 1

        struct.pack_into('<I', data, offset, settings["oled_keyboard"]); offset += 4

        if self.stop_mode_supported:
            # byte 20: 0x80 validity | Stop Mode mask (bits0-4) | AT/CC enable
            # flags (bit5 = Aftertouch Modes, bit6 = CC Modes).
            _byte20 = 0x80 | (settings.get("stop_mode", 0) & self.STOP_MODE_MASK_ALL)
            if settings.get("enable_at_modes"):
                _byte20 |= 0x20
            if settings.get("enable_cc_modes"):
                _byte20 |= 0x40
            data[offset] = _byte20
        else:
            data[offset] = 0
        offset += 1
        data[offset] = settings["smart_chord_light_mode"]; offset += 1

        return data
    
    def pack_advanced_data(self, settings):
        """Pack advanced settings into 24-byte structure

        Note: loop_messaging_channel, sync_midi_mode, alternate_restart_mode
        are now managed by the ThruLoop tab (0xB0 packet), not the advanced packet.
        """
        data = bytearray(24)

        offset = 0
        data[offset] = settings["key_split_channel"]; offset += 1
        data[offset] = settings["key_split2_channel"]; offset += 1
        data[offset] = settings["key_split_status"]; offset += 1
        data[offset] = settings["key_split_transpose_status"]; offset += 1
        data[offset] = settings["key_split_velocity_status"]; offset += 1
        data[offset] = 1 if settings["custom_layer_animations_enabled"] else 0; offset += 1
        data[offset] = settings["unsynced_mode_active"]; offset += 1
        data[offset] = 1 if settings["sample_mode_active"] else 0; offset += 1
        data[offset] = 1 if settings["instant_loop_start"] else 0; offset += 1
        data[offset] = settings["colorblindmode"]; offset += 1
        data[offset] = settings["cclooprecording"]; offset += 1
        data[offset] = 1 if settings["truesustain"] else 0; offset += 1
        # MIDI Routing Override settings (bytes 12-17)
        data[offset] = 1 if settings.get("channel_override", False) else 0; offset += 1
        data[offset] = 1 if settings.get("velocity_override", False) else 0; offset += 1
        data[offset] = 1 if settings.get("transpose_override", False) else 0; offset += 1
        data[offset] = settings.get("midi_in_mode", 0); offset += 1
        data[offset] = settings.get("usb_midi_mode", 0); offset += 1
        data[offset] = settings.get("midi_clock_source", 0); offset += 1
        # Macro override live notes (byte 18)
        data[offset] = 1 if settings.get("macro_override_live_notes", False) else 0; offset += 1
        # SmartChord settings (bytes 19-22)
        data[offset] = settings.get("smartchord_mode", 0); offset += 1
        data[offset] = settings.get("base_smartchord_ignore", 0); offset += 1
        data[offset] = settings.get("keysplit_smartchord_ignore", 0); offset += 1
        data[offset] = settings.get("triplesplit_smartchord_ignore", 0); offset += 1
        # Chord progression OLED display mode (byte 23): 0=Chords, 1=Numerals, 2=Name
        data[offset] = settings.get("chord_display_mode", 2); offset += 1

        return data
    
    def on_save_slot(self, slot):
        """Save current settings to slot"""
        try:
            if not self.device or not isinstance(self.device, VialKeyboard):
                raise RuntimeError("Device not connected")

            settings = self.get_current_settings()

            # Byte-20 fields (Stop Mode mask + AT/CC enable flags) are ALSO
            # written by the Velocity tab and the on-device settings menu. If
            # our widgets are untouched since the last device load, prefer the
            # device's live values so a stale Save can't silently revert an
            # edit made elsewhere (e.g. enabling CC Modes from the Velocity
            # tab's locked-preset page). The widgets/snapshot are deliberately
            # left alone: still-untouched widgets keep matching the snapshot,
            # so every subsequent Save re-merges the live values too.
            loaded = getattr(self, '_byte20_loaded', None)
            current = (settings.get("stop_mode", 0),
                       bool(settings.get("enable_at_modes")),
                       bool(settings.get("enable_cc_modes")))
            if loaded is not None and current == loaded:
                cfg = self.device.keyboard.get_midi_config()
                if cfg and cfg.get("stop_mode_supported"):
                    settings["stop_mode"] = cfg.get("stop_mode", settings.get("stop_mode", 0))
                    settings["enable_at_modes"] = bool(cfg.get("enable_at_modes"))
                    settings["enable_cc_modes"] = bool(cfg.get("enable_cc_modes"))

            basic_data = self.pack_basic_data(settings)
            print(f"[MIDI Settings] Saving slot {slot}: basic_data={len(basic_data)} bytes: {basic_data.hex()}")
            if not self.device.keyboard.save_midi_slot(slot, basic_data):
                raise RuntimeError(f"Failed to save basic data to slot {slot}")

            print(f"[MIDI Settings] Basic data saved OK, sending advanced data in 50ms...")
            QtCore.QTimer.singleShot(50, lambda: self._send_advanced_data(settings))

        except Exception as e:
            print(f"[MIDI Settings] Save error: {e}")
            QMessageBox.critical(None, "Error", f"Failed to save to slot {slot}: {str(e)}")
    
    def _send_advanced_data(self, settings):
        """Send advanced data (helper for save operations)"""
        try:
            if not self.device or not isinstance(self.device, VialKeyboard):
                return

            advanced_data = self.pack_advanced_data(settings)
            print(f"[MIDI Settings] Sending advanced data: {len(advanced_data)} bytes: {advanced_data.hex()}")
            if not self.device.keyboard.set_midi_advanced_config(advanced_data):
                raise RuntimeError("Failed to send advanced config")
            print(f"[MIDI Settings] Advanced data sent OK")
        except Exception as e:
            print(f"[MIDI Settings] Advanced data error: {e}")
            QMessageBox.critical(None, "Error", f"Failed to send advanced data: {str(e)}")
    
    def on_load_slot(self, slot):
        """Load settings from slot with multi-packet handling"""
        try:
            if not self.device or not isinstance(self.device, VialKeyboard):
                raise RuntimeError("Device not connected")

            print(f"[MIDI Settings] Loading slot {slot}...")
            if not self.device.keyboard.load_midi_slot(slot):
                raise RuntimeError(f"Failed to load from slot {slot}")

            print(f"[MIDI Settings] Slot {slot} load command OK, fetching config in 100ms...")
            # Small delay then get the loaded configuration
            QtCore.QTimer.singleShot(100, lambda: self._load_config_after_slot_load(slot))

        except Exception as e:
            print(f"[MIDI Settings] Load error: {e}")
            QMessageBox.critical(None, "Error", f"Failed to load from slot {slot}: {str(e)}")

    def _load_config_after_slot_load(self, slot):
        """Get and apply configuration after slot load"""
        try:
            config = self.device.keyboard.get_midi_config()

            if not config:
                raise RuntimeError("Failed to get config after slot load")

            print(f"[MIDI Settings] Loaded config from slot {slot}: {config}")
            self.apply_settings(config)
            print(f"[MIDI Settings] Settings applied to UI")

        except Exception as e:
            print(f"[MIDI Settings] Apply config error: {e}")
            QMessageBox.critical(None, "Error", f"Failed to apply loaded config: {str(e)}")
    
    def on_load_current_settings(self):
        """Load current settings from keyboard using multi-packet collection"""
        try:
            if not self.device or not isinstance(self.device, VialKeyboard):
                raise RuntimeError("Device not connected")
            
            config = self.device.keyboard.get_midi_config()
            
            if not config:
                raise RuntimeError("Failed to load current settings")
            
            self.apply_settings(config)
                
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to load current settings: {str(e)}")
    
    def on_reset(self):
        """Reset to default settings"""
        try:
            reply = QMessageBox.question(None, "Confirm Reset", 
                                       "Reset all keyboard settings to defaults? This cannot be undone.",
                                       QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                if not self.device or not isinstance(self.device, VialKeyboard):
                    raise RuntimeError("Device not connected")
                    
                if not self.device.keyboard.reset_midi_config():
                    raise RuntimeError("Failed to reset settings")
                    
                self.reset_ui_to_defaults()
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to reset settings: {str(e)}")
    
    def reset_ui_to_defaults(self):
        """Reset UI to default values"""
        defaults = {
            "velocity_sensitivity": 1,
            "cc_sensitivity": 1,
            "transpose_number2": 0,
            "transpose_number3": 0,
            "random_velocity_modifier": 127,
            "oled_keyboard": 0,
            "stop_mode": 0,  # all Mute (firmware default)
            "enable_at_modes": False,  # AT/CC Mode bands locked by default
            "enable_cc_modes": False,
            "smart_chord_light_mode": 0,
            "key_split_channel": 0,
            "key_split2_channel": 0,
            "key_split_status": 0,
            "key_split_transpose_status": 0,
            "key_split_velocity_status": 0,
            "custom_layer_animations_enabled": False,
            "unsynced_mode_active": 0,
            "sample_mode_active": False,
            "instant_loop_start": False,
            "colorblindmode": 0,
            "cclooprecording": 0,
            "truesustain": False,
            "velocity_curve2": 2,
            "velocity_curve3": 2,
            "global_transpose": 0,
            "global_channel": 0,
            "global_velocity_curve": 2,
            "base_sustain": 0,
            "keysplit_sustain": 0,
            "triplesplit_sustain": 0,
            # MIDI Routing Override settings
            "channel_override": False,
            "velocity_override": False,
            "transpose_override": False,
            "midi_in_mode": 0,
            "usb_midi_mode": 0,
            "midi_clock_source": 0,
            # Macro override live notes
            "macro_override_live_notes": False,
            # SmartChord settings
            "smartchord_mode": 0,
            "base_smartchord_ignore": 0,
            "keysplit_smartchord_ignore": 0,
            "triplesplit_smartchord_ignore": 0,
            # Chord progression OLED display mode (default Name)
            "chord_display_mode": 2
        }
        self.apply_settings(defaults)
    
    def valid(self):
        return isinstance(self.device, VialKeyboard)

    def rebuild(self, device):
        super().rebuild(device)
        if not self.valid():
            return

        # Load MIDI configuration from keyboard
        if hasattr(self.device.keyboard, 'midi_config') and self.device.keyboard.midi_config:
            self.apply_settings(self.device.keyboard.midi_config)

        # Load the global drum keybinds (drum machine voice bindings)
        self.load_drum_keybinds_from_keyboard()

# SPDX-License-Identifier: GPL-2.0-or-later

from PyQt5.QtWidgets import (QVBoxLayout, QPushButton, QWidget, QHBoxLayout, QLabel, 
                           QSizePolicy, QGroupBox, QGridLayout, QSlider, QCheckBox,
                           QMessageBox, QScrollArea, QFrame, QComboBox)
from PyQt5.QtCore import Qt
from PyQt5 import QtCore

from editor.basic_editor import BasicEditor
from util import tr
from vial_device import VialKeyboard

class LayerActuationConfigurator(BasicEditor):
    
    def __init__(self):
        super().__init__()
        
        # Master widgets
        self.master_widgets = {}
        
        # Single layer widgets
        self.layer_widgets = {}
        
        # Current layer being viewed
        self.current_layer = 0
        
        # All layer data stored in memory
        self.layer_data = []
        for _ in range(12):
            self.layer_data.append({
                'normal': 127,
                'midi': 127,
                'aftertouch': 0,
                'velocity': 3,  # Speed+Peak (only supported mode)
                'rapid': 4,
                'midi_rapid_sens': 10,
                'midi_rapid_vel': 10,
                'vel_speed': 10,
                'aftertouch_cc': 255,  # 255 = off (no CC sent)
                'vibrato_sensitivity': 50,   # 50% (mid-range)
                'vibrato_decay_time': 10,    # 10ms decay
                'rapidfire_enabled': False,
                'midi_rapidfire_enabled': False,
                # HE Velocity defaults
                'use_fixed_velocity': False,
                'he_curve': 2,  # Medium (linear)
                'he_min': 1,
                'he_max': 127
            })
        
        # Flag to prevent recursion
        self.updating_from_master = False
        
        # Per-layer mode
        self.per_layer_enabled = False
        
        # Advanced options shown
        self.advanced_shown = False
        
        self.setup_ui()
        
    def setup_ui(self):
        self.addStretch()
        
        # Create scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setMinimumSize(900, 600)
        
        main_widget = QWidget()
        main_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_widget.setLayout(main_layout)
        
        scroll.setWidget(main_widget)
        self.addWidget(scroll)
        self.setAlignment(scroll, QtCore.Qt.AlignHCenter)
        
        # Info label
        info_label = QLabel(tr("LayerActuationConfigurator", 
            "Configure actuation distances and settings per layer"))
        info_label.setStyleSheet("QLabel { color: #666; font-style: italic; font-size: 10px; margin: 5px; }")
        main_layout.addWidget(info_label, alignment=QtCore.Qt.AlignCenter)
        
        # Create master controls group
        self.master_group = self.create_master_group()
        main_layout.addWidget(self.master_group)
        
        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line)
        
        # Layer selector container (hidden by default)
        self.layer_selector_container = QWidget()
        layer_selector_layout = QVBoxLayout()
        layer_selector_layout.setSpacing(10)
        self.layer_selector_container.setLayout(layer_selector_layout)
        
        # Layer dropdown
        selector_row = QHBoxLayout()
        selector_row.addStretch()
        selector_label = QLabel(tr("LayerActuationConfigurator", "Select Layer:"))
        selector_label.setStyleSheet("QLabel { font-weight: bold; font-size: 11px; }")
        selector_row.addWidget(selector_label)
        
        self.layer_dropdown = ArrowComboBox()
        self.layer_dropdown.setMinimumWidth(150)
        self.layer_dropdown.setStyleSheet("QComboBox { padding: 0px; text-align: center; }")
        for i in range(12):
            self.layer_dropdown.addItem(f"Layer {i + 1}", i)
        self.layer_dropdown.setEditable(True)
        self.layer_dropdown.lineEdit().setReadOnly(True)
        self.layer_dropdown.lineEdit().setAlignment(Qt.AlignCenter)
        self.layer_dropdown.currentIndexChanged.connect(self.on_layer_changed)
        selector_row.addWidget(self.layer_dropdown)
        selector_row.addStretch()
        
        layer_selector_layout.addLayout(selector_row)
        
        # Single layer group
        self.layer_group = self.create_layer_group()
        layer_selector_layout.addWidget(self.layer_group, alignment=QtCore.Qt.AlignCenter)
        
        self.layer_selector_container.setVisible(False)
        main_layout.addWidget(self.layer_selector_container)
        
        main_layout.addStretch()
        
        # Buttons
        self.addStretch()
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        # Button style - bigger and less rounded
        button_style = "QPushButton { border-radius: 3px; padding: 8px 16px; }"

        save_btn = QPushButton(tr("LayerActuationConfigurator", "Save to Keyboard"))
        save_btn.setMinimumHeight(45)
        save_btn.setMinimumWidth(180)
        save_btn.setStyleSheet(button_style)
        save_btn.clicked.connect(self.on_save)
        buttons_layout.addWidget(save_btn)

        load_btn = QPushButton(tr("LayerActuationConfigurator", "Load from Keyboard"))
        load_btn.setMinimumHeight(45)
        load_btn.setMinimumWidth(210)
        load_btn.setStyleSheet(button_style)
        load_btn.clicked.connect(self.on_load_from_keyboard)
        buttons_layout.addWidget(load_btn)

        reset_btn = QPushButton(tr("LayerActuationConfigurator", "Reset All to Defaults"))
        reset_btn.setMinimumHeight(45)
        reset_btn.setMinimumWidth(210)
        reset_btn.setStyleSheet(button_style)
        reset_btn.clicked.connect(self.on_reset)
        buttons_layout.addWidget(reset_btn)

        self.addLayout(buttons_layout)
    
    def create_master_group(self):
        """Create the master control group with all settings"""
        group = QGroupBox(tr("LayerActuationConfigurator", "Master Settings (All Layers)"))
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(15, 20, 15, 15)
        group.setLayout(layout)
        
        # Top row with both checkboxes
        checkboxes_layout = QHBoxLayout()
        
        # Master per-layer checkbox
        self.per_layer_checkbox = QCheckBox(tr("LayerActuationConfigurator", "Enable Per-Layer Settings"))
        self.per_layer_checkbox.setStyleSheet("QCheckBox { font-weight: bold; font-size: 11px; }")
        self.per_layer_checkbox.stateChanged.connect(self.on_per_layer_toggled)
        checkboxes_layout.addWidget(self.per_layer_checkbox)
        
        checkboxes_layout.addSpacing(20)
        
        # Show Advanced Options checkbox
        self.advanced_checkbox = QCheckBox(tr("LayerActuationConfigurator", "Show Advanced Actuation Options"))
        self.advanced_checkbox.setStyleSheet("QCheckBox { font-size: 11px; }")
        self.advanced_checkbox.stateChanged.connect(self.on_advanced_toggled)
        checkboxes_layout.addWidget(self.advanced_checkbox)
        
        checkboxes_layout.addStretch()
        layout.addLayout(checkboxes_layout)
        
        # Add separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)
        
        # Normal Keys Actuation (slider) - ALWAYS VISIBLE
        slider_layout = QHBoxLayout()
        label = QLabel(tr("LayerActuationConfigurator", "Normal Keys Actuation:"))
        label.setMinimumWidth(200)
        slider_layout.addWidget(label)
        
        normal_slider = QSlider(Qt.Horizontal)
        normal_slider.setMinimum(0)
        normal_slider.setMaximum(255)
        normal_slider.setValue(127)
        slider_layout.addWidget(normal_slider)
        
        normal_value_label = QLabel("2.00mm (80)")
        normal_value_label.setMinimumWidth(100)
        normal_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        slider_layout.addWidget(normal_value_label)
        
        layout.addLayout(slider_layout)
        normal_slider.valueChanged.connect(
            lambda v, lbl=normal_value_label: self.on_master_slider_changed('normal', v, lbl)
        )
        
        # Enable Rapidfire checkbox - ALWAYS VISIBLE
        rapid_checkbox = QCheckBox(tr("LayerActuationConfigurator", "Enable RapidTrigger"))
        rapid_checkbox.setChecked(False)
        layout.addWidget(rapid_checkbox)
        rapid_checkbox.stateChanged.connect(self.on_rapidfire_toggled)
        
        # Rapidfire Sensitivity (slider) - hidden by default
        rapid_slider_layout = QHBoxLayout()
        rapid_label = QLabel(tr("LayerActuationConfigurator", "RapidTrigger Sensitivity:"))
        rapid_label.setMinimumWidth(200)
        rapid_slider_layout.addWidget(rapid_label)
        
        rapid_slider = QSlider(Qt.Horizontal)
        rapid_slider.setMinimum(1)
        rapid_slider.setMaximum(100)
        rapid_slider.setValue(4)
        rapid_slider_layout.addWidget(rapid_slider)
        
        rapid_value_label = QLabel("4")
        rapid_value_label.setMinimumWidth(100)
        rapid_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        rapid_slider_layout.addWidget(rapid_value_label)
        
        rapid_slider_widget = QWidget()
        rapid_slider_widget.setLayout(rapid_slider_layout)
        rapid_slider_widget.setVisible(False)
        layout.addWidget(rapid_slider_widget)
        
        rapid_slider.valueChanged.connect(
            lambda v, lbl=rapid_value_label: self.on_master_slider_changed('rapid', v, lbl)
        )

        # === AFTERTOUCH CONTROLS (always visible) ===
        # Aftertouch Mode dropdown
        aftertouch_layout = QHBoxLayout()
        aftertouch_label = QLabel(tr("LayerActuationConfigurator", "Aftertouch Mode:"))
        aftertouch_label.setMinimumWidth(200)
        aftertouch_layout.addWidget(aftertouch_label)

        aftertouch_combo = ArrowComboBox()
        aftertouch_combo.setStyleSheet("QComboBox { padding: 0px; text-align: center; }")
        aftertouch_combo.addItem("Off", 0)
        aftertouch_combo.addItem("Bottom-Out", 1)
        aftertouch_combo.addItem("Bottom-Out (NS)", 2)
        aftertouch_combo.addItem("Reverse", 3)
        aftertouch_combo.addItem("Reverse (NS)", 4)
        aftertouch_combo.addItem("Post-Actuation", 5)
        aftertouch_combo.addItem("Post-Actuation (NS)", 6)
        aftertouch_combo.addItem("Vibrato", 7)
        aftertouch_combo.addItem("Vibrato (NS)", 8)
        aftertouch_combo.setCurrentIndex(0)
        aftertouch_combo.setEditable(True)
        aftertouch_combo.lineEdit().setReadOnly(True)
        aftertouch_combo.lineEdit().setAlignment(Qt.AlignCenter)
        aftertouch_layout.addWidget(aftertouch_combo)
        aftertouch_layout.addStretch()
        layout.addLayout(aftertouch_layout)
        aftertouch_combo.currentIndexChanged.connect(
            lambda: self.on_master_combo_changed('aftertouch', aftertouch_combo)
        )

        # Aftertouch CC dropdown
        aftertouch_cc_layout = QHBoxLayout()
        aftertouch_cc_label = QLabel(tr("LayerActuationConfigurator", "Aftertouch CC:"))
        aftertouch_cc_label.setMinimumWidth(200)
        aftertouch_cc_layout.addWidget(aftertouch_cc_label)

        aftertouch_cc_combo = ArrowComboBox()
        aftertouch_cc_combo.setStyleSheet("QComboBox { padding: 0px; text-align: center; }")
        aftertouch_cc_combo.addItem("Off", 255)
        for cc in range(128):
            aftertouch_cc_combo.addItem(f"CC#{cc}", cc)
        aftertouch_cc_combo.setCurrentIndex(0)
        aftertouch_cc_combo.setEditable(True)
        aftertouch_cc_combo.lineEdit().setReadOnly(True)
        aftertouch_cc_combo.lineEdit().setAlignment(Qt.AlignCenter)
        aftertouch_cc_layout.addWidget(aftertouch_cc_combo)
        aftertouch_cc_layout.addStretch()
        layout.addLayout(aftertouch_cc_layout)
        aftertouch_cc_combo.currentIndexChanged.connect(
            lambda: self.on_master_combo_changed('aftertouch_cc', aftertouch_cc_combo)
        )

        # Vibrato Sensitivity slider (hidden by default, shown when Vibrato mode)
        vibrato_sens_widget = QWidget()
        vibrato_sens_layout = QHBoxLayout()
        vibrato_sens_layout.setContentsMargins(0, 0, 0, 0)
        vibrato_sens_widget.setLayout(vibrato_sens_layout)

        vibrato_sens_label = QLabel(tr("LayerActuationConfigurator", "Vibrato Sensitivity:"))
        vibrato_sens_label.setMinimumWidth(200)
        vibrato_sens_layout.addWidget(vibrato_sens_label)

        vibrato_sens_slider = QSlider(Qt.Horizontal)
        vibrato_sens_slider.setMinimum(0)
        vibrato_sens_slider.setMaximum(100)
        vibrato_sens_slider.setValue(50)
        vibrato_sens_layout.addWidget(vibrato_sens_slider)

        vibrato_sens_value_label = QLabel("50%")
        vibrato_sens_value_label.setMinimumWidth(60)
        vibrato_sens_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        vibrato_sens_layout.addWidget(vibrato_sens_value_label)

        layout.addWidget(vibrato_sens_widget)
        vibrato_sens_widget.setVisible(False)
        vibrato_sens_slider.valueChanged.connect(
            lambda v, lbl=vibrato_sens_value_label: self.on_master_slider_changed('vibrato_sensitivity', v, lbl)
        )

        # Vibrato Decay Time slider (hidden by default, shown when Vibrato mode)
        vibrato_decay_widget = QWidget()
        vibrato_decay_layout = QHBoxLayout()
        vibrato_decay_layout.setContentsMargins(0, 0, 0, 0)
        vibrato_decay_widget.setLayout(vibrato_decay_layout)

        vibrato_decay_label = QLabel(tr("LayerActuationConfigurator", "Vibrato Decay Time:"))
        vibrato_decay_label.setMinimumWidth(200)
        vibrato_decay_layout.addWidget(vibrato_decay_label)

        vibrato_decay_slider = QSlider(Qt.Horizontal)
        vibrato_decay_slider.setMinimum(0)
        vibrato_decay_slider.setMaximum(50)
        vibrato_decay_slider.setValue(10)
        vibrato_decay_layout.addWidget(vibrato_decay_slider)

        vibrato_decay_value_label = QLabel("10ms")
        vibrato_decay_value_label.setMinimumWidth(60)
        vibrato_decay_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        vibrato_decay_layout.addWidget(vibrato_decay_value_label)

        layout.addWidget(vibrato_decay_widget)
        vibrato_decay_widget.setVisible(False)
        vibrato_decay_slider.valueChanged.connect(
            lambda v, lbl=vibrato_decay_value_label: self.on_master_slider_changed('vibrato_decay_time', v, lbl)
        )

        # Connect aftertouch mode to show/hide vibrato controls
        aftertouch_combo.currentIndexChanged.connect(
            lambda idx: self.on_aftertouch_mode_changed(aftertouch_combo, vibrato_sens_widget, vibrato_decay_widget)
        )

        # === ADVANCED OPTIONS (hidden by default) ===
        self.advanced_widget = QWidget()
        advanced_layout_main = QVBoxLayout()
        advanced_layout_main.setSpacing(8)
        advanced_layout_main.setContentsMargins(0, 10, 0, 0)
        self.advanced_widget.setLayout(advanced_layout_main)
        self.advanced_widget.setVisible(False)

        # Add separator
        adv_line = QFrame()
        adv_line.setFrameShape(QFrame.HLine)
        adv_line.setFrameShadow(QFrame.Sunken)
        advanced_layout_main.addWidget(adv_line)

        # Title for MIDI settings section
        midi_settings_title = QLabel(tr("LayerActuationConfigurator", "Basic MIDI Settings"))
        midi_settings_title.setStyleSheet("QLabel { font-weight: bold; font-size: 11px; margin: 5px 0px; }")
        advanced_layout_main.addWidget(midi_settings_title)

        # Container for MIDI settings and split offshoots (side by side)
        content_container = QHBoxLayout()
        advanced_layout = QVBoxLayout()

        # Split Mode control
        split_mode_layout = QHBoxLayout()
        split_mode_label = QLabel(tr("LayerActuationConfigurator", "Split Mode:"))
        split_mode_label.setMinimumWidth(200)
        split_mode_layout.addWidget(split_mode_label)

        self.actuation_split_mode = ArrowComboBox()
        self.actuation_split_mode.setStyleSheet("QComboBox { padding: 0px; text-align: center; }")
        self.actuation_split_mode.addItem("Disable Keysplit", 0)
        self.actuation_split_mode.addItem("KeySplit On", 1)
        self.actuation_split_mode.addItem("TripleSplit On", 2)
        self.actuation_split_mode.addItem("Both Splits On", 3)
        self.actuation_split_mode.setCurrentIndex(0)
        self.actuation_split_mode.setEditable(True)
        self.actuation_split_mode.lineEdit().setReadOnly(True)
        self.actuation_split_mode.lineEdit().setAlignment(Qt.AlignCenter)
        self.actuation_split_mode.currentIndexChanged.connect(self.on_actuation_split_mode_changed)
        split_mode_layout.addWidget(self.actuation_split_mode)
        split_mode_layout.addStretch()

        advanced_layout.addLayout(split_mode_layout)

        # MIDI Keys Actuation (slider)
        midi_slider_layout = QHBoxLayout()
        midi_label = QLabel(tr("LayerActuationConfigurator", "MIDI Keys Actuation:"))
        midi_label.setMinimumWidth(200)
        midi_slider_layout.addWidget(midi_label)
        
        midi_slider = QSlider(Qt.Horizontal)
        midi_slider.setMinimum(0)
        midi_slider.setMaximum(255)
        midi_slider.setValue(127)
        midi_slider_layout.addWidget(midi_slider)
        
        midi_value_label = QLabel("2.00mm (80)")
        midi_value_label.setMinimumWidth(100)
        midi_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        midi_slider_layout.addWidget(midi_value_label)
        
        advanced_layout.addLayout(midi_slider_layout)
        midi_slider.valueChanged.connect(
            lambda v, lbl=midi_value_label: self.on_master_slider_changed('midi', v, lbl)
        )

        # Note: Aftertouch controls moved outside advanced section (always visible)

        # Velocity Mode (dropdown)
        combo_layout = QHBoxLayout()
        label = QLabel(tr("LayerActuationConfigurator", "Velocity Mode:"))
        label.setMinimumWidth(200)
        combo_layout.addWidget(label)
        
        velocity_combo = ArrowComboBox()
        velocity_combo.setStyleSheet("QComboBox { padding: 0px; text-align: center; }")
        velocity_combo.addItem("Speed + Peak", 3)
        velocity_combo.setCurrentIndex(0)
        velocity_combo.setEditable(True)
        velocity_combo.lineEdit().setReadOnly(True)
        velocity_combo.lineEdit().setAlignment(Qt.AlignCenter)
        velocity_combo.setEnabled(False)  # Fixed at Speed+Peak, not user-configurable
        combo_layout.addWidget(velocity_combo)
        combo_layout.addStretch()

        advanced_layout.addLayout(combo_layout)
        
        # Velocity Speed Scale (deprecated - fixed at 10, kept for protocol compat)
        combo_layout = QHBoxLayout()
        label = QLabel(tr("LayerActuationConfigurator", "Velocity Speed Scale:"))
        label.setMinimumWidth(200)
        combo_layout.addWidget(label)

        vel_speed_combo = ArrowComboBox()
        vel_speed_combo.setStyleSheet("QComboBox { padding: 0px; text-align: center; }")
        for i in range(1, 21):
            vel_speed_combo.addItem(str(i), i)
        vel_speed_combo.setCurrentIndex(9)
        vel_speed_combo.setEditable(True)
        vel_speed_combo.lineEdit().setReadOnly(True)
        vel_speed_combo.lineEdit().setAlignment(Qt.AlignCenter)
        vel_speed_combo.setEnabled(False)  # Deprecated: speed scale handled by speed_peak_ratio
        vel_speed_combo.setToolTip("Deprecated: handled automatically by the Articulation tab")
        combo_layout.addWidget(vel_speed_combo)
        combo_layout.addStretch()

        advanced_layout.addLayout(combo_layout)
        
        # Enable MIDI Rapidfire checkbox
        midi_rapid_checkbox = QCheckBox(tr("LayerActuationConfigurator", "Enable MIDI RapidTrigger"))
        midi_rapid_checkbox.setChecked(False)
        advanced_layout.addWidget(midi_rapid_checkbox)
        midi_rapid_checkbox.stateChanged.connect(self.on_midi_rapidfire_toggled)
        
        # MIDI Rapidfire Sensitivity (slider) - hidden by default
        midi_rapid_sens_layout = QHBoxLayout()
        midi_rapid_sens_label = QLabel(tr("LayerActuationConfigurator", "MIDI RapidTrigger Sensitivity:"))
        midi_rapid_sens_label.setMinimumWidth(200)
        midi_rapid_sens_layout.addWidget(midi_rapid_sens_label)
        
        midi_rapid_sens_slider = QSlider(Qt.Horizontal)
        midi_rapid_sens_slider.setMinimum(1)
        midi_rapid_sens_slider.setMaximum(100)
        midi_rapid_sens_slider.setValue(10)
        midi_rapid_sens_layout.addWidget(midi_rapid_sens_slider)
        
        midi_rapid_sens_value_label = QLabel("10")
        midi_rapid_sens_value_label.setMinimumWidth(100)
        midi_rapid_sens_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        midi_rapid_sens_layout.addWidget(midi_rapid_sens_value_label)
        
        midi_rapid_sens_widget = QWidget()
        midi_rapid_sens_widget.setLayout(midi_rapid_sens_layout)
        midi_rapid_sens_widget.setVisible(False)
        advanced_layout.addWidget(midi_rapid_sens_widget)
        
        midi_rapid_sens_slider.valueChanged.connect(
            lambda v, lbl=midi_rapid_sens_value_label: self.on_master_slider_changed('midi_rapid_sens', v, lbl)
        )
        
        # MIDI Rapidfire Velocity Range (slider) - hidden by default
        midi_rapid_vel_layout = QHBoxLayout()
        midi_rapid_vel_label = QLabel(tr("LayerActuationConfigurator", "MIDI RapidTrigger Velocity Range:"))
        midi_rapid_vel_label.setMinimumWidth(200)
        midi_rapid_vel_layout.addWidget(midi_rapid_vel_label)
        
        midi_rapid_vel_slider = QSlider(Qt.Horizontal)
        midi_rapid_vel_slider.setMinimum(0)
        midi_rapid_vel_slider.setMaximum(20)
        midi_rapid_vel_slider.setValue(10)
        midi_rapid_vel_layout.addWidget(midi_rapid_vel_slider)
        
        midi_rapid_vel_value_label = QLabel("±10")
        midi_rapid_vel_value_label.setMinimumWidth(100)
        midi_rapid_vel_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        midi_rapid_vel_layout.addWidget(midi_rapid_vel_value_label)
        
        midi_rapid_vel_widget = QWidget()
        midi_rapid_vel_widget.setLayout(midi_rapid_vel_layout)
        midi_rapid_vel_widget.setVisible(False)
        advanced_layout.addWidget(midi_rapid_vel_widget)
        
        midi_rapid_vel_slider.valueChanged.connect(
            lambda v, lbl=midi_rapid_vel_value_label: self.on_master_slider_changed('midi_rapid_vel', v, lbl)
        )

        # === HE VELOCITY CONTROLS ===
        # Add separator
        he_line = QFrame()
        he_line.setFrameShape(QFrame.HLine)
        he_line.setFrameShadow(QFrame.Sunken)
        advanced_layout.addWidget(he_line)

        # Use Fixed Velocity checkbox
        use_fixed_vel_checkbox = QCheckBox(tr("LayerActuationConfigurator", "Use Fixed Velocity"))
        use_fixed_vel_checkbox.setChecked(False)
        use_fixed_vel_checkbox.setStyleSheet("QCheckBox { font-size: 10px; }")
        advanced_layout.addWidget(use_fixed_vel_checkbox)
        use_fixed_vel_checkbox.stateChanged.connect(self.on_use_fixed_velocity_toggled)

        # HE Velocity Curve (dropdown)
        curve_layout = QHBoxLayout()
        curve_label = QLabel(tr("LayerActuationConfigurator", "Articulation:"))
        curve_label.setMinimumWidth(200)
        curve_layout.addWidget(curve_label)

        he_curve_combo = ArrowComboBox()
        he_curve_combo.setMinimumHeight(30)
        he_curve_combo.setStyleSheet("QComboBox { padding: 0px; text-align: center; font-size: 12px; } QComboBox QAbstractItemView { min-height: 125px; }")
        populate_articulation_combo(he_curve_combo)
        he_curve_combo.setCurrentIndex(0)  # Default: Linear
        he_curve_combo.setEditable(True)
        he_curve_combo.lineEdit().setReadOnly(True)
        he_curve_combo.lineEdit().setAlignment(Qt.AlignCenter)
        curve_layout.addWidget(he_curve_combo)
        curve_layout.addStretch()

        advanced_layout.addLayout(curve_layout)
        he_curve_combo.currentIndexChanged.connect(
            lambda: self.on_master_combo_changed('he_curve', he_curve_combo)
        )

        # HE Velocity Min (slider)
        he_min_layout = QHBoxLayout()
        he_min_label = QLabel(tr("LayerActuationConfigurator", "HE Velocity Min:"))
        he_min_label.setMinimumWidth(200)
        he_min_layout.addWidget(he_min_label)

        he_min_slider = QSlider(Qt.Horizontal)
        he_min_slider.setMinimum(1)
        he_min_slider.setMaximum(127)
        he_min_slider.setValue(1)
        he_min_layout.addWidget(he_min_slider)

        he_min_value_label = QLabel("1")
        he_min_value_label.setMinimumWidth(100)
        he_min_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        he_min_layout.addWidget(he_min_value_label)

        advanced_layout.addLayout(he_min_layout)
        he_min_slider.valueChanged.connect(
            lambda v, lbl=he_min_value_label: self.on_master_slider_changed('he_min', v, lbl)
        )

        # HE Velocity Max (slider)
        he_max_layout = QHBoxLayout()
        he_max_label = QLabel(tr("LayerActuationConfigurator", "HE Velocity Max:"))
        he_max_label.setMinimumWidth(200)
        he_max_layout.addWidget(he_max_label)

        he_max_slider = QSlider(Qt.Horizontal)
        he_max_slider.setMinimum(1)
        he_max_slider.setMaximum(127)
        he_max_slider.setValue(127)
        he_max_layout.addWidget(he_max_slider)

        he_max_value_label = QLabel("127")
        he_max_value_label.setMinimumWidth(100)
        he_max_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        he_max_layout.addWidget(he_max_value_label)

        advanced_layout.addLayout(he_max_layout)
        he_max_slider.valueChanged.connect(
            lambda v, lbl=he_max_value_label: self.on_master_slider_changed('he_max', v, lbl)
        )

        # Add the MIDI settings layout to the content container
        content_container.addLayout(advanced_layout, 1)

        # Create KeySplit offshoot window
        self.keysplit_actuation_offshoot = QGroupBox(tr("LayerActuationConfigurator", "KeySplit Settings"))
        self.keysplit_actuation_offshoot.setMaximumWidth(300)
        keysplit_layout = QGridLayout()
        keysplit_layout.setVerticalSpacing(10)
        keysplit_layout.setHorizontalSpacing(10)
        self.keysplit_actuation_offshoot.setLayout(keysplit_layout)

        ks_row = 0
        keysplit_layout.addWidget(QLabel(tr("LayerActuationConfigurator", "Sustain:")), ks_row, 0)
        self.keysplit_actuation_sustain = ArrowComboBox()
        self.keysplit_actuation_sustain.setMinimumWidth(80)
        self.keysplit_actuation_sustain.setMaximumWidth(120)
        self.keysplit_actuation_sustain.setMinimumHeight(25)
        self.keysplit_actuation_sustain.setMaximumHeight(25)
        self.keysplit_actuation_sustain.addItem("Ignore", 0)
        self.keysplit_actuation_sustain.addItem("Allow", 1)
        self.keysplit_actuation_sustain.setCurrentIndex(0)
        self.keysplit_actuation_sustain.setEditable(True)
        self.keysplit_actuation_sustain.lineEdit().setReadOnly(True)
        self.keysplit_actuation_sustain.lineEdit().setAlignment(Qt.AlignCenter)
        keysplit_layout.addWidget(self.keysplit_actuation_sustain, ks_row, 1)

        self.keysplit_actuation_offshoot.hide()

        # TripleSplit offshoot window
        self.triplesplit_actuation_offshoot = QGroupBox(tr("LayerActuationConfigurator", "TripleSplit Settings"))
        self.triplesplit_actuation_offshoot.setMaximumWidth(300)
        triplesplit_layout = QGridLayout()
        triplesplit_layout.setVerticalSpacing(10)
        triplesplit_layout.setHorizontalSpacing(10)
        self.triplesplit_actuation_offshoot.setLayout(triplesplit_layout)

        ts_row = 0
        triplesplit_layout.addWidget(QLabel(tr("LayerActuationConfigurator", "Sustain:")), ts_row, 0)
        self.triplesplit_actuation_sustain = ArrowComboBox()
        self.triplesplit_actuation_sustain.setMinimumWidth(80)
        self.triplesplit_actuation_sustain.setMaximumWidth(120)
        self.triplesplit_actuation_sustain.setMinimumHeight(25)
        self.triplesplit_actuation_sustain.setMaximumHeight(25)
        self.triplesplit_actuation_sustain.addItem("Ignore", 0)
        self.triplesplit_actuation_sustain.addItem("Allow", 1)
        self.triplesplit_actuation_sustain.setCurrentIndex(0)
        self.triplesplit_actuation_sustain.setEditable(True)
        self.triplesplit_actuation_sustain.lineEdit().setReadOnly(True)
        self.triplesplit_actuation_sustain.lineEdit().setAlignment(Qt.AlignCenter)
        triplesplit_layout.addWidget(self.triplesplit_actuation_sustain, ts_row, 1)

        self.triplesplit_actuation_offshoot.hide()

        # Add offshoots to content container (side by side)
        content_container.addWidget(self.keysplit_actuation_offshoot)
        content_container.addWidget(self.triplesplit_actuation_offshoot)

        # Add content container to main advanced layout
        advanced_layout_main.addLayout(content_container)

        layout.addWidget(self.advanced_widget)
        
        # Store widgets
        self.master_widgets = {
            'normal_slider': normal_slider,
            'normal_label': normal_value_label,
            'midi_slider': midi_slider,
            'midi_label': midi_value_label,
            'aftertouch_combo': aftertouch_combo,
            'aftertouch_cc_combo': aftertouch_cc_combo,
            'vibrato_sensitivity_slider': vibrato_sens_slider,
            'vibrato_sensitivity_label': vibrato_sens_value_label,
            'vibrato_sensitivity_widget': vibrato_sens_widget,
            'vibrato_decay_time_slider': vibrato_decay_slider,
            'vibrato_decay_time_label': vibrato_decay_value_label,
            'vibrato_decay_time_widget': vibrato_decay_widget,
            'velocity_combo': velocity_combo,
            'vel_speed_combo': vel_speed_combo,
            'rapid_checkbox': rapid_checkbox,
            'rapid_slider': rapid_slider,
            'rapid_label': rapid_value_label,
            'rapid_widget': rapid_slider_widget,
            'midi_rapid_checkbox': midi_rapid_checkbox,
            'midi_rapid_sens_slider': midi_rapid_sens_slider,
            'midi_rapid_sens_label': midi_rapid_sens_value_label,
            'midi_rapid_sens_widget': midi_rapid_sens_widget,
            'midi_rapid_vel_slider': midi_rapid_vel_slider,
            'midi_rapid_vel_label': midi_rapid_vel_value_label,
            'midi_rapid_vel_widget': midi_rapid_vel_widget,
            # HE Velocity controls
            'use_fixed_vel_checkbox': use_fixed_vel_checkbox,
            'he_curve_combo': he_curve_combo,
            'he_min_slider': he_min_slider,
            'he_min_label': he_min_value_label,
            'he_max_slider': he_max_slider,
            'he_max_label': he_max_value_label
        }
        
        return group
    
    def create_layer_group(self):
        """Create a group for the currently selected layer's settings"""
        group = QGroupBox(tr("LayerActuationConfigurator", f"Layer {self.current_layer + 1} Settings"))
        group.setMaximumWidth(500)
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11px; }")
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(15, 20, 15, 15)
        group.setLayout(layout)
        
        # Show Advanced Options checkbox
        layer_advanced_checkbox = QCheckBox(tr("LayerActuationConfigurator", "Show Advanced Actuation Options"))
        layer_advanced_checkbox.setStyleSheet("QCheckBox { font-size: 11px; margin-bottom: 5px; }")
        layer_advanced_checkbox.stateChanged.connect(self.on_layer_advanced_toggled)
        layout.addWidget(layer_advanced_checkbox)
        
        # Add separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)
        
        # Normal actuation slider - ALWAYS VISIBLE
        normal_slider_layout = QHBoxLayout()
        normal_label = QLabel(tr("LayerActuationConfigurator", "Normal Keys Actuation:"))
        normal_label.setMinimumWidth(180)
        normal_slider_layout.addWidget(normal_label)
        
        normal_slider = QSlider(Qt.Horizontal)
        normal_slider.setMinimum(0)
        normal_slider.setMaximum(255)
        normal_slider.setValue(127)
        normal_slider_layout.addWidget(normal_slider)
        
        normal_value_label = QLabel("2.00mm (80)")
        normal_value_label.setMinimumWidth(100)
        normal_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        normal_slider_layout.addWidget(normal_value_label)
        
        layout.addLayout(normal_slider_layout)
        normal_slider.valueChanged.connect(
            lambda v, lbl=normal_value_label: self.on_layer_slider_changed('normal', v, lbl)
        )
        self.layer_widgets['normal_slider'] = normal_slider
        self.layer_widgets['normal_label'] = normal_value_label
        
        # Enable Rapidfire checkbox - ALWAYS VISIBLE
        rapid_checkbox = QCheckBox(tr("LayerActuationConfigurator", "Enable RapidTrigger"))
        rapid_checkbox.setStyleSheet("QCheckBox { font-size: 10px; }")
        layout.addWidget(rapid_checkbox)
        self.layer_widgets['rapid_checkbox'] = rapid_checkbox
        
        # Rapidfire Sensitivity slider - hidden by default
        rapid_sens_slider_layout = QHBoxLayout()
        rapid_sens_label = QLabel(tr("LayerActuationConfigurator", "RapidTrigger Sensitivity:"))
        rapid_sens_label.setMinimumWidth(180)
        rapid_sens_slider_layout.addWidget(rapid_sens_label)
        
        rapid_sens_slider = QSlider(Qt.Horizontal)
        rapid_sens_slider.setMinimum(1)
        rapid_sens_slider.setMaximum(100)
        rapid_sens_slider.setValue(4)
        rapid_sens_slider_layout.addWidget(rapid_sens_slider)
        
        rapid_sens_value_label = QLabel("4")
        rapid_sens_value_label.setMinimumWidth(100)
        rapid_sens_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        rapid_sens_slider_layout.addWidget(rapid_sens_value_label)
        
        rapid_widget = QWidget()
        rapid_widget.setLayout(rapid_sens_slider_layout)
        rapid_widget.setVisible(False)
        layout.addWidget(rapid_widget)
        
        rapid_sens_slider.valueChanged.connect(
            lambda v, lbl=rapid_sens_value_label: self.on_layer_slider_changed('rapid', v, lbl)
        )
        self.layer_widgets['rapid_slider'] = rapid_sens_slider
        self.layer_widgets['rapid_label'] = rapid_sens_value_label
        self.layer_widgets['rapid_widget'] = rapid_widget
        
        rapid_checkbox.stateChanged.connect(
            lambda state: rapid_widget.setVisible(state == Qt.Checked)
        )
        
        # === ADVANCED OPTIONS (hidden by default) ===
        layer_advanced_widget = QWidget()
        layer_advanced_layout = QVBoxLayout()
        layer_advanced_layout.setSpacing(8)
        layer_advanced_layout.setContentsMargins(0, 10, 0, 0)
        layer_advanced_widget.setLayout(layer_advanced_layout)
        layer_advanced_widget.setVisible(False)
        
        # Add separator
        adv_line = QFrame()
        adv_line.setFrameShape(QFrame.HLine)
        adv_line.setFrameShadow(QFrame.Sunken)
        layer_advanced_layout.addWidget(adv_line)
        
        # MIDI actuation slider
        midi_slider_layout = QHBoxLayout()
        midi_label = QLabel(tr("LayerActuationConfigurator", "MIDI Keys Actuation:"))
        midi_label.setMinimumWidth(180)
        midi_slider_layout.addWidget(midi_label)
        
        midi_slider = QSlider(Qt.Horizontal)
        midi_slider.setMinimum(0)
        midi_slider.setMaximum(255)
        midi_slider.setValue(127)
        midi_slider_layout.addWidget(midi_slider)
        
        midi_value_label = QLabel("2.00mm (80)")
        midi_value_label.setMinimumWidth(100)
        midi_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        midi_slider_layout.addWidget(midi_value_label)
        
        layer_advanced_layout.addLayout(midi_slider_layout)
        midi_slider.valueChanged.connect(
            lambda v, lbl=midi_value_label: self.on_layer_slider_changed('midi', v, lbl)
        )
        self.layer_widgets['midi_slider'] = midi_slider
        self.layer_widgets['midi_label'] = midi_value_label
        
        # Aftertouch Mode combo
        combo_layout = QHBoxLayout()
        label = QLabel(tr("LayerActuationConfigurator", "Aftertouch Mode:"))
        label.setMinimumWidth(180)
        combo_layout.addWidget(label)
        
        combo = ArrowComboBox()
        combo.setStyleSheet("QComboBox { padding: 0px; text-align: center; }")
        combo.addItem("Off", 0)
        combo.addItem("Bottom-Out", 1)
        combo.addItem("Reverse", 2)
        combo.addItem("Post-Actuation", 3)
        combo.addItem("Bottom-Out (NS)", 4)
        combo.addItem("Reverse (NS)", 5)
        combo.addItem("Vibrato", 6)
        combo.setEditable(True)
        combo.lineEdit().setReadOnly(True)
        combo.lineEdit().setAlignment(Qt.AlignCenter)
        combo_layout.addWidget(combo)
        combo_layout.addStretch()

        layer_advanced_layout.addLayout(combo_layout)
        combo.currentIndexChanged.connect(
            lambda: self.on_layer_combo_changed('aftertouch', combo)
        )
        self.layer_widgets['aftertouch_combo'] = combo
        
        # Aftertouch CC combo
        combo_layout = QHBoxLayout()
        label = QLabel(tr("LayerActuationConfigurator", "Aftertouch CC:"))
        label.setMinimumWidth(180)
        combo_layout.addWidget(label)
        
        combo = ArrowComboBox()
        combo.setStyleSheet("QComboBox { padding: 0px; text-align: center; }")
        combo.addItem("Off", 255)  # 255 = no CC sent, only poly aftertouch
        for cc in range(128):
            combo.addItem(f"CC#{cc}", cc)
        combo.setCurrentIndex(0)  # Default: Off
        combo.setEditable(True)
        combo.lineEdit().setReadOnly(True)
        combo.lineEdit().setAlignment(Qt.AlignCenter)
        combo_layout.addWidget(combo)
        combo_layout.addStretch()

        layer_advanced_layout.addLayout(combo_layout)
        combo.currentIndexChanged.connect(
            lambda: self.on_layer_combo_changed('aftertouch_cc', combo)
        )
        self.layer_widgets['aftertouch_cc_combo'] = combo
        
        # Velocity Mode combo
        combo_layout = QHBoxLayout()
        label = QLabel(tr("LayerActuationConfigurator", "Velocity Mode:"))
        label.setMinimumWidth(180)
        combo_layout.addWidget(label)
        
        combo = ArrowComboBox()
        combo.setStyleSheet("QComboBox { padding: 0px; text-align: center; }")
        combo.addItem("Speed + Peak", 3)
        combo.setCurrentIndex(0)
        combo.setEditable(True)
        combo.lineEdit().setReadOnly(True)
        combo.lineEdit().setAlignment(Qt.AlignCenter)
        combo.setEnabled(False)  # Fixed at Speed+Peak, not user-configurable
        combo_layout.addWidget(combo)
        combo_layout.addStretch()

        layer_advanced_layout.addLayout(combo_layout)
        self.layer_widgets['velocity_combo'] = combo
        
        # Velocity Speed Scale combo (deprecated - fixed at 10, kept for protocol compat)
        combo_layout = QHBoxLayout()
        label = QLabel(tr("LayerActuationConfigurator", "Velocity Speed Scale:"))
        label.setMinimumWidth(180)
        combo_layout.addWidget(label)

        combo = ArrowComboBox()
        combo.setStyleSheet("QComboBox { padding: 0px; text-align: center; }")
        for i in range(1, 21):
            combo.addItem(str(i), i)
        combo.setCurrentIndex(9)
        combo.setEditable(True)
        combo.lineEdit().setReadOnly(True)
        combo.lineEdit().setAlignment(Qt.AlignCenter)
        combo.setEnabled(False)  # Deprecated: speed scale handled by speed_peak_ratio
        combo.setToolTip("Deprecated: use Speed/Peak Ratio in Velocity tab instead")
        combo_layout.addWidget(combo)
        combo_layout.addStretch()

        layer_advanced_layout.addLayout(combo_layout)
        self.layer_widgets['vel_speed_combo'] = combo
        
        # Enable MIDI Rapidfire checkbox
        midi_rapid_checkbox = QCheckBox(tr("LayerActuationConfigurator", "Enable MIDI RapidTrigger"))
        midi_rapid_checkbox.setStyleSheet("QCheckBox { font-size: 10px; }")
        layer_advanced_layout.addWidget(midi_rapid_checkbox)
        self.layer_widgets['midi_rapid_checkbox'] = midi_rapid_checkbox
        
        # MIDI Rapidfire Sensitivity slider - hidden by default
        midi_rapid_sens_slider_layout = QHBoxLayout()
        midi_rapid_sens_label = QLabel(tr("LayerActuationConfigurator", "MIDI RapidTrigger Sensitivity:"))
        midi_rapid_sens_label.setMinimumWidth(180)
        midi_rapid_sens_slider_layout.addWidget(midi_rapid_sens_label)
        
        midi_rapid_sens_slider = QSlider(Qt.Horizontal)
        midi_rapid_sens_slider.setMinimum(1)
        midi_rapid_sens_slider.setMaximum(100)
        midi_rapid_sens_slider.setValue(10)
        midi_rapid_sens_slider_layout.addWidget(midi_rapid_sens_slider)
        
        midi_rapid_sens_value_label = QLabel("10")
        midi_rapid_sens_value_label.setMinimumWidth(100)
        midi_rapid_sens_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        midi_rapid_sens_slider_layout.addWidget(midi_rapid_sens_value_label)
        
        midi_rapid_sens_widget = QWidget()
        midi_rapid_sens_widget.setLayout(midi_rapid_sens_slider_layout)
        midi_rapid_sens_widget.setVisible(False)
        layer_advanced_layout.addWidget(midi_rapid_sens_widget)
        
        midi_rapid_sens_slider.valueChanged.connect(
            lambda v, lbl=midi_rapid_sens_value_label: self.on_layer_slider_changed('midi_rapid_sens', v, lbl)
        )
        self.layer_widgets['midi_rapid_sens_slider'] = midi_rapid_sens_slider
        self.layer_widgets['midi_rapid_sens_label'] = midi_rapid_sens_value_label
        self.layer_widgets['midi_rapid_sens_widget'] = midi_rapid_sens_widget
        
        # MIDI Rapidfire Velocity Range slider - hidden by default
        midi_rapid_vel_slider_layout = QHBoxLayout()
        midi_rapid_vel_label = QLabel(tr("LayerActuationConfigurator", "MIDI RapidTrigger Velocity Range:"))
        midi_rapid_vel_label.setMinimumWidth(180)
        midi_rapid_vel_slider_layout.addWidget(midi_rapid_vel_label)
        
        midi_rapid_vel_slider = QSlider(Qt.Horizontal)
        midi_rapid_vel_slider.setMinimum(0)
        midi_rapid_vel_slider.setMaximum(20)
        midi_rapid_vel_slider.setValue(10)
        midi_rapid_vel_slider_layout.addWidget(midi_rapid_vel_slider)
        
        midi_rapid_vel_value_label = QLabel("±10")
        midi_rapid_vel_value_label.setMinimumWidth(100)
        midi_rapid_vel_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        midi_rapid_vel_slider_layout.addWidget(midi_rapid_vel_value_label)
        
        midi_rapid_vel_widget = QWidget()
        midi_rapid_vel_widget.setLayout(midi_rapid_vel_slider_layout)
        midi_rapid_vel_widget.setVisible(False)
        layer_advanced_layout.addWidget(midi_rapid_vel_widget)
        
        midi_rapid_vel_slider.valueChanged.connect(
            lambda v, lbl=midi_rapid_vel_value_label: self.on_layer_slider_changed('midi_rapid_vel', v, lbl)
        )
        self.layer_widgets['midi_rapid_vel_slider'] = midi_rapid_vel_slider
        self.layer_widgets['midi_rapid_vel_label'] = midi_rapid_vel_value_label
        self.layer_widgets['midi_rapid_vel_widget'] = midi_rapid_vel_widget
        
        # Connect checkbox to show/hide both MIDI rapidfire widgets
        def toggle_midi_rapid_widgets(state):
            enabled = (state == Qt.Checked)
            midi_rapid_sens_widget.setVisible(enabled)
            midi_rapid_vel_widget.setVisible(enabled)
        
        midi_rapid_checkbox.stateChanged.connect(toggle_midi_rapid_widgets)

        # === HE VELOCITY CONTROLS (PER-LAYER) ===
        # Add separator
        he_line = QFrame()
        he_line.setFrameShape(QFrame.HLine)
        he_line.setFrameShadow(QFrame.Sunken)
        layer_advanced_layout.addWidget(he_line)

        # Use Fixed Velocity checkbox
        use_fixed_vel_checkbox = QCheckBox(tr("LayerActuationConfigurator", "Use Fixed Velocity"))
        use_fixed_vel_checkbox.setChecked(False)
        use_fixed_vel_checkbox.setStyleSheet("QCheckBox { font-size: 10px; }")
        layer_advanced_layout.addWidget(use_fixed_vel_checkbox)
        self.layer_widgets['use_fixed_vel_checkbox'] = use_fixed_vel_checkbox

        # HE Velocity Curve (dropdown)
        curve_layout = QHBoxLayout()
        curve_label = QLabel(tr("LayerActuationConfigurator", "Articulation:"))
        curve_label.setMinimumWidth(180)
        curve_layout.addWidget(curve_label)

        he_curve_combo = ArrowComboBox()
        he_curve_combo.setMinimumHeight(30)
        he_curve_combo.setStyleSheet("QComboBox { padding: 0px; text-align: center; font-size: 12px; } QComboBox QAbstractItemView { min-height: 125px; }")
        populate_articulation_combo(he_curve_combo)
        he_curve_combo.setCurrentIndex(0)  # Default: Linear
        he_curve_combo.setEditable(True)
        he_curve_combo.lineEdit().setReadOnly(True)
        he_curve_combo.lineEdit().setAlignment(Qt.AlignCenter)
        curve_layout.addWidget(he_curve_combo)
        curve_layout.addStretch()

        layer_advanced_layout.addLayout(curve_layout)
        he_curve_combo.currentIndexChanged.connect(
            lambda: self.on_layer_combo_changed('he_curve', he_curve_combo)
        )
        self.layer_widgets['he_curve_combo'] = he_curve_combo

        # HE Velocity Min (slider)
        he_min_layout = QHBoxLayout()
        he_min_label = QLabel(tr("LayerActuationConfigurator", "HE Velocity Min:"))
        he_min_label.setMinimumWidth(180)
        he_min_layout.addWidget(he_min_label)

        he_min_slider = QSlider(Qt.Horizontal)
        he_min_slider.setMinimum(1)
        he_min_slider.setMaximum(127)
        he_min_slider.setValue(1)
        he_min_layout.addWidget(he_min_slider)

        he_min_value_label = QLabel("1")
        he_min_value_label.setMinimumWidth(100)
        he_min_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        he_min_layout.addWidget(he_min_value_label)

        layer_advanced_layout.addLayout(he_min_layout)
        he_min_slider.valueChanged.connect(
            lambda v, lbl=he_min_value_label: self.on_layer_slider_changed('he_min', v, lbl)
        )
        self.layer_widgets['he_min_slider'] = he_min_slider
        self.layer_widgets['he_min_label'] = he_min_value_label

        # HE Velocity Max (slider)
        he_max_layout = QHBoxLayout()
        he_max_label = QLabel(tr("LayerActuationConfigurator", "HE Velocity Max:"))
        he_max_label.setMinimumWidth(180)
        he_max_layout.addWidget(he_max_label)

        he_max_slider = QSlider(Qt.Horizontal)
        he_max_slider.setMinimum(1)
        he_max_slider.setMaximum(127)
        he_max_slider.setValue(127)
        he_max_layout.addWidget(he_max_slider)

        he_max_value_label = QLabel("127")
        he_max_value_label.setMinimumWidth(100)
        he_max_value_label.setStyleSheet("QLabel { font-weight: bold; }")
        he_max_layout.addWidget(he_max_value_label)

        layer_advanced_layout.addLayout(he_max_layout)
        he_max_slider.valueChanged.connect(
            lambda v, lbl=he_max_value_label: self.on_layer_slider_changed('he_max', v, lbl)
        )
        self.layer_widgets['he_max_slider'] = he_max_slider
        self.layer_widgets['he_max_label'] = he_max_value_label

        layout.addWidget(layer_advanced_widget)
        self.layer_widgets['advanced_widget'] = layer_advanced_widget
        self.layer_widgets['advanced_checkbox'] = layer_advanced_checkbox
        self.layer_widgets['group'] = group
        
        return group
    
    def on_advanced_toggled(self):
        """Show/hide advanced options in master controls"""
        self.advanced_shown = self.advanced_checkbox.isChecked()
        self.advanced_widget.setVisible(self.advanced_shown)

    def on_actuation_split_mode_changed(self):
        """Show/hide split offshoots based on split mode"""
        if not hasattr(self, 'actuation_split_mode'):
            return

        split_status = self.actuation_split_mode.currentData()

        # Show/hide offshoot windows based on split mode
        if split_status == 0:  # No splits
            self.keysplit_actuation_offshoot.hide()
            self.triplesplit_actuation_offshoot.hide()
        elif split_status == 1:  # KeySplit only
            self.keysplit_actuation_offshoot.show()
            self.triplesplit_actuation_offshoot.hide()
        elif split_status == 2:  # TripleSplit only
            self.keysplit_actuation_offshoot.hide()
            self.triplesplit_actuation_offshoot.show()
        elif split_status == 3:  # Both splits
            self.keysplit_actuation_offshoot.show()
            self.triplesplit_actuation_offshoot.show()

    def on_layer_advanced_toggled(self):
        """Show/hide advanced options in layer controls"""
        shown = self.layer_widgets['advanced_checkbox'].isChecked()
        self.layer_widgets['advanced_widget'].setVisible(shown)
    
    def on_per_layer_toggled(self):
        """Handle master per-layer checkbox toggle"""
        self.per_layer_enabled = self.per_layer_checkbox.isChecked()
        self.layer_selector_container.setVisible(self.per_layer_enabled)
        
        # Enable/disable master controls based on per-layer mode
        self.master_group.setEnabled(not self.per_layer_enabled)
        
        if not self.per_layer_enabled:
            self.sync_all_to_master()
        else:
            # Load current layer data into UI
            self.load_layer_to_ui(self.current_layer)
    
    def on_layer_changed(self, index):
        """Handle layer dropdown change"""
        # Save current layer data from UI
        self.save_ui_to_layer(self.current_layer)
        
        # Update current layer
        self.current_layer = index
        
        # Update group title
        self.layer_widgets['group'].setTitle(tr("LayerActuationConfigurator", f"Layer {self.current_layer + 1} Settings"))
        
        # Load new layer data to UI
        self.load_layer_to_ui(self.current_layer)
    
    def save_ui_to_layer(self, layer):
        """Save current UI values to layer data"""
        self.layer_data[layer]['normal'] = self.layer_widgets['normal_slider'].value()
        self.layer_data[layer]['midi'] = self.layer_widgets['midi_slider'].value()
        self.layer_data[layer]['aftertouch'] = self.layer_widgets['aftertouch_combo'].currentData()
        self.layer_data[layer]['velocity'] = self.layer_widgets['velocity_combo'].currentData()
        self.layer_data[layer]['rapid'] = self.layer_widgets['rapid_slider'].value()
        self.layer_data[layer]['midi_rapid_sens'] = self.layer_widgets['midi_rapid_sens_slider'].value()
        self.layer_data[layer]['midi_rapid_vel'] = self.layer_widgets['midi_rapid_vel_slider'].value()
        self.layer_data[layer]['vel_speed'] = self.layer_widgets['vel_speed_combo'].currentData()
        self.layer_data[layer]['aftertouch_cc'] = self.layer_widgets['aftertouch_cc_combo'].currentData()
        self.layer_data[layer]['rapidfire_enabled'] = self.layer_widgets['rapid_checkbox'].isChecked()
        self.layer_data[layer]['midi_rapidfire_enabled'] = self.layer_widgets['midi_rapid_checkbox'].isChecked()
        # HE Velocity fields
        self.layer_data[layer]['use_fixed_velocity'] = self.layer_widgets['use_fixed_vel_checkbox'].isChecked()
        self.layer_data[layer]['he_curve'] = self.layer_widgets['he_curve_combo'].currentData()
        self.layer_data[layer]['he_min'] = self.layer_widgets['he_min_slider'].value()
        self.layer_data[layer]['he_max'] = self.layer_widgets['he_max_slider'].value()
    
    def load_layer_to_ui(self, layer):
        """Load layer data to UI"""
        data = self.layer_data[layer]

        # Set sliders
        self.layer_widgets['normal_slider'].setValue(data['normal'])
        self.layer_widgets['midi_slider'].setValue(data['midi'])

        # Set combos
        for key in ['aftertouch', 'aftertouch_cc', 'velocity', 'vel_speed', 'he_curve']:
            combo = self.layer_widgets[f'{key}_combo']
            for i in range(combo.count()):
                if combo.itemData(i) == data[key]:
                    combo.setCurrentIndex(i)
                    break

        # Set rapidfire
        self.layer_widgets['rapid_checkbox'].setChecked(data['rapidfire_enabled'])
        self.layer_widgets['rapid_widget'].setVisible(data['rapidfire_enabled'])
        self.layer_widgets['rapid_slider'].setValue(data['rapid'])

        # Set MIDI rapidfire
        self.layer_widgets['midi_rapid_checkbox'].setChecked(data['midi_rapidfire_enabled'])
        self.layer_widgets['midi_rapid_sens_widget'].setVisible(data['midi_rapidfire_enabled'])
        self.layer_widgets['midi_rapid_vel_widget'].setVisible(data['midi_rapidfire_enabled'])
        self.layer_widgets['midi_rapid_sens_slider'].setValue(data['midi_rapid_sens'])
        self.layer_widgets['midi_rapid_vel_slider'].setValue(data['midi_rapid_vel'])

        # Set HE Velocity settings
        self.layer_widgets['use_fixed_vel_checkbox'].setChecked(data['use_fixed_velocity'])
        self.layer_widgets['he_min_slider'].setValue(data['he_min'])
        self.layer_widgets['he_max_slider'].setValue(data['he_max'])
    
    def on_rapidfire_toggled(self):
        """Show/hide rapidfire sensitivity based on checkbox"""
        enabled = self.master_widgets['rapid_checkbox'].isChecked()
        self.master_widgets['rapid_widget'].setVisible(enabled)
        
        if not self.per_layer_enabled:
            for layer_data in self.layer_data:
                layer_data['rapidfire_enabled'] = enabled
    
    def on_midi_rapidfire_toggled(self):
        """Show/hide MIDI rapidfire widgets based on checkbox"""
        enabled = self.master_widgets['midi_rapid_checkbox'].isChecked()
        self.master_widgets['midi_rapid_sens_widget'].setVisible(enabled)
        self.master_widgets['midi_rapid_vel_widget'].setVisible(enabled)

        if not self.per_layer_enabled:
            for layer_data in self.layer_data:
                layer_data['midi_rapidfire_enabled'] = enabled

    def on_use_fixed_velocity_toggled(self):
        """Handle Use Fixed Velocity checkbox toggle"""
        enabled = self.master_widgets['use_fixed_vel_checkbox'].isChecked()

        if not self.per_layer_enabled:
            for layer_data in self.layer_data:
                layer_data['use_fixed_velocity'] = enabled

    def on_aftertouch_mode_changed(self, combo, vibrato_sens_widget, vibrato_decay_widget):
        """Handle aftertouch mode changes - show/hide vibrato controls"""
        mode = combo.currentData()
        is_vibrato = (mode in (7, 8))
        vibrato_sens_widget.setVisible(is_vibrato)
        vibrato_decay_widget.setVisible(is_vibrato)

    def on_master_slider_changed(self, key, value, label):
        """Handle master slider changes"""
        if key in ['normal', 'midi']:
            label.setText(f"{value * 4.0 / 255.0:.2f}mm ({value})")
        elif key == 'midi_rapid_vel':
            label.setText(f"±{value}")
        elif key == 'vibrato_sensitivity':
            label.setText(f"{value}%")
        elif key == 'vibrato_decay_time':
            label.setText(f"{value}ms")
        else:
            label.setText(str(value))
        
        # If changing normal actuation and advanced is NOT shown, also update MIDI
        if key == 'normal' and not self.advanced_shown:
            self.master_widgets['midi_slider'].setValue(value)
            self.master_widgets['midi_label'].setText(f"{value * 4.0 / 255.0:.2f}mm ({value})")
        
        if not self.per_layer_enabled:
            for layer_data in self.layer_data:
                layer_data[key] = value
                # Also sync MIDI when changing normal without advanced shown
                if key == 'normal' and not self.advanced_shown:
                    layer_data['midi'] = value
    
    def on_master_combo_changed(self, key, combo):
        """Handle master combo changes"""
        if not self.per_layer_enabled:
            value = combo.currentData()
            for layer_data in self.layer_data:
                layer_data[key] = value
    
    def on_layer_slider_changed(self, key, value, label):
        """Handle layer slider changes"""
        if key in ['normal', 'midi']:
            label.setText(f"{value * 4.0 / 255.0:.2f}mm ({value})")
        elif key == 'midi_rapid_vel':
            label.setText(f"±{value}")
        else:
            label.setText(str(value))
        
        # If changing normal actuation and advanced is NOT shown, also update MIDI
        if key == 'normal' and not self.layer_widgets['advanced_checkbox'].isChecked():
            self.layer_widgets['midi_slider'].setValue(value)
            self.layer_widgets['midi_label'].setText(f"{value * 4.0 / 255.0:.2f}mm ({value})")
            self.layer_data[self.current_layer]['midi'] = value
        
        # Update layer data
        self.layer_data[self.current_layer][key] = value
    
    def on_layer_combo_changed(self, key, combo):
        """Handle layer combo changes"""
        self.layer_data[self.current_layer][key] = combo.currentData()
    
    def sync_all_to_master(self):
        """Sync all layer settings to master values"""
        master_data = {
            'normal': self.master_widgets['normal_slider'].value(),
            'midi': self.master_widgets['midi_slider'].value(),
            'aftertouch': self.master_widgets['aftertouch_combo'].currentData(),
            'velocity': self.master_widgets['velocity_combo'].currentData(),
            'rapid': self.master_widgets['rapid_slider'].value(),
            'midi_rapid_sens': self.master_widgets['midi_rapid_sens_slider'].value(),
            'midi_rapid_vel': self.master_widgets['midi_rapid_vel_slider'].value(),
            'vel_speed': self.master_widgets['vel_speed_combo'].currentData(),
            'aftertouch_cc': self.master_widgets['aftertouch_cc_combo'].currentData(),
            'vibrato_sensitivity': self.master_widgets['vibrato_sensitivity_slider'].value(),
            'vibrato_decay_time': self.master_widgets['vibrato_decay_time_slider'].value(),
            'rapidfire_enabled': self.master_widgets['rapid_checkbox'].isChecked(),
            'midi_rapidfire_enabled': self.master_widgets['midi_rapid_checkbox'].isChecked(),
            # HE Velocity settings
            'use_fixed_velocity': self.master_widgets['use_fixed_vel_checkbox'].isChecked(),
            'he_curve': self.master_widgets['he_curve_combo'].currentData(),
            'he_min': self.master_widgets['he_min_slider'].value(),
            'he_max': self.master_widgets['he_max_slider'].value()
        }

        for i in range(12):
            self.layer_data[i] = master_data.copy()
    
    def get_all_actuations(self):
        """Get all actuation values as a list of dicts"""
        actuations = []
        for layer_data in self.layer_data:
            # Build flags byte
            flags = 0
            if layer_data['rapidfire_enabled']:
                flags |= 0x01
            if layer_data['midi_rapidfire_enabled']:
                flags |= 0x02
            if layer_data['use_fixed_velocity']:
                flags |= 0x04

            data_dict = {
                'normal': layer_data['normal'],
                'midi': layer_data['midi'],
                'aftertouch': layer_data.get('aftertouch', 0),
                'velocity': layer_data['velocity'],
                'rapid': layer_data['rapid'],
                'midi_rapid_sens': layer_data['midi_rapid_sens'],
                'midi_rapid_vel': layer_data['midi_rapid_vel'],
                'vel_speed': layer_data['vel_speed'],
                'aftertouch_cc': layer_data.get('aftertouch_cc', 255),
                'vibrato_sensitivity': layer_data.get('vibrato_sensitivity', 50),
                'vibrato_decay_time': layer_data.get('vibrato_decay_time', 10),
                'flags': flags,
                # HE Velocity settings
                'he_curve': layer_data['he_curve'],
                'he_min': layer_data['he_min'],
                'he_max': layer_data['he_max']
            }
            actuations.append(data_dict)
        return actuations
    
    def on_save(self):
        """Save all actuation settings to keyboard"""
        try:
            # Save current layer UI to data before saving
            if self.per_layer_enabled:
                self.save_ui_to_layer(self.current_layer)

            if not self.device or not isinstance(self.device, VialKeyboard):
                raise RuntimeError("Device not connected")

            actuations = self.get_all_actuations()

            # Send all 12 layers (11 bytes each)
            # Protocol: [layer, normal, midi, velocity_mode, vel_speed, flags,
            #            aftertouch_mode, aftertouch_cc, vibrato_sensitivity,
            #            vibrato_decay_time_low, vibrato_decay_time_high]
            for layer, values in enumerate(actuations):
                vibrato_decay = values['vibrato_decay_time']
                data = bytearray([
                    layer,
                    values['normal'],
                    values['midi'],
                    values['velocity'],
                    values['vel_speed'],
                    values['flags'],
                    values['aftertouch'],
                    values['aftertouch_cc'],
                    values['vibrato_sensitivity'],
                    vibrato_decay & 0xFF,           # Low byte
                    (vibrato_decay >> 8) & 0xFF     # High byte
                ])

                if not self.device.keyboard.set_layer_actuation(data):
                    raise RuntimeError(f"Failed to set actuation for layer {layer}")

            QMessageBox.information(None, "Success",
                "Layer actuations saved successfully!")

        except Exception as e:
            QMessageBox.critical(None, "Error",
                f"Failed to save actuations: {str(e)}")
    
    def on_load_from_keyboard(self):
        """Load all actuation settings from keyboard"""
        try:
            if not self.device or not isinstance(self.device, VialKeyboard):
                raise RuntimeError("Device not connected")

            # Get all actuations (120 bytes = 12 layers × 10 bytes)
            # [normal, midi, velocity_mode, vel_speed, flags,
            #  aftertouch_mode, aftertouch_cc, vibrato_sensitivity,
            #  vibrato_decay_time_low, vibrato_decay_time_high]
            actuations = self.device.keyboard.get_all_layer_actuations()

            if not actuations or len(actuations) < 120:
                raise RuntimeError("Failed to load actuations from keyboard")

            # Check if all layers are the same
            all_same = True
            first_values = {}

            # New protocol: 10 bytes per layer
            keys = ['normal', 'midi', 'velocity', 'vel_speed', 'flags',
                    'aftertouch', 'aftertouch_cc', 'vibrato_sensitivity',
                    'vibrato_decay_low', 'vibrato_decay_high']

            for key_idx, key in enumerate(keys):
                first_values[key] = actuations[key_idx]

                for layer in range(1, 12):
                    offset = layer * 10 + key_idx
                    if actuations[offset] != first_values[key]:
                        all_same = False
                        break
                if not all_same:
                    break

            # Compute vibrato_decay_time from low/high bytes
            first_values['vibrato_decay_time'] = first_values['vibrato_decay_low'] | (first_values['vibrato_decay_high'] << 8)

            # Load into layer data
            for layer in range(12):
                offset = layer * 10
                flags = actuations[offset + 4]
                vibrato_decay = actuations[offset + 8] | (actuations[offset + 9] << 8)

                self.layer_data[layer] = {
                    'normal': actuations[offset + 0],
                    'midi': actuations[offset + 1],
                    'velocity': actuations[offset + 2],
                    'vel_speed': actuations[offset + 3],
                    'aftertouch': actuations[offset + 5],
                    'aftertouch_cc': actuations[offset + 6],
                    'vibrato_sensitivity': actuations[offset + 7],
                    'vibrato_decay_time': vibrato_decay,
                    'rapidfire_enabled': (flags & 0x01) != 0,
                    'midi_rapidfire_enabled': (flags & 0x02) != 0,
                    'use_fixed_velocity': (flags & 0x04) != 0,
                    # Defaults for fields not in new protocol (per-key now)
                    'rapid': 4,
                    'midi_rapid_sens': 4,
                    'midi_rapid_vel': 0,
                    'he_curve': 2,
                    'he_min': 1,
                    'he_max': 127
                }

            # Set master controls
            self.master_widgets['normal_slider'].setValue(first_values['normal'])
            self.master_widgets['midi_slider'].setValue(first_values['midi'])

            for key in ['aftertouch', 'aftertouch_cc', 'velocity', 'vel_speed']:
                combo = self.master_widgets[f'{key}_combo']
                for i in range(combo.count()):
                    if combo.itemData(i) == first_values[key]:
                        combo.setCurrentIndex(i)
                        break

            # Vibrato sensitivity and decay
            self.master_widgets['vibrato_sensitivity_slider'].setValue(first_values['vibrato_sensitivity'])
            self.master_widgets['vibrato_decay_time_slider'].setValue(first_values['vibrato_decay_time'])

            # Show/hide vibrato controls based on mode
            is_vibrato = (first_values['aftertouch'] in (7, 8))
            self.master_widgets['vibrato_sensitivity_widget'].setVisible(is_vibrato)
            self.master_widgets['vibrato_decay_time_widget'].setVisible(is_vibrato)

            # Rapidfire (flags-based)
            first_flags = first_values['flags']
            rapid_enabled = (first_flags & 0x01) != 0
            self.master_widgets['rapid_checkbox'].setChecked(rapid_enabled)
            self.master_widgets['rapid_widget'].setVisible(rapid_enabled)

            # MIDI Rapidfire
            midi_rapid_enabled = (first_flags & 0x02) != 0
            self.master_widgets['midi_rapid_checkbox'].setChecked(midi_rapid_enabled)
            self.master_widgets['midi_rapid_sens_widget'].setVisible(midi_rapid_enabled)
            self.master_widgets['midi_rapid_vel_widget'].setVisible(midi_rapid_enabled)

            # HE Velocity settings (use defaults since not in layer protocol anymore)
            use_fixed_vel = (first_flags & 0x04) != 0
            self.master_widgets['use_fixed_vel_checkbox'].setChecked(use_fixed_vel)

            # Load current layer to UI if in per-layer mode
            if self.per_layer_enabled:
                self.load_layer_to_ui(self.current_layer)

            self.per_layer_checkbox.setChecked(not all_same)

            QMessageBox.information(None, "Success",
                "Layer actuations loaded successfully!")

        except Exception as e:
            QMessageBox.critical(None, "Error",
                f"Failed to load actuations: {str(e)}")
    
    def on_reset(self):
        """Reset all actuations to defaults"""
        try:
            reply = QMessageBox.question(None, "Confirm Reset", 
                "Reset all layer actuations to defaults? This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No)
            
            if reply == QMessageBox.Yes:
                if not self.device or not isinstance(self.device, VialKeyboard):
                    raise RuntimeError("Device not connected")
                
                if not self.device.keyboard.reset_layer_actuations():
                    raise RuntimeError("Failed to reset actuations")
                
                # Update UI to defaults
                defaults = {
                    'normal': 127,
                    'midi': 127,
                    'aftertouch': 0,
                    'velocity': 3,  # Speed+Peak (only supported mode)
                    'rapid': 4,
                    'midi_rapid_sens': 10,
                    'midi_rapid_vel': 10,
                    'vel_speed': 10,
                    'aftertouch_cc': 255,  # 255 = off (no CC sent)
                    'vibrato_sensitivity': 50,   # 50% (mid-range)
                    'vibrato_decay_time': 10,    # 10ms decay
                    'rapidfire_enabled': False,
                    'midi_rapidfire_enabled': False,
                    'use_fixed_velocity': False,
                    'he_curve': 2,
                    'he_min': 1,
                    'he_max': 127
                }

                # Reset master
                self.master_widgets['normal_slider'].setValue(defaults['normal'])
                self.master_widgets['midi_slider'].setValue(defaults['midi'])

                for key in ['aftertouch', 'aftertouch_cc', 'velocity', 'vel_speed']:
                    combo = self.master_widgets[f'{key}_combo']
                    for i in range(combo.count()):
                        if combo.itemData(i) == defaults[key]:
                            combo.setCurrentIndex(i)
                            break

                # Vibrato controls
                self.master_widgets['vibrato_sensitivity_slider'].setValue(defaults['vibrato_sensitivity'])
                self.master_widgets['vibrato_decay_time_slider'].setValue(defaults['vibrato_decay_time'])
                self.master_widgets['vibrato_sensitivity_widget'].setVisible(False)
                self.master_widgets['vibrato_decay_time_widget'].setVisible(False)

                self.master_widgets['rapid_checkbox'].setChecked(False)
                self.master_widgets['rapid_widget'].setVisible(False)
                self.master_widgets['rapid_slider'].setValue(defaults['rapid'])

                self.master_widgets['midi_rapid_checkbox'].setChecked(False)
                self.master_widgets['midi_rapid_sens_widget'].setVisible(False)
                self.master_widgets['midi_rapid_vel_widget'].setVisible(False)
                self.master_widgets['midi_rapid_sens_slider'].setValue(defaults['midi_rapid_sens'])
                self.master_widgets['midi_rapid_vel_slider'].setValue(defaults['midi_rapid_vel'])

                # Reset all layer data
                for i in range(12):
                    self.layer_data[i] = defaults.copy()
                
                # Reload current layer to UI if in per-layer mode
                if self.per_layer_enabled:
                    self.load_layer_to_ui(self.current_layer)
                
                self.per_layer_checkbox.setChecked(False)
                
                QMessageBox.information(None, "Success", 
                    "Layer actuations reset to defaults!")
                    
        except Exception as e:
            QMessageBox.critical(None, "Error", 
                f"Failed to reset actuations: {str(e)}")
    
    def valid(self):
        return isinstance(self.device, VialKeyboard)

    def rebuild(self, device):
        super().rebuild(device)
        if not self.valid():
            return

        # Load actuation settings from keyboard
        self.on_load_from_keyboard_silent()
        # Bring the per-key / per-layer Articulation pickers in line with the
        # device: real user-slot names, unconfigured user slots hidden, AT/CC
        # bands shown only when enabled.
        self._refresh_articulation_pickers()

    def _refresh_articulation_pickers(self):
        """Rebuild the master (per-key) + per-layer Articulation pickers with the
        device's user-slot names and hide unconfigured user slots / disabled
        AT/CC bands. These combos are setters (not stored state), so hiding a row
        never affects a stored per-key value."""
        combos = []
        try:
            combos.append(self.master_widgets['he_curve_combo'])
        except Exception:
            pass
        try:
            combos.append(self.layer_widgets['he_curve_combo'])
        except Exception:
            pass
        if not combos:
            return
        user_names, user_configured = None, None
        cc_enabled, at_enabled = True, True
        try:
            if self.device and isinstance(self.device, VialKeyboard):
                res = self.device.keyboard.get_all_user_curve_names()
                if res:
                    user_names, user_configured = res
                config = self.device.keyboard.get_midi_config() or {}
                cc_enabled = bool(config.get('enable_cc_modes', False))
                at_enabled = bool(config.get('enable_at_modes', False))
        except Exception:
            pass
        for combo in combos:
            keep = combo.currentData()
            populate_articulation_combo(combo, user_names=user_names)
            blocked = combo.blockSignals(True)
            try:
                if keep is not None:
                    for i in range(combo.count()):
                        if combo.itemData(i) == keep:
                            combo.setCurrentIndex(i)
                            break
            finally:
                combo.blockSignals(blocked)
            apply_articulation_visibility(combo, user_configured=user_configured,
                                          cc_enabled=cc_enabled, at_enabled=at_enabled,
                                          keep_index=keep)

    def on_load_from_keyboard_silent(self):
        """Load settings without showing success message"""
        if not self.device or not isinstance(self.device, VialKeyboard):
            return
        
        actuations = self.device.keyboard.get_all_layer_actuations()
        
        if not actuations or len(actuations) != 120:
            return
        
        # Parse and apply (same logic as on_load_from_keyboard but silent)
        all_same = True
        first_values = {}
        
        for key_idx, key in enumerate(['normal', 'midi', 'aftertouch', 'velocity', 'rapid',
                                      'midi_rapid_sens', 'midi_rapid_vel', 'vel_speed',
                                      'aftertouch_cc', 'flags']):
            first_values[key] = actuations[key_idx]

            for layer in range(1, 12):
                offset = layer * 10 + key_idx
                if actuations[offset] != first_values[key]:
                    all_same = False
                    break
            if not all_same:
                break

        for layer in range(12):
            offset = layer * 10
            flags = actuations[offset + 9]
            
            self.layer_data[layer] = {
                'normal': actuations[offset + 0],
                'midi': actuations[offset + 1],
                'aftertouch': actuations[offset + 2],
                'velocity': actuations[offset + 3],
                'rapid': actuations[offset + 4],
                'midi_rapid_sens': actuations[offset + 5],
                'midi_rapid_vel': actuations[offset + 6],
                'vel_speed': actuations[offset + 7],
                'aftertouch_cc': actuations[offset + 8],
                'rapidfire_enabled': (flags & 0x01) != 0,
                'midi_rapidfire_enabled': (flags & 0x02) != 0
            }
        
        self.master_widgets['normal_slider'].setValue(first_values['normal'])
        self.master_widgets['midi_slider'].setValue(first_values['midi'])
        
        for key in ['aftertouch', 'aftertouch_cc', 'velocity', 'vel_speed']:
            combo = self.master_widgets[f'{key}_combo']
            for i in range(combo.count()):
                if combo.itemData(i) == first_values[key]:
                    combo.setCurrentIndex(i)
                    break
        
        first_flags = first_values['flags']
        rapid_enabled = (first_flags & 0x01) != 0
        self.master_widgets['rapid_checkbox'].setChecked(rapid_enabled)
        self.master_widgets['rapid_widget'].setVisible(rapid_enabled)
        self.master_widgets['rapid_slider'].setValue(first_values['rapid'])
        
        midi_rapid_enabled = (first_flags & 0x02) != 0
        self.master_widgets['midi_rapid_checkbox'].setChecked(midi_rapid_enabled)
        self.master_widgets['midi_rapid_sens_widget'].setVisible(midi_rapid_enabled)
        self.master_widgets['midi_rapid_vel_widget'].setVisible(midi_rapid_enabled)
        self.master_widgets['midi_rapid_sens_slider'].setValue(first_values['midi_rapid_sens'])
        self.master_widgets['midi_rapid_vel_slider'].setValue(first_values['midi_rapid_vel'])
        
        if self.per_layer_enabled:
            self.load_layer_to_ui(self.current_layer)
        
        self.per_layer_checkbox.setChecked(not all_same)




class GamingConfigurator(BasicEditor):

    def __init__(self):
        super().__init__()
        self.keyboard = None
        self.gaming_controls = {}
        self.active_control_id = None  # Track which control is being assigned
        self.setup_ui()

    def create_help_label(self, tooltip_text):
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
                border-color: #fff;
            }
        """)
        help_btn.setToolTip(tooltip_text)
        help_btn.setFocusPolicy(Qt.NoFocus)
        return help_btn

    def setup_ui(self):
        # Create scroll area for better window resizing
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        scroll_area.setWidget(main_widget)
        self.addWidget(scroll_area)

        # Create horizontal layout: Settings (title+desc+response+calibration) | Gamepad | Curve
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(15)
        main_layout.addLayout(controls_layout)

        # COLUMN 1: Title, Description, and Response+Calibration side by side
        settings_column = QVBoxLayout()
        settings_column.setSpacing(8)

        # Title at top
        title_label = QLabel(tr("GamingConfigurator", "Gaming Mode"))
        title_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        settings_column.addWidget(title_label)

        # Description below title
        desc_label = QLabel(tr("GamingConfigurator",
            "Assign keyboard keys to gamepad buttons. "
            "Assigned keys will act as gamepad inputs when Gaming Mode is enabled, "
            "and function normally when disabled. "
            "Click a button on the controller, then select a key from the keycodes below."))
        desc_label.setWordWrap(True)
        desc_label.setMaximumWidth(400)
        desc_label.setStyleSheet("color: gray; font-size: 9pt;")
        settings_column.addWidget(desc_label)

        # Gaming Mode master enable. Without this the tab had no way to turn gaming
        # mode ON — a user could assign controls and Save, but the mappings only
        # take effect while gaming mode is active, so the gamepad stayed dead. This
        # applies instantly (like the on-device GAMING_MODE keycode) rather than
        # waiting for "Save Configuration".
        enable_row = QHBoxLayout()
        enable_row.setContentsMargins(0, 0, 0, 0)
        self.gaming_mode_checkbox = QCheckBox(tr("GamingConfigurator", "Gaming Mode Enabled"))
        self.gaming_mode_checkbox.setStyleSheet("font-weight: bold;")
        self.gaming_mode_checkbox.setToolTip(
            "Turn the keyboard's gamepad mode on or off. Applies immediately.\n"
            "When on, assigned keys act as gamepad inputs; when off, they behave normally.")
        self.gaming_mode_checkbox.toggled.connect(self.on_gaming_mode_toggled)
        enable_row.addWidget(self.gaming_mode_checkbox)
        enable_row.addStretch()
        settings_column.addLayout(enable_row)

        # Horizontal layout for Response and Calibration side by side
        response_calibration_layout = QHBoxLayout()
        response_calibration_layout.setSpacing(8)

        # Gamepad Response Section
        response_group = QGroupBox(tr("GamingConfigurator", "Gamepad Response"))
        response_group.setMaximumWidth(200)
        response_layout = QVBoxLayout()
        response_layout.setSpacing(4)
        response_group.setLayout(response_layout)

        # Angle Adjustment
        angle_adj_row = QHBoxLayout()
        angle_adj_row.addWidget(self.create_help_label("Enable diagonal angle adjustment.\nModifies the angle at which diagonals are registered."))
        self.angle_adj_checkbox = QCheckBox(tr("GamingConfigurator", "Angle adjustment"))
        angle_adj_row.addWidget(self.angle_adj_checkbox)
        angle_adj_row.addStretch()
        response_layout.addLayout(angle_adj_row)

        # Diagonal Angle Slider
        angle_widget = QWidget()
        angle_layout = QVBoxLayout()
        angle_layout.setSpacing(2)
        angle_layout.setContentsMargins(15, 0, 0, 0)  # Indent
        angle_widget.setLayout(angle_layout)

        angle_label_row = QHBoxLayout()
        angle_label_row.addWidget(self.create_help_label("Angle offset for diagonal detection (0-90°).\nHigher values make diagonals easier to hit."))
        self.diagonal_angle_label = QLabel("Angle: 0°")
        angle_label_row.addWidget(self.diagonal_angle_label)
        angle_label_row.addStretch()
        angle_layout.addLayout(angle_label_row)

        self.diagonal_angle_slider = QSlider(Qt.Horizontal)
        self.diagonal_angle_slider.setMinimum(0)
        self.diagonal_angle_slider.setMaximum(90)
        self.diagonal_angle_slider.setValue(0)
        self.diagonal_angle_slider.setTickInterval(10)
        self.diagonal_angle_slider.valueChanged.connect(
            lambda val: self.diagonal_angle_label.setText(f"Angle: {val}°")
        )
        angle_layout.addWidget(self.diagonal_angle_slider)
        response_layout.addWidget(angle_widget)

        # Square Output
        square_row = QHBoxLayout()
        square_row.addWidget(self.create_help_label(
            "Restrict joystick movement to a square instead of circle.\n"
            "Allows maximum axis output. Recommended for Rocket League and CS:GO."))
        self.square_output_checkbox = QCheckBox(tr("GamingConfigurator", "Square output"))
        square_row.addWidget(self.square_output_checkbox)
        square_row.addStretch()
        response_layout.addLayout(square_row)

        # Snappy Joystick
        snappy_row = QHBoxLayout()
        snappy_row.addWidget(self.create_help_label(
            "Use maximum value of opposite sides of axis rather than combining them."))
        self.snappy_joystick_checkbox = QCheckBox(tr("GamingConfigurator", "Snappy Joystick"))
        snappy_row.addWidget(self.snappy_joystick_checkbox)
        snappy_row.addStretch()
        response_layout.addLayout(snappy_row)

        # Suppress Keystrokes
        suppress_row = QHBoxLayout()
        suppress_row.addWidget(self.create_help_label(
            "When enabled, keys mapped as gaming controls will not send\n"
            "their normal keystrokes (e.g. 'E') while Gaming Mode is active.\n"
            "Only the joystick button/axis output will be sent."))
        self.suppress_keystrokes_checkbox = QCheckBox(tr("GamingConfigurator", "Suppress keystrokes"))
        self.suppress_keystrokes_checkbox.setChecked(True)  # Default ON
        suppress_row.addWidget(self.suppress_keystrokes_checkbox)
        suppress_row.addStretch()
        response_layout.addLayout(suppress_row)

        response_calibration_layout.addWidget(response_group, alignment=QtCore.Qt.AlignTop)

        # Analog Calibration Group
        calibration_group = QGroupBox(tr("GamingConfigurator", "Analog Calibration"))
        calibration_group.setMaximumWidth(400)
        calibration_layout = QVBoxLayout()
        calibration_layout.setSpacing(6)
        calibration_group.setLayout(calibration_layout)

        # Helper function to create stacked slider pair (min on top, max below)
        def create_minmax_slider_row(section_name, default_min, default_max):
            container = QWidget()
            layout = QVBoxLayout()
            layout.setSpacing(2)
            layout.setContentsMargins(0, 0, 0, 0)
            container.setLayout(layout)

            section_label = QLabel(f"<b>{section_name}</b>")
            layout.addWidget(section_label)

            # Min slider
            min_label = QLabel(f"Min: {default_min/100:.2f}mm")
            min_label.setStyleSheet("font-size: 8pt;")
            layout.addWidget(min_label)

            min_slider = QSlider(Qt.Horizontal)
            min_slider.setMinimum(0)
            min_slider.setMaximum(400)  # 0.00 to 4.00mm in 0.01mm increments
            min_slider.setValue(default_min)
            min_slider.valueChanged.connect(
                lambda val, lbl=min_label: lbl.setText(f"Min: {val/100:.2f}mm")
            )
            layout.addWidget(min_slider)

            # Max slider
            max_label = QLabel(f"Max: {default_max/100:.2f}mm")
            max_label.setStyleSheet("font-size: 8pt;")
            layout.addWidget(max_label)

            max_slider = QSlider(Qt.Horizontal)
            max_slider.setMinimum(0)
            max_slider.setMaximum(400)  # 0.00 to 4.00mm in 0.01mm increments
            max_slider.setValue(default_max)
            max_slider.valueChanged.connect(
                lambda val, lbl=max_label: lbl.setText(f"Max: {val/100:.2f}mm")
            )
            layout.addWidget(max_slider)

            return container, min_slider, max_slider, min_label, max_label

        # LS (Left Stick) Calibration
        ls_widget, self.ls_min_travel_slider, self.ls_max_travel_slider, self.ls_min_travel_label, self.ls_max_travel_label = create_minmax_slider_row(
            tr("GamingConfigurator", "Left Stick"), 100, 200
        )
        calibration_layout.addWidget(ls_widget)

        # RS (Right Stick) Calibration
        rs_widget, self.rs_min_travel_slider, self.rs_max_travel_slider, self.rs_min_travel_label, self.rs_max_travel_label = create_minmax_slider_row(
            tr("GamingConfigurator", "Right Stick"), 100, 200
        )
        calibration_layout.addWidget(rs_widget)

        # Triggers Calibration
        trigger_widget, self.trigger_min_travel_slider, self.trigger_max_travel_slider, self.trigger_min_travel_label, self.trigger_max_travel_label = create_minmax_slider_row(
            tr("GamingConfigurator", "Triggers"), 100, 200
        )
        calibration_layout.addWidget(trigger_widget)

        response_calibration_layout.addWidget(calibration_group, alignment=QtCore.Qt.AlignTop)

        settings_column.addLayout(response_calibration_layout)
        settings_column.addStretch()

        controls_layout.addLayout(settings_column)

        # COLUMN 3: Gamepad widget with drawn outline
        gamepad_widget = GamepadWidget()
        gamepad_widget.setFixedSize(750, 560)
        controls_layout.addWidget(gamepad_widget)

        # RIGHT COLUMN: Per-Axis Analog Curves (LS/RS/LT/RT tabs)
        from widgets.gaming_curve_editor import GamingCurveEditor
        curve_group = QGroupBox(tr("GamingConfigurator", "Analog Curves"))
        curve_group.setMaximumWidth(320)
        curve_group_layout = QVBoxLayout()
        curve_group.setLayout(curve_group_layout)

        self.gaming_curve_editor = GamingCurveEditor()
        curve_group_layout.addWidget(self.gaming_curve_editor)

        # Save/Load/Reset buttons below curves
        curve_buttons_layout = QHBoxLayout()
        curve_buttons_layout.setSpacing(4)

        curve_button_style = "QPushButton { border-radius: 3px; padding: 4px 8px; font-size: 8pt; }"

        save_btn = QPushButton(tr("GamingConfigurator", "Save Configuration"))
        save_btn.setMinimumHeight(30)
        save_btn.setStyleSheet(curve_button_style)
        save_btn.clicked.connect(self.on_save)
        curve_buttons_layout.addWidget(save_btn)

        load_btn = QPushButton(tr("GamingConfigurator", "Load from Keyboard"))
        load_btn.setMinimumHeight(30)
        load_btn.setStyleSheet(curve_button_style)
        load_btn.clicked.connect(self.on_load_from_keyboard)
        curve_buttons_layout.addWidget(load_btn)

        reset_btn = QPushButton(tr("GamingConfigurator", "Reset to Defaults"))
        reset_btn.setMinimumHeight(30)
        reset_btn.setStyleSheet(curve_button_style)
        reset_btn.clicked.connect(self.on_reset)
        curve_buttons_layout.addWidget(reset_btn)

        curve_group_layout.addLayout(curve_buttons_layout)

        controls_layout.addWidget(curve_group, alignment=QtCore.Qt.AlignTop)

        # Map control IDs to positions and names
        # Control IDs 0-9: axes/triggers (handled by firmware switch statement)
        #   0=LS Up, 1=LS Down, 2=LS Left, 3=LS Right
        #   4=RS Up, 5=RS Down, 6=RS Left, 7=RS Right
        #   8=LT, 9=RT
        # Control IDs 10+: buttons[control_id - 10] → joystick button (control_id - 10)
        # Must match keycode button IDs: A=0, B=1, X=2, Y=3, LB=4, RB=5,
        # Back=6, Start=7, L3=8, R3=9, DPad=12-15
        control_mapping = {
            # Face buttons (buttons 0-3, control_ids 10-13)
            10: ("Button 1", "btn1", 517, 178, 50, 50, "1"),  # A = joystick button 0
            11: ("Button 2", "btn2", 553, 139, 50, 50, "2"),  # B = joystick button 1
            12: ("Button 3", "btn3", 481, 139, 50, 50, "3"),  # X = joystick button 2
            13: ("Button 4", "btn4", 517, 103, 50, 50, "4"),  # Y = joystick button 3
            # Bumpers (buttons 4-5, control_ids 14-15)
            14: ("LB", "lb", 177, 65, 60, 30, "LB"),
            15: ("RB", "rb", 503, 65, 60, 30, "RB"),
            # Center buttons (buttons 6-7, control_ids 16-17)
            16: ("Back", "back", 320, 170, 50, 30, "Back"),
            17: ("Start", "start", 380, 170, 50, 30, "Start"),
            # Stick clicks (buttons 8-9, control_ids 18-19)
            18: ("LS Click", "l3", 275, 223, 38, 38, "L3"),
            19: ("RS Click", "r3", 439, 223, 38, 38, "R3"),
            # D-pad (buttons 12-15, control_ids 22-25)
            22: ("D-pad Up", "dpad_up", 180, 105, 56, 58, "↑"),
            23: ("D-pad Down", "dpad_down", 180, 163, 56, 58, "↓"),
            24: ("D-pad Left", "dpad_left", 150, 135, 58, 56, "←"),
            25: ("D-pad Right", "dpad_right", 208, 135, 58, 56, "→"),
            # Sticks (axes, control_ids 0-7)
            0: ("LS Up", "ls_up", 275, 185, 38, 38, "↑"),
            1: ("LS Down", "ls_down", 275, 261, 38, 38, "↓"),
            2: ("LS Left", "ls_left", 237, 223, 38, 38, "←"),
            3: ("LS Right", "ls_right", 313, 223, 38, 38, "→"),
            4: ("RS Up", "rs_up", 439, 185, 38, 38, "↑"),
            5: ("RS Down", "rs_down", 439, 261, 38, 38, "↓"),
            6: ("RS Left", "rs_left", 401, 223, 38, 38, "←"),
            7: ("RS Right", "rs_right", 477, 223, 38, 38, "→"),
            # Triggers (axes, control_ids 8-9)
            8: ("LT", "lt", 177, 25, 60, 35, "LT"),
            9: ("RT", "rt", 503, 25, 60, 35, "RT"),
        }

        # Create buttons positioned over gamepad
        for control_id, (name, key, x, y, w, h, text) in control_mapping.items():
            # Create button based on type
            if "dpad" in key:
                # Use DpadButton for d-pad with shaped paths
                btn = DpadButton("Not Set")
                btn.setFixedSize(w, h)
                btn.setParent(gamepad_widget)
                btn.move(x, y)

                # Set shaped path for d-pad buttons
                path = QPainterPath()
                if key == "dpad_up":
                    path.moveTo(28, 58)
                    path.lineTo(3, 33)
                    path.lineTo(3, 8)
                    path.quadTo(8, 3, 15, 3)
                    path.lineTo(41, 3)
                    path.quadTo(48, 3, 53, 8)
                    path.lineTo(53, 33)
                    path.lineTo(28, 58)
                    path.closeSubpath()
                elif key == "dpad_down":
                    path.moveTo(28, 0)
                    path.lineTo(3, 25)
                    path.lineTo(3, 50)
                    path.quadTo(8, 55, 15, 55)
                    path.lineTo(41, 55)
                    path.quadTo(48, 55, 53, 50)
                    path.lineTo(53, 25)
                    path.lineTo(28, 0)
                    path.closeSubpath()
                elif key == "dpad_left":
                    path.moveTo(58, 28)
                    path.lineTo(33, 3)
                    path.lineTo(8, 3)
                    path.quadTo(3, 8, 3, 15)
                    path.lineTo(3, 41)
                    path.quadTo(3, 48, 8, 53)
                    path.lineTo(33, 53)
                    path.lineTo(58, 28)
                    path.closeSubpath()
                elif key == "dpad_right":
                    path.moveTo(0, 28)
                    path.lineTo(25, 3)
                    path.lineTo(50, 3)
                    path.quadTo(55, 8, 55, 15)
                    path.lineTo(55, 41)
                    path.quadTo(55, 48, 50, 53)
                    path.lineTo(25, 53)
                    path.lineTo(0, 28)
                    path.closeSubpath()

                btn.setMask(QRegion(path.toFillPolygon().toPolygon()))
                btn.set_border_path(path)
            elif "btn" in key and key in ["btn1", "btn2", "btn3", "btn4"]:
                # Circular face buttons (exactly like GamingTab)
                btn = QPushButton("Not Set")
                btn.setFixedSize(w, h)
                btn.setParent(gamepad_widget)
                btn.move(x, y)
                btn.setStyleSheet("border-radius: 25px;")
            else:
                # Regular rectangular buttons (no special styling, exactly like GamingTab)
                btn = QPushButton("Not Set")
                btn.setFixedSize(w, h)
                btn.setParent(gamepad_widget)
                btn.move(x, y)

            btn.clicked.connect(lambda checked, cid=control_id: self.on_assign_key(cid))
            btn.setProperty("control_id", control_id)

            # Store reference with button type
            button_type = "dpad" if "dpad" in key else ("face" if key in ["btn1", "btn2", "btn3", "btn4"] else "regular")
            self.gaming_controls[control_id] = {
                'button': btn,
                'button_type': button_type,
                'keycode': None,
                'row': None,
                'col': None,
                'enabled': False
            }

        # Add outer stretch on the right
        controls_layout.addStretch(1)

        # Add TabbedKeycodes at the bottom like in Macros tab
        from tabbed_keycodes import TabbedKeycodes
        self.tabbed_keycodes = TabbedKeycodes()
        self.tabbed_keycodes.keycode_changed.connect(self.on_keycode_selected)
        self.addWidget(self.tabbed_keycodes)

        # Apply stylesheet
        main_widget.setStyleSheet("""
            QCheckBox:focus {
                font-weight: normal;
                outline: none;
            }
            QPushButton:focus {
                font-weight: normal;
                outline: none;
            }
        """)

    def get_button_style(self, button_type, highlighted=False):
        """Get the appropriate style for a button based on its type"""
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QPalette

        if button_type == "face":
            # Face buttons are circular
            base_style = "border-radius: 25px;"
        elif button_type == "dpad":
            # D-pad buttons don't have inline styles (they use masks)
            base_style = ""
        else:
            # Regular buttons have no special styling
            base_style = ""

        if highlighted:
            # Use theme colors for highlighting
            palette = QApplication.palette()
            highlight_color = palette.color(QPalette.Highlight).name()
            highlight_text = palette.color(QPalette.HighlightedText).name()
            return f"QPushButton {{ {base_style} background-color: {highlight_color}; color: {highlight_text}; }}"
        else:
            # Return empty stylesheet to clear any previous styling (except base_style)
            return f"QPushButton {{ {base_style} }}"

    def on_gaming_mode_toggled(self, checked):
        """Enable/disable gaming mode on the device immediately."""
        if not self.keyboard:
            return
        try:
            if not self.keyboard.set_gaming_mode(checked):
                QMessageBox.warning(None, "Error", "Failed to change Gaming Mode on the keyboard")
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Error setting Gaming Mode: {str(e)}")

    def _apply_key_map_to_control(self, control_id, mapping):
        """Populate one gamepad control button from a firmware key mapping dict."""
        data = self.gaming_controls.get(control_id)
        if data is None:
            return
        button_type = data.get('button_type', 'regular')
        if mapping and mapping.get('enabled'):
            row, col = mapping['row'], mapping['col']
            data['row'] = row
            data['col'] = col
            data['enabled'] = True
            # Resolve the keycode at that position (prefer layer 0) purely for a
            # readable button label; the mapping itself is by row/col.
            label = None
            kc = None
            if self.keyboard:
                for (layer, r, c), k in sorted(self.keyboard.layout.items()):
                    if r == row and c == col:
                        kc = k
                        break
            if kc is not None:
                from keycodes.keycodes import Keycode
                label = Keycode.label(kc)
                data['keycode'] = kc
            if not label:
                label = f"r{row}c{col}"
            if len(label) > 7:
                label = label[:6] + ".."
            data['button'].setText(label)
        else:
            data['keycode'] = None
            data['row'] = None
            data['col'] = None
            data['enabled'] = False
            data['button'].setText("Not Set")
        data['button'].setStyleSheet(self.get_button_style(button_type, highlighted=False))

    def _load_key_mappings(self):
        """Read every gamepad control's mapping back from the device and show it.

        Essential for a safe Save: on_save() sends enabled=0 for any control that
        isn't shown as assigned, so without loading the existing mappings first a
        Save would wipe the user's gamepad layout on the device."""
        if not self.keyboard or not hasattr(self.keyboard, 'get_gaming_key_map'):
            return
        for control_id in self.gaming_controls.keys():
            mapping = self.keyboard.get_gaming_key_map(control_id)
            self._apply_key_map_to_control(control_id, mapping)

    def on_assign_key(self, control_id):
        """Handle key assignment for a gaming control"""
        self.active_control_id = control_id
        # Highlight the button being assigned and unhighlight all others
        for cid, data in self.gaming_controls.items():
            button_type = data.get('button_type', 'regular')
            if cid == control_id:
                data['button'].setStyleSheet(self.get_button_style(button_type, highlighted=True))
            else:
                # Always set style to clear any previous highlighting
                data['button'].setStyleSheet(self.get_button_style(button_type, highlighted=False))

    def on_keycode_selected(self, keycode):
        """Called when a keycode is selected from TabbedKeycodes"""
        if self.active_control_id is None or not self.keyboard:
            return

        # Find the physical position (row, col) of this keycode - search ALL layers
        row, col = self.find_keycode_position(keycode)

        if row is not None and col is not None:
            # Assign to the active control
            data = self.gaming_controls[self.active_control_id]
            data['keycode'] = keycode
            data['row'] = row
            data['col'] = col
            data['enabled'] = True

            # Update button text to show the keycode label
            from keycodes.keycodes import Keycode
            label = Keycode.label(keycode)
            # Truncate label to fit in 50x50 button
            if len(label) > 7:
                label = label[:6] + ".."
            data['button'].setText(label)

            # Reset button style based on its type (clears highlighting)
            button_type = data.get('button_type', 'regular')
            data['button'].setStyleSheet(self.get_button_style(button_type, highlighted=False))

            # Clear active control
            self.active_control_id = None
        else:
            # Keycode not found in any layer - show error
            QMessageBox.warning(None, "Key Not Found",
                              f"The selected keycode is not found in your keymap on any layer.\n"
                              f"Please select a key that exists in your keymap.")
            # Reset the button style (clears highlighting)
            data = self.gaming_controls[self.active_control_id]
            button_type = data.get('button_type', 'regular')
            data['button'].setStyleSheet(self.get_button_style(button_type, highlighted=False))
            self.active_control_id = None

    def find_keycode_position(self, keycode):
        """Find the matrix position (row, col) of a keycode - searches ALL layers"""
        if not self.keyboard:
            return None, None

        # Search through ALL layers for this keycode (prefer layer 0 first)
        for (layer, row, col), kc in sorted(self.keyboard.layout.items()):
            if kc == keycode:
                return row, col

        return None, None

    def on_save(self):
        """Save gaming configuration to keyboard"""
        if not self.keyboard:
            QMessageBox.warning(None, "No Keyboard", "No keyboard connected")
            return

        try:
            # Save analog configuration - separate for LS, RS, and Triggers
            ls_min = self.ls_min_travel_slider.value()
            ls_max = self.ls_max_travel_slider.value()
            rs_min = self.rs_min_travel_slider.value()
            rs_max = self.rs_max_travel_slider.value()
            trigger_min = self.trigger_min_travel_slider.value()
            trigger_max = self.trigger_max_travel_slider.value()

            # Validate ranges
            if ls_min >= ls_max:
                QMessageBox.warning(None, "Invalid Range", "LS Min travel must be less than LS Max travel")
                return
            if rs_min >= rs_max:
                QMessageBox.warning(None, "Invalid Range", "RS Min travel must be less than RS Max travel")
                return
            if trigger_min >= trigger_max:
                QMessageBox.warning(None, "Invalid Range", "Trigger Min travel must be less than Trigger Max travel")
                return

            suppress_keystrokes = self.suppress_keystrokes_checkbox.isChecked()
            # Convert slider values from 0.01mm to 0.1mm (firmware units)
            success = self.keyboard.set_gaming_analog_config(
                ls_min // 10, ls_max // 10, rs_min // 10, rs_max // 10,
                trigger_min // 10, trigger_max // 10, suppress_keystrokes
            )

            # Save key mappings
            for control_id, data in self.gaming_controls.items():
                if data['enabled'] and data['row'] is not None and data['col'] is not None:
                    self.keyboard.set_gaming_key_map(control_id, data['row'], data['col'], 1)
                else:
                    self.keyboard.set_gaming_key_map(control_id, 0, 0, 0)

            # Save gamepad response settings
            angle_adj_enabled = self.angle_adj_checkbox.isChecked()
            diagonal_angle = self.diagonal_angle_slider.value()
            square_output = self.square_output_checkbox.isChecked()
            snappy_joystick = self.snappy_joystick_checkbox.isChecked()

            response_success = self.keyboard.set_gaming_response(
                angle_adj_enabled, diagonal_angle, square_output, snappy_joystick, 0
            )

            # Save per-axis analog curves
            curve_map = {'ls': 0, 'rs': 1, 'lt': 2, 'rt': 3}
            curves = self.gaming_curve_editor.get_all_curves()
            curves_success = True
            for key, curve_id in curve_map.items():
                if key in curves:
                    if not self.keyboard.set_gaming_curve(curve_id, curves[key]):
                        curves_success = False

            if success and response_success and curves_success:
                QMessageBox.information(None, "Success", "Gaming configuration saved successfully")
            else:
                QMessageBox.warning(None, "Error", "Failed to save gaming configuration")
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Error saving configuration: {str(e)}")

    def on_load_from_keyboard(self):
        """Load gaming configuration from keyboard"""
        if not self.keyboard:
            QMessageBox.warning(None, "No Keyboard", "No keyboard connected")
            return

        try:
            settings = self.keyboard.get_gaming_settings()
            if settings:
                # Block signals while updating
                self.ls_min_travel_slider.blockSignals(True)
                self.ls_max_travel_slider.blockSignals(True)
                self.rs_min_travel_slider.blockSignals(True)
                self.rs_max_travel_slider.blockSignals(True)
                self.trigger_min_travel_slider.blockSignals(True)
                self.trigger_max_travel_slider.blockSignals(True)

                # Set values for LS/RS/Triggers (convert from 0.1mm firmware units to 0.01mm slider units)
                self.ls_min_travel_slider.setValue(settings.get('ls_min_travel', 10) * 10)
                self.ls_max_travel_slider.setValue(settings.get('ls_max_travel', 20) * 10)
                self.rs_min_travel_slider.setValue(settings.get('rs_min_travel', 10) * 10)
                self.rs_max_travel_slider.setValue(settings.get('rs_max_travel', 20) * 10)
                self.trigger_min_travel_slider.setValue(settings.get('trigger_min_travel', 10) * 10)
                self.trigger_max_travel_slider.setValue(settings.get('trigger_max_travel', 20) * 10)

                self.ls_min_travel_slider.blockSignals(False)
                self.ls_max_travel_slider.blockSignals(False)
                self.rs_min_travel_slider.blockSignals(False)
                self.rs_max_travel_slider.blockSignals(False)
                self.trigger_min_travel_slider.blockSignals(False)
                self.trigger_max_travel_slider.blockSignals(False)

                # Update labels (firmware values in 0.1mm, display in mm)
                self.ls_min_travel_label.setText(f"Min: {settings.get('ls_min_travel', 10)/10:.1f}mm")
                self.ls_max_travel_label.setText(f"Max: {settings.get('ls_max_travel', 20)/10:.1f}mm")
                self.rs_min_travel_label.setText(f"Min: {settings.get('rs_min_travel', 10)/10:.1f}mm")
                self.rs_max_travel_label.setText(f"Max: {settings.get('rs_max_travel', 20)/10:.1f}mm")
                self.trigger_min_travel_label.setText(f"Min: {settings.get('trigger_min_travel', 10)/10:.1f}mm")
                self.trigger_max_travel_label.setText(f"Max: {settings.get('trigger_max_travel', 20)/10:.1f}mm")

                # Update suppress keystrokes checkbox
                self.suppress_keystrokes_checkbox.blockSignals(True)
                self.suppress_keystrokes_checkbox.setChecked(settings.get('suppress_keystrokes', True))
                self.suppress_keystrokes_checkbox.blockSignals(False)

                # Reflect current gaming-mode enable state (signals blocked)
                self.gaming_mode_checkbox.blockSignals(True)
                self.gaming_mode_checkbox.setChecked(settings.get('enabled', False))
                self.gaming_mode_checkbox.blockSignals(False)

                # Load existing key mappings so Save can't wipe them
                self._load_key_mappings()

                # Load gamepad response settings
                response = self.keyboard.get_gaming_response()
                if response:
                    self.angle_adj_checkbox.setChecked(response.get('angle_adj_enabled', False))
                    self.diagonal_angle_slider.setValue(response.get('diagonal_angle', 0))
                    self.diagonal_angle_label.setText(f"Angle: {response.get('diagonal_angle', 0)}°")
                    self.square_output_checkbox.setChecked(response.get('square_output', False))
                    self.snappy_joystick_checkbox.setChecked(response.get('snappy_joystick', False))

                # Load per-axis analog curves
                curve_map = {'ls': 0, 'rs': 1, 'lt': 2, 'rt': 3}
                curves = {}
                for key, curve_id in curve_map.items():
                    points = self.keyboard.get_gaming_curve(curve_id)
                    if points:
                        curves[key] = points
                if curves:
                    self.gaming_curve_editor.set_all_curves(curves)

                QMessageBox.information(None, "Success", "Gaming configuration loaded from keyboard")
            else:
                QMessageBox.warning(None, "Error", "Failed to load gaming configuration")
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Error loading configuration: {str(e)}")

    def on_reset(self):
        """Reset gaming configuration to defaults"""
        if not self.keyboard:
            QMessageBox.warning(None, "No Keyboard", "No keyboard connected")
            return

        reply = QMessageBox.question(None, "Confirm Reset",
                                     "Reset gaming configuration to defaults?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                success = self.keyboard.reset_gaming_settings()
                if success:
                    self.on_load_from_keyboard()
                    # Clear all assignments
                    for data in self.gaming_controls.values():
                        data['button'].setText("Not Set")
                        data['button'].setStyleSheet("QPushButton { text-align: center; border-radius: 3px; font-size: 9px; }")
                        data['keycode'] = None
                        data['row'] = None
                        data['col'] = None
                        data['enabled'] = False
                    self.gaming_curve_editor.reset_all()
                    QMessageBox.information(None, "Success", "Gaming configuration reset to defaults")
                else:
                    QMessageBox.warning(None, "Error", "Failed to reset gaming configuration")
            except Exception as e:
                QMessageBox.critical(None, "Error", f"Error resetting configuration: {str(e)}")

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            # Set keyboard reference for tabbed keycodes (so GamingTab can access it)
            self.tabbed_keycodes.set_keyboard(self.keyboard)
            self.tabbed_keycodes.recreate_keycode_buttons()
            # Load gaming data immediately during device connection
            self._load_gaming_data()

    def activate(self):
        """Called when tab is selected"""
        pass

    def _load_gaming_data(self):
        """Load gaming settings from device (heavy operation - multiple HID calls)"""
        print("GamingConfigurator: Loading gaming data (this may take a while)...")
        try:
            # Use cached gaming settings if available, otherwise fetch them
            settings = getattr(self.keyboard, 'gaming_settings', None) or self.keyboard.get_gaming_settings()
            if settings:
                # Block signals while updating
                self.ls_min_travel_slider.blockSignals(True)
                self.ls_max_travel_slider.blockSignals(True)
                self.rs_min_travel_slider.blockSignals(True)
                self.rs_max_travel_slider.blockSignals(True)
                self.trigger_min_travel_slider.blockSignals(True)
                self.trigger_max_travel_slider.blockSignals(True)

                # Convert from 0.1mm (firmware) to 0.01mm (slider units)
                self.ls_min_travel_slider.setValue(settings.get('ls_min_travel', 10) * 10)
                self.ls_max_travel_slider.setValue(settings.get('ls_max_travel', 20) * 10)
                self.rs_min_travel_slider.setValue(settings.get('rs_min_travel', 10) * 10)
                self.rs_max_travel_slider.setValue(settings.get('rs_max_travel', 20) * 10)
                self.trigger_min_travel_slider.setValue(settings.get('trigger_min_travel', 10) * 10)
                self.trigger_max_travel_slider.setValue(settings.get('trigger_max_travel', 20) * 10)

                self.ls_min_travel_slider.blockSignals(False)
                self.ls_max_travel_slider.blockSignals(False)
                self.rs_min_travel_slider.blockSignals(False)
                self.rs_max_travel_slider.blockSignals(False)
                self.trigger_min_travel_slider.blockSignals(False)
                self.trigger_max_travel_slider.blockSignals(False)

                # Update labels (firmware values in 0.1mm, display in mm)
                self.ls_min_travel_label.setText(f"Min: {settings.get('ls_min_travel', 10)/10:.1f}mm")
                self.ls_max_travel_label.setText(f"Max: {settings.get('ls_max_travel', 20)/10:.1f}mm")
                self.rs_min_travel_label.setText(f"Min: {settings.get('rs_min_travel', 10)/10:.1f}mm")
                self.rs_max_travel_label.setText(f"Max: {settings.get('rs_max_travel', 20)/10:.1f}mm")
                self.trigger_min_travel_label.setText(f"Min: {settings.get('trigger_min_travel', 10)/10:.1f}mm")
                self.trigger_max_travel_label.setText(f"Max: {settings.get('trigger_max_travel', 20)/10:.1f}mm")

                # Update suppress keystrokes checkbox
                self.suppress_keystrokes_checkbox.blockSignals(True)
                self.suppress_keystrokes_checkbox.setChecked(settings.get('suppress_keystrokes', True))
                self.suppress_keystrokes_checkbox.blockSignals(False)

                # Reflect the current gaming-mode enable state (block signals so
                # showing it doesn't fire an unwanted set_gaming_mode round-trip).
                self.gaming_mode_checkbox.blockSignals(True)
                self.gaming_mode_checkbox.setChecked(settings.get('enabled', False))
                self.gaming_mode_checkbox.blockSignals(False)

            # Load existing key mappings so Save can't wipe them
            self._load_key_mappings()

            # Load gamepad response settings
            response = self.keyboard.get_gaming_response()
            if response:
                self.angle_adj_checkbox.blockSignals(True)
                self.diagonal_angle_slider.blockSignals(True)
                self.square_output_checkbox.blockSignals(True)
                self.snappy_joystick_checkbox.blockSignals(True)

                self.angle_adj_checkbox.setChecked(response.get('angle_adj_enabled', False))
                self.diagonal_angle_slider.setValue(response.get('diagonal_angle', 0))
                self.diagonal_angle_label.setText(f"Angle: {response.get('diagonal_angle', 0)}°")
                self.square_output_checkbox.setChecked(response.get('square_output', False))
                self.snappy_joystick_checkbox.setChecked(response.get('snappy_joystick', False))

                self.angle_adj_checkbox.blockSignals(False)
                self.diagonal_angle_slider.blockSignals(False)
                self.square_output_checkbox.blockSignals(False)
                self.snappy_joystick_checkbox.blockSignals(False)

            # Load per-axis analog curves
            curve_map = {'ls': 0, 'rs': 1, 'lt': 2, 'rt': 3}
            curves = {}
            for key, curve_id in curve_map.items():
                points = self.keyboard.get_gaming_curve(curve_id)
                if points:
                    curves[key] = points
            if curves:
                self.gaming_curve_editor.set_all_curves(curves)

            print("GamingConfigurator: Gaming data loading complete")
        except Exception as e:
            # Silently fail during load - user can manually load if needed
            print(f"GamingConfigurator: Error loading data: {e}")

    def valid(self):
        return isinstance(self.device, VialKeyboard)
