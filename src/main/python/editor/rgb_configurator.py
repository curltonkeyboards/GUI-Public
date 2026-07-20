# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import pyqtSignal, QObject, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QPushButton, QHBoxLayout, QSizePolicy, QGridLayout, QLabel, QSlider, \
    QComboBox, QColorDialog, QCheckBox, QTabWidget, QMenu, QAction, QScrollArea, QVBoxLayout, QGroupBox, \
    QStackedWidget

from widgets.combo_box import ArrowComboBox
from widgets.keyboard_widget import KeyboardWidget2, KeyboardWidgetSimple, KeyboardWidgetNoHighlight
from editor.basic_editor import BasicEditor
from widgets.clickable_label import ClickableLabel
from util import tr
from vial_device import VialKeyboard
from protocol.constants import CMD_VIA_VIAL_PREFIX, CMD_VIAL_LAYER_RGB_SAVE, CMD_VIAL_LAYER_RGB_LOAD, \
    CMD_VIAL_LAYER_RGB_ENABLE, CMD_VIAL_LAYER_RGB_GET_STATUS, CMD_VIAL_CUSTOM_ANIM_SET_PARAM, \
    CMD_VIAL_CUSTOM_ANIM_GET_PARAM, CMD_VIAL_CUSTOM_ANIM_SET_ALL, CMD_VIAL_CUSTOM_ANIM_GET_ALL, \
    CMD_VIAL_CUSTOM_ANIM_SAVE, CMD_VIAL_CUSTOM_ANIM_LOAD, CMD_VIAL_CUSTOM_ANIM_RESET_SLOT, \
    CMD_VIAL_CUSTOM_ANIM_GET_STATUS, CMD_VIAL_CUSTOM_ANIM_RESCAN_LEDS, CMD_VIAL_PER_KEY_GET_PALETTE, \
    CMD_VIAL_PER_KEY_SET_PALETTE_COLOR, CMD_VIAL_PER_KEY_GET_PRESET_DATA, CMD_VIAL_PER_KEY_SET_LED_COLOR, \
    CMD_VIAL_PER_KEY_SAVE, CMD_VIAL_PER_KEY_LOAD, \
    HID_CMD_FUNC_LED_GET, HID_CMD_FUNC_LED_SET, HID_CMD_FUNC_LED_SAVE, FUNC_LED_STATE_COUNT
import time

NUM_CUSTOM_SLOTS = 50  # Change this to your desi5red number

class QmkRgblightEffect:

    def __init__(self, idx, name, color_picker):
        self.idx = idx
        self.name = name
        self.color_picker = color_picker


QMK_RGBLIGHT_EFFECTS = [
    QmkRgblightEffect(0, "All Off", False),
    QmkRgblightEffect(1, "Solid Color", True),
    QmkRgblightEffect(2, "Breathing 1", True),
    QmkRgblightEffect(3, "Breathing 2", True),
    QmkRgblightEffect(4, "Breathing 3", True),
    QmkRgblightEffect(5, "Breathing 4", True),
    QmkRgblightEffect(6, "Rainbow Mood 1", False),
    QmkRgblightEffect(7, "Rainbow Mood 2", False),
    QmkRgblightEffect(8, "Rainbow Mood 3", False),
    QmkRgblightEffect(9, "Rainbow Swirl 1", False),
    QmkRgblightEffect(10, "Rainbow Swirl 2", False),
    QmkRgblightEffect(11, "Rainbow Swirl 3", False),
    QmkRgblightEffect(12, "Rainbow Swirl 4", False),
    QmkRgblightEffect(13, "Rainbow Swirl 5", False),
    QmkRgblightEffect(14, "Rainbow Swirl 6", False),
    QmkRgblightEffect(15, "Snake 1", True),
    QmkRgblightEffect(16, "Snake 2", True),
    QmkRgblightEffect(17, "Snake 3", True),
    QmkRgblightEffect(18, "Snake 4", True),
    QmkRgblightEffect(19, "Snake 5", True),
    QmkRgblightEffect(20, "Snake 6", True),
    QmkRgblightEffect(21, "Knight 1", True),
    QmkRgblightEffect(22, "Knight 2", True),
    QmkRgblightEffect(23, "Knight 3", True),
    QmkRgblightEffect(24, "Christmas", True),
    QmkRgblightEffect(25, "Gradient 1", True),
    QmkRgblightEffect(26, "Gradient 2", True),
    QmkRgblightEffect(27, "Gradient 3", True),
    QmkRgblightEffect(28, "Gradient 4", True),
    QmkRgblightEffect(29, "Gradient 5", True),
    QmkRgblightEffect(30, "Gradient 6", True),
    QmkRgblightEffect(31, "Gradient 7", True),
    QmkRgblightEffect(32, "Gradient 8", True),
    QmkRgblightEffect(33, "Gradient 9", True),
    QmkRgblightEffect(34, "Gradient 10", True),
    QmkRgblightEffect(35, "RGB Test", True),
    QmkRgblightEffect(36, "Alternating", True),
]


class VialRGBEffect:

    def __init__(self, idx, name):
        self.idx = idx
        self.name = name


VIALRGB_EFFECTS = [
    VialRGBEffect(0, "Disable"),
    VialRGBEffect(1, "Direct Control"),
    VialRGBEffect(2, "Solid Color"),
    VialRGBEffect(3, "Alphas Mods"),
    VialRGBEffect(4, "Gradient Column"),
    VialRGBEffect(5, "Gradient Row"),
    VialRGBEffect(6, "Breathing"),
    VialRGBEffect(7, "Band Sat"),
    VialRGBEffect(8, "Band Val"),
    VialRGBEffect(9, "Band Pinwheel Sat"),
    VialRGBEffect(10, "Band Pinwheel Val"),
    VialRGBEffect(11, "Band Spiral Sat"),
    VialRGBEffect(12, "Band Spiral Val"),
    VialRGBEffect(13, "Cycle All"),
    VialRGBEffect(14, "Cycle Row"),
    VialRGBEffect(15, "Cycle Column"),
    VialRGBEffect(16, "Rainbow Moving Chevron"),
    VialRGBEffect(17, "Cycle Out In"),
    VialRGBEffect(18, "Cycle Out In Dual"),
    VialRGBEffect(19, "Cycle Pinwheel"),
    VialRGBEffect(20, "Cycle Spiral"),
    VialRGBEffect(21, "Dual Beacon"),
    VialRGBEffect(22, "Rainbow Beacon"),
    VialRGBEffect(23, "Rainbow Pinwheels"),
    VialRGBEffect(24, "Raindrops"),
    VialRGBEffect(25, "Jellybean Raindrops"),
    VialRGBEffect(26, "Hue Breathing"),
    VialRGBEffect(27, "Hue Pendulum"),
    VialRGBEffect(28, "Hue Wave"),
    VialRGBEffect(29, "Typing Heatmap"),
    VialRGBEffect(30, "Digital Rain"),
    VialRGBEffect(31, "Solid Reactive Simple"),
    VialRGBEffect(32, "Solid Reactive"),
    VialRGBEffect(33, "Solid Reactive Wide"),
    VialRGBEffect(34, "Solid Reactive Multiwide"),
    VialRGBEffect(35, "Solid Reactive Cross"),
    VialRGBEffect(36, "Solid Reactive Multicross"),
    VialRGBEffect(37, "Solid Reactive Nexus"),
    VialRGBEffect(38, "Solid Reactive Multinexus"),
    VialRGBEffect(39, "Splash"),
    VialRGBEffect(40, "Multisplash"),
    VialRGBEffect(41, "Solid Splash"),
    VialRGBEffect(42, "Solid Multisplash"),
    VialRGBEffect(43, "Pixel Rain"),
    VialRGBEffect(44, "Pixel Fractal"),
    VialRGBEffect(45, "MIDI Switch Auto Light"),
    VialRGBEffect(46, "Reactive Lightning"),
    VialRGBEffect(47, "Reactive Ripple"),
    VialRGBEffect(48, "Reactive Fireworks"),
    VialRGBEffect(49, "Comet Trail"),
    VialRGBEffect(50, "Tetris Vertical"),
    VialRGBEffect(51, "Tetris Horizontal"),
    VialRGBEffect(52, "Fireplace"),
    VialRGBEffect(53, "Pong"),
    VialRGBEffect(54, "L/R Sweep Static"),
    VialRGBEffect(55, "L/R Sweep Rainbow"),
    VialRGBEffect(56, "L/R Sweep Random"),
    # Per Key RGB Presets (57-68)
    VialRGBEffect(57, "Per Key 1"),
    VialRGBEffect(58, "Per Key 2"),
    VialRGBEffect(59, "Per Key 3"),
    VialRGBEffect(60, "Per Key 4"),
    VialRGBEffect(61, "Per Key 5"),
    VialRGBEffect(62, "Per Key 6"),
    VialRGBEffect(63, "Per Key 7"),
    VialRGBEffect(64, "Per Key 8"),
    VialRGBEffect(65, "Per Key 9"),
    VialRGBEffect(66, "Per Key 10"),
    VialRGBEffect(67, "Per Key 11"),
    VialRGBEffect(68, "Per Key 12"),
    # Random Effects (69-77)
    VialRGBEffect(69, "Random 1 - Loop"),
    VialRGBEffect(70, "Random 2 - Loop"),
    VialRGBEffect(71, "Random 3 - Loop"),
    VialRGBEffect(72, "Random 1 - BPM"),
    VialRGBEffect(73, "Random 2 - BPM"),
    VialRGBEffect(74, "Random 3 - BPM"),
    VialRGBEffect(75, "Random 1 - Manual"),
    VialRGBEffect(76, "Random 2 - Manual"),
    VialRGBEffect(77, "Random 3 - Manual"),
    # Custom Animation Slots (78-126)
    VialRGBEffect(78, "Custom Slot 1"),
    VialRGBEffect(79, "Custom Slot 2"),
    VialRGBEffect(80, "Custom Slot 3"),
    VialRGBEffect(81, "Custom Slot 4"),
    VialRGBEffect(82, "Custom Slot 5"),
    VialRGBEffect(83, "Custom Slot 6"),
    VialRGBEffect(84, "Custom Slot 7"),
    VialRGBEffect(85, "Custom Slot 8"),
    VialRGBEffect(86, "Custom Slot 9"),
    VialRGBEffect(87, "Custom Slot 10"),
    VialRGBEffect(88, "Custom Slot 11"),
    VialRGBEffect(89, "Custom Slot 12"),
    VialRGBEffect(90, "Custom Slot 13"),
    VialRGBEffect(91, "Custom Slot 14"),
    VialRGBEffect(92, "Custom Slot 15"),
    VialRGBEffect(93, "Custom Slot 16"),
    VialRGBEffect(94, "Custom Slot 17"),
    VialRGBEffect(95, "Custom Slot 18"),
    VialRGBEffect(96, "Custom Slot 19"),
    VialRGBEffect(97, "Custom Slot 20"),
    VialRGBEffect(98, "Custom Slot 21"),
    VialRGBEffect(99, "Custom Slot 22"),
    VialRGBEffect(100, "Custom Slot 23"),
    VialRGBEffect(101, "Custom Slot 24"),
    VialRGBEffect(102, "Custom Slot 25"),
    VialRGBEffect(103, "Custom Slot 26"),
    VialRGBEffect(104, "Custom Slot 27"),
    VialRGBEffect(105, "Custom Slot 28"),
    VialRGBEffect(106, "Custom Slot 29"),
    VialRGBEffect(107, "Custom Slot 30"),
    VialRGBEffect(108, "Custom Slot 31"),
    VialRGBEffect(109, "Custom Slot 32"),
    VialRGBEffect(110, "Custom Slot 33"),
    VialRGBEffect(111, "Custom Slot 34"),
    VialRGBEffect(112, "Custom Slot 35"),
    VialRGBEffect(113, "Custom Slot 36"),
    VialRGBEffect(114, "Custom Slot 37"),
    VialRGBEffect(115, "Custom Slot 38"),
    VialRGBEffect(116, "Custom Slot 39"),
    VialRGBEffect(117, "Custom Slot 40"),
    VialRGBEffect(118, "Custom Slot 41"),
    VialRGBEffect(119, "Custom Slot 42"),
    VialRGBEffect(120, "Custom Slot 43"),
    VialRGBEffect(121, "Custom Slot 44"),
    VialRGBEffect(122, "Custom Slot 45"),
    VialRGBEffect(123, "Custom Slot 46"),
    VialRGBEffect(124, "Custom Slot 47"),
    VialRGBEffect(125, "Custom Slot 48"),
    VialRGBEffect(126, "Custom Slot 49"),
]


# Hierarchical structure for effects
# Hierarchical structure for effects - COMPLETE REWRITE WITH SHIFTED INDICES
LIVE_EFFECTS_HIERARCHY = {
    "Simple": [
        {"name": "Simple", "index": 0},
        {"name": "Simple Solo", "index": 1}
    ],
    "Wide": [
        {"name": "Wide", "index": 2},
        {"name": "Wide Solo", "index": 3},
        {"name": "Wider", "index": 4},
        {"name": "Wider Solo", "index": 5}
    ],
    "Heatmap": [
        {"name": "Heatmap", "index": 6},
        {"name": "Heatmap 2", "index": 7}
    ],
    "Columns": [
        {"name": "Column", "index": 8},
        {"name": "Column Solo", "index": 9}
    ],
    "Rows": [
        {"name": "Row", "index": 10},
        {"name": "Row Solo", "index": 11}
    ],
    "Expanding Row": [
        {"name": "Growing Row Short", "index": 52},
        {"name": "Growing Row Short Solo", "index": 53},
        {"name": "Growing Row Long", "index": 54},
        {"name": "Growing Row Long Solo", "index": 55}
    ],
    "Expanding Column": [
        {"name": "Growing Column Short", "index": 56},
        {"name": "Growing Column Short Solo", "index": 57},
        {"name": "Growing Column Long", "index": 58},
        {"name": "Growing Column Long Solo", "index": 59}
    ],
    "Collapsing Column": [
        {"name": "Collapsing Column Small", "index": 86},
        {"name": "Collapsing Column Small Solo", "index": 87},
        {"name": "Collapsing Column Small Wide", "index": 88},
        {"name": "Collapsing Column Small Wide Solo", "index": 89},
        {"name": "Collapsing Column Large", "index": 90},
        {"name": "Collapsing Column Large Solo", "index": 91},
        {"name": "Collapsing Column Large Wide", "index": 92},
        {"name": "Collapsing Column Large Wide Solo", "index": 93}
    ],
    "Collapsing Row": [
        {"name": "Collapsing Row Small", "index": 94},
        {"name": "Collapsing Row Small Solo", "index": 95},
        {"name": "Collapsing Row Small Wide", "index": 96},
        {"name": "Collapsing Row Small Wide Solo", "index": 97},
        {"name": "Collapsing Row Med", "index": 98},
        {"name": "Collapsing Row Med Solo", "index": 99},
        {"name": "Collapsing Row Med Wide", "index": 100},
        {"name": "Collapsing Row Med Wide Solo", "index": 101},
        {"name": "Collapsing Row Large", "index": 102},
        {"name": "Collapsing Row Large Solo", "index": 103},
        {"name": "Collapsing Row Large Wide", "index": 104},
        {"name": "Collapsing Row Large Wide Solo", "index": 105}
    ],
    "Crosses": [
        {"name": "Cross Short", "index": 12},
        {"name": "Cross Short Solo", "index": 13},
        {"name": "Criss Cross", "index": 14},
        {"name": "Criss Cross Solo", "index": 15}
    ],
    "Side Dots": [
        {"name": "Side Dots Short", "index": 16},
        {"name": "Side Dots Short Solo", "index": 17},
        {"name": "Side Dots Long", "index": 18},
        {"name": "Side Dots Long Solo", "index": 19},
        {"name": "Side Dots Short Reverse", "index": 106},
        {"name": "Side Dots Short Reverse Solo", "index": 107},
        {"name": "Side Dots Long Reverse", "index": 108},
        {"name": "Side Dots Long Reverse Solo", "index": 109}
    ],
        
    "Side Dots Large": [
        {"name": "Side Dots Large", "index": 114},
        {"name": "Side Dots Large Solo", "index": 115},
        {"name": "Side Dots Large Long", "index": 116},
        {"name": "Side Dots Large Long Solo", "index": 117},
        {"name": "Side Dots Large Reverse", "index": 118},
        {"name": "Side Dots Large Reverse Solo", "index": 119},
        {"name": "Side Dots Large Reverse Long", "index": 120},
        {"name": "Side Dots Large Reverse Long Solo", "index": 121}
    ],
    
    "Up/Down Dots": [
        {"name": "Up/Down Dots Short", "index": 20},
        {"name": "Up/Down Dots Short Solo", "index": 21},
        {"name": "Up/Down Dots Long", "index": 22},
        {"name": "Up/Down Dots Long Solo", "index": 23},
        {"name": "Up/Down Dots Short Reverse", "index": 110},
        {"name": "Up/Down Dots Short Reverse Solo", "index": 111},
        {"name": "Up/Down Dots Long Reverse", "index": 112},
        {"name": "Up/Down Dots Long Reverse Solo", "index": 113}
    ],

    "Up/Down Dots Large": [
        {"name": "Up/Down Dots Large", "index": 122},
        {"name": "Up/Down Dots Large Solo", "index": 123},
        {"name": "Up/Down Dots Large Long", "index": 124},
        {"name": "Up/Down Dots Large Long Solo", "index": 125},
        {"name": "Up/Down Dots Large Reverse", "index": 126},
        {"name": "Up/Down Dots Large Reverse Solo", "index": 127},
        {"name": "Up/Down Dots Large Reverse Long", "index": 128},
        {"name": "Up/Down Dots Large Reverse Long Solo", "index": 129}
    ],
    
    "Diagonal Dots": [
        {"name": "Diagonal Dots 1", "index": 24},
        {"name": "Diagonal Dots 1 Solo", "index": 25},
        {"name": "Diagonal Dots 2", "index": 26},
        {"name": "Diagonal Dots 2 Solo", "index": 27}
    ],
    
    "Diagonal Dots Large": [
        {"name": "Diagonal Burst", "index": 32},
        {"name": "Diagonal Burst Solo", "index": 33},
        {"name": "Criss Cross Dots", "index": 34},
        {"name": "Criss Cross Dots Solo", "index": 35}
    ],
    
    "Cross Dots": [
        {"name": "Cross Dots Short", "index": 28},
        {"name": "Cross Dots Short Solo", "index": 29},
        {"name": "Cross Dots Long", "index": 30},
        {"name": "Cross Dots Long Solo", "index": 31},
        {"name": "Cross Dots Reverse", "index": 146},
        {"name": "Cross Dots Reverse Solo", "index": 147},
        {"name": "Cross Dots Reverse Long", "index": 148},
        {"name": "Cross Dots Reverse Long Solo", "index": 149},
    ],

    "Cross Dots Large": [    
        {"name": "Cross Dots Large", "index": 150},
        {"name": "Cross Dots Large Solo", "index": 151},
        {"name": "Cross Dots Long Large", "index": 152},
        {"name": "Cross Dots Long Large Solo", "index": 153},
        {"name": "Cross Dots Large Reverse", "index": 154},
        {"name": "Cross Dots Large Reverse Solo", "index": 155},
        {"name": "Cross Dots Long Reverse Large", "index": 156},
        {"name": "Cross Dots Long Reverse Large Solo", "index": 157},
    ],

    "Ripple": [
        {"name": "Ripple Small", "index": 36},
        {"name": "Ripple Small Solo", "index": 37},
        {"name": "Ripple Med", "index": 38},
        {"name": "Ripple Med Solo", "index": 39},
        {"name": "Ripple Large", "index": 40},
        {"name": "Ripple Large Solo", "index": 41},
        {"name": "Ripple Massive", "index": 42},
        {"name": "Ripple Massive Solo", "index": 43}
    ],
    "Target": [
        {"name": "Target Small", "index": 44},
        {"name": "Target Small Solo", "index": 48},
        {"name": "Target Med", "index": 45},
        {"name": "Target Med Solo", "index": 49},
        {"name": "Target Large", "index": 46},
        {"name": "Target Large Solo", "index": 50},
        {"name": "Target Massive", "index": 47},
        {"name": "Target Massive Solo", "index": 51}
    ],
    "Firework": [
        {"name": "Firework Small", "index": 60},
        {"name": "Firework Small Solo", "index": 61},
        {"name": "Firework Med", "index": 62},
        {"name": "Firework Med Solo", "index": 63},
        {"name": "Firework Large", "index": 64},
        {"name": "Firework Large Solo", "index": 65}
    ],
    "Collapsing Star": [
        {"name": "Collapsing Star Small", "index": 166},
        {"name": "Collapsing Star Small Solo", "index": 167},
        {"name": "Collapsing Star Med", "index": 168},
        {"name": "Collapsing Star Med Solo", "index": 169},
        {"name": "Collapsing Star Large", "index": 170},
        {"name": "Collapsing Star Large Solo", "index": 171}
    ],
    "Volume Bars": [
        {"name": "Volume Bars Small", "index": 66},
        {"name": "Volume Bars Small Solo", "index": 67},
        {"name": "Volume Bars Small Wide", "index": 68},
        {"name": "Volume Bars Small Wide Solo", "index": 69},
        {"name": "Volume Bars Large", "index": 70},
        {"name": "Volume Bars Large Solo", "index": 71},
        {"name": "Volume Bars Large Wide", "index": 72},
        {"name": "Volume Bars Large Wide Solo", "index": 73}
    ],
    "Volume Rows": [
        {"name": "Volume Rows Small", "index": 74},
        {"name": "Volume Rows Small Solo", "index": 75},
        {"name": "Volume Rows Small Wide", "index": 76},
        {"name": "Volume Rows Small Wide Solo", "index": 77},
        {"name": "Volume Rows Med", "index": 78},
        {"name": "Volume Rows Med Solo", "index": 79},
        {"name": "Volume Rows Med Wide", "index": 80},
        {"name": "Volume Rows Med Wide Solo", "index": 81},
        {"name": "Volume Rows Large", "index": 82},
        {"name": "Volume Rows Large Solo", "index": 83},
        {"name": "Volume Rows Large Wide", "index": 84},
        {"name": "Volume Rows Large Wide Solo", "index": 85}
    ],
    "Side Lines": [
        {"name": "Side Lines", "index": 130},
        {"name": "Side Lines Solo", "index": 131},
        {"name": "Side Lines Long", "index": 132},
        {"name": "Side Lines Long Solo", "index": 133},
        {"name": "Side Lines Reverse", "index": 134},
        {"name": "Side Lines Reverse Solo", "index": 135},
        {"name": "Side Lines Reverse Long", "index": 136},
        {"name": "Side Lines Reverse Long Solo", "index": 137}
    ],
    "Up/Down Lines": [
        {"name": "Up/Down Lines", "index": 138},
        {"name": "Up/Down Lines Solo", "index": 139},
        {"name": "Up/Down Lines Long", "index": 140},
        {"name": "Up/Down Lines Long Solo", "index": 141},
        {"name": "Up/Down Lines Reverse", "index": 142},
        {"name": "Up/Down Lines Reverse Solo", "index": 143},
        {"name": "Up/Down Lines Reverse Long", "index": 144},
        {"name": "Up/Down Lines Reverse Long Solo", "index": 145}
    ],
    "Cross Lines": [
        {"name": "Cross Lines", "index": 158},
        {"name": "Cross Lines Solo", "index": 159},
        {"name": "Cross Lines Long", "index": 160},
        {"name": "Cross Lines Long Solo", "index": 161},
        {"name": "Cross Lines Reverse", "index": 162},
        {"name": "Cross Lines Reverse Solo", "index": 163},
        {"name": "Cross Lines Reverse Long", "index": 164},
        {"name": "Cross Lines Reverse Long Solo", "index": 165}
    ]
}


# Hierarchical structure for backgrounds
BACKGROUNDS_HIERARCHY = {
    "None": [
        {"name": "None", "index": 0},
    ],
    "Basic": [
        {"name": "Basic", "index": 1},
        {"name": "Basic Desaturated", "index": 79},
        {"name": "Basic 2", "index": 2},
        {"name": "Basic 2 Desaturated", "index": 80},
        {"name": "Basic 3", "index": 3},
        {"name": "Basic 3 Desaturated", "index": 81},
        {"name": "Basic 4", "index": 4},
        {"name": "Basic 4 Desaturated", "index": 82},
    ],
    "Autolight": [
        {"name": "Autolight", "index": 5},
        {"name": "Autolight Desaturated", "index": 83},
        {"name": "Autolight 2", "index": 6},
        {"name": "Autolight 2 Desaturated", "index": 84},
        {"name": "Autolight Cycle", "index": 7},
        {"name": "Autolight Cycle Desaturated", "index": 85},
        {"name": "Autolight Breathing", "index": 8},
        {"name": "Autolight Breathing Desaturated", "index": 86},
    ],
    "Cycle Effects": [
        {"name": "Cycle All", "index": 59},
        {"name": "Cycle All Desaturated", "index": 87},
        {"name": "Cycle Left Right", "index": 60},
        {"name": "Cycle Left Right Desaturated", "index": 88},
        {"name": "Cycle Up Down", "index": 61},
        {"name": "Cycle Up Down Desaturated", "index": 89},
        {"name": "Cycle Out In", "index": 62},
        {"name": "Cycle Out In Desaturated", "index": 90},
        {"name": "Cycle Out In Dual", "index": 63},
        {"name": "Cycle Out In Dual Desaturated", "index": 91},
        {"name": "Rainbow Pinwheel", "index": 64},
        {"name": "Rainbow Pinwheel Desaturated", "index": 92},
    ],
    "Wave Effects": [
        {"name": "Wave Left Right", "index": 66},
        {"name": "Wave Left Right Desaturated", "index": 94},
        {"name": "Diagonal Wave", "index": 67},
        {"name": "Diagonal Wave Desaturated", "index": 95},
        {"name": "Diagonal Wave Hue Cycle", "index": 107},
        {"name": "Diagonal Wave Hue Cycle Desaturated", "index": 114},
        {"name": "Diagonal Wave Dual Color", "index": 108},
        {"name": "Diagonal Wave Dual Color Desaturated", "index": 115},
        {"name": "Diagonal Wave Dual Hue Cycle", "index": 109},
        {"name": "Diagonal Wave Dual Hue Cycle Desaturated", "index": 116},
        {"name": "Diagonal Wave Reverse", "index": 110},
        {"name": "Diagonal Wave Reverse Desaturated", "index": 117},
        {"name": "Diagonal Wave Reverse Hue Cycle", "index": 111},
        {"name": "Diagonal Wave Reverse Hue Cycle Desaturated", "index": 118},
        {"name": "Diagonal Wave Reverse Dual Color", "index": 112},
        {"name": "Diagonal Wave Reverse Dual Color Desaturated", "index": 119},
        {"name": "Diagonal Wave Reverse Dual Hue Cycle", "index": 113},
        {"name": "Diagonal Wave Reverse Dual Hue Cycle Desaturated", "index": 120},
    ],
    "Breathing Effects": [
        {"name": "Breathing", "index": 65},
        {"name": "Breathing Desaturated", "index": 93},
    ],
    "Gradient Effects": [
        {"name": "Gradient Up Down", "index": 68},
        {"name": "Gradient Up Down Desaturated", "index": 96},
        {"name": "Gradient Left Right", "index": 69},
        {"name": "Gradient Left Right Desaturated", "index": 97},
        {"name": "Gradient Diagonal", "index": 70},
        {"name": "Gradient Diagonal Desaturated", "index": 98},
    ],
    "Hue Effects": [
        {"name": "Hue Breathing", "index": 71},
        {"name": "Hue Breathing Desaturated", "index": 99},
        {"name": "Hue Pendulum", "index": 72},
        {"name": "Hue Pendulum Desaturated", "index": 100},
        {"name": "Hue Wave", "index": 73},
        {"name": "Hue Wave Desaturated", "index": 101},
    ],
    "Rainbow Effects": [
        {"name": "Rainbow Moving Chevron", "index": 74},
        {"name": "Rainbow Moving Chevron Desaturated", "index": 102},
    ],
    "Band Effects": [
        {"name": "Band Pinwheel Sat", "index": 75},
        {"name": "Band Pinwheel Sat Desaturated", "index": 103},
        {"name": "Band Pinwheel Val", "index": 76},
        {"name": "Band Pinwheel Val Desaturated", "index": 104},
        {"name": "Band Spiral Sat", "index": 77},
        {"name": "Band Spiral Sat Desaturated", "index": 105},
        {"name": "Band Spiral Val", "index": 78},
        {"name": "Band Spiral Val Desaturated", "index": 106},
    ],
        "BPM Pulse Fade": [
        {"name": "BPM Pulse Fade", "index": 9},
        {"name": "BPM Pulse Fade 2", "index": 10},
        {"name": "BPM Pulse Fade Desaturated", "index": 11},
        {"name": "BPM Pulse Fade Disco", "index": 12},
        {"name": "BPM Pulse Fade Solid Background", "index": 13},
        {"name": "BPM Pulse Fade Solid Background 2", "index": 14},
        {"name": "BPM Pulse Fade Solid Disco", "index": 15},
        {"name": "BPM Pulse Fade Autolight", "index": 16},
        {"name": "BPM Pulse Fade Autolight 2", "index": 17},
        {"name": "BPM Pulse Fade Autolight Disco", "index": 18},
    ],
    "BPM Quadrants": [
        {"name": "BPM Quadrants", "index": 19},
        {"name": "BPM Quadrants 2", "index": 20},
        {"name": "BPM Quadrants Desaturated", "index": 21},
        {"name": "BPM Quadrants Disco", "index": 22},
        {"name": "BPM Quadrants Solid Background", "index": 23},
        {"name": "BPM Quadrants Solid Background 2", "index": 24},
        {"name": "BPM Quadrants Solid Disco", "index": 25},
        {"name": "BPM Quadrants Autolight", "index": 26},
        {"name": "BPM Quadrants Autolight 2", "index": 27},
        {"name": "BPM Quadrants Autolight Disco", "index": 28},
    ],
    "BPM Row": [
        {"name": "BPM Row", "index": 29},
        {"name": "BPM Row 2", "index": 30},
        {"name": "BPM Row Desaturated", "index": 31},
        {"name": "BPM Row Disco", "index": 32},
        {"name": "BPM Row Solid Background", "index": 33},
        {"name": "BPM Row Solid Background 2", "index": 34},
        {"name": "BPM Row Solid Disco", "index": 35},
        {"name": "BPM Row Autolight", "index": 36},
        {"name": "BPM Row Autolight 2", "index": 37},
        {"name": "BPM Row Autolight Disco", "index": 38},
    ],
    "BPM Column": [
        {"name": "BPM Column", "index": 39},
        {"name": "BPM Column 2", "index": 40},
        {"name": "BPM Column Desaturated", "index": 41},
        {"name": "BPM Column Disco", "index": 42},
        {"name": "BPM Column Solid Background", "index": 43},
        {"name": "BPM Column Solid Background 2", "index": 44},
        {"name": "BPM Column Solid Disco", "index": 45},
        {"name": "BPM Column Autolight", "index": 46},
        {"name": "BPM Column Autolight 2", "index": 47},
        {"name": "BPM Column Autolight Disco", "index": 48},
    ],
    "BPM All": [
        {"name": "BPM All", "index": 49},
        {"name": "BPM All 2", "index": 50},
        {"name": "BPM All Desaturated", "index": 51},
        {"name": "BPM All Disco", "index": 52},
        {"name": "BPM All Solid Background", "index": 53},
        {"name": "BPM All Solid Background 2", "index": 54},
        {"name": "BPM All Solid Disco", "index": 55},
        {"name": "BPM All Autolight", "index": 56},
        {"name": "BPM All Autolight 2", "index": 57},
        {"name": "BPM All Autolight Disco", "index": 58},
    ],
    "Per Key Layers": [
        {"name": "Per Key 1", "index": 57},
        {"name": "Per Key 2", "index": 58},
        {"name": "Per Key 3", "index": 59},
        {"name": "Per Key 4", "index": 60},
        {"name": "Per Key 5", "index": 61},
        {"name": "Per Key 6", "index": 62},
        {"name": "Per Key 7", "index": 63},
        {"name": "Per Key 8", "index": 64},
        {"name": "Per Key 9", "index": 65},
        {"name": "Per Key 10", "index": 66},
        {"name": "Per Key 11", "index": 67},
        {"name": "Per Key 12", "index": 68},
    ]
}

# Hierarchical structure for live positioning styles
LIVE_STYLES_HIERARCHY = {
    "Basic Positions": [
        {"name": "TrueKey", "index": 0},
        {"name": "Zone", "index": 1},
        {"name": "Zone 2", "index": 23},
        {"name": "Zone 3", "index": 24},
    ],
    "Count to 8": [
        {"name": "Count to 8", "index": 25},
    ],
    "Pitch Mapping": [
        {"name": "Pitch Mapping 1", "index": 26},
        {"name": "Pitch Mapping 2", "index": 27},
        {"name": "Pitch Mapping 3", "index": 28},
        {"name": "Pitch Mapping 4", "index": 29},
    ],
    "Region-Based": [
        {"name": "Center Zones", "index": 2},
        {"name": "Center Block", "index": 31},
        {"name": "Snake", "index": 30},
    ],
    "Note Row Positions": [
        {"name": "Left Edge", "index": 3},
        {"name": "Right Edge", "index": 4},
        {"name": "Top Edge", "index": 6},
        {"name": "Bottom Edge", "index": 7},
        {"name": "Left and Right Edges", "index": 9},
        {"name": "Top and Bottom Edges", "index": 10},
        {"name": "Middle Row", "index": 8}, 
        {"name": "Middle Column", "index": 5},            
    ],
    "Single Dots": [
        {"name": "Top Dot", "index": 11},
        {"name": "Left Dot", "index": 12},
        {"name": "Right Dot", "index": 13},
        {"name": "Bottom Dot", "index": 14},
        {"name": "Center Dot", "index": 15},
        {"name": "Top Left Dot", "index": 16},
        {"name": "Top Right Dot", "index": 17},
        {"name": "Bottom Left Dot", "index": 18},
        {"name": "Bottom Right Dot", "index": 19},
    ],
    "Group Dots": [
        {"name": "Corner Dots", "index": 20},
        {"name": "Edge Dots", "index": 21},
        {"name": "All Dots", "index": 22},
        {"name": "Close Dots 1", "index": 32},
        {"name": "Close Dots 2", "index": 33},
    ],
}

# Hierarchical structure for macro positioning styles
MACRO_STYLES_HIERARCHY = {
    "Basic Positions": [
        {"name": "TrueKey", "index": 0},
        {"name": "Zone", "index": 1},
        {"name": "Zone 2", "index": 34},
        {"name": "Zone 3", "index": 35},
    ],

    "Count to 8": [
        {"name": "Count to 8", "index": 36},
        {"name": "Loop Count to 8", "index": 37},
    ],
    "Pitch Mapping": [
        {"name": "Pitch Mapping 1", "index": 38},
        {"name": "Pitch Mapping 2", "index": 39},
        {"name": "Pitch Mapping 3", "index": 40},
        {"name": "Pitch Mapping 4", "index": 41},
    ],

    "Region-Based": [
        {"name": "Loop Quadrant Corners", "index": 2},
        {"name": "Loop Quadrant Central", "index": 44},
        {"name": "Loop Blocks", "index": 18},
        {"name": "Center Block Small", "index": 19},
        {"name": "Center Block Large", "index": 43},   
        {"name": "Snake", "index": 42},        
    ],
    "Note Row Positions": [
        {"name": "Left Edge", "index": 3},
        {"name": "Right Edge", "index": 4},
        {"name": "Top Edge", "index": 6},
        {"name": "Bottom Edge", "index": 7},
        {"name": "Left and Right Edges", "index": 9},
        {"name": "Top and Bottom Edges", "index": 10},
        {"name": "Middle Row", "index": 8},
        {"name": "Middle Column", "index": 5},

    ],
    "Loop Row Positions": [
        {"name": "Loop Left Edge", "index": 11},
        {"name": "Loop Right Edge", "index": 12},
        {"name": "Loop Top Edge", "index": 15},
        {"name": "Loop Bottom Edge", "index": 16},
        {"name": "Loop Middle Row", "index": 17},
        {"name": "Loop Middle Column", "index": 13},
        {"name": "Loop Left and Right Edges", "index": 14},
    ],
    "Single Dots": [
        {"name": "Top Dot", "index": 20},
        {"name": "Left Dot", "index": 21},
        {"name": "Right Dot", "index": 22},
        {"name": "Bottom Dot", "index": 23},
        {"name": "Center Dot", "index": 24},
        {"name": "Top Left Dot", "index": 25},
        {"name": "Top Right Dot", "index": 26},
        {"name": "Bottom Left Dot", "index": 27},
        {"name": "Bottom Right Dot", "index": 28},
    ],

    "Group Dots": [
        {"name": "Corner Dots", "index": 29},
        {"name": "Edge Dots", "index": 30},
        {"name": "Loop Corner Dots", "index": 32},
        {"name": "Loop Edge Dots", "index": 33},
        {"name": "All Dots", "index": 31},        
        {"name": "Close Dots 1", "index": 45},
        {"name": "Close Dots 2", "index": 46},
    ],
}

CUSTOM_LIGHT_COLOR_TYPES_HIERARCHY = {
    "Basic": [
        {"name": "Synthwave", "index": 65},
        {"name": "Ocean Depth", "index": 66},
        {"name": "Sunset Horizon", "index": 67},
        {"name": "Aurora Borealis", "index": 68},
        {"name": "Forest Canopy", "index": 69},
        {"name": "Desert Mirage", "index": 70},
        {"name": "Volcanic Flow", "index": 71},
        {"name": "Ice Crystal", "index": 72},
        {"name": "Toxic Waste", "index": 73},
        {"name": "Deep Space", "index": 74},
        {"name": "Crystal Cave", "index": 75},
        {"name": "Enchanted Forest", "index": 76},
        {"name": "Rose Garden", "index": 77},
        {"name": "Tropical Paradise", "index": 78},
        {"name": "Cherry Blossom", "index": 79},
        {"name": "Autumn Leaves", "index": 80},
        {"name": "Neon City", "index": 81},
        {"name": "Cyberpunk Alley", "index": 82},
        {"name": "Matrix Code", "index": 83},
        {"name": "Retro Arcade", "index": 84},
    ],
    "Modular": [
        {"name": "Base", "index": 0},
        {"name": "Channel", "index": 1},
        {"name": "Loop", "index": 2},
        {"name": "Rainbow", "index": 3},
        {"name": "Pitch 1", "index": 4},
        {"name": "Pitch 2", "index": 5},
    ],
    "Modular Sat": [
        {"name": "Base Sat", "index": 6},
        {"name": "Channel Sat", "index": 7},
        {"name": "Macro Sat", "index": 8},
        {"name": "Rainbow Sat", "index": 9},
        {"name": "Pitch 1 Sat", "index": 10},
        {"name": "Pitch 2 Sat", "index": 11},
    ],
    "Modular Desat": [
        {"name": "Base Desat", "index": 12},
        {"name": "Channel Desat", "index": 13},
        {"name": "Macro Desat", "index": 14},
        {"name": "Rainbow Desat", "index": 15},
        {"name": "Pitch 1 Desat", "index": 16},
        {"name": "Pitch 2 Desat", "index": 17},
    ],
    "Modular Distance": [
        {"name": "Base Distance", "index": 18},
        {"name": "Channel Distance", "index": 19},
        {"name": "Macro Distance", "index": 20},
        {"name": "Rainbow Distance", "index": 21},
        {"name": "Pitch 1 Distance", "index": 22},
        {"name": "Pitch 2 Distance", "index": 23},
    ],
    "Modular Distance + Sat": [
        {"name": "Base Distance Sat", "index": 24},
        {"name": "Channel Distance Sat", "index": 25},
        {"name": "Macro Distance Sat", "index": 26},
        {"name": "Rainbow Distance Sat", "index": 27},
        {"name": "Pitch 1 Distance Sat", "index": 28},
        {"name": "Pitch 2 Distance Sat", "index": 29},
    ],
    "Modular Distance + Desat": [
        {"name": "Base Distance Desat", "index": 30},
        {"name": "Channel Distance Desat", "index": 31},
        {"name": "Macro Distance Desat", "index": 32},
        {"name": "Rainbow Distance Desat", "index": 33},
        {"name": "Pitch 1 Distance Desat", "index": 34},
        {"name": "Pitch 2 Distance Desat", "index": 35},
    ],
    "Special Effects": [
        {"name": "Beat Sync", "index": 36},
        {"name": "Temperature Gradient", "index": 37},
    ],
    "Horizontal Gradients": [
        {"name": "Horizontal Soft", "index": 38},
        {"name": "Horizontal Soft Sat", "index": 39},
        {"name": "Horizontal Soft Desat", "index": 40},
        {"name": "Horizontal Medium", "index": 41},
        {"name": "Horizontal Medium Sat", "index": 42},
        {"name": "Horizontal Medium Desat", "index": 43},
        {"name": "Horizontal Strong", "index": 44},
        {"name": "Horizontal Strong Sat", "index": 45},
        {"name": "Horizontal Strong Desat", "index": 46},
    ],
    "Diagonal Gradients": [
        {"name": "Diagonal Soft", "index": 47},
        {"name": "Diagonal Soft Sat", "index": 48},
        {"name": "Diagonal Soft Desat", "index": 49},
        {"name": "Diagonal Medium", "index": 50},
        {"name": "Diagonal Medium Sat", "index": 51},
        {"name": "Diagonal Medium Desat", "index": 52},
        {"name": "Diagonal Strong", "index": 53},
        {"name": "Diagonal Strong Sat", "index": 54},
        {"name": "Diagonal Strong Desat", "index": 55},
    ],
    "Vertical Gradients": [
        {"name": "Vertical Soft", "index": 56},
        {"name": "Vertical Soft Sat", "index": 57},
        {"name": "Vertical Soft Desat", "index": 58},
        {"name": "Vertical Medium", "index": 59},
        {"name": "Vertical Medium Sat", "index": 60},
        {"name": "Vertical Medium Desat", "index": 61},
        {"name": "Vertical Strong", "index": 62},
        {"name": "Vertical Strong Sat", "index": 63},
        {"name": "Vertical Strong Desat", "index": 64},
    ]
}

# Keep the old list for backward compatibility in validation functions
CUSTOM_LIGHT_COLOR_TYPES = [
    "Base",              # 0
    "Channel",           # 1  
    "Macro",             # 2
    "Heat",              # 3
    "Rainbow",           # 4
    "Channel Distance",  # 5
    "Macro Split",       # 6
    "Macro Distance",    # 7
    "Disco Live",        # 8
    "Disco All",         # 9
    "Channel SAT",       # 10
    "Macro SAT",         # 11
    "Velocity Colors",   # 12
    "Time Shift",        # 13
    "Beat Sync",         # 14
    "Temperature Gradient", # 15
    "Spectrum Cycle"     # 16
]


CUSTOM_LIGHT_PRESETS = [
    "Classic TrueKey", "Heat Effects", "Moving Dots", "BPM Disco",
    "Zone Lighting", "Sustain Mode", "Performance Setup"
]


class HierarchicalDropdown(QPushButton):
    """Custom dropdown that supports hierarchical menus"""
    
    valueChanged = pyqtSignal(int)
    
    def __init__(self, hierarchy_dict, parent=None):
        super().__init__(parent)
        self.hierarchy = hierarchy_dict
        self.current_index = 0
        self.current_text = ""
        self.setText("Select...")
        
        # Build the menu
        self.menu = QMenu(self)
        self.build_menu()
        self.setMenu(self.menu)
    
    def build_menu(self):
        """Build hierarchical menu from dictionary"""
        self.menu.clear()
        
        for category, items in self.hierarchy.items():
            if len(items) == 1:
                # Single item - add directly
                action = QAction(items[0]["name"], self)
                action.triggered.connect(lambda checked, idx=items[0]["index"], name=items[0]["name"]: 
                                       self.select_item(idx, name))
                self.menu.addAction(action)
            else:
                # Multiple items - create submenu
                submenu = QMenu(category, self)
                for item in items:
                    action = QAction(item["name"], submenu)
                    action.triggered.connect(lambda checked, idx=item["index"], name=item["name"]: 
                                           self.select_item(idx, name))
                    submenu.addAction(action)
                self.menu.addMenu(submenu)
    
    def select_item(self, index, name):
        """Handle item selection"""
        self.current_index = index
        self.current_text = name
        self.setText(name)
        self.valueChanged.emit(index)
    
    def setCurrentIndex(self, index):
        """Set current selection by index"""
        # Find the item with this index
        for category, items in self.hierarchy.items():
            for item in items:
                if item["index"] == index:
                    self.current_index = index
                    self.current_text = item["name"]
                    self.setText(item["name"])
                    return
        
        # If not found, set to first item
        if self.hierarchy:
            first_category = list(self.hierarchy.keys())[0]
            first_item = self.hierarchy[first_category][0]
            self.current_index = first_item["index"]
            self.current_text = first_item["name"]
            self.setText(first_item["name"])
    
    def currentIndex(self):
        """Get current index"""
        return self.current_index
    
    def blockSignals(self, block):
        """Override to maintain compatibility"""
        super().blockSignals(block)


class BasicHandler(QObject):

    update = pyqtSignal()

    def __init__(self, container):
        super().__init__()
        self.device = self.keyboard = None
        self.widgets = []

    def set_device(self, device):
        self.device = device
        if self.valid():
            self.keyboard = self.device.keyboard
            self.show()
        else:
            self.hide()

    def show(self):
        for w in self.widgets:
            w.show()

    def hide(self):
        for w in self.widgets:
            w.hide()

    def block_signals(self):
        for w in self.widgets:
            w.blockSignals(True)

    def unblock_signals(self):
        for w in self.widgets:
            w.blockSignals(False)

    def update_from_keyboard(self):
        raise NotImplementedError

    def valid(self):
        raise NotImplementedError


class QmkRgblightHandler(BasicHandler):

    def __init__(self, container):
        super().__init__(container)

        row = container.rowCount()

        self.lbl_underglow_effect = QLabel(tr("RGBConfigurator", "Underglow Effect"))
        container.addWidget(self.lbl_underglow_effect, row, 0)
        self.underglow_effect = ArrowComboBox()
        self.underglow_effect.setStyleSheet("QComboBox { border-radius: 5px; }")
        for ef in QMK_RGBLIGHT_EFFECTS:
            self.underglow_effect.addItem(ef.name)
        container.addWidget(self.underglow_effect, row, 1)

        self.lbl_underglow_brightness = QLabel(tr("RGBConfigurator", "Underglow Brightness"))
        container.addWidget(self.lbl_underglow_brightness, row + 1, 0)
        self.underglow_brightness = QSlider(QtCore.Qt.Horizontal)
        self.underglow_brightness.setMinimum(0)
        self.underglow_brightness.setMaximum(255)
        self.underglow_brightness.valueChanged.connect(self.on_underglow_brightness_changed)
        container.addWidget(self.underglow_brightness, row + 1, 1)

        self.lbl_underglow_color = QLabel(tr("RGBConfigurator", "Underglow Color"))
        container.addWidget(self.lbl_underglow_color, row + 2, 0)
        self.underglow_color = ClickableLabel(" ")
        self.underglow_color.clicked.connect(self.on_underglow_color)
        container.addWidget(self.underglow_color, row + 2, 1)

        self.underglow_effect.currentIndexChanged.connect(self.on_underglow_effect_changed)

        self.widgets = [self.lbl_underglow_effect, self.underglow_effect, self.lbl_underglow_brightness,
                        self.underglow_brightness, self.lbl_underglow_color, self.underglow_color]

    def update_from_keyboard(self):
        if not self.valid():
            return

        self.underglow_brightness.setValue(self.device.keyboard.underglow_brightness)
        self.underglow_effect.setCurrentIndex(self.device.keyboard.underglow_effect)
        self.underglow_color.setStyleSheet("QWidget { background-color: %s}" % self.current_color().name())

    def valid(self):
        return isinstance(self.device, VialKeyboard) and self.device.keyboard.lighting_qmk_rgblight

    def on_underglow_brightness_changed(self, value):
        self.device.keyboard.set_qmk_rgblight_brightness(value)
        self.update.emit()

    def on_underglow_effect_changed(self, index):
        self.lbl_underglow_color.setVisible(QMK_RGBLIGHT_EFFECTS[index].color_picker)
        self.underglow_color.setVisible(QMK_RGBLIGHT_EFFECTS[index].color_picker)

        self.device.keyboard.set_qmk_rgblight_effect(index)

    def on_underglow_color(self):
        self.dlg_color = QColorDialog()
        self.dlg_color.setModal(True)
        self.dlg_color.finished.connect(self.on_underglow_color_finished)
        self.dlg_color.setCurrentColor(self.current_color())
        self.dlg_color.show()

    def on_underglow_color_finished(self):
        color = self.dlg_color.selectedColor()
        if not color.isValid():
            return
        self.underglow_color.setStyleSheet("QWidget { background-color: %s}" % color.name())
        h, s, v, a = color.getHsvF()
        if h < 0:
            h = 0
        self.device.keyboard.set_qmk_rgblight_color(int(255 * h), int(255 * s), int(255 * v))
        self.update.emit()

    def current_color(self):
        return QColor.fromHsvF(self.device.keyboard.underglow_color[0] / 255.0,
                               self.device.keyboard.underglow_color[1] / 255.0,
                               self.device.keyboard.underglow_brightness / 255.0)


class QmkBacklightHandler(BasicHandler):

    def __init__(self, container):
        super().__init__(container)

        row = container.rowCount()

        self.lbl_backlight_brightness = QLabel(tr("RGBConfigurator", "Backlight Brightness"))
        container.addWidget(self.lbl_backlight_brightness, row, 0)
        self.backlight_brightness = QSlider(QtCore.Qt.Horizontal)
        self.backlight_brightness.setMinimum(0)
        self.backlight_brightness.setMaximum(255)
        self.backlight_brightness.valueChanged.connect(self.on_backlight_brightness_changed)
        container.addWidget(self.backlight_brightness, row, 1)

        self.lbl_backlight_breathing = QLabel(tr("RGBConfigurator", "Backlight Breathing"))
        container.addWidget(self.lbl_backlight_breathing, row + 1, 0)
        self.backlight_breathing = QCheckBox()
        self.backlight_breathing.stateChanged.connect(self.on_backlight_breathing_changed)
        container.addWidget(self.backlight_breathing, row + 1, 1)

        self.widgets = [self.lbl_backlight_brightness, self.backlight_brightness, self.lbl_backlight_breathing,
                        self.backlight_breathing]

    def update_from_keyboard(self):
        if not self.valid():
            return

        self.backlight_brightness.setValue(self.device.keyboard.backlight_brightness)
        self.backlight_breathing.setChecked(self.device.keyboard.backlight_effect == 1)

    def valid(self):
        return isinstance(self.device, VialKeyboard) and self.device.keyboard.lighting_qmk_backlight

    def on_backlight_brightness_changed(self, value):
        self.device.keyboard.set_qmk_backlight_brightness(value)

    def on_backlight_breathing_changed(self, checked):
        self.device.keyboard.set_qmk_backlight_effect(int(checked))


class VialRGBHandler(BasicHandler):

    def __init__(self, container):
        super().__init__(container)

        row = container.rowCount()

        self.lbl_rgb_effect = QLabel(tr("RGBConfigurator", "RGB Effect"))
        container.addWidget(self.lbl_rgb_effect, row, 0)
        self.rgb_effect = ArrowComboBox()
        self.rgb_effect.setStyleSheet("QComboBox { border-radius: 5px; }")
        self.rgb_effect.addItem("0")
        self.rgb_effect.addItem("1")
        self.rgb_effect.addItem("2")
        self.rgb_effect.addItem("3")
        self.rgb_effect.currentIndexChanged.connect(self.on_rgb_effect_changed)
        container.addWidget(self.rgb_effect, row, 1)

        self.lbl_rgb_color = QLabel(tr("RGBConfigurator", "RGB Color"))
        container.addWidget(self.lbl_rgb_color, row + 1, 0)
        self.rgb_color = ClickableLabel(" ")
        self.rgb_color.clicked.connect(self.on_rgb_color)
        container.addWidget(self.rgb_color, row + 1, 1)

        self.lbl_rgb_brightness = QLabel(tr("RGBConfigurator", "RGB Brightness"))
        container.addWidget(self.lbl_rgb_brightness, row + 2, 0)
        self.rgb_brightness = QSlider(QtCore.Qt.Horizontal)
        self.rgb_brightness.setMinimum(0)
        self.rgb_brightness.setMaximum(255)
        self.rgb_brightness.valueChanged.connect(self.on_rgb_brightness_changed)
        container.addWidget(self.rgb_brightness, row + 2, 1)

        self.lbl_rgb_speed = QLabel(tr("RGBConfigurator", "RGB Speed"))
        container.addWidget(self.lbl_rgb_speed, row + 3, 0)
        self.rgb_speed = QSlider(QtCore.Qt.Horizontal)
        self.rgb_speed.setMinimum(0)
        self.rgb_speed.setMaximum(255)
        self.rgb_speed.valueChanged.connect(self.on_rgb_speed_changed)
        container.addWidget(self.rgb_speed, row + 3, 1)

        self.widgets = [self.lbl_rgb_effect, self.rgb_effect, self.lbl_rgb_brightness, self.rgb_brightness,
                        self.lbl_rgb_color, self.rgb_color, self.lbl_rgb_speed, self.rgb_speed]

        self.effects = []

    def on_rgb_brightness_changed(self, value):
        self.keyboard.set_vialrgb_brightness(value)

    def on_rgb_speed_changed(self, value):
        self.keyboard.set_vialrgb_speed(value)

    def on_rgb_effect_changed(self, index):
        self.keyboard.set_vialrgb_mode(self.effects[index].idx)

    def on_rgb_color(self):
        self.dlg_color = QColorDialog()
        self.dlg_color.setModal(True)
        self.dlg_color.finished.connect(self.on_rgb_color_finished)
        self.dlg_color.setCurrentColor(self.current_color())
        self.dlg_color.show()

    def on_rgb_color_finished(self):
        color = self.dlg_color.selectedColor()
        if not color.isValid():
            return
        self.rgb_color.setStyleSheet("QWidget { background-color: %s}" % color.name())
        h, s, v, a = color.getHsvF()
        if h < 0:
            h = 0
        self.keyboard.set_vialrgb_color(int(255 * h), int(255 * s), self.keyboard.rgb_hsv[2])
        self.update.emit()

    def current_color(self):
        return QColor.fromHsvF(self.keyboard.rgb_hsv[0] / 255.0,
                               self.keyboard.rgb_hsv[1] / 255.0,
                               1.0)

    def rebuild_effects(self):
        self.effects = []
        for effect in VIALRGB_EFFECTS:
            if effect.idx in self.keyboard.rgb_supported_effects:
                self.effects.append(effect)

        self.rgb_effect.clear()
        for effect in self.effects:
            self.rgb_effect.addItem(effect.name)

    def update_from_keyboard(self):
        if not self.valid():
            return

        self.rebuild_effects()
        for x, effect in enumerate(self.effects):
            if effect.idx == self.keyboard.rgb_mode:
                self.rgb_effect.setCurrentIndex(x)
                break
        self.rgb_brightness.setMaximum(self.keyboard.rgb_maximum_brightness)
        self.rgb_brightness.setValue(self.keyboard.rgb_hsv[2])
        self.rgb_speed.setValue(self.keyboard.rgb_speed)
        self.rgb_color.setStyleSheet("QWidget { background-color: %s}" % self.current_color().name())

    def valid(self):
        return isinstance(self.device, VialKeyboard) and self.device.keyboard.lighting_vialrgb


class RescanButtonHandler(BasicHandler):
    """Handler for Save Settings and Rescan LED Positions buttons"""

    def __init__(self, container):
        super().__init__(container)

        row = container.rowCount()

        # Create horizontal layout for both buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # Save Settings button (90px wide, same height as rescan button)
        self.save_button = QPushButton(tr("RGBConfigurator", "Save Settings"))
        self.save_button.clicked.connect(self.on_save_settings)
        self.save_button.setFixedWidth(90)
        self.save_button.setMinimumHeight(30)
        self.save_button.setStyleSheet("QPushButton { border-radius: 5px; padding: 8px; }")
        button_layout.addWidget(self.save_button)

        # Rescan LED Positions button (same height as save button)
        self.rescan_button = QPushButton(tr("RGBConfigurator", "Rescan LED Positions"))
        self.rescan_button.clicked.connect(self.on_rescan_led_positions)
        self.rescan_button.setMinimumHeight(30)
        self.rescan_button.setStyleSheet("QPushButton { border-radius: 5px; padding: 8px; }")
        button_layout.addWidget(self.rescan_button)

        button_layout.addStretch()

        button_widget = QWidget()
        button_widget.setLayout(button_layout)
        container.addWidget(button_widget, row, 0, 1, 2)

        self.widgets = [button_widget]

    def on_save_settings(self):
        """Save RGB settings"""
        if hasattr(self.device, 'keyboard') and hasattr(self.device.keyboard, 'save_rgb'):
            self.device.keyboard.save_rgb()

    def update_from_keyboard(self):
        # No updates needed for this button
        pass

    def valid(self):
        # Always show the rescan button
        return isinstance(self.device, VialKeyboard)

    def on_rescan_led_positions(self):
        """Rescan LED positions and restart the application"""
        try:
            print("Starting LED rescan process...")
            
            # Disable the button to prevent multiple clicks
            self.rescan_button.setEnabled(False)
            self.rescan_button.setText("Rescanning... App will restart in 10 seconds")
            
            # Force immediate GUI update to show disabled state
            from PyQt5.QtWidgets import QApplication, QMessageBox
            QApplication.processEvents()
            
            # Send the rescan command
            if hasattr(self.device.keyboard, 'rescan_led_positions'):
                self.device.keyboard.rescan_led_positions()
                print("Rescan LED command sent")
            else:
                print("Rescan LED method not available")
                self.restore_button()
                return
                
            # Wait 10 seconds for firmware to complete processing
            print("Waiting 10 seconds for firmware to complete...")
            import time
            time.sleep(10.0)
            
            print("LED rescan completed, restarting application...")
            
            # Try to restart the application
            self.restart_application()
            
        except Exception as e:
            print(f"Error during LED rescan process: {e}")
            self.restore_button()

    def restart_application(self):
        """Restart the application or shut down with message"""
        try:
            import sys
            import os
            from PyQt5.QtWidgets import QMessageBox, QApplication
            from PyQt5.QtCore import QTimer
            
            # Try to restart the application
            try:
                print("Attempting to restart application...")
                
                # Get the current executable and arguments
                executable = sys.executable
                args = sys.argv
                
                # Show message about restart
                msg = QMessageBox()
                msg.setWindowTitle("LED Rescan Complete")
                msg.setText("LED positions have been rescanned.\nThe application will now restart to refresh all settings.")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.setIcon(QMessageBox.Information)
                msg.exec_()
                
                # Close current instance and restart
                QApplication.quit()
                os.execv(executable, [executable] + args[1:])
                
            except Exception as restart_error:
                print(f"Could not restart application: {restart_error}")
                
                # Fall back to shutdown with message
                msg = QMessageBox()
                msg.setWindowTitle("LED Rescan Complete - Please Restart")
                msg.setText("LED positions have been rescanned successfully.\n\n"
                           "Please manually restart the application to ensure "
                           "all RGB settings are properly refreshed.\n\n"
                           "The application will now close.")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.setIcon(QMessageBox.Information)
                msg.exec_()
                
                # Shutdown the application
                print("Shutting down application...")
                QApplication.quit()
                sys.exit(0)
                
        except Exception as e:
            print(f"Error during application restart/shutdown: {e}")
            # Emergency shutdown
            import sys
            sys.exit(1)

    def restore_button(self):
        """Restore button to normal state"""
        try:
            self.rescan_button.setEnabled(True)
            self.rescan_button.setText("Rescan LED Positions")
        except Exception as e:
            print(f"Error restoring button: {e}")
            
class LayerRGBHandler(BasicHandler):
    """Handler for per-layer RGB functionality - always shows all buttons"""

    def __init__(self, container):
        super().__init__(container)

        row = container.rowCount()

        # Enable per-layer RGB checkbox
        self.lbl_layer_rgb_enable = QLabel(tr("RGBConfigurator", "Enable Per-Layer RGB"))
        container.addWidget(self.lbl_layer_rgb_enable, row, 0)
        self.layer_rgb_enable = QCheckBox()
        self.layer_rgb_enable.stateChanged.connect(self.on_layer_rgb_enable_changed)
        container.addWidget(self.layer_rgb_enable, row, 1)

        # Layer buttons container
        self.lbl_layer_buttons = QLabel(tr("RGBConfigurator", "Save RGB to Layer"))
        container.addWidget(self.lbl_layer_buttons, row + 1, 0)
        
        # Create a grid layout for layer buttons (3 rows x 4 columns)
        self.layer_buttons_widget = QWidget()
        self.layer_buttons_layout = QGridLayout(self.layer_buttons_widget)
        self.layer_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.layer_buttons_layout.setSpacing(2)  # Smaller spacing between buttons
        container.addWidget(self.layer_buttons_widget, row + 1, 1)

        self.layer_buttons = []
        self.per_layer_enabled = False
        self.initial_load_complete = False  # Track if we've done the initial load
        self.user_set_state = None  # Track what the user manually set

        self.widgets = [self.lbl_layer_rgb_enable, self.layer_rgb_enable, 
                       self.lbl_layer_buttons, self.layer_buttons_widget]

        # Create initial buttons (they will be updated when device connects)
        self.create_layer_buttons()

    def create_layer_buttons(self):
        """Create buttons for each layer in a 3x4 grid - always create 12 buttons regardless of layer count"""
        # Clear existing buttons
        for button in self.layer_buttons:
            button.setParent(None)
        self.layer_buttons.clear()

        # Always create 12 buttons for 3x4 grid regardless of layer count
        for layer in range(12):
            button = QPushButton(f"Layer {layer + 1}")
            button.clicked.connect(lambda checked, l=layer: self.on_save_to_layer(l))
            button.setEnabled(self.per_layer_enabled)
            button.setMaximumWidth(80)  # Set a reasonable button width
            button.setMinimumWidth(60)  # Minimum width for readability
            button.setFixedHeight(35)  # 35px tall
            button.setStyleSheet("QPushButton { border-radius: 5px; }")  # Rounded edges

            # Calculate row and column for 3x4 grid
            row = layer // 4  # 4 buttons per row
            col = layer % 4   # Column position within row

            self.layer_buttons_layout.addWidget(button, row, col)
            self.layer_buttons.append(button)

    def update_from_keyboard(self):
        """Update from keyboard - NEVER update checkbox after initial load"""
        if not self.valid():
            return

        # Block signals to prevent triggering state change events during update
        self.block_signals()

        # Only update checkbox state on the very first load
        # After that, NEVER touch the checkbox regardless of keyboard state
        if not self.initial_load_complete:
            print("LayerRGBHandler: Initial load - checking keyboard state")
            # Try to get per-layer RGB status if methods exist
            if hasattr(self.device.keyboard, 'get_layer_rgb_status'):
                try:
                    status = self.device.keyboard.get_layer_rgb_status()
                    if status is not None:
                        # status is get_layer_rgb_status() -> data[2:]; byte 0 is the enable flag.
                        # Test the flag byte, not truthiness of the whole buffer.
                        keyboard_state = bool(status[0]) if len(status) > 0 else False
                        self.per_layer_enabled = keyboard_state
                        self.user_set_state = keyboard_state  # Initialize user state
                        print(f"Initial layer RGB status from keyboard: {keyboard_state}")
                        # Set checkbox state ONLY on initial load
                        self.layer_rgb_enable.setChecked(self.per_layer_enabled)
                    else:
                        self.per_layer_enabled = False
                        self.user_set_state = False
                        print("No initial layer RGB status data received")
                        self.layer_rgb_enable.setChecked(False)
                except Exception as e:
                    print(f"Error getting initial layer RGB status: {e}")
                    self.per_layer_enabled = False
                    self.user_set_state = False
                    self.layer_rgb_enable.setChecked(False)
            else:
                # Default values for testing when keyboard methods aren't implemented yet
                self.per_layer_enabled = False
                self.user_set_state = False
                print("Layer RGB methods not implemented on keyboard")
                self.layer_rgb_enable.setChecked(False)

            self.initial_load_complete = True
        else:
            # On subsequent updates (e.g., when other RGB settings change),
            # COMPLETELY IGNORE keyboard state and preserve checkbox as-is
            print("LayerRGBHandler: Subsequent update - completely ignoring keyboard state, preserving checkbox")
            # Don't touch the checkbox at all - let it stay exactly as the user set it
            # Just update our internal state to match the checkbox
            self.per_layer_enabled = self.layer_rgb_enable.isChecked()
        
        # Always recreate buttons to ensure they're in sync with current checkbox state
        self.create_layer_buttons()

        # Unblock signals after update is complete
        self.unblock_signals()

    def valid(self):
        # Always return True so buttons are always shown
        return isinstance(self.device, VialKeyboard)

    def on_layer_rgb_enable_changed(self, checked):
        self.per_layer_enabled = checked
        
        # Try to call the keyboard method if it exists
        if hasattr(self.device.keyboard, 'set_layer_rgb_enable'):
            self.device.keyboard.set_layer_rgb_enable(checked)
        else:
            print(f"Layer RGB enable changed to: {checked} (keyboard method not implemented yet)")
        
        # Enable/disable layer buttons
        for button in self.layer_buttons:
            button.setEnabled(checked)

    def on_save_to_layer(self, layer):
        """Save current RGB settings to specified layer"""
        if self.per_layer_enabled:
            # Try to call the keyboard method if it exists
            if hasattr(self.device.keyboard, 'save_rgb_to_layer'):
                success = self.device.keyboard.save_rgb_to_layer(layer)
                if success:
                    print(f"Successfully saved RGB to layer {layer}")
                    self.update.emit()
                else:
                    print(f"Failed to save RGB to layer {layer}")
            else:
                print(f"Save RGB to layer {layer} (keyboard method not implemented yet)")

    def block_signals(self):
        """Override to ensure checkbox signals are properly blocked"""
        super().block_signals()
        # Extra safety - explicitly block the checkbox signal
        self.layer_rgb_enable.blockSignals(True)
        print("LayerRGBHandler: Signals blocked")

    def unblock_signals(self):
        """Override to ensure checkbox signals are properly unblocked"""
        super().unblock_signals()
        # Extra safety - explicitly unblock the checkbox signal
        self.layer_rgb_enable.blockSignals(False)
        print("LayerRGBHandler: Signals unblocked")

    def show(self):
        # Always show all widgets - no conditional visibility
        for w in self.widgets:
            w.show()

    def hide(self):
        # Always show all widgets - no hiding capability
        for w in self.widgets:
            w.show()


class SimpleLayoutEditor:
    """Simple layout editor stub for KeyboardWidget2"""
    def get_choice(self, idx):
        return 0


class PaletteButton(QPushButton):
    """Custom palette button that handles single-click, double-click, and right-click"""
    single_clicked = pyqtSignal(int)
    edit_requested = pyqtSignal(int)

    def __init__(self, index, parent=None):
        super().__init__("", parent)
        self.index = index
        self.setFixedSize(55, 55)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda: self.edit_requested.emit(self.index))

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to edit color"""
        self.edit_requested.emit(self.index)
        event.accept()

    def mousePressEvent(self, event):
        """Handle single-click to select color"""
        if event.button() == Qt.LeftButton:
            super().mousePressEvent(event)
            self.single_clicked.emit(self.index)
        elif event.button() == Qt.RightButton:
            self.edit_requested.emit(self.index)
            event.accept()


class PerKeyRGBHandler(BasicHandler):
    """Handler for per-key RGB configuration with 12 presets and 16-color palette"""

    # Default palette colors: Red, Green, Blue, Yellow, Cyan, Magenta, White, Orange,
    # Purple, Pink, Lime, Teal, Navy, Maroon, Olive, Silver
    DEFAULT_PALETTE = [
        [0, 255, 255],      # Red
        [85, 255, 255],     # Green
        [170, 255, 255],    # Blue
        [43, 255, 255],     # Yellow
        [128, 255, 255],    # Cyan
        [213, 255, 255],    # Magenta
        [0, 0, 255],        # White
        [21, 255, 255],     # Orange
        [192, 255, 255],    # Purple
        [234, 128, 255],    # Pink
        [64, 255, 255],     # Lime
        [149, 255, 200],    # Teal
        [170, 255, 128],    # Navy
        [0, 200, 128],      # Maroon
        [43, 200, 128],     # Olive
        [0, 0, 192],        # Silver
    ]

    def __init__(self, container):
        super().__init__(container)

        row = container.rowCount()

        # Title
        self.lbl_title = QLabel(tr("RGBConfigurator", "Per-Key RGB Configuration"))
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14pt;")
        container.addWidget(self.lbl_title, row, 0, 1, 2)
        row += 1

        # Description
        self.lbl_description = QLabel(tr("RGBConfigurator",
            "Configure individual LED colors for each key. Select a preset, choose a color from the palette,\n"
            "then click keys on the keyboard to paint them. Double-click palette colors to edit them."))
        self.lbl_description.setWordWrap(True)
        self.lbl_description.setStyleSheet("color: gray; font-size: 9pt;")
        container.addWidget(self.lbl_description, row, 0, 1, 2)
        row += 1

        # Preset selector with individual buttons
        self.lbl_preset = QLabel(tr("RGBConfigurator", "Select Preset:"))
        container.addWidget(self.lbl_preset, row, 0)

        # Create horizontal layout for preset buttons
        preset_button_widget = QWidget()
        preset_button_layout = QHBoxLayout(preset_button_widget)
        preset_button_layout.setContentsMargins(0, 0, 0, 0)
        preset_button_layout.setSpacing(4)

        # Create 12 preset buttons (35x35 pixels each)
        self.preset_buttons = []
        for i in range(12):
            btn = QPushButton(str(i + 1))
            btn.setFixedSize(35, 35)
            btn.clicked.connect(lambda checked, idx=i: self.on_preset_changed(idx))
            preset_button_layout.addWidget(btn)
            self.preset_buttons.append(btn)

        preset_button_layout.addStretch()
        container.addWidget(preset_button_widget, row, 1)
        row += 1

        # Main horizontal layout: Palette on left, Keyboard on right
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Left side: Color palette and buttons
        palette_container = QWidget()
        palette_container.setFixedWidth(240)  # Fixed width to match 4x4 grid
        palette_container_layout = QVBoxLayout(palette_container)
        palette_container_layout.setContentsMargins(0, 0, 0, 0)
        palette_container_layout.setSpacing(8)

        self.lbl_palette = QLabel(tr("RGBConfigurator", "Color Palette:"))
        palette_container_layout.addWidget(self.lbl_palette)

        # 4x4 palette grid
        self.palette_widget = QWidget()
        self.palette_layout = QGridLayout(self.palette_widget)
        self.palette_layout.setContentsMargins(0, 0, 0, 0)
        self.palette_layout.setSpacing(4)
        palette_container_layout.addWidget(self.palette_widget)

        # Create 4x4 palette buttons (same size, border selection)
        self.palette_buttons = []
        for i in range(16):
            r = i // 4  # 4 rows
            c = i % 4   # 4 columns
            button = PaletteButton(i)
            button.setFixedSize(55, 55)  # Fixed size for all
            button.single_clicked.connect(self.on_palette_selected)
            button.edit_requested.connect(self.on_palette_edit)
            self.palette_layout.addWidget(button, r, c)
            self.palette_buttons.append(button)

        # Change Color button (below palette) - with rounded edges, 35px tall
        self.btn_change_color = QPushButton(tr("RGBConfigurator", "Change Color"))
        self.btn_change_color.clicked.connect(self.on_change_color_clicked)
        self.btn_change_color.setFixedHeight(35)
        self.btn_change_color.setStyleSheet("QPushButton { border-radius: 5px; }")
        palette_container_layout.addWidget(self.btn_change_color)

        # Action buttons (below Change Color button) - with rounded edges, 35px tall
        self.btn_change_all_layers = QPushButton(tr("RGBConfigurator", "Change ALL Layers to Per Key"))
        self.btn_change_all_layers.clicked.connect(self.on_change_all_layers)
        self.btn_change_all_layers.setFixedHeight(35)
        self.btn_change_all_layers.setStyleSheet("QPushButton { border-radius: 5px; }")
        palette_container_layout.addWidget(self.btn_change_all_layers)

        self.btn_save = QPushButton(tr("RGBConfigurator", "Save to EEPROM"))
        self.btn_save.clicked.connect(self.on_save)
        self.btn_save.setFixedHeight(35)
        self.btn_save.setStyleSheet("QPushButton { border-radius: 5px; }")
        palette_container_layout.addWidget(self.btn_save)

        self.btn_load = QPushButton(tr("RGBConfigurator", "Load from EEPROM"))
        self.btn_load.clicked.connect(self.on_load)
        self.btn_load.setFixedHeight(35)
        self.btn_load.setStyleSheet("QPushButton { border-radius: 5px; }")
        palette_container_layout.addWidget(self.btn_load)

        self.btn_reset = QPushButton(tr("RGBConfigurator", "Reset to Defaults"))
        self.btn_reset.clicked.connect(self.on_reset_defaults)
        self.btn_reset.setFixedHeight(35)
        self.btn_reset.setStyleSheet("QPushButton { border-radius: 5px; background-color: #cc4444; color: white; }")
        palette_container_layout.addWidget(self.btn_reset)

        palette_container_layout.addStretch()

        main_layout.addWidget(palette_container)

        # Right side: Keyboard widget
        keyboard_container = QWidget()
        keyboard_layout = QVBoxLayout(keyboard_container)
        keyboard_layout.setContentsMargins(0, 0, 0, 0)

        # Create simple layout editor stub
        self.layout_editor = SimpleLayoutEditor()

        # Create KeyboardWidget2
        self.keyboard_widget = KeyboardWidgetNoHighlight(self.layout_editor)
        self.keyboard_widget.clicked.connect(self.on_key_clicked)
        keyboard_layout.addWidget(self.keyboard_widget)

        main_layout.addWidget(keyboard_container)

        container.addWidget(main_widget, row, 0, 1, 2)
        row += 1

        # Debug output area
        from PyQt5.QtWidgets import QTextEdit
        self.lbl_debug = QLabel(tr("RGBConfigurator", "Debug Output (select all and copy to share):"))
        self.lbl_debug.setStyleSheet("font-weight: bold; margin-top: 10px;")
        container.addWidget(self.lbl_debug, row, 0, 1, 2)
        row += 1

        self.debug_output = QTextEdit()
        self.debug_output.setReadOnly(True)
        self.debug_output.setFixedHeight(150)
        self.debug_output.setStyleSheet("font-family: monospace; font-size: 10pt;")
        container.addWidget(self.debug_output, row, 0, 1, 2)
        row += 1

        # State variables
        self.current_preset = 0
        self.selected_palette_index = 0
        self.palette = [list(color) for color in self.DEFAULT_PALETTE]  # Initialize with default colors
        self.preset_data = [[0 for _ in range(70)] for _ in range(12)]  # 12 presets x 70 LEDs
        self.device = None
        self.key_widgets = []  # Will store references to keyboard key widgets

        self.widgets = [
            self.lbl_title, self.lbl_description, self.lbl_preset, preset_button_widget,
            main_widget, self.lbl_debug, self.debug_output
        ]

        # Initialize palette display with default colors
        self.update_palette_display()
        self.update_palette_selection()
        self.update_preset_button_selection()

    def debug_log(self, message):
        """Append message to debug output widget"""
        self.debug_output.append(message)
        # Auto-scroll to bottom
        scrollbar = self.debug_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_debug(self):
        """Clear debug output"""
        self.debug_output.clear()

    def on_preset_changed(self, index):
        """Handle preset selection change - switches to local cached preset data"""
        self.current_preset = index
        # Update button visual states to show current selection
        self.update_preset_button_selection()
        # Update display with cached preset data (no firmware reload)
        self.update_keyboard_display()

    def on_key_clicked(self):
        """Handle keyboard key click - assign current palette color to clicked key"""
        if not self.keyboard_widget.active_key:
            return

        # Find the LED index for the clicked key
        key_index = self.get_key_index(self.keyboard_widget.active_key)
        if key_index is None or key_index >= 70:
            self.debug_log(f"Invalid key index: {key_index}")
            return

        # Assign the selected palette color to this key
        if hasattr(self, 'keyboard') and self.keyboard:
            self.set_led_color(self.current_preset, key_index, self.selected_palette_index)
            self.preset_data[self.current_preset][key_index] = self.selected_palette_index
            self.update_keyboard_display()
        else:
            self.debug_log("No keyboard device available")

    def on_palette_selected(self, palette_index):
        """Handle palette button single-click - select this color for painting"""
        self.selected_palette_index = palette_index
        self.update_palette_selection()

    def on_palette_edit(self, palette_index):
        """Handle palette button double-click or right-click - edit this color"""
        self.selected_palette_index = palette_index
        self.update_palette_selection()
        self.open_color_dialog(palette_index)

    def on_change_color_clicked(self):
        """Handle Change Color button - edit the currently selected palette color"""
        self.open_color_dialog(self.selected_palette_index)

    def open_color_dialog(self, palette_index):
        """Open QColorDialog to edit a palette color"""
        # Get current color
        h, s, v = self.palette[palette_index]
        rgb = self.hsv_to_rgb(h, s, v)
        current_color = QColor(rgb[0], rgb[1], rgb[2])

        # Open color dialog
        color = QColorDialog.getColor(current_color, None, tr("RGBConfigurator", "Select Color"))

        if color.isValid():
            # Convert RGB to HSV (0-255 range)
            h, s, v = self.rgb_to_hsv(color.red(), color.green(), color.blue())

            # Update palette
            self.palette[palette_index] = [h, s, v]

            # Send to firmware
            if hasattr(self.device, 'keyboard'):
                self.set_palette_color(palette_index, h, s, v)

            # Update displays
            self.update_palette_display()
            self.update_keyboard_display()

    def update_palette_selection(self):
        """Update the visual selection state of palette buttons with borders and opacity"""
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QPalette

        # Detect if dark or light theme
        bg_color = QApplication.palette().color(QPalette.Window)
        is_dark_theme = bg_color.lightness() < 128
        border_color = "#FFFFFF" if is_dark_theme else "#000000"

        for i, button in enumerate(self.palette_buttons):
            # Get the base color
            h, s, v = self.palette[i]
            rgb = self.hsv_to_rgb(h, s, v)

            # Create radial gradient effect (brighter center, darker edges)
            r, g, b = rgb[0], rgb[1], rgb[2]
            # Stronger darkening for better visibility
            r_dark = max(0, r - 60)
            g_dark = max(0, g - 60)
            b_dark = max(0, b - 60)

            # Selected palette: 100% opacity with white/black border
            # Unselected palette: 70% opacity with thin border
            if i == self.selected_palette_index:
                opacity = 255
                border = f"border: 3px solid {border_color};"
            else:
                opacity = int(255 * 0.7)  # 70% opacity
                border = "border: 1px solid #444444;"

            # Use radial gradient for centered effect with opacity
            stylesheet = f"""
                QPushButton {{
                    background-color: rgba({r}, {g}, {b}, {opacity});
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.7,
                        fx:0.5, fy:0.5,
                        stop:0 rgba({r}, {g}, {b}, {opacity}),
                        stop:1 rgba({r_dark}, {g_dark}, {b_dark}, {opacity}));
                    {border}
                }}
            """

            button.setStyleSheet(stylesheet)

    def update_preset_button_selection(self):
        """Update the visual selection state of preset buttons using theme colors"""
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QPalette

        # Get theme colors
        highlight_color = QApplication.palette().color(QPalette.Highlight)
        highlight_text = QApplication.palette().color(QPalette.HighlightedText)
        button_color = QApplication.palette().color(QPalette.Button)
        text_color = QApplication.palette().color(QPalette.ButtonText)

        for i, button in enumerate(self.preset_buttons):
            if i == self.current_preset:
                # Selected preset - use theme highlight colors
                button.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {highlight_color.name()};
                        color: {highlight_text.name()};
                        font-weight: bold;
                        border: 2px solid {highlight_color.lighter(120).name()};
                    }}
                    QPushButton:hover {{
                        background-color: {highlight_color.lighter(110).name()};
                    }}
                """)
            else:
                # Unselected preset - use theme button colors
                button.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {button_color.name()};
                        color: {text_color.name()};
                        border: 1px solid {button_color.darker(120).name()};
                    }}
                    QPushButton:hover {{
                        background-color: {button_color.lighter(110).name()};
                        border: 1px solid {button_color.darker(110).name()};
                    }}
                """)

    def get_key_index(self, key_widget):
        """Get the LED index (0-69) for a given key widget based on matrix position"""
        if not hasattr(key_widget, 'desc') or not hasattr(key_widget.desc, 'row') or not hasattr(key_widget.desc, 'col'):
            return None

        row = key_widget.desc.row
        col = key_widget.desc.col

        # Map matrix position to LED index (row-major order: row * 14 + col)
        if row is not None and col is not None and row < 5 and col < 14:
            return row * 14 + col

        return None

    def on_change_all_layers(self):
        """Set layer 0→Per Key 1, layer 1→Per Key 2, etc."""
        if hasattr(self.device.keyboard, 'set_layer_rgb_enable'):
            # Enable per-layer RGB
            self.device.keyboard.set_layer_rgb_enable(True)

            # Set each layer to its corresponding Per Key preset
            for layer in range(12):
                # Set RGB mode to Per Key preset (VIALRGB indices 57-68)
                per_key_mode = 57 + layer
                # This would require a method to set the RGB mode for a specific layer
                # For now, this is a placeholder
                print(f"Would set layer {layer} to Per Key {layer + 1} (mode {per_key_mode})")

    def on_save(self):
        """Save per-key data to EEPROM"""
        if hasattr(self, 'keyboard') and self.keyboard:
            import struct
            data = struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_PER_KEY_SAVE)
            self.keyboard.usb_send(self.keyboard.dev, data, retries=20)
            self.debug_log("=== SAVE TO EEPROM ===")
            self.debug_log("Saved per-key RGB data to EEPROM")

    def on_load(self):
        """Load per-key data from EEPROM"""
        if hasattr(self, 'keyboard') and self.keyboard:
            import struct
            self.clear_debug()
            self.debug_log("=== LOAD FROM EEPROM ===")
            data = struct.pack("BB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_PER_KEY_LOAD)
            self.keyboard.usb_send(self.keyboard.dev, data, retries=20)

            # Reload palette and ALL presets from firmware after EEPROM load
            self.load_palette_from_firmware()
            self.debug_log("Loading all presets from EEPROM...")
            for preset_idx in range(12):
                self.load_preset_from_firmware(preset_idx)
            self.debug_log("All presets loaded from EEPROM.")

            # Update displays
            self.update_palette_display()
            self.update_keyboard_display()

    def on_reset_defaults(self):
        """Reset per-key RGB to defaults (clears all presets)"""
        if hasattr(self, 'keyboard') and self.keyboard:
            import struct
            self.clear_debug()
            self.debug_log("=== RESET TO DEFAULTS ===")
            # Send load command with 0xFF parameter to trigger reset
            data = struct.pack("BBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_PER_KEY_LOAD, 0xFF)
            self.keyboard.usb_send(self.keyboard.dev, data, retries=20)
            self.debug_log("Sent reset command to firmware")

            # Reload palette and ALL presets from firmware after reset
            self.load_palette_from_firmware()
            self.debug_log("Loading all presets after reset...")
            for preset_idx in range(12):
                self.load_preset_from_firmware(preset_idx)
            self.debug_log("All presets loaded after reset.")

            # Update displays
            self.update_palette_display()
            self.update_keyboard_display()

    def load_palette_from_firmware(self):
        """Load 16-color palette from firmware (paginated due to 32-byte HID limit)"""
        if not hasattr(self, 'keyboard') or not self.keyboard:
            return

        try:
            import struct
            self.debug_log("Loading palette from firmware (paginated)...")

            # Load palette in chunks (max 10 colors per request due to 31-byte response limit)
            # Request format: [prefix, cmd, offset, count] where offset/count are color indices
            # Response format: [success, h0, s0, v0, h1, s1, v1, ...] = 1 + count*3 bytes
            palette_offset = 0
            while palette_offset < 16:
                count = min(10, 16 - palette_offset)  # Max 10 colors (30 bytes) per request
                data = struct.pack("BBBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_PER_KEY_GET_PALETTE,
                                   palette_offset, count)
                response = self.keyboard.usb_send(self.keyboard.dev, data, retries=20)

                expected_len = 1 + count * 3  # 1 success + count*3 HSV bytes
                if response and len(response) >= expected_len and response[0] == 0x01:
                    for i in range(count):
                        h = response[1 + i * 3]
                        s = response[1 + i * 3 + 1]
                        v = response[1 + i * 3 + 2]
                        self.palette[palette_offset + i] = [h, s, v]
                else:
                    self.debug_log(f"ERROR: Palette chunk failed at offset {palette_offset}, "
                                   f"response length: {len(response) if response else 'None'}")
                    return

                palette_offset += count

            # Log loaded palette
            self.debug_log("Palette loaded from firmware:")
            for i in range(16):
                h, s, v = self.palette[i]
                self.debug_log(f"  Color {i}: H={h} S={s} V={v}")
            self.update_palette_display()
        except Exception as e:
            self.debug_log(f"ERROR loading palette: {e}")

    def load_preset_from_firmware(self, preset):
        """Load preset LED data from firmware (paginated)"""
        if not hasattr(self, 'keyboard') or not self.keyboard:
            return

        try:
            import struct
            # Load in chunks (31 bytes per request due to HID packet size)
            offset = 0
            non_zero_leds = []
            while offset < 70:
                count = min(31, 70 - offset)
                data = struct.pack("BBBBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_PER_KEY_GET_PRESET_DATA,
                                   preset, offset, count)
                response = self.keyboard.usb_send(self.keyboard.dev, data, retries=20)

                # Firmware replies [success=0x01, data...] (vial.c 0xD5); an
                # error/echo response must not be parsed as LED palette data.
                if response and len(response) >= count + 1 and response[0] == 0x01:
                    for i in range(count):
                        val = response[1 + i]
                        self.preset_data[preset][offset + i] = val
                        if val != 0:
                            led_idx = offset + i
                            row = led_idx // 14
                            col = led_idx % 14
                            non_zero_leds.append(f"r{row}c{col}={val}")

                offset += count

            if non_zero_leds:
                self.debug_log(f"Preset {preset}: {len(non_zero_leds)} colored LEDs: {', '.join(non_zero_leds)}")
            else:
                self.debug_log(f"Preset {preset}: all LEDs are black (0)")
            self.update_keyboard_display()
        except Exception as e:
            self.debug_log(f"ERROR loading preset {preset}: {e}")

    def set_palette_color(self, palette_index, h, s, v):
        """Set a palette color in firmware"""
        if not hasattr(self, 'keyboard') or not self.keyboard:
            return

        try:
            import struct
            data = struct.pack("BBBBBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_PER_KEY_SET_PALETTE_COLOR,
                               palette_index, h, s, v)
            self.keyboard.usb_send(self.keyboard.dev, data, retries=20)
        except Exception as e:
            print(f"Error setting palette color: {e}")

    def set_led_color(self, preset, led_index, palette_index):
        """Set an LED's palette index in firmware"""
        if not hasattr(self, 'keyboard') or not self.keyboard:
            return

        try:
            import struct
            data = struct.pack("BBBBB", CMD_VIA_VIAL_PREFIX, CMD_VIAL_PER_KEY_SET_LED_COLOR,
                               preset, led_index, palette_index)
            self.keyboard.usb_send(self.keyboard.dev, data, retries=20)
        except Exception as e:
            self.debug_log(f"ERROR setting LED color: {e}")

    def set_device(self, device):
        """Set device and initialize keyboard widget"""
        super().set_device(device)

        # Set keyboard keys if device is available
        if hasattr(device, 'keyboard') and hasattr(device.keyboard, 'keys'):
            keys = device.keyboard.keys
            encoders = device.keyboard.encoders if hasattr(device.keyboard, 'encoders') else []
            self.keyboard_widget.set_keys(keys, encoders)
            self.keyboard_widget.update_layout()

            # Clear and start fresh debug output
            self.clear_debug()
            self.debug_log("=== INITIAL LOAD ON CONNECT ===")

            # Load palette from firmware
            self.load_palette_from_firmware()

            # Load ALL presets from firmware to cache them locally
            # This allows switching between presets without losing unsaved changes
            self.debug_log("Loading all 12 presets from firmware...")
            for preset_idx in range(12):
                self.load_preset_from_firmware(preset_idx)
            self.debug_log("=== INITIAL LOAD COMPLETE ===")

            # Update display for current preset
            self.update_keyboard_display()

    def update_palette_display(self):
        """Update palette button colors with gradient effect"""
        # Use update_palette_selection which handles both colors and selection
        self.update_palette_selection()

    def update_keyboard_display(self):
        """Update keyboard key colors based on current preset"""
        if not self.keyboard_widget.widgets:
            return

        for widget in self.keyboard_widget.widgets:
            key_index = self.get_key_index(widget)
            if key_index is not None and key_index < 70:
                palette_index = self.preset_data[self.current_preset][key_index]

                # Bounds check - ensure palette index is valid (0-15)
                if palette_index < 0 or palette_index >= 16:
                    self.debug_log(f"WARNING: Invalid palette index {palette_index} for key {key_index}, defaulting to 0")
                    palette_index = 0
                    self.preset_data[self.current_preset][key_index] = 0

                h, s, v = self.palette[palette_index]
                rgb = self.hsv_to_rgb(h, s, v)
                # Set the key color
                color = QColor(rgb[0], rgb[1], rgb[2])
                widget.setColor(color)

        # Trigger repaint
        self.keyboard_widget.update()

    @staticmethod
    def hsv_to_rgb(h, s, v):
        """Convert HSV (0-255) to RGB (0-255)"""
        h = h / 255.0 * 360.0
        s = s / 255.0
        v = v / 255.0

        c = v * s
        x = c * (1 - abs((h / 60.0) % 2 - 1))
        m = v - c

        if h < 60:
            r, g, b = c, x, 0
        elif h < 120:
            r, g, b = x, c, 0
        elif h < 180:
            r, g, b = 0, c, x
        elif h < 240:
            r, g, b = 0, x, c
        elif h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x

        return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))

    @staticmethod
    def rgb_to_hsv(r, g, b):
        """Convert RGB (0-255) to HSV (0-255)"""
        r, g, b = r / 255.0, g / 255.0, b / 255.0
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        diff = max_val - min_val

        # Hue calculation
        if diff == 0:
            h = 0
        elif max_val == r:
            h = 60 * (((g - b) / diff) % 6)
        elif max_val == g:
            h = 60 * (((b - r) / diff) + 2)
        else:
            h = 60 * (((r - g) / diff) + 4)

        # Saturation calculation
        s = 0 if max_val == 0 else diff / max_val

        # Value calculation
        v = max_val

        # Convert to 0-255 range
        return (int(h / 360.0 * 255), int(s * 255), int(v * 255))

    def update_from_keyboard(self):
        """Update from keyboard - loads all presets to preserve local edits"""
        if not self.valid():
            return

        self.load_palette_from_firmware()

        # Load ALL presets from firmware to cache them locally
        print("Refreshing all presets from firmware...")
        for preset_idx in range(12):
            self.load_preset_from_firmware(preset_idx)
        print("All presets refreshed.")

        # Update display for current preset
        self.update_keyboard_display()

    def valid(self):
        return isinstance(self.device, VialKeyboard)


class CustomLightsHandler(BasicHandler):
    """Handler for custom animation slot configuration - uses VialKeyboard infrastructure"""

    def create_help_label(self, tooltip_text):
        """Create a small question mark button with tooltip for help"""
        help_btn = QPushButton("?")
        help_btn.setStyleSheet("""
            QPushButton {
                color: #888;
                font-weight: bold;
                font-size: 9pt;
                border: 1px solid #888;
                border-radius: 9px;
                min-width: 16px;
                max-width: 16px;
                min-height: 16px;
                max-height: 16px;
                padding: 0px;
                margin: 0px;
                background: transparent;
            }
            QPushButton:hover {
                color: #fff;
                background-color: #555;
                border-color: #fff;
            }
        """)
        help_btn.setToolTip(tooltip_text)
        help_btn.setFocusPolicy(Qt.NoFocus)
        return help_btn

    def __init__(self, container):
        super().__init__(container)

        row = container.rowCount()

        # Custom Lights label
        self.lbl_custom_lights = QLabel(tr("RGBConfigurator", "Custom Lights"))
        container.addWidget(self.lbl_custom_lights, row, 0, 1, 2)

        # Create main tab widget for groups
        self.main_tab_widget = QTabWidget()
        container.addWidget(self.main_tab_widget, row + 1, 0, 1, 2)
        
        # Track the currently active slot (for parameter changes)
        self.current_active_slot = None
        self.current_randomize_slot = None
        # Slots whose widget values were actually populated from the device
        # (update_slot_widgets). Widget init defaults (hue 0 / sat 255 = red)
        # must never be pushed to the keyboard as if they were real data.
        self.slots_loaded_from_device = set()
        # Placeholder tab pages; real controls are built on first visit
        self._slot_tab_placeholders = {}
        
        # Create grouped tabs
        self.slot_tabs = []
        self.slot_widgets = {}
        self.group_tab_widgets = {}  # Store sub-tab widgets for each group
        
        # Define groups: 1-9, 10-19, 20-29, 30-39, 40-49 (removed the single "50" group)
        self.groups = [
            ("1-9", 0, 9),
            ("10-19", 9, 19), 
            ("20-29", 19, 29),
            ("30-39", 29, 39),
            ("40-49", 39, 50)  # Changed to go up to 50 (slots 39-49)
        ]
        
        # Connect main tab change to load lowest slot in group
        self.main_tab_widget.currentChanged.connect(self.on_main_tab_changed)
        
        for group_name, start_idx, end_idx in self.groups:
            self.create_group_tab(group_name, start_idx, end_idx)

        self.widgets = [self.lbl_custom_lights, self.main_tab_widget]

    def create_group_tab(self, group_name, start_idx, end_idx):
        """Create a main tab containing sub-tabs for a group of slots"""
        # Create the main tab widget
        group_widget = QWidget()
        self.main_tab_widget.addTab(group_widget, group_name)
        
        # Create layout for the group
        group_layout = QHBoxLayout(group_widget)
        group_layout.setContentsMargins(5, 5, 5, 5)
        
        # Create sub-tab widget for individual slots in this group
        sub_tab_widget = QTabWidget()
        group_layout.addWidget(sub_tab_widget)
        
        # Store reference to sub-tab widget
        self.group_tab_widgets[group_name] = sub_tab_widget
        
        # Connect tab change signal for this sub-tab widget
        sub_tab_widget.currentChanged.connect(lambda index, start=start_idx: self.on_sub_tab_changed(index, start))
        
        # Create individual slot tabs within this group
        for slot in range(start_idx, end_idx):
            self.create_slot_tab(slot, sub_tab_widget)
        
    def create_slot_tab(self, slot, parent_tab_widget):
        """Register a placeholder tab for a slot. The actual controls (a
        dozen dropdowns/sliders each, x50 slots) are built on the first visit
        via _ensure_slot_tab() — building all of them up front cost ~0.5s and
        tens of thousands of signal connects at startup."""
        tab_widget = QWidget()
        # Register BEFORE addTab: adding the first tab fires currentChanged
        # synchronously, which routes to _ensure_slot_tab for that slot — this
        # builds each group's initially-visible slot so it is never blank.
        self._slot_tab_placeholders[slot] = tab_widget
        parent_tab_widget.addTab(tab_widget, str(slot + 1))  # Tab names: "1", "2", "3", etc.

    def _ensure_slot_tab(self, slot):
        """Build a slot tab's real content on first use."""
        if slot in self.slot_widgets:
            return
        tab_widget = self._slot_tab_placeholders.get(slot)
        if tab_widget is None:
            return
        self._build_slot_tab_content(slot, tab_widget)

    def _build_slot_tab_content(self, slot, tab_widget):
        """Create the full control set for one slot inside its placeholder."""
        # Create layout for this tab
        layout = QGridLayout(tab_widget)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(3)

        row = 0

        # Live Animation section header
        live_header = QHBoxLayout()
        live_label = QLabel(tr("RGBConfigurator", "Live Animation:"))
        live_label.setStyleSheet("font-weight: bold;")
        live_header.addWidget(self.create_help_label("Animation that plays while keys are held."))
        live_header.addWidget(live_label)
        live_header.addStretch()
        layout.addLayout(live_header, row, 0, 1, 4)
        row += 1

        # Live Effect
        live_effect_label = QLabel(tr("RGBConfigurator", "Effect:"))
        layout.addWidget(live_effect_label, row, 0)
        live_effect = HierarchicalDropdown(LIVE_EFFECTS_HIERARCHY)
        live_effect.setStyleSheet("QComboBox { border-radius: 5px; }")
        live_effect.valueChanged.connect(lambda idx, s=slot: self.on_live_effect_changed(s, idx))
        layout.addWidget(live_effect, row, 1, 1, 3)
        row += 1

        # Live Position (below Effect)
        live_position_label = QLabel(tr("RGBConfigurator", "Position:"))
        layout.addWidget(live_position_label, row, 0)
        live_style = HierarchicalDropdown(LIVE_STYLES_HIERARCHY)
        live_style.setStyleSheet("QComboBox { border-radius: 5px; }")
        live_style.valueChanged.connect(lambda idx, s=slot: self.on_live_style_changed(s, idx))
        layout.addWidget(live_style, row, 1, 1, 3)
        row += 1

        # Live Brightness + Speed on same row
        live_bright_label = QLabel(tr("RGBConfigurator", "Brightness:"))
        layout.addWidget(live_bright_label, row, 0)
        live_brightness = QSlider(QtCore.Qt.Horizontal)
        live_brightness.setMinimum(0)
        live_brightness.setMaximum(255)
        live_brightness.setValue(255)
        self._connect_throttled(live_brightness, self.on_live_brightness_changed, slot)  # ~1 HID/sec while dragging + on release
        layout.addWidget(live_brightness, row, 1)
        live_speed_label = QLabel(tr("RGBConfigurator", "Speed:"))
        layout.addWidget(live_speed_label, row, 2)
        live_speed = QSlider(QtCore.Qt.Horizontal)
        live_speed.setMinimum(0)
        live_speed.setMaximum(255)
        live_speed.setValue(128)
        self._connect_throttled(live_speed, self.on_live_speed_changed, slot)  # ~1 HID/sec while dragging + on release
        layout.addWidget(live_speed, row, 3)
        row += 1

        # Enable Live Dynamic Brightness checkbox
        vel_brightness_live = QCheckBox(tr("RGBConfigurator", "Enable Live Dynamic Brightness"))
        vel_brightness_live.setToolTip("When enabled, live animation brightness scales with\nkeypress velocity. Soft press = dim, hard press = bright.")
        vel_brightness_live.setChecked(False)
        vel_brightness_live.stateChanged.connect(lambda state, s=slot: self.on_vel_brightness_live_changed(s, state))
        layout.addWidget(vel_brightness_live, row, 0, 1, 4)
        row += 1

        # Macro Animation section header
        macro_header = QHBoxLayout()
        macro_label = QLabel(tr("RGBConfigurator", "Macro Animation:"))
        macro_label.setStyleSheet("font-weight: bold;")
        macro_header.addWidget(self.create_help_label("Animation triggered on key press from macro playback."))
        macro_header.addWidget(macro_label)
        macro_header.addStretch()
        layout.addLayout(macro_header, row, 0, 1, 4)
        row += 1

        # Macro Effect
        macro_effect_label = QLabel(tr("RGBConfigurator", "Effect:"))
        layout.addWidget(macro_effect_label, row, 0)
        macro_effect = HierarchicalDropdown(LIVE_EFFECTS_HIERARCHY)
        macro_effect.setStyleSheet("QComboBox { border-radius: 5px; }")
        macro_effect.valueChanged.connect(lambda idx, s=slot: self.on_macro_effect_changed(s, idx))
        layout.addWidget(macro_effect, row, 1, 1, 3)
        row += 1

        # Macro Position (below Effect)
        macro_position_label = QLabel(tr("RGBConfigurator", "Position:"))
        layout.addWidget(macro_position_label, row, 0)
        macro_style = HierarchicalDropdown(MACRO_STYLES_HIERARCHY)
        macro_style.setStyleSheet("QComboBox { border-radius: 5px; }")
        macro_style.valueChanged.connect(lambda idx, s=slot: self.on_macro_style_changed(s, idx))
        layout.addWidget(macro_style, row, 1, 1, 3)
        row += 1

        # Macro Brightness + Speed on same row
        macro_bright_label = QLabel(tr("RGBConfigurator", "Brightness:"))
        layout.addWidget(macro_bright_label, row, 0)
        macro_brightness = QSlider(QtCore.Qt.Horizontal)
        macro_brightness.setMinimum(0)
        macro_brightness.setMaximum(255)
        macro_brightness.setValue(255)
        self._connect_throttled(macro_brightness, self.on_macro_brightness_changed, slot)  # ~1 HID/sec while dragging + on release
        layout.addWidget(macro_brightness, row, 1)
        macro_speed_label = QLabel(tr("RGBConfigurator", "Speed:"))
        layout.addWidget(macro_speed_label, row, 2)
        macro_speed = QSlider(QtCore.Qt.Horizontal)
        macro_speed.setMinimum(0)
        macro_speed.setMaximum(255)
        macro_speed.setValue(128)
        self._connect_throttled(macro_speed, self.on_macro_speed_changed, slot)  # ~1 HID/sec while dragging + on release
        layout.addWidget(macro_speed, row, 3)
        row += 1

        # Enable Macro Dynamic Brightness checkbox
        vel_brightness_macro = QCheckBox(tr("RGBConfigurator", "Enable Macro Dynamic Brightness"))
        vel_brightness_macro.setToolTip("When enabled, macro animation brightness scales with\nkeypress velocity. Soft press = dim, hard press = bright.")
        vel_brightness_macro.setChecked(False)
        vel_brightness_macro.stateChanged.connect(lambda state, s=slot: self.on_vel_brightness_macro_changed(s, state))
        layout.addWidget(vel_brightness_macro, row, 0, 1, 4)
        row += 1

        # Background section header
        bg_header = QHBoxLayout()
        effects_label = QLabel(tr("RGBConfigurator", "Background:"))
        effects_label.setStyleSheet("font-weight: bold;")
        bg_header.addWidget(self.create_help_label("Background lighting when no keys are pressed."))
        bg_header.addWidget(effects_label)
        bg_header.addStretch()
        layout.addLayout(bg_header, row, 0, 1, 4)
        row += 1

        # Background dropdown
        bg_effect_label = QLabel(tr("RGBConfigurator", "Background:"))
        layout.addWidget(bg_effect_label, row, 0)
        background = HierarchicalDropdown(BACKGROUNDS_HIERARCHY)
        background.setStyleSheet("QComboBox { border-radius: 5px; }")
        background.valueChanged.connect(lambda idx, s=slot: self.on_background_changed(s, idx))
        layout.addWidget(background, row, 1, 1, 3)
        row += 1

        # Background Brightness + Speed on same row
        bg_brightness_label = QLabel(tr("RGBConfigurator", "Brightness:"))
        layout.addWidget(bg_brightness_label, row, 0)
        background_brightness = QSlider(QtCore.Qt.Horizontal)
        background_brightness.setMinimum(0)
        background_brightness.setMaximum(100)
        background_brightness.setValue(30)
        self._connect_throttled(background_brightness, self.on_background_brightness_changed, slot)  # ~1 HID/sec while dragging + on release
        layout.addWidget(background_brightness, row, 1)
        bg_speed_label = QLabel(tr("RGBConfigurator", "Speed:"))
        layout.addWidget(bg_speed_label, row, 2)
        bg_speed = QSlider(QtCore.Qt.Horizontal)
        bg_speed.setMinimum(0)
        bg_speed.setMaximum(255)
        bg_speed.setValue(128)
        bg_speed.setToolTip("Background animation speed.\n0 = Slowest, 128 = Normal, 255 = Fastest")
        self._connect_throttled(bg_speed, self.on_bg_speed_changed, slot)  # ~1 HID/sec while dragging + on release
        layout.addWidget(bg_speed, row, 3)
        row += 1

        # Background Color (per-slot, sets global RGB hue/sat on load)
        bg_color_label = QLabel(tr("RGBConfigurator", "Color:"))
        bg_color_label.setToolTip("Background color for this slot.\nSets the base hue and saturation for background lighting.")
        layout.addWidget(bg_color_label, row, 0)
        rgb_bg_color = ClickableLabel(" ")
        rgb_bg_color.setFixedHeight(20)
        rgb_bg_color.setFixedWidth(200)
        rgb_bg_color.setStyleSheet("QWidget { background-color: red; border: 1px solid #888; border-radius: 3px; }")
        rgb_bg_color.clicked.connect(lambda s=slot: self.on_rgb_bg_color_clicked(s))
        layout.addWidget(rgb_bg_color, row, 1)
        row += 1

        # Effect Colours section header
        colours_header = QHBoxLayout()
        colours_label = QLabel(tr("RGBConfigurator", "Effect Colours:"))
        colours_label.setStyleSheet("font-weight: bold;")
        colours_header.addWidget(self.create_help_label("Color settings for animations."))
        colours_header.addWidget(colours_label)
        colours_header.addStretch()
        layout.addLayout(colours_header, row, 0, 1, 4)
        row += 1

        # Colour Scheme
        colour_scheme_label = QLabel(tr("RGBConfigurator", "Colour Scheme:"))
        layout.addWidget(colour_scheme_label, row, 0)
        color_type = HierarchicalDropdown(CUSTOM_LIGHT_COLOR_TYPES_HIERARCHY)
        color_type.setStyleSheet("QComboBox { border-radius: 5px; }")
        color_type.valueChanged.connect(lambda idx, s=slot: self.on_color_type_changed(s, idx))
        layout.addWidget(color_type, row, 1, 1, 3)
        row += 1

        # Buttons
        buttons_layout = QHBoxLayout()

        save_button = QPushButton(tr("RGBConfigurator", "Save"))
        save_button.clicked.connect(lambda checked, s=slot: self.on_save_slot(s))
        save_button.setMinimumHeight(30)
        save_button.setStyleSheet("QPushButton { border-radius: 5px; }")
        save_button.setToolTip("Save current settings to this animation slot on the keyboard.")
        buttons_layout.addWidget(save_button)

        load_button = QPushButton(tr("RGBConfigurator", "Load Settings from Keyboard"))
        load_button.clicked.connect(lambda checked, s=slot: self.on_load_from_keyboard(s))
        load_button.setMinimumHeight(30)
        load_button.setStyleSheet("QPushButton { border-radius: 5px; }")
        load_button.setToolTip("Load current settings from the keyboard for this slot.\nRefreshes the display with saved values.")
        buttons_layout.addWidget(load_button)

        preset_combo = ArrowComboBox()
        preset_combo.addItem("Load Preset...")
        for preset in CUSTOM_LIGHT_PRESETS:
            preset_combo.addItem(preset)
        preset_combo.setMinimumHeight(30)
        preset_combo.setStyleSheet("QComboBox { border-radius: 5px; }")
        preset_combo.setToolTip("Load a predefined animation preset.\nQuickly set up common lighting effects.")
        preset_combo.currentIndexChanged.connect(lambda idx, s=slot: self.on_load_preset(s, idx))
        buttons_layout.addWidget(preset_combo)
        
        buttons_widget = QWidget()
        buttons_widget.setLayout(buttons_layout)
        layout.addWidget(buttons_widget, row, 0, 1, 4)

        # Store widgets for this slot
        self.slot_widgets[slot] = {
            'live_effect': live_effect,
            'live_style': live_style,
            'live_speed': live_speed,
            'live_brightness': live_brightness,
            'vel_brightness_live': vel_brightness_live,
            'macro_effect': macro_effect,
            'macro_style': macro_style,
            'macro_speed': macro_speed,
            'macro_brightness': macro_brightness,
            'vel_brightness_macro': vel_brightness_macro,
            'background': background,
            'background_brightness': background_brightness,
            'bg_speed': bg_speed,
            'color_type': color_type,
            'rgb_bg_color': rgb_bg_color,
            'preset_combo': preset_combo,
            'effect_hue': 0,
            'effect_sat': 255
        }

        self.slot_tabs.append(tab_widget)

    def on_main_tab_changed(self, index):
        """Handle main tab change - load EEPROM for lowest slot in group"""
        if index >= len(self.groups):
            return

        group_name, start_idx, end_idx = self.groups[index]
        lowest_slot = start_idx

        print(f"Main tab changed to {group_name}, loading EEPROM for lowest slot {lowest_slot}")
        self._ensure_slot_tab(lowest_slot)
        self.block_signals()
        self.load_slot_from_eeprom(lowest_slot)
        self._apply_slot_rgb_to_keyboard(lowest_slot)
        self._preview_slot_on_keyboard(lowest_slot)
        self.unblock_signals()

    def on_sub_tab_changed(self, index, start_slot):
        """Handle sub-tab switching within a group"""
        actual_slot = start_slot + index
        print(f"Sub-tab changed to {index}, actual slot {actual_slot}, loading EEPROM state")
        self._ensure_slot_tab(actual_slot)
        self.block_signals()
        self.load_slot_from_eeprom(actual_slot)
        self._apply_slot_rgb_to_keyboard(actual_slot)
        self._preview_slot_on_keyboard(actual_slot)
        self.unblock_signals()

    def _preview_slot_on_keyboard(self, slot):
        """Switch the device's live RGB mode to this slot so it previews the tab
        being edited. Non-persistent on the firmware side (restored on power
        cycle). Slots 0..48 have a dedicated effect; 49 is the randomize scratch."""
        if slot < 0 or slot >= 49:
            return
        kb = getattr(getattr(self, 'device', None), 'keyboard', None)
        if kb is not None and hasattr(kb, 'activate_custom_slot_preview'):
            try:
                kb.activate_custom_slot_preview(slot)
            except Exception as e:
                print(f"Slot preview failed: {e}")

    def _connect_throttled(self, slider, handler, slot):
        """Wire a slider so it emits at most ~1 HID write per second while being
        dragged, and always sends the final value when released. Avoids the
        per-tick write storm without losing live feedback (the value updates
        roughly once a second during a drag)."""
        import time
        state = {'last': 0.0}

        def on_changed(value, s=slot):
            now = time.monotonic()
            if now - state['last'] >= 1.0:
                state['last'] = now
                handler(s, value)

        def on_released(s=slot):
            state['last'] = time.monotonic()
            handler(s, slider.value())

        slider.setTracking(True)
        slider.valueChanged.connect(on_changed)
        slider.sliderReleased.connect(on_released)

    def _apply_slot_rgb_to_keyboard(self, slot):
        """Send a slot's stored hue/sat to the keyboard for live preview"""
        if slot not in self.slot_widgets:
            return
        if slot not in self.slots_loaded_from_device:
            # The slot's EEPROM read failed (or never ran) — the widgets still
            # hold init defaults (hue 0 / sat 255 = red). Don't push those.
            return
        widgets = self.slot_widgets[slot]
        h = widgets.get('effect_hue', 0)
        s = widgets.get('effect_sat', 255)
        if hasattr(self, 'device') and hasattr(self.device, 'keyboard') and hasattr(self.device.keyboard, 'rgb_hsv'):
            self.device.keyboard.set_vialrgb_color(h, s, self.device.keyboard.rgb_hsv[2])
        
    def get_current_slot_index(self):
        """Get the currently selected slot index across all groups"""
        # Get current main tab (group)
        main_tab_index = self.main_tab_widget.currentIndex()
        if main_tab_index >= len(self.groups):
            return 0
            
        group_name, start_idx, end_idx = self.groups[main_tab_index]
        
        # Get current sub-tab within the group
        sub_tab_widget = self.group_tab_widgets[group_name]
        sub_tab_index = sub_tab_widget.currentIndex()
        
        # Calculate actual slot index
        actual_slot = start_idx + sub_tab_index
        return min(actual_slot, 49)  # Ensure we don't exceed slot 49
            
    def get_currently_active_slot(self):
        """Get the slot number that is currently active - FIXED to use current slot"""
        try:
            if hasattr(self.device.keyboard, 'get_custom_animation_status'):
                status = self.device.keyboard.get_custom_animation_status()
                if status and len(status) > 1:
                    current_slot = status[1]  # Use status[1] (current slot) NOT status[2] (active slot)
                    # Validate slot is in valid range
                    if 0 <= current_slot < 50:
                        return current_slot
            # Fallback to slot 0 if anything fails
            return 0
        except Exception as e:
            print(f"Error getting current slot: {e}")
            return 0

    def on_load_from_keyboard(self, slot):
        """Load current RAM settings from CURRENT slot into this tab's GUI - FIXED VERSION"""
        try:
            self.block_signals()
            
            # Get the current slot (the one that's actually active)
            current_slot = self.get_currently_active_slot()
            print(f"Loading from current slot {current_slot} into tab {slot}")
            
            # Get the RAM data from the current slot
            config = self.device.keyboard.get_custom_slot_config(current_slot, from_eeprom=False)
            if config and len(config) >= 12:
                # Update the GUI widgets for the CURRENT TAB (slot), not the current slot
                self.update_slot_widgets(slot, config)
                print(f"Successfully loaded current slot {current_slot} settings into tab {slot}")
            else:
                print(f"Failed to get RAM config for current slot {current_slot}")
                
        except Exception as e:
            print(f"Error loading from current slot: {e}")
        finally:
            self.unblock_signals()
        
    def show_debug_popup(self, debug_info, title="Debug Info"):
        """Show debug information in a popup - ALWAYS appears"""
        try:
            from PyQt5.QtWidgets import QMessageBox, QTextEdit, QVBoxLayout, QDialog, QPushButton
            from PyQt5.QtCore import Qt
            
            # Create custom dialog for better text display
            dialog = QDialog()
            dialog.setWindowTitle(title)
            dialog.setModal(True)
            dialog.resize(800, 600)
            
            layout = QVBoxLayout()
            
            # Create text edit for scrollable debug info
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setFont(QtGui.QFont("Courier", 9))  # Monospace font
            text_edit.setText('\n'.join(debug_info))
            text_edit.setLineWrapMode(QTextEdit.NoWrap)
            layout.addWidget(text_edit)
            
            # Add close button
            close_button = QPushButton("Close")
            close_button.clicked.connect(dialog.accept)
            layout.addWidget(close_button)
            
            dialog.setLayout(layout)
            dialog.exec_()
            
        except Exception as e:
            # Fallback to simple message box if custom dialog fails
            try:
                from PyQt5.QtWidgets import QMessageBox
                msg = QMessageBox()
                msg.setWindowTitle(title)
                msg.setText("DEBUG INFO (Custom dialog failed):\n\n" + '\n'.join(debug_info[:20]))  # First 20 lines
                msg.setDetailedText('\n'.join(debug_info))  # All debug info in details
                msg.exec_()
            except Exception as e2:
                print(f"CRITICAL: Both popup methods failed!")
                print(f"Original error: {e}")
                print(f"Fallback error: {e2}")
                print("Debug info:")
                for line in debug_info:
                    print(line)
                
    def load_slot_from_eeprom(self, slot):
        """Load slot settings from EEPROM"""
        try:
            config = self.device.keyboard.get_custom_slot_config(slot, from_eeprom=True)  # Explicit EEPROM
            if config and len(config) >= 12:
                self.update_slot_widgets(slot, config)
        except Exception as e:
            print(f"Error loading EEPROM state for slot {slot}: {e}")

    def load_slot_from_ram(self, slot):
        """Load slot settings from current RAM state"""
        try:
            config = self.device.keyboard.get_custom_slot_config(slot, from_eeprom=False)  # Explicit RAM
            if config and len(config) >= 12:
                self.update_slot_widgets(slot, config)
        except Exception as e:
            print(f"Error loading RAM state for slot {slot}: {e}")
    
    def update_slot_widgets(self, slot, config):
        """Update GUI widgets for a slot with given config"""
        if slot not in self.slot_widgets:
            print(f"Warning: slot {slot} not in slot_widgets dict")
            return
            
        widgets = self.slot_widgets[slot]
        widgets['live_effect'].setCurrentIndex(min(config[2], 171))
        widgets['live_style'].setCurrentIndex(min(config[0], 33))
        widgets['macro_effect'].setCurrentIndex(min(config[3], 171))
        widgets['macro_style'].setCurrentIndex(min(config[1], 46))
        widgets['background'].setCurrentIndex(min(config[5], 121))
        widgets['bg_speed'].setValue(config[14] if len(config) > 14 else 128)
        widgets['color_type'].setCurrentIndex(min(config[7], 84))
        widgets['background_brightness'].setValue(config[9] if len(config) > 9 else 30)
        flags = config[4] if len(config) > 4 else 0
        widgets['vel_brightness_live'].setChecked(bool(flags & 0x02))
        widgets['vel_brightness_macro'].setChecked(bool(flags & 0x04))
        widgets['live_speed'].setValue(config[10] if len(config) > 10 else 128)
        widgets['macro_speed'].setValue(config[11] if len(config) > 11 else 128)
        widgets['live_brightness'].setValue(config[12] if len(config) > 12 else 255)
        widgets['macro_brightness'].setValue(config[13] if len(config) > 13 else 255)
        widgets['effect_hue'] = config[6] if len(config) > 6 else 0
        widgets['effect_sat'] = config[15] if len(config) > 15 else 255
        self.slots_loaded_from_device.add(slot)
        # Update swatch from per-slot values (do NOT touch global RGB here)
        self._update_rgb_color_swatch(slot)

    def _update_rgb_color_swatch(self, slot):
        """Update background color swatch for a single slot from its per-slot hue/sat"""
        if slot not in self.slot_widgets:
            return
        widgets = self.slot_widgets[slot]
        if 'rgb_bg_color' not in widgets:
            return
        h = widgets.get('effect_hue', 0)
        s = widgets.get('effect_sat', 255)
        color = QColor.fromHsvF(h / 255.0, s / 255.0, 1.0)
        widgets['rgb_bg_color'].setStyleSheet(
            "QWidget { background-color: %s; border: 1px solid #888; border-radius: 3px; }" % color.name())

    def _update_all_rgb_color_swatches(self):
        """Update background color swatches for all slots from their per-slot hue/sat"""
        for slot in self.slot_widgets:
            self._update_rgb_color_swatch(slot)

    def update_from_keyboard(self):
        """Periodic refresh - update status tracking only, do NOT reload widget values from EEPROM.
        Widget values are loaded only on explicit user actions (tab switch, load, preset).
        When the firmware switches active slot, set global RGB from that slot's stored color (Option A)."""
        self.block_signals()

        try:
            if hasattr(self.device.keyboard, 'get_custom_animation_status'):
                status = self.device.keyboard.get_custom_animation_status()
                if status is None:
                    # Comm failure: state unknown — do nothing rather than act
                    # on invented data.
                    self.unblock_signals()
                    return
                # status = get_custom_animation_status() (already stripped of the leading byte).
                # status[1] is the slot the device is currently RENDERING. There is no
                # "active slot" at status[2] (that's the per-slot enabled bitmap) and no
                # "randomize" field at status[6] — reading those triggered spurious color
                # changes off unrelated bitmap bits. Disable the randomize path entirely.
                randomize_active = False
                active_slot = status[1] if len(status) > 1 else 0

                prev_active = self.current_active_slot

                if randomize_active:
                    self.current_randomize_slot = active_slot
                    self.current_active_slot = active_slot
                else:
                    self.current_randomize_slot = None
                    self.current_active_slot = self.get_currently_active_slot()

                # When the active slot CHANGES, set global RGB from the new slot's
                # color. prev_active is None only on the first refresh after a
                # connect — never write to the device just for connecting.
                if (prev_active is not None and
                        self.current_active_slot != prev_active and
                        self.current_active_slot is not None):
                    self._sync_rgb_for_active_slot(self.current_active_slot)
            else:
                self.current_randomize_slot = None
                self.current_active_slot = self.get_current_slot_index()

        except Exception as e:
            print(f"Error in update_from_keyboard: {e}")

        self.unblock_signals()

    def _sync_rgb_for_active_slot(self, slot):
        """Set global RGB from a slot's stored hue/sat (Option A: main RGB follows active slot).
        Fetches from EEPROM if the slot hasn't been loaded into slot_widgets yet."""
        h = 0
        s = 255
        # Use widget values only when this slot was actually populated from the
        # device — the widgets are created for all 50 slots up front with init
        # defaults (hue 0 / sat 255 = red), which are NOT real data.
        loaded_from_eeprom = slot in self.slots_loaded_from_device and slot in self.slot_widgets
        if loaded_from_eeprom:
            widgets = self.slot_widgets[slot]
            h = widgets.get('effect_hue', 0)
            s = widgets.get('effect_sat', 255)

        if not loaded_from_eeprom:
            # Fetch directly from EEPROM for slots never visited in the GUI
            try:
                config = self.device.keyboard.get_custom_slot_config(slot, from_eeprom=True)
                if config and len(config) > 15:
                    h = config[6]
                    s = config[15]
                    loaded_from_eeprom = True
            except Exception as e:
                print(f"Error fetching slot {slot} color from EEPROM: {e}")

        if not loaded_from_eeprom:
            # No real data for this slot — send nothing rather than defaults.
            return

        if hasattr(self.device, 'keyboard') and hasattr(self.device.keyboard, 'rgb_hsv'):
            self.device.keyboard.set_vialrgb_color(h, s, self.device.keyboard.rgb_hsv[2])

    def set_slot_defaults(self, slot):
        """Set default values for a slot"""
        if slot not in self.slot_widgets:
            return
            
        widgets = self.slot_widgets[slot]
        widgets['live_effect'].setCurrentIndex(0)         # None
        widgets['live_style'].setCurrentIndex(0)          # TrueKey
        widgets['live_speed'].setValue(128)               # Default live speed
        widgets['macro_effect'].setCurrentIndex(0)        # None
        widgets['macro_style'].setCurrentIndex(0)         # TrueKey
        widgets['macro_speed'].setValue(128)              # Default macro speed
        widgets['background'].setCurrentIndex(0)          # None
        widgets['background_brightness'].setValue(30)     # 30% background brightness
        widgets['live_brightness'].setValue(255)          # Full live brightness
        widgets['macro_brightness'].setValue(255)         # Full macro brightness
        widgets['vel_brightness_live'].setChecked(False)  # Off by default
        widgets['vel_brightness_macro'].setChecked(False) # Off by default
        widgets['color_type'].setCurrentIndex(1)          # Channel
        widgets['bg_speed'].setValue(128)                  # Default background speed

    def valid(self):
        """Always return True - always show custom lights section"""
        return isinstance(self.device, VialKeyboard)

    def block_signals(self):
        """Block signals for all widgets"""
        for slot in self.slot_widgets.keys():  # Only iterate through actually created slots
            widgets = self.slot_widgets[slot]
            for widget in widgets.values():
                if hasattr(widget, 'blockSignals'):
                    widget.blockSignals(True)

    def unblock_signals(self):
        """Unblock signals for all widgets"""
        for slot in self.slot_widgets.keys():  # Only iterate through actually created slots
            widgets = self.slot_widgets[slot]
            for widget in widgets.values():
                if hasattr(widget, 'blockSignals'):
                    widget.blockSignals(False)

     # Event handlers - ALL FIXED to use current slot
    def on_live_effect_changed(self, slot, index):
        """Handle live effect change - send to this tab's slot"""
        current_slot = slot
        print(f"Live effect changed on tab {slot}, sending to current slot {current_slot}")
        
        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 2, index)
        else:
            print(f"Live effect changed: tab {slot} -> current slot {current_slot}, effect {index}")

    def on_live_style_changed(self, slot, index):
        """Handle live style change - send to this tab's slot"""
        current_slot = slot
        print(f"Live style changed on tab {slot}, sending to current slot {current_slot}")
        
        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 0, index)
        else:
            print(f"Live style changed: tab {slot} -> current slot {current_slot}, style {index}")

    def on_live_speed_changed(self, slot, value):
        """Handle live animation speed change - send to this tab's slot"""
        current_slot = slot
        print(f"Live speed changed on tab {slot}, sending to current slot {current_slot}")
        
        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 10, value)
        else:
            print(f"Live speed changed: tab {slot} -> current slot {current_slot}, speed {value}")

    def on_macro_effect_changed(self, slot, index):
        """Handle macro effect change - send to this tab's slot"""
        current_slot = slot
        print(f"Macro effect changed on tab {slot}, sending to current slot {current_slot}")
        
        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 3, index)
        else:
            print(f"Macro effect changed: tab {slot} -> current slot {current_slot}, effect {index}")

    def on_macro_style_changed(self, slot, index):
        """Handle macro style change - send to this tab's slot"""
        current_slot = slot
        print(f"Macro style changed on tab {slot}, sending to current slot {current_slot}")
        
        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 1, index)
        else:
            print(f"Macro style changed: tab {slot} -> current slot {current_slot}, style {index}")

    def on_macro_speed_changed(self, slot, value):
        """Handle macro animation speed change - send to this tab's slot"""
        current_slot = slot
        print(f"Macro speed changed on tab {slot}, sending to current slot {current_slot}")
        
        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 11, value)
        else:
            print(f"Macro speed changed: tab {slot} -> current slot {current_slot}, speed {value}")

    def on_background_changed(self, slot, index):
        """Handle background change - send to this tab's slot"""
        current_slot = slot
        print(f"Background changed on tab {slot}, sending to current slot {current_slot}")
        
        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 5, index)
        else:
            print(f"Background changed: tab {slot} -> current slot {current_slot}, index {index}")

    def on_background_brightness_changed(self, slot, value):
        """Handle background brightness change - send to this tab's slot"""
        current_slot = slot
        print(f"Background brightness changed on tab {slot}, sending to current slot {current_slot}")
        
        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 9, value)
        else:
            print(f"Background brightness changed: tab {slot} -> current slot {current_slot}, brightness {value}%")

    def on_vel_brightness_live_changed(self, slot, state):
        """Handle live velocity brightness toggle - send flags to this tab's slot"""
        current_slot = slot
        enabled = state != 0

        current_flags = 0
        if hasattr(self.device.keyboard, 'get_custom_slot_config'):
            config = self.device.keyboard.get_custom_slot_config(current_slot, from_eeprom=False)
            if config and len(config) > 4:
                current_flags = config[4]

        if enabled:
            current_flags |= 0x02   # Set bit 1 (live vel brightness)
        else:
            current_flags &= ~0x02  # Clear bit 1

        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 4, current_flags)

    def on_vel_brightness_macro_changed(self, slot, state):
        """Handle macro velocity brightness toggle - send flags to this tab's slot"""
        current_slot = slot
        enabled = state != 0

        current_flags = 0
        if hasattr(self.device.keyboard, 'get_custom_slot_config'):
            config = self.device.keyboard.get_custom_slot_config(current_slot, from_eeprom=False)
            if config and len(config) > 4:
                current_flags = config[4]

        if enabled:
            current_flags |= 0x04   # Set bit 2 (macro vel brightness)
        else:
            current_flags &= ~0x04  # Clear bit 2

        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 4, current_flags)

    def on_live_brightness_changed(self, slot, value):
        """Handle live brightness slider change - send to this tab's slot"""
        current_slot = slot
        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 12, value)

    def on_macro_brightness_changed(self, slot, value):
        """Handle macro brightness slider change - send to this tab's slot"""
        current_slot = slot
        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 13, value)

    def on_bg_speed_changed(self, slot, value):
        """Handle background speed change - send to this tab's slot (param 14 / background_speed)"""
        current_slot = slot
        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 14, value)

    def on_color_type_changed(self, slot, index):
        """Handle color type change - send to this tab's slot"""
        current_slot = slot
        print(f"Color type changed on tab {slot}, sending to current slot {current_slot}")

        if hasattr(self.device.keyboard, 'set_custom_slot_parameter'):
            self.device.keyboard.set_custom_slot_parameter(current_slot, 7, index)
        else:
            print(f"Color type changed: tab {slot} -> current slot {current_slot}, index {index}")

    def on_rgb_bg_color_clicked(self, slot):
        """Open color dialog for background color using per-slot hue/sat"""
        current_slot = self.get_current_slot_index()
        widgets = self.slot_widgets.get(current_slot, {})
        h = widgets.get('effect_hue', 0)
        s = widgets.get('effect_sat', 255)
        self._rgb_color_dialog = QColorDialog()
        self._rgb_color_dialog.setModal(True)
        self._rgb_color_dialog.finished.connect(lambda: self._on_rgb_bg_color_finished(slot))
        self._rgb_color_dialog.setCurrentColor(QColor.fromHsvF(h / 255.0, s / 255.0, 1.0))
        self._rgb_color_dialog.show()

    def _on_rgb_bg_color_finished(self, slot):
        """Apply selected background color to the current slot"""
        color = self._rgb_color_dialog.selectedColor()
        if not color.isValid():
            return
        h, s, v, a = color.getHsvF()
        if h < 0:
            h = 0
        hue_val = int(255 * h)
        sat_val = int(255 * s)
        # Store in per-slot widgets so swatch and save use the right values
        current_slot = self.get_current_slot_index()
        if current_slot in self.slot_widgets:
            self.slot_widgets[current_slot]['effect_hue'] = hue_val
            self.slot_widgets[current_slot]['effect_sat'] = sat_val
        # Also set global RGB for live preview on the keyboard
        if hasattr(self.device, 'keyboard'):
            self.device.keyboard.set_vialrgb_color(hue_val, sat_val, self.device.keyboard.rgb_hsv[2])
        # Update swatch from per-slot values
        self._update_rgb_color_swatch(current_slot)

    def on_save_slot(self, slot):
        """Save current GUI configuration to the tab slot's EEPROM"""
        try:
            # Get current GUI state for this tab
            widgets = self.slot_widgets[slot]
            
            # Collect all parameters from GUI
            live_pos = widgets['live_style'].currentIndex()
            macro_pos = widgets['macro_style'].currentIndex()
            live_anim = widgets['live_effect'].currentIndex()
            macro_anim = widgets['macro_effect'].currentIndex()
            flags = 0
            if widgets['vel_brightness_live'].isChecked():
                flags |= 0x02
            if widgets['vel_brightness_macro'].isChecked():
                flags |= 0x04
            background = widgets['background'].currentIndex()
            bg_speed = widgets['bg_speed'].value()
            color_type = widgets['color_type'].currentIndex()
            enabled = 1
            bg_brightness = widgets['background_brightness'].value()
            live_speed = widgets['live_speed'].value()
            macro_speed = widgets['macro_speed'].value()
            live_bright = widgets['live_brightness'].value()
            macro_bright = widgets['macro_brightness'].value()

            # Use per-slot stored hue/sat (set by color picker or loaded from EEPROM)
            effect_hue = widgets.get('effect_hue', 0)
            effect_sat = widgets.get('effect_sat', 255)

            # Send GUI state directly to the tab slot and save to EEPROM
            if hasattr(self.device.keyboard, 'set_custom_slot_all_parameters'):
                success = self.device.keyboard.set_custom_slot_all_parameters(
                    slot, live_pos, macro_pos, live_anim, macro_anim, flags,
                    background, effect_hue, color_type, enabled, bg_brightness,
                    live_speed, macro_speed, live_bright, macro_bright, bg_speed, effect_sat
                )
                if success:
                    print(f"Saved GUI state to tab slot {slot + 1} EEPROM")
                else:
                    print(f"Failed to save to tab slot {slot + 1}")
            else:
                print(f"Save slot {slot + 1} (keyboard method not implemented)")
                    
        except Exception as e:
            print(f"Error saving slot {slot + 1}: {e}")

    def on_load_preset(self, slot, index):
        """Load a preset configuration - now sets individual parameters"""
        if index == 0:  # "Load Preset..." header
            return
            
        preset_index = index - 1  # Adjust for header
        
        # Define preset configurations as individual parameter sets
        presets = [
            # Classic TrueKey: live(TrueKey,None), macro(TrueKey,None), Basic bg, All sustain, Channel color
            {'live_pos': 0, 'live_anim': 0, 'macro_pos': 0, 'macro_anim': 0, 'background': 1, 'sustain': 3, 'color': 1, 'bg_brightness': 30, 'live_speed': 255, 'macro_speed': 255},
            # Heat Effects: live(TrueKey,Heat), macro(TrueKey,Heat), Basic bg, All sustain, Heat color
            {'live_pos': 0, 'live_anim': 1, 'macro_pos': 0, 'macro_anim': 1, 'background': 1, 'sustain': 3, 'color': 3, 'bg_brightness': 25, 'live_speed': 255, 'macro_speed': 255},
            # Moving Dots: live(Zone,Moving Dots Row), macro(Zone,Moving Dots Row), Basic bg, All sustain, Channel color
            {'live_pos': 1, 'live_anim': 3, 'macro_pos': 1, 'macro_anim': 3, 'background': 1, 'sustain': 3, 'color': 1, 'bg_brightness': 35, 'live_speed': 255, 'macro_speed': 255},
            # BPM Disco: live(Quadrant,None), macro(Quadrant,None), BPM All Disco bg, All sustain, Macro color
            {'live_pos': 2, 'live_anim': 0, 'macro_pos': 2, 'macro_anim': 0, 'background': 46, 'sustain': 3, 'color': 2, 'bg_brightness': 40, 'live_speed': 255, 'macro_speed': 255},
            # Zone Lighting: live(Zone,None), macro(Zone,None), None bg, All sustain, Base color
            {'live_pos': 1, 'live_anim': 0, 'macro_pos': 1, 'macro_anim': 0, 'background': 0, 'sustain': 3, 'color': 0, 'bg_brightness': 0, 'live_speed': 255, 'macro_speed': 255},
            # Sustain Mode: live(TrueKey,Sustain), macro(TrueKey,Sustain), None bg, All sustain, Channel color
            {'live_pos': 0, 'live_anim': 2, 'macro_pos': 0, 'macro_anim': 2, 'background': 0, 'sustain': 3, 'color': 1, 'bg_brightness': 0, 'live_speed': 180, 'macro_speed': 180},
            # Performance Setup: live(TrueKey,None), macro(Zone,Heat), Basic bg, All sustain, Channel color
            {'live_pos': 0, 'live_anim': 0, 'macro_pos': 1, 'macro_anim': 1, 'background': 1, 'sustain': 3, 'color': 1, 'bg_brightness': 30, 'live_speed': 255, 'macro_speed': 255},
        ]
        
        if preset_index >= len(presets):
            return
            
        preset = presets[preset_index]
        
        try:
            # Set all parameters using individual calls
            if hasattr(self.device.keyboard, 'set_custom_slot_all_parameters'):
                success = self.device.keyboard.set_custom_slot_all_parameters(
                    slot,
                    preset['live_pos'], preset['macro_pos'], preset['live_anim'], preset['macro_anim'],
                    0, preset['background'], 0,
                    preset['color'], 1, preset['bg_brightness'], preset['live_speed'], preset['macro_speed'],
                    preset.get('live_brightness', 255), preset.get('macro_brightness', 255),
                    preset.get('background_speed', 128)
                )
                if success:
                    # Update GUI to reflect the loaded preset
                    widgets = self.slot_widgets[slot]
                    widgets['live_effect'].setCurrentIndex(preset['live_anim'])
                    widgets['live_style'].setCurrentIndex(preset['live_pos'])
                    widgets['macro_effect'].setCurrentIndex(preset['macro_anim'])
                    widgets['macro_style'].setCurrentIndex(preset['macro_pos'])
                    widgets['background'].setCurrentIndex(preset['background'])
                    widgets['bg_speed'].setValue(preset.get('background_speed', 128))
                    widgets['color_type'].setCurrentIndex(preset['color'])
                    widgets['background_brightness'].setValue(preset['bg_brightness'])
                    widgets['live_speed'].setValue(preset['live_speed'])
                    widgets['macro_speed'].setValue(preset['macro_speed'])
                    widgets['live_brightness'].setValue(preset.get('live_brightness', 255))
                    widgets['macro_brightness'].setValue(preset.get('macro_brightness', 255))
                    print(f"Loaded preset {preset_index} to slot {slot + 1}")
                else:
                    print(f"Failed to load preset {preset_index}")
            else:
                print(f"Load preset {preset_index} to slot {slot + 1} (keyboard method not implemented)")
        except Exception as e:
            print(f"Error loading preset: {e}")
        
        # Reset combo box to header
        self.slot_widgets[slot]['preset_combo'].setCurrentIndex(0)

# =============================================================================
# Advanced Key Lighting Handler
# =============================================================================

# State definitions matching firmware enum func_led_state
FUNC_LED_STATES = [
    # (index, name, group) — indices match the firmware func_led_state enum
    # Arpeggiator Quick Build states [0-5]
    (0, "QB: Empty / No Build", "Arpeggiator"),
    (1, "QB: Has Build (Idle)", "Arpeggiator"),
    (2, "QB: Playing", "Arpeggiator"),
    (3, "QB: Pending Play", "Arpeggiator"),
    (4, "QB: Pending Stop", "Arpeggiator"),
    (5, "QB: Building / Recording", "Arpeggiator"),
    # Arp Play button states [6-8]
    (6, "Play: Active / Playing", "Arpeggiator"),
    (7, "Play: Deferred Start", "Arpeggiator"),
    (8, "Play: Idle", "Arpeggiator"),
    # Arp Preset button states [9-11]
    (9, "Preset: Playing", "Arpeggiator"),
    (10, "Preset: Deferred", "Arpeggiator"),
    (11, "Preset: Idle", "Arpeggiator"),
    # Step Sequencer Quick Build states [52-57]
    (52, "QB: Empty / No Build", "Step Sequencer"),
    (53, "QB: Has Build (Idle)", "Step Sequencer"),
    (54, "QB: Playing", "Step Sequencer"),
    (55, "QB: Pending Play", "Step Sequencer"),
    (56, "QB: Pending Stop", "Step Sequencer"),
    (57, "QB: Building / Recording", "Step Sequencer"),
    # Seq Play button states [58-60]
    (58, "Play: Active / Playing", "Step Sequencer"),
    (59, "Play: Deferred Start", "Step Sequencer"),
    (60, "Play: Idle", "Step Sequencer"),
    # Seq Preset button states [61-63]
    (61, "Preset: Playing", "Step Sequencer"),
    (62, "Preset: Deferred", "Step Sequencer"),
    (63, "Preset: Idle", "Step Sequencer"),
    # Chord Progression slot button states [80-83]
    (80, "Idle / Stopped", "Chord Progression"),
    (81, "Playing", "Chord Progression"),
    (82, "Pending Play (Deferred Start)", "Chord Progression"),
    (83, "Pending Stop (Deferred Stop)", "Chord Progression"),
    # Vial Macros [12-14]
    (12, "Loop Idle", "Vial Macros"),
    (13, "Playing", "Vial Macros"),
    (14, "Deferred Start", "Vial Macros"),
    # Loop Pedal base states [15-20]
    (15, "Primed for Recording", "Loop Pedal"),
    (16, "Recording (REC/DUB)", "Loop Pedal"),
    (17, "Recording End Pending", "Loop Pedal"),
    (18, "Playing", "Loop Pedal"),
    (19, "Stopped / Muted", "Loop Pedal"),
    (20, "Empty Slot", "Loop Pedal"),
    # Loop Pedal overdub combination alt colors [48-51]
    (48, "Playing + OD Playing: Alt Color", "Loop Pedal"),
    (49, "Playing + OD Muted: Alt Color", "Loop Pedal"),
    (50, "Playing + OD Recording: Alt Color", "Loop Pedal"),
    (51, "Stopped + OD Playing: Alt Color", "Loop Pedal"),
    # Toggle keys [21-31]
    (21, "Standard: Idle", "Toggle Keys"),
    (22, "Standard: Held", "Toggle Keys"),
    (23, "Unconfigured", "Toggle Keys"),
    (24, "Multi-Key Step 1", "Toggle Keys"),
    (25, "Multi-Key Step 2", "Toggle Keys"),
    (26, "Multi-Key Step 3", "Toggle Keys"),
    (27, "Multi-Key Step 4", "Toggle Keys"),
    (28, "Multi-Key Step 5", "Toggle Keys"),
    (29, "Multi-Key Step 6", "Toggle Keys"),
    (30, "Multi-Key Step 7", "Toggle Keys"),
    (31, "Multi-Key Step 8", "Toggle Keys"),
    # Delay [32-33]
    (32, "Active", "Delay Slots"),
    (33, "Inactive", "Delay Slots"),
    # SmartChord [34-41]
    (34, "Toggle Latched", "SmartChord"),
    (35, "Chord 1", "SmartChord"),
    (36, "Chord 2", "SmartChord"),
    (37, "Chord 3", "SmartChord"),
    (38, "Chord 4", "SmartChord"),
    (39, "Chord 5", "SmartChord"),
    (40, "Chord 6", "SmartChord"),
    (41, "Chord 7", "SmartChord"),
    # AutoFader On/Off [78, 77]
    (78, "On", "AutoFader"),
    (77, "Off", "AutoFader"),
    # Dynamic Chord On/Off [74, 73]
    (74, "On", "Dynamic Chord"),
    (73, "Off", "Dynamic Chord"),
    # DrumLIVE On/Off [84-85]
    (84, "On", "DrumLIVE"),
    (85, "Off", "DrumLIVE"),
    # Drum Machine On/Off [86-87]
    (86, "On", "Drum Machine"),
    (87, "Off", "Drum Machine"),
    # Ear Trainer On/Off [88-89]
    (88, "On", "Ear Trainer"),
    (89, "Off", "Ear Trainer"),
    # Other [42-47]
    (42, "Caps Lock", "Other Indicators"),
    (43, "Gaming Mode", "Other Indicators"),
    (44, "Tap Tempo: Manual Beat 1", "Other Indicators"),
    (45, "Tap Tempo: Manual Beats 2-4", "Other Indicators"),
    (46, "Tap Tempo: Auto Beat 1", "Other Indicators"),
    (47, "Tap Tempo: Auto Beats 2-4", "Other Indicators"),
]

BLINK_MODES = ["Solid", "Slow Blink", "Fast Blink"]

# Group ordering for the dropdown
FUNC_LED_GROUPS = [
    "Arpeggiator", "Step Sequencer", "Chord Progression", "Vial Macros",
    "Loop Pedal", "Toggle Keys", "Delay Slots", "SmartChord", "AutoFader",
    "Dynamic Chord", "DrumLIVE", "Drum Machine", "Ear Trainer",
    "Other Indicators"
]

# Descriptions shown at top of each group section
FUNC_LED_GROUP_DESCRIPTIONS = {
    "Arpeggiator": "Colors for arpeggiator quick build, play button, and preset button LEDs.",
    "Step Sequencer": "Colors for step sequencer quick build, play button, and preset button LEDs.",
    "Chord Progression": "Colors for chord progression.",
    "Vial Macros": "Colors for Vial macro keys (loop idle, playing, deferred).",
    "Loop Pedal": (
        "Colors for the hardware loop pedal macro system.\n"
        "Base states control the primary color. Overdub 'Alt Color' entries control\n"
        "the secondary color in BPM-synced animations when overdub is active.\n"
        "The LED smoothly cycles between the base and alt colors."
    ),
    "Toggle Keys": "Colors for toggle key states and multi-key cycle steps.",
    "Delay Slots": "Colors for MIDI delay slot indicators.",
    "SmartChord": "Colors for SmartChord toggle and individual chord keys.",
    "AutoFader": "On/Off colors for AutoFader keys (On while the CC ramp is running).",
    "Dynamic Chord": "On/Off colors for Dynamic Chord keys.",
    "DrumLIVE": "On/Off colors for DrumLIVE keys (On while the live drum filter is active).",
    "Drum Machine": "On/Off colors for Drum Machine slot keys (On while a slot is playing).",
    "Ear Trainer": "On/Off colors for Ear Trainer keys (On while a session is running).",
    "Other Indicators": "Colors for caps lock, gaming mode, and tap tempo indicators.",
}


class AdvancedKeyLightingHandler(QObject):
    """Handler for the Advanced Key Lighting sub-tab - configurable functional LED colors"""

    update = pyqtSignal()

    def __init__(self, container):
        super().__init__()
        self.container = container
        self.keyboard = None
        self.widgets_created = False

        # State data: list of [h, s, v, blink] for each state
        self.state_data = [[0, 0, 0, 0] for _ in range(FUNC_LED_STATE_COUNT)]
        self.color_buttons = {}   # state_idx -> QPushButton
        self.blink_combos = {}    # state_idx -> QComboBox
        self.brightness_sliders = {}  # state_idx -> QSlider
        self.brightness_labels = {}   # state_idx -> QLabel

        self._build_ui()

    def _build_ui(self):
        """Build the Advanced Key Lighting UI with dropdown group selector"""
        layout = self.container

        # Title
        title = QLabel("Advanced Key Lighting")
        title.setStyleSheet("font-weight: bold; font-size: 14pt;")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title, 0, 0, 1, 2)

        # Description
        desc = QLabel("Configure colors, brightness, and blink patterns for functional key indicators.\n"
                       "These settings control LED colors for arpeggiator, sequencer, loop pedal, macros, toggles, and more.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray; font-size: 9pt;")
        desc.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(desc, 1, 0, 1, 2)

        # Top row: dropdown + action buttons
        top_layout = QHBoxLayout()

        # Group selector dropdown
        self.group_combo = QComboBox()
        self.group_combo.setMinimumWidth(160)
        for group_name in FUNC_LED_GROUPS:
            self.group_combo.addItem(group_name)
        self.group_combo.currentIndexChanged.connect(self._on_group_changed)
        top_layout.addWidget(QLabel("Category:"))
        top_layout.addWidget(self.group_combo)

        top_layout.addSpacing(20)

        self.btn_save = QPushButton("Save to Keyboard")
        self.btn_save.setMaximumWidth(140)
        self.btn_save.clicked.connect(self._on_save)
        top_layout.addWidget(self.btn_save)

        self.btn_load = QPushButton("Load from Keyboard")
        self.btn_load.setMaximumWidth(140)
        self.btn_load.clicked.connect(self._on_load)
        top_layout.addWidget(self.btn_load)

        self.btn_reset = QPushButton("Reset to Defaults")
        self.btn_reset.setMaximumWidth(140)
        self.btn_reset.clicked.connect(self._on_reset)
        top_layout.addWidget(self.btn_reset)

        top_widget = QWidget()
        top_widget.setLayout(top_layout)
        layout.addWidget(top_widget, 2, 0, 1, 2, QtCore.Qt.AlignCenter)

        # Stacked widget to hold one panel per group
        self.group_stack = QStackedWidget()
        self.group_stack.setMaximumWidth(800)

        for group_name in FUNC_LED_GROUPS:
            group_states = [(idx, name) for idx, name, grp in FUNC_LED_STATES if grp == group_name]
            if not group_states:
                # Empty placeholder
                self.group_stack.addWidget(QWidget())
                continue

            # Scroll area for the group
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

            group_widget = QWidget()
            grid = QGridLayout()
            grid.setColumnStretch(0, 2)  # State name
            grid.setColumnStretch(1, 0)  # Color button
            grid.setColumnStretch(2, 2)  # Brightness
            grid.setColumnStretch(3, 0)  # Brightness value
            grid.setColumnStretch(4, 1)  # Blink mode

            current_row = 0

            # Group description
            group_desc = FUNC_LED_GROUP_DESCRIPTIONS.get(group_name, "")
            if group_desc:
                desc_label = QLabel(group_desc)
                desc_label.setWordWrap(True)
                desc_label.setStyleSheet("color: #888; font-size: 8pt; font-style: italic; padding: 4px;")
                grid.addWidget(desc_label, current_row, 0, 1, 5)
                current_row += 1

            # Header row
            headers = ["State", "Color", "Brightness", "", "Blink Mode"]
            for col, header in enumerate(headers):
                lbl = QLabel(header)
                lbl.setStyleSheet("font-weight: bold; font-size: 8pt;")
                grid.addWidget(lbl, current_row, col)
            current_row += 1

            # Track if we need a separator for Loop Pedal overdub section
            in_overdub_section = False

            for state_idx, state_name in group_states:
                # Add separator before overdub alt colors in Loop Pedal
                if group_name == "Loop Pedal" and state_idx >= 48 and not in_overdub_section:
                    in_overdub_section = True
                    sep_label = QLabel("  Overdub Combination Colors")
                    sep_label.setStyleSheet(
                        "font-weight: bold; font-size: 8pt; color: #aaa; "
                        "border-top: 1px solid #555; padding-top: 6px; margin-top: 4px;")
                    grid.addWidget(sep_label, current_row, 0, 1, 5)
                    current_row += 1

                row = current_row

                # State name
                name_label = QLabel(state_name)
                name_label.setStyleSheet("font-size: 9pt;")
                grid.addWidget(name_label, row, 0)

                # Color button (shows current color, click to change)
                color_btn = QPushButton()
                color_btn.setFixedSize(30, 22)
                color_btn.setToolTip("Click to change color")
                color_btn.clicked.connect(lambda checked, sid=state_idx: self._on_color_click(sid))
                self.color_buttons[state_idx] = color_btn
                grid.addWidget(color_btn, row, 1)

                # Brightness slider
                slider = QSlider(Qt.Horizontal)
                slider.setMinimum(0)
                slider.setMaximum(255)
                slider.setFixedWidth(120)
                slider.valueChanged.connect(lambda val, sid=state_idx: self._on_brightness_change(sid, val))
                self.brightness_sliders[state_idx] = slider
                grid.addWidget(slider, row, 2)

                # Brightness value label
                val_label = QLabel("0")
                val_label.setFixedWidth(28)
                val_label.setStyleSheet("font-size: 8pt;")
                self.brightness_labels[state_idx] = val_label
                grid.addWidget(val_label, row, 3)

                # Blink mode combo
                blink_combo = QComboBox()
                blink_combo.addItems(BLINK_MODES)
                blink_combo.setFixedWidth(100)
                blink_combo.currentIndexChanged.connect(
                    lambda idx, sid=state_idx: self._on_blink_change(sid, idx))
                self.blink_combos[state_idx] = blink_combo
                grid.addWidget(blink_combo, row, 4)

                current_row += 1

            grid.setRowStretch(current_row, 1)
            group_widget.setLayout(grid)
            scroll.setWidget(group_widget)
            self.group_stack.addWidget(scroll)

        layout.addWidget(self.group_stack, 3, 0, 1, 2, QtCore.Qt.AlignCenter)
        self.widgets_created = True

    def _on_group_changed(self, index):
        """Switch the displayed group when dropdown changes"""
        self.group_stack.setCurrentIndex(index)

    def _hsv_to_qcolor(self, h, s, v):
        """Convert QMK HSV (0-255 each) to QColor"""
        # QMK H: 0-255 maps to 0-360 degrees
        # QColor.fromHsv expects H:0-359, S:0-255, V:0-255
        qh = int(h * 360 / 256) % 360
        return QColor.fromHsv(qh, s, v)

    def _qcolor_to_hsv(self, color):
        """Convert QColor to QMK HSV (0-255 each)"""
        qh, qs, qv, _ = color.getHsv()
        if qh < 0:
            qh = 0
        # QColor H: 0-359 -> QMK H: 0-255
        h = int(qh * 256 / 360) % 256
        return h, qs, qv

    def _update_color_button(self, state_idx):
        """Update a color button's background to reflect current state"""
        if state_idx not in self.color_buttons:
            return
        h, s, v, blink = self.state_data[state_idx]
        color = self._hsv_to_qcolor(h, s, v)
        btn = self.color_buttons[state_idx]
        btn.setStyleSheet(
            f"background-color: {color.name()}; border: 1px solid #666; border-radius: 3px;")

    def _update_all_widgets(self):
        """Refresh all widgets from state_data"""
        for state_idx in range(FUNC_LED_STATE_COUNT):
            h, s, v, blink = self.state_data[state_idx]

            self._update_color_button(state_idx)

            if state_idx in self.brightness_sliders:
                self.brightness_sliders[state_idx].blockSignals(True)
                self.brightness_sliders[state_idx].setValue(v)
                self.brightness_sliders[state_idx].blockSignals(False)

            if state_idx in self.brightness_labels:
                self.brightness_labels[state_idx].setText(str(v))

            if state_idx in self.blink_combos:
                self.blink_combos[state_idx].blockSignals(True)
                self.blink_combos[state_idx].setCurrentIndex(min(blink, 2))
                self.blink_combos[state_idx].blockSignals(False)

    def _on_color_click(self, state_idx):
        """Open color dialog for a state"""
        h, s, v, blink = self.state_data[state_idx]
        current_color = self._hsv_to_qcolor(h, s, v)

        color = QColorDialog.getColor(current_color, None, "Select Color")
        if color.isValid():
            new_h, new_s, new_v = self._qcolor_to_hsv(color)
            self.state_data[state_idx] = [new_h, new_s, new_v, blink]
            self._update_color_button(state_idx)
            # Update brightness slider to match new V
            if state_idx in self.brightness_sliders:
                self.brightness_sliders[state_idx].blockSignals(True)
                self.brightness_sliders[state_idx].setValue(new_v)
                self.brightness_sliders[state_idx].blockSignals(False)
            if state_idx in self.brightness_labels:
                self.brightness_labels[state_idx].setText(str(new_v))
            # Send to firmware immediately
            self._send_state_to_firmware(state_idx)

    def _on_brightness_change(self, state_idx, value):
        """Handle brightness slider change"""
        self.state_data[state_idx][2] = value  # Update V
        if state_idx in self.brightness_labels:
            self.brightness_labels[state_idx].setText(str(value))
        self._update_color_button(state_idx)
        self._send_state_to_firmware(state_idx)

    def _on_blink_change(self, state_idx, blink_idx):
        """Handle blink mode change"""
        self.state_data[state_idx][3] = blink_idx
        self._send_state_to_firmware(state_idx)

    # =========================================================================
    # HID Communication
    # =========================================================================

    def _send_state_to_firmware(self, state_idx):
        """Send a single state update to firmware"""
        if not hasattr(self, 'keyboard') or not self.keyboard:
            return
        try:
            import struct
            h, s, v, blink = self.state_data[state_idx]
            data = struct.pack("BBBBBBB", CMD_VIA_VIAL_PREFIX, HID_CMD_FUNC_LED_SET,
                               state_idx, h, s, v, blink)
            response = self.keyboard.usb_send(self.keyboard.dev, data, retries=20)
            if not response:
                print(f"Error sending functional LED state {state_idx}: no response from keyboard")
        except Exception as e:
            print(f"Error sending functional LED state {state_idx}: {e}")

    def _load_all_from_firmware(self):
        """Load all states from firmware (paginated, 7 states per packet)"""
        if not hasattr(self, 'keyboard') or not self.keyboard:
            return
        try:
            import struct
            offset = 0
            while offset < FUNC_LED_STATE_COUNT:
                count = min(7, FUNC_LED_STATE_COUNT - offset)
                data = struct.pack("BBBB", CMD_VIA_VIAL_PREFIX, HID_CMD_FUNC_LED_GET,
                                   offset, count)
                response = self.keyboard.usb_send(self.keyboard.dev, data, retries=20)

                if response and len(response) >= 1 + count * 4 and response[0] == 0x01:
                    for i in range(count):
                        base = 1 + i * 4
                        h = response[base]
                        s = response[base + 1]
                        v = response[base + 2]
                        blink = response[base + 3]
                        self.state_data[offset + i] = [h, s, v, blink]
                else:
                    print(f"Error loading functional LED states at offset {offset}")
                    return

                offset += count

            self._update_all_widgets()
        except Exception as e:
            print(f"Error loading functional LED config: {e}")

    def _on_save(self):
        """Save all states to EEPROM"""
        if not hasattr(self, 'keyboard') or not self.keyboard:
            return
        try:
            import struct
            data = struct.pack("BBB", CMD_VIA_VIAL_PREFIX, HID_CMD_FUNC_LED_SAVE, 0x00)
            response = self.keyboard.usb_send(self.keyboard.dev, data, retries=20)
            if not response:
                print("Error saving functional LED config: no response from keyboard")
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(None, "Error",
                                    "Failed to save functional LED settings to the keyboard.")
        except Exception as e:
            print(f"Error saving functional LED config: {e}")

    def _on_load(self):
        """Load all states from EEPROM and refresh UI"""
        if not hasattr(self, 'keyboard') or not self.keyboard:
            return
        try:
            import struct
            # Tell firmware to reload from EEPROM
            data = struct.pack("BBB", CMD_VIA_VIAL_PREFIX, HID_CMD_FUNC_LED_SAVE, 0x01)
            self.keyboard.usb_send(self.keyboard.dev, data, retries=20)
            # Then load into GUI
            self._load_all_from_firmware()
        except Exception as e:
            print(f"Error loading functional LED config: {e}")

    def _on_reset(self):
        """Reset to factory defaults"""
        if not hasattr(self, 'keyboard') or not self.keyboard:
            return
        try:
            import struct
            data = struct.pack("BBB", CMD_VIA_VIAL_PREFIX, HID_CMD_FUNC_LED_SAVE, 0xFF)
            self.keyboard.usb_send(self.keyboard.dev, data, retries=20)
            # Reload into GUI
            self._load_all_from_firmware()
        except Exception as e:
            print(f"Error resetting functional LED config: {e}")

    # =========================================================================
    # Handler Interface (called by RGBConfigurator)
    # =========================================================================

    def start(self):
        pass

    def show(self):
        pass

    def block_signals(self):
        pass

    def unblock_signals(self):
        pass

    def update_from_keyboard(self):
        """Called when keyboard is connected - load config"""
        self._load_all_from_firmware()

    def set_device(self, device):
        self.device = device
        if device and hasattr(device, 'keyboard'):
            self.keyboard = device.keyboard
        else:
            self.keyboard = None

    def valid(self):
        return self.keyboard is not None


class RGBConfigurator(BasicEditor):

    def __init__(self):
        super().__init__()

        # Create tab widget (similar to QMK Settings)
        self.tabs_widget = QTabWidget()
        self.addWidget(self.tabs_widget)

        # Tab 1: Basic - for basic RGB controls (with title/description)
        self.basic_container = QGridLayout()
        self.basic_tab = self._create_tab_with_title(
            self.basic_container,
            "Basic RGB",
            "Configure global RGB lighting settings including brightness,\n"
            "effects, speed, and color. Changes apply to all keys."
        )
        self.tabs_widget.addTab(self.basic_tab, tr("RGBConfigurator", "Basic"))

        # Tab 2: Lighting Configurator - for per-key RGB
        self.lighting_container = QGridLayout()
        self.lighting_tab = self._create_tab_with_scroll(self.lighting_container)
        self.tabs_widget.addTab(self.lighting_tab, tr("RGBConfigurator", "Lighting Configurator"))

        # Tab 3: Custom Lights - side by side layout (Basic left, Custom right)
        self.custom_basic_container = QGridLayout()
        self.custom_lights_container = QGridLayout()
        self.custom_tab = self._create_custom_lights_tab()
        self.tabs_widget.addTab(self.custom_tab, tr("RGBConfigurator", "Custom Lights"))

        # Tab 4: Advanced Key Lighting - configurable functional LED colors
        self.adv_key_lighting_container = QGridLayout()
        self.adv_key_lighting_tab = self._create_tab_with_scroll(self.adv_key_lighting_container)
        self.tabs_widget.addTab(self.adv_key_lighting_tab, tr("RGBConfigurator", "Advanced Key Lighting"))

        # Initialize handlers for Basic tab
        self.handler_backlight = QmkBacklightHandler(self.basic_container)
        self.handler_backlight.update.connect(self.update_from_keyboard)
        self.handler_rgblight = QmkRgblightHandler(self.basic_container)
        self.handler_rgblight.update.connect(self.update_from_keyboard)
        self.handler_vialrgb = VialRGBHandler(self.basic_container)
        self.handler_vialrgb.update.connect(self.update_from_keyboard)

        # Add the rescan button handler - NO UPDATE CONNECTION
        self.handler_rescan = RescanButtonHandler(self.basic_container)
        # REMOVED: self.handler_rescan.update.connect(self.update_from_keyboard)

        # Add the per-layer RGB handler
        self.handler_layer_rgb = LayerRGBHandler(self.basic_container)
        self.handler_layer_rgb.update.connect(self.update_from_keyboard)

        # Initialize handler for Lighting Configurator tab (per-key RGB)
        self.handler_per_key_rgb = PerKeyRGBHandler(self.lighting_container)
        # No update connection needed for per-key handler

        # Initialize handlers for Custom Lights tab - Basic side (left)
        self.handler_backlight_custom = QmkBacklightHandler(self.custom_basic_container)
        self.handler_backlight_custom.update.connect(self.update_from_keyboard)
        self.handler_rgblight_custom = QmkRgblightHandler(self.custom_basic_container)
        self.handler_rgblight_custom.update.connect(self.update_from_keyboard)
        self.handler_vialrgb_custom = VialRGBHandler(self.custom_basic_container)
        self.handler_vialrgb_custom.update.connect(self.update_from_keyboard)
        self.handler_rescan_custom = RescanButtonHandler(self.custom_basic_container)
        self.handler_layer_rgb_custom = LayerRGBHandler(self.custom_basic_container)
        self.handler_layer_rgb_custom.update.connect(self.update_from_keyboard)

        # Custom Lights handler (right side)
        self.handler_custom_lights = CustomLightsHandler(self.custom_lights_container)
        self.handler_custom_lights.update.connect(self.update_from_keyboard)

        # Advanced Key Lighting handler (Tab 4)
        self.handler_adv_key_lighting = AdvancedKeyLightingHandler(self.adv_key_lighting_container)

        self.handlers = [self.handler_backlight, self.handler_rgblight,
                        self.handler_vialrgb, self.handler_rescan,
                        self.handler_layer_rgb, self.handler_per_key_rgb,
                        self.handler_backlight_custom, self.handler_rgblight_custom,
                        self.handler_vialrgb_custom, self.handler_rescan_custom,
                        self.handler_layer_rgb_custom, self.handler_custom_lights,
                        self.handler_adv_key_lighting]

        # Save button is now inside the Basic tab, after LayerRGBHandler

    def _create_tab_with_title(self, container, title, description):
        """Helper method to create a tab with title, description, and scroll area - centered"""
        content_layout = QVBoxLayout()
        content_layout.addStretch()

        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        content_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; font-size: 9pt;")
        desc_label.setAlignment(QtCore.Qt.AlignCenter)
        content_layout.addWidget(desc_label)

        # Layer info
        layer_info = QLabel("Select a layer button to apply lighting effects only to that layer\n"
                           "when Per-Layer RGB is enabled.")
        layer_info.setWordWrap(True)
        layer_info.setStyleSheet("color: gray; font-size: 9pt; font-style: italic;")
        layer_info.setAlignment(QtCore.Qt.AlignCenter)
        content_layout.addWidget(layer_info)

        content_layout.addSpacing(10)

        w = QWidget()
        w.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        w.setLayout(container)
        content_layout.addWidget(w, alignment=QtCore.Qt.AlignHCenter)
        content_layout.addStretch()

        # Create widget for content layout
        content_widget = QWidget()
        content_widget.setLayout(content_layout)

        # Wrap in scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidget(content_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        return scroll_area

    def _create_custom_lights_tab(self):
        """Create Custom Lights tab with side-by-side layout"""
        content_layout = QVBoxLayout()
        content_layout.addStretch()

        # Title (centered)
        title_label = QLabel("Custom Lights")
        title_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        content_layout.addWidget(title_label)

        # Description (centered)
        desc_label = QLabel("Create and edit custom RGB animations. Basic controls on the left,\n"
                           "custom animation slots on the right.")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; font-size: 9pt;")
        desc_label.setAlignment(QtCore.Qt.AlignCenter)
        content_layout.addWidget(desc_label)

        content_layout.addSpacing(10)

        # Side by side layout (centered)
        h_layout = QHBoxLayout()
        h_layout.addStretch()

        # Left side: Basic RGB Functions (max 450px)
        basic_group = QGroupBox("Basic RGB Functions")
        basic_group.setMaximumWidth(450)
        basic_widget = QWidget()
        basic_widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        basic_widget.setLayout(self.custom_basic_container)
        basic_group_layout = QVBoxLayout()
        basic_group_layout.addWidget(basic_widget, alignment=QtCore.Qt.AlignTop)
        basic_group.setLayout(basic_group_layout)
        h_layout.addWidget(basic_group, alignment=QtCore.Qt.AlignTop)

        # Right side: Custom Lights (fixed 750x550)
        custom_group = QGroupBox("Custom Animation Slots")
        custom_group.setFixedWidth(750)
        custom_group.setFixedHeight(600)
        custom_widget = QWidget()
        custom_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        custom_widget.setLayout(self.custom_lights_container)
        custom_group_layout = QVBoxLayout()
        custom_group_layout.addWidget(custom_widget)
        custom_group.setLayout(custom_group_layout)
        h_layout.addWidget(custom_group)

        h_layout.addStretch()
        content_layout.addLayout(h_layout)
        content_layout.addStretch()

        # Create widget for content layout
        content_widget = QWidget()
        content_widget.setLayout(content_layout)

        # Wrap in scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidget(content_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        return scroll_area

    def _create_tab_with_scroll(self, container):
        """Helper method to create a tab with scroll area"""
        content_layout = QVBoxLayout()
        content_layout.addStretch()

        w = QWidget()
        w.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        w.setLayout(container)
        content_layout.addWidget(w, alignment=QtCore.Qt.AlignHCenter)
        content_layout.addStretch()

        # Create widget for content layout
        content_widget = QWidget()
        content_widget.setLayout(content_layout)

        # Wrap in scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidget(content_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        return scroll_area

    def on_save(self):
        self.device.keyboard.save_rgb()

    def valid(self):
        # Always show RGB configurator for VialKeyboard
        return isinstance(self.device, VialKeyboard)

    def block_signals(self):
        for h in self.handlers:
            h.block_signals()

    def unblock_signals(self):
        for h in self.handlers:
            h.unblock_signals()

    def update_from_keyboard(self):
        self.device.keyboard.reload_rgb()
        
        # Check for layer RGB support
        if hasattr(self.device.keyboard, 'reload_layer_rgb_support'):
            self.device.keyboard.reload_layer_rgb_support()

        # Check for custom lights support  
        if hasattr(self.device.keyboard, 'reload_custom_lights_support'):
            self.device.keyboard.reload_custom_lights_support()

        self.block_signals()

        for h in self.handlers:
            h.update_from_keyboard()

        self.unblock_signals()

    def rebuild(self, device):
        super().rebuild(device)

        for h in self.handlers:
            h.set_device(device)

        if not self.valid():
            return

        self.update_from_keyboard()
        
        