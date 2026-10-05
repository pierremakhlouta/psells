"""Tests for infra/grafana, the configuration that watches the AWS demo.

Read as text, as test_infra.py reads infra/aws, so they need neither Grafana
nor a token. They hold the checks, the SLOs, the one alert and the dashboard
to what was decided in Phase 10, and keep every token and every identifier of
the stack out of the repository.
"""

import glob
import json
import os
import re
import subprocess

import psells


GRAFANA_DIR = os.path.join(psells.PROJECT_DIR, "infra", "grafana")
DASHBOARD = os.path.join(psells.PROJECT_DIR, "monitoring", "dashboards",
                         "psells-demo.json")

# A month of minutes, and the free tier's runs a month.
MINUTES_A_MONTH = 30 * 24 * 60
FREE_CHECK_RUNS = 100_000


def read(path):
    with open(path) as file:
        return file.read()


def code():
    """Every .tf file in infra/grafana, comments removed."""
    text = "".join(read(path) for path in
                   sorted(glob.glob(os.path.join(GRAFANA_DIR, "*.tf"))))
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def block(text, kind, name):
    """The body of one top-level block, up to the matching closing brace."""
    start = text.index(f'{kind} "{name}"')
    depth, i = 0, text.index("{", start)
    for j in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if depth == 0:
            return text[i:j + 1]
    raise AssertionError(f"{kind} {name} does not close")


def ignored(path):
    return subprocess.run(["git", "check-ignore", "-q", path],
                          cwd=psells.PROJECT_DIR).returncode == 0


# The configuration -----------------------------------------------------------

def test_one_exact_grafana_provider_locked_for_every_platform():
    pinned = re.findall(
        r'grafana = \{\s*source\s*= "grafana/grafana"\s*version\s*= "([^"]+)"',
        code())
    lock = read(os.path.join(GRAFANA_DIR, ".terraform.lock.hcl"))
    locked = re.findall(
        r'provider "registry.terraform.io/grafana/grafana" \{\s*version\s*= "([^"]+)"',
        lock)

    assert len(pinned) == 1 and re.fullmatch(r"\d+\.\d+\.\d+", pinned[0])
    assert locked == pinned
    # CI validates on Linux with the lock file read-only, and the Mac runs it.
    assert len(re.findall(r'"h1:', lock)) >= 3
    assert not ignored("infra/grafana/.terraform.lock.hcl")


def test_the_state_sits_beside_the_aws_state_under_its_own_key():
    text = code()
    aws = read(os.path.join(psells.PROJECT_DIR, "infra", "aws",
                            "versions.tf"))
    bucket = re.search(r'bucket\s*= "([^"]+)"', aws).group(1)

    assert f'bucket       = "{bucket}"' in text
    assert re.search(r'key\s*= "psells/grafana\.tfstate"', text)
    assert re.search(r"encrypt\s*= true", text)
    assert re.search(r"use_lockfile\s*= true", text)


def test_no_token_and_no_identifier_of_the_stack_is_in_the_repository():
    text = code()
    dashboard = read(DASHBOARD)

    # Both tokens come from the environment, read from the Keychain.
    assert not re.search(r"^\s*(auth|sm_access_token)\s*=", text, re.M)
    for everything in (text, dashboard):
        assert not re.search(r"\bgl(c|sa)_", everything)
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", everything)
        # The stack's name and address are in terraform.tfvars only.
        assert not re.search(r"https://[a-z0-9-]+\.grafana\.net", everything
                             .replace("https://${var.stack}.grafana.net", "")
                             .replace("synthetic-monitoring-api-ca-east-0", ""))
    assert ignored("infra/grafana/terraform.tfvars")
    for state in ("terraform.tfstate", ".terraform/x"):
        assert ignored(f"infra/grafana/{state}")


# The checks ------------------------------------------------------------------

def test_the_login_page_is_checked_from_three_places_over_https_with_its_certificate():
    check = block(code(), "resource", "grafana_synthetic_monitoring_check")
    locations = re.search(r"probe_locations = \[([^\]]*)\]", code()).group(1)

    assert 'target    = "https://psells.lakeshorefreight.me/login"' in check
    assert re.findall(r'"(\w+)"', locations) == ["Montreal", "NorthVirginia",
                                                 "London"]
    assert "valid_status_codes  = [200]" in check
    assert "no_follow_redirects = true" in check
    assert "fail_if_not_ssl     = true" in check
    # No skipping the certificate check.
    assert "insecure_skip_verify" not in check
    # Synthetic Monitoring's own alerts are off: there is one alert.
    assert 'alert_sensitivity  = "none"' in check


def test_the_checks_fit_the_free_tier():
    check = block(code(), "resource", "grafana_synthetic_monitoring_check")
    frequency_ms = int(re.search(r"frequency = (\d+)", check).group(1))
    locations = len(re.findall(r'"\w+"', re.search(
        r"probe_locations = \[([^\]]*)\]", code()).group(1)))

    runs = locations * MINUTES_A_MONTH * 60_000 / frequency_ms
    assert runs <= 0.7 * FREE_CHECK_RUNS, runs


# The SLOs ----------------------------------------------------------------------

def test_the_two_slos_are_the_ones_decided():
    availability = block(code(), "resource", "grafana_slo")
    latency = code()[code().index('resource "grafana_slo" "latency"'):]

    assert 'success_metric        = "probe_all_success_sum{job=\\"psells-login\\"}"' in availability
    assert 'total_metric          = "probe_all_success_count{job=\\"psells-login\\"}"' in availability
    assert re.search(r"value\s*= 0\.995\s*window\s*= \"7d\"", availability)
    assert 'le=\\"0.5\\"' in latency
    assert "loki_process_custom_nginx_request_seconds_count" in latency
    assert re.search(r"value\s*= 0\.99\s*window\s*= \"7d\"", latency)
    # Neither SLO alerts; the one alert is the site down.
    assert "alerting {" not in code()


def test_the_latency_slo_reads_what_the_agent_sends():
    config = read(os.path.join(psells.PROJECT_DIR, "monitoring",
                               "config.alloy"))

    # loki.process names its metrics loki_process_custom_<name>, and 0.5 must
    # be one of the histogram's buckets for the SLO to have anything to count.
    assert 'name              = "nginx_request_seconds"' in config
    buckets = re.search(r"buckets\s*= \[([^\]]*)\]", config).group(1)
    assert "0.5" in [b.strip() for b in buckets.split(",")]


# The alert -----------------------------------------------------------------------

def test_there_is_one_alert_and_it_is_the_site_being_down():
    text = code()
    rules = re.findall(r"^\s*rule \{", text, re.M)
    group = block(text, "resource", "grafana_rule_group")

    assert len(rules) == 1
    assert 'probe_all_success_sum{job=\\"psells-login\\"}' in group
    assert "[5m]" in group
    assert re.search(r'type = "lt", params = \[0\.5\]', group)
    assert 'for            = "2m"' in group
    # Silence is not health: no data alerts too.
    assert 'no_data_state  = "Alerting"' in group
    assert 'exec_err_state = "Alerting"' in group


def test_every_alert_goes_to_the_email_address_in_tfvars():
    contact = block(code(), "resource", "grafana_contact_point")
    policy = block(code(), "resource", "grafana_notification_policy")

    assert "addresses               = [var.alert_email]" in contact
    assert "disable_resolve_message = false" in contact
    assert "contact_point   = grafana_contact_point.email.name" in policy


# The dashboard ---------------------------------------------------------------------

def dashboard_panels():
    with open(DASHBOARD) as file:
        return json.load(file)


def test_the_dashboard_names_its_data_sources_only_by_placeholder():
    dashboard = dashboard_panels()
    sources = set()
    for panel in dashboard["panels"]:
        for item in [panel] + panel.get("targets", []):
            if "datasource" in item:
                sources.add(item["datasource"]["uid"])

    assert sources == {"__METRICS_UID__", "__LOGS_UID__"}
    assert dashboard["uid"] == "psells-demo"
    # The file is the dashboard: an edit in the UI would be lost.
    assert dashboard["editable"] is False


def test_the_dashboard_shows_both_slos_the_checks_the_server_and_the_log():
    dashboard = dashboard_panels()
    rows = [panel["title"] for panel in dashboard["panels"]
            if panel["type"] == "row"]
    queries = " ".join(target.get("expr", "") for panel in dashboard["panels"]
                       for target in panel.get("targets", []))

    assert len(rows) == 5
    for needed in ("probe_all_success_sum", "nginx_request_seconds_bucket",
                   "nginx_requests_total", "node_memory_MemAvailable_bytes",
                   "node_filesystem_avail_bytes", '{job="nginx"}'):
        assert needed in queries, needed


def test_the_dashboard_file_is_the_one_terraform_applies():
    dashboard = block(code(), "resource", "grafana_dashboard")

    assert "monitoring/dashboards/psells-demo.json" in dashboard
    assert '"__METRICS_UID__", data.grafana_data_source.metrics.uid' in dashboard
    assert '"__LOGS_UID__", data.grafana_data_source.logs.uid' in dashboard
