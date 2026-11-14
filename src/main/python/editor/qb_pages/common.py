# SPDX-License-Identifier: GPL-2.0-or-later
"""What the QuickBuild editor pages share: the page frame (title, "Read from
keyboard", the firmware-too-old message, the status line), dropdowns and spin
boxes that do not change under a scrolling mouse wheel, a background loader for
long lists read from the keyboard, and the 28-voicing DrumLIVE grid."""

import re
from contextlib import contextmanager

from PyQt5.QtCore import Qt, QObject, QTimer, QEvent, QModelIndex, QPoint, pyqtSignal
from PyQt5.QtGui import QValidator
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
                             QComboBox, QSpinBox, QScrollArea, QStackedWidget, QGroupBox,
                             QCompleter, QFrame, QSizePolicy, QMenu, QSlider)

from editor.articulation_options import FACTORY_ARTIC_NAMES
from widgets.combo_box import ArrowComboBox
from util import tr

TITLE_STYLE = "font-weight: bold; font-size: 14pt;"
DESCRIPTION_STYLE = "color: palette(dark); font-size: 9pt;"
HINT_STYLE = "color: palette(dark); font-size: 9pt;"
SECTION_STYLE = "font-weight: bold; font-size: 11pt;"

NOTE_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
DRUM_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

SEQUENCED_VOICES = ["Kick", "Snare", "Closed HH", "Open HH", "Clap", "Rimshot", "Cowbell", "Cymbal",
                    "Low Tom", "Mid Tom", "Hi Tom", "Shaker"]
EXTRA_VOICES = ["Crash", "Crash 2", "Splash", "China", "Ride Bell", "Pedal HH", "Elec Snare",
                "Hi-Mid Tom", "Floor Tom L", "Floor Tom H", "Hi Bongo", "Lo Bongo", "Maracas",
                "Vibraslap", "Claves", "Triangle"]
DRUM_MODES = ["On", "Off", "Quiet", "Loud"]


def _t(text):
    return tr("QuickBuildPages", text)


class Combo(ArrowComboBox):
    """A dropdown that only follows the mouse wheel once it has been clicked,
    so scrolling the page never changes (and saves) a setting by accident."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(9)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def set_data(self, value, missing_label="{}"):
        """Select the row holding `value`; a value the list does not know is
        added so that what the keyboard holds is always shown as it is."""
        row = self.findData(value)
        if row < 0:
            self.addItem(missing_label.format(value), value)
            row = self.count() - 1
        self.setCurrentIndex(row)


class SearchCombo(Combo):
    """A dropdown for long lists: type part of a name to narrow it down."""

    def __init__(self, parent=None):
        super().__init__(parent)
        QComboBox.setEditable(self, True)       # not ArrowComboBox's: the text must stay typable
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMinimumContentsLength(24)
        completer = QCompleter(self.model(), self)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setMaxVisibleItems(14)
        self.setCompleter(completer)
        completer.activated[QModelIndex].connect(self._picked)
        self.lineEdit().editingFinished.connect(self._restore_text)
        self.lineEdit().installEventFilter(self)
        self.setToolTip(_t("Type part of a name to search, or open the list."))

    def mousePressEvent(self, event):
        QComboBox.mousePressEvent(self, event)

    def eventFilter(self, obj, event):
        if obj is self.lineEdit() and event.type() == QEvent.FocusIn:
            QTimer.singleShot(0, self._select_all)
        return super().eventFilter(obj, event)

    def _select_all(self):
        try:
            if self.lineEdit() is not None and self.lineEdit().hasFocus():
                self.lineEdit().selectAll()
        except RuntimeError:
            pass

    def _picked(self, index):
        try:
            source = self.completer().completionModel().mapToSource(index)
        except Exception:
            return
        if source.isValid():
            self.setCurrentIndex(source.row())

    def _restore_text(self):
        row = self.currentIndex()
        if row >= 0 and self.lineEdit().text() != self.itemText(row):
            self.lineEdit().setText(self.itemText(row))


class Spin(QSpinBox):
    """A number box that ignores the mouse wheel until it has been clicked and
    reports a typed number once, when it is finished."""

    def __init__(self, low, high, parent=None, step=1, suffix=""):
        super().__init__(parent)
        self.setRange(low, high)
        self.setSingleStep(step)
        if suffix:
            self.setSuffix(suffix)
        self.setKeyboardTracking(False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumWidth(84)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class SignedSpin(Spin):
    """Shows positive numbers with a plus sign (+3)."""

    def textFromValue(self, value):
        return "+{}".format(value) if value > 0 else str(value)

    def valueFromText(self, text):
        try:
            return int(text.replace("+", "").strip())
        except ValueError:
            return self.value()

    def validate(self, text, pos):
        if re.fullmatch(r"\s*[+-]?\d*\s*", text):
            state = QValidator.Intermediate
            try:
                if self.minimum() <= int(text.replace("+", "").strip()) <= self.maximum():
                    state = QValidator.Acceptable
            except ValueError:
                pass
            return state, text, pos
        return QValidator.Invalid, text, pos


def midi_note_name(note):
    """36 -> "C1" (middle C, 60, is C3)."""
    return "{}{}".format(DRUM_NOTE_NAMES[note % 12], note // 12 - 2)


class NoteSpin(Spin):
    """A MIDI note, shown with its name: "C1 (36)". Accepts a number or a name."""

    def __init__(self, parent=None):
        super().__init__(0, 127, parent)
        self.setMinimumWidth(104)

    def textFromValue(self, value):
        return "{} ({})".format(midi_note_name(value), value)

    def _parse(self, text):
        text = text.strip()
        match = re.search(r"\((\d+)\)?$", text) or re.fullmatch(r"(\d+)", text)
        if match:
            return int(match.group(1))
        match = re.fullmatch(r"([A-Ga-g])([#b]?)\s*(-?\d)", text)
        if match:
            base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[match.group(1).upper()]
            base += {"#": 1, "b": -1, "": 0}[match.group(2)]
            return base + (int(match.group(3)) + 2) * 12
        return None

    def valueFromText(self, text):
        value = self._parse(text)
        return self.value() if value is None else max(0, min(127, value))

    def validate(self, text, pos):
        value = self._parse(text)
        if value is not None and 0 <= value <= 127:
            return QValidator.Acceptable, text, pos
        return QValidator.Intermediate, text, pos

    def fixup(self, text):
        return self.textFromValue(self.value())


def factory_curve_combo():
    """The 23 built-in velocity curves (the ones a slot can use)."""
    combo = Combo()
    for index, name in enumerate(FACTORY_ARTIC_NAMES):
        combo.addItem(name, index)
    return combo


def channel_combo(first_is_master):
    """Channels 1-16; with "Master" first its data is 0 and channels are 1-16,
    without it the data is 0-15."""
    combo = Combo()
    if first_is_master:
        combo.addItem(_t("Master"), 0)
    for channel in range(1, 17):
        combo.addItem(_t("Channel {}").format(channel), channel if first_is_master else channel - 1)
    return combo


def left(widget):
    """A row holding `widget` at its own width, for forms whose fields would
    otherwise stretch a small number box across the page."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(widget)
    row.addStretch(1)
    return row


def hint_label(text=""):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(HINT_STYLE)
    return label


def section_label(text):
    label = QLabel(text)
    label.setStyleSheet(SECTION_STYLE)
    return label


def divider():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Plain)
    line.setStyleSheet("color: palette(mid);")
    return line


class Loader(QObject):
    """Reads a long list from the keyboard a few entries at a time so the
    window stays responsive. `fetch(index)` returns the entry or None; the first
    None stops the run (the keyboard has gone or refuses), `start` resumes it."""

    loaded = pyqtSignal(int)

    def __init__(self, parent, fetch, batch=8):
        super().__init__(parent)
        self._fetch = fetch
        self._batch = batch
        self.values = {}
        self.count = 0
        self._next = 0
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._tick)

    def reset(self):
        self._timer.stop()
        self.values = {}
        self.count = 0
        self._next = 0

    def stop(self):
        self._timer.stop()

    def start(self, count):
        self.count = count
        self._next = 0
        # (entries past `count` can be known too, read one at a time with get())
        if any(index not in self.values for index in range(count)):
            self._timer.start()

    def running(self):
        return self._timer.isActive()

    def get(self, index, refresh=False):
        """The entry now (asking the keyboard if it is not known yet)."""
        if refresh or index not in self.values:
            try:
                value = self._fetch(index)
            except Exception:
                value = None
            if value is None:
                return self.values.get(index) if not refresh else None
            self.values[index] = value
            self.loaded.emit(index)
        return self.values[index]

    def put(self, index, value):
        self.values[index] = value
        self.loaded.emit(index)

    def _tick(self):
        done = 0
        while done < self._batch:
            while self._next < self.count and self._next in self.values:
                self._next += 1
            if self._next >= self.count:
                self._timer.stop()
                return
            index = self._next
            try:
                value = self._fetch(index)
            except Exception:
                value = None
            if value is None:
                self._timer.stop()
                return
            self.values[index] = value
            self._next += 1
            done += 1
            self.loaded.emit(index)


class ModeGrid(QWidget):
    """The 28 DrumLIVE voicings, each On / Off / Quiet / Loud."""

    changed = pyqtSignal()
    COLUMNS = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._quiet = False
        self.combos = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for title, names in ((_t("Pattern voices"), SEQUENCED_VOICES), (_t("Extra voices"), EXTRA_VOICES)):
            box = QGroupBox(title)
            grid = QGridLayout(box)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(6)
            for i, name in enumerate(names):
                row, column = divmod(i, self.COLUMNS)
                label = QLabel(_t(name))
                label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                label.setMinimumWidth(76)
                combo = Combo()
                combo.setMinimumContentsLength(5)
                for mode in DRUM_MODES:
                    combo.addItem(_t(mode))
                combo.currentIndexChanged.connect(self._on_changed)
                label.setBuddy(combo)
                grid.addWidget(label, row, column * 2)
                grid.addWidget(combo, row, column * 2 + 1)
                grid.setColumnStretch(column * 2 + 1, 1)
                self.combos.append(combo)
            layout.addWidget(box)

    def _on_changed(self, _index):
        if not self._quiet:
            self.changed.emit()

    def modes(self):
        return [combo.currentIndex() for combo in self.combos]

    def set_modes(self, modes):
        self._quiet = True
        try:
            for combo, mode in zip(self.combos, modes):
                combo.setCurrentIndex(mode & 3)
        finally:
            self._quiet = False


class QbPage(QWidget):
    """The frame every page shares. A page fills in `build(layout)`, `load()`
    (read everything it shows; return False if the keyboard did not answer) and
    `forget()` (drop what was read)."""

    TITLE = ""
    DESCRIPTION = ""
    UPDATE_MESSAGE = "Update the keyboard's firmware to edit this here."

    def __init__(self, parent=None):
        super().__init__(parent)
        self.app_config = None
        self._loaded = False
        self._tried = False         # a read was tried since the page was last shown / given a keyboard
        self._loading = False
        self._quiet = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        self._message = QLabel(_t(self.UPDATE_MESSAGE))
        self._message.setAlignment(Qt.AlignCenter)
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color: palette(dark); font-size: 11pt;")
        self._stack.addWidget(self._message)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        scroll.setWidget(body)
        self._stack.addWidget(scroll)

        title = QLabel(_t(self.TITLE))
        title.setStyleSheet(TITLE_STYLE)
        layout.addWidget(title)
        description = QLabel(_t(self.DESCRIPTION))
        description.setWordWrap(True)
        description.setStyleSheet(DESCRIPTION_STYLE)
        layout.addWidget(description)

        top = QHBoxLayout()
        self.read_button = QPushButton(_t("Read from keyboard"))
        self.read_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.read_button.clicked.connect(self.reload)
        top.addWidget(self.read_button)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        top.addWidget(self.status_label, 1)
        layout.addLayout(top)

        self.build(layout)
        layout.addStretch(1)
        self._stack.setCurrentIndex(0)

    # ---- what a page provides ---------------------------------------------------

    def build(self, layout):
        raise NotImplementedError

    def load(self):
        raise NotImplementedError

    def forget(self):
        pass

    # ---- what the host calls ----------------------------------------------------

    def set_app_config(self, app_config):
        self.app_config = app_config
        self._loaded = False
        with self.quiet():
            try:
                self.forget()
            except Exception:
                pass
        self.set_status("")
        self._tried = False
        if app_config is None:
            self._stack.setCurrentIndex(0)
        elif self.isVisible():
            self.shown()

    def shown(self):
        """The page has come into view: read the keyboard if that has not been
        done since it was given (set_app_config). The page does this itself
        whenever it is shown (showEvent), so a host does not have to call it;
        one that does costs nothing, as a read is tried once per showing."""
        if not self.usable():
            self._stack.setCurrentIndex(0)
            return
        self._stack.setCurrentIndex(1)
        if not self._loaded and not self._tried and not self._loading:
            self._tried = True
            self.reload()

    def showEvent(self, event):
        super().showEvent(event)
        # A keyboard given while the page was out of view (set_app_config
        # reads only when it is on show) is read now, whoever shows the page.
        if self.app_config is not None and not self._loaded:
            self.shown()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._tried = False         # a read that failed is tried again on the next showing

    # ---- helpers ----------------------------------------------------------------

    def usable(self):
        config = self.app_config
        if config is None:
            return False
        try:
            return bool(config.supported())
        except Exception:
            return False

    def reload(self):
        if not self.usable():
            self._stack.setCurrentIndex(0)
            return
        if self._loading:
            return
        ok = False
        self._loading = True
        try:
            with self.quiet():
                try:
                    ok = self.load() is not False
                except Exception:
                    ok = False
        finally:
            self._loading = False
        self._loaded = ok
        if ok:
            self.set_status(_t("Read from the keyboard."))
        else:
            self.set_status(_t("The keyboard did not answer. Check the connection, then press "
                               "Read from keyboard."), problem=True)

    @contextmanager
    def quiet(self):
        """Controls changed inside this block do not count as the user's edits."""
        self._quiet += 1
        try:
            yield
        finally:
            self._quiet -= 1

    def is_quiet(self):
        return self._quiet > 0

    def ready(self):
        """True when a control change is the user's and there is a keyboard to tell."""
        return self._quiet == 0 and self.app_config is not None

    def call(self, name, *args):
        """One AppConfig helper; None if there is no keyboard or anything goes wrong."""
        config = self.app_config
        if config is None:
            return None
        try:
            return getattr(config, name)(*args)
        except Exception:
            return None

    def set_status(self, text, problem=False):
        self.status_label.setStyleSheet("font-weight: bold;" if problem else HINT_STYLE)
        self.status_label.setText(text)

    def refused(self):
        self.set_status(_t("The keyboard refused that change."), problem=True)

    def saved(self):
        self.set_status(_t("Saved to the keyboard."))


class CategoryCombo(Combo):
    """A dropdown for long lists that the keyboard's own menus sort into
    categories: a click anywhere opens a menu with one sub-menu per category.
    A category is a name, a tuple of names (a sub-menu inside a sub-menu) or
    None for an entry at the top of the menu."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumContentsLength(24)
        self._entries = []          # (path, data) in the order they were added
        self._labels = {}
        self._value = None
        self._menu = None
        QComboBox.addItem(self, "")     # the one row shows the current entry

    def add_item(self, category, label, data):
        if not category:
            path = ()
        elif isinstance(category, str):
            path = (category,)
        else:
            path = tuple(category)
        self._entries.append((path, data))
        self._labels[data] = label

    def clear(self):
        self._entries = []
        self._labels = {}
        self._value = None
        self.setItemText(0, "")
        self.setItemData(0, None)

    def item_count(self):
        return len(self._labels)

    def set_label(self, data, label):
        if data in self._labels:
            self._labels[data] = label
            if data == self._value:
                self.setItemText(0, label)

    def current_data(self):
        return self._value

    def set_data(self, value, missing_label="{}"):
        """Show `value`; one the list does not know is added under "Other" so
        that what the keyboard holds is always shown as it is."""
        if value not in self._labels:
            self.add_item(_t("Other"), missing_label.format(value), value)
        self._value = value
        self.setItemText(0, self._labels[value])
        self.setItemData(0, value)

    def build_menu(self):
        menu = QMenu(self)
        menus = {(): menu}
        bold = menu.font()
        bold.setBold(True)
        for path, data in self._entries:
            for depth in range(1, len(path) + 1):
                if path[:depth] not in menus:
                    menus[path[:depth]] = menus[path[:depth - 1]].addMenu(path[depth - 1].replace("&", "&&"))
            action = menus[path].addAction(self._labels[data].replace("&", "&&"))
            action.setData(data)
            action.triggered.connect(lambda _checked=False, data=data: self._pick(data))
            if data == self._value:     # the current entry and the way to it stand out
                action.setFont(bold)
                for depth in range(1, len(path) + 1):
                    menus[path[:depth]].menuAction().setFont(bold)
        return menu

    def showPopup(self):
        if not self._entries:
            return
        if self._menu is not None:
            self._menu.deleteLater()
        self._menu = self.build_menu()
        self._menu.setMinimumWidth(self.width())
        self._menu.popup(self.mapToGlobal(QPoint(0, self.height())))

    def hidePopup(self):
        if self._menu is not None:
            self._menu.close()

    def wheelEvent(self, event):
        event.ignore()

    def _pick(self, data):
        if data == self._value:
            return
        self.set_data(data)
        self.changed.emit()


class _Slider(QSlider):
    """Ignores the mouse wheel until it has been clicked."""

    focus_lost = pyqtSignal()

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focus_lost.emit()


class ValueSlider(QWidget):
    """A horizontal slider with its value beside it. `changed` is sent once the
    slider is let go (or shortly after a key or wheel step), not while it moves."""

    changed = pyqtSignal(int)

    def __init__(self, low, high, parent=None, width=150):
        super().__init__(parent)
        self.slider = _Slider(Qt.Horizontal)
        self.slider.setRange(low, high)
        self.slider.setPageStep(max(1, (high - low) // 10))
        self.slider.setFocusPolicy(Qt.StrongFocus)
        self.slider.setFixedWidth(width)
        self.label = QLabel(str(low))
        self.label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.label.setFixedWidth(self.label.fontMetrics().horizontalAdvance("0" * len(str(high))) + 6)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(self.slider)
        row.addWidget(self.label)
        self.setFocusProxy(self.slider)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._sent = low
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._send)
        self.slider.valueChanged.connect(self._on_moved)
        self.slider.sliderReleased.connect(self._send)
        self.slider.focus_lost.connect(self._send)

    def value(self):
        return self.slider.value()

    def setValue(self, value):
        """Show a value read from the keyboard; this is not the user's edit."""
        self._timer.stop()
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self.label.setText(str(self.slider.value()))
        self._sent = self.slider.value()

    def _on_moved(self, value):
        self.label.setText(str(value))
        if not self.slider.isSliderDown():
            self._timer.start()

    def _send(self):
        self._timer.stop()
        if self.slider.isSliderDown() or self.slider.value() == self._sent:
            return
        self._sent = self.slider.value()
        self.changed.emit(self._sent)
