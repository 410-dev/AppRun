#!/bin/bash
set -euo pipefail

MODE="gui"
OUTPUT="apprun.deb"

usage() {
    cat <<'EOF'
Usage:
  ./build.sh
  ./build.sh --no-gui

Options:
  --no-gui   Build the headless package as apprun-headless.deb.
             The headless package does not include the DropIn desktop daemon
             and does not depend on GUI/desktop integration packages.
EOF
}

die() {
    echo "Error: $*" >&2
    exit 1
}

case "${1:-}" in
    "")
        ;;
    "--no-gui")
        MODE="headless"
        OUTPUT="apprun-headless.deb"
        ;;
    "-h"|"--help")
        usage
        exit 0
        ;;
    *)
        die "unknown option: $1"
        ;;
esac

if [ "$#" -gt 1 ]; then
    die "too many arguments"
fi

WORKDIR="$(mktemp -d)"
cleanup() {
    rm -rf "$WORKDIR"
}
trap cleanup EXIT

cp -a src "$WORKDIR/"
STAGE="$WORKDIR/src"

find "$STAGE" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$STAGE" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm"

package_dropin_daemon() {
    local stage="$1"
    local project="$stage/usr/lib/AppRun/AppRunDropInService.apprunxproj"
    local output="$stage/usr/lib/AppRun/AppRunDropInService.apprunx"

    if command -v apprun3-package >/dev/null 2>&1; then
        apprun3-package "$project" --output "$output" --force
    elif command -v apprun-package >/dev/null 2>&1; then
        apprun-package "$project" --output "$output" --force
    else
        die "No apprun packaging tool found (apprun3-package or apprun-package)"
    fi
}

write_headless_maintainer_scripts() {
    local stage="$1"

    cat > "$stage/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e

if ! command -v uv >/dev/null 2>&1; then
    echo "Error: uv is required but is not installed. Install the distribution uv package before configuring AppRun." >&2
    exit 1
fi

orig_files_map_to=(
    "apprun"
    "apprun-package"
    "dictionary"
)

for file in "${orig_files_map_to[@]}"; do
    if [ -f "/usr/bin/${file}.py" ]; then
        chmod +x "/usr/bin/${file}.py"
        ln -sf "/usr/bin/${file}.py" "/usr/bin/${file}"
    elif [ -f "/usr/bin/${file}.sh" ]; then
        chmod +x "/usr/bin/${file}.sh"
        ln -sf "/usr/bin/${file}.sh" "/usr/bin/${file}"
    else
        echo "Error: ${file} was not found in /usr/bin/"
        exit 1
    fi
done

ln -fs "/usr/bin/apprun" "/usr/bin/apprun3"
ln -fs "/usr/bin/apprun-package" "/usr/bin/apprun3-package"

if [ -f "/usr/lib/python3/dist-packages/AppContext.py" ]; then
    rm -f "/usr/lib/python3/dist-packages/AppContext.py"
fi
ln -fs "/usr/lib/AppRun/libs/AppContext.py" "/usr/lib/python3/dist-packages/AppContext.py"
EOF

    cat > "$stage/DEBIAN/prerm" <<'EOF'
#!/bin/bash

lns=(
    "/usr/bin/apprun"
    "/usr/bin/dictionary"
    "/usr/bin/apprun3"
    "/usr/bin/apprun-package"
    "/usr/bin/apprun3-package"
)

for file in "${lns[@]}"; do
    if [ -L "${file}" ]; then
        rm -f "${file}"
    fi
done
EOF

    chmod 755 "$stage/DEBIAN/postinst" "$stage/DEBIAN/prerm"
}

patch_headless_control() {
    local control="$1"
    local patched="$control.headless"

    awk '
        $1 == "Package:" {
            print "Package: apprun-headless"
            next
        }
        $1 == "Version:" {
            version = $2
            print
            print "Provides: apprun (= " version ")"
            print "Conflicts: apprun"
            print "Replaces: apprun"
            next
        }
        $1 == "Depends:" {
            line = $0
            sub(/^Depends:[[:space:]]*/, "", line)
            count = split(line, deps, /,[[:space:]]*/)
            output = ""
            for (i = 1; i <= count; i++) {
                dep = deps[i]
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", dep)
                if (dep == "python3-inotify" || dep == "python3-pyinotify" || dep == "imagemagick" || dep == "zenity" || dep == "libnotify-bin") {
                    continue
                }
                output = output (output ? ", " : "") dep
            }
            print "Depends: " output
            next
        }
        { print }
    ' "$control" > "$patched"
    mv "$patched" "$control"
}

prepare_headless_stage() {
    local stage="$1"

    patch_headless_control "$stage/DEBIAN/control"
    write_headless_maintainer_scripts "$stage"

    rm -rf "$stage/usr/lib/AppRun/AppRunDropInService.apprunxproj"
    rm -f "$stage/usr/lib/AppRun/AppRunDropInService.apprunx"
    rm -f "$stage/usr/bin/apprunx-thumbnailer.py"
    rm -f "$stage/usr/share/applications/apprun3.desktop"
    rm -f "$stage/usr/share/thumbnailers/apprunx.thumbnailer"
    rm -f "$stage/usr/share/mime/packages/apprunx.xml"
    rm -f "$stage/usr/share/apprun/apprun.png"
    rm -f "$stage/usr/share/apprun/badge.png"
    rm -f "$stage/usr/share/apprun/default-icon.png"
}

if [ "$MODE" = "gui" ]; then
    package_dropin_daemon "$STAGE"
else
    prepare_headless_stage "$STAGE"
fi

dpkg-deb --root-owner-group --build "$STAGE" "$OUTPUT"
