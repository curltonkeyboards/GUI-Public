# SPDX-License-Identifier: GPL-2.0-or-later
import json
import struct

from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QVBoxLayout, QMessageBox, QWidget,
                              QGroupBox, QSlider, QCheckBox, QPushButton, QComboBox, QFrame,
                              QSizePolicy, QScrollArea, QTabWidget, QDialog, QDialogButtonBox,
                              QSpinBox, QGridLayout, QMenu, QToolButton, QAction, QInputDialog)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer

from widgets.combo_box import ArrowComboBox
from any_keycode_dialog import AnyKeycodeDialog
from editor.basic_editor import BasicEditor
from widgets.keyboard_widget import KeyboardWidget2, KeyboardWidgetSimple, EncoderWidget, EncoderWidget2
from keycodes.keycodes import Keycode
from widgets.square_button import SquareButton
from tabbed_keycodes import TabbedKeycodes, keycode_filter_masked
from util import tr, KeycodeDisplay
from vial_device import VialKeyboard
from editor.arpeggiator import DebugConsole
from editor.keymap_presets import (KEYMAP_PRESETS, ENCODER_PRESETS,
                                   INDIVIDUAL_ENCODER_PRESETS,
                                   PRESET_CATEGORIES,
                                   PRESET_TYPE_TUNING, PRESET_TYPE_SINGLE_ROW,
                                   PRESET_TYPE_KEYBOARD)
from protocol.keyboard_comm import (
    PARAM_CHANNEL_NUMBER, PARAM_TRANSPOSE_NUMBER, PARAM_TRANSPOSE_NUMBER2, PARAM_TRANSPOSE_NUMBER3,
    PARAM_HE_VELOCITY_CURVE, PARAM_HE_VELOCITY_MIN, PARAM_HE_VELOCITY_MAX,
    PARAM_KEYSPLIT_HE_VELOCITY_CURVE, PARAM_KEYSPLIT_HE_VELOCITY_MIN, PARAM_KEYSPLIT_HE_VELOCITY_MAX,
    PARAM_TRIPLESPLIT_HE_VELOCITY_CURVE, PARAM_TRIPLESPLIT_HE_VELOCITY_MIN, PARAM_TRIPLESPLIT_HE_VELOCITY_MAX,
    PARAM_BASE_SUSTAIN, PARAM_KEYSPLIT_SUSTAIN, PARAM_TRIPLESPLIT_SUSTAIN,
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
                'normal': 80,
                'midi': 80,
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

        self.setMinimumWidth(320)
        self.setMaximumWidth(320)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 0, 10)  # No right margin for flush layout
        self.setLayout(layout)

        # Layer name header with rename button (matches toggle/macro/delay title style)
        layer_header = QHBoxLayout()
        layer_header.setContentsMargins(0, 0, 0, 0)
        self.layer_title_label = QLabel("<b>Layer 0</b>")
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

        # Show MIDI Settings directly (no tab widget)
        self.midi_tab = self.create_midi_tab()
        layout.addWidget(self.midi_tab)

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
        top_row_layout.addWidget(self.create_help_label("Enable individual actuation point per key.\nConfigure in Trigger Settings tab."))
        top_row_layout.addWidget(self.enable_per_key_checkbox)

        top_row_layout.addWidget(self.create_help_label("Enable different actuation points per layer.\nWhen off, same actuation applies to all layers."))
        self.per_layer_checkbox = QCheckBox(tr("QuickActuationWidget", "Enable Per-Layer Actuation"))
        self.per_layer_checkbox.setStyleSheet("QCheckBox { font-weight: bold; font-size: 10px; } QCheckBox::indicator { border: 1px solid palette(mid); background-color: palette(button); width: 13px; height: 13px; } QCheckBox::indicator:checked { border: 1px solid palette(highlight); background-color: palette(highlight); }")
        self.per_layer_checkbox.stateChanged.connect(self.on_per_layer_toggled)
        top_row_layout.addWidget(self.per_layer_checkbox)

        top_row_layout.addStretch()
        layout.addLayout(top_row_layout)

        # Layer indicator (only visible in per-layer mode)
        self.layer_label = QLabel(tr("QuickActuationWidget", "Layer 0"))
        self.layer_label.setStyleSheet("QLabel { font-weight: bold; font-size: 10px; color: #666; }")
        self.layer_label.setVisible(False)
        layout.addWidget(self.layer_label, alignment=Qt.AlignCenter)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Per-key mode message (shown when per-key actuation is enabled)
        self.per_key_message = QLabel(tr("QuickActuationWidget", "Per-key actuation enabled.\nChange per key actuation in Trigger Settings tab."))
        self.per_key_message.setStyleSheet("QLabel { font-style: italic; font-size: 10px; color: #888; padding: 10px; }")
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
        self.normal_slider.setMinimum(0)
        self.normal_slider.setMaximum(100)
        self.normal_slider.setValue(80)
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
        self.midi_slider.setMinimum(0)
        self.midi_slider.setMaximum(100)
        self.midi_slider.setValue(80)
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
        self.save_btn.clicked.connect(self.on_save_actuation)
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
        self.simple_transpose_slider.setMinimum(-12)
        self.simple_transpose_slider.setMaximum(12)
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

        preset_label = QLabel(tr("QuickActuationWidget", "Playing Style:"))
        preset_label.setStyleSheet("QLabel { font-size: 14px; }")
        preset_label.setMinimumWidth(90)
        preset_label.setMaximumWidth(90)
        preset_row.addWidget(preset_label)

        self.simple_velocity_preset_combo = ArrowComboBox()
        self.simple_velocity_preset_combo.setFixedWidth(70)
        self.simple_velocity_preset_combo.setMaximumHeight(35)
        self.simple_velocity_preset_combo.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.simple_velocity_preset_combo.setEditable(True)
        self.simple_velocity_preset_combo.lineEdit().setReadOnly(True)
        self.simple_velocity_preset_combo.lineEdit().setAlignment(Qt.AlignCenter)
        # Factory curves (0-6)
        self.simple_velocity_preset_combo.addItem("Softest", 0)
        self.simple_velocity_preset_combo.addItem("Soft", 1)
        self.simple_velocity_preset_combo.addItem("Linear", 2)
        self.simple_velocity_preset_combo.addItem("Hard", 3)
        self.simple_velocity_preset_combo.addItem("Hardest", 4)
        self.simple_velocity_preset_combo.addItem("Aggro", 5)
        self.simple_velocity_preset_combo.addItem("Digital", 6)
        # User curves (7-56) - will be populated when keyboard connects
        for i in range(50):
            self.simple_velocity_preset_combo.addItem("User {}".format(i + 1), 7 + i)
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
        self.midi_transpose_slider.setMinimum(-12)
        self.midi_transpose_slider.setMaximum(12)
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

        curve_label = QLabel(tr("QuickActuationWidget", "Playing Style:"))
        curve_label.setStyleSheet("QLabel { font-size: 14px; }")
        curve_label.setMinimumWidth(100)
        curve_label.setMaximumWidth(100)
        curve_row.addWidget(curve_label)

        self.midi_velocity_curve = ArrowComboBox()
        self.midi_velocity_curve.setMaximumWidth(120)
        self.midi_velocity_curve.setMaximumHeight(30)
        self.midi_velocity_curve.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.midi_velocity_curve.setEditable(True)
        self.midi_velocity_curve.lineEdit().setReadOnly(True)
        self.midi_velocity_curve.lineEdit().setAlignment(Qt.AlignCenter)
        # Factory curves (0-6)
        self.midi_velocity_curve.addItem("Softest", 0)
        self.midi_velocity_curve.addItem("Soft", 1)
        self.midi_velocity_curve.addItem("Linear", 2)
        self.midi_velocity_curve.addItem("Hard", 3)
        self.midi_velocity_curve.addItem("Hardest", 4)
        self.midi_velocity_curve.addItem("Aggro", 5)
        self.midi_velocity_curve.addItem("Digital", 6)
        # User curves (7-56)
        for i in range(50):
            self.midi_velocity_curve.addItem("User {}".format(i + 1), 7 + i)
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
        self.keysplit_transpose_slider.setMinimum(-12)
        self.keysplit_transpose_slider.setMaximum(12)
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

        ks_curve_label = QLabel(tr("QuickActuationWidget", "Playing Style:"))
        ks_curve_label.setStyleSheet("QLabel { font-size: 14px; }")
        ks_curve_label.setMinimumWidth(100)
        ks_curve_label.setMaximumWidth(100)
        ks_curve_row.addWidget(ks_curve_label)

        self.keysplit_velocity_curve = ArrowComboBox()
        self.keysplit_velocity_curve.setMaximumWidth(120)
        self.keysplit_velocity_curve.setMaximumHeight(30)
        self.keysplit_velocity_curve.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.keysplit_velocity_curve.setEditable(True)
        self.keysplit_velocity_curve.lineEdit().setReadOnly(True)
        self.keysplit_velocity_curve.lineEdit().setAlignment(Qt.AlignCenter)
        # Factory curves (0-6)
        self.keysplit_velocity_curve.addItem("Softest", 0)
        self.keysplit_velocity_curve.addItem("Soft", 1)
        self.keysplit_velocity_curve.addItem("Linear", 2)
        self.keysplit_velocity_curve.addItem("Hard", 3)
        self.keysplit_velocity_curve.addItem("Hardest", 4)
        self.keysplit_velocity_curve.addItem("Aggro", 5)
        self.keysplit_velocity_curve.addItem("Digital", 6)
        # User curves (7-56)
        for i in range(50):
            self.keysplit_velocity_curve.addItem("User {}".format(i + 1), 7 + i)
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
        self.triplesplit_transpose_slider.setMinimum(-12)
        self.triplesplit_transpose_slider.setMaximum(12)
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

        ts_curve_label = QLabel(tr("QuickActuationWidget", "Playing Style:"))
        ts_curve_label.setStyleSheet("QLabel { font-size: 14px; }")
        ts_curve_label.setMinimumWidth(100)
        ts_curve_label.setMaximumWidth(100)
        ts_curve_row.addWidget(ts_curve_label)

        self.triplesplit_velocity_curve = ArrowComboBox()
        self.triplesplit_velocity_curve.setMaximumWidth(120)
        self.triplesplit_velocity_curve.setMaximumHeight(30)
        self.triplesplit_velocity_curve.setStyleSheet("QComboBox { padding: 0px; font-size: 14px; text-align: center; }")
        self.triplesplit_velocity_curve.setEditable(True)
        self.triplesplit_velocity_curve.lineEdit().setReadOnly(True)
        self.triplesplit_velocity_curve.lineEdit().setAlignment(Qt.AlignCenter)
        # Factory curves (0-6)
        self.triplesplit_velocity_curve.addItem("Softest", 0)
        self.triplesplit_velocity_curve.addItem("Soft", 1)
        self.triplesplit_velocity_curve.addItem("Linear", 2)
        self.triplesplit_velocity_curve.addItem("Hard", 3)
        self.triplesplit_velocity_curve.addItem("Hardest", 4)
        self.triplesplit_velocity_curve.addItem("Aggro", 5)
        self.triplesplit_velocity_curve.addItem("Digital", 6)
        # User curves (7-56)
        for i in range(50):
            self.triplesplit_velocity_curve.addItem("User {}".format(i + 1), 7 + i)
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

        return widget
        
    def update_per_key_ui_state(self, per_key_enabled):
        """Update UI state when per-key mode changes"""
        # Show/hide sliders and message based on per-key state
        self.sliders_container.setVisible(not per_key_enabled)
        self.per_key_message.setVisible(per_key_enabled)
        # Disable save button when per-key is enabled (managed in Trigger Settings)
        self.save_btn.setEnabled(not per_key_enabled)
    
    def on_per_layer_toggled(self):
        """Handle per-layer mode toggle"""
        self.per_layer_enabled = self.per_layer_checkbox.isChecked()

        # Show/hide layer label
        self.layer_label.setVisible(self.per_layer_enabled)

        # Update save button text
        if self.per_layer_enabled:
            self.save_btn.setText(tr("QuickActuationWidget", f"Save to Layer {self.current_layer}"))
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
                tr("QuickActuationWidget", "Per-key actuation is now enabled.\nUse Trigger Settings tab to configure individual keys.")
            )
            # Emit signal to request tab switch
            self.enable_per_key_requested.emit()

    # Factory preset vel_min/vel_max settings - must match firmware factory_preset_zones[]
    FACTORY_PRESET_VEL = {
        0: (1, 60),     # Softest
        1: (1, 90),     # Soft
        2: (1, 127),    # Linear
        3: (30, 127),   # Hard
        4: (60, 127),   # Hardest
        5: (80, 127),   # Aggro
        6: (127, 127),  # Digital
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
            label.setText(f"{value * 0.025:.2f}mm")
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
                ts.global_normal_value_label.setText(f"Act: {value * 0.025:.2f}mm")
            elif key == 'midi':
                ts.global_midi_slider.set_actuation(value)
                ts.global_midi_value_label.setText(f"Act: {value * 0.025:.2f}mm")

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
        self.normal_value_label.setText(f"{data['normal'] * 0.025:.2f}mm")

        self.midi_slider.setValue(data['midi'])
        self.midi_value_label.setText(f"{data['midi'] * 0.025:.2f}mm")

        # NOTE: Velocity mode is now managed in VelocityTab, not here

        self.syncing = False
    
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
        elif 7 <= curve_index <= 56:
            slot = curve_index - 7
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
        Factory curves (0-6) use hardcoded table. User curves (7-56) load from device."""
        vel_min = None
        vel_max = None

        if curve_index in self.FACTORY_PRESET_VEL:
            vel_min, vel_max = self.FACTORY_PRESET_VEL[curve_index]
        elif curve_index >= 7 and curve_index <= 56:
            # User curve - load from device
            slot = curve_index - 7
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
            self.simple_midi_widget.setVisible(False)
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
        # Adjust status values when disabling keysplit
        if not self.keysplit_enabled_checkbox.isChecked():
            self._adjust_status_values_on_keysplit_close()

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
        else:
            # Adjust status values when disabling triplesplit
            self._adjust_status_values_on_triplesplit_close()

        self.update_midi_container_view()
        if not self.syncing:
            self.save_midi_ui_to_memory()
            self._send_split_status()

    def set_matrix_test_reference(self, matrix_test):
        """Set reference to MatrixTest widget for status value adjustments"""
        self.matrix_test = matrix_test

    def _adjust_status_values_on_keysplit_close(self):
        """Adjust status values when keysplit window is closed
        - Status 3 (Both Splits On) -> 2 (TripleSplit On)
        - Status 1 (KeySplit On) -> 0 (Disable Keysplit)
        """
        if not self.matrix_test:
            return

        try:
            # Adjust channel split status
            current_value = self.matrix_test.key_split_status.currentData()
            if current_value == 3:  # Both Splits On -> TripleSplit On
                self.matrix_test.key_split_status.setCurrentIndex(2)
            elif current_value == 1:  # KeySplit On -> Disable Keysplit
                self.matrix_test.key_split_status.setCurrentIndex(0)

            # Adjust transpose split status
            current_value = self.matrix_test.key_split_transpose_status.currentData()
            if current_value == 3:  # Both Splits On -> TripleSplit On
                self.matrix_test.key_split_transpose_status.setCurrentIndex(2)
            elif current_value == 1:  # KeySplit On -> Disable Keysplit
                self.matrix_test.key_split_transpose_status.setCurrentIndex(0)

            # Adjust velocity split status
            current_value = self.matrix_test.key_split_velocity_status.currentData()
            if current_value == 3:  # Both Splits On -> TripleSplit On
                self.matrix_test.key_split_velocity_status.setCurrentIndex(2)
            elif current_value == 1:  # KeySplit On -> Disable Keysplit
                self.matrix_test.key_split_velocity_status.setCurrentIndex(0)
        except Exception as e:
            pass

    def _adjust_status_values_on_triplesplit_close(self):
        """Adjust status values when triplesplit window is closed
        - Status 3 (Both Splits On) -> 1 (KeySplit On)
        - Status 2 (TripleSplit On) -> 0 (Disable Keysplit)
        """
        if not self.matrix_test:
            return

        try:
            # Adjust channel split status
            current_value = self.matrix_test.key_split_status.currentData()
            if current_value == 3:  # Both Splits On -> KeySplit On
                self.matrix_test.key_split_status.setCurrentIndex(1)
            elif current_value == 2:  # TripleSplit On -> Disable Keysplit
                self.matrix_test.key_split_status.setCurrentIndex(0)

            # Adjust transpose split status
            current_value = self.matrix_test.key_split_transpose_status.currentData()
            if current_value == 3:  # Both Splits On -> KeySplit On
                self.matrix_test.key_split_transpose_status.setCurrentIndex(1)
            elif current_value == 2:  # TripleSplit On -> Disable Keysplit
                self.matrix_test.key_split_transpose_status.setCurrentIndex(0)

            # Adjust velocity split status
            current_value = self.matrix_test.key_split_velocity_status.currentData()
            if current_value == 3:  # Both Splits On -> KeySplit On
                self.matrix_test.key_split_velocity_status.setCurrentIndex(1)
            elif current_value == 2:  # TripleSplit On -> Disable Keysplit
                self.matrix_test.key_split_velocity_status.setCurrentIndex(0)
        except Exception as e:
            pass

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
        self.midi_settings['keysplit_velocity_curve'] = self.keysplit_velocity_curve.currentData()
        self.midi_settings['keysplit_velocity_min'] = self.keysplit_velocity_min.value()
        self.midi_settings['keysplit_velocity_max'] = self.keysplit_velocity_max.value()

        self.midi_settings['triplesplit_enabled'] = self.triplesplit_enabled_checkbox.isChecked()
        self.midi_settings['triplesplit_channel'] = self.triplesplit_channel_slider.value()
        self.midi_settings['triplesplit_transpose'] = self.triplesplit_transpose_slider.value()
        self.midi_settings['triplesplit_sustain'] = self.triplesplit_sustain_combo.currentData()
        self.midi_settings['triplesplit_velocity_curve'] = self.triplesplit_velocity_curve.currentData()
        self.midi_settings['triplesplit_velocity_min'] = self.triplesplit_velocity_min.value()
        self.midi_settings['triplesplit_velocity_max'] = self.triplesplit_velocity_max.value()

    def on_save_actuation(self):
        """Save actuation settings - to all layers or current layer depending on mode
        NOTE: velocity_mode, aftertouch settings are now GLOBAL and saved via Advanced tab.
        This function only saves actuation points (normal, midi) per-layer.
        """
        try:
            if not self.device or not isinstance(self.device, VialKeyboard):
                raise RuntimeError("Device not connected")

            # Get global settings for backward compatibility with firmware protocol
            global_settings = self.global_midi_settings

            if self.per_layer_enabled:
                # Save to current layer only
                data = self.layer_data[self.current_layer]
                flags = 0
                if data.get('rapidfire_enabled', False):
                    flags |= 0x01
                if data.get('midi_rapidfire_enabled', False):
                    flags |= 0x02

                vibrato_decay = global_settings.get('vibrato_decay_time', 10)
                # Protocol: 11 bytes (layer + 10 data bytes)
                # velocity/aftertouch fields use GLOBAL settings
                payload = bytearray([
                    self.current_layer,
                    data['normal'],
                    data['midi'],
                    global_settings.get('velocity_mode', 3),   # GLOBAL: Speed+Peak
                    10,  # vel_speed deprecated, use default
                    flags,
                    global_settings.get('aftertouch_mode', 0),      # GLOBAL
                    global_settings.get('aftertouch_cc', 255),      # GLOBAL
                    global_settings.get('vibrato_sensitivity', 50), # GLOBAL
                    vibrato_decay & 0xFF,
                    (vibrato_decay >> 8) & 0xFF
                ])

                if not self.device.keyboard.set_layer_actuation(payload):
                    raise RuntimeError(f"Failed to set actuation for layer {self.current_layer}")

                QMessageBox.information(None, "Success",
                    f"Layer {self.current_layer} actuation saved successfully!")
            else:
                # Save to all 12 layers
                vibrato_decay = global_settings.get('vibrato_decay_time', 10)
                for layer in range(12):
                    data = self.layer_data[layer]
                    flags = 0
                    if data.get('rapidfire_enabled', False):
                        flags |= 0x01
                    if data.get('midi_rapidfire_enabled', False):
                        flags |= 0x02

                    # Protocol: 11 bytes (layer + 10 data bytes)
                    # velocity/aftertouch fields use GLOBAL settings
                    payload = bytearray([
                        layer,
                        data['normal'],
                        data['midi'],
                        global_settings.get('velocity_mode', 3),   # GLOBAL: Speed+Peak
                        10,  # vel_speed deprecated, use default
                        flags,
                        global_settings.get('aftertouch_mode', 0),      # GLOBAL
                        global_settings.get('aftertouch_cc', 255),      # GLOBAL
                        global_settings.get('vibrato_sensitivity', 50), # GLOBAL
                        vibrato_decay & 0xFF,
                        (vibrato_decay >> 8) & 0xFF
                    ])

                    if not self.device.keyboard.set_layer_actuation(payload):
                        raise RuntimeError(f"Failed to set actuation for layer {layer}")

                QMessageBox.information(None, "Success",
                    "Actuation saved to all layers successfully!")

        except Exception as e:
            QMessageBox.critical(None, "Error",
                f"Failed to save actuation settings: {str(e)}")

    def update_user_curve_names(self, names):
        """Update user curve names in all velocity curve dropdowns (simple, basic, keysplit, triplesplit)"""
        combos = [self.simple_velocity_preset_combo, self.midi_velocity_curve,
                  self.keysplit_velocity_curve, self.triplesplit_velocity_curve]
        for combo in combos:
            for i, name in enumerate(names):
                idx = 7 + i  # Factory curves take indices 0-6
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
            for i in range(self.simple_velocity_preset_combo.count()):
                if self.simple_velocity_preset_combo.itemData(i) == base_curve:
                    self.simple_velocity_preset_combo.setCurrentIndex(i)
                    break
            for i in range(self.midi_velocity_curve.count()):
                if self.midi_velocity_curve.itemData(i) == base_curve:
                    self.midi_velocity_curve.setCurrentIndex(i)
                    break

            ks_curve = config.get('keysplit_he_velocity_curve', 2)
            for i in range(self.keysplit_velocity_curve.count()):
                if self.keysplit_velocity_curve.itemData(i) == ks_curve:
                    self.keysplit_velocity_curve.setCurrentIndex(i)
                    break

            ts_curve = config.get('triplesplit_he_velocity_curve', 2)
            for i in range(self.triplesplit_velocity_curve.count()):
                if self.triplesplit_velocity_curve.itemData(i) == ts_curve:
                    self.triplesplit_velocity_curve.setCurrentIndex(i)
                    break

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

        except Exception:
            pass
    
    def set_layer(self, layer):
        """Set current layer and load its settings if in per-layer mode"""
        self.current_layer = layer
        self.layer_label.setText(tr("QuickActuationWidget", f"Layer {layer}"))
        self.update_layer_title()

        # Update save button text if in per-layer mode
        if self.per_layer_enabled:
            self.save_btn.setText(tr("QuickActuationWidget", f"Save to Layer {layer}"))
            # Load from memory (fast, no device I/O)
            self.load_layer_from_memory()

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
            "Name for Layer {} (max {} chars, uppercase):".format(self.current_layer, MAX_NAME_LENGTH),
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


class EncoderAssignWidget(QWidget):
    """Widget for assigning keycodes to encoders and sustain pedal per layer"""

    clicked = pyqtSignal()  # Emitted when a button is clicked (for tabbed_keycodes integration)

    def __init__(self):
        super().__init__()

        self.current_layer = 0
        self.selected_button = None
        self.buttons = []
        # Single-encoder hardware: one rotary encoder (enc_idx 0) + sustain pedal.
        self.labels = [
            "Encoder Up",
            "Encoder Down",
            "Encoder Press",
            "Sustain Pedal"
        ]

        self.setMinimumWidth(185)
        self.setMaximumWidth(185)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        # Make background transparent so keyboard background shows through
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(5, 45, 5, 10)  # 45px top margin
        self.setLayout(layout)

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

        # Now add to UI layout in display order (sustain at top, then encoder)
        # Sustain pedal group - at top, center aligned with 20px left shift
        sustain_label = QLabel("Sustain Pedal")
        sustain_label.setStyleSheet("QLabel { font-size: 11px; font-weight: bold; background: transparent; }")
        sustain_label.setAlignment(Qt.AlignCenter)
        sustain_label_container = QHBoxLayout()
        sustain_label_container.addWidget(sustain_label)
        layout.addLayout(sustain_label_container)

        sustain_layout = QHBoxLayout()
        sustain_layout.setSpacing(5)
        sustain_layout.addSpacing(63)  # 20px left shift
        sustain_layout.addWidget(sustain_btn)
        sustain_layout.addStretch()
        layout.addLayout(sustain_layout)

        # Add 10px spacer below sustain button
        layout.addSpacing(23)

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

        encoder_container = QWidget()
        encoder_container.setAttribute(Qt.WA_TranslucentBackground)
        encoder_container.setStyleSheet("background: transparent;")
        encoder_container.setFixedSize(col_push + BTN, Q3 * 2 + BTN + 18)

        # Up: same column, shifted down 3/4 of a button height
        enc_up_btn.setParent(encoder_container)
        enc_up_btn.move(col_up, Q3)

        # Down: moved to the old Push column, shifted down 3/4 of a button height
        enc_down_btn.setParent(encoder_container)
        enc_down_btn.move(col_push, Q3)

        # Push: centered horizontally between the new Up/Down, a FURTHER 3/4 down
        col_push_center = (col_up + col_push) // 2  # 60
        enc_push_btn.setParent(encoder_container)
        enc_push_btn.move(col_push_center, Q3 * 2)

        # The only remaining encoder title: "Click" under the push button
        click_label = QLabel("Click", encoder_container)
        click_label.setStyleSheet("QLabel { font-size: 9px; background: transparent; }")
        click_label.setAlignment(Qt.AlignCenter)
        click_label.setGeometry(col_push_center, Q3 * 2 + BTN, BTN, 14)

        layout.addWidget(encoder_container)
        layout.addStretch()

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position encoder widget to overlay the left side of keyboard widget
        # Position it at the left edge of the keyboard widget, offset down by 30 pixels
        keyboard_pos = self.keyboard_widget.pos()
        self.encoder_widget.move(keyboard_pos.x(), keyboard_pos.y() + 30)


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

        # Connect encoder widget signals
        self.encoder_assign.clicked.connect(self.on_encoder_clicked)

        # Create overlay container with encoder widget overlaying keyboard
        self.keyboard_overlay = OverlayContainer(self.container, self.encoder_assign)

        # Layout with actuation on left, then keyboard with encoder overlay
        keyboard_layout = QHBoxLayout()
        keyboard_layout.setSpacing(0)  # No spacing between widgets
        keyboard_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        keyboard_layout.addStretch(1)  # Add stretch before
        keyboard_layout.addWidget(self.quick_actuation, 0, Qt.AlignTop)
        keyboard_layout.addWidget(self.keyboard_overlay, 0, Qt.AlignTop)
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
        elif preset_type == PRESET_TYPE_SINGLE_ROW:
            self._apply_single_row_preset(name, description, generator)

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
                             self.current_layer)))
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

    def _apply_single_row_preset(self, name, description, generator):
        """Show dialog for single-row preset with row picker."""
        dlg = QDialog(None)
        dlg.setWindowTitle(tr("KeymapEditor", "Apply Single-Row Preset"))
        dlg.setMinimumWidth(300)
        layout = QVBoxLayout()
        dlg.setLayout(layout)

        # Preset info
        info = QLabel(tr("KeymapEditor",
                         '<b>{}</b><br><i>{}</i>'.format(name, description)))
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(8)

        # Row picker
        row_layout = QHBoxLayout()
        row_layout.addWidget(QLabel(tr("KeymapEditor", "Apply to row:")))
        row_spin = QSpinBox()
        row_spin.setMinimum(1)
        row_spin.setMaximum(5)
        row_spin.setValue(1)  # Default to Row 1 (top)
        row_spin.setToolTip("Row 1 = top, Row 5 = bottom")
        row_layout.addWidget(row_spin)
        row_layout.addStretch()
        layout.addLayout(row_layout)

        layout.addSpacing(8)

        warn = QLabel(tr("KeymapEditor",
                         "This will overwrite the selected row on Layer {}.".format(
                             self.current_layer)))
        warn.setStyleSheet("color: #c00; font-size: 9pt;")
        layout.addWidget(warn)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec_() != QDialog.Accepted:
            return

        # User row 1-5 -> matrix row 0-4
        matrix_row = row_spin.value() - 1
        row_keycodes = generator()

        layer = self.current_layer
        for col in range(min(14, len(row_keycodes))):
            self.keyboard.set_key(layer, matrix_row, col, row_keycodes[col])

        self.refresh_layer_display()

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
                   name, self.current_layer, description)),
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

    def on_empty_space_clicked(self):
        self.container.deselect()
        self.encoder_assign.deselect()
        self.container.update()

    def on_keycode_changed(self, code):
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
            btn = SquareButton(str(x))
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

    def adjust_size(self, minus):
        if minus:
            self.container.set_scale(self.container.get_scale() - 0.1)
        else:
            self.container.set_scale(self.container.get_scale() + 0.1)
        self.refresh_layer_display()

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard

            # get number of layers
            self.rebuild_layers()

            self.container.set_keys(self.keyboard.keys, self.keyboard.encoders)

            self.current_layer = 0
            self.on_layout_changed()

            self.tabbed_keycodes.recreate_keycode_buttons()
            TabbedKeycodes.tray.recreate_keycode_buttons()

            # Initialize encoder widget with keyboard data
            self.encoder_assign.set_layer(self.current_layer, self.keyboard)

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
        current_code = self.code_for_widget(self.container.active_key)
        if self.container.active_mask:
            kc = Keycode.find_inner_keycode(current_code)
            current_code = kc.qmk_id

        self.dlg = AnyKeycodeDialog(current_code)
        self.dlg.finished.connect(self.on_dlg_finished)
        self.dlg.setModal(True)
        self.dlg.show()

    def on_dlg_finished(self, res):
        if res > 0:
            self.on_keycode_changed(self.dlg.value)

    def code_for_widget(self, widget):
        if widget.desc.row is not None:
            return self.keyboard.layout[(self.current_layer, widget.desc.row, widget.desc.col)]
        else:
            return self.keyboard.encoder_layout[(self.current_layer, widget.desc.encoder_idx,
                                                 widget.desc.encoder_dir)]

    def refresh_layer_display(self):
        """ Refresh text on key widgets to display data corresponding to current layer """

        self.container.update_layout()

        from protocol.feature_names import get_feature_name_manager, FEATURE_LAYER
        mgr = get_feature_name_manager()

        for idx, btn in enumerate(self.layer_buttons):
            btn.setEnabled(idx != self.current_layer)
            btn.setChecked(idx == self.current_layer)
            # Update tooltip with current layer name
            if self.keyboard and idx < self.keyboard.layers:
                layer_name = mgr.get_name(FEATURE_LAYER, idx)
                btn.setToolTip(layer_name)

        for widget in self.container.widgets:
            code = self.code_for_widget(widget)
            KeycodeDisplay.display_keycode(widget, code)
        self.container.update()
        self.container.updateGeometry()

    def switch_layer(self, idx):
        self.container.deselect()
        self.current_layer = idx
        # Update quick actuation widget layer (loads from memory, no lag)
        self.quick_actuation.set_layer(idx)
        # Update encoder widget layer (load from keyboard)
        self.encoder_assign.set_layer(idx, self.keyboard)
        self.refresh_layer_display()

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
            keycode = kc.qmk_id.replace("(kc)", "({})".format(keycode))

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
                keycode = kc.qmk_id.replace("(kc)", "({})".format(keycode))

            self.keyboard.set_key(l, r, c, keycode)
            self.refresh_layer_display()
            self._schedule_rescan()

    def on_key_clicked(self):
        """ Called when a key on the keyboard widget is clicked """
        # Deselect encoder buttons when keyboard is clicked
        self.encoder_assign.deselect()

        self.refresh_layer_display()
        if self.container.active_mask:
            self.tabbed_keycodes.set_keycode_filter(keycode_filter_masked)
        else:
            self.tabbed_keycodes.set_keycode_filter(None)

    def on_key_deselected(self):
        self.tabbed_keycodes.set_keycode_filter(None)

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

        self.refresh_layer_display()
        self.keyboard.set_layout_options(self.layout_editor.pack())

    def on_keymap_override(self):
        self.refresh_layer_display()