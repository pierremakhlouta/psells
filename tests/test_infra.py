"""Tests for infra/aws/, the Terraform that describes the AWS server.

Terraform's state holds every value of every resource in plain text, so what
matters first is that no state file can be committed. Then the pins: every
configuration names the AWS provider at one exact version, the lock file
records that same version, and the state bucket cannot be destroyed by
accident, since losing it loses the record of everything else.

The configurations are read as text rather than parsed as HCL, which would
need a package for this one purpose; the patterns are anchored to whole
lines.
"""

import glob
import os
import re
import subprocess

import pytest
import yaml

import psells


INFRA_DIR = os.path.join(psells.PROJECT_DIR, "infra", "aws")
CONFIGURATIONS = sorted({os.path.dirname(path) for path in glob.glob(
    os.path.join(INFRA_DIR, "**", "*.tf"), recursive=True)})
BOOTSTRAP = os.path.join(INFRA_DIR, "bootstrap", "main.tf")

PROVIDER_PIN = re.compile(
    r'^\s*aws = \{\s*source\s*= "hashicorp/aws"\s*version\s*= "([^"]+)"',
    re.M)
LOCKED = re.compile(
    r'^provider "registry.terraform.io/hashicorp/aws" \{\s*version\s*= "([^"]+)"',
    re.M)


def read(path):
    with open(path) as source:
        return source.read()


def ignored(path):
    """Whether git ignores this path, relative to the project."""
    return subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=psells.PROJECT_DIR).returncode == 0


def test_there_is_terraform_to_check():
    assert os.path.join(INFRA_DIR, "bootstrap") in CONFIGURATIONS


@pytest.mark.parametrize("name", [
    "terraform.tfstate", "terraform.tfstate.backup", ".terraform/providers",
    "plan.tfplan"])
def test_no_state_or_working_file_can_be_committed(name):
    for configuration in CONFIGURATIONS:
        relative = os.path.relpath(os.path.join(configuration, name),
                                   psells.PROJECT_DIR)
        assert ignored(relative), relative


def test_the_lock_file_is_committed():
    for configuration in CONFIGURATIONS:
        lock = os.path.relpath(os.path.join(configuration, ".terraform.lock.hcl"),
                               psells.PROJECT_DIR)
        assert os.path.exists(os.path.join(psells.PROJECT_DIR, lock)), lock
        assert not ignored(lock), lock


def test_every_configuration_pins_one_exact_aws_provider_and_locks_it():
    versions = set()
    for configuration in CONFIGURATIONS:
        text = "".join(read(path) for path in
                       glob.glob(os.path.join(configuration, "*.tf")))
        pinned = PROVIDER_PIN.findall(text)
        locked = LOCKED.findall(read(os.path.join(configuration,
                                                  ".terraform.lock.hcl")))

        # One exact version, not a range a later init could move within.
        assert len(pinned) == 1 and re.fullmatch(r"\d+\.\d+\.\d+", pinned[0]), (
            configuration, pinned)
        assert locked == pinned, (configuration, locked, pinned)
        versions.add(pinned[0])

    assert len(versions) == 1, versions


def test_the_state_bucket_cannot_be_destroyed_by_accident_and_keeps_versions():
    text = read(BOOTSTRAP)

    assert re.search(r"^\s*prevent_destroy = true$", text, re.M)
    assert re.search(r'^\s*status = "Enabled"$', text, re.M)
    for setting in ("block_public_acls", "ignore_public_acls",
                    "block_public_policy", "restrict_public_buckets"):
        assert re.search(rf"^\s*{setting}\s*= true$", text, re.M), setting
    assert '"aws:SecureTransport" = "false"' in text


# The server's configuration ---------------------------------------------------

MAIN = os.path.join(INFRA_DIR)


def main_text():
    """Every .tf file of infra/aws/ itself, joined."""
    return "".join(read(path) for path in
                   sorted(glob.glob(os.path.join(MAIN, "*.tf"))))


def without_comments(text):
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def test_the_state_is_kept_in_s3_encrypted_and_locked():
    text = main_text()

    assert re.search(r'^\s*backend "s3" \{', text, re.M)
    assert re.search(r'^\s*bucket\s*= "psells-terraform-state-[0-9a-f]+"$', text, re.M)
    assert re.search(r"^\s*encrypt\s*= true$", text, re.M)
    assert re.search(r"^\s*use_lockfile\s*= true$", text, re.M)


def test_no_secret_and_no_personal_value_is_in_the_configuration():
    code = without_comments(main_text())

    # The database password is made by hand; managing it here would copy its
    # value into the state in plain text.
    assert "/psells/postgres/password" not in code
    assert "SecureString" not in code
    # The alert address comes from terraform.tfvars, which git ignores.
    assert "@" not in code
    assert ignored("infra/aws/terraform.tfvars")
    # No import block, and no account number or resource id written in.
    assert not re.search(r"^\s*import \{", code, re.M)
    assert not re.search(r"\b\d{12}\b", code)
    assert not re.search(r"\b(i|sg|sgr|eipalloc|eipassoc|vol)-[0-9a-f]{8,}\b", code)


def test_the_firewall_lets_in_http_and_https_and_nothing_else():
    code = without_comments(main_text())
    ingress = re.findall(
        r'resource "aws_vpc_security_group_ingress_rule" "\w+" \{(.*?)\n\}',
        code, re.S)
    ports = sorted((re.search(r"from_port\s*= (\d+)", rule).group(1),
                    re.search(r"to_port\s*= (\d+)", rule).group(1))
                   for rule in ingress)

    assert ports == [("443", "443"), ("80", "80")]
    # Inline rules on the group itself would slip past the check above.
    assert not re.search(r"^\s*ingress \{", code, re.M)


def test_the_server_has_no_key_imdsv2_only_and_cannot_burst_into_a_bill():
    server = re.search(r'resource "aws_instance" "server" \{(.*?)\n\}',
                       without_comments(main_text()), re.S).group(1)

    assert "key_name" not in server
    assert re.search(r'http_tokens\s*= "required"', server)
    assert re.search(r"http_put_response_hop_limit = 1\b", server)
    assert re.search(r'cpu_credits = "standard"', server)
    assert re.search(r"encrypted\s*= true", server)


def test_the_server_role_may_only_read_two_paths_and_add_backups():
    code = without_comments(main_text())
    actions = sorted(re.findall(r'Action\s*= "([^"]+)"', code))

    # The backup bucket's Deny s3:* over plain HTTP, and the role's trust, are
    # the only other actions named.
    assert actions == ["s3:*", "s3:PutObject", "ssm:GetParametersByPath",
                       "sts:AssumeRole"]
    assert '"${aws_s3_bucket.backups.arn}/daily/*"' in code
    assert re.search(r"parameter/psells/postgres\",", code)
    assert re.search(r"parameter/psells/backup\",", code)


# Checked on every push ---------------------------------------------------------

def test_ci_formats_and_validates_every_configuration_with_the_pinned_release():
    with open(os.path.join(psells.PROJECT_DIR, ".github", "workflows",
                           "lint.yml")) as workflow:
        job = yaml.safe_load(workflow)["jobs"]["terraform"]
    image = job["env"]["TERRAFORM_IMAGE"]
    steps = "\n".join(step.get("run", "") for step in job["steps"])
    validated = re.search(r"for dir in ([^;]+);", steps).group(1).split()

    # Pinned by digest, and a release every required_version allows.
    assert re.fullmatch(r"hashicorp/terraform:1\.(\d+)\.\d+@sha256:[0-9a-f]{64}",
                        image)
    assert int(re.match(r"hashicorp/terraform:1\.(\d+)", image).group(1)) >= 16
    assert "fmt -check -recursive" in steps
    # Every configuration, without touching AWS, holding to the lock file.
    assert sorted(os.path.join(psells.PROJECT_DIR, d) for d in validated) \
        == CONFIGURATIONS
    assert "-backend=false" in steps
    assert "-lockfile=readonly" in steps


def test_a_new_server_sets_itself_up_and_a_running_one_is_left_alone():
    server = re.search(r'resource "aws_instance" "server" \{(.*?)\n\}',
                       without_comments(main_text()), re.S).group(1)
    variables = read(os.path.join(MAIN, "variables.tf"))

    assert 'file("${path.module}/../../deploy/aws/first-boot.sh")' in server
    assert re.search(r"ignore_changes = \[ami, user_data\]", server)
    # The real Let's Encrypt service unless a trial rebuild asks otherwise.
    assert re.search(r'variable "acme_staging" \{[^}]*default\s*= false', variables,
                     re.S)
