# Security Hardening Notes - 2026-05-14

This note documents the refactor driven by `inspection-report-0514-compiled.md`.
The main goal is to keep bundle-controlled data behind explicit validation and
serialization boundaries before AppRun performs host operations.

## New Shared Modules

Shared helpers live in `src/usr/lib/python3/dist-packages/` so installed entry
points and the DropIn service use the same rules.

- `apprun_validation.py`
  - Validates bundle IDs, Debian package names, systemd unit names, bundled
    service paths, desktop scalar values, and safe relative paths.
  - Raises `ValidationError` for untrusted values that would become path
    fragments, command operands, or line-oriented config values.

- `apprun_desktop.py`
  - Serializes `.desktop` files from fixed templates.
  - Formats `Exec=` from argv-style lists instead of shell strings.
  - Parses bundled desktop files with an allowlist and always overrides
    host-sensitive keys such as `Exec`, `Icon`, `Type`, and `StartupWMClass`.

- `apprun_systemd.py`
  - Serializes generated systemd units with newline/control-character rejection.
  - Validates dependency unit names and formats `ExecStart=` from argv-style
    lists.

- `apprun_safeio.py`
  - Provides no-final-symlink writes for privileged paths.
  - Uses file descriptors for mode and ownership changes so chmod/chown do not
    follow a hostile final symlink.

## Refactored Callers

- `apprun_cli`
  - Handles `--is-format3` before any prepare/run path.
  - Validates apt package names, bundled service paths, service names, generated
    dependency units, and generated app IDs.
  - Replaces systemctl shell batching with direct argv calls.
  - Uses the shared desktop and systemd serializers for generated launchers and
    services.
  - Writes `.desktop` files with `0644`.
  - Fast successful exits only warn when metadata opts in with
    `warn_on_fast_exit`.

- DropIn service
  - Rejects unsafe bundle IDs instead of using them in per-user paths.
  - Writes desktop/icon files through no-symlink helpers with `0644` desktop
    mode.
  - Generates desktop files from an allowlist instead of passing bundled lines
    through unchanged.
  - Saves cache files atomically and catches per-event registration failures.

- `libapprun`
  - Is now a directory package with a stable `__init__.py` export surface.
  - Validates returned bundle IDs centrally.
  - Uses exact `/proc/mounts` matching and cryptographic random mount suffixes.
  - Validates package names from `apt-requirements`.

- `AppContext.py`
  - Keeps the single-file layout as requested.
  - Confines `file_in_box`, `has_file_in_box`, `read`, and `write` to the
    resolved AppRun box root and rejects absolute paths, `..`, NUL bytes, and
    symlink escapes.
  - Keeps file cache bytes as bytes.
  - Supports `AppRunMeta/DesktopLinks` with legacy `DesktopLink` fallback.

## Packaging And Utility Changes

- Debian `postinst` no longer runs `curl | sh`; `uv` is now a package
  dependency and configuration fails clearly if it is unavailable.
- Debian `prerm` uses the correct `AppRunDropInService.apprunx` casing.
- Build scripts avoid recursive ownership/mode mutation of the workspace and
  `build-nogui.sh` restores `control` through a trap.
- `dictionary.py` confines dictionary collections under
  `/usr/share/dictionaries`.
- `apprun-package.py` refuses to overwrite output unless `--force` is supplied.
- `apprunx-thumbnailer.py` bounds icon size, accepts only PNG icon data, clamps
  thumbnail size, and sets ImageMagick timeouts.

## Remaining Work

The current patch addresses the highest-risk validation and shell-injection
paths, but deeper hardening still needs dedicated tests and design work:

- Drop privileges before writing into user homes from the root DropIn daemon.
- Replace remaining root-owned user-home directory creation with stricter
  parent-chain ownership checks.
- Add integration tests for malicious bundle IDs, service names, desktop files,
  symlinked targets, malformed metadata, and `--is-format3` non-execution.
- Revisit direct bundled service installation UX so privileged directives are
  summarized before installation.
