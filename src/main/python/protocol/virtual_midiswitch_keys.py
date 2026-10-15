# SPDX-License-Identifier: GPL-2.0-or-later
"""Key-level settings of the software MIDIswitch: per-key actuation, layer
actuation, gamepad settings and joystick bindings, toggle keys, dynamic
keystroke slots, null-bind (SOCD) groups and custom display names."""
import copy
import struct

_LEN = 32
_HDR = bytes([0x7D, 0x00, 0x4D])

# Per-key actuation (8 bytes per key, 70 analog keys, 12 layers).
PK_LAYERS = 12
PK_KEYS = 70
PK_KEYS_PER_PACKET = 3
PK_PACKETS = 24
# Factory: actuation 3.0 mm (191/255 of 4 mm), deadzones ~0.1 mm, Basic
# articulation, no flags, rapid trigger sensitivities ~0.1 mm, no offset.
PK_FACTORY = (191, 6, 6, 2, 0, 6, 6, 0)
PK_DEADZONE_MAX = 51
PK_CURVE_MAX = 98            # last valid articulation index
PK_CURVE_BASIC = 2
PK_FLAG_RAPID = 0x01

# Layer actuation (10 bytes per layer + global aftertouch fields).
LA_FACTORY = [30, 30, 2, 10, 0]      # normal, midi, velocity mode, speed scale, flags
AT_FACTORY = [0, 255, 50, 10, False]  # aftertouch mode, CC (255 = off), vibrato sens, decay, velocity-as-AT

# Gamepad
GAMING_FN_MAX = 24
GAMING_CONTROLS = 26
LINEAR_CURVE = [0, 0, 85, 85, 170, 170, 255, 255]

# Toggle keys
TOGGLE_SLOTS = 100
TOGGLE_EXTRA = 7
TOGGLE_ENTRY_SIZE = 22

# Dynamic keystroke slots
DKS_SLOTS = 50

# Null-bind groups
NB_GROUPS = 20
NB_KEYS = 8

# Custom names: category -> slot count
CN_COUNTS = [25, 100, 40, 40, 50, 12]
CN_NAME_LEN = 16

# Articulation preset names (bulk name list)
USER_PRESETS = 50


def _reply(cmd):
    r = bytearray(_LEN)
    r[0:3] = _HDR
    r[3] = cmd
    return r


def _factory_dks_slot():
    return {
        "press_kc": [0, 0, 0, 0], "press_act": [24, 48, 72, 96],
        "release_kc": [0, 0, 0, 0], "release_act": [96, 72, 48, 24],
        "behaviors": 0,
    }


def _factory_nb_group():
    return {"behavior": 0, "count": 0, "keys": [0xFF] * NB_KEYS, "layer": 0, "reserved": [0] * 7}


class KeysMixin:

    # ------------------------------------------------------------------ state

    def _init_keys(self):
        self.per_key = [[list(PK_FACTORY) for _ in range(PK_KEYS)] for _ in range(PK_LAYERS)]
        self.per_key_mode = [0, 0]           # mode enabled, per-layer enabled (factory: off)
        self.layer_act = [list(LA_FACTORY) for _ in range(PK_LAYERS)]
        self.at_globals = list(AT_FACTORY)

        self.gaming_mode = False
        self.gaming_analog = [10, 20, 10, 20, 10, 20]   # ls min/max, rs min/max, trigger min/max (0.1 mm)
        self.gaming_suppress = True
        self.gaming_keymap = [[0, 0, 0] for _ in range(GAMING_CONTROLS)]   # row, col, enabled
        self.gaming_curves = [list(LINEAR_CURVE) for _ in range(4)]
        self.gaming_response = [0, 0, 0, 0, PK_CURVE_BASIC]  # angle adj, angle, square, snappy, curve
        self.gaming_binds = {}               # (layer, index) -> function id

        self.toggle_pool = {}                # slot -> dict(kc, flags, num, multi)
        self.toggle_saved = {}

        self.dks = [_factory_dks_slot() for _ in range(DKS_SLOTS)]
        self.dks_saved = None

        self.nb_groups = [_factory_nb_group() for _ in range(NB_GROUPS)]
        self.nb_enabled = True
        self.nb_saved = (copy.deepcopy(self.nb_groups), True)

        self.cn_names = [[b""] * n for n in CN_COUNTS]

        self.preset_names = [b""] * USER_PRESETS
        self.preset_names[0] = b"User 1"

    # --------------------------------------------------------------- dispatch

    def _custom_keys(self, cmd, msg):
        if 0xE0 <= cmd <= 0xE6:
            return self._keys_per_key(cmd, msg)
        if 0xEB <= cmd <= 0xEE:
            return self._keys_layer_act(cmd, msg)
        if cmd in (0xBC, 0xBD, 0xCF, 0xD0, 0xD1, 0xD2, 0x90, 0x91, 0xDD, 0xDE):
            return self._keys_gaming(cmd, msg)
        if cmd == 0x9A:
            return self._keys_gaming_bind(msg)
        if 0xF0 <= cmd <= 0xF4:
            return self._keys_nullbind(cmd, msg)
        if 0xF5 <= cmd <= 0xFD:
            return self._keys_toggle(cmd, msg)
        if 0xAA <= cmd <= 0xAF:
            return self._keys_dks(cmd, msg)
        if cmd == 0xCD:
            return self._keys_names(msg)
        if cmd == 0xDB:
            return self._keys_preset_names()
        return None

    # -------------------------------------------------------- per-key actuation

    def _keys_per_key(self, cmd, msg):
        r = _reply(cmd)
        d = msg[6:]
        if cmd == 0xE0:
            layer, key = d[0], d[1]
            if layer < PK_LAYERS and key < PK_KEYS:
                act = d[2]
                if act == 0:
                    act = PK_FACTORY[0]
                elif act < 7:
                    act = 7
                flags = d[6]
                press = d[7]
                if (flags & PK_FLAG_RAPID) and press == 0:
                    press = PK_FACTORY[5]
                self.per_key[layer][key] = [
                    act, min(d[3], PK_DEADZONE_MAX), min(d[4], PK_DEADZONE_MAX),
                    d[5] if d[5] <= PK_CURVE_MAX else PK_CURVE_BASIC,
                    flags, press, d[8], d[9]]
            r[4] = 1
        elif cmd == 0xE1:
            layer, key = d[0], d[1]
            r[4] = 1
            if layer < PK_LAYERS and key < PK_KEYS:
                r[5:13] = bytes(self.per_key[layer][key])
        elif cmd == 0xE2:
            layer = d[0]
            if layer >= PK_LAYERS:
                return r
            out = []
            for pkt in range(PK_PACKETS):
                p = _reply(0xE2)
                p[4], p[5], p[6], p[7] = 1, layer, pkt, PK_PACKETS
                for k in range(PK_KEYS_PER_PACKET):
                    key = pkt * PK_KEYS_PER_PACKET + k
                    if key >= PK_KEYS:
                        break
                    off = 8 + k * 8
                    p[off:off + 8] = bytes(self.per_key[layer][key])
                out.append(p)
            return out
        elif cmd == 0xE3:
            self.per_key = [[list(PK_FACTORY) for _ in range(PK_KEYS)] for _ in range(PK_LAYERS)]
            r[4] = 1
        elif cmd == 0xE4:
            self.per_key_mode = [d[0], d[1]]
            r[4] = 1
        elif cmd == 0xE5:
            r[4] = 1
            r[5], r[6] = self.per_key_mode
        elif cmd == 0xE6:
            src, dst = d[0], d[1]
            if src < PK_LAYERS and dst < PK_LAYERS:
                self.per_key[dst] = [list(k) for k in self.per_key[src]]
            r[4] = 1
        return r

    # --------------------------------------------------------- layer actuation

    def _layer_record(self, layer):
        mode, cc, sens, decay, vel_at = self.at_globals
        return bytes(self.layer_act[layer]) + bytes([mode, cc, sens, decay & 0xFF, (decay >> 8) & 0xFF])

    def _keys_layer_act(self, cmd, msg):
        r = _reply(cmd)
        d = msg[6:]
        if cmd == 0xEB:
            layer = d[0]
            if layer < PK_LAYERS:
                r[4] = 1
                r[5] = 1
                r[6:16] = self._layer_record(layer)
                r[16] = 1 if self.at_globals[4] else 0
        elif cmd == 0xEC:
            layer = d[0]
            if layer < PK_LAYERS:
                self.layer_act[layer] = list(d[1:6])
            r[4] = 1
        elif cmd == 0xED:
            out = []
            for pkt in range(6):
                p = _reply(0xED)
                p[4], p[5], p[6] = 1, pkt, 6
                for n in range(2):
                    off = 7 + n * 10
                    p[off:off + 10] = self._layer_record(pkt * 2 + n)
                out.append(p)
            return out
        elif cmd == 0xEE:
            self.layer_act = [list(LA_FACTORY) for _ in range(PK_LAYERS)]
            r[4] = 1
        return r

    # ------------------------------------------------------------------ gaming

    def _keys_gaming(self, cmd, msg):
        r = _reply(cmd)
        d = msg[6:]
        if cmd == 0xBC:
            self.gaming_mode = d[0] != 0
            r[5] = 0
        elif cmd == 0xCF:
            if d[0] < GAMING_CONTROLS:
                self.gaming_keymap[d[0]] = [d[1], d[2], d[3]]
                r[5] = 0
            else:
                r[5] = 1
        elif cmd == 0xBD:
            if d[0] < GAMING_CONTROLS:
                row, col, en = self.gaming_keymap[d[0]]
                r[5], r[6], r[7], r[8], r[9] = 0, d[0], row, col, 1 if en else 0
            else:
                r[5] = 1
        elif cmd == 0xD0:
            self.gaming_analog = list(d[0:6])
            self.gaming_suppress = d[6] != 0
            r[5] = 0
        elif cmd == 0xD1:
            r[5] = 0
            r[6] = 1 if self.gaming_mode else 0
            r[7:13] = bytes(self.gaming_analog)
            r[13] = 1 if self.gaming_suppress else 0
        elif cmd == 0xD2:
            self.gaming_mode = False
            self.gaming_analog = [10, 20, 10, 20, 10, 20]
            self.gaming_suppress = True
            for m in self.gaming_keymap:
                m[2] = 0
            self.gaming_curves = [list(LINEAR_CURVE) for _ in range(4)]
            self.gaming_response = [0, 0, 0, 0, PK_CURVE_BASIC]
            r[5] = 0
        elif cmd == 0x90:
            if d[0] < 4:
                self.gaming_curves[d[0]] = list(d[1:9])
                r[5] = 1
        elif cmd == 0x91:
            if d[0] < 4:
                r[5] = 1
                r[6:14] = bytes(self.gaming_curves[d[0]])
        elif cmd == 0xDD:
            self.gaming_response = [1 if d[0] else 0, d[1], 1 if d[2] else 0, 1 if d[3] else 0, d[4]]
            r[5] = 1
        elif cmd == 0xDE:
            r[5] = 1
            r[6:11] = bytes(self.gaming_response)
        return r

    def _keys_gaming_bind(self, msg):
        r = _reply(0x9A)
        rows, cols = self._keys_matrix()
        total = rows * cols
        sub = msg[4]
        d = msg[6:]
        if sub == 0:
            layer, first = d[0], d[1]
            if layer < PK_LAYERS and first < total:
                count = min(24, total - first)
                for i in range(count):
                    r[8 + i] = self.gaming_binds.get((layer, first + i), 0)
                r[4], r[5], r[6], r[7] = 1, layer, first, count
        elif sub == 1:
            layer, row, col, fn = d[0], d[1], d[2], d[3]
            if layer < PK_LAYERS and row < rows and col < cols and fn <= GAMING_FN_MAX:
                idx = row * cols + col
                if fn:
                    self.gaming_binds[(layer, idx)] = fn
                else:
                    self.gaming_binds.pop((layer, idx), None)
                r[4] = 1
                r[5] = fn
                r[30], r[31] = rows, cols
        elif sub == 2:
            self.gaming_binds = {}
            r[4] = 1
            r[30], r[31] = rows, cols
        return r

    def _keys_matrix(self):
        try:
            import protocol.virtual_midiswitch as vm
            return vm.ROWS, vm.COLS
        except Exception:
            return 6, 14

    # --------------------------------------------------------------- null bind

    def _keys_nullbind(self, cmd, msg):
        r = _reply(cmd)
        d = msg[6:]
        if cmd == 0xF0:
            g = d[0]
            if g == 0xFF:
                r[4] = 0
                r[5] = 1 if self.nb_enabled else 0
            elif g < NB_GROUPS:
                grp = self.nb_groups[g]
                r[4] = 0
                r[5] = grp["behavior"]
                r[6] = grp["count"]
                r[7:15] = bytes(grp["keys"])
                r[15] = grp["layer"]
                r[16:23] = bytes(grp["reserved"])
            else:
                r[4] = 1
        elif cmd == 0xF1:
            g = d[0]
            if g == 0xFF:
                self.nb_enabled = d[1] != 0
            elif g < NB_GROUPS:
                layer = d[11]
                if layer >= 12 and layer != 0xFF:
                    layer = 0
                self.nb_groups[g] = {"behavior": d[1], "count": min(d[2], NB_KEYS),
                                     "keys": list(d[3:11]), "layer": layer,
                                     "reserved": list(d[12:19])}
            r[4] = 0
        elif cmd == 0xF2:
            self.nb_saved = (copy.deepcopy(self.nb_groups), self.nb_enabled)
        elif cmd == 0xF3:
            self.nb_groups = copy.deepcopy(self.nb_saved[0])
            self.nb_enabled = self.nb_saved[1]
        elif cmd == 0xF4:
            self.nb_groups = [_factory_nb_group() for _ in range(NB_GROUPS)]
            self.nb_saved = (copy.deepcopy(self.nb_groups), self.nb_enabled)
        return r

    # ------------------------------------------------------------- toggle keys

    def _keys_toggle(self, cmd, msg):
        r = _reply(cmd)
        d = msg[6:]
        slot = d[0]
        if cmd == 0xF5:
            if slot >= TOGGLE_SLOTS:
                r[4] = 1
                return r
            e = self.toggle_pool.get(slot) or self.toggle_saved.get(slot)
            if e:
                struct.pack_into("<HBB", r, 5, e["kc"], e["flags"], e["num"])
        elif cmd == 0xF6:
            if slot < TOGGLE_SLOTS:
                kc = d[1] | (d[2] << 8)
                if kc:
                    e = self.toggle_pool.setdefault(slot, {"kc": 0, "flags": 0, "num": 0,
                                                           "multi": [0] * TOGGLE_EXTRA})
                    e["kc"], e["flags"], e["num"] = kc, d[3], d[4]
                else:
                    self.toggle_pool.pop(slot, None)
        elif cmd == 0xF7:
            self.toggle_saved = copy.deepcopy(self.toggle_pool)
        elif cmd == 0xF8:
            self.toggle_pool = copy.deepcopy(self.toggle_saved)
        elif cmd == 0xF9:
            self.toggle_pool = {}
            self.toggle_saved = {}
        elif cmd == 0xFA:
            pass
        elif cmd == 0xFB:
            r[4] = 0
            r[5:10] = bytes([1] * 5)
        elif cmd == 0xFC:
            if slot >= TOGGLE_SLOTS:
                r[4] = 1
                return r
            e = self.toggle_pool.get(slot)
            src = e
            if e is None:
                src = self.toggle_saved.get(slot)
            multi = src["multi"] if src else [0] * TOGGLE_EXTRA
            for j, kc in enumerate(multi):
                struct.pack_into("<H", r, 5 + j * 2, kc)
            r[19] = TOGGLE_ENTRY_SIZE
            if e is not None:
                r[20] = 0
                r[21], r[22] = e["flags"], e["num"]
                struct.pack_into("<H", r, 23, e["kc"])
                r[25] = slot
            else:
                r[20] = 1
        elif cmd == 0xFD:
            if slot >= TOGGLE_SLOTS:
                r[4] = 1
                return r
            kcs = [d[1 + j * 2] | (d[2 + j * 2] << 8) for j in range(TOGGLE_EXTRA)]
            e = self.toggle_pool.get(slot)
            r[5] = TOGGLE_ENTRY_SIZE
            if e is None:
                if not any(kcs):
                    return r
                e = self.toggle_pool.setdefault(slot, {"kc": 0, "flags": 0, "num": 0,
                                                       "multi": [0] * TOGGLE_EXTRA})
            e["multi"] = kcs
            for j, kc in enumerate(kcs):
                struct.pack_into("<H", r, 6 + j * 2, kc)
            r[20], r[21] = e["flags"], e["num"]
        return r

    # ------------------------------------------------------ dynamic keystrokes

    def _keys_dks(self, cmd, msg):
        r = _reply(cmd)
        d = msg[6:]
        if cmd == 0xAA:
            n = d[0]
            if n >= DKS_SLOTS:
                r[5] = 1
                return r
            s = self.dks[n]
            struct.pack_into("<4H4B4H4BH", r, 6, *s["press_kc"], *s["press_act"],
                             *s["release_kc"], *s["release_act"], s["behaviors"])
        elif cmd == 0xAB:
            n, is_press, i = d[0], d[1], d[2]
            if n >= DKS_SLOTS or i >= 4:
                r[5] = 1
                return r
            kc = d[3] | (d[4] << 8)
            act = min(d[5], 100)
            beh = d[6] if d[6] <= 2 else 0
            s = self.dks[n]
            pos = i if is_press else i + 4
            if is_press:
                s["press_kc"][i], s["press_act"][i] = kc, act
            else:
                s["release_kc"][i], s["release_act"][i] = kc, act
            s["behaviors"] = (s["behaviors"] & ~(0x03 << (pos * 2))) | (beh << (pos * 2))
        elif cmd == 0xAC:
            self.dks_saved = copy.deepcopy(self.dks)
        elif cmd == 0xAD:
            if self.dks_saved is not None:
                self.dks = copy.deepcopy(self.dks_saved)
        elif cmd == 0xAE:
            n = d[0]
            if n >= DKS_SLOTS:
                r[5] = 1
            else:
                self.dks[n] = _factory_dks_slot()
        elif cmd == 0xAF:
            self.dks = [_factory_dks_slot() for _ in range(DKS_SLOTS)]
        return r

    # ------------------------------------------------------------ custom names

    def _keys_names(self, msg):
        r = _reply(0xCD)
        sub = msg[4]
        cat, idx = msg[5], msg[6]
        r[4] = sub
        valid = cat < len(CN_COUNTS) and idx < CN_COUNTS[cat]
        if sub == 0x00:
            if valid:
                name = bytes(msg[7:7 + CN_NAME_LEN])
                name = name[:CN_NAME_LEN - 1].split(b"\x00")[0]
                self.cn_names[cat][idx] = name
                r[5] = 0
            else:
                r[5] = 1
        elif sub == 0x01:
            r[5], r[6] = cat, idx
            if valid:
                r[7:7 + len(self.cn_names[cat][idx])] = self.cn_names[cat][idx]
        elif sub == 0x02:
            count = CN_COUNTS[cat] if cat < len(CN_COUNTS) else 0
            out = []
            sent = 0
            i = idx
            while i < count and sent < 8:
                p = _reply(0xCD)
                p[4], p[5], p[6], p[7], p[8] = sub, cat, i, count, sent
                name = self.cn_names[cat][i]
                p[9:9 + len(name)] = name
                out.append(p)
                i += 1
                sent += 1
            r[5], r[6], r[7], r[8] = cat, 0xFF, count, sent
            out.append(r)
            return out
        elif sub == 0x03:
            r[5] = 0
        elif sub == 0x04:
            self.cn_names = [[b""] * n for n in CN_COUNTS]
            r[5] = 0
        elif sub == 0x05:
            r[5] = 1
            r[6:12] = bytes(CN_COUNTS)
        else:
            r[5] = 0xFF
        return r

    # ------------------------------------------------ articulation preset names

    def _keys_preset_names(self):
        out = []
        for pkt in range(USER_PRESETS // 2):
            p = _reply(0xDB)
            p[4], p[5], p[6] = 1, pkt, USER_PRESETS // 2
            for n in range(2):
                name = self.preset_names[pkt * 2 + n]
                off = 7 + n * 11
                p[off] = 1 if name else 0
                p[off + 1:off + 1 + min(10, len(name))] = name[:10]
            out.append(p)
        return out
