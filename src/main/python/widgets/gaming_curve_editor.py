# SPDX-License-Identifier: GPL-2.0-or-later

"""
Gaming Analog Curve Editor Widget
A dropdown-selectable curve editor with individual curves for Left Stick,
Right Stick, Left Trigger, and Right Trigger. No presets - just direct
4-point editing. Curves are persisted when "Save Configuration" is clicked.
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel
from PyQt5.QtCore import Qt, QPointF, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor


# Linear default: 4 points on a straight diagonal
LINEAR_CURVE = [[0, 0], [85, 85], [170, 170], [255, 255]]


class GamingCurveCanvas(QWidget):
    """Canvas widget for drawing and interacting with a single 4-point curve."""

    point_moved = pyqtSignal()  # Emitted when any point changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = [list(p) for p in LINEAR_CURVE]
        self.canvas_size = 260
        self.margin = 20
        self.grid_divisions = 10
        self.dragging_point = -1
        self.hover_point = -1
        self.point_radius = 6

        self.setFixedSize(self.canvas_size, self.canvas_size)
        self.setMouseTracking(True)

    def set_points(self, points):
        if len(points) == 4:
            self.points = self._validate_points(points)
            self.update()

    def get_points(self):
        return [list(p) for p in self.points]

    def _validate_points(self, points):
        validated = [list(p) for p in points]
        for p in validated:
            p[0] = max(0, min(255, p[0]))
            p[1] = max(0, min(255, p[1]))
        validated[0][0] = 0
        validated[3][0] = 255
        validated[1][0] = max(1, min(validated[2][0] - 1, validated[1][0]))
        validated[2][0] = max(validated[1][0] + 1, min(254, validated[2][0]))
        validated[1][0] = max(1, min(validated[2][0] - 1, validated[1][0]))
        return validated

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(30, 30, 30))
        self._draw_grid(painter)
        self._draw_curve(painter)
        self._draw_points(painter)

    def _draw_grid(self, painter):
        pen = QPen(QColor(50, 50, 50))
        painter.setPen(pen)
        draw_area = self.canvas_size - 2 * self.margin
        step = draw_area // self.grid_divisions
        for i in range(self.grid_divisions + 1):
            x = self.margin + i * step
            painter.drawLine(x, self.margin, x, self.canvas_size - self.margin)
        for i in range(self.grid_divisions + 1):
            y = self.margin + i * step
            painter.drawLine(self.margin, y, self.canvas_size - self.margin, y)
        painter.setPen(QPen(QColor(150, 150, 150)))
        painter.drawText(self.margin - 15, self.canvas_size - self.margin + 15, "0%")
        painter.drawText(self.canvas_size - self.margin - 20, self.canvas_size - self.margin + 15, "100%")
        painter.drawText(5, self.margin + 5, "100%")
        painter.drawText(5, self.canvas_size - self.margin + 5, "0%")

    def _draw_curve(self, painter):
        pen = QPen(QColor(255, 165, 0), 2)
        painter.setPen(pen)
        canvas_points = [self._value_to_canvas(p) for p in self.points]
        for i in range(len(canvas_points) - 1):
            painter.drawLine(canvas_points[i], canvas_points[i + 1])

    def _draw_points(self, painter):
        for i, point in enumerate(self.points):
            cp = self._value_to_canvas(point)
            if i == self.hover_point or i == self.dragging_point:
                color = QColor(255, 200, 0)
            elif i == 0 or i == 3:
                color = QColor(200, 100, 50)
            else:
                color = QColor(255, 165, 0)
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.white, 2))
            painter.drawEllipse(cp, self.point_radius, self.point_radius)

    def _value_to_canvas(self, point):
        draw_area = self.canvas_size - 2 * self.margin
        x = self.margin + (point[0] / 255.0) * draw_area
        y = self.canvas_size - self.margin - (point[1] / 255.0) * draw_area
        return QPointF(x, y)

    def _canvas_to_value(self, pos):
        draw_area = self.canvas_size - 2 * self.margin
        x = ((pos.x() - self.margin) / draw_area) * 255.0
        y = ((self.canvas_size - self.margin - pos.y()) / draw_area) * 255.0
        x = max(0, min(255, x))
        y = max(0, min(255, y))
        return [int(x), int(y)]

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            for i in range(4):
                cp = self._value_to_canvas(self.points[i])
                dist = (event.pos() - cp.toPoint()).manhattanLength()
                if dist <= self.point_radius + 5:
                    self.dragging_point = i
                    break

    def mouseMoveEvent(self, event):
        if self.dragging_point >= 0:
            nv = self._canvas_to_value(event.pos())
            if self.dragging_point == 0:
                nv[0] = 0
            elif self.dragging_point == 1:
                nv[0] = max(1, min(self.points[2][0] - 1, nv[0]))
            elif self.dragging_point == 2:
                nv[0] = max(self.points[1][0] + 1, min(254, nv[0]))
            elif self.dragging_point == 3:
                nv[0] = 255
            self.points[self.dragging_point] = nv
            self.update()
            self.point_moved.emit()
        else:
            old_hover = self.hover_point
            self.hover_point = -1
            for i in range(4):
                cp = self._value_to_canvas(self.points[i])
                dist = (event.pos() - cp.toPoint()).manhattanLength()
                if dist <= self.point_radius + 5:
                    self.hover_point = i
                    break
            if old_hover != self.hover_point:
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging_point = -1


class GamingCurveEditor(QWidget):
    """
    Dropdown-selectable curve editor for gaming analog controls.

    A single canvas with a dropdown to switch between Left Stick, Right Stick,
    Left Trigger, and Right Trigger curves. Each has an independent 4-point
    curve (no presets). Curves are saved/loaded with the gaming configuration.

    Signals:
        curves_changed: Emitted whenever any curve is modified.
    """

    curves_changed = pyqtSignal()

    DROPDOWN_NAMES = ["Left Stick", "Right Stick", "Left Trigger", "Right Trigger"]
    KEYS = ["ls", "rs", "lt", "rt"]

    def __init__(self, parent=None):
        super().__init__(parent)
        # Store all 4 curves in memory, display one at a time
        self._curves = {key: [list(p) for p in LINEAR_CURVE] for key in self.KEYS}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Dropdown selector
        selector_layout = QHBoxLayout()
        selector_layout.setContentsMargins(0, 0, 0, 0)
        self.selector = QComboBox()
        for name in self.DROPDOWN_NAMES:
            self.selector.addItem(name)
        self.selector.currentIndexChanged.connect(self._on_selection_changed)
        selector_layout.addWidget(self.selector)
        layout.addLayout(selector_layout)

        # Single shared canvas
        self.canvas = GamingCurveCanvas()
        self.canvas.point_moved.connect(self._on_canvas_changed)
        layout.addWidget(self.canvas, alignment=Qt.AlignCenter)

        self.setLayout(layout)

        # Show first curve
        self.canvas.set_points(self._curves[self.KEYS[0]])

    def _current_key(self):
        idx = self.selector.currentIndex()
        return self.KEYS[idx] if 0 <= idx < len(self.KEYS) else self.KEYS[0]

    def _on_selection_changed(self, index):
        """Switch canvas to show the selected curve."""
        key = self.KEYS[index] if 0 <= index < len(self.KEYS) else self.KEYS[0]
        self.canvas.set_points(self._curves[key])

    def _on_canvas_changed(self):
        """Store canvas edits back into the current curve's data."""
        self._curves[self._current_key()] = self.canvas.get_points()
        self.curves_changed.emit()

    def get_all_curves(self):
        """Return dict of all 4 curves: {key: [[x,y], [x,y], [x,y], [x,y]]}"""
        # Flush current canvas state
        self._curves[self._current_key()] = self.canvas.get_points()
        return {key: [list(p) for p in pts] for key, pts in self._curves.items()}

    def set_all_curves(self, curves):
        """Set all 4 curves from dict: {key: [[x,y], [x,y], [x,y], [x,y]]}"""
        for key in self.KEYS:
            if key in curves and len(curves[key]) == 4:
                self._curves[key] = [list(p) for p in curves[key]]
        # Refresh canvas for currently selected curve
        self.canvas.set_points(self._curves[self._current_key()])

    def get_curve(self, key):
        """Get a single curve's points by key (ls/rs/lt/rt)."""
        if key == self._current_key():
            self._curves[key] = self.canvas.get_points()
        if key in self._curves:
            return [list(p) for p in self._curves[key]]
        return [list(p) for p in LINEAR_CURVE]

    def set_curve(self, key, points):
        """Set a single curve's points by key."""
        if key in self._curves and len(points) == 4:
            self._curves[key] = [list(p) for p in points]
            if key == self._current_key():
                self.canvas.set_points(self._curves[key])

    def reset_all(self):
        """Reset all curves to linear."""
        for key in self.KEYS:
            self._curves[key] = [list(p) for p in LINEAR_CURVE]
        self.canvas.set_points(self._curves[self._current_key()])
