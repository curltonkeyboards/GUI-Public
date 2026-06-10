# SPDX-License-Identifier: GPL-2.0-or-later
"""
DKS (Dynamic Keystroke) Settings Editor

Allows configuration of multi-action analog keys with customizable actuation points.
Users configure DKS slots (DKS_00 - DKS_49) and then assign them to keys via the keymap editor.
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
                              QComboBox, QSlider, QGroupBox, QMessageBox, QFrame,
                              QSizePolicy, QCheckBox, QSpinBox, QScrollArea, QApplication, QTabWidget)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPalette, QPixmap, QImage

from editor.basic_editor import BasicEditor
from editor.arpeggiator import DebugConsole
from protocol.dks_protocol import (ProtocolDKS, DKSSlot, DKS_BEHAVIOR_TAP,
                                   DKS_BEHAVIOR_PRESS, DKS_BEHAVIOR_RELEASE,
                                   DKS_NUM_SLOTS, DKS_ACTIONS_PER_STAGE)
from keycodes.keycodes import Keycode
from widgets.key_widget import KeyWidget
from tabbed_keycodes import TabbedKeycodes
from vial_device import VialKeyboard
import widgets.resources  # Import Qt resources for switch crossection image


class DKSKeyWidget(KeyWidget):
    """Custom KeyWidget that doesn't open tray - parent will handle keycode selection"""

    selected = pyqtSignal(object)  # Emits self when clicked

    def __init__(self):
        super().__init__()
        self.is_selected = False

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


class TravelBarWidget(QWidget):
    """Visual representation of key travel with actuation points"""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(100)
        self.setMaximumHeight(140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.press_actuations = []      # List of (actuation_point, enabled) tuples
        self.release_actuations = []    # List of (actuation_point, enabled) tuples

    def set_actuations(self, press_points, release_points):
        """Set actuation points to display

        Args:
            press_points: List of (actuation, enabled) tuples for press actions
            release_points: List of (actuation, enabled) tuples for release actions
        """
        self.press_actuations = press_points
        self.release_actuations = release_points
        self.update()

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
        margin = 40
        bar_height = 30
        bar_y = (height - bar_height) // 2

        # Draw travel bar background - use theme colors
        bar_bg = palette.color(QPalette.AlternateBase)
        bar_border = palette.color(QPalette.Mid)
        text_color = palette.color(QPalette.Text)

        # Get theme accent colors for press/release
        press_color = palette.color(QPalette.Highlight)
        release_color = palette.color(QPalette.Link)

        painter.setBrush(bar_bg)
        painter.setPen(QPen(bar_border, 2))
        painter.drawRect(margin, bar_y, width - 2 * margin, bar_height)

        # Draw 0mm and 4.0mm labels
        painter.setPen(text_color)
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(margin - 10, bar_y + bar_height + 20, "0.0mm")
        painter.drawText(width - margin - 35, bar_y + bar_height + 20, "4.0mm")

        # Draw press actuation points (theme press color, above bar)
        for actuation, enabled in self.press_actuations:
            if not enabled:
                continue

            x = margin + int((actuation / 100.0) * (width - 2 * margin))

            # Draw line
            painter.setPen(QPen(press_color, 3))  # Theme press color
            painter.drawLine(x, bar_y - 20, x, bar_y)

            # Draw circle at top
            painter.setBrush(press_color)
            painter.drawEllipse(x - 5, bar_y - 28, 10, 10)

            # Draw actuation value
            mm_value = (actuation / 100.0) * 4.0
            painter.setPen(text_color)  # Use theme text color for readability
            font_small = QFont()
            font_small.setPointSize(8)
            painter.setFont(font_small)
            painter.drawText(x - 18, bar_y - 32, f"{mm_value:.2f}")
            painter.setFont(font)

        # Draw release actuation points (theme release color, below bar)
        for actuation, enabled in self.release_actuations:
            if not enabled:
                continue

            x = margin + int((actuation / 100.0) * (width - 2 * margin))

            # Draw line
            painter.setPen(QPen(release_color, 3))  # Theme release color
            painter.drawLine(x, bar_y + bar_height, x, bar_y + bar_height + 20)

            # Draw circle at bottom
            painter.setBrush(release_color)
            painter.drawEllipse(x - 5, bar_y + bar_height + 20, 10, 10)

            # Draw actuation value
            mm_value = (actuation / 100.0) * 4.0
            painter.setPen(text_color)  # Use theme text color for readability
            font_small = QFont()
            font_small.setPointSize(8)
            painter.setFont(font_small)
            painter.drawText(x - 18, bar_y + bar_height + 42, f"{mm_value:.2f}")
            painter.setFont(font)


class KeyswitchDiagramWidget(QWidget):
    """Visual diagram of a mechanical keyswitch cross-section using the actual image"""

    def __init__(self):
        super().__init__()
        self.setMinimumWidth(450)
        self.setMinimumHeight(750)
        self.setMaximumWidth(450)
        self.setMaximumHeight(750)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Detect dark mode
        palette = QApplication.palette()
        window_color = palette.color(QPalette.Window)
        brightness = (window_color.red() * 0.299 +
                      window_color.green() * 0.587 +
                      window_color.blue() * 0.114)
        is_dark = brightness < 127

        # Load the switch crossection image from Qt resources
        pixmap = QPixmap(":/switchcrossection")

        if not pixmap.isNull():
            # Calculate scaling to fit widget while maintaining aspect ratio
            widget_width = self.width()
            widget_height = self.height()

            # Scale the pixmap to fit the widget
            scaled_pixmap = pixmap.scaled(
                widget_width, widget_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            # Invert colors if in dark mode
            if is_dark:
                image = scaled_pixmap.toImage()
                image.invertPixels()
                scaled_pixmap = QPixmap.fromImage(image)

            # Center horizontally, align to top vertically (to match travel bar alignment)
            x = (widget_width - scaled_pixmap.width()) // 2 - 35  # Move 35 pixels left
            y = -30  # Move 30 pixels higher

            painter.drawPixmap(x, y, scaled_pixmap)
        else:
            # Fallback: draw a simple placeholder if image fails to load
            painter.setPen(QColor(128, 128, 128))
            painter.drawText(self.rect(), Qt.AlignCenter, "Switch\nDiagram")


class VerticalTravelBarWidget(QWidget):
    """Vertical representation of key travel with actuation points and draggable markers"""

    # Signals emitted when actuation points are dragged
    pressActuationDragged = pyqtSignal(int, int)  # (point_index, new_value 0-255)
    releaseActuationDragged = pyqtSignal(int, int)  # (point_index, new_value 0-255)

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
        self.actuation_point = 127       # First activation point (0-255, representing 0-4.0mm)

        # Dragging state
        self.dragging = False
        self.drag_point_type = None  # 'press' or 'release'
        self.drag_point_index = 0

        # Enable mouse tracking for cursor changes
        self.setMouseTracking(True)

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
        """Convert y position to actuation value (0-255)"""
        bar_x, margin_top, margin_bottom, bar_width, bar_height = self._get_bar_geometry()
        if bar_height <= 0:
            return 50
        actuation = ((y - margin_top) / bar_height) * 100
        return max(0, min(100, int(actuation)))

    def _actuation_to_y(self, actuation):
        """Convert actuation value (0-255) to y position"""
        bar_x, margin_top, margin_bottom, bar_width, bar_height = self._get_bar_geometry()
        return margin_top + int((actuation / 100.0) * bar_height)

    def mousePressEvent(self, event):
        """Handle mouse press - start dragging if clicking on an actuation point"""
        if event.button() == Qt.LeftButton:
            bar_x, margin_top, margin_bottom, bar_width, bar_height = self._get_bar_geometry()
            x, y = event.x(), event.y()

            # Check if clicking on a press actuation point (left side)
            for i, (actuation, enabled) in enumerate(self.press_actuations):
                if not enabled:
                    continue
                point_y = self._actuation_to_y(actuation)

                # Hit test for press point (left side of bar)
                if abs(y - point_y) < 15 and x < bar_x + bar_width // 2:
                    self.dragging = True
                    self.drag_point_type = 'press'
                    self.drag_point_index = i
                    self.setCursor(Qt.ClosedHandCursor)
                    return

            # Check if clicking on a release actuation point (right side)
            for i, (actuation, enabled) in enumerate(self.release_actuations):
                if not enabled:
                    continue
                point_y = self._actuation_to_y(actuation)

                # Hit test for release point (right side of bar)
                if abs(y - point_y) < 15 and x > bar_x + bar_width // 2:
                    self.dragging = True
                    self.drag_point_type = 'release'
                    self.drag_point_index = i
                    self.setCursor(Qt.ClosedHandCursor)
                    return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move - update dragged point position"""
        bar_x, margin_top, margin_bottom, bar_width, bar_height = self._get_bar_geometry()

        if self.dragging:
            y = event.y()
            actuation = self._y_to_actuation(y)

            if self.drag_point_type == 'press':
                self.pressActuationDragged.emit(self.drag_point_index, actuation)
            elif self.drag_point_type == 'release':
                self.releaseActuationDragged.emit(self.drag_point_index, actuation)
        else:
            # Update cursor based on hover position
            x, y = event.x(), event.y()
            hovering_point = False

            # Check press points
            for i, (actuation, enabled) in enumerate(self.press_actuations):
                if not enabled:
                    continue
                point_y = self._actuation_to_y(actuation)
                if abs(y - point_y) < 15 and x < bar_x + bar_width // 2:
                    hovering_point = True
                    break

            # Check release points
            if not hovering_point:
                for i, (actuation, enabled) in enumerate(self.release_actuations):
                    if not enabled:
                        continue
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

    def set_actuations(self, press_points, release_points, rapidfire_mode=False,
                      deadzone_top=0, deadzone_bottom=0, actuation_point=60):
        """Set actuation points to display

        Args:
            press_points: List of (actuation, enabled) tuples for press actions
            release_points: List of (actuation, enabled) tuples for release actions
            rapidfire_mode: If True, show relative to actuation point with first activation line
            deadzone_top: Top deadzone value (0-20, 0-0.5mm from top, internally inverted)
            deadzone_bottom: Bottom deadzone value (0-20, 0-0.5mm from bottom)
            actuation_point: First activation point (0-255, 0-4.0mm)
        """
        self.press_actuations = press_points
        self.release_actuations = release_points
        self.rapidfire_mode = rapidfire_mode
        self.deadzone_top = deadzone_top
        self.deadzone_bottom = deadzone_bottom
        self.actuation_point = actuation_point
        self.update()

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

        # Top deadzone: from top to deadzone_bottom value
        # deadzone_bottom is 0-20 (0-0.5mm from bottom of range)
        # Convert to 0-100 range: deadzone_bottom * 5 = percentage from top
        if self.deadzone_bottom > 0:
            deadzone_bottom_percent = (self.deadzone_bottom / 20.0) * 12.5  # 0-20 maps to 0-12.5%
            deadzone_bottom_height = int(bar_height * deadzone_bottom_percent / 255.0)
            painter.fillRect(bar_x, margin_top, bar_width, deadzone_bottom_height, deadzone_color)

            # Draw "Top Deadzone" label
            font_small = QFont()
            font_small.setPointSize(7)
            painter.setFont(font_small)

            label_text = "Top Deadzone"
            label_x = bar_x + bar_width + 5
            label_y = margin_top + deadzone_bottom_height // 2 - 6

            # Theme background
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

            painter.setPen(text_color)  # Use theme text color for deadzone labels
            painter.drawText(label_x, label_y + text_height - 4, label_text)

        # Bottom deadzone: from bottom up to (max_travel - deadzone_top)
        # deadzone_top is 0-20 (0-0.5mm from top, internally inverted)
        # For visualization: fill from bottom upward
        if self.deadzone_top > 0:
            deadzone_top_percent = (self.deadzone_top / 20.0) * 12.5  # 0-20 maps to 0-12.5%
            deadzone_top_height = int(bar_height * deadzone_top_percent / 255.0)
            deadzone_top_y = margin_top + bar_height - deadzone_top_height
            painter.fillRect(bar_x, deadzone_top_y, bar_width, deadzone_top_height, deadzone_color)

            # Draw "Bottom Deadzone" label
            font_small = QFont()
            font_small.setPointSize(7)
            painter.setFont(font_small)

            label_text = "Bottom Deadzone"
            label_x = bar_x + bar_width + 5
            label_y = deadzone_top_y + deadzone_top_height // 2 - 6

            # Theme background
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

            painter.setPen(text_color)  # Use theme text color for deadzone labels
            painter.drawText(label_x, label_y + text_height - 4, label_text)

        if self.rapidfire_mode:

            # Draw actuation line for "First Activation" at actual actuation point
            actuation_y = margin_top + int((self.actuation_point / 255.0) * bar_height)
            painter.setPen(QPen(QColor(255, 200, 0), 2, Qt.DashLine))  # Yellow dashed line
            painter.drawLine(bar_x, actuation_y, bar_x + bar_width, actuation_y)

            # Draw "First Activation" label with button-like styling
            font = QFont()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)

            # Calculate label background
            label_text = "First Activation"
            label_x = bar_x + bar_width + 15  # Closer to bar, consistent with other labels
            label_y = actuation_y - 10

            # Button-like styling with highlight color (active button)
            button_bg = palette.color(QPalette.Highlight)
            button_border = palette.color(QPalette.Highlight)

            # Measure text to size the box
            fm = painter.fontMetrics()
            text_width = fm.width(label_text)
            text_height = fm.height()
            padding = 6

            # Draw rounded button background
            painter.setPen(QPen(button_border, 1))
            painter.setBrush(button_bg)
            painter.drawRoundedRect(label_x - padding, label_y - padding,
                                   text_width + 2 * padding, text_height + 2 * padding, 6, 6)

            painter.setPen(palette.color(QPalette.HighlightedText))  # Use theme highlighted text for first activation label
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
            # In rapidfire mode:
            # - Release is relative to first activation (actuation_y), going upward
            # - Press is relative to release, going downward
            bar_height = height - margin_top - margin_bottom
            actuation_y = margin_top + int((self.actuation_point / 255.0) * bar_height)

            # Draw release actuation points first (theme release color, above actuation line)
            release_y = actuation_y  # Default to actuation line
            for actuation, enabled in self.release_actuations:
                if not enabled:
                    continue

                # Release is upward from actuation point
                # actuation is sensitivity in 0-100 (representing 0-4.0mm distance)
                y = actuation_y - int((actuation / 100.0) * bar_height)
                release_y = y

                # Draw line to right
                painter.setPen(QPen(release_color, 3))  # Theme release color
                painter.drawLine(bar_x + bar_width, y, bar_x + bar_width + 20, y)

                # Draw circle on right
                painter.setBrush(release_color)
                painter.drawEllipse(bar_x + bar_width + 18, y - 5, 10, 10)

                # Draw "Release Threshold" identifier and mm value with button-like styling
                mm_value = (actuation / 100.0) * 4.0

                # Use bigger font for button-like appearance
                font_label = QFont()
                font_label.setPointSize(9)
                font_label.setBold(True)
                painter.setFont(font_label)

                fm = painter.fontMetrics()
                padding = 6  # Bigger padding for button-like appearance
                label_x = bar_x + bar_width + 15  # Closer to bar

                # Button-like background
                button_bg = palette.color(QPalette.Button)
                button_border = palette.color(QPalette.Light)

                # Draw "Release Threshold" identifier (button-like)
                id_text = "Release Threshold"
                id_width = fm.width(id_text)
                id_height = fm.height()
                id_y = y - id_height - 10

                # Draw rounded button background
                painter.setPen(QPen(button_border, 1))
                painter.setBrush(button_bg)
                painter.drawRoundedRect(label_x - padding, id_y - padding,
                                       id_width + 2 * padding, id_height + 2 * padding, 6, 6)
                painter.setPen(palette.color(QPalette.ButtonText))  # Use button text color
                painter.drawText(label_x, id_y + id_height - 4, id_text)

                # Draw mm value below identifier (smaller, secondary label)
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
                painter.setPen(text_color)  # Use theme text color for readability
                painter.drawText(label_x, mm_y, mm_text)

            # Draw press actuation points (theme press color, below release line)
            for actuation, enabled in self.press_actuations:
                if not enabled:
                    continue

                # Press is downward from release point
                # actuation is sensitivity in 0-100 (representing 0-4.0mm distance)
                y = release_y + int((actuation / 100.0) * bar_height)

                # Draw line to left
                painter.setPen(QPen(press_color, 3))  # Theme press color
                painter.drawLine(bar_x - 20, y, bar_x, y)

                # Draw circle on left
                painter.setBrush(press_color)
                painter.drawEllipse(bar_x - 28, y - 5, 10, 10)

                # Draw "Press Threshold" identifier and mm value with button-like styling
                mm_value = (actuation / 100.0) * 4.0

                # Use bigger font for button-like appearance
                font_label = QFont()
                font_label.setPointSize(9)
                font_label.setBold(True)
                painter.setFont(font_label)

                fm = painter.fontMetrics()
                padding = 6  # Bigger padding for button-like appearance

                # Button-like background
                button_bg = palette.color(QPalette.Button)
                button_border = palette.color(QPalette.Light)

                # Draw "Press Threshold" identifier (button-like)
                id_text = "Press Threshold"
                id_width = fm.width(id_text)
                id_height = fm.height()
                label_x = bar_x - id_width - 15
                id_y = y - id_height - 10

                # Draw rounded button background
                painter.setPen(QPen(button_border, 1))
                painter.setBrush(button_bg)
                painter.drawRoundedRect(label_x - padding, id_y - padding,
                                       id_width + 2 * padding, id_height + 2 * padding, 6, 6)
                painter.setPen(palette.color(QPalette.ButtonText))  # Use button text color
                painter.drawText(label_x, id_y + id_height - 4, id_text)

                # Draw mm value below identifier (smaller, secondary label)
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
                painter.setPen(text_color)  # Use theme text color for readability
                painter.drawText(mm_x, mm_y, mm_text)
        else:
            # Normal mode: draw from top to bottom
            font = QFont()
            font.setPointSize(9)

            # Draw press actuation points (theme press color, left side)
            # These represent Press 1, Press 2, etc. actuation points for DKS
            for idx, (actuation, enabled) in enumerate(self.press_actuations):
                if not enabled:
                    continue

                y = margin_top + int((actuation / 100.0) * (height - margin_top - margin_bottom))

                # Draw line to left
                painter.setPen(QPen(press_color, 3))  # Theme press color
                painter.drawLine(bar_x - 20, y, bar_x, y)

                # Draw circle on left
                painter.setBrush(press_color)
                painter.drawEllipse(bar_x - 28, y - 5, 10, 10)

                # Draw identifier and mm value with button-like styling
                mm_value = (actuation / 100.0) * 4.0

                # Use bigger font for button-like appearance
                font_label = QFont()
                font_label.setPointSize(9)
                font_label.setBold(True)
                painter.setFont(font_label)

                fm = painter.fontMetrics()
                padding = 6  # Bigger padding for button-like appearance

                # Draw identifier label (button-like)
                id_text = f"Press {idx + 1} Actuation"
                id_width = fm.width(id_text)
                id_height = fm.height()
                label_x = bar_x - id_width - 15
                id_y = y - id_height - 10

                # Button-like background with highlight color
                button_bg = palette.color(QPalette.Button)
                button_border = palette.color(QPalette.Light)

                # Draw rounded button background
                painter.setPen(QPen(button_border, 1))
                painter.setBrush(button_bg)
                painter.drawRoundedRect(label_x - padding, id_y - padding,
                                       id_width + 2 * padding, id_height + 2 * padding, 6, 6)
                painter.setPen(palette.color(QPalette.ButtonText))  # Use button text color
                painter.drawText(label_x, id_y + id_height - 4, id_text)

                # Draw mm value below identifier (smaller, secondary label)
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
                painter.setPen(text_color)  # Use theme text color for readability
                painter.drawText(mm_x, mm_y, mm_text)

            # Draw release actuation points (theme release color, right side)
            # These represent Release 1, Release 2, etc. actuation points for DKS
            for idx, (actuation, enabled) in enumerate(self.release_actuations):
                if not enabled:
                    continue

                y = margin_top + int((actuation / 100.0) * (height - margin_top - margin_bottom))

                # Draw line to right
                painter.setPen(QPen(release_color, 3))  # Theme release color
                painter.drawLine(bar_x + bar_width, y, bar_x + bar_width + 20, y)

                # Draw circle on right
                painter.setBrush(release_color)
                painter.drawEllipse(bar_x + bar_width + 18, y - 5, 10, 10)

                # Draw identifier and mm value with button-like styling
                mm_value = (actuation / 100.0) * 4.0

                # Use bigger font for button-like appearance
                font_label = QFont()
                font_label.setPointSize(9)
                font_label.setBold(True)
                painter.setFont(font_label)

                fm = painter.fontMetrics()
                padding = 6  # Bigger padding for button-like appearance
                label_x = bar_x + bar_width + 15  # Closer to bar

                # Button-like background
                button_bg = palette.color(QPalette.Button)
                button_border = palette.color(QPalette.Light)

                # Draw identifier label (button-like)
                id_text = f"Release {idx + 1} Actuation"
                id_width = fm.width(id_text)
                id_height = fm.height()
                id_y = y - id_height - 10

                # Draw rounded button background
                painter.setPen(QPen(button_border, 1))
                painter.setBrush(button_bg)
                painter.drawRoundedRect(label_x - padding, id_y - padding,
                                       id_width + 2 * padding, id_height + 2 * padding, 6, 6)
                painter.setPen(palette.color(QPalette.ButtonText))  # Use button text color
                painter.drawText(label_x, id_y + id_height - 4, id_text)

                # Draw mm value below identifier (smaller, secondary label)
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
                painter.setPen(text_color)  # Use theme text color for readability
                painter.drawText(label_x, mm_y, mm_text)


class DKSActionEditor(QWidget):
    """Editor for a single DKS action with DKSKeyWidget integration"""

    changed = pyqtSignal()
    key_selected = pyqtSignal(object)  # Emits the DKSKeyWidget when clicked

    def __init__(self, action_num, is_press=True):
        super().__init__()
        self.action_num = action_num
        self.is_press = is_press

        # Main vertical layout - button on top, slider below
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        # Top row: Behavior dropdown and Key widget side by side
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        # Behavior selector (narrower)
        self.behavior_combo = QComboBox()
        self.behavior_combo.addItems(["Tap", "Press", "Release"])
        self.behavior_combo.setCurrentIndex(DKS_BEHAVIOR_TAP)
        self.behavior_combo.currentIndexChanged.connect(self._on_changed)
        self.behavior_combo.setFixedSize(50, 25)
        top_row.addWidget(self.behavior_combo)

        # Key widget with label
        key_container = QVBoxLayout()
        key_container.setSpacing(2)

        action_type = "Press" if is_press else "Release"
        action_label = QLabel(f"{action_type} {action_num + 1}")
        action_label.setAlignment(Qt.AlignCenter)
        action_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 9px;
                color: palette(button-text);
                background-color: palette(button);
                border-radius: 4px;
                padding: 2px 4px;
            }
        """)
        key_container.addWidget(action_label)

        self.key_widget = DKSKeyWidget()
        self.key_widget.setFixedSize(55, 45)
        self.key_widget.changed.connect(self._on_changed)
        self.key_widget.selected.connect(self._on_key_selected)
        key_container.addWidget(self.key_widget, alignment=Qt.AlignCenter)

        top_row.addLayout(key_container)
        layout.addLayout(top_row)

        # Bottom row: Slider below the button
        slider_container = QHBoxLayout()
        slider_container.setSpacing(4)

        self.actuation_slider = QSlider(Qt.Horizontal)
        self.actuation_slider.setMinimum(0)
        self.actuation_slider.setMaximum(100)
        self.actuation_slider.setValue(50)
        self.actuation_slider.setFixedWidth(70)
        self.actuation_slider.valueChanged.connect(self._update_actuation_label)
        self.actuation_slider.valueChanged.connect(self._on_changed)
        slider_container.addWidget(self.actuation_slider)

        self.actuation_label = QLabel("1.50mm")
        self.actuation_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.actuation_label.setStyleSheet("font-size: 8px;")
        self.actuation_label.setFixedWidth(35)
        slider_container.addWidget(self.actuation_label)

        layout.addLayout(slider_container)

        # Store label reference for color styling
        self.label = action_label

        self.setLayout(layout)
        self._update_actuation_label()

        # Style the widget with theme colors
        self.setStyleSheet("""
            DKSActionEditor {
                border: 1px solid palette(mid);
                border-radius: 5px;
                background: palette(base);
            }
        """)

    def _update_actuation_label(self):
        """Update actuation label with mm value"""
        value = self.actuation_slider.value()
        mm = (value / 100.0) * 4.0
        self.actuation_label.setText(f"{mm:.2f}mm")

    def _on_changed(self):
        """Emit changed signal"""
        self.changed.emit()

    def _on_key_selected(self, widget):
        """Forward key selection signal to parent"""
        self.key_selected.emit(widget)

    def set_action(self, keycode, actuation, behavior):
        """Set action values"""
        # Convert keycode integer to string qmk_id
        if isinstance(keycode, int):
            if keycode == 0:
                keycode_str = "KC_NO"
            else:
                keycode_str = Keycode.serialize(keycode)
        else:
            keycode_str = keycode

        self.key_widget.set_keycode(keycode_str)
        self.actuation_slider.setValue(actuation)
        self.behavior_combo.setCurrentIndex(behavior)

    def get_action(self):
        """Get action values as (keycode, actuation, behavior) tuple"""
        keycode_str = self.key_widget.keycode

        # Convert keycode string to integer
        if keycode_str == "KC_NO" or keycode_str == "":
            keycode = 0
        else:
            keycode = Keycode.deserialize(keycode_str)

        actuation = self.actuation_slider.value()
        behavior = self.behavior_combo.currentIndex()
        return (keycode, actuation, behavior)


class DKSVisualWidget(QWidget):
    """Visual layout widget for DKS actions - horizontal layout"""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(1100, 350)  # Wide enough for labels, min height prevents squishing
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)  # Minimum allows scrolling

        # Will be set by parent
        self.press_editors = []
        self.release_editors = []

        # Main horizontal layout
        self.main_layout = QHBoxLayout()
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(20)
        self.setLayout(self.main_layout)

    def set_editors(self, press_editors, release_editors):
        """Position the action editors in horizontal layout with 2x2 grids"""
        self.press_editors = press_editors
        self.release_editors = release_editors

        # Clear existing layout
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Left section: Title/Description + Press actions (2x2 grid)
        press_container = QWidget()
        press_layout = QVBoxLayout()
        press_layout.setContentsMargins(0, 0, 0, 0)
        press_layout.setSpacing(6)

        # Title and description at top left
        title_label = QLabel("DKS Configuration")
        title_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        press_layout.addWidget(title_label)

        desc_label = QLabel("Configure multi-action keys with customizable actuation points.\n"
                           "Set different actions for press and release at specific depths.")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; font-size: 9pt;")
        press_layout.addWidget(desc_label)

        # Add some spacing before press section
        press_layout.addSpacing(10)

        press_label = QLabel("Key Press (Downstroke)")
        press_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 11px;
                color: palette(button-text);
                background-color: palette(button);
                border-radius: 6px;
                padding: 4px 10px;
            }
        """)
        press_label.setAlignment(Qt.AlignCenter)
        press_layout.addWidget(press_label)

        # 2x2 grid for press actions
        press_grid = QGridLayout()
        press_grid.setSpacing(6)
        for i, editor in enumerate(self.press_editors):
            row = i // 2  # 0, 0, 1, 1
            col = i % 2   # 0, 1, 0, 1
            editor.setParent(press_container)
            press_grid.addWidget(editor, row, col)
        press_layout.addLayout(press_grid)

        press_layout.addStretch()
        press_container.setLayout(press_layout)
        self.main_layout.addWidget(press_container)

        # Middle: Visualization container (matching trigger settings exactly)
        viz_container = QFrame()
        viz_container.setFrameShape(QFrame.StyledPanel)
        viz_container.setStyleSheet("QFrame { background-color: palette(base); }")
        viz_container.setMaximumHeight(325)
        viz_container.setMaximumWidth(580)
        viz_layout = QVBoxLayout()
        viz_layout.setContentsMargins(0, 10, 0, 10)
        viz_layout.setSpacing(0)

        # Horizontal layout for diagram and travel bar
        viz_h_layout = QHBoxLayout()
        viz_h_layout.setSpacing(0)
        viz_h_layout.setContentsMargins(0, 0, 0, 0)

        # Add keyswitch diagram
        self.keyswitch_diagram = KeyswitchDiagramWidget()
        viz_h_layout.addWidget(self.keyswitch_diagram)

        # Add vertical travel bar
        viz_h_layout.addWidget(self.create_vertical_travel_bar())

        viz_layout.addLayout(viz_h_layout)
        viz_layout.addStretch()

        viz_container.setLayout(viz_layout)
        self.main_layout.addWidget(viz_container, alignment=Qt.AlignTop)

        # Right section: Release actions (2x2 grid) - with top spacing to align with press
        release_container = QWidget()
        release_layout = QVBoxLayout()
        release_layout.setContentsMargins(0, 0, 0, 0)
        release_layout.setSpacing(6)

        # Add spacing at top to align with press section (title + desc height)
        release_layout.addSpacing(75)

        release_label = QLabel("Key Release (Upstroke)")
        release_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 11px;
                color: palette(button-text);
                background-color: palette(button);
                border-radius: 6px;
                padding: 4px 10px;
            }
        """)
        release_label.setAlignment(Qt.AlignCenter)
        release_layout.addWidget(release_label)

        # 2x2 grid for release actions
        release_grid = QGridLayout()
        release_grid.setSpacing(6)
        for i, editor in enumerate(self.release_editors):
            row = i // 2  # 0, 0, 1, 1
            col = i % 2   # 0, 1, 0, 1
            editor.setParent(release_container)
            release_grid.addWidget(editor, row, col)
        release_layout.addLayout(release_grid)

        release_layout.addStretch()
        release_container.setLayout(release_layout)
        self.main_layout.addWidget(release_container)

    def create_vertical_travel_bar(self):
        """Create a vertical travel bar indicator"""
        self.vertical_travel_bar = VerticalTravelBarWidget()
        # Connect drag signals to update the action editors
        self.vertical_travel_bar.pressActuationDragged.connect(self._on_press_actuation_dragged)
        self.vertical_travel_bar.releaseActuationDragged.connect(self._on_release_actuation_dragged)
        return self.vertical_travel_bar

    def _on_press_actuation_dragged(self, index, value):
        """Handle press actuation point dragged on visualizer"""
        if index < len(self.press_editors):
            self.press_editors[index].actuation_slider.setValue(value)

    def _on_release_actuation_dragged(self, index, value):
        """Handle release actuation point dragged on visualizer"""
        if index < len(self.release_editors):
            self.release_editors[index].actuation_slider.setValue(value)

    def update_travel_bar(self, press_points, release_points):
        """Update the vertical travel bar with actuation points"""
        if hasattr(self, 'vertical_travel_bar'):
            self.vertical_travel_bar.set_actuations(press_points, release_points)


class DKSEntryUI(QWidget):
    """UI for a single DKS slot"""

    changed = pyqtSignal()

    def __init__(self, slot_idx):
        super().__init__()
        self.slot_idx = slot_idx
        self.dks_protocol = None
        self.selected_key_widget = None  # Track which key widget is selected
        self._loading = False  # Guard flag: True while loading from keyboard/slot

        # Set minimum height to prevent squishing - allows scroll instead
        self.setMinimumHeight(400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # Horizontal layout for visual widget (centered)
        visual_layout = QHBoxLayout()
        visual_layout.setContentsMargins(0, 0, 0, 0)

        self.visual_widget = DKSVisualWidget()

        # Create action editors
        self.press_editors = []
        self.release_editors = []

        for i in range(DKS_ACTIONS_PER_STAGE):
            press_editor = DKSActionEditor(i, is_press=True)
            press_editor.changed.connect(self._on_action_changed)
            press_editor.key_selected.connect(self._on_key_selected)
            self.press_editors.append(press_editor)

            release_editor = DKSActionEditor(i, is_press=False)
            release_editor.changed.connect(self._on_action_changed)
            release_editor.key_selected.connect(self._on_key_selected)
            self.release_editors.append(release_editor)

        # Set editors in visual widget
        self.visual_widget.set_editors(self.press_editors, self.release_editors)

        # Center the visual widget with stretches on both sides
        visual_layout.addStretch()
        visual_layout.addWidget(self.visual_widget)
        visual_layout.addStretch()
        main_layout.addLayout(visual_layout)

        # Buttons directly in the tab
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.reset_all_btn = QPushButton("Reset All Slots")
        self.reset_all_btn.setFixedWidth(150)
        self.reset_all_btn.clicked.connect(self._on_reset_all)
        button_layout.addWidget(self.reset_all_btn)

        self.load_eeprom_btn = QPushButton("Load All from EEPROM")
        self.load_eeprom_btn.setFixedWidth(150)
        self.load_eeprom_btn.clicked.connect(self._on_load_eeprom)
        button_layout.addWidget(self.load_eeprom_btn)

        button_layout.addStretch()

        self.reset_btn = QPushButton("Reset Slot")
        self.reset_btn.setFixedWidth(150)
        self.reset_btn.clicked.connect(self._on_reset)
        button_layout.addWidget(self.reset_btn)

        self.save_eeprom_btn = QPushButton("Save to EEPROM")
        self.save_eeprom_btn.setFixedWidth(150)
        self.save_eeprom_btn.clicked.connect(self._on_save_eeprom)
        button_layout.addWidget(self.save_eeprom_btn)

        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

    def set_dks_protocol(self, protocol):
        """Set the DKS protocol handler"""
        self.dks_protocol = protocol

    def set_debug_log(self, debug_log):
        """Set the debug log callback"""
        self._debug_log = debug_log

    def set_debug_console(self, console):
        """Set the debug console widget for operation markers"""
        self._debug_console = console

    def _log(self, message, level="DEBUG"):
        """Log to debug console if available"""
        if hasattr(self, '_debug_log') and self._debug_log:
            self._debug_log(message, level)

    def _on_load(self):
        """Load slot from keyboard"""
        if not self.dks_protocol:
            self._log(f"Slot {self.slot_idx}: _on_load called but no protocol set", "WARN")
            return

        self._log(f"Loading slot {self.slot_idx} from keyboard...", "INFO")
        slot = self.dks_protocol.get_slot(self.slot_idx)
        if not slot:
            self._log(f"Slot {self.slot_idx}: get_slot returned None (firmware may not support DKS)", "WARN")
            return

        self._log(f"Slot {self.slot_idx}: loaded successfully, updating UI", "INFO")
        self.load_from_slot(slot)

    def load_from_slot(self, slot):
        """Load UI from slot data.

        Sets _loading flag to prevent _on_action_changed (and therefore
        _send_to_keyboard) from firing while editors are being populated.
        Without this guard, the first editor update triggers _send_to_keyboard
        which reads ALL editors (most still at defaults) and overwrites the
        firmware's correct slot data with partially-loaded values.
        """
        self._loading = True
        try:
            # Press actions
            for i, editor in enumerate(self.press_editors):
                action = slot.press_actions[i]
                editor.set_action(action.keycode, action.actuation, action.behavior)

            # Release actions
            for i, editor in enumerate(self.release_editors):
                action = slot.release_actions[i]
                editor.set_action(action.keycode, action.actuation, action.behavior)
        finally:
            self._loading = False

        self._update_travel_bar()

    def save_to_slot(self):
        """Save UI to slot (returns tuple of press and release actions)"""
        press_actions = []
        for editor in self.press_editors:
            press_actions.append(editor.get_action())

        release_actions = []
        for editor in self.release_editors:
            release_actions.append(editor.get_action())

        return (press_actions, release_actions)

    def _on_action_changed(self):
        """Handle action change - skip if we're loading data from the keyboard"""
        if self._loading:
            return
        self._update_travel_bar()
        self._send_to_keyboard()
        self.changed.emit()

    def _on_key_selected(self, widget):
        """Handle key widget selection - update visual feedback"""
        # Clear previous selection
        if self.selected_key_widget:
            self.selected_key_widget.set_selected(False)

        # Set new selection
        self.selected_key_widget = widget
        widget.set_selected(True)

    def on_keycode_selected(self, keycode):
        """Called when a keycode is selected from TabbedKeycodes"""
        if self.selected_key_widget:
            self.selected_key_widget.on_keycode_changed(keycode)

    def _send_to_keyboard(self):
        """Send current configuration to keyboard"""
        if not self.dks_protocol:
            self._log(f"Slot {self.slot_idx}: _send_to_keyboard skipped - no protocol", "WARN")
            return

        self._log(f"Slot {self.slot_idx}: sending all 8 actions to keyboard...", "INFO")

        # Send press actions
        for i, editor in enumerate(self.press_editors):
            keycode, actuation, behavior = editor.get_action()
            success = self.dks_protocol.set_action(
                self.slot_idx, True, i, keycode, actuation, behavior
            )
            if not success:
                self._log(f"Slot {self.slot_idx}: FAILED to send Press[{i}]", "ERROR")

        # Send release actions
        for i, editor in enumerate(self.release_editors):
            keycode, actuation, behavior = editor.get_action()
            success = self.dks_protocol.set_action(
                self.slot_idx, False, i, keycode, actuation, behavior
            )
            if not success:
                self._log(f"Slot {self.slot_idx}: FAILED to send Release[{i}]", "ERROR")

    def _update_travel_bar(self):
        """Update travel bar visualization"""
        press_points = []
        for editor in self.press_editors:
            keycode, actuation, behavior = editor.get_action()
            enabled = (keycode != 0)
            press_points.append((actuation, enabled))

        release_points = []
        for editor in self.release_editors:
            keycode, actuation, behavior = editor.get_action()
            enabled = (keycode != 0)
            release_points.append((actuation, enabled))

        self.visual_widget.update_travel_bar(press_points, release_points)

    def _on_reset(self):
        """Reset slot to defaults"""
        if not self.dks_protocol:
            return

        reply = QMessageBox.question(
            self, "Confirm Reset",
            f"Reset DKS_{self.slot_idx:02d} to default configuration?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._log(f"User requested reset of slot {self.slot_idx}", "INFO")
            if self.dks_protocol.reset_slot(self.slot_idx):
                self._log(f"Slot {self.slot_idx} reset OK, reloading...", "INFO")
                QMessageBox.information(self, "Success", "Slot reset to defaults")
                self._on_load()
            else:
                self._log(f"Slot {self.slot_idx} reset FAILED", "ERROR")
                QMessageBox.warning(self, "Error", "Failed to reset slot")

    def _on_save_eeprom(self):
        """Save to EEPROM"""
        if not self.dks_protocol:
            return

        console = getattr(self, '_debug_console', None)
        if console:
            console.mark_operation_start()
        self._log("User requested SAVE TO EEPROM", "INFO")
        success = self.dks_protocol.save_to_eeprom()
        if success:
            self._log("Save to EEPROM: SUCCESS", "INFO")
            QMessageBox.information(self, "Success", "DKS configuration saved to EEPROM")
        else:
            self._log("Save to EEPROM: FAILED", "ERROR")
            QMessageBox.warning(self, "Error", "Failed to save to EEPROM")
        if console:
            console.mark_operation_end(success)

    def _on_reset_all(self):
        """Reset all slots to defaults"""
        if not self.dks_protocol:
            return

        reply = QMessageBox.question(
            self, "Confirm Reset",
            "Reset ALL DKS slots to default configuration? This cannot be undone!",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._log("User requested RESET ALL SLOTS", "INFO")
            if self.dks_protocol.reset_all_slots():
                self._log("Reset all slots: SUCCESS, reloading...", "INFO")
                QMessageBox.information(self, "Success", "All slots reset to defaults")
                self._on_load()
            else:
                self._log("Reset all slots: FAILED", "ERROR")
                QMessageBox.warning(self, "Error", "Failed to reset slots")

    def _on_load_eeprom(self):
        """Load all slots from EEPROM"""
        if not self.dks_protocol:
            return

        console = getattr(self, '_debug_console', None)
        if console:
            console.mark_operation_start()
        self._log("User requested LOAD FROM EEPROM", "INFO")
        success = self.dks_protocol.load_from_eeprom()
        if success:
            self._log("Load from EEPROM: SUCCESS, reloading current slot...", "INFO")
            QMessageBox.information(self, "Success", "DKS configurations loaded from EEPROM")
            self._on_load()
        else:
            self._log("Load from EEPROM: FAILED", "ERROR")
            QMessageBox.warning(self, "Error", "Failed to load from EEPROM")
        if console:
            console.mark_operation_end(success)


class DKSSettingsTab(BasicEditor):
    """Main DKS settings editor tab with filtered slots"""

    def __init__(self, layout_editor):
        super().__init__()
        self.layout_editor = layout_editor
        self.dks_protocol = None
        self.dks_entries = []
        self.dks_scroll_widgets = []  # Store scroll widgets for each entry
        self.loaded_slots = set()  # Track which slots have been loaded

        # Dynamic tab tracking
        self._visible_tab_count = 1  # Minimum 1 tab visible
        self._manually_expanded_count = 0  # Tabs added via "+" button

        # Create tab widget for DKS slots
        self.tabs = QTabWidget()

        # Create all DKS entries and their scroll widgets
        for i in range(DKS_NUM_SLOTS):
            entry = DKSEntryUI(i)
            entry.changed.connect(self.on_entry_changed)
            self.dks_entries.append(entry)

            scroll = QScrollArea()
            scroll.setWidget(entry)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.dks_scroll_widgets.append(scroll)

        self.addWidget(self.tabs)

        # Connect tab changes for lazy loading and "+" tab handling
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Add TabbedKeycodes at the bottom (same as keymap editor)
        self.tabbed_keycodes = TabbedKeycodes()
        self.tabbed_keycodes.keycode_changed.connect(self.on_keycode_selected)
        self.addWidget(self.tabbed_keycodes)

        # Debug console at the bottom
        self.debug_console = DebugConsole("DKS Debug Console")
        self.addWidget(self.debug_console)

    def on_entry_changed(self):
        """Handle entry change (can be used for modified indicators)"""
        # Future: Add modified state tracking like TapDance
        pass

    def on_keycode_selected(self, keycode):
        """Called when a keycode is selected from TabbedKeycodes"""
        current_idx = self.tabs.currentIndex()
        if current_idx >= 0 and current_idx < len(self.dks_entries):
            self.dks_entries[current_idx].on_keycode_selected(keycode)

    def _on_tab_changed(self, index):
        """Handle tab change - lazy load slot data and handle '+' tab"""
        # Check if "+" tab was clicked
        if self._visible_tab_count < DKS_NUM_SLOTS and index == self._visible_tab_count:
            self._manually_expanded_count += 1
            self._update_visible_tabs()
            # Update keycode buttons to show new DKS count
            self.tabbed_keycodes.refresh_macro_buttons()
            self.tabs.setCurrentIndex(self._visible_tab_count - 1)
            self.debug_log(f"Tab expanded - now showing {self._visible_tab_count} tabs", "INFO")
            return

        # Lazy load: Only load slot data when first viewing the tab
        if index >= 0 and index < len(self.dks_entries):
            if self.dks_protocol and index not in self.loaded_slots:
                self.debug_log(f"Lazy loading slot {index} (first view)", "INFO")
                self.dks_entries[index]._on_load()
                self.loaded_slots.add(index)

    def debug_log(self, message, level="DEBUG"):
        """Log a message to the debug console"""
        if hasattr(self, 'debug_console'):
            self.debug_console.log(message, level)

    def rebuild(self, device):
        """Rebuild the editor when device changes"""
        super().rebuild(device)

        if not self.valid():
            self.dks_protocol = None
            return

        self.debug_log("Device connected - initializing DKS protocol", "INFO")

        # Create DKS protocol handler with debug logging callback
        # NOTE: device is VialKeyboard, device.keyboard is the Keyboard comm object
        # that has _create_hid_packet and usb_send methods
        self.dks_protocol = ProtocolDKS(device.keyboard, debug_log=self.debug_log)

        # Set protocol for all entries
        for entry in self.dks_entries:
            entry.set_dks_protocol(self.dks_protocol)
            entry.set_debug_log(self.debug_log)
            entry.set_debug_console(self.debug_console)

        # Clear loaded slots cache on device change
        self.loaded_slots.clear()

        # Reset manual expansion and scan for used slots
        self._manually_expanded_count = 0
        self.debug_log("Scanning all slots for content...", "INFO")
        self._scan_and_update_visible_tabs()
        self.debug_log(f"Scan complete - {self._visible_tab_count} tabs visible", "INFO")

        # Set keyboard reference for tabbed keycodes
        if hasattr(device, 'keyboard'):
            self.tabbed_keycodes.set_keyboard(device.keyboard)

    def _dks_slot_has_content(self, slot):
        """Check if a DKS slot has any keycodes assigned"""
        # Check press actions
        for action in slot.press_actions:
            if action.keycode != 0:
                return True
        # Check release actions
        for action in slot.release_actions:
            if action.keycode != 0:
                return True
        return False

    def _scan_and_update_visible_tabs(self):
        """Scan all slots to find which have content and update visible tabs"""
        if not self.dks_protocol:
            return

        # Load all slots to find which have content
        last_used = -1
        for i in range(DKS_NUM_SLOTS):
            slot = self.dks_protocol.get_slot(i)
            if slot:
                self.dks_entries[i].load_from_slot(slot)
                self.loaded_slots.add(i)
                if self._dks_slot_has_content(slot):
                    last_used = i

        self._update_visible_tabs_with_last_used(last_used)

    def _find_last_used_index(self):
        """Find the index of the last DKS slot that has content"""
        for idx in range(DKS_NUM_SLOTS - 1, -1, -1):
            if idx in self.loaded_slots:
                # Check if this entry has any keycodes set
                for editor in self.dks_entries[idx].press_editors:
                    keycode, _, _ = editor.get_action()
                    if keycode != 0:
                        return idx
                for editor in self.dks_entries[idx].release_editors:
                    keycode, _, _ = editor.get_action()
                    if keycode != 0:
                        return idx
        return -1

    def _update_visible_tabs_with_last_used(self, last_used):
        """Update visible tabs given the last used index"""
        max_tabs = DKS_NUM_SLOTS

        # Calculate visible count: last used + 1, or at least 1, plus any manually expanded
        base_visible = max(1, last_used + 1)
        self._visible_tab_count = min(max_tabs, base_visible + self._manually_expanded_count)

        # Remove all tabs first
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)

        # Add visible DKS tabs
        for x in range(self._visible_tab_count):
            self.tabs.addTab(self.dks_scroll_widgets[x], f"DKS{x}")

        # Add "+" tab if not all tabs are visible
        if self._visible_tab_count < max_tabs:
            plus_widget = QWidget()
            self.tabs.addTab(plus_widget, "+")

    def _update_visible_tabs(self):
        """Update which tabs are visible based on content and manual expansion"""
        last_used = self._find_last_used_index()
        self._update_visible_tabs_with_last_used(last_used)

    def valid(self):
        """Check if this tab is valid for the current device"""
        return isinstance(self.device, VialKeyboard)
