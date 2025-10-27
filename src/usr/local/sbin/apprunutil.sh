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
    echo "  BundleInfo [AppRunPath]                   Show bundle information"
    echo ""
elif [[ "$1" == "Prepare" ]]; then
    # Call /usr/local/sbin/apprun-prepare.sh
    /usr/local/sbin/apprun-prepare.sh "$2"
    exit $?
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
        echo ""
    else
        echo ""
    fi
elif [[ "$1" == "ListProperties" ]]; then
    # List all properties in the AppRunMeta directory
    # There could be subdirectories - find it recursively while containing the directory name
    APP_RUN_PATH="$2"
    if [[ -d "$APP_RUN_PATH/AppRunMeta" ]]; then
        find "$APP_RUN_PATH/AppRunMeta" -type f | while read -r file; do
            PROPERTY_NAME=$(realpath --relative-to="$APP_RUN_PATH/AppRunMeta" "$file")
            echo "$PROPERTY_NAME"
        done
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
elif [[ "$1" == "BundleInfo" ]]; then
    # Show bundle info
    #   Format (If contains AppRunMeta/id file then it is format 2. If it contains just id file then it is format 1 which does not show any further information other than id)
    #   ID (from AppRunMeta/id or ./id) [Format 1 shows this only]
    #   Version (from AppRunMeta/Version or AppRunMeta/DesktopLink/Version)
    #   Name (from AppRunMeta/DesktopLink/Name or AppRunMeta/Name)
    #   Library loads (from AppRunMeta/libs)
    #   Application Type (Any of Java, Python, Bash, Binary - Type identified by extension of main file in the bundle root)

    APP_RUN_PATH="$2"
    if [[ -f "$APP_RUN_PATH/AppRunMeta/id" ]]; then
        echo "Format: 2"
        echo "ID: $(cat "$APP_RUN_PATH/AppRunMeta/id")"
    elif [[ -f "$APP_RUN_PATH/id" ]]; then
        echo "Format: 1"
        echo "ID: $(cat "$APP_RUN_PATH/id")"
    else
        echo "Unidentifiable format."
        exit 1
    fi

    if [[ -f "$APP_RUN_PATH/AppRunMeta/Version" ]]; then
        echo "Version: $(cat "$APP_RUN_PATH/AppRunMeta/Version")"
    elif [[ -f "$APP_RUN_PATH/AppRunMeta/DesktopLink/Version" ]]; then
        echo "Version: $(cat "$APP_RUN_PATH/AppRunMeta/DesktopLink/Version")"
    fi

    if [[ -f "$APP_RUN_PATH/AppRunMeta/DesktopLink/Name" ]]; then
        echo "Name: $(cat "$APP_RUN_PATH/AppRunMeta/DesktopLink/Name")"
    elif [[ -f "$APP_RUN_PATH/AppRunMeta/Name" ]]; then
        echo "Name: $(cat "$APP_RUN_PATH/AppRunMeta/Name")"
    fi

    if [[ -f "$APP_RUN_PATH/AppRunMeta/libs" ]]; then
        echo "Library loads:"
        cat "$APP_RUN_PATH/AppRunMeta/libs"
    fi

    # Determine Application Type
    if [[ -f "$APP_RUN_PATH/main.jar" ]]; then
        echo "Application Type: Java"
    elif [[ -f "$APP_RUN_PATH/main.py" ]]; then
        echo "Application Type: Python"
    elif [[ -f "$APP_RUN_PATH/main.sh" ]]; then
        echo "Application Type: Bash"
    elif [[ -f "$APP_RUN_PATH/main" ]]; then
        echo "Application Type: Binary"
    fi
    
    exit 0

else
    echo "Unknown command. Use 'apprunutil.sh Help' for usage information."
fi
