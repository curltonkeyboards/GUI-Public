# SPDX-License-Identifier: GPL-2.0-or-later

import time

from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QVBoxLayout, QMessageBox, QWidget,
                              QInputDialog,
                              QSlider, QCheckBox, QPushButton, QComboBox, QFrame,
                              QSizePolicy, QScrollArea, QTabWidget, QApplication,
                              QInputDialog)
from PyQt5.QtCore import Qt, pyqtSignal, QEvent
from PyQt5.QtGui import QColor, QPalette, QPainter, QPen, QBrush, QFont

from editor.basic_editor import BasicEditor
from widgets.keyboard_widget import KeyboardWidget2
from widgets.square_button import SquareButton
from widgets.range_slider import TriggerSlider, RapidTriggerSlider
from util import tr, KeycodeDisplay
from vial_device import VialKeyboard
# Delay (seconds) inserted between per-layer HID reads during the connect load so
# the burst doesn't saturate the shared USB device and stall firmware MIDI output.
# ~24 layer reads x 3ms = ~72ms added to connect — imperceptible to the user.
CONNECT_READ_PACING_S = 0.003

from protocol.nullbind_protocol import (ProtocolNullBind, NullBindGroup,
                                         NULLBIND_NUM_GROUPS, NULLBIND_MAX_KEYS_PER_GROUP,
                                         NULLBIND_BEHAVIOR_NEUTRAL, NULLBIND_BEHAVIOR_LAST_INPUT,
                                         NULLBIND_BEHAVIOR_DISTANCE, NULLBIND_BEHAVIOR_PRIORITY_BASE,
                                         NULLBIND_LAYER_ALL,
                                         get_behavior_name, get_behavior_choices)


class ClickableWidget(QWidget):
    """Widget that emits clicked signal when clicked anywhere"""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class TriggerVisualizerWidget(QWidget):
    """Vertical travel bar visualization for Trigger Settings with custom labels and draggable points.

    Labels:
    - Global mode (per-key disabled): "Normal Keys", "Midi Keys"
    - Per-key mode: "Key actuation"
    - Rapidfire mode: "Press Threshold", "Release Threshold" (unchanged)
    """

    # Signals emitted when actuation points are dragged
    actuationDragged = pyqtSignal(int, int)  # (point_index, new_value 0-100)
    pressSensDragged = pyqtSignal(int)  # new_value 0-100
    releaseSensDragged = pyqtSignal(int)  # new_value 0-100

    # Label mode constants
    LABEL_MODE_GLOBAL = 0  # Show "Normal Keys", "Midi Keys"
    LABEL_MODE_PER_KEY = 1  # Show "Key actuation"

    def __init__(self):
        super().__init__()
        self.setMinimumWidth(400)  # Wide enough for all labels without cutoff
        self.setMinimumHeight(250)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.press_actuations = []      # List of (actuation_point, enabled) tuples
        self.release_actuations = []    # List of (actuation_point, enabled) tuples
        self.rapidfire_mode = False     # Flag to enable rapidfire visualization mode
        self.deadzone_top = 0           # Top deadzone value (0-20, representing 0-0.5mm)
        self.deadzone_bottom = 0        # Bottom deadzone value (0-20, representing 0-0.5mm)
        self.actuation_point = 60       # First activation point (0-100, representing 0-4.0mm)

        # Label mode for trigger settings
        self.label_mode = self.LABEL_MODE_GLOBAL

        # Dragging state
        self.dragging = False
        self.drag_point_type = None  # 'press', 'release', 'press_sens', 'release_sens'
        self.drag_point_index = 0

        # Hit areas for actuation points (populated during paint)
        self.press_hit_areas = []  # List of (y, actuation, index) tuples
        self.release_hit_areas = []  # List of (y, actuation, index) tuples

        # Enable mouse tracking for cursor changes
        self.setMouseTracking(True)

    def set_label_mode(self, mode):
        """Set the label mode (LABEL_MODE_GLOBAL or LABEL_MODE_PER_KEY)"""
        self.label_mode = mode
        self.update()

    def set_actuations(self, press_points, release_points, rapidfire_mode=False,
                      deadzone_top=0, deadzone_bottom=0, actuation_point=60):
        """Set actuation points to display

        Args:
            press_points: List of (actuation, enabled) tuples for press actions
            release_points: List of (actuation, enabled) tuples for release actions
            rapidfire_mode: If True, show relative to actuation point with first activation line
            deadzone_top: Top deadzone value (0-20, 0-0.5mm from top, internally inverted)
            deadzone_bottom: Bottom deadzone value (0-20, 0-0.5mm from bottom)
            actuation_point: First activation point (0-100, 0-4.0mm)
        """
        self.press_actuations = press_points
        self.release_actuations = release_points
        self.rapidfire_mode = rapidfire_mode
        self.deadzone_top = deadzone_top
        self.deadzone_bottom = deadzone_bottom
        self.actuation_point = actuation_point
        self.update()

    def _get_bar_geometry(self):
        """Calculate bar geometry for drawing and hit testing"""
        height = self.height()
        margin_top = 40
        margin_bottom = 20
        bar_width = 30
        bar_x = 120
        bar_height = height - margin_top - margin_bottom
        return bar_x, margin_top, margin_bottom, bar_width, bar_height

    def _y_to_actuation(self, y):
        """Convert y position to actuation value (0-255 for 4mm travel)"""
        bar_x, margin_top, margin_bottom, bar_width, bar_height = self._get_bar_geometry()
        if bar_height <= 0:
            return 127  # Default to middle (2mm)
        actuation = ((y - margin_top) / bar_height) * 255
        return max(0, min(255, int(actuation)))

    def _actuation_to_y(self, actuation):
        """Convert actuation value (0-255 for 4mm travel) to y position"""
        bar_x, margin_top, margin_bottom, bar_width, bar_height = self._get_bar_geometry()
        return margin_top + int((actuation / 255.0) * bar_height)

    def mousePressEvent(self, event):
        """Handle mouse press - start dragging if clicking on an actuation point"""
        if event.button() == Qt.LeftButton:
            bar_x, margin_top, margin_bottom, bar_width, bar_height = self._get_bar_geometry()
            x, y = event.x(), event.y()

            # Check if clicking on a press actuation point (left side)
            for i, (actuation, enabled) in enumerate(self.press_actuations):
                if not enabled:
                    continue

                if self.rapidfire_mode:
                    # In rapidfire mode, press is relative to release
                    # Sensitivity values are in firmware 0-255 distance units
                    actuation_y = self._actuation_to_y(self.actuation_point)
                    # Get release position first
                    release_y = actuation_y
                    if self.release_actuations:
                        rel_actuation, rel_enabled = self.release_actuations[0]
                        if rel_enabled:
                            release_y = actuation_y - int((rel_actuation / 255.0) * bar_height)
                    point_y = release_y + int((actuation / 255.0) * bar_height)
                else:
                    point_y = self._actuation_to_y(actuation)

                # Hit test for press point (left side of bar)
                if abs(y - point_y) < 15 and x < bar_x + bar_width // 2:
                    self.dragging = True
                    self.drag_point_type = 'press_sens' if self.rapidfire_mode else 'press'
                    self.drag_point_index = i
                    self.setCursor(Qt.ClosedHandCursor)
                    return

            # Check if clicking on a release actuation point (right side)
            for i, (actuation, enabled) in enumerate(self.release_actuations):
                if not enabled:
                    continue

                if self.rapidfire_mode:
                    # Sensitivity values are in firmware 0-255 distance units
                    actuation_y = self._actuation_to_y(self.actuation_point)
                    point_y = actuation_y - int((actuation / 255.0) * bar_height)
                else:
                    point_y = self._actuation_to_y(actuation)

                # Hit test for release point (right side of bar)
                if abs(y - point_y) < 15 and x > bar_x + bar_width // 2:
                    self.dragging = True
                    self.drag_point_type = 'release_sens' if self.rapidfire_mode else 'release'
                    self.drag_point_index = i
                    self.setCursor(Qt.ClosedHandCursor)
                    return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move - update dragged point position"""
        bar_x, margin_top, margin_bottom, bar_width, bar_height = self._get_bar_geometry()

        if self.dragging:
            y = event.y()

            if self.rapidfire_mode:
                # In rapidfire mode, calculate sensitivity relative to actuation/release point
                # Sensitivity values are in firmware 0-255 distance units (0-4.0mm)
                actuation_y = self._actuation_to_y(self.actuation_point)

                if self.drag_point_type == 'release_sens':
                    # Release is upward from actuation point
                    delta = actuation_y - y
                    # Convert pixel delta to firmware 0-255 units
                    sensitivity = max(1, min(127, int((delta / bar_height) * 255)))
                    self.releaseSensDragged.emit(sensitivity)
                elif self.drag_point_type == 'press_sens':
                    # Press is downward from release point
                    release_y = actuation_y
                    if self.release_actuations:
                        rel_actuation, rel_enabled = self.release_actuations[0]
                        if rel_enabled:
                            release_y = actuation_y - int((rel_actuation / 255.0) * bar_height)
                    delta = y - release_y
                    # Convert pixel delta to firmware 0-255 units
                    sensitivity = max(1, min(127, int((delta / bar_height) * 255)))
                    self.pressSensDragged.emit(sensitivity)
            else:
                # Normal mode - direct actuation value
                actuation = self._y_to_actuation(y)
                if self.drag_point_type == 'press' or self.drag_point_type == 'release':
                    self.actuationDragged.emit(self.drag_point_index, actuation)
        else:
            # Update cursor based on hover position
            x, y = event.x(), event.y()
            hovering_point = False

            # Check press points
            for i, (actuation, enabled) in enumerate(self.press_actuations):
                if not enabled:
                    continue
                if self.rapidfire_mode:
                    # Sensitivity values are in firmware 0-255 distance units
                    actuation_y = self._actuation_to_y(self.actuation_point)
                    release_y = actuation_y
                    if self.release_actuations:
                        rel_actuation, rel_enabled = self.release_actuations[0]
                        if rel_enabled:
                            release_y = actuation_y - int((rel_actuation / 255.0) * bar_height)
                    point_y = release_y + int((actuation / 255.0) * bar_height)
                else:
                    point_y = self._actuation_to_y(actuation)

                if abs(y - point_y) < 15 and x < bar_x + bar_width // 2:
                    hovering_point = True
                    break

            # Check release points
            if not hovering_point:
                for i, (actuation, enabled) in enumerate(self.release_actuations):
                    if not enabled:
                        continue
                    if self.rapidfire_mode:
                        # Sensitivity values are in firmware 0-255 distance units
                        actuation_y = self._actuation_to_y(self.actuation_point)
                        point_y = actuation_y - int((actuation / 255.0) * bar_height)
                    else:
                        point_y = self._actuation_to_y(actuation)

                    if abs(y - point_y) < 15 and x > bar_x + bar_width // 2:
                        hovering_point = True
                        break

            if hovering_point:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release - stop dragging"""
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self.drag_point_type = None
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get theme colors
        palette = QApplication.palette()
        window_color = palette.color(QPalette.Window)
        brightness = (window_color.red() * 0.299 +
                      window_color.green() * 0.587 +
                      window_color.blue() * 0.114)
        is_dark = brightness < 127

        # Calculate drawing area
        width = self.width()
        height = self.height()
        margin_top = 40
        margin_bottom = 20
        bar_width = 30
        # Center the bar with room for labels on both sides
        bar_x = 120

        # Draw travel bar background (vertical) - use theme colors
        bar_bg = palette.color(QPalette.AlternateBase)
        bar_border = palette.color(QPalette.Mid)
        text_color = palette.color(QPalette.Text)

        # Get theme accent colors for press/release
        press_color = palette.color(QPalette.Highlight)
        release_color = palette.color(QPalette.Link)

        painter.setBrush(bar_bg)
        painter.setPen(QPen(bar_border, 2))
        painter.drawRect(bar_x, margin_top, bar_width, height - margin_top - margin_bottom)

        # Calculate bar height for vertical positioning
        bar_height = height - margin_top - margin_bottom

        # Draw deadzone fills (light grey) - shown in all modes
        deadzone_color = QColor(128, 128, 128, 80)  # Light grey with transparency

        # Top deadzone (deadzone_bottom is 0-51, representing 0-0.8mm = 20% of 4mm)
        if self.deadzone_bottom > 0:
            deadzone_bottom_percent = (self.deadzone_bottom / 51.0) * 20.0  # 0-51 maps to 0-20% (0.8mm of 4mm)
            deadzone_bottom_height = int(bar_height * deadzone_bottom_percent / 100.0)
            painter.fillRect(bar_x, margin_top, bar_width, deadzone_bottom_height, deadzone_color)

            # Draw "Top Deadzone" label
            font_small = QFont()
            font_small.setPointSize(7)
            painter.setFont(font_small)

            label_text = "Top Deadzone"
            label_x = bar_x + bar_width + 5
            label_y = margin_top + deadzone_bottom_height // 2 - 6

            if is_dark:
                label_bg = palette.color(QPalette.Window).darker(110)
                label_border = palette.color(QPalette.Mid)
            else:
                label_bg = palette.color(QPalette.Base)
                label_border = palette.color(QPalette.Mid)

            fm = painter.fontMetrics()
            text_width = fm.width(label_text)
            text_height = fm.height()
            padding = 2

            painter.fillRect(label_x - padding, label_y - padding,
                           text_width + 2 * padding, text_height + 2 * padding, label_bg)
            painter.setPen(QPen(label_border, 1))
            painter.drawRect(label_x - padding, label_y - padding,
                           text_width + 2 * padding, text_height + 2 * padding)

            painter.setPen(text_color)
            painter.drawText(label_x, label_y + text_height - 4, label_text)

        # Bottom deadzone (deadzone_top is 0-51, representing 0-0.8mm = 20% of 4mm)
        if self.deadzone_top > 0:
            deadzone_top_percent = (self.deadzone_top / 51.0) * 20.0  # 0-51 maps to 0-20% (0.8mm of 4mm)
            deadzone_top_height = int(bar_height * deadzone_top_percent / 100.0)
            deadzone_top_y = margin_top + bar_height - deadzone_top_height
            painter.fillRect(bar_x, deadzone_top_y, bar_width, deadzone_top_height, deadzone_color)

            # Draw "Bottom Deadzone" label
            font_small = QFont()
            font_small.setPointSize(7)
            painter.setFont(font_small)

            label_text = "Bottom Deadzone"
            label_x = bar_x + bar_width + 5
            label_y = deadzone_top_y + deadzone_top_height // 2 - 6

            if is_dark:
                label_bg = palette.color(QPalette.Window).darker(110)
                label_border = palette.color(QPalette.Mid)
            else:
                label_bg = palette.color(QPalette.Base)
                label_border = palette.color(QPalette.Mid)

            fm = painter.fontMetrics()
            text_width = fm.width(label_text)
            text_height = fm.height()
            padding = 2

            painter.fillRect(label_x - padding, label_y - padding,
                           text_width + 2 * padding, text_height + 2 * padding, label_bg)
            painter.setPen(QPen(label_border, 1))
            painter.drawRect(label_x - padding, label_y - padding,
                           text_width + 2 * padding, text_height + 2 * padding)

            painter.setPen(text_color)
            painter.drawText(label_x, label_y + text_height - 4, label_text)

        if self.rapidfire_mode:
            # Draw actuation line for "First Activation" at actual actuation point (0-255 range)
            actuation_y = margin_top + int((self.actuation_point / 255.0) * bar_height)
            painter.setPen(QPen(QColor(255, 200, 0), 2, Qt.DashLine))
            painter.drawLine(bar_x, actuation_y, bar_x + bar_width, actuation_y)

            # Draw "First Activation" label with button-like styling
            font = QFont()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)

            label_text = "First Activation"
            label_x = bar_x + bar_width + 15
            label_y = actuation_y - 10

            button_bg = palette.color(QPalette.Highlight)
            button_border = palette.color(QPalette.Highlight)

            fm = painter.fontMetrics()
            text_width = fm.width(label_text)
            text_height = fm.height()
            padding = 6

            painter.setPen(QPen(button_border, 1))
            painter.setBrush(button_bg)
            painter.drawRoundedRect(label_x - padding, label_y - padding,
                                   text_width + 2 * padding, text_height + 2 * padding, 6, 6)

            painter.setPen(palette.color(QPalette.HighlightedText))
            painter.drawText(label_x, actuation_y + 3, label_text)
        else:
            # Draw 0mm and 4.0mm labels (top and bottom) for normal mode
            painter.setPen(text_color)
            font = QFont()
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(bar_x + bar_width // 2 - 15, margin_top - 10, "0.0mm")
            painter.drawText(bar_x + bar_width // 2 - 15, height - margin_bottom + 15, "4.0mm")

        # Draw press and release actuation points
        if self.rapidfire_mode:
            # Rapidfire mode - actuation_point is 0-255 (0-4mm)
            actuation_y = margin_top + int((self.actuation_point / 255.0) * bar_height)

            # Draw release actuation points (theme release color, above actuation line)
            # Sensitivity values are in firmware 0-255 distance units (0-4.0mm)
            release_y = actuation_y
            for actuation, enabled in self.release_actuations:
                if not enabled:
                    continue

                # actuation is 0-255 firmware units, relative to actuation point
                y = actuation_y - int((actuation / 255.0) * bar_height)
                release_y = y

                painter.setPen(QPen(release_color, 3))
                painter.drawLine(bar_x + bar_width, y, bar_x + bar_width + 20, y)

                painter.setBrush(release_color)
                painter.drawEllipse(bar_x + bar_width + 18, y - 5, 10, 10)

                mm_value = (actuation / 255.0) * 4.0  # 0-255 maps to 0-4.0mm

                font_label = QFont()
                font_label.setPointSize(9)
                font_label.setBold(True)
                painter.setFont(font_label)

                fm = painter.fontMetrics()
                padding = 6
                label_x = bar_x + bar_width + 15

                button_bg = palette.color(QPalette.Button)
                button_border = palette.color(QPalette.Light)

                id_text = "Release Threshold"
                id_width = fm.width(id_text)
                id_height = fm.height()
                id_y = y - id_height - 10

                painter.setPen(QPen(button_border, 1))
                painter.setBrush(button_bg)
                painter.drawRoundedRect(label_x - padding, id_y - padding,
                                       id_width + 2 * padding, id_height + 2 * padding, 6, 6)
                painter.setPen(palette.color(QPalette.ButtonText))
                painter.drawText(label_x, id_y + id_height - 4, id_text)

                font_mm = QFont()
                font_mm.setPointSize(8)
                painter.setFont(font_mm)
                fm = painter.fontMetrics()

                mm_text = f"{mm_value:.2f}mm"
                mm_width = fm.width(mm_text)
                mm_height = fm.height()
                mm_y = y + 6

                painter.setPen(QPen(button_border, 1))
                painter.setBrush(palette.color(QPalette.AlternateBase))
                painter.drawRoundedRect(label_x - 4, mm_y - mm_height,
                                       mm_width + 8, mm_height + 4, 4, 4)
                painter.setPen(text_color)
                painter.drawText(label_x, mm_y, mm_text)

            # Draw press actuation points (theme press color, below release line)
            # Sensitivity values are in firmware 0-255 distance units (0-4.0mm)
            for actuation, enabled in self.press_actuations:
                if not enabled:
                    continue

                # actuation is 0-255 firmware units, relative to release point
                y = release_y + int((actuation / 255.0) * bar_height)

                painter.setPen(QPen(press_color, 3))
                painter.drawLine(bar_x - 20, y, bar_x, y)

                painter.setBrush(press_color)
                painter.drawEllipse(bar_x - 28, y - 5, 10, 10)

                mm_value = (actuation / 255.0) * 4.0  # 0-255 maps to 0-4.0mm

                font_label = QFont()
                font_label.setPointSize(9)
                font_label.setBold(True)
                painter.setFont(font_label)

                fm = painter.fontMetrics()
                padding = 6

                button_bg = palette.color(QPalette.Button)
                button_border = palette.color(QPalette.Light)

                id_text = "Press Threshold"
                id_width = fm.width(id_text)
                id_height = fm.height()
                label_x = bar_x - id_width - 15
                id_y = y - id_height - 10

                painter.setPen(QPen(button_border, 1))
                painter.setBrush(button_bg)
                painter.drawRoundedRect(label_x - padding, id_y - padding,
                                       id_width + 2 * padding, id_height + 2 * padding, 6, 6)
                painter.setPen(palette.color(QPalette.ButtonText))
                painter.drawText(label_x, id_y + id_height - 4, id_text)

                font_mm = QFont()
                font_mm.setPointSize(8)
                painter.setFont(font_mm)
                fm = painter.fontMetrics()

                mm_text = f"{mm_value:.2f}mm"
                mm_width = fm.width(mm_text)
                mm_height = fm.height()
                mm_x = bar_x - mm_width - 12
                mm_y = y + 6

                painter.setPen(QPen(button_border, 1))
                painter.setBrush(palette.color(QPalette.AlternateBase))
                painter.drawRoundedRect(mm_x - 4, mm_y - mm_height,
                                       mm_width + 8, mm_height + 4, 4, 4)
                painter.setPen(text_color)
                painter.drawText(mm_x, mm_y, mm_text)
        else:
            # Normal mode: draw from top to bottom with custom labels
            # Actuation values are 0-255 (0-4mm)
            font = QFont()
            font.setPointSize(9)

            # Draw press actuation points (theme press color, left side)
            for idx, (actuation, enabled) in enumerate(self.press_actuations):
                if not enabled:
                    continue

                # actuation is 0-255, representing 0-4mm
                y = margin_top + int((actuation / 255.0) * (height - margin_top - margin_bottom))

                painter.setPen(QPen(press_color, 3))
                painter.drawLine(bar_x - 20, y, bar_x, y)

                painter.setBrush(press_color)
                painter.drawEllipse(bar_x - 28, y - 5, 10, 10)

                mm_value = (actuation / 255.0) * 4.0  # 0-255 maps to 0-4mm

                font_label = QFont()
                font_label.setPointSize(9)
                font_label.setBold(True)
                painter.setFont(font_label)

                fm = painter.fontMetrics()
                padding = 6

                # Custom labels for Trigger Settings
                if self.label_mode == self.LABEL_MODE_GLOBAL:
                    # Global mode: "Normal Keys", "Midi Keys"
                    if idx == 0:
                        id_text = "Normal Keys"
                    elif idx == 1:
                        id_text = "Midi Keys"
                    else:
                        id_text = f"Actuation {idx + 1}"
                else:
                    # Per-key mode: just "Key actuation"
                    id_text = "Key actuation"

                id_width = fm.width(id_text)
                id_height = fm.height()
                label_x = bar_x - id_width - 15
                id_y = y - id_height - 10

                button_bg = palette.color(QPalette.Button)
                button_border = palette.color(QPalette.Light)

                painter.setPen(QPen(button_border, 1))
                painter.setBrush(button_bg)
                painter.drawRoundedRect(label_x - padding, id_y - padding,
                                       id_width + 2 * padding, id_height + 2 * padding, 6, 6)
                painter.setPen(palette.color(QPalette.ButtonText))
                painter.drawText(label_x, id_y + id_height - 4, id_text)

                font_mm = QFont()
                font_mm.setPointSize(8)
                painter.setFont(font_mm)
                fm = painter.fontMetrics()

                mm_text = f"{mm_value:.2f}mm"
                mm_width = fm.width(mm_text)
                mm_height = fm.height()
                mm_x = bar_x - mm_width - 12
                mm_y = y + 6

                painter.setPen(QPen(button_border, 1))
                painter.setBrush(palette.color(QPalette.AlternateBase))
                painter.drawRoundedRect(mm_x - 4, mm_y - mm_height,
                                       mm_width + 8, mm_height + 4, 4, 4)
                painter.setPen(text_color)
                painter.drawText(mm_x, mm_y, mm_text)

            # Draw release actuation points (theme release color, right side) - if any
            # Actuation values are 0-255 (0-4mm)
            for idx, (actuation, enabled) in enumerate(self.release_actuations):
                if not enabled:
                    continue

                # actuation is 0-255, representing 0-4mm
                y = margin_top + int((actuation / 255.0) * (height - margin_top - margin_bottom))

                painter.setPen(QPen(release_color, 3))
                painter.drawLine(bar_x + bar_width, y, bar_x + bar_width + 20, y)

                painter.setBrush(release_color)
                painter.drawEllipse(bar_x + bar_width + 18, y - 5, 10, 10)

                mm_value = (actuation / 255.0) * 4.0  # 0-255 maps to 0-4mm

                font_label = QFont()
                font_label.setPointSize(9)
                font_label.setBold(True)
                painter.setFont(font_label)

                fm = painter.fontMetrics()
                padding = 6
                label_x = bar_x + bar_width + 15

                button_bg = palette.color(QPalette.Button)
                button_border = palette.color(QPalette.Light)

                id_text = f"Release {idx + 1}"
                id_width = fm.width(id_text)
                id_height = fm.height()
                id_y = y - id_height - 10

                painter.setPen(QPen(button_border, 1))
                painter.setBrush(button_bg)
                painter.drawRoundedRect(label_x - padding, id_y - padding,
                                       id_width + 2 * padding, id_height + 2 * padding, 6, 6)
                painter.setPen(palette.color(QPalette.ButtonText))
                painter.drawText(label_x, id_y + id_height - 4, id_text)

                font_mm = QFont()
                font_mm.setPointSize(8)
                painter.setFont(font_mm)
                fm = painter.fontMetrics()

                mm_text = f"{mm_value:.2f}mm"
                mm_width = fm.width(mm_text)
                mm_height = fm.height()
                mm_y = y + 6

                painter.setPen(QPen(button_border, 1))
                painter.setBrush(palette.color(QPalette.AlternateBase))
                painter.drawRoundedRect(label_x - 4, mm_y - mm_height,
                                       mm_width + 8, mm_height + 4, 4, 4)
                painter.setPen(text_color)
                painter.drawText(label_x, mm_y, mm_text)


class TriggerSettingsTab(BasicEditor):
    """Per-key actuation settings editor"""

    def __init__(self, layout_editor):
        print("TriggerSettingsTab.__init__ called")
        super().__init__()

        self.layout_editor = layout_editor
        self.keyboard = None
        self.current_layer = 0
        self.syncing = False
        self.actuation_widget_ref = None  # Reference to QuickActuationWidget for synchronization
        self._needs_loading = False  # Flag for lazy loading - defer heavy HID calls until tab is opened

        # Track which tab is active (replaces hover_state)
        # Possible values: 'actuation', 'rapidfire', 'velocity'
        self.active_tab = 'actuation'
        self.showing_keymap = False  # Track if hovering over keyboard

        # Cache for per-key actuation values (70 keys × 12 layers)
        # Each key now stores 8 fields
        # Note: deadzone values are ALWAYS enabled (non-zero by default)
        self.per_key_values = []
        for layer in range(12):
            layer_keys = []
            for _ in range(70):
                layer_keys.append({
                    'actuation': 127,                   # 0-255 = 0-4.0mm, default 2.0mm (127/255 of 4mm)
                    'deadzone_top': 6,                  # 0-51 = 0-0.8mm (20% of 4mm), default ~0.1mm - FROM RIGHT
                    'deadzone_bottom': 6,               # 0-51 = 0-0.8mm (20% of 4mm), default ~0.1mm - FROM LEFT
                    'velocity_curve': 0,                # Articulation index: 0-22 factory, 23-72 user, 73-98 AT/CC
                    'flags': 0,                         # Bit 0: rapidfire_enabled, Bit 1: use_per_key_velocity_curve, Bit 2: continuous_rt
                    'rapidfire_press_sens': 6,          # 0-255 = 0-4.0mm, default ~0.1mm - FROM LEFT
                    'rapidfire_release_sens': 6,        # 0-255 = 0-4.0mm, default ~0.1mm - FROM RIGHT
                    'rapidfire_velocity_mod': 0         # -64 to +64, default 0
                })
            self.per_key_values.append(layer_keys)

        # Mode flags
        self.mode_enabled = False
        self.per_layer_enabled = False

        # Cache for layer actuation settings
        self.layer_data = []
        for _ in range(12):
            self.layer_data.append({
                'normal': 127,  # 2.0mm default (0-255 = 0-4.0mm, matches firmware scale)
                'midi': 127,    # 2.0mm default
                'velocity': 2,  # Velocity mode (0=Fixed, 1=Peak, 2=Speed, 3=Speed+Peak)
                'vel_speed': 10  # Velocity speed scale
            })

        # Track unsaved changes for global actuation settings
        self.has_unsaved_changes = False
        self.pending_layer_data = None  # Will store pending changes before save
        self.pending_per_key_keys = set()  # Track (layer, key_index) tuples with pending per-key changes

        # Null Bind state
        self.nullbind_protocol = None
        self.nullbind_groups = [NullBindGroup() for _ in range(NULLBIND_NUM_GROUPS)]
        self.current_nullbind_group = 0
        self.nullbind_pending_changes = False

        # Top bar with layer selection
        self.layout_layers = QHBoxLayout()
        self.layout_layers.setSpacing(6)  # Add spacing between layer buttons
        self.layout_size = QVBoxLayout()
        self.layout_size.setSpacing(6)  # Add spacing between size buttons
        layer_label = QLabel(tr("TriggerSettings", "Layer"))

        layout_labels_container = QHBoxLayout()
        layout_labels_container.addWidget(layer_label)
        layout_labels_container.addLayout(self.layout_layers)
        layout_labels_container.addStretch()
        layout_labels_container.addLayout(self.layout_size)

        # Keyboard display
        self.container = KeyboardWidget2(layout_editor)
        # Shade the whole selected key (not just the outline) on this tab.
        self.container.highlight_selected_fill = True
        self.container.clicked.connect(self.on_key_clicked)
        self.container.deselected.connect(self.on_key_deselected)
        self.container.installEventFilter(self)

        # Checkboxes for enable modes (will be placed left of keyboard)
        self.enable_checkbox = QCheckBox(tr("TriggerSettings", "Enable Per-Key Actuation"))
        self.enable_checkbox.setStyleSheet("QCheckBox { font-weight: bold; }")
        self.enable_checkbox.clicked.connect(self.on_enable_changed)

        self.per_layer_checkbox = QCheckBox(tr("TriggerSettings", "Enable Per-Layer Actuation"))
        self.per_layer_checkbox.setStyleSheet("QCheckBox { font-weight: bold; }")
        self.per_layer_checkbox.clicked.connect(self.on_per_layer_changed)

        # Selection buttons column (left of keyboard)
        selection_buttons_layout = QVBoxLayout()
        selection_buttons_layout.setSpacing(8)  # Add spacing between buttons

        self.select_all_btn = QPushButton(tr("TriggerSettings", "Select All"))
        self.select_all_btn.setMinimumHeight(32)  # Make buttons bigger
        self.select_all_btn.clicked.connect(self.on_select_all)
        selection_buttons_layout.addWidget(self.select_all_btn)

        self.unselect_all_btn = QPushButton(tr("TriggerSettings", "Unselect All"))
        self.unselect_all_btn.setMinimumHeight(32)  # Make buttons bigger
        self.unselect_all_btn.clicked.connect(self.on_unselect_all)
        selection_buttons_layout.addWidget(self.unselect_all_btn)

        self.invert_selection_btn = QPushButton(tr("TriggerSettings", "Invert Selection"))
        self.invert_selection_btn.setMinimumHeight(32)  # Make buttons bigger
        self.invert_selection_btn.clicked.connect(self.on_invert_selection)
        selection_buttons_layout.addWidget(self.invert_selection_btn)

        # Add layer management buttons to selection section
        self.copy_layer_btn = QPushButton(tr("TriggerSettings", "Copy from Layer..."))
        self.copy_layer_btn.setMinimumHeight(32)  # Make buttons bigger
        self.copy_layer_btn.setEnabled(False)
        self.copy_layer_btn.clicked.connect(self.on_copy_layer)
        selection_buttons_layout.addWidget(self.copy_layer_btn)

        self.copy_all_layers_btn = QPushButton(tr("TriggerSettings", "Copy Settings to All Layers"))
        self.copy_all_layers_btn.setMinimumHeight(32)  # Make buttons bigger
        self.copy_all_layers_btn.setEnabled(False)
        self.copy_all_layers_btn.clicked.connect(self.on_copy_to_all_layers)
        selection_buttons_layout.addWidget(self.copy_all_layers_btn)

        self.reset_btn = QPushButton(tr("TriggerSettings", "Reset All to Default"))
        self.reset_btn.setMinimumHeight(32)  # Make buttons bigger
        self.reset_btn.setEnabled(False)
        self.reset_btn.clicked.connect(self.on_reset_all)
        selection_buttons_layout.addWidget(self.reset_btn)

        self.save_btn = QPushButton(tr("TriggerSettings", "Save"))
        self.save_btn.setMinimumHeight(32)  # Make buttons bigger
        self.save_btn.setEnabled(False)
        self.save_btn.setStyleSheet("QPushButton:enabled { font-weight: bold; color: palette(highlight); }")
        self.save_btn.clicked.connect(self.on_save)
        selection_buttons_layout.addWidget(self.save_btn)

        selection_buttons_layout.addStretch()

        # Keyboard area with layer buttons
        keyboard_area = QVBoxLayout()
        keyboard_area.addLayout(layout_labels_container)

        keyboard_layout = QHBoxLayout()
        keyboard_layout.addStretch(1)  # Add spacer to center the buttons and keyboard
        keyboard_layout.addSpacing(15)  # Add left margin so buttons aren't against the wall
        keyboard_layout.addLayout(selection_buttons_layout)
        keyboard_layout.addSpacing(20)  # Add spacing between buttons and keyboard
        keyboard_layout.addWidget(self.container, 0, Qt.AlignTop)
        keyboard_layout.addStretch(1)
        keyboard_area.addLayout(keyboard_layout)
        keyboard_area.setContentsMargins(0, 0, 0, 0)  # Remove margins
        keyboard_area.setSpacing(0)  # Remove spacing
        keyboard_area.addStretch()  # Push keyboard to top to minimize gap

        w = ClickableWidget()
        w.setLayout(keyboard_area)
        w.clicked.connect(self.on_empty_space_clicked)

        # Wrap keyboard area in scroll area with max height
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setMaximumHeight(500)  # Set maximum height of 500 pixels
        scroll_area.setWidget(w)

        # Control panel at bottom
        control_panel = self.create_control_panel()

        self.layer_buttons = []
        self.device = None

        layout_editor.changed.connect(self.on_layout_changed)

        # Add widgets to BasicEditor layout (QVBoxLayout)
        self.addWidget(scroll_area)
        self.addWidget(control_panel)

    def eventFilter(self, obj, event):
        """Filter events to track hover state for keyboard widget"""
        if event.type() == QEvent.Enter:
            if obj == self.container:
                # Show keymap when hovering over keyboard
                self.showing_keymap = True
                self.refresh_layer_display()
        elif event.type() == QEvent.Leave:
            if obj == self.container:
                # Revert to tab-based display when leaving keyboard
                self.showing_keymap = False
                self.refresh_layer_display()

        return super().eventFilter(obj, event)

    def create_control_panel(self):
        """Create the bottom control panel"""
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setMaximumHeight(500)  # Increased to allow more expansion for rapidfire mode
        layout = QVBoxLayout()
        layout.setSpacing(3)
        layout.setContentsMargins(15, 3, 15, 8)

        # Create settings content directly (no tabs)
        settings_widget = self.create_settings_content()
        layout.addWidget(settings_widget)

        # Buttons moved to selection section, so removed from here

        panel.setLayout(layout)
        return panel

    def create_trigger_container(self):
        """Create the trigger travel configuration container"""
        container = QFrame()
        container.setFrameShape(QFrame.StyledPanel)
        container.setStyleSheet("QFrame { background-color: palette(base); }")
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # Global actuation widget (shown when per-key mode is disabled)
        self.global_actuation_widget = QWidget()
        global_actuation_layout = QVBoxLayout()
        global_actuation_layout.setSpacing(6)
        global_actuation_layout.setContentsMargins(0, 0, 0, 0)

        # Normal Keys Section
        normal_section_label = QLabel(tr("TriggerSettings", "Normal Keys"))
        normal_section_label.setStyleSheet("QLabel { font-weight: bold; font-size: 10pt; }")
        global_actuation_layout.addWidget(normal_section_label)

        # Normal Keys header with values
        normal_header = QHBoxLayout()
        self.global_normal_dz_min_value_label = QLabel(f"DZ: {self.deadzone_to_mm(6)}")
        self.global_normal_dz_min_value_label.setStyleSheet("QLabel { font-size: 8pt; }")
        normal_header.addWidget(self.global_normal_dz_min_value_label)
        normal_header.addStretch()
        self.global_normal_value_label = QLabel(f"Act: {self.value_to_mm(127)}")
        self.global_normal_value_label.setStyleSheet("QLabel { font-weight: bold; color: palette(highlight); }")
        normal_header.addWidget(self.global_normal_value_label)
        normal_header.addStretch()
        self.global_normal_dz_max_value_label = QLabel(f"DZ: {self.deadzone_to_mm(6)}")
        self.global_normal_dz_max_value_label.setStyleSheet("QLabel { font-size: 8pt; }")
        normal_header.addWidget(self.global_normal_dz_max_value_label)
        global_actuation_layout.addLayout(normal_header)

        # Normal Keys TriggerSlider (combines deadzone min, actuation, deadzone max)
        self.global_normal_slider = TriggerSlider(minimum=0, maximum=255)
        self.global_normal_slider.set_deadzone_bottom(6)  # ~0.1mm default
        self.global_normal_slider.set_actuation(127)      # 2.0mm default (127/255 of 4mm)
        self.global_normal_slider.set_deadzone_top(6)     # ~0.1mm default
        self.global_normal_slider.deadzoneBottomChanged.connect(self.on_global_normal_dz_min_changed)
        self.global_normal_slider.actuationChanged.connect(self.on_global_normal_changed)
        self.global_normal_slider.deadzoneTopChanged.connect(self.on_global_normal_dz_max_changed)
        self.global_normal_slider.setMinimumHeight(50)
        global_actuation_layout.addWidget(self.global_normal_slider)

        # Add separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.HLine)
        separator1.setFrameShadow(QFrame.Sunken)
        global_actuation_layout.addWidget(separator1)

        # MIDI Keys Section
        midi_section_label = QLabel(tr("TriggerSettings", "MIDI Keys"))
        midi_section_label.setStyleSheet("QLabel { font-weight: bold; font-size: 10pt; }")
        global_actuation_layout.addWidget(midi_section_label)

        # MIDI Keys header with values
        midi_header = QHBoxLayout()
        self.global_midi_dz_min_value_label = QLabel(f"DZ: {self.deadzone_to_mm(6)}")
        self.global_midi_dz_min_value_label.setStyleSheet("QLabel { font-size: 8pt; }")
        midi_header.addWidget(self.global_midi_dz_min_value_label)
        midi_header.addStretch()
        self.global_midi_value_label = QLabel(f"Act: {self.value_to_mm(127)}")
        self.global_midi_value_label.setStyleSheet("QLabel { font-weight: bold; color: palette(link); }")
        midi_header.addWidget(self.global_midi_value_label)
        midi_header.addStretch()
        self.global_midi_dz_max_value_label = QLabel(f"DZ: {self.deadzone_to_mm(6)}")
        self.global_midi_dz_max_value_label.setStyleSheet("QLabel { font-size: 8pt; }")
        midi_header.addWidget(self.global_midi_dz_max_value_label)
        global_actuation_layout.addLayout(midi_header)

        # MIDI Keys TriggerSlider (combines deadzone min, actuation, deadzone max)
        self.global_midi_slider = TriggerSlider(minimum=0, maximum=255)
        self.global_midi_slider.set_deadzone_bottom(6)  # ~0.1mm default
        self.global_midi_slider.set_actuation(127)      # 2.0mm default (127/255 of 4mm)
        self.global_midi_slider.set_deadzone_top(6)     # ~0.1mm default
        self.global_midi_slider.deadzoneBottomChanged.connect(self.on_global_midi_dz_min_changed)
        self.global_midi_slider.actuationChanged.connect(self.on_global_midi_changed)
        self.global_midi_slider.deadzoneTopChanged.connect(self.on_global_midi_dz_max_changed)
        self.global_midi_slider.setMinimumHeight(50)
        global_actuation_layout.addWidget(self.global_midi_slider)

        self.global_actuation_widget.setLayout(global_actuation_layout)
        self.global_actuation_widget.setVisible(True)
        layout.addWidget(self.global_actuation_widget)

        # Per-Key Trigger Travel widget
        self.per_key_actuation_widget = QWidget()
        per_key_layout = QVBoxLayout()
        per_key_layout.setSpacing(6)
        per_key_layout.setContentsMargins(0, 0, 0, 0)

        # Title
        title_label = QLabel("Trigger Travel")
        title_label.setStyleSheet("QLabel { font-weight: bold; font-size: 10pt; }")
        per_key_layout.addWidget(title_label)

        # Value display row
        values_layout = QHBoxLayout()

        # Deadzone bottom
        dz_bottom_container = QVBoxLayout()
        dz_bottom_title = QLabel("DZ Min")
        dz_bottom_title.setStyleSheet("QLabel { color: gray; font-size: 7pt; }")
        self.deadzone_bottom_value_label = QLabel(self.deadzone_to_mm(6))
        self.deadzone_bottom_value_label.setStyleSheet("QLabel { font-weight: bold; font-size: 9pt; }")
        dz_bottom_container.addWidget(dz_bottom_title, 0, Qt.AlignCenter)
        dz_bottom_container.addWidget(self.deadzone_bottom_value_label, 0, Qt.AlignCenter)
        values_layout.addLayout(dz_bottom_container)

        values_layout.addStretch()

        # Actuation
        actuation_container = QVBoxLayout()
        actuation_title = QLabel("Actuation")
        actuation_title.setStyleSheet("QLabel { color: gray; font-size: 7pt; }")
        self.actuation_value_label = QLabel(self.value_to_mm(127))
        self.actuation_value_label.setStyleSheet("QLabel { font-weight: bold; font-size: 10pt; color: palette(highlight); }")
        actuation_container.addWidget(actuation_title, 0, Qt.AlignCenter)
        actuation_container.addWidget(self.actuation_value_label, 0, Qt.AlignCenter)
        values_layout.addLayout(actuation_container)

        values_layout.addStretch()

        # Deadzone top
        dz_top_container = QVBoxLayout()
        dz_top_title = QLabel("DZ Max")
        dz_top_title.setStyleSheet("QLabel { color: gray; font-size: 7pt; }")
        self.deadzone_top_value_label = QLabel(self.deadzone_to_mm(6))
        self.deadzone_top_value_label.setStyleSheet("QLabel { font-weight: bold; font-size: 9pt; }")
        dz_top_container.addWidget(dz_top_title, 0, Qt.AlignCenter)
        dz_top_container.addWidget(self.deadzone_top_value_label, 0, Qt.AlignCenter)
        values_layout.addLayout(dz_top_container)

        per_key_layout.addLayout(values_layout)

        # Combined trigger slider
        self.trigger_slider = TriggerSlider(minimum=0, maximum=255)
        self.trigger_slider.setEnabled(False)
        self.trigger_slider.deadzoneBottomChanged.connect(self.on_deadzone_bottom_changed)
        self.trigger_slider.actuationChanged.connect(self.on_key_actuation_changed)
        self.trigger_slider.deadzoneTopChanged.connect(self.on_deadzone_top_changed)
        self.trigger_slider.setMinimumHeight(50)
        per_key_layout.addWidget(self.trigger_slider)

        self.per_key_actuation_widget.setLayout(per_key_layout)
        self.per_key_actuation_widget.setVisible(False)
        layout.addWidget(self.per_key_actuation_widget)

        # Add spacer to push everything to the top
        layout.addStretch()

        container.setLayout(layout)
        return container

    def create_rapidfire_container(self):
        """Create the rapidfire configuration container"""
        container = QFrame()
        container.setFrameShape(QFrame.StyledPanel)
        container.setStyleSheet("QFrame { background-color: palette(base); }")
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # Enable checkbox container for centering
        self.rapidfire_checkbox_container = QWidget()
        checkbox_container_layout = QVBoxLayout()
        checkbox_container_layout.setContentsMargins(0, 0, 0, 0)

        # Enable checkbox
        self.rapidfire_checkbox = QCheckBox(tr("TriggerSettings", "Enable RapidTrigger"))
        self.rapidfire_checkbox.setEnabled(False)
        self.rapidfire_checkbox.stateChanged.connect(self.on_rapidfire_toggled)
        # Make it bigger and bold when unchecked - will be updated in on_rapidfire_toggled
        self.rapidfire_checkbox.setStyleSheet("QCheckBox { font-size: 14pt; font-weight: bold; }")

        checkbox_container_layout.addStretch()
        checkbox_container_layout.addWidget(self.rapidfire_checkbox, 0, Qt.AlignCenter)
        checkbox_container_layout.addStretch()

        self.rapidfire_checkbox_container.setLayout(checkbox_container_layout)
        layout.addWidget(self.rapidfire_checkbox_container)

        # MIDI-note notice: the firmware never runs per-key Rapid Trigger on MIDI
        # note keys (they use velocity-based retrigger instead), so enabling it
        # there would silently do nothing. Shown/hidden per selected key.
        self.rf_midi_note_label = QLabel(tr("TriggerSettings",
            "Rapid Trigger is not available on MIDI note keys.\n"
            "They use velocity-based retrigger instead."))
        self.rf_midi_note_label.setWordWrap(True)
        self.rf_midi_note_label.setAlignment(Qt.AlignCenter)
        self.rf_midi_note_label.setStyleSheet("QLabel { color: palette(mid); font-style: italic; }")
        self.rf_midi_note_label.setVisible(False)
        layout.addWidget(self.rf_midi_note_label)

        # Rapidfire widget
        self.rf_widget = QWidget()
        rf_layout = QVBoxLayout()
        rf_layout.setSpacing(6)
        rf_layout.setContentsMargins(0, 0, 0, 0)

        # Title
        rf_title = QLabel("Rapid Trigger")
        rf_title.setStyleSheet("QLabel { font-weight: bold; font-size: 10pt; }")
        rf_layout.addWidget(rf_title)

        # Value display row
        rf_values_layout = QHBoxLayout()

        # Press sensitivity
        press_container = QVBoxLayout()
        press_title = QLabel("Press")
        press_title.setStyleSheet("QLabel { color: gray; font-size: 7pt; }")
        self.rf_press_value_label = QLabel(self.value_to_mm(6))
        self.rf_press_value_label.setStyleSheet("QLabel { font-weight: bold; font-size: 9pt; color: palette(highlight); }")
        press_container.addWidget(press_title, 0, Qt.AlignCenter)
        press_container.addWidget(self.rf_press_value_label, 0, Qt.AlignCenter)
        rf_values_layout.addLayout(press_container)

        rf_values_layout.addStretch()

        # Release sensitivity
        release_container = QVBoxLayout()
        release_title = QLabel("Release")
        release_title.setStyleSheet("QLabel { color: gray; font-size: 7pt; }")
        self.rf_release_value_label = QLabel(self.value_to_mm(6))
        self.rf_release_value_label.setStyleSheet("QLabel { font-weight: bold; font-size: 9pt; color: palette(link); }")
        release_container.addWidget(release_title, 0, Qt.AlignCenter)
        release_container.addWidget(self.rf_release_value_label, 0, Qt.AlignCenter)
        rf_values_layout.addLayout(release_container)

        rf_layout.addLayout(rf_values_layout)

        # Combined rapid trigger slider
        self.rapid_trigger_slider = RapidTriggerSlider(minimum=1, maximum=255)
        self.rapid_trigger_slider.setEnabled(False)
        self.rapid_trigger_slider.pressSensChanged.connect(self.on_rf_press_changed)
        self.rapid_trigger_slider.releaseSensChanged.connect(self.on_rf_release_changed)
        self.rapid_trigger_slider.setMinimumHeight(50)
        rf_layout.addWidget(self.rapid_trigger_slider)

        # Continuous mode checkbox
        self.continuous_rt_checkbox = QCheckBox(tr("TriggerSettings", "Continuous Rapid Trigger"))
        self.continuous_rt_checkbox.setToolTip(
            tr("TriggerSettings",
               "When enabled, rapid trigger only resets when the key is fully released.\n"
               "When disabled, rapid trigger resets when the key goes above the actuation point."))
        self.continuous_rt_checkbox.setEnabled(False)
        self.continuous_rt_checkbox.stateChanged.connect(self.on_continuous_rt_toggled)
        rf_layout.addWidget(self.continuous_rt_checkbox)

        rf_layout.addStretch()

        self.rf_widget.setLayout(rf_layout)
        self.rf_widget.setVisible(False)
        layout.addWidget(self.rf_widget)

        container.setLayout(layout)
        return container

    def create_nullbind_container(self):
        """Create the null bind (SOCD) configuration container"""
        container = QFrame()
        container.setFrameShape(QFrame.StyledPanel)
        container.setStyleSheet("QFrame { background-color: palette(base); }")
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header row with global enable toggle
        header_row = QHBoxLayout()
        header_label = QLabel(tr("TriggerSettings", "Null Bind (SOCD Handling)"))
        header_label.setStyleSheet("QLabel { font-weight: bold; font-size: 11pt; }")
        header_row.addWidget(header_label)
        header_row.addStretch()

        # Global enable/disable for all SOCD handling (persisted on the device).
        self.nullbind_enable_checkbox = QCheckBox(tr("TriggerSettings", "Enable SOCD"))
        self.nullbind_enable_checkbox.setChecked(True)
        self.nullbind_enable_checkbox.setToolTip(
            tr("TriggerSettings", "Master switch for all Null Bind / SOCD groups. "
               "When off, every group is inactive without having to clear it."))
        self.nullbind_enable_checkbox.stateChanged.connect(self.on_nullbind_enable_toggled)
        header_row.addWidget(self.nullbind_enable_checkbox)
        layout.addLayout(header_row)

        # --- Selected Keys box (live from the keyboard selection above) ---
        sel_frame = QFrame()
        sel_frame.setFrameShape(QFrame.StyledPanel)
        sel_frame.setStyleSheet("QFrame { background-color: palette(alternate-base); }")
        sel_layout = QVBoxLayout()
        sel_layout.setSpacing(6)
        sel_layout.setContentsMargins(8, 8, 8, 8)

        sel_header = QHBoxLayout()
        sel_title = QLabel(tr("TriggerSettings", "Selected Keys:"))
        sel_title.setStyleSheet("QLabel { font-weight: bold; }")
        sel_header.addWidget(sel_title)
        sel_header.addStretch()

        self.nullbind_selected_count_label = QLabel(tr("TriggerSettings", "0 keys"))
        self.nullbind_selected_count_label.setStyleSheet("QLabel { color: gray; }")
        sel_header.addWidget(self.nullbind_selected_count_label)
        sel_layout.addLayout(sel_header)

        self.nullbind_selected_display = QLabel(tr("TriggerSettings", "(No keys selected)"))
        self.nullbind_selected_display.setStyleSheet("QLabel { font-size: 10pt; padding: 8px; background: palette(base); border-radius: 4px; }")
        self.nullbind_selected_display.setWordWrap(True)
        self.nullbind_selected_display.setMinimumHeight(40)
        sel_layout.addWidget(self.nullbind_selected_display)

        sel_frame.setLayout(sel_layout)
        layout.addWidget(sel_frame)

        # --- Behavior selection row (authoring input for the group to Save) ---
        behavior_row = QHBoxLayout()
        behavior_row.setSpacing(10)

        behavior_label = QLabel(tr("TriggerSettings", "Behavior:"))
        behavior_label.setStyleSheet("QLabel { font-weight: bold; }")
        behavior_row.addWidget(behavior_label)

        self.nullbind_behavior_combo = QComboBox()
        self.nullbind_behavior_combo.setFixedWidth(200)
        self.nullbind_behavior_combo.currentIndexChanged.connect(self.on_nullbind_behavior_changed)
        behavior_row.addWidget(self.nullbind_behavior_combo)

        behavior_row.addStretch()
        layout.addLayout(behavior_row)

        # --- Active Layer row (authoring input; SOCD groups are layer-specific) ---
        layer_row = QHBoxLayout()
        layer_row.setSpacing(10)

        layer_label = QLabel(tr("TriggerSettings", "Active Layer:"))
        layer_label.setStyleSheet("QLabel { font-weight: bold; }")
        layer_row.addWidget(layer_label)

        self.nullbind_layer_combo = QComboBox()
        self.nullbind_layer_combo.addItem("All Layers", NULLBIND_LAYER_ALL)
        for i in range(12):
            self.nullbind_layer_combo.addItem(f"Layer {i + 1}", i)
        self.nullbind_layer_combo.currentIndexChanged.connect(self.on_nullbind_layer_changed)
        self.nullbind_layer_combo.setFixedWidth(120)
        layer_row.addWidget(self.nullbind_layer_combo)

        layer_hint = QLabel(tr("TriggerSettings", "(This group only activates on this layer)"))
        layer_hint.setStyleSheet("QLabel { color: gray; font-size: 9pt; }")
        layer_row.addWidget(layer_hint)

        layer_row.addStretch()
        layout.addLayout(layer_row)

        # --- Save / Overwrite buttons (above the Group Viewer) ---
        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.nullbind_save_btn = QPushButton(tr("TriggerSettings", "Save"))
        self.nullbind_save_btn.setMinimumHeight(30)
        self.nullbind_save_btn.setStyleSheet("QPushButton { font-weight: bold; color: palette(highlight); }")
        self.nullbind_save_btn.clicked.connect(self.on_nullbind_save)
        button_row.addWidget(self.nullbind_save_btn)

        self.nullbind_overwrite_btn = QPushButton(tr("TriggerSettings", "Overwrite"))
        self.nullbind_overwrite_btn.setMinimumHeight(30)
        self.nullbind_overwrite_btn.clicked.connect(self.on_nullbind_overwrite)
        button_row.addWidget(self.nullbind_overwrite_btn)

        button_row.addStretch()
        layout.addLayout(button_row)

        # --- Group Viewer box (browse/edit configured groups) ---
        gv_frame = QFrame()
        gv_frame.setFrameShape(QFrame.StyledPanel)
        gv_frame.setStyleSheet("QFrame { background-color: palette(alternate-base); }")
        gv_layout = QVBoxLayout()
        gv_layout.setSpacing(6)
        gv_layout.setContentsMargins(8, 8, 8, 8)

        gv_header = QHBoxLayout()
        gv_header.setSpacing(10)
        gv_group_label = QLabel(tr("TriggerSettings", "Group:"))
        gv_group_label.setStyleSheet("QLabel { font-weight: bold; }")
        gv_header.addWidget(gv_group_label)

        self.nullbind_group_combo = QComboBox()
        self.nullbind_group_combo.setFixedWidth(140)
        self.nullbind_group_combo.currentIndexChanged.connect(self.on_nullbind_group_changed)
        gv_header.addWidget(self.nullbind_group_combo)
        gv_header.addStretch()
        gv_layout.addLayout(gv_header)

        self.nullbind_group_view = QLabel(tr("TriggerSettings", "(No groups configured)"))
        self.nullbind_group_view.setStyleSheet("QLabel { font-size: 10pt; padding: 8px; background: palette(base); border-radius: 4px; }")
        self.nullbind_group_view.setWordWrap(True)
        self.nullbind_group_view.setMinimumHeight(56)
        gv_layout.addWidget(self.nullbind_group_view)

        clear_row = QHBoxLayout()
        self.nullbind_clear_btn = QPushButton(tr("TriggerSettings", "Clear Group"))
        self.nullbind_clear_btn.clicked.connect(self.on_nullbind_clear_group)
        self.nullbind_clear_btn.setMinimumHeight(28)
        clear_row.addWidget(self.nullbind_clear_btn)
        clear_row.addStretch()
        gv_layout.addLayout(clear_row)

        gv_frame.setLayout(gv_layout)
        layout.addWidget(gv_frame)

        # Behavior explanation
        self.nullbind_behavior_desc = QLabel("")
        self.nullbind_behavior_desc.setStyleSheet("QLabel { color: palette(text); font-size: 9pt; font-style: italic; padding: 4px; }")
        self.nullbind_behavior_desc.setWordWrap(True)
        layout.addWidget(self.nullbind_behavior_desc)

        layout.addStretch()

        container.setLayout(layout)

        # Initialize the group combo + live selection/behavior displays
        self.rebuild_nullbind_group_combo()
        self.update_socd_selected_display()
        self.update_nullbind_group_view()

        return container

    def create_settings_content(self):
        """Create the settings content with tabbed layout and visualization"""
        widget = QWidget()
        widget.setMaximumHeight(430)  # Set maximum height for entire container
        main_layout = QHBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(5, 3, 5, 5)

        # Left side: Tabbed settings container with checkboxes above
        left_container = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setSpacing(6)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Tabbed settings container
        tabs_container = QFrame()
        tabs_container.setFrameShape(QFrame.StyledPanel)
        tabs_container.setStyleSheet("QFrame { background-color: palette(alternate-base); }")
        tabs_layout = QVBoxLayout()
        tabs_layout.setSpacing(6)
        tabs_layout.setContentsMargins(10, 10, 10, 10)

        # Create tab widget
        self.settings_tabs = QTabWidget()
        self.settings_tabs.currentChanged.connect(self.on_tab_changed)

        # Actuation Tab
        actuation_tab = QWidget()
        actuation_layout = QHBoxLayout()
        actuation_layout.setContentsMargins(8, 8, 8, 8)
        actuation_layout.setSpacing(12)

        # Left side: Description with checkboxes
        actuation_desc_container = QWidget()
        actuation_desc_container.setFixedWidth(210)
        actuation_desc_layout = QVBoxLayout()
        actuation_desc_layout.setContentsMargins(0, 0, 0, 0)
        actuation_desc_title = QLabel(tr("TriggerSettings", "Actuation"))
        actuation_desc_title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        actuation_desc_layout.addWidget(actuation_desc_title)
        actuation_desc_text = QLabel(tr("TriggerSettings",
            "Set the key travel distance at which a keypress is registered. "
            "Adjust deadzones to prevent accidental presses."))
        actuation_desc_text.setWordWrap(True)
        actuation_desc_text.setStyleSheet("color: gray; font-size: 9pt;")
        actuation_desc_layout.addWidget(actuation_desc_text)

        actuation_desc_layout.addSpacing(10)

        # Per-Key checkbox with description
        actuation_desc_layout.addWidget(self.enable_checkbox)
        per_key_desc = QLabel(tr("TriggerSettings",
            "Per-Key: Each key can have its own actuation settings."))
        per_key_desc.setWordWrap(True)
        per_key_desc.setStyleSheet("color: gray; font-size: 8pt; margin-left: 18px;")
        actuation_desc_layout.addWidget(per_key_desc)

        actuation_desc_layout.addSpacing(5)

        # Per-Layer checkbox with description
        actuation_desc_layout.addWidget(self.per_layer_checkbox)
        per_layer_desc = QLabel(tr("TriggerSettings",
            "Per-Layer: Settings change based on the active keyboard layer."))
        per_layer_desc.setWordWrap(True)
        per_layer_desc.setStyleSheet("color: gray; font-size: 8pt; margin-left: 18px;")
        actuation_desc_layout.addWidget(per_layer_desc)

        actuation_desc_layout.addStretch()
        actuation_desc_container.setLayout(actuation_desc_layout)
        actuation_layout.addWidget(actuation_desc_container)

        # Right side: Controls
        self.trigger_container = self.create_trigger_container()
        actuation_layout.addWidget(self.trigger_container, 1)

        actuation_tab.setLayout(actuation_layout)
        self.settings_tabs.addTab(actuation_tab, "Actuation")

        # Rapidfire Tab
        rapidfire_tab = QWidget()
        rapidfire_layout = QHBoxLayout()
        rapidfire_layout.setContentsMargins(8, 8, 8, 8)
        rapidfire_layout.setSpacing(12)

        # Left side: Description with checkboxes
        rapidfire_desc_container = QWidget()
        rapidfire_desc_container.setFixedWidth(210)
        rapidfire_desc_layout = QVBoxLayout()
        rapidfire_desc_layout.setContentsMargins(0, 0, 0, 0)
        rapidfire_desc_title = QLabel(tr("TriggerSettings", "RapidTrigger"))
        rapidfire_desc_title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        rapidfire_desc_layout.addWidget(rapidfire_desc_title)
        rapidfire_desc_text = QLabel(tr("TriggerSettings",
            "Enable rapid key repeats based on key travel. "
            "Adjust press and release sensitivity thresholds."))
        rapidfire_desc_text.setWordWrap(True)
        rapidfire_desc_text.setStyleSheet("color: gray; font-size: 9pt;")
        rapidfire_desc_layout.addWidget(rapidfire_desc_text)

        rapidfire_desc_layout.addSpacing(10)

        # Per-Key checkbox with description
        self.rf_enable_checkbox = QCheckBox(tr("TriggerSettings", "Enable Per-Key Actuation"))
        self.rf_enable_checkbox.setStyleSheet("QCheckBox { font-weight: bold; }")
        self.rf_enable_checkbox.clicked.connect(self.on_enable_changed)
        rapidfire_desc_layout.addWidget(self.rf_enable_checkbox)
        rf_per_key_desc = QLabel(tr("TriggerSettings",
            "Per-Key: Each key can have its own RapidTrigger settings."))
        rf_per_key_desc.setWordWrap(True)
        rf_per_key_desc.setStyleSheet("color: gray; font-size: 8pt; margin-left: 18px;")
        rapidfire_desc_layout.addWidget(rf_per_key_desc)

        rapidfire_desc_layout.addSpacing(5)

        # Per-Layer checkbox with description
        self.rf_per_layer_checkbox = QCheckBox(tr("TriggerSettings", "Enable Per-Layer Actuation"))
        self.rf_per_layer_checkbox.setStyleSheet("QCheckBox { font-weight: bold; }")
        self.rf_per_layer_checkbox.clicked.connect(self.on_per_layer_changed)
        rapidfire_desc_layout.addWidget(self.rf_per_layer_checkbox)
        rf_per_layer_desc = QLabel(tr("TriggerSettings",
            "Per-Layer: Settings change based on the active keyboard layer."))
        rf_per_layer_desc.setWordWrap(True)
        rf_per_layer_desc.setStyleSheet("color: gray; font-size: 8pt; margin-left: 18px;")
        rapidfire_desc_layout.addWidget(rf_per_layer_desc)

        rapidfire_desc_layout.addStretch()
        rapidfire_desc_container.setLayout(rapidfire_desc_layout)
        rapidfire_layout.addWidget(rapidfire_desc_container)

        # Right side: Controls
        self.rapidfire_container = self.create_rapidfire_container()
        rapidfire_layout.addWidget(self.rapidfire_container, 1)

        rapidfire_tab.setLayout(rapidfire_layout)
        self.settings_tabs.addTab(rapidfire_tab, "RapidTrigger")

        # SOCD/Null Bind Tab
        nullbind_tab = QWidget()
        nullbind_layout = QHBoxLayout()
        nullbind_layout.setContentsMargins(8, 8, 8, 8)
        nullbind_layout.setSpacing(12)

        # Left side: Description with checkboxes
        nullbind_desc_container = QWidget()
        nullbind_desc_container.setFixedWidth(210)
        nullbind_desc_layout = QVBoxLayout()
        nullbind_desc_layout.setContentsMargins(0, 0, 0, 0)
        nullbind_desc_title = QLabel(tr("TriggerSettings", "SOCD/Null Bind"))
        nullbind_desc_title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        nullbind_desc_layout.addWidget(nullbind_desc_title)
        nullbind_desc_text = QLabel(tr("TriggerSettings",
            "Configure SOCD (Simultaneous Opposing Cardinal Directions) handling. "
            "Define how the keyboard resolves conflicting key presses. "
            "Each group is layer-specific - assign a layer where the group is active."))
        nullbind_desc_text.setWordWrap(True)
        nullbind_desc_text.setStyleSheet("color: gray; font-size: 9pt;")
        nullbind_desc_layout.addWidget(nullbind_desc_text)

        nullbind_desc_layout.addSpacing(10)

        # Per-Key checkbox with description
        self.nb_enable_checkbox = QCheckBox(tr("TriggerSettings", "Enable Per-Key Actuation"))
        self.nb_enable_checkbox.setStyleSheet("QCheckBox { font-weight: bold; }")
        self.nb_enable_checkbox.clicked.connect(self.on_enable_changed)
        nullbind_desc_layout.addWidget(self.nb_enable_checkbox)
        nb_per_key_desc = QLabel(tr("TriggerSettings",
            "Per-Key: Each key can have its own null bind settings."))
        nb_per_key_desc.setWordWrap(True)
        nb_per_key_desc.setStyleSheet("color: gray; font-size: 8pt; margin-left: 18px;")
        nullbind_desc_layout.addWidget(nb_per_key_desc)

        nullbind_desc_layout.addSpacing(5)

        # Per-Layer checkbox with description
        self.nb_per_layer_checkbox = QCheckBox(tr("TriggerSettings", "Enable Per-Layer Actuation"))
        self.nb_per_layer_checkbox.setStyleSheet("QCheckBox { font-weight: bold; }")
        self.nb_per_layer_checkbox.clicked.connect(self.on_per_layer_changed)
        nullbind_desc_layout.addWidget(self.nb_per_layer_checkbox)
        nb_per_layer_desc = QLabel(tr("TriggerSettings",
            "Per-Layer: Settings change based on the active keyboard layer."))
        nb_per_layer_desc.setWordWrap(True)
        nb_per_layer_desc.setStyleSheet("color: gray; font-size: 8pt; margin-left: 18px;")
        nullbind_desc_layout.addWidget(nb_per_layer_desc)

        nullbind_desc_layout.addStretch()
        nullbind_desc_container.setLayout(nullbind_desc_layout)
        nullbind_layout.addWidget(nullbind_desc_container)

        # Right side: Controls
        self.nullbind_container = self.create_nullbind_container()
        nullbind_layout.addWidget(self.nullbind_container, 1)

        nullbind_tab.setLayout(nullbind_layout)
        self.settings_tabs.addTab(nullbind_tab, "SOCD/Null Bind")

        tabs_layout.addWidget(self.settings_tabs)
        tabs_container.setLayout(tabs_layout)
        left_layout.addWidget(tabs_container)

        left_container.setLayout(left_layout)
        main_layout.addWidget(left_container, 2)

        # Right side: Visualization container (crossection + actuation visualizer)
        viz_container = QFrame()
        viz_container.setFrameShape(QFrame.StyledPanel)
        viz_container.setStyleSheet("QFrame { background-color: palette(base); }")
        viz_container.setMaximumHeight(325)  # Set maximum height for visualization container
        viz_container.setMaximumWidth(580)  # Max width for trigger settings
        viz_layout = QVBoxLayout()
        viz_layout.setContentsMargins(0, 10, 0, 10)  # Minimal horizontal margins
        viz_layout.setSpacing(0)  # No spacing

        # Import keyswitch diagram from dks_settings
        from editor.dks_settings import KeyswitchDiagramWidget

        # Horizontal layout for diagram and travel bar
        viz_h_layout = QHBoxLayout()
        viz_h_layout.setSpacing(0)  # No spacing between diagram and visualizer
        viz_h_layout.setContentsMargins(0, 0, 0, 0)

        # Keyswitch diagram
        self.keyswitch_diagram = KeyswitchDiagramWidget()
        viz_h_layout.addWidget(self.keyswitch_diagram)

        # Vertical travel bar - using TriggerVisualizerWidget for custom labels and dragging
        self.actuation_visualizer = TriggerVisualizerWidget()
        self.actuation_visualizer.actuationDragged.connect(self.on_visualizer_actuation_dragged)
        self.actuation_visualizer.pressSensDragged.connect(self.on_visualizer_press_sens_dragged)
        self.actuation_visualizer.releaseSensDragged.connect(self.on_visualizer_release_sens_dragged)
        viz_h_layout.addWidget(self.actuation_visualizer)

        viz_layout.addLayout(viz_h_layout)
        viz_layout.addStretch()

        viz_container.setLayout(viz_layout)
        main_layout.addWidget(viz_container, 1)

        widget.setLayout(main_layout)
        return widget

    def on_tab_changed(self, index):
        """Handle tab change - update active_tab and refresh display"""
        tab_names = ['actuation', 'rapidfire', 'nullbind']
        if index >= 0 and index < len(tab_names):
            self.active_tab = tab_names[index]
            # Sync checkbox states across all tabs when switching
            self.sync_all_tab_checkboxes()
            self.refresh_layer_display()
            self.update_actuation_visualizer()
            # Update null bind display when switching to that tab
            if self.active_tab == 'nullbind':
                self.update_nullbind_display()

    def update_actuation_visualizer(self):
        """Update the actuation visualizer based on current tab and selected key"""
        if not hasattr(self, 'actuation_visualizer'):
            return

        # Always show current layer's per-key values in the visualizer
        layer = self.current_layer

        # Get active key if selected
        if self.container.active_key and self.container.active_key.desc.row is not None:
            row, col = self.container.active_key.desc.row, self.container.active_key.desc.col
            key_index = row * 14 + col
            if key_index < 70:
                settings = self.per_key_values[layer][key_index]

                # Set label mode to per-key when a key is selected
                self.actuation_visualizer.set_label_mode(TriggerVisualizerWidget.LABEL_MODE_PER_KEY)

                # Build actuation points based on active tab
                if self.active_tab == 'actuation':
                    # Show actuation point and deadzones
                    press_points = [(settings['actuation'], True)]
                    # Deadzones aren't shown as separate actuation points in the visualizer
                    release_points = []
                    self.actuation_visualizer.set_actuations(
                        press_points, release_points, rapidfire_mode=False,
                        deadzone_top=settings['deadzone_top'],
                        deadzone_bottom=settings['deadzone_bottom'],
                        actuation_point=settings['actuation']
                    )
                elif self.active_tab == 'rapidfire':
                    # Show rapidfire press/release sensitivities if enabled
                    rapidfire_enabled = (settings['flags'] & 0x01) != 0
                    if rapidfire_enabled:
                        press_points = [(settings['rapidfire_press_sens'], True)]
                        release_points = [(settings['rapidfire_release_sens'], True)]
                    else:
                        press_points = []
                        release_points = []
                    # Pass deadzone and actuation values for visualization
                    self.actuation_visualizer.set_actuations(
                        press_points, release_points, rapidfire_mode=True,
                        deadzone_top=settings['deadzone_top'],
                        deadzone_bottom=settings['deadzone_bottom'],
                        actuation_point=settings['actuation']
                    )
                else:
                    press_points = []
                    release_points = []
                    self.actuation_visualizer.set_actuations(
                        press_points, release_points, rapidfire_mode=False,
                        deadzone_top=settings['deadzone_top'],
                        deadzone_bottom=settings['deadzone_bottom'],
                        actuation_point=settings['actuation']
                    )
                return

        # No key selected or in global mode - show global actuation
        if not self.mode_enabled:
            # Set label mode to global (Normal Keys, Midi Keys)
            self.actuation_visualizer.set_label_mode(TriggerVisualizerWidget.LABEL_MODE_GLOBAL)

            data_source = self.pending_layer_data if self.pending_layer_data else self.layer_data
            layer_to_use = self.current_layer if self.per_layer_enabled else 0

            if self.active_tab == 'actuation':
                # Show both normal and MIDI actuation points
                press_points = [
                    (data_source[layer_to_use]['normal'], True),
                    (data_source[layer_to_use]['midi'], True)
                ]
                release_points = []
                # Global mode doesn't have deadzones, pass 0
                self.actuation_visualizer.set_actuations(
                    press_points, release_points, rapidfire_mode=False,
                    deadzone_top=0, deadzone_bottom=0,
                    actuation_point=data_source[layer_to_use]['normal']
                )
            elif self.active_tab == 'rapidfire':
                # Show First Activation line using normal actuation in rapidfire mode
                # Rapidfire sensitivity controls not shown in global mode
                press_points = []
                release_points = []
                # Use normal actuation as the First Activation reference
                self.actuation_visualizer.set_actuations(
                    press_points, release_points, rapidfire_mode=True,
                    deadzone_top=0, deadzone_bottom=0,
                    actuation_point=data_source[layer_to_use]['normal']
                )
            else:
                # Velocity and other tabs in global mode
                press_points = []
                release_points = []
                self.actuation_visualizer.set_actuations(
                    press_points, release_points, rapidfire_mode=False,
                    deadzone_top=0, deadzone_bottom=0,
                    actuation_point=data_source[layer_to_use]['normal']
                )
        else:
            # Per-key mode but no key selected - clear visualizer
            self.actuation_visualizer.set_label_mode(TriggerVisualizerWidget.LABEL_MODE_PER_KEY)
            self.actuation_visualizer.set_actuations(
                [], [], rapidfire_mode=False,
                deadzone_top=0, deadzone_bottom=0, actuation_point=60
            )

    def value_to_mm(self, value):
        """Convert 0-255 value to millimeters string"""
        mm = (value / 255.0) * 4.0  # 0-255 maps to 0-4.0mm (full key travel)
        return f"{mm:.2f}mm"

    def on_global_normal_changed(self, value):
        """Handle global normal actuation slider change - updates all normal keys' per-key values"""
        self.global_normal_value_label.setText(f"Act: {self.value_to_mm(value)}")

        if self.syncing:
            return

        # Initialize pending data if not already
        if self.pending_layer_data is None:
            self.pending_layer_data = []
            for layer_data in self.layer_data:
                self.pending_layer_data.append(layer_data.copy())

        # Update pending_layer_data for current layer (or all layers if not per-layer)
        layer = self.current_layer

        if self.per_layer_enabled:
            # Update only current layer
            self.pending_layer_data[layer]['normal'] = value
        else:
            # Update all layers
            for i in range(12):
                self.pending_layer_data[i]['normal'] = value

        # Also update all normal keys' per-key actuation values
        self.apply_actuation_to_keys(is_midi=False, value=value)

        # Mark as having unsaved changes
        self.has_unsaved_changes = True
        self.save_btn.setEnabled(True)

        # Update display to show pending value
        self.refresh_layer_display()
        self.update_actuation_visualizer()

        # Sync to QuickActuationWidget if reference exists
        if self.actuation_widget_ref:
            aw = self.actuation_widget_ref
            aw.syncing = True
            aw.normal_slider.setValue(value)
            aw.normal_value_label.setText(f"{value / 255.0 * 4.0:.2f}mm")
            # Also sync the layer_data
            if self.per_layer_enabled:
                aw.layer_data[self.current_layer]['normal'] = value
            else:
                for i in range(12):
                    aw.layer_data[i]['normal'] = value
            aw.syncing = False

    def on_global_midi_changed(self, value):
        """Handle global MIDI actuation slider change - updates all MIDI keys' per-key values"""
        self.global_midi_value_label.setText(f"Act: {self.value_to_mm(value)}")

        if self.syncing:
            return

        # Initialize pending data if not already
        if self.pending_layer_data is None:
            self.pending_layer_data = []
            for layer_data in self.layer_data:
                self.pending_layer_data.append(layer_data.copy())

        # Update pending_layer_data for current layer (or all layers if not per-layer)
        layer = self.current_layer

        if self.per_layer_enabled:
            # Update only current layer
            self.pending_layer_data[layer]['midi'] = value
        else:
            # Update all layers
            for i in range(12):
                self.pending_layer_data[i]['midi'] = value

        # Also update all MIDI keys' per-key actuation values
        self.apply_actuation_to_keys(is_midi=True, value=value)

        # Mark as having unsaved changes
        self.has_unsaved_changes = True
        self.save_btn.setEnabled(True)

        # Update display to show pending value
        self.refresh_layer_display()
        self.update_actuation_visualizer()

        # Sync to QuickActuationWidget if reference exists
        if self.actuation_widget_ref:
            aw = self.actuation_widget_ref
            aw.syncing = True
            aw.midi_slider.setValue(value)
            aw.midi_value_label.setText(f"{value / 255.0 * 4.0:.2f}mm")
            # Also sync the layer_data
            if self.per_layer_enabled:
                aw.layer_data[self.current_layer]['midi'] = value
            else:
                for i in range(12):
                    aw.layer_data[i]['midi'] = value
            aw.syncing = False

    def apply_actuation_to_keys(self, is_midi, value):
        """Apply actuation value to all normal or MIDI keys based on keymap (local only, no HID)"""
        if not self.valid() or not self.keyboard:
            return

        # Get layers to update
        if self.per_layer_enabled:
            layers_to_update = [self.current_layer]
        else:
            layers_to_update = list(range(12))

        # Scan all keys and update matching type (local state only)
        for layer in layers_to_update:
            for key in self.container.widgets:
                if key.desc.row is not None:
                    row, col = key.desc.row, key.desc.col
                    key_index = row * 14 + col

                    if key_index < 70:
                        # Get the keycode for this key from the keymap
                        # Use 'layer' not 'current_layer' so each layer's keymap determines key type
                        keycode = self.keyboard.layout.get((layer, row, col), "KC_NO")

                        # Check if key type matches
                        key_is_midi = self.is_midi_keycode(keycode)
                        if key_is_midi == is_midi:
                            # Update the actuation value locally (HID sent on Save)
                            self.per_key_values[layer][key_index]['actuation'] = value
                            # Track that this key has pending changes
                            self.pending_per_key_keys.add((layer, key_index))

    def deadzone_to_mm(self, value):
        """Convert 0-51 deadzone value to millimeters string (20% of 4mm travel)"""
        mm = (value / 51.0) * 0.8  # 0-51 maps to 0-0.8mm (20% of 4mm)
        return f"{mm:.2f}mm"

    def on_global_normal_dz_min_changed(self, value):
        """Handle global normal keys deadzone min slider change"""
        self.global_normal_dz_min_value_label.setText(f"DZ: {self.deadzone_to_mm(value)}")

        if self.syncing:
            return

        # Apply deadzone_bottom to all normal keys
        self.apply_deadzone_to_keys(is_midi=False, is_min=True, value=value)
        self.save_btn.setEnabled(True)

    def on_global_normal_dz_max_changed(self, value):
        """Handle global normal keys deadzone max slider change"""
        self.global_normal_dz_max_value_label.setText(f"DZ: {self.deadzone_to_mm(value)}")

        if self.syncing:
            return

        # Apply deadzone_top to all normal keys
        self.apply_deadzone_to_keys(is_midi=False, is_min=False, value=value)
        self.save_btn.setEnabled(True)

    def on_global_midi_dz_min_changed(self, value):
        """Handle global MIDI keys deadzone min slider change"""
        self.global_midi_dz_min_value_label.setText(f"DZ: {self.deadzone_to_mm(value)}")

        if self.syncing:
            return

        # Apply deadzone_bottom to all MIDI keys
        self.apply_deadzone_to_keys(is_midi=True, is_min=True, value=value)
        self.save_btn.setEnabled(True)

    def on_global_midi_dz_max_changed(self, value):
        """Handle global MIDI keys deadzone max slider change"""
        self.global_midi_dz_max_value_label.setText(f"DZ: {self.deadzone_to_mm(value)}")

        if self.syncing:
            return

        # Apply deadzone_top to all MIDI keys
        self.apply_deadzone_to_keys(is_midi=True, is_min=False, value=value)
        self.save_btn.setEnabled(True)

    def apply_deadzone_to_keys(self, is_midi, is_min, value):
        """Apply deadzone value to all normal or MIDI keys (local only, no HID)"""
        if not self.valid() or not self.keyboard:
            return

        # Get layers to update
        if self.per_layer_enabled:
            layers_to_update = [self.current_layer]
        else:
            layers_to_update = list(range(12))

        # Scan all keys and update matching type (local state only)
        for layer in layers_to_update:
            for key in self.container.widgets:
                if key.desc.row is not None:
                    row, col = key.desc.row, key.desc.col
                    key_index = row * 14 + col

                    if key_index < 70:
                        # Get the keycode for this key from the keymap
                        # Use 'layer' not 'current_layer' so each layer's keymap determines key type
                        keycode = self.keyboard.layout.get((layer, row, col), "KC_NO")

                        # Check if key type matches
                        key_is_midi = self.is_midi_keycode(keycode)
                        if key_is_midi == is_midi:
                            # Update the appropriate deadzone value locally (HID sent on Save)
                            if is_min:
                                self.per_key_values[layer][key_index]['deadzone_bottom'] = value
                            else:
                                self.per_key_values[layer][key_index]['deadzone_top'] = value
                            # Track that this key has pending changes
                            self.pending_per_key_keys.add((layer, key_index))

        self.refresh_layer_display()
        self.update_actuation_visualizer()

    def _push_per_key_to_device(self, items):
        """Write per-key settings for each (layer, key_index) in `items` to the
        device, showing a modal progress dialog so the UI stays responsive during
        large batches (a layer-wide change enqueues up to 840 keys). Returns the
        set of (layer, key_index) that failed to write.
        """
        from PyQt5.QtWidgets import QProgressDialog
        items = list(items)
        if not (self.device and isinstance(self.device, VialKeyboard)):
            return set(items)

        failed = set()
        total = len(items)
        progress = None
        # Only bother with a dialog for large batches; small edits are instant.
        if total > 24:
            progress = QProgressDialog(
                tr("TriggerSettings", "Writing key settings to keyboard..."),
                None, 0, total, self.widget())
            progress.setWindowTitle(tr("TriggerSettings", "Saving"))
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(300)
            progress.setCancelButton(None)  # not safely cancellable mid-batch

        try:
            for i, (layer, key_index) in enumerate(items):
                settings = self.per_key_values[layer][key_index]
                if not self.device.keyboard.set_per_key_actuation(layer, key_index, settings):
                    failed.add((layer, key_index))
                if progress is not None:
                    progress.setValue(i + 1)
                    QApplication.processEvents()
        finally:
            if progress is not None:
                progress.close()
        return failed

    def on_save(self):
        """Save pending global actuation and per-key changes to device

        NOTE: Layer-wide actuation changes are converted to per-key commands.
        The layer actuation HID command (0xCA) is no longer used for actuation
        because it conflicts with arpeggiator commands. Instead, when the user
        changes layer-wide actuation, apply_actuation_to_keys() adds all affected
        keys to pending_per_key_keys, and we send per-key commands (0xE0) for each.
        """
        has_layer_changes = self.has_unsaved_changes and self.pending_layer_data is not None
        has_per_key_changes = len(self.pending_per_key_keys) > 0
        has_nullbind_changes = self.nullbind_pending_changes

        if not has_layer_changes and not has_per_key_changes and not has_nullbind_changes:
            return

        # If the initial per-key read from the device failed, per_key_values holds
        # substituted defaults, not the device's real config. Saving now (a
        # layer-wide change enqueues every key) would overwrite the real config
        # with defaults. Refuse and offer a re-read instead. (Null-bind changes use
        # an independent protocol and are unaffected, so only guard when there are
        # actuation/per-key changes to write.)
        if (has_layer_changes or has_per_key_changes) and not getattr(self, '_per_key_read_ok', True):
            ret = QMessageBox.warning(
                None, tr("TriggerSettings", "Reading from keyboard failed"),
                tr("TriggerSettings",
                   "Per-key settings could not be read from the keyboard, so the "
                   "values shown are defaults. Saving now would overwrite the "
                   "keyboard's real settings.\n\nReload from the keyboard first?"),
                QMessageBox.Yes | QMessageBox.Cancel)
            if ret == QMessageBox.Yes:
                self._load_per_key_data()
            return

        # Apply pending layer changes to local state
        if has_layer_changes:
            for i in range(12):
                self.layer_data[i]['normal'] = self.pending_layer_data[i]['normal']
                self.layer_data[i]['midi'] = self.pending_layer_data[i]['midi']
            # NOTE: Layer actuation HID command (0xCA) removed - conflicts with arpeggiator
            # Actuation is now per-key only. The apply_actuation_to_keys() function already
            # added all affected keys to pending_per_key_keys, so they'll be sent below.

        # Send pending per-key changes to device (includes layer-wide actuation changes)
        if has_per_key_changes and self.device and isinstance(self.device, VialKeyboard):
            # Disable the button up-front so a rapid double-click can't queue a
            # second overlapping batch of transfers; re-enabled in finally.
            self.save_btn.setEnabled(False)
            try:
                # set_per_key_actuation returns False (and swallows exceptions) when
                # the write does not reach the device (busy / unplugged). The old
                # code ignored the result and cleared the whole pending set, so a
                # failed save silently dropped those edits while the GUI reported
                # success and diverged from the device. (M16)
                failed = self._push_per_key_to_device(self.pending_per_key_keys)
                if failed:
                    # Keep the un-written keys pending and tell the user; do not clear.
                    self.pending_per_key_keys = failed
                    self.has_unsaved_changes = True
                    QMessageBox.warning(
                        None, tr("TriggerSettings", "Save incomplete"),
                        tr("TriggerSettings",
                           "{} changed key(s) could not be written to the keyboard and "
                           "remain unsaved. Check the connection and save again.").format(len(failed)))
                    return
            finally:
                # Re-enable if anything remains unsaved so the user can retry;
                # the full-success path disables it again below.
                self.save_btn.setEnabled(self.has_unsaved_changes or bool(self.pending_per_key_keys))

        # Also flush pending SOCD / Null Bind changes so the single "Save" button
        # persists everything on this tab (they otherwise had a separate button
        # and were silently left unsaved).
        if has_nullbind_changes:
            result = self._persist_nullbind_groups()
            if result != 'ok':
                self.has_unsaved_changes = True
                self.save_btn.setEnabled(True)
                QMessageBox.warning(
                    None, tr("TriggerSettings", "Save incomplete"),
                    tr("TriggerSettings",
                       "SOCD / Null Bind settings could not be written to the "
                       "keyboard and remain unsaved. Check the connection and save again."))
                return
            # (SOCD "Save" button stays always-enabled in the new model — it is the
            # "Save as New / Overwrite" trigger, not a pending-changes commit.)

        # Clear all unsaved changes flags
        self.has_unsaved_changes = False
        self.pending_layer_data = None
        self.pending_per_key_keys.clear()
        self.save_btn.setEnabled(False)

        # After saving edits, unselect all keys so the next edit starts fresh.
        self.container.unselect_all()

    def on_empty_space_clicked(self):
        """Clicking off the keyboard (empty page area, not the mini-tab controls)
        unselects ALL keys, not just the active one."""
        self.container.unselect_all()

    def on_key_clicked(self):
        """Handle key click - load all per-key settings"""
        if self.container.active_key is None:
            return

        key = self.container.active_key
        if key.desc.row is None:
            # Encoder, not a key
            return

        row, col = key.desc.row, key.desc.col
        key_index = row * 14 + col

        if key_index >= 70:
            return

        # Always show/edit current layer's per-key settings
        layer = self.current_layer

        # Load all settings from cache
        settings = self.per_key_values[layer][key_index]
        self.syncing = True

        # Load trigger slider (actuation + deadzones)
        self.trigger_slider.set_deadzone_bottom(settings['deadzone_bottom'])
        self.trigger_slider.set_actuation(settings['actuation'])
        self.trigger_slider.set_deadzone_top(settings['deadzone_top'])

        # Update labels
        self.deadzone_bottom_value_label.setText(self.deadzone_to_mm(settings['deadzone_bottom']))
        self.actuation_value_label.setText(self.value_to_mm(settings['actuation']))
        self.deadzone_top_value_label.setText(self.deadzone_to_mm(settings['deadzone_top']))

        # Load rapidfire settings (extract bit 0 from flags)
        rapidfire_enabled = (settings['flags'] & 0x01) != 0
        self.rapidfire_checkbox.setChecked(rapidfire_enabled)

        # Load rapid trigger slider
        self.rapid_trigger_slider.set_press_sens(settings['rapidfire_press_sens'])
        self.rapid_trigger_slider.set_release_sens(settings['rapidfire_release_sens'])
        self.rf_press_value_label.setText(self.value_to_mm(settings['rapidfire_press_sens']))
        self.rf_release_value_label.setText(self.value_to_mm(settings['rapidfire_release_sens']))

        # Load continuous rapid trigger checkbox (extract bit 2 from flags)
        continuous_rt = (settings['flags'] & 0x04) != 0
        self.continuous_rt_checkbox.setChecked(continuous_rt)

        self.syncing = False

        # Rapid Trigger only runs on non-MIDI keys in firmware. For MIDI note
        # keys, disable the RT controls and show a notice so the user isn't
        # misled into thinking RT is active where it does nothing.
        key_is_midi = self._key_index_is_midi(row, col)
        self.rf_midi_note_label.setVisible(key_is_midi)

        # Enable controls when key is selected
        key_selected = self.container.active_key is not None
        self.trigger_slider.setEnabled(key_selected and self.mode_enabled)
        self.rapidfire_checkbox.setEnabled(key_selected and not key_is_midi)
        self.rapid_trigger_slider.setEnabled(key_selected and rapidfire_enabled and not key_is_midi)
        self.rf_widget.setVisible(rapidfire_enabled and not key_is_midi)
        self.continuous_rt_checkbox.setEnabled(key_selected and rapidfire_enabled and not key_is_midi)

        # Update actuation visualizer
        self.update_actuation_visualizer()

        # Keep the SOCD "Selected Keys" box live with the current selection
        self.update_socd_selected_display()

    def on_key_deselected(self):
        """Handle key deselection - disable all controls"""
        self.trigger_slider.setEnabled(False)
        self.rapidfire_checkbox.setEnabled(False)
        self.rapid_trigger_slider.setEnabled(False)
        self.continuous_rt_checkbox.setEnabled(False)
        self.rf_widget.setVisible(False)
        if hasattr(self, 'rf_midi_note_label'):
            self.rf_midi_note_label.setVisible(False)

        # Update actuation visualizer
        self.update_actuation_visualizer()

        # Keep the SOCD "Selected Keys" box live with the current selection
        self.update_socd_selected_display()

    def save_current_key_settings(self):
        """Helper to save current key's settings to device"""
        if not self.container.active_key or self.container.active_key.desc.row is None:
            return

        row = self.container.active_key.desc.row
        col = self.container.active_key.desc.col
        key_index = row * 14 + col

        if key_index >= 70:
            return

        # Always use current layer's settings
        layer = self.current_layer
        settings = self.per_key_values[layer][key_index]

        # Send to device
        if self.device and isinstance(self.device, VialKeyboard):
            self.device.keyboard.set_per_key_actuation(layer, key_index, settings)

        # Refresh display
        self.refresh_layer_display()

    def _edit_layers(self):
        """Layers a per-key edit applies to.

        With per-layer mode ON, edits touch only the current layer. With
        per-layer OFF, the same key position is updated on ALL 12 layers so
        the layers stay uniform.
        """
        if self.per_layer_enabled:
            return [self.current_layer]
        return list(range(12))

    def on_key_actuation_changed(self, value):
        """Handle key actuation slider value change - applies to all selected keys"""
        self.actuation_value_label.setText(self.value_to_mm(value))

        if self.syncing or not self.mode_enabled:
            return

        # Get all selected keys (or just active key if none selected)
        selected_keys = self.container.get_selected_keys()
        if not selected_keys and self.container.active_key:
            selected_keys = [self.container.active_key]

        # Apply to all selected keys
        for key in selected_keys:
            if key.desc.row is not None:
                row, col = key.desc.row, key.desc.col
                key_index = row * 14 + col

                if key_index < 70:
                    for layer in self._edit_layers():
                        self.per_key_values[layer][key_index]['actuation'] = value
                        # Track for deferred save (no immediate HID)
                        self.pending_per_key_keys.add((layer, key_index))

        # Mark as having unsaved changes
        self.has_unsaved_changes = True
        self.save_btn.setEnabled(True)
        self.refresh_layer_display()

    def on_deadzone_top_changed(self, value):
        """Handle top deadzone slider change - applies to all selected keys"""
        self.deadzone_top_value_label.setText(self.deadzone_to_mm(value))

        if self.syncing:
            return

        # Get all selected keys (or just active key if none selected)
        selected_keys = self.container.get_selected_keys()
        if not selected_keys and self.container.active_key:
            selected_keys = [self.container.active_key]

        # Apply to all selected keys
        for key in selected_keys:
            if key.desc.row is not None:
                row, col = key.desc.row, key.desc.col
                key_index = row * 14 + col

                if key_index < 70:
                    for layer in self._edit_layers():
                        self.per_key_values[layer][key_index]['deadzone_top'] = value
                        # Track for deferred save (no immediate HID)
                        self.pending_per_key_keys.add((layer, key_index))

        # Mark as having unsaved changes
        self.has_unsaved_changes = True
        self.save_btn.setEnabled(True)

        self.refresh_layer_display()
        self.update_actuation_visualizer()

    def on_deadzone_bottom_changed(self, value):
        """Handle bottom deadzone slider change - applies to all selected keys"""
        self.deadzone_bottom_value_label.setText(self.deadzone_to_mm(value))

        if self.syncing:
            return

        # Get all selected keys (or just active key if none selected)
        selected_keys = self.container.get_selected_keys()
        if not selected_keys and self.container.active_key:
            selected_keys = [self.container.active_key]

        # Apply to all selected keys
        for key in selected_keys:
            if key.desc.row is not None:
                row, col = key.desc.row, key.desc.col
                key_index = row * 14 + col

                if key_index < 70:
                    for layer in self._edit_layers():
                        self.per_key_values[layer][key_index]['deadzone_bottom'] = value
                        # Track for deferred save (no immediate HID)
                        self.pending_per_key_keys.add((layer, key_index))

        # Mark as having unsaved changes
        self.has_unsaved_changes = True
        self.save_btn.setEnabled(True)
        self.refresh_layer_display()
        self.update_actuation_visualizer()

    def on_rapidfire_toggled(self, state):
        """Handle rapidfire checkbox toggle"""
        enabled = (state == Qt.Checked)

        # Update checkbox styling based on state
        if enabled:
            # When checked: normal size, left-aligned
            self.rapidfire_checkbox.setStyleSheet("QCheckBox { font-size: 9pt; font-weight: normal; }")
            # Clear the checkbox container layout and re-add without centering
            for i in reversed(range(self.rapidfire_checkbox_container.layout().count())):
                item = self.rapidfire_checkbox_container.layout().itemAt(i)
                if item.widget():
                    item.widget().setParent(None)
                elif item.spacerItem():
                    self.rapidfire_checkbox_container.layout().removeItem(item)
            self.rapidfire_checkbox_container.layout().addWidget(self.rapidfire_checkbox)
        else:
            # When unchecked: bigger, bold, centered
            self.rapidfire_checkbox.setStyleSheet("QCheckBox { font-size: 14pt; font-weight: bold; }")
            # Clear and re-add with centering
            for i in reversed(range(self.rapidfire_checkbox_container.layout().count())):
                item = self.rapidfire_checkbox_container.layout().itemAt(i)
                if item.widget():
                    item.widget().setParent(None)
                elif item.spacerItem():
                    self.rapidfire_checkbox_container.layout().removeItem(item)
            self.rapidfire_checkbox_container.layout().addStretch()
            self.rapidfire_checkbox_container.layout().addWidget(self.rapidfire_checkbox, 0, Qt.AlignCenter)
            self.rapidfire_checkbox_container.layout().addStretch()

        if not self.syncing:
            # Show/hide rapidfire widget and enable sliders
            self.rf_widget.setVisible(enabled)
            self.rapid_trigger_slider.setEnabled(enabled)
            self.continuous_rt_checkbox.setEnabled(enabled)

            # Get all selected keys (or just active key if none selected)
            selected_keys = self.container.get_selected_keys()
            if not selected_keys and self.container.active_key:
                selected_keys = [self.container.active_key]

            # Apply to all selected keys
            for key in selected_keys:
                if key.desc.row is not None:
                    row, col = key.desc.row, key.desc.col
                    key_index = row * 14 + col

                    # Rapid Trigger has no effect on MIDI note keys in firmware,
                    # so don't set the (inert) flag on them.
                    if key_index < 70 and not self._key_index_is_midi(row, col):
                        for layer in self._edit_layers():
                            # Update flags field: set or clear bit 0
                            if enabled:
                                self.per_key_values[layer][key_index]['flags'] |= 0x01  # Set bit 0
                            else:
                                self.per_key_values[layer][key_index]['flags'] &= ~0x01  # Clear bit 0

                            # Track for deferred save (no immediate HID)
                            self.pending_per_key_keys.add((layer, key_index))

            # Mark as having unsaved changes
            self.has_unsaved_changes = True
            self.save_btn.setEnabled(True)
            self.refresh_layer_display()
            self.update_actuation_visualizer()

    def on_rf_press_changed(self, value):
        """Handle rapidfire press sensitivity slider change - applies to all selected keys"""
        self.rf_press_value_label.setText(self.value_to_mm(value))

        if self.syncing:
            return

        # Get all selected keys (or just active key if none selected)
        selected_keys = self.container.get_selected_keys()
        if not selected_keys and self.container.active_key:
            selected_keys = [self.container.active_key]

        # Apply to all selected keys
        for key in selected_keys:
            if key.desc.row is not None:
                row, col = key.desc.row, key.desc.col
                key_index = row * 14 + col

                if key_index < 70:
                    for layer in self._edit_layers():
                        self.per_key_values[layer][key_index]['rapidfire_press_sens'] = value
                        # Track for deferred save (no immediate HID)
                        self.pending_per_key_keys.add((layer, key_index))

        # Mark as having unsaved changes
        self.has_unsaved_changes = True
        self.save_btn.setEnabled(True)
        self.refresh_layer_display()
        self.update_actuation_visualizer()

    def on_rf_release_changed(self, value):
        """Handle rapidfire release sensitivity slider change - applies to all selected keys"""
        self.rf_release_value_label.setText(self.value_to_mm(value))

        if self.syncing:
            return

        # Get all selected keys (or just active key if none selected)
        selected_keys = self.container.get_selected_keys()
        if not selected_keys and self.container.active_key:
            selected_keys = [self.container.active_key]

        # Apply to all selected keys
        for key in selected_keys:
            if key.desc.row is not None:
                row, col = key.desc.row, key.desc.col
                key_index = row * 14 + col

                if key_index < 70:
                    for layer in self._edit_layers():
                        self.per_key_values[layer][key_index]['rapidfire_release_sens'] = value
                        # Track for deferred save (no immediate HID)
                        self.pending_per_key_keys.add((layer, key_index))

        # Mark as having unsaved changes
        self.has_unsaved_changes = True
        self.save_btn.setEnabled(True)
        self.refresh_layer_display()
        self.update_actuation_visualizer()

    def on_visualizer_actuation_dragged(self, point_index, value):
        """Handle actuation point dragged on the visualizer - updates corresponding sliders"""
        if self.syncing:
            return

        if not self.mode_enabled:
            # Global mode - update the appropriate slider based on point index
            if point_index == 0:
                # Normal Keys
                self.global_normal_slider.set_actuation(value)
            elif point_index == 1:
                # Midi Keys
                self.global_midi_slider.set_actuation(value)
        else:
            # Per-key mode - update the per-key actuation slider
            self.trigger_slider.set_actuation(value)

    def on_visualizer_press_sens_dragged(self, value):
        """Handle press threshold dragged on the visualizer in rapidfire mode"""
        if self.syncing:
            return

        # Update the rapid trigger slider's press sensitivity
        if hasattr(self, 'rapid_trigger_slider'):
            self.rapid_trigger_slider.set_press_sens(value)

    def on_visualizer_release_sens_dragged(self, value):
        """Handle release threshold dragged on the visualizer in rapidfire mode"""
        if self.syncing:
            return

        # Update the rapid trigger slider's release sensitivity
        if hasattr(self, 'rapid_trigger_slider'):
            self.rapid_trigger_slider.set_release_sens(value)

    def on_continuous_rt_toggled(self, state):
        """Handle continuous rapid trigger checkbox toggle - applies to all selected keys"""
        if self.syncing:
            return

        enabled = (state == Qt.Checked)

        # Get all selected keys (or just active key if none selected)
        selected_keys = self.container.get_selected_keys()
        if not selected_keys and self.container.active_key:
            selected_keys = [self.container.active_key]

        # Apply to all selected keys
        for key in selected_keys:
            if key.desc.row is not None:
                row, col = key.desc.row, key.desc.col
                key_index = row * 14 + col

                if key_index < 70:
                    for layer in self._edit_layers():
                        # Update flags field: set or clear bit 2
                        if enabled:
                            self.per_key_values[layer][key_index]['flags'] |= 0x04  # Set bit 2
                        else:
                            self.per_key_values[layer][key_index]['flags'] &= ~0x04  # Clear bit 2

                        # Track for deferred save (no immediate HID)
                        self.pending_per_key_keys.add((layer, key_index))

        # Mark as having unsaved changes
        self.has_unsaved_changes = True
        self.save_btn.setEnabled(True)
        self.refresh_layer_display()

    def send_layer_actuation(self, layer):
        """DEPRECATED: Layer actuation HID command removed.

        This function is no longer used because:
        1. Command 0xCA conflicts with arpeggiator (ARP_CMD_SET_NOTE)
        2. Firmware already uses per-key actuation exclusively
        3. Layer-wide changes are now sent as 70 per-key commands via apply_actuation_to_keys()

        Keeping this function for reference but it should not be called.
        """
        # DEPRECATED - do not use
        pass

    def _key_index_is_midi(self, row, col):
        """Return True if the key at (row, col) on the current layer is a MIDI note key.

        Firmware never runs per-key Rapid Trigger on MIDI note keys, so the GUI
        disables the RT controls for them.
        """
        if not self.keyboard or not hasattr(self.keyboard, 'layout'):
            return False
        keycode = self.keyboard.layout.get((self.current_layer, row, col), "KC_NO")
        return self.is_midi_keycode(keycode)

    def is_midi_keycode(self, keycode):
        """Check if a keycode is a MIDI note keycode (base, keysplit, or triplesplit)"""
        if not keycode or keycode == "KC_NO" or keycode == "KC_TRNS":
            return False

        # Check for MI_SPLIT_ (keysplit) and MI_SPLIT2_ (triplesplit) first
        if keycode.startswith("MI_SPLIT2_") or keycode.startswith("MI_SPLIT_"):
            # These are keysplit/triplesplit MIDI notes - check for note suffix
            # Format: MI_SPLIT_C, MI_SPLIT_Cs, MI_SPLIT_C_1, MI_SPLIT2_C, etc.
            if keycode.startswith("MI_SPLIT2_"):
                remaining = keycode[10:]  # After "MI_SPLIT2_"
            else:
                remaining = keycode[9:]   # After "MI_SPLIT_"

            # Check if it starts with a note letter (C, D, E, F, G, A, B)
            if remaining and remaining[0] in 'CDEFGAB':
                return True
            return False

        # Mod Press keys (MI_MOD_PRESS_*) are analog travel keys that map key
        # depth to a CC. They use per-key actuation/deadzone exactly like MIDI
        # note keys, so group them with MIDI so the MIDI actuation/deadzone
        # sliders (and per-key edits) reach them. Without this they fell into
        # the "Normal" bucket, so the MIDI deadzone slider silently skipped
        # them and they kept the default ~0.1mm deadzone.
        if keycode.startswith("MI_MOD_PRESS"):
            return True

        # Check for MI_ prefix (base MIDI notes like MI_C, MI_C_1, MI_Cs, etc.)
        if keycode.startswith("MI_"):
            # Filter out non-note MIDI keycodes (controls, channels, etc.)
            # Note keycodes are: MI_C, MI_Cs/MI_Db, MI_D, MI_Ds/MI_Eb, MI_E, MI_F, MI_Fs/MI_Gb,
            #                    MI_G, MI_Gs/MI_Ab, MI_A, MI_As/MI_Bb, MI_B
            # And their octave variants: MI_C_1, MI_C1, MI_C_2, MI_C2, etc.
            note_prefixes = ['MI_C', 'MI_D', 'MI_E', 'MI_F', 'MI_G', 'MI_A', 'MI_B']
            for prefix in note_prefixes:
                if keycode.startswith(prefix):
                    # Make sure it's actually a note (not MI_CH1, MI_CHORD, etc.)
                    remaining = keycode[len(prefix):]
                    if remaining == '' or remaining.startswith('s') or remaining.startswith('b'):
                        return True  # MI_C, MI_Cs, MI_Cb, MI_Db, etc.
                    if remaining.startswith('_') or remaining[0].isdigit():
                        return True  # MI_C_1, MI_C1, MI_Cs_1, etc.
            return False

        return False

    def apply_keymap_based_actuations(self):
        """Apply actuation and deadzone values to all layers based on each layer's keymap.

        This is called when per-layer mode is disabled or when per-key mode is disabled.
        It scans each layer's keymap and applies the appropriate normal or MIDI actuation
        and deadzone values based on whether each key is a MIDI key on that layer.

        This ensures that when using a single set of normal/MIDI values, each layer
        gets the correct actuation based on its own keymap configuration.
        """
        if not self.valid() or not self.keyboard:
            return

        # Safe defaults: 2.0mm actuation (50), 0.1mm deadzones (4)
        DEFAULT_ACTUATION = 127  # 2.0mm (127/255 of 4mm full travel)
        DEFAULT_DEADZONE = 6   # ~0.1mm (6/51 * 0.8mm)
        MIN_ACTUATION = 13     # 0.2mm minimum to prevent keyboard crash (13/255 * 4mm)

        # Get current layer actuation values (use as source for all layers)
        data_source = self.pending_layer_data if self.pending_layer_data else self.layer_data
        normal_actuation = data_source[self.current_layer]['normal']
        midi_actuation = data_source[self.current_layer]['midi']

        # Use safe defaults if values are too low (could crash keyboard)
        if normal_actuation < MIN_ACTUATION:
            normal_actuation = DEFAULT_ACTUATION
        if midi_actuation < MIN_ACTUATION:
            midi_actuation = DEFAULT_ACTUATION

        # Get deadzone values from the global sliders, with safe defaults
        normal_dz_bottom = self.global_normal_slider.get_deadzone_bottom()
        normal_dz_top = self.global_normal_slider.get_deadzone_top()
        midi_dz_bottom = self.global_midi_slider.get_deadzone_bottom()
        midi_dz_top = self.global_midi_slider.get_deadzone_top()

        # Ensure deadzones have safe minimum values
        if normal_dz_bottom < 1:
            normal_dz_bottom = DEFAULT_DEADZONE
        if normal_dz_top < 1:
            normal_dz_top = DEFAULT_DEADZONE
        if midi_dz_bottom < 1:
            midi_dz_bottom = DEFAULT_DEADZONE
        if midi_dz_top < 1:
            midi_dz_top = DEFAULT_DEADZONE

        # Apply to ALL 12 layers for uniformity (firmware always uses per-key per-layer)
        touched = []
        for layer in range(12):
            # Scan all keys in the keymap and assign actuation values
            for key in self.container.widgets:
                if key.desc.row is not None:
                    row, col = key.desc.row, key.desc.col
                    key_index = row * 14 + col

                    if key_index < 70:
                        # Get the keycode for this key from the keymap
                        keycode = self.keyboard.layout.get((layer, row, col), "KC_NO")

                        # Determine actuation and deadzone values based on whether it's a MIDI key
                        if self.is_midi_keycode(keycode):
                            actuation_value = midi_actuation
                            dz_bottom = midi_dz_bottom
                            dz_top = midi_dz_top
                        else:
                            actuation_value = normal_actuation
                            dz_bottom = normal_dz_bottom
                            dz_top = normal_dz_top

                        # Update per-key values in memory (velocity_curve/flags untouched)
                        self.per_key_values[layer][key_index]['actuation'] = actuation_value
                        self.per_key_values[layer][key_index]['deadzone_bottom'] = dz_bottom
                        self.per_key_values[layer][key_index]['deadzone_top'] = dz_top
                        touched.append((layer, key_index))

        # Send to device via the responsive batched writer (up to 840 keys). This
        # replaces the old inline synchronous loop that froze the UI and saturated
        # the shared USB device with hundreds of back-to-back writes.
        self._push_per_key_to_device(touched)

        # Update layer_data with the safe values used, so global sliders show correct values
        for layer in range(12):
            self.layer_data[layer]['normal'] = normal_actuation
            self.layer_data[layer]['midi'] = midi_actuation

    def on_enable_changed(self, checked):
        """Handle enable checkbox toggle (connected to clicked signal, not stateChanged).

        Using clicked instead of stateChanged ensures this only fires on USER
        interaction, not programmatic setChecked() calls. This prevents re-entrancy
        issues where the confirmation dialog's modal event loop would process
        queued stateChanged signals and desync the checkbox state.

        NOTE: Firmware ALWAYS uses per-key per-layer settings. The checkboxes
        only control how the GUI sends values:
        - Per-key OFF + Per-layer OFF: Same value to all keys × all layers
        - Per-key OFF + Per-layer ON: Same value to all keys, different per layer
        - Per-key ON + Per-layer OFF: Per-key values, each edit written to that
          key position on ALL 12 layers
        - Per-key ON + Per-layer ON: Different values per key per layer
        """
        if self.syncing:
            return

        new_mode_enabled = checked

        # If user is disabling per-key mode, show confirmation dialog
        if self.mode_enabled and not new_mode_enabled:
            ret = QMessageBox.warning(
                self.widget(),
                tr("TriggerSettings", "Disable Per-Key Actuation"),
                tr("TriggerSettings", "Are you sure? You will lose all custom per-key values you have set.\n\n"
                   "The system will automatically assign actuation values based on your keymap:\n"
                   "- Normal keys will use the 'Normal Keys' actuation value\n"
                   "- MIDI keys will use the 'MIDI Keys' actuation value"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if ret != QMessageBox.Yes:
                # User cancelled - revert all checkbox states (user may have clicked from any tab)
                self.sync_all_tab_checkboxes()
                return

            # User confirmed - apply keymap-based actuations before disabling
            self.apply_keymap_based_actuations()

        self.mode_enabled = new_mode_enabled

        # Per-layer stays independent of per-key: with per-layer OFF, per-key
        # edits are written to that key position on ALL 12 layers.

        # Sync all tab checkboxes to reflect the new state
        self.sync_all_tab_checkboxes()

        self.copy_layer_btn.setEnabled(self.mode_enabled)
        self.copy_all_layers_btn.setEnabled(self.mode_enabled)
        self.reset_btn.setEnabled(self.mode_enabled)

        # Toggle between global and per-key actuation sliders only
        self.global_actuation_widget.setVisible(not self.mode_enabled)
        self.per_key_actuation_widget.setVisible(self.mode_enabled)

        # Load appropriate values for the visible widget
        if not self.mode_enabled:
            # Load global actuation values
            self.load_global_actuation()

        # Update enabled state of trigger slider when in per-key mode
        if self.mode_enabled:
            key_selected = self.container.active_key is not None
            self.trigger_slider.setEnabled(key_selected)

        # NOTE: set_per_key_mode is deprecated - firmware always uses per-key per-layer
        # The call is kept for backward compatibility but is a no-op
        if self.device and isinstance(self.device, VialKeyboard):
            self.device.keyboard.set_per_key_mode(self.mode_enabled, self.per_layer_enabled)

        # Synchronize with Actuation Settings tab
        if self.actuation_widget_ref:
            self.actuation_widget_ref.syncing = True
            self.actuation_widget_ref.enable_per_key_checkbox.setChecked(self.mode_enabled)
            self.actuation_widget_ref.update_per_key_ui_state(self.mode_enabled)
            self.actuation_widget_ref.syncing = False

        self.refresh_layer_display()

    def update_slider_states(self):
        """Update slider visibility and checkbox state based on per-key mode"""
        # Toggle between global and per-key actuation sliders
        self.global_actuation_widget.setVisible(not self.mode_enabled)
        self.per_key_actuation_widget.setVisible(self.mode_enabled)

        # Sync all tab checkboxes to reflect current state
        self.sync_all_tab_checkboxes()

        # Update trigger slider enabled state when in per-key mode
        if self.mode_enabled:
            key_selected = self.container.active_key is not None
            self.trigger_slider.setEnabled(key_selected)

        # Sync with Actuation Settings tab if available
        if self.actuation_widget_ref:
            self.actuation_widget_ref.syncing = True
            self.actuation_widget_ref.enable_per_key_checkbox.setChecked(self.mode_enabled)
            self.actuation_widget_ref.update_per_key_ui_state(self.mode_enabled)
            self.actuation_widget_ref.syncing = False

    def sync_all_tab_checkboxes(self):
        """Sync all tab checkboxes to the shared mode_enabled and per_layer_enabled state.

        Each tab (Actuation, Rapidfire, SOCD/Null Bind) has its own checkbox
        widgets, but they all control the same shared state. This method ensures all
        checkboxes visually reflect the current state.

        Uses blockSignals to prevent re-entrant stateChanged signals when
        reverting checkbox state (e.g. after user cancels a confirmation dialog).
        """
        # Guard: checkboxes may not exist yet during early initialization
        if not hasattr(self, 'rf_enable_checkbox'):
            return

        self.syncing = True

        # Sync all per-key enable checkboxes (blockSignals prevents re-entrant issues)
        for cb in [self.enable_checkbox, self.rf_enable_checkbox, self.nb_enable_checkbox]:
            cb.blockSignals(True)
            cb.setChecked(self.mode_enabled)
            cb.blockSignals(False)

        # Sync all per-layer checkboxes
        for cb in [self.per_layer_checkbox, self.rf_per_layer_checkbox, self.nb_per_layer_checkbox]:
            cb.blockSignals(True)
            cb.setChecked(self.per_layer_enabled)
            cb.blockSignals(False)

        # Per-layer stays user-toggleable in BOTH modes: with per-key ON and
        # per-layer OFF, per-key edits apply to that key on ALL 12 layers.
        self.per_layer_checkbox.setEnabled(True)
        self.rf_per_layer_checkbox.setEnabled(True)
        self.nb_per_layer_checkbox.setEnabled(True)

        self.syncing = False

    def on_per_layer_changed(self, checked):
        """Handle per-layer checkbox toggle (connected to clicked signal, not stateChanged).

        NOTE: When per-layer is unchecked, changes to actuation settings are
        written to ALL 12 layers so they stay uniform — in global mode via the
        keymap-based appliers, in per-key mode via each per-key edit handler
        (the edited key position is updated on every layer).
        Firmware ALWAYS uses per-key per-layer - this checkbox controls GUI behavior.
        """
        if self.syncing:
            return

        new_per_layer_enabled = checked

        # If user is disabling per-layer mode, show confirmation dialog
        if self.per_layer_enabled and not new_per_layer_enabled:
            ret = QMessageBox.warning(
                self.widget(),
                tr("TriggerSettings", "Disable Per-Layer Actuation"),
                tr("TriggerSettings", "Are you sure? All 12 layers will be set to the same values.\n\n"
                   "The current layer's actuation values will be copied to all other layers."),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if ret != QMessageBox.Yes:
                # User cancelled - revert all checkbox states
                self.sync_all_tab_checkboxes()
                return

            # User confirmed - sync current layer to all layers
            self.sync_current_layer_to_all_layers()

        self.per_layer_enabled = new_per_layer_enabled

        # Sync all tab checkboxes to reflect the new state
        self.sync_all_tab_checkboxes()

        # NOTE: set_per_key_mode is deprecated - firmware always uses per-key per-layer
        # The call is kept for backward compatibility but is a no-op
        if self.device and isinstance(self.device, VialKeyboard):
            self.device.keyboard.set_per_key_mode(self.mode_enabled, self.per_layer_enabled)

        # Synchronize with Actuation Settings tab
        if self.actuation_widget_ref:
            self.actuation_widget_ref.syncing = True
            self.actuation_widget_ref.per_layer_checkbox.setChecked(self.per_layer_enabled)
            self.actuation_widget_ref.syncing = False

        self.refresh_layer_display()

    def sync_current_layer_to_all_layers(self):
        """Sync current layer's per-key values to all 12 layers

        Called when per-layer is disabled to make all layers uniform.
        """
        if not self.device or not isinstance(self.device, VialKeyboard):
            return

        source_layer = self.current_layer

        # Copy from current layer to all other layers (in memory and on device)
        for dest_layer in range(12):
            if dest_layer == source_layer:
                continue

            # Copy in memory
            for key_index in range(70):
                self.per_key_values[dest_layer][key_index] = self.per_key_values[source_layer][key_index].copy()

            # Copy on device using the copy layer command
            self.device.keyboard.copy_layer_actuations(source_layer, dest_layer)

    def on_copy_layer(self):
        """Show dialog to copy actuations from another layer"""
        if not self.mode_enabled:
            return

        # Create simple combo box dialog
        msg = QMessageBox(self.widget())
        msg.setWindowTitle(tr("TriggerSettings", "Copy Layer"))
        msg.setText(tr("TriggerSettings", "Copy actuation settings from which layer?"))

        combo = QComboBox()
        for i in range(12):
            combo.addItem(f"Layer {i + 1}", i)
        combo.setCurrentIndex(0 if self.current_layer == 0 else 0)

        msg.layout().addWidget(combo, 1, 1)
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

        if msg.exec_() == QMessageBox.Ok:
            source_layer = combo.currentData()
            dest_layer = self.current_layer

            # Copy in memory (deep copy of dicts)
            for key_index in range(70):
                self.per_key_values[dest_layer][key_index] = self.per_key_values[source_layer][key_index].copy()

            # Copy on device
            if self.device and isinstance(self.device, VialKeyboard):
                self.copy_layer_btn.setEnabled(False)
                try:
                    self.device.keyboard.copy_layer_actuations(source_layer, dest_layer)
                finally:
                    self.copy_layer_btn.setEnabled(self.mode_enabled)

            self.refresh_layer_display()

    def on_copy_to_all_layers(self):
        """Copy current layer's per-key settings to all layers"""
        if not self.mode_enabled:
            return

        ret = QMessageBox.question(
            self.widget(),
            tr("TriggerSettings", "Copy to All Layers"),
            tr("TriggerSettings", f"Copy per-key settings from Layer {self.current_layer} to all layers?"),
            QMessageBox.Yes | QMessageBox.No
        )

        if ret == QMessageBox.Yes:
            source_layer = self.current_layer

            # Copy to all layers in memory and on device
            all_ok = True
            self.copy_all_layers_btn.setEnabled(False)
            try:
                for dest_layer in range(12):
                    if dest_layer != source_layer:
                        # Copy in memory (deep copy of dicts)
                        for key_index in range(70):
                            self.per_key_values[dest_layer][key_index] = self.per_key_values[source_layer][key_index].copy()

                        # Copy on device
                        if self.device and isinstance(self.device, VialKeyboard):
                            if not self.device.keyboard.copy_layer_actuations(source_layer, dest_layer):
                                all_ok = False
            finally:
                self.copy_all_layers_btn.setEnabled(self.mode_enabled)

            self.refresh_layer_display()
            if all_ok:
                QMessageBox.information(
                    self.widget(),
                    tr("TriggerSettings", "Copy Complete"),
                    tr("TriggerSettings", f"Per-key settings copied to all layers.")
                )
            else:
                QMessageBox.warning(
                    self.widget(),
                    tr("TriggerSettings", "Copy Incomplete"),
                    tr("TriggerSettings",
                       "Some layers could not be written to the keyboard. "
                       "Check the connection and try again.")
                )

    def on_reset_all(self):
        """Reset all actuation/deadzone/rapid-trigger settings to default.

        Per-key VELOCITY CURVES (set on the Velocity tab) are preserved — this
        button only resets the Trigger-Settings fields, so it does not silently
        wipe the user's velocity-curve assignments. The firmware's blanket reset
        command would clear velocity curves too, so we write the preserved values
        per key instead.
        """
        ret = QMessageBox.question(
            self.widget(),
            tr("TriggerSettings", "Reset All"),
            tr("TriggerSettings",
               "Reset actuation (2.0mm), deadzones and rapid trigger for all keys "
               "to default?\n\nPer-key articulation is kept."),
            QMessageBox.Yes | QMessageBox.No
        )

        if ret != QMessageBox.Yes:
            return

        # Reset the actuation-related fields in memory, PRESERVING each key's
        # velocity_curve and the per-key-velocity flag bit (bit 1).
        for layer in range(12):
            for key_index in range(70):
                existing = self.per_key_values[layer][key_index]
                self.per_key_values[layer][key_index] = {
                    'actuation': 127,                   # 2.0mm (127/255 of 4mm)
                    'deadzone_top': 6,                  # ~0.1mm from right
                    'deadzone_bottom': 6,               # ~0.1mm from left
                    'velocity_curve': existing.get('velocity_curve', 0),  # preserved
                    # Clear RT bits (0, 2) but keep the per-key-velocity flag (bit 1)
                    'flags': existing.get('flags', 0) & 0x02,
                    'rapidfire_press_sens': 6,          # ~0.1mm from left
                    'rapidfire_release_sens': 6,        # ~0.1mm from right
                    'rapidfire_velocity_mod': 0         # No modifier
                }

        # Write the reset values to the device per key (preserving velocity
        # curves). A progress dialog keeps the UI responsive for the 840 writes.
        if self.device and isinstance(self.device, VialKeyboard):
            self.reset_btn.setEnabled(False)
            try:
                items = [(layer, k) for layer in range(12) for k in range(70)]
                failed = self._push_per_key_to_device(items)
                if failed:
                    QMessageBox.warning(
                        self.widget(),
                        tr("TriggerSettings", "Reset Incomplete"),
                        tr("TriggerSettings",
                           "{} key(s) could not be written to the keyboard. "
                           "Check the connection and try again.").format(len(failed)))
            finally:
                self.reset_btn.setEnabled(self.mode_enabled)

        self.refresh_layer_display()

    def rebuild_layers(self):
        """Create layer selection buttons"""
        # Delete old buttons
        for btn in self.layer_buttons:
            btn.hide()
            btn.deleteLater()
        self.layer_buttons = []

        # Create layer buttons — 1-based labels + layer-name tooltips, matching
        # the keymap editor (and the rest of the GUI's 1-based layer numbering).
        from protocol.feature_names import get_feature_name_manager, FEATURE_LAYER
        mgr = get_feature_name_manager()
        for x in range(self.keyboard.layers):
            btn = SquareButton(str(x + 1))
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setRelSize(2.0)  # Increased from 1.667 to 2.0 for bigger buttons
            btn.setCheckable(True)
            btn.setToolTip(mgr.get_name(FEATURE_LAYER, x))
            btn.clicked.connect(lambda state, idx=x: self.switch_layer(idx))
            self.layout_layers.addWidget(btn)
            self.layer_buttons.append(btn)

        # Size adjustment buttons
        for x in range(0, 2):
            btn = SquareButton("-") if x else SquareButton("+")
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setRelSize(2.0)  # Increased from 1.667 to 2.0 for bigger buttons
            btn.setCheckable(False)
            btn.clicked.connect(lambda state, idx=x: self.adjust_size(idx))
            self.layout_size.addWidget(btn)
            self.layer_buttons.append(btn)

    def adjust_size(self, minus):
        """Adjust keyboard display size"""
        if minus:
            self.container.set_scale(self.container.get_scale() - 0.1)
        else:
            self.container.set_scale(self.container.get_scale() + 0.1)
        self.refresh_layer_display()

    def switch_layer(self, layer):
        """Switch to a different layer"""
        self.current_layer = layer
        for idx, btn in enumerate(self.layer_buttons[:self.keyboard.layers]):
            btn.setChecked(idx == layer)

        # Load layer data into controls
        self.load_layer_controls()

        self.refresh_layer_display()

    def load_layer_controls(self):
        """Load current layer's data into control widgets"""
        if not self.valid():
            return

        # Load global actuation values if per-key mode is disabled
        if not self.mode_enabled:
            self.load_global_actuation()

    def load_global_actuation(self):
        """Load global actuation values from layer_data"""
        if not self.valid():
            return

        self.syncing = True

        # Safe defaults: 2.0mm actuation (50)
        DEFAULT_ACTUATION = 127  # 2.0mm (127/255 of 4mm full travel)
        MIN_ACTUATION = 13      # 0.2mm minimum (13/255 * 4mm)

        # Get layer to use
        layer = self.current_layer

        # Use pending data if available, otherwise use saved data
        data_source = self.pending_layer_data if self.pending_layer_data else self.layer_data

        # Load normal actuation values using TriggerSlider methods
        normal_act = data_source[layer]['normal']
        if normal_act < MIN_ACTUATION:
            normal_act = DEFAULT_ACTUATION
        self.global_normal_slider.set_actuation(normal_act)
        self.global_normal_value_label.setText(f"Act: {self.value_to_mm(normal_act)}")

        # Load MIDI actuation values using TriggerSlider methods
        midi_act = data_source[layer]['midi']
        if midi_act < MIN_ACTUATION:
            midi_act = DEFAULT_ACTUATION
        self.global_midi_slider.set_actuation(midi_act)
        self.global_midi_value_label.setText(f"Act: {self.value_to_mm(midi_act)}")

        self.syncing = False

    def on_layout_changed(self):
        """Handle layout change from layout editor"""
        self.refresh_layer_display()

    def rebuild(self, device):
        """Rebuild UI with new device - uses lazy loading to defer heavy HID calls"""
        print(f"TriggerSettingsTab.rebuild() called with device={device}")
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard

            self.rebuild_layers()
            self.container.set_keys(self.keyboard.keys, self.keyboard.encoders)
            self.current_layer = 0

            # Load mode flags from device (quick, single call)
            mode_data = self.keyboard.get_per_key_mode()
            if mode_data:
                self.syncing = True
                self.mode_enabled = mode_data['mode_enabled']
                self.per_layer_enabled = mode_data['per_layer_enabled']
                self.enable_checkbox.setChecked(self.mode_enabled)
                self.per_layer_checkbox.setChecked(self.per_layer_enabled)
                # Enable mode-dependent buttons
                self.copy_layer_btn.setEnabled(self.mode_enabled)
                self.copy_all_layers_btn.setEnabled(self.mode_enabled)
                self.reset_btn.setEnabled(self.mode_enabled)
                self.syncing = False

            # Load per-key data immediately (optimized with bulk read + reduced retries)
            self._load_per_key_data()
            self._needs_loading = False

            # Clear any unsaved changes when loading from device
            self.has_unsaved_changes = False
            self.pending_layer_data = None
            self.save_btn.setEnabled(False)

            # Update slider states
            self.update_slider_states()

            # Load current layer data into controls (uses cached defaults until real data loads)
            self.load_layer_controls()

            self.refresh_layer_display()

            # Initialize null bind protocol and load groups
            self.nullbind_protocol = ProtocolNullBind(self.keyboard)
            try:
                self.load_nullbind_groups()
            except Exception as e:
                print(f"Error loading null bind groups: {e}")
                # Reset to empty groups on error
                self.nullbind_groups = [NullBindGroup() for _ in range(NULLBIND_NUM_GROUPS)]

        self.container.setEnabled(self.valid())

    def activate(self):
        """Called when tab is selected - load heavy data if needed"""
        if self._needs_loading and self.keyboard:
            self._load_per_key_data()
            self._needs_loading = False

    def deactivate(self):
        """Called when the user switches away from this tab.

        Everything on this tab (actuation / rapid trigger / deadzone AND SOCD /
        Null Bind) is saved through the one "Save" button, so warn before the
        edits are silently lost on navigation and offer to save them.
        """
        if not self.valid():
            return
        has_pending = (self.has_unsaved_changes
                       or bool(self.pending_per_key_keys)
                       or self.nullbind_pending_changes)
        if not has_pending:
            return
        ret = QMessageBox.question(
            self.widget(),
            tr("TriggerSettings", "Unsaved Changes"),
            tr("TriggerSettings",
               "You have unsaved trigger/SOCD changes. Save them to the keyboard now?"),
            QMessageBox.Save | QMessageBox.Discard,
            QMessageBox.Save)
        if ret == QMessageBox.Save:
            self.on_save()

    def _load_per_key_data(self):
        """Load all per-key actuation data from device"""
        print("TriggerSettingsTab: Loading per-key data...")

        # Tracks whether the values now in per_key_values reflect the device.
        # If a read fails we substitute defaults for display, but those must NOT
        # be saved back (a layer-wide actuation change enqueues ALL keys, which
        # would then overwrite the device's real per-key config with defaults).
        self._per_key_read_ok = True

        # Try bulk read first (much faster - 12 calls instead of 840)
        bulk_success = False
        if hasattr(self.keyboard, 'get_all_per_key_actuations'):
            print("  Attempting bulk read (12 layer reads)...")
            try:
                bulk_success = True
                for layer in range(12):
                    layer_data = self.keyboard.get_all_per_key_actuations(layer)
                    # Pace the connect burst: each bulk layer read pulls ~24 HID
                    # packets back. Firing all 12 back-to-back saturates the shared
                    # USB device, which starves the MIDI IN endpoint and stalls the
                    # firmware's blocking MIDI send (audible looper glitch on connect).
                    # A few ms between reads lets the device drain MIDI between bursts.
                    time.sleep(CONNECT_READ_PACING_S)
                    if layer_data and len(layer_data) == 70:
                        for key_index, settings in enumerate(layer_data):
                            self.per_key_values[layer][key_index] = settings
                    else:
                        bulk_success = False
                        print(f"  Bulk read failed for layer {layer}, falling back to individual reads")
                        break
                if bulk_success:
                    print("  Bulk read successful!")
            except Exception as e:
                print(f"  Bulk read error: {e}, falling back to individual reads")
                bulk_success = False

        # Fall back to individual reads if bulk read not supported
        if not bulk_success:
            print("  Using individual reads (840 calls, reduced retries)...")
            communication_failed = False
            try:
                for layer in range(12):
                    for key_index in range(70):
                        settings = self.keyboard.get_per_key_actuation(layer, key_index)
                        if settings is not None:
                            self.per_key_values[layer][key_index] = settings
                        else:
                            communication_failed = True
                            break
                    if communication_failed:
                        break
                    # Progress indicator
                    if layer % 3 == 0:
                        print(f"    Layer {layer}/12 loaded...")
            except Exception as e:
                print(f"Error loading per-key actuations from device: {e}")
                communication_failed = True

            # If communication failed, set all keys to safe defaults
            if communication_failed:
                # Defaults are for DISPLAY ONLY — mark the read as failed so
                # on_save() refuses to persist them over the device's real config.
                self._per_key_read_ok = False
                print("Setting all keys to safe defaults: 0.1mm deadzones, 2.0mm actuation")
                for layer in range(12):
                    for key_index in range(70):
                        self.per_key_values[layer][key_index] = {
                            'actuation': 127,                   # 2.0mm (127/255 of 4mm)
                            'deadzone_top': 6,                  # ~0.1mm from right
                            'deadzone_bottom': 6,               # ~0.1mm from left
                            'velocity_curve': 0,                # Linear (firmware default)
                            'flags': 0,                         # All disabled
                            'rapidfire_press_sens': 6,          # ~0.1mm from left
                            'rapidfire_release_sens': 6,        # ~0.1mm from right
                            'rapidfire_velocity_mod': 0         # No modifier
                        }

        # Load layer actuation data from device (6 bytes per layer)
        try:
            for layer in range(12):
                data = self.keyboard.get_layer_actuation(layer)
                time.sleep(CONNECT_READ_PACING_S)  # pace burst (see _load_per_key_data note)
                if data:
                    self.layer_data[layer] = {
                        'normal': data['normal'],
                        'midi': data['midi'],
                        'velocity': data['velocity'],
                        'vel_speed': data['vel_speed']
                        # Removed: 'use_per_key_velocity_curve' - now per-key
                    }
        except Exception as e:
            print(f"Error loading layer actuations: {e}")

        # Refresh UI with loaded data
        self.load_layer_controls()
        self.refresh_layer_display()
        print("TriggerSettingsTab: Per-key data loading complete")

    def valid(self):
        """Check if device is valid"""
        result = isinstance(self.device, VialKeyboard)
        print(f"TriggerSettingsTab.valid() called: device={self.device}, result={result}")
        return result

    def refresh_layer_display(self):
        """Refresh keyboard display based on active tab and hover state"""
        if not self.valid():
            return

        # Update layer button highlighting + keep tooltips in sync with names
        from protocol.feature_names import get_feature_name_manager, FEATURE_LAYER
        mgr = get_feature_name_manager()
        for idx, btn in enumerate(self.layer_buttons[:self.keyboard.layers]):
            btn.setChecked(idx == self.current_layer)
            btn.setToolTip(mgr.get_name(FEATURE_LAYER, idx))

        # Update keyboard key displays - always show current layer's per-key values
        # Even when per-layer is disabled, each layer has its own values based on keymap
        layer = self.current_layer

        # Use pending data if available, otherwise use saved data
        data_source = self.pending_layer_data if self.pending_layer_data else self.layer_data

        for key in self.container.widgets:
            if key.desc.row is not None:
                row, col = key.desc.row, key.desc.col
                key_index = row * 14 + col

                if key_index < 70:
                    # Get settings for this key
                    settings = self.per_key_values[layer][key_index]
                    rapidfire_enabled = (settings['flags'] & 0x01) != 0

                    # Default: clear mask text
                    key.setMaskText("")

                    # Display content based on showing_keymap flag and active tab
                    if self.active_tab == 'nullbind':
                        # Null bind tab: ALWAYS show keycode legends (like the keymap),
                        # regardless of hover, and overlay group-membership highlight.
                        from PyQt5.QtWidgets import QApplication
                        palette = QApplication.palette()
                        if self.keyboard and hasattr(self.keyboard, 'layout'):
                            code = self.keyboard.layout.get((self.current_layer, row, col), "KC_NO")
                            KeycodeDisplay.display_keycode(key, code)
                        else:
                            key.setText("")
                            key.setColor(None)
                        # Overlay group-membership highlight on top of the legend
                        group_idx, is_priority = self.get_key_nullbind_group(key_index)
                        if group_idx is not None:
                            if group_idx == self.current_nullbind_group:
                                if is_priority:
                                    key.setColor(palette.color(QPalette.Highlight))  # Priority key
                                else:
                                    key.setColor(palette.color(QPalette.Link))  # Normal group member
                            else:
                                key.setColor(palette.color(QPalette.Mid))  # Other group (dimmed)
                    elif self.showing_keymap:
                        # Hovering over keyboard: show keycodes like keymap tab
                        if self.keyboard and hasattr(self.keyboard, 'layout'):
                            code = self.keyboard.layout.get((self.current_layer, row, col), "KC_NO")
                            KeycodeDisplay.display_keycode(key, code)
                        else:
                            key.setText("")
                            key.setColor(None)
                    elif self.active_tab == 'rapidfire':
                        # Rapidfire tab: show press/release values or nothing
                        if rapidfire_enabled:
                            press_mm = self.value_to_mm(settings['rapidfire_press_sens'])
                            release_mm = self.value_to_mm(settings['rapidfire_release_sens'])
                            # Use same format as normal/midi display
                            key.setText(f"{press_mm}\n{release_mm}")
                            key.masked = False
                            key.setColor(None)
                        else:
                            key.setText("")
                            key.setColor(None)
                    else:  # self.active_tab == 'actuation'
                        # Actuation tab: always show per-key actuation value
                        # Get keycode to determine if this is a MIDI key
                        keycode = self.keyboard.layout.get((self.current_layer, row, col), "KC_NO") if self.keyboard else "KC_NO"
                        is_midi_key = self.is_midi_keycode(keycode)

                        # Color keys based on type and rapidfire state - use theme colors
                        from PyQt5.QtWidgets import QApplication
                        palette = QApplication.palette()
                        if rapidfire_enabled:
                            key.setColor(palette.color(QPalette.Highlight))  # Theme highlight for rapidfire
                        elif is_midi_key:
                            key.setColor(palette.color(QPalette.Link))  # Theme link color for MIDI keys
                        else:
                            key.setColor(None)  # Default for normal keys

                        # Always show per-key actuation value
                        key.setText(self.value_to_mm(settings['actuation']))
                else:
                    key.setText("")

        self.container.update()

    def on_select_all(self):
        """Handle Select All button click"""
        self.container.select_all()

    def on_unselect_all(self):
        """Handle Unselect All button click"""
        self.container.unselect_all()

    def on_invert_selection(self):
        """Handle Invert Selection button click"""
        self.container.invert_selection()

    # ========== Null Bind Methods ==========

    def get_key_label(self, key_index):
        """Get a human-readable label for a key index"""
        if not self.keyboard:
            return f"Key {key_index}"

        row = key_index // 14
        col = key_index % 14

        # Try to get the keycode from the current layer's keymap
        keycode = self.keyboard.layout.get((self.current_layer, row, col), "KC_NO")
        if keycode and keycode != "KC_NO" and keycode != "KC_TRNS":
            # Simplify keycode display
            if keycode.startswith("KC_"):
                return keycode[3:]
            elif keycode.startswith("MI_"):
                return keycode
            return keycode
        return f"R{row}C{col}"

    def _nullbind_selected_indices(self):
        """Return the sorted, de-duplicated key indices currently selected on the
        shared keyboard (capped to the per-group maximum)."""
        indices = []
        for key in self.container.get_selected_keys():
            if key.desc.row is not None:
                ki = key.desc.row * 14 + key.desc.col
                if ki < 70:
                    indices.append(ki)
        indices = sorted(set(indices))
        return indices[:NULLBIND_MAX_KEYS_PER_GROUP]

    def nullbind_group_count(self):
        """Number of configured (non-empty) null bind groups (kept packed at front)."""
        return sum(1 for g in self.nullbind_groups if len(g.keys) > 0)

    def persist_nullbind_to_device(self):
        """Write ALL null bind groups (and the global enable flag) to the device
        and EEPROM immediately."""
        if not self.nullbind_protocol:
            return
        self._persist_nullbind_groups()

    def _persist_nullbind_groups(self):
        """Send all null-bind groups to the keyboard and commit to EEPROM.

        Returns 'ok' on success, 'send' if a group failed to transmit, or
        'eeprom' if the EEPROM commit failed. No dialogs — callers decide how to
        report. Clears the pending flag on success.
        """
        if not self.nullbind_protocol:
            return 'send'
        # Push the global enable flag first (RAM only; committed by the EEPROM
        # save below). On firmware without the flag this is a harmless no-op.
        if hasattr(self, 'nullbind_enable_checkbox'):
            self.nullbind_protocol.set_enabled(self.nullbind_enable_checkbox.isChecked())
        for i, group in enumerate(self.nullbind_groups):
            if not self.nullbind_protocol.set_group(i, group):
                return 'send'
        if not self.nullbind_protocol.save_to_eeprom():
            return 'eeprom'
        self.nullbind_pending_changes = False
        return 'ok'

    def _nullbind_author_behavior(self):
        """Current authoring behavior value from the Behavior combo."""
        behavior = self.nullbind_behavior_combo.currentData()
        if behavior is None:
            behavior = NULLBIND_BEHAVIOR_NEUTRAL
        return behavior

    def _nullbind_author_layer(self):
        """Current authoring layer value from the Active Layer combo
        (may be NULLBIND_LAYER_ALL)."""
        layer = self.nullbind_layer_combo.currentData()
        if layer is None:
            layer = 0
        return layer

    def _nullbind_layer_label(self, layer):
        """Human-readable label for a group's stored layer value."""
        if layer == NULLBIND_LAYER_ALL:
            return "All Layers"
        return f"Layer {layer + 1}"

    def update_socd_selected_display(self):
        """Refresh the live "Selected Keys" box and the Behavior authoring choices
        from the current keyboard selection."""
        if not hasattr(self, 'nullbind_selected_display'):
            return
        # Keep it cheap: only do work while the SOCD tab is active.
        if getattr(self, 'active_tab', None) != 'nullbind':
            return

        indices = self._nullbind_selected_indices()
        count = len(indices)

        # Count + list
        self.nullbind_selected_count_label.setText(
            tr("TriggerSettings", "1 key") if count == 1 else tr("TriggerSettings", f"{count} keys"))
        if count == 0:
            self.nullbind_selected_display.setText(tr("TriggerSettings", "(No keys selected)"))
        else:
            labels = [self.get_key_label(ki) for ki in indices]
            self.nullbind_selected_display.setText(", ".join(labels))

        # Rebuild the Behavior choices to match the selection count, preserving the
        # current selection when it is still valid.
        current = self.nullbind_behavior_combo.currentData()
        self.nullbind_behavior_combo.blockSignals(True)
        self.nullbind_behavior_combo.clear()
        for value, name in get_behavior_choices(count):
            self.nullbind_behavior_combo.addItem(name, value)
        idx = self.nullbind_behavior_combo.findData(current) if current is not None else -1
        self.nullbind_behavior_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.nullbind_behavior_combo.blockSignals(False)

        self.update_nullbind_behavior_description()

    def update_nullbind_behavior_description(self):
        """Update the behavior description text (based on the live selection)."""
        behavior = self._nullbind_author_behavior()

        if behavior == NULLBIND_BEHAVIOR_NEUTRAL:
            desc = "When 2+ keys in this group are pressed simultaneously, all keys are nulled (no output)."
        elif behavior == NULLBIND_BEHAVIOR_LAST_INPUT:
            desc = "Only the last pressed key is active. Other keys in the group are nulled."
        elif behavior == NULLBIND_BEHAVIOR_DISTANCE:
            desc = "The key pressed furthest down (most travel) wins. Other keys are nulled."
        elif behavior >= NULLBIND_BEHAVIOR_PRIORITY_BASE:
            indices = self._nullbind_selected_indices()
            priority_idx = behavior - NULLBIND_BEHAVIOR_PRIORITY_BASE
            if priority_idx < len(indices):
                key_label = self.get_key_label(indices[priority_idx])
                desc = f"{key_label} has absolute priority. It cannot be nulled by other keys. Other keys are nulled when {key_label} is held, and activate when it releases."
            else:
                desc = ""
        else:
            desc = ""

        self.nullbind_behavior_desc.setText(desc)

    def update_nullbind_group_view(self):
        """Fill the read-only Group Viewer text for the current group."""
        if not hasattr(self, 'nullbind_group_view'):
            return
        count = self.nullbind_group_count()
        if count == 0:
            self.nullbind_group_view.setText(tr("TriggerSettings", "(No groups configured)"))
            return
        idx = self.current_nullbind_group
        if idx >= count:
            idx = count - 1
        group = self.nullbind_groups[idx]
        key_labels = [self.get_key_label(k) for k in group.keys]
        keys_str = ", ".join(key_labels) if key_labels else "(none)"
        behavior_str = get_behavior_name(group.behavior, len(group.keys))
        self.nullbind_group_view.setText(
            f"Keys: {keys_str}\nBehavior: {behavior_str}\nActive Layer: {self._nullbind_layer_label(group.layer)}")

    def rebuild_nullbind_group_combo(self):
        """Repopulate the Group Viewer combo with only configured groups."""
        if not hasattr(self, 'nullbind_group_combo'):
            return
        count = self.nullbind_group_count()
        self.nullbind_group_combo.blockSignals(True)
        self.nullbind_group_combo.clear()
        if count == 0:
            self.nullbind_group_combo.addItem(tr("TriggerSettings", "(No groups)"), -1)
            self.nullbind_group_combo.setEnabled(False)
            self.current_nullbind_group = 0
        else:
            self.nullbind_group_combo.setEnabled(True)
            for i in range(count):
                self.nullbind_group_combo.addItem(f"Group {i + 1}", i)
            if self.current_nullbind_group >= count:
                self.current_nullbind_group = count - 1
            self.nullbind_group_combo.setCurrentIndex(self.current_nullbind_group)
        self.nullbind_group_combo.blockSignals(False)

    def update_nullbind_display(self):
        """Refresh all SOCD widgets (combo, viewer, live selection box)."""
        self.rebuild_nullbind_group_combo()
        self.update_nullbind_group_view()
        self.update_socd_selected_display()

    def on_nullbind_group_changed(self, index):
        """Handle Group Viewer selection change - load that group into the live
        selection and authoring inputs for edit-in-place."""
        if index < 0:
            return
        data = self.nullbind_group_combo.currentData()
        if data is None or data < 0:
            return

        self.current_nullbind_group = data
        group = self.nullbind_groups[data]

        # Load the group's keys into the shared keyboard selection
        self.container.selected_keys = set()
        active = None
        for widget in self.container.widgets:
            if widget.desc.row is not None:
                ki = widget.desc.row * 14 + widget.desc.col
                if ki in group.keys:
                    self.container.selected_keys.add(widget)
                    active = widget
        self.container.active_key = active
        self.container.update()

        # Populate the authoring Active Layer combo from the stored group (select
        # by data since the combo leads with an "All Layers" row).
        self.nullbind_layer_combo.blockSignals(True)
        li = self.nullbind_layer_combo.findData(group.layer)
        self.nullbind_layer_combo.setCurrentIndex(li if li >= 0 else 0)
        self.nullbind_layer_combo.blockSignals(False)

        # Rebuild behavior choices for the loaded selection, then force the group's
        # stored behavior.
        self.update_socd_selected_display()
        self.nullbind_behavior_combo.blockSignals(True)
        bi = self.nullbind_behavior_combo.findData(group.behavior)
        self.nullbind_behavior_combo.setCurrentIndex(bi if bi >= 0 else 0)
        self.nullbind_behavior_combo.blockSignals(False)
        self.update_nullbind_behavior_description()

        self.update_nullbind_group_view()
        self.refresh_layer_display()

    def on_nullbind_behavior_changed(self, index):
        """Behavior combo change - authoring only; just refresh the description."""
        if index < 0:
            return
        self.update_nullbind_behavior_description()

    def on_nullbind_enable_toggled(self, state):
        """Handle the global SOCD enable checkbox (persists immediately)."""
        if self.syncing:
            return
        self.persist_nullbind_to_device()

    def on_nullbind_layer_changed(self, index):
        """Active Layer combo change - authoring only; applied on Save/Overwrite."""
        return

    def _nullbind_write_group(self, group_idx, indices):
        """Write the live selection + authoring behavior/layer into a group slot."""
        group = self.nullbind_groups[group_idx]
        group.keys = list(indices)
        group.behavior = self._nullbind_author_behavior()
        group.layer = self._nullbind_author_layer()

    def on_nullbind_save(self):
        """Save the current selection as a new group or overwrite an existing one."""
        indices = self._nullbind_selected_indices()
        if not indices:
            QMessageBox.information(
                self.widget(),
                tr("TriggerSettings", "No Keys Selected"),
                tr("TriggerSettings", "Please select keys on the keyboard above to save a group.")
            )
            return

        box = QMessageBox(self.widget())
        box.setWindowTitle(tr("TriggerSettings", "Save Null Bind Group"))
        box.setText(tr("TriggerSettings", "Do you wish to save as new or overwrite?"))
        new_btn = box.addButton(tr("TriggerSettings", "Save as New"), QMessageBox.AcceptRole)
        overwrite_btn = box.addButton(tr("TriggerSettings", "Overwrite"), QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.exec_()

        clicked = box.clickedButton()
        if clicked == new_btn:
            self._nullbind_save_as_new(indices)
        elif clicked == overwrite_btn:
            self.nullbind_overwrite_flow()

    def _nullbind_save_as_new(self, indices):
        """Create a new configured group at the end of the packed list."""
        count = self.nullbind_group_count()
        if count >= NULLBIND_NUM_GROUPS:
            QMessageBox.warning(
                self.widget(),
                tr("TriggerSettings", "Too Many Groups"),
                tr("TriggerSettings", "Maximum number of groups exceeded, please overwrite or remove other groups")
            )
            return

        new_idx = count
        self._nullbind_write_group(new_idx, indices)
        self.current_nullbind_group = new_idx

        self.persist_nullbind_to_device()
        self.rebuild_nullbind_group_combo()
        self.update_nullbind_group_view()
        self.update_socd_selected_display()
        self.refresh_layer_display()

    def on_nullbind_overwrite(self):
        """Overwrite button handler."""
        self.nullbind_overwrite_flow()

    def nullbind_overwrite_flow(self):
        """Replace an existing configured group (chosen by the user) with the
        current selection + authoring behavior/layer."""
        indices = self._nullbind_selected_indices()
        if not indices:
            QMessageBox.information(
                self.widget(),
                tr("TriggerSettings", "No Keys Selected"),
                tr("TriggerSettings", "Please select keys on the keyboard above to overwrite a group.")
            )
            return

        count = self.nullbind_group_count()
        if count == 0:
            QMessageBox.information(
                self.widget(),
                tr("TriggerSettings", "No Groups"),
                tr("TriggerSettings", "No groups to overwrite.")
            )
            return

        items = [f"Group {i + 1}" for i in range(count)]
        preselect = self.current_nullbind_group if self.current_nullbind_group < count else 0
        item, ok = QInputDialog.getItem(
            self.widget(),
            tr("TriggerSettings", "Overwrite Group"),
            tr("TriggerSettings", "Select group to overwrite:"),
            items, preselect, False
        )
        if not ok or not item:
            return

        target = items.index(item)
        self._nullbind_write_group(target, indices)
        self.current_nullbind_group = target

        self.persist_nullbind_to_device()
        self.rebuild_nullbind_group_combo()
        self.update_nullbind_group_view()
        self.update_socd_selected_display()
        self.refresh_layer_display()

    def on_nullbind_clear_group(self):
        """Delete the current group and pack the remaining groups down."""
        count = self.nullbind_group_count()
        if count == 0:
            return

        idx = self.current_nullbind_group
        if idx >= count:
            idx = count - 1

        ret = QMessageBox.question(
            self.widget(),
            tr("TriggerSettings", "Delete Group"),
            tr("TriggerSettings", f"Delete Group {idx + 1} and its keys?"),
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return

        # Delete + pack (append a fresh empty group to keep 20 fixed slots)
        del self.nullbind_groups[idx]
        self.nullbind_groups.append(NullBindGroup())

        new_count = self.nullbind_group_count()
        self.current_nullbind_group = min(idx, new_count - 1) if new_count > 0 else 0

        self.persist_nullbind_to_device()
        self.rebuild_nullbind_group_combo()
        self.update_nullbind_group_view()
        self.update_socd_selected_display()
        self.refresh_layer_display()

    def load_nullbind_groups(self):
        """Load null bind groups from keyboard, packing configured groups to the front."""
        if not self.nullbind_protocol:
            return

        loaded = []
        for i in range(NULLBIND_NUM_GROUPS):
            group = self.nullbind_protocol.get_group(i)
            loaded.append(group if group else NullBindGroup())

        # Keep configured (non-empty) groups packed at the front
        configured = [g for g in loaded if len(g.keys) > 0]
        self.nullbind_groups = configured + [
            NullBindGroup() for _ in range(NULLBIND_NUM_GROUPS - len(configured))
        ]
        self.current_nullbind_group = 0

        # Load the global enable flag (default to enabled if the firmware is too
        # old to answer, matching the firmware's own default).
        if hasattr(self, 'nullbind_enable_checkbox'):
            enabled = self.nullbind_protocol.get_enabled()
            self.nullbind_enable_checkbox.blockSignals(True)
            self.nullbind_enable_checkbox.setChecked(True if enabled is None else enabled)
            self.nullbind_enable_checkbox.blockSignals(False)

        self.nullbind_pending_changes = False

        self.rebuild_nullbind_group_combo()
        self.update_nullbind_group_view()
        self.update_socd_selected_display()

    def get_key_nullbind_group(self, key_index):
        """Find which null bind group a key belongs to

        Returns:
            (group_index, is_priority) or (None, False) if not in any group
        """
        for g_idx, group in enumerate(self.nullbind_groups):
            if group.has_key(key_index):
                is_priority = False
                if group.behavior >= NULLBIND_BEHAVIOR_PRIORITY_BASE:
                    priority_idx = group.behavior - NULLBIND_BEHAVIOR_PRIORITY_BASE
                    key_pos_in_group = group.keys.index(key_index)
                    is_priority = (key_pos_in_group == priority_idx)
                return (g_idx, is_priority)
        return (None, False)
