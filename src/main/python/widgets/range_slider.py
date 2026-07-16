# SPDX-License-Identifier: GPL-2.0-or-later

from PyQt5.QtWidgets import QWidget, QSlider, QApplication
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QPalette


class StyledSlider(QWidget):
    """
    A styled single-handle slider matching the MultiHandleSlider aesthetic
    """

    valueChanged = pyqtSignal(int)

    def __init__(self, minimum=0, maximum=100, parent=None):
        super().__init__(parent)
        self.minimum = minimum
        self.maximum = maximum
        self.value = (minimum + maximum) // 2
        self.active = False

        # Visual settings (matching MultiHandleSlider)
        self.handle_radius = 10
        self.track_height = 8
        self.margin = 25

        # Color scheme will be fetched from palette at paint time
        self.track_bg_color = None  # Will use palette
        self.handle_color = None  # Will use palette
        self.handle_border_color = None  # Will use palette
        self.fill_color = None  # Will use palette highlight

        self.setMinimumHeight(40)
        self.setMinimumWidth(200)

    def setValue(self, value):
        """Set slider value"""
        self.value = max(self.minimum, min(self.maximum, value))
        self.update()

    def getValue(self):
        """Get slider value"""
        return self.value

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get theme colors from palette
        palette = QApplication.palette()
        track_bg_color = palette.color(QPalette.AlternateBase)
        fill_color = palette.color(QPalette.Highlight)

        width = self.width()
        height = self.height()

        # Calculate track geometry
        track_y = height // 2 - self.track_height // 2
        track_x = self.margin
        track_width = width - 2 * self.margin

        # Draw background track with shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 40)))
        painter.drawRoundedRect(track_x + 1, track_y + 1, track_width, self.track_height, 4, 4)

        # Draw background track
        painter.setBrush(QBrush(track_bg_color))
        painter.drawRoundedRect(track_x, track_y, track_width, self.track_height, 4, 4)

        # Draw filled section (from left to handle)
        handle_x = self._value_to_pixel(self.value)
        painter.setBrush(QBrush(fill_color))
        painter.drawRoundedRect(int(track_x), track_y, int(handle_x - track_x), self.track_height, 4, 4)
        # Square off right edge
        painter.drawRect(int(handle_x - 4), track_y, 4, self.track_height)

        # Draw handle
        self._draw_handle(painter, handle_x, height // 2)

    def _draw_handle(self, painter, x, y):
        """Draw handle with depth and modern styling (matching MultiHandleSlider)"""
        # Get theme colors from palette
        palette = QApplication.palette()
        handle_border_color = palette.color(QPalette.Mid)
        highlight_color = palette.color(QPalette.Highlight)
        button_color = palette.color(QPalette.Button)

        # Draw shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 80)))
        painter.drawEllipse(QPointF(x + 2, y + 2), self.handle_radius, self.handle_radius)

        # Draw outer glow for active handle
        if self.active:
            glow_color = QColor(highlight_color)
            glow_color.setAlpha(60)
            painter.setBrush(QBrush(glow_color))
            painter.drawEllipse(QPointF(x, y), self.handle_radius + 3, self.handle_radius + 3)

        # Draw handle with gradient
        gradient = QLinearGradient(x, y - self.handle_radius, x, y + self.handle_radius)
        gradient.setColorAt(0, palette.color(QPalette.Light))
        gradient.setColorAt(1, button_color)
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(handle_border_color, 2))
        painter.drawEllipse(QPointF(x, y), self.handle_radius, self.handle_radius)

        # Draw inner indicator/grip
        if self.active:
            painter.setBrush(QBrush(highlight_color))
        else:
            painter.setBrush(QBrush(palette.color(QPalette.Mid)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(x, y), self.handle_radius - 4, self.handle_radius - 4)

    def _value_to_pixel(self, value):
        """Convert value to pixel position"""
        track_width = self.width() - 2 * self.margin
        ratio = (value - self.minimum) / (self.maximum - self.minimum)
        return self.margin + ratio * track_width

    def _pixel_to_value(self, pixel):
        """Convert pixel position to value"""
        track_width = self.width() - 2 * self.margin
        ratio = (pixel - self.margin) / track_width
        value = self.minimum + ratio * (self.maximum - self.minimum)
        return max(self.minimum, min(self.maximum, value))

    def _is_over_handle(self, x, y):
        """Check if position is over handle"""
        center_y = self.height() // 2
        handle_x = self._value_to_pixel(self.value)

        dx = x - handle_x
        dy = y - center_y
        distance = (dx ** 2 + dy ** 2) ** 0.5

        return distance <= self.handle_radius + 5

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._is_over_handle(event.x(), event.y()):
                self.active = True
                self.update()

    def mouseMoveEvent(self, event):
        if self.active:
            new_value = int(self._pixel_to_value(event.x()))
            if new_value != self.value:
                self.value = new_value
                self.update()
                self.valueChanged.emit(self.value)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.active = False
            self.update()


class MultiHandleSlider(QWidget):
    """
    A slider with multiple draggable handles and colored sections.

    For trigger settings:
    - 3 handles: deadzone_bottom, actuation, deadzone_top
    - Constraint: deadzone_bottom <= actuation <= deadzone_top

    For rapid trigger:
    - 2 handles: press_sens, release_sens
    """

    valuesChanged = pyqtSignal(list)  # Emits list of all handle values

    def __init__(self, num_handles=3, minimum=0, maximum=100, parent=None):
        super().__init__(parent)
        self.num_handles = num_handles
        self.minimum = minimum
        self.maximum = maximum

        # Handle values (positions)
        self.values = []
        for i in range(num_handles):
            # Default spacing
            self.values.append(minimum + (maximum - minimum) * (i + 1) / (num_handles + 1))

        # Handle being dragged
        self.active_handle = None

        # Visual settings
        self.handle_radius = 10
        self.track_height = 8
        self.margin = 25  # Space on left/right for handles

        # Color scheme will be fetched from palette at paint time
        self.track_bg_color = None  # Will use palette
        self.handle_color = None  # Will use palette
        self.handle_border_color = None  # Will use palette

        # Section colors will be set dynamically using theme colors
        # Gray deadzone color is kept constant as requested
        self.deadzone_gray = QColor(80, 80, 85)  # Keep deadzone gray constant
        self.section_colors = None  # Will be set at paint time
        self.rf_section_colors = None  # Will be set at paint time

        self.setMinimumHeight(40)
        self.setMinimumWidth(200)

        # Labels for handles (optional)
        self.handle_labels = []

    def set_values(self, values):
        """Set all handle values at once"""
        if len(values) != self.num_handles:
            return
        self.values = list(values)
        self.update()

    def set_value(self, handle_index, value, emit_signal=True):
        """Set a specific handle value"""
        if 0 <= handle_index < self.num_handles:
            self.values[handle_index] = max(self.minimum, min(self.maximum, value))
            self.update()
            if emit_signal:
                self.valuesChanged.emit(self.values)

    def get_values(self):
        """Get all handle values"""
        return list(self.values)

    def set_handle_labels(self, labels):
        """Set labels to display below each handle"""
        self.handle_labels = labels
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get theme colors from palette
        palette = QApplication.palette()
        track_bg_color = palette.color(QPalette.AlternateBase)
        press_color = palette.color(QPalette.Highlight)
        release_color = palette.color(QPalette.Link)

        # Set up section colors dynamically with theme colors (keep deadzone gray constant)
        self.section_colors = [
            self.deadzone_gray,  # Before deadzone bottom (gray)
            press_color,  # Theme highlight - trigger zone (between deadzone_bottom and actuation)
            release_color,  # Theme link - release zone (between actuation and deadzone_top)
            self.deadzone_gray,  # After deadzone top (gray)
        ]

        self.rf_section_colors = [
            press_color,  # Theme highlight - press zone (from left)
            QColor(100, 100, 105),  # Gray - unused middle section
            release_color,  # Theme link - release zone (from right)
        ]

        width = self.width()
        height = self.height()

        # Calculate track geometry
        track_y = height // 2 - self.track_height // 2
        track_x = self.margin
        track_width = width - 2 * self.margin

        # Draw background track with shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 40)))
        painter.drawRoundedRect(track_x + 1, track_y + 1, track_width, self.track_height, 4, 4)

        # Draw background track
        painter.setBrush(QBrush(track_bg_color))
        painter.drawRoundedRect(track_x, track_y, track_width, self.track_height, 4, 4)

        # Draw colored sections
        self._draw_sections(painter, track_x, track_y, track_width)

        # Draw handles
        for i, value in enumerate(self.values):
            pos_x = self._value_to_pixel(value)
            self._draw_handle(painter, pos_x, height // 2, i)

        # Draw labels
        if self.handle_labels and len(self.handle_labels) == self.num_handles:
            painter.setPen(QPen(palette.color(QPalette.Text)))
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)

            for i, label in enumerate(self.handle_labels):
                pos_x = self._value_to_pixel(self.values[i])
                # Draw label below handle
                label_rect = QRectF(pos_x - 30, height // 2 + self.handle_radius + 5, 60, 15)
                painter.drawText(label_rect, Qt.AlignCenter, label)

    def _draw_sections(self, painter, track_x, track_y, track_width):
        """Draw colored sections between handles with rounded corners"""
        # Get handle positions
        positions = [track_x] + [self._value_to_pixel(v) for v in self.values] + [track_x + track_width]

        colors = self.section_colors if self.num_handles == 3 else self.rf_section_colors

        # Draw each section with rounded corners at edges
        for i in range(len(positions) - 1):
            x1 = positions[i]
            x2 = positions[i + 1]

            if x2 - x1 > 0:
                painter.setBrush(QBrush(colors[i]))
                painter.setPen(Qt.NoPen)

                # Use rounded rectangle only for first and last sections
                if i == 0:
                    # First section - round left corners only
                    painter.drawRoundedRect(int(x1), track_y, int(x2 - x1), self.track_height, 4, 4)
                    # Cover right side to make it square
                    painter.drawRect(int(x2 - 4), track_y, 4, self.track_height)
                elif i == len(positions) - 2:
                    # Last section - round right corners only
                    painter.drawRoundedRect(int(x1), track_y, int(x2 - x1), self.track_height, 4, 4)
                    # Cover left side to make it square
                    painter.drawRect(int(x1), track_y, 4, self.track_height)
                else:
                    # Middle sections - no rounding
                    painter.drawRect(int(x1), track_y, int(x2 - x1), self.track_height)

    def _draw_handle(self, painter, x, y, index):
        """Draw a single handle with depth and modern styling"""
        # Get theme colors from palette
        palette = QApplication.palette()
        handle_border_color = palette.color(QPalette.Mid)
        highlight_color = palette.color(QPalette.Highlight)
        button_color = palette.color(QPalette.Button)

        # Draw shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 80)))
        painter.drawEllipse(QPointF(x + 2, y + 2), self.handle_radius, self.handle_radius)

        # Draw outer glow for active handle
        if index == self.active_handle:
            glow_color = QColor(highlight_color)
            glow_color.setAlpha(60)
            painter.setBrush(QBrush(glow_color))
            painter.drawEllipse(QPointF(x, y), self.handle_radius + 3, self.handle_radius + 3)

        # Draw handle with gradient
        gradient = QLinearGradient(x, y - self.handle_radius, x, y + self.handle_radius)
        gradient.setColorAt(0, palette.color(QPalette.Light))
        gradient.setColorAt(1, button_color)
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(handle_border_color, 2))
        painter.drawEllipse(QPointF(x, y), self.handle_radius, self.handle_radius)

        # Draw inner indicator/grip
        if index == self.active_handle:
            painter.setBrush(QBrush(highlight_color))
        else:
            painter.setBrush(QBrush(palette.color(QPalette.Mid)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(x, y), self.handle_radius - 4, self.handle_radius - 4)

    def _value_to_pixel(self, value):
        """Convert value to pixel position"""
        track_width = self.width() - 2 * self.margin
        ratio = (value - self.minimum) / (self.maximum - self.minimum)
        return self.margin + ratio * track_width

    def _pixel_to_value(self, pixel):
        """Convert pixel position to value"""
        track_width = self.width() - 2 * self.margin
        ratio = (pixel - self.margin) / track_width
        value = self.minimum + ratio * (self.maximum - self.minimum)
        return max(self.minimum, min(self.maximum, value))

    def _get_handle_at_position(self, x, y):
        """Get handle index at position, or None - check in reverse order for topmost"""
        center_y = self.height() // 2

        # Check each handle in REVERSE order (so topmost/last-drawn handles are checked first)
        for i in range(len(self.values) - 1, -1, -1):
            handle_x = self._value_to_pixel(self.values[i])

            # Check if click is within handle circle
            dx = x - handle_x
            dy = y - center_y
            distance = (dx ** 2 + dy ** 2) ** 0.5

            if distance <= self.handle_radius + 5:  # 5px tolerance
                return i

        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.active_handle = self._get_handle_at_position(event.x(), event.y())
            if self.active_handle is not None:
                self.update()

    def mouseMoveEvent(self, event):
        if self.active_handle is not None:
            new_value = self._pixel_to_value(event.x())

            # Apply constraints based on handle type
            new_value = self._apply_constraints(self.active_handle, new_value)

            if new_value != self.values[self.active_handle]:
                self.values[self.active_handle] = new_value
                self.update()
                self.valuesChanged.emit(self.get_values())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.active_handle = None
            self.update()

    def _apply_constraints(self, handle_index, new_value):
        """Apply constraints to handle movement"""
        if self.num_handles == 3:
            # For 3-handle mode (deadzone_bottom, actuation, deadzone_top)
            if handle_index == 0:  # Deadzone bottom
                # Must be less than actuation
                max_val = self.values[1] - 1
                return max(self.minimum, min(new_value, max_val))
            elif handle_index == 1:  # Actuation
                # Must be between deadzones
                min_val = self.values[0] + 1
                max_val = self.values[2] - 1
                return max(min_val, min(new_value, max_val))
            elif handle_index == 2:  # Deadzone top
                # Must be greater than actuation
                min_val = self.values[1] + 1
                return max(min_val, min(new_value, self.maximum))

        elif self.num_handles == 2:
            # For 2-handle mode (no strict ordering required)
            # But typically press_sens should be <= release_sens
            return max(self.minimum, min(new_value, self.maximum))

        return new_value


# Minimum actuation point the user is allowed to set, on the 0-255 = 0-4.0mm
# scale. 7 = round(0.11/4 * 255) = 0.11mm. Kept in sync with the firmware's
# MIN_ACTUATION_DISTANCE floor in matrix.c so the GUI never offers an actuation
# the device would silently raise anyway (values below 0.1mm are disallowed).
MIN_ACTUATION_VALUE = 7


class TriggerSlider(MultiHandleSlider):
    """
    Specialized slider for trigger settings with 3 handles:
    - Deadzone bottom (from left: 0-20, where 0=0mm, 20=0.5mm)
    - Actuation point (normal: 0-100)
    - Deadzone top (from right: 0-20, where 0=0mm from top, 20=0.5mm from top)

    Deadzone top is inverted - stored internally as (100 - user_value)
    """

    deadzoneBottomChanged = pyqtSignal(int)
    actuationChanged = pyqtSignal(int)
    deadzoneTopChanged = pyqtSignal(int)

    def __init__(self, minimum=0, maximum=255, parent=None):
        super().__init__(num_handles=3, minimum=minimum, maximum=maximum, parent=parent)

        # Set default values: bottom=6 (~0.1mm), actuation=127 (2.0mm), top=249 (which is 6 from right)
        # Internal representation: [deadzone_bottom, actuation, 255 - deadzone_top]
        # Note: 0-255 range represents 0-4.0mm full key travel
        # Deadzones are limited to 0-51 (20% of 255) representing 0-0.8mm
        self.values = [6, 127, 249]  # 249 = 255 - 6

        # Store the actual user-facing deadzone_top value (inverted)
        self._user_deadzone_top = 6

        # Connect to emit individual signals
        self.valuesChanged.connect(self._on_values_changed)

    def _on_values_changed(self, values):
        """Emit individual signals for each handle"""
        self.deadzoneBottomChanged.emit(int(values[0]))
        self.actuationChanged.emit(int(values[1]))
        # For deadzone_top, emit the inverted value (distance from right)
        inverted_top = 255 - int(values[2])
        self._user_deadzone_top = inverted_top
        self.deadzoneTopChanged.emit(inverted_top)

    def set_deadzone_bottom(self, value):
        """Set deadzone bottom value (0-51 = 20% of travel)"""
        self.set_value(0, value)

    def set_actuation(self, value):
        """Set actuation point value (0-255), floored at the 0.11mm minimum"""
        if value < MIN_ACTUATION_VALUE:
            value = MIN_ACTUATION_VALUE
        self.set_value(1, value)

    def set_deadzone_top(self, value):
        """Set deadzone top value (0-51, inverted internally)"""
        # Convert user value (distance from top) to internal position
        self._user_deadzone_top = value
        internal_value = 255 - value
        self.set_value(2, internal_value)

    def get_deadzone_bottom(self):
        """Get deadzone bottom value"""
        return int(self.values[0])

    def get_actuation(self):
        """Get actuation point value"""
        return int(self.values[1])

    def get_deadzone_top(self):
        """Get deadzone top value (user-facing, inverted)"""
        return self._user_deadzone_top

    def paintEvent(self, event):
        """Override to draw actuation point marker"""
        super().paintEvent(event)

        # Draw actuation point marker line (handle 1)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get theme highlight color
        palette = QApplication.palette()
        marker_color = palette.color(QPalette.Highlight)

        height = self.height()
        track_y = height // 2 - self.track_height // 2
        actuation_x = self._value_to_pixel(self.values[1])

        # Draw marker line above and below the actuation point
        painter.setPen(QPen(marker_color, 3))  # Theme highlight color
        painter.drawLine(int(actuation_x), track_y - 10, int(actuation_x), track_y - 2)
        painter.drawLine(int(actuation_x), track_y + self.track_height + 2, int(actuation_x), track_y + self.track_height + 10)

    def _apply_constraints(self, handle_index, new_value):
        """Apply constraints to handle movement
        Range is 0-255 representing 0-4.0mm travel
        Deadzone max is 51 (0.8mm = 20% of travel)
        """
        DEADZONE_MAX = 51  # 0.8mm max deadzone (20% of 255)

        if handle_index == 0:  # Deadzone bottom
            # Can go from 0 to DEADZONE_MAX, but must not exceed actuation minus gap
            max_val = min(self.values[1] - 1, DEADZONE_MAX)
            return max(self.minimum, min(new_value, max_val))
        elif handle_index == 1:  # Actuation
            # Must be between deadzones with gaps, and never below the 0.11mm floor
            min_val = max(self.values[0] + 1, MIN_ACTUATION_VALUE)  # >= deadzone bottom + 1 and >= 0.11mm
            max_val = self.values[2] - 1  # At least 1 below deadzone top
            return max(min_val, min(new_value, max_val))
        elif handle_index == 2:  # Deadzone top (inverted)
            # Internal range is (255 - DEADZONE_MAX) to 255, i.e., 204 to 255
            # Must not go below actuation plus gap, and must stay above 204 (max 0.8mm from top)
            min_val = max(self.values[1] + 1, 255 - DEADZONE_MAX)  # At least 204 (0.8mm from top)
            return max(min_val, min(new_value, self.maximum))

        return new_value


class RapidTriggerSlider(MultiHandleSlider):
    """
    Specialized slider for rapid trigger settings with 2 handles:
    - Press sensitivity (from left: 1 to midpoint, in firmware 0-255 distance units)
    - Release sensitivity (from right: 1 to midpoint, inverted internally)

    Both values are in firmware distance units (0-255 = 0-4.0mm).
    Release is inverted - stored internally as (maximum + 1 - user_value).
    A center divider splits the slider into equal halves.
    """

    pressSensChanged = pyqtSignal(int)
    releaseSensChanged = pyqtSignal(int)

    def __init__(self, minimum=1, maximum=255, parent=None):
        super().__init__(num_handles=2, minimum=minimum, maximum=maximum, parent=parent)

        # Calculate the midpoint and inversion offset dynamically
        self._midpoint = (minimum + maximum) // 2  # 128 for 1-255, 50 for 1-100
        self._invert_offset = maximum + 1           # 256 for max=255, 101 for max=100

        # Set default values: press=6 (~0.09mm), release inverted = 256-6 = 250
        default_sens = 6
        self.values = [max(minimum, default_sens), self._invert_offset - default_sens]

        # Store the actual user-facing release value (inverted)
        self._user_release = default_sens

        # Connect to emit individual signals
        self.valuesChanged.connect(self._on_values_changed)

    def _on_values_changed(self, values):
        """Emit individual signals for each handle"""
        self.pressSensChanged.emit(int(values[0]))
        # For release, emit the inverted value (distance from right)
        inverted_release = self._invert_offset - int(values[1])
        self._user_release = inverted_release
        self.releaseSensChanged.emit(inverted_release)

    def set_press_sens(self, value):
        """Set press sensitivity value (1 to midpoint, in firmware 0-255 units)"""
        clamped_value = max(self.minimum, min(value, self._midpoint))
        self.set_value(0, clamped_value)

    def set_release_sens(self, value):
        """Set release sensitivity value (1 to midpoint, inverted internally)"""
        # Convert user value (distance from right) to internal position
        clamped_value = max(self.minimum, min(value, self._midpoint))
        self._user_release = clamped_value
        internal_value = self._invert_offset - clamped_value
        self.set_value(1, internal_value)

    def get_press_sens(self):
        """Get press sensitivity value"""
        return int(self.values[0])

    def get_release_sens(self):
        """Get release sensitivity value (user-facing, inverted)"""
        return self._user_release

    def paintEvent(self, event):
        """Override to draw sections and center divider"""
        # Call grandparent paintEvent but not parent to customize section drawing
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get theme colors from palette
        palette = QApplication.palette()
        track_bg_color = palette.color(QPalette.AlternateBase)
        press_color = palette.color(QPalette.Highlight)
        release_color = palette.color(QPalette.Link)
        divider_color = palette.color(QPalette.Mid)

        width = self.width()
        height = self.height()

        # Calculate track geometry
        track_y = height // 2 - self.track_height // 2
        track_x = self.margin
        track_width = width - 2 * self.margin

        # Draw background track with shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 40)))
        painter.drawRoundedRect(track_x + 1, track_y + 1, track_width, self.track_height, 4, 4)

        # Draw background track
        painter.setBrush(QBrush(track_bg_color))
        painter.drawRoundedRect(track_x, track_y, track_width, self.track_height, 4, 4)

        # Draw 3 colored sections: press (theme highlight), middle (gray), release (theme link)
        press_x = self._value_to_pixel(self.values[0])  # Press handle position
        release_x = self._value_to_pixel(self.values[1])  # Release handle position

        # Section 1: Press (from left to press handle) - theme highlight
        painter.setBrush(QBrush(press_color))
        painter.drawRoundedRect(int(track_x), track_y, int(press_x - track_x), self.track_height, 4, 4)
        painter.drawRect(int(press_x - 4), track_y, 4, self.track_height)  # Square off right edge

        # Section 2: Gray (from press handle to release handle - unused middle)
        painter.setBrush(QBrush(QColor(100, 100, 105)))  # Keep gray for middle section
        painter.drawRect(int(press_x), track_y, int(release_x - press_x), self.track_height)

        # Section 3: Release (from release handle to right) - theme link
        painter.setBrush(QBrush(release_color))
        painter.drawRoundedRect(int(release_x), track_y, int(track_x + track_width - release_x), self.track_height, 4, 4)
        painter.drawRect(int(release_x), track_y, 4, self.track_height)  # Square off left edge

        # Draw handles
        for i, value in enumerate(self.values):
            pos_x = self._value_to_pixel(value)
            self._draw_handle(painter, pos_x, height // 2, i)

        # Draw center divider line at the midpoint
        divider_x = track_x + ((self._midpoint - self.minimum) / (self.maximum - self.minimum)) * track_width
        painter.setPen(QPen(divider_color, 2))
        painter.drawLine(int(divider_x), track_y - 5, int(divider_x), track_y + self.track_height + 5)

    def _apply_constraints(self, handle_index, new_value):
        """Apply constraints to prevent overlap - each side limited to midpoint"""
        if handle_index == 0:  # Press sensitivity (from left)
            # Must stay in left half: minimum to midpoint
            return max(self.minimum, min(new_value, self._midpoint))
        elif handle_index == 1:  # Release sensitivity (from right, inverted)
            # Must stay in right half: midpoint+1 to maximum
            return max(self._midpoint + 1, min(new_value, self.maximum))
        return max(self.minimum, min(new_value, self.maximum))


class DualRangeSlider(QWidget):
    """
    A simple dual-handle range slider for selecting min/max values.
    Handles cannot cross each other.
    """

    range_changed = pyqtSignal(int, int)  # (low_value, high_value)

    def __init__(self, minimum=0, maximum=100, parent=None):
        super().__init__(parent)
        self._minimum = minimum
        self._maximum = maximum
        self._low_value = minimum
        self._high_value = maximum
        self._active_handle = None  # 'low', 'high', or None
        self._hover_handle = None

        # Visual settings
        self.handle_radius = 8
        self.track_height = 6
        self.margin = 20  # Increased margin for labels
        self.show_labels = True  # Show min/max labels below handles

        self.setMinimumHeight(45)  # Increased to fit labels below handles
        self.setMinimumWidth(150)
        self.setMouseTracking(True)

    def minimum(self):
        return self._minimum

    def maximum(self):
        return self._maximum

    def setRange(self, minimum, maximum):
        self._minimum = minimum
        self._maximum = maximum
        self._low_value = max(minimum, min(self._low_value, maximum))
        self._high_value = max(minimum, min(self._high_value, maximum))
        self.update()

    def lowValue(self):
        return self._low_value

    def highValue(self):
        return self._high_value

    def setLowValue(self, value):
        # Ensure at least 1 unit gap from high value
        value = max(self._minimum, min(value, self._high_value - 1))
        if value != self._low_value:
            self._low_value = value
            self.update()
            self.range_changed.emit(self._low_value, self._high_value)

    def setHighValue(self, value):
        # Ensure at least 1 unit gap from low value
        value = max(self._low_value + 1, min(value, self._maximum))
        if value != self._high_value:
            self._high_value = value
            self.update()
            self.range_changed.emit(self._low_value, self._high_value)

    def setValues(self, low, high):
        """Set both values at once, ensuring at least 1 unit gap"""
        low = max(self._minimum, min(low, self._maximum - 1))
        high = max(self._minimum + 1, min(high, self._maximum))
        if low >= high:
            # Ensure gap of at least 1
            high = low + 1
            if high > self._maximum:
                high = self._maximum
                low = high - 1
        self._low_value = low
        self._high_value = high
        self.update()

    def _value_to_x(self, value):
        track_width = self.width() - 2 * self.margin
        if self._maximum == self._minimum:
            return self.margin
        ratio = (value - self._minimum) / (self._maximum - self._minimum)
        return int(self.margin + ratio * track_width)

    def _x_to_value(self, x):
        track_width = self.width() - 2 * self.margin
        if track_width == 0:
            return self._minimum
        ratio = (x - self.margin) / track_width
        ratio = max(0, min(1, ratio))
        return int(self._minimum + ratio * (self._maximum - self._minimum))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        palette = QApplication.palette()
        track_bg = palette.color(QPalette.AlternateBase)
        fill_color = palette.color(QPalette.Highlight)
        text_color = palette.color(QPalette.Text)

        height = self.height()
        # Adjust track position to leave room for labels below
        track_y = 12  # Fixed position near top

        # Draw track background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(track_bg))
        painter.drawRoundedRect(self.margin, track_y,
                                self.width() - 2 * self.margin,
                                self.track_height, 3, 3)

        # Draw selected range
        low_x = self._value_to_x(self._low_value)
        high_x = self._value_to_x(self._high_value)
        painter.setBrush(QBrush(fill_color))
        painter.drawRoundedRect(low_x, track_y, high_x - low_x, self.track_height, 3, 3)

        # Draw handles
        handle_y = track_y + self.track_height // 2
        for which, value in [('low', self._low_value), ('high', self._high_value)]:
            x = self._value_to_x(value)

            if self._active_handle == which or self._hover_handle == which:
                painter.setBrush(QBrush(QColor(255, 200, 100)))
            else:
                painter.setBrush(QBrush(palette.color(QPalette.Button)))

            painter.setPen(QPen(palette.color(QPalette.Mid), 1))
            painter.drawEllipse(QPointF(x, handle_y), self.handle_radius, self.handle_radius)

        # Draw min/max labels below handles with small arrows
        if self.show_labels:
            from PyQt5.QtGui import QFont, QFontMetrics
            font = painter.font()
            font.setPointSize(9)  # Bigger font for readability
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(text_color)

            # Label positions - below handles
            label_y = track_y + self.track_height + self.handle_radius + 14

            # Min label with up arrow
            min_text = "▲ min"
            fm = QFontMetrics(font)
            min_width = fm.width(min_text)
            painter.drawText(int(low_x - min_width // 2), int(label_y), min_text)

            # Max label with up arrow
            max_text = "▲ max"
            max_width = fm.width(max_text)
            painter.drawText(int(high_x - max_width // 2), int(label_y), max_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            x, y = event.x(), event.y()
            low_x = self._value_to_x(self._low_value)
            high_x = self._value_to_x(self._high_value)
            # Handle y position matches paintEvent
            track_y = 12
            cy = track_y + self.track_height // 2

            # Check handles
            dist_low = ((x - low_x) ** 2 + (y - cy) ** 2) ** 0.5
            dist_high = ((x - high_x) ** 2 + (y - cy) ** 2) ** 0.5

            if dist_low <= self.handle_radius + 5:
                self._active_handle = 'low'
            elif dist_high <= self.handle_radius + 5:
                self._active_handle = 'high'
            else:
                # Click on track - move nearest handle
                if abs(x - low_x) < abs(x - high_x):
                    self._active_handle = 'low'
                    self.setLowValue(self._x_to_value(x))
                else:
                    self._active_handle = 'high'
                    self.setHighValue(self._x_to_value(x))
            self.update()

    def mouseMoveEvent(self, event):
        if self._active_handle:
            value = self._x_to_value(event.x())
            if self._active_handle == 'low':
                value = min(value, self._high_value)
                self.setLowValue(value)
            else:
                value = max(value, self._low_value)
                self.setHighValue(value)
        else:
            # Update hover
            x, y = event.x(), event.y()
            low_x = self._value_to_x(self._low_value)
            high_x = self._value_to_x(self._high_value)
            # Handle y position matches paintEvent
            track_y = 12
            cy = track_y + self.track_height // 2

            old_hover = self._hover_handle
            dist_low = ((x - low_x) ** 2 + (y - cy) ** 2) ** 0.5
            dist_high = ((x - high_x) ** 2 + (y - cy) ** 2) ** 0.5

            if dist_low <= self.handle_radius + 5:
                self._hover_handle = 'low'
            elif dist_high <= self.handle_radius + 5:
                self._hover_handle = 'high'
            else:
                self._hover_handle = None

            if old_hover != self._hover_handle:
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._active_handle = None
            self.update()

    def leaveEvent(self, event):
        self._hover_handle = None
        self.update()

