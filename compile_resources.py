#!/usr/bin/env python3
"""
Simple script to compile Qt resources (.qrc) to Python (.py)
"""
import xml.etree.ElementTree as ET
import base64
import os
import sys

def compile_qrc(qrc_file, output_file):
    """Compile a .qrc file to a Python resource file"""

    # Parse the QRC XML file
    tree = ET.parse(qrc_file)
    root = tree.getroot()

    # Get the directory of the QRC file for resolving relative paths
    qrc_dir = os.path.dirname(os.path.abspath(qrc_file))

    # Start building the Python file content
    output = []
    output.append("# -*- coding: utf-8 -*-")
    output.append("")
    output.append("# Resource object code")
    output.append("#")
    output.append("# Created by: compile_resources.py")
    output.append("#")
    output.append("# WARNING! All changes made in this file will be lost!")
    output.append("")
    output.append("from PyQt5 import QtCore")
    output.append("")
    output.append("qt_resource_data = b\"\\")

    # Dictionary to store file data and offsets
    file_data = {}
    current_offset = 0
    data_parts = []

    # Process each file in the QRC
    for qresource in root.findall('qresource'):
        for file_elem in qresource.findall('file'):
            alias = file_elem.get('alias', file_elem.text)
            file_path = file_elem.text

            # Resolve file path relative to QRC file
            full_path = os.path.join(qrc_dir, file_path)

            # Read the file data
            with open(full_path, 'rb') as f:
                data = f.read()

            # Store file info
            file_data[alias] = {
                'offset': current_offset,
                'size': len(data),
                'data': data
            }

            current_offset += len(data)
            data_parts.append(data)

    # Combine all file data
    all_data = b''.join(data_parts)

    # Convert to hex string representation
    hex_str = all_data.hex()
    # Split into lines of 80 characters
    for i in range(0, len(hex_str), 80):
        chunk = hex_str[i:i+80]
        output.append(f"\\x{chunk[0:2]}".replace("\\x", "\\x") + "".join(f"\\x{chunk[j:j+2]}" for j in range(2, len(chunk), 2)))

    output.append("\"")
    output.append("")

    # Build the resource tree structure
    output.append("qt_resource_name = b\"\\")
    name_data = []
    name_offsets = {}

    for alias in file_data.keys():
        name_offsets[alias] = len(b''.join(name_data))
        # Length (2 bytes) + name hash (4 bytes) + name utf16
        name_utf16 = alias.encode('utf-16-be')
        name_len = len(alias)
        # Pack: length (2 bytes big-endian), hash (4 bytes big-endian), name
        # Calculate hash and ensure it fits in 4 bytes signed
        name_hash = hash(alias) & 0xFFFFFFFF
        if name_hash >= 0x80000000:
            name_hash -= 0x100000000
        name_entry = name_len.to_bytes(2, 'big') + name_hash.to_bytes(4, 'big', signed=True) + name_utf16
        name_data.append(name_entry)

    all_names = b''.join(name_data)
    hex_names = all_names.hex()
    for i in range(0, len(hex_names), 80):
        chunk = hex_names[i:i+80]
        if chunk:
            output.append("".join(f"\\x{chunk[j:j+2]}" for j in range(0, len(chunk), 2)))

    output.append("\"")
    output.append("")

    # Build resource structure
    output.append("qt_resource_struct = b\"\\")
    struct_parts = []

    # Root entry
    struct_parts.append(b'\x00\x00\x00\x00\x00\x02\x00\x00\x00\x01\x00\x00\x00\x01')

    # File entries
    for i, (alias, info) in enumerate(file_data.items()):
        # name_offset (4 bytes), flags (2 bytes), child_count/file_offset (4 bytes), last_modified (4 bytes)
        name_off = name_offsets[alias]
        flags = 0  # File flag
        struct_entry = (
            name_off.to_bytes(4, 'big') +
            flags.to_bytes(2, 'big') +
            info['offset'].to_bytes(4, 'big') +
            b'\x00\x00\x00\x00'  # last modified
        )
        struct_parts.append(struct_entry)

    all_struct = b''.join(struct_parts)
    hex_struct = all_struct.hex()
    for i in range(0, len(hex_struct), 80):
        chunk = hex_struct[i:i+80]
        if chunk:
            output.append("".join(f"\\x{chunk[j:j+2]}" for j in range(0, len(chunk), 2)))

    output.append("\"")
    output.append("")

    # Add the registration function
    output.append("def qInitResources():")
    output.append("    QtCore.qRegisterResourceData(0x03, qt_resource_struct, qt_resource_name, qt_resource_data)")
    output.append("")
    output.append("def qCleanupResources():")
    output.append("    QtCore.qUnregisterResourceData(0x03, qt_resource_struct, qt_resource_name, qt_resource_data)")
    output.append("")
    output.append("qInitResources()")

    # Write to output file
    with open(output_file, 'w') as f:
        f.write('\n'.join(output))

    print(f"Successfully compiled {qrc_file} -> {output_file}")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: compile_resources.py <input.qrc> <output.py>")
        sys.exit(1)

    compile_qrc(sys.argv[1], sys.argv[2])
