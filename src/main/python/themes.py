# SPDX-License-Identifier: GPL-2.0-or-later

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor

themes = [
    ("Light", {
        QPalette.Window: "#ffefebe7",
        QPalette.WindowText: "#ff000000",
        QPalette.Base: "#ffffffff",
        QPalette.AlternateBase: "#fff7f5f3",
        QPalette.ToolTipBase: "#ffffffdc",
        QPalette.ToolTipText: "#ff000000",
        QPalette.Text: "#ff000000",
        QPalette.Button: "#ffefebe7",
        QPalette.ButtonText: "#ff000000",
        QPalette.BrightText: "#ffffffff",
        QPalette.Link: "#ff0000ff",
        QPalette.Highlight: "#ff308cc6",
        QPalette.HighlightedText: "#ffffffff",
        (QPalette.Active, QPalette.Button): "#ffefebe7",
        (QPalette.Disabled, QPalette.ButtonText): "#ffbebebe",
        (QPalette.Disabled, QPalette.WindowText): "#ffbebebe",
        (QPalette.Disabled, QPalette.Text): "#ffbebebe",
        (QPalette.Disabled, QPalette.Light): "#ffffffff",
    }),
    ("Dark", {
        QPalette.Window: "#353535",
        QPalette.WindowText: "#ffffff",
        QPalette.Base: "#232323",
        QPalette.AlternateBase: "#353535",
        QPalette.ToolTipBase: "#191919",
        QPalette.ToolTipText: "#ffffff",
        QPalette.Text: "#ffffff",
        QPalette.Button: "#353535",
        QPalette.ButtonText: "#ffffff",
        QPalette.BrightText: "#ff0000",
        QPalette.Link: "#f7a948",
        QPalette.Highlight: "#bababa",
        QPalette.HighlightedText: "#232323",
        (QPalette.Active, QPalette.Button): "#353535",
        (QPalette.Disabled, QPalette.ButtonText): "#808080",
        (QPalette.Disabled, QPalette.WindowText): "#808080",
        (QPalette.Disabled, QPalette.Text): "#808080",
        (QPalette.Disabled, QPalette.Light): "#353535",
    }),
    ("Arc", {
        QPalette.Window: "#333333",
        QPalette.WindowText: "#cc5200",
        QPalette.Base: "#61574a",
        QPalette.AlternateBase: "#baaa93",
        QPalette.ToolTipBase: "#3e2308",
        QPalette.ToolTipText: "#cc5200",
        QPalette.Text: "#cc5200",
        QPalette.Button: "#baaa93",
        QPalette.ButtonText: "#cc5200",
        QPalette.BrightText: "#cc5200",
        QPalette.Link: "#baaa93",
        QPalette.Highlight: "#a59783",
        QPalette.HighlightedText: "#cc5200",
        (QPalette.Active, QPalette.Button): "#baaa93",
        (QPalette.Disabled, QPalette.ButtonText): "#cc5200",
        (QPalette.Disabled, QPalette.WindowText): "#cc5200",
        (QPalette.Disabled, QPalette.Text): "#baaa93",
        (QPalette.Disabled, QPalette.Light): "#baaa93",
    }),
    ("Nord", {
        QPalette.Window: "#4b3832",
        QPalette.WindowText: "#fff4e6",
        QPalette.Base: "#be9b7b",
        QPalette.AlternateBase: "#434c5e",
        QPalette.ToolTipBase: "#4c566a",
        QPalette.ToolTipText: "#3c2f2f",
        QPalette.Text: "#eceff4",
        QPalette.Button: "#4b3832",
        QPalette.ButtonText: "#eceff4",
        QPalette.BrightText: "#88c0d0",
        QPalette.Link: "#88c0d0",
        QPalette.Highlight: "#88c0d0",
        QPalette.HighlightedText: "#eceff4",
        (QPalette.Active, QPalette.Button): "#4b3832",
        (QPalette.Disabled, QPalette.ButtonText): "#eceff4",
        (QPalette.Disabled, QPalette.WindowText): "#eceff4",
        (QPalette.Disabled, QPalette.Text): "#eceff4",
        (QPalette.Disabled, QPalette.Light): "#88c0d0",
    }),
    ("Olivia", {
        QPalette.Window: "#181818",
        QPalette.WindowText: "#d9d9d9",
        QPalette.Base: "#181818",
        QPalette.AlternateBase: "#2c2c2c",
        QPalette.ToolTipBase: "#363636 ",
        QPalette.ToolTipText: "#d9d9d9",
        QPalette.Text: "#d9d9d9",
        QPalette.Button: "#181818",
        QPalette.ButtonText: "#d9d9d9",
        QPalette.BrightText: "#fabcad",
        QPalette.Link: "#fabcad",
        QPalette.Highlight: "#fabcad",
        QPalette.HighlightedText: "#2c2c2c",
        (QPalette.Active, QPalette.Button): "#181818",
        (QPalette.Disabled, QPalette.ButtonText): "#d9d9d9",
        (QPalette.Disabled, QPalette.WindowText): "#d9d9d9",
        (QPalette.Disabled, QPalette.Text): "#d9d9d9",
        (QPalette.Disabled, QPalette.Light): "#fabcad",
    }),
    ("Dracula", {
        QPalette.Window: "#282a36",
        QPalette.WindowText: "#f8f8f2",
        QPalette.Base: "#282a36",
        QPalette.AlternateBase: "#44475a",
        QPalette.ToolTipBase: "#6272a4",
        QPalette.ToolTipText: "#f8f8f2",
        QPalette.Text: "#f8f8f2",
        QPalette.Button: "#282a36",
        QPalette.ButtonText: "#f8f8f2",
        QPalette.BrightText: "#8be9fd",
        QPalette.Link: "#8be9fd",
        QPalette.Highlight: "#8be9fd",
        QPalette.HighlightedText: "#f8f8f2",
        (QPalette.Active, QPalette.Button): "#282a36",
        (QPalette.Disabled, QPalette.ButtonText): "#f8f8f2",
        (QPalette.Disabled, QPalette.WindowText): "#f8f8f2",
        (QPalette.Disabled, QPalette.Text): "#f8f8f2",
        (QPalette.Disabled, QPalette.Light): "#8be9fd",
    }),
    ("Bliss", {
        QPalette.Window: "#343434",
        QPalette.WindowText: "#cbc8c9",
        QPalette.Base: "#343434",
        QPalette.AlternateBase: "#3b3b3b",
        QPalette.ToolTipBase: "#424242",
        QPalette.ToolTipText: "#cbc8c9",
        QPalette.Text: "#cbc8c9",
        QPalette.Button: "#343434",
        QPalette.ButtonText: "#cbc8c9",
        QPalette.BrightText: "#f5d1c8",
        QPalette.Link: "#f5d1c8",
        QPalette.Highlight: "#f5d1c8",
        QPalette.HighlightedText: "#424242",
        (QPalette.Active, QPalette.Button): "#343434",
        (QPalette.Disabled, QPalette.ButtonText): "#cbc8c9",
        (QPalette.Disabled, QPalette.WindowText): "#cbc8c9",
        (QPalette.Disabled, QPalette.Text): "#cbc8c9",
        (QPalette.Disabled, QPalette.Light): "#f5d1c8",
    }),
    # Modern 2025 Pastel Themes
    ("Lavender Dream", {
        QPalette.Window: "#f5f3ff",
        QPalette.WindowText: "#4a4458",
        QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#faf9ff",
        QPalette.ToolTipBase: "#e8e4ff",
        QPalette.ToolTipText: "#4a4458",
        QPalette.Text: "#4a4458",
        QPalette.Button: "#f0ecff",
        QPalette.ButtonText: "#4a4458",
        QPalette.BrightText: "#8b7ab8",
        QPalette.Link: "#9d8ac7",
        QPalette.Highlight: "#c4b5fd",
        QPalette.HighlightedText: "#2d2438",
        (QPalette.Active, QPalette.Button): "#e8e4ff",
        (QPalette.Disabled, QPalette.ButtonText): "#b4adc4",
        (QPalette.Disabled, QPalette.WindowText): "#b4adc4",
        (QPalette.Disabled, QPalette.Text): "#b4adc4",
        (QPalette.Disabled, QPalette.Light): "#e8e4ff",
    }),
    ("Mint Fresh", {
        QPalette.Window: "#f0fdf9",
        QPalette.WindowText: "#1e4d3f",
        QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#f4fefb",
        QPalette.ToolTipBase: "#d1fae5",
        QPalette.ToolTipText: "#1e4d3f",
        QPalette.Text: "#1e4d3f",
        QPalette.Button: "#e5fcf3",
        QPalette.ButtonText: "#1e4d3f",
        QPalette.BrightText: "#34d399",
        QPalette.Link: "#6ee7b7",
        QPalette.Highlight: "#a7f3d0",
        QPalette.HighlightedText: "#064e3b",
        (QPalette.Active, QPalette.Button): "#d1fae5",
        (QPalette.Disabled, QPalette.ButtonText): "#9ca3af",
        (QPalette.Disabled, QPalette.WindowText): "#9ca3af",
        (QPalette.Disabled, QPalette.Text): "#9ca3af",
        (QPalette.Disabled, QPalette.Light): "#d1fae5",
    }),
    ("Peachy Keen", {
        QPalette.Window: "#fff8f3",
        QPalette.WindowText: "#5c3d2e",
        QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#fffbf7",
        QPalette.ToolTipBase: "#ffe8d9",
        QPalette.ToolTipText: "#5c3d2e",
        QPalette.Text: "#5c3d2e",
        QPalette.Button: "#fff4ed",
        QPalette.ButtonText: "#5c3d2e",
        QPalette.BrightText: "#fb923c",
        QPalette.Link: "#fdba74",
        QPalette.Highlight: "#fed7aa",
        QPalette.HighlightedText: "#431407",
        (QPalette.Active, QPalette.Button): "#ffe8d9",
        (QPalette.Disabled, QPalette.ButtonText): "#b8a99f",
        (QPalette.Disabled, QPalette.WindowText): "#b8a99f",
        (QPalette.Disabled, QPalette.Text): "#b8a99f",
        (QPalette.Disabled, QPalette.Light): "#ffe8d9",
    }),
    ("Sky Serenity", {
        QPalette.Window: "#f0f9ff",
        QPalette.WindowText: "#1e3a5f",
        QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#f5fbff",
        QPalette.ToolTipBase: "#dbeafe",
        QPalette.ToolTipText: "#1e3a5f",
        QPalette.Text: "#1e3a5f",
        QPalette.Button: "#edf7fe",
        QPalette.ButtonText: "#1e3a5f",
        QPalette.BrightText: "#38bdf8",
        QPalette.Link: "#7dd3fc",
        QPalette.Highlight: "#bae6fd",
        QPalette.HighlightedText: "#0c4a6e",
        (QPalette.Active, QPalette.Button): "#dbeafe",
        (QPalette.Disabled, QPalette.ButtonText): "#94a3b8",
        (QPalette.Disabled, QPalette.WindowText): "#94a3b8",
        (QPalette.Disabled, QPalette.Text): "#94a3b8",
        (QPalette.Disabled, QPalette.Light): "#dbeafe",
    }),
    ("Rose Garden", {
        QPalette.Window: "#fef3f6",
        QPalette.WindowText: "#4a2533",
        QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#fff8fa",
        QPalette.ToolTipBase: "#fce7f3",
        QPalette.ToolTipText: "#4a2533",
        QPalette.Text: "#4a2533",
        QPalette.Button: "#fef7fa",
        QPalette.ButtonText: "#4a2533",
        QPalette.BrightText: "#f472b6",
        QPalette.Link: "#f9a8d4",
        QPalette.Highlight: "#fbcfe8",
        QPalette.HighlightedText: "#500724",
        (QPalette.Active, QPalette.Button): "#fce7f3",
        (QPalette.Disabled, QPalette.ButtonText): "#b8a5ad",
        (QPalette.Disabled, QPalette.WindowText): "#b8a5ad",
        (QPalette.Disabled, QPalette.Text): "#b8a5ad",
        (QPalette.Disabled, QPalette.Light): "#fce7f3",
    }),
    # Modern Dark Themes with Gradients
    ("Midnight Lavender", {
        QPalette.Window: "#1a1625",
        QPalette.WindowText: "#e0d9f0",
        QPalette.Base: "#221b2e",
        QPalette.AlternateBase: "#2a2438",
        QPalette.ToolTipBase: "#332d47",
        QPalette.ToolTipText: "#e0d9f0",
        QPalette.Text: "#e0d9f0",
        QPalette.Button: "#2a2438",
        QPalette.ButtonText: "#e0d9f0",
        QPalette.BrightText: "#a78bfa",
        QPalette.Link: "#c4b5fd",
        QPalette.Highlight: "#7c3aed",
        QPalette.HighlightedText: "#f5f3ff",
        QPalette.Light: "#4a3f5e",
        QPalette.Mid: "#6b5f8a",
        QPalette.Dark: "#15111f",
        QPalette.Midlight: "#3d3352",
        (QPalette.Active, QPalette.Button): "#332d47",
        (QPalette.Disabled, QPalette.ButtonText): "#6b5f7a",
        (QPalette.Disabled, QPalette.WindowText): "#6b5f7a",
        (QPalette.Disabled, QPalette.Text): "#6b5f7a",
        (QPalette.Disabled, QPalette.Light): "#332d47",
    }),
    ("Forest Depths", {
        QPalette.Window: "#0f1f1a",
        QPalette.WindowText: "#d1f5e8",
        QPalette.Base: "#1a2822",
        QPalette.AlternateBase: "#1f3329",
        QPalette.ToolTipBase: "#254d3d",
        QPalette.ToolTipText: "#d1f5e8",
        QPalette.Text: "#d1f5e8",
        QPalette.Button: "#1f3329",
        QPalette.ButtonText: "#d1f5e8",
        QPalette.BrightText: "#34d399",
        QPalette.Link: "#6ee7b7",
        QPalette.Highlight: "#059669",
        QPalette.HighlightedText: "#f0fdf9",
        QPalette.Light: "#2f4d42",
        QPalette.Mid: "#4a7865",
        QPalette.Dark: "#0a1712",
        QPalette.Midlight: "#243d34",
        (QPalette.Active, QPalette.Button): "#254d3d",
        (QPalette.Disabled, QPalette.ButtonText): "#5a7167",
        (QPalette.Disabled, QPalette.WindowText): "#5a7167",
        (QPalette.Disabled, QPalette.Text): "#5a7167",
        (QPalette.Disabled, QPalette.Light): "#254d3d",
    }),
    ("Sunset Ember", {
        QPalette.Window: "#1f1410",
        QPalette.WindowText: "#ffe4d1",
        QPalette.Base: "#2a1d16",
        QPalette.AlternateBase: "#33241c",
        QPalette.ToolTipBase: "#4a3326",
        QPalette.ToolTipText: "#ffe4d1",
        QPalette.Text: "#ffe4d1",
        QPalette.Button: "#33241c",
        QPalette.ButtonText: "#ffe4d1",
        QPalette.BrightText: "#fb923c",
        QPalette.Link: "#fdba74",
        QPalette.Highlight: "#ea580c",
        QPalette.HighlightedText: "#fff8f3",
        QPalette.Light: "#5a4336",
        QPalette.Mid: "#8a6854",
        QPalette.Dark: "#140f0b",
        QPalette.Midlight: "#44342a",
        (QPalette.Active, QPalette.Button): "#4a3326",
        (QPalette.Disabled, QPalette.ButtonText): "#8a6f5f",
        (QPalette.Disabled, QPalette.WindowText): "#8a6f5f",
        (QPalette.Disabled, QPalette.Text): "#8a6f5f",
        (QPalette.Disabled, QPalette.Light): "#4a3326",
    }),
    ("Deep Ocean", {
        QPalette.Window: "#0a1929",
        QPalette.WindowText: "#dbeafe",
        QPalette.Base: "#132337",
        QPalette.AlternateBase: "#1e3a5f",
        QPalette.ToolTipBase: "#1e3a5f",
        QPalette.ToolTipText: "#dbeafe",
        QPalette.Text: "#dbeafe",
        QPalette.Button: "#1e3a5f",
        QPalette.ButtonText: "#dbeafe",
        QPalette.BrightText: "#38bdf8",
        QPalette.Link: "#7dd3fc",
        QPalette.Highlight: "#0284c7",
        QPalette.HighlightedText: "#f0f9ff",
        QPalette.Light: "#2e5278",
        QPalette.Mid: "#4a7ba8",
        QPalette.Dark: "#06111d",
        QPalette.Midlight: "#234263",
        (QPalette.Active, QPalette.Button): "#1e3a5f",
        (QPalette.Disabled, QPalette.ButtonText): "#64748b",
        (QPalette.Disabled, QPalette.WindowText): "#64748b",
        (QPalette.Disabled, QPalette.Text): "#64748b",
        (QPalette.Disabled, QPalette.Light): "#1e3a5f",
    }),
    ("Twilight Rose", {
        QPalette.Window: "#1f0f18",
        QPalette.WindowText: "#fce7f3",
        QPalette.Base: "#2b1621",
        QPalette.AlternateBase: "#3d1f2f",
        QPalette.ToolTipBase: "#4a2533",
        QPalette.ToolTipText: "#fce7f3",
        QPalette.Text: "#fce7f3",
        QPalette.Button: "#3d1f2f",
        QPalette.ButtonText: "#fce7f3",
        QPalette.BrightText: "#f472b6",
        QPalette.Link: "#f9a8d4",
        QPalette.Highlight: "#db2777",
        QPalette.HighlightedText: "#fef3f6",
        QPalette.Light: "#5d3549",
        QPalette.Mid: "#8a5570",
        QPalette.Dark: "#150a11",
        QPalette.Midlight: "#4d2a3c",
        (QPalette.Active, QPalette.Button): "#4a2533",
        (QPalette.Disabled, QPalette.ButtonText): "#7a5f6b",
        (QPalette.Disabled, QPalette.WindowText): "#7a5f6b",
        (QPalette.Disabled, QPalette.Text): "#7a5f6b",
        (QPalette.Disabled, QPalette.Light): "#4a2533",
    }),
]

palettes = dict()

for name, colors in themes:
    palette = QPalette()
    for role, color in colors.items():
        if not hasattr(type(role), '__iter__'):
            role = [role]
        palette.setColor(*role, QColor(color))
    palettes[name] = palette


class Theme:

    theme = ""

    @classmethod
    def set_theme(cls, theme):
        cls.theme = theme
        if theme in palettes:
            QApplication.setPalette(palettes[theme])
            QApplication.setStyle("Fusion")
            QApplication.instance().setStyleSheet(cls.get_stylesheet())
        # For default/system theme, do nothing
        # User will have to restart the application for it to be applied

    @classmethod
    def get_theme(cls):
        return cls.theme

    @classmethod
    def mask_light_factor(cls):
        light_themes = ["Light", "Lavender Dream", "Mint Fresh", "Peachy Keen", "Sky Serenity", "Rose Garden"]
        if cls.theme in light_themes:
            return 103
        return 150

    @classmethod
    def get_stylesheet(cls):
        """Return modern 2025 stylesheet for UI elements"""
        return """
            /* Tooltip Styling - Ensure tooltips are visible */
            QToolTip {
                background-color: palette(tooltip-base);
                color: palette(tooltip-text);
                border: 1px solid palette(mid);
                border-radius: 3px;
                padding: 2px 4px;
                font-size: 9pt;
            }

            /* Modern Tab Styling with Rounded Edges */
            QTabBar::tab {
                background: palette(button);
                border: 1px solid palette(mid);
                padding: 2px 6px;
                margin-right: 2px;
                margin-bottom: 0px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                border-bottom: 1px solid palette(mid);
                font-weight: 500;
                font-size: 9pt;
            }

            QTabBar::tab:selected {
                background: palette(base);
                border-bottom-color: palette(base);
                padding-bottom: 2px;
                margin-bottom: -1px;
            }

            QTabBar::tab:hover:!selected {
                background: palette(light);
            }

            QTabWidget::pane {
                border: 1px solid palette(mid);
                border-top: 1px solid palette(mid);
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 0.1,
                                           stop: 0 palette(alternate-base),
                                           stop: 1 palette(base));
                top: -1px;
            }

            /* General Rounded Buttons */
            QPushButton {
                border-radius: 8px;
                border: 1px solid palette(light);
                background: palette(button);
            }

            QPushButton:hover {
                background: palette(light);
                border-color: palette(mid);
            }

            QPushButton:pressed {
                background: palette(highlight);
                color: palette(highlighted-text);
                border-color: palette(highlight);
            }

            /* Rounded Keycode Buttons - Using object name selector */
            QPushButton[keycode_button="true"] {
                border-radius: 8px;
                border: 1px solid palette(light);
                background: palette(button);
                font-size: 9pt;
            }

            QPushButton[keycode_button="true"]:hover {
                background: palette(light);
                border-color: palette(mid);
            }

            QPushButton[keycode_button="true"]:pressed {
                background: palette(highlight);
                color: palette(highlighted-text);
                border-color: palette(highlight);
            }

            /* Layer Selection Button Styling */
            QPushButton[keycode_button="true"]:checked {
                background: palette(highlight);
                color: palette(highlighted-text);
                border: 2px solid palette(highlight);
                font-weight: 600;
            }

            /* Modern Dropdown/ComboBox Styling */
            QComboBox {
                border: 1px solid palette(mid);
                border-radius: 6px;
                padding: 6px 12px;
                padding-right: 28px;
                background: palette(button);
                min-width: 80px;
            }

            QComboBox:hover {
                border-color: palette(highlight);
                background: palette(light);
            }

            QComboBox:focus {
                border-color: palette(highlight);
                background: palette(button);
            }

            QComboBox:on {
                background: palette(button);
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
                border: 1px solid palette(mid);
                border-radius: 6px;
                background: palette(button);
                selection-background-color: palette(highlight);
                selection-color: palette(highlighted-text);
                padding: 4px;
                outline: 0px;
            }

            QComboBox QAbstractItemView::item {
                padding: 6px;
                min-height: 24px;
            }

            /* Modern Table Styling with Self-Contained Columns */
            QTableWidget, QTableView {
                border: 1px solid palette(mid);
                border-radius: 8px;
                background: palette(base);
                gridline-color: palette(mid);
                selection-background-color: palette(highlight);
                selection-color: palette(highlighted-text);
            }

            QTableWidget::item, QTableView::item {
                padding: 8px;
                border: 1px solid palette(midlight);
                border-radius: 4px;
                margin: 2px;
            }

            QTableWidget::item:hover, QTableView::item:hover {
                background: palette(alternate-base);
                border-color: palette(highlight);
            }

            QHeaderView::section {
                background: palette(button);
                padding: 10px;
                border: 1px solid palette(mid);
                border-radius: 6px;
                margin: 2px;
                font-weight: 600;
            }

            QHeaderView::section:hover {
                background: palette(light);
            }

            /* Modern Scrollbars - Themed with Oval Shape */
            QScrollBar:vertical {
                background: palette(window);
                width: 14px;
                border-radius: 10px;
                margin: 0px;
            }

            QScrollBar::handle:vertical {
                background: palette(button);
                border-radius: 10px;
                min-height: 30px;
                margin: 2px;
            }

            QScrollBar::handle:vertical:hover {
                background: palette(highlight);
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
                background: palette(window);
                height: 14px;
                border-radius: 10px;
                margin: 0px;
            }

            QScrollBar::handle:horizontal {
                background: palette(button);
                border-radius: 10px;
                min-width: 30px;
                margin: 2px;
            }

            QScrollBar::handle:horizontal:hover {
                background: palette(highlight);
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0px;
            }

            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: none;
            }

            /* Input Boxes - SpinBox and LineEdit Styling */
            QSpinBox, QLineEdit {
                border: 1px solid palette(mid);
                border-radius: 6px;
                padding: 6px 8px;
                background: palette(base);
                selection-background-color: palette(highlight);
                selection-color: palette(highlighted-text);
            }

            QSpinBox:hover, QLineEdit:hover {
                border-color: palette(highlight);
            }

            QSpinBox:focus, QLineEdit:focus {
                border: 2px solid palette(highlight);
                padding: 5px 7px;
            }

            QSpinBox::up-button, QSpinBox::down-button {
                background: palette(button);
                border: 1px solid palette(mid);
                width: 16px;
            }

            QSpinBox::up-button {
                subcontrol-position: top right;
                border-top-right-radius: 5px;
            }

            QSpinBox::down-button {
                subcontrol-position: bottom right;
                border-bottom-right-radius: 5px;
            }

            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: palette(light);
                border-color: palette(highlight);
            }

            QSpinBox::up-arrow, QSpinBox::down-arrow {
                /* Arrows drawn programmatically by ArrowSpinBox */
                width: 10px;
                height: 6px;
            }

            QCheckBox::indicator {
                border: 1px solid palette(mid);
                border-radius: 3px;
                width: 14px;
                height: 14px;
                background-color: palette(base);
            }

            QCheckBox::indicator:hover {
                border-color: palette(highlight);
            }

            QCheckBox::indicator:checked {
                border-color: palette(highlight);
                background-color: palette(highlight);
            }

            /* Inner Tab Buttons - Horizontal tabs like main headers */
            QPushButton[inner_tab="true"] {
                border: 1px solid palette(light);
                margin-right: 2px;
                margin-bottom: 0px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                border-bottom: 1px solid palette(light);
                background: palette(button);
                font-weight: 500;
                font-size: 9pt;
            }

            QPushButton[inner_tab="true"]:hover:!checked {
                background: palette(light);
                border-color: palette(mid);
            }

            QPushButton[inner_tab="true"]:checked {
                background: palette(base);
                border-bottom-color: palette(base);
                margin-bottom: -1px;
            }

            /* Side Tab Buttons - Vertical tabs on left */
            QPushButton[side_tab="true"] {
                border: 1px solid palette(light);
                margin-bottom: 2px;
                margin-right: 0px;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                border-right: 1px solid palette(light);
                background: palette(button);
                text-align: left;
                min-width: 100px;
                font-weight: 500;
                font-size: 9pt;
            }

            QPushButton[side_tab="true"]:hover:!checked {
                background: palette(light);
                border-color: palette(mid);
            }

            QPushButton[side_tab="true"]:checked {
                background: palette(base);
                border-right-color: palette(base);
                margin-right: -1px;
            }
        """

    @classmethod
    def get_button_stylesheet(cls):
        """Return stylesheet for keycode buttons"""
        return """
            QPushButton {
                border-radius: 8px;
                border: 1px solid palette(mid);
            }
        """
