# SPDX-License-Identifier: GPL-2.0-or-later
"""Lighting commands for the software MIDIswitch: per-layer RGB, custom
animation slots, per-key RGB presets and the functional (indicator) LED
colours. Every table starts at the factory values a fresh keyboard has."""

LIGHT_LAYERS = 12
CUSTOM_SLOT_COUNT = 50
CUSTOM_PARAM_COUNT = 16
CUSTOM_PREVIEW_SLOTS = 49          # slots with their own lighting effect
CUSTOM_EFFECT_BASE = 78            # effect id of custom slot 0
PER_KEY_PALETTE_SIZE = 16
PER_KEY_PRESETS = 12
PER_KEY_LEDS = 70
FLED_COUNT = 92
KEYMAP_CHUNKS = 12 * 6             # layers x matrix rows

# Custom animation slots, 16 parameters each:
# live pos, macro pos, live anim, macro anim, flags, background, effect hue,
# colour scheme, enabled, background brightness, live speed, macro speed,
# live brightness, macro brightness, background speed, effect saturation.
CUSTOM_SLOT_DEFAULTS = (
    (0,0,6,7,0,5,0,68,1,40,255,255,255,255,128,255),
    (0,0,2,0,0,51,137,72,1,75,255,255,255,255,128,255),
    (1,1,18,22,0,72,18,28,1,35,255,255,255,255,128,255),
    (0,3,62,78,0,67,155,42,1,50,255,255,255,255,128,255),
    (20,33,116,124,0,59,36,48,1,20,180,180,255,255,128,255),
    (4,3,82,78,0,115,173,36,1,50,180,190,255,255,128,255),
    (1,18,28,17,0,5,54,2,1,50,255,255,255,255,128,255),
    (22,29,161,18,0,66,191,29,1,15,180,180,255,255,128,255),
    (6,9,68,96,0,106,72,52,1,35,255,255,255,255,128,255),
    (1,1,24,26,0,76,209,41,1,50,255,255,255,255,128,255),
    (15,19,39,12,0,92,90,38,1,25,255,255,255,255,128,255),
    (21,32,42,41,0,108,227,25,1,30,255,255,255,255,128,255),
    (10,16,114,122,0,71,108,59,1,40,255,255,255,255,128,255),
    (1,0,50,171,0,81,245,31,1,50,180,200,255,255,128,255),
    (5,16,140,70,0,105,126,17,1,45,180,180,255,255,128,255),
    (7,13,124,126,0,75,7,9,1,50,180,180,255,255,128,255),
    (15,31,33,30,0,100,144,53,1,20,255,255,255,255,128,255),
    (1,13,108,79,0,87,25,22,1,50,200,190,255,255,128,255),
    (3,15,83,135,0,110,162,46,1,50,255,255,255,255,128,255),
    (20,24,142,39,0,78,43,35,1,25,190,180,255,255,128,255),
    (0,7,2,170,0,93,180,58,1,40,255,255,255,255,128,255),
    (8,14,22,97,0,68,61,11,1,50,255,255,255,255,128,255),
    (1,18,20,14,0,101,198,40,1,45,210,190,255,255,128,255),
    (22,33,30,118,0,84,79,27,1,15,255,255,255,255,128,255),
    (0,0,160,140,0,77,216,4,1,50,255,255,255,255,128,255),
    (15,11,31,138,0,106,97,37,1,30,255,255,255,255,128,255),
    (6,9,71,101,0,73,234,20,1,50,255,255,255,255,128,255),
    (21,29,43,49,0,105,115,13,1,25,180,180,255,255,128,255),
    (0,19,16,24,0,98,252,32,1,45,255,255,255,255,128,255),
    (5,8,158,134,0,85,133,42,1,40,255,255,255,255,128,255),
    (7,13,135,128,0,102,14,16,1,50,255,255,255,255,128,255),
    (15,1,62,27,0,97,151,39,1,30,255,255,255,255,128,255),
    (1,1,170,167,0,6,32,76,1,30,180,180,255,255,128,255),
    (15,14,16,18,0,31,169,80,1,65,255,255,255,255,128,255),
    (7,6,22,20,0,7,50,84,1,50,180,180,255,255,128,255),
    (3,4,16,16,0,41,187,67,1,60,255,255,255,255,128,255),
    (7,6,20,20,0,8,68,71,1,40,255,255,255,255,128,255),
    (1,2,40,74,0,21,205,75,1,80,255,255,255,255,128,255),
    (0,24,14,32,0,5,86,79,1,25,255,255,255,255,128,255),
    (5,17,122,116,0,11,223,83,1,70,180,180,255,255,128,255),
    (21,18,63,35,0,6,104,66,1,35,180,180,255,255,128,255),
    (10,11,132,138,0,51,241,70,1,85,255,255,255,255,128,255),
    (15,0,148,38,0,7,122,74,1,30,255,255,255,255,128,255),
    (23,43,41,29,0,5,3,78,1,45,255,255,255,255,128,255),
    (24,44,19,15,0,21,140,82,1,75,255,255,255,255,128,255),
    (25,36,1,1,0,8,21,65,1,50,255,255,255,255,128,255),
    (32,46,32,62,0,11,158,69,1,60,255,255,255,255,128,255),
    (26,42,65,45,0,6,39,73,1,40,190,180,255,255,128,255),
    (30,36,130,140,0,31,176,77,1,70,255,255,255,255,128,255),
    (31,34,12,28,0,7,57,81,1,35,255,255,255,255,128,255),
)

# Parameter limits (value must be below the limit, None = any byte).
_CUSTOM_PARAM_LIMIT = (34, 47, 174, 174, None, 121, None, 85, None, 101,
                       None, None, None, None, None, None)

# 16-colour palette (H, S, V): off, red, orange, yellow, green, cyan, blue,
# purple, magenta, pink, white, warm white, spring green, coral, gold, azure.
PER_KEY_PALETTE_DEFAULTS = (
    (0, 0, 0), (0, 255, 255), (28, 255, 255), (43, 255, 255),
    (85, 255, 255), (128, 255, 255), (170, 255, 255), (191, 255, 255),
    (213, 255, 255), (234, 255, 255), (0, 0, 255), (28, 50, 255),
    (106, 255, 255), (11, 176, 255), (36, 255, 218), (132, 102, 255),
)

# Functional LED states (H, S, V, blink: 0 solid, 1 slow, 2 fast).
FLED_DEFAULTS = (
    (0,0,150,0), (0,255,200,0), (85,255,200,0), (85,255,200,2),
    (0,255,200,2), (23,255,255,0), (85,255,200,0), (85,255,200,2),
    (0,0,80,0), (85,255,120,0), (85,255,120,2), (0,255,120,0),
    (0,255,200,0), (85,255,200,0), (85,255,200,1), (23,255,200,2),
    (23,255,200,0), (85,255,200,2), (85,255,200,0), (0,255,200,0),
    (0,0,30,0), (0,255,200,0), (85,255,200,0), (0,255,80,0),
    (85,255,200,0), (170,255,200,0), (0,255,200,0), (43,255,200,0),
    (128,255,200,0), (213,255,200,0), (0,0,200,0), (23,255,200,0),
    (85,255,200,0), (43,255,200,0), (85,255,200,0), (170,255,255,0),
    (0,255,255,0), (85,255,255,0), (213,255,255,0), (43,255,255,0),
    (28,255,255,0), (128,255,255,0), (0,255,200,0), (192,255,200,0),
    (85,255,200,0), (0,255,200,0), (192,255,200,0), (225,128,200,0),
    (192,255,200,0), (0,0,30,0), (23,255,200,0), (23,255,200,0),
    (0,0,150,0), (170,255,200,0), (128,255,200,0), (128,255,200,2),
    (170,255,200,2), (23,255,255,0), (128,255,200,0), (128,255,200,2),
    (0,0,80,0), (128,255,120,0), (128,255,120,2), (170,255,120,0),
    (0,0,80,0), (43,255,200,0), (85,255,200,0), (23,255,255,0),
    (0,0,80,0), (192,255,200,0), (213,255,200,0), (23,255,255,0),
    (0,0,80,0), (225,200,200,0), (225,255,255,0), (23,255,255,0),
    (0,0,80,0), (128,255,200,0), (128,255,255,0), (23,255,255,0),
    (28,255,200,0), (43,255,255,0), (43,255,255,2), (28,255,200,2),
    (0,255,220,0), (0,0,40,0), (85,255,220,0), (0,0,60,0),
    (128,255,220,0), (0,0,40,0), (190,255,220,0), (0,0,40,0),
)


def _sanitize_slot(p):
    """Values a stored slot is corrected to when it is read back."""
    p = list(p)
    if p[9] > 100:
        p[9] = 100
    if p[14] == 0:
        p[14] = 128
    if p[5] > 120:
        p[5] = 5
    if p[0] >= 34:
        p[0] = 1
    if p[1] >= 47:
        p[1] = 1
    if p[2] >= 174:
        p[2] = 0
    if p[3] >= 174:
        p[3] = 0
    if p[7] >= 85:
        p[7] = 1
    return p


class LightingMixin:

    def _init_lighting(self):
        self.layer_rgb_enabled = False
        self.layer_rgb_blocks = [None] * LIGHT_LAYERS           # (mode, h, s, v, speed)
        self.custom_slots = [list(s) for s in CUSTOM_SLOT_DEFAULTS]
        self.custom_slots_saved = [list(s) for s in CUSTOM_SLOT_DEFAULTS]
        self.current_custom_slot = 0
        self._reset_per_key()
        self.per_key_saved = ([list(c) for c in self.per_key_palette],
                              [list(p) for p in self.per_key_presets])
        self.fled = [list(e) for e in FLED_DEFAULTS]
        self.fled_saved = [list(e) for e in FLED_DEFAULTS]
        self.ram_keymap_chunks = {}

    def _reset_per_key(self):
        self.per_key_palette = [list(c) for c in PER_KEY_PALETTE_DEFAULTS]
        self.per_key_presets = [[0] * PER_KEY_LEDS for _ in range(PER_KEY_PRESETS)]

    def _custom_lighting(self, cmd, msg):
        # Every lighting command travels with the prefix form; nothing to
        # claim in the custom family.
        return None

    # ---- helpers ---------------------------------------------------------

    def _rgb_state(self):
        rgb = getattr(self, "rgb", None)
        if rgb is None:
            rgb = [0, 128, 0, 255, 255]
            self.rgb = rgb
        return rgb

    def _active_custom_slot(self):
        mode = self._rgb_state()[0]
        if CUSTOM_EFFECT_BASE <= mode < CUSTOM_EFFECT_BASE + CUSTOM_PREVIEW_SLOTS:
            self.current_custom_slot = mode - CUSTOM_EFFECT_BASE
        return self.current_custom_slot

    def _set_custom_param(self, slot, param, value):
        limit = _CUSTOM_PARAM_LIMIT[param]
        if param == 8:
            value = 1 if value else 0
        elif limit is not None and value >= limit:
            return
        self.custom_slots[slot][param] = value

    # ---- prefix-form commands --------------------------------------------

    def _vial_lighting(self, sub, msg):
        r = bytearray(msg)
        if sub == 0xBC:                                   # save current RGB to a layer
            layer = msg[2]
            if layer < LIGHT_LAYERS:
                mode, speed, h, s, v = self._rgb_state()
                self.layer_rgb_blocks[layer] = (mode, h, s, v, speed)
                r[0] = 1
            else:
                r[0] = 0
        elif sub == 0xBD:                                 # apply a layer's saved RGB
            layer = msg[2]
            if layer < LIGHT_LAYERS:
                block = self.layer_rgb_blocks[layer]
                if block is None and layer != 0:
                    block = self.layer_rgb_blocks[0]
                if block is not None:
                    mode, h, s, v, speed = block
                    rgb = self._rgb_state()
                    rgb[:] = [mode, speed, h, s, v]
                r[0] = 1
            else:
                r[0] = 0
        elif sub == 0xBE:                                 # per-layer RGB on/off
            self.layer_rgb_enabled = msg[2] != 0
            r[0] = 1
        elif sub == 0xBF:                                 # per-layer RGB status
            r[0] = 1 if self.layer_rgb_enabled else 0
            r[1] = LIGHT_LAYERS
        elif sub == 0xC0:                                 # set one slot parameter
            slot, param, value = msg[2], msg[3], msg[4]
            if slot >= CUSTOM_SLOT_COUNT or param >= CUSTOM_PARAM_COUNT:
                r[0] = 0
            else:
                self._set_custom_param(slot, param, value)
                r[0] = 1
        elif sub == 0xC1:                                 # get one slot parameter
            slot, param = msg[2], msg[3]
            if slot >= CUSTOM_SLOT_COUNT or param >= CUSTOM_PARAM_COUNT:
                r[0] = 0
            else:
                r[0] = 1
                r[4] = self.custom_slots[slot][param]
        elif sub == 0xC2:                                 # set all parameters (stored)
            slot = msg[2]
            if slot >= CUSTOM_SLOT_COUNT:
                r[0] = 0
            else:
                for i in range(CUSTOM_PARAM_COUNT):
                    self._set_custom_param(slot, i, msg[3 + i])
                self.custom_slots_saved[slot] = list(self.custom_slots[slot])
                r[0] = 1
        elif sub in (0xC3, 0xC9):                         # get all parameters
            slot = msg[2]
            if slot >= CUSTOM_SLOT_COUNT:
                r[0] = 0
            else:
                src = self.custom_slots_saved if (sub == 0xC3 and msg[3] == 1) else self.custom_slots
                r[0] = 1
                r[3:3 + CUSTOM_PARAM_COUNT] = bytes(src[slot])
        elif sub == 0xC4:                                 # store all slots
            self.custom_slots_saved = [list(s) for s in self.custom_slots]
            r[0] = 1
        elif sub == 0xC5:                                 # reload stored slots
            self.custom_slots = [_sanitize_slot(s) for s in self.custom_slots_saved]
            r[0] = 1
        elif sub == 0xC6:                                 # reset a slot to a plain default
            slot = msg[2]
            if slot >= CUSTOM_SLOT_COUNT:
                r[0] = 0
            else:
                p = self.custom_slots[slot]
                p[0], p[1], p[2], p[3], p[4], p[5] = 1, 1, 0, 0, 0, 0
                p[6], p[15], p[7], p[8], p[9] = 0, 255, 1, 1, 30
                p[12], p[13], p[14] = 255, 255, 128
                self.custom_slots_saved[slot] = list(p)
                r[0] = 1
        elif sub == 0xC7:                                 # custom animation status
            r[0] = 1
            r[1] = CUSTOM_SLOT_COUNT
            r[2] = self._active_custom_slot()
            r[3:10] = bytes(7)
            for i, s in enumerate(self.custom_slots):
                if s[8]:
                    r[3 + i // 8] |= 1 << (i % 8)
            r[10] = CUSTOM_PARAM_COUNT
        elif sub == 0xC8:                                 # rescan LED positions
            r[0] = 1
        elif sub == 0xED:                                 # preview a slot (not stored)
            slot = msg[2]
            if slot < CUSTOM_PREVIEW_SLOTS:
                self._rgb_state()[0] = CUSTOM_EFFECT_BASE + slot
                self.current_custom_slot = slot
            r[0] = 1
        elif sub == 0xD3:                                 # per-key palette (paged)
            offset, count = msg[2], msg[3]
            if offset >= PER_KEY_PALETTE_SIZE:
                offset, count = 0, 10
            if count == 0:
                count = 10
            count = min(count, PER_KEY_PALETTE_SIZE - offset, 10)
            r = bytearray(32)
            r[0] = 1
            for i in range(count):
                r[1 + i * 3:4 + i * 3] = bytes(self.per_key_palette[offset + i])
        elif sub == 0xD4:                                 # set palette colour
            idx = msg[2]
            if idx < PER_KEY_PALETTE_SIZE:
                self.per_key_palette[idx] = [msg[3], msg[4], msg[5]]
                r[0] = 1
            else:
                r[0] = 0
        elif sub == 0xD5:                                 # preset LED data (paged)
            preset, offset, count = msg[2], msg[3], msg[4]
            if preset < PER_KEY_PRESETS and offset < PER_KEY_LEDS:
                count = min(count, 31, PER_KEY_LEDS - offset)
                r = bytearray(32)
                r[0] = 1
                r[1:1 + count] = bytes(self.per_key_presets[preset][offset:offset + count])
            else:
                r[0] = 0
        elif sub == 0xD6:                                 # set an LED's palette index
            preset, led, idx = msg[2], msg[3], msg[4]
            if preset < PER_KEY_PRESETS and led < PER_KEY_LEDS and idx < PER_KEY_PALETTE_SIZE:
                self.per_key_presets[preset][led] = idx
                r[0] = 1
            else:
                r[0] = 0
        elif sub == 0xD7:                                 # store per-key data
            self.per_key_saved = ([list(c) for c in self.per_key_palette],
                                  [list(p) for p in self.per_key_presets])
            r[0] = 1
        elif sub == 0xD8:                                 # reload, or 0xFF = factory reset
            if msg[2] == 0xFF:
                self._reset_per_key()
                self.per_key_saved = ([list(c) for c in self.per_key_palette],
                                      [list(p) for p in self.per_key_presets])
            else:
                pal, pre = self.per_key_saved
                self.per_key_palette = [list(c) for c in pal]
                self.per_key_presets = [list(p) for p in pre]
            r[0] = 1
        elif sub == 0xE9:                                 # keymap upload + rescan
            if msg[2] == 0x00:
                if msg[3] < KEYMAP_CHUNKS:
                    self.ram_keymap_chunks[msg[3]] = bytes(msg[4:32])
                    r[0] = 1
                else:
                    r[0] = 0
            else:
                r[0] = 1 if msg[2] == 0x01 else 0
        elif sub == 0xEA:                                 # functional LED states (paged)
            offset, count = msg[2], msg[3]
            if offset >= FLED_COUNT:
                offset, count = 0, 7
            if count == 0:
                count = 7
            count = min(count, FLED_COUNT - offset, 7)
            r = bytearray(32)
            r[0] = 1
            for i in range(count):
                r[1 + i * 4:5 + i * 4] = bytes(self.fled[offset + i])
        elif sub == 0xEB:                                 # set a functional LED state
            idx = msg[2]
            if idx < FLED_COUNT:
                blink = msg[6] if msg[6] <= 2 else 0
                self.fled[idx] = [msg[3], msg[4], msg[5], blink]
                r[0] = 1
            else:
                r[0] = 0
        elif sub == 0xEC:                                 # 0 store, 1 reload, 0xFF factory
            op = msg[2]
            if op == 0x00:
                self.fled_saved = [list(e) for e in self.fled]
                r[0] = 1
            elif op == 0x01:
                self.fled = [list(e) for e in self.fled_saved]
                r[0] = 1
            elif op == 0xFF:
                self.fled = [list(e) for e in FLED_DEFAULTS]
                self.fled_saved = [list(e) for e in FLED_DEFAULTS]
                r[0] = 1
            else:
                r[0] = 0
        else:
            return None
        return r
