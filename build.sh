#!/bin/bash

# If no argument, make deb file from src
if [ -z "$1" ]; then
    sudo chown -R root:root src
    sudo chmod -R 755 src
    sudo dpkg-deb --build src
    sudo chown -R $USER:$USER src
    sudo chmod -R 755 src
    sudo chown $USER src.deb
    mv src.deb apprun.deb
fi

exit 0
