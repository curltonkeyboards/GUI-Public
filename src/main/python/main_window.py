# SPDX-License-Identifier: GPL-2.0-or-later
import base64
import json
import logging
import platform
import time
from json import JSONDecodeError

from PyQt5.QtCore import Qt, QSettings, QStandardPaths, QTimer, QRect, QT_VERSION_STR
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QWidget, QComboBox, QToolButton, QHBoxLayout, QVBoxLayout, QMainWindow, QAction, qApp, \
    QFileDialog, QDialog, QTabWidget, QActionGroup, QMessageBox, QLabel, QStackedWidget, QPushButton, QGridLayout, QFrame

import os
import sys

from protocol.feature_names import get_feature_name_manager

# Startup logging helper
def _startup_log(msg):
    try:
        from startup_dialog import startup_log
        startup_log(msg)
    except ImportError:
        pass

from widgets.combo_box import ArrowComboBox
from autorefresh.autorefresh import Autorefresh
from constants import WINDOW_WIDTH, WINDOW_HEIGHT
from widgets.editor_container import EditorContainer
from widgets.home_page import HomePage
from widgets.toggle_switch import ToggleSwitch
from editor.quickbuild_tab import QuickBuildTab
from editor.grouped_editor import GroupedEditor
from editor.firmware_flasher import FirmwareFlasher
from editor.combo_keys import ComboKeys
from protocol.keyboard_comm import ProtocolError
from protocol.clone_migrations import CloneMigrationError, can_migrate, migrate_clone
from editor.keymap_editor import KeymapEditor
from editor.trigger_settings import TriggerSettingsTab
from editor.dks_settings import DKSSettingsTab
from editor.toggle_settings import ToggleSettingsTab
from editor.layout_editor import LayoutEditor
from editor.macro_recorder import MacroRecorder
from editor.macro_settings import MacroSettingsDefs
from editor.rgb_configurator import RGBConfigurator
from tabbed_keycodes import TabbedKeycodes
from editor.tap_dance import TapDance
from unlocker import Unlocker
from util import tr, EXAMPLE_KEYBOARDS, KeycodeDisplay, EXAMPLE_KEYBOARD_PREFIX, \
    MIDISWITCH_KEYBOARD_UID, LATEST_FIRMWARE_VERSION
from vial_device import VialKeyboard, VialDummyKeyboard, VialVirtualKeyboard
from editor.matrix_test import MatrixTest
from editor.matrix_test import MIDIswitchSettingsConfigurator
from editor.matrix_test import GamingConfigurator
from editor.velocity_tab import VelocityTab
from editor.midi_patch import MIDIPatchBay
from editor.loop_manager import LoopManager
from editor.arpeggiator import Arpeggiator, StepSequencer
from editor.delay_tab import DelayTab

import themes
import ui_mode


class MainWindow(QMainWindow):

    def __init__(self, appctx):
        super().__init__()
        _startup_log("MainWindow.__init__ starting...")
        init_start = time.time()

        self.appctx = appctx

        self.ui_lock_count = 0
        self.lockable_actions = []          # menu actions that must wait while the UI is locked
        self._clone_transfer_running = False
        # A device change that arrives while another one is still being
        # handled (or in the middle of a click on a tab) waits here: see
        # on_devices_updated.
        self._selecting_device = False
        self._waiting_devices = None
        # What to come back to when the keyboard returns after being gone for
        # a moment (it restarts after a clone or a firmware update).
        self._editor_to_restore = None
        self._group_to_restore = None

        self.settings = QSettings("MIDIswitch", "SwitchStation")
        if self.settings.value("size", None):
            self.resize(self.settings.value("size"))
        else:
            self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        _pos = self.settings.value("pos", None)
        # NOTE: QDesktopWidget is obsolete, but QApplication.screenAt only usable in Qt 5.10+
        if _pos and qApp.desktop().geometry().contains(QRect(_pos, self.size())):
        #if _pos and qApp.screenAt(_pos) and qApp.screenAt(_pos + (self.rect().bottomRight())):
            self.move(self.settings.value("pos"))

        themes.Theme.set_theme(self.get_theme())

        # Set modern font for 2025 aesthetic
        modern_font = QFont()
        # Try modern system fonts in order of preference
        if sys.platform == "darwin":
            modern_font.setFamily("SF Pro Display")
        elif sys.platform == "win32":
            modern_font.setFamily("Segoe UI")
        else:
            modern_font.setFamily("Ubuntu")
        modern_font.setPointSize(10)
        modern_font.setWeight(QFont.Normal)
        modern_font.setStyleHint(QFont.SansSerif)
        qApp.setFont(modern_font)

        self.combobox_devices = ArrowComboBox()
        self.combobox_devices.currentIndexChanged.connect(self.on_device_selected)

        self.btn_refresh_devices = QToolButton()
        self.btn_refresh_devices.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_refresh_devices.setText(tr("MainWindow", "Refresh"))
        self.btn_refresh_devices.clicked.connect(self.on_click_refresh)

        layout_combobox = QHBoxLayout()
        layout_combobox.addWidget(self.combobox_devices)
        if sys.platform != "emscripten":
            layout_combobox.addWidget(self.btn_refresh_devices)

        _startup_log("Creating UI editors...")
        t0 = time.time()
        self.layout_editor = LayoutEditor()
        self.keymap_editor = KeymapEditor(self.layout_editor)
        _startup_log(f"  LayoutEditor + KeymapEditor ({time.time()-t0:.2f}s)")

        t0 = time.time()
        self.trigger_settings = TriggerSettingsTab(self.layout_editor)
        _startup_log(f"  TriggerSettingsTab ({time.time()-t0:.2f}s)")

        # Set up references between Actuation Settings and Trigger Settings for synchronization
        self.keymap_editor.quick_actuation.trigger_settings_ref = self.trigger_settings
        self.trigger_settings.actuation_widget_ref = self.keymap_editor.quick_actuation

        # Connect signal for tab switching
        self.keymap_editor.quick_actuation.enable_per_key_requested.connect(self.switch_to_trigger_settings)

        # Create DKS Settings tab
        t0 = time.time()
        self.dks_settings = DKSSettingsTab(self.layout_editor)
        _startup_log(f"  DKSSettingsTab ({time.time()-t0:.2f}s)")

        # Create Toggle Settings tab
        t0 = time.time()
        self.toggle_settings = ToggleSettingsTab(self.layout_editor)
        _startup_log(f"  ToggleSettingsTab ({time.time()-t0:.2f}s)")

        t0 = time.time()
        self.firmware_flasher = FirmwareFlasher(self)
        self.macro_recorder = MacroRecorder()
        self.tap_dance = TapDance()
        self.combo_keys = ComboKeys()
        MacroSettingsDefs.initialize(appctx)
        self.matrix_tester = MatrixTest(self.layout_editor)
        self.velocity_tab = VelocityTab(self.layout_editor)
        self.rgb_configurator = RGBConfigurator()
        _startup_log(f"  Core editors (Firmware, Macro, Tap/Hold, etc) ({time.time()-t0:.2f}s)")

        # Connect keymap_editor to matrix_tester for status value adjustments
        self.keymap_editor.set_matrix_test_reference(self.matrix_tester)
        
        # Initialize the new configurators
        t0 = time.time()
        self.MIDIswitchSettingsConfigurator = MIDIswitchSettingsConfigurator()
        self.gaming_configurator = GamingConfigurator()

        # Initialize MIDI Patch and Loop Manager tabs
        self.midi_patchbay = MIDIPatchBay()
        self.loop_manager = LoopManager()
        self.arpeggiator = Arpeggiator()
        self.step_sequencer = StepSequencer()
        self.delay_tab = DelayTab()
        _startup_log(f"  MIDI configurators ({time.time()-t0:.2f}s)")

        # Updated editors list with new tabs inserted between Lighting and Tap Dance
        # Gaming Settings is a sub-tab of Settings, not a tab of its own
        self.MIDIswitchSettingsConfigurator.add_sub_editor(self.gaming_configurator, "Gaming Settings")

        # QuickBuild: the overview of the 100 QuickBuild buttons, with the editors
        # for what they play as tabs beside it (they used to be tabs of their own;
        # Multi Channel used to be a sub-tab of Settings).
        self.quickbuild = QuickBuildTab()
        self.quickbuild.add_editor(self.arpeggiator, "Arpeggiator")
        self.quickbuild.add_editor(self.step_sequencer, "Step Sequencer")
        self.quickbuild.add_editor(self.delay_tab, "Delay")
        from editor.qb_pages import (KeySplitPage, DrumLivePage, RhythmEnginePage, DrumMachinePage,
                                     AutoFaderPage, SmartChordPage)
        self.quickbuild.add_page(SmartChordPage(), "SmartChord")
        self.quickbuild.add_page(KeySplitPage(), "KeySplit")
        self.quickbuild.add_page(
            self.MIDIswitchSettingsConfigurator.take_sub_tab("Multi Channel Settings"), "Multi Channel")
        self.quickbuild.add_page(DrumLivePage(), "DrumLIVE")
        self.quickbuild.add_page(RhythmEnginePage(), "Rhythm Engine")
        self.quickbuild.add_page(DrumMachinePage(), "Drum Machine")
        self.quickbuild.add_page(AutoFaderPage(), "AutoFader")

        # Advanced Keys: the special kinds of key, each of which used to be a
        # tab of its own
        self.advanced_keys = GroupedEditor("MainWindow")
        self.advanced_keys.add_editor(self.macro_recorder, "Macros")
        self.advanced_keys.add_editor(self.toggle_settings, "Toggle")
        self.advanced_keys.add_editor(self.tap_dance, "Tap/Hold")
        self.advanced_keys.add_editor(self.combo_keys, "Key Shortcuts")
        self.advanced_keys.add_editor(self.dks_settings, "Dynamic Keystroke")

        # (The Loop Manager is built and kept up to date but has no tab: loops
        # are saved and loaded from MIDIswitch Play.)
        self.editors = [(self.keymap_editor, "Keymap"), (self.trigger_settings, "Actuation"),
                        (self.velocity_tab, "Articulation"), (self.rgb_configurator, "Lighting"),
                        (self.advanced_keys, "Advanced Keys"),
                        (self.quickbuild, "QuickBuild"), (self.midi_patchbay, "MIDI Link"),
                        (self.MIDIswitchSettingsConfigurator, "Settings"),
                        (self.matrix_tester, "Calibration"),
                        (self.layout_editor, "Layout"),
                        (self.firmware_flasher, "Firmware updater")]

        ui_mode.on_change(self.on_mode_changed)

        # Basic mode is a home screen with one bubble per tab; a bubble opens
        # that tab on its own (no row of tabs), with a Home button to come
        # back. Advanced mode is every tab in one row. Every page shows all of
        # its options either way. (bubble name, description, editors)
        descriptions = {
            "Keymap": "Choose what each key, the knob and the footswitch do, layer by layer",
            "Actuation": "How far each key goes down before it plays, and rapid trigger",
            "Articulation": "How your playing turns into velocity, aftertouch and legato",
            "Lighting": "Light effects, colours, brightness and key indicators",
            "Advanced Keys": "Macros, toggles, tap/hold keys, key shortcuts and dynamic keystrokes",
            "QuickBuild": "One-press arpeggios, sequences, delays, chords, drums and more",
            "MIDI Link": "Pass MIDI between the MIDIswitch and other devices and apps",
            "Settings": "Channels, transpose, looping, stop mode, routing and more",
            "Calibration": "Test every key and tune the sensors",
            "Layout": "Choose the keyboard's layout options",
            "Firmware updater": "Update the MIDIswitch's firmware",
        }
        self.groups = [("Advanced Settings" if label == "Settings" else label,
                        descriptions.get(label, ""), [editor])
                       for editor, label in self.editors]
        self.current_group = None

        Unlocker.global_layout_editor = self.layout_editor
        Unlocker.global_main_window = self

        self.current_tab = None
        # Each editor is wrapped in an EditorContainer exactly once and the
        # wrapper is reused across refresh_tabs() calls (see refresh_tabs).
        self.editor_containers = {}
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        # a tab's first opening can keep the app busy for a moment: cover the
        # page with "Loading..." from the click until it is ready
        self.tabs.tabBarClicked.connect(self.on_tab_clicked)

        self.home_page = HomePage()
        self.home_page.group_chosen.connect(self.open_group)

        # The bar above a page opened from the home screen: the page's name on
        # the left, the big Home button in the middle. (The "Basic mode"
        # switch is at the top right of the window, in the menu bar.)
        from widgets.home_hint import HomeButton
        self.btn_home = HomeButton()
        self.btn_home.clicked.connect(self.go_home)
        self.lbl_group = QLabel()
        self.lbl_group.setStyleSheet("QLabel { font-size: 12pt; font-weight: bold; }")
        group_header = QGridLayout()
        group_header.setContentsMargins(10, 4, 10, 2)
        group_header.addWidget(self.lbl_group, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        group_header.addWidget(self.btn_home, 0, 1, Qt.AlignCenter)
        group_header.setColumnStretch(0, 1)
        group_header.setColumnStretch(2, 1)
        # on a page opened from the home screen the "Basic mode" switch is here,
        # at the right of the bar, inside the page's panel (elsewhere it is at the
        # top right of the window)
        from widgets.mode_switch import make_mode_switch
        self.page_mode_switch = make_mode_switch()
        # and an X at the far right, which also goes back to the home screen
        from widgets.home_hint import CloseButton
        self.btn_close_page = CloseButton()
        self.btn_close_page.clicked.connect(self.go_home)
        right_side = QHBoxLayout()
        right_side.setContentsMargins(0, 0, 0, 0)
        right_side.setSpacing(18)
        right_side.addWidget(self.page_mode_switch)
        right_side.addWidget(self.btn_close_page)
        group_header.addLayout(right_side, 0, 2, Qt.AlignRight | Qt.AlignVCenter)
        self.top_bar = QWidget()
        self.top_bar.setLayout(group_header)
        self.top_bar.hide()
        self._home_hint = None

        # The page that holds the tabs. In Basic mode it is one rounded panel
        # with the bar (the page's name and the Home button) inside, at the top.
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(0)
        group_layout.addWidget(self.top_bar)
        group_layout.addWidget(self.tabs, 1)
        self.group_layout = group_layout
        self.group_page = QFrame()
        self.group_page.setLayout(group_layout)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.home_page)
        self.pages.addWidget(self.group_page)
        self.refresh_tabs()

        no_devices = 'No keyboard detected. Connect a MIDIswitch: it is found on its own.'
        if sys.platform != "emscripten":
            no_devices += '<br><br>If it is connected and still not found, unplug it and plug it ' \
                          'back in, or choose File &gt; Look for keyboards again.'
        if sys.platform.startswith("linux"):
            no_devices += '<br><br>On Linux you need a udev rule that grants access to the device ' \
                          '(idVendor b1d7, idProduct 4012) before it can be detected.'
        self.lbl_no_devices = QLabel(tr("MainWindow", no_devices))
        self.lbl_no_devices.setTextFormat(Qt.RichText)
        self.lbl_no_devices.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        # The device picker + Refresh toolbar is not shown: the app connects
        # to the keyboard on its own. The (hidden) combobox is still the model
        # autorefresh selects devices through.

        # Allow tabs to shrink much more
        self.tabs.setMinimumHeight(150)  # Tabs can compress to 150px
        layout.addWidget(self.pages, 1)


        layout.addWidget(self.lbl_no_devices)
        layout.setAlignment(self.lbl_no_devices, Qt.AlignHCenter)
        self.tray_keycodes = TabbedKeycodes()
        self.tray_keycodes.make_tray()
        self.tray_keycodes.setFixedHeight(450)  # Fixed height for tray
        layout.addWidget(self.tray_keycodes, 0)
        self.tray_keycodes.hide()

        # Connect editors to tray_keycodes for dynamic keycode counts
        self.tray_keycodes.set_editors(
            macro_recorder=self.macro_recorder,
            tap_dance_editor=self.tap_dance,
            dks_settings=self.dks_settings,
            toggle_settings=self.toggle_settings,
            delay_settings=self.delay_tab
        )

        # Prevent the layout from resizing the window
        layout.setSizeConstraint(QVBoxLayout.SetNoConstraint)

        w = QWidget()
        w.setLayout(layout)
        self.setCentralWidget(w)

        self.init_menu()

        # The "Basic mode" switch: top right of the window, in both modes
        from widgets.mode_switch import make_mode_switch
        self.mode_switch = make_mode_switch()
        switch_holder = QWidget()
        switch_layout = QHBoxLayout(switch_holder)
        switch_layout.setContentsMargins(8, 1, 10, 1)
        switch_layout.addWidget(self.mode_switch)
        self.menuBar().setCornerWidget(switch_holder, Qt.TopRightCorner)
        self.mode_switch_holder = switch_holder
        # (not while a Basic-mode page is showing: its panel has the switch)
        switch_holder.setVisible(not self.group_page.property("pagePanel"))

        _startup_log("Initializing autorefresh (device scanning)...")
        t0 = time.time()
        self.autorefresh = Autorefresh()
        self.autorefresh.devices_updated.connect(self.on_devices_updated)
        _startup_log(f"  Autorefresh initialized ({time.time()-t0:.2f}s)")

        # cache for via definition files
        self.cache_path = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
        if not os.path.exists(self.cache_path):
            os.makedirs(self.cache_path)

        # check if the via defitions already exist
        if os.path.isfile(os.path.join(self.cache_path, "via_keyboards.json")):
            _startup_log("Loading cached keyboard definitions...")
            t0 = time.time()
            with open(os.path.join(self.cache_path, "via_keyboards.json")) as vf:
                data = vf.read()
            try:
                self.autorefresh.load_via_stack(data)
                _startup_log(f"  Keyboard definitions loaded ({time.time()-t0:.2f}s)")
            except JSONDecodeError as e:
                # the saved file is invalid - just ignore this
                logging.warning("Failed to parse stored via_keyboards.json: {}".format(e))
                _startup_log(f"  Keyboard definitions failed to parse")

        # make sure initial state is valid
        _startup_log("Starting initial device refresh...")
        t0 = time.time()
        self.on_click_refresh()
        _startup_log(f"Initial device refresh complete ({time.time()-t0:.2f}s)")

        # webmain's demo mode loads a virtual keyboard after this and says
        # "ready" itself once that has finished.
        if sys.platform == "emscripten" and not getattr(appctx, "defer_ready", False):
            import vialglue
            QTimer.singleShot(100, vialglue.notify_ready)

    def init_menu(self):
        layout_load_act = QAction(tr("MenuFile", "Load saved layout..."), self)
        layout_load_act.setShortcut("Ctrl+O")
        layout_load_act.triggered.connect(self.on_layout_load)

        layout_save_act = QAction(tr("MenuFile", "Save current layout..."), self)
        layout_save_act.setShortcut("Ctrl+S")
        layout_save_act.triggered.connect(self.on_layout_save)

        clone_load_act = QAction(tr("MenuFile", "Load keyboard clone..."), self)
        clone_load_act.triggered.connect(self.on_clone_load)

        clone_save_act = QAction(tr("MenuFile", "Save keyboard clone..."), self)
        clone_save_act.triggered.connect(self.on_clone_save)

        # The app finds the keyboard on its own; this is for when it did not
        # (the keyboard was busy, or in use by another program, when it tried).
        rescan_act = QAction(tr("MenuFile", "Look for keyboards again"), self)
        rescan_act.triggered.connect(self.on_click_refresh)

        # Not while a firmware update or a clone transfer is running (lock_ui)
        self.lockable_actions = [layout_load_act, layout_save_act, clone_load_act, clone_save_act,
                                 rescan_act]

        exit_act = QAction(tr("MenuFile", "Exit"), self)
        exit_act.setShortcut("Ctrl+Q")
        exit_act.triggered.connect(self.close)

        if sys.platform != "emscripten":
            file_menu = self.menuBar().addMenu(tr("Menu", "File"))
            file_menu.addAction(layout_load_act)
            file_menu.addAction(layout_save_act)
            file_menu.addSeparator()
            file_menu.addAction(clone_load_act)
            file_menu.addAction(clone_save_act)
            file_menu.addSeparator()
            file_menu.addAction(rescan_act)
            from widgets.debug_windows import DebugWindows
            self.show_debug_act = QAction(tr("MenuFile", "Show debug windows"), self)
            self.show_debug_act.setCheckable(True)
            self.show_debug_act.setChecked(DebugWindows.visible())
            self.show_debug_act.toggled.connect(DebugWindows.set_visible)
            file_menu.addAction(self.show_debug_act)

        if sys.platform != "emscripten":
            self.theme_menu = self.menuBar().addMenu(tr("Menu", "Theme"))
            theme_group = QActionGroup(self)
            selected_theme = self.get_theme()
            for name, _ in themes.themes:
                act = QAction(tr("MenuTheme", name), self)
                act.triggered.connect(lambda x,name=name: self.set_theme(name))
                act.setCheckable(True)
                act.setChecked(selected_theme == name)
                theme_group.addAction(act)
                self.theme_menu.addAction(act)
            # check the default theme if nothing else is selected
            if theme_group.checkedAction() is None:
                theme_group.actions()[0].setChecked(True)

        help_menu = self.menuBar().addMenu(tr("Menu", "Help"))
        about_act = QAction(tr("MenuHelp", "About MIDIswitch KeyStation..."), self)
        about_act.triggered.connect(self.show_about)
        help_menu.addAction(about_act)

    def show_about(self):
        from widgets.about_dialog import AboutDialog
        dlg = AboutDialog(self, self.appctx)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()

    def on_layout_load(self):
        if self.ui_lock_count > 0:
            return      # a firmware update or clone transfer is running
        # Guard: a layout can only be applied to a connected keyboard.
        if not isinstance(self.autorefresh.current_device, VialKeyboard):
            QMessageBox.warning(self, "No keyboard",
                                tr("MainWindow", "Connect a keyboard before loading a layout."))
            return

        dialog = QFileDialog()
        dialog.setDefaultSuffix("vil")
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setNameFilters(["SwitchStation layout (*.vil)"])
        if dialog.exec_() == QDialog.Accepted:
            try:
                with open(dialog.selectedFiles()[0], "rb") as inf:
                    data = inf.read()
                self.keymap_editor.restore_layout(data)
                self.rebuild()
            except Exception as e:
                # Malformed/hand-edited/wrong-version .vil: report instead of
                # crashing (JSON decode error, missing keys, bad keycodes).
                logging.exception("Failed to load layout")
                QMessageBox.critical(self, "Load failed",
                                     tr("MainWindow", "Could not load this layout file:\n{}").format(e))

    def on_layout_save(self):
        # Guard: there is only a layout to save with a keyboard connected (not
        # with none, and not with one that is in update mode). Without this the
        # chosen file was emptied before the save failed.
        if self.ui_lock_count > 0:
            return
        if not isinstance(self.autorefresh.current_device, VialKeyboard):
            QMessageBox.warning(self, "No keyboard",
                                tr("MainWindow", "Connect a keyboard before saving its layout."))
            return

        dialog = QFileDialog()
        dialog.setDefaultSuffix("vil")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setNameFilters(["SwitchStation layout (*.vil)"])
        if dialog.exec_() == QDialog.Accepted:
            try:
                # the keyboard may have gone while the file dialog was open
                if not isinstance(self.autorefresh.current_device, VialKeyboard):
                    raise RuntimeError(tr("MainWindow", "the keyboard is no longer connected"))
                # everything to write is ready before the file is touched, so a
                # failure never leaves an existing file emptied
                data = self.keymap_editor.save_layout()
                with open(dialog.selectedFiles()[0], "wb") as outf:
                    outf.write(data)
            except Exception as e:
                logging.exception("Failed to save layout")
                QMessageBox.critical(self, "Save failed",
                                     tr("MainWindow", "Could not save the layout:\n{}").format(e))

    # ------------------------------------------------------------------
    # Keyboard clone: save / restore the keyboard's complete settings image.
    # The image carries a layout version; an older image is converted with
    # protocol/clone_migrations.py, a newer one is refused.
    # ------------------------------------------------------------------

    CLONE_FILE_MAGIC = "midiswitch-keyboard-clone"

    def _clone_get_keyboard_or_warn(self):
        """Return (keyboard, clone_info) for a connected clone-capable
        keyboard, or (None, None) after showing the appropriate warning."""
        if self.ui_lock_count > 0:
            return None, None       # a firmware update or clone transfer is running
        if not isinstance(self.autorefresh.current_device, VialKeyboard):
            QMessageBox.warning(self, "No keyboard",
                                tr("MainWindow", "Connect a keyboard before using keyboard clones."))
            return None, None
        keyboard = self.autorefresh.current_device.keyboard
        info = keyboard.get_clone_info()
        if not info:
            QMessageBox.warning(self, "Not supported",
                                tr("MainWindow", "The connected keyboard's firmware does not support "
                                                 "keyboard clones. Update the firmware and try again."))
            return None, None
        return keyboard, info

    def on_clone_save(self):
        keyboard, info = self._clone_get_keyboard_or_warn()
        if keyboard is None:
            return

        dialog = QFileDialog()
        dialog.setDefaultSuffix("kbclone")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setNameFilters(["Keyboard clone (*.kbclone)"])
        if dialog.exec_() != QDialog.Accepted:
            return
        path = dialog.selectedFiles()[0]

        from PyQt5.QtWidgets import QApplication, QProgressDialog
        from util import set_hid_transfer_active

        size = info["eeprom_size"]
        chunk_size = info["chunk_size"]
        blob = bytearray()

        progress = QProgressDialog(tr("MainWindow", "Reading keyboard memory..."),
                                   tr("MainWindow", "Cancel"), 0, size, self)
        progress.setWindowTitle(tr("MainWindow", "Save Keyboard Clone"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        # The live pollers (matrix/velocity) share the HID handle; make them
        # stand down for the duration of the bulk transfer.
        #
        # The chunk loop runs on a BACKGROUND thread (HID access is serialized
        # by hid_lock_for) while the GUI thread only pumps events and updates
        # the progress bar. Running the transfer synchronously on the GUI
        # thread froze the whole app for its duration — each chunk's HID read
        # can block up to 500 ms × retries — and a frozen app stops draining
        # the keyboard's USB endpoints while it is trying to send
        # mid-transfer.
        import threading
        import time
        state = {"addr": 0, "done": False, "canceled": False, "failed_addr": None}

        def read_worker():
            try:
                addr = 0
                while addr < size:
                    if state["canceled"]:
                        return
                    length = min(chunk_size, size - addr)
                    data = None
                    for _ in range(3):  # per-chunk retry on top of the HID-level retries
                        data = keyboard.clone_read_chunk(addr, length)
                        if data is not None:
                            break
                    if data is None:
                        state["failed_addr"] = addr
                        return
                    blob.extend(data)
                    addr += length
                    state["addr"] = addr
            except Exception:
                logging.exception("Clone read worker failed")
                state["failed_addr"] = state["addr"]
            finally:
                state["done"] = True

        set_hid_transfer_active(True)
        # Ignore device add/remove events until the transfer is over: a refresh
        # would close the HID handle while the worker thread is reading it.
        self.lock_ui()
        self._clone_transfer_running = True     # the window cannot be closed meanwhile
        try:
            worker = threading.Thread(target=read_worker, daemon=True)
            worker.start()
            while not state["done"]:
                if progress.wasCanceled():
                    state["canceled"] = True
                progress.setValue(state["addr"])
                QApplication.processEvents()
                time.sleep(0.01)
            worker.join()
        finally:
            self._clone_transfer_running = False
            set_hid_transfer_active(False)
            self.unlock_ui()
            progress.close()

        if state["canceled"]:
            return  # nothing was written to the device or to disk
        if state["failed_addr"] is not None:
            QMessageBox.critical(self, "Save failed",
                                 tr("MainWindow", "Failed to read keyboard memory at address {}.\n"
                                                  "No file was written.").format(state["failed_addr"]))
            return

        clone = {
            "magic": self.CLONE_FILE_MAGIC,
            "file_version": 1,
            "eeprom_layout_version": info["layout_version"],
            "eeprom_size": size,
            "firmware_version": list(info["fw_version"]),
            "data": base64.b64encode(bytes(blob)).decode("ascii"),
        }
        try:
            with open(path, "w", encoding="utf-8") as outf:
                json.dump(clone, outf)
        except OSError as e:
            logging.exception("Failed to write keyboard clone")
            QMessageBox.critical(self, "Save failed",
                                 tr("MainWindow", "Could not write the clone file:\n{}").format(e))
            return

        QMessageBox.information(self, "Clone saved",
                                tr("MainWindow", "Keyboard clone saved successfully."))

    def on_clone_load(self):
        keyboard, info = self._clone_get_keyboard_or_warn()
        if keyboard is None:
            return

        dialog = QFileDialog()
        dialog.setDefaultSuffix("kbclone")
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setNameFilters(["Keyboard clone (*.kbclone)"])
        if dialog.exec_() != QDialog.Accepted:
            return

        try:
            with open(dialog.selectedFiles()[0], "r", encoding="utf-8") as inf:
                clone = json.load(inf)
            if clone.get("magic") != self.CLONE_FILE_MAGIC:
                raise ValueError("not a keyboard clone file")
            blob = base64.b64decode(clone["data"])
            file_layout = int(clone["eeprom_layout_version"])
            if len(blob) != int(clone["eeprom_size"]):
                raise ValueError("clone data size does not match its header")
        except Exception as e:
            logging.exception("Failed to parse keyboard clone")
            QMessageBox.critical(self, "Load failed",
                                 tr("MainWindow", "Could not load this keyboard clone file:\n{}").format(e))
            return

        # Layout compatibility gate. A clone saved under a different settings
        # layout can't be written as-is — it would
        # scatter old data over the new layout. An OLDER clone is converted
        # forward (see protocol/clone_migrations.py); anything we have no
        # conversion path for is still refused.
        device_layout = info["layout_version"]
        if len(blob) != info["eeprom_size"]:
            QMessageBox.critical(
                self, "Incompatible clone",
                tr("MainWindow", "This clone holds {} bytes of keyboard memory but this keyboard "
                                 "has {}, so it cannot be restored.").format(
                                     len(blob), info["eeprom_size"]))
            return

        if file_layout != device_layout:
            if not can_migrate(file_layout, device_layout):
                # Newer-than-firmware clone, or a version gap we have no
                # migration for. Never guess — a wrong guess corrupts settings.
                if file_layout > device_layout:
                    detail = tr("MainWindow", "The clone is NEWER than the keyboard's firmware. "
                                              "Update the keyboard's firmware and try again.")
                else:
                    # The clone is OLDER but a migration link is missing.
                    # Migrations ship with the app, so nine times out of ten
                    # the fix is simply a newer app build — say so instead of
                    # presenting a dead end.
                    detail = tr("MainWindow", "This version of the app has no conversion path "
                                              "between those two layouts.\n\n"
                                              "Newer versions of this app add conversions for "
                                              "newer firmware — update the app and try again.")
                QMessageBox.critical(
                    self, "Incompatible clone",
                    tr("MainWindow", "This clone was saved from a firmware with a different EEPROM "
                                     "layout (clone layout v{}, keyboard layout v{}), so restoring "
                                     "it could corrupt the keyboard's settings.\n\n{}").format(
                                         file_layout, device_layout, detail))
                return

            try:
                blob, notes = migrate_clone(blob, file_layout, device_layout)
            except CloneMigrationError as e:
                logging.exception("Clone migration failed")
                QMessageBox.critical(
                    self, "Incompatible clone",
                    tr("MainWindow", "This clone could not be converted to the keyboard's EEPROM "
                                     "layout:\n{}").format(e))
                return

            summary = "\n".join("  • " + n for n in notes)
            ret = QMessageBox.question(
                self, "Convert older clone",
                tr("MainWindow", "This clone was saved from an older firmware (EEPROM layout v{}; "
                                 "this keyboard uses v{}).\n\n"
                                 "It can be converted automatically. What that means for your "
                                 "settings:\n\n{}\n\n"
                                 "Everything else is carried across unchanged. The clone file "
                                 "itself is not modified.\n\n"
                                 "Convert and restore?").format(file_layout, device_layout, summary),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if ret != QMessageBox.Yes:
                return

        ret = QMessageBox.warning(
            self, "Load keyboard clone",
            tr("MainWindow", "This will overwrite ALL settings stored on the keyboard — layout, "
                             "MIDI settings, ThruLoop settings, per-key actuations, presets, "
                             "names, everything — with the contents of the clone file.\n\n"
                             "Do not disconnect the keyboard while the restore is running. "
                             "The keyboard will reboot when it finishes.\n\nContinue?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return

        from PyQt5.QtWidgets import QApplication, QProgressDialog
        from util import set_hid_transfer_active

        size = info["eeprom_size"]
        chunk_size = info["chunk_size"]

        progress = QProgressDialog(tr("MainWindow", "Writing keyboard memory..."),
                                   tr("MainWindow", "Cancel"), 0, size, self)
        progress.setWindowTitle(tr("MainWindow", "Load Keyboard Clone"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        # Chunk loop on a background thread, GUI thread pumps — same rationale
        # as the save path (a synchronous transfer froze the app, and a frozen
        # app used to wedge the keyboard when keys were pressed mid-transfer).
        import threading
        import time
        state = {"addr": 0, "done": False, "canceled": False, "failed_addr": None}

        def write_worker():
            try:
                addr = 0
                while addr < size:
                    if state["canceled"]:
                        return
                    length = min(chunk_size, size - addr)
                    written = False
                    for _ in range(3):  # per-chunk retry on top of the HID-level retries
                        if keyboard.clone_write_chunk(addr, blob[addr:addr + length]):
                            written = True
                            break
                    if not written:
                        state["failed_addr"] = addr
                        return
                    addr += length
                    state["addr"] = addr
            except Exception:
                logging.exception("Clone write worker failed")
                state["failed_addr"] = state["addr"]
            finally:
                state["done"] = True

        set_hid_transfer_active(True)
        # Ignore device add/remove events until the transfer is over: a refresh
        # would close the HID handle while the worker thread is reading it.
        self.lock_ui()
        self._clone_transfer_running = True     # the window cannot be closed meanwhile
        try:
            worker = threading.Thread(target=write_worker, daemon=True)
            worker.start()
            while not state["done"]:
                if progress.wasCanceled():
                    state["canceled"] = True
                progress.setValue(state["addr"])
                QApplication.processEvents()
                time.sleep(0.01)
            worker.join()
        finally:
            self._clone_transfer_running = False
            set_hid_transfer_active(False)
            self.unlock_ui()
            progress.close()

        canceled = state["canceled"]
        failed_addr = state["failed_addr"]
        ok = failed_addr is None

        if canceled or not ok:
            # A partial restore leaves the EEPROM as a mix of old and new data.
            # The device was NOT rebooted (no finalize), so it is still running
            # on its old RAM state — loading the clone again (or a fresh one)
            # fully recovers it.
            detail = tr("MainWindow", "The restore was cancelled.") if canceled else \
                tr("MainWindow", "Writing failed at address {}.").format(failed_addr)
            QMessageBox.warning(
                self, "Restore incomplete",
                detail + tr("MainWindow", "\n\nThe keyboard's stored settings are now a mix of old "
                                          "and new data. Load a clone again to complete the restore "
                                          "before power-cycling the keyboard."))
            return

        try:
            finalized = bool(keyboard.clone_finalize())
        except Exception:
            logging.exception("Clone finalize failed")
            finalized = False
        if not finalized:
            # Everything was written, but the keyboard did not confirm the
            # step that makes it restart and take the restored settings up.
            QMessageBox.warning(
                self, "Restore not confirmed",
                tr("MainWindow", "The clone was written to the keyboard, but the keyboard did not "
                                 "confirm it, so it may not have restarted with the restored "
                                 "settings.\n\n"
                                 "Unplug the keyboard and plug it back in, then check your settings. "
                                 "If they are not the clone's, load the clone again."))
            QTimer.singleShot(4000, lambda: self.autorefresh.update(quiet=True, hard=True))
            return
        QMessageBox.information(
            self, "Clone loaded",
            tr("MainWindow", "Keyboard clone restored successfully.\n\n"
                             "The keyboard is rebooting to apply the restored settings; "
                             "it will reconnect automatically in a few seconds."))
        # Pick the device back up once it has re-enumerated.
        QTimer.singleShot(4000, lambda: self.autorefresh.update(quiet=True, hard=True))

    def on_click_refresh(self):
        self.autorefresh.update(quiet=False, hard=True)

    def _device_change_must_wait(self):
        from widgets.loading_overlay import putting_up
        return self._selecting_device or putting_up()

    def _handle_waiting_devices(self):
        if self._waiting_devices is None:
            return
        if self._device_change_must_wait():
            QTimer.singleShot(50, self._handle_waiting_devices)
            return
        devices, hard_refresh = self._waiting_devices
        self._waiting_devices = None
        self.on_devices_updated(devices, hard_refresh)

    def on_devices_updated(self, devices, hard_refresh):
        # Connecting to a keyboard lets waiting events run here and there (the
        # startup log, a Loading cover going up in the middle of a click on a
        # tab). A second device change that arrives through one of those must
        # not start inside the first, or rebuild the tabs under the click: it
        # waits and is handled right after. The device list has changed under
        # whatever was running, so what waits is always handled in full.
        if self._device_change_must_wait():
            self._waiting_devices = (devices, True)
            QTimer.singleShot(0, self._handle_waiting_devices)
            return

        self.combobox_devices.blockSignals(True)

        self.combobox_devices.clear()
        for dev in devices:
            self.combobox_devices.addItem(dev.title())
            if self.autorefresh.current_device and dev.desc["path"] == self.autorefresh.current_device.desc["path"]:
                self.combobox_devices.setCurrentIndex(self.combobox_devices.count() - 1)

        self.combobox_devices.blockSignals(False)

        if devices:
            self.lbl_no_devices.hide()
            self.pages.show()
            self.top_bar.setVisible(ui_mode.is_basic() and self.current_group is not None)
        else:
            self.lbl_no_devices.show()
            self.pages.hide()
            self.top_bar.hide()

        if hard_refresh:
            self.on_device_selected()

    def on_device_selected(self):
        if self._selecting_device:
            return      # already connecting; a change that arrived meanwhile is waiting its turn
        self._selecting_device = True
        try:
            self._select_device()
        finally:
            self._selecting_device = False

    def _select_device(self):
        _startup_log("on_device_selected() called...")
        t0 = time.time()
        try:
            index = self.combobox_devices.currentIndex()
            if index >= len(self.autorefresh.devices):
                # the device list changed while this was starting (the log line
                # above can let events run); that change is waiting its turn
                # (on_devices_updated) and selects again with the new list
                index = -1
            self.autorefresh.select_device(index)
            _startup_log(f"  autorefresh.select_device() done ({time.time()-t0:.2f}s)")
        except ProtocolError:
            QMessageBox.warning(self, "", "Unsupported protocol version!\n"
                                          "Please update SwitchStation to the latest version.")
        except Exception as e:
            # Opening the HID device can fail if it's claimed by another
            # process or was unplugged between enumeration and selection.
            # Reset to "no device" and report, instead of leaving a stale UI
            # pointed at a half-open device.
            logging.exception("Failed to open selected device")
            try:
                self.autorefresh.select_device(-1)
            except Exception:
                pass
            QMessageBox.warning(self, "", tr("MainWindow",
                                "Could not open the selected keyboard. It may be in use by "
                                "another application or was disconnected.\n\n{}\n\n"
                                "Close the other application, or unplug the keyboard and plug it "
                                "back in, then choose File > Look for keyboards again.").format(e))

        if isinstance(self.autorefresh.current_device, VialKeyboard) \
                and not isinstance(self.autorefresh.current_device, VialDummyKeyboard):
            keyboard_id = self.autorefresh.current_device.keyboard.keyboard_id
            if (keyboard_id in EXAMPLE_KEYBOARDS) or ((keyboard_id & 0xFFFFFFFFFFFFFF) == EXAMPLE_KEYBOARD_PREFIX):
                QMessageBox.warning(self, "", "An example keyboard UID was detected.\n"
                                              "Please change your keyboard UID to be unique before you ship!")
            # Initialize feature name manager for this keyboard. Individual
            # renames are pushed to the firmware at edit time (set_name ->
            # _hid_set_name); bulk-pushing the local JSON cache here would
            # clobber names renamed on-device and burn EEPROM write cycles
            # on every device select.
            mgr = get_feature_name_manager()
            mgr.set_keyboard(keyboard_id, self.autorefresh.current_device.keyboard)

            # Confirm this is our keyboard via its model ID (the product
            # string was already matched at enumeration). If it matches, run the
            # startup firmware-version check.
            if keyboard_id != MIDISWITCH_KEYBOARD_UID:
                QMessageBox.warning(self, "", "This does not appear to be a MIDIswitch keyboard.\n"
                                              "Some features may not work correctly.")
            elif not isinstance(self.autorefresh.current_device, VialVirtualKeyboard):
                self._check_firmware_update(self.autorefresh.current_device.keyboard)

        t0 = time.time()
        self.rebuild()
        _startup_log(f"  rebuild() total: {time.time()-t0:.2f}s")

        t0 = time.time()
        self.refresh_tabs()
        _startup_log(f"  refresh_tabs(): {time.time()-t0:.2f}s")
        _startup_log("on_device_selected() complete")

    def _check_firmware_update(self, keyboard):
        """Compare the keyboard's firmware version against the version bundled
        with this GUI and prompt once if an update is available. Detection only —
        this does not flash anything. Silent if the version can't be read (e.g.
        firmware predating the query) to avoid false alarms."""
        try:
            version = keyboard.get_firmware_version()
        except Exception:
            version = None
        if not version:
            return
        if tuple(version) >= tuple(LATEST_FIRMWARE_VERSION):
            return
        # Only prompt once per keyboard UID per session
        if not hasattr(self, "_fw_update_prompted"):
            self._fw_update_prompted = set()
        uid = getattr(keyboard, "keyboard_id", None)
        if uid in self._fw_update_prompted:
            return
        self._fw_update_prompted.add(uid)
        cur = ".".join(str(v) for v in version)
        latest = ".".join(str(v) for v in LATEST_FIRMWARE_VERSION)
        QMessageBox.information(
            self, "Firmware update available",
            "Your MIDIswitch is running firmware {}.\n"
            "The latest version is {}.\n\n"
            "A firmware update is available — download it from the MIDIswitch releases page "
            "and install it from Firmware on the home screen.".format(cur, latest))

    def rebuild(self):
        _startup_log("MainWindow.rebuild() starting...")
        rebuild_start = time.time()

        # if unlock process was interrupted, we must finish it first
        if isinstance(self.autorefresh.current_device, VialKeyboard) and self.autorefresh.current_device.keyboard.get_unlock_in_progress():
            Unlocker.unlock(self.autorefresh.current_device.keyboard)
            self.autorefresh.current_device.keyboard.reload()

        # Updated to include the new configurators in the rebuild process
        editors_to_rebuild = [
            (self.layout_editor, "layout_editor"),
            (self.keymap_editor, "keymap_editor"),
            (self.trigger_settings, "trigger_settings"),
            (self.dks_settings, "dks_settings"),
            (self.toggle_settings, "toggle_settings"),
            (self.firmware_flasher, "firmware_flasher"),
            (self.macro_recorder, "macro_recorder"),
            (self.tap_dance, "tap_dance"),
            (self.combo_keys, "combo_keys"),
            (self.matrix_tester, "matrix_tester"),
            (self.rgb_configurator, "rgb_configurator"),
            (self.MIDIswitchSettingsConfigurator, "MIDIswitchSettingsConfigurator"),
            (self.gaming_configurator, "gaming_configurator"),
            (self.midi_patchbay, "midi_patchbay"),
            (self.loop_manager, "loop_manager"),
            (self.arpeggiator, "arpeggiator"),
            (self.step_sequencer, "step_sequencer"),
            (self.delay_tab, "delay_tab"),
            (self.quickbuild, "quickbuild"),
            (self.advanced_keys, "advanced_keys"),      # after the editors it holds
            (self.velocity_tab, "velocity_tab"),
        ]

        for editor, name in editors_to_rebuild:
            t0 = time.time()
            editor.rebuild(self.autorefresh.current_device)
            elapsed = time.time() - t0
            if elapsed > 0.1:  # Only log if it took more than 100ms
                _startup_log(f"  rebuild {name}: {elapsed:.2f}s")

        _startup_log(f"  All editors rebuilt ({time.time()-rebuild_start:.2f}s)")

        # Set all editor references on all tabbed_keycodes instances
        t0 = time.time()
        self._update_all_tabbed_keycodes()
        _startup_log(f"  _update_all_tabbed_keycodes ({time.time()-t0:.2f}s)")

        # Refresh keycode buttons in tray to reflect updated content counts from editors
        self.tray_keycodes.recreate_keycode_buttons()

    def _update_all_tabbed_keycodes(self):
        """Set all editor references on all tabbed_keycodes instances for consistent keycode counts"""
        editors_with_tabbed_keycodes = [
            self.keymap_editor,
            self.macro_recorder,
            self.tap_dance,
            self.combo_keys,
            self.dks_settings,
            self.toggle_settings,
            self.matrix_tester,
        ]

        for editor in editors_with_tabbed_keycodes:
            if hasattr(editor, 'tabbed_keycodes'):
                editor.tabbed_keycodes.set_keyboard(self.autorefresh.current_device.keyboard if isinstance(self.autorefresh.current_device, VialKeyboard) else None)
                editor.tabbed_keycodes.set_editors(
                    macro_recorder=self.macro_recorder,
                    tap_dance_editor=self.tap_dance,
                    dks_settings=self.dks_settings,
                    toggle_settings=self.toggle_settings,
                    delay_settings=self.delay_tab
                )

        # Also update the tray keycodes
        if isinstance(self.autorefresh.current_device, VialKeyboard):
            self.tray_keycodes.set_keyboard(self.autorefresh.current_device.keyboard)

    def refresh_tabs(self, remember_tab=True):
        """Show the tabs this keyboard and mode have. `remember_tab`: come
        back to the tab that is showing now (False when the user is going
        somewhere else: a home tile, the Home button)."""
        # Disable UI updates during tab refresh to speed up the process
        self.tabs.setUpdatesEnabled(False)
        # Taking the tabs out and putting them back would report a change of
        # tab for each one, activating and deactivating every editor in turn
        # (Calibration grabbing the keyboard for an instant, Actuation asking
        # about unsaved changes...) and leave the first tab showing. So the
        # tab widget is kept quiet meanwhile, the tab that was showing is
        # brought back if it is still there, and the change is reported once
        # at the end: one deactivate for the editor that was showing, one
        # activate for the one that is now (the same one after a rebuild, so
        # that it starts again on the new keyboard).
        showing = self.tabs.currentWidget()
        if showing is not None and remember_tab:
            self._editor_to_restore = showing.editor
        self.tabs.blockSignals(True)
        try:
            # QTabWidget.clear() reparents the pages to None without deleting
            # them, so the cached EditorContainers survive and can be re-added.
            self.tabs.clear()

            def shown(editor):
                return editor.valid()

            # The home screen offers a bubble for every tab that has something to show
            tiles = []
            for name, description, members in self.groups:
                if any(shown(editor) for editor in members):
                    tiles.append((name, tr("HomePage", description) if description else ""))
            self.home_page.set_tiles(tiles)
            names = [name for name, _ in tiles]
            if self.current_group not in names:
                if not names and self.current_group is not None:
                    # the keyboard has gone (it restarts after a clone or an
                    # update): come back to this page when it returns
                    self._group_to_restore = self.current_group
                # Only one thing to do (a keyboard waiting for firmware): go straight to it
                self.current_group = names[0] if len(names) == 1 else None
                if self.current_group is None and self._group_to_restore in names \
                        and ui_mode.is_basic():
                    self.current_group = self._group_to_restore
            if names:
                self._group_to_restore = None
            if ui_mode.is_basic():
                members = next((m for name, _, m in self.groups if name == self.current_group), [])
            else:
                # Advanced mode: every editor, as one row of tabs
                members = [editor for editor, _ in self.editors]

            labels = dict(self.editors)
            for editor in members:      # in the group's own order
                lbl = labels[editor]
                if not shown(editor):
                    continue

                # Wrap each editor once and reuse the wrapper: constructing a
                # new EditorContainer per refresh re-set the editor layout on a
                # new widget and re-polished the entire widget tree every time,
                # while leaking the previous containers.
                c = self.editor_containers.get(editor)
                if c is None:
                    c = EditorContainer(editor)
                    self.editor_containers[editor] = c
                self.tabs.addTab(c, tr("MainWindow", lbl))

            # back to the tab that was showing (also across the moment a
            # restarting keyboard is gone, when there are no tabs at all)
            wanted = self.editor_containers.get(self._editor_to_restore)
            if wanted is not None and self.tabs.indexOf(wanted) >= 0:
                self.tabs.setCurrentWidget(wanted)
            if self.tabs.count():
                self._editor_to_restore = None

            # a group with one page needs no tab to choose it
            self.tabs.tabBar().setVisible(self.tabs.count() > 1)
            in_group = ui_mode.is_basic() and self.current_group is not None
            self.lbl_group.setText(tr("HomePage", self.current_group or "") if in_group else "")
            self.btn_home.setVisible(in_group and len(names) > 1)
            self.btn_close_page.setVisible(in_group and len(names) > 1)
            self.top_bar.setVisible(in_group and not self.pages.isHidden())
            on_home = ui_mode.is_basic() and self.current_group is None
            self.pages.setCurrentWidget(self.home_page if on_home else self.group_page)
            self._set_page_panel(in_group)
        finally:
            self.tabs.blockSignals(False)
            self.tabs.setUpdatesEnabled(True)
        if self.current_tab is not None or self.tabs.currentIndex() >= 0:
            self.on_tab_changed(self.tabs.currentIndex())

    def _set_page_panel(self, on):
        """Basic mode's page look: one rounded panel round the bar and the page
        (the tab frame inside drops its own); Advanced mode: just the tabs."""
        holder = getattr(self, "mode_switch_holder", None)
        if holder is not None:
            holder.setVisible(not on)       # the panel's bar has the switch
        if bool(self.group_page.property("pagePanel")) == on:
            return
        self.group_page.setProperty("pagePanel", on)
        self.tabs.setProperty("inPagePanel", on)
        self.group_layout.setContentsMargins(*((8, 6, 8, 10) if on else (0, 0, 0, 0)))
        for widget in (self.group_page, self.tabs):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def on_tab_clicked(self, index):
        page = self.tabs.widget(index)
        if page is not None and index != self.tabs.currentIndex():
            from widgets.loading_overlay import begin_loading
            # lifted at the end of on_tab_changed, once the page is up
            self._tab_cover = begin_loading(self.tabs, page, top=self.tabs.tabBar().height())

    def open_group(self, name, editor=None):
        """A tile on the home screen was clicked: show that group's page
        (on `editor`'s tab if one is given, else on its first)."""
        from widgets.loading_overlay import begin_loading, end_loading
        cover = begin_loading(self.pages, ("group", name, ui_mode.mode()))
        try:
            self.current_group = name
            self._editor_to_restore = editor
            self.refresh_tabs(remember_tab=False)
        finally:
            end_loading(cover)
        if ui_mode.is_basic() and self.btn_home.isVisible() and editor is None:
            QTimer.singleShot(150, self.show_home_hint_once)

    HOME_HINT_KEY = "home_hint_shown"

    def show_home_hint_once(self):
        """The first time a page is opened from the home screen, point at the
        Home button (everything else blurred): "Press this to go back to the
        main menu". Remembered, so it is shown only once."""
        settings = ui_mode._settings()
        if settings.value(self.HOME_HINT_KEY, False, type=bool):
            return
        if self._home_hint is not None or not self.btn_home.isVisible() or not ui_mode.is_basic():
            return
        from widgets.home_hint import HomeHint
        settings.setValue(self.HOME_HINT_KEY, True)
        self._home_hint = HomeHint(self, self.btn_home,
                                   blur=[self.tabs, self.lbl_group, self.page_mode_switch, self.btn_close_page,
                                         self.menuBar()])
        self._home_hint.closed.connect(self._on_home_hint_closed)

    def _on_home_hint_closed(self):
        self._home_hint = None

    def go_home(self):
        TabbedKeycodes.close_tray()
        self.current_group = None
        self._editor_to_restore = None
        self.refresh_tabs(remember_tab=False)

    def show_editor(self, editor):
        """Open the page that holds `editor` and bring its tab forward.
        Returns False if that editor is not on offer right now."""
        if ui_mode.is_basic():
            for name, _, members in self.groups:
                if editor in members and self.current_group != name:
                    self.open_group(name, editor)
        for i in range(self.tabs.count()):
            if self.tabs.widget(i).editor == editor:
                self.tabs.setCurrentIndex(i)
                return True
        return False

    def on_mode_changed(self):
        """Basic <-> Advanced (the switch at the top): show what that mode
        has, staying on the tab the user was on where it still exists."""
        TabbedKeycodes.close_tray()
        current = self.tabs.currentWidget()
        if ui_mode.is_basic():
            self.current_group = None       # Basic mode starts from its home screen
            current = None
            self._editor_to_restore = None
        # refresh_tabs keeps the tab that is showing where it still exists
        self.refresh_tabs(remember_tab=not ui_mode.is_basic())
        index = self.tabs.indexOf(current) if current is not None else -1
        self.tabs.setCurrentIndex(index if index >= 0 else 0)

    def load_via_stack_json(self):
        from urllib.request import urlopen

        with urlopen("https://github.com/vial-kb/via-keymap-precompiled/raw/main/via_keyboard_stack.json") as resp:
            data = resp.read()
        self.autorefresh.load_via_stack(data)
        # write to cache
        with open(os.path.join(self.cache_path, "via_keyboards.json"), "wb") as cf:
            cf.write(data)

    def on_load_dummy(self):
        dialog = QFileDialog()
        dialog.setDefaultSuffix("json")
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setNameFilters(["Layout JSON (*.json)"])
        if dialog.exec_() == QDialog.Accepted:
            with open(dialog.selectedFiles()[0], "rb") as inf:
                data = inf.read()
            self.autorefresh.load_dummy(data)

    def lock_ui(self):
        self.ui_lock_count += 1
        if self.ui_lock_count == 1:
            self.autorefresh._lock()
            self.pages.setEnabled(False)
            # (the Basic-mode Home button and the Basic mode switch are
            # outside `pages`: either would rebuild the tabs)
            self.top_bar.setEnabled(False)
            self.mode_switch.setEnabled(False)
            self.page_mode_switch.setEnabled(False)
            # File > Load / Save layout and clone, and their shortcuts, must
            # not reach the keyboard in the middle of an update or a transfer
            for action in self.lockable_actions:
                action.setEnabled(False)
            self.combobox_devices.setEnabled(False)
            self.btn_refresh_devices.setEnabled(False)

    def unlock_ui(self):
        if self.ui_lock_count <= 0:
            return      # (an unlock without its lock must not leave the next lock undone)
        self.ui_lock_count -= 1
        if self.ui_lock_count == 0:
            self.autorefresh._unlock()
            self.pages.setEnabled(True)
            self.top_bar.setEnabled(True)
            self.mode_switch.setEnabled(True)
            self.page_mode_switch.setEnabled(True)
            for action in self.lockable_actions:
                action.setEnabled(True)
            self.combobox_devices.setEnabled(True)
            self.btn_refresh_devices.setEnabled(True)

    def reboot_to_bootloader(self):
        if isinstance(self.autorefresh.current_device, VialKeyboard):
            Unlocker.unlock(self.autorefresh.current_device.keyboard)
            self.autorefresh.current_device.keyboard.reset()


    def get_theme(self):
        # The web app (midiswitch.app) opens in Retro Blue to match its
        # blue landing page; the desktop app opens in Retro Peach.
        default = "Retro Blue" if sys.platform == "emscripten" else themes.DEFAULT_THEME
        theme = self.settings.value("theme", default)
        if theme not in [name for name, _ in themes.themes]:
            theme = default
        return theme

    def set_theme(self, theme):
        themes.Theme.set_theme(theme)
        self.settings.setValue("theme", theme)
        msg = QMessageBox()
        msg.setText(tr("MainWindow", "In order to fully apply the theme you should restart the application."))
        msg.exec_()

    def on_tab_changed(self, index):
        TabbedKeycodes.close_tray()
        old_tab = self.current_tab
        new_tab = None
        if index >= 0:
            new_tab = self.tabs.widget(index)

        # current_tab always names the editor that is activated right now, also
        # while this runs (an editor's activate() can let events through, and
        # one of them can change the tab again): no editor is ever deactivated
        # twice or left activated behind.
        try:
            if old_tab is not None:
                self.current_tab = None
                old_tab.editor.deactivate()
            if new_tab is not None and self.current_tab is None \
                    and self.tabs.currentWidget() is new_tab:
                self.current_tab = new_tab
                new_tab.editor.activate()
        finally:
            from widgets.loading_overlay import end_loading
            end_loading(getattr(self, "_tab_cover", None))
            self._tab_cover = None

    def switch_to_trigger_settings(self):
        """Switch to Trigger Settings tab and enable per-key mode"""
        # Find the index of the Trigger Settings tab
        if not self.show_editor(self.trigger_settings):
            return
        for i in range(self.tabs.count()):
            if self.tabs.widget(i).editor == self.trigger_settings:
                # Switch to the tab
                self.tabs.setCurrentIndex(i)

                # Enable per-key mode in Trigger Settings
                self.trigger_settings.syncing = True
                self.trigger_settings.enable_checkbox.setChecked(True)
                self.trigger_settings.syncing = False

                # Trigger the enable changed handler
                self.trigger_settings.on_enable_changed(Qt.Checked)
                break


    def busy_with_keyboard(self):
        """What is running that must not be cut short ("" if nothing)."""
        if self.firmware_flasher.running:
            return tr("MainWindow", "A firmware update is running.")
        if self._clone_transfer_running:
            return tr("MainWindow", "The keyboard's settings are being transferred.")
        return ""

    def closeEvent(self, e):
        # Closing now would stop a firmware update or a settings transfer
        # halfway (they run on threads that end with the app), leaving the
        # keyboard without firmware or with half-written settings.
        busy = self.busy_with_keyboard()
        if busy:
            e.ignore()
            QMessageBox.warning(
                self, tr("MainWindow", "Please wait"),
                busy + " " + tr("MainWindow", "Leave the app open and the keyboard plugged in "
                                              "until it has finished, then close the app."))
            return

        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())

        # Stop the background device-polling thread so it doesn't keep running
        # (and potentially crash on a half-torn-down device) after the window
        # closes.
        try:
            self.autorefresh.stop()
        except Exception:
            logging.exception("Error stopping autorefresh thread on close")

        e.accept()