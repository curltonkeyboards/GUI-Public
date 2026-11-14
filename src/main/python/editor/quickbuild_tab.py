# SPDX-License-Identifier: GPL-2.0-or-later
"""The QuickBuild tab: what each of the 100 QuickBuild buttons does, with the
editors for the things QuickBuilds play as tabs beside it.

With firmware that has the app-config command (protocol/app_config.py) the
list can be changed from here. Older firmware has no such command, so there
the list is read-only: it is read out of the keyboard's settings image with
the same read command "Save keyboard clone" uses."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDialog,
                             QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QAbstractItemView,
                             QFormLayout, QDialogButtonBox, QSpinBox)

from editor.grouped_editor import GroupedEditor
from protocol.app_config import AppConfig
from protocol.feature_names import (get_feature_name_manager, FEATURE_ARP, FEATURE_SEQ, FEATURE_DELAY,
                                    FEATURE_TOGGLE, FEATURE_MACRO)
from widgets.combo_box import ArrowComboBox
from util import tr
from vial_device import VialKeyboard

QUICKBUILD_COUNT = 100

# Where older firmware keeps the assignments in its settings image: a two-byte
# marker, then (category, slot, flags) for each of the 100 buttons.
QB_STORE_ADDRESS = 64722
QB_STORE_MARKER = bytes([0xDB, 0x04])
QB_UNSET = 0xFF

# The firmware's category numbers (master_menu_categories / MM_CAT_*):
# number -> (name, how many slots)
CATEGORIES = {
    0: ("Arpeggiator (old)", 4), 1: ("Step Sequencer (old)", 8), 2: ("Delay (old)", 4),
    3: ("Custom SmartChord", 20), 4: ("Dynamic chord", 8), 5: ("AutoFader", 40),
    6: ("Drum Machine", 20), 7: ("Chord progression", 8), 8: ("Bass line", 6), 9: ("Lead line", 6),
    10: ("Ear Trainer", 10), 11: ("Interval", 11), 12: ("3-note chord", 12), 13: ("4-note chord", 16),
    14: ("5-note chord", 16), 15: ("6-note chord", 12), 16: ("Extended chord", 22), 17: ("Scale", 16),
    18: ("DrumLIVE", 48), 19: ("Loop", 8), 20: ("Loop modifier", 10), 21: ("CC message", 1),
    22: ("Rhythm Engine", 20), 23: ("Factory delay", 48), 24: ("Custom delay", 50),
    25: ("Factory arpeggio", 119), 26: ("User arpeggio", 40), 27: ("User sequence", 40),
    28: ("Basics", 35), 29: ("ThruLoop", 8), 30: ("Macro", 255), 31: ("Toggle", 100),
    32: ("Multi Channel", 16), 33: ("KeySplit", 10),
}
# What the "Change" dialog offers, in the order of the keyboard's own menu.
OFFERED = [25, 26, 27, 23, 24, 12, 13, 14, 15, 16, 11, 17, 3, 4, 5, 6, 22, 10, 18, 19, 20, 29,
           32, 33, 21, 30, 31, 28]

# The names the keyboard's own menus use (firmware: basics group / leaf names in
# arpeggiator.c, get_delay_slot_name() in orthomidi5x14.c).
# Basics: (group, name, offered in the dialog)
BASICS = [
    ("Channel", "Touch Dial", True), ("Channel", "Up", True), ("Channel", "Down", True),
    ("Transpose", "Touch Dial", True), ("Transpose", "Up", True), ("Transpose", "Down", True),
    ("Articulation", "Touch Dial", True), ("Articulation", "Up", True), ("Articulation", "Down", True),
    ("SmartChord", "Touch Dial", True),
    ("Note Doubler", "Cycle (old)", False), ("KeySplit", "On/Off (old)", False),
    ("TripleSplit", "On/Off (old)", False),
    ("BPM", "Up", True), ("BPM", "Down", True), ("BPM", "Tap", True), ("BPM", "Touch Dial", True),
    ("Octave", "Up", True), ("Octave", "Down", True),
    ("Note Doubler", "Cycle", True), ("Note Doubler", "+1 Oct", True), ("Note Doubler", "+2 Oct", True),
    ("Note Doubler", "-1 Oct", True), ("Note Doubler", "Off", True),
    ("Lighting", "On/Off", True), ("Lighting", "Preset +", True), ("Lighting", "Preset -", True),
    ("Lighting", "Bright +", True), ("Lighting", "Bright -", True), ("Lighting", "Speed +", True),
    ("Lighting", "Speed -", True), ("Lighting", "Hue +", True), ("Lighting", "Hue -", True),
    ("Lighting", "Sat +", True), ("Lighting", "Sat -", True),
]
# Factory delays: 5 rates x (Note, Dot, Trip) x (Short, Med, Long), then 3 pitch delays
FACTORY_DELAYS = ["{} {} {}".format(rate, timing, length)
                  for rate in ("1/1", "1/2", "1/4", "1/8", "1/16")
                  for timing in ("Note", "Dot", "Trip")
                  for length in ("Short", "Med", "Long")] + \
                 ["1/4 Pitch Dly", "1/8 Pitch Dly", "1/16 Pitch Dly"]
RHYTHM_INSTRUMENTS = ["Chords", "Arp", "Bass", "Lead"]

# CC QuickBuilds: what the key sends is a keycode kept beside the assignment.
# (key, name, has a CC number, has a value, what the value is called)
CC_KINDS = [
    ("cc", "Send a CC value", True, True, "Value"),
    ("cc_up", "CC up", True, False, ""),
    ("cc_down", "CC down", True, False, ""),
    ("cc_toggle", "CC on/off", True, False, ""),
    ("cc_touch_dial", "CC on the touch dial", True, False, ""),
    ("program", "Program change", False, True, "Program"),
    ("program_up", "Next program", False, False, ""),
    ("program_down", "Previous program", False, False, ""),
    ("bank_msb", "Bank MSB", False, True, "Bank"),
    ("bank_lsb", "Bank LSB", False, True, "Bank"),
    ("bank_up", "Bank up", False, False, ""),
    ("bank_down", "Bank down", False, False, ""),
]
# Where older firmware keeps the CC keycodes in its settings image: a marker,
# then (keycode low, keycode high, channel) for each of the 100 buttons.
CC_STORE_ADDRESS = 64018
CC_STORE_MARKER = bytes([0x01, 0xCC])


def cc_keycode(kind, cc=0, value=0):
    return {"cc": 0x8180 + cc * 128 + value, "cc_up": 0x8080 + cc, "cc_down": 0x8100 + cc,
            "cc_toggle": 0x8000 + cc, "cc_touch_dial": 0xC961 + cc,
            "bank_lsb": 0xC200 + value, "bank_msb": 0xC180 + value, "bank_up": 0xC301,
            "bank_down": 0xC302, "program": 0xC280 + value, "program_up": 0xC303,
            "program_down": 0xC304}[kind]


def cc_parts(keycode):
    """(kind, cc, value) of a CC QuickBuild's keycode, or None if it is not
    one of the kinds this app can make (a multi-toggle, a lighting preset)."""
    if 0x8000 <= keycode <= 0x807F:
        return "cc_toggle", keycode - 0x8000, 0
    if 0x8080 <= keycode <= 0x80FF:
        return "cc_up", keycode - 0x8080, 0
    if 0x8100 <= keycode <= 0x817F:
        return "cc_down", keycode - 0x8100, 0
    if 0x8180 <= keycode <= 0xC17F:
        return ("cc",) + divmod(keycode - 0x8180, 128)
    if 0xC180 <= keycode <= 0xC1FF:
        return "bank_msb", 0, keycode - 0xC180
    if 0xC200 <= keycode <= 0xC27F:
        return "bank_lsb", 0, keycode - 0xC200
    if 0xC280 <= keycode <= 0xC2FF:
        return "program", 0, keycode - 0xC280
    if keycode in (0xC301, 0xC302, 0xC303, 0xC304):
        return {0xC301: "bank_up", 0xC302: "bank_down", 0xC303: "program_up", 0xC304: "program_down"}[keycode], 0, 0
    if 0xC961 <= keycode <= 0xC9E0:
        return "cc_touch_dial", keycode - 0xC961, 0
    return None


def describe_cc(keycode, channel=0):
    """What a CC QuickBuild sends, in words."""
    parts = cc_parts(keycode)
    if parts is None:
        if 0xEF10 <= keycode <= 0xEF73:
            text = tr("QuickBuild", "CC steps (Toggle {})").format(keycode - 0xEF10 + 1)
        elif keycode == 0:
            return tr("QuickBuild", "CC message (nothing chosen)")
        elif 0xC460 <= keycode <= 0xC4E8:
            text = tr("QuickBuild", "Lighting preset")
            try:        # the preset's own name, from the key picker's label
                from keycodes.keycodes import Keycode
                label = Keycode.find(_keycode_name(keycode)).label.replace("\n", " ").strip()
                if label and label != "None":
                    text = tr("QuickBuild", "Lighting: {}").format(label)
            except Exception:
                pass
        else:
            text = tr("QuickBuild", "CC message")
    else:
        kind, cc, value = parts
        text = {"cc": "CC {cc} value {value}", "cc_up": "CC {cc} up", "cc_down": "CC {cc} down",
                "cc_toggle": "CC {cc} on/off", "cc_touch_dial": "CC {cc} on the touch dial",
                "program": "Program {value}", "program_up": "Next program",
                "program_down": "Previous program", "bank_msb": "Bank MSB {value}",
                "bank_lsb": "Bank LSB {value}", "bank_up": "Bank up", "bank_down": "Bank down"}[kind]
        text = tr("QuickBuild", text).format(cc=cc, value=value)
    return text if channel == 0 else tr("QuickBuild", "{}, channel {}").format(text, channel)


def read_cc_from_image(keyboard):
    """Older firmware: {QuickBuild number: (keycode, channel)} for the CC
    QuickBuilds, read from the settings image ({} if not found)."""
    try:
        info = keyboard.get_clone_info()
        total = 2 + QUICKBUILD_COUNT * 3
        if not info or CC_STORE_ADDRESS + total > info['eeprom_size']:
            return {}
        data = b""
        while len(data) < total:
            chunk = keyboard.clone_read_chunk(CC_STORE_ADDRESS + len(data), min(info['chunk_size'], total - len(data)))
            if chunk is None:
                return {}
            data += chunk
            if len(data) >= 2 and data[:2] != CC_STORE_MARKER:
                return {}
        return {i: (data[2 + i * 3] | (data[3 + i * 3] << 8), data[4 + i * 3]) for i in range(QUICKBUILD_COUNT)}
    except Exception:
        return {}
# SmartChord categories: the keycode of slot 0 (slot n is that + n)
SMARTCHORD_BASE = {11: 0xC38B, 12: 0xC396, 13: 0xC3A2, 14: 0xC3B2, 15: 0xC3C2, 16: 0xC3CE, 17: 0xC3FA}
# Categories whose flags hold a chord inversion (bits 0-3)
HAS_INVERSION = set(SMARTCHORD_BASE) | {3}
# Categories with names the user gave in this app
USER_NAMES = {26: FEATURE_ARP, 27: FEATURE_SEQ, 24: FEATURE_DELAY, 31: FEATURE_TOGGLE, 30: FEATURE_MACRO}
# Which tab here edits what a category plays
CATEGORY_EDITOR = {0: "Arpeggiator", 25: "Arpeggiator", 26: "Arpeggiator",
                   1: "Step Sequencer", 27: "Step Sequencer",
                   2: "Delay", 24: "Delay", 32: "Multi Channel", 33: "KeySplit",
                   18: "DrumLIVE", 22: "Rhythm Engine", 6: "Drum Machine", 5: "AutoFader",
                   3: "SmartChord"}

_keycode_names = None


def _keycode_name(keycode):
    global _keycode_names
    if _keycode_names is None:
        from keycodes.keycodes_v6 import keycodes_v6
        _keycode_names = {value: name for name, value in keycodes_v6.kc.items()}
    return _keycode_names.get(keycode)


def _smartchord_name(category, slot):
    """The chord a SmartChord slot plays, by its keycode ("m9", "Maj7"...)."""
    global _keycode_names
    try:
        from keycodes.keycodes import Keycode
        if _keycode_names is None:
            from keycodes.keycodes_v6 import keycodes_v6
            _keycode_names = {value: name for name, value in keycodes_v6.kc.items()}
        keycode = Keycode.find(_keycode_names.get(SMARTCHORD_BASE[category] + slot))
        return keycode.label.replace("\n", " ") if keycode else None
    except Exception:
        return None


def slot_label(category, slot):
    """What slot `slot` of a category is called."""
    if category in SMARTCHORD_BASE:
        return _smartchord_name(category, slot) or str(slot + 1)
    if category == 25:
        try:
            from keycodes.keycodes import _arp_factory_name
            return " ".join(str(part) for part in _arp_factory_name(slot) if part)
        except Exception:
            return str(slot + 1)
    if category == 20:
        return (tr("QuickBuild", "Loop {} Modifier").format(slot + 1) if slot < 8
                else tr("QuickBuild", "Overdub") if slot == 8 else tr("QuickBuild", "Mute"))
    if category == 28 and slot < len(BASICS):
        return "{} {}".format(BASICS[slot][0], BASICS[slot][1])
    if category == 23 and slot < len(FACTORY_DELAYS):
        return FACTORY_DELAYS[slot]
    if category == 29:
        return tr("QuickBuild", "Thru {}").format(slot + 1)
    if category in USER_NAMES:
        try:
            name = get_feature_name_manager().get_name(USER_NAMES[category], slot)
            if name:
                return name
        except Exception:
            pass
    return str(slot + 1)


def describe(category, slot, detail=None):
    """`detail`: something more the keyboard told us about what is in the slot
    (a drum pattern's name, a DrumLIVE slot's name...), or for a CC QuickBuild
    the words for what it sends."""
    if category == QB_UNSET:
        return tr("QuickBuild", "Not set")
    if category not in CATEGORIES:
        return tr("QuickBuild", "Type {}").format(category)
    name = tr("QuickBuild", CATEGORIES[category][0])
    if category == 21:
        return detail or name
    label = slot_label(category, slot)
    if category in SMARTCHORD_BASE:
        return tr("QuickBuild", "SmartChord: {}").format(label)
    if category in (28, 29, 20, 19):
        return label if not label.isdigit() else "{} {}".format(name, label)
    text = "{}: {}".format(name, label) if not label.isdigit() else "{} {}".format(name, label)
    return "{} ({})".format(text, detail) if detail else text


def read_assignments_from_image(keyboard):
    """Older firmware: [(category, slot, flags)] x 100 read from the settings
    image, or None if they are not where this app expects."""
    info = keyboard.get_clone_info()
    if not info:
        return None
    total = 2 + QUICKBUILD_COUNT * 3
    if QB_STORE_ADDRESS + total > info['eeprom_size']:
        return None
    data = b""
    while len(data) < total:
        length = min(info['chunk_size'], total - len(data))
        chunk = keyboard.clone_read_chunk(QB_STORE_ADDRESS + len(data), length)
        if chunk is None:
            return None
        data += chunk
        if len(data) >= 2 and data[:2] != QB_STORE_MARKER:
            return None
    return [tuple(data[2 + i * 3: 5 + i * 3]) for i in range(QUICKBUILD_COUNT)]


class ChangeDialog(QDialog):
    """Choose what one QuickBuild does."""

    def __init__(self, parent, number, category, slot, flags, cc_keycode_now=0, cc_channel_now=0):
        super().__init__(parent)
        self.setWindowTitle(tr("QuickBuild", "Rebind function: QuickBuild {}").format(number))
        self.setMinimumWidth(380)

        self.kind = ArrowComboBox()
        self.kind.addItem(tr("QuickBuild", "Not set"), QB_UNSET)
        for offered in OFFERED:
            self.kind.addItem(tr("QuickBuild", CATEGORIES[offered][0]), offered)
        if category != QB_UNSET and category not in OFFERED and category in CATEGORIES:
            self.kind.addItem(tr("QuickBuild", CATEGORIES[category][0]), category)
        self.which = ArrowComboBox()
        self.which.setMaxVisibleItems(18)
        self.inversion = ArrowComboBox()
        self.inversion.addItem(tr("QuickBuild", "Root position"), 0)
        for n in range(1, 9):
            self.inversion.addItem(tr("QuickBuild", "Inversion {}").format(n), n)

        form = QFormLayout()
        form.addRow(tr("QuickBuild", "Category:"), self.kind)
        self.which_label = QLabel(tr("QuickBuild", "Function:"))
        form.addRow(self.which_label, self.which)
        self.inversion_label = QLabel(tr("QuickBuild", "Inversion:"))
        form.addRow(self.inversion_label, self.inversion)

        # CC message: what to send
        self._cc_keycode_now = cc_keycode_now
        self.cc_kind = ArrowComboBox()
        now = cc_parts(cc_keycode_now) if category == 21 else ("cc", 0, 0)
        if now is None:
            # made on the keyboard, of a kind this dialog cannot make: can be kept
            self.cc_kind.addItem(tr("QuickBuild", "Keep: {}").format(describe_cc(cc_keycode_now)), "keep")
        for key, label, _, _, _ in CC_KINDS:
            self.cc_kind.addItem(tr("QuickBuild", label), key)
        self.cc_number = QSpinBox()
        self.cc_number.setRange(0, 127)
        self.cc_value = QSpinBox()
        self.cc_value.setRange(0, 127)
        self.cc_channel = ArrowComboBox()
        self.cc_channel.addItem(tr("QuickBuild", "The keyboard's channel"), 0)
        for channel in range(1, 17):
            self.cc_channel.addItem(tr("QuickBuild", "Channel {}").format(channel), channel)
        if now is not None:
            self.cc_kind.setCurrentIndex(max(0, self.cc_kind.findData(now[0])))
            self.cc_number.setValue(now[1])
            self.cc_value.setValue(now[2])
        self.cc_channel.setCurrentIndex(max(0, self.cc_channel.findData(cc_channel_now if category == 21 else 0)))
        self.cc_kind_label = QLabel(tr("QuickBuild", "Sends:"))
        self.cc_number_label = QLabel(tr("QuickBuild", "CC number:"))
        self.cc_value_label = QLabel(tr("QuickBuild", "Value:"))
        self.cc_channel_label = QLabel(tr("QuickBuild", "On:"))
        form.addRow(self.cc_kind_label, self.cc_kind)
        form.addRow(self.cc_number_label, self.cc_number)
        form.addRow(self.cc_value_label, self.cc_value)
        form.addRow(self.cc_channel_label, self.cc_channel)
        self.cc_kind.currentIndexChanged.connect(lambda _: self.show_cc_fields())

        note = QLabel(tr(
            "QuickBuild",
            "This chooses what the key does. Something that has not been made yet (an empty "
            "arpeggio, delay, fader and so on) still needs setting up, on its tab here or on the keyboard."))
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(dark); font-size: 9pt;")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)
        self.setLayout(layout)

        self._flags = flags
        self._category = category       # what the QuickBuild is now (see result_values)
        self._slot = slot
        self.kind.setCurrentIndex(max(0, self.kind.findData(category)))
        self.kind.currentIndexChanged.connect(lambda _: self.on_kind_changed())
        self.fill_slots(slot)
        self.show_inversion()

    def on_kind_changed(self):
        # Another category starts on its first entry in root position; going
        # back to the one the QuickBuild has shows what it has again.
        same = self.kind.currentData() == self._category
        self.fill_slots(self._slot if same else 0)
        self.show_inversion()

    def show_inversion(self):
        same = self.kind.currentData() == self._category
        inversion = self._flags & 0x0F if same and self._category in HAS_INVERSION else 0
        self.inversion.setCurrentIndex(max(0, self.inversion.findData(inversion)))

    def fill_slots(self, select):
        category = self.kind.currentData()
        self.which.clear()
        count = CATEGORIES[category][1] if category in CATEGORIES else 0
        for slot in range(count):
            if category == 28 and not BASICS[slot][2] and slot != select:
                continue        # an old entry the keyboard no longer offers
            label = slot_label(category, slot)
            self.which.addItem(label if not label.isdigit() else
                               "{} {}".format(tr("QuickBuild", CATEGORIES[category][0]), label), slot)
        if count:
            self.which.setCurrentIndex(max(0, self.which.findData(min(select, count - 1))))
        show_slot = count > 1
        self.which.setVisible(show_slot)
        self.which_label.setVisible(show_slot)
        show_inversion = category in HAS_INVERSION
        self.inversion.setVisible(show_inversion)
        self.inversion_label.setVisible(show_inversion)
        self.show_cc_fields()

    def show_cc_fields(self):
        is_cc = self.kind.currentData() == 21
        key = self.cc_kind.currentData()
        kind = next((k for k in CC_KINDS if k[0] == key), None)
        uses_cc = is_cc and kind is not None and kind[2]
        uses_value = is_cc and kind is not None and kind[3]
        for widget, visible in ((self.cc_kind, is_cc), (self.cc_kind_label, is_cc),
                                (self.cc_number, uses_cc), (self.cc_number_label, uses_cc),
                                (self.cc_value, uses_value), (self.cc_value_label, uses_value),
                                (self.cc_channel, is_cc), (self.cc_channel_label, is_cc)):
            widget.setVisible(visible)
        if uses_value:
            self.cc_value_label.setText(tr("QuickBuild", kind[4]) + ":")

    def cc_values(self):
        """(keycode, channel) for a CC message, (0, 0) for anything else."""
        if self.kind.currentData() != 21:
            return 0, 0
        key = self.cc_kind.currentData()
        keycode = self._cc_keycode_now if key == "keep" else \
            cc_keycode(key, self.cc_number.value(), self.cc_value.value())
        return keycode, self.cc_channel.currentData() or 0

    def result_values(self):
        """(category, slot, flags) as chosen."""
        category = self.kind.currentData()
        if category == QB_UNSET:
            return QB_UNSET, 0, 0
        if category == 21:
            return 21, 0, 0
        slot = self.which.currentData() or 0
        # The flags mean something different in each category (a chord's
        # inversion and "ignore voice leading", an arpeggio's mode), so what
        # the QuickBuild had is only kept while its category stays the same.
        # 0 is every category's default.
        kept = self._flags if category == self._category else 0
        if category in HAS_INVERSION:
            flags = (kept & 0x10) | (self.inversion.currentData() or 0)
        elif category == 25:
            flags = kept            # the arpeggio's mode, set on the keyboard
        else:
            flags = 0
        return category, slot, flags


class QuickBuildOverview(QWidget):
    """The list of the 100 QuickBuilds and what each one does."""

    def __init__(self, open_tab):
        super().__init__()
        self.open_tab = open_tab        # called with a tab's name ("Arpeggiator", ...)
        self.keyboard = None
        self.app_config = None
        self.assignments = None
        self.loaded_for = None
        self.can_change = False
        self.cc = {}            # QuickBuild number -> (keycode, channel), for CC messages
        self.details = {}       # QuickBuild number -> more about what is in its slot

        title = QLabel(tr("QuickBuild", "QuickBuild"))
        title.setStyleSheet("font-weight: bold; font-size: 14pt;")
        title.setAlignment(Qt.AlignCenter)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignCenter)
        self.description.setStyleSheet("color: palette(dark); font-size: 9pt;")

        self.only_set = QCheckBox(tr("QuickBuild", "Show only the ones that are set"))
        self.only_set.stateChanged.connect(self.fill)
        self.refresh_button = QPushButton(tr("QuickBuild", "Read from keyboard"))
        self.refresh_button.clicked.connect(self.reload)
        self.status = QLabel()
        self.status.setStyleSheet("color: palette(dark); font-size: 9pt;")
        tools = QHBoxLayout()
        tools.addWidget(self.only_set)
        tools.addStretch(1)
        tools.addWidget(self.status)
        tools.addWidget(self.refresh_button)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("QuickBuild", "QuickBuild"), tr("QuickBuild", "Function"), tr("QuickBuild", "Edit")])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 190)
        self.table.cellClicked.connect(self.on_cell_clicked)
        self.table.viewport().setCursor(Qt.PointingHandCursor)

        column = QVBoxLayout()
        column.addWidget(title)
        column.addWidget(self.description)
        column.addSpacing(8)
        column.addLayout(tools)
        column.addWidget(self.table, 1)
        holder = QWidget()
        holder.setLayout(column)
        holder.setMaximumWidth(900)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(holder, 5)
        row.addStretch(1)
        self.setLayout(row)
        self.set_description()

    # buttons that sit in a table row: the theme's usual padding is too tall for one
    def link_item(self, text):
        """A table cell that reads as something to click (see on_cell_clicked)."""
        item = QTableWidgetItem(text)
        font = item.font()
        font.setUnderline(True)
        font.setBold(True)
        item.setFont(font)
        item.setForeground(self.palette().highlight().color())
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def on_cell_clicked(self, row, column):
        item = self.table.item(row, 0)
        if item is None:
            return
        qb = item.data(Qt.UserRole)
        if column == 1 and self.can_change:
            self.change(qb)         # the function itself, or its Rebind link
        elif column == 2:
            target = CATEGORY_EDITOR.get(self.assignments[qb][0])
            if target:
                self.open_tab(target)

    def set_description(self):
        text = tr("QuickBuild",
                  "A QuickBuild is a key that starts an arpeggio, a sequence, a delay, a chord, a loop "
                  "and more. This list shows each one's function. ")
        if self.can_change:
            text += tr("QuickBuild", "Click a function to rebind that QuickBuild to something else. ")
        else:
            text += tr("QuickBuild",
                       "To set or change one, press its key on the keyboard (hold a key that is already "
                       "set for its menu); newer firmware lets you change them here. ")
        text += tr("QuickBuild", "The other tabs edit what the QuickBuilds play.")
        self.description.setText(text)

    def set_keyboard(self, keyboard, app_config):
        self.keyboard = keyboard
        self.app_config = app_config
        self.assignments = None
        self.loaded_for = None
        self.can_change = False
        self.fill()

    def load_if_needed(self):
        """Called when the page comes into view: read once per keyboard."""
        if self.keyboard is not None and self.loaded_for is not self.keyboard:
            self.reload()

    def reload(self):
        self.assignments = None
        self.can_change = False
        if self.keyboard is not None:
            try:
                if self.app_config is not None and self.app_config.supported():
                    self.assignments = self.app_config.qb_get_all()
                    self.can_change = self.assignments is not None
                if self.assignments is None:
                    self.assignments = read_assignments_from_image(self.keyboard)
            except Exception:
                self.assignments = None
            self.loaded_for = self.keyboard
            self.cc = {}
            self.details = {}
            if self.assignments is not None:
                if not self.can_change and any(c == 21 for c, _, _ in self.assignments):
                    self.cc = read_cc_from_image(self.keyboard)
                for qb in range(QUICKBUILD_COUNT):
                    self.load_detail(qb)
        self.set_description()
        self.fill()

    def load_detail(self, qb):
        """Ask the keyboard what is in the slot a QuickBuild points at, where
        that gives a better name than a number. Only for QuickBuilds that are
        set, and only with firmware that answers (a few requests in all)."""
        self.details.pop(qb, None)
        category, slot, _ = self.assignments[qb]
        config = self.app_config
        if category == QB_UNSET or config is None or not self.can_change:
            return
        try:
            detail = None
            if category == 21:
                reply = config.qb_get(qb)
                if reply is not None:
                    self.cc[qb] = (reply["cc_keycode"], reply["cc_channel"])
            elif category == 6:
                slot_config = config.dm_get(slot)
                if slot_config is not None and slot_config["pattern"] != 0xFFFF:
                    detail = config.dm_pattern_name(slot_config["pattern"])
                elif slot_config is not None:
                    detail = tr("QuickBuild", "empty")
            elif category == 18:
                reply = config.dl_slot_get(slot)
                if reply is not None:
                    detail = reply["name"] or (None if reply["configured"] else tr("QuickBuild", "empty"))
            elif category == 22:
                reply = config.re_get(slot)
                if reply is not None:
                    progression = config.re_progression(reply["progression"])
                    instrument = RHYTHM_INSTRUMENTS[reply["instrument"]] if reply["instrument"] < 4 else ""
                    detail = ", ".join(part for part in (progression["name"] if progression else "", instrument) if part)
            elif category == 5:
                reply = config.fd_get(slot)
                if reply is not None:
                    detail = tr("QuickBuild", "CC {}").format(reply["cc"]) if reply["flags"] & 1 else tr("QuickBuild", "empty")
            elif category == 3:
                reply = config.sc_get(slot)
                if reply is not None:
                    detail = " ".join("{:+d}".format(i) for i in reply["intervals"]) or tr("QuickBuild", "empty")
            if detail:
                self.details[qb] = detail
        except Exception:
            pass

    def describe_row(self, qb):
        category, slot, _ = self.assignments[qb]
        if category == 21:
            keycode, channel = self.cc.get(qb, (None, 0))
            return describe(category, slot, describe_cc(keycode, channel) if keycode is not None else None)
        return describe(category, slot, self.details.get(qb))

    def fill(self):
        self.table.setRowCount(0)
        if self.assignments is None:
            self.status.setText(tr(
                "QuickBuild", "This keyboard's firmware does not let the app read its QuickBuilds.")
                if self.loaded_for is not None else "")
            return

        set_count = sum(1 for category, _, _ in self.assignments if category != QB_UNSET)
        self.status.setText(tr("QuickBuild", "{} of {} set").format(set_count, QUICKBUILD_COUNT))
        for number, (category, slot, _) in enumerate(self.assignments, start=1):
            if self.only_set.isChecked() and category == QB_UNSET:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            name = QTableWidgetItem(tr("QuickBuild", "QuickBuild {}").format(number))
            name.setData(Qt.UserRole, number - 1)
            self.table.setItem(row, 0, name)
            item = QTableWidgetItem(self.describe_row(number - 1))
            if category == QB_UNSET:
                item.setForeground(Qt.gray)
            self.table.setItem(row, 1, item)
            target = CATEGORY_EDITOR.get(category)
            if target:
                self.table.setItem(row, 2, self.link_item(
                    tr("QuickBuild", "Open {}").format(tr("QuickBuild", target))))
            if self.can_change:
                item.setToolTip(tr("QuickBuild", "Click to choose a different function"))

    def change(self, qb):
        category, slot, flags = self.assignments[qb]
        dialog = ChangeDialog(self, qb + 1, category, slot, flags, *self.cc.get(qb, (0, 0)))
        if dialog.exec_() != QDialog.Accepted:
            return
        self.apply_change(qb, *dialog.result_values(), *dialog.cc_values())

    def apply_change(self, qb, category, slot, flags, cc_keycode=0, cc_channel=0):
        """Send one QuickBuild's new assignment; returns whether the keyboard took it."""
        current = self.app_config.qb_get(qb) if self.app_config is not None else None
        if current is None:
            self.status.setText(tr("QuickBuild", "The keyboard did not answer."))
            return False
        # An arpeggio's rate and gate (set on the keyboard) stay with it while
        # the QuickBuild stays a factory arpeggio. One that is only now made an
        # arpeggio starts on the pattern's own rate and gate (0), not on what
        # an earlier arpeggio on this QuickBuild left behind.
        keep_arp = category == 25 and current["category"] == 25
        reply = self.app_config.qb_set(
            qb, category, slot, flags, cc_keycode=cc_keycode, cc_channel=cc_channel,
            arp_rate=current["arp_rate"] if keep_arp else 0,
            arp_gate=current["arp_gate"] if keep_arp else 0)
        if reply is None:
            self.status.setText(tr(
                "QuickBuild", "The keyboard refused that change (close any menu open on the keyboard and try again)."))
            return False
        self.assignments[qb] = (reply["category"], reply["slot"], reply["flags"])
        self.cc.pop(qb, None)
        self.load_detail(qb)
        scroll = self.table.verticalScrollBar().value()
        self.fill()
        self.table.verticalScrollBar().setValue(scroll)
        return True


class QuickBuildTab(GroupedEditor):
    """QuickBuild overview first, then the editors passed to add_editor() /
    add_page() as tabs beside it. A page with set_app_config() / shown() is
    given the keyboard's AppConfig and told when it comes into view."""

    def __init__(self):
        super().__init__("QuickBuild")
        self.keyboard = None
        self.app_config = None
        self.overview = QuickBuildOverview(self.open_tab)
        self.add_page(self.overview, "QuickBuild")

    def valid(self):
        return isinstance(self.device, VialKeyboard)

    def rebuild(self, device):
        super().rebuild(device)
        self.keyboard = device.keyboard if self.valid() else None
        self.app_config = AppConfig(self.keyboard) if self.keyboard is not None else None
        self.overview.set_keyboard(self.keyboard, self.app_config)
        for page, _, editor in self.entries:
            if editor is None and hasattr(page, "set_app_config"):
                page.set_app_config(self.app_config)
        if self.is_active:
            self.page_shown(self.tabs.currentWidget())

    def page_shown(self, page):
        if page is self.overview:
            self.overview.load_if_needed()
        elif hasattr(page, "shown"):
            page.shown()
