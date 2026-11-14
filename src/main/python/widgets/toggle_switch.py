# SPDX-License-Identifier: GPL-2.0-or-later
"""A sliding on/off switch with its label and an ON / OFF word beside it."""

from PyQt5.QtCore import Qt, QRectF, QSize, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtWidgets import QAbstractButton, QSizePolicy


class ToggleSwitch(QAbstractButton):

    switched = pyqtSignal(bool)     # the user flipped it (not sent by set_on)

    TRACK_WIDTH = 44
    TRACK_HEIGHT = 22

    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.label = label
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.clicked.connect(lambda checked: self.switched.emit(checked))

    def set_on(self, on):
        self.setChecked(bool(on))
        self.update()

    def _fonts(self):
        label_font = QFont(self.font())
        label_font.setBold(True)
        state_font = QFont(self.font())
        state_font.setBold(True)
        return label_font, state_font

    def sizeHint(self):
        metrics = self.fontMetrics()
        width = metrics.horizontalAdvance(self.label) + 30 + self.TRACK_WIDTH + 10 + metrics.horizontalAdvance("OFF") + 16
        return QSize(width, max(self.TRACK_HEIGHT + 8, metrics.height() + 8))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        on = self.isChecked()
        label_font, state_font = self._fonts()

        p.setFont(label_font)
        p.setPen(palette.windowText().color())
        label_width = p.fontMetrics().horizontalAdvance(self.label)
        p.drawText(QRectF(4, 0, label_width + 8, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.label)

        x = 4 + label_width + 14
        y = (self.height() - self.TRACK_HEIGHT) / 2
        track = QRectF(x, y, self.TRACK_WIDTH, self.TRACK_HEIGHT)
        track_colour = QColor(palette.highlight().color() if on else palette.mid().color())
        if self.underMouse():
            track_colour = track_colour.lighter(108)
        p.setPen(Qt.NoPen)
        p.setBrush(track_colour)
        p.drawRoundedRect(track, self.TRACK_HEIGHT / 2, self.TRACK_HEIGHT / 2)

        knob = self.TRACK_HEIGHT - 6
        knob_x = track.right() - knob - 3 if on else track.left() + 3
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QRectF(knob_x, y + 3, knob, knob))

        p.setFont(state_font)
        p.setPen(palette.highlight().color() if on else palette.dark().color())
        p.drawText(QRectF(track.right() + 10, 0, 60, self.height()), Qt.AlignVCenter | Qt.AlignLeft, "ON" if on else "OFF")
