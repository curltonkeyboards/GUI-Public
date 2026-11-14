# SPDX-License-Identifier: GPL-2.0-or-later
"""Key Shortcuts editor (the keyboard's key overrides).

A Key Shortcut is: hold one or more modifiers (and / or Fn 1, Fn 2), press a
key, and the keyboard sends the "output key" instead - with the held
modifiers suppressed, so the output arrives clean. The modifiers and the key
are set by recording them (widgets/shortcut_recorder.py); the key can also be
picked from the keys below, for keys a computer keyboard does not have.
"""
import math

import sip

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal, QObject, Qt
from PyQt5.QtWidgets import QTabWidget, QWidget, QGridLayout, QVBoxLayout, QLabel, QScrollArea, \
    QHBoxLayout, QPushButton, QGroupBox, QCheckBox

from protocol.constants import VIAL_PROTOCOL_DYNAMIC
from protocol.key_override import KeyOverrideEntry, KeyOverrideOptions
from widgets.keycode_button import KeycodeButton, install_click_away_deselect
from widgets.shortcut_recorder import ShortcutRecorder, held_text
from tabbed_keycodes import TabbedKeycodes
from util import tr, is_hid_transfer_active
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


# The Fn keys, as the keymap names them and as raw keycode numbers
FN_KEYCODES = {"FN_MO13": FN1, 0x7C77: FN1, "FN_MO23": FN2, 0x7C78: FN2}


def poll_fn_held(keyboard, cache=None):
    """Which Fn keys are held on the keyboard right now: bit 0 = Fn 1, bit 1 =
    Fn 2. None if it cannot be told just now. Raises if the keyboard cannot
    be asked at all.

    Fn 1 / Fn 2 send nothing to the computer, so this reads the keyboard's
    switch state (the same read-only request the matrix tester makes) and
    looks each pressed key up in the keymap, on the keyboard's highest active
    layer and through transparent keys down to layer 1. (The keyboard itself
    passes a transparent key only through layers that are switched on; it
    reports just its highest active layer, so every layer below is looked
    at here - the same answer unless a layer in between is off and holds an
    Fn key at that spot.) Nothing is written.

    `cache` (a dict kept by the caller for one recording) saves asking for
    the active layer again while the same keys stay down."""
    if keyboard is None:
        raise RuntimeError("no keyboard")
    if is_hid_transfer_active():
        return None                     # a loop transfer owns the connection: skip this look
    data = keyboard.matrix_poll()
    if not data:
        raise RuntimeError("the keyboard does not report its keys")

    rows = getattr(keyboard, "firmware_rows", 0) or keyboard.rows
    cols = getattr(keyboard, "firmware_cols", 0) or keyboard.cols
    row_size = math.ceil(cols / 8)      # one bit per key, most significant byte first
    pressed = []
    for row in range(rows):
        row_data = data[2 + row * row_size:2 + (row + 1) * row_size]
        if len(row_data) < row_size:
            break
        bits = int.from_bytes(bytes(row_data), "big")
        for col in range(cols):
            if bits & (1 << col):
                pressed.append((row, col))
    if not pressed:
        if cache is not None:
            cache.clear()
        return 0

    layer = 0
    if keyboard.layers > 1:
        key = tuple(pressed)
        if cache is not None and cache.get("pressed") == key:
            layer = cache.get("layer", 0)
        else:
            layer = keyboard.get_active_layer() or 0
            if cache is not None:
                cache["pressed"], cache["layer"] = key, layer
    layer = min(layer, keyboard.layers - 1)

    held = 0
    for row, col in pressed:
        for l in range(layer, -1, -1):
            code = keyboard.layout.get((l, row, col))
            if code in ("KC_TRNS", 1) and l > 0:
                continue
            held |= FN_KEYCODES.get(code, 0)
            break
    return held


def model_is_used(model):
    tapped, output, mods, fn, disabled = model
    return tapped != "KC_NO" or output != "KC_NO" or mods != 0 or fn != 0


def _kc(v):
    """A fresh KeyOverrideEntry() carries integer 0 keycodes; entries read from
    the device carry code_id strings. Normalise to the string form."""
    return "KC_NO" if v in (0, None, "") else v


def entry_to_model(ko):
    """KeyOverrideEntry -> (tapped, output, held_mods, held_fn, disabled).

    An all-zero entry (the "unused" state) reads as an enabled,
    empty combo — not as a disabled one — so fresh tabs come up ready to
    edit."""
    tapped, output = _kc(ko.trigger), _kc(ko.replacement)
    mods = ko.trigger_mods & 0xFF
    if tapped == "KC_NO" and output == "KC_NO" and mods == 0:
        # No keys and no held modifier: an empty slot, whatever its layer /
        # Fn bits say (a freshly reset keyboard fills every slot's layer word
        # with ones, which would otherwise read as "Fn 1 + Fn 2" and make all
        # 100 slots look configured).
        return EMPTY
    model = (tapped, output, mods, (ko.layers >> FN_SHIFT) & 0x3, False)
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
        # reads the Fn keys held on the keyboard while recording (set by the editor)
        self.fn_poll = None

    # ---- UI ---------------------------------------------------------------

    def _ensure_ui(self):
        if self.w2 is not None:
            return
        idx = self.idx

        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        header_layout = QHBoxLayout()
        self.title_label = QLabel("<b>Key Shortcut {}</b>".format(idx + 1))
        self.title_label.setStyleSheet("font-size: 14pt;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        desc = QLabel(tr("ComboKeys",
                         "Hold the modifiers, press the key, and the output key is sent instead.\n"
                         "The held modifiers are not sent with the output key."))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: palette(dark); font-size: 9pt;")
        main_layout.addWidget(desc)

        # Disable row + notice
        disable_row = QHBoxLayout()
        self.disable_chk = QCheckBox(tr("ComboKeys", "Disable"))
        self.disable_chk.stateChanged.connect(self._on_disable_toggled)
        disable_row.addWidget(self.disable_chk)
        disable_row.addStretch()
        main_layout.addLayout(disable_row)

        self.disabled_notice = QLabel(tr("ComboKeys",
                                         "This key shortcut is currently disabled. "
                                         "Untick \"Disable\" to turn it back on."))
        self.disabled_notice.setWordWrap(True)
        self.disabled_notice.setStyleSheet("color: #d08020; font-weight: bold;")
        self.disabled_notice.hide()
        main_layout.addWidget(self.disabled_notice)

        # Keys group (greyed out while disabled)
        self.keys_group = QGroupBox(tr("ComboKeys", "Keys"))
        keys_layout = QVBoxLayout()

        instruction = QLabel(tr("ComboKeys",
                                "Press Record, hold the modifiers (Ctrl, Shift, Alt, Win, and Fn 1 / Fn 2 "
                                "on the MIDIswitch) and press the key. "
                                "Or click a key box and choose from the keys below."))
        instruction.setWordWrap(True)
        instruction.setStyleSheet("color: palette(dark); font-style: italic;")
        keys_layout.addWidget(instruction)

        grid = QGridLayout()

        # The shortcut: the modifiers and Fn keys held (recorded), then the key
        self._mods = 0
        self._fn = 0
        grid.addWidget(QLabel(tr("ComboKeys", "Shortcut")), 0, 0)
        shortcut = QWidget()
        shortcut_layout = QHBoxLayout()
        shortcut_layout.setContentsMargins(0, 0, 0, 0)
        shortcut_layout.setSpacing(10)
        self.held_label = QLabel()
        self.held_label.setStyleSheet("font-weight: bold;")
        self.kc_tapped = ComboKeyWidget()
        self.kc_tapped.changed.connect(self.on_key_changed)
        self.kc_tapped.selected.connect(self._on_key_selected)
        self.recorder = ShortcutRecorder()
        self.recorder.set_fn_poll(self._poll_fn)
        self.recorder.recorded.connect(self._on_recorded)
        self.recorder.held_changed.connect(self._on_recording_held)
        self.recorder.stopped.connect(self._on_recording_stopped)
        self.clear_shortcut = QPushButton(tr("ComboKeys", "Clear"))
        self.clear_shortcut.clicked.connect(lambda: self._set_shortcut(0, "KC_NO", 0))
        shortcut_layout.addWidget(self.held_label)
        shortcut_layout.addWidget(self.kc_tapped)
        shortcut_layout.addSpacing(8)
        shortcut_layout.addWidget(self.recorder)
        shortcut_layout.addWidget(self.clear_shortcut)
        shortcut_layout.addStretch(1)
        shortcut.setLayout(shortcut_layout)
        grid.addWidget(shortcut, 0, 1, Qt.AlignLeft | Qt.AlignVCenter)

        self.record_note = QLabel()
        self.record_note.setStyleSheet("color: palette(dark); font-size: 9pt;")
        grid.addWidget(self.record_note, 1, 1, Qt.AlignLeft)

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
        widgets = [self.kc_tapped, self.kc_output, self.disable_chk]
        for w in widgets:
            w.blockSignals(True)
        self.recorder.stop("")
        self.kc_tapped.set_keycode(tapped)
        self.kc_output.set_keycode(output)
        self._mods = mods & 0xFF
        self._fn = fn & 0x3
        self._show_held(self._mods, self._fn)
        self.record_note.setText("")
        self.disable_chk.setChecked(disabled)
        for w in widgets:
            w.blockSignals(False)
        self._refresh_disabled_look(disabled)

    def save(self):
        if self.w2 is None:
            # Unbuilt entries can't have unsaved edits: hand back the loaded data
            return self._pending if self._pending is not None else EMPTY
        return (self.kc_tapped.keycode, self.kc_output.keycode, self._mods, self._fn,
                self.disable_chk.isChecked())

    # ---- the recorded shortcut ----------------------------------------------

    def _poll_fn(self):
        """The Fn keys held on the keyboard now (asked by the recorder while
        it records). Raises when there is no keyboard to ask."""
        if self.fn_poll is None:
            raise RuntimeError("no keyboard")
        return self.fn_poll()

    def _show_held(self, mods, fn):
        text = held_text(mods, fn)
        self.held_label.setText(text + "  +" if text else "")
        self.held_label.setVisible(bool(text))

    def _set_shortcut(self, mods, keycode, fn):
        self._mods = mods & 0xFF
        self._fn = fn & 0x3
        self._show_held(self._mods, self._fn)
        self.kc_tapped.blockSignals(True)
        self.kc_tapped.set_keycode(keycode)
        self.kc_tapped.blockSignals(False)
        self.record_note.setText("")
        self.on_key_changed()

    def _on_recorded(self, mods, keycode, fn):
        self._set_shortcut(mods, keycode, fn)

    def _on_recording_held(self, mods, fn):
        # while recording, show the modifiers and Fn keys as they go down
        self._show_held(mods, fn)
        if self.recorder.fn_watching():
            note = tr("ComboKeys", "Recording: hold the modifiers (and Fn 1 / Fn 2 on the MIDIswitch), "
                                   "then press the key.")
        else:
            note = tr("ComboKeys", "Recording: hold the modifiers, then press the key. "
                                   "(Fn 1 / Fn 2 can only be recorded with the MIDIswitch connected.)")
        self.record_note.setText(note)

    def _on_recording_stopped(self, reason):
        self._show_held(self._mods, self._fn)       # back to what it was
        self.record_note.setText(reason)

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
            entry.fn_poll = self._poll_fn_held
            self.entries_available.append(entry)
        self._fn_cache = {}

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

    # ---- Fn 1 / Fn 2 while recording ---------------------------------------

    def _poll_fn_held(self):
        """Read-only look at the keyboard for the Fn keys held now; raises when
        there is no keyboard that can be asked (the recorder then stops asking)."""
        if not self.valid() or self.keyboard is None:
            raise RuntimeError("no keyboard")
        return poll_fn_held(self.keyboard, self._fn_cache)

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
