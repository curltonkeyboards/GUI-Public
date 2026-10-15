# SPDX-License-Identifier: GPL-2.0-or-later
"""App-wide switch for the debug windows (File > Show debug windows).

Debug consoles, logs and similar developer output register here. They are
hidden unless the user turns the option on; the choice is remembered."""

import weakref

from PyQt5.QtCore import QSettings

_SETTINGS_KEY = "debug/show_windows"


def _settings():
    return QSettings("MIDIswitch", "SwitchStation")


class DebugWindows:
    _visible = None
    _widgets = []   # weak references

    @classmethod
    def visible(cls):
        if cls._visible is None:
            val = _settings().value(_SETTINGS_KEY, False)
            cls._visible = val in (True, "true", "1", 1)
        return cls._visible

    @classmethod
    def register(cls, widget):
        """Mark `widget` as a debug window: shown only while the option is on."""
        widget._is_debug_window = True
        cls._widgets.append(weakref.ref(widget))
        widget.setVisible(cls.visible())
        return widget

    @classmethod
    def set_visible(cls, visible):
        cls._visible = bool(visible)
        _settings().setValue(_SETTINGS_KEY, cls._visible)
        alive = []
        for ref in cls._widgets:
            w = ref()
            if w is None:
                continue
            try:
                w.setVisible(cls._visible)
            except RuntimeError:        # C++ object already deleted
                continue
            alive.append(ref)
        cls._widgets = alive

    @classmethod
    def allowed(cls, widget):
        """Whether `widget` may be shown (False for a debug window while the
        option is off). Used by code that shows/hides groups of widgets."""
        return cls.visible() or not getattr(widget, "_is_debug_window", False)
