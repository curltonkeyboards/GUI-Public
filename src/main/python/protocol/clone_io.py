# SPDX-License-Identifier: GPL-2.0-or-later
"""Keyboard clone transfer without any UI, for background threads.

Same .kbclone file format as File > Save / Load keyboard clone. Used by the
firmware updater to back the settings up before an update and put them
back afterwards.
"""
import base64
import datetime
import glob
import json
import os

CLONE_FILE_MAGIC = "midiswitch-keyboard-clone"
BACKUPS_KEPT = 5


class CloneError(Exception):
    pass


def _transfer_active(active):
    try:
        from util import set_hid_transfer_active
    except ImportError:
        return
    set_hid_transfer_active(active)


def read_image(keyboard, info, progress=None):
    """Read the whole settings memory. Returns bytes."""
    size, chunk = info["eeprom_size"], info["chunk_size"]
    blob = bytearray()
    _transfer_active(True)
    try:
        addr = 0
        while addr < size:
            length = min(chunk, size - addr)
            data = None
            for _ in range(3):
                data = keyboard.clone_read_chunk(addr, length)
                if data is not None:
                    break
            if data is None:
                raise CloneError("reading the keyboard's settings failed at address %d" % addr)
            blob.extend(data)
            addr += length
            if progress:
                progress(addr / size)
    finally:
        _transfer_active(False)
    return bytes(blob)


def write_image(keyboard, info, blob, progress=None):
    """Write the whole settings memory (does not finalize)."""
    size, chunk = info["eeprom_size"], info["chunk_size"]
    if len(blob) != size:
        raise CloneError("the backup holds %d bytes but the keyboard has %d" % (len(blob), size))
    _transfer_active(True)
    try:
        addr = 0
        while addr < size:
            length = min(chunk, size - addr)
            ok = False
            for _ in range(3):
                if keyboard.clone_write_chunk(addr, blob[addr:addr + length]):
                    ok = True
                    break
            if not ok:
                raise CloneError("writing the keyboard's settings failed at address %d" % addr)
            addr += length
            if progress:
                progress(addr / size)
    finally:
        _transfer_active(False)


def to_dict(blob, info):
    return {
        "magic": CLONE_FILE_MAGIC,
        "file_version": 1,
        "eeprom_layout_version": info["layout_version"],
        "eeprom_size": info["eeprom_size"],
        "firmware_version": list(info["fw_version"]),
        "data": base64.b64encode(bytes(blob)).decode("ascii"),
    }


def save_file(path, blob, info):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_dict(blob, info), f)


def load_file(path):
    """Returns (blob, layout_version)."""
    with open(path, "r", encoding="utf-8") as f:
        clone = json.load(f)
    if clone.get("magic") != CLONE_FILE_MAGIC:
        raise CloneError("not a keyboard clone file")
    blob = base64.b64decode(clone["data"])
    if len(blob) != int(clone["eeprom_size"]):
        raise CloneError("clone data size does not match its header")
    return blob, int(clone["eeprom_layout_version"])


# ---- Automatic backups ---------------------------------------------------------

def backup_dir():
    # A fixed "MIDIswitch" folder under the per-user data directory, not one
    # named after the app, so renaming the app never hides earlier backups.
    try:
        from PyQt5.QtCore import QStandardPaths
        base = QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation)
    except Exception:
        base = ""
    base = os.path.join(base, "MIDIswitch") if base else os.path.join(os.path.expanduser("~"), ".midiswitch")
    path = os.path.join(base, "firmware-update-backups")
    os.makedirs(path, exist_ok=True)
    return path


def _safe(serial):
    return "".join(c for c in (serial or "unknown") if c.isalnum()) or "unknown"


def new_backup_path(serial):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(backup_dir(), "%s-%s.kbclone" % (_safe(serial), stamp))


def backups_for(serial):
    """Newest first."""
    return sorted(glob.glob(os.path.join(backup_dir(), "%s-*.kbclone" % _safe(serial))), reverse=True)


def prune_backups(serial, keep=BACKUPS_KEPT):
    for old in backups_for(serial)[keep:]:
        try:
            os.remove(old)
        except OSError:
            pass
