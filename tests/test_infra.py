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
    # value into the state in plain text. It may be read only ephemerally,
    # which keeps nothing, for RDS's write-only password.
    for kind in ("resource", "data"):
        for _, _, body in blocks(code, kind):
            assert "/psells/postgres/password" not in body
    assert [name for _, name, body in blocks(code, "ephemeral")
            if "/psells/postgres/password" in body] == ["postgres_password"]
    assert "SecureString" not in code
    # The alert address comes from terraform.tfvars, which git ignores. (An @
    # alone is allowed: GitHub's subject uses it between a name and an ID.)
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", code)
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
    # The server's own security group: what reaches the server at all.
    server = [rule for rule in ingress
              if re.search(r"^\s*security_group_id\s*= aws_security_group\.web\.id$",
                           rule, re.M)]
    from_anywhere = sorted((re.search(r"from_port\s*= (\d+)", rule).group(1),
                            re.search(r"to_port\s*= (\d+)", rule).group(1))
                           for rule in server if '"0.0.0.0/0"' in rule)
    from_elsewhere = [rule for rule in server if '"0.0.0.0/0"' not in rule]

    assert from_anywhere == [("443", "443"), ("80", "80")]
    # The one other way in: the load balancer's listener, from the load
    # balancer's own security group, and only while it exists.
    assert len(from_elsewhere) == 1
    assert "referenced_security_group_id = aws_security_group.lb[0].id" in from_elsewhere[0]
    assert re.search(r"from_port\s*= 8090\b", from_elsewhere[0])
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


def test_the_server_role_may_only_read_three_paths_and_add_backups():
    # The server's role and the backup bucket; the deploy role is in deploy.tf.
    code = without_comments(read(os.path.join(MAIN, "iam.tf"))
                            + read(os.path.join(MAIN, "storage.tf")))
    actions = sorted(re.findall(r'Action\s*= "([^"]+)"', code))

    # The backup bucket's Deny s3:* over plain HTTP, and the role's trust, are
    # the only other actions named.
    assert actions == ["s3:*", "s3:PutObject", "ssm:GetParametersByPath",
                       "sts:AssumeRole"]
    assert '"${aws_s3_bucket.backups.arn}/daily/*"' in code
    paths = re.findall(r'parameter(/psells/[a-z]+)"', code)
    assert paths == ["/psells/postgres", "/psells/backup", "/psells/grafana"]


def test_no_secret_parameter_is_managed_by_terraform():
    # Terraform keeps every value it manages in its state, in plain text. The
    # database password and the monitoring agent's token are made by hand, so
    # no parameter Terraform manages is a SecureString, and the Grafana ones
    # can only be the four fields of the grafana variable.
    code = without_comments("".join(
        read(path) for path in glob.glob(os.path.join(MAIN, "*.tf"))))
    names = re.findall(
        r'resource "aws_ssm_parameter" "\w+" \{[^}]*?name\s*=\s*"([^"]+)"',
        code, re.S)
    grafana = re.search(r'variable "grafana" \{.*?object\(\{(.*?)\}\)',
                        code, re.S).group(1)

    assert "SecureString" not in code
    assert sorted(names) == ["/psells/backup/bucket",
                             "/psells/grafana/${each.key}",
                             "/psells/postgres/db", "/psells/postgres/host",
                             "/psells/postgres/user"]
    assert re.findall(r"(\w+)\s*=\s*string", grafana) == [
        "metrics_url", "metrics_user", "logs_url", "logs_user"]


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
        == sorted(CONFIGURATIONS + [os.path.join(psells.PROJECT_DIR, "infra",
                                                 "grafana")])
    # Formatting checks every configuration under infra/, Grafana's too.
    assert "--workdir /repo/infra " in steps
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


# Deploying from GitHub ---------------------------------------------------------

def deploy_text():
    return without_comments(read(os.path.join(MAIN, "deploy.tf")))


def test_only_main_of_this_repository_can_take_the_deploy_role():
    code = deploy_text()

    assert 'url            = "https://token.actions.githubusercontent.com"' in code
    # GitHub's immutable subject: names and numeric IDs, which a recycled
    # name cannot reproduce.
    assert 'deploy_subject = "repo:pierremakhlouta@238794836/psells@1330163843:ref:refs/heads/main"' in code
    assert '"token.actions.githubusercontent.com:sub" = local.deploy_subject' in code
    assert '"token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"' in code
    # An exact match, never a pattern that other branches or repositories fit.
    assert "StringLike" not in code
    assert "*" not in re.search(r'deploy_subject = "([^"]+)"', code).group(1)


def test_the_deploy_role_can_run_the_deploy_document_and_nothing_else():
    code = deploy_text()
    policy = re.search(r'resource "aws_iam_role_policy" "deploy" \{(.*?)\n\}',
                       code, re.S).group(1)
    actions = sorted(re.findall(r'"(ssm:[A-Za-z]+|ec2:[A-Za-z]+|s3:[A-Za-z*]+|iam:[A-Za-z*]+)"',
                                policy))

    assert actions == ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations",
                       "ssm:SendCommand", "ssm:SendCommand"]
    assert "AWS-RunShellScript" not in code
    # SendCommand is authorised on the document and on the instance, and a
    # condition covers every resource in its statement. So the document is
    # alone in a statement with no condition (it has no tags to match), and
    # the instances are alone in one that requires the psells tag.
    sends = re.findall(r'\{\s*(?:#[^\n]*\n\s*)*Sid\s*=\s*"(\w+)"(.*?)\n      \}',
                       policy, re.S)
    statements = {sid: body for sid, body in sends if "ssm:SendCommand" in body}
    document = statements["SendOnlyTheDeployDocument"]
    instances = statements["SendOnlyToThePsellsServer"]
    assert re.search(r"Resource\s*= aws_ssm_document\.deploy\.arn$", document, re.M)
    assert "Condition" not in document
    assert re.search(r'Resource\s*= "arn:aws:ec2:[^"]+:instance/\*"', instances)
    assert '"ssm:resourceTag/Name" = "psells"' in instances


def test_the_deploy_document_takes_only_a_commit_hash_and_a_digest():
    code = deploy_text()

    assert 'allowedPattern = "^[0-9a-f]{40}$"' in code
    assert 'allowedPattern = "^sha256:[0-9a-f]{64}$"' in code
    assert len(re.findall(r"allowedPattern", code)) == 2
    # Quoted where they reach the shell, and the script stops at an error.
    assert '"set -eu",' in code
    assert "checkout --quiet --detach '{{ commit }}'" in code
    assert "PSELLS_IMAGE_DIGEST='{{ digest }}' /opt/psells/deploy/aws/deploy.sh" in code



# Managed services, behind a switch -------------------------------------------

SWITCHED = ("database.tf", "loadbalancer.tf")


def blocks(text, kind):
    """Each top-level block of that kind, as (type, name, body)."""
    return re.findall(rf'^{kind} "(\w+)" "(\w+)" \{{(.*?)\n\}}', text, re.S | re.M)


def test_everything_that_costs_money_waits_for_the_switch():
    variables = read(os.path.join(MAIN, "variables.tf"))
    assert re.search(r'variable "managed_services" \{[^}]*default\s*= false',
                     variables, re.S)
    for name in SWITCHED:
        code = without_comments(read(os.path.join(MAIN, name)))
        for kind in ("resource", "ephemeral"):
            for resource_type, resource_name, body in blocks(code, kind):
                # The certificate alone is free and kept, so it is validated once.
                if (resource_type, resource_name) == ("aws_acm_certificate", "lb"):
                    continue
                assert re.search(r"^\s*count = var\.managed_services \? 1 : 0$",
                                 body, re.M), (resource_type, resource_name)


def test_rds_is_private_encrypted_and_never_holds_the_password_in_state():
    database = dict(((t, n), b) for t, n, b in blocks(
        without_comments(read(os.path.join(MAIN, "database.tf"))), "resource"))
    db = database[("aws_db_instance", "db")]

    assert re.search(r"publicly_accessible\s*= false", db)
    assert re.search(r"storage_encrypted = true", db)
    assert re.search(r'engine_version = "18\.6"', db)
    # Write-only, from the ephemeral read: never a plain password argument.
    assert re.search(r"password_wo\s*= ephemeral\.aws_ssm_parameter\.postgres_password\[0\]\.value", db)
    assert not re.search(r"^\s*password\s*=", db, re.M)
    # PostgreSQL's port from the server's security group, and nothing else.
    rule = database[("aws_vpc_security_group_ingress_rule", "db_from_server")]
    assert "referenced_security_group_id = aws_security_group.web.id" in rule
    assert "cidr_ipv4" not in rule
    assert [n for t, n in database if t == "aws_vpc_security_group_ingress_rule"] \
        == ["db_from_server"]


def test_the_load_balancer_is_tls_1_3_and_reaches_only_the_server_listener():
    lb = dict(((t, n), b) for t, n, b in blocks(
        without_comments(read(os.path.join(MAIN, "loadbalancer.tf"))), "resource"))

    https = lb[("aws_lb_listener", "https")]
    assert re.search(r'ssl_policy\s*= "ELBSecurityPolicy-TLS13-1-3-', https)
    # A name that is not its own is refused at the load balancer.
    assert 'status_code  = "421"' in https
    assert "values = [local.lb_name]" in lb[("aws_lb_listener_rule", "psells")]
    # The server's 8090 opens to the load balancer only, and the load balancer
    # sends to that port only.
    into_server = lb[("aws_vpc_security_group_ingress_rule", "server_from_lb")]
    assert "referenced_security_group_id = aws_security_group.lb[0].id" in into_server
    assert "from_port                    = 8090" in into_server
    out = lb[("aws_vpc_security_group_egress_rule", "lb_to_server")]
    assert "referenced_security_group_id = aws_security_group.web.id" in out
    assert "from_port                    = 8090" in out
    assert lb[("aws_lb", "lb")].count("drop_invalid_header_fields = true") == 1
    # The health check asks nginx's own path on the listener.
    assert 'path    = "/lb-health"' in lb[("aws_lb_target_group", "server")]


def test_security_group_descriptions_use_only_what_aws_accepts():
    # AWS refuses a security group or rule description with any other
    # character; "nginx's", with its apostrophe, failed a switch-on halfway.
    allowed = re.compile(r"^[A-Za-z0-9. _\-:/()#,@\[\]+=&;{}!$*]*$")
    code = without_comments(main_text())
    for kind in ("aws_security_group", "aws_vpc_security_group_ingress_rule",
                 "aws_vpc_security_group_egress_rule"):
        for body in re.findall(rf'resource "{kind}" "\w+" \{{(.*?)\n\}}', code, re.S):
            for description in re.findall(r'description\s*=\s*"([^"]*)"', body):
                assert allowed.match(description), (kind, description)
