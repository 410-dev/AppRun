# AppRun Codebase Inspection Report (May 14, 2026)

## 1. Executive Summary
A thorough codebase inspection of the AppRun application was conducted, focusing on stability and security vulnerabilities. Several critical vulnerabilities were discovered, including a privilege escalation vector in the system daemon, command injection risks during service installation, and insecure temporary file handling. Additionally, minor instability factors related to build scripts and process management were identified.

---

## 2. Security Vulnerabilities

### 2.1. CRITICAL: Privilege Escalation & Arbitrary File Overwrite in DropIn Service
**Location:** `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py` (`_write_as_user`, `_chown_parents`, `_chown_recursive`)
**Description:** 
The `apprun3-dropin` service runs as a system daemon (root) and processes `.apprunx` bundles to create `.desktop` files in users' home directories (`~/.local/share/applications/`). 
When writing the `.desktop` file or the icon, the service uses standard file writing (`path.write_bytes()` / `path.write_text()`), followed by `path.chmod()` and `os.chown()`. 
Because these functions follow symbolic links by default, a malicious local user can preemptively create a symbolic link (e.g., `~/.local/share/applications/apprun-dropin-malicious.desktop -> /etc/sudoers`). When the drop-in service processes the bundle, it will overwrite the target file (`/etc/sudoers`) with the `.desktop` file content and change its ownership to the unprivileged user, leading to a full system compromise.
**Remediation:** 
- Open files with `os.open` using `os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW` to prevent following symlinks.
- Use `os.lchown` instead of `os.chown`, or explicitly pass `follow_symlinks=False` to `os.chown`.
- Ensure directory creation and ownership changes (`_chown_parents`) also safely handle symlink traversals.

### 2.2. HIGH: Command Injection in System Service Installation
**Location:** `src/usr/bin/apprun.py` (`handle_install_services`)
**Description:**
When installing services from a bundle's `services/` directory, the script retrieves the filename using `Path(svc_path).name` and appends it to an `installed` list. 
Later, if running as a non-root user, it elevates privileges and executes a shell command constructed via string formatting: 
`script_parts.append(f"systemctl {action} {' '.join(installed)}")`
Because `installed` contains untrusted filenames extracted from the user-provided bundle, an attacker can create a bundle with a maliciously named service file (e.g., `services/foo.service;id>.service`). This filename will be inserted directly into the shell command executed as `root` without `shlex.quote()`, leading to arbitrary command execution.
**Remediation:**
- Ensure all elements in the `installed` list are escaped using `shlex.quote()` before joining them into the shell string, or rigorously sanitize the filenames (as is done in `_sanitize_service_name`).

### 2.3. MEDIUM: Insecure Global Lock File Creation
**Location:** `src/usr/lib/AppRun/libs/AppContext.py` (`_ensure_single_process`, `_get_lock_path`)
**Description:**
When `ensure_single_process_globally` is called, the application creates a lock file in `/tmp` using `Path(tempfile.gettempdir()) / f"{safe_id}.lock"`. 
Since `/tmp` is world-writable, any local user can preemptively create a file or directory with the same name. This can be exploited to launch a Denial of Service (DoS) attack against the application (preventing it from starting for other users).
**Remediation:**
- Do not use predictable paths in `/tmp` for global application locks unless the application handles secure directory creation (`tempfile.mkdtemp` with proper permissions) or uses POSIX abstract namespace sockets (on Linux) which are not file-system dependent.

### 2.4. LOW: Directory Traversal in Dictionary Utility
**Location:** `src/usr/bin/dictionary.py`
**Description:**
The script constructs the dictionary collection path using `os.path.join("/usr/share/dictionaries", args.dict_collection)`. Because `args.dict_collection` is not sanitized, an attacker could supply a path like `../../../tmp/malicious` to load arbitrary JSON files. Although this does not directly result in RCE, it allows the tool to read out-of-scope files.
**Remediation:**
- Ensure `args.dict_collection` contains only alphanumeric characters or safely resolve the absolute path and verify it starts with `/usr/share/dictionaries/`.

---

## 3. Instability Issues

### 3.1. Build Script Disrupting Local Workspace Ownership
**Location:** `build.sh`
**Description:**
The script performs `sudo chown -R root:root src` and then attempts to restore the ownership using `sudo chown -R $USER:$USER src` at the end. If the packaging process fails or is forcibly interrupted by the user (e.g., `Ctrl+C`), the workspace remains owned by `root`.
**Remediation:**
- Use `dpkg-deb --root-owner-group` or tools like `fakeroot` to build Debian packages without actually changing the ownership of the files on the host filesystem.

### 3.2. Unmount Race Condition / Device Busy
**Location:** `src/usr/lib/python3/dist-packages/libapprun.py` (`unmount`)
**Description:**
The `unmount` function executes `subprocess.run([FUSERMOUNT, "-u", mountpoint], check=True)` and immediately follows it with `Path(mountpoint).rmdir()`. Since `fusermount -u` might return before the kernel has completely cleaned up the mount point, `rmdir()` may raise a "Device or resource busy" (`OSError`), causing the script to crash unexpectedly.
**Remediation:**
- Implement a small polling loop with `time.sleep()` to wait until the mount point is completely unmounted before attempting to remove the directory.

### 3.3. False Positive Crash Detection
**Location:** `src/usr/bin/apprun.py` (`_detect_crash`)
**Description:**
The crash detection logic checks if the application exits in less than 1.0 second (`duration < 1.0`). For legitimate fast-executing GUI tools or dialogs bundled as Applications, this triggers an unwarranted "Abnormal Exit" warning popup, confusing users.
**Remediation:**
- Differentiate between normal exits (`exit_code == 0`) and actual crashes, or allow bundles to define a `fast_exit_expected` flag in `meta.json`. Wait, the current code does `elif duration < 1.0:` which triggers even if `exit_code == 0`. It should at least be configurable.

---
**End of Report**