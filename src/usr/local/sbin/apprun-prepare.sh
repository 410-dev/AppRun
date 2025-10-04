#!/bin/bash

appid="$(/usr/local/sbin/appid.sh "$1")"
appBoxRoot="$(getent passwd $(whoami) | cut -f6 -d:)/.local/apprun/boxes/"

if [[ ! -d "$appBoxRoot" ]]; then
    mkdir -p "$appBoxRoot"
fi

if [[ ! -d "$appBoxRoot/$appid" ]]; then
    echo "Preparing application cache for $appid..."
    mkdir -p "$appBoxRoot/$appid"
fi


if [ -f "$1/main.py" ]; then
    if [ ! -f "$appBoxRoot/$appid/pyvenv/bin/python3" ]; then
        python3 -m venv "$appBoxRoot/$appid/pyvenv"
    fi

    if [ -f "$1/requirements.txt" ]; then

        # Check checksum of requirements.txt
        if [ -f "$appBoxRoot/$appid/requirements.txt.checksum" ]; then
            old_checksum=$(cat "$appBoxRoot/$appid/requirements.txt.checksum")
        else
            old_checksum=""
        fi

        new_checksum=$(md5sum "$1/requirements.txt" | awk '{ print $1 }')

        if [[ "$old_checksum" == "" ]]; then
            echo "$new_checksum" > "$appBoxRoot/$appid/requirements.txt.checksum"
            echo "First time setup, installing dependencies..."
            echo "Running preinstallation..."
            "$appBoxRoot/$appid/pyvenv/bin/python3" -m pip install --upgrade pip setuptools wheel
            "$appBoxRoot/$appid/pyvenv/bin/python3" -m pip install -r "$1/requirements.txt"

        elif [[ "$old_checksum" != "$new_checksum" ]]; then
            echo "$new_checksum" > "$appBoxRoot/$appid/requirements.txt.checksum"
            echo "Requirements file changed, reinstalling dependencies..."
            rm -rf "$appBoxRoot/$appid/pyvenv"
            python3 -m venv "$appBoxRoot/$appid/pyvenv"
            echo "Running preinstallation..."
            "$appBoxRoot/$appid/pyvenv/bin/python3" -m pip install --upgrade pip setuptools wheel
            "$appBoxRoot/$appid/pyvenv/bin/python3" -m pip install -r "$1/requirements.txt"

        fi
    fi
fi
