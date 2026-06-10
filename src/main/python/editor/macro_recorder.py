# SPDX-License-Identifier: GPL-2.0-or-later
import sys
import sip

from PyQt5.QtWidgets import QPushButton, QHBoxLayout, QWidget, QLabel, QTabWidget

from editor.basic_editor import BasicEditor
from macro.macro_action import ActionText, ActionTap, ActionDown, ActionUp
from macro.macro_action_ui import ui_action
from macro.macro_key import KeyString, KeyDown, KeyUp, KeyTap
from macro.macro_optimizer import macro_optimize
from macro.macro_tab import MacroTab
from protocol.feature_names import get_feature_name_manager, FEATURE_MACRO
from unlocker import Unlocker
from util import tr
from vial_device import VialKeyboard
from tabbed_keycodes import TabbedKeycodes


class MacroRecorder(BasicEditor):

    def __init__(self):
        super().__init__()

        self.keyboard = None
        self.suppress_change = False
        self._names_dirty = False

        self.keystrokes = []
        self.macro_tabs = []
        self.macro_tab_w = []

        self.recorder = None
        self.selected_key_widget = None  # Track currently selected key widget

        # Dynamic tab tracking
        self._visible_tab_count = 1  # Minimum 1 tab visible
        self._manually_expanded_count = 0  # Tabs added via "+" button

        if sys.platform.startswith("linux"):
            from macro.macro_recorder_linux import LinuxRecorder

            self.recorder = LinuxRecorder()
        elif sys.platform.startswith("win"):
            from macro.macro_recorder_windows import WindowsRecorder

            self.recorder = WindowsRecorder()

        if self.recorder:
            self.recorder.keystroke.connect(self.on_keystroke)
            self.recorder.stopped.connect(self.on_stop)
        self.recording = False

        self.recording_tab = None
        self.recording_append = False

        # Macro tabs
        self.tabs = QTabWidget()
        self.addWidget(self.tabs)

        # Memory label
        self.lbl_memory = QLabel()

        buttons = QHBoxLayout()
        buttons.addWidget(self.lbl_memory)
        buttons.addStretch()

        self.addLayout(buttons)

        # TabbedKeycodes always visible at the bottom
        self.tabbed_keycodes = TabbedKeycodes()
        self.tabbed_keycodes.keycode_changed.connect(self.on_keycode_selected)
        self.addWidget(self.tabbed_keycodes)

    def valid(self):
        return isinstance(self.device, VialKeyboard)

    def rebuild(self, device):
        super().rebuild(device)
        if not self.valid():
            return
        self.keyboard = self.device.keyboard

        for x in range(self.keyboard.macro_count - len(self.macro_tab_w)):
            tab = MacroTab(self, self.recorder is not None, macro_index=len(self.macro_tab_w))
            tab.changed.connect(self.on_change)
            tab.name_changed.connect(self.on_name_changed)
            tab.save_clicked.connect(self.on_save)
            tab.revert_clicked.connect(self.on_revert)
            tab.key_selected.connect(self.on_key_widget_selected)
            tab.widget_deleted.connect(self.on_widget_deleted)
            self.macro_tabs.append(tab)
            w = QWidget()
            w.setLayout(tab)
            self.macro_tab_w.append(w)

        # only show the number of macro editors that keyboard supports
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)
        for x, w in enumerate(self.macro_tab_w[:self.keyboard.macro_count]):
            self.tabs.addTab(w, "")
            # Update macro index in case of reuse
            self.macro_tabs[x].set_macro_index(x)

        # deserialize macros that came from keyboard
        self.deserialize(self.keyboard.macro)

        # Reset manual expansion count on rebuild, then update visible tabs
        self._manually_expanded_count = 0
        self._update_visible_tabs()

        # Set keyboard reference for tabbed keycodes
        self.tabbed_keycodes.set_keyboard(self.keyboard)
        # Set editor reference so MacroTab can get accurate visible tab counts
        self.tabbed_keycodes.set_editors(macro_recorder=self)

        self.on_change()

    def on_widget_deleted(self, widget):
        """Clear reference to widget that is being deleted"""
        if self.selected_key_widget is widget:
            self.selected_key_widget = None

    def on_key_widget_selected(self, widget):
        """Handle when a key widget is selected in a macro tab"""
        # Deselect the previously selected widget (with safety check)
        if self.selected_key_widget is not None and self.selected_key_widget != widget:
            try:
                # Check if the widget is still valid (not deleted)
                if not sip.isdeleted(self.selected_key_widget):
                    self.selected_key_widget.set_selected(False)
            except RuntimeError:
                pass  # Widget was already deleted
            self.selected_key_widget = None

        # Select the new widget
        self.selected_key_widget = widget
        widget.set_selected(True)

    def on_keycode_selected(self, keycode):
        """Handle keycode selection from TabbedKeycodes"""
        if self.selected_key_widget is not None:
            try:
                # Check if the widget is still valid (not deleted)
                if not sip.isdeleted(self.selected_key_widget):
                    self.selected_key_widget.set_keycode(keycode)
            except RuntimeError:
                self.selected_key_widget = None

    def update_tab_titles(self):
        macros = self.keyboard.macro.split(b"\x00")
        mgr = get_feature_name_manager()
        # Only update titles for visible tabs (not the "+" tab)
        for x in range(self._visible_tab_count):
            title = mgr.get_name(FEATURE_MACRO, x)
            if macros[x] != self.keyboard.macro_serialize(self.macro_tabs[x].actions()):
                title += "*"
            self.tabs.setTabText(x, title)

    def on_stop(self):
        # Re-enable all visible tabs (and "+" tab if present)
        for x in range(self._visible_tab_count):
            self.tabs.tabBar().setTabEnabled(x, True)
        if self._visible_tab_count < self.keyboard.macro_count:
            self.tabs.tabBar().setTabEnabled(self._visible_tab_count, True)

        if not self.recording_append:
            self.recording_tab.clear()

        self.keystrokes = macro_optimize(self.keystrokes)
        actions = []
        for k in self.keystrokes:
            if isinstance(k, KeyString):
                actions.append(ActionText(k.string))
            else:
                cls = {KeyDown: ActionDown, KeyUp: ActionUp, KeyTap: ActionTap}[type(k)]
                actions.append(cls([k.keycode.qmk_id]))

        # merge: i.e. replace multiple instances of KeyDown with a single multi-key ActionDown, etc
        actions = self.keyboard.macro_deserialize(self.keyboard.macro_serialize(actions))
        for act in actions:
            self.recording_tab.add_action(ui_action[type(act)](self.recording_tab.container, act))

    def on_keystroke(self, keystroke):
        self.keystrokes.append(keystroke)

    def _get_current_loop_modes(self):
        """Get current loop modes from all macro tabs"""
        return [self.macro_tabs[x].get_loop_mode() for x in range(self.keyboard.macro_count)]

    def _get_current_sync_flags(self):
        """Get current sync-to-BPM flags from all macro tabs"""
        return [self.macro_tabs[x].get_sync_to_bpm() for x in range(self.keyboard.macro_count)]

    def on_name_changed(self):
        """Handle macro name change - mark dirty so save button enables and refresh labels"""
        self._names_dirty = True
        # Refresh keycode button labels to show new custom name
        self.tabbed_keycodes.recreate_keycode_buttons()
        self.on_change()

    def on_change(self):
        if self.suppress_change:
            return

        data = self.serialize()
        memory = len(data)
        self.lbl_memory.setText("Memory used by macros: {}/{}".format(memory, self.keyboard.macro_memory))

        # Check if anything changed: macro data, loop modes, sync flags, or names
        data_changed = data != self.keyboard.macro
        loop_modes_changed = self._get_current_loop_modes() != self.keyboard.get_macro_loop_modes()
        sync_flags_changed = self._get_current_sync_flags() != self.keyboard.get_macro_sync_flags()
        has_changes = data_changed or loop_modes_changed or sync_flags_changed or self._names_dirty

        save_enabled = has_changes and memory <= self.keyboard.macro_memory
        # Update save button on all tabs
        for tab in self.macro_tabs[:self.keyboard.macro_count]:
            tab.set_save_enabled(save_enabled)

        self.lbl_memory.setStyleSheet("QLabel { color: red; }" if memory > self.keyboard.macro_memory else "")
        self.update_tab_titles()

    def serialize(self):
        macros = []
        for x, t in enumerate(self.macro_tabs[:self.keyboard.macro_count]):
            macros.append(t.actions())
        return self.keyboard.macros_serialize(macros)

    def deserialize(self, data):
        self.suppress_change = True
        macros = self.keyboard.macros_deserialize(data)
        for macro, tab in zip(macros, self.macro_tabs[:self.keyboard.macro_count]):
            tab.clear()
            for act in macro:
                tab.add_action(ui_action[type(act)](tab.container, act))
        # Load loop modes from keyboard
        loop_modes = self.keyboard.get_macro_loop_modes()
        for x, mode in enumerate(loop_modes[:self.keyboard.macro_count]):
            self.macro_tabs[x].set_loop_mode(mode)
        # Load sync flags from keyboard
        sync_flags = self.keyboard.get_macro_sync_flags()
        for x, sync in enumerate(sync_flags[:self.keyboard.macro_count]):
            self.macro_tabs[x].set_sync_to_bpm(sync)
        self.suppress_change = False

    def on_revert(self):
        self.keyboard.reload_macros()
        self.deserialize(self.keyboard.macro)
        self._names_dirty = False
        self.on_change()

    def on_save(self):
        Unlocker.unlock(self.device.keyboard)
        self.keyboard.set_macro(self.serialize())
        # Save loop modes and sync flags to keyboard
        loop_modes = self._get_current_loop_modes()
        sync_flags = self._get_current_sync_flags()
        self.keyboard.set_macro_loop_modes(loop_modes)
        self.keyboard.set_macro_sync_flags(sync_flags)
        self._names_dirty = False
        self.on_change()

    def _find_last_used_index(self):
        """Find the index of the last macro that has content (counting back from max)"""
        for idx in range(self.keyboard.macro_count - 1, -1, -1):
            if len(self.macro_tabs[idx].actions()) > 0:
                return idx
        return -1  # No macros have content

    def _update_visible_tabs(self):
        """Update which tabs are visible based on content and manual expansion"""
        if not self.keyboard:
            return

        max_tabs = self.keyboard.macro_count
        last_used = self._find_last_used_index()

        # Calculate visible count: last used + 1, or at least 1, plus any manually expanded
        base_visible = max(1, last_used + 1)
        self._visible_tab_count = min(max_tabs, base_visible + self._manually_expanded_count)

        # Remove all tabs first
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)

        # Add visible macro tabs
        for x in range(self._visible_tab_count):
            self.tabs.addTab(self.macro_tab_w[x], "")
            self.macro_tabs[x].set_macro_index(x)

        # Add "+" tab if not all tabs are visible
        if self._visible_tab_count < max_tabs:
            plus_widget = QWidget()
            self.tabs.addTab(plus_widget, "+")
            # Connect tab change to detect "+" click
            self.tabs.currentChanged.connect(self._on_tab_changed)
        else:
            # Disconnect if all tabs shown
            try:
                self.tabs.currentChanged.disconnect(self._on_tab_changed)
            except TypeError:
                pass  # Not connected

        self.update_tab_titles()

    def _on_tab_changed(self, index):
        """Handle tab change - check if '+' tab was clicked"""
        # Check if the "+" tab was clicked (last tab when not all visible)
        if self._visible_tab_count < self.keyboard.macro_count and index == self._visible_tab_count:
            # Expand one more tab
            self._manually_expanded_count += 1
            # Disconnect before updating to avoid recursion
            try:
                self.tabs.currentChanged.disconnect(self._on_tab_changed)
            except TypeError:
                pass
            self._update_visible_tabs()
            # Update keycode buttons to show new macro count
            self.tabbed_keycodes.refresh_macro_buttons()
            # Switch to the newly visible tab
            self.tabs.setCurrentIndex(self._visible_tab_count - 1)
