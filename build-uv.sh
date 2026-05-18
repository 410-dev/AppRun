#!/bin/bash
set -euo pipefail

UV_VERSION="${UV_VERSION:-0.11.14}"
PKG_REVISION="${PKG_REVISION:-1}"
BASE_URL="${UV_RELEASE_BASE_URL:-https://releases.astral.sh/github/uv/releases/download}"
ARCH="${1:-$(dpkg --print-architecture)}"

usage() {
    cat <<'EOF'
Usage:
  ./build-uv.sh [debian-architecture]

Environment:
  UV_VERSION            uv version to package. Default: 0.11.14
  PKG_REVISION          Debian package revision. Default: 1
  UV_RELEASE_BASE_URL   Release base URL. Default: https://releases.astral.sh/github/uv/releases/download

Examples:
  ./build-uv.sh
  ./build-uv.sh amd64
  UV_VERSION=0.11.14 ./build-uv.sh arm64
EOF
}

die() {
    echo "Error: $*" >&2
    exit 1
}

case "$ARCH" in
    "-h"|"--help")
        usage
        exit 0
        ;;
esac

if [ "$#" -gt 1 ]; then
    die "too many arguments"
fi

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "$1 is required"
}

uv_target_for_arch() {
    case "$1" in
        amd64) echo "x86_64-unknown-linux-gnu" ;;
        arm64) echo "aarch64-unknown-linux-gnu" ;;
        armhf) echo "armv7-unknown-linux-gnueabihf" ;;
        i386) echo "i686-unknown-linux-gnu" ;;
        ppc64el) echo "powerpc64le-unknown-linux-gnu" ;;
        riscv64) echo "riscv64gc-unknown-linux-gnu" ;;
        s390x) echo "s390x-unknown-linux-gnu" ;;
        *) die "unsupported Debian architecture: $1" ;;
    esac
}

require_cmd curl
require_cmd dpkg-deb
require_cmd sha256sum
require_cmd tar

UV_TARGET="$(uv_target_for_arch "$ARCH")"
ARCHIVE="uv-${UV_TARGET}.tar.gz"
URL="${BASE_URL}/${UV_VERSION}/${ARCHIVE}"
CHECKSUM_URL="${URL}.sha256"
PKG_VERSION="${UV_VERSION}-${PKG_REVISION}"
OUTPUT="apprun-uv_${PKG_VERSION}_${ARCH}.deb"

WORKDIR="$(mktemp -d)"
cleanup() {
    rm -rf "$WORKDIR"
}
trap cleanup EXIT

echo "Downloading uv ${UV_VERSION} for ${ARCH} (${UV_TARGET})..."
curl --proto '=https' --tlsv1.2 -LsSf "$URL" -o "$WORKDIR/$ARCHIVE"
curl --proto '=https' --tlsv1.2 -LsSf "$CHECKSUM_URL" -o "$WORKDIR/$ARCHIVE.sha256"

(cd "$WORKDIR" && sha256sum -c "$ARCHIVE.sha256")
tar -xzf "$WORKDIR/$ARCHIVE" -C "$WORKDIR"

EXTRACTED="$WORKDIR/uv-${UV_TARGET}"
[ -x "$EXTRACTED/uv" ] || die "uv binary was not found in $ARCHIVE"
[ -x "$EXTRACTED/uvx" ] || die "uvx binary was not found in $ARCHIVE"

STAGE="$WORKDIR/apprun-uv"
install -d "$STAGE/DEBIAN" "$STAGE/usr/bin" "$STAGE/usr/lib/uvs/$ARCH"
install -m 0755 "$EXTRACTED/uv" "$STAGE/usr/lib/uvs/$ARCH/uv"
install -m 0755 "$EXTRACTED/uvx" "$STAGE/usr/lib/uvs/$ARCH/uvx"
ln -s "../lib/uvs/$ARCH/uv" "$STAGE/usr/bin/uv"
ln -s "../lib/uvs/$ARCH/uvx" "$STAGE/usr/bin/uvx"

cat > "$STAGE/DEBIAN/control" <<EOF
Package: apprun-uv
Version: ${PKG_VERSION}
Section: devel
Priority: optional
Architecture: ${ARCH}
Maintainer: LKS410
Provides: uv (= ${PKG_VERSION})
Conflicts: uv
Replaces: uv
Depends: libc6, ca-certificates
Description: uv binaries packaged for AppRun
 Provides the official uv and uvx prebuilt binaries as a Debian package.
EOF

dpkg-deb --root-owner-group --build "$STAGE" "$OUTPUT"
