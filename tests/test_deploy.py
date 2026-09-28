"""Tests for deploy/aws/, what runs PSells on the AWS server.

deploy.sh rewrites .env, so what matters most is where it refuses to run: on
the Mac, where .env holds the real database's password, and anywhere but the
server's /opt/psells. backup-to-s3.sh must refuse on the Mac too, or the real
records could be copied to S3. Those refusals are tested by running a copy of the
script in a temporary folder, never the real one, with stand-in docker and aws
commands that record being called, so a refusal is shown to happen before
anything is touched.

The rest is read as text: that the server gets the sample configuration, and
that the renewal timer's service agrees with compose.aws.yaml about where it
runs and where the challenge files go.
"""

import configparser
import os
import re
import shutil
import subprocess

import pytest
import yaml

import psells


DEPLOY_DIR = os.path.join(psells.PROJECT_DIR, "deploy", "aws")
SCRIPT = os.path.join(DEPLOY_DIR, "deploy.sh")
BACKUP = os.path.join(DEPLOY_DIR, "backup-to-s3.sh")
SERVICE = os.path.join(DEPLOY_DIR, "psells-certbot-renew.service")
TIMER = os.path.join(DEPLOY_DIR, "psells-certbot-renew.timer")
BACKUP_SERVICE = os.path.join(DEPLOY_DIR, "psells-backup.service")
BACKUP_TIMER = os.path.join(DEPLOY_DIR, "psells-backup.timer")

ORIGINAL_ENV = "POSTGRES_PASSWORD=the-real-one\n"


@pytest.fixture
def project(tmp_path):
    """A stand-in project folder holding a copy of deploy.sh and a .env,
    with docker and aws on the PATH replaced by commands that only record
    that they were called."""
    folder = tmp_path / "psells"
    (folder / "deploy" / "aws").mkdir(parents=True)
    shutil.copy(SCRIPT, folder / "deploy" / "aws" / "deploy.sh")
    shutil.copy(BACKUP, folder / "deploy" / "aws" / "backup-to-s3.sh")
    (folder / ".env").write_text(ORIGINAL_ENV)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for command in ("docker", "aws", "systemctl"):
        stand_in = bin_dir / command
        stand_in.write_text(f'#!/bin/sh\necho {command} >> "{calls}"\n')
        stand_in.chmod(0o755)
    return folder, bin_dir, calls


def run(folder, bin_dir, script="deploy.sh"):
    environment = dict(os.environ,
                       PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return subprocess.run(
        ["bash", str(folder / "deploy" / "aws" / script)],
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


# The daily backup to S3 ------------------------------------------------------

def test_the_backup_refuses_where_the_real_records_are(project):
    folder, bin_dir, calls = project
    (folder / "data").mkdir()
    (folder / "data" / "config.json").write_text("{}")

    result = run(folder, bin_dir, "backup-to-s3.sh")

    assert result.returncode == 1
    assert "the real data never leaves the Mac" in result.stderr
    # Refused before docker or aws is ever called: nothing dumped, nothing sent.
    assert not calls.exists()


def test_the_backup_is_proved_before_it_is_sent_and_only_under_daily():
    with open(BACKUP) as script:
        text = script.read()

    # The one copy to S3 comes after the restore check and the counts.
    copies = [line for line in text.splitlines() if "aws s3 cp" in line]
    assert len(copies) == 1
    assert text.index("aws s3 cp") > text.index("pg_restore")
    assert text.index("aws s3 cp") > text.index('[ "$RESTORED" = "$LIVE" ]')
    assert '"s3://$bucket/daily/$NAME"' in text


def test_the_backup_runs_daily_from_where_deploy_puts_it():
    service = unit(BACKUP_SERVICE)["Service"]
    timer = unit(BACKUP_TIMER)

    assert service["Type"] == "oneshot"
    assert service["ExecStart"] == "/opt/psells/deploy/aws/backup-to-s3.sh"
    assert os.access(BACKUP, os.X_OK)
    assert timer["Timer"]["OnCalendar"] == "*-*-* 08:00:00"
    assert timer["Timer"]["Persistent"] == "true"
    assert timer["Install"]["WantedBy"] == "timers.target"


def test_deploy_installs_and_enables_every_unit_in_the_folder():
    with open(SCRIPT) as script:
        text = script.read()
    units = sorted(name for name in os.listdir(DEPLOY_DIR)
                   if name.endswith((".service", ".timer")))
    install = text[text.index("install -m 644"):text.index("/etc/systemd/system/")]
    enable = [line for line in text.splitlines()
              if line.startswith("systemctl enable --now")]

    assert units == ["psells-backup.service", "psells-backup.timer",
                     "psells-certbot-renew.service", "psells-certbot-renew.timer"]
    for name in units:
        assert f"deploy/aws/{name}" in install, name
    assert len(enable) == 1
    assert set(enable[0].split()[3:]) == {
        name for name in units if name.endswith(".timer")}


# A server that sets itself up ------------------------------------------------

FIRST_BOOT = os.path.join(DEPLOY_DIR, "first-boot.sh")


def test_deploy_reads_the_certificates_name_from_the_file_nginx_reads():
    with open(SCRIPT) as script:
        line = [line for line in script.read().splitlines()
                if line.startswith("NAME=$(")][0]
    with open(os.path.join(psells.PROJECT_DIR, "nginx", "sites", "aws",
                           "https.conf")) as site:
        served = re.search(r"^server_name (\S+);$", site.read(), re.M).group(1)

    # Run the script's own line against the real file.
    found = subprocess.run(["bash", "-c", f'{line}; echo "$NAME"'],
                           cwd=psells.PROJECT_DIR, capture_output=True,
                           text=True).stdout.strip()

    assert found == served == "psells.lakeshorefreight.me"


def test_a_certificate_is_fetched_only_when_missing_and_before_the_stack():
    with open(SCRIPT) as script:
        text = script.read()
    fetch = text.index("certonly --standalone")

    # Only when none exists, so a redeploy never asks Let's Encrypt again.
    assert re.search(r'if \[ -e "data/letsencrypt/live/\$NAME/fullchain.pem" \]',
                     text)
    # Before nginx holds port 80, then renewals switched to nginx's webroot.
    assert fetch < text.index("compose up -d --build --wait") \
        < text.index("reconfigure")
    # Through the pinned certbot service, as nginx's user, into its folders.
    assert "compose run --rm -p 80:80 certbot certonly" in text
    assert "install -d -o 101 -g 101 -m 700 data/letsencrypt" in text
    # Staging only when asked for.
    assert '[ "${PSELLS_ACME_STAGING:-0}" = 1 ] && staging=(--staging)' in text


def test_first_boot_prepares_the_host_then_deploys_the_public_repository():
    with open(FIRST_BOOT) as script:
        text = script.read()

    assert os.access(FIRST_BOOT, os.X_OK)
    assert text.startswith("#!/bin/bash\n")
    assert "REPOSITORY=https://github.com/pierremakhlouta/psells.git" in text
    assert "PROJECT_DIR=/opt/psells" in text
    # Every host step comes before the deploy, and the deploy is last.
    for step in ("fallocate -l 2G /swapfile", "docker-compose-plugin",
                 "snap install aws-cli", "git clone"):
        assert text.index(step) < text.index('"$PROJECT_DIR/deploy/aws/deploy.sh"'), step
    assert text.rstrip().endswith('"$PROJECT_DIR/deploy/aws/deploy.sh"')
