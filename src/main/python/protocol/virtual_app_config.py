# SPDX-License-Identifier: GPL-2.0-or-later
"""The software keyboard's side of MSW_CMD_APP_CONFIG (0x8F), so the editors
that use protocol/app_config.py work against the demo keyboard. It keeps the
values it is given and hands them back; it does not model what they do."""

import struct

from protocol import app_config as ac

_DL_PRESETS = ["All On", "All Off", "Kick Only", "Snare Only", "Hats Only", "Kick & Snare",
               "Kick Snare Hats", "No Kick", "No Snare", "Quiet Hats", "Loud All", "Punchy"]
_PROGRESSIONS = [("I-V-vi-IV", 4, 0), ("I-IV-V", 3, 0), ("ii-V-I", 3, 0), ("I-vi-IV-V", 4, 0),
                 ("i-VI-III-VII", 4, 1), ("i-iv-v", 3, 1), ("i-VII-VI-V", 4, 1), ("12 Bar Blues", 12, 0)]
_RHYTHMS = ["Whole Notes", "Half Notes", "Quarter Notes", "Eighths", "Syncopated", "Reggae Skank",
            "Bossa", "Four on the Floor"]
_PATTERNS = ["Rock 1", "Rock 2", "Pop 1", "Funk 1", "House 1", "Hip Hop 1", "Trap 1", "Latin 1"]
_USER_PATTERN_FIRST, _USER_PATTERN_COUNT = 0x8000, 40      # user sequences as drum patterns
_BASICS = 35
_SLOT_COUNTS = {0: 4, 1: 8, 2: 4, 3: 20, 4: 8, 5: 40, 6: 20, 7: 8, 8: 6, 9: 6, 10: 10, 11: 11, 12: 12,
                13: 16, 14: 16, 15: 12, 16: 22, 17: 16, 18: 48, 19: 8, 20: 10, 21: 1, 22: 20, 23: 48,
                24: 50, 25: 119, 26: 40, 27: 40, 28: _BASICS, 29: 8, 30: 255, 31: 100, 32: 16, 33: 10}
_SC_BASE = {11: 0xC38B, 12: 0xC396, 13: 0xC3A2, 14: 0xC3B2, 15: 0xC3C2, 16: 0xC3CE, 17: 0xC3FA}


class VirtualAppConfig:

    def __init__(self):
        self.qb = [[ac.QB_UNSET, 0, 0] for _ in range(ac.QB_COUNT)]
        self.qb_cc = [[0, 0] for _ in range(ac.QB_COUNT)]
        self.qb_arp = [[0, 0] for _ in range(ac.QB_COUNT)]
        # a few bindings so the overview has something to show
        for qb_id, (category, slot) in enumerate([(19, 0), (19, 1), (13, 8), (14, 2), (26, 0), (32, 1), (33, 0)]):
            self.qb[qb_id] = [category, slot, 0]
        blank_zone = struct.pack("<BbBB", 0, 0, 0xFF, 0)
        self.ksp = [bytearray(bytes([0]) + blank_zone * 3 + b"\x00") for _ in range(ac.KSP_COUNT)]
        self.ksp_active = [False] * ac.KSP_COUNT
        self.dl_edit = [0] * ac.DL_VOICINGS
        self.dl_slots = [([0] * ac.DL_VOICINGS, b"") for _ in range(ac.DL_SLOTS)]
        self.re = [bytearray(struct.pack("<BHHBBBbBB", 0, i % len(_PROGRESSIONS), i % len(_RHYTHMS), 0, 0, 2, 0, 0, 0))
                   for i in range(ac.RE_SLOTS)]
        self.dm = [{"head": bytearray(struct.pack("<HBBBB", 0xFFFF, 9, 2, 0, 0)),
                    "notes": bytearray([36, 38, 42, 46, 39, 37, 56, 51, 45, 47, 50, 70]),
                    "velocities": bytearray([100] * 12)} for _ in range(ac.DM_SLOTS)]
        self.dm_chain = [[] for _ in range(ac.DM_SLOTS)]
        self.dm_chain_tail = [[ac.DM_NO_PATTERN] * 8 for _ in range(ac.DM_SLOTS)]
        self.fd = [bytearray(11) for _ in range(ac.FD_SLOTS)]
        self.vl_rules = bytearray([0, 0, 0, 0, 0, 0])
        self.vl_priority = bytearray([0, 1, 2, 3, 4, 5])
        self.sc = [bytearray(7) for _ in range(ac.SC_SLOTS)]

    # ---- helpers ---------------------------------------------------------------

    def _qb_reply(self, r, qb_id):
        category, slot, flags = self.qb[qb_id]
        target = _SC_BASE[category] + slot if category in _SC_BASE else 0
        r[6:10] = bytes([qb_id, category, slot, flags])
        struct.pack_into("<HHB", r, 10, target, self.qb_cc[qb_id][0], self.qb_cc[qb_id][1])
        r[15], r[16] = self.qb_arp[qb_id]
        r[17] = 0 if category == ac.QB_UNSET else 1

    def _dl_reply(self, r):
        r[6] = 4 if any(self.dl_edit) else 0
        r[7:14] = ac.pack_modes(self.dl_edit)
        r[14:21] = ac.pack_modes(self.dl_edit)

    def _ksp_forces_something(self, p):
        """A zone in use with a channel, transpose, curve, auto-notes or
        sustain of its own (the firmware's ksp_any_field_set)."""
        raw = self.ksp[p]
        for z in range(3):
            channel, _transpose, curve, flags = struct.unpack_from("<BbBB", raw, 1 + z * 4)
            if raw[0] & (1 << z) and (channel > 0 or curve != 0xFF or flags & 0x1F):
                return True
        return False

    @staticmethod
    def _pattern_valid(index):
        """A factory pattern, or one of the user's sequences (the firmware's
        seq_pattern_index_valid)."""
        return index < len(_PATTERNS) or \
            _USER_PATTERN_FIRST <= index < _USER_PATTERN_FIRST + _USER_PATTERN_COUNT

    @staticmethod
    def _name(r, offset, size, text):
        raw = text.encode("ascii", "replace")[:size - 1]
        r[offset:offset + len(raw)] = raw

    # ---- the command -----------------------------------------------------------

    def handle(self, msg):
        r = bytearray(32)
        r[0:4] = msg[0:4]
        sub = msg[4]
        r[5] = sub
        a = msg[6:32]
        ok = self._dispatch(sub, a, r)
        if not ok:
            r[6:] = bytes(26)
        r[4] = 1 if ok else 0
        return r

    def _dispatch(self, sub, a, r):
        if sub == ac.SUB_INFO:
            r[6], r[7] = 1, ac.QB_COUNT
            return True

        if sub in (ac.SUB_QB_GET, ac.SUB_QB_SET):
            qb_id = a[0]
            if qb_id >= ac.QB_COUNT:
                return False
            if sub == ac.SUB_QB_SET:
                category, slot, flags = a[1], a[2], a[3]
                if category == ac.QB_UNSET:
                    slot = flags = 0
                elif category not in _SLOT_COUNTS or slot >= _SLOT_COUNTS[category]:
                    return False
                elif category == 21 and (a[4] | (a[5] << 8)) == 0:
                    return False
                if category not in (3, 25) and category not in _SC_BASE:
                    flags = 0
                self.qb[qb_id] = [category, slot, flags & 0x1F if category != 25 else flags]
                self.qb_cc[qb_id] = [a[4] | (a[5] << 8), a[6]] if category == 21 else [0, 0]
                if category == 25:
                    self.qb_arp[qb_id] = [a[7], a[8]]
            self._qb_reply(r, qb_id)
            return True
        if sub == ac.SUB_QB_GET_BULK:
            first = a[0]
            if first >= ac.QB_COUNT:
                return False
            count = min(8, ac.QB_COUNT - first)
            r[6], r[7] = first, count
            for i in range(count):
                r[8 + i * 3: 11 + i * 3] = bytes(self.qb[first + i])
            return True

        if sub in (ac.SUB_KSP_GET, ac.SUB_KSP_SET, ac.SUB_KSP_SWITCH):
            p = a[0]
            if p >= ac.KSP_COUNT:
                return False
            if sub == ac.SUB_KSP_SET:
                self.ksp[p] = bytearray(a[1:15])
            elif sub == ac.SUB_KSP_SWITCH:
                # as the firmware (ksp_apply): turning on a preset that forces
                # nothing is refused; one that is already on stays on
                if a[1] and not self.ksp_active[p] and not self._ksp_forces_something(p):
                    return False
                self.ksp_active[p] = bool(a[1])
            r[6], r[7] = p, int(self.ksp_active[p])
            r[8:22] = self.ksp[p]
            return True

        if sub in (ac.SUB_DL_GET, ac.SUB_DL_SET, ac.SUB_DL_PRESET):
            if sub == ac.SUB_DL_SET:
                self.dl_edit = ac.unpack_modes(a[0:7])
            elif sub == ac.SUB_DL_PRESET:
                if a[0] >= len(_DL_PRESETS):
                    return False
                # stand-in: preset 0 is everything on, 1 everything off, others mute a rotating voicing
                self.dl_edit = [0] * ac.DL_VOICINGS if a[0] == 0 else \
                    [1] * ac.DL_VOICINGS if a[0] == 1 else \
                    [1 if i % (a[0] + 1) else 0 for i in range(ac.DL_VOICINGS)]
            self._dl_reply(r)
            return True
        if sub == ac.SUB_DL_PRESET_NAME:
            if a[0] >= len(_DL_PRESETS):
                return False
            r[6], r[7] = a[0], len(_DL_PRESETS)
            self._name(r, 8, 16, _DL_PRESETS[a[0]])
            return True
        if sub in (ac.SUB_DL_SLOT_GET, ac.SUB_DL_SLOT_SET):
            slot = a[0]
            if slot >= ac.DL_SLOTS:
                return False
            if sub == ac.SUB_DL_SLOT_SET:
                self.dl_slots[slot] = (ac.unpack_modes(a[1:8]), bytes(a[8:24]).split(b"\x00", 1)[0])
            snapshot, name = self.dl_slots[slot]
            r[6], r[7] = slot, int(any(snapshot) or bool(name))
            r[8:15] = ac.pack_modes(snapshot)
            r[15:15 + len(name)] = name
            return True

        if sub in (ac.SUB_RE_GET, ac.SUB_RE_SET):
            slot = a[0]
            if slot >= ac.RE_SLOTS:
                return False
            if sub == ac.SUB_RE_SET:
                self.re[slot] = bytearray(a[1:12])
            r[6] = slot
            r[7:18] = self.re[slot]
            return True
        if sub == ac.SUB_RE_INFO:
            struct.pack_into("<HH", r, 6, len(_PROGRESSIONS), len(_RHYTHMS))
            return True
        if sub == ac.SUB_RE_PROG_NAME:
            index = a[0] | (a[1] << 8)
            if index >= len(_PROGRESSIONS):
                return False
            name, length, minor = _PROGRESSIONS[index]
            struct.pack_into("<HBB", r, 6, index, length, minor)
            self._name(r, 10, 22, name)
            return True
        if sub == ac.SUB_RE_RHYTHM_NAME:
            index = a[0] | (a[1] << 8)
            if index >= len(_RHYTHMS):
                return False
            struct.pack_into("<H", r, 6, index)
            self._name(r, 8, 24, _RHYTHMS[index])
            return True

        if sub in (ac.SUB_DM_GET, ac.SUB_DM_SET):
            slot, part = a[0], a[1]
            if slot >= ac.DM_SLOTS or part > 1:
                return False
            entry = self.dm[slot]
            if sub == ac.SUB_DM_SET:
                if part == 0:
                    entry["head"] = bytearray(a[2:8])
                else:
                    entry["notes"], entry["velocities"] = bytearray(a[2:14]), bytearray(a[14:26])
            r[6], r[7] = slot, part
            if part == 0:
                r[8:14] = entry["head"]
            else:
                r[8:20], r[20:32] = entry["notes"], entry["velocities"]
            return True
        if sub == ac.SUB_DM_INFO:
            struct.pack_into("<H", r, 6, len(_PATTERNS))
            return True
        if sub == ac.SUB_DM_PATTERN_NAME:
            index = a[0] | (a[1] << 8)
            if not self._pattern_valid(index):
                return False
            struct.pack_into("<H", r, 6, index)
            # a user sequence used as a drum pattern is named after its number
            self._name(r, 8, 24, _PATTERNS[index] if index < len(_PATTERNS)
                       else "User Seq %d" % (index - _USER_PATTERN_FIRST + 1))
            return True

        if sub in (ac.SUB_DM_CHAIN_GET, ac.SUB_DM_CHAIN_SET):
            slot, part = a[0], a[1]
            if slot >= ac.DM_SLOTS or part > 1:
                return False
            if sub == ac.SUB_DM_CHAIN_SET:
                length = a[2]
                beats = list(struct.unpack_from("<8H", bytes(a), 4))
                if any(b != ac.DM_NO_PATTERN and not self._pattern_valid(b) for b in beats) \
                        or length > ac.DM_CHAIN_MAX:
                    return False
                if part == 1:
                    self.dm_chain_tail[slot] = beats
                else:
                    if length == 1:
                        length = 0
                    if length and beats[0] == ac.DM_NO_PATTERN:
                        return False
                    self.dm_chain[slot] = (beats + self.dm_chain_tail[slot])[:length]
                    if length:
                        struct.pack_into("<H", self.dm[slot]["head"], 0, beats[0])
            chain = self.dm_chain[slot] + [ac.DM_NO_PATTERN] * (ac.DM_CHAIN_MAX - len(self.dm_chain[slot]))
            r[6], r[7], r[8] = slot, part, len(self.dm_chain[slot])
            struct.pack_into("<8H", r, 10, *chain[part * 8: part * 8 + 8])
            return True

        if sub in (ac.SUB_FD_GET, ac.SUB_FD_SET):
            slot = a[0]
            if slot >= ac.FD_SLOTS:
                return False
            if sub == ac.SUB_FD_SET:
                self.fd[slot] = bytearray(a[1:12]) if a[1] & 1 else bytearray(11)
            r[6] = slot
            r[7:18] = self.fd[slot]
            return True

        if sub in (ac.SUB_VL_GET, ac.SUB_VL_SET, ac.SUB_VL_RESET):
            if sub == ac.SUB_VL_SET:
                if sorted(a[6:12]) != [0, 1, 2, 3, 4, 5] or any(rule > 4 for rule in a[0:6]):
                    return False
                self.vl_rules, self.vl_priority = bytearray(a[0:6]), bytearray(a[6:12])
            elif sub == ac.SUB_VL_RESET:
                self.vl_rules, self.vl_priority = bytearray(6), bytearray([0, 1, 2, 3, 4, 5])
            r[6:12], r[12:18] = self.vl_rules, self.vl_priority
            return True

        if sub in (ac.SUB_SC_GET, ac.SUB_SC_SET):
            slot = a[0]
            if slot >= ac.SC_SLOTS:
                return False
            if sub == ac.SUB_SC_SET:
                count = a[1]
                intervals = list(a[2:2 + min(count, 6)])
                if count > 6 or 0 in intervals or len(set(intervals)) != len(intervals):
                    return False
                self.sc[slot] = bytearray([count]) + bytearray(a[2:8]) if count else bytearray(7)
            r[6] = slot
            r[7:14] = self.sc[slot]
            return True

        return False
