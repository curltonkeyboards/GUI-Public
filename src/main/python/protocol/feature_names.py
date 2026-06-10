# SPDX-License-Identifier: GPL-2.0-or-later
"""
Manages user-defined names for macros, toggles, arp/seq presets, and delay slots.
Names are persisted locally per-device in a JSON file AND synced to the keyboard's
EEPROM via HID so they appear on the OLED display.
"""

import json
import os
import struct

from PyQt5.QtCore import QStandardPaths


# Feature type keys (must match firmware CN_CAT_* constants)
FEATURE_MACRO = "macro"
FEATURE_TOGGLE = "toggle"
FEATURE_ARP = "arp"
FEATURE_SEQ = "seq"
FEATURE_DELAY = "delay"
FEATURE_LAYER = "layer"

# Firmware category IDs (match custom_names.h CN_CAT_*)
_CAT_IDS = {
    FEATURE_MACRO: 0,
    FEATURE_TOGGLE: 1,
    FEATURE_ARP: 2,
    FEATURE_SEQ: 3,
    FEATURE_DELAY: 4,
    FEATURE_LAYER: 5,
}

# Default name formats per feature type
DEFAULT_FORMATS = {
    FEATURE_MACRO: "M{}",
    FEATURE_TOGGLE: "TGL_{:02d}",
    FEATURE_ARP: "User Arp {}",
    FEATURE_SEQ: "User Seq {}",
    FEATURE_DELAY: "Delay {}",
    FEATURE_LAYER: "Layer {}",
}

# Maximum name length (must match firmware CUSTOM_NAME_LENGTH)
MAX_NAME_LENGTH = 16

# HID command ID (must match firmware custom_names.h)
# Single command 0xCD with sub-commands in payload[0] (data[4])
HID_CMD_CUSTOM_NAMES = 0xCD

# Sub-command IDs (sent as first payload byte)
CN_SUB_SET_NAME = 0x00
CN_SUB_GET_NAME = 0x01
CN_SUB_GET_BULK = 0x02
CN_SUB_SAVE = 0x03
CN_SUB_RESET = 0x04
CN_SUB_GET_INFO = 0x05

# HID protocol constants
HID_MANUFACTURER_ID = 0x7D
HID_SUB_ID = 0x00
HID_DEVICE_ID = 0x4D


class FeatureNameManager:
    """Stores and retrieves user-defined names for keyboard features.

    Names are persisted to a JSON file in the app cache directory,
    keyed by keyboard_id and feature type. When a keyboard device is
    connected, names are also synced to the firmware's EEPROM via HID
    so they can be displayed on the keyboard's OLED.
    """

    def __init__(self):
        self._names = {}  # {feature_type: {index: name}}
        self._keyboard_id = None
        self._file_path = None
        self._keyboard = None  # Keyboard comm object for HID sync

    def set_keyboard(self, keyboard_id, keyboard=None):
        """Set the current keyboard and load its names from disk.

        Args:
            keyboard_id: Unique identifier for the keyboard
            keyboard: Optional Keyboard comm object for HID sync
        """
        self._keyboard_id = keyboard_id
        self._keyboard = keyboard
        self._names = {}

        cache_dir = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
        names_dir = os.path.join(cache_dir, "feature_names")
        if not os.path.exists(names_dir):
            os.makedirs(names_dir)

        self._file_path = os.path.join(names_dir, "{}.json".format(keyboard_id))
        self._load()

    def set_keyboard_comm(self, keyboard):
        """Set or update the keyboard communication object for HID sync."""
        self._keyboard = keyboard

    def _load(self):
        """Load names from JSON file."""
        if self._file_path and os.path.isfile(self._file_path):
            try:
                with open(self._file_path, "r") as f:
                    self._names = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._names = {}

    def _save(self):
        """Save names to JSON file."""
        if not self._file_path:
            return
        try:
            with open(self._file_path, "w") as f:
                json.dump(self._names, f, indent=2)
        except IOError:
            pass

    def get_name(self, feature_type, index):
        """Get the name for a feature slot, or the default if not set."""
        names = self._names.get(feature_type, {})
        custom = names.get(str(index))
        if custom:
            return custom
        fmt = DEFAULT_FORMATS.get(feature_type, "Item {}")
        # Arp and Seq use 1-based display index
        if feature_type in (FEATURE_ARP, FEATURE_SEQ, FEATURE_DELAY):
            return fmt.format(index + 1)
        return fmt.format(index)

    def set_name(self, feature_type, index, name):
        """Set a custom name for a feature slot. Empty string clears it.

        Also syncs to keyboard EEPROM via HID if connected.
        """
        if feature_type not in self._names:
            self._names[feature_type] = {}

        name = name.strip()[:MAX_NAME_LENGTH]
        # Layer names are always uppercase (matches OLED display)
        if feature_type == FEATURE_LAYER:
            name = name.upper()
        if name:
            self._names[feature_type][str(index)] = name
        else:
            # Clear custom name (revert to default)
            self._names[feature_type].pop(str(index), None)
            # Clean up empty dicts
            if not self._names[feature_type]:
                del self._names[feature_type]

        self._save()

        # Sync to firmware EEPROM
        self._hid_set_name(feature_type, index, name)

    def has_custom_name(self, feature_type, index):
        """Check if a feature slot has a custom name."""
        names = self._names.get(feature_type, {})
        return str(index) in names

    def get_default_name(self, feature_type, index):
        """Get the default name for a feature slot (ignoring custom names)."""
        fmt = DEFAULT_FORMATS.get(feature_type, "Item {}")
        if feature_type in (FEATURE_ARP, FEATURE_SEQ, FEATURE_DELAY):
            return fmt.format(index + 1)
        return fmt.format(index)

    # =========================================================================
    # HID SYNC - Send names to keyboard firmware EEPROM
    # =========================================================================

    def _build_hid_packet(self, cmd, payload=None):
        """Build a 32-byte HID packet with standard header."""
        data = bytearray(32)
        data[0] = HID_MANUFACTURER_ID
        data[1] = HID_SUB_ID
        data[2] = HID_DEVICE_ID
        data[3] = cmd
        if payload:
            for i, b in enumerate(payload):
                if 4 + i < 32:
                    data[4 + i] = b & 0xFF
        return bytes(data)

    def _hid_send(self, packet):
        """Send HID packet and return response, or None on failure."""
        if not self._keyboard or not self._keyboard.dev:
            return None
        try:
            return self._keyboard.usb_send(self._keyboard.dev, packet, retries=3)
        except Exception:
            return None

    def _hid_set_name(self, feature_type, index, name):
        """Send a single name to the firmware via HID."""
        cat_id = _CAT_IDS.get(feature_type)
        if cat_id is None:
            return False

        # Build payload: [sub_cmd, cat, index, name_bytes[16]]
        name_bytes = (name or "").encode("ascii", errors="replace")[:MAX_NAME_LENGTH - 1]
        payload = bytearray(3 + MAX_NAME_LENGTH)
        payload[0] = CN_SUB_SET_NAME
        payload[1] = cat_id
        payload[2] = index & 0xFF
        for i, b in enumerate(name_bytes):
            payload[3 + i] = b

        packet = self._build_hid_packet(HID_CMD_CUSTOM_NAMES, payload)
        response = self._hid_send(packet)
        if response and len(response) > 5:
            return response[5] == 0  # 0 = success (response[4]=sub, response[5]=status)
        return False

    def sync_all_to_firmware(self):
        """Sync all custom names to the firmware EEPROM.

        Call this after connecting to a keyboard to push all local names
        to the firmware so they show on the OLED.
        """
        if not self._keyboard:
            return False

        synced = 0
        for feature_type, names in self._names.items():
            for idx_str, name in names.items():
                try:
                    idx = int(idx_str)
                except ValueError:
                    continue
                if self._hid_set_name(feature_type, idx, name):
                    synced += 1

        return synced > 0

    def sync_category_to_firmware(self, feature_type):
        """Sync all names for a specific category to firmware."""
        if not self._keyboard:
            return False

        names = self._names.get(feature_type, {})
        for idx_str, name in names.items():
            try:
                idx = int(idx_str)
            except ValueError:
                continue
            self._hid_set_name(feature_type, idx, name)
        return True


# Singleton instance
_instance = None


def get_feature_name_manager():
    """Get the singleton FeatureNameManager instance."""
    global _instance
    if _instance is None:
        _instance = FeatureNameManager()
    return _instance
