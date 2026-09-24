# SPDX-License-Identifier: GPL-2.0-or-later
"""A software MIDIswitch for the "look around" mode.

VirtualMidiswitchDevice stands in for the USB handle. It answers the app's
32-byte reports the way a factory-fresh MIDIswitch does, so the app runs the
same code it runs for a connected keyboard: same layer count, same keymap,
same tabs, same loading steps. Nothing is written anywhere; changes live
until the page or app is closed.
"""
import collections
import logging
import struct

from protocol.msw_protocol import (
    MSW_CMD_IDENT, MSW_CAP_DIGITIZER, MSW_CAP_DIN_MIDI, MSW_CAP_RGB_MATRIX, MSW_CAP_CLONE,
    ALIAS_TO_VIA, ALIAS_VIAL_PREFIX, MSW_CMD_MACRO_SETTINGS, MSET_MOUSE_MARKER,
)
from util import MIDISWITCH_KEYBOARD_UID
from protocol.virtual_midiswitch_lighting import LightingMixin
from protocol.virtual_midiswitch_keys import KeysMixin
from protocol.virtual_midiswitch_music import MusicMixin

MSG_LEN = 32

ROWS, COLS, LAYERS = 6, 14, 12
MACRO_COUNT = 255
MACRO_BUFFER_SIZE = 15876
TAP_HOLD_COUNT = 100
COMBO_KEY_COUNT = 100
LAYOUT_VERSION = 9
FIRMWARE_VERSION = (1, 0, 0)

_ROW0 = "KC_ESCAPE KC_1 KC_2 KC_3 KC_4 KC_5 KC_6 KC_7 KC_8 KC_9 KC_0 KC_MINUS KC_EQUAL KC_BSPACE"
_ROW1 = "KC_TAB KC_Q KC_W KC_E KC_R KC_T KC_Y KC_U KC_I KC_O KC_P KC_LBRACKET KC_RBRACKET KC_BSLASH"
_ROW2 = "KC_CAPSLOCK KC_A KC_S KC_D KC_F KC_G KC_H KC_J KC_K KC_L KC_SCOLON KC_QUOTE KC_ENTER KC_ENTER"
_ROW5 = "KC_B KC_C KC_A"

# Factory keymap: layer 1 differs from the others in its bottom two rows.
FACTORY_LAYER_FIRST = [
    _ROW0, _ROW1, _ROW2,
    "KC_LSHIFT KC_LSHIFT KC_Z KC_X KC_C KC_V KC_B KC_N KC_M KC_COMMA KC_DOT KC_SLASH KC_UP KC_RSHIFT",
    "KC_LCTRL KC_LGUI KC_LALT KC_SPACE KC_SPACE KC_SPACE MO(2) KC_SPACE KC_SPACE KC_SPACE "
    "KC_RCTRL KC_LEFT KC_DOWN KC_RIGHT",
    _ROW5,
]
FACTORY_LAYER_OTHER = [
    _ROW0, _ROW1, _ROW2,
    "KC_LSHIFT KC_Z KC_X KC_C KC_V KC_B KC_N KC_M KC_COMMA KC_DOT KC_SLASH KC_END KC_UP KC_RSHIFT",
    "KC_LCTRL KC_LGUI KC_LALT MO(1) KC_SPACE KC_SPACE KC_SPACE KC_SPACE KC_RALT MO(1) "
    "KC_RCTRL KC_LEFT KC_DOWN KC_RIGHT",
    _ROW5,
]
FACTORY_ENCODER = ("KC_VOLD", "KC_VOLU")   # counter-clockwise, clockwise

# Combo Keys shipped enabled: Fn 1 + number row -> F1..F12.
_FN_ROW = ["KC_1", "KC_2", "KC_3", "KC_4", "KC_5", "KC_6", "KC_7", "KC_8", "KC_9", "KC_0",
           "KC_MINUS", "KC_EQUAL"]

# Lighting
RGB_MAX_BRIGHTNESS = 225
RGB_EFFECT_COUNT = 127
RGB_DEFAULT_MODE = 14   # cycle left/right


def _kc(name):
    from keycodes.keycodes import Keycode
    return Keycode.deserialize(name)


class VirtualMidiswitchDevice(LightingMixin, KeysMixin, MusicMixin):
    """hidapi-style handle: write() takes a report (leading report-id byte),
    read() returns the next queued reply or b"" when there is none."""

    def __init__(self):
        self._replies = collections.deque()
        self._keymap = None      # built on first use: keycode tables must be loaded
        self._encoders = None
        self.macro_buffer = bytearray(MACRO_BUFFER_SIZE)
        self.tap_hold = [struct.pack("<HHHHH", 0, 0, 0, 0, 200)] * TAP_HOLD_COUNT
        self._combo_keys = None
        self.settings = {7: 200, 18: 1, 6: 5000}
        self.mouse = [10, 100]
        self.rgb = [RGB_DEFAULT_MODE, 128, 0, 255, RGB_MAX_BRIGHTNESS]   # mode, speed, h, s, v
        self.custom = {}         # (cmd, key) -> last payload set, for simple get/set pairs
        self.unhandled = collections.Counter()
        self.closed = False
        for name in dir(self):
            if name.startswith("_init_"):
                getattr(self, name)()

    # ---- hidapi surface ------------------------------------------------

    def open_path(self, path):
        pass

    def close(self):
        self.closed = True

    def set_nonblocking(self, flag):
        return 0

    def write(self, data):
        data = bytes(data)
        msg = bytearray(data[1:1 + MSG_LEN])
        msg += bytearray(MSG_LEN - len(msg))
        try:
            reply = self._handle(msg)
        except Exception:
            logging.exception("virtual MIDIswitch: error answering %s", msg[:4].hex())
            reply = None
        if reply is None:
            return len(data)
        for one in (reply if isinstance(reply, list) else [reply]):
            one = bytes(one[:MSG_LEN]) + bytes(max(0, MSG_LEN - len(one)))
            self._replies.append(one)
        return len(data)

    def read(self, length, timeout_ms=0):
        if self._replies:
            return self._replies.popleft()[:length]
        return b""

    # ---- state built on first use ---------------------------------------

    def _ensure_keymap(self):
        if self._keymap is not None:
            return
        self._keymap = []
        for layer in range(LAYERS):
            rows = FACTORY_LAYER_FIRST if layer == 0 else FACTORY_LAYER_OTHER
            codes = []
            for r in range(ROWS):
                names = rows[r].split()
                for c in range(COLS):
                    codes.append(_kc(names[c]) if c < len(names) else 0)
            self._keymap.append(codes)
        ccw, cw = _kc(FACTORY_ENCODER[0]), _kc(FACTORY_ENCODER[1])
        self._encoders = collections.defaultdict(lambda: [ccw, cw])

    def _ensure_combo_keys(self):
        if self._combo_keys is not None:
            return
        self._combo_keys = []
        options = 0x07 | 0x80
        layers = 0x0FFF | (1 << 12)
        f_keys = ["KC_F{}".format(n) for n in range(1, 13)]
        for i in range(COMBO_KEY_COUNT):
            if i < len(_FN_ROW):
                self._combo_keys.append(struct.pack("<HHHBBBB", _kc(_FN_ROW[i]), _kc(f_keys[i]),
                                                    layers, 0, 0, 0, options))
            else:
                self._combo_keys.append(bytes(10))

    def _keymap_bytes(self):
        self._ensure_keymap()
        out = bytearray()
        for layer in self._keymap:
            for code in layer:
                out += struct.pack(">H", code)
        return out

    # ---- dispatch --------------------------------------------------------

    def _handle(self, msg):
        b0 = msg[0]
        if b0 in ALIAS_TO_VIA:
            reply = self._via(ALIAS_TO_VIA[b0], msg)
            if reply is not None and reply[0] == ALIAS_TO_VIA[b0]:
                reply[0] = b0
            return reply
        if b0 == ALIAS_VIAL_PREFIX:
            return self._vial(msg)
        if b0 == 0x7D and msg[1] == 0x00 and msg[2] == 0x4D:
            return self._custom(msg)
        # Any other form: the keyboard answers foreign packets with a
        # custom-family error echo.
        reply = bytearray(MSG_LEN)
        reply[0:4] = bytes([0x7D, 0x00, 0x4D, 0x00])
        reply[5] = 1
        return reply

    def _via(self, cmd, msg):
        r = bytearray(msg)
        if cmd == 0x01:                                   # protocol version
            r[1:3] = struct.pack(">H", 9)
        elif cmd == 0x02:                                 # keyboard value
            if msg[1] == 0x02:                            # layout options
                r[2:6] = struct.pack(">I", 0)
            elif msg[1] == 0x03:                          # switch matrix state: nothing pressed
                r[2:MSG_LEN] = bytes(MSG_LEN - 2)
        elif cmd == 0x03:
            pass
        elif cmd == 0x04:                                 # get keycode
            self._ensure_keymap()
            layer, row, col = msg[1], msg[2], msg[3]
            code = self._keymap[layer][row * COLS + col] if layer < LAYERS and row < ROWS and col < COLS else 0
            r[4:6] = struct.pack(">H", code)
        elif cmd == 0x05:                                 # set keycode
            self._ensure_keymap()
            layer, row, col = msg[1], msg[2], msg[3]
            if layer < LAYERS and row < ROWS and col < COLS:
                self._keymap[layer][row * COLS + col] = struct.unpack(">H", bytes(msg[4:6]))[0]
        elif cmd == 0x06:                                 # reset keymap
            self._keymap = None
        elif cmd == 0x07:                                 # lighting set
            if msg[1] == 0x41:
                mode, speed, h, s, v = struct.unpack_from("<HBBBB", bytes(msg), 2)
                self.rgb = [mode, speed, h, s, min(v, RGB_MAX_BRIGHTNESS)]
        elif cmd == 0x08:                                 # lighting get
            sub = msg[1]
            if sub == 0x40:
                r[2:5] = bytes([1, 0, RGB_MAX_BRIGHTNESS])
            elif sub == 0x41:
                r[2:8] = struct.pack("<HBBBB", *self.rgb)
            elif sub == 0x42:
                gt = struct.unpack_from("<H", bytes(msg), 2)[0]
                ids = [i for i in range(RGB_EFFECT_COUNT) if i > gt][:(MSG_LEN - 2) // 2]
                payload = b"".join(struct.pack("<H", i) for i in ids)
                payload += b"\xFF" * (MSG_LEN - 2 - len(payload))
                r[2:MSG_LEN] = payload
            else:
                r[2:MSG_LEN] = bytes(MSG_LEN - 2)
        elif cmd == 0x09:
            pass
        elif cmd == 0x0C:                                 # macro count
            r[1] = MACRO_COUNT
        elif cmd == 0x0D:                                 # macro buffer size
            r[1:3] = struct.pack(">H", MACRO_BUFFER_SIZE)
        elif cmd == 0x0E:                                 # macro buffer get
            off, sz = struct.unpack(">H", bytes(msg[1:3]))[0], msg[3]
            r[4:4 + sz] = bytes(self.macro_buffer[off:off + sz]).ljust(sz, b"\x00")
        elif cmd == 0x0F:                                 # macro buffer set
            off, sz = struct.unpack(">H", bytes(msg[1:3]))[0], msg[3]
            self.macro_buffer[off:off + sz] = msg[4:4 + sz]
            del self.macro_buffer[MACRO_BUFFER_SIZE:]
        elif cmd == 0x10:                                 # macro reset
            self.macro_buffer = bytearray(MACRO_BUFFER_SIZE)
        elif cmd == 0x11:                                 # layer count
            r[1] = LAYERS
        elif cmd == 0x12:                                 # keymap buffer get
            off, sz = struct.unpack(">H", bytes(msg[1:3]))[0], msg[3]
            r[4:4 + sz] = bytes(self._keymap_bytes()[off:off + sz]).ljust(sz, b"\x00")
        elif cmd == 0x13:                                 # keymap buffer set
            off, sz = struct.unpack(">H", bytes(msg[1:3]))[0], msg[3]
            buf = self._keymap_bytes()
            buf[off:off + sz] = msg[4:4 + sz]
            for layer in range(LAYERS):
                for i in range(ROWS * COLS):
                    p = (layer * ROWS * COLS + i) * 2
                    self._keymap[layer][i] = struct.unpack(">H", bytes(buf[p:p + 2]))[0]
        else:
            self.unhandled["via %02X" % cmd] += 1
        return r

    def _vial(self, msg):
        sub = msg[1]
        r = bytearray(MSG_LEN)
        if sub == 0x00:                                   # keyboard id
            r[0:8] = struct.pack("<Q", MIDISWITCH_KEYBOARD_UID)
        elif sub == 0x03:                                 # get encoder
            self._ensure_keymap()
            ccw, cw = self._encoders[(msg[2], msg[3])]
            r[0:4] = struct.pack(">HH", ccw, cw)
        elif sub == 0x04:                                 # set encoder
            self._ensure_keymap()
            self._encoders[(msg[2], msg[3])][msg[4]] = struct.unpack(">H", bytes(msg[5:7]))[0]
        elif sub == 0x05:                                 # unlock status: unlocked
            r[0] = 1
            r[1] = 0
            r[2:] = b"\xFF" * (MSG_LEN - 2)
        elif sub in (0x06, 0x07, 0x08):
            r[0] = 1 if sub == 0x07 else 0
        elif sub == 0x0D:                                 # dynamic entries
            op = msg[2]
            if op == 0x00:
                r[0], r[1], r[2] = TAP_HOLD_COUNT, 0, COMBO_KEY_COUNT
                r[31] = 0
            elif op == 0x01:
                idx = msg[3]
                r[0] = 0
                if idx < TAP_HOLD_COUNT:
                    r[1:11] = self.tap_hold[idx]
            elif op == 0x02:
                idx = msg[3]
                if idx < TAP_HOLD_COUNT:
                    self.tap_hold[idx] = bytes(msg[4:14])
            elif op == 0x05:
                self._ensure_combo_keys()
                idx = msg[3]
                r[0] = 0
                if idx < COMBO_KEY_COUNT:
                    r[1:11] = self._combo_keys[idx]
            elif op == 0x06:
                self._ensure_combo_keys()
                idx = msg[3]
                if idx < COMBO_KEY_COUNT:
                    self._combo_keys[idx] = bytes(msg[4:14])
            else:
                r[0] = 1
        else:
            for hook in self._vial_hooks():
                reply = hook(sub, msg)
                if reply is not None:
                    return reply
            self.unhandled["vial %02X" % sub] += 1
        return r

    def _vial_hooks(self):
        return [getattr(self, n) for n in ("_vial_lighting", "_vial_keys", "_vial_music") if hasattr(self, n)]

    def _custom_hooks(self):
        return [getattr(self, n) for n in ("_custom_lighting", "_custom_keys", "_custom_music") if hasattr(self, n)]

    def _custom(self, msg):
        cmd = msg[3]
        r = bytearray(msg)
        if cmd == MSW_CMD_IDENT:
            r[4:] = bytes(MSG_LEN - 4)
            caps = MSW_CAP_DIGITIZER | MSW_CAP_DIN_MIDI | MSW_CAP_RGB_MATRIX | MSW_CAP_CLONE
            struct.pack_into("<BBBBBBBBBHIB8sI", r, 4, 1, ord("M"), ord("S"), ord("W"), 1, 0,
                             FIRMWARE_VERSION[0], FIRMWARE_VERSION[1], FIRMWARE_VERSION[2],
                             LAYOUT_VERSION, caps, 1, struct.pack("<Q", MIDISWITCH_KEYBOARD_UID), 0)
            return r
        if cmd == MSW_CMD_MACRO_SETTINGS:
            sub = msg[4]
            if sub == 1:
                self.settings[7], self.settings[18], self.settings[6] = struct.unpack_from("<HHH", bytes(msg), 6)
                if msg[16] == MSET_MOUSE_MARKER:
                    self.mouse = list(struct.unpack_from("<HH", bytes(msg), 12))
            elif sub == 2:
                self.settings = {7: 200, 18: 1, 6: 5000}
                self.mouse = [10, 100]
            r[4:] = bytes(MSG_LEN - 4)
            r[4] = 1
            struct.pack_into("<HHHHH", r, 5, self.settings[7], self.settings[18], self.settings[6], *self.mouse)
            r[15] = MSET_MOUSE_MARKER
            return r
        for hook in self._custom_hooks():
            reply = hook(cmd, msg)
            if reply is not None:
                return reply
        self.unhandled["custom %02X" % cmd] += 1
        return self._custom_default(cmd, msg)

    def _custom_default(self, cmd, msg):
        r = bytearray(msg)
        r[4:] = bytes(MSG_LEN - 4)
        r[4] = 1
        return r
