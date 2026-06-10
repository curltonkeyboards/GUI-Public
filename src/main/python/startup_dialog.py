# SPDX-License-Identifier: GPL-2.0-or-later
"""
Startup dialog with progress logging to help diagnose slow startup times.
Shows what the application is waiting for during initialization.
"""

import time
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTextEdit, QLabel, QProgressBar, QApplication)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QTextCursor


class StartupLogger(QObject):
    """Global logger for startup progress messages."""

    instance = None
    message_logged = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        StartupLogger.instance = self
        self._start_time = time.time()
        self._step_start = None
        self._enabled = True

    def log(self, message):
        """Log a message with timestamp."""
        if not self._enabled:
            return
        elapsed = time.time() - self._start_time
        formatted = f"[{elapsed:6.2f}s] {message}"
        print(formatted)  # Also print to console
        self.message_logged.emit(formatted)

    def start_step(self, step_name):
        """Start timing a step."""
        self._step_start = time.time()
        self.log(f"Starting: {step_name}...")

    def end_step(self, step_name=None):
        """End timing a step and log duration."""
        if self._step_start is not None:
            duration = time.time() - self._step_start
            suffix = f" ({duration:.2f}s)" if step_name else f" (took {duration:.2f}s)"
            msg = f"Completed: {step_name}{suffix}" if step_name else f"Step completed{suffix}"
            self.log(msg)
            self._step_start = None

    def disable(self):
        """Disable logging (for after startup)."""
        self._enabled = False

    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance."""
        if cls.instance is None:
            cls.instance = StartupLogger()
        return cls.instance


def startup_log(message):
    """Convenience function to log startup messages."""
    logger = StartupLogger.get_instance()
    if logger:
        logger.log(message)


def startup_step(step_name):
    """Convenience function to start a timed step."""
    logger = StartupLogger.get_instance()
    if logger:
        logger.start_step(step_name)


def startup_step_done(step_name=None):
    """Convenience function to end a timed step."""
    logger = StartupLogger.get_instance()
    if logger:
        logger.end_step(step_name)


class StartupDialog(QDialog):
    """
    Dialog shown at startup to let user choose when to start the app
    and see progress of initialization.
    """

    start_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Curlton KeyStation - Startup Log")
        self.setMinimumSize(600, 400)
        self.resize(700, 500)

        # Start as modal, will become non-modal after startup
        self.setModal(True)

        # Allow close button
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

        self._should_start = False
        self._is_running = False
        self._startup_complete = False

        self._setup_ui()
        self._setup_logger()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Curlton KeyStation")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Description
        self.desc_label = QLabel("The application needs to scan for HID devices and load keyboard data.\n"
                                  "This can take some time. The log below will show progress.")
        self.desc_label.setAlignment(Qt.AlignCenter)
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)

        # Progress bar (hidden initially, shown during loading)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # Log output - make it selectable and copyable
        log_label = QLabel("Startup Log (select text to copy):")
        layout.addWidget(log_label)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        # Enable text selection and copying
        self.log_output.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.log_output.setFont(QFont("Consolas", 9) if hasattr(QFont, "Consolas") else QFont("monospace", 9))
        self.log_output.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                padding: 5px;
                selection-background-color: #264f78;
                selection-color: #ffffff;
            }
        """)
        layout.addWidget(self.log_output, 1)  # Stretch factor 1

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.copy_button = QPushButton("Copy Log")
        self.copy_button.setMinimumWidth(100)
        self.copy_button.clicked.connect(self._on_copy)
        button_layout.addWidget(self.copy_button)

        self.start_button = QPushButton("Start Application")
        self.start_button.setMinimumWidth(150)
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self._on_start)
        button_layout.addWidget(self.start_button)

        self.close_button = QPushButton("Cancel")
        self.close_button.setMinimumWidth(100)
        self.close_button.clicked.connect(self._on_close)
        button_layout.addWidget(self.close_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def _setup_logger(self):
        self.logger = StartupLogger.get_instance()
        self.logger.message_logged.connect(self._append_log)

    def _append_log(self, message):
        """Append a message to the log output."""
        self.log_output.append(message)
        # Auto-scroll to bottom
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_output.setTextCursor(cursor)
        # Process events to update UI
        QApplication.processEvents()

    def _on_copy(self):
        """Copy all log text to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.log_output.toPlainText())
        # Brief visual feedback
        old_text = self.copy_button.text()
        self.copy_button.setText("Copied!")
        QTimer.singleShot(1000, lambda: self.copy_button.setText(old_text))

    def _on_start(self):
        """Handle start button click."""
        self._should_start = True
        self._is_running = True
        self.start_button.setEnabled(False)
        self.start_button.setText("Starting...")
        self.close_button.setText("Cancel Startup")
        self.progress_bar.show()

        startup_log("User requested application start")

        # Emit signal to start the app (after a small delay to let UI update)
        QTimer.singleShot(100, self.start_requested.emit)

    def _on_close(self):
        """Handle close button click."""
        if self._startup_complete:
            # After startup, just close the log window
            self.close()
        elif self._is_running:
            startup_log("Startup cancelled by user")
            self._should_start = False
            self.reject()
        else:
            self._should_start = False
            self.reject()

    def should_start(self):
        """Return whether the user chose to start the app."""
        return self._should_start

    def finish_startup(self):
        """Called when startup is complete - close the dialog automatically."""
        startup_log("Startup complete - main window is now open")

        self._startup_complete = True
        self._is_running = False

        # Close the dialog automatically after a brief delay
        # This allows the final log message to be visible momentarily
        QTimer.singleShot(500, self.accept)

    def log(self, message):
        """Log a message to the startup log."""
        startup_log(message)
