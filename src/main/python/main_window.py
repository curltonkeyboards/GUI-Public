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
    QFileDialog, QDialog, QTabWidget, QActionGroup, QMessageBox, QLabel

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
from about_keyboard import AboutKeyboard
from autorefresh.autorefresh import Autorefresh
from editor.combos import Combos
from constants import WINDOW_WIDTH, WINDOW_HEIGHT
from widgets.editor_container import EditorContainer
from editor.firmware_flasher import FirmwareFlasher
from editor.key_override import KeyOverride
from protocol.keyboard_comm import ProtocolError
from protocol.clone_migrations import CloneMigrationError, can_migrate, migrate_clone
from editor.keymap_editor import KeymapEditor
from editor.trigger_settings import TriggerSettingsTab
from editor.dks_settings import DKSSettingsTab
from editor.toggle_settings import ToggleSettingsTab
from keymaps import KEYMAPS
from editor.layout_editor import LayoutEditor
from editor.macro_recorder import MacroRecorder
from editor.qmk_settings import QmkSettings
from editor.rgb_configurator import RGBConfigurator
from tabbed_keycodes import TabbedKeycodes
from editor.tap_dance import TapDance
from unlocker import Unlocker
from util import tr, EXAMPLE_KEYBOARDS, KeycodeDisplay, EXAMPLE_KEYBOARD_PREFIX, \
    MIDISWITCH_KEYBOARD_UID, LATEST_FIRMWARE_VERSION
from vial_device import VialKeyboard
from editor.matrix_test import MatrixTest
from editor.matrix_test import MIDIswitchSettingsConfigurator
from editor.matrix_test import GamingConfigurator
from editor.velocity_tab import VelocityTab
from editor.midi_patch import MIDIPatchBay
from editor.loop_manager import LoopManager
from editor.arpeggiator import Arpeggiator, StepSequencer
from editor.delay_tab import DelayTab

import themes


class MainWindow(QMainWindow):

    def __init__(self, appctx):
        super().__init__()
        _startup_log("MainWindow.__init__ starting...")
        init_start = time.time()

        self.appctx = appctx

        self.ui_lock_count = 0

        self.settings = QSettings("Vial", "Vial")
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
        self.combos = Combos()
        self.key_override = KeyOverride()
        QmkSettings.initialize(appctx)
        self.qmk_settings = QmkSettings()
        self.matrix_tester = MatrixTest(self.layout_editor)
        self.velocity_tab = VelocityTab(self.layout_editor)
        self.rgb_configurator = RGBConfigurator()
        _startup_log(f"  Core editors (Firmware, Macro, TapDance, etc) ({time.time()-t0:.2f}s)")

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
        self.editors = [(self.keymap_editor, "Keymap"), (self.trigger_settings, "Trigger Settings"),
                        (self.dks_settings, "DKS Settings"), (self.toggle_settings, "Toggle Keys"),
                        (self.layout_editor, "Layout"), (self.macro_recorder, "Macros"),
                        (self.rgb_configurator, "Lighting"), (self.MIDIswitchSettingsConfigurator, "MIDI Settings"),
                        (self.gaming_configurator, "Gaming Settings"),
                        (self.midi_patchbay, "MIDI Patch"), (self.loop_manager, "Loop Manager"),
                        (self.arpeggiator, "Arpeggiator"), (self.step_sequencer, "Step Sequencer"),
                        (self.delay_tab, "Delay"),
                        (self.tap_dance, "Tap Dance"), (self.combos, "Combos"),
                        (self.key_override, "Key Overrides"), (self.qmk_settings, "QMK Settings"),
                        (self.matrix_tester, "Matrix tester"), (self.velocity_tab, "Articulation"),
                        (self.firmware_flasher, "Firmware updater")]

        Unlocker.global_layout_editor = self.layout_editor
        Unlocker.global_main_window = self

        self.current_tab = None
        # Each editor is wrapped in an EditorContainer exactly once and the
        # wrapper is reused across refresh_tabs() calls (see refresh_tabs).
        self.editor_containers = {}
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.refresh_tabs()

        no_devices = 'No devices detected. Connect a Vial-compatible device and press "Refresh"<br>' \
                     'or select "File" → "Download VIA definitions" in order to enable support for VIA keyboards.'
        if sys.platform.startswith("linux"):
            no_devices += '<br><br>On Linux you need to set up a custom udev rule for keyboards to be detected. ' \
                          'Follow the instructions linked below:<br>' \
                          '<a href="https://get.vial.today/manual/linux-udev.html">https://get.vial.today/manual/linux-udev.html</a>'
        self.lbl_no_devices = QLabel(tr("MainWindow", no_devices))
        self.lbl_no_devices.setTextFormat(Qt.RichText)
        self.lbl_no_devices.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.addLayout(layout_combobox)

        # Allow tabs to shrink much more
        self.tabs.setMinimumHeight(150)  # Tabs can compress to 150px
        layout.addWidget(self.tabs, 1)

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
            _startup_log("Loading cached VIA definitions...")
            t0 = time.time()
            with open(os.path.join(self.cache_path, "via_keyboards.json")) as vf:
                data = vf.read()
            try:
                self.autorefresh.load_via_stack(data)
                _startup_log(f"  VIA definitions loaded ({time.time()-t0:.2f}s)")
            except JSONDecodeError as e:
                # the saved file is invalid - just ignore this
                logging.warning("Failed to parse stored via_keyboards.json: {}".format(e))
                _startup_log(f"  VIA definitions failed to parse")

        # make sure initial state is valid
        _startup_log("Starting initial device refresh...")
        t0 = time.time()
        self.on_click_refresh()
        _startup_log(f"Initial device refresh complete ({time.time()-t0:.2f}s)")

        if sys.platform == "emscripten":
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

        keyboard_unlock_act = QAction(tr("MenuSecurity", "Unlock"), self)
        keyboard_unlock_act.setShortcut("Ctrl+U")
        keyboard_unlock_act.triggered.connect(self.unlock_keyboard)

        keyboard_lock_act = QAction(tr("MenuSecurity", "Lock"), self)
        keyboard_lock_act.setShortcut("Ctrl+L")
        keyboard_lock_act.triggered.connect(self.lock_keyboard)

        keyboard_layout_menu = self.menuBar().addMenu(tr("Menu", "Keyboard layout"))
        keymap_group = QActionGroup(self)
        selected_keymap = self.settings.value("keymap")
        for idx, keymap in enumerate(KEYMAPS):
            act = QAction(tr("KeyboardLayout", keymap[0]), self)
            act.triggered.connect(lambda checked, x=idx: self.change_keyboard_layout(x))
            act.setCheckable(True)
            if selected_keymap == keymap[0]:
                self.change_keyboard_layout(idx)
                act.setChecked(True)
            keymap_group.addAction(act)
            keyboard_layout_menu.addAction(act)
        # check "QWERTY" if nothing else is selected
        if keymap_group.checkedAction() is None:
            keymap_group.actions()[0].setChecked(True)

        self.security_menu = self.menuBar().addMenu(tr("Menu", "Security"))
        self.security_menu.addAction(keyboard_unlock_act)
        self.security_menu.addAction(keyboard_lock_act)

        if sys.platform != "emscripten":
            self.theme_menu = self.menuBar().addMenu(tr("Menu", "Theme"))
            theme_group = QActionGroup(self)
            selected_theme = self.get_theme()
            for name, _ in [("System", None)] + themes.themes:
                act = QAction(tr("MenuTheme", name), self)
                act.triggered.connect(lambda x,name=name: self.set_theme(name))
                act.setCheckable(True)
                act.setChecked(selected_theme == name)
                theme_group.addAction(act)
                self.theme_menu.addAction(act)
            # check "System" if nothing else is selected
            if theme_group.checkedAction() is None:
                theme_group.actions()[0].setChecked(True)

        about_vial_act = QAction(tr("MenuAbout", "About SwitchStation..."), self)
        about_vial_act.triggered.connect(self.about_vial)
        self.about_keyboard_act = QAction("", self)
        self.about_keyboard_act.triggered.connect(self.about_keyboard)
        self.about_menu = self.menuBar().addMenu(tr("Menu", "About"))
        self.about_menu.addAction(self.about_keyboard_act)
        self.about_menu.addAction(about_vial_act)

    def on_layout_load(self):
        # Guard: a layout can only be applied to a connected keyboard.
        if not isinstance(self.autorefresh.current_device, VialKeyboard):
            QMessageBox.warning(self, "No keyboard",
                                tr("MainWindow", "Connect a keyboard before loading a layout."))
            return

        dialog = QFileDialog()
        dialog.setDefaultSuffix("vil")
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setNameFilters(["Vial layout (*.vil)"])
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
        dialog = QFileDialog()
        dialog.setDefaultSuffix("vil")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setNameFilters(["Vial layout (*.vil)"])
        if dialog.exec_() == QDialog.Accepted:
            with open(dialog.selectedFiles()[0], "wb") as outf:
                outf.write(self.keymap_editor.save_layout())

    # ------------------------------------------------------------------
    # Keyboard clone (whole-EEPROM save/restore)
    #
    # A clone captures the keyboard's ENTIRE persistent state — layout plus
    # every MIDI/ThruLoop/actuation/articulation setting, presets, names, QB
    # masters, everything — by streaming the 64KB config EEPROM over raw HID
    # (command 0x94). The firmware reports an EEPROM layout version; it is
    # stamped into the clone file and checked before a restore, so a clone
    # saved on a firmware whose EEPROM regions live at different addresses
    # can never be written over an incompatible layout and corrupt it.
    # ------------------------------------------------------------------

    CLONE_FILE_MAGIC = "midiswitch-keyboard-clone"

    def _clone_get_keyboard_or_warn(self):
        """Return (keyboard, clone_info) for a connected clone-capable
        keyboard, or (None, None) after showing the appropriate warning."""
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
        # the keyboard's USB endpoints, which (before the firmware's bounded-
        # send fix) wedged the keyboard itself when keys were pressed
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
            set_hid_transfer_active(False)
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

        # EEPROM-layout compatibility gate. A clone whose firmware stored its
        # regions at different addresses can't be written as-is — it would
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
            set_hid_transfer_active(False)
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

        keyboard.clone_finalize()
        QMessageBox.information(
            self, "Clone loaded",
            tr("MainWindow", "Keyboard clone restored successfully.\n\n"
                             "The keyboard is rebooting to apply the restored settings; "
                             "it will reconnect automatically in a few seconds."))
        # Pick the device back up once it has re-enumerated.
        QTimer.singleShot(4000, lambda: self.autorefresh.update(quiet=True, hard=True))

    def on_click_refresh(self):
        self.autorefresh.update(quiet=False, hard=True)

    def on_devices_updated(self, devices, hard_refresh):
        self.combobox_devices.blockSignals(True)

        self.combobox_devices.clear()
        for dev in devices:
            self.combobox_devices.addItem(dev.title())
            if self.autorefresh.current_device and dev.desc["path"] == self.autorefresh.current_device.desc["path"]:
                self.combobox_devices.setCurrentIndex(self.combobox_devices.count() - 1)

        self.combobox_devices.blockSignals(False)

        if devices:
            self.lbl_no_devices.hide()
            self.tabs.show()
        else:
            self.lbl_no_devices.show()
            self.tabs.hide()

        if hard_refresh:
            self.on_device_selected()

    def on_device_selected(self):
        _startup_log("on_device_selected() called...")
        t0 = time.time()
        try:
            self.autorefresh.select_device(self.combobox_devices.currentIndex())
            _startup_log(f"  autorefresh.select_device() done ({time.time()-t0:.2f}s)")
        except ProtocolError:
            QMessageBox.warning(self, "", "Unsupported protocol version!\n"
                                          "Please download latest Vial from https://get.vial.today/")
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
                                "another application or was disconnected.\n\n{}").format(e))

        if isinstance(self.autorefresh.current_device, VialKeyboard):
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

            # Confirm this is our keyboard via its unique Vial UID (the product
            # string was already matched at enumeration). If it matches, run the
            # startup firmware-version check.
            if keyboard_id != MIDISWITCH_KEYBOARD_UID:
                QMessageBox.warning(self, "", "This does not appear to be a MIDIswitch keyboard.\n"
                                              "Some features may not work correctly.")
            else:
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
            "A firmware update is available — see the MIDIswitch releases page to update.".format(cur, latest))

    def rebuild(self):
        _startup_log("MainWindow.rebuild() starting...")
        rebuild_start = time.time()

        # don't show "Security" menu for bootloader mode, as the bootloader is inherently insecure
        self.security_menu.menuAction().setVisible(isinstance(self.autorefresh.current_device, VialKeyboard))

        self.about_keyboard_act.setVisible(False)
        if isinstance(self.autorefresh.current_device, VialKeyboard):
            self.about_keyboard_act.setText("About {}...".format(self.autorefresh.current_device.title()))
            self.about_keyboard_act.setVisible(True)

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
            (self.combos, "combos"),
            (self.key_override, "key_override"),
            (self.qmk_settings, "qmk_settings"),
            (self.matrix_tester, "matrix_tester"),
            (self.rgb_configurator, "rgb_configurator"),
            (self.MIDIswitchSettingsConfigurator, "MIDIswitchSettingsConfigurator"),
            (self.gaming_configurator, "gaming_configurator"),
            (self.midi_patchbay, "midi_patchbay"),
            (self.loop_manager, "loop_manager"),
            (self.arpeggiator, "arpeggiator"),
            (self.step_sequencer, "step_sequencer"),
            (self.delay_tab, "delay_tab"),
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
            self.dks_settings,
            self.toggle_settings,
            self.combos,
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

    def refresh_tabs(self):
        # Disable UI updates during tab refresh to speed up the process
        self.tabs.setUpdatesEnabled(False)
        try:
            # QTabWidget.clear() reparents the pages to None without deleting
            # them, so the cached EditorContainers survive and can be re-added.
            self.tabs.clear()
            for editor, lbl in self.editors:
                if not editor.valid():
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
        finally:
            self.tabs.setUpdatesEnabled(True)

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
        dialog.setNameFilters(["VIA layout JSON (*.json)"])
        if dialog.exec_() == QDialog.Accepted:
            with open(dialog.selectedFiles()[0], "rb") as inf:
                data = inf.read()
            self.autorefresh.load_dummy(data)

    def lock_ui(self):
        self.ui_lock_count += 1
        if self.ui_lock_count == 1:
            self.autorefresh._lock()
            self.tabs.setEnabled(False)
            self.combobox_devices.setEnabled(False)
            self.btn_refresh_devices.setEnabled(False)

    def unlock_ui(self):
        self.ui_lock_count -= 1
        if self.ui_lock_count == 0:
            self.autorefresh._unlock()
            self.tabs.setEnabled(True)
            self.combobox_devices.setEnabled(True)
            self.btn_refresh_devices.setEnabled(True)

    def unlock_keyboard(self):
        if isinstance(self.autorefresh.current_device, VialKeyboard):
            Unlocker.unlock(self.autorefresh.current_device.keyboard)

    def lock_keyboard(self):
        if isinstance(self.autorefresh.current_device, VialKeyboard):
            self.autorefresh.current_device.keyboard.lock()

    def reboot_to_bootloader(self):
        if isinstance(self.autorefresh.current_device, VialKeyboard):
            Unlocker.unlock(self.autorefresh.current_device.keyboard)
            self.autorefresh.current_device.keyboard.reset()

    def change_keyboard_layout(self, index):
        self.settings.setValue("keymap", KEYMAPS[index][0])
        KeycodeDisplay.set_keymap_override(KEYMAPS[index][1])

    def get_theme(self):
        return self.settings.value("theme", "Lavender Dream")

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

        if old_tab is not None:
            old_tab.editor.deactivate()
        if new_tab is not None:
            new_tab.editor.activate()

        self.current_tab = new_tab

    def switch_to_trigger_settings(self):
        """Switch to Trigger Settings tab and enable per-key mode"""
        # Find the index of the Trigger Settings tab
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

    def about_vial(self):
        title = "About SwitchStation"
        text = 'SwitchStation ver {}<br>Python {}<br>Qt {}<br>' \
                'Licensed under the terms of the<br>GNU General Public License (version 2 or later)<br><br>' \
                '<a href="https://www.MIDIswitch.com">https://www.MIDIswitch.com</a><br><br><br>' \
                'Only made possible by all the amazing contributors to Vial!<br>' \
                .format(qApp.applicationVersion(), platform.python_version(), QT_VERSION_STR)
    


        if sys.platform == "emscripten":
            self.msg_about = QMessageBox()
            self.msg_about.setWindowTitle(title)
            self.msg_about.setText(text)
            self.msg_about.setModal(True)
            self.msg_about.show()
        else:
            QMessageBox.about(self, title, text)

    def about_keyboard(self):
        self.about_dialog = AboutKeyboard(self.autorefresh.current_device)
        self.about_dialog.setModal(True)
        self.about_dialog.show()

    def closeEvent(self, e):
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