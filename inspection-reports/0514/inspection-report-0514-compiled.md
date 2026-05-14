# AppRun Consolidated Inspection Report - 2026-05-14

Compiled from:

- `inspection-report-0514-claude.md`
- `inspection-report-0514-codex.md`
- `inspection-report-0514-gemini.md`

This report deduplicates the three reviewer reports and groups the findings by practical risk. It is a synthesized report, not a verbatim concatenation.

Citation format: each finding lists the source report sections that contained the same or materially overlapping content.

## Executive Summary

AppRun handles untrusted `.apprunx` bundles, extracts metadata, creates desktop entries, installs dependencies, mounts FUSE filesystems, and can install systemd services. The reviewed code currently lacks a consistent validation boundary between bundle-controlled data and privileged host operations.

The most urgent risks are local privilege escalation through the root DropIn daemon, shell command injection in privileged/systemd paths, untrusted bundle IDs used as path fragments, unsafe `.desktop` generation, and install-time execution of a remote `curl | sh` script.

Highest priority fixes:

1. Validate bundle IDs, service names, package names, systemd unit names, desktop values, and safe relative paths centrally.
2. Remove shell-string command construction where any argument can come from a bundle, filename, metadata, or user-controlled path.
3. Harden all root writes into user-controlled directories against symlink and path traversal attacks.
4. Fix `--is-format3` so it cannot fall through into bundle execution.
5. Remove network installer execution from Debian maintainer scripts.

## Critical Findings

### C1. DropIn daemon can write or overwrite files as root through path traversal and symlinks

Source reports: Claude C1 and H1; Codex Findings 3 and 4; Gemini 2.1.

Evidence:

- `src/DEBIAN/postinst:57` installs the DropIn bundle as a service.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:201-215` writes files with `write_text`/`write_bytes`, then runs `chmod` and `os.chown`.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:398-408` builds per-user desktop/icon paths using untrusted `app_id`.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:609-625` recursively changes ownership in paths under user homes.

Impact:

The DropIn service runs as root and writes into user-controlled home directories. A local user can use a crafted bundle ID with path traversal components, or pre-create symlinks at expected desktop/icon locations. The daemon can then follow the symlink, overwrite a root-writable target, and change its ownership or mode. This is a realistic local privilege escalation primitive.

Fix:

Reject unsafe bundle IDs before any path use. Use `os.open` with `O_NOFOLLOW | O_CREAT | O_EXCL`, operate on file descriptors with `fchmod`/`fchown`, and verify every parent directory with `lstat`. Prefer dropping privileges to the target user before writing into that user's home.

### C2. Privileged command injection through unquoted shell command construction

Source reports: Codex Findings 1, 2, 7, and 9; Claude M15; Gemini 2.2.

Evidence:

- `src/usr/bin/apprun.py:338-348` joins command arguments with `" ".join(gui_cmds)` and runs the result through `bash -c`.
- `src/usr/bin/apprun.py:500-508` uses that helper for GUI package installation with `pkexec apt install`.
- `src/usr/bin/apprun.py:878-907` accepts bundled `services/*.service` names without validating unit names.
- `src/usr/bin/apprun.py:1874-1878` and `src/usr/bin/apprun.py:1881-1892` build `systemctl` shell strings by joining service names.
- `src/usr/bin/apprun.py:1806-1817` runs arbitrary batched privileged scripts with `bash -c`.

Impact:

Bundle-controlled package names, file names, service names, paths, or metadata can be interpolated into shell strings. When these paths run through `pkexec`, `sudo`, or a root re-exec, the injection can become root command execution.

Fix:

Use direct argv-based `subprocess.run([...])` calls wherever possible. If a shell is unavoidable, use a fixed wrapper with positional parameters and quote every value. Validate Debian package names and systemd unit names with strict allowlists before invoking apt or systemctl.

### C3. Desktop entry injection and unsafe `.desktop` propagation

Source reports: Claude C2, C3, H2, and M11; Codex Finding 8.

Evidence:

- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:248-296` passes most lines from bundled `desktopfile.desktop` through unchanged.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:267`, `271`, and `330` write `Exec=apprun3 {apprunx_path}` without robust desktop-entry escaping.
- `src/usr/bin/apprun.py:852-863` writes `.desktop` files with unescaped `Name`, `Comment`, `Exec`, `Icon`, and `StartupWMClass` values.
- `src/usr/bin/apprun.py:1127-1144` has a safer formatter, but it is only used in GUI autostart paths.

Impact:

A malicious bundle can inject additional desktop keys, malformed values, field codes, or launch arguments. DropIn writes entries for all detected users, so one malicious bundle in a watched directory can create hostile application launchers across accounts.

Fix:

Do not pass through arbitrary `.desktop` keys from a bundle. Generate desktop files from a fixed template, sanitize all values by rejecting newlines/control characters, escape `Exec` arguments consistently, and reject path values containing dangerous desktop field-code characters where appropriate.

## High Findings

### H1. Bundle IDs are trusted as filesystem and UI identifiers

Source reports: Claude C1 and C2; Codex Finding 3.

Evidence:

- `src/usr/lib/python3/dist-packages/libapprun.py:37-63` returns `AppRunMeta/id` directly.
- `src/usr/lib/python3/dist-packages/libapprun.py:157-182` uses the ID in mount, box, and portable data paths.
- `src/usr/bin/apprun.py:844-863` uses the ID in desktop/icon file names.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:398-408` uses the ID in per-user desktop/icon paths.

Impact:

IDs containing `/`, `..`, newlines, leading dots, or control characters can escape intended directories, create invalid files, inject desktop content, or destabilize storage layout.

Fix:

Add a canonical ID validator. A reasonable default is reverse-DNS-like text using only `[A-Za-z0-9_.-]`, with no empty components, no `..`, no leading dash where used as a command operand, and no path separators.

### H2. `--is-format3` is parsed but can execute the bundle

Source reports: Codex Finding 5.

Evidence:

- `src/usr/bin/apprun.py:1928-1930` parses `--is-format3`.
- `src/usr/bin/apprun.py:2042-2082` does not dispatch that flag and falls through to `handle_run`.

Impact:

A caller expecting a harmless format check may mount, prepare, install dependencies for, or execute an untrusted bundle.

Fix:

Handle `--is-format3` before any run/prepare path. It should inspect only package structure and return `true`/`false`.

### H3. Debian `postinst` executes a remote installer as root

Source reports: Claude H7; Codex Finding 6.

Evidence:

- `src/DEBIAN/postinst:5-13` runs `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- `src/DEBIAN/postinst:8-24` assumes `$HOME/.local/bin/uv` and `uvx` were created and moves them into `/usr/local/bin`.

Impact:

Package installation depends on live network state and a mutable remote shell script. A compromised upstream, MITM, or malformed response can run as root or leave the package half-configured.

Fix:

Do not run network installers in maintainer scripts. Use an apt dependency, a vendored versioned binary with checksum/signature validation, or fail with a clear manual-install message.

### H4. Generated systemd units accept unsafe metadata and dependency strings

Source reports: Codex Finding 7; Claude M14 and M15.

Evidence:

- `src/usr/bin/apprun.py:998-999` converts `After` and `Before` spec strings without validating unit names.
- `src/usr/bin/apprun.py:1260-1283` inserts bundle metadata into generated system services.
- `src/usr/bin/apprun.py:1378-1398` inserts bundle metadata into generated global user services.

Impact:

Newlines or invalid characters in descriptions, service specs, or dependency lists can create malformed unit files or inject additional directives.

Fix:

Serialize unit files through a constrained helper. Validate unit names, reject control characters, and escape or reject newlines in all unit values.

### H5. Root writes in GUI startup installation have the same symlink/TOCTOU class

Source reports: Claude H10; Codex Finding 4.

Evidence:

- `src/usr/bin/apprun.py:1580-1659` writes stored bundles and `.desktop` files into user or global autostart locations.
- `src/usr/bin/apprun.py:1635-1646` creates directories and writes files before ownership correction.

Impact:

When re-executed as root for another user or global scope, user-controlled home paths and intermediate directories can be symlinked or raced.

Fix:

Verify each path component with `lstat`, refuse symlinks, write via file descriptors, and set ownership before exposing files through final paths.

### H6. `AppContext` box file APIs allow path traversal

Source reports: Claude M7; Codex Finding 9.

Evidence:

- `src/usr/lib/AppRun/libs/AppContext.py:258-259` directly joins caller input under the box.
- `src/usr/lib/AppRun/libs/AppContext.py:360-380` writes caller-provided filenames.
- `src/usr/lib/AppRun/libs/AppContext.py:382-413` reads caller-provided filenames.

Impact:

The API appears box-scoped, but `../` or absolute paths can escape the box and read/write any path allowed by the process privileges.

Fix:

Resolve the final path and require it to stay inside the resolved box root. Reject absolute paths, `..`, NUL/control characters, and symlink escapes where relevant.

### H7. Package installation from bundle metadata is too permissive

Source reports: Claude H9; Codex Finding 1.

Evidence:

- `src/usr/lib/python3/dist-packages/libapprun.py:315-333` reads `apt-requirements` from bundle metadata.
- `src/usr/bin/apprun.py:495-527` strips requirements to package names and invokes `apt`/`apt-get`.

Impact:

A bundle can prompt users to install arbitrary apt packages or request versions/downgrades without enough visibility. GUI paths also interact with the command injection issue in C2.

Fix:

Show full requirements verbatim before installing, validate package names and version constraints, and consider a policy/allowlist for automatic dependency installation.

### H8. Thumbnailer processes untrusted icon data without limits

Source reports: Claude M12; Codex Finding 13.

Evidence:

- `src/usr/lib/python3/dist-packages/libapprun.py:109-117` captures full extracted bytes in memory.
- `src/usr/bin/apprunx-thumbnailer.py:70-99` runs ImageMagick `convert` on the extracted icon.

Impact:

A crafted bundle can force memory pressure, slow image processing, or exposure to ImageMagick parser/delegate vulnerabilities.

Fix:

Limit extracted icon size, validate PNG magic and dimensions, bound thumbnail size, set subprocess timeouts, and prefer a safer image library or explicitly forced PNG decoding.

### H9. DropIn service uninstall path has a case mismatch

Source reports: Claude H8; Codex Finding 10.

Evidence:

- `src/DEBIAN/postinst:57` installs `/usr/lib/AppRun/AppRunDropInService.apprunx`.
- `src/DEBIAN/prerm:3` removes `/usr/lib/AppRun/AppRunDropinService.apprunx`.

Impact:

On case-sensitive filesystems, package removal can leave a stale systemd service and stored bundle state behind.

Fix:

Use one shared path constant or correct the casing. Add install/purge packaging tests.

### H10. Direct service installation copies bundled service files verbatim

Source reports: Claude M14; Codex Finding 2.

Evidence:

- `src/usr/bin/apprun.py:870-962` copies bundled `.service` files into the system service store and links them into systemd.

Impact:

This may be intended behavior, but users are not shown a reliable summary of `ExecStart`, `User`, `Group`, or privilege level. A bundle can install a root-running service if the user accepts a vague prompt.

Fix:

Show a pre-install summary of sensitive directives and require explicit confirmation for root-running or broadly privileged services.

## Medium Findings

### M1. Mount lifecycle is fragile

Source reports: Claude H3, H4, H5, M3, and L9; Codex Finding 14; Gemini 3.2.

Evidence:

- `src/usr/lib/python3/dist-packages/libapprun.py:149-152` checks mounts with substring matching against `/proc/mounts`.
- `src/usr/lib/python3/dist-packages/libapprun.py:154-158` uses `random.choices` for mount suffixes.
- `src/usr/bin/apprun.py:609-693` depends on a `finally` block for unmount cleanup.
- `src/usr/lib/python3/dist-packages/libapprun.py:143-146` unmounts and immediately removes the directory.

Impact:

False mounted detections, collisions, stale FUSE mounts after hard kill, and `Device or resource busy` races can cause launch failures or resource leaks.

Fix:

Parse `/proc/mounts` exactly, use `secrets` or `tempfile.mkdtemp`, create mount roots with `0700`, separate unmount from directory cleanup, and scrub orphaned mounts on startup.

### M2. Build scripts mutate workspace ownership and permissions

Source reports: Claude L4; Codex Finding 15; Gemini 3.1.

Evidence:

- `build.sh:16-21` recursively changes `src` ownership and mode.
- `build-nogui.sh:7-15` edits `src/DEBIAN/control` in place and restores it only on normal completion.

Impact:

Interrupted builds can leave the workspace root-owned or the control file modified. `chmod -R 755` also makes data files executable and loses intended file modes.

Fix:

Use `dpkg-deb --root-owner-group` or `fakeroot`, stage builds in a temporary directory, and restore temporary edits through a trap.

### M3. Locking in `AppContext` is predictable and can leak stale state

Source reports: Claude M8 and M9; Gemini 2.3.

Evidence:

- `src/usr/lib/AppRun/libs/AppContext.py:196-208` uses predictable lock file names in `/tmp` for global locks.
- `src/usr/lib/AppRun/libs/AppContext.py:639-668` can recurse on stale locks.
- `src/usr/lib/AppRun/libs/AppContext.py:680-682` handles only `SIGINT` and `SIGTERM`.

Impact:

Other local users can pre-create lock paths to deny service. Stale or malformed lock files can cause confusing behavior, and some signals can leave locks behind.

Fix:

Use secure per-app lock directories or abstract Unix sockets, bound stale-lock retries, include boot identity/PID checks, and chain/restore signal handlers.

### M4. DropIn daemon is brittle against malformed metadata and noisy watches

Source reports: Codex Finding 11; Claude M10 and L10.

Evidence:

- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:123-124` loads config JSON without schema validation.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:307-324` assumes metadata value types.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:543-561` event handlers call registration without local exception handling.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:574-591` watches `/etc` broadly for passwd changes.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:183-187` writes the cache non-atomically.

Impact:

Malformed bundles or config can crash the daemon or trigger systemd restart loops. Busy hosts can generate unnecessary event churn, and cache corruption causes full re-registration.

Fix:

Validate schema and types, catch per-file registration failures, watch passwd changes more narrowly or debounce them, and save cache atomically.

### M5. `.desktop` files are written executable

Source reports: Claude M11.

Evidence:

- `src/usr/bin/apprun.py:864` chmods desktop files to `0755`.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:400` writes DropIn desktop entries with `0755`.

Impact:

Executable `.desktop` files can bypass or confuse desktop-environment trust UX.

Fix:

Use `0644` unless there is a desktop-specific trust mechanism that is intentionally managed.

### M6. `dictionary.py` allows collection path traversal

Source reports: Gemini 2.4.

Evidence:

- `src/usr/bin/dictionary.py:12-20` joins `/usr/share/dictionaries` with user-provided `--dict-collection`.

Impact:

`../` input can make the utility read JSON files outside the intended dictionary directory. This is lower risk, but it weakens path expectations.

Fix:

Resolve the final path and require it to remain under `/usr/share/dictionaries`, or restrict collection IDs to an allowlisted character set.

### M7. Packaging tool can overwrite output paths without confirmation

Source reports: Claude M13.

Evidence:

- `src/usr/bin/apprun-package.py:120-123` unlinks any existing output path.

Impact:

A typo in `-o` can delete an important file.

Fix:

Require `--force` to overwrite, or refuse to overwrite non-AppRun artifacts.

### M8. AppContext has correctness issues in cache and metadata paths

Source reports: Codex Finding 16.

Evidence:

- `src/usr/lib/AppRun/libs/AppContext.py:407-410` can cache decoded strings while `read()` advertises bytes.
- `src/usr/lib/AppRun/libs/AppContext.py:488` and `601-602` use `AppRunMeta/DesktopLink`, while the rest of the project uses `AppRunMeta/DesktopLinks`.

Impact:

Callers can receive inconsistent types, and icon/terminal detection can silently fail.

Fix:

Keep byte and text caches separate. Support `DesktopLinks` and optionally retain `DesktopLink` only as a backward-compatible fallback.

### M9. Privileged script batching hides partial failures

Source reports: Claude M15 and M16; Codex Finding 2.

Evidence:

- `src/usr/bin/apprun.py:1806-1817` runs `bash -c` and reports only the final command status.
- `src/usr/bin/apprun.py:1187-1190` replaces symlinks through unlink-then-create rather than an atomic replacement.

Impact:

Mid-script failures can be masked by later successful commands, leaving partially installed units or links. Concurrent installs can interleave.

Fix:

Avoid shell batching, or at least use `bash -ec`. Use atomic symlink replacement through a temporary link and `os.replace`.

### M10. Crash detection can warn on legitimate fast exits

Source reports: Gemini 3.3.

Evidence:

- `src/usr/bin/apprun.py:816-830` shows an abnormal-exit warning when an `Application` exits successfully in under one second.

Impact:

Short-lived legitimate tools can appear broken to users.

Fix:

Warn only on nonzero exits by default, or add metadata to opt into fast-exit warnings.

### M11. Maintainer script post-install cleanup is unreliable

Source reports: Codex Finding 12; Claude H7.

Evidence:

- `src/DEBIAN/postinst:66-71` switches to `set +e`, calls `sudo` from a root maintainer script, runs `xdg-mime`, and deletes `~/.cache/thumbnails/`.

Impact:

Failures are hidden, `sudo` may not exist, and `~` may not refer to the desktop user's home.

Fix:

Remove `sudo`, handle optional cache/database updates explicitly, and avoid deleting user caches from package installation.

### M12. Miscellaneous robustness issues

Source reports: Claude M1, M2, M5, L5, L11, and L12; Codex Findings 14 and 15.

Evidence and impact:

- `src/usr/lib/python3/dist-packages/libapprun.py:98-106` decodes extracted files as text; binary or invalid UTF-8 can behave poorly.
- `src/usr/lib/python3/dist-packages/libapprun.py:120-129` parses `unsquashfs -l` text output and is fragile for unusual filenames.
- `src/usr/bin/apprun.py:2038` checks only `Path.exists()` before treating the input as a bundle; FIFOs, directories, or special files reach mount attempts.
- Several `subprocess.run` calls ignore return codes, including some systemd paths.
- `apprun-package.py` size calculation can be skewed by symlinks.

Fix:

Read binary data as bytes, parse archive listings with a more structured method, require regular files for bundle inputs, inspect subprocess return codes, and use symlink-aware size calculations.

## Consolidated Remediation Plan

1. Implement central validators: `app_id`, Debian package name, systemd unit name, desktop value, safe relative path, and service spec.
2. Replace shell-string privileged calls with argv calls. Where a shell remains, quote all values and use `set -e`.
3. Harden DropIn and GUI startup file writes using descriptor-based no-symlink writes or privilege dropping.
4. Replace all `.desktop` generation with one safe serializer and fixed key allowlist.
5. Fix `--is-format3` and add regression coverage proving it never launches or prepares bundles.
6. Remove `curl | sh` from `postinst`; use a deterministic dependency or verified vendored artifact.
7. Correct `prerm` casing and add package install/remove tests.
8. Harden mount lifecycle: exact mount detection, secure random mount directories, orphan cleanup, robust unmount cleanup.
9. Restrict and clearly display package/service installation behavior before prompting users.
10. Add tests for malicious app IDs, service filenames, symlinked target files, paths with spaces/percent signs, malformed metadata, malformed dictionaries, and fast-exit applications.

## Source Report Coverage

- Claude emphasized root DropIn path traversal/symlink issues, desktop-entry abuse, mount lifecycle risks, `prerm` typo, AppContext traversal, and service/unit handling.
- Codex emphasized shell injection surfaces, central validation gaps, `--is-format3` fall-through, maintainer-script supply chain risk, thumbnailer limits, and desktop/systemd serializers.
- Gemini emphasized DropIn symlink overwrite, service-install command injection, global lock DoS, dictionary traversal, build-script ownership mutation, unmount races, and false positive crash warnings.
