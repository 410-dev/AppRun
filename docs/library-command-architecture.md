# Library and Command Architecture

AppRun now separates public command entry points from implementation packages.
The goal is the same user experience as a large command such as `apt`, while
the internals stay maintainable and importable.

## Public Commands

The installed command remains:

```sh
apprun [--flags] <bundle.apprunx> [app args...]
apprun3 [--flags] <bundle.apprunx> [app args...]
```

`/usr/bin/apprun.py` is a facade.  It only prepares the local development import
path and calls:

```python
from apprun_cli import main
```

This keeps command discovery and packaging simple while allowing internals to
move between modules without changing the executable contract.

## `apprun_cli`

`apprun_cli` is the internal command package:

- `apprun_cli/__init__.py`
  - Stable package export for `main`.
- `apprun_cli/__main__.py`
  - Development entry point for `python3 -m apprun_cli`.
- `apprun_cli/main.py`
  - Tiny stable command-suite entry point.
- `apprun_cli/constants.py`
  - Paths, service store locations, supported option values, and binary paths.
- `apprun_cli/parser.py`
  - Flag parsing and option normalization.
- `apprun_cli/command.py`
  - Current command implementation and handlers.

Future handler splits should keep `apprun_cli.main.main()` stable.  A good next
step is to move handler groups from `command.py` into modules named after their
behavior, for example `runtime.py`, `services.py`, `gui_startup.py`, and
`parser.py`.

## `libapprun`

`libapprun` is now a directory package instead of one large `libapprun.py` file.
Existing imports still work:

```python
import libapprun
from libapprun import get_bundle_id, mount
```

The public surface is defined in `libapprun/__init__.py`.  Keep compatibility
there when moving implementation details.

Current modules:

- `libapprun/constants.py`
  - Runtime paths and external tool paths.
- `libapprun/bundle.py`
  - Bundle ID, metadata, `unsquashfs` reads, and bundle file listing.
- `libapprun/mounts.py`
  - FUSE mount lifecycle and mount path generation.
- `libapprun/boxes.py`
  - Box paths and lock-file helpers.
- `libapprun/ui.py`
  - Notification and GUI alert helpers.
- `libapprun/packages.py`
  - `apt-requirements` parsing and installed package checks.
- `libapprun/util.py`
  - General helpers such as checksums and subprocess wrappers.

Private compatibility exports with leading underscores are currently retained
because existing tools still call them.  New code should prefer public helpers
where possible.
