#!/bin/bash
# If no argument, make deb file from src (no GUI dependencies)

if [ -z "$1" ]; then
    # Temporarily patch control file to remove GUI dependencies
    CONTROL="src/DEBIAN/control"
    cp "$CONTROL" "$CONTROL.bak"
    trap 'mv "$CONTROL.bak" "$CONTROL"' EXIT

    sed -i 's/, imagemagick//' "$CONTROL"
    sed -i 's/, zenity//' "$CONTROL"

    ./build.sh nogui

    # Restore original control file
    mv "$CONTROL.bak" "$CONTROL"
    trap - EXIT
fi
exit 0
