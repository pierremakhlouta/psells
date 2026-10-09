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


def run_start(tmp_path, real_stack=True, docker_up=True):
    """start-stack.sh in a copy of the project; returns (exit code, the
    docker calls it made, its log)."""
    project = tmp_path / "psells"
    project.mkdir()
    shutil.copy(START_SCRIPT, project / "start-stack.sh")
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


def run_refresh(tmp_path, real_stack=True, db_health="healthy", etl_ok=True):
    """refresh-analytics.sh in a copy of the project; returns (exit code, the
    docker calls it made, its log)."""
    project = tmp_path / "psells"
    project.mkdir()
    shutil.copy(REFRESH_SCRIPT, project / "refresh-analytics.sh")
    if real_stack:
        (project / "data").mkdir()
        (project / "data" / "config.json").write_text("{}")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
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


def test_only_its_own_month_old_copies_are_removed(tmp_path):
    result, _, _, offsite = run_offsite(tmp_path, old_copy=True)

    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in offsite.iterdir()) == [
        "notes.txt", "psells-2026-10-09_090000.tar.age"]


def test_the_backup_sends_the_copy_only_after_the_dump_is_proved():
    with open(BACKUP_SCRIPT) as file:
        text = file.read()

    call = '"$SCRIPT_DIR/offsite-backup.sh" "psells-$STAMP.dump" "config-$STAMP.json"'
    assert call in text
    assert text.index('mv "$PARTIAL" "$TARGET"') < text.index(call)
    assert text.index('log "ok  psells-$STAMP.dump') < text.index(call)
    assert '|| fail "the off-Mac copy: $OFFSITE"' in text
    assert os.access(OFFSITE_SCRIPT, os.X_OK)
