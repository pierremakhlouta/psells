# The one alert: the site is down. It pages on what a visitor feels, not on a
# cause such as memory, and by email to the address in terraform.tfvars.
#
# Evaluated every minute over the last five: the share of all checks that
# passed. Under half means most locations are failing, not one location's own
# network; held for two minutes before it fires, so a single bad run never
# pages. A real outage is noticed in about seven minutes. If the checks stop
# reporting at all, that alerts too: silence is not health. It resolves itself
# when the checks pass again, and the resolution is mailed as well.

resource "grafana_contact_point" "email" {
  name = "PSells email"

  email {
    addresses               = [var.alert_email]
    single_email            = true
    disable_resolve_message = false
  }
}

# Every alert in the stack goes to that address. This replaces the stack's
# default routing; there is nothing else in the stack to route.
resource "grafana_notification_policy" "root" {
  contact_point   = grafana_contact_point.email.name
  group_by        = ["alertname"]
  group_wait      = "30s"
  group_interval  = "5m"
  repeat_interval = "4h"
}

resource "grafana_rule_group" "site" {
  name             = "PSells site"
  folder_uid       = grafana_folder.psells.uid
  interval_seconds = 60

  rule {
    name           = "PSells site down"
    condition      = "B"
    for            = "2m"
    no_data_state  = "Alerting"
    exec_err_state = "Alerting"

    labels = { service = "psells", severity = "page" }
    annotations = {
      summary     = "The PSells demo's login page is failing outside checks from most locations."
      description = "Under half of the checks of https://psells.lakeshorefreight.me/login passed in the last five minutes. Start with the dashboard's checks and nginx's 5xx lines."
    }

    data {
      ref_id         = "A"
      datasource_uid = data.grafana_data_source.metrics.uid
      relative_time_range {
        from = 600
        to   = 0
      }
      model = jsonencode({
        refId   = "A"
        expr    = "sum(rate(probe_all_success_sum{job=\"psells-login\"}[5m])) / sum(rate(probe_all_success_count{job=\"psells-login\"}[5m]))"
        instant = true
      })
    }

    data {
      ref_id         = "B"
      datasource_uid = "__expr__"
      relative_time_range {
        from = 0
        to   = 0
      }
      model = jsonencode({
        refId      = "B"
        type       = "threshold"
        expression = "A"
        conditions = [{ evaluator = { type = "lt", params = [0.5] } }]
      })
    }
  }
}
