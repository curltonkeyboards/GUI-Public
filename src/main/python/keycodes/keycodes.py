# coding: utf-8

# SPDX-License-Identifier: GPL-2.0-or-later

import sys

from keycodes.keycodes_v5 import keycodes_v5
from keycodes.keycodes_v6 import keycodes_v6

# Cached AnyKeycode instance used by Keycode.deserialize()/is_basic().
# Constructing one walks every keycode to build its name tables, so creating
# a fresh instance per deserialize() call is prohibitively slow. The name
# tables depend on the current keyboard's keycodes and protocol, so the cache
# is invalidated whenever the keycode tables are regenerated (see
# recreate_keycodes / recreate_keyboard_keycodes).
_any_keycode_cache = None


def _invalidate_any_keycode_cache():
    global _any_keycode_cache
    _any_keycode_cache = None


class Keycode:

    masked_keycodes = set()
    recorder_alias_to_keycode = dict()
    qmk_id_to_keycode = dict()
    protocol = 0

    def __init__(self, qmk_id, label, tooltip=None, masked=False, printable=None, recorder_alias=None, alias=None):
        self.qmk_id = qmk_id
        self.qmk_id_to_keycode[qmk_id] = self
        self.label = label
        # we cannot embed full CJK fonts due to large size, workaround like this for now
        if sys.platform == "emscripten" and not label.isascii() and qmk_id != "KC_TRNS":
            self.label = qmk_id.replace("KC_", "")

        self.tooltip = tooltip
        # whether this keycode requires another sub-keycode
        self.masked = masked

        # if this is printable keycode, what character does it normally output (i.e. non-shifted state)
        self.printable = printable

        self.alias = [self.qmk_id]
        if alias:
            self.alias += alias

        if recorder_alias:
            for alias in recorder_alias:
                if alias in self.recorder_alias_to_keycode:
                    raise RuntimeError("Misconfigured: two keycodes claim the same alias {}".format(alias))
                self.recorder_alias_to_keycode[alias] = self

        if masked:
            assert qmk_id.endswith("(kc)")
            self.masked_keycodes.add(qmk_id.replace("(kc)", ""))

    @classmethod
    def find(cls, qmk_id):
        # this is to handle cases of qmk_id LCTL(kc) propagated here from find_inner_keycode
        if qmk_id == "kc":
            qmk_id = "KC_NO"
        return KEYCODES_MAP.get(qmk_id)

    @classmethod
    def find_outer_keycode(cls, qmk_id):
        """
        Finds outer keycode, i.e. if it is masked like 0x5Fxx, just return the 0x5F00 portion
        """
        if cls.is_mask(qmk_id):
            qmk_id = qmk_id[:qmk_id.find("(")]
        return cls.find(qmk_id)

    @classmethod
    def find_inner_keycode(cls, qmk_id):
        """
        Finds inner keycode, i.e. if it is masked like 0x5F12, just return the 0x12 portion
        """
        if cls.is_mask(qmk_id):
            qmk_id = qmk_id[qmk_id.find("(")+1:-1]
        return cls.find(qmk_id)

    @classmethod
    def find_by_recorder_alias(cls, alias):
        return cls.recorder_alias_to_keycode.get(alias)

    @classmethod
    def find_by_qmk_id(cls, qmk_id):
        return cls.qmk_id_to_keycode.get(qmk_id)

    @classmethod
    def is_mask(cls, qmk_id):
        return "(" in qmk_id and qmk_id[:qmk_id.find("(")] in cls.masked_keycodes

    @classmethod
    def is_basic(cls, qmk_id):
        return cls.deserialize(qmk_id) < 0x00FF

    @classmethod
    def label(cls, qmk_id):
        keycode = cls.find_outer_keycode(qmk_id)
        if keycode is None:
            return qmk_id
        return keycode.label

    @classmethod
    def tooltip(cls, qmk_id):
        keycode = cls.find_outer_keycode(qmk_id)
        if keycode is None:
            return None
        tooltip = keycode.qmk_id
        if keycode.tooltip:
            tooltip = "{}: {}".format(tooltip, keycode.tooltip)
        return tooltip

    @classmethod
    def serialize(cls, code):
        """ Converts integer keycode to string """
        if cls.protocol == 6:
            masked = keycodes_v6.masked
        else:
            masked = keycodes_v5.masked

        if (code & 0xFF00) not in masked:
            kc = RAWCODES_MAP.get(code)
            if kc is not None:
                return kc.qmk_id
        else:
            outer = RAWCODES_MAP.get(code & 0xFF00)
            inner = RAWCODES_MAP.get(code & 0x00FF)
            if outer is not None and inner is not None:
                return outer.qmk_id.replace("kc", inner.qmk_id)
        return hex(code)

    @classmethod
    def deserialize(cls, val, reraise=False):
        """ Converts string keycode to integer """

        from any_keycode import AnyKeycode

        global _any_keycode_cache

        if isinstance(val, int):
            return val
        if val in cls.qmk_id_to_keycode:
            return cls.resolve(cls.qmk_id_to_keycode[val].qmk_id)
        if _any_keycode_cache is None:
            _any_keycode_cache = AnyKeycode()
        try:
            return _any_keycode_cache.decode(val)
        except Exception:
            if reraise:
                raise
        return 0

    @classmethod
    def normalize(cls, code):
        """ Changes e.g. KC_PERC to LSFT(KC_5) """

        return Keycode.serialize(Keycode.deserialize(code))

    @classmethod
    def resolve(cls, qmk_constant):
        """ Translates a qmk_constant into firmware-specific integer keycode or macro constant """
        if cls.protocol == 6:
            kc = keycodes_v6.kc
        else:
            kc = keycodes_v5.kc

        if qmk_constant not in kc:
            raise RuntimeError("unable to resolve qmk_id={}".format(qmk_constant))
        return kc[qmk_constant]
        
    @classmethod
    def description(cls, qmk_id):
        keycode = cls.find_outer_keycode(qmk_id)
        if keycode is None or keycode.tooltip is None:
            return ""
        return keycode.tooltip


K = Keycode

BASIC_KEYCODES = {
    "KC_NO",
    "KC_TRNS",
    "KC_A",
    "KC_B",
    "KC_C",
    "KC_D",
    "KC_E",
    "KC_F",
    "KC_G",
    "KC_H",
    "KC_I",
    "KC_J",
    "KC_K",
    "KC_L",
    "KC_M",
    "KC_N",
    "KC_O",
    "KC_P",
    "KC_Q",
    "KC_R",
    "KC_S",
    "KC_T",
    "KC_U",
    "KC_V",
    "KC_W",
    "KC_X",
    "KC_Y",
    "KC_Z",
    "KC_1",
    "KC_2",
    "KC_3",
    "KC_4",
    "KC_5",
    "KC_6",
    "KC_7",
    "KC_8",
    "KC_9",
    "KC_0",
    "KC_ENTER",
    "KC_ESCAPE",
    "KC_BSPACE",
    "KC_TAB",
    "KC_SPACE",
    "KC_MINUS",
    "KC_EQUAL",
    "KC_LBRACKET",
    "KC_RBRACKET",
    "KC_BSLASH",
    "KC_NONUS_HASH",
    "KC_SCOLON",
    "KC_QUOTE",
    "KC_GRAVE",
    "KC_COMMA",
    "KC_DOT",
    "KC_SLASH",
    "KC_CAPSLOCK",
    "KC_F1",
    "KC_F2",
    "KC_F3",
    "KC_F4",
    "KC_F5",
    "KC_F6",
    "KC_F7",
    "KC_F8",
    "KC_F9",
    "KC_F10",
    "KC_F11",
    "KC_F12",
    "KC_PSCREEN",
    "KC_SCROLLLOCK",
    "KC_PAUSE",
    "KC_INSERT",
    "KC_HOME",
    "KC_PGUP",
    "KC_DELETE",
    "KC_END",
    "KC_PGDOWN",
    "KC_RIGHT",
    "KC_LEFT",
    "KC_DOWN",
    "KC_UP",
    "KC_NUMLOCK",
    "KC_KP_SLASH",
    "KC_KP_ASTERISK",
    "KC_KP_MINUS",
    "KC_KP_PLUS",
    "KC_KP_ENTER",
    "KC_KP_1",
    "KC_KP_2",
    "KC_KP_3",
    "KC_KP_4",
    "KC_KP_5",
    "KC_KP_6",
    "KC_KP_7",
    "KC_KP_8",
    "KC_KP_9",
    "KC_KP_0",
    "KC_KP_DOT",
    "KC_NONUS_BSLASH",
    "KC_APPLICATION",
    "KC_KP_EQUAL",
    "KC_F13",
    "KC_F14",
    "KC_F15",
    "KC_F16",
    "KC_F17",
    "KC_F18",
    "KC_F19",
    "KC_F20",
    "KC_F21",
    "KC_F22",
    "KC_F23",
    "KC_F24",
    "KC_EXEC",
    "KC_HELP",
    "KC_SLCT",
    "KC_STOP",
    "KC_AGIN",
    "KC_UNDO",
    "KC_CUT",
    "KC_COPY",
    "KC_PSTE",
    "KC_FIND",
    "KC__VOLUP",
    "KC__VOLDOWN",
    "KC_LCAP",
    "KC_LNUM",
    "KC_LSCR",
    "KC_KP_COMMA",
    "KC_RO",
    "KC_KANA",
    "KC_JYEN",
    "KC_HENK",
    "KC_MHEN",
    "KC_LANG1",
    "KC_LANG2",
    "KC_PWR",
    "KC_SLEP",
    "KC_WAKE",
    "KC_MUTE",
    "KC_VOLU",
    "KC_VOLD",
    "KC_MNXT",
    "KC_MPRV",
    "KC_MSTP",
    "KC_MPLY",
    "KC_MSEL",
    "KC_EJCT",
    "KC_MAIL",
    "KC_CALC",
    "KC_MYCM",
    "KC_WSCH",
    "KC_WHOM",
    "KC_WBAK",
    "KC_WFWD",
    "KC_WSTP",
    "KC_WREF",
    "KC_WFAV",
    "KC_MFFD",
    "KC_MRWD",
    "KC_BRIU",
    "KC_BRID",
    "KC_LCTRL",
    "KC_LSHIFT",
    "KC_LALT",
    "KC_LGUI",
    "KC_RCTRL",
    "KC_RSHIFT",
    "KC_RALT",
    "KC_RGUI",
}

KEYCODES_CLEAR = [
]

KEYCODES_SPECIAL = [
    K("KC_NO", ""),
    K("KC_TRNS", "▽", alias=["KC_TRANSPARENT"]),
]

KEYCODES_BASIC_NUMPAD = [
    K("KC_NUMLOCK", "Num\nLock", recorder_alias=["num lock"], alias=["KC_NLCK"]),
    K("KC_KP_SLASH", "/", alias=["KC_PSLS"]),
    K("KC_KP_ASTERISK", "*", alias=["KC_PAST"]),
    K("KC_KP_MINUS", "-", alias=["KC_PMNS"]),
    K("KC_KP_PLUS", "+", alias=["KC_PPLS"]),
    K("KC_KP_ENTER", "Num\nEnter", alias=["KC_PENT"]),
    K("KC_KP_1", "1", alias=["KC_P1"]),
    K("KC_KP_2", "2", alias=["KC_P2"]),
    K("KC_KP_3", "3", alias=["KC_P3"]),
    K("KC_KP_4", "4", alias=["KC_P4"]),
    K("KC_KP_5", "5", alias=["KC_P5"]),
    K("KC_KP_6", "6", alias=["KC_P6"]),
    K("KC_KP_7", "7", alias=["KC_P7"]),
    K("KC_KP_8", "8", alias=["KC_P8"]),
    K("KC_KP_9", "9", alias=["KC_P9"]),
    K("KC_KP_0", "0", alias=["KC_P0"]),
    K("KC_KP_DOT", ".", alias=["KC_PDOT"]),
    K("KC_KP_EQUAL", "=", alias=["KC_PEQL"]),
    K("KC_KP_COMMA", ",", alias=["KC_PCMM"]),
]

KEYCODES_BASIC_NAV = [
    K("KC_PSCREEN", "Print\nScreen", alias=["KC_PSCR"]),
    K("KC_SCROLLLOCK", "Scroll\nLock", recorder_alias=["scroll lock"], alias=["KC_SLCK", "KC_BRMD"]),
    K("KC_PAUSE", "Pause", recorder_alias=["pause", "break"], alias=["KC_PAUS", "KC_BRK", "KC_BRMU"]),
    K("KC_INSERT", "Insert", recorder_alias=["insert"], alias=["KC_INS"]),
    K("KC_HOME", "Home", recorder_alias=["home"]),
    K("KC_PGUP", "Page\nUp", recorder_alias=["page up"]),
    K("KC_DELETE", "Del", recorder_alias=["delete"], alias=["KC_DEL"]),
    K("KC_END", "End", recorder_alias=["end"]),
    K("KC_PGDOWN", "Page\nDown", recorder_alias=["page down"], alias=["KC_PGDN"]),
    K("KC_RIGHT", "Right", recorder_alias=["right"], alias=["KC_RGHT"]),
    K("KC_LEFT", "Left", recorder_alias=["left"]),
    K("KC_DOWN", "Down", recorder_alias=["down"]),
    K("KC_UP", "Up", recorder_alias=["up"]),
]

KEYCODES_BASIC = [
    K("KC_A", "A", printable="a", recorder_alias=["a"]),
    K("KC_B", "B", printable="b", recorder_alias=["b"]),
    K("KC_C", "C", printable="c", recorder_alias=["c"]),
    K("KC_D", "D", printable="d", recorder_alias=["d"]),
    K("KC_E", "E", printable="e", recorder_alias=["e"]),
    K("KC_F", "F", printable="f", recorder_alias=["f"]),
    K("KC_G", "G", printable="g", recorder_alias=["g"]),
    K("KC_H", "H", printable="h", recorder_alias=["h"]),
    K("KC_I", "I", printable="i", recorder_alias=["i"]),
    K("KC_J", "J", printable="j", recorder_alias=["j"]),
    K("KC_K", "K", printable="k", recorder_alias=["k"]),
    K("KC_L", "L", printable="l", recorder_alias=["l"]),
    K("KC_M", "M", printable="m", recorder_alias=["m"]),
    K("KC_N", "N", printable="n", recorder_alias=["n"]),
    K("KC_O", "O", printable="o", recorder_alias=["o"]),
    K("KC_P", "P", printable="p", recorder_alias=["p"]),
    K("KC_Q", "Q", printable="q", recorder_alias=["q"]),
    K("KC_R", "R", printable="r", recorder_alias=["r"]),
    K("KC_S", "S", printable="s", recorder_alias=["s"]),
    K("KC_T", "T", printable="t", recorder_alias=["t"]),
    K("KC_U", "U", printable="u", recorder_alias=["u"]),
    K("KC_V", "V", printable="v", recorder_alias=["v"]),
    K("KC_W", "W", printable="w", recorder_alias=["w"]),
    K("KC_X", "X", printable="x", recorder_alias=["x"]),
    K("KC_Y", "Y", printable="y", recorder_alias=["y"]),
    K("KC_Z", "Z", printable="z", recorder_alias=["z"]),
    K("KC_1", "!\n1", printable="1", recorder_alias=["1"]),
    K("KC_2", "@\n2", printable="2", recorder_alias=["2"]),
    K("KC_3", "#\n3", printable="3", recorder_alias=["3"]),
    K("KC_4", "$\n4", printable="4", recorder_alias=["4"]),
    K("KC_5", "%\n5", printable="5", recorder_alias=["5"]),
    K("KC_6", "^\n6", printable="6", recorder_alias=["6"]),
    K("KC_7", "&\n7", printable="7", recorder_alias=["7"]),
    K("KC_8", "*\n8", printable="8", recorder_alias=["8"]),
    K("KC_9", "(\n9", printable="9", recorder_alias=["9"]),
    K("KC_0", ")\n0", printable="0", recorder_alias=["0"]),
    K("KC_ENTER", "Enter", recorder_alias=["enter"], alias=["KC_ENT"]),
    K("KC_ESCAPE", "Esc", recorder_alias=["esc"], alias=["KC_ESC"]),
    K("KC_BSPACE", "Bksp", recorder_alias=["backspace"], alias=["KC_BSPC"]),
    K("KC_TAB", "Tab", recorder_alias=["tab"]),
    K("KC_SPACE", "Space", recorder_alias=["space"], alias=["KC_SPC"]),
    K("KC_MINUS", "_\n-", printable="-", recorder_alias=["-"], alias=["KC_MINS"]),
    K("KC_EQUAL", "+\n=", printable="=", recorder_alias=["="], alias=["KC_EQL"]),
    K("KC_LBRACKET", "{\n[", printable="[", recorder_alias=["["], alias=["KC_LBRC"]),
    K("KC_RBRACKET", "}\n]", printable="]", recorder_alias=["]"], alias=["KC_RBRC"]),
    K("KC_BSLASH", "|\n\\", printable="\\", recorder_alias=["\\"], alias=["KC_BSLS"]),
    K("KC_SCOLON", ":\n;", printable=";", recorder_alias=[";"], alias=["KC_SCLN"]),
    K("KC_QUOTE", "\"\n'", printable="'", recorder_alias=["'"], alias=["KC_QUOT"]),
    K("KC_GRAVE", "~\n`", printable="`", recorder_alias=["`"], alias=["KC_GRV", "KC_ZKHK"]),
    K("KC_COMMA", "<\n,", printable=",", recorder_alias=[","], alias=["KC_COMM"]),
    K("KC_DOT", ">\n.", printable=".", recorder_alias=["."]),
    K("KC_SLASH", "?\n/", printable="/", recorder_alias=["/"], alias=["KC_SLSH"]),
    K("KC_CAPSLOCK", "Caps\nLock", recorder_alias=["caps lock"], alias=["KC_CLCK", "KC_CAPS"]),
    K("KC_F1", "F1", recorder_alias=["f1"]),
    K("KC_F2", "F2", recorder_alias=["f2"]),
    K("KC_F3", "F3", recorder_alias=["f3"]),
    K("KC_F4", "F4", recorder_alias=["f4"]),
    K("KC_F5", "F5", recorder_alias=["f5"]),
    K("KC_F6", "F6", recorder_alias=["f6"]),
    K("KC_F7", "F7", recorder_alias=["f7"]),
    K("KC_F8", "F8", recorder_alias=["f8"]),
    K("KC_F9", "F9", recorder_alias=["f9"]),
    K("KC_F10", "F10", recorder_alias=["f10"]),
    K("KC_F11", "F11", recorder_alias=["f11"]),
    K("KC_F12", "F12", recorder_alias=["f12"]),

    K("KC_APPLICATION", "Menu", recorder_alias=["menu", "left menu", "right menu"], alias=["KC_APP"]),
    K("KC_LCTRL", "LCtrl", recorder_alias=["left ctrl", "ctrl"], alias=["KC_LCTL"]),
    K("KC_LSHIFT", "LShift", recorder_alias=["left shift", "shift"], alias=["KC_LSFT"]),
    K("KC_LALT", "LAlt", recorder_alias=["alt"], alias=["KC_LOPT"]),
    K("KC_LGUI", "LGui", recorder_alias=["left windows", "windows"], alias=["KC_LCMD", "KC_LWIN"]),
    K("KC_RCTRL", "RCtrl", recorder_alias=["right ctrl"], alias=["KC_RCTL"]),
    K("KC_RSHIFT", "RShift", recorder_alias=["right shift"], alias=["KC_RSFT"]),
    K("KC_RALT", "RAlt", alias=["KC_ALGR", "KC_ROPT"]),
    K("KC_RGUI", "RGui", recorder_alias=["right windows"], alias=["KC_RCMD", "KC_RWIN"]),
]

KEYCODES_BASIC.extend(KEYCODES_BASIC_NUMPAD)
KEYCODES_BASIC.extend(KEYCODES_BASIC_NAV)

KEYCODES_SHIFTED = [
    K("KC_TILD", "~"),
    K("KC_EXLM", "!"),
    K("KC_AT", "@"),
    K("KC_HASH", "#"),
    K("KC_DLR", "$"),
    K("KC_PERC", "%"),
    K("KC_CIRC", "^"),
    K("KC_AMPR", "&"),
    K("KC_ASTR", "*"),
    K("KC_LPRN", "("),
    K("KC_RPRN", ")"),
    K("KC_UNDS", "_"),
    K("KC_PLUS", "+"),
    K("KC_LCBR", "{"),
    K("KC_RCBR", "}"),
    K("KC_LT", "<"),
    K("KC_GT", ">"),
    K("KC_COLN", ":"),
    K("KC_PIPE", "|"),
    K("KC_QUES", "?"),
    K("KC_DQUO", '"'),
]

KEYCODES_ISO = [
    K("KC_NONUS_HASH", "~\n#", "Non-US # and ~", alias=["KC_NUHS"]),
    K("KC_NONUS_BSLASH", "|\n\\", "Non-US \\ and |", alias=["KC_NUBS"]),
    K("KC_RO", "_\n\\", "JIS \\ and _", alias=["KC_INT1"]),
    K("KC_KANA", "カタカナ\nひらがな", "JIS Katakana/Hiragana", alias=["KC_INT2"]),
    K("KC_JYEN", "|\n¥", alias=["KC_INT3"]),
    K("KC_HENK", "変換", "JIS Henkan", alias=["KC_INT4"]),
    K("KC_MHEN", "無変換", "JIS Muhenkan", alias=["KC_INT5"]),
]

KEYCODES_ISO_KR = [
    K("KC_LANG1", "한영\nかな", "Korean Han/Yeong / JP Mac Kana", alias=["KC_HAEN"]),
    K("KC_LANG2", "漢字\n英数", "Korean Hanja / JP Mac Eisu", alias=["KC_HANJ"]),
]

KEYCODES_ISO.extend(KEYCODES_ISO_KR)

KEYCODES_LAYERS = []

KEYCODES_OLED = [
    K("OLED_1", "Screen\nKeyboard\nShift", "Momentarily turn on layer when pressed"),
    K("OLED_2", "Smart\nChord\nLight\nMode", "Momentarily turn on layer when pressed"),
   # K("OLED_3", "SmartChord\nPiano\nModes", "Momentarily turn on layer when pressed"),
  #  K("OLED_1", "Hold\nLayer\n3", "Momentarily turn on layer when pressed"),
  #  K("OLED_1", "Hold\nLayer\n4", "Momentarily turn on layer when pressed"),
]

KEYCODES_LAYERS_MO = [
    K("MO(0)", "Hold\nLayer\n0", "Momentarily turn on layer when pressed"),
    K("MO(1)", "Hold\nLayer\n1", "Momentarily turn on layer when pressed"),
    K("MO(2)", "Hold\nLayer\n2", "Momentarily turn on layer when pressed"),
    K("MO(3)", "Hold\nLayer\n3", "Momentarily turn on layer when pressed"),
    K("MO(4)", "Hold\nLayer\n4", "Momentarily turn on layer when pressed"),
    K("MO(5)", "Hold\nLayer\n5", "Momentarily turn on layer when pressed"),
    K("MO(6)", "Hold\nLayer\n6", "Momentarily turn on layer when pressed"),
    K("MO(7)", "Hold\nLayer\n7", "Momentarily turn on layer when pressed"),
    K("MO(8)", "Hold\nLayer\n8", "Momentarily turn on layer when pressed"),
    K("MO(9)", "Hold\nLayer\n9", "Momentarily turn on layer when pressed"),
    K("MO(10)", "Hold\nLayer\n10", "Momentarily turn on layer when pressed"),
    K("MO(11)", "Hold\nLayer\n11", "Momentarily turn on layer when pressed"),
]


KEYCODES_LAYERS_DF = [
    K("DF(0)", "Default\nLayer\n0", "Set to default (active)\nLayer)"),
    K("DF(1)", "Default\nLayer\n1", "Set to default (active)\nLayer)"),
    K("DF(2)", "Default\nLayer\n2", "Set to default (active)\nLayer)"),
    K("DF(3)", "Default\nLayer\n3", "Set to default (active)\nLayer)"),
    K("DF(4)", "Default\nLayer\n4", "Set to default (active)\nLayer)"),
    K("DF(5)", "Default\nLayer\n5", "Set to default (active)\nLayer)"),
    K("DF(6)", "Default\nLayer\n6", "Set to default (active)\nLayer)"),
    K("DF(7)", "Default\nLayer\n7", "Set to default (active)\nLayer)"),
    K("DF(8)", "Default\nLayer\n8", "Set to default (active)\nLayer)"),
    K("DF(9)", "Default\nLayer\n9", "Set to default (active)\nLayer)"),
    K("DF(10)", "Default\nLayer\n10", "Set to default (active)\nLayer)"),
    K("DF(11)", "Default\nLayer\n11", "Set to default (active)\nLayer)"),
]

KEYCODES_LAYERS_TG = [
    K("TG(0)", "Toggle\nLayer\n0", "Toggle\nLayer on or off)"),
    K("TG(1)", "Toggle\nLayer\n1", "Toggle\nLayer on or off)"),
    K("TG(2)", "Toggle\nLayer\n2", "Toggle\nLayer on or off)"),
    K("TG(3)", "Toggle\nLayer\n3", "Toggle\nLayer on or off)"),
    K("TG(4)", "Toggle\nLayer\n4", "Toggle\nLayer on or off)"),
    K("TG(5)", "Toggle\nLayer\n5", "Toggle\nLayer on or off)"),
    K("TG(6)", "Toggle\nLayer\n6", "Toggle\nLayer on or off)"),
    K("TG(7)", "Toggle\nLayer\n7", "Toggle\nLayer on or off)"),
    K("TG(8)", "Toggle\nLayer\n8", "Toggle\nLayer on or off)"),
    K("TG(9)", "Toggle\nLayer\n9", "Toggle\nLayer on or off)"),
    K("TG(10)", "Toggle\nLayer\n10", "Toggle\nLayer on or off)"),
    K("TG(11)", "Toggle\nLayer\n11", "Toggle\nLayer on or off)"),
]

KEYCODES_LAYERS_TT = [
    K("TT(0)", "TT\nLayer\n0", "Normally acts like MO unless it's tapped multiple times, which toggles\nLayer on)"),
    K("TT(1)", "TT\nLayer\n1", "Normally acts like MO unless it's tapped multiple times, which toggles\nLayer on)"),
    K("TT(2)", "TT\nLayer\n2", "Normally acts like MO unless it's tapped multiple times, which toggles\nLayer on)"),
    K("TT(3)", "TT\nLayer\n3", "Normally acts like MO unless it's tapped multiple times, which toggles\nLayer on)"),
    K("TT(4)", "TT\nLayer\n4", "Normally acts like MO unless it's tapped multiple times, which toggles\nLayer on)"),
    K("TT(5)", "TT\nLayer\n5", "Normally acts like MO unless it's tapped multiple times, which toggles\nLayer on)"),
    K("TT(6)", "TT\nLayer\n6", "Normally acts like MO unless it's tapped multiple times, which toggles\nLayer on)"),
    K("TT(7)", "TT\nLayer\n7", "Normally acts like MO unless it's tapped multiple times, which toggles\nLayer on)"),
    K("TT(8)", "TT\nLayer\n8", "Normally acts like MO unless it's tapped multiple times, which toggles\nLayer on)"),
    K("TT(9)", "TT\nLayer\n9", "Normally acts like MO unless it's tapped multiple times, which toggles\nLayer on)"),
    K("TT(10)", "TT\nLayer\n10", "Normally acts like MO unless it's tapped multiple times, which toggles\nLayer on)"),
    K("TT(11)", "TT\nLayer\n11", "Normally acts like MO unless it's tapped multiple times, which toggles\nLayer on)"),
]

KEYCODES_LAYERS_OSL = [
    K("OSL(0)", "One Shot\nLayer\n0", "Momentarily activates\nLayer until a key is pressed)"),
    K("OSL(1)", "One Shot\nLayer\n1", "Momentarily activates\nLayer until a key is pressed)"),
    K("OSL(2)", "One Shot\nLayer\n2", "Momentarily activates\nLayer until a key is pressed)"),
    K("OSL(3)", "One Shot\nLayer\n3", "Momentarily activates\nLayer until a key is pressed)"),
    K("OSL(4)", "One Shot\nLayer\n4", "Momentarily activates\nLayer until a key is pressed)"),
    K("OSL(5)", "One Shot\nLayer\n5", "Momentarily activates\nLayer until a key is pressed)"),
    K("OSL(6)", "One Shot\nLayer\n6", "Momentarily activates\nLayer until a key is pressed)"),
    K("OSL(7)", "One Shot\nLayer\n7", "Momentarily activates\nLayer until a key is pressed)"),
    K("OSL(8)", "One Shot\nLayer\n8", "Momentarily activates\nLayer until a key is pressed)"),
    K("OSL(9)", "One Shot\nLayer\n9", "Momentarily activates\nLayer until a key is pressed)"),
    K("OSL(10)", "One Shot\nLayer\n10", "Momentarily activates\nLayer until a key is pressed)"),
    K("OSL(11)", "One Shot\nLayer\n11", "Momentarily activates\nLayer until a key is pressed)"),
]

KEYCODES_LAYERS_TO = [
    K("TO(0)", "TO\nLayer\n0", "Turns on\nLayer and turns off all other\nLayers, except the default\nLayer)"),
    K("TO(1)", "TO\nLayer\n1", "Turns on\nLayer and turns off all other\nLayers, except the default\nLayer)"),
    K("TO(2)", "TO\nLayer\n2", "Turns on\nLayer and turns off all other\nLayers, except the default\nLayer)"),
    K("TO(3)", "TO\nLayer\n3", "Turns on\nLayer and turns off all other\nLayers, except the default\nLayer)"),
    K("TO(4)", "TO\nLayer\n4", "Turns on\nLayer and turns off all other\nLayers, except the default\nLayer)"),
    K("TO(5)", "TO\nLayer\n5", "Turns on\nLayer and turns off all other\nLayers, except the default\nLayer)"),
    K("TO(6)", "TO\nLayer\n6", "Turns on\nLayer and turns off all other\nLayers, except the default\nLayer)"),
    K("TO(7)", "TO\nLayer\n7", "Turns on\nLayer and turns off all other\nLayers, except the default\nLayer)"),
    K("TO(8)", "TO\nLayer\n8", "Turns on\nLayer and turns off all other\nLayers, except the default\nLayer)"),
    K("TO(9)", "TO\nLayer\n9", "Turns on\nLayer and turns off all other\nLayers, except the default\nLayer)"),
    K("TO(10)", "TO\nLayer\n10", "Turns on\nLayer and turns off all other\nLayers, except the default\nLayer)"),
    K("TO(11)", "TO\nLayer\n11", "Turns on\nLayer and turns off all other\nLayers, except the default\nLayer)"),
]

KEYCODES_LAYERS_LT = [
    K("LT1(kc)", "LT\nLayer\n0", "kc on tap, switch to specified\nLayer while held)"),
    K("LT1(kc)", "LT\nLayer\n1", "kc on tap, switch to specified\nLayer while held)"),
    K("LT2(kc)", "LT\nLayer\n2", "kc on tap, switch to specified\nLayer while held)"),
    K("LT3(kc)", "LT\nLayer\n3", "kc on tap, switch to specified\nLayer while held)"),
    K("LT4(kc)", "LT\nLayer\n4", "kc on tap, switch to specified\nLayer while held)"),
    K("LT5(kc)", "LT\nLayer\n5", "kc on tap, switch to specified\nLayer while held)"),
    K("LT6(kc)", "LT\nLayer\n6", "kc on tap, switch to specified\nLayer while held)"),
    K("LT7(kc)", "LT\nLayer\n7", "kc on tap, switch to specified\nLayer while held)"),
    K("LT8(kc)", "LT\nLayer\n8", "kc on tap, switch to specified\nLayer while held)"),
    K("LT9(kc)", "LT\nLayer\n9", "kc on tap, switch to specified\nLayer while held)"),
    K("LT10(kc)", "LT\nLayer\n10", "kc on tap, switch to specified\nLayer while held)"),
    K("LT11(kc)", "LT\nLayer\n11", "kc on tap, switch to specified\nLayer while held)"),
]





RESET_KEYCODE = "RESET"

KEYCODES_BOOT = [
    K("RESET", "Reset", "Reboot to bootloader")
]

KEYCODES_MODIFIERS = [
    K("OSM(MOD_LSFT)", "OSM\nLSft", "Enable Left Shift for one keypress"),
    K("OSM(MOD_LCTL)", "OSM\nLCtl", "Enable Left Control for one keypress"),
    K("OSM(MOD_LALT)", "OSM\nLAlt", "Enable Left Alt for one keypress"),
    K("OSM(MOD_LGUI)", "OSM\nLGUI", "Enable Left GUI for one keypress"),
    K("OSM(MOD_RSFT)", "OSM\nRSft", "Enable Right Shift for one keypress"),
    K("OSM(MOD_RCTL)", "OSM\nRCtl", "Enable Right Control for one keypress"),
    K("OSM(MOD_RALT)", "OSM\nRAlt", "Enable Right Alt for one keypress"),
    K("OSM(MOD_RGUI)", "OSM\nRGUI", "Enable Right GUI for one keypress"),
    K("OSM(MOD_LCTL|MOD_LSFT)", "OSM\nCS", "Enable Left Control and Shift for one keypress"),
    K("OSM(MOD_LCTL|MOD_LALT)", "OSM\nCA", "Enable Left Control and Alt for one keypress"),
    K("OSM(MOD_LCTL|MOD_LGUI)", "OSM\nCG", "Enable Left Control and GUI for one keypress"),
    K("OSM(MOD_LSFT|MOD_LALT)", "OSM\nSA", "Enable Left Shift and Alt for one keypress"),
    K("OSM(MOD_LSFT|MOD_LGUI)", "OSM\nSG", "Enable Left Shift and GUI for one keypress"),
    K("OSM(MOD_LALT|MOD_LGUI)", "OSM\nAG", "Enable Left Alt and GUI for one keypress"),
    K("OSM(MOD_RCTL|MOD_RSFT)", "OSM\nRCS", "Enable Right Control and Shift for one keypress"),
    K("OSM(MOD_RCTL|MOD_RALT)", "OSM\nRCA", "Enable Right Control and Alt for one keypress"),
    K("OSM(MOD_RCTL|MOD_RGUI)", "OSM\nRCG", "Enable Right Control and GUI for one keypress"),
    K("OSM(MOD_RSFT|MOD_RALT)", "OSM\nRSA", "Enable Right Shift and Alt for one keypress"),
    K("OSM(MOD_RSFT|MOD_RGUI)", "OSM\nRSG", "Enable Right Shift and GUI for one keypress"),
    K("OSM(MOD_RALT|MOD_RGUI)", "OSM\nRAG", "Enable Right Alt and GUI for one keypress"),
    K("OSM(MOD_LCTL|MOD_LSFT|MOD_LGUI)", "OSM\nCSG", "Enable Left Control, Shift, and GUI for one keypress"),
    K("OSM(MOD_LCTL|MOD_LALT|MOD_LGUI)", "OSM\nCAG", "Enable Left Control, Alt, and GUI for one keypress"),
    K("OSM(MOD_LSFT|MOD_LALT|MOD_LGUI)", "OSM\nSAG", "Enable Left Shift, Alt, and GUI for one keypress"),
    K("OSM(MOD_RCTL|MOD_RSFT|MOD_RGUI)", "OSM\nRCSG", "Enable Right Control, Shift, and GUI for one keypress"),
    K("OSM(MOD_RCTL|MOD_RALT|MOD_RGUI)", "OSM\nRCAG", "Enable Right Control, Alt, and GUI for one keypress"),
    K("OSM(MOD_RSFT|MOD_RALT|MOD_RGUI)", "OSM\nRSAG", "Enable Right Shift, Alt, and GUI for one keypress"),
    K("OSM(MOD_MEH)", "OSM\nMeh", "Enable Left Control, Shift, and Alt for one keypress"),
    K("OSM(MOD_HYPR)", "OSM\nHyper", "Enable Left Control, Shift, Alt, and GUI for one keypress"),
    K("OSM(MOD_RCTL|MOD_RSFT|MOD_RALT)", "OSM\nRMeh", "Enable Right Control, Shift, and Alt for one keypress"),
    K("OSM(MOD_RCTL|MOD_RSFT|MOD_RALT|MOD_RGUI)", "OSM\nRHyp", "Enable Right Control, Shift, Alt, and GUI for one keypress"),

    K("KC_GESC", "~\nEsc", "Esc normally, but ~ when Shift or GUI is pressed"),
    K("KC_LSPO", "LS\n(", "Left Shift when held, ( when tapped"),
    K("KC_RSPC", "RS\n)", "Right Shift when held, ) when tapped"),
    K("KC_LCPO", "LC\n(", "Left Control when held, ( when tapped"),
    K("KC_RCPC", "RC\n)", "Right Control when held, ) when tapped"),
    K("KC_LAPO", "LA\n(", "Left Alt when held, ( when tapped"),
    K("KC_RAPC", "RA\n)", "Right Alt when held, ) when tapped"),
    K("KC_SFTENT", "RS\nEnter", "Right Shift when held, Enter when tapped"),
]

KEYCODES_KC = [
    K("LSFT(kc)", "LSft\n(kc)", masked=True),
    K("LCTL(kc)", "LCtl\n(kc)", masked=True),
    K("LALT(kc)", "LAlt\n(kc)", masked=True),
    K("LGUI(kc)", "LGui\n(kc)", masked=True),
    K("RSFT(kc)", "RSft\n(kc)", masked=True),
    K("RCTL(kc)", "RCtl\n(kc)", masked=True),
    K("RALT(kc)", "RAlt\n(kc)", masked=True),
    K("RGUI(kc)", "RGui\n(kc)", masked=True),
    K("C_S(kc)", "LCS\n(kc)", "LCTL + LSFT", masked=True, alias=["LCS(kc)"]),
    K("LCA(kc)", "LCA\n(kc)", "LCTL + LALT", masked=True),
    K("LCG(kc)", "LCG\n(kc)", "LCTL + LGUI", masked=True),
    K("LSA(kc)", "LSA\n(kc)", "LSFT + LALT", masked=True),
    K("SGUI(kc)", "LSG\n(kc)", "LGUI + LSFT", masked=True, alias=["LSG(kc)"]),
    K("LCAG(kc)", "LCAG\n(kc)", "LCTL + LALT + LGUI", masked=True),
    K("RCG(kc)", "RCG\n(kc)", "RCTL + RGUI", masked=True),
    K("MEH(kc)", "Meh\n(kc)", "LCTL + LSFT + LALT", masked=True),
    K("HYPR(kc)", "Hyper\n(kc)", "LCTL + LSFT + LALT + LGUI", masked=True),

    K("LSFT_T(kc)", "LSft_T\n(kc)", "Left Shift when held, kc when tapped", masked=True),
    K("LCTL_T(kc)", "LCtl_T\n(kc)", "Left Control when held, kc when tapped", masked=True),
    K("LALT_T(kc)", "LAlt_T\n(kc)", "Left Alt when held, kc when tapped", masked=True),
    K("LGUI_T(kc)", "LGui_T\n(kc)", "Left GUI when held, kc when tapped", masked=True),
    K("RSFT_T(kc)", "RSft_T\n(kc)", "Right Shift when held, kc when tapped", masked=True),
    K("RCTL_T(kc)", "RCtl_T\n(kc)", "Right Control when held, kc when tapped", masked=True),
    K("RALT_T(kc)", "RAlt_T\n(kc)", "Right Alt when held, kc when tapped", masked=True),
    K("RGUI_T(kc)", "RGui_T\n(kc)", "Right GUI when held, kc when tapped", masked=True),
    K("C_S_T(kc)", "LCS_T\n(kc)", "Left Control + Left Shift when held, kc when tapped", masked=True, alias=["LCS_T(kc)"] ),
    K("LCA_T(kc)", "LCA_T\n(kc)", "LCTL + LALT when held, kc when tapped", masked=True),
    K("LCG_T(kc)", "LCG_T\n(kc)", "LCTL + LGUI when held, kc when tapped", masked=True),
    K("LSA_T(kc)", "LSA_T\n(kc)", "LSFT + LALT when held, kc when tapped", masked=True),
    K("SGUI_T(kc)", "LSG_T\n(kc)", "LGUI + LSFT when held, kc when tapped", masked=True, alias=["LSG_T(kc)"]),
    K("LCAG_T(kc)", "LCAG_T\n(kc)", "LCTL + LALT + LGUI when held, kc when tapped", masked=True),
    K("RCG_T(kc)", "RCG_T\n(kc)", "RCTL + RGUI when held, kc when tapped", masked=True),
    K("RCAG_T(kc)", "RCAG_T\n(kc)", "RCTL + RALT + RGUI when held, kc when tapped", masked=True),
    K("MEH_T(kc)", "Meh_T\n(kc)", "LCTL + LSFT + LALT when held, kc when tapped", masked=True),
    K("ALL_T(kc)", "ALL_T\n(kc)", "LCTL + LSFT + LALT + LGUI when held, kc when tapped", masked=True),
]

KEYCODES_QUANTUM = [
    K("MAGIC_SWAP_CONTROL_CAPSLOCK", "Swap\nCtrl\nCaps", "Swap Caps Lock and Left Control", alias=["CL_SWAP"]),
    K("MAGIC_UNSWAP_CONTROL_CAPSLOCK", "Unswap\nCtrl\nCaps", "Unswap Caps Lock and Left Control", alias=["CL_NORM"]),
    K("MAGIC_CAPSLOCK_TO_CONTROL", "Caps\nto\nCtrl", "Treat Caps Lock as Control", alias=["CL_CTRL"]),
    K("MAGIC_UNCAPSLOCK_TO_CONTROL", "Caps\nnot to\nCtrl", "Stop treating Caps Lock as Control", alias=["CL_CAPS"]),
    K("MAGIC_SWAP_LCTL_LGUI", "Swap\nLCtl\nLGui", "Swap Left Control and GUI", alias=["LCG_SWP"]),
    K("MAGIC_UNSWAP_LCTL_LGUI", "Unswap\nLCtl\nLGui", "Unswap Left Control and GUI", alias=["LCG_NRM"]),
    K("MAGIC_SWAP_RCTL_RGUI", "Swap\nRCtl\nRGui", "Swap Right Control and GUI", alias=["RCG_SWP"]),
    K("MAGIC_UNSWAP_RCTL_RGUI", "Unswap\nRCtl\nRGui", "Unswap Right Control and GUI", alias=["RCG_NRM"]),
    K("MAGIC_SWAP_CTL_GUI", "Swap\nCtl\nGui", "Swap Control and GUI on both sides", alias=["CG_SWAP"]),
    K("MAGIC_UNSWAP_CTL_GUI", "Unswap\nCtl\nGui", "Unswap Control and GUI on both sides", alias=["CG_NORM"]),
    K("MAGIC_TOGGLE_CTL_GUI", "Toggle\nCtl\nGui", "Toggle Control and GUI swap on both sides", alias=["CG_TOGG"]),
    K("MAGIC_SWAP_LALT_LGUI", "Swap\nLAlt\nLGui", "Swap Left Alt and GUI", alias=["LAG_SWP"]),
    K("MAGIC_UNSWAP_LALT_LGUI", "Unswap\nLAlt\nLGui", "Unswap Left Alt and GUI", alias=["LAG_NRM"]),
    K("MAGIC_SWAP_RALT_RGUI", "Swap\nRAlt\nRGui", "Swap Right Alt and GUI", alias=["RAG_SWP"]),
    K("MAGIC_UNSWAP_RALT_RGUI", "Unswap\nRAlt\nRGui", "Unswap Right Alt and GUI", alias=["RAG_NRM"]),
    K("MAGIC_SWAP_ALT_GUI", "Swap\nAlt\nGui", "Swap Alt and GUI on both sides", alias=["AG_SWAP"]),
    K("MAGIC_UNSWAP_ALT_GUI", "Unswap\nAlt\nGui", "Unswap Alt and GUI on both sides", alias=["AG_NORM"]),
    K("MAGIC_TOGGLE_ALT_GUI", "Toggle\nAlt\nGui", "Toggle Alt and GUI swap on both sides", alias=["AG_TOGG"]),
    K("MAGIC_NO_GUI", "GUI\nOff", "Disable the GUI keys", alias=["GUI_OFF"]),
    K("MAGIC_UNNO_GUI", "GUI\nOn", "Enable the GUI keys", alias=["GUI_ON"]),
    K("MAGIC_SWAP_GRAVE_ESC", "Swap\n`\nEsc", "Swap ` and Escape", alias=["GE_SWAP"]),
    K("MAGIC_UNSWAP_GRAVE_ESC", "Unswap\n`\nEsc", "Unswap ` and Escape", alias=["GE_NORM"]),
    K("MAGIC_SWAP_BACKSLASH_BACKSPACE", "Swap\n\\\nBS", "Swap \\ and Backspace", alias=["BS_SWAP"]),
    K("MAGIC_UNSWAP_BACKSLASH_BACKSPACE", "Unswap\n\\\nBS", "Unswap \\ and Backspace", alias=["BS_NORM"]),
    K("MAGIC_HOST_NKRO", "NKRO\nOn", "Enable N-key rollover", alias=["NK_ON"]),
    K("MAGIC_UNHOST_NKRO", "NKRO\nOff", "Disable N-key rollover", alias=["NK_OFF"]),
    K("MAGIC_TOGGLE_NKRO", "NKRO\nToggle", "Toggle N-key rollover", alias=["NK_TOGG"]),
    K("MAGIC_EE_HANDS_LEFT", "EEH\nLeft", "Set the master half of a split keyboard as the left hand (for EE_HANDS)",
      alias=["EH_LEFT"]),
    K("MAGIC_EE_HANDS_RIGHT", "EEH\nRight", "Set the master half of a split keyboard as the right hand (for EE_HANDS)",
      alias=["EH_RGHT"]),

    K("AU_ON", "Audio\nON", "Audio mode on"),
    K("AU_OFF", "Audio\nOFF", "Audio mode off"),
    K("AU_TOG", "Audio\nToggle", "Toggles Audio mode"),
    K("CLICKY_TOGGLE", "Clicky\nToggle", "Toggles Audio clicky mode", alias=["CK_TOGG"]),
    K("CLICKY_UP", "Clicky\nUp", "Increases frequency of the clicks", alias=["CK_UP"]),
    K("CLICKY_DOWN", "Clicky\nDown", "Decreases frequency of the clicks", alias=["CK_DOWN"]),
    K("CLICKY_RESET", "Clicky\nReset", "Resets frequency to default", alias=["CK_RST"]),
    K("MU_ON", "Music\nOn", "Turns on Music Mode"),
    K("MU_OFF", "Music\nOff", "Turns off Music Mode"),
    K("MU_TOG", "Music\nToggle", "Toggles Music Mode"),
    K("MU_MOD", "Music\nCycle", "Cycles through the music modes"),

    K("HPT_ON", "Haptic\nOn", "Turn haptic feedback on"),
    K("HPT_OFF", "Haptic\nOff", "Turn haptic feedback off"),
    K("HPT_TOG", "Haptic\nToggle", "Toggle haptic feedback on/off"),
    K("HPT_RST", "Haptic\nReset", "Reset haptic feedback config to default"),
    K("HPT_FBK", "Haptic\nFeed\nback", "Toggle feedback to occur on keypress, release or both"),
    K("HPT_BUZ", "Haptic\nBuzz", "Toggle solenoid buzz on/off"),
    K("HPT_MODI", "Haptic\nNext", "Go to next DRV2605L waveform"),
    K("HPT_MODD", "Haptic\nPrev", "Go to previous DRV2605L waveform"),
    K("HPT_CONT", "Haptic\nCont.", "Toggle continuous haptic mode on/off"),
    K("HPT_CONI", "Haptic\n+", "Increase DRV2605L continous haptic strength"),
    K("HPT_COND", "Haptic\n-", "Decrease DRV2605L continous haptic strength"),
    K("HPT_DWLI", "Haptic\nDwell+", "Increase Solenoid dwell time"),
    K("HPT_DWLD", "Haptic\nDwell-", "Decrease Solenoid dwell time"),

    K("KC_ASDN", "Auto-\nshift\nDown", "Lower the Auto Shift timeout variable (down)"),
    K("KC_ASUP", "Auto-\nshift\nUp", "Raise the Auto Shift timeout variable (up)"),
    K("KC_ASRP", "Auto-\nshift\nReport", "Report your current Auto Shift timeout value"),
    K("KC_ASON", "Auto-\nshift\nOn", "Turns on the Auto Shift Function"),
    K("KC_ASOFF", "Auto-\nshift\nOff", "Turns off the Auto Shift Function"),
    K("KC_ASTG", "Auto-\nshift\nToggle", "Toggles the state of the Auto Shift feature"),

    K("CMB_ON", "Combo\nOn", "Turns on Combo feature"),
    K("CMB_OFF", "Combo\nOff", "Turns off Combo feature"),
    K("CMB_TOG", "Combo\nToggle", "Toggles Combo feature on and off"),
]

KEYCODES_BACKLIGHT = [
    K("RGB_TOG", "RGB\nToggle", "Toggle RGB lighting on or off"),
    K("RGB_MOD", "RGB\nMode +", "Next RGB mode"),
    K("RGB_RMOD", "RGB\nMode -", "Previous RGB mode"),
    K("RGB_HUI", "Hue\n+", "Increase hue"),
    K("RGB_HUD", "Hue\n-", "Decrease hue"),
    K("RGB_SAI", "Sat\n+", "Increase saturation"),
    K("RGB_SAD", "Sat\n-", "Decrease saturation"),
    K("RGB_VAI", "Bright\n+", "Increase value"),
    K("RGB_VAD", "Bright\n-", "Decrease value"),
    K("RGB_SPI", "Speed\n+", "Increase RGB effect speed"),
    K("RGB_SPD", "Speed\n-", "Decrease RGB effect speed"),
]

KEYCODES_MEDIA = [
    K("KC_F13", "F13"),
    K("KC_F14", "F14"),
    K("KC_F15", "F15"),
    K("KC_F16", "F16"),
    K("KC_F17", "F17"),
    K("KC_F18", "F18"),
    K("KC_F19", "F19"),
    K("KC_F20", "F20"),
    K("KC_F21", "F21"),
    K("KC_F22", "F22"),
    K("KC_F23", "F23"),
    K("KC_F24", "F24"),

    K("KC_PWR", "Power", "System Power Down", alias=["KC_SYSTEM_POWER"]),
    K("KC_SLEP", "Sleep", "System Sleep", alias=["KC_SYSTEM_SLEEP"]),
    K("KC_WAKE", "Wake", "System Wake", alias=["KC_SYSTEM_WAKE"]),
    K("KC_EXEC", "Exec", "Execute", alias=["KC_EXECUTE"]),
    K("KC_HELP", "Help"),
    K("KC_SLCT", "Select", alias=["KC_SELECT"]),
    K("KC_STOP", "Stop"),
    K("KC_AGIN", "Again", alias=["KC_AGAIN"]),
    K("KC_UNDO", "Undo"),
    K("KC_CUT", "Cut"),
    K("KC_COPY", "Copy"),
    K("KC_PSTE", "Paste", alias=["KC_PASTE"]),
    K("KC_FIND", "Find"),

    K("KC_CALC", "Calc", "Launch Calculator (Windows)", alias=["KC_CALCULATOR"]),
    K("KC_MAIL", "Mail", "Launch Mail (Windows)"),
    K("KC_MSEL", "Media\nPlayer", "Launch Media Player (Windows)", alias=["KC_MEDIA_SELECT"]),
    K("KC_MYCM", "My\nPC", "Launch My Computer (Windows)", alias=["KC_MY_COMPUTER"]),
    K("KC_WSCH", "Browser\nSearch", "Browser Search (Windows)", alias=["KC_WWW_SEARCH"]),
    K("KC_WHOM", "Browser\nHome", "Browser Home (Windows)", alias=["KC_WWW_HOME"]),
    K("KC_WBAK", "Browser\nBack", "Browser Back (Windows)", alias=["KC_WWW_BACK"]),
    K("KC_WFWD", "Browser\nForward", "Browser Forward (Windows)", alias=["KC_WWW_FORWARD"]),
    K("KC_WSTP", "Browser\nStop", "Browser Stop (Windows)", alias=["KC_WWW_STOP"]),
    K("KC_WREF", "Browser\nRefresh", "Browser Refresh (Windows)", alias=["KC_WWW_REFRESH"]),
    K("KC_WFAV", "Browser\nFav.", "Browser Favorites (Windows)", alias=["KC_WWW_FAVORITES"]),
    K("KC_BRIU", "Bright.\nUp", "Increase the brightness of screen (Laptop)", alias=["KC_BRIGHTNESS_UP"]),
    K("KC_BRID", "Bright.\nDown", "Decrease the brightness of screen (Laptop)", alias=["KC_BRIGHTNESS_DOWN"]),

    K("KC_MPRV", "Media\nPrev", "Previous Track", alias=["KC_MEDIA_PREV_TRACK"]),
    K("KC_MNXT", "Media\nNext", "Next Track", alias=["KC_MEDIA_NEXT_TRACK"]),
    K("KC_MUTE", "Mute", "Mute Audio", alias=["KC_AUDIO_MUTE"]),
    K("KC_VOLD", "Vol -", "Volume Down", alias=["KC_AUDIO_VOL_DOWN"]),
    K("KC_VOLU", "Vol +", "Volume Up", alias=["KC_AUDIO_VOL_UP"]),
    K("KC__VOLDOWN", "Vol -\nAlt", "Volume Down Alternate"),
    K("KC__VOLUP", "Vol +\nAlt", "Volume Up Alternate"),
    K("KC_MSTP", "Media\nStop", alias=["KC_MEDIA_STOP"]),
    K("KC_MPLY", "Media\nPlay", "Play/Pause", alias=["KC_MEDIA_PLAY_PAUSE"]),
    K("KC_MRWD", "Prev\nTrack\n(macOS)", "Previous Track / Rewind (macOS)", alias=["KC_MEDIA_REWIND"]),
    K("KC_MFFD", "Next\nTrack\n(macOS)", "Next Track / Fast Forward (macOS)", alias=["KC_MEDIA_FAST_FORWARD"]),
    K("KC_EJCT", "Eject", "Eject (macOS)", alias=["KC_MEDIA_EJECT"]),

    K("KC_MS_U", "Mouse\nUp", "Mouse Cursor Up", alias=["KC_MS_UP"]),
    K("KC_MS_D", "Mouse\nDown", "Mouse Cursor Down", alias=["KC_MS_DOWN"]),
    K("KC_MS_L", "Mouse\nLeft", "Mouse Cursor Left", alias=["KC_MS_LEFT"]),
    K("KC_MS_R", "Mouse\nRight", "Mouse Cursor Right", alias=["KC_MS_RIGHT"]),
    K("KC_BTN1", "Mouse\n1", "Mouse Button 1", alias=["KC_MS_BTN1"]),
    K("KC_BTN2", "Mouse\n2", "Mouse Button 2", alias=["KC_MS_BTN2"]),
    K("KC_BTN3", "Mouse\n3", "Mouse Button 3", alias=["KC_MS_BTN3"]),
    K("KC_BTN4", "Mouse\n4", "Mouse Button 4", alias=["KC_MS_BTN4"]),
    K("KC_BTN5", "Mouse\n5", "Mouse Button 5", alias=["KC_MS_BTN5"]),
    K("KC_WH_U", "Mouse\nWheel\nUp", alias=["KC_MS_WH_UP"]),
    K("KC_WH_D", "Mouse\nWheel\nDown", alias=["KC_MS_WH_DOWN"]),
    K("KC_WH_L", "Mouse\nWheel\nLeft", alias=["KC_MS_WH_LEFT"]),
    K("KC_WH_R", "Mouse\nWheel\nRight", alias=["KC_MS_WH_RIGHT"]),
    K("KC_ACL0", "Mouse\nAccel\n0", "Set mouse acceleration to 0", alias=["KC_MS_ACCEL0"]),
    K("KC_ACL1", "Mouse\nAccel\n1", "Set mouse acceleration to 1", alias=["KC_MS_ACCEL1"]),
    K("KC_ACL2", "Mouse\nAccel\n2", "Set mouse acceleration to 2", alias=["KC_MS_ACCEL2"]),

    K("KC_LCAP", "Locking\nCaps", "Locking Caps Lock", alias=["KC_LOCKING_CAPS"]),
    K("KC_LNUM", "Locking\nNum", "Locking Num Lock", alias=["KC_LOCKING_NUM"]),
    K("KC_LSCR", "Locking\nScroll", "Locking Scroll Lock", alias=["KC_LOCKING_SCROLL"]),
]

KEYCODES_SAVE = [
    K("SAVE_SETTINGS", "Save as\nDefault\nSettings", "save settings"),
    K("DEFAULT_SETTINGS", "Reset to\nFactory\nSettings", "reset to factory"),
]

KEYCODES_SETTINGS1 = [
    K("DEFAULT_SETTINGS", "Reset to\nFactory\nSettings", "reset to factory"),    
    K("SAVE_SETTINGS", "Save as\nDefault\nSettings", "save settings"),     
    K("LOAD_SETTINGS", "Load\nDefault\nSettings", "load settings"),
    K("MI_SETTINGS_MENU", "Settings\nMenu", "Open the on-device settings menu on the keyboard screen"),
    K("MI_LOAD_MENU", "Load\nPreset\nMenu", "Open the on-device load-preset picker on the keyboard screen"),
    K("MI_EDIT_STYLES", "Playing\nStyle\nEditor", "Open the on-device velocity-preset (playing style) editor"),
]    

KEYCODES_SETTINGS2 = [
    K("SAVE_SETTINGS_2", "Save\nto\nPreset 1", "save preset 1"),
    K("SAVE_SETTINGS_3", "Save\nto\nPreset 2", "save preset 2"),
    K("SAVE_SETTINGS_4", "Save\nto\nPreset 3", "save preset 3"),
    K("SAVE_SETTINGS_5", "Save\nto\nPreset 4", "save preset 4"),
]

KEYCODES_SETTINGS3 = [
    K("LOAD_SETTINGS_2", "Load\nPreset 1", "load preset 1"),
    K("LOAD_SETTINGS_3", "Load\nPreset 2", "load preset 2"),
    K("LOAD_SETTINGS_4", "Load\nPreset 3", "load preset 3"),
    K("LOAD_SETTINGS_5", "Load\nPreset 4", "load preset 4"),
]

KEYCODES_TAP_DANCE = [
    K("TD(0)", "Tap/\nHold\n0", "TapDance0"),
    K("TD(1)", "Tap/\nHold\n1", "TapDance1"),
    K("TD(2)", "Tap/\nHold\n2", "TapDance2"),
    K("TD(3)", "Tap/\nHold\n3", "TapDance3"),
    K("TD(4)", "Tap/\nHold\n4", "TapDance4"),
    K("TD(5)", "Tap/\nHold\n5", "TapDance5"),
    K("TD(6)", "Tap/\nHold\n6", "TapDance6"),
    K("TD(7)", "Tap/\nHold\n7", "TapDance7"),
    K("TD(8)", "Tap/\nHold\n8", "TapDance8"),
    K("TD(9)", "Tap/\nHold\n9", "TapDance9"),
    K("TD(10)", "Tap/\nHold\n10", "TapDance10"),
    K("TD(11)", "Tap/\nHold\n11", "TapDance11"),
    K("TD(12)", "Tap/\nHold\n12", "TapDance12"),
    K("TD(13)", "Tap/\nHold\n13", "TapDance13"),
    K("TD(14)", "Tap/\nHold\n14", "TapDance14"),
    K("TD(15)", "Tap/\nHold\n15", "TapDance15"),
    K("TD(16)", "Tap/\nHold\n16", "TapDance16"),
    K("TD(17)", "Tap/\nHold\n17", "TapDance17"),
    K("TD(18)", "Tap/\nHold\n18", "TapDance18"),
    K("TD(19)", "Tap/\nHold\n19", "TapDance19"),
    K("TD(20)", "Tap/\nHold\n20", "TapDance20"),
    K("TD(21)", "Tap/\nHold\n21", "TapDance21"),
    K("TD(22)", "Tap/\nHold\n22", "TapDance22"),
    K("TD(23)", "Tap/\nHold\n23", "TapDance23"),
    K("TD(24)", "Tap/\nHold\n24", "TapDance24"),
    K("TD(25)", "Tap/\nHold\n25", "TapDance25"),
    K("TD(26)", "Tap/\nHold\n26", "TapDance26"),
    K("TD(27)", "Tap/\nHold\n27", "TapDance27"),
    K("TD(28)", "Tap/\nHold\n28", "TapDance28"),
    K("TD(29)", "Tap/\nHold\n29", "TapDance29"),
    K("TD(30)", "Tap/\nHold\n30", "TapDance30"),
    K("TD(31)", "Tap/\nHold\n31", "TapDance31"),
]

KEYCODES_USER = [
    K("USER00", "USER00", "USER00"),
    K("USER01", "USER01", "USER01"),
    K("USER02", "USER02", "USER02"),
    K("USER03", "USER03", "USER03"),
    K("USER04", "USER04", "USER04"),
    K("USER05", "USER05", "USER05"),
    K("USER06", "USER06", "USER06"),
    K("USER07", "USER07", "USER07"),
    K("USER08", "USER08", "USER08"),
    K("USER09", "USER09", "USER09"),
    K("USER10", "USER10", "USER10"),
    K("USER11", "USER11", "USER11"),
    K("USER12", "USER12", "USER12"),
    K("USER13", "USER13", "USER13"),
    K("USER14", "USER14", "USER14"),
    K("USER15", "USER15", "USER15"),
]

KEYCODES_MACRO = [
    K("M0", "Macro\n0", "Macro\n1"),
    K("M1", "Macro\n1", "Macro\n1"),
    K("M2", "Macro\n2", "Macro\n2"),
    K("M3", "Macro\n3", "Macro\n3"),
    K("M4", "Macro\n4", "Macro\n4"),
    K("M5", "Macro\n5", "Macro\n5"),
    K("M6", "Macro\n6", "Macro\n6"),
    K("M7", "Macro\n7", "Macro\n7"),
    K("M8", "Macro\n8", "Macro\n8"),
    K("M9", "Macro\n9", "Macro\n9"),
    K("M10", "Macro\n10", "Macro\n10"),
    K("M11", "Macro\n11", "Macro\n11"),
    K("M12", "Macro\n12", "Macro\n12"),
    K("M13", "Macro\n13", "Macro\n13"),
    K("M14", "Macro\n14", "Macro\n14"),
    K("M15", "Macro\n15", "Macro\n15"),
    K("M16", "Macro\n16", "Macro\n16"),
    K("M17", "Macro\n17", "Macro\n17"),
    K("M18", "Macro\n18", "Macro\n18"),
    K("M19", "Macro\n19", "Macro\n19"),
    K("M20", "Macro\n20", "Macro\n20"),
    K("M21", "Macro\n21", "Macro\n21"),
    K("M22", "Macro\n22", "Macro\n22"),
    K("M23", "Macro\n23", "Macro\n23"),
    K("M24", "Macro\n24", "Macro\n24"),
    K("M25", "Macro\n25", "Macro\n25"),
    K("M26", "Macro\n26", "Macro\n26"),
    K("M27", "Macro\n27", "Macro\n27"),
    K("M28", "Macro\n28", "Macro\n28"),
    K("M29", "Macro\n29", "Macro\n29"),
    K("M30", "Macro\n30", "Macro\n30"),
    K("M31", "Macro\n31", "Macro\n31"),
    K("M32", "Macro\n32", "Macro\n32"),
    K("M33", "Macro\n33", "Macro\n33"),
    K("M34", "Macro\n34", "Macro\n34"),
    K("M35", "Macro\n35", "Macro\n35"),
    K("M36", "Macro\n36", "Macro\n36"),
    K("M37", "Macro\n37", "Macro\n37"),
    K("M38", "Macro\n38", "Macro\n38"),
    K("M39", "Macro\n39", "Macro\n39"),
    K("M40", "Macro\n40", "Macro\n40"),
    K("M41", "Macro\n41", "Macro\n41"),
    K("M42", "Macro\n42", "Macro\n42"),
    K("M43", "Macro\n43", "Macro\n43"),
    K("M44", "Macro\n44", "Macro\n44"),
    K("M45", "Macro\n45", "Macro\n45"),
    K("M46", "Macro\n46", "Macro\n46"),
    K("M47", "Macro\n47", "Macro\n47"),
    K("M48", "Macro\n48", "Macro\n48"),
    K("M49", "Macro\n49", "Macro\n49"),
    K("M50", "Macro\n50", "Macro\n50"),
    K("M51", "Macro\n51", "Macro\n51"),
    K("M52", "Macro\n52", "Macro\n52"),
    K("M53", "Macro\n53", "Macro\n53"),
    K("M54", "Macro\n54", "Macro\n54"),
    K("M55", "Macro\n55", "Macro\n55"),
    K("M56", "Macro\n56", "Macro\n56"),
    K("M57", "Macro\n57", "Macro\n57"),
    K("M58", "Macro\n58", "Macro\n58"),
    K("M59", "Macro\n59", "Macro\n59"),
    K("M60", "Macro\n60", "Macro\n60"),
    K("M61", "Macro\n61", "Macro\n61"),
    K("M62", "Macro\n62", "Macro\n62"),
    K("M63", "Macro\n63", "Macro\n63"),
    K("M64", "Macro\n64", "Macro\n64"),
    K("M65", "Macro\n65", "Macro\n65"),
    K("M66", "Macro\n66", "Macro\n66"),
    K("M67", "Macro\n67", "Macro\n67"),
    K("M68", "Macro\n68", "Macro\n68"),
    K("M69", "Macro\n69", "Macro\n69"),
    K("M70", "Macro\n70", "Macro\n70"),
    K("M71", "Macro\n71", "Macro\n71"),
    K("M72", "Macro\n72", "Macro\n72"),
    K("M73", "Macro\n73", "Macro\n73"),
    K("M74", "Macro\n74", "Macro\n74"),
    K("M75", "Macro\n75", "Macro\n75"),
    K("M76", "Macro\n76", "Macro\n76"),
    K("M77", "Macro\n77", "Macro\n77"),
    K("M78", "Macro\n78", "Macro\n78"),
    K("M79", "Macro\n79", "Macro\n79"),
    K("M80", "Macro\n80", "Macro\n80"),
    K("M81", "Macro\n81", "Macro\n81"),
    K("M82", "Macro\n82", "Macro\n82"),
    K("M83", "Macro\n83", "Macro\n83"),
    K("M84", "Macro\n84", "Macro\n84"),
    K("M85", "Macro\n85", "Macro\n85"),
    K("M86", "Macro\n86", "Macro\n86"),
    K("M87", "Macro\n87", "Macro\n87"),
    K("M88", "Macro\n88", "Macro\n88"),
    K("M89", "Macro\n89", "Macro\n89"),
    K("M90", "Macro\n90", "Macro\n90"),
    K("M91", "Macro\n91", "Macro\n91"),
    K("M92", "Macro\n92", "Macro\n92"),
    K("M93", "Macro\n93", "Macro\n93"),
    K("M94", "Macro\n94", "Macro\n94"),
    K("M95", "Macro\n95", "Macro\n95"),
    K("M96", "Macro\n96", "Macro\n96"),
    K("M97", "Macro\n97", "Macro\n97"),
    K("M98", "Macro\n98", "Macro\n98"),
    K("M99", "Macro\n99", "Macro\n99"),
    K("M100", "Macro\n100", "Macro\n100"),
    K("M101", "Macro\n101", "Macro\n101"),
    K("M102", "Macro\n102", "Macro\n102"),
    K("M103", "Macro\n103", "Macro\n103"),
    K("M104", "Macro\n104", "Macro\n104"),
    K("M105", "Macro\n105", "Macro\n105"),
    K("M106", "Macro\n106", "Macro\n106"),
    K("M107", "Macro\n107", "Macro\n107"),
    K("M108", "Macro\n108", "Macro\n108"),
    K("M109", "Macro\n109", "Macro\n109"),
    K("M110", "Macro\n110", "Macro\n110"),
    K("M111", "Macro\n111", "Macro\n111"),
    K("M112", "Macro\n112", "Macro\n112"),
    K("M113", "Macro\n113", "Macro\n113"),
    K("M114", "Macro\n114", "Macro\n114"),
    K("M115", "Macro\n115", "Macro\n115"),
    K("M116", "Macro\n116", "Macro\n116"),
    K("M117", "Macro\n117", "Macro\n117"),
    K("M118", "Macro\n118", "Macro\n118"),
    K("M119", "Macro\n119", "Macro\n119"),
    K("M120", "Macro\n120", "Macro\n120"),
    K("M121", "Macro\n121", "Macro\n121"),
    K("M122", "Macro\n122", "Macro\n122"),
    K("M123", "Macro\n123", "Macro\n123"),
    K("M124", "Macro\n124", "Macro\n124"),
    K("M125", "Macro\n125", "Macro\n125"),
    K("M126", "Macro\n126", "Macro\n126"),
    K("M127", "Macro\n127", "Macro\n127"),
    K("M128", "Macro\n128", "Macro\n128"),
    K("M129", "Macro\n129", "Macro\n129"),
    K("M130", "Macro\n130", "Macro\n130"),
    K("M131", "Macro\n131", "Macro\n131"),
    K("M132", "Macro\n132", "Macro\n132"),
    K("M133", "Macro\n133", "Macro\n133"),
    K("M134", "Macro\n134", "Macro\n134"),
    K("M135", "Macro\n135", "Macro\n135"),
    K("M136", "Macro\n136", "Macro\n136"),
    K("M137", "Macro\n137", "Macro\n137"),
    K("M138", "Macro\n138", "Macro\n138"),
    K("M139", "Macro\n139", "Macro\n139"),
    K("M140", "Macro\n140", "Macro\n140"),
    K("M141", "Macro\n141", "Macro\n141"),
    K("M142", "Macro\n142", "Macro\n142"),
    K("M143", "Macro\n143", "Macro\n143"),
    K("M144", "Macro\n144", "Macro\n144"),
    K("M145", "Macro\n145", "Macro\n145"),
    K("M146", "Macro\n146", "Macro\n146"),
    K("M147", "Macro\n147", "Macro\n147"),
    K("M148", "Macro\n148", "Macro\n148"),
    K("M149", "Macro\n149", "Macro\n149"),
    K("M150", "Macro\n150", "Macro\n150"),
    K("M151", "Macro\n151", "Macro\n151"),
    K("M152", "Macro\n152", "Macro\n152"),
    K("M153", "Macro\n153", "Macro\n153"),
    K("M154", "Macro\n154", "Macro\n154"),
    K("M155", "Macro\n155", "Macro\n155"),
    K("M156", "Macro\n156", "Macro\n156"),
    K("M157", "Macro\n157", "Macro\n157"),
    K("M158", "Macro\n158", "Macro\n158"),
    K("M159", "Macro\n159", "Macro\n159"),
    K("M160", "Macro\n160", "Macro\n160"),
    K("M161", "Macro\n161", "Macro\n161"),
    K("M162", "Macro\n162", "Macro\n162"),
    K("M163", "Macro\n163", "Macro\n163"),
    K("M164", "Macro\n164", "Macro\n164"),
    K("M165", "Macro\n165", "Macro\n165"),
    K("M166", "Macro\n166", "Macro\n166"),
    K("M167", "Macro\n167", "Macro\n167"),
    K("M168", "Macro\n168", "Macro\n168"),
    K("M169", "Macro\n169", "Macro\n169"),
    K("M170", "Macro\n170", "Macro\n170"),
    K("M171", "Macro\n171", "Macro\n171"),
    K("M172", "Macro\n172", "Macro\n172"),
    K("M173", "Macro\n173", "Macro\n173"),
    K("M174", "Macro\n174", "Macro\n174"),
    K("M175", "Macro\n175", "Macro\n175"),
    K("M176", "Macro\n176", "Macro\n176"),
    K("M177", "Macro\n177", "Macro\n177"),
    K("M178", "Macro\n178", "Macro\n178"),
    K("M179", "Macro\n179", "Macro\n179"),
    K("M180", "Macro\n180", "Macro\n180"),
    K("M181", "Macro\n181", "Macro\n181"),
    K("M182", "Macro\n182", "Macro\n182"),
    K("M183", "Macro\n183", "Macro\n183"),
    K("M184", "Macro\n184", "Macro\n184"),
    K("M185", "Macro\n185", "Macro\n185"),
    K("M186", "Macro\n186", "Macro\n186"),
    K("M187", "Macro\n187", "Macro\n187"),
    K("M188", "Macro\n188", "Macro\n188"),
    K("M189", "Macro\n189", "Macro\n189"),
    K("M190", "Macro\n190", "Macro\n190"),
    K("M191", "Macro\n191", "Macro\n191"),
    K("M192", "Macro\n192", "Macro\n192"),
    K("M193", "Macro\n193", "Macro\n193"),
    K("M194", "Macro\n194", "Macro\n194"),
    K("M195", "Macro\n195", "Macro\n195"),
    K("M196", "Macro\n196", "Macro\n196"),
    K("M197", "Macro\n197", "Macro\n197"),
    K("M198", "Macro\n198", "Macro\n198"),
    K("M199", "Macro\n199", "Macro\n199"),
    K("M200", "Macro\n200", "Macro\n200"),
    K("M201", "Macro\n201", "Macro\n201"),
    K("M202", "Macro\n202", "Macro\n202"),
    K("M203", "Macro\n203", "Macro\n203"),
    K("M204", "Macro\n204", "Macro\n204"),
    K("M205", "Macro\n205", "Macro\n205"),
    K("M206", "Macro\n206", "Macro\n206"),
    K("M207", "Macro\n207", "Macro\n207"),
    K("M208", "Macro\n208", "Macro\n208"),
    K("M209", "Macro\n209", "Macro\n209"),
    K("M210", "Macro\n210", "Macro\n210"),
    K("M211", "Macro\n211", "Macro\n211"),
    K("M212", "Macro\n212", "Macro\n212"),
    K("M213", "Macro\n213", "Macro\n213"),
    K("M214", "Macro\n214", "Macro\n214"),
    K("M215", "Macro\n215", "Macro\n215"),
    K("M216", "Macro\n216", "Macro\n216"),
    K("M217", "Macro\n217", "Macro\n217"),
    K("M218", "Macro\n218", "Macro\n218"),
    K("M219", "Macro\n219", "Macro\n219"),
    K("M220", "Macro\n220", "Macro\n220"),
    K("M221", "Macro\n221", "Macro\n221"),
    K("M222", "Macro\n222", "Macro\n222"),
    K("M223", "Macro\n223", "Macro\n223"),
    K("M224", "Macro\n224", "Macro\n224"),
    K("M225", "Macro\n225", "Macro\n225"),
    K("M226", "Macro\n226", "Macro\n226"),
    K("M227", "Macro\n227", "Macro\n227"),
    K("M228", "Macro\n228", "Macro\n228"),
    K("M229", "Macro\n229", "Macro\n229"),
    K("M230", "Macro\n230", "Macro\n230"),
    K("M231", "Macro\n231", "Macro\n231"),
    K("M232", "Macro\n232", "Macro\n232"),
    K("M233", "Macro\n233", "Macro\n233"),
    K("M234", "Macro\n234", "Macro\n234"),
    K("M235", "Macro\n235", "Macro\n235"),
    K("M236", "Macro\n236", "Macro\n236"),
    K("M237", "Macro\n237", "Macro\n237"),
    K("M238", "Macro\n238", "Macro\n238"),
    K("M239", "Macro\n239", "Macro\n239"),
    K("M240", "Macro\n240", "Macro\n240"),
    K("M241", "Macro\n241", "Macro\n241"),
    K("M242", "Macro\n242", "Macro\n242"),
    K("M243", "Macro\n243", "Macro\n243"),
    K("M244", "Macro\n244", "Macro\n244"),
    K("M245", "Macro\n245", "Macro\n245"),
    K("M246", "Macro\n246", "Macro\n246"),
    K("M247", "Macro\n247", "Macro\n247"),
    K("M248", "Macro\n248", "Macro\n248"),
    K("M249", "Macro\n249", "Macro\n249"),
    K("M250", "Macro\n250", "Macro\n250"),
    K("M251", "Macro\n251", "Macro\n251"),
    K("M252", "Macro\n252", "Macro\n252"),
    K("M253", "Macro\n253", "Macro\n253"),
    K("M254", "Macro\n254", "Macro\n254"),
    K("M255", "Macro\n255", "Macro\n255")
]


KEYCODES_MACRO_BASE = [
    K("DYN_REC_START1", "Dynamic\nMacro 1\nRec", "Dynamic Macro 1 Rec Start", alias=["DM_REC1"]),
    K("DYN_REC_START2", "Dynamic\nMacro 2\nRec", "Dynamic Macro 2 Rec Start", alias=["DM_REC2"]),    
    K("DYN_MACRO_PLAY1", "Dynamic\nMacro 1\nPlay", "Dynamic Macro 1 Play", alias=["DM_PLY1"]),
    K("DYN_MACRO_PLAY2", "Dynamic\nMacro 2\nPlay", "Dynamic Macro 2 Play", alias=["DM_PLY2"]),
    K("DYN_REC_STOP", "Stop\nMacro\nRec", "Dynamic Macro Rec Stop", alias=["DM_RSTP"]),
    K("QK_MACRO_ALL_OFF", "All\nMacros\nOff", "Stop all playing Vial macros"),
]

KEYCODES_EARTRAINER = []  # removed: ear trainer is outdated / managed on-device

KEYCODES_CHORDTRAINER = []  # removed: ear trainer is outdated / managed on-device

KEYCODES_MIDI = []

KEYCODES_MIDI_BASIC = [
    K("MI_C", "Midi\nC", "Midi send note C"),
    K("MI_Cs", "Midi\nC#/Dᵇ", "Midi send note C#/Dᵇ", alias=["MI_Db"]),
    K("MI_D", "Midi\nD", "Midi send note D"),
    K("MI_Ds", "Midi\nD#/Eᵇ", "Midi send note D#/Eᵇ", alias=["MI_Eb"]),
    K("MI_E", "Midi\nE", "Midi send note E"),
    K("MI_F", "Midi\nF", "Midi send note F"),
    K("MI_Fs", "Midi\nF#/Gᵇ", "Midi send note F#/Gᵇ", alias=["MI_Gb"]),
    K("MI_G", "Midi\nG", "Midi send note G"),
    K("MI_Gs", "Midi\nG#/Aᵇ", "Midi send note G#/Aᵇ", alias=["MI_Ab"]),
    K("MI_A", "Midi\nA", "Midi send note A"),
    K("MI_As", "Midi\nA#/Bᵇ", "Midi send note A#/Bᵇ", alias=["MI_Bb"]),
    K("MI_B", "Midi\nB", "Midi send note B"),

    K("MI_C_1", "Midi\nC₁", "Midi send note C₁"),
    K("MI_Cs_1", "Midi\nC#₁/Dᵇ₁", "Midi send note C#₁/Dᵇ₁", alias=["MI_Db_1"]),
    K("MI_D_1", "Midi\nD₁", "Midi send note D₁"),
    K("MI_Ds_1", "Midi\nD#₁/Eᵇ₁", "Midi send note D#₁/Eᵇ₁", alias=["MI_Eb_1"]),
    K("MI_E_1", "Midi\nE₁", "Midi send note E₁"),
    K("MI_F_1", "Midi\nF₁", "Midi send note F₁"),
    K("MI_Fs_1", "Midi\nF#₁/Gᵇ₁", "Midi send note F#₁/Gᵇ₁", alias=["MI_Gb_1"]),
    K("MI_G_1", "Midi\nG₁", "Midi send note G₁"),
    K("MI_Gs_1", "Midi\nG#₁/Aᵇ₁", "Midi send note G#₁/Aᵇ₁", alias=["MI_Ab_1"]),
    K("MI_A_1", "Midi\nA₁", "Midi send note A₁"),
    K("MI_As_1", "Midi\nA#₁/Bᵇ₁", "Midi send note A#₁/Bᵇ₁", alias=["MI_Bb_1"]),
    K("MI_B_1", "Midi\nB₁", "Midi send note B₁"),

    K("MI_C_2", "Midi\nC₂", "Midi send note C₂"),
    K("MI_Cs_2", "Midi\nC#₂/Dᵇ₂", "Midi send note C#₂/Dᵇ₂", alias=["MI_Db_2"]),
    K("MI_D_2", "Midi\nD₂", "Midi send note D₂"),
    K("MI_Ds_2", "Midi\nD#₂/Eᵇ₂", "Midi send note D#₂/Eᵇ₂", alias=["MI_Eb_2"]),
    K("MI_E_2", "Midi\nE₂", "Midi send note E₂"),
    K("MI_F_2", "Midi\nF₂", "Midi send note F₂"),
    K("MI_Fs_2", "Midi\nF#₂/Gᵇ₂", "Midi send note F#₂/Gᵇ₂", alias=["MI_Gb_2"]),
    K("MI_G_2", "Midi\nG₂", "Midi send note G₂"),
    K("MI_Gs_2", "Midi\nG#₂/Aᵇ₂", "Midi send note G#₂/Aᵇ₂", alias=["MI_Ab_2"]),
    K("MI_A_2", "Midi\nA₂", "Midi send note A₂"),
    K("MI_As_2", "Midi\nA#₂/Bᵇ₂", "Midi send note A#₂/Bᵇ₂", alias=["MI_Bb_2"]),
    K("MI_B_2", "Midi\nB₂", "Midi send note B₂"),

    K("MI_C_3", "Midi\nC₃", "Midi send note C₃"),
    K("MI_Cs_3", "Midi\nC#₃/Dᵇ₃", "Midi send note C#₃/Dᵇ₃", alias=["MI_Db_3"]),
    K("MI_D_3", "Midi\nD₃", "Midi send note D₃"),
    K("MI_Ds_3", "Midi\nD#₃/Eᵇ₃", "Midi send note D#₃/Eᵇ₃", alias=["MI_Eb_3"]),
    K("MI_E_3", "Midi\nE₃", "Midi send note E₃"),
    K("MI_F_3", "Midi\nF₃", "Midi send note F₃"),
    K("MI_Fs_3", "Midi\nF#₃/Gᵇ₃", "Midi send note F#₃/Gᵇ₃", alias=["MI_Gb_3"]),
    K("MI_G_3", "Midi\nG₃", "Midi send note G₃"),
    K("MI_Gs_3", "Midi\nG#₃/Aᵇ₃", "Midi send note G#₃/Aᵇ₃", alias=["MI_Ab_3"]),
    K("MI_A_3", "Midi\nA₃", "Midi send note A₃"),
    K("MI_As_3", "Midi\nA#₃/Bᵇ₃", "Midi send note A#₃/Bᵇ₃", alias=["MI_Bb_3"]),
    K("MI_B_3", "Midi\nB₃", "Midi send note B₃"),

    K("MI_C_4", "Midi\nC₄", "Midi send note C₄"),
    K("MI_Cs_4", "Midi\nC#₄/Dᵇ₄", "Midi send note C#₄/Dᵇ₄", alias=["MI_Db_4"]),
    K("MI_D_4", "Midi\nD₄", "Midi send note D₄"),
    K("MI_Ds_4", "Midi\nD#₄/Eᵇ₄", "Midi send note D#₄/Eᵇ₄", alias=["MI_Eb_4"]),
    K("MI_E_4", "Midi\nE₄", "Midi send note E₄"),
    K("MI_F_4", "Midi\nF₄", "Midi send note F₄"),
    K("MI_Fs_4", "Midi\nF#₄/Gᵇ₄", "Midi send note F#₄/Gᵇ₄", alias=["MI_Gb_4"]),
    K("MI_G_4", "Midi\nG₄", "Midi send note G₄"),
    K("MI_Gs_4", "Midi\nG#₄/Aᵇ₄", "Midi send note G#₄/Aᵇ₄", alias=["MI_Ab_4"]),
    K("MI_A_4", "Midi\nA₄", "Midi send note A₄"),
    K("MI_As_4", "Midi\nA#₄/Bᵇ₄", "Midi send note A#₄/Bᵇ₄", alias=["MI_Bb_4"]),
    K("MI_B_4", "Midi\nB₄", "Midi send note B₄"),

    K("MI_C_5", "Midi\nC₅", "Midi send note C₅"),
    K("MI_Cs_5", "Midi\nC#₅/Dᵇ₅", "Midi send note C#₅/Dᵇ₅", alias=["MI_Db_5"]),
    K("MI_D_5", "Midi\nD₅", "Midi send note D₅"),
    K("MI_Ds_5", "Midi\nD#₅/Eᵇ₅", "Midi send note D#₅/Eᵇ₅", alias=["MI_Eb_5"]),
    K("MI_E_5", "Midi\nE₅", "Midi send note E₅"),
    K("MI_F_5", "Midi\nF₅", "Midi send note F₅"),
    K("MI_Fs_5", "Midi\nF#₅/Gᵇ₅", "Midi send note F#₅/Gᵇ₅", alias=["MI_Gb_5"]),
    K("MI_G_5", "Midi\nG₅", "Midi send note G₅"),
    K("MI_Gs_5", "Midi\nG#₅/Aᵇ₅", "Midi send note G#₅/Aᵇ₅", alias=["MI_Ab_5"]),
    K("MI_A_5", "Midi\nA₅", "Midi send note A₅"),
    K("MI_As_5", "Midi\nA#₅/Bᵇ₅", "Midi send note A#₅/Bᵇ₅", alias=["MI_Bb_5"]),
    K("MI_B_5", "Midi\nB₅", "Midi send note B₅"),

    K("MI_ALLOFF", "All\nNotes\nOff", "Midi send all notes OFF"),
    K("MI_SUS", "Sustain\nPedal", "Midi Sustain"),
    K("KC_NO", "", "None"),
    K("MI_CHORD_99", "Smart\nChord", "Press QuickChord"),  
]

KEYCODES_MIDI_SPLIT = [
        K("MI_SPLIT_C", "KS\nC", "Midi send note C"),
        K("MI_SPLIT_Cs", "KS\nC#/Dᵇ", "Midi send note C#/Dᵇ", alias=["MI_SPLIT_Db"]),
        K("MI_SPLIT_D", "KS\nD", "Midi send note D"),
        K("MI_SPLIT_Ds", "KS\nD#/Eᵇ", "Midi send note D#/Eᵇ", alias=["MI_SPLIT_Eb"]),
        K("MI_SPLIT_E", "KS\nE", "Midi send note E"),
        K("MI_SPLIT_F", "KS\nF", "Midi send note F"),
        K("MI_SPLIT_Fs", "KS\nF#/Gᵇ", "Midi send note F#/Gᵇ", alias=["MI_SPLIT_Gb"]),
        K("MI_SPLIT_G", "KS\nG", "Midi send note G"),
        K("MI_SPLIT_Gs", "KS\nG#/Aᵇ", "Midi send note G#/Aᵇ", alias=["MI_SPLIT_Ab"]),
        K("MI_SPLIT_A", "KS\nA", "Midi send note A"),
        K("MI_SPLIT_As", "KS\nA#/Bᵇ", "Midi send note A#/Bᵇ", alias=["MI_SPLIT_Bb"]),
        K("MI_SPLIT_B", "KS\nB", "Midi send note B"),

        K("MI_SPLIT_C_1", "KS\nC₁", "Midi send note C₁"),
        K("MI_SPLIT_Cs_1", "KS\nC#₁/Dᵇ₁", "Midi send note C#₁/Dᵇ₁", alias=["MI_SPLIT_Db_1"]),
        K("MI_SPLIT_D_1", "KS\nD₁", "Midi send note D₁"),
        K("MI_SPLIT_Ds_1", "KS\nD#₁/Eᵇ₁", "Midi send note D#₁/Eᵇ₁", alias=["MI_SPLIT_Eb_1"]),
        K("MI_SPLIT_E_1", "KS\nE₁", "Midi send note E₁"),
        K("MI_SPLIT_F_1", "KS\nF₁", "Midi send note F₁"),
        K("MI_SPLIT_Fs_1", "KS\nF#₁/Gᵇ₁", "Midi send note F#₁/Gᵇ₁", alias=["MI_SPLIT_Gb_1"]),
        K("MI_SPLIT_G_1", "KS\nG₁", "Midi send note G₁"),
        K("MI_SPLIT_Gs_1", "KS\nG#₁/Aᵇ₁", "Midi send note G#₁/Aᵇ₁", alias=["MI_SPLIT_Ab_1"]),
        K("MI_SPLIT_A_1", "KS\nA₁", "Midi send note A₁"),
        K("MI_SPLIT_As_1", "KS\nA#₁/Bᵇ₁", "Midi send note A#₁/Bᵇ₁", alias=["MI_SPLIT_Bb_1"]),
        K("MI_SPLIT_B_1", "KS\nB₁", "Midi send note B₁"),

        K("MI_SPLIT_C_2", "KS\nC₂", "Midi send note C₂"),
        K("MI_SPLIT_Cs_2", "KS\nC#₂/Dᵇ₂", "Midi send note C#₂/Dᵇ₂", alias=["MI_SPLIT_Db_2"]),
        K("MI_SPLIT_D_2", "KS\nD₂", "Midi send note D₂"),
        K("MI_SPLIT_Ds_2", "KS\nD#₂/Eᵇ₂", "Midi send note D#₂/Eᵇ₂", alias=["MI_SPLIT_Eb_2"]),
        K("MI_SPLIT_E_2", "KS\nE₂", "Midi send note E₂"),
        K("MI_SPLIT_F_2", "KS\nF₂", "Midi send note F₂"),
        K("MI_SPLIT_Fs_2", "KS\nF#₂/Gᵇ₂", "Midi send note F#₂/Gᵇ₂", alias=["MI_SPLIT_Gb_2"]),
        K("MI_SPLIT_G_2", "KS\nG₂", "Midi send note G₂"),
        K("MI_SPLIT_Gs_2", "KS\nG#₂/Aᵇ₂", "Midi send note G#₂/Aᵇ₂", alias=["MI_SPLIT_Ab_2"]),
        K("MI_SPLIT_A_2", "KS\nA₂", "Midi send note A₂"),
        K("MI_SPLIT_As_2", "KS\nA#₂/Bᵇ₂", "Midi send note A#₂/Bᵇ₂", alias=["MI_SPLIT_Bb_2"]),
        K("MI_SPLIT_B_2", "KS\nB₂", "Midi send note B₂"),

        K("MI_SPLIT_C_3", "KS\nC₃", "Midi send note C₃"),
        K("MI_SPLIT_Cs_3", "KS\nC#₃/Dᵇ₃", "Midi send note C#₃/Dᵇ₃", alias=["MI_SPLIT_Db_3"]),
        K("MI_SPLIT_D_3", "KS\nD₃", "Midi send note D₃"),
        K("MI_SPLIT_Ds_3", "KS\nD#₃/Eᵇ₃", "Midi send note D#₃/Eᵇ₃", alias=["MI_SPLIT_Eb_3"]),
        K("MI_SPLIT_E_3", "KS\nE₃", "Midi send note E₃"),
        K("MI_SPLIT_F_3", "KS\nF₃", "Midi send note F₃"),
        K("MI_SPLIT_Fs_3", "KS\nF#₃/Gᵇ₃", "Midi send note F#₃/Gᵇ₃", alias=["MI_SPLIT_Gb_3"]),
        K("MI_SPLIT_G_3", "KS\nG₃", "Midi send note G₃"),
        K("MI_SPLIT_Gs_3", "KS\nG#₃/Aᵇ₃", "Midi send note G#₃/Aᵇ₃", alias=["MI_SPLIT_Ab_3"]),
        K("MI_SPLIT_A_3", "KS\nA₃", "Midi send note A₃"),
        K("MI_SPLIT_As_3", "KS\nA#₃/Bᵇ₃", "Midi send note A#₃/Bᵇ₃", alias=["MI_SPLIT_Bb_3"]),
        K("MI_SPLIT_B_3", "KS\nB₃", "Midi send note B₃"),

        K("MI_SPLIT_C_4", "KS\nC₄", "Midi send note C₄"),
        K("MI_SPLIT_Cs_4", "KS\nC#₄/Dᵇ₄", "Midi send note C#₄/Dᵇ₄", alias=["MI_SPLIT_Db_4"]),
        K("MI_SPLIT_D_4", "KS\nD₄", "Midi send note D₄"),
        K("MI_SPLIT_Ds_4", "KS\nD#₄/Eᵇ₄", "Midi send note D#₄/Eᵇ₄", alias=["MI_SPLIT_Eb_4"]),
        K("MI_SPLIT_E_4", "KS\nE₄", "Midi send note E₄"),
        K("MI_SPLIT_F_4", "KS\nF₄", "Midi send note F₄"),
        K("MI_SPLIT_Fs_4", "KS\nF#₄/Gᵇ₄", "Midi send note F#₄/Gᵇ₄", alias=["MI_SPLIT_Gb_4"]),
        K("MI_SPLIT_G_4", "KS\nG₄", "Midi send note G₄"),
        K("MI_SPLIT_Gs_4", "KS\nG#₄/Aᵇ₄", "Midi send note G#₄/Aᵇ₄", alias=["MI_SPLIT_Ab_4"]),
        K("MI_SPLIT_A_4", "KS\nA₄", "Midi send note A₄"),
        K("MI_SPLIT_As_4", "KS\nA#₄/Bᵇ₄", "Midi send note A#₄/Bᵇ₄", alias=["MI_SPLIT_Bb_4"]),
        K("MI_SPLIT_B_4", "KS\nB₄", "Midi send note B₄"),

        K("MI_SPLIT_C_5", "KS\nC₅", "Midi send note C₅"),
        K("MI_SPLIT_Cs_5", "KS\nC#₅/Dᵇ₅", "Midi send note C#₅/Dᵇ₅", alias=["MI_SPLIT_Db_5"]),
        K("MI_SPLIT_D_5", "KS\nD₅", "Midi send note D₅"),
        K("MI_SPLIT_Ds_5", "KS\nD#₅/Eᵇ₅", "Midi send note D#₅/Eᵇ₅", alias=["MI_SPLIT_Eb_5"]),
        K("MI_SPLIT_E_5", "KS\nE₅", "Midi send note E₅"),
        K("MI_SPLIT_F_5", "KS\nF₅", "Midi send note F₅"),
        K("MI_SPLIT_Fs_5", "KS\nF#₅/Gᵇ₅", "Midi send note F#₅/Gᵇ₅", alias=["MI_SPLIT_Gb_5"]),
        K("MI_SPLIT_G_5", "KS\nG₅", "Midi send note G₅"),
        K("MI_SPLIT_Gs_5", "KS\nG#₅/Aᵇ₅", "Midi send note G#₅/Aᵇ₅", alias=["MI_SPLIT_Ab_5"]),
        K("MI_SPLIT_A_5", "KS\nA₅", "Midi send note A₅"),
        K("MI_SPLIT_As_5", "KS\nA#₅/Bᵇ₅", "Midi send note A#₅/Bᵇ₅", alias=["MI_SPLIT_Bb_5"]),
        K("MI_SPLIT_B_5", "KS\nB₅", "Midi send note B₅"),

        K("MI_ALLOFF", "All\nNotes\nOff", "Midi send all notes OFF"),
        K("MI_SUS", "Sustain\nPedal", "Midi Sustain"),
        K("KC_NO", "", "None"),
        K("MI_CHORD_99", "Smart\nChord", "Press QuickChord"),  
        K("KS_CHAN_DOWN", "KS\nChannel▼", "Midi set key split channel Down"),
        K("KS_CHAN_UP", "KS\nChannel▲", "Midi set key split channel UP"),
        K("KS2_CHAN_DOWN", "TS\nChannel▼", "Midi set key split channel Down"),
        K("KS2_CHAN_UP", "TS\nChannel▲", "Midi set key split channel UP"),
        K("MI_VELOCITY2_DOWN", "KS\nVelocity▼", "Midi set key split channel Down"),
        K("MI_VELOCITY2_UP", "KS\nVelocity▲", "Midi set key split channel UP"),
        K("MI_VELOCITY3_DOWN", "TS\nVelocity▼", "Midi set key split channel Down"),
        K("MI_VELOCITY3_UP", "TS\nVelocity▲", "Midi set key split channel UP"),
        K("MI_TRANSPOSE2_DOWN", "KS\nTranspose▼", "Midi set key split channel Down"),
        K("MI_TRANSPOSE2_UP", "KS\nTranspose▲", "Midi set key split channel UP"),
        K("MI_TRANSPOSE3_DOWN", "TS\nTranspose▼", "Midi set key split channel Down"),
        K("MI_TRANSPOSE3_UP", "TS\nTranspose▲", "Midi set key split channel UP"),
        K("MI_OCTAVE2_DOWN", "KS\nOctave▼", "Midi set key split channel Down"),
        K("MI_OCTAVE2_UP", "KS\nOctave▲", "Midi set key split channel UP"),
        K("MI_OCTAVE3_DOWN", "TS\nOctave▼", "Midi set key split channel Down"),
        K("MI_OCTAVE3_UP", "TS\nOctave▲", "Midi set key split channel UP"),
]

KEYCODES_MIDI_SPLIT_BUTTONS = [        
        K("KS_CHAN_UP", "KS\nChannel\n▲", "Midi set key split channel UP"),       
        K("KS2_CHAN_UP", "TS\nChannel\n▲", "Midi set key split channel UP"),       
        K("MI_VELOCITY2_UP", "KS\nVelocity\n▲", "Midi set key split channel UP"),       
        K("MI_VELOCITY3_UP", "TS\nVelocity\n▲", "Midi set key split channel UP"),       
        K("MI_TRANSPOSE2_UP", "KS\nTranspose\n▲", "Midi set key split channel UP"),        
        K("MI_TRANSPOSE3_UP", "TS\nTranspose\n▲", "Midi set key split channel UP"),      
        K("MI_OCTAVE2_UP", "KS\nOctave\n▲", "Midi set key split channel UP"),       
        K("MI_OCTAVE3_UP", "TS\nOctave\n▲", "Midi set key split channel UP"),        
        K("KS_CHAN_DOWN", "KS\nChannel\n▼", "Midi set key split channel Down"),
        K("KS2_CHAN_DOWN", "TS\nChannel\n▼", "Midi set key split channel Down"),
        K("MI_VELOCITY2_DOWN", "KS\nVelocity\n▼", "Midi set key split channel Down"),
        K("MI_VELOCITY3_DOWN", "TS\nVelocity\n▼", "Midi set key split channel Down"),
        K("MI_TRANSPOSE2_DOWN", "KS\nTranspose\n▼", "Midi set key split channel Down"),
        K("MI_TRANSPOSE3_DOWN", "TS\nTranspose\n▼", "Midi set key split channel Down"),
        K("MI_OCTAVE2_DOWN", "KS\nOctave\n▼", "Midi set key split channel Down"),
        K("MI_OCTAVE3_DOWN", "TS\nOctave\n▼", "Midi set key split channel Down"),
]

KEYCODES_MIDI_SPLIT2 = [
        K("MI_SPLIT2_C", "TS\nC", "Midi send note C"),
        K("MI_SPLIT2_Cs", "TS\nC#/Dᵇ", "Midi send note C#/Dᵇ", alias=["MI_SPLIT2_Db"]),
        K("MI_SPLIT2_D", "TS\nD", "Midi send note D"),
        K("MI_SPLIT2_Ds", "TS\nD#/Eᵇ", "Midi send note D#/Eᵇ", alias=["MI_SPLIT2_Eb"]),
        K("MI_SPLIT2_E", "TS\nE", "Midi send note E"),
        K("MI_SPLIT2_F", "TS\nF", "Midi send note F"),
        K("MI_SPLIT2_Fs", "TS\nF#/Gᵇ", "Midi send note F#/Gᵇ", alias=["MI_SPLIT2_Gb"]),
        K("MI_SPLIT2_G", "TS\nG", "Midi send note G"),
        K("MI_SPLIT2_Gs", "TS\nG#/Aᵇ", "Midi send note G#/Aᵇ", alias=["MI_SPLIT2_Ab"]),
        K("MI_SPLIT2_A", "TS\nA", "Midi send note A"),
        K("MI_SPLIT2_As", "TS\nA#/Bᵇ", "Midi send note A#/Bᵇ", alias=["MI_SPLIT2_Bb"]),
        K("MI_SPLIT2_B", "TS\nB", "Midi send note B"),

        K("MI_SPLIT2_C_1", "TS\nC₁", "Midi send note C₁"),
        K("MI_SPLIT2_Cs_1", "TS\nC#₁/Dᵇ₁", "Midi send note C#₁/Dᵇ₁", alias=["MI_SPLIT2_Db_1"]),
        K("MI_SPLIT2_D_1", "TS\nD₁", "Midi send note D₁"),
        K("MI_SPLIT2_Ds_1", "TS\nD#₁/Eᵇ₁", "Midi send note D#₁/Eᵇ₁", alias=["MI_SPLIT2_Eb_1"]),
        K("MI_SPLIT2_E_1", "TS\nE₁", "Midi send note E₁"),
        K("MI_SPLIT2_F_1", "TS\nF₁", "Midi send note F₁"),
        K("MI_SPLIT2_Fs_1", "TS\nF#₁/Gᵇ₁", "Midi send note F#₁/Gᵇ₁", alias=["MI_SPLIT2_Gb_1"]),
        K("MI_SPLIT2_G_1", "TS\nG₁", "Midi send note G₁"),
        K("MI_SPLIT2_Gs_1", "TS\nG#₁/Aᵇ₁", "Midi send note G#₁/Aᵇ₁", alias=["MI_SPLIT2_Ab_1"]),
        K("MI_SPLIT2_A_1", "TS\nA₁", "Midi send note A₁"),
        K("MI_SPLIT2_As_1", "TS\nA#₁/Bᵇ₁", "Midi send note A#₁/Bᵇ₁", alias=["MI_SPLIT2_Bb_1"]),
        K("MI_SPLIT2_B_1", "TS\nB₁", "Midi send note B₁"),

        K("MI_SPLIT2_C_2", "TS\nC₂", "Midi send note C₂"),
        K("MI_SPLIT2_Cs_2", "TS\nC#₂/Dᵇ₂", "Midi send note C#₂/Dᵇ₂", alias=["MI_SPLIT2_Db_2"]),
        K("MI_SPLIT2_D_2", "TS\nD₂", "Midi send note D₂"),
        K("MI_SPLIT2_Ds_2", "TS\nD#₂/Eᵇ₂", "Midi send note D#₂/Eᵇ₂", alias=["MI_SPLIT2_Eb_2"]),
        K("MI_SPLIT2_E_2", "TS\nE₂", "Midi send note E₂"),
        K("MI_SPLIT2_F_2", "TS\nF₂", "Midi send note F₂"),
        K("MI_SPLIT2_Fs_2", "TS\nF#₂/Gᵇ₂", "Midi send note F#₂/Gᵇ₂", alias=["MI_SPLIT2_Gb_2"]),
        K("MI_SPLIT2_G_2", "TS\nG₂", "Midi send note G₂"),
        K("MI_SPLIT2_Gs_2", "TS\nG#₂/Aᵇ₂", "Midi send note G#₂/Aᵇ₂", alias=["MI_SPLIT2_Ab_2"]),
        K("MI_SPLIT2_A_2", "TS\nA₂", "Midi send note A₂"),
        K("MI_SPLIT2_As_2", "TS\nA#₂/Bᵇ₂", "Midi send note A#₂/Bᵇ₂", alias=["MI_SPLIT2_Bb_2"]),
        K("MI_SPLIT2_B_2", "TS\nB₂", "Midi send note B₂"),

        K("MI_SPLIT2_C_3", "TS\nC₃", "Midi send note C₃"),
        K("MI_SPLIT2_Cs_3", "TS\nC#₃/Dᵇ₃", "Midi send note C#₃/Dᵇ₃", alias=["MI_SPLIT2_Db_3"]),
        K("MI_SPLIT2_D_3", "TS\nD₃", "Midi send note D₃"),
        K("MI_SPLIT2_Ds_3", "TS\nD#₃/Eᵇ₃", "Midi send note D#₃/Eᵇ₃", alias=["MI_SPLIT2_Eb_3"]),
        K("MI_SPLIT2_E_3", "TS\nE₃", "Midi send note E₃"),
        K("MI_SPLIT2_F_3", "TS\nF₃", "Midi send note F₃"),
        K("MI_SPLIT2_Fs_3", "TS\nF#₃/Gᵇ₃", "Midi send note F#₃/Gᵇ₃", alias=["MI_SPLIT2_Gb_3"]),
        K("MI_SPLIT2_G_3", "TS\nG₃", "Midi send note G₃"),
        K("MI_SPLIT2_Gs_3", "TS\nG#₃/Aᵇ₃", "Midi send note G#₃/Aᵇ₃", alias=["MI_SPLIT2_Ab_3"]),
        K("MI_SPLIT2_A_3", "TS\nA₃", "Midi send note A₃"),
        K("MI_SPLIT2_As_3", "TS\nA#₃/Bᵇ₃", "Midi send note A#₃/Bᵇ₃", alias=["MI_SPLIT2_Bb_3"]),
        K("MI_SPLIT2_B_3", "TS\nB₃", "Midi send note B₃"),

        K("MI_SPLIT2_C_4", "TS\nC₄", "Midi send note C₄"),
        K("MI_SPLIT2_Cs_4", "TS\nC#₄/Dᵇ₄", "Midi send note C#₄/Dᵇ₄", alias=["MI_SPLIT2_Db_4"]),
        K("MI_SPLIT2_D_4", "TS\nD₄", "Midi send note D₄"),
        K("MI_SPLIT2_Ds_4", "TS\nD#₄/Eᵇ₄", "Midi send note D#₄/Eᵇ₄", alias=["MI_SPLIT2_Eb_4"]),
        K("MI_SPLIT2_E_4", "TS\nE₄", "Midi send note E₄"),
        K("MI_SPLIT2_F_4", "TS\nF₄", "Midi send note F₄"),
        K("MI_SPLIT2_Fs_4", "TS\nF#₄/Gᵇ₄", "Midi send note F#₄/Gᵇ₄", alias=["MI_SPLIT2_Gb_4"]),
        K("MI_SPLIT2_G_4", "TS\nG₄", "Midi send note G₄"),
        K("MI_SPLIT2_Gs_4", "TS\nG#₄/Aᵇ₄", "Midi send note G#₄/Aᵇ₄", alias=["MI_SPLIT2_Ab_4"]),
        K("MI_SPLIT2_A_4", "TS\nA₄", "Midi send note A₄"),
        K("MI_SPLIT2_As_4", "TS\nA#₄/Bᵇ₄", "Midi send note A#₄/Bᵇ₄", alias=["MI_SPLIT2_Bb_4"]),
        K("MI_SPLIT2_B_4", "TS\nB₄", "Midi send note B₄"),

        K("MI_SPLIT2_C_5", "TS\nC₅", "Midi send note C₅"),
        K("MI_SPLIT2_Cs_5", "TS\nC#₅/Dᵇ₅", "Midi send note C#₅/Dᵇ₅", alias=["MI_SPLIT2_Db_5"]),
        K("MI_SPLIT2_D_5", "TS\nD₅", "Midi send note D₅"),
        K("MI_SPLIT2_Ds_5", "TS\nD#₅/Eᵇ₅", "Midi send note D#₅/Eᵇ₅", alias=["MI_SPLIT2_Eb_5"]),
        K("MI_SPLIT2_E_5", "TS\nE₅", "Midi send note E₅"),
        K("MI_SPLIT2_F_5", "TS\nF₅", "Midi send note F₅"),
        K("MI_SPLIT2_Fs_5", "TS\nF#₅/Gᵇ₅", "Midi send note F#₅/Gᵇ₅", alias=["MI_SPLIT2_Gb_5"]),
        K("MI_SPLIT2_G_5", "TS\nG₅", "Midi send note G₅"),
        K("MI_SPLIT2_Gs_5", "TS\nG#₅/Aᵇ₅", "Midi send note G#₅/Aᵇ₅", alias=["MI_SPLIT2_Ab_5"]),
        K("MI_SPLIT2_A_5", "TS\nA₅", "Midi send note A₅"),
        K("MI_SPLIT2_As_5", "TS\nA#₅/Bᵇ₅", "Midi send note A#₅/Bᵇ₅", alias=["MI_SPLIT2_Bb_5"]),
        K("MI_SPLIT2_B_5", "TS\nB₅", "Midi send note B₅"),

        K("MI_ALLOFF", "All\nNotes\nOff", "Midi send all notes OFF"),
        K("MI_SUS", "Sustain\nPedal", "Midi Sustain"),
        K("KC_NO", "", "None"),
        K("MI_CHORD_99", "Smart\nChord", "Press QuickChord"),  
]

KEYCODES_MIDI_ADVANCED = [
    K("MI_TRNSU", "Transpose\n▲", "Midi increase transposition"),
    K("MI_OCTU", "Octave\n▲", "Midi move up an octave"),  
    K("MI_VELOCITY_UP", "Velocity\n▲", "Midi increase velocity"),  
    K("MI_CHU", "Channel\n▲", "Midi increase channel"),   
    K("MI_BENDU", "Pitch\nBend ▲", "Midi bend pitch up"),   
    K("MI_MODSU", "Mod\nSpeed ▲", "Midi increase modulation speed"), 
    K("MI_PROG_UP", "Program\n▲", "Program up")  ,  
    K("MI_BANK_UP", "Bank\n▲", "Bank up"),     
    K("MI_TRNSD", "Transpose\n▼", "Midi decrease transposition"),  
    K("MI_OCTD", "Octave\n▼", "Midi move down an octave"),
    K("MI_VELOCITY_DOWN", "Velocity\n▼", "Midi decrease velocity"), 
    K("MI_CHD", "Channel\n▼", "Midi decrease channel"),
    K("MI_BENDD", "Pitch\nBend ▼", "Midi bend pitch down"),
    K("MI_MODSD", "Mod\nSpeed ▼", "Midi decrease modulation speed"), 
    K("MI_PROG_DWN", "Program\n▼", "Program down"),
    K("MI_BANK_DWN", "Bank\n▼", "Bank down"),
    K("MI_ALLOFF", "All\nNotes\nOff", "Midi send all notes OFF"),    
    K("MI_PORT", "Portmento", "Midi Portmento"),
    K("MI_SOST", "Sostenuto", "Midi Sostenuto"),
    K("MI_LEG", "Legato", "Midi Legato"),    
    K("MI_MOD", "Modulation", "Midi Modulation"),
    K("MI_SUS", "Sustain\nPedal", "Midi Sustain"),
    K("MI_SOFT", "Soft\nSPedal", "Midi Soft Pedal"),
    K("OLED_1", "Screen\nKeyboard\nShift", "Momentarily turn on layer when pressed"),
    K("MI_TAP", "Set\nBPM", "Set BPM"),
    K("BPM_UP", "BPM\nUp", "Set BPM"),
    K("BPM_DOWN", "BPM\nDown", "Set BPM"),
]

KEYCODES_MIDI_PEDAL = [
    K("MI_ALLOFF", "All\nNotes\nOff", "Midi send all notes OFF"),
    K("MI_SUS", "Sustain\nPedal", "Midi Sustain"),
]

KEYCODES_MIDI_INOUT = [
    # MIDI Routing Controls - Both inputs have same 4 modes:
    # PROC (process all through QMK), THRU (forward to both outputs), CLK (process clock only), IGN (ignore)
    K("MIDI_IN_MODE_TOG", "HW MIDI\nRoute", "Toggle Hardware MIDI IN routing: PROC→THRU→CLK→IGN"),
    K("USB_MIDI_MODE_TOG", "USB MIDI\nRoute", "Toggle USB MIDI routing: PROC→THRU→CLK→IGN"),
    K("MIDI_CLOCK_SRC_TOG", "Clock\nSource", "Toggle MIDI clock source: LOCAL→USB→MIDI_IN"),

    # Override Toggles
    K("MI_CH_OVR_TOG", "Channel\nOverride", "Toggle channel override"),
    K("MI_VEL_OVR_TOG", "Velocity\nOverride", "Toggle velocity override"),
    K("MI_TRNS_OVR_TOG", "Transpose\nOverride", "Toggle transpose override"),

    # Additional MIDI Toggles
    K("MI_TRUE_SUS_TOG", "True\nSustain", "Toggle true sustain mode"),
    K("MI_CC_LOOP_TOG", "CC Loop\nRec", "Toggle CC loop recording"),
]

# LEGACY (no longer shown in the picker): the main-zone Octave selector was
# condensed, together with the Key selector, into the single -64..+64
# KEYCODES_MIDI_TRANSPOSE_SELECT band below. The K() entries stay registered
# so saved layouts using the old keycodes still load and display.
KEYCODES_MIDI_OCTAVE = [
    K("MI_OCT_N2", "Octave\n-2", "Midi set octave to -2"),
    K("MI_OCT_N1", "Octave\n-1", "Midi set octave to -1"),
    K("MI_OCT_0", "Octave\n 0", "Midi set octave to 0"),
    K("MI_OCT_1", "Octave\n+1", "Midi set octave to 1"),
    K("MI_OCT_2", "Octave\n+2", "Midi set octave to 2"),
    K("MI_OCT_3", "Octave\n+3", "Midi set octave to 3"),
    K("MI_OCT_4", "Octave\n+4", "Midi set octave to 4"),
    K("MI_OCT_5", "Octave\n+5", "Midi set octave to 5"),
    K("MI_OCT_6", "Octave\n+6", "Midi set octave to 6"),
    K("MI_OCT_7", "Octave\n+7", "Midi set octave to 7"),
] 

KEYCODES_MIDI_OCTAVE2 = [
    K("MI_OCTAVE2_N2", "KS\nOctave\n-2", "Midi set octave to -2"),
    K("MI_OCTAVE2_N1", "KS\nOctave\n-1", "Midi set octave to -1"),
    K("MI_OCTAVE2_0", "KS\nOctave\n 0", "Midi set octave to 0"),
    K("MI_OCTAVE2_1", "KS\nOctave\n+1", "Midi set octave to 1"),
    K("MI_OCTAVE2_2", "KS\nOctave\n+2", "Midi set octave to 2"),
    K("MI_OCTAVE2_3", "KS\nOctave\n+3", "Midi set octave to 3"),
    K("MI_OCTAVE2_4", "KS\nOctave\n+4", "Midi set octave to 4"),
    K("MI_OCTAVE2_5", "KS\nOctave\n+5", "Midi set octave to 5"),
    K("MI_OCTAVE2_6", "KS\nOctave\n+6", "Midi set octave to 6"),
    K("MI_OCTAVE2_7", "KS\nOctave\n+7", "Midi set octave to 7"),
] 

KEYCODES_MIDI_OCTAVE3 = [
    K("MI_OCTAVE3_N2", "TS\nOctave\n-2", "Midi set octave to -2"),
    K("MI_OCTAVE3_N1", "TS\nOctave\n-1", "Midi set octave to -1"),
    K("MI_OCTAVE3_0", "TS\nOctave\n 0", "Midi set octave to 0"),
    K("MI_OCTAVE3_1", "TS\nOctave\n+1", "Midi set octave to 1"),
    K("MI_OCTAVE3_2", "TS\nOctave\n+2", "Midi set octave to 2"),
    K("MI_OCTAVE3_3", "TS\nOctave\n+3", "Midi set octave to 3"),
    K("MI_OCTAVE3_4", "TS\nOctave\n+4", "Midi set octave to 4"),
    K("MI_OCTAVE3_5", "TS\nOctave\n+5", "Midi set octave to 5"),
    K("MI_OCTAVE3_6", "TS\nOctave\n+6", "Midi set octave to 6"),
    K("MI_OCTAVE3_7", "TS\nOctave\n+7", "Midi set octave to 7"),
] 

KEYCODES_MIDI_UPDOWN = [
    K("MI_TRNSU", "Transpose\n▲", "Midi increase transposition"),
    K("MI_OCTU", "Octave\n▲", "Midi move up an octave"),
    K("MI_CHU", "Channel\n▲", "Midi increase channel"),
    K("HE_VEL_CURVE_UP", "Articulation\n▲", "Articulation Up (hold loop modifier for loop-specific)"),
    K("SMARTCHORD_UP", "Smart\nChord\n▲", "QuickChord Up"),
    K("MI_TRNSD", "Transpose\n▼", "Midi decrease transposition"),
    K("MI_OCTD", "Octave\n▼", "Midi move down an octave"),
    K("MI_CHD", "Channel\n▼", "Midi decrease channel"),
    K("HE_VEL_CURVE_DOWN", "Articulation\n▼", "Articulation Down (hold loop modifier for loop-specific)"),
    K("SMARTCHORD_DOWN", "Smart\nChord\n▼", "QuickChord Down"),

]    

# LEGACY (no longer shown in the picker) — see KEYCODES_MIDI_TRANSPOSE_SELECT.
KEYCODES_MIDI_KEY = [
    K("MI_TRNS_0", "Key\nC Major\nA minor", "Midi set no transposition"),
    K("MI_TRNS_1", "Key\nC# Major\nA# minor", "Midi set transposition to +1 semitones"),
    K("MI_TRNS_2", "Key\nD Major\nB minor", "Midi set transposition to +2 semitones"),
    K("MI_TRNS_3", "Key\nD# Major\nC minor", "Midi set transposition to +3 semitones"),
    K("MI_TRNS_4", "Key\nE Major\nC# minor", "Midi set transposition to +4 semitones"),
    K("MI_TRNS_5", "Key\nF Major\nD minor", "Midi set transposition to +5 semitones"),
    K("MI_TRNS_6", "Key\nF# Major\nD# minor", "Midi set transposition to +6 semitones"),
    K("MI_TRNS_N5", "Key\nG Major\nE minor", "Midi set transposition to -5 semitones"),
    K("MI_TRNS_N4", "Key\nG# Major\nF minor", "Midi set transposition to -4 semitones"),
    K("MI_TRNS_N3", "Key\nA Major\nF# minor", "Midi set transposition to -3 semitones"),
    K("MI_TRNS_N2", "Key\nA# Major\nG minor", "Midi set transposition to -2 semitones"),
    K("MI_TRNS_N1", "Key B Major\n G# Minor", "Midi set transposition to -1 semitones"),
]

KEYCODES_MIDI_KEY2 = [
    K("MI_TRNS2_0", "KS\nC Major\nA minor", "Midi set no transposition"),
    K("MI_TRNS2_1", "KS\nC# Major\nA# minor", "Midi set transposition to +1 semitones"),
    K("MI_TRNS2_2", "KS\nD Major\nB minor", "Midi set transposition to +2 semitones"),
    K("MI_TRNS2_3", "KS\nD# Major\nC minor", "Midi set transposition to +3 semitones"),
    K("MI_TRNS2_4", "KS\nE Major\nC# minor", "Midi set transposition to +4 semitones"),
    K("MI_TRNS2_5", "KS\nF Major\nD minor", "Midi set transposition to +5 semitones"),
    K("MI_TRNS2_6", "KS\nF# Major\nD# minor", "Midi set transposition to +6 semitones"),
    K("MI_TRNS2_N5", "KS\nG Major\nE minor", "Midi set transposition to -5 semitones"),
    K("MI_TRNS2_N4", "KS\nG# Major\nF minor", "Midi set transposition to -4 semitones"),
    K("MI_TRNS2_N3", "KS\nA Major\nF# minor", "Midi set transposition to -3 semitones"),
    K("MI_TRNS2_N2", "KS\nA# Major\nG minor", "Midi set transposition to -2 semitones"),
    K("MI_TRNS2_N1", "KS B Major\n G# Minor", "Midi set transposition to -1 semitones"),
]

KEYCODES_MIDI_KEY3 = [
    K("MI_TRNS3_0", "TS\nC Major\nA minor", "Midi set no transposition"),
    K("MI_TRNS3_1", "TS\nC# Major\nA# minor", "Midi set transposition to +1 semitones"),
    K("MI_TRNS3_2", "TS\nD Major\nB minor", "Midi set transposition to +2 semitones"),
    K("MI_TRNS3_3", "TS\nD# Major\nC minor", "Midi set transposition to +3 semitones"),
    K("MI_TRNS3_4", "TS\nE Major\nC# minor", "Midi set transposition to +4 semitones"),
    K("MI_TRNS3_5", "TS\nF Major\nD minor", "Midi set transposition to +5 semitones"),
    K("MI_TRNS3_6", "TS\nF# Major\nD# minor", "Midi set transposition to +6 semitones"),
    K("MI_TRNS3_N5", "TS\nG Major\nE minor", "Midi set transposition to -5 semitones"),
    K("MI_TRNS3_N4", "TS\nG# Major\nF minor", "Midi set transposition to -4 semitones"),
    K("MI_TRNS3_N3", "TS\nA Major\nF# minor", "Midi set transposition to -3 semitones"),
    K("MI_TRNS3_N2", "TS\nA# Major\nG minor", "Midi set transposition to -2 semitones"),
    K("MI_TRNS3_N1", "TS B Major\n G# Minor", "Midi set transposition to -1 semitones"),
]

# Transpose selector: ONE -64..+64 semitone band that replaces the separate
# main-zone Key (MI_TRNS_N6..MI_TRNS_6) and Octave (MI_OCT_N2..MI_OCT_7)
# selector pickers. The firmware clamps the combined transposition to the value
# and re-splits it into whole octaves (octave_number) + a -11..+11 key
# remainder (transpose_number). KS/TS selector lists above are unchanged.
KEYCODES_MIDI_TRANSPOSE_SELECT = [
    K("MI_TRNS_SET_N{}".format(-v) if v < 0 else "MI_TRNS_SET_{}".format(v),
      "Transpose\n 0" if v == 0 else "Transpose\n{:+d}".format(v),
      "Set combined transposition (octave + key) to {:+d} semitones".format(v))
    for v in range(-64, 65)
]

KEYCODES_MIDI_CHANNEL = [
    K("MI_CH1", "Channel\n1", "Midi set channel to 1"),
    K("MI_CH2", "Channel\n2", "Midi set channel to 2"),
    K("MI_CH3", "Channel\n3", "Midi set channel to 3"),
    K("MI_CH4", "Channel\n4", "Midi set channel to 4"),
    K("MI_CH5", "Channel\n5", "Midi set channel to 5"),
    K("MI_CH6", "Channel\n6", "Midi set channel to 6"),
    K("MI_CH7", "Channel\n7", "Midi set channel to 7"),
    K("MI_CH8", "Channel\n8", "Midi set channel to 8"),
    K("MI_CH9", "Channel\n9", "Midi set channel to 9"),
    K("MI_CH10", "Channel\n10", "Midi set channel to 10"),
    K("MI_CH11", "Channel\n11", "Midi set channel to 11"),
    K("MI_CH12", "Channel\n12", "Midi set channel to 12"),
    K("MI_CH13", "Channel\n13", "Midi set channel to 13"),
    K("MI_CH14", "Channel\n14", "Midi set channel to 14"),
    K("MI_CH15", "Channel\n15", "Midi set channel to 15"),
    K("MI_CH16", "Channel\n16", "Midi set channel to 16"),
]

# Multichannel echo presets (16): tap = preset on/off — while on, everything
# the device outputs on the preset's target channel is echoed onto its multi
# channels; hold = on-device config menu (Target / Multi Ch 1-3).
KEYCODES_MULTICHANNEL = [
    K("MULTICHANNEL_{}".format(n), "Multi\nCH {}".format(n),
      "Multichannel preset {}: tap = echo on/off (duplicates the target channel's output onto up to 3 multi channels), hold = configure target + multi channels".format(n))
    for n in range(1, 17)
]

KEYCODES_MIDI_CHANNEL_KEYSPLIT = [
    K("MI_CHANNEL_KEYSPLIT_1", "KS\nChannel 1", "Midi set key split channel to 1"),
    K("MI_CHANNEL_KEYSPLIT_2", "KS\nChannel 2", "Midi set key split channel to 2"),
    K("MI_CHANNEL_KEYSPLIT_3", "KS\nChannel 3", "Midi set key split channel to 3"),
    K("MI_CHANNEL_KEYSPLIT_4", "KS\nChannel 4", "Midi set key split channel to 4"),
    K("MI_CHANNEL_KEYSPLIT_5", "KS\nChannel 5", "Midi set key split channel to 5"),
    K("MI_CHANNEL_KEYSPLIT_6", "KS\nChannel 6", "Midi set key split channel to 6"),
    K("MI_CHANNEL_KEYSPLIT_7", "KS\nChannel 7", "Midi set key split channel to 7"),
    K("MI_CHANNEL_KEYSPLIT_8", "KS\nChannel 8", "Midi set key split channel to 8"),
    K("MI_CHANNEL_KEYSPLIT_9", "KS\nChannel 9", "Midi set key split channel to 9"),
    K("MI_CHANNEL_KEYSPLIT_10", "KS\nChannel 10", "Midi set key split channel to 10"),
    K("MI_CHANNEL_KEYSPLIT_11", "KS\nChannel 11", "Midi set key split channel to 11"),
    K("MI_CHANNEL_KEYSPLIT_12", "KS\nChannel 12", "Midi set key split channel to 12"),
    K("MI_CHANNEL_KEYSPLIT_13", "KS\nChannel 13", "Midi set key split channel to 13"),
    K("MI_CHANNEL_KEYSPLIT_14", "KS\nChannel 14", "Midi set key split channel to 14"),
    K("MI_CHANNEL_KEYSPLIT_15", "KS\nChannel 15", "Midi set key split channel to 15"),
    K("MI_CHANNEL_KEYSPLIT_16", "KS\nChannel 16", "Midi set key split channel to 16"),
]

KEYCODES_KEYSPLIT_BUTTONS = [
    K("KS_QB_TOGGLE", "Keysplit\nOn/Off", "Tap: turn keysplit on/off using the button's configured options. Hold: configure Channel, Transpose and Articulation (each defaults to 'Device Master' = follow the base zone); once any option is set, Auto Notes and Sustain Allow/Ignore appear too. LED shows on/off like a toggle key."),
    K("TS_QB_TOGGLE", "Triplesplit\nOn/Off", "Tap: turn triplesplit on/off using the button's configured options. Hold: configure Channel, Transpose and Articulation (each defaults to 'Device Master' = follow the base zone); once any option is set, Auto Notes and Sustain Allow/Ignore appear too. LED shows on/off like a toggle key."),
    K("KS_TOGGLE", "Channel\nSplit\nToggle", "Toggle keysplit mode"),
    K("KS_TRANSPOSE_TOGGLE", "Transpose\nSplit\nToggle", "Toggle keysplit mode"),
    K("KS_VELOCITY_TOGGLE", "Velocity\nSplit\nToggle", "Toggle keysplit mode"),
    K("KS_MODIFIER", "KeySplit\nModifier", "Hold: redirect channel/transpose/velocity to keysplit zone. Double-tap: turn off keysplit and reset velocity range"),
    K("TS_MODIFIER", "TripleSplit\nModifier", "Hold: redirect channel/transpose/velocity to triplesplit zone. Double-tap: turn off triplesplit and reset velocity range"),
    K("CLEAR_MENU", "Clear\nMenu", "Open clear/reset menu (ALL, MODIFIERS, LOOPS, UNBIND QB, FACTORY)"),
    K("CLEAR_MODIFIERS", "Clear\nModifiers", "Reset all modifiers: key/triple split, transpose, channel, velocity range, octave doubler, and per-loop modifiers."),
    K("CLEAR_LOOPS", "Clear\nAll Loops", "Clear all loop content and reset every loop's modifiers."),
    K("RESET_DEFAULT", "Reset to\nDefault", "Reload the saved keyboard settings, clear all loops, cancel any quick build, and reset per-loop modifiers."),
    K("RESET_QUICKBUILDS", "Reset All\nQuickbuilds", "Unbind ALL QuickBuild master keys (a fresh reset of the master bindings). Built content is kept; only the key→function bindings are removed."),
    K("RESET_FACTORY", "Reset\nFactory\nDefaults", "FACTORY RESET — opens an \"Are you sure?\" confirmation on the keyboard, then ERASES ALL saved data (settings, key layouts, macros, quickbuilds, presets, curves, names, loops — everything) and reboots. Cannot be undone."),
]

KEYCODES_MIDI_CHANNEL_KEYSPLIT2 = [
    K("MI_CHANNEL_KEYSPLIT2_1", "TS\nChannel 1", "Midi set key split channel to 1"),
    K("MI_CHANNEL_KEYSPLIT2_2", "TS\nChannel 2", "Midi set key split channel to 2"),
    K("MI_CHANNEL_KEYSPLIT2_3", "TS\nChannel 3", "Midi set key split channel to 3"),
    K("MI_CHANNEL_KEYSPLIT2_4", "TS\nChannel 4", "Midi set key split channel to 4"),
    K("MI_CHANNEL_KEYSPLIT2_5", "TS\nChannel 5", "Midi set key split channel to 5"),
    K("MI_CHANNEL_KEYSPLIT2_6", "TS\nChannel 6", "Midi set key split channel to 6"),
    K("MI_CHANNEL_KEYSPLIT2_7", "TS\nChannel 7", "Midi set key split channel to 7"),
    K("MI_CHANNEL_KEYSPLIT2_8", "TS\nChannel 8", "Midi set key split channel to 8"),
    K("MI_CHANNEL_KEYSPLIT2_9", "TS\nChannel 9", "Midi set key split channel to 9"),
    K("MI_CHANNEL_KEYSPLIT2_10", "TS\nChannel 10", "Midi set key split channel to 10"),
    K("MI_CHANNEL_KEYSPLIT2_11", "TS\nChannel 11", "Midi set key split channel to 11"),
    K("MI_CHANNEL_KEYSPLIT2_12", "TS\nChannel 12", "Midi set key split channel to 12"),
    K("MI_CHANNEL_KEYSPLIT2_13", "TS\nChannel 13", "Midi set key split channel to 13"),
    K("MI_CHANNEL_KEYSPLIT2_14", "TS\nChannel 14", "Midi set key split channel to 14"),
    K("MI_CHANNEL_KEYSPLIT2_15", "TS\nChannel 15", "Midi set key split channel to 15"),
    K("MI_CHANNEL_KEYSPLIT2_16", "TS\nChannel 16", "Midi set key split channel to 16"),
]

KEYCODES_VELOCITY_SHUFFLE = [
    K("MI_RVEL_0", "Dynamic\nRange\n0", "Set dynamic range to 0 (allows min=max velocity)"),
    K("MI_RVEL_1", "Dynamic\nRange\n1", "Set dynamic range to 1"),
    K("MI_RVEL_2", "Dynamic\nRange\n2", "Set dynamic range to 2"),
    K("MI_RVEL_3", "Dynamic\nRange\n3", "Set dynamic range to 3"),
    K("MI_RVEL_4", "Dynamic\nRange\n4", "Set dynamic range to 4"),
    K("MI_RVEL_5", "Dynamic\nRange\n5", "Set dynamic range to 5"),
    K("MI_RVEL_6", "Dynamic\nRange\n6", "Set dynamic range to 6"),
    K("MI_RVEL_7", "Dynamic\nRange\n7", "Set dynamic range to 7"),
    K("MI_RVEL_8", "Dynamic\nRange\n8", "Set dynamic range to 8"),
    K("MI_RVEL_9", "Dynamic\nRange\n9", "Set dynamic range to 9"),
    K("MI_RVEL_10", "Dynamic\nRange\n10", "Set dynamic range to 10"),
    K("MI_RVEL_11", "Dynamic\nRange\n11", "Set dynamic range to 11"),
    K("MI_RVEL_12", "Dynamic\nRange\n12", "Set dynamic range to 12"),
    K("MI_RVEL_13", "Dynamic\nRange\n13", "Set dynamic range to 13"),
    K("MI_RVEL_14", "Dynamic\nRange\n14", "Set dynamic range to 14"),
    K("MI_RVEL_15", "Dynamic\nRange\n15", "Set dynamic range to 15"),
    K("MI_RVEL_16", "Dynamic\nRange\n16", "Set dynamic range to 16"),
]

KEYCODES_CC_ENCODERVALUE = [
    K("MI_CCENCODER_0", "CC 0\nTouch\nDial", "CC Expression wheel 0"),
    K("MI_CCENCODER_1", "CC 1\nTouch\nDial", "CC Expression wheel 1"),
    K("MI_CCENCODER_2", "CC 2\nTouch\nDial", "CC Expression wheel 2"),
    K("MI_CCENCODER_3", "CC 3\nTouch\nDial", "CC Expression wheel 3"),
    K("MI_CCENCODER_4", "CC 4\nTouch\nDial", "CC Expression wheel 4"),
    K("MI_CCENCODER_5", "CC 5\nTouch\nDial", "CC Expression wheel 5"),
    K("MI_CCENCODER_6", "CC 6\nTouch\nDial", "CC Expression wheel 6"),
    K("MI_CCENCODER_7", "CC 7\nTouch\nDial", "CC Expression wheel 7"),
    K("MI_CCENCODER_8", "CC 8\nTouch\nDial", "CC Expression wheel 8"),
    K("MI_CCENCODER_9", "CC 9\nTouch\nDial", "CC Expression wheel 9"),
    K("MI_CCENCODER_10", "CC 10\nTouch\nDial", "CC Expression wheel 10"),
    K("MI_CCENCODER_11", "CC 11\nTouch\nDial", "CC Expression wheel 11"),
    K("MI_CCENCODER_12", "CC 12\nTouch\nDial", "CC Expression wheel 12"),
    K("MI_CCENCODER_13", "CC 13\nTouch\nDial", "CC Expression wheel 13"),
    K("MI_CCENCODER_14", "CC 14\nTouch\nDial", "CC Expression wheel 14"),
    K("MI_CCENCODER_15", "CC 15\nTouch\nDial", "CC Expression wheel 15"),
    K("MI_CCENCODER_16", "CC 16\nTouch\nDial", "CC Expression wheel 16"),
    K("MI_CCENCODER_17", "CC 17\nTouch\nDial", "CC Expression wheel 17"),
    K("MI_CCENCODER_18", "CC 18\nTouch\nDial", "CC Expression wheel 18"),
    K("MI_CCENCODER_19", "CC 19\nTouch\nDial", "CC Expression wheel 19"),
    K("MI_CCENCODER_20", "CC 20\nTouch\nDial", "CC Expression wheel 20"),
    K("MI_CCENCODER_21", "CC 21\nTouch\nDial", "CC Expression wheel 21"),
    K("MI_CCENCODER_22", "CC 22\nTouch\nDial", "CC Expression wheel 22"),
    K("MI_CCENCODER_23", "CC 23\nTouch\nDial", "CC Expression wheel 23"),
    K("MI_CCENCODER_24", "CC 24\nTouch\nDial", "CC Expression wheel 24"),
    K("MI_CCENCODER_25", "CC 25\nTouch\nDial", "CC Expression wheel 25"),
    K("MI_CCENCODER_26", "CC 26\nTouch\nDial", "CC Expression wheel 26"),
    K("MI_CCENCODER_27", "CC 27\nTouch\nDial", "CC Expression wheel 27"),
    K("MI_CCENCODER_28", "CC 28\nTouch\nDial", "CC Expression wheel 28"),
    K("MI_CCENCODER_29", "CC 29\nTouch\nDial", "CC Expression wheel 29"),
    K("MI_CCENCODER_30", "CC 30\nTouch\nDial", "CC Expression wheel 30"),
    K("MI_CCENCODER_31", "CC 31\nTouch\nDial", "CC Expression wheel 31"),
    K("MI_CCENCODER_32", "CC 32\nTouch\nDial", "CC Expression wheel 32"),
    K("MI_CCENCODER_33", "CC 33\nTouch\nDial", "CC Expression wheel 33"),
    K("MI_CCENCODER_34", "CC 34\nTouch\nDial", "CC Expression wheel 34"),
    K("MI_CCENCODER_35", "CC 35\nTouch\nDial", "CC Expression wheel 35"),
    K("MI_CCENCODER_36", "CC 36\nTouch\nDial", "CC Expression wheel 36"),
    K("MI_CCENCODER_37", "CC 37\nTouch\nDial", "CC Expression wheel 37"),
    K("MI_CCENCODER_38", "CC 38\nTouch\nDial", "CC Expression wheel 38"),
    K("MI_CCENCODER_39", "CC 39\nTouch\nDial", "CC Expression wheel 39"),
    K("MI_CCENCODER_40", "CC 40\nTouch\nDial", "CC Expression wheel 40"),
    K("MI_CCENCODER_41", "CC 41\nTouch\nDial", "CC Expression wheel 41"),
    K("MI_CCENCODER_42", "CC 42\nTouch\nDial", "CC Expression wheel 42"),
    K("MI_CCENCODER_43", "CC 43\nTouch\nDial", "CC Expression wheel 43"),
    K("MI_CCENCODER_44", "CC 44\nTouch\nDial", "CC Expression wheel 44"),
    K("MI_CCENCODER_45", "CC 45\nTouch\nDial", "CC Expression wheel 45"),
    K("MI_CCENCODER_46", "CC 46\nTouch\nDial", "CC Expression wheel 46"),
    K("MI_CCENCODER_47", "CC 47\nTouch\nDial", "CC Expression wheel 47"),
    K("MI_CCENCODER_48", "CC 48\nTouch\nDial", "CC Expression wheel 48"),
    K("MI_CCENCODER_49", "CC 49\nTouch\nDial", "CC Expression wheel 49"),
    K("MI_CCENCODER_50", "CC 50\nTouch\nDial", "CC Expression wheel 50"),
    K("MI_CCENCODER_51", "CC 51\nTouch\nDial", "CC Expression wheel 51"),
    K("MI_CCENCODER_52", "CC 52\nTouch\nDial", "CC Expression wheel 52"),
    K("MI_CCENCODER_53", "CC 53\nTouch\nDial", "CC Expression wheel 53"),
    K("MI_CCENCODER_54", "CC 54\nTouch\nDial", "CC Expression wheel 54"),
    K("MI_CCENCODER_55", "CC 55\nTouch\nDial", "CC Expression wheel 55"),
    K("MI_CCENCODER_56", "CC 56\nTouch\nDial", "CC Expression wheel 56"),
    K("MI_CCENCODER_57", "CC 57\nTouch\nDial", "CC Expression wheel 57"),
    K("MI_CCENCODER_58", "CC 58\nTouch\nDial", "CC Expression wheel 58"),
    K("MI_CCENCODER_59", "CC 59\nTouch\nDial", "CC Expression wheel 59"),
    K("MI_CCENCODER_60", "CC 60\nTouch\nDial", "CC Expression wheel 60"),
    K("MI_CCENCODER_61", "CC 61\nTouch\nDial", "CC Expression wheel 61"),
    K("MI_CCENCODER_62", "CC 62\nTouch\nDial", "CC Expression wheel 62"),
    K("MI_CCENCODER_63", "CC 63\nTouch\nDial", "CC Expression wheel 63"),
    K("MI_CCENCODER_64", "CC 64\nTouch\nDial", "CC Expression wheel 64"),
    K("MI_CCENCODER_65", "CC 65\nTouch\nDial", "CC Expression wheel 65"),
    K("MI_CCENCODER_66", "CC 66\nTouch\nDial", "CC Expression wheel 66"),
    K("MI_CCENCODER_67", "CC 67\nTouch\nDial", "CC Expression wheel 67"),
    K("MI_CCENCODER_68", "CC 68\nTouch\nDial", "CC Expression wheel 68"),
    K("MI_CCENCODER_69", "CC 69\nTouch\nDial", "CC Expression wheel 69"),
    K("MI_CCENCODER_70", "CC 70\nTouch\nDial", "CC Expression wheel 70"),
    K("MI_CCENCODER_71", "CC 71\nTouch\nDial", "CC Expression wheel 71"),
    K("MI_CCENCODER_72", "CC 72\nTouch\nDial", "CC Expression wheel 72"),
    K("MI_CCENCODER_73", "CC 73\nTouch\nDial", "CC Expression wheel 73"),
    K("MI_CCENCODER_74", "CC 74\nTouch\nDial", "CC Expression wheel 74"),
    K("MI_CCENCODER_75", "CC 75\nTouch\nDial", "CC Expression wheel 75"),
    K("MI_CCENCODER_76", "CC 76\nTouch\nDial", "CC Expression wheel 76"),
    K("MI_CCENCODER_77", "CC 77\nTouch\nDial", "CC Expression wheel 77"),
    K("MI_CCENCODER_78", "CC 78\nTouch\nDial", "CC Expression wheel 78"),
    K("MI_CCENCODER_79", "CC 79\nTouch\nDial", "CC Expression wheel 79"),
    K("MI_CCENCODER_80", "CC 80\nTouch\nDial", "CC Expression wheel 80"),
    K("MI_CCENCODER_81", "CC 81\nTouch\nDial", "CC Expression wheel 81"),
    K("MI_CCENCODER_82", "CC 82\nTouch\nDial", "CC Expression wheel 82"),
    K("MI_CCENCODER_83", "CC 83\nTouch\nDial", "CC Expression wheel 83"),
    K("MI_CCENCODER_84", "CC 84\nTouch\nDial", "CC Expression wheel 84"),
    K("MI_CCENCODER_85", "CC 85\nTouch\nDial", "CC Expression wheel 85"),
    K("MI_CCENCODER_86", "CC 86\nTouch\nDial", "CC Expression wheel 86"),
    K("MI_CCENCODER_87", "CC 87\nTouch\nDial", "CC Expression wheel 87"),
    K("MI_CCENCODER_88", "CC 88\nTouch\nDial", "CC Expression wheel 88"),
    K("MI_CCENCODER_89", "CC 89\nTouch\nDial", "CC Expression wheel 89"),
    K("MI_CCENCODER_90", "CC 90\nTouch\nDial", "CC Expression wheel 90"),
    K("MI_CCENCODER_91", "CC 91\nTouch\nDial", "CC Expression wheel 91"),
    K("MI_CCENCODER_92", "CC 92\nTouch\nDial", "CC Expression wheel 92"),
    K("MI_CCENCODER_93", "CC 93\nTouch\nDial", "CC Expression wheel 93"),
    K("MI_CCENCODER_94", "CC 94\nTouch\nDial", "CC Expression wheel 94"),
    K("MI_CCENCODER_95", "CC 95\nTouch\nDial", "CC Expression wheel 95"),
    K("MI_CCENCODER_96", "CC 96\nTouch\nDial", "CC Expression wheel 96"),
    K("MI_CCENCODER_97", "CC 97\nTouch\nDial", "CC Expression wheel 97"),
    K("MI_CCENCODER_98", "CC 98\nTouch\nDial", "CC Expression wheel 98"),
    K("MI_CCENCODER_99", "CC 99\nTouch\nDial", "CC Expression wheel 99"),
    K("MI_CCENCODER_100", "CC 100\nTouch\nDial", "CC Expression wheel 100"),
    K("MI_CCENCODER_101", "CC 101\nTouch\nDial", "CC Expression wheel 101"),
    K("MI_CCENCODER_102", "CC 102\nTouch\nDial", "CC Expression wheel 102"),
    K("MI_CCENCODER_103", "CC 103\nTouch\nDial", "CC Expression wheel 103"),
    K("MI_CCENCODER_104", "CC 104\nTouch\nDial", "CC Expression wheel 104"),
    K("MI_CCENCODER_105", "CC 105\nTouch\nDial", "CC Expression wheel 105"),
    K("MI_CCENCODER_106", "CC 106\nTouch\nDial", "CC Expression wheel 106"),
    K("MI_CCENCODER_107", "CC 107\nTouch\nDial", "CC Expression wheel 107"),
    K("MI_CCENCODER_108", "CC 108\nTouch\nDial", "CC Expression wheel 108"),
    K("MI_CCENCODER_109", "CC 109\nTouch\nDial", "CC Expression wheel 109"),
    K("MI_CCENCODER_110", "CC 110\nTouch\nDial", "CC Expression wheel 110"),
    K("MI_CCENCODER_111", "CC 111\nTouch\nDial", "CC Expression wheel 111"),
    K("MI_CCENCODER_112", "CC 112\nTouch\nDial", "CC Expression wheel 112"),
    K("MI_CCENCODER_113", "CC 113\nTouch\nDial", "CC Expression wheel 113"),
    K("MI_CCENCODER_114", "CC 114\nTouch\nDial", "CC Expression wheel 114"),
    K("MI_CCENCODER_115", "CC 115\nTouch\nDial", "CC Expression wheel 115"),
    K("MI_CCENCODER_116", "CC 116\nTouch\nDial", "CC Expression wheel 116"),
    K("MI_CCENCODER_117", "CC 117\nTouch\nDial", "CC Expression wheel 117"),
    K("MI_CCENCODER_118", "CC 118\nTouch\nDial", "CC Expression wheel 118"),
    K("MI_CCENCODER_119", "CC 119\nTouch\nDial", "CC Expression wheel 119"),
    K("MI_CCENCODER_120", "CC 120\nTouch\nDial", "CC Expression wheel 120"),
    K("MI_CCENCODER_121", "CC 121\nTouch\nDial", "CC Expression wheel 121"),
    K("MI_CCENCODER_122", "CC 122\nTouch\nDial", "CC Expression wheel 122"),
    K("MI_CCENCODER_123", "CC 123\nTouch\nDial", "CC Expression wheel 123"),
    K("MI_CCENCODER_124", "CC 124\nTouch\nDial", "CC Expression wheel 124"),
    K("MI_CCENCODER_125", "CC 125\nTouch\nDial", "CC Expression wheel 125"),
    K("MI_CCENCODER_126", "CC 126\nTouch\nDial", "CC Expression wheel 126"),
    K("MI_CCENCODER_127", "CC 127\nTouch\nDial", "CC Expression wheel 127"),
]

KEYCODES_CC_STEPSIZE = [
    K("CC_STEPSIZE_1", "CC\nIncrement\n1", "SET CC Up/Down TO X1"),
    K("CC_STEPSIZE_2", "CC\nIncrement\n2", "SET CC Up/Down TO X2"),
    K("CC_STEPSIZE_3", "CC\nIncrement\n3", "SET CC Up/Down TO X3"),
    K("CC_STEPSIZE_4", "CC\nIncrement\n4", "SET CC Up/Down TO X4"),
    K("CC_STEPSIZE_5", "CC\nIncrement\n5", "SET CC Up/Down TO X5"),
    K("CC_STEPSIZE_6", "CC\nIncrement\n6", "SET CC Up/Down TO X6"),
    K("CC_STEPSIZE_7", "CC\nIncrement\n7", "SET CC Up/Down TO X7"),
    K("CC_STEPSIZE_8", "CC\nIncrement\n8", "SET CC Up/Down TO X8"),
    K("CC_STEPSIZE_9", "CC\nIncrement\n9", "SET CC Up/Down TO X9"),
    K("CC_STEPSIZE_10", "CC\nIncrement\n10", "SET CC Up/Down TO X10"),
]

KEYCODES_VELOCITY_STEPSIZE = [
    K("MI_VELOCITY_STEPSIZE_1", "Velocity\nIncrement\n1", "SET Velocity Up/Down x1"),
    K("MI_VELOCITY_STEPSIZE_2", "Velocity\nIncrement\n2", "SET Velocity Up/Down TO x2"),
    K("MI_VELOCITY_STEPSIZE_3", "Velocity\nIncrement\n3", "SET Velocity Up/Down TO x3"),
    K("MI_VELOCITY_STEPSIZE_4", "Velocity\nIncrement\n4", "SET Velocity Up/Down TO x4"),
    K("MI_VELOCITY_STEPSIZE_5", "Velocity\nIncrement\n5", "SET Velocity Up/Down TO x5"),
    K("MI_VELOCITY_STEPSIZE_6", "Velocity\nIncrement\n6", "SET Velocity Up/Down TO x6"),
    K("MI_VELOCITY_STEPSIZE_7", "Velocity\nIncrement\n7", "SET Velocity Up/Down TO x7"),
    K("MI_VELOCITY_STEPSIZE_8", "Velocity\nIncrement\n8", "SET Velocity Up/Down TO x8"),
    K("MI_VELOCITY_STEPSIZE_9", "Velocity\nIncrement\n9", "SET Velocity Up/Down TO x9"),
    K("MI_VELOCITY_STEPSIZE_10", "Velocity\nIncrement\n10", "SET Velocity Up/Down TO x10"),
]

KEYCODES_MIDI_SMARTCHORDBUTTONS = [
    K("SMARTCHORD_DOWN", "Smart\nChord\n▼", "QuickChord Down"),
    K("MI_CHORD_99", "Smart\nChord", "Press QuickChord"),
    K("SMARTCHORD_UP", "Smart\nChord\n▲", "QuickChord Up"),
    K("MI_INV_DOWN", "Inversion\nPosition\n▼", "Inv Up"),
    K("MI_INV_UP", "Inversion\nPosition\n▲", "Inv Up"),
    K("COLORBLIND_TOGGLE", "Colorblind\nMode\nOn/Off", "Colorblind"),
    #K("SMARTCHORDCOLOR_TOGGLE", "Smartchord\nRGB\nOn/Off", "Smartchord LEDs Toggle"),
    K("OLED_2", "Smart\nChord\nRGB", "Toggle Smartchord Light mode"),
    K("OLED_1", "Screen\nKeyboard\nShift", "Adjust Keyboard Screen"),
    # K("OLED_3", "SmartChord\nPiano\nModes", "Momentarily turn on layer when pressed"),
    K("SOLO_MODE", "Solo\nMode", "Toggle solo mode (monophonic - one note at a time)"),

]

KEYCODES_MIDI_CHANNEL_HOLD = [
    K("MI_CHANNEL_HOLD_1", "Hold\nChannel\n1", "Hold for MIDI channel 1, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_2", "Hold\nChannel\n2", "Hold for MIDI channel 2, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_3", "Hold\nChannel\n3", "Hold for MIDI channel 3, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_4", "Hold\nChannel\n4", "Hold for MIDI channel 4, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_5", "Hold\nChannel\n5", "Hold for MIDI channel 5, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_6", "Hold\nChannel\n6", "Hold for MIDI channel 6, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_7", "Hold\nChannel\n7", "Hold for MIDI channel 7, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_8", "Hold\nChannel\n8", "Hold for MIDI channel 8, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_9", "Hold\nChannel\n9", "Hold for MIDI channel 9, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_10", "Hold\nChannel\n10", "Hold for MIDI channel 10, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_11", "Hold\nChannel\n11", "Hold for MIDI channel 11, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_12", "Hold\nChannel\n12", "Hold for MIDI channel 12, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_13", "Hold\nChannel\n13", "Hold for MIDI channel 13, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_14", "Hold\nChannel\n14", "Hold for MIDI channel 14, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_15", "Hold\nChannel\n15", "Hold for MIDI channel 15, release for default MIDI channel"),
    K("MI_CHANNEL_HOLD_16", "Hold\nChannel\n16", "Hold for MIDI channel 16, release for default MIDI channel"),
]

KEYCODES_MIDI_CHANNEL_OS = [
    K("MI_CHANNEL_OS_1", "Temporary\nChannel\n1", "Temporary switch to MIDI channel 1"),
    K("MI_CHANNEL_OS_2", "Temporary\nChannel\n2", "Temporary switch to MIDI channel 2"),
    K("MI_CHANNEL_OS_3", "Temporary\nChannel\n3", "Temporary switch to MIDI channel 3"),
    K("MI_CHANNEL_OS_4", "Temporary\nChannel\n4", "Temporary switch to MIDI channel 4"),
    K("MI_CHANNEL_OS_5", "Temporary\nChannel\n5", "Temporary switch to MIDI channel 5"),
    K("MI_CHANNEL_OS_6", "Temporary\nChannel\n6", "Temporary switch to MIDI channel 6"),
    K("MI_CHANNEL_OS_7", "Temporary\nChannel\n7", "Temporary switch to MIDI channel 7"),
    K("MI_CHANNEL_OS_8", "Temporary\nChannel\n8", "Temporary switch to MIDI channel 8"),
    K("MI_CHANNEL_OS_9", "Temporary\nChannel\n9", "Temporary switch to MIDI channel 9"),
    K("MI_CHANNEL_OS_10", "Temporary\nChannel\n10", "Temporary switch to MIDI channel 10"),
    K("MI_CHANNEL_OS_11", "Temporary\nChannel\n11", "Temporary switch to MIDI channel 11"),
    K("MI_CHANNEL_OS_12", "Temporary\nChannel\n12", "Temporary switch to MIDI channel 12"),
    K("MI_CHANNEL_OS_13", "Temporary\nChannel\n13", "Temporary switch to MIDI channel 13"),
    K("MI_CHANNEL_OS_14", "Temporary\nChannel\n14", "Temporary switch to MIDI channel 14"),
    K("MI_CHANNEL_OS_15", "Temporary\nChannel\n15", "Temporary switch to MIDI channel 15"),
    K("MI_CHANNEL_OS_16", "Temporary\nChannel\n16", "Temporary switch to MIDI channel 16"),
]

KEYCODES_MIDI_CHORD_0 = [
K("MI_INV_1", "Major 2nd", "Minor\n2nd"),
K("MI_INV_2", "Minor 2nd", "Major\n2nd"), 
K("MI_INV_3", "Minor 3rd", "Minor\n3rd"),
K("MI_INV_4", "Major 3rd", "Major\n3rd"),
K("MI_INV_5", "Perfect Fourth", "Perfect\nFourth"),
K("MI_INV_6", "Tritone", "Tritone"),
K("MI_INV_7", "Perfect 5th", "Perfect\nFifth"),
K("MI_INV_8", "Minor 6th", "Minor\n6th"),
K("MI_INV_9", "Major 6th", "Major\n6th"),
K("MI_INV_10", "Minor 7th", "Minor\n7th"),
K("MI_INV_11", "Major 7th", "Major\n7th"),
]

KEYCODES_MIDI_CHORD_1 = [
K("MI_CHORD_0", "Major", "Major"),
K("MI_CHORD_1", "m", "Minor"),
K("MI_CHORD_2", "dim", "Diminished"),
K("MI_CHORD_3", "aug", "Augmented"),
K("MI_CHORD_4", "b5", "b5"),
K("MI_CHORD_5", "sus2", "Sus2"),
K("MI_CHORD_6", "sus4", "Sus4"),
K("MI_CHORD_7", "7no3", "7 no 3"),
K("MI_CHORD_8", "maj7\nno3", "Major 7 no 3"),
K("MI_CHORD_9", "7no5", "7 no 5"),
K("MI_CHORD_10", "m7no5", "Minor 7 no 5"),
K("MI_CHORD_11", "maj7\nno5", "Major 7 no 5"),
]

KEYCODES_MIDI_CHORD_2 = [
K("MI_CHORD_12", "6", "Major 6"),
K("MI_CHORD_13", "m6", "Minor 6"), 
K("MI_CHORD_14", "add2", "Add2"),
K("MI_CHORD_15", "m(add2)", "Minor Add2"),
K("MI_CHORD_16", "add4", "Add4"),
K("MI_CHORD_17", "m(add4)", "Minor Add4"),
K("MI_CHORD_18", "7", "7"),
K("MI_CHORD_19", "Maj7", "Major 7"),
K("MI_CHORD_20", "m7", "Minor 7"),
K("MI_CHORD_21", "m7b5", "Minor 7 b5"),
K("MI_CHORD_22", "dim7", "Diminished 7"),
K("MI_CHORD_23", "minMaj7", "Minor Major 7"),
K("MI_CHORD_24", "7sus4", "7 Sus4"),
K("MI_CHORD_25", "add9", "Add9"),
K("MI_CHORD_26", "m(add9)", "Minor Add9"),
K("MI_CHORD_27", "add11", "Add11"),
K("MI_CHORD_28", "m(add11)", "Minor Add11"),
]

KEYCODES_MIDI_CHORD_3 = [
K("MI_CHORD_29", "9", "9"),
K("MI_CHORD_30", "m9", "Minor 9"),
K("MI_CHORD_31", "Maj9", "Major 9"),
K("MI_CHORD_32", "6/9", "6/9"),
K("MI_CHORD_33", "m6/9", "Minor 6/9"),
K("MI_CHORD_34", "7b9", "7 b9"),
K("MI_CHORD_35", "7(11)", "7(11)"),
K("MI_CHORD_36", "7(#11)", "7(#11)"),
K("MI_CHORD_37", "m7(11)", "Minor 7(11)"),
K("MI_CHORD_38", "maj7\n(11)", "Major 7(11)"),
K("MI_CHORD_39", "Maj7\n(#11)", "Major 7(#11)"),
K("MI_CHORD_40", "7(13)", "7(13)"),
K("MI_CHORD_41", "m7(13)", "Minor 7(13)"),
K("MI_CHORD_42", "Maj7\n(13)", "Major 7(13)"),
]

KEYCODES_MIDI_CHORD_4 = [
K("MI_CHORD_43", "11", "11"),
K("MI_CHORD_44", "m11", "Minor 11"),
K("MI_CHORD_45", "Maj11", "Major 11"),
K("MI_CHORD_46", "7(11)\n(13)", "7(11)(13)"),
K("MI_CHORD_47", "m7(11)\n(13)", "Minor 7(11)(13)"),
K("MI_CHORD_48", "maj7\n(11)(13)", "Major 7(11)(13)"),
K("MI_CHORD_49", "9(13)", "9(13)"),
K("MI_CHORD_50", "m9(13)", "Minor 9(13)"),
K("MI_CHORD_51", "maj9\n(13)", "Major 9(13)"),
K("MI_CHORD_52", "13", "13"),
K("MI_CHORD_53", "m13", "Minor 13"),
K("MI_CHORD_54", "Maj13", "Major 13"),
]

KEYCODES_MIDI_CHORD_5 = [
K("MI_CHORD_55", "7b9(11)", "7 b9(11)"),
K("MI_CHORD_56", "7sus2", "7 Sus2"),
K("MI_CHORD_57", "7#5", "7 #5"),
K("MI_CHORD_58", "7b5", "7 b5"),
K("MI_CHORD_59", "7#9", "7 #9"),
K("MI_CHORD_60", "7b5b9", "7 b5 b9"),
K("MI_CHORD_61", "7b5#9", "7 b5 #9"),
K("MI_CHORD_62", "7b9(13)", "7 b9(13)"),
K("MI_CHORD_63", "7#9(13)", "7 #9(13)"),
K("MI_CHORD_64", "7#5b9", "7 #5 b9"),
K("MI_CHORD_65", "7#5#9", "7 #5 #9"),
K("MI_CHORD_66", "7b5(11)", "7 b5(11)"),
K("MI_CHORD_67", "maj7\nsus4", "Major 7 Sus4"),
K("MI_CHORD_68", "maj7\n#5", "Major 7 #5"),
K("MI_CHORD_69", "maj7\nb5", "Major 7 b5"),
K("MI_CHORD_70", "minMaj7\n(11)", "Minor Major 7(11)"),
K("MI_CHORD_71", "(addb5)", "Add b5"),
K("MI_CHORD_72", "9#11", "9 #11"),
K("MI_CHORD_73", "9b5", "9 b5"),
K("MI_CHORD_74", "9#5", "9 #5"),
K("MI_CHORD_75", "m9b5", "Minor 9 b5"),
K("MI_CHORD_76", "m9#11", "Minor 9 #11"),
K("MI_CHORD_77", "9sus4", "9 Sus4"),
]

KEYCODES_MIDI_SCALES = [ 
K("MI_CHORD_100", "Major\nScale\n(Ionian)", "Major(Ionian)"),
K("MI_CHORD_101", "Dorian\nScale", "Dorian"),
K("MI_CHORD_102", "Phrygian\nScale", "Phrygian"),
K("MI_CHORD_103", "Lydian\nScale", "Lydian"),
K("MI_CHORD_104", "Mixolydian\nScale", "Mixolydian"),
K("MI_CHORD_105", "Minor\nScale\n(Aeolian)", "Minor(Aeolian)"),
K("MI_CHORD_106", "Locrian\nScale", "Locrian"),
K("MI_CHORD_107", "Melodic\nMinor\nScale", "Melodic Minor"),
K("MI_CHORD_108", "Lydian\nDominant\nScale", "Lydian Dominant"),
K("MI_CHORD_109", "Altered\nScale", "Altered Scale"),
K("MI_CHORD_110", "Harmonic\nMinor\nScale", "Harmonic Minor"),
K("MI_CHORD_111", "Major\nPentatonic\nScale", "Major Pentatonic"),
K("MI_CHORD_112", "Minor\nPentatonic\nScale", "Minor Pentatonic"),
K("MI_CHORD_113", "Whole\nTone\nScale", "Whole Tone"),
K("MI_CHORD_114", "Diminished\nScale", "Diminished"),
K("MI_CHORD_115", "Blues\nScale", "Blues"),
]

    
KEYCODES_MIDI_INVERSION = [
 K ("MI_INVERSION_DEF", "Root \nPosition", "Root Position"),
 K ("MI_INVERSION_1", "1st \nInversion", "1st Inversion"),
 K ("MI_INVERSION_2", "2nd \nInversion", "2nd Inversion"),
 K ("MI_INVERSION_3", "3rd \nInversion", "3rd Inversion"),
 K ("MI_INVERSION_4", "4th \nInversion", "4th Inversion"),
 K ("MI_INVERSION_5", "5th \nInversion", "5th Inversion"),
 K ("MI_INVERSION_6", "6th \nInversion", "6th Inversion"),
]

KEYCODES_RGB_KC_CUSTOM = [
    K("RGB_KC_1", "None", "RGB Mode: None"),
    K("RGB_KC_2", "Solid\nColor", "RGB Mode: Solid Color"),
    K("RGB_KC_3", "Alphas\nMods", "RGB Mode: Alphas Mods"),
    K("RGB_KC_4", "Gradient\nUp Down", "RGB Mode: Gradient Up Down"),
    K("RGB_KC_5", "Gradient\nLeft Right", "RGB Mode: Gradient Left Right"),
    K("RGB_KC_6", "Breathing", "RGB Mode: Breathing"),
    K("RGB_KC_7", "Band SAT", "RGB Mode: Band Saturation"),
    K("RGB_KC_8", "Band VAL", "RGB Mode: Band Brightness"),
    K("RGB_KC_9", "Band\nPinwheel SAT", "RGB Mode: Band Pinwheel Saturation"),
    K("RGB_KC_10", "Band\nPinwheel VAL", "RGB Mode: Band Pinwheel Brightness"),
    K("RGB_KC_11", "Band\nSpiral SAT", "RGB Mode: Band Spiral Saturation"),
    K("RGB_KC_12", "Band\nSpiral VAL", "RGB Mode: Band Spiral Brightness"),
    K("RGB_KC_13", "Cycle\nAll", "RGB Mode: Cycle All"),
    K("RGB_KC_14", "Cycle\nLeft Right", "RGB Mode: Cycle Left Right"),
    K("RGB_KC_15", "Cycle\nUp Down", "RGB Mode: Cycle Up Down"),
    K("RGB_KC_16", "Cycle\nOut In", "RGB Mode: Cycle Out In"),
    K("RGB_KC_17", "Cycle\nOut In Dual", "RGB Mode: Cycle Out In Dual"),
    K("RGB_KC_18", "Rainbow\nMoving\nChevron", "RGB Mode: Rainbow Moving Chevron"),
    K("RGB_KC_19", "Cycle\nPinwheel", "RGB Mode: Cycle Pinwheel"),
    K("RGB_KC_20", "Cycle\nSpiral", "RGB Mode: Cycle Spiral"),
    K("RGB_KC_21", "Dual\nBeacon", "RGB Mode: Dual Beacon"),
    K("RGB_KC_22", "Rainbow\nBeacon", "RGB Mode: Rainbow Beacon"),
    K("RGB_KC_23", "Rainbow\nPinwheels", "RGB Mode: Rainbow Pinwheels"),
    K("RGB_KC_24", "Raindrops", "RGB Mode: Raindrops"),
    K("RGB_KC_25", "Jellybean\nRaindrops", "RGB Mode: Jellybean Raindrops"),
    K("RGB_KC_26", "Hue\nBreathing", "RGB Mode: Hue Breathing"),
    K("RGB_KC_27", "Hue\nPendulum", "RGB Mode: Hue Pendulum"),
    K("RGB_KC_28", "Hue\nWave", "RGB Mode: Hue Wave"),
    K("RGB_KC_29", "Pixel\nFractal", "RGB Mode: Pixel Fractal"),
    K("RGB_KC_30", "Pixel\nFlow", "RGB Mode: Pixel Flow"),
    K("RGB_KC_31", "Pixel\nRain", "RGB Mode: Pixel Rain"),
    K("RGB_KC_32", "Typing\nHeatmap", "RGB Mode: Typing Heatmap"),
    K("RGB_KC_33", "Digital\nRain", "RGB Mode: Digital Rain"),
    K("RGB_KC_34", "Solid\nReactive\nSimple", "RGB Mode: Solid Reactive Simple"),
    K("RGB_KC_35", "Solid\nReactive", "RGB Mode: Solid Reactive"),
    K("RGB_KC_36", "Solid\nReactive\nWide", "RGB Mode: Solid Reactive Wide"),
    K("RGB_KC_37", "Solid\nReactive\nMultiWide", "RGB Mode: Solid Reactive MultiWide"),
    K("RGB_KC_38", "Solid\nReactive\nCross", "RGB Mode: Solid Reactive Cross"),
    K("RGB_KC_39", "Solid\nReactive\nMultiCross", "RGB Mode: Solid Reactive MultiCross"),
    K("RGB_KC_40", "Solid\nReactive\nNexus", "RGB Mode: Solid Reactive Nexus"),
    K("RGB_KC_41", "Solid\nReactive\nMultiNexus", "RGB Mode: Solid Reactive MultiNexus"),
    K("RGB_KC_42", "Splash", "RGB Mode: Splash"),
    K("RGB_KC_43", "MultiSplash", "RGB Mode: MultiSplash"),
    K("RGB_KC_44", "Solid\nSplash", "RGB Mode: Solid Splash"),
    K("RGB_KC_45", "Solid\nMultiSplash", "RGB Mode: Solid MultiSplash"),
    K("RGB_MIDISWITCH", "MIDI\nSwitch\nAuto Light", "RGB Mode: MIDI Switch Auto Light"),
    # (RGB_KC_46 / RGB_KC_47 @ 0xC4A4/0xC4A5 repurposed as EXWHEEL_SC / EXWHEEL_BPM
    #  touch dials — they were non-functional placeholders here; the real Reactive
    #  Lightning/Ripple modes are selected via the Lighting picker.)
    K("RGB_KC_48", "Reactive\nFireworks", "RGB Mode: Reactive Fireworks"),
    K("RGB_KC_49", "Comet\nTrail", "RGB Mode: Comet Trail"),
    K("RGB_KC_50", "Tetris\nVertical", "RGB Mode: Tetris Vertical"),
    K("RGB_KC_51", "Tetris\nHorizontal", "RGB Mode: Tetris Horizontal"),
    K("RGB_KC_52", "Fireplace", "RGB Mode: Fireplace"),
    K("RGB_KC_53", "Pong", "RGB Mode: Pong"),
    K("RGB_KC_54", "L/R Sweep\nStatic", "RGB Mode: L/R Sweep Static"),
    K("RGB_KC_55", "L/R Sweep\nRainbow", "RGB Mode: L/R Sweep Rainbow"),
    K("RGB_KC_56", "L/R Sweep\nRandom", "RGB Mode: L/R Sweep Random"),
    K("RGB_KC_57", "Custom\nSlot 1", "RGB Mode: Custom Slot 1"),
    K("RGB_KC_58", "Custom\nSlot 2", "RGB Mode: Custom Slot 2"),
    K("RGB_KC_59", "Custom\nSlot 3", "RGB Mode: Custom Slot 3"),
    K("RGB_KC_60", "Custom\nSlot 4", "RGB Mode: Custom Slot 4"),
    K("RGB_KC_61", "Custom\nSlot 5", "RGB Mode: Custom Slot 5"),
    K("RGB_KC_62", "Custom\nSlot 6", "RGB Mode: Custom Slot 6"),
    K("RGB_KC_63", "Custom\nSlot 7", "RGB Mode: Custom Slot 7"),
    K("RGB_KC_64", "Custom\nSlot 8", "RGB Mode: Custom Slot 8"),
    K("RGB_KC_65", "Custom\nSlot 9", "RGB Mode: Custom Slot 9"),
    K("RGB_KC_66", "Custom\nSlot 10", "RGB Mode: Custom Slot 10"),
    K("RGB_KC_67", "Custom\nSlot 11", "RGB Mode: Custom Slot 11"),
    K("RGB_KC_68", "Custom\nSlot 12", "RGB Mode: Custom Slot 12"),
    K("RGB_KC_69", "Custom\nSlot 13", "RGB Mode: Custom Slot 13"),
    K("RGB_KC_70", "Custom\nSlot 14", "RGB Mode: Custom Slot 14"),
    K("RGB_KC_71", "Custom\nSlot 15", "RGB Mode: Custom Slot 15"),
    K("RGB_KC_72", "Custom\nSlot 16", "RGB Mode: Custom Slot 16"),
    K("RGB_KC_73", "Custom\nSlot 17", "RGB Mode: Custom Slot 17"),
    K("RGB_KC_74", "Custom\nSlot 18", "RGB Mode: Custom Slot 18"),
    K("RGB_KC_75", "Custom\nSlot 19", "RGB Mode: Custom Slot 19"),
    K("RGB_KC_76", "Custom\nSlot 20", "RGB Mode: Custom Slot 20"),
    K("RGB_KC_77", "Custom\nSlot 21", "RGB Mode: Custom Slot 21"),
    K("RGB_KC_78", "Custom\nSlot 22", "RGB Mode: Custom Slot 22"),
    K("RGB_KC_79", "Custom\nSlot 23", "RGB Mode: Custom Slot 23"),
    K("RGB_KC_80", "Custom\nSlot 24", "RGB Mode: Custom Slot 24"),
    K("RGB_KC_81", "Custom\nSlot 25", "RGB Mode: Custom Slot 25"),
    K("RGB_KC_82", "Custom\nSlot 26", "RGB Mode: Custom Slot 26"),
    K("RGB_KC_83", "Custom\nSlot 27", "RGB Mode: Custom Slot 27"),
    K("RGB_KC_84", "Custom\nSlot 28", "RGB Mode: Custom Slot 28"),
    K("RGB_KC_85", "Custom\nSlot 29", "RGB Mode: Custom Slot 29"),
    K("RGB_KC_86", "Custom\nSlot 30", "RGB Mode: Custom Slot 30"),
    K("RGB_KC_87", "Custom\nSlot 31", "RGB Mode: Custom Slot 31"),
    K("RGB_KC_88", "Custom\nSlot 32", "RGB Mode: Custom Slot 32"),
    K("RGB_KC_89", "Custom\nSlot 33", "RGB Mode: Custom Slot 33"),
    K("RGB_KC_90", "Custom\nSlot 34", "RGB Mode: Custom Slot 34"),
    K("RGB_KC_91", "Custom\nSlot 35", "RGB Mode: Custom Slot 35"),
    K("RGB_KC_92", "Custom\nSlot 36", "RGB Mode: Custom Slot 36"),
    K("RGB_KC_93", "Custom\nSlot 37", "RGB Mode: Custom Slot 37"),
    K("RGB_KC_94", "Custom\nSlot 38", "RGB Mode: Custom Slot 38"),
    K("RGB_KC_95", "Custom\nSlot 39", "RGB Mode: Custom Slot 39"),
    K("RGB_KC_96", "Custom\nSlot 40", "RGB Mode: Custom Slot 40"),
    K("RGB_KC_97", "Custom\nSlot 41", "RGB Mode: Custom Slot 41"),
    K("RGB_KC_98", "Custom\nSlot 42", "RGB Mode: Custom Slot 42"),
    K("RGB_KC_99", "Custom\nSlot 43", "RGB Mode: Custom Slot 43"),
    K("RGB_KC_100", "Custom\nSlot 44", "RGB Mode: Custom Slot 44"),
    K("RGB_KC_101", "Custom\nSlot 45", "RGB Mode: Custom Slot 45"),
    K("RGB_KC_102", "Custom\nSlot 46", "RGB Mode: Custom Slot 46"),
    K("RGB_KC_103", "Custom\nSlot 47", "RGB Mode: Custom Slot 47"),
    K("RGB_KC_104", "Custom\nSlot 48", "RGB Mode: Custom Slot 48"),
    K("RGB_KC_105", "Custom\nSlot 49", "RGB Mode: Custom Slot 49"),
    K("RGB_KC_106", "Random 1\nLoop", "RGB Mode: Random 1 - Loop"),
    K("RGB_KC_107", "Random 2\nLoop", "RGB Mode: Random 2 - Loop"),
    K("RGB_KC_108", "Random 3\nLoop", "RGB Mode: Random 3 - Loop"),
    K("RGB_KC_109", "Random 1\nBPM", "RGB Mode: Random 1 - BPM"),
    K("RGB_KC_110", "Random 2\nBPM", "RGB Mode: Random 2 - BPM"),
    K("RGB_KC_111", "Random 3\nBPM", "RGB Mode: Random 3 - BPM"),
    K("RGB_KC_112", "Random 1\nManual", "RGB Mode: Random 1 - Manual"),
    K("RGB_KC_113", "Random 2\nManual", "RGB Mode: Random 2 - Manual"),
    K("RGB_KC_114", "Random 3\nManual", "RGB Mode: Random 3 - Manual"),
]

KEYCODES_RGB_KC_CUSTOM2 = [
    K("RGB_LAYERRECORD0", "Record\nRGB\nLyr 0", "Record Lighting Layer 0"),
    K("RGB_LAYERRECORD1", "Record\nRGB\nLyr 1", "Record Lighting Layer 0"),
    K("RGB_LAYERRECORD2", "Record\nRGB\nLyr 2", "Record Lighting Layer 0"),
    K("RGB_LAYERRECORD3", "Record\nRGB\nLyr 3", "Record Lighting Layer 0"),
    K("RGB_LAYERRECORD4", "Record\nRGB\nLyr 4", "Record Lighting Layer 0"),
    K("RGB_LAYERRECORD5", "Record\nRGB\nLyr 5", "Record Lighting Layer 0"),
    K("RGB_LAYERRECORD6", "Record\nRGB\nLyr 6", "Record Lighting Layer 0"),
    K("RGB_LAYERRECORD7", "Record\nRGB\nLyr 7", "Record Lighting Layer 0"),
    K("RGB_LAYERRECORD8", "Record\nRGB\nLyr 8", "Record Lighting Layer 0"),
    K("RGB_LAYERRECORD9", "Record\nRGB\nLyr 9", "Record Lighting Layer 0"),
    K("RGB_LAYERRECORD10", "Record\nRGB\nLyr 10", "Record Lighting Layer 0"),
    K("RGB_LAYERRECORD11", "Record\nRGB\nLyr 11", "Record Lighting Layer 0"),
]

KEYCODES_RGBSAVE = [
    K("RGB_LAYERSAVE", "RGB\nLayer\nMode On", "Save RGB settings"),
    K("RGB_LAYER_CUSTOM", "RGB\nLayer\nMode Off", "Save RGB settings"),
]

KEYCODES_EXWHEEL = [
    K("EXWHEEL_TRA", "Touch\nDial\nTranspose", "Touch dial: transpose"),
    K("EXWHEEL_VEL", "Touch\nDial\nDynamics", "Touch dial: dynamics (articulation)"),
    K("EXWHEEL_CHA", "Touch\nDial\nChannel", "Touch dial: channel"),
    K("EXWHEEL_SC", "Touch\nDial\nSmartChord", "Touch dial: SmartChord (encoder = chord up/down, press = play)"),
    K("EXWHEEL_BPM", "Touch\nDial\nBPM", "Touch dial: BPM (encoder = BPM up/down, press = Tap BPM)"),
]

KEYCODES_RGB_KC_COLOR = [
    K("RGB_KC_COLOR_1", "Azure", "RGB Color: Azure"),
    K("RGB_KC_COLOR_2", "Black", "RGB Color: Black/Off"),
    K("RGB_KC_COLOR_3", "Blue", "RGB Color: Blue"),
    K("RGB_KC_COLOR_4", "Chartreuse", "RGB Color: Chartreuse"),
    K("RGB_KC_COLOR_5", "Coral", "RGB Color: Coral"),
    K("RGB_KC_COLOR_6", "Cyan", "RGB Color: Cyan"),
    K("RGB_KC_COLOR_7", "Gold", "RGB Color: Gold"),
    K("RGB_KC_COLOR_8", "Goldenrod", "RGB Color: Goldenrod"),
    K("RGB_KC_COLOR_9", "Green", "RGB Color: Green"),
    K("RGB_KC_COLOR_10", "Magenta", "RGB Color: Magenta"),
    K("RGB_KC_COLOR_11", "Orange", "RGB Color: Orange"),
    K("RGB_KC_COLOR_12", "Pink", "RGB Color: Pink"),
    K("RGB_KC_COLOR_13", "Purple", "RGB Color: Purple"),
    K("RGB_KC_COLOR_14", "Red", "RGB Color: Red"),
    K("RGB_KC_COLOR_15", "Spring Green", "RGB Color: Spring Green"),
    K("RGB_KC_COLOR_16", "Teal", "RGB Color: Teal"),
    K("RGB_KC_COLOR_17", "Turquoise", "RGB Color: Turquoise"),
    K("RGB_KC_COLOR_18", "White", "RGB Color: White"),
    K("RGB_KC_COLOR_19", "Yellow", "RGB Color: Yellow")
]
# BASIC - MINOR PROGRESSIONS
# Chord Progression Slot Keycodes (20 slots, interval-based system)
# Tap = play/stop, Hold 2s = open OLED config menu
# (#audit) Each slot's type (Chords / Arp / Bass / Lead) is now stored per-slot in
# the firmware and set on-device, so the old fixed "Chord/Bass/Lead Machine N"
# labels misdescribed slots the user had reconfigured. Label generically by slot;
# the keycode identity (CPROG_SLOT_N) and default per-slot type are unchanged.
KEYCODES_CPROG_SLOTS = []  # removed: Rhythm Engine slots are bound via Master Quick Build

# VOICINGS AND OCTAVE CONTROLS
KEYCODES_CHORD_PROG_CONTROLS = []  # removed with the Chord Progressions section (BPM/tap keys live in KEYCODES_MIDI_ADVANCED)

KEYCODES_LOOP_BUTTONS = [
    # Main macro keys
    K("DM_MACRO_1", "Loop\n1", "Main loop/macro key 1"),
    K("DM_MACRO_2", "Loop\n2", "Main loop/macro key 2"),
    K("DM_MACRO_3", "Loop\n3", "Main loop/macro key 3"),
    K("DM_MACRO_4", "Loop\n4", "Main loop/macro key 4"),
    K("DM_REC5", "Loop\n5", "Main loop/macro key 5"),
    K("DM_REC6", "Loop\n6", "Main loop/macro key 6"),
    K("DM_REC7", "Loop\n7", "Main loop/macro key 7"),
    K("DM_REC8", "Loop\n8", "Main loop/macro key 8"),
    K("DM_NEXT_LOOP_REC", "Next\nLoop\nRec", "Starts recording the next empty loop (like pressing its button). If a loop is currently recording, starting the new one automatically stops it (the built-in quick record handoff), so the new recording begins right away. If nothing is recording, starts recording the first empty loop."),

    # ThruLoop transport keys (silent CC-only loop tracks 1-8)
    K("DM_THRULOOP_1", "Thru\n1", "ThruLoop 1: record/play/stop timing + ThruLoop CCs (no MIDI notes). Hold for menu."),
    K("DM_THRULOOP_2", "Thru\n2", "ThruLoop 2: record/play/stop timing + ThruLoop CCs (no MIDI notes). Hold for menu."),
    K("DM_THRULOOP_3", "Thru\n3", "ThruLoop 3: record/play/stop timing + ThruLoop CCs (no MIDI notes). Hold for menu."),
    K("DM_THRULOOP_4", "Thru\n4", "ThruLoop 4: record/play/stop timing + ThruLoop CCs (no MIDI notes). Hold for menu."),
    K("DM_THRULOOP_5", "Thru\n5", "ThruLoop 5: record/play/stop timing + ThruLoop CCs (no MIDI notes). Hold for menu."),
    K("DM_THRULOOP_6", "Thru\n6", "ThruLoop 6: record/play/stop timing + ThruLoop CCs (no MIDI notes). Hold for menu."),
    K("DM_THRULOOP_7", "Thru\n7", "ThruLoop 7: record/play/stop timing + ThruLoop CCs (no MIDI notes). Hold for menu."),
    K("DM_THRULOOP_8", "Thru\n8", "ThruLoop 8: record/play/stop timing + ThruLoop CCs (no MIDI notes). Hold for menu."),
    K("DM_NEXT_THRULOOP_REC", "Next\nThru\nRec", "Starts recording the next empty ThruLoop (like pressing its button). If a ThruLoop is currently recording, starting the new one automatically finishes it (the quick record handoff, deferred to the musical boundary when the unit is running), so the new recording takes over seamlessly. If nothing is recording, starts recording the first empty ThruLoop."),

    # Core control buttons
    K("DM_MUTE", "Mute\nButton", "Global mute button"),
    K("DM_OVERDUB", "Overdub\nButton", "Overdub recording button"),
    K("DM_UNSYNC", "Sync\nMode", "Toggle sync mode"),
    K("DM_SAMPLE", "Sample\nMode", "Toggle sample mode"),
    K("DM_EDIT_MOD", "Global\nEdit", "Global edit modifier button"),
    K("DM_PLAY_PAUSE", "Play\nPause", "Global play/pause toggle"),

    # Loop modifier keys
    K("DM_LOOP_MOD_1", "Loop 1\nModifier", "Loop modifier 1 (hold + loop for alt function)"),
    K("DM_LOOP_MOD_2", "Loop 2\nModifier", "Loop modifier 2 (hold + loop for alt function)"),
    K("DM_LOOP_MOD_3", "Loop 3\nModifier", "Loop modifier 3 (hold + loop for alt function)"),
    K("DM_LOOP_MOD_4", "Loop 4\nModifier", "Loop modifier 4 (hold + loop for alt function)"),
    K("DM_LOOP_MOD_5", "Loop 5\nModifier", "Loop modifier 5 (hold + loop for alt function)"),
    K("DM_LOOP_MOD_6", "Loop 6\nModifier", "Loop modifier 6 (hold + loop for alt function)"),
    K("DM_LOOP_MOD_7", "Loop 7\nModifier", "Loop modifier 7 (hold + loop for alt function)"),
    K("DM_LOOP_MOD_8", "Loop 8\nModifier", "Loop modifier 8 (hold + loop for alt function)"),

    # Dedicated mute keys
    K("DM_MUTE_1", "Mute\nLoop 1", "Dedicated mute for loop 1"),
    K("DM_MUTE_2", "Mute\nLoop 2", "Dedicated mute for loop 2"),
    K("DM_MUTE_3", "Mute\nLoop 3", "Dedicated mute for loop 3"),
    K("DM_MUTE_4", "Mute\nLoop 4", "Dedicated mute for loop 4"),
    K("DM_MUTE_5", "Mute\nLoop 5", "Dedicated mute for loop 5"),
    K("DM_MUTE_6", "Mute\nLoop 6", "Dedicated mute for loop 6"),
    K("DM_MUTE_7", "Mute\nLoop 7", "Dedicated mute for loop 7"),
    K("DM_MUTE_8", "Mute\nLoop 8", "Dedicated mute for loop 8"),
    
    # Octave doubler controls
    K("DM_OCT_1", "Octave\nDouble\nLoop 1", "Octave doubler toggle for loop 1"),
    K("DM_OCT_2", "Octave\nDouble\nLoop 2", "Octave doubler toggle for loop 2"),
    K("DM_OCT_3", "Octave\nDouble\nLoop 3", "Octave doubler toggle for loop 3"),
    K("DM_OCT_4", "Octave\nDouble\nLoop 4", "Octave doubler toggle for loop 4"),
    K("DM_OCT_5", "Octave\nDouble\nLoop 5", "Octave doubler toggle for loop 5"),
    K("DM_OCT_6", "Octave\nDouble\nLoop 6", "Octave doubler toggle for loop 6"),
    K("DM_OCT_7", "Octave\nDouble\nLoop 7", "Octave doubler toggle for loop 7"),
    K("DM_OCT_8", "Octave\nDouble\nLoop 8", "Octave doubler toggle for loop 8"),
    K("DM_OCT_MOD", "Octave\nModifier", "Octave doubler modifier (hold, then press a loop key to toggle that loop's octave doubler)"),
    K("OCT_DBL_TOGGLE", "Oct Dbl\nToggle", "Octave doubler modifier/toggle (hold=modifier, release=cycle Off/+1/+2/-1)"),
    K("CLEAR_HOLD", "Clear\nHold", "Hold, then press a loop or sequencer key to clear it"),
    
    # Speed controls
    K("DM_SPEED_MOD", "Speed\nModifier", "Speed modifier button (hold + loop)"),
    K("DM_SLOW_MOD", "Slow\nModifier", "Slow modifier button (hold + loop)"),
    K("DM_SPEED_1", "Speed\nLoop 1", "Individual speed toggle for loop 1"),
    K("DM_SPEED_2", "Speed\nLoop 2", "Individual speed toggle for loop 2"),
    K("DM_SPEED_3", "Speed\nLoop 3", "Individual speed toggle for loop 3"),
    K("DM_SPEED_4", "Speed\nLoop 4", "Individual speed toggle for loop 4"),
    K("DM_SPEED_5", "Speed\nLoop 5", "Individual speed toggle for loop 5"),
    K("DM_SPEED_6", "Speed\nLoop 6", "Individual speed toggle for loop 6"),
    K("DM_SPEED_7", "Speed\nLoop 7", "Individual speed toggle for loop 7"),
    K("DM_SPEED_8", "Speed\nLoop 8", "Individual speed toggle for loop 8"),
    K("DM_SPEED_ALL", "Speed\nAll\nLoops", "Speed up all macros"),
    K("DM_SLOW_1", "Slow\nLoop 1", "Individual slow toggle for loop 1"),
    K("DM_SLOW_2", "Slow\nLoop 2", "Individual slow toggle for loop 2"),
    K("DM_SLOW_3", "Slow\nLoop 3", "Individual slow toggle for loop 3"),
    K("DM_SLOW_4", "Slow\nLoop 4", "Individual slow toggle for loop 4"),
    K("DM_SLOW_5", "Slow\nLoop 5", "Individual slow toggle for loop 5"),
    K("DM_SLOW_6", "Slow\nLoop 6", "Individual slow toggle for loop 6"),
    K("DM_SLOW_7", "Slow\nLoop 7", "Individual slow toggle for loop 7"),
    K("DM_SLOW_8", "Slow\nLoop 8", "Individual slow toggle for loop 8"),
    K("DM_SLOW_ALL", "Slow\nAll\nLoops", "Slow up all macros"),
    K("DM_RESET_SPEED", "Reset\nSpeed", "Reset all speeds and BPM to original"),
    
    # Navigation controls
    K("DM_NAV_BWD_1S", "Nav\n◀ 1s", "Navigate backward 1 second"),
    K("DM_NAV_FWD_1S", "Nav\n1s ▶", "Navigate forward 1 second"),
    K("DM_NAV_BWD_5S", "Nav\n◀ 5s", "Navigate backward 5 seconds"),
    K("DM_NAV_FWD_5S", "Nav\n5s ▶", "Navigate forward 5 seconds"),
    
    # Fractional navigation (BeatSkip)
    K("DM_SKIP_0_8", "Beat\nSkip\n0/8", "Skip to start (0/8)"),
    K("DM_SKIP_1_8", "Beat\nSkip\n1/8", "Skip to 1/8 position"),
    K("DM_SKIP_2_8", "Beat\nSkip\n2/8", "Skip to 2/8 position"),
    K("DM_SKIP_3_8", "Beat\nSkip\n3/8", "Skip to 3/8 position"),
    K("DM_SKIP_4_8", "Beat\nSkip\n4/8", "Skip to middle (4/8)"),
    K("DM_SKIP_5_8", "Beat\nSkip\n5/8", "Skip to 5/8 position"),
    K("DM_SKIP_6_8", "Beat\nSkip\n6/8", "Skip to 6/8 position"),
    K("DM_SKIP_7_8", "Beat\nSkip\n7/8", "Skip to 7/8 position"),
    
    # Save and copy operations
    K("DM_COPY", "Copy\nLoop", "Copy loop operation"),
    K("DM_SAVE_1", "Save\nLoop 1", "Save loop 1 to file"),
    K("DM_SAVE_2", "Save\nLoop 2", "Save loop 2 to file"),
    K("DM_SAVE_3", "Save\nLoop 3", "Save loop 3 to file"),
    K("DM_SAVE_4", "Save\nLoop 4", "Save loop 4 to file"),
    K("DM_SAVE_ALL", "Save\nAll", "Save all loops to file"),
        
    # Overdub operations
    K("DM_OVERDUB_1", "Overdub\nLoop 1", "Overdub loop 1"),
    K("DM_OVERDUB_2", "Overdub\nLoop 2", "Overdub loop 2"),
    K("DM_OVERDUB_3", "Overdub\nLoop 3", "Overdub loop 3"),
    K("DM_OVERDUB_4", "Overdub\nLoop 4", "Overdub loop 4"),
    K("DM_OVERDUB_5", "Overdub\nLoop 5", "Overdub loop 5"),
    K("DM_OVERDUB_6", "Overdub\nLoop 6", "Overdub loop 6"),
    K("DM_OVERDUB_7", "Overdub\nLoop 7", "Overdub loop 7"),
    K("DM_OVERDUB_8", "Overdub\nLoop 8", "Overdub loop 8"),

    # Overdub mute operations
    K("DM_OVERDUB_MUTE_1", "Overdub\nMute 1", "Overdub mute loop 1"),
    K("DM_OVERDUB_MUTE_2", "Overdub\nMute 2", "Overdub mute loop 2"),
    K("DM_OVERDUB_MUTE_3", "Overdub\nMute 3", "Overdub mute loop 3"),
    K("DM_OVERDUB_MUTE_4", "Overdub\nMute 4", "Overdub mute loop 4"),
    K("DM_OVERDUB_MUTE_5", "Overdub\nMute 5", "Overdub mute loop 5"),
    K("DM_OVERDUB_MUTE_6", "Overdub\nMute 6", "Overdub mute loop 6"),
    K("DM_OVERDUB_MUTE_7", "Overdub\nMute 7", "Overdub mute loop 7"),
    K("DM_OVERDUB_MUTE_8", "Overdub\nMute 8", "Overdub mute loop 8"),

    # Loop advanced controls
    K("LOOP_QUANTIZE", "Loop\nQuantize", "Quantize loop timing"),
    K("LOOP_BPM_DOUBLE", "Loop\nBPM x2", "Double loop BPM"),
]

# DrumLIVE — live drum note filter. A filter on outgoing drum-channel notes:
# Mute (block), Quiet (-50% vel), Loud (+50% vel), Solo ("only"). Targets are
# the 6 category groups and the 12 individual drum voices. Each mode keycode
# toggles that target (press again to clear). The menu/reset keys round it out.
def _build_drumlive_keycodes():
    out = [
        K("DRUMLIVE_MENU", "DrumLIVE\nMenu", "Open the DrumLIVE filter menu on the device (Presets / Basic / Advanced)"),
        K("DRUMLIVE_RESET", "DrumLIVE\nAll On", "Clear all DrumLIVE filters (every target back to On)"),
        K("DRUMLIVE_ALL_OFF", "DrumLIVE\nAll Off", "Mute every drum target (turn one back On for a solo)"),
    ]
    # modeidx -> (short label fragment, tooltip verb). On is the cleared state,
    # so only Off/Quiet/Loud get keycodes (press again to return to On).
    modes = [
        ("No",    "Off — block {}"),
        ("Quiet", "{} at -50% velocity"),
        ("Loud",  "{} at +50% velocity"),
    ]
    cat_names = ["Kicks", "Snares", "Hats", "Cymbals", "Toms", "Perc"]
    voice_names = ["Kick", "Snare", "ClosedHH", "OpenHH", "Clap", "Rimshot",
                   "Cowbell", "Cymbal", "LowTom", "MidTom", "HiTom", "Shaker"]
    for c, cname in enumerate(cat_names):
        for m, (frag, tip) in enumerate(modes):
            out.append(K("DRUMLIVE_CAT_{}_{}".format(c, m),
                         "{}\n{}".format(frag, cname), tip.format(cname + " group")))
    for v, vname in enumerate(voice_names):
        for m, (frag, tip) in enumerate(modes):
            out.append(K("DRUMLIVE_VOICE_{}_{}".format(v, m),
                         "{}\n{}".format(frag, vname), tip.format(vname)))
    return out

KEYCODES_DRUMLIVE = _build_drumlive_keycodes()

# Gaming Controller Keycodes
KEYCODES_GAMING = [
    # Toggle gaming mode
    K("GAMING_MODE", "Gaming\nMode", "Toggle gaming mode on/off. When on, keys assigned in the Gaming Settings tab act as gamepad inputs."),

    # Digital Buttons (Face buttons)
    K("XBOX_A", "Button\n1", "Button 1 (Button 0)"),
    K("XBOX_B", "Button\n2", "Button 2 (Button 1)"),
    K("XBOX_X", "Button\n3", "Button 3 (Button 2)"),
    K("XBOX_Y", "Button\n4", "Button 4 (Button 3)"),

    # Shoulder Buttons
    K("XBOX_LB", "LB", "Left bumper (Button 4)"),
    K("XBOX_RB", "RB", "Right bumper (Button 5)"),

    # Center Buttons
    K("XBOX_BACK", "Back", "Back/Select (Button 6)"),
    K("XBOX_START", "Start", "Start (Button 7)"),

    # Stick Click Buttons
    K("XBOX_L3", "L3", "Left stick click (Button 8)"),
    K("XBOX_R3", "R3", "Right stick click (Button 9)"),

    # Left Analog Stick (Hall Effect)
    K("LS_UP", "LS ↑", "Left stick up (Axis 1 negative)"),
    K("LS_DOWN", "LS ↓", "Left stick down (Axis 1 positive)"),
    K("LS_LEFT", "LS ←", "Left stick left (Axis 0 negative)"),
    K("LS_RIGHT", "LS →", "Left stick right (Axis 0 positive)"),

    # Right Analog Stick (Hall Effect)
    K("RS_UP", "RS ↑", "Right stick up (Axis 3 negative)"),
    K("RS_DOWN", "RS ↓", "Right stick down (Axis 3 positive)"),
    K("RS_LEFT", "RS ←", "Right stick left (Axis 2 negative)"),
    K("RS_RIGHT", "RS →", "Right stick right (Axis 2 positive)"),

    # Analog Triggers (Hall Effect)
    K("LT", "LT", "Left trigger (Axis 4, 0-127 based on press depth)"),
    K("RT", "RT", "Right trigger (Axis 5, 0-127 based on press depth)"),

    # D-pad (Digital directional pad)
    K("DPAD_UP", "D-pad ↑", "D-pad Up (Button 12)"),
    K("DPAD_DOWN", "D-pad ↓", "D-pad Down (Button 13)"),
    K("DPAD_LEFT", "D-pad ←", "D-pad Left (Button 14)"),
    K("DPAD_RIGHT", "D-pad →", "D-pad Right (Button 15)"),
]


KEYCODES_ARPEGGIATOR = [
    # Control keycodes
    K("ARP_PLAY", "Play\nArp", "Arpeggiator play/stop toggle"),
    K("ARP_NEXT_PRESET", "Next\nPreset", "Load next arpeggiator preset"),
    K("ARP_PREV_PRESET", "Prev\nPreset", "Load previous arpeggiator preset"),
    K("ARP_SYNC_MODE", "Sync\nMode", "Toggle arpeggiator sync mode"),
    K("ARP_GATE_RESET", "Gate\nReset", "Reset gate to preset default"),
    K("ARP_RESET_OVERRIDES", "Reset\nOverrides", "Reset all arpeggiator overrides"),

    # Gate up controls (1-10%)
    K("ARP_GATE_1_UP", "Gate\n+1%", "Increase arpeggiator gate (+1%)"),
    K("ARP_GATE_2_UP", "Gate\n+2%", "Increase arpeggiator gate (+2%)"),
    K("ARP_GATE_3_UP", "Gate\n+3%", "Increase arpeggiator gate (+3%)"),
    K("ARP_GATE_4_UP", "Gate\n+4%", "Increase arpeggiator gate (+4%)"),
    K("ARP_GATE_5_UP", "Gate\n+5%", "Increase arpeggiator gate (+5%)"),
    K("ARP_GATE_6_UP", "Gate\n+6%", "Increase arpeggiator gate (+6%)"),
    K("ARP_GATE_7_UP", "Gate\n+7%", "Increase arpeggiator gate (+7%)"),
    K("ARP_GATE_8_UP", "Gate\n+8%", "Increase arpeggiator gate (+8%)"),
    K("ARP_GATE_9_UP", "Gate\n+9%", "Increase arpeggiator gate (+9%)"),
    K("ARP_GATE_10_UP", "Gate\n+10%", "Increase arpeggiator gate (+10%)"),

    # Gate down controls (1-10%)
    K("ARP_GATE_1_DOWN", "Gate\n-1%", "Decrease arpeggiator gate (-1%)"),
    K("ARP_GATE_2_DOWN", "Gate\n-2%", "Decrease arpeggiator gate (-2%)"),
    K("ARP_GATE_3_DOWN", "Gate\n-3%", "Decrease arpeggiator gate (-3%)"),
    K("ARP_GATE_4_DOWN", "Gate\n-4%", "Decrease arpeggiator gate (-4%)"),
    K("ARP_GATE_5_DOWN", "Gate\n-5%", "Decrease arpeggiator gate (-5%)"),
    K("ARP_GATE_6_DOWN", "Gate\n-6%", "Decrease arpeggiator gate (-6%)"),
    K("ARP_GATE_7_DOWN", "Gate\n-7%", "Decrease arpeggiator gate (-7%)"),
    K("ARP_GATE_8_DOWN", "Gate\n-8%", "Decrease arpeggiator gate (-8%)"),
    K("ARP_GATE_9_DOWN", "Gate\n-9%", "Decrease arpeggiator gate (-9%)"),
    K("ARP_GATE_10_DOWN", "Gate\n-10%", "Decrease arpeggiator gate (-10%)"),

    # Rate overrides
    K("ARP_RATE_QUARTER", "Quarter\nNotes", "Arpeggiator rate: quarter notes"),
    K("ARP_RATE_QUARTER_DOT", "Quarter\nDotted", "Arpeggiator rate: dotted quarter"),
    K("ARP_RATE_QUARTER_TRIP", "Quarter\nTriplet", "Arpeggiator rate: triplet quarter"),
    K("ARP_RATE_EIGHTH", "Eighth\nNotes", "Arpeggiator rate: eighth notes"),
    K("ARP_RATE_EIGHTH_DOT", "Eighth\nDotted", "Arpeggiator rate: dotted eighth"),
    K("ARP_RATE_EIGHTH_TRIP", "Eighth\nTriplet", "Arpeggiator rate: triplet eighth"),
    K("ARP_RATE_SIXTEENTH", "16th\nNotes", "Arpeggiator rate: sixteenth notes"),
    K("ARP_RATE_SIXTEENTH_DOT", "16th\nDotted", "Arpeggiator rate: dotted sixteenth"),
    K("ARP_RATE_SIXTEENTH_TRIP", "16th\nTriplet", "Arpeggiator rate: triplet sixteenth"),
    K("ARP_RATE_RESET", "Rate\nReset", "Reset to preset's default rate"),

    # NEW: Rate cycling
    K("ARP_RATE_UP", "Rate\nUp", "Cycle to next arpeggiator rate"),
    K("ARP_RATE_DOWN", "Rate\nDown", "Cycle to previous arpeggiator rate"),

    # NEW: Static gate values
    K("ARP_SET_GATE_10", "Gate\n10%", "Set arpeggiator gate to 10%"),
    K("ARP_SET_GATE_20", "Gate\n20%", "Set arpeggiator gate to 20%"),
    K("ARP_SET_GATE_30", "Gate\n30%", "Set arpeggiator gate to 30%"),
    K("ARP_SET_GATE_40", "Gate\n40%", "Set arpeggiator gate to 40%"),
    K("ARP_SET_GATE_50", "Gate\n50%", "Set arpeggiator gate to 50%"),
    K("ARP_SET_GATE_60", "Gate\n60%", "Set arpeggiator gate to 60%"),
    K("ARP_SET_GATE_70", "Gate\n70%", "Set arpeggiator gate to 70%"),
    K("ARP_SET_GATE_80", "Gate\n80%", "Set arpeggiator gate to 80%"),
    K("ARP_SET_GATE_90", "Gate\n90%", "Set arpeggiator gate to 90%"),
    K("ARP_SET_GATE_100", "Gate\n100%", "Set arpeggiator gate to 100%"),


    # Gate quick controls
    K("ARP_GATE_UP", "Gate\nUp 10%", "Increase arpeggiator gate by 10%"),
    K("ARP_GATE_DOWN", "Gate\nDn 10%", "Decrease arpeggiator gate by 10%"),

    # Quick Build
]

# Generate preset selection keycodes (200 factory rhythm arps + 40 user = 240 total)
#
# Factory presets 0-199 are single-note "rhythm arpeggios": 10 categories x 20,
# id = category*20 + slot. The name (category prefix + rate + tag) mirrors the
# firmware generator in arp_factory_presets.c so the GUI label matches the OLED.
def _arp_factory_name(idn):
    # Mirrors arp_fac_describe() in arp_factory_presets.c. One entry per PATTERN
    # (rate/gate are per-master flags, not separate presets). 10 categories:
    #   Basic 0, Ascending 1-3, Descending 4-6, Syncopated 7-29, Off Beat 30-38,
    #   Rock 39-50, Funk 51-67, Hip 68-82, Dance 83-100, Chords 101-118.
    # Returns (pfx, tag).
    gap_grids = {
        3:  ("Syn", ["Tres", "Clave", "Rmba", "Hban", "Dmbw", "Boss", "Smba", "Cscr", "Funk",
                     "Son23", "Rmb23", "Bmbe", "ChaCh", "Cumb", "Baio", "Part", "Mrct", "Gahu",
                     "Calyp", "Soca", "Plena", "Bomba", "Guajr"]),
        4:  ("Off", ["Off8", "Off16", "Push", "Chrl", "Stab", "Drop", "Lilt", "Sync", "OneDr"]),
        5:  ("Rock", None), 6: ("Funk", None), 7: ("Hip", None), 8: ("EDM", None),  # numbered
    }
    ch_pfx   = ["5th", "Maj", "Min", "Maj7", "Min7", "Dom7"]
    cats     = [(0, 1), (1, 3), (4, 3), (7, 23), (30, 9),
                (39, 12), (51, 17), (68, 15), (83, 18), (101, 18)]
    cat = 0
    for ci, (off, cnt) in enumerate(cats):
        if off <= idn < off + cnt:
            cat, base = ci, off
            break
    k = idn - base
    if cat == 0:        # Basic
        return "Basic", ""
    if cat in (1, 2):   # Ascending / Descending (velocity ramp x1/x2/x4)
        ramp = [1, 2, 4][k if k < 3 else 0]
        return ("Asc" if cat == 1 else "Desc"), "x{}".format(ramp)
    if cat in gap_grids:   # Syncopated / Off Beat / Rock / Funk / Hip / Dance
        pfx, names = gap_grids[cat]
        if names is None:           # Western banks are numbered
            return pfx, str(k + 1)
        return pfx, names[k]
    # Chords: 6 types x {Flat/Rise/Fall}
    t, vs = k // 3, k % 3
    return ch_pfx[t], ["Flat", "Rise", "Fall"][vs]

KEYCODES_ARPEGGIATOR_PRESETS = []
# User presets only (119-158, displayed as User 1-40). Factory rhythm patterns
# are managed via the Master Quick Build menu and are not exposed in the GUI.
for x in range(119, 159):
    user_num = x - 118
    KEYCODES_ARPEGGIATOR_PRESETS.append(
        K("ARP_PRESET_{}".format(x), "Arp\nUser\n{}".format(user_num), "Load arpeggiator user preset {}".format(user_num))
    )


KEYCODES_STEP_SEQUENCER = [
    # Control keycodes
    K("SEQ_PLAY", "Play\nSeq", "Step sequencer play"),
    K("SEQ_STOP_ALL", "Stop\nAll Seq", "Stop all step sequencers"),
    K("SEQ_NEXT_PRESET", "Next\nPreset", "Load next sequencer preset"),
    K("SEQ_PREV_PRESET", "Prev\nPreset", "Load previous sequencer preset"),
    K("SEQ_SYNC_MODE", "Sync\nMode", "Toggle sequencer sync mode"),
    K("SEQ_GATE_RESET", "Gate\nReset", "Reset gate to preset default"),
    K("SEQ_RESET_OVERRIDES", "Reset\nOverrides", "Reset all sequencer overrides"),

    # Gate up controls (1-10%)
    K("SEQ_GATE_1_UP", "Gate\n+1%", "Increase sequencer gate (+1%)"),
    K("SEQ_GATE_2_UP", "Gate\n+2%", "Increase sequencer gate (+2%)"),
    K("SEQ_GATE_3_UP", "Gate\n+3%", "Increase sequencer gate (+3%)"),
    K("SEQ_GATE_4_UP", "Gate\n+4%", "Increase sequencer gate (+4%)"),
    K("SEQ_GATE_5_UP", "Gate\n+5%", "Increase sequencer gate (+5%)"),
    K("SEQ_GATE_6_UP", "Gate\n+6%", "Increase sequencer gate (+6%)"),
    K("SEQ_GATE_7_UP", "Gate\n+7%", "Increase sequencer gate (+7%)"),
    K("SEQ_GATE_8_UP", "Gate\n+8%", "Increase sequencer gate (+8%)"),
    K("SEQ_GATE_9_UP", "Gate\n+9%", "Increase sequencer gate (+9%)"),
    K("SEQ_GATE_10_UP", "Gate\n+10%", "Increase sequencer gate (+10%)"),

    # Gate down controls (1-10%)
    K("SEQ_GATE_1_DOWN", "Gate\n-1%", "Decrease sequencer gate (-1%)"),
    K("SEQ_GATE_2_DOWN", "Gate\n-2%", "Decrease sequencer gate (-2%)"),
    K("SEQ_GATE_3_DOWN", "Gate\n-3%", "Decrease sequencer gate (-3%)"),
    K("SEQ_GATE_4_DOWN", "Gate\n-4%", "Decrease sequencer gate (-4%)"),
    K("SEQ_GATE_5_DOWN", "Gate\n-5%", "Decrease sequencer gate (-5%)"),
    K("SEQ_GATE_6_DOWN", "Gate\n-6%", "Decrease sequencer gate (-6%)"),
    K("SEQ_GATE_7_DOWN", "Gate\n-7%", "Decrease sequencer gate (-7%)"),
    K("SEQ_GATE_8_DOWN", "Gate\n-8%", "Decrease sequencer gate (-8%)"),
    K("SEQ_GATE_9_DOWN", "Gate\n-9%", "Decrease sequencer gate (-9%)"),
    K("SEQ_GATE_10_DOWN", "Gate\n-10%", "Decrease sequencer gate (-10%)"),

    # Rate overrides
    K("SEQ_RATE_QUARTER", "Quarter\nNotes", "Sequencer rate: quarter notes"),
    K("SEQ_RATE_QUARTER_DOT", "Quarter\nDotted", "Sequencer rate: dotted quarter"),
    K("SEQ_RATE_QUARTER_TRIP", "Quarter\nTriplet", "Sequencer rate: triplet quarter"),
    K("SEQ_RATE_EIGHTH", "Eighth\nNotes", "Sequencer rate: eighth notes"),
    K("SEQ_RATE_EIGHTH_DOT", "Eighth\nDotted", "Sequencer rate: dotted eighth"),
    K("SEQ_RATE_EIGHTH_TRIP", "Eighth\nTriplet", "Sequencer rate: triplet eighth"),
    K("SEQ_RATE_SIXTEENTH", "16th\nNotes", "Sequencer rate: sixteenth notes"),
    K("SEQ_RATE_SIXTEENTH_DOT", "16th\nDotted", "Sequencer rate: dotted sixteenth"),
    K("SEQ_RATE_SIXTEENTH_TRIP", "16th\nTriplet", "Sequencer rate: triplet sixteenth"),
    K("SEQ_RATE_RESET", "Rate\nReset", "Reset to preset's default rate"),
    K("SEQ_DOUBLE_TIME", "Double\nTime", "Toggle double-time (2x speed)"),

    # NEW: Rate cycling
    K("SEQ_RATE_UP", "Rate\nUp", "Cycle to next sequencer rate"),
    K("SEQ_RATE_DOWN", "Rate\nDown", "Cycle to previous sequencer rate"),

    # NEW: Static gate values
    K("STEP_SET_GATE_10", "Gate\n10%", "Set sequencer gate to 10%"),
    K("STEP_SET_GATE_20", "Gate\n20%", "Set sequencer gate to 20%"),
    K("STEP_SET_GATE_30", "Gate\n30%", "Set sequencer gate to 30%"),
    K("STEP_SET_GATE_40", "Gate\n40%", "Set sequencer gate to 40%"),
    K("STEP_SET_GATE_50", "Gate\n50%", "Set sequencer gate to 50%"),
    K("STEP_SET_GATE_60", "Gate\n60%", "Set sequencer gate to 60%"),
    K("STEP_SET_GATE_70", "Gate\n70%", "Set sequencer gate to 70%"),
    K("STEP_SET_GATE_80", "Gate\n80%", "Set sequencer gate to 80%"),
    K("STEP_SET_GATE_90", "Gate\n90%", "Set sequencer gate to 90%"),
    K("STEP_SET_GATE_100", "Gate\n100%", "Set sequencer gate to 100%"),

    # (Removed: SEQ_MOD_1..8 dedicated seq modifier buttons — seq modifiers are now
    #  selected via Global Modifier + tapping the user step sequencer.)

    # Gate quick controls
    K("SEQ_GATE_UP", "Gate\nUp 10%", "Increase sequencer gate by 10%"),
    K("SEQ_GATE_DOWN", "Gate\nDn 10%", "Decrease sequencer gate by 10%"),

    # Quick Build
]

# Octave Doubler & Temporary Transposition keycodes
KEYCODES_OCTAVE_DOUBLER = [
    K("OCT_DBL_TOGGLE", "Oct Dbl\nToggle", "Octave doubler modifier/toggle (hold=modifier, release=cycle Off/+1/+2/-1)"),
    K("OCT_DBL_PLUS1", "Oct Dbl\n+1", "Set octave doubler to +1 octave (+12 semitones)"),
    K("OCT_DBL_PLUS2", "Oct Dbl\n+2", "Set octave doubler to +2 octaves (+24 semitones)"),
    K("OCT_DBL_MINUS1", "Oct Dbl\n-1", "Set octave doubler to -1 octave (-12 semitones)"),
    K("OCT_DBL_OFF", "Oct Dbl\nOff", "Turn off octave doubler"),
    K("TEMP_TRANS_PLUS12", "Temp\nTrans\n+12", "Hold: temporarily add +12 to transposition"),
    K("TEMP_TRANS_PLUS24", "Temp\nTrans\n+24", "Hold: temporarily add +24 to transposition"),
    K("TEMP_TRANS_MINUS12", "Temp\nTrans\n-12", "Hold: temporarily add -12 to transposition"),
]

# Generate preset selection keycodes.
# NOTE: the first 20 SEQ_PRESET keycodes (0xED98-0xEDAB) are the persistent
# DRUM MACHINE slots (MAX_FACTORY_SEQ_SLOTS = 20), not step-sequencer presets —
# tapping one opens/plays its drum slot. Only 20-87 are step-seq presets.
KEYCODES_DRUM_SLOTS = []
# Drum machine slots 0-19 (persistent slots, configured on-device)
for x in range(20):
    KEYCODES_DRUM_SLOTS.append(
        K("SEQ_PRESET_{}".format(x), "Drum\nSlot\n{}".format(x + 1), "Drum machine slot {}".format(x + 1))
    )

KEYCODES_STEP_SEQUENCER_PRESETS = []
# User presets 48-87 (displayed as User 1-40). Factory step-seq presets 20-47
# are managed via the Master Quick Build menu and are not exposed in the GUI.
for x in range(48, 88):
    user_num = x - 47
    KEYCODES_STEP_SEQUENCER_PRESETS.append(
        K("SEQ_PRESET_{}".format(x), "Seq\nUser\n{}".format(user_num), "Load sequencer user preset {}".format(user_num))
    )


# DKS (Dynamic Keystroke) slot keycodes (50 slots)
KEYCODES_DKS = []
for x in range(50):
    KEYCODES_DKS.append(
        K("DKS_{:02d}".format(x), "Dynamic\nKeystroke\n{}".format(x), "Dynamic Keystroke slot {} - multi-action analog key".format(x))
    )

# Toggle key slot keycodes (100 slots)
KEYCODES_TOGGLE = []
for x in range(100):
    KEYCODES_TOGGLE.append(
        K("TGL_{:02d}".format(x), "Toggle\n{}".format(x), "Toggle key slot {} - toggle keycode held/released".format(x))
    )

# Toggle bulk-reset action keys (act on ALL toggle slots at once)
KEYCODES_TOGGLE_ACTIONS = [
    K("TOGGLE_RESET_MULTI", "Reset\nMulti-\nToggles", "Puts every multi-key toggle back on its first step (as after keyboard startup). Only rewinds the step position - no keycodes are pressed or released."),
    K("TOGGLE_UNHOLD_ALL", "Reset\nToggles", "Releases (\"unholds\") every held hold-type toggle. Multi-key toggles are not affected - only standard toggles whose target key is currently held down."),
]

# MIDI Delay control keycodes (navigation + clear)
KEYCODES_DELAY_CLEAR = [
    K("DELAY_PREV", "Delay\nPrev", "Cycle to previous delay slot"),
    K("DELAY_NEXT", "Delay\nNext", "Cycle to next delay slot"),
    K("DELAY_ONOFF", "Delay\nOn/Off", "Toggle selected delay on/off (exclusive)"),
    K("DELAY_CLEAR", "Delay\nClear", "Clear all active delays and stop queue"),
]

# MIDI Delay slot keycodes (98 total: 48 factory + 50 user)
# Factory presets are const in firmware flash. User slots are in EEPROM.
# Unified keycode range: DELAY_01-DELAY_98, indices 0-47 factory, 48-97 user

# Factory preset keycodes (48): always visible, read-only
KEYCODES_DELAY_FACTORY = []

_delay_rates = ["1/1", "1/2", "1/4", "1/8", "1/16"]
_delay_timings = ["Note", "Dot.", "Trip"]  # Straight, Dotted, Triplet (matches firmware order)
_delay_decays = ["Short", "Med", "Long"]   # 38%, 20%, 11%

for r in range(5):
    for t in range(3):
        for d in range(3):
            idx = r * 9 + t * 3 + d
            label = "{} {}\nDecay\n{}".format(_delay_rates[r], _delay_timings[t], _delay_decays[d])
            tooltip = "Factory delay {}: {} {} decay {}".format(idx + 1, _delay_rates[r], _delay_timings[t], _delay_decays[d])
            KEYCODES_DELAY_FACTORY.append(
                K("DELAY_{:02d}".format(idx + 1), label, tooltip)
            )

# Pitch delay presets (factory slots 45-47)
_pitch_rates = ["1/4", "1/8", "1/16"]
for p in range(3):
    idx = 45 + p
    label = "{} Note\nPitch\nDelay".format(_pitch_rates[p])
    tooltip = "Factory delay {}: {} pitch delay (+12 semi cumulative)".format(idx + 1, _pitch_rates[p])
    KEYCODES_DELAY_FACTORY.append(
        K("DELAY_{:02d}".format(idx + 1), label, tooltip)
    )

# User delay slot keycodes (50): shown based on _visible_tab_count
KEYCODES_DELAY_USER = []
for x in range(50):
    unified_idx = 48 + x  # Unified index (factory count + user index)
    KEYCODES_DELAY_USER.append(
        K("DELAY_{:02d}".format(unified_idx + 1), "User\nDelay\n{}".format(x + 1),
          "User delay slot {} - toggle delay effect on/off".format(x + 1))
    )

# Combined for backward compat
KEYCODES_DELAY = KEYCODES_DELAY_FACTORY + KEYCODES_DELAY_USER

# =============================================================================
# Quick Build: Delay / Smart Chord / Dynamic Chord
# =============================================================================

KEYCODES_DELAY_QB = []  # removed: only Master Quick Build buttons are supported

KEYCODES_CHORD_QB = []  # removed: only Master Quick Build buttons are supported

# SmartChord voice-leading override.  Each press cycles a single-rule
# Highest-voice override that masks per-voice menu config.  Reopening the
# SmartChord menu (hold a smartchord key) clears the override.
KEYCODES_SMARTCHORD_VL = [
    K("MI_SC_VL_UP",   "SC VL\n+",  "Cycle Highest voice-leading rule forward (None/Desc/Asc/Alt/Tight)"),
    K("MI_SC_VL_DOWN", "SC VL\n-",  "Cycle Highest voice-leading rule backward"),
]

KEYCODES_DYNCHORD_QB = []  # removed: only Master Quick Build buttons are supported

KEYCODES_FADER_QB = []  # removed: only Master Quick Build buttons are supported

# Master Quick Build slots — 50 programmable keys.  Each keycode stores
# its own {category, slot} assignment in EEPROM, so you can place them
# freely and configure each one on-device. Tap unconfigured = picker;
# tap configured = acts as the assigned target keycode (Arp QB / Seq QB
# / SmartChord / Fader / drum machine / chord prog / ear trainer).
KEYCODES_QB_MASTER = [
    K("QB_MASTER_{}".format(i + 1),
      "Quickbuild\n{}".format(i + 1),
      "Quickbuild slot {} - tap: picker (unconfigured) or run assigned target".format(i + 1))
    for i in range(100)
]

# Ear Trainer Quick Build — 10 per-key slots.  Tap starts a session
# (countdown, play, answer picker, streak).  Hold 2 s opens setup to pick
# mode (intervals/chords), preset or custom selection, and difficulty.
KEYCODES_EARTRAINER_QB = []  # removed: only Master Quick Build buttons are supported

# =============================================================================
# UNIFIED DAW Shortcut Keycodes
# =============================================================================
# These keycodes send keyboard shortcuts that adapt to the currently selected DAW.
# Use DAW_SELECT to cycle through: Ableton Live, FL Studio, Logic Pro, Pro Tools,
# GarageBand, Cubase, Reaper, Studio One, Bitwig Studio.
# Use DAW_OS to toggle Mac/Windows modifier mode (Cmd vs Ctrl).

KEYCODES_DAW = [
    # Meta / Selector
    K("DAW_SELECT", "DAW\nNext", "Cycle to next DAW (Ableton/FL/Logic/PT/GB/Cubase/Reaper/S1/Bitwig)"),
    K("DAW_PREV", "DAW\nPrev", "Cycle to previous DAW"),
    K("DAW_OS", "DAW\nOS", "Toggle Mac/Windows modifier mode (Cmd vs Ctrl)"),

    # Transport Controls
    K("DAW_PLAY", "Play", "DAW: Play/Pause - adapts to selected DAW"),
    K("DAW_STOP", "Stop", "DAW: Stop - adapts to selected DAW"),
    K("DAW_RECORD", "Record", "DAW: Record - adapts to selected DAW"),
    K("DAW_LOOP", "Loop", "DAW: Toggle Loop/Cycle - adapts to selected DAW"),
    K("DAW_REWIND", "Rewind", "DAW: Go to Start / Return to Zero - adapts to selected DAW"),
    K("DAW_METRONOME", "Metro", "DAW: Toggle Metronome/Click - adapts to selected DAW"),
    # Editing
    K("DAW_UNDO", "Undo", "DAW: Undo - adapts to selected DAW"),
    K("DAW_REDO", "Redo", "DAW: Redo - adapts to selected DAW"),
    K("DAW_CUT", "Cut", "DAW: Cut - adapts to selected DAW"),
    K("DAW_COPY", "Copy", "DAW: Copy - adapts to selected DAW"),
    K("DAW_PASTE", "Paste", "DAW: Paste - adapts to selected DAW"),
    K("DAW_DUPLICATE", "Dupe", "DAW: Duplicate - adapts to selected DAW"),
    K("DAW_DELETE", "Delete", "DAW: Delete - adapts to selected DAW"),
    K("DAW_SPLIT", "Split", "DAW: Split at Cursor/Playhead - adapts to selected DAW"),
    K("DAW_QUANTIZE", "Quant", "DAW: Quantize - adapts to selected DAW"),
    K("DAW_JOIN", "Join", "DAW: Join/Consolidate/Glue - adapts to selected DAW"),
    K("DAW_SELECT_ALL", "Select\nAll", "DAW: Select All - adapts to selected DAW"),

    # Track Controls
    K("DAW_SOLO", "Solo", "DAW: Solo selected track - adapts to selected DAW"),
    K("DAW_MUTE", "Mute", "DAW: Mute selected track - adapts to selected DAW"),
    K("DAW_ARM", "Arm", "DAW: Arm/Record Enable - adapts to selected DAW"),
    K("DAW_TRACK_UP", "Track\nUp", "DAW: Select previous track - adapts to selected DAW"),
    K("DAW_TRACK_DOWN", "Track\nDown", "DAW: Select next track - adapts to selected DAW"),
    K("DAW_NEW_TRACK", "New\nTrack", "DAW: New track - adapts to selected DAW"),
    K("DAW_GROUP", "Group", "DAW: Group tracks - adapts to selected DAW"),

    # Navigation & Zoom
    K("DAW_ZOOM_IN", "Zoom\nIn", "DAW: Zoom In - adapts to selected DAW"),
    K("DAW_ZOOM_OUT", "Zoom\nOut", "DAW: Zoom Out - adapts to selected DAW"),
    K("DAW_ZOOM_FIT", "Zoom\nFit", "DAW: Zoom to Fit - adapts to selected DAW"),

    # Views
    K("DAW_MIXER", "Mixer", "DAW: Toggle Mixer - adapts to selected DAW"),
    K("DAW_BROWSER", "Browser", "DAW: Toggle Browser/Media - adapts to selected DAW"),
    K("DAW_PIANO_ROLL", "Piano\nRoll", "DAW: Toggle Piano Roll/MIDI Editor - adapts to selected DAW"),
    K("DAW_AUTOMATION", "Auto\nView", "DAW: Toggle Automation View - adapts to selected DAW"),

    # File Operations
    K("DAW_SAVE", "Save", "DAW: Save - adapts to selected DAW"),
    K("DAW_SAVE_AS", "Save\nAs", "DAW: Save As - adapts to selected DAW"),
    K("DAW_EXPORT", "Export", "DAW: Export/Bounce/Render - adapts to selected DAW"),

]

KEYCODES_HIDDEN = []
for x in range(256):
    KEYCODES_HIDDEN.append(K("TD({})".format(x), "Tap/\nHold\n{}".format(x)))

KEYCODES = []
KEYCODES_MAP = dict()
RAWCODES_MAP = dict()

KEYCODES_MIDI_CC = []
KEYCODES_MIDI_CC_UP = []
KEYCODES_MIDI_CC_DOWN = []
KEYCODES_MIDI_CC_FIXED = []

for x in range (128):
    KEYCODES_MIDI_CC.append(K("MI_CC_{}_TOG".format(x),
                              "CC{}\nOn/Off".format(x),
                              "Midi CC{} toggle".format(x)))
    KEYCODES_MIDI_CC_UP.append(K("MI_CC_{}_UP".format(x),
                              "CC{}\n▲".format(x),
                              "Midi CC{} up".format(x)))
    KEYCODES_MIDI_CC_DOWN.append(K("MI_CC_{}_DWN".format(x),
                              "CC{}\n▼".format(x),
                              "Midi CC{} down".format(x)))

KEYCODES_MOD_PRESS = []

for x in range (128):
    KEYCODES_MOD_PRESS.append(K("MI_MOD_PRESS_{}".format(x),
                              "Dyn CC\n{}".format(x),
                              "Dynamic CC {}: analog key depth -> CC value; all Dynamic CC keys for this CC on the active layer combine into one controller".format(x)))


for x in range(128):
    for y in range(128):
        KEYCODES_MIDI_CC_FIXED.append(K("MI_CC_{}_{}".format(x,y),
                                    "CC{}\n{}".format(x,y),
                                    "Midi CC{} = {}".format(x,y)))



KEYCODES_MIDI_VELOCITY = []

for x in range (128):
    KEYCODES_MIDI_VELOCITY.append(K("MI_VELOCITY_{}".format(x),
                              "Fixed\nVelocity\n{}".format(x),
                              "Fixed Velocity {}".format(x)))
                              
KEYCODES_MIDI_VELOCITY2 = []

for x in range (128):
    KEYCODES_MIDI_VELOCITY2.append(K("MI_VELOCITY2_{}".format(x),
                              "KS\nVelocity\n{}".format(x),
                              "KS\nVelocity {}".format(x)))
                              
KEYCODES_MIDI_VELOCITY3 = []

for x in range (128):
    KEYCODES_MIDI_VELOCITY3.append(K("MI_VELOCITY3_{}".format(x),
                              "TS\nVelocity\n{}".format(x),
                              "TS\nVelocity {}".format(x)))

# Playing Style keycodes - all 29 presets (5 classic + 14 new factory + 10 user)
KEYCODES_HE_VELOCITY_CURVE = [
    # Factory articulations (new indices 0-22; each keycode keeps selecting
    # the articulation it is NAMED for — the firmware maps names to indices)
    K("HE_CURVE_SOFTEST", "Softest", "Articulation Softest"),
    K("HE_CURVE_SOFT", "Soft", "Articulation Soft"),
    K("HE_CURVE_MEDIUM", "Basic", "Articulation Basic"),
    K("HE_CURVE_HARD", "Hard", "Articulation Hard"),
    K("HE_CURVE_HARDEST", "Hardest", "Articulation Hardest"),
    K("HE_CURVE_FAC_19", "Soft Leg", "Articulation Soft Leg"),
    K("HE_CURVE_FAC_20", "Basic Leg", "Articulation Basic Leg"),
    K("HE_CURVE_FAC_21", "Hard Leg", "Articulation Hard Leg"),
    K("HE_CURVE_FAC_22", "Sens Leg", "Articulation Sens Leg"),
    K("HE_CURVE_FAC_8", "Fixed Vol", "Articulation Fixed Vol"),
    K("HE_CURVE_FAC_9", "Drums Easy", "Articulation Drums Easy"),
    K("HE_CURVE_FAC_10", "Drums Soft", "Articulation Drums Soft"),
    K("HE_CURVE_FAC_11", "Drums Basic", "Articulation Drums Basic"),
    K("HE_CURVE_FAC_12", "Drums Hard", "Articulation Drums Hard"),
    K("HE_CURVE_AGGRO", "Sensitive Soft", "Articulation Sensitive Soft"),
    K("HE_CURVE_DIGITAL", "Sensitive", "Articulation Sensitive"),
    K("HE_CURVE_FAC_7", "Sensitive Hard", "Articulation Sensitive Hard"),
    K("HE_CURVE_FAC_13", "Drums Sens", "Articulation Drums Sens"),
    K("HE_CURVE_FAC_14", "Ultra Sens", "Articulation Ultra Sens"),
    K("HE_CURVE_FAC_15", "Fixed Sens", "Articulation Fixed Sens"),
    K("HE_CURVE_FAC_16", "Two Toned", "Articulation Two Toned"),
    K("HE_CURVE_FAC_17", "Reverse", "Articulation Reverse"),
    K("HE_CURVE_FAC_18", "Random Highlights", "Articulation Random Highlights"),
    # User presets (23-72; first 10 have direct-select keycodes)
    K("HE_CURVE_USER_1", "User 1", "Articulation User Preset 1"),
    K("HE_CURVE_USER_2", "User 2", "Articulation User Preset 2"),
    K("HE_CURVE_USER_3", "User 3", "Articulation User Preset 3"),
    K("HE_CURVE_USER_4", "User 4", "Articulation User Preset 4"),
    K("HE_CURVE_USER_5", "User 5", "Articulation User Preset 5"),
    K("HE_CURVE_USER_6", "User 6", "Articulation User Preset 6"),
    K("HE_CURVE_USER_7", "User 7", "Articulation User Preset 7"),
    K("HE_CURVE_USER_8", "User 8", "Articulation User Preset 8"),
    K("HE_CURVE_USER_9", "User 9", "Articulation User Preset 9"),
    K("HE_CURVE_USER_10", "User 10", "Articulation User Preset 10"),
]

# Macro-aware HE Velocity Curve keycodes - these target loops when modifiers are held
KEYCODES_HE_MACRO_CURVE = [
    # Cycling keycodes
    K("HE_MACRO_CURVE_UP", "Loop\nArticulation ▲", "Loop Articulation Up (cycles 0-16)"),
    K("HE_MACRO_CURVE_DOWN", "Loop\nArticulation ▼", "Loop Articulation Down (cycles 0-16)"),
    K("HE_MACRO_MIN_UP", "Loop\nMin ▲", "Loop Velocity Min Up"),
    K("HE_MACRO_MIN_DOWN", "Loop\nMin ▼", "Loop Velocity Min Down"),
    K("HE_MACRO_MAX_UP", "Loop\nMax ▲", "Loop Velocity Max Up"),
    K("HE_MACRO_MAX_DOWN", "Loop\nMax ▼", "Loop Velocity Max Down"),
    # Playing Style cycling (global, or loop-specific when loop modifier held)
    K("HE_VEL_CURVE_UP", "Articulation\n▲", "Articulation Up (hold loop modifier for loop-specific)"),
    K("HE_VEL_CURVE_DOWN", "Articulation\n▼", "Articulation Down (hold loop modifier for loop-specific)"),
    # Direct macro curve selection (0-16)
    K("HE_MACRO_CURVE_0", "Loop Articulation\nSoftest", "Loop Articulation Softest (0)"),
    K("HE_MACRO_CURVE_1", "Loop Articulation\nSoft", "Loop Articulation Soft (1)"),
    K("HE_MACRO_CURVE_2", "Loop Articulation\nBasic", "Loop Articulation Basic (2)"),
    K("HE_MACRO_CURVE_3", "Loop Articulation\nHard", "Loop Articulation Hard (3)"),
    K("HE_MACRO_CURVE_4", "Loop Articulation\nHardest", "Loop Articulation Hardest (4)"),
    K("HE_MACRO_CURVE_5", "Loop Articulation\nSoft Leg", "Loop Articulation Soft Leg (5)"),
    K("HE_MACRO_CURVE_6", "Loop Articulation\nBasic Leg", "Loop Articulation Basic Leg (6)"),
    K("HE_MACRO_CURVE_7", "Loop Articulation\nHard Leg", "Loop Articulation Hard Leg (7)"),
    K("HE_MACRO_CURVE_8", "Loop Articulation\nSens Leg", "Loop Articulation Sens Leg (8)"),
    K("HE_MACRO_CURVE_9", "Loop Articulation\nFixed Vol", "Loop Articulation Fixed Vol (9)"),
    K("HE_MACRO_CURVE_10", "Loop Articulation\nDrums Easy", "Loop Articulation Drums Easy (10)"),
    K("HE_MACRO_CURVE_11", "Loop Articulation\nDrums Soft", "Loop Articulation Drums Soft (11)"),
    K("HE_MACRO_CURVE_12", "Loop Articulation\nDrums Basic", "Loop Articulation Drums Basic (12)"),
    K("HE_MACRO_CURVE_13", "Loop Articulation\nDrums Hard", "Loop Articulation Drums Hard (13)"),
    K("HE_MACRO_CURVE_14", "Loop Articulation\nSensitive Soft", "Loop Articulation Sensitive Soft (14)"),
    K("HE_MACRO_CURVE_15", "Loop Articulation\nSensitive", "Loop Articulation Sensitive (15)"),
    K("HE_MACRO_CURVE_16", "Loop Articulation\nSensitive Hard", "Loop Articulation Sensitive Hard (16)"),
]

# HE Velocity Range keycodes (min/max pairs where min ≤ max)
# Generates 8,128 keycodes total (127×128/2 triangular number)
KEYCODES_HE_VELOCITY_RANGE = []

for min_val in range(1, 128):  # 1 to 127
    for max_val in range(min_val, 128):  # min to 127 (includes min == max for fixed velocity)
        KEYCODES_HE_VELOCITY_RANGE.append(K("HE_VEL_RANGE_{}_{}".format(min_val, max_val),
                                  "VEL\n{}\n{}".format(min_val, max_val),
                                  "Velocity Range {}-{}".format(min_val, max_val)))

KEYCODES_MIDI_BANK = []
KEYCODES_MIDI_BANK_MSB = []
KEYCODES_MIDI_BANK_LSB = []
KEYCODES_Program_Change = []
KEYCODES_Program_Change_UPDOWN = []

KEYCODES_MIDI_BANK.append(K("MI_BANK_UP",
                            "Bank\nUp",
                            "Bank up"))
KEYCODES_MIDI_BANK.append(K("MI_BANK_DWN",
                            "Bank\nDown",
                            "Bank down"))
KEYCODES_Program_Change_UPDOWN.append(K("MI_PROG_UP",
                            "Program\n▲",
                            "Program up"))
KEYCODES_Program_Change_UPDOWN.append(K("MI_PROG_DWN",
                            "Program\n▼",
                            "Program down"))

for x in range(128):
    KEYCODES_MIDI_BANK_MSB.append(K("MI_BANK_MSB_{}".format(x),
                              "Bank\nMSB\n{}".format(x),
                              "Bank select MSB {}".format(x)))
    KEYCODES_MIDI_BANK_LSB.append(K("MI_BANK_LSB_{}".format(x),
                              "Bank\nLSB\n{}".format(x),
                              "Bank select LSB {}".format(x)))
    KEYCODES_Program_Change.append(K("MI_PROG_{}".format(x),
                              "Program\n{}".format(x),
                              "Program change {}".format(x)))


K = None


def recreate_keycodes():
    """ Regenerates global KEYCODES array """

    # The keycode tables AnyKeycode builds its name maps from are changing —
    # a stale cached instance would misclassify keycodes.
    _invalidate_any_keycode_cache()

    KEYCODES.clear()
    KEYCODES.extend(KEYCODES_SPECIAL + KEYCODES_BASIC + KEYCODES_SHIFTED + KEYCODES_ISO + KEYCODES_LAYERS + KEYCODES_LAYERS_DF + KEYCODES_LAYERS_MO + KEYCODES_LAYERS_TG + KEYCODES_LAYERS_TT + KEYCODES_LAYERS_OSL + KEYCODES_LAYERS_TO + KEYCODES_LAYERS_LT +
                    KEYCODES_BOOT + KEYCODES_MODIFIERS + KEYCODES_QUANTUM + KEYCODES_BACKLIGHT + KEYCODES_MEDIA + KEYCODES_OLED + KEYCODES_CLEAR + KEYCODES_RGB_KC_COLOR + KEYCODES_MIDI_OCTAVE2 + KEYCODES_MIDI_OCTAVE3 + KEYCODES_MIDI_KEY2 + KEYCODES_MIDI_KEY3 + KEYCODES_MIDI_VELOCITY2 + KEYCODES_MIDI_VELOCITY3 +
                    KEYCODES_TAP_DANCE + KEYCODES_MACRO + KEYCODES_MACRO_BASE + KEYCODES_EARTRAINER + KEYCODES_SAVE + KEYCODES_SETTINGS1 + KEYCODES_SETTINGS2 + KEYCODES_SETTINGS3 + KEYCODES_CHORDTRAINER + KEYCODES_USER + KEYCODES_HIDDEN + KEYCODES_MIDI+ KEYCODES_MIDI_CHANNEL_OS + KEYCODES_MIDI_CHANNEL_HOLD + KEYCODES_RGB_KC_CUSTOM + KEYCODES_RGB_KC_CUSTOM2 + KEYCODES_RGBSAVE + KEYCODES_MIDI_CHANNEL_KEYSPLIT + KEYCODES_MIDI_CHANNEL_KEYSPLIT2 + KEYCODES_KEYSPLIT_BUTTONS +
                    KEYCODES_MIDI_CC_FIXED+KEYCODES_MIDI_CC+KEYCODES_MIDI_CC_DOWN+KEYCODES_MIDI_CC_UP+KEYCODES_MOD_PRESS+KEYCODES_MIDI_BANK+KEYCODES_Program_Change+KEYCODES_MIDI_SMARTCHORDBUTTONS+KEYCODES_VELOCITY_STEPSIZE+KEYCODES_VELOCITY_SHUFFLE + KEYCODES_CC_ENCODERVALUE+ KEYCODES_EXWHEEL +
                    KEYCODES_MIDI_VELOCITY+KEYCODES_CC_STEPSIZE+KEYCODES_MIDI_CHANNEL+KEYCODES_MULTICHANNEL+KEYCODES_MIDI_UPDOWN+KEYCODES_MIDI_CHORD_0+KEYCODES_MIDI_CHORD_1+KEYCODES_MIDI_CHORD_2+KEYCODES_MIDI_CHORD_3+KEYCODES_MIDI_CHORD_4+KEYCODES_MIDI_CHORD_5+KEYCODES_MIDI_SPLIT+KEYCODES_MIDI_SPLIT2+
                    KEYCODES_HE_VELOCITY_CURVE+KEYCODES_HE_MACRO_CURVE+KEYCODES_HE_VELOCITY_RANGE+
                    KEYCODES_ARPEGGIATOR+KEYCODES_ARPEGGIATOR_PRESETS+KEYCODES_STEP_SEQUENCER+KEYCODES_STEP_SEQUENCER_PRESETS+KEYCODES_DRUM_SLOTS+KEYCODES_OCTAVE_DOUBLER+KEYCODES_DKS+KEYCODES_TOGGLE+KEYCODES_TOGGLE_ACTIONS+KEYCODES_DELAY_CLEAR+KEYCODES_DELAY+KEYCODES_DELAY_QB+KEYCODES_CHORD_QB+KEYCODES_SMARTCHORD_VL+KEYCODES_DYNCHORD_QB+KEYCODES_FADER_QB+KEYCODES_QB_MASTER+KEYCODES_EARTRAINER_QB+
                    KEYCODES_CPROG_SLOTS + KEYCODES_LOOP_BUTTONS + KEYCODES_DRUMLIVE + KEYCODES_GAMING +
                    KEYCODES_MIDI_INVERSION+KEYCODES_MIDI_SCALES+KEYCODES_MIDI_OCTAVE+KEYCODES_MIDI_KEY+KEYCODES_Program_Change_UPDOWN+KEYCODES_MIDI_BANK_LSB+KEYCODES_MIDI_BANK_MSB+KEYCODES_MIDI_PEDAL+KEYCODES_MIDI_ADVANCED+KEYCODES_MIDI_INOUT+KEYCODES_MIDI_SPLIT_BUTTONS+KEYCODES_BASIC + KEYCODES_SHIFTED + KEYCODES_CHORD_PROG_CONTROLS +
                    KEYCODES_DAW)
    KEYCODES_MAP.clear()
    RAWCODES_MAP.clear()
    for keycode in KEYCODES:
        KEYCODES_MAP[keycode.qmk_id.replace("(kc)", "")] = keycode
        RAWCODES_MAP[Keycode.deserialize(keycode.qmk_id)] = keycode


def create_user_keycodes():
    KEYCODES_USER.clear()
    for x in range(16):
        KEYCODES_USER.append(
            Keycode(
                "USER{:02}".format(x),
                "User {}".format(x),
                "User keycode {}".format(x)
            )
        )


def create_custom_user_keycodes(custom_keycodes):
    KEYCODES_USER.clear()
    for x, c_keycode in enumerate(custom_keycodes):
        KEYCODES_USER.append(
            Keycode(
                "USER{:02}".format(x),
                c_keycode.get("shortName", "USER{:02}".format(x)),
                c_keycode.get("title", "USER{:02}".format(x)),
                alias=[c_keycode.get("name", "USER{:02}".format(x))]
            )
        )


def create_midi_keycodes(midiSettingLevel):
    KEYCODES_MIDI.clear()

    if midiSettingLevel == "basic" or midiSettingLevel == "advanced":
        KEYCODES_MIDI.extend(KEYCODES_MIDI_BASIC)

    if midiSettingLevel == "advanced":
        KEYCODES_MIDI.extend(KEYCODES_MIDI_ADVANCED)


def recreate_keyboard_keycodes(keyboard):
    """ Generates keycodes based on information the keyboard provides (e.g. layer keycodes, macros) """

    # Invalidate up front too: the protocol change below already affects how
    # AnyKeycode would resolve names (recreate_keycodes() at the end
    # invalidates again once the tables are final).
    _invalidate_any_keycode_cache()

    Keycode.protocol = keyboard.vial_protocol

    layers = keyboard.layers

    def generate_keycodes_for_mask(label, description):
        keycodes = []
        for layer in range(layers):
            lbl = "{}({})".format(label, layer)
            keycodes.append(Keycode(lbl, lbl, description))
        return keycodes

    KEYCODES_LAYERS.clear()

    if layers >= 4:
        KEYCODES_LAYERS.append(Keycode("FN_MO13", "Fn1\n(Fn3)"))
        KEYCODES_LAYERS.append(Keycode("FN_MO23", "Fn2\n(Fn3)"))


    for x in range(layers):
        KEYCODES_LAYERS_LT.append(Keycode("LT{}(kc)".format(x), "LT {}\n(kc)".format(x),
                                       "kc on tap, switch to layer {} while held".format(x), masked=True))

    KEYCODES_MACRO.clear()
    for x in range(keyboard.macro_count):
        qmk_id = "M{}".format(x)
        label = "Macro\n{}".format(x)
        KEYCODES_MACRO.append(Keycode(qmk_id, label))


    KEYCODES_TAP_DANCE.clear()
    for x in range(keyboard.tap_dance_count):
        qmk_id = "TD({})".format(x)
        label = "Tap/\nHold\n{}".format(x)
        KEYCODES_TAP_DANCE.append(Keycode(qmk_id, label, "Tap dance keycode"))

    # Check if custom keycodes are defined in keyboard, and if so add them to user keycodes
    if keyboard.custom_keycodes is not None and len(keyboard.custom_keycodes) > 0:
        create_custom_user_keycodes(keyboard.custom_keycodes)
    else:
        create_user_keycodes()

    create_midi_keycodes(keyboard.midi)

    recreate_keycodes()


recreate_keycodes()
