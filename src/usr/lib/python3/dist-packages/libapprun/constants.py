"""Constants used by the AppRun Format 3 runtime library."""

from pathlib import Path

BOXES_ROOT = Path.home() / ".local/apprun/boxes"
MOUNT_ROOT = Path.home() / ".local/apprun/mounts"
SQUASHFUSE = "/usr/bin/squashfuse"
FUSERMOUNT = "/usr/bin/fusermount"
UNSQUASHFS = "/usr/bin/unsquashfs"
MKSQUASHFS = "/usr/bin/mksquashfs"

