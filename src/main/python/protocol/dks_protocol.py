# SPDX-License-Identifier: GPL-2.0-or-later
"""
DKS (Dynamic Keystroke) Protocol Handler

Provides communication between the GUI and firmware for DKS configuration.
DKS allows up to 8 actions per key (4 press + 4 release) with customizable
actuation points and behaviors.
"""

import struct
from typing import Optional, Dict, List, Tuple

# DKS HID Command Codes (0xAA-0xAF)
# NOTE: Moved from 0xE5-0xEA to avoid conflict with arpeggiator_hid.c handlers
# (0xE5-0xE6 used for per-key actuation, 0xE7-0xE9 for distance/calibration/EQ)
HID_CMD_DKS_GET_SLOT = 0xAA        # Get DKS slot configuration (26 bytes payload)
HID_CMD_DKS_SET_ACTION = 0xAB      # Set a single DKS action
HID_CMD_DKS_SAVE_EEPROM = 0xAC     # Save all DKS configs to EEPROM
HID_CMD_DKS_LOAD_EEPROM = 0xAD     # Load all DKS configs from EEPROM
HID_CMD_DKS_RESET_SLOT = 0xAE      # Reset a slot to defaults
HID_CMD_DKS_RESET_ALL = 0xAF       # Reset all slots to defaults

# DKS Constants
DKS_NUM_SLOTS = 50                  # Number of DKS slots (DKS_00 - DKS_49)
DKS_ACTIONS_PER_STAGE = 4           # 4 press + 4 release

# Firmware slot is 32 bytes (includes 6 bytes reserved padding), but HID can
# only carry 26 bytes of data (32 byte packet - 6 byte header).  The first 26
# bytes of the slot struct contain all meaningful fields:
#   press_keycode[4]      8 bytes
#   press_actuation[4]    4 bytes
#   release_keycode[4]    8 bytes
#   release_actuation[4]  4 bytes
#   behaviors             2 bytes  = 26 bytes total
# The trailing 6 bytes (reserved[6]) are padding/unused.
DKS_SLOT_SIZE = 32                  # Full firmware struct size
DKS_SLOT_WIRE_SIZE = 26             # Bytes actually transmitted over HID
HID_HEADER_SIZE = 6                 # Header bytes in HID packet

# Behavior Types
DKS_BEHAVIOR_TAP = 0                # Press + immediate release
DKS_BEHAVIOR_PRESS = 1              # Press and hold
DKS_BEHAVIOR_RELEASE = 2            # Release only


class DKSAction:
    """Represents a single DKS action (press or release)"""

    def __init__(self, keycode=0, actuation=50, behavior=DKS_BEHAVIOR_TAP):
        self.keycode = keycode          # Keycode to send (0 = disabled)
        self.actuation = actuation      # Actuation point (0-100 = 0-4.0mm)
        self.behavior = behavior        # TAP/PRESS/RELEASE

    def is_enabled(self):
        """Check if this action is enabled (has a valid keycode)"""
        return self.keycode != 0

    def to_dict(self):
        """Convert to dictionary for GUI"""
        return {
            'keycode': self.keycode,
            'actuation': self.actuation,
            'behavior': self.behavior
        }

    @staticmethod
    def from_dict(data):
        """Create from dictionary"""
        return DKSAction(
            keycode=data.get('keycode', 0),
            actuation=data.get('actuation', 50),
            behavior=data.get('behavior', DKS_BEHAVIOR_TAP)
        )


class DKSSlot:
    """Represents a complete DKS slot configuration"""

    def __init__(self):
        self.press_actions = [DKSAction() for _ in range(DKS_ACTIONS_PER_STAGE)]
        self.release_actions = [DKSAction() for _ in range(DKS_ACTIONS_PER_STAGE)]

    def to_bytes(self):
        """Pack slot into 32-byte firmware format"""
        data = bytearray(DKS_SLOT_SIZE)
        offset = 0

        # Press keycodes (8 bytes)
        for action in self.press_actions:
            struct.pack_into('<H', data, offset, action.keycode)
            offset += 2

        # Press actuation points (4 bytes)
        for action in self.press_actions:
            data[offset] = action.actuation
            offset += 1

        # Release keycodes (8 bytes)
        for action in self.release_actions:
            struct.pack_into('<H', data, offset, action.keycode)
            offset += 2

        # Release actuation points (4 bytes)
        for action in self.release_actions:
            data[offset] = action.actuation
            offset += 1

        # Behaviors (2 bytes, bit-packed)
        behaviors = 0
        for i, action in enumerate(self.press_actions):
            behaviors |= (action.behavior & 0x03) << (i * 2)
        for i, action in enumerate(self.release_actions):
            behaviors |= (action.behavior & 0x03) << ((i + 4) * 2)

        struct.pack_into('<H', data, offset, behaviors)

        return bytes(data)

    @staticmethod
    def from_bytes(data):
        """Unpack slot from firmware format (accepts 26 or 32 bytes).

        The HID response only carries 26 bytes (the meaningful fields).
        The full 32-byte struct has 6 bytes of reserved padding at the end
        which are not transmitted.
        """
        if len(data) < DKS_SLOT_WIRE_SIZE:
            raise ValueError(f"DKS slot data must be at least {DKS_SLOT_WIRE_SIZE} bytes, got {len(data)}")

        slot = DKSSlot()
        offset = 0

        # Press keycodes (8 bytes)
        for i in range(DKS_ACTIONS_PER_STAGE):
            slot.press_actions[i].keycode = struct.unpack_from('<H', data, offset)[0]
            offset += 2

        # Press actuation points (4 bytes)
        for i in range(DKS_ACTIONS_PER_STAGE):
            slot.press_actions[i].actuation = data[offset]
            offset += 1

        # Release keycodes (8 bytes)
        for i in range(DKS_ACTIONS_PER_STAGE):
            slot.release_actions[i].keycode = struct.unpack_from('<H', data, offset)[0]
            offset += 2

        # Release actuation points (4 bytes)
        for i in range(DKS_ACTIONS_PER_STAGE):
            slot.release_actions[i].actuation = data[offset]
            offset += 1

        # Behaviors (2 bytes, bit-packed)
        behaviors = struct.unpack_from('<H', data, offset)[0]
        for i in range(DKS_ACTIONS_PER_STAGE):
            slot.press_actions[i].behavior = (behaviors >> (i * 2)) & 0x03
        for i in range(DKS_ACTIONS_PER_STAGE):
            slot.release_actions[i].behavior = (behaviors >> ((i + 4) * 2)) & 0x03

        return slot

    def to_dict(self):
        """Convert to dictionary for GUI"""
        return {
            'press': [action.to_dict() for action in self.press_actions],
            'release': [action.to_dict() for action in self.release_actions]
        }

    @staticmethod
    def from_dict(data):
        """Create from dictionary"""
        slot = DKSSlot()
        if 'press' in data:
            slot.press_actions = [DKSAction.from_dict(a) for a in data['press']]
        if 'release' in data:
            slot.release_actions = [DKSAction.from_dict(a) for a in data['release']]
        return slot


class ProtocolDKS:
    """DKS protocol handler - manages communication with firmware"""

    def __init__(self, keyboard, debug_log=None):
        """Initialize DKS protocol

        Args:
            keyboard: Keyboard communication object with usb_send and _create_hid_packet methods
            debug_log: Optional callback for debug logging: debug_log(message, level)
        """
        self.keyboard = keyboard
        self.slots_cache = {}  # Cache of loaded slots
        self._debug_log = debug_log

    def _log(self, message, level="DEBUG"):
        """Log a message to the debug console if available"""
        if self._debug_log:
            self._debug_log(message, level)

    def get_slot(self, slot_num: int) -> Optional[DKSSlot]:
        """Get DKS slot configuration from keyboard.

        The firmware sends 26 bytes of slot data (the meaningful fields) in a
        single 32-byte HID packet (6 header + 26 data).  The trailing 6 bytes
        of reserved padding in the firmware struct are NOT transmitted.

        Args:
            slot_num: Slot number (0-49)

        Returns:
            DKSSlot object or None on error
        """
        if slot_num < 0 or slot_num >= DKS_NUM_SLOTS:
            self._log(f"get_slot: invalid slot_num={slot_num} (valid: 0-{DKS_NUM_SLOTS-1})", "ERROR")
            return None

        try:
            # Create HID packet with slot number
            packet = self.keyboard._create_hid_packet(HID_CMD_DKS_GET_SLOT, 0, [slot_num])
            self._log(f"GET slot {slot_num}: TX cmd=0xAA data=[{slot_num}] packet_len={len(packet)}", "HID_TX")
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            if not response or len(response) < (HID_HEADER_SIZE + DKS_SLOT_WIRE_SIZE):
                resp_len = len(response) if response else 0
                self._log(f"GET slot {slot_num}: RX FAILED - response_len={resp_len} (need {HID_HEADER_SIZE + DKS_SLOT_WIRE_SIZE})", "ERROR")
                if response:
                    self._log(f"  Raw response: [{' '.join(f'0x{b:02X}' for b in response[:min(len(response), 32)])}]", "DATA")
                return None

            # Check status byte (response[5])
            if response[5] != 0:  # 0 = success
                self._log(f"GET slot {slot_num}: RX status=0x{response[5]:02X} (expected 0x00)", "ERROR")
                return None

            # Extract slot data (starts at response[6], 26 meaningful bytes)
            slot_data = response[HID_HEADER_SIZE:HID_HEADER_SIZE + DKS_SLOT_WIRE_SIZE]
            slot = DKSSlot.from_bytes(slot_data)

            self._log(f"GET slot {slot_num}: OK - raw=[{' '.join(f'0x{b:02X}' for b in slot_data)}]", "HID_RX")

            # Log parsed slot contents
            for i, a in enumerate(slot.press_actions):
                if a.keycode != 0:
                    self._log(f"  Press[{i}]: kc=0x{a.keycode:04X} act={a.actuation} beh={a.behavior}", "DATA")
            for i, a in enumerate(slot.release_actions):
                if a.keycode != 0:
                    self._log(f"  Release[{i}]: kc=0x{a.keycode:04X} act={a.actuation} beh={a.behavior}", "DATA")

            # Cache it
            self.slots_cache[slot_num] = slot

            return slot

        except Exception as e:
            self._log(f"GET slot {slot_num}: EXCEPTION - {e}", "ERROR")
            print(f"DKS: Error getting slot {slot_num}: {e}")
            return None

    def set_action(self, slot_num: int, is_press: bool, action_index: int,
                   keycode: int, actuation: int, behavior: int) -> bool:
        """Set a single DKS action

        Args:
            slot_num: Slot number (0-49)
            is_press: True for press action, False for release
            action_index: Action index (0-3)
            keycode: Keycode to send
            actuation: Actuation point (0-100, where 100 = 4.0mm)
            behavior: Behavior type (TAP/PRESS/RELEASE)

        Returns:
            True if successful
        """
        stage = "Press" if is_press else "Release"
        beh_names = {0: "TAP", 1: "PRESS", 2: "RELEASE"}
        beh_name = beh_names.get(behavior, f"?{behavior}")

        if slot_num < 0 or slot_num >= DKS_NUM_SLOTS:
            self._log(f"SET action: invalid slot_num={slot_num}", "ERROR")
            return False
        if action_index < 0 or action_index >= DKS_ACTIONS_PER_STAGE:
            self._log(f"SET action: invalid action_index={action_index}", "ERROR")
            return False

        try:
            # Packet format: [slot_num] [is_press] [action_index] [keycode_low] [keycode_high] [actuation] [behavior]
            data = bytearray([
                slot_num,
                1 if is_press else 0,
                action_index,
                keycode & 0xFF,
                (keycode >> 8) & 0xFF,
                actuation,
                behavior
            ])

            self._log(f"SET slot {slot_num} {stage}[{action_index}]: TX cmd=0xAB kc=0x{keycode:04X} act={actuation} beh={beh_name} data=[{' '.join(f'0x{b:02X}' for b in data)}]", "HID_TX")

            packet = self.keyboard._create_hid_packet(HID_CMD_DKS_SET_ACTION, 0, data)
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            success = response and len(response) > 5 and response[5] == 0

            if success:
                self._log(f"SET slot {slot_num} {stage}[{action_index}]: OK (status=0x{response[5]:02X})", "HID_RX")
            else:
                resp_status = f"0x{response[5]:02X}" if response and len(response) > 5 else "NO_RESP"
                resp_len = len(response) if response else 0
                self._log(f"SET slot {slot_num} {stage}[{action_index}]: FAILED status={resp_status} resp_len={resp_len}", "ERROR")
                if response:
                    self._log(f"  Raw response: [{' '.join(f'0x{b:02X}' for b in response[:min(len(response), 20)])}]", "DATA")

            # Update cache if successful
            if success and slot_num in self.slots_cache:
                slot = self.slots_cache[slot_num]
                if is_press:
                    slot.press_actions[action_index].keycode = keycode
                    slot.press_actions[action_index].actuation = actuation
                    slot.press_actions[action_index].behavior = behavior
                else:
                    slot.release_actions[action_index].keycode = keycode
                    slot.release_actions[action_index].actuation = actuation
                    slot.release_actions[action_index].behavior = behavior

            return success

        except Exception as e:
            self._log(f"SET slot {slot_num} {stage}[{action_index}]: EXCEPTION - {e}", "ERROR")
            print(f"DKS: Error setting action: {e}")
            return False

    def save_to_eeprom(self) -> bool:
        """Save all DKS configurations to EEPROM

        Returns:
            True if successful
        """
        try:
            self._log("SAVE TO EEPROM: TX cmd=0xAC (writing all 50 slots)", "HID_TX")
            packet = self.keyboard._create_hid_packet(HID_CMD_DKS_SAVE_EEPROM, 0, None)
            # Use extra retries - firmware writes 50 slots to I2C EEPROM which can take ~300ms
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=5)
            success = response and len(response) > 5 and response[5] == 0
            if success:
                self._log("SAVE TO EEPROM: OK", "HID_RX")
            else:
                resp_status = f"0x{response[5]:02X}" if response and len(response) > 5 else "NO_RESP"
                resp_len = len(response) if response else 0
                self._log(f"SAVE TO EEPROM: FAILED status={resp_status} resp_len={resp_len}", "ERROR")
            return success
        except Exception as e:
            self._log(f"SAVE TO EEPROM: EXCEPTION - {e}", "ERROR")
            print(f"DKS: Error saving to EEPROM: {e}")
            return False

    def load_from_eeprom(self) -> bool:
        """Load all DKS configurations from EEPROM

        Returns:
            True if successful
        """
        try:
            self._log("LOAD FROM EEPROM: TX cmd=0xAD (reading all 50 slots)", "HID_TX")
            packet = self.keyboard._create_hid_packet(HID_CMD_DKS_LOAD_EEPROM, 0, None)
            # Use extra retries - firmware reads 50 slots from I2C EEPROM
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=5)

            success = response and len(response) > 5 and response[5] == 0

            if success:
                self._log("LOAD FROM EEPROM: OK - cache cleared", "HID_RX")
                self.slots_cache.clear()
            else:
                resp_status = f"0x{response[5]:02X}" if response and len(response) > 5 else "NO_RESP"
                resp_len = len(response) if response else 0
                self._log(f"LOAD FROM EEPROM: FAILED status={resp_status} resp_len={resp_len}", "ERROR")

            return success
        except Exception as e:
            self._log(f"LOAD FROM EEPROM: EXCEPTION - {e}", "ERROR")
            print(f"DKS: Error loading from EEPROM: {e}")
            return False

    def reset_slot(self, slot_num: int) -> bool:
        """Reset a DKS slot to defaults

        Args:
            slot_num: Slot number (0-49)

        Returns:
            True if successful
        """
        if slot_num < 0 or slot_num >= DKS_NUM_SLOTS:
            self._log(f"RESET SLOT: invalid slot_num={slot_num}", "ERROR")
            return False

        try:
            self._log(f"RESET SLOT {slot_num}: TX cmd=0xAE", "HID_TX")
            packet = self.keyboard._create_hid_packet(HID_CMD_DKS_RESET_SLOT, 0, [slot_num])
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            success = response and len(response) > 5 and response[5] == 0

            if success:
                self._log(f"RESET SLOT {slot_num}: OK", "HID_RX")
                if slot_num in self.slots_cache:
                    del self.slots_cache[slot_num]
            else:
                resp_status = f"0x{response[5]:02X}" if response and len(response) > 5 else "NO_RESP"
                self._log(f"RESET SLOT {slot_num}: FAILED status={resp_status}", "ERROR")

            return success
        except Exception as e:
            self._log(f"RESET SLOT {slot_num}: EXCEPTION - {e}", "ERROR")
            print(f"DKS: Error resetting slot: {e}")
            return False

    def reset_all_slots(self) -> bool:
        """Reset all DKS slots to defaults

        Returns:
            True if successful
        """
        try:
            self._log("RESET ALL SLOTS: TX cmd=0xAF", "HID_TX")
            packet = self.keyboard._create_hid_packet(HID_CMD_DKS_RESET_ALL, 0, None)
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            success = response and len(response) > 5 and response[5] == 0

            if success:
                self._log("RESET ALL SLOTS: OK - cache cleared", "HID_RX")
                self.slots_cache.clear()
            else:
                resp_status = f"0x{response[5]:02X}" if response and len(response) > 5 else "NO_RESP"
                self._log(f"RESET ALL SLOTS: FAILED status={resp_status}", "ERROR")

            return success
        except Exception as e:
            self._log(f"RESET ALL SLOTS: EXCEPTION - {e}", "ERROR")
            print(f"DKS: Error resetting all slots: {e}")
            return False

    def clear_cache(self):
        """Clear the slots cache"""
        self.slots_cache.clear()
