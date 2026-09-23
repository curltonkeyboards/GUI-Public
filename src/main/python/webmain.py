# SPDX-License-Identifier: GPL-2.0-or-later
import os

import traceback

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSignal

import sys
import json

from main_window import MainWindow


# http://timlehr.com/python-exception-hooks-with-qt-message-box/
from util import init_logger


def show_exception_box(log_msg):
    if QtWidgets.QApplication.instance() is not None:
        global errorbox

        errorbox = QtWidgets.QMessageBox()
        errorbox.setText(log_msg)
        errorbox.setModal(True)
        errorbox.show()


class UncaughtHook(QtCore.QObject):
    _exception_caught = pyqtSignal(object)

    def __init__(self, *args, **kwargs):
        super(UncaughtHook, self).__init__(*args, **kwargs)

        # this registers the exception_hook() function as hook with the Python interpreter
        sys._excepthook = sys.excepthook
        sys.excepthook = self.exception_hook

        # connect signal to execute the message box function always on main thread
        self._exception_caught.connect(show_exception_box)

    def exception_hook(self, exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # ignore keyboard interrupt to support console applications
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
        else:
            log_msg = '\n'.join([''.join(traceback.format_tb(exc_traceback)),
                                 '{0}: {1}'.format(exc_type.__name__, exc_value)])

            # trigger message box show
            self._exception_caught.emit(log_msg)
        sys._excepthook(exc_type, exc_value, exc_traceback)


def web_get_resource(name):
    return "/usr/local/" + name


_open_dialogs = []  # keeps non-blocking dialogs alive until closed


def _show_non_blocking(dlg):
    _open_dialogs.append(dlg)
    dlg.finished.connect(lambda _r, d=dlg: _open_dialogs.remove(d) if d in _open_dialogs else None)
    dlg.show()


def _make_dialogs_non_blocking():
    """The browser build cannot run a nested event loop (exec_ would need
    emscripten_sleep and aborts the whole page). Show dialogs without waiting
    and hand the caller a safe answer: OK for notices, No for questions,
    Rejected for other dialogs, no action for menus."""
    from PyQt5.QtWidgets import QDialog, QMessageBox, QMenu

    def dialog_exec(self, *args):
        _show_non_blocking(self)
        return QDialog.Rejected

    def msgbox_exec(self, *args):
        _show_non_blocking(self)
        buttons = self.standardButtons()
        if buttons & QMessageBox.No:
            return QMessageBox.No
        if buttons & QMessageBox.Cancel:
            return QMessageBox.Cancel
        return QMessageBox.Ok

    def notice(icon):
        def show(parent, title, text, *args, **kwargs):
            box = QMessageBox(icon, title, text, QMessageBox.Ok, parent)
            _show_non_blocking(box)
            return QMessageBox.Ok
        return staticmethod(show)

    def question(parent, title, text, *args, **kwargs):
        box = QMessageBox(QMessageBox.Question, title, text, QMessageBox.Ok, parent)
        _show_non_blocking(box)
        return QMessageBox.No

    def about(parent, title, text):
        box = QMessageBox(QMessageBox.Information, title, text, QMessageBox.Ok, parent)
        _show_non_blocking(box)

    def menu_exec(self, *args):
        if args:
            self.popup(args[0])
        return None

    QDialog.exec_ = dialog_exec
    QDialog.exec = dialog_exec
    QMessageBox.exec_ = msgbox_exec
    QMessageBox.exec = msgbox_exec
    QMessageBox.warning = notice(QMessageBox.Warning)
    QMessageBox.information = notice(QMessageBox.Information)
    QMessageBox.critical = notice(QMessageBox.Critical)
    QMessageBox.question = staticmethod(question)
    QMessageBox.about = staticmethod(about)
    QMenu.exec_ = menu_exec
    QMenu.exec = menu_exec


def main(app, demo=False):
    _make_dialogs_non_blocking()
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)

    app.get_resource = web_get_resource
    with open(app.get_resource("build_settings.json"), "r") as inf:
        app.build_settings = json.loads(inf.read())
    qt_exception_hook = UncaughtHook()
    app.defer_ready = demo
    window = MainWindow(app)
    window.show()
    app.processEvents()
    if demo:
        # No keyboard: open a virtual MIDIswitch built from the bundled
        # layout definition so the app can be explored.
        from protocol import msw_definition
        definition = msw_definition.get_definition(1)  # the MIDIswitch model
        if not isinstance(definition, (str, bytes)):
            definition = json.dumps(definition)
        if isinstance(definition, str):
            definition = definition.encode("utf-8")
        window.autorefresh.load_dummy(definition)
        window.update()
        app.processEvents()
        import vialglue
        vialglue.notify_ready()
