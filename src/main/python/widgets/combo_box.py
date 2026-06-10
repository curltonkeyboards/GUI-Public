# SPDX-License-Identifier: GPL-2.0-or-later

from PyQt5.QtWidgets import QComboBox, QStyleOptionComboBox, QSpinBox, QStyleOptionSpinBox
from PyQt5.QtGui import QPalette, QPainter, QPolygon, QBrush
from PyQt5.QtCore import Qt, QPoint, QEvent, QObject


class LineEditEventFilter(QObject):
    """Event filter to make lineEdit in combobox open the dropdown when clicked"""

    def __init__(self, combobox):
        super().__init__()
        self.combobox = combobox

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self.combobox.showPopup()
            return True
        return super().eventFilter(obj, event)


class ArrowComboBox(QComboBox):
    """
    QComboBox with programmatically drawn dropdown arrow.
    Fixes issues where CSS border triangles don't render properly on some systems.
    Also allows clicking anywhere on the combobox to open the dropdown.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.line_edit_filter = None

    def setEditable(self, editable):
        """Override setEditable to install event filter on lineEdit"""
        super().setEditable(editable)
        if editable and self.lineEdit():
            self.line_edit_filter = LineEditEventFilter(self)
            self.lineEdit().installEventFilter(self.line_edit_filter)

    def paintEvent(self, event):
        # Draw the standard combobox
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)

        painter = QPainter(self)
        self.style().drawComplexControl(self.style().CC_ComboBox, opt, painter, self)
        self.style().drawControl(self.style().CE_ComboBoxLabel, opt, painter, self)

        # Draw dropdown arrow manually
        arrow_rect = self.style().subControlRect(self.style().CC_ComboBox, opt, self.style().SC_ComboBoxArrow, self)
        arrow_center_x = arrow_rect.center().x()
        arrow_center_y = arrow_rect.center().y()

        # Create triangle pointing down
        arrow_size = 4
        arrow = QPolygon([
            QPoint(arrow_center_x - arrow_size, arrow_center_y - 2),
            QPoint(arrow_center_x + arrow_size, arrow_center_y - 2),
            QPoint(arrow_center_x, arrow_center_y + 3)
        ])

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.palette().color(QPalette.Text)))
        painter.drawPolygon(arrow)

    def mousePressEvent(self, event):
        """Make the entire combobox clickable to open the dropdown"""
        if event.button() == Qt.LeftButton:
            self.showPopup()
        else:
            super().mousePressEvent(event)


class ArrowSpinBox(QSpinBox):
    """
    QSpinBox with programmatically drawn up/down arrows.
    Mirrors ArrowComboBox approach to fix CSS arrow rendering issues.
    """

    def paintEvent(self, event):
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)

        painter = QPainter(self)
        # Draw the full spinbox (frame, text, buttons)
        self.style().drawComplexControl(self.style().CC_SpinBox, opt, painter, self)

        color = self.palette().color(QPalette.Text)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))

        arrow_size = 3

        # Draw up arrow
        up_rect = self.style().subControlRect(
            self.style().CC_SpinBox, opt, self.style().SC_SpinBoxUp, self)
        cx, cy = up_rect.center().x(), up_rect.center().y()
        painter.drawPolygon(QPolygon([
            QPoint(cx - arrow_size, cy + 2),
            QPoint(cx + arrow_size, cy + 2),
            QPoint(cx, cy - 2)
        ]))

        # Draw down arrow
        dn_rect = self.style().subControlRect(
            self.style().CC_SpinBox, opt, self.style().SC_SpinBoxDown, self)
        cx, cy = dn_rect.center().x(), dn_rect.center().y()
        painter.drawPolygon(QPolygon([
            QPoint(cx - arrow_size, cy - 2),
            QPoint(cx + arrow_size, cy - 2),
            QPoint(cx, cy + 2)
        ]))
