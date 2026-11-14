# SPDX-License-Identifier: GPL-2.0-or-later
"""An engraved "Loading..." over a page while it is being built.

Some pages are only built the first time they are opened, and building one
keeps the app busy for a moment. Without a sign the window just looks stuck,
so the first opening of a page is done under this cover:

    cover = begin_loading(area, page)     # put the cover up (None if not needed)
    ...open the page...
    end_loading(cover)                    # lift it once the app is free again

`area` is the widget to cover, `page` whatever identifies the page (its
widget): a page that has been opened once opens without the cover from then on.
"""

from PyQt5 import sip
from PyQt5.QtCore import Qt, QEventLoop, QRect, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import QApplication, QWidget

from util import tr

_opened = set()
_putting_up = 0


def putting_up():
    """True while a cover is being got onto the screen. That lets waiting
    events run in the middle of a click on a tab or tile, so anything that
    would rebuild the pages (a keyboard being plugged in or unplugged) must
    wait until this is False again: see MainWindow.on_devices_updated."""
    return _putting_up > 0


class LoadingOverlay(QWidget):

    def __init__(self, area, top=0):
        super().__init__(area)
        self.setGeometry(0, top, area.width(), max(0, area.height() - top))
        self.setAttribute(Qt.WA_DeleteOnClose)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.fillRect(self.rect(), self.palette().window())

        font = QFont(self.font())
        font.setPointSizeF(20)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        painter.setFont(font)
        text = tr("Loading", "Loading...")
        area = self.rect()
        # Engraved, like the side tabs: a lit edge below the letters, a shaded
        # one above, the letters a little sunk into the surface colour.
        ink = QColor(self.palette().windowText().color())
        shade = QColor(ink)
        shade.setAlpha(60)
        ink.setAlpha(120)
        painter.setPen(QColor(255, 255, 255, 200))
        painter.drawText(QRect(area).translated(0, 1), Qt.AlignCenter, text)
        painter.setPen(shade)
        painter.drawText(QRect(area).translated(0, -1), Qt.AlignCenter, text)
        painter.setPen(ink)
        painter.drawText(area, Qt.AlignCenter, text)


def begin_loading(area, page, top=0):
    """Cover `area` now if `page` has not been opened before. Returns the
    cover (for end_loading) or None."""
    key = page if isinstance(page, tuple) else id(page)
    if key in _opened or area is None or not area.isVisible():
        return None
    _opened.add(key)
    overlay = LoadingOverlay(area, top)
    overlay.show()
    overlay.raise_()
    overlay.repaint()
    # get it onto the screen before the busy part starts (not letting clicks in)
    global _putting_up
    _putting_up += 1
    try:
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
    finally:
        _putting_up -= 1
    # in case nobody lifts it (the opening was abandoned)
    QTimer.singleShot(8000, lambda: end_loading(overlay))
    return overlay


def end_loading(overlay):
    """Lift a cover from begin_loading, as soon as the app is free. Building
    a page may itself let events through for a while, so the cover is only
    lifted from here, after the building, never on a timer started before it."""
    if overlay is None:
        return
    QTimer.singleShot(0, lambda: _close(overlay))


def _close(overlay):
    # The cover deletes itself when closed, and this can be reached twice (the
    # normal lift, then the 8 second fallback), so check it is still there:
    # touching a deleted widget raises, which showed up as an error box.
    try:
        if not sip.isdeleted(overlay):
            overlay.close()
    except RuntimeError:
        pass
