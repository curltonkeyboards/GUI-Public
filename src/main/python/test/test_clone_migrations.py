import struct
import unittest

from protocol.clone_migrations import (
    CloneMigrationError, can_migrate, migrate_clone,
    V1_FLED_BASE, V1_FLED_STATE_COUNT, V1_FLED_MAGIC_ADDR, V1_FLED_MAGIC,
    V2_FLED_MAGIC_ADDR, V2_FLED_MAGIC, V2_FLED_NEW_STATE_DEFAULTS,
    ET_BASE, ET_SLOTS_ADDR, ET_SLOT_SIZE, ET_SLOT_COUNT,
    V1_ET_MAGIC, V2_ET_MAGIC, V2_NEW_REGIONS,
    V3_KSP_BASE, V3_KSP_SIZE, V2_KSQB_BASE, V2_KSQB_MAGIC,
    V4_NOTE_GATE_BASE, V4_NOTE_GATE_SIZE,
    V5_NAV_LAYER_BASE, V5_NAV_LAYER_SIZE,
)
from protocol import clone_migrations

EEPROM_SIZE = 65536


def build_v1_image():
    """A v1 EEPROM image with recognisable func-LED colours + ear-trainer slots.

    Filled with junk first, the way a real chip is: anything the migration is
    NOT supposed to touch must survive byte-for-byte.
    """
    blob = bytearray(b"\xA5" * EEPROM_SIZE)

    # v1 func-LED: 90 states x {h, s, v, blink}, magic 0xF1F1 at 64680.
    for i in range(V1_FLED_STATE_COUNT):
        off = V1_FLED_BASE + i * 4
        blob[off:off + 4] = bytes((i, 255 - i, (i * 2) & 0xFF, i % 3))
    struct.pack_into("<H", blob, V1_FLED_MAGIC_ADDR, V1_FLED_MAGIC)

    # v1 ear trainer, 10 x 24 bytes:
    #   mode preset diff inv | mask[5] | 3n(4) 4n(4) 5n(4) | valid | pad[2]
    struct.pack_into("<H", blob, ET_BASE, V1_ET_MAGIC)
    for s in range(ET_SLOT_COUNT):
        slot = bytearray(ET_SLOT_SIZE)
        slot[0] = s % 2                     # mode
        slot[1] = 0xFF if s == 3 else s     # preset (CUSTOM on slot 3)
        slot[2] = s % 4                     # difficulty
        slot[3] = 1 if s % 2 else 0         # inversions_allowed
        slot[4:9] = bytes((0x11, 0x22, 0x33, 0x44, 0x15))    # interval_mask
        struct.pack_into("<I", slot, 9, 0xDEADBE00 + s)      # chord_mask_3n
        struct.pack_into("<I", slot, 13, 0xCAFE0000 + s)     # chord_mask_4n
        struct.pack_into("<I", slot, 17, 0x0BADF00D - s)     # chord_mask_5n
        slot[21] = 1                                         # valid
        off = ET_SLOTS_ADDR + s * ET_SLOT_SIZE
        blob[off:off + ET_SLOT_SIZE] = slot

    # Regions that are free in v1 keep their junk — the migration must
    # neutralise them so the firmware doesn't read them as a valid config.
    return bytes(blob)


class TestCloneMigrationChain(unittest.TestCase):

    def test_same_version_is_a_noop(self):
        image = build_v1_image()
        out, notes = migrate_clone(image, 2, 2)
        self.assertEqual(out, image)
        self.assertEqual(notes, [])

    def test_refuses_downgrade(self):
        self.assertFalse(can_migrate(2, 1))
        with self.assertRaises(CloneMigrationError):
            migrate_clone(b"\x00" * EEPROM_SIZE, 2, 1)

    def test_refuses_unknown_gap(self):
        # One past the highest registered migration: no chain can reach it.
        unreachable = max(clone_migrations._MIGRATIONS) + 3
        self.assertFalse(can_migrate(1, unreachable))
        with self.assertRaises(CloneMigrationError):
            migrate_clone(b"\x00" * EEPROM_SIZE, 1, unreachable)

    def test_every_registered_step_is_contiguous(self):
        # can_migrate() walks range(from, to) and needs EVERY intermediate
        # version present. A registry with a hole (e.g. 1 and 3 but not 2)
        # would silently make older clones unloadable.
        versions = sorted(clone_migrations._MIGRATIONS)
        self.assertEqual(versions, list(range(1, len(versions) + 1)),
                         "migration registry must be contiguous from v1")

    def test_full_chain_from_oldest(self):
        newest = max(clone_migrations._MIGRATIONS) + 1
        self.assertTrue(can_migrate(1, newest))
        out, notes = migrate_clone(build_v1_image(), 1, newest)
        self.assertEqual(len(out), EEPROM_SIZE)
        self.assertTrue(notes)

    def test_v1_to_v2_available(self):
        self.assertTrue(can_migrate(1, 2))


class TestCloneMigrationV1ToV2(unittest.TestCase):

    def setUp(self):
        self.v1 = build_v1_image()
        self.v2, self.notes = migrate_clone(self.v1, 1, 2)

    def test_size_unchanged(self):
        self.assertEqual(len(self.v2), EEPROM_SIZE)

    def test_only_the_affected_regions_change(self):
        allowed = set(range(ET_BASE, ET_BASE + 2 + ET_SLOT_COUNT * ET_SLOT_SIZE))
        allowed |= set(range(V1_FLED_MAGIC_ADDR, V2_FLED_MAGIC_ADDR + 2))
        for addr, size, _name in V2_NEW_REGIONS:
            allowed |= set(range(addr, addr + size))
        changed = {i for i in range(EEPROM_SIZE) if self.v1[i] != self.v2[i]}
        self.assertTrue(changed.issubset(allowed),
                        "migration touched bytes outside the regions it owns: "
                        "{}".format(sorted(changed - allowed)[:16]))

    # ---- functional LED ----

    def test_fled_magic_moved_and_bumped(self):
        self.assertEqual(struct.unpack_from("<H", self.v2, V2_FLED_MAGIC_ADDR)[0],
                         V2_FLED_MAGIC)

    def test_fled_existing_colours_preserved(self):
        # States 0-89 keep both their index and their address, so the user's
        # colours must come through byte-for-byte.
        for i in range(V1_FLED_STATE_COUNT):
            off = V1_FLED_BASE + i * 4
            self.assertEqual(bytes(self.v2[off:off + 4]),
                             bytes((i, 255 - i, (i * 2) & 0xFF, i % 3)),
                             "FLED state {} changed".format(i))

    def test_fled_new_states_seeded_with_firmware_defaults(self):
        for n, expected in enumerate(V2_FLED_NEW_STATE_DEFAULTS):
            off = V1_FLED_BASE + (V1_FLED_STATE_COUNT + n) * 4
            self.assertEqual(tuple(self.v2[off:off + 4]), expected)

    # ---- ear trainer ----

    def test_et_magic_bumped(self):
        self.assertEqual(struct.unpack_from("<H", self.v2, ET_BASE)[0], V2_ET_MAGIC)

    def test_et_slots_relaid_without_data_loss(self):
        for s in range(ET_SLOT_COUNT):
            off = ET_SLOTS_ADDR + s * ET_SLOT_SIZE
            old = self.v1[off:off + ET_SLOT_SIZE]
            new = self.v2[off:off + ET_SLOT_SIZE]
            self.assertEqual(new[0:4], old[0:4],
                             "slot {}: mode/preset/difficulty/inversions".format(s))
            # The mask's bit numbering ("semitone + 24") is identical in both
            # versions, so the old 5 bytes copy over and the 2 new bytes
            # (intervals +13..+24, inexpressible in v1) must be clear.
            self.assertEqual(new[4:9], old[4:9], "slot {}: interval_mask".format(s))
            self.assertEqual(new[9:11], b"\x00\x00",
                             "slot {}: new interval bits should start clear".format(s))
            # The three uint32 chord masks and `valid` all shift +2.
            for new_off, old_off, name in ((11, 9, "3n"), (15, 13, "4n"), (19, 17, "5n")):
                self.assertEqual(struct.unpack_from("<I", new, new_off)[0],
                                 struct.unpack_from("<I", old, old_off)[0],
                                 "slot {}: chord_mask_{}".format(s, name))
            self.assertEqual(new[23], old[21], "slot {}: valid".format(s))

    # ---- regions introduced in v2 ----

    def test_new_regions_fully_cleared(self):
        # Zeroing the magic is what makes the firmware reseed; zeroing the body
        # too means the image carries no junk from whatever used to live at
        # these addresses when they were free space in v1.
        for addr, size, name in V2_NEW_REGIONS:
            region = bytes(self.v2[addr:addr + size])
            self.assertEqual(region, bytes(size),
                             "{} at {}..{} must be fully cleared, got {!r}".format(
                                 name, addr, addr + size - 1, region))

    def test_new_regions_were_actually_dirty_before(self):
        # Guards the test above against silently passing on an image that
        # happened to be zero there already.
        for addr, size, name in V2_NEW_REGIONS:
            self.assertNotEqual(bytes(self.v1[addr:addr + size]), bytes(size),
                                "{} should hold junk in the v1 fixture".format(name))


class TestCloneMigrationUninitialisedSource(unittest.TestCase):
    """A clone from a keyboard that never configured these regions."""

    def setUp(self):
        blank = b"\xFF" * EEPROM_SIZE     # no valid v1 magic anywhere
        self.out, self.notes = migrate_clone(blank, 1, 2)

    def test_fled_region_cleared_not_garbage(self):
        end = V2_FLED_MAGIC_ADDR + 2
        self.assertEqual(bytes(self.out[V1_FLED_BASE:end]), bytes(end - V1_FLED_BASE))

    def test_et_region_cleared_not_garbage(self):
        size = 2 + ET_SLOT_COUNT * ET_SLOT_SIZE
        self.assertEqual(bytes(self.out[ET_BASE:ET_BASE + size]), bytes(size))

    def test_new_regions_cleared(self):
        for addr, size, name in V2_NEW_REGIONS:
            self.assertEqual(bytes(self.out[addr:addr + size]), bytes(size), name)

    def test_notes_still_produced(self):
        self.assertTrue(self.notes)


if __name__ == "__main__":
    unittest.main()


def build_v2_image(with_ksqb=True):
    """A v2 image: like v1 but already migrated, optionally with KSQB configured."""
    blob = bytearray(migrate_clone(build_v1_image(), 1, 2)[0])
    if with_ksqb:
        # The retired two-button config, as a v2 firmware would have left it:
        # magic + 2 zones x {channel, transpose, curve, flags}.
        struct.pack_into("<H", blob, V2_KSQB_BASE, V2_KSQB_MAGIC)
        blob[V2_KSQB_BASE + 2:V2_KSQB_BASE + 10] = bytes(
            (5, 12, 0xFF, 0x01, 9, 256 - 12, 3, 0x05))
    return bytes(blob)


class TestCloneMigrationV2ToV3(unittest.TestCase):
    """KSQB retired; 10 unified Keysplit presets added in a new region."""

    def test_new_ksp_region_fully_cleared(self):
        v2 = bytearray(build_v2_image())
        v2[V3_KSP_BASE:V3_KSP_BASE + V3_KSP_SIZE] = b"\x5A" * V3_KSP_SIZE   # junk
        v3, _notes = migrate_clone(bytes(v2), 2, 3)
        self.assertEqual(bytes(v3[V3_KSP_BASE:V3_KSP_BASE + V3_KSP_SIZE]),
                         bytes(V3_KSP_SIZE),
                         "the new Keysplit-preset region must be fully cleared "
                         "so the firmware seeds it")

    def test_retired_ksqb_region_left_intact(self):
        # The firmware reads it ONCE to seed presets 1 and 2 from the old
        # buttons. Clearing it here would silently drop the user's settings.
        v2 = build_v2_image(with_ksqb=True)
        v3, notes = migrate_clone(v2, 2, 3)
        self.assertEqual(bytes(v3[V2_KSQB_BASE:V2_KSQB_BASE + 10]),
                         bytes(v2[V2_KSQB_BASE:V2_KSQB_BASE + 10]))
        self.assertTrue(any("carried over" in n for n in notes), notes)

    def test_reports_defaults_when_no_ksqb(self):
        v2 = build_v2_image(with_ksqb=False)
        _v3, notes = migrate_clone(v2, 2, 3)
        self.assertTrue(any("started at defaults" in n for n in notes), notes)

    def test_only_the_ksp_region_changes(self):
        v2 = build_v2_image()
        v3, _notes = migrate_clone(v2, 2, 3)
        changed = {i for i in range(EEPROM_SIZE) if v2[i] != v3[i]}
        allowed = set(range(V3_KSP_BASE, V3_KSP_BASE + V3_KSP_SIZE))
        self.assertTrue(changed.issubset(allowed),
                        "v2->v3 touched bytes outside the Keysplit-preset "
                        "region: {}".format(sorted(changed - allowed)[:16]))


def build_v3_image():
    """A v3 image with the note-gate region as a v3 firmware left it:
    old magic 0x4C47 + 8 zone masks (the retired 'Rec Notes' format)."""
    blob = bytearray(migrate_clone(build_v2_image(), 2, 3)[0])
    struct.pack_into("<H", blob, V4_NOTE_GATE_BASE, 0x4C47)
    blob[V4_NOTE_GATE_BASE + 2:V4_NOTE_GATE_BASE + V4_NOTE_GATE_SIZE] = bytes(
        (7, 1, 2, 4, 3, 5, 6, 7))
    return bytes(blob)


class TestCloneMigrationV3ToV4(unittest.TestCase):
    """The note-gate region changed meaning zone-mask -> channel gate."""

    def test_note_gate_region_fully_cleared(self):
        # An old zone mask (1-7) would decode as "channel 1-7 only" under the
        # new meaning — the region must be wiped so the firmware seeds
        # All-Channels defaults, exactly like a brand-new region.
        v3 = build_v3_image()
        v4, _notes = migrate_clone(v3, 3, 4)
        self.assertEqual(
            bytes(v4[V4_NOTE_GATE_BASE:V4_NOTE_GATE_BASE + V4_NOTE_GATE_SIZE]),
            bytes(V4_NOTE_GATE_SIZE))

    def test_only_the_note_gate_region_changes(self):
        v3 = build_v3_image()
        v4, _notes = migrate_clone(v3, 3, 4)
        changed = {i for i in range(EEPROM_SIZE) if v3[i] != v4[i]}
        allowed = set(range(V4_NOTE_GATE_BASE,
                            V4_NOTE_GATE_BASE + V4_NOTE_GATE_SIZE))
        self.assertTrue(changed.issubset(allowed),
                        "v3->v4 touched bytes outside the note-gate region: "
                        "{}".format(sorted(changed - allowed)[:16]))

    def test_reset_is_reported(self):
        _v4, notes = migrate_clone(build_v3_image(), 3, 4)
        self.assertTrue(any("All Channels" in n for n in notes), notes)


class TestCloneMigrationV1ToV3Chain(unittest.TestCase):
    """A v1 clone must walk 1 -> 2 -> 3 and land coherent."""

    def setUp(self):
        self.v1 = build_v1_image()
        self.v3, self.notes = migrate_clone(self.v1, 1, 3)

    def test_v2_work_still_applied(self):
        # The func-LED colours preserved by the v1->v2 step must survive the
        # v2->v3 step untouched.
        for i in range(V1_FLED_STATE_COUNT):
            off = V1_FLED_BASE + i * 4
            self.assertEqual(bytes(self.v3[off:off + 4]),
                             bytes((i, 255 - i, (i * 2) & 0xFF, i % 3)))
        self.assertEqual(struct.unpack_from("<H", self.v3, V2_FLED_MAGIC_ADDR)[0],
                         V2_FLED_MAGIC)

    def test_ksp_region_cleared(self):
        self.assertEqual(bytes(self.v3[V3_KSP_BASE:V3_KSP_BASE + V3_KSP_SIZE]),
                         bytes(V3_KSP_SIZE))

    def test_ksqb_reports_defaults_not_carryover(self):
        # v1 never had a KSQB region, and the v1->v2 step zeroes it, so the
        # v2->v3 step must NOT claim it carried button settings over.
        self.assertTrue(any("started at defaults" in n for n in self.notes),
                        self.notes)

    def test_notes_cover_both_steps(self):
        joined = " ".join(self.notes)
        self.assertIn("Functional LED", joined)
        self.assertIn("Ear trainer", joined)
        self.assertIn("Keysplit", joined)


def build_v4_image():
    """A v4 image with junk where the nav-layer region will live (that gap was
    free space in v4, so a real clone carries whatever was left there)."""
    blob = bytearray(migrate_clone(build_v3_image(), 3, 4)[0])
    blob[V5_NAV_LAYER_BASE:V5_NAV_LAYER_BASE + V5_NAV_LAYER_SIZE] = (
        b"\x5A" * V5_NAV_LAYER_SIZE)
    return bytes(blob)


class TestCloneMigrationV4ToV5(unittest.TestCase):
    """New navigation-layer mini-region at 60373."""

    def test_nav_layer_region_fully_cleared(self):
        # The region did not exist in v4 — junk there could decode as a valid
        # magic + out-of-range layer, so wipe it and let the firmware seed the
        # default (layer 1).
        v4 = build_v4_image()
        v5, _notes = migrate_clone(v4, 4, 5)
        self.assertEqual(
            bytes(v5[V5_NAV_LAYER_BASE:V5_NAV_LAYER_BASE + V5_NAV_LAYER_SIZE]),
            bytes(V5_NAV_LAYER_SIZE))

    def test_only_the_nav_layer_region_changes(self):
        v4 = build_v4_image()
        v5, _notes = migrate_clone(v4, 4, 5)
        changed = {i for i in range(EEPROM_SIZE) if v4[i] != v5[i]}
        allowed = set(range(V5_NAV_LAYER_BASE,
                            V5_NAV_LAYER_BASE + V5_NAV_LAYER_SIZE))
        self.assertTrue(changed.issubset(allowed),
                        "v4->v5 touched bytes outside the nav-layer region: "
                        "{}".format(sorted(changed - allowed)[:16]))

    def test_default_is_reported(self):
        _v5, notes = migrate_clone(build_v4_image(), 4, 5)
        self.assertTrue(any("Navigation layer" in n for n in notes), notes)

    def test_full_chain_from_v1_reaches_v5(self):
        self.assertTrue(can_migrate(1, 5))
        v5, _notes = migrate_clone(build_v1_image(), 1, 5)
        self.assertEqual(
            bytes(v5[V5_NAV_LAYER_BASE:V5_NAV_LAYER_BASE + V5_NAV_LAYER_SIZE]),
            bytes(V5_NAV_LAYER_SIZE))
