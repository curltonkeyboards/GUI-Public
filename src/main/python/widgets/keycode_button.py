# SPDX-License-Identifier: GPL-2.0-or-later
"""Keycode slot button used by the customizable-feature editors (macros, toggle
keys, tap dance, combos, DKS).

It is a SquareButton with the same ``keycode_button`` styling and
``KEYCODE_BTN_RATIO`` size as the buttons in FilteredTabbedKeycodes, so the
keys shown inside an editor look exactly like the palette they are picked from.
The selected slot (the one the next palette pick lands on) renders through the
stylesheet's ``:checked`` state plus a contrasting outline drawn on top, and an
owner can call ``install_click_away_deselect`` so a click on empty space in its
editor area clears the selection.

Unlike KeyWidget it never opens the keycode tray itself: clicking a button emits
``selected`` and the owning editor feeds the palette pick back through
``on_keycode_changed`` / ``set_keycode``.  Keycode display goes through
KeycodeDisplay.display_keycode, so custom names and the country-keymap override
colouring are preserved.

Optional per-sequence behaviour (enabled by the owner setting ``drag_group``):

* drag one button onto another of the same group to reorder — the owner gets
  ``reorder_requested(source, target, before)`` and reorders its model (a
  group can span several owners, e.g. every action line of one macro; the
  drop handler then defers any widget rebuild to ``drag_finished``).  While
  the drag hovers a button the owner gets ``drop_hover(source, target,
  before)`` and opens its ``DropGap`` there, so the other keys are pushed
  aside to show where the dragged one will sit;
* right-click → "Duplicate" — the owner gets ``duplicate_requested(button)``;
* a key dragged from the PALETTE (SquareButton's drag, KEYCODE_PALETTE_MIME)
  can be dropped on a row's button / gap / "+" to INSERT it there
  (``insert_requested(qmk_id, target, before)``), or on a fixed slot to assign
  it (``assign_requested``).
"""

import sip

from PyQt5.QtCore import Qt, QEvent, QObject, QMimeData, QPropertyAnimation, QEasingCurve, QSize, QRect, pyqtSignal, pyqtProperty
from PyQt5.QtGui import QDrag, QPainter, QPen, QPalette
from PyQt5.QtWidgets import QApplication, QMenu, QSizePolicy, QWidget

from constants import KEYCODE_BTN_RATIO
from keycodes.keycodes import Keycode
from keycode_search_dialog import KeycodeSearchDialog
from tabbed_keycodes import keycode_filter_any
from util import KeycodeDisplay
from widgets.square_button import SquareButton, KEYCODE_PALETTE_MIME

KEYCODE_DRAG_MIME = "application/x-midiswitch-keycode-button"

# The editor buttons are the palette button plus this much on each axis: the
# palette packs thousands of keys, an editor shows a handful and they are the
# thing being edited, so they get room to breathe (and a bigger drop target).
KEYCODE_BTN_EXTRA_PX = 10


def keycode_button_px(font_metrics):
    """Edge length of an editor keycode button for the given font metrics —
    the palette size (KEYCODE_BTN_RATIO x font height) + KEYCODE_BTN_EXTRA_PX.
    Owners size their companion buttons (the macro line's "+") with it."""
    return int(round(font_metrics.height() * KEYCODE_BTN_RATIO)) + KEYCODE_BTN_EXTRA_PX


class _ClickAwayDeselect(QObject):
    """Application event filter behind install_click_away_deselect."""

    def __init__(self, area, callback):
        super().__init__(area)
        self.area = area
        self.callback = callback

    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.MouseButtonPress or not isinstance(obj, QWidget):
            return False
        area = self.area
        if sip.isdeleted(area) or not area.isVisible():
            return False
        if obj is not area and not area.isAncestorOf(obj):
            return False
        w = obj
        while w is not None and w is not area:
            # A press on a key (or a key's own child, e.g. the macro X) or on a
            # drop target keeps the selection; the key handles it itself.
            if getattr(w, "keeps_key_selection", False):
                return False
            w = w.parentWidget()
        self.callback()
        return False


def install_click_away_deselect(area, callback):
    """Call ``callback`` whenever the mouse is pressed inside ``area`` on
    anything that is not a keycode button (empty space, labels, group boxes,
    ...), so clicking off the selected key in the same editor unselects it.
    The palette sits outside ``area``, so picking a keycode never deselects."""
    app = QApplication.instance()
    if app is None:
        return None
    filt = _ClickAwayDeselect(area, callback)
    app.installEventFilter(filt)
    area.destroyed.connect(lambda *_: app.removeEventFilter(filt))
    return filt


def drag_accepted_from(ev, drag_group, exclude=None):
    """True if ``ev`` carries a KeycodeButton of ``drag_group`` (not ``exclude``)."""
    src = ev.source()
    return (isinstance(src, KeycodeButton) and src is not exclude
            and drag_group is not None and src.drag_group is drag_group
            and ev.mimeData().hasFormat(KEYCODE_DRAG_MIME))


def palette_keycode_from(ev, keycode_filter=None):
    """The qmk_id a PALETTE drag (see SquareButton) carries, if ``ev`` is one
    and ``keycode_filter`` (None = accept any) admits it; else None."""
    mime = ev.mimeData()
    if mime is None or not mime.hasFormat(KEYCODE_PALETTE_MIME):
        return None
    try:
        qmk_id = bytes(mime.data(KEYCODE_PALETTE_MIME)).decode("utf-8")
    except Exception:
        return None
    if not qmk_id:
        return None
    if keycode_filter is not None and not keycode_filter(qmk_id):
        return None
    return qmk_id


class DropGap(QWidget):
    """The "push" preview of a drag: an empty slot the owner inserts into its
    row at the place the dragged key will land, so the neighbours slide aside
    before the drop instead of just highlighting one of them.

    One gap per owner (a row).  ``open_at(target, before, size)`` records the
    drop position and animates the gap open (the owner has already inserted
    it into the layout there); ``close()`` collapses it.  Only one gap is open
    at a time across ALL owners — opening one closes the previous, so dragging
    from one macro line to another leaves no stale gap behind.

    It accepts the drag itself (the hovered button shifts sideways when the gap
    opens next to it, so the cursor often ends up over the gap) and a drop on
    it reorders exactly like a drop on the button it stands in for:
    ``dropped(source, target, before)``.
    """

    keeps_key_selection = True

    dropped = pyqtSignal(object, object, bool)   # source, target, insert-before
    inserted = pyqtSignal(str, object, bool)     # palette qmk_id, target, insert-before

    _active = None       # the currently open gap, if any
    ANIM_MS = 130

    def __init__(self, parent=None):
        super().__init__(parent)
        self.drag_group = None
        self.keycode_filter = None   # gate for palette drops (None = accept any)
        self.target = None       # (target button, before) the gap stands in for
        self.before = True
        self._gap_width = 0
        self._full_width = 0
        self._key_size = QSize(0, 0)   # dashed outline drawn inside the gap
        self._key_offset = 0
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedWidth(0)
        self._anim = QPropertyAnimation(self, b"gapWidth", self)
        self._anim.setDuration(self.ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.hide()

    # animated property: the current width of the slot
    def _get_gap_width(self):
        return self._gap_width

    def _set_gap_width(self, w):
        self._gap_width = int(w)
        self.setFixedWidth(self._gap_width)
        self.updateGeometry()

    gapWidth = pyqtProperty(int, _get_gap_width, _set_gap_width)

    @classmethod
    def close_active(cls):
        if cls._active is not None:
            cls._active.close()

    def is_open(self):
        return self.isVisible() and self.target is not None

    def stands_for(self, target, before):
        return self.is_open() and self.target is target and self.before == before

    def open_at(self, target, before, size, key_size=None, key_offset=0):
        """Open (animated) for a drop next to ``target``.  Call after inserting
        the gap into the layout at that position.  ``size`` is the slot the
        row must open; a dashed outline of ``key_size`` (default: the slot)
        is drawn ``key_offset`` px in, where the key itself will sit."""
        if DropGap._active is not None and DropGap._active is not self:
            DropGap._active.close()
        DropGap._active = self
        self.target = target
        self.before = before
        self._key_size = QSize(key_size) if key_size is not None else QSize(size)
        self._key_offset = key_offset
        self.setFixedHeight(size.height())
        self._anim.stop()
        if not self.isVisible():
            self._set_gap_width(0)
            self.show()
        self._full_width = size.width()
        self._anim.setStartValue(self._gap_width)
        self._anim.setEndValue(self._full_width)
        self._anim.start()

    def close(self):
        self._anim.stop()
        self.target = None
        self._set_gap_width(0)
        self.hide()
        if DropGap._active is self:
            DropGap._active = None

    def sizeHint(self):
        return QSize(self._gap_width, self.height())

    def paintEvent(self, ev):
        # Dashed outline of the landing slot, growing with the gap
        w = min(self._gap_width - self._key_offset, self._key_size.width())
        if w < 8:
            return
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QApplication.palette().highlight().color())
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        qp.setPen(pen)
        qp.setBrush(Qt.NoBrush)
        r = QRect(self._key_offset + 2, 2, w - 4, self._key_size.height() - 4)
        qp.drawRoundedRect(r, 8, 8)
        qp.end()

    # ---- drag events: keep accepting the drag while the cursor sits in the gap
    def dragEnterEvent(self, ev):
        if drag_accepted_from(ev, self.drag_group):
            ev.setDropAction(Qt.MoveAction)
            ev.accept()
        elif palette_keycode_from(ev, self.keycode_filter):
            ev.setDropAction(Qt.CopyAction)
            ev.accept()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        self.dragEnterEvent(ev)

    def dropEvent(self, ev):
        if not self.isVisible():   # not open: nothing to stand in for
            ev.ignore()
            return
        target, before = self.target, self.before   # target may be None = "empty row"
        if drag_accepted_from(ev, self.drag_group):
            ev.setDropAction(Qt.MoveAction)
            ev.accept()
            self.dropped.emit(ev.source(), target, before)
            return
        qmk_id = palette_keycode_from(ev, self.keycode_filter)
        if qmk_id:
            ev.setDropAction(Qt.CopyAction)
            ev.accept()
            self.inserted.emit(qmk_id, target, before)
            return
        ev.ignore()


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
    drag_started = pyqtSignal(object)                # self, just before QDrag.exec_() (already hidden)
    drag_finished = pyqtSignal(object)               # self, after QDrag.exec_() returned
    # A drag of the same group hovers this button: (source, self, insert-before).
    # The owner opens its DropGap there so the row previews the drop.  A PALETTE
    # drag hovering a button of a drag group reports the same way (source = the
    # palette button), so it gets the same push preview.
    drop_hover = pyqtSignal(object, object, bool)
    # A palette key was dropped on a button of a drag group: (qmk_id, self,
    # insert-before) — the owner inserts a NEW key there.
    insert_requested = pyqtSignal(str, object, bool)
    # A palette key was dropped on a fixed slot (no drag group): the button has
    # already taken it (on_keycode_changed) — (resulting keycode, self).
    assign_requested = pyqtSignal(str, object)

    keeps_key_selection = True   # see install_click_away_deselect

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

    def sizeHint(self):
        base = super().sizeHint()
        return QSize(base.width() + KEYCODE_BTN_EXTRA_PX, base.height() + KEYCODE_BTN_EXTRA_PX)

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
        self.dlg = KeycodeSearchDialog(self.keycode_filter, self.window())
        self.dlg.finished.connect(self.on_dlg_finished)
        self.dlg.setModal(True)
        self.dlg.show()

    def on_dlg_finished(self, res):
        if res > 0 and self.dlg.value:
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

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if not self.is_selected:
            return
        # Selection outline: the :checked fill alone reads as "pressed", so
        # the key the next pick lands on also gets a contrasting border.
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self.palette().color(QPalette.WindowText))
        pen.setWidth(3)
        qp.setPen(pen)
        qp.setBrush(Qt.NoBrush)
        qp.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 8, 8)
        qp.end()

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
        # The key is "picked up": hide it for the duration of the drag so the
        # row collapses around it and the DropGap the owner opens shows the
        # exact post-drop arrangement (same idiom as Qt's fridge-magnets
        # example).  Shown again below whatever happened to the drop.
        self.hide()
        self.drag_started.emit(self)
        drag.exec_(Qt.MoveAction)
        DropGap.close_active()
        self.show()
        # The drop handler ran INSIDE exec_()'s nested event loop, where an
        # owner must not destroy buttons (this one included).  Owners that need
        # to rebuild after a drop wait for this signal instead.
        self.drag_finished.emit(self)

    def _drag_accepted(self, ev):
        return drag_accepted_from(ev, self.drag_group, exclude=self)

    def _drop_side(self, pos):
        return "before" if pos.x() < self.width() / 2 else "after"

    def _palette_drop_accepted(self, ev):
        return palette_keycode_from(ev, self.keycode_filter) is not None

    def dragEnterEvent(self, ev):
        if self._drag_accepted(ev):
            ev.setDropAction(Qt.MoveAction)
            ev.accept()
            self._drop_hover = self._drop_side(ev.pos())
            self.drop_hover.emit(ev.source(), self, self._drop_hover == "before")
        elif self._palette_drop_accepted(ev):
            ev.setDropAction(Qt.CopyAction)
            ev.accept()
            if self.drag_group is not None:   # a row: preview the insertion
                self._drop_hover = self._drop_side(ev.pos())
                self.drop_hover.emit(ev.source(), self, self._drop_hover == "before")
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        if self._drag_accepted(ev) or (self._palette_drop_accepted(ev) and self.drag_group is not None):
            ev.setDropAction(Qt.MoveAction if self._drag_accepted(ev) else Qt.CopyAction)
            ev.accept()
            side = self._drop_side(ev.pos())
            if side != self._drop_hover:
                self._drop_hover = side
                self.drop_hover.emit(ev.source(), self, side == "before")
        elif self._palette_drop_accepted(ev):
            ev.setDropAction(Qt.CopyAction)
            ev.accept()
        else:
            ev.ignore()

    def dragLeaveEvent(self, ev):
        # The gap stays where it is: the cursor is usually just moving into
        # the gap itself or onto the next button, which re-places it.  It is
        # collapsed when the drag ends (DropGap.close_active in _start_drag).
        self._drop_hover = None
        ev.accept()

    def dropEvent(self, ev):
        self._drop_hover = None
        before = self._drop_side(ev.pos()) == "before"
        if self._drag_accepted(ev):
            ev.setDropAction(Qt.MoveAction)
            ev.accept()
            self.reorder_requested.emit(ev.source(), self, before)
            return
        qmk_id = palette_keycode_from(ev, self.keycode_filter)
        if qmk_id:
            ev.setDropAction(Qt.CopyAction)
            ev.accept()
            if self.drag_group is not None:
                # a row (macro line / toggle cycle): insert a new key here
                self.insert_requested.emit(qmk_id, self, before)
            else:
                # a fixed slot (tap dance / combo / DKS / toggle target): take it
                self.on_keycode_changed(qmk_id)
                self.assign_requested.emit(self.keycode, self)
            return
        ev.ignore()

    def _show_context_menu(self, global_pos):
        if self.drag_group is None:
            return
        menu = QMenu(self)
        act_dup = menu.addAction("Duplicate")
        chosen = menu.exec_(global_pos)
        if chosen is act_dup:
            self.duplicate_requested.emit(self)
