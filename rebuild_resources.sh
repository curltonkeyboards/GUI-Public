#!/bin/bash
# Recompile the Qt resource modules from their .qrc sources.
#
# The keyboard GUI reads images (backgrounds, controller art, etc.) from
# COMPILED resource modules, not the raw PNGs. After changing any image
# referenced by a .qrc, run this script and commit the regenerated *.py so
# the change actually shows up in the app.
#
# Requires pyrcc5 (ships with PyQt5: `pip install pyqt5`).
#
# Resource modules:
#   widgets/resources.py  <- widgets/resources.qrc  (backgrounds, controllers, switch crossection)
#   themes2.py            <- widgets/themes2.qrc     (backgrounds + ps4 controller)
# Both register :/backgroundlight and :/backgrounddark, so both must be rebuilt.

set -e

# Resolve paths relative to this script so it works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIDGETS_DIR="$SCRIPT_DIR/src/main/python/widgets"

if ! command -v pyrcc5 >/dev/null 2>&1; then
    echo "error: pyrcc5 not found. Install it with: pip install pyqt5" >&2
    exit 1
fi

cd "$WIDGETS_DIR"

echo "Compiling widgets/resources.qrc -> widgets/resources.py"
pyrcc5 resources.qrc -o resources.py

echo "Compiling widgets/themes2.qrc   -> themes2.py"
pyrcc5 themes2.qrc -o ../themes2.py

echo "Done. Remember to commit the regenerated resources.py and themes2.py."
