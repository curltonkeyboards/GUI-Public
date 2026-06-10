# SPDX-License-Identifier: GPL-2.0-or-later
"""
MIDI Delay Protocol Handler

Manages communication with the firmware's MIDI delay system.
Each delay slot has configurable rate, decay, repeats, channel, and transpose settings.
"""

import struct

# HID Command Codes (0xD6-0xD8)
HID_CMD_DELAY_GET_SLOT = 0xD6     # Get single slot config
HID_CMD_DELAY_SET_SLOT = 0xD7     # Set single slot config (0xFF = save to EEPROM)
HID_CMD_DELAY_GET_BULK = 0xD8     # Get multiple slots (chunked)

# Delay Constants
DELAY_FACTORY_COUNT = 48  # Factory presets in firmware flash (read-only)
DELAY_USER_SLOT_COUNT = 50  # User-configurable slots
DELAY_TOTAL_SLOT_COUNT = DELAY_FACTORY_COUNT + DELAY_USER_SLOT_COUNT  # 98 total
DELAY_NUM_SLOTS = DELAY_USER_SLOT_COUNT  # For backward compat (editor uses this for user slots)
DELAY_CONFIG_SIZE = 16

# Delay Keycode Range (unified: 0-47 factory, 48-97 user)
DELAY_KEY_BASE = 0xEF90
DELAY_KEY_MAX = DELAY_KEY_BASE + DELAY_TOTAL_SLOT_COUNT - 1  # 0xEFF1

# Rate modes
RATE_MODE_BPM = 0
RATE_MODE_FIXED_MS = 1

# Transpose modes
TRANSPOSE_FIXED = 0
TRANSPOSE_CUMULATIVE = 1


def is_delay_keycode(keycode):
    """Check if a keycode is a delay keycode"""
    return DELAY_KEY_BASE <= keycode <= DELAY_KEY_MAX


def delay_keycode_to_slot(keycode):
    """Convert a delay keycode to its slot number"""
    return keycode - DELAY_KEY_BASE


def slot_to_delay_keycode(slot):
    """Convert a slot number to its delay keycode"""
    return DELAY_KEY_BASE + slot


class DelaySlot:
    """Represents a delay slot configuration"""

    def __init__(self):
        self.rate_mode = RATE_MODE_BPM       # 0=BPM-synced, 1=fixed ms
        self.note_value = 3                   # 0=1/1, 1=1/2, 2=1/4, 3=1/8, 4=1/16
        self.timing_mode = 0                  # 0=note, 1=triplet, 2=dotted
        self.decay_percent = 50               # 0-100
        self.fixed_delay_ms = 500             # 10-5000
        self.max_repeats = 3                  # 0-255 (0=infinite)
        self.channel = 0                      # 0=same, 1-16=specific
        self.transpose_semi = 0               # -48 to +48
        self.transpose_mode = TRANSPOSE_FIXED # 0=fixed, 1=cumulative
        self.max_active_notes = 0             # 0=no limit, 1-12=max active delay notes per slot
        self.channel_count = 1                # 1=single channel, 2-4=multi-channel cycling
        self.channel2 = 0                     # 2nd channel (1-16, 0=unused)
        self.channel3 = 0                     # 3rd channel (1-16, 0=unused)
        self.channel4 = 0                     # 4th channel (1-16, 0=unused)

    def to_bytes(self):
        """Pack slot into firmware format (16 bytes)"""
        data = bytearray(DELAY_CONFIG_SIZE)
        data[0] = self.rate_mode & 0xFF
        data[1] = self.note_value & 0xFF
        data[2] = self.timing_mode & 0xFF
        data[3] = self.decay_percent & 0xFF
        struct.pack_into('<H', data, 4, self.fixed_delay_ms)
        data[6] = self.max_repeats & 0xFF
        data[7] = self.channel & 0xFF
        data[8] = self.transpose_semi & 0xFF  # int8_t stored as uint8_t
        data[9] = self.transpose_mode & 0xFF
        data[10] = min(self.max_active_notes, 12) & 0xFF
        data[11] = min(max(self.channel_count, 1), 4) & 0xFF
        data[12] = self.channel2 & 0xFF
        data[13] = self.channel3 & 0xFF
        data[14] = self.channel4 & 0xFF
        # byte 15 reserved
        return bytes(data)

    @staticmethod
    def from_bytes(data):
        """Unpack slot from firmware format"""
        if len(data) < DELAY_CONFIG_SIZE:
            raise ValueError(f"Delay slot data must be {DELAY_CONFIG_SIZE} bytes")

        slot = DelaySlot()
        slot.rate_mode = data[0]
        slot.note_value = data[1]
        slot.timing_mode = data[2]
        slot.decay_percent = data[3]
        slot.fixed_delay_ms = struct.unpack_from('<H', data, 4)[0]
        slot.max_repeats = data[6]
        slot.channel = data[7]
        # int8_t: convert unsigned byte to signed
        raw = data[8]
        slot.transpose_semi = raw if raw < 128 else raw - 256
        slot.transpose_mode = data[9]
        slot.max_active_notes = data[10] if data[10] <= 12 else 0
        slot.channel_count = data[11] if 1 <= data[11] <= 4 else 1
        slot.channel2 = data[12] if data[12] <= 16 else 0
        slot.channel3 = data[13] if data[13] <= 16 else 0
        slot.channel4 = data[14] if data[14] <= 16 else 0
        return slot

    def is_default(self):
        """Check if slot has default/unconfigured values"""
        return (self.rate_mode == RATE_MODE_BPM and
                self.note_value == 3 and
                self.timing_mode == 0 and
                self.decay_percent == 50 and
                self.fixed_delay_ms == 500 and
                self.max_repeats == 3 and
                self.channel == 0 and
                self.transpose_semi == 0 and
                self.transpose_mode == TRANSPOSE_FIXED and
                self.max_active_notes == 0 and
                self.channel_count == 1)


class ProtocolDelay:
    """Delay protocol handler - manages communication with firmware"""

    def __init__(self, keyboard):
        self.keyboard = keyboard
        self.slots_cache = {}

    def get_slot(self, slot_num):
        """Get delay slot configuration from keyboard (unified index 0-97)"""
        if slot_num < 0 or slot_num >= DELAY_TOTAL_SLOT_COUNT:
            return None

        try:
            packet = self.keyboard._create_hid_packet(HID_CMD_DELAY_GET_SLOT, 0, bytes([slot_num]))
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            if not response or len(response) < (5 + DELAY_CONFIG_SIZE):
                return None

            # Status at index 4 (0x01 = success)
            if response[4] != 0x01:
                return None

            # Config data at index 5
            slot_data = response[5:5 + DELAY_CONFIG_SIZE]
            slot = DelaySlot.from_bytes(slot_data)

            self.slots_cache[slot_num] = slot
            return slot

        except Exception as e:
            print(f"Delay: Error getting slot {slot_num}: {e}")
            return None

    def set_slot(self, slot_num, slot):
        """Set delay slot configuration (only user slots 48-97 accepted by firmware)"""
        if slot_num < 0 or slot_num >= DELAY_TOTAL_SLOT_COUNT:
            return False
        if slot_num < DELAY_FACTORY_COUNT:
            return False  # Factory presets are read-only

        try:
            data = bytearray([slot_num]) + bytearray(slot.to_bytes())
            packet = self.keyboard._create_hid_packet(HID_CMD_DELAY_SET_SLOT, 0, bytes(data))
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            success = response and len(response) > 4 and response[4] == 0x01

            if success:
                self.slots_cache[slot_num] = slot

            return success

        except Exception as e:
            print(f"Delay: Error setting slot {slot_num}: {e}")
            return False

    def save_to_eeprom(self):
        """Save all delay configurations to EEPROM"""
        try:
            # Send SET_SLOT with slot_id=0xFF to trigger save
            data = bytearray([0xFF])
            packet = self.keyboard._create_hid_packet(HID_CMD_DELAY_SET_SLOT, 0, bytes(data))
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=5)

            return response and len(response) > 4 and response[4] == 0x01

        except Exception as e:
            print(f"Delay: Error saving to EEPROM: {e}")
            return False

    def get_bulk(self, start, count):
        """Get multiple slot configurations (chunked)"""
        try:
            data = bytearray([start, count])
            packet = self.keyboard._create_hid_packet(HID_CMD_DELAY_GET_BULK, 0, bytes(data))

            slots = []
            for i in range(count):
                response = self.keyboard.usb_send(self.keyboard.dev, packet if i == 0 else None, retries=3)
                if not response or len(response) < (7 + DELAY_CONFIG_SIZE):
                    break

                slot_idx = response[5]
                slot_data = response[7:7 + DELAY_CONFIG_SIZE]
                slot = DelaySlot.from_bytes(slot_data)
                self.slots_cache[slot_idx] = slot
                slots.append((slot_idx, slot))

            return slots

        except Exception as e:
            print(f"Delay: Error getting bulk slots: {e}")
            return []
