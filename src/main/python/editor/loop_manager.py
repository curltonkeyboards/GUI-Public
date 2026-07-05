# SPDX-License-Identifier: GPL-2.0-or-later
import struct
import os
import threading
import time
import logging
from datetime import datetime
from PyQt5 import QtCore
from PyQt5.QtCore import QTimer, pyqtSignal, QObject, QUrl
from PyQt5.QtGui import QDesktopServices, QPalette
from PyQt5.QtWidgets import (QWidget, QPushButton, QHBoxLayout, QVBoxLayout, QSizePolicy,
                             QLabel, QGroupBox, QFileDialog, QMessageBox, QProgressBar,
                             QListWidget, QListWidgetItem, QGridLayout, QCheckBox, QButtonGroup,
                             QRadioButton, QScrollArea, QFrame, QInputDialog, QApplication,
                             QTabWidget)

from editor.basic_editor import BasicEditor
from util import tr
from vial_device import VialKeyboard
import math

# The firmware looper has 8 loop slots (MAX_MACROS). "Save All Loops" and the
# file import/export paths must cover all 8 — several loops here were left at
# the old 4-slot bound, which silently dropped loops 5-8.
NUM_LOOPS = 8

# Setup logging to file for standalone builds
LOG_FILE = os.path.join(os.path.expanduser("~"), "vial-loop-manager.log")
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'),  # Overwrite each session
        logging.StreamHandler()  # Also print to console
    ]
)
logger = logging.getLogger(__name__)


class LoopManager(BasicEditor):
    """Loop Manager tab for uploading/downloading loops to/from MIDIswitch"""

    # HID Command constants - Updated to match webapp (0xA0-0xA9 range)
    # Save/Load Operations (0xA0-0xA7)
    HID_CMD_SAVE_START = 0xA0              # was 0x01
    HID_CMD_SAVE_CHUNK = 0xA1              # was 0x02
    HID_CMD_SAVE_END = 0xA2                # was 0x03
    HID_CMD_LOAD_START = 0xA3              # was 0x04
    HID_CMD_LOAD_CHUNK = 0xA4              # was 0x05
    HID_CMD_LOAD_END = 0xA5                # was 0x06
    HID_CMD_LOAD_OVERDUB_START = 0xA6      # was 0x07

    # Request/Trigger Operations (0xA8-0xAF)
    HID_CMD_REQUEST_SAVE = 0xA8            # was 0x10
    HID_CMD_TRIGGER_SAVE_ALL = 0xA9        # was 0x30

    HID_PACKET_SIZE = 32
    HID_HEADER_SIZE = 6
    HID_DATA_SIZE = HID_PACKET_SIZE - HID_HEADER_SIZE

    MANUFACTURER_ID = 0x7D
    SUB_ID = 0x00
    DEVICE_ID = 0x4D

    # Signals for thread-safe UI updates
    transfer_progress = pyqtSignal(int, str)  # progress, message
    transfer_complete = pyqtSignal(bool, str)  # success, message
    hid_data_received = pyqtSignal(bytes)  # raw HID data

    def __init__(self):
        super().__init__()

        # Log startup
        logger.info("="*60)
        logger.info("Loop Manager initialized")
        logger.info(f"Log file: {LOG_FILE}")
        logger.info("="*60)

        self.current_transfer = {
            'active': False,
            'is_loading': False,
            'loop_num': 0,
            'expected_packets': 0,
            'received_packets': 0,
            'total_size': 0,
            'received_data': bytearray(),
            'file_name': '',
            'save_format': 'loop',  # 'loop' or 'midi'
            'save_all_mode': False,
            'save_all_directory': '',
            'save_all_current': 0
        }

        self.loaded_files = {}  # Dict: filename -> {'tracks': [], 'bpm': 120}
        self.loop_contents = {}  # Track what's in each loop (1-4)
        self.overdub_contents = {}  # Track what's in each overdub (1-4)
        self.selected_track = None  # Currently selected track {file_idx, track_idx}
        self.pending_assignments = {}  # Track assignments pending load
        self.loop_content_labels = []  # UI labels for displaying loop contents

        self.hid_listener_thread = None
        self.hid_listening = False

        # Connect signals
        self.transfer_progress.connect(self.on_transfer_progress)
        self.transfer_complete.connect(self.on_transfer_complete)
        self.hid_data_received.connect(self.handle_device_response)

        self.setup_ui()

    def extract_bpm_from_loop_data(self, data):
        """Extract BPM from loop data - matches webapp extractBPMQuickly()"""
        logger.info(f"Extracting BPM from last 5 bytes of {len(data)} total bytes")

        if len(data) < 5:
            logger.info("Data too short for BPM, using default 120 BPM")
            return 120.0

        # Get last 5 bytes
        last_five = data[-5:]
        logger.info(f"Last 5 bytes: {' '.join(f'{b:02x}' for b in last_five)}")

        bpm_flag = last_five[0]
        logger.info(f"BPM flag byte: 0x{bpm_flag:02x} ({bpm_flag})")

        if bpm_flag != 0x01:
            logger.info("Flag indicates no BPM set, using default 120 BPM")
            return 120.0

        # Extract 3-byte BPM value (bytes 2, 3, 4 of the last 5 bytes)
        bpm_bytes = last_five[2:5]
        logger.info(f"BPM bytes: {' '.join(f'{b:02x}' for b in bpm_bytes)}")

        bpm_value = (bpm_bytes[0] << 16) | (bpm_bytes[1] << 8) | bpm_bytes[2]
        logger.info(f"Raw BPM value: {bpm_value}")

        bpm = bpm_value / 100000.0
        logger.info(f"Calculated BPM: {bpm}")

        # Round to 1 decimal place
        final_bpm = round(bpm * 10) / 10
        logger.info(f"Final BPM: {final_bpm}")

        return final_bpm

    def parse_loop_data(self, data):
        """Parse loop data file - matches webapp parseLoopData()"""
        logger.info(f"Parsing loop data: {len(data)} bytes")
        logger.info(f"First 20 bytes: {' '.join(f'{b:02x}' for b in data[:20])}")

        # Check header
        if len(data) < 4 or data[0] != 0xAA or data[1] != 0x55:
            logger.info("Invalid loop file header")
            return None

        version = data[2]
        loop_num = data[3]
        offset = 4

        logger.info(f"Loop {loop_num}, version {version}")

        # Read main macro size
        if offset + 2 > len(data):
            logger.info("Insufficient data for main size")
            return None

        main_size = (data[offset] << 8) | data[offset + 1]
        offset += 2
        logger.info(f"Main macro size: {main_size} bytes at offset {offset - 2}")

        # Parse main macro events
        main_events = []
        if main_size > 0:
            if offset + main_size > len(data):
                logger.info("Insufficient data for main events")
                return None

            main_data = data[offset:offset + main_size]
            main_events = self.parse_midi_events(main_data)
            offset += main_size

        logger.info(f"Found {len(main_events)} main events")

        # Read overdub size
        if offset + 2 > len(data):
            logger.info("Insufficient data for overdub size")
            return None

        overdub_size = (data[offset] << 8) | data[offset + 1]
        offset += 2
        logger.info(f"Overdub size: {overdub_size} bytes at offset {offset - 2}")

        # Parse overdub events
        overdub_events = []
        if overdub_size > 0:
            if offset + overdub_size > len(data):
                logger.info("Insufficient data for overdub events")
                return None

            overdub_data = data[offset:offset + overdub_size]
            overdub_events = self.parse_midi_events(overdub_data)
            offset += overdub_size

        logger.info(f"Found {len(overdub_events)} overdub events")

        # Skip transformation data (7 bytes)
        if offset + 7 <= len(data):
            offset += 7
            logger.info("Skipped 7 bytes of transformation settings")

        # Extract timing info (8 bytes: 4 for loop_length, 4 for loop_gap)
        loop_length = 0
        loop_gap = 0
        if offset + 8 <= len(data):
            loop_length = (data[offset] << 24) | (data[offset + 1] << 16) | \
                         (data[offset + 2] << 8) | data[offset + 3]
            offset += 4

            loop_gap = (data[offset] << 24) | (data[offset + 1] << 16) | \
                      (data[offset + 2] << 8) | data[offset + 3]
            offset += 4

            logger.info(f"Loop length: {loop_length}ms, gap: {loop_gap}ms")

        # Extract BPM
        bpm = self.extract_bpm_from_loop_data(data)

        return {
            'loopNum': loop_num,
            'mainEvents': main_events,
            'overdubEvents': overdub_events,
            'loopLength': loop_length,
            'loopGap': loop_gap,
            'bpm': bpm
        }

    def parse_midi_events(self, data):
        """Parse MIDI events from loop data - adaptive event size detection (8, 12, or 16 bytes)"""
        logger.info(f"Parsing {len(data)} bytes of event data")

        # Try each possible event size and score the results
        candidate_sizes = [8, 12, 16]
        best_result = None
        best_score = -1

        for event_size in candidate_sizes:
            candidate_events = []
            valid_events = 0
            invalid_events = 0
            last_timestamp = 0
            timestamp_increases = 0
            timestamp_decreases = 0

            logger.info(f"Trying event_size={event_size}")

            offset = 0
            while offset + event_size <= len(data):
                event_type = data[offset]
                channel = data[offset + 1]
                note = data[offset + 2]
                velocity = data[offset + 3]

                # Read timestamp (4 bytes, little-endian) - handle as signed 32-bit
                timestamp = (data[offset + 4]) | (data[offset + 5] << 8) | \
                           (data[offset + 6] << 16) | (data[offset + 7] << 24)

                # Convert to signed 32-bit integer
                if timestamp > 0x7FFFFFFF:
                    timestamp = timestamp - 0x100000000

                # Handle negative timestamps (preroll) - clamp to 1ms
                if timestamp < 0:
                    logger.info(f"PREROLL: Found negative timestamp {timestamp}ms, clamping to 1ms")
                    timestamp = 1

                # Skip completely empty events (all zeros)
                if event_type == 0 and channel == 0 and note == 0 and velocity == 0 and timestamp == 0:
                    offset += event_size
                    continue

                # Check if this looks like a valid MIDI event
                # Note: firmware stores raw_travel (0-255) in the velocity field, not MIDI velocity (0-127)
                # velocity_to_storage() scales MIDI vel 1-127 → 0-255 for loop playback curve processing
                is_valid_type = (event_type >= 0 and event_type <= 2)  # NOTE_OFF, NOTE_ON, CC
                is_valid_channel = (channel >= 0 and channel <= 15)
                is_valid_note = (note >= 0 and note <= 127)
                is_valid_velocity = (velocity >= 0 and velocity <= 255)  # raw_travel range is 0-255
                is_reasonable_timestamp = (timestamp >= 0 and timestamp < 600000)  # Less than 10 minutes

                if is_valid_type and is_valid_channel and is_valid_note and is_valid_velocity and is_reasonable_timestamp:
                    candidate_events.append({
                        'type': event_type,
                        'channel': channel,
                        'note': note,
                        'velocity': velocity,
                        'timestamp': timestamp
                    })
                    valid_events += 1

                    # Track timestamp ordering (should generally increase)
                    if timestamp >= last_timestamp:
                        timestamp_increases += 1
                    else:
                        timestamp_decreases += 1
                    last_timestamp = timestamp
                else:
                    invalid_events += 1

                offset += event_size

            # Score this attempt
            note_ons = sum(1 for e in candidate_events if e['type'] == 1)
            note_offs = sum(1 for e in candidate_events if e['type'] == 0)
            has_balanced_events = min(note_ons, note_offs) > 0

            score = (valid_events * 100
                    - invalid_events * 50
                    + timestamp_increases * 10
                    - timestamp_decreases * 20
                    + (500 if has_balanced_events else 0))

            logger.info(f"event_size={event_size}, valid={valid_events}, invalid={invalid_events}, "
                       f"note_ons={note_ons}, note_offs={note_offs}, score={score}")

            if score > best_score:
                best_score = score
                best_result = {
                    'event_size': event_size,
                    'events': candidate_events,
                    'note_ons': note_ons,
                    'note_offs': note_offs
                }

        if best_result:
            logger.info(f"Selected event_size={best_result['event_size']} with {len(best_result['events'])} events "
                       f"({best_result['note_ons']} note-ons, {best_result['note_offs']} note-offs)")

            # Sort events by timestamp
            best_result['events'].sort(key=lambda e: e['timestamp'])

            if len(best_result['events']) > 0:
                logger.info(f"Timestamp range: {best_result['events'][0]['timestamp']}ms to "
                           f"{best_result['events'][-1]['timestamp']}ms")

                # Log first few events for debugging
                for i in range(min(5, len(best_result['events']))):
                    e = best_result['events'][i]
                    type_str = 'NOTE_ON' if e['type'] == 1 else 'NOTE_OFF' if e['type'] == 0 else 'CC'
                    logger.info(f"Event {i+1}: {type_str} ch={e['channel']} note={e['note']} "
                               f"vel={e['velocity']} time={e['timestamp']}ms")

            return best_result['events']

        logger.info("No valid events found with any event size")
        return []

    def find_shortest_track_length(self, tracks, bpm, tpqn):
        """Find the shortest track length for sync reference"""
        if len(tracks) <= 1:
            logger.info(f"Only {len(tracks)} track(s), skipping synchronization")
            return None

        track_lengths = [track.get('loopLength', 0) for track in tracks]
        shortest_ms = min([length for length in track_lengths if length > 0], default=0)

        if shortest_ms == 0:
            return None

        shortest_ticks = self.ms_to_ticks(shortest_ms, bpm, tpqn)
        logger.info(f"SYNC: Shortest track reference: {shortest_ms}ms ({shortest_ticks} ticks)")

        return {'ms': shortest_ms, 'ticks': shortest_ticks}

    def find_sync_target(self, track_ms, shortest_ms, threshold_ms):
        """Find the closest multiple of the shortest track that's within threshold"""
        # Calculate which multiple we're closest to
        exact_multiple = track_ms / shortest_ms
        lower_multiple = int(exact_multiple)
        upper_multiple = int(exact_multiple) + 1

        # Check both possibilities
        lower_target = lower_multiple * shortest_ms
        upper_target = upper_multiple * shortest_ms

        lower_diff = abs(track_ms - lower_target)
        upper_diff = abs(track_ms - upper_target)

        # Choose the closest one that's within threshold
        if lower_diff <= threshold_ms and upper_diff <= threshold_ms:
            # Both are within threshold, choose the closest
            return lower_target if lower_diff <= upper_diff else upper_target
        elif lower_diff <= threshold_ms:
            return lower_target
        elif upper_diff <= threshold_ms:
            return upper_target
        else:
            # Neither is within threshold, don't adjust
            return track_ms

    def convert_loop_to_midi(self, loops_data, bpm):
        """Convert loop data to MIDI file bytes - matches webapp createMIDIFile()"""
        logger.info(f"Creating MIDI file at {bpm} BPM")
        logger.info(f"Converting {len(loops_data)} loops to MIDI")

        # MIDI constants
        MIDI_TPQN = 480  # Ticks per quarter note

        # Collect all tracks
        tracks = []
        for loop_num in range(1, NUM_LOOPS + 1):
            if loop_num not in loops_data:
                continue

            loop_data = loops_data[loop_num]
            logger.info(f"Loop {loop_num}: {len(loop_data['mainEvents'])} main events, {len(loop_data['overdubEvents'])} overdub events")

            # Filter out invalid event types (only 0, 1, 2 are valid)
            valid_main_events = [e for e in loop_data['mainEvents'] if e['type'] in [0, 1, 2]]
            if len(valid_main_events) < len(loop_data['mainEvents']):
                logger.info(f"  Filtered {len(loop_data['mainEvents']) - len(valid_main_events)} invalid main events")

            if valid_main_events:
                track_dict = {
                    'name': f'Loop {loop_num} Main',
                    'events': valid_main_events,
                    'loopLength': loop_data.get('loopLength', 0),
                    'loopGap': loop_data.get('loopGap', 0)
                }
                tracks.append(track_dict)
                logger.info(f"Added main track for loop {loop_num} with {len(valid_main_events)} events")
                # Log first event for debugging
                first_event = valid_main_events[0]
                logger.info(f"  First event: type={first_event['type']} ch={first_event['channel']} note={first_event['note']} vel={first_event['velocity']} @{first_event['timestamp']}ms")

            # Filter overdub events too
            valid_overdub_events = [e for e in loop_data['overdubEvents'] if e['type'] in [0, 1, 2]]
            if len(valid_overdub_events) < len(loop_data['overdubEvents']):
                logger.info(f"  Filtered {len(loop_data['overdubEvents']) - len(valid_overdub_events)} invalid overdub events")

            if valid_overdub_events:
                tracks.append({
                    'name': f'Loop {loop_num} Overdub',
                    'events': valid_overdub_events,
                    'loopLength': loop_data.get('loopLength', 0),
                    'loopGap': loop_data.get('loopGap', 0)
                })
                logger.info(f"Added overdub track for loop {loop_num} with {len(valid_overdub_events)} events")

        if not tracks:
            logger.info("No tracks to save")
            return None

        logger.info(f"Creating MIDI with {len(tracks)} tracks")

        # Find shortest track for sync reference
        shortest_track_ref = self.find_shortest_track_length(tracks, bpm, MIDI_TPQN)

        # Create MIDI file
        midi_data = bytearray()

        # MIDI Header
        midi_data.extend(self.create_midi_header(len(tracks), MIDI_TPQN))

        # Create each track with sync info
        for track in tracks:
            track_data = self.create_midi_track(track, bpm, MIDI_TPQN, shortest_track_ref)
            midi_data.extend(track_data)

        return bytes(midi_data)

    def create_midi_header(self, track_count, tpqn):
        """Create MIDI file header"""
        header = bytearray()

        # "MThd" chunk
        header.extend(b'MThd')

        # Header length (always 6 bytes)
        header.extend(struct.pack('>I', 6))

        # Format type (1 = multiple tracks, synchronous)
        header.extend(struct.pack('>H', 1))

        # Number of tracks
        header.extend(struct.pack('>H', track_count))

        # Time division (TPQN)
        header.extend(struct.pack('>H', tpqn))

        return header

    def create_midi_track(self, track, bpm, tpqn, shortest_track_ref=None):
        """Create a MIDI track from events with loopLength silence and sync adjustment"""
        track_events = bytearray()

        # Track name event
        track_name = track['name'].encode('utf-8')
        logger.info(f"Creating track '{track['name']}' with {len(track['events'])} events")
        track_events.extend(self.create_variable_length(0))  # Delta time 0
        track_events.extend(bytes([0xFF, 0x03]))  # Track name meta event
        track_events.extend(self.create_variable_length(len(track_name)))  # Length as variable-length
        track_events.extend(track_name)
        logger.info(f"Track name: {len(track_name)} bytes")

        # Tempo event (only in first track typically, but let's add to all)
        microseconds_per_quarter = int(60000000 / bpm)
        tempo_bytes = struct.pack('>I', microseconds_per_quarter)[1:]  # 3 bytes
        track_events.extend(self.create_variable_length(0))  # Delta time 0
        track_events.extend(bytes([0xFF, 0x51]))  # Tempo meta event
        track_events.extend(self.create_variable_length(len(tempo_bytes)))  # Length as variable-length
        track_events.extend(tempo_bytes)

        # Sort events by timestamp
        sorted_events = sorted(track['events'], key=lambda e: e['timestamp'])
        logger.info(f"Sorted {len(sorted_events)} events by timestamp")

        # Filter out invalid event types (only 0, 1, 2 are valid)
        valid_events = [e for e in sorted_events if e['type'] in [0, 1, 2]]
        if len(valid_events) < len(sorted_events):
            logger.info(f"Filtered out {len(sorted_events) - len(valid_events)} invalid events (types not in [0,1,2])")
            # Log the invalid events for debugging
            invalid_events = [e for e in sorted_events if e['type'] not in [0, 1, 2]]
            for inv_evt in invalid_events[:3]:  # Log first 3 invalid events
                logger.info(f"  Invalid event: type={inv_evt['type']} ch={inv_evt['channel']} note={inv_evt['note']} vel={inv_evt['velocity']} @{inv_evt['timestamp']}ms")

        # Convert events to MIDI
        last_time_ticks = 0
        for idx, event in enumerate(valid_events):
            # Convert milliseconds to ticks
            time_ms = event['timestamp']
            ms_per_tick = 60000.0 / (bpm * tpqn)
            time_ticks = int(round(time_ms / ms_per_tick))

            # Delta time
            delta_ticks = time_ticks - last_time_ticks
            track_events.extend(self.create_variable_length(delta_ticks))
            last_time_ticks = time_ticks

            # MIDI event - device event types: 0=Note Off, 1=Note On, 2=CC
            event_type = event['type']
            channel = event['channel']
            note = event['note']
            raw_travel = event['velocity']  # Firmware stores raw_travel (0-255), not MIDI velocity

            # Scale raw_travel (0-255) back to MIDI velocity (1-127) for note events
            # Firmware uses velocity_to_storage(): ((midi_vel - 1) * 255) / 126
            # Reverse: midi_vel = (raw_travel * 126 / 255) + 1, clamped to 1-127
            if event_type in [0, 1]:  # Note On or Note Off
                midi_velocity = max(1, min(127, int(round(raw_travel * 126.0 / 255.0) + 1)))
            else:
                # CC values are stored as-is (0-127) in firmware
                midi_velocity = min(127, raw_travel)

            if event_type == 1:  # Note On (device type 1)
                status = 0x90 | (channel & 0x0F)
                track_events.extend(bytes([status, note, midi_velocity]))
                if idx < 3:  # Log first 3 events
                    logger.info(f"Event {idx}: NoteOn ch={channel} note={note} raw_travel={raw_travel} midi_vel={midi_velocity} @{time_ms}ms ({time_ticks} ticks)")
            elif event_type == 0:  # Note Off (device type 0)
                status = 0x80 | (channel & 0x0F)
                track_events.extend(bytes([status, note, midi_velocity]))
                if idx < 3:
                    logger.info(f"Event {idx}: NoteOff ch={channel} note={note} raw_travel={raw_travel} midi_vel={midi_velocity} @{time_ms}ms ({time_ticks} ticks)")
            elif event_type == 2:  # Control Change (device type 2)
                status = 0xB0 | (channel & 0x0F)
                track_events.extend(bytes([status, note, midi_velocity]))
                if idx < 3:
                    logger.info(f"Event {idx}: CC ch={channel} cc={note} val={midi_velocity} @{time_ms}ms ({time_ticks} ticks)")

        # Calculate end-of-track delta (silence to reach loopLength)
        end_track_delta = 0
        loop_length = track.get('loopLength', 0)

        if loop_length and loop_length > 0 and loop_length < 600000:
            loop_length_ticks = self.ms_to_ticks(loop_length, bpm, tpqn)
            if loop_length_ticks > last_time_ticks:
                end_track_delta = loop_length_ticks - last_time_ticks
                logger.info(f"TRACK: Will add {end_track_delta} ticks of silence before end of track ({loop_length}ms)")
            else:
                logger.info(f"TRACK: No silence needed - events already fill loop length")
        else:
            logger.info(f"TRACK: No valid loopLength specified ({loop_length}ms)")

        # Apply sync adjustment if we have a reference and this isn't the shortest track
        if shortest_track_ref and loop_length != shortest_track_ref['ms']:
            current_final_length_ticks = last_time_ticks + end_track_delta
            current_final_length_ms = self.ticks_to_ms(current_final_length_ticks, bpm, tpqn)

            # Calculate sync target
            sync_target = self.find_sync_target(current_final_length_ms, shortest_track_ref['ms'],
                                               shortest_track_ref['ms'] * 0.1)

            if sync_target != current_final_length_ms:
                sync_target_ticks = self.ms_to_ticks(sync_target, bpm, tpqn)
                adjustment = sync_target_ticks - current_final_length_ticks
                adjustment_ms = sync_target - current_final_length_ms

                # Apply the adjustment to end_track_delta
                original_delta = end_track_delta
                end_track_delta += adjustment

                # Ensure we don't go negative
                if end_track_delta < 0:
                    logger.info(f"SYNC: Track '{track['name']}': Sync adjustment would create negative delta "
                               f"({end_track_delta}), clamping to 0")
                    end_track_delta = 0

                action = 'Adding' if adjustment > 0 else 'Removing'
                logger.info(f"SYNC: Track '{track['name']}': {current_final_length_ms}ms → {sync_target}ms "
                           f"({action} {abs(adjustment_ms)}ms)")
                logger.info(f"SYNC: Track '{track['name']}': {action} {abs(adjustment)} ticks for synchronization")
                logger.info(f"SYNC: Track '{track['name']}': Final delta: {original_delta} → {end_track_delta} ticks")
            else:
                logger.info(f"SYNC: Track '{track['name']}': {current_final_length_ms}ms (no adjustment needed)")

        # End of track (with silence incorporated into the delta time)
        track_events.extend(self.create_variable_length(end_track_delta))
        track_events.extend(bytes([0xFF, 0x2F, 0x00]))

        # Create track chunk
        track_chunk = bytearray()
        track_chunk.extend(b'MTrk')
        track_chunk.extend(struct.pack('>I', len(track_events)))
        track_chunk.extend(track_events)

        logger.info(f"Created track chunk: {len(track_events)} bytes of track data, {len(track_chunk)} bytes total")
        logger.info(f"First 40 bytes of track chunk: {' '.join(f'{b:02x}' for b in track_chunk[:40])}")

        return track_chunk

    def create_variable_length(self, value):
        """Create MIDI variable-length quantity"""
        result = bytearray()

        result.append(value & 0x7F)
        value >>= 7

        while value > 0:
            result.insert(0, (value & 0x7F) | 0x80)
            value >>= 7

        return result

    def read_variable_length(self, data, offset):
        """Read MIDI variable-length quantity - matches webapp readVarLength()"""
        value = 0
        while offset < len(data):
            byte = data[offset]
            offset += 1
            value = (value << 7) | (byte & 0x7F)
            if (byte & 0x80) == 0:
                break
        return {'value': value, 'offset': offset}

    def ticks_to_ms(self, ticks, bpm, tpqn=480):
        """Convert MIDI ticks to milliseconds - matches webapp ticksToMs()"""
        ms_per_tick = 60000.0 / (bpm * tpqn)
        return int(round(ticks * ms_per_tick))

    def ms_to_ticks(self, ms, bpm, tpqn=480):
        """Convert milliseconds to MIDI ticks - matches webapp msToTicks()"""
        ms_per_tick = 60000.0 / (bpm * tpqn)
        return int(round(ms / ms_per_tick))

    def parse_midi_track(self, data, tpqn):
        """Parse MIDI track events - matches webapp parseMIDITrack()"""
        # Device event type constants - MUST MATCH DEVICE FORMAT!
        MIDI_EVENT_NOTE_OFF = 0
        MIDI_EVENT_NOTE_ON = 1
        MIDI_EVENT_CC = 2

        events = []
        offset = 0
        current_ticks = 0
        track_name = None
        tempo = None
        max_ticks = 0

        logger.info(f"Parsing MIDI track: {len(data)} bytes, TPQN={tpqn}")

        while offset < len(data):
            # Read delta time
            delta_result = self.read_variable_length(data, offset)
            delta_time = delta_result['value']
            offset = delta_result['offset']

            current_ticks += delta_time
            max_ticks = max(max_ticks, current_ticks)

            if offset >= len(data):
                break

            event_byte = data[offset]
            offset += 1

            # Debug logging for first few events
            if len(events) < 5 or offset < 100:
                logger.info(f"Offset {offset-1}: delta={delta_time}, ticks={current_ticks}, byte=0x{event_byte:02x}")

            if event_byte == 0xFF:
                # Meta event
                if offset >= len(data):
                    break
                meta_type = data[offset]
                offset += 1

                length_result = self.read_variable_length(data, offset)
                meta_length = length_result['value']
                offset = length_result['offset']

                if offset + meta_length > len(data):
                    break

                if meta_type == 0x03 and not track_name:
                    # Track name
                    try:
                        track_name = data[offset:offset + meta_length].decode('utf-8', errors='ignore')
                    except:
                        track_name = None
                elif meta_type == 0x51 and meta_length == 3:
                    # Tempo
                    microseconds_per_quarter = (data[offset] << 16) | (data[offset + 1] << 8) | data[offset + 2]
                    tempo = round(60000000 / microseconds_per_quarter)
                elif meta_type == 0x2F:
                    # End of track
                    max_ticks = max(max_ticks, current_ticks)

                offset += meta_length

            elif (event_byte & 0xF0) == 0x90:
                # Note on
                if offset + 2 > len(data):
                    break
                channel = event_byte & 0x0F
                note = data[offset]
                velocity = data[offset + 1]
                offset += 2

                if velocity > 0:
                    events.append({
                        'type': MIDI_EVENT_NOTE_ON,
                        'channel': channel,
                        'note': note,
                        'velocity': velocity,
                        'ticks': current_ticks
                    })
                else:
                    # Note on with velocity 0 = note off
                    events.append({
                        'type': MIDI_EVENT_NOTE_OFF,
                        'channel': channel,
                        'note': note,
                        'velocity': 64,
                        'ticks': current_ticks
                    })

            elif (event_byte & 0xF0) == 0x80:
                # Note off
                if offset + 2 > len(data):
                    break
                channel = event_byte & 0x0F
                note = data[offset]
                velocity = data[offset + 1]
                offset += 2

                events.append({
                    'type': MIDI_EVENT_NOTE_OFF,
                    'channel': channel,
                    'note': note,
                    'velocity': velocity,
                    'ticks': current_ticks
                })

            elif (event_byte & 0xF0) == 0xB0:
                # Control change
                if offset + 2 > len(data):
                    break
                channel = event_byte & 0x0F
                controller = data[offset]
                value = data[offset + 1]
                offset += 2

                events.append({
                    'type': MIDI_EVENT_CC,
                    'channel': channel,
                    'note': controller,
                    'velocity': value,
                    'ticks': current_ticks
                })

            elif (event_byte & 0xF0) in [0xC0, 0xD0]:
                # Program change (0xC0) or Channel pressure (0xD0) - 1 data byte
                if offset + 1 > len(data):
                    break
                offset += 1  # Skip the data byte

            elif (event_byte & 0xF0) == 0xE0:
                # Pitch bend - 2 data bytes
                if offset + 2 > len(data):
                    break
                offset += 2  # Skip the data bytes

            elif event_byte == 0xF0 or event_byte == 0xF7:
                # SysEx event - skip it
                length_result = self.read_variable_length(data, offset)
                sysex_length = length_result['value']
                offset = length_result['offset']
                offset += sysex_length

            else:
                # Unknown event type - try to continue instead of breaking
                logger.info(f"Unknown event type: 0x{event_byte:02x} at offset {offset - 1}, breaking")
                break

        logger.info(f"Parsed MIDI track: {len(events)} events, max_ticks={max_ticks}, tempo={tempo}")
        return {'events': events, 'tempo': tempo, 'trackName': track_name, 'maxTicks': max_ticks}

    def convert_midi_to_loop_format(self, events, bpm, tpqn=480):
        """Convert MIDI events to loop format - matches webapp convertMIDIToLoopFormat()"""
        logger.info(f"Converting {len(events)} MIDI events to loop format at {bpm} BPM")

        loop_events = []
        for event in events:
            loop_events.append({
                'type': event['type'],
                'channel': event['channel'],
                'note': event['note'],
                'velocity': event['velocity'],
                'timestamp': self.ticks_to_ms(event['ticks'], bpm, tpqn)
            })

        # Sort by timestamp
        loop_events.sort(key=lambda e: e['timestamp'])

        logger.info(f"Converted to {len(loop_events)} loop events")
        if loop_events:
            logger.info(f"Event range: {loop_events[0]['timestamp']}ms to {loop_events[-1]['timestamp']}ms")

        return loop_events

    def calculate_loop_timing(self, events, bpm, track_length_ticks=None, skip_quantization=False):
        """Calculate loop timing from events - matches webapp calculateLoopTiming()"""
        if not events:
            return {'loopLength': 0, 'loopGap': 0}

        # Get timestamps
        timestamps = [e['timestamp'] for e in events]
        first_event_time = min(timestamps)
        last_event_time = max(timestamps)

        # Calculate basic loop length
        loop_length = last_event_time

        # If we have track length info from MIDI, use it
        if track_length_ticks:
            track_length_ms = self.ticks_to_ms(track_length_ticks, bpm)
            loop_length = max(loop_length, track_length_ms)
            logger.info(f"Using track length: {track_length_ms}ms vs event range: {last_event_time}ms")

        # Skip quantization for shortest loop (reference loop)
        if skip_quantization:
            logger.info(f"SHORTEST LOOP: Preserving exact timing: {loop_length}ms (no quantization)")
        else:
            # Smart quantization to bar boundaries
            ms_per_beat = 60000 / bpm
            ms_per_bar = ms_per_beat * 4  # 4/4 time
            threshold = ms_per_bar * 0.05  # 5% of a bar

            # Find closest multiple of bar length
            exact_bars = loop_length / ms_per_bar
            nearest_bars = round(exact_bars)
            quantized_length = nearest_bars * ms_per_bar

            # Calculate difference
            difference = abs(loop_length - quantized_length)

            # Only apply quantization if within 5% of bar boundary
            if difference <= threshold and nearest_bars > 0:
                loop_length = quantized_length
                logger.info(f"Quantized loop length to {nearest_bars} bars: {loop_length}ms")
            else:
                logger.info(f"No quantization applied: {difference}ms difference > {threshold}ms threshold")

        # Calculate gap (silence at end)
        loop_gap = max(0, loop_length - last_event_time)

        logger.info(f"Calculated timing - Length: {loop_length}ms, Gap: {loop_gap}ms")

        return {'loopLength': int(loop_length), 'loopGap': int(loop_gap)}

    def create_loop_data_from_events(self, events, loop_num, bpm, loop_timing=None, is_overdub=False):
        """Create loop data from events - matches webapp createLoopDataFromEvents()"""
        logger.info(f"Creating loop data for loop {loop_num} with {len(events)} events at {bpm} BPM (overdub: {is_overdub})")

        buffer = bytearray()

        # Header: AA 55 01 <loop_num>
        buffer.extend([0xAA, 0x55, 0x01, loop_num])

        # Convert events to binary format (8 bytes per event to match device midi_event_t structure)
        event_data = bytearray()
        for event in events:
            # Each event: type(1) + channel(1) + note(1) + raw_travel(1) + timestamp(4 LE) = 8 bytes total
            # Matches firmware typedef struct { uint8_t type; uint8_t channel; uint8_t note; uint8_t raw_travel; uint32_t timestamp; }
            event_data.append(event['type'])
            event_data.append(event['channel'])
            event_data.append(event['note'])

            # Scale MIDI velocity (0-127) to raw_travel (0-255) for firmware
            # Matches firmware velocity_to_storage(): ((midi_vel - 1) * 255) / 126
            velocity = event['velocity']
            if event['type'] in [0, 1]:  # Note On or Note Off
                if velocity <= 0:
                    raw_travel = 0
                else:
                    raw_travel = min(255, int((max(1, velocity) - 1) * 255 / 126))
            else:
                # CC values are stored as-is (0-127)
                raw_travel = min(127, velocity)
            event_data.append(raw_travel)

            # Timestamp as 32-bit little-endian
            timestamp = int(event['timestamp'])
            event_data.append(timestamp & 0xFF)
            event_data.append((timestamp >> 8) & 0xFF)
            event_data.append((timestamp >> 16) & 0xFF)
            event_data.append((timestamp >> 24) & 0xFF)

            # No padding - firmware expects 8-byte events

        # Main macro size (2 bytes, big-endian)
        if not is_overdub:
            main_size = len(event_data)
            buffer.append((main_size >> 8) & 0xFF)
            buffer.append(main_size & 0xFF)
            buffer.extend(event_data)

            # Overdub size (0)
            buffer.extend([0x00, 0x00])
        else:
            # Main size (0)
            buffer.extend([0x00, 0x00])

            # Overdub size
            overdub_size = len(event_data)
            buffer.append((overdub_size >> 8) & 0xFF)
            buffer.append(overdub_size & 0xFF)
            buffer.extend(event_data)

        # Transformation data (7 bytes)
        buffer.extend([0] * 7)

        # Timing info (8 bytes: 4 for loop_length, 4 for loop_gap)
        if loop_timing:
            loop_length = loop_timing['loopLength']
            loop_gap = loop_timing['loopGap']
        else:
            loop_length = 0
            loop_gap = 0

        # Loop length (4 bytes, big-endian)
        buffer.append((loop_length >> 24) & 0xFF)
        buffer.append((loop_length >> 16) & 0xFF)
        buffer.append((loop_length >> 8) & 0xFF)
        buffer.append(loop_length & 0xFF)

        # Loop gap (4 bytes, big-endian)
        buffer.append((loop_gap >> 24) & 0xFF)
        buffer.append((loop_gap >> 16) & 0xFF)
        buffer.append((loop_gap >> 8) & 0xFF)
        buffer.append(loop_gap & 0xFF)

        # BPM data (5 bytes: flag + reserved + 3-byte BPM value)
        buffer.append(0x01)  # BPM flag
        buffer.append(0x00)  # Reserved

        # BPM as 3-byte value (scaled by 100000)
        bpm_value = int(bpm * 100000)
        buffer.append((bpm_value >> 16) & 0xFF)
        buffer.append((bpm_value >> 8) & 0xFF)
        buffer.append(bpm_value & 0xFF)

        logger.info(f"Created loop data: {len(buffer)} bytes total")
        return bytes(buffer)

    def setup_ui(self):
        # No stretch at top - goes directly to content

        # Create scrollable main widget
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 5, 10, 10)  # Reduce top margin
        main_widget.setLayout(main_layout)
        scroll.setWidget(main_widget)

        # Create tab widget
        self.tabs = QTabWidget()

        # Tab 1: Loop Control (existing content)
        self.tabs.addTab(scroll, "Loop Control")

        # Tab 2: ThruLoop
        from editor.matrix_test import ThruLoopConfigurator
        self.thruloop_tab = ThruLoopConfigurator()
        thruloop_container = QWidget()
        thruloop_container.setLayout(self.thruloop_tab)
        self.tabs.addTab(thruloop_container, "ThruLoop")

        self.addWidget(self.tabs)

        # Title
        title = QLabel(tr("LoopManager", "Loop Manager"))
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        title.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(title)

        # Description
        desc_label = QLabel(tr("LoopManager",
            "Save and load loop recordings to/from your device. Save loops as .loop files for backup,\n"
            "or export as MIDI files. Load loops from files and assign tracks to loop slots."))
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; font-size: 9pt;")
        desc_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(desc_label)

        # Main container with two columns
        columns_layout = QHBoxLayout()
        main_layout.addLayout(columns_layout)

        # Add stretch to push boxes together in center
        columns_layout.addStretch()

        # === SAVE SECTION (Left Column) ===
        save_group = QGroupBox(tr("LoopManager", "Save from Device"))
        save_layout = QVBoxLayout()
        save_group.setLayout(save_layout)
        save_group.setMaximumWidth(500)
        columns_layout.addWidget(save_group)

        # Save All Loops button (use theme colors)
        save_all_btn = QPushButton(tr("LoopManager", "Save All Loops"))
        save_all_btn.setMinimumHeight(45)
        save_all_btn.clicked.connect(self.on_save_all_loops)
        save_layout.addWidget(save_all_btn)

        # Clear All Loops button
        clear_all_btn = QPushButton(tr("LoopManager", "Clear All Loops"))
        clear_all_btn.setMinimumHeight(45)
        clear_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #c0392b;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e74c3c;
            }
            QPushButton:pressed {
                background-color: #922b21;
            }
        """)
        clear_all_btn.clicked.connect(self.on_clear_all_loops)
        save_layout.addWidget(clear_all_btn)

        save_layout.addWidget(QLabel(tr("LoopManager", "Save individual loops:")))

        # Individual loop save buttons (8 in two rows)
        loop_buttons_layout = QGridLayout()
        self.save_loop_btns = []
        for i in range(8):
            btn = QPushButton(tr("LoopManager", f"Loop {i+1}"))
            btn.setMinimumHeight(35)
            btn.clicked.connect(lambda checked, loop=i+1: self.on_save_loop(loop))
            loop_buttons_layout.addWidget(btn, i // 4, i % 4)
            self.save_loop_btns.append(btn)

        save_layout.addLayout(loop_buttons_layout)

        # Save format selection
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel(tr("LoopManager", "Save as:")))
        self.format_group = QButtonGroup(self)
        self.format_loop_radio = QRadioButton(tr("LoopManager", ".loop file"))
        self.format_midi_radio = QRadioButton(tr("LoopManager", "MIDI file"))
        self.format_loop_radio.setChecked(True)
        self.format_group.addButton(self.format_loop_radio)
        self.format_group.addButton(self.format_midi_radio)
        format_layout.addWidget(self.format_loop_radio)
        format_layout.addWidget(self.format_midi_radio)
        format_layout.addStretch()
        save_layout.addLayout(format_layout)

        # Save progress
        self.save_progress_label = QLabel("")
        save_layout.addWidget(self.save_progress_label)

        self.save_progress_bar = QProgressBar()
        self.save_progress_bar.setMinimum(0)
        self.save_progress_bar.setMaximum(100)
        self.save_progress_bar.setValue(0)
        self.save_progress_bar.setVisible(False)
        save_layout.addWidget(self.save_progress_bar)

        # Log file button
        log_button_layout = QHBoxLayout()
        self.view_log_btn = QPushButton(tr("LoopManager", "📋 View Debug Log"))
        self.view_log_btn.setMaximumWidth(200)
        self.view_log_btn.clicked.connect(self.on_view_log)
        log_button_layout.addWidget(self.view_log_btn)
        log_button_layout.addStretch()
        save_layout.addLayout(log_button_layout)

        save_layout.addStretch()

        # === LOAD SECTION (Right Column) ===
        load_group = QGroupBox(tr("LoopManager", "Load to Device"))
        load_layout = QVBoxLayout()
        load_group.setLayout(load_layout)
        load_group.setMaximumWidth(500)
        columns_layout.addWidget(load_group)

        # Add stretch to push boxes together in center
        columns_layout.addStretch()

        # Browse button
        browse_btn = QPushButton(tr("LoopManager", "Browse for Loop/MIDI Files"))
        browse_btn.setMinimumHeight(45)
        browse_btn.clicked.connect(self.on_browse_files)
        load_layout.addWidget(browse_btn)

        # File list
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(100)
        self.file_list.setMaximumHeight(150)
        self.file_list.currentItemChanged.connect(self.on_file_selected)
        load_layout.addWidget(self.file_list)

        # Clear list button
        clear_btn = QPushButton(tr("LoopManager", "Clear File List"))
        clear_btn.clicked.connect(self.on_clear_file_list)
        load_layout.addWidget(clear_btn)

        # Load All button
        self.load_all_btn = QPushButton(tr("LoopManager", "Load All Tracks to Device"))
        self.load_all_btn.setMinimumHeight(35)
        self.load_all_btn.setEnabled(False)
        self.load_all_btn.clicked.connect(self.on_load_all_tracks)
        load_layout.addWidget(self.load_all_btn)

        # Load progress
        self.load_progress_label = QLabel("")
        load_layout.addWidget(self.load_progress_label)

        self.load_progress_bar = QProgressBar()
        self.load_progress_bar.setMinimum(0)
        self.load_progress_bar.setMaximum(100)
        self.load_progress_bar.setValue(0)
        self.load_progress_bar.setVisible(False)
        load_layout.addWidget(self.load_progress_bar)

        load_layout.addStretch()

        # === ADVANCED TRACK ASSIGNMENT SECTION ===
        self.advanced_section = QGroupBox(tr("LoopManager", "Advanced Track Assignment"))
        advanced_layout = QVBoxLayout()
        self.advanced_section.setLayout(advanced_layout)
        self.advanced_section.setVisible(True)
        main_layout.addWidget(self.advanced_section)

        # Track selection area
        track_select_label = QLabel(tr("LoopManager", "Select Track:"))
        track_select_label.setStyleSheet("font-weight: bold;")
        advanced_layout.addWidget(track_select_label)

        self.track_info_label = QLabel(tr("LoopManager", "Select a MIDI file to see tracks"))
        self.track_info_label.setStyleSheet("font-style: italic;")
        advanced_layout.addWidget(self.track_info_label)

        # Centered container for track buttons
        track_container_layout = QHBoxLayout()
        track_container_layout.addStretch()
        self.track_buttons_widget = QWidget()
        self.track_buttons_layout = QGridLayout()
        self.track_buttons_widget.setLayout(self.track_buttons_layout)
        track_container_layout.addWidget(self.track_buttons_widget)
        track_container_layout.addStretch()
        advanced_layout.addLayout(track_container_layout)

        self.track_button_group = QButtonGroup(self)
        self.track_button_group.setExclusive(True)
        self.track_button_group.buttonClicked.connect(self.on_track_button_clicked)

        # Loop assignment area
        assign_label = QLabel(tr("LoopManager", "Assign Selected Track to Loop:"))
        assign_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        advanced_layout.addWidget(assign_label)

        # Center container for all loop buttons (main and overdub together)
        all_buttons_container = QHBoxLayout()
        all_buttons_container.addStretch()
        all_buttons_widget = QWidget()
        all_buttons_layout = QGridLayout()
        all_buttons_layout.setSpacing(8)
        all_buttons_widget.setLayout(all_buttons_layout)

        self.main_assign_btns = []
        self.main_clear_btns = []
        self.overdub_assign_btns = []
        self.overdub_clear_btns = []

        # Create 8 columns: Loop 1-8 (main) in rows 0-1, Overdub 1-8 in rows 2-3
        for i in range(8):
            # Main loop button with container
            main_container = QWidget()
            main_container.setFixedSize(120, 60)  # Increased width by 20px
            main_container_layout = QVBoxLayout(main_container)
            main_container_layout.setContentsMargins(0, 0, 0, 0)
            main_container_layout.setSpacing(0)

            main_btn = QPushButton(f"Loop {i+1}")
            main_btn.setMinimumHeight(60)
            main_btn.setMaximumWidth(120)  # Increased by 20px
            main_btn.setMinimumWidth(120)  # Increased by 20px
            main_btn.clicked.connect(lambda checked, loop=i+1: self.on_assign_main(loop))
            main_btn.setProperty('loop_num', i+1)
            main_container_layout.addWidget(main_btn)

            # X button positioned at top right
            main_clear_btn = QPushButton("✕")
            main_clear_btn.setParent(main_container)
            main_clear_btn.setGeometry(95, 2, 20, 20)  # Adjusted for wider button
            main_clear_btn.setVisible(False)
            main_clear_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 0, 0, 0.7);
                    color: white;
                    border: none;
                    border-radius: 10px;
                    font-weight: bold;
                    font-size: 10px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 0, 0, 0.9);
                }
            """)
            main_clear_btn.clicked.connect(lambda checked, loop=i+1: self.on_clear_main_assignment(loop))

            all_buttons_layout.addWidget(main_container, 0, i)
            self.main_assign_btns.append(main_btn)
            self.main_clear_btns.append(main_clear_btn)

            # Overdub loop button with container
            overdub_container = QWidget()
            overdub_container.setFixedSize(120, 60)  # Increased width by 20px
            overdub_container_layout = QVBoxLayout(overdub_container)
            overdub_container_layout.setContentsMargins(0, 0, 0, 0)
            overdub_container_layout.setSpacing(0)

            overdub_btn = QPushButton(f"Overdub {i+1}")
            overdub_btn.setMinimumHeight(60)
            overdub_btn.setMaximumWidth(120)  # Increased by 20px
            overdub_btn.setMinimumWidth(120)  # Increased by 20px
            overdub_btn.setEnabled(False)
            overdub_btn.clicked.connect(lambda checked, loop=i+1: self.on_assign_overdub(loop))
            overdub_btn.setProperty('loop_num', i+1)
            overdub_container_layout.addWidget(overdub_btn)

            # X button positioned at top right
            overdub_clear_btn = QPushButton("✕")
            overdub_clear_btn.setParent(overdub_container)
            overdub_clear_btn.setGeometry(95, 2, 20, 20)  # Adjusted for wider button
            overdub_clear_btn.setVisible(False)
            overdub_clear_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 0, 0, 0.7);
                    color: white;
                    border: none;
                    border-radius: 10px;
                    font-weight: bold;
                    font-size: 10px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 0, 0, 0.9);
                }
            """)
            overdub_clear_btn.clicked.connect(lambda checked, loop=i+1: self.on_clear_overdub_assignment(loop))

            all_buttons_layout.addWidget(overdub_container, 1, i)
            self.overdub_assign_btns.append(overdub_btn)
            self.overdub_clear_btns.append(overdub_clear_btn)

        all_buttons_container.addWidget(all_buttons_widget)
        all_buttons_container.addStretch()
        advanced_layout.addLayout(all_buttons_container)

        # Info text
        info_label = QLabel(tr("LoopManager",
            "💡 Overdub tracks are only available for loops that already have main content. "
            "Select a track above, then click a loop button to assign."))
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-size: 11px; padding: 8px;")
        advanced_layout.addWidget(info_label)

        # Load assignments button
        self.load_assignments_btn = QPushButton(tr("LoopManager", "Load Assigned Tracks to Device"))
        self.load_assignments_btn.setMinimumHeight(40)
        self.load_assignments_btn.setEnabled(False)
        self.load_assignments_btn.clicked.connect(self.on_load_assignments)
        advanced_layout.addWidget(self.load_assignments_btn)

    def send_hid_packet(self, command, macro_num, status=0, data=None):
        """Send raw HID packet to device"""
        if not self.device or not isinstance(self.device, VialKeyboard):
            raise Exception("Device not connected")

        packet = bytearray(self.HID_PACKET_SIZE)
        packet[0] = self.MANUFACTURER_ID
        packet[1] = self.SUB_ID
        packet[2] = self.DEVICE_ID
        packet[3] = command
        packet[4] = macro_num
        packet[5] = status

        if data:
            data_len = min(len(data), self.HID_DATA_SIZE)
            packet[6:6 + data_len] = data[:data_len]

        try:
            # Send raw HID data (not VIA command)
            self.device.send(bytes(packet))
        except Exception as e:
            raise Exception(f"Failed to send HID packet: {str(e)}")

    def start_hid_listener(self):
        """Start background thread to listen for HID responses"""
        if self.hid_listening:
            return

        self.hid_listening = True
        self.hid_listener_thread = threading.Thread(target=self.hid_listener_loop, daemon=True)
        self.hid_listener_thread.start()

    def stop_hid_listener(self):
        """Stop the HID listener thread"""
        self.hid_listening = False
        if self.hid_listener_thread:
            self.hid_listener_thread.join(timeout=1.0)

    def hid_listener_loop(self):
        """Background thread loop to receive HID data"""
        logger.info("HID listener thread started")
        while self.hid_listening and self.device:
            try:
                # Read HID data with shorter timeout (100ms) for better responsiveness
                # Listener only runs during active transfers now, so shorter timeout is safe
                data = self.device.recv(self.HID_PACKET_SIZE, timeout_ms=100)
                if data and len(data) > 0:
                    logger.info(f"HID received {len(data)} bytes: {data[:10].hex()}...")
                    if len(data) == self.HID_PACKET_SIZE:
                        # Emit signal for thread-safe UI update
                        self.hid_data_received.emit(bytes(data))
                    else:
                        logger.info(f"Warning: Received {len(data)} bytes, expected {self.HID_PACKET_SIZE}")
            except Exception as e:
                # Ignore timeout errors but log others
                error_msg = str(e).lower()
                if "timeout" not in error_msg and "timed out" not in error_msg:
                    logger.info(f"HID listener error: {e}")
        logger.info("HID listener thread stopped")

    def on_view_log(self):
        """Open the debug log file"""
        try:
            if os.path.exists(LOG_FILE):
                # Open log file in default text editor
                QDesktopServices.openUrl(QUrl.fromLocalFile(LOG_FILE))
                QMessageBox.information(None, "Debug Log",
                    f"Log file location:\n{LOG_FILE}\n\n"
                    "The log file contains detailed debug information about HID communication.")
            else:
                QMessageBox.warning(None, "Log Not Found",
                    f"Log file not found at:\n{LOG_FILE}\n\n"
                    "The log will be created when you perform save/load operations.")
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to open log file: {str(e)}")

    def on_save_loop(self, loop_num):
        """Request to save a specific loop from device"""
        try:
            # Don't prompt for filename yet - wait for data and BPM extraction
            logger.info(f"\n=== Requesting Loop {loop_num} from device ===")

            # Initialize transfer state (no filename yet)
            self.current_transfer = {
                'active': True,
                'is_loading': False,
                'loop_num': loop_num,
                'expected_packets': 0,
                'received_packets': 0,
                'total_size': 0,
                'received_data': bytearray(),
                'file_name': '',  # Will be set after BPM extraction
                'save_format': 'midi' if self.format_midi_radio.isChecked() else 'loop',
                'save_all_mode': False,
                'save_all_directory': '',
                'save_all_current': 0
            }

            # Start HID listener if not already running
            self.start_hid_listener()

            # Wait a moment for listener to be ready
            time.sleep(0.1)

            # Update UI
            self.save_progress_label.setText(f"Requesting Loop {loop_num} from device...")
            self.save_progress_bar.setValue(0)
            self.save_progress_bar.setVisible(True)

            logger.info(f"Sending REQUEST_SAVE command for loop {loop_num}")
            # Send request to device
            self.send_hid_packet(self.HID_CMD_REQUEST_SAVE, loop_num)
            logger.info("REQUEST_SAVE sent, waiting for response...")

        except Exception as e:
            logger.info(f"Error in on_save_loop: {e}")
            QMessageBox.critical(None, "Error", f"Failed to request loop save: {str(e)}")
            self.reset_transfer_state()

    def on_clear_all_loops(self):
        """Clear all loop content on the device"""
        # Confirmation dialog
        reply = QMessageBox.question(
            None,
            tr("LoopManager", "Clear All Loops"),
            tr("LoopManager", "Are you sure you want to clear ALL loop content on the device?\n\nThis action cannot be undone."),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            if not self.device or not isinstance(self.device, VialKeyboard):
                QMessageBox.warning(None, tr("LoopManager", "Error"),
                    tr("LoopManager", "No keyboard connected"))
                return

            # Call the clear_all_loops method on the keyboard
            success = self.device.keyboard.clear_all_loops()

            if success:
                # Clear local tracking
                self.loop_contents.clear()
                self.overdub_contents.clear()

                # Update UI to show empty loops
                for i in range(8):
                    if i < len(self.main_loop_btns):
                        self.main_loop_btns[i].setText(f"Main {i+1}\n(empty)")
                    if i < len(self.overdub_btns):
                        self.overdub_btns[i].setText(f"Overdub {i+1}\n(empty)")
                        self.overdub_btns[i].setEnabled(False)
                    # Hide clear buttons
                    if hasattr(self, 'main_clear_btns') and i < len(self.main_clear_btns):
                        self.main_clear_btns[i].setVisible(False)
                    if hasattr(self, 'overdub_clear_btns') and i < len(self.overdub_clear_btns):
                        self.overdub_clear_btns[i].setVisible(False)

                QMessageBox.information(None, tr("LoopManager", "Success"),
                    tr("LoopManager", "All loops have been cleared."))
                logger.info("All loops cleared successfully")
            else:
                QMessageBox.warning(None, tr("LoopManager", "Error"),
                    tr("LoopManager", "Failed to clear loops. Please try again."))
                logger.error("Failed to clear all loops")

        except Exception as e:
            logger.error(f"Error clearing all loops: {e}")
            QMessageBox.critical(None, tr("LoopManager", "Error"),
                tr("LoopManager", f"Error clearing loops: {str(e)}"))

    def on_save_all_loops(self):
        """Save all loops from device to a single file"""
        try:
            # Determine format and prompt for single filename
            save_format = 'midi' if self.format_midi_radio.isChecked() else 'loop'

            if save_format == 'midi':
                filter_str = "MIDI Files (*.midi);;All Files (*)"
                default_name = "all_loops.midi"
            else:
                filter_str = "Loop Files (*.loop);;All Files (*)"
                default_name = "all_loops.loop"

            filename, _ = QFileDialog.getSaveFileName(
                None, "Save All Loops", default_name, filter_str
            )

            if not filename:
                return

            logger.info(f"\n=== Saving All Loops to {filename} ===")

            # Initialize for save all mode
            self.current_transfer = {
                'active': True,
                'is_loading': False,
                'loop_num': 0,
                'expected_packets': 0,
                'received_packets': 0,
                'total_size': 0,
                'received_data': bytearray(),
                'file_name': filename,
                'save_format': save_format,
                'save_all_mode': True,
                'save_all_data': {},  # Will store all loop data
                'save_all_current': 1,
                'save_all_max_bpm': 120.0
            }

            # Start HID listener
            self.start_hid_listener()

            # Wait a moment for listener to be ready
            time.sleep(0.1)

            # Update UI
            self.save_progress_label.setText("Requesting all loops from device...")
            self.save_progress_bar.setValue(0)
            self.save_progress_bar.setVisible(True)

            # Start requesting loops
            self.save_next_loop_in_sequence()

        except Exception as e:
            logger.info(f"Error in on_save_all_loops: {e}")
            QMessageBox.critical(None, "Error", f"Failed to save all loops: {str(e)}")
            self.reset_transfer_state()

    def save_next_loop_in_sequence(self):
        """Continue save all sequence - request next loop"""
        loop_num = self.current_transfer.get('save_all_current', 0)

        if loop_num > NUM_LOOPS:
            # All loops received, now save to file
            logger.info("All loops received, creating combined file...")
            self.save_all_loops_to_file()
            return

        # Setup for this loop
        self.current_transfer['active'] = True
        self.current_transfer['loop_num'] = loop_num
        self.current_transfer['expected_packets'] = 0
        self.current_transfer['received_packets'] = 0
        self.current_transfer['total_size'] = 0
        self.current_transfer['received_data'] = bytearray()

        # Update UI
        self.save_progress_label.setText(f"Requesting Loop {loop_num} of {NUM_LOOPS}...")
        self.save_progress_bar.setValue(int((loop_num - 1) * 100 / NUM_LOOPS))
        self.save_progress_bar.setVisible(True)

        # Send request
        logger.info(f"Requesting loop {loop_num} for save all")
        self.send_hid_packet(self.HID_CMD_REQUEST_SAVE, loop_num)

    def save_all_loops_to_file(self):
        """Save all collected loops to a single file"""
        try:
            save_format = self.current_transfer['save_format']
            filename = self.current_transfer['file_name']
            save_all_data = self.current_transfer.get('save_all_data', {})

            logger.info(f"Saving all loops to {filename} in {save_format} format")
            logger.info(f"Collected data for loops: {list(save_all_data.keys())}")

            if save_format == 'midi':
                # Convert to MIDI - all loops in one file
                loops_data = {}
                max_bpm = self.current_transfer.get('save_all_max_bpm', 120.0)

                for loop_num, loop_bytes in save_all_data.items():
                    parsed = self.parse_loop_data(loop_bytes)
                    if parsed:
                        loops_data[loop_num] = parsed
                        # Use highest BPM from all loops
                        if parsed['bpm'] > max_bpm:
                            max_bpm = parsed['bpm']

                logger.info(f"Using BPM: {max_bpm} for MIDI file")

                midi_data = self.convert_loop_to_midi(loops_data, max_bpm)

                if midi_data:
                    with open(filename, 'wb') as f:
                        f.write(midi_data)
                    logger.info(f"Successfully saved MIDI file: {filename}")
                    self.save_progress_label.setText(f"Saved all loops to {os.path.basename(filename)}")
                else:
                    logger.info("Failed to create MIDI data")
                    QMessageBox.warning(None, "Warning", "Failed to convert loops to MIDI")

            else:
                # Save as .loop file (combined format) - EXACT MATCH to webapp format
                # Format matches saveCombinedLoopFile() in index.html (lines 5969-6048)
                # Header: MSWLOOPS (8) + Version (1) + Count (1) + Global BPM (4) + Reserved (2) = 16 bytes
                # Per loop: Loop# (1) + Loop BPM (4) + Length (4) + Data (variable)

                combined_data = bytearray()

                # Get loop numbers sorted (same as webapp)
                loop_numbers = sorted(save_all_data.keys())
                loop_count = len(loop_numbers)

                # Extract BPM from each loop and find max for global BPM
                loop_bpms = {}
                max_bpm = self.current_transfer.get('save_all_max_bpm', 120.0)
                for loop_num in loop_numbers:
                    loop_bpm = self.extract_bpm_from_loop_data(save_all_data[loop_num])
                    loop_bpms[loop_num] = loop_bpm
                    if loop_bpm > max_bpm:
                        max_bpm = loop_bpm

                logger.info(f"Creating .loop file with {loop_count} loops at global BPM {max_bpm}")

                # Write header "MSWLOOPS" (8 bytes) - EXACT match to webapp
                combined_data.extend(b'MSWLOOPS')

                # Write version (1 byte)
                combined_data.append(0x01)

                # Write loop count (1 byte)
                combined_data.append(loop_count)

                # Write global BPM (4 bytes, little-endian) - EXACT match to webapp
                bpm_value = int(max_bpm)
                combined_data.extend(struct.pack('<I', bpm_value))

                # Write reserved bytes (2 bytes) - EXACT match to webapp
                combined_data.extend(b'\x00\x00')

                logger.info(f"Header size: {len(combined_data)} bytes (should be 16)")

                # Write each loop's data - EXACT match to webapp
                for loop_num in loop_numbers:
                    loop_data = save_all_data[loop_num]
                    loop_bpm = int(loop_bpms[loop_num])

                    logger.info(f"Adding loop {loop_num}: {len(loop_data)} bytes at BPM {loop_bpm}")

                    # Write loop number (1 byte)
                    combined_data.append(loop_num)

                    # Write loop-specific BPM (4 bytes, little-endian)
                    combined_data.extend(struct.pack('<I', loop_bpm))

                    # Write data length (4 bytes, little-endian)
                    combined_data.extend(struct.pack('<I', len(loop_data)))

                    # Write loop data
                    combined_data.extend(loop_data)

                with open(filename, 'wb') as f:
                    f.write(combined_data)

                logger.info(f"Successfully saved .loop file: {filename} ({len(combined_data)} total bytes)")
                self.save_progress_label.setText(f"Saved all loops to {os.path.basename(filename)}")

            # Update progress bar
            self.save_progress_bar.setValue(100)

            # Reset after a short delay (no popup notification)
            QTimer.singleShot(2000, self.reset_transfer_state)

        except Exception as e:
            logger.info(f"Error saving all loops to file: {e}")
            QMessageBox.critical(None, "Error", f"Failed to save file: {str(e)}")
            self.reset_transfer_state()

    def parse_loop_file(self, filename):
        """Parse a .loop or .loops file and extract track info"""
        try:
            with open(filename, 'rb') as f:
                data = f.read()

            # Basic validation
            if len(data) < 4:
                return None

            # Check if it's a .loop file with combined/multi-loop format
            # Support both old "LOOPS" and new "MSWLOOPS" formats
            if data[0:8] == b'MSWLOOPS' or data[0:5] == b'LOOPS':
                return self.parse_loops_file(data)

            # Check if it's a single .loop file
            if data[0] == 0xAA and data[1] == 0x55:
                # Extract BPM from loop data
                bpm = self.extract_bpm_from_loop_data(data)

                # Parse the loop to get event counts for track info
                parsed = self.parse_loop_data(data)
                if not parsed:
                    return None

                # Create track list based on what's in the loop
                tracks = []
                if parsed['mainEvents']:
                    tracks.append({
                        'name': f'Loop Main ({len(parsed["mainEvents"])} events)',
                        'index': 0,
                        'is_overdub': False
                    })
                if parsed['overdubEvents']:
                    tracks.append({
                        'name': f'Loop Overdub ({len(parsed["overdubEvents"])} events)',
                        'index': 1,
                        'is_overdub': True
                    })

                return {
                    'tracks': tracks,
                    'bpm': bpm,
                    'loop_data': data  # Store raw data for loading
                }

            return None

        except Exception as e:
            logger.info(f"Error parsing loop file: {e}")
            return None

    def parse_loops_file(self, data):
        """Parse a .loop file (combined/multi-loop format) - supports both old and new formats"""
        try:
            # Check if it's the new MSWLOOPS format or old LOOPS format
            is_new_format = data[0:8] == b'MSWLOOPS'
            is_old_format = data[0:5] == b'LOOPS'

            if is_new_format:
                # New format: MSWLOOPS (8) + Version (1) + Count (1) + Global BPM (4) + Reserved (2) = 16 bytes
                # Per loop: Loop# (1) + Loop BPM (4) + Length (4) + Data (variable)
                logger.info("Parsing new MSWLOOPS format")

                if len(data) < 16:
                    logger.info("File too short for MSWLOOPS format")
                    return None

                version = data[8]
                loop_count = data[9]
                global_bpm = struct.unpack('<I', data[10:14])[0]  # Little-endian
                # Reserved bytes at 14:16
                offset = 16

                logger.info(f"MSWLOOPS file: version {version}, {loop_count} loops, global BPM {global_bpm}")

                tracks = []
                loops_data = {}

                for i in range(loop_count):
                    if offset + 9 > len(data):  # Need at least 9 bytes for metadata
                        logger.info(f"Insufficient data for loop {i+1} metadata")
                        break

                    # Read loop metadata
                    loop_num = data[offset]
                    offset += 1

                    loop_bpm = struct.unpack('<I', data[offset:offset + 4])[0]  # Little-endian
                    offset += 4

                    loop_size = struct.unpack('<I', data[offset:offset + 4])[0]  # Little-endian
                    offset += 4

                    logger.info(f"Loop {loop_num}: BPM={loop_bpm}, size={loop_size} bytes")

                    # loop_num is read straight from the file and later sent to
                    # the keyboard as a slot selector; reject out-of-range values
                    # so a hand-edited/corrupt file can never target an invalid
                    # firmware slot. Skip the payload and keep parsing.
                    if not (1 <= loop_num <= NUM_LOOPS):
                        logger.warning(f"Skipping loop with out-of-range number {loop_num}")
                        if loop_size > 0 and offset + loop_size <= len(data):
                            offset += loop_size
                        else:
                            break
                        continue

                    if loop_size > 0:
                        if offset + loop_size > len(data):
                            logger.info(f"Invalid loop size for loop {loop_num}")
                            break

                        loop_data = data[offset:offset + loop_size]
                        offset += loop_size

                        # Store loop data and create simple track (matches webapp behavior)
                        loops_data[loop_num] = loop_data
                        tracks.append({
                            'name': f'Loop {loop_num}',
                            'index': len(tracks),
                            'loop_num': loop_num,
                            'is_overdub': False
                        })

                return {
                    'tracks': tracks,
                    'bpm': global_bpm,
                    'loops_data': loops_data  # Dict of loop_num -> raw loop data
                }

            elif is_old_format:
                # Old format: LOOPS + version(1) + count(1) + [loop1_size(4) + loop1_data]...
                logger.info("Parsing old LOOPS format")

                if len(data) < 7:
                    return None

                version = data[5]
                loop_count = data[6]
                offset = 7

                logger.info(f"Old LOOPS file: version {version}, {loop_count} loops")

                tracks = []
                loops_data = {}

                for loop_num in range(1, loop_count + 1):
                    if offset + 4 > len(data):
                        break

                    # Read loop size (4 bytes, big-endian in old format)
                    loop_size = struct.unpack('>I', data[offset:offset + 4])[0]
                    offset += 4

                    if loop_size > 0:
                        if offset + loop_size > len(data):
                            logger.info(f"Invalid loop size for loop {loop_num}")
                            break

                        loop_data = data[offset:offset + loop_size]
                        offset += loop_size

                        # Store loop data and create simple track (matches webapp behavior)
                        loops_data[loop_num] = loop_data
                        tracks.append({
                            'name': f'Loop {loop_num}',
                            'index': len(tracks),
                            'loop_num': loop_num,
                            'is_overdub': False
                        })

                # Use highest BPM from all loops
                max_bpm = 120.0
                for loop_data in loops_data.values():
                    bpm = self.extract_bpm_from_loop_data(loop_data)
                    if bpm > max_bpm:
                        max_bpm = bpm

                return {
                    'tracks': tracks,
                    'bpm': max_bpm,
                    'loops_data': loops_data  # Dict of loop_num -> raw loop data
                }

            else:
                logger.info("Unknown .loop file format")
                return None

        except Exception as e:
            logger.info(f"Error parsing .loop file: {e}")
            return None

    def parse_midi_file(self, filename):
        """Parse a MIDI file and extract track info - matches webapp parseMIDIFile()"""
        try:
            with open(filename, 'rb') as f:
                data = f.read()

            logger.info(f"Parsing MIDI file: {filename}, {len(data)} bytes")

            # Basic MIDI file validation
            if len(data) < 14:
                logger.info("File too short for MIDI header")
                return None

            # Check "MThd" header
            if data[0:4] != b'MThd':
                logger.info("Not a valid MIDI file (missing MThd header)")
                return None

            # Parse header
            offset = 4
            header_length = struct.unpack('>I', data[offset:offset + 4])[0]
            offset += 4

            if header_length < 6:
                logger.info(f"Invalid header length: {header_length}")
                return None

            format_type = struct.unpack('>H', data[offset:offset + 2])[0]
            track_count = struct.unpack('>H', data[offset + 2:offset + 4])[0]
            tpqn = struct.unpack('>H', data[offset + 4:offset + 6])[0]
            offset += header_length

            logger.info(f"MIDI file: format={format_type}, tracks={track_count}, TPQN={tpqn}")

            # Parse each track
            tracks = []
            found_bpm = 120  # Default BPM

            for track_idx in range(track_count):
                if offset + 8 > len(data):
                    logger.info(f"Not enough data for track {track_idx + 1}")
                    break

                # Check for "MTrk" chunk
                if data[offset:offset + 4] != b'MTrk':
                    logger.info(f"Track {track_idx + 1}: Invalid track header")
                    break

                offset += 4
                track_length = struct.unpack('>I', data[offset:offset + 4])[0]
                offset += 4

                if offset + track_length > len(data):
                    logger.info(f"Track {track_idx + 1}: Invalid track length {track_length}")
                    break

                # Parse track events
                track_data = data[offset:offset + track_length]
                parsed_track = self.parse_midi_track(track_data, tpqn)

                if parsed_track['tempo']:
                    found_bpm = parsed_track['tempo']
                    logger.info(f"Found BPM in track {track_idx + 1}: {found_bpm}")

                track_name = parsed_track['trackName'] or f'Track {track_idx + 1}'

                # Calculate track duration in milliseconds
                duration_ms = 0
                if parsed_track['events']:
                    # Convert MIDI track to loop format to calculate timing
                    loop_events = self.convert_midi_to_loop_format(parsed_track['events'], found_bpm, tpqn)
                    if loop_events:
                        timing = self.calculate_loop_timing(loop_events, found_bpm, parsed_track['maxTicks'], False)
                        duration_ms = timing['loopLength']

                tracks.append({
                    'name': track_name,
                    'index': track_idx,
                    'events': parsed_track['events'],
                    'maxTicks': parsed_track['maxTicks'],
                    'duration_ms': duration_ms
                })

                logger.info(f"Track {track_idx + 1} '{track_name}': {len(parsed_track['events'])} events, {duration_ms}ms")

                offset += track_length

            logger.info(f"Parsed {len(tracks)} tracks, BPM: {found_bpm}")

            return {
                'tracks': tracks,
                'bpm': found_bpm,
                'tpqn': tpqn
            }

        except Exception as e:
            logger.info(f"Error parsing MIDI file: {e}")
            import traceback
            traceback.print_exc()
            return None

    def on_browse_files(self):
        """Browse for loop/MIDI files to load"""
        filenames, _ = QFileDialog.getOpenFileNames(
            None, "Select Loop or MIDI Files", "",
            "All Supported (*.loop *.mid *.midi);;Loop Files (*.loop);;MIDI Files (*.mid *.midi);;All Files (*)"
        )

        for filename in filenames:
            # Check if already in list
            found = False
            for i in range(self.file_list.count()):
                if self.file_list.item(i).data(QtCore.Qt.UserRole) == filename:
                    found = True
                    break

            if not found:
                # Parse file to get track info
                file_info = None
                if filename.endswith('.loop'):
                    file_info = self.parse_loop_file(filename)
                elif filename.endswith('.mid') or filename.endswith('.midi'):
                    file_info = self.parse_midi_file(filename)

                if file_info:
                    # Store file info
                    self.loaded_files[filename] = file_info

                # Add to list
                display_name = os.path.basename(filename)
                file_size = os.path.getsize(filename)
                track_count = len(file_info['tracks']) if file_info else 0
                display_text = f"{display_name} ({track_count} tracks, {file_size} bytes)"

                item = QListWidgetItem(display_text)
                item.setData(QtCore.Qt.UserRole, filename)
                self.file_list.addItem(item)

        # Enable load all button if files loaded
        if self.file_list.count() > 0:
            self.load_all_btn.setEnabled(True)

    def on_clear_file_list(self):
        """Clear the file list"""
        self.file_list.clear()
        self.loaded_files.clear()
        self.load_all_btn.setEnabled(False)
        self.pending_assignments.clear()
        self.selected_track = None
        self.update_track_display()
        self.update_assignment_buttons()

    def on_file_selected(self, current, previous):
        """Handle file selection - show tracks"""
        if not current:
            self.update_track_display()
            return

        filename = current.data(QtCore.Qt.UserRole)
        if filename in self.loaded_files:
            self.update_track_display(filename)

        # Enable load all
        self.load_all_btn.setEnabled(True)

    def update_track_display(self, filename=None):
        """Update the track selection display"""
        # Clear existing track buttons
        for i in reversed(range(self.track_buttons_layout.count())):
            self.track_buttons_layout.itemAt(i).widget().deleteLater()

        # Clear button group
        for button in self.track_button_group.buttons():
            self.track_button_group.removeButton(button)

        if not filename or filename not in self.loaded_files:
            self.track_info_label.setText(tr("LoopManager", "Select a MIDI file to see tracks"))
            self.track_info_label.setVisible(True)
            self.track_buttons_widget.setVisible(False)
            return

        file_info = self.loaded_files[filename]
        tracks = file_info['tracks']

        if len(tracks) == 0:
            self.track_info_label.setText(tr("LoopManager", "No tracks found in file"))
            self.track_info_label.setVisible(True)
            self.track_buttons_widget.setVisible(False)
            return

        # Hide info label, show track buttons
        self.track_info_label.setVisible(False)
        self.track_buttons_widget.setVisible(True)

        # Create track buttons (max 4 per row)
        for idx, track in enumerate(tracks):
            row = idx // 4
            col = idx % 4

            # Create button label with "Track X - Xms" format
            duration_ms = track.get('duration_ms', 0)
            btn_label = f"Track {idx + 1} - {duration_ms}ms"

            btn = QPushButton(btn_label)
            btn.setCheckable(True)
            btn.setMinimumHeight(35)
            btn.setMaximumWidth(150)  # Make buttons less wide
            btn.setProperty('filename', filename)
            btn.setProperty('track_idx', idx)
            btn.setProperty('track_duration_ms', duration_ms)

            # Style assignable loop buttons using theme colors
            palette = QApplication.palette()
            btn_color = palette.color(QPalette.Button).name()
            btn_text = palette.color(QPalette.ButtonText).name()
            highlight_color = palette.color(QPalette.Highlight).name()
            highlight_text = palette.color(QPalette.HighlightedText).name()
            alt_base = palette.color(QPalette.AlternateBase).name()
            light_color = palette.color(QPalette.Light).name()
            mid_color = palette.color(QPalette.Mid).name()

            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {btn_color};
                    color: {btn_text};
                    border: 2px solid {mid_color};
                    border-radius: 4px;
                    font-weight: bold;
                    padding: 5px;
                }}
                QPushButton:hover {{
                    background-color: {alt_base};
                }}
                QPushButton:checked {{
                    background-color: {highlight_color};
                    color: {highlight_text};
                    border: 4px solid {light_color};
                }}
                QPushButton:disabled {{
                    background-color: {alt_base};
                    color: {light_color};
                }}
            """)

            self.track_button_group.addButton(btn)
            self.track_buttons_layout.addWidget(btn, row, col)

    def on_track_button_clicked(self, button):
        """Handle track button click"""
        filename = button.property('filename')
        track_idx = button.property('track_idx')

        self.selected_track = {
            'filename': filename,
            'track_idx': track_idx
        }

    def on_toggle_advanced(self, state):
        """Toggle advanced track assignment section"""
        self.advanced_section.setVisible(state == QtCore.Qt.Checked)

    def on_assign_main(self, loop_num):
        """Assign selected track to main loop"""
        if not self.selected_track:
            QMessageBox.warning(None, "Warning", "Please select a track first")
            return

        # Store pending assignment
        if loop_num not in self.pending_assignments:
            self.pending_assignments[loop_num] = {}
        self.pending_assignments[loop_num]['main'] = self.selected_track.copy()

        self.update_assignment_buttons()
        self.load_assignments_btn.setEnabled(True)

    def on_assign_overdub(self, loop_num):
        """Assign selected track to overdub loop"""
        if not self.selected_track:
            QMessageBox.warning(None, "Warning", "Please select a track first")
            return

        # Check if main loop has content
        if loop_num not in self.loop_contents and loop_num not in self.pending_assignments:
            QMessageBox.warning(None, "Warning",
                f"Loop {loop_num} must have main content before adding overdub")
            return

        # Store pending assignment
        if loop_num not in self.pending_assignments:
            self.pending_assignments[loop_num] = {}
        self.pending_assignments[loop_num]['overdub'] = self.selected_track.copy()

        self.update_assignment_buttons()
        self.load_assignments_btn.setEnabled(True)

    def load_loop_data_to_device(self, loop_data, loop_num):
        """Load loop data to device via HID - matches webapp loadLoopData()"""
        # loop_num is used by the firmware as a slot index (loop_num - 1); a bad
        # value causes out-of-bounds writes on the keyboard. Guard here so every
        # caller (file import, restore, drag/drop) is covered.
        if not (1 <= loop_num <= NUM_LOOPS):
            logger.error(f"Refusing to load loop: invalid loop number {loop_num}")
            return False
        try:
            logger.info(f"\n=== Loading loop data to device: Loop {loop_num}, {len(loop_data)} bytes ===")

            # Calculate number of packets needed
            chunk_size = self.HID_DATA_SIZE - 4  # Reserve 4 bytes for chunk info
            total_packets = (len(loop_data) + chunk_size - 1) // chunk_size  # Ceiling division

            logger.info(f"Total packets to send: {total_packets}, chunk size: {chunk_size}")

            # Send LOAD_START packet
            start_data = bytearray(4)
            start_data[0] = total_packets & 0xFF
            start_data[1] = (total_packets >> 8) & 0xFF
            start_data[2] = len(loop_data) & 0xFF
            start_data[3] = (len(loop_data) >> 8) & 0xFF

            logger.info(f"Sending LOAD_START: {total_packets} packets, {len(loop_data)} bytes")
            self.send_hid_packet(self.HID_CMD_LOAD_START, loop_num, 0, start_data)
            time.sleep(0.05)

            # Send data in chunks
            for packet_num in range(total_packets):
                offset = packet_num * chunk_size
                chunk_len = min(chunk_size, len(loop_data) - offset)
                chunk_data = loop_data[offset:offset + chunk_len]

                # Create packet data: packet_num(2) + chunk_len(2) + chunk_data
                packet_data = bytearray(4 + chunk_len)
                packet_data[0] = packet_num & 0xFF
                packet_data[1] = (packet_num >> 8) & 0xFF
                packet_data[2] = chunk_len & 0xFF
                packet_data[3] = (chunk_len >> 8) & 0xFF
                packet_data[4:4 + chunk_len] = chunk_data

                logger.info(f"Sending chunk {packet_num + 1}/{total_packets}: {chunk_len} bytes")
                self.send_hid_packet(self.HID_CMD_LOAD_CHUNK, loop_num, 0, packet_data)
                time.sleep(0.01)  # Small delay between packets

            # Send LOAD_END packet
            logger.info("Sending LOAD_END")
            self.send_hid_packet(self.HID_CMD_LOAD_END, loop_num, 0)
            time.sleep(0.05)

            logger.info(f"Successfully sent all data for loop {loop_num}")
            return True

        except Exception as e:
            logger.info(f"Error loading loop data to device: {e}")
            return False

    def on_load_all_tracks(self):
        """Load all tracks from selected file"""
        try:
            # Get currently selected file
            current_item = self.file_list.currentItem()
            if not current_item:
                QMessageBox.warning(None, "Warning", "Please select a file first")
                return

            filename = current_item.data(QtCore.Qt.UserRole)
            if filename not in self.loaded_files:
                QMessageBox.warning(None, "Warning", "File data not found")
                return

            file_info = self.loaded_files[filename]
            logger.info(f"\n=== Loading all tracks from {filename} ===")

            # Check if it's a .loops file or MIDI file
            if 'loops_data' in file_info:
                # .loops file - load each loop to corresponding slot
                loops_data = file_info['loops_data']
                logger.info(f"Loading .loops file with {len(loops_data)} loops")

                self.load_progress_label.setText("Loading loops to device...")
                self.load_progress_bar.setValue(0)
                self.load_progress_bar.setVisible(True)

                for idx, (loop_num, loop_data) in enumerate(loops_data.items()):
                    progress = int(((idx + 1) / len(loops_data)) * 100)
                    self.load_progress_label.setText(f"Loading Loop {loop_num} to device...")
                    self.load_progress_bar.setValue(progress)

                    success = self.load_loop_data_to_device(loop_data, loop_num)
                    if not success:
                        QMessageBox.warning(None, "Warning", f"Failed to load Loop {loop_num}")
                        break

                self.load_progress_label.setText("All loops loaded successfully")
                self.load_progress_bar.setValue(100)
                QTimer.singleShot(2000, self.reset_transfer_state)

            elif 'loop_data' in file_info:
                # Single .loop file - ask which loop to load to
                loop_num, ok = QInputDialog.getInt(
                    None, "Select Loop", "Load to which loop (1-4)?", 1, 1, 4
                )
                if not ok:
                    return

                logger.info(f"Loading single loop file to Loop {loop_num}")

                self.load_progress_label.setText(f"Loading to Loop {loop_num}...")
                self.load_progress_bar.setValue(50)
                self.load_progress_bar.setVisible(True)

                success = self.load_loop_data_to_device(file_info['loop_data'], loop_num)

                if success:
                    self.load_progress_label.setText(f"Loaded to Loop {loop_num}")
                    self.load_progress_bar.setValue(100)
                else:
                    QMessageBox.warning(None, "Warning", f"Failed to load to Loop {loop_num}")

                QTimer.singleShot(2000, self.reset_transfer_state)

            else:
                # MIDI file - load tracks sequentially to available loop slots
                if 'tracks' not in file_info:
                    QMessageBox.warning(None, "Warning", "No tracks found in MIDI file")
                    return

                tracks = file_info['tracks']
                bpm = file_info['bpm']
                tpqn = file_info.get('tpqn', 480)

                logger.info(f"Loading MIDI file with {len(tracks)} tracks at {bpm} BPM")

                self.load_progress_label.setText("Loading MIDI tracks to device...")
                self.load_progress_bar.setValue(0)
                self.load_progress_bar.setVisible(True)

                # Load up to 4 tracks
                for idx, track in enumerate(tracks[:4]):
                    loop_num = idx + 1

                    if not track['events']:
                        logger.info(f"Track {idx + 1} has no events, skipping")
                        continue

                    progress = int(((idx + 1) / min(len(tracks), 4)) * 100)
                    self.load_progress_label.setText(f"Loading track {idx + 1} '{track['name']}' to Loop {loop_num}...")
                    self.load_progress_bar.setValue(progress)

                    # Convert MIDI track to loop format
                    logger.info(f"Converting track {idx + 1} to loop format: {len(track['events'])} events")
                    loop_events = self.convert_midi_to_loop_format(track['events'], bpm, tpqn)

                    if loop_events:
                        # Calculate timing
                        timing = self.calculate_loop_timing(loop_events, bpm, track.get('maxTicks'), False)

                        # Create loop data
                        loop_data = self.create_loop_data_from_events(loop_events, loop_num, bpm, timing, False)

                        # Load to device
                        success = self.load_loop_data_to_device(loop_data, loop_num)

                        if not success:
                            QMessageBox.warning(None, "Warning", f"Failed to load track {idx + 1} to Loop {loop_num}")
                            break

                self.load_progress_label.setText("All MIDI tracks loaded successfully")
                self.load_progress_bar.setValue(100)
                QTimer.singleShot(2000, self.reset_transfer_state)

        except Exception as e:
            logger.info(f"Error in on_load_all_tracks: {e}")
            QMessageBox.critical(None, "Error", f"Failed to load tracks: {str(e)}")
            self.reset_transfer_state()

    def on_load_assignments(self):
        """Load assigned tracks to device"""
        try:
            if not self.pending_assignments:
                QMessageBox.warning(None, "Warning", "No tracks assigned. Please assign tracks first.")
                return

            logger.info(f"\n=== Loading assigned tracks to device ===")
            logger.info(f"Pending assignments: {list(self.pending_assignments.keys())}")

            self.load_progress_label.setText("Loading assigned tracks...")
            self.load_progress_bar.setValue(0)
            self.load_progress_bar.setVisible(True)

            total_assignments = sum(
                1 + (1 if 'overdub' in assignments else 0)
                for assignments in self.pending_assignments.values()
                if 'main' in assignments
            )

            logger.info(f"Total assignments to load: {total_assignments}")

            completed = 0

            for loop_num, assignments in self.pending_assignments.items():
                if 'main' in assignments:
                    # Load main track
                    track_info = assignments['main']
                    filename = track_info['filename']
                    track_idx = track_info['track_idx']

                    logger.info(f"Loading main track {track_idx} from {filename} to Loop {loop_num}")

                    # Get file info
                    if filename not in self.loaded_files:
                        logger.info(f"File {filename} not found in loaded files")
                        continue

                    file_info = self.loaded_files[filename]
                    if track_idx >= len(file_info['tracks']):
                        logger.info(f"Track index {track_idx} out of range")
                        continue

                    track = file_info['tracks'][track_idx]
                    bpm = file_info['bpm']
                    tpqn = file_info.get('tpqn', 480)

                    # Convert MIDI track to loop format
                    logger.info(f"Converting MIDI track to loop format: {len(track['events'])} events at {bpm} BPM")
                    loop_events = self.convert_midi_to_loop_format(track['events'], bpm, tpqn)

                    if loop_events:
                        # Calculate timing
                        timing = self.calculate_loop_timing(loop_events, bpm, track.get('maxTicks'), False)

                        # Create loop data
                        loop_data = self.create_loop_data_from_events(loop_events, loop_num, bpm, timing, False)

                        # Load to device
                        self.load_progress_label.setText(f"Loading Loop {loop_num} Main...")
                        success = self.load_loop_data_to_device(loop_data, loop_num)

                        if not success:
                            QMessageBox.warning(None, "Warning", f"Failed to load Loop {loop_num} Main")
                            break

                    completed += 1
                    progress = int((completed / total_assignments) * 100)
                    self.load_progress_bar.setValue(progress)

                if 'overdub' in assignments:
                    # Load overdub track
                    track_info = assignments['overdub']
                    filename = track_info['filename']
                    track_idx = track_info['track_idx']

                    logger.info(f"Loading overdub track {track_idx} from {filename} to Loop {loop_num}")

                    # Get file info
                    if filename not in self.loaded_files:
                        logger.info(f"File {filename} not found in loaded files")
                        continue

                    file_info = self.loaded_files[filename]
                    if track_idx >= len(file_info['tracks']):
                        logger.info(f"Track index {track_idx} out of range")
                        continue

                    track = file_info['tracks'][track_idx]
                    bpm = file_info['bpm']
                    tpqn = file_info.get('tpqn', 480)

                    # Convert MIDI track to loop format
                    logger.info(f"Converting MIDI track to loop format: {len(track['events'])} events at {bpm} BPM")
                    loop_events = self.convert_midi_to_loop_format(track['events'], bpm, tpqn)

                    if loop_events:
                        # Calculate timing
                        timing = self.calculate_loop_timing(loop_events, bpm, track.get('maxTicks'), False)

                        # Create loop data
                        loop_data = self.create_loop_data_from_events(loop_events, loop_num, bpm, timing, True)

                        # Load to device
                        self.load_progress_label.setText(f"Loading Loop {loop_num} Overdub...")
                        success = self.load_loop_data_to_device(loop_data, loop_num)

                        if not success:
                            QMessageBox.warning(None, "Warning", f"Failed to load Loop {loop_num} Overdub")
                            break

                    completed += 1
                    progress = int((completed / total_assignments) * 100)
                    self.load_progress_bar.setValue(progress)

            self.load_progress_label.setText("All assigned tracks loaded")
            self.load_progress_bar.setValue(100)

            # Clear pending assignments
            self.pending_assignments = {}
            self.update_assignment_buttons()

            QTimer.singleShot(2000, self.reset_transfer_state)

        except Exception as e:
            logger.info(f"Error in on_load_assignments: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(None, "Error", f"Failed to load assignments: {str(e)}")
            self.reset_transfer_state()

    def update_assignment_buttons(self):
        """Update assignment button states and labels"""
        for i in range(8):
            loop_num = i + 1

            # Main button
            if loop_num in self.pending_assignments and 'main' in self.pending_assignments[loop_num]:
                track_info = self.pending_assignments[loop_num]['main']
                filename = track_info['filename']
                file_info = self.loaded_files.get(filename)
                if file_info:
                    track_idx = track_info['track_idx']
                    track = file_info['tracks'][track_idx]
                    duration_ms = track.get('duration_ms', 0)
                    # Format: "Loop X\nTrack Y\nZms" with green background
                    self.main_assign_btns[i].setText(f"Loop {loop_num}\nTrack {track_idx + 1}\n{duration_ms}ms")
                    self.main_assign_btns[i].setStyleSheet("""
                        QPushButton {
                            background-color: #2ecc71;
                            color: white;
                            border: 2px solid #27ae60;
                            border-radius: 4px;
                            font-weight: bold;
                            padding: 5px;
                        }
                        QPushButton:hover {
                            background-color: #27ae60;
                        }
                    """)
                    self.main_clear_btns[i].setVisible(True)
                else:
                    self.main_assign_btns[i].setText(f"Loop {loop_num}\nPending")
                    self.main_assign_btns[i].setStyleSheet("""
                        QPushButton {
                            background-color: #f39c12;
                            color: white;
                            border: 2px solid #e67e22;
                            border-radius: 4px;
                            font-weight: bold;
                            padding: 5px;
                        }
                    """)
                    self.main_clear_btns[i].setVisible(True)
            else:
                self.main_assign_btns[i].setText(f"Loop {loop_num}")
                self.main_assign_btns[i].setStyleSheet("")  # Reset to default
                self.main_clear_btns[i].setVisible(False)

            # Overdub button
            has_main = loop_num in self.loop_contents or (
                loop_num in self.pending_assignments and 'main' in self.pending_assignments[loop_num]
            )
            self.overdub_assign_btns[i].setEnabled(has_main)

            if loop_num in self.pending_assignments and 'overdub' in self.pending_assignments[loop_num]:
                track_info = self.pending_assignments[loop_num]['overdub']
                filename = track_info['filename']
                file_info = self.loaded_files.get(filename)
                if file_info:
                    track_idx = track_info['track_idx']
                    track = file_info['tracks'][track_idx]
                    duration_ms = track.get('duration_ms', 0)
                    # Format: "Overdub X\nTrack Y\nZms" with green background
                    self.overdub_assign_btns[i].setText(f"Overdub {loop_num}\nTrack {track_idx + 1}\n{duration_ms}ms")
                    self.overdub_assign_btns[i].setStyleSheet("""
                        QPushButton {
                            background-color: #2ecc71;
                            color: white;
                            border: 2px solid #27ae60;
                            border-radius: 4px;
                            font-weight: bold;
                            padding: 5px;
                        }
                        QPushButton:hover {
                            background-color: #27ae60;
                        }
                    """)
                    self.overdub_clear_btns[i].setVisible(True)
                else:
                    self.overdub_assign_btns[i].setText(f"Overdub {loop_num}\nPending")
                    self.overdub_assign_btns[i].setStyleSheet("""
                        QPushButton {
                            background-color: #f39c12;
                            color: white;
                            border: 2px solid #e67e22;
                            border-radius: 4px;
                            font-weight: bold;
                            padding: 5px;
                        }
                    """)
                    self.overdub_clear_btns[i].setVisible(True)
            else:
                self.overdub_assign_btns[i].setText(f"Overdub {loop_num}")
                self.overdub_assign_btns[i].setStyleSheet("")  # Reset to default
                self.overdub_clear_btns[i].setVisible(False)

        # Update track button colors based on assignments
        self.update_track_button_colors()

    def on_clear_main_assignment(self, loop_num):
        """Clear main loop assignment"""
        if loop_num in self.pending_assignments and 'main' in self.pending_assignments[loop_num]:
            del self.pending_assignments[loop_num]['main']
            if not self.pending_assignments[loop_num]:  # If no assignments left for this loop
                del self.pending_assignments[loop_num]
            self.update_assignment_buttons()
            # Disable load button if no assignments left
            if not self.pending_assignments:
                self.load_assignments_btn.setEnabled(False)

    def on_clear_overdub_assignment(self, loop_num):
        """Clear overdub loop assignment"""
        if loop_num in self.pending_assignments and 'overdub' in self.pending_assignments[loop_num]:
            del self.pending_assignments[loop_num]['overdub']
            if not self.pending_assignments[loop_num]:  # If no assignments left for this loop
                del self.pending_assignments[loop_num]
            self.update_assignment_buttons()
            # Disable load button if no assignments left
            if not self.pending_assignments:
                self.load_assignments_btn.setEnabled(False)

    def update_track_button_colors(self):
        """Update track button colors to highlight assigned tracks"""
        # Get all buttons from the track button group
        for button in self.track_button_group.buttons():
            filename = button.property('filename')
            track_idx = button.property('track_idx')

            # Check if this track is assigned to any loop
            is_assigned = False
            for loop_num, assignments in self.pending_assignments.items():
                for assign_type in ['main', 'overdub']:
                    if assign_type in assignments:
                        track_info = assignments[assign_type]
                        if track_info['filename'] == filename and track_info['track_idx'] == track_idx:
                            is_assigned = True
                            break
                if is_assigned:
                    break

            # Update button style based on assignment status
            palette = QApplication.palette()
            btn_color = palette.color(QPalette.Button).name()
            btn_text = palette.color(QPalette.ButtonText).name()
            highlight_color = palette.color(QPalette.Highlight).name()
            highlight_text = palette.color(QPalette.HighlightedText).name()
            alt_base = palette.color(QPalette.AlternateBase).name()
            light_color = palette.color(QPalette.Light).name()
            bright_text = palette.color(QPalette.BrightText).name()

            if is_assigned:
                # Use green color for assigned tracks
                button.setStyleSheet(f"""
                    QPushButton {{
                        background-color: #2ecc71;
                        color: white;
                        border: 2px solid #27ae60;
                        border-radius: 4px;
                        font-weight: bold;
                        padding: 5px;
                    }}
                    QPushButton:hover {{
                        background-color: #27ae60;
                        color: white;
                    }}
                    QPushButton:checked {{
                        background-color: #27ae60;
                        color: white;
                        border-color: #27ae60;
                    }}
                    QPushButton:disabled {{
                        background-color: {alt_base};
                        color: {light_color};
                    }}
                """)
            else:
                # Default style
                button.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {btn_color};
                        color: {btn_text};
                        border: 2px solid {light_color};
                        border-radius: 4px;
                        font-weight: bold;
                        padding: 5px;
                    }}
                    QPushButton:hover {{
                        background-color: {alt_base};
                    }}
                    QPushButton:checked {{
                        background-color: {highlight_color};
                        color: {highlight_text};
                        border-color: {highlight_color};
                    }}
                    QPushButton:disabled {{
                        background-color: {alt_base};
                        color: {light_color};
                    }}
                """)

    def handle_device_response(self, data):
        """Handle incoming HID data from device"""
        logger.info(f"handle_device_response called with {len(data)} bytes")

        if len(data) < self.HID_HEADER_SIZE:
            logger.info(f"Data too short: {len(data)} < {self.HID_HEADER_SIZE}")
            return

        # Validate header
        if (data[0] != self.MANUFACTURER_ID or
            data[1] != self.SUB_ID or
            data[2] != self.DEVICE_ID):
            logger.info(f"Invalid header: {data[0]:02x} {data[1]:02x} {data[2]:02x}")
            return

        command = data[3]
        macro_num = data[4]
        status = data[5]
        payload = data[self.HID_HEADER_SIZE:]

        logger.info(f"Valid packet - Command: 0x{command:02x}, Loop: {macro_num}, Status: {status}")

        if command == self.HID_CMD_SAVE_START:
            logger.info("-> SAVE_START")
            self.handle_save_start(macro_num, status, payload)
        elif command == self.HID_CMD_SAVE_CHUNK:
            logger.info("-> SAVE_CHUNK")
            self.handle_save_chunk(macro_num, status, payload)
        elif command == self.HID_CMD_SAVE_END:
            logger.info("-> SAVE_END")
            self.handle_save_end(macro_num, status)
        elif command == self.HID_CMD_REQUEST_SAVE:
            logger.info(f"-> REQUEST_SAVE acknowledgment (loop {macro_num}, status {status})")
            # Device acknowledged the request, now waiting for SAVE_START
        elif command == self.HID_CMD_TRIGGER_SAVE_ALL:
            logger.info(f"-> TRIGGER_SAVE_ALL acknowledgment (status {status})")
            # Device acknowledged the trigger, will send individual loop data
        elif command == self.HID_CMD_LOAD_START or command == self.HID_CMD_LOAD_OVERDUB_START:
            logger.info(f"-> {'LOAD_START' if command == self.HID_CMD_LOAD_START else 'LOAD_OVERDUB_START'} acknowledgment")
            # Device acknowledged load start
        elif command == self.HID_CMD_LOAD_END:
            logger.info(f"-> LOAD_END acknowledgment (loop {macro_num}, status {status})")
            # Device acknowledged load completion
        else:
            logger.info(f"-> Unknown command: 0x{command:02x}")

    def handle_save_start(self, macro_num, status, data):
        """Handle SAVE_START response from device"""
        logger.info(f"handle_save_start: loop={macro_num}, status={status}, data_len={len(data)}")

        if status != 0:
            logger.info(f"Loop {macro_num} status error: {status}")
            # Loop is empty, skip if in save all mode
            if self.current_transfer.get('save_all_mode'):
                logger.info(f"Loop {macro_num} is empty, skipping...")
                # Move to next loop
                self.current_transfer['save_all_current'] += 1
                QTimer.singleShot(100, self.save_next_loop_in_sequence)
            else:
                self.transfer_complete.emit(False, f"Loop {macro_num} is empty or error occurred")
            return

        # Extract total packets and size from payload - MATCHES WEBAPP FORMAT!
        # Webapp: totalPackets = data[0] | (data[1] << 8); totalSize = data[2] | (data[3] << 8);
        if len(data) >= 4:
            total_packets = data[0] | (data[1] << 8)
            total_size = data[2] | (data[3] << 8)

            self.current_transfer['expected_packets'] = total_packets
            self.current_transfer['total_size'] = total_size

            logger.info(f"SAVE_START: {total_packets} packets, {total_size} bytes total")
        else:
            logger.info(f"Warning: SAVE_START payload too short: {len(data)} bytes")

        self.transfer_progress.emit(0,
            f"Receiving Loop {macro_num}: 0 / {self.current_transfer['total_size']} bytes")

    def handle_save_chunk(self, macro_num, status, data):
        """Handle SAVE_CHUNK response from device"""
        if not self.current_transfer['active']:
            logger.info("handle_save_chunk: transfer not active, ignoring")
            return

        # Parse chunk header - MATCHES WEBAPP FORMAT!
        # Webapp: packetNum = data[0] | (data[1] << 8); chunkLen = data[2] | (data[3] << 8);
        if len(data) >= 4:
            packet_num = data[0] | (data[1] << 8)
            chunk_len = data[2] | (data[3] << 8)

            if chunk_len > 0 and len(data) >= 4 + chunk_len:
                # Extract actual chunk data
                chunk_data = data[4:4 + chunk_len]
                self.current_transfer['received_data'].extend(chunk_data)
                self.current_transfer['received_packets'] += 1

                # Calculate progress
                received = len(self.current_transfer['received_data'])
                total = self.current_transfer['total_size']
                expected_packets = self.current_transfer['expected_packets']

                logger.info(f"Chunk {self.current_transfer['received_packets']}/{expected_packets}: packet#{packet_num}, {chunk_len} bytes (total: {received}/{total})")

                if expected_packets > 0:
                    progress = int((self.current_transfer['received_packets'] / expected_packets) * 100)
                    self.transfer_progress.emit(progress,
                        f"Receiving Loop {macro_num}: {received} / {total} bytes ({progress}%)")
            else:
                logger.info(f"handle_save_chunk: invalid chunk - len={chunk_len}, data_len={len(data)}")
        else:
            logger.info(f"handle_save_chunk: payload too short: {len(data)} bytes")

    def handle_save_end(self, macro_num, status):
        """Handle SAVE_END response from device"""
        logger.info(f"handle_save_end: loop={macro_num}, status={status}")

        if not self.current_transfer['active']:
            logger.info("handle_save_end: transfer not active, ignoring")
            return

        if status == 0:
            try:
                received_data = bytes(self.current_transfer['received_data'])
                received_size = len(received_data)
                logger.info(f"Received {received_size} bytes for loop {macro_num}")

                # Check if in save all mode
                if self.current_transfer.get('save_all_mode'):
                    logger.info(f"Save all mode: storing loop {macro_num} data")

                    # Store the loop data
                    if 'save_all_data' not in self.current_transfer:
                        self.current_transfer['save_all_data'] = {}

                    self.current_transfer['save_all_data'][macro_num] = received_data

                    # Extract and track max BPM
                    bpm = self.extract_bpm_from_loop_data(received_data)
                    if bpm > self.current_transfer.get('save_all_max_bpm', 0):
                        self.current_transfer['save_all_max_bpm'] = bpm

                    logger.info(f"Stored loop {macro_num}, BPM: {bpm}")

                    # Move to next loop
                    self.current_transfer['save_all_current'] += 1
                    self.current_transfer['active'] = False  # Reset for next loop
                    QTimer.singleShot(100, self.save_next_loop_in_sequence)

                else:
                    # Individual save - extract BPM first, then prompt for filename
                    bpm = self.extract_bpm_from_loop_data(received_data)
                    logger.info(f"Extracted BPM: {bpm}")

                    # Determine file extension and default name with BPM
                    if self.current_transfer['save_format'] == 'midi':
                        filter_str = "MIDI Files (*.midi);;All Files (*)"
                        default_name = f"loop{macro_num}_{bpm}.midi"
                    else:
                        filter_str = "Loop Files (*.loop);;All Files (*)"
                        default_name = f"loop{macro_num}_{bpm}.loop"

                    # Prompt for filename with BPM included
                    filename, _ = QFileDialog.getSaveFileName(
                        None, f"Save Loop {macro_num} ({bpm} BPM)", default_name, filter_str
                    )

                    if not filename:
                        # User cancelled
                        logger.info("User cancelled save")
                        self.reset_transfer_state()
                        return

                    logger.info(f"User chose filename: {filename}")

                    if self.current_transfer['save_format'] == 'midi':
                        # Convert to MIDI
                        logger.info("Converting to MIDI format...")

                        # Parse the loop data
                        parsed = self.parse_loop_data(received_data)

                        if parsed:
                            logger.info(f"Parsed loop data successfully")

                            # Convert to MIDI
                            loops_data = {macro_num: parsed}
                            midi_data = self.convert_loop_to_midi(loops_data, bpm)

                            if midi_data:
                                with open(filename, 'wb') as f:
                                    f.write(midi_data)
                                logger.info(f"Successfully saved MIDI file: {filename}")
                                self.save_progress_label.setText(f"Saved to {os.path.basename(filename)}")
                                self.save_progress_bar.setValue(100)
                            else:
                                logger.info("Failed to create MIDI data")
                                QMessageBox.warning(None, "Warning", "Failed to convert to MIDI")
                        else:
                            logger.info("Failed to parse loop data")
                            QMessageBox.warning(None, "Warning", "Failed to parse loop data")

                    else:
                        # Save as .loop file (raw data)
                        with open(filename, 'wb') as f:
                            f.write(received_data)

                        logger.info(f"Successfully saved loop file: {filename}")
                        self.save_progress_label.setText(f"Saved to {os.path.basename(filename)}")
                        self.save_progress_bar.setValue(100)

                    # Reset after a short delay (no popup notification)
                    QTimer.singleShot(2000, self.reset_transfer_state)

            except Exception as e:
                logger.info(f"Error saving file: {e}")
                QMessageBox.critical(None, "Error", f"Failed to save file: {str(e)}")
                self.reset_transfer_state()

        else:
            logger.info(f"SAVE_END with error status: {status}")
            # Check if in save all mode
            if self.current_transfer.get('save_all_mode'):
                logger.info(f"Loop {macro_num} had error, skipping and continuing...")
                # Continue to next loop even on error
                self.current_transfer['save_all_current'] += 1
                self.current_transfer['active'] = False
                QTimer.singleShot(100, self.save_next_loop_in_sequence)
            else:
                QMessageBox.warning(None, "Warning", f"Failed to receive Loop {macro_num}")
                self.reset_transfer_state()

    def on_transfer_progress(self, progress, message):
        """Update UI with transfer progress (thread-safe)"""
        self.save_progress_label.setText(message)
        self.save_progress_bar.setValue(progress)

    def on_transfer_complete(self, success, message):
        """Handle transfer completion (thread-safe) - NO POPUP NOTIFICATIONS"""
        # Just update the UI, no popup notifications
        if success:
            self.save_progress_label.setText(message)
            self.save_progress_bar.setValue(100)
        else:
            # Only show popup for errors
            QMessageBox.warning(None, "Warning", message)

        # Reset after a short delay
        QTimer.singleShot(2000, self.reset_transfer_state)

    def reset_transfer_state(self):
        """Reset transfer state"""
        self.current_transfer = {
            'active': False,
            'is_loading': False,
            'loop_num': 0,
            'expected_packets': 0,
            'received_packets': 0,
            'total_size': 0,
            'received_data': bytearray(),
            'file_name': '',
            'save_format': 'loop',
            'save_all_mode': False,
            'save_all_data': {},
            'save_all_current': 0,
            'save_all_max_bpm': 120.0
        }

        self.save_progress_label.setText("")
        self.save_progress_bar.setValue(0)
        self.save_progress_bar.setVisible(False)

        self.load_progress_label.setText("")
        self.load_progress_bar.setValue(0)
        self.load_progress_bar.setVisible(False)

        # Stop HID listener when transfer completes to prevent blocking other HID operations
        self.stop_hid_listener()

    def update_loop_contents_display(self):
        """Update the loop contents display"""
        # Only update if labels exist
        if not self.loop_content_labels:
            return

        for i in range(8):
            loop_num = i + 1
            if loop_num in self.loop_contents:
                self.loop_content_labels[i].setText(self.loop_contents[loop_num])
            else:
                self.loop_content_labels[i].setText(tr("LoopManager", "Empty"))

    def valid(self):
        """This tab is valid for all VialKeyboard devices"""
        return isinstance(self.device, VialKeyboard)

    def rebuild(self, device):
        super().rebuild(device)
        if not self.valid():
            self.stop_hid_listener()
            return

        # Rebuild ThruLoop tab
        if hasattr(self, 'thruloop_tab'):
            self.thruloop_tab.device = self.device
            self.thruloop_tab.rebuild(device)

        # Don't start HID listener automatically - only start when needed during transfers
        # This prevents continuous polling that blocks other HID operations

        # Reset state when device changes
        self.reset_transfer_state()
        self.loop_contents = {}
        self.overdub_contents = {}
        self.update_loop_contents_display()

    def __del__(self):
        """Cleanup on deletion"""
        self.stop_hid_listener()
