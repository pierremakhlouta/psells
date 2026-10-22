"""Tests for what schedules the backup.

backup.sh itself talks to Docker, so it is checked by shellcheck in CI and was
exercised against a real PostgreSQL by hand, failure paths included. The job
file that runs it is plain data and can be held here: if it stops parsing, or
stops pointing at backup.sh, the backups stop and nothing says so until the
log is read.
"""

import os
import plistlib
import shutil
import subprocess

import pytest

import psells


PLIST = os.path.join(psells.PROJECT_DIR, "launchd", "local.psells.backup.plist")


def job():
    with open(PLIST, "rb") as template:
        return plistlib.load(template)


def test_the_job_runs_backup_sh_from_the_project_with_bash():
    assert job()["ProgramArguments"] == [
        "/bin/bash", "__PROJECT_DIR__/backup.sh"]


def test_the_job_runs_daily_at_nine():
    assert job()["StartCalendarInterval"] == {"Hour": 9, "Minute": 0}


def test_the_job_is_a_template_with_no_personal_paths():
    # Filled in on install. A real home folder here would put a username in a
    # public repository and break on every other machine.
    with open(PLIST) as template:
        text = template.read()

    assert "/Users/" not in text
    assert job()["StandardOutPath"].startswith("__HOME__/")
    assert job()["StandardErrorPath"].startswith("__HOME__/")


def test_the_script_the_job_runs_is_executable_and_exists():
    script = os.path.join(psells.PROJECT_DIR, "backup.sh")

    assert os.access(script, os.X_OK)



# The login job that starts the stack ----------------------------------------------
#
# Added after 7 October 2026, when Docker Desktop came back after a boot and
# restarted none of the stack's containers. start-stack.sh is run here in a
# copy of the project, with stand-ins for docker and sleep that only record
# what they were asked, so no test ever reaches the real Docker.

START_PLIST = os.path.join(psells.PROJECT_DIR, "launchd",
                           "local.psells.start.plist")
START_SCRIPT = os.path.join(psells.PROJECT_DIR, "start-stack.sh")


def start_job():
    with open(START_PLIST, "rb") as template:
        return plistlib.load(template)


def test_the_start_job_runs_start_stack_sh_once_at_login():
    job = start_job()

    assert job["Label"] == "local.psells.start"
    assert job["ProgramArguments"] == ["/bin/bash",
                                       "__PROJECT_DIR__/start-stack.sh"]
    assert job["RunAtLoad"] is True
    # Once, not kept alive or repeated.
    assert "KeepAlive" not in job and "StartInterval" not in job


def test_the_start_job_is_a_template_with_no_personal_paths():
    with open(START_PLIST) as template:
        text = template.read()

    assert "/Users/" not in text
    for key in ("StandardOutPath", "StandardErrorPath"):
        assert start_job()[key].startswith("__HOME__/Library/Logs/"), key
    assert os.access(START_SCRIPT, os.X_OK)


def stand_in(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


NOTIFY_SCRIPT = os.path.join(psells.PROJECT_DIR, "notify.sh")


def stand_in_osascript(bin_dir, tmp_path):
    """An osascript that records each notification's arguments and script."""
    record = tmp_path / "notifications"
    stand_in(bin_dir / "osascript",
             f'for arg in "$@"; do printf "%s|" "$arg" >> "{record}"; done\n'
             f'echo >> "{record}"\ncat > "{tmp_path}/applescript"\n')


def notifications(tmp_path):
    record = tmp_path / "notifications"
    return record.read_text().splitlines() if record.exists() else []


def run_start(tmp_path, real_stack=True, docker_up=True):
    """start-stack.sh in a copy of the project; returns (exit code, the
    docker calls it made, its log)."""
    project = tmp_path / "psells"
    project.mkdir()
    shutil.copy(START_SCRIPT, project / "start-stack.sh")
    shutil.copy(NOTIFY_SCRIPT, project / "notify.sh")
    if real_stack:
        (project / "data").mkdir()
        (project / "data" / "config.json").write_text("{}")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    stand_in(bin_dir / "docker",
             f'echo "$*" >> "{calls}"\n'
             f'[ "$1" = info ] && exit {0 if docker_up else 1}\nexit 0\n')
    # Twenty minutes of waiting, in no time.
    stand_in(bin_dir / "sleep", "exit 0\n")
    stand_in_osascript(bin_dir, tmp_path)

    home = tmp_path / "home"
    result = subprocess.run(
        ["bash", str(project / "start-stack.sh")], capture_output=True,
        text=True, env=dict(os.environ, HOME=str(home),
                            PATH=f"{bin_dir}:{os.environ['PATH']}"))
    log = home / "Library" / "Logs" / "psells-start.log"

    return (result.returncode,
            calls.read_text().splitlines() if calls.exists() else [],
            log.read_text() if log.exists() else "")


def test_it_starts_what_is_stopped_and_recreates_nothing(tmp_path):
    code, calls, log = run_start(tmp_path)

    assert code == 0
    up = [call for call in calls if " up " in f" {call} "]
    assert len(up) == 1
    assert up[0].startswith("compose --project-directory ")
    assert up[0].endswith(" up -d --wait --no-recreate")
    # Whole arguments, not substrings: the temporary path can contain "rm".
    arguments = {word for call in calls for word in call.split()}
    assert not arguments & {"--build", "down", "restart", "rm", "stop",
                            "--force-recreate"}
    assert "  ok  stack up:" in log


def test_it_refuses_outside_the_real_stacks_folder(tmp_path):
    code, calls, log = run_start(tmp_path, real_stack=False)

    assert code == 1
    assert calls == []
    assert "FAILED: no data/config.json" in log


def test_it_gives_up_if_docker_never_starts(tmp_path):
    code, calls, log = run_start(tmp_path, docker_up=False)

    assert code == 1
    assert calls and all(call == "info" for call in calls)
    # It waited: two hundred and forty tries, five seconds apart.
    assert len(calls) == 241
    assert "FAILED: Docker Desktop did not start" in log


# The hourly analytics refresh -------------------------------------------------
#
# refresh-analytics.sh is run here in a copy of the project, with stand-ins
# for docker and sleep that record what they were asked and answer as told,
# so no test reaches the real Docker.

ANALYTICS_PLIST = os.path.join(psells.PROJECT_DIR, "launchd",
                               "local.psells.analytics.plist")
REFRESH_SCRIPT = os.path.join(psells.PROJECT_DIR, "refresh-analytics.sh")


def analytics_job():
    with open(ANALYTICS_PLIST, "rb") as template:
        return plistlib.load(template)


def test_the_analytics_job_runs_the_refresh_on_the_hour_and_at_login():
    job = analytics_job()

    assert job["Label"] == "local.psells.analytics"
    assert job["ProgramArguments"] == ["/bin/bash",
                                       "__PROJECT_DIR__/refresh-analytics.sh"]
    assert job["StartCalendarInterval"] == {"Minute": 0}
    assert job["RunAtLoad"] is True
    assert "KeepAlive" not in job


def test_the_analytics_job_is_a_template_with_no_personal_paths():
    with open(ANALYTICS_PLIST) as template:
        text = template.read()

    assert "/Users/" not in text
    for key in ("StandardOutPath", "StandardErrorPath"):
        assert analytics_job()[key].startswith("__HOME__/Library/Logs/"), key
    assert os.access(REFRESH_SCRIPT, os.X_OK)


def run_refresh(tmp_path, real_stack=True, db_health="healthy", etl_ok=True,
                earlier_log=""):
    """refresh-analytics.sh in a copy of the project; returns (exit code, the
    docker calls it made, its log)."""
    project = tmp_path / "psells"
    project.mkdir(parents=True, exist_ok=True)
    shutil.copy(REFRESH_SCRIPT, project / "refresh-analytics.sh")
    shutil.copy(NOTIFY_SCRIPT, project / "notify.sh")
    if real_stack:
        (project / "data").mkdir()
        (project / "data" / "config.json").write_text("{}")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    calls = tmp_path / "calls"
    stand_in_osascript(bin_dir, tmp_path)
    stand_in(bin_dir / "docker", f'''echo "$*" >> "{calls}"
case "$*" in
  info*) exit 0 ;;
  inspect*) echo {db_health} ;;
  *" run --rm --no-deps etl"*)
    {"echo 'Warehouse rebuilt: 3 products, 2 sales, 0 returns, 1 payments, 9 days.'; exit 0" if etl_ok else "echo 'The warehouse does not add up to psells figures, so it was not changed: total_sold' >&2; exit 1"} ;;
esac
exit 0
''')
    stand_in(bin_dir / "sleep", "exit 0\n")

    home = tmp_path / "home"
    if earlier_log:
        (home / "Library" / "Logs").mkdir(parents=True, exist_ok=True)
        (home / "Library" / "Logs" / "psells-etl.log").write_text(earlier_log)
    result = subprocess.run(
        ["bash", str(project / "refresh-analytics.sh")], capture_output=True,
        text=True, env=dict(os.environ, HOME=str(home),
                            PATH=f"{bin_dir}:{os.environ['PATH']}"))
    log = home / "Library" / "Logs" / "psells-etl.log"

    return (result.returncode,
            calls.read_text().splitlines() if calls.exists() else [],
            log.read_text() if log.exists() else "")


def test_the_refresh_brings_up_the_warehouse_and_runs_the_etl_alone(tmp_path):
    code, calls, log = run_refresh(tmp_path)
    compose = [c for c in calls if c.startswith("compose ")]

    assert code == 0
    assert len(compose) == 2
    assert compose[0].endswith(" up -d --wait warehouse")
    assert compose[1].endswith(" run --rm --no-deps etl")
    for call in compose:
        assert "-f " + str(tmp_path / "psells" / "compose.analytics.yaml") in call
    # It never touches the business stack, and never builds.
    for call in calls:
        for word in (" down", " stop", " restart", "--build", " rm ",
                     " up -d --wait db", " app", " proxy"):
            assert word not in call, (word, call)
    assert log.endswith("ok  Warehouse rebuilt: 3 products, 2 sales, 0 returns, "
                        "1 payments, 9 days.\n")


def test_a_failed_etl_is_logged_with_its_reason(tmp_path):
    code, _, log = run_refresh(tmp_path, etl_ok=False)

    assert code == 1
    assert "FAILED: the ETL did not complete: The warehouse does not add up" in log


def test_the_refresh_waits_for_a_healthy_database_and_never_starts_it(tmp_path):
    code, calls, log = run_refresh(tmp_path, db_health="starting")

    assert code == 1
    assert sum(c.startswith("inspect ") for c in calls) == 121
    assert not [c for c in calls if c.startswith("compose ")]
    assert "FAILED: the business database was not healthy within ten minutes" in log


def test_the_refresh_refuses_outside_the_real_stacks_folder(tmp_path):
    code, calls, log = run_refresh(tmp_path, real_stack=False)

    assert code == 1
    assert calls == []
    assert "not the real stack's folder" in log


# The off-Mac copy -------------------------------------------------------------
#
# offsite-backup.sh is run here for real, with the real age, a key made for
# the test, and a stand-in for security that hands that key over as the
# Keychain would.

OFFSITE_SCRIPT = os.path.join(psells.PROJECT_DIR, "offsite-backup.sh")
BACKUP_SCRIPT = os.path.join(psells.PROJECT_DIR, "backup.sh")


def make_key():
    made = subprocess.run(["age-keygen"], capture_output=True, text=True,
                          check=True).stdout
    secret = next(line for line in made.splitlines()
                  if line.startswith("AGE-SECRET-KEY-"))
    public = subprocess.run(["age-keygen", "-y"], input=secret + "\n",
                            capture_output=True, text=True, check=True).stdout
    return secret, public


def run_offsite(tmp_path, keychain_key=None, recipient=True, old_copy=False,
                corrupt_decryption=False):
    secret, public = make_key()
    project = tmp_path / "psells"
    (project / "data").mkdir(parents=True)
    shutil.copy(OFFSITE_SCRIPT, project / "offsite-backup.sh")
    if recipient:
        (project / "data" / "backup-recipient.txt").write_text(public)
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "psells-2026-10-09_090000.dump").write_bytes(b"invented dump \x00\x01")
    (daily / "config-2026-10-09_090000.json").write_text('{"invented": 1}')
    offsite = tmp_path / "icloud"
    if old_copy:
        offsite.mkdir()
        old = offsite / "psells-2026-08-01_090000.tar.age"
        old.write_bytes(b"old")
        os.utime(old, (0, 0))
        (offsite / "notes.txt").write_text("not ours")
        os.utime(offsite / "notes.txt", (0, 0))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand_in(bin_dir / "security",
             f"echo '{keychain_key or secret}'\n")
    if corrupt_decryption:
        # The real age, but what it decrypts comes back with one word changed.
        real_age = shutil.which("age")
        stand_in(bin_dir / "age",
                 f'case " $* " in *" -d "*) "{real_age}" "$@" | sed s/invented/inventeX/ ;;\n'
                 f'  *) exec "{real_age}" "$@" ;; esac\n')
    result = subprocess.run(
        ["bash", str(project / "offsite-backup.sh"),
         "psells-2026-10-09_090000.dump", "config-2026-10-09_090000.json"],
        capture_output=True, text=True,
        env=dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
                 PSELLS_BACKUP_DIR=str(daily), PSELLS_OFFSITE_DIR=str(offsite)))
    return result, secret, daily, offsite


def test_the_off_mac_copy_is_encrypted_and_decrypts_to_the_same_files(tmp_path):
    result, secret, daily, offsite = run_offsite(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("psells-2026-10-09_090000.tar.age  ")
    assert result.stdout.rstrip().endswith("bytes, decrypted and matched")
    (copy,) = offsite.iterdir()
    assert copy.name == "psells-2026-10-09_090000.tar.age"
    data = copy.read_bytes()
    # Ciphertext only: neither file's contents appear in it.
    assert data.startswith(b"age-encryption.org/v1\n")
    assert b"invented" not in data
    # And the key in the password manager opens it.
    key = tmp_path / "key.txt"
    key.write_text(secret + "\n")
    decrypted = subprocess.run(["age", "-d", "-i", str(key), str(copy)],
                               capture_output=True, check=True).stdout
    listing = subprocess.run(["tar", "-tf", "-"], input=decrypted,
                             capture_output=True, check=True).stdout.decode().split()
    assert sorted(listing) == ["config-2026-10-09_090000.json",
                               "psells-2026-10-09_090000.dump"]
    # The key is never printed.
    assert secret not in result.stdout + result.stderr


def test_a_copy_that_does_not_decrypt_with_the_keychains_key_is_not_kept(tmp_path):
    other, _ = make_key()
    result, _, _, offsite = run_offsite(tmp_path, keychain_key=other)

    assert result.returncode == 1
    assert "does not decrypt with the Keychain's key" in result.stderr
    assert list(offsite.iterdir()) == []


def test_a_copy_that_decrypts_to_different_bytes_is_not_kept(tmp_path):
    result, _, _, offsite = run_offsite(tmp_path, corrupt_decryption=True)

    assert result.returncode == 1
    assert "does not match the original" in result.stderr
    assert list(offsite.iterdir()) == []


def test_without_a_recipient_it_refuses_and_writes_nothing(tmp_path):
    result, _, _, offsite = run_offsite(tmp_path, recipient=False)

    assert result.returncode == 1
    assert "the off-Mac copy is not set up" in result.stderr
    assert not offsite.exists() or list(offsite.iterdir()) == []


@pytest.fixture
def unlistable():
    """Make a folder as macOS shows iCloud Drive to a job launchd starts: a
    file named in it can be written, read and removed, but the folder cannot
    be listed. Every scheduled backup failed on that from 13 October 2026.
    Listable again after the test whatever happens, or pytest cannot remove
    it."""
    made = []

    def make(folder):
        folder.mkdir(exist_ok=True)
        folder.chmod(0o333)
        made.append(folder)

    yield make
    for folder in made:
        folder.chmod(0o755)


def test_the_copy_is_made_in_a_folder_it_may_not_list(tmp_path, unlistable):
    unlistable(tmp_path / "icloud")
    result, _, _, offsite = run_offsite(tmp_path, old_copy=False)

    assert result.returncode == 0, result.stderr
    offsite.chmod(0o755)
    assert sorted(p.name for p in offsite.iterdir()) == [
        "psells-2026-10-09_090000.tar.age"]


def test_making_a_copy_removes_nothing(tmp_path):
    result, _, _, offsite = run_offsite(tmp_path, old_copy=True)

    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in offsite.iterdir()) == [
        "notes.txt", "psells-2026-08-01_090000.tar.age",
        "psells-2026-10-09_090000.tar.age"]


def run_remove(tmp_path, *names):
    project = tmp_path / "psells"
    project.mkdir(exist_ok=True)
    shutil.copy(OFFSITE_SCRIPT, project / "offsite-backup.sh")
    return subprocess.run(
        ["bash", str(project / "offsite-backup.sh"), "--remove", *names],
        capture_output=True, text=True,
        env=dict(os.environ, PSELLS_OFFSITE_DIR=str(tmp_path / "icloud")))


def test_old_copies_are_removed_by_name_without_listing_the_folder(tmp_path,
                                                                    unlistable):
    offsite = tmp_path / "icloud"
    offsite.mkdir()
    for name in ("psells-2026-08-01_090000.tar.age", "photos-2026-08-02_090000.tar.age",
                 "psells-2026-10-09_090000.tar.age", "notes.txt"):
        (offsite / name).write_bytes(b"x")
    unlistable(offsite)

    result = run_remove(tmp_path, "psells-2026-08-01_090000.tar.age",
                        "photos-2026-08-02_090000.tar.age",
                        "psells-2026-07-01_090000.tar.age")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "removed 3 old copies\n"
    offsite.chmod(0o755)
    assert sorted(p.name for p in offsite.iterdir()) == [
        "notes.txt", "psells-2026-10-09_090000.tar.age"]


@pytest.mark.parametrize("name", ["notes.txt", "../psells-1.tar.age",
                                  "psells-1.tar.age/x", "psells-*.tar.age",
                                  "other-2026-08-01.tar.age"])
def test_only_its_own_copies_can_be_removed(tmp_path, name):
    offsite = tmp_path / "icloud"
    offsite.mkdir()
    (offsite / "notes.txt").write_bytes(b"x")

    result = run_remove(tmp_path, "psells-2026-08-01_090000.tar.age", name)

    assert result.returncode == 1
    assert "not an off-Mac copy's name" in result.stderr
    assert sorted(p.name for p in offsite.iterdir()) == ["notes.txt"]


def test_no_script_lists_the_icloud_folder():
    for script in (OFFSITE_SCRIPT, BACKUP_SCRIPT, PHOTOS_SCRIPT):
        with open(script) as file:
            text = file.read()
        code = "\n".join(line for line in text.splitlines()
                         if not line.lstrip().startswith("#"))
        for listing in ('find "$OFFSITE_DIR"', 'ls "$OFFSITE_DIR"',
                        '"$OFFSITE_DIR"/*', "$OFFSITE_DIR/*"):
            assert listing not in code, (script, listing)


def test_the_backup_removes_each_old_dumps_copy_by_name():
    with open(BACKUP_SCRIPT) as file:
        text = file.read()

    assert ("OLD_DUMP_LIST=\"$(find \"$BACKUP_DIR\" -name 'psells-*.dump' "
            "-mtime +\"$KEEP_DAYS\" -print -delete)\"") in text
    assert 'COPIES+=("$name.tar.age")' in text
    assert ('REMOVED="$("$SCRIPT_DIR/offsite-backup.sh" --remove "${COPIES[@]}" 2>&1)"'
            in text)
    assert '|| fail "the off-Mac clean-up: $REMOVED"' in text


def test_the_backup_sends_the_copy_only_after_the_dump_is_proved():
    with open(BACKUP_SCRIPT) as file:
        text = file.read()

    call = '"$SCRIPT_DIR/offsite-backup.sh" "psells-$STAMP.dump" "config-$STAMP.json"'
    assert call in text
    assert text.index('mv "$PARTIAL" "$TARGET"') < text.index(call)
    assert text.index('log "ok  psells-$STAMP.dump') < text.index(call)
    assert '|| fail "the off-Mac copy: $OFFSITE"' in text
    assert os.access(OFFSITE_SCRIPT, os.X_OK)



# Notifications when a job fails ----------------------------------------------

def test_a_stack_that_does_not_start_is_notified(tmp_path):
    code, _, _ = run_start(tmp_path, docker_up=False)

    assert code == 1
    assert notifications(tmp_path) == [
        "-|PSells did not start|Docker Desktop did not start within twenty minutes|"]


def test_a_stack_that_starts_notifies_nothing(tmp_path):
    code, _, _ = run_start(tmp_path)

    assert code == 0
    assert notifications(tmp_path) == []


def test_the_refresh_notifies_its_first_failure_and_not_the_next(tmp_path):
    ok = "2026-10-09 09:00:00  ok  Warehouse rebuilt: 1 products.\n"
    failed = "2026-10-09 10:00:00  FAILED: the business database was not healthy\n"

    run_refresh(tmp_path / "after_ok", etl_ok=False, earlier_log=ok)
    run_refresh(tmp_path / "after_failed", etl_ok=False, earlier_log=ok + failed)
    run_refresh(tmp_path / "first_ever", etl_ok=False)
    run_refresh(tmp_path / "working", earlier_log=ok + failed)

    assert len(notifications(tmp_path / "after_ok")) == 1
    assert notifications(tmp_path / "after_ok")[0].startswith(
        "-|PSells analytics refresh failed|the ETL did not complete: ")
    assert notifications(tmp_path / "after_failed") == []
    assert len(notifications(tmp_path / "first_ever")) == 1
    assert notifications(tmp_path / "working") == []


def test_a_message_reaches_applescript_as_an_argument_never_as_code(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand_in_osascript(bin_dir, tmp_path)
    message = 'odd "quotes" & do shell script "touch owned"'

    result = subprocess.run(["bash", NOTIFY_SCRIPT, "PSells", message],
                            env=dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}"))

    assert result.returncode == 0
    assert notifications(tmp_path) == [f"-|PSells|{message}|"]
    assert "touch owned" not in (tmp_path / "applescript").read_text()


def test_a_notification_that_cannot_be_shown_never_fails_the_job(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand_in(bin_dir / "osascript", "exit 1\n")

    result = subprocess.run(["bash", NOTIFY_SCRIPT, "PSells", "x"],
                            env=dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}"))
    assert result.returncode == 0


def test_the_backup_notifies_every_failure():
    with open(BACKUP_SCRIPT) as file:
        text = file.read()

    fail = text[text.index("fail() {"):text.index("}", text.index("fail() {"))]
    assert '"$SCRIPT_DIR/notify.sh" "PSells backup failed" "$1" || true' in fail
    assert os.access(NOTIFY_SCRIPT, os.X_OK)


# The certificate warning -------------------------------------------------------

CERT_SCRIPT = os.path.join(psells.PROJECT_DIR, "check-certificates.sh")


def make_certificate(path, days):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt",
         "ec_paramgen_curve:P-256", "-nodes", "-days", str(days),
         "-subj", "/CN=psells.localhost", "-keyout", str(path) + ".key",
         "-out", str(path)], capture_output=True, check=True)


def run_certificates(tmp_path, mac=None, cluster=None, ca=None, openssl=None):
    """check-certificates.sh in a copy of the project, with each certificate
    lasting the given days (None: absent); returns (exit, lines, notices)."""
    project = tmp_path / "psells"
    project.mkdir()
    for name in ("check-certificates.sh", "notify.sh"):
        shutil.copy(os.path.join(psells.PROJECT_DIR, name), project / name)
    if mac is not None:
        make_certificate(project / "data" / "tls" / "psells.localhost.crt", mac)
    if cluster is not None:
        make_certificate(tmp_path / "kind" / "psells.localhost.crt", cluster)
    if ca is not None:
        make_certificate(tmp_path / "ca" / "ca.crt", ca)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand_in_osascript(bin_dir, tmp_path)
    if openssl:
        stand_in(bin_dir / "openssl", openssl)
    result = subprocess.run(
        ["bash", str(project / "check-certificates.sh")],
        capture_output=True, text=True,
        env=dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
                 PSELLS_CA_DIR=str(tmp_path / "ca"),
                 PSELLS_KIND_TLS_DIR=str(tmp_path / "kind")))
    return result.returncode, result.stdout.splitlines(), notifications(tmp_path)


def test_certificates_far_from_their_end_are_ok_and_quiet(tmp_path):
    code, lines, notices = run_certificates(tmp_path, mac=397, cluster=397, ca=1825)

    assert code == 0
    assert [line.split(":")[0] for line in lines] == [
        "The Mac's certificate", "The cluster's certificate",
        "The certificate authority"]
    assert all(": ok until " in line for line in lines)
    assert notices == []


def test_a_certificate_within_a_month_of_its_end_is_notified_with_its_renewal(tmp_path):
    code, lines, notices = run_certificates(tmp_path, mac=10, ca=1825)

    assert code == 0
    assert lines[0].startswith("The Mac's certificate: expires within 30 days, ")
    (notice,) = notices
    assert notice.startswith("-|PSells certificate expires soon|The Mac's certificate expires ")
    assert "Renew: ./make-certificate.sh, then docker compose restart proxy" in notice


def test_an_expired_certificate_says_so(tmp_path):
    stand_in_openssl = (
        'case "$*" in version) echo "OpenSSL 3 stand-in" ;; '
        '*-enddate*) echo "notAfter=Jan  1 00:00:00 2020 GMT" ;; '
        '*-checkend*) echo "Certificate will expire"; exit 1 ;; esac\n')
    code, lines, notices = run_certificates(tmp_path, mac=397, openssl=stand_in_openssl)

    assert code == 0
    assert lines == ["The Mac's certificate: EXPIRED Jan  1 00:00:00 2020 GMT"]
    assert notices[0].startswith("-|PSells certificate expired|")


def test_a_missing_certificate_is_skipped(tmp_path):
    code, lines, notices = run_certificates(tmp_path, mac=397)

    assert code == 0
    assert len(lines) == 1 and notices == []


def test_the_backup_runs_the_certificate_check_and_logs_it():
    with open(BACKUP_SCRIPT) as file:
        text = file.read()

    assert 'done < <("$SCRIPT_DIR/check-certificates.sh")' in text
    assert 'log "certificate  $line"' in text
    # Before the off-Mac copy, whose failure would end the run.
    assert text.index("check-certificates.sh") < text.index("offsite-backup.sh\" \"psells")


def test_an_unreadable_certificate_is_notified(tmp_path):
    (tmp_path / "ca").mkdir()
    (tmp_path / "ca" / "ca.crt").write_text("not a certificate\n")

    code, lines, notices = run_certificates(tmp_path)

    assert code == 0
    assert lines == ["The certificate authority: unreadable"]
    assert notices[0].startswith("-|PSells certificate unreadable|The certificate authority: ")


def test_the_ca_is_warned_about_before_renewals_would_be_refused(tmp_path):
    # make-certificate.sh signs nothing that would outlive the CA, so with
    # fewer than 397 days left neither certificate could be renewed.
    code, lines, notices = run_certificates(tmp_path, ca=420)

    assert code == 0
    assert lines[0].startswith("The certificate authority: expires within 427 days, ")
    (notice,) = notices
    assert notice.startswith("-|PSells certificate expires soon|The certificate authority expires ")


def test_the_check_reads_what_openssl_says_not_its_exit_status(tmp_path):
    # OpenSSL 3.6.0 printed "Certificate will expire" and exited 0.
    stand_in_openssl = (
        'case "$*" in version) echo "OpenSSL 3.6.0 stand-in" ;; '
        '*-enddate*) echo "notAfter=Nov  1 00:00:00 2026 GMT" ;; '
        '*"-checkend 0"*) echo "Certificate will not expire" ;; '
        '*-checkend*) echo "Certificate will expire" ;; esac\n')
    code, lines, notices = run_certificates(tmp_path, mac=397, openssl=stand_in_openssl)

    assert lines == ["The Mac's certificate: expires within 30 days, Nov  1 00:00:00 2026 GMT"]
    assert notices[0].startswith("-|PSells certificate expires soon|")


# The photos -----------------------------------------------------------------------
#
# backup-photos.sh is run here in a copy of the project, with the real tar,
# age and offsite-backup.sh, and a stand-in for docker that archives a folder
# standing in for the photos volume and answers the database's list of photo
# names from a file. No test reaches the real Docker.

PHOTOS_SCRIPT = os.path.join(psells.PROJECT_DIR, "backup-photos.sh")


class PhotoBackup:
    """A copy of the project, a photos volume and a database's photo rows,
    and run() to back them up."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.secret, public = make_key()
        self.project = tmp_path / "psells"
        (self.project / "data").mkdir(parents=True)
        for script in (PHOTOS_SCRIPT, OFFSITE_SCRIPT):
            shutil.copy(script, self.project / os.path.basename(script))
        (self.project / "data" / "backup-recipient.txt").write_text(public)
        self.volume = tmp_path / "volume"
        self.volume.mkdir()
        self.rows = tmp_path / "rows"
        self.rows.write_text("")
        self.archives = tmp_path / "photo-backups"
        self.offsite = tmp_path / "icloud"
        self.calls = tmp_path / "calls"
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        stand_in(self.bin / "docker", f'''echo "$*" >> "{self.calls}"
case "$*" in
  *" exec -T app tar -cf - -C /photos ."*) exec tar -cf - -C "{self.volume}" . ;;
  *" exec -T db sh -c "*) exec cat "{self.rows}" ;;
esac
exit 0
''')
        stand_in(self.bin / "security", f"echo '{self.secret}'\n")

    def photo(self, name, data=b"jpeg bytes", row=True):
        (self.volume / name).write_bytes(data)
        if row:
            self.rows.write_text(self.rows.read_text() + name + "\n")

    def run(self, stamp):
        return subprocess.run(
            ["bash", str(self.project / "backup-photos.sh"), stamp],
            capture_output=True, text=True,
            env=dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                     PSELLS_PHOTO_BACKUP_DIR=str(self.archives),
                     PSELLS_OFFSITE_DIR=str(self.offsite)))

    def kept(self):
        return sorted(p.name for p in self.archives.iterdir())

    def copies(self):
        return sorted(p.name for p in self.offsite.iterdir()) if self.offsite.exists() else []

    def names_in(self, archive):
        listing = subprocess.run(["tar", "-tf", str(archive)], capture_output=True,
                                 text=True, check=True).stdout.split()
        return sorted(name.removeprefix("./") for name in listing
                      if name.endswith(".jpg"))

    def decrypted(self, copy):
        key = self.tmp / "key.txt"
        key.write_text(self.secret + "\n")
        return subprocess.run(["age", "-d", "-i", str(key), str(copy)],
                              capture_output=True, check=True).stdout


@pytest.fixture
def photo_backup(tmp_path):
    return PhotoBackup(tmp_path)


def test_the_photos_are_archived_proved_and_copied_off_the_mac(photo_backup):
    photo_backup.photo("a.jpg")
    photo_backup.photo("b.jpg")

    result = photo_backup.run("2026-10-19_090000")

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(
        "photos-2026-10-19_090000.tar  2 photos, 0 without a row; offsite "
        "photos-2026-10-19_090000.tar.age  ")
    assert photo_backup.kept() == ["photos-2026-10-19_090000.tar"]
    archive = photo_backup.archives / "photos-2026-10-19_090000.tar"
    assert photo_backup.names_in(archive) == ["a.jpg", "b.jpg"]
    (copy,) = photo_backup.copies()
    assert copy == "photos-2026-10-19_090000.tar.age"
    encrypted = (photo_backup.offsite / copy).read_bytes()
    assert encrypted.startswith(b"age-encryption.org/v1\n")
    assert b"jpeg bytes" not in encrypted
    assert photo_backup.decrypted(photo_backup.offsite / copy) == archive.read_bytes()
    assert photo_backup.secret not in result.stdout + result.stderr


def test_unchanged_photos_make_no_new_archive(photo_backup):
    photo_backup.photo("a.jpg")
    photo_backup.run("2026-10-19_090000")

    result = photo_backup.run("2026-10-20_090000")

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "unchanged  1 photos, still in photos-2026-10-19_090000.tar, "
        "0 without a row\n")
    assert photo_backup.kept() == ["photos-2026-10-19_090000.tar"]
    assert photo_backup.copies() == ["photos-2026-10-19_090000.tar.age"]


def test_a_new_photo_makes_a_new_archive(photo_backup):
    photo_backup.photo("a.jpg")
    photo_backup.run("2026-10-19_090000")
    photo_backup.photo("b.jpg")

    result = photo_backup.run("2026-10-20_090000")

    assert result.returncode == 0, result.stderr
    assert photo_backup.kept() == ["photos-2026-10-19_090000.tar",
                                   "photos-2026-10-20_090000.tar"]
    assert photo_backup.names_in(
        photo_backup.archives / "photos-2026-10-20_090000.tar") == ["a.jpg", "b.jpg"]


def test_a_photo_the_database_records_but_the_volume_lacks_fails_it(photo_backup):
    photo_backup.photo("a.jpg")
    photo_backup.rows.write_text("a.jpg\ngone.jpg\n")

    result = photo_backup.run("2026-10-19_090000")

    assert result.returncode == 1
    assert ("1 photos the database records are not in the volume, first "
            "gone.jpg") in result.stderr
    assert photo_backup.kept() == []
    assert photo_backup.copies() == []


def test_a_file_without_a_row_is_counted_and_kept(photo_backup):
    photo_backup.photo("a.jpg")
    photo_backup.photo("spare.jpg", row=False)

    result = photo_backup.run("2026-10-19_090000")

    assert result.returncode == 0, result.stderr
    assert "2 photos, 1 without a row" in result.stdout


def test_old_archives_go_but_the_newest_is_kept_however_old(photo_backup,
                                                            unlistable):
    photo_backup.photo("a.jpg")
    photo_backup.run("2026-08-01_090000")
    for old in (photo_backup.archives / "photos-2026-08-01_090000.tar",
                photo_backup.offsite / "photos-2026-08-01_090000.tar.age"):
        os.utime(old, (0, 0))

    # Unchanged, months later: the one archive is still the newest, and stays.
    assert photo_backup.run("2026-10-19_090000").returncode == 0
    assert photo_backup.kept() == ["photos-2026-08-01_090000.tar"]

    # Changed: a new newest, and the old one, past 30 days, goes, here and in
    # iCloud, which the job may not list.
    photo_backup.photo("b.jpg")
    unlistable(photo_backup.offsite)
    result = photo_backup.run("2026-10-20_090000")
    assert result.returncode == 0, result.stderr
    photo_backup.offsite.chmod(0o755)
    assert photo_backup.kept() == ["photos-2026-10-20_090000.tar"]
    assert photo_backup.copies() == ["photos-2026-10-20_090000.tar.age"]


def test_the_photo_backup_never_rebuilds_stops_or_recreates_anything(photo_backup):
    photo_backup.photo("a.jpg")
    photo_backup.run("2026-10-19_090000")

    calls = photo_backup.calls.read_text().splitlines()
    assert calls[0].endswith(" up -d --wait --no-recreate app")
    for call in calls:
        assert call.startswith(
            f"compose --project-directory {photo_backup.project} "), call
        for word in (" down", " stop", " restart", "--build", " rm ", " run "):
            assert word not in call, (word, call)


def test_a_photos_copy_that_does_not_decrypt_with_the_keychains_key_is_not_kept(
        photo_backup):
    other, _ = make_key()
    stand_in(photo_backup.bin / "security", f"echo '{other}'\n")
    photo_backup.photo("a.jpg")

    result = photo_backup.run("2026-10-19_090000")

    assert result.returncode == 1
    assert "does not decrypt with the Keychain's key" in result.stderr
    assert photo_backup.copies() == []


def test_the_backup_archives_the_photos_after_the_records_copies():
    with open(BACKUP_SCRIPT) as file:
        text = file.read()

    call = 'PHOTOS="$("$SCRIPT_DIR/backup-photos.sh" "$STAMP" 2>&1)"'
    assert call in text
    assert text.index('log "offsite ok  $OFFSITE"') < text.index(call)
    assert '|| fail "the photos: $PHOTOS"' in text
    assert 'log "photos ok  $PHOTOS"' in text
    assert os.access(PHOTOS_SCRIPT, os.X_OK)


def test_a_photos_copy_that_decrypts_to_different_bytes_is_not_kept(photo_backup):
    # The real age, but what it decrypts comes back with one word changed.
    real_age = shutil.which("age")
    stand_in(photo_backup.bin / "age",
             f'case " $* " in *" -d "*) "{real_age}" "$@" | sed s/jpeg/jpeX/ ;;\n'
             f'  *) exec "{real_age}" "$@" ;; esac\n')
    photo_backup.photo("a.jpg")

    result = photo_backup.run("2026-10-19_090000")

    assert result.returncode == 1
    assert "the encrypted copy of photos-2026-10-19_090000.tar does not match" in result.stderr
    assert photo_backup.copies() == []


def test_a_photos_copy_that_failed_is_made_again_the_next_morning(photo_backup):
    other, _ = make_key()
    stand_in(photo_backup.bin / "security", f"echo '{other}'\n")
    photo_backup.photo("a.jpg")
    assert photo_backup.run("2026-10-19_090000").returncode == 1
    assert photo_backup.kept() == []

    stand_in(photo_backup.bin / "security", f"echo '{photo_backup.secret}'\n")
    result = photo_backup.run("2026-10-20_090000")

    assert result.returncode == 0, result.stderr
    assert photo_backup.kept() == ["photos-2026-10-20_090000.tar"]
    assert photo_backup.copies() == ["photos-2026-10-20_090000.tar.age"]


# The demo's end ----------------------------------------------------------------

REMINDER = os.path.join(psells.PROJECT_DIR, "demo-end-reminder.sh")


@pytest.mark.parametrize("today, reminded", [
    ("2027-02-28", False), ("2027-03-01", True), ("2027-03-27", True),
    ("2027-03-28", False), ("2026-10-22", False),
])
def test_the_demos_end_is_announced_through_march_2027(tmp_path, today, reminded):
    project = tmp_path / "psells"
    project.mkdir()
    shutil.copy(REMINDER, project / "demo-end-reminder.sh")
    shown = tmp_path / "shown"
    stand_in(project / "notify.sh", f'echo "$1|$2" >> "{shown}"\n')

    result = subprocess.run(["bash", str(project / "demo-end-reminder.sh")],
                            capture_output=True, text=True,
                            env=dict(os.environ, PSELLS_TODAY=today))

    assert result.returncode == 0, result.stderr
    if reminded:
        assert result.stdout == ("AWS's free plan closes about 2027-03-27. "
                                 "Follow RUNBOOK.md, End the demonstration.\n")
        assert shown.read_text().startswith("PSells demo ends soon|")
    else:
        assert result.stdout == ""
        assert not shown.exists()


def test_the_backup_logs_the_demos_end():
    with open(BACKUP_SCRIPT) as file:
        text = file.read()

    assert 'done < <("$SCRIPT_DIR/demo-end-reminder.sh")' in text
    assert 'log "demo  $line"' in text
    assert os.access(REMINDER, os.X_OK)
