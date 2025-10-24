#!/bin/bash

if [[ "$1" == "Help" ]] || [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    echo "Usage: apprunutil.sh [Command] [Arguments]"
    echo ""
    echo "Note: This utility only detects AppRun bundle Format 2."
    echo ""
    echo "Commands:"
    echo "  Help                                      Show this help message"
    echo "  Prepare [AppRunPath]                      Prepare the AppRun environment"
    echo "  HasProperty [AppRunPath] [PropertyName]   Check if the AppRun has a specific property"
    echo "  GetProperty [AppRunPath] [PropertyName]   Get the value of a specific property from the AppRun"
    echo "  ListProperties [AppRunPath]               List all properties in the AppRun"
    echo "  ViewProperties [AppRunPath]               View all properties and their values in the AppRun"
    echo ""
elif [[ "$1" == "Prepare" ]]; then
    # Call /usr/local/sbin/apprun-prepare.sh
    shift
    /usr/local/sbin/apprun-prepare.sh "$@"
elif [[ "$1" == "HasProperty" ]]; then
    # Check if the bundle has a specific property in AppRunMeta/<property name> file
    APP_RUN_PATH="$2"
    PROPERTY_NAME="$3"
    if [[ -f "$APP_RUN_PATH/AppRunMeta/$PROPERTY_NAME" ]]; then
        echo "true"
    else
        echo "false"
    fi
elif [[ "$1" == "GetProperty" ]]; then
    # Get the value of a specific property from AppRunMeta/<property name> file
    APP_RUN_PATH="$2"
    PROPERTY_NAME="$3"
    if [[ -f "$APP_RUN_PATH/AppRunMeta/$PROPERTY_NAME" ]]; then
        cat "$APP_RUN_PATH/AppRunMeta/$PROPERTY_NAME"
    else
        echo ""
    fi
elif [[ "$1" == "ListProperties" ]]; then
    # List all properties in the AppRunMeta directory
    APP_RUN_PATH="$2"
    if [[ -d "$APP_RUN_PATH/AppRunMeta" ]]; then
        ls -1 "$APP_RUN_PATH/AppRunMeta"
    fi
elif [[ "$1" == "ViewProperties" ]]; then
    # View all properties and their values in the AppRunMeta directory
    APP_RUN_PATH="$2"
    if [[ -d "$APP_RUN_PATH/AppRunMeta" ]]; then
        for file in "$APP_RUN_PATH/AppRunMeta"/*; do
            PROPERTY_NAME=$(basename "$file")
            PROPERTY_VALUE=$(cat "$file")
            echo "$PROPERTY_NAME: $PROPERTY_VALUE"
        done
    fi
else
    echo "Unknown command. Use 'apprunutil.sh Help' for usage information."
fi
