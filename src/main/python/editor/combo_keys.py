# SPDX-License-Identifier: GPL-2.0-or-later
"""Key Combos editor.

A Key Combo is: hold one or more "held keys" (the 8 modifiers, Fn 1, Fn 2),
tap the "tapped key", and the keyboard sends the "output key" instead - with
the held modifiers suppressed, so the output arrives clean.
"""
import sip

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal, QObject, Qt
from PyQt5.QtWidgets import QTabWidget, QWidget, QGridLayout, QVBoxLayout, QLabel, QScrollArea, \
    QHBoxLayout, QPushButton, QGroupBox, QCheckBox

from protocol.constants import VIAL_PROTOCOL_DYNAMIC
from protocol.key_override import KeyOverrideEntry, KeyOverrideOptions
from widgets.keycode_button import KeycodeButton, install_click_away_deselect
from widgets.checkbox_no_padding import CheckBoxNoPadding
from tabbed_keycodes import TabbedKeycodes
from util import tr
from vial_device import VialKeyboard
from editor.basic_editor import BasicEditor


# layers: bits 0-11 = layers, bits 12-13 = Fn held keys
LAYERS_ALL = 0x0FFF
FN_SHIFT = 12
FN1 = 1 << 0
FN2 = 1 << 1

# Default activation events: activate when the tapped key goes down, when a
# required held key goes down, or when a negative mod (none here) goes up.
OPTIONS_DEFAULT = (1 << 0) | (1 << 1) | (1 << 2)

MOD_NAMES = ["LCtrl", "LShift", "LAlt", "LGui", "RCtrl", "RShift", "RAlt", "RGui"]
FN_NAMES = ["Fn 1", "Fn 2"]

EMPTY = ("KC_NO", "KC_NO", 0, 0, False)   # tapped, output, mods, fn, disabled


def model_is_used(model):
    tapped, output, mods, fn, disabled = model
    return tapped != "KC_NO" or output != "KC_NO" or mods != 0 or fn != 0


def _kc(v):
    """A fresh KeyOverrideEntry() carries integer 0 keycodes; entries read from
    the device carry qmk_id strings. Normalise to the string form."""
    return "KC_NO" if v in (0, None, "") else v


def entry_to_model(ko):
    """KeyOverrideEntry -> (tapped, output, held_mods, held_fn, disabled).

    An all-zero entry (the "unused" state) reads as an enabled,
    empty combo — not as a disabled one — so fresh tabs come up ready to
    edit."""
    model = (_kc(ko.trigger), _kc(ko.replacement), ko.trigger_mods & 0xFF,
             (ko.layers >> FN_SHIFT) & 0x3, False)
    if model_is_used(model):
        model = model[:4] + (not ko.options.enabled,)
    return model


def model_to_entry(model):
    """(tapped, output, held_mods, held_fn, disabled) -> KeyOverrideEntry.

    An unused combo (no keys, no held keys) serialises as the all-zero entry
    that means empty — never as an enabled entry with an empty trigger, which
    would activate on every key press."""
    if not model_is_used(model):
        return KeyOverrideEntry()
    tapped, output, mods, fn, disabled = model
    ko = KeyOverrideEntry()
    ko.trigger = tapped
    ko.replacement = output
    ko.trigger_mods = mods
    ko.suppressed_mods = mods          # output key is always sent clean
    ko.negative_mod_mask = 0
    ko.layers = LAYERS_ALL | ((fn & 0x3) << FN_SHIFT)
    ko.options = KeyOverrideOptions(OPTIONS_DEFAULT)
    ko.options.enabled = not disabled
    return ko


class ComboKeyWidget(KeycodeButton):
    """Palette-styled keycode button; the editor feeds the palette pick to the
    selected button, the button itself never opens the tray."""


class ComboKeyEntryUI(QObject):

    key_changed = pyqtSignal()
    key_selected = pyqtSignal(object)

    def __init__(self, idx):
        super().__init__()
        self.idx = idx
        # UI is built on the first widget() call - 100 of these exist and most
        # tabs are never opened. load()ed data is buffered in _pending until
        # then; save() serves it back so the entry keeps acting as the model.
        self.w2 = None
        self._pending = None

    # ---- UI ---------------------------------------------------------------

    def _ensure_ui(self):
        if self.w2 is not None:
            return
        idx = self.idx

        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        header_layout = QHBoxLayout()
        self.title_label = QLabel("<b>Key Combo {}</b>".format(idx + 1))
        self.title_label.setStyleSheet("font-size: 14pt;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        desc = QLabel(tr("ComboKeys",
                         "Hold the held key(s), tap the tapped key, and the output key is sent instead.\n"
                         "The held modifiers are not sent with the output key."))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray; font-size: 9pt;")
        main_layout.addWidget(desc)

        # Disable row + notice
        disable_row = QHBoxLayout()
        self.disable_chk = QCheckBox(tr("ComboKeys", "Disable"))
        self.disable_chk.stateChanged.connect(self._on_disable_toggled)
        disable_row.addWidget(self.disable_chk)
        disable_row.addStretch()
        main_layout.addLayout(disable_row)

        self.disabled_notice = QLabel(tr("ComboKeys",
                                         "This key combo is currently disabled. "
                                         "Untick \"Disable\" to reenable the combo"))
        self.disabled_notice.setWordWrap(True)
        self.disabled_notice.setStyleSheet("color: #d08020; font-weight: bold;")
        self.disabled_notice.hide()
        main_layout.addWidget(self.disabled_notice)

        # Keys group (greyed out while disabled)
        self.keys_group = QGroupBox(tr("ComboKeys", "Keys"))
        keys_layout = QVBoxLayout()

        instruction = QLabel(tr("ComboKeys", "Click a key to select, then choose from keycodes below"))
        instruction.setStyleSheet("color: gray; font-style: italic;")
        keys_layout.addWidget(instruction)

        grid = QGridLayout()

        # Held key: modifiers + Fn 1 / Fn 2
        grid.addWidget(QLabel(tr("ComboKeys", "Held key")), 0, 0, Qt.AlignTop)
        held = QWidget()
        held_layout = QGridLayout()
        held_layout.setContentsMargins(0, 0, 0, 0)
        self.mod_chks = [CheckBoxNoPadding(n) for n in MOD_NAMES]
        self.fn_chks = [CheckBoxNoPadding(n) for n in FN_NAMES]
        # LCtrl/RCtrl in a column, LShift/RShift, ... then Fn 1 / Fn 2
        for x in range(4):
            held_layout.addWidget(self.mod_chks[x], 0, x)
            held_layout.addWidget(self.mod_chks[x + 4], 1, x)
        held_layout.addWidget(self.fn_chks[0], 0, 4)
        held_layout.addWidget(self.fn_chks[1], 1, 4)
        for w in self.mod_chks + self.fn_chks:
            w.stateChanged.connect(self.on_key_changed)
        held.setLayout(held_layout)
        grid.addWidget(held, 0, 1, Qt.AlignLeft | Qt.AlignVCenter)

        self.kc_tapped = ComboKeyWidget()
        self.kc_tapped.changed.connect(self.on_key_changed)
        self.kc_tapped.selected.connect(self._on_key_selected)
        grid.addWidget(QLabel(tr("ComboKeys", "Tapped key")), 1, 0)
        grid.addWidget(self.kc_tapped, 1, 1, Qt.AlignLeft | Qt.AlignVCenter)

        self.kc_output = ComboKeyWidget()
        self.kc_output.changed.connect(self.on_key_changed)
        self.kc_output.selected.connect(self._on_key_selected)
        grid.addWidget(QLabel(tr("ComboKeys", "Output key")), 2, 0)
        grid.addWidget(self.kc_output, 2, 1, Qt.AlignLeft | Qt.AlignVCenter)

        # the key column takes the spare width, so the labels stay tight to the keys
        grid.setColumnStretch(1, 1)
        keys_layout.addLayout(grid)
        keys_layout.addStretch()
        self.keys_group.setLayout(keys_layout)

        scroll = QScrollArea()
        scroll.setWidget(self.keys_group)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        main_layout.addWidget(scroll)

        self.w2 = QWidget()
        self.w2.setLayout(main_layout)

        if self._pending is not None:
            self._apply(self._pending)

    def widget(self):
        self._ensure_ui()
        return self.w2

    def key_widgets(self):
        self._ensure_ui()
        return [self.kc_tapped, self.kc_output]

    # ---- model ------------------------------------------------------------

    def load(self, model):
        self._pending = tuple(model)
        if self.w2 is not None:
            self._apply(model)

    def _apply(self, model):
        tapped, output, mods, fn, disabled = model
        widgets = [self.kc_tapped, self.kc_output, self.disable_chk] + self.mod_chks + self.fn_chks
        for w in widgets:
            w.blockSignals(True)
        self.kc_tapped.set_keycode(tapped)
        self.kc_output.set_keycode(output)
        for x, chk in enumerate(self.mod_chks):
            chk.setChecked(bool(mods & (1 << x)))
        for x, chk in enumerate(self.fn_chks):
            chk.setChecked(bool(fn & (1 << x)))
        self.disable_chk.setChecked(disabled)
        for w in widgets:
            w.blockSignals(False)
        self._refresh_disabled_look(disabled)

    def save(self):
        if self.w2 is None:
            # Unbuilt entries can't have unsaved edits: hand back the loaded data
            return self._pending if self._pending is not None else EMPTY
        mods = 0
        for x, chk in enumerate(self.mod_chks):
            mods |= int(chk.isChecked()) << x
        fn = 0
        for x, chk in enumerate(self.fn_chks):
            fn |= int(chk.isChecked()) << x
        return (self.kc_tapped.keycode, self.kc_output.keycode, mods, fn, self.disable_chk.isChecked())

    # ---- signals ----------------------------------------------------------

    def _on_key_selected(self, widget):
        self.key_selected.emit(widget)

    def _on_disable_toggled(self, state):
        self._refresh_disabled_look(bool(state))
        self.on_key_changed()

    def _refresh_disabled_look(self, disabled):
        self.keys_group.setEnabled(not disabled)
        self.disabled_notice.setVisible(disabled)

    def on_key_changed(self):
        self.key_changed.emit()


class ComboKeys(BasicEditor):

    def __init__(self):
        super().__init__()
        self.keyboard = None
        self.selected_key_widget = None

        self.entries = []
        self.entries_available = []
        self.tabs = QTabWidget()

        # Dynamic tab tracking: show used entries + 1, "+" tab reveals another
        self._visible_tab_count = 1
        self._manually_expanded_count = 0
        self._plus_connected = False
        for x in range(128):
            entry = ComboKeyEntryUI(x)
            entry.key_changed.connect(self.on_key_changed)
            entry.key_selected.connect(self.on_key_widget_selected)
            self.entries_available.append(entry)

        self.addWidget(self.tabs)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_save = QPushButton(tr("ComboKeys", "Save"))
        self.btn_save.setMinimumHeight(30)
        self.btn_save.setMaximumHeight(30)
        self.btn_save.setMinimumWidth(80)
        self.btn_save.setStyleSheet("QPushButton { border-radius: 5px; }")
        self.btn_save.clicked.connect(self.on_save)
        self.btn_revert = QPushButton(tr("ComboKeys", "Revert"))
        self.btn_revert.setMinimumHeight(30)
        self.btn_revert.setMaximumHeight(30)
        self.btn_revert.setMinimumWidth(80)
        self.btn_revert.setStyleSheet("QPushButton { border-radius: 5px; }")
        self.btn_revert.clicked.connect(self.on_revert)
        buttons.addWidget(self.btn_save)
        buttons.addWidget(self.btn_revert)
        self.addLayout(buttons)

        # Keycode palette always visible at the bottom
        self.tabbed_keycodes = TabbedKeycodes()
        install_click_away_deselect(self.tabs, self._clear_key_selection)
        self.tabbed_keycodes.keycode_changed.connect(self.on_keycode_selected)
        self.addWidget(self.tabbed_keycodes)

    # ---- palette wiring ---------------------------------------------------

    def on_key_widget_selected(self, widget):
        if self.selected_key_widget is not None and self.selected_key_widget != widget:
            try:
                if not sip.isdeleted(self.selected_key_widget):
                    self.selected_key_widget.set_selected(False)
            except RuntimeError:
                pass
            self.selected_key_widget = None
        self.selected_key_widget = widget
        widget.set_selected(True)

    def _clear_key_selection(self):
        """Click on empty space in the editor: unselect the selected key."""
        w = self.selected_key_widget
        self.selected_key_widget = None
        if w is not None:
            try:
                if not sip.isdeleted(w):
                    w.set_selected(False)
            except RuntimeError:
                pass

    def on_keycode_selected(self, keycode):
        if self.selected_key_widget is not None:
            try:
                if not sip.isdeleted(self.selected_key_widget):
                    self.selected_key_widget.on_keycode_changed(keycode)
            except RuntimeError:
                self.selected_key_widget = None

    # ---- device sync ------------------------------------------------------

    def _device_model(self, idx):
        return entry_to_model(self.keyboard.key_override_get(idx))

    def rebuild_ui(self):
        self._manually_expanded_count = 0
        self._update_visible_tabs()

    def reload_ui(self):
        for x, e in enumerate(self.entries):
            e.load(self._device_model(x))
        self.update_modified_state()

    def on_save(self):
        for x, e in enumerate(self.entries):
            self.keyboard.key_override_set(x, model_to_entry(e.save()))
        self.update_modified_state()

    def on_revert(self):
        self.keyboard.reload_key_override()
        self.reload_ui()

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            self.rebuild_ui()

    def valid(self):
        return isinstance(self.device, VialKeyboard) and \
               (self.device.keyboard and self.device.keyboard.vial_protocol >= VIAL_PROTOCOL_DYNAMIC
                and self.device.keyboard.key_override_count > 0)

    def on_key_changed(self):
        self.update_modified_state()

    # ---- tabs -------------------------------------------------------------

    def _find_last_used_index(self):
        for idx in range(self.keyboard.key_override_count - 1, -1, -1):
            if model_is_used(self._device_model(idx)):
                return idx
        return -1

    def _update_visible_tabs(self):
        if not self.keyboard:
            return

        max_tabs = min(self.keyboard.key_override_count, len(self.entries_available))
        last_used = self._find_last_used_index()
        base_visible = max(1, last_used + 1)
        self._visible_tab_count = min(max_tabs, base_visible + self._manually_expanded_count)

        if self._plus_connected:
            self.tabs.currentChanged.disconnect(self._on_tab_changed)
            self._plus_connected = False

        while self.tabs.count() > 0:
            self.tabs.removeTab(0)

        self.entries = self.entries_available[:self._visible_tab_count]
        for x, e in enumerate(self.entries):
            self.tabs.addTab(e.widget(), str(x + 1))

        if self._visible_tab_count < max_tabs:
            self.tabs.addTab(QWidget(), "+")
            self.tabs.currentChanged.connect(self._on_tab_changed)
            self._plus_connected = True

        self.reload_ui()

    def _on_tab_changed(self, index):
        if self._visible_tab_count < self.keyboard.key_override_count and index == self._visible_tab_count:
            self._manually_expanded_count += 1
            self._update_visible_tabs()
            self.tabs.setCurrentIndex(self._visible_tab_count - 1)

    def update_modified_state(self):
        """Mark modified tabs with '*' and enable Save only when needed."""
        has_changes = False
        for x, e in enumerate(self.entries):
            if e.save() != self._device_model(x):
                has_changes = True
                self.tabs.setTabText(x, "{}*".format(x + 1))
            else:
                self.tabs.setTabText(x, str(x + 1))
        self.btn_save.setEnabled(has_changes)
