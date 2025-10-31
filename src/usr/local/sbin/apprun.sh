#!/bin/bash

/usr/local/sbin/apprun-prepare.sh "$1"
if [ $? -ne 0 ]; then
    exit $?
fi
cmd="$1"
shift

# Get current time to check the application run duration later
start_time=$(date +%s)
exit_code=9

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
            exit_code=$?
        else
            sudo "$(getent passwd $(whoami) | cut -f6 -d:)/.local/apprun/boxes/$(/usr/local/sbin/appid.sh "$cmd")/pyvenv/bin/python3" "$cmd/main.py" "$@"
            exit_code=$?
        fi
    else
        "$(getent passwd $(whoami) | cut -f6 -d:)/.local/apprun/boxes/$(/usr/local/sbin/appid.sh "$cmd")/pyvenv/bin/python3" "$cmd/main.py" "$@"
        exit_code=$?
    fi
elif [ -f "$cmd/main.jar" ]; then
    if [[ -f "$cmd/AppRunMeta/EnforceRootLaunch" ]]; then
        if [[ -f "$cmd/AppRunMeta/KeepEnvironment" ]]; then
            sudo -E java -jar "$cmd/main.jar" "$@"
            exit_code=$?
        else
            sudo java -jar "$cmd/main.jar" "$@"
            exit_code=$?
        fi
    else
        java -jar "$cmd/main.jar" "$@"
        exit_code=$?
    fi
elif [ -f "$cmd/main.sh" ]; then
    if [[ -f "$cmd/AppRunMeta/EnforceRootLaunch" ]]; then
        if [[ -f "$cmd/AppRunMeta/KeepEnvironment" ]]; then
            sudo -E bash "$cmd/main.sh" "$@"
            exit_code=$?
        else
            sudo bash "$cmd/main.sh" "$@"
            exit_code=$?
        fi
    else
        bash "$cmd/main.sh" "$@"
        exit_code=$?
    fi
elif [ -x "$cmd/main" ]; then
    if [[ -f "$cmd/AppRunMeta/EnforceRootLaunch" ]]; then
        if [[ -f "$cmd/AppRunMeta/KeepEnvironment" ]]; then
            sudo -E "$cmd/main" "$@"
            exit_code=$?
        else
            sudo "$cmd/main" "$@"
            exit_code=$?
        fi
    else
        "$cmd/main" "$@"
        exit_code=$?
    fi
else
    echo "No valid main file found to execute."
    exit 10
fi

# Get end time and calculate duration
end_time=$(date +%s)
duration=$((end_time - start_time))

# If bundle type is application, do time based crash detection
if [[ "$(/usr/local/sbin/apprunutil.sh GetProperty "$cmd" "DesktopLink/Type")" -ne "Application" ]]; then
    exit 0
fi

# If duration is less than 1 second, assume a crash and prompt graphical message
if [[ $duration -lt 1 ]] || [[ $exit_code -ne 0 ]]; then
    message="The application might have been crashed immediately after launch. Please check the application logs, or run the application in a terminal for more details."

    if [[ $exit_code -ne 0 ]]; then
        message="The application has exited with a non-zero exit code ($exit_code). Please check the application logs, or run the application in a terminal for more details."
    fi

    echo "AppRun: $message"

    if command -v zenity >/dev/null 2>&1; then
        zenity --error --text="$message" --title="AppRun Application Crash"
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --error --text="$message" --title="AppRun Application Crash"
    fi
fi