# SPDX-License-Identifier: GPL-2.0-or-later
"""
Velocity Tab - Real-time MIDI velocity visualization and configuration

This tab provides:
1. Layer selection to view MIDI keys on specific layers
2. Keyboard visualization with velocity values (1-127) overlaid
3. Live velocity curve editor
4. Min/max travel time calibration for velocity scaling
"""

from PyQt5.QtWidgets import (QVBoxLayout, QPushButton, QWidget, QHBoxLayout, QLabel,
                           QSizePolicy, QGroupBox, QGridLayout, QComboBox, QCheckBox,
                           QFrame, QScrollArea, QSlider, QSpinBox, QButtonGroup,
                           QRadioButton, QMessageBox, QTabWidget, QListWidget, QListWidgetItem,
                           QInputDialog, QMenu, QAction, QDialog, QDialogButtonBox,
                           QLineEdit, QApplication, QTextEdit, QStackedWidget)
from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5 import QtCore
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QFont, QLinearGradient

from widgets.combo_box import ArrowComboBox
from widgets.curve_editor import CurveEditorWidget
from widgets.range_slider import DualRangeSlider
from widgets.square_button import SquareButton
from editor.basic_editor import BasicEditor
from widgets.keyboard_widget import KeyboardWidgetSimple
from themes import Theme
from util import tr, is_hid_transfer_active
from vial_device import VialKeyboard
from protocol.keyboard_comm import (
    PARAM_SPEED_PEAK_RATIO, PARAM_AFTERTOUCH_MODE, PARAM_AFTERTOUCH_CC,
    PARAM_VIBRATO_SENSITIVITY, PARAM_VIBRATO_DECAY_TIME, PARAM_VELOCITY_AS_AT
)
from keycodes.keycodes import Keycode


# Number of factory articulation presets (single source of truth: the curve
# editor's factory name list). User preset slots start at this index.
FACTORY_COUNT = len(CurveEditorWidget.FACTORY_CURVES)


# AT/CC Mode presets — a second factory band at curve indices 69-78, added
# after the 19 factory curves (0-18) and the 50 user slots (19-68).
# 69-73 are aftertouch-flavor (gated by the "Enable Aftertouch Modes" flag);
# 74-78 are CC-flavor (gated by the "Enable CC Modes" flag). An AT/CC index
# i is CC-flavor iff i >= ATCC_START + 5.
ATCC_START = FACTORY_COUNT + 50          # 69
ATCC_COUNT = 10
ATCC_END = ATCC_START + ATCC_COUNT - 1   # 78
ATCC_NAMES = ["Vibrato Slow", "Vibrato Fast", "Rising", "Slow Rise", "Wind Chords",
              "Vibrato Slow CC", "Vibrato Fast CC", "Rising CC", "Slow Rise CC", "Wind Chords CC"]


# MIDI note keycode range (from keycodes_v6.py)
MIDI_NOTE_MIN = 0x7103  # MI_C
MIDI_NOTE_MAX = 0x714A  # MI_B_5


def is_midi_note_keycode(keycode):
    """Check if a keycode is a MIDI note (not control codes like octave/transpose)"""
    if not keycode or keycode == "KC_NO" or keycode == "KC_TRNS":
        return False

    # Handle string keycodes (most common case from keyboard.layout)
    if isinstance(keycode, str):
        # Check for MI_SPLIT_ (keysplit) and MI_SPLIT2_ (triplesplit) first
        if keycode.startswith("MI_SPLIT2_") or keycode.startswith("MI_SPLIT_"):
            if keycode.startswith("MI_SPLIT2_"):
                remaining = keycode[10:]
            else:
                remaining = keycode[9:]
            if remaining and remaining[0] in 'CDEFGAB':
                return True
            return False

        # Check for MI_ prefix (base MIDI notes like MI_C, MI_C_1, MI_Cs, MI_Cb, etc.)
        if keycode.startswith("MI_"):
            note_prefixes = ['MI_C', 'MI_D', 'MI_E', 'MI_F', 'MI_G', 'MI_A', 'MI_B']
            for prefix in note_prefixes:
                if keycode.startswith(prefix):
                    # Make sure it's not a control code like MI_CHANNEL.
                    # Accept sharp ('s'/'S'), flat ('b'), octave separator/digits.
                    # (Flats matter: MI_Db/MI_Eb/... otherwise miss the count while
                    # the firmware still treats them as MIDI note keys.)
                    remaining = keycode[len(prefix):]
                    if not remaining or remaining[0] in 'sSb_0123456789':
                        return True
            return False
        return False

    # Handle numeric keycodes. Cover all three MIDI note ranges the firmware
    # treats as KEY_TYPE_MIDI, not just base notes — a keysplit/triplesplit note
    # that arrives as a raw int (unresolved label) is still a MIDI key.
    #   base        0x7103-0x714A
    #   keysplit    0xC600-0xC647
    #   triplesplit 0xC670-0xC6B7
    return ((MIDI_NOTE_MIN <= keycode <= MIDI_NOTE_MAX) or
            (0xC600 <= keycode <= 0xC647) or
            (0xC670 <= keycode <= 0xC6B7))


def get_midi_key_type(keycode):
    """Get the type of MIDI key: 'base', 'keysplit', 'triplesplit', or None if not a MIDI note.

    NOTE: Currently unused. Firmware now handles zone-specific overrides directly.
    Kept for potential future use or debugging.
    """
    if not keycode or keycode == "KC_NO" or keycode == "KC_TRNS":
        return None

    if isinstance(keycode, str):
        # Check for MI_SPLIT2_ (triplesplit) first since it's longer
        if keycode.startswith("MI_SPLIT2_"):
            remaining = keycode[10:]
            if remaining and remaining[0] in 'CDEFGAB':
                return 'triplesplit'
            return None

        # Check for MI_SPLIT_ (keysplit)
        if keycode.startswith("MI_SPLIT_"):
            remaining = keycode[9:]
            if remaining and remaining[0] in 'CDEFGAB':
                return 'keysplit'
            return None

        # Check for MI_ prefix (base MIDI notes)
        if keycode.startswith("MI_"):
            note_prefixes = ['MI_C', 'MI_D', 'MI_E', 'MI_F', 'MI_G', 'MI_A', 'MI_B']
            for prefix in note_prefixes:
                if keycode.startswith(prefix):
                    remaining = keycode[len(prefix):]
                    if not remaining or remaining[0] in 'sS_0123456789':
                        return 'base'
            return None
        return None

    # Numeric keycodes - check ranges
    # Base MIDI notes: 0x7103 - 0x714A
    if MIDI_NOTE_MIN <= keycode <= MIDI_NOTE_MAX:
        return 'base'
    # Keysplit notes: 0xC600 - 0xC6FF range (MI_SPLIT_*)
    if 0xC600 <= keycode <= 0xC6FF:
        return 'keysplit'
    # Triplesplit notes: 0xC700 - 0xC7FF range (MI_SPLIT2_*)
    if 0xC700 <= keycode <= 0xC7FF:
        return 'triplesplit'

    return None


# Aftertouch mode byte (0-16) <-> three-control decomposition.
# Base mode pairs: Bottom=1, Reverse=3, Post=5, Vibrato=7. +1 for Sustain OFF (NS),
# +8 for Legato style. 0 = Off. The "pair" index used by the Mode combo itemData is
# 1=Bottom, 2=Reverse, 3=Post, 4=Vibrato (0=Off).
_AT_PAIR_TO_BASE = {1: 1, 2: 3, 3: 5, 4: 7}


def encode_aftertouch_byte(pair, sustain_on, legato):
    """Combine (mode pair, sustain on, legato) into the packed 0-16 byte."""
    if not pair:
        return 0
    base = _AT_PAIR_TO_BASE.get(pair, 1)
    return base + (0 if sustain_on else 1) + (8 if legato else 0)


def decode_aftertouch_byte(byte):
    """Split the packed 0-16 byte into (mode pair, sustain on, legato).

    pair: 0=Off, 1=Bottom, 2=Reverse, 3=Post, 4=Vibrato.
    """
    if not byte:
        return 0, True, False
    legato = byte > 8
    b = byte - 8 if byte > 8 else byte
    sustain_on = (b & 1) == 1
    pair = (b + 1) // 2
    return pair, sustain_on, legato


class VelocityKeyboardWidget(KeyboardWidgetSimple):
    """Extended keyboard widget that displays velocity values on keys.

    For MIDI keys, each key shows:
    - Velocity value (0-127) at the top of the key
    - Press time (ms) at the bottom of the key
    - A vertical volume bar on the right edge visualizing velocity level
    """

    def __init__(self, layout_editor):
        super().__init__(layout_editor)
        self.velocity_values = {}   # {(row, col): velocity}
        self.press_time_values = {} # {(row, col): travel_time_ms}
        self.midi_keys = set()      # Set of (row, col) that have MIDI notes
        self.show_velocity = True

    def set_velocity(self, row, col, velocity, press_time_ms=0):
        """Set velocity and press time for a specific key"""
        self.velocity_values[(row, col)] = velocity
        if press_time_ms > 0:
            self.press_time_values[(row, col)] = press_time_ms
        self.update()

    def set_midi_keys(self, midi_keys):
        """Set which keys are MIDI keys (to highlight them)"""
        self.midi_keys = set(midi_keys)
        self.update()

    def clear_velocities(self):
        """Clear all velocity and press time values"""
        self.velocity_values = {}
        self.press_time_values = {}
        self.update()

    def _velocity_color(self, velocity):
        """Get color for a velocity value (blue=low, red=high)"""
        if velocity > 0:
            ratio = velocity / 127.0
            r = int(50 + ratio * 205)
            g = int(150 - ratio * 100)
            b = int(255 - ratio * 205)
            return QColor(r, g, b)
        return QColor(100, 100, 100)

    def paintEvent(self, event):
        # Call parent paint first
        super().paintEvent(event)

        if not self.show_velocity:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Check if light theme
        light_themes = ["Light", "Lavender Dream", "Mint Fresh", "Peachy Keen", "Sky Serenity", "Rose Garden"]
        is_light = Theme.get_theme() in light_themes

        # Draw velocity overlay on keys
        for widget in self.widgets:
            if not hasattr(widget, 'desc'):
                continue

            row = widget.desc.row
            col = widget.desc.col

            scale = self.scale * 1.3
            rect_x = int((widget.x + widget.shift_x) * scale)
            rect_y = int((widget.y + widget.shift_y) * scale)
            rect_w = int(widget.w * scale)
            rect_h = int(widget.h * scale)

            is_midi = (row, col) in self.midi_keys

            if is_midi:
                velocity = self.velocity_values.get((row, col), 0)
                press_time = self.press_time_values.get((row, col), 0)
                color = self._velocity_color(velocity)

                # --- Volume bar on right side ---
                bar_width = max(4, int(rect_w * 0.10))
                bar_margin = 2
                bar_x = rect_x + rect_w - bar_width - bar_margin
                bar_y = rect_y + bar_margin
                bar_h = rect_h - 2 * bar_margin

                # Draw bar background (dark track)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(60, 60, 60, 140)))
                painter.drawRoundedRect(bar_x, bar_y, bar_width, bar_h, 2, 2)

                # Draw filled portion (bottom-up)
                if velocity > 0:
                    fill_ratio = velocity / 127.0
                    fill_h = int(bar_h * fill_ratio)
                    fill_y = bar_y + bar_h - fill_h

                    # Gradient from bottom (blue) to top (red)
                    gradient = QLinearGradient(bar_x, bar_y + bar_h, bar_x, bar_y)
                    gradient.setColorAt(0.0, QColor(50, 150, 255))
                    gradient.setColorAt(1.0, QColor(255, 50, 50))
                    painter.setBrush(QBrush(gradient))
                    painter.drawRoundedRect(bar_x, fill_y, bar_width, fill_h, 2, 2)

                # --- Velocity text at top of key ---
                text_area_w = rect_w - bar_width - bar_margin - 2
                vel_font = QFont()
                vel_font.setBold(True)
                vel_font.setPointSize(8)
                painter.setFont(vel_font)

                text_color = QColor(0, 0, 0) if is_light else QColor(255, 255, 255)
                painter.setPen(QPen(text_color))

                vel_rect = QRect(rect_x, rect_y + 2, text_area_w, int(rect_h * 0.45))
                vel_text = str(velocity) if velocity > 0 else "-"
                painter.drawText(vel_rect, Qt.AlignCenter, vel_text)

                # --- Press time text at bottom of key ---
                time_font = QFont()
                time_font.setPointSize(6)
                painter.setFont(time_font)

                time_color = QColor(80, 80, 80) if is_light else QColor(180, 180, 180)
                painter.setPen(QPen(time_color))

                time_rect = QRect(rect_x, rect_y + int(rect_h * 0.55), text_area_w, int(rect_h * 0.40))
                time_text = f"{press_time}ms" if press_time > 0 else "-"
                painter.drawText(time_rect, Qt.AlignCenter, time_text)

            else:
                # Non-MIDI keys - show grayed out indicator
                painter.setPen(QPen(QColor(120, 120, 120, 100)))
                painter.setBrush(Qt.NoBrush)
                dim_font = QFont()
                dim_font.setPointSize(7)
                painter.setFont(dim_font)
                painter.drawText(
                    rect_x, rect_y, rect_w, rect_h,
                    Qt.AlignCenter,
                    "-"
                )

        painter.end()


class VelocityTab(BasicEditor):
    """Main velocity tab for real-time velocity visualization and configuration"""

    def __init__(self, layout_editor):
        super().__init__()

        self.layout_editor = layout_editor
        self.keyboard = None
        self.current_layer = 0
        self.midi_keys = []  # List of (row, col) for MIDI keys on current layer

        # Global MIDI settings
        # Note: velocity_mode is fixed at 3 (Speed+Peak) in firmware, not configurable
        # Single-zone format: all settings at the top level (base zone only)
        self.global_midi_settings = {
            'velocity_min': 1,          # 1-127 (minimum MIDI velocity)
            'velocity_max': 127,        # 1-127 (maximum MIDI velocity)
            'aftertouch_mode': 0,       # packed byte 0-16: 0=Off; base Bottom=1/Reverse=3/Post=5/Vibrato=7, +1 Sustain OFF (NS), +8 Legato style
            'aftertouch_smoothness': 0, # 0-100% EMA smoothing (shares retrigger byte when aftertouch active)
            'aftertouch_cc': 255,       # 0-127=CC number, 255=off (poly AT only)
            'velocity_as_at': False,    # Pre-load aftertouch from velocity on note-on
            'vibrato_sensitivity': 50,  # 0-100 (percentage, 100% = 30% effective)
            'vibrato_decay_time': 10,   # 0-50 (ms per unit decay)
            'min_press_time': 200,      # 50-500ms (slow press threshold)
            'max_press_time': 20,       # 5-100ms (fast press threshold)
            'actuation_override': False, # Override per-key actuation for MIDI keys
            'actuation_point': 20,      # 0-40 = 0.0-4.0mm in 0.1mm steps
            'speed_peak_ratio': 1,      # Repurposed: Trigger Minimum in 0.1mm steps (1-35 = 0.1-3.5mm)
            'retrigger_distance': 0,    # 0=off, 5-20 = 0.5-2.0mm retrigger distance
            'at_uses_curve': False,     # Map AT/CC value through this zone's velocity curve before sending
        }

        # Polling timer
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.poll_velocity)
        self.poll_interval = 50  # 50ms = 20Hz

        # Track if tab is active
        self.is_active = False

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
            }
        """)
        help_btn.setToolTip(tooltip_text)
        help_btn.setCursor(Qt.WhatsThisCursor)
        return help_btn

    def create_zone_controls(self, zone_name, include_curve_editor=False):
        """Create a widget containing all velocity controls for a zone.
        Returns (scroll_area, controls_dict) where controls_dict has references to all control widgets.
        Layout: curve editor on left, controls on right."""

        # Create scroll area to wrap the content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        controls = {}

        # All zones use same layout: curve editor on left, controls on right
        main_layout = QHBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(5, 5, 5, 5)
        container.setLayout(main_layout)

        # Left column: title + curve editor
        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        left_col.setContentsMargins(0, 0, 0, 0)

        # Preset name header with Rename button (above the curve editor)
        controls['name_header'] = QHBoxLayout()
        controls['name_header'].setContentsMargins(0, 0, 0, 0)
        controls['name_header'].setSpacing(8)
        controls['preset_name_label'] = QLabel("Linear")
        controls['preset_name_label'].setStyleSheet("QLabel { font-size: 14px; font-weight: bold; }")
        controls['name_header'].addStretch()
        controls['name_header'].addWidget(controls['preset_name_label'])
        controls['preset_rename_btn'] = QPushButton("Rename")
        controls['preset_rename_btn'].setToolTip("Rename preset")
        controls['preset_rename_btn'].setMinimumWidth(72)
        controls['preset_rename_btn'].setMaximumHeight(26)
        controls['preset_rename_btn'].setStyleSheet("QPushButton { padding: 2px 12px; }")
        controls['preset_rename_btn'].setVisible(False)  # Hidden for factory presets
        controls['name_header'].addWidget(controls['preset_rename_btn'])
        controls['name_header'].addStretch()
        left_col.addLayout(controls['name_header'])

        # Curve editor on left side (hide preset selector)
        controls['curve_editor'] = CurveEditorWidget(show_save_button=False)
        controls['curve_editor'].setMinimumSize(250, 200)
        controls['curve_editor'].setMaximumWidth(300)
        controls['curve_editor'].setProperty('zone', zone_name)
        # Hide the preset selector widget for zone curve editors
        controls['curve_editor'].preset_selector_widget.setVisible(False)
        left_col.addWidget(controls['curve_editor'])
        left_col.addStretch()
        main_layout.addLayout(left_col)

        # Controls on right side in vertical layout
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)
        controls_widget = QWidget()
        controls_widget.setLayout(layout)
        main_layout.addWidget(controls_widget, 1)

        # Velocity Range (dual-handle slider) - title and value above slider
        vel_container = QVBoxLayout()
        vel_container.setContentsMargins(0, 0, 0, 0)
        vel_container.setSpacing(2)

        vel_header = QHBoxLayout()
        vel_header.setContentsMargins(0, 0, 0, 0)
        vel_label = QLabel(tr("VelocityTab", "Velocity Range:"))
        vel_header.addWidget(vel_label)
        controls['velocity_range_value'] = QLabel("1 - 127")
        controls['velocity_range_value'].setStyleSheet("QLabel { font-weight: bold; }")
        vel_header.addWidget(controls['velocity_range_value'])
        vel_header.addStretch()
        vel_container.addLayout(vel_header)

        controls['velocity_range_slider'] = DualRangeSlider(minimum=1, maximum=127)
        controls['velocity_range_slider'].setValues(1, 127)
        controls['velocity_range_slider'].setProperty('zone', zone_name)
        vel_container.addWidget(controls['velocity_range_slider'])
        layout.addLayout(vel_container)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Key Press ms Range (dual-handle slider) - title and value above slider
        press_container = QVBoxLayout()
        press_container.setContentsMargins(0, 0, 0, 0)
        press_container.setSpacing(2)

        press_header = QHBoxLayout()
        press_header.setContentsMargins(0, 0, 0, 0)
        press_header.addWidget(self.create_help_label(
            "Key press time range (ms):\n"
            "Fast end: Keys pressed faster get max velocity\n"
            "Slow end: Keys pressed slower get min velocity"
        ))
        press_label = QLabel(tr("VelocityTab", "Key Press range (ms):"))
        press_header.addWidget(press_label)
        controls['press_time_range_value'] = QLabel("20 - 200 ms")
        controls['press_time_range_value'].setStyleSheet("QLabel { font-weight: bold; }")
        press_header.addWidget(controls['press_time_range_value'])
        press_header.addStretch()
        press_container.addLayout(press_header)

        controls['press_time_range_slider'] = DualRangeSlider(minimum=1, maximum=500)
        controls['press_time_range_slider'].setValues(20, 200)  # fast=20ms, slow=200ms
        controls['press_time_range_slider'].setProperty('zone', zone_name)
        press_container.addWidget(controls['press_time_range_slider'])
        layout.addLayout(press_container)

        # Separator
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line2)

        # Aftertouch Mode
        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(4)
        mode_layout.addWidget(self.create_help_label(
            "Aftertouch pressure behavior:\n"
            "Off: No aftertouch\n"
            "Bottom-Out: Full travel 0-127, sustain suppresses note-on/off\n"
            "Reverse: Full travel 127-0, sustain suppresses note-on/off\n"
            "Post-Actuation: Pressure after actuation point\n"
            "Bottom-Out (NS): Full travel 0-127, no sustain suppression\n"
            "Reverse (NS): Full travel 127-0, no sustain suppression\n"
            "Vibrato: Wiggle key for aftertouch"
        ))
        mode_label = QLabel(tr("VelocityTab", "Aftertouch Mode:"))
        mode_label.setMinimumWidth(85)
        mode_layout.addWidget(mode_label)

        controls['aftertouch_mode_combo'] = ArrowComboBox()
        controls['aftertouch_mode_combo'].setMaximumHeight(25)
        controls['aftertouch_mode_combo'].setMaximumWidth(150)
        controls['aftertouch_mode_combo'].setStyleSheet("QComboBox { padding: 0px; font-size: 10px; }")
        controls['aftertouch_mode_combo'].setEditable(True)
        controls['aftertouch_mode_combo'].lineEdit().setReadOnly(True)
        controls['aftertouch_mode_combo'].lineEdit().setAlignment(Qt.AlignCenter)
        # Mode combo stores the "pair" index as itemData:
        # 0=Off, 1=Bottom, 2=Reverse, 3=Post, 4=Vibrato
        controls['aftertouch_mode_combo'].addItem("Off", 0)
        controls['aftertouch_mode_combo'].addItem("Post Actuation", 3)
        controls['aftertouch_mode_combo'].addItem("Bottom Out", 1)
        controls['aftertouch_mode_combo'].addItem("Reverse", 2)
        controls['aftertouch_mode_combo'].addItem("Vibrato", 4)
        # Per-item hover tooltips (plain-language explanations of each mode)
        _at_mode_tips = {
            0: "Off: pressing a held key harder does nothing.",
            3: "Post Actuation: aftertouch is set by how hard you struck the "
               "note, then eases off only as you let the key back up.",
            1: "Bottom Out: push a held key deeper to send more aftertouch; "
               "ease up to send less.",
            2: "Reverse: opposite of Bottom Out - a held key sends the most "
               "aftertouch near the top and less as you press deeper.",
            4: "Vibrato: wiggling a held key up and down swells the aftertouch, "
               "which fades when you hold still - like adding vibrato by hand.",
        }
        for _i in range(controls['aftertouch_mode_combo'].count()):
            _d = controls['aftertouch_mode_combo'].itemData(_i)
            if _d in _at_mode_tips:
                controls['aftertouch_mode_combo'].setItemData(_i, _at_mode_tips[_d], Qt.ToolTipRole)
        controls['aftertouch_mode_combo'].setCurrentIndex(0)
        controls['aftertouch_mode_combo'].setProperty('zone', zone_name)
        mode_layout.addWidget(controls['aftertouch_mode_combo'], 1)
        layout.addLayout(mode_layout)

        # Aftertouch Style (Chord vs Legato) - hidden when aftertouch is Off
        controls['aftertouch_style_widget'] = QWidget()
        style_layout = QHBoxLayout()
        style_layout.setContentsMargins(0, 0, 0, 0)
        style_layout.setSpacing(4)
        controls['aftertouch_style_widget'].setLayout(style_layout)
        style_layout.addWidget(self.create_help_label(
            "Aftertouch style:\n"
            "Chord: Average pressure across held keys\n"
            "Legato: Single (last-pressed) key drives aftertouch"
        ))
        style_label = QLabel(tr("VelocityTab", "AT Style:"))
        style_label.setMinimumWidth(85)
        style_layout.addWidget(style_label)

        controls['aftertouch_style_combo'] = ArrowComboBox()
        controls['aftertouch_style_combo'].setMaximumHeight(25)
        controls['aftertouch_style_combo'].setMaximumWidth(150)
        controls['aftertouch_style_combo'].setStyleSheet("QComboBox { padding: 0px; font-size: 10px; }")
        controls['aftertouch_style_combo'].setEditable(True)
        controls['aftertouch_style_combo'].lineEdit().setReadOnly(True)
        controls['aftertouch_style_combo'].lineEdit().setAlignment(Qt.AlignCenter)
        controls['aftertouch_style_combo'].addItem("Chord", 0)   # legato False
        controls['aftertouch_style_combo'].addItem("Legato", 1)  # legato True
        controls['aftertouch_style_combo'].setItemData(0,
            "Chord: all held keys share one aftertouch value - the average of "
            "how hard each key is pressed.", Qt.ToolTipRole)
        controls['aftertouch_style_combo'].setItemData(1,
            "Legato: only the most-recently-pressed key controls the aftertouch "
            "(earlier keys stop affecting it), and only one note sounds at a time.",
            Qt.ToolTipRole)
        controls['aftertouch_style_combo'].setCurrentIndex(0)
        controls['aftertouch_style_combo'].setProperty('zone', zone_name)
        style_layout.addWidget(controls['aftertouch_style_combo'], 1)
        layout.addWidget(controls['aftertouch_style_widget'])
        controls['aftertouch_style_widget'].setVisible(False)  # Hidden when aftertouch is Off

        # Sustain (On/Off) - hidden when aftertouch is Off
        controls['aftertouch_sustain_widget'] = QWidget()
        sustain_layout = QHBoxLayout()
        sustain_layout.setContentsMargins(0, 0, 0, 0)
        sustain_layout.setSpacing(4)
        controls['aftertouch_sustain_widget'].setLayout(sustain_layout)
        sustain_layout.addWidget(self.create_help_label(
            "Sustain suppression:\n"
            "On: Aftertouch suppresses note-on/off (held note)\n"
            "Off: No sustain suppression (NS)"
        ))
        sustain_label = QLabel(tr("VelocityTab", "Sustain:"))
        sustain_label.setMinimumWidth(85)
        sustain_layout.addWidget(sustain_label)

        controls['aftertouch_sustain_combo'] = ArrowComboBox()
        controls['aftertouch_sustain_combo'].setMaximumHeight(25)
        controls['aftertouch_sustain_combo'].setMaximumWidth(150)
        controls['aftertouch_sustain_combo'].setStyleSheet("QComboBox { padding: 0px; font-size: 10px; }")
        controls['aftertouch_sustain_combo'].setEditable(True)
        controls['aftertouch_sustain_combo'].lineEdit().setReadOnly(True)
        controls['aftertouch_sustain_combo'].lineEdit().setAlignment(Qt.AlignCenter)
        controls['aftertouch_sustain_combo'].addItem("On", 1)   # sustain on
        controls['aftertouch_sustain_combo'].addItem("Off", 0)  # sustain off (NS)
        controls['aftertouch_sustain_combo'].setItemData(0,
            "On: while the sustain pedal is holding a note, aftertouch stops "
            "responding.", Qt.ToolTipRole)
        controls['aftertouch_sustain_combo'].setItemData(1,
            "Off (NS): aftertouch keeps responding even while the sustain pedal "
            "holds the note.", Qt.ToolTipRole)
        controls['aftertouch_sustain_combo'].setCurrentIndex(0)
        controls['aftertouch_sustain_combo'].setProperty('zone', zone_name)
        sustain_layout.addWidget(controls['aftertouch_sustain_combo'], 1)
        layout.addWidget(controls['aftertouch_sustain_widget'])
        controls['aftertouch_sustain_widget'].setVisible(False)  # Hidden when aftertouch is Off

        # Aftertouch CC (hidden when aftertouch is Off)
        controls['aftertouch_cc_widget'] = QWidget()
        cc_layout = QHBoxLayout()
        cc_layout.setContentsMargins(0, 0, 0, 0)
        cc_layout.setSpacing(4)
        controls['aftertouch_cc_widget'].setLayout(cc_layout)

        cc_layout.addWidget(self.create_help_label("MIDI CC for aftertouch.\nOff: Standard aftertouch\nCC#: Send as CC instead"))
        cc_label = QLabel(tr("VelocityTab", "Polyphonic/CC:"))
        cc_label.setMinimumWidth(95)
        cc_layout.addWidget(cc_label)

        controls['aftertouch_cc_combo'] = ArrowComboBox()
        controls['aftertouch_cc_combo'].setMaximumHeight(25)
        controls['aftertouch_cc_combo'].setMaximumWidth(150)
        controls['aftertouch_cc_combo'].setStyleSheet("QComboBox { padding: 0px; font-size: 10px; }")
        controls['aftertouch_cc_combo'].setEditable(True)
        controls['aftertouch_cc_combo'].lineEdit().setReadOnly(True)
        controls['aftertouch_cc_combo'].lineEdit().setAlignment(Qt.AlignCenter)
        controls['aftertouch_cc_combo'].addItem("Polyphonic", 255)
        for cc in range(128):
            controls['aftertouch_cc_combo'].addItem(f"CC#{cc}", cc)
        controls['aftertouch_cc_combo'].setCurrentIndex(0)
        controls['aftertouch_cc_combo'].setProperty('zone', zone_name)
        cc_layout.addWidget(controls['aftertouch_cc_combo'], 1)

        layout.addWidget(controls['aftertouch_cc_widget'])
        controls['aftertouch_cc_widget'].setVisible(False)  # Hidden when aftertouch is Off

        # Velocity as Aftertouch checkbox (hidden when aftertouch is Off)
        controls['velocity_as_at_widget'] = QWidget()
        vat_layout = QHBoxLayout()
        vat_layout.setContentsMargins(0, 0, 0, 0)
        controls['velocity_as_at_widget'].setLayout(vat_layout)

        vat_layout.addWidget(self.create_help_label(
            "Pre-load aftertouch from note-on velocity.\n"
            "Aftertouch starts at the velocity value\n"
            "instead of 0 when a note triggers."))
        controls['velocity_as_at_checkbox'] = QCheckBox(tr("VelocityTab", "Velocity as Aftertouch"))
        controls['velocity_as_at_checkbox'].setProperty('zone', zone_name)
        vat_layout.addWidget(controls['velocity_as_at_checkbox'])

        layout.addWidget(controls['velocity_as_at_widget'])
        controls['velocity_as_at_widget'].setVisible(False)  # Hidden when aftertouch is Off

        # AT/CC Uses Velocity Curve checkbox (hidden when aftertouch is Off).
        # When on, the aftertouch/CC value is mapped through this zone's velocity
        # curve before being sent. Persisted in the preset's zone flags (bit 1).
        controls['at_uses_curve_widget'] = QWidget()
        atc_layout = QHBoxLayout()
        atc_layout.setContentsMargins(0, 0, 0, 0)
        controls['at_uses_curve_widget'].setLayout(atc_layout)

        atc_layout.addWidget(self.create_help_label(
            "Shape the aftertouch/CC output with this preset's velocity curve.\n"
            "The AT/CC value is mapped through the curve before it is sent,\n"
            "so the curve editor bends the aftertouch response too."))
        controls['at_uses_curve_check'] = QCheckBox(tr("VelocityTab", "AT/CC Uses Velocity Curve"))
        controls['at_uses_curve_check'].setProperty('zone', zone_name)
        atc_layout.addWidget(controls['at_uses_curve_check'])

        layout.addWidget(controls['at_uses_curve_widget'])
        controls['at_uses_curve_widget'].setVisible(False)  # Hidden when aftertouch is Off

        # Aftertouch Smoothness slider (shares retrigger byte, visible when aftertouch is on)
        controls['smoothness_widget'] = QWidget()
        smooth_layout = QHBoxLayout()
        smooth_layout.setContentsMargins(0, 0, 0, 0)
        controls['smoothness_widget'].setLayout(smooth_layout)

        smooth_layout.addWidget(self.create_help_label(
            "Slew rate limiter for aftertouch output.\n"
            "Fast = instant response\n"
            "Slow = very smooth (10s full sweep)"))
        smooth_label = QLabel(tr("VelocityTab", "Smoothness:"))
        smooth_label.setMinimumWidth(85)
        smooth_layout.addWidget(smooth_label)

        fast_label = QLabel("Fast")
        fast_label.setStyleSheet("QLabel { font-size: 10px; color: #888; }")
        smooth_layout.addWidget(fast_label)

        controls['smoothness_slider'] = QSlider(Qt.Horizontal)
        controls['smoothness_slider'].setMinimum(0)
        controls['smoothness_slider'].setMaximum(100)
        controls['smoothness_slider'].setValue(0)
        controls['smoothness_slider'].setProperty('zone', zone_name)
        smooth_layout.addWidget(controls['smoothness_slider'], 1)

        slow_label = QLabel("Slow")
        slow_label.setStyleSheet("QLabel { font-size: 10px; color: #888; }")
        smooth_layout.addWidget(slow_label)

        # Hidden label to keep control reference (not displayed)
        controls['smoothness_value'] = QLabel("")
        controls['smoothness_value'].setVisible(False)
        smooth_layout.addWidget(controls['smoothness_value'])

        layout.addWidget(controls['smoothness_widget'])
        controls['smoothness_widget'].setVisible(False)

        # Vibrato Sensitivity (hidden by default) - reversed: left=sensitive, right=less sensitive
        controls['vibrato_sens_widget'] = QWidget()
        sens_layout = QHBoxLayout()
        sens_layout.setContentsMargins(0, 0, 0, 0)
        controls['vibrato_sens_widget'].setLayout(sens_layout)

        sens_layout.addWidget(self.create_help_label("Wiggle sensitivity.\nLeft=Most sensitive, Right=Least sensitive"))
        sens_label = QLabel(tr("VelocityTab", "Vib Sens:"))
        sens_label.setMinimumWidth(85)
        sens_layout.addWidget(sens_label)

        sens_high_label = QLabel("Sensitive")
        sens_high_label.setStyleSheet("QLabel { font-size: 10px; color: #888; }")
        sens_layout.addWidget(sens_high_label)

        controls['vibrato_sens_slider'] = QSlider(Qt.Horizontal)
        controls['vibrato_sens_slider'].setMinimum(0)
        controls['vibrato_sens_slider'].setMaximum(100)
        controls['vibrato_sens_slider'].setValue(50)
        controls['vibrato_sens_slider'].setProperty('zone', zone_name)
        sens_layout.addWidget(controls['vibrato_sens_slider'], 1)

        sens_low_label = QLabel("Less")
        sens_low_label.setStyleSheet("QLabel { font-size: 10px; color: #888; }")
        sens_layout.addWidget(sens_low_label)

        # Hidden label to keep control reference
        controls['vibrato_sens_value'] = QLabel("")
        controls['vibrato_sens_value'].setVisible(False)
        sens_layout.addWidget(controls['vibrato_sens_value'])

        layout.addWidget(controls['vibrato_sens_widget'])
        controls['vibrato_sens_widget'].setVisible(False)

        # Vibrato Decay (hidden by default) - now percentage-based, synced with smoothness scale
        controls['vibrato_decay_widget'] = QWidget()
        decay_layout = QHBoxLayout()
        decay_layout.setContentsMargins(0, 0, 0, 0)
        controls['vibrato_decay_widget'].setLayout(decay_layout)

        decay_layout.addWidget(self.create_help_label("Vibrato decay rate.\nSynced with smoothness scale.\nFast=instant decay, Slow=gradual decay"))
        decay_label = QLabel(tr("VelocityTab", "Vib Decay:"))
        decay_label.setMinimumWidth(85)
        decay_layout.addWidget(decay_label)

        decay_fast_label = QLabel("Fast")
        decay_fast_label.setStyleSheet("QLabel { font-size: 10px; color: #888; }")
        decay_layout.addWidget(decay_fast_label)

        controls['vibrato_decay_slider'] = QSlider(Qt.Horizontal)
        controls['vibrato_decay_slider'].setMinimum(0)
        controls['vibrato_decay_slider'].setMaximum(100)
        controls['vibrato_decay_slider'].setValue(0)
        controls['vibrato_decay_slider'].setProperty('zone', zone_name)
        decay_layout.addWidget(controls['vibrato_decay_slider'], 1)

        decay_slow_label = QLabel("Slow")
        decay_slow_label.setStyleSheet("QLabel { font-size: 10px; color: #888; }")
        decay_layout.addWidget(decay_slow_label)

        # Hidden label to keep control reference
        controls['vibrato_decay_value'] = QLabel("")
        controls['vibrato_decay_value'].setVisible(False)
        decay_layout.addWidget(controls['vibrato_decay_value'])

        layout.addWidget(controls['vibrato_decay_widget'])
        controls['vibrato_decay_widget'].setVisible(False)

        # Separator before actuation override
        line3 = QFrame()
        line3.setFrameShape(QFrame.HLine)
        line3.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line3)

        # Actuation Override checkbox
        actuation_layout = QHBoxLayout()
        actuation_layout.setContentsMargins(0, 0, 0, 0)
        actuation_layout.setSpacing(4)
        actuation_layout.addWidget(self.create_help_label(
            "Override per-key actuation points for MIDI keys.\n"
            "When enabled, MIDI note-on triggers at this fixed distance\n"
            "instead of each key's individual actuation point."
        ))
        controls['actuation_override_checkbox'] = QCheckBox(tr("VelocityTab", "Override MIDI actuation"))
        controls['actuation_override_checkbox'].setChecked(False)
        controls['actuation_override_checkbox'].setProperty('zone', zone_name)
        actuation_layout.addWidget(controls['actuation_override_checkbox'])
        actuation_layout.addStretch()
        layout.addLayout(actuation_layout)

        # Actuation Point slider (hidden by default)
        controls['actuation_point_widget'] = QWidget()
        actuation_point_layout = QHBoxLayout()
        actuation_point_layout.setContentsMargins(0, 0, 0, 0)
        controls['actuation_point_widget'].setLayout(actuation_point_layout)

        actuation_point_layout.addWidget(self.create_help_label(
            "Actuation distance for MIDI note-on.\n"
            "0.0mm = very sensitive (top of travel)\n"
            "4.0mm = full press required"
        ))
        actuation_label = QLabel(tr("VelocityTab", "Actuation:"))
        actuation_label.setMinimumWidth(85)
        actuation_point_layout.addWidget(actuation_label)

        controls['actuation_point_slider'] = QSlider(Qt.Horizontal)
        controls['actuation_point_slider'].setMinimum(0)
        controls['actuation_point_slider'].setMaximum(40)  # 0-40 = 0.0-4.0mm in 0.1mm steps
        controls['actuation_point_slider'].setValue(20)  # Default 2.0mm
        controls['actuation_point_slider'].setProperty('zone', zone_name)
        actuation_point_layout.addWidget(controls['actuation_point_slider'], 1)

        controls['actuation_point_value'] = QLabel("2.0mm")
        controls['actuation_point_value'].setMinimumWidth(50)
        controls['actuation_point_value'].setStyleSheet("QLabel { font-weight: bold; }")
        actuation_point_layout.addWidget(controls['actuation_point_value'])

        layout.addWidget(controls['actuation_point_widget'])
        controls['actuation_point_widget'].setVisible(False)

        # Separator before speed/peak ratio
        line4 = QFrame()
        line4.setFrameShape(QFrame.HLine)
        line4.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line4)

        # Trigger Minimum slider (stored in 0.1mm steps, 1-35 = 0.1-3.5mm)
        # Reuses the former speed/peak byte; the speed/peak blend is now locked at 75%.
        ratio_layout = QHBoxLayout()
        ratio_layout.setContentsMargins(0, 0, 0, 0)
        ratio_layout.setSpacing(4)
        ratio_layout.addWidget(self.create_help_label(
            "Trigger Minimum:\n"
            "How deep the key must be pressed before releasing it\n"
            "triggers the note. 0.1mm = most sensitive (default);\n"
            "higher values ignore slight presses."
        ))
        ratio_label = QLabel(tr("VelocityTab", "Trigger Minimum:"))
        ratio_label.setMinimumWidth(95)
        ratio_layout.addWidget(ratio_label)

        controls['speed_peak_slider'] = QSlider(Qt.Horizontal)
        controls['speed_peak_slider'].setMinimum(1)   # 0.1mm
        controls['speed_peak_slider'].setMaximum(35)  # 3.5mm
        controls['speed_peak_slider'].setValue(1)     # Default 0.1mm
        controls['speed_peak_slider'].setProperty('zone', zone_name)
        ratio_layout.addWidget(controls['speed_peak_slider'], 1)

        controls['speed_peak_value'] = QLabel("0.1mm")
        controls['speed_peak_value'].setMinimumWidth(45)
        controls['speed_peak_value'].setStyleSheet("QLabel { font-weight: bold; }")
        ratio_layout.addWidget(controls['speed_peak_value'])
        layout.addLayout(ratio_layout)

        # Retrigger checkbox
        retrigger_layout = QHBoxLayout()
        retrigger_layout.setContentsMargins(0, 0, 0, 0)
        retrigger_layout.setSpacing(4)
        retrigger_layout.addWidget(self.create_help_label(
            "Enable note retrigger without full release.\n"
            "Release to the retrigger point and press again\n"
            "to send a new note-on. Velocity is capped based\n"
            "on how far the key was released."
        ))
        controls['retrigger_checkbox'] = QCheckBox(tr("VelocityTab", "Enable Retrigger"))
        controls['retrigger_checkbox'].setChecked(False)
        controls['retrigger_checkbox'].setProperty('zone', zone_name)
        retrigger_layout.addWidget(controls['retrigger_checkbox'])

        controls['retrigger_disabled_label'] = QLabel("(disabled when aftertouch is enabled)")
        controls['retrigger_disabled_label'].setStyleSheet("QLabel { color: #888; font-style: italic; font-size: 10px; }")
        controls['retrigger_disabled_label'].setVisible(False)
        retrigger_layout.addWidget(controls['retrigger_disabled_label'])

        retrigger_layout.addStretch()
        layout.addLayout(retrigger_layout)

        # Retrigger Distance slider (hidden by default)
        controls['retrigger_widget'] = QWidget()
        retrigger_dist_layout = QHBoxLayout()
        retrigger_dist_layout.setContentsMargins(0, 0, 0, 0)
        controls['retrigger_widget'].setLayout(retrigger_dist_layout)

        retrigger_dist_layout.addWidget(self.create_help_label(
            "Retrigger distance from actuation point.\n"
            "0.5mm = sensitive retrigger\n"
            "2.0mm = requires more release"
        ))
        retrigger_dist_label = QLabel(tr("VelocityTab", "Retrigger:"))
        retrigger_dist_label.setMinimumWidth(85)
        retrigger_dist_layout.addWidget(retrigger_dist_label)

        controls['retrigger_slider'] = QSlider(Qt.Horizontal)
        controls['retrigger_slider'].setMinimum(5)   # 0.5mm minimum
        controls['retrigger_slider'].setMaximum(20)  # 2.0mm maximum
        controls['retrigger_slider'].setValue(10)    # Default 1.0mm
        controls['retrigger_slider'].setProperty('zone', zone_name)
        retrigger_dist_layout.addWidget(controls['retrigger_slider'], 1)

        controls['retrigger_value'] = QLabel("1.0mm")
        controls['retrigger_value'].setMinimumWidth(50)
        controls['retrigger_value'].setStyleSheet("QLabel { font-weight: bold; }")
        retrigger_dist_layout.addWidget(controls['retrigger_value'])

        layout.addWidget(controls['retrigger_widget'])
        controls['retrigger_widget'].setVisible(False)

        layout.addStretch()

        # Set container in scroll area and return
        scroll_area.setWidget(container)
        return scroll_area, controls

    def connect_zone_controls(self, controls, zone_name):
        """Connect signals for zone controls. Zone name is 'base'."""
        # Get the settings dict for this zone
        def get_settings():
            return self.global_midi_settings

        def set_setting(key, value):
            self.global_midi_settings[key] = value

        # Velocity range (dual-handle slider)
        def on_velocity_range_changed(low, high):
            controls['velocity_range_value'].setText(f"{low} - {high}")
            set_setting('velocity_min', low)
            set_setting('velocity_max', high)

        controls['velocity_range_slider'].range_changed.connect(on_velocity_range_changed)

        # Press time range (dual-handle slider)
        def on_press_time_range_changed(fast, slow):
            controls['press_time_range_value'].setText(f"{fast} - {slow} ms")
            set_setting('max_press_time', fast)  # fast press = max velocity
            set_setting('min_press_time', slow)  # slow press = min velocity

        controls['press_time_range_slider'].range_changed.connect(on_press_time_range_changed)

        # Aftertouch mode / style / sustain -> packed byte (0-16)
        def compute_aftertouch_byte():
            pair = controls['aftertouch_mode_combo'].currentData() or 0
            sustain_on = (controls['aftertouch_sustain_combo'].currentData() == 1)
            legato = (controls['aftertouch_style_combo'].currentData() == 1)
            return encode_aftertouch_byte(pair, sustain_on, legato)

        def on_aftertouch_mode_changed(index):
            pair = controls['aftertouch_mode_combo'].currentData() or 0
            is_vibrato = (pair == 4)
            is_off = (pair == 0)
            controls['vibrato_sens_widget'].setVisible(is_vibrato)
            controls['vibrato_decay_widget'].setVisible(is_vibrato)
            controls['aftertouch_cc_widget'].setVisible(not is_off)
            controls['velocity_as_at_widget'].setVisible(not is_off)
            controls['at_uses_curve_widget'].setVisible(not is_off)
            # Post Actuation (pair 3) locks "Velocity as Aftertouch" ON: the note
            # velocity IS the CC ceiling, so it's intrinsic and can't be toggled off.
            is_post = (pair == 3)
            vat = controls['velocity_as_at_checkbox']
            vat.blockSignals(True)
            if is_post:
                vat.setChecked(True)
                vat.setEnabled(False)
            else:
                vat.setChecked(bool(get_settings().get('velocity_as_at', False)))
                vat.setEnabled(True)
            vat.blockSignals(False)
            # Style/Sustain only apply when aftertouch is enabled
            controls['aftertouch_style_widget'].setVisible(not is_off)
            controls['aftertouch_sustain_widget'].setVisible(not is_off)
            # Smoothness replaces retrigger when aftertouch is active
            controls['smoothness_widget'].setVisible(not is_off)
            # Disable retrigger when aftertouch is enabled
            controls['retrigger_checkbox'].setEnabled(is_off)
            controls['retrigger_disabled_label'].setVisible(not is_off)
            if not is_off:
                controls['retrigger_checkbox'].setChecked(False)
                controls['retrigger_widget'].setVisible(False)
            set_setting('aftertouch_mode', compute_aftertouch_byte())

        def on_aftertouch_style_or_sustain_changed(index):
            set_setting('aftertouch_mode', compute_aftertouch_byte())

        controls['aftertouch_mode_combo'].currentIndexChanged.connect(on_aftertouch_mode_changed)
        controls['aftertouch_style_combo'].currentIndexChanged.connect(on_aftertouch_style_or_sustain_changed)
        controls['aftertouch_sustain_combo'].currentIndexChanged.connect(on_aftertouch_style_or_sustain_changed)

        # Aftertouch CC
        def on_aftertouch_cc_changed(index):
            cc = controls['aftertouch_cc_combo'].currentData()
            set_setting('aftertouch_cc', cc)

        controls['aftertouch_cc_combo'].currentIndexChanged.connect(on_aftertouch_cc_changed)

        # Velocity as Aftertouch checkbox
        def on_velocity_as_at_changed(state):
            enabled = (state == Qt.Checked)
            set_setting('velocity_as_at', enabled)
            if self.keyboard:
                self.keyboard.set_keyboard_param_single(PARAM_VELOCITY_AS_AT, 1 if enabled else 0)

        controls['velocity_as_at_checkbox'].stateChanged.connect(on_velocity_as_at_changed)

        # AT/CC Uses Velocity Curve checkbox (persisted in preset zone flags bit 1)
        def on_at_uses_curve_changed(state):
            set_setting('at_uses_curve', state == Qt.Checked)

        controls['at_uses_curve_check'].stateChanged.connect(on_at_uses_curve_changed)

        # Aftertouch smoothness (0-100%, shares retrigger byte in protocol)
        def on_smoothness_changed(value):
            set_setting('aftertouch_smoothness', value)

        controls['smoothness_slider'].valueChanged.connect(on_smoothness_changed)

        # Vibrato sensitivity (slider is reversed: 0=most sensitive, 100=least sensitive)
        # Firmware value = 100 - slider_value
        def on_vibrato_sens_changed(value):
            firmware_value = 100 - value
            set_setting('vibrato_sensitivity', firmware_value)

        # Vibrato decay (percentage-based, synced with smoothness scale)
        # Convert percentage to ms-per-unit: decay_ms = (pct * 100) / 127
        # At 100%: 10000ms / 127 = ~79ms per unit (same as smoothness full sweep)
        def on_vibrato_decay_changed(value):
            if value > 0:
                decay_ms = max(1, (value * 100) // 127)
            else:
                decay_ms = 0
            set_setting('vibrato_decay_time', decay_ms)

        controls['vibrato_sens_slider'].valueChanged.connect(on_vibrato_sens_changed)
        controls['vibrato_decay_slider'].valueChanged.connect(on_vibrato_decay_changed)

        # Actuation override
        def on_actuation_override_changed(state):
            enabled = (state == Qt.Checked)
            controls['actuation_point_widget'].setVisible(enabled)
            set_setting('actuation_override', enabled)

        controls['actuation_override_checkbox'].stateChanged.connect(on_actuation_override_changed)

        # Actuation point
        def on_actuation_point_changed(value):
            mm_value = value / 10.0
            controls['actuation_point_value'].setText(f"{mm_value:.1f}mm")
            set_setting('actuation_point', value)

        controls['actuation_point_slider'].valueChanged.connect(on_actuation_point_changed)

        # Trigger Minimum (stored as 0.1mm steps in the former speed/peak byte)
        def on_speed_peak_changed(value):
            controls['speed_peak_value'].setText(f"{value // 10}.{value % 10}mm")
            set_setting('speed_peak_ratio', value)
            # Send to firmware in real-time (base zone only - zones share the same param)
            if zone_name == 'base' and self.keyboard:
                self.keyboard.set_keyboard_param_single(PARAM_SPEED_PEAK_RATIO, value)

        controls['speed_peak_slider'].valueChanged.connect(on_speed_peak_changed)

        # Retrigger
        def on_retrigger_changed(state):
            enabled = (state == Qt.Checked)
            controls['retrigger_widget'].setVisible(enabled)
            if enabled:
                set_setting('retrigger_distance', controls['retrigger_slider'].value())
            else:
                set_setting('retrigger_distance', 0)

        controls['retrigger_checkbox'].stateChanged.connect(on_retrigger_changed)

        def on_retrigger_distance_changed(value):
            mm_value = value / 10.0
            controls['retrigger_value'].setText(f"{mm_value:.1f}mm")
            set_setting('retrigger_distance', value)

        controls['retrigger_slider'].valueChanged.connect(on_retrigger_distance_changed)

        # Curve editor for zone tabs
        if 'curve_editor' in controls:
            def on_curve_changed():
                points = controls['curve_editor'].get_points()
                set_setting('points', points)
            controls['curve_editor'].curve_changed.connect(on_curve_changed)

    def setup_ui(self):
        # Create scroll area for the main content - stretches to fill window
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # Show horizontal scroll when needed
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        main_widget = QWidget()
        main_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_widget.setLayout(main_layout)

        scroll.setWidget(main_widget)
        self.addWidget(scroll, stretch=1)  # Allow scroll area to stretch

        # Title
        title_label = QLabel(tr("VelocityTab", "Velocity Monitor"))
        title_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(tr("VelocityTab",
            "Monitor real-time MIDI velocity values for keys.\n"
            "Configure articulation, aftertouch, and press timing."))
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; font-size: 9pt;")
        desc_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(desc_label)

        # Layer indicator — the velocity tab auto-follows the keyboard's
        # currently-active layer (polled from the firmware); there is no manual
        # layer switching here.
        layer_chooser_layout = QHBoxLayout()
        layer_chooser_layout.setSpacing(4)
        layer_chooser_layout.setContentsMargins(0, 0, 0, 0)

        layer_chooser_layout.addStretch()
        self.layer_status_label = QLabel(tr("VelocityTab", "Active Layer: 1  (auto-follows keyboard)"))
        self.layer_status_label.setStyleSheet("font-weight: bold; font-size: 10pt;")
        layer_chooser_layout.addWidget(self.layer_status_label)
        layer_chooser_layout.addStretch()
        main_layout.addLayout(layer_chooser_layout)

        # Kept for back-compat with the helper methods (no buttons in auto mode)
        self.layer_buttons = []

        # MIDI keys info label
        self.midi_info_label = QLabel(tr("VelocityTab", "MIDI Keys: 0"))
        self.midi_info_label.setStyleSheet("color: #888; font-size: 10pt;")
        self.midi_info_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(self.midi_info_label)

        # Keyboard widget
        self.keyboard_widget = VelocityKeyboardWidget(self.layout_editor)
        self.keyboard_widget.setMinimumWidth(800)
        self.keyboard_widget.setMinimumHeight(250)
        main_layout.addWidget(self.keyboard_widget, alignment=Qt.AlignCenter)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line)

        # Bottom section: Combined Velocity Preset configuration (centered)
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)
        bottom_layout.addStretch()  # Left stretch to center the group

        # =====================================================================
        # LEFT SIDE: Scrollable Preset List
        # =====================================================================
        preset_list_group = QGroupBox(tr("VelocityTab", "Presets"))
        preset_list_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        preset_list_group.setMinimumWidth(200)
        preset_list_group.setMaximumWidth(280)
        preset_list_group.setMinimumHeight(400)
        preset_list_group.setMaximumHeight(600)
        preset_list_layout = QVBoxLayout()
        preset_list_layout.setSpacing(5)
        preset_list_group.setLayout(preset_list_layout)

        # Scrollable preset list
        self.preset_list_widget = QListWidget()
        self.preset_list_widget.setMinimumHeight(300)

        # Factory presets
        factory_curves = ["Softest", "Soft", "Linear", "Hard", "Hardest", "Sensitive Soft", "Sensitive", "Sensitive Hard", "Fixed Vol", "Drums Easy", "Drums Soft", "Drums Linear", "Drums Hard", "Drums Sensitive", "Ultra Sensitive", "Fixed Sensitive", "Two Toned", "Reverse", "Random Highlights"]
        for i, name in enumerate(factory_curves):
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, i)  # Store curve index
            self.preset_list_widget.addItem(item)

        # Separator (hidden until user presets are configured)
        self.user_presets_separator = QListWidgetItem("─── User Presets ───")
        self.user_presets_separator.setData(Qt.UserRole, -2)  # Special value for separator
        self.user_presets_separator.setFlags(Qt.NoItemFlags)  # Non-selectable
        self.user_presets_separator.setHidden(True)
        self.preset_list_widget.addItem(self.user_presets_separator)

        # User presets (indices FACTORY_COUNT..FACTORY_COUNT+49) - initially all hidden, shown when configured
        self.user_curve_names = ["User {}".format(i + 1) for i in range(50)]
        self.user_preset_configured = [False] * 50
        for i, name in enumerate(self.user_curve_names):
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, FACTORY_COUNT + i)  # Store curve index
            self.preset_list_widget.addItem(item)
            item.setHidden(True)  # Hidden until we know it's configured

        # AT/CC Mode presets (indices 69-78) — a second factory band gated by
        # two global enable flags. Default disabled → rows shown greyed/locked.
        # Clicking a locked row shows an "Enable … Modes" placeholder instead
        # of the settings panel (see on_preset_list_clicked).
        self.atcc_at_enabled = False
        self.atcc_cc_enabled = False
        # atcc_row_items stays ordered by curve index (69..78) across BOTH
        # sections so the positional lookups in update_atcc_rows_enabled line up.
        self.atcc_row_items = []
        # --- AT Modes section (curve indices 69-73, ATCC_NAMES[0..4]) ---
        self.atcc_at_separator = QListWidgetItem("─── AT Modes ───")
        self.atcc_at_separator.setData(Qt.UserRole, -3)  # AT separator (non-selectable)
        self.atcc_at_separator.setFlags(Qt.NoItemFlags)
        self.preset_list_widget.addItem(self.atcc_at_separator)
        for i in range(5):
            item = QListWidgetItem(ATCC_NAMES[i])
            item.setData(Qt.UserRole, ATCC_START + i)  # curve index 69-73
            self.preset_list_widget.addItem(item)
            self.atcc_row_items.append(item)
        # --- CC Modes section (curve indices 74-78, ATCC_NAMES[5..9]) ---
        self.atcc_cc_separator = QListWidgetItem("─── CC Modes ───")
        self.atcc_cc_separator.setData(Qt.UserRole, -4)  # CC separator (non-selectable)
        self.atcc_cc_separator.setFlags(Qt.NoItemFlags)
        self.preset_list_widget.addItem(self.atcc_cc_separator)
        for i in range(5, ATCC_COUNT):
            item = QListWidgetItem(ATCC_NAMES[i])
            item.setData(Qt.UserRole, ATCC_START + i)  # curve index 74-78
            self.preset_list_widget.addItem(item)
            self.atcc_row_items.append(item)
        self.update_atcc_rows_enabled()

        # Select Linear by default
        self.preset_list_widget.setCurrentRow(2)
        self.preset_list_widget.itemClicked.connect(self.on_preset_list_clicked)

        # Enable right-click context menu for renaming user presets
        self.preset_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.preset_list_widget.customContextMenuRequested.connect(self.on_preset_context_menu)

        preset_list_layout.addWidget(self.preset_list_widget)
        bottom_layout.addWidget(preset_list_group)

        # =====================================================================
        # RIGHT SIDE: Preset Settings Group (zone controls with embedded curve editor)
        # =====================================================================
        preset_group = QGroupBox(tr("VelocityTab", "Preset Settings"))
        preset_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        preset_group.setMinimumWidth(700)
        preset_group.setMaximumWidth(1100)
        preset_group.setMinimumHeight(400)
        preset_group.setMaximumHeight(600)
        preset_main_layout = QVBoxLayout()
        preset_main_layout.setSpacing(6)
        preset_group.setLayout(preset_main_layout)

        # Store zone controls for easy access
        self.zone_controls = {}

        # Create base zone controls with curve editor inside (directly in preset group)
        base_widget, base_controls = self.create_zone_controls('base', include_curve_editor=True)
        self.zone_controls['base'] = base_controls
        self.connect_zone_controls(base_controls, 'base')
        # Wrap the settings panel in a stack so a locked AT/CC preset can swap
        # in an "Enable … Modes" placeholder (page 1) in place of the panel
        # (page 0). Switched in on_preset_list_clicked / load_velocity_curve.
        self.preset_settings_stack = QStackedWidget()
        self.preset_settings_stack.addWidget(base_widget)  # page 0 = settings panel
        # Page 1: locked-band placeholder + an actionable "Enable … Modes"
        # checkbox. Ticking it writes the corresponding global enable flag
        # (bit5 = AT, bit6 = CC) to the device (persisted to slot 0), unlocks the
        # band locally, and returns to the settings panel. The label/checkbox
        # text + governed band are set whenever page 1 is shown (see
        # _show_atcc_locked_page); the tick is handled by _on_atcc_enable_toggled.
        atcc_page = QWidget()
        atcc_page_layout = QVBoxLayout()
        atcc_page_layout.setAlignment(Qt.AlignCenter)
        atcc_page.setLayout(atcc_page_layout)
        self.atcc_placeholder_label = QLabel("")
        self.atcc_placeholder_label.setAlignment(Qt.AlignCenter)
        self.atcc_placeholder_label.setWordWrap(True)
        self.atcc_placeholder_label.setStyleSheet(
            "QLabel { font-size: 16px; font-weight: bold; color: #888; }")
        atcc_page_layout.addWidget(self.atcc_placeholder_label)
        # True when the checkbox currently governs the CC band (bit6); False for
        # the AT band (bit5). Set by _show_atcc_locked_page.
        self._atcc_check_is_cc = False
        self.atcc_enable_check = QCheckBox("Enable Aftertouch Modes")
        self.atcc_enable_check.setStyleSheet("QCheckBox { font-size: 13px; }")
        self.atcc_enable_check.stateChanged.connect(self._on_atcc_enable_toggled)
        atcc_page_layout.addWidget(self.atcc_enable_check, alignment=Qt.AlignCenter)
        self.preset_settings_stack.addWidget(atcc_page)  # page 1
        preset_main_layout.addWidget(self.preset_settings_stack, 1)

        # Store reference to the base curve editor
        self.curve_editor = base_controls['curve_editor']
        self.curve_editor.curve_changed.connect(self.on_curve_changed)
        self.curve_editor.user_curve_selected.connect(self.on_user_curve_selected)

        # Store references to preset name/rename controls
        self.preset_name_label = base_controls['preset_name_label']
        self.preset_rename_btn = base_controls['preset_rename_btn']
        self.preset_rename_btn.clicked.connect(self.on_preset_rename_clicked)

        # Create references to base zone controls for backward compatibility
        self.velocity_range_slider = base_controls['velocity_range_slider']
        self.velocity_range_value = base_controls['velocity_range_value']
        self.press_time_range_slider = base_controls['press_time_range_slider']
        self.press_time_range_value = base_controls['press_time_range_value']
        self.aftertouch_mode_combo = base_controls['aftertouch_mode_combo']
        self.aftertouch_style_combo = base_controls['aftertouch_style_combo']
        self.aftertouch_style_widget = base_controls['aftertouch_style_widget']
        self.aftertouch_sustain_combo = base_controls['aftertouch_sustain_combo']
        self.aftertouch_sustain_widget = base_controls['aftertouch_sustain_widget']
        self.aftertouch_cc_combo = base_controls['aftertouch_cc_combo']
        self.aftertouch_cc_widget = base_controls['aftertouch_cc_widget']
        self.velocity_as_at_widget = base_controls['velocity_as_at_widget']
        self.velocity_as_at_checkbox = base_controls['velocity_as_at_checkbox']
        self.at_uses_curve_widget = base_controls['at_uses_curve_widget']
        self.at_uses_curve_check = base_controls['at_uses_curve_check']
        self.vibrato_sens_widget = base_controls['vibrato_sens_widget']
        self.vibrato_sens_slider = base_controls['vibrato_sens_slider']
        self.vibrato_sens_value = base_controls['vibrato_sens_value']
        self.vibrato_decay_widget = base_controls['vibrato_decay_widget']
        self.vibrato_decay_slider = base_controls['vibrato_decay_slider']
        self.vibrato_decay_value = base_controls['vibrato_decay_value']
        self.smoothness_widget = base_controls['smoothness_widget']
        self.smoothness_slider = base_controls['smoothness_slider']
        self.smoothness_value = base_controls['smoothness_value']
        self.actuation_override_checkbox = base_controls['actuation_override_checkbox']
        self.actuation_point_widget = base_controls['actuation_point_widget']
        self.actuation_point_slider = base_controls['actuation_point_slider']
        self.actuation_point_value = base_controls['actuation_point_value']
        self.speed_peak_slider = base_controls['speed_peak_slider']
        self.speed_peak_value = base_controls['speed_peak_value']
        self.retrigger_checkbox = base_controls['retrigger_checkbox']
        self.retrigger_disabled_label = base_controls['retrigger_disabled_label']
        self.retrigger_widget = base_controls['retrigger_widget']
        self.retrigger_slider = base_controls['retrigger_slider']
        self.retrigger_value = base_controls['retrigger_value']

        # Buttons row (New + Save + Save As)
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(6)

        self.new_preset_btn = QPushButton(tr("VelocityTab", "New"))
        self.new_preset_btn.setMinimumHeight(35)
        self.new_preset_btn.setToolTip("Create a new user preset with default (Linear) settings")
        self.new_preset_btn.clicked.connect(self.on_new_linear_preset)
        buttons_layout.addWidget(self.new_preset_btn)

        self.save_preset_btn = QPushButton(tr("VelocityTab", "Save"))
        self.save_preset_btn.setMinimumHeight(35)
        self.save_preset_btn.setToolTip("Overwrite the currently selected user preset")
        self.save_preset_btn.clicked.connect(self.on_save_preset_overwrite)
        buttons_layout.addWidget(self.save_preset_btn)

        self.save_as_btn = QPushButton(tr("VelocityTab", "Save As..."))
        self.save_as_btn.setMinimumHeight(35)
        self.save_as_btn.setToolTip("Save to an existing or new user preset slot")
        self.save_as_btn.clicked.connect(self.on_save_as_dialog)
        buttons_layout.addWidget(self.save_as_btn)

        self.export_btn = QPushButton(tr("VelocityTab", "Export..."))
        self.export_btn.setMinimumHeight(35)
        self.export_btn.setToolTip("Copy this articulation's exact settings as text "
                                   "(shareable / for defining factory presets)")
        self.export_btn.clicked.connect(self.on_export_articulation)
        buttons_layout.addWidget(self.export_btn)

        preset_main_layout.addLayout(buttons_layout)

        bottom_layout.addWidget(preset_group)
        bottom_layout.addStretch()  # Right stretch to center the group

        main_layout.addLayout(bottom_layout)
        main_layout.addStretch()

    def valid(self):
        """This tab is always valid for VialKeyboard devices"""
        return isinstance(self.device, VialKeyboard)

    def rebuild(self, device):
        super().rebuild(device)
        if not self.valid():
            return

        self.keyboard = device.keyboard

        try:
            # Rebuild keyboard widget
            self.keyboard_widget.set_keys(self.keyboard.keys, self.keyboard.encoders)
            # Rebuild layer chooser buttons
            self.rebuild_layer_buttons()
            # Load velocity curve from keyboard
            self.load_velocity_curve()
            # Load advanced settings from keyboard
            self.load_advanced_settings()
            # Scan for MIDI keys on current layer
            self.scan_midi_keys()
        except Exception as e:
            print(f"VelocityTab rebuild error: {e}")

    def rebuild_layer_buttons(self):
        """Auto-follow mode: there are no manual layer buttons. Sync the view to
        the keyboard's active layer immediately so the tab opens on the layer the
        keyboard is physically on."""
        self.layer_buttons = []
        if not self.keyboard:
            return
        detected = self._read_active_layer()
        self.current_layer = detected if detected is not None else 0
        self.refresh_layer_buttons()

    def refresh_layer_buttons(self):
        """Update the active-layer indicator label."""
        if hasattr(self, 'layer_status_label'):
            self.layer_status_label.setText(
                tr("VelocityTab", "Active Layer: {}  (auto-follows keyboard)").format(self.current_layer + 1))

    def _read_active_layer(self):
        """Query the keyboard's current active layer over HID (None if the
        firmware doesn't support it or on comms error)."""
        if not self.keyboard:
            return None
        try:
            return self.keyboard.get_active_layer()
        except Exception:
            return None

    def _follow_active_layer(self):
        """Poll the hardware's active layer and switch the view if it changed."""
        detected = self._read_active_layer()
        if detected is None:
            # Old firmware (no layer query) — disable polling after a few misses.
            self._layer_follow_fails = getattr(self, '_layer_follow_fails', 0) + 1
            if self._layer_follow_fails >= 3:
                self._layer_follow_supported = False
            return
        self._layer_follow_fails = 0
        if detected == self.current_layer:
            return
        self.current_layer = detected
        self.refresh_layer_buttons()
        self.keyboard_widget.clear_velocities()
        self.scan_midi_keys()

    def activate(self):
        """Called when tab becomes active"""
        self.is_active = True
        if self.keyboard:
            self.scan_midi_keys()
            self.poll_timer.start(self.poll_interval)

    def deactivate(self):
        """Called when tab becomes inactive"""
        self.is_active = False
        self.poll_timer.stop()
        self.keyboard_widget.clear_velocities()

    def set_layer(self, layer):
        """Set the current layer (can be called externally)"""
        self.current_layer = layer
        self.refresh_layer_buttons()
        self.keyboard_widget.clear_velocities()
        self.scan_midi_keys()

    def scan_midi_keys(self):
        """Scan current layer for MIDI note keycodes"""
        if not self.keyboard:
            return

        self.midi_keys = []

        # Iterate through all keys on the current layer
        for (layer, row, col), keycode in self.keyboard.layout.items():
            if layer != self.current_layer:
                continue

            # Check if this is a MIDI note keycode
            if is_midi_note_keycode(keycode):
                self.midi_keys.append((row, col))

        # Update keyboard widget
        self.keyboard_widget.set_midi_keys(self.midi_keys)

        # Update info label
        self.midi_info_label.setText(
            tr("VelocityTab", f"MIDI Keys on Layer {self.current_layer + 1}: {len(self.midi_keys)}")
        )

    def poll_velocity(self):
        """Poll velocity and press time values from keyboard"""
        # A loop transfer owns the HID handle; skip this tick so we don't steal
        # its packets (or read garbage). The poll timer keeps running. (H3)
        if is_hid_transfer_active():
            return
        if not self.keyboard or not self.is_active:
            return

        # Auto-follow the keyboard's active layer (~5 Hz, the poll runs at 20 Hz).
        # Skipped if the firmware doesn't support the query (old firmware), so we
        # don't stall on every poll waiting for a reply that never comes.
        if getattr(self, '_layer_follow_supported', True):
            self._layer_poll_counter = getattr(self, '_layer_poll_counter', 0) + 1
            if self._layer_poll_counter >= 4:
                self._layer_poll_counter = 0
                self._follow_active_layer()

        if not self.midi_keys:
            return

        # Poll in batches of 6 (firmware limit)
        for i in range(0, len(self.midi_keys), 6):
            batch = self.midi_keys[i:i+6]
            result = self.keyboard.velocity_matrix_poll(batch)

            if result:
                for (row, col), data in result.items():
                    velocity = data.get('velocity', 0)
                    press_time = data.get('travel_time_ms', 0)
                    self.keyboard_widget.set_velocity(row, col, velocity, press_time)

    def load_advanced_settings(self):
        """Load advanced settings from keyboard (same approach as keymap_editor)"""
        if not self.keyboard:
            return

        try:
            # Get layer actuation settings (velocity_mode is fixed at 3 in firmware)
            result = self.keyboard.get_layer_actuation(0)  # Get from layer 0 for global settings
            if result:
                # Update global_midi_settings from device
                # Note: velocity_mode is fixed at Speed+Peak (3) and not configurable
                aftertouch_mode = result.get('aftertouch_mode', 0)
                self.global_midi_settings['aftertouch_mode'] = aftertouch_mode
                # Note: aftertouch_smoothness comes from zone preset (retrigger byte), not layer actuation
                aftertouch_cc = result.get('aftertouch_cc', 255)
                self.global_midi_settings['aftertouch_cc'] = aftertouch_cc
                vibrato_sens = result.get('vibrato_sensitivity', 50)
                self.global_midi_settings['vibrato_sensitivity'] = vibrato_sens
                vibrato_decay = result.get('vibrato_decay_time', 10)
                self.global_midi_settings['vibrato_decay_time'] = vibrato_decay
                # velocity_as_at is a global device setting; the firmware now
                # reports it in the layer-actuation response. Read it back so the
                # "Velocity as Aftertouch" checkbox reflects the saved device state
                # (older firmware omits it -> keep whatever we had).
                if 'velocity_as_at' in result:
                    self.global_midi_settings['velocity_as_at'] = result['velocity_as_at']

                # Update UI from settings
                self.load_advanced_ui_from_settings()

            # NOTE: velocity_as_at is deliberately NOT pushed to the keyboard
            # here. This runs on every connect/rebuild, and pushing the GUI's
            # local default silently overwrote the device's setting just for
            # opening the app. The parameter is written only when the user
            # explicitly toggles it (its change handler); the device's own
            # value wins on connect.
        except Exception as e:
            print(f"Error loading advanced settings: {e}")

    def load_advanced_ui_from_settings(self):
        """Update UI controls from global_midi_settings"""
        settings = self.global_midi_settings

        # Block signals during UI update
        self.velocity_range_slider.blockSignals(True)
        self.press_time_range_slider.blockSignals(True)
        self.aftertouch_mode_combo.blockSignals(True)
        self.aftertouch_style_combo.blockSignals(True)
        self.aftertouch_sustain_combo.blockSignals(True)
        self.aftertouch_cc_combo.blockSignals(True)
        self.smoothness_slider.blockSignals(True)
        self.vibrato_sens_slider.blockSignals(True)
        self.vibrato_decay_slider.blockSignals(True)
        self.velocity_as_at_checkbox.blockSignals(True)
        self.at_uses_curve_check.blockSignals(True)

        # Set velocity range
        vel_min = settings.get('velocity_min', 1)
        vel_max = settings.get('velocity_max', 127)
        self.velocity_range_slider.setValues(vel_min, vel_max)
        self.velocity_range_value.setText(f"{vel_min} - {vel_max}")

        # Set press time range (fast=max_press, slow=min_press)
        fast_press = settings.get('max_press_time', 20)
        slow_press = settings.get('min_press_time', 200)
        self.press_time_range_slider.setValues(fast_press, slow_press)
        self.press_time_range_value.setText(f"{fast_press} - {slow_press} ms")

        # Set aftertouch mode / style / sustain (decode the packed 0-16 byte)
        mode = settings.get('aftertouch_mode', 0)
        pair, sustain_on, legato = decode_aftertouch_byte(mode)
        for i in range(self.aftertouch_mode_combo.count()):
            if self.aftertouch_mode_combo.itemData(i) == pair:
                self.aftertouch_mode_combo.setCurrentIndex(i)
                break
        self.aftertouch_style_combo.setCurrentIndex(1 if legato else 0)
        self.aftertouch_sustain_combo.setCurrentIndex(0 if sustain_on else 1)

        # Show/hide vibrato controls, smoothness, aftertouch CC, and velocity_as_at
        is_vibrato = (pair == 4)
        is_off = (pair == 0)
        self.vibrato_sens_widget.setVisible(is_vibrato)
        self.vibrato_decay_widget.setVisible(is_vibrato)
        self.aftertouch_cc_widget.setVisible(not is_off)
        self.velocity_as_at_widget.setVisible(not is_off)
        self.at_uses_curve_widget.setVisible(not is_off)
        # Post Actuation (pair 3) locks "Velocity as Aftertouch" ON (intrinsic cap).
        is_post = (pair == 3)
        self.velocity_as_at_checkbox.blockSignals(True)
        self.velocity_as_at_checkbox.setEnabled(not is_post)
        if is_post:
            self.velocity_as_at_checkbox.setChecked(True)
        self.velocity_as_at_checkbox.blockSignals(False)
        self.aftertouch_style_widget.setVisible(not is_off)
        self.aftertouch_sustain_widget.setVisible(not is_off)
        self.smoothness_widget.setVisible(not is_off)

        # Disable retrigger when aftertouch is enabled
        self.retrigger_checkbox.setEnabled(is_off)
        self.retrigger_disabled_label.setVisible(not is_off)
        if not is_off:
            self.retrigger_checkbox.setChecked(False)
            self.retrigger_widget.setVisible(False)

        # Set AT/CC uses velocity curve checkbox
        self.at_uses_curve_check.setChecked(bool(settings.get('at_uses_curve', False)))

        # Set aftertouch CC
        cc = settings.get('aftertouch_cc', 255)
        for i in range(self.aftertouch_cc_combo.count()):
            if self.aftertouch_cc_combo.itemData(i) == cc:
                self.aftertouch_cc_combo.setCurrentIndex(i)
                break

        # Set velocity as aftertouch checkbox
        velocity_as_at = settings.get('velocity_as_at', False)
        self.velocity_as_at_checkbox.setChecked(velocity_as_at)

        # Set smoothness
        smoothness = settings.get('aftertouch_smoothness', 0)
        self.smoothness_slider.setValue(smoothness)

        # Set vibrato settings (sensitivity is reversed in UI: slider 0=max sens, 100=min sens)
        sens = settings.get('vibrato_sensitivity', 50)
        self.vibrato_sens_slider.setValue(100 - sens)  # Reverse for display

        # Convert decay ms back to percentage for slider
        decay_ms = settings.get('vibrato_decay_time', 10)
        if decay_ms > 0:
            decay_pct = min(100, (decay_ms * 127) // 100)
        else:
            decay_pct = 0
        self.vibrato_decay_slider.setValue(decay_pct)

        # Unblock signals
        self.velocity_range_slider.blockSignals(False)
        self.press_time_range_slider.blockSignals(False)
        self.aftertouch_mode_combo.blockSignals(False)
        self.aftertouch_style_combo.blockSignals(False)
        self.aftertouch_sustain_combo.blockSignals(False)
        self.aftertouch_cc_combo.blockSignals(False)
        self.smoothness_slider.blockSignals(False)
        self.vibrato_sens_slider.blockSignals(False)
        self.vibrato_decay_slider.blockSignals(False)
        self.velocity_as_at_checkbox.blockSignals(False)
        self.at_uses_curve_check.blockSignals(False)

    def on_aftertouch_mode_changed(self, index):
        """Handle aftertouch mode change - show/hide vibrato, smoothness, and CC controls"""
        pair = self.aftertouch_mode_combo.currentData() or 0
        sustain_on = (self.aftertouch_sustain_combo.currentData() == 1)
        legato = (self.aftertouch_style_combo.currentData() == 1)
        mode = encode_aftertouch_byte(pair, sustain_on, legato)
        is_vibrato = (pair == 4)
        is_off = (pair == 0)
        self.vibrato_sens_widget.setVisible(is_vibrato)
        self.vibrato_decay_widget.setVisible(is_vibrato)
        self.aftertouch_cc_widget.setVisible(not is_off)
        self.velocity_as_at_widget.setVisible(not is_off)
        self.at_uses_curve_widget.setVisible(not is_off)
        # Post Actuation (pair 3) locks "Velocity as Aftertouch" ON (intrinsic cap).
        is_post = (pair == 3)
        self.velocity_as_at_checkbox.blockSignals(True)
        self.velocity_as_at_checkbox.setEnabled(not is_post)
        if is_post:
            self.velocity_as_at_checkbox.setChecked(True)
        self.velocity_as_at_checkbox.blockSignals(False)
        self.aftertouch_style_widget.setVisible(not is_off)
        self.aftertouch_sustain_widget.setVisible(not is_off)
        # Smoothness replaces retrigger when aftertouch is active
        self.smoothness_widget.setVisible(not is_off)
        # Disable retrigger when aftertouch is enabled
        self.retrigger_checkbox.setEnabled(is_off)
        self.retrigger_disabled_label.setVisible(not is_off)
        if not is_off:
            self.retrigger_checkbox.setChecked(False)
            self.retrigger_widget.setVisible(False)
        self.global_midi_settings['aftertouch_mode'] = mode
        if self.keyboard:
            self.keyboard.set_keyboard_param_single(PARAM_AFTERTOUCH_MODE, mode)

    def on_aftertouch_cc_changed(self, index):
        """Handle aftertouch CC change"""
        cc = self.aftertouch_cc_combo.currentData()
        self.global_midi_settings['aftertouch_cc'] = cc
        if self.keyboard:
            self.keyboard.set_keyboard_param_single(PARAM_AFTERTOUCH_CC, cc)

    def on_velocity_as_at_changed(self, state):
        """Handle velocity as aftertouch checkbox change"""
        enabled = (state == Qt.Checked)
        self.global_midi_settings['velocity_as_at'] = enabled
        if self.keyboard:
            self.keyboard.set_keyboard_param_single(PARAM_VELOCITY_AS_AT, 1 if enabled else 0)

    def on_vibrato_sensitivity_changed(self, value):
        """Handle vibrato sensitivity slider change (reversed: 0=max sens, 100=min sens)"""
        firmware_value = 100 - value
        self.global_midi_settings['vibrato_sensitivity'] = firmware_value
        if self.keyboard:
            self.keyboard.set_keyboard_param_single(PARAM_VIBRATO_SENSITIVITY, firmware_value)

    def on_vibrato_decay_changed(self, value):
        """Handle vibrato decay slider change (percentage, synced with smoothness scale)"""
        if value > 0:
            decay_ms = max(1, (value * 100) // 127)
        else:
            decay_ms = 0
        self.global_midi_settings['vibrato_decay_time'] = decay_ms
        if self.keyboard:
            self.keyboard.set_keyboard_param_single(PARAM_VIBRATO_DECAY_TIME, decay_ms)

    def on_actuation_override_changed(self, state):
        """Handle actuation override checkbox change"""
        enabled = (state == Qt.Checked)
        self.actuation_point_widget.setVisible(enabled)
        self.global_midi_settings['actuation_override'] = enabled

    def on_actuation_point_changed(self, value):
        """Handle actuation point slider change"""
        mm_value = value / 10.0  # Convert 0-40 to 0.0-4.0mm
        self.actuation_point_value.setText(f"{mm_value:.1f}mm")
        self.global_midi_settings['actuation_point'] = value

    def on_speed_peak_changed(self, value):
        """Handle speed/peak ratio slider change"""
        self.speed_peak_value.setText(f"{value // 10}.{value % 10}mm")
        self.global_midi_settings['speed_peak_ratio'] = value
        # Send to firmware in real-time
        if self.keyboard:
            self.keyboard.set_keyboard_param_single(PARAM_SPEED_PEAK_RATIO, value)

    def on_retrigger_changed(self, state):
        """Handle retrigger checkbox change"""
        enabled = (state == Qt.Checked)
        self.retrigger_widget.setVisible(enabled)
        if enabled:
            # When enabling, use the slider's current value
            self.global_midi_settings['retrigger_distance'] = self.retrigger_slider.value()
        else:
            # When disabling, set to 0
            self.global_midi_settings['retrigger_distance'] = 0

    def on_retrigger_distance_changed(self, value):
        """Handle retrigger distance slider change"""
        mm_value = value / 10.0  # Convert 5-20 to 0.5-2.0mm
        self.retrigger_value.setText(f"{mm_value:.1f}mm")
        self.global_midi_settings['retrigger_distance'] = value

    def update_zone_controls_from_settings(self, zone_name, zone_data):
        """Update zone controls UI from zone settings data"""
        controls = self.zone_controls.get(zone_name)
        if not controls or not zone_data:
            return

        # Block signals during update
        for control in controls.values():
            if hasattr(control, 'blockSignals'):
                control.blockSignals(True)

        # Update velocity range
        vel_min = zone_data.get('velocity_min', 1)
        vel_max = zone_data.get('velocity_max', 127)
        controls['velocity_range_slider'].setValues(vel_min, vel_max)
        controls['velocity_range_value'].setText(f"{vel_min} - {vel_max}")

        # Update press time range
        slow_press = zone_data.get('slow_press_time', zone_data.get('min_press_time', 200))
        fast_press = zone_data.get('fast_press_time', zone_data.get('max_press_time', 20))
        controls['press_time_range_slider'].setValues(fast_press, slow_press)
        controls['press_time_range_value'].setText(f"{fast_press} - {slow_press} ms")

        # Update aftertouch mode / style / sustain (decode the packed 0-16 byte)
        at_mode = zone_data.get('aftertouch_mode', 0)
        pair, sustain_on, legato = decode_aftertouch_byte(at_mode)
        for i in range(controls['aftertouch_mode_combo'].count()):
            if controls['aftertouch_mode_combo'].itemData(i) == pair:
                controls['aftertouch_mode_combo'].setCurrentIndex(i)
                break
        controls['aftertouch_style_combo'].setCurrentIndex(1 if legato else 0)
        controls['aftertouch_sustain_combo'].setCurrentIndex(0 if sustain_on else 1)

        # Show/hide vibrato controls, smoothness, and aftertouch CC based on mode
        is_vibrato = (pair == 4)
        is_off = (pair == 0)
        controls['vibrato_sens_widget'].setVisible(is_vibrato)
        controls['vibrato_decay_widget'].setVisible(is_vibrato)
        controls['aftertouch_cc_widget'].setVisible(not is_off)
        controls['velocity_as_at_widget'].setVisible(not is_off)
        controls['at_uses_curve_widget'].setVisible(not is_off)
        # Post Actuation (pair 3) locks "Velocity as Aftertouch" ON (intrinsic cap).
        is_post = (pair == 3)
        controls['velocity_as_at_checkbox'].blockSignals(True)
        controls['velocity_as_at_checkbox'].setEnabled(not is_post)
        if is_post:
            controls['velocity_as_at_checkbox'].setChecked(True)
        controls['velocity_as_at_checkbox'].blockSignals(False)
        controls['aftertouch_style_widget'].setVisible(not is_off)
        controls['aftertouch_sustain_widget'].setVisible(not is_off)
        controls['smoothness_widget'].setVisible(not is_off)

        # Disable retrigger when aftertouch is enabled
        controls['retrigger_checkbox'].setEnabled(is_off)
        controls['retrigger_disabled_label'].setVisible(not is_off)
        if not is_off:
            controls['retrigger_checkbox'].setChecked(False)
            controls['retrigger_widget'].setVisible(False)

        # Update aftertouch CC
        at_cc = zone_data.get('aftertouch_cc', 255)
        for i in range(controls['aftertouch_cc_combo'].count()):
            if controls['aftertouch_cc_combo'].itemData(i) == at_cc:
                controls['aftertouch_cc_combo'].setCurrentIndex(i)
                break

        # Update velocity as aftertouch checkbox
        velocity_as_at = zone_data.get('velocity_as_at', False)
        controls['velocity_as_at_checkbox'].setChecked(velocity_as_at)

        # Update AT/CC uses velocity curve checkbox
        controls['at_uses_curve_check'].setChecked(bool(zone_data.get('at_uses_curve', False)))

        # Update smoothness
        smoothness = zone_data.get('aftertouch_smoothness', 0)
        controls['smoothness_slider'].setValue(smoothness)

        # Update vibrato settings (sensitivity reversed in UI: slider 0=max, 100=min)
        vib_sens = zone_data.get('vibrato_sensitivity', 50)
        controls['vibrato_sens_slider'].setValue(100 - vib_sens)  # Reverse for display

        # Convert decay ms back to percentage for slider
        vib_decay_ms = zone_data.get('vibrato_decay', zone_data.get('vibrato_decay_time', 10))
        if vib_decay_ms > 0:
            vib_decay_pct = min(100, (vib_decay_ms * 127) // 100)
        else:
            vib_decay_pct = 0
        controls['vibrato_decay_slider'].setValue(vib_decay_pct)

        # Update actuation override
        actuation_override = zone_data.get('actuation_override', False)
        actuation_point = zone_data.get('actuation_point', 20)
        controls['actuation_override_checkbox'].setChecked(actuation_override)
        controls['actuation_point_slider'].setValue(actuation_point)
        mm_value = actuation_point / 10.0
        controls['actuation_point_value'].setText(f"{mm_value:.1f}mm")
        controls['actuation_point_widget'].setVisible(actuation_override)

        # Update speed/peak ratio
        # Trigger Minimum (0.1mm steps). Legacy presets stored a 0-100 speed/peak
        # percent here; the slider (max 35) clamps those to 3.5mm.
        trigger_min = zone_data.get('speed_peak_ratio', 1)
        controls['speed_peak_slider'].setValue(trigger_min)
        v = controls['speed_peak_slider'].value()  # clamped to 1-35
        controls['speed_peak_value'].setText(f"{v // 10}.{v % 10}mm")

        # Update retrigger settings
        retrigger_distance = zone_data.get('retrigger_distance', 0)
        retrigger_enabled = (retrigger_distance > 0)
        controls['retrigger_checkbox'].setChecked(retrigger_enabled)
        if retrigger_enabled:
            controls['retrigger_slider'].setValue(retrigger_distance)
            mm_value = retrigger_distance / 10.0
            controls['retrigger_value'].setText(f"{mm_value:.1f}mm")
        controls['retrigger_widget'].setVisible(retrigger_enabled)

        # Update curve editor if present
        if 'curve_editor' in controls:
            points = zone_data.get('points', [[0, 0], [85, 85], [170, 170], [255, 255]])
            controls['curve_editor'].set_points(points)

        # Unblock signals
        for control in controls.values():
            if hasattr(control, 'blockSignals'):
                control.blockSignals(False)


    def on_curve_changed(self):
        """Handle curve editor changes"""
        # The curve editor emits this when user drags control points
        # For now, just update the display - actual curve changes
        # would need to be sent to the keyboard
        pass

    def load_velocity_curve(self):
        """Load current velocity curve and user curve names from keyboard"""
        if not self.keyboard:
            return

        try:
            # Load user curve names and configured state from keyboard
            result = self.keyboard.get_all_user_curve_names()
            if result:
                user_curve_names, configured = result
                self.update_preset_list_names(user_curve_names)
                self.update_user_preset_visibility(configured)

            # Get keyboard config which includes velocity curve index
            config = self.keyboard.get_midi_config()
            if config:
                # AT/CC Mode enable flags (global). Read here so the velocity
                # tab is self-contained — it does not depend on the MIDI-settings
                # tab pushing them. They live in the same keyboard-config byte
                # (packet 1 offset 20) as Stop Mode; get_midi_config() exposes
                # them as enable_at_modes / enable_cc_modes.
                self.atcc_at_enabled = bool(config.get('enable_at_modes', False))
                self.atcc_cc_enabled = bool(config.get('enable_cc_modes', False))
                self.update_atcc_rows_enabled()

                curve_index = config.get('he_velocity_curve', 2)  # Default to Linear (2)
                # Select the curve in the preset list
                self.select_preset_by_index(curve_index)
                if 0 <= curve_index < FACTORY_COUNT:
                    # Factory curve - load points and settings
                    self.preset_settings_stack.setCurrentIndex(0)
                    self._apply_factory_preset_settings(curve_index)
                    points = CurveEditorWidget.FACTORY_CURVE_POINTS[curve_index]
                    self.curve_editor.set_points(points)
                elif FACTORY_COUNT <= curve_index <= FACTORY_COUNT + 49:
                    # User curve - load from keyboard
                    self.preset_settings_stack.setCurrentIndex(0)
                    self.on_user_curve_selected(curve_index - FACTORY_COUNT)
                elif ATCC_START <= curve_index <= ATCC_END:
                    # Device is already on an AT/CC preset - reflect it.
                    is_cc = curve_index >= ATCC_START + 5
                    enabled = self.atcc_cc_enabled if is_cc else self.atcc_at_enabled
                    if enabled:
                        self.preset_settings_stack.setCurrentIndex(0)
                        self.curve_editor.set_points(CurveEditorWidget.FACTORY_CURVE_POINTS[2])
                    else:
                        self._show_atcc_locked_page(is_cc)
                self._update_preset_name_header(curve_index)
        except Exception as e:
            print(f"Error loading velocity curve: {e}")

    def update_preset_list_names(self, user_curve_names):
        """Update user curve names in the preset list widget and keycode labels"""
        if len(user_curve_names) != 50:
            return
        self.user_curve_names = list(user_curve_names)
        # User presets start after the factory curves + 1 separator (row FACTORY_COUNT + 1)
        for i, name in enumerate(user_curve_names):
            item = self.preset_list_widget.item((FACTORY_COUNT + 1) + i)
            if item:
                item.setText(name)
        # Update keycode labels so the keymap editor dropdown shows current names
        self.update_velocity_keycode_labels(user_curve_names)

    def update_user_preset_visibility(self, configured):
        """Show/hide user presets in the list based on which are configured.
        Slot 0 (User 1) is always visible regardless of configured state."""
        self.user_preset_configured = list(configured)
        # Ensure slot 0 is always marked configured
        self.user_preset_configured[0] = True
        for i in range(len(self.user_preset_configured)):
            is_visible = self.user_preset_configured[i]
            item = self.preset_list_widget.item((FACTORY_COUNT + 1) + i)  # User presets start at row FACTORY_COUNT + 1
            if item:
                item.setHidden(not is_visible)
        # Separator is always shown since User 1 is always visible
        self.user_presets_separator.setHidden(False)

    def update_atcc_rows_enabled(self):
        """Recolor the 10 AT/CC Mode rows (69-78): greyed (locked) unless the
        governing global enable flag is on. Rows 69-73 follow atcc_at_enabled;
        74-78 follow atcc_cc_enabled. Called on setup and whenever the flags
        change (see load_velocity_curve)."""
        items = getattr(self, 'atcc_row_items', None)
        if not items:
            return
        for i, item in enumerate(items):
            curve_index = ATCC_START + i
            is_cc = curve_index >= ATCC_START + 5
            enabled = self.atcc_cc_enabled if is_cc else self.atcc_at_enabled
            if enabled:
                # Restore the theme's normal text color (theme-safe).
                item.setForeground(self.preset_list_widget.palette().text().color())
            else:
                item.setForeground(Qt.gray)

    def get_configured_preset_count(self):
        """Return how many user presets are currently configured"""
        return sum(1 for c in self.user_preset_configured if c)

    def get_configured_preset_indices(self):
        """Return list of curve indices (7-56) that are configured, for cycling"""
        return [FACTORY_COUNT + i for i, c in enumerate(self.user_preset_configured) if c]

    def update_velocity_keycode_labels(self, user_curve_names):
        """Update HE_CURVE_USER_* and HE_MACRO_CURVE_* keycode labels with actual user curve names"""
        for i, name in enumerate(user_curve_names):
            slot_num = i + 1  # 1-10
            display_name = name if name and name.strip() else "User {}".format(slot_num)

            # Update HE_CURVE_USER_* keycodes (Playing Style direct selection)
            kc = Keycode.find("HE_CURVE_USER_{}".format(slot_num))
            if kc:
                kc.label = display_name
                kc.tooltip = "Articulation {} ({})".format(display_name, FACTORY_COUNT + i)

            # Update HE_MACRO_CURVE_* keycodes (macro-aware direct selection)
            kc_macro = Keycode.find("HE_MACRO_CURVE_{}".format(7 + i))
            if kc_macro:
                kc_macro.label = "Loop Articulation\n{}".format(display_name)
                kc_macro.tooltip = "Loop Articulation {} ({})".format(display_name, 7 + i)

    def on_preset_context_menu(self, pos):
        """Show context menu for right-clicking user presets"""
        item = self.preset_list_widget.itemAt(pos)
        if not item:
            return
        curve_index = item.data(Qt.UserRole)
        # Only allow actions on user presets (indices FACTORY_COUNT..FACTORY_COUNT+49)
        if curve_index is None or curve_index < FACTORY_COUNT or curve_index > FACTORY_COUNT + 49:
            return
        slot_index = curve_index - FACTORY_COUNT
        menu = QMenu(self.preset_list_widget)
        rename_action = menu.addAction("Rename")
        move_up_action = menu.addAction("Move Up")
        move_down_action = menu.addAction("Move Down")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")
        # Disable delete on slot 0 (User 1 is always present)
        if slot_index == 0:
            delete_action.setEnabled(False)
        # Disable move up if first configured, move down if last configured
        configured_slots = [i for i, c in enumerate(self.user_preset_configured) if c]
        if slot_index not in configured_slots:
            return
        idx_in_list = configured_slots.index(slot_index)
        if idx_in_list == 0:
            move_up_action.setEnabled(False)
        if idx_in_list >= len(configured_slots) - 1:
            move_down_action.setEnabled(False)

        action = menu.exec_(self.preset_list_widget.mapToGlobal(pos))
        if action == rename_action:
            self.rename_user_preset(slot_index)
        elif action == delete_action:
            self.delete_user_preset(slot_index)
        elif action == move_up_action:
            other = configured_slots[idx_in_list - 1]
            self.swap_user_presets(slot_index, other)
        elif action == move_down_action:
            other = configured_slots[idx_in_list + 1]
            self.swap_user_presets(slot_index, other)

    def rename_user_preset(self, slot_index):
        """Rename a user preset via input dialog and save to keyboard"""
        current_name = self.user_curve_names[slot_index]
        new_name, ok = QInputDialog.getText(
            None,
            "Rename Preset",
            "Enter new name (max 16 chars):",
            text=current_name
        )
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()[:16]
        self.user_curve_names[slot_index] = new_name
        # Update the list widget display
        item = self.preset_list_widget.item((FACTORY_COUNT + 1) + slot_index)
        if item:
            item.setText(new_name)
        # Read current preset from keyboard, then re-save with new name
        if self.keyboard:
            try:
                result = self.keyboard.get_velocity_preset(slot_index)
                if result:
                    base_zone = result.get('base', result)
                    points = base_zone.get('points', [[0, 0], [85, 85], [170, 170], [255, 255]])
                    self.keyboard.set_velocity_preset(
                        slot=slot_index,
                        points=points,
                        name=new_name,
                        velocity_min=base_zone.get('velocity_min', 1),
                        velocity_max=base_zone.get('velocity_max', 127),
                        slow_press_time=base_zone.get('slow_press_time', 200),
                        fast_press_time=base_zone.get('fast_press_time', 20),
                        aftertouch_mode=base_zone.get('aftertouch_mode', 0),
                        aftertouch_smoothness=base_zone.get('aftertouch_smoothness', 0),
                        aftertouch_cc=base_zone.get('aftertouch_cc', 255),
                        vibrato_sensitivity=base_zone.get('vibrato_sensitivity', 50),
                        vibrato_decay=base_zone.get('vibrato_decay', 10),
                        actuation_override=base_zone.get('actuation_override', False),
                        actuation_point=base_zone.get('actuation_point', 20),
                        speed_peak_ratio=base_zone.get('speed_peak_ratio', 1),
                        retrigger_distance=base_zone.get('retrigger_distance', 0),
                        at_uses_curve=base_zone.get('at_uses_curve', False),
                    )
            except Exception as e:
                print(f"Error saving preset name: {e}")
        # Update keycode labels
        self.update_velocity_keycode_labels(self.user_curve_names)

    def select_preset_by_index(self, curve_index):
        """Select a preset in the list by its curve index"""
        self.preset_list_widget.blockSignals(True)
        if 0 <= curve_index < FACTORY_COUNT:
            # Factory curve
            self.preset_list_widget.setCurrentRow(curve_index)
        elif FACTORY_COUNT <= curve_index <= FACTORY_COUNT + 49:
            # User curve - account for separator at row FACTORY_COUNT
            self.preset_list_widget.setCurrentRow((FACTORY_COUNT + 1) + (curve_index - FACTORY_COUNT))
        elif ATCC_START <= curve_index <= ATCC_END:
            # AT/CC row - after FACTORY_COUNT + 1 user-sep + 50 user + 1 AT-sep,
            # plus one extra for the CC-sep once we're past the 5 AT rows.
            row = (FACTORY_COUNT + 1 + 50 + 1) + (curve_index - ATCC_START)
            if curve_index >= ATCC_START + 5:
                row += 1  # CC separator sits above the CC rows
            self.preset_list_widget.setCurrentRow(row)
        self.preset_list_widget.blockSignals(False)

    def get_selected_preset_index(self):
        """Get the curve index of the currently selected preset"""
        item = self.preset_list_widget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return 2  # Default to Linear

    def on_preset_list_clicked(self, item):
        """Handle clicking on a preset in the list - loads settings and applies to keyboard"""
        curve_index = item.data(Qt.UserRole)

        if curve_index in (-2, -3, -4):
            # Separator (user presets / AT Modes / CC Modes) - do nothing
            return

        # AT/CC Mode presets (69-78). If the governing enable flag is OFF, show
        # an "Enable … Modes" placeholder instead of the settings panel and do
        # NOT apply anything to the keyboard.
        if ATCC_START <= curve_index <= ATCC_END:
            is_cc = curve_index >= ATCC_START + 5
            enabled = self.atcc_cc_enabled if is_cc else self.atcc_at_enabled
            if not enabled:
                self._show_atcc_locked_page(is_cc)
                self._update_preset_name_header(curve_index)
                return
            # Enabled AT/CC preset: the GUI has no local mirror of this band's
            # curve/settings data, so we just select it on the device and leave
            # the curve editor showing Linear (read-only-ish). See report notes.
            self.preset_settings_stack.setCurrentIndex(0)
            self.curve_editor.set_points(CurveEditorWidget.FACTORY_CURVE_POINTS[2])
            self._update_preset_name_header(curve_index)
            self._apply_preset_to_keyboard(curve_index)
            return

        # Normal factory / user preset → make sure the settings panel is shown.
        self.preset_settings_stack.setCurrentIndex(0)

        if curve_index < FACTORY_COUNT:
            # Factory curve - apply per-preset settings, then set curve points last
            self._apply_factory_preset_settings(curve_index)
            points = CurveEditorWidget.FACTORY_CURVE_POINTS[curve_index]
            self.curve_editor.set_points(points)
        else:
            # User curve - load full preset from keyboard
            slot_index = curve_index - FACTORY_COUNT
            self.on_user_curve_selected(slot_index)

        # Update the preset name header and rename button visibility
        self._update_preset_name_header(curve_index)

        # Auto-apply the selected preset to the keyboard
        self._apply_preset_to_keyboard(curve_index)

    def _update_preset_name_header(self, curve_index):
        """Update the preset name label and rename button based on selected preset"""
        if ATCC_START <= curve_index <= ATCC_END:
            # AT/CC Mode preset - read-only factory band, no rename.
            self.preset_name_label.setText(ATCC_NAMES[curve_index - ATCC_START])
            self.preset_rename_btn.setVisible(False)
            return
        if curve_index < FACTORY_COUNT:
            factory_names = ["Softest", "Soft", "Linear", "Hard", "Hardest", "Sensitive Soft", "Sensitive", "Sensitive Hard", "Fixed Vol", "Drums Easy", "Drums Soft", "Drums Linear", "Drums Hard", "Drums Sensitive", "Ultra Sensitive", "Fixed Sensitive", "Two Toned", "Reverse", "Random Highlights"]
            self.preset_name_label.setText(factory_names[curve_index])
            self.preset_rename_btn.setVisible(False)
        else:
            slot_index = curve_index - FACTORY_COUNT
            name = self.user_curve_names[slot_index] if slot_index < len(self.user_curve_names) else "User {}".format(slot_index + 1)
            self.preset_name_label.setText(name)
            self.preset_rename_btn.setVisible(True)

    def _apply_preset_to_keyboard(self, curve_index):
        """Apply the selected preset to the keyboard (sets the active curve index)"""
        if not self.keyboard or curve_index < 0:
            return
        try:
            self.keyboard.set_keyboard_param_single(4, curve_index)
        except Exception as e:
            print(f"Error applying preset: {e}")

    def on_preset_rename_clicked(self):
        """Handle clicking the pencil/rename button in the preset name header"""
        curve_index = self.get_selected_preset_index()
        if curve_index is None or curve_index < FACTORY_COUNT:
            return
        slot_index = curve_index - FACTORY_COUNT
        self.rename_user_preset(slot_index)
        # Update the header label after rename
        self._update_preset_name_header(curve_index)

    def on_save_as_dialog(self):
        """Open a Save As dialog to pick an existing user preset slot or save as new"""
        dialog = SaveAsPresetDialog(None, self.user_curve_names, self.user_preset_configured)
        if dialog.exec_() == QDialog.Accepted:
            slot_index = dialog.selected_slot
            name = dialog.selected_name
            if slot_index is None or name is None:
                return
            self.on_save_to_user_curve(slot_index, name)
            # Mark as configured and show in list
            self.user_curve_names[slot_index] = name
            self.user_preset_configured[slot_index] = True
            item = self.preset_list_widget.item((FACTORY_COUNT + 1) + slot_index)
            if item:
                item.setText(name)
                item.setHidden(False)
            self.user_presets_separator.setHidden(False)
            self.update_velocity_keycode_labels(self.user_curve_names)
            # Select and apply the newly saved preset
            self.select_preset_by_index(FACTORY_COUNT + slot_index)
            self._update_preset_name_header(FACTORY_COUNT + slot_index)
            self._apply_preset_to_keyboard(FACTORY_COUNT + slot_index)

    # Factory preset settings table - must match firmware factory_preset_zones[] in orthomidi5x14.c
    # Each factory curve has its own velocity range, press times, and other zone settings.
    # Extensible: add aftertouch, vibrato, etc. per-preset here in the future.
    FACTORY_PRESET_SETTINGS = {
        0: {  # Softest
            'velocity_min': 1, 'velocity_max': 60,
            'slow_press_time': 100, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 20,
            'speed_peak_ratio': 1, 'retrigger_distance': 0,
        },
        1: {  # Soft
            'velocity_min': 1, 'velocity_max': 90,
            'slow_press_time': 100, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 20,
            'speed_peak_ratio': 1, 'retrigger_distance': 0,
        },
        2: {  # Linear
            'velocity_min': 1, 'velocity_max': 127,
            'slow_press_time': 100, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 20,
            'speed_peak_ratio': 1, 'retrigger_distance': 0,
        },
        3: {  # Hard
            'velocity_min': 30, 'velocity_max': 127,
            'slow_press_time': 100, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 20,
            'speed_peak_ratio': 1, 'retrigger_distance': 0,
        },
        4: {  # Hardest
            'velocity_min': 60, 'velocity_max': 127,
            'slow_press_time': 100, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 20,
            'speed_peak_ratio': 1, 'retrigger_distance': 0,
        },
        5: {  # Sensitive Soft
            'velocity_min': 1, 'velocity_max': 127,
            'slow_press_time': 67, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 25,
            'speed_peak_ratio': 1, 'retrigger_distance': 5,
        },
        6: {  # Sensitive
            'velocity_min': 1, 'velocity_max': 127,
            'slow_press_time': 67, 'fast_press_time': 4,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 25,
            'speed_peak_ratio': 1, 'retrigger_distance': 5,
        },
        7: {  # Sensitive Hard
            'velocity_min': 30, 'velocity_max': 127,
            'slow_press_time': 67, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 25,
            'speed_peak_ratio': 1, 'retrigger_distance': 5,
        },
        8: {  # Fixed Vol
            'velocity_min': 126, 'velocity_max': 127,
            'slow_press_time': 2, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': True, 'actuation_point': 37,
            'speed_peak_ratio': 1, 'retrigger_distance': 0,
        },
        9: {  # Drums Easy
            'velocity_min': 1, 'velocity_max': 127,
            'slow_press_time': 24, 'fast_press_time': 4,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 20,
            'speed_peak_ratio': 1, 'retrigger_distance': 5,
        },
        10: {  # Drums Soft
            'velocity_min': 1, 'velocity_max': 127,
            'slow_press_time': 40, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 20,
            'speed_peak_ratio': 1, 'retrigger_distance': 0,
        },
        11: {  # Drums Linear
            'velocity_min': 1, 'velocity_max': 127,
            'slow_press_time': 40, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 20,
            'speed_peak_ratio': 1, 'retrigger_distance': 0,
        },
        12: {  # Drums Hard
            'velocity_min': 1, 'velocity_max': 127,
            'slow_press_time': 40, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 20,
            'speed_peak_ratio': 1, 'retrigger_distance': 0,
        },
        13: {  # Drums Sensitive
            'velocity_min': 1, 'velocity_max': 127,
            'slow_press_time': 46, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 20,
            'speed_peak_ratio': 1, 'retrigger_distance': 5,
        },
        14: {  # Ultra Sensitive
            'velocity_min': 1, 'velocity_max': 127,
            'slow_press_time': 29, 'fast_press_time': 5,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': True, 'actuation_point': 3,
            'speed_peak_ratio': 1, 'retrigger_distance': 5,
        },
        15: {  # Fixed Sensitive
            'velocity_min': 126, 'velocity_max': 127,
            'slow_press_time': 2, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': True, 'actuation_point': 5,
            'speed_peak_ratio': 1, 'retrigger_distance': 5,
        },
        16: {  # Two Toned
            'velocity_min': 70, 'velocity_max': 127,
            'slow_press_time': 147, 'fast_press_time': 8,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 0,
            'speed_peak_ratio': 1, 'retrigger_distance': 0,
        },
        17: {  # Reverse
            'velocity_min': 1, 'velocity_max': 127,
            'slow_press_time': 100, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 20,
            'speed_peak_ratio': 1, 'retrigger_distance': 0,
        },
        18: {  # Random Highlights
            'velocity_min': 1, 'velocity_max': 127,
            'slow_press_time': 62, 'fast_press_time': 1,
            'aftertouch_mode': 0, 'aftertouch_smoothness': 0, 'aftertouch_cc': 255,
            'vibrato_sensitivity': 50, 'vibrato_decay': 10,
            'actuation_override': False, 'actuation_point': 20,
            'speed_peak_ratio': 5, 'retrigger_distance': 5,
        },
    }

    def _apply_factory_preset_settings(self, curve_index):
        """Apply per-factory-preset zone settings when selecting a factory curve.
        Each factory curve has its own velocity range, press times, etc."""
        zone_data = self.FACTORY_PRESET_SETTINGS.get(curve_index, self.FACTORY_PRESET_SETTINGS[2])

        # Update base zone controls
        self.update_zone_controls_from_settings('base', zone_data)

        # Store in global_midi_settings
        self.global_midi_settings['velocity_min'] = zone_data['velocity_min']
        self.global_midi_settings['velocity_max'] = zone_data['velocity_max']
        self.global_midi_settings['min_press_time'] = zone_data['slow_press_time']
        self.global_midi_settings['max_press_time'] = zone_data['fast_press_time']
        self.global_midi_settings['aftertouch_mode'] = zone_data['aftertouch_mode']
        self.global_midi_settings['aftertouch_smoothness'] = zone_data.get('aftertouch_smoothness', 0)
        self.global_midi_settings['aftertouch_cc'] = zone_data['aftertouch_cc']
        self.global_midi_settings['vibrato_sensitivity'] = zone_data['vibrato_sensitivity']
        self.global_midi_settings['vibrato_decay_time'] = zone_data['vibrato_decay']
        self.global_midi_settings['actuation_override'] = zone_data['actuation_override']
        self.global_midi_settings['actuation_point'] = zone_data['actuation_point']
        self.global_midi_settings['speed_peak_ratio'] = zone_data['speed_peak_ratio']
        self.global_midi_settings['retrigger_distance'] = zone_data['retrigger_distance']
        self.global_midi_settings['at_uses_curve'] = zone_data.get('at_uses_curve', False)

    def delete_user_preset(self, slot_index):
        """Delete a user preset (clear it on firmware and hide in list). Slot 0 cannot be deleted."""
        if slot_index == 0:
            return
        if not self.keyboard:
            return

        name = self.user_curve_names[slot_index]
        reply = QMessageBox.question(
            None,
            "Delete Preset",
            "Delete preset '{}'?".format(name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            # Write an empty preset (blank name = unconfigured)
            self.keyboard.set_velocity_preset(
                slot=slot_index,
                points=[[0, 0], [85, 85], [170, 170], [255, 255]],
                name="",
                velocity_min=1, velocity_max=127,
                slow_press_time=200, fast_press_time=20,
                aftertouch_mode=0, aftertouch_smoothness=0, aftertouch_cc=255,
                vibrato_sensitivity=50, vibrato_decay=10,
                actuation_override=False, actuation_point=20,
                speed_peak_ratio=1, retrigger_distance=0,
            )
            # Update local state
            self.user_preset_configured[slot_index] = False
            self.user_curve_names[slot_index] = "User {}".format(slot_index + 1)
            item = self.preset_list_widget.item((FACTORY_COUNT + 1) + slot_index)
            if item:
                item.setText(self.user_curve_names[slot_index])
                item.setHidden(True)
            # Hide separator if no configured presets remain
            if not any(self.user_preset_configured):
                self.user_presets_separator.setHidden(True)
            self.update_velocity_keycode_labels(self.user_curve_names)
        except Exception as e:
            QMessageBox.warning(None, "Delete Failed", "Error deleting preset: {}".format(e))

    def swap_user_presets(self, slot_a, slot_b):
        """Swap two user presets on the firmware and update the GUI list."""
        if not self.keyboard:
            return

        try:
            # Read both presets from firmware
            preset_a = self.keyboard.get_velocity_preset(slot_a)
            preset_b = self.keyboard.get_velocity_preset(slot_b)
            if not preset_a or not preset_b:
                return

            # Write A's data to slot B and vice versa
            self._write_preset_data(slot_b, preset_a)
            self._write_preset_data(slot_a, preset_b)

            # Swap local state
            self.user_curve_names[slot_a], self.user_curve_names[slot_b] = \
                self.user_curve_names[slot_b], self.user_curve_names[slot_a]
            self.user_preset_configured[slot_a], self.user_preset_configured[slot_b] = \
                self.user_preset_configured[slot_b], self.user_preset_configured[slot_a]

            # Update list widget text and visibility
            for slot in (slot_a, slot_b):
                item = self.preset_list_widget.item((FACTORY_COUNT + 1) + slot)
                if item:
                    item.setText(self.user_curve_names[slot])
                    item.setHidden(not self.user_preset_configured[slot])

            self.update_velocity_keycode_labels(self.user_curve_names)
        except Exception as e:
            QMessageBox.warning(None, "Move Failed", "Error moving preset: {}".format(e))

    def _write_preset_data(self, slot, preset_data):
        """Write preset data dict (from get_velocity_preset) to a slot on the firmware."""
        name = preset_data.get('name', '')
        base = preset_data.get('base', preset_data)
        self.keyboard.set_velocity_preset(
            slot=slot,
            points=base.get('points', [[0, 0], [85, 85], [170, 170], [255, 255]]),
            name=name,
            velocity_min=base.get('velocity_min', 1),
            velocity_max=base.get('velocity_max', 127),
            slow_press_time=base.get('slow_press_time', 200),
            fast_press_time=base.get('fast_press_time', 20),
            aftertouch_mode=base.get('aftertouch_mode', 0),
            aftertouch_smoothness=base.get('aftertouch_smoothness', 0),
            aftertouch_cc=base.get('aftertouch_cc', 255),
            vibrato_sensitivity=base.get('vibrato_sensitivity', 50),
            vibrato_decay=base.get('vibrato_decay', 10),
            actuation_override=base.get('actuation_override', False),
            actuation_point=base.get('actuation_point', 20),
            speed_peak_ratio=base.get('speed_peak_ratio', 1),
            retrigger_distance=base.get('retrigger_distance', 0),
            at_uses_curve=base.get('at_uses_curve', False),
        )

    def on_save_preset_overwrite(self):
        """Overwrite the currently selected user preset with current settings.
        If a factory preset is selected, redirect to Save As dialog."""
        curve_index = self.get_selected_preset_index()
        if curve_index is None or curve_index < FACTORY_COUNT or curve_index > FACTORY_COUNT + 49:
            # Factory preset selected - redirect to Save As
            self.on_save_as_dialog()
            return
        slot_index = curve_index - FACTORY_COUNT
        name = self.user_curve_names[slot_index]
        self.on_save_to_user_curve(slot_index, name)
        # Ensure it's marked configured and visible
        self.user_preset_configured[slot_index] = True
        item = self.preset_list_widget.item((FACTORY_COUNT + 1) + slot_index)
        if item:
            item.setHidden(False)
        self.user_presets_separator.setHidden(False)
        # Apply the saved preset to the keyboard
        self._apply_preset_to_keyboard(curve_index)

    def on_new_linear_preset(self):
        """Create a brand-new user preset defaulting to the Linear curve + settings.
        Finds the first empty slot, names it, saves it, and selects it for editing."""
        # Find first empty slot
        empty_slot = None
        for i in range(50):
            if not self.user_preset_configured[i]:
                empty_slot = i
                break
        if empty_slot is None:
            QMessageBox.warning(None, "No Empty Slots", "All 50 user preset slots are in use.")
            return

        name, ok = QInputDialog.getText(
            None,
            "New Preset",
            "Preset Name:",
            text="User {}".format(empty_slot + 1)
        )
        if not ok or not name.strip():
            return
        name = name.strip()[:16]

        # Reset the editor to the factory Linear curve + its settings so the new
        # preset starts from Linear defaults (index 2 = Linear).
        self.curve_editor.set_points(CurveEditorWidget.FACTORY_CURVE_POINTS[2])
        self._apply_factory_preset_settings(2)

        # Persist the Linear defaults into the empty slot
        self.on_save_to_user_curve(empty_slot, name)
        # Mark as configured and show in list
        self.user_curve_names[empty_slot] = name
        self.user_preset_configured[empty_slot] = True
        item = self.preset_list_widget.item((FACTORY_COUNT + 1) + empty_slot)
        if item:
            item.setText(name)
            item.setHidden(False)
        self.user_presets_separator.setHidden(False)
        self.update_velocity_keycode_labels(self.user_curve_names)
        # Select, label, and apply the newly created preset
        self.select_preset_by_index(FACTORY_COUNT + empty_slot)
        self._update_preset_name_header(FACTORY_COUNT + empty_slot)
        self._apply_preset_to_keyboard(FACTORY_COUNT + empty_slot)

    def on_save_as_new_preset(self):
        """Save current settings as a new user preset. Prompts for name, finds first empty slot."""
        # Find first empty slot
        empty_slot = None
        for i in range(50):
            if not self.user_preset_configured[i]:
                empty_slot = i
                break
        if empty_slot is None:
            QMessageBox.warning(None, "No Empty Slots", "All 50 user preset slots are in use.")
            return

        name, ok = QInputDialog.getText(
            None,
            "New Preset",
            "Preset Name:",
            text="User {}".format(empty_slot + 1)
        )
        if not ok or not name.strip():
            return
        name = name.strip()[:16]

        self.on_save_to_user_curve(empty_slot, name)
        # Mark as configured and show in list
        self.user_curve_names[empty_slot] = name
        self.user_preset_configured[empty_slot] = True
        item = self.preset_list_widget.item((FACTORY_COUNT + 1) + empty_slot)
        if item:
            item.setText(name)
            item.setHidden(False)
        self.user_presets_separator.setHidden(False)
        self.update_velocity_keycode_labels(self.user_curve_names)
        # Select the newly created preset
        self.select_preset_by_index(FACTORY_COUNT + empty_slot)

    def on_user_curve_selected(self, slot_index):
        """Load user curve (velocity preset) from keyboard when selected in dropdown.
        Loads base zone preset settings (single-zone format)."""
        if not self.keyboard:
            return

        try:
            # get_velocity_preset returns full preset with zone data
            result = self.keyboard.get_velocity_preset(slot_index)
            if result:
                # Load and display preset name from device
                preset_name = result.get('name', f'User {slot_index + 1}')
                if preset_name:  # Only update if name is not empty
                    self.curve_editor.set_user_curve_name(slot_index, preset_name)

                # Load base zone data
                base_zone = result.get('base', result)  # Fallback to top-level for backward compat
                points = base_zone.get('points', [[0, 0], [85, 85], [170, 170], [255, 255]])
                self.curve_editor.load_user_curve_points(points, slot_index)

                # Update base zone controls and settings
                self.update_zone_controls_from_settings('base', base_zone)

                # Store base zone settings in global_midi_settings
                self.global_midi_settings['velocity_min'] = base_zone.get('velocity_min', 1)
                self.global_midi_settings['velocity_max'] = base_zone.get('velocity_max', 127)
                self.global_midi_settings['min_press_time'] = base_zone.get('slow_press_time', 200)
                self.global_midi_settings['max_press_time'] = base_zone.get('fast_press_time', 20)
                self.global_midi_settings['aftertouch_mode'] = base_zone.get('aftertouch_mode', 0)
                self.global_midi_settings['aftertouch_smoothness'] = base_zone.get('aftertouch_smoothness', 0)
                self.global_midi_settings['aftertouch_cc'] = base_zone.get('aftertouch_cc', 255)
                self.global_midi_settings['vibrato_sensitivity'] = base_zone.get('vibrato_sensitivity', 50)
                self.global_midi_settings['vibrato_decay_time'] = base_zone.get('vibrato_decay', 10)
                self.global_midi_settings['actuation_override'] = base_zone.get('actuation_override', False)
                self.global_midi_settings['actuation_point'] = base_zone.get('actuation_point', 20)
                self.global_midi_settings['speed_peak_ratio'] = base_zone.get('speed_peak_ratio', 1)
                self.global_midi_settings['retrigger_distance'] = base_zone.get('retrigger_distance', 0)
                self.global_midi_settings['at_uses_curve'] = base_zone.get('at_uses_curve', False)

        except Exception as e:
            print(f"Error loading user curve {slot_index}: {e}")

    def get_zone_settings_from_controls(self, zone_name):
        """Get zone settings from the zone controls widgets"""
        controls = self.zone_controls.get(zone_name)
        if not controls:
            return None

        zone_data = {
            'velocity_min': controls['velocity_range_slider'].lowValue(),
            'velocity_max': controls['velocity_range_slider'].highValue(),
            'slow_press_time': controls['press_time_range_slider'].highValue(),  # slow is high value
            'fast_press_time': controls['press_time_range_slider'].lowValue(),   # fast is low value
            'aftertouch_mode': encode_aftertouch_byte(
                controls['aftertouch_mode_combo'].currentData() or 0,
                controls['aftertouch_sustain_combo'].currentData() == 1,
                controls['aftertouch_style_combo'].currentData() == 1),
            'aftertouch_smoothness': controls['smoothness_slider'].value(),
            'aftertouch_cc': controls['aftertouch_cc_combo'].currentData(),
            'vibrato_sensitivity': controls['vibrato_sens_slider'].value(),
            'vibrato_decay': controls['vibrato_decay_slider'].value(),
            'actuation_override': controls['actuation_override_checkbox'].isChecked(),
            'actuation_point': controls['actuation_point_slider'].value(),
            'speed_peak_ratio': controls['speed_peak_slider'].value(),
            'retrigger_distance': controls['retrigger_slider'].value() if controls['retrigger_checkbox'].isChecked() else 0,
            'at_uses_curve': controls['at_uses_curve_check'].isChecked()
        }

        # Get curve points from the zone's curve editor (or the main one for base)
        if 'curve_editor' in controls:
            zone_data['points'] = controls['curve_editor'].get_points()
        else:
            zone_data['points'] = self.curve_editor.get_points()

        return zone_data

    def on_save_to_user_curve(self, slot_index, curve_name):
        """Save current velocity preset to a user slot on the keyboard.
        Saves base zone settings (single-zone format)."""
        if not self.keyboard:
            QMessageBox.warning(
                None,
                tr("VelocityTab", "Save Failed"),
                tr("VelocityTab", "Keyboard not connected.")
            )
            return

        # Re-entrancy guard: rapid double-clicks (overwrite / Save As) funnel
        # through here; block a second synchronous transfer while one is in flight.
        if getattr(self, '_save_busy', False):
            return
        self._save_busy = True

        try:
            points = self.curve_editor.get_points()
            settings = self.global_midi_settings

            # Use the set_velocity_preset method (single-zone, base only)
            success = self.keyboard.set_velocity_preset(
                slot=slot_index,
                points=points,
                name=curve_name,
                velocity_min=settings.get('velocity_min', 1),
                velocity_max=settings.get('velocity_max', 127),
                slow_press_time=settings.get('min_press_time', 200),
                fast_press_time=settings.get('max_press_time', 20),
                aftertouch_mode=settings.get('aftertouch_mode', 0),
                aftertouch_smoothness=settings.get('aftertouch_smoothness', 0),
                aftertouch_cc=settings.get('aftertouch_cc', 255),
                vibrato_sensitivity=settings.get('vibrato_sensitivity', 50),
                vibrato_decay=settings.get('vibrato_decay_time', 10),
                actuation_override=settings.get('actuation_override', False),
                actuation_point=settings.get('actuation_point', 20),
                speed_peak_ratio=settings.get('speed_peak_ratio', 1),
                retrigger_distance=settings.get('retrigger_distance', 0),
                at_uses_curve=settings.get('at_uses_curve', False),
            )

            if success:
                extra_info = ""
                if settings.get('actuation_override', False):
                    mm_value = settings.get('actuation_point', 20) / 10.0
                    extra_info += f", actuation override {mm_value:.1f}mm"
                _tm = settings.get('speed_peak_ratio', 1)
                extra_info += f", trigger min {_tm // 10}.{_tm % 10}mm"
                retrig = settings.get('retrigger_distance', 0)
                if retrig > 0:
                    extra_info += f", retrigger {retrig/10.0:.1f}mm"

                # NOTE: Actuation override and retrigger are now handled directly by firmware
                # The firmware reads zone-specific settings from the velocity preset globals
                # (preset_actuation_override, preset_retrigger_distance, etc.) and applies
                # them during MIDI key processing. No per-key actuation changes needed here.

                QMessageBox.information(
                    None,
                    tr("VelocityTab", "Articulation Preset Saved"),
                    tr("VelocityTab", f"Preset saved to User slot {slot_index + 1} as '{curve_name}'.\n\n"
                       f"Includes: articulation, velocity {settings.get('velocity_min', 1)}-{settings.get('velocity_max', 127)}, "
                       f"press times, aftertouch, vibrato{extra_info}.")
                )
                # Update the user curve name in the preset list and keycode labels
                self.user_curve_names[slot_index] = curve_name
                item = self.preset_list_widget.item((FACTORY_COUNT + 1) + slot_index)
                if item:
                    item.setText(curve_name)
                self.update_velocity_keycode_labels(self.user_curve_names)
            else:
                QMessageBox.warning(
                    None,
                    tr("VelocityTab", "Save Failed"),
                    tr("VelocityTab", "Failed to save articulation preset to keyboard.")
                )
        except Exception as e:
            QMessageBox.warning(
                None,
                tr("VelocityTab", "Save Failed"),
                tr("VelocityTab", f"Error saving articulation preset: {e}")
            )
        finally:
            self._save_busy = False

    def _build_articulation_export_text(self):
        """Serialize the currently-edited articulation (curve points + all bundled
        zone settings) into a stable, human-readable text block. The field set and
        order mirror the firmware `zone_settings_t` so an export can be turned
        directly into a factory preset definition."""
        points = self.curve_editor.get_points()
        s = self.global_midi_settings

        # Resolve a display name from the current preset list selection.
        name = "Custom"
        try:
            item = self.preset_list_widget.currentItem()
            if item is not None:
                txt = item.text()
                if txt and not txt.startswith("─"):
                    name = txt
        except Exception:
            pass

        pts_str = " ".join("[{},{}]".format(int(p[0]), int(p[1])) for p in points)
        at_mode = s.get('aftertouch_mode', 0)
        lines = [
            "=== Articulation Export ===",
            "name: {}".format(name),
            "points: {}".format(pts_str),
            "velocity_min: {}".format(s.get('velocity_min', 1)),
            "velocity_max: {}".format(s.get('velocity_max', 127)),
            "slow_press_time: {}".format(s.get('min_press_time', 200)),
            "fast_press_time: {}".format(s.get('max_press_time', 20)),
            "aftertouch_mode: {}".format(at_mode),
            "aftertouch_cc: {}".format(s.get('aftertouch_cc', 255)),
            "aftertouch_smoothness: {}".format(s.get('aftertouch_smoothness', 0)),
            "vibrato_sensitivity: {}".format(s.get('vibrato_sensitivity', 50)),
            "vibrato_decay: {}".format(s.get('vibrato_decay_time', 10)),
            "actuation_override: {}".format(1 if s.get('actuation_override', False) else 0),
            "actuation_point: {}".format(s.get('actuation_point', 20)),
            "trigger_minimum: {}".format(s.get('speed_peak_ratio', 1)),
            "retrigger_distance: {}".format(s.get('retrigger_distance', 0)),
            "at_uses_curve: {}".format(1 if s.get('at_uses_curve', False) else 0),
        ]
        return "\n".join(lines)

    def on_export_articulation(self):
        """Copy the current articulation's full settings to the clipboard as text
        and show them in a selectable dialog so they can be shared / pasted."""
        try:
            text = self._build_articulation_export_text()
        except Exception as e:
            QMessageBox.warning(
                None,
                tr("VelocityTab", "Export Failed"),
                tr("VelocityTab", f"Could not read the current articulation: {e}")
            )
            return

        # Put it on the clipboard immediately.
        try:
            QApplication.clipboard().setText(text)
        except Exception:
            pass

        dlg = QDialog()
        dlg.setWindowTitle(tr("VelocityTab", "Export Articulation"))
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)

        info = QLabel(tr("VelocityTab",
                         "Copied to clipboard. Select and copy the text below to share "
                         "these exact articulation settings."))
        info.setWordWrap(True)
        layout.addWidget(info)

        text_box = QTextEdit()
        text_box.setPlainText(text)
        text_box.setReadOnly(True)
        text_box.setLineWrapMode(QTextEdit.NoWrap)
        text_box.setMinimumHeight(320)
        layout.addWidget(text_box)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton(tr("VelocityTab", "Copy to Clipboard"))
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(text))
        btn_row.addWidget(copy_btn)
        close_btn = QPushButton(tr("VelocityTab", "Close"))
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dlg.exec_()

    def on_save_curve(self):
        """Save velocity curve selection to keyboard (sets the active curve index)"""
        if not self.keyboard:
            return

        # Get curve index from the preset list
        curve_index = self.get_selected_preset_index()

        if curve_index < 0:
            return

        try:
            # Use set_keyboard_param_single to set the velocity curve
            # PARAM_HE_VELOCITY_CURVE = 4 (from keyboard_comm.py constants)
            success = self.keyboard.set_keyboard_param_single(4, curve_index)
            if not success:
                QMessageBox.warning(
                    None,
                    tr("VelocityTab", "Apply Failed"),
                    tr("VelocityTab", "Failed to apply articulation.")
                )
        except Exception as e:
            QMessageBox.warning(
                None,
                tr("VelocityTab", "Apply Failed"),
                tr("VelocityTab", f"Error applying articulation: {e}")
            )


class SaveAsPresetDialog(QDialog):
    """Dialog for Save As - lets user pick an existing user preset slot or save as new."""

    def __init__(self, parent, user_curve_names, user_preset_configured):
        super().__init__(parent)
        self.setWindowTitle("Save As...")
        self.setMinimumWidth(320)
        self.setMaximumWidth(400)
        self.user_curve_names = list(user_curve_names)
        self.user_preset_configured = list(user_preset_configured)
        self.selected_slot = None
        self.selected_name = None

        layout = QVBoxLayout()
        layout.setSpacing(8)

        # Name field
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(16)
        self.name_edit.setPlaceholderText("Preset name")
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)

        # User preset list
        layout.addWidget(QLabel("Overwrite existing preset:"))
        self.preset_list = QListWidget()
        self.preset_list.setMaximumHeight(200)
        for i in range(50):
            if self.user_preset_configured[i]:
                item = QListWidgetItem(self.user_curve_names[i])
                item.setData(Qt.UserRole, i)
                self.preset_list.addItem(item)
        self.preset_list.itemClicked.connect(self._on_preset_clicked)
        layout.addWidget(self.preset_list)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.save_btn = QPushButton("Save")
        self.save_btn.setEnabled(False)
        self.save_btn.setToolTip("Overwrite the selected preset")
        self.save_btn.clicked.connect(self._on_save_to_existing)
        btn_layout.addWidget(self.save_btn)

        save_new_btn = QPushButton("Save as New")
        save_new_btn.setToolTip("Save to the first available empty slot")
        save_new_btn.clicked.connect(self._on_save_as_new)
        btn_layout.addWidget(save_new_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _on_preset_clicked(self, item):
        """When a preset is clicked, populate the name field"""
        self.name_edit.setText(item.text())
        self.save_btn.setEnabled(True)

    def _on_save_to_existing(self):
        """Save to the selected existing preset slot"""
        item = self.preset_list.currentItem()
        if not item:
            return
        name = self.name_edit.text().strip()[:16]
        if not name:
            name = item.text()
        self.selected_slot = item.data(Qt.UserRole)
        self.selected_name = name
        self.accept()

    def _on_save_as_new(self):
        """Save to the first available empty slot"""
        name = self.name_edit.text().strip()[:16]
        if not name:
            QMessageBox.warning(self, "Name Required", "Please enter a preset name.")
            return
        # Find first empty slot
        empty_slot = None
        for i in range(50):
            if not self.user_preset_configured[i]:
                empty_slot = i
                break
        if empty_slot is None:
            QMessageBox.warning(self, "No Empty Slots", "All 50 user preset slots are in use.")
            return
        self.selected_slot = empty_slot
        self.selected_name = name
        self.accept()
