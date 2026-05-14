# AppRun Code Inspection Report

- **Date**: 2026-05-14
- **Reviewer**: Claude (Opus 4.7)
- **Branch**: devel
- **Scope**: All source under `src/` — `apprun.py`, `apprun-package.py`, `apprunx-thumbnailer.py`, `dictionary.py`, `libapprun.py`, `apprun_i18n.py`, `AppRunDropInService.apprunxproj/main.py`, `AppContext.py`, and DEBIAN scripts.

Severity legend: **Critical** = remote/local code execution or root compromise; **High** = privilege escalation, data corruption, or arbitrary file write; **Medium** = correctness/stability bug with realistic impact; **Low** = minor issue, robustness, defense-in-depth.

---

## Critical

### C1. Path traversal in DropIn service → arbitrary file write as root, chowned to attacker-controlled user
**File**: `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:398`, helper `_write_as_user` at line 201.

`register_desktop()` builds the destination path as:
```python
desktop_file = user.desktop_dir / f"apprun-dropin-{app_id}.desktop"
```
`app_id` is taken verbatim from the bundle's `AppRunMeta/id` (`libapprun.get_bundle_id`) without any sanitization. A bundle can therefore set `id` to `../../../../etc/cron.d/evil` (or any path), and the DropIn service (which runs as **root**, see `postinst` line 57) will:
1. `path.parent.mkdir(parents=True, exist_ok=True)` — creates intermediate directories.
2. `path.write_text(content)` / `path.write_bytes(content)` — writes attacker-controlled `[Desktop Entry]` content.
3. `path.chmod(0o755)` (line 400 invokes `_write_as_user(..., mode=0o755)`).
4. `os.chown(str(path), user.uid, -1)` — gives ownership to a normal user.

Combined with the trigger being *any* `.apprunx` file appearing in a watched directory (e.g. `/applications`, `/opt/applications`, or per-user `~/applications`), a crafted bundle dropped by an unprivileged user lets that user obtain a root-created file at an attacker-chosen path, owned by themselves with mode 0755. This is a clear local privilege-escalation primitive (e.g. write into `/etc/profile.d/*.sh` is not directly possible because the suffix is fixed to `.desktop`, but `~/.bashrc`, `~/.config/autostart/*.desktop`, polkit policy locations, etc., are all reachable; even with `.desktop` suffix, dropping it into another user's `~/.config/autostart/` immediately runs attacker-controlled `Exec=` on next login).

The same flaw exists in `unregister_desktop()` (line 460) where stale entries unlink arbitrary paths constructed from the cached `app_id`.

**Fix**: sanitize `app_id` with a strict allow-list (e.g. `^[a-zA-Z0-9._-]+$`, no `..`, no leading `.`) before using it in any filesystem path or `.desktop` field, both on registration and on unregistration. Reject bundles whose `id` does not match.

---

### C2. Same path-traversal class in `apprun3 --install-as-service` via `app_id`
**File**: `src/usr/bin/apprun.py:1255-1257, 1373-1376`.

`_sanitize_service_name` (line 968) only replaces unsafe characters with `-`, which neutralizes most cases — *but* the destination is constructed via `Path(...) / f"{svc_name}.service"`. Because `_sanitize_service_name` replaces `/`, the traversal is blocked here. However, the upstream value flowing into the desktop content in `_register_desktop` (line 854-863) and `_build_gui_startup_desktop` (line 1172) is the raw `app_id`, which is *not* sanitized when interpolated into `Exec=apprun3 <apprunx_path>` and the `Name=` / `Icon=` fields. A malicious `app_id` containing newlines can inject extra `.desktop` keys such as `Exec=/bin/sh -c 'curl … | sh'` because `_desktop_value` only strips `\n` for some helpers but the registration path in `_register_desktop` does not use `_desktop_value` at all.

**Fix**: route all attacker-controllable metadata (`name`, `description`, `app_id`, `apprunx_path`) through `_desktop_value` (and a stricter allow-list for `id` and `StartupWMClass`).

---

### C3. `Exec=` injection via unquoted `apprunx_path` in DropIn-generated `.desktop`
**File**: `AppRunDropInService.apprunxproj/main.py:267, 271, 330`.

```python
processed.append(f"Exec=apprun3 {apprunx_path}")
...
f"Exec=apprun3 {apprunx_path} {' '.join(args_launch)}",
```
`apprunx_path` is the resolved path of the dropped bundle. A user able to place a file in a watched directory can choose its filename. Filenames may contain spaces, `%`, `"`, and `;`. Desktop spec field codes are interpreted by the launcher (e.g. `%f`, `%U`). A file named `evil %f; rm -rf ~/.local/share` or one containing `; xdotool key …` is interpreted by the desktop launcher as additional fields/arguments. Coupled with `apprun-dropin-<id>.desktop` files registered into every user's `~/.local/share/applications/`, the entry is automatically reachable from the GNOME Activities/App Grid.

`apprun.py:_register_desktop` (line 856) has the identical issue:
```python
f"Exec=apprun3 {apprunx_path}\n"
```

**Fix**: quote with `_desktop_exec_quote_arg` (already defined in `apprun.py:1131`) and strictly reject filenames containing field-code metacharacters (`%`) — the desktop spec treats `%%` as literal `%` and the rest as field codes which can include `%c`, `%k`, `%f`, etc.

---

## High

### H1. TOCTOU/symlink attack against `_write_as_user` and `_chown_parents`
**File**: `AppRunDropInService.apprunxproj/main.py:201-233`.

The DropIn service runs as root and writes into each normal user's home tree. `_write_as_user` does:
```python
path.parent.mkdir(parents=True, exist_ok=True)
_chown_parents(path, user)
...
path.write_bytes(content)
path.chmod(mode)
os.chown(str(path), user.uid, -1)
```
None of the steps use `O_NOFOLLOW` / `dir_fd` and the user owns the entire chain (or can race with it). A hostile user can replace `~/.local/share` (or any intermediate component) with a symlink between `mkdir` and `write_bytes`. The result: a file is written through the symlink to an arbitrary location, then chowned to the user (already trivial), or — more interestingly — the *parent directory* of the symlink target is `chmod`'d / `chown`'d. Because `_chown_parents` only walks while the prefix-string starts with `home_str`, the user can satisfy that by making `~/.local/share/applications` a symlink to a path that *also* lives under their home; but a more direct attack is replacing `~/.local/share/icons/apprun-default.png` location with a symlink to a root-owned config file — `_write_as_user(default_dest, DEFAULT_ICON.read_bytes(), user)` then overwrites that file with arbitrary bytes as root and chowns to the user.

**Fix**: open files with `O_NOFOLLOW | O_CREAT | O_EXCL`, perform the write/chown via the fd (`os.fchown`, `os.fchmod`), and stat each component to make sure it is a real directory owned by the target user before descending. Or do the entire write through `os.fork` + `setuid(user.uid)` + `setgid(user.gid)` so the kernel enforces the user's permissions.

---

### H2. DropIn service trusts attacker-supplied bundle contents in `desktopfile.desktop`
**File**: `AppRunDropInService.apprunxproj/main.py:248-296`.

The original `desktopfile.desktop` bytes from inside a bundle are decoded with `errors="replace"`, then *every* line not starting with `Exec=`/`Icon=` is appended verbatim. A crafted bundle can therefore inject arbitrary keys: `X-GNOME-Autostart-enabled=true`, `Hidden=false`, `OnlyShowIn=...`, additional `Exec=` lines, or even `Type=Application\nExec=...` blocks. Worse, the resulting file is written to every detected normal user. Even without any path traversal (C1) or quoting bug (C3), this alone lets an attacker pre-stage menu/desktop entries on victim accounts.

**Fix**: do not pass through arbitrary keys. Build the `.desktop` from a fixed template using only the validated `Name`, `Comment`, `Icon`, `Exec`, `Terminal`, `StartupWMClass`, and `Categories` keys. Strip newlines from every value.

---

### H3. `is_mounted` substring match → false positives skip a real mount
**File**: `src/usr/lib/python3/dist-packages/libapprun.py:149-152`.

```python
def is_mounted(mountpoint: str) -> bool:
    mp = str(Path(mountpoint).resolve())
    with open("/proc/mounts") as f:
        return any(mp in line for line in f)
```
Substring match: a mountpoint `/home/alice/.local/apprun/mounts/foo` will be reported as mounted whenever *anything else* references that string in `/proc/mounts` (which it normally would not), but more dangerously a shorter mountpoint like `/home/alice/.local/apprun/mounts/foo` is a prefix of `/home/alice/.local/apprun/mounts/foo.bar`. In `handle_run`, when `is_mounted` returns `True` spuriously, the code calls `libapprun.unmount(str(mount_path))` on a path that is *not* in fact mounted. `fusermount -u` will fail with `check=True`, raising and bailing out before the legitimate mount. This is a denial-of-service if mount paths collide via the `_random_str` suffix.

**Fix**: tokenize `/proc/mounts` by whitespace and compare field 2 exactly.

---

### H4. Race in `_random_str` for mountpoints
**File**: `libapprun.py:154-158`.

`random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8)` uses the non-cryptographic PRNG, seeded from time. Two `handle_run` invocations in the same process or near-simultaneous runs can collide, especially under tests or autostart. Combined with H3 (`is_mounted` substring match) this is observable. Also: the mountpoint is created with default `mkdir` permissions (`0o755`) under `~/.local/apprun/mounts/`, which is fine, but `MOUNT_ROOT` itself is auto-created with default umask — if the user has lax umask this is `0777`, allowing other local users on multi-user systems to peer at mountpoints.

**Fix**: use `secrets.token_hex(8)` and create `MOUNT_ROOT` with explicit `0o700`.

---

### H5. `handle_run` leaks mount on hard kill
**File**: `apprun.py:609-693`.

The `finally` block calls `libapprun.unmount(str(mount_path))`, but if the apprun3 process itself is killed with `SIGKILL` (or crashes uncatchably), the squashfuse mount is left dangling at `~/.local/apprun/mounts/<id>.<random>/`. There is no scrubber on startup that unmounts orphaned mounts. Over time this grows without bound and exhausts FUSE/inotify limits.

**Fix**: at `handle_run` startup, walk `MOUNT_ROOT`, identify entries whose owning PID (recorded under `box/.run/<digest>`) is no longer alive, and `fusermount -u` them.

---

### H6. `Exec=` in `_register_desktop` uses absolute apprunx path from a `box/source.path` file
**File**: `apprun.py:833-864`.

`source.path` is written (line 272) inside the box, in user-writable space. If a different process or symlink replaces `source.path` between `_register_desktop` reading it and the `.desktop` being written, the desktop entry can be made to execute arbitrary content. The mitigation in libapprun.mount uses squashfuse to mount read-only, but `source.path` lives outside the mount in the box dir.

**Fix**: pass the apprunx path explicitly from the caller rather than re-reading a mutable file in the box.

---

### H7. `postinst` runs uv installer over the network as root with `set -e`
**File**: `src/DEBIAN/postinst:5-29`.

`curl -LsSf https://astral.sh/uv/install.sh | sh` is executed during package install (root). If `astral.sh` is compromised, MITM'd, or returns malformed content, arbitrary code runs as root. The script also doesn't verify a checksum or signature. `set -e` is on, so a hostile but partial response simply fails the install — but a successful poisoned install is undetectable.

Additionally, `$HOME/.local/bin/uv` is computed using whatever `$HOME` dpkg passes (usually `/root`). The script then moves the binary to `/usr/local/bin/uv` and (line 13) `mv` fails if `$HOME` was empty — the `set -e` will then abort the install partway through, leaving the package half-configured. The conditional on line 12 actually papers this over, but the `chmod +x` on line 8 happens *before* the existence check.

**Fix**: pin a uv version, download it via `apt` or as a vendored binary inside the .deb, verify a checksum, and avoid network installs in postinst. At minimum guard `chmod`/`mv` with `[ -x ]`.

---

### H8. `prerm` typo: `AppRunDropinService.apprunx` vs `AppRunDropInService.apprunx`
**File**: `src/DEBIAN/prerm:3` vs `src/DEBIAN/postinst:57`.

The case difference (`Dropin` vs `DropIn`) means `prerm` will call `apprun3 --uninstall-as-service` against a file that does not exist, returning a non-zero exit. Without `set -e` the rest of `prerm` still runs, so unit files in `/etc/systemd/system/` and the stored copy in `/usr/share/services.apprd/system/` are *not* cleaned up, leaving orphan systemd units after package removal. Subsequent reinstall reactivates a unit pointing to a vanished bundle and systemd boot may print failures.

**Fix**: correct the casing; also handle the case where the .apprunx no longer exists by removing the stored unit file directly.

---

### H9. `_install_packages_cli` invokes `sudo apt-get install` with package names from a bundle's metadata
**File**: `apprun.py:511-527` and `libapprun.py:251-260`.

`apt-requirements` is read from `meta.json` inside the bundle. While `subprocess.run` with a list prevents shell injection, the user is shown a confirmation prompt that only lists package *names* (operator stripped). A malicious bundle can claim to need `python3-venv` (innocuous) and *also* list `evil-package` that the local apt mirror serves. More directly: nothing prevents a bundle from listing `cowsay` and a `=arbitrary-version` constraint to downgrade trusted packages. The user grants `sudo` once and apt installs whatever appears in the list.

**Fix**: surface the full requirements verbatim in the prompt; consider refusing requirements that contain unusual characters or that are not on a curated allow-list.

---

### H10. GUI startup `.desktop` written to other users' homes without proper checks
**File**: `apprun.py:1580-1659`.

`handle_install_as_gui_startup` running as root after `_reexec_privileged` does `shutil.copy2(apprunx_abs, stored_bundle)` and `stored_desktop.write_bytes(desktop_bytes)` into a directory that resolves through `Path(f"~{resolved_user}").expanduser()`. If the named user's `$HOME` (or any intermediate dir) is a symlink they control, the same TOCTOU class as H1 applies — except this is invoked as root from the CLI and so is exploitable even on single-user systems where the user is root-equivalent under `--user=<other>`. The `_chown_to_user` walk happens *after* the writes.

**Fix**: stat each component (no symlinks, owned by target user, perms ≤ 0755) before writing.

---

## Medium

### M1. `peek_file` decodes binary as text
**File**: `libapprun.py:98-106`.

`peek_file` uses `text=True` (UTF-8 with replace defaults from `subprocess`). If `AppRunMeta/id` (or `meta.json`) contains bytes outside UTF-8, `subprocess.run` may raise `UnicodeDecodeError`, leaving the operation undefined.

**Fix**: read as bytes, then decode with explicit `errors="replace"` only where safe.

---

### M2. `list_files` is fragile against odd filenames
**File**: `libapprun.py:120-129`.

Filenames containing newlines or beginning with whitespace will be lost or mis-parsed. `unsquashfs -l` is unsuitable for programmatic use; `unsquashfs -lc` is similar. Use `-stat`/`-ll` and parse columns, or use the C API.

---

### M3. `unmount` raises on `rmdir` failure but mount is gone
**File**: `libapprun.py:143-146`.

If FUSE unmounted successfully but the directory is not empty (e.g. NFS staleness, stray hidden file from a stacked overlay), `Path.rmdir()` throws; the caller treats this as "unmount failed" which is misleading and stops cleanup. The mountpoint dir will be left behind.

**Fix**: separate the unmount success from the cleanup; ignore `rmdir` failure with `os.rmdir` wrapped in try/except.

---

### M4. Re-exec under `pkexec` strips environment unexpectedly
**File**: `apprun.py:111-119`.

`pkexec` resets most env vars by policy. `LOCAL_DIST_PACKAGES` path injection in `apprun.py:18-21` will still work because it is path-based and resolved at import time, but `APPRUN_LANG`, `LANGUAGE`, locale, `PYTHONPATH` set by the user, and `DBUS_SESSION_BUS_ADDRESS` won't propagate. The re-execed process under root may operate in an unintended locale, affecting `tr()` and error parsing.

**Fix**: when escalating, pass `--keep-cache` or list specific env vars via `pkexec env VAR=val cmd …`.

---

### M5. `handle_run` does not check that the bundle is a regular file before mounting
**File**: `apprun.py:632`.

`libapprun.mount` is called on the user-supplied path. If the path is a FIFO, special file, or a directory, squashfuse will fail with various errors that propagate as `RuntimeError`. There is no early validation in `main()` beyond `Path(apprunx).exists()` (line 2038), which is true for any node type.

**Fix**: assert `Path(apprunx).is_file()` (and optionally `magic` check for squashfs header).

---

### M6. `_setup_pythonpath` blindly trusts `libs` file content
**File**: `apprun.py:740-758`.

The libs file is run through `dictionary.py` and the output is *prepended* to `PYTHONPATH`. An attacker who can write into the bundle's mounted view (impossible — read-only) or into `/usr/share/dictionaries/apprun-python/` (root-only) cannot influence this. Still, the substitutions are not validated; a libs file that contains absolute paths to malicious wheels installed elsewhere on the system would let a bundle hijack imports for its own code (which is the intent), but the doc says PYTHONPATH is prepended, so it overrides system packages. This is by design but worth flagging.

---

### M7. `AppContext.read`/`write` allow path traversal out of the box
**File**: `src/usr/lib/AppRun/libs/AppContext.py:360-413`.

```python
file_path = os.path.join(self._apprun_box_path, filename)
```
`os.path.join` with an absolute or `..`-laden `filename` does not stay inside the box. Bundle code calling `ctx.write("/etc/passwd", b"...")` will happily try the write. The "protected filenames" check is a fixed list and string-prefix match — it will not block traversal.

**Fix**: `Path(box).joinpath(filename).resolve()` and assert the resolved path is under `Path(box).resolve()`.

---

### M8. AppContext signal handler only restored for SIGINT/SIGTERM, lock leak otherwise
**File**: `AppContext.py:680-682`.

`SIGHUP`, `SIGQUIT`, `SIGABRT`, etc., are not handled, and the original handler is never chained. If the application installs its own SIGINT handler after `_ensure_single_process`, AppContext's handler is replaced and the lock file is not cleaned up on `_handle_signal`-style termination, though `atexit` covers normal exit.

**Fix**: chain previous handlers; cover at least `SIGHUP`.

---

### M9. `_ensure_single_process` reads PID from a lock file the writer may not have flushed
**File**: `AppContext.py:639-668`.

If two processes race, the second reads PID via `raw.strip()`. The first writer truncates and then `flush()`s after acquiring lock. The reader (blocked, then `BlockingIOError`) may see an empty file or a partial PID written by the *previous* run that crashed before truncate completed. The `isdigit()` guard catches the empty case (`existing_pid = -1`) and the stale check then deletes the lock and recurses without limit — there is no recursion bound.

**Fix**: bound retries (e.g. 3) before raising; also include the boot time in the lock file to detect PID reuse across reboots.

---

### M10. `PasswdEventHandler` does coarse `/etc` watch
**File**: `AppRunDropInService.apprunxproj/main.py:574-591`.

Watching `/etc` for `IN_CLOSE_WRITE | IN_MOVED_TO` fires for *every* file edit there. The handler then sleeps 0.3 s and reloads users. On a busy host (Ansible-managed config, etc.) this is unnecessary churn. Worse, the sleep means events can pile up while the handler is blocked, slowing the notifier thread.

**Fix**: watch `/etc/passwd` specifically with `pyinotify.IN_MODIFY` + `IN_MOVE_SELF` and drop the sleep, or coalesce with a debouncer thread.

---

### M11. `_register_desktop` and DropIn service write `.desktop` files with mode 0755
**File**: `apprun.py:864`, `AppRunDropInService.apprunxproj/main.py:400`.

`.desktop` files do not need to be executable; some desktop environments warn ("Untrusted desktop file") until the user marks them trusted. Setting 0755 bypasses that. While the bundle owner intended for the file to be launchable, the security UX expectation is undermined.

**Fix**: use 0644 for `.desktop` files; rely on GIO's "trusted" flag where appropriate.

---

### M12. `apprunx-thumbnailer` runs ImageMagick `convert` on bundle-supplied PNG
**File**: `src/usr/bin/apprunx-thumbnailer.py:70-99`.

ImageMagick has a long history of format-confusion CVEs (Ghostscript delegate, MVG, etc.). Even though the input file is named `Icon.png`, ImageMagick auto-detects type by magic bytes by default. Modern distros ship a restrictive `/etc/ImageMagick-*/policy.xml`, but not all do. If a user double-clicks a malicious `.apprunx` in Nautilus, the thumbnailer runs in their session.

**Fix**: pass `-define` to force `PNG:` format, or use a safer image library (`Pillow`).

---

### M13. `package(...)` removes existing output without confirmation
**File**: `apprun-package.py:120-123`.

`out.unlink()` removes any file at the output path (passed via `-o`). If the user typos `-o /important/file`, it is gone. The CLI should refuse to overwrite unless the user passes `--force` (or at minimum verify the existing file has a squashfs magic before removing).

---

### M14. `handle_install_services` (system store) does not verify `.service` content
**File**: `apprun.py:870-962`.

`.service` files are copied verbatim from the bundle into `/etc/systemd/system/`. There is no check on `ExecStart=` or `User=`. A bundle author can ship a unit that runs as root (e.g. `User=root`) — by design — but the user only sees "installing service for app X". Reading the unit file before confirming is up to the operator.

**Fix**: show a summary of `ExecStart=`/`User=`/`Group=` and require explicit confirmation in interactive mode, or sandbox to a non-root user by default and require an opt-in flag for `User=root`.

---

### M15. `_run_privileged` joins multiple commands with `;` — partial-success ambiguity
**File**: `apprun.py:1806-1817`.

`"; ".join(script_parts)` runs all commands even if an earlier one fails. The function returns based on the *final* command's exit code (well, on `proc.returncode` from bash, which is the last command's). So a mid-script failure (e.g. `mkdir -p` worked but `mv` failed) can still report success if a later `systemctl daemon-reload` succeeded.

**Fix**: prepend `set -e` to the script: `_sudo_cmd() + ["bash", "-ec", script]`.

---

### M16. `_replace_symlink` is not atomic
**File**: `apprun.py:1187-1190`.

```python
if link_path.exists() or link_path.is_symlink():
    link_path.unlink()
link_path.symlink_to(target_path)
```
Between `unlink` and `symlink_to`, another process can occupy the path. A concurrent install of two bundles with the same `app_id` interleaves into broken state.

**Fix**: `os.symlink(target, link + ".new"); os.replace(link + ".new", link)` for atomicity.

---

## Low / Defense-in-Depth

### L1. `prerm` returns the exit status of `apprun3 --uninstall-as-service` implicitly
File ends without `exit 0`. If the last loop's last `rm` fails (improbable since `[ -L ]` check), prerm fails and aborts removal. Add explicit `exit 0`.

### L2. `dictionary.py` silently swallows JSON errors
`json.JSONDecodeError` is logged but iteration continues. Output may be partially substituted — caller cannot tell.

### L3. `apprun_i18n._candidate_langs` falls back to `locale.getlocale()` which may return `(None, None)` in non-interactive contexts.
Already chained with `or DEFAULT_LANG`, but the `.split` operations on `None` would raise. Verify: `raw = ... or DEFAULT_LANG`. Then `raw.split(".", 1)` is fine. OK on inspection, just brittle.

### L4. `build.sh` chains `sudo chmod -R 755 src` which strips the executable bit from non-script files but also from binary-shipped assets if any are added later. Harmless today but a footgun.

### L5. `apprun.py` has many places where a `subprocess.run` is invoked without `check=` and without inspecting `returncode` (e.g. line 1474 `systemctl --global disable`, line 1845 daemon-reload). Failures are silent.

### L6. `_get_user_systemd_env` falls back to constructing `unix:path=...` for `DBUS_SESSION_BUS_ADDRESS`, but does not verify the socket is actually a unix socket (it could be a regular file the user planted).

### L7. `handle_extract_file` writes to user-specified `dest` with no traversal check (line 251). Intentional — but consider rejecting `..` in `inner_path` to defend against future squashfuse bugs.

### L8. `_get_proc_title` truncates to 15 chars (line 712) which matches `PR_SET_NAME` limit — good, but the symlink is created with `_get_proc_title(...)[:15]` while `proc_title` itself is full-length, leading to drift between displayed and actual name.

### L9. `mount` does not pass `-o ro` to squashfuse explicitly. Squashfuse is read-only by nature but explicit is better.

### L10. The cache file `/var/lib/apprun-dropin/desktop_hashes.json` is written non-atomically (`open(..., "w")` then `json.dump`). Crash mid-write leaves a corrupt JSON file, which is handled (`json.JSONDecodeError → {}`) but loses the entire registration cache, forcing full re-registration churn.

### L11. `_dir_size` in `apprun-package.py` follows symlinks via `rglob` + `stat()` (no `follow_symlinks=False`). A bundle directory containing a symlink to `/` would hang or inflate sizes. mksquashfs handles the actual packaging, but pre-validation could be misleading.

### L12. `_pkg_names_only` regex (`libapprun.py:257`) does not allow `~` (used by debian native package versioning) or `:` (epochs in version part) — that's the comparison side, fine — but for the package name part, `+`/`-`/`.` are accepted. Real Debian package names also allow lowercase only. Strict allow-list would catch typos.

### L13. `AppContext._chown_recursive` (line 609) walks parent chain by string prefix. Symlinked home dirs would not be detected as belonging to the user.

### L14. The `notify-send` calls do not specify `--app-name` or `--icon`, so notifications cannot be styled or grouped.

### L15. `apprun-package.py` uses `Path(bundle).rglob("*")` for size calculation — for very large bundles this is slow. Acceptable, but consider sampling.

---

## Summary of Top Recommendations

1. **Sanitize `app_id` strictly** at every use site that touches the filesystem or `.desktop` content (C1, C2). This is the single highest-impact change.
2. **Lock down `.desktop` content** to a fixed-template generator (H2, C3, M11). Never pass through arbitrary keys from a bundle.
3. **Harden DropIn write path** against TOCTOU (H1, H10): write via `os.open(..., O_NOFOLLOW | O_CREAT | O_EXCL)`, or drop privileges to the target user using `fork + setuid` before writing.
4. **Fix `is_mounted`** to compare mount fields exactly (H3) and switch to `secrets` for mount-suffix randomness (H4).
5. **Replace network-fetched `uv` in `postinst`** with a vendored binary or apt dependency, verify checksum (H7).
6. **Correct the `prerm` typo** (`Dropin` → `DropIn`, H8).
7. **Add `set -e` to `_run_privileged` scripts** so partial failures are not masked (M15).
8. **Atomic symlink replace** (M16) and a startup scrubber for orphan FUSE mounts (H5).
9. **Bound retries in `_ensure_single_process`** (M9) and harden `AppContext.read/write` against traversal (M7).
10. **Display the full `.service` unit before installing** (M14) and the full `apt-requirements` list (H9) so the user can actually consent.

## Files Reviewed (line counts)
- `src/usr/bin/apprun.py` — 2086 lines
- `src/usr/bin/apprun-package.py` — 270 lines
- `src/usr/bin/apprunx-thumbnailer.py` — 103 lines
- `src/usr/bin/dictionary.py` — 32 lines
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py` — 799 lines
- `src/usr/lib/AppRun/libs/AppContext.py` — 1019 lines
- `src/usr/lib/python3/dist-packages/libapprun.py` — 334 lines
- `src/usr/lib/python3/dist-packages/apprun_i18n.py` — 75 lines
- `src/DEBIAN/postinst`, `src/DEBIAN/prerm`, `src/DEBIAN/control`
- `build.sh`, `build-nogui.sh`, `build.json`
