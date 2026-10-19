# SPDX-License-Identifier: GPL-2.0-or-later
"""Firmware update over USB HID (MIDIswitch update mode).

The keyboard's update mode is a vendor-defined HID device, so no driver is
needed on any OS. One request = one 64-byte output report
[cmd, seq, args...]; one reply = one 64-byte input report
[cmd, seq, status, data...].

Firmware arrives as a signed, encrypted ``.mswfw`` package (XChaCha20; the
keyboard decrypts it as it arrives). The keyboard checks the signature itself and only marks the new firmware bootable once every byte is
on flash and the signature verifies, so an interrupted update leaves the
keyboard in update mode, ready to try again.
"""
import struct
import time

# ---- USB identity --------------------------------------------------------------
BOOT_USB_VID = 0xB1D7
BOOT_USB_PID = 0x4013
BOOT_USAGE_PAGE = 0xFF4D
BOOT_USAGE = 0x55
REPORT_SIZE = 64

# ---- Flash layout ----------------------------------------------------------------
APP_BASE = 0x08008400
FIRST_APP_SECTOR = 2

# ---- Commands / status -----------------------------------------------------------
CMD_INFO = 0x01
CMD_BEGIN = 0x02
CMD_SIG = 0x03
CMD_ERASE = 0x04
CMD_WRITE = 0x05
CMD_FINISH = 0x06
CMD_REBOOT = 0x07

STATUS_TEXT = {
    0x01: "unknown command",
    0x02: "bad argument",
    0x03: "steps out of order",
    0x04: "flash write failed",
    0x05: "firmware damaged in transfer (CRC mismatch)",
    0x06: "firmware signature not accepted",
    0x07: "firmware is for a different model",
    0x08: "firmware too large",
}

WRITE_MAX = 56

# ---- Package -----------------------------------------------------------------------
PKG_MAGIC = b"MSWFWPK2"
PKG_MAGIC_V1 = b"MSWFWPK1"       # older unencrypted packages
PKG_HEADER_SIZE = 128
MODEL_ID = 1
MIN_BOOT_PROTO = 2               # first updater that takes encrypted images


class UpdateError(Exception):
    pass


# STM32 CRC unit (poly 0x04C11DB7, init 0xFFFFFFFF, little-endian 32-bit
# words fed most-significant byte first, no reflection, no final xor).
_CRC_TABLE = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) if _c & 0x80000000 else (_c << 1)
        _c &= 0xFFFFFFFF
    _CRC_TABLE.append(_c)


def stm32_crc(data):
    if len(data) % 4:
        raise ValueError("length must be a multiple of 4")
    crc = 0xFFFFFFFF
    t = _CRC_TABLE
    for i in range(0, len(data), 4):
        for b in (data[i + 3], data[i + 2], data[i + 1], data[i]):
            crc = ((crc << 8) & 0xFFFFFFFF) ^ t[((crc >> 24) ^ b) & 0xFF]
    return crc


def version_str(v):
    return "%d.%d.%d" % ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)


def parse_package(blob):
    """Check a .mswfw file and return its fields. Raises UpdateError."""
    if bytes(blob[:8]) == PKG_MAGIC_V1:
        raise UpdateError("This firmware file is in an older format that this app no longer "
                          "installs. Download the current firmware file.")
    if len(blob) < PKG_HEADER_SIZE or blob[:8] != PKG_MAGIC:
        raise UpdateError("This is not a MIDIswitch firmware file (.mswfw).")
    model, ver, size, crc, flags, file_crc = struct.unpack_from("<6I", blob, 8)
    image = bytes(blob[PKG_HEADER_SIZE:])
    if model != MODEL_ID:
        raise UpdateError("This firmware is for a different keyboard model.")
    if len(image) != size or size % 4:
        raise UpdateError("The firmware file is truncated.")
    if stm32_crc(image) != file_crc:
        raise UpdateError("The firmware file is damaged (checksum mismatch).")
    # "crc" is the checksum of the decrypted firmware (checked by the keyboard);
    # "image" stays encrypted all the way to the keyboard.
    return {
        "model": model, "version": ver, "size": size, "crc": crc, "flags": flags,
        "signature": bytes(blob[32:96]), "key_id": bytes(blob[96:104]),
        "nonce": bytes(blob[104:128]), "image": image,
    }


def sector_start(s):
    if s < 4:
        return 0x08000000 + s * 0x4000
    if s == 4:
        return 0x08010000
    return 0x08020000 + (s - 5) * 0x20000


def sector_of(addr):
    for s in range(11, -1, -1):
        if addr >= sector_start(s):
            return s
    return 0


def is_bootloader_desc(desc):
    return (desc.get("vendor_id") == BOOT_USB_VID and desc.get("product_id") == BOOT_USB_PID
            and desc.get("usage_page") == BOOT_USAGE_PAGE and desc.get("usage") == BOOT_USAGE)


def find_bootloader(descs, serial=None):
    """Pick the update-mode device from a hid.enumerate() list. With a serial,
    only that unit; without, only when exactly one is present."""
    found = [d for d in descs if is_bootloader_desc(d)]
    if serial:
        found = [d for d in found if (d.get("serial_number") or "") == serial]
        return found[0] if found else None
    return found[0] if len(found) == 1 else None


class HidTransport:
    """64-byte report transport over an open hidapi device."""

    def __init__(self, dev):
        self.dev = dev

    def write(self, report):
        n = self.dev.write(b"\x00" + bytes(report))
        if n is not None and n < 0:
            raise UpdateError("USB write failed")

    def read(self, timeout_ms):
        data = self.dev.read(REPORT_SIZE, timeout_ms=timeout_ms)
        return bytes(data) if data else b""


class BootloaderClient:

    def __init__(self, transport):
        self.t = transport
        self.seq = 0

    def drain(self):
        while self.t.read(10):
            pass

    def request(self, cmd, args=b"", timeout_ms=2000):
        self.seq = (self.seq + 1) & 0xFF
        rep = bytearray(REPORT_SIZE)
        rep[0], rep[1] = cmd, self.seq
        rep[2:2 + len(args)] = args
        self.t.write(rep)
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            left = int((deadline - time.monotonic()) * 1000)
            if left <= 0:
                raise UpdateError("The keyboard stopped answering (command 0x%02X)." % cmd)
            r = self.t.read(min(left, 500))
            if len(r) >= 3 and r[0] == cmd and r[1] == self.seq:
                if r[2] != 0:
                    raise UpdateError("The keyboard refused the update: %s."
                                      % STATUS_TEXT.get(r[2], "error 0x%02X" % r[2]))
                return r

    def info(self):
        r = self.request(CMD_INFO)
        d = r[3:]
        return {
            "proto": d[0],
            "bl_version": struct.unpack_from("<H", d, 1)[0],
            "model": struct.unpack_from("<I", d, 3)[0],
            "app_base": struct.unpack_from("<I", d, 7)[0],
            "app_max": struct.unpack_from("<I", d, 11)[0],
            "app_valid": bool(d[15]),
            "app_version": struct.unpack_from("<I", d, 16)[0],
            "write_max": d[20],
            "key_id": bytes(d[21:29]),
            "uid": bytes(d[29:41]),
            "why": d[41],
        }

    def flash(self, pkg, log=lambda s: None, progress=lambda f: None):
        """Install a parsed package. progress(0..1)."""
        info = self.info()
        if info["proto"] < MIN_BOOT_PROTO:
            raise UpdateError("This keyboard's updater is too old for this firmware file. Install "
                              "the factory image once with STM32CubeProgrammer, then update "
                              "from the app again.")
        if info["model"] != pkg["model"]:
            raise UpdateError("This firmware is for a different keyboard model.")
        if pkg["size"] > info["app_max"]:
            raise UpdateError("This firmware is too large for the keyboard.")
        if pkg["key_id"] != info["key_id"]:
            raise UpdateError("This firmware is not signed for this keyboard (it was signed with a "
                              "different key). Unplug the keyboard and plug it back in to go "
                              "back to the firmware it has.")
        chunk = min(WRITE_MAX, info["write_max"] or WRITE_MAX)

        self.request(CMD_BEGIN, struct.pack("<5I", pkg["size"], pkg["crc"], pkg["version"],
                                            pkg["model"], pkg["flags"]) + pkg["nonce"])
        self.request(CMD_SIG, b"\x00" + pkg["signature"][:32])
        self.request(CMD_SIG, b"\x01" + pkg["signature"][32:])

        last = sector_of(APP_BASE + pkg["size"] - 1)
        sectors = list(range(FIRST_APP_SECTOR, last + 1))
        # Erase ~15 %, write ~80 %, verify ~5 % of the bar.
        log("Erasing...")
        for i, s in enumerate(sectors):
            self.request(CMD_ERASE, bytes([s]), timeout_ms=8000)
            progress(0.15 * (i + 1) / len(sectors))

        log("Writing...")
        image = pkg["image"]
        total = len(image)
        for off in range(0, total, chunk):
            part = image[off:off + chunk]
            self.request(CMD_WRITE, struct.pack("<IB", off, len(part)) + b"\x00" + part)
            if (off // chunk) % 32 == 0:
                progress(0.15 + 0.80 * (off + len(part)) / total)

        log("Checking...")
        self.request(CMD_FINISH, timeout_ms=30000)
        progress(1.0)

    def reboot(self):
        try:
            self.request(CMD_REBOOT, timeout_ms=1000)
        except UpdateError:
            pass  # it may already be gone
