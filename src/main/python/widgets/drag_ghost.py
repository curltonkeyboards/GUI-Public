# SPDX-License-Identifier: GPL-2.0-or-later
"""Makes a drag look like the button itself is being carried.

Qt's own drag picture on Windows is drawn by the system's drag-and-drop loop: it trails the mouse
and is see-through. Here the picture of the button is shown in a small window of our own that is
moved to the mouse many times a second, so it stays under the cursor. The window lets the mouse
through, so the drop still lands on whatever is underneath.

    run_drag(drag, source_widget, hot_spot, Qt.MoveAction)

is used in place of  drag.setPixmap(...); drag.setHotSpot(...); drag.exec_(...).
"""
import sys

from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QCursor, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel

# How far the mouse moves with the button held before a drag begins. Qt's default (10 pixels on
# Windows) makes a drag feel slow to start.
START_DISTANCE = 4


def drag_start_distance():
    return min(START_DISTANCE, QApplication.startDragDistance())


class _Ghost(QLabel):
    """The picture of the button, following the mouse."""

    def __init__(self, pixmap, hot_spot):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent; border: none;")
        self.setPixmap(pixmap)
        self.resize(int(pixmap.width() / pixmap.devicePixelRatio()), int(pixmap.height() / pixmap.devicePixelRatio()))
        self._hot_spot = hot_spot
        self._timer = QTimer(self)
        self._timer.setInterval(6)          # well above the screen's refresh rate
        self._timer.timeout.connect(self.follow)
        self.follow()

    def follow(self):
        self.move(QCursor.pos() - self._hot_spot)

    def start(self):
        self.show()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()
        self.deleteLater()


def run_drag(drag, source, hot_spot, action):
    """Runs the drag with a picture of `source` carried under the mouse. Returns what exec_() returns."""
    pixmap = source.grab()
    hot_spot = hot_spot if hot_spot is not None else QPoint(pixmap.width() // 2, pixmap.height() // 2)

    if sys.platform != "win32":
        # elsewhere Qt's own drag picture keeps up with the mouse
        drag.setPixmap(pixmap)
        drag.setHotSpot(hot_spot)
        return drag.exec_(action)

    # no picture from Qt: ours takes its place
    blank = QPixmap(1, 1)
    blank.fill(Qt.transparent)
    drag.setPixmap(blank)

    ghost = _Ghost(pixmap, hot_spot)
    ghost.start()
    try:
        return drag.exec_(action)
    finally:
        ghost.stop()
