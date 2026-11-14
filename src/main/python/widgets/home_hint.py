# SPDX-License-Identifier: GPL-2.0-or-later
"""Basic mode's way back to the home screen.

HomeButton: the big "Home" button (with a house icon) at the top middle of a
page opened from the home screen.

HomeHint: shown once, the first time a page is opened from the home screen.
Everything else is blurred and dimmed, the Home button is ringed in red, and
an arrow points to it: "Press this to go back to the main menu". A click on
the button goes home; a click anywhere else (or Esc) just closes the hint.
"""

import math

from PyQt5.QtCore import Qt, QEvent, QPointF, QRectF, QSize, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PyQt5.QtWidgets import QApplication, QGraphicsBlurEffect, QPushButton, QWidget

from util import tr

RED = QColor(220, 38, 38)


def house_icon(color, size=24):
    """A house: pitched roof, walls and a door, drawn in `color`."""
    ratio = 2
    pix = QPixmap(size * ratio, size * ratio)
    pix.setDevicePixelRatio(ratio)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    s = float(size)
    pen = QPen(color, s * 0.09)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    roof = QPolygonF([QPointF(s * 0.10, s * 0.50), QPointF(s * 0.50, s * 0.14), QPointF(s * 0.90, s * 0.50)])
    p.drawPolyline(roof)
    walls = QPainterPath()
    walls.moveTo(s * 0.22, s * 0.42)
    walls.lineTo(s * 0.22, s * 0.86)
    walls.lineTo(s * 0.78, s * 0.86)
    walls.lineTo(s * 0.78, s * 0.42)
    p.drawPath(walls)
    p.setBrush(color)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(s * 0.42, s * 0.60, s * 0.16, s * 0.26), s * 0.03, s * 0.03)
    p.end()
    return QIcon(pix)


class HomeButton(QPushButton):
    """The big Home button. Its icon follows the theme's text colour."""

    ICON = 24

    def __init__(self, parent=None):
        super().__init__(tr("MainWindow", "Home"), parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(150, 42)
        font = QFont(self.font())
        font.setPointSizeF(12)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet("QPushButton { font-size: 12pt; font-weight: bold; padding: 6px 22px; }")
        self.setIconSize(QSize(self.ICON, self.ICON))
        self._paint_icon()

    def _paint_icon(self):
        self.setIcon(house_icon(self.palette().color(self.foregroundRole()), self.ICON))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.StyleChange):
            self._paint_icon()


def cross_icon(color, size=18):
    """An X, drawn in `color`."""
    ratio = 2
    pix = QPixmap(size * ratio, size * ratio)
    pix.setDevicePixelRatio(ratio)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    s = float(size)
    pen = QPen(color, s * 0.13)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.22, s * 0.22), QPointF(s * 0.78, s * 0.78))
    p.drawLine(QPointF(s * 0.78, s * 0.22), QPointF(s * 0.22, s * 0.78))
    p.end()
    return QIcon(pix)


class CloseButton(QPushButton):
    """The X at the top right of a page opened from the home screen: back to
    the home screen, like the Home button. Its icon follows the theme."""

    ICON = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(38, 38)
        self.setToolTip(tr("MainWindow", "Close this page and go back to the main menu"))
        self.setStyleSheet("QPushButton { padding: 0px; }")
        self.setIconSize(QSize(self.ICON, self.ICON))
        self._paint_icon()

    def _paint_icon(self):
        self.setIcon(cross_icon(self.palette().color(self.foregroundRole()), self.ICON))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.StyleChange):
            self._paint_icon()


class HomeHint(QWidget):
    """The one-time pointer to the Home button (see the module notes).

    `cover`: the widget it lies over (the window's central widget);
    `target`: the Home button; `blur`: the widgets to blur meanwhile."""

    closed = pyqtSignal()

    def __init__(self, cover, target, blur):
        super().__init__(cover)
        self.target = target
        self._blurred = []
        for widget in blur:
            if widget is not None and widget.graphicsEffect() is None:
                effect = QGraphicsBlurEffect(widget)
                effect.setBlurRadius(9)
                widget.setGraphicsEffect(effect)
                self._blurred.append(widget)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        cover.installEventFilter(self)
        self.setGeometry(cover.rect())
        self.show()
        self.raise_()
        self.setFocus()

    # ---- where things go ------------------------------------------------------

    def _ring(self):
        """The red circle around the Home button, in this widget's coordinates."""
        r = QRectF(self.target.rect())
        top_left = QPointF(self.target.mapTo(self.parentWidget(), r.topLeft().toPoint()))
        r.moveTopLeft(top_left)
        pad = 14
        return r.adjusted(-pad, -pad * 0.8, pad, pad * 0.8)

    def _text_box(self, ring):
        font = self._text_font()
        from PyQt5.QtGui import QFontMetrics
        fm = QFontMetrics(font)
        text = self._text()
        w = fm.horizontalAdvance(text) + 40
        h = fm.height() + 26
        # below the ring and to the right, with room for the arrow
        x = min(max(ring.center().x() + 70, 12), self.width() - w - 12)
        y = min(ring.bottom() + 90, self.height() - h - 12)
        return QRectF(x, y, w, h)

    def _text(self):
        return tr("MainWindow", "Press this to go back to the main menu")

    def _text_font(self):
        font = QFont(self.font())
        font.setPointSizeF(13)
        font.setBold(True)
        return font

    # ---- drawing ------------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        ring = self._ring()

        # dim everything but the Home button
        shade = QPainterPath()
        shade.addRect(QRectF(self.rect()))
        hole = QPainterPath()
        hole.addEllipse(ring)
        p.fillPath(shade.subtracted(hole), QColor(0, 0, 0, 120))

        # the red ring
        p.setPen(QPen(RED, 4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(ring)

        # the words, in a box
        box = self._text_box(ring)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 245))
        p.drawRoundedRect(box, 10, 10)
        p.setPen(QPen(RED, 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(box, 10, 10)
        p.setFont(self._text_font())
        p.setPen(QColor(30, 30, 30))
        p.drawText(box, Qt.AlignCenter, self._text())

        # the arrow: from the box up to the ring's edge
        start = QPointF(box.left() + 28, box.top())
        centre = ring.center()
        # the point on the ellipse facing the start
        angle = math.atan2(start.y() - centre.y(), start.x() - centre.x())
        end = QPointF(centre.x() + (ring.width() / 2 + 6) * math.cos(angle),
                      centre.y() + (ring.height() / 2 + 6) * math.sin(angle))
        bend = QPointF(start.x(), (start.y() + end.y()) / 2)
        path = QPainterPath(start)
        path.quadTo(bend, end)
        pen = QPen(RED, 4)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawPath(path)
        # arrow head, along the curve's last direction
        d = end - bend
        length = math.hypot(d.x(), d.y()) or 1.0
        ux, uy = d.x() / length, d.y() / length
        head = 16
        left = QPointF(end.x() - head * ux + head * 0.55 * uy, end.y() - head * uy - head * 0.55 * ux)
        right = QPointF(end.x() - head * ux - head * 0.55 * uy, end.y() - head * uy + head * 0.55 * ux)
        p.setPen(Qt.NoPen)
        p.setBrush(RED)
        p.drawPolygon(QPolygonF([end, left, right]))

    # ---- closing ------------------------------------------------------------------

    def mousePressEvent(self, event):
        go_home = self._ring().contains(QPointF(event.pos()))
        self.finish()
        if go_home:
            self.target.click()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.finish()
        else:
            super().keyPressEvent(event)

    def finish(self):
        for widget in self._blurred:
            try:
                widget.setGraphicsEffect(None)
            except RuntimeError:
                pass
        self._blurred = []
        self.closed.emit()
        self.close()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == QEvent.Resize:
            self.setGeometry(obj.rect())
        return False
