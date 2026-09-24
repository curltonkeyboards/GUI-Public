# SPDX-License-Identifier: GPL-2.0-or-later
"""MIDI / music replies for the virtual MIDIswitch.

Covers the MIDI settings packets and slots, the loop (ThruLoop) CC map and
loop transfers, the arpeggiator / step sequencer presets, velocity
(articulation) presets, MIDI delay slots, drum settings, multichannel echo,
channel articulations, navigation layer, DAW, LCD theme, macro loop modes,
active layer / firmware version and the settings-image info.
"""
import copy
import struct

_MSG = 32
_HDR = bytes([0x7D, 0x00, 0x4D])

# ---- keyboard (MIDI) settings: factory defaults --------------------------------
_KB_DEFAULTS = {
    "velocity_sensitivity": 1, "cc_sensitivity": 1, "channel_number": 0,
    "transpose": [0, 0, 0],            # combined transposition per zone, -64..+64
    "dynamic_range": 127, "oledkeyboard": 0, "loop_stop_mode": 0,
    "smartchordlightmode": 0, "chord_display_mode": 2,
    "base_sustain": 0, "keysplit_sustain": 0, "triplesplit_sustain": 0,
    "keysplitchannel": 0, "keysplit2channel": 0, "keysplitstatus": 0,
    "keysplittransposestatus": 0, "keysplitvelocitystatus": 0,
    "custom_layer_animations_enabled": 0, "unsynced_mode_active": 0,
    "sample_mode_active": 0, "instant_loop_start": 0, "colorblindmode": 0,
    "cclooprecording": 0, "truesustain": 0, "channeloverride": 0,
    "velocityoverride": 0, "transposeoverride": 0, "midi_in_mode": 0,
    "usb_midi_mode": 0, "midi_clock_source": 0, "macro_override_live_notes": 0,
    "smartchord_mode": 1, "base_smartchord_ignore": 0,
    "keysplit_smartchord_ignore": 0, "triplesplit_smartchord_ignore": 0,
    "he_velocity_curve": [2, 2, 2], "he_velocity_min": [1, 1, 1],
    "he_velocity_max": [127, 127, 127],
    # velocity timing after the Basic articulation is applied at start-up
    "min_press_time": 80, "max_press_time": 3,
    "lut_correction_strength": 100, "aftertouch_mode": 0, "aftertouch_cc": 255,
    "vibrato_sensitivity": 50, "vibrato_decay_time": 10, "trigger_min": 10,
    "velocity_as_at": 0,
}

# ---- loop CC map ---------------------------------------------------------------
_LOOPS = 8
_CC_NONE = 128
_LOOP_ARRAYS = ("restart", "start_rec", "stop_rec", "start_play", "stop_play", "clear",
                "od_start_rec", "od_stop_rec", "od_start_play", "od_stop_play", "od_clear",
                "od_restart")
_LOOP_CHUNK = 22

# ---- arpeggiator / step sequencer ------------------------------------------------
ARP_FACTORY = 119
ARP_USER_START = 119
ARP_MAX = ARP_USER_START + 40          # 159
SEQ_FACTORY_BASE = 68
SEQ_FACTORY = 48
SEQ_USER_START = 116
SEQ_MAX = SEQ_USER_START + 40           # 156
PRESET_NOTES_MAX = 255
POOL_MAX_NOTES = 3897
TYPE_ARP, TYPE_SEQ = 0, 1
ARP_MODES = 5

_NV_QUARTER, _NV_EIGHTH, _NV_SIXTEENTH = 0, 1, 2
_VS_FLAT, _VS_RISE, _VS_FALL = 0, 1, 2

# Factory pattern categories: (first id, count)
_AFC = [(0, 1), (1, 3), (4, 3), (7, 23), (30, 9), (39, 12), (51, 17), (68, 15), (83, 18), (101, 18)]
_AFC_BASIC, _AFC_ASC, _AFC_DESC, _AFC_SYNC, _AFC_OFF = 0, 1, 2, 3, 4
_AFC_CHORD = 9

_CH_TONES = [(0, 7), (0, 4, 7), (0, 3, 7), (0, 4, 7, 11), (0, 3, 7, 10), (0, 4, 7, 10)]
_CH_ORDER = {
    2: [(0, 1), (1, 0), (0, 1)],
    3: [(0, 2, 1), (2, 0, 1), (0, 1, 2)],
    4: [(0, 2, 1, 3), (0, 2, 3, 1), (2, 0, 3, 1)],
}

# 16th-step hit positions per rhythm grid, by category
_GRIDS = {
    3: [  # syncopated / world
        (0, 3, 6, 8, 11, 14), (0, 3, 6, 10, 12), (0, 3, 7, 10, 12), (0, 3, 8, 11),
        (0, 3, 6, 7, 10, 13), (0, 3, 6, 10, 13), (0, 2, 3, 5, 8, 11, 13, 14),
        (0, 2, 3, 5, 6, 8, 10, 11, 13, 14), (0, 3, 4, 6, 9, 10, 12, 14), (2, 4, 8, 11, 14),
        (2, 4, 8, 11, 15), (0, 2, 4, 6, 7, 9, 11, 13), (0, 4, 7, 10, 12),
        (0, 3, 4, 7, 8, 11, 12, 15), (0, 3, 6, 8, 11), (0, 3, 6, 7, 10, 14),
        (0, 2, 3, 6, 8, 10, 11, 14), (0, 2, 5, 6, 8, 10, 13), (0, 3, 6, 8, 11, 13),
        (0, 4, 6, 8, 11, 12, 14), (0, 2, 3, 6, 8, 10, 11, 13), (0, 3, 4, 7, 8, 11, 12, 14),
        (0, 3, 6, 9, 10, 12)],
    4: [  # off beat
        (2, 6, 10, 14), (1, 3, 5, 7, 9, 11, 13, 15), (2, 3, 6, 7, 10, 11, 14, 15),
        (0, 4, 7, 11, 14), (3, 7, 11, 15), (2, 5, 8, 11, 14), (1, 4, 7, 10, 13),
        (0, 3, 5, 6, 9, 11, 14), (2, 6, 8, 10, 14)],
    5: [  # rock / pop
        (0, 4, 8, 12), (0, 4, 7, 8, 12, 15), (0, 2, 4, 6, 8, 10, 12, 14),
        (0, 3, 4, 8, 11, 12, 15), (0, 4, 8, 10, 12), (0, 6, 8, 14), (0, 2, 4, 8, 10, 12),
        (0, 5, 8, 13), (0, 3, 4, 6, 8, 11, 12, 14), (0, 2, 4, 5, 8, 10, 12, 13),
        (0, 4, 6, 8, 12, 14), (0, 3, 8, 11, 12)],
    6: [  # funk
        (0, 3, 6, 7, 10, 12, 13), (0, 2, 5, 6, 8, 11, 14), (0, 2, 3, 6, 7, 10, 11, 14, 15),
        (0, 1, 4, 6, 7, 9, 12, 14), (0, 3, 6, 8, 10, 13), (0, 2, 5, 8, 10, 13, 15),
        (0, 1, 4, 7, 8, 11, 14), (0, 3, 5, 6, 9, 11, 12, 15), (0, 3, 4, 7, 10, 11, 14),
        (0, 4, 6, 8, 12, 14, 15), (0, 2, 3, 5, 7, 8, 11, 13, 14), (0, 1, 3, 6, 8, 9, 11, 14),
        (0, 4, 5, 8, 11, 12, 14), (0, 3, 4, 6, 9, 11, 13), (0, 2, 5, 6, 9, 11, 13),
        (0, 2, 4, 6, 7, 10, 12, 14), (0, 3, 5, 8, 10, 11, 13)],
    7: [  # hip-hop
        (0, 6, 8, 11, 14), (0, 3, 6, 8, 12, 14), (0, 3, 6, 9, 10, 13), (0, 6, 8, 14, 15),
        (0, 3, 6, 8, 10, 11, 12, 14), (0, 4, 6, 8, 11, 14), (0, 4, 7, 8, 12, 14),
        (0, 2, 6, 8, 10, 14), (0, 3, 8, 11, 12, 14), (0, 2, 6, 9, 12, 14),
        (0, 2, 3, 8, 11, 12, 15), (0, 3, 6, 8, 10, 12, 13), (0, 2, 5, 7, 9, 12, 14),
        (0, 4, 6, 9, 12, 14), (0, 3, 6, 8, 10, 12, 15)],
    8: [  # dance / electronic
        (0, 4, 8, 10, 12, 14), (0, 4, 8, 11, 12), (0, 5, 10, 12), (0, 4, 7, 10),
        (0, 3, 6, 10, 12, 14), (0, 8, 10, 12), (0, 2, 5, 7, 10, 13), (0, 4, 8, 12, 14),
        (0, 3, 6, 9, 12), (0, 2, 4, 7, 9, 12, 14), (0, 3, 7, 10, 12, 14),
        (0, 4, 6, 7, 10, 12), (0, 3, 6, 7, 10, 12, 14), (0, 3, 6, 8, 11, 12),
        (0, 3, 6, 8, 11, 12, 14), (0, 3, 5, 8, 11, 13), (0, 3, 4, 6, 7, 10, 11, 13),
        (0, 2, 4, 7, 8, 10, 12, 14)],
}


def _pack_tv(timing, vel, sign=0):
    return ((timing & 0x7F) | ((vel & 0x7F) << 7) | ((sign & 1) << 14)
            | (((timing >> 7) & 1) << 15))


def _pack_no(note, octave):
    return (note & 0x0F) | ((octave & 0x0F) << 4)


def _fac_velocity(vshape, ramp, i, n):
    if vshape in (_VS_RISE, _VS_FALL):
        span = n // ramp if ramp else n
        span = max(span, 1)
        pos = i % span
        r = 80 * pos // (span - 1) if span > 1 else 80
        v = 30 + r if vshape == _VS_RISE else 110 - r
    else:
        v = 100
    return max(30, min(115, v))


def _preset(ptype, gate, timing, note_value, length, notes):
    return {"type": ptype, "note_count": len(notes), "length": length, "gate": gate,
            "timing": timing, "note_value": note_value, "notes": list(notes), "mode": 0}


def factory_arp_preset(pid):
    """Factory rhythm arpeggio `pid` (0-118) as a preset dict."""
    if not 0 <= pid < ARP_FACTORY:
        return _preset(TYPE_ARP, 80, 0, _NV_QUARTER, 16, [])
    cat = next(c for c, (off, n) in enumerate(_AFC) if off <= pid < off + n)
    k = pid - _AFC[cat][0]
    if cat in _GRIDS:
        notes = [(_pack_tv(p, 115 if p % 4 == 0 else 90), _pack_no(0, 0)) for p in _GRIDS[cat][k]]
        return _preset(TYPE_ARP, 60, 0, _NV_SIXTEENTH, 16, notes)
    if cat == _AFC_CHORD:
        t, vs = min(k // 3, 5), k % 3
        tones = _CH_TONES[t]
        cc = len(tones)
        order = _CH_ORDER[cc][vs]
        n = cc * 2
        vshape = (_VS_FLAT, _VS_RISE, _VS_FALL)[vs]
        notes = []
        for i in range(n):
            octv, pos = i // cc, i % cc
            tone = tones[order[(pos + octv) % cc]]
            notes.append((_pack_tv(i, _fac_velocity(vshape, 1, i, n)), _pack_no(tone, octv)))
        return _preset(TYPE_ARP, 80, 0, _NV_SIXTEENTH, n, notes)
    vshape, ramp = _VS_FLAT, 1
    if cat in (_AFC_ASC, _AFC_DESC):
        ramp = (1, 2, 4)[k if k < 3 else 0]
        vshape = _VS_RISE if cat == _AFC_ASC else _VS_FALL
    n = 16
    notes = [(_pack_tv(i, _fac_velocity(vshape, ramp, i, n)), _pack_no(0, 0)) for i in range(n)]
    return _preset(TYPE_ARP, 60, 0, _NV_EIGHTH, n, notes)


def factory_seq_preset(fid):
    """Factory step-sequencer preset `fid` (0-47) as a preset dict."""
    def seq(gate, vel, notes, octaves):
        ns = [(_pack_tv(i, vel), _pack_no(nt, oc)) for i, (nt, oc) in enumerate(zip(notes, octaves))]
        return _preset(TYPE_SEQ, gate, 0, _NV_QUARTER, len(ns), ns)
    if fid == 0:   # C major scale
        return seq(80, 100, (0, 2, 4, 5, 7, 9, 11, 0), (4, 4, 4, 4, 4, 4, 4, 5))
    if fid == 1:   # bass line
        return seq(70, 110, (0, 0, 7, 0), (2, 2, 2, 3))
    if fid == 2:   # kick
        return seq(50, 127, (0, 0, 0, 0), (1, 1, 1, 1))
    if fid == 3:   # melody
        return seq(75, 90, (4, 7, 9, 7, 4, 2, 0, 2), (4,) * 8)
    return _preset(TYPE_SEQ, 80, 0, _NV_QUARTER, 16, [])


# ---- velocity (articulation) presets -------------------------------------------
VEL_PRESET_COUNT = 50


def _zone_default(points=((0, 0), (85, 85), (170, 170), (255, 255))):
    z = bytearray()
    for x, y in points:
        z += bytes([x, y])
    z += bytes([1, 127]) + struct.pack("<HH", 200, 20) + bytes([0, 255, 50])
    z += struct.pack("<H", 10) + bytes([0, 20, 1, 0])
    return bytes(z)          # 23 bytes on the wire


def _vel_preset_default(slot):
    name = b"User 1" if slot == 0 else b""
    return {"name": name.ljust(16, b"\x00"), "zone": _zone_default()}


# ---- MIDI delay ----------------------------------------------------------------
DELAY_FACTORY = 48
DELAY_USER = 50


def _delay_cfg(rate_mode=0, note_value=3, timing=0, feedback=50, fixed_ms=500, repeats=3,
               channel=0, transpose=0, t_mode=0, max_active=0, ch_count=1):
    return bytearray(struct.pack("<BBBBHBBbBBBBBBB", rate_mode, note_value, timing, feedback,
                                 fixed_ms, repeats, channel, transpose, t_mode, max_active,
                                 ch_count, 0, 0, 0, 0))


def _delay_factory():
    out = []
    for rate in range(5):
        for timing in (0, 2, 1):
            for fb in (40, 55, 72):
                out.append(bytes(_delay_cfg(note_value=rate, timing=timing, feedback=fb, repeats=0)))
    for rate in (2, 3, 4):   # pitch delays: +12 cumulative, 2 repeats
        out.append(bytes(_delay_cfg(note_value=rate, feedback=75, repeats=2, transpose=12, t_mode=1)))
    return out


_DELAY_FACTORY = _delay_factory()

# ---- drums -----------------------------------------------------------------------
_DRUM_NOTES = [36, 38, 42, 46, 39, 37, 56, 51, 45, 47, 50, 54]
_DRUM_VELS = [100] * 12
_DRUM_CHANNEL = 9
_DRUM_EXTRAS = [49, 57, 55, 52, 53, 44, 40, 48, 41, 43, 60, 61, 70, 58, 75, 81]

DAW_COUNT = 9
LCD_THEME_COUNT = 4
CHANNEL_ARTIC_MAX = 98
_IMAGE_SIZE = 65536
_CLONE_CHUNK = 22


def _s8(b):
    return b - 256 if b > 127 else b


class MusicMixin:

    def _init_music(self):
        self.mus_kb = copy.deepcopy(_KB_DEFAULTS)
        self.mus_slots = [copy.deepcopy(_KB_DEFAULTS) for _ in range(5)]
        self.mus_pending_slot = 255
        self._mus_reset_loop_config()
        self.mus_loop_data = {}          # loop number -> stored transfer stream
        self.mus_loop_rx = None
        self.mus_arp_user = {}           # preset id -> preset dict
        self.mus_seq_user = {}
        self.mus_edit = None             # preset being edited
        self.mus_edit_id = 255
        self.mus_edit_mode = 0
        self.mus_arp_state = {"active": 0, "sync": 1, "latch": 0, "mode": 0, "preset": 0}
        self.vel_presets = [_vel_preset_default(i) for i in range(VEL_PRESET_COUNT)]
        self.mus_delay_user = [bytes(_delay_cfg()) for _ in range(DELAY_USER)]
        self.mus_drum_notes = list(_DRUM_NOTES)
        self.mus_drum_vels = list(_DRUM_VELS)
        self.mus_drum_channel = _DRUM_CHANNEL
        self.mus_drum_extras = list(_DRUM_EXTRAS)
        self.mus_mc = [[i, 0xFF, 0xFF, 0xFF] for i in range(16)]
        self.mus_nav_layer = 0
        self.mus_daw = [0, 0]
        self.mus_lcd_theme = 0
        self.mus_chartic = {"enabled": 0, "map": [0xFF] * 16, "cc": 1}
        self.mus_macro_modes = bytearray(96)
        self.mus_macro_sync = 0

    # ---- helpers -----------------------------------------------------------------

    @staticmethod
    def _mus_reply(cmd, macro_num=0, status=0, data=b""):
        r = bytearray(_MSG)
        r[0:3] = _HDR
        r[3], r[4], r[5] = cmd, macro_num & 0xFF, status
        data = bytes(data)[:_MSG - 6]
        r[6:6 + len(data)] = data
        return r

    @staticmethod
    def _mus_head(cmd):
        r = bytearray(_MSG)
        r[0:3] = _HDR
        r[3] = cmd
        return r

    def _mus_reset_loop_config(self):
        self.mus_loop = {name: [_CC_NONE] * _LOOPS for name in _LOOP_ARRAYS}
        self.mus_loop.update({"channel": 16, "sync": 0, "alt_restart": 0,
                              "nav_master": 0, "nav_master_cc": _CC_NONE,
                              "nav": [_CC_NONE] * 8})

    # ---- dispatch ------------------------------------------------------------------

    def _custom_music(self, cmd, msg):
        if 0xA0 <= cmd <= 0xA9 or 0xB0 <= cmd <= 0xBB:
            return self._mus_macro_family(cmd, msg)
        if (0xC0 <= cmd <= 0xCC) or cmd == 0xCE:
            return self._mus_arp(cmd, msg)
        handler = {
            0x92: self._mus_active_layer, 0x93: self._mus_fw_version,
            0x94: self._mus_clone, 0x95: self._mus_macro_modes_get,
            0x96: self._mus_multichannel, 0x97: self._mus_nav_layer,
            0x99: self._mus_daw_cmd, 0xD4: self._mus_velocity_time,
            0xD6: self._mus_delay, 0xD7: self._mus_delay, 0xD8: self._mus_delay,
            0xD9: self._mus_vel_preset, 0xDA: self._mus_vel_preset, 0xDC: self._mus_vel_preset,
            0xE8: self._mus_param_single,
            0xE9: self._mus_drums, 0xEA: self._mus_drums, 0xEF: self._mus_drums,
            0xFE: self._mus_lcd_theme, 0xFF: self._mus_channel_artic,
        }.get(cmd)
        return handler(cmd, msg) if handler else None

    # ---- MIDI settings, slots, loop CCs, loop transfers ---------------------------

    def _mus_macro_family(self, cmd, msg):
        num = msg[4]
        d = msg[6:]
        valid = 1 <= num <= _LOOPS
        if cmd != 0xBB:
            self.mus_pending_slot = 255
        R = self._mus_reply
        if cmd == 0xB0:
            if 1 <= d[0] <= 16:
                self.mus_loop["channel"] = d[0]
            self.mus_loop["sync"] = int(d[1] != 0)
            self.mus_loop["alt_restart"] = int(d[2] != 0)
            self.mus_loop["restart"] = list(d[3:11])
            return R(cmd, num)
        if cmd in (0xB1, 0xB2):
            names = (("start_rec", "stop_rec", "start_play", "stop_play", "clear") if cmd == 0xB1 else
                     ("od_start_rec", "od_stop_rec", "od_start_play", "od_stop_play", "od_clear",
                      "od_restart"))
            off = num * 4
            for i in range(4):
                if off + i < _LOOPS:
                    for j, name in enumerate(names):
                        self.mus_loop[name][off + i] = d[j * 4 + i]
            return R(cmd, num)
        if cmd == 0xB3:
            self.mus_loop["nav_master"] = int(d[0] != 0)
            self.mus_loop["nav_master_cc"] = d[1]
            self.mus_loop["nav"] = list(d[2:10])
            return R(cmd, num)
        if cmd == 0xB4:
            return self._mus_loop_config_reports(num)
        if cmd == 0xB5:
            self._mus_reset_loop_config()
            return R(cmd, num)
        if cmd == 0xA7:
            self.mus_loop_data.clear()
            return R(cmd, 0)
        if cmd == 0xB6:
            self._mus_apply_basic(d)
            return R(cmd, 0)
        if cmd == 0xB7:
            return self._mus_kb_reports(self.mus_kb)
        if cmd == 0xB8:
            self._mus_reset_kb()
            return R(cmd, 0)
        if cmd == 0xB9:
            slot = d[0]
            if slot > 4:
                return R(cmd, 0, 1)
            self._mus_apply_basic(d[1:])
            self.mus_slots[slot] = copy.deepcopy(self.mus_kb)
            self.mus_pending_slot = slot
            return R(cmd, 0)
        if cmd == 0xBA:
            slot = d[0]
            if slot > 4:
                return R(cmd, 0, 1)
            self.mus_kb = copy.deepcopy(self.mus_slots[slot])
            return self._mus_kb_reports(self.mus_kb) + [R(cmd, 0)]
        if cmd == 0xBB:
            self._mus_apply_advanced(d)
            if self.mus_pending_slot != 255:
                self.mus_slots[self.mus_pending_slot] = copy.deepcopy(self.mus_kb)
                self.mus_pending_slot = 255
            else:
                self.mus_slots[0] = copy.deepcopy(self.mus_kb)
            return R(cmd, 0)
        if cmd == 0xA8:
            if not valid:
                return R(cmd, num, 1)
            return self._mus_loop_save(num)
        if cmd in (0xA3, 0xA6):
            if not valid:
                return R(cmd, num, 1)
            self.mus_loop_rx = {"num": num, "total": d[0] | (d[1] << 8), "count": 0,
                                "data": bytearray(), "overdub": cmd == 0xA6}
            return R(cmd, num)
        if cmd == 0xA4:
            rx = self.mus_loop_rx
            if rx is not None:
                n = d[2] | (d[3] << 8)
                if 0 < n <= _LOOP_CHUNK:
                    rx["data"] += d[4:4 + n]
                    rx["count"] += 1
            return None                   # no reply to a chunk
        if cmd == 0xA5:
            rx, self.mus_loop_rx = self.mus_loop_rx, None
            if rx is None or rx["count"] != rx["total"] or not rx["data"]:
                return R(cmd, num, 1)
            if not rx["overdub"]:
                self.mus_loop_data[rx["num"]] = bytes(rx["data"])
            return R(cmd, num)
        return R(cmd, num, 1)

    def _mus_loop_config_reports(self, num):
        lp, R = self.mus_loop, self._mus_reply
        out = [R(0xB0, num, 0, [lp["channel"], lp["sync"], lp["alt_restart"]] + lp["restart"])]
        for bank in range(2):
            p = []
            for name in ("start_rec", "stop_rec", "start_play", "stop_play", "clear"):
                p += lp[name][bank * 4:bank * 4 + 4]
            out.append(R(0xB1, bank, 0, p))
        for bank in range(2):
            p = []
            for name in ("od_start_rec", "od_stop_rec", "od_start_play", "od_stop_play",
                         "od_clear", "od_restart"):
                p += lp[name][bank * 4:bank * 4 + 4]
            out.append(R(0xB2, bank, 0, p))
        out.append(R(0xB3, num, 0, [lp["nav_master"], lp["nav_master_cc"]] + lp["nav"]))
        return out

    def _mus_loop_save(self, num):
        data = self.mus_loop_data.get(num)
        R = self._mus_reply
        if not data:
            return R(0xA0, num, 1)
        data = bytearray(data)
        if len(data) >= 4 and data[0] == 0xAA and data[1] == 0x55:
            data[3] = num
        pkts = (len(data) + _LOOP_CHUNK - 1) // _LOOP_CHUNK
        out = [R(0xA0, num, 0, struct.pack("<HH", pkts, len(data)))]
        for p in range(pkts):
            chunk = data[p * _LOOP_CHUNK:(p + 1) * _LOOP_CHUNK]
            out.append(R(0xA1, num, 0, struct.pack("<HH", p, len(chunk)) + bytes(chunk)))
        out.append(R(0xA2, num))
        return out

    def _mus_kb_reports(self, kb):
        t = kb["transpose"]
        p1 = struct.pack("<iiBbbbbbbBiBBBBBB", kb["velocity_sensitivity"], kb["cc_sensitivity"],
                         kb["channel_number"], t[0], 0, t[1], 0, t[2], 0, kb["dynamic_range"],
                         kb["oledkeyboard"], 0x80 | (kb["loop_stop_mode"] & 0x7F),
                         kb["smartchordlightmode"], kb["chord_display_mode"], kb["base_sustain"],
                         kb["keysplit_sustain"], kb["triplesplit_sustain"])
        p2 = [kb[k] for k in (
            "keysplitchannel", "keysplit2channel", "keysplitstatus", "keysplittransposestatus",
            "keysplitvelocitystatus", "custom_layer_animations_enabled", "unsynced_mode_active",
            "sample_mode_active", "instant_loop_start", "colorblindmode", "cclooprecording",
            "truesustain", "channeloverride", "velocityoverride", "transposeoverride",
            "midi_in_mode", "usb_midi_mode", "midi_clock_source", "macro_override_live_notes",
            "smartchord_mode", "base_smartchord_ignore", "keysplit_smartchord_ignore",
            "triplesplit_smartchord_ignore")] + list(kb["he_velocity_curve"])
        return [self._mus_reply(0xB7, 0, 0, p1), self._mus_reply(0xBB, 0, 0, bytes(p2))]

    def _mus_apply_basic(self, d):
        kb = self.mus_kb
        kb["velocity_sensitivity"], kb["cc_sensitivity"] = struct.unpack_from("<ii", bytes(d), 0)
        kb["channel_number"] = d[8]
        kb["transpose"] = [max(-64, min(64, _s8(d[i]))) for i in (9, 11, 13)]
        kb["dynamic_range"] = d[15]
        kb["oledkeyboard"] = struct.unpack_from("<i", bytes(d), 16)[0]
        if d[20] & 0x80:
            kb["loop_stop_mode"] = d[20] & 0x7F
        kb["smartchordlightmode"] = d[21]

    def _mus_apply_advanced(self, d):
        kb = self.mus_kb
        kb["keysplitchannel"], kb["keysplit2channel"] = d[0] & 0x0F, d[1] & 0x0F
        for i, k in enumerate(("keysplitstatus", "keysplittransposestatus", "keysplitvelocitystatus")):
            kb[k] = d[2 + i] if d[2 + i] <= 3 else 0
        kb["custom_layer_animations_enabled"] = int(d[5] != 0)
        kb["unsynced_mode_active"] = d[6] if d[6] <= 5 else 0
        kb["sample_mode_active"] = int(d[7] != 0)
        kb["instant_loop_start"] = int(d[8] != 0)
        kb["colorblindmode"] = d[9]
        kb["cclooprecording"] = d[10] if d[10] <= 3 else 0
        kb["truesustain"] = int(d[11] != 0)
        kb["channeloverride"], kb["velocityoverride"], kb["transposeoverride"] = (
            int(d[12] != 0), int(d[13] != 0), int(d[14] != 0))
        kb["midi_in_mode"] = d[15] if d[15] <= 3 else 0
        kb["usb_midi_mode"] = d[16] if d[16] <= 3 else 0
        kb["midi_clock_source"] = d[17] if d[17] <= 2 else 0
        kb["macro_override_live_notes"] = int(d[18] != 0)
        kb["smartchord_mode"] = 1
        kb["base_smartchord_ignore"], kb["keysplit_smartchord_ignore"], \
            kb["triplesplit_smartchord_ignore"] = d[20], d[21], d[22]
        if d[23] < 3:
            kb["chord_display_mode"] = d[23]

    def _mus_reset_kb(self):
        kb = self.mus_kb
        keep = ("chord_display_mode", "base_sustain", "keysplit_sustain", "triplesplit_sustain",
                "he_velocity_curve", "he_velocity_min", "he_velocity_max", "min_press_time",
                "max_press_time", "lut_correction_strength", "aftertouch_mode", "aftertouch_cc",
                "vibrato_sensitivity", "vibrato_decay_time", "trigger_min", "velocity_as_at")
        fresh = copy.deepcopy(_KB_DEFAULTS)
        for k in keep:
            fresh[k] = kb[k]
        self.mus_kb = fresh
        self.mus_slots[0] = copy.deepcopy(fresh)

    def _mus_param_single(self, cmd, msg):
        pid, v8 = msg[6], msg[7]
        v16 = msg[7] | (msg[8] << 8)
        kb, ok = self.mus_kb, True
        simple = {0: "channel_number", 14: "aftertouch_mode", 15: "base_sustain",
                  16: "keysplit_sustain", 17: "triplesplit_sustain", 18: "keysplitchannel",
                  19: "keysplit2channel", 20: "keysplitstatus", 21: "keysplittransposestatus",
                  22: "keysplitvelocitystatus", 39: "aftertouch_cc", 40: "vibrato_sensitivity",
                  47: "base_smartchord_ignore", 48: "keysplit_smartchord_ignore",
                  49: "triplesplit_smartchord_ignore"}
        booleans = {33: "channeloverride", 34: "velocityoverride", 35: "transposeoverride",
                    45: "macro_override_live_notes", 50: "velocity_as_at"}
        if pid in simple:
            kb[simple[pid]] = v8
        elif pid in booleans:
            kb[booleans[pid]] = int(v8 != 0)
        elif pid in (1, 2, 3):
            kb["transpose"][pid - 1] = max(-64, min(64, _s8(v8)))
        elif 4 <= pid <= 12:
            zone, what = divmod(pid - 4, 3)
            kb[("he_velocity_curve", "he_velocity_min", "he_velocity_max")[what]][zone] = v8
        elif pid == 13 or pid == 54:
            pass
        elif pid == 32:
            kb["lut_correction_strength"] = min(v8, 100)
        elif pid in (36, 37):
            kb["midi_in_mode" if pid == 36 else "usb_midi_mode"] = v8 if v8 <= 3 else 0
        elif pid == 38:
            kb["midi_clock_source"] = v8 if v8 <= 2 else 0
        elif pid == 41:
            kb["vibrato_decay_time"] = v16
        elif pid in (42, 43):
            kb["min_press_time" if pid == 42 else "max_press_time"] = v16
        elif pid == 44:
            kb["trigger_min"] = max(1, min(35, v8))
            v8 = kb["trigger_min"]
        elif pid == 46:
            kb["smartchord_mode"] = 1
        elif pid == 51:
            self.mus_macro_sync = int(v8 != 0)
        elif pid == 52:
            mid, mode = v16 & 0xFF, (v16 >> 8) & 0x03
            idx, shift = mid // 4, (mid % 4) * 2
            if idx < 64:
                self.mus_macro_modes[idx] = (self.mus_macro_modes[idx] & ~(3 << shift) & 0xFF) | (mode << shift)
        elif pid == 53:
            mid, sync = v16 & 0xFF, (v16 >> 8) & 1
            idx, bit = 64 + mid // 8, mid % 8
            if idx < 96:
                if sync:
                    self.mus_macro_modes[idx] |= 1 << bit
                else:
                    self.mus_macro_modes[idx] &= ~(1 << bit) & 0xFF
        elif pid == 55:
            kb["chord_display_mode"] = min(v8, 2)
            v8 = kb["chord_display_mode"]
        else:
            ok = False
        r = self._mus_head(cmd)
        r[5], r[6], r[7] = int(ok), pid, v8
        return r

    def _mus_velocity_time(self, cmd, msg):
        kb, sub = self.mus_kb, msg[6]
        r = self._mus_head(cmd)
        if sub == 1:
            mn, mx = msg[7] | (msg[8] << 8), msg[9] | (msg[10] << 8)
            if 50 <= mn <= 500 and 1 <= mx <= 100 and mx < mn:
                kb["min_press_time"], kb["max_press_time"] = mn, mx
                r[4] = 1
        elif sub in (0, 2):
            r[4] = 1
        else:
            return r
        struct.pack_into("<HH", r, 5, kb["min_press_time"], kb["max_press_time"])
        return r

    # ---- arpeggiator / step sequencer ----------------------------------------------

    @staticmethod
    def _mus_ptype(sel, pid):
        if sel == 1:
            return "arp" if pid < ARP_MAX else None
        if sel == 2:
            return "seq" if SEQ_FACTORY_BASE <= pid < SEQ_MAX else None
        if pid < ARP_MAX:
            return "arp"
        if SEQ_FACTORY_BASE <= pid < SEQ_MAX:
            return "seq"
        return None

    def _mus_load_preset(self, kind, pid):
        """Stored preset (copy) or None when a user slot is empty."""
        if kind == "arp":
            if pid < ARP_USER_START:
                return factory_arp_preset(pid)
            p = self.mus_arp_user.get(pid)
        else:
            if pid < SEQ_USER_START:
                return factory_seq_preset(pid - SEQ_FACTORY_BASE)
            p = self.mus_seq_user.get(pid)
        return copy.deepcopy(p) if p and p["note_count"] > 0 else None

    def _mus_used_notes(self):
        return sum(p["note_count"] for p in list(self.mus_arp_user.values()) + list(self.mus_seq_user.values()))

    def _mus_arp(self, cmd, msg):
        r = bytearray(msg)
        p = r                       # parameters start at byte 4
        o = 4
        if cmd == 0xC9:
            free = max(0, POOL_MAX_NOTES - self._mus_used_notes())
            vals = [0, ARP_FACTORY, 40, SEQ_FACTORY, 40, PRESET_NOTES_MAX, PRESET_NOTES_MAX]
            r[o:o + 7] = bytes(vals)
            struct.pack_into("<HH", r, o + 7, free, POOL_MAX_NOTES)
            r[o + 11] = sum(1 for x in self.mus_arp_user.values() if x["note_count"] > 0)
            r[o + 12] = sum(1 for x in self.mus_seq_user.values() if x["note_count"] > 0)
        elif cmd == 0xC7:
            s = self.mus_arp_state
            r[o:o + 6] = bytes([0, s["active"], s["sync"], s["latch"], s["mode"], s["preset"]])
        elif cmd == 0xC8:
            s = self.mus_arp_state
            s["active"] = int(p[o] != 0)
            if p[o]:
                s["preset"] = p[o + 4]
            s["sync"], s["latch"] = int(p[o + 1] != 0), int(p[o + 2] != 0)
            if p[o + 3] < ARP_MODES:
                s["mode"] = p[o + 3]
            r[o] = 0
        elif cmd == 0xCC:
            if p[o] < ARP_MODES:
                self.mus_arp_state["mode"] = p[o]
                r[o] = 0
            else:
                r[o] = 1
        elif cmd == 0xC0:
            pid = p[o]
            kind = self._mus_ptype(p[o + 1], pid)
            pre = self._mus_load_preset(kind, pid) if kind else None
            if pre is None:
                r[o] = 1
                return r
            self.mus_edit, self.mus_edit_id = pre, pid
            mode = pre["mode"] if kind == "arp" and pid >= ARP_USER_START else 0
            self.mus_edit_mode = mode
            r[o:o + 9] = bytes([0, pre["type"], pre["note_count"] & 0xFF, (pre["length"] >> 8) & 0xFF,
                                pre["length"] & 0xFF, pre["gate"], pre["timing"], pre["note_value"], mode])
        elif cmd == 0xC1:
            pid, ptype = p[o], p[o + 1]
            is_arp = ptype == TYPE_ARP and ARP_USER_START <= pid < ARP_MAX
            is_seq = ptype == TYPE_SEQ and SEQ_USER_START <= pid < SEQ_MAX
            if not (is_arp or is_seq):
                r[o] = 1
                return r
            if self.mus_edit_id != pid or self.mus_edit is None:
                store = self.mus_arp_user if is_arp else self.mus_seq_user
                self.mus_edit = copy.deepcopy(store.get(pid)) or _preset(ptype, 0, 0, 0, 0, [])
                self.mus_edit_id = pid
            e = self.mus_edit
            e["type"], e["note_count"] = ptype, p[o + 2]
            e["length"] = (p[o + 3] << 8) | p[o + 4]
            e["gate"], e["timing"], e["note_value"] = p[o + 5], p[o + 6], p[o + 7]
            self.mus_edit_mode = p[o + 8]
            r[o] = 0 if (e["gate"] <= 100 and 1 <= e["length"] <= 127) else 1
        elif cmd in (0xCA, 0xCB):
            pid = p[o]
            e = self.mus_edit
            if e is None or self.mus_edit_id != pid:
                r[o] = 1
                return r
            user_start = ARP_USER_START if e["type"] == TYPE_ARP else SEQ_USER_START
            start = p[o + 1]
            count = 1 if cmd == 0xCA else p[o + 2]
            base = o + 2 if cmd == 0xCA else o + 3
            if (pid < user_start or start >= PRESET_NOTES_MAX or count == 0 or count > 8
                    or start + count > PRESET_NOTES_MAX):
                r[o] = 1
                return r
            notes = e["notes"]
            while len(notes) < start + count:
                notes.append((0, 0))
            for i in range(count):
                b = base + i * 3
                notes[start + i] = (p[b] | (p[b + 1] << 8), p[b + 2])
            r[o] = 0
            if cmd == 0xCB:
                r[o + 1] = count
        elif cmd == 0xCE:
            e = self.mus_edit
            start, count = p[o], min(p[o + 1], 8)
            if e is None or start >= PRESET_NOTES_MAX:
                r[o] = 1
                return r
            count = min(count, PRESET_NOTES_MAX - start)
            r[o], r[o + 1] = 0, count
            for i in range(count):
                pk, no = e["notes"][start + i] if start + i < len(e["notes"]) else (0, 0)
                struct.pack_into("<HB", r, o + 2 + i * 3, pk, no)
        elif cmd == 0xC2:
            pid, e = p[o], self.mus_edit
            ok = False
            if e is not None and self.mus_edit_id == pid:
                if e["type"] == TYPE_ARP and ARP_USER_START <= pid < ARP_MAX:
                    store = self.mus_arp_user
                elif e["type"] == TYPE_SEQ and SEQ_USER_START <= pid < SEQ_MAX:
                    store = self.mus_seq_user
                else:
                    store = None
                if store is not None and e["gate"] <= 100 and 1 <= e["length"] <= 127:
                    saved = copy.deepcopy(e)
                    saved["notes"] = (saved["notes"] + [(0, 0)] * saved["note_count"])[:saved["note_count"]]
                    saved["mode"] = self.mus_edit_mode if self.mus_edit_mode < ARP_MODES else 0
                    store[pid] = saved
                    ok = True
            r[o] = 0 if ok else 1
        elif cmd == 0xC3:
            pid = p[o]
            kind = self._mus_ptype(p[o + 2], pid)
            ok = kind is not None and self._mus_load_preset(kind, pid) is not None
            if ok and kind == "arp":
                self.mus_arp_state["preset"] = pid
            r[o] = 0 if ok else 1
        elif cmd == 0xC4:
            pid = p[o]
            kind = self._mus_ptype(p[o + 1], pid)
            ok = False
            if kind == "arp" and pid >= ARP_USER_START:
                self.mus_arp_user.pop(pid, None)
                ok = True
            elif kind == "seq" and pid >= SEQ_USER_START:
                self.mus_seq_user.pop(pid, None)
                ok = True
            r[o] = 0 if ok else 1
        elif cmd == 0xC5:
            src, dst = p[o], p[o + 1]
            kind = self._mus_ptype(p[o + 2], dst)
            ok = False
            if kind == "arp" and dst >= ARP_USER_START:
                pre = self._mus_load_preset("arp", src) if src < ARP_MAX else None
                if pre:
                    self.mus_arp_user[dst] = pre
                    ok = True
            elif kind == "seq" and dst >= SEQ_USER_START:
                pre = self._mus_load_preset("seq", src) if SEQ_FACTORY_BASE <= src < SEQ_MAX else None
                if pre:
                    self.mus_seq_user[dst] = pre
                    ok = True
            r[o] = 0 if ok else 1
        elif cmd == 0xC6:
            if p[o] in (0, 2):
                self.mus_arp_user.clear()
            if p[o] in (1, 2):
                self.mus_seq_user.clear()
            r[o] = 0
        else:
            r[o] = 0xFF
        return r

    # ---- velocity (articulation) presets -------------------------------------------

    def _mus_vel_preset(self, cmd, msg):
        r = self._mus_head(cmd)
        slot = msg[6]
        if cmd == 0xDC:
            self.vel_presets = [_vel_preset_default(i) for i in range(VEL_PRESET_COUNT)]
            r[5] = 1
            return r
        if slot >= VEL_PRESET_COUNT:
            return r
        pre = self.vel_presets[slot]
        if cmd == 0xD9:
            chunk = msg[7]
            if chunk == 0:
                name = bytearray(msg[8:24])
                name[15] = 0
                pre["name"] = bytes(name)
                r[5] = 1
            elif chunk == 1:
                pre["zone"] = bytes(msg[8:31])
                r[5] = 1
            return r
        c0 = self._mus_head(0xDA)
        c0[5], c0[6], c0[7] = 1, slot, 0
        c0[8:24] = pre["name"]
        c1 = self._mus_head(0xDA)
        c1[5], c1[6], c1[7] = 1, slot, 1
        c1[8:31] = pre["zone"]
        return [c0, c1]

    # ---- MIDI delay ---------------------------------------------------------------

    def _mus_delay_cfg(self, slot):
        if slot < DELAY_FACTORY:
            return _DELAY_FACTORY[slot]
        if slot < DELAY_FACTORY + DELAY_USER:
            return self.mus_delay_user[slot - DELAY_FACTORY]
        return None

    def _mus_delay(self, cmd, msg):
        r = self._mus_head(cmd)
        slot = msg[6]
        if cmd == 0xD6:
            cfg = self._mus_delay_cfg(slot)
            if cfg is not None:
                r[4] = 1
                r[5:21] = cfg
            return r
        if cmd == 0xD7:
            if DELAY_FACTORY <= slot < DELAY_FACTORY + DELAY_USER:
                c = bytearray(msg[7:23])
                rate, nv, tm, fb, ms, rep, ch, tr, tmode, act, cnt, c2, c3, c4, _ = struct.unpack(
                    "<BBBBHBBbBBBBBBB", bytes(c))
                c = _delay_cfg(rate if rate <= 1 else 0, nv if nv <= 4 else 2, tm if tm <= 2 else 0,
                               fb if fb <= 100 else 50, max(10, min(5000, ms)), rep,
                               ch if ch <= 16 else 0, max(-48, min(48, tr)), tmode if tmode <= 1 else 0,
                               act if act <= 12 else 0, cnt if 1 <= cnt <= 4 else 1)
                c[12], c[13], c[14] = (x if x <= 16 else 0 for x in (c2, c3, c4))
                self.mus_delay_user[slot - DELAY_FACTORY] = bytes(c)
            r[4] = 1
            return r
        # Bulk read: one report per slot on the keyboard. Only the first is
        # returned here, matching how many the app's reader consumes.
        start, count = msg[6], msg[7]
        end = min(start + count, DELAY_FACTORY + DELAY_USER)
        out = []
        for s in range(start, end):
            rr = self._mus_head(0xD8)
            rr[4], rr[5], rr[6] = 1, s, 1 if s < DELAY_FACTORY else 0
            rr[7:23] = self._mus_delay_cfg(s)
            out.append(rr)
            break
        return out[0] if out else None

    # ---- drums ------------------------------------------------------------------------

    def _mus_drums(self, cmd, msg):
        mode = msg[4]
        if cmd == 0xEA:
            if mode == 1:
                self.mus_drum_channel = msg[6] if msg[6] <= 15 else 9
            elif mode == 2:
                self.mus_drum_extras = [b if b <= 127 else _DRUM_EXTRAS[i]
                                        for i, b in enumerate(msg[6:22])]
            else:
                self.mus_drum_notes = [b & 0x7F for b in msg[6:18]]
                self.mus_drum_vels = [b & 0x7F for b in msg[18:30]]
        elif cmd == 0xEF:
            self.mus_drum_notes = list(_DRUM_NOTES)
            self.mus_drum_vels = list(_DRUM_VELS)
            self.mus_drum_channel = _DRUM_CHANNEL
            self.mus_drum_extras = list(_DRUM_EXTRAS)
        r = self._mus_head(cmd)
        r[4] = 1
        if mode == 2:
            r[6:22] = bytes(self.mus_drum_extras)
        else:
            r[6:18] = bytes(self.mus_drum_notes)
            r[18:30] = bytes(self.mus_drum_vels)
            r[30] = self.mus_drum_channel
        return r

    # ---- small settings ---------------------------------------------------------------

    def _mus_active_layer(self, cmd, msg):
        r = self._mus_head(cmd)
        r[4], r[5] = 1, 0
        return r

    def _mus_fw(self):
        try:
            from protocol import virtual_midiswitch as vm
            return tuple(vm.FIRMWARE_VERSION), vm.LAYOUT_VERSION
        except Exception:
            return (1, 0, 0), 9

    def _mus_fw_version(self, cmd, msg):
        r = self._mus_head(cmd)
        r[4] = 1
        r[5:8] = bytes(self._mus_fw()[0])
        return r

    def _mus_clone(self, cmd, msg):
        r = self._mus_head(cmd)
        sub = msg[4]
        if sub == 0:
            fw, layout = self._mus_fw()
            r[4] = 1
            struct.pack_into("<HIB", r, 5, layout, _IMAGE_SIZE, _CLONE_CHUNK)
            r[12:15] = bytes(fw)
        elif sub in (1, 2):
            addr, n = msg[6] | (msg[7] << 8), msg[8]
            if 0 < n <= _CLONE_CHUNK and addr + n <= _IMAGE_SIZE:
                r[4], r[5], r[6] = 1, msg[6], msg[7]
                if sub == 1:
                    r[7] = n          # settings image is not modelled: reads as zeros
        elif sub == 3:
            r[4] = 1
        return r

    def _mus_macro_modes_get(self, cmd, msg):
        r = self._mus_head(cmd)
        chunk = msg[4]
        if chunk < 4:
            r[4], r[5] = 1, chunk
            r[6:30] = self.mus_macro_modes[chunk * 24:chunk * 24 + 24]
            if chunk == 3:
                r[30] = self.mus_macro_sync
        return r

    def _mus_multichannel(self, cmd, msg):
        r = self._mus_head(cmd)
        sub, preset = msg[4], msg[6]
        if preset >= 16 or sub > 1:
            return r
        cfg = self.mus_mc[preset]
        if sub == 1:
            cfg[0] = min(msg[7], 15)
            for e in range(3):
                ch, raw = msg[8 + e], msg[11 + e] & 0x07
                octv = raw - 8 if raw & 0x04 else raw
                octv = max(-3, min(3, octv))
                cfg[1 + e] = ((octv & 0x07) << 4) | ch if ch <= 15 else 0xFF
        r[4], r[5], r[6] = 1, preset, cfg[0]
        for e in range(3):
            b = cfg[1 + e]
            valid = b <= 0x7F and ((b >> 4) & 0x07) != 4
            r[7 + e] = (b & 0x0F) if valid else 0xFF
            r[11 + e] = ((b >> 4) & 0x07) if valid else 0
        r[10] = 0            # on/off state is not set over the wire; starts off
        return r

    def _mus_nav_layer(self, cmd, msg):
        r = self._mus_head(cmd)
        try:
            from protocol import virtual_midiswitch as vm
            layers = vm.LAYERS
        except Exception:
            layers = 12
        sub = msg[4]
        if sub > 1 or (sub == 1 and msg[6] >= layers):
            return r
        if sub == 1:
            self.mus_nav_layer = msg[6]
        r[4], r[5], r[6] = 1, self.mus_nav_layer, layers
        return r

    def _mus_daw_cmd(self, cmd, msg):
        r = self._mus_head(cmd)
        sub = msg[4]
        ok = sub <= 1
        if ok and sub == 1:
            idx, os_b = msg[6], msg[7]
            if idx < DAW_COUNT:
                self.mus_daw[0] = idx
                if os_b <= 1:
                    self.mus_daw[1] = os_b
                if idx in (2, 4):     # Mac-only DAWs
                    self.mus_daw[1] = 1
            else:
                ok = False
        r[4], r[5], r[6], r[7] = int(ok), self.mus_daw[0], self.mus_daw[1], DAW_COUNT
        return r

    def _mus_lcd_theme(self, cmd, msg):
        r = self._mus_head(cmd)
        if msg[4] == 1 and msg[6] < LCD_THEME_COUNT:
            self.mus_lcd_theme = msg[6]
        r[4], r[5], r[6] = 0, self.mus_lcd_theme, LCD_THEME_COUNT
        return r

    def _mus_channel_artic(self, cmd, msg):
        ca = self.mus_chartic
        if msg[4] == 1:
            ca["enabled"] = int(msg[6] != 0)
            ca["map"] = [b if b <= CHANNEL_ARTIC_MAX else 0xFF for b in msg[7:23]]
            if msg[23] & 0x80:
                ca["cc"] = msg[23] & 0x7F
        r = self._mus_head(cmd)
        r[4], r[5] = 0, ca["enabled"]
        r[6:22] = bytes(ca["map"])
        r[22] = 0x80 | ca["cc"]
        return r
