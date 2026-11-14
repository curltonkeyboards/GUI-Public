# SPDX-License-Identifier: GPL-2.0-or-later
import json
import ui_mode
import struct

import sys

from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QVBoxLayout, QMessageBox, QWidget,
                              QGroupBox, QSlider, QCheckBox, QPushButton, QComboBox, QFrame,
                              QSizePolicy, QScrollArea, QTabWidget, QDialog, QDialogButtonBox,
                              QSpinBox, QGridLayout, QMenu, QToolButton, QAction, QInputDialog,
                              QGraphicsView, QGraphicsScene, QStyle)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSettings, QEvent, QPointF
from PyQt5.QtGui import QCursor, QPainter

from widgets.combo_box import ArrowComboBox
from keycode_search_dialog import KeycodeSearchDialog
from editor.basic_editor import BasicEditor
from editor.articulation_options import populate_articulation_combo, apply_articulation_visibility
from widgets.keyboard_widget import KeyboardWidget2, KeyboardWidgetSimple, EncoderWidget, EncoderWidget2
from keycodes.keycodes import Keycode, joystick_function_id, JOYSTICK_FUNCTION_LABELS, JOYSTICK_FUNCTION_NAMES
from widgets.square_button import SquareButton
from tabbed_keycodes import TabbedKeycodes, keycode_filter_masked
from util import tr, KeycodeDisplay
from vial_device import VialKeyboard
from editor.arpeggiator import DebugConsole
from editor.keymap_presets import (KEYMAP_PRESETS, ENCODER_PRESETS,
                                   INDIVIDUAL_ENCODER_PRESETS,
                                   PRESET_CATEGORIES,
                                   PRESET_TYPE_TUNING, PRESET_TYPE_QB_ROW, PRESET_TYPE_QB_COLUMN,
                                   PRESET_TYPE_KEYBOARD)
from protocol.keyboard_comm import (
    PARAM_CHANNEL_NUMBER, PARAM_TRANSPOSE_NUMBER, PARAM_TRANSPOSE_NUMBER2, PARAM_TRANSPOSE_NUMBER3,
    PARAM_HE_VELOCITY_CURVE, PARAM_HE_VELOCITY_MIN, PARAM_HE_VELOCITY_MAX,
    PARAM_KEYSPLIT_HE_VELOCITY_CURVE, PARAM_KEYSPLIT_HE_VELOCITY_MIN, PARAM_KEYSPLIT_HE_VELOCITY_MAX,
    PARAM_TRIPLESPLIT_HE_VELOCITY_CURVE, PARAM_TRIPLESPLIT_HE_VELOCITY_MIN, PARAM_TRIPLESPLIT_HE_VELOCITY_MAX,
    PARAM_BASE_SUSTAIN, PARAM_KEYSPLIT_SUSTAIN, PARAM_TRIPLESPLIT_SUSTAIN,
    PARAM_KEYSPLIT_SMARTCHORD_IGNORE, PARAM_TRIPLESPLIT_SMARTCHORD_IGNORE,
    PARAM_KEYSPLITCHANNEL, PARAM_KEYSPLIT2CHANNEL, PARAM_KEYSPLITSTATUS, PARAM_KEYSPLITTRANSPOSESTATUS, PARAM_KEYSPLITVELOCITYSTATUS,
    PARAM_VELOCITY_SENSITIVITY, PARAM_CC_SENSITIVITY
)


class Debouncer:
    """Debounce utility for delaying function calls until user stops interacting

    Usage:
        debouncer = Debouncer(200, my_function, arg1, arg2)
        # Call trigger() each time the event happens
        debouncer.trigger()  # Function will only execute 200ms after last trigger
    """
    def __init__(self, delay_ms, callback, *args, **kwargs):
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: callback(*args, **kwargs))
        self.delay_ms = delay_ms

    def trigger(self):
        """Trigger the debouncer - restarts the timer"""
        self.timer.stop()
        self.timer.start(self.delay_ms)

    def cancel(self):
        """Cancel pending callback"""
        self.timer.stop()



class QuickActuationWidget(QWidget):
    """Full-featured per-layer actuation controls in keymap editor"""

    # Signal emitted when "Enable Per-Key" is checked
    enable_per_key_requested = pyqtSignal()
    # Signal emitted when a layer is renamed
    layer_renamed = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.device = None
        self.syncing = False
        self.current_layer = 0
        self.per_layer_enabled = False
        self.trigger_settings_ref = None  # Reference to TriggerSettingsTab

        # Cache all layer data in memory to avoid device I/O lag
        self.layer_data = []
        for _ in range(12):
            self.layer_data.append({
                'normal': 127,
                'midi': 127,
                'velocity': 3,  # Velocity mode: 3=Speed+Peak (only supported mode)
                'vel_speed': 10,  # Velocity speed scale
                'aftertouch_mode': 0,  # 0=Off, 1-8 = various modes
                'aftertouch_cc': 255,  # 255=Off (no CC), 0-127=CC number
                'vibrato_sensitivity': 50,   # 0-100 (percentage, 100% = 30% effective)
                'vibrato_decay_time': 10    # 0-50 (ms per unit decay)
            })

        # MIDI settings (global, per keyboard)
        self.midi_settings = {
            'channel': 0,
            'transpose': 0,
            'sustain': 0,  # Allow
            'velocity_preset': 2,  # Medium
            'velocity_curve': 2,
            'velocity_min': 1,
            'velocity_max': 127,
            'keysplit_enabled': False,
            'keysplit_channel': 0,
            'keysplit_transpose': 0,
            'keysplit_sustain': 0,  # Allow
            'keysplit_velocity_curve': 2,
            'keysplit_velocity_min': 1,
            'keysplit_velocity_max': 127,
            'triplesplit_enabled': False,
            'triplesplit_channel': 0,
            'triplesplit_transpose': 0,
            'triplesplit_sustain': 0,  # Allow
            'triplesplit_velocity_curve': 2,
            'triplesplit_velocity_min': 1,
            'triplesplit_velocity_max': 127
        }

        # Global MIDI settings for velocity/aftertouch (not per-layer)
        self.global_midi_settings = {
            'velocity_mode': 3,         # 3=Speed+Peak (only supported mode)
            'aftertouch_mode': 0,       # 0=Off, 1-8 = various modes
            'aftertouch_cc': 255,       # 0-127=CC number, 255=off (poly AT only)
            'vibrato_sensitivity': 50,  # 0-100 (percentage, 100% = 30% effective)
            'vibrato_decay_time': 10,   # 0-50 (ms per unit decay)
            'min_press_time': 200,      # 50-500ms (slow press threshold)
            'max_press_time': 20        # 5-100ms (fast press threshold)
        }

        self.matrix_test = None  # Reference to MatrixTest (set later via set_matrix_test_reference)

        self.setMinimumWidth(344)
        self.setMaximumWidth(344)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        # The whole panel sits in a card (drawn by the theme: see QFrame[card="true"] in themes.py)
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(6, 6, 10, 6)
        self.setLayout(outer_layout)
        card = QFrame()
        card.setProperty("card", True)
        outer_layout.addWidget(card)
        outer_layout.addStretch(1)

        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(12, 10, 10, 12)
        card.setLayout(layout)

        # Layer name header with rename button (matches toggle/macro/delay title style)
        layer_header = QHBoxLayout()
        layer_header.setContentsMargins(0, 0, 0, 0)
        self.layer_title_label = QLabel("<b>Layer 1</b>")
        self.layer_title_label.setStyleSheet("font-size: 14pt;")
        layer_header.addWidget(self.layer_title_label)

        self.layer_rename_btn = QPushButton("Rename")
        self.layer_rename_btn.setMaximumHeight(24)
        self.layer_rename_btn.setMaximumWidth(60)
        self.layer_rename_btn.setStyleSheet("QPushButton { font-size: 8pt; border-radius: 3px; padding: 2px 6px; }")
        self.layer_rename_btn.clicked.connect(self._on_layer_rename)
        layer_header.addWidget(self.layer_rename_btn)

        layer_header.addStretch()
        layout.addLayout(layer_header)

        # Create actuation widgets (hidden, kept for sync with TriggerSettingsTab)
        self.actuation_tab = self.create_actuation_tab()

        # One actuation slider for the layer (it moves the two hidden ones together)
        layout.addWidget(self.create_layer_actuation_panel())

        # Show MIDI Settings directly (no tab widget)
        self.midi_tab = self.create_midi_tab()
        layout.addWidget(self.midi_tab)

    def create_help_label(self, tooltip_text):
        """Create a small question mark button with tooltip for help"""
        help_btn = QPushButton("?")
        help_btn.setStyleSheet("""
            QPushButton {
                color: palette(dark);
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
                color: palette(button-text);
                background-color: palette(light);
                border-color: palette(highlight);
            }
        """)
        help_btn.setToolTip(tooltip_text)
        help_btn.setFocusPolicy(Qt.NoFocus)
        return help_btn

    def create_layer_actuation_panel(self):
        """The Actuation controls shown above MIDI Settings: one slider, in mm, that sets the
        actuation point of every key on the layer (normal keys and MIDI keys alike), and a
        small Per layer button.

        Per layer off: the value is given to all twelve layers. Per layer on: only the
        layer being shown changes. With per-key actuation on, each key has its own value
        (set in the Advanced tab), so the slider is greyed out."""
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(3)
        layout.setContentsMargins(10, 4, 10, 0)
        panel.setLayout(layout)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        title = QLabel(tr("QuickActuationWidget", "Actuation"))
        title.setStyleSheet("QLabel { font-weight: bold; font-size: 12px; }")
        head.addWidget(title)
        head.addWidget(self.create_help_label(
            "How far a key travels before it registers, for every key on the layer\n"
            "(normal keys and MIDI keys). Lower = lighter touch.\n\n"
            "Per layer off: the same value on all layers.\n"
            "Per layer on: each layer keeps its own value."))
        head.addStretch(1)

        self.layer_actuation_per_layer_btn = QPushButton(tr("QuickActuationWidget", "Per layer"))
        self.layer_actuation_per_layer_btn.setCheckable(True)
        self.layer_actuation_per_layer_btn.setMaximumHeight(24)
        self.layer_actuation_per_layer_btn.setStyleSheet("QPushButton { font-size: 8pt; padding: 2px 8px; }")
        self.layer_actuation_per_layer_btn.setToolTip(
            "On: this layer has its own actuation. Off: all layers share one.")
        self.layer_actuation_per_layer_btn.clicked.connect(self.on_layer_actuation_per_layer_clicked)
        head.addWidget(self.layer_actuation_per_layer_btn)
        layout.addLayout(head)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.layer_actuation_slider = QSlider(Qt.Horizontal)
        self.layer_actuation_slider.setMinimum(7)         # 0.11mm, the same floor as the other actuation sliders
        self.layer_actuation_slider.setMaximum(255)       # 4.00mm
        self.layer_actuation_slider.setValue(127)
        self.layer_actuation_slider.valueChanged.connect(self.on_layer_actuation_moved)
        self.layer_actuation_slider.sliderReleased.connect(self.on_layer_actuation_released)
        row.addWidget(self.layer_actuation_slider, 1)

        self.layer_actuation_label = QLabel("2.00mm")
        self.layer_actuation_label.setMinimumWidth(58)
        self.layer_actuation_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; }")
        self.layer_actuation_label.setAlignment(Qt.AlignCenter)
        row.addWidget(self.layer_actuation_label)
        layout.addLayout(row)

        self.layer_actuation_note = QLabel(tr("QuickActuationWidget", "Per-key actuation is on: set each key in the Actuation tab."))
        self.layer_actuation_note.setStyleSheet("QLabel { font-style: italic; font-size: 10px; }")
        self.layer_actuation_note.setWordWrap(True)
        self.layer_actuation_note.setVisible(False)
        layout.addWidget(self.layer_actuation_note)

        # While the handle is being dragged nothing is sent: the value goes to the keyboard once,
        # when the mouse button is let go. Changes made without dragging (arrow keys, the mouse
        # wheel, a click on the track) are sent a moment after the last one.
        self._layer_actuation_timer = QTimer(self)
        self._layer_actuation_timer.setSingleShot(True)
        self._layer_actuation_timer.setInterval(450)
        self._layer_actuation_timer.timeout.connect(self.commit_layer_actuation)
        self._layer_actuation_filling = False

        return panel

    def refresh_layer_actuation_ui(self):
        """Show the current layer's actuation and the per-layer / per-key state."""
        if not hasattr(self, 'layer_actuation_slider'):
            return

        # The Advanced tab owns the two modes; ask it, so this always shows what it shows.
        ts = self.trigger_settings_ref
        per_key = ts.mode_enabled if ts else self.enable_per_key_checkbox.isChecked()
        per_layer = ts.per_layer_enabled if ts else self.per_layer_enabled
        value = self.layer_data[self.current_layer].get('normal', 127)

        self._layer_actuation_filling = True
        self.layer_actuation_slider.setValue(max(7, min(255, int(value))))
        self._layer_actuation_filling = False
        self.layer_actuation_label.setText(f"{self.layer_actuation_slider.value() * 4.0 / 255.0:.2f}mm")

        self.layer_actuation_slider.setEnabled(not per_key)
        self.layer_actuation_label.setEnabled(not per_key)
        self.layer_actuation_note.setVisible(per_key)
        self.layer_actuation_per_layer_btn.setChecked(per_layer)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_layer_actuation_ui()

    def on_layer_actuation_moved(self, value):
        self.layer_actuation_label.setText(f"{value * 4.0 / 255.0:.2f}mm")

        if not self._layer_actuation_filling and not self.layer_actuation_slider.isSliderDown():
            self._layer_actuation_timer.start()

    def on_layer_actuation_released(self):
        self._layer_actuation_timer.stop()

        # let go where it started: nothing to send
        stored = self.layer_data[self.current_layer]
        value = self.layer_actuation_slider.value()
        if stored.get('normal') == value and stored.get('midi') == value:
            return

        self.commit_layer_actuation()

    def commit_layer_actuation(self):
        """Give the slider's value to the normal keys and the MIDI keys of the layer (of every
        layer when Per layer is off) and store it on the keyboard."""
        ts = self.trigger_settings_ref

        if (ts.mode_enabled if ts else self.enable_per_key_checkbox.isChecked()):
            return      # per-key actuation: each key has its own value

        if ts:
            self.per_layer_enabled = ts.per_layer_enabled      # one layer or all twelve, as the Advanced tab has it

        value = self.layer_actuation_slider.value()

        # The Advanced tab applies the value to the keys of ITS current layer: point it at the
        # layer shown here while the change is made.
        shown_there = ts.current_layer if ts else None
        if ts:
            ts.current_layer = self.current_layer

        try:
            # Moving the two (hidden) sliders does the work: each updates the layer data and
            # queues the change for its kind of key.
            for slider in (self.normal_slider, self.midi_slider):
                if slider.value() == value:
                    slider.valueChanged.emit(value)     # same number as before: still apply it
                else:
                    slider.setValue(value)

            if ts:
                ts.on_save()                            # writes the queued keys to the keyboard
        finally:
            if ts:
                ts.current_layer = shown_there
                ts.refresh_layer_display()

    def on_layer_actuation_per_layer_clicked(self, checked):
        """Switch per-layer actuation. The Advanced tab owns the setting (and asks before
        switching it off, since that copies this layer to all the others)."""
        ts = self.trigger_settings_ref

        if ts:
            shown_there = ts.current_layer
            ts.current_layer = self.current_layer       # 'this layer' means the one shown here
            try:
                ts.on_per_layer_changed(checked)
            finally:
                ts.current_layer = shown_there
            self.per_layer_enabled = ts.per_layer_enabled
        else:
            self.per_layer_checkbox.setChecked(checked)

        self.refresh_layer_actuation_ui()

    def create_actuation_tab(self):
        """Create the Actuation Settings tab"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)
        tab.setLayout(layout)

        # Top row with checkboxes
        top_row_layout = QHBoxLayout()
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        top_row_layout.setSpacing(10)

        self.enable_per_key_checkbox = QCheckBox(tr("QuickActuationWidget", "Enable Per-Key"))
        self.enable_per_key_checkbox.setStyleSheet("QCheckBox { font-weight: bold; font-size: 10px; } QCheckBox::indicator { border: 1px solid palette(mid); background-color: palette(button); width: 13px; height: 13px; } QCheckBox::indicator:checked { border: 1px solid palette(highlight); background-color: palette(highlight); }")
        self.enable_per_key_checkbox.stateChanged.connect(self.on_enable_per_key_toggled)
        top_row_layout.addWidget(self.create_help_label("Enable individual actuation point per key.\nConfigure in the Actuation tab."))
        top_row_layout.addWidget(self.enable_per_key_checkbox)

        top_row_layout.addWidget(self.create_help_label("Enable different actuation points per layer.\nWhen off, same actuation applies to all layers."))
        self.per_layer_checkbox = QCheckBox(tr("QuickActuationWidget", "Enable Per-Layer Actuation"))
        self.per_layer_checkbox.setStyleSheet("QCheckBox { font-weight: bold; font-size: 10px; } QCheckBox::indicator { border: 1px solid palette(mid); background-color: palette(button); width: 13px; height: 13px; } QCheckBox::indicator:checked { border: 1px solid palette(highlight); background-color: palette(highlight); }")
        self.per_layer_checkbox.stateChanged.connect(self.on_per_layer_toggled)
        top_row_layout.addWidget(self.per_layer_checkbox)

        top_row_layout.addStretch()
        layout.addLayout(top_row_layout)

        # Layer indicator (only visible in per-layer mode)
        self.layer_label = QLabel(tr("QuickActuationWidget", "Layer 1"))
        self.layer_label.setStyleSheet("QLabel { font-weight: bold; font-size: 10px; color: palette(dark); }")
        self.layer_label.setVisible(False)
        layout.addWidget(self.layer_label, alignment=Qt.AlignCenter)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Per-key mode message (shown when per-key actuation is enabled)
        self.per_key_message = QLabel(tr("QuickActuationWidget", "Per-key actuation enabled.\nChange per key actuation in the Actuation tab."))
        self.per_key_message.setStyleSheet("QLabel { font-style: italic; font-size: 10px; color: palette(dark); padding: 10px; }")
        self.per_key_message.setAlignment(Qt.AlignCenter)
        self.per_key_message.setVisible(False)
        layout.addWidget(self.per_key_message)

        # Container for sliders (hidden when per-key is enabled)
        self.sliders_container = QWidget()
        sliders_layout = QVBoxLayout()
        sliders_layout.setContentsMargins(0, 0, 0, 0)
        sliders_layout.setSpacing(6)
        self.sliders_container.setLayout(sliders_layout)

        # Normal Keys Actuation slider - ALWAYS VISIBLE
        slider_layout = QHBoxLayout()
        slider_layout.setContentsMargins(0, 0, 0, 0)
        slider_layout.setSpacing(4)
        slider_layout.addWidget(self.create_help_label("Actuation point for non-MIDI keys.\nLower = more sensitive, higher = deeper press required."))
        label = QLabel(tr("QuickActuationWidget", "Normal Keys:"))
        label.setMinimumWidth(75)
        label.setMaximumWidth(75)
        slider_layout.addWidget(label)

        self.normal_slider = QSlider(Qt.Horizontal)
        # Floor at 7 (0.11mm, same as the Trigger Settings slider) — actuation 0
        # is not a valid setting; any wobble past the deadzone would fire.
        self.normal_slider.setMinimum(7)
        self.normal_slider.setMaximum(255)
        self.normal_slider.setValue(127)
        slider_layout.addWidget(self.normal_slider, 1)

        self.normal_value_label = QLabel("2.00mm")
        self.normal_value_label.setMinimumWidth(50)
        self.normal_value_label.setMaximumWidth(50)
        self.normal_value_label.setStyleSheet("QLabel { font-weight: bold; font-size: 9px; }")
        slider_layout.addWidget(self.normal_value_label)

        sliders_layout.addLayout(slider_layout)
        self.normal_slider.valueChanged.connect(
            lambda v: self.on_slider_changed('normal', v, self.normal_value_label)
        )

        # MIDI Keys Actuation slider - now always visible
        midi_slider_layout = QHBoxLayout()
        midi_slider_layout.setContentsMargins(0, 0, 0, 0)
        midi_slider_layout.setSpacing(4)
        midi_slider_layout.addWidget(self.create_help_label("Actuation point for MIDI note keys.\nLower = more sensitive, higher = deeper press required."))
        midi_label = QLabel(tr("QuickActuationWidget", "MIDI Keys:"))
        midi_label.setMinimumWidth(75)
        midi_label.setMaximumWidth(75)
        midi_slider_layout.addWidget(midi_label)

        self.midi_slider = QSlider(Qt.Horizontal)
        # Floor at 7 (0.11mm) — see normal_slider above.
        self.midi_slider.setMinimum(7)
        self.midi_slider.setMaximum(255)
        self.midi_slider.setValue(127)
        midi_slider_layout.addWidget(self.midi_slider, 1)

        self.midi_value_label = QLabel("2.00mm")
        self.midi_value_label.setMinimumWidth(50)
        self.midi_value_label.setMaximumWidth(50)
        self.midi_value_label.setStyleSheet("QLabel { font-weight: bold; font-size: 9px; }")
        midi_slider_layout.addWidget(self.midi_value_label)

        sliders_layout.addLayout(midi_slider_layout)

        self.midi_slider.valueChanged.connect(
            lambda v: self.on_slider_changed('midi', v, self.midi_value_label)
        )

        layout.addWidget(self.sliders_container)

        layout.addStretch()

        # Save button at the bottom
        self.save_btn = QPushButton(tr("QuickActuationWidget", "Save to All Layers"))
        self.save_btn.setMaximumHeight(24)
        self.save_btn.setStyleSheet("padding: 2px 6px; font-size: 9pt;")
        # Not connected: this tab is never shown. The actuation points are
        # saved by the Actuation slider above MIDI Settings and by the Advanced tab.
        layout.addWidget(self.save_btn)

        return tab

    # NOTE: Advanced tab (velocity, aftertouch settings) has been moved to VelocityTab
    # The create_advanced_tab, on_save_advanced, and related handlers are now in velocity_tab.py

    def create_midi_tab(self):
        """Create the MIDI Settings panel (shown directly, no outer tab widget)"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)
        tab.setLayout(layout)

        # Header
        header = QLabel("MIDI Settings")
        header.setStyleSheet("QLabel { font-weight: bold; font-size: 12px; }")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Advanced checkbox and split enable checkboxes at the top
        advanced_row = QHBoxLayout()
        advanced_row.setContentsMargins(0, 0, 0, 0)
        advanced_row.setSpacing(15)

        self.midi_advanced_checkbox = QCheckBox(tr("QuickActuationWidget", "Show Advanced"))
        self.midi_advanced_checkbox.setStyleSheet("QCheckBox { font-size: 10px; } QCheckBox::indicator { border: 1px solid palette(mid); background-color: palette(button); width: 13px; height: 13px; } QCheckBox::indicator:checked { border: 1px solid palette(highlight); background-color: palette(highlight); }")
        self.midi_advanced_checkbox.stateChanged.connect(self.on_midi_advanced_toggled)
        advanced_row.addWidget(self.midi_advanced_checkbox)

        # Enable KeySplit - Checkbox on left, labels on right vertically centered
        keysplit_container = QHBoxLayout()
        keysplit_container.setSpacing(5)
        keysplit_container.setContentsMargins(0, 0, 0, 0)

        self.keysplit_enabled_checkbox = QCheckBox()
        self.keysplit_enabled_checkbox.setStyleSheet("QCheckBox::indicator { border: 1px solid palette(mid); background-color: palette(button); width: 13px; height: 13px; } QCheckBox::indicator:checked { border: 1px solid palette(highlight); background-color: palette(highlight); }")
        self.keysplit_enabled_checkbox.stateChanged.connect(self.on_keysplit_enabled_toggled)
        keysplit_container.addWidget(self.keysplit_enabled_checkbox, 0, Qt.AlignCenter)

        keysplit_labels = QVBoxLayout()
        keysplit_labels.setSpacing(0)
        keysplit_labels.setContentsMargins(0, 0, 0, 0)

        enable_label_ks = QLabel(tr("QuickActuationWidget", "Enable"))
        enable_label_ks.setStyleSheet("QLabel { font-size: 9px; }")
        enable_label_ks.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        keysplit_labels.addWidget(enable_label_ks)

        keysplit_label = QLabel(tr("QuickActuationWidget", "KeySplit"))
        keysplit_label.setStyleSheet("QLabel { font-size: 10px; }")
        keysplit_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        keysplit_labels.addWidget(keysplit_label)

        keysplit_container.addLayout(keysplit_labels)

        keysplit_widget = QWidget()
        keysplit_widget.setLayout(keysplit_container)
        keysplit_widget.setVisible(False)
        advanced_row.addWidget(keysplit_widget)
        self.keysplit_enable_widget = keysplit_widget

        # Enable TripleSplit - Checkbox on left, labels on right vertically centered
        triplesplit_container = QHBoxLayout()
        triplesplit_container.setSpacing(5)
        triplesplit_container.setContentsMargins(0, 0, 0, 0)

        self.triplesplit_enabled_checkbox = QCheckBox()
        self.triplesplit_enabled_checkbox.setStyleSheet("QCheckBox::indicator { border: 1px solid palette(mid); background-color: palette(button); width: 13px; height: 13px; } QCheckBox::indicator:checked { border: 1px solid palette(highlight); background-color: palette(highlight); }")
        self.triplesplit_enabled_checkbox.stateChanged.connect(self.on_triplesplit_enabled_toggled)
        triplesplit_container.addWidget(self.triplesplit_enabled_checkbox, 0, Qt.AlignCenter)

        triplesplit_labels = QVBoxLayout()
        triplesplit_labels.setSpacing(0)
        triplesplit_labels.setContentsMargins(0, 0, 0, 0)

        enable_label_ts = QLabel(tr("QuickActuationWidget", "Enable"))
        enable_label_ts.setStyleSheet("QLabel { font-size: 9px; }")
        enable_label_ts.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        triplesplit_labels.addWidget(enable_label_ts)

        triplesplit_label = QLabel(tr("QuickActuationWidget", "TripleSplit"))
        triplesplit_label.setStyleSheet("QLabel { font-size: 10px; }")
        triplesplit_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        triplesplit_labels.addWidget(triplesplit_label)

        triplesplit_container.addLayout(triplesplit_labels)

        triplesplit_widget = QWidget()
        triplesplit_widget.setLayout(triplesplit_container)
        triplesplit_widget.setVisible(False)
        advanced_row.addWidget(triplesplit_widget)
        self.triplesplit_enable_widget = triplesplit_widget

        advanced_row.addStretch()
        layout.addLayout(advanced_row)

        # Container that will hold tabbed view (always visible)
        self.midi_settings_container = QWidget()
        self.midi_settings_layout = QVBoxLayout()
        self.midi_settings_layout.setContentsMargins(0, 0, 0, 0)
        self.midi_settings_layout.setSpacing(6)
        self.midi_settings_container.setLayout(self.midi_settings_layout)
        layout.addWidget(self.midi_settings_container)

        # Create tabbed container (always shown, tabs dynamically added/removed)
        self.midi_tabs = QTabWidget()
        self.midi_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid palette(mid); }
            QTabBar::tab {
                font-size: 9px;
                padding: 4px 8px;
                min-width: 53px;
            }
            QTabBar {
                qproperty-expanding: true;
            }
        """)

        # Create simple controls for non-advanced mode
        self.simple_midi_widget = self.create_simple_midi_controls()
        self.midi_settings_layout.addWidget(self.simple_midi_widget)

        # Create tabs for advanced mode
        self.basic_tab_widget = self.create_basic_midi_controls()
        self.keysplit_tab_widget = self.create_keysplit_midi_controls()
        self.triplesplit_tab_widget = self.create_triplesplit_midi_controls()

        self.midi_tabs.addTab(self.basic_tab_widget, "Basic")

        self.midi_settings_layout.addWidget(self.midi_tabs)
        self.midi_tabs.setVisible(False)  # Hidden by default, shown when advanced mode is on

        # Basic mode: the simple Channel / Transposition / Articulation controls
        # only. The split options stay as they are on the keyboard, out of sight.
        ui_mode.advanced_only(self.midi_advanced_checkbox, self.keysplit_enable_widget,
                              self.triplesplit_enable_widget, self.midi_tabs)
        ui_mode.on_change(self.apply_mode)

        layout.addStretch()

        return tab

    def create_simple_midi_controls(self):
        """Create simple MIDI controls for non-advanced mode (channel, transpose, velocity preset only)"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(3)
        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)

        # Channel slider
        ch_row = QHBoxLayout()
        ch_row.setContentsMargins(0, 0, 0, 0)
        ch_row.setSpacing(6)

        ch_label = QLabel(tr("QuickActuationWidget", "Channel:"))
        ch_label.setStyleSheet("QLabel { font-size: 14px; }")
        ch_label.setMinimumWidth(90)
        ch_label.setMaximumWidth(90)
        ch_row.addWidget(ch_label)

        self.simple_channel_slider = QSlider(Qt.Horizontal)
        self.simple_channel_slider.setMinimum(0)
        self.simple_channel_slider.setMaximum(15)
        self.simple_channel_slider.setValue(0)
        self.simple_channel_slider.valueChanged.connect(lambda v: self.on_simple_channel_changed(v))
        ch_row.addWidget(self.simple_channel_slider, 1)

        self.simple_channel_label = QLabel("1")
        self.simple_channel_label.setMinimumWidth(35)
        self.simple_channel_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; }")
        self.simple_channel_label.setAlignment(Qt.AlignCenter)
        ch_row.addWidget(self.simple_channel_label)

        layout.addLayout(ch_row)

        # Transposition slider
        trans_row = QHBoxLayout()
        trans_row.setContentsMargins(0, 0, 0, 0)
        trans_row.setSpacing(6)

        trans_label = QLabel(tr("QuickActuationWidget", "Transposition:"))
        trans_label.setStyleSheet("QLabel { font-size: 14px; }")
        trans_label.setMinimumWidth(90)
        trans_label.setMaximumWidth(90)
        trans_row.addWidget(trans_label)

        self.simple_transpose_slider = QSlider(Qt.Horizontal)
        # +/-64: the keyboard's combined transposition range
        self.simple_transpose_slider.setMinimum(-64)
        self.simple_transpose_slider.setMaximum(64)
        self.simple_transpose_slider.setValue(0)
        self.simple_transpose_slider.valueChanged.connect(lambda v: self.on_simple_transpose_changed(v))
        trans_row.addWidget(self.simple_transpose_slider, 1)

        self.simple_transpose_label = QLabel("0")
        self.simple_transpose_label.setMinimumWidth(35)
        self.simple_transpose_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; }")
        self.simple_transpose_label.setAlignment(Qt.AlignCenter)
        trans_row.addWidget(self.simple_transpose_label)

        layout.addLayout(trans_row)

        # Velocity preset (label next to dropdown)
        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(6)

        preset_label = QLabel(tr("QuickActuationWidget", "Articulation:"))
        preset_label.setStyleSheet("QLabel { font-size: 14px; }")
        preset_label.setMinimumWidth(90)
        preset_label.setMaximumWidth(90)
        preset_row.addWidget(preset_label)

        self.simple_velocity_preset_combo = ArrowComboBox()
        self.simple_velocity_preset_combo.setFixedWidth(140)
        self.simple_velocity_preset_combo.setMaximumHeight(35)
        self.simple_velocity_preset_combo.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.simple_velocity_preset_combo.setEditable(True)
        self.simple_velocity_preset_combo.lineEdit().setReadOnly(True)
        self.simple_velocity_preset_combo.lineEdit().setAlignment(Qt.AlignCenter)
        populate_articulation_combo(self.simple_velocity_preset_combo)
        self.simple_velocity_preset_combo.setCurrentIndex(0)
        self.simple_velocity_preset_combo.currentIndexChanged.connect(self.on_velocity_preset_changed)
        preset_row.addWidget(self.simple_velocity_preset_combo)
        preset_row.addStretch()
        layout.addLayout(preset_row)

        return widget

    def create_basic_midi_controls(self):
        """Create basic MIDI controls (channel, transpose, sustain, velocity)"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(3)
        layout.setContentsMargins(10, 10, 10, 10)
        widget.setLayout(layout)

        # Channel slider
        ch_row = QHBoxLayout()
        ch_row.setContentsMargins(0, 0, 0, 0)
        ch_row.setSpacing(6)

        ch_label = QLabel(tr("QuickActuationWidget", "Channel:"))
        ch_label.setStyleSheet("QLabel { font-size: 14px; }")
        ch_label.setMinimumWidth(90)
        ch_label.setMaximumWidth(90)
        ch_row.addWidget(ch_label)

        self.midi_channel_slider = QSlider(Qt.Horizontal)
        self.midi_channel_slider.setMinimum(0)
        self.midi_channel_slider.setMaximum(15)
        self.midi_channel_slider.setValue(0)
        self.midi_channel_slider.valueChanged.connect(lambda v: self.on_midi_channel_changed(v))
        ch_row.addWidget(self.midi_channel_slider, 1)

        self.midi_channel_label = QLabel("1")
        self.midi_channel_label.setMinimumWidth(35)
        self.midi_channel_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; }")
        self.midi_channel_label.setAlignment(Qt.AlignCenter)
        ch_row.addWidget(self.midi_channel_label)

        layout.addLayout(ch_row)

        # Transposition slider
        trans_row = QHBoxLayout()
        trans_row.setContentsMargins(0, 0, 0, 0)
        trans_row.setSpacing(6)

        trans_label = QLabel(tr("QuickActuationWidget", "Transposition:"))
        trans_label.setStyleSheet("QLabel { font-size: 14px; }")
        trans_label.setMinimumWidth(90)
        trans_label.setMaximumWidth(90)
        trans_row.addWidget(trans_label)

        self.midi_transpose_slider = QSlider(Qt.Horizontal)
        # +/-64: the keyboard's combined transposition range
        self.midi_transpose_slider.setMinimum(-64)
        self.midi_transpose_slider.setMaximum(64)
        self.midi_transpose_slider.setValue(0)
        self.midi_transpose_slider.valueChanged.connect(lambda v: self.on_midi_transpose_changed(v))
        trans_row.addWidget(self.midi_transpose_slider, 1)

        self.midi_transpose_label = QLabel("0")
        self.midi_transpose_label.setMinimumWidth(35)
        self.midi_transpose_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; }")
        self.midi_transpose_label.setAlignment(Qt.AlignCenter)
        trans_row.addWidget(self.midi_transpose_label)

        layout.addLayout(trans_row)

        # Velocity min/max hidden — they now come from the Playing Style
        # (velocity preset) only. Widgets kept (invisible) so other code that
        # calls .value()/setValue() in the sync/save paths still works.
        self.midi_velocity_min = QSlider(Qt.Horizontal)
        self.midi_velocity_min.setMinimum(1); self.midi_velocity_min.setMaximum(127); self.midi_velocity_min.setValue(1)
        self.midi_velocity_min.hide()
        self.midi_velocity_min_label = QLabel("1"); self.midi_velocity_min_label.hide()
        self.midi_velocity_max = QSlider(Qt.Horizontal)
        self.midi_velocity_max.setMinimum(1); self.midi_velocity_max.setMaximum(127); self.midi_velocity_max.setValue(127)
        self.midi_velocity_max.hide()
        self.midi_velocity_max_label = QLabel("127"); self.midi_velocity_max_label.hide()

        # Velocity Curve (label next to dropdown)
        curve_row = QHBoxLayout()
        curve_row.setContentsMargins(0, 0, 0, 0)
        curve_row.setSpacing(6)

        curve_label = QLabel(tr("QuickActuationWidget", "Articulation:"))
        curve_label.setStyleSheet("QLabel { font-size: 14px; }")
        curve_label.setMinimumWidth(100)
        curve_label.setMaximumWidth(100)
        curve_row.addWidget(curve_label)

        self.midi_velocity_curve = ArrowComboBox()
        self.midi_velocity_curve.setMaximumWidth(180)
        self.midi_velocity_curve.setMaximumHeight(30)
        self.midi_velocity_curve.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.midi_velocity_curve.setEditable(True)
        self.midi_velocity_curve.lineEdit().setReadOnly(True)
        self.midi_velocity_curve.lineEdit().setAlignment(Qt.AlignCenter)
        populate_articulation_combo(self.midi_velocity_curve)
        self.midi_velocity_curve.setCurrentIndex(0)
        self.midi_velocity_curve.currentIndexChanged.connect(self.on_base_velocity_curve_changed)
        curve_row.addWidget(self.midi_velocity_curve)
        curve_row.addStretch()
        layout.addLayout(curve_row)

        # 5px spacing between velocity curve and sustain
        layout.addSpacing(5)

        # Sustain (label next to dropdown) - below velocity min/max - hidden unless splits enabled
        sustain_row = QHBoxLayout()
        sustain_row.setContentsMargins(0, 0, 0, 0)
        sustain_row.setSpacing(6)

        sustain_label = QLabel(tr("QuickActuationWidget", "Sustain:"))
        sustain_label.setStyleSheet("QLabel { font-size: 14px; }")
        sustain_label.setMinimumWidth(100)
        sustain_label.setMaximumWidth(100)
        sustain_row.addWidget(sustain_label)

        self.midi_sustain_combo = ArrowComboBox()
        self.midi_sustain_combo.setMaximumWidth(120)
        self.midi_sustain_combo.setMaximumHeight(30)
        self.midi_sustain_combo.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.midi_sustain_combo.setEditable(True)
        self.midi_sustain_combo.lineEdit().setReadOnly(True)
        self.midi_sustain_combo.lineEdit().setAlignment(Qt.AlignCenter)
        self.midi_sustain_combo.addItem("Allow", 0)
        self.midi_sustain_combo.addItem("Ignore", 1)
        self.midi_sustain_combo.setCurrentIndex(0)
        self.midi_sustain_combo.currentIndexChanged.connect(self.on_base_sustain_changed)
        sustain_row.addWidget(self.midi_sustain_combo)
        sustain_row.addStretch()

        self.midi_sustain_widget = QWidget()
        self.midi_sustain_widget.setLayout(sustain_row)
        self.midi_sustain_widget.setVisible(False)  # Hidden by default
        layout.addWidget(self.midi_sustain_widget)

        return widget

    def create_keysplit_midi_controls(self):
        """Create KeySplit MIDI controls"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(3)
        layout.setContentsMargins(10, 10, 10, 10)
        widget.setLayout(layout)

        # Channel slider
        ch_row = QHBoxLayout()
        ch_row.setContentsMargins(0, 0, 0, 0)
        ch_row.setSpacing(6)

        ch_label = QLabel(tr("QuickActuationWidget", "Channel:"))
        ch_label.setStyleSheet("QLabel { font-size: 14px; }")
        ch_label.setMinimumWidth(90)
        ch_label.setMaximumWidth(90)
        ch_row.addWidget(ch_label)

        self.keysplit_channel_slider = QSlider(Qt.Horizontal)
        self.keysplit_channel_slider.setMinimum(0)
        self.keysplit_channel_slider.setMaximum(15)
        self.keysplit_channel_slider.setValue(0)
        self.keysplit_channel_slider.valueChanged.connect(lambda v: self.on_keysplit_channel_changed(v))
        ch_row.addWidget(self.keysplit_channel_slider, 1)

        self.keysplit_channel_label = QLabel("1")
        self.keysplit_channel_label.setMinimumWidth(35)
        self.keysplit_channel_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; }")
        self.keysplit_channel_label.setAlignment(Qt.AlignCenter)
        ch_row.addWidget(self.keysplit_channel_label)

        layout.addLayout(ch_row)

        # Transposition slider
        trans_row = QHBoxLayout()
        trans_row.setContentsMargins(0, 0, 0, 0)
        trans_row.setSpacing(6)

        trans_label = QLabel(tr("QuickActuationWidget", "Transposition:"))
        trans_label.setStyleSheet("QLabel { font-size: 14px; }")
        trans_label.setMinimumWidth(90)
        trans_label.setMaximumWidth(90)
        trans_row.addWidget(trans_label)

        self.keysplit_transpose_slider = QSlider(Qt.Horizontal)
        # +/-64: the keyboard's combined transposition range
        self.keysplit_transpose_slider.setMinimum(-64)
        self.keysplit_transpose_slider.setMaximum(64)
        self.keysplit_transpose_slider.setValue(0)
        self.keysplit_transpose_slider.valueChanged.connect(lambda v: self.on_keysplit_transpose_changed(v))
        trans_row.addWidget(self.keysplit_transpose_slider, 1)

        self.keysplit_transpose_label = QLabel("0")
        self.keysplit_transpose_label.setMinimumWidth(35)
        self.keysplit_transpose_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; }")
        self.keysplit_transpose_label.setAlignment(Qt.AlignCenter)
        trans_row.addWidget(self.keysplit_transpose_label)

        layout.addLayout(trans_row)

        # Keysplit velocity min/max hidden — come from the Playing Style only.
        self.keysplit_velocity_min = QSlider(Qt.Horizontal)
        self.keysplit_velocity_min.setMinimum(1); self.keysplit_velocity_min.setMaximum(127); self.keysplit_velocity_min.setValue(1)
        self.keysplit_velocity_min.hide()
        self.keysplit_velocity_min_label = QLabel("1"); self.keysplit_velocity_min_label.hide()
        self.keysplit_velocity_max = QSlider(Qt.Horizontal)
        self.keysplit_velocity_max.setMinimum(1); self.keysplit_velocity_max.setMaximum(127); self.keysplit_velocity_max.setValue(127)
        self.keysplit_velocity_max.hide()
        self.keysplit_velocity_max_label = QLabel("127"); self.keysplit_velocity_max_label.hide()

        # Playing Style (velocity curve dropdown)
        ks_curve_row = QHBoxLayout()
        ks_curve_row.setContentsMargins(0, 0, 0, 0)
        ks_curve_row.setSpacing(6)

        ks_curve_label = QLabel(tr("QuickActuationWidget", "Articulation:"))
        ks_curve_label.setStyleSheet("QLabel { font-size: 14px; }")
        ks_curve_label.setMinimumWidth(100)
        ks_curve_label.setMaximumWidth(100)
        ks_curve_row.addWidget(ks_curve_label)

        self.keysplit_velocity_curve = ArrowComboBox()
        self.keysplit_velocity_curve.setMaximumWidth(180)
        self.keysplit_velocity_curve.setMaximumHeight(30)
        self.keysplit_velocity_curve.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.keysplit_velocity_curve.setEditable(True)
        self.keysplit_velocity_curve.lineEdit().setReadOnly(True)
        self.keysplit_velocity_curve.lineEdit().setAlignment(Qt.AlignCenter)
        populate_articulation_combo(self.keysplit_velocity_curve)
        self.keysplit_velocity_curve.setCurrentIndex(2)  # Default: Linear
        self.keysplit_velocity_curve.currentIndexChanged.connect(self.on_keysplit_velocity_curve_changed)
        ks_curve_row.addWidget(self.keysplit_velocity_curve)
        ks_curve_row.addStretch()
        layout.addLayout(ks_curve_row)

        # Sustain (label next to dropdown)
        sustain_row = QHBoxLayout()
        sustain_row.setContentsMargins(0, 0, 0, 0)
        sustain_row.setSpacing(6)

        sustain_label = QLabel(tr("QuickActuationWidget", "Sustain:"))
        sustain_label.setStyleSheet("QLabel { font-size: 14px; }")
        sustain_label.setMinimumWidth(100)
        sustain_label.setMaximumWidth(100)
        sustain_row.addWidget(sustain_label)

        self.keysplit_sustain_combo = ArrowComboBox()
        self.keysplit_sustain_combo.setMaximumWidth(120)
        self.keysplit_sustain_combo.setMaximumHeight(30)
        self.keysplit_sustain_combo.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.keysplit_sustain_combo.setEditable(True)
        self.keysplit_sustain_combo.lineEdit().setReadOnly(True)
        self.keysplit_sustain_combo.lineEdit().setAlignment(Qt.AlignCenter)
        self.keysplit_sustain_combo.addItem("Allow", 0)
        self.keysplit_sustain_combo.addItem("Ignore", 1)
        self.keysplit_sustain_combo.setCurrentIndex(0)
        self.keysplit_sustain_combo.currentIndexChanged.connect(self.on_keysplit_sustain_changed)
        sustain_row.addWidget(self.keysplit_sustain_combo)
        sustain_row.addStretch()
        layout.addLayout(sustain_row)

        # Auto-Notes (smartchord/delay/dynamic-chord/arpeggiator/octave-doubler gate)
        autonotes_row = QHBoxLayout()
        autonotes_row.setContentsMargins(0, 0, 0, 0)
        autonotes_row.setSpacing(6)

        autonotes_label = QLabel(tr("QuickActuationWidget", "Auto-Notes:"))
        autonotes_label.setStyleSheet("QLabel { font-size: 14px; }")
        autonotes_label.setMinimumWidth(100)
        autonotes_label.setMaximumWidth(100)
        autonotes_row.addWidget(autonotes_label)

        self.keysplit_autonotes_combo = ArrowComboBox()
        self.keysplit_autonotes_combo.setMaximumWidth(120)
        self.keysplit_autonotes_combo.setMaximumHeight(30)
        self.keysplit_autonotes_combo.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.keysplit_autonotes_combo.setEditable(True)
        self.keysplit_autonotes_combo.lineEdit().setReadOnly(True)
        self.keysplit_autonotes_combo.lineEdit().setAlignment(Qt.AlignCenter)
        self.keysplit_autonotes_combo.addItem("Allow", 0)
        self.keysplit_autonotes_combo.addItem("Ignore", 1)
        self.keysplit_autonotes_combo.setCurrentIndex(0)
        self.keysplit_autonotes_combo.setToolTip(
            "Ignore = keysplit keys play ONLY their plain pressed note - no smartchord harmony,\n"
            "MIDI-delay echoes, dynamic chords, arpeggiator participation or octave-doubler note.\n"
            "Looping is unaffected. Applies only while the keysplit zone is enabled; while it is\n"
            "off, keysplit keys follow the base zone's Auto-Notes setting.")
        self.keysplit_autonotes_combo.currentIndexChanged.connect(self.on_keysplit_autonotes_changed)
        autonotes_row.addWidget(self.keysplit_autonotes_combo)
        autonotes_row.addStretch()
        layout.addLayout(autonotes_row)

        return widget

    def create_triplesplit_midi_controls(self):
        """Create TripleSplit MIDI controls"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(3)
        layout.setContentsMargins(10, 10, 10, 10)
        widget.setLayout(layout)

        # Channel slider
        ch_row = QHBoxLayout()
        ch_row.setContentsMargins(0, 0, 0, 0)
        ch_row.setSpacing(6)

        ch_label = QLabel(tr("QuickActuationWidget", "Channel:"))
        ch_label.setStyleSheet("QLabel { font-size: 14px; }")
        ch_label.setMinimumWidth(90)
        ch_label.setMaximumWidth(90)
        ch_row.addWidget(ch_label)

        self.triplesplit_channel_slider = QSlider(Qt.Horizontal)
        self.triplesplit_channel_slider.setMinimum(0)
        self.triplesplit_channel_slider.setMaximum(15)
        self.triplesplit_channel_slider.setValue(0)
        self.triplesplit_channel_slider.valueChanged.connect(lambda v: self.on_triplesplit_channel_changed(v))
        ch_row.addWidget(self.triplesplit_channel_slider, 1)

        self.triplesplit_channel_label = QLabel("1")
        self.triplesplit_channel_label.setMinimumWidth(35)
        self.triplesplit_channel_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; }")
        self.triplesplit_channel_label.setAlignment(Qt.AlignCenter)
        ch_row.addWidget(self.triplesplit_channel_label)

        layout.addLayout(ch_row)

        # Transposition slider
        trans_row = QHBoxLayout()
        trans_row.setContentsMargins(0, 0, 0, 0)
        trans_row.setSpacing(6)

        trans_label = QLabel(tr("QuickActuationWidget", "Transposition:"))
        trans_label.setStyleSheet("QLabel { font-size: 14px; }")
        trans_label.setMinimumWidth(90)
        trans_label.setMaximumWidth(90)
        trans_row.addWidget(trans_label)

        self.triplesplit_transpose_slider = QSlider(Qt.Horizontal)
        # +/-64: the keyboard's combined transposition range
        self.triplesplit_transpose_slider.setMinimum(-64)
        self.triplesplit_transpose_slider.setMaximum(64)
        self.triplesplit_transpose_slider.setValue(0)
        self.triplesplit_transpose_slider.valueChanged.connect(lambda v: self.on_triplesplit_transpose_changed(v))
        trans_row.addWidget(self.triplesplit_transpose_slider, 1)

        self.triplesplit_transpose_label = QLabel("0")
        self.triplesplit_transpose_label.setMinimumWidth(35)
        self.triplesplit_transpose_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; }")
        self.triplesplit_transpose_label.setAlignment(Qt.AlignCenter)
        trans_row.addWidget(self.triplesplit_transpose_label)

        layout.addLayout(trans_row)

        # Triplesplit velocity min/max hidden — come from the Playing Style only.
        self.triplesplit_velocity_min = QSlider(Qt.Horizontal)
        self.triplesplit_velocity_min.setMinimum(1); self.triplesplit_velocity_min.setMaximum(127); self.triplesplit_velocity_min.setValue(1)
        self.triplesplit_velocity_min.hide()
        self.triplesplit_velocity_min_label = QLabel("1"); self.triplesplit_velocity_min_label.hide()
        self.triplesplit_velocity_max = QSlider(Qt.Horizontal)
        self.triplesplit_velocity_max.setMinimum(1); self.triplesplit_velocity_max.setMaximum(127); self.triplesplit_velocity_max.setValue(127)
        self.triplesplit_velocity_max.hide()
        self.triplesplit_velocity_max_label = QLabel("127"); self.triplesplit_velocity_max_label.hide()

        # Playing Style (velocity curve dropdown)
        ts_curve_row = QHBoxLayout()
        ts_curve_row.setContentsMargins(0, 0, 0, 0)
        ts_curve_row.setSpacing(6)

        ts_curve_label = QLabel(tr("QuickActuationWidget", "Articulation:"))
        ts_curve_label.setStyleSheet("QLabel { font-size: 14px; }")
        ts_curve_label.setMinimumWidth(100)
        ts_curve_label.setMaximumWidth(100)
        ts_curve_row.addWidget(ts_curve_label)

        self.triplesplit_velocity_curve = ArrowComboBox()
        self.triplesplit_velocity_curve.setMaximumWidth(180)
        self.triplesplit_velocity_curve.setMaximumHeight(30)
        self.triplesplit_velocity_curve.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.triplesplit_velocity_curve.setEditable(True)
        self.triplesplit_velocity_curve.lineEdit().setReadOnly(True)
        self.triplesplit_velocity_curve.lineEdit().setAlignment(Qt.AlignCenter)
        populate_articulation_combo(self.triplesplit_velocity_curve)
        self.triplesplit_velocity_curve.setCurrentIndex(2)  # Default: Linear
        self.triplesplit_velocity_curve.currentIndexChanged.connect(self.on_triplesplit_velocity_curve_changed)
        ts_curve_row.addWidget(self.triplesplit_velocity_curve)
        ts_curve_row.addStretch()
        layout.addLayout(ts_curve_row)

        # Sustain (label next to dropdown)
        sustain_row = QHBoxLayout()
        sustain_row.setContentsMargins(0, 0, 0, 0)
        sustain_row.setSpacing(6)

        sustain_label = QLabel(tr("QuickActuationWidget", "Sustain:"))
        sustain_label.setStyleSheet("QLabel { font-size: 14px; }")
        sustain_label.setMinimumWidth(100)
        sustain_label.setMaximumWidth(100)
        sustain_row.addWidget(sustain_label)

        self.triplesplit_sustain_combo = ArrowComboBox()
        self.triplesplit_sustain_combo.setMaximumWidth(120)
        self.triplesplit_sustain_combo.setMaximumHeight(30)
        self.triplesplit_sustain_combo.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.triplesplit_sustain_combo.setEditable(True)
        self.triplesplit_sustain_combo.lineEdit().setReadOnly(True)
        self.triplesplit_sustain_combo.lineEdit().setAlignment(Qt.AlignCenter)
        self.triplesplit_sustain_combo.addItem("Allow", 0)
        self.triplesplit_sustain_combo.addItem("Ignore", 1)
        self.triplesplit_sustain_combo.setCurrentIndex(0)
        self.triplesplit_sustain_combo.currentIndexChanged.connect(self.on_triplesplit_sustain_changed)
        sustain_row.addWidget(self.triplesplit_sustain_combo)
        sustain_row.addStretch()
        layout.addLayout(sustain_row)

        # Auto-Notes (smartchord/delay/dynamic-chord/arpeggiator/octave-doubler gate)
        autonotes_row = QHBoxLayout()
        autonotes_row.setContentsMargins(0, 0, 0, 0)
        autonotes_row.setSpacing(6)

        autonotes_label = QLabel(tr("QuickActuationWidget", "Auto-Notes:"))
        autonotes_label.setStyleSheet("QLabel { font-size: 14px; }")
        autonotes_label.setMinimumWidth(100)
        autonotes_label.setMaximumWidth(100)
        autonotes_row.addWidget(autonotes_label)

        self.triplesplit_autonotes_combo = ArrowComboBox()
        self.triplesplit_autonotes_combo.setMaximumWidth(120)
        self.triplesplit_autonotes_combo.setMaximumHeight(30)
        self.triplesplit_autonotes_combo.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.triplesplit_autonotes_combo.setEditable(True)
        self.triplesplit_autonotes_combo.lineEdit().setReadOnly(True)
        self.triplesplit_autonotes_combo.lineEdit().setAlignment(Qt.AlignCenter)
        self.triplesplit_autonotes_combo.addItem("Allow", 0)
        self.triplesplit_autonotes_combo.addItem("Ignore", 1)
        self.triplesplit_autonotes_combo.setCurrentIndex(0)
        self.triplesplit_autonotes_combo.setToolTip(
            "Ignore = triplesplit keys play ONLY their plain pressed note - no smartchord harmony,\n"
            "MIDI-delay echoes, dynamic chords, arpeggiator participation or octave-doubler note.\n"
            "Looping is unaffected. Applies only while the triplesplit zone is enabled; while it is\n"
            "off, triplesplit keys follow the base zone's Auto-Notes setting.")
        self.triplesplit_autonotes_combo.currentIndexChanged.connect(self.on_triplesplit_autonotes_changed)
        autonotes_row.addWidget(self.triplesplit_autonotes_combo)
        autonotes_row.addStretch()
        layout.addLayout(autonotes_row)

        return widget
        
    def update_per_key_ui_state(self, per_key_enabled):
        """Update UI state when per-key mode changes"""
        # Show/hide sliders and message based on per-key state
        self.sliders_container.setVisible(not per_key_enabled)
        self.per_key_message.setVisible(per_key_enabled)
        # Disable save button when per-key is enabled (managed in Trigger Settings)
        self.save_btn.setEnabled(not per_key_enabled)
        self.refresh_layer_actuation_ui()
    
    def on_per_layer_toggled(self):
        """Handle per-layer mode toggle"""
        self.per_layer_enabled = self.per_layer_checkbox.isChecked()
        self.refresh_layer_actuation_ui()

        # Show/hide layer label
        self.layer_label.setVisible(self.per_layer_enabled)

        # Update save button text
        if self.per_layer_enabled:
            self.save_btn.setText(tr("QuickActuationWidget", f"Save to Layer {self.current_layer + 1}"))
            # Load current layer's settings from memory
            self.load_layer_from_memory()
        else:
            self.save_btn.setText(tr("QuickActuationWidget", "Save to All Layers"))

        # Synchronize with Trigger Settings tab
        if self.trigger_settings_ref:
            self.trigger_settings_ref.syncing = True
            self.trigger_settings_ref.per_layer_checkbox.setChecked(self.per_layer_enabled)
            self.trigger_settings_ref.syncing = False

    def on_enable_per_key_toggled(self):
        """Handle enable per-key checkbox toggle"""
        if self.syncing:
            return

        per_key_enabled = self.enable_per_key_checkbox.isChecked()

        # Update UI state based on per-key mode
        self.update_per_key_ui_state(per_key_enabled)

        # Sync with Trigger Settings tab
        if self.trigger_settings_ref:
            self.trigger_settings_ref.syncing = True
            self.trigger_settings_ref.enable_checkbox.setChecked(per_key_enabled)
            self.trigger_settings_ref.syncing = False
            # Trigger the enable_changed handler to update trigger settings UI
            self.trigger_settings_ref.on_enable_changed(Qt.Checked if per_key_enabled else Qt.Unchecked)

        if per_key_enabled:
            # Show notification and switch to trigger settings tab
            QMessageBox.information(
                self,
                tr("QuickActuationWidget", "Per-Key Actuation Enabled"),
                tr("QuickActuationWidget", "Per-key actuation is now enabled.\nUse the Actuation tab to configure individual keys.")
            )
            # Emit signal to request tab switch
            self.enable_per_key_requested.emit()

    # Factory preset vel_min/vel_max settings - must match firmware factory_preset_zones[]
    FACTORY_PRESET_VEL = {
        0: (1, 60), # Softest
        1: (1, 127), # Soft
        2: (1, 127), # Basic
        3: (1, 127), # Hard
        4: (60, 127), # Hardest
        5: (1, 127), # Soft Leg
        6: (1, 127), # Basic Leg
        7: (1, 127), # Hard Leg
        8: (1, 127), # Sens Leg
        9: (126, 127), # Fixed Vol
        10: (1, 127), # Drums Easy
        11: (1, 127), # Drums Soft
        12: (1, 127), # Drums Basic
        13: (1, 127), # Drums Hard
        14: (1, 127), # Sensitive Soft
        15: (1, 127), # Sensitive
        16: (30, 127), # Sensitive Hard
        17: (1, 127), # Drums Sens
        18: (46, 127), # Ultra Sens
        19: (126, 127), # Fixed Sens
        20: (70, 127), # Two Toned
        21: (1, 127), # Reverse
        22: (1, 127), # Random Highlights
    }

    def send_param(self, param_id, value):
        """Send a single parameter to the keyboard live via HID"""
        try:
            if self.device and isinstance(self.device, VialKeyboard):
                self.device.keyboard.set_keyboard_param_single(param_id, value)
        except Exception:
            pass

    def on_simple_channel_changed(self, value):
        """Handle simple channel slider changes"""
        self.simple_channel_label.setText(str(value + 1))
        if not self.syncing:
            self.midi_settings['channel'] = value
            # Sync to advanced control
            self.syncing = True
            self.midi_channel_slider.setValue(value)
            self.midi_channel_label.setText(str(value + 1))
            self.syncing = False
            self.send_param(PARAM_CHANNEL_NUMBER, value)

    def on_simple_transpose_changed(self, value):
        """Handle simple transpose slider changes"""
        self.simple_transpose_label.setText(f"{'+' if value >= 0 else ''}{value}")
        if not self.syncing:
            self.midi_settings['transpose'] = value
            # Sync to advanced control
            self.syncing = True
            self.midi_transpose_slider.setValue(value)
            self.midi_transpose_label.setText(f"{'+' if value >= 0 else ''}{value}")
            self.syncing = False
            self.send_param(PARAM_TRANSPOSE_NUMBER, value & 0xFF)

    def on_midi_channel_changed(self, value):
        """Handle MIDI channel slider changes"""
        self.midi_channel_label.setText(str(value + 1))
        if not self.syncing:
            self.save_midi_ui_to_memory()
            # Sync to simple control
            self.syncing = True
            self.simple_channel_slider.setValue(value)
            self.simple_channel_label.setText(str(value + 1))
            self.syncing = False
            self.send_param(PARAM_CHANNEL_NUMBER, value)

    def on_midi_transpose_changed(self, value):
        """Handle MIDI transpose slider changes"""
        self.midi_transpose_label.setText(f"{'+' if value >= 0 else ''}{value}")
        if not self.syncing:
            self.save_midi_ui_to_memory()
            # Sync to simple control
            self.syncing = True
            self.simple_transpose_slider.setValue(value)
            self.simple_transpose_label.setText(f"{'+' if value >= 0 else ''}{value}")
            self.syncing = False
            self.send_param(PARAM_TRANSPOSE_NUMBER, value & 0xFF)

    def on_keysplit_channel_changed(self, value):
        """Handle keysplit channel slider changes"""
        self.keysplit_channel_label.setText(str(value + 1))
        if not self.syncing:
            self.save_midi_ui_to_memory()
            self.send_param(PARAM_KEYSPLITCHANNEL, value)

    def on_keysplit_transpose_changed(self, value):
        """Handle keysplit transpose slider changes"""
        self.keysplit_transpose_label.setText(f"{'+' if value >= 0 else ''}{value}")
        if not self.syncing:
            self.save_midi_ui_to_memory()
            self.send_param(PARAM_TRANSPOSE_NUMBER2, value & 0xFF)

    def on_triplesplit_channel_changed(self, value):
        """Handle triplesplit channel slider changes"""
        self.triplesplit_channel_label.setText(str(value + 1))
        if not self.syncing:
            self.save_midi_ui_to_memory()
            self.send_param(PARAM_KEYSPLIT2CHANNEL, value)

    def on_triplesplit_transpose_changed(self, value):
        """Handle triplesplit transpose slider changes"""
        self.triplesplit_transpose_label.setText(f"{'+' if value >= 0 else ''}{value}")
        if not self.syncing:
            self.save_midi_ui_to_memory()
            self.send_param(PARAM_TRANSPOSE_NUMBER3, value & 0xFF)
    
    def on_slider_changed(self, key, value, label):
        """Handle slider changes"""
        if self.syncing:
            return

        if key in ['normal', 'midi']:
            label.setText(f"{value * 4.0 / 255.0:.2f}mm")
        elif key == 'midi_rapid_vel':
            label.setText(f"±{value}")
        else:
            label.setText(str(value))

        # Update memory
        self.save_ui_to_memory()

        # Sync to TriggerSettingsTab if reference exists
        if self.trigger_settings_ref and key in ['normal', 'midi']:
            ts = self.trigger_settings_ref
            ts.syncing = True

            if key == 'normal':
                ts.global_normal_slider.set_actuation(value)
                ts.global_normal_value_label.setText(f"Act: {value * 4.0 / 255.0:.2f}mm")
            elif key == 'midi':
                ts.global_midi_slider.set_actuation(value)
                ts.global_midi_value_label.setText(f"Act: {value * 4.0 / 255.0:.2f}mm")

            # Initialize pending_layer_data if not already
            if ts.pending_layer_data is None:
                ts.pending_layer_data = []
                for layer_data in ts.layer_data:
                    ts.pending_layer_data.append(layer_data.copy())

            # Update pending_layer_data for current layer (or all layers if not per-layer)
            if self.per_layer_enabled:
                ts.pending_layer_data[self.current_layer][key] = value
            else:
                for i in range(12):
                    ts.pending_layer_data[i][key] = value

            # Also update layer_data to keep in sync
            if self.per_layer_enabled:
                ts.layer_data[self.current_layer][key] = value
            else:
                for i in range(12):
                    ts.layer_data[i][key] = value

            # Apply actuation to matching keys (normal or MIDI)
            ts.apply_actuation_to_keys(is_midi=(key == 'midi'), value=value)

            # Mark as having unsaved changes
            ts.has_unsaved_changes = True
            ts.save_btn.setEnabled(True)

            # Update display
            ts.refresh_layer_display()
            ts.update_actuation_visualizer()

            ts.syncing = False
    
    def on_combo_changed(self):
        """Handle combo box changes"""
        if not self.syncing:
            self.save_ui_to_memory()
    
    def save_ui_to_memory(self):
        """Save current UI state to memory (for current layer if per-layer, all if master)"""
        # NOTE: Velocity mode is now managed in VelocityTab, not here

        if self.per_layer_enabled:
            # Update only the basic actuation keys
            self.layer_data[self.current_layer].update({
                'normal': self.normal_slider.value(),
                'midi': self.midi_slider.value()
            })
        else:
            # Save to all layers (master mode)
            data = {
                'normal': self.normal_slider.value(),
                'midi': self.midi_slider.value()
            }
            for i in range(12):
                self.layer_data[i].update(data)
    
    def load_layer_from_memory(self):
        """Load layer settings from memory cache"""
        self.syncing = True

        data = self.layer_data[self.current_layer]

        # Set sliders and immediately update labels
        self.normal_slider.setValue(data['normal'])
        self.normal_value_label.setText(f"{data['normal'] * 4.0 / 255.0:.2f}mm")

        self.midi_slider.setValue(data['midi'])
        self.midi_value_label.setText(f"{data['midi'] * 4.0 / 255.0:.2f}mm")

        # NOTE: Velocity mode is now managed in VelocityTab, not here

        self.syncing = False
        self.refresh_layer_actuation_ui()
    
    def on_base_velocity_curve_changed(self):
        """Handle base zone velocity curve changes - send live with vel_min/vel_max"""
        if not self.syncing:
            curve_index = self.midi_velocity_curve.currentData()
            if curve_index is not None:
                self.send_param(PARAM_HE_VELOCITY_CURVE, curve_index)
                self._apply_curve_vel_range(curve_index)
                self.save_midi_ui_to_memory()

    def on_keysplit_velocity_curve_changed(self):
        """Handle keysplit velocity curve changes - send live"""
        if not self.syncing:
            curve_index = self.keysplit_velocity_curve.currentData()
            if curve_index is not None:
                self.send_param(PARAM_KEYSPLIT_HE_VELOCITY_CURVE, curve_index)
                self._apply_split_curve_vel_range('keysplit', curve_index)
                self.save_midi_ui_to_memory()

    def on_triplesplit_velocity_curve_changed(self):
        """Handle triplesplit velocity curve changes - send live"""
        if not self.syncing:
            curve_index = self.triplesplit_velocity_curve.currentData()
            if curve_index is not None:
                self.send_param(PARAM_TRIPLESPLIT_HE_VELOCITY_CURVE, curve_index)
                self._apply_split_curve_vel_range('triplesplit', curve_index)
                self.save_midi_ui_to_memory()

    def _apply_split_curve_vel_range(self, split_type, curve_index):
        """Look up vel_min/vel_max for a keysplit/triplesplit curve and update sliders."""
        vel_min = None
        vel_max = None

        if curve_index in self.FACTORY_PRESET_VEL:
            vel_min, vel_max = self.FACTORY_PRESET_VEL[curve_index]
        elif 19 <= curve_index <= 68:
            slot = curve_index - 19
            try:
                if self.device and isinstance(self.device, VialKeyboard):
                    result = self.device.keyboard.get_velocity_preset(slot)
                    if result:
                        base = result.get('base', result)
                        vel_min = base.get('velocity_min', 1)
                        vel_max = base.get('velocity_max', 127)
            except Exception:
                pass

        if vel_min is not None and vel_max is not None:
            self.syncing = True
            if split_type == 'keysplit':
                self.keysplit_velocity_min.setValue(vel_min)
                self.keysplit_velocity_min_label.setText(str(vel_min))
                self.keysplit_velocity_max.setValue(vel_max)
                self.keysplit_velocity_max_label.setText(str(vel_max))
            else:
                self.triplesplit_velocity_min.setValue(vel_min)
                self.triplesplit_velocity_min_label.setText(str(vel_min))
                self.triplesplit_velocity_max.setValue(vel_max)
                self.triplesplit_velocity_max_label.setText(str(vel_max))
            self.syncing = False

    def on_base_sustain_changed(self):
        """Handle base zone sustain changes - send live"""
        if not self.syncing:
            sustain_val = self.midi_sustain_combo.currentData()
            if sustain_val is not None:
                self.save_midi_ui_to_memory()
                self.send_param(PARAM_BASE_SUSTAIN, sustain_val)

    def on_keysplit_sustain_changed(self):
        """Handle keysplit sustain changes - send live"""
        if not self.syncing:
            sustain_val = self.keysplit_sustain_combo.currentData()
            if sustain_val is not None:
                self.save_midi_ui_to_memory()
                self.send_param(PARAM_KEYSPLIT_SUSTAIN, sustain_val)

    def on_triplesplit_sustain_changed(self):
        """Handle triplesplit sustain changes - send live"""
        if not self.syncing:
            sustain_val = self.triplesplit_sustain_combo.currentData()
            if sustain_val is not None:
                self.save_midi_ui_to_memory()
                self.send_param(PARAM_TRIPLESPLIT_SUSTAIN, sustain_val)

    def on_keysplit_autonotes_changed(self):
        """Handle keysplit Auto-Notes allow/ignore changes - send live"""
        if not self.syncing:
            val = self.keysplit_autonotes_combo.currentData()
            if val is not None:
                self.save_midi_ui_to_memory()
                self.send_param(PARAM_KEYSPLIT_SMARTCHORD_IGNORE, val)

    def on_triplesplit_autonotes_changed(self):
        """Handle triplesplit Auto-Notes allow/ignore changes - send live"""
        if not self.syncing:
            val = self.triplesplit_autonotes_combo.currentData()
            if val is not None:
                self.save_midi_ui_to_memory()
                self.send_param(PARAM_TRIPLESPLIT_SMARTCHORD_IGNORE, val)

    def on_velocity_preset_changed(self):
        """Handle velocity preset changes - update curve index and send live with vel_min/vel_max"""
        if self.syncing:
            return

        curve_index = self.simple_velocity_preset_combo.currentData()
        if curve_index is not None:
            self.midi_settings['velocity_curve'] = curve_index
            self.midi_settings['velocity_preset'] = curve_index

            # Sync to advanced velocity curve control
            self.syncing = True
            for i in range(self.midi_velocity_curve.count()):
                if self.midi_velocity_curve.itemData(i) == curve_index:
                    self.midi_velocity_curve.setCurrentIndex(i)
                    break
            self.syncing = False

            self.send_param(PARAM_HE_VELOCITY_CURVE, curve_index)
            self._apply_curve_vel_range(curve_index)

    def _apply_curve_vel_range(self, curve_index):
        """Look up vel_min/vel_max for a curve and apply to UI + keyboard.
        Factory curves (0-22) use hardcoded table. User curves (23-72) load from device."""
        vel_min = None
        vel_max = None

        if curve_index in self.FACTORY_PRESET_VEL:
            vel_min, vel_max = self.FACTORY_PRESET_VEL[curve_index]
        elif curve_index >= 19 and curve_index <= 68:
            # User curve - load from device
            slot = curve_index - 19
            try:
                if self.device and isinstance(self.device, VialKeyboard):
                    result = self.device.keyboard.get_velocity_preset(slot)
                    if result:
                        base = result.get('base', result)
                        vel_min = base.get('velocity_min', 1)
                        vel_max = base.get('velocity_max', 127)
            except Exception:
                pass

        if vel_min is not None and vel_max is not None:
            # Update sliders only - firmware already set vel_min/vel_max
            # via velocity_preset_apply() when we sent PARAM_HE_VELOCITY_CURVE
            self.syncing = True
            self.midi_velocity_min.setValue(vel_min)
            self.midi_velocity_min_label.setText(str(vel_min))
            self.midi_velocity_max.setValue(vel_max)
            self.midi_velocity_max_label.setText(str(vel_max))
            self.syncing = False

    def on_midi_advanced_toggled(self):
        """Toggle advanced MIDI options visibility"""
        show_advanced = self.midi_advanced_checkbox.isChecked()

        # Show/hide keysplit/triplesplit enable widgets
        self.keysplit_enable_widget.setVisible(show_advanced)
        self.triplesplit_enable_widget.setVisible(show_advanced)

        # Toggle between simple controls and tabs
        if show_advanced:
            # Hide simple widget, show tabs
            self.simple_midi_widget.setVisible(ui_mode.pages_simplified())
            self.midi_tabs.setVisible(True)
            # Sync values from simple to advanced controls
            self.sync_simple_to_advanced()
            # Update tab view based on split settings
            self.update_midi_container_view()
        else:
            # Show simple widget, hide tabs
            self.simple_midi_widget.setVisible(True)
            self.midi_tabs.setVisible(False)
            # Sync values from advanced to simple controls
            self.sync_advanced_to_simple()
            # Uncheck keysplit/triplesplit when leaving advanced mode
            self.keysplit_enabled_checkbox.setChecked(False)
            self.triplesplit_enabled_checkbox.setChecked(False)

    def apply_mode(self):
        """Basic mode always shows the simple MIDI controls, whatever
        "Show Advanced" (hidden in that mode) is set to."""
        advanced = self.midi_advanced_checkbox.isChecked()
        self.simple_midi_widget.setVisible(ui_mode.pages_simplified() or not advanced)

    def sync_simple_to_advanced(self):
        """Sync values from simple controls to advanced tab controls"""
        # Sync channel
        channel_val = self.simple_channel_slider.value()
        self.midi_channel_slider.setValue(channel_val)
        self.midi_channel_label.setText(str(channel_val + 1))

        # Sync transpose
        transpose_val = self.simple_transpose_slider.value()
        self.midi_transpose_slider.setValue(transpose_val)
        self.midi_transpose_label.setText(f"{'+' if transpose_val >= 0 else ''}{transpose_val}")

    def sync_advanced_to_simple(self):
        """Sync values from advanced tab controls to simple controls"""
        # Sync channel
        channel_val = self.midi_channel_slider.value()
        self.simple_channel_slider.setValue(channel_val)
        self.simple_channel_label.setText(str(channel_val + 1))

        # Sync transpose
        transpose_val = self.midi_transpose_slider.value()
        self.simple_transpose_slider.setValue(transpose_val)
        self.simple_transpose_label.setText(f"{'+' if transpose_val >= 0 else ''}{transpose_val}")

    def on_midi_velocity_slider_changed(self, slider_type, value):
        """Handle velocity slider changes"""
        if slider_type == 'min':
            self.midi_velocity_min_label.setText(str(value))
            if not self.syncing:
                self.save_midi_ui_to_memory()
                self.send_param(PARAM_HE_VELOCITY_MIN, value)
        elif slider_type == 'max':
            self.midi_velocity_max_label.setText(str(value))
            if not self.syncing:
                self.save_midi_ui_to_memory()
                self.send_param(PARAM_HE_VELOCITY_MAX, value)

    def on_keysplit_velocity_slider_changed(self, slider_type, value):
        """Handle keysplit velocity slider changes"""
        if slider_type == 'min':
            self.keysplit_velocity_min_label.setText(str(value))
            if not self.syncing:
                self.save_midi_ui_to_memory()
                self.send_param(PARAM_KEYSPLIT_HE_VELOCITY_MIN, value)
        elif slider_type == 'max':
            self.keysplit_velocity_max_label.setText(str(value))
            if not self.syncing:
                self.save_midi_ui_to_memory()
                self.send_param(PARAM_KEYSPLIT_HE_VELOCITY_MAX, value)

    def on_triplesplit_velocity_slider_changed(self, slider_type, value):
        """Handle triplesplit velocity slider changes"""
        if slider_type == 'min':
            self.triplesplit_velocity_min_label.setText(str(value))
            if not self.syncing:
                self.save_midi_ui_to_memory()
                self.send_param(PARAM_TRIPLESPLIT_HE_VELOCITY_MIN, value)
        elif slider_type == 'max':
            self.triplesplit_velocity_max_label.setText(str(value))
            if not self.syncing:
                self.save_midi_ui_to_memory()
                self.send_param(PARAM_TRIPLESPLIT_HE_VELOCITY_MAX, value)

    def _compute_split_status(self):
        """Compute the split status value from checkbox state"""
        ks = self.keysplit_enabled_checkbox.isChecked()
        ts = self.triplesplit_enabled_checkbox.isChecked()
        if ks and ts:
            return 3
        if ts:
            return 2
        if ks:
            return 1
        return 0

    def _send_split_status(self):
        """Send all three split status params to the keyboard"""
        status = self._compute_split_status()
        self.send_param(PARAM_KEYSPLITSTATUS, status)
        self.send_param(PARAM_KEYSPLITTRANSPOSESTATUS, status)
        self.send_param(PARAM_KEYSPLITVELOCITYSTATUS, status)

    def on_keysplit_enabled_toggled(self):
        """Toggle KeySplit settings - switch to tabbed view when enabled"""
        self.update_midi_container_view()
        if not self.syncing:
            self.save_midi_ui_to_memory()
            self._send_split_status()

    def on_triplesplit_enabled_toggled(self):
        """Toggle TripleSplit settings - auto-enable keysplit and switch to tabbed view"""
        if self.triplesplit_enabled_checkbox.isChecked():
            # Auto-tick keysplit when triplesplit is enabled
            if not self.keysplit_enabled_checkbox.isChecked():
                self.keysplit_enabled_checkbox.setChecked(True)

        self.update_midi_container_view()
        if not self.syncing:
            self.save_midi_ui_to_memory()
            self._send_split_status()

    def set_matrix_test_reference(self, matrix_test):
        """Set reference to MatrixTest widget for status value adjustments"""
        self.matrix_test = matrix_test

    def update_midi_container_view(self):
        """Update tabs based on split settings - always show tabs"""
        keysplit_enabled = self.keysplit_enabled_checkbox.isChecked()
        triplesplit_enabled = self.triplesplit_enabled_checkbox.isChecked()

        # Show/hide sustain widget in Basic tab based on split settings
        if hasattr(self, 'midi_sustain_widget'):
            self.midi_sustain_widget.setVisible(keysplit_enabled or triplesplit_enabled)

        # Tabs are always shown, just rebuild which tabs are visible
        self.midi_tabs.clear()
        self.midi_tabs.addTab(self.basic_tab_widget, "Basic")
        if keysplit_enabled:
            self.midi_tabs.addTab(self.keysplit_tab_widget, "KeySplit")
        if triplesplit_enabled:
            self.midi_tabs.addTab(self.triplesplit_tab_widget, "TripleSplit")

    def on_keysplit_tab_checkbox_changed(self):
        """Handle keysplit checkbox changes from tab widgets"""
        if self.syncing:
            return
        # Get the state from whichever checkbox was changed
        checked = False
        if hasattr(self, 'keysplit_enabled_checkbox_tab') and self.sender() == self.keysplit_enabled_checkbox_tab:
            checked = self.keysplit_enabled_checkbox_tab.isChecked()
        elif hasattr(self, 'keysplit_enabled_checkbox_tab_ts') and self.sender() == self.keysplit_enabled_checkbox_tab_ts:
            checked = self.keysplit_enabled_checkbox_tab_ts.isChecked()

        # Update main checkbox
        self.syncing = True
        self.keysplit_enabled_checkbox.setChecked(checked)
        self.syncing = False

        # Update view and save
        self.update_midi_container_view()
        self.save_midi_ui_to_memory()

    def on_triplesplit_tab_checkbox_changed(self):
        """Handle triplesplit checkbox changes from tab widgets"""
        if self.syncing:
            return
        # Get the state from whichever checkbox was changed
        checked = False
        if hasattr(self, 'triplesplit_enabled_checkbox_tab') and self.sender() == self.triplesplit_enabled_checkbox_tab:
            checked = self.triplesplit_enabled_checkbox_tab.isChecked()
        elif hasattr(self, 'triplesplit_enabled_checkbox_tab_ks') and self.sender() == self.triplesplit_enabled_checkbox_tab_ks:
            checked = self.triplesplit_enabled_checkbox_tab_ks.isChecked()

        # Update main checkbox (this will trigger auto-tick of keysplit if needed)
        self.syncing = True
        self.triplesplit_enabled_checkbox.setChecked(checked)
        self.syncing = False

        # If enabling triplesplit, also enable keysplit
        if checked and not self.keysplit_enabled_checkbox.isChecked():
            self.keysplit_enabled_checkbox.setChecked(True)

        # Update view and save
        self.update_midi_container_view()
        self.save_midi_ui_to_memory()

    def save_midi_ui_to_memory(self):
        """Save MIDI settings from UI to memory"""
        self.midi_settings['channel'] = self.midi_channel_slider.value()
        self.midi_settings['transpose'] = self.midi_transpose_slider.value()
        self.midi_settings['sustain'] = self.midi_sustain_combo.currentData()
        self.midi_settings['velocity_curve'] = self.midi_velocity_curve.currentData()
        self.midi_settings['velocity_min'] = self.midi_velocity_min.value()
        self.midi_settings['velocity_max'] = self.midi_velocity_max.value()

        self.midi_settings['keysplit_enabled'] = self.keysplit_enabled_checkbox.isChecked()
        self.midi_settings['keysplit_channel'] = self.keysplit_channel_slider.value()
        self.midi_settings['keysplit_transpose'] = self.keysplit_transpose_slider.value()
        self.midi_settings['keysplit_sustain'] = self.keysplit_sustain_combo.currentData()
        self.midi_settings['keysplit_autonotes_ignore'] = self.keysplit_autonotes_combo.currentData()
        self.midi_settings['keysplit_velocity_curve'] = self.keysplit_velocity_curve.currentData()
        self.midi_settings['keysplit_velocity_min'] = self.keysplit_velocity_min.value()
        self.midi_settings['keysplit_velocity_max'] = self.keysplit_velocity_max.value()

        self.midi_settings['triplesplit_enabled'] = self.triplesplit_enabled_checkbox.isChecked()
        self.midi_settings['triplesplit_channel'] = self.triplesplit_channel_slider.value()
        self.midi_settings['triplesplit_transpose'] = self.triplesplit_transpose_slider.value()
        self.midi_settings['triplesplit_sustain'] = self.triplesplit_sustain_combo.currentData()
        self.midi_settings['triplesplit_autonotes_ignore'] = self.triplesplit_autonotes_combo.currentData()
        self.midi_settings['triplesplit_velocity_curve'] = self.triplesplit_velocity_curve.currentData()
        self.midi_settings['triplesplit_velocity_min'] = self.triplesplit_velocity_min.value()
        self.midi_settings['triplesplit_velocity_max'] = self.triplesplit_velocity_max.value()

    def update_user_curve_names(self, names):
        """Update user curve names in all velocity curve dropdowns (simple, basic, keysplit, triplesplit)"""
        combos = [self.simple_velocity_preset_combo, self.midi_velocity_curve,
                  self.keysplit_velocity_curve, self.triplesplit_velocity_curve]
        for combo in combos:
            for i, name in enumerate(names):
                idx = 23 + i  # Factory curves take indices 0-22 (23 factory presets)
                display = name if name and name.strip() else "User {}".format(i + 1)
                # Find the combo item with this data value
                for j in range(combo.count()):
                    if combo.itemData(j) == idx:
                        combo.setItemText(j, display)
                        break

    def set_device(self, device):
        """Set the device and load initial settings from device"""
        self.device = device
        is_vial = isinstance(device, VialKeyboard)
        self.setEnabled(is_vial)

        # Ensure checkboxes always stay enabled when widget is enabled
        if is_vial:
            self.per_layer_checkbox.setEnabled(True)
            self.enable_per_key_checkbox.setEnabled(True)

        if self.device and isinstance(self.device, VialKeyboard):
            # Load all layers from device into memory cache
            self.load_all_layers_from_device()
            # Load current layer to UI
            self.load_layer_from_memory()
            # Load MIDI settings from device
            self.load_midi_settings_from_device()

    def load_midi_settings_from_device(self):
        """Load MIDI settings from keyboard and populate UI controls"""
        try:
            if not self.device or not isinstance(self.device, VialKeyboard):
                return

            config = self.device.keyboard.get_midi_config()
            if not config:
                return

            self.syncing = True

            # Base channel
            ch = config.get('channel_number', 0)
            self.simple_channel_slider.setValue(ch)
            self.simple_channel_label.setText(str(ch + 1))
            self.midi_channel_slider.setValue(ch)
            self.midi_channel_label.setText(str(ch + 1))

            # Base transpose
            tr_val = config.get('transpose_number', 0)
            self.simple_transpose_slider.setValue(tr_val)
            self.simple_transpose_label.setText(f"{'+' if tr_val >= 0 else ''}{tr_val}")
            self.midi_transpose_slider.setValue(tr_val)
            self.midi_transpose_label.setText(f"{'+' if tr_val >= 0 else ''}{tr_val}")

            # KeySplit channel
            ks_ch = config.get('key_split_channel', 0)
            self.keysplit_channel_slider.setValue(ks_ch)
            self.keysplit_channel_label.setText(str(ks_ch + 1))

            # TripleSplit channel
            ts_ch = config.get('key_split2_channel', 0)
            self.triplesplit_channel_slider.setValue(ts_ch)
            self.triplesplit_channel_label.setText(str(ts_ch + 1))

            # KeySplit transpose
            tr2 = config.get('transpose_number2', 0)
            self.keysplit_transpose_slider.setValue(tr2)
            self.keysplit_transpose_label.setText(f"{'+' if tr2 >= 0 else ''}{tr2}")

            # TripleSplit transpose
            tr3 = config.get('transpose_number3', 0)
            self.triplesplit_transpose_slider.setValue(tr3)
            self.triplesplit_transpose_label.setText(f"{'+' if tr3 >= 0 else ''}{tr3}")

            # Velocity curves
            base_curve = config.get('he_velocity_curve', 2)
            ks_curve = config.get('keysplit_he_velocity_curve', 2)
            ts_curve = config.get('triplesplit_he_velocity_curve', 2)

            # Rebuild the Articulation combos with the device's user-slot names,
            # hiding unconfigured user slots and showing the AT/CC bands only
            # when enabled (each combo keeps its own current index visible so a
            # device sitting on a hidden index still round-trips).
            self._refresh_articulation_combos(config, {
                'simple_velocity_preset_combo': base_curve,
                'midi_velocity_curve': base_curve,
                'keysplit_velocity_curve': ks_curve,
                'triplesplit_velocity_curve': ts_curve,
            })

            for i in range(self.simple_velocity_preset_combo.count()):
                if self.simple_velocity_preset_combo.itemData(i) == base_curve:
                    self.simple_velocity_preset_combo.setCurrentIndex(i)
                    break
            for i in range(self.midi_velocity_curve.count()):
                if self.midi_velocity_curve.itemData(i) == base_curve:
                    self.midi_velocity_curve.setCurrentIndex(i)
                    break

            for i in range(self.keysplit_velocity_curve.count()):
                if self.keysplit_velocity_curve.itemData(i) == ks_curve:
                    self.keysplit_velocity_curve.setCurrentIndex(i)
                    break

            for i in range(self.triplesplit_velocity_curve.count()):
                if self.triplesplit_velocity_curve.itemData(i) == ts_curve:
                    self.triplesplit_velocity_curve.setCurrentIndex(i)
                    break

            # Sustain and Auto-Notes (0 = Allow, 1 = Ignore on the keyboard)
            for combo, key in ((self.midi_sustain_combo, 'base_sustain'),
                               (self.keysplit_sustain_combo, 'keysplit_sustain'),
                               (self.triplesplit_sustain_combo, 'triplesplit_sustain'),
                               (self.keysplit_autonotes_combo, 'keysplit_smartchord_ignore'),
                               (self.triplesplit_autonotes_combo, 'triplesplit_smartchord_ignore')):
                idx = combo.findData(1 if config.get(key, 0) == 1 else 0)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

            # Split status - determine which splits are enabled
            ks_status = config.get('key_split_status', 0)
            ks_enabled = ks_status in [1, 3]
            ts_enabled = ks_status in [2, 3]
            self.keysplit_enabled_checkbox.setChecked(ks_enabled)
            self.triplesplit_enabled_checkbox.setChecked(ts_enabled)

            # Show advanced mode if splits are enabled
            if ks_enabled or ts_enabled:
                self.midi_advanced_checkbox.setChecked(True)

            # Update memory
            self.save_midi_ui_to_memory()

            self.syncing = False
        except Exception:
            self.syncing = False

    def _refresh_articulation_combos(self, config, combo_keep):
        """Rebuild the Articulation combos with device user-slot names and apply
        band visibility. `combo_keep` maps this object's combo attribute name to
        the curve index that combo should keep visible (its to-be-selected
        value). Cheap and safe to call whenever the device config reloads."""
        # User-slot names + configured flags (device round-trip; guard failures)
        user_names, user_configured = None, None
        try:
            if self.device and isinstance(self.device, VialKeyboard):
                res = self.device.keyboard.get_all_user_curve_names()
                if res:
                    user_names, user_configured = res
        except Exception:
            user_names, user_configured = None, None
        # Cache so a later enable-toggle refresh can reuse them
        self._artic_user_names = user_names
        self._artic_user_configured = user_configured
        cc_enabled = bool(config.get('enable_cc_modes', False))
        at_enabled = bool(config.get('enable_at_modes', False))
        for attr, keep_index in combo_keep.items():
            combo = getattr(self, attr, None)
            if combo is None:
                continue
            populate_articulation_combo(combo, user_names=user_names)
            apply_articulation_visibility(combo, user_configured=user_configured,
                                          cc_enabled=cc_enabled, at_enabled=at_enabled,
                                          keep_index=keep_index)

    def load_all_layers_from_device(self):
        """Load all 12 layers from device into memory cache (only called once on connect)"""
        try:
            if not self.device or not isinstance(self.device, VialKeyboard):
                return

            actuations = self.device.keyboard.get_all_layer_actuations()

            if not actuations or len(actuations) < 120:  # 12 layers * 10 bytes
                return

            # Load all layers into memory
            # New format: [normal, midi, velocity_mode, vel_speed, flags,
            #              aftertouch_mode, aftertouch_cc, vibrato_sensitivity,
            #              vibrato_decay_time_low, vibrato_decay_time_high]
            for layer in range(12):
                offset = layer * 10
                flags = actuations[offset + 4]
                vibrato_decay = actuations[offset + 8] | (actuations[offset + 9] << 8)

                self.layer_data[layer] = {
                    'normal': actuations[offset + 0],
                    'midi': actuations[offset + 1],
                    'velocity': actuations[offset + 2],  # Velocity mode
                    'vel_speed': actuations[offset + 3],
                    'rapidfire_enabled': (flags & 0x01) != 0,
                    'midi_rapidfire_enabled': (flags & 0x02) != 0,
                    'aftertouch_mode': actuations[offset + 5],
                    'aftertouch_cc': actuations[offset + 6],
                    'vibrato_sensitivity': actuations[offset + 7],
                    'vibrato_decay_time': vibrato_decay
                }

            # NOTE: Advanced settings UI moved to VelocityTab

            self.load_layer_from_memory()       # show what the keyboard has (also updates the Actuation slider)

        except Exception:
            pass
    
    def set_layer(self, layer):
        """Set current layer and load its settings if in per-layer mode"""
        self.current_layer = layer
        self.layer_label.setText(tr("QuickActuationWidget", f"Layer {layer + 1}"))
        self.update_layer_title()

        # Update save button text if in per-layer mode
        if self.per_layer_enabled:
            self.save_btn.setText(tr("QuickActuationWidget", f"Save to Layer {layer + 1}"))
            # Load from memory (fast, no device I/O)
            self.load_layer_from_memory()

        self.refresh_layer_actuation_ui()

        # NOTE: Advanced tab settings now in VelocityTab, not here

    def update_layer_title(self):
        """Update the layer title label with the current layer name"""
        from protocol.feature_names import get_feature_name_manager, FEATURE_LAYER
        mgr = get_feature_name_manager()
        name = mgr.get_name(FEATURE_LAYER, self.current_layer)
        self.layer_title_label.setText("<b>{}</b>".format(name))

    def _on_layer_rename(self):
        """Open rename dialog for the current layer"""
        from protocol.feature_names import get_feature_name_manager, FEATURE_LAYER, MAX_NAME_LENGTH
        mgr = get_feature_name_manager()
        current = mgr.get_name(FEATURE_LAYER, self.current_layer)
        new_name, ok = QInputDialog.getText(
            self, "Rename Layer",
            "Name for Layer {} (max {} chars, uppercase):".format(self.current_layer + 1, MAX_NAME_LENGTH),
            text=current
        )
        if ok and new_name.strip():
            mgr.set_name(FEATURE_LAYER, self.current_layer, new_name)
            self.update_layer_title()
            # Also notify parent to refresh layer button tooltips
            self.layer_renamed.emit()


class EncoderButton(QWidget):
    """Circular encoder button widget with arrow indicator"""

    clicked = pyqtSignal()

    def __init__(self, is_up=True):
        super().__init__()
        self.is_up = is_up
        self.is_selected = False
        self.text = "KC_NO"
        self.setFixedSize(55, 55)
        self.setMouseTracking(True)

    def setChecked(self, checked):
        self.is_selected = checked
        self.update()

    def setText(self, text):
        self.text = text
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QPainterPath, QPen, QBrush, QFont
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QPalette
        from PyQt5.QtCore import Qt

        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)

        # Draw circular background with 50% opacity fill
        if self.is_selected:
            pen = QPen(QApplication.palette().color(QPalette.Highlight))
            pen.setWidth(2)
            qp.setPen(pen)
        else:
            pen = QPen(QApplication.palette().color(QPalette.Window))
            pen.setWidth(2)
            qp.setPen(pen)

        # Create brush with 50% opacity
        button_color = QApplication.palette().color(QPalette.Button)
        button_color.setAlpha(128)  # 50% opacity
        brush = QBrush(button_color)
        qp.setBrush(brush)
        qp.drawEllipse(3, 3, 49, 49)

        # Draw keycode text (label is now outside button)
        qp.setPen(QApplication.palette().color(QPalette.ButtonText))
        font = QFont()
        font.setPointSize(8)  # Match keyboard widget font size
        qp.setFont(font)
        text_rect = self.rect().adjusted(3, 3, -3, -3)
        qp.drawText(text_rect, Qt.AlignCenter, self.text)

        qp.end()


class PushButton(QWidget):
    """Square push button widget"""

    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.is_selected = False
        self.text = "KC_NO"
        self.setFixedSize(55, 55)
        self.setMouseTracking(True)

    def setChecked(self, checked):
        self.is_selected = checked
        self.update()

    def setText(self, text):
        self.text = text
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QPen, QBrush, QFont
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QPalette
        from PyQt5.QtCore import Qt

        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)

        # Draw square background with 50% opacity fill
        if self.is_selected:
            pen = QPen(QApplication.palette().color(QPalette.Highlight))
            pen.setWidth(2)
            qp.setPen(pen)
        else:
            pen = QPen(QApplication.palette().color(QPalette.Window))
            pen.setWidth(2)
            qp.setPen(pen)

        # Create brush with 50% opacity
        button_color = QApplication.palette().color(QPalette.Button)
        button_color.setAlpha(128)  # 50% opacity
        brush = QBrush(button_color)
        qp.setBrush(brush)
        qp.drawRoundedRect(3, 3, 49, 49, 4, 4)

        # Draw keycode text (label is now outside button)
        qp.setPen(QApplication.palette().color(QPalette.ButtonText))
        font = QFont()
        font.setPointSize(8)  # Match keyboard widget font size
        qp.setFont(font)
        text_rect = self.rect().adjusted(3, 3, -3, -3)
        qp.drawText(text_rect, Qt.AlignCenter, self.text)

        qp.end()


class SustainButton(QWidget):
    """Sustain pedal button widget"""

    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.is_selected = False
        self.text = "KC_NO"
        self.setFixedSize(50, 50)
        self.setMouseTracking(True)

    def setChecked(self, checked):
        self.is_selected = checked
        self.update()

    def setText(self, text):
        self.text = text
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QPen, QBrush, QFont
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QPalette
        from PyQt5.QtCore import Qt

        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)

        # Draw rounded rectangle background with 50% opacity
        if self.is_selected:
            pen = QPen(QApplication.palette().color(QPalette.Highlight))
            pen.setWidth(2)
            qp.setPen(pen)
        else:
            pen = QPen(QApplication.palette().color(QPalette.Window))
            pen.setWidth(2)
            qp.setPen(pen)

        # Create brush with 50% opacity
        button_color = QApplication.palette().color(QPalette.Button)
        button_color.setAlpha(128)  # 50% opacity
        brush = QBrush(button_color)
        qp.setBrush(brush)
        qp.drawRoundedRect(3, 3, 44, 44, 4, 4)

        # Draw keycode text
        qp.setPen(QApplication.palette().color(QPalette.ButtonText))
        font = QFont()
        font.setPointSize(8)  # Match keyboard widget font size
        qp.setFont(font)
        text_rect = self.rect().adjusted(3, 3, -3, -3)
        qp.drawText(text_rect, Qt.AlignCenter, self.text)

        qp.end()


class RotationArrow(QWidget):
    """Curved rotational-arrow title for the encoder buttons.

    Draws a thick arc ending in a solid arrowhead (rotate-left). Pass
    mirror=True to flip it horizontally into a rotate-right arrow.
    """

    def __init__(self, mirror=False, parent=None):
        super().__init__(parent)
        self.mirror = mirror
        self.setFixedSize(30, 25)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        import math
        from PyQt5.QtGui import QPainter, QPen, QBrush, QPainterPath, QPolygonF
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QPalette
        from PyQt5.QtCore import Qt, QRectF, QPointF

        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if self.mirror:
            qp.translate(w, 0)
            qp.scale(-1, 1)

        color = QApplication.palette().color(QPalette.ButtonText)
        pad = w * 0.16
        rect = QRectF(pad, pad, w - 2 * pad, h - 2 * pad)
        start, span = 0, 180        # exact 180° half-circle
        body = span - 18            # leave a gap at the end for the arrowhead
        head = w * 0.42

        path = QPainterPath()
        path.arcMoveTo(rect, start)
        path.arcTo(rect, start, body)
        pen = QPen(color)
        pen.setWidthF(w * 0.17)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        qp.setPen(pen)
        qp.setBrush(Qt.NoBrush)
        qp.drawPath(path)

        end = path.currentPosition()
        prev_path = QPainterPath()
        prev_path.arcMoveTo(rect, start + body - 6)
        prev = prev_path.currentPosition()
        dx, dy = end.x() - prev.x(), end.y() - prev.y()
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        px, py = -uy, ux  # perpendicular to the tangent
        tip = QPointF(end.x() + ux * head * 0.75, end.y() + uy * head * 0.75)
        base1 = QPointF(end.x() + px * head * 0.55, end.y() + py * head * 0.55)
        base2 = QPointF(end.x() - px * head * 0.55, end.y() - py * head * 0.55)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QBrush(color))
        qp.drawPolygon(QPolygonF([tip, base1, base2]))

        qp.end()


class EncoderAssignWidget(QWidget):
    """Widget for assigning keycodes to encoders and sustain pedal per layer"""

    clicked = pyqtSignal()  # Emitted when a button is clicked (for tabbed_keycodes integration)
    joystick_clicked = pyqtSignal(int)  # joystick overlay on button index clicked

    def __init__(self):
        super().__init__()

        self.current_layer = 0
        self.selected_button = None
        self.buttons = []
        self.joystick_overlays = {}
        # Single-encoder hardware: one rotary encoder (enc_idx 0) + sustain pedal.
        self.labels = [
            "Encoder Up",
            "Encoder Down",
            "Encoder Press",
            "Footswitch"
        ]

        # Sized and placed by OverlayContainer over the left part of the keyboard
        # photo; the buttons are placed on the photo's screen and knob by
        # place_on_photo().
        self.resize(185, 345)

        # Make background transparent so keyboard background shows through
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # Create buttons in logical order (indices 0-3) before adding to UI
        # Index 0: Encoder Up
        enc_up_btn = EncoderButton(is_up=True)
        enc_up_btn.clicked.connect(lambda: self.on_button_clicked(0))
        self.buttons.append(enc_up_btn)

        # Index 1: Encoder Down
        enc_down_btn = EncoderButton(is_up=False)
        enc_down_btn.clicked.connect(lambda: self.on_button_clicked(1))
        self.buttons.append(enc_down_btn)

        # Index 2: Encoder Press
        enc_push_btn = PushButton()
        enc_push_btn.clicked.connect(lambda: self.on_button_clicked(2))
        self.buttons.append(enc_push_btn)

        # Index 3: Sustain Pedal
        sustain_btn = SustainButton()
        sustain_btn.clicked.connect(lambda: self.on_button_clicked(3))
        self.buttons.append(sustain_btn)

        # The footswitch: its title and button on the photo's screen
        sustain_label = QLabel("Footswitch", self)
        # Always white so it stays legible over both light and dark backgrounds.
        sustain_label.setStyleSheet("QLabel { font-size: 11px; font-weight: bold; color: white; background: transparent; }")
        sustain_label.setAlignment(Qt.AlignCenter)
        sustain_btn.setParent(self)
        self.sustain_label = sustain_label
        self.sustain_btn = sustain_btn

        # Encoder group (single encoder) — absolutely-positioned buttons.
        # No "Encoder"/UP/DOWN/PUSH titles. Up and Down sit level, each shifted
        # down 3/4 of a button height; Down takes the old Push column. Push is
        # centered between Up and Down, a further 3/4 of a button height lower.
        # The push button keeps a single "Click" title beneath it.
        BTN = 55                 # button width/height (fixed 55x55)
        SPACING = 5              # original inter-button gap
        Q3 = int(round(BTN * 0.75))  # 3/4 of a button height (≈ 41px)

        # Original columns (HBox with 5px spacing): up=0, down=60, push=120
        col_up = 0
        col_push = (BTN + SPACING) * 2  # 120 — old Push column

        encoder_container = QWidget(self)
        encoder_container.setAttribute(Qt.WA_TranslucentBackground)
        encoder_container.setStyleSheet("background: transparent;")
        encoder_container.setFixedSize(col_push + BTN, Q3 * 2 + BTN + 18)

        # Down (rotate left, CCW) on the left, Up (rotate right, CW) on the
        # right, each shifted down 3/4 of a button height.
        enc_down_btn.setParent(encoder_container)
        enc_down_btn.move(col_up, Q3)

        enc_up_btn.setParent(encoder_container)
        enc_up_btn.move(col_push, Q3)

        # Encoder rotation titles: curved rotational arrows above the left/right
        # buttons (left = rotate-left, right = rotate-right) instead of UP/DOWN.
        ARROW_W = 30
        left_arrow = RotationArrow(mirror=False, parent=encoder_container)
        left_arrow.move(col_up + (BTN - ARROW_W) // 2, Q3 - 22)
        right_arrow = RotationArrow(mirror=True, parent=encoder_container)
        right_arrow.move(col_push + (BTN - ARROW_W) // 2, Q3 - 22)

        # Push: centered horizontally between the new Up/Down, a FURTHER 3/4 down
        col_push_center = (col_up + col_push) // 2  # 60
        enc_push_btn.setParent(encoder_container)
        enc_push_btn.move(col_push_center, Q3 * 2)

        # The only remaining encoder title: bold "Click" above the push button
        click_label = QLabel("Click", encoder_container)
        click_label.setStyleSheet("QLabel { font-size: 9px; font-weight: bold; background: transparent; }")
        click_label.setAlignment(Qt.AlignCenter)
        click_label.setGeometry(col_push_center, Q3 * 2 - 16, BTN, 14)

        self.encoder_container = encoder_container
        # The point of the encoder group that goes on the knob's centre: midway
        # between the rotate buttons' row and the Click button, under Click.
        self.knob_point = QPointF(col_push_center + BTN / 2.0, 1.5 * Q3 + BTN / 2.0)

        # Where they sit until the keyboard picture is laid out
        self.place_on_photo(QPointF(93, 126), QPointF(93, 283))

    def place_on_photo(self, foot_centre, knob_centre):
        """Put the footswitch button (with its title above it) centred on
        `foot_centre`, the photo's screen, and the encoder group on
        `knob_centre`, the photo's knob. Both in this widget's coordinates."""
        b = self.sustain_btn
        b.move(round(foot_centre.x() - b.width() / 2.0), round(foot_centre.y() - b.height() / 2.0))
        title_h = self.sustain_label.sizeHint().height()
        self.sustain_label.setGeometry(round(foot_centre.x()) - 70, b.y() - title_h - 6, 140, title_h)
        c = self.encoder_container
        c.move(round(knob_centre.x() - self.knob_point.x()), round(knob_centre.y() - self.knob_point.y()))

    def on_button_clicked(self, index):
        """Handle button click - mark as selected and notify parent"""
        # Deselect all other buttons
        for i, btn in enumerate(self.buttons):
            btn.setChecked(i == index)

        self.selected_button = index
        self.clicked.emit()

    def deselect(self):
        """Deselect all buttons"""
        for btn in self.buttons:
            btn.setChecked(False)
        self.selected_button = None

    def set_keycode(self, index, keycode):
        """Update button display with keycode"""
        if 0 <= index < len(self.buttons):
            self.buttons[index].setText(Keycode.label(keycode))

    def _on_button_context_menu(self, index):
        overlay = self.joystick_overlays.get(index)
        if overlay is not None and not overlay.isHidden():
            self.joystick_clicked.emit(index)

    def set_joystick(self, index, text):
        """Show the joystick function attached to button `index` (the click /
        footswitch matrix keys) at 50% opacity in its bottom-right quarter;
        clicking it emits joystick_clicked(index). Empty text hides it."""
        if not (0 <= index < len(self.buttons)):
            return
        overlay = self.joystick_overlays.get(index)
        if not text:
            if overlay is not None:
                overlay.hide()
            return
        btn = self.buttons[index]
        if overlay is None:
            overlay = QPushButton(btn)
            overlay.setFocusPolicy(Qt.NoFocus)
            overlay.setCursor(Qt.PointingHandCursor)
            overlay.setStyleSheet(
                "QPushButton { background: rgba(150, 60, 255, 128); color: rgba(255, 255, 255, 170);"
                " border: none; border-radius: 4px; font-weight: bold; font-size: 8pt; padding: 0px; }")
            overlay.clicked.connect(lambda _=False, i=index: self.joystick_clicked.emit(i))
            # Right click on the overlay or its button opens the same menu
            overlay.setContextMenuPolicy(Qt.CustomContextMenu)
            overlay.customContextMenuRequested.connect(
                lambda _pos, i=index: self.joystick_clicked.emit(i))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda _pos, i=index: self._on_button_context_menu(i))
            self.joystick_overlays[index] = overlay
        w, h = btn.width(), btn.height()
        overlay.setGeometry(w // 2, h // 2, w - w // 2, h - h // 2)
        overlay.setText(text)
        overlay.show()
        overlay.raise_()

    def set_layer(self, layer, keyboard=None):
        """Update current layer and refresh button displays from keyboard"""
        self.current_layer = layer

        # Load keycodes from keyboard if provided
        if keyboard is not None:
            # Encoder rotation mapping (only CW and CCW, not press)
            encoder_mapping = {
                0: (0, 1),  # Encoder Up (enc_idx=0, dir=1 CW)
                1: (0, 0),  # Encoder Down (enc_idx=0, dir=0 CCW)
            }

            # Matrix key mapping for encoder press and sustain pedal
            matrix_key_mapping = {
                2: (5, 0),  # Encoder Press -> row 5, col 0 (firmware single-encoder click, PB0)
                3: (5, 2),  # Sustain Pedal -> row 5, col 2
            }

            # Update encoder rotation buttons (from encoder_layout)
            for idx in encoder_mapping:
                enc_idx, direction = encoder_mapping[idx]
                keycode = keyboard.encoder_layout.get((layer, enc_idx, direction), "KC_NO")
                self.buttons[idx].setText(Keycode.label(keycode))

            # Update encoder press and sustain pedal buttons (from regular matrix layout)
            for idx in matrix_key_mapping:
                row, col = matrix_key_mapping[idx]
                keycode = keyboard.layout.get((layer, row, col), "KC_NO")
                self.buttons[idx].setText(Keycode.label(keycode))

        # Deselect when changing layers
        self.deselect()


class ClickableWidget(QWidget):

    clicked = pyqtSignal()

    def mousePressEvent(self, evt):
        super().mousePressEvent(evt)
        self.clicked.emit()


class OverlayContainer(QWidget):
    """Container that overlays encoder widget on top of keyboard widget"""

    def __init__(self, keyboard_widget, encoder_widget):
        super().__init__()
        self.keyboard_widget = keyboard_widget
        self.encoder_widget = encoder_widget

        # Set up layout with no spacing
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(keyboard_widget)
        self.setLayout(layout)

        # Make encoder widget a child of this container for overlay
        encoder_widget.setParent(self)
        encoder_widget.raise_()  # Bring to front
        # the buttons follow the keyboard picture when a theme switch changes it
        if hasattr(keyboard_widget, "photo_changed"):
            keyboard_widget.photo_changed.connect(self.place_encoder_widget)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.place_encoder_widget()

    def place_encoder_widget(self):
        """Lay the encoder / footswitch buttons over the keyboard photo: the
        widget covers the photo's left part (up to the first key, so it never
        takes a key's clicks), the footswitch goes on the photo's screen and
        the encoder buttons around its knob."""
        kw = self.keyboard_widget
        pos = kw.pos()
        if not hasattr(kw, "photo_rect") or kw.photo_rect.isEmpty():
            self.encoder_widget.setGeometry(pos.x(), pos.y() + 30, 185, max(kw.rect().height(), 345))
            return
        width = max(60, int(kw.keys_left()) - 2)
        self.encoder_widget.setGeometry(pos.x(), pos.y(), width, kw.rect().height())
        knob, _radius = kw.photo_knob()
        self.encoder_widget.place_on_photo(kw.photo_screen_rect().center(), knob)


class ZoomView(QGraphicsView):
    """Shows a widget at a zoom factor. Everything inside it (the keyboard photo, the keys
    and the dial and footswitch buttons laid over the photo) is scaled together, so the
    parts stay lined up at every size. The view is always exactly as big as its scaled
    content, so the layout around it takes up or gives back the space."""

    zoom_changed = pyqtSignal()

    MIN_ZOOM, MAX_ZOOM = 0.5, 1.6

    def __init__(self, content):
        super().__init__()
        self.content = content
        self.zoom = 1.0

        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("background: transparent;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHints(self.renderHints() | QPainter.Antialiasing | QPainter.SmoothPixmapTransform
                            | QPainter.TextAntialiasing)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        content.setAttribute(Qt.WA_TranslucentBackground)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._proxy = self._scene.addWidget(content)
        content.installEventFilter(self)      # its size changes when the keyboard layout does
        self.refit()

    def set_zoom(self, zoom):
        zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, round(zoom, 2)))
        if zoom != self.zoom:
            self.zoom = zoom
            self.refit()

    def refit(self):
        """Match the view to the size of the content at the current zoom."""
        hint = self.content.sizeHint()
        if not hint.isValid() or hint.isEmpty():
            return
        if self.content.size() != hint:
            self.content.resize(hint)
        self._scene.setSceneRect(0, 0, hint.width(), hint.height())
        self.resetTransform()
        self.scale(self.zoom, self.zoom)
        size = (int(hint.width() * self.zoom + 0.999), int(hint.height() * self.zoom + 0.999))
        if (self.width(), self.height()) != size:
            self.setFixedSize(*size)
            self.zoom_changed.emit()

    def eventFilter(self, obj, ev):
        if obj is self.content and ev.type() == QEvent.LayoutRequest:
            QTimer.singleShot(0, self.refit)
        return super().eventFilter(obj, ev)


class KeymapEditor(BasicEditor):

    def __init__(self, layout_editor):
        super().__init__()

        self.layout_editor = layout_editor
        self.matrix_test = None  # Reference to MatrixTest widget for status adjustments

        self.layout_layers = QHBoxLayout()
        self.layout_size = QVBoxLayout()
        layer_label = QLabel(tr("KeymapEditor", "Layer"))

        layout_labels_container = QHBoxLayout()
        layout_labels_container.addWidget(layer_label)
        layout_labels_container.addLayout(self.layout_layers)

        # Navigation-layer control: shows whether the selected layer is the
        # layer the keyboard's on-device menus read typed input from (naming /
        # search letters, digits, arrow keys), and lets the user move it.
        # State loads in rebuild() via keyboard.get_nav_layer(); disabled on
        # firmware that predates the nav-layer HID command (0x97).
        self.nav_layer = 0
        self.nav_layer_supported = False
        layout_labels_container.addSpacing(12)
        self.nav_layer_checkbox = QCheckBox(tr("KeymapEditor", "Make Navigation Layer"))
        self.nav_layer_checkbox.setFocusPolicy(Qt.NoFocus)
        self.nav_layer_checkbox.clicked.connect(self.on_nav_layer_clicked)
        layout_labels_container.addWidget(self.nav_layer_checkbox)
        nav_help = QPushButton("?")
        nav_help.setStyleSheet("""
            QPushButton {
                color: palette(dark);
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
                color: palette(button-text);
                background-color: palette(light);
                border-color: palette(highlight);
            }
        """)
        nav_help.setFocusPolicy(Qt.NoFocus)
        nav_help.setToolTip(tr(
            "KeymapEditor",
            "The NAVIGATION LAYER is the layer the keyboard uses to navigate "
            "its on-device menus: typing names and search text (A-Z, 0-9), "
            "entering numbers, and nudging values with the arrow keys all read "
            "this layer's keymap. It defaults to Layer 1. Tick the box to make "
            "the currently selected layer the navigation layer. The navigation "
            "layer should always keep a full A-Z alphabet, the arrow keys and "
            "ESC, or menus on the device may become impossible to navigate."))
        layout_labels_container.addWidget(nav_help)
        ui_mode.advanced_only(self.nav_layer_checkbox, nav_help)
        layout_labels_container.addStretch()

        # Preset menu button with nested submenus (applies on selection)
        preset_label = QLabel(tr("KeymapEditor", "Preset:"))
        preset_label.setStyleSheet("QLabel { font-weight: bold; }")
        layout_labels_container.addWidget(preset_label)

        self.preset_menu_btn = QToolButton()
        self.preset_menu_btn.setText("Select Preset...")
        self.preset_menu_btn.setMinimumWidth(160)
        self.preset_menu_btn.setMaximumWidth(220)
        self.preset_menu_btn.setMaximumHeight(24)
        self.preset_menu_btn.setStyleSheet(
            "QToolButton { padding: 2px 8px; font-size: 9pt; }"
            "QToolButton::menu-indicator { image: none; }")
        self.preset_menu_btn.setPopupMode(QToolButton.InstantPopup)
        self._build_preset_menu()
        layout_labels_container.addWidget(self.preset_menu_btn)

        layout_labels_container.addSpacing(10)

        # Encoder preset menu button with Individual/Both submenus (applies on selection)
        enc_label = QLabel(tr("KeymapEditor", "Encoder:"))
        enc_label.setStyleSheet("QLabel { font-weight: bold; }")
        layout_labels_container.addWidget(enc_label)

        self.encoder_menu_btn = QToolButton()
        self.encoder_menu_btn.setText("Select Encoder Preset...")
        self.encoder_menu_btn.setMinimumWidth(160)
        self.encoder_menu_btn.setMaximumWidth(220)
        self.encoder_menu_btn.setMaximumHeight(24)
        self.encoder_menu_btn.setStyleSheet(
            "QToolButton { padding: 2px 8px; font-size: 9pt; }"
            "QToolButton::menu-indicator { image: none; }")
        self.encoder_menu_btn.setPopupMode(QToolButton.InstantPopup)
        self._build_encoder_menu()
        layout_labels_container.addWidget(self.encoder_menu_btn)
        ui_mode.advanced_only(enc_label, self.encoder_menu_btn)
        ui_mode.on_change(self._build_preset_menu)

        layout_labels_container.addSpacing(10)
        layout_labels_container.addLayout(self.layout_size)

        # Create quick actuation widget
        self.quick_actuation = QuickActuationWidget()
        self.quick_actuation.layer_renamed.connect(self.refresh_layer_display)

        # Create encoder assignment widget
        self.encoder_assign = EncoderAssignWidget()

        # contains the actual keyboard
        self.container = KeyboardWidgetSimple(layout_editor)
        self.container.clicked.connect(self.on_key_clicked)
        self.container.deselected.connect(self.on_key_deselected)
        # Keys dragged out of the keycode palette drop straight onto the layout.
        self.container.set_drop_assign_enabled(True)
        self.container.keycode_dropped.connect(self.on_keycode_dropped)
        self.container.joystick_clicked.connect(self.on_joystick_overlay_clicked)

        # Connect encoder widget signals
        self.encoder_assign.clicked.connect(self.on_encoder_clicked)
        self.encoder_assign.joystick_clicked.connect(self.on_encoder_joystick_clicked)

        # Create overlay container with encoder widget overlaying keyboard
        self.keyboard_overlay = OverlayContainer(self.container, self.encoder_assign)

        # The + and - buttons zoom the whole keyboard picture (photo, keys and the
        # buttons laid over it) as one.
        self.keyboard_zoom = ZoomView(self.keyboard_overlay)

        # Layout with actuation on left, then keyboard with encoder overlay
        keyboard_layout = QHBoxLayout()
        keyboard_layout.setSpacing(0)  # No spacing between widgets
        keyboard_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        # (the space to the left of the keyboard: the "Basic mode" switch is at
        # the top right of the window now)
        left_space = QVBoxLayout()
        left_space.addStretch(1)
        keyboard_layout.addLayout(left_space, 1)

        # The helper panel (layer name, actuation, MIDI settings) is tucked away until asked for.
        self.helper_toggle = QPushButton()
        self.helper_toggle.setFocusPolicy(Qt.NoFocus)
        self.helper_toggle.setStyleSheet("QPushButton { font-size: 8pt; padding: 3px 8px; }")
        self.helper_toggle.clicked.connect(lambda: self.set_helper_visible(not self.quick_actuation.isVisible()))
        helper_column = QVBoxLayout()
        helper_column.setContentsMargins(0, 8, 8, 0)
        helper_column.addWidget(self.helper_toggle, 0, Qt.AlignRight)
        helper_column.addWidget(self.quick_actuation, 0, Qt.AlignTop)
        helper_column.addStretch(1)
        keyboard_layout.addLayout(helper_column)
        self.set_helper_visible(QSettings("MIDIswitch", "SwitchStation").value("keymap_helper_visible", False, type=bool))
        keyboard_layout.addWidget(self.keyboard_zoom, 0, Qt.AlignTop)
        keyboard_layout.addStretch(1)  # Add stretch after

        layout = QVBoxLayout()
        layout.addLayout(layout_labels_container)
        layout.addLayout(keyboard_layout)

        w = ClickableWidget()
        w.setLayout(layout)
        w.clicked.connect(self.on_empty_space_clicked)

        # Wrap in scroll area for better resizing
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setWidget(w)

        # The keyboard area is only ever as tall as its content, so the keycode panel
        # below takes the room freed by zooming out (and gives it back on zooming in).
        self._keyboard_scroll = scroll_area
        self._keyboard_page = w
        self.keyboard_zoom.zoom_changed.connect(self._fit_keyboard_area)

        self.layer_buttons = []
        self.keyboard = None
        self.current_layer = 0

        layout_editor.changed.connect(self.on_layout_changed)

        self.container.anykey.connect(self.on_any_keycode)

        self.tabbed_keycodes = TabbedKeycodes()
        self.tabbed_keycodes.keycode_changed.connect(self.on_keycode_changed)
        self.tabbed_keycodes.anykey.connect(self.on_any_keycode)

        self.addWidget(scroll_area)
        self.addWidget(self.tabbed_keycodes)

        self.device = None
        KeycodeDisplay.notify_keymap_override(self)

        # Debounced MIDI/LED rescan timer - after keymap changes, waits for
        # the user to stop editing before sending the keymap from GUI RAM to
        # the firmware for a fast rescan (avoids slow I2C EEPROM reads).
        self._rescan_timer = QTimer()
        self._rescan_timer.setSingleShot(True)
        self._rescan_timer.setInterval(1000)
        self._rescan_timer.timeout.connect(self._do_ram_rescan)

        # Follow keymap edits made on the keyboard itself (the Key Mapper
        # menu): poll the keyboard's change count while this page is shown.
        self._device_km_timer = QTimer()
        self._device_km_timer.setInterval(1000)
        self._device_km_timer.timeout.connect(self._poll_device_keymap)
        self._device_km_timer.start()

    def _poll_device_keymap(self):
        """Redraw keys that were changed on the keyboard itself. Does nothing
        while the page is hidden, while a transfer owns the keyboard, or on a
        keyboard that does not report its own edits. Never raises."""
        try:
            kb = getattr(self, "keyboard", None)
            if not self.valid() or kb is None or not hasattr(kb, "poll_device_keymap_changes"):
                return
            if kb is not getattr(self.device, "keyboard", None):
                return
            # The keyboard picture lives in a graphics scene (ZoomView), where it
            # counts as shown whatever page is open: ask the view, which sits in
            # the page, whether the Keymap page is on screen.
            view = self.keyboard_zoom
            if not view.isVisible() or view.window().isMinimized():
                return
            from util import is_hid_transfer_active
            if is_hid_transfer_active():
                return
            if kb.poll_device_keymap_changes():
                self.refresh_layer_display()
                self.encoder_assign.set_layer(self.current_layer, kb)
        except Exception:
            pass

    def _prime_device_keymap_sync(self):
        """Take the keyboard's count of its own keymap edits now, right after
        the keymap was read: edits made on the keyboard before the Keymap page
        is first shown are then still picked up by the poll (its first call
        would otherwise only record the count, edits included). Never raises."""
        try:
            kb = self.keyboard
            if kb is None or not hasattr(kb, "poll_device_keymap_changes"):
                return
            from util import is_hid_transfer_active
            if is_hid_transfer_active():
                return
            kb.poll_device_keymap_changes()
        except Exception:
            pass

    def _do_ram_rescan(self):
        """Send keymap from GUI RAM to firmware and trigger fast rescan."""
        if self.keyboard and hasattr(self.keyboard, 'send_keymap_for_ram_rescan'):
            self.keyboard.send_keymap_for_ram_rescan()

    def _schedule_rescan(self):
        """Start or restart the debounced rescan timer."""
        self._rescan_timer.start()

    def set_matrix_test_reference(self, matrix_test):
        """Set reference to MatrixTest widget for status value adjustments"""
        self.matrix_test = matrix_test
        # Also set the reference in the quick_actuation widget
        self.quick_actuation.set_matrix_test_reference(matrix_test)

    def _build_preset_menu(self):
        """Build nested menu with categories as submenus. Selecting applies immediately."""
        menu = QMenu(self.preset_menu_btn)
        for cat_name, entries in PRESET_CATEGORIES:
            # Basic mode: whole-keyboard layouts only (no splits or QuickBuild fills)
            if ui_mode.pages_simplified() and cat_name not in ("Typing", "Music"):
                continue
            submenu = menu.addMenu(cat_name)
            for name, description, generator, preset_type in entries:
                action = submenu.addAction(name)
                action.setToolTip(description)
                entry = (name, description, generator, preset_type)
                action.triggered.connect(
                    lambda checked, e=entry: self._on_preset_selected_apply(e))
        self.preset_menu_btn.setMenu(menu)

    def _build_encoder_menu(self):
        """Build encoder menu (single encoder, flat preset list)."""
        menu = QMenu(self.encoder_menu_btn)

        # Single-encoder hardware: one flat list of presets applied to the encoder.
        for name, description, enc_cw, enc_ccw, enc_press in INDIVIDUAL_ENCODER_PRESETS:
            action = menu.addAction(name)
            action.setToolTip(description)
            entry = (name, description, enc_cw, enc_ccw, enc_press)
            action.triggered.connect(
                lambda checked, e=entry: self._on_individual_encoder_selected(e))

        self.encoder_menu_btn.setMenu(menu)

    def _on_preset_selected_apply(self, entry):
        """Handle preset selection — immediately show apply dialog."""
        if self.keyboard is None:
            return

        name, description, generator, preset_type = entry
        self.preset_menu_btn.setText(name)
        self.preset_menu_btn.setToolTip(description)

        if preset_type == PRESET_TYPE_TUNING:
            self._apply_tuning_preset(name, description, generator)
        elif preset_type == PRESET_TYPE_KEYBOARD:
            self._apply_tuning_preset(name, description, generator)
        elif preset_type == PRESET_TYPE_QB_ROW:
            self._apply_quickbuild_fill(name, description, generator, column=False)
        elif preset_type == PRESET_TYPE_QB_COLUMN:
            self._apply_quickbuild_fill(name, description, generator, column=True)

    def _apply_tuning_preset(self, name, description, generator):
        """Show dialog for tuning preset with row selection checkboxes."""
        dlg = QDialog(None)
        dlg.setWindowTitle(tr("KeymapEditor", "Apply Tuning Preset"))
        dlg.setMinimumWidth(320)
        layout = QVBoxLayout()
        dlg.setLayout(layout)

        # Preset info
        info = QLabel(tr("KeymapEditor",
                         '<b>{}</b><br><i>{}</i>'.format(name, description)))
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(8)

        # Row selection
        row_label = QLabel(tr("KeymapEditor", "Select rows to overwrite:"))
        row_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(row_label)

        row_checks = []
        row_grid = QGridLayout()
        row_grid.setSpacing(4)
        for i in range(5):
            # User-facing: Row 1 (top) to Row 5 (bottom) = matrix rows 0-4
            cb = QCheckBox(tr("KeymapEditor", "Row {} {}".format(
                i + 1, "(top)" if i == 0 else "(bottom)" if i == 4 else "")))
            cb.setChecked(True)
            row_checks.append(cb)
            row_grid.addWidget(cb, i // 3, i % 3)
        layout.addLayout(row_grid)

        # Select all / none buttons
        sel_layout = QHBoxLayout()
        sel_all = QPushButton(tr("KeymapEditor", "Select All"))
        sel_all.clicked.connect(lambda: [cb.setChecked(True) for cb in row_checks])
        sel_none = QPushButton(tr("KeymapEditor", "Select None"))
        sel_none.clicked.connect(lambda: [cb.setChecked(False) for cb in row_checks])
        sel_layout.addWidget(sel_all)
        sel_layout.addWidget(sel_none)
        sel_layout.addStretch()
        layout.addLayout(sel_layout)

        layout.addSpacing(8)

        warn = QLabel(tr("KeymapEditor",
                         "This will overwrite the selected rows on Layer {}.".format(
                             self.current_layer + 1)))
        warn.setStyleSheet("color: #c00; font-size: 9pt;")
        layout.addWidget(warn)

        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec_() != QDialog.Accepted:
            return

        # Determine which matrix rows are selected (user row 1-5 = matrix row 0-4)
        selected_rows = [i for i, cb in enumerate(row_checks) if cb.isChecked()]
        if not selected_rows:
            return

        # Generate preset grid scaled to the number of selected rows
        num_rows = len(selected_rows)
        grid = generator(num_rows)

        # Map generated grid rows to selected matrix rows
        # Grid row 0 = topmost selected row, grid row -1 = bottommost selected row
        layer = self.current_layer
        for grid_idx, matrix_row in enumerate(selected_rows):
            for col in range(14):
                keycode = grid[grid_idx][col]
                self.keyboard.set_key(layer, matrix_row, col, keycode)

        self.refresh_layer_display()
        self._schedule_rescan()

    def _apply_quickbuild_fill(self, name, description, generator, column):
        """Fill one row (14 keys) or one column (5 keys) with QuickBuild keys,
        counting up from a starting QuickBuild number the user picks."""
        rows, cols = 5, 14
        length = rows if column else cols
        what = "column" if column else "row"

        dlg = QDialog(None)
        dlg.setWindowTitle(tr("KeymapEditor", "Fill {} with QuickBuild keys").format(what))
        dlg.setMinimumWidth(340)
        layout = QVBoxLayout()
        dlg.setLayout(layout)

        info = QLabel(tr("KeymapEditor",
                         '<b>{}</b><br><i>{}</i>'.format(name, description)))
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(8)

        form = QGridLayout()
        form.addWidget(QLabel(tr("KeymapEditor", "Apply to {}:").format(what)), 0, 0)
        pos_spin = QSpinBox()
        pos_spin.setMinimum(1)
        pos_spin.setMaximum(cols if column else rows)
        pos_spin.setValue(1)
        pos_spin.setToolTip("Column 1 = left, Column 14 = right" if column
                            else "Row 1 = top, Row 5 = bottom")
        form.addWidget(pos_spin, 0, 1)
        form.addWidget(QLabel(tr("KeymapEditor", "Start at QuickBuild:")), 1, 0)
        start_spin = QSpinBox()
        start_spin.setMinimum(1)
        start_spin.setMaximum(100)
        start_spin.setValue(1)
        form.addWidget(start_spin, 1, 1)
        form.setColumnStretch(2, 1)
        layout.addLayout(form)

        span = QLabel()
        span.setStyleSheet("font-size: 9pt;")
        layout.addWidget(span)

        def update_span():
            start = start_spin.value()
            end = min(100, start + length - 1)
            filled = end - start + 1
            text = "Keys: QuickBuild {} to {}".format(start, end)
            if filled < length:
                text += " (the last {} key(s) are left unchanged)".format(length - filled)
            span.setText(text)
        start_spin.valueChanged.connect(update_span)
        update_span()

        layout.addSpacing(8)
        warn = QLabel(tr("KeymapEditor",
                         "This will overwrite the selected {} on Layer {}.".format(
                             what, self.current_layer + 1)))
        warn.setStyleSheet("color: #c00; font-size: 9pt;")
        layout.addWidget(warn)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec_() != QDialog.Accepted:
            return

        pos = pos_spin.value() - 1
        keycodes = generator(start_spin.value(), length)
        layer = self.current_layer
        for i, kc in enumerate(keycodes):
            # Column fills top to bottom, row fills left to right.
            row, col = (i, pos) if column else (pos, i)
            self.keyboard.set_key(layer, row, col, kc)

        self.refresh_layer_display()
        self._schedule_rescan()

    def _on_individual_encoder_selected(self, entry):
        """Handle encoder preset — confirm and apply to the single encoder."""
        if self.keyboard is None:
            return

        name, description, enc_cw, enc_ccw, enc_press = entry
        self.encoder_menu_btn.setText(name)
        self.encoder_menu_btn.setToolTip(description)

        ret = QMessageBox.question(
            None,
            tr("KeymapEditor", "Apply Encoder Preset"),
            tr("KeymapEditor",
               'Apply "{}" encoder preset to Layer {}?\n\n'
               '{}\n\n'
               'This will overwrite the encoder assignment.'.format(
                   name, self.current_layer + 1, description)),
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return

        layer = self.current_layer
        # Single encoder = enc_idx 0; press is the firmware click at row 5, col 0.
        self.keyboard.set_encoder(layer, 0, 1, enc_cw)
        self.keyboard.set_encoder(layer, 0, 0, enc_ccw)
        self.keyboard.set_key(layer, 5, 0, enc_press)

        self.encoder_assign.set_layer(self.current_layer, self.keyboard)
        self.refresh_layer_display()
        self._schedule_rescan()

    def on_empty_space_clicked(self):
        self.container.deselect()
        self.encoder_assign.deselect()
        self.container.update()

    def on_keycode_changed(self, code):
        # Joystick functions are attached to the selected key, not placed on it.
        fid = joystick_function_id(code)
        if fid:
            self._attach_joystick_to_selection(fid)
            return
        # Check if encoder button is selected
        if self.encoder_assign.selected_button is not None:
            self.set_encoder_keycode(self.encoder_assign.selected_button, code)
        else:
            # Otherwise, set keyboard key
            self.set_key(code)

    def rebuild_layers(self):
        # delete old layer labels
        for label in self.layer_buttons:
            label.hide()
            label.deleteLater()
        self.layer_buttons = []

        from protocol.feature_names import get_feature_name_manager, FEATURE_LAYER
        mgr = get_feature_name_manager()

        # create new layer labels
        for x in range(self.keyboard.layers):
            layer_name = mgr.get_name(FEATURE_LAYER, x)
            btn = SquareButton(str(x + 1))
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setRelSize(1.667)
            btn.setCheckable(True)
            btn.setToolTip(layer_name)
            btn.clicked.connect(lambda state, idx=x: self.switch_layer(idx))
            self.layout_layers.addWidget(btn)
            self.layer_buttons.append(btn)
        for x in range(0,2):
            btn = SquareButton("-") if x else SquareButton("+")
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCheckable(False)
            btn.clicked.connect(lambda state, idx=x: self.adjust_size(idx))
            self.layout_size.addWidget(btn)
            self.layer_buttons.append(btn)

    def set_helper_visible(self, visible):
        """Show or hide the helper panel beside the keyboard; the choice is remembered."""
        self.quick_actuation.setVisible(visible)
        self.helper_toggle.setText("\u25C2  Hide helper" if visible else "Show helper  \u25B8")
        self.helper_toggle.setToolTip("Hide the layer helper" if visible
                                      else "Show the layer helper: layer name, actuation and MIDI settings")
        QSettings("MIDIswitch", "SwitchStation").setValue("keymap_helper_visible", bool(visible))

    def adjust_size(self, minus):
        self.keyboard_zoom.set_zoom(self.keyboard_zoom.zoom + (-0.1 if minus else 0.1))

    def _fit_keyboard_area(self):
        self._keyboard_page.layout().activate()
        sa = self._keyboard_scroll
        page = self._keyboard_page.sizeHint()
        height = page.height() + 2 * sa.frameWidth() + 2
        # a page wider than the area gets a horizontal scroll bar, which takes height too
        if page.width() > sa.width() - 2 * sa.frameWidth():
            height += sa.style().pixelMetric(QStyle.PM_ScrollBarExtent, None, sa)
        if sa.maximumHeight() != height:
            sa.setMaximumHeight(height)
        self._share_height()

    def _share_height(self):
        """The keyboard area gets its whole height first, the keycode panel the
        rest (never less than its own minimum). Done by capping the panel's
        height, which (unlike a minimum on the keyboard area) never stops the
        window from being made smaller."""
        sa = self._keyboard_scroll
        holder = sa.parentWidget()
        if holder is None:
            return
        if not getattr(self, "_watching_holder", None) is holder:
            holder.installEventFilter(self)
            self._watching_holder = holder
        m = self.contentsMargins()
        room = holder.height() - m.top() - m.bottom() - max(0, self.spacing())
        panel_min = self.tabbed_keycodes.minimumSizeHint().height()
        cap = max(panel_min, room - sa.maximumHeight())
        if self.tabbed_keycodes.maximumHeight() != cap:
            self.tabbed_keycodes.setMaximumHeight(cap)

    def eventFilter(self, obj, ev):
        if obj is getattr(self, "_watching_holder", None) and ev.type() == QEvent.Resize:
            self._fit_keyboard_area()
        return super().eventFilter(obj, ev)

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            self._prime_device_keymap_sync()

            # get number of layers
            self.rebuild_layers()

            self.container.set_keys(self.keyboard.keys, self.keyboard.encoders)

            self.current_layer = 0
            self.on_layout_changed()

            self.tabbed_keycodes.recreate_keycode_buttons()
            # NOTE: the shared tray (TabbedKeycodes.tray) is deliberately NOT
            # recreated here. Every KeymapEditor.rebuild() runs inside
            # MainWindow.rebuild(), which recreates the tray exactly once at
            # the end (after set_keyboard/set_editors), so doing it here too
            # rebuilt tens of thousands of buttons a second time per connect.

            # Initialize encoder widget with keyboard data
            self.encoder_assign.set_layer(self.current_layer, self.keyboard)

            # Load the device's navigation layer (None = firmware predates the
            # nav-layer HID command; control shows layer 1 and stays disabled).
            nl = None
            if hasattr(self.keyboard, "get_nav_layer"):
                nl = self.keyboard.get_nav_layer()
            self.nav_layer_supported = nl is not None
            self.nav_layer = nl if nl is not None else 0
            self.nav_layer_checkbox.setEnabled(self.nav_layer_supported)
            if not self.nav_layer_supported:
                self.nav_layer_checkbox.setToolTip(tr(
                    "KeymapEditor",
                    "Changing the navigation layer requires a firmware update."))

            self.refresh_layer_display()

        # Set device for quick actuation widget (loads all layers once)
        self.quick_actuation.set_device(device)
        if self.valid():
            self.quick_actuation.set_layer(self.current_layer)
        self.container.setEnabled(self.valid())

    def valid(self):
        return isinstance(self.device, VialKeyboard)

    def save_layout(self):
        return self.keyboard.save_layout()

    def restore_layout(self, data):
        if json.loads(data.decode("utf-8")).get("uid") != self.keyboard.keyboard_id:
            ret = QMessageBox.question(self.widget(), "",
                                       tr("KeymapEditor", "Saved keymap belongs to a different keyboard,"
                                                          " are you sure you want to continue?"),
                                       QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.keyboard.restore_layout(data)
        self.refresh_layer_display()
        # Schedule rescan via debounce timer rather than calling it directly,
        # because main_window.on_layout_load() calls rebuild() immediately
        # after this returns, and a synchronous rescan would leave stale HID
        # responses in the USB buffer that corrupt the subsequent reload.
        self._schedule_rescan()

    def on_any_keycode(self):
        if self.container.active_key is None:
            return
        keycode_filter = keycode_filter_masked if self.container.active_mask else None
        self.dlg = KeycodeSearchDialog(keycode_filter, self.container.window())
        self.dlg.finished.connect(self.on_dlg_finished)
        self.dlg.setModal(True)
        self.dlg.show()

    def on_dlg_finished(self, res):
        if res > 0 and self.dlg.value:
            self.on_keycode_changed(self.dlg.value)

    def code_for_widget(self, widget):
        if widget.desc.row is not None:
            return self.keyboard.layout[(self.current_layer, widget.desc.row, widget.desc.col)]
        else:
            return self.keyboard.encoder_layout[(self.current_layer, widget.desc.encoder_idx,
                                                 widget.desc.encoder_dir)]

    def refresh_layer_display(self):
        """ Refresh text on key widgets to display data corresponding to current layer """

        # No container.update_layout() here: that re-derives every keycap's
        # polygons/paths (~7 ms for 70 keys) and is only needed when the
        # geometry changes (set_keys, resize, scale, layout options) — those
        # paths call it themselves. This refresh only relabels the keys.

        from protocol.feature_names import get_feature_name_manager, FEATURE_LAYER
        mgr = get_feature_name_manager()

        for idx, btn in enumerate(self.layer_buttons):
            btn.setEnabled(idx != self.current_layer)
            btn.setChecked(idx == self.current_layer)
            # Update tooltip with current layer name
            if self.keyboard and idx < self.keyboard.layers:
                layer_name = mgr.get_name(FEATURE_LAYER, idx)
                if idx == self.nav_layer:
                    layer_name = "{} — NAVIGATION LAYER".format(layer_name)
                btn.setToolTip(layer_name)

        self._update_nav_layer_display()

        for widget in self.container.widgets:
            code = self.code_for_widget(widget)
            KeycodeDisplay.display_keycode(widget, code)
        self._refresh_joystick_overlays()
        self.container.update()
        self.container.updateGeometry()

    # ------------------------------------------------------------------
    # Joystick functions attached to keys (active in Gaming Mode)
    # ------------------------------------------------------------------

    # Encoder-widget buttons that are real matrix keys: click, footswitch
    ENCODER_MATRIX_KEYS = {2: (5, 0), 3: (5, 2)}

    def _joystick_label(self, layer, row, col):
        if self.keyboard is None or not hasattr(self.keyboard, "get_gaming_bind"):
            return ""
        return JOYSTICK_FUNCTION_LABELS.get(self.keyboard.get_gaming_bind(layer, row, col), "")

    def _refresh_joystick_overlays(self):
        layer = self.current_layer
        for widget in self.container.widgets:
            if isinstance(widget, EncoderWidget2) or widget.desc.row is None or widget.desc.row < 0:
                widget.joystick_text = ""
                widget.joystick_icon = None
            else:
                fid = self.keyboard.get_gaming_bind(layer, widget.desc.row, widget.desc.col) \
                    if self.keyboard is not None and hasattr(self.keyboard, "get_gaming_bind") else 0
                widget.joystick_text = JOYSTICK_FUNCTION_LABELS.get(fid, "")
                widget.joystick_icon = JOYSTICK_FUNCTION_NAMES.get(fid)
        for idx, (row, col) in self.ENCODER_MATRIX_KEYS.items():
            self.encoder_assign.set_joystick(idx, self._joystick_label(layer, row, col))

    def _set_joystick(self, row, col, fid):
        """Attach joystick function `fid` (0 = remove) to row/col on the
        current layer. Replaces whatever joystick the key had."""
        if self.keyboard is None:
            return
        if not getattr(self.keyboard, "gaming_binds_supported", False):
            QMessageBox.warning(None, "Joystick keys",
                                "This keyboard needs a firmware update before joystick "
                                "functions can be attached to keys.")
            return
        if not self.keyboard.set_gaming_bind(self.current_layer, row, col, fid):
            QMessageBox.warning(None, "Joystick keys",
                                "Could not save the joystick function to the keyboard.")
        self._refresh_joystick_overlays()
        self.container.update()

    def _attach_joystick_to_selection(self, fid):
        sel = self.encoder_assign.selected_button
        if sel is not None:
            if sel in self.ENCODER_MATRIX_KEYS:
                self._set_joystick(*self.ENCODER_MATRIX_KEYS[sel], fid)
            return  # encoder turns cannot hold a joystick function
        key = self.container.active_key
        if key is None or isinstance(key, EncoderWidget2):
            return
        if key.desc.row is None or key.desc.row < 0 or key.desc.col < 0:
            return
        self._set_joystick(key.desc.row, key.desc.col, fid)

    def _joystick_remove_menu(self, row, col):
        # Act on the pick instead of waiting in exec_(): the web build cannot
        # run a nested event loop.
        from keycode_search_dialog import top_window
        menu = QMenu(top_window(self.container))       # not inside the zoom view
        act = menu.addAction(tr("KeymapEditor", "Remove Joystick button"))
        act.triggered.connect(lambda _=False, r=row, c=col: self._set_joystick(r, c, 0))
        menu.aboutToHide.connect(menu.deleteLater)
        self._joystick_menu = menu
        menu.popup(QCursor.pos())

    def on_joystick_overlay_clicked(self, key):
        if key is None or isinstance(key, EncoderWidget2):
            return
        self._joystick_remove_menu(key.desc.row, key.desc.col)

    def on_encoder_joystick_clicked(self, index):
        if index in self.ENCODER_MATRIX_KEYS:
            self._joystick_remove_menu(*self.ENCODER_MATRIX_KEYS[index])

    def switch_layer(self, idx):
        self.container.deselect()
        self.current_layer = idx
        # Update quick actuation widget layer (loads from memory, no lag)
        self.quick_actuation.set_layer(idx)
        # Update encoder widget layer (load from keyboard)
        self.encoder_assign.set_layer(idx, self.keyboard)
        self.refresh_layer_display()

    # ------------------------------------------------------------------
    # Navigation layer (the layer on-device menus read typed input from)
    # ------------------------------------------------------------------

    # Keys the on-device menus depend on: naming/search typing needs the full
    # alphabet, number-page nudges need the arrows, and ESC backs out of menus.
    NAV_REQUIRED_KEYS = frozenset(
        ["KC_" + chr(ord("A") + i) for i in range(26)]
        + ["KC_ESC", "KC_ESCAPE", "KC_UP", "KC_DOWN", "KC_LEFT", "KC_RIGHT"]
    )

    def _update_nav_layer_display(self):
        """Sync the nav-layer checkbox with the currently selected layer:
        a bold, bordered, ticked "NAVIGATION LAYER" when the selected layer IS
        the navigation layer, a plain "Make Navigation Layer" otherwise."""
        if not hasattr(self, "nav_layer_checkbox"):
            return
        is_nav = (self.current_layer == self.nav_layer)
        self.nav_layer_checkbox.blockSignals(True)
        self.nav_layer_checkbox.setChecked(is_nav)
        if is_nav:
            self.nav_layer_checkbox.setText(tr("KeymapEditor", "NAVIGATION LAYER"))
            self.nav_layer_checkbox.setStyleSheet(
                "QCheckBox { font-weight: bold; border: 2px solid palette(highlight); "
                "border-radius: 4px; padding: 2px 6px; }")
        else:
            self.nav_layer_checkbox.setText(tr("KeymapEditor", "Make Navigation Layer"))
            self.nav_layer_checkbox.setStyleSheet("QCheckBox { padding: 2px 6px; }")
        self.nav_layer_checkbox.blockSignals(False)

    def _nav_warning(self, suppress_key, text):
        """Show a Yes/No navigation-layer warning with a "do not show again"
        checkbox. Returns True when the action may proceed. The suppression is
        only persisted when the user proceeds (Yes), so a suppressed dialog can
        never block a later confirmation."""
        settings = QSettings("MIDIswitch", "SwitchStation")
        if settings.value(suppress_key, False, type=bool):
            return True
        box = QMessageBox(self.widget())
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("KeymapEditor", "Navigation Layer Warning"))
        box.setText(text)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        dont_show = QCheckBox(tr("KeymapEditor", "Do not show this message again"))
        box.setCheckBox(dont_show)
        if sys.platform == "emscripten":
            # The web build cannot wait for the answer (no nested event
            # loop): show the warning as a notice and let the change go ahead.
            box.setStandardButtons(QMessageBox.Ok)
            box.setCheckBox(None)
            box.setModal(False)
            box.show()
            self._nav_notice = box
            return True
        ret = box.exec_()
        if ret == QMessageBox.Yes and dont_show.isChecked():
            settings.setValue(suppress_key, True)
        return ret == QMessageBox.Yes

    def on_nav_layer_clicked(self, checked):
        """Handle the "Make Navigation Layer" checkbox click."""
        if not checked:
            # There must always be a navigation layer — unticking the current
            # one is meaningless; pick a different layer and tick it there.
            self._update_nav_layer_display()
            return
        if not self.nav_layer_supported or self.keyboard is None:
            self._update_nav_layer_display()
            return
        if self.current_layer == self.nav_layer:
            self._update_nav_layer_display()
            return

        proceed = self._nav_warning(
            "nav_layer/suppress_change_warning",
            tr("KeymapEditor",
               "!WARNING: YOU ARE TRYING TO CHANGE THE NAVIGATION LAYER ON "
               "THE DEVICE.\n\nTHE NAVIGATION LAYER IS USED TO NAVIGATE MENUS "
               "ON THE DEVICE AND IF CHANGED MAY MAKE YOU UNABLE TO NAVIGATE "
               "MENUS ON THE DEVICE.\n\nARE YOU SURE YOU WANT TO PROCEED?"))
        if not proceed:
            self._update_nav_layer_display()
            return

        if self.keyboard.set_nav_layer(self.current_layer):
            self.nav_layer = self.current_layer
        else:
            QMessageBox.warning(
                self.widget(),
                tr("KeymapEditor", "Navigation Layer"),
                tr("KeymapEditor", "Failed to set the navigation layer on the device."))
        self.refresh_layer_display()

    def _nav_layer_edit_allowed(self, layer, row, col, new_keycode):
        """Gate a keymap edit on the NAVIGATION layer: if it would remove the
        last A-Z / ESC / arrow key the on-device menus depend on, warn (with a
        "do not show again" option) before proceeding."""
        if layer != self.nav_layer or self.keyboard is None:
            return True
        old = self.keyboard.layout.get((layer, row, col), "KC_NO")
        if old not in self.NAV_REQUIRED_KEYS or old == new_keycode:
            return True
        # Still available somewhere else on this layer's physical rows?
        for r2 in range(5):
            for c2 in range(14):
                if (r2, c2) == (row, col):
                    continue
                if self.keyboard.layout.get((layer, r2, c2), "KC_NO") == old:
                    return True
        return self._nav_warning(
            "nav_layer/suppress_required_key_warning",
            tr("KeymapEditor",
               "WARNING: A-Z, ESC AND ARROW KEYS ARE NECESSARY FOR THE "
               "NAVIGATION LAYER.\n\nTHE NAVIGATION LAYER IS USED TO NAVIGATE "
               "MENUS ON THE DEVICE AND IF CHANGED MAY MAKE YOU UNABLE TO "
               "NAVIGATE MENUS ON THE DEVICE.\n\nARE YOU SURE YOU WANT TO "
               "PROCEED?"))

    def set_key(self, keycode):
        """ Change currently selected key to provided keycode """

        if self.container.active_key is None:
            return

        if isinstance(self.container.active_key, EncoderWidget2):
            self.set_key_encoder(keycode)
        else:
            self.set_key_matrix(keycode)

        self.container.select_next()

    def set_encoder_keycode(self, button_index, keycode):
        """Set keycode for encoder/sustain button and send to keyboard via USB"""
        l = self.current_layer

        # Map button index to encoder parameters or matrix key positions
        # Button 0: Encoder Up (enc_idx=0, dir=1) - encoder rotation
        # Button 1: Encoder Down (enc_idx=0, dir=0) - encoder rotation
        # Button 2: Encoder Press - matrix key at row=5, col=0 (firmware PB0 click)
        # Button 3: Sustain Pedal - matrix key at row=5, col=2

        # Matrix key mappings for encoder click and sustain pedal
        matrix_key_mapping = {
            2: (5, 0),  # Encoder Press -> row 5, col 0
            3: (5, 2),  # Sustain Pedal -> row 5, col 2
        }

        if button_index in matrix_key_mapping:
            # These are regular matrix keys, not encoder actions
            row, col = matrix_key_mapping[button_index]
            self.keyboard.set_key(l, row, col, keycode)
        else:
            # Map button index to encoder index and direction (rotation only)
            encoder_mapping = {
                0: (0, 1),  # Encoder Up (CW)
                1: (0, 0),  # Encoder Down (CCW)
            }

            if button_index in encoder_mapping:
                enc_idx, direction = encoder_mapping[button_index]
                self.keyboard.set_encoder(l, enc_idx, direction, keycode)

        # Update the button display
        self.encoder_assign.set_keycode(button_index, keycode)
        self.refresh_layer_display()
        self._schedule_rescan()

    def set_key_encoder(self, keycode):
        l, i, d = self.current_layer, self.container.active_key.desc.encoder_idx,\
                            self.container.active_key.desc.encoder_dir

        # if masked, ensure that this is a byte-sized keycode
        if self.container.active_mask:
            if not Keycode.is_basic(keycode):
                return
            kc = Keycode.find_outer_keycode(self.keyboard.encoder_layout[(l, i, d)])
            if kc is None:
                return
            keycode = kc.code_id.replace("(kc)", "({})".format(keycode))

        self.keyboard.set_encoder(l, i, d, keycode)
        self.refresh_layer_display()
        self._schedule_rescan()

    def set_key_matrix(self, keycode):
        l, r, c = self.current_layer, self.container.active_key.desc.row, self.container.active_key.desc.col

        if r >= 0 and c >= 0:
            # if masked, ensure that this is a byte-sized keycode
            if self.container.active_mask:
                if not Keycode.is_basic(keycode):
                    return
                kc = Keycode.find_outer_keycode(self.keyboard.layout[(l, r, c)])
                if kc is None:
                    return
                keycode = kc.code_id.replace("(kc)", "({})".format(keycode))

            # Removing the last A-Z / ESC / arrow key from the NAVIGATION
            # layer can make the on-device menus impossible to drive — warn.
            if not self._nav_layer_edit_allowed(l, r, c, keycode):
                return

            # Picking Space for a key that already shows Space still writes it:
            # the keyboard may hold the other raw value for that key (see
            # read_aliases in keycodes_v6.py), which set_key would skip as
            # "unchanged".
            if keycode == self.keyboard.layout.get((l, r, c)) and Keycode.has_read_alias(keycode):
                self.keyboard.layout[(l, r, c)] = None
                try:
                    self.keyboard.set_key(l, r, c, keycode)
                finally:
                    if self.keyboard.layout.get((l, r, c)) is None:
                        self.keyboard.layout[(l, r, c)] = keycode
            else:
                self.keyboard.set_key(l, r, c, keycode)
            self.refresh_layer_display()
            self._schedule_rescan()

    def on_key_clicked(self):
        """ Called when a key on the keyboard widget is clicked """
        # Deselect encoder buttons when keyboard is clicked
        self.encoder_assign.deselect()

        # Selection only changed — repaint; the labels are already current
        # (relabelling all keys here ran on every click AND every drag-paint
        # move, on top of the relabel set_key just did).
        self.container.update()
        if self.container.active_mask:
            self.tabbed_keycodes.set_keycode_filter(keycode_filter_masked)
        else:
            self.tabbed_keycodes.set_keycode_filter(None)

    def on_key_deselected(self):
        self.tabbed_keycodes.set_keycode_filter(None)

    def on_keycode_dropped(self, key, mask, code_id):
        """A palette keycode was dropped on ``key`` (see KeyboardWidget2
        keycode_dropped): select that key and assign exactly like a palette
        click would, then leave it selected (no select_next — the drop named
        its target, so the next palette click still lands there)."""
        if self.keyboard is None or key is None:
            return
        if joystick_function_id(code_id):
            mask = False  # a joystick function attaches to the whole key
        elif mask and not Keycode.is_basic(code_id):
            return
        # Run after the drop event returns: the drop is delivered inside the
        # palette button's QDrag.exec_() loop, and the assignment can raise a
        # modal warning (navigation-layer guard) that should not nest in it.
        QTimer.singleShot(0, lambda: self._assign_dropped_keycode(key, mask, code_id))

    def _assign_dropped_keycode(self, key, mask, code_id):
        if self.keyboard is None or key not in self.container.widgets:
            return
        self.encoder_assign.deselect()
        self.container.active_key = key
        self.container.active_mask = mask
        fid = joystick_function_id(code_id)
        if fid:
            if not isinstance(key, EncoderWidget2):
                self._set_joystick(key.desc.row, key.desc.col, fid)
            self.on_key_clicked()
            return
        if isinstance(key, EncoderWidget2):
            self.set_key_encoder(code_id)
        else:
            self.set_key_matrix(code_id)
        self.on_key_clicked()

    def on_encoder_clicked(self):
        """ Called when an encoder button is clicked """
        # Deselect keyboard keys when encoder button is clicked
        self.container.deselect()
        self.container.update()

        # No filter needed for encoder assignments
        self.tabbed_keycodes.set_keycode_filter(None)

    def on_layout_changed(self):
        if self.keyboard is None:
            return

        self.container.update_layout()
        # the footswitch / encoder buttons follow the keyboard photo
        self.keyboard_overlay.place_encoder_widget()
        self.refresh_layer_display()
        self.keyboard.set_layout_options(self.layout_editor.pack())

    def on_keymap_override(self):
        self.refresh_layer_display()