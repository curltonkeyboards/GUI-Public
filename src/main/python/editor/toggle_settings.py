# SPDX-License-Identifier: GPL-2.0-or-later
"""
Toggle Keys Settings Editor

Allows configuration of toggle key slots (TGL_00 - TGL_99).
Users configure slots with target keycodes and then assign TGL_XX keycodes to keys via the keymap editor.

Supports two modes:
- Standard toggle: Press to hold keycode, press again to release
- Multi-key toggle: Each press taps (press+release) a different keycode, cycling through up to 8
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QComboBox, QGroupBox, QMessageBox, QFrame, QCheckBox,
                              QSizePolicy, QScrollArea, QTabWidget, QGridLayout, QInputDialog)
from PyQt5.QtCore import Qt, pyqtSignal

from editor.basic_editor import BasicEditor
from editor.arpeggiator import DebugConsole
from protocol.toggle_protocol import (ProtocolToggle, ToggleSlot,
                                       TOGGLE_NUM_SLOTS, TOGGLE_KEY_BASE,
                                       TOGGLE_MULTI_MAX_KEYS, TOGGLE_MULTI_COLORS,
                                       TOGGLE_MULTI_COLOR_NAMES, TOGGLE_FLAG_MULTI_KEY,
                                       slot_to_toggle_keycode)
from keycodes.keycodes import Keycode
from widgets.key_widget import KeyWidget
from tabbed_keycodes import TabbedKeycodes, FilteredTabbedKeycodes, keycode_filter_any, keycode_filter_masked
from tabbed_keycodes import KeyboardTab, MusicTab, GamingTab, MacroTab, LightingTab, LightingTab2, MIDITab, SearchTab, SimpleTab
from keycodes.keycodes import (KEYCODES_MACRO_BASE, KEYCODES_MACRO, KEYCODES_TAP_DANCE, KEYCODES_BACKLIGHT,
                               KEYCODES_RGBSAVE, KEYCODES_RGB_KC_CUSTOM, KEYCODES_RGB_KC_COLOR,
                               KEYCODES_RGB_KC_CUSTOM2, KEYCODES_CLEAR, KEYCODES_GAMING,
                               KEYCODES_LAYERS_DF, KEYCODES_LAYERS_MO, KEYCODES_LAYERS_OSL)
from util import tr, KeycodeDisplay
from vial_device import VialKeyboard


class FilteredTabbedKeycodesNoLayers(QTabWidget):
    """Custom FilteredTabbedKeycodes without LayerTab to avoid overlay issues"""

    keycode_changed = pyqtSignal(str)
    anykey = pyqtSignal()

    def __init__(self, parent=None, keycode_filter=keycode_filter_any):
        super().__init__(parent)

        self.keycode_filter = keycode_filter

        # Create tabs WITHOUT LayerTab (Keyboard & Macro skips its Layer
        # section; LightingTab2 provides the overlay-safe layer pickers)
        self.tabs = [
            KeyboardTab(self, include_layer=False),
            MusicTab(self),
            LightingTab2(self, "Layers", KEYCODES_LAYERS_DF, KEYCODES_LAYERS_MO, KEYCODES_LAYERS_OSL),
            MIDITab(self),
            SearchTab(self),
            SimpleTab(self, " ", KEYCODES_CLEAR),
        ]

        for tab in self.tabs:
            tab.keycode_changed.connect(self.on_keycode_changed)

        self.recreate_keycode_buttons()
        KeycodeDisplay.notify_keymap_override(self)

    def on_keycode_changed(self, code):
        """Handle keycode changes from tabs"""
        if code == "Any":
            self.anykey.emit()
        else:
            self.keycode_changed.emit(Keycode.normalize(code))

    def recreate_keycode_buttons(self):
        """Recreate all keycode buttons based on filter"""
        prev_tab = self.tabText(self.currentIndex()) if self.currentIndex() >= 0 else ""
        while self.count() > 0:
            self.removeTab(0)

        for tab in self.tabs:
            tab.recreate_buttons(self.keycode_filter)
            if tab.has_buttons():
                self.addTab(tab, tr("TabbedKeycodes", tab.label))
                if tab.label == prev_tab:
                    self.setCurrentIndex(self.count() - 1)

    def on_keymap_override(self):
        """Update button labels when keymap overrides change"""
        for tab in self.tabs:
            tab.relabel_buttons()

    def set_keyboard(self, keyboard):
        """Set keyboard reference for tabs that need it"""
        for tab in self.tabs:
            if hasattr(tab, 'set_keyboard') and callable(tab.set_keyboard):
                tab.set_keyboard(keyboard)
            elif hasattr(tab, 'keyboard'):
                tab.keyboard = keyboard

    def set_editors(self, macro_recorder=None, tap_dance_editor=None, dks_settings=None, toggle_settings=None, **kwargs):
        """Set editor references for tabs that need them (e.g., MacroTab)"""
        for tab in self.tabs:
            if hasattr(tab, 'set_editors') and callable(tab.set_editors):
                tab.set_editors(macro_recorder, tap_dance_editor, dks_settings, toggle_settings)

    def refresh_macro_buttons(self):
        """Force refresh the MacroTab buttons"""
        for tab in self.tabs:
            if hasattr(tab, 'refresh_buttons') and callable(tab.refresh_buttons):
                tab.refresh_buttons()


class TabbedKeycodesNoLayers(QWidget):
    """Custom TabbedKeycodes without LayerTab for Toggle settings"""

    keycode_changed = pyqtSignal(str)
    anykey = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.target = None
        self.is_tray = False

        self.layout = QVBoxLayout()

        # Both palettes are expensive (thousands of buttons); build each on
        # first use — the one the current filter needs is created on the
        # first showEvent. State that arrives earlier is recorded/replayed.
        self.all_keycodes = None
        self.basic_keycodes = None
        self._current_filter = keycode_filter_any
        self._pal_kb = None
        self._pal_kb_pending = False
        self._pal_editors = None
        self._all_dirty = False
        self._basic_dirty = False

        self.setLayout(self.layout)

    def _make_palette(self, keycode_filter, dirty):
        opt = FilteredTabbedKeycodesNoLayers(keycode_filter=keycode_filter)
        opt.keycode_changed.connect(self.keycode_changed)
        opt.anykey.connect(self.anykey)
        self.layout.addWidget(opt)
        opt.hide()
        need_recreate = dirty
        if self._pal_kb_pending:
            opt.set_keyboard(self._pal_kb)
            need_recreate = True
        if self._pal_editors is not None:
            opt.set_editors(**self._pal_editors)
            need_recreate = True
        if need_recreate:
            opt.recreate_keycode_buttons()
        return opt

    def _apply_current_filter(self):
        if self._current_filter == keycode_filter_masked:
            if self.basic_keycodes is None:
                self.basic_keycodes = self._make_palette(keycode_filter_masked, self._basic_dirty)
                self._basic_dirty = False
            if self.all_keycodes is not None:
                self.all_keycodes.hide()
            self.basic_keycodes.show()
        else:
            if self.all_keycodes is None:
                self.all_keycodes = self._make_palette(keycode_filter_any, self._all_dirty)
                self._all_dirty = False
            if self.basic_keycodes is not None:
                self.basic_keycodes.hide()
            self.all_keycodes.show()

    def showEvent(self, event):
        self._apply_current_filter()
        super().showEvent(event)

    def set_keycode_filter(self, keycode_filter):
        """Show/hide filtered keycode widgets"""
        self._current_filter = keycode_filter
        if self.isVisible():
            self._apply_current_filter()

    def set_keyboard(self, keyboard):
        """Set keyboard reference for all tab widgets"""
        self._pal_kb = keyboard
        self._pal_kb_pending = True
        for opt in [self.all_keycodes, self.basic_keycodes]:
            if opt is not None:
                opt.set_keyboard(keyboard)

    def set_editors(self, macro_recorder=None, tap_dance_editor=None, dks_settings=None, toggle_settings=None, **kwargs):
        """Set editor references for all tab widgets"""
        self._pal_editors = dict(macro_recorder=macro_recorder, tap_dance_editor=tap_dance_editor,
                                 dks_settings=dks_settings, toggle_settings=toggle_settings)
        for opt in [self.all_keycodes, self.basic_keycodes]:
            if opt is not None:
                opt.set_editors(macro_recorder, tap_dance_editor, dks_settings, toggle_settings)

    def refresh_macro_buttons(self):
        """Force refresh the macro tab buttons in all keycodes widgets"""
        self._all_dirty = self.all_keycodes is None or self._all_dirty
        self._basic_dirty = self.basic_keycodes is None or self._basic_dirty
        for opt in [self.all_keycodes, self.basic_keycodes]:
            if opt is not None:
                opt.refresh_macro_buttons()

    def recreate_keycode_buttons(self):
        """Recreate all keycode buttons to reflect updated labels"""
        self._all_dirty = self.all_keycodes is None or self._all_dirty
        self._basic_dirty = self.basic_keycodes is None or self._basic_dirty
        for opt in [self.all_keycodes, self.basic_keycodes]:
            if opt is not None:
                opt.recreate_keycode_buttons()


class ToggleKeyWidget(KeyWidget):
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


class ToggleEntryUI(QWidget):
    """UI for a single toggle slot"""

    changed = pyqtSignal()
    name_changed = pyqtSignal()

    def __init__(self, slot_num, toggle_protocol=None):
        super().__init__()
        self.slot_num = slot_num
        self.toggle_protocol = toggle_protocol
        self.slot = ToggleSlot()
        self.pending_changes = False
        self.selected_key_index = -1  # Which key widget is selected for keycode assignment

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Slot info header
        header_layout = QHBoxLayout()

        from protocol.feature_names import get_feature_name_manager, FEATURE_TOGGLE
        name = get_feature_name_manager().get_name(FEATURE_TOGGLE, self.slot_num)
        self.slot_label = QLabel(f"<b>{name}</b>")
        self.slot_label.setStyleSheet("font-size: 14pt;")
        header_layout.addWidget(self.slot_label)

        self.btn_rename = QPushButton("Rename")
        self.btn_rename.setMaximumHeight(24)
        self.btn_rename.setMaximumWidth(60)
        self.btn_rename.setStyleSheet("QPushButton { font-size: 8pt; border-radius: 3px; padding: 2px 6px; }")
        self.btn_rename.clicked.connect(self._on_rename)
        header_layout.addWidget(self.btn_rename)

        self.keycode_label = QLabel(f"Keycode: 0x{slot_to_toggle_keycode(self.slot_num):04X}")
        self.keycode_label.setStyleSheet("font-family: monospace; color: gray;")
        header_layout.addWidget(self.keycode_label)

        header_layout.addStretch()

        self.status_label = QLabel("(Not configured)")
        self.status_label.setStyleSheet("color: gray;")
        header_layout.addWidget(self.status_label)

        layout.addLayout(header_layout)

        # Description
        desc = QLabel("Configure the target keycode that will be toggled when this key is pressed.\n"
                      "Assign this TGL keycode to a physical key in your keymap.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(desc)

        # Multi-key toggle checkbox
        self.multi_key_checkbox = QCheckBox("Multi Key Toggle")
        self.multi_key_checkbox.setToolTip(
            "When enabled, each press taps a different keycode in sequence.\n"
            "Configure up to 8 keycodes to cycle through.\n"
            "KC_NO in a step will skip without sending a keycode.")
        self.multi_key_checkbox.toggled.connect(self._on_multi_key_toggled)
        layout.addWidget(self.multi_key_checkbox)

        # Standard toggle: single target keycode
        self.standard_group = QGroupBox("Target Keycode")
        standard_layout = QHBoxLayout()

        standard_layout.addWidget(QLabel("Target:"))

        self.target_key = ToggleKeyWidget()
        self.target_key.selected.connect(lambda w: self._on_key_selected(0))
        standard_layout.addWidget(self.target_key)

        standard_layout.addWidget(QLabel("<- Click to select, then choose from keycodes below"))
        standard_layout.addStretch()

        self.standard_group.setLayout(standard_layout)
        layout.addWidget(self.standard_group)

        # Multi-key toggle: start with 2 visible, expandable up to 8
        self.multi_group = QGroupBox("Multi-Key Cycle")
        multi_outer_layout = QVBoxLayout()
        multi_outer_layout.setSpacing(6)

        self.multi_keys_layout = QHBoxLayout()
        self.multi_keys_layout.setSpacing(0)

        self.multi_key_widgets = []
        self.multi_color_labels = []
        self.multi_key_spacers = []
        self._visible_multi_keys = 2  # Start with 2 visible

        for i in range(TOGGLE_MULTI_MAX_KEYS):
            # Colour indicator (compact)
            r, g, b = TOGGLE_MULTI_COLORS[i]
            color_label = QLabel(f"{i+1}")
            color_label.setAlignment(Qt.AlignCenter)
            color_label.setFixedSize(18, 18)
            color_label.setStyleSheet(
                f"background-color: rgb({r},{g},{b}); "
                f"color: {'black' if (r + g + b) > 300 else 'white'}; "
                f"border-radius: 9px; font-size: 8pt; font-weight: bold;")
            color_label.setToolTip(f"Step {i+1}: {TOGGLE_MULTI_COLOR_NAMES[i]}")
            self.multi_color_labels.append(color_label)
            self.multi_keys_layout.addWidget(color_label)

            # Key widget
            key_widget = ToggleKeyWidget()
            key_idx = i  # Capture for lambda
            key_widget.selected.connect(lambda w, idx=key_idx: self._on_key_selected(idx))
            self.multi_key_widgets.append(key_widget)
            self.multi_keys_layout.addWidget(key_widget)

            # Add 60px spacer after each key (except the last)
            if i < TOGGLE_MULTI_MAX_KEYS - 1:
                spacer = QWidget()
                spacer.setFixedWidth(60)
                self.multi_key_spacers.append(spacer)
                self.multi_keys_layout.addWidget(spacer)

        # Push all keys to the left
        self.multi_keys_layout.addStretch()

        multi_outer_layout.addLayout(self.multi_keys_layout)

        # Add/Remove key buttons
        multi_btn_layout = QHBoxLayout()
        self.add_key_btn = QPushButton("+ Add Key")
        self.add_key_btn.setMaximumWidth(90)
        self.add_key_btn.setStyleSheet("QPushButton { font-size: 8pt; padding: 2px 8px; }")
        self.add_key_btn.clicked.connect(self._on_add_multi_key)
        multi_btn_layout.addWidget(self.add_key_btn)

        self.remove_key_btn = QPushButton("- Remove Key")
        self.remove_key_btn.setMaximumWidth(100)
        self.remove_key_btn.setStyleSheet("QPushButton { font-size: 8pt; padding: 2px 8px; }")
        self.remove_key_btn.clicked.connect(self._on_remove_multi_key)
        multi_btn_layout.addWidget(self.remove_key_btn)

        self.multi_key_count_label = QLabel("2 / 8 keys")
        self.multi_key_count_label.setStyleSheet("color: gray; font-size: 8pt;")
        multi_btn_layout.addWidget(self.multi_key_count_label)

        multi_btn_layout.addStretch()
        multi_outer_layout.addLayout(multi_btn_layout)

        self.multi_group.setLayout(multi_outer_layout)
        self.multi_group.setVisible(False)
        layout.addWidget(self.multi_group)

        # Apply initial visibility for multi-key slots
        self._update_multi_key_visibility()

        # Action buttons
        btn_layout = QHBoxLayout()

        self.clear_btn = QPushButton("Clear Slot")
        self.clear_btn.clicked.connect(self._on_clear)
        btn_layout.addWidget(self.clear_btn)

        btn_layout.addStretch()

        self.save_btn = QPushButton("Save to Keyboard")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)

        self.load_btn = QPushButton("Load from Keyboard")
        self.load_btn.clicked.connect(self._on_load)
        btn_layout.addWidget(self.load_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        self.setLayout(layout)

    def set_protocol(self, protocol):
        """Set the toggle protocol for communication"""
        self.toggle_protocol = protocol

    def update_multi_key_colors(self, colors):
        """Update multi-key step color labels with colors from functional LED config.
        colors: list of 8 (r, g, b) tuples."""
        for i, label in enumerate(self.multi_color_labels):
            if i < len(colors):
                r, g, b = colors[i]
                label.setStyleSheet(
                    f"background-color: rgb({r},{g},{b}); "
                    f"color: {'black' if (r + g + b) > 300 else 'white'}; "
                    f"border-radius: 9px; font-size: 8pt; font-weight: bold;")

    def _on_rename(self):
        """Open rename dialog for this toggle slot"""
        from protocol.feature_names import get_feature_name_manager, FEATURE_TOGGLE, MAX_NAME_LENGTH
        mgr = get_feature_name_manager()
        current = mgr.get_name(FEATURE_TOGGLE, self.slot_num)
        new_name, ok = QInputDialog.getText(
            self, "Rename Toggle",
            f"Name for TGL_{self.slot_num:02d} (max {MAX_NAME_LENGTH} chars):",
            text=current
        )
        if ok:
            mgr.set_name(FEATURE_TOGGLE, self.slot_num, new_name.strip()[:MAX_NAME_LENGTH])
            display = mgr.get_name(FEATURE_TOGGLE, self.slot_num)
            self.slot_label.setText(f"<b>{display}</b>")
            self.save_btn.setEnabled(True)
            self.name_changed.emit()
            self.changed.emit()

    def _on_multi_key_toggled(self, checked):
        """Handle multi-key checkbox toggle"""
        self.standard_group.setVisible(not checked)
        self.multi_group.setVisible(checked)

        self.slot.is_multi_key = checked
        if checked and self.slot.num_keys < 2:
            self.slot.num_keys = 2
            self._visible_multi_keys = 2

        self.pending_changes = True
        self.save_btn.setEnabled(True)
        self._deselect_all_keys()
        self._update_display()
        self._update_multi_key_visibility()
        self.changed.emit()

    def _on_add_multi_key(self):
        """Add another multi-key step. The new step starts as KC_NO (a valid
        "skip" step in the firmware cycle) and num_keys tracks the number of
        steps the user added, so an empty step survives a save instead of
        being trimmed away."""
        if self._visible_multi_keys < TOGGLE_MULTI_MAX_KEYS:
            self._visible_multi_keys += 1
            self.slot.set_keycode(self._visible_multi_keys - 1, 0)  # explicit KC_NO
            self.slot.num_keys = max(2, self._visible_multi_keys)
            self._update_multi_key_visibility()
            self._update_display()
            self.pending_changes = True
            self.save_btn.setEnabled(True)
            self.changed.emit()

    def _on_remove_multi_key(self):
        """Remove the HIGHLIGHTED multi-key step (falling back to the last one
        when nothing is highlighted), shifting the later steps down."""
        if self._visible_multi_keys <= 2:
            return
        removed_idx = self.selected_key_index
        if not (0 <= removed_idx < self._visible_multi_keys):
            removed_idx = self._visible_multi_keys - 1  # nothing highlighted -> last
        # Shift every later step down into the removed position
        for i in range(removed_idx, TOGGLE_MULTI_MAX_KEYS - 1):
            self.slot.set_keycode(i, self.slot.get_keycode(i + 1))
        self.slot.set_keycode(TOGGLE_MULTI_MAX_KEYS - 1, 0)
        self._visible_multi_keys -= 1
        self.slot.num_keys = max(2, self._visible_multi_keys)
        self._deselect_all_keys()
        self._update_multi_key_visibility()
        self._update_display()
        self.pending_changes = True
        self.save_btn.setEnabled(True)
        self.changed.emit()

    def _update_multi_key_visibility(self):
        """Show/hide multi-key slots based on _visible_multi_keys count"""
        for i in range(TOGGLE_MULTI_MAX_KEYS):
            visible = i < self._visible_multi_keys
            self.multi_key_widgets[i].setVisible(visible)
            self.multi_color_labels[i].setVisible(visible)
        # Show spacers only between visible keys (hide spacer after last visible key)
        for i in range(len(self.multi_key_spacers)):
            self.multi_key_spacers[i].setVisible(i < self._visible_multi_keys - 1)
        self.add_key_btn.setEnabled(self._visible_multi_keys < TOGGLE_MULTI_MAX_KEYS)
        self.remove_key_btn.setEnabled(self._visible_multi_keys > 2)
        self.multi_key_count_label.setText(f"{self._visible_multi_keys} / {TOGGLE_MULTI_MAX_KEYS} keys")

    def _on_key_selected(self, index):
        """Handle key widget selection"""
        self._deselect_all_keys()
        self.selected_key_index = index

        if self.slot.is_multi_key:
            if 0 <= index < len(self.multi_key_widgets):
                self.multi_key_widgets[index].set_selected(True)
        else:
            if index == 0:
                self.target_key.set_selected(True)

    def _deselect_all_keys(self):
        """Deselect all key widgets"""
        self.selected_key_index = -1
        self.target_key.set_selected(False)
        for w in self.multi_key_widgets:
            w.set_selected(False)

    def on_keycode_selected(self, keycode):
        """Called when a keycode is selected from TabbedKeycodes"""
        if self.selected_key_index < 0:
            return

        try:
            keycode_value = Keycode.deserialize(keycode)
        except Exception:
            keycode_value = 0

        if self.slot.is_multi_key:
            self.slot.set_keycode(self.selected_key_index, keycode_value)
            # num_keys is the number of steps the user added (KC_NO steps are
            # valid "skip" steps and count) — never trimmed to the highest
            # non-empty step.
            self.slot.num_keys = max(2, self._visible_multi_keys)
        else:
            self.slot.target_keycode = keycode_value

        self._update_display()
        self.pending_changes = True
        self.save_btn.setEnabled(True)
        self.changed.emit()
        self._deselect_all_keys()

    def _update_display(self):
        """Update the UI to reflect current slot state"""
        # Update standard target key display
        if self.slot.target_keycode != 0:
            qmk_id = Keycode.serialize(self.slot.target_keycode)
            self.target_key.set_keycode(qmk_id)
        else:
            self.target_key.set_keycode("KC_NO")

        # Update multi-key displays
        for i in range(TOGGLE_MULTI_MAX_KEYS):
            kc = self.slot.get_keycode(i)
            if kc != 0:
                qmk_id = Keycode.serialize(kc)
                self.multi_key_widgets[i].set_keycode(qmk_id)
            else:
                self.multi_key_widgets[i].set_keycode("KC_NO")

        # Update multi-key checkbox without triggering signal
        self.multi_key_checkbox.blockSignals(True)
        self.multi_key_checkbox.setChecked(self.slot.is_multi_key)
        self.multi_key_checkbox.blockSignals(False)

        # Show/hide groups based on mode
        self.standard_group.setVisible(not self.slot.is_multi_key)
        self.multi_group.setVisible(self.slot.is_multi_key)

        # Sync visible multi-key count with loaded data
        if self.slot.is_multi_key:
            # Show at least num_keys slots, or find highest non-zero
            max_used = 0
            for i in range(TOGGLE_MULTI_MAX_KEYS):
                if self.slot.get_keycode(i) != 0:
                    max_used = i + 1
            self._visible_multi_keys = max(2, max(self.slot.num_keys, max_used))
            self._update_multi_key_visibility()

        # Update status
        if self.slot.is_multi_key:
            active_count = sum(1 for i in range(TOGGLE_MULTI_MAX_KEYS) if self.slot.get_keycode(i) != 0)
            self.status_label.setText(f"Multi-Key ({active_count} keycodes)")
            self.status_label.setStyleSheet("color: #0088cc;")
        elif self.slot.target_keycode != 0:
            self.status_label.setText("Configured")
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText("(Not configured)")
            self.status_label.setStyleSheet("color: gray;")

    def _on_clear(self):
        """Clear this slot"""
        self.slot = ToggleSlot()
        self._update_display()
        self.pending_changes = True
        self.save_btn.setEnabled(True)
        self.changed.emit()

    def _on_save(self):
        """Save slot to keyboard"""
        if not self.toggle_protocol:
            QMessageBox.warning(self, "Error", "Not connected to keyboard")
            return

        self.toggle_protocol._log(f"--- Save TGL_{self.slot_num:02d} started ---", "DEBUG")

        if self.toggle_protocol.set_slot(self.slot_num, self.slot):
            if self.toggle_protocol.save_to_eeprom():
                self.toggle_protocol._log(f"--- Save TGL_{self.slot_num:02d} completed OK ---", "DEBUG")
                QMessageBox.information(self, "Success", f"TGL_{self.slot_num:02d} saved to keyboard")
                self.pending_changes = False
                self.save_btn.setEnabled(False)
            else:
                self.toggle_protocol._log(f"--- Save TGL_{self.slot_num:02d} FAILED (EEPROM) ---", "ERROR")
                QMessageBox.warning(self, "Error", "Failed to save to EEPROM")
        else:
            self.toggle_protocol._log(f"--- Save TGL_{self.slot_num:02d} FAILED (set_slot) ---", "ERROR")
            QMessageBox.warning(self, "Error", "Failed to send configuration to keyboard")

    def _on_load(self, silent=False):
        """Load slot from keyboard"""
        if not self.toggle_protocol:
            if not silent:
                QMessageBox.warning(self, "Error", "Not connected to keyboard")
            return

        self.toggle_protocol._log(f"--- Load TGL_{self.slot_num:02d} started ---", "DEBUG")

        slot = self.toggle_protocol.get_slot(self.slot_num)
        if slot:
            self.slot = slot
            self._update_display()
            self.pending_changes = False
            self.save_btn.setEnabled(False)
            self.toggle_protocol._log(f"--- Load TGL_{self.slot_num:02d} completed OK ---", "DEBUG")
        else:
            if not silent:
                QMessageBox.warning(self, "Error", "Failed to load configuration from keyboard")


class ToggleSettingsTab(BasicEditor):
    """Main Toggle settings editor tab"""

    def __init__(self, layout_editor=None):
        super().__init__()
        self.layout_editor = layout_editor
        self.toggle_protocol = None
        self.loaded_slots = set()  # Track which slots have been loaded

        # Dynamic tab tracking
        self._visible_tab_count = 1  # Minimum 1 tab visible
        self._manually_expanded_count = 0  # Tabs added via "+" button

        # Create tab widget for toggle slots
        self.tabs = QTabWidget()

        # Toggle entries (each ~9 KeyWidgets + controls) are created on
        # demand — building all 100 up front cost seconds of startup for
        # slots most users never open. State that arrives before an entry
        # exists (protocol, scanned slot data, multi-key colors) is recorded
        # and replayed in _entry() when it is created.
        self._entries = {}          # idx -> ToggleEntryUI
        self._scrolls = {}          # idx -> QScrollArea wrapping the entry
        self._scanned_slots = {}    # idx -> ToggleSlot from the rebuild scan
        self._multi_key_colors = None

        self.addWidget(self.tabs)

        # Connect tab changes for lazy loading and "+" tab handling
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Debug console
        self.debug_console = DebugConsole("Toggle Keys Debug Console")
        self.addWidget(self.debug_console)

        # Bottom action buttons
        button_layout = QHBoxLayout()

        self.reset_all_btn = QPushButton("Reset All Slots")
        self.reset_all_btn.clicked.connect(self._on_reset_all)
        button_layout.addWidget(self.reset_all_btn)

        button_layout.addStretch()

        self.load_eeprom_btn = QPushButton("Load All from EEPROM")
        self.load_eeprom_btn.clicked.connect(self._on_load_eeprom)
        button_layout.addWidget(self.load_eeprom_btn)

        self.addLayout(button_layout)

        # Add TabbedKeycodes at the bottom
        self.tabbed_keycodes = TabbedKeycodesNoLayers()
        self.tabbed_keycodes.keycode_changed.connect(self.on_keycode_selected)
        self.addWidget(self.tabbed_keycodes)

    def _entry(self, idx):
        """Create (or return) the ToggleEntryUI for a slot, replaying any
        state that arrived while it did not exist yet."""
        entry = self._entries.get(idx)
        if entry is not None:
            return entry
        entry = ToggleEntryUI(idx)
        entry.changed.connect(self.on_entry_changed)
        entry.name_changed.connect(self.on_name_changed)
        if self.toggle_protocol is not None:
            entry.set_protocol(self.toggle_protocol)
        if idx in self._scanned_slots:
            entry.slot = self._scanned_slots[idx]
            entry._update_display()
        if self._multi_key_colors is not None:
            entry.update_multi_key_colors(self._multi_key_colors)
        self._entries[idx] = entry
        return entry

    def _scroll(self, idx):
        """Create (or return) the scroll area wrapping a slot's entry."""
        scroll = self._scrolls.get(idx)
        if scroll is not None:
            return scroll
        scroll = QScrollArea()
        scroll.setWidget(self._entry(idx))
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scrolls[idx] = scroll
        return scroll

    def on_entry_changed(self):
        """Handle entry change - update tab titles"""
        from protocol.feature_names import get_feature_name_manager, FEATURE_TOGGLE
        mgr = get_feature_name_manager()
        for x in range(min(self._visible_tab_count, TOGGLE_NUM_SLOTS)):
            self.tabs.setTabText(x, mgr.get_name(FEATURE_TOGGLE, x))

    def on_name_changed(self):
        """Handle name change - update tab titles and refresh keycode labels"""
        self.on_entry_changed()
        self.tabbed_keycodes.recreate_keycode_buttons()

    def on_keycode_selected(self, keycode):
        """Called when a keycode is selected from TabbedKeycodes"""
        current_idx = self.tabs.currentIndex()
        if 0 <= current_idx < self._visible_tab_count:
            self._entry(current_idx).on_keycode_selected(keycode)

    def _on_tab_changed(self, index):
        """Handle tab change - lazy load slot data and handle '+' tab"""
        # Check if "+" tab was clicked
        if self._visible_tab_count < TOGGLE_NUM_SLOTS and index == self._visible_tab_count:
            self._manually_expanded_count += 1
            self._update_visible_tabs()
            # Update keycode buttons to show new toggle count
            self.tabbed_keycodes.refresh_macro_buttons()
            self.tabs.setCurrentIndex(self._visible_tab_count - 1)
            return

        # Lazy load: Only load slot data when first viewing the tab
        if 0 <= index < self._visible_tab_count:
            if self.toggle_protocol and index not in self.loaded_slots:
                self._entry(index)._on_load(silent=True)
                self.loaded_slots.add(index)

    def _on_reset_all(self):
        """Reset all slots to defaults"""
        if not self.toggle_protocol:
            return

        reply = QMessageBox.question(
            None, "Confirm Reset",
            "Reset ALL Toggle slots to default configuration? This cannot be undone!",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.toggle_protocol.reset_all_slots():
                QMessageBox.information(None, "Success", "All slots reset to defaults")
                # Reload current tab (silent since reset already showed success)
                current_idx = self.tabs.currentIndex()
                if 0 <= current_idx < self._visible_tab_count:
                    self._entry(current_idx)._on_load(silent=True)
            else:
                QMessageBox.warning(None, "Error", "Failed to reset slots")

    def _on_load_eeprom(self):
        """Load all slots from EEPROM"""
        if not self.toggle_protocol:
            return

        if self.toggle_protocol.load_from_eeprom():
            QMessageBox.information(None, "Success", "Toggle configurations loaded from EEPROM")
            # Reload current tab (silent since load already showed success)
            current_idx = self.tabs.currentIndex()
            if 0 <= current_idx < self._visible_tab_count:
                self._entry(current_idx)._on_load(silent=True)
        else:
            QMessageBox.warning(None, "Error", "Failed to load from EEPROM")

    def rebuild(self, device):
        """Rebuild the tab when device changes"""
        super().rebuild(device)

        if self.valid():
            self.keyboard = device.keyboard
            self.toggle_protocol = ProtocolToggle(self.keyboard)
            self.toggle_protocol.set_debug_console(self.debug_console)

            # Set protocol on already-created entries; entries created later
            # pick it up in _entry().
            for entry in self._entries.values():
                entry.set_protocol(self.toggle_protocol)

            # Set keyboard on tabbed keycodes
            self.tabbed_keycodes.set_keyboard(self.keyboard)

            # Clear loaded slots cache (and stale scan data from a previous
            # device — _scan_and_update_visible_tabs refills it)
            self.loaded_slots.clear()
            self._scanned_slots.clear()

            # Load multi-key step colors from functional LED config
            self._load_multi_key_colors()

            # Reset manual expansion and scan for used slots
            self._manually_expanded_count = 0
            self._scan_and_update_visible_tabs()

    def _load_multi_key_colors(self):
        """Load multi-key step colors from functional LED config on the keyboard"""
        if not hasattr(self, 'keyboard') or not self.keyboard:
            return
        try:
            import struct
            from protocol.constants import CMD_VIA_VIAL_PREFIX, HID_CMD_FUNC_LED_GET
            # Multi-key step colors are at FLED indices 27-34 (8 steps)
            # Request states 27-34 (offset=27, count=7 then offset=34, count=1 - or just do offset=24, count=7 to get 27-33, then 34)
            # Simplest: request offset=27, count=7 (gets 27-33), then offset=34, count=1
            colors = []
            data = struct.pack("BBBB", CMD_VIA_VIAL_PREFIX, HID_CMD_FUNC_LED_GET, 27, 7)
            response = self.keyboard.usb_send(self.keyboard.dev, data, retries=20)
            if response and len(response) >= 1 + 7 * 4 and response[0] == 0x01:
                for i in range(7):
                    base = 1 + i * 4
                    h, s, v = response[base], response[base + 1], response[base + 2]
                    colors.append(self._hsv_to_rgb(h, s, v))
            else:
                return
            # Get state 34
            data = struct.pack("BBBB", CMD_VIA_VIAL_PREFIX, HID_CMD_FUNC_LED_GET, 34, 1)
            response = self.keyboard.usb_send(self.keyboard.dev, data, retries=20)
            if response and len(response) >= 1 + 1 * 4 and response[0] == 0x01:
                h, s, v = response[1], response[2], response[3]
                colors.append(self._hsv_to_rgb(h, s, v))
            else:
                return

            # Record for entries created later; update the existing ones now
            self._multi_key_colors = colors
            for entry in self._entries.values():
                entry.update_multi_key_colors(colors)
        except Exception as e:
            print(f"Error loading multi-key colors: {e}")

    @staticmethod
    def _hsv_to_rgb(h, s, v):
        """Convert QMK HSV (0-255 each) to RGB tuple"""
        from PyQt5.QtGui import QColor
        qh = int(h * 360 / 256) % 360
        c = QColor.fromHsv(qh, s, v)
        return (c.red(), c.green(), c.blue())

    def _scan_and_update_visible_tabs(self):
        """Scan all slots to find which have content and update visible tabs"""
        if not self.toggle_protocol:
            return

        # Load all slots to find which have content
        last_used = -1
        for i in range(TOGGLE_NUM_SLOTS):
            slot = self.toggle_protocol.get_slot(i)
            if slot:
                self._scanned_slots[i] = slot
                entry = self._entries.get(i)
                if entry is not None:
                    entry.slot = slot
                    entry._update_display()
                self.loaded_slots.add(i)
                if slot.is_enabled():
                    last_used = i

        self._update_visible_tabs_with_last_used(last_used)

    def _find_last_used_index(self):
        """Find the index of the last toggle slot that has content"""
        for idx in range(TOGGLE_NUM_SLOTS - 1, -1, -1):
            entry = self._entries.get(idx)
            if entry is not None and idx in self.loaded_slots and entry.slot.target_keycode != 0:
                return idx
            slot = self._scanned_slots.get(idx)
            if slot is not None and idx in self.loaded_slots and slot.target_keycode != 0:
                return idx
        return -1

    def _update_visible_tabs_with_last_used(self, last_used):
        """Update visible tabs given the last used index"""
        max_tabs = TOGGLE_NUM_SLOTS

        # Calculate visible count: last used + 1, or at least 1, plus any manually expanded
        base_visible = max(1, last_used + 1)
        self._visible_tab_count = min(max_tabs, base_visible + self._manually_expanded_count)

        # Remove all tabs first
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)

        # Add visible toggle tabs
        from protocol.feature_names import get_feature_name_manager, FEATURE_TOGGLE
        mgr = get_feature_name_manager()
        for x in range(self._visible_tab_count):
            self.tabs.addTab(self._scroll(x), mgr.get_name(FEATURE_TOGGLE, x))

        # Add "+" tab if not all tabs are visible
        if self._visible_tab_count < max_tabs:
            plus_widget = QWidget()
            self.tabs.addTab(plus_widget, "+")

    def _update_visible_tabs(self):
        """Update which tabs are visible based on content and manual expansion"""
        last_used = self._find_last_used_index()
        self._update_visible_tabs_with_last_used(last_used)

    def valid(self):
        """Check if device is valid"""
        return isinstance(self.device, VialKeyboard)
