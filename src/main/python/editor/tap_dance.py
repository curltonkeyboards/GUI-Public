# SPDX-License-Identifier: GPL-2.0-or-later
import sip

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal, QObject, Qt
from PyQt5.QtWidgets import QTabWidget, QWidget, QSizePolicy, QGridLayout, QVBoxLayout, QLabel, QHBoxLayout, \
    QPushButton, QSpinBox, QScrollArea, QGroupBox

from protocol.constants import VIAL_PROTOCOL_DYNAMIC
from widgets.key_widget import KeyWidget
from tabbed_keycodes import TabbedKeycodes
from util import tr
from vial_device import VialKeyboard
from editor.basic_editor import BasicEditor


class TapDanceKeyWidget(KeyWidget):
    """Custom KeyWidget that doesn't open tray - parent will handle keycode selection"""

    selected = pyqtSignal(object)  # Emits self when clicked

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_selected = False

    def mousePressEvent(self, ev):
        # Set active_key to the actual widget so KeyboardWidget draws the highlight
        if len(self.widgets) > 0:
            self.active_key = self.widgets[0]
            self.active_mask = False

        # Emit that we're selected (don't call parent which opens tray)
        self.selected.emit(self)
        self.update()
        ev.accept()

    def mouseReleaseEvent(self, ev):
        ev.accept()

    def set_selected(self, selected):
        """Visual feedback for selection"""
        self.is_selected = selected
        if selected:
            if len(self.widgets) > 0:
                self.active_key = self.widgets[0]
                self.active_mask = False
        else:
            self.active_key = None
        self.update()


class TapDanceEntryUI(QObject):

    key_changed = pyqtSignal()
    timing_changed = pyqtSignal()
    key_selected = pyqtSignal(object)  # Emits when a key widget is selected

    def __init__(self, idx):
        super().__init__()

        self.idx = idx
        self.key_widgets = []

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Header with tap dance name
        header_layout = QHBoxLayout()
        self.title_label = QLabel(f"<b>TD({idx})</b>")
        self.title_label.setStyleSheet("font-size: 14pt;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Description
        desc = QLabel("Configure what happens when this tap dance key is tapped, held, or double-tapped.\n"
                      "Assign this tap dance to a key using TD({}) in your keymap.".format(idx))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray; font-size: 9pt;")
        main_layout.addWidget(desc)

        # Keys group
        keys_group = QGroupBox("Actions")
        keys_layout = QVBoxLayout()

        # Instruction text
        instruction = QLabel("← Click a key to select, then choose from keycodes below")
        instruction.setStyleSheet("color: gray; font-style: italic;")
        keys_layout.addWidget(instruction)

        # Container for key widgets
        self.container = QGridLayout()
        self.populate_container()
        keys_layout.addLayout(self.container)

        # Tapping term
        timing_layout = QHBoxLayout()
        timing_layout.addWidget(QLabel("Tapping term (ms):"))
        self.txt_tapping_term = QSpinBox()
        self.txt_tapping_term.valueChanged.connect(self.on_timing_changed)
        self.txt_tapping_term.setMinimum(0)
        self.txt_tapping_term.setMaximum(10000)
        timing_layout.addWidget(self.txt_tapping_term)
        timing_layout.addStretch()
        keys_layout.addLayout(timing_layout)

        keys_layout.addStretch()
        keys_group.setLayout(keys_layout)

        # Scroll area for keys group
        scroll = QScrollArea()
        scroll.setWidget(keys_group)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        main_layout.addWidget(scroll)

        # Create widget for the layout
        self.w2 = QWidget()
        self.w2.setLayout(main_layout)

    def populate_container(self):
        labels = ["On tap", "On hold", "On double tap", "On tap + hold"]

        self.kc_on_tap = TapDanceKeyWidget()
        self.kc_on_tap.changed.connect(self.on_key_changed)
        self.kc_on_tap.selected.connect(self._on_key_selected)
        self.key_widgets.append(self.kc_on_tap)

        self.kc_on_hold = TapDanceKeyWidget()
        self.kc_on_hold.changed.connect(self.on_key_changed)
        self.kc_on_hold.selected.connect(self._on_key_selected)
        self.key_widgets.append(self.kc_on_hold)

        self.kc_on_double_tap = TapDanceKeyWidget()
        self.kc_on_double_tap.changed.connect(self.on_key_changed)
        self.kc_on_double_tap.selected.connect(self._on_key_selected)
        self.key_widgets.append(self.kc_on_double_tap)

        self.kc_on_tap_hold = TapDanceKeyWidget()
        self.kc_on_tap_hold.changed.connect(self.on_key_changed)
        self.kc_on_tap_hold.selected.connect(self._on_key_selected)
        self.key_widgets.append(self.kc_on_tap_hold)

        widgets = [self.kc_on_tap, self.kc_on_hold, self.kc_on_double_tap, self.kc_on_tap_hold]
        for i, (label, widget) in enumerate(zip(labels, widgets)):
            self.container.addWidget(QLabel(label), i, 0)
            self.container.addWidget(widget, i, 1)

    def _on_key_selected(self, widget):
        """Bubble up key selection"""
        self.key_selected.emit(widget)

    def widget(self):
        return self.w2

    def load(self, data):
        objs = [self.kc_on_tap, self.kc_on_hold, self.kc_on_double_tap, self.kc_on_tap_hold, self.txt_tapping_term]
        for o in objs:
            o.blockSignals(True)

        self.kc_on_tap.set_keycode(data[0])
        self.kc_on_hold.set_keycode(data[1])
        self.kc_on_double_tap.set_keycode(data[2])
        self.kc_on_tap_hold.set_keycode(data[3])
        self.txt_tapping_term.setValue(data[4])

        for o in objs:
            o.blockSignals(False)

    def save(self):
        return (
            self.kc_on_tap.keycode,
            self.kc_on_hold.keycode,
            self.kc_on_double_tap.keycode,
            self.kc_on_tap_hold.keycode,
            self.txt_tapping_term.value()
        )

    def on_key_changed(self):
        self.key_changed.emit()

    def on_timing_changed(self):
        self.timing_changed.emit()


class TapDance(BasicEditor):

    def __init__(self):
        super().__init__()
        self.keyboard = None
        self.selected_key_widget = None

        self.tap_dance_entries = []
        self.tap_dance_entries_available = []
        self.tabs = QTabWidget()
        for x in range(128):
            entry = TapDanceEntryUI(x)
            entry.key_changed.connect(self.on_key_changed)
            entry.timing_changed.connect(self.on_timing_changed)
            entry.key_selected.connect(self.on_key_widget_selected)
            self.tap_dance_entries_available.append(entry)

        # Dynamic tab tracking
        self._visible_tab_count = 1  # Minimum 1 tab visible
        self._manually_expanded_count = 0  # Tabs added via "+" button

        self.addWidget(self.tabs)

        # Save/Revert buttons
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_save = QPushButton(tr("TapDance", "Save"))
        self.btn_save.setMinimumHeight(30)
        self.btn_save.setMaximumHeight(30)
        self.btn_save.setMinimumWidth(80)
        self.btn_save.setStyleSheet("QPushButton { border-radius: 5px; }")
        self.btn_save.clicked.connect(self.on_save)
        btn_revert = QPushButton(tr("TapDance", "Revert"))
        btn_revert.setMinimumHeight(30)
        btn_revert.setMaximumHeight(30)
        btn_revert.setMinimumWidth(80)
        btn_revert.setStyleSheet("QPushButton { border-radius: 5px; }")
        btn_revert.clicked.connect(self.on_revert)
        buttons.addWidget(self.btn_save)
        buttons.addWidget(btn_revert)
        self.addLayout(buttons)

        # TabbedKeycodes always visible at bottom
        self.tabbed_keycodes = TabbedKeycodes()
        self.tabbed_keycodes.keycode_changed.connect(self.on_keycode_selected)
        self.addWidget(self.tabbed_keycodes)

    def on_key_widget_selected(self, widget):
        """Handle when a key widget is selected"""
        if self.selected_key_widget is not None and self.selected_key_widget != widget:
            try:
                if not sip.isdeleted(self.selected_key_widget):
                    self.selected_key_widget.set_selected(False)
            except RuntimeError:
                pass
            self.selected_key_widget = None

        self.selected_key_widget = widget
        widget.set_selected(True)

    def on_keycode_selected(self, keycode):
        """Handle keycode selection from TabbedKeycodes"""
        if self.selected_key_widget is not None:
            try:
                if not sip.isdeleted(self.selected_key_widget):
                    self.selected_key_widget.set_keycode(keycode)
            except RuntimeError:
                self.selected_key_widget = None

    def rebuild_ui(self):
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)
        self.tap_dance_entries = self.tap_dance_entries_available[:self.keyboard.tap_dance_count]
        self.reload_ui()
        # Reset manual expansion and update visible tabs
        self._manually_expanded_count = 0
        self._update_visible_tabs()

    def reload_ui(self):
        for x, e in enumerate(self.tap_dance_entries):
            e.load(self.keyboard.tap_dance_get(x))
        self.update_modified_state()

    def on_save(self):
        for x, e in enumerate(self.tap_dance_entries):
            self.keyboard.tap_dance_set(x, self.tap_dance_entries[x].save())
        self.update_modified_state()

    def on_revert(self):
        self.keyboard.reload_dynamic()
        self.reload_ui()

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            self.rebuild_ui()
            # Set keyboard reference for tabbed keycodes
            self.tabbed_keycodes.set_keyboard(self.keyboard)

    def valid(self):
        return isinstance(self.device, VialKeyboard) and \
               (self.device.keyboard and self.device.keyboard.vial_protocol >= VIAL_PROTOCOL_DYNAMIC
                and self.device.keyboard.tap_dance_count > 0)

    def on_key_changed(self):
        self.on_save()

    def update_modified_state(self):
        """ Update indication of which tabs are modified, and keep Save button enabled only if it's needed """
        has_changes = False
        # Only update titles for visible tabs (not the "+" tab)
        for x in range(self._visible_tab_count):
            if self.tap_dance_entries[x].save() != self.keyboard.tap_dance_get(x):
                has_changes = True
                self.tabs.setTabText(x, "{}*".format(x))
            else:
                self.tabs.setTabText(x, str(x))
        self.btn_save.setEnabled(has_changes)

    def on_timing_changed(self):
        self.update_modified_state()

    def _tap_dance_has_content(self, entry_idx):
        """Check if a tap dance entry has any keycodes assigned"""
        entry = self.tap_dance_entries[entry_idx]
        data = entry.save()  # Returns (on_tap, on_hold, on_double_tap, on_tap_hold, tapping_term)
        # Check if any of the 4 keycodes is not "KC_NO"
        return data[0] != "KC_NO" or data[1] != "KC_NO" or data[2] != "KC_NO" or data[3] != "KC_NO"

    def _find_last_used_index(self):
        """Find the index of the last tap dance that has content (counting back from max)"""
        for idx in range(len(self.tap_dance_entries) - 1, -1, -1):
            if self._tap_dance_has_content(idx):
                return idx
        return -1  # No tap dances have content

    def _update_visible_tabs(self):
        """Update which tabs are visible based on content and manual expansion"""
        if not self.keyboard or not self.tap_dance_entries:
            return

        max_tabs = len(self.tap_dance_entries)
        last_used = self._find_last_used_index()

        # Calculate visible count: last used + 1, or at least 1, plus any manually expanded
        base_visible = max(1, last_used + 1)
        self._visible_tab_count = min(max_tabs, base_visible + self._manually_expanded_count)

        # Remove all tabs first
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)

        # Add visible tap dance tabs
        for x in range(self._visible_tab_count):
            self.tabs.addTab(self.tap_dance_entries[x].widget(), str(x))

        # Add "+" tab if not all tabs are visible
        if self._visible_tab_count < max_tabs:
            plus_widget = QWidget()
            self.tabs.addTab(plus_widget, "+")
            self.tabs.currentChanged.connect(self._on_tab_changed)
        else:
            try:
                self.tabs.currentChanged.disconnect(self._on_tab_changed)
            except TypeError:
                pass

        self.update_modified_state()

    def _on_tab_changed(self, index):
        """Handle tab change - check if '+' tab was clicked"""
        if self._visible_tab_count < len(self.tap_dance_entries) and index == self._visible_tab_count:
            self._manually_expanded_count += 1
            try:
                self.tabs.currentChanged.disconnect(self._on_tab_changed)
            except TypeError:
                pass
            self._update_visible_tabs()
            # Update keycode buttons to show new tapdance count
            self.tabbed_keycodes.refresh_macro_buttons()
            self.tabs.setCurrentIndex(self._visible_tab_count - 1)
