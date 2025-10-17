#!/bin/bash

/usr/local/sbin/apprun-prepare.sh "$1"
if [ $? -ne 0 ]; then
    exit $?
fi
cmd="$1"
shift
if [ -f "$cmd/main.py" ]; then
    if [[ -f "$cmd/libs" ]]; then
        export PYTHONPATH="$(/usr/bin/python3 /usr/local/sbin/dictionary.py --dict-collection=apprun-python --string="$(cat "$cmd/libs")"):$PYTHONPATH" 
    elif [[ -f "$cmd/AppRunMeta/libs" ]]; then
        export PYTHONPATH="$(/usr/bin/python3 /usr/local/sbin/dictionary.py --dict-collection=apprun-python --string="$(cat "$cmd/AppRunMeta/libs")"):$PYTHONPATH" 
    fi
    if [[ -f "$cmd/AppRunMeta/EnforceRootLaunch" ]]; then
        options=""
        if [[ -f "$cmd/AppRunMeta/KeepEnvironment" ]]; then
            sudo -E "$(getent passwd $(whoami) | cut -f6 -d:)/.local/apprun/boxes/$(/usr/local/sbin/appid.sh "$cmd")/pyvenv/bin/python3" "$cmd/main.py" "$@"
        else
            sudo "$(getent passwd $(whoami) | cut -f6 -d:)/.local/apprun/boxes/$(/usr/local/sbin/appid.sh "$cmd")/pyvenv/bin/python3" "$cmd/main.py" "$@"
        fi
    else
        "$(getent passwd $(whoami) | cut -f6 -d:)/.local/apprun/boxes/$(/usr/local/sbin/appid.sh "$cmd")/pyvenv/bin/python3" "$cmd/main.py" "$@"
    fi
elif [ -f "$cmd/main.jar" ]; then
    if [[ -f "$cmd/AppRunMeta/EnforceRootLaunch" ]]; then
        if [[ -f "$cmd/AppRunMeta/KeepEnvironment" ]]; then
            sudo -E java -jar "$cmd/main.jar" "$@"
        else
            sudo java -jar "$cmd/main.jar" "$@"
        fi
    else
        java -jar "$cmd/main.jar" "$@"
    fi
elif [ -f "$cmd/main.sh" ]; then
    if [[ -f "$cmd/AppRunMeta/EnforceRootLaunch" ]]; then
        if [[ -f "$cmd/AppRunMeta/KeepEnvironment" ]]; then
            sudo -E bash "$cmd/main.sh" "$@"
        else
            sudo bash "$cmd/main.sh" "$@"
        fi
    else
        bash "$cmd/main.sh" "$@"
    fi
elif [ -x "$cmd/main" ]; then
    if [[ -f "$cmd/AppRunMeta/EnforceRootLaunch" ]]; then
        if [[ -f "$cmd/AppRunMeta/KeepEnvironment" ]]; then
            sudo -E "$cmd/main" "$@"
        else
            sudo "$cmd/main" "$@"
        fi
    else
        "$cmd/main" "$@"
    fi
else
    echo "No valid main file found to execute."
    exit 10
fi
