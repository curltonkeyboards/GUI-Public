# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QLabel

from keycodes.keycodes import Keycode
from util import tr


class KeycodeSearchDialog(QDialog):
    """"Search for a keycode" window opened by double-clicking a key: the same
    searchable browser as the palette's Search tab. Clicking a result picks it
    and closes the window; the pick is in `value`."""

    def __init__(self, keycode_filter=None, parent=None):
        super().__init__(parent)
        # Imported here: tabbed_keycodes imports widgets that import this module.
        from tabbed_keycodes import SearchTab

        self.setWindowTitle(tr("KeycodeSearchDialog", "Search for a keycode"))
        self.keycode_filter = keycode_filter
        self.value = ""

        self.search = SearchTab(self)
        self.search.keycode_changed.connect(self.on_pick)

        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("color: palette(mid);")
        self.lbl_status.hide()

        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.search, 1)
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.buttons)
        self.setLayout(layout)
        self.resize(900, 600)

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
