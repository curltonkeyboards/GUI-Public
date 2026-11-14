# SPDX-License-Identifier: GPL-2.0-or-later
"""The home screen (Basic mode): one bubble per tab of the app. Clicking a
bubble opens that tab on its own (see MainWindow.open_group); the page's
Home button comes back."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton

from util import tr

TILE_WIDTH = 250
TILE_HEIGHT = 112
COLUMNS = 4


class HomeTile(QPushButton):
    """A big button with the name of the tab it opens and a line saying what
    is done there."""

    def __init__(self, title, description=""):
        super().__init__()
        self.setFixedSize(TILE_WIDTH, TILE_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("QLabel { font-size: 13pt; font-weight: bold; background: transparent; }")
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("QLabel { font-size: 9pt; color: palette(dark); background: transparent; }")

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label)
        layout.addStretch(1)
        self.setLayout(layout)
        self.set_description(description)

        # the click belongs to the tile, not to the words on it
        for label in (self.title_label, self.description_label):
            label.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_description(self, description):
        self.description_label.setText(description)
        self.description_label.setVisible(bool(description))


class HomePage(QWidget):

    group_chosen = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.heading = QLabel(tr("HomePage", "What do you want to set up?"))
        self.heading.setAlignment(Qt.AlignCenter)
        self.heading.setStyleSheet("QLabel { font-size: 16pt; font-weight: bold; }")

        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        self.tiles = {}     # name -> HomeTile

        grid_row = QHBoxLayout()
        grid_row.addStretch(1)
        grid_row.addLayout(self.grid)
        grid_row.addStretch(1)

        layout = QVBoxLayout()
        layout.addStretch(1)
        layout.addWidget(self.heading)
        layout.addSpacing(24)
        layout.addLayout(grid_row)
        layout.addStretch(2)
        self.setLayout(layout)

    def set_tiles(self, tiles):
        """tiles: (name, description) for every tab that has something to
        show right now, in order. The description may be empty."""
        wanted = [name for name, _ in tiles]
        if wanted == getattr(self, "_shown", None):
            for name, description in tiles:
                self.tiles[name].set_description(description)
            return
        self._shown = wanted

        for tile in self.tiles.values():
            self.grid.removeWidget(tile)
            tile.hide()

        for position, (name, description) in enumerate(tiles):
            tile = self.tiles.get(name)
            if tile is None:
                tile = HomeTile(tr("HomePage", name), description)
                tile.clicked.connect(lambda checked=False, name=name: self.group_chosen.emit(name))
                self.tiles[name] = tile
            tile.set_description(description)
            self.grid.addWidget(tile, position // COLUMNS, position % COLUMNS)
            tile.show()
