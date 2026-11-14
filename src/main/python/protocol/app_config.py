# SPDX-License-Identifier: GPL-2.0-or-later
"""App access to the keyboard's QuickBuild-related settings: one raw-HID
command, MSW_CMD_APP_CONFIG (0x8F), with a sub-command per thing.

    Request:  [3]=0x8F  [4]=sub  [5]=0  [6..31]=arguments
    Reply:    [4]=status (1 ok, 0 refused)  [5]=sub echoed  [6..31]=data

Older firmware does not know the command and never answers it, so every
editor that uses this checks AppConfig.supported() first (asked once per
keyboard) and otherwise says the firmware needs updating.

Numbers are little-endian; slots, ids and presets count from 0. The byte
layouts below are the firmware's (app/ext/msw_hid.h); keep the two in step.
"""

import struct
import time

HID_CMD_APP_CONFIG = 0x8F
SUPPORT_ASK_AGAIN_S = 5.0       # how long an unanswered INFO counts as "not supported"

SUB_INFO = 0x00
SUB_QB_GET, SUB_QB_SET, SUB_QB_GET_BULK = 0x01, 0x02, 0x03
SUB_KSP_GET, SUB_KSP_SET, SUB_KSP_SWITCH = 0x10, 0x11, 0x12
SUB_DL_GET, SUB_DL_SET, SUB_DL_PRESET, SUB_DL_PRESET_NAME, SUB_DL_SLOT_GET, SUB_DL_SLOT_SET = \
    0x20, 0x21, 0x22, 0x23, 0x24, 0x25
SUB_RE_GET, SUB_RE_SET, SUB_RE_INFO, SUB_RE_PROG_NAME, SUB_RE_RHYTHM_NAME = 0x30, 0x31, 0x32, 0x33, 0x34
SUB_DM_GET, SUB_DM_SET, SUB_DM_INFO, SUB_DM_PATTERN_NAME = 0x40, 0x41, 0x42, 0x43
SUB_DM_CHAIN_GET, SUB_DM_CHAIN_SET = 0x44, 0x45
SUB_FD_GET, SUB_FD_SET = 0x50, 0x51
SUB_VL_GET, SUB_VL_SET, SUB_VL_RESET = 0x60, 0x61, 0x62
SUB_SC_GET, SUB_SC_SET = 0x70, 0x71

QB_COUNT = 100
QB_UNSET = 0xFF
KSP_COUNT = 10
DL_VOICINGS = 28
DL_SLOTS = 48
RE_SLOTS = 20
DM_SLOTS = 20
DM_CHAIN_MAX = 16
DM_NO_PATTERN = 0xFFFF
FD_SLOTS = 40
SC_SLOTS = 20


def _text(raw):
    return bytes(raw).split(b"\x00", 1)[0].decode("ascii", "replace").strip()


def pack_modes(modes):
    """28 DrumLIVE modes (0..3) -> 7 bytes, two bits each."""
    out = bytearray(7)
    for i, mode in enumerate(modes[:DL_VOICINGS]):
        out[i // 4] |= (mode & 3) << ((i % 4) * 2)
    return bytes(out)


def unpack_modes(raw):
    return [(raw[i // 4] >> ((i % 4) * 2)) & 3 for i in range(DL_VOICINGS)]


class AppConfig:
    """The 0x8F commands for one keyboard (a protocol.keyboard_comm.Keyboard)."""

    def __init__(self, keyboard):
        self.keyboard = keyboard
        self._supported = None
        self._asked_at = None       # when INFO last went unanswered (time.monotonic())

    # ---- transport -------------------------------------------------------------

    def _exchange(self, sub, args=b"", retries=3):
        """Send one sub-command. Returns the keyboard's whole reply to it, or
        None if it did not answer (or answered something else)."""
        try:
            kb = self.keyboard
            packet = kb._create_hid_packet(HID_CMD_APP_CONFIG, sub, list(bytes(args)) or None)
            data = kb.usb_send(kb.dev, packet, retries=retries)
        except Exception:
            return None
        if not data or len(data) < 32 or data[3] != HID_CMD_APP_CONFIG or data[5] != sub:
            return None
        return bytes(data[:32])

    def request(self, sub, args=b"", retries=3):
        """Send one sub-command. Returns the reply's data bytes ([6..31]) or
        None if the keyboard refused it or did not answer."""
        data = self._exchange(sub, args, retries)
        if data is None or data[4] != 1:
            return None
        return data[6:32]

    def supported(self):
        """Whether this keyboard's firmware knows the command. An answer is
        remembered for good. No answer is what older firmware gives, but also
        what one lost reply looks like, so it is asked a second time before
        saying no, and that "no" is only kept for a few seconds: the pages ask
        this each time they are shown, and a keyboard that was only busy is
        then found to be fine without waiting for a reconnect."""
        if self._supported is not None:
            return self._supported
        now = time.monotonic()
        if self._asked_at is not None and now - self._asked_at < SUPPORT_ASK_AGAIN_S:
            return False
        for _ in range(2):
            data = self._exchange(SUB_INFO, retries=1)
            if data is not None:
                self._supported = data[4] == 1 and data[6] >= 1
                return self._supported
        self._asked_at = time.monotonic()
        return False

    # ---- QuickBuild masters ----------------------------------------------------

    @staticmethod
    def _qb(reply):
        if reply is None:
            return None
        return {"id": reply[0], "category": reply[1], "slot": reply[2], "flags": reply[3],
                "target_keycode": reply[4] | (reply[5] << 8),
                "cc_keycode": reply[6] | (reply[7] << 8), "cc_channel": reply[8],
                "arp_rate": reply[9], "arp_gate": reply[10], "configured": bool(reply[11])}

    def qb_get(self, qb_id):
        return self._qb(self.request(SUB_QB_GET, [qb_id]))

    def qb_set(self, qb_id, category, slot=0, flags=0, cc_keycode=0, cc_channel=0, arp_rate=0, arp_gate=0):
        return self._qb(self.request(SUB_QB_SET, [
            qb_id, category, slot, flags, cc_keycode & 0xFF, (cc_keycode >> 8) & 0xFF,
            cc_channel, arp_rate, arp_gate]))

    def qb_get_all(self):
        """[(category, slot, flags)] x 100, or None."""
        out = []
        while len(out) < QB_COUNT:
            reply = self.request(SUB_QB_GET_BULK, [len(out)])
            if reply is None or reply[0] != len(out) or not 1 <= reply[1] <= 8:
                return None
            for i in range(reply[1]):
                out.append(tuple(reply[2 + i * 3: 5 + i * 3]))
        return out[:QB_COUNT]

    # ---- KeySplit presets ------------------------------------------------------
    # A preset: {"zone_en": bits, "zones": [zone x3]}; a zone: channel (0 = master,
    # 1-16), transpose (None = master, else -64..64), curve (None = master),
    # auto_notes and sustain (0 master / 1 allow / 2 ignore).

    @staticmethod
    def _ksp(reply):
        if reply is None:
            return None
        raw = reply[2:16]
        zones = []
        for z in range(3):
            channel, transpose, curve, flags = struct.unpack_from("<BbBB", raw, 1 + z * 4)
            zones.append({"channel": channel,
                          "transpose": transpose if flags & 1 else None,
                          "curve": None if curve == 0xFF else curve,
                          "auto_notes": (flags >> 1) & 3, "sustain": (flags >> 3) & 3})
        return {"preset": reply[0], "active": bool(reply[1]), "zone_en": raw[0], "zones": zones}

    @staticmethod
    def _ksp_bytes(preset):
        raw = bytearray(14)
        raw[0] = preset["zone_en"] & 7
        for z, zone in enumerate(preset["zones"][:3]):
            flags = ((zone["auto_notes"] & 3) << 1) | ((zone["sustain"] & 3) << 3)
            transpose = 0
            if zone["transpose"] is not None:
                flags |= 1
                transpose = zone["transpose"]
            curve = 0xFF if zone["curve"] is None else zone["curve"]
            struct.pack_into("<BbBB", raw, 1 + z * 4, zone["channel"], transpose, curve, flags)
        return bytes(raw)

    def ksp_get(self, preset):
        return self._ksp(self.request(SUB_KSP_GET, [preset]))

    def ksp_set(self, preset, config):
        return self._ksp(self.request(SUB_KSP_SET, bytes([preset]) + self._ksp_bytes(config)))

    def ksp_switch(self, preset, on):
        return self._ksp(self.request(SUB_KSP_SWITCH, [preset, 1 if on else 0]))

    # ---- DrumLIVE --------------------------------------------------------------

    @staticmethod
    def _dl(reply):
        if reply is None:
            return None
        return {"pending": bool(reply[0] & 1), "authoring": bool(reply[0] & 2), "filtering": bool(reply[0] & 4),
                "edit": unpack_modes(reply[1:8]), "active": unpack_modes(reply[8:15])}

    def dl_get(self):
        return self._dl(self.request(SUB_DL_GET))

    def dl_set(self, modes):
        return self._dl(self.request(SUB_DL_SET, pack_modes(modes)))

    def dl_apply_preset(self, number):
        return self._dl(self.request(SUB_DL_PRESET, [number]))

    def dl_preset_names(self):
        """Names of the factory presets, in order ([] if unreadable)."""
        names = []
        count = 1
        while len(names) < count:
            reply = self.request(SUB_DL_PRESET_NAME, [len(names)])
            if reply is None or reply[0] != len(names):
                return names
            count = reply[1]
            if count == 0:
                break
            names.append(_text(reply[2:18]))
        return names

    @staticmethod
    def _dl_slot(reply):
        if reply is None:
            return None
        return {"slot": reply[0], "configured": bool(reply[1]),
                "snapshot": unpack_modes(reply[2:9]), "name": _text(reply[9:25])}

    def dl_slot_get(self, slot):
        return self._dl_slot(self.request(SUB_DL_SLOT_GET, [slot]))

    def dl_slot_set(self, slot, snapshot, name):
        raw = name.encode("ascii", "replace")[:15].ljust(16, b"\x00")
        return self._dl_slot(self.request(SUB_DL_SLOT_SET, bytes([slot]) + pack_modes(snapshot) + raw))

    # ---- Rhythm Engine ---------------------------------------------------------
    RE_FIELDS = ("key", "progression", "rhythm", "voicing", "channel", "velocity_curve",
                 "transpose", "humanize", "instrument")
    _RE_FORMAT = "<BHHBBBbBB"       # 11 bytes

    def _re(self, reply):
        if reply is None:
            return None
        out = dict(zip(self.RE_FIELDS, struct.unpack_from(self._RE_FORMAT, reply, 1)))
        out["slot"] = reply[0]
        return out

    def re_get(self, slot):
        return self._re(self.request(SUB_RE_GET, [slot]))

    def re_set(self, slot, config):
        raw = struct.pack(self._RE_FORMAT, *[config[name] for name in self.RE_FIELDS])
        return self._re(self.request(SUB_RE_SET, bytes([slot]) + raw))

    def re_info(self):
        reply = self.request(SUB_RE_INFO)
        if reply is None:
            return None
        progressions, rhythms = struct.unpack_from("<HH", reply, 0)
        return {"progressions": progressions, "rhythms": rhythms}

    def re_progression(self, index):
        reply = self.request(SUB_RE_PROG_NAME, struct.pack("<H", index))
        if reply is None:
            return None
        return {"name": _text(reply[4:26]), "length": reply[2], "minor": bool(reply[3])}

    def re_rhythm_name(self, index):
        reply = self.request(SUB_RE_RHYTHM_NAME, struct.pack("<H", index))
        return None if reply is None else _text(reply[2:26])

    # ---- Drum Machine ----------------------------------------------------------

    def dm_get(self, slot):
        """{"pattern" (0xFFFF = empty), "channel", "velocity_curve", "humanize_on",
        "humanize", "notes"[12], "velocities"[12]} or None."""
        a = self.request(SUB_DM_GET, [slot, 0])
        b = self.request(SUB_DM_GET, [slot, 1])
        if a is None or b is None:
            return None
        return {"slot": slot, "pattern": a[2] | (a[3] << 8), "channel": a[4], "velocity_curve": a[5],
                "humanize_on": bool(a[6]), "humanize": a[7],
                "notes": list(b[2:14]), "velocities": list(b[14:26])}

    def dm_set(self, slot, config):
        a = self.request(SUB_DM_SET, [slot, 0, config["pattern"] & 0xFF, (config["pattern"] >> 8) & 0xFF,
                                      config["channel"], config["velocity_curve"],
                                      1 if config["humanize_on"] else 0, config["humanize"]])
        b = self.request(SUB_DM_SET, bytes([slot, 1]) + bytes(config["notes"][:12]) + bytes(config["velocities"][:12]))
        return a is not None and b is not None

    def dm_pattern_count(self):
        reply = self.request(SUB_DM_INFO)
        return None if reply is None else reply[0] | (reply[1] << 8)

    def dm_pattern_name(self, index):
        reply = self.request(SUB_DM_PATTERN_NAME, struct.pack("<H", index))
        return None if reply is None else _text(reply[2:26])

    # A chain plays several patterns one after another, one per bar: a list of
    # 2..16 pattern numbers ([] = no chain). Two packets each way, 8 bars in
    # each: [6]=slot [7]=part [8]=length [9]=0 [10..25]=8 x u16.

    def dm_chain_get(self, slot):
        """The slot's chain as a list of pattern numbers ([] = none), or None."""
        a = self.request(SUB_DM_CHAIN_GET, [slot, 0])
        b = self.request(SUB_DM_CHAIN_GET, [slot, 1])
        if a is None or b is None:
            return None
        patterns = list(struct.unpack_from("<8H", a, 4)) + list(struct.unpack_from("<8H", b, 4))
        return patterns[:min(a[2], DM_CHAIN_MAX)]

    def dm_chain_set(self, slot, patterns):
        """Store a chain ([] clears it). The second half goes first; the first
        half carries the length and makes the keyboard keep the whole chain.
        Returns the chain as the keyboard kept it, or None if it refused."""
        patterns = list(patterns)[:DM_CHAIN_MAX]
        padded = patterns + [DM_NO_PATTERN] * (DM_CHAIN_MAX - len(patterns))
        length = len(patterns)
        if self.request(SUB_DM_CHAIN_SET, bytes([slot, 1, length, 0]) + struct.pack("<8H", *padded[8:])) is None:
            return None
        if self.request(SUB_DM_CHAIN_SET, bytes([slot, 0, length, 0]) + struct.pack("<8H", *padded[:8])) is None:
            return None
        return self.dm_chain_get(slot)

    # ---- AutoFader -------------------------------------------------------------
    FD_FIELDS = ("flags", "cc", "channel", "start", "end", "style", "rate", "note_value",
                 "timing_mode", "duration_ms")
    _FD_FORMAT = "<BBBBBBBBBH"      # 11 bytes; flags bit0 saved, bit1 synced, bit2 defer

    def _fd(self, reply):
        if reply is None:
            return None
        out = dict(zip(self.FD_FIELDS, struct.unpack_from(self._FD_FORMAT, reply, 1)))
        out["slot"] = reply[0]
        return out

    def fd_get(self, slot):
        return self._fd(self.request(SUB_FD_GET, [slot]))

    def fd_set(self, slot, config):
        raw = struct.pack(self._FD_FORMAT, *[config[name] for name in self.FD_FIELDS])
        return self._fd(self.request(SUB_FD_SET, bytes([slot]) + raw))

    # ---- Voice leading ---------------------------------------------------------

    @staticmethod
    def _vl(reply):
        return None if reply is None else {"rules": list(reply[0:6]), "priority": list(reply[6:12])}

    def vl_get(self):
        return self._vl(self.request(SUB_VL_GET))

    def vl_set(self, rules, priority):
        return self._vl(self.request(SUB_VL_SET, bytes(rules[:6]) + bytes(priority[:6])))

    def vl_reset(self):
        return self._vl(self.request(SUB_VL_RESET))

    # ---- Custom SmartChords ----------------------------------------------------

    @staticmethod
    def _sc(reply):
        if reply is None:
            return None
        count = min(reply[1], 6)
        return {"slot": reply[0], "intervals": list(struct.unpack_from("<6b", reply, 2))[:count]}

    def sc_get(self, slot):
        return self._sc(self.request(SUB_SC_GET, [slot]))

    def sc_set(self, slot, intervals):
        """intervals: up to six semitone offsets from the root ([] erases)."""
        padded = (list(intervals)[:6] + [0] * 6)[:6]
        return self._sc(self.request(SUB_SC_SET, bytes([slot, min(len(intervals), 6)]) + struct.pack("<6b", *padded)))
