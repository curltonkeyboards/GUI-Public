import collections
import time
import unittest

from protocol.keyboard_comm import Keyboard
from util import hid_send


class FakeKeyboard:
    def __init__(self):
        self.queue = collections.deque()
        self.sets = []

    def _put(self, cmd, bank, data):
        pkt = bytearray(32)
        pkt[:6] = bytes([0x7D, 0x00, 0x4D, cmd, bank, 0])
        pkt[6:6 + len(data)] = data
        self.queue.append(bytes(pkt))

    def write(self, buf):
        msg = buf[1:]
        if msg[:3] == b"\x7d\x00\x4d":
            cmd = msg[3]
            if cmd == 0xB4:
                self._put(0xB0, 0, bytes([5, 1, 0] + list(range(20, 28))))
                for b in range(2):
                    self._put(0xB1, b, bytes(range(30 + b * 20, 50 + b * 20)))
                for b in range(2):
                    self._put(0xB2, b, bytes(range(80 + b * 24, 104 + b * 24)))
                self._put(0xB3, 0, bytes([1, 7] + list(range(60, 68))))
            elif cmd in (0xB0, 0xB1, 0xB2, 0xB3):
                self.sets.append(cmd)
                self._put(cmd, msg[4], b"")
        return len(buf)

    def read(self, n, timeout_ms=0):
        if self.queue:
            return list(self.queue.popleft())
        time.sleep(timeout_ms / 1000.0)
        return []


def make(codec):
    kb = Keyboard.__new__(Keyboard)
    kb._usb_send_raw = hid_send
    kb.hid_codec = codec
    kb.dev = FakeKeyboard()
    kb.usb_send = kb._usb_send_codec
    return kb


class TestThruLoopConfig(unittest.TestCase):

    def check(self, codec):
        kb = make(codec)
        cfg = kb.get_thruloop_config()
        self.assertIsNotNone(cfg)
        self.assertEqual(kb.dev.sets, [])
        self.assertEqual(cfg["loopChannel"], 5)
        self.assertTrue(cfg["syncMidi"])
        self.assertEqual(cfg["restartCCs"], list(range(20, 28)))
        self.assertEqual(cfg["mainCCs"], list(range(30, 70)))
        self.assertEqual(cfg["overdubCCs"], list(range(80, 128)))
        # the keyboard sent 1 = "use the single LoopChop CC", so not separate
        self.assertFalse(cfg["separateLoopChopCC"])
        self.assertEqual(cfg["masterCC"], 7)
        self.assertEqual(cfg["navCCs"], list(range(60, 68)))

    def test_msw_codec(self):
        self.check("msw")

    def test_legacy_codec(self):
        self.check("legacy")

    def test_stale_packet_ahead_of_reply(self):
        kb = make("msw")
        kb.dev._put(0xB7, 0, b"\x01\x02")
        self.assertIsNotNone(kb.get_thruloop_config())

    def test_no_reply_gives_none_and_no_writes(self):
        kb = make("msw")
        kb.dev.write = lambda buf: len(buf)
        self.assertIsNone(kb.get_thruloop_config())


if __name__ == "__main__":
    unittest.main()
