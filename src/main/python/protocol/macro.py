import struct

from keycodes.keycodes import Keycode
from macro.macro_action import (SS_TAP_CODE, SS_DOWN_CODE, SS_UP_CODE, ActionText, ActionTap, ActionDown, ActionUp,
    SS_QMK_PREFIX, SS_DELAY_CODE, ActionDelay, VIAL_MACRO_EXT_TAP, VIAL_MACRO_EXT_DOWN, VIAL_MACRO_EXT_UP,
    SS_BPM_DELAY_CODE, ActionBPMDelay, SS_BPM_DELAY_REPEAT_CODE,
    SS_MIXING_CONTROL_CODE, ActionMixingControl)
from macro.macro_action_ui import tag_to_action
from protocol.base_protocol import BaseProtocol
from protocol.constants import CMD_VIA_MACRO_GET_COUNT, CMD_VIA_MACRO_GET_BUFFER_SIZE, CMD_VIA_MACRO_GET_BUFFER, \
    CMD_VIA_MACRO_SET_BUFFER, BUFFER_FETCH_CHUNK, VIAL_PROTOCOL_ADVANCED_MACROS
from unlocker import Unlocker
from util import chunks


def macro_deserialize_v1(data):
    """
    Deserialize a single macro, protocol version 1
    """

    out = []
    sequence = []
    data = bytearray(data)
    while len(data) > 0:
        if data[0] in [SS_TAP_CODE, SS_DOWN_CODE, SS_UP_CODE]:
            if len(data) < 2:
                break

            # append to previous *_CODE if it's the same type, otherwise create a new entry
            if len(sequence) > 0 and isinstance(sequence[-1], list) and sequence[-1][0] == data[0]:
                sequence[-1][1].append(data[1])
            else:
                sequence.append([data[0], [data[1]]])

            data.pop(0)
            data.pop(0)
        else:
            # append to previous string if it is a string, otherwise create a new entry
            ch = chr(data[0])
            if len(sequence) > 0 and isinstance(sequence[-1], str):
                sequence[-1] += ch
            else:
                sequence.append(ch)
            data.pop(0)
    for s in sequence:
        if isinstance(s, str):
            out.append(ActionText(s))
        else:
            keycodes = s[1]
            cls = {SS_TAP_CODE: ActionTap, SS_DOWN_CODE: ActionDown, SS_UP_CODE: ActionUp}[s[0]]
            keycodes = [Keycode.serialize(kc) for kc in keycodes]
            out.append(cls(keycodes))
    return out


def macro_deserialize_v2(data):
    """
    Deserialize a single macro, protocol version 2
    """

    out = []
    sequence = []
    data = bytearray(data)
    while len(data) > 0:
        if data[0] == SS_QMK_PREFIX:
            if len(data) < 2:
                break

            act = data[1]
            if act in [SS_TAP_CODE, SS_DOWN_CODE, SS_UP_CODE,
                       VIAL_MACRO_EXT_TAP, VIAL_MACRO_EXT_DOWN, VIAL_MACRO_EXT_UP]:
                if act in [SS_TAP_CODE, SS_DOWN_CODE, SS_UP_CODE]:
                    if len(data) < 3:
                        break
                    length = 3
                    kc = data[2]
                else:
                    remap = {VIAL_MACRO_EXT_TAP: SS_TAP_CODE,
                             VIAL_MACRO_EXT_DOWN: SS_DOWN_CODE,
                             VIAL_MACRO_EXT_UP: SS_UP_CODE}
                    act = remap[act]
                    if len(data) < 4:
                        break
                    length = 4
                    kc = struct.unpack("<H", data[2:4])[0]
                    # see decode_keycode() in qmk
                    if kc > 0xFF00:
                        kc = (kc & 0xFF) << 8

                # append to previous *_CODE if it's the same type, otherwise create a new entry
                if len(sequence) > 0 and isinstance(sequence[-1], list) and sequence[-1][0] == act:
                    sequence[-1][1].append(kc)
                else:
                    sequence.append([act, [kc]])

                for x in range(length):
                    data.pop(0)
            elif act == SS_DELAY_CODE:
                if len(data) < 4:
                    break

                # decode the delay
                delay = (data[2] - 1) + (data[3] - 1) * 255
                sequence.append([SS_DELAY_CODE, delay])

                for x in range(4):
                    data.pop(0)
            elif act == SS_BPM_DELAY_CODE:
                if len(data) < 4:
                    break

                note_value = data[2] - 1    # 0=1/1, 1=1/2, 2=1/4, 3=1/8, 4=1/16
                timing_mode = data[3] - 1   # 0=straight, 1=triplet, 2=dotted

                sequence.append([SS_BPM_DELAY_CODE, note_value, timing_mode])

                for x in range(4):
                    data.pop(0)
            elif act == SS_BPM_DELAY_REPEAT_CODE:
                if len(data) < 5:
                    break

                note_value = data[2] - 1
                timing_mode = data[3] - 1
                repeat = data[4] - 1

                sequence.append([SS_BPM_DELAY_REPEAT_CODE, note_value, timing_mode, repeat])

                for x in range(5):
                    data.pop(0)
            elif act == SS_MIXING_CONTROL_CODE:
                if len(data) < 9:
                    break

                cc_num = data[2] - 1
                channel = data[3] - 1
                start_val = data[4] - 1
                end_val = data[5] - 1
                dur_type = data[6] - 1
                d0 = data[7]
                d1 = data[8]

                if dur_type == 0:
                    # ms duration
                    duration = (d0 - 1) + (d1 - 1) * 255
                else:
                    # BPM duration: pack note_value and timing into duration
                    duration = ((d0 - 1) << 8) | (d1 - 1)

                sequence.append([SS_MIXING_CONTROL_CODE, cc_num, channel, start_val,
                                end_val, dur_type, duration])

                for x in range(9):
                    data.pop(0)
            else:
                # it is clearly malformed, just skip this byte and hope for the best
                data.pop(0)
                data.pop(0)
        else:
            # append to previous string if it is a string, otherwise create a new entry
            ch = chr(data[0])
            if len(sequence) > 0 and isinstance(sequence[-1], str):
                sequence[-1] += ch
            else:
                sequence.append(ch)
            data.pop(0)
    for s in sequence:

        if isinstance(s, str):
            out.append(ActionText(s))
        else:
            if s[0] == SS_BPM_DELAY_CODE:
                out.append(ActionBPMDelay(s[1], s[2]))
            elif s[0] == SS_BPM_DELAY_REPEAT_CODE:
                # Preserve the repeat count invisibly on the plain BPM-delay
                # action so a GUI round-trip re-emits the same 5-byte opcode
                # (the on-device configurator authors these; converting to a
                # plain delay silently destroyed the repeat).
                a = ActionBPMDelay(s[1], s[2])
                a.repeat = s[3]
                out.append(a)
            elif s[0] == SS_MIXING_CONTROL_CODE:
                out.append(ActionMixingControl(s[1], s[2], s[3], s[4], s[5], s[6]))
            else:
                args = None
                if s[0] in [SS_TAP_CODE, SS_DOWN_CODE, SS_UP_CODE]:
                    args = s[1]
                    if args is not None:
                        args = [Keycode.serialize(kc) for kc in args]
                elif s[0] == SS_DELAY_CODE:
                    args = s[1]

                if args is not None:
                    cls = {SS_TAP_CODE: ActionTap, SS_DOWN_CODE: ActionDown, SS_UP_CODE: ActionUp,
                           SS_DELAY_CODE: ActionDelay}[s[0]]
                    out.append(cls(args))
    return out


class ProtocolMacro(BaseProtocol):

    def reload_macros_early(self):
        """ Reload macro information that doesn't require any info about keycodes, i.e. number of macros """
        data = self.usb_send(self.dev, struct.pack("B", CMD_VIA_MACRO_GET_COUNT), retries=20)
        self.macro_count = data[1]
        data = self.usb_send(self.dev, struct.pack("B", CMD_VIA_MACRO_GET_BUFFER_SIZE), retries=20)
        self.macro_memory = struct.unpack(">H", data[1:3])[0]

    def reload_macros_late(self):
        """ Load actual keycodes """
        self.macro = b""
        if not hasattr(self, 'macro_loop_modes') or self.macro_loop_modes is None:
            self.macro_loop_modes = [0] * self.macro_count
        if not hasattr(self, 'macro_sync_flags') or self.macro_sync_flags is None:
            self.macro_sync_flags = [False] * self.macro_count
        if self.macro_memory:
            # now retrieve the entire buffer, MACRO_CHUNK bytes at a time, as that is what fits into a packet
            for x in range(0, self.macro_memory, BUFFER_FETCH_CHUNK):
                sz = min(BUFFER_FETCH_CHUNK, self.macro_memory - x)
                data = self.usb_send(self.dev, struct.pack(">BHB", CMD_VIA_MACRO_GET_BUFFER, x, sz), retries=20)
                self.macro += data[4:4 + sz]
                if self.macro.count(b"\x00") > self.macro_count:
                    break
            # macros are stored as NUL-separated strings, so let's clean up the buffer
            # ensuring we only get macro_count strings after we split by NUL
            macros = self.macro.split(b"\x00") + [b""] * self.macro_count
            self.macro = b"\x00".join(macros[:self.macro_count]) + b"\x00"
        # Read the persisted loop-mode/per-sync/global-sync state back from the
        # device (0x95). Older firmware lacks the command — the seeded defaults
        # above stay, exactly as before.
        self.reload_macro_modes()

    def reload_macro_modes(self):
        """Read the device's persisted macro loop modes, per-macro sync flags,
        and the global macro-sync bool via the 0x95 GET (4 chunks x 24 bytes of
        the 2-bit/1-bit packed state). Returns False (keeping the local
        defaults) on old firmware or comm failure."""
        self.macro_sync_to_loop_device = None
        try:
            raw = bytearray()
            for chunk in range(4):
                packet = self._create_hid_packet(0x95, chunk, None)
                resp = self.usb_send(self.dev, packet, retries=3)
                if (not resp or len(resp) < 31 or resp[3] != 0x95 or
                        resp[4] != 0x01 or resp[5] != chunk):
                    return False
                raw += bytes(resp[6:30])
                if chunk == 3:
                    self.macro_sync_to_loop_device = (resp[30] == 1)
            self.macro_loop_modes = [(raw[m // 4] >> ((m % 4) * 2)) & 0x03
                                     for m in range(self.macro_count)]
            self.macro_sync_flags = [bool((raw[64 + m // 8] >> (m % 8)) & 1)
                                     for m in range(self.macro_count)]
            return True
        except Exception:
            return False

    def reload_macros(self):
        """ Loads macro information from the keyboard """
        self.reload_macros_early()
        self.reload_macros_late()

    def set_macro(self, data):
        if len(data) > self.macro_memory:
            raise RuntimeError("the macro is too big: got {} max {}".format(len(data), self.macro_memory))

        for x, chunk in enumerate(chunks(data, BUFFER_FETCH_CHUNK)):
            off = x * BUFFER_FETCH_CHUNK
            self.usb_send(self.dev, struct.pack(">BHB", CMD_VIA_MACRO_SET_BUFFER, off, len(chunk)) + chunk,
                          retries=20)
        self.macro = data

    def save_macro(self):
        macros = self.macros_deserialize(self.macro)
        out = []
        for macro in macros:
            out.append([act.save() for act in macro])
        return {"macros": out, "loop_modes": self.get_macro_loop_modes(),
                "sync_flags": self.get_macro_sync_flags()}

    def restore_macros(self, macros):
        # Support both old format (list) and new format (dict with loop_modes/sync_flags)
        loop_modes = None
        sync_flags = None
        if isinstance(macros, dict):
            loop_modes = macros.get("loop_modes", None)
            sync_flags = macros.get("sync_flags", None)
            macros = macros.get("macros", [])
        if not isinstance(macros, list):
            return

        if loop_modes is not None:
            self.set_macro_loop_modes(loop_modes)
        if sync_flags is not None:
            self.set_macro_sync_flags(sync_flags)

        full_macro = []
        for macro in macros:
            actions = []
            for act in macro:
                if act[0] in tag_to_action:
                    obj = tag_to_action[act[0]]()
                    obj.restore(act)
                    actions.append(obj)
            full_macro.append(actions)
        if len(full_macro) < self.macro_count:
            full_macro += [[] for x in range(self.macro_count - len(full_macro))]
        full_macro = full_macro[:self.macro_count]
        # TODO: log a warning if macro is cutoff
        data = self.macros_serialize(full_macro)[0:self.macro_memory]
        if data != self.macro:
            Unlocker.unlock(self)
            self.set_macro(data)

    def macro_serialize(self, macro):
        """
        Serialize a single macro, a macro is made out of macro actions (BasicAction)
        """
        out = b""
        for action in macro:
            out += action.serialize(self.vial_protocol)
        return out

    def macro_deserialize(self, data):
        """
        Deserialize a single macro
        """
        if self.vial_protocol >= VIAL_PROTOCOL_ADVANCED_MACROS:
            return macro_deserialize_v2(data)
        return macro_deserialize_v1(data)

    def macros_serialize(self, macros):
        """
        Serialize a list of macros, the list must contain all macros (macro_count)
        """
        if len(macros) != self.macro_count:
            raise RuntimeError("expected array with {} macros, got {} macros".format(self.macro_count, len(macros)))
        out = [self.macro_serialize(macro) for macro in macros]
        return b"\x00".join(out) + b"\x00"

    def macros_deserialize(self, data):
        """
        Deserialize a list of macros
        """
        macros = data.split(b"\x00")
        if len(macros) < self.macro_count:
            macros += [b""] * (self.macro_count - len(macros))
        macros = macros[:self.macro_count]
        return [self.macro_deserialize(x) for x in macros]

    def set_macro_loop_modes(self, modes):
        """
        Store and send loop modes (list of int 0-3, one per macro) to firmware.

        Only CHANGED entries are sent. There is no GET for these, so the local
        cache seeds to all-zero on connect — pushing the full list on every
        macro Save wiped whatever the device had persisted (including modes set
        from the on-device Options page), and cost ~255 HID round-trips each
        doing a full EEPROM region write.
        """
        prev = self.get_macro_loop_modes()
        self.macro_loop_modes = modes[:self.macro_count]
        try:
            from protocol.keyboard_comm import PARAM_MACRO_LOOP_MODE
            for macro_id, mode in enumerate(self.macro_loop_modes):
                if macro_id < len(prev) and prev[macro_id] == mode:
                    continue
                self.set_keyboard_param_single(PARAM_MACRO_LOOP_MODE,
                                               (macro_id & 0xFF) | ((mode & 0x03) << 8))
        except Exception:
            pass

    def get_macro_loop_modes(self):
        """
        Get loop modes. Returns list of int 0-3, one per macro.
        """
        if not hasattr(self, 'macro_loop_modes') or self.macro_loop_modes is None:
            self.macro_loop_modes = [0] * self.macro_count
        return self.macro_loop_modes

    def set_macro_sync_flags(self, flags):
        """
        Store and send per-macro sync-to-BPM flags to firmware.

        Only CHANGED entries are sent (see set_macro_loop_modes — no GET
        exists, so a full-list push clobbered on-device state).
        """
        prev = self.get_macro_sync_flags()
        self.macro_sync_flags = [bool(f) for f in flags[:self.macro_count]]
        try:
            from protocol.keyboard_comm import PARAM_MACRO_PER_SYNC
            for macro_id, sync in enumerate(self.macro_sync_flags):
                if macro_id < len(prev) and bool(prev[macro_id]) == sync:
                    continue
                self.set_keyboard_param_single(PARAM_MACRO_PER_SYNC,
                                               (macro_id & 0xFF) | ((1 if sync else 0) << 8))
        except Exception:
            pass

    def get_macro_sync_flags(self):
        """
        Get per-macro sync flags. Returns list of bool, one per macro.
        """
        if not hasattr(self, 'macro_sync_flags') or self.macro_sync_flags is None:
            self.macro_sync_flags = [False] * self.macro_count
        return self.macro_sync_flags
