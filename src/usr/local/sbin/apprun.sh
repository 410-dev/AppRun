#!/bin/bash

# ==============================================================================
# Helpers
# ==============================================================================

show_gui_alert() {
    local title="$1"
    local message="$2"
    local type="$3" # --warning or --error

    echo "AppRun: $message"

    if command -v zenity >/dev/null 2>&1; then
        zenity "$type" --text="$message" --title="$title" --width=400
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog "$type" --text="$message" --title="$title"
    fi
}

# ==============================================================================
# Initialization & Preparation
# ==============================================================================

if [[ -z "$1" ]]; then
    echo "Usage: apprun.sh <AppRun bundle path> [args...]"
    exit 1
fi

BUNDLE_PATH="$1"
META_DIR="$BUNDLE_PATH/AppRunMeta"
shift # Remove bundle path from args, leaving only application arguments

# Run preparation script
/usr/local/sbin/apprun-prepare.sh "$BUNDLE_PATH"
if [ $? -ne 0 ]; then
    exit $?
fi

# ==============================================================================
# Determine Execution Mode (Interpreter & Main File)
# ==============================================================================

CMD_ARRAY=()
BOX_PATH="$(getent passwd $(whoami) | cut -f6 -d:)/.local/apprun/boxes"

if [ -f "$BUNDLE_PATH/main.py" ]; then
    # --- Python Setup ---
    mkdir -p "$BOX_PATH/pycache"
    export PYTHONPYCACHEPREFIX="$BOX_PATH/pycache"

    # Handle Libraries / PYTHONPATH
    LIBS_FILE=""
    [[ -f "$BUNDLE_PATH/libs" ]] && LIBS_FILE="$BUNDLE_PATH/libs"
    [[ -f "$BUNDLE_PATH/AppRunMeta/libs" ]] && LIBS_FILE="$BUNDLE_PATH/AppRunMeta/libs"

    if [[ -n "$LIBS_FILE" ]]; then
        DICT_VAL="$(cat "$LIBS_FILE")"
        PYTHON_PATH_ADD="$(/usr/bin/python3 /usr/local/sbin/dictionary.py --dict-collection=apprun-python --string="$DICT_VAL")"
        export PYTHONPATH="$PYTHON_PATH_ADD:$PYTHONPATH"
    fi

    # Define Python Interpreter
    APP_ID="$(/usr/local/sbin/appid.sh "$BUNDLE_PATH")"
    INTERPRETER="$BOX_PATH/$APP_ID/pyvenv/bin/python3"

    CMD_ARRAY=("$INTERPRETER" "$BUNDLE_PATH/main.py")

elif [ -f "$BUNDLE_PATH/main.jar" ]; then
    # --- Java Setup ---
    CMD_ARRAY=(java -jar "$BUNDLE_PATH/main.jar")

elif [ -f "$BUNDLE_PATH/main.sh" ]; then
    # --- Bash Setup ---
    CMD_ARRAY=(bash "$BUNDLE_PATH/main.sh")

elif [ -x "$BUNDLE_PATH/main" ]; then
    # --- Binary Setup ---
    CMD_ARRAY=("$BUNDLE_PATH/main")

else
    echo "No valid main file found to execute in bundle: $BUNDLE_PATH"
    exit 10
fi

# ==============================================================================
# Handle Root Privileges (Sudo)
# ==============================================================================

if [[ -f "$META_DIR/EnforceRootLaunch" ]]; then
    if [[ -f "$META_DIR/KeepEnvironment" ]]; then
        CMD_ARRAY=(sudo -E "${CMD_ARRAY[@]}")
    else
        CMD_ARRAY=(sudo "${CMD_ARRAY[@]}")
    fi
fi

# ==============================================================================
# Handle Screen Execution (New Feature)
# ==============================================================================

SCREEN_CONFIG="$META_DIR/LaunchInScreen"
USE_SCREEN=false

if [[ -f "$SCREEN_CONFIG" ]]; then
    SCREEN_MODE="$(cat "$SCREEN_CONFIG" 2>/dev/null | tr -d '[:space:]')"
    # Default to "recommend" if empty
    [[ -z "$SCREEN_MODE" ]] && SCREEN_MODE="recommend"

    if command -v screen >/dev/null 2>&1; then
        USE_SCREEN=true
    else
        if [[ "$SCREEN_MODE" == "enforced" ]]; then
            echo "Error: 'screen' is required but not installed."
            show_gui_alert "AppRun Missing Requirement" "This application requires 'screen' to run, but it was not found on your system." "--error"
            exit 127
        else
            # Recommend mode: Warning but proceed
            show_gui_alert "AppRun Suggestion" "This application recommends running in 'screen', but it is not installed. Launching normally." "--warning"
        fi
    fi
fi

if [[ "$USE_SCREEN" == true ]]; then
    # Generate a session name based on the bundle directory name
    SESSION_NAME="apprun_$(basename "$BUNDLE_PATH")_$$"

    # prepend screen command
    # -D -m: Start screen in detached mode but don't fork (waits for session to end)
    # -S: Name the session
    CMD_ARRAY=(screen -D -m -S "$SESSION_NAME" "${CMD_ARRAY[@]}")
fi

# ==============================================================================
# Execution & Monitoring
# ==============================================================================

start_time=$(date +%s)

# Execute the final constructed command with arguments
"${CMD_ARRAY[@]}" "$@"
exit_code=$?

end_time=$(date +%s)
duration=$((end_time - start_time))

# ==============================================================================
# Crash Detection & Reporting
# ==============================================================================

# Check if we need to perform crash detection (Only for Application type)
APP_TYPE="$(/usr/local/sbin/apprunutil.sh GetProperty "$BUNDLE_PATH" "DesktopLink/Type")"

if [[ "$APP_TYPE" == "Application" ]]; then
    # If exited with error OR (duration < 1s and not a clean exit)
    # Note: original logic implied duration < 1 is bad regardless of exit code,
    # but usually if exit_code is 0 and duration is short, it might just be a help flag or quick task.
    # However, strictly following your prompt's logic:

    if [[ $duration -lt 1 ]] || [[ $exit_code -ne 0 ]]; then
        if [[ $exit_code -ne 0 ]]; then
            title="AppRun Application Crash"
            message="The application has exited with a non-zero exit code ($exit_code). Please check the application logs, or run the application in a terminal for more details."
            option="--error"
        else
            title="AppRun Application Terminated Quickly"
            message="The application terminated too quickly, which may indicate a crash immediately after launch. Please check the application logs or run the application in a terminal for more details."
            option="--warning"
        fi

        show_gui_alert "$title" "$message" "$option"
    fi
f

exit $exit_code
