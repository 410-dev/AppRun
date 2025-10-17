#!/bin/bash

if [ -f "$1/AppRunMeta/id" ]; then
    cat "$1/AppRunMeta/id"
elif [ -f "$1/id" ]; then
    cat "$1/id"
else
    # If ends with .apprun, append "_application"
    if [[ "$1" == *.apprun ]] || [[ "$1" == *.apprun/ ]]; then
        echo "$(basename "$1" .apprun)_application"
    else
        echo "$(basename "$1")_unknowntype"
    fi
fi
