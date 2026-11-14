# SPDX-License-Identifier: GPL-2.0-or-later
"""Basic / Advanced mode (the "Basic mode" switch at the top right of the window).

Basic mode is a home screen with one bubble per tab: a bubble opens that tab
on its own, with a Home button to come back. Advanced mode is every tab in one
row. Either way every page shows all of its options (pages_simplified() is
False); the gating below is kept so a page could be simplified again later.

How the rest of the app uses this:

    ui_mode.advanced_only(widget)      the widget is hidden in Basic mode
    ui_mode.basic_only(widget)         the widget is shown only in Basic mode
    ui_mode.limit_tabs(tabs, labels)   a QTabWidget keeps only these tabs in Basic mode
    ui_mode.on_change(callback)        called after the mode changes
    ui_mode.is_basic()

A widget marked with advanced_only() may still be shown and hidden by the
code that owns it, as before. The mark remembers what that code last asked
for, keeps the widget hidden while in Basic mode, and puts it back the way
its owner wanted on the way to Advanced mode.
"""

import sys
import weakref

from PyQt5 import sip

from PyQt5.QtCore import QEvent, QObject, QSettings, Qt

BASIC = "Basic"
ADVANCED = "Advanced"
MODES = (BASIC, ADVANCED)

_SETTINGS_KEY = "ui_mode"

_mode = None
_gates = []         # _Gate objects
_tab_limits = []    # (weakref to QTabWidget, set of labels kept in Basic mode)
_callbacks = []
_next_tidy = 200


def _settings():
    return QSettings("MIDIswitch", "SwitchStation")


def mode():
    global _mode
    if _mode is None:
        saved = _settings().value(_SETTINGS_KEY, BASIC)
        _mode = saved if saved in MODES else BASIC
    return _mode


def is_basic():
    return mode() == BASIC


def pages_simplified():
    """Whether pages hide their advanced parts in Basic mode. They do not:
    Basic mode only changes how you get to the pages."""
    return False


def set_mode(new_mode):
    global _mode
    if new_mode not in MODES or new_mode == mode():
        return
    _mode = new_mode
    _settings().setValue(_SETTINGS_KEY, new_mode)
    refresh()
    for callback in list(_callbacks):
        try:
            callback()
        except RuntimeError:        # belongs to a widget that has been deleted
            _callbacks.remove(callback)


def on_change(callback):
    _callbacks.append(callback)


class _Gate(QObject):
    """Keeps one widget hidden while the mode says so (see the module notes)."""

    def __init__(self, widget, show_in_basic):
        super().__init__(widget)
        self.widget = weakref.ref(widget)
        self.show_in_basic = show_in_basic
        # A widget that nobody has shown or hidden yet counts as wanted: it
        # appears along with its parent.
        self.wanted = not (widget.testAttribute(Qt.WA_WState_ExplicitShowHide) and widget.isHidden())
        self.busy = False
        self.dead = False
        widget.installEventFilter(self)
        if not self.allowed():
            self._set(False)

    def allowed(self):
        return pages_simplified() == self.show_in_basic

    def eventFilter(self, obj, event):
        if not self.busy and obj is self.widget():
            kind = event.type()
            if kind == QEvent.ShowToParent:
                self.wanted = True
                if not self.allowed():
                    self._set(False)
            elif kind == QEvent.HideToParent:
                self.wanted = False
        return False

    def _set(self, visible):
        widget = self.widget()
        if widget is None:
            self.dead = True
            return
        self.busy = True
        try:
            # (showing a widget that has no parent yet would open it as a window)
            if not visible or widget.parentWidget() is not None:
                widget.setVisible(visible)
        except RuntimeError:        # C++ object already deleted
            self.dead = True
        finally:
            self.busy = False

    def apply(self):
        self._set(self.wanted and self.allowed())


def advanced_only(*widgets):
    """Hide these widgets in Basic mode. Returns the first one, so a call can
    wrap the creation of a widget."""
    for widget in widgets:
        if widget is not None:
            _gates.append(_Gate(widget, show_in_basic=False))
    _forget_deleted()
    return widgets[0] if widgets else None


def _forget_deleted():
    """Parts of the key picker are rebuilt often, each time marking new
    widgets; drop the marks of the ones that have gone."""
    global _next_tidy
    if len(_gates) >= _next_tidy:
        _gates[:] = [g for g in _gates if not g.dead and g.widget() is not None and not sip.isdeleted(g.widget())]
        _next_tidy = len(_gates) + 200


def basic_only(*widgets):
    for widget in widgets:
        if widget is not None:
            _gates.append(_Gate(widget, show_in_basic=True))
    return widgets[0] if widgets else None


def limit_tabs(tab_widget, basic_labels):
    """In Basic mode `tab_widget` shows only the tabs whose label is in
    `basic_labels`. Call apply_tab_limits() again after adding tabs."""
    _tab_limits.append((weakref.ref(tab_widget), set(basic_labels)))
    _apply_tab_limit(tab_widget, set(basic_labels))


def _apply_tab_limit(tab_widget, labels):
    basic = pages_simplified()
    first_visible = -1
    for index in range(tab_widget.count()):
        visible = (not basic) or tab_widget.tabText(index) in labels
        tab_widget.setTabVisible(index, visible)
        if visible and first_visible < 0:
            first_visible = index
    current = tab_widget.currentIndex()
    if first_visible >= 0 and (current < 0 or not tab_widget.isTabVisible(current)):
        tab_widget.setCurrentIndex(first_visible)
    # with one tab left there is nothing to choose between
    visible_count = sum(1 for i in range(tab_widget.count()) if tab_widget.isTabVisible(i))
    tab_widget.tabBar().setVisible(visible_count > 1)


def apply_tab_limits():
    alive = []
    for ref, labels in _tab_limits:
        tab_widget = ref()
        if tab_widget is None:
            continue
        try:
            _apply_tab_limit(tab_widget, labels)
        except RuntimeError:
            continue
        alive.append((ref, labels))
    _tab_limits[:] = alive


def refresh():
    """Put every marked widget and tab in line with the current mode."""
    alive = []
    for gate in _gates:
        if gate.widget() is None:
            continue
        gate.apply()
        if not gate.dead:
            alive.append(gate)
    _gates[:] = alive
    apply_tab_limits()
