#!/usr/bin/env python3
"""Public AppRun command facade.

The user-facing command intentionally stays small.  The implementation lives in
``apprun_cli`` so subcommands can be maintained like a command suite while
``apprun`` continues to feel like one large command.
"""

import sys
from pathlib import Path

LOCAL_DIST_PACKAGES = Path(__file__).resolve().parents[1] / "lib/python3/dist-packages"
sys.path.insert(0, "/usr/lib/python3/dist-packages")
if LOCAL_DIST_PACKAGES.exists():
    sys.path.insert(0, str(LOCAL_DIST_PACKAGES))

from apprun_cli import main


if __name__ == "__main__":
    main()
