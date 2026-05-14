# AppRun 통합 점검 보고서 - 2026-05-14

통합 대상 보고서:

- `inspection-report-0514-claude.md`
- `inspection-report-0514-codex.md`
- `inspection-report-0514-gemini.md`

이 문서는 세 보고서의 중복 내용을 합치고, 실제 위험도 기준으로 재분류한 통합 보고서입니다. 원문을 그대로 이어 붙인 문서가 아니라 종합 정리본입니다.

출처 표기 방식: 각 이슈 아래에 같은 내용 또는 실질적으로 겹치는 내용을 포함한 원본 보고서 section을 표시했습니다.

## 요약

AppRun은 신뢰할 수 없는 `.apprunx` 번들을 처리하고, 메타데이터를 추출하며, 데스크톱 항목을 만들고, 의존성을 설치하고, FUSE 파일시스템을 마운트하며, systemd 서비스를 설치할 수 있습니다. 현재 코드는 번들에서 온 데이터와 권한이 높은 호스트 작업 사이의 검증 경계가 일관적이지 않습니다.

가장 시급한 위험은 root 권한 DropIn 데몬을 통한 로컬 권한 상승, 권한 상승/systemd 경로의 셸 명령 주입, 번들 ID를 파일 경로 조각으로 사용하는 문제, 안전하지 않은 `.desktop` 생성, Debian 설치 스크립트에서 원격 `curl | sh`를 실행하는 문제입니다.

최우선 수정 항목:

1. 번들 ID, 서비스 이름, 패키지 이름, systemd 유닛 이름, 데스크톱 값, 안전한 상대 경로를 중앙에서 검증합니다.
2. 번들, 파일명, 메타데이터, 사용자 제어 경로에서 온 값이 섞일 수 있는 곳에서는 셸 문자열 명령 구성을 제거합니다.
3. root가 사용자 제어 디렉터리에 파일을 쓰는 모든 경로를 심볼릭 링크 및 경로 탈출 공격으로부터 보호합니다.
4. `--is-format3`가 번들 실행 경로로 빠지지 않도록 수정합니다.
5. Debian maintainer script에서 네트워크 설치 스크립트 실행을 제거합니다.

## 치명적 이슈

### C1. DropIn 데몬이 경로 탈출과 심볼릭 링크를 통해 root 권한으로 파일을 쓰거나 덮어쓸 수 있음

출처 보고서: Claude C1 및 H1; Codex Findings 3 및 4; Gemini 2.1.

근거:

- `src/DEBIAN/postinst:57`에서 DropIn 번들을 서비스로 설치합니다.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:201-215`에서 `write_text`/`write_bytes`로 파일을 쓴 뒤 `chmod`와 `os.chown`을 실행합니다.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:398-408`에서 신뢰할 수 없는 `app_id`를 사용자별 데스크톱/아이콘 경로에 사용합니다.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:609-625`에서 사용자 홈 하위 경로의 소유권을 재귀적으로 변경합니다.

영향:

DropIn 서비스는 root로 실행되며 사용자 제어 홈 디렉터리에 파일을 씁니다. 로컬 사용자는 경로 탈출 요소가 들어간 번들 ID를 사용하거나, 예상되는 데스크톱/아이콘 위치에 심볼릭 링크를 미리 만들 수 있습니다. 그 결과 데몬이 심볼릭 링크를 따라가 root가 쓸 수 있는 대상을 덮어쓰고, 소유권이나 권한을 바꿀 수 있습니다. 이는 현실적인 로컬 권한 상승 경로입니다.

수정:

경로 사용 전에 안전하지 않은 번들 ID를 거부합니다. `O_NOFOLLOW | O_CREAT | O_EXCL`을 포함한 `os.open`을 사용하고, `fchmod`/`fchown`처럼 파일 디스크립터 기반 작업을 사용하며, 모든 상위 디렉터리를 `lstat`으로 검증합니다. 가능하면 해당 사용자 홈에 파일을 쓰기 전에 대상 사용자 권한으로 낮춰서 실행합니다.

### C2. 따옴표 처리되지 않은 셸 명령 구성으로 인한 권한 상승 명령 주입

출처 보고서: Codex Findings 1, 2, 7, 9; Claude M15; Gemini 2.2.

근거:

- `src/usr/bin/apprun.py:338-348`에서 명령 인자를 `" ".join(gui_cmds)`로 합친 뒤 `bash -c`로 실행합니다.
- `src/usr/bin/apprun.py:500-508`에서 GUI 패키지 설치 시 `pkexec apt install`에 같은 헬퍼를 사용합니다.
- `src/usr/bin/apprun.py:878-907`에서 번들 내 `services/*.service` 이름을 systemd 유닛 이름으로 검증하지 않고 받아들입니다.
- `src/usr/bin/apprun.py:1874-1878` 및 `src/usr/bin/apprun.py:1881-1892`에서 서비스 이름을 합쳐 `systemctl` 셸 문자열을 만듭니다.
- `src/usr/bin/apprun.py:1806-1817`에서 권한 상승된 배치 스크립트를 `bash -c`로 실행합니다.

영향:

번들이 제어하는 패키지 이름, 파일명, 서비스 이름, 경로, 메타데이터가 셸 문자열에 삽입될 수 있습니다. 이 경로가 `pkexec`, `sudo`, root 재실행을 통해 실행되면 root 명령 실행으로 이어질 수 있습니다.

수정:

가능한 모든 곳에서 `subprocess.run([...])` 형태의 argv 기반 직접 실행을 사용합니다. 셸이 불가피하면 고정된 wrapper와 위치 인자를 사용하고 모든 값을 인용합니다. apt나 systemctl 호출 전 Debian 패키지 이름과 systemd 유닛 이름을 엄격한 allowlist로 검증합니다.

### C3. 데스크톱 항목 주입 및 안전하지 않은 `.desktop` 전파

출처 보고서: Claude C2, C3, H2, M11; Codex Finding 8.

근거:

- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:248-296`에서 번들 내부 `desktopfile.desktop`의 대부분 라인을 그대로 통과시킵니다.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:267`, `271`, `330`에서 `Exec=apprun3 {apprunx_path}`를 견고한 desktop-entry escaping 없이 씁니다.
- `src/usr/bin/apprun.py:852-863`에서 `Name`, `Comment`, `Exec`, `Icon`, `StartupWMClass` 값을 escape하지 않고 `.desktop` 파일을 씁니다.
- `src/usr/bin/apprun.py:1127-1144`에 더 안전한 포매터가 있지만 GUI autostart 경로에서만 사용됩니다.

영향:

악의적 번들이 추가 desktop key, 비정상 값, field code, 실행 인자를 삽입할 수 있습니다. DropIn은 감지된 모든 사용자에게 항목을 쓰므로, 감시 디렉터리에 있는 하나의 악성 번들이 여러 계정에 악성 애플리케이션 런처를 만들 수 있습니다.

수정:

번들의 임의 `.desktop` key를 그대로 통과시키지 않습니다. 고정 템플릿으로 데스크톱 파일을 생성하고, 모든 값에서 개행 및 제어 문자를 거부하며, `Exec` 인자를 일관되게 escape하고, 필요한 경우 위험한 desktop field-code 문자가 포함된 경로 값을 거부합니다.

## 높은 위험 이슈

### H1. 번들 ID가 파일시스템 및 UI 식별자로 신뢰됨

출처 보고서: Claude C1 및 C2; Codex Finding 3.

근거:

- `src/usr/lib/python3/dist-packages/libapprun.py:37-63`에서 `AppRunMeta/id`를 그대로 반환합니다.
- `src/usr/lib/python3/dist-packages/libapprun.py:157-182`에서 ID를 mount, box, portable data 경로에 사용합니다.
- `src/usr/bin/apprun.py:844-863`에서 ID를 데스크톱/아이콘 파일명에 사용합니다.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:398-408`에서 ID를 사용자별 데스크톱/아이콘 경로에 사용합니다.

영향:

`/`, `..`, 개행, leading dot, 제어 문자가 포함된 ID는 의도한 디렉터리를 벗어나거나, 잘못된 파일을 만들거나, desktop content를 주입하거나, 저장소 구조를 불안정하게 만들 수 있습니다.

수정:

표준 ID 검증기를 추가합니다. 기본값으로는 `[A-Za-z0-9_.-]`만 허용하는 reverse-DNS 형태를 권장하며, 빈 component, `..`, 명령 인자로 쓰일 때의 leading dash, 경로 구분자를 금지합니다.

### H2. `--is-format3`가 파싱되지만 번들을 실행할 수 있음

출처 보고서: Codex Finding 5.

근거:

- `src/usr/bin/apprun.py:1928-1930`에서 `--is-format3`를 파싱합니다.
- `src/usr/bin/apprun.py:2042-2082`에서 이 플래그를 처리하지 않아 `handle_run`으로 떨어질 수 있습니다.

영향:

무해한 포맷 검사라고 기대한 호출이 신뢰할 수 없는 번들을 마운트, 준비, 의존성 설치, 실행할 수 있습니다.

수정:

`--is-format3`를 실행/준비 경로보다 먼저 처리합니다. 패키지 구조만 확인하고 `true`/`false`를 반환해야 합니다.

### H3. Debian `postinst`가 root 권한으로 원격 설치 스크립트를 실행함

출처 보고서: Claude H7; Codex Finding 6.

근거:

- `src/DEBIAN/postinst:5-13`에서 `curl -LsSf https://astral.sh/uv/install.sh | sh`를 실행합니다.
- `src/DEBIAN/postinst:8-24`에서 `$HOME/.local/bin/uv`와 `uvx`가 생성됐다고 가정하고 `/usr/local/bin`으로 이동합니다.

영향:

패키지 설치가 실시간 네트워크 상태와 변경 가능한 원격 셸 스크립트에 의존합니다. upstream 침해, MITM, 잘못된 응답이 root 권한 실행 또는 반쯤 설정된 패키지 상태로 이어질 수 있습니다.

수정:

maintainer script에서 네트워크 설치 프로그램을 실행하지 않습니다. apt dependency, checksum/signature 검증이 있는 vendored versioned binary, 또는 명확한 수동 설치 안내 실패로 바꿉니다.

### H4. 생성되는 systemd 유닛이 안전하지 않은 메타데이터와 dependency 문자열을 받음

출처 보고서: Codex Finding 7; Claude M14 및 M15.

근거:

- `src/usr/bin/apprun.py:998-999`에서 `After`와 `Before` spec 문자열을 유닛 이름 검증 없이 변환합니다.
- `src/usr/bin/apprun.py:1260-1283`에서 번들 메타데이터를 system service에 삽입합니다.
- `src/usr/bin/apprun.py:1378-1398`에서 번들 메타데이터를 global user service에 삽입합니다.

영향:

description, service spec, dependency list의 개행이나 잘못된 문자가 잘못된 unit file을 만들거나 추가 directive를 주입할 수 있습니다.

수정:

제한된 helper를 통해 unit file을 직렬화합니다. 유닛 이름을 검증하고 제어 문자를 거부하며 모든 unit 값의 개행을 escape하거나 거부합니다.

### H5. GUI startup 설치의 root 파일 쓰기도 같은 symlink/TOCTOU 문제를 가짐

출처 보고서: Claude H10; Codex Finding 4.

근거:

- `src/usr/bin/apprun.py:1580-1659`에서 user 또는 global autostart 위치에 저장된 번들과 `.desktop` 파일을 씁니다.
- `src/usr/bin/apprun.py:1635-1646`에서 디렉터리 생성 및 파일 쓰기를 한 뒤 소유권을 보정합니다.

영향:

다른 사용자 또는 global scope를 위해 root로 재실행될 때, 사용자 제어 home path와 중간 디렉터리가 symlink로 대체되거나 race condition의 대상이 될 수 있습니다.

수정:

각 path component를 `lstat`으로 검증하고 symlink를 거부하며, file descriptor 기반으로 쓰고, 최종 경로에 노출하기 전에 소유권을 설정합니다.

### H6. `AppContext` box 파일 API가 경로 탈출을 허용함

출처 보고서: Claude M7; Codex Finding 9.

근거:

- `src/usr/lib/AppRun/libs/AppContext.py:258-259`에서 호출자 입력을 box 하위에 직접 join합니다.
- `src/usr/lib/AppRun/libs/AppContext.py:360-380`에서 호출자가 제공한 filename에 씁니다.
- `src/usr/lib/AppRun/libs/AppContext.py:382-413`에서 호출자가 제공한 filename을 읽습니다.

영향:

API는 box-scoped로 보이지만, `../` 또는 절대 경로가 box를 벗어나 프로세스 권한으로 가능한 임의 경로를 읽거나 쓸 수 있습니다.

수정:

최종 경로를 resolve한 뒤 resolved box root 내부인지 확인합니다. 절대 경로, `..`, NUL/제어 문자, 필요한 경우 symlink escape를 거부합니다.

### H7. 번들 메타데이터 기반 패키지 설치가 지나치게 허용적임

출처 보고서: Claude H9; Codex Finding 1.

근거:

- `src/usr/lib/python3/dist-packages/libapprun.py:315-333`에서 번들 메타데이터의 `apt-requirements`를 읽습니다.
- `src/usr/bin/apprun.py:495-527`에서 requirement를 package name으로 줄인 뒤 `apt`/`apt-get`을 호출합니다.

영향:

번들이 임의 apt 패키지 설치를 유도하거나 충분한 가시성 없이 특정 버전/다운그레이드를 요구할 수 있습니다. GUI 경로에서는 C2의 명령 주입 문제와도 연결됩니다.

수정:

설치 전 전체 requirement를 그대로 보여주고, package name과 version constraint를 검증하며, 자동 dependency 설치에는 policy/allowlist를 고려합니다.

### H8. Thumbnailer가 제한 없이 신뢰할 수 없는 아이콘 데이터를 처리함

출처 보고서: Claude M12; Codex Finding 13.

근거:

- `src/usr/lib/python3/dist-packages/libapprun.py:109-117`에서 추출된 전체 바이트를 메모리에 담습니다.
- `src/usr/bin/apprunx-thumbnailer.py:70-99`에서 추출 아이콘에 ImageMagick `convert`를 실행합니다.

영향:

조작된 번들이 메모리 압박, 느린 이미지 처리, ImageMagick parser/delegate 취약점 노출을 유발할 수 있습니다.

수정:

추출 아이콘 크기를 제한하고, PNG magic과 dimension을 검증하며, 썸네일 크기에 상한을 두고, subprocess timeout을 설정합니다. 더 안전한 이미지 라이브러리 또는 명시적 PNG decoding을 사용합니다.

### H9. DropIn 서비스 제거 경로의 대소문자가 맞지 않음

출처 보고서: Claude H8; Codex Finding 10.

근거:

- `src/DEBIAN/postinst:57`은 `/usr/lib/AppRun/AppRunDropInService.apprunx`를 설치합니다.
- `src/DEBIAN/prerm:3`은 `/usr/lib/AppRun/AppRunDropinService.apprunx`를 제거하려고 합니다.

영향:

대소문자를 구분하는 파일시스템에서 패키지 제거 후 stale systemd service와 저장된 번들 상태가 남을 수 있습니다.

수정:

공유 path constant를 사용하거나 대소문자를 바로잡습니다. package install/purge 테스트를 추가합니다.

### H10. 직접 서비스 설치가 번들 내 service file을 그대로 복사함

출처 보고서: Claude M14; Codex Finding 2.

근거:

- `src/usr/bin/apprun.py:870-962`에서 번들 내 `.service` 파일을 system service store에 복사하고 systemd에 링크합니다.

영향:

의도된 기능일 수 있지만, 사용자는 `ExecStart`, `User`, `Group`, 권한 수준에 대한 신뢰할 만한 요약을 보지 못합니다. 사용자가 모호한 prompt를 수락하면 번들이 root로 실행되는 서비스를 설치할 수 있습니다.

수정:

설치 전에 민감한 directive 요약을 보여주고, root로 실행되거나 광범위한 권한이 있는 서비스에는 명시적 확인을 요구합니다.

## 중간 위험 이슈

### M1. Mount lifecycle이 취약함

출처 보고서: Claude H3, H4, H5, M3, L9; Codex Finding 14; Gemini 3.2.

근거:

- `src/usr/lib/python3/dist-packages/libapprun.py:149-152`에서 `/proc/mounts`를 substring matching으로 검사합니다.
- `src/usr/lib/python3/dist-packages/libapprun.py:154-158`에서 mount suffix에 `random.choices`를 사용합니다.
- `src/usr/bin/apprun.py:609-693`에서 `finally` block에 unmount cleanup을 의존합니다.
- `src/usr/lib/python3/dist-packages/libapprun.py:143-146`에서 unmount 직후 directory를 제거합니다.

영향:

잘못된 mounted 판정, collision, 강제 종료 후 stale FUSE mount, `Device or resource busy` race가 실행 실패나 resource leak을 유발할 수 있습니다.

수정:

`/proc/mounts`를 정확히 parsing하고, `secrets` 또는 `tempfile.mkdtemp`를 사용하며, mount root를 `0700`으로 만들고, unmount와 directory cleanup을 분리하며, 시작 시 orphan mount를 정리합니다.

### M2. Build script가 workspace ownership과 permission을 변경함

출처 보고서: Claude L4; Codex Finding 15; Gemini 3.1.

근거:

- `build.sh:16-21`에서 `src` ownership과 mode를 재귀적으로 바꿉니다.
- `build-nogui.sh:7-15`에서 `src/DEBIAN/control`을 제자리 수정하고 정상 완료 시에만 복원합니다.

영향:

빌드가 중단되면 workspace가 root 소유로 남거나 control file이 수정된 채 남을 수 있습니다. `chmod -R 755`는 data file을 executable로 만들고 의도한 file mode를 잃게 합니다.

수정:

`dpkg-deb --root-owner-group` 또는 `fakeroot`를 사용하고, 임시 디렉터리에서 빌드하며, 임시 수정은 trap을 통해 복원합니다.

### M3. `AppContext` locking이 예측 가능하고 stale 상태를 남길 수 있음

출처 보고서: Claude M8 및 M9; Gemini 2.3.

근거:

- `src/usr/lib/AppRun/libs/AppContext.py:196-208`에서 global lock에 `/tmp`의 예측 가능한 lock file name을 사용합니다.
- `src/usr/lib/AppRun/libs/AppContext.py:639-668`에서 stale lock 처리 중 재귀 호출이 발생할 수 있습니다.
- `src/usr/lib/AppRun/libs/AppContext.py:680-682`에서 `SIGINT`와 `SIGTERM`만 처리합니다.

영향:

다른 로컬 사용자가 lock path를 미리 만들어 denial of service를 유발할 수 있습니다. stale 또는 malformed lock file은 혼란스러운 동작을 만들 수 있고, 일부 signal은 lock을 남길 수 있습니다.

수정:

안전한 per-app lock directory 또는 abstract Unix socket을 사용하고, stale-lock retry 횟수를 제한하며, boot identity/PID 검사를 포함하고, signal handler를 chain/restore합니다.

### M4. DropIn 데몬이 잘못된 metadata와 noisy watch에 취약함

출처 보고서: Codex Finding 11; Claude M10 및 L10.

근거:

- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:123-124`에서 config JSON을 schema validation 없이 로드합니다.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:307-324`에서 metadata value type을 가정합니다.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:543-561`에서 event handler가 local exception handling 없이 registration을 호출합니다.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:574-591`에서 passwd 변경 감지를 위해 `/etc`를 넓게 watch합니다.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:183-187`에서 cache를 non-atomic하게 저장합니다.

영향:

잘못된 번들 또는 config가 데몬 crash나 systemd restart loop를 유발할 수 있습니다. busy host에서는 불필요한 event churn이 생기고, cache corruption은 전체 재등록을 유발합니다.

수정:

schema와 type을 검증하고, 파일별 registration failure를 잡고, passwd 변경 watch를 좁히거나 debounce하며, cache를 atomic하게 저장합니다.

### M5. `.desktop` 파일이 executable로 저장됨

출처 보고서: Claude M11.

근거:

- `src/usr/bin/apprun.py:864`에서 desktop file을 `0755`로 chmod합니다.
- `src/usr/lib/AppRun/AppRunDropInService.apprunxproj/main.py:400`에서 DropIn desktop entry를 `0755`로 씁니다.

영향:

Executable `.desktop` 파일은 desktop environment의 trust UX를 우회하거나 혼란스럽게 만들 수 있습니다.

수정:

의도적으로 관리되는 desktop-specific trust mechanism이 없다면 `0644`를 사용합니다.

### M6. `dictionary.py`가 collection path traversal을 허용함

출처 보고서: Gemini 2.4.

근거:

- `src/usr/bin/dictionary.py:12-20`에서 `/usr/share/dictionaries`와 사용자 제공 `--dict-collection`을 join합니다.

영향:

`../` 입력으로 의도한 dictionary directory 밖의 JSON 파일을 읽을 수 있습니다. 위험도는 낮지만 path expectation을 약화합니다.

수정:

최종 경로를 resolve하고 `/usr/share/dictionaries` 아래에 남는지 확인하거나, collection ID를 허용 문자 집합으로 제한합니다.

### M7. Packaging tool이 확인 없이 output path를 덮어쓸 수 있음

출처 보고서: Claude M13.

근거:

- `src/usr/bin/apprun-package.py:120-123`에서 기존 output path를 unlink합니다.

영향:

`-o` 오타로 중요한 파일을 삭제할 수 있습니다.

수정:

덮어쓰기에는 `--force`를 요구하거나, AppRun artifact가 아닌 파일은 덮어쓰지 않습니다.

### M8. AppContext cache와 metadata path의 정확성 문제

출처 보고서: Codex Finding 16.

근거:

- `src/usr/lib/AppRun/libs/AppContext.py:407-410`에서 `read()`는 bytes를 반환한다고 보이지만 decoded string을 cache할 수 있습니다.
- `src/usr/lib/AppRun/libs/AppContext.py:488` 및 `601-602`에서 `AppRunMeta/DesktopLink`를 사용하지만, 프로젝트의 다른 부분은 `AppRunMeta/DesktopLinks`를 사용합니다.

영향:

호출자가 일관되지 않은 type을 받을 수 있고, icon/terminal detection이 조용히 실패할 수 있습니다.

수정:

byte cache와 text cache를 분리합니다. `DesktopLinks`를 지원하고, 필요하다면 `DesktopLink`는 backward-compatible fallback으로만 유지합니다.

### M9. 권한 상승 script batching이 부분 실패를 숨김

출처 보고서: Claude M15 및 M16; Codex Finding 2.

근거:

- `src/usr/bin/apprun.py:1806-1817`에서 `bash -c`를 실행하고 마지막 command status만 보고합니다.
- `src/usr/bin/apprun.py:1187-1190`에서 symlink를 unlink 후 생성하는 비원자적 방식으로 교체합니다.

영향:

중간 command 실패가 이후 command 성공에 가려져 일부만 설치된 unit이나 link가 남을 수 있습니다. 동시 설치가 interleave될 수 있습니다.

수정:

셸 batching을 피하거나 최소한 `bash -ec`를 사용합니다. 임시 link와 `os.replace`를 통한 atomic symlink replacement를 사용합니다.

### M10. Crash detection이 정상적인 빠른 종료에도 경고할 수 있음

출처 보고서: Gemini 3.3.

근거:

- `src/usr/bin/apprun.py:816-830`에서 `Application`이 1초 미만에 정상 종료해도 abnormal-exit warning을 표시합니다.

영향:

정상적인 짧은 실행 도구가 사용자에게 고장난 것처럼 보일 수 있습니다.

수정:

기본적으로 nonzero exit에만 경고하거나, fast-exit warning opt-in metadata를 추가합니다.

### M11. Maintainer script의 post-install cleanup이 신뢰하기 어려움

출처 보고서: Codex Finding 12; Claude H7.

근거:

- `src/DEBIAN/postinst:66-71`에서 `set +e`로 전환하고, root maintainer script 안에서 `sudo`를 호출하며, `xdg-mime`을 실행하고, `~/.cache/thumbnails/`를 삭제합니다.

영향:

실패가 숨겨지고, `sudo`가 없을 수 있으며, `~`가 desktop user home을 가리키지 않을 수 있습니다.

수정:

`sudo`를 제거하고, 선택적 cache/database update를 명시적으로 처리하며, package installation 중 사용자 cache 삭제를 피합니다.

### M12. 기타 견고성 문제

출처 보고서: Claude M1, M2, M5, L5, L11, L12; Codex Findings 14 및 15.

근거 및 영향:

- `src/usr/lib/python3/dist-packages/libapprun.py:98-106`에서 추출 파일을 text로 decode합니다. binary 또는 invalid UTF-8에서 문제가 생길 수 있습니다.
- `src/usr/lib/python3/dist-packages/libapprun.py:120-129`에서 `unsquashfs -l` text output을 parsing하므로 특이한 filename에 취약합니다.
- `src/usr/bin/apprun.py:2038`에서 입력을 bundle로 다루기 전에 `Path.exists()`만 검사합니다. FIFO, directory, special file이 mount 시도까지 도달할 수 있습니다.
- 여러 `subprocess.run` 호출이 return code를 무시하며, 일부 systemd 경로도 포함됩니다.
- `apprun-package.py` size calculation은 symlink 때문에 왜곡될 수 있습니다.

수정:

binary data는 bytes로 읽고, archive listing은 더 구조화된 방식으로 parsing하며, bundle input은 regular file인지 검사하고, subprocess return code를 확인하며, symlink-aware size calculation을 사용합니다.

## 통합 수정 계획

1. 중앙 validator를 구현합니다: `app_id`, Debian package name, systemd unit name, desktop value, safe relative path, service spec.
2. 권한 상승 셸 문자열 호출을 argv 호출로 바꿉니다. 셸이 남는 곳은 모든 값을 인용하고 `set -e`를 사용합니다.
3. DropIn 및 GUI startup 파일 쓰기를 descriptor 기반 no-symlink write 또는 privilege dropping으로 강화합니다.
4. 모든 `.desktop` 생성을 하나의 안전한 serializer와 고정 key allowlist로 교체합니다.
5. `--is-format3`를 수정하고, 번들을 실행하거나 준비하지 않는다는 regression test를 추가합니다.
6. `postinst`에서 `curl | sh`를 제거하고 deterministic dependency 또는 검증된 vendored artifact를 사용합니다.
7. `prerm` 대소문자 문제를 수정하고 package install/remove 테스트를 추가합니다.
8. Mount lifecycle을 강화합니다: 정확한 mount detection, 안전한 random mount directory, orphan cleanup, robust unmount cleanup.
9. 사용자에게 prompt하기 전 package/service installation behavior를 제한하고 명확히 표시합니다.
10. 악성 app ID, service filename, symlinked target file, space/percent가 포함된 path, malformed metadata, malformed dictionary, fast-exit application에 대한 테스트를 추가합니다.

## 원본 보고서별 주요 기여

- Claude 보고서는 root DropIn path traversal/symlink 문제, desktop-entry 악용, mount lifecycle 위험, `prerm` typo, AppContext traversal, service/unit handling을 중점적으로 지적했습니다.
- Codex 보고서는 shell injection surface, 중앙 validation 부재, `--is-format3` fall-through, maintainer-script supply chain risk, thumbnailer limit, desktop/systemd serializer 문제를 중점적으로 지적했습니다.
- Gemini 보고서는 DropIn symlink overwrite, service-install command injection, global lock DoS, dictionary traversal, build-script ownership mutation, unmount race, false positive crash warning을 중점적으로 지적했습니다.
