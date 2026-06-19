# SPDX-License-Identifier: GPL-2.0-or-later
import logging
import os
import pathlib
import sys
import time
from logging.handlers import RotatingFileHandler

from PyQt5.QtCore import QCoreApplication, QStandardPaths
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QApplication, QWidget, QScrollArea, QFrame

from hidproxy import hid
from keycodes.keycodes import Keycode
from keymaps import KEYMAPS

tr = QCoreApplication.translate

# For Vial keyboard
VIAL_SERIAL_NUMBER_MAGIC = "vial:f64c2b3c"

# For bootloader
VIBL_SERIAL_NUMBER_MAGIC = "vibl:d4f8159c"

MSG_LEN = 32

# these should match what we have in vial-qmk/keyboards/vial_example
# so that people don't accidentally reuse a sample keyboard UID
EXAMPLE_KEYBOARDS = [
    0xD4A36200603E3007,  # vial_stm32f103_vibl
    0x32F62BC2EEF2237B,  # vial_atmega32u4
    0x38CEA320F23046A5,  # vial_stm32f072
    0xBED2D31EC59A0BD8,  # vial_stm32f401
]

# anything starting with this prefix should not be allowed
EXAMPLE_KEYBOARD_PREFIX = 0xA6867BDFD3B00F

# Restrict detection to OUR keyboard only — other Vial boards aren't compatible
# with this app's custom features. Fast product-string match happens here at
# enumeration; the unique Vial UID is confirmed before connecting (see
# main_window.on_device_selected).
MIDISWITCH_PRODUCT_STRING = "midiswitch"
# Vial keyboard UID for MIDIswitch (firmware VIAL_KEYBOARD_UID, little-endian uint64)
MIDISWITCH_KEYBOARD_UID = 0xB26D0425F36AC4F4
# Latest firmware version bundled with this GUI release (major, minor, patch).
# Bump in lockstep with the firmware's MIDISWITCH_FW_VERSION_* in config.h so the
# startup "update available" check stays accurate.
LATEST_FIRMWARE_VERSION = (1, 0, 0)


def is_our_keyboard(dev):
    """True if an enumerated HID device's product string is our keyboard."""
    product = dev.get("product_string") or ""
    return MIDISWITCH_PRODUCT_STRING in product.lower()


def hid_send(dev, msg, retries=1):
    if len(msg) > MSG_LEN:
        raise RuntimeError("message must be less than 32 bytes")
    msg += b"\x00" * (MSG_LEN - len(msg))

    data = b""
    first = True

    while retries > 0:
        retries -= 1
        if not first:
            time.sleep(0.5)
        first = False
        try:
            # add 00 at start for hidapi report id
            if dev.write(b"\x00" + msg) != MSG_LEN + 1:
                continue

            data = bytes(dev.read(MSG_LEN, timeout_ms=500))
            if not data:
                continue
        except OSError:
            continue
        break

    if not data:
        raise RuntimeError("failed to communicate with the device")
    return data


def is_rawhid(desc, quiet):
    if desc["usage_page"] != 0xFF60 or desc["usage"] != 0x61:
        if not quiet:
            logging.warning("is_rawhid: {} does not match - usage_page={:04X} usage={:02X}".format(
                desc["path"], desc["usage_page"], desc["usage"]))
        return False

    # there's no reason to check for permission issues on mac or windows
    # and mac won't let us reopen an opened device
    # so skip the rest of the checks for non-linux
    if not sys.platform.startswith("linux"):
        return True

    dev = hid.device()

    try:
        dev.open_path(desc["path"])
    except OSError as e:
        if not quiet:
            logging.warning("is_rawhid: {} does not match - open_path error {}".format(desc["path"], e))
        return False

    dev.close()
    return True


def find_vial_devices(via_stack_json, sideload_vid=None, sideload_pid=None, quiet=False):
    from vial_device import VialBootloader, VialKeyboard, VialDummyKeyboard

    # Startup logging
    try:
        from startup_dialog import startup_log
        startup_log("Enumerating HID devices...")
    except ImportError:
        startup_log = lambda x: None

    import time
    t0 = time.time()
    all_devices = list(hid.enumerate())
    startup_log(f"Found {len(all_devices)} HID devices ({time.time()-t0:.2f}s)")

    filtered = []
    for dev in all_devices:
        if dev["vendor_id"] == sideload_vid and dev["product_id"] == sideload_pid:
            if not quiet:
                logging.info("Trying VID={:04X}, PID={:04X}, serial={}, path={} - sideload".format(
                    dev["vendor_id"], dev["product_id"], dev["serial_number"], dev["path"]
                ))
            if is_rawhid(dev, quiet):
                filtered.append(VialKeyboard(dev, sideload=True))
        elif VIAL_SERIAL_NUMBER_MAGIC in dev["serial_number"] and is_our_keyboard(dev):
            if not quiet:
                logging.info("Matching VID={:04X}, PID={:04X}, serial={}, path={} - vial serial magic".format(
                    dev["vendor_id"], dev["product_id"], dev["serial_number"], dev["path"]
                ))
            if is_rawhid(dev, quiet):
                filtered.append(VialKeyboard(dev))
        elif VIBL_SERIAL_NUMBER_MAGIC in dev["serial_number"]:
            if not quiet:
                logging.info("Matching VID={:04X}, PID={:04X}, serial={}, path={} - vibl serial magic".format(
                    dev["vendor_id"], dev["product_id"], dev["serial_number"], dev["path"]
                ))
            filtered.append(VialBootloader(dev))
        elif str(dev["vendor_id"] * 65536 + dev["product_id"]) in via_stack_json["definitions"] and is_our_keyboard(dev):
            if not quiet:
                logging.info("Matching VID={:04X}, PID={:04X}, serial={}, path={} - VIA stack".format(
                    dev["vendor_id"], dev["product_id"], dev["serial_number"], dev["path"]
                ))
            if is_rawhid(dev, quiet):
                filtered.append(VialKeyboard(dev, via_stack=True))

    if sideload_vid == sideload_pid == 0:
        filtered.append(VialDummyKeyboard())

    startup_log(f"Found {len(filtered)} Vial-compatible device(s)")
    return filtered


def chunks(data, sz):
    for i in range(0, len(data), sz):
        yield data[i:i+sz]


def pad_for_vibl(msg):
    """ Pads message to vibl fixed 64-byte length """
    if len(msg) > 64:
        raise RuntimeError("vibl message too long")
    return msg + b"\x00" * (64 - len(msg))


def init_logger():
    logging.basicConfig(level=logging.INFO)
    directory = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
    path = os.path.join(directory, "vial.log")
    handler = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=5)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"))
    logging.getLogger().addHandler(handler)


def make_scrollable(layout):
    w = QWidget()
    w.setLayout(layout)
    w.setObjectName("w")
    scroll = QScrollArea()
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setStyleSheet("QScrollArea { background-color:transparent; }")
    w.setStyleSheet("#w { background-color:transparent; }")
    scroll.setWidgetResizable(True)
    scroll.setWidget(w)
    return scroll


class KeycodeDisplay:

    keymap_override = KEYMAPS[0][1]
    clients = []

    @staticmethod
    def _wrap_label(name):
        """Wrap a custom name for key button display.
        Break at spaces or every 6 chars, max 3 lines (2 newlines)."""
        if not name:
            return name
        lines = []
        current = ""
        for ch in name:
            if ch == ' ' and current:
                lines.append(current)
                current = ""
                if len(lines) >= 3:
                    break
                continue
            current += ch
            if len(current) >= 6:
                lines.append(current)
                current = ""
                if len(lines) >= 3:
                    break
        if current and len(lines) < 3:
            lines.append(current)
        return "\n".join(lines)

    @classmethod
    def get_custom_name_label(cls, qmk_id):
        """Check if this keycode has a custom name from feature_names.
        Returns the custom label string (wrapped for button display) or None."""
        try:
            from protocol.feature_names import (get_feature_name_manager,
                FEATURE_MACRO, FEATURE_TOGGLE, FEATURE_ARP, FEATURE_SEQ, FEATURE_DELAY)
            mgr = get_feature_name_manager()

            # Macro: M0-M127
            if qmk_id.startswith("M") and qmk_id[1:].isdigit():
                idx = int(qmk_id[1:])
                if mgr.has_custom_name(FEATURE_MACRO, idx):
                    return cls._wrap_label(mgr.get_name(FEATURE_MACRO, idx))

            # Toggle: TGL_00-TGL_99
            if qmk_id.startswith("TGL_") and len(qmk_id) > 4 and qmk_id[4:].isdigit():
                idx = int(qmk_id[4:])
                if mgr.has_custom_name(FEATURE_TOGGLE, idx):
                    return cls._wrap_label(mgr.get_name(FEATURE_TOGGLE, idx))

            # Arp user presets: ARP_PRESET_48-ARP_PRESET_67
            if qmk_id.startswith("ARP_PRESET_") and qmk_id[11:].isdigit():
                idx = int(qmk_id[11:])
                if idx >= 48:
                    user_idx = idx - 48
                    if mgr.has_custom_name(FEATURE_ARP, user_idx):
                        return cls._wrap_label(mgr.get_name(FEATURE_ARP, user_idx))

            # Seq user presets: SEQ_PRESET_48-SEQ_PRESET_67
            if qmk_id.startswith("SEQ_PRESET_") and qmk_id[11:].isdigit():
                idx = int(qmk_id[11:])
                if idx >= 48:
                    user_idx = idx - 48
                    if mgr.has_custom_name(FEATURE_SEQ, user_idx):
                        return cls._wrap_label(mgr.get_name(FEATURE_SEQ, user_idx))

            # Delay user slots: DELAY_49-DELAY_98 (unified index, user starts at 49)
            if qmk_id.startswith("DELAY_") and qmk_id[6:].isdigit():
                idx = int(qmk_id[6:])
                if idx > 48:
                    user_idx = idx - 49
                    if mgr.has_custom_name(FEATURE_DELAY, user_idx):
                        return cls._wrap_label(mgr.get_name(FEATURE_DELAY, user_idx))

        except Exception:
            pass
        return None

    @classmethod
    def get_label(cls, code):
        """ Get label for a specific keycode """
        custom = cls.get_custom_name_label(code)
        if custom:
            return custom
        if cls.code_is_overriden(code):
            return cls.keymap_override[Keycode.find_outer_keycode(code).qmk_id]
        return Keycode.label(code)

    @classmethod
    def code_is_overriden(cls, code):
        """ Check whether a country-specific keymap overrides a code """
        key = Keycode.find_outer_keycode(code)
        return key is not None and key.qmk_id in cls.keymap_override

    @classmethod
    def display_keycode(cls, widget, code):
        custom = cls.get_custom_name_label(code)
        if custom:
            text = custom
        else:
            text = cls.get_label(code)
        tooltip = Keycode.tooltip(code)
        mask = Keycode.is_mask(code)
        mask_text = ""
        inner = Keycode.find_inner_keycode(code)
        if inner:
            mask_text = cls.get_label(inner.qmk_id)
        if mask and not custom:
            text = text.split("\n")[0]
        widget.masked = mask if not custom else False
        widget.setText(text)
        widget.setMaskText(mask_text if not custom else "")
        widget.setToolTip(tooltip)
        if cls.code_is_overriden(code):
            widget.setColor(QApplication.palette().color(QPalette.Link))
        else:
            widget.setColor(None)
        if inner and mask and cls.code_is_overriden(inner.qmk_id):
            widget.setMaskColor(QApplication.palette().color(QPalette.Link))
        else:
            widget.setMaskColor(None)

    @classmethod
    def set_keymap_override(cls, override):
        cls.keymap_override = override
        for client in cls.clients:
            client.on_keymap_override()

    @classmethod
    def notify_keymap_override(cls, client):
        cls.clients.append(client)
        client.on_keymap_override()

    @classmethod
    def unregister_keymap_override(cls, client):
        cls.clients.remove(client)

    @classmethod
    def relabel_buttons(cls, buttons):
        for widget in buttons:
            qmk_id = widget.keycode.qmk_id
            custom = cls.get_custom_name_label(qmk_id)
            if custom:
                label = custom
                widget.setStyleSheet("QPushButton {}")
            elif qmk_id in KeycodeDisplay.keymap_override:
                label = KeycodeDisplay.keymap_override[qmk_id]
                highlight_color = QApplication.palette().color(QPalette.Link).getRgb()
                widget.setStyleSheet("QPushButton {color: rgb%s;}" % str(highlight_color))
            else:
                label = widget.keycode.label
                widget.setStyleSheet("QPushButton {}")
            widget.setText(label.replace("&", "&&"))
