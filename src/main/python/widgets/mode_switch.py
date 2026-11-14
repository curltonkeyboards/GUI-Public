# SPDX-License-Identifier: GPL-2.0-or-later
"""The "Basic mode" ON / OFF switch (the window has one, at the top right of
its menu bar). Any number can exist; they all show and set the one mode."""

import ui_mode
from util import tr
from widgets.toggle_switch import ToggleSwitch


def make_mode_switch():
    switch = ToggleSwitch(tr("MainWindow", "Basic mode"))
    switch.set_on(ui_mode.is_basic())
    switch.setToolTip(tr(
        "MainWindow", "On: a home screen with a button for each tab.\nOff: every tab in one row along the top."))
    switch.switched.connect(lambda on: ui_mode.set_mode(ui_mode.BASIC if on else ui_mode.ADVANCED))
    ui_mode.on_change(lambda: switch.set_on(ui_mode.is_basic()))
    return switch
