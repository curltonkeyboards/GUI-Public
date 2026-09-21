# SPDX-License-Identifier: GPL-2.0-or-later
"""Keycode slot button used by the customizable-feature editors (macros, toggle
keys, tap dance, combos, DKS).

It is a SquareButton with the same ``keycode_button`` styling and
``KEYCODE_BTN_RATIO`` size as the buttons in FilteredTabbedKeycodes, so the
keys shown inside an editor look exactly like the palette they are picked from.
The selected slot (the one the next palette pick lands on) renders through the
stylesheet's ``:checked`` state.

Unlike KeyWidget it never opens the keycode tray itself: clicking a button emits
``selected`` and the owning editor feeds the palette pick back through
``on_keycode_changed`` / ``set_keycode``.  Keycode display goes through
KeycodeDisplay.display_keycode, so custom names and the country-keymap override
colouring are preserved.

Optional per-sequence behaviour (enabled by the owner setting ``drag_group``):

* drag one button onto another of the same group to reorder — the owner gets
  ``reorder_requested(source, target, before)`` and reorders its model;
* right-click → "Duplicate" — the owner gets ``duplicate_requested(button)``.
"""

from PyQt5.QtCore import Qt, QMimeData, pyqtSignal
from PyQt5.QtGui import QDrag, QPainter, QPen
from PyQt5.QtWidgets import QApplication, QMenu, QSizePolicy

from constants import KEYCODE_BTN_RATIO
from keycodes.keycodes import Keycode
from any_keycode_dialog import AnyKeycodeDialog
from tabbed_keycodes import keycode_filter_any
from util import KeycodeDisplay
from widgets.square_button import SquareButton

KEYCODE_DRAG_MIME = "application/x-midiswitch-keycode-button"


def reorder_list(items, src_idx, dst_idx, before):
    """Move ``items[src_idx]`` next to ``items[dst_idx]`` (before or after it),
    in place.  Returns the item's new index."""
    if src_idx == dst_idx:
        return src_idx
    item = items.pop(src_idx)
    ins = dst_idx if before else dst_idx + 1
    if src_idx < ins:
        ins -= 1
    items.insert(ins, item)
    return ins


def merge_keycode_pick(current, picked):
    """Resolve a palette pick against the button's current keycode.

    A masked keycode (e.g. ``LSFT(kc)``) is picked in two steps on the palette:
    the modifier button first, then a basic key for the inner part.  KeyWidget
    handled that with a separately clickable inner area; a flat button has
    none, so while the button holds a mask whose inner key is still empty, the
    next basic pick fills the inner key instead of replacing the whole thing.
    """
    try:
        if (isinstance(current, str) and Keycode.is_mask(current)
                and isinstance(picked, str) and Keycode.is_basic(picked)):
            inner = Keycode.find_inner_keycode(current)
            if inner is None or inner.qmk_id == "KC_NO":
                return "{}({})".format(current[:current.find("(")], picked)
    except Exception:
        pass
    return picked


class KeycodeButton(SquareButton):

    changed = pyqtSignal()
    selected = pyqtSignal(object)                    # self, on left click
    reorder_requested = pyqtSignal(object, object, bool)  # source, target, insert-before
    duplicate_requested = pyqtSignal(object)         # self

    def __init__(self, keycode_filter=None, parent=None):
        super().__init__(parent)
        self.setRelSize(KEYCODE_BTN_RATIO)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.ClickFocus)
        # Right-clicks come to mousePressEvent (we build the menu there);
        # nothing else must synthesize a context-menu event for the parent.
        self.setContextMenuPolicy(Qt.PreventContextMenu)
        self.setAcceptDrops(True)

        self.keycode = "KC_NO"
        self.is_selected = False
        self.masked = False
        self.drag_group = None   # owner object; drag/drop and Duplicate only inside one group
        self._text = ""
        self._mask_text = ""
        self._color = None
        self._mask_color = None
        self._base_tooltip = ""
        self._press_pos = None
        self._drop_hover = None  # None / "before" / "after"
        self._registered = False

        self.set_keycode_filter(keycode_filter)
        self.update_display()
        KeycodeDisplay.notify_keymap_override(self)
        self._registered = True

    # ---- lifecycle -----------------------------------------------------

    def _unregister(self):
        if self._registered:
            self._registered = False
            try:
                KeycodeDisplay.unregister_keymap_override(self)
            except ValueError:
                pass

    def delete(self):
        self._unregister()
        self.deleteLater()

    def deleteLater(self):
        self._unregister()
        super().deleteLater()

    # ---- keycode model -------------------------------------------------

    def set_keycode_filter(self, keycode_filter):
        if keycode_filter is None:
            keycode_filter = keycode_filter_any
        self.keycode_filter = keycode_filter

    def set_keycode(self, kc):
        if kc == self.keycode:
            return
        if self.keycode_filter and not self.keycode_filter(kc):
            return
        self.keycode = kc
        self.update_display()
        self.changed.emit()

    def on_keycode_changed(self, keycode):
        """A pick arrived from the palette: fill an empty mask inner key, else
        replace the keycode."""
        self.set_keycode(merge_keycode_pick(self.keycode, keycode))

    def on_anykey(self):
        kc = self.keycode
        if self.masked:
            inner = Keycode.find_inner_keycode(kc)
            if inner is not None:
                kc = inner.qmk_id
        self.dlg = AnyKeycodeDialog(kc)
        self.dlg.finished.connect(self.on_dlg_finished)
        self.dlg.setModal(True)
        self.dlg.show()

    def on_dlg_finished(self, res):
        if res > 0:
            self.on_keycode_changed(self.dlg.value)

    def on_keymap_override(self):
        self.update_display()

    def update_display(self):
        if not isinstance(self.keycode, str):
            # 0 is the "remove me" marker used by the macro editor; nothing to draw
            return
        KeycodeDisplay.display_keycode(self, self.keycode)

    # ---- KeycodeDisplay widget API (setText/setMaskText/setToolTip/colors) --

    def setText(self, text):
        self._text = text
        self._refresh_text()

    def setMaskText(self, text):
        self._mask_text = text
        self._refresh_text()

    def _refresh_text(self):
        text = self._text
        if self.masked:
            # outer label on the first line, inner key (or the "(kc)" slot
            # still waiting for a pick) on the second
            outer = text.split("\n")[0]
            if "(" in outer:
                # unresolved raw id such as "LSFT(kc)" / "LSFT(KC_A)": show the modifier
                outer = outer[:outer.find("(")]
            outer = outer.strip()
            inner = self._mask_text.strip()
            text = "{}\n{}".format(outer, inner if inner else "(kc)")
        super().setText(text.replace("&", "&&"))

    def setToolTip(self, tooltip):
        self._base_tooltip = tooltip or ""
        self._refresh_tooltip()

    def _refresh_tooltip(self):
        tip = self._base_tooltip
        if self.drag_group is not None:
            hint = "Drag to reorder · right-click to duplicate"
            tip = "{}\n{}".format(tip, hint) if tip else hint
        super().setToolTip(tip)

    def setColor(self, color):
        self._color = color
        self._refresh_color()

    def setMaskColor(self, color):
        self._mask_color = color
        self._refresh_color()

    def _refresh_color(self):
        # Same idiom as KeycodeDisplay.relabel_buttons for the palette buttons:
        # an overridden keycode (country keymap) shows in the Link colour.
        color = self._color or self._mask_color
        if color is not None:
            self.setStyleSheet("QPushButton {color: rgb%s;}" % str(color.getRgb()))
        else:
            self.setStyleSheet("QPushButton {}")

    # ---- selection -----------------------------------------------------

    def set_selected(self, selected):
        self.is_selected = bool(selected)
        self.setChecked(self.is_selected)
        self.update()

    def deselect(self):
        self.set_selected(False)

    # ---- drag & drop reordering / duplicate ----------------------------

    def set_drag_group(self, group):
        self.drag_group = group
        self._refresh_tooltip()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._press_pos = ev.pos()
            self.setFocus(Qt.MouseFocusReason)
            self.selected.emit(self)
            ev.accept()
        elif ev.button() == Qt.RightButton:
            ev.accept()
            self._show_context_menu(ev.globalPos())
        else:
            ev.accept()

    def mouseMoveEvent(self, ev):
        if (self._press_pos is not None and (ev.buttons() & Qt.LeftButton)
                and self.drag_group is not None
                and (ev.pos() - self._press_pos).manhattanLength() >= QApplication.startDragDistance()):
            self._start_drag()
            return
        ev.accept()

    def mouseReleaseEvent(self, ev):
        self._press_pos = None
        ev.accept()

    def keyPressEvent(self, ev):
        # A checkable QAbstractButton toggles on Space/Enter; the checked state
        # mirrors the editor's selection, so keep the keyboard off it.
        if ev.key() in (Qt.Key_Space, Qt.Key_Select, Qt.Key_Return, Qt.Key_Enter):
            ev.accept()
            return
        super().keyPressEvent(ev)

    def _start_drag(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(KEYCODE_DRAG_MIME, str(self.keycode).encode("utf-8"))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(self._press_pos)
        self._press_pos = None
        drag.exec_(Qt.MoveAction)

    def _drag_accepted(self, ev):
        src = ev.source()
        return (isinstance(src, KeycodeButton) and src is not self
                and self.drag_group is not None and src.drag_group is self.drag_group
                and ev.mimeData().hasFormat(KEYCODE_DRAG_MIME))

    def _drop_side(self, pos):
        return "before" if pos.x() < self.width() / 2 else "after"

    def dragEnterEvent(self, ev):
        if self._drag_accepted(ev):
            ev.setDropAction(Qt.MoveAction)
            ev.accept()
            self._drop_hover = self._drop_side(ev.pos())
            self.update()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        if self._drag_accepted(ev):
            ev.setDropAction(Qt.MoveAction)
            ev.accept()
            side = self._drop_side(ev.pos())
            if side != self._drop_hover:
                self._drop_hover = side
                self.update()
        else:
            ev.ignore()

    def dragLeaveEvent(self, ev):
        self._drop_hover = None
        self.update()
        ev.accept()

    def dropEvent(self, ev):
        self._drop_hover = None
        self.update()
        if not self._drag_accepted(ev):
            ev.ignore()
            return
        before = self._drop_side(ev.pos()) == "before"
        ev.setDropAction(Qt.MoveAction)
        ev.accept()
        self.reorder_requested.emit(ev.source(), self, before)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._drop_hover is None:
            return
        # Insertion marker on the side the dragged key will land on
        qp = QPainter(self)
        pen = QPen(QApplication.palette().highlight().color())
        pen.setWidth(3)
        qp.setPen(pen)
        x = 2 if self._drop_hover == "before" else self.width() - 2
        qp.drawLine(x, 3, x, self.height() - 3)
        qp.end()

    def _show_context_menu(self, global_pos):
        if self.drag_group is None:
            return
        menu = QMenu(self)
        act_dup = menu.addAction("Duplicate")
        chosen = menu.exec_(global_pos)
        if chosen is act_dup:
            self.duplicate_requested.emit(self)
