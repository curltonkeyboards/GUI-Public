"""Keyboard clone: convert a saved settings image to the layout version the connected keyboard reports."""
import struct


class CloneMigrationError(Exception):
    pass


def _u16le(blob, addr):
    return struct.unpack_from("<H", blob, addr)[0]


def _set_u16le(blob, addr, value):
    struct.pack_into("<H", blob, addr, value)


V1_FLED_BASE = 64320
V1_FLED_STATE_COUNT = 90
V1_FLED_MAGIC_ADDR = V1_FLED_BASE + V1_FLED_STATE_COUNT * 4
V1_FLED_MAGIC = 0xF1F1

V2_FLED_STATE_COUNT = 92
V2_FLED_MAGIC_ADDR = V1_FLED_BASE + V2_FLED_STATE_COUNT * 4
V2_FLED_MAGIC = 0xF1F2
V2_FLED_NEW_STATE_DEFAULTS = [
    (190, 255, 220, 0),
    (0,     0,  40, 0),
]

ET_BASE = 60812
ET_SLOT_COUNT = 10
ET_SLOT_SIZE = 24
ET_SLOTS_ADDR = ET_BASE + 2
V1_ET_MAGIC = 0xE701
V2_ET_MAGIC = 0xE702

V2_NEW_REGIONS = [
    (37150, 10, "per-loop Rec Notes gate"),
    (65430, 10, "Keysplit/Triplesplit button config"),
    (65444, 66, "Multichannel echo presets"),
]


def _migrate_et_slot_v1_to_v2(old):
    new = bytearray(ET_SLOT_SIZE)
    new[0:4] = old[0:4]
    new[4:9] = old[4:9]
    new[9:11] = b"\x00\x00"
    new[11:23] = old[9:21]
    new[23] = old[21]
    return new


def _migrate_v1_to_v2(blob, notes):
    if _u16le(blob, V1_FLED_MAGIC_ADDR) == V1_FLED_MAGIC:
        for i, (h, s, v, blink) in enumerate(V2_FLED_NEW_STATE_DEFAULTS):
            off = V1_FLED_BASE + (V1_FLED_STATE_COUNT + i) * 4
            blob[off:off + 4] = bytes((h, s, v, blink))
        _set_u16le(blob, V2_FLED_MAGIC_ADDR, V2_FLED_MAGIC)
        notes.append("Functional LED colours: kept (2 new Multi Channel states "
                     "set to their defaults).")
    else:
        blob[V1_FLED_BASE:V2_FLED_MAGIC_ADDR + 2] = bytes(
            V2_FLED_MAGIC_ADDR + 2 - V1_FLED_BASE)
        notes.append("Functional LED colours: not configured in the clone, "
                     "cleared and will use defaults.")

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

    for addr, size, _name in V2_NEW_REGIONS:
        blob[addr:addr + size] = bytes(size)
    notes.append("New in this firmware, cleared and started at defaults: "
                 + ", ".join(name for _addr, _size, name in V2_NEW_REGIONS) + ".")


V3_KSP_BASE = 60380
V3_KSP_SIZE = 2 + 10 * 14
V2_KSQB_BASE = 65430
V2_KSQB_MAGIC = 0x4B51


def _migrate_v2_to_v3(blob, notes):
    blob[V3_KSP_BASE:V3_KSP_BASE + V3_KSP_SIZE] = bytes(V3_KSP_SIZE)
    if _u16le(blob, V2_KSQB_BASE) == V2_KSQB_MAGIC:
        notes.append("Keysplit / Triplesplit button settings: carried over "
                     "into Keysplit presets 1 and 2.")
    else:
        notes.append("Keysplit presets: new in this firmware, started at "
                     "defaults.")


V4_NOTE_GATE_BASE = 37150
V4_NOTE_GATE_SIZE = 2 + 8


def _migrate_v3_to_v4(blob, notes):
    blob[V4_NOTE_GATE_BASE:V4_NOTE_GATE_BASE + V4_NOTE_GATE_SIZE] = bytes(
        V4_NOTE_GATE_SIZE)
    notes.append("Per-loop record gate: the old key-zone 'Rec Notes' setting "
                 "was replaced by a per-channel 'Rec Channel' gate and resets "
                 "to All Channels.")


V5_NAV_LAYER_BASE = 60373
V5_NAV_LAYER_SIZE = 2 + 1


def _migrate_v4_to_v5(blob, notes):
    blob[V5_NAV_LAYER_BASE:V5_NAV_LAYER_BASE + V5_NAV_LAYER_SIZE] = bytes(
        V5_NAV_LAYER_SIZE)
    notes.append("Navigation layer: new in this firmware, starts at the "
                 "default (Layer 1).")


V6_DL_QB_BASE        = 61600
V6_DL_QB_V5_MAGIC    = 0xDB07
V6_DL_QB_V6_MAGIC    = 0xDB08
V6_DL_QB_V5_ENTRY    = 37
V6_DL_QB_V5_SLOTS    = 64
V6_DL_QB_V6_ENTRY    = 44
V6_DL_QB_V6_SLOTS    = 48
V6_DL_QB_SPAN        = 2 + V6_DL_QB_V5_SLOTS * V6_DL_QB_V5_ENTRY
V6_DL_NUM_VOICES     = 12
V6_DL_NUM_EXTRA      = 16
V6_DL_MODE_COUNT     = 4
V6_DL_V5_VOICE_CATEGORY = (0, 1, 2, 2, 1, 1, 5, 3, 4, 4, 4, 5)
V6_DL_V5_EXTRA_CATEGORY = (3, 3, 3, 3, 3, 2, 1, 4, 4, 4, 5, 5, 5, 5, 5, 5)


def _v6_convert_dl_slot(old):
    snap = bytearray(V6_DL_NUM_VOICES + V6_DL_NUM_EXTRA)
    if old[0] == 0:
        cat = old[3:3 + 6]
        voc = old[3 + 6:3 + 6 + V6_DL_NUM_VOICES]
        ext = old[3 + 6 + V6_DL_NUM_VOICES:3 + 6 + V6_DL_NUM_VOICES + V6_DL_NUM_EXTRA]
        for v in range(V6_DL_NUM_VOICES):
            m = voc[v] if voc[v] != 0 else cat[V6_DL_V5_VOICE_CATEGORY[v]]
            snap[v] = m if m < V6_DL_MODE_COUNT else 0
        for e in range(V6_DL_NUM_EXTRA):
            m = ext[e] if ext[e] != 0 else cat[V6_DL_V5_EXTRA_CATEGORY[e]]
            snap[V6_DL_NUM_VOICES + e] = m if m < V6_DL_MODE_COUNT else 0
    return bytes(snap) + bytes(16)


def _migrate_v5_to_v6(blob, notes):
    region = bytes(blob[V6_DL_QB_BASE:V6_DL_QB_BASE + V6_DL_QB_SPAN])
    kept = dropped_toggles = dropped_high = 0
    new = bytearray(V6_DL_QB_SPAN)
    if _u16le(region, 0) == V6_DL_QB_V5_MAGIC:
        for s in range(V6_DL_QB_V5_SLOTS):
            off = 2 + s * V6_DL_QB_V5_ENTRY
            old = region[off:off + V6_DL_QB_V5_ENTRY]
            configured = old[0] != 0 or any(b != 0 for b in old[3:3 + 34])
            if s >= V6_DL_QB_V6_SLOTS:
                if configured:
                    dropped_high += 1
                continue
            if old[0] != 0:
                dropped_toggles += 1
                continue
            ent = _v6_convert_dl_slot(old)
            noff = 2 + s * V6_DL_QB_V6_ENTRY
            new[noff:noff + V6_DL_QB_V6_ENTRY] = ent
            if configured:
                kept += 1
        _set_u16le(new, 0, V6_DL_QB_V6_MAGIC)
        notes.append("DrumLIVE QuickBuild buttons: {} snapshot button(s) carried "
                     "over (converted to the new per-voicing format, unnamed); "
                     "{} toggle button(s) reset (toggles no longer exist); "
                     "{} button(s) in slots 49-64 dropped (48 slots now)."
                     .format(kept, dropped_toggles, dropped_high))
    else:
        notes.append("DrumLIVE QuickBuild buttons: none were configured; "
                     "started at defaults.")
    blob[V6_DL_QB_BASE:V6_DL_QB_BASE + V6_DL_QB_SPAN] = new


V7_DYN_COMBO_OLD_BASE = 2805
V7_DYN_COMBO_OLD_COUNT = 100
V7_DYN_KO_OLD_BASE = 3805
V7_DYN_KO_OLD_COUNT = 32
V7_DYN_ENTRY = 10
V7_DYN_KO_NEW_BASE = V7_DYN_COMBO_OLD_BASE
V7_DYN_KO_NEW_COUNT = 100
V7_DYN_SPAN_END = V7_DYN_KO_OLD_BASE + V7_DYN_KO_OLD_COUNT * V7_DYN_ENTRY
V7_KO_LAYERS_MASK = 0x0FFF


def _migrate_v6_to_v7(blob, notes):
    old_ko = bytes(blob[V7_DYN_KO_OLD_BASE:V7_DYN_SPAN_END])
    old_combos = bytes(blob[V7_DYN_COMBO_OLD_BASE:V7_DYN_KO_OLD_BASE])
    combos_dropped = sum(1 for i in range(V7_DYN_COMBO_OLD_COUNT)
                         if any(old_combos[i * V7_DYN_ENTRY:(i + 1) * V7_DYN_ENTRY]))

    new = bytearray(V7_DYN_SPAN_END - V7_DYN_COMBO_OLD_BASE)
    kept = 0
    for i in range(V7_DYN_KO_OLD_COUNT):
        ent = bytearray(old_ko[i * V7_DYN_ENTRY:(i + 1) * V7_DYN_ENTRY])
        if not any(ent):
            continue
        layers = _u16le(ent, 4) & V7_KO_LAYERS_MASK
        _set_u16le(ent, 4, layers)
        off = (V7_DYN_KO_NEW_BASE - V7_DYN_COMBO_OLD_BASE) + i * V7_DYN_ENTRY
        new[off:off + V7_DYN_ENTRY] = ent
        kept += 1
    blob[V7_DYN_COMBO_OLD_BASE:V7_DYN_SPAN_END] = new

    notes.append("Combo Keys (key overrides): {} entr{} carried over into the first 32 of the "
                 "100 slots (Fn held-key bits cleared). {} combo(s) dropped: combos no longer "
                 "exist.".format(kept, "y" if kept == 1 else "ies", combos_dropped))


V8_MOUSE_TIMING_BASE = 60522
V8_MOUSE_TIMING_SIZE = 6


def _migrate_v7_to_v8(blob, notes):
    blob[V8_MOUSE_TIMING_BASE:V8_MOUSE_TIMING_BASE + V8_MOUSE_TIMING_SIZE] = bytes(
        V8_MOUSE_TIMING_SIZE)
    notes.append("Macro mouse timing (click delay, double click speed): new in this "
                 "firmware, starts at the defaults.")


_MIGRATIONS = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
    4: _migrate_v4_to_v5,
    5: _migrate_v5_to_v6,
    6: _migrate_v6_to_v7,
    7: _migrate_v7_to_v8,
}


def can_migrate(from_version, to_version):
    if from_version == to_version:
        return True
    if from_version > to_version:
        return False
    return all(v in _MIGRATIONS for v in range(from_version, to_version))


def migrate_clone(data, from_version, to_version):
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
