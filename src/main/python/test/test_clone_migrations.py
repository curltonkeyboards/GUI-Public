"""Tests for the keyboard clone conversions."""
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
    V6_DL_QB_BASE, V6_DL_QB_SPAN, V6_DL_QB_V5_MAGIC, V6_DL_QB_V6_MAGIC,
    V6_DL_QB_V5_ENTRY, V6_DL_QB_V6_ENTRY,
    V7_DYN_COMBO_OLD_BASE, V7_DYN_COMBO_OLD_COUNT, V7_DYN_KO_OLD_BASE, V7_DYN_KO_OLD_COUNT,
    V7_DYN_ENTRY, V7_DYN_KO_NEW_BASE, V7_DYN_KO_NEW_COUNT, V7_DYN_SPAN_END,
    V8_MOUSE_TIMING_BASE, V8_MOUSE_TIMING_SIZE,
    V9_GBIND_REGIONS,
)
from protocol import clone_migrations

EEPROM_SIZE = 65536


def build_v1_image():
    blob = bytearray(b"\xA5" * EEPROM_SIZE)

    for i in range(V1_FLED_STATE_COUNT):
        off = V1_FLED_BASE + i * 4
        blob[off:off + 4] = bytes((i, 255 - i, (i * 2) & 0xFF, i % 3))
    struct.pack_into("<H", blob, V1_FLED_MAGIC_ADDR, V1_FLED_MAGIC)

    struct.pack_into("<H", blob, ET_BASE, V1_ET_MAGIC)
    for s in range(ET_SLOT_COUNT):
        slot = bytearray(ET_SLOT_SIZE)
        slot[0] = s % 2
        slot[1] = 0xFF if s == 3 else s
        slot[2] = s % 4
        slot[3] = 1 if s % 2 else 0
        slot[4:9] = bytes((0x11, 0x22, 0x33, 0x44, 0x15))
        struct.pack_into("<I", slot, 9, 0xDEADBE00 + s)
        struct.pack_into("<I", slot, 13, 0xCAFE0000 + s)
        struct.pack_into("<I", slot, 17, 0x0BADF00D - s)
        slot[21] = 1
        off = ET_SLOTS_ADDR + s * ET_SLOT_SIZE
        blob[off:off + ET_SLOT_SIZE] = slot

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
        unreachable = max(clone_migrations._MIGRATIONS) + 3
        self.assertFalse(can_migrate(1, unreachable))
        with self.assertRaises(CloneMigrationError):
            migrate_clone(b"\x00" * EEPROM_SIZE, 1, unreachable)

    def test_every_registered_step_is_contiguous(self):
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


    def test_fled_magic_moved_and_bumped(self):
        self.assertEqual(struct.unpack_from("<H", self.v2, V2_FLED_MAGIC_ADDR)[0],
                         V2_FLED_MAGIC)

    def test_fled_existing_colours_preserved(self):
        for i in range(V1_FLED_STATE_COUNT):
            off = V1_FLED_BASE + i * 4
            self.assertEqual(bytes(self.v2[off:off + 4]),
                             bytes((i, 255 - i, (i * 2) & 0xFF, i % 3)),
                             "FLED state {} changed".format(i))

    def test_fled_new_states_seeded_with_firmware_defaults(self):
        for n, expected in enumerate(V2_FLED_NEW_STATE_DEFAULTS):
            off = V1_FLED_BASE + (V1_FLED_STATE_COUNT + n) * 4
            self.assertEqual(tuple(self.v2[off:off + 4]), expected)


    def test_et_magic_bumped(self):
        self.assertEqual(struct.unpack_from("<H", self.v2, ET_BASE)[0], V2_ET_MAGIC)

    def test_et_slots_relaid_without_data_loss(self):
        for s in range(ET_SLOT_COUNT):
            off = ET_SLOTS_ADDR + s * ET_SLOT_SIZE
            old = self.v1[off:off + ET_SLOT_SIZE]
            new = self.v2[off:off + ET_SLOT_SIZE]
            self.assertEqual(new[0:4], old[0:4],
                             "slot {}: mode/preset/difficulty/inversions".format(s))
            self.assertEqual(new[4:9], old[4:9], "slot {}: interval_mask".format(s))
            self.assertEqual(new[9:11], b"\x00\x00",
                             "slot {}: new interval bits should start clear".format(s))
            for new_off, old_off, name in ((11, 9, "3n"), (15, 13, "4n"), (19, 17, "5n")):
                self.assertEqual(struct.unpack_from("<I", new, new_off)[0],
                                 struct.unpack_from("<I", old, old_off)[0],
                                 "slot {}: chord_mask_{}".format(s, name))
            self.assertEqual(new[23], old[21], "slot {}: valid".format(s))


    def test_new_regions_fully_cleared(self):
        for addr, size, name in V2_NEW_REGIONS:
            region = bytes(self.v2[addr:addr + size])
            self.assertEqual(region, bytes(size),
                             "{} at {}..{} must be fully cleared, got {!r}".format(
                                 name, addr, addr + size - 1, region))

    def test_new_regions_were_actually_dirty_before(self):
        for addr, size, name in V2_NEW_REGIONS:
            self.assertNotEqual(bytes(self.v1[addr:addr + size]), bytes(size),
                                "{} should hold junk in the v1 fixture".format(name))


class TestCloneMigrationUninitialisedSource(unittest.TestCase):

    def setUp(self):
        blank = b"\xFF" * EEPROM_SIZE
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


def build_v6_image():
    blob = bytearray(build_v1_image())
    for i, (a, out) in enumerate(((0x04, 0x1E), (0x05, 0x1F), (0x06, 0x20))):
        struct.pack_into("<HHHHH", blob, V7_DYN_COMBO_OLD_BASE + i * V7_DYN_ENTRY, a, a + 1, 0, 0, out)
    struct.pack_into("<HHHBBBB", blob, V7_DYN_KO_OLD_BASE + 0 * V7_DYN_ENTRY, 0x04, 0x05, 0xF001, 0x01, 0, 0x01, 0x87)
    struct.pack_into("<HHHBBBB", blob, V7_DYN_KO_OLD_BASE + 5 * V7_DYN_ENTRY, 0x1E, 0x1F, 0x0FFF, 0x22, 0, 0x22, 0x07)
    struct.pack_into("<HHHBBBB", blob, V7_DYN_KO_OLD_BASE + 31 * V7_DYN_ENTRY, 0x29, 0x2A, 0x3800, 0x80, 0, 0x80, 0x87)
    for i in range(3, V7_DYN_COMBO_OLD_COUNT):
        blob[V7_DYN_COMBO_OLD_BASE + i * V7_DYN_ENTRY:V7_DYN_COMBO_OLD_BASE + (i + 1) * V7_DYN_ENTRY] = bytes(V7_DYN_ENTRY)
    for i in range(V7_DYN_KO_OLD_COUNT):
        if i not in (0, 5, 31):
            blob[V7_DYN_KO_OLD_BASE + i * V7_DYN_ENTRY:V7_DYN_KO_OLD_BASE + (i + 1) * V7_DYN_ENTRY] = bytes(V7_DYN_ENTRY)
    return bytes(blob)


class TestCloneMigrationV6ToV7(unittest.TestCase):

    def setUp(self):
        self.v6 = build_v6_image()
        self.v7, self.notes = migrate_clone(self.v6, 6, 7)

    def _entry(self, slot):
        off = V7_DYN_KO_NEW_BASE + slot * V7_DYN_ENTRY
        return struct.unpack_from("<HHHBBBB", self.v7, off)

    def test_overrides_relocated_and_fn_bits_cleared(self):
        self.assertEqual(self._entry(0), (0x04, 0x05, 0x0001, 0x01, 0, 0x01, 0x87))
        self.assertEqual(self._entry(5), (0x1E, 0x1F, 0x0FFF, 0x22, 0, 0x22, 0x07))
        self.assertEqual(self._entry(31), (0x29, 0x2A, 0x0800, 0x80, 0, 0x80, 0x87))

    def test_unused_new_slots_and_reserve_are_zero(self):
        for slot in range(V7_DYN_KO_NEW_COUNT):
            if slot in (0, 5, 31):
                continue
            off = V7_DYN_KO_NEW_BASE + slot * V7_DYN_ENTRY
            self.assertEqual(bytes(self.v7[off:off + V7_DYN_ENTRY]), bytes(V7_DYN_ENTRY), slot)
        self.assertEqual(bytes(self.v7[V7_DYN_KO_OLD_BASE:V7_DYN_SPAN_END]),
                         bytes(V7_DYN_SPAN_END - V7_DYN_KO_OLD_BASE))

    def test_combos_gone(self):
        self.assertNotEqual(struct.unpack_from("<HHHHH", self.v7, V7_DYN_COMBO_OLD_BASE + V7_DYN_ENTRY),
                            (0x05, 0x06, 0, 0, 0x1F))

    def test_only_the_dynamic_span_changes(self):
        changed = {i for i in range(EEPROM_SIZE) if self.v6[i] != self.v7[i]}
        allowed = set(range(V7_DYN_COMBO_OLD_BASE, V7_DYN_SPAN_END))
        self.assertTrue(changed.issubset(allowed),
                        "v6->v7 touched bytes outside the combo/override span: "
                        "{}".format(sorted(changed - allowed)[:16]))
        self.assertEqual(self.v6[V7_DYN_SPAN_END:V7_DYN_SPAN_END + 64],
                         self.v7[V7_DYN_SPAN_END:V7_DYN_SPAN_END + 64])

    def test_counts_reported(self):
        n = " ".join(self.notes)
        self.assertIn("3 entries carried over", n)
        self.assertIn("3 combo(s) dropped", n)

    def test_full_chain_from_v1_reaches_v7(self):
        self.assertTrue(can_migrate(1, 7))
        v7, _notes = migrate_clone(build_v1_image(), 1, 7)
        self.assertEqual(len(v7), EEPROM_SIZE)


class TestCloneMigrationV7ToV8(unittest.TestCase):

    def setUp(self):
        self.v7 = build_v1_image()
        self.v8, self.notes = migrate_clone(self.v7, 7, 8)

    def test_region_fully_cleared(self):
        self.assertEqual(bytes(self.v8[V8_MOUSE_TIMING_BASE:V8_MOUSE_TIMING_BASE + V8_MOUSE_TIMING_SIZE]),
                         bytes(V8_MOUSE_TIMING_SIZE))

    def test_only_the_region_changes(self):
        changed = {i for i in range(EEPROM_SIZE) if self.v7[i] != self.v8[i]}
        allowed = set(range(V8_MOUSE_TIMING_BASE, V8_MOUSE_TIMING_BASE + V8_MOUSE_TIMING_SIZE))
        self.assertTrue(changed.issubset(allowed), sorted(changed - allowed)[:16])

    def test_default_is_reported(self):
        self.assertTrue(any("mouse timing" in n for n in self.notes), self.notes)

    def test_full_chain_from_v1_reaches_v8(self):
        self.assertTrue(can_migrate(1, 8))
        v8, _notes = migrate_clone(build_v1_image(), 1, 8)
        self.assertEqual(len(v8), EEPROM_SIZE)


class TestCloneMigrationV8ToV9(unittest.TestCase):

    def setUp(self):
        self.v8 = build_v1_image()
        self.v9, self.notes = migrate_clone(self.v8, 8, 9)

    def test_regions_fully_cleared(self):
        for base, size in V9_GBIND_REGIONS:
            self.assertEqual(bytes(self.v9[base:base + size]), bytes(size))

    def test_only_the_regions_change(self):
        changed = {i for i in range(EEPROM_SIZE) if self.v8[i] != self.v9[i]}
        allowed = set()
        for base, size in V9_GBIND_REGIONS:
            allowed.update(range(base, base + size))
        self.assertTrue(changed.issubset(allowed), sorted(changed - allowed)[:16])

    def test_reset_is_reported(self):
        self.assertTrue(any("Joystick keys" in n for n in self.notes), self.notes)

    def test_full_chain_from_v1_reaches_v9(self):
        self.assertTrue(can_migrate(1, 9))
        v9, _notes = migrate_clone(build_v1_image(), 1, 9)
        self.assertEqual(len(v9), EEPROM_SIZE)


if __name__ == "__main__":
    unittest.main()


def build_v2_image(with_ksqb=True):
    blob = bytearray(migrate_clone(build_v1_image(), 1, 2)[0])
    if with_ksqb:
        struct.pack_into("<H", blob, V2_KSQB_BASE, V2_KSQB_MAGIC)
        blob[V2_KSQB_BASE + 2:V2_KSQB_BASE + 10] = bytes(
            (5, 12, 0xFF, 0x01, 9, 256 - 12, 3, 0x05))
    return bytes(blob)


class TestCloneMigrationV2ToV3(unittest.TestCase):

    def test_new_ksp_region_fully_cleared(self):
        v2 = bytearray(build_v2_image())
        v2[V3_KSP_BASE:V3_KSP_BASE + V3_KSP_SIZE] = b"\x5A" * V3_KSP_SIZE
        v3, _notes = migrate_clone(bytes(v2), 2, 3)
        self.assertEqual(bytes(v3[V3_KSP_BASE:V3_KSP_BASE + V3_KSP_SIZE]),
                         bytes(V3_KSP_SIZE),
                         "the new Keysplit-preset region must be fully cleared "
                         "so the firmware seeds it")

    def test_retired_ksqb_region_left_intact(self):
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
    blob = bytearray(migrate_clone(build_v2_image(), 2, 3)[0])
    struct.pack_into("<H", blob, V4_NOTE_GATE_BASE, 0x4C47)
    blob[V4_NOTE_GATE_BASE + 2:V4_NOTE_GATE_BASE + V4_NOTE_GATE_SIZE] = bytes(
        (7, 1, 2, 4, 3, 5, 6, 7))
    return bytes(blob)


class TestCloneMigrationV3ToV4(unittest.TestCase):

    def test_note_gate_region_fully_cleared(self):
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

    def setUp(self):
        self.v1 = build_v1_image()
        self.v3, self.notes = migrate_clone(self.v1, 1, 3)

    def test_v2_work_still_applied(self):
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
        self.assertTrue(any("started at defaults" in n for n in self.notes),
                        self.notes)

    def test_notes_cover_both_steps(self):
        joined = " ".join(self.notes)
        self.assertIn("Functional LED", joined)
        self.assertIn("Ear trainer", joined)
        self.assertIn("Keysplit", joined)


def build_v4_image():
    blob = bytearray(migrate_clone(build_v3_image(), 3, 4)[0])
    blob[V5_NAV_LAYER_BASE:V5_NAV_LAYER_BASE + V5_NAV_LAYER_SIZE] = (
        b"\x5A" * V5_NAV_LAYER_SIZE)
    return bytes(blob)


class TestCloneMigrationV4ToV5(unittest.TestCase):

    def test_nav_layer_region_fully_cleared(self):
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


class TestCloneMigrationV3ToV5DataSurvival(unittest.TestCase):

    KSP_MAGIC = 0x4B50

    def setUp(self):
        v3 = bytearray(build_v3_image())
        struct.pack_into("<H", v3, V3_KSP_BASE, self.KSP_MAGIC)
        self.ksp_payload = bytes((i * 7 + 3) & 0xFF for i in range(V3_KSP_SIZE - 2))
        v3[V3_KSP_BASE + 2:V3_KSP_BASE + V3_KSP_SIZE] = self.ksp_payload
        self.v3 = bytes(v3)
        self.v5, self.notes = migrate_clone(self.v3, 3, 5)

    def test_ksp_presets_survive_byte_for_byte(self):
        self.assertEqual(struct.unpack_from("<H", self.v5, V3_KSP_BASE)[0],
                         self.KSP_MAGIC)
        self.assertEqual(bytes(self.v5[V3_KSP_BASE + 2:V3_KSP_BASE + V3_KSP_SIZE]),
                         self.ksp_payload)

    def test_note_gate_and_nav_region_cleared(self):
        self.assertEqual(
            bytes(self.v5[V4_NOTE_GATE_BASE:V4_NOTE_GATE_BASE + V4_NOTE_GATE_SIZE]),
            bytes(V4_NOTE_GATE_SIZE))
        self.assertEqual(
            bytes(self.v5[V5_NAV_LAYER_BASE:V5_NAV_LAYER_BASE + V5_NAV_LAYER_SIZE]),
            bytes(V5_NAV_LAYER_SIZE))

    def test_blast_radius_is_13_bytes(self):
        changed = {i for i in range(EEPROM_SIZE) if self.v3[i] != self.v5[i]}
        allowed = set(range(V4_NOTE_GATE_BASE, V4_NOTE_GATE_BASE + V4_NOTE_GATE_SIZE))
        allowed |= set(range(V5_NAV_LAYER_BASE, V5_NAV_LAYER_BASE + V5_NAV_LAYER_SIZE))
        self.assertTrue(changed.issubset(allowed),
                        "v3->v5 touched bytes outside the two regions it owns: "
                        "{}".format(sorted(changed - allowed)[:16]))

    def test_chain_is_available(self):
        self.assertTrue(can_migrate(3, 5))
        self.assertTrue(can_migrate(1, 5))


def _v5_dl_entry(kind, cats, voices=None, extras=None):
    e = bytearray(V6_DL_QB_V5_ENTRY)
    e[0] = kind
    e[3:3 + 6] = bytes(cats)
    e[9:9 + 12] = bytes(voices or [0] * 12)
    e[21:21 + 16] = bytes(extras or [0] * 16)
    return bytes(e)


def build_v5_image(with_dl_store=True):
    blob = bytearray(migrate_clone(build_v4_image(), 4, 5)[0])
    if with_dl_store:
        struct.pack_into("<H", blob, V6_DL_QB_BASE, V6_DL_QB_V5_MAGIC)
        body = bytearray(V6_DL_QB_SPAN - 2)
        body[0:37] = _v5_dl_entry(0, (1,   0,    2,   0,   0,   0),
                                  voices=[3] + [0] * 11,
                                  extras=[0] * 5 + [1] + [0] * 10)
        body[37:74] = _v5_dl_entry(1, (0,) * 6)
        body[50 * 37:51 * 37] = _v5_dl_entry(0, (1,) * 6)
        blob[V6_DL_QB_BASE + 2:V6_DL_QB_BASE + V6_DL_QB_SPAN] = body
    return bytes(blob)


class TestCloneMigrationV5ToV6(unittest.TestCase):

    SLOT0_VOICES = (3, 0, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0)
    SLOT0_EXTRAS = (0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    def setUp(self):
        self.v5 = build_v5_image()
        self.v6, self.notes = migrate_clone(self.v5, 5, 6)

    def _entry(self, slot):
        off = V6_DL_QB_BASE + 2 + slot * V6_DL_QB_V6_ENTRY
        return bytes(self.v6[off:off + V6_DL_QB_V6_ENTRY])

    def test_magic_is_v6(self):
        self.assertEqual(struct.unpack_from("<H", self.v6, V6_DL_QB_BASE)[0],
                         V6_DL_QB_V6_MAGIC)

    def test_snapshot_slot_converted_per_voicing(self):
        e = self._entry(0)
        self.assertEqual(e[:12], bytes(self.SLOT0_VOICES))
        self.assertEqual(e[12:28], bytes(self.SLOT0_EXTRAS))
        self.assertEqual(e[28:44], bytes(16), "converted slots are unnamed")

    def test_toggle_slot_reset(self):
        self.assertEqual(self._entry(1), bytes(V6_DL_QB_V6_ENTRY))

    def test_unconfigured_slot_stays_empty(self):
        self.assertEqual(self._entry(2), bytes(V6_DL_QB_V6_ENTRY))

    def test_old_span_tail_zeroed(self):
        tail_from = V6_DL_QB_BASE + 2 + 48 * V6_DL_QB_V6_ENTRY
        tail_to = V6_DL_QB_BASE + V6_DL_QB_SPAN
        self.assertEqual(bytes(self.v6[tail_from:tail_to]),
                         bytes(tail_to - tail_from))

    def test_only_the_drumlive_region_changes(self):
        changed = {i for i in range(EEPROM_SIZE) if self.v5[i] != self.v6[i]}
        allowed = set(range(V6_DL_QB_BASE, V6_DL_QB_BASE + V6_DL_QB_SPAN))
        self.assertTrue(changed.issubset(allowed),
                        "v5->v6 touched bytes outside the DrumLIVE region: "
                        "{}".format(sorted(changed - allowed)[:16]))

    def test_counts_reported(self):
        n = " ".join(self.notes)
        self.assertIn("1 snapshot button(s) carried over", n)
        self.assertIn("1 toggle button(s) reset", n)
        self.assertIn("1 button(s) in slots 49-64 dropped", n)

    def test_no_v5_store_reports_defaults_and_zeroes(self):
        v5 = build_v5_image(with_dl_store=False)
        v6, notes = migrate_clone(v5, 5, 6)
        self.assertEqual(bytes(v6[V6_DL_QB_BASE:V6_DL_QB_BASE + V6_DL_QB_SPAN]),
                         bytes(V6_DL_QB_SPAN))
        self.assertTrue(any("started at defaults" in n for n in notes), notes)

    def test_full_chain_from_v1_reaches_v6(self):
        self.assertTrue(can_migrate(1, 6))
        v6, _notes = migrate_clone(build_v1_image(), 1, 6)
        self.assertEqual(struct.unpack_from("<H", v6, V6_DL_QB_BASE)[0], 0,
                         "a v1 image never had a DrumLIVE store: region zeroed")
