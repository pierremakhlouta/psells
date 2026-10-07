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
