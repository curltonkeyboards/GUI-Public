# SPDX-License-Identifier: GPL-2.0-or-later
"""Layout definitions bundled with the app, keyed by the keyboard's model id.

GENERATED FILE - do not edit by hand. A keyboard that answers IDENT names
its model id; when that id is listed here the app uses this document as the
keyboard's layout definition and asks the keyboard for nothing more. The
document is the minified JSON the app has always parsed (matrix size,
key layout, lighting kind, MIDI capability), so everything downstream of
``Keyboard.reload_layout`` is unchanged.
"""
import json

# model id -> minified definition JSON
_DEFINITIONS = {
    1: '{"name":"ortho5x14","vendorId":"0xBEEF","productId":"0x0000","lighting":"vialrgb","matrix":{"rows":6,"cols":14},"layouts":{"keymap":[[{"x":2.5},"0,0","0,1","0,2","0,3","0,4","0,5","0,6","0,7","0,8","0,9","0,10","0,11","0,12","0,13"],["0,0\\n\\n\\n\\n\\n\\n\\n\\n\\ne","5,0","0,1\\n\\n\\n\\n\\n\\n\\n\\n\\ne",{"x":-0.5},"1,0","1,1","1,2","1,3","1,4","1,5","1,6","1,7","1,8","1,9","1,10","1,11","1,12","1,13"],[{"x":2.5},"2,0","2,1","2,2","2,3","2,4","2,5","2,6","2,7","2,8","2,9","2,10","2,11","2,12","2,13"],["1,0\\n\\n\\n\\n\\n\\n\\n\\n\\ne","5,1","1,1\\n\\n\\n\\n\\n\\n\\n\\n\\ne",{"x":-0.5},"3,0","3,1","3,2","3,3","3,4","3,5","3,6","3,7","3,8","3,9","3,10","3,11","3,12","3,13"],[{"x":2.5},"4,0","4,1","4,2","4,3","4,4","4,5","4,6","4,7","4,8","4,9","4,10","4,11","4,12","4,13"],[{"x":0,"y":0.5},"5,2"]]},"vial":{"midi":"advanced"}}',
}


def has_definition(model_id):
    """True if the app carries a layout definition for this model id."""
    return model_id in _DEFINITIONS


def get_definition(model_id):
    """The parsed layout definition for ``model_id`` (a fresh object per
    call), or None when the model is unknown."""
    text = _DEFINITIONS.get(model_id)
    if text is None:
        return None
    return json.loads(text)
