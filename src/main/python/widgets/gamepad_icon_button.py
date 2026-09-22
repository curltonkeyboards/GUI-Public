# SPDX-License-Identifier: GPL-2.0-or-later
"""Palette button that shows a gamepad control as a drawn icon (face buttons,
Start/Back, D-pad arrows, stick directions, bumpers, triggers) instead of a
text label.  It is a SquareButton, so it has the palette key's size, frame,
hover/pressed styling, click and drag-to-assign behaviour; the icon is painted
on top of that frame."""

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QPainterPath, QFont, QPolygonF

from constants import KEYCODE_BTN_RATIO
from widgets.square_button import SquareButton

GREY = QColor("#7d828c")
GREY_LIGHT = QColor("#c9ccd2")
PILL = QColor("#e6e8eb")
PILL_MARK = QColor("#8a8f98")
ACCENT = QColor("#fcd34d")
WHITE = QColor("#ffffff")

FACE_COLORS = {
    "A": QColor("#22c55e"),
    "B": QColor("#ef4444"),
    "X": QColor("#3b82f6"),
    "Y": QColor("#eab308"),
}

# Degrees (Qt: 0 = 3 o'clock, counter-clockwise) of the arc lit for each
# stick direction.
_STICK_ANGLE = {"up": 90, "left": 180, "down": 270, "right": 0}

# qmk_id -> (kind, arg)
GAMEPAD_ICONS = {
    "XBOX_A": ("face", "A"), "XBOX_B": ("face", "B"),
    "XBOX_X": ("face", "X"), "XBOX_Y": ("face", "Y"),
    "XBOX_START": ("pill", "right"), "XBOX_BACK": ("pill", "left"),
    "GAMING_MODE": ("mode", None),
    "DPAD_UP": ("dpad", "up"), "DPAD_DOWN": ("dpad", "down"),
    "DPAD_LEFT": ("dpad", "left"), "DPAD_RIGHT": ("dpad", "right"),
    "LS_UP": ("stick", ("L", "up")), "LS_DOWN": ("stick", ("L", "down")),
    "LS_LEFT": ("stick", ("L", "left")), "LS_RIGHT": ("stick", ("L", "right")),
    "XBOX_L3": ("stick", ("L", "click")),
    "RS_UP": ("stick", ("R", "up")), "RS_DOWN": ("stick", ("R", "down")),
    "RS_LEFT": ("stick", ("R", "left")), "RS_RIGHT": ("stick", ("R", "right")),
    "XBOX_R3": ("stick", ("R", "click")),
    "XBOX_LB": ("shoulder", ("LB", "left", False)), "LT": ("shoulder", ("LT", "left", True)),
    "XBOX_RB": ("shoulder", ("RB", "right", False)), "RT": ("shoulder", ("RT", "right", True)),
}

# Palette order (matches the reference sheet): face buttons, Start, Back,
# Gaming Mode, D-pad, left stick, right stick, shoulders.
GAMEPAD_ORDER = [
    "XBOX_A", "XBOX_B", "XBOX_X", "XBOX_Y", "XBOX_START", "XBOX_BACK", "GAMING_MODE",
    "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT",
    "LS_UP", "LS_DOWN", "LS_LEFT", "LS_RIGHT", "XBOX_L3",
    "RS_UP", "RS_DOWN", "RS_LEFT", "RS_RIGHT", "XBOX_R3",
    "XBOX_LB", "LT", "XBOX_RB", "RT",
]


class GamepadIconButton(SquareButton):

    def __init__(self, qmk_id, parent=None):
        super().__init__(parent)
        self.setRelSize(KEYCODE_BTN_RATIO)
        self.icon_kind, self.icon_arg = GAMEPAD_ICONS[qmk_id]

    def paintEvent(self, ev):
        super().paintEvent(ev)
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        # icon box: centred square, 76% of the button
        s = side * 0.76
        box = QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s)
        getattr(self, "_draw_" + self.icon_kind)(qp, box, self.icon_arg)
        qp.end()

    # ---- helpers ------------------------------------------------------

    @staticmethod
    def _text(qp, rect, text, size_frac, color=WHITE):
        font = QFont(qp.font())
        font.setBold(True)
        font.setPixelSize(max(6, int(rect.height() * size_frac)))
        qp.setFont(font)
        qp.setPen(color)
        qp.drawText(rect, Qt.AlignCenter, text)

    # ---- icons --------------------------------------------------------

    def _draw_face(self, qp, box, letter):
        color = FACE_COLORS[letter]
        qp.setPen(QPen(color.darker(125), max(1.0, box.width() * 0.05)))
        qp.setBrush(color)
        r = box.adjusted(box.width() * 0.04, box.height() * 0.04, -box.width() * 0.04, -box.height() * 0.04)
        qp.drawEllipse(r)
        self._text(qp, r, letter, 0.5)

    def _draw_pill(self, qp, box, direction):
        h = box.height() * 0.46
        r = QRectF(box.left(), box.center().y() - h / 2, box.width(), h)
        qp.setPen(QPen(GREY_LIGHT, max(1.0, h * 0.05)))   # keeps it visible on light themes
        qp.setBrush(PILL)
        qp.drawRoundedRect(r, h * 0.22, h * 0.22)
        t = h * 0.5
        c = r.center()
        if direction == "right":
            tri = [QPointF(c.x() - t * 0.4, c.y() - t / 2), QPointF(c.x() + t * 0.5, c.y()),
                   QPointF(c.x() - t * 0.4, c.y() + t / 2)]
        else:
            tri = [QPointF(c.x() + t * 0.4, c.y() - t / 2), QPointF(c.x() - t * 0.5, c.y()),
                   QPointF(c.x() + t * 0.4, c.y() + t / 2)]
        qp.setPen(QPen(PILL_MARK, max(1.0, h * 0.07)))
        qp.setBrush(Qt.NoBrush)
        qp.drawPolygon(QPolygonF(tri))

    def _draw_mode(self, qp, box, _arg):
        w = box.width() * 0.08
        r = box.adjusted(w, w, -w, -w)
        qp.setPen(QPen(ACCENT, w))
        qp.setBrush(GREY)
        qp.drawEllipse(r)
        # X across the circle, inset so it stays inside the ring
        k = r.width() * 0.5 * 0.707
        c = r.center()
        qp.drawLine(QPointF(c.x() - k, c.y() - k), QPointF(c.x() + k, c.y() + k))
        qp.drawLine(QPointF(c.x() - k, c.y() + k), QPointF(c.x() + k, c.y() - k))

    def _draw_dpad(self, qp, box, direction):
        arm = box.width() * 0.32
        c = box.center()
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)   # the arms overlap in the centre
        path.addRect(QRectF(c.x() - arm / 2, box.top(), arm, box.height()))
        path.addRect(QRectF(box.left(), c.y() - arm / 2, box.width(), arm))
        qp.setPen(Qt.NoPen)
        qp.setBrush(GREY)
        qp.drawPath(path.simplified())
        # white arrowhead at the end of the arm for this direction
        t = arm * 0.32
        e = box.width() * 0.5 - t * 1.4   # distance from centre to the arrow
        if direction == "up":
            p = QPointF(c.x(), c.y() - e)
            tri = [QPointF(p.x(), p.y() - t), QPointF(p.x() + t, p.y() + t * 0.6), QPointF(p.x() - t, p.y() + t * 0.6)]
        elif direction == "down":
            p = QPointF(c.x(), c.y() + e)
            tri = [QPointF(p.x(), p.y() + t), QPointF(p.x() + t, p.y() - t * 0.6), QPointF(p.x() - t, p.y() - t * 0.6)]
        elif direction == "left":
            p = QPointF(c.x() - e, c.y())
            tri = [QPointF(p.x() - t, p.y()), QPointF(p.x() + t * 0.6, p.y() - t), QPointF(p.x() + t * 0.6, p.y() + t)]
        else:
            p = QPointF(c.x() + e, c.y())
            tri = [QPointF(p.x() + t, p.y()), QPointF(p.x() - t * 0.6, p.y() - t), QPointF(p.x() - t * 0.6, p.y() + t)]
        qp.setBrush(WHITE)
        qp.drawPolygon(QPolygonF(tri))

    def _draw_stick(self, qp, box, arg):
        letter, direction = arg
        ring_w = box.width() * 0.09
        outer = box.adjusted(ring_w / 2, ring_w / 2, -ring_w / 2, -ring_w / 2)
        # thin outline of the stick well
        qp.setPen(QPen(GREY_LIGHT, max(1.0, box.width() * 0.025)))
        qp.setBrush(Qt.NoBrush)
        qp.drawEllipse(outer)
        # lit direction (a quarter arc) or the whole ring for the stick click
        pen = QPen(ACCENT, ring_w)
        pen.setCapStyle(Qt.RoundCap)
        qp.setPen(pen)
        if direction == "click":
            qp.drawEllipse(outer)
        else:
            start = _STICK_ANGLE[direction] - 40
            qp.drawArc(outer, int(start * 16), int(80 * 16))
        # stick cap
        cap = box.width() * 0.17
        inner = box.adjusted(cap, cap, -cap, -cap)
        qp.setPen(Qt.NoPen)
        qp.setBrush(GREY)
        qp.drawEllipse(inner)
        self._text(qp, inner, letter, 0.6)

    def _draw_shoulder(self, qp, box, arg):
        text, side, trigger = arg
        h = box.height() * (0.82 if trigger else 0.6)
        r = QRectF(box.left(), box.bottom() - h, box.width(), h)
        big = min(r.width(), r.height()) * (0.7 if trigger else 0.55)
        small = r.height() * 0.12
        # rounded rectangle with one large rounded top corner (outer side)
        tl = big if side == "left" else small
        tr = big if side == "right" else small
        path = QPainterPath()
        path.moveTo(r.left() + tl, r.top())
        path.lineTo(r.right() - tr, r.top())
        path.quadTo(r.right(), r.top(), r.right(), r.top() + tr)
        path.lineTo(r.right(), r.bottom() - small)
        path.quadTo(r.right(), r.bottom(), r.right() - small, r.bottom())
        path.lineTo(r.left() + small, r.bottom())
        path.quadTo(r.left(), r.bottom(), r.left(), r.bottom() - small)
        path.lineTo(r.left(), r.top() + tl)
        path.quadTo(r.left(), r.top(), r.left() + tl, r.top())
        qp.setPen(Qt.NoPen)
        qp.setBrush(GREY)
        qp.drawPath(path)
        self._text(qp, r, text, 0.42 if trigger else 0.5)
