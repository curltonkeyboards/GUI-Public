# SPDX-License-Identifier: GPL-2.0-or-later
"""Sign and encrypt a plain firmware .bin so the keyboard's updater accepts it.

EdDSA on Curve25519 with BLAKE2b-512 as the hash (the scheme Monocypher 4
calls crypto_eddsa_*). The secret key file holds 64 bytes as hex: the 32-byte
seed followed by the 32-byte public key. Pure Python, no extra dependency;
signing one image takes a fraction of a second.

The image is then encrypted with XChaCha20 under a key derived from the same
key file (BLAKE2b-256 of ENC_KEY_LABEL + the seed); the keyboard decrypts it
while installing. The signature covers the decrypted image.
"""
import hashlib
import os
import struct

from protocol import msw_updater as upd

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _recover_x(y, sign):
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _I % _P
    if x & 1 != sign:
        x = _P - x
    return x


_BY = 4 * pow(5, _P - 2, _P) % _P
_B = (_recover_x(_BY, 0), _BY, 1, _recover_x(_BY, 0) * _BY % _P)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = 2 * t1 * t2 * _D % _P
    d = 2 * z1 * z2 % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mul(s, p):
    q = (0, 1, 1, 0)
    while s:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _encode(p):
    x, y, z, _ = p
    zi = pow(z, _P - 2, _P)
    x, y = x * zi % _P, y * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _h(*parts):
    return hashlib.blake2b(b"".join(parts), digest_size=64).digest()


def _expand(seed):
    h = _h(seed)
    a = bytearray(h[:32])
    a[0] &= 248
    a[31] &= 127
    a[31] |= 64
    return int.from_bytes(a, "little"), h[32:]


def public_key(seed):
    a, _ = _expand(seed)
    return _encode(_mul(a, _B))


def sign(secret, msg):
    seed = secret[:32]
    a, prefix = _expand(seed)
    pub = _encode(_mul(a, _B))
    r = int.from_bytes(_h(prefix, msg), "little") % _L
    rb = _encode(_mul(r, _B))
    k = int.from_bytes(_h(rb, pub, msg), "little") % _L
    return rb + int.to_bytes((r + k * a) % _L, 32, "little")


# ---- XChaCha20 (same output as Monocypher crypto_chacha20_x) ----------------------
_M = 0xFFFFFFFF
_SIGMA = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)

def _rounds(x):
    for _ in range(10):
        for a, b, c, d in ((0,4,8,12),(1,5,9,13),(2,6,10,14),(3,7,11,15),
                           (0,5,10,15),(1,6,11,12),(2,7,8,13),(3,4,9,14)):
            x[a] = (x[a] + x[b]) & _M; t = x[d] ^ x[a]; x[d] = ((t << 16) | (t >> 16)) & _M
            x[c] = (x[c] + x[d]) & _M; t = x[b] ^ x[c]; x[b] = ((t << 12) | (t >> 20)) & _M
            x[a] = (x[a] + x[b]) & _M; t = x[d] ^ x[a]; x[d] = ((t << 8) | (t >> 24)) & _M
            x[c] = (x[c] + x[d]) & _M; t = x[b] ^ x[c]; x[b] = ((t << 7) | (t >> 25)) & _M

def hchacha20(key, nonce16):
    x = list(_SIGMA) + list(struct.unpack("<8I", key)) + list(struct.unpack("<4I", nonce16))
    _rounds(x)
    return struct.pack("<8I", *(x[0:4] + x[12:16]))

def xchacha20(key, nonce24, data, counter=0):
    sub = struct.unpack("<8I", hchacha20(key, nonce24[:16]))
    n = struct.unpack("<2I", nonce24[16:24])
    out = bytearray(data)
    for blk in range((len(out) + 63) // 64):
        c = counter + blk
        st = list(_SIGMA) + list(sub) + [c & _M, (c >> 32) & _M, n[0], n[1]]
        x = st[:]
        _rounds(x)
        ks = struct.pack("<16I", *((x[i] + st[i]) & _M for i in range(16)))
        base = blk * 64
        for i in range(min(64, len(out) - base)):
            out[base + i] ^= ks[i]
    return bytes(out)


ENC_KEY_LABEL = b"MIDIswitch firmware encryption v1"


def enc_key(secret):
    """The image encryption key belonging to a signing key."""
    return hashlib.blake2b(ENC_KEY_LABEL + bytes(secret[:32]), digest_size=32).digest()


# ---- Keys --------------------------------------------------------------------------

DEFAULT_KEY = os.path.join(os.path.expanduser("~"), ".midiswitch", "firmware_signing_key.hex")


def load_key(path):
    """Read and check a signing key file. Returns the 64-byte secret key."""
    try:
        with open(path) as f:
            key = bytes.fromhex(f.read().strip())
    except (OSError, ValueError):
        raise upd.UpdateError("Could not read the signing key file {}.".format(path))
    if len(key) != 64 or public_key(key[:32]) != key[32:]:
        raise upd.UpdateError("{} is not a MIDIswitch firmware signing key.".format(path))
    return key


# ---- Plain .bin -> package ---------------------------------------------------------

APP_MAX = 0x08100000 - upd.APP_BASE
RAM_BASE, RAM_END = 0x20000000, 0x20040000
HDR_MAGIC = 0x4153574D
HDR_VERSION = 1
VERSION_TAG = b"MSWFWVER"


def bin_version(image):
    """Firmware version from the tag the firmware carries, or None."""
    i = image.find(VERSION_TAG)
    if i < 0 or i + 13 > len(image) or image[i + 8] != 1:
        return None
    major, minor, patch, model = image[i + 9], image[i + 10], image[i + 11], image[i + 12]
    if model != upd.MODEL_ID:
        raise upd.UpdateError("This firmware is for a different keyboard model.")
    return (major << 16) | (minor << 8) | patch


def check_bin(image):
    if len(image) < 8:
        raise upd.UpdateError("This file is too small to be keyboard firmware.")
    if len(image) > APP_MAX:
        raise upd.UpdateError("This firmware is {} KB, more than fits ({} KB).".format(
            len(image) // 1024, APP_MAX // 1024))
    sp, pc = struct.unpack_from("<II", image, 0)
    if not (RAM_BASE <= sp <= RAM_END):
        raise upd.UpdateError("This .bin does not look like keyboard firmware.")
    if not (pc & 1) or not (upd.APP_BASE <= (pc & ~1) < upd.APP_BASE + len(image)):
        raise upd.UpdateError(
            "This .bin was built for the old flash layout (without the updater) and cannot "
            "be installed here. Build it from the current firmware source, or use the "
            "factory image with STM32CubeProgrammer.")


def package_from_bin(blob, secret):
    """Turn a plain firmware .bin into the same dict parse_package() returns,
    signed and encrypted with ``secret``."""
    image = bytearray(blob)
    while len(image) % 4:
        image.append(0xFF)
    image = bytes(image)
    check_bin(image)
    ver = bin_version(image)
    size, crc = len(image), upd.stm32_crc(image)
    head = struct.pack("<8I", HDR_MAGIC, HDR_VERSION, size, crc, ver or 0, upd.MODEL_ID, 0, 0)
    sig = sign(secret, head + hashlib.blake2b(image, digest_size=64).digest())
    nonce = os.urandom(24)
    return {
        "model": upd.MODEL_ID, "version": ver or 0, "size": size, "crc": crc, "flags": 0,
        "signature": sig, "key_id": secret[32:40], "nonce": nonce,
        "image": xchacha20(enc_key(secret), nonce, image),
        "version_known": ver is not None,
    }
