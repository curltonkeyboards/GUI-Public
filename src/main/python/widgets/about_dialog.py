# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QDialogButtonBox, QApplication

from util import tr


class AboutDialog(QDialog):
    """Help > About: app name, version and the licence credits."""

    def __init__(self, parent, appctx):
        super().__init__(parent)
        self.setWindowTitle(tr("About", "About MIDIswitch KeyStation"))
        self.resize(720, 560)

        layout = QVBoxLayout(self)

        title = QLabel("MIDIswitch KeyStation")
        font = title.font()
        font.setPointSize(font.pointSize() + 6)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        version = QApplication.applicationVersion()
        if not version:
            try:
                version = appctx.build_settings.get("version", "")
            except Exception:
                version = ""
        info = QLabel(tr("About", "Version {}").format(version) + "\n" +
                      tr("About", "Copyright (c) MIDIswitch"))
        layout.addWidget(info)

        heading = QLabel(tr("About", "Licences and credits"))
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)

        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.NoWrap)
        text.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        text.setPlainText(self._load_licences(appctx))
        layout.addWidget(text, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    @staticmethod
    def _load_licences(appctx):
        try:
            with open(appctx.get_resource("licences.txt"), "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return tr("About", "The licence file could not be found.")
