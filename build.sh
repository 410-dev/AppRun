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

    dpkg-deb --root-owner-group --build src
    if [[ "$1" == "nogui" ]]; then
        mv src.deb apprun-nogui.deb
    else
        mv src.deb apprun.deb
    fi
fi

exit 0
