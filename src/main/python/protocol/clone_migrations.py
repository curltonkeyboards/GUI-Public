# SPDX-License-Identifier: GPL-2.0-or-later
"""Keyboard-clone EEPROM layout migrations.

A `.kbclone` file is a byte-for-byte image of the keyboard's 64 KB config
EEPROM, stamped with the `EEPROM_LAYOUT_VERSION` of the firmware that produced
it. When that version doesn't match the connected keyboard's, the image can't
be written as-is — regions may have moved, resized, or changed meaning.

Rather than refusing outright, this module converts an older image forward one
version at a time, so a clone taken before a firmware update still restores
with its data intact.

HOW TO ADD A MIGRATION
----------------------
When you bump `EEPROM_LAYOUT_VERSION` in the firmware's config.h, add a
`_migrate_vN_to_vN1(blob, notes)` function here and register it in
`_MIGRATIONS` under key N. `migrate_clone()` chains them, so a v1 image will
walk 1 -> 2 -> 3 -> ... up to whatever the connected firmware reports.

Each migration:
  * receives a `bytearray` of the WHOLE EEPROM image and mutates it in place;
  * appends a human-readable line to `notes` for anything a user would care
    about (data carried across, data reset to defaults);
  * must be safe when the source region was never initialised — check the old
    magic first, and if it doesn't match, just invalidate the new magic so the
    firmware reseeds that region on the next boot.

RULES OF THUMB
--------------
  * Region addresses below are the values of the firmware `#define`s AT THE
    TIME OF THAT MIGRATION. Never replace them with "current" constants — a
    migration describes a historical layout and must stay frozen even when the
    live layout moves again.
  * Magic words are stored little-endian (the firmware writes the raw bytes of
    a uint16 on a little-endian MCU).
  * Regions that are NEW in the target version hold whatever junk occupied that
    address in the old layout. Zero their magic so the firmware's own
    magic-mismatch path seeds proper defaults, instead of leaving a 1-in-65536
    chance of stale bytes being read as a valid config.
  * The QMK magic (0-1), the VIA/Vial magic and the boot-magic shadow are
    deliberately NOT touched here — the firmware's clone WRITE path already
    overlays the chip's current bytes over those (kb_clone_protect_chunk), so a
    clone can never plant a foreign magic and trigger a factory reset.
"""

import struct


class CloneMigrationError(Exception):
    """Raised when an image cannot be converted to the target layout."""


def _u16le(blob, addr):
    return struct.unpack_from("<H", blob, addr)[0]


def _set_u16le(blob, addr, value):
    struct.pack_into("<H", blob, addr, value)


# =============================================================================
# v1 -> v2   (2026-07)
# =============================================================================
# Three things changed between layout v1 and v2:
#
#   1. Functional LED config (base 64320) grew 90 -> 92 states, 360 -> 368
#      bytes. States 0-89 keep their exact indices and addresses (the two new
#      Multichannel states were APPENDED), so the user's colours survive
#      untouched — only the magic moves (64680 -> 64688) and its value bumps
#      (0xF1F1 -> 0xF1F2), and the two new entries need their defaults.
#
#   2. Ear-trainer slots (base 60812, 10 x 24 bytes) changed field layout IN
#      PLACE: interval_mask grew 5 -> 7 bytes, absorbing the two trailing pad
#      bytes. sizeof stayed 24, so the region did not move, but every field
#      after the mask shifted by 2. Bit numbering inside the mask is unchanged
#      ("semitone + 24" in both), so the old 5 bytes copy over verbatim and the
#      2 new bytes (intervals +13..+24, which v1 could not express) are zero.
#
#   3. Three mini-regions are NEW: the per-loop note gate (37150), the
#      Keysplit/Triplesplit button config (65430) and Multichannel (65444).
#      Nothing to carry across — invalidate so the firmware seeds defaults.

# --- v1 functional LED region ---
V1_FLED_BASE = 64320
V1_FLED_STATE_COUNT = 90
V1_FLED_MAGIC_ADDR = V1_FLED_BASE + V1_FLED_STATE_COUNT * 4     # 64680
V1_FLED_MAGIC = 0xF1F1

# --- v2 functional LED region ---
V2_FLED_STATE_COUNT = 92
V2_FLED_MAGIC_ADDR = V1_FLED_BASE + V2_FLED_STATE_COUNT * 4     # 64688
V2_FLED_MAGIC = 0xF1F2
# Defaults for the two appended states, mirroring func_led_defaults[] in the
# firmware's led/functional_led_config.c: {h, s, v, blink}.
V2_FLED_NEW_STATE_DEFAULTS = [
    (190, 255, 220, 0),   # FLED_MULTICHANNEL_ON  — blue-violet (echoing)
    (0,     0,  40, 0),   # FLED_MULTICHANNEL_OFF — dim white (idle)
]

# --- ear trainer (region address and slot size identical in v1 and v2) ---
ET_BASE = 60812
ET_SLOT_COUNT = 10
ET_SLOT_SIZE = 24
ET_SLOTS_ADDR = ET_BASE + 2
V1_ET_MAGIC = 0xE701
V2_ET_MAGIC = 0xE702

# --- regions introduced in v2: (address, total size incl. magic, name) ---
# These addresses were FREE in the v1 layout, so a v1 image carries whatever
# junk the old firmware happened to leave there. Zero the WHOLE region, not
# just the magic: the firmware would reseed the data anyway (magic mismatch →
# defaults → save), but leaving live-looking bytes sitting under a region that
# is only one magic word away from being read is exactly the kind of thing that
# turns into a mystery bug later. Sizes are magic(2) + the firmware's data:
#   note gate  2 + MAX_MACROS(8)          = 10
#   KSQB       2 + 2 zones * 4            = 10
#   MC         2 + MC_PRESET_COUNT(16) * 4 = 66
V2_NEW_REGIONS = [
    (37150, 10, "per-loop Rec Notes gate"),
    (65430, 10, "Keysplit/Triplesplit button config"),
    (65444, 66, "Multichannel echo presets"),
]


def _migrate_et_slot_v1_to_v2(old):
    """Re-lay one 24-byte ear-trainer slot from the v1 field order to v2.

    v1: mode preset diff inv | mask[5] | 3n(4) 4n(4) 5n(4) | valid | pad[2]
    v2: mode preset diff inv | mask[7] | 3n(4) 4n(4) 5n(4) | valid
    """
    new = bytearray(ET_SLOT_SIZE)
    new[0:4] = old[0:4]           # mode / preset / difficulty / inversions
    new[4:9] = old[4:9]           # interval_mask low 5 bytes (same bit numbering)
    new[9:11] = b"\x00\x00"       # new mask bytes: intervals +13..+24, none set
    new[11:23] = old[9:21]        # the three uint32 chord masks, shifted +2
    new[23] = old[21]             # valid
    return new


def _migrate_v1_to_v2(blob, notes):
    # ---- 1. functional LED config ----
    if _u16le(blob, V1_FLED_MAGIC_ADDR) == V1_FLED_MAGIC:
        # States 0-89 are already at the right addresses. Append the two new
        # entries (they land on top of the old magic word, which is correct)
        # and stamp the new magic past them.
        for i, (h, s, v, blink) in enumerate(V2_FLED_NEW_STATE_DEFAULTS):
            off = V1_FLED_BASE + (V1_FLED_STATE_COUNT + i) * 4
            blob[off:off + 4] = bytes((h, s, v, blink))
        _set_u16le(blob, V2_FLED_MAGIC_ADDR, V2_FLED_MAGIC)
        notes.append("Functional LED colours: kept (2 new Multi Channel states "
                     "set to their defaults).")
    else:
        # Never initialised on the source keyboard — clear the whole region so
        # no stale bytes ride along, and let the firmware seed it.
        blob[V1_FLED_BASE:V2_FLED_MAGIC_ADDR + 2] = bytes(
            V2_FLED_MAGIC_ADDR + 2 - V1_FLED_BASE)
        notes.append("Functional LED colours: not configured in the clone, "
                     "cleared and will use defaults.")

    # ---- 2. ear trainer slots ----
    if _u16le(blob, ET_BASE) == V1_ET_MAGIC:
        for slot in range(ET_SLOT_COUNT):
            off = ET_SLOTS_ADDR + slot * ET_SLOT_SIZE
            blob[off:off + ET_SLOT_SIZE] = _migrate_et_slot_v1_to_v2(
                blob[off:off + ET_SLOT_SIZE])
        _set_u16le(blob, ET_BASE, V2_ET_MAGIC)
        notes.append("Ear trainer slots: kept (converted to the wider "
                     "-24..+24 interval range).")
    else:
        et_size = 2 + ET_SLOT_COUNT * ET_SLOT_SIZE
        blob[ET_BASE:ET_BASE + et_size] = bytes(et_size)
        notes.append("Ear trainer slots: not configured in the clone, cleared "
                     "and will use defaults.")

    # ---- 3. regions that did not exist in v1 ----
    # Wipe each region to zero, magic included. The zeroed magic is what makes
    # the firmware seed proper defaults on the next boot; zeroing the data too
    # just means no stale bytes ride along in the meantime.
    for addr, size, _name in V2_NEW_REGIONS:
        blob[addr:addr + size] = bytes(size)
    notes.append("New in this firmware, cleared and started at defaults: "
                 + ", ".join(name for _addr, _size, name in V2_NEW_REGIONS) + ".")


# ---------------------------------------------------------------------------
# v2 -> v3 (2026-07): the two-button Keysplit/Triplesplit config (KSQB) was
# retired and replaced by 10 unified Keysplit presets, each carrying the
# Normal + Keysplit + Triplesplit sections, in a NEW region. Nothing else
# moved. The firmware seeds the new region from the old KSQB bytes itself when
# it finds no new magic — but only if the old region is still intact — so the
# migration must NOT clear the retired region, just the new one.
V3_KSP_BASE = 60380                 # magic word + 10 x 14 = 142 bytes
V3_KSP_SIZE = 2 + 10 * 14
V2_KSQB_BASE = 65430                # retired region (magic 0x4B51 + 2 x 4)
V2_KSQB_MAGIC = 0x4B51


def _migrate_v2_to_v3(blob, notes):
    # The new region held whatever occupied 60380 in v2 (free space): zero it
    # magic-first so the firmware's magic-mismatch path seeds it, and no stale
    # bytes ride along.
    blob[V3_KSP_BASE:V3_KSP_BASE + V3_KSP_SIZE] = bytes(V3_KSP_SIZE)
    if _u16le(blob, V2_KSQB_BASE) == V2_KSQB_MAGIC:
        # Left in place on purpose: the firmware reads it once, on the first
        # boot after the update, to seed presets 1 and 2 from the old buttons.
        notes.append("Keysplit / Triplesplit button settings: carried over "
                     "into Keysplit presets 1 and 2.")
    else:
        notes.append("Keysplit presets: new in this firmware, started at "
                     "defaults.")


# ---------------------------------------------------------------------------
# v3 -> v4 (2026-07): the per-loop record gate (37150, magic + 8 bytes)
# changed MEANING in place — the old key-zone mask (1-7, "Rec Notes") became a
# channel gate (0 = All Channels, 1-16 = record only that channel, the
# "Rec Channel" row). Same address and size; the firmware bumped the region's
# magic 0x4C47 -> 0x4C48 so an in-place upgrade reseeds it. An old zone mask
# cannot be mapped onto a single channel, so the migration clears the region
# and the gate starts back at All Channels.
V4_NOTE_GATE_BASE = 37150           # magic word + 8 gate bytes = 10 bytes
V4_NOTE_GATE_SIZE = 2 + 8


def _migrate_v3_to_v4(blob, notes):
    blob[V4_NOTE_GATE_BASE:V4_NOTE_GATE_BASE + V4_NOTE_GATE_SIZE] = bytes(
        V4_NOTE_GATE_SIZE)
    notes.append("Per-loop record gate: the old key-zone 'Rec Notes' setting "
                 "was replaced by a per-channel 'Rec Channel' gate and resets "
                 "to All Channels.")


# Registry: key = source version, value = function converting it to key + 1.
_MIGRATIONS = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
}


def can_migrate(from_version, to_version):
    """True if a complete chain of migrations exists for this upgrade."""
    if from_version == to_version:
        return True
    if from_version > to_version:
        return False   # clone is NEWER than the firmware — we can't downgrade
    return all(v in _MIGRATIONS for v in range(from_version, to_version))


def migrate_clone(data, from_version, to_version):
    """Convert a whole-EEPROM clone image from one layout version to another.

    Args:
        data: the clone's EEPROM image (bytes or bytearray).
        from_version: the `eeprom_layout_version` stamped in the clone file.
        to_version: the layout version the connected firmware reports.

    Returns:
        (migrated_bytes, notes) — notes is a list of human-readable strings
        describing what was carried across and what will reset to defaults.

    Raises:
        CloneMigrationError if no chain of migrations covers the gap.
    """
    if from_version == to_version:
        return bytes(data), []
    if not can_migrate(from_version, to_version):
        raise CloneMigrationError(
            "No conversion path from EEPROM layout v{} to v{}.".format(
                from_version, to_version))

    blob = bytearray(data)
    notes = []
    for version in range(from_version, to_version):
        _MIGRATIONS[version](blob, notes)
    return bytes(blob), notes
