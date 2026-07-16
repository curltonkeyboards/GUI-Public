# SPDX-License-Identifier: GPL-2.0-or-later
import struct
import json
import lzma
import logging
import time
from collections import OrderedDict

from keycodes.keycodes import RESET_KEYCODE, Keycode, recreate_keyboard_keycodes

# Startup logging - import lazily to avoid circular imports
def _startup_log(msg):
    try:
        from startup_dialog import startup_log
        startup_log(msg)
    except ImportError:
        pass
from kle_serial import Serial as KleSerial, Key
from protocol.combo import ProtocolCombo
from protocol.constants import CMD_VIA_GET_PROTOCOL_VERSION, CMD_VIA_GET_KEYBOARD_VALUE, CMD_VIA_SET_KEYBOARD_VALUE, \
    CMD_VIA_SET_KEYCODE, CMD_VIA_LIGHTING_SET_VALUE, CMD_VIA_LIGHTING_GET_VALUE, CMD_VIA_LIGHTING_SAVE, \
    CMD_VIA_GET_LAYER_COUNT, CMD_VIA_KEYMAP_GET_BUFFER, CMD_VIA_VIAL_PREFIX, VIA_LAYOUT_OPTIONS, \
    VIA_SWITCH_MATRIX_STATE, QMK_BACKLIGHT_BRIGHTNESS, QMK_BACKLIGHT_EFFECT, QMK_RGBLIGHT_BRIGHTNESS, \
    QMK_RGBLIGHT_EFFECT, QMK_RGBLIGHT_EFFECT_SPEED, QMK_RGBLIGHT_COLOR, VIALRGB_GET_INFO, VIALRGB_GET_MODE, \
    VIALRGB_GET_SUPPORTED, VIALRGB_SET_MODE, CMD_VIAL_GET_KEYBOARD_ID, CMD_VIAL_GET_SIZE, CMD_VIAL_GET_DEFINITION, \
    CMD_VIAL_GET_ENCODER, CMD_VIAL_SET_ENCODER, CMD_VIAL_GET_UNLOCK_STATUS, CMD_VIAL_UNLOCK_START, CMD_VIAL_UNLOCK_POLL, \
    CMD_VIAL_LOCK, CMD_VIAL_QMK_SETTINGS_QUERY, CMD_VIAL_QMK_SETTINGS_GET, CMD_VIAL_QMK_SETTINGS_SET, \
    CMD_VIAL_QMK_SETTINGS_RESET, BUFFER_FETCH_CHUNK, VIAL_PROTOCOL_QMK_SETTINGS, \
    CMD_VIAL_LAYER_RGB_SAVE, CMD_VIAL_LAYER_RGB_LOAD, CMD_VIAL_LAYER_RGB_ENABLE, CMD_VIAL_LAYER_RGB_GET_STATUS, \
    CMD_VIAL_CUSTOM_ANIM_SET_PARAM, CMD_VIAL_CUSTOM_ANIM_GET_PARAM, CMD_VIAL_CUSTOM_ANIM_SET_ALL, \
    CMD_VIAL_CUSTOM_ANIM_GET_ALL, CMD_VIAL_CUSTOM_ANIM_SAVE, CMD_VIAL_CUSTOM_ANIM_LOAD, \
    CMD_VIAL_CUSTOM_ANIM_RESET_SLOT, CMD_VIAL_CUSTOM_ANIM_GET_STATUS, CMD_VIAL_CUSTOM_ANIM_RESCAN_LEDS, \
    CMD_VIAL_CUSTOM_ANIM_ACTIVATE_SLOT, \
    CMD_VIAL_KEYMAP_RAM_RESCAN
from protocol.dynamic import ProtocolDynamic
from protocol.key_override import ProtocolKeyOverride
from protocol.macro import ProtocolMacro
from protocol.tap_dance import ProtocolTapDance
from unlocker import Unlocker
from util import MSG_LEN, hid_lock_for, hid_send

SUPPORTED_VIA_PROTOCOL = [-1, 9]
SUPPORTED_VIAL_PROTOCOL = [-1, 0, 1, 2, 3, 4, 5, 6]

HID_MANUFACTURER_ID = 0x7D
HID_SUB_ID = 0x00
HID_DEVICE_ID = 0x4D
HID_PACKET_SIZE = 32

# Loop Operations (0xA7)
HID_CMD_CLEAR_ALL_LOOPS = 0xA7        # Clear all loop content

# ThruLoop Commands (0xB0-0xB5)
HID_CMD_SET_LOOP_CONFIG = 0xB0
HID_CMD_SET_MAIN_LOOP_CCS = 0xB1
HID_CMD_SET_OVERDUB_CCS = 0xB2
HID_CMD_SET_NAVIGATION_CONFIG = 0xB3
HID_CMD_GET_ALL_CONFIG = 0xB4
HID_CMD_RESET_LOOP_CONFIG = 0xB5

# MIDIswitch Commands (0xB6-0xBF)
HID_CMD_SET_KEYBOARD_CONFIG = 0xB6
HID_CMD_GET_KEYBOARD_CONFIG = 0xB7
HID_CMD_RESET_KEYBOARD_CONFIG = 0xB8
HID_CMD_SAVE_KEYBOARD_SLOT = 0xB9
HID_CMD_LOAD_KEYBOARD_SLOT = 0xBA
HID_CMD_SET_KEYBOARD_CONFIG_ADVANCED = 0xBB
HID_CMD_LCD_THEME = 0xFE  # Get/set global LCD colour theme (sub 0=GET, 1=SET)
HID_CMD_SET_KEYBOARD_PARAM_SINGLE = 0xE8  # Set individual parameter (changed from 0xBD collision)

# Parameter IDs for HID_CMD_SET_KEYBOARD_PARAM_SINGLE
PARAM_CHANNEL_NUMBER = 0
PARAM_TRANSPOSE_NUMBER = 1
PARAM_TRANSPOSE_NUMBER2 = 2
PARAM_TRANSPOSE_NUMBER3 = 3
PARAM_HE_VELOCITY_CURVE = 4
PARAM_HE_VELOCITY_MIN = 5
PARAM_HE_VELOCITY_MAX = 6
PARAM_KEYSPLIT_HE_VELOCITY_CURVE = 7
PARAM_KEYSPLIT_HE_VELOCITY_MIN = 8
PARAM_KEYSPLIT_HE_VELOCITY_MAX = 9
PARAM_TRIPLESPLIT_HE_VELOCITY_CURVE = 10
PARAM_TRIPLESPLIT_HE_VELOCITY_MIN = 11
PARAM_TRIPLESPLIT_HE_VELOCITY_MAX = 12
# Global MIDI Settings (velocity, aftertouch, vibrato)
PARAM_VELOCITY_MODE = 13             # 0=Fixed, 1=Peak, 2=Speed, 3=Speed+Peak
PARAM_AFTERTOUCH_MODE = 14           # 0=Off, 1=Bottom-out, 2=Bottom-out(NS), 3=Reverse, 4=Reverse(NS), 5=Post-actuation, 6=Post-actuation(NS), 7=Vibrato, 8=Vibrato(NS)
PARAM_BASE_SUSTAIN = 15
PARAM_KEYSPLIT_SUSTAIN = 16
PARAM_TRIPLESPLIT_SUSTAIN = 17
PARAM_KEYSPLITCHANNEL = 18
PARAM_KEYSPLIT2CHANNEL = 19
PARAM_KEYSPLITSTATUS = 20
PARAM_KEYSPLITTRANSPOSESTATUS = 21
PARAM_KEYSPLITVELOCITYSTATUS = 22
PARAM_VELOCITY_SENSITIVITY = 30  # 4-byte uint32
PARAM_CC_SENSITIVITY = 31  # 4-byte uint32
PARAM_LUT_CORRECTION_STRENGTH = 32  # 0-100: Hall sensor linearization strength
# MIDI Routing Override Settings
PARAM_CHANNEL_OVERRIDE = 33        # bool: Override channel with fixed channel_number
PARAM_VELOCITY_OVERRIDE = 34       # bool: Override velocity calculation
PARAM_TRANSPOSE_OVERRIDE = 35      # bool: Override transpose
PARAM_MIDI_IN_MODE = 36            # 0=Process All, 1=Thru, 2=Clock Only, 3=Ignore
PARAM_USB_MIDI_MODE = 37           # 0=Process All, 1=Thru, 2=Clock Only, 3=Ignore
PARAM_MIDI_CLOCK_SOURCE = 38       # 0=Local, 1=USB, 2=MIDI IN
# Global MIDI Settings (continued)
PARAM_AFTERTOUCH_CC = 39           # 0-127 = CC number, 255 = off (poly AT only)
PARAM_VIBRATO_SENSITIVITY = 40     # 50-200 (percentage, 100 = normal)
PARAM_VIBRATO_DECAY_TIME = 41      # 0-2000 (milliseconds, 16-bit) - use 2-byte write
PARAM_MIN_PRESS_TIME = 42          # 0-255 (ms) - minimum time for slow press (full velocity)
PARAM_MAX_PRESS_TIME = 43          # 0-255 (ms) - maximum time for fast press (min velocity)
PARAM_SPEED_PEAK_RATIO = 44       # 0-100 = ratio of speed to peak (0=all peak, 100=all speed)
PARAM_MACRO_OVERRIDE_LIVE_NOTES = 45  # bool: macro notes override live notes
# SmartChord settings
PARAM_SMARTCHORD_MODE = 46            # 0=Hold, 1=Toggle
PARAM_BASE_SMARTCHORD_IGNORE = 47     # 0=Allow, 1=Ignore smartchord for base zone
PARAM_KEYSPLIT_SMARTCHORD_IGNORE = 48 # 0=Allow, 1=Ignore smartchord for keysplit zone
PARAM_TRIPLESPLIT_SMARTCHORD_IGNORE = 49  # 0=Allow, 1=Ignore smartchord for triplesplit zone
PARAM_VELOCITY_AS_AT = 50                # bool: pre-load aftertouch from velocity on note-on
PARAM_MACRO_SYNC_TO_LOOP = 51            # bool: defer macro send until next loop trigger (global, deprecated)
PARAM_MACRO_LOOP_MODE = 52               # 16-bit: low byte=macro_id, high byte=mode (0-3)
PARAM_MACRO_PER_SYNC = 53               # 16-bit: low byte=macro_id, high byte=sync (0/1)
PARAM_MACRO_CANCEL_ALL = 54              # trigger: cancel all playing Vial macros
PARAM_CHORD_DISPLAY_MODE = 55            # 0=Chords, 1=Numerals, 2=Name (chord progression OLED label)

# Gaming/Joystick Commands (0xCE-0xD2)
HID_CMD_GAMING_SET_MODE = 0xBC           # Set gaming mode on/off (moved from 0xCE, which the firmware arp handler claims as GET_NOTES_CHUNK)
HID_CMD_GAMING_SET_KEY_MAP = 0xCF        # Map key to joystick control
HID_CMD_GAMING_SET_ANALOG_CONFIG = 0xD0  # Set min/max travel and deadzone
HID_CMD_GAMING_GET_SETTINGS = 0xD1       # Get current gaming settings
HID_CMD_GAMING_RESET = 0xD2              # Reset gaming settings to defaults

# ADC Matrix Tester Command (0xDF)
HID_CMD_GET_ADC_MATRIX = 0xDF             # Get ADC values for matrix row

# Distance Matrix Command (0xE7)
HID_CMD_GET_DISTANCE_MATRIX = 0xE7        # Get distance (mm) values for specific keys

# Calibration Debug Command (0xD5) - moved from 0xE8 to avoid collision with SET_KEYBOARD_PARAM_SINGLE
HID_CMD_CALIBRATION_DEBUG = 0xD5          # Get calibration debug values

# Per-Key Actuation Commands (0xE0-0xE6)
HID_CMD_SET_PER_KEY_ACTUATION = 0xE0     # Set actuation for specific key
HID_CMD_GET_PER_KEY_ACTUATION = 0xE1     # Get actuation for specific key
HID_CMD_GET_ALL_PER_KEY_ACTUATIONS = 0xE2  # Get all per-key actuations
HID_CMD_RESET_PER_KEY_ACTUATIONS = 0xE3  # Reset all to defaults
HID_CMD_SET_PER_KEY_MODE = 0xE4          # Set per-key mode flags
HID_CMD_GET_PER_KEY_MODE = 0xE5          # Get per-key mode flags
HID_CMD_COPY_LAYER_ACTUATIONS = 0xE6     # Copy one layer to another

# Layer Actuation Commands (0xEB-0xEE) - moved from 0xCA-0xCD to avoid arpeggiator conflict
HID_CMD_GET_LAYER_ACTUATION = 0xEB       # Get actuation for specific layer
HID_CMD_SET_LAYER_ACTUATION = 0xEC       # Set actuation for specific layer
HID_CMD_GET_ALL_LAYER_ACTUATIONS = 0xED  # Get all layer actuations (bulk)
HID_CMD_RESET_LAYER_ACTUATIONS = 0xEE    # Reset all layer actuations

# Velocity Tab Commands (0xD3-0xD4)
HID_CMD_VELOCITY_MATRIX_POLL = 0xD3      # Poll velocity + travel time for specific keys
HID_CMD_VELOCITY_TIME_SETTINGS = 0xD4    # Get/Set global velocity min/max time settings

# Device introspection (0x92-0x93; moved from 0xD6-0xD7, which collided with
# the MIDI-delay slot commands and the gaming-curve commands in firmware)
HID_CMD_GET_ACTIVE_LAYER = 0x92          # Get the keyboard's currently-active layer
HID_CMD_GET_FIRMWARE_VERSION = 0x93      # Get firmware version (major, minor, patch)

# Custom Names Command (0xCD) - OLED display names for macros/arp/seq/delay/toggles
# Single command with sub-commands in payload[0] (see feature_names.py for sub-command IDs)
HID_CMD_CUSTOM_NAMES = 0xCD

# Drum Keybinds (global default drum-voice bindings for the drum machine).
# Payload/response layout after the 6-byte header: bytes 6..17 = 12 voice notes,
# bytes 18..29 = 12 voice velocities. Reuses formerly-EQ command bytes.
HID_CMD_DRUM_KEYBINDS_GET = 0xE9    # Get current global default bindings
HID_CMD_DRUM_KEYBINDS_SET = 0xEA    # Set global default + link to uncustomized slots
HID_CMD_DRUM_KEYBINDS_RESET = 0xEF  # Reset ALL slots + global default to GM factory

# Number of drum voice slots (must match firmware FACTORY_SEQ_VOICE_SLOTS)
DRUM_KEYBIND_VOICE_COUNT = 12
DRUM_EXTRA_VOICE_COUNT = 16          # extra DrumLIVE-only voicings (notes only)
DRUM_KEYBINDS_SUBMODE_EXTRAS = 2     # data[4] sub-mode for the extra voicings

class ProtocolError(Exception):
    pass


def _hid_transaction(fn):
    """Hold the device's shared HID transaction lock for the whole method.

    Multi-packet reads (request via usb_send, then a loop of raw dev.read
    calls) must be atomic against other threads using the same handle (the
    loop manager's listener thread) — an interleaved read steals packets from
    the collector and corrupts both sides. The lock is an RLock shared with
    hid_send and VialDevice.send/recv, so nested usb_send calls are fine."""
    def wrapper(self, *args, **kwargs):
        with hid_lock_for(self.dev):
            return fn(self, *args, **kwargs)
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper

class Keyboard(ProtocolMacro, ProtocolDynamic, ProtocolTapDance, ProtocolCombo, ProtocolKeyOverride):
    """ Low-level communication with a vial-enabled keyboard """

    def __init__(self, dev, usb_send=hid_send):
        self.dev = dev
        self.usb_send = usb_send
        self.definition = None

        # n.b. using OrderedDict here to make order of layout requests consistent for tests
        self.rowcol = OrderedDict()
        self.encoderpos = OrderedDict()
        self.encoder_count = 0
        self.layout = dict()
        self.encoder_layout = dict()
        self.rows = self.cols = self.layers = 0
        self.layout_labels = None
        self.layout_options = -1
        self.keys = []
        self.encoders = []
        self.vibl = False
        self.custom_keycodes = None
        self.midi = None

        self.lighting_qmk_rgblight = self.lighting_qmk_backlight = self.lighting_vialrgb = False

        # underglow
        self.underglow_brightness = self.underglow_effect = self.underglow_effect_speed = -1
        self.underglow_color = (0, 0)
        # backlight
        self.backlight_brightness = self.backlight_effect = -1
        # vialrgb
        self.rgb_mode = self.rgb_speed = self.rgb_version = self.rgb_maximum_brightness = -1
        self.rgb_hsv = (0, 0, 0)
        self.rgb_supported_effects = set()

        # layer RGB - always initialize as supported for GUI purposes
        self.layer_rgb_supported = True
        self.layer_rgb_enabled = False

        self.via_protocol = self.vial_protocol = self.keyboard_id = -1

        # ThruLoop, MIDI, Actuation, and Gaming settings
        self.thruloop_config = None
        self.midi_config = None
        self.layer_actuations = None
        self.gaming_settings = None

    def reload(self, sideload_json=None):
        """ Load information about the keyboard: number of layers, physical key layout """
        import time
        _startup_log("Keyboard reload starting...")
        reload_start = time.time()

        self.rowcol = OrderedDict()
        self.encoderpos = OrderedDict()
        self.layout = dict()
        self.encoder_layout = dict()

        _startup_log("  Loading keyboard layout definition...")
        t0 = time.time()
        self.reload_layout(sideload_json)
        _startup_log(f"  Layout loaded ({time.time()-t0:.2f}s) - {self.rows}x{self.cols} matrix")

        _startup_log("  Getting layer count...")
        t0 = time.time()
        self.reload_layers()
        _startup_log(f"  Layers: {self.layers} ({time.time()-t0:.2f}s)")

        _startup_log("  Loading macros (early)...")
        t0 = time.time()
        self.reload_macros_early()
        _startup_log(f"  Macros early done ({time.time()-t0:.2f}s)")

        _startup_log("  Loading RGB settings (persistent)...")
        t0 = time.time()
        self.reload_persistent_rgb()
        _startup_log(f"  RGB persistent done ({time.time()-t0:.2f}s)")

        _startup_log("  Loading RGB state...")
        t0 = time.time()
        self.reload_rgb()
        _startup_log(f"  RGB state done ({time.time()-t0:.2f}s)")

        _startup_log("  Checking layer RGB support...")
        t0 = time.time()
        self.reload_layer_rgb_support()
        _startup_log(f"  Layer RGB check done ({time.time()-t0:.2f}s)")

        _startup_log("  Loading QMK settings...")
        t0 = time.time()
        self.reload_settings()
        _startup_log(f"  QMK settings done ({time.time()-t0:.2f}s)")

        _startup_log("  Loading dynamic config...")
        t0 = time.time()
        self.reload_dynamic()
        _startup_log(f"  Dynamic config done ({time.time()-t0:.2f}s)")

        # based on the number of macros, tapdance, etc, this will generate global keycode arrays
        _startup_log("  Recreating keyboard keycodes...")
        t0 = time.time()
        recreate_keyboard_keycodes(self)
        _startup_log(f"  Keycodes recreated ({time.time()-t0:.2f}s)")

        # at this stage we have correct keycode info and can reload everything that depends on keycodes
        _startup_log("  Loading keymap (this may take a while)...")
        t0 = time.time()
        self.reload_keymap()
        _startup_log(f"  Keymap loaded ({time.time()-t0:.2f}s)")

        _startup_log("  Loading macros (late)...")
        t0 = time.time()
        self.reload_macros_late()
        _startup_log(f"  Macros late done ({time.time()-t0:.2f}s)")

        _startup_log("  Loading tap dance...")
        t0 = time.time()
        self.reload_tap_dance()
        _startup_log(f"  Tap dance done ({time.time()-t0:.2f}s)")

        _startup_log("  Loading combos...")
        t0 = time.time()
        self.reload_combo()
        _startup_log(f"  Combos done ({time.time()-t0:.2f}s)")

        _startup_log("  Loading key overrides...")
        t0 = time.time()
        self.reload_key_override()
        _startup_log(f"  Key overrides done ({time.time()-t0:.2f}s)")

        # Load custom tab settings
        _startup_log("  Loading ThruLoop config...")
        t0 = time.time()
        self.reload_thruloop_config()
        _startup_log(f"  ThruLoop config done ({time.time()-t0:.2f}s)")

        _startup_log("  Loading MIDI config...")
        t0 = time.time()
        self.reload_midi_config()
        _startup_log(f"  MIDI config done ({time.time()-t0:.2f}s)")

        _startup_log("  Loading layer actuations...")
        t0 = time.time()
        self.reload_layer_actuations()
        _startup_log(f"  Layer actuations done ({time.time()-t0:.2f}s)")

        _startup_log("  Loading gaming settings...")
        t0 = time.time()
        self.reload_gaming_settings()
        _startup_log(f"  Gaming settings done ({time.time()-t0:.2f}s)")

        total_time = time.time() - reload_start
        _startup_log(f"Keyboard reload complete! Total time: {total_time:.2f}s")

    def reload_layers(self):
        """ Get how many layers the keyboard has """
        self.layers = self.usb_send(self.dev, struct.pack("B", CMD_VIA_GET_LAYER_COUNT), retries=20)[1]

    def reload_via_protocol(self):
        data = self.usb_send(self.dev, struct.pack("B", CMD_VIA_GET_PROTOCOL_VERSION), retries=20)
        self.via_protocol = struct.unpack(">H", data[1:3])[0]

    def check_protocol_version(self):
        if self.via_protocol not in SUPPORTED_VIA_PROTOCOL or self.vial_protocol not in SUPPORTED_VIAL_PROTOCOL:
            raise ProtocolError()

    def reload_layout(self, sideload_json=None):
        """ Requests layout data from the current device """

        self.reload_via_protocol()

        self.sideload = False
        if sideload_json is not None:
            self.sideload = True
            payload = sideload_json
        else:
            # get keyboard identification
            data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_GET_KEYBOARD_ID), retries=20)
            self.vial_protocol, self.keyboard_id = struct.unpack("<IQ", data[0:12])

            # get the size
            data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_GET_SIZE), retries=20)
            sz = struct.unpack("<I", data[0:4])[0]

            # get the payload
            payload = b""
            block = 0
            while sz > 0:
                data = self.usb_send(self.dev, struct.pack("<BBI", CMD_VIA_VIAL_PREFIX, CMD_VIAL_GET_DEFINITION, block),
                                     retries=20)
                if sz < MSG_LEN:
                    data = data[:sz]
                payload += data
                block += 1
                sz -= MSG_LEN

            payload = json.loads(lzma.decompress(payload))

        self.check_protocol_version()

        self.definition = payload

        if "vial" in payload:
            vial = payload["vial"]
            self.vibl = vial.get("vibl", False)
            self.midi = vial.get("midi", None)

        self.layout_labels = payload["layouts"].get("labels")

        self.rows = payload["matrix"]["rows"]
        self.cols = payload["matrix"]["cols"]

        self.custom_keycodes = payload.get("customKeycodes", None)

        serial = KleSerial()
        kb = serial.deserialize(payload["layouts"]["keymap"])

        self.keys = []
        self.encoders = []

        for key in kb.keys:
            key.row = key.col = None
            key.encoder_idx = key.encoder_dir = None
            if key.labels[4] == "e":
                idx, direction = key.labels[0].split(",")
                idx, direction = int(idx), int(direction)
                key.encoder_idx = idx
                key.encoder_dir = direction
                self.encoderpos[idx] = True
                self.encoder_count = max(self.encoder_count, idx + 1)
                self.encoders.append(key)
            elif key.decal or (key.labels[0] and "," in key.labels[0]):
                row, col = 0, 0
                if key.labels[0] and "," in key.labels[0]:
                    row, col = key.labels[0].split(",")
                    row, col = int(row), int(col)
                key.row = row
                key.col = col
                self.rowcol[(row, col)] = True
                self.keys.append(key)

            # bottom right corner determines layout index and option in this layout
            key.layout_index = -1
            key.layout_option = -1
            if key.labels[8]:
                idx, opt = key.labels[8].split(",")
                key.layout_index, key.layout_option = int(idx), int(opt)

        # Save original firmware matrix dimensions for reading keymap data
        # (we may extend these dimensions if we inject additional keys)
        self.firmware_rows = self.rows
        self.firmware_cols = self.cols

        # Force encoder click buttons and sustain pedal to always be visible
        # even if the firmware doesn't report them in the layout
        # Position them based on the vial.json layout coordinates:
        # - Array 2 (y=1): Encoder 0 down at x=0, click at x=1, up at x=2
        # - Array 4 (y=3): Encoder 1 down at x=0, click at x=1, up at x=2
        # - Array 6 (y=5+0.5): Sustain pedal at x=0.5
        required_keys = [
            (5, 0, 1.0, 1.0),   # Encoder 0 click button (middle of encoder 0)
            (5, 1, 1.0, 3.0),   # Encoder 1 click button (middle of encoder 1)
            (5, 2, 0.5, 5.5),   # Sustain pedal (bottom left)
        ]

        for row, col, x_pos, y_pos in required_keys:
            if (row, col) not in self.rowcol:
                # Create a new key for this position
                new_key = Key()
                new_key.row = row
                new_key.col = col
                new_key.labels = [f"{row},{col}"] + [""] * 11
                new_key.x = x_pos
                new_key.y = y_pos
                new_key.width = 1
                new_key.height = 1
                new_key.layout_index = -1
                new_key.layout_option = -1
                new_key.decal = False

                # Add to keys list and mark as existing
                self.keys.append(new_key)
                self.rowcol[(row, col)] = True

        # Do NOT update self.rows and self.cols - keep original firmware dimensions
        # This prevents the keyboard container from expanding to include the injected keys

    def reload_keymap(self):
        """ Load current key mapping from the keyboard """

        keymap = b""
        # Use firmware dimensions (not extended dimensions) for fetching keymap data
        # If we added extra keys beyond firmware matrix, we'll handle them separately
        firmware_rows = getattr(self, 'firmware_rows', self.rows)
        firmware_cols = getattr(self, 'firmware_cols', self.cols)

        # calculate what the size of keymap will be and retrieve the entire binary buffer
        size = self.layers * firmware_rows * firmware_cols * 2
        for x in range(0, size, BUFFER_FETCH_CHUNK):
            offset = x
            sz = min(size - offset, BUFFER_FETCH_CHUNK)
            data = self.usb_send(self.dev, struct.pack(">BHB", CMD_VIA_KEYMAP_GET_BUFFER, offset, sz), retries=20)
            keymap += data[4:4+sz]

        for layer in range(self.layers):
            for row, col in self.rowcol.keys():
                # Skip keys that are outside the firmware matrix
                # (these are injected keys like encoder clicks and sustain pedal)
                if row >= firmware_rows or col >= firmware_cols:
                    # Set a default keycode (KC_TRNS - transparent) for injected keys
                    self.layout[(layer, row, col)] = "KC_TRNS"
                    continue

                # For firmware keys, determine where this (layer, row, col) is in keymap array
                offset = layer * firmware_rows * firmware_cols * 2 + row * firmware_cols * 2 + col * 2
                keycode = Keycode.serialize(struct.unpack(">H", keymap[offset:offset+2])[0])
                self.layout[(layer, row, col)] = keycode

        for layer in range(self.layers):
            for idx in self.encoderpos:
                data = self.usb_send(self.dev, struct.pack("BBBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_GET_ENCODER, layer, idx),
                                     retries=20)
                self.encoder_layout[(layer, idx, 0)] = Keycode.serialize(struct.unpack(">H", data[0:2])[0])
                self.encoder_layout[(layer, idx, 1)] = Keycode.serialize(struct.unpack(">H", data[2:4])[0])

        if self.layout_labels:
            data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_GET_KEYBOARD_VALUE, VIA_LAYOUT_OPTIONS),
                                 retries=20)
            self.layout_options = struct.unpack(">I", data[2:6])[0]

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
            data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_LIGHTING_GET_VALUE, VIALRGB_GET_INFO),
                                 retries=20)[2:]
            self.rgb_version = data[0] | (data[1] << 8)
            if self.rgb_version != 1:
                raise RuntimeError("Unsupported VialRGB protocol ({}), update your Vial version to latest"
                                   .format(self.rgb_version))
            self.rgb_maximum_brightness = data[2]

            self.rgb_supported_effects = {0}
            max_effect = 0
            while max_effect < 0xFFFF:
                data = self.usb_send(self.dev, struct.pack("<BBH", CMD_VIA_LIGHTING_GET_VALUE, VIALRGB_GET_SUPPORTED,
                                                           max_effect))[2:]
                for x in range(0, len(data), 2):
                    value = int.from_bytes(data[x:x+2], byteorder="little")
                    if value != 0xFFFF:
                        self.rgb_supported_effects.add(value)
                    max_effect = max(max_effect, value)

    def reload_rgb(self):
        if self.lighting_qmk_rgblight:
            self.underglow_brightness = self.usb_send(
                self.dev, struct.pack(">BB", CMD_VIA_LIGHTING_GET_VALUE, QMK_RGBLIGHT_BRIGHTNESS), retries=20)[2]
            self.underglow_effect = self.usb_send(
                self.dev, struct.pack(">BB", CMD_VIA_LIGHTING_GET_VALUE, QMK_RGBLIGHT_EFFECT), retries=20)[2]
            self.underglow_effect_speed = self.usb_send(
                self.dev, struct.pack(">BB", CMD_VIA_LIGHTING_GET_VALUE, QMK_RGBLIGHT_EFFECT_SPEED), retries=20)[2]
            color = self.usb_send(
                self.dev, struct.pack(">BB", CMD_VIA_LIGHTING_GET_VALUE, QMK_RGBLIGHT_COLOR), retries=20)[2:4]
            # hue, sat
            self.underglow_color = (color[0], color[1])

        if self.lighting_qmk_backlight:
            self.backlight_brightness = self.usb_send(
                self.dev, struct.pack(">BB", CMD_VIA_LIGHTING_GET_VALUE, QMK_BACKLIGHT_BRIGHTNESS), retries=20)[2]
            self.backlight_effect = self.usb_send(
                self.dev, struct.pack(">BB", CMD_VIA_LIGHTING_GET_VALUE, QMK_BACKLIGHT_EFFECT), retries=20)[2]

        if self.lighting_vialrgb:
            data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_LIGHTING_GET_VALUE, VIALRGB_GET_MODE),
                                 retries=20)[2:]
            self.rgb_mode = int.from_bytes(data[0:2], byteorder="little")
            self.rgb_speed = data[2]
            self.rgb_hsv = (data[3], data[4], data[5])

    def reload_settings(self):
        self.settings = dict()
        self.supported_settings = set()
        if self.vial_protocol < VIAL_PROTOCOL_QMK_SETTINGS:
            return
        cur = 0
        # (#11) This loop terminates only when a response contains the 0xFFFF
        # sentinel (which makes cur == 0xFFFF). A malformed or empty reply (no
        # 0xFFFF, and no qsid higher than the current cur) would leave cur
        # unchanged and spin forever, hanging the connect path. Break out when the
        # query makes no progress, with an absolute iteration backstop as well.
        _query_guard = 0
        while cur != 0xFFFF:
            _query_guard += 1
            if _query_guard > 2048:
                logging.warning("reload_settings: aborting QMK settings query (too many blocks / malformed stream)")
                break
            _prev_cur = cur
            data = self.usb_send(self.dev, struct.pack("<BBH", CMD_VIA_VIAL_PREFIX, CMD_VIAL_QMK_SETTINGS_QUERY, cur),
                                 retries=20)
            for x in range(0, len(data), 2):
                qsid = int.from_bytes(data[x:x+2], byteorder="little")
                cur = max(cur, qsid)
                if qsid != 0xFFFF:
                    self.supported_settings.add(qsid)
            if cur == _prev_cur:
                # No 0xFFFF terminator and no higher qsid this round -> stop rather
                # than re-querying the same block indefinitely.
                logging.warning("reload_settings: QMK settings query stalled (malformed response); stopping")
                break

        for qsid in self.supported_settings:
            from editor.qmk_settings import QmkSettings

            if not QmkSettings.is_qsid_supported(qsid):
                continue

            data = self.usb_send(self.dev, struct.pack("<BBH", CMD_VIA_VIAL_PREFIX, CMD_VIAL_QMK_SETTINGS_GET, qsid),
                                 retries=20)
            if data[0] == 0:
                self.settings[qsid] = QmkSettings.qsid_deserialize(qsid, data[1:])

    def set_key(self, layer, row, col, code):
        key = (layer, row, col)
        if self.layout[key] != code:
            if code == RESET_KEYCODE:
                Unlocker.unlock(self)

            # Check if this is an injected key (outside firmware matrix)
            firmware_rows = getattr(self, 'firmware_rows', self.rows)
            firmware_cols = getattr(self, 'firmware_cols', self.cols)

            if row >= firmware_rows or col >= firmware_cols:
                # This is an injected key - just update the local layout, don't send to device
                # (The firmware doesn't have this key position)
                self.layout[key] = code
            else:
                # Normal key - send to device
                self.usb_send(self.dev, struct.pack(">BBBBH", CMD_VIA_SET_KEYCODE, layer, row, col,
                                                    Keycode.deserialize(code)), retries=20)
                self.layout[key] = code

    def set_encoder(self, layer, index, direction, code):
        key = (layer, index, direction)
        if self.encoder_layout[key] != code:
            if code == RESET_KEYCODE:
                Unlocker.unlock(self)

            self.usb_send(self.dev, struct.pack(">BBBBBH", CMD_VIA_VIAL_PREFIX, CMD_VIAL_SET_ENCODER,
                                                layer, index, direction, Keycode.deserialize(code)), retries=20)
            self.encoder_layout[key] = code

    def set_layout_options(self, options):
        if self.layout_options != -1 and self.layout_options != options:
            self.layout_options = options
            self.usb_send(self.dev, struct.pack(">BBI", CMD_VIA_SET_KEYBOARD_VALUE, VIA_LAYOUT_OPTIONS, options),
                          retries=20)

    def set_qmk_rgblight_brightness(self, value):
        self.underglow_brightness = value
        self.usb_send(self.dev, struct.pack(">BBB", CMD_VIA_LIGHTING_SET_VALUE, QMK_RGBLIGHT_BRIGHTNESS, value),
                      retries=20)

    def set_qmk_rgblight_effect(self, index):
        self.underglow_effect = index
        self.usb_send(self.dev, struct.pack(">BBB", CMD_VIA_LIGHTING_SET_VALUE, QMK_RGBLIGHT_EFFECT, index),
                      retries=20)

    def set_qmk_rgblight_effect_speed(self, value):
        self.underglow_effect_speed = value
        self.usb_send(self.dev, struct.pack(">BBB", CMD_VIA_LIGHTING_SET_VALUE, QMK_RGBLIGHT_EFFECT_SPEED, value),
                      retries=20)

    def set_qmk_rgblight_color(self, h, s, v):
        self.set_qmk_rgblight_brightness(v)
        self.usb_send(self.dev, struct.pack(">BBBB", CMD_VIA_LIGHTING_SET_VALUE, QMK_RGBLIGHT_COLOR, h, s))

    def set_qmk_backlight_brightness(self, value):
        self.backlight_brightness = value
        self.usb_send(self.dev, struct.pack(">BBB", CMD_VIA_LIGHTING_SET_VALUE, QMK_BACKLIGHT_BRIGHTNESS, value))

    def set_qmk_backlight_effect(self, value):
        self.backlight_effect = value
        self.usb_send(self.dev, struct.pack(">BBB", CMD_VIA_LIGHTING_SET_VALUE, QMK_BACKLIGHT_EFFECT, value))

    def save_rgb(self):
        self.usb_send(self.dev, struct.pack(">B", CMD_VIA_LIGHTING_SAVE), retries=20)

    def save_layout(self):
        """ Serializes current layout to a binary """

        data = {"version": 1, "uid": self.keyboard_id}

        layout = []
        for l in range(self.layers):
            layer = []
            layout.append(layer)
            for r in range(self.rows):
                row = []
                layer.append(row)
                for c in range(self.cols):
                    val = self.layout.get((l, r, c), -1)
                    row.append(val)

        encoder_layout = []
        for l in range(self.layers):
            layer = []
            for e in range(self.encoder_count):
                cw = (l, e, 0)
                ccw = (l, e, 1)
                layer.append([self.encoder_layout.get(cw, -1),
                              self.encoder_layout.get(ccw, -1)])
            encoder_layout.append(layer)

        data["layout"] = layout
        data["encoder_layout"] = encoder_layout
        data["layout_options"] = self.layout_options
        data["macro"] = self.save_macro()
        data["vial_protocol"] = self.vial_protocol
        data["via_protocol"] = self.via_protocol
        data["tap_dance"] = self.save_tap_dance()
        data["combo"] = self.save_combo()
        data["key_override"] = self.save_key_override()
        data["settings"] = self.settings

        return json.dumps(data).encode("utf-8")

    def restore_layout(self, data):
        """ Restores saved layout """

        data = json.loads(data.decode("utf-8"))

        # restore keymap
        for l, layer in enumerate(data["layout"]):
            for r, row in enumerate(layer):
                for c, code in enumerate(row):
                    if (l, r, c) in self.layout:
                        self.set_key(l, r, c, Keycode.serialize(Keycode.deserialize(code)))

        # restore encoders
        for l, layer in enumerate(data["encoder_layout"]):
            for e, encoder in enumerate(layer):
                self.set_encoder(l, e, 0, Keycode.serialize(Keycode.deserialize(encoder[0])))
                self.set_encoder(l, e, 1, Keycode.serialize(Keycode.deserialize(encoder[1])))

        self.set_layout_options(data["layout_options"])
        self.restore_macros(data.get("macro"))

        self.restore_tap_dance(data.get("tap_dance", []))
        self.restore_combo(data.get("combo", []))
        self.restore_key_override(data.get("key_override", []))

        for qsid, value in data.get("settings", dict()).items():
            from editor.qmk_settings import QmkSettings

            qsid = int(qsid)
            if QmkSettings.is_qsid_supported(qsid):
                self.qmk_settings_set(qsid, value)

    def reset(self):
        self.usb_send(self.dev, struct.pack("B", 0xB))
        self.dev.close()

    def get_uid(self):
        """ Retrieve UID from the keyboard, explicitly sending a query packet """
        data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_GET_KEYBOARD_ID), retries=20)
        keyboard_id = data[4:12]
        return keyboard_id

    def get_unlock_status(self, retries=20):
        # VIA keyboards are always unlocked
        if self.vial_protocol < 0:
            return 1

        data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_GET_UNLOCK_STATUS),
                             retries=retries)
        return data[0]

    def get_unlock_in_progress(self):
        # VIA keyboards are never being unlocked
        if self.vial_protocol < 0:
            return 0

        data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_GET_UNLOCK_STATUS), retries=20)
        return data[1]

    def get_unlock_keys(self):
        """ Return keys users have to hold to unlock the keyboard as a list of rowcols """

        # VIA keyboards don't have unlock keys
        if self.vial_protocol < 0:
            return []

        data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_GET_UNLOCK_STATUS), retries=20)
        rowcol = []
        for x in range(15):
            row = data[2 + x * 2]
            col = data[3 + x * 2]
            if row != 255 and col != 255:
                rowcol.append((row, col))
        return rowcol

    def unlock_start(self):
        if self.vial_protocol < 0:
            return

        self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_UNLOCK_START), retries=20)

    def unlock_poll(self):
        if self.vial_protocol < 0:
            return b""

        data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_UNLOCK_POLL), retries=20)
        return data

    def lock(self):
        if self.vial_protocol < 0:
            return

        self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_LOCK), retries=20)

    def matrix_poll(self):
        if self.via_protocol < 0:
            return

        data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_GET_KEYBOARD_VALUE, VIA_SWITCH_MATRIX_STATE),
                             retries=3)
        return data

    def adc_matrix_poll(self, row):
        """Poll ADC values for a specific matrix row

        Args:
            row: Matrix row index (0-based)

        Returns:
            list: Raw ADC values (0-4095, 12-bit) for each column in the row, or None on error

        Protocol:
            Request: [HID_MANUFACTURER_ID, HID_SUB_ID, HID_DEVICE_ID, HID_CMD_GET_ADC_MATRIX, row, 0...]
            Response: [HID_MANUFACTURER_ID, HID_SUB_ID, HID_DEVICE_ID, HID_CMD_GET_ADC_MATRIX, row, status,
                      adc_low_0, adc_high_0, adc_low_1, adc_high_1, ...] (16-bit little-endian values)
        """
        try:
            packet = self._create_hid_packet(HID_CMD_GET_ADC_MATRIX, row, None)
            response = self.usb_send(self.dev, packet, retries=1)

            if not response or len(response) < 6:
                return None

            # Check if command was successful (status byte at index 5)
            if response[5] != 0x01:
                return None

            # Parse ADC values from response (starting at index 6)
            # Each ADC value is 2 bytes (16-bit little-endian), max 13 columns
            adc_values = []
            data_start = 6
            max_cols = min(self.cols, 13) if hasattr(self, 'cols') else 13

            for col in range(max_cols):
                offset = data_start + col * 2
                if offset + 1 < len(response):
                    # 16-bit little-endian value (raw 12-bit ADC, 0-4095)
                    adc_value = response[offset] | (response[offset + 1] << 8)
                    adc_values.append(adc_value)
                else:
                    break

            return adc_values

        except Exception:
            return None

    def distance_matrix_poll(self, keys):
        """Poll distance values (in mm * 100) for specific keys using analog_matrix_get_distance

        Args:
            keys: List of (row, col) tuples for keys to query (max 8 keys per request)

        Returns:
            dict: {(row, col): distance_mm} where distance_mm is in 0.01mm units (0-400 for 0-4.0mm),
                  or None on error

        Protocol:
            Request: [HID_MANUFACTURER_ID, HID_SUB_ID, HID_DEVICE_ID, HID_CMD_GET_DISTANCE_MATRIX,
                      num_keys, row0, col0, row1, col1, ...]
            Response: [HID_MANUFACTURER_ID, HID_SUB_ID, HID_DEVICE_ID, HID_CMD_GET_DISTANCE_MATRIX,
                      num_keys, status, dist_low_0, dist_high_0, dist_low_1, dist_high_1, ...]
                      (16-bit little-endian values in 0.01mm units)
        """
        try:
            if not keys or len(keys) > 8:
                return None

            # Build request data: [num_keys, row0, col0, row1, col1, ...]
            data = bytearray([len(keys)])
            for row, col in keys:
                data.append(row)
                data.append(col)

            packet = self._create_hid_packet(HID_CMD_GET_DISTANCE_MATRIX, len(keys), bytes(data))
            response = self.usb_send(self.dev, packet, retries=1)

            if not response or len(response) < 6:
                return None

            # Check if command was successful (status byte at index 5)
            if response[5] != 0x01:
                return None

            # Parse distance values from response (starting at index 6)
            # Each distance value is 2 bytes (16-bit little-endian), in 0.01mm units
            result = {}
            data_start = 6
            for i, (row, col) in enumerate(keys):
                offset = data_start + i * 2
                if offset + 1 < len(response):
                    # 16-bit little-endian value (distance in 0.01mm units)
                    distance = response[offset] | (response[offset + 1] << 8)
                    result[(row, col)] = distance

            return result

        except Exception:
            return None

    def calibration_debug_poll(self, keys):
        """Poll calibration values (rest, bottom, raw ADC) for specific keys

        Args:
            keys: List of (row, col) tuples for keys to query (max 4 keys per request)

        Returns:
            dict: {(row, col): {'rest': int, 'bottom': int, 'raw': int}} or None on error

        Protocol:
            Request: [HID_MANUFACTURER_ID, HID_SUB_ID, HID_DEVICE_ID, 0xD5,
                      num_keys, row0, col0, row1, col1, ...]
            Response: [header(4), num_keys, status, rest_lo, rest_hi, bottom_lo, bottom_hi, raw_lo, raw_hi, ...]
        """
        HID_CMD_CALIBRATION_DEBUG = 0xD5
        try:
            if not keys or len(keys) > 4:
                return None

            # Build request data: [num_keys, row0, col0, row1, col1, ...]
            data = bytearray([len(keys)])
            for row, col in keys:
                data.append(row)
                data.append(col)

            packet = self._create_hid_packet(HID_CMD_CALIBRATION_DEBUG, len(keys), bytes(data))
            response = self.usb_send(self.dev, packet, retries=1)

            if not response or len(response) < 6:
                return None

            # Check if command was successful (status byte at index 5)
            if response[5] != 0x01:
                return None

            # Parse calibration values from response (starting at index 6)
            # Each key has 6 bytes: rest(2) + bottom(2) + raw(2)
            result = {}
            data_start = 6
            for i, (row, col) in enumerate(keys):
                offset = data_start + i * 6
                if offset + 5 < len(response):
                    rest = response[offset] | (response[offset + 1] << 8)
                    bottom = response[offset + 2] | (response[offset + 3] << 8)
                    raw = response[offset + 4] | (response[offset + 5] << 8)
                    result[(row, col)] = {'rest': rest, 'bottom': bottom, 'raw': raw}

            return result

        except Exception:
            return None

    def velocity_matrix_poll(self, keys):
        """Poll velocity values (final MIDI velocity 0-127, travel time in ms) for specific keys

        Args:
            keys: List of (row, col) tuples for keys to query (max 6 keys per request)

        Returns:
            dict: {(row, col): {'velocity': int, 'travel_time_ms': int, 'raw_velocity': int}}
                  or None on error

        Protocol:
            Request: [HID_MANUFACTURER_ID, HID_SUB_ID, HID_DEVICE_ID, 0xD3,
                      num_keys, row0, col0, row1, col1, ...]
            Response: [header(4), num_keys, status, vel0, time_lo0, time_hi0, raw0, ...]
        """
        try:
            if not keys or len(keys) > 6:
                return None

            # Build request data: [num_keys, row0, col0, row1, col1, ...]
            data = bytearray([len(keys)])
            for row, col in keys:
                data.append(row)
                data.append(col)

            packet = self._create_hid_packet(HID_CMD_VELOCITY_MATRIX_POLL, len(keys), bytes(data))
            response = self.usb_send(self.dev, packet, retries=1)

            if not response or len(response) < 6:
                return None

            # Check if command was successful (status byte at index 5)
            if response[5] != 0x01:
                return None

            # Parse velocity values from response (starting at index 6)
            # Each key has 4 bytes: velocity(1) + travel_time(2) + raw_velocity(1)
            result = {}
            data_start = 6
            for i, (row, col) in enumerate(keys):
                offset = data_start + i * 4
                if offset + 3 < len(response):
                    velocity = response[offset]
                    travel_time_ms = response[offset + 1] | (response[offset + 2] << 8)
                    raw_velocity = response[offset + 3]
                    result[(row, col)] = {
                        'velocity': velocity,
                        'travel_time_ms': travel_time_ms,
                        'raw_velocity': raw_velocity
                    }

            return result

        except Exception:
            return None

    def get_velocity_time_settings(self):
        """Get global velocity min/max time settings from keyboard

        Returns:
            dict: {'min_time': int, 'max_time': int} in milliseconds, or None on error
            - min_time: Time for slowest press = minimum velocity (10-400ms, default 100)
            - max_time: Time for fastest press = maximum velocity (5-100ms, default 10)

        Protocol:
            Request: [HID_MANUFACTURER_ID, HID_SUB_ID, HID_DEVICE_ID, 0xD4, _, 0 (GET)]
            Response: [header(4), status, min_lo, min_hi, max_lo, max_hi]
        """
        try:
            # sub_cmd = 0 for GET
            data = bytearray([0])  # GET command
            packet = self._create_hid_packet(HID_CMD_VELOCITY_TIME_SETTINGS, 0, bytes(data))
            response = self.usb_send(self.dev, packet, retries=1)

            if not response or len(response) < 9:
                return None

            # Check if command was successful (status byte at index 4)
            if response[4] != 0x01:
                return None

            # Parse min/max time values
            min_time = response[5] | (response[6] << 8)
            max_time = response[7] | (response[8] << 8)

            return {
                'min_time': min_time,
                'max_time': max_time
            }

        except Exception:
            return None

    def set_velocity_time_settings(self, min_time, max_time):
        """Set global velocity min/max time settings

        Args:
            min_time: Time in ms for slowest press = minimum velocity (10-400ms)
            max_time: Time in ms for fastest press = maximum velocity (5-100ms)
            NOTE: max_time must be less than min_time

        Returns:
            bool: True on success, False on failure

        Protocol:
            Request: [HID_MANUFACTURER_ID, HID_SUB_ID, HID_DEVICE_ID, 0xD4, _, 1 (SET),
                      min_lo, min_hi, max_lo, max_hi]
            Response: [header(4), status, min_lo, min_hi, max_lo, max_hi]
        """
        try:
            # Validate inputs
            if min_time < 10 or min_time > 400:
                return False
            if max_time < 5 or max_time > 100:
                return False
            if max_time >= min_time:
                return False

            # sub_cmd = 1 for SET
            data = bytearray([
                1,  # SET command
                min_time & 0xFF,
                (min_time >> 8) & 0xFF,
                max_time & 0xFF,
                (max_time >> 8) & 0xFF
            ])
            packet = self._create_hid_packet(HID_CMD_VELOCITY_TIME_SETTINGS, 1, bytes(data))
            response = self.usb_send(self.dev, packet, retries=1)

            # Check for success response
            return response and len(response) >= 5 and response[4] == 0x01

        except Exception:
            return False

    def save_velocity_time_settings(self):
        """Save current velocity time settings to EEPROM for persistence

        Returns:
            bool: True on success, False on failure

        Protocol:
            Request: [HID_MANUFACTURER_ID, HID_SUB_ID, HID_DEVICE_ID, 0xD4, _, 2 (SAVE)]
            Response: [header(4), status]
        """
        try:
            # sub_cmd = 2 for SAVE
            data = bytearray([2])  # SAVE command
            packet = self._create_hid_packet(HID_CMD_VELOCITY_TIME_SETTINGS, 2, bytes(data))
            response = self.usb_send(self.dev, packet, retries=1)

            # Check for success response
            return response and len(response) >= 5 and response[4] == 0x01

        except Exception:
            return False

    def qmk_settings_set(self, qsid, value):
        from editor.qmk_settings import QmkSettings
        self.settings[qsid] = value
        data = self.usb_send(self.dev, struct.pack("<BBH", CMD_VIA_VIAL_PREFIX, CMD_VIAL_QMK_SETTINGS_SET, qsid)
                             + QmkSettings.qsid_serialize(qsid, value),
                             retries=20)
        return data[0]

    def qmk_settings_reset(self):
        self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_QMK_SETTINGS_RESET))

    def _vialrgb_set_mode(self):
        self.usb_send(self.dev, struct.pack("BBHBBBB", CMD_VIA_LIGHTING_SET_VALUE, VIALRGB_SET_MODE,
                                            self.rgb_mode, self.rgb_speed,
                                            self.rgb_hsv[0], self.rgb_hsv[1], self.rgb_hsv[2]))

    def set_vialrgb_brightness(self, value):
        self.rgb_hsv = (self.rgb_hsv[0], self.rgb_hsv[1], value)
        self._vialrgb_set_mode()

    def set_vialrgb_speed(self, value):
        self.rgb_speed = value
        self._vialrgb_set_mode()

    def set_vialrgb_mode(self, value):
        self.rgb_mode = value
        self._vialrgb_set_mode()

    def set_vialrgb_color(self, h, s, v):
        self.rgb_hsv = (h, s, v)
        self._vialrgb_set_mode()

    def reload_layer_rgb_support(self):
        """Check if keyboard supports per-layer RGB and get initial status"""
        self.layer_rgb_supported = True
        
        try:
            data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_LAYER_RGB_GET_STATUS), retries=20)
            self.layer_rgb_enabled = bool(data[2])
            return True
        except:
            self.layer_rgb_enabled = False
            return True

    def get_layer_rgb_status(self):
        """Get current per-layer RGB status"""
        try:
            data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_LAYER_RGB_GET_STATUS), retries=20)
            return data[2:]
        except:
            # Comm failure: report "unknown" instead of a fabricated status the
            # caller would mistake for real device state.
            return None

    def set_layer_rgb_enable(self, enabled):
        """Enable or disable per-layer RGB functionality"""
        try:
            data = self.usb_send(self.dev, struct.pack("BBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_LAYER_RGB_ENABLE, int(enabled)), retries=20)
            success = data[2] == 0x01
            if success:
                self.layer_rgb_enabled = enabled
            return success
        except:
            # The write never reached the device — do not report success.
            return False

    def save_rgb_to_layer(self, layer):
        """Save current RGB settings to specified layer"""
        try:
            data = self.usb_send(self.dev, struct.pack("BBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_LAYER_RGB_SAVE, layer), retries=20)
            return data[2] == 0x01
        except:
            # The write never reached the device — do not report success.
            return False

    def load_rgb_from_layer(self, layer):
        """Load RGB settings from specified layer"""
        try:
            data = self.usb_send(self.dev, struct.pack("BBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_LAYER_RGB_LOAD, layer), retries=20)
            return data[2] == 0x01
        except:
            return True
            
    def get_custom_slot_config(self, slot, from_eeprom=True):
        """Get all parameters for a custom animation slot"""
        try:
            if slot >= 50:
                return None
            
            source = 1 if from_eeprom else 0
            data = self.usb_send(self.dev, struct.pack("BBBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_CUSTOM_ANIM_GET_ALL, slot, source), retries=20)
            if data and len(data) > 2 and data[0] == 0x01:
                return data[3:19]
            return None
        except Exception as e:
            return None

    def get_custom_slot_ram_state(self, slot):
        """Get current RAM state for a custom animation slot"""
        return self.get_custom_slot_config(slot, from_eeprom=False)

    def set_custom_slot_parameter(self, slot, param_index, value):
        """Set a single parameter for a custom animation slot"""
        try:
            if slot >= 50 or param_index >= 15:
                return False
                
            data = self.usb_send(self.dev, struct.pack("BBBBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_CUSTOM_ANIM_SET_PARAM, slot, param_index, value), retries=20)
            return data and len(data) > 0 and data[0] == 0x01
        except Exception as e:
            return False

    def activate_custom_slot_preview(self, slot):
        """Ask the device to render (live-preview) a custom-animation slot.
        Non-persistent (firmware uses rgb_matrix_mode_noeeprom), so a power
        cycle restores the user's saved RGB mode. Slots 0..48 only."""
        try:
            if slot < 0 or slot >= 49:
                return False
            data = self.usb_send(self.dev, struct.pack("BBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_CUSTOM_ANIM_ACTIVATE_SLOT, slot), retries=20)
            return data and len(data) > 0 and data[0] == 0x01
        except Exception:
            return False

    def set_custom_slot_all_parameters(self, slot, live_pos, macro_pos, live_anim, macro_anim, flags,
                                     background, effect_hue, color_type, enabled, bg_brightness, live_speed, macro_speed,
                                     live_brightness=255, macro_brightness=255, background_speed=128, effect_sat=255):
        """Set all parameters for a custom animation slot"""
        try:
            if slot >= 50:
                return False

            params = [slot, live_pos, macro_pos, live_anim, macro_anim, flags,
                     background, effect_hue, color_type, enabled, bg_brightness, live_speed, macro_speed,
                     live_brightness, macro_brightness, background_speed, effect_sat]
            data = self.usb_send(self.dev, struct.pack("BB" + "B" * len(params), CMD_VIA_VIAL_PREFIX, CMD_VIAL_CUSTOM_ANIM_SET_ALL, *params), retries=20)
            return data and len(data) > 0 and data[0] == 0x01
            
        except Exception as e:
            return False
            
    def save_custom_slot(self, slot):
        """Save a specific custom slot configuration to EEPROM"""
        try:
            if slot >= 50:
                return False
                
            data = self.usb_send(self.dev, struct.pack("BBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_CUSTOM_ANIM_SAVE, slot), retries=20)
            return data and len(data) > 0 and data[0] == 0x01
        except Exception as e:
            return False     

    def save_custom_slots(self):
        """Save all custom slot configurations to EEPROM"""
        try:
            data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_CUSTOM_ANIM_SAVE), retries=20)
            return data and len(data) > 0 and data[0] == 0x01
        except Exception as e:
            return False

    def reset_custom_slot(self, slot):
        """Reset a custom slot to default values"""
        try:
            if slot >= 50:
                return False
                
            data = self.usb_send(self.dev, struct.pack("BBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_CUSTOM_ANIM_RESET_SLOT, slot), retries=20)
            return data and len(data) > 0 and data[0] == 0x01
        except Exception as e:
            return False
            
    def rescan_led_positions(self):
        """Rescan LED positions on the keyboard (reads from EEPROM - slow)"""
        try:
            data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_CUSTOM_ANIM_RESCAN_LEDS), retries=20)
            return data and len(data) > 0 and data[0] == 0x01
        except Exception as e:
            return False

    def send_keymap_for_ram_rescan(self):
        """Send current keymap from GUI RAM to firmware and trigger rescan.

        Instead of the firmware reading keycodes from slow I2C EEPROM,
        we send the keymap data the GUI already has in self.layout directly
        to the firmware's RAM cache, then trigger a rescan from that cache.
        This avoids ~5,040 I2C byte reads that would block the main loop.
        """
        try:
            firmware_rows = getattr(self, 'firmware_rows', self.rows)
            firmware_cols = getattr(self, 'firmware_cols', self.cols)

            # Send keymap in chunks: 1 chunk = 1 row of 1 layer (14 keycodes × 2 bytes = 28 bytes)
            # chunk_index = layer * firmware_rows + row
            for layer in range(self.layers):
                for row in range(firmware_rows):
                    chunk_index = layer * firmware_rows + row
                    # Build 28 bytes of keycode data for this row
                    keycode_data = bytearray()
                    for col in range(firmware_cols):
                        key = (layer, row, col)
                        code_str = self.layout.get(key, "KC_NO")
                        code_int = Keycode.deserialize(code_str)
                        keycode_data += struct.pack(">H", code_int)

                    # Pad if fewer than 14 cols (shouldn't happen for 5×14, but be safe)
                    while len(keycode_data) < 28:
                        keycode_data += b'\x00\x00'

                    # Send chunk: [0xFE, 0xE9, 0x00 (sub_cmd), chunk_index, data[28]]
                    msg = struct.pack("BBBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_KEYMAP_RAM_RESCAN, 0x00, chunk_index)
                    msg += bytes(keycode_data[:28])
                    data = self.usb_send(self.dev, msg, retries=5)
                    if not data or data[0] != 0x01:
                        return False

            # All chunks sent - trigger RAM-based rescan
            data = self.usb_send(self.dev, struct.pack("BBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_KEYMAP_RAM_RESCAN, 0x01), retries=5)
            return data and len(data) > 0 and data[0] == 0x01
        except Exception as e:
            return False

    def get_custom_animation_status(self):
        """Get custom animation status including active slot.

        Returns None on comm failure — callers must treat that as "unknown"
        and skip, not act on it. The old fabricated fake-success buffer here
        made the GUI believe slot 0 was active after a failed read, which
        then drove real RGB writes to the device on connect.
        """
        try:
            data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_CUSTOM_ANIM_GET_STATUS), retries=20)
            if data and len(data) >= 12:
                return data[1:]
            return None
        except Exception as e:
            return None

    def get_current_custom_slot(self):
        """Get the currently active custom slot number"""
        try:
            status = self.get_custom_animation_status()
            if status is not None and len(status) > 1:
                return status[1]
                
            current_mode = self.rgb_mode
            if 57 <= current_mode <= 105:
                return current_mode - 57
            if current_mode in [106, 107, 108, 109, 110, 111, 112, 113, 114]:
                return 49
            return 0
        except Exception as e:
            return 0
         
    def get_active_layer(self):
        """Return the keyboard's currently-active (highest) layer, or None if the
        firmware doesn't support the query or on a comms error.
        Response: [header(4), status=0x01, active_layer]."""
        try:
            packet = self._create_hid_packet(HID_CMD_GET_ACTIVE_LAYER, 0, None)
            response = self.usb_send(self.dev, packet, retries=1)
            if response and len(response) >= 6 and response[4] == 0x01:
                return response[5]
        except Exception:
            pass
        return None

    def get_firmware_version(self):
        """Return the firmware version as a (major, minor, patch) tuple, or None
        if the firmware predates this command / on a comms error.
        Response: [header(4), status=0x01, major, minor, patch]."""
        try:
            packet = self._create_hid_packet(HID_CMD_GET_FIRMWARE_VERSION, 0, None)
            response = self.usb_send(self.dev, packet, retries=3)
            if response and len(response) >= 8 and response[4] == 0x01:
                return (response[5], response[6], response[7])
        except Exception:
            pass
        return None

    def _create_hid_packet(self, command, macro_num, data):
        """Create a properly formatted 32-byte HID packet"""
        packet = bytearray(HID_PACKET_SIZE)
        packet[0] = HID_MANUFACTURER_ID
        packet[1] = HID_SUB_ID
        packet[2] = HID_DEVICE_ID
        packet[3] = command
        packet[4] = macro_num
        packet[5] = 0  # Status
        
        if data:
            data_len = min(len(data), HID_PACKET_SIZE - 6)
            packet[6:6+data_len] = data[:data_len]
        
        return bytes(packet)

    def get_lcd_theme(self):
        """Get the keyboard's current global LCD colour theme index.

        Returns the theme index (int) or None on failure. Firmware response
        layout (raw_hid_receive_kb family): status@4, current index@5, count@6.
        """
        try:
            # sub-cmd 0 = GET (carried in the macro_num/byte-4 field)
            packet = self._create_hid_packet(HID_CMD_LCD_THEME, 0, None)
            data = self.usb_send(self.dev, packet, retries=3)
            if not data or len(data) < 7 or data[3] != HID_CMD_LCD_THEME:
                return None
            if data[4] != 0:
                return None
            # Firmware that predates the via.c 0xFE routing fix rejects this
            # command with an error ECHO: it keeps data[4]=0 (our GET sub-cmd)
            # and forces data[5]=1, which parsed as "theme 1". The real handler
            # always reports the theme count (>=1) at data[6]; the echo carries
            # our request's 0 there — use that to tell them apart.
            if data[6] == 0:
                return None
            return data[5]
        except Exception:
            return None

    def set_lcd_theme(self, theme_index):
        """Set the keyboard's global LCD colour theme (applies + persists)."""
        try:
            # sub-cmd 1 = SET; payload byte 0 = theme index
            packet = self._create_hid_packet(HID_CMD_LCD_THEME, 1, [theme_index & 0xFF])
            data = self.usb_send(self.dev, packet, retries=3)
            return bool(data) and len(data) > 4 and data[4] == 0
        except Exception:
            return False

    def set_thruloop_config(self, loop_config_data):
        """Set basic ThruLoop configuration (includes 8 restart CCs)"""
        try:
            packet = self._create_hid_packet(HID_CMD_SET_LOOP_CONFIG, 0, loop_config_data)
            data = self.usb_send(self.dev, packet, retries=20)
            return data and len(data) > 0 and data[5] == 0
        except Exception as e:
            return False

    def set_thruloop_main_ccs(self, cc_values):
        """Set main loop CC values for all 8 loops (sent in 2 banks of 4)"""
        try:
            # Bank 0: loops 1-4 (20 bytes: 5 arrays × 4 CCs)
            bank0 = cc_values[:20]
            packet = self._create_hid_packet(HID_CMD_SET_MAIN_LOOP_CCS, 0, bank0)
            data = self.usb_send(self.dev, packet, retries=20)
            if not (data and len(data) > 0 and data[5] == 0):
                return False
            # Bank 1: loops 5-8 (20 bytes: 5 arrays × 4 CCs)
            bank1 = cc_values[20:40] if len(cc_values) > 20 else [128] * 20
            packet = self._create_hid_packet(HID_CMD_SET_MAIN_LOOP_CCS, 1, bank1)
            data = self.usb_send(self.dev, packet, retries=20)
            return data and len(data) > 0 and data[5] == 0
        except Exception as e:
            return False

    def set_thruloop_overdub_ccs(self, cc_values):
        """Set overdub CC values for all 8 loops (sent in 2 banks of 4)"""
        try:
            # Bank 0: loops 1-4 (24 bytes: 6 arrays × 4 CCs)
            bank0 = cc_values[:24]
            packet = self._create_hid_packet(HID_CMD_SET_OVERDUB_CCS, 0, bank0)
            data = self.usb_send(self.dev, packet, retries=20)
            if not (data and len(data) > 0 and data[5] == 0):
                return False
            # Bank 1: loops 5-8 (24 bytes: 6 arrays × 4 CCs)
            bank1 = cc_values[24:48] if len(cc_values) > 24 else [128] * 24
            packet = self._create_hid_packet(HID_CMD_SET_OVERDUB_CCS, 1, bank1)
            data = self.usb_send(self.dev, packet, retries=20)
            return data and len(data) > 0 and data[5] == 0
        except Exception as e:
            return False

    def set_thruloop_navigation(self, nav_data):
        """Set ThruLoop navigation configuration"""
        try:
            packet = self._create_hid_packet(HID_CMD_SET_NAVIGATION_CONFIG, 0, nav_data)
            data = self.usb_send(self.dev, packet, retries=20)
            return data and len(data) > 0 and data[5] == 0
        except Exception as e:
            return False

    @_hid_transaction
    def get_thruloop_config(self):
        """Get all ThruLoop configuration using multi-packet collection"""
        try:
            # Send request for all config
            packet = self._create_hid_packet(HID_CMD_GET_ALL_CONFIG, 0, None)
            response = self.usb_send(self.dev, packet, retries=20)
            
            if not response or len(response) == 0 or response[5] != 0:
                return None
            
            # Collect response packets using proper HID read method
            # Banked commands (main/overdub CCs) send 2 packets each, so expect 6 total
            packets = {}
            expected_commands = [HID_CMD_SET_LOOP_CONFIG, HID_CMD_SET_MAIN_LOOP_CCS,
                               HID_CMD_SET_OVERDUB_CCS, HID_CMD_SET_NAVIGATION_CONFIG]
            expected_packet_count = 6  # config + 2x main CCs + 2x overdub CCs + nav

            # The usb_send() above already consumed the first of the 6 response
            # packets — record it, otherwise the collector can never complete.
            if response and len(response) >= 4 and response[0] == HID_MANUFACTURER_ID:
                cmd = response[3]
                if cmd in expected_commands:
                    packets[cmd] = [response]

            # Try multiple times to collect all expected packets
            for attempt in range(30):
                try:
                    # Use the device's read method directly
                    if hasattr(self.dev, 'read'):
                        data = self.dev.read(32, timeout_ms=100)
                    else:
                        # Fallback: try to read using get_feature
                        data = self.dev.get_feature_report(0, 32)

                    if data and len(data) >= 4 and data[0] == HID_MANUFACTURER_ID:
                        cmd = data[3]
                        if cmd in expected_commands:
                            # Store as list to handle banked packets (same cmd, different bank)
                            if cmd not in packets:
                                packets[cmd] = []
                            packets[cmd].append(data)

                    total_collected = sum(len(v) for v in packets.values())
                    if total_collected >= expected_packet_count:
                        break
                        
                except:
                    # If direct read fails, try a small delay and continue
                    time.sleep(0.01)
                    continue
            
            # If the response set is incomplete, fail the read rather than
            # parsing partial data. (A previous "fallback" here re-sent the
            # expected commands as zero-payload packets — but these are SET
            # commands, so the firmware executed them as real writes and
            # persisted zeroed loop config to EEPROM. Never send SETs to read.)
            total_collected = sum(len(v) for v in packets.values()) if packets else 0
            if total_collected < expected_packet_count:
                return None

            # Parse collected packets (8-loop banked protocol)
            config = {}

            if HID_CMD_SET_LOOP_CONFIG in packets:
                data = packets[HID_CMD_SET_LOOP_CONFIG][0][6:]
                config['loopChannel'] = data[0]
                config['syncMidi'] = data[1] != 0
                config['alternateRestart'] = data[2] != 0
                config['restartCCs'] = list(data[3:11])  # 8 restart CCs

            # Main CCs may arrive as 2 banked packets; collect both banks
            main_ccs_bank0 = None
            main_ccs_bank1 = None
            overdub_ccs_bank0 = None
            overdub_ccs_bank1 = None

            for pkt in packets.get(HID_CMD_SET_MAIN_LOOP_CCS, []):
                bank = pkt[4]  # macro_num field = bank
                pkt_data = pkt[6:]
                if bank == 0:
                    main_ccs_bank0 = list(pkt_data[:20])
                elif bank == 1:
                    main_ccs_bank1 = list(pkt_data[:20])

            for pkt in packets.get(HID_CMD_SET_OVERDUB_CCS, []):
                bank = pkt[4]
                pkt_data = pkt[6:]
                if bank == 0:
                    overdub_ccs_bank0 = list(pkt_data[:24])
                elif bank == 1:
                    overdub_ccs_bank1 = list(pkt_data[:24])

            # Combine banks into full 8-loop arrays
            if main_ccs_bank0:
                config['mainCCs'] = main_ccs_bank0 + (main_ccs_bank1 or [128] * 20)
            if overdub_ccs_bank0:
                config['overdubCCs'] = overdub_ccs_bank0 + (overdub_ccs_bank1 or [128] * 24)

            if HID_CMD_SET_NAVIGATION_CONFIG in packets:
                nav_pkt = packets[HID_CMD_SET_NAVIGATION_CONFIG][0]
                data = nav_pkt[6:]
                config['separateLoopChopCC'] = data[0] != 0
                config['masterCC'] = data[1]
                config['navCCs'] = list(data[2:10])
                
            return config if config else None
            
        except Exception as e:
            return None

    def reset_thruloop_config(self):
        """Reset ThruLoop configuration to defaults"""
        try:
            packet = self._create_hid_packet(HID_CMD_RESET_LOOP_CONFIG, 0, None)
            data = self.usb_send(self.dev, packet, retries=20)
            return data and len(data) > 0 and data[5] == 0
        except Exception as e:
            return False

    def clear_all_loops(self):
        """Clear all loop content (equivalent to holding all macro buttons)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            packet = self._create_hid_packet(HID_CMD_CLEAR_ALL_LOOPS, 0, None)
            data = self.usb_send(self.dev, packet, retries=20)
            return data and len(data) > 0 and data[5] == 0
        except Exception as e:
            return False

    def set_midi_config(self, config_data):
        """Set MIDIswitch basic configuration"""
        try:
            packet = self._create_hid_packet(HID_CMD_SET_KEYBOARD_CONFIG, 0, config_data)
            data = self.usb_send(self.dev, packet, retries=20)
            return data and len(data) > 0 and data[5] == 0
        except Exception as e:
            return False

    def set_midi_advanced_config(self, advanced_data):
        """Set MIDIswitch advanced configuration"""
        try:
            packet = self._create_hid_packet(HID_CMD_SET_KEYBOARD_CONFIG_ADVANCED, 0, advanced_data)
            data = self.usb_send(self.dev, packet, retries=20)
            return data and len(data) > 0 and data[5] == 0
        except Exception as e:
            return False

    @_hid_transaction
    def set_keyboard_param_single(self, param_id, value):
        """Set individual keyboard parameter (real-time update)

        Args:
            param_id: Parameter ID (PARAM_* constant)
            value: Parameter value (int or bytes)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Build data payload: [param_id, value_bytes...]
            if param_id in [PARAM_VELOCITY_SENSITIVITY, PARAM_CC_SENSITIVITY]:
                # 4-byte parameters
                data = bytearray([param_id]) + struct.pack('<I', value)
            elif param_id in [PARAM_VIBRATO_DECAY_TIME, PARAM_MIN_PRESS_TIME, PARAM_MAX_PRESS_TIME,
                             PARAM_MACRO_LOOP_MODE, PARAM_MACRO_PER_SYNC]:
                # 16-bit parameters (little-endian)
                data = bytearray([param_id, value & 0xFF, (value >> 8) & 0xFF])
            elif param_id in [PARAM_TRANSPOSE_NUMBER, PARAM_TRANSPOSE_NUMBER2, PARAM_TRANSPOSE_NUMBER3]:
                # Signed byte parameters
                data = bytearray([param_id, value & 0xFF])
            else:
                # Standard 1-byte parameters
                data = bytearray([param_id, value])

            packet = self._create_hid_packet(HID_CMD_SET_KEYBOARD_PARAM_SINGLE, 0, data)

            # Retry logic: 4 retries with 100ms delay. A retry re-SENDS only
            # when no response arrived at all. If a response arrives but isn't
            # the 0xE8 echo (a stale packet from an earlier timed-out command),
            # keep READING for the real reply instead of re-sending — each
            # duplicate send executes the SET again on the firmware and queues
            # another orphan response, compounding the stream desync.
            for attempt in range(5):  # 1 initial + 4 retries = 5 total attempts
                try:
                    response = self.usb_send(self.dev, packet, retries=1)
                    for _ in range(3):
                        if response and len(response) >= 6 and \
                                response[3] == HID_CMD_SET_KEYBOARD_PARAM_SINGLE:
                            break
                        response = bytes(self.dev.read(MSG_LEN, timeout_ms=500))
                    if response and len(response) >= 6 and \
                            response[3] == HID_CMD_SET_KEYBOARD_PARAM_SINGLE:
                        return response[5] == 1

                    # If not last attempt, wait before retry
                    if attempt < 4:
                        time.sleep(0.1)  # 100ms delay
                except Exception as e:
                    if attempt < 4:
                        time.sleep(0.1)
                    continue

            return False

        except Exception as e:
            return False

    def get_drum_keybinds(self):
        """Get the global default drum settings (drum machine voice bindings).

        Returns:
            (notes, velocities, channel) where notes/velocities are 12-element
            lists and channel is 0-15; or None on failure.
        """
        try:
            packet = self._create_hid_packet(HID_CMD_DRUM_KEYBINDS_GET, 0, None)
            response = self.usb_send(self.dev, packet, retries=5)
            if (response and len(response) >= 31 and
                    response[0] == HID_MANUFACTURER_ID and response[4] == 0x01):
                notes = list(response[6:6 + DRUM_KEYBIND_VOICE_COUNT])
                vels = list(response[18:18 + DRUM_KEYBIND_VOICE_COUNT])
                channel = response[30]
                return notes, vels, channel
            return None
        except Exception:
            return None

    def set_drum_keybinds(self, notes, velocities):
        """Set the global default drum keybinds.

        The firmware applies the new default, propagates it to every drum slot
        whose bindings still matched the previous default (uncustomized slots),
        and persists everything to EEPROM.

        Args:
            notes: 12-element list of MIDI notes (0-127)
            velocities: 12-element list of velocities (0-127)

        Returns:
            bool: True on success.
        """
        try:
            data = bytearray(DRUM_KEYBIND_VOICE_COUNT * 2)
            for i in range(DRUM_KEYBIND_VOICE_COUNT):
                data[i] = int(notes[i]) & 0x7F
                data[DRUM_KEYBIND_VOICE_COUNT + i] = int(velocities[i]) & 0x7F
            packet = self._create_hid_packet(HID_CMD_DRUM_KEYBINDS_SET, 0, data)
            response = self.usb_send(self.dev, packet, retries=5)
            return bool(response and len(response) >= 5 and response[4] == 0x01)
        except Exception:
            return False

    def set_drum_default_channel(self, channel):
        """Set the global default drum channel; forces ALL drum slots to it.

        Args:
            channel: MIDI channel 0-15 (0 = channel 1, 9 = channel 10).

        Returns:
            bool: True on success.
        """
        try:
            data = bytearray(1)
            data[0] = int(channel) & 0x0F
            # macro_num (data[4]) = 1 selects the "default channel" SET sub-mode.
            packet = self._create_hid_packet(HID_CMD_DRUM_KEYBINDS_SET, 1, data)
            response = self.usb_send(self.dev, packet, retries=5)
            return bool(response and len(response) >= 5 and response[4] == 0x01)
        except Exception:
            return False

    def reset_drum_keybinds(self):
        """Reset ALL drum slots + the global default to GM factory.

        Returns:
            (notes, velocities, channel) of the new (factory) global default,
            or None.
        """
        try:
            packet = self._create_hid_packet(HID_CMD_DRUM_KEYBINDS_RESET, 0, None)
            response = self.usb_send(self.dev, packet, retries=5)
            if (response and len(response) >= 31 and
                    response[0] == HID_MANUFACTURER_ID and response[4] == 0x01):
                notes = list(response[6:6 + DRUM_KEYBIND_VOICE_COUNT])
                vels = list(response[18:18 + DRUM_KEYBIND_VOICE_COUNT])
                channel = response[30]
                return notes, vels, channel
            return None
        except Exception:
            return None

    def get_drum_extra_notes(self):
        """Get the 16 extra DrumLIVE-only voicing notes (notes only).

        Returns:
            list of 16 MIDI notes (0-127), or None on failure.
        """
        try:
            packet = self._create_hid_packet(HID_CMD_DRUM_KEYBINDS_GET,
                                              DRUM_KEYBINDS_SUBMODE_EXTRAS, None)
            response = self.usb_send(self.dev, packet, retries=5)
            if (response and len(response) >= 6 + DRUM_EXTRA_VOICE_COUNT and
                    response[0] == HID_MANUFACTURER_ID and response[4] == 0x01):
                return list(response[6:6 + DRUM_EXTRA_VOICE_COUNT])
            return None
        except Exception:
            return None

    def set_drum_extra_notes(self, notes):
        """Set the 16 extra DrumLIVE-only voicing notes. Persisted on the device.

        Args:
            notes: 16-element list of MIDI notes (0-127).

        Returns:
            bool: True on success.
        """
        try:
            data = bytearray(DRUM_EXTRA_VOICE_COUNT)
            for i in range(DRUM_EXTRA_VOICE_COUNT):
                data[i] = int(notes[i]) & 0x7F
            packet = self._create_hid_packet(HID_CMD_DRUM_KEYBINDS_SET,
                                             DRUM_KEYBINDS_SUBMODE_EXTRAS, data)
            response = self.usb_send(self.dev, packet, retries=5)
            return bool(response and len(response) >= 5 and response[4] == 0x01)
        except Exception:
            return False

    def save_midi_slot(self, slot, config_data):
        """Save MIDIswitch configuration to slot"""
        try:
            slot_data = [slot] + list(config_data)
            packet = self._create_hid_packet(HID_CMD_SAVE_KEYBOARD_SLOT, 0, slot_data)
            data = self.usb_send(self.dev, packet, retries=20)
            return data and len(data) > 0 and data[5] == 0
        except Exception as e:
            return False

    def load_midi_slot(self, slot):
        """Load MIDIswitch configuration from slot"""
        try:
            packet = self._create_hid_packet(HID_CMD_LOAD_KEYBOARD_SLOT, 0, [slot])
            data = self.usb_send(self.dev, packet, retries=20)
            return data and len(data) > 0 and data[5] == 0
        except Exception as e:
            return False

    def reset_midi_config(self):
        """Reset MIDIswitch configuration to defaults"""
        try:
            packet = self._create_hid_packet(HID_CMD_RESET_KEYBOARD_CONFIG, 0, None)
            data = self.usb_send(self.dev, packet, retries=20)
            return data and len(data) > 0 and data[5] == 0
        except Exception as e:
            return False

    @_hid_transaction
    def get_midi_config(self):
        """Get MIDIswitch configuration using multi-packet collection"""
        try:
            # Send request for keyboard config
            packet = self._create_hid_packet(HID_CMD_GET_KEYBOARD_CONFIG, 0, None)
            response = self.usb_send(self.dev, packet, retries=20)

            if not response or len(response) == 0 or response[5] != 0:
                return None

            # Collect response packets using proper HID read method
            # IMPORTANT: Initialize with the first response packet!
            packets = {}
            expected_commands = [HID_CMD_GET_KEYBOARD_CONFIG, HID_CMD_SET_KEYBOARD_CONFIG_ADVANCED]

            # Add the initial response to packets if it's valid
            if response and len(response) >= 4 and response[0] == HID_MANUFACTURER_ID:
                cmd = response[3]
                if cmd in expected_commands:
                    packets[cmd] = response
            
            # Try multiple times to collect all expected packets
            for attempt in range(20):
                try:
                    # Use the device's read method directly
                    if hasattr(self.dev, 'read'):
                        data = self.dev.read(32, timeout_ms=100)
                    else:
                        # Fallback: try to read using get_feature
                        data = self.dev.get_feature_report(0, 32)
                    
                    if data and len(data) >= 4 and data[0] == HID_MANUFACTURER_ID:
                        cmd = data[3]
                        if cmd in expected_commands:
                            packets[cmd] = data
                            
                    if len(packets) >= 2:
                        break
                        
                except:
                    # If direct read fails, try a small delay and continue
                    time.sleep(0.01)
                    continue
            
            # If the response set is incomplete, fail the read rather than
            # parsing partial data. (A previous "fallback" here re-sent the
            # expected commands as zero-payload packets — but 0xBB is a SET
            # command, so the firmware executed it as a real settings write,
            # zeroing and persisting the user's advanced MIDI configuration.
            # Never send SETs to read.)
            if len(packets) < 2:
                return None

            # Parse collected packets
            config = {}
            
            if HID_CMD_GET_KEYBOARD_CONFIG in packets:
                data = packets[HID_CMD_GET_KEYBOARD_CONFIG][6:]
                
                velocity_sensitivity = struct.unpack('<I', data[0:4])[0]
                cc_sensitivity = struct.unpack('<I', data[4:8])[0] 
                channel_number = data[8]
                transpose_number = struct.unpack('<b', data[9:10])[0]
                octave_number = struct.unpack('<b', data[10:11])[0]
                transpose_number2 = struct.unpack('<b', data[11:12])[0]
                octave_number2 = struct.unpack('<b', data[12:13])[0]
                transpose_number3 = struct.unpack('<b', data[13:14])[0]
                octave_number3 = struct.unpack('<b', data[14:15])[0]
                random_velocity_modifier = data[15]
                oled_keyboard = struct.unpack('<I', data[16:20])[0]
                # Byte 20 (was reserved / overdub_advanced_mode): per-function
                # Stop Mode bitmask. Bit 7 set = "firmware supports Stop Mode"
                # (feature detect); low 5 bits = STOP_MODE_* mask (bit clear =
                # Mute, bit set = Stop). Old firmware sends 0 here.
                stop_mode_byte = data[20]
                smart_chord_light_mode = data[21]
                # Bytes 22-25: firmware now carries these here (packet 2 was full).
                # Previously they had NO GET path, so the GUI defaulted them and a
                # slot-load clobbered the device. See firmware handle_get_keyboard_config.
                chord_display_mode = data[22] if len(data) > 22 else 2
                base_sustain = data[23] if len(data) > 23 else 0
                keysplit_sustain = data[24] if len(data) > 24 else 0
                triplesplit_sustain = data[25] if len(data) > 25 else 0

                config.update({
                    "velocity_sensitivity": velocity_sensitivity,
                    "cc_sensitivity": cc_sensitivity,
                    "channel_number": channel_number,
                    "transpose_number": transpose_number,
                    "transpose_number2": transpose_number2,
                    "transpose_number3": transpose_number3,
                    "random_velocity_modifier": random_velocity_modifier,
                    "oled_keyboard": oled_keyboard,
                    "stop_mode_supported": bool(stop_mode_byte & 0x80),
                    "stop_mode": stop_mode_byte & 0x1F,
                    "smart_chord_light_mode": smart_chord_light_mode,
                    "chord_display_mode": chord_display_mode,
                    "base_sustain": base_sustain,
                    "keysplit_sustain": keysplit_sustain,
                    "triplesplit_sustain": triplesplit_sustain
                })
                
            if HID_CMD_SET_KEYBOARD_CONFIG_ADVANCED in packets:
                data = packets[HID_CMD_SET_KEYBOARD_CONFIG_ADVANCED][6:]

                config.update({
                    "key_split_channel": data[0],
                    "key_split2_channel": data[1],
                    "key_split_status": data[2],
                    "key_split_transpose_status": data[3],
                    "key_split_velocity_status": data[4],
                    "custom_layer_animations_enabled": data[5] != 0,
                    "unsynced_mode_active": data[6],
                    "sample_mode_active": data[7] != 0,
                    "instant_loop_start": data[8] != 0,
                    # Note: channel/sync/restart now in ThruLoop packet (0xB0)
                    "colorblindmode": data[9],
                    "cclooprecording": data[10],
                    "truesustain": data[11] != 0,
                    # MIDI Routing Override Settings (bytes 12-17)
                    "channel_override": data[12] != 0 if len(data) > 12 else False,
                    "velocity_override": data[13] != 0 if len(data) > 13 else False,
                    "transpose_override": data[14] != 0 if len(data) > 14 else False,
                    "midi_in_mode": data[15] if len(data) > 15 else 0,
                    "usb_midi_mode": data[16] if len(data) > 16 else 0,
                    "midi_clock_source": data[17] if len(data) > 17 else 0,
                    # Macro override live notes (byte 18)
                    "macro_override_live_notes": data[18] != 0 if len(data) > 18 else False,
                    # SmartChord settings (bytes 19-22)
                    "smartchord_mode": data[19] if len(data) > 19 else 0,
                    "base_smartchord_ignore": data[20] if len(data) > 20 else 0,
                    "keysplit_smartchord_ignore": data[21] if len(data) > 21 else 0,
                    "triplesplit_smartchord_ignore": data[22] if len(data) > 22 else 0,
                    # Velocity curve indices (bytes 23-25)
                    "he_velocity_curve": data[23] if len(data) > 23 else 2,
                    "keysplit_he_velocity_curve": data[24] if len(data) > 24 else 2,
                    "triplesplit_he_velocity_curve": data[25] if len(data) > 25 else 2
                    # chord_display_mode now comes from the BASIC packet (bytes 22);
                    # the advanced packet is full at 26 bytes so data[26] was always
                    # out of range and pinned it to the default.
                })
                
            return config if config else None
            
        except Exception as e:
            return None
            
    def set_layer_actuation(self, data):
        """Set actuation for a specific layer

        Args:
            data: bytearray [layer, normal_actuation, midi_actuation, velocity_mode,
                            velocity_speed_scale, flags, aftertouch_mode, aftertouch_cc,
                            vibrato_sensitivity, vibrato_decay_time_low, vibrato_decay_time_high]
                  (11 bytes total)

        Note: Rapidfire settings are now per-key only (removed from layer settings).
              Aftertouch settings (mode, cc, vibrato_sensitivity, vibrato_decay_time) are per-layer.
              Uses new command 0xEC (moved from 0xCA to avoid arpeggiator conflict)
        """
        try:
            packet = self._create_hid_packet(HID_CMD_SET_LAYER_ACTUATION, 0, data)
            response = self.usb_send(self.dev, packet, retries=3)
            return response and len(response) > 0 and response[5] == 0x01
        except Exception as e:
            return False

    def get_layer_actuation(self, layer):
        """Get actuation for a specific layer

        Args:
            layer: Layer number (0-11)

        Returns:
            dict: {normal, midi, velocity, vel_speed, flags, aftertouch_mode, aftertouch_cc,
                   vibrato_sensitivity, vibrato_decay_time} or None

        Note: Rapidfire settings are now per-key only (removed from layer settings).
              Aftertouch settings are per-layer.
        """
        try:
            # Use new command code 0xEB (moved from 0xCB to avoid arpeggiator conflict)
            packet = self._create_hid_packet(HID_CMD_GET_LAYER_ACTUATION, 0, [layer])
            response = self.usb_send(self.dev, packet, retries=3)

            if not response or len(response) < 16:  # 5 header + 11 data bytes
                return None

            # Validate the command echo and both status bytes — a stale packet
            # from an earlier timed-out command would otherwise be parsed as
            # aftertouch/vibrato settings and land in global_midi_settings.
            if response[3] != HID_CMD_GET_LAYER_ACTUATION or \
                    response[4] != 0x01 or response[5] != 0x01:
                return None

            flags = response[10]
            vibrato_decay_time = response[14] | (response[15] << 8)
            return {
                'normal': response[6],
                'midi': response[7],
                'velocity': response[8],
                'vel_speed': response[9],
                'flags': flags,
                'use_per_key_velocity_curve': (flags & 0x08) != 0,
                'aftertouch_mode': response[11],
                'aftertouch_cc': response[12],
                'vibrato_sensitivity': response[13],
                'vibrato_decay_time': vibrato_decay_time
            }
        except Exception as e:
            return None

    @_hid_transaction
    def get_all_layer_actuations(self):
        """Get all layer actuations at once using bulk read

        Returns:
            list: 120 bytes (12 layers × 10 bytes) or None on error
            Each layer: [normal, midi, velocity_mode, vel_speed, flags,
                        aftertouch_mode, aftertouch_cc, vibrato_sensitivity,
                        vibrato_decay_time_low, vibrato_decay_time_high]

        Note: Aftertouch settings are now per-layer.
              Uses new command 0xED (moved from 0xCC to avoid arpeggiator conflict)
        """
        try:
            packet = self._create_hid_packet(HID_CMD_GET_ALL_LAYER_ACTUATIONS, 0, None)

            # Send request - use write directly to avoid waiting for response
            if hasattr(self.dev, 'write'):
                self.dev.write(b"\x00" + packet)
            else:
                self.dev.send_feature_report(packet)

            # Collect 6 packets (120 bytes total, 20 bytes per packet - 2 layers each)
            # Response format: [header(4)] [status(1)] [packet_num(1)] [total(1)] [layer_data(20)]
            EXPECTED_PACKETS = 6
            packets = {}

            for attempt in range(60):
                try:
                    if hasattr(self.dev, 'read'):
                        data = bytes(self.dev.read(32, timeout_ms=50))
                    else:
                        data = bytes(self.dev.get_feature_report(0, 32))

                    if not data or len(data) < 8:
                        continue

                    # Check if this is our response
                    if (data[0] == HID_MANUFACTURER_ID and
                        data[3] == HID_CMD_GET_ALL_LAYER_ACTUATIONS):

                        status = data[4]
                        packet_num = data[5]
                        total_packets = data[6]

                        if status != 0x01:
                            return None  # Error response

                        if packet_num < EXPECTED_PACKETS and packet_num not in packets:
                            # Extract layer data (20 bytes at offset 7)
                            packets[packet_num] = data[7:27]

                    if len(packets) >= EXPECTED_PACKETS:
                        break

                except Exception:
                    continue

            if len(packets) < EXPECTED_PACKETS:
                return None

            # Sort packets and combine
            actuations = bytearray()
            for i in range(EXPECTED_PACKETS):
                if i not in packets:
                    return None  # Missing packet
                actuations.extend(packets[i])

            return actuations[:120]  # 12 layers × 10 bytes
        except Exception as e:
            return None

    def reset_layer_actuations(self):
        """Reset all layer actuations to defaults

        Uses new command 0xEE (moved from 0xCD to avoid arpeggiator conflict)
        """
        try:
            packet = self._create_hid_packet(HID_CMD_RESET_LAYER_ACTUATIONS, 0, None)
            response = self.usb_send(self.dev, packet, retries=3)
            return response and len(response) > 0 and response[5] == 0x01
        except Exception as e:
            return False
            
    def reload_thruloop_config(self):
        """Load ThruLoop configuration from keyboard"""
        try:
            self.thruloop_config = self.get_thruloop_config()
        except:
            self.thruloop_config = None

    def reload_midi_config(self):
        """Load MIDI configuration from keyboard"""
        try:
            self.midi_config = self.get_midi_config()
        except:
            self.midi_config = None

    def reload_layer_actuations(self):
        """Load layer actuations from keyboard"""
        try:
            self.layer_actuations = self.get_all_layer_actuations()
        except:
            self.layer_actuations = None

    def set_gaming_mode(self, enabled):
        """Enable or disable gaming mode

        Args:
            enabled: True to enable gaming mode, False to disable

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            packet = self._create_hid_packet(HID_CMD_GAMING_SET_MODE, 0, [1 if enabled else 0])
            response = self.usb_send(self.dev, packet, retries=20)
            return response and len(response) > 5 and response[5] == 0x00
        except Exception as e:
            return False

    def set_gaming_key_map(self, control_id, row, col, enabled):
        """Map a key to a joystick control

        Args:
            control_id: Control ID (0-3=LS, 4-7=RS, 8=LT, 9=RT, 10-25=Buttons)
            row: Matrix row (0-4)
            col: Matrix column (0-13)
            enabled: 1 to enable mapping, 0 to disable

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            data = [control_id, row, col, 1 if enabled else 0]
            packet = self._create_hid_packet(HID_CMD_GAMING_SET_KEY_MAP, 0, data)
            response = self.usb_send(self.dev, packet, retries=20)
            return response and len(response) > 5 and response[5] == 0x00
        except Exception as e:
            return False

    def set_gaming_analog_config(self, ls_min, ls_max, rs_min, rs_max, trigger_min, trigger_max, suppress_keystrokes=True):
        """Set analog calibration configuration for LS, RS, and Triggers

        Args:
            ls_min: Left Stick minimum travel in 0.1mm units (e.g., 10 = 1.0mm)
            ls_max: Left Stick maximum travel in 0.1mm units (e.g., 20 = 2.0mm)
            rs_min: Right Stick minimum travel in 0.1mm units
            rs_max: Right Stick maximum travel in 0.1mm units
            trigger_min: Trigger minimum travel in 0.1mm units
            trigger_max: Trigger maximum travel in 0.1mm units
            suppress_keystrokes: Suppress normal keycodes for mapped gaming keys

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Values should be in 0.1mm units (firmware native), e.g. 10 = 1.0mm
            data = [ls_min, ls_max, rs_min, rs_max, trigger_min, trigger_max, 1 if suppress_keystrokes else 0]
            packet = self._create_hid_packet(HID_CMD_GAMING_SET_ANALOG_CONFIG, 0, data)
            response = self.usb_send(self.dev, packet, retries=20)
            return response and len(response) > 5 and response[5] == 0x00
        except Exception as e:
            return False

    def get_gaming_key_map(self, control_id):
        """Read back a single gamepad control's key mapping from the keyboard.

        Needed so the configurator can restore existing gamepad assignments on
        connect. Without it the GUI cannot see current mappings, and its Save
        would overwrite every control with "unassigned" — silently wiping the
        user's gamepad layout.

        Args:
            control_id: 0-9 = axes/triggers, 10-25 = buttons

        Returns:
            dict {'row', 'col', 'enabled'} or None on error/unmapped
        """
        try:
            # HID_CMD_GAMING_GET_KEY_MAP (0xBD). Firmware success = status byte 0x00.
            packet = self._create_hid_packet(0xBD, 0, [int(control_id) & 0xFF])
            response = self.usb_send(self.dev, packet, retries=3)
            if not response or len(response) < 10 or response[5] != 0x00:
                return None
            return {
                'row': response[7],
                'col': response[8],
                'enabled': response[9] != 0,
            }
        except Exception:
            return None

    def get_gaming_settings(self):
        """Get current gaming settings from keyboard

        Returns:
            dict: Gaming settings or None on error
        """
        try:
            packet = self._create_hid_packet(HID_CMD_GAMING_GET_SETTINGS, 0, None)
            response = self.usb_send(self.dev, packet, retries=3)

            # Firmware GET_SETTINGS reports success with status byte (index 5) == 0.
            # Check it so a joystick-disabled build (which returns an error packet of
            # zeros) is not misread as "all sliders at 0.0mm".
            if not response or len(response) < 14 or response[5] != 0x00:
                return None

            # Parse gaming settings from response
            # Response format: [status, enabled, ls_min, ls_max, rs_min, rs_max, trigger_min, trigger_max, suppress_keystrokes, ...]
            # Values are in 0.1mm units (firmware native), e.g. 10 = 1.0mm
            return {
                'enabled': response[6] != 0,
                'ls_min_travel': response[7],
                'ls_max_travel': response[8],
                'rs_min_travel': response[9],
                'rs_max_travel': response[10],
                'trigger_min_travel': response[11],
                'trigger_max_travel': response[12],
                'suppress_keystrokes': response[13] != 0 if len(response) > 13 else True
            }
        except Exception as e:
            return None

    def reset_gaming_settings(self):
        """Reset gaming settings to defaults

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            packet = self._create_hid_packet(HID_CMD_GAMING_RESET, 0, None)
            response = self.usb_send(self.dev, packet, retries=20)
            return response and len(response) > 5 and response[5] == 0x00
        except Exception as e:
            return False

    def reload_gaming_settings(self):
        """Load gaming settings from keyboard"""
        try:
            self.gaming_settings = self.get_gaming_settings()
        except:
            self.gaming_settings = None

    # =========================================================================
    # USER CURVE METHODS
    # =========================================================================

    def _serialize_zone_settings(self, zone):
        """Serialize zone settings to bytes for HID transfer."""
        data = bytearray()
        # Points (8 bytes)
        for point in zone.get('points', [[0,0], [85,85], [170,170], [255,255]]):
            data.append(int(point[0]) & 0xFF)
            data.append(int(point[1]) & 0xFF)
        # Settings (15 bytes)
        data.append(int(zone.get('velocity_min', 1)) & 0xFF)
        data.append(int(zone.get('velocity_max', 127)) & 0xFF)
        slow = int(zone.get('slow_press_time', 200))
        data.append(slow & 0xFF)
        data.append((slow >> 8) & 0xFF)
        fast = int(zone.get('fast_press_time', 20))
        data.append(fast & 0xFF)
        data.append((fast >> 8) & 0xFF)
        at_mode = int(zone.get('aftertouch_mode', 0)) & 0xFF
        data.append(at_mode)
        data.append(int(zone.get('aftertouch_cc', 255)) & 0xFF)
        data.append(int(zone.get('vibrato_sensitivity', 50)) & 0xFF)
        vib = int(zone.get('vibrato_decay', 10))
        data.append(vib & 0xFF)
        data.append((vib >> 8) & 0xFF)
        flags = 0x01 if zone.get('actuation_override', False) else 0x00
        data.append(flags)
        data.append(int(zone.get('actuation_point', 20)) & 0xFF)
        data.append(int(zone.get('speed_peak_ratio', 50)) & 0xFF)
        # Dual-use byte: smoothness (0-100) when aftertouch active, retrigger (0-20) when off
        if at_mode > 0:
            data.append(int(zone.get('aftertouch_smoothness', 0)) & 0xFF)
        else:
            data.append(int(zone.get('retrigger_distance', 0)) & 0xFF)
        return data

    def set_velocity_preset(self, slot, points, name, velocity_min=1, velocity_max=127,
                            slow_press_time=200, fast_press_time=20, aftertouch_mode=0,
                            aftertouch_smoothness=0, aftertouch_cc=255,
                            vibrato_sensitivity=100, vibrato_decay=200,
                            actuation_override=False, actuation_point=20,
                            speed_peak_ratio=50, retrigger_distance=0,
                            **kwargs):
        """
        Set a velocity preset slot with curve points and all associated settings.
        Single-zone format - zone assignment is done at runtime via modifier keys.

        Args:
            slot: Slot index (0-9 for User 1-10)
            points: List of 4 points [[x0,y0], [x1,y1], [x2,y2], [x3,y3]] (0-255 range)
            name: Preset name (max 16 characters)
            velocity_min: Minimum MIDI velocity (1-127)
            velocity_max: Maximum MIDI velocity (1-127)
            slow_press_time: Slow press threshold in ms (50-500)
            fast_press_time: Fast press threshold in ms (5-100)
            aftertouch_mode: 0=Off, 1-8 various modes
            aftertouch_smoothness: EMA smoothing level (0-100%)
            aftertouch_cc: CC number (0-127) or 255 for poly AT only
            vibrato_sensitivity: Percentage (0-100)
            vibrato_decay: ms per unit of aftertouch decay (0-50)
            actuation_override: Enable per-key actuation override
            actuation_point: Actuation point (0-40 = 0.0-4.0mm)
            speed_peak_ratio: Ratio of speed to peak for velocity (0-100)
            retrigger_distance: Retrigger distance (0=off, 5-20)

        Returns:
            bool: True if successful
        """
        if slot < 0 or slot >= 50:
            return False

        if len(points) != 4 or any(len(p) != 2 for p in points):
            return False

        # Build zone settings dict
        zone = {
            'points': points,
            'velocity_min': velocity_min,
            'velocity_max': velocity_max,
            'slow_press_time': slow_press_time,
            'fast_press_time': fast_press_time,
            'aftertouch_mode': aftertouch_mode,
            'aftertouch_smoothness': aftertouch_smoothness,
            'aftertouch_cc': aftertouch_cc,
            'vibrato_sensitivity': vibrato_sensitivity,
            'vibrato_decay': vibrato_decay,
            'actuation_override': actuation_override,
            'actuation_point': actuation_point,
            'speed_peak_ratio': speed_peak_ratio,
            'retrigger_distance': retrigger_distance
        }

        # === Send Chunk 0: name ===
        data0 = bytearray([slot, 0])  # slot, chunk_id=0
        name_bytes = name.encode('utf-8')[:16]
        name_bytes += b'\x00' * (16 - len(name_bytes))
        data0.extend(name_bytes)
        data0.append(0)  # reserved
        data0.append(0)  # reserved

        packet0 = self._create_hid_packet(0xD9, 0, data0)
        response0 = self.usb_send(self.dev, packet0, retries=20)
        if not response0 or len(response0) < 6 or response0[5] != 0x01:
            return False

        # === Send Chunk 1: zone settings ===
        data1 = bytearray([slot, 1])
        data1.extend(self._serialize_zone_settings(zone))
        packet1 = self._create_hid_packet(0xD9, 0, data1)
        response1 = self.usb_send(self.dev, packet1, retries=20)
        return response1 and len(response1) > 5 and response1[5] == 0x01

    def set_user_curve(self, slot, points, name, **kwargs):
        """
        Set a user curve slot with custom Bezier points and name.
        This is a compatibility wrapper for set_velocity_preset.

        Args:
            slot: Slot index (0-9 for User 1-10)
            points: List of 4 points [[x0,y0], [x1,y1], [x2,y2], [x3,y3]] (0-255 range)
            name: Curve name (max 16 characters)
            **kwargs: Additional preset settings (velocity_min, velocity_max, etc.)

        Returns:
            bool: True if successful
        """
        return self.set_velocity_preset(slot, points, name, **kwargs)

    def _deserialize_zone_settings(self, data, offset=8):
        """Deserialize zone settings from HID response bytes."""
        points = []
        for i in range(4):
            x = data[offset + i*2]
            y = data[offset + i*2 + 1]
            points.append([x, y])
        return {
            'points': points,
            'velocity_min': data[offset + 8],
            'velocity_max': data[offset + 9],
            'slow_press_time': data[offset + 10] | (data[offset + 11] << 8),
            'fast_press_time': data[offset + 12] | (data[offset + 13] << 8),
            'aftertouch_mode': data[offset + 14],
            'aftertouch_cc': data[offset + 15],
            'vibrato_sensitivity': data[offset + 16],
            'vibrato_decay': data[offset + 17] | (data[offset + 18] << 8),
            'actuation_override': (data[offset + 19] & 0x01) != 0,
            'actuation_point': data[offset + 20],
            'speed_peak_ratio': data[offset + 21],
            # Dual-use byte: smoothness when aftertouch active, retrigger when off
            'aftertouch_smoothness': data[offset + 22] if data[offset + 14] > 0 else 0,
            'retrigger_distance': data[offset + 22] if data[offset + 14] == 0 else 0
        }

    def get_velocity_preset(self, slot):
        """
        Get a velocity preset from the keyboard with all settings.
        Single-zone format - returns flat settings dict.

        Args:
            slot: Slot index (0-9)

        Returns:
            dict: {
                'name': str,
                'points': [[x0,y0], ...],
                'velocity_min': int, 'velocity_max': int, etc.
            } or None
        """
        if slot < 0 or slot >= 50:
            return None

        data = bytearray([slot])
        packet = self._create_hid_packet(0xDA, 0, data)  # HID_CMD_VELOCITY_PRESET_GET

        # Firmware sends 2 response packets
        # Receive Chunk 0: name — verify command byte and slot, not just status,
        # so a stale packet from another command can't be parsed as this preset.
        response0 = self.usb_send(self.dev, packet, retries=3)
        if (not response0 or len(response0) < 32 or response0[3] != 0xDA or
                response0[5] != 0x01 or response0[6] != slot):
            return None

        if response0[7] != 0:
            return None

        # Parse name from chunk 0 (16 bytes at offset 8)
        name_bytes = bytes(response0[8:24])
        name = name_bytes.decode('utf-8', errors='ignore').rstrip('\x00')

        # Receive Chunk 1: zone settings. A missing or invalid chunk fails the
        # whole read — silently substituting factory defaults here made the
        # editor display defaults as the user's preset, and a subsequent save
        # would overwrite the real preset with those defaults.
        try:
            response1 = bytes(self.dev.read(32, timeout_ms=500))
        except Exception:
            response1 = None
        if (not response1 or len(response1) < 31 or response1[3] != 0xDA or
                response1[5] != 0x01 or response1[6] != slot or response1[7] != 1):
            return None
        zone = self._deserialize_zone_settings(response1)

        # Build flat result
        result = {'name': name}
        result.update(zone)

        return result

    def get_user_curve(self, slot):
        """
        Get a user curve from the keyboard.
        This is a compatibility wrapper for get_velocity_preset.

        Args:
            slot: Slot index (0-9)

        Returns:
            dict: {'points': [[x0,y0], ...], 'name': str, ...} or None
        """
        return self.get_velocity_preset(slot)

    @_hid_transaction
    def get_all_user_curve_names(self):
        """
        Get all user curve names from the keyboard (50 presets via bulk read).

        Firmware sends 25 packets (2 presets each) in response to a single request.
        Packet format: [header(4), status(1), pkt_num(1), total(1),
                        configured1(1), name1(10), configured2(1), name2(10)]

        Returns:
            tuple: (names, configured) where names is list of 50 strings and
                   configured is list of 50 bools indicating if each slot has been saved
        """
        configured = [False] * 50
        names = ["User {}".format(i + 1) for i in range(50)]

        try:
            # Send single request to trigger bulk response
            packet = self._create_hid_packet(0xDB, 0, bytearray())  # HID_CMD_USER_CURVE_GET_ALL

            # Send request directly (firmware sends multiple response packets)
            if hasattr(self.dev, 'write'):
                self.dev.write(b"\x00" + packet)
            else:
                self.dev.send_feature_report(packet)

            EXPECTED_PACKETS = 25
            NAMES_PER_PACKET = 2
            received = set()

            # Read bulk response packets
            for attempt in range(100):
                try:
                    if hasattr(self.dev, 'read'):
                        response = bytes(self.dev.read(32, timeout_ms=50))
                    else:
                        response = bytes(self.dev.get_feature_report(0, 32))

                    if not response or len(response) < 29:
                        if len(received) >= EXPECTED_PACKETS:
                            break
                        continue

                    # Verify this is our response
                    if (response[0] == HID_MANUFACTURER_ID and
                        response[3] == 0xDB and
                        response[4] == 0x01):

                        pkt_num = response[5]
                        if pkt_num in received:
                            continue
                        received.add(pkt_num)

                        # Parse 2 presets per packet
                        for n in range(NAMES_PER_PACKET):
                            slot = pkt_num * NAMES_PER_PACKET + n
                            if slot >= 50:
                                break
                            offset = 7 + n * 11  # 1 flag + 10 name chars
                            is_configured = response[offset] != 0
                            name_bytes = response[offset + 1 : offset + 11]
                            name = ''.join(chr(b) if 32 <= b < 127 else '' for b in name_bytes).rstrip('\x00').strip()

                            configured[slot] = is_configured
                            if name:
                                names[slot] = name

                        if len(received) >= EXPECTED_PACKETS:
                            break
                except Exception:
                    if len(received) >= EXPECTED_PACKETS:
                        break
                    continue

        except Exception:
            pass  # Return defaults for any slots not received

        return names[:50], configured[:50]

    def reset_user_curves(self):
        """Reset all user curves to defaults (linear)."""
        packet = self._create_hid_packet(0xDC, 0, bytearray())  # HID_CMD_USER_CURVE_RESET
        response = self.usb_send(self.dev, packet, retries=20)
        return response and len(response) > 5 and response[5] == 0x01

    def toggle_velocity_preset_debug(self):
        """
        Toggle velocity preset debug display on OLED.
        Shows aftertouch, actuation override, speed/peak ratio, retrigger settings.

        Returns:
            bool: New state (True = debug mode on, False = off), or None if failed
        """
        packet = self._create_hid_packet(0xDD, 0, bytearray())  # HID_CMD_VELOCITY_PRESET_DEBUG_TOGGLE
        response = self.usb_send(self.dev, packet, retries=3)
        if response and len(response) > 6 and response[5] == 0x01:
            return response[6] == 0x01  # Returns current state
        return None

    # =========================================================================
    # GAMING RESPONSE SETTINGS
    # =========================================================================

    def set_gaming_response(self, angle_adj_enabled, diagonal_angle, square_output, snappy_joystick, curve_index):
        """
        Set gamepad response transformation settings.

        Args:
            angle_adj_enabled: bool - Enable diagonal angle adjustment
            diagonal_angle: int (0-90) - Angle in degrees
            square_output: bool - Use square joystick output
            snappy_joystick: bool - Use snappy joystick mode
            curve_index: int (0-16) - Analog curve index (0-6 factory, 7-16 user)

        Returns:
            bool: True if successful
        """
        data = bytearray([
            1 if angle_adj_enabled else 0,
            int(diagonal_angle) & 0xFF,
            1 if square_output else 0,
            1 if snappy_joystick else 0,
            int(curve_index) & 0xFF
        ])

        packet = self._create_hid_packet(0xDD, 0, data)  # HID_CMD_GAMING_SET_RESPONSE
        response = self.usb_send(self.dev, packet, retries=20)
        return response and len(response) > 5 and response[5] == 0x01

    def get_gaming_response(self):
        """
        Get gamepad response transformation settings.

        Returns:
            dict: {
                'angle_adj_enabled': bool,
                'diagonal_angle': int,
                'square_output': bool,
                'snappy_joystick': bool,
                'curve_index': int
            } or None
        """
        packet = self._create_hid_packet(0xDE, 0, bytearray())  # HID_CMD_GAMING_GET_RESPONSE
        response = self.usb_send(self.dev, packet, retries=3)

        if not response or len(response) < 11 or response[5] != 0x01:
            return None

        return {
            'angle_adj_enabled': response[6] != 0,
            'diagonal_angle': response[7],
            'square_output': response[8] != 0,
            'snappy_joystick': response[9] != 0,
            'curve_index': response[10]
        }

    def set_gaming_curve(self, curve_id, points):
        """Set a per-axis gaming curve.

        Args:
            curve_id: 0=LS, 1=RS, 2=LT, 3=RT
            points: [[x0,y0], [x1,y1], [x2,y2], [x3,y3]] (0-255 each)

        Returns:
            bool: True if successful
        """
        point_bytes = bytearray()
        for p in points:
            point_bytes.append(int(p[0]) & 0xFF)
            point_bytes.append(int(p[1]) & 0xFF)
        data = bytearray([int(curve_id) & 0xFF]) + point_bytes
        packet = self._create_hid_packet(0x90, 0, data)  # HID_CMD_GAMING_SET_CURVE (moved from 0xD6)
        response = self.usb_send(self.dev, packet, retries=20)
        return response and len(response) > 5 and response[5] == 0x01

    def get_gaming_curve(self, curve_id):
        """Get a per-axis gaming curve.

        Args:
            curve_id: 0=LS, 1=RS, 2=LT, 3=RT

        Returns:
            list: [[x0,y0], [x1,y1], [x2,y2], [x3,y3]] or None
        """
        data = bytearray([int(curve_id) & 0xFF])
        packet = self._create_hid_packet(0x91, 0, data)  # HID_CMD_GAMING_GET_CURVE (moved from 0xD7)
        response = self.usb_send(self.dev, packet, retries=3)

        if not response or len(response) < 14 or response[5] != 0x01:
            return None

        points = []
        for i in range(4):
            x = response[6 + i * 2]
            y = response[6 + i * 2 + 1]
            points.append([x, y])
        return points

    def set_per_key_actuation(self, layer, key_index, settings):
        """Set per-key actuation settings for a specific key

        Args:
            layer: Layer number (0-11)
            key_index: Key index (0-69, calculated as row * 14 + col)
            settings: dict with keys (firmware uses 0-255 = 0-4.0mm distance units):
                - actuation: Actuation point (0-255, default 127 = 2.0mm)
                - deadzone_top: Top deadzone (0-51, default 6 ~ 0.1mm; firmware clamps to 51)
                - deadzone_bottom: Bottom deadzone (0-51, default 6 ~ 0.1mm; firmware clamps to 51)
                - velocity_curve: Velocity curve (0-16: 0-6 Factory curves, 7-16 User curves)
                - flags: Flags byte (Bit 0: rapidfire_enabled, Bit 1: use_per_key_velocity_curve,
                         Bit 2: continuous_rt)
                - rapidfire_press_sens: Rapidfire press sensitivity (0-255, default 6 ~ 0.1mm)
                - rapidfire_release_sens: Rapidfire release sensitivity (0-255, default 6 ~ 0.1mm)
                - rapidfire_velocity_mod: Rapidfire velocity modifier (-64 to +64). NOTE:
                  currently inert — the firmware forces this to 0 in the velocity path.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Convert signed velocity mod to unsigned byte
            velocity_mod = settings.get('rapidfire_velocity_mod', 0)
            velocity_mod_byte = velocity_mod & 0xFF if velocity_mod < 0 else velocity_mod

            data = bytearray([
                layer,
                key_index,
                settings.get('actuation', 60),
                settings.get('deadzone_top', 4),
                settings.get('deadzone_bottom', 4),
                settings.get('velocity_curve', 2),
                settings.get('flags', 0),  # Now using flags field
                settings.get('rapidfire_press_sens', 4),
                settings.get('rapidfire_release_sens', 4),
                velocity_mod_byte
            ])
            packet = self._create_hid_packet(HID_CMD_SET_PER_KEY_ACTUATION, 0, data)
            response = self.usb_send(self.dev, packet, retries=20)
            return response and len(response) > 4 and response[4] == 0x01
        except Exception as e:
            return False

    def get_per_key_actuation(self, layer, key_index):
        """Get per-key actuation settings for a specific key

        Args:
            layer: Layer number (0-11)
            key_index: Key index (0-69, calculated as row * 14 + col)

        Returns:
            dict: {
                actuation, deadzone_top, deadzone_bottom, velocity_curve,
                flags, rapidfire_press_sens, rapidfire_release_sens,
                rapidfire_velocity_mod
            } or None on error
        """
        try:
            data = [layer, key_index]
            packet = self._create_hid_packet(HID_CMD_GET_PER_KEY_ACTUATION, 0, data)
            # Reduced retries from 20 to 3 for faster loading
            response = self.usb_send(self.dev, packet, retries=3)

            if response and len(response) >= 13:
                # Response format: [header (4 bytes) + status (1 byte)] + [8 per-key fields at index 5]
                # Convert unsigned byte to signed for velocity mod
                velocity_mod_byte = response[12]
                velocity_mod = velocity_mod_byte if velocity_mod_byte < 128 else velocity_mod_byte - 256

                return {
                    'actuation': response[5],
                    'deadzone_top': response[6],
                    'deadzone_bottom': response[7],
                    'velocity_curve': response[8],
                    'flags': response[9],  # Now using flags field
                    'rapidfire_press_sens': response[10],
                    'rapidfire_release_sens': response[11],
                    'rapidfire_velocity_mod': velocity_mod
                }
            return None
        except Exception as e:
            return None

    def get_all_per_key_actuations(self, layer):
        """Get all per-key actuation settings for a layer using bulk read

        This is much faster than calling get_per_key_actuation 70 times.
        Uses HID_CMD_GET_ALL_PER_KEY_ACTUATIONS (0xE2) to fetch all keys at once.

        Firmware sends 24 packets with 3 keys each (70 keys total):
        - Bytes 0-3: Header [0x7D, 0x00, 0x4D, 0xE2]
        - Byte 4: Status (0x01 = success)
        - Byte 5: Layer number
        - Byte 6: Packet number (0-23)
        - Byte 7: Total packets (24)
        - Bytes 8-31: Key data (up to 3 keys × 8 bytes = 24 bytes)

        Args:
            layer: Layer number (0-11)

        Returns:
            list: List of 70 dicts with per-key settings, or None on error
        """
        try:
            # Request all per-key actuations for this layer
            data = [layer]
            packet = self._create_hid_packet(HID_CMD_GET_ALL_PER_KEY_ACTUATIONS, 0, data)

            # Send request - use write directly to avoid waiting for response
            if hasattr(self.dev, 'write'):
                self.dev.write(b"\x00" + packet)
            else:
                self.dev.send_feature_report(packet)

            # Collect response packets (24 packets with 3 keys each)
            EXPECTED_PACKETS = 24
            KEYS_PER_PACKET = 3
            packets = {}

            # Read packets with short timeout - firmware sends them all quickly.
            # On a bad packet we must NOT return early: the firmware keeps
            # streaming the rest of the 24-packet response, and any packet left
            # in the HID FIFO would be misparsed as the reply to the NEXT
            # command (hid_send has no command/response correlation). Keep
            # draining until the stream goes quiet, then fail.
            failed = False
            empty_reads = 0
            for attempt in range(200):  # Max 200 read attempts
                try:
                    if hasattr(self.dev, 'read'):
                        response = bytes(self.dev.read(32, timeout_ms=50))
                    else:
                        response = bytes(self.dev.get_feature_report(0, 32))

                    if not response or len(response) < 8:
                        empty_reads += 1
                        # After a failure, stop once the stream has drained
                        # (a few consecutive empty reads = firmware is done).
                        if failed and empty_reads >= 3:
                            break
                        continue
                    empty_reads = 0

                    # Check if this is a response to our command
                    if (response[0] == HID_MANUFACTURER_ID and
                        response[3] == HID_CMD_GET_ALL_PER_KEY_ACTUATIONS):

                        status = response[4]
                        resp_layer = response[5]
                        packet_num = response[6]
                        total_packets = response[7]

                        # Validate response — mark failure but keep draining
                        if status != 0x01 or resp_layer != layer:
                            failed = True
                            continue

                        if packet_num < EXPECTED_PACKETS and packet_num not in packets:
                            # Extract key data (bytes 8-31, up to 24 bytes = 3 keys × 8)
                            key_data = response[8:32]
                            packets[packet_num] = key_data

                    if not failed and len(packets) >= EXPECTED_PACKETS:
                        break

                except Exception:
                    continue

            if failed or len(packets) < EXPECTED_PACKETS:
                # Bulk read failed, return None to trigger fallback
                return None

            # Parse keys from packets (3 keys per packet, 8 bytes per key)
            keys = []
            for pkt_num in range(EXPECTED_PACKETS):
                if pkt_num not in packets:
                    return None  # Missing packet

                pkt_data = packets[pkt_num]
                start_key = pkt_num * KEYS_PER_PACKET

                for k in range(KEYS_PER_PACKET):
                    key_idx = start_key + k
                    if key_idx >= 70:
                        break

                    offset = k * 8
                    if offset + 8 > len(pkt_data):
                        break

                    velocity_mod_byte = pkt_data[offset + 7]
                    velocity_mod = velocity_mod_byte if velocity_mod_byte < 128 else velocity_mod_byte - 256

                    keys.append({
                        'actuation': pkt_data[offset + 0],
                        'deadzone_top': pkt_data[offset + 1],
                        'deadzone_bottom': pkt_data[offset + 2],
                        'velocity_curve': pkt_data[offset + 3],
                        'flags': pkt_data[offset + 4],
                        'rapidfire_press_sens': pkt_data[offset + 5],
                        'rapidfire_release_sens': pkt_data[offset + 6],
                        'rapidfire_velocity_mod': velocity_mod
                    })

            return keys if len(keys) == 70 else None

        except Exception as e:
            return None

    def set_per_key_mode(self, mode_enabled, per_layer_enabled):
        """DEPRECATED: Set per-key actuation mode flags

        NOTE: Mode flags have been REMOVED from firmware. Firmware now ALWAYS uses
        per-key per-layer settings. The GUI handles "apply to all keys/layers" by
        writing the same values to all keys/layers when the user wants uniform settings.

        This function is kept for backward compatibility but is now a no-op.
        The HID command still exists in firmware but does nothing.

        Args:
            mode_enabled: Ignored - always per-key
            per_layer_enabled: Ignored - always per-layer

        Returns:
            bool: Always True (no-op success)
        """
        # No-op: firmware always uses per-key per-layer
        # Still send the command for backward compatibility with older firmware
        try:
            data = [1 if mode_enabled else 0, 1 if per_layer_enabled else 0]
            packet = self._create_hid_packet(HID_CMD_SET_PER_KEY_MODE, 0, data)
            response = self.usb_send(self.dev, packet, retries=20)
            return response and len(response) > 4 and response[4] == 0x01
        except Exception as e:
            return True  # Return success anyway - this is a no-op

    def get_per_key_mode(self):
        """DEPRECATED: Get per-key actuation mode flags

        NOTE: Mode flags have been REMOVED from firmware. Firmware now ALWAYS uses
        per-key per-layer settings. This function always returns both modes as enabled.

        Returns:
            dict: {'mode_enabled': True, 'per_layer_enabled': True} - always enabled
        """
        # Always return enabled - firmware always uses per-key per-layer
        # Still query firmware for backward compatibility
        try:
            packet = self._create_hid_packet(HID_CMD_GET_PER_KEY_MODE, 0, None)
            response = self.usb_send(self.dev, packet, retries=20)
            if response and len(response) > 6:
                return {
                    'mode_enabled': response[5] != 0,
                    'per_layer_enabled': response[6] != 0
                }
            # If query fails, return enabled defaults
            return {'mode_enabled': True, 'per_layer_enabled': True}
        except Exception as e:
            return {'mode_enabled': True, 'per_layer_enabled': True}

    def reset_per_key_actuations(self):
        """Reset all per-key actuations to default (60 = 1.5mm)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            packet = self._create_hid_packet(HID_CMD_RESET_PER_KEY_ACTUATIONS, 0, None)
            response = self.usb_send(self.dev, packet, retries=20)
            return response and len(response) > 4 and response[4] == 0x01
        except Exception as e:
            return False

    def copy_layer_actuations(self, source_layer, dest_layer):
        """Copy actuation settings from one layer to another

        Args:
            source_layer: Source layer number (0-11)
            dest_layer: Destination layer number (0-11)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            data = [source_layer, dest_layer]
            packet = self._create_hid_packet(HID_CMD_COPY_LAYER_ACTUATIONS, 0, data)
            response = self.usb_send(self.dev, packet, retries=20)
            return response and len(response) > 4 and response[4] == 0x01
        except Exception as e:
            return False