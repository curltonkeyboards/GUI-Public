# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QLabel, QApplication

from keycodes.keycodes import Keycode
from util import tr


def top_window(widget):
    """The real window `widget` is shown in. The Keymap page's keyboard sits
    inside a zoomable graphics view, where it belongs to a hidden top-level of
    its own: a dialog or menu given that as its parent would be drawn inside
    the view (squeezed into the keyboard's area, and scaled by its zoom)."""
    window = widget.window() if widget is not None else None
    for _ in range(4):
        proxy = window.graphicsProxyWidget() if window is not None else None
        if proxy is None or proxy.scene() is None or not proxy.scene().views():
            break
        window = proxy.scene().views()[0].window()
    return window if window is not None else QApplication.activeWindow()


class KeycodeSearchDialog(QDialog):
    """"Search for a keycode" window opened by double-clicking a key: the same
    searchable browser as the palette's Search tab. Clicking a result picks it
    and closes the window; the pick is in `value`."""

    def __init__(self, keycode_filter=None, parent=None):
        # a window of its own over the app, never inside the Keymap's zoom view
        super().__init__(top_window(parent) if parent is not None else None)
        # Imported here: tabbed_keycodes imports widgets that import this module.
        from tabbed_keycodes import SearchTab

        self.setWindowTitle(tr("KeycodeSearchDialog", "Search for a keycode"))
        self.keycode_filter = keycode_filter
        self.value = ""

        self.search = SearchTab(self)
        self.search.keycode_changed.connect(self.on_pick)

        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("color: palette(dark);")
        self.lbl_status.hide()

        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.search, 1)
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.buttons)
        self.setLayout(layout)
        self.resize(900, 600)

        # No hover pop-ups (e.g. "KC_T") over the results in this window.
        QApplication.instance().installEventFilter(self)

        bar = getattr(self.search, "adv_search_bar", None)
        if bar is not None:
            bar.setFocus(Qt.OtherFocusReason)

    def on_pick(self, code):
        try:
            code = Keycode.normalize(code)
        except Exception:
            return
        if self.keycode_filter is not None and not self.keycode_filter(code):
            self.lbl_status.setText(tr("KeycodeSearchDialog",
                                       "That keycode can't be used here - pick a basic key."))
            self.lbl_status.show()
            return
        self.value = code
        self.accept()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ToolTip and hasattr(obj, "window") and obj.window() is self:
            return True
        return super().eventFilter(obj, event)

    def done(self, result):
        QApplication.instance().removeEventFilter(self)
        super().done(result)
