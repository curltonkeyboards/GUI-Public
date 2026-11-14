# SPDX-License-Identifier: GPL-2.0-or-later
"""A Record button for a key shortcut: press it, hold the modifier keys, press
the key. It reports the modifiers that were held and the key that was pressed.

Recording ends at the first key that is not a modifier. Pressed with a
modifier held, that is the shortcut; pressed on its own (or Esc), recording
just stops and nothing changes.

Fn 1 / Fn 2 are keys of the MIDIswitch itself and send nothing to the
computer, so no key event ever arrives for them. While recording, the button
asks the keyboard instead: `set_fn_poll()` takes a function that returns the
Fn keys held right now (bit 0 = Fn 1, bit 1 = Fn 2), and the button calls it a
few times a second. They then count as held modifiers like any other.
"""

import sys

from PyQt5.QtCore import Qt, QEvent, QRectF, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPen
from PyQt5.QtWidgets import QApplication, QPushButton, QSizePolicy

from util import tr

# bit number of each modifier, as the keyboard counts them
LCTRL, LSHIFT, LALT, LGUI, RCTRL, RSHIFT, RALT, RGUI = range(8)
MOD_NAMES = ["LCtrl", "LShift", "LAlt", "LGui", "RCtrl", "RShift", "RAlt", "RGui"]
FN_NAMES = ["Fn 1", "Fn 2"]

RECORD_RED = QColor(0xE5, 0x39, 0x35)
FN_POLL_MS = 40
PULSE_MS = 50

# Which side a modifier is on, from its scan code (Windows; the 0x100 marks
# the right-hand / extended key). Elsewhere, or if unknown, the left one.
_SCAN_MODS = {0x1D: LCTRL, 0x11D: RCTRL, 0x2A: LSHIFT, 0x36: RSHIFT,
              0x38: LALT, 0x138: RALT, 0x15B: LGUI, 0x15C: RGUI}
_QT_MODS = {Qt.Key_Control: LCTRL, Qt.Key_Shift: LSHIFT, Qt.Key_Alt: LALT,
            Qt.Key_Meta: LGUI, Qt.Key_AltGr: RALT, Qt.Key_Super_L: LGUI, Qt.Key_Super_R: RGUI}

# Windows virtual-key codes: the key itself, whatever Shift makes of it
_VK_KEYS = {0xBA: "KC_SCOLON", 0xBB: "KC_EQUAL", 0xBC: "KC_COMMA", 0xBD: "KC_MINUS", 0xBE: "KC_DOT",
            0xBF: "KC_SLASH", 0xC0: "KC_GRAVE", 0xDB: "KC_LBRACKET", 0xDC: "KC_BSLASH",
            0xDD: "KC_RBRACKET", 0xDE: "KC_QUOTE"}
_VK_KEYS.update({0x41 + i: "KC_" + chr(0x41 + i) for i in range(26)})
_VK_KEYS.update({0x30 + i: "KC_" + str(i) for i in range(10)})
_VK_KEYS.update({0x60 + i: "KC_KP_" + str(i) for i in range(10)})

_QT_KEYS = {
    Qt.Key_Space: "KC_SPACE", Qt.Key_Return: "KC_ENTER", Qt.Key_Enter: "KC_KP_ENTER", Qt.Key_Tab: "KC_TAB",
    Qt.Key_Backtab: "KC_TAB", Qt.Key_Backspace: "KC_BSPACE", Qt.Key_Delete: "KC_DELETE",
    Qt.Key_Insert: "KC_INSERT", Qt.Key_Home: "KC_HOME", Qt.Key_End: "KC_END",
    Qt.Key_PageUp: "KC_PGUP", Qt.Key_PageDown: "KC_PGDOWN", Qt.Key_Up: "KC_UP", Qt.Key_Down: "KC_DOWN",
    Qt.Key_Left: "KC_LEFT", Qt.Key_Right: "KC_RIGHT", Qt.Key_CapsLock: "KC_CAPSLOCK",
    Qt.Key_Print: "KC_PSCREEN", Qt.Key_Pause: "KC_PAUSE", Qt.Key_ScrollLock: "KC_SCROLLLOCK",
    Qt.Key_NumLock: "KC_NUMLOCK", Qt.Key_Menu: "KC_APPLICATION",
    Qt.Key_Minus: "KC_MINUS", Qt.Key_Underscore: "KC_MINUS", Qt.Key_Equal: "KC_EQUAL", Qt.Key_Plus: "KC_EQUAL",
    Qt.Key_BracketLeft: "KC_LBRACKET", Qt.Key_BraceLeft: "KC_LBRACKET",
    Qt.Key_BracketRight: "KC_RBRACKET", Qt.Key_BraceRight: "KC_RBRACKET",
    Qt.Key_Backslash: "KC_BSLASH", Qt.Key_Bar: "KC_BSLASH", Qt.Key_Semicolon: "KC_SCOLON",
    Qt.Key_Colon: "KC_SCOLON", Qt.Key_Apostrophe: "KC_QUOTE", Qt.Key_QuoteDbl: "KC_QUOTE",
    Qt.Key_QuoteLeft: "KC_GRAVE", Qt.Key_AsciiTilde: "KC_GRAVE", Qt.Key_Comma: "KC_COMMA",
    Qt.Key_Less: "KC_COMMA", Qt.Key_Period: "KC_DOT", Qt.Key_Greater: "KC_DOT",
    Qt.Key_Slash: "KC_SLASH", Qt.Key_Question: "KC_SLASH",
    Qt.Key_Exclam: "KC_1", Qt.Key_At: "KC_2", Qt.Key_NumberSign: "KC_3", Qt.Key_Dollar: "KC_4",
    Qt.Key_Percent: "KC_5", Qt.Key_AsciiCircum: "KC_6", Qt.Key_Ampersand: "KC_7",
    Qt.Key_Asterisk: "KC_8", Qt.Key_ParenLeft: "KC_9", Qt.Key_ParenRight: "KC_0",
}
_QT_KEYS.update({Qt.Key_A + i: "KC_" + chr(0x41 + i) for i in range(26)})
_QT_KEYS.update({Qt.Key_0 + i: "KC_" + str(i) for i in range(10)})
_QT_KEYS.update({Qt.Key_F1 + i: "KC_F{}".format(i + 1) for i in range(24)})


def modifier_of(event):
    """The modifier bit a key event is for, or None if it is another key."""
    if event.key() not in _QT_MODS:
        return None
    if sys.platform == "win32":
        side = _SCAN_MODS.get(event.nativeScanCode())
        if side is not None:
            return side
    return _QT_MODS[event.key()]


def keycode_of(event):
    """The keyboard keycode ("KC_A") for a non-modifier key event, or None."""
    if event.modifiers() & Qt.KeypadModifier:
        keypad = {Qt.Key_Plus: "KC_KP_PLUS", Qt.Key_Minus: "KC_KP_MINUS", Qt.Key_Asterisk: "KC_KP_ASTERISK",
                  Qt.Key_Slash: "KC_KP_SLASH", Qt.Key_Period: "KC_KP_DOT", Qt.Key_Enter: "KC_KP_ENTER"}
        if event.key() in keypad:
            return keypad[event.key()]
    if sys.platform == "win32" and event.nativeVirtualKey() in _VK_KEYS:
        return _VK_KEYS[event.nativeVirtualKey()]
    return _QT_KEYS.get(event.key())


def mods_text(mods):
    return " + ".join(name for bit, name in enumerate(MOD_NAMES) if mods & (1 << bit))


def held_text(mods, fn=0):
    """"Fn 1 + LCtrl + LShift": the Fn keys first, then the modifiers."""
    names = [name for bit, name in enumerate(FN_NAMES) if fn & (1 << bit)]
    names += [name for bit, name in enumerate(MOD_NAMES) if mods & (1 << bit)]
    return " + ".join(names)


def _mix(a, b, amount):
    """Colour `a` moved `amount` (0..1) of the way to colour `b`."""
    return QColor(round(a.red() + (b.red() - a.red()) * amount),
                  round(a.green() + (b.green() - a.green()) * amount),
                  round(a.blue() + (b.blue() - a.blue()) * amount))


class ShortcutRecorder(QPushButton):

    recorded = pyqtSignal(int, str, int)    # modifier bits, keycode, Fn bits
    held_changed = pyqtSignal(int, int)     # while recording: the modifiers and Fn keys held so far
    stopped = pyqtSignal(str)               # recording ended without a shortcut: why ("" = cancelled)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.recording = False
        self.held = 0
        self.fn_held = 0
        self._fn_poll = None
        self._fn_timer = QTimer(self)
        self._fn_timer.setInterval(FN_POLL_MS)
        self._fn_timer.timeout.connect(self._poll_fn)
        self._pulse = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(PULSE_MS)
        self._pulse_timer.timeout.connect(self._on_pulse)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.clicked.connect(self.toggle)
        self._show_state()

    # ---- Fn 1 / Fn 2, read from the keyboard ----------------------------------

    def set_fn_poll(self, poll):
        """`poll()` returns the Fn keys held now (bit 0 = Fn 1, bit 1 = Fn 2),
        or None if it cannot tell just now (the last answer is kept). If it
        raises, the Fn keys are not watched for the rest of this recording.
        It is only ever called while recording."""
        self._fn_poll = poll

    def fn_watching(self):
        """True while the Fn keys are being read from the keyboard."""
        return self._fn_timer.isActive()

    def _read_fn(self):
        """One read of the Fn keys; False if they cannot be read at all."""
        if self._fn_poll is None:
            return False
        try:
            bits = self._fn_poll()
        except Exception:
            return False
        if bits is not None:
            self.fn_held = int(bits) & 0x3
        return True

    def _poll_fn(self):
        if not self.recording:
            self._fn_timer.stop()
            return
        before = self.fn_held
        if not self._read_fn():
            self._fn_timer.stop()
            self.fn_held = 0
        if self.fn_held != before:
            self.held_changed.emit(self.held, self.fn_held)

    # ---- recording -----------------------------------------------------------

    def _show_state(self):
        self.setText(tr("ShortcutRecorder", "Press the keys…") if self.recording
                     else tr("ShortcutRecorder", "Record"))
        self.setToolTip(tr("ShortcutRecorder", "Click again or press Esc to cancel") if self.recording
                        else tr("ShortcutRecorder", "Record the shortcut from the keys you press"))
        self.updateGeometry()
        self.update()

    def toggle(self):
        if self.recording:
            self.stop("")
        else:
            self.recording = True
            self.held = 0
            self.fn_held = 0
            self.setFocus()
            self.grabKeyboard()         # so Tab, Space, Enter and the rest come here too
            self._pulse = 0
            self._pulse_timer.start()
            if self._read_fn():
                self._fn_timer.start()
            else:
                self.fn_held = 0
            self._show_state()
            self.held_changed.emit(self.held, self.fn_held)

    def stop(self, reason=None):
        """End recording. `reason` is None when a shortcut was recorded."""
        self._fn_timer.stop()
        self._pulse_timer.stop()
        if not self.recording:
            return
        self.recording = False
        self.releaseKeyboard()
        self._show_state()
        if reason is not None:
            self.stopped.emit(reason)

    def event(self, event):
        # While recording, every key belongs to the shortcut: Tab must not move
        # the focus, and no key may set off one of the app's own shortcuts.
        if self.recording:
            if event.type() == QEvent.ShortcutOverride:
                event.accept()
                return True
            if event.type() == QEvent.KeyPress:
                self.keyPressEvent(event)
                return True
            if event.type() == QEvent.KeyRelease:
                self.keyReleaseEvent(event)
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        if not self.recording:
            return super().keyPressEvent(event)
        event.accept()
        if event.isAutoRepeat():
            return
        modifier = modifier_of(event)
        if modifier is not None:
            self.held |= 1 << modifier
            self.held_changed.emit(self.held, self.fn_held)
            return
        # The key that ends the recording. The Fn keys held are the ones last
        # seen, plus any seen right now (Fn pressed since the last look).
        fn = self.fn_held
        if self._fn_timer.isActive():
            self._read_fn()
            fn |= self.fn_held
        if event.key() == Qt.Key_Escape and not self.held and not fn:
            return self.stop("")
        if not self.held and not fn:
            # a key on its own is not a shortcut: recording just closes
            return self.stop(tr("ShortcutRecorder",
                                "Hold a modifier (Ctrl, Shift, Alt, Win, or Fn 1 / Fn 2 on the MIDIswitch) "
                                "and then press the key."))
        keycode = keycode_of(event)
        if keycode is None:
            return self.stop(tr("ShortcutRecorder", "That key cannot be recorded. Pick it from the keys below instead."))
        held = self.held
        self.stop()
        self.recorded.emit(held, keycode, fn)

    def keyReleaseEvent(self, event):
        if not self.recording:
            return super().keyReleaseEvent(event)
        event.accept()
        if event.isAutoRepeat():
            return
        modifier = modifier_of(event)
        if modifier is not None:
            self.held &= ~(1 << modifier)
            self.held_changed.emit(self.held, self.fn_held)

    def focusOutEvent(self, event):
        self.stop("")
        super().focusOutEvent(event)

    def hideEvent(self, event):
        self.stop("")
        super().hideEvent(event)

    # ---- looks: a big button with a red record dot ------------------------------

    MARK = 16           # diameter of the record dot
    PAD = 16

    def _text_font(self):
        font = QFont(self.font())
        font.setBold(True)
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() + 1.5)
        return font

    def sizeHint(self):
        metrics = QFontMetrics(self._text_font())
        widest = max(metrics.horizontalAdvance(tr("ShortcutRecorder", "Record")),
                     metrics.horizontalAdvance(tr("ShortcutRecorder", "Press the keys…")))
        return QSize(max(160, self.PAD + self.MARK + 10 + widest + self.PAD), max(44, metrics.height() + 22))

    def minimumSizeHint(self):
        return self.sizeHint()

    def _on_pulse(self):
        self._pulse = (self._pulse + 1) % 24
        self.update()

    def paintEvent(self, event):
        # the application's palette: the widget's own carries stylesheet gradients, not plain colours
        pal = QApplication.palette()
        enabled = self.isEnabled()
        group = QPalette.Active if enabled else QPalette.Disabled
        base = pal.color(group, QPalette.Button)
        text = pal.color(group, QPalette.ButtonText)
        red = RECORD_RED if enabled else _mix(RECORD_RED, base, 0.6)
        hover = enabled and self.underMouse()

        if self.recording:
            fill = _mix(base, RECORD_RED, 0.22)
            border, width = RECORD_RED, 2.5
        else:
            fill = _mix(base, text, 0.10 if self.isDown() else 0.05 if hover else 0.0)
            border = _mix(base, RECORD_RED, 0.75) if hover or self.hasFocus() else _mix(base, text, 0.45)
            width = 2.0 if hover or self.hasFocus() else 1.5

        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        half = width / 2.0
        frame = QRectF(self.rect()).adjusted(half, half, -half, -half)
        qp.setPen(QPen(border, width))
        qp.setBrush(fill)
        qp.drawRoundedRect(frame, 9, 9)

        font = self._text_font()
        qp.setFont(font)
        metrics = QFontMetrics(font)
        label = self.text()
        gap = 10
        total = self.MARK + gap + metrics.horizontalAdvance(label)
        x = max(self.PAD, (self.width() - total) / 2.0)
        cy = self.height() / 2.0

        # the mark: a red dot; while recording, a "stop" square that pulses
        qp.setPen(Qt.NoPen)
        if self.recording:
            phase = abs(self._pulse - 12) / 12.0          # 1 .. 0 .. 1
            glow = QColor(red)
            glow.setAlphaF(0.30 * phase)
            qp.setBrush(glow)
            qp.drawEllipse(QRectF(x - 5, cy - self.MARK / 2.0 - 5, self.MARK + 10, self.MARK + 10))
            mark = QColor(red)
            mark.setAlphaF(0.55 + 0.45 * phase)
            qp.setBrush(mark)
            side = self.MARK - 3
            qp.drawRoundedRect(QRectF(x + 1.5, cy - side / 2.0, side, side), 3, 3)
        else:
            ring = QColor(red)
            ring.setAlphaF(0.25)
            qp.setBrush(ring)
            qp.drawEllipse(QRectF(x - 3, cy - self.MARK / 2.0 - 3, self.MARK + 6, self.MARK + 6))
            qp.setBrush(red)
            qp.drawEllipse(QRectF(x, cy - self.MARK / 2.0, self.MARK, self.MARK))

        qp.setPen(text)
        qp.drawText(QRectF(x + self.MARK + gap, 0, self.width() - x - self.MARK - gap, self.height()),
                    Qt.AlignVCenter | Qt.AlignLeft, label)
        qp.end()
