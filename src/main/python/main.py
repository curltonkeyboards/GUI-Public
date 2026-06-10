# SPDX-License-Identifier: GPL-2.0-or-later
import ssl
import certifi
import os

if ssl.get_default_verify_paths().cafile is None:
    os.environ['SSL_CERT_FILE'] = certifi.where()

import traceback

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSignal

from fbs_runtime.application_context import cached_property
from fbs_runtime.application_context.PyQt5 import ApplicationContext

import sys

from main_window import MainWindow


# http://timlehr.com/python-exception-hooks-with-qt-message-box/
from util import init_logger


def show_exception_box(log_msg):
    if QtWidgets.QApplication.instance() is not None:
        errorbox = QtWidgets.QMessageBox()
        errorbox.setText(log_msg)
        errorbox.exec_()


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

class VialApplicationContext(ApplicationContext):
    @cached_property
    def app(self):
        # Override the app definition in order to set WM_CLASS.
        result = QtWidgets.QApplication(sys.argv)
        #result.setApplicationName(self.build_settings["app_name"])
        result.setApplicationName("Curlton KeyStation")
        result.setOrganizationDomain("vial.today")

        #TODO: Qt sets applicationVersion on non-Linux platforms if the exe/pkg metadata is correctly configured.
        # https://doc.qt.io/qt-5/qcoreapplication.html#applicationVersion-prop
        # Verify it is, and only set manually on Linux.
        #if sys.platform.startswith("linux"):
        result.setApplicationVersion(self.build_settings["version"])
        return result

class StartupManager:
    """Manages the startup flow with optional startup dialog."""

    def __init__(self, appctxt):
        self.appctxt = appctxt
        self.window = None
        self.startup_dialog = None
        self._startup_complete = False

    def run_with_startup_dialog(self):
        """Show startup dialog, then launch main window."""
        from startup_dialog import StartupDialog, startup_log

        startup_log("Application context created")
        startup_log("Initializing startup dialog...")

        self.startup_dialog = StartupDialog()
        self.startup_dialog.start_requested.connect(self._on_start_requested)

        # Show the dialog (modal until startup completes)
        self.startup_dialog.show()

        # Run the event loop - this will process events until app exits
        return self.appctxt.app.exec_()

    def _on_start_requested(self):
        """Called when user clicks Start in the startup dialog."""
        from startup_dialog import startup_log
        from PyQt5.QtWidgets import QApplication
        import time

        startup_log("Creating main window...")
        t0 = time.time()

        try:
            # Create the main window (this triggers device scanning and loading)
            self.window = MainWindow(self.appctxt)
            startup_log(f"Main window created ({time.time()-t0:.2f}s)")

            # Mark startup complete and update dialog
            self.startup_dialog.finish_startup()

            # Show the main window
            self.window.show()

        except Exception as e:
            startup_log(f"ERROR: {e}")
            import traceback
            startup_log(traceback.format_exc())
            raise

    def run_without_dialog(self):
        """Run without startup dialog (original behavior)."""
        self.window = MainWindow(self.appctxt)
        self.window.show()
        return self.appctxt.app.exec_()


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == "--linux-recorder":
        from linux_keystroke_recorder import linux_keystroke_recorder

        linux_keystroke_recorder()
    else:
        appctxt = VialApplicationContext()       # 1. Instantiate ApplicationContext
        init_logger()
        qt_exception_hook = UncaughtHook()

        # Check for --no-startup-dialog flag to skip the dialog
        use_startup_dialog = "--no-startup-dialog" not in sys.argv

        manager = StartupManager(appctxt)
        if use_startup_dialog:
            exit_code = manager.run_with_startup_dialog()
        else:
            exit_code = manager.run_without_dialog()

        sys.exit(exit_code)
