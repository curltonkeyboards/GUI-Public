# SPDX-License-Identifier: GPL-2.0-or-later

from PyQt5.QtCore import QEvent, QSize, Qt, QMimeData
from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import QPushButton, QLabel, QHBoxLayout, QApplication

# Drag payload of a keycode picked up from the palette (the qmk_id as UTF-8).
# The editors' keycode buttons, drop gaps and "+" buttons accept it — see
# widgets/keycode_button.py — inserting the key where it is dropped.
KEYCODE_PALETTE_MIME = "application/x-midiswitch-palette-keycode"


class SquareButton(QPushButton):
    """Palette key button.  Any instance that carries a ``keycode`` (the
    palette sites set ``btn.keycode = <Keycode>`` / a qmk_id string) can be
    DRAGGED: a press-and-move starts a copy drag carrying the qmk_id, so a key
    can be pulled straight from the palette into a macro line / toggle cycle
    (inserted at the drop position) or onto any editor key slot.  A plain
    click still emits ``clicked`` as before."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.scale = 1.2
        self.label = None
        self.word_wrap = False
        self.text = ""

        # Set property for styling via stylesheet
        self.setProperty("keycode_button", "true")
        self._palette_press_pos = None

    # ---- palette drag source -------------------------------------------

    def palette_drag_qmk_id(self):
        """The qmk_id this button would drag, or None (not a keycode button)."""
        kc = getattr(self, "keycode", None)
        if kc is None:
            return None
        if isinstance(kc, str):
            return kc
        return getattr(kc, "qmk_id", None)

    def mousePressEvent(self, ev):
        self._palette_press_pos = ev.pos() if ev.button() == Qt.LeftButton else None
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if (self._palette_press_pos is not None and (ev.buttons() & Qt.LeftButton)
                and (ev.pos() - self._palette_press_pos).manhattanLength() >= QApplication.startDragDistance()):
            qmk_id = self.palette_drag_qmk_id()
            if qmk_id:
                self._start_palette_drag(qmk_id)
                return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._palette_press_pos = None
        super().mouseReleaseEvent(ev)

    def _start_palette_drag(self, qmk_id):
        press_pos = self._palette_press_pos
        self._palette_press_pos = None
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(KEYCODE_PALETTE_MIME, str(qmk_id).encode("utf-8"))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        if press_pos is not None:
            drag.setHotSpot(press_pos)
        drag.exec_(Qt.CopyAction)
        # The release went to the drop target, so undo the pressed look and
        # collapse whatever drop preview an editor opened for this drag.
        self.setDown(False)
        try:
            from widgets.keycode_button import DropGap   # lazy: avoids an import cycle
            DropGap.close_active()
        except Exception:
            pass

    def event(self, ev):
        # Keycode buttons (anything carrying a keycode) show no hover text,
        # so hovering never pops up an id such as "KC_T".
        if ev.type() == QEvent.ToolTip and getattr(self, "keycode", None) is not None:
            ev.ignore()
            return True
        return super().event(ev)

    def setRelSize(self, ratio):
        self.scale = ratio
        self.updateGeometry()

    def setWordWrap(self, state):
        self.word_wrap = state
        self.setText(self.text)

    def sizeHint(self):
        size = int(round(self.fontMetrics().height() * self.scale))
        return QSize(size, size)

    # Override setText to facilitate automatic word wrapping
    def setText(self, text):
        self.text = text
        if self.word_wrap:
            super().setText("")
            if self.label is None:
                self.label = QLabel(text, self)
                self.label.setWordWrap(True)
                self.label.setAlignment(Qt.AlignCenter)
                layout = QHBoxLayout(self)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.addWidget(self.label,0,Qt.AlignCenter)
            else:
                self.label.setText(text)
        else:
            if self.label is not None:
                self.label.deleteLater()
            super().setText(text)