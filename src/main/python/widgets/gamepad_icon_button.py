# SPDX-License-Identifier: GPL-2.0-or-later
"""Gamepad controls drawn as icons (face buttons, Start/Back, D-pad arrows,
stick directions, bumpers, triggers).

`paint_gamepad_icon()` draws one icon into a square box; the palette button
(`GamepadIconButton`) and the keymap view both use it, so a key assigned a
gamepad control shows the same icon it was picked from."""

import math

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QPainterPath, QFont, QPolygonF

from constants import KEYCODE_BTN_RATIO
from widgets.square_button import SquareButton

BODY = QColor("#5b616e")        # D-pad, stick caps, shoulders
BODY_EDGE = QColor("#454a55")
WELL = QColor("#b9bdc6")        # stick well outline
MARK = QColor("#2f333b")        # stick direction arrows
PANEL = QColor("#3b3f48")       # Start / Back / face button body
WHITE = QColor("#ffffff")

FACE_COLORS = {
    "A": QColor("#34d17a"),
    "B": QColor("#f0585b"),
    "X": QColor("#4c8df6"),
    "Y": QColor("#f2bf2c"),
}

# Degrees (Qt: 0 = 3 o'clock, counter-clockwise) for each direction.
_ANGLE = {"up": 90, "left": 180, "down": 270, "right": 0}

# qmk_id -> (kind, arg)
GAMEPAD_ICONS = {
    "XBOX_A": ("face", "A"), "XBOX_B": ("face", "B"),
    "XBOX_X": ("face", "X"), "XBOX_Y": ("face", "Y"),
    "XBOX_START": ("panel", "START"), "XBOX_BACK": ("panel", "BACK"),
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

# Palette order: face buttons, Start, Back, Gaming Mode (a plain text key),
# D-pad, left stick, right stick, shoulders.
GAMEPAD_ORDER = [
    "XBOX_A", "XBOX_B", "XBOX_X", "XBOX_Y", "XBOX_START", "XBOX_BACK", "GAMING_MODE",
    "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT",
    "LS_UP", "LS_DOWN", "LS_LEFT", "LS_RIGHT", "XBOX_L3",
    "RS_UP", "RS_DOWN", "RS_LEFT", "RS_RIGHT", "XBOX_R3",
    "XBOX_LB", "LT", "XBOX_RB", "RT",
]


def has_gamepad_icon(qmk_id):
    return qmk_id in GAMEPAD_ICONS


def paint_gamepad_icon(qp, box, qmk_id):
    """Draw the icon for `qmk_id` inside the square QRectF `box`."""
    kind, arg = GAMEPAD_ICONS[qmk_id]
    qp.save()
    qp.setRenderHint(QPainter.Antialiasing)
    _PAINTERS[kind](qp, box, arg)
    qp.restore()


# ---- helpers ----------------------------------------------------------------

def _text(qp, rect, text, size_frac, color=WHITE, bold=True):
    font = QFont(qp.font())
    font.setBold(bold)
    font.setPixelSize(max(6, int(rect.height() * size_frac)))
    qp.setFont(font)
    qp.setPen(color)
    qp.drawText(rect, Qt.AlignCenter, text)


def _triangle(center, size, angle_deg):
    """Equilateral-ish triangle pointing at angle_deg, centred on `center`."""
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), -math.sin(a)       # screen y grows down
    px, py = -dy, dx                         # perpendicular
    tip = QPointF(center.x() + dx * size, center.y() + dy * size)
    back = QPointF(center.x() - dx * size * 0.6, center.y() - dy * size * 0.6)
    return QPolygonF([tip,
                      QPointF(back.x() + px * size * 0.85, back.y() + py * size * 0.85),
                      QPointF(back.x() - px * size * 0.85, back.y() - py * size * 0.85)])


# ---- icons ------------------------------------------------------------------

def _paint_face(qp, box, letter):
    # Dark round button with a coloured ring and a coloured letter.
    color = FACE_COLORS[letter]
    ring = max(1.5, box.width() * 0.08)
    r = box.adjusted(ring, ring, -ring, -ring)
    qp.setPen(QPen(color, ring))
    qp.setBrush(PANEL)
    qp.drawEllipse(r)
    _text(qp, r, letter, 0.55, color)


def _paint_panel(qp, box, label):
    # Rounded slate with a small play / back glyph and the word under it.
    h = box.height() * 0.62
    r = QRectF(box.left(), box.center().y() - h / 2, box.width(), h)
    radius = h * 0.28
    qp.setPen(Qt.NoPen)
    qp.setBrush(PANEL)
    qp.drawRoundedRect(r, radius, radius)
    glyph = QPointF(r.center().x(), r.top() + h * 0.33)
    qp.setBrush(WHITE)
    qp.drawPolygon(_triangle(glyph, h * 0.16, 0 if label == "START" else 180))
    _text(qp, QRectF(r.left(), r.top() + h * 0.52, r.width(), h * 0.42), label, 0.72)


def _paint_dpad(qp, box, direction):
    arm = box.width() * 0.34
    radius = 2.0                               # 2px rounded corners
    c = box.center()
    vert = QRectF(c.x() - arm / 2, box.top(), arm, box.height())
    horz = QRectF(box.left(), c.y() - arm / 2, box.width(), arm)
    path = QPainterPath()
    path.setFillRule(Qt.WindingFill)
    path.addRoundedRect(vert, radius, radius)
    path.addRoundedRect(horz, radius, radius)
    qp.setPen(QPen(BODY_EDGE, max(1.0, box.width() * 0.02)))
    qp.setBrush(BODY)
    qp.drawPath(path.simplified())
    # the pressed arm: a lighter pad with a white arrow in it
    half = (box.width() - arm) / 2
    arm_rect = {
        "up": QRectF(vert.left(), vert.top(), arm, half),
        "down": QRectF(vert.left(), vert.bottom() - half, arm, half),
        "left": QRectF(horz.left(), horz.top(), half, arm),
        "right": QRectF(horz.right() - half, horz.top(), half, arm),
    }[direction]
    pad = arm_rect.adjusted(arm * 0.1, arm * 0.1, -arm * 0.1, -arm * 0.1)
    qp.setPen(Qt.NoPen)
    qp.setBrush(BODY.lighter(135))
    qp.drawRoundedRect(pad, radius, radius)
    qp.setBrush(WHITE)
    qp.drawPolygon(_triangle(pad.center(), arm * 0.26, _ANGLE[direction]))


def _paint_stick(qp, box, arg):
    letter, direction = arg
    c = box.center()
    well_r = box.width() * 0.47
    cap_r = box.width() * 0.27
    qp.setPen(QPen(WELL, max(1.0, box.width() * 0.035)))
    qp.setBrush(Qt.NoBrush)
    qp.drawEllipse(c, well_r, well_r)
    cap = QRectF(c.x() - cap_r, c.y() - cap_r, cap_r * 2, cap_r * 2)
    qp.setPen(QPen(BODY_EDGE, max(1.0, box.width() * 0.02)))
    qp.setBrush(BODY)
    qp.drawEllipse(cap)
    _text(qp, cap, letter, 0.62)
    # small arrow(s) between the cap and the well
    qp.setPen(Qt.NoPen)
    qp.setBrush(MARK)
    mid = (cap_r + well_r) / 2
    size = box.width() * 0.075
    if direction == "click":
        # press: arrows on all four sides pointing in at the cap
        for ang in (90, 180, 270, 0):
            a = math.radians(ang)
            p = QPointF(c.x() + math.cos(a) * mid, c.y() - math.sin(a) * mid)
            qp.drawPolygon(_triangle(p, size, ang + 180))
    else:
        a = math.radians(_ANGLE[direction])
        p = QPointF(c.x() + math.cos(a) * mid, c.y() - math.sin(a) * mid)
        qp.drawPolygon(_triangle(p, size * 1.25, _ANGLE[direction]))


def _paint_shoulder(qp, box, arg):
    text, side, trigger = arg
    if trigger:
        # trigger: tall rounded tab, deeper on the outer side
        h = box.height() * 0.84
        r = QRectF(box.left() + box.width() * 0.08, box.bottom() - h, box.width() * 0.84, h)
        big = r.width() * 0.45
        small = r.width() * 0.12
    else:
        # bumper: wide low bar
        h = box.height() * 0.46
        r = QRectF(box.left(), box.center().y() - h / 2, box.width(), h)
        big = h * 0.7
        small = h * 0.2
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
    qp.setPen(QPen(BODY_EDGE, max(1.0, box.width() * 0.02)))
    qp.setBrush(BODY)
    qp.drawPath(path)
    _text(qp, r, text, 0.36 if trigger else 0.5)


_PAINTERS = {
    "face": _paint_face,
    "panel": _paint_panel,
    "dpad": _paint_dpad,
    "stick": _paint_stick,
    "shoulder": _paint_shoulder,
}


class GamepadIconButton(SquareButton):
    """Palette button showing a gamepad control as its icon. It is a
    SquareButton, so it has the palette key's size, frame, hover/pressed
    styling, click and drag-to-assign behaviour."""

    def __init__(self, qmk_id, parent=None):
        super().__init__(parent)
        self.setRelSize(KEYCODE_BTN_RATIO)
        self.icon_qmk_id = qmk_id

    def paintEvent(self, ev):
        super().paintEvent(ev)
        qp = QPainter(self)
        side = min(self.width(), self.height())
        s = side * 0.74
        box = QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s)
        paint_gamepad_icon(qp, box, self.icon_qmk_id)
        qp.end()
