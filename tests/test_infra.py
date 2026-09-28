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
