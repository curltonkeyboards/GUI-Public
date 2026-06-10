# SPDX-License-Identifier: GPL-2.0-or-later
import time
from PyQt5 import QtCore
from PyQt5.QtCore import QTimer, pyqtSignal, QObject
from PyQt5.QtWidgets import (QWidget, QPushButton, QHBoxLayout, QVBoxLayout, QSizePolicy,
                             QLabel, QComboBox, QListWidget, QListWidgetItem, QGroupBox,
                             QMessageBox, QCheckBox)

from editor.basic_editor import BasicEditor
from util import tr
from vial_device import VialKeyboard

try:
    import rtmidi
    MIDI_AVAILABLE = True
except ImportError:
    MIDI_AVAILABLE = False


class MIDIPatchBay(BasicEditor):
    """MIDI Patchbay tab for routing MIDI devices to/from MIDIswitch"""

    def __init__(self):
        super().__init__()

        self.midi_in = None
        self.midi_out = None
        self.midiswitch_output = None
        self.active_connections = {}  # {input_id: {input, output, callback, filters}}
        self.selected_connection_id = None  # Track which connection's filters are shown
        self.device_refresh_timer = QTimer()
        self.device_refresh_timer.timeout.connect(self.refresh_devices)

        self.setup_ui()

        if MIDI_AVAILABLE:
            self.initialize_midi()
            self.device_refresh_timer.start(2000)  # Refresh every 2 seconds

    def setup_ui(self):
        self.addStretch()

        main_widget = QWidget()
        main_widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        self.addWidget(main_widget)
        self.setAlignment(main_widget, QtCore.Qt.AlignHCenter)

        # Title
        title_label = QLabel(tr("MIDIPatchBay", "MIDI Patchbay"))
        title_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(tr("MIDIPatchBay",
            "Route MIDI devices to your MIDIswitch keyboard. Connect external MIDI controllers\n"
            "to send MIDI messages through the keyboard. Filter which message types are passed through."))
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; font-size: 9pt;")
        desc_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(desc_label)

        if not MIDI_AVAILABLE:
            error_label = QLabel(tr("MIDIPatchBay",
                "MIDI support not available. Please install python-rtmidi:\npip install python-rtmidi"))
            error_label.setStyleSheet("color: red; padding: 20px;")
            error_label.setAlignment(QtCore.Qt.AlignCenter)
            main_layout.addWidget(error_label)
            self.addStretch()
            return

        # Connection section
        connection_group = QGroupBox()
        connection_layout = QVBoxLayout()
        connection_group.setLayout(connection_layout)
        main_layout.addWidget(connection_group)

        # Device selector
        device_layout = QHBoxLayout()
        device_layout.addWidget(QLabel(tr("MIDIPatchBay", "Connect Device to midiswitch")))

        self.device_selector = QComboBox()
        self.device_selector.setMinimumWidth(250)
        device_layout.addWidget(self.device_selector)

        self.connect_btn = QPushButton(tr("MIDIPatchBay", "Connect"))
        self.connect_btn.setMinimumHeight(30)
        self.connect_btn.clicked.connect(self.on_connect_device)
        device_layout.addWidget(self.connect_btn)

        device_layout.addStretch()
        connection_layout.addLayout(device_layout)

        # Active connections list
        connections_group = QGroupBox(tr("MIDIPatchBay", "Active Connections"))
        connections_layout = QVBoxLayout()
        connections_group.setLayout(connections_layout)
        main_layout.addWidget(connections_group)

        self.connections_list = QListWidget()
        self.connections_list.setMinimumHeight(150)
        self.connections_list.itemClicked.connect(self.on_connection_selected)
        connections_layout.addWidget(self.connections_list)

        disconnect_selected_btn = QPushButton(tr("MIDIPatchBay", "Disconnect Selected"))
        disconnect_selected_btn.clicked.connect(self.on_disconnect_selected)
        connections_layout.addWidget(disconnect_selected_btn)

        # Per-connection filter panel (hidden by default)
        self.filter_panel = QGroupBox()
        self.filter_panel.setVisible(False)
        filter_panel_layout = QVBoxLayout()
        self.filter_panel.setLayout(filter_panel_layout)
        main_layout.addWidget(self.filter_panel)

        filter_title = QLabel(tr("MIDIPatchBay", "Send to MIDIswitch"))
        filter_title.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        filter_panel_layout.addWidget(filter_title)

        # Create checkboxes for all message types (all checked by default = pass through)
        filter_types_layout1 = QHBoxLayout()
        self.filter_note = QCheckBox(tr("MIDIPatchBay", "Notes"))
        self.filter_cc = QCheckBox(tr("MIDIPatchBay", "CC"))
        self.filter_pc = QCheckBox(tr("MIDIPatchBay", "Program Change"))
        self.filter_pb = QCheckBox(tr("MIDIPatchBay", "Pitch Bend"))

        filter_types_layout1.addWidget(self.filter_note)
        filter_types_layout1.addWidget(self.filter_cc)
        filter_types_layout1.addWidget(self.filter_pc)
        filter_types_layout1.addWidget(self.filter_pb)
        filter_types_layout1.addStretch()
        filter_panel_layout.addLayout(filter_types_layout1)

        filter_types_layout2 = QHBoxLayout()
        self.filter_aftertouch = QCheckBox(tr("MIDIPatchBay", "Aftertouch"))
        self.filter_poly_aftertouch = QCheckBox(tr("MIDIPatchBay", "Poly Aftertouch"))
        self.filter_system = QCheckBox(tr("MIDIPatchBay", "System"))

        filter_types_layout2.addWidget(self.filter_aftertouch)
        filter_types_layout2.addWidget(self.filter_poly_aftertouch)
        filter_types_layout2.addWidget(self.filter_system)
        filter_types_layout2.addStretch()
        filter_panel_layout.addLayout(filter_types_layout2)

        # Connect checkboxes to update filters in real-time
        self.filter_note.stateChanged.connect(self.on_filter_changed)
        self.filter_cc.stateChanged.connect(self.on_filter_changed)
        self.filter_pc.stateChanged.connect(self.on_filter_changed)
        self.filter_pb.stateChanged.connect(self.on_filter_changed)
        self.filter_aftertouch.stateChanged.connect(self.on_filter_changed)
        self.filter_poly_aftertouch.stateChanged.connect(self.on_filter_changed)
        self.filter_system.stateChanged.connect(self.on_filter_changed)

        # Buttons
        self.addStretch()
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        refresh_btn = QPushButton(tr("MIDIPatchBay", "Refresh Devices"))
        refresh_btn.setMinimumHeight(35)
        refresh_btn.setMinimumWidth(150)
        refresh_btn.clicked.connect(self.refresh_devices)
        buttons_layout.addWidget(refresh_btn)

        disconnect_all_btn = QPushButton(tr("MIDIPatchBay", "Disconnect All"))
        disconnect_all_btn.setMinimumHeight(35)
        disconnect_all_btn.setMinimumWidth(150)
        disconnect_all_btn.clicked.connect(self.on_disconnect_all)
        buttons_layout.addWidget(disconnect_all_btn)

        self.addLayout(buttons_layout)

    def initialize_midi(self):
        """Initialize MIDI input/output"""
        try:
            self.midi_in = rtmidi.MidiIn()
            self.midi_out = rtmidi.MidiOut()
            self.refresh_devices()
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to initialize MIDI: {str(e)}")

    def refresh_devices(self):
        """Refresh MIDI device lists"""
        if not MIDI_AVAILABLE or not self.midi_in or not self.midi_out:
            return

        try:
            # Save current selection
            current_text = self.device_selector.currentText()

            # Get available input devices
            input_ports = self.midi_in.get_ports()

            # Find MIDIswitch output
            output_ports = self.midi_out.get_ports()
            self.midiswitch_output = None
            for i, port in enumerate(output_ports):
                if "midiswitch" in port.lower() or "curlton" in port.lower():
                    self.midiswitch_output = (i, port)
                    break

            # Update device selector (exclude MIDIswitch from inputs to prevent feedback)
            self.device_selector.clear()
            for i, port in enumerate(input_ports):
                if "midiswitch" not in port.lower() and "curlton" not in port.lower():
                    self.device_selector.addItem(port, i)

            # Restore selection if possible
            index = self.device_selector.findText(current_text)
            if index >= 0:
                self.device_selector.setCurrentIndex(index)

        except Exception as e:
            print(f"Error refreshing devices: {e}")

    def on_connect_device(self):
        """Connect selected MIDI input to MIDIswitch output"""
        if not self.midiswitch_output:
            return

        if self.device_selector.currentIndex() < 0:
            return

        input_port_idx = self.device_selector.currentData()
        input_port_name = self.device_selector.currentText()

        # Check if already connected
        if input_port_idx in self.active_connections:
            return

        try:
            # Create new MIDI input for this connection
            midi_in = rtmidi.MidiIn()
            midi_in.open_port(input_port_idx)

            # Create MIDI output for MIDIswitch
            midi_out = rtmidi.MidiOut()
            midi_out.open_port(self.midiswitch_output[0])

            # Initialize filters - all True by default (pass through everything)
            filters = {
                'note': True,
                'cc': True,
                'pc': True,
                'pb': True,
                'aftertouch': True,
                'poly_aftertouch': True,
                'system': True
            }

            # Create callback for MIDI message routing
            callback = self.create_callback(midi_out, filters)
            midi_in.set_callback(callback)

            # Store connection
            self.active_connections[input_port_idx] = {
                'input': midi_in,
                'output': midi_out,
                'name': input_port_name,
                'callback': callback,
                'filters': filters
            }

            # Update UI
            self.update_connections_list()

        except Exception as e:
            print(f"Failed to connect device: {e}")

    def create_callback(self, output, filters):
        """Create a MIDI callback that filters messages based on filter settings"""
        def callback(event, data=None):
            message, deltatime = event

            if len(message) == 0:
                return

            # Filter out SysEx to prevent feedback loops
            if message[0] == 0xF0:
                return

            status = message[0] & 0xF0

            # Check message type and filter accordingly
            # If checkbox is checked = pass through, if unchecked = block
            if status in [0x80, 0x90]:  # Note On/Off
                if not filters['note']:
                    return
            elif status == 0xB0:  # CC
                if not filters['cc']:
                    return
            elif status == 0xC0:  # Program Change
                if not filters['pc']:
                    return
            elif status == 0xE0:  # Pitch Bend
                if not filters['pb']:
                    return
            elif status == 0xD0:  # Aftertouch (Channel Pressure)
                if not filters['aftertouch']:
                    return
            elif status == 0xA0:  # Polyphonic Aftertouch
                if not filters['poly_aftertouch']:
                    return
            elif message[0] >= 0xF0:  # System messages (0xF8 = Clock, 0xFA = Start, etc.)
                if not filters['system']:
                    return

            # Forward message to MIDIswitch
            try:
                output.send_message(message)
            except:
                pass

        return callback

    def on_connection_selected(self, item):
        """Show filter panel for selected connection"""
        input_port_idx = item.data(QtCore.Qt.UserRole)

        if input_port_idx not in self.active_connections:
            return

        self.selected_connection_id = input_port_idx
        conn = self.active_connections[input_port_idx]
        filters = conn['filters']

        # Update checkboxes to match connection's filter settings
        self.filter_note.blockSignals(True)
        self.filter_cc.blockSignals(True)
        self.filter_pc.blockSignals(True)
        self.filter_pb.blockSignals(True)
        self.filter_aftertouch.blockSignals(True)
        self.filter_poly_aftertouch.blockSignals(True)
        self.filter_system.blockSignals(True)

        self.filter_note.setChecked(filters['note'])
        self.filter_cc.setChecked(filters['cc'])
        self.filter_pc.setChecked(filters['pc'])
        self.filter_pb.setChecked(filters['pb'])
        self.filter_aftertouch.setChecked(filters['aftertouch'])
        self.filter_poly_aftertouch.setChecked(filters['poly_aftertouch'])
        self.filter_system.setChecked(filters['system'])

        self.filter_note.blockSignals(False)
        self.filter_cc.blockSignals(False)
        self.filter_pc.blockSignals(False)
        self.filter_pb.blockSignals(False)
        self.filter_aftertouch.blockSignals(False)
        self.filter_poly_aftertouch.blockSignals(False)
        self.filter_system.blockSignals(False)

        # Show filter panel
        self.filter_panel.setVisible(True)

    def on_filter_changed(self):
        """Update filters in real-time when checkboxes change"""
        if self.selected_connection_id is None:
            return

        if self.selected_connection_id not in self.active_connections:
            return

        conn = self.active_connections[self.selected_connection_id]

        # Update filter settings
        conn['filters']['note'] = self.filter_note.isChecked()
        conn['filters']['cc'] = self.filter_cc.isChecked()
        conn['filters']['pc'] = self.filter_pc.isChecked()
        conn['filters']['pb'] = self.filter_pb.isChecked()
        conn['filters']['aftertouch'] = self.filter_aftertouch.isChecked()
        conn['filters']['poly_aftertouch'] = self.filter_poly_aftertouch.isChecked()
        conn['filters']['system'] = self.filter_system.isChecked()

        # Recreate callback with updated filters
        new_callback = self.create_callback(conn['output'], conn['filters'])
        conn['input'].set_callback(new_callback)
        conn['callback'] = new_callback

    def on_disconnect_selected(self):
        """Disconnect selected connection from list"""
        current_item = self.connections_list.currentItem()
        if not current_item:
            return

        # Extract port index from item data
        input_port_idx = current_item.data(QtCore.Qt.UserRole)
        self.disconnect_connection(input_port_idx)

    def disconnect_connection(self, input_port_idx):
        """Disconnect a specific connection"""
        if input_port_idx not in self.active_connections:
            return

        try:
            conn = self.active_connections[input_port_idx]

            # Close MIDI ports
            conn['input'].close_port()
            conn['output'].close_port()

            # Remove from active connections
            del self.active_connections[input_port_idx]

            # Hide filter panel if this was the selected connection
            if self.selected_connection_id == input_port_idx:
                self.filter_panel.setVisible(False)
                self.selected_connection_id = None

            # Update UI
            self.update_connections_list()

        except Exception as e:
            print(f"Failed to disconnect: {e}")

    def on_disconnect_all(self):
        """Disconnect all active connections"""
        port_indices = list(self.active_connections.keys())
        for port_idx in port_indices:
            self.disconnect_connection(port_idx)

        # Hide filter panel
        self.filter_panel.setVisible(False)
        self.selected_connection_id = None

    def update_connections_list(self):
        """Update the active connections list widget"""
        self.connections_list.clear()

        for port_idx, conn in self.active_connections.items():
            item_text = f"{conn['name']} → {self.midiswitch_output[1]}"
            item = QListWidgetItem(item_text)
            item.setData(QtCore.Qt.UserRole, port_idx)
            self.connections_list.addItem(item)

    def valid(self):
        """This tab is always valid for VialKeyboard devices"""
        return isinstance(self.device, VialKeyboard)

    def rebuild(self, device):
        super().rebuild(device)
        if not self.valid():
            return

        # Refresh devices when keyboard connects (only if MIDI available)
        if MIDI_AVAILABLE and hasattr(self, 'midi_in'):
            self.refresh_devices()

    def __del__(self):
        """Cleanup on deletion"""
        if hasattr(self, 'device_refresh_timer'):
            self.device_refresh_timer.stop()

        # Disconnect all connections
        if hasattr(self, 'active_connections'):
            port_indices = list(self.active_connections.keys())
            for port_idx in port_indices:
                try:
                    self.disconnect_connection(port_idx)
                except:
                    pass
