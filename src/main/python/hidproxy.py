# SPDX-License-Identifier: GPL-2.0-or-later
import struct
import sys

from protocol.constants import CMD_VIA_VIAL_PREFIX, CMD_VIAL_GET_KEYBOARD_ID

if sys.platform == "emscripten":

    import vialglue
    import json

    class hiddevice:

        def __init__(self):
            self._pending = False

        def open_path(self, path):
            print("opening {}...".format(path))

        def write(self, data):
            self._pending = True
            return vialglue.write_device(data)

        def read(self, length, timeout_ms=0):
            # The browser only has a reply for a request we sent: with none
            # outstanding there is nothing to wait for (read_device would
            # wait forever), so report "no data" like a timed-out read.
            if not self._pending:
                return b""
            self._pending = False
            return vialglue.read_device()


    class hid:

        @staticmethod
        def enumerate():
            from util import hid_send

            desc = json.loads(vialglue.get_device_desc())
            # WebHID does not expose the vendor/product IDs discovery keys on, so
            # probe the device with a keyboard-ID request and, if it answers
            # with a valid ID, stamp the MIDIswitch VID/PID into the descriptor.
            from util import MIDISWITCH_USB_VID, MIDISWITCH_USB_PID
            from protocol.msw_protocol import build_ident_request, parse_ident
            dev = hid.device()
            # IDENT first; a keyboard that predates it still answers the
            # legacy keyboard-ID request.
            ident = parse_ident(hid_send(dev, build_ident_request(), retries=20))
            if ident is not None:
                uid = struct.pack("<Q", ident["model_uid"])
            else:
                data = hid_send(dev, struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_GET_KEYBOARD_ID), retries=20)
                uid = data[4:12]
            if uid != b"\x00" * 8:
                desc["vendor_id"] = MIDISWITCH_USB_VID
                desc["product_id"] = MIDISWITCH_USB_PID
            return [desc]

        @staticmethod
        def device():
            return hiddevice()

elif sys.platform.startswith("linux"):
    import hidraw as hid
else:
    import hid
