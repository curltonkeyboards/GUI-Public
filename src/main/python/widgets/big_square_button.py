# SPDX-License-Identifier: GPL-2.0-or-later

# SPDX-License-Identifier: GPL-2.0-or-later

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QFont, QFontMetrics
from PyQt5.QtWidgets import QPushButton, QLabel, QHBoxLayout

class BigSquareButton(QPushButton):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scale = 1.2
        self.label = None
        self.word_wrap = True
        self.text = ""
        self.adjust_font_size = True

        # Set property for styling via stylesheet
        self.setProperty("keycode_button", "true")

        self.update_size()  # Set the initial size for the button

    def setRelSize(self, ratio):
        self.scale = ratio
        self.update_size()  # Update the size based on the new ratio
        self.update_text()

    def update_size(self):
        new_size = self.sizeHint()
        new_size.setWidth(int(new_size.width() * 1.5))  # Increase width by 50%
        new_size.setHeight(int(new_size.height() * 1.5))  # Increase height by 50%
        self.setFixedSize(new_size)  # Set the new fixed size for the button

    def setWordWrap(self, state):
        self.word_wrap = state
        self.update_text()

    def sizeHint(self):
        size = int(round(self.fontMetrics().height() * self.scale))
        return QSize(size, size)  # Return the size of the button

    def setText(self, text):
        self.text = text
        self.update_text()

    def update_text(self):
        if self.word_wrap:
            if self.label is None:
                self.label = QLabel(self)
                self.label.setWordWrap(True)
                self.label.setAlignment(Qt.AlignCenter)
                layout = QHBoxLayout(self)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.addWidget(self.label, 0, Qt.AlignCenter)
            self.adjust_font_size_if_needed()
            self.label.setText(self.text)
        else:
            if self.label is not None:
                self.label.deleteLater()
            super().setText(self.text)

    def adjust_font_size_if_needed(self):
        if self.adjust_font_size:
            font = self.font()
            font_size = font.pointSize()
            fm = QFontMetrics(font)
            text_width = fm.width(self.text)
            text_height = fm.height()
            button_width = self.width()
            button_height = self.height()

            while text_width > (button_width + 20) or text_height > (button_height + 20):
                font_size -= 1
                if font_size <= 6:  # Avoid too small font sizes
                    break
                font.setPointSize(font_size)
                fm = QFontMetrics(font)
                text_width = fm.width(self.text)
                text_height = fm.height()

            self.label.setFont(font)

