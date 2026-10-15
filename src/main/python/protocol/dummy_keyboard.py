from protocol.keyboard_comm import Keyboard


# Layer 1 of the virtual MIDIswitch (the demo / "just looking around" mode):
# the standard MIDIswitch keycap layout, rows 0-4 of the 5x14 key grid.
DEMO_LAYER0 = [
    "KC_ESCAPE KC_1 KC_2 KC_3 KC_4 KC_5 KC_6 KC_7 KC_8 KC_9 KC_0 KC_MINUS KC_EQUAL KC_BSPACE",
    "KC_TAB KC_Q KC_W KC_E KC_R KC_T KC_Y KC_U KC_I KC_O KC_P KC_LBRACKET KC_RBRACKET KC_DELETE",
    "KC_CAPSLOCK KC_A KC_S KC_D KC_F KC_G KC_H KC_J KC_K KC_L KC_SCOLON KC_QUOTE KC_NO KC_ENTER",
    "KC_LSHIFT KC_NO KC_Z KC_X KC_C KC_V KC_B KC_N KC_M KC_COMMA KC_DOT KC_SLASH KC_UP KC_BSLASH",
    "KC_LCTRL KC_LGUI KC_LALT FN_MO13 KC_SPACE KC_SPACE KC_SPACE KC_SPACE KC_SPACE KC_SPACE "
    "KC_RCTRL KC_LEFT KC_DOWN KC_RIGHT",
]


class DummyKeyboard(Keyboard):

    def reload_layers(self):
        self.layers = 4

    def reload_keymap(self):
        demo = [row.split() for row in DEMO_LAYER0]
        for layer in range(self.layers):
            for row, col in self.rowcol.keys():
                code = "KC_NO"
                if layer == 0 and row < len(demo) and col < len(demo[row]):
                    code = demo[row][col]
                self.layout[(layer, row, col)] = code

        for layer in range(self.layers):
            for idx in self.encoderpos:
                self.encoder_layout[(layer, idx, 0)] = "KC_NO"
                self.encoder_layout[(layer, idx, 1)] = "KC_NO"

        if self.layout_labels:
            self.layout_options = 0

    def reload_macros_early(self):
        self.macro_count = 16
        self.macro_memory = 900

    def reload_macros_late(self):
        self.macro = b"\x00" * self.macro_count

    def set_key(self, layer, row, col, code):
        self.layout[(layer, row, col)] = code

    def set_encoder(self, layer, index, direction, code):
        self.encoder_layout[(layer, index, direction)] = code

    def set_layout_options(self, options):
        if self.layout_options != -1 and self.layout_options != options:
            self.layout_options = options

    def set_macro(self, data):
        if len(data) > self.macro_memory:
            raise RuntimeError("the macro is too big: got {} max {}".format(len(data), self.macro_memory))
        self.macro = data

    def reset(self):
        pass

    def get_uid(self):
        return b"\x00" * 8

    def get_unlock_status(self):
        return 1

    def get_unlock_in_progress(self):
        return 0

    def get_unlock_keys(self):
        return []

    def unlock_start(self):
        return

    def unlock_poll(self):
        return b""

    def lock(self):
        return

    def probe_ident(self):
        return None

    def reload_via_protocol(self):
        pass

    def reload_persistent_rgb(self):
        """
            Reload RGB properties which are slow, and do not change while keyboard is plugged in
            e.g. VialRGB supported effects list
        """

        if "lighting" in self.definition:
            self.lighting_qmk_rgblight = self.definition["lighting"] in ["qmk_rgblight", "qmk_backlight_rgblight"]
            self.lighting_qmk_backlight = self.definition["lighting"] in ["qmk_backlight", "qmk_backlight_rgblight"]
            self.lighting_vialrgb = self.definition["lighting"] == "vialrgb"

        if self.lighting_vialrgb:
            self.rgb_version = 1
            self.rgb_maximum_brightness = 128

            self.rgb_supported_effects = {0, 1, 2, 3}

    def reload_rgb(self):
        if self.lighting_qmk_rgblight:
            self.underglow_brightness = 128
            self.underglow_effect = 1
            self.underglow_effect_speed = 5
            # hue, sat
            self.underglow_color = (32, 64)

        if self.lighting_qmk_backlight:
            self.backlight_brightness = 42
            self.backlight_effect = 0

        if self.lighting_vialrgb:
            self.rgb_mode = 2
            self.rgb_speed = 90
            self.rgb_hsv = (16, 32, 64)
