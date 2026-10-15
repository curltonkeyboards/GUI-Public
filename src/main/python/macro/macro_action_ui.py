from PyQt5.QtCore import QObject, pyqtSignal, Qt, QTimer
from PyQt5.QtWidgets import (QLineEdit, QToolButton, QWidget, QSizePolicy, QSpinBox, QComboBox,
                              QLabel, QHBoxLayout, QVBoxLayout, QCheckBox)

from constants import KEY_SIZE_RATIO
from widgets.flowlayout import FlowLayout
from widgets.combo_box import ArrowComboBox, ArrowSpinBox
from macro.macro_action import (text_to_actions, ActionText, ActionSequence, ActionDown, ActionUp, ActionTap,
                                ActionDelay, ActionBPMDelay,
                                ActionMixingControl, MIXING_CURRENT_VALUE,
                                ActionMouseMove, MOUSE_COORD_MAX, MOUSE_CLICK_NONE,
                                MOUSE_CLICK_LEFT, MOUSE_CLICK_DOUBLE, MOUSE_CLICK_RIGHT,
                                ActionGamepad, GAMEPAD_BUTTONS, GAMEPAD_DIRECTIONS, GAMEPAD_MS_MAX,
                                GAMEPAD_TAP, GAMEPAD_PRESS, GAMEPAD_RELEASE, GAMEPAD_TRIGGER,
                                GAMEPAD_TRIGGER_RELEASE, GAMEPAD_STICK, GAMEPAD_STICK_RELEASE,
                                GAMEPAD_DEFAULT_DURATION, GAMEPAD_TAP_DEFAULT_DURATION)
from widgets.keycode_button import (KeycodeButton, DropGap, reorder_list, keycode_button_px,
                                    drag_accepted_from, palette_keycode_from)


class MacroKeyWidget(KeycodeButton):
    """Keycode button for a macro sequence - same look as the palette buttons.
    Doesn't open the tray: the MacroRecorder feeds the palette pick to the
    selected button."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def keyReleaseEvent(self, ev):
        # remove this keycode from the sequence when delete is pressed
        if ev.key() == Qt.Key_Delete:
            self.set_keycode(0)
        else:
            super().keyReleaseEvent(ev)


class DeletableKeyWidget(MacroKeyWidget):
    """MacroKeyWidget with a small red X overlay at top-right for removal"""

    remove_clicked = pyqtSignal(object)  # Emits self when X is clicked

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Small red X button overlaid at top-right
        self.btn_x = QToolButton(self)
        self.btn_x.setText("\u00d7")
        self.btn_x.setFixedSize(14, 14)
        self.btn_x.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_x.setStyleSheet("""
            QToolButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 3px;
                font-weight: bold;
                font-size: 9px;
                padding: 0px;
            }
            QToolButton:hover { background-color: #c82333; }
        """)
        self.btn_x.clicked.connect(lambda: self.remove_clicked.emit(self))
        self.btn_x.raise_()
        self._position_x_button()

    def _position_x_button(self):
        """Position X button at top-right of the button"""
        self.btn_x.move(max(0, self.width() - self.btn_x.width() - 2), 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_x_button()


class PlusDropButton(QToolButton):
    """The sequence's "+" button, also a drop target: dropping a key button of
    the same drag group on it appends that key to this sequence."""

    dropped = pyqtSignal(object)  # the dropped KeycodeButton
    hovered = pyqtSignal(object)  # a drag of the group hovers "+" (append position)
    insert_dropped = pyqtSignal(str)  # a palette key was dropped on "+": append it

    keeps_key_selection = True   # adding a key must not clear the selection

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.drag_group = None
        self.keycode_filter = None   # gate for palette drops (None = accept any)
        self.setAcceptDrops(True)

    def _drag_accepted(self, ev):
        return drag_accepted_from(ev, self.drag_group)

    def dragEnterEvent(self, ev):
        if self._drag_accepted(ev):
            ev.setDropAction(Qt.MoveAction)
            ev.accept()
            self.hovered.emit(ev.source())
        elif palette_keycode_from(ev, self.keycode_filter):
            ev.setDropAction(Qt.CopyAction)
            ev.accept()
            self.hovered.emit(ev.source())
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        self.dragEnterEvent(ev)

    def dropEvent(self, ev):
        if self._drag_accepted(ev):
            ev.setDropAction(Qt.MoveAction)
            ev.accept()
            self.dropped.emit(ev.source())
            return
        qmk_id = palette_keycode_from(ev, self.keycode_filter)
        if qmk_id:
            ev.setDropAction(Qt.CopyAction)
            ev.accept()
            self.insert_dropped.emit(qmk_id)
            return
        ev.ignore()


class BasicActionUI(QObject):

    changed = pyqtSignal()
    key_selected = pyqtSignal(object)  # Emits the selected key widget
    # A key button from ANOTHER action of the same drag group was dropped on
    # this action: (source button, this action UI, insert index).  The owner of
    # the group (the macro tab) performs the move once the drag has finished.
    cross_move_requested = pyqtSignal(object, object, int)
    # Replace this line with these actions (the "Type Text" line generating its keys).
    expand_requested = pyqtSignal(object)
    actcls = None

    def __init__(self, container, act=None):
        super().__init__()
        self.container = container
        if act is None:
            act = self.actcls()
        if not isinstance(act, self.actcls):
            raise RuntimeError("{} was initialized with {}, expecting {}".format(self, act, self.actcls))
        self.act = act

    def set_keycode_filter(self, keycode_filter):
        pass

    def set_drag_group(self, group):
        """Object whose key buttons may be dragged onto each other (the macro
        tab, so keys move between action lines).  No-op for non-key actions."""
        pass


class ActionTextUI(BasicActionUI):
    """"Type Text" line: the user types text and presses Generate Keys (or
    Enter); the line is replaced by the Keypress / Hold / Release lines that
    type it (text_to_actions). Raw text is never stored in a macro — anything
    left in the box is converted the same way when the macro is saved."""

    actcls = ActionText

    def __init__(self, container, act=None):
        super().__init__(container, act)
        self.widget = QWidget()
        lay = QHBoxLayout(self.widget)
        lay.setContentsMargins(0, 0, 0, 0)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Type text, then Generate Keys")
        self.text.setText(self.act.text)
        self.text.textChanged.connect(self.on_change)
        self.text.returnPressed.connect(self.on_generate)
        self.btn_generate = QToolButton()
        self.btn_generate.setText("Generate Keys")
        self.btn_generate.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_generate.clicked.connect(self.on_generate)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.btn_generate)

    def insert(self, row):
        self.container.addWidget(self.widget, row, 3)

    def remove(self):
        self.container.removeWidget(self.widget)

    def delete(self):
        self.widget.deleteLater()

    def on_change(self):
        self.act.text = self.text.text()
        self.changed.emit()

    def on_generate(self):
        actions, skipped = text_to_actions(self.text.text())
        if skipped:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self.widget, "Type Text",
                                "These characters have no key and were left out: "
                                + " ".join(sorted(set(skipped))))
        if not actions:
            return
        # The button that fired this belongs to the line being replaced:
        # replace it on the next event-loop pass.
        QTimer.singleShot(0, lambda: self.expand_requested.emit(actions))


def _make_thruloop_combo():
    """Create a combo box styled like ThruLoop dropdowns - restricted height, scrollbar"""
    combo = ArrowComboBox()
    combo.setMaximumHeight(30)
    combo.setEditable(True)
    combo.lineEdit().setReadOnly(True)
    combo.lineEdit().setAlignment(Qt.AlignCenter)
    return combo


class ActionSequenceUI(BasicActionUI):

    actcls = ActionSequence

    def __init__(self, container, act=None):
        super().__init__(container, act)

        # Square + button matching the key buttons' size (also a drop target
        # that appends a dragged key to this sequence)
        self.btn_plus = PlusDropButton()
        self.btn_plus.setText("+")
        self.btn_plus.dropped.connect(self.on_plus_drop)
        self.btn_plus.hovered.connect(self._on_plus_hover)
        self.btn_plus.insert_dropped.connect(lambda kc: self.on_insert_keycode(kc, None, True))
        plus_size = keycode_button_px(self.btn_plus.fontMetrics())
        self.btn_plus.setFixedWidth(plus_size)
        self.btn_plus.setFixedHeight(plus_size)
        self.btn_plus.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_plus.clicked.connect(self.on_add)

        # skip_hidden: the key being dragged is hidden for the drag, and its
        # slot must collapse so the DropGap shows the true post-drop row
        self.layout = FlowLayout(skip_hidden=True)
        self.layout_container = QWidget()
        self.layout_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.layout_container.setLayout(self.layout)
        self.widgets = []
        self.keycode_filter = None
        # The "push" preview: an empty slot inserted where a hovering drag
        # would drop, so the neighbours slide aside (see DropGap)
        self.gap = DropGap()
        self.gap.dropped.connect(self.on_reorder_widget)
        self.gap.inserted.connect(self.on_insert_keycode)
        self._gap_slot = None
        # Until the owner installs a wider group, keys only move within this line
        self.drag_group = self
        self.btn_plus.drag_group = self
        self.gap.drag_group = self
        self.recreate_sequence()

    def set_keycode_filter(self, keycode_filter):
        if keycode_filter != self.keycode_filter:
            self.keycode_filter = keycode_filter
            self.gap.keycode_filter = keycode_filter
            self.btn_plus.keycode_filter = keycode_filter
            for w in self.widgets:
                w.set_keycode_filter(self.keycode_filter)

    def set_drag_group(self, group):
        if group is None:
            group = self
        self.drag_group = group
        self.btn_plus.drag_group = group
        self.gap.drag_group = group
        for w in self.widgets:
            w.set_drag_group(group)

    def recreate_sequence(self):
        self.gap.close()
        self.layout.removeWidget(self.gap)
        self.layout.removeWidget(self.btn_plus)
        for w in self.widgets:
            self.layout.removeWidget(w)
            w.deleteLater()
        self.widgets.clear()

        for kc in self.act.sequence:
            w = DeletableKeyWidget(self.keycode_filter)
            w.set_keycode(kc)
            w.changed.connect(self.on_change)
            w.selected.connect(self._on_key_selected)
            w.remove_clicked.connect(self.on_remove_widget)
            # Buttons of the drag group (this line, or every line of the macro)
            # can be dragged onto each other to reorder / move, and
            # right-click -> Duplicate copies one next to itself
            w.set_drag_group(self.drag_group)
            w.reorder_requested.connect(self.on_reorder_widget)
            w.duplicate_requested.connect(self.on_duplicate_widget)
            w.drop_hover.connect(self._on_drop_hover)
            w.insert_requested.connect(self.on_insert_keycode)
            self.layout.addWidget(w)
            self.widgets.append(w)
        self.layout.addWidget(self.btn_plus)

    def _on_key_selected(self, widget):
        """Handle key widget selection - bubble up to parent"""
        self.key_selected.emit(widget)

    def insert(self, row):
        self.container.addWidget(self.layout_container, row, 3)

    def remove(self):
        self.container.removeWidget(self.layout_container)

    def delete(self):
        for w in self.widgets:
            w.deleteLater()
        self.btn_plus.deleteLater()
        self.gap.deleteLater()
        self.layout_container.deleteLater()

    # ---- drop preview ("push" the neighbours aside) ----------------------

    def _on_drop_hover(self, source, target, before):
        """A drag of the group hovers one of this line's keys: open the gap
        on that side of it."""
        if target in self.widgets:
            self._open_gap(source, target, before)

    def _on_plus_hover(self, source):
        """A drag hovers the "+": the key would be appended — gap at the end."""
        vis = [w for w in self.widgets if not w.isHidden()]
        if vis:
            self._open_gap(source, vis[-1], False)
        else:
            self._open_gap(source, None, True)   # the line has no other key

    def _open_gap(self, source, target, before):
        """Insert the DropGap into the flow where a drop on (target, before)
        would land the key.  Slots are counted over the VISIBLE keys (the one
        being dragged is hidden), so "after A" and "before B" — the same
        place — don't re-open the gap and restart its animation."""
        vis = [w for w in self.widgets if not w.isHidden()]
        if target is None:
            slot = 0
        elif target in vis:
            slot = vis.index(target) + (0 if before else 1)
        else:
            return
        if self.gap.is_open() and self._gap_slot == slot:
            self.gap.target, self.gap.before = target, before   # equivalent position
            return
        self._gap_slot = slot
        self.layout.removeWidget(self.gap)
        anchor = vis[slot] if slot < len(vis) else self.btn_plus
        self.layout.insertWidget(self.layout.indexOf(anchor), self.gap)
        # a palette button is smaller than an editor key: size the slot like ours
        size = source.sizeHint() if isinstance(source, KeycodeButton) else self.btn_plus.sizeHint()
        self.gap.open_at(target, before, size)

    def on_insert_keycode(self, qmk_id, target, before):
        """A key dragged from the palette was dropped on this line (on a key,
        in the gap, or on "+"): insert it at that position.  The buttons are
        rebuilt on the next event-loop pass — the drop is still being delivered
        to one of them."""
        if target is None or target not in self.widgets:
            idx = len(self.act.sequence)
        else:
            idx = self.widgets.index(target) + (0 if before else 1)
        self.act.sequence.insert(idx, qmk_id)
        self.gap.close()
        QTimer.singleShot(0, self._rebuild_and_select(idx))
        self.changed.emit()

    def _rebuild_and_select(self, idx):
        def go():
            self.recreate_sequence()
            if 0 <= idx < len(self.widgets):
                self.widgets[idx].selected.emit(self.widgets[idx])
        return go

    def on_add(self):
        self.act.sequence.append("KC_TRNS")
        self.recreate_sequence()
        self.changed.emit()

    def on_remove_widget(self, widget):
        """Remove a specific keycode widget by its X button"""
        try:
            idx = self.widgets.index(widget)
            del self.act.sequence[idx]
            self.recreate_sequence()
            self.changed.emit()
        except ValueError:
            pass

    def on_reorder_widget(self, source, target, before):
        """A key button was dropped onto one of this sequence's buttons.

        From this same line: move it there.  The widgets are kept (the drop is
        delivered while the drag's own event loop is still running, so none of
        them may be destroyed here); only the keycodes are re-dealt onto them
        in the new order.

        From another line of the macro: hand the move to the group owner (the
        macro tab), which rebuilds both lines once the drag has finished."""
        if target is None:
            # dropped in the gap of a line with no other key: append
            self.on_plus_drop(source)
            return
        try:
            dst_idx = self.widgets.index(target)
        except ValueError:
            return
        if source not in self.widgets:
            self.cross_move_requested.emit(source, self, dst_idx if before else dst_idx + 1)
            return
        src_idx = self.widgets.index(source)
        if src_idx == dst_idx:
            return
        new_idx = reorder_list(self.act.sequence, src_idx, dst_idx, before)
        self._redeal_keycodes(source.is_selected, new_idx)

    def on_plus_drop(self, source):
        """A key button was dropped on the "+" button: append it to this line."""
        if source not in self.widgets:
            self.cross_move_requested.emit(source, self, len(self.act.sequence))
            return
        src_idx = self.widgets.index(source)
        last = len(self.act.sequence) - 1
        if src_idx == last:
            return
        new_idx = reorder_list(self.act.sequence, src_idx, last, False)
        self._redeal_keycodes(source.is_selected, new_idx)

    def _redeal_keycodes(self, was_selected, new_idx):
        """Write the (reordered) sequence back onto the existing buttons."""
        for w, kc in zip(self.widgets, self.act.sequence):
            w.blockSignals(True)
            w.set_keycode(kc)
            w.blockSignals(False)
        if was_selected:
            # keep the selection on the key that was dragged
            self.widgets[new_idx].selected.emit(self.widgets[new_idx])
        self.changed.emit()

    def on_duplicate_widget(self, widget):
        """Right-click -> Duplicate: insert a copy right after this key"""
        try:
            idx = self.widgets.index(widget)
        except ValueError:
            return
        self.act.sequence.insert(idx + 1, self.act.sequence[idx])
        self.recreate_sequence()
        self.changed.emit()

    def on_change(self):
        for x in range(len(self.act.sequence)):
            if x >= len(self.widgets):
                break
            kc = self.widgets[x].keycode
            if kc == 0:
                # asked to remove this item
                del self.act.sequence[x]
                self.recreate_sequence()
                break
            else:
                self.act.sequence[x] = kc
        self.changed.emit()


class ActionDownUI(ActionSequenceUI):
    actcls = ActionDown


class ActionUpUI(ActionSequenceUI):
    actcls = ActionUp


class ActionTapUI(ActionSequenceUI):
    actcls = ActionTap


class ActionDelayUI(BasicActionUI):

    actcls = ActionDelay

    def __init__(self, container, act=None):
        super().__init__(container, act)
        self.value = ArrowSpinBox()
        self.value.setMinimum(0)
        self.value.setMaximum(64000)  # up to 64s
        self.value.setValue(self.act.delay)
        self.value.valueChanged.connect(self.on_change)

        self.layout = FlowLayout()
        self.layout_container = QWidget()
        self.layout_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.layout_container.setLayout(self.layout)

        self.layout.addWidget(self.value)

    def insert(self, row):
        self.container.addWidget(self.layout_container, row, 3)

    def remove(self):
        self.container.removeWidget(self.layout_container)

    def delete(self):
        self.value.deleteLater()
        self.layout_container.deleteLater()

    def on_change(self):
        self.act.delay = self.value.value()
        self.changed.emit()


class ActionBPMDelayUI(BasicActionUI):

    actcls = ActionBPMDelay

    # Extended note values: indices 0-4 = original (1/1..1/16), 5-8 = multi-bar (2/1..16/1)
    NOTE_DISPLAY_ORDER = [
        (8, "16/1"), (7, "8/1"), (6, "4/1"), (5, "2/1"),
        (0, "1/1"), (1, "1/2"), (2, "1/4"), (3, "1/8"), (4, "1/16")
    ]

    def __init__(self, container, act=None):
        super().__init__(container, act)

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self.layout_container = QWidget()
        self.layout_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        self.layout.addWidget(QLabel("Rate:"))
        self.note_combo = _make_thruloop_combo()
        for _, label in self.NOTE_DISPLAY_ORDER:
            self.note_combo.addItem(label)
        # Find display index for current note_value
        display_idx = next((i for i, (val, _) in enumerate(self.NOTE_DISPLAY_ORDER)
                           if val == self.act.note_value), 4)  # default to 1/1
        self.note_combo.setCurrentIndex(display_idx)
        self.note_combo.setMinimumWidth(70)
        self.note_combo.currentIndexChanged.connect(self.on_note_change)
        self.layout.addWidget(self.note_combo)

        self.layout_container.setLayout(self.layout)

    def insert(self, row):
        self.container.addWidget(self.layout_container, row, 3)

    def remove(self):
        self.container.removeWidget(self.layout_container)

    def delete(self):
        self.note_combo.deleteLater()
        self.layout_container.deleteLater()

    def on_note_change(self):
        display_idx = self.note_combo.currentIndex()
        self.act.note_value = self.NOTE_DISPLAY_ORDER[display_idx][0]
        self.act.timing_mode = 0  # Always straight
        self.changed.emit()


class ActionMixingControlUI(BasicActionUI):

    actcls = ActionMixingControl

    def __init__(self, container, act=None):
        super().__init__(container, act)

        self._initializing = True  # Guard against on_change during init

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(2)
        self.layout_container = QWidget()
        self.layout_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        # CC Number
        lbl_cc = QLabel("CC#")
        self.layout.addWidget(lbl_cc)
        self.cc_spin = ArrowSpinBox()
        self.cc_spin.setMinimum(0)
        self.cc_spin.setMaximum(127)
        self.cc_spin.setValue(self.act.cc_num)
        self.cc_spin.setFixedWidth(60)
        self.cc_spin.valueChanged.connect(self.on_change)
        self.layout.addWidget(self.cc_spin)

        self.layout.addSpacing(10)

        # Channel
        lbl_ch = QLabel("Channel")
        self.layout.addWidget(lbl_ch)
        self.channel_combo = _make_thruloop_combo()
        self.channel_combo.addItem("Master Channel (default)")
        for i in range(1, 17):
            self.channel_combo.addItem(str(i))
        self.channel_combo.setCurrentIndex(self.act.channel)
        self.channel_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.channel_combo.currentIndexChanged.connect(self.on_change)
        self.layout.addWidget(self.channel_combo)

        self.layout.addSpacing(10)

        # Start value (dropdown with Live Value + 0-127)
        lbl_start = QLabel("Starting Value:")
        self.layout.addWidget(lbl_start)
        self.start_combo = _make_thruloop_combo()
        self.start_combo.addItem("Live Value")
        for i in range(128):
            self.start_combo.addItem(str(i))
        if self.act.start_val == MIXING_CURRENT_VALUE:
            self.start_combo.setCurrentIndex(0)
        else:
            self.start_combo.setCurrentIndex(self.act.start_val + 1)
        self.start_combo.setFixedWidth(80)
        self.start_combo.currentIndexChanged.connect(self.on_start_change)
        self.layout.addWidget(self.start_combo)

        self.layout.addSpacing(10)

        # End value (dropdown with conditional Live Value + 0-127)
        lbl_end = QLabel("End Value:")
        self.layout.addWidget(lbl_end)
        self.end_combo = _make_thruloop_combo()
        self._rebuild_end_combo()
        self.end_combo.setFixedWidth(80)
        self.end_combo.currentIndexChanged.connect(self.on_change)
        self.layout.addWidget(self.end_combo)

        self.layout.addSpacing(10)

        # Duration - defaults to BPM, with "Unsynced (ms)" checkbox to switch
        lbl_dur = QLabel("Duration")
        self.layout.addWidget(lbl_dur)

        # Duration value (BPM mode) - shown by default
        self.dur_note_combo = _make_thruloop_combo()
        for _, label in ActionBPMDelayUI.NOTE_DISPLAY_ORDER:
            self.dur_note_combo.addItem(label)
        self.dur_note_combo.setFixedWidth(60)
        self.dur_note_combo.currentIndexChanged.connect(self.on_change)
        self.layout.addWidget(self.dur_note_combo)

        # Duration value (ms mode) - hidden by default
        self.dur_ms_spin = ArrowSpinBox()
        self.dur_ms_spin.setMinimum(20)
        self.dur_ms_spin.setMaximum(64000)
        self.dur_ms_spin.setSingleStep(100)
        if self.act.duration_type == 0:
            self.dur_ms_spin.setValue(self.act.duration)
        else:
            self.dur_ms_spin.setValue(1000)
        self.dur_ms_spin.setFixedWidth(75)
        self.dur_ms_spin.valueChanged.connect(self.on_change)
        self.layout.addWidget(self.dur_ms_spin)

        self.dur_ms_cb = QCheckBox("Unsynced (ms)")
        self.dur_ms_cb.stateChanged.connect(self._on_dur_ms_toggle)
        self.layout.addWidget(self.dur_ms_cb)

        # Push everything left so widgets don't stretch across the row
        self.layout.addStretch()

        # Restore BPM params if in BPM mode
        if self.act.duration_type == 1:
            note_val = (self.act.duration >> 8) & 0xFF
            display_idx = next((i for i, (val, _) in enumerate(ActionBPMDelayUI.NOTE_DISPLAY_ORDER)
                               if val == note_val), 4)
            self.dur_note_combo.setCurrentIndex(display_idx)
            self.dur_ms_cb.setChecked(False)
        else:
            # ms mode - check the box
            self.dur_ms_cb.setChecked(True)

        # Default BPM note to 1/1 for new actions (index 4 in NOTE_DISPLAY_ORDER)
        if not act:
            self.dur_note_combo.setCurrentIndex(4)

        self._update_dur_visibility()
        self.layout_container.setLayout(self.layout)
        self._initializing = False

    def _rebuild_end_combo(self):
        """Rebuild end combo - 'Live Value' not allowed if start is 'Live Value'"""
        self.end_combo.blockSignals(True)
        old_val = self.act.end_val
        self.end_combo.clear()
        start_is_current = (self.start_combo.currentIndex() == 0)
        if not start_is_current:
            self.end_combo.addItem("Live Value")
        for i in range(128):
            self.end_combo.addItem(str(i))
        # Restore selection
        if start_is_current:
            idx = min(old_val, 127)
            self.end_combo.setCurrentIndex(idx)
        else:
            if old_val == MIXING_CURRENT_VALUE:
                self.end_combo.setCurrentIndex(0)
            else:
                self.end_combo.setCurrentIndex(old_val + 1)
        self.end_combo.blockSignals(False)

    def _update_dur_visibility(self):
        is_ms = self.dur_ms_cb.isChecked()
        self.dur_ms_spin.setVisible(is_ms)
        self.dur_note_combo.setVisible(not is_ms)

    def on_start_change(self):
        self._rebuild_end_combo()
        self.on_change()

    def _on_dur_ms_toggle(self):
        self._update_dur_visibility()
        self.on_change()

    def insert(self, row):
        self.container.addWidget(self.layout_container, row, 3)

    def remove(self):
        self.container.removeWidget(self.layout_container)

    def delete(self):
        self.cc_spin.deleteLater()
        self.channel_combo.deleteLater()
        self.start_combo.deleteLater()
        self.end_combo.deleteLater()
        self.dur_ms_cb.deleteLater()
        self.dur_ms_spin.deleteLater()
        self.dur_note_combo.deleteLater()
        self.layout_container.deleteLater()

    def on_change(self):
        if self._initializing:
            return

        self.act.cc_num = self.cc_spin.value()
        self.act.channel = self.channel_combo.currentIndex()

        # Start value
        if self.start_combo.currentIndex() == 0:
            self.act.start_val = MIXING_CURRENT_VALUE
        else:
            self.act.start_val = self.start_combo.currentIndex() - 1

        # End value
        start_is_current = (self.start_combo.currentIndex() == 0)
        if start_is_current:
            self.act.end_val = self.end_combo.currentIndex()
        else:
            if self.end_combo.currentIndex() == 0:
                self.act.end_val = MIXING_CURRENT_VALUE
            else:
                self.act.end_val = self.end_combo.currentIndex() - 1

        # Duration
        if self.dur_ms_cb.isChecked():
            self.act.duration_type = 0
            self.act.duration = self.dur_ms_spin.value()
        else:
            self.act.duration_type = 1
            display_idx = self.dur_note_combo.currentIndex()
            note_val = ActionBPMDelayUI.NOTE_DISPLAY_ORDER[display_idx][0]
            self.act.duration = (note_val << 8) | 0

        self.changed.emit()



# ---------------------------------------------------------------------------
# Mouse Move actions: X/Y in desktop pixels + "Get coordinate" capture overlay
# ---------------------------------------------------------------------------
def _virtual_desktop():
    """The union of every screen, in pixels (what the digitizer's 0..32767 maps to)."""
    from PyQt5.QtWidgets import QApplication
    screen = QApplication.primaryScreen()
    if screen is None:
        from PyQt5.QtCore import QRect
        return QRect(0, 0, 1920, 1080)
    return screen.virtualGeometry()


def mouse_px_to_coord(px, origin, size):
    if size <= 1:
        return 0
    v = int(round((px - origin) * MOUSE_COORD_MAX / float(size - 1)))
    return max(0, min(MOUSE_COORD_MAX, v))


def mouse_coord_to_px(v, origin, size):
    return origin + int(round(v * (size - 1) / float(MOUSE_COORD_MAX)))


class CoordinateCaptureOverlay(QWidget):
    """Full-desktop, semi-transparent, always-on-top sheet: the next click
    anywhere reports its global pixel position; Esc cancels."""

    captured = pyqtSignal(int, int)   # global x, y in pixels
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(_virtual_desktop())
        self.setFocusPolicy(Qt.StrongFocus)

    def paintEvent(self, ev):
        from PyQt5.QtGui import QPainter, QColor, QFont
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 70))
        p.setPen(QColor(255, 255, 255))
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter,
                   "Click anywhere to capture that position\n(Esc to cancel)")
        p.end()

    def mousePressEvent(self, ev):
        pos = ev.globalPos()
        self.captured.emit(pos.x(), pos.y())
        self.close()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()
        else:
            super().keyPressEvent(ev)


class ActionMouseMoveUI(BasicActionUI):
    """Shared UI for the four Mouse Move line types; the subclass fixes the
    click kind. Coordinates are edited in pixels of THIS desktop and stored as
    the digitizer's 0..32767 fraction, so they survive a resolution change."""

    actcls = ActionMouseMove
    click_kind = MOUSE_CLICK_NONE

    def __init__(self, container, act=None):
        fresh = act is None
        super().__init__(container, act)
        if fresh:
            self.act.click = self.click_kind
        self._initializing = True
        self._overlay = None

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)
        self.layout_container = QWidget()
        self.layout_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        vg = _virtual_desktop()
        self.lbl_x = QLabel("X")
        self.layout.addWidget(self.lbl_x)
        self.x_spin = ArrowSpinBox()
        self.x_spin.setRange(vg.left(), vg.left() + max(0, vg.width() - 1))
        self.x_spin.setFixedWidth(80)
        self.x_spin.setValue(mouse_coord_to_px(self.act.x, vg.left(), vg.width()))
        self.x_spin.valueChanged.connect(self.on_change)
        self.layout.addWidget(self.x_spin)

        self.lbl_y = QLabel("Y")
        self.layout.addWidget(self.lbl_y)
        self.y_spin = ArrowSpinBox()
        self.y_spin.setRange(vg.top(), vg.top() + max(0, vg.height() - 1))
        self.y_spin.setFixedWidth(80)
        self.y_spin.setValue(mouse_coord_to_px(self.act.y, vg.top(), vg.height()))
        self.y_spin.valueChanged.connect(self.on_change)
        self.layout.addWidget(self.y_spin)

        self.btn_get = QToolButton()
        self.btn_get.setText("Get coordinate")
        self.btn_get.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_get.setToolTip("Hides this window, then the next click anywhere on the desktop "
                                "becomes the position (Esc cancels).")
        self.btn_get.clicked.connect(self.on_get_coordinate)
        self.layout.addWidget(self.btn_get)

        self.lbl_desk = QLabel("(desktop {}x{})".format(vg.width(), vg.height()))
        self.lbl_desk.setStyleSheet("color: gray; font-size: 9pt;")
        self.layout.addWidget(self.lbl_desk)
        self.layout.addStretch()

        self.layout_container.setLayout(self.layout)
        self._initializing = False

    # ---- capture ---------------------------------------------------------

    def on_get_coordinate(self):
        win = self.btn_get.window()
        self._restore_state = win.windowState() if win is not None else None
        self._restore_win = win
        if win is not None:
            win.showMinimized()
        self._overlay = CoordinateCaptureOverlay()
        self._overlay.captured.connect(self._on_captured)
        self._overlay.cancelled.connect(self._restore_window)
        self._overlay.show()
        self._overlay.raise_()
        self._overlay.activateWindow()

    def _on_captured(self, gx, gy):
        vg = _virtual_desktop()
        self.set_pixels(gx, gy)
        self._restore_window()

    def _restore_window(self):
        win = getattr(self, "_restore_win", None)
        self._overlay = None
        if win is None:
            return
        state = self._restore_state if self._restore_state is not None else Qt.WindowNoState
        win.setWindowState(state & ~Qt.WindowMinimized)
        win.show()
        win.raise_()
        win.activateWindow()

    # ---- model -----------------------------------------------------------

    def set_pixels(self, px, py):
        """Set the position from desktop pixels (clamped to the desktop)."""
        self.x_spin.setValue(int(px))
        self.y_spin.setValue(int(py))

    def insert(self, row):
        self.container.addWidget(self.layout_container, row, 3)

    def remove(self):
        self.container.removeWidget(self.layout_container)

    def delete(self):
        self.x_spin.deleteLater()
        self.y_spin.deleteLater()
        self.btn_get.deleteLater()
        self.lbl_x.deleteLater()
        self.lbl_y.deleteLater()
        self.lbl_desk.deleteLater()
        self.layout_container.deleteLater()

    def on_change(self):
        if self._initializing:
            return
        vg = _virtual_desktop()
        self.act.x = mouse_px_to_coord(self.x_spin.value(), vg.left(), vg.width())
        self.act.y = mouse_px_to_coord(self.y_spin.value(), vg.top(), vg.height())
        self.act.click = self.click_kind
        self.changed.emit()


class ActionMouseMoveClickUI(ActionMouseMoveUI):
    click_kind = MOUSE_CLICK_LEFT


class ActionMouseMoveDoubleClickUI(ActionMouseMoveUI):
    click_kind = MOUSE_CLICK_DOUBLE


class ActionMouseMoveRightClickUI(ActionMouseMoveUI):
    click_kind = MOUSE_CLICK_RIGHT


MOUSE_UI_BY_CLICK = {
    MOUSE_CLICK_NONE: ActionMouseMoveUI,
    MOUSE_CLICK_LEFT: ActionMouseMoveClickUI,
    MOUSE_CLICK_DOUBLE: ActionMouseMoveDoubleClickUI,
    MOUSE_CLICK_RIGHT: ActionMouseMoveRightClickUI,
}


class ActionGamepadUI(BasicActionUI):
    """Shared UI for the gamepad macro line types. Each subclass fixes which
    controls are shown and the action kind / target it writes."""

    actcls = ActionGamepad
    # subclass configuration
    kinds = [GAMEPAD_TAP]          # selectable kinds (mode combo when > 1)
    kind_names = ["Tap"]
    fixed_target = None            # stick / trigger fixed by the line type
    show_button = False
    show_trigger = False
    show_direction = False
    show_percent = False           # percent only for kinds that use it

    def __init__(self, container, act=None):
        fresh = act is None
        super().__init__(container, act)
        if fresh or self.act.kind not in self.kinds:
            self.act.kind = self.kinds[0]
        if self.fixed_target is not None:
            self.act.target = self.fixed_target
        self._initializing = True
        self._widgets = []

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)
        self.layout_container = QWidget()
        self.layout_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        self.button_combo = None
        if self.show_button:
            self.button_combo = ArrowComboBox()
            for num, name in GAMEPAD_BUTTONS:
                self.button_combo.addItem(name, num)
            idx = self.button_combo.findData(self.act.target)
            self.button_combo.setCurrentIndex(max(0, idx))
            if idx < 0:
                self.act.target = GAMEPAD_BUTTONS[0][0]
            self.button_combo.currentIndexChanged.connect(self.on_change)
            self._add(self.button_combo)

        self.trigger_combo = None
        if self.show_trigger:
            self.trigger_combo = ArrowComboBox()
            self.trigger_combo.addItems(["Left Trigger (LT)", "Right Trigger (RT)"])
            self.trigger_combo.setCurrentIndex(1 if self.act.target == 1 else 0)
            self.trigger_combo.currentIndexChanged.connect(self.on_change)
            self._add(self.trigger_combo)

        self.mode_combo = None
        if len(self.kinds) > 1:
            self.mode_combo = ArrowComboBox()
            self.mode_combo.addItems(self.kind_names)
            self.mode_combo.setCurrentIndex(self.kinds.index(self.act.kind))
            self.mode_combo.currentIndexChanged.connect(self.on_change)
            self._add(self.mode_combo)

        self.dir_combo = None
        if self.show_direction:
            self._add(QLabel("Direction"))
            self.dir_combo = ArrowComboBox()
            self.dir_combo.addItems(GAMEPAD_DIRECTIONS)
            self.dir_combo.setCurrentIndex(self.act.value if 0 <= self.act.value < 8 else 0)
            self.dir_combo.currentIndexChanged.connect(self.on_change)
            self._add(self.dir_combo)

        self.pct_label = None
        self.pct_spin = None
        if self.show_percent:
            self.pct_label = QLabel("Amount %")
            self._add(self.pct_label)
            self.pct_spin = ArrowSpinBox()
            self.pct_spin.setRange(0, 100)
            self.pct_spin.setValue(self.act.percent if fresh is False else 100)
            if fresh:
                self.act.percent = 100
            self.pct_spin.valueChanged.connect(self.on_change)
            self._add(self.pct_spin)

        # Duration: how long the move / tap takes. Wait: delay before the
        # next action, tied to the duration unless the user unties it.
        if fresh:
            self.act.duration = (GAMEPAD_TAP_DEFAULT_DURATION if self.act.kind == GAMEPAD_TAP
                                 else GAMEPAD_DEFAULT_DURATION)
            self.act.tied = self.act.uses_duration
            self.act.wait = self.act.duration if self.act.tied else 0
        self.dur_label = QLabel("Duration (ms)")
        self._add(self.dur_label)
        self.dur_spin = ArrowSpinBox()
        self.dur_spin.setRange(1, GAMEPAD_MS_MAX)
        self.dur_spin.setValue(max(1, self.act.duration))
        self.dur_spin.valueChanged.connect(self.on_change)
        self._add(self.dur_spin)

        self.tie_check = QCheckBox("Tie wait to action duration")
        self.tie_check.setToolTip("When ticked, the next action starts once this one has finished. "
                                  "Untick to set a different wait.")
        self.tie_check.setChecked(bool(self.act.tied))
        self.tie_check.toggled.connect(self.on_change)
        self._add(self.tie_check)

        self.ms_label_w = QLabel("Wait (ms)")
        self._add(self.ms_label_w)
        self.ms_spin = ArrowSpinBox()
        self.ms_spin.setRange(0, GAMEPAD_MS_MAX)
        self.ms_spin.setValue(self.act.effective_wait())
        self.ms_spin.setToolTip("How long to wait before the next action")
        self.ms_spin.valueChanged.connect(self.on_change)
        self._add(self.ms_spin)
        self.layout.addStretch()

        self.layout_container.setLayout(self.layout)
        self._update_visibility()
        self._initializing = False

    def _add(self, w):
        self._widgets.append(w)
        self.layout.addWidget(w)

    def _update_visibility(self):
        # Percent only means something while a trigger / stick is being set.
        if self.pct_spin is not None:
            on = self.act.kind in (GAMEPAD_TRIGGER, GAMEPAD_STICK)
            self.pct_spin.setVisible(on)
            self.pct_label.setVisible(on)
        uses = self.act.uses_duration
        for w in (self.dur_label, self.dur_spin, self.tie_check):
            w.setVisible(uses)
        if self.act.kind == GAMEPAD_TAP:
            self.dur_spin.setToolTip("How long the button is held down")
        else:
            self.dur_spin.setToolTip("How long the move takes: 1 ms is instant, 2000 ms moves "
                                     "it gradually over two seconds from where it is now")
        tied = uses and self.tie_check.isChecked()
        self.ms_spin.setEnabled(not tied)
        if tied:
            self.ms_spin.blockSignals(True)
            self.ms_spin.setValue(self.dur_spin.value())
            self.ms_spin.blockSignals(False)

    def insert(self, row):
        self.container.addWidget(self.layout_container, row, 3)

    def remove(self):
        self.container.removeWidget(self.layout_container)

    def delete(self):
        for w in self._widgets:
            w.deleteLater()
        self.layout_container.deleteLater()

    def on_change(self):
        if self._initializing:
            return
        if self.mode_combo is not None:
            self.act.kind = self.kinds[self.mode_combo.currentIndex()]
        if self.button_combo is not None:
            self.act.target = self.button_combo.currentData()
        if self.trigger_combo is not None:
            self.act.target = self.trigger_combo.currentIndex()
        if self.fixed_target is not None:
            self.act.target = self.fixed_target
        if self.dir_combo is not None:
            self.act.value = self.dir_combo.currentIndex()
        if self.pct_spin is not None:
            self.act.percent = self.pct_spin.value()
        self.act.duration = self.dur_spin.value()
        self.act.tied = self.act.uses_duration and self.tie_check.isChecked()
        self._update_visibility()
        self.act.wait = self.ms_spin.value()
        self.changed.emit()


class ActionGamepadButtonUI(ActionGamepadUI):
    kinds = [GAMEPAD_TAP, GAMEPAD_PRESS, GAMEPAD_RELEASE]
    kind_names = ["Tap", "Press", "Release"]
    show_button = True


class ActionGamepadTriggerUI(ActionGamepadUI):
    kinds = [GAMEPAD_TRIGGER, GAMEPAD_TRIGGER_RELEASE]
    kind_names = ["Press", "Release"]
    show_trigger = True
    show_percent = True


class ActionGamepadLeftStickUI(ActionGamepadUI):
    kinds = [GAMEPAD_STICK]
    fixed_target = 0
    show_direction = True
    show_percent = True


class ActionGamepadRightStickUI(ActionGamepadLeftStickUI):
    fixed_target = 1


class ActionGamepadLeftStickReleaseUI(ActionGamepadUI):
    kinds = [GAMEPAD_STICK_RELEASE]
    fixed_target = 0


class ActionGamepadRightStickReleaseUI(ActionGamepadLeftStickReleaseUI):
    fixed_target = 1


def _gamepad_ui_for(act):
    if act.kind in (GAMEPAD_TAP, GAMEPAD_PRESS, GAMEPAD_RELEASE):
        return ActionGamepadButtonUI
    if act.kind in (GAMEPAD_TRIGGER, GAMEPAD_TRIGGER_RELEASE):
        return ActionGamepadTriggerUI
    if act.kind == GAMEPAD_STICK:
        return ActionGamepadRightStickUI if act.target == 1 else ActionGamepadLeftStickUI
    return ActionGamepadRightStickReleaseUI if act.target == 1 else ActionGamepadLeftStickReleaseUI


tag_to_action = {
    "down": ActionDown,
    "up": ActionUp,
    "tap": ActionTap,
    "text": ActionText,
    "delay": ActionDelay,
    "bpm_delay": ActionBPMDelay,
    "bpm_delay_repeat": ActionBPMDelay,  # Convert old repeat type to plain BPM delay
    "mixing_control": ActionMixingControl,
    "mouse_move": ActionMouseMove,
    "gamepad": ActionGamepad,
}

ui_action = {
    ActionText: ActionTextUI,
    ActionUp: ActionUpUI,
    ActionDown: ActionDownUI,
    ActionTap: ActionTapUI,
    ActionDelay: ActionDelayUI,
    ActionBPMDelay: ActionBPMDelayUI,
    ActionMixingControl: ActionMixingControlUI,
    ActionMouseMove: ActionMouseMoveUI,
    ActionGamepad: ActionGamepadButtonUI,
}


def ui_for_action(act):
    """The UI class for an existing action object. Mouse Move is one action
    class shown as four line types (one per click kind), so it is resolved by
    the action's click field rather than its type."""
    if isinstance(act, ActionMouseMove):
        return MOUSE_UI_BY_CLICK.get(act.click, ActionMouseMoveUI)
    if isinstance(act, ActionGamepad):
        return _gamepad_ui_for(act)
    return ui_action[type(act)]
