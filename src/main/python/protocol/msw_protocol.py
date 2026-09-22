# SPDX-License-Identifier: GPL-2.0-or-later
"""MIDIswitch raw-HID protocol: IDENT ("who are you") and command aliases.

Two things live here:

1. IDENT: custom-family command 0x00 (``7D 00 4D 00``). The app sends it
   before anything else. A keyboard that answers it is a MIDIswitch and
   reports its protocol version, firmware version, EEPROM layout version,
   capabilities, model id / model UID and a per-unit hardware id. A keyboard
   that does not know the command echoes it back with an error status.

2. Command aliases. Every configurator command that is still addressed by a
   byte-0 id (the ids 0x01..0x13 and the 0xFE sub-command prefix) has a
   MIDIswitch byte-0 value. When IDENT has answered, the app sends the
   alias byte instead of the original id; the keyboard maps it back before
   its handler runs. Payload bytes never move — only byte 0 is renamed — so
   the two forms carry identical data and the rest of the app is unaware of
   which one is on the wire. ``ProtocolKeyboard.usb_send`` applies
   :func:`encode_request` / :func:`decode_response` around every packet.

The alias values are a wire contract with the firmware; change both sides
or neither.
"""
import struct

# ---- IDENT ------------------------------------------------------------------

MSW_CMD_IDENT = 0x00
MSW_IDENT_MAGIC = b"MSW"
MSW_PROTOCOL_MAJOR_SUPPORTED = 1  # 1 = alias layer over the legacy payload formats

# Capability bits (u32 in the IDENT response).
MSW_CAP_LEGACY_PATHS = 1 << 0   # original byte-0 ids still answered
MSW_CAP_DEFINITION = 1 << 1     # layout definition downloadable
MSW_CAP_DIGITIZER = 1 << 2
MSW_CAP_DIN_MIDI = 1 << 3
MSW_CAP_RGB_MATRIX = 1 << 4
MSW_CAP_CLONE = 1 << 5

# Payload-format levels the MSW protocol 1 keyboard implements. The app's
# feature gates were written against these numbers; the alias layer carries
# exactly those payload formats, so they are fixed for protocol major 1.
MSW1_VIA_LEVEL = 9
MSW1_VIAL_LEVEL = 6

_IDENT_FMT = "<BBBBBBBBBHIB8sI"  # from byte 4: status, magic*3, proto*2, fw*3, layout, caps, model, uid, hwid


def build_ident_request():
    """The 32-byte IDENT request packet."""
    return bytes([0x7D, 0x00, 0x4D, MSW_CMD_IDENT]) + b"\x00" * 28


def parse_ident(response):
    """Return the IDENT fields as a dict, or None if ``response`` is not a
    valid IDENT reply (wrong echo, error status, missing magic)."""
    if not response or len(response) < 32:
        return None
    if bytes(response[0:4]) != bytes([0x7D, 0x00, 0x4D, MSW_CMD_IDENT]):
        return None
    (status, m0, m1, m2, proto_major, proto_minor, fw_major, fw_minor, fw_patch,
     layout_version, caps, model_id, uid, hwid) = struct.unpack_from(_IDENT_FMT, bytes(response), 4)
    if status != 1 or bytes([m0, m1, m2]) != MSW_IDENT_MAGIC:
        return None
    return {
        "protocol": (proto_major, proto_minor),
        "firmware": (fw_major, fw_minor, fw_patch),
        "eeprom_layout_version": layout_version,
        "capabilities": caps,
        "model_id": model_id,
        "model_uid": struct.unpack("<Q", uid)[0],
        "hardware_id": hwid,
    }


# ---- Aliases ----------------------------------------------------------------

LEGACY_VIA_FIRST = 0x01
LEGACY_VIA_LAST = 0x13
LEGACY_VIAL_PREFIX = 0xFE

ALIAS_VIA_BASE = 0x2A        # 0x01..0x13 -> 0x2A..0x3C
ALIAS_VIAL_PREFIX = 0x4D     # 0xFE -> 0x4D

VIA_TO_ALIAS = {legacy: ALIAS_VIA_BASE + (legacy - LEGACY_VIA_FIRST)
                for legacy in range(LEGACY_VIA_FIRST, LEGACY_VIA_LAST + 1)}
ALIAS_TO_VIA = {alias: legacy for legacy, alias in VIA_TO_ALIAS.items()}


def encode_request(msg):
    """Rewrite byte 0 of an outgoing packet to its alias. Packets that carry
    no aliased id (the custom family, anything unknown) are returned as-is."""
    if not msg:
        return msg
    b0 = msg[0]
    if b0 in VIA_TO_ALIAS:
        return bytes([VIA_TO_ALIAS[b0]]) + bytes(msg[1:])
    if b0 == LEGACY_VIAL_PREFIX:
        return bytes([ALIAS_VIAL_PREFIX]) + bytes(msg[1:])
    return msg


def decode_response(request_msg, response):
    """Undo the alias on a reply so callers see the byte-0 value they
    expect. A byte-0 id command replies with the id in byte 0, so that byte
    is mapped back; if the keyboard replaced it (its 0xFF "unhandled"
    marker) it is left alone. Sub-command (0xFE) replies never carry the
    prefix — byte 0 is a status or data byte — so they are returned
    untouched."""
    if not request_msg or not response:
        return response
    b0 = request_msg[0]
    if b0 in VIA_TO_ALIAS and response[0] == VIA_TO_ALIAS[b0]:
        return bytes([b0]) + bytes(response[1:])
    return response


def is_alias_candidate(msg):
    """True if :func:`encode_request` would change this packet."""
    return bool(msg) and (msg[0] in VIA_TO_ALIAS or msg[0] == LEGACY_VIAL_PREFIX)


# ---- Macro Settings ---------------------------------------------------------
#
# The three timing settings the Macro Settings page edits, as ONE explicit
# custom-family command (0x98) instead of the per-setting sub-commands:
#
#   request  data[4] = sub-command: 0 GET, 1 SET, 2 RESET
#            SET payload: data[6..11] = three u16 LE, in MACRO_SETTINGS_QSIDS order
#   response status@4 (1 = ok), then the CURRENT values as three u16 LE at
#            5..10 - for every sub-command, so the caller refreshes from it.
#
# The keys are the app's own setting ids (the ones qmk_settings.json lists),
# so the settings page, .vil save/restore and the About dialog are unchanged.
#
# The macro Mouse Move timing rides the same command, feature-detected by a
# marker byte so an app and a firmware of different ages never misread it:
#   SET      data[12..15] = click delay, double-click speed (u16 LE each),
#            data[16] = MSET_MOUSE_MARKER (without it the mouse values are
#            left alone)
#   response click delay, double-click speed (u16 LE) at 11..14 and
#            MSET_MOUSE_MARKER at 15 when the firmware has them
# They use app-side ids (MOUSE_SETTINGS_IDS) that are not device setting ids.

MSW_CMD_MACRO_SETTINGS = 0x98
MSW_MSET_GET = 0
MSW_MSET_SET = 1
MSW_MSET_RESET = 2
MACRO_SETTINGS_QSIDS = (7, 18, 6)   # hold duration, gap between macro keys, one-shot timeout
MOUSE_CLICK_DELAY_ID = 0x1001        # wait after a macro mouse move before clicking (ms)
MOUSE_DOUBLE_CLICK_ID = 0x1002       # gap between the two clicks of a double click (ms)
MOUSE_SETTINGS_IDS = (MOUSE_CLICK_DELAY_ID, MOUSE_DOUBLE_CLICK_ID)
MSET_MOUSE_MARKER = 0x4D

_MSET_HEADER = bytes([0x7D, 0x00, 0x4D, MSW_CMD_MACRO_SETTINGS])


def build_macro_settings_request(sub, values=None):
    """The 32-byte Macro Settings packet. ``values`` maps setting id -> value
    and is required for SET (every id in MACRO_SETTINGS_QSIDS)."""
    pkt = bytearray(_MSET_HEADER) + bytearray(28)
    pkt[4] = sub
    if sub == MSW_MSET_SET:
        struct.pack_into("<HHH", pkt, 6, *[int(values[q]) & 0xFFFF for q in MACRO_SETTINGS_QSIDS])
        if all(q in values for q in MOUSE_SETTINGS_IDS):
            struct.pack_into("<HH", pkt, 12, *[int(values[q]) & 0xFFFF for q in MOUSE_SETTINGS_IDS])
            pkt[16] = MSET_MOUSE_MARKER
    return bytes(pkt)


def parse_macro_settings(response):
    """Return {setting id: value} from a Macro Settings reply, or None if the
    reply is not a successful echo of the command."""
    if not response or len(response) < 11:
        return None
    if bytes(response[0:4]) != _MSET_HEADER or response[4] != 1:
        return None
    vals = struct.unpack_from("<HHH", bytes(response), 5)
    out = dict(zip(MACRO_SETTINGS_QSIDS, vals))
    if len(response) >= 16 and response[15] == MSET_MOUSE_MARKER:
        out.update(zip(MOUSE_SETTINGS_IDS, struct.unpack_from("<HH", bytes(response), 11)))
    return out
