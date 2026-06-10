# PyInstaller hook for rtmidi
# This ensures rtmidi and its dependencies are properly included in the frozen application

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

# Collect all rtmidi modules, binaries, and data files
datas, binaries, hiddenimports = collect_all('rtmidi')

# Also collect dynamic libraries explicitly
binaries += collect_dynamic_libs('rtmidi')

# Ensure these modules are imported
hiddenimports += [
    'rtmidi',
    'rtmidi.midiutil',
    'rtmidi.midiconstants',
]
