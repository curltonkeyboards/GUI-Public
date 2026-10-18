# SPDX-License-Identifier: GPL-2.0-or-later
"""Firmware updater page.

Update flow for a connected keyboard:
  1. back up every setting (keyboard clone, saved to the backups folder)
  2. put the keyboard into update mode (no buttons to hold)
  3. install the signed .mswfw package over USB HID (no driver needed)
  4. wait for the keyboard to restart, then restore the backup —
     converted forward when the new firmware stores settings differently

A keyboard found already in update mode (an interrupted update, or no
firmware installed) can be flashed directly, and offers to restore the newest
backup taken for it.
"""
import datetime
import logging
import os
import sys
import threading
import time

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QHBoxLayout, QLineEdit, QToolButton, QPlainTextEdit, QProgressBar, \
    QFileDialog, QDialog, QCheckBox, QLabel, QPushButton, QMessageBox

from editor.basic_editor import BasicEditor
from hidproxy import hid
from protocol import clone_io
from protocol import msw_updater as upd
from util import tr, is_midiswitch_usb_id, RAW_HID_USAGE_PAGE, RAW_HID_USAGE
from vial_device import VialKeyboard, VialDummyKeyboard, VialVirtualKeyboard, MswBootloader

WAIT_BOOTLOADER_S = 30
WAIT_KEYBOARD_S = 45

WHY_TEXT = {
    0: "the app asked it to",
    1: "ESC was held at power-on",
    2: "no firmware is installed (or the last update was interrupted)",
}


def _keyboard_desc(descs, serial):
    for d in descs:
        if (is_midiswitch_usb_id(d) and d.get("usage_page") == RAW_HID_USAGE_PAGE
                and d.get("usage") == RAW_HID_USAGE
                and (not serial or (d.get("serial_number") or "") == serial)):
            return d
    return None


class FirmwareFlasher(BasicEditor):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(float)
    done_signal = pyqtSignal(bool, str)

    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        self.package = None
        self.kb_update = None
        self.boot_info = None
        self.running = False

        self.log_signal.connect(self._on_log)
        self.progress_signal.connect(self._on_progress)
        self.done_signal.connect(self._on_done)

        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        self.addWidget(self.lbl_status)

        row = QHBoxLayout()
        self.txt_file = QLineEdit()
        self.txt_file.setReadOnly(True)
        self.txt_file.setPlaceholderText(tr("Flasher", "Choose a firmware file (.mswfw)"))
        row.addWidget(self.txt_file)
        self.btn_select = QToolButton()
        self.btn_select.setText(tr("Flasher", "Select file..."))
        self.btn_select.clicked.connect(self.on_select_file)
        row.addWidget(self.btn_select)
        self.addLayout(row)

        self.lbl_package = QLabel()
        self.addWidget(self.lbl_package)

        self.chk_keep = QCheckBox(tr("Flasher", "Keep my settings (back up before the update and "
                                                "restore them afterwards)"))
        self.chk_keep.setChecked(True)
        self.addWidget(self.chk_keep)

        row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        row.addWidget(self.progress)
        self.btn_update = QPushButton(tr("Flasher", "Update firmware"))
        self.btn_update.clicked.connect(self.on_update)
        row.addWidget(self.btn_update)
        self.addLayout(row)

        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.addWidget(self.txt_log)

        self.btn_backups = QToolButton()
        self.btn_backups.setText(tr("Flasher", "Show settings backups folder"))
        self.btn_backups.clicked.connect(self.on_show_backups)
        self.addWidget(self.btn_backups, alignment=Qt.AlignLeft)

    # ---- Device state ------------------------------------------------------------

    def _is_real_keyboard(self):
        return isinstance(self.device, VialKeyboard) and \
            not isinstance(self.device, (VialDummyKeyboard, VialVirtualKeyboard))

    def valid(self):
        if sys.platform == "emscripten":
            return False
        return isinstance(self.device, MswBootloader) or self._is_real_keyboard()

    def rebuild(self, device):
        super().rebuild(device)
        if self.running:
            return
        self.kb_update = None
        self.boot_info = None
        if self._is_real_keyboard():
            try:
                self.kb_update = self.device.keyboard.get_update_mode_info()
            except Exception:
                logging.exception("update mode query failed")
        elif isinstance(self.device, MswBootloader) and self.device.dev is not None:
            try:
                client = upd.BootloaderClient(upd.HidTransport(self.device.dev))
                client.drain()
                self.boot_info = client.info()
            except Exception:
                logging.exception("bootloader info failed")
        self._refresh_status()

    def _current_version(self):
        kb = self.device.keyboard
        get = getattr(kb, "get_firmware_version", None)
        if get:
            try:
                v = get()
                if v:
                    return tuple(v)
            except Exception:
                pass
        ident = getattr(kb, "msw_ident", None)
        return tuple(ident["firmware"]) if ident else None

    def _refresh_status(self):
        can = False
        if isinstance(self.device, MswBootloader):
            if self.boot_info:
                why = WHY_TEXT.get(self.boot_info["why"], "")
                text = tr("Flasher", "The keyboard is in update mode ({}).").format(why)
                if self.boot_info["app_valid"]:
                    text += " " + tr("Flasher", "Installed firmware: {}.").format(
                        upd.version_str(self.boot_info["app_version"]))
                can = True
            else:
                text = tr("Flasher", "The keyboard is in update mode but is not answering. "
                                     "Unplug it and plug it back in.")
            self.chk_keep.setText(tr("Flasher", "Restore my settings from the newest backup "
                                                "afterwards (if there is one)"))
        elif self._is_real_keyboard():
            cur = self._current_version()
            cur_s = ".".join(str(v) for v in cur) if cur else tr("Flasher", "unknown")
            if self.kb_update and self.kb_update[0] == 2:
                text = tr("Flasher", "Installed firmware: {}. Choose a firmware file to update.").format(cur_s)
                can = True
            else:
                text = tr("Flasher", "Installed firmware: {}.\n\nThis keyboard cannot be updated from "
                                     "the app yet: it needs the MIDIswitch updater installed once "
                                     "with STM32CubeProgrammer (see the update instructions). "
                                     "After that, every update happens here.").format(cur_s)
            self.chk_keep.setText(tr("Flasher", "Keep my settings (back up before the update and "
                                                "restore them afterwards)"))
        else:
            text = ""
        self.lbl_status.setText(text)
        self.btn_update.setEnabled(can and self.package is not None and not self.running)

    # ---- UI actions ------------------------------------------------------------------

    def on_select_file(self):
        dialog = QFileDialog()
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setNameFilters(["MIDIswitch firmware (*.mswfw)"])
        if dialog.exec_() != QDialog.Accepted:
            return
        path = dialog.selectedFiles()[0]
        try:
            with open(path, "rb") as f:
                blob = f.read(4 * 1024 * 1024)
            self.package = upd.parse_package(blob)
        except (OSError, upd.UpdateError) as e:
            self.package = None
            self.lbl_package.setText("")
            QMessageBox.warning(None, tr("Flasher", "Firmware file"), str(e))
        else:
            self.txt_file.setText(path)
            self.lbl_package.setText(tr("Flasher", "Firmware {} ({} KB)").format(
                upd.version_str(self.package["version"]), self.package["size"] // 1024))
            self.log("Selected {}".format(path))
        self._refresh_status()

    def on_show_backups(self):
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(clone_io.backup_dir()))

    def on_update(self):
        if self.package is None or self.running:
            return
        pkg = self.package
        restore_path = None

        if isinstance(self.device, MswBootloader):
            mode = "bootloader"
            serial = self.device.desc.get("serial_number") or ""
            if self.chk_keep.isChecked():
                backups = clone_io.backups_for(serial)
                if backups:
                    restore_path = backups[0]
            msg = tr("Flasher", "Install firmware {}?").format(upd.version_str(pkg["version"]))
            if restore_path:
                msg += "\n\n" + tr("Flasher", "Afterwards your settings will be restored from the "
                                              "backup taken {}.").format(self._backup_time(restore_path))
        else:
            mode = "keyboard"
            cur = self._current_version()
            msg = tr("Flasher", "Update the keyboard to firmware {}?").format(upd.version_str(pkg["version"]))
            if cur and (cur[0] << 16 | cur[1] << 8 | cur[2]) > pkg["version"]:
                msg += "\n\n" + tr("Flasher", "This is OLDER than the installed firmware ({}).").format(
                    ".".join(str(v) for v in cur))
            if self.chk_keep.isChecked():
                msg += "\n\n" + tr("Flasher", "Your settings are backed up first and restored "
                                              "afterwards.")
            else:
                msg += "\n\n" + tr("Flasher", "Your settings will NOT be backed up.")
        msg += "\n\n" + tr("Flasher", "Don't unplug the keyboard until this finishes. If the update "
                                      "is interrupted, plug it back in and it will come back in "
                                      "update mode.")
        if QMessageBox.question(None, tr("Flasher", "Firmware update"), msg,
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return

        self.running = True
        self.progress.setValue(0)
        self.btn_update.setEnabled(False)
        self.btn_select.setEnabled(False)
        self.main.lock_ui()
        keep = self.chk_keep.isChecked()
        threading.Thread(target=self._run, args=(mode, pkg, keep, restore_path), daemon=True).start()

    @staticmethod
    def _backup_time(path):
        try:
            return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        except OSError:
            return os.path.basename(path)

    # ---- Worker (background thread) ------------------------------------------------------

    def _wait_for(self, finder, seconds, what):
        self.log_signal.emit("Waiting for {}...".format(what))
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                found = finder(list(hid.enumerate()))
            except Exception:
                found = None
            if found:
                return found
            time.sleep(0.5)
        raise upd.UpdateError("Timed out waiting for {}.".format(what))

    def _run(self, mode, pkg, keep, restore_path):
        log = self.log_signal.emit
        prog = self.progress_signal.emit
        backup = None   # (path, blob, layout_version)
        opened = None
        try:
            serial = self.device.desc.get("serial_number") or ""
            if mode == "keyboard":
                kb = self.device.keyboard
                if keep:
                    info = kb.get_clone_info()
                    if not info:
                        raise upd.UpdateError("This firmware cannot back up its settings. Untick "
                                              "'Keep my settings' to update anyway.")
                    log("Backing up settings...")
                    blob = clone_io.read_image(kb, info, lambda f: prog(0.10 * f))
                    path = clone_io.new_backup_path(serial)
                    clone_io.save_file(path, blob, info)
                    clone_io.prune_backups(serial)
                    backup = (path, blob, info["layout_version"])
                    log("Settings saved to {}".format(path))
                log("Restarting the keyboard in update mode...")
                r = kb.enter_update_mode()
                if r == "busy":
                    raise upd.UpdateError("A loop is recording. Stop it and try again.")
                if r != "ok":
                    raise upd.UpdateError("The keyboard did not accept the update request.")
                desc = self._wait_for(lambda ds: upd.find_bootloader(ds, serial), WAIT_BOOTLOADER_S,
                                      "the keyboard to enter update mode")
                opened = hid.device()
                opened.open_path(desc["path"])
                dev = opened
            else:
                dev = self.device.dev
                if restore_path:
                    blob, layout = clone_io.load_file(restore_path)
                    backup = (restore_path, blob, layout)

            client = upd.BootloaderClient(upd.HidTransport(dev))
            client.drain()
            log("Installing firmware {}...".format(upd.version_str(pkg["version"])))
            client.flash(pkg, log, lambda f: prog(0.10 + 0.75 * f))
            log("Firmware installed. Restarting the keyboard...")
            client.reboot()
            if opened is not None:
                opened.close()
                opened = None

            kb_desc = self._wait_for(lambda ds: _keyboard_desc(ds, serial), WAIT_KEYBOARD_S,
                                     "the keyboard to restart")
            if backup:
                self._restore(kb_desc, backup)
                self._wait_for(lambda ds: _keyboard_desc(ds, serial), WAIT_KEYBOARD_S,
                               "the keyboard to restart with your settings")
            prog(1.0)
            self.done_signal.emit(True, "Update complete.")
        except Exception as e:
            logging.exception("firmware update failed")
            msg = str(e) or e.__class__.__name__
            if backup:
                msg += "\n\nYour settings backup is saved at:\n{}".format(backup[0])
            self.done_signal.emit(False, msg)
        finally:
            if opened is not None:
                try:
                    opened.close()
                except Exception:
                    pass

    def _restore(self, desc, backup):
        from protocol.keyboard_comm import Keyboard
        from protocol.clone_migrations import can_migrate, migrate_clone
        log = self.log_signal.emit
        path, blob, from_v = backup

        dev = hid.device()
        dev.open_path(desc["path"])
        try:
            kb = Keyboard(dev)
            info = None
            for _ in range(20):        # the new firmware may still be starting up
                info = kb.get_clone_info()
                if info:
                    break
                time.sleep(0.5)
            if not info:
                raise upd.UpdateError("The new firmware installed, but it does not accept settings "
                                      "restores, so your settings were not put back.")
            to_v = info["layout_version"]
            if from_v != to_v:
                if not can_migrate(from_v, to_v):
                    raise upd.UpdateError(
                        "The new firmware installed, but your settings could not be converted "
                        "automatically (settings layout v{} -> v{}), so they were not restored. "
                        "Update the app, then load the backup with File > Load keyboard clone."
                        .format(from_v, to_v))
                blob, notes = migrate_clone(bytearray(blob), from_v, to_v)
                log("Converting settings to the new firmware's layout:")
                for n in notes:
                    log("  - " + n)
            log("Restoring settings...")
            clone_io.write_image(kb, info, bytes(blob), lambda f: self.progress_signal.emit(0.85 + 0.13 * f))
            if not kb.clone_finalize():
                raise upd.UpdateError("Settings were written but the keyboard did not confirm.")
            log("Settings restored. Restarting the keyboard...")
        finally:
            dev.close()

    # ---- Signals (GUI thread) ----------------------------------------------------------

    def _on_log(self, line):
        self.log(line)

    def _on_progress(self, f):
        self.progress.setValue(int(max(0.0, min(1.0, f)) * 1000))

    def _on_done(self, ok, msg):
        self.running = False
        self.log(msg)
        self.btn_select.setEnabled(True)
        self.main.unlock_ui()
        if ok:
            QMessageBox.information(None, tr("Flasher", "Firmware update"), msg)
        else:
            QMessageBox.critical(None, tr("Flasher", "Firmware update failed"), msg)
        self.main.on_click_refresh()

    def log(self, line):
        self.txt_log.appendPlainText("[{}] {}".format(datetime.datetime.now().strftime("%H:%M:%S"), line))
