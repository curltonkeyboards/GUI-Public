# SPDX-License-Identifier: GPL-2.0-or-later
"""A column of tabs down the left side, with engraved lettering, and the
chosen page on the right. It answers to the part of QTabWidget's interface
that the editors use (addTab, clear, count, widget, tabText, currentWidget,
currentIndex, setCurrentIndex, setCurrentWidget, indexOf, currentChanged)."""

from PyQt5.QtCore import Qt, QRect, QSize, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics
from PyQt5.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QStackedWidget,
                             QStylePainter, QStyleOptionButton, QStyle)


class SideTabButton(QPushButton):
    """A side tab whose name looks pressed into the surface: the theme draws
    the tab itself (its `side_tab` rules), this draws the lettering."""

    def __init__(self, text):
        super().__init__(text)
        self.setCheckable(True)
        self.setProperty("side_tab", True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(44)
        self.setMinimumWidth(168)

    def lettering_font(self):
        font = QFont(self.font())
        font.setPointSizeF(10.5)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        return font

    def sizeHint(self):
        # wide enough for the name in the lettering's own (larger) font
        width = QFontMetrics(self.lettering_font()).horizontalAdvance(self.text()) + 44
        return QSize(max(width, 150), 44)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""                    # the tab without its words
        painter.drawControl(QStyle.CE_PushButton, option)

        font = self.lettering_font()
        painter.setFont(font)
        painter.setRenderHint(QStylePainter.TextAntialiasing)

        area = self.rect().adjusted(18 if self.isChecked() else 20, 0, -8, 0)
        flags = Qt.AlignVCenter | Qt.AlignLeft
        ink = QColor(self.palette().buttonText().color())
        # Engraved: a lit edge just below the letters, a shaded one just above,
        # and the letters themselves a little sunk into the surface colour.
        lit = QColor(255, 255, 255, 190)
        shade = QColor(ink)
        shade.setAlpha(70)
        ink.setAlpha(215 if self.isChecked() else 150)
        painter.setPen(lit)
        painter.drawText(QRect(area).translated(0, 1), flags, self.text())
        painter.setPen(shade)
        painter.drawText(QRect(area).translated(0, -1), flags, self.text())
        painter.setPen(ink)
        painter.drawText(area, flags, self.text())


class SideTabs(QWidget):

    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buttons = []

        self.column = QVBoxLayout()
        self.column.setSpacing(0)
        self.column.setContentsMargins(0, 8, 0, 0)
        # below the last tab, carry on the line that separates tabs from content
        self.filler = QWidget()
        self.filler.setObjectName("side_tabs_filler")
        self.filler.setStyleSheet("QWidget#side_tabs_filler { border-right: 1px solid palette(mid); }")
        self.column.addWidget(self.filler, 1)
        side = QWidget()
        side.setLayout(self.column)

        self.stack = QStackedWidget()
        self.content = QWidget()
        self.content.setObjectName("side_tabs_content")
        self.content.setStyleSheet(
            "QWidget#side_tabs_content { border: 1px solid palette(mid); border-left: none; }")
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(1, 1, 1, 1)
        content_layout.addWidget(self.stack)
        self.content.setLayout(content_layout)

        layout = QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(side)
        layout.addWidget(self.content, 1)
        self.setLayout(layout)

    # ---- the QTabWidget-like part ----------------------------------------------

    def addTab(self, page, label):
        button = SideTabButton(label)
        button.clicked.connect(lambda checked=False, b=button: self.setCurrentIndex(self.buttons.index(b)))
        self.column.insertWidget(len(self.buttons), button)
        self.buttons.append(button)
        # every tab as wide as the widest name
        width = max(b.sizeHint().width() for b in self.buttons)
        for b in self.buttons:
            b.setFixedWidth(width)
        self.stack.addWidget(page)
        if len(self.buttons) == 1:
            self._show(0)
        return len(self.buttons) - 1

    def clear(self):
        """Take every page out (they are kept alive, as QTabWidget.clear does)."""
        for button in self.buttons:
            self.column.removeWidget(button)
            button.hide()               # gone from view at once, not when it is deleted
            button.setParent(None)
            button.deleteLater()
        self.buttons = []
        while self.stack.count():
            page = self.stack.widget(0)
            self.stack.removeWidget(page)
            page.setParent(None)

    def count(self):
        return len(self.buttons)

    def widget(self, index):
        return self.stack.widget(index) if 0 <= index < self.count() else None

    def tabText(self, index):
        return self.buttons[index].text() if 0 <= index < self.count() else ""

    def indexOf(self, page):
        return self.stack.indexOf(page)

    def currentIndex(self):
        return self.stack.currentIndex() if self.count() else -1

    def currentWidget(self):
        return self.stack.currentWidget() if self.count() else None

    def _show(self, index):
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.buttons):
            button.setChecked(i == index)

    def setCurrentIndex(self, index):
        if not 0 <= index < self.count():
            return
        changed = index != self.stack.currentIndex()
        cover = None
        if changed:
            # the first opening of a page can take a moment: say so meanwhile
            from widgets.loading_overlay import begin_loading, end_loading
            for i, button in enumerate(self.buttons):
                button.setChecked(i == index)
            cover = begin_loading(self.content, self.stack.widget(index))
        self._show(index)       # also puts the click's own toggle right
        if changed:
            try:
                self.currentChanged.emit(index)
            finally:
                end_loading(cover)

    def setCurrentWidget(self, page):
        self.setCurrentIndex(self.indexOf(page))
