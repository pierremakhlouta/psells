"""Tests for deploy/aws/, what runs PSells on the AWS server.

deploy.sh rewrites .env, so what matters most is where it refuses to run: on
the Mac, where .env holds the real database's password, and anywhere but the
server's /opt/psells. Those refusals are tested by running a copy of the
script in a temporary folder, never the real one, with stand-in docker and aws
commands that record being called, so a refusal is shown to happen before
anything is touched.

The rest is read as text: that the server gets the sample configuration, and
that the renewal timer's service agrees with compose.aws.yaml about where it
runs and where the challenge files go.
"""

import configparser
import os
import shutil
import subprocess

import pytest
import yaml

import psells


DEPLOY_DIR = os.path.join(psells.PROJECT_DIR, "deploy", "aws")
SCRIPT = os.path.join(DEPLOY_DIR, "deploy.sh")
SERVICE = os.path.join(DEPLOY_DIR, "psells-certbot-renew.service")
TIMER = os.path.join(DEPLOY_DIR, "psells-certbot-renew.timer")

ORIGINAL_ENV = "POSTGRES_PASSWORD=the-real-one\n"


@pytest.fixture
def project(tmp_path):
    """A stand-in project folder holding a copy of deploy.sh and a .env,
    with docker and aws on the PATH replaced by commands that only record
    that they were called."""
    folder = tmp_path / "psells"
    (folder / "deploy" / "aws").mkdir(parents=True)
    shutil.copy(SCRIPT, folder / "deploy" / "aws" / "deploy.sh")
    (folder / ".env").write_text(ORIGINAL_ENV)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for command in ("docker", "aws", "systemctl"):
        stand_in = bin_dir / command
        stand_in.write_text(f'#!/bin/sh\necho {command} >> "{calls}"\n')
        stand_in.chmod(0o755)
    return folder, bin_dir, calls


def run(folder, bin_dir):
    environment = dict(os.environ,
                       PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return subprocess.run(
        ["bash", str(folder / "deploy" / "aws" / "deploy.sh")],
        capture_output=True, text=True, env=environment)


def test_it_refuses_where_the_real_configuration_is(project):
    folder, bin_dir, calls = project
    (folder / "data").mkdir()
    (folder / "data" / "config.json").write_text("{}")

    result = run(folder, bin_dir)

    assert result.returncode == 1
    assert "data/config.json exists" in result.stderr
    assert (folder / ".env").read_text() == ORIGINAL_ENV
    assert not calls.exists()


def test_it_refuses_anywhere_but_the_servers_project_folder(project):
    folder, bin_dir, calls = project

    result = run(folder, bin_dir)

    assert result.returncode == 1
    assert "/opt/psells" in result.stderr
    assert (folder / ".env").read_text() == ORIGINAL_ENV
    assert not calls.exists()


def test_the_server_gets_the_sample_configuration_only():
    with open(SCRIPT) as script:
        text = script.read()

    # One configuration line in the .env it writes, naming the sample file.
    assert [line for line in text.splitlines()
            if line.startswith("PSELLS_CONFIG_FILE=")] == [
        "PSELLS_CONFIG_FILE=./sample_data/config.json"]
    # And the stack it starts is the server's.
    assert "docker compose -f compose.yaml -f compose.aws.yaml" in text


class ComposeLoader(yaml.SafeLoader):
    """A safe loader that also reads Compose's !override tag, as a list."""


ComposeLoader.add_constructor(
    "!override", lambda loader, node: loader.construct_sequence(node))


def unit(path):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read(path)
    return parser


def test_renewal_runs_where_deploy_puts_the_project_and_as_compose_says():
    service = unit(SERVICE)["Service"]
    with open(os.path.join(psells.PROJECT_DIR, "compose.aws.yaml")) as overlay:
        certbot = yaml.load(overlay, Loader=ComposeLoader)["services"]["certbot"]
    webroot = [volume.split(":")[1] for volume in certbot["volumes"]
               if volume.startswith("./data/acme:")]

    assert service["WorkingDirectory"] == "/opt/psells"
    assert service["Type"] == "oneshot"
    start = service["ExecStart"].split()
    assert start[:8] == ["/usr/bin/docker", "compose", "-f", "compose.yaml",
                         "-f", "compose.aws.yaml", "run", "--rm"]
    assert start[8:10] == ["certbot", "renew"]
    # The webroot certbot writes to is the one nginx serves the challenge from.
    assert start[start.index("--webroot-path") + 1] == webroot[0] == "/var/www/acme"
    assert service["ExecStartPost"].endswith("exec -T proxy nginx -s reload")


def test_renewal_is_tried_twice_a_day_and_survives_the_server_being_off():
    timer = unit(TIMER)

    assert timer["Timer"]["OnCalendar"] == "*-*-* 03,15:00:00"
    assert timer["Timer"]["Persistent"] == "true"
    assert timer["Install"]["WantedBy"] == "timers.target"
