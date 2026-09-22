# SPDX-License-Identifier: GPL-2.0-or-later
import struct

from keycodes.keycodes import Keycode
from protocol.constants import VIAL_PROTOCOL_ADVANCED_MACROS

SS_QMK_PREFIX = 1

SS_TAP_CODE = 1
SS_DOWN_CODE = 2
SS_UP_CODE = 3
SS_DELAY_CODE = 4
VIAL_MACRO_EXT_TAP = 5
VIAL_MACRO_EXT_DOWN = 6
VIAL_MACRO_EXT_UP = 7
SS_BPM_DELAY_CODE = 8
SS_BPM_DELAY_REPEAT_CODE = 9
SS_MIXING_CONTROL_CODE = 10

# Mixing control special value for "Current" CC
MIXING_CURRENT_VALUE = 128


class BasicAction:

    tag = "unknown"

    def save(self):
        return [self.tag]

    def restore(self, act):
        if self.tag != act[0]:
            raise RuntimeError("cannot restore {}: expected tag={} got tag={}".format(
                self, self.tag, act[0]
            ))

    def __eq__(self, other):
        return self.tag == other.tag


class ActionText(BasicAction):

    tag = "text"

    def __init__(self, text=""):
        super().__init__()
        self.text = text
        # Keyboard layout the text is typed for (UI only, never stored).
        self.layout = "English (US)"

    def serialize(self, vial_protocol):
        return self.text.encode("utf-8")

    def save(self):
        return super().save() + [self.text]

    def restore(self, act):
        super().restore(act)
        self.text = act[1]

    def __eq__(self, other):
        return super().__eq__(other) and self.text == other.text

    def __repr__(self):
        return "{}<{}>".format(self.tag, self.text)


class ActionSequence(BasicAction):

    tag = "unknown-sequence"

    def __init__(self, sequence=None):
        super().__init__()
        if sequence is None:
            sequence = []
        self.sequence = sequence

    def serialize_prefix(self, kc):
        raise NotImplementedError

    def serialize(self, vial_protocol):
        out = b""
        for kc in self.sequence:
            if vial_protocol >= VIAL_PROTOCOL_ADVANCED_MACROS:
                out += struct.pack("B", SS_QMK_PREFIX)
            kc = Keycode.deserialize(kc)
            out += self.serialize_prefix(kc)
            if kc < 256:
                out += struct.pack("B", kc)
            else:
                # see decode_keycode() in qmk
                if kc % 256 == 0:
                    kc = 0xFF00 | (kc >> 8)
                out += struct.pack("<H", kc)
        return out

    def save(self):
        out = super().save()
        for kc in self.sequence:
            out.append(kc)
        return out

    def restore(self, act):
        super().restore(act)
        for kc in act[1:]:
            self.sequence.append(kc)

    def __eq__(self, other):
        return super().__eq__(other) and self.sequence == other.sequence

    def __repr__(self):
        return "{}<{}>".format(self.tag, self.sequence)


class ActionDown(ActionSequence):

    tag = "down"

    def serialize_prefix(self, kc):
        if kc >= 256:
            return b"\x06"
        return b"\x02"


class ActionUp(ActionSequence):

    tag = "up"

    def serialize_prefix(self, kc):
        if kc >= 256:
            return b"\x07"
        return b"\x03"


class ActionTap(ActionSequence):

    tag = "tap"

    def serialize_prefix(self, kc):
        if kc >= 256:
            return b"\x05"
        return b"\x01"


# Typed text -> key actions. Macros never store raw text: a typed string is
# turned into ordinary Keypress / Hold / Release lines, so it plays back
# through the same key path as any hand-built macro. The keys depend on the
# keyboard layout the computer is set to, so each language has its own table.
# Table value = (qmk_id, mods): "" plain, "S" Shift, "A" AltGr (Right Alt),
# "SA" Shift+AltGr. Dead keys (accents that wait for the next key) are left
# out - they cannot be typed as a single character.
TEXT_SHIFT_KEY = "KC_LSHIFT"
TEXT_ALTGR_KEY = "KC_RALT"

_ROW_NUM = ["KC_1", "KC_2", "KC_3", "KC_4", "KC_5", "KC_6", "KC_7", "KC_8", "KC_9", "KC_0"]


def _letters(table, swaps=None):
    swaps = swaps or {}
    for c in "abcdefghijklmnopqrstuvwxyz":
        kc = swaps.get(c, "KC_" + c.upper())
        table.setdefault(c, (kc, ""))
        table.setdefault(c.upper(), (kc, "S"))


def _pairs(table, pairs, mods):
    for ch, kc in pairs:
        table.setdefault(ch, (kc, mods))


def _common(table):
    _pairs(table, [(" ", "KC_SPACE"), ("\n", "KC_ENTER"), ("\t", "KC_TAB")], "")


def _us():
    t = {}
    _common(t)
    _letters(t)
    _pairs(t, zip("1234567890", _ROW_NUM), "")
    _pairs(t, zip("!@#$%^&*()", _ROW_NUM), "S")
    _pairs(t, [("-", "KC_MINUS"), ("=", "KC_EQUAL"), ("[", "KC_LBRACKET"), ("]", "KC_RBRACKET"),
               ("\\", "KC_BSLASH"), (";", "KC_SCOLON"), ("'", "KC_QUOTE"), ("`", "KC_GRAVE"),
               (",", "KC_COMMA"), (".", "KC_DOT"), ("/", "KC_SLASH")], "")
    _pairs(t, [("_", "KC_MINUS"), ("+", "KC_EQUAL"), ("{", "KC_LBRACKET"), ("}", "KC_RBRACKET"),
               ("|", "KC_BSLASH"), (":", "KC_SCOLON"), ('"', "KC_QUOTE"), ("~", "KC_GRAVE"),
               ("<", "KC_COMMA"), (">", "KC_DOT"), ("?", "KC_SLASH")], "S")
    return t


def _german():
    t = {}
    _common(t)
    _letters(t, {"y": "KC_Z", "z": "KC_Y"})
    _pairs(t, zip("1234567890", _ROW_NUM), "")
    _pairs(t, zip('!"§$%&/()=', _ROW_NUM), "S")
    _pairs(t, [("²", "KC_2"), ("³", "KC_3"), ("{", "KC_7"), ("[", "KC_8"), ("]", "KC_9"),
               ("}", "KC_0"), ("\\", "KC_MINUS"), ("~", "KC_RBRACKET"), ("|", "KC_NONUS_BSLASH"),
               ("@", "KC_Q"), ("€", "KC_E"), ("µ", "KC_M")], "A")
    _pairs(t, [("ß", "KC_MINUS"), ("ü", "KC_LBRACKET"), ("+", "KC_RBRACKET"), ("ö", "KC_SCOLON"),
               ("ä", "KC_QUOTE"), ("#", "KC_NONUS_HASH"), (",", "KC_COMMA"), (".", "KC_DOT"),
               ("-", "KC_SLASH"), ("<", "KC_NONUS_BSLASH")], "")
    _pairs(t, [("?", "KC_MINUS"), ("Ü", "KC_LBRACKET"), ("*", "KC_RBRACKET"), ("Ö", "KC_SCOLON"),
               ("Ä", "KC_QUOTE"), ("'", "KC_NONUS_HASH"), (";", "KC_COMMA"), (":", "KC_DOT"),
               ("_", "KC_SLASH"), (">", "KC_NONUS_BSLASH"), ("°", "KC_GRAVE")], "S")
    return t


def _french():
    t = {}
    _common(t)
    _letters(t, {"a": "KC_Q", "q": "KC_A", "z": "KC_W", "w": "KC_Z", "m": "KC_SCOLON"})
    _pairs(t, zip("1234567890", _ROW_NUM), "S")
    _pairs(t, zip('&é"\'(-è_çà', _ROW_NUM), "")
    _pairs(t, [("#", "KC_3"), ("{", "KC_4"), ("[", "KC_5"), ("|", "KC_6"), ("\\", "KC_8"),
               ("^", "KC_9"), ("@", "KC_0"), ("]", "KC_MINUS"), ("}", "KC_EQUAL"),
               ("¤", "KC_RBRACKET"), ("€", "KC_E")], "A")
    _pairs(t, [(")", "KC_MINUS"), ("=", "KC_EQUAL"), ("$", "KC_RBRACKET"), ("ù", "KC_QUOTE"),
               ("*", "KC_NONUS_HASH"), (",", "KC_M"), (";", "KC_COMMA"), (":", "KC_DOT"),
               ("!", "KC_SLASH"), ("<", "KC_NONUS_BSLASH"), ("²", "KC_GRAVE")], "")
    _pairs(t, [("°", "KC_MINUS"), ("+", "KC_EQUAL"), ("£", "KC_RBRACKET"), ("%", "KC_QUOTE"),
               ("µ", "KC_NONUS_HASH"), ("?", "KC_M"), (".", "KC_COMMA"), ("/", "KC_DOT"),
               ("§", "KC_SLASH"), (">", "KC_NONUS_BSLASH")], "S")
    return t


def _spanish():
    t = {}
    _common(t)
    _letters(t)
    _pairs(t, zip("1234567890", _ROW_NUM), "")
    _pairs(t, zip('!"·$%&/()=', _ROW_NUM), "S")
    _pairs(t, [("|", "KC_1"), ("@", "KC_2"), ("#", "KC_3"), ("~", "KC_4"), ("€", "KC_5"),
               ("¬", "KC_6"), ("[", "KC_LBRACKET"), ("]", "KC_RBRACKET"), ("{", "KC_QUOTE"),
               ("}", "KC_NONUS_HASH"), ("\\", "KC_GRAVE")], "A")
    _pairs(t, [("'", "KC_MINUS"), ("¡", "KC_EQUAL"), ("+", "KC_RBRACKET"), ("ñ", "KC_SCOLON"),
               ("ç", "KC_NONUS_HASH"), ("º", "KC_GRAVE"), (",", "KC_COMMA"), (".", "KC_DOT"),
               ("-", "KC_SLASH"), ("<", "KC_NONUS_BSLASH")], "")
    _pairs(t, [("?", "KC_MINUS"), ("¿", "KC_EQUAL"), ("*", "KC_RBRACKET"), ("Ñ", "KC_SCOLON"),
               ("Ç", "KC_NONUS_HASH"), ("ª", "KC_GRAVE"), (";", "KC_COMMA"), (":", "KC_DOT"),
               ("_", "KC_SLASH"), (">", "KC_NONUS_BSLASH")], "S")
    return t


def _russian():
    t = {}
    _common(t)
    rows = [
        ("йцукенгшщзхъ", ["KC_Q", "KC_W", "KC_E", "KC_R", "KC_T", "KC_Y", "KC_U", "KC_I", "KC_O",
                          "KC_P", "KC_LBRACKET", "KC_RBRACKET"]),
        ("фывапролджэ", ["KC_A", "KC_S", "KC_D", "KC_F", "KC_G", "KC_H", "KC_J", "KC_K", "KC_L",
                         "KC_SCOLON", "KC_QUOTE"]),
        ("ячсмитьбю", ["KC_Z", "KC_X", "KC_C", "KC_V", "KC_B", "KC_N", "KC_M", "KC_COMMA", "KC_DOT"]),
        ("ё", ["KC_GRAVE"]),
    ]
    for chars, kcs in rows:
        for ch, kc in zip(chars, kcs):
            t.setdefault(ch, (kc, ""))
            t.setdefault(ch.upper(), (kc, "S"))
    _pairs(t, zip("1234567890", _ROW_NUM), "")
    _pairs(t, zip('!"№;%:?*()', _ROW_NUM), "S")
    _pairs(t, [("-", "KC_MINUS"), ("=", "KC_EQUAL"), ("\\", "KC_BSLASH"), (".", "KC_SLASH")], "")
    _pairs(t, [("_", "KC_MINUS"), ("+", "KC_EQUAL"), ("/", "KC_BSLASH"), (",", "KC_SLASH")], "S")
    return t


def _japanese():
    t = {}
    _common(t)
    _letters(t)
    _pairs(t, zip("1234567890", _ROW_NUM), "")
    _pairs(t, zip("!\"#$%&'()", _ROW_NUM[:9]), "S")
    _pairs(t, [("-", "KC_MINUS"), ("^", "KC_EQUAL"), ("¥", "KC_JYEN"), ("@", "KC_LBRACKET"),
               ("[", "KC_RBRACKET"), (";", "KC_SCOLON"), (":", "KC_QUOTE"), ("]", "KC_NONUS_HASH"),
               (",", "KC_COMMA"), (".", "KC_DOT"), ("/", "KC_SLASH"), ("\\", "KC_RO")], "")
    _pairs(t, [("=", "KC_MINUS"), ("~", "KC_EQUAL"), ("|", "KC_JYEN"), ("`", "KC_LBRACKET"),
               ("{", "KC_RBRACKET"), ("+", "KC_SCOLON"), ("*", "KC_QUOTE"), ("}", "KC_NONUS_HASH"),
               ("<", "KC_COMMA"), (">", "KC_DOT"), ("?", "KC_SLASH"), ("_", "KC_RO")], "S")
    return t


TEXT_LAYOUT_DEFAULT = "English (US)"
TEXT_LAYOUTS = {
    "English (US)": _us(),
    "German": _german(),
    "French": _french(),
    "Spanish": _spanish(),
    "Russian": _russian(),
    "Japanese": _japanese(),
}


def char_to_key(ch, layout=TEXT_LAYOUT_DEFAULT):
    """(qmk_id, mods) for one character on ``layout``, or None."""
    return TEXT_LAYOUTS.get(layout, TEXT_LAYOUTS[TEXT_LAYOUT_DEFAULT]).get(ch)


def text_to_actions(text, layout=TEXT_LAYOUT_DEFAULT):
    """Turn typed text into key actions for the computer's ``layout``: one
    Keypress line per run of characters needing the same modifiers, with Hold
    / Release lines for Shift and AltGr around the runs that need them
    ("happy" -> Keypress H, A, P, P, Y). Returns (actions, skipped_chars);
    characters the layout cannot type are skipped."""
    actions = []
    skipped = []
    run, run_mods = [], None

    def flush():
        if not run:
            return
        mods = [kc for flag, kc in (("S", TEXT_SHIFT_KEY), ("A", TEXT_ALTGR_KEY)) if flag in run_mods]
        if mods:
            actions.append(ActionDown(list(mods)))
        actions.append(ActionTap(list(run)))
        if mods:
            actions.append(ActionUp(list(reversed(mods))))

    for ch in text:
        key = char_to_key(ch, layout)
        if key is None:
            skipped.append(ch)
            continue
        kc, mods = key
        if run and mods != run_mods:
            flush()
            run = []
        run_mods = mods
        run.append(kc)
    flush()
    return actions, skipped


def expand_text_actions(actions):
    """Replace every ActionText in ``actions`` with its key actions."""
    out = []
    for act in actions:
        if isinstance(act, ActionText):
            out.extend(text_to_actions(act.text, getattr(act, "layout", TEXT_LAYOUT_DEFAULT))[0])
        else:
            out.append(act)
    return out


class ActionDelay(BasicAction):

    tag = "delay"

    def __init__(self, delay=0):
        super().__init__()
        self.delay = delay

    def serialize(self, vial_protocol):
        if vial_protocol < VIAL_PROTOCOL_ADVANCED_MACROS:
            raise RuntimeError("ActionDelay can only be used with vial_protocol>=2")
        delay = self.delay
        return struct.pack("BBBB", SS_QMK_PREFIX, SS_DELAY_CODE, (delay % 255) + 1, (delay // 255) + 1)

    def save(self):
        return super().save() + [self.delay]

    def restore(self, act):
        super().restore(act)
        self.delay = act[1]

    def __eq__(self, other):
        return super().__eq__(other) and self.delay == other.delay


# Note value indices (internal, not display order)
# 0=1/1, 1=1/2, 2=1/4, 3=1/8, 4=1/16, 5=2/1, 6=4/1, 7=8/1, 8=16/1
BPM_NOTE_VALUES = [4, 2, 1]  # Legacy: beat multipliers for indices 0-2

# Timing mode is always straight (hidden from user)
BPM_TIMING_STRAIGHT = 0


class ActionBPMDelay(BasicAction):

    tag = "bpm_delay"

    def __init__(self, note_value=2, timing_mode=0):
        super().__init__()
        self.note_value = note_value      # 0=1/1, 1=1/2, 2=1/4, 3=1/8, 4=1/16, 5=2/1, 6=4/1, 7=8/1, 8=16/1
        self.timing_mode = timing_mode    # Always 0 (straight)
        # Repeat count carried invisibly: the on-device macro configurator
        # authors the 5-byte SS_BPM_DELAY_REPEAT opcode (Wait 1/4 x8). The GUI
        # has no repeat editor, but it must ROUND-TRIP the opcode — the old
        # "convert to plain BPM delay" downgrade silently rewrote a x8 wait to
        # x1 on every GUI save of a device-authored macro.
        self.repeat = 1

    def serialize(self, vial_protocol):
        if vial_protocol < VIAL_PROTOCOL_ADVANCED_MACROS:
            raise RuntimeError("ActionBPMDelay can only be used with vial_protocol>=2")
        if getattr(self, 'repeat', 1) > 1:
            return struct.pack("BBBBB", SS_QMK_PREFIX, SS_BPM_DELAY_REPEAT_CODE,
                               self.note_value + 1, self.timing_mode + 1, self.repeat + 1)
        return struct.pack("BBBB", SS_QMK_PREFIX, SS_BPM_DELAY_CODE,
                           self.note_value + 1, self.timing_mode + 1)

    def save(self):
        out = super().save() + [self.note_value, self.timing_mode]
        if getattr(self, 'repeat', 1) > 1:
            out.append(self.repeat)
        return out

    def restore(self, act):
        # Accept both "bpm_delay" and "bpm_delay_repeat" tags for backward compat
        if act[0] not in ("bpm_delay", "bpm_delay_repeat"):
            raise RuntimeError("cannot restore {}: expected tag=bpm_delay got tag={}".format(self, act[0]))
        self.note_value = act[1]
        self.timing_mode = act[2] if len(act) > 2 else 0
        self.repeat = act[3] if len(act) > 3 else 1

    def __eq__(self, other):
        return (isinstance(other, ActionBPMDelay) and self.note_value == other.note_value
                and self.timing_mode == other.timing_mode
                and getattr(self, 'repeat', 1) == getattr(other, 'repeat', 1))


class ActionBPMDelayRepeat(BasicAction):

    tag = "bpm_delay_repeat"

    def __init__(self, note_value=2, timing_mode=0, repeat=1):
        super().__init__()
        self.note_value = note_value      # 0=1/1, 1=1/2, 2=1/4, 3=1/8, 4=1/16
        self.timing_mode = timing_mode    # 0=straight, 1=triplet, 2=dotted
        self.repeat = repeat              # 1-255

    def serialize(self, vial_protocol):
        if vial_protocol < VIAL_PROTOCOL_ADVANCED_MACROS:
            raise RuntimeError("ActionBPMDelayRepeat can only be used with vial_protocol>=2")
        return struct.pack("BBBBB", SS_QMK_PREFIX, SS_BPM_DELAY_REPEAT_CODE,
                           self.note_value + 1, self.timing_mode + 1, self.repeat + 1)

    def save(self):
        return super().save() + [self.note_value, self.timing_mode, self.repeat]

    def restore(self, act):
        super().restore(act)
        self.note_value = act[1]
        self.timing_mode = act[2]
        self.repeat = act[3]

    def __eq__(self, other):
        return (super().__eq__(other) and self.note_value == other.note_value
                and self.timing_mode == other.timing_mode and self.repeat == other.repeat)


class ActionMixingControl(BasicAction):

    tag = "mixing_control"

    def __init__(self, cc_num=0, channel=0, start_val=0, end_val=127,
                 duration_type=1, duration=0):
        super().__init__()
        self.cc_num = cc_num              # 0-127
        self.channel = channel            # 0=zone channel, 1-16=explicit
        self.start_val = start_val        # 0-127=fixed, 128=Current
        self.end_val = end_val            # 0-127=fixed
        self.duration_type = duration_type  # 0=ms, 1=BPM
        self.duration = duration          # ms value or packed BPM params

    def serialize(self, vial_protocol):
        if vial_protocol < VIAL_PROTOCOL_ADVANCED_MACROS:
            raise RuntimeError("ActionMixingControl can only be used with vial_protocol>=2")
        if self.duration_type == 0:
            # ms duration
            d0 = (self.duration % 255) + 1
            d1 = (self.duration // 255) + 1
        else:
            # BPM duration: duration stores (note_value, timing_mode) packed
            note_val = (self.duration >> 8) & 0xFF
            timing = self.duration & 0xFF
            d0 = note_val + 1
            d1 = timing + 1
        return struct.pack("BBBBBBBBB", SS_QMK_PREFIX, SS_MIXING_CONTROL_CODE,
                           self.cc_num + 1, self.channel + 1,
                           self.start_val + 1, self.end_val + 1,
                           self.duration_type + 1, d0, d1)

    def save(self):
        return super().save() + [self.cc_num, self.channel, self.start_val,
                                  self.end_val, self.duration_type, self.duration]

    def restore(self, act):
        super().restore(act)
        self.cc_num = act[1]
        self.channel = act[2]
        self.start_val = act[3]
        self.end_val = act[4]
        self.duration_type = act[5]
        self.duration = act[6]

    def __eq__(self, other):
        return (super().__eq__(other) and self.cc_num == other.cc_num
                and self.channel == other.channel and self.start_val == other.start_val
                and self.end_val == other.end_val and self.duration_type == other.duration_type
                and self.duration == other.duration)


# ---------------------------------------------------------------------------
# Mouse Move (absolute pointer position via the keyboard's HID digitizer)
# ---------------------------------------------------------------------------
SS_MOUSE_MOVE_CODE = 11

# Coordinates are stored as 0..MOUSE_COORD_MAX over the WHOLE host desktop
# (the digitizer's logical range), so a macro is resolution independent: the
# GUI converts to/from pixels of the desktop it is running on.
MOUSE_COORD_MAX = 32767

MOUSE_CLICK_NONE = 0
MOUSE_CLICK_LEFT = 1
MOUSE_CLICK_DOUBLE = 2
MOUSE_CLICK_RIGHT = 3
MOUSE_CLICK_NAMES = {
    MOUSE_CLICK_NONE: "Mouse Move",
    MOUSE_CLICK_LEFT: "Mouse Move + Click",
    MOUSE_CLICK_DOUBLE: "Mouse Move + Double Click",
    MOUSE_CLICK_RIGHT: "Mouse Move + Right Click",
}


def _mouse_coord_bytes(v):
    """0..32767 -> three +1-encoded 7-bit groups (no byte may be 0 in a macro)."""
    v = max(0, min(MOUSE_COORD_MAX, int(v)))
    return [(v & 0x7F) + 1, ((v >> 7) & 0x7F) + 1, ((v >> 14) & 0x01) + 1]


def mouse_coord_from_bytes(b0, b1, b2):
    return ((b0 - 1) | ((b1 - 1) << 7) | ((b2 - 1) << 14)) & MOUSE_COORD_MAX


class ActionMouseMove(BasicAction):
    """Move the host pointer to an absolute desktop position, optionally
    clicking there. x / y are 0..MOUSE_COORD_MAX; click is MOUSE_CLICK_*."""

    tag = "mouse_move"

    def __init__(self, x=0, y=0, click=MOUSE_CLICK_NONE):
        super().__init__()
        self.x = x
        self.y = y
        self.click = click

    def serialize(self, vial_protocol):
        if vial_protocol < VIAL_PROTOCOL_ADVANCED_MACROS:
            raise RuntimeError("ActionMouseMove can only be used with vial_protocol>=2")
        payload = _mouse_coord_bytes(self.x) + _mouse_coord_bytes(self.y) + [int(self.click) + 1]
        return struct.pack("BB", SS_QMK_PREFIX, SS_MOUSE_MOVE_CODE) + bytes(payload)

    def save(self):
        return super().save() + [self.x, self.y, self.click]

    def restore(self, act):
        super().restore(act)
        self.x = act[1]
        self.y = act[2]
        self.click = act[3] if len(act) > 3 else MOUSE_CLICK_NONE

    def __eq__(self, other):
        return (super().__eq__(other) and self.x == other.x and self.y == other.y
                and self.click == other.click)

    def __repr__(self):
        return "{}<{},{} click={}>".format(self.tag, self.x, self.y, self.click)
