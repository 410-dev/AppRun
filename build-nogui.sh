#!/bin/bash
# If no argument, make deb file from src (no GUI dependencies)

if [ -z "$1" ]; then
    # Temporarily patch control file to remove GUI dependencies
    CONTROL="src/DEBIAN/control"
    cp "$CONTROL" "$CONTROL.bak"

    sed -i 's/, imagemagick//' "$CONTROL"
    sed -i 's/, zenity//' "$CONTROL"

    ./build.sh nogui

    # Restore original control file
    mv "$CONTROL.bak" "$CONTROL"
fi
exit 0
