#!/bin/bash

# If no argument, make deb file from src
if [ -z "$1" ] || [ "$1" == "nogui" ]; then

    # Package src/usr/lib/AppRun/apprundropinf3.apprunxproj
    if [[ ! -z "$(which apprun3-package)" ]]; then
        apprun3-package src/usr/lib/AppRun/AppRunDropInService.apprunxproj --output src/usr/lib/AppRun/AppRunDropInService.apprunx
    elif [[ ! -z "$(which apprun-package)" ]]; then
        apprun-package src/usr/lib/AppRun/AppRunDropInService.apprunxproj --output src/usr/lib/AppRun/AppRunDropInService.apprunx
    else
        echo "Error: No apprun packaging tool found (apprun3-package or apprun-package)"
        exit 1
    fi

    sudo chown -R root:root src
    sudo chmod -R 755 src
    sudo dpkg-deb --build src
    sudo chown -R $USER:$USER src
    sudo chmod -R 755 src
    sudo chown $USER src.deb
    if [[ "$1" == "nogui" ]]; then
        mv src.deb apprun-nogui.deb
    else
        mv src.deb apprun.deb
    fi
fi

exit 0
