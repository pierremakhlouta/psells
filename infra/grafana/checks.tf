# The demo's login page, checked from outside as a visitor would reach it:
# over HTTPS, with the certificate checked, from three of Grafana's public
# locations every two minutes. Three, so one location's own network trouble
# is never mistaken for the site's; every two minutes, so the three use 64,800
# of the free tier's 100,000 runs a month.
#
# A run passes only on a 200 from /login itself, over TLS. A redirect is not
# followed: the page answers directly, so a redirect would mean something has
# changed. These runs are the availability SLI.

data "grafana_synthetic_monitoring_probes" "public" {
  filter_deprecated = true
}

locals {
  probe_locations = ["Montreal", "NorthVirginia", "London"]
}

resource "grafana_synthetic_monitoring_check" "login" {
  job       = "psells-login"
  target    = "https://psells.lakeshorefreight.me/login"
  enabled   = true
  frequency = 120000
  timeout   = 10000
  probes    = [for name in local.probe_locations : data.grafana_synthetic_monitoring_probes.public.probes[name]]
  labels    = { service = "psells" }

  # Only the metrics the SLO and the dashboard use, and none of Synthetic
  # Monitoring's own alerts: the one alert is in alerting.tf.
  basic_metrics_only = true
  alert_sensitivity  = "none"

  settings {
    http {
      method              = "GET"
      ip_version          = "V4"
      no_follow_redirects = true
      valid_status_codes  = [200]
      fail_if_not_ssl     = true
    }
  }
}
