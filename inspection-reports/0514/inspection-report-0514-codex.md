# AppRun Inspection Report - 2026-05-14

## Scope

Inspected the AppRun repository source, packaging scripts, runtime launcher, DropIn daemon, helper library, desktop/thumbnailer integration, and build scripts. I explicitly excluded files whose names start with `inspection-report` from content reads.

Primary reviewed areas:

- Debian maintainer scripts and build scripts.
- Runtime launcher: `src/usr/bin/apprun.py`.
- Packaging and thumbnailing tools.
- Shared library: `src/usr/lib/python3/dist-packages/libapprun.py`.
- DropIn daemon: `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py`.
- App helper API: `src/usr/lib/AppRun/libs/AppContext.py`.
- Desktop, MIME, thumbnailer registration files.

Verification performed:

- `python3 -m py_compile` passed for all Python source files reviewed, with bytecode redirected to `/tmp/apprun-codex-pyc`.
- `bash -n` passed for `build.sh`, `build-nogui.sh`, `src/DEBIAN/postinst`, and `src/DEBIAN/prerm`.
- Runtime integration tests were not run because the important paths require root/systemd/FUSE/GUI behavior and would mutate the host.

## Executive Summary

AppRun intentionally executes untrusted `.apprunx` bundles, installs dependencies, creates desktop files, and can install systemd services. That makes input validation and privilege boundaries critical. The current implementation has several high-impact issues where bundle-controlled metadata or file names are reused as shell command text, filesystem paths, desktop entries, and systemd unit content without a consistent validation layer.

The highest priority fixes are:

1. Remove shell-string command construction for privileged/systemd and GUI-terminal execution paths.
2. Strictly validate bundle IDs, service file names, systemd unit names, package names, and desktop values.
3. Harden the root DropIn daemon against symlink writes in user-controlled directories.
4. Fix `--is-format3`, which is parsed but currently falls through to bundle execution.
5. Remove network `curl | sh` behavior from the package maintainer script.

## Findings

### 1. High: GUI terminal command path is shell injectable

Evidence:

- `src/usr/bin/apprun.py:338-348` builds `shell_cmd` with `" ".join(gui_cmds)` and runs it with `bash -c`.
- `src/usr/bin/apprun.py:445-449` passes `uv pip install ... -r <requirements>` into that helper.
- `src/usr/bin/apprun.py:500-508` uses the same helper for GUI package installation via `pkexec apt install`.
- `src/usr/lib/python3/dist-packages/libapprun.py:315-333` reads `apt-requirements` from bundle metadata; `_parse_pkg_requirement` at `src/usr/lib/python3/dist-packages/libapprun.py:251-260` returns unvalidated strings when no version operator is matched.

Impact:

A malicious bundle can place shell metacharacters in `apt-requirements`, bundle IDs that influence paths, or other command arguments. When a terminal emulator is available, AppRun constructs a shell string and executes it. This can execute unintended commands as the user, or as `pkexec`/root depending on the path.

Recommendation:

Do not join argv into shell text. If a terminal must show the command, use a tiny fixed wrapper script or `bash -c` with positional parameters, for example `bash -c 'exec "$@"' bash <argv...>`, and keep the status-display logic out of interpolated command strings. Validate package names against a conservative Debian package-name regex before any install attempt.

### 2. High: Bundled service file names can inject root shell commands

Evidence:

- `src/usr/bin/apprun.py:878-907` accepts every `services/*.service` entry and uses `Path(...).name` without validating it as a systemd unit name.
- `src/usr/bin/apprun.py:1874-1878` builds `systemctl` commands by joining service names into a shell string.
- `src/usr/bin/apprun.py:1881-1892` stops/disables a service through another unquoted shell string.
- `src/usr/bin/apprun.py:1716-1737` repeats the same service-name trust during uninstall.

Impact:

If a bundle contains a service file with a malicious file name and the user runs `--install-services --enable`, `--install-services --start`, or uninstall paths, the service name is interpolated into `bash -c` as root.

Recommendation:

Reject service file names that do not match a strict unit-name allowlist such as `[A-Za-z0-9_.@-]+\.service`. Prefer direct `subprocess.run(["systemctl", action, *svc_names])` calls. If batching through a shell remains, quote every unit name with `shlex.quote`, but validation should still be mandatory.

### 3. High: Bundle IDs are trusted as path fragments

Evidence:

- `src/usr/lib/python3/dist-packages/libapprun.py:37-63` returns `AppRunMeta/id` directly.
- `src/usr/lib/python3/dist-packages/libapprun.py:157-182` uses the ID in mount, box, and portable data paths.
- `src/usr/bin/apprun.py:844-863` uses the ID in icon and `.desktop` output paths.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:398-408` uses the ID in per-user desktop and icon paths.

Impact:

An ID containing `/`, `..`, control characters, or newlines can escape intended storage directories, create malformed desktop files, or write under unexpected locations. Several later call sites sanitize service names, but the core ID remains unvalidated and is reused broadly.

Recommendation:

Introduce one canonical `validate_app_id()` / `safe_app_id()` layer. Treat raw bundle IDs as untrusted display data only. For path use, reject separators, `..`, empty components, control characters, and names outside a documented format such as reverse-DNS plus `[A-Za-z0-9_.-]`. After joining paths, resolve and enforce containment under the intended root.

### 4. High: Root DropIn daemon follows user-controlled symlinks when writing files

Evidence:

- `src/DEBIAN/postinst:57` installs the DropIn bundle as a service.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:201-215` writes a path with `write_text`/`write_bytes`, then `chmod`, then `os.chown`.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:398-408` writes `.desktop` and icon files into each user's home directory.

Impact:

The daemon runs as root and writes into user-controlled directories. A local user can pre-create target paths as symlinks. Python file writes follow symlinks, so the daemon may overwrite an arbitrary root-writable path with content controlled by an `.apprunx` bundle, especially through the icon extraction path.

Recommendation:

Never write root-owned content to user-controlled paths by following existing pathnames. Use `os.open` with `O_NOFOLLOW | O_CREAT | O_EXCL`, write to a new temp file in a safe directory, `fsync`, then `rename` only after `lstat` checks. Consider dropping to the target user's UID before writing user-home files. Refuse symlinked parent directories and target files.

### 5. High: `--is-format3` is parsed but can execute the bundle

Evidence:

- `src/usr/bin/apprun.py:1928-1930` parses `--is-format3`.
- `src/usr/bin/apprun.py:2042-2082` handles many flags but has no `is_format3` branch before falling through to `handle_run`.

Impact:

A user or integration that calls `apprun3 --is-format3 file.apprunx` expects a harmless format check. Instead, the flag is ignored at dispatch and the bundle may be mounted, prepared, and executed.

Recommendation:

Handle `is_format3` before any execution path. It should only inspect package structure and print `true`/`false` with a reliable exit code.

### 6. High: Maintainer script downloads and runs an installer as root

Evidence:

- `src/DEBIAN/postinst:5-13` runs `curl -LsSf https://astral.sh/uv/install.sh | sh`, then moves binaries into `/usr/local/bin`.

Impact:

Package installation depends on live network behavior and a mutable remote shell script. This weakens reproducibility, breaks offline installs, and creates a supply-chain execution path during package installation.

Recommendation:

Declare `uv` as a package dependency where possible, vendor a specific verified binary with checksum/signature validation, or fail with a clear message telling the operator to install `uv` through a trusted package source. Avoid writing unmanaged files to `/usr/local/bin` from a Debian package maintainer script.

### 7. Medium: Generated systemd units accept unsanitized metadata and unit dependencies

Evidence:

- `src/usr/bin/apprun.py:998-999` converts `After` and `Before` spec strings without validating unit names.
- `src/usr/bin/apprun.py:1260-1283` inserts bundle metadata into generated system units.
- `src/usr/bin/apprun.py:1378-1398` does the same for global user units.

Impact:

Newlines or invalid characters in metadata/spec inputs can create malformed unit files or inject additional directives. The risk is especially sensitive because these paths are used for system and global user service creation.

Recommendation:

Validate dependency unit names with a systemd unit-name allowlist. Sanitize all unit file values by rejecting or escaping newlines and control characters. Generate units through a small serializer that enforces allowed sections and directives.

### 8. Medium: Desktop `Exec` lines and desktop values are inconsistently escaped

Evidence:

- `src/usr/bin/apprun.py:852-863` writes a desktop file with `Exec=apprun3 {apprunx_path}` unquoted.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:261-296` rewrites `Exec` and `Icon` fields without escaping path/app ID values.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:307-339` generates desktop files from metadata without type checks or desktop-value escaping.
- A safer formatter exists at `src/usr/bin/apprun.py:1127-1144`, but it is only used for GUI autostart.

Impact:

Paths with spaces can fail to launch. Metadata with newlines or special desktop-entry characters can inject additional keys. Field-code handling may also become ambiguous.

Recommendation:

Use one desktop-entry writer everywhere. Escape `Exec` arguments with the existing `_format_desktop_exec` approach, sanitize all key values with newline/control-character removal, and validate `Type`, `Terminal`, `Categories`, and `StartupWMClass`.

### 9. Medium: `AppContext` box file APIs allow path traversal

Evidence:

- `src/usr/lib/AppRun/libs/AppContext.py:258-259` joins caller input directly under the box path.
- `src/usr/lib/AppRun/libs/AppContext.py:360-380` writes `filename` after a direct join.
- `src/usr/lib/AppRun/libs/AppContext.py:382-413` reads `filename` after a direct join.

Impact:

The API presents itself as box-scoped file I/O, but `../` or absolute-looking subpaths can escape the AppRun box and read/write any path the process can access.

Recommendation:

Normalize with `Path(self._apprun_box_path, filename).resolve()` and require the result to stay under `Path(self._apprun_box_path).resolve()`. Reject absolute paths, `..`, NUL/control characters, and symlink escapes where appropriate.

### 10. Medium: DropIn service uninstall path has a case mismatch

Evidence:

- `src/DEBIAN/postinst:57` installs `/usr/lib/AppRun/AppRunDropInService.apprunx`.
- `src/DEBIAN/prerm:3` tries to uninstall `/usr/lib/AppRun/AppRunDropinService.apprunx`.

Impact:

On case-sensitive filesystems, package removal may fail to remove the service that was installed, leaving a stale systemd service or stored bundle behind.

Recommendation:

Use one constant path in both scripts and add a package removal test that installs then purges the package in a disposable environment.

### 11. Medium: DropIn daemon can be destabilized by malformed metadata/config

Evidence:

- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:123-124` loads config JSON without schema validation.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:307-324` assumes metadata values are strings/lists and mutates `desktopfile-args`.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:543-561` event handlers call registration without local exception handling.

Impact:

A malformed `.apprunx` or config can crash event handling or cause repeated restart loops under systemd.

Recommendation:

Validate config and bundle metadata types before use. Catch per-file registration errors inside inotify event handlers so one bad bundle cannot take down the daemon.

### 12. Medium: Maintainer script uses `sudo` and broad cache deletion after `set +e`

Evidence:

- `src/DEBIAN/postinst:66-71` switches to `set +e`, calls `sudo update-*`, runs `xdg-mime`, and deletes `~/.cache/thumbnails/`.

Impact:

Debian maintainer scripts already run as root and may not have `sudo`. `~` is the maintainer-script environment home, not necessarily the desktop user's home, so cache cleanup is likely ineffective or can affect the wrong account. `set +e` also hides failures in MIME/desktop registration.

Recommendation:

Remove `sudo` from maintainer scripts. Run cache/database updates directly where appropriate, tolerate known non-critical failures explicitly, and avoid deleting user caches from a package install script.

### 13. Medium: Thumbnailer extracts and processes untrusted icon bytes without limits

Evidence:

- `src/usr/lib/python3/dist-packages/libapprun.py:109-117` captures full extracted file bytes in memory.
- `src/usr/bin/apprunx-thumbnailer.py:35-45` accepts input/output/size from the thumbnailer request and processes the extracted icon.
- `src/usr/bin/apprunx-thumbnailer.py:70-99` invokes ImageMagick `convert` without size, timeout, or format validation.

Impact:

A crafted bundle can force large memory use, expensive ImageMagick processing, or parser exposure during thumbnail generation.

Recommendation:

Cap extracted icon size, reject unreasonable thumbnail sizes, use subprocess timeouts, and consider a safer image decoding path with explicit PNG validation.

### 14. Low: Mount detection uses substring matching

Evidence:

- `src/usr/lib/python3/dist-packages/libapprun.py:149-152` checks `mp in line` for each `/proc/mounts` line.

Impact:

One mount path can be falsely considered mounted if it is a substring of another mount entry. This can lead to incorrect unmount attempts or confusing runtime failures.

Recommendation:

Parse `/proc/mounts` fields and compare the decoded mountpoint field exactly.

### 15. Low: Build scripts mutate ownership and permissions broadly

Evidence:

- `build.sh:16-21` recursively changes ownership and mode for the entire `src` tree and generated package.
- `build-nogui.sh:7-15` edits `src/DEBIAN/control` in place and restores it only at the end.

Impact:

The build process makes all package files mode `755`, including data and metadata, and can leave the source tree with wrong ownership or modified control metadata if interrupted. The no-GUI build also removes `imagemagick` and `zenity` but not `libnotify-bin`, while the README says to remove all three.

Recommendation:

Use `dpkg-deb --root-owner-group` or `fakeroot` instead of recursive `sudo chown`. Stage no-GUI builds in a temporary directory or use a trap for restoration. Preserve file modes and align no-GUI dependency removal with documentation.

### 16. Low: AppContext has correctness bugs in cache and icon paths

Evidence:

- `src/usr/lib/AppRun/libs/AppContext.py:382-413` documents/returns bytes, but the cache path can return a decoded string stored at `src/usr/lib/AppRun/libs/AppContext.py:407-410`.
- `src/usr/lib/AppRun/libs/AppContext.py:488` uses `AppRunMeta/DesktopLink/Icon.png`, while the rest of the project uses `AppRunMeta/DesktopLinks/Icon.png`.
- `src/usr/lib/AppRun/libs/AppContext.py:601-602` uses the same singular `DesktopLink` path for terminal metadata.

Impact:

Callers can receive inconsistent types from `read()`, and icon/terminal detection may silently fail for Format 3 bundles that follow the documented `DesktopLinks` directory.

Recommendation:

Keep cache entries in the same type as `read()` returns, or split byte/string cache APIs. Update singular `DesktopLink` paths to documented `DesktopLinks` paths, with backward-compatible fallback if needed.

## Cross-Cutting Hardening Recommendations

1. Add a central validation module for app IDs, package names, systemd unit names, service specs, desktop values, and safe relative paths.
2. Replace all privileged shell-string batching with direct argv calls or a tightly controlled wrapper that does not interpolate untrusted input.
3. Make root/user boundary writes explicit: drop privileges where possible, never follow symlinks in user-writable paths, and enforce path containment after `resolve()`.
4. Treat `.apprunx` files as untrusted archives until the user intentionally launches them. Format checks, thumbnailing, DropIn scanning, and registration should not execute shell-like behavior or write arbitrary host paths.
5. Add regression tests for malicious IDs, malicious service names, paths with spaces, malformed metadata, symlinked user targets, and `--is-format3`.
6. Move package installation behavior behind explicit, auditable prompts and validate package names before invoking apt.

## Suggested Priority Order

1. Fix `--is-format3` fall-through.
2. Remove command injection in `_run_cmd_gui_term_prefer`.
3. Validate service names and remove shell-string systemctl batching.
4. Validate/sanitize bundle IDs and enforce path containment.
5. Harden DropIn writes against symlinks.
6. Remove `curl | sh` from `postinst`.
7. Normalize desktop/systemd file generation with safe serializers.
