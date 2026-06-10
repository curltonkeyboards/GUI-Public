# SPDX-License-Identifier: GPL-2.0-or-later
"""
Toggle Keys Protocol Handler

Provides toggle key functionality where pressing a key toggles between
holding and releasing a target keycode. This is implemented as keybinds
(TGL_00 - TGL_99) that can be assigned to any physical key.

Each toggle slot contains:
- target_keycode: The keycode to toggle (held until toggled again)
- flags: Bit 0 = multi-key toggle mode
- num_keys: Number of keycodes in multi-key mode (2-8)
- state: Current state (0 = released, 1 = held) - runtime only

Multi-key toggle mode:
- Each press sends a tap (press+release) of the current keycode in the cycle
- Advances to the next keycode, wrapping around after the last
- Up to 8 keycodes per slot
- KC_NO (0) in a step skips without sending a keycode

Usage:
1. Configure a toggle slot with a target keycode via GUI
2. Optionally enable multi-key mode and configure up to 8 keycodes
3. Assign TGL_XX keycode to a physical key in keymap
4. Pressing the key toggles (standard) or cycles (multi-key) keycodes
"""

import struct
from typing import Optional, List

# Toggle HID Command Codes
HID_CMD_TOGGLE_GET_SLOT = 0xF5        # Get toggle slot configuration
HID_CMD_TOGGLE_SET_SLOT = 0xF6        # Set toggle slot configuration
HID_CMD_TOGGLE_SAVE_EEPROM = 0xF7     # Save all slots to EEPROM
HID_CMD_TOGGLE_LOAD_EEPROM = 0xF8     # Load all slots from EEPROM
HID_CMD_TOGGLE_RESET_ALL = 0xF9       # Reset all slots to defaults
HID_CMD_TOGGLE_GET_MULTI = 0xFC       # Get multi-key keycodes for a slot
HID_CMD_TOGGLE_SET_MULTI = 0xFD       # Set multi-key keycodes for a slot

# Toggle Constants
TOGGLE_NUM_SLOTS = 100                 # Number of toggle slots (TGL_00 - TGL_99)
TOGGLE_SLOT_SIZE = 4                   # Bytes per slot in firmware
TOGGLE_MULTI_MAX_KEYS = 8             # Max keycodes per multi-key slot
TOGGLE_MULTI_EXTRA_KEYS = 7           # Extra keycodes stored separately (keycodes 2-8)

# Toggle slot flags
TOGGLE_FLAG_MULTI_KEY = 0x01          # Bit 0: Multi-key toggle mode enabled

# Toggle Keycode Range
TOGGLE_KEY_BASE = 0xEF10               # TGL_00
TOGGLE_KEY_MAX = 0xEF73                # TGL_99 (0xEF10 + 99)

# Fixed LED colours for multi-key cycle steps (matches firmware)
TOGGLE_MULTI_COLORS = [
    (0, 200, 0),       # Step 0: Green
    (0, 0, 200),       # Step 1: Blue
    (200, 0, 0),       # Step 2: Red
    (200, 200, 0),     # Step 3: Yellow
    (0, 200, 200),     # Step 4: Cyan
    (200, 0, 200),     # Step 5: Magenta
    (200, 200, 200),   # Step 6: White
    (200, 100, 0),     # Step 7: Orange
]

TOGGLE_MULTI_COLOR_NAMES = [
    "Green", "Blue", "Red", "Yellow", "Cyan", "Magenta", "White", "Orange"
]


def is_toggle_keycode(keycode: int) -> bool:
    """Check if a keycode is a toggle keycode (TGL_XX)"""
    return TOGGLE_KEY_BASE <= keycode <= TOGGLE_KEY_MAX


def toggle_keycode_to_slot(keycode: int) -> int:
    """Convert a toggle keycode to its slot number"""
    return keycode - TOGGLE_KEY_BASE


def slot_to_toggle_keycode(slot: int) -> int:
    """Convert a slot number to its toggle keycode"""
    return TOGGLE_KEY_BASE + slot


class ToggleSlot:
    """Represents a toggle slot configuration"""

    def __init__(self, target_keycode: int = 0, flags: int = 0, num_keys: int = 0):
        self.target_keycode = target_keycode
        self.flags = flags
        self.num_keys = num_keys
        self.multi_keycodes = [0] * TOGGLE_MULTI_EXTRA_KEYS  # Keycodes 2-8

    @property
    def is_multi_key(self) -> bool:
        return bool(self.flags & TOGGLE_FLAG_MULTI_KEY)

    @is_multi_key.setter
    def is_multi_key(self, value: bool):
        if value:
            self.flags |= TOGGLE_FLAG_MULTI_KEY
        else:
            self.flags &= ~TOGGLE_FLAG_MULTI_KEY

    def get_keycode(self, index: int) -> int:
        """Get keycode at index (0-7)"""
        if index == 0:
            return self.target_keycode
        if 0 < index < TOGGLE_MULTI_MAX_KEYS:
            return self.multi_keycodes[index - 1]
        return 0

    def set_keycode(self, index: int, keycode: int):
        """Set keycode at index (0-7)"""
        if index == 0:
            self.target_keycode = keycode
        elif 0 < index < TOGGLE_MULTI_MAX_KEYS:
            self.multi_keycodes[index - 1] = keycode

    def is_enabled(self) -> bool:
        """Check if this slot is configured (has a target keycode)"""
        return self.target_keycode != 0

    def to_bytes(self) -> bytes:
        """Pack slot into firmware format (4 bytes)

        Format:
        - bytes 0-1: target_keycode (uint16_t)
        - byte 2: flags
        - byte 3: num_keys
        """
        data = bytearray(TOGGLE_SLOT_SIZE)
        struct.pack_into('<H', data, 0, self.target_keycode)
        data[2] = self.flags
        data[3] = self.num_keys
        return bytes(data)

    @staticmethod
    def from_bytes(data: bytes) -> 'ToggleSlot':
        """Unpack slot from firmware format"""
        if len(data) < TOGGLE_SLOT_SIZE:
            raise ValueError(f"Toggle slot data must be {TOGGLE_SLOT_SIZE} bytes")

        slot = ToggleSlot()
        slot.target_keycode = struct.unpack_from('<H', data, 0)[0]
        slot.flags = data[2]
        slot.num_keys = data[3]
        return slot

    def to_dict(self) -> dict:
        """Convert to dictionary for GUI"""
        return {
            'target_keycode': self.target_keycode,
            'flags': self.flags,
            'num_keys': self.num_keys,
            'multi_keycodes': list(self.multi_keycodes),
        }

    @staticmethod
    def from_dict(data: dict) -> 'ToggleSlot':
        """Create from dictionary"""
        slot = ToggleSlot(
            target_keycode=data.get('target_keycode', 0),
            flags=data.get('flags', 0),
            num_keys=data.get('num_keys', 0),
        )
        multi = data.get('multi_keycodes', [])
        for i in range(min(len(multi), TOGGLE_MULTI_EXTRA_KEYS)):
            slot.multi_keycodes[i] = multi[i]
        return slot


class ProtocolToggle:
    """Toggle protocol handler - manages communication with firmware"""

    def __init__(self, keyboard):
        self.keyboard = keyboard
        self.slots_cache = {}
        self._debug_console = None

    def set_debug_console(self, console):
        """Attach a DebugConsole widget for logging"""
        self._debug_console = console

    def _log(self, message, level="INFO"):
        if self._debug_console:
            self._debug_console.log(message, level)

    @staticmethod
    def _hex_bytes(data):
        return ' '.join('0x{:02X}'.format(b) for b in data)

    @staticmethod
    def _hex_keycodes(keycodes):
        return ', '.join('0x{:04X}'.format(kc) for kc in keycodes)

    def get_slot(self, slot_num: int) -> Optional[ToggleSlot]:
        """Get toggle slot configuration from keyboard"""
        if slot_num < 0 or slot_num >= TOGGLE_NUM_SLOTS:
            return None

        try:
            packet = self.keyboard._create_hid_packet(HID_CMD_TOGGLE_GET_SLOT, 0, [slot_num])
            self._log(f"GET_SLOT slot={slot_num}", "HID_TX")
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            if not response or len(response) < (5 + TOGGLE_SLOT_SIZE):
                self._log(f"GET_SLOT slot={slot_num}: response too short ({len(response) if response else 0} bytes)", "ERROR")
                return None

            if response[4] != 0:
                self._log(f"GET_SLOT slot={slot_num}: error status {response[4]}", "ERROR")
                return None

            slot_data = response[5:5 + TOGGLE_SLOT_SIZE]
            slot = ToggleSlot.from_bytes(slot_data)
            self._log(f"GET_SLOT slot={slot_num}: target=0x{slot.target_keycode:04X} flags=0x{slot.flags:02X} num_keys={slot.num_keys} raw=[{self._hex_bytes(slot_data)}]", "HID_RX")

            # If multi-key mode, also load the extra keycodes
            if slot.is_multi_key:
                self._load_multi_keycodes(slot_num, slot)

            self.slots_cache[slot_num] = slot
            return slot

        except Exception as e:
            self._log(f"GET_SLOT slot={slot_num}: exception: {e}", "ERROR")
            return None

    def _load_multi_keycodes(self, slot_num: int, slot: ToggleSlot):
        """Load multi-key extra keycodes from firmware"""
        try:
            packet = self.keyboard._create_hid_packet(HID_CMD_TOGGLE_GET_MULTI, 0, [slot_num])
            self._log(f"GET_MULTI slot={slot_num}", "HID_TX")
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            if not response or len(response) < (5 + TOGGLE_MULTI_EXTRA_KEYS * 2):
                self._log(f"GET_MULTI slot={slot_num}: response too short ({len(response) if response else 0} bytes)", "ERROR")
                return

            self._log(f"GET_MULTI slot={slot_num}: raw response[4:26]=[{self._hex_bytes(response[4:27])}]", "HID_RX")
            self._log(f"GET_MULTI FULL RX response=[{self._hex_bytes(response[:32])}]", "DEBUG")

            if response[4] != 0:
                self._log(f"GET_MULTI slot={slot_num}: error status {response[4]}", "ERROR")
                return

            for j in range(TOGGLE_MULTI_EXTRA_KEYS):
                slot.multi_keycodes[j] = struct.unpack_from('<H', response, 5 + j * 2)[0]

            self._log(f"GET_MULTI slot={slot_num}: parsed keycodes=[{self._hex_keycodes(slot.multi_keycodes)}]", "DATA")

            # Parse diagnostics from extended response bytes
            if len(response) >= 27:
                sizeof_entry = response[19]  # response[4+15]
                source = response[20]        # response[4+16]: 0=pool, 1=EEPROM
                fw_flags = response[21]      # response[4+17]
                fw_num_keys = response[22]   # response[4+18]
                fw_target_kc = struct.unpack_from('<H', response, 23)[0]  # response[4+19..20]
                fw_slot_num = response[25]   # response[4+21]
                fw_cycle_idx = response[26]  # response[4+22]
                source_str = "POOL" if source == 0 else "EEPROM"
                self._log(f"GET_MULTI DIAG: sizeof={sizeof_entry} source={source_str} slot_num={fw_slot_num} target=0x{fw_target_kc:04X} flags=0x{fw_flags:02X} num_keys={fw_num_keys} cycle_idx={fw_cycle_idx}", "DEBUG")

        except Exception as e:
            self._log(f"GET_MULTI slot={slot_num}: exception: {e}", "ERROR")

    def set_slot(self, slot_num: int, slot: ToggleSlot) -> bool:
        """Set toggle slot configuration"""
        if slot_num < 0 or slot_num >= TOGGLE_NUM_SLOTS:
            return False

        try:
            # Packet: [slot_num, target_kc_lo, target_kc_hi, flags, num_keys]
            data = bytearray([slot_num]) + bytearray(slot.to_bytes())

            self._log(f"SET_SLOT slot={slot_num}: target=0x{slot.target_keycode:04X} flags=0x{slot.flags:02X} num_keys={slot.num_keys} is_multi={slot.is_multi_key}", "HID_TX")
            self._log(f"SET_SLOT raw data=[{self._hex_bytes(data)}]", "DATA")

            packet = self.keyboard._create_hid_packet(HID_CMD_TOGGLE_SET_SLOT, 0, data)
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            success = response and len(response) > 4 and response[4] == 0
            self._log(f"SET_SLOT response: {'OK' if success else 'FAIL'}", "HID_RX")

            # If multi-key mode, also send the extra keycodes
            if success and slot.is_multi_key:
                success = self._send_multi_keycodes(slot_num, slot)

            if success:
                self.slots_cache[slot_num] = slot

            return success

        except Exception as e:
            self._log(f"SET_SLOT slot={slot_num}: exception: {e}", "ERROR")
            return False

    def _send_multi_keycodes(self, slot_num: int, slot: ToggleSlot) -> bool:
        """Send multi-key extra keycodes to firmware"""
        try:
            # Packet: [slot_num, kc2_lo, kc2_hi, kc3_lo, kc3_hi, ...]
            data = bytearray([slot_num])
            for j in range(TOGGLE_MULTI_EXTRA_KEYS):
                kc = slot.multi_keycodes[j]
                data.append(kc & 0xFF)
                data.append((kc >> 8) & 0xFF)

            self._log(f"SET_MULTI slot={slot_num}: keycodes=[{self._hex_keycodes(slot.multi_keycodes)}]", "HID_TX")
            self._log(f"SET_MULTI raw data=[{self._hex_bytes(data)}]", "DATA")

            packet = self.keyboard._create_hid_packet(HID_CMD_TOGGLE_SET_MULTI, 0, data)
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            success = response and len(response) > 4 and response[4] == 0
            self._log(f"SET_MULTI response: {'OK' if success else 'FAIL'} (status={response[4] if response and len(response) > 4 else 'N/A'})", "HID_RX")

            # Dump FULL raw response and sent packet for byte-level debugging
            if response:
                self._log(f"SET_MULTI FULL TX packet=[{self._hex_bytes(packet[:32])}]", "DEBUG")
                self._log(f"SET_MULTI FULL RX response=[{self._hex_bytes(response[:32])}]", "DEBUG")

            # Parse extended response: readback verification from firmware
            if response and len(response) >= 22:
                sizeof_entry = response[5]
                readback_kcs = []
                for j in range(TOGGLE_MULTI_EXTRA_KEYS):
                    readback_kcs.append(struct.unpack_from('<H', response, 6 + j * 2)[0])
                fw_flags = response[20] if len(response) > 20 else -1
                fw_num_keys = response[21] if len(response) > 21 else -1
                self._log(f"SET_MULTI READBACK: sizeof(toggle_entry_t)={sizeof_entry} flags=0x{fw_flags:02X} num_keys={fw_num_keys}", "DEBUG")
                self._log(f"SET_MULTI READBACK keycodes=[{self._hex_keycodes(readback_kcs)}]", "DEBUG")

                # Compare sent vs readback
                mismatch = False
                for j in range(TOGGLE_MULTI_EXTRA_KEYS):
                    if slot.multi_keycodes[j] != readback_kcs[j]:
                        self._log(f"SET_MULTI MISMATCH at kc[{j}]: sent=0x{slot.multi_keycodes[j]:04X} readback=0x{readback_kcs[j]:04X}", "ERROR")
                        mismatch = True
                if not mismatch:
                    self._log(f"SET_MULTI READBACK: all keycodes match!", "DEBUG")

            return success

        except Exception as e:
            self._log(f"SET_MULTI slot={slot_num}: exception: {e}", "ERROR")
            return False

    def save_to_eeprom(self) -> bool:
        """Save all toggle configurations to EEPROM"""
        try:
            self._log("SAVE_EEPROM", "HID_TX")
            packet = self.keyboard._create_hid_packet(HID_CMD_TOGGLE_SAVE_EEPROM, 0, None)
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)
            success = response and len(response) > 4 and response[4] == 0
            self._log(f"SAVE_EEPROM response: {'OK' if success else 'FAIL'}", "HID_RX")
            return success
        except Exception as e:
            self._log(f"SAVE_EEPROM exception: {e}", "ERROR")
            return False

    def load_from_eeprom(self) -> bool:
        """Load all toggle configurations from EEPROM"""
        try:
            self._log("LOAD_EEPROM", "HID_TX")
            packet = self.keyboard._create_hid_packet(HID_CMD_TOGGLE_LOAD_EEPROM, 0, None)
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            success = response and len(response) > 4 and response[4] == 0
            self._log(f"LOAD_EEPROM response: {'OK' if success else 'FAIL'}", "HID_RX")

            if success:
                self.slots_cache.clear()

            return success
        except Exception as e:
            self._log(f"LOAD_EEPROM exception: {e}", "ERROR")
            return False

    def reset_all_slots(self) -> bool:
        """Reset all toggle slots to defaults"""
        try:
            self._log("RESET_ALL", "HID_TX")
            packet = self.keyboard._create_hid_packet(HID_CMD_TOGGLE_RESET_ALL, 0, None)
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            success = response and len(response) > 4 and response[4] == 0
            self._log(f"RESET_ALL response: {'OK' if success else 'FAIL'}", "HID_RX")

            if success:
                self.slots_cache.clear()

            return success
        except Exception as e:
            self._log(f"RESET_ALL exception: {e}", "ERROR")
            return False

    def clear_cache(self):
        """Clear the slots cache"""
        self.slots_cache.clear()

    def get_all_slots(self) -> List[ToggleSlot]:
        """Load all slots from keyboard"""
        slots = []
        for i in range(TOGGLE_NUM_SLOTS):
            slot = self.get_slot(i)
            if slot:
                slots.append(slot)
            else:
                slots.append(ToggleSlot())
        return slots

    def get_configured_slots(self) -> List[tuple]:
        """Get list of configured (non-empty) slots"""
        configured = []
        for slot_num, slot in self.slots_cache.items():
            if slot.is_enabled():
                configured.append((slot_num, slot))
        return configured
