#!/bin/bash

/usr/local/sbin/apprun-prepare.sh "$1"
cmd="$1"
shift
if [ -f "$cmd/main.py" ]; then
    if [[ -f "$cmd/libs" ]]; then
        export PYTHONPATH="$(/usr/bin/python3 /usr/local/sbin/dictionary.py --dict-collection=apprun-python --string="$(cat "$cmd/libs")"):$PYTHONPATH" 
    fi
    "$(getent passwd $(whoami) | cut -f6 -d:)/.local/apprun/boxes/$(/usr/local/sbin/appid.sh "$cmd")/pyvenv/bin/python3" "$cmd/main.py" "$@"
fi
if [ -f "$cmd/main.jar" ]; then
    java -jar "$cmd/main.jar" "$@"
fi
