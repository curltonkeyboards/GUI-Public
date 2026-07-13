# SPDX-License-Identifier: GPL-2.0-or-later
import struct
import logging
from datetime import datetime
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QPalette
from PyQt5.QtWidgets import (QWidget, QPushButton, QHBoxLayout, QVBoxLayout,
                             QLabel, QGroupBox, QMessageBox, QGridLayout,
                             QComboBox, QSpinBox, QLineEdit, QScrollArea,
                             QFrame, QButtonGroup, QRadioButton, QCheckBox, QSlider,
                             QInputDialog, QTabWidget, QDialog, QDialogButtonBox,
                             QApplication, QToolButton, QTextEdit, QSizePolicy)

from editor.basic_editor import BasicEditor
from util import tr
from vial_device import VialKeyboard
from widgets.combo_box import ArrowComboBox

logger = logging.getLogger(__name__)


# =============================================================================
# DEBUG CONSOLE WIDGET
# =============================================================================

class DebugConsole(QWidget):
    """Collapsible debug console for logging HID commands and save operations.

    Provides a text log with timestamps, color-coded messages, and buttons
    to copy the log to clipboard or clear it.
    """

    def __init__(self, title="Debug Console", parent=None):
        super().__init__(parent)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toggle button to show/hide console
        self.btn_toggle = QPushButton(f">>> {title}")
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setChecked(False)
        self.btn_toggle.setStyleSheet(
            "QPushButton { text-align: left; padding: 4px 8px; "
            "border: 1px solid gray; border-radius: 3px; font-weight: bold; }"
            "QPushButton:checked { border-bottom-left-radius: 0px; "
            "border-bottom-right-radius: 0px; }"
        )
        self.btn_toggle.clicked.connect(self._toggle_console)
        layout.addWidget(self.btn_toggle)

        # Console container (hidden by default)
        self.console_container = QWidget()
        console_layout = QVBoxLayout()
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(4)

        # Text display
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 9) if QFont("Consolas").exactMatch()
                               else QFont("Monospace", 9))
        self.text_edit.setMinimumHeight(120)
        self.text_edit.setMaximumHeight(200)
        self.text_edit.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #cccccc; "
            "border: 1px solid gray; border-top: none; padding: 4px; }"
        )
        console_layout.addWidget(self.text_edit)

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        btn_style = ("QPushButton { min-height: 24px; max-height: 24px; "
                     "padding: 2px 12px; border-radius: 3px; }")

        self.btn_copy = QPushButton("Copy Log")
        self.btn_copy.setStyleSheet(btn_style)
        self.btn_copy.setToolTip("Copy entire debug log to clipboard")
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        btn_layout.addWidget(self.btn_copy)

        self.btn_copy_last = QPushButton("Copy Last Operation")
        self.btn_copy_last.setStyleSheet(btn_style)
        self.btn_copy_last.setToolTip("Copy log entries from the last save/load operation")
        self.btn_copy_last.clicked.connect(self._copy_last_operation)
        btn_layout.addWidget(self.btn_copy_last)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setStyleSheet(btn_style)
        self.btn_clear.setToolTip("Clear all debug log entries")
        self.btn_clear.clicked.connect(self._clear_log)
        btn_layout.addWidget(self.btn_clear)

        btn_layout.addStretch()
        console_layout.addLayout(btn_layout)

        self.console_container.setLayout(console_layout)
        self.console_container.setVisible(False)
        layout.addWidget(self.console_container)

        self.setLayout(layout)

        # Track operation boundaries for "Copy Last Operation"
        self._last_operation_start = 0
        self._plain_log = []  # Store plain text entries for clipboard

    def _toggle_console(self, checked):
        """Toggle console visibility"""
        self.console_container.setVisible(checked)
        title = self.btn_toggle.text().replace(">>> ", "").replace("<<< ", "")
        if checked:
            self.btn_toggle.setText(f"<<< {title}")
        else:
            self.btn_toggle.setText(f">>> {title}")

    def log(self, message, level="INFO"):
        """Append a timestamped message to the debug console.

        Args:
            message: The log message text
            level: One of 'INFO', 'ERROR', 'WARN', 'DEBUG', 'HID_TX', 'HID_RX', 'DATA'
        """
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        color_map = {
            "INFO": "#cccccc",
            "ERROR": "#ff6b6b",
            "WARN": "#ffd93d",
            "DEBUG": "#888888",
            "HID_TX": "#6bcfff",
            "HID_RX": "#6bff8a",
            "DATA": "#c4a7ff",
        }
        color = color_map.get(level, "#cccccc")

        # Plain text entry for clipboard
        plain_entry = f"[{timestamp}] [{level:6s}] {message}"
        self._plain_log.append(plain_entry)

        # HTML formatted entry for display
        html = (f'<span style="color:#888;">[{timestamp}]</span> '
                f'<span style="color:{color};font-weight:bold;">[{level:6s}]</span> '
                f'<span style="color:{color};">{message}</span>')
        self.text_edit.append(html)

        # Auto-scroll to bottom
        scrollbar = self.text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def mark_operation_start(self):
        """Mark the start of a new operation (save/load) for 'Copy Last Operation'"""
        self._last_operation_start = len(self._plain_log)
        self.log("--- Operation started ---", "DEBUG")

    def mark_operation_end(self, success=True):
        """Mark the end of an operation"""
        status = "COMPLETED" if success else "FAILED"
        self.log(f"--- Operation {status} ---", "DEBUG")

    def _copy_to_clipboard(self):
        """Copy the entire log to system clipboard"""
        clipboard = QApplication.clipboard()
        text = "\n".join(self._plain_log)
        if not text:
            text = "(empty log)"
        clipboard.setText(text)
        self.log("Log copied to clipboard", "DEBUG")

    def _copy_last_operation(self):
        """Copy only the last operation's log entries to clipboard"""
        clipboard = QApplication.clipboard()
        if self._last_operation_start < len(self._plain_log):
            entries = self._plain_log[self._last_operation_start:]
            text = "\n".join(entries)
        else:
            text = "(no operation logged yet)"
        clipboard.setText(text)
        self.log("Last operation log copied to clipboard", "DEBUG")

    def _clear_log(self):
        """Clear the debug log"""
        self.text_edit.clear()
        self._plain_log.clear()
        self._last_operation_start = 0
        self.log("Console cleared", "DEBUG")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def flat_semitones_to_interval_octave(flat_semitones):
    """
    Convert flat semitones to (interval, octave) pair for firmware.
    Examples:
        +29 → (interval=+5, octave=+2)
        -1 → (interval=-1, octave=0)
        -13 → (interval=-1, octave=-1)
        +12 → (interval=0, octave=+1)
    """
    # Calculate octave (how many complete 12-semitone octaves)
    octave = flat_semitones // 12
    # Calculate interval within octave (-11 to +11)
    interval = flat_semitones % 12

    # Handle negative intervals properly
    # If we have a negative remainder, adjust
    if flat_semitones < 0 and interval != 0:
        octave -= 1
        interval = 12 + interval

    return interval, octave


def interval_octave_to_flat_semitones(interval, octave):
    """
    Convert (interval, octave) pair to flat semitones.
    Examples:
        (interval=+5, octave=+2) → +29
        (interval=-1, octave=0) → -1
        (interval=-1, octave=-1) → -13
        (interval=0, octave=+1) → +12
    """
    return interval + (octave * 12)


# =============================================================================
# GRID-BASED INTERFACE WIDGETS (for Basic Tab)
# =============================================================================

class GridCell(QFrame):
    """Individual grid cell for Basic tab - handles clicks and visual state"""

    leftClicked = pyqtSignal(int, int)  # row, col
    rightClicked = pyqtSignal(int, int)  # row, col
    dragEntered = pyqtSignal(int, int)  # row, col - emitted when mouse drags into this cell

    def __init__(self, row, col, parent=None):
        super().__init__(parent)
        self.row = row
        self.col = col
        self.active = False
        self.velocity = 255  # Default velocity (max)
        self.octave = 0  # For arpeggiator only
        self.is_tie = False  # True = sustained from previous step, False = retrigger
        self.in_scale = True  # Default to in scale (for scale filtering)

        # Set size based on whether this is step sequencer or arpeggiator
        if hasattr(parent, 'is_arpeggiator') and not parent.is_arpeggiator:
            # Step sequencer - 50x50
            self.setFixedSize(50, 50)
        else:
            # Arpeggiator - 30x30
            self.setFixedSize(30, 30)
        self.setFrameStyle(QFrame.Box)
        self.setLineWidth(1)

        self.update_style()

    def set_active(self, active, velocity=127, octave=0):
        """Set cell state"""
        self.active = active
        self.velocity = velocity
        self.octave = octave
        self.update_style()

    def get_octave_color(self):
        """Get color based on octave for arpeggiator - uses theme-relative hue shifts"""
        # Get theme highlight color as base - use QApplication.palette() for consistent theme colors
        palette = QApplication.palette()
        highlight = palette.color(QPalette.Highlight)

        # Convert to HSV for hue shifting
        h = highlight.hsvHue()
        s = highlight.hsvSaturation()
        v = highlight.value()

        # Root octave (0) uses the theme color directly
        if self.octave == 0:
            return highlight

        # Apply hue shift based on octave
        # Negative octaves shift hue one direction, positive the other
        # Each octave shifts hue by 30 degrees (360/12 for chromatic scale feel)
        hue_shift = self.octave * 30
        new_hue = (h + hue_shift) % 360

        # Adjust saturation and value based on octave distance from root
        # Further octaves = more saturated and slightly darker
        octave_distance = abs(self.octave)
        saturation_boost = min(255, s + (octave_distance * 30))
        value_adjust = max(128, v - (octave_distance * 10))

        color = QColor.fromHsv(new_hue, saturation_boost, value_adjust)
        return color if color.isValid() else highlight

    def update_style(self):
        """Update visual appearance based on state"""
        # Get theme colors - use QApplication.palette() for consistent theme colors
        # Using self.palette() can return inconsistent values after stylesheets are applied
        palette = QApplication.palette()
        bg_color = palette.color(QPalette.Window)
        highlight = palette.color(QPalette.Highlight)

        # Determine if light or dark theme
        is_light_theme = bg_color.lightness() > 128

        # Use theme-based border colors (no special border for column 0)
        border_color_qcolor = highlight.darker(150) if self.active else highlight.darker(300)
        border_color = border_color_qcolor.name()
        border_width = 1

        if self.active:
            # Intensity based on velocity (velocity is 0-255, display as 0-127)
            intensity = self.velocity / 255.0

            # For arpeggiator, blend with octave color
            if hasattr(self.parent(), 'is_arpeggiator') and self.parent().is_arpeggiator:
                octave_color = self.get_octave_color()

                # On light themes: darken only (no brightening)
                # On dark themes: keep current behavior
                if is_light_theme:
                    # Darken: multiply by factor 0.5 to 0.85 based on intensity
                    factor = 0.5 + 0.35 * intensity
                else:
                    # Dark theme: keep current behavior (0.5 to 1.2)
                    factor = 0.5 + 0.7 * intensity

                r = min(255, int(octave_color.red() * factor))
                g = min(255, int(octave_color.green() * factor))
                b = min(255, int(octave_color.blue() * factor))
                color = QColor(r, g, b)
            else:
                # For step sequencer, use theme color with intensity
                # On light themes: darken only (no brightening)
                # On dark themes: keep current behavior
                if is_light_theme:
                    # Darken: multiply by factor 0.5 to 0.85 based on intensity
                    factor = 0.5 + 0.35 * intensity
                else:
                    # Dark theme: keep current behavior (0.5 to 1.2)
                    factor = 0.5 + 0.7 * intensity

                r = min(255, int(highlight.red() * factor))
                g = min(255, int(highlight.green() * factor))
                b = min(255, int(highlight.blue() * factor))
                color = QColor(r, g, b)

            # Use opacity for scale filtering instead of darkening
            opacity = 0.3 if not self.in_scale else 1.0
            # Sustained cells get a dotted border on the step-axis side to show continuation
            if self.is_tie:
                is_arp = hasattr(self.parent(), 'is_arpeggiator') and self.parent().is_arpeggiator
                if is_arp:
                    # Arpeggiator: steps are rows (Y axis), so dotted top border
                    self.setStyleSheet(f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {opacity}); "
                                       f"border: {border_width}px solid {border_color}; "
                                       f"border-top: 3px dotted {border_color}; border-radius: 3px;")
                else:
                    # Step sequencer: steps are columns (X axis), so dotted left border
                    self.setStyleSheet(f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {opacity}); "
                                       f"border: {border_width}px solid {border_color}; "
                                       f"border-left: 3px dotted {border_color}; border-radius: 3px;")
            else:
                self.setStyleSheet(f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {opacity}); border: {border_width}px solid {border_color}; border-radius: 3px;")
        else:
            # Inactive state - use white for light themes, black for dark themes
            inactive_color = QColor(255, 255, 255) if is_light_theme else QColor(0, 0, 0)
            # Use opacity for scale filtering instead of darkening
            opacity = 0.3 if not self.in_scale else 1.0
            self.setStyleSheet(f"background-color: rgba({inactive_color.red()}, {inactive_color.green()}, {inactive_color.blue()}, {opacity}); border: {border_width}px solid {border_color}; border-radius: 3px;")

    def mousePressEvent(self, event):
        """Handle mouse clicks"""
        if event.button() == Qt.LeftButton:
            self.leftClicked.emit(self.row, self.col)
        elif event.button() == Qt.RightButton:
            self.rightClicked.emit(self.row, self.col)

    def enterEvent(self, event):
        """Handle mouse entering cell during drag"""
        if QApplication.mouseButtons() & Qt.LeftButton:
            self.dragEntered.emit(self.row, self.col)
        super().enterEvent(event)

    def mouseReleaseEvent(self, event):
        """Clear drag state in parent grid on mouse release"""
        if event.button() == Qt.LeftButton:
            # Walk up to find the grid widget and clear its drag state
            p = self.parent()
            while p is not None:
                if hasattr(p, '_drag_mode'):
                    p._drag_mode = None
                    break
                p = p.parent()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        """Draw connecting line through sustained cells"""
        super().paintEvent(event)
        if not self.active or not self.is_tie:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Use a contrasting color for the sustain line
        palette = QApplication.palette()
        line_color = palette.color(QPalette.HighlightedText)
        pen = QPen(line_color, 2, Qt.DashLine)
        painter.setPen(pen)

        is_arp = hasattr(self.parent(), 'is_arpeggiator') and self.parent().is_arpeggiator
        w = self.width()
        h = self.height()

        if is_arp:
            # Arpeggiator: steps are rows, draw vertical line from top edge to center
            mid_x = w // 2
            painter.drawLine(mid_x, 0, mid_x, h // 2)
        else:
            # Step sequencer: steps are columns, draw horizontal line from left edge to center
            mid_y = h // 2
            painter.drawLine(0, mid_y, w // 2, mid_y)

        painter.end()


class VelocityOctavePopup(QDialog):
    """Popup dialog for configuring velocity and octave (arpeggiator only)"""

    def __init__(self, velocity, octave=None, allow_negative_octave=True, allow_positive_octave=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cell Configuration")
        self.setModal(True)

        layout = QVBoxLayout()

        # Velocity slider
        vel_label = QLabel("Velocity:")
        layout.addWidget(vel_label)

        self.velocity_slider = QSlider(Qt.Horizontal)
        self.velocity_slider.setRange(1, 255)  # Internal range 1-255
        self.velocity_slider.setValue(velocity)
        self.velocity_slider.valueChanged.connect(self.update_velocity_label)
        layout.addWidget(self.velocity_slider)

        # Velocity value label (display as half: 1-127)
        self.velocity_value_label = QLabel(str(velocity // 2))
        self.velocity_value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.velocity_value_label)

        # Octave spinner (only for arpeggiator)
        self.octave_spinner = None
        if octave is not None:
            oct_label = QLabel("Octave:")
            layout.addWidget(oct_label)

            self.octave_spinner = QSpinBox()

            # Determine min/max based on constraints
            min_octave = -4 if allow_negative_octave else 0
            max_octave = 4 if allow_positive_octave else 0

            self.octave_spinner.setRange(min_octave, max_octave)
            self.octave_spinner.setValue(octave)
            layout.addWidget(self.octave_spinner)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def update_velocity_label(self, value):
        """Update the velocity label to show half the internal value"""
        self.velocity_value_label.setText(str(value // 2))

    def get_values(self):
        """Get configured values"""
        velocity = self.velocity_slider.value()
        octave = self.octave_spinner.value() if self.octave_spinner else 0
        return velocity, octave


class BasicStepSequencerGrid(QWidget):
    """Grid widget for step sequencer basic tab with dynamic rows"""

    dataChanged = pyqtSignal()  # Emitted when grid data changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_arpeggiator = False  # For octave color logic
        self.num_steps = 8  # Default number of columns
        self.default_velocity = 255  # Default velocity for new cells
        self.rows = []  # List of row data: {'note': 0, 'octave': 4, 'cells': [GridCell, ...]}

        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(2)
        self.main_layout.setContentsMargins(5, 5, 5, 5)

        # Create scroll area for grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(2)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.grid_container.setLayout(self.grid_layout)

        scroll.setWidget(self.grid_container)
        self.main_layout.addWidget(scroll, 1)

        self.setLayout(self.main_layout)

        # Create header row (step numbers)
        self.rebuild_header()

        # Create "+" button (will be positioned after rows) - same size as note buttons
        self.btn_add_note = QToolButton()
        self.btn_add_note.setText("+")
        self.btn_add_note.setToolButtonStyle(Qt.ToolButtonTextOnly)
        # Same size as the editable note buttons (50x50)
        self.btn_add_note.setFixedSize(50, 50)
        self.btn_add_note.setCursor(Qt.PointingHandCursor)
        self.btn_add_note.clicked.connect(self.add_note_row)

        # Create "Note" label (will span note rows on left side)
        self.note_title = QLabel("Note")
        self.note_title.setAlignment(Qt.AlignCenter)
        self.note_title.setStyleSheet("font-weight: bold;")

        # Add 4 default rows
        default_notes = [
            ('C', 3),
            ('D', 3),
            ('E', 3),
            ('F', 3)
        ]
        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        for note_name, octave in default_notes:
            note_index = note_names.index(note_name)
            self._create_row(note_index, octave)

        # Position the "+" button after all rows
        self._update_add_button_position()

    def _update_add_button_position(self):
        """Update the position of the '+' button to be after all note rows"""
        self._ensure_add_note_label()

        # Remove the button and label from their current positions if they exist
        try:
            if self.btn_add_note.parent() is not None:
                self.grid_layout.removeWidget(self.btn_add_note)
        except RuntimeError:
            pass
        try:
            if self.add_note_label.parent() is not None:
                self.grid_layout.removeWidget(self.add_note_label)
        except RuntimeError:
            pass

        # Add them at the row after all existing rows (len(self.rows) + 2, accounting for 2 header rows)
        row_position = len(self.rows) + 2

        # Place + button in column 1 (aligned with note buttons)
        self.grid_layout.addWidget(self.btn_add_note, row_position, 1)

        # Add instruction label in column 2 (next to + button)
        self.grid_layout.addWidget(self.add_note_label, row_position, 2, 1, self.num_steps)

    def _ensure_note_title(self):
        """Ensure note_title QLabel exists and is valid (recreate if C++ object was deleted)"""
        try:
            self.note_title.isVisible()
        except (RuntimeError, AttributeError):
            self.note_title = QLabel("Note")
            self.note_title.setAlignment(Qt.AlignCenter)
            self.note_title.setStyleSheet("font-weight: bold;")

    def _ensure_add_note_label(self):
        """Ensure add_note_label QLabel exists and is valid (recreate if C++ object was deleted)"""
        try:
            if hasattr(self, 'add_note_label'):
                self.add_note_label.isVisible()
            else:
                raise AttributeError
        except (RuntimeError, AttributeError):
            self.add_note_label = QLabel("Add a new note row")
            self.add_note_label.setStyleSheet("color: gray; font-style: italic;")
            self.add_note_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def _remove_persistent_widgets_from_grid(self):
        """Remove persistent widgets from grid layout to prevent deletion during grid clears"""
        try:
            self.grid_layout.removeWidget(self.btn_add_note)
        except RuntimeError:
            pass
        try:
            self.grid_layout.removeWidget(self.note_title)
        except RuntimeError:
            pass
        try:
            if hasattr(self, 'add_note_label'):
                self.grid_layout.removeWidget(self.add_note_label)
        except RuntimeError:
            pass

    def _update_note_label_position(self):
        """Update the position of the 'Note' label to span all note rows"""
        self._ensure_note_title()
        # Remove from current position
        self.grid_layout.removeWidget(self.note_title)
        # Add spanning all note rows (col 0, starting at row 2)
        if len(self.rows) > 0:
            self.grid_layout.addWidget(self.note_title, 2, 0, len(self.rows), 1)

    def rebuild_header(self):
        """Rebuild the header rows with Step title and step numbers"""
        # Clear first two rows
        for row in range(2):
            for col in range(self.grid_layout.columnCount()):
                item = self.grid_layout.itemAtPosition(row, col)
                if item and item.widget():
                    item.widget().deleteLater()

        # Row 0: "Step" label above step columns (cols 2+)
        step_title = QLabel("Step")
        step_title.setAlignment(Qt.AlignCenter)
        step_title.setStyleSheet("font-weight: bold;")
        self.grid_layout.addWidget(step_title, 0, 2, 1, self.num_steps)

        # Row 1: Step numbers (cols 2+)
        for step in range(self.num_steps):
            lbl = QLabel(f"{step + 1}")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-weight: bold;")
            self.grid_layout.addWidget(lbl, 1, step + 2)

        # Add hint label to the right of step numbers
        steps_hint = QLabel("To add or remove steps, adjust the Number of Steps setting below")
        steps_hint.setStyleSheet("color: gray; font-style: italic; padding-left: 10px;")
        self.grid_layout.addWidget(steps_hint, 1, self.num_steps + 2)

    def on_steps_changed(self, new_steps):
        """Handle number of steps changed"""
        old_steps = self.num_steps
        self.num_steps = new_steps

        if new_steps > old_steps:
            # Add columns (cols 2+ for cells, row offset +2 for headers)
            for row_idx, row_data in enumerate(self.rows):
                for step in range(old_steps, new_steps):
                    cell = GridCell(row_idx, step, self)
                    cell.leftClicked.connect(self.on_cell_left_click)
                    cell.rightClicked.connect(self.on_cell_right_click)
                    cell.dragEntered.connect(self.on_cell_drag_entered)
                    row_data['cells'].append(cell)
                    self.grid_layout.addWidget(cell, row_idx + 2, step + 2)
        elif new_steps < old_steps:
            # Remove columns
            for row_data in self.rows:
                for step in range(new_steps, old_steps):
                    cell = row_data['cells'].pop()
                    self.grid_layout.removeWidget(cell)
                    cell.deleteLater()

        self.rebuild_header()
        self._update_add_button_position()
        self.dataChanged.emit()

    def on_default_velocity_changed(self, value):
        """Handle default velocity changed"""
        self.default_velocity = value * 2  # Store as 0-255 internally

    def _create_row(self, note_index, octave):
        """Internal method to create a row with given note and octave"""
        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

        # Create row
        row_idx = len(self.rows)
        row_data = {
            'note': note_index,
            'octave': octave,
            'cells': []
        }

        # Create note label with delete button (col 1)
        note_widget = QWidget()
        note_layout = QHBoxLayout()
        note_layout.setContentsMargins(0, 0, 0, 0)
        note_layout.setSpacing(2)

        # Delete button (on the left)
        delete_btn = QPushButton("X")
        delete_btn.setFixedSize(20, 20)
        # Use red background with white text
        warning_color = QColor.fromHsv(0, 200, 200)  # Red hue, medium saturation/value
        delete_btn.setStyleSheet(f"background-color: {warning_color.name()}; color: white; font-weight: bold; border-radius: 3px;")
        delete_btn.clicked.connect(lambda checked, r=row_idx: self.delete_note_row(r))
        note_layout.addWidget(delete_btn)

        # Note label - clickable with theme styling (50x50 square)
        note_label = QPushButton(f"{note_names[note_index]}{octave}")
        note_label.setFixedSize(50, 50)
        palette = self.palette()
        highlight = palette.color(QPalette.Highlight)
        note_label.setStyleSheet(f"""
            QPushButton {{
                font-weight: bold;
                text-align: center;
                border: 2px solid {highlight.name()};
                background-color: rgba({highlight.red()}, {highlight.green()}, {highlight.blue()}, 50);
                border-radius: 3px;
            }}
            QPushButton:hover {{
                background-color: rgba({highlight.red()}, {highlight.green()}, {highlight.blue()}, 100);
            }}
        """)
        note_label.setCursor(Qt.PointingHandCursor)
        note_label.clicked.connect(lambda checked, r=row_idx: self.edit_note_row(r))
        note_layout.addWidget(note_label)

        note_widget.setLayout(note_layout)
        self.grid_layout.addWidget(note_widget, row_idx + 2, 1)  # Row offset +2 for headers, col 1

        # Create cells for this row (cols 2+)
        for step in range(self.num_steps):
            cell = GridCell(row_idx, step, self)
            cell.leftClicked.connect(self.on_cell_left_click)
            cell.rightClicked.connect(self.on_cell_right_click)
            cell.dragEntered.connect(self.on_cell_drag_entered)
            row_data['cells'].append(cell)
            self.grid_layout.addWidget(cell, row_idx + 2, step + 2)  # Row offset +2, col offset +2

        self.rows.append(row_data)
        self._update_add_button_position()
        self._update_note_label_position()

    def add_note_row(self):
        """Add a new note row"""
        if len(self.rows) >= 128:  # MAX_PRESET_NOTES
            QMessageBox.warning(self, "Maximum Rows", "Maximum 128 note rows reached")
            return

        # Ask user to select note and octave
        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        note, ok1 = QInputDialog.getItem(self, "Select Note", "Choose note:", note_names, 0, False)
        if not ok1:
            return

        octave, ok2 = QInputDialog.getInt(self, "Select Octave", "Choose octave:", 4, 0, 7, 1)
        if not ok2:
            return

        note_index = note_names.index(note)
        self._create_row(note_index, octave)
        self._update_add_button_position()
        self.dataChanged.emit()

    def edit_note_row(self, row_idx):
        """Edit an existing note row"""
        if row_idx >= len(self.rows):
            return

        row_data = self.rows[row_idx]
        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

        # Ask user to select new note and octave
        current_note = note_names[row_data['note']]
        note, ok1 = QInputDialog.getItem(self, "Edit Note", "Choose note:", note_names, note_names.index(current_note), False)
        if not ok1:
            return

        octave, ok2 = QInputDialog.getInt(self, "Edit Octave", "Choose octave:", row_data['octave'], 0, 7, 1)
        if not ok2:
            return

        # Update row data
        row_data['note'] = note_names.index(note)
        row_data['octave'] = octave

        # Update label (row offset +2 for headers, col 1 for note widgets)
        item = self.grid_layout.itemAtPosition(row_idx + 2, 1)
        if item and item.widget():
            widget = item.widget()
            # Find the note label button (not the delete "X" button)
            for btn in widget.findChildren(QPushButton):
                if btn.text() != "X":
                    btn.setText(f"{note}{octave}")
                    break

        self.dataChanged.emit()

    def delete_note_row(self, row_idx):
        """Delete a note row"""
        reply = QMessageBox.question(
            self,
            "Delete Row",
            "Are you sure you want to delete this note row?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Remove widgets
        row_data = self.rows[row_idx]

        # Remove note widget (column 1, row offset +2)
        item = self.grid_layout.itemAtPosition(row_idx + 2, 1)
        if item and item.widget():
            item.widget().deleteLater()

        # Remove cells
        for cell in row_data['cells']:
            self.grid_layout.removeWidget(cell)
            cell.deleteLater()

        # Remove from list
        self.rows.pop(row_idx)

        # Rebuild grid (re-index rows)
        self.rebuild_grid()
        self._update_add_button_position()
        self._update_note_label_position()
        self.dataChanged.emit()

    def rebuild_grid(self):
        """Rebuild entire grid after deletion"""
        # Save cell states before clearing
        cell_states = []
        for row_data in self.rows:
            row_states = []
            for cell in row_data['cells']:
                row_states.append({
                    'active': cell.active,
                    'velocity': cell.velocity,
                    'octave': cell.octave,
                    'is_tie': getattr(cell, 'is_tie', False)
                })
            cell_states.append(row_states)

        # Remove persistent widgets from grid before clearing to prevent deletion
        self._remove_persistent_widgets_from_grid()

        # Clear grid widgets
        for i in reversed(range(self.grid_layout.count())):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()

        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

        # Rebuild header
        self.rebuild_header()

        # Rebuild rows with NEW cells
        for row_idx, row_data in enumerate(self.rows):
            # Recreate note label
            note_widget = QWidget()
            note_layout = QHBoxLayout()
            note_layout.setContentsMargins(0, 0, 0, 0)
            note_layout.setSpacing(2)

            # Delete button (on the left)
            delete_btn = QPushButton("X")
            delete_btn.setFixedSize(20, 20)
            # Use red background with white text
            warning_color_temp = QColor.fromHsv(0, 200, 200)  # Red hue, medium saturation/value
            delete_btn.setStyleSheet(f"background-color: {warning_color_temp.name()}; color: white; font-weight: bold; border-radius: 3px;")
            delete_btn.clicked.connect(lambda checked, r=row_idx: self.delete_note_row(r))
            note_layout.addWidget(delete_btn)

            # Note label - clickable with theme styling (50x50 square)
            note_label = QPushButton(f"{note_names[row_data['note']]}{row_data['octave']}")
            note_label.setFixedSize(50, 50)
            palette = self.palette()
            highlight = palette.color(QPalette.Highlight)
            note_label.setStyleSheet(f"""
                QPushButton {{
                    font-weight: bold;
                    text-align: center;
                    border: 2px solid {highlight.name()};
                    background-color: rgba({highlight.red()}, {highlight.green()}, {highlight.blue()}, 50);
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    background-color: rgba({highlight.red()}, {highlight.green()}, {highlight.blue()}, 100);
                }}
            """)
            note_label.setCursor(Qt.PointingHandCursor)
            note_label.clicked.connect(lambda checked, r=row_idx: self.edit_note_row(r))
            note_layout.addWidget(note_label)

            note_widget.setLayout(note_layout)
            self.grid_layout.addWidget(note_widget, row_idx + 2, 1)  # Row offset +2, col 1

            # Create NEW cells and restore their states
            new_cells = []
            for step in range(len(row_data['cells'])):
                cell = GridCell(row_idx, step, self)
                cell.leftClicked.connect(self.on_cell_left_click)
                cell.rightClicked.connect(self.on_cell_right_click)
                cell.dragEntered.connect(self.on_cell_drag_entered)

                # Restore state if available
                if row_idx < len(cell_states) and step < len(cell_states[row_idx]):
                    state = cell_states[row_idx][step]
                    cell.is_tie = state.get('is_tie', False)
                    cell.set_active(state['active'], state['velocity'], state['octave'])

                new_cells.append(cell)
                self.grid_layout.addWidget(cell, row_idx + 2, step + 2)  # Row offset +2, col offset +2

            # Replace old cells list with new cells
            row_data['cells'] = new_cells

        self._update_add_button_position()
        self._update_note_label_position()

    def on_cell_left_click(self, row, col):
        """Handle left click - toggle cell and start drag tracking"""
        if row >= len(self.rows):
            return

        row_data = self.rows[row]
        cell = row_data['cells'][col]

        # Toggle active state - reset to defaults when activating
        if cell.active:
            # Deactivate - clear data
            cell.set_active(False, self.default_velocity, 0)
            cell.is_tie = False
            self._drag_mode = 'erase'
        else:
            # Activate - use default values (not sustained - individual note)
            cell.set_active(True, self.default_velocity, 0)
            cell.is_tie = False
            self._drag_mode = 'paint'

        # Track drag start for sustain painting
        # Step sequencer: steps are on X axis (columns), so drag along columns
        self._drag_row = row
        self.dataChanged.emit()

    def on_cell_drag_entered(self, row, col):
        """Handle drag entering a cell - sustain notes across steps (columns) for step sequencer"""
        if not hasattr(self, '_drag_mode') or self._drag_mode is None:
            return
        if not hasattr(self, '_drag_row') or self._drag_row is None:
            return

        # Only drag within the same row (same note)
        if row != self._drag_row:
            return
        if row >= len(self.rows):
            return

        row_data = self.rows[row]
        if col >= len(row_data['cells']):
            return
        cell = row_data['cells'][col]

        if self._drag_mode == 'paint':
            if not cell.active:
                # Subsequent cells in a drag are sustained
                cell.set_active(True, self.default_velocity, 0)
                cell.is_tie = True
                cell.update_style()
                self.dataChanged.emit()
        elif self._drag_mode == 'erase':
            if cell.active:
                cell.set_active(False, self.default_velocity, 0)
                cell.is_tie = False
                self.dataChanged.emit()

    def on_cell_right_click(self, row, col):
        """Handle right click - activate and configure with current or default values"""
        if row >= len(self.rows):
            return

        row_data = self.rows[row]
        cell = row_data['cells'][col]

        # Show velocity popup (no octave for step sequencer) - use current value if active
        current_velocity = cell.velocity if cell.active else self.default_velocity
        popup = VelocityOctavePopup(current_velocity, octave=None, parent=self)
        if popup.exec_() == QDialog.Accepted:
            velocity, _ = popup.get_values()
            cell.set_active(True, velocity, 0)
            self.dataChanged.emit()

    def get_grid_data(self, rate_16ths=16):
        """Get grid data as list of notes with timing

        Args:
            rate_16ths: Timing in 16th notes per step (default 1 = 1/16 notes)
        """
        notes = []
        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

        for row_idx, row_data in enumerate(self.rows):
            for step, cell in enumerate(row_data['cells']):
                if cell.active:
                    # Calculate timing based on actual rate
                    timing_16ths = step * rate_16ths

                    notes.append({
                        'timing_16ths': timing_16ths,
                        'note_index': row_data['note'],  # Absolute note (0-11)
                        'octave_offset': row_data['octave'],  # Absolute octave (0-7)
                        'velocity': cell.velocity,
                        'raw_travel': cell.velocity,
                        'is_tie': getattr(cell, 'is_tie', False)
                    })

        return notes

    def set_grid_data(self, notes_data, num_steps=8, rate_16ths=16):
        """Set grid data from notes list

        Args:
            notes_data: List of note dictionaries
            num_steps: Number of steps in the grid
            rate_16ths: Timing in 16th notes per step (default 1 = 1/16 notes)
        """
        # Save existing rows configuration before any changes
        existing_rows_config = []
        for row_data in self.rows:
            row_config = {
                'note': row_data['note'],
                'octave': row_data['octave'],
                'cells_state': []
            }
            for cell in row_data['cells']:
                row_config['cells_state'].append({
                    'active': cell.active,
                    'velocity': cell.velocity,
                    'octave': cell.octave,
                    'is_tie': getattr(cell, 'is_tie', False)
                })
            existing_rows_config.append(row_config)

        # Group notes by (note_index, octave) to create rows
        note_groups = {}
        for note in notes_data:
            key = (note.get('note_index', 0), note.get('octave_offset', 4))
            if key not in note_groups:
                note_groups[key] = []
            note_groups[key].append(note)

        # Preserve existing row configurations that aren't in the new data
        # This prevents empty rows from being dropped during tab switches
        if existing_rows_config:
            for row_config in existing_rows_config:
                key = (row_config['note'], row_config['octave'])
                if key not in note_groups:
                    note_groups[key] = []  # Empty row - preserve the note/octave but no active cells

        # If no data AND no existing rows, will fall through to create defaults below
        if not note_groups and not existing_rows_config:
            pass  # Will create defaults below

        # Remove persistent widgets from grid before clearing to prevent deletion
        self._remove_persistent_widgets_from_grid()

        # Clear existing rows - iterate with index to avoid lookup issues
        for i in range(len(self.rows) - 1, -1, -1):
            row_data = self.rows[i]
            # Remove and delete cells
            for cell in row_data['cells']:
                self.grid_layout.removeWidget(cell)
                cell.deleteLater()
            # Remove and delete note label widget (row offset +2 for headers, col 1)
            item = self.grid_layout.itemAtPosition(i + 2, 1)
            if item and item.widget():
                item.widget().deleteLater()

        self.rows.clear()

        # Set number of steps
        self.num_steps = num_steps
        self.rebuild_header()

        # If no data AND no existing rows, create default rows (C3, D3, E3, F3)
        if not note_groups:
            note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
            default_notes = [
                ('C', 3),
                ('D', 3),
                ('E', 3),
                ('F', 3)
            ]
            for note_name, octave in default_notes:
                note_index = note_names.index(note_name)
                self._create_row(note_index, octave)
            self._update_add_button_position()
            self._update_note_label_position()
            return

        # Create rows - use original row order when available, append new rows at end
        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

        # Build ordered list of (note_idx, octave) keys preserving original row order
        ordered_keys = []
        seen_keys = set()
        # First add keys in their original order from existing_rows_config
        for row_config in existing_rows_config:
            key = (row_config['note'], row_config['octave'])
            if key in note_groups and key not in seen_keys:
                ordered_keys.append(key)
                seen_keys.add(key)
        # Then add any new keys from note_groups that weren't in existing rows
        for key in note_groups:
            if key not in seen_keys:
                ordered_keys.append(key)
                seen_keys.add(key)

        for (note_idx, octave) in ordered_keys:
            notes = note_groups[(note_idx, octave)]
            row_idx = len(self.rows)
            row_data = {
                'note': note_idx,
                'octave': octave,
                'cells': []
            }

            # Create note label
            note_widget = QWidget()
            note_layout = QHBoxLayout()
            note_layout.setContentsMargins(0, 0, 0, 0)
            note_layout.setSpacing(2)

            # Delete button (on the left)
            delete_btn = QPushButton("X")
            delete_btn.setFixedSize(20, 20)
            # Use red background with white text
            warning_color_temp = QColor.fromHsv(0, 200, 200)  # Red hue, medium saturation/value
            delete_btn.setStyleSheet(f"background-color: {warning_color_temp.name()}; color: white; font-weight: bold; border-radius: 3px;")
            delete_btn.clicked.connect(lambda checked, r=row_idx: self.delete_note_row(r))
            note_layout.addWidget(delete_btn)

            # Note label - clickable with theme styling (50x50 square)
            note_label = QPushButton(f"{note_names[note_idx]}{octave}")
            note_label.setFixedSize(50, 50)
            palette = self.palette()
            highlight = palette.color(QPalette.Highlight)
            note_label.setStyleSheet(f"""
                QPushButton {{
                    font-weight: bold;
                    text-align: center;
                    border: 2px solid {highlight.name()};
                    background-color: rgba({highlight.red()}, {highlight.green()}, {highlight.blue()}, 50);
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    background-color: rgba({highlight.red()}, {highlight.green()}, {highlight.blue()}, 100);
                }}
            """)
            note_label.setCursor(Qt.PointingHandCursor)
            note_label.clicked.connect(lambda checked, r=row_idx: self.edit_note_row(r))
            note_layout.addWidget(note_label)

            note_widget.setLayout(note_layout)
            self.grid_layout.addWidget(note_widget, row_idx + 2, 1)  # Row offset +2 for headers, col 1

            # Create cells
            for step in range(num_steps):
                cell = GridCell(row_idx, step, self)
                cell.leftClicked.connect(self.on_cell_left_click)
                cell.rightClicked.connect(self.on_cell_right_click)
                cell.dragEntered.connect(self.on_cell_drag_entered)

                # Check if this step has a note - use actual rate
                timing_16ths = step * rate_16ths
                matching_note = next((n for n in notes if abs(n['timing_16ths'] - timing_16ths) <= (rate_16ths // 2)), None)

                if matching_note:
                    cell.is_tie = matching_note.get('is_tie', False)
                    cell.set_active(True, matching_note.get('velocity', 127), 0)

                row_data['cells'].append(cell)
                self.grid_layout.addWidget(cell, row_idx + 2, step + 2)  # Row offset +2, col offset +2

            self.rows.append(row_data)

        self._update_add_button_position()
        self._update_note_label_position()


class BasicArpeggiatorGrid(QWidget):
    """Grid widget for arpeggiator basic tab with fixed 23 rows (intervals -11 to +11)"""

    dataChanged = pyqtSignal()  # Emitted when grid data changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_arpeggiator = True  # For octave color logic
        self.num_steps = 8  # Default number of rows
        self.default_velocity = 255  # Default velocity for new cells
        self.cells = []  # num_steps rows x 23 columns (intervals)
        self.show_negative_intervals = True  # Show negative intervals by default

        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(2)
        self.main_layout.setContentsMargins(5, 5, 5, 5)

        # Create scroll area for grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(2)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.grid_container.setLayout(self.grid_layout)

        scroll.setWidget(self.grid_container)
        self.main_layout.addWidget(scroll, 1)

        # Scale selector
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale:"))

        self.combo_scale = ArrowComboBox()
        self.combo_scale.setMinimumWidth(150)
        self.combo_scale.setMaximumHeight(30)
        self.combo_scale.setEditable(True)
        self.combo_scale.lineEdit().setReadOnly(True)
        self.combo_scale.lineEdit().setAlignment(Qt.AlignCenter)

        # Define all scales and modes
        self.scale_definitions = {
            'Chromatic': list(range(-11, 12)),  # All 23 semitones
            'Major': [0, 2, 4, 5, 7, 9, 11],
            'Minor': [0, 2, 3, 5, 7, 8, 10],
            'Pentatonic Major': [0, 2, 4, 7, 9],
            'Pentatonic Minor': [0, 3, 5, 7, 10],
            'Blues': [0, 3, 5, 6, 7, 10],
            'Dorian': [0, 2, 3, 5, 7, 9, 10],
            'Phrygian': [0, 1, 3, 5, 7, 8, 10],
            'Lydian': [0, 2, 4, 6, 7, 9, 11],
            'Mixolydian': [0, 2, 4, 5, 7, 9, 10],
            'Locrian': [0, 1, 3, 5, 6, 8, 10],
            'Harmonic Minor': [0, 2, 3, 5, 7, 8, 11],
            'Melodic Minor': [0, 2, 3, 5, 7, 9, 11],
            'Whole Tone': [0, 2, 4, 6, 8, 10],
            'Diminished': [0, 2, 3, 5, 6, 8, 9, 11],
        }

        for scale_name in self.scale_definitions.keys():
            self.combo_scale.addItem(scale_name)
        self.combo_scale.setCurrentText('Chromatic')
        self.combo_scale.setToolTip("Select scale to highlight intervals")
        self.combo_scale.currentTextChanged.connect(self.on_scale_changed)
        scale_layout.addWidget(self.combo_scale)
        scale_layout.addStretch()
        self.main_layout.addLayout(scale_layout)

        # Add octave color legend note
        legend_layout = QHBoxLayout()
        legend_label = QLabel("Octave colors use theme-relative hue shifts (0 = root, ±1-4 = shifted hues)")
        # Use theme-based muted text color
        palette = self.palette()
        muted_color = palette.color(QPalette.WindowText).lighter(150)
        legend_label.setStyleSheet(f"color: {muted_color.name()}; font-size: 10px; font-style: italic;")
        legend_layout.addWidget(legend_label)
        legend_layout.addStretch()
        self.main_layout.addLayout(legend_layout)

        # Create steps hint label (will be positioned in the grid)
        self.steps_hint = QLabel("To add or remove steps, adjust the Number of Steps setting below")
        self.steps_hint.setStyleSheet(f"color: {muted_color.name()}; font-size: 10px; font-style: italic; padding-top: 5px;")

        self.setLayout(self.main_layout)

        # Build grid
        self.build_grid()

    def _ensure_steps_hint(self):
        """Ensure steps_hint QLabel exists and is valid (recreate if C++ object was deleted)"""
        try:
            self.steps_hint.isVisible()
        except (RuntimeError, AttributeError):
            palette = self.palette()
            muted_color = palette.color(QPalette.WindowText).lighter(150)
            self.steps_hint = QLabel("To add or remove steps, adjust the Number of Steps setting below")
            self.steps_hint.setStyleSheet(f"color: {muted_color.name()}; font-size: 10px; font-style: italic; padding-top: 5px;")

    def build_grid(self):
        """Build the complete grid - swapped axes: steps as rows, intervals as columns"""
        # Remove persistent widgets from grid before mass deletion to prevent them being destroyed
        try:
            self.grid_layout.removeWidget(self.steps_hint)
        except RuntimeError:
            pass

        # Clear existing
        for i in reversed(range(self.grid_layout.count())):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()

        self.cells = []

        # Header row 0: "Interval" label above interval columns (cols 2-24)
        interval_title = QLabel("Interval")
        interval_title.setAlignment(Qt.AlignCenter)
        interval_title.setStyleSheet("font-weight: bold;")
        self.grid_layout.addWidget(interval_title, 0, 2, 1, 23)  # Span interval columns only

        # Header row 1: Interval numbers (cols 2-24)
        for col in range(23):
            interval = col - 11  # Col 0 = -11, col 11 = 0, col 22 = +11

            # Interval label
            if interval == 0:
                lbl_text = "0"
            elif interval > 0:
                lbl_text = f"+{interval}"
            else:
                lbl_text = str(interval)

            lbl = QLabel(lbl_text)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-weight: bold;")
            self.grid_layout.addWidget(lbl, 1, col + 2)

        # "Step" label on left side spanning all step rows (col 0)
        self.step_title = QLabel("Step")
        self.step_title.setAlignment(Qt.AlignCenter)
        self.step_title.setStyleSheet("font-weight: bold;")
        # Will be positioned after creating rows

        # Create num_steps rows (one for each step) x 23 columns (intervals -11 to +11)
        for row in range(self.num_steps):
            # Step number label (col 1)
            lbl = QLabel(f"{row + 1}")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl.setStyleSheet("min-width: 30px; padding-right: 5px; font-weight: bold;")
            self.grid_layout.addWidget(lbl, row + 2, 1)

            # Create cells for this row (cols 2-24)
            row_cells = []
            for col in range(23):
                cell = GridCell(row, col, self)
                cell.leftClicked.connect(self.on_cell_left_click)
                cell.rightClicked.connect(self.on_cell_right_click)
                cell.dragEntered.connect(self.on_cell_drag_entered)
                row_cells.append(cell)
                self.grid_layout.addWidget(cell, row + 2, col + 2)

            self.cells.append(row_cells)

        # Position "Step" label spanning all step rows (col 0, rows 2 to num_steps+1)
        self.grid_layout.addWidget(self.step_title, 2, 0, self.num_steps, 1)

        # Add steps hint below the last step row
        self._update_steps_hint_position()

    def _update_steps_hint_position(self):
        """Position the steps hint below the last step row"""
        self._ensure_steps_hint()
        # Remove from current position if it exists
        self.grid_layout.removeWidget(self.steps_hint)
        # Add at row after all steps (num_steps + 2 accounts for 2 header rows)
        # Span all 25 columns (col 0=Step label, col 1=numbers, cols 2-24=intervals)
        self.grid_layout.addWidget(self.steps_hint, self.num_steps + 2, 0, 1, 25)

    def on_steps_changed(self, new_steps):
        """Handle number of steps changed - preserve existing data"""
        old_steps = self.num_steps
        self.num_steps = new_steps

        if new_steps > old_steps:
            # Add rows - append new rows with all 23 interval cells
            for step in range(old_steps, new_steps):
                # Step number label (col 1)
                lbl = QLabel(f"{step + 1}")
                lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                lbl.setStyleSheet("min-width: 30px; padding-right: 5px; font-weight: bold;")
                self.grid_layout.addWidget(lbl, step + 2, 1)

                # Create cells for this row (cols 2-24)
                row_cells = []
                for col in range(23):
                    cell = GridCell(step, col, self)
                    cell.leftClicked.connect(self.on_cell_left_click)
                    cell.rightClicked.connect(self.on_cell_right_click)
                    cell.dragEntered.connect(self.on_cell_drag_entered)
                    row_cells.append(cell)
                    self.grid_layout.addWidget(cell, step + 2, col + 2)

                self.cells.append(row_cells)
        elif new_steps < old_steps:
            # Remove rows - remove from end
            for step in range(new_steps, old_steps):
                if step < len(self.cells):
                    # Remove step number label (col 1)
                    label_item = self.grid_layout.itemAtPosition(step + 2, 1)
                    if label_item and label_item.widget():
                        label_item.widget().deleteLater()

                    # Remove all cells in this row
                    row_cells = self.cells[step]
                    for cell in row_cells:
                        self.grid_layout.removeWidget(cell)
                        cell.deleteLater()

            # Trim cells list
            self.cells = self.cells[:new_steps]

        # Update "Step" label to span new number of rows
        try:
            self.grid_layout.removeWidget(self.step_title)
        except RuntimeError:
            self.step_title = QLabel("Step")
            self.step_title.setAlignment(Qt.AlignCenter)
            self.step_title.setStyleSheet("font-weight: bold;")
        self.grid_layout.addWidget(self.step_title, 2, 0, self.num_steps, 1)

        # Update hint position
        self._update_steps_hint_position()
        self.dataChanged.emit()

    def on_default_velocity_changed(self, value):
        """Handle default velocity changed"""
        self.default_velocity = value * 2  # Store as 0-255 internally

    def on_cell_left_click(self, row, col):
        """Handle left click - toggle cell and start drag tracking
        Note: With swapped axes, row is the step, col is the interval
        """
        if row >= len(self.cells) or col >= len(self.cells[row]):
            return

        cell = self.cells[row][col]

        # Toggle active state - reset to defaults when activating
        if cell.active:
            # Deactivate - clear data
            cell.set_active(False, self.default_velocity, 0)
            cell.is_tie = False
            self._drag_mode = 'erase'
        else:
            # Activate - use default values
            cell.set_active(True, self.default_velocity, 0)
            cell.is_tie = False
            self._drag_mode = 'paint'

        # Track drag start for sustain painting
        # Arpeggiator: steps are on Y axis (rows), so drag along rows
        self._drag_col = col
        self.dataChanged.emit()

    def on_cell_drag_entered(self, row, col):
        """Handle drag entering a cell - sustain notes across steps (rows) for arpeggiator"""
        if not hasattr(self, '_drag_mode') or self._drag_mode is None:
            return
        if not hasattr(self, '_drag_col') or self._drag_col is None:
            return

        # Only drag within the same column (same interval)
        if col != self._drag_col:
            return
        if row >= len(self.cells) or col >= len(self.cells[row]):
            return

        cell = self.cells[row][col]

        if self._drag_mode == 'paint':
            if not cell.active:
                cell.set_active(True, self.default_velocity, 0)
                cell.is_tie = True
                cell.update_style()
                self.dataChanged.emit()
        elif self._drag_mode == 'erase':
            if cell.active:
                cell.set_active(False, self.default_velocity, 0)
                cell.is_tie = False
                self.dataChanged.emit()

    def on_cell_right_click(self, row, col):
        """Handle right click - activate and configure
        Note: With swapped axes, row is the step, col is the interval
        """
        if row >= len(self.cells) or col >= len(self.cells[row]):
            return

        cell = self.cells[row][col]
        interval = col - 11  # Calculate interval from column (col 0 = -11, col 11 = 0, col 22 = +11)

        # Determine octave constraints based on interval
        # Interval 0 allows both negative and positive
        # Positive intervals only allow positive octaves
        # Negative intervals only allow negative octaves
        allow_negative = (interval <= 0)
        allow_positive = (interval >= 0)

        # Show velocity + octave popup - use current cell values if active
        current_velocity = cell.velocity if cell.active else self.default_velocity
        current_octave = cell.octave if cell.active else 0

        popup = VelocityOctavePopup(current_velocity, octave=current_octave,
                                    allow_negative_octave=allow_negative,
                                    allow_positive_octave=allow_positive,
                                    parent=self)
        if popup.exec_() == QDialog.Accepted:
            velocity, octave = popup.get_values()
            cell.set_active(True, velocity, octave)
            self.dataChanged.emit()

    def get_grid_data(self, rate_16ths=16):
        """Get grid data as list of notes with timing
        Note: With swapped axes, each row is a step, each column is an interval

        Args:
            rate_16ths: Timing in 16th notes per step (default 1 = 1/16 notes)
        """
        notes = []

        for step_idx, row_cells in enumerate(self.cells):
            # Calculate timing for this step
            timing_16ths = step_idx * rate_16ths

            for col_idx, cell in enumerate(row_cells):
                if cell.active:
                    interval = col_idx - 11  # Calculate interval from column

                    notes.append({
                        'timing_16ths': timing_16ths,
                        'note_index': interval,  # Semitone offset for arpeggiator
                        'semitone_offset': interval,  # Also store as semitone_offset
                        'octave_offset': cell.octave,
                        'velocity': cell.velocity,
                        'raw_travel': cell.velocity,
                        'is_tie': getattr(cell, 'is_tie', False)
                    })

        return notes

    def set_grid_data(self, notes_data, num_steps=8, rate_16ths=16):
        """Set grid data from notes list
        Note: With swapped axes, each row is a step, each column is an interval

        Args:
            notes_data: List of note dictionaries
            num_steps: Number of steps in the grid
            rate_16ths: Timing in 16th notes per step (default 1 = 1/16 notes)
        """
        # Set number of steps
        self.num_steps = num_steps
        self.build_grid()

        # Populate cells
        for note in notes_data:
            interval = note.get('semitone_offset', note.get('note_index', 0))
            octave = note.get('octave_offset', 0)
            velocity = note.get('velocity', 127)
            timing_16ths = note.get('timing_16ths', 0)

            # Calculate step from timing using actual rate
            step = timing_16ths // rate_16ths

            # Calculate column from interval (col 0 = -11, col 11 = 0, col 22 = +11)
            col = interval + 11

            if 0 <= step < self.num_steps and 0 <= col < 23:
                cell = self.cells[step][col]
                cell.is_tie = note.get('is_tie', False)
                cell.set_active(True, velocity, octave)

    def filter_rows_by_scale(self, allowed_intervals):
        """Darken columns that aren't in the selected scale
        Note: With swapped axes, intervals are columns, not rows
        """
        # allowed_intervals is a set of semitone offsets (-11 to +11)
        for col in range(23):
            interval = col - 11  # Col 0 = -11, col 11 = 0, col 22 = +11

            # Determine if this interval is in the scale
            in_scale = interval in allowed_intervals

            # Darken the interval label if not in scale - grey out LOTS
            label_item = self.grid_layout.itemAtPosition(1, col + 1)
            if label_item and label_item.widget():
                label = label_item.widget()
                palette_grid = self.palette()
                if in_scale:
                    # Restore base styling - all intervals bold
                    label.setStyleSheet("font-weight: bold;")
                else:
                    # Grey out label significantly - use theme-based dark color, keep bold
                    dark_color = palette_grid.color(QPalette.WindowText).darker(300)
                    label.setStyleSheet(f"font-weight: bold; color: {dark_color.name()};")

            # Darken all cells in this column if not in scale - keep them selectable
            for row in range(len(self.cells)):
                if col < len(self.cells[row]):
                    cell = self.cells[row][col]
                    # Store scale state in cell for use in update_style
                    cell.in_scale = in_scale
                    # Force update of cell style
                    cell.update_style()

    def on_scale_changed(self, scale_name):
        """Handle scale selection change"""
        # Get the intervals for this scale
        scale_intervals = self.scale_definitions.get(scale_name, list(range(-11, 12)))

        # Expand scale to cover all octaves
        expanded_intervals = set()
        for interval in scale_intervals:
            # Add interval in all octaves (-11 to +11)
            for octave in range(-1, 2):  # -1, 0, +1 octaves
                semitone = interval + (octave * 12)
                if -11 <= semitone <= 11:
                    expanded_intervals.add(semitone)

        # Filter rows based on scale
        self.filter_rows_by_scale(expanded_intervals)


class IntervalSelector(QWidget):
    """Custom interval selector with +/- buttons and editable value box"""

    valueChanged = pyqtSignal(int)

    # Interval names mapping (extended range)
    # Note: -1 is now a valid interval (minor second down), not "Empty"
    INTERVAL_NAMES = {
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
        -1: "-Minor Second",
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
        self.value = 0  # Default to Root Note

        layout = QVBoxLayout()
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        # Interval name label (above the box)
        self.name_label = QLabel("Root Note")
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
        self.value_box = QLabel("+0")
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
        if self.value >= 0:
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
        from PyQt5.QtGui import QPalette, QPainterPath
        from PyQt5.QtCore import QRectF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get theme colors from palette
        palette = self.palette()
        bg_color = palette.color(QPalette.Window)
        highlight_color = palette.color(QPalette.Highlight)

        # Create rounded rectangle path for background
        bg_path = QPainterPath()
        bg_rect = QRectF(0, 0, self.width(), self.height())
        bg_path.addRoundedRect(bg_rect, 5, 5)

        # Background
        painter.fillPath(bg_path, bg_color.darker(120))

        # Border
        painter.setPen(QPen(palette.color(QPalette.Mid), 1))
        painter.drawPath(bg_path)

        # Velocity bar with theme highlight color
        if self.velocity > 0:
            bar_height = int((self.velocity / 255.0) * (self.height() - 2))
            bar_y = self.height() - bar_height - 1

            # Use theme highlight color with intensity based on velocity
            intensity = self.velocity / 255.0
            color = QColor(
                int(highlight_color.red() * (0.5 + 0.5 * intensity)),
                int(highlight_color.green() * (0.5 + 0.5 * intensity)),
                int(highlight_color.blue() * (0.5 + 0.5 * intensity))
            )

            # Create rounded rectangle path for velocity bar
            bar_path = QPainterPath()
            bar_rect = QRectF(1, bar_y, self.width() - 2, bar_height)
            bar_path.addRoundedRect(bar_rect, 4, 4)
            painter.fillPath(bar_path, color)

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


class CompactNoteLabel(QPushButton):
    """Compact clickable label for a note in the list"""

    removed = pyqtSignal()  # Signal to remove this note
    selected = pyqtSignal()  # Signal when clicked to select

    def __init__(self, note_num, is_step_sequencer=False, parent=None):
        super().__init__(parent)
        self.note_num = note_num
        self.is_step_sequencer = is_step_sequencer
        self.note_data = {
            'velocity': 200,
            'octave_offset': 4 if is_step_sequencer else 0,
            'note_index': 0 if is_step_sequencer else None,
            'semitone_offset': 0 if not is_step_sequencer else None,
            'is_tie': False
        }
        self.is_selected = False

        # Setup as checkable button
        self.setCheckable(True)
        self.clicked.connect(self.on_clicked)
        self.setMinimumHeight(25)
        self.setMaximumHeight(25)

        self.update_label()
        self.set_selected(False)  # Initialize with unselected style

    def on_clicked(self):
        """Button clicked - emit selected signal"""
        self.selected.emit()

    def set_selected(self, selected):
        """Set selection state"""
        self.is_selected = selected
        self.setChecked(selected)

        # Update style to highlight border when selected
        palette = self.palette()
        highlight = palette.color(QPalette.Highlight)
        if selected:
            self.setStyleSheet(f"""
                QPushButton {{
                    border: 3px solid {highlight.name()};
                    background-color: rgba({highlight.red()}, {highlight.green()}, {highlight.blue()}, 50);
                    padding: 3px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    border: 1px solid {highlight.darker(150).name()};
                    background-color: rgba({highlight.red()}, {highlight.green()}, {highlight.blue()}, 20);
                    padding: 3px;
                }}
            """)

    def update_label(self):
        """Update label text based on note data"""
        note_str = ""
        if self.is_step_sequencer:
            # Step sequencer: show "C#4" (note + octave)
            note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
            note_idx = self.note_data.get('note_index', 0)
            octave = self.note_data.get('octave_offset', 4)
            note_str = f"{note_names[note_idx]}{octave}"
        else:
            # Arpeggiator: show "Int +5, Oct +1"
            interval = self.note_data.get('semitone_offset', 0)
            octave = self.note_data.get('octave_offset', 0)
            int_str = f"+{interval}" if interval > 0 else str(interval)
            oct_str = f"+{octave}" if octave > 0 else str(octave)
            note_str = f"Int {int_str}, Oct {oct_str}"

        if self.note_data.get('is_tie', False):
            note_str += " (Sustained)"

        self.setText(note_str)

    def get_note_data(self):
        """Get note data dict"""
        return self.note_data.copy()

    def set_note_data(self, data):
        """Set note data and update label"""
        self.note_data.update(data)
        self.update_label()


class StepWidget(QFrame):
    """Single step in the sequencer - narrow vertical layout with compact note list"""

    def __init__(self, step_num, is_step_sequencer=False, parent=None):
        super().__init__(parent)
        self.step_num = step_num
        self.is_step_sequencer = is_step_sequencer
        self.note_labels = []
        self.selected_note_index = None

        # Main vertical layout
        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(4)
        self.main_layout.setContentsMargins(4, 4, 4, 4)

        # Step number label
        lbl_step = QLabel(f"Step {step_num + 1}")
        lbl_step.setAlignment(Qt.AlignCenter)
        lbl_step.setFont(QFont("Arial", 10, QFont.Bold))
        self.main_layout.addWidget(lbl_step)

        # Create empty state widgets
        self.empty_container = QWidget()
        empty_layout = QVBoxLayout()
        empty_layout.addStretch()
        self.btn_add_note_empty = QPushButton("Add Note")
        self.btn_add_note_empty.setStyleSheet("QPushButton { min-height: 30px; max-height: 30px; }")
        self.btn_add_note_empty.clicked.connect(self.add_note)
        empty_layout.addWidget(self.btn_add_note_empty)
        # Sustain Previous Step button (empty state)
        self.btn_sustain_empty = QPushButton("Sustain\nPrevious Step")
        self.btn_sustain_empty.setStyleSheet("QPushButton { min-height: 40px; max-height: 40px; font-size: 8pt; }")
        self.btn_sustain_empty.setToolTip("Copy all notes from the previous step as sustained notes")
        self.btn_sustain_empty.clicked.connect(self.sustain_previous_step)
        empty_layout.addWidget(self.btn_sustain_empty)
        empty_layout.addStretch()
        self.empty_container.setLayout(empty_layout)
        self.main_layout.addWidget(self.empty_container, 1)

        # Create filled state widgets (hidden initially)
        self.filled_container = QWidget()
        filled_layout = QVBoxLayout()
        filled_layout.setSpacing(2)
        filled_layout.setContentsMargins(0, 0, 0, 0)

        # Velocity title
        lbl_velocity = QLabel("Velocity")
        lbl_velocity.setAlignment(Qt.AlignCenter)
        lbl_velocity.setFont(QFont("Arial", 9, QFont.Bold))
        filled_layout.addWidget(lbl_velocity)

        # Velocity bar (centered)
        velocity_bar_container = QWidget()
        velocity_bar_layout = QHBoxLayout()
        velocity_bar_layout.setContentsMargins(0, 0, 0, 0)
        velocity_bar_layout.addStretch()
        self.velocity_bar = VelocityBar()
        self.velocity_bar.clicked.connect(self.on_velocity_changed)
        velocity_bar_layout.addWidget(self.velocity_bar)
        velocity_bar_layout.addStretch()
        velocity_bar_container.setLayout(velocity_bar_layout)
        filled_layout.addWidget(velocity_bar_container)

        # Note/Interval label
        if self.is_step_sequencer:
            lbl_note = QLabel("Note")
            lbl_note.setAlignment(Qt.AlignCenter)
            lbl_note.setFont(QFont("Arial", 9, QFont.Bold))
            filled_layout.addWidget(lbl_note)
        else:
            lbl_interval = QLabel("Interval")
            lbl_interval.setAlignment(Qt.AlignCenter)
            lbl_interval.setFont(QFont("Arial", 9, QFont.Bold))
            filled_layout.addWidget(lbl_interval)

        # Interval/Note selector
        if self.is_step_sequencer:
            self.note_selector = NoteSelector()
            self.note_selector.valueChanged.connect(self.on_note_changed)
            filled_layout.addWidget(self.note_selector)
        else:
            self.interval_selector = IntervalSelector()
            self.interval_selector.valueChanged.connect(self.on_interval_changed)
            filled_layout.addWidget(self.interval_selector)

        # Octave title
        lbl_octave = QLabel("Octave")
        lbl_octave.setAlignment(Qt.AlignCenter)
        lbl_octave.setFont(QFont("Arial", 9, QFont.Bold))
        filled_layout.addWidget(lbl_octave)

        # Octave selector
        if self.is_step_sequencer:
            self.octave_selector = OctaveSelector(min_octave=0, max_octave=7, default_octave=4)
        else:
            self.octave_selector = OctaveSelector(min_octave=-4, max_octave=4, default_octave=0)
        self.octave_selector.valueChanged.connect(self.on_octave_changed)
        filled_layout.addWidget(self.octave_selector)

        # Add Note button
        self.btn_add_note = QPushButton("Add Note")
        self.btn_add_note.setStyleSheet("QPushButton { min-height: 25px; max-height: 25px; }")
        self.btn_add_note.clicked.connect(self.add_note)
        filled_layout.addWidget(self.btn_add_note)

        # Small spacer
        filled_layout.addSpacing(8)

        # Scroll area for note labels
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setMinimumHeight(60)

        # Container for note labels
        self.notes_container = QWidget()
        self.notes_layout = QVBoxLayout()
        self.notes_layout.setSpacing(0)  # No space between notes
        self.notes_layout.setContentsMargins(0, 0, 0, 0)
        self.notes_layout.addStretch()  # Push notes from bottom
        self.notes_container.setLayout(self.notes_layout)
        scroll_area.setWidget(self.notes_container)

        filled_layout.addWidget(scroll_area, 1)

        # Remove Note button at bottom
        self.btn_remove = QPushButton("Remove Note")
        self.btn_remove.setStyleSheet("QPushButton { min-height: 25px; max-height: 25px; }")
        self.btn_remove.clicked.connect(self.remove_selected_note)
        filled_layout.addWidget(self.btn_remove)

        # Sustain Previous Step button (filled state)
        self.btn_sustain_filled = QPushButton("Sustain Previous Step")
        self.btn_sustain_filled.setStyleSheet("QPushButton { min-height: 25px; max-height: 25px; font-size: 8pt; }")
        self.btn_sustain_filled.setToolTip("Copy all notes from the previous step as sustained notes")
        self.btn_sustain_filled.clicked.connect(self.sustain_previous_step)
        filled_layout.addWidget(self.btn_sustain_filled)

        self.filled_container.setLayout(filled_layout)
        self.main_layout.addWidget(self.filled_container, 1)
        self.filled_container.setVisible(False)

        self.setLayout(self.main_layout)
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(2)
        self.setMinimumWidth(140)
        self.setMaximumWidth(140)

        # Update empty state styling
        self.update_empty_state()

    def update_empty_state(self):
        """Update styling based on whether step is empty"""
        is_empty = len(self.note_labels) == 0

        if is_empty:
            # Use theme-based darker background
            palette = self.palette()
            bg_color = palette.color(QPalette.Window)
            darker_bg = bg_color.darker(130)
            self.setStyleSheet(f"QFrame {{ background-color: {darker_bg.name()}; }}")
            self.empty_container.setVisible(True)
            self.filled_container.setVisible(False)
        else:
            # Normal styling
            self.setStyleSheet("")
            self.empty_container.setVisible(False)
            self.filled_container.setVisible(True)

    def add_note(self):
        """Add a new note to this step"""
        if len(self.note_labels) >= 8:
            QMessageBox.warning(None, "Maximum Notes", "Maximum 8 notes per step reached")
            return

        note_label = CompactNoteLabel(len(self.note_labels), self.is_step_sequencer)
        note_label.selected.connect(lambda: self.select_note(note_label))
        self.note_labels.append(note_label)
        # Insert before the stretch (which is the last item)
        self.notes_layout.insertWidget(self.notes_layout.count() - 1, note_label)

        # Auto-select the new note
        self.select_note(note_label)

        # Update button state
        self.btn_add_note.setEnabled(len(self.note_labels) < 8)

        # Update empty state
        self.update_empty_state()

    def select_note(self, note_label):
        """Select a note and show its data in the controls"""
        # Deselect all notes
        for label in self.note_labels:
            label.set_selected(False)

        # Select this note
        note_label.set_selected(True)
        self.selected_note_index = self.note_labels.index(note_label)

        # Load note data into controls
        data = note_label.get_note_data()
        self.velocity_bar.set_velocity(data.get('velocity', 200))

        if self.is_step_sequencer:
            self.note_selector.set_value(data.get('note_index', 0))
            self.octave_selector.set_value(data.get('octave_offset', 4))
        else:
            self.interval_selector.set_value(data.get('semitone_offset', 0))
            self.octave_selector.set_value(data.get('octave_offset', 0))

    def on_velocity_changed(self, velocity):
        """Velocity changed - update selected note"""
        if self.selected_note_index is not None and self.selected_note_index < len(self.note_labels):
            note_label = self.note_labels[self.selected_note_index]
            data = note_label.get_note_data()
            data['velocity'] = velocity
            note_label.set_note_data(data)

    def on_interval_changed(self, value):
        """Interval changed - update selected note"""
        if self.selected_note_index is not None and self.selected_note_index < len(self.note_labels):
            note_label = self.note_labels[self.selected_note_index]
            data = note_label.get_note_data()
            data['semitone_offset'] = value
            note_label.set_note_data(data)

    def on_note_changed(self, value):
        """Note changed - update selected note"""
        if self.selected_note_index is not None and self.selected_note_index < len(self.note_labels):
            note_label = self.note_labels[self.selected_note_index]
            data = note_label.get_note_data()
            data['note_index'] = value
            note_label.set_note_data(data)

    def on_octave_changed(self, value):
        """Octave changed - update selected note"""
        if self.selected_note_index is not None and self.selected_note_index < len(self.note_labels):
            note_label = self.note_labels[self.selected_note_index]
            data = note_label.get_note_data()
            data['octave_offset'] = value
            note_label.set_note_data(data)

    def remove_selected_note(self):
        """Remove the currently selected note"""
        if self.selected_note_index is not None and self.selected_note_index < len(self.note_labels):
            note_label = self.note_labels[self.selected_note_index]
            self.note_labels.remove(note_label)
            self.notes_layout.removeWidget(note_label)
            note_label.deleteLater()

            # Renumber remaining notes
            for i, label in enumerate(self.note_labels):
                label.note_num = i
                label.update_label()

            # Clear selection
            self.selected_note_index = None

            # Update button state
            self.btn_add_note.setEnabled(len(self.note_labels) < 8)

            # Update empty state
            self.update_empty_state()

            # If there are still notes, select the first one
            if len(self.note_labels) > 0:
                self.select_note(self.note_labels[0])

    def sustain_previous_step(self):
        """Copy all notes from the previous step as sustained notes"""
        if self.step_num == 0:
            return  # No previous step for step 0

        # Use the sibling_steps reference set by rebuild_steps
        if not hasattr(self, 'sibling_steps') or self.sibling_steps is None:
            return

        if self.step_num >= len(self.sibling_steps) or self.step_num == 0:
            return

        prev_step = self.sibling_steps[self.step_num - 1]
        prev_notes = prev_step.get_step_data()

        if not prev_notes:
            return

        # Clear current notes
        for label in self.note_labels[:]:
            self.notes_layout.removeWidget(label)
            label.deleteLater()
        self.note_labels.clear()
        self.selected_note_index = None

        # Add sustained copies of previous step's notes
        for note_data in prev_notes:
            sustained_data = note_data.copy()
            sustained_data['is_tie'] = True

            note_label = CompactNoteLabel(len(self.note_labels), self.is_step_sequencer)
            note_label.selected.connect(lambda nl=note_label: self.select_note(nl))
            note_label.set_note_data(sustained_data)
            self.note_labels.append(note_label)
            self.notes_layout.insertWidget(self.notes_layout.count() - 1, note_label)

        # Update button state
        self.btn_add_note.setEnabled(len(self.note_labels) < 8)
        self.update_empty_state()

        # Select first note if any
        if len(self.note_labels) > 0:
            self.select_note(self.note_labels[0])

    def get_step_data(self):
        """Return step data as list of note dicts"""
        notes = []
        for label in self.note_labels:
            notes.append(label.get_note_data())
        return notes

    def set_step_data(self, notes_data):
        """Load step data from list of note dicts"""
        # Clear existing notes
        for label in self.note_labels[:]:
            self.notes_layout.removeWidget(label)
            label.deleteLater()
        self.note_labels.clear()
        self.selected_note_index = None

        # Add notes from data
        for note_data in notes_data:
            note_label = CompactNoteLabel(len(self.note_labels), self.is_step_sequencer)
            note_label.selected.connect(lambda nl=note_label: self.select_note(nl))
            note_label.set_note_data(note_data)
            self.note_labels.append(note_label)
            # Insert before the stretch (which is the last item)
            self.notes_layout.insertWidget(self.notes_layout.count() - 1, note_label)

        # Update button state
        self.btn_add_note.setEnabled(len(self.note_labels) < 8)

        # Update empty state
        self.update_empty_state()

        # Select first note if any
        if len(self.note_labels) > 0:
            self.select_note(self.note_labels[0])




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
    ARP_CMD_SET_NOTE = 0xCA
    ARP_CMD_SET_NOTES_CHUNK = 0xCB
    ARP_CMD_SET_MODE = 0xCC
    ARP_CMD_GET_NOTES_CHUNK = 0xCE

    MANUFACTURER_ID = 0x7D
    SUB_ID = 0x00
    DEVICE_ID = 0x4D

    # Signals
    hid_data_received = pyqtSignal(bytes)

    def __init__(self):
        super().__init__()

        logger.info("Arpeggiator tab initialized")

        self.current_preset_id = 0  # Presets 0-118 factory rhythm patterns, 119-158 user
        self.is_step_sequencer = False  # This is the arpeggiator tab
        self.preset_data = {
            'preset_type': 0,  # PRESET_TYPE_ARPEGGIATOR
            'note_count': 0,
            'pattern_length_16ths': 16,
            'gate_length_percent': 80,
            'timing_mode': 0,  # 0=straight, 1=triplet, 2=dotted
            'note_value': 2,   # 0=quarter, 1=eighth, 2=sixteenth
            'steps': []  # Flat list of notes with timing
        }

        self.step_widgets = []
        self.clipboard_preset = None  # Internal clipboard for copy/paste
        self.hid_data_received.connect(self.handle_hid_response)

        # Dynamic tab tracking
        self._visible_tab_count = 1
        self._manually_expanded_count = 0
        self._user_presets_used = 0

        self.setup_ui()

    def setup_ui(self):
        """Build the UI with top tabs for presets and side tabs for Basic/Advanced"""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # === Top Preset Tabs (User Arp 1-40, pool-based) ===
        self.preset_tabs = QTabWidget()

        # Create all 40 user preset entry widgets (presets 119-158 for arpeggiator, pool-based)
        from protocol.feature_names import get_feature_name_manager, FEATURE_ARP
        mgr = get_feature_name_manager()
        self.entry_widgets = []
        for i in range(40):
            preset_id = 119 + i  # User Arp presets start at 119 (after 119 factory patterns)
            entry = self._create_preset_entry(i, preset_id)
            self.entry_widgets.append(entry)

        # Initially show only 1 tab + "+" button (will expand on rebuild with device info)
        self.preset_tabs.addTab(self.entry_widgets[0]['widget'], mgr.get_name(FEATURE_ARP, 0))
        plus_widget = QWidget()
        self.preset_tabs.addTab(plus_widget, "+")

        self.preset_tabs.currentChanged.connect(self.on_preset_tab_changed)
        main_layout.addWidget(self.preset_tabs, 1)

        # === Bottom Section: Parameters and Actions ===
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)

        # Left Container: Preset Parameters
        params_group = QGroupBox()
        params_group.setMaximumWidth(500)
        params_layout = QGridLayout()

        # Arpeggiator Mode
        lbl_mode = QLabel("Arpeggiator Mode:")
        self.combo_mode = ArrowComboBox()
        self.combo_mode.setMinimumWidth(150)
        self.combo_mode.setMaximumHeight(30)
        self.combo_mode.setEditable(True)
        self.combo_mode.lineEdit().setReadOnly(True)
        self.combo_mode.lineEdit().setAlignment(Qt.AlignCenter)
        self.combo_mode.addItem("Single Note Synced", 0)
        self.combo_mode.addItem("Single Note Unsynced", 1)
        self.combo_mode.addItem("Chord Synced", 2)
        self.combo_mode.addItem("Chord Unsynced", 3)
        self.combo_mode.addItem("Chord Advanced", 4)
        # Advanced chord-ordering variants (one note per step, visited in a
        # pitch-derived order). Mirror the firmware arp_mode_t enum values 5-10
        # and the on-device quick-build "Sync" labels (Asc/Desc/Up-Down/...).
        self.combo_mode.addItem("Chord Ascending", 5)
        self.combo_mode.addItem("Chord Descending", 6)
        self.combo_mode.addItem("Chord Up-Down", 7)
        self.combo_mode.addItem("Chord Down-Up", 8)
        self.combo_mode.addItem("Chord Mix 1", 9)
        self.combo_mode.addItem("Chord Mix 2", 10)
        self.combo_mode.setToolTip("Select how the arpeggiator plays notes")
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)
        params_layout.addWidget(lbl_mode, 0, 0)
        params_layout.addWidget(self.combo_mode, 0, 1)

        # Pattern Rate
        lbl_pattern_rate = QLabel("Pattern Rate:")
        self.combo_pattern_rate = ArrowComboBox()
        self.combo_pattern_rate.setMinimumWidth(150)
        self.combo_pattern_rate.setMaximumHeight(30)
        self.combo_pattern_rate.setEditable(True)
        self.combo_pattern_rate.lineEdit().setReadOnly(True)
        self.combo_pattern_rate.lineEdit().setAlignment(Qt.AlignCenter)
        self.combo_pattern_rate.addItem("1/4", 0)
        self.combo_pattern_rate.addItem("1/4T", 1)
        self.combo_pattern_rate.addItem("1/4.", 2)
        self.combo_pattern_rate.addItem("1/8", 3)
        self.combo_pattern_rate.addItem("1/8T", 4)
        self.combo_pattern_rate.addItem("1/8.", 5)
        self.combo_pattern_rate.addItem("1/16", 6)
        self.combo_pattern_rate.addItem("1/16T", 7)
        self.combo_pattern_rate.addItem("1/16.", 8)
        self.combo_pattern_rate.setCurrentIndex(6)
        self.combo_pattern_rate.setToolTip("Note subdivision and timing mode (T=triplet, .=dotted)")
        self.combo_pattern_rate.currentIndexChanged.connect(self.on_pattern_rate_changed)
        params_layout.addWidget(lbl_pattern_rate, 1, 0)
        params_layout.addWidget(self.combo_pattern_rate, 1, 1)

        # Number of steps
        lbl_num_steps = QLabel("Number of Steps:")
        self.spin_num_steps = QSpinBox()
        self.spin_num_steps.setRange(1, 128)
        self.spin_num_steps.setValue(8)
        self.spin_num_steps.setButtonSymbols(QSpinBox.UpDownArrows)
        self.spin_num_steps.setToolTip("Number of steps in the pattern")
        self.spin_num_steps.valueChanged.connect(self.on_num_steps_changed)
        params_layout.addWidget(lbl_num_steps, 2, 0)
        params_layout.addWidget(self.spin_num_steps, 2, 1)

        # Pattern rhythm
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

        # Default velocity
        lbl_default_velocity = QLabel("Default Velocity:")
        self.spin_default_velocity = QSpinBox()
        self.spin_default_velocity.setRange(1, 127)
        self.spin_default_velocity.setValue(127)
        self.spin_default_velocity.setButtonSymbols(QSpinBox.UpDownArrows)
        self.spin_default_velocity.setToolTip("Default velocity for new notes in basic grid")
        self.spin_default_velocity.valueChanged.connect(self.on_default_velocity_changed)
        params_layout.addWidget(lbl_default_velocity, 5, 0)
        params_layout.addWidget(self.spin_default_velocity, 5, 1)

        params_group.setLayout(params_layout)
        bottom_layout.addWidget(params_group)

        # Right Container: Actions
        actions_group = QGroupBox()
        actions_group.setMaximumWidth(500)
        actions_layout = QGridLayout()

        button_style = "QPushButton { min-height: 30px; max-height: 30px; border-radius: 5px; }"

        self.btn_load = QPushButton("Load from Device")
        self.btn_load.setStyleSheet(button_style)
        self.btn_load.clicked.connect(self.load_preset)
        self.btn_save = QPushButton("Save to Device")
        self.btn_save.setStyleSheet(button_style)
        self.btn_save.clicked.connect(self.save_preset)

        actions_layout.addWidget(self.btn_load, 0, 0, 1, 2)
        actions_layout.addWidget(self.btn_save, 1, 0, 1, 2)

        # Copy and Paste buttons
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
        actions_layout.addLayout(copy_paste_layout, 2, 0, 1, 2)

        # Reset All Steps button
        self.btn_reset_all = QPushButton("Reset All Steps")
        self.btn_reset_all.setStyleSheet(button_style)
        self.btn_reset_all.clicked.connect(self.reset_all_steps)
        actions_layout.addWidget(self.btn_reset_all, 3, 0, 1, 2)

        actions_group.setLayout(actions_layout)
        bottom_layout.addWidget(actions_group)

        bottom_layout.addStretch(1)
        main_layout.addLayout(bottom_layout)

        # Status and memory layout
        status_row = QHBoxLayout()
        self.lbl_status = QLabel("Ready. Select a preset tab to begin.")
        palette_status = self.lbl_status.palette()
        info_color = palette_status.color(QPalette.Highlight)
        self.lbl_status.setStyleSheet(f"color: {info_color.name()}; padding: 5px;")
        status_row.addWidget(self.lbl_status)
        status_row.addStretch()
        self.lbl_memory = QLabel("")
        self.lbl_memory.setStyleSheet("padding: 5px;")
        status_row.addWidget(self.lbl_memory)
        main_layout.addLayout(status_row)

        # Debug console
        self.debug_console = DebugConsole("Arpeggiator Debug Console")
        main_layout.addWidget(self.debug_console)

        self.addLayout(main_layout)

        # Initialize with first preset
        self._setup_current_preset_entry()
        self.rebuild_steps()
        self.update_pattern_length_display()

    def _update_visible_preset_tabs(self):
        """Update which preset tabs are visible based on used count and manual expansion"""
        max_tabs = len(self.entry_widgets)
        base_visible = max(1, self._user_presets_used)
        self._visible_tab_count = min(max_tabs, base_visible + self._manually_expanded_count)

        # Block signals to avoid triggering on_preset_tab_changed during rebuild
        self.preset_tabs.blockSignals(True)

        # Remove all tabs
        while self.preset_tabs.count() > 0:
            self.preset_tabs.removeTab(0)

        # Add visible preset tabs with names from feature manager
        from protocol.feature_names import get_feature_name_manager, FEATURE_ARP
        mgr = get_feature_name_manager()
        for x in range(self._visible_tab_count):
            self.preset_tabs.addTab(self.entry_widgets[x]['widget'], mgr.get_name(FEATURE_ARP, x))

        # Add "+" tab if not all tabs are visible
        if self._visible_tab_count < max_tabs:
            plus_widget = QWidget()
            self.preset_tabs.addTab(plus_widget, "+")

        self.preset_tabs.blockSignals(False)

    def _create_preset_entry(self, index, preset_id):
        """Create a preset entry widget with top tabs for Basic/Advanced"""
        from protocol.feature_names import get_feature_name_manager, FEATURE_ARP, MAX_NAME_LENGTH

        # Main container widget
        container = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header with title and rename button
        header_layout = QHBoxLayout()
        mgr = get_feature_name_manager()
        title_label = QLabel(f"<b>{mgr.get_name(FEATURE_ARP, index)}</b>")
        title_label.setStyleSheet("font-size: 14pt;")
        header_layout.addWidget(title_label)

        btn_rename = QPushButton("Rename")
        btn_rename.setMaximumHeight(24)
        btn_rename.setMaximumWidth(60)
        btn_rename.setStyleSheet("QPushButton { font-size: 8pt; border-radius: 3px; padding: 2px 6px; }")
        btn_rename.clicked.connect(lambda checked, idx=index, lbl=title_label: self._on_rename_arp(idx, lbl))
        header_layout.addWidget(btn_rename)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Description
        desc = QLabel("Configure arpeggiator pattern with intervals relative to the played notes.\n"
                      "Click cells to toggle notes on/off. Right-click for velocity and octave settings.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(desc)

        # Top tabs for Basic/Advanced
        side_tabs = QTabWidget()

        # Basic tab with grid
        basic_grid = BasicArpeggiatorGrid()
        side_tabs.addTab(basic_grid, "Basic")

        # Advanced tab with step widgets
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout()
        advanced_layout.setContentsMargins(0, 0, 0, 0)

        step_scroll = QScrollArea()
        step_scroll.setWidgetResizable(True)
        step_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        step_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        step_scroll.setMinimumHeight(300)

        step_container = QWidget()
        step_layout = QHBoxLayout()
        step_layout.setSpacing(2)
        step_layout.setDirection(QHBoxLayout.LeftToRight)
        step_container.setLayout(step_layout)
        step_scroll.setWidget(step_container)

        advanced_layout.addWidget(step_scroll)
        advanced_tab.setLayout(advanced_layout)
        side_tabs.addTab(advanced_tab, "Advanced")

        layout.addWidget(side_tabs, 1)
        container.setLayout(layout)

        return {
            'widget': container,
            'title_label': title_label,
            'basic_grid': basic_grid,
            'side_tabs': side_tabs,
            'step_scroll': step_scroll,
            'step_container': step_container,
            'step_layout': step_layout,
            'preset_id': preset_id,
            'step_widgets': []
        }

    def _setup_current_preset_entry(self):
        """Setup references to current preset entry's components"""
        current_idx = self.preset_tabs.currentIndex()
        if current_idx < 0 or current_idx >= len(self.entry_widgets):
            return

        entry = self.entry_widgets[current_idx]
        self.basic_grid = entry['basic_grid']
        self.basic_grid.dataChanged.connect(self.on_basic_grid_changed)
        self.step_layout = entry['step_layout']
        self.step_widgets = entry['step_widgets']
        self.tabs = entry['side_tabs']
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.current_preset_id = entry['preset_id']

        # Initialize basic grid settings
        if hasattr(self, 'spin_default_velocity'):
            self.basic_grid.default_velocity = self.spin_default_velocity.value() * 2
        # Sync basic grid's num_steps with the spin control
        if hasattr(self, 'spin_num_steps') and self.basic_grid.num_steps != self.spin_num_steps.value():
            self.basic_grid.on_steps_changed(self.spin_num_steps.value())

    def on_preset_tab_changed(self, index):
        """Handle preset tab change - including '+' tab expansion"""
        # Check if "+" tab was clicked
        if self._visible_tab_count < len(self.entry_widgets) and index == self._visible_tab_count:
            self._manually_expanded_count += 1
            self._update_visible_preset_tabs()
            self.preset_tabs.setCurrentIndex(self._visible_tab_count - 1)
            return

        if index < 0 or index >= len(self.entry_widgets):
            return

        # Disconnect old signals
        if hasattr(self, 'basic_grid') and self.basic_grid:
            try:
                self.basic_grid.dataChanged.disconnect(self.on_basic_grid_changed)
            except:
                pass
        if hasattr(self, 'tabs') and self.tabs:
            try:
                self.tabs.currentChanged.disconnect(self.on_tab_changed)
            except:
                pass

        # Setup new preset entry
        self._setup_current_preset_entry()

        # Rebuild steps for this entry
        self.rebuild_steps()

        # Auto-load preset from device
        if self.valid():
            self.load_preset()
        else:
            from protocol.feature_names import get_feature_name_manager, FEATURE_ARP
            self.update_status(f"{get_feature_name_manager().get_name(FEATURE_ARP, index)} selected")

    def _on_rename_arp(self, index, title_label):
        """Open rename dialog for an arp preset"""
        from protocol.feature_names import get_feature_name_manager, FEATURE_ARP, MAX_NAME_LENGTH
        mgr = get_feature_name_manager()
        current = mgr.get_name(FEATURE_ARP, index)
        new_name, ok = QInputDialog.getText(
            None, "Rename Arp Preset",
            f"Name for User Arp {index + 1} (max {MAX_NAME_LENGTH} chars):",
            text=current
        )
        if ok:
            mgr.set_name(FEATURE_ARP, index, new_name.strip()[:MAX_NAME_LENGTH])
            display = mgr.get_name(FEATURE_ARP, index)
            title_label.setText(f"<b>{display}</b>")
            self.preset_tabs.setTabText(index, display)

    def rebuild_steps(self):
        """Rebuild step widgets based on step count - preserve existing data"""
        # Save existing step data before clearing
        old_step_data = []
        for widget in self.step_widgets:
            old_step_data.append(widget.get_step_data())

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

            # Restore existing step data if available from old widgets
            if i < len(old_step_data):
                step_widget.set_step_data(old_step_data[i])

            self.step_widgets.append(step_widget)
            self.step_layout.addWidget(step_widget, 0, Qt.AlignLeft)  # Explicitly align left

        # Set sibling references so steps can access each other (for sustain previous step)
        for step_widget in self.step_widgets:
            step_widget.sibling_steps = self.step_widgets

        self.step_layout.addStretch()  # Add stretch at the end to push steps to the left
        self.update_pattern_length_display()
        self.update_status(f"Rebuilt sequencer with {step_count} steps")

    def on_mode_changed(self, index):
        """Arpeggiator mode changed - send to device immediately"""
        mode = self.combo_mode.currentData()
        if mode is None:
            mode = 0  # Default to Single Note

        mode_names = ["Single Note Synced", "Single Note Unsynced", "Chord Synced", "Chord Unsynced", "Chord Advanced"]
        mode_name = mode_names[mode] if mode < len(mode_names) else f"Mode {mode}"

        # Send mode change to device
        if self.send_hid_command(self.ARP_CMD_SET_MODE, [mode]):
            self.update_status(f"Arpeggiator mode changed to {mode_name}")
        else:
            self.update_status(f"Failed to set arpeggiator mode", error=True)

    def on_pattern_rate_changed(self, index):
        """Pattern rate changed - update pattern length display"""
        rate_text = self.combo_pattern_rate.currentText()
        self.update_pattern_length_display()
        self.update_status(f"Pattern rate changed to {rate_text}")

    def on_num_steps_changed(self, value):
        """Number of steps changed - rebuild and update pattern length"""
        self.rebuild_steps()
        # Also update basic grid's num_steps when changed from preset container
        if hasattr(self, 'basic_grid') and self.basic_grid.num_steps != value:
            self.basic_grid.on_steps_changed(value)

    def on_default_velocity_changed(self, value):
        """Default velocity changed - update basic grid"""
        if hasattr(self, 'basic_grid'):
            # Convert display value (1-127) to internal value (2-254)
            internal_value = value * 2
            self.basic_grid.default_velocity = internal_value
            self.update_status(f"Default velocity changed to {value}")

    def get_rate_and_timing_from_combo(self):
        """Helper to extract rate_16ths, note_value, and timing_mode from combo box data.

        Returns:
            tuple: (rate_16ths, note_value, timing_mode)
        """
        data = self.combo_pattern_rate.currentData()
        if data is None:
            data = 6  # Default to 1/16 straight
        note_value = data // 3  # 0=quarter, 1=eighth, 2=sixteenth
        timing_mode = data % 3  # 0=straight, 1=triplet, 2=dotted
        # Base rate: quarter=4, eighth=2, sixteenth=1
        base_rate_map = {0: 4, 1: 2, 2: 1}
        rate_16ths = base_rate_map.get(note_value, 1)
        return (rate_16ths, note_value, timing_mode)

    def update_pattern_length_display(self):
        """Update the pattern length display in x/y format with halving logic"""
        rate_16ths, note_value, timing_mode = self.get_rate_and_timing_from_combo()

        num_steps = self.spin_num_steps.value()

        # Calculate pattern length in 16ths
        pattern_length_16ths = rate_16ths * num_steps

        # Calculate denominator from rate (y value)
        # rate_16ths = 4 means /4, 2 means /8, 1 means /16
        # Denominator: 4 -> /4, 2 -> /8, 1 -> /16
        denominator_map = {4: 4, 2: 8, 1: 16}
        y = denominator_map.get(rate_16ths, 16)

        # x is the number of steps
        x = num_steps

        # Apply halving logic: keep halving both x and y if possible, stop at y=4
        import math
        while x % 2 == 0 and y % 2 == 0 and y > 4:
            x = x // 2
            y = y // 2

        self.lbl_pattern_length.setText(f"{x}/{y}")

    def _get_complete_steps_from_grid(self, grid_data, num_steps, rate_16ths):
        """Helper: Convert basic grid data to steps array (no empty placeholders needed)"""
        # Group grid data by timing to see which steps have notes
        notes_by_timing = {}
        for note in grid_data:
            timing = note['timing_16ths']
            if timing not in notes_by_timing:
                notes_by_timing[timing] = []
            notes_by_timing[timing].append(note)

        # Build steps array - only include steps that have notes
        # Empty steps are simply absent from the data
        complete_steps = []
        for step_idx in range(num_steps):
            step_timing = step_idx * rate_16ths

            if step_timing in notes_by_timing:
                # This step has notes from the grid - use them
                complete_steps.extend(notes_by_timing[step_timing])
            # No else - empty steps are not represented

        return complete_steps

    def on_basic_grid_changed(self):
        """Handle changes in basic grid - live update preset data"""
        # Get current rate and timing
        rate_16ths, note_value, timing_mode = self.get_rate_and_timing_from_combo()

        # Get grid data (flat list with timing) - ONLY returns active cells
        grid_data = self.basic_grid.get_grid_data(rate_16ths)

        # Get complete steps
        num_steps = self.spin_num_steps.value()

        complete_steps = self._get_complete_steps_from_grid(grid_data, num_steps, rate_16ths)

        # Update preset_data with COMPLETE steps (including empty ones)
        self.preset_data['steps'] = complete_steps
        self.preset_data['note_count'] = len(complete_steps)

        # Calculate pattern length
        self.preset_data['pattern_length_16ths'] = rate_16ths * num_steps

        # Note: Don't rebuild advanced view here - only sync when switching tabs

    def on_tab_changed(self, index):
        """Handle tab switching - sync data between views"""
        if index == 0:  # Switched to Basic tab
            # Sync data from Advanced to Basic
            self.sync_advanced_to_basic()
        elif index == 1:  # Switched to Advanced tab
            # Sync data from Basic to Advanced
            self.sync_basic_to_advanced()

    def sync_advanced_to_basic(self):
        """Sync data from Advanced view to Basic grid"""
        # Read directly from step widgets (Advanced tab) - don't use gather_preset_data()
        # because the Basic tab is already active when this is called
        rate_16ths, note_value, timing_mode = self.get_rate_and_timing_from_combo()
        num_steps = self.spin_num_steps.value()

        all_notes = []
        for i, widget in enumerate(self.step_widgets):
            step_notes = widget.get_step_data()
            timing_16ths = i * rate_16ths
            for note_data in step_notes:
                note_data['timing_16ths'] = timing_16ths
                all_notes.append(note_data)

        # Update preset_data with step widget data
        self.preset_data['steps'] = all_notes
        self.preset_data['note_count'] = len(all_notes)

        # Set grid data (includes num_steps sync and rate)
        self.basic_grid.set_grid_data(all_notes, num_steps, rate_16ths)

    def sync_basic_to_advanced(self):
        """Sync data from Basic grid to Advanced view"""
        # Calculate rate and timing to determine timing for each step
        rate_16ths, note_value, timing_mode = self.get_rate_and_timing_from_combo()

        # Get grid data (flat list with timing) - ONLY returns active cells
        grid_data = self.basic_grid.get_grid_data(rate_16ths)

        # Number of steps comes from preset container (spin_num_steps)
        num_steps = self.spin_num_steps.value()

        # Ensure basic grid is in sync with preset container
        if self.basic_grid.num_steps != num_steps:
            self.basic_grid.on_steps_changed(num_steps)

        # Get complete steps including Empty placeholders for empty steps
        complete_steps = self._get_complete_steps_from_grid(grid_data, num_steps, rate_16ths)

        # Update preset_data with COMPLETE steps (including empty ones)
        self.preset_data['steps'] = complete_steps
        self.preset_data['note_count'] = len(complete_steps)

        # CRITICAL: Update pattern_length and gate from preset container before applying
        # These are the authoritative source and must be synced to preset_data
        self.preset_data['pattern_length_16ths'] = rate_16ths * num_steps
        self.preset_data['gate_length_percent'] = self.spin_gate.value()

        # Rebuild advanced view using apply_preset_data
        # Use recalculate_from_pattern_length=False to preserve existing num_steps and rate
        # (we already have the correct values from the UI controls)
        self.apply_preset_data(recalculate_from_pattern_length=False)

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
        """Gather current UI state into preset_data dict - preserves ALL notes including empty ones"""
        # Calculate pattern length from rate × steps
        rate_16ths, note_value, timing_mode = self.get_rate_and_timing_from_combo()
        num_steps = self.spin_num_steps.value()
        self.preset_data['pattern_length_16ths'] = rate_16ths * num_steps
        self.preset_data['gate_length_percent'] = self.spin_gate.value()
        self.preset_data['preset_type'] = 0  # PRESET_TYPE_ARPEGGIATOR
        self.preset_data['timing_mode'] = timing_mode  # 0=straight, 1=triplet, 2=dotted
        self.preset_data['note_value'] = note_value    # 0=quarter, 1=eighth, 2=sixteenth

        # Check which tab is active: Basic (index 0) or Advanced (index 1)
        # If Basic tab is active, gather from the basic grid instead of step_widgets
        active_tab = self.tabs.currentIndex() if hasattr(self, 'tabs') else 1

        if active_tab == 0 and hasattr(self, 'basic_grid') and self.basic_grid is not None:
            # Basic tab is active - gather from basic grid
            grid_data = self.basic_grid.get_grid_data(rate_16ths)
            all_notes = self._get_complete_steps_from_grid(grid_data, num_steps, rate_16ths)
        else:
            # Advanced tab is active - gather from step widgets
            all_notes = []
            for i, widget in enumerate(self.step_widgets):
                step_notes = widget.get_step_data()  # Returns list of note dicts
                timing_16ths = i * rate_16ths

                for note_data in step_notes:
                    # Add timing to note
                    note_data['timing_16ths'] = timing_16ths

                    # Convert to firmware format
                    if self.is_step_sequencer:
                        # Step sequencer: note_index already contains absolute note (0-11)
                        # octave_offset contains absolute octave (0-7)
                        pass  # Data is already in the right format
                    else:
                        # Arpeggiator: Convert flat semitones to (interval, octave) for firmware
                        # GUI stores semitone_offset and octave_offset separately
                        # Firmware needs them combined as flat semitones, then split into note_index and octave_offset
                        semitone = note_data.get('semitone_offset', 0)
                        octave = note_data.get('octave_offset', 0)

                        # Convert to flat semitones
                        flat_semitones = interval_octave_to_flat_semitones(semitone, octave)

                        # Convert back to firmware format (interval within octave + octave offset)
                        interval, octave_offset = flat_semitones_to_interval_octave(flat_semitones)

                        # Store in firmware format
                        note_data['note_index'] = interval
                        note_data['octave_offset'] = octave_offset

                    # Raw travel is velocity
                    note_data['raw_travel'] = note_data.get('velocity', 200)

                    all_notes.append(note_data)

        self.preset_data['steps'] = all_notes
        # Note count includes ALL notes for internal tracking - firmware will filter empty ones
        self.preset_data['note_count'] = len(all_notes)

    def get_firmware_notes(self):
        """Get notes for firmware - all notes are valid (no empty placeholders exist)"""
        # Return all notes - there are no empty placeholders to filter
        return self.preset_data.get('steps', [])

    def apply_preset_data(self, recalculate_from_pattern_length=True):
        """Apply preset_data to UI - convert flat note list to step-based structure

        Args:
            recalculate_from_pattern_length: If True, recalculate num_steps and rate from
                pattern_length_16ths (used when loading from device/clipboard).
                If False, use existing UI values (used when syncing from Basic to Advanced).
        """
        self.spin_gate.setValue(self.preset_data.get('gate_length_percent', 80))

        # Convert flat note list back to step-based structure
        # Group notes by timing
        notes_by_timing = {}
        for note in self.preset_data.get('steps', []):
            timing = note.get('timing_16ths', 0)
            if timing not in notes_by_timing:
                notes_by_timing[timing] = []
            notes_by_timing[timing].append(note)

        # Determine number of steps from pattern length, rate, timing mode, and note value
        if recalculate_from_pattern_length:
            # Recalculate num_steps and rate from pattern_length_16ths
            # (used when loading preset from device or clipboard)
            pattern_length = self.preset_data.get('pattern_length_16ths', 16)
            timing_mode = self.preset_data.get('timing_mode', 0)  # 0=straight
            note_value = self.preset_data.get('note_value', 2)    # 2=sixteenth

            # Calculate combo data: (note_value * 3) + timing_mode
            combo_data = (note_value * 3) + timing_mode

            # Base rate: quarter=4, eighth=2, sixteenth=1
            base_rate_map = {0: 4, 1: 2, 2: 1}
            rate_16ths = base_rate_map.get(note_value, 1)

            # Calculate num_steps
            num_steps = pattern_length // rate_16ths
            if pattern_length % rate_16ths == 0 and 1 <= num_steps <= 128:
                self.combo_pattern_rate.setCurrentIndex(combo_data)
                self.spin_num_steps.setValue(num_steps)
            else:
                # Fallback: use 1/16 notes straight
                self.combo_pattern_rate.setCurrentIndex(6)  # 1/16 straight
                self.spin_num_steps.setValue(max(1, min(128, pattern_length)))

        # Rebuild steps and populate with notes
        self.rebuild_steps()

        # Populate steps with notes
        rate_16ths, note_value, timing_mode = self.get_rate_and_timing_from_combo()
        for i, widget in enumerate(self.step_widgets):
            step_timing = i * rate_16ths
            step_notes = notes_by_timing.get(step_timing, [])
            widget.set_step_data(step_notes)

        # Sync loaded data to Basic grid so it reflects the preset immediately
        # (Basic tab is the default visible tab, but only Advanced steps were populated above)
        if hasattr(self, 'basic_grid') and self.basic_grid:
            self.sync_advanced_to_basic()

    def on_preset_changed(self, index):
        """Preset selection changed"""
        self.current_preset_id = index

        # Update UI state - use correct threshold based on preset type
        # Arpeggiator: factory 0-118, user 119-158 (pool-based)
        # Step Sequencer: factory 68-115, user 116-155 (pool-based)
        if self.is_step_sequencer:
            is_factory = (index < 116)
            factory_range = "68-115"
        else:
            is_factory = (index < 119)
            factory_range = "0-118"

        self.btn_save.setEnabled(not is_factory)

        if is_factory:
            self.update_status(f"Factory preset {index} selected (read-only)")
        else:
            self.update_status(f"User preset {index} selected")

    def send_hid_command(self, cmd, params, return_response=False):
        """Send HID command to device. If return_response=True, returns raw response bytes instead of bool."""
        # Map command codes to names for debug output
        cmd_names = {
            0xC0: "GET_PRESET", 0xC1: "SET_PRESET", 0xC2: "SAVE_PRESET",
            0xC3: "LOAD_PRESET", 0xC4: "CLEAR_PRESET", 0xC5: "COPY_PRESET",
            0xC6: "RESET_ALL", 0xC7: "GET_STATE", 0xC8: "SET_STATE",
            0xC9: "GET_INFO", 0xCA: "SET_NOTE", 0xCB: "SET_NOTES_CHUNK",
            0xCC: "SET_MODE", 0xCE: "GET_NOTES_CHUNK"
        }
        cmd_name = cmd_names.get(cmd, f"UNKNOWN(0x{cmd:02X})")

        if not isinstance(self.device, VialKeyboard):
            self.debug_log(f"HID TX BLOCKED - device not connected (cmd={cmd_name})", "ERROR")
            self.update_status("Error: Device not connected", error=True)
            return None if return_response else False

        self.debug_log(f"HID TX: cmd=0x{cmd:02X} ({cmd_name}) params=[{', '.join(f'0x{p:02X}' if isinstance(p, int) else repr(p) for p in params)}] ({len(params)} params)", "HID_TX")

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

        # Log raw packet hex
        hex_str = ' '.join(f'{b:02X}' for b in data)
        self.debug_log(f"HID TX RAW: [{hex_str}]", "HID_TX")

        try:
            response = self.device.keyboard.usb_send(
                self.device.keyboard.dev, bytes(data), retries=20)
            logger.info(f"Sent HID command: 0x{cmd:02X}")

            # Log and process response
            if response:
                hex_str = ' '.join(f'{b:02X}' for b in response[:32])
                self.debug_log(f"HID RX RAW: [{hex_str}] ({len(response)} bytes)", "HID_RX")

                resp_status = response[4] if len(response) > 4 else 0xFF
                resp_cmd = response[3] if len(response) > 3 else 0
                resp_cmd_name = cmd_names.get(resp_cmd, f"0x{resp_cmd:02X}")
                self.debug_log(f"HID RX: cmd={resp_cmd_name} status=0x{resp_status:02X}", "HID_RX")

                # (#8) Correlate the reply to the command we sent. The custom protocol
                # echoes the command byte at response[3]; a mismatch means we read a
                # stale/out-of-order reply (e.g. a slow command answering after its
                # read window). Do NOT apply it as this command's data — treat it as a
                # failed transfer so the caller can retry rather than showing/saving
                # another command's payload.
                if resp_cmd != cmd:
                    self.debug_log(
                        f"HID RX: reply cmd 0x{resp_cmd:02X} != sent 0x{cmd:02X} "
                        f"(stale/mismatched) — ignoring", "WARN")
                    return None if return_response else False

                if return_response:
                    return response

                # Process response data (applies preset data for GET_PRESET, etc.)
                self._process_hid_response(response)

                if resp_status != 0:
                    self.debug_log(f"HID {cmd_name}: device returned error status 0x{resp_status:02X}", "ERROR")
                    return False

                self.debug_log(f"HID TX+RX OK: {cmd_name} completed successfully", "HID_TX")
            else:
                self.debug_log(f"HID TX: empty response for {cmd_name}", "WARN")
                if return_response:
                    return None

            return True
        except RuntimeError as e:
            logger.error(f"HID send error: {e}")
            self.debug_log(f"HID TX FAIL: {cmd_name} RuntimeError: {e}", "ERROR")
            self.update_status(f"HID error: {e}", error=True)
            return None if return_response else False
        except Exception as e:
            logger.error(f"HID send error: {e}")
            self.debug_log(f"HID TX FAIL: {cmd_name} exception: {type(e).__name__}: {e}", "ERROR")
            self.update_status(f"HID error: {e}", error=True)
            return None if return_response else False

    def pack_note_data(self, note):
        """
        Pack a note into 3 bytes for transmission to firmware.
        Returns bytes: [packed_timing_vel_low, packed_timing_vel_high, note_octave]

        Note structure:
        - timing: 0-127 (7 bits)
        - velocity: 0-127 (7 bits)
        - sign: 0 or 1 (1 bit) - arp: interval sign / seq: sustained flag
        - note_index: 0-11 (4 bits)
        - octave_offset: -8 to +7 (4 bits signed)
        """
        timing = note.get('timing_16ths', 0) & 0x7F
        velocity = note.get('velocity', 200) // 2  # Convert 0-255 to 0-127
        velocity = max(0, min(127, velocity))

        # For arpeggiator: note_index can be negative (interval with sign)
        # For step sequencer: note_index is always positive (0-11), bit 14 = sustained flag
        note_index = note.get('note_index', 0)
        sign_bit = 0

        if note_index < 0:
            # Arpeggiator interval: extract sign and magnitude
            sign_bit = 1
            note_index = abs(note_index)
        elif note.get('is_tie', False):
            # Step sequencer: sustained flag (note continues from previous step)
            sign_bit = 1

        note_index = note_index & 0x0F  # 4 bits
        octave_offset = note.get('octave_offset', 0)

        # Clamp octave to -8..+7 range
        octave_offset = max(-8, min(7, octave_offset))

        # Pack timing_vel: bits 0-6=timing, 7-13=velocity, 14=sign/sustained, 15=timing high bit
        packed_timing_vel = timing | (velocity << 7) | (sign_bit << 14)

        # Pack note_octave: bits 0-3=note, 4-7=octave (as 4-bit signed)
        # Convert signed octave to 4-bit two's complement
        octave_4bit = octave_offset & 0x0F
        note_octave = note_index | (octave_4bit << 4)

        # Return as little-endian bytes
        return bytes([
            packed_timing_vel & 0xFF,        # Low byte
            (packed_timing_vel >> 8) & 0xFF, # High byte
            note_octave                       # Note/octave byte
        ])

    def send_notes_chunked(self, preset_id, notes):
        """
        Send note data to firmware in chunks.
        Each chunk can contain up to 9 notes (9 × 3 = 27 bytes).
        Returns True if all chunks sent successfully.
        """
        if not notes:
            self.debug_log("CHUNKS: No notes to send, returning True", "INFO")
            logger.info("No notes to send")
            return True

        chunk_size = 8  # Max 8 notes per packet: note data starts at byte 7 of the
        # 32-byte HID packet, so 9 notes (27 bytes) would run 2 bytes past the end
        total_notes = len(notes)
        total_chunks = (total_notes + chunk_size - 1) // chunk_size
        chunks_sent = 0

        self.debug_log(f"CHUNKS: Sending {total_notes} notes in {total_chunks} chunks "
                       f"(max {chunk_size} notes/chunk, 3 bytes/note)", "INFO")
        logger.info(f"Sending {total_notes} notes in chunks of {chunk_size}")

        for start_idx in range(0, total_notes, chunk_size):
            end_idx = min(start_idx + chunk_size, total_notes)
            chunk = notes[start_idx:end_idx]
            chunk_count = len(chunk)

            # Build parameter list for this chunk
            params = [
                preset_id,     # params[0]
                start_idx,     # params[1]
                chunk_count    # params[2]
            ]

            # Pack and append note data (3 bytes per note)
            for note in chunk:
                packed_bytes = self.pack_note_data(note)
                params.extend(packed_bytes)

            # Send chunk
            self.debug_log(f"CHUNKS: Sending chunk {chunks_sent + 1}/{total_chunks}: "
                           f"notes[{start_idx}..{end_idx - 1}] ({chunk_count} notes, "
                           f"{len(params)} param bytes)", "DATA")
            logger.info(f"Sending chunk {chunks_sent + 1}: notes {start_idx}-{end_idx - 1} ({chunk_count} notes)")

            if not self.send_hid_command(self.ARP_CMD_SET_NOTES_CHUNK, params):
                logger.error(f"Failed to send chunk {chunks_sent + 1}")
                self.debug_log(f"CHUNKS: FAILED at chunk {chunks_sent + 1}/{total_chunks}", "ERROR")
                self.update_status(f"Error: Failed to send notes (chunk {chunks_sent + 1})", error=True)
                return False

            chunks_sent += 1

            # Small delay between chunks to avoid overwhelming the device
            QTimer.singleShot(10, lambda: None)

        self.debug_log(f"CHUNKS: All {chunks_sent} chunks sent successfully ({total_notes} notes)", "INFO")
        logger.info(f"Successfully sent {chunks_sent} chunks ({total_notes} notes)")
        return True

    def unpack_note_data(self, low_byte, high_byte, note_octave_byte):
        """Unpack 3 bytes from firmware into a note dict (reverse of pack_note_data)"""
        packed_timing_vel = low_byte | (high_byte << 8)

        timing = packed_timing_vel & 0x7F
        velocity_7bit = (packed_timing_vel >> 7) & 0x7F
        sign_bit = (packed_timing_vel >> 14) & 0x01

        note_index = note_octave_byte & 0x0F
        octave_4bit = (note_octave_byte >> 4) & 0x0F
        # Convert 4-bit two's complement to signed
        octave_offset = octave_4bit if octave_4bit < 8 else octave_4bit - 16

        # Convert 7-bit velocity back to 0-255 range
        velocity = velocity_7bit * 2

        note = {
            'timing_16ths': timing,
            'velocity': velocity,
            'note_index': note_index,
            'octave_offset': octave_offset,
            'is_tie': False
        }

        if self.is_step_sequencer:
            note['is_tie'] = bool(sign_bit)
        else:
            # Arpeggiator: sign bit means negative interval
            if sign_bit:
                note['note_index'] = -note_index

        return note

    def receive_notes_chunked(self, note_count):
        """
        Read note data from firmware edit buffer in chunks after GET_PRESET.
        Returns a list of note dicts, or None on failure.
        """
        if note_count == 0:
            return []

        chunk_size = 8  # Max 8 notes per packet (matches firmware response-buffer limit)
        notes = []
        total_chunks = (note_count + chunk_size - 1) // chunk_size

        self.debug_log(f"RECV CHUNKS: Reading {note_count} notes in {total_chunks} chunks", "INFO")

        for start_idx in range(0, note_count, chunk_size):
            remaining = note_count - start_idx
            request_count = min(chunk_size, remaining)

            params = [start_idx, request_count]
            response = self.send_hid_command(self.ARP_CMD_GET_NOTES_CHUNK, params, return_response=True)

            if response is None:
                self.debug_log(f"RECV CHUNKS: FAILED at chunk starting at note {start_idx}", "ERROR")
                return None

            status = response[4] if len(response) > 4 else 0xFF
            if status != 0:
                self.debug_log(f"RECV CHUNKS: Error status {status} at note {start_idx}", "ERROR")
                return None

            notes_returned = response[5] if len(response) > 5 else 0
            note_data_start = 6  # params[2] onwards

            for i in range(notes_returned):
                offset = note_data_start + (i * 3)
                if offset + 2 < len(response):
                    note = self.unpack_note_data(
                        response[offset],
                        response[offset + 1],
                        response[offset + 2]
                    )
                    notes.append(note)

        self.debug_log(f"RECV CHUNKS: Successfully received {len(notes)} notes", "INFO")
        return notes

    def handle_hid_response(self, data):
        """Handle HID response from device (called via signal from external data).

        Logs raw data then delegates to _process_hid_response.
        """
        # Log raw response data (only when called via signal, not from send_hid_command)
        if data:
            hex_str = ' '.join(f'{b:02X}' for b in data[:32])
            self.debug_log(f"HID RX RAW (signal): [{hex_str}] ({len(data)} bytes)", "HID_RX")

        self._process_hid_response(data)

    def _process_hid_response(self, data):
        """Core response processing logic. Called by both handle_hid_response and send_hid_command."""
        if not data or len(data) < 4:
            self.debug_log(f"HID RX: response too short ({len(data) if data else 0} bytes), ignoring", "WARN")
            return

        cmd = data[3]
        status = data[4] if len(data) > 4 else 0xFF

        cmd_names = {
            0xC0: "GET_PRESET", 0xC1: "SET_PRESET", 0xC2: "SAVE_PRESET",
            0xC3: "LOAD_PRESET", 0xC4: "CLEAR_PRESET", 0xC5: "COPY_PRESET",
            0xC6: "RESET_ALL", 0xC7: "GET_STATE", 0xC8: "SET_STATE",
            0xC9: "GET_INFO", 0xCA: "SET_NOTE", 0xCB: "SET_NOTES_CHUNK",
            0xCC: "SET_MODE", 0xCE: "GET_NOTES_CHUNK"
        }
        cmd_name = cmd_names.get(cmd, f"UNKNOWN(0x{cmd:02X})")

        if status == 0:
            if cmd == self.ARP_CMD_GET_INFO:
                # Parse pool-based system info
                # data[4]=status, data[5]=factory_arp, data[6]=user_arp_max,
                # data[7]=factory_seq, data[8]=user_seq_max,
                # data[9]=max_arp_notes, data[10]=max_seq_notes,
                # data[11..12]=pool_notes_free (uint16 LE),
                # data[13..14]=pool_max_notes (uint16 LE),
                # data[15]=arp_used, data[16]=seq_used
                if len(data) > 16:
                    pool_free = data[11] | (data[12] << 8)
                    pool_max = data[13] | (data[14] << 8)
                    arp_used = data[15]
                    seq_used = data[16]
                    pool_used = pool_max - pool_free
                    pool_pct = int(100 * pool_used / pool_max) if pool_max > 0 else 0
                    self.debug_log(f"HID RX INFO: pool {pool_used}/{pool_max} notes used ({pool_pct}%), "
                                   f"arp={arp_used} seq={seq_used} presets", "DATA")
                    self.update_status(f"Pool: {pool_used}/{pool_max} notes ({pool_pct}% used)")

                    # Store used count and update visible tabs
                    if self.is_step_sequencer:
                        self._user_presets_used = seq_used
                    else:
                        self._user_presets_used = arp_used
                    self._update_visible_preset_tabs()

                    # Update persistent memory label
                    mem_text = f"Memory used: {pool_used}/{pool_max} notes ({pool_pct}%)"
                    if hasattr(self, 'lbl_memory'):
                        self.lbl_memory.setText(mem_text)
                        if pool_pct >= 90:
                            self.lbl_memory.setStyleSheet("QLabel { color: red; padding: 5px; }")
                        elif pool_pct >= 75:
                            self.lbl_memory.setStyleSheet("QLabel { color: orange; padding: 5px; }")
                        else:
                            self.lbl_memory.setStyleSheet("padding: 5px;")

            elif cmd == self.ARP_CMD_GET_PRESET:
                # Parse preset data (new protocol without name field)
                # data[4] = status
                # data[5] = preset_type
                # data[6] = note_count
                # data[7-8] = pattern_length_16ths
                # data[9] = gate_length_percent
                # data[10] = timing_mode (0=straight, 1=triplet, 2=dotted)
                # data[11] = note_value (0=quarter, 1=eighth, 2=sixteenth)
                preset_type = data[5] if len(data) > 5 else 0
                note_count = data[6] if len(data) > 6 else 0
                pattern_length = ((data[7] << 8) | data[8]) if len(data) > 8 else 16
                gate_length = data[9] if len(data) > 9 else 80
                timing_mode = data[10] if len(data) > 10 else 0
                note_value = data[11] if len(data) > 11 else 2  # Default to sixteenth
                arp_mode = data[12] if len(data) > 12 else 0    # arp play mode (Single/Chord x Sync)

                self.debug_log(f"HID RX PRESET: type={preset_type} notes={note_count} "
                               f"pattern_len={pattern_length} gate={gate_length}% "
                               f"timing={timing_mode} note_val={note_value} mode={arp_mode}", "DATA")

                self.preset_data['preset_type'] = preset_type
                self.preset_data['note_count'] = note_count
                self.preset_data['pattern_length_16ths'] = pattern_length
                self.preset_data['gate_length_percent'] = gate_length
                self.preset_data['timing_mode'] = timing_mode
                self.preset_data['note_value'] = note_value
                self.preset_data['mode'] = arp_mode

                # Fetch notes from device edit buffer (GET_PRESET loads preset into buffer)
                if note_count > 0:
                    notes = self.receive_notes_chunked(note_count)
                    if notes is not None:
                        self.preset_data['steps'] = notes
                    else:
                        self.debug_log(f"HID RX PRESET: Failed to fetch notes, using empty", "WARN")
                        self.preset_data['steps'] = []
                else:
                    self.preset_data['steps'] = []

                self.apply_preset_data()
                # Restore the Mode dropdown from the per-preset stored value
                # (arp only). Block signals so this doesn't fire a live SET_MODE.
                if not self.is_step_sequencer and hasattr(self, 'combo_mode'):
                    idx = self.combo_mode.findData(arp_mode)
                    if idx >= 0:
                        self.combo_mode.blockSignals(True)
                        self.combo_mode.setCurrentIndex(idx)
                        self.combo_mode.blockSignals(False)
                self.update_status(f"Loaded preset {self.current_preset_id} ({note_count} notes)")
        else:
            error_msg = {
                1: "Error: Invalid preset or operation failed",
                0xFF: "Error: Unknown command"
            }.get(status, f"Error: Status code {status}")
            self.debug_log(f"HID RX ERROR: {cmd_name} returned status 0x{status:02X}: {error_msg}", "ERROR")
            self.update_status(error_msg, error=True)

    def load_preset(self):
        """Load preset from device via HID"""
        if hasattr(self, 'debug_console'):
            self.debug_console.mark_operation_start()
        self.debug_log(f"LOAD: Starting load for preset_id={self.current_preset_id}", "INFO")

        preset_id = self.current_preset_id
        self.update_status(f"Requesting preset {preset_id} from device...")

        # params[1] = explicit type selector (1=arp, 2=seq): arp/seq preset ID
        # ranges overlap, so the firmware cannot infer the pool from the ID alone
        if self.send_hid_command(self.ARP_CMD_GET_PRESET, [preset_id, 2 if self.is_step_sequencer else 1]):
            # Response was processed in _process_hid_response which calls apply_preset_data
            # and sets status to "Loaded preset X"
            if hasattr(self, 'debug_console'):
                self.debug_console.mark_operation_end(success=True)
        else:
            self.update_status(f"Error: Failed to load preset {preset_id}", error=True)
            if hasattr(self, 'debug_console'):
                self.debug_console.mark_operation_end(success=False)

    def save_preset(self):
        """Save preset to device via HID"""
        if hasattr(self, 'debug_console'):
            self.debug_console.mark_operation_start()

        preset_type_name = "StepSequencer" if self.is_step_sequencer else "Arpeggiator"
        self.debug_log(f"SAVE: Starting save for preset_id={self.current_preset_id} "
                       f"type={preset_type_name}", "INFO")

        # Check factory preset threshold based on preset type
        # Arpeggiator: factory 0-118, user 119-158 (pool-based)
        # Step Sequencer: factory 68-115, user 116-155 (pool-based)
        if self.is_step_sequencer:
            if self.current_preset_id < 116:
                self.debug_log(f"SAVE: BLOCKED - preset_id {self.current_preset_id} is factory (< 116)", "ERROR")
                self.update_status("Cannot save to factory preset (68-115)!", error=True)
                if hasattr(self, 'debug_console'):
                    self.debug_console.mark_operation_end(success=False)
                return
        else:
            if self.current_preset_id < 119:
                self.debug_log(f"SAVE: BLOCKED - preset_id {self.current_preset_id} is factory (< 119)", "ERROR")
                self.update_status("Cannot save to factory preset (0-118)!", error=True)
                if hasattr(self, 'debug_console'):
                    self.debug_console.mark_operation_end(success=False)
                return

        self.gather_preset_data()

        # Log the gathered preset data
        self.debug_log(f"SAVE: preset_data = {{"
                       f"preset_type={self.preset_data.get('preset_type', '?')}, "
                       f"note_count={self.preset_data.get('note_count', '?')}, "
                       f"pattern_length_16ths={self.preset_data.get('pattern_length_16ths', '?')}, "
                       f"gate_length_percent={self.preset_data.get('gate_length_percent', '?')}, "
                       f"timing_mode={self.preset_data.get('timing_mode', '?')}, "
                       f"note_value={self.preset_data.get('note_value', '?')}, "
                       f"steps_count={len(self.preset_data.get('steps', []))}"
                       f"}}", "DATA")

        # Get filtered notes for firmware (excludes empty arpeggiator notes)
        firmware_notes = self.get_firmware_notes()
        firmware_note_count = len(firmware_notes)
        self.debug_log(f"SAVE: firmware_notes={firmware_note_count} (filtered from "
                       f"{len(self.preset_data.get('steps', []))} steps)", "DATA")

        # Log first few notes for debugging
        for i, note in enumerate(firmware_notes[:5]):
            self.debug_log(f"SAVE: note[{i}] = {note}", "DATA")
        if firmware_note_count > 5:
            self.debug_log(f"SAVE: ... and {firmware_note_count - 5} more notes", "DATA")

        # Build parameter list (new protocol without name field)
        # params[0] = preset_id
        # params[1] = preset_type
        # params[2] = note_count
        # params[3] = pattern_length_16ths (high byte)
        # params[4] = pattern_length_16ths (low byte)
        # params[5] = gate_length_percent
        # params[6] = timing_mode (0=straight, 1=triplet, 2=dotted)
        # params[7] = note_value (0=quarter, 1=eighth, 2=sixteenth)
        params = [
            self.current_preset_id,
            self.preset_data.get('preset_type', 0),
            firmware_note_count,  # Use filtered count for firmware
            (self.preset_data['pattern_length_16ths'] >> 8) & 0xFF,
            self.preset_data['pattern_length_16ths'] & 0xFF,
            self.preset_data['gate_length_percent'],
            self.preset_data.get('timing_mode', 0),
            self.preset_data.get('note_value', 2),
            # params[8] = arp play mode (Single/Chord x Sync). Persisted per user
            # preset on the device (dir spare byte). Seq has no mode -> 0.
            (self.combo_mode.currentData() or 0)
                if (not self.is_step_sequencer and hasattr(self, 'combo_mode')) else 0
        ]

        self.debug_log(f"SAVE Step 1/3: Sending metadata via SET_PRESET", "INFO")

        # Step 1: Send preset metadata
        if self.send_hid_command(self.ARP_CMD_SET_PRESET, params):
            self.update_status(f"Saving preset {self.current_preset_id} (metadata sent)...")

            # Step 2: Send note data in chunks (after a short delay)
            if firmware_note_count > 0:
                self.debug_log(f"SAVE Step 2/3: Scheduling note send ({firmware_note_count} notes, 50ms delay)", "INFO")
                QTimer.singleShot(50, lambda: self._save_preset_send_notes(
                    self.current_preset_id, firmware_notes))
            else:
                self.debug_log(f"SAVE Step 2/3: No notes to send, skipping to EEPROM write", "INFO")
                # No notes to send, go straight to EEPROM save
                QTimer.singleShot(50, lambda: self._save_preset_finalize(
                    self.current_preset_id))
        else:
            self.debug_log(f"SAVE Step 1/3: FAILED - SET_PRESET command failed", "ERROR")
            self.update_status(f"Error: Failed to save preset {self.current_preset_id}", error=True)
            if hasattr(self, 'debug_console'):
                self.debug_console.mark_operation_end(success=False)

    def _save_preset_send_notes(self, preset_id, notes):
        """Helper: Send note data after metadata (step 2 of save)"""
        self.debug_log(f"SAVE Step 2/3: Sending {len(notes)} notes for preset {preset_id}", "INFO")
        self.update_status(f"Saving preset {preset_id} (sending {len(notes)} notes)...")

        if self.send_notes_chunked(preset_id, notes):
            self.debug_log(f"SAVE Step 2/3: Notes sent OK, scheduling EEPROM write (100ms delay)", "INFO")
            # Step 3: Save to EEPROM (after notes are sent)
            QTimer.singleShot(100, lambda: self._save_preset_finalize(preset_id))
        else:
            self.debug_log(f"SAVE Step 2/3: FAILED - send_notes_chunked returned False", "ERROR")
            self.update_status(f"Error: Failed to send notes for preset {preset_id}", error=True)
            if hasattr(self, 'debug_console'):
                self.debug_console.mark_operation_end(success=False)

    def _save_preset_finalize(self, preset_id):
        """Helper: Finalize preset save to EEPROM (step 3 of save)"""
        self.debug_log(f"SAVE Step 3/3: Writing preset {preset_id} to EEPROM via SAVE_PRESET", "INFO")
        self.update_status(f"Saving preset {preset_id} (writing to EEPROM)...")

        if self.send_hid_command(self.ARP_CMD_SAVE_PRESET, [preset_id]):
            self.debug_log(f"SAVE Step 3/3: EEPROM write OK - preset {preset_id} saved!", "INFO")
            self.update_status(f"Preset {preset_id} saved successfully!")
            if hasattr(self, 'debug_console'):
                self.debug_console.mark_operation_end(success=True)
            # Refresh pool info to update memory usage display
            self.send_hid_command(self.ARP_CMD_GET_INFO, [])
        else:
            self.debug_log(f"SAVE Step 3/3: FAILED - SAVE_PRESET command failed", "ERROR")
            self.update_status(f"Error: Failed to save preset {preset_id} to EEPROM", error=True)
            if hasattr(self, 'debug_console'):
                self.debug_console.mark_operation_end(success=False)

    def update_status(self, message, error=False):
        """Update status label and debug console"""
        logger.info(message)
        self.lbl_status.setText(message)
        # Use theme-based colors for status
        palette_upd = self.lbl_status.palette()
        if error:
            error_color = QColor.fromHsv(0, 200, 200)  # Red hue
            self.lbl_status.setStyleSheet(f"color: {error_color.name()}; padding: 5px;")
        else:
            info_color = palette_upd.color(QPalette.Highlight)
            self.lbl_status.setStyleSheet(f"color: {info_color.name()}; padding: 5px;")

        # Also log to debug console
        if hasattr(self, 'debug_console'):
            level = "ERROR" if error else "INFO"
            self.debug_console.log(message, level)

    def debug_log(self, message, level="DEBUG"):
        """Log a message to the debug console only (not the status bar)"""
        logger.debug(message)
        if hasattr(self, 'debug_console'):
            self.debug_console.log(message, level)

    def valid(self):
        """Check if this tab should be visible"""
        return isinstance(self.device, VialKeyboard)

    def rebuild(self, device):
        """Rebuild for new device"""
        super().rebuild(device)

        if self.valid():
            self.update_status("Arpeggiator ready")
            # Reset manual expansion on device change
            self._manually_expanded_count = 0
            # Setup widget references for the currently selected preset tab
            # This must happen before load_preset() so that step_layout, basic_grid,
            # and current_preset_id are properly initialized
            self._setup_current_preset_entry()
            # Request system info (this also updates visible tabs via _user_presets_used)
            self.send_hid_command(self.ARP_CMD_GET_INFO, [])
            # Load the currently selected preset from device
            self.load_preset()
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

        self.current_preset_id = 68  # Factory seq: 68-115, User seq: 116-155 (pool-based)
        self.is_step_sequencer = True  # This is the step sequencer tab
        self.preset_data = {
            'preset_type': 1,  # PRESET_TYPE_STEP_SEQUENCER
            'note_count': 0,
            'pattern_length_16ths': 16,
            'gate_length_percent': 80,
            'timing_mode': 0,  # 0=straight, 1=triplet, 2=dotted
            'note_value': 2,   # 0=quarter, 1=eighth, 2=sixteenth
            'steps': []  # Flat list of notes with timing
        }

        self.step_widgets = []
        self.clipboard_preset = None  # Internal clipboard for copy/paste
        self.hid_data_received.connect(self.handle_hid_response)

        # Dynamic tab tracking
        self._visible_tab_count = 1
        self._manually_expanded_count = 0
        self._user_presets_used = 0

        self.setup_ui()

    def setup_ui(self):
        """Build the UI with top tabs for User Seq 1-40 and side tabs for Basic/Advanced"""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # === Top Preset Tabs (User Seq 1-40, pool-based) ===
        self.preset_tabs = QTabWidget()

        # Create all 40 user preset entry widgets (presets 116-155 for step sequencer, pool-based)
        from protocol.feature_names import get_feature_name_manager, FEATURE_SEQ
        mgr = get_feature_name_manager()
        self.entry_widgets = []
        for i in range(40):
            preset_id = 116 + i  # User Seq presets start at 116
            entry = self._create_preset_entry(i, preset_id)
            self.entry_widgets.append(entry)

        # Initially show only 1 tab + "+" button (will expand on rebuild with device info)
        self.preset_tabs.addTab(self.entry_widgets[0]['widget'], mgr.get_name(FEATURE_SEQ, 0))
        plus_widget = QWidget()
        self.preset_tabs.addTab(plus_widget, "+")

        self.preset_tabs.currentChanged.connect(self.on_preset_tab_changed)
        main_layout.addWidget(self.preset_tabs, 1)

        # === Bottom Section: Parameters and Actions ===
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)

        # Left Container: Preset Parameters
        params_group = QGroupBox()
        params_group.setMaximumWidth(500)
        params_layout = QGridLayout()

        # Pattern Rate
        lbl_pattern_rate = QLabel("Pattern Rate:")
        self.combo_pattern_rate = ArrowComboBox()
        self.combo_pattern_rate.setMinimumWidth(150)
        self.combo_pattern_rate.setMaximumHeight(30)
        self.combo_pattern_rate.setEditable(True)
        self.combo_pattern_rate.lineEdit().setReadOnly(True)
        self.combo_pattern_rate.lineEdit().setAlignment(Qt.AlignCenter)
        self.combo_pattern_rate.addItem("1/4", 0)
        self.combo_pattern_rate.addItem("1/4T", 1)
        self.combo_pattern_rate.addItem("1/4.", 2)
        self.combo_pattern_rate.addItem("1/8", 3)
        self.combo_pattern_rate.addItem("1/8T", 4)
        self.combo_pattern_rate.addItem("1/8.", 5)
        self.combo_pattern_rate.addItem("1/16", 6)
        self.combo_pattern_rate.addItem("1/16T", 7)
        self.combo_pattern_rate.addItem("1/16.", 8)
        self.combo_pattern_rate.setCurrentIndex(6)
        self.combo_pattern_rate.setToolTip("Note subdivision and timing mode (T=triplet, .=dotted)")
        self.combo_pattern_rate.currentIndexChanged.connect(self.on_pattern_rate_changed)
        params_layout.addWidget(lbl_pattern_rate, 0, 0)
        params_layout.addWidget(self.combo_pattern_rate, 0, 1)

        # Number of steps
        lbl_num_steps = QLabel("Number of Steps:")
        self.spin_num_steps = QSpinBox()
        self.spin_num_steps.setRange(1, 128)
        self.spin_num_steps.setValue(16)  # Default 16 for step sequencer
        self.spin_num_steps.setButtonSymbols(QSpinBox.UpDownArrows)
        self.spin_num_steps.setToolTip("Number of steps in the pattern")
        self.spin_num_steps.valueChanged.connect(self.on_num_steps_changed)
        params_layout.addWidget(lbl_num_steps, 1, 0)
        params_layout.addWidget(self.spin_num_steps, 1, 1)

        # Pattern rhythm
        lbl_rhythm = QLabel("Pattern Rhythm:")
        self.lbl_pattern_length = QLabel("16/16")
        self.lbl_pattern_length.setToolTip("Total pattern rhythm (auto-calculated from steps/rate)")
        params_layout.addWidget(lbl_rhythm, 2, 0)
        params_layout.addWidget(self.lbl_pattern_length, 2, 1)

        # Gate length
        lbl_gate = QLabel("Gate Length:")
        self.spin_gate = QSpinBox()
        self.spin_gate.setRange(10, 100)
        self.spin_gate.setValue(80)
        self.spin_gate.setSuffix("%")
        self.spin_gate.setButtonSymbols(QSpinBox.UpDownArrows)
        self.spin_gate.setToolTip("Note gate length percentage")
        params_layout.addWidget(lbl_gate, 3, 0)
        params_layout.addWidget(self.spin_gate, 3, 1)

        # Default velocity
        lbl_default_velocity = QLabel("Default Velocity:")
        self.spin_default_velocity = QSpinBox()
        self.spin_default_velocity.setRange(1, 127)
        self.spin_default_velocity.setValue(127)
        self.spin_default_velocity.setButtonSymbols(QSpinBox.UpDownArrows)
        self.spin_default_velocity.setToolTip("Default velocity for new notes in basic grid")
        self.spin_default_velocity.valueChanged.connect(self.on_default_velocity_changed)
        params_layout.addWidget(lbl_default_velocity, 4, 0)
        params_layout.addWidget(self.spin_default_velocity, 4, 1)

        params_group.setLayout(params_layout)
        bottom_layout.addWidget(params_group)

        # Right Container: Actions
        actions_group = QGroupBox()
        actions_group.setMaximumWidth(500)
        actions_layout = QGridLayout()

        button_style = "QPushButton { min-height: 30px; max-height: 30px; border-radius: 5px; }"

        self.btn_load = QPushButton("Load from Device")
        self.btn_load.setStyleSheet(button_style)
        self.btn_load.clicked.connect(self.load_preset)
        self.btn_save = QPushButton("Save to Device")
        self.btn_save.setStyleSheet(button_style)
        self.btn_save.clicked.connect(self.save_preset)

        actions_layout.addWidget(self.btn_load, 0, 0, 1, 2)
        actions_layout.addWidget(self.btn_save, 1, 0, 1, 2)

        # Copy and Paste buttons
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
        actions_layout.addLayout(copy_paste_layout, 2, 0, 1, 2)

        # Reset All Steps button
        self.btn_reset_all = QPushButton("Reset All Steps")
        self.btn_reset_all.setStyleSheet(button_style)
        self.btn_reset_all.clicked.connect(self.reset_all_steps)
        actions_layout.addWidget(self.btn_reset_all, 3, 0, 1, 2)

        actions_group.setLayout(actions_layout)
        bottom_layout.addWidget(actions_group)

        bottom_layout.addStretch(1)
        main_layout.addLayout(bottom_layout)

        # Status and memory layout
        status_row = QHBoxLayout()
        self.lbl_status = QLabel("Ready. Select a preset tab to begin.")
        palette_status = self.lbl_status.palette()
        info_color = palette_status.color(QPalette.Highlight)
        self.lbl_status.setStyleSheet(f"color: {info_color.name()}; padding: 5px;")
        status_row.addWidget(self.lbl_status)
        status_row.addStretch()
        self.lbl_memory = QLabel("")
        self.lbl_memory.setStyleSheet("padding: 5px;")
        status_row.addWidget(self.lbl_memory)
        main_layout.addLayout(status_row)

        # Debug console
        self.debug_console = DebugConsole("Step Sequencer Debug Console")
        main_layout.addWidget(self.debug_console)

        self.addLayout(main_layout)

        # Initialize with first preset
        self._setup_current_preset_entry()
        self.rebuild_steps()
        self.update_pattern_length_display()

    def _create_preset_entry(self, index, preset_id):
        """Create a preset entry widget with top tabs for Basic/Advanced - uses Step Sequencer grid"""
        from protocol.feature_names import get_feature_name_manager, FEATURE_SEQ, MAX_NAME_LENGTH

        # Main container widget
        container = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header with title and rename button
        header_layout = QHBoxLayout()
        mgr = get_feature_name_manager()
        title_label = QLabel(f"<b>{mgr.get_name(FEATURE_SEQ, index)}</b>")
        title_label.setStyleSheet("font-size: 14pt;")
        header_layout.addWidget(title_label)

        btn_rename = QPushButton("Rename")
        btn_rename.setMaximumHeight(24)
        btn_rename.setMaximumWidth(60)
        btn_rename.setStyleSheet("QPushButton { font-size: 8pt; border-radius: 3px; padding: 2px 6px; }")
        btn_rename.clicked.connect(lambda checked, idx=index, lbl=title_label: self._on_rename_seq(idx, lbl))
        header_layout.addWidget(btn_rename)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Description
        desc = QLabel("Configure step sequence with absolute MIDI notes.\n"
                      "Click cells to toggle notes on/off. Right-click for velocity settings.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(desc)

        # Top tabs for Basic/Advanced
        side_tabs = QTabWidget()

        # Basic tab with step sequencer grid
        basic_grid = BasicStepSequencerGrid()
        side_tabs.addTab(basic_grid, "Basic")

        # Advanced tab with step widgets
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout()
        advanced_layout.setContentsMargins(0, 0, 0, 0)

        step_scroll = QScrollArea()
        step_scroll.setWidgetResizable(True)
        step_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        step_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        step_scroll.setMinimumHeight(300)

        step_container = QWidget()
        step_layout = QHBoxLayout()
        step_layout.setSpacing(2)
        step_layout.setDirection(QHBoxLayout.LeftToRight)
        step_container.setLayout(step_layout)
        step_scroll.setWidget(step_container)

        advanced_layout.addWidget(step_scroll)
        advanced_tab.setLayout(advanced_layout)
        side_tabs.addTab(advanced_tab, "Advanced")

        layout.addWidget(side_tabs, 1)
        container.setLayout(layout)

        return {
            'widget': container,
            'title_label': title_label,
            'basic_grid': basic_grid,
            'side_tabs': side_tabs,
            'step_scroll': step_scroll,
            'step_container': step_container,
            'step_layout': step_layout,
            'preset_id': preset_id,
            'step_widgets': []
        }

    def _update_visible_preset_tabs(self):
        """Update which preset tabs are visible - uses FEATURE_SEQ names"""
        max_tabs = len(self.entry_widgets)
        base_visible = max(1, self._user_presets_used)
        self._visible_tab_count = min(max_tabs, base_visible + self._manually_expanded_count)

        # Block signals to avoid triggering on_preset_tab_changed during rebuild
        self.preset_tabs.blockSignals(True)

        # Remove all tabs
        while self.preset_tabs.count() > 0:
            self.preset_tabs.removeTab(0)

        # Add visible preset tabs with names from feature manager
        from protocol.feature_names import get_feature_name_manager, FEATURE_SEQ
        mgr = get_feature_name_manager()
        for x in range(self._visible_tab_count):
            self.preset_tabs.addTab(self.entry_widgets[x]['widget'], mgr.get_name(FEATURE_SEQ, x))

        # Add "+" tab if not all tabs are visible
        if self._visible_tab_count < max_tabs:
            plus_widget = QWidget()
            self.preset_tabs.addTab(plus_widget, "+")

        self.preset_tabs.blockSignals(False)

    def on_preset_tab_changed(self, index):
        """Handle preset tab change - including '+' tab expansion"""
        # Check if "+" tab was clicked
        if self._visible_tab_count < len(self.entry_widgets) and index == self._visible_tab_count:
            self._manually_expanded_count += 1
            self._update_visible_preset_tabs()
            self.preset_tabs.setCurrentIndex(self._visible_tab_count - 1)
            return

        if index < 0 or index >= len(self.entry_widgets):
            return

        # Disconnect old signals
        if hasattr(self, 'basic_grid') and self.basic_grid:
            try:
                self.basic_grid.dataChanged.disconnect(self.on_basic_grid_changed)
            except:
                pass
        if hasattr(self, 'tabs') and self.tabs:
            try:
                self.tabs.currentChanged.disconnect(self.on_tab_changed)
            except:
                pass

        # Setup new preset entry
        self._setup_current_preset_entry()

        # Rebuild steps for this entry
        self.rebuild_steps()

        # Auto-load preset from device
        if self.valid():
            self.load_preset()
        else:
            from protocol.feature_names import get_feature_name_manager, FEATURE_SEQ
            self.update_status(f"{get_feature_name_manager().get_name(FEATURE_SEQ, index)} selected")

    def _on_rename_seq(self, index, title_label):
        """Open rename dialog for a seq preset"""
        from protocol.feature_names import get_feature_name_manager, FEATURE_SEQ, MAX_NAME_LENGTH
        mgr = get_feature_name_manager()
        current = mgr.get_name(FEATURE_SEQ, index)
        new_name, ok = QInputDialog.getText(
            None, "Rename Seq Preset",
            f"Name for User Seq {index + 1} (max {MAX_NAME_LENGTH} chars):",
            text=current
        )
        if ok:
            mgr.set_name(FEATURE_SEQ, index, new_name.strip()[:MAX_NAME_LENGTH])
            display = mgr.get_name(FEATURE_SEQ, index)
            title_label.setText(f"<b>{display}</b>")
            self.preset_tabs.setTabText(index, display)

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
