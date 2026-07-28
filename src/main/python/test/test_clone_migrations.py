import struct
import unittest

from protocol.clone_migrations import (
    CloneMigrationError, can_migrate, migrate_clone,
    V1_FLED_BASE, V1_FLED_STATE_COUNT, V1_FLED_MAGIC_ADDR, V1_FLED_MAGIC,
    V2_FLED_MAGIC_ADDR, V2_FLED_MAGIC, V2_FLED_NEW_STATE_DEFAULTS,
    ET_BASE, ET_SLOTS_ADDR, ET_SLOT_SIZE, ET_SLOT_COUNT,
    V1_ET_MAGIC, V2_ET_MAGIC, V2_NEW_REGION_MAGICS,
)

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
        # No v2 -> v3 migration is registered yet, so a v1 image cannot reach v3.
        self.assertFalse(can_migrate(1, 3))
        with self.assertRaises(CloneMigrationError):
            migrate_clone(b"\x00" * EEPROM_SIZE, 1, 3)

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
        for addr, _name in V2_NEW_REGION_MAGICS:
            allowed |= {addr, addr + 1}
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

    def test_new_regions_invalidated(self):
        for addr, name in V2_NEW_REGION_MAGICS:
            self.assertEqual(struct.unpack_from("<H", self.v2, addr)[0], 0,
                             "{} magic at {} must be zeroed so the firmware "
                             "seeds defaults".format(name, addr))


class TestCloneMigrationUninitialisedSource(unittest.TestCase):
    """A clone from a keyboard that never configured these regions."""

    def setUp(self):
        blank = b"\xFF" * EEPROM_SIZE     # no valid v1 magic anywhere
        self.out, self.notes = migrate_clone(blank, 1, 2)

    def test_fled_magic_invalidated_not_garbage(self):
        self.assertEqual(struct.unpack_from("<H", self.out, V2_FLED_MAGIC_ADDR)[0], 0)

    def test_et_magic_invalidated_not_garbage(self):
        self.assertEqual(struct.unpack_from("<H", self.out, ET_BASE)[0], 0)

    def test_notes_still_produced(self):
        self.assertTrue(self.notes)


if __name__ == "__main__":
    unittest.main()
