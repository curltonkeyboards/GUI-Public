# SPDX-License-Identifier: GPL-2.0-or-later
"""
Null Bind Protocol Handler

Provides SOCD (Simultaneous Opposing Cardinal Directions) handling through
null bind groups. Each group contains multiple keys that interact according
to a configured behavior when pressed simultaneously.

Behaviors:
- NEUTRAL: All keys in group are nulled when 2+ are pressed
- LAST_INPUT: Only the last pressed key is active, others nulled
- DISTANCE: Key pressed further (more travel) wins, others nulled
- PRIORITY_KEY_X: Absolute priority for key X in the group
  - Priority key cannot be nulled by other keys
  - Other keys are nulled when priority key is held
  - Other keys activate when priority key releases
"""

import struct
from typing import Optional, List, Tuple

# Null Bind HID Command Codes (0xF0-0xF4)
HID_CMD_NULLBIND_GET_GROUP = 0xF0      # Get null bind group configuration
HID_CMD_NULLBIND_SET_GROUP = 0xF1      # Set null bind group configuration
HID_CMD_NULLBIND_SAVE_EEPROM = 0xF2    # Save all groups to EEPROM
HID_CMD_NULLBIND_LOAD_EEPROM = 0xF3    # Load all groups from EEPROM
HID_CMD_NULLBIND_RESET_ALL = 0xF4      # Reset all groups to defaults

# Null Bind Constants
NULLBIND_NUM_GROUPS = 20               # Number of null bind groups
NULLBIND_MAX_KEYS_PER_GROUP = 8        # Maximum keys per group
NULLBIND_GROUP_SIZE = 18               # Bytes per group in firmware
NULLBIND_LAYER_ALL = 0xFF             # layer value = "all layers" (global group)
NULLBIND_GLOBAL_SELECTOR = 0xFF       # group_num that selects the global-settings sub-command

# Behavior Types
# Base behaviors (0-2)
NULLBIND_BEHAVIOR_NEUTRAL = 0          # All keys nulled when 2+ pressed
NULLBIND_BEHAVIOR_LAST_INPUT = 1       # Last pressed key wins
NULLBIND_BEHAVIOR_DISTANCE = 2         # Key with more travel wins

# Priority behaviors (3+): PRIORITY_KEY_0, PRIORITY_KEY_1, etc.
# behavior = 3 + key_index means that key has absolute priority
NULLBIND_BEHAVIOR_PRIORITY_BASE = 3

def get_behavior_name(behavior: int, key_count: int = 0) -> str:
    """Get human-readable name for a behavior"""
    if behavior == NULLBIND_BEHAVIOR_NEUTRAL:
        return "Neutral (All Null)"
    elif behavior == NULLBIND_BEHAVIOR_LAST_INPUT:
        return "Last Input Priority"
    elif behavior == NULLBIND_BEHAVIOR_DISTANCE:
        return "Distance Priority"
    elif behavior >= NULLBIND_BEHAVIOR_PRIORITY_BASE:
        key_idx = behavior - NULLBIND_BEHAVIOR_PRIORITY_BASE
        return f"Priority: Key {key_idx + 1}"
    return f"Unknown ({behavior})"

def get_behavior_choices(key_count: int) -> List[Tuple[int, str]]:
    """Get list of (behavior_value, name) tuples for a group with N keys"""
    choices = [
        (NULLBIND_BEHAVIOR_NEUTRAL, "Neutral (All Null)"),
        (NULLBIND_BEHAVIOR_LAST_INPUT, "Last Input Priority"),
        (NULLBIND_BEHAVIOR_DISTANCE, "Distance Priority"),
    ]
    # Add absolute priority options for each key in the group
    for i in range(key_count):
        behavior = NULLBIND_BEHAVIOR_PRIORITY_BASE + i
        choices.append((behavior, f"Absolute Priority: Key {i + 1}"))
    return choices


class NullBindGroup:
    """Represents a null bind group configuration

    NOTE: Groups are now layer-specific. Each group is assigned to a single layer
    and only activates when that layer is active.
    """

    def __init__(self):
        self.behavior = NULLBIND_BEHAVIOR_NEUTRAL
        self.keys = []  # List of key indices (row * 14 + col for 5x14 keyboard)
        self.layer = 0  # Layer this group is active on (0-11)

    @property
    def key_count(self) -> int:
        return len(self.keys)

    def add_key(self, key_index: int) -> bool:
        """Add a key to the group

        Args:
            key_index: Key index (row * 14 + col)

        Returns:
            True if added, False if group full or key already exists
        """
        if len(self.keys) >= NULLBIND_MAX_KEYS_PER_GROUP:
            return False
        if key_index in self.keys:
            return False
        self.keys.append(key_index)
        return True

    def remove_key(self, key_index: int) -> bool:
        """Remove a key from the group

        Args:
            key_index: Key index to remove

        Returns:
            True if removed, False if not found
        """
        if key_index in self.keys:
            # Resolve the key that currently holds priority (by key index, not
            # array position) BEFORE mutating the list, so removing a
            # lower-indexed key can't silently reassign priority to a different
            # surviving key.
            priority_key = None
            if self.behavior >= NULLBIND_BEHAVIOR_PRIORITY_BASE:
                priority_idx = self.behavior - NULLBIND_BEHAVIOR_PRIORITY_BASE
                if priority_idx < len(self.keys):
                    priority_key = self.keys[priority_idx]

            self.keys.remove(key_index)

            # Re-derive the priority behavior from the priority key's new position
            if self.behavior >= NULLBIND_BEHAVIOR_PRIORITY_BASE:
                if priority_key is None or priority_key == key_index or priority_key not in self.keys:
                    # The priority key itself was removed -> reset to neutral
                    self.behavior = NULLBIND_BEHAVIOR_NEUTRAL
                else:
                    self.behavior = NULLBIND_BEHAVIOR_PRIORITY_BASE + self.keys.index(priority_key)
            return True
        return False

    def clear(self):
        """Clear all keys from the group"""
        self.keys = []
        self.behavior = NULLBIND_BEHAVIOR_NEUTRAL
        # Note: layer is preserved when clearing

    def has_key(self, key_index: int) -> bool:
        """Check if a key is in this group"""
        return key_index in self.keys

    def get_priority_key_index(self) -> Optional[int]:
        """Get the index of the priority key if behavior is absolute priority

        Returns:
            Key index with priority, or None if not priority behavior
        """
        if self.behavior >= NULLBIND_BEHAVIOR_PRIORITY_BASE:
            priority_idx = self.behavior - NULLBIND_BEHAVIOR_PRIORITY_BASE
            if priority_idx < len(self.keys):
                return self.keys[priority_idx]
        return None

    def set_priority_key(self, key_index: int) -> bool:
        """Set a key as the absolute priority key

        Args:
            key_index: Key index to set as priority

        Returns:
            True if set, False if key not in group
        """
        if key_index not in self.keys:
            return False
        idx_in_group = self.keys.index(key_index)
        self.behavior = NULLBIND_BEHAVIOR_PRIORITY_BASE + idx_in_group
        return True

    def to_bytes(self) -> bytes:
        """Pack group into firmware format (18 bytes)

        Format:
        - byte 0: behavior
        - byte 1: key_count
        - bytes 2-9: keys[8] (padded with 0xFF for unused)
        - byte 10: layer (0-11, which layer this group is active on)
        - bytes 11-17: reserved (for future use)
        """
        data = bytearray(NULLBIND_GROUP_SIZE)
        data[0] = self.behavior
        data[1] = len(self.keys)

        # Pack keys (0xFF = unused slot)
        for i in range(NULLBIND_MAX_KEYS_PER_GROUP):
            if i < len(self.keys):
                data[2 + i] = self.keys[i]
            else:
                data[2 + i] = 0xFF

        # Layer field (byte 10). 0-11 = a specific layer, 0xFF = all layers
        # (global group). Anything else is coerced to layer 0.
        if self.layer == NULLBIND_LAYER_ALL or self.layer < 12:
            data[10] = self.layer
        else:
            data[10] = 0

        # Reserved bytes (11-17) already 0
        return bytes(data)

    @staticmethod
    def from_bytes(data: bytes) -> 'NullBindGroup':
        """Unpack group from firmware format"""
        if len(data) < NULLBIND_GROUP_SIZE:
            raise ValueError(f"NullBind group data must be {NULLBIND_GROUP_SIZE} bytes")

        group = NullBindGroup()
        group.behavior = data[0]
        key_count = data[1]

        # Unpack keys (skip 0xFF entries)
        group.keys = []
        for i in range(min(key_count, NULLBIND_MAX_KEYS_PER_GROUP)):
            key = data[2 + i]
            if key != 0xFF:
                group.keys.append(key)

        # Layer field (byte 10). 0xFF = all layers (global group); 0-11 = a
        # specific layer; anything else is treated as layer 0.
        group.layer = data[10] if (data[10] == NULLBIND_LAYER_ALL or data[10] < 12) else 0

        return group

    def to_dict(self) -> dict:
        """Convert to dictionary for GUI"""
        return {
            'behavior': self.behavior,
            'keys': list(self.keys),
            'layer': self.layer
        }

    @staticmethod
    def from_dict(data: dict) -> 'NullBindGroup':
        """Create from dictionary"""
        group = NullBindGroup()
        group.behavior = data.get('behavior', NULLBIND_BEHAVIOR_NEUTRAL)
        group.keys = list(data.get('keys', []))
        group.layer = data.get('layer', 0)
        return group


class ProtocolNullBind:
    """Null Bind protocol handler - manages communication with firmware"""

    def __init__(self, keyboard):
        """Initialize Null Bind protocol

        Args:
            keyboard: Keyboard communication object
        """
        self.keyboard = keyboard
        self.groups_cache = {}  # Cache of loaded groups

    def get_group(self, group_num: int) -> Optional[NullBindGroup]:
        """Get null bind group configuration from keyboard

        Args:
            group_num: Group number (0-19)

        Returns:
            NullBindGroup object or None on error
        """
        if group_num < 0 or group_num >= NULLBIND_NUM_GROUPS:
            return None

        try:
            packet = self.keyboard._create_hid_packet(HID_CMD_NULLBIND_GET_GROUP, 0, [group_num])
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            if not response or len(response) < (5 + NULLBIND_GROUP_SIZE):
                return None

            # Verify the command byte (response[3]) — hid_send does not correlate
            # responses to commands, so a stale packet from another command could
            # otherwise be parsed as this group's data.
            if response[3] != HID_CMD_NULLBIND_GET_GROUP:
                return None

            # Check status byte (firmware puts it at index 4)
            if response[4] != 0:
                return None

            # Extract group data (firmware puts it at index 5)
            group_data = response[5:5 + NULLBIND_GROUP_SIZE]
            group = NullBindGroup.from_bytes(group_data)

            # Cache it
            self.groups_cache[group_num] = group

            return group

        except Exception as e:
            print(f"NullBind: Error getting group {group_num}: {e}")
            return None

    def set_group(self, group_num: int, group: NullBindGroup) -> bool:
        """Set null bind group configuration

        Args:
            group_num: Group number (0-19)
            group: NullBindGroup configuration

        Returns:
            True if successful
        """
        if group_num < 0 or group_num >= NULLBIND_NUM_GROUPS:
            return False

        try:
            # Packet: [group_num] + group_data (18 bytes)
            data = bytearray([group_num]) + bytearray(group.to_bytes())

            packet = self.keyboard._create_hid_packet(HID_CMD_NULLBIND_SET_GROUP, 0, data)
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            success = response and len(response) > 4 and response[4] == 0

            # Update cache
            if success:
                self.groups_cache[group_num] = group

            return success

        except Exception as e:
            print(f"NullBind: Error setting group {group_num}: {e}")
            return False

    def save_to_eeprom(self) -> bool:
        """Save all null bind configurations to EEPROM

        Returns:
            True if successful
        """
        try:
            packet = self.keyboard._create_hid_packet(HID_CMD_NULLBIND_SAVE_EEPROM, 0, None)
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)
            return response and len(response) > 4 and response[4] == 0
        except Exception as e:
            print(f"NullBind: Error saving to EEPROM: {e}")
            return False

    def load_from_eeprom(self) -> bool:
        """Load all null bind configurations from EEPROM

        Returns:
            True if successful
        """
        try:
            packet = self.keyboard._create_hid_packet(HID_CMD_NULLBIND_LOAD_EEPROM, 0, None)
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            success = response and len(response) > 4 and response[4] == 0

            if success:
                self.groups_cache.clear()

            return success
        except Exception as e:
            print(f"NullBind: Error loading from EEPROM: {e}")
            return False

    def reset_all_groups(self) -> bool:
        """Reset all null bind groups to defaults

        Returns:
            True if successful
        """
        try:
            packet = self.keyboard._create_hid_packet(HID_CMD_NULLBIND_RESET_ALL, 0, None)
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            success = response and len(response) > 4 and response[4] == 0

            if success:
                self.groups_cache.clear()

            return success
        except Exception as e:
            print(f"NullBind: Error resetting groups: {e}")
            return False

    def get_enabled(self) -> Optional[bool]:
        """Read the global SOCD / null-bind enable flag from the keyboard.

        Uses the GET_GROUP command with the special group selector 0xFF (the
        firmware returns the enable flag in place of group data). Returns None
        on error (e.g. firmware too old to answer) so the caller can default.
        """
        try:
            packet = self.keyboard._create_hid_packet(
                HID_CMD_NULLBIND_GET_GROUP, 0, [NULLBIND_GLOBAL_SELECTOR])
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)

            if not response or len(response) < 6:
                return None
            if response[3] != HID_CMD_NULLBIND_GET_GROUP:
                return None
            if response[4] != 0:  # status byte
                return None
            return response[5] != 0
        except Exception as e:
            print(f"NullBind: Error getting enable flag: {e}")
            return None

    def set_enabled(self, enabled: bool) -> bool:
        """Set the global SOCD / null-bind enable flag (RAM only).

        Uses SET_GROUP with the special selector 0xFF. Not persisted until
        save_to_eeprom() runs (the normal Save flow calls it).
        """
        try:
            data = bytearray([NULLBIND_GLOBAL_SELECTOR, 1 if enabled else 0])
            packet = self.keyboard._create_hid_packet(
                HID_CMD_NULLBIND_SET_GROUP, 0, data)
            response = self.keyboard.usb_send(self.keyboard.dev, packet, retries=3)
            return bool(response) and len(response) > 4 and response[4] == 0
        except Exception as e:
            print(f"NullBind: Error setting enable flag: {e}")
            return False

    def clear_cache(self):
        """Clear the groups cache"""
        self.groups_cache.clear()

    def get_all_groups(self) -> List[NullBindGroup]:
        """Load all groups from keyboard

        Returns:
            List of all NullBindGroup objects
        """
        groups = []
        for i in range(NULLBIND_NUM_GROUPS):
            group = self.get_group(i)
            if group:
                groups.append(group)
            else:
                groups.append(NullBindGroup())  # Default empty group
        return groups

    def find_key_group(self, key_index: int) -> Optional[int]:
        """Find which group a key belongs to

        Args:
            key_index: Key index to search for

        Returns:
            Group number (0-19) or None if not in any group
        """
        for group_num, group in self.groups_cache.items():
            if group.has_key(key_index):
                return group_num
        return None
