#!/bin/bash
# If no argument, make deb file from src (no GUI dependencies)

if [ -z "$1" ]; then
    # Temporarily patch control file to remove GUI dependencies
    CONTROL="src/DEBIAN/control"
    cp "$CONTROL" "$CONTROL.bak"

    sed -i 's/, imagemagick//' "$CONTROL"
    sed -i 's/, zenity//' "$CONTROL"

    sudo chown -R root:root src
    sudo chmod -R 755 src
    sudo dpkg-deb --build src
    sudo chown -R $USER:$USER src
    sudo chmod -R 755 src
    sudo chown $USER src.deb
    mv src.deb apprun-nogui.deb

    # Restore original control file
    mv "$CONTROL.bak" "$CONTROL"
fi
exit 0
