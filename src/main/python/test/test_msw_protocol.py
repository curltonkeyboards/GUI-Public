import json
import lzma
import os
import struct
import unittest

from protocol import msw_protocol as msw
from protocol import msw_definition
from protocol.keyboard_comm import Keyboard, ProtocolError
from util import MSG_LEN, chunks

LAYOUT_2x2 = ('{"name":"test","vendorId":"0x0000","productId":"0x1111","lighting":"none",'
              '"matrix":{"rows":2,"cols":2},"layouts":{"keymap":[["0,0","0,1"],["1,0","1,1"]]}}')
MODEL_UID = 0xB26D0425F36AC4F4
BUNDLED_MODEL = 1                       # a model id the app carries a definition for
BUNDLED_ROWS = msw_definition.get_definition(BUNDLED_MODEL)["matrix"]["rows"]
UNKNOWN_MODEL = 2                       # a model id the app does not know
SETTINGS_DEFAULTS = {7: 200, 18: 1, 6: 5000}


def pad(b):
    return bytes(b) + b"\x00" * (MSG_LEN - len(b))


class FakeFirmware:
    """A keyboard-side model of the dispatcher: IDENT, the alias translation
    (the same rules the keyboard applies), a handful of legacy handlers
    with their real response shapes, and the legacy-paths switch."""

    def __init__(self, has_ident=True, legacy_paths=True, definition=LAYOUT_2x2,
                 model_id=BUNDLED_MODEL, serve_definition=False):
        self.has_ident = has_ident
        self.legacy_paths = legacy_paths
        self.model_id = model_id
        self.serve_definition = serve_definition      # the definition download is compiled in
        self.definition = lzma.compress(definition.encode("utf-8"))
        self.settings = dict(SETTINGS_DEFAULTS)       # the three Macro Settings values
        self.wire = []  # every request as it arrived on the wire

    # ---- the firmware ----
    def ident(self, d):
        r = bytearray(32)
        r[0:4] = d[0:4]
        if not self.has_ident:
            r[5] = 1  # "unknown custom command" error echo of an old firmware
            return bytes(r)
        r[4] = 1
        r[5:8] = b"MSW"
        r[8], r[9] = 1, 0
        r[10:13] = bytes([1, 2, 3])
        struct.pack_into("<H", r, 13, 7)
        caps = msw.MSW_CAP_CLONE | (msw.MSW_CAP_LEGACY_PATHS if self.legacy_paths else 0) \
            | (msw.MSW_CAP_DEFINITION if self.serve_definition else 0)
        struct.pack_into("<I", r, 15, caps)
        r[19] = self.model_id
        struct.pack_into("<Q", r, 20, MODEL_UID)
        struct.pack_into("<I", r, 28, 0xDEADBEEF)
        return bytes(r)

    def macro_settings(self, d):
        r = bytearray(32)
        r[0:4] = d[0:4]
        sub = d[4]
        if sub > 2:
            return bytes(r)  # status 0
        if sub == 2:
            self.settings = dict(SETTINGS_DEFAULTS)
        elif sub == 1:
            for i, q in enumerate(msw.MACRO_SETTINGS_QSIDS):
                self.settings[q] = struct.unpack_from("<H", bytes(d), 6 + 2 * i)[0]
        r[4] = 1
        struct.pack_into("<HHH", r, 5, *[self.settings[q] for q in msw.MACRO_SETTINGS_QSIDS])
        return bytes(r)

    def legacy_dispatch(self, d):
        d = bytearray(d)
        b0 = d[0]
        if b0 == 0x01:
            d[1], d[2] = 0x00, 0x09
        elif b0 == 0x11:
            d[1] = 2
        elif b0 == 0x04:
            kc = 0x1000 + d[1] * 0x100 + d[2] * 0x10 + d[3]
            d[4], d[5] = kc >> 8, kc & 0xFF
        elif b0 == 0x0C:
            d[1] = 0
        elif b0 == 0xFE:
            sub = d[1]
            if sub == 0x00:
                d[0:12] = struct.pack("<IQ", 6, MODEL_UID)
            elif sub == 0x01:
                d[0:4] = struct.pack("<I", len(self.definition) if self.serve_definition else 0)
            elif sub == 0x02:
                page = struct.unpack("<I", bytes(d[2:6]))[0]
                d[:] = pad(self.definition[page * 32:(page + 1) * 32]) if self.serve_definition else bytes(32)
            elif sub in (0x09, 0x0A, 0x0B, 0x0C):
                if not self.legacy_paths:
                    pass  # the per-setting sub-commands are not compiled in: request echoed back
                elif sub == 0x09:
                    gt = struct.unpack("<H", bytes(d[2:4]))[0]
                    ids = [q for q in sorted(self.settings) if q > gt]
                    d[:] = b"".join(struct.pack("<H", q) for q in ids).ljust(32, b"\xff")
                elif sub == 0x0A:
                    qsid = struct.unpack("<H", bytes(d[2:4]))[0]
                    d[0] = 0 if qsid in self.settings else 1
                    if qsid in self.settings:
                        d[1:3] = struct.pack("<H", self.settings[qsid])
                elif sub == 0x0B:
                    qsid = struct.unpack("<H", bytes(d[2:4]))[0]
                    d[0] = 0 if qsid in self.settings else 1
                    if qsid in self.settings:
                        self.settings[qsid] = struct.unpack("<H", bytes(d[4:6]))[0]
                else:
                    self.settings = dict(SETTINGS_DEFAULTS)
            elif sub == 0x03:
                kc = 0xFE4D  # a keycode whose high byte equals the legacy prefix
                d[0], d[1] = kc >> 8, kc & 0xFF
            elif sub == 0x0D:
                d[0], d[1], d[2] = 100, 0, 100
            else:
                d[0] = 0  # error status
        else:
            d[0] = 0xFF  # unhandled marker
        return bytes(d)

    def receive(self, data):
        self.wire.append(bytes(data))
        d = bytearray(data)
        if d[0:3] == bytes([0x7D, 0x00, 0x4D]) and d[3] == msw.MSW_CMD_IDENT:
            return self.ident(d)
        if d[0:3] == bytes([0x7D, 0x00, 0x4D]) and d[3] == msw.MSW_CMD_MACRO_SETTINGS:
            return self.macro_settings(d)
        # alias translation (msw_alias_translate)
        alias = None
        if d[0] in msw.ALIAS_TO_VIA:
            alias, legacy = d[0], msw.ALIAS_TO_VIA[d[0]]
            d[0] = legacy
        elif d[0] == msw.ALIAS_VIAL_PREFIX:
            alias, legacy = d[0], msw.LEGACY_VIAL_PREFIX
            d[0] = legacy
        elif not self.legacy_paths:
            r = bytearray(32)
            r[0:3] = bytes([0x7D, 0x00, 0x4D])
            r[5] = 1
            return bytes(r)
        out = bytearray(self.legacy_dispatch(d))
        # msw_alias_restore
        if alias is not None and legacy != msw.LEGACY_VIAL_PREFIX and out[0] == legacy:
            out[0] = alias
        return bytes(out)

    # ---- the usb_send signature the Keyboard object expects ----
    def send(self, dev, msg, retries=1):
        return self.receive(pad(msg))


LEGACY_BYTE0 = set(range(0x01, 0x14)) | {0xFE}


class TestAliasTable(unittest.TestCase):

    def test_values_match_firmware(self):
        self.assertEqual(msw.ALIAS_VIA_BASE, 0x2A)
        self.assertEqual(msw.ALIAS_VIAL_PREFIX, 0x4D)
        self.assertEqual(msw.VIA_TO_ALIAS[0x01], 0x2A)
        self.assertEqual(msw.VIA_TO_ALIAS[0x13], 0x3C)

    def test_aliases_unique_and_outside_legacy_values(self):
        values = list(msw.VIA_TO_ALIAS.values()) + [msw.ALIAS_VIAL_PREFIX]
        self.assertEqual(len(values), len(set(values)))
        for v in values:
            self.assertNotIn(v, LEGACY_BYTE0)
            self.assertNotEqual(v, 0x7D)
            self.assertGreater(v, 0x01)  # never a status byte

    def test_encode_leaves_custom_family_alone(self):
        pkt = bytes([0x7D, 0x00, 0x4D, 0x93]) + b"\x00" * 28
        self.assertEqual(msw.encode_request(pkt), pkt)
        self.assertFalse(msw.is_alias_candidate(pkt))


class TestIdent(unittest.TestCase):

    def test_parse_good_reply(self):
        fw = FakeFirmware()
        ident = msw.parse_ident(fw.receive(msw.build_ident_request()))
        self.assertEqual(ident["protocol"], (1, 0))
        self.assertEqual(ident["firmware"], (1, 2, 3))
        self.assertEqual(ident["eeprom_layout_version"], 7)
        self.assertTrue(ident["capabilities"] & msw.MSW_CAP_LEGACY_PATHS)
        self.assertEqual(ident["model_id"], 1)
        self.assertEqual(ident["model_uid"], MODEL_UID)
        self.assertEqual(ident["hardware_id"], 0xDEADBEEF)

    def test_error_echo_is_not_an_ident(self):
        fw = FakeFirmware(has_ident=False)
        self.assertIsNone(msw.parse_ident(fw.receive(msw.build_ident_request())))
        self.assertIsNone(msw.parse_ident(b""))
        self.assertIsNone(msw.parse_ident(pad(b"\x01\x00\x09")))


class TestCodecParity(unittest.TestCase):
    """Both codecs must hand the caller identical bytes for identical requests."""

    REQUESTS = [
        struct.pack("B", 0x01),
        struct.pack("B", 0x11),
        struct.pack("BBBB", 0x04, 1, 0, 1),
        struct.pack("B", 0x0C),
        struct.pack("B", 0x13),                      # falls to the "unhandled" marker
        struct.pack("BB", 0xFE, 0x00),
        struct.pack("BB", 0xFE, 0x01),
        struct.pack("<BBI", 0xFE, 0x02, 0),
        struct.pack("BBBB", 0xFE, 0x03, 0, 0),       # response byte 0 == 0xFE by data
        struct.pack("BBB", 0xFE, 0x0D, 0x00),
        struct.pack("BB", 0xFE, 0x77),               # status 0 in byte 0
    ]

    def test_parity(self):
        legacy_fw, msw_fw = FakeFirmware(), FakeFirmware()
        kb_legacy = Keyboard(None, legacy_fw.send)
        kb_msw = Keyboard(None, msw_fw.send)
        self.assertIsNotNone(kb_msw.probe_ident())
        self.assertEqual(kb_msw.hid_codec, "msw")
        self.assertEqual(kb_legacy.hid_codec, "legacy")
        for req in self.REQUESTS:
            a = kb_legacy.usb_send(None, req)
            b = kb_msw.usb_send(None, req)
            self.assertEqual(a, b, "response differs for request {}".format(req.hex()))
            # and what left the msw keyboard on the wire carried the alias, never the legacy id
            wire = msw_fw.wire[-1]
            self.assertNotIn(wire[0], LEGACY_BYTE0, "legacy byte 0 on the wire: {}".format(wire.hex()))
            self.assertEqual(wire[1:], pad(req)[1:], "payload moved for {}".format(req.hex()))

    def test_definition_bytes_that_look_like_headers_survive(self):
        # a definition page whose first byte is the alias prefix (0x4D) or the legacy prefix (0xFE)
        fw = FakeFirmware(serve_definition=True)
        fw.definition = b"\x4d" * 32 + b"\xfe" * 32 + b"\x2a" * 32
        kb = Keyboard(None, fw.send)
        kb.probe_ident()
        for page, first in ((0, 0x4D), (1, 0xFE), (2, 0x2A)):
            data = kb.usb_send(None, struct.pack("<BBI", 0xFE, 0x02, page))
            self.assertEqual(data, bytes([first]) * 32)

    def test_unhandled_marker_not_disguised(self):
        fw = FakeFirmware()
        kb = Keyboard(None, fw.send)
        kb.probe_ident()
        self.assertEqual(kb.usb_send(None, struct.pack("B", 0x13))[0], 0xFF)


class TestConnect(unittest.TestCase):

    def test_old_firmware_stays_legacy(self):
        fw = FakeFirmware(has_ident=False, serve_definition=True)
        kb = Keyboard(None, fw.send)
        self.assertIsNone(kb.probe_ident())
        self.assertEqual(kb.hid_codec, "legacy")
        kb.reload_layout()
        self.assertEqual((kb.via_protocol, kb.vial_protocol, kb.keyboard_id), (9, 6, MODEL_UID))
        self.assertEqual(kb.rows, 2)

    def test_msw_firmware_connect_sends_no_legacy_ids(self):
        fw = FakeFirmware()
        kb = Keyboard(None, fw.send)
        kb.reload_layout()
        self.assertEqual(kb.hid_codec, "msw")
        self.assertEqual((kb.via_protocol, kb.vial_protocol, kb.keyboard_id), (9, 6, MODEL_UID))
        self.assertEqual(kb.msw_ident["firmware"], (1, 2, 3))
        self.assertEqual(kb.rows, BUNDLED_ROWS)   # the bundled definition, not the 2x2 the fake would serve
        for pkt in fw.wire:
            self.assertNotIn(pkt[0], LEGACY_BYTE0, "legacy id on the wire during connect: {}".format(pkt.hex()))
        self.assertFalse(definition_requests(fw), "definition download requested for a bundled model")

    def test_unknown_model_downloads_when_the_keyboard_offers(self):
        fw = FakeFirmware(model_id=UNKNOWN_MODEL, serve_definition=True)
        kb = Keyboard(None, fw.send)
        kb.reload_layout()
        self.assertEqual(kb.hid_codec, "msw")
        self.assertEqual(kb.rows, 2)
        self.assertTrue(definition_requests(fw))

    def test_unknown_model_without_definition_is_refused(self):
        fw = FakeFirmware(model_id=UNKNOWN_MODEL, serve_definition=False)
        kb = Keyboard(None, fw.send)
        with self.assertRaises(ProtocolError):
            kb.reload_layout()
        self.assertFalse(definition_requests(fw))

    def test_legacy_paths_off_only_aliases_answer(self):
        fw = FakeFirmware(legacy_paths=False)
        kb = Keyboard(None, fw.send)
        kb.reload_layout()  # works: IDENT + aliases only
        self.assertEqual(kb.rows, BUNDLED_ROWS)
        self.assertFalse(kb.msw_ident["capabilities"] & msw.MSW_CAP_LEGACY_PATHS)
        # a foreign probe in the original form gets the custom "unknown" reply
        self.assertEqual(fw.receive(pad(b"\x01"))[0:3], bytes([0x7D, 0x00, 0x4D]))
        self.assertEqual(fw.receive(pad(b"\xfe\x00"))[0:3], bytes([0x7D, 0x00, 0x4D]))

    def test_future_protocol_major_keeps_legacy_codec(self):
        fw = FakeFirmware()
        good = fw.ident
        def ident_v2(d):
            r = bytearray(good(d)); r[8] = 2; return bytes(r)
        fw.ident = ident_v2
        kb = Keyboard(None, fw.send)
        self.assertIsNotNone(kb.probe_ident())
        self.assertEqual(kb.hid_codec, "legacy")


class TestMacroSettings(unittest.TestCase):

    def test_explicit_command_replaces_the_per_setting_ones(self):
        fw = FakeFirmware(legacy_paths=False)
        kb = Keyboard(None, fw.send)
        kb.reload_layout()
        kb.reload_settings()
        self.assertEqual(kb.supported_settings, set(msw.MACRO_SETTINGS_QSIDS))
        self.assertEqual(kb.settings, SETTINGS_DEFAULTS)

        self.assertEqual(kb.qmk_settings_set(7, 250), 0)
        self.assertEqual(fw.settings[7], 250)
        self.assertEqual(fw.settings[18], SETTINGS_DEFAULTS[18])   # the other two carried unchanged
        self.assertEqual(kb.settings[7], 250)

        kb.qmk_settings_reset()
        self.assertEqual(fw.settings, SETTINGS_DEFAULTS)
        self.assertEqual(kb.settings, SETTINGS_DEFAULTS)

        self.assertEqual(kb.qmk_settings_set(99, 1), 1)              # not a Macro Setting
        self.assertFalse(setting_subcommands(fw), "per-setting sub-command on the wire")

    def test_set_before_reload_fetches_the_rest(self):
        fw = FakeFirmware()
        kb = Keyboard(None, fw.send)
        kb.reload_layout()
        self.assertEqual(kb.qmk_settings_set(18, 7), 0)
        self.assertEqual(fw.settings, {7: 200, 18: 7, 6: 5000})

    def test_bad_reply_leaves_settings_unsupported(self):
        fw = FakeFirmware()
        fw.macro_settings = lambda d: bytes(32)
        kb = Keyboard(None, fw.send)
        kb.reload_layout()
        kb.reload_settings()
        self.assertEqual(kb.supported_settings, set())
        self.assertEqual(kb.settings, {})
        self.assertEqual(kb.qmk_settings_set(7, 1), 1)

    def test_legacy_firmware_still_uses_the_per_setting_commands(self):
        # the per-setting path decodes through the settings definitions the app ships
        from editor.qmk_settings import QmkSettingsDefs
        res = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "resources", "base")

        class Ctx:
            def get_resource(self, name):
                return os.path.join(res, name)
        QmkSettingsDefs.initialize(Ctx())

        fw = FakeFirmware(has_ident=False, serve_definition=True)
        kb = Keyboard(None, fw.send)
        kb.reload_layout()
        kb.reload_settings()
        self.assertEqual(kb.supported_settings, set(SETTINGS_DEFAULTS))
        self.assertEqual(kb.settings, SETTINGS_DEFAULTS)
        self.assertEqual(kb.qmk_settings_set(6, 123), 0)
        self.assertEqual(fw.settings[6], 123)
        self.assertTrue(setting_subcommands(fw))


def definition_requests(fw):
    """The definition size / page requests seen on the wire, either form."""
    return [p for p in fw.wire if p[0] in (0xFE, msw.ALIAS_VIAL_PREFIX) and p[1] in (0x01, 0x02)]


def setting_subcommands(fw):
    """The per-setting query/get/set/reset requests seen on the wire, either form."""
    return [p for p in fw.wire if p[0] in (0xFE, msw.ALIAS_VIAL_PREFIX) and 0x09 <= p[1] <= 0x0C]


if __name__ == "__main__":
    unittest.main()
