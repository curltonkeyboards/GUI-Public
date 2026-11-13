# SPDX-License-Identifier: GPL-2.0-or-later
#
# The looks shared with MIDIswitch Play.
#
#   Retro Peach / Retro Blue          "pop": near-white panels, dark outlines, hard offset shadows
#   Futuristic Light / Futuristic Dark "clay": soft raised and hollowed-out shapes, no colour accent
#   Futuristic Peach / Futuristic Blue "clay" again, tinted with the peach and the blue pastels
#                                      (a quiet accent of the same family, as in MIDIswitch Play)
#
# Each theme is a small set of colour tokens (TOKENS). The QPalette and the application stylesheet are
# both generated from them, so a colour is only ever written down once.

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor

TOKENS = {
    "Retro Peach": dict(
        style="pop", dark=False,
        backdrop="#f3b7be",     # behind everything (the main window)
        window="#fcece6",       # the big panel that holds the interface
        card="#fef9f8",         # raised things: buttons, cards, fields
        hover="#fde4e0",
        text="#5b3b3c", dim="#b38f8c", disabled="#cdb6b3", muted="#8f6f6c",
        accent="#f08c8f", accent_hover="#f4a2a4", on_accent="#ffffff",
        track="#f2d5cd",        # grooves: slider tracks, scroll bars
        outline="#5b3b3c", soft_line="#e3c9c4",
    ),
    "Retro Blue": dict(
        style="pop", dark=False,
        backdrop="#a5c8f1",
        window="#e7eff9",
        card="#fafcfd",
        hover="#dcebfb",
        text="#2c4259", dim="#869bb1", disabled="#b3c1d0", muted="#5f7790",
        accent="#6aa9ec", accent_hover="#86b9f0", on_accent="#ffffff",
        track="#cfdded",
        outline="#2c4259", soft_line="#c3d3e6",
    ),
    "Futuristic Light": dict(
        style="clay", dark=False,
        backdrop="#e0e6ee",
        window="#e8eaee",
        card="#eceef2",
        hover="#f3f5f8",
        text="#2f333b", dim="#8b919d", disabled="#b4b9c2", muted="#6b7280",
        accent="#9299a6", accent_hover="#a3a9b5", on_accent="#ffffff",
        track="#d8dce3",
        outline="#b4bbc7", soft_line="#d3d7de",
        hi="#ffffff", lo="#9aa2b1",          # the lit and the shaded edge of every shape
        raised_a="#f7f8fa", raised_b="#d9dde4",
    ),
    "Futuristic Dark": dict(
        style="clay", dark=True,
        backdrop="#2a2d37",
        window="#33353d",
        card="#464a55",
        hover="#535763",
        text="#e9eaf0", dim="#8c909c", disabled="#666a75", muted="#aeb2bd",
        accent="#5d616d", accent_hover="#6c717e", on_accent="#ffffff",
        track="#24262c",
        outline="#191b1f", soft_line="#2a2c33",
        hi="#7a7f8c", lo="#0e0f12",
        raised_a="#585c68", raised_b="#3a3e47",
    ),
    "Futuristic Peach": dict(
        style="clay", dark=False,
        backdrop="#f5d8d3",
        window="#fbe6de",
        card="#fcebe5",
        hover="#fef3ef",
        text="#5b3b3c", dim="#b08d8a", disabled="#cdb6b3", muted="#8f6f6c",
        accent="#dba29b", accent_hover="#e3b3ad", on_accent="#ffffff",
        track="#f0d4cb",
        outline="#d9b5ad", soft_line="#ecd0c8",
        hi="#ffffff", lo="#c99a90",
        raised_a="#fff6f2", raised_b="#f1d6ce",
    ),
    "Futuristic Blue": dict(
        style="clay", dark=False,
        backdrop="#cfdff2",
        window="#dfe9f6",
        card="#e6eefa",
        hover="#eff5fc",
        text="#2c4259", dim="#869bb1", disabled="#b3c1d0", muted="#5f7790",
        accent="#8fb0d6", accent_hover="#a3bfdf", on_accent="#ffffff",
        track="#cfdcec",
        outline="#b0c3da", soft_line="#c9d8ea",
        hi="#ffffff", lo="#93a9c4",
        raised_a="#f4f8fd", raised_b="#d2deee",
    ),
}

DEFAULT_THEME = "Retro Peach"


def _palette_colors(t):
    """The QPalette roles for a theme. Widgets with their own stylesheets refer to these as
    palette(button), palette(mid) and so on, so the roles are chosen to suit that use:
    mid is the line colour, light the hover fill, highlight the accent."""
    pop = t["style"] == "pop"
    return {
        QPalette.Window: t["window"],
        QPalette.WindowText: t["text"],
        QPalette.Base: t["card"],
        QPalette.AlternateBase: t["hover"],
        QPalette.ToolTipBase: t["card"],
        QPalette.ToolTipText: t["text"],
        QPalette.Text: t["text"],
        QPalette.Button: t["card"],
        QPalette.ButtonText: t["text"],
        QPalette.BrightText: t["accent"],
        QPalette.Link: t["accent"],
        QPalette.Highlight: t["accent"],
        QPalette.HighlightedText: t["on_accent"],
        QPalette.Light: t["hover"],
        QPalette.Midlight: t["soft_line"],
        QPalette.Mid: t["outline"] if pop else t["lo"],
        # "dark" is the role local stylesheets use for secondary text (palette(dark)): descriptions,
        # hints, counts. It is the theme's muted text colour, never a line colour.
        QPalette.Dark: t["muted"],
        QPalette.Shadow: t["outline"] if pop else t["lo"],
        (QPalette.Disabled, QPalette.ButtonText): t["disabled"],
        (QPalette.Disabled, QPalette.WindowText): t["disabled"],
        (QPalette.Disabled, QPalette.Text): t["disabled"],
        (QPalette.Disabled, QPalette.Light): t["hover"],
    }


# (name, palette colours) for each theme, in menu order
themes = [(name, _palette_colors(t)) for name, t in TOKENS.items()]

palettes = dict()

for name, colors in themes:
    palette = QPalette()
    for role, color in colors.items():
        if not hasattr(type(role), '__iter__'):
            role = [role]
        palette.setColor(*role, QColor(color))
    palettes[name] = palette


# ---------------------------------------------------------------------------------------------
# Stylesheet pieces. Rounded squares throughout; only slider handles are round.

def _raised(t, radius=8, depth=3):
    """A thing that stands up from the surface: a button, a tab, a card."""
    if t["style"] == "pop":
        return """
                background: %(card)s;
                color: %(text)s;
                border: 1px solid %(outline)s;
                border-bottom: {d}px solid %(outline)s;
                border-right: {d}px solid %(outline)s;
                border-radius: {r}px;""".format(d=depth, r=radius) % t
    return """
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 %(raised_a)s, stop: 1 %(raised_b)s);
                color: %(text)s;
                border: 1px solid %(lo)s;
                border-top-color: %(hi)s;
                border-left-color: %(hi)s;
                border-radius: {r}px;""".format(r=radius) % t


def _raised_hover(t):
    if t["style"] == "pop":
        return "background: %(hover)s;" % t
    return "background: %(hover)s;" % t


def _pressed(t, radius=8, depth=3):
    """Pushed in. Pop: the shadow goes and the face moves into its place. Clay: hollowed out."""
    if t["style"] == "pop":
        return """
                background: %(hover)s;
                border: 1px solid %(outline)s;
                margin-top: {m}px;
                margin-left: {m}px;
                border-radius: {r}px;""".format(m=depth - 1, r=radius) % t
    return _hollow(t, radius)


def _hollow(t, radius=8):
    """A groove or a well in the surface: text fields, slider tracks, a pressed clay button."""
    if t["style"] == "pop":
        return """
                background: %(card)s;
                color: %(text)s;
                border: 1px solid %(outline)s;
                border-radius: {r}px;""".format(r=radius) % t
    return """
                background: %(track)s;
                color: %(text)s;
                border: 1px solid %(hi)s;
                border-top-color: %(lo)s;
                border-left-color: %(lo)s;
                border-radius: {r}px;""".format(r=radius) % t


def _chosen(t, radius=8, depth=3):
    """Switched on: a selected tab, a checked button. Pop fills with the accent; clay hollows out."""
    if t["style"] == "pop":
        return """
                background: %(accent)s;
                color: %(on_accent)s;
                border: 1px solid %(outline)s;
                border-bottom: {d}px solid %(outline)s;
                border-right: {d}px solid %(outline)s;
                border-radius: {r}px;
                font-weight: 600;""".format(d=depth, r=radius) % t
    return _hollow(t, radius) + "\n                font-weight: 600;"


def build_stylesheet(t):
    """The application stylesheet for one theme."""
    pop = t["style"] == "pop"
    parts = dict(t)
    parts.update(
        raised=_raised(t), raised_small=_raised(t, 6, 2), raised_big=_raised(t, 10, 4),
        raised_hover=_raised_hover(t),
        pressed=_pressed(t), pressed_small=_pressed(t, 6, 2),
        hollow=_hollow(t), hollow_small=_hollow(t, 6), hollow_tiny=_hollow(t, 4),
        chosen=_chosen(t), chosen_small=_chosen(t, 6, 2),
        focus_line=t["accent"] if pop else t["dim"],
        handle_border=t["outline"] if pop else t["lo"],
        handle_fill=t["card"] if pop else ("#d9dbe3" if t["dark"] else "#ffffff"),
        fill=t["accent"],
        menu_radius=8,
        check_fill=t["accent"] if pop else t["track"],      # behind the tick of a ticked box
        card_fill=t["card"] if pop else "qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 %s, stop: 1 %s)" % (t["raised_a"], t["window"]),
        tab_line=t["outline"] if pop else t["lo"],          # the edge of a tab, and its shaded side
        tab_lit=t["outline"] if pop else t["hi"],           # its lit side
        tab_mark=t["accent"] if pop else t["dim"],          # the stripe along the selected tab
    )
    return """
            QMainWindow, QDialog {
                background: %(backdrop)s;
            }

            QDialog {
                background: %(window)s;
            }

            QToolTip {
                background-color: %(card)s;
                color: %(text)s;
                border: 1px solid %(handle_border)s;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 9pt;
            }

            /* ---- menus ---- */
            QMenuBar {
                background: %(backdrop)s;
                color: %(text)s;
            }

            QMenuBar::item {
                background: transparent;
                padding: 4px 10px;
                border-radius: 6px;
            }

            QMenuBar::item:selected, QMenuBar::item:pressed {
                background: %(card)s;
            }

            QMenu {
                background: %(card)s;
                color: %(text)s;
                border: 1px solid %(handle_border)s;
                border-radius: %(menu_radius)spx;
                padding: 5px;
            }

            QMenu::item {
                padding: 5px 22px 5px 22px;
                border-radius: 5px;
            }

            QMenu::item:selected {
                background: %(accent)s;
                color: %(on_accent)s;
            }

            QMenu::item:disabled {
                color: %(disabled)s;
            }

            QMenu::separator {
                height: 1px;
                background: %(soft_line)s;
                margin: 4px 8px;
            }

            /* ---- tabs: attached to the panel below; the selected one opens into it ---- */
            QTabBar::tab {
                background: %(track)s;
                color: %(text)s;
                border: 1px solid %(tab_line)s;
                border-top-color: %(tab_lit)s;
                border-left-color: %(tab_lit)s;
                border-bottom-color: %(tab_line)s;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                padding: 3px 9px;
                margin-top: 4px;
                margin-right: 2px;
                margin-bottom: 0px;
                font-weight: 500;
                font-size: 9pt;
            }

            QTabBar::tab:hover:!selected {
                background: %(hover)s;
            }

            QTabBar::tab:selected {
                background: %(window)s;
                border-top: 3px solid %(tab_mark)s;
                border-bottom-color: %(window)s;
                margin-top: 0px;
                margin-bottom: -1px;
                padding-bottom: 4px;
                font-weight: 600;
            }

            QTabBar::tab:disabled {
                color: %(disabled)s;
            }

            QTabWidget::pane {%(raised_big)s
                background: %(window)s;
                border-top-left-radius: 0px;
                top: -1px;
            }

            /* ---- buttons ---- */
            QPushButton {%(raised)s
                padding: 2px 8px;
            }

            QPushButton:hover {
                %(raised_hover)s
            }

            QPushButton:pressed {%(pressed)s
            }

            QPushButton:checked {%(chosen)s
            }

            QPushButton:disabled {
                color: %(disabled)s;
            }

            /* Dialog buttons (Save / Discard / OK ...) - room for their text */
            QMessageBox QPushButton, QDialogButtonBox QPushButton {
                min-width: 96px;
                min-height: 30px;
                padding: 4px 16px;
            }

            /* Keycode buttons */
            QPushButton[keycode_button="true"] {%(raised_small)s
                padding: 0px;
                font-size: 9pt;
            }

            QPushButton[keycode_button="true"]:hover {
                %(raised_hover)s
            }

            QPushButton[keycode_button="true"]:pressed {%(pressed_small)s
            }

            /* Layer selection buttons */
            QPushButton[keycode_button="true"]:checked {%(chosen_small)s
            }

            /* Inner tab buttons - a row of tabs inside a page, attached to what is below */
            QPushButton[inner_tab="true"] {
                background: %(track)s;
                color: %(text)s;
                border: 1px solid %(tab_line)s;
                border-top-color: %(tab_lit)s;
                border-left-color: %(tab_lit)s;
                border-radius: 0px;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                padding: 2px 8px;
                margin-top: 3px;
                margin-right: 2px;
                margin-bottom: 0px;
                font-weight: 500;
                font-size: 9pt;
            }

            QPushButton[inner_tab="true"]:hover:!checked {
                background: %(hover)s;
            }

            QPushButton[inner_tab="true"]:checked {
                background: %(window)s;
                color: %(text)s;
                border-top: 3px solid %(tab_mark)s;
                border-bottom-color: %(window)s;
                margin-top: 0px;
                margin-bottom: -1px;
                font-weight: 600;
            }

            /* Side tab buttons - a column of tabs on the left, attached to the content on their
               right. Each draws the dividing line on its right edge; the selected one leaves it
               out and takes the content's colour, so it opens into the content. */
            QPushButton[side_tab="true"] {
                background: %(track)s;
                color: %(text)s;
                border: 1px solid %(tab_line)s;
                border-top-color: %(tab_lit)s;
                border-left-color: %(tab_lit)s;
                border-radius: 0px;
                border-top-left-radius: 7px;
                border-bottom-left-radius: 7px;
                padding: 2px 8px 2px 12px;
                margin-top: 1px;
                margin-bottom: 1px;
                margin-left: 4px;
                margin-right: 0px;
                text-align: left;
                min-width: 100px;
                font-weight: 500;
                font-size: 9pt;
            }

            QPushButton[side_tab="true"]:hover:!checked {
                background: %(hover)s;
                color: %(text)s;
            }

            QPushButton[side_tab="true"]:checked {
                background: %(window)s;
                color: %(text)s;
                border: 1px solid %(tab_line)s;
                border-top-color: %(tab_lit)s;
                border-left: 4px solid %(tab_mark)s;
                border-right-color: %(window)s;
                margin-left: 0px;
                font-weight: 600;
            }

            QPushButton[side_tab="true"]:pressed {
                background: %(hover)s;
                color: %(text)s;
                margin-top: 1px;
            }

            QToolButton {%(raised_small)s
                padding: 2px 6px;
            }

            QToolButton:hover {
                %(raised_hover)s
            }

            QToolButton:pressed {%(pressed_small)s
            }

            QToolButton:checked {%(chosen_small)s
            }

            /* ---- drop-downs ---- */
            QComboBox {%(raised_small)s
                padding: 2px 12px;
                padding-right: 28px;
                min-height: 20px;
                min-width: 80px;
            }

            QComboBox:hover {
                %(raised_hover)s
            }

            /* The dropdowns of the keycode panel are all the same, taller, height */
            CenteredComboBox {
                min-height: 34px;
            }

            QComboBox:disabled {
                color: %(disabled)s;
            }

            /* The read-only text field inside editable (centred) combos:
               no box of its own, so it can't eat the combo's height */
            QComboBox QLineEdit, QComboBox QLineEdit:hover, QComboBox QLineEdit:focus {
                padding: 0px;
                margin: 0px;
                border: none;
                background: transparent;
            }

            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border: none;
                padding-right: 4px;
            }

            QComboBox::down-arrow {
                /* Arrow is drawn programmatically in custom ComboBox classes */
                width: 12px;
                height: 8px;
            }

            QComboBox QAbstractItemView {
                border: 1px solid %(handle_border)s;
                border-radius: 6px;
                background: %(card)s;
                color: %(text)s;
                selection-background-color: %(accent)s;
                selection-color: %(on_accent)s;
                padding: 4px;
                outline: 0px;
            }

            QComboBox QAbstractItemView::item {
                padding: 6px;
                min-height: 24px;
            }

            /* ---- lists and tables ---- */
            QListWidget, QListView, QTreeWidget, QTreeView, QTextEdit, QPlainTextEdit {%(hollow)s
                selection-background-color: %(accent)s;
                selection-color: %(on_accent)s;
                outline: 0px;
            }

            QListWidget::item, QListView::item {
                border-radius: 4px;
                padding: 1px 4px;
            }

            QListWidget::item:hover, QListView::item:hover {
                background: %(hover)s;
            }

            QListWidget::item:selected, QListView::item:selected {
                background: %(accent)s;
                color: %(on_accent)s;
            }

            QTableWidget, QTableView {%(hollow)s
                gridline-color: %(soft_line)s;
                selection-background-color: %(accent)s;
                selection-color: %(on_accent)s;
            }

            QTableWidget::item, QTableView::item {
                padding: 8px;
                border: 1px solid %(soft_line)s;
                border-radius: 4px;
                margin: 2px;
            }

            QTableWidget::item:hover, QTableView::item:hover {
                background: %(hover)s;
                border-color: %(focus_line)s;
            }

            QHeaderView::section {%(raised_small)s
                padding: 8px;
                margin: 2px;
                font-weight: 600;
            }

            QHeaderView::section:hover {
                %(raised_hover)s
            }

            /* ---- scroll bars: a groove with a rounded-square handle ---- */
            QScrollBar:vertical {
                background: %(track)s;
                width: 14px;
                border-radius: 5px;
                margin: 0px;
            }

            QScrollBar::handle:vertical {
                background: %(handle_fill)s;
                border: 1px solid %(handle_border)s;
                border-radius: 4px;
                min-height: 30px;
                margin: 2px;
            }

            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background: %(hover)s;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: none;
            }

            QScrollBar:horizontal {
                background: %(track)s;
                height: 14px;
                border-radius: 5px;
                margin: 0px;
            }

            QScrollBar::handle:horizontal {
                background: %(handle_fill)s;
                border: 1px solid %(handle_border)s;
                border-radius: 4px;
                min-width: 30px;
                margin: 2px;
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0px;
            }

            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: none;
            }

            /* ---- sliders: a groove, filled up to a round handle ---- */
            QSlider::groove:horizontal {%(hollow_tiny)s
                height: 6px;
            }

            QSlider::sub-page:horizontal {
                background: %(fill)s;
                border: 1px solid %(handle_border)s;
                border-radius: 4px;
            }

            QSlider::handle:horizontal {
                background: %(handle_fill)s;
                border: 1px solid %(handle_border)s;
                width: 14px;
                height: 14px;
                margin: -5px 0px;
                border-radius: 8px;
            }

            QSlider::groove:vertical {%(hollow_tiny)s
                width: 6px;
            }

            QSlider::add-page:vertical {
                background: %(fill)s;
                border: 1px solid %(handle_border)s;
                border-radius: 4px;
            }

            QSlider::handle:vertical {
                background: %(handle_fill)s;
                border: 1px solid %(handle_border)s;
                width: 14px;
                height: 14px;
                margin: 0px -5px;
                border-radius: 8px;
            }

            QSlider::handle:hover {
                background: %(hover)s;
            }

            /* ---- number and text fields ---- */
            QSpinBox, QDoubleSpinBox, QLineEdit {%(hollow_small)s
                padding: 6px 8px;
                selection-background-color: %(accent)s;
                selection-color: %(on_accent)s;
            }

            QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
                border-color: %(focus_line)s;
            }

            QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {
                color: %(disabled)s;
            }

            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                background: %(card)s;
                border: 1px solid %(handle_border)s;
                width: 16px;
            }

            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-position: top right;
                border-top-right-radius: 5px;
            }

            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-position: bottom right;
                border-bottom-right-radius: 5px;
            }

            QSpinBox::up-button:hover, QSpinBox::down-button:hover,
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
                background: %(hover)s;
            }

            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                image: url(__SPIN_UP__);
                width: 10px;
                height: 6px;
            }

            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                image: url(__SPIN_DOWN__);
                width: 10px;
                height: 6px;
            }

            /* ArrowSpinBox paints its own arrows */
            ArrowSpinBox::up-arrow, ArrowSpinBox::down-arrow {
                image: none;
            }

            /* ---- tick boxes ---- */
            QCheckBox::indicator, QGroupBox::indicator {%(hollow_tiny)s
                width: 14px;
                height: 14px;
            }

            QCheckBox::indicator:hover, QGroupBox::indicator:hover {
                border-color: %(focus_line)s;
            }

            QCheckBox::indicator:checked, QGroupBox::indicator:checked {
                background-color: %(check_fill)s;
                border: 1px solid %(handle_border)s;
                image: url(__CHECK__);
            }

            QRadioButton::indicator {%(hollow_tiny)s
                width: 14px;
                height: 14px;
                border-radius: 8px;
            }

            QRadioButton::indicator:checked {
                background-color: %(text)s;
                border: 3px solid %(card)s;
            }

            /* ---- cards ---- */
            QGroupBox {%(raised_big)s
                background: %(window)s;
                margin-top: 12px;
                padding: 12px 8px 8px 8px;
                font-weight: 600;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0px 6px;
                color: %(text)s;
            }

            /* A card: a panel of related controls. Outlined with a hard shadow in the Retro themes,
               raised from the surface in the Futuristic ones. */
            QFrame[card="true"] {%(raised_big)s
                background: %(card_fill)s;
            }

            QScrollArea {
                background: transparent;
                border: none;
            }

            QProgressBar {%(hollow_small)s
                text-align: center;
                min-height: 14px;
            }

            QProgressBar::chunk {
                background: %(accent)s;
                border-radius: 4px;
            }

            QStatusBar {
                background: %(backdrop)s;
                color: %(text)s;
            }

            QSplitter::handle {
                background: %(soft_line)s;
            }
        """ % parts


class Theme:

    theme = ""

    @classmethod
    def _arrow_images(cls, color):
        """Write the spin-box arrow images in this theme's text colour and
        return their paths (a stylesheet can only show arrows as images)."""
        from PyQt5.QtCore import QStandardPaths, QDir, QPoint, Qt
        from PyQt5.QtGui import QPixmap, QPainter, QPolygon
        base = QStandardPaths.writableLocation(QStandardPaths.TempLocation)
        folder = QDir(base).filePath("switchstation_arrows")
        QDir().mkpath(folder)
        paths = []
        for name, pts in (("up", [(0, 6), (10, 6), (5, 0)]), ("down", [(0, 0), (10, 0), (5, 6)])):
            pix = QPixmap(10, 6)
            pix.fill(Qt.transparent)
            qp = QPainter(pix)
            qp.setRenderHint(QPainter.Antialiasing)
            qp.setPen(Qt.NoPen)
            qp.setBrush(color)
            qp.drawPolygon(QPolygon([QPoint(x, y) for x, y in pts]))
            qp.end()
            path = QDir(folder).filePath("spin_{}_{}.png".format(name, color.name()[1:]))
            pix.save(path, "PNG")
            paths.append(QDir.fromNativeSeparators(path))
        return paths

    @classmethod
    def _check_image(cls, color):
        """Write the tick shown in a ticked box, in the given colour, and return its path."""
        from PyQt5.QtCore import QStandardPaths, QDir, QPointF, Qt
        from PyQt5.QtGui import QPixmap, QPainter, QPen, QPolygonF
        base = QStandardPaths.writableLocation(QStandardPaths.TempLocation)
        folder = QDir(base).filePath("switchstation_arrows")
        QDir().mkpath(folder)
        pix = QPixmap(14, 14)
        pix.fill(Qt.transparent)
        qp = QPainter(pix)
        qp.setRenderHint(QPainter.Antialiasing)
        pen = QPen(color, 2.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        qp.setPen(pen)
        qp.drawPolyline(QPolygonF([QPointF(3.0, 7.4), QPointF(5.9, 10.2), QPointF(11.0, 4.0)]))
        qp.end()
        path = QDir(folder).filePath("check_{}.png".format(color.name()[1:]))
        pix.save(path, "PNG")
        return QDir.fromNativeSeparators(path)

    @classmethod
    def set_theme(cls, theme):
        cls.theme = theme
        if theme in palettes:
            QApplication.setPalette(palettes[theme])
            QApplication.setStyle("Fusion")
            up, down = cls._arrow_images(palettes[theme].color(QPalette.Active, QPalette.ButtonText))
            sheet = cls.get_stylesheet().replace("__SPIN_UP__", up).replace("__SPIN_DOWN__", down)
            # the tick is white on the accent in the Retro themes, the text colour in the Futuristic ones
            tick = cls._check_image(cls.color("on_accent" if cls.is_pop() else "text"))
            sheet = sheet.replace("__CHECK__", tick)
            QApplication.instance().setStyleSheet(sheet)
        # For default/system theme, do nothing
        # User will have to restart the application for it to be applied

    @classmethod
    def get_theme(cls):
        return cls.theme

    @classmethod
    def tokens(cls):
        """The colour tokens of the current theme (see TOKENS)."""
        return TOKENS.get(cls.theme, TOKENS[DEFAULT_THEME])

    @classmethod
    def color(cls, name):
        """One colour of the current theme, as a QColor: Theme.color("accent")."""
        return QColor(cls.tokens()[name])

    @classmethod
    def is_light(cls):
        return not cls.tokens()["dark"]

    @classmethod
    def is_pop(cls):
        """True for the Retro themes (outlines and hard shadows), False for the Futuristic ones."""
        return cls.tokens()["style"] == "pop"

    @classmethod
    def mask_light_factor(cls):
        return 103 if cls.is_light() else 150

    @classmethod
    def get_stylesheet(cls):
        """The application stylesheet for the current theme."""
        return build_stylesheet(cls.tokens())

    @classmethod
    def get_button_stylesheet(cls):
        """Return stylesheet for keycode buttons"""
        return """
            QPushButton {
                border-radius: 6px;
                border: 1px solid palette(mid);
            }
        """
