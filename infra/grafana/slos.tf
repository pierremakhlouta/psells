# The two service level objectives, over a rolling seven days. Grafana's SLO
# app keeps the error budget and its burn for each; neither alerts, because
# the one alert is the site being down (alerting.tf).

data "grafana_data_source" "metrics" {
  name = "grafanacloud-${var.stack}-prom"
}

resource "grafana_folder" "psells" {
  title = "PSells"
}

# Availability, from outside: the share of checks of /login that passed.
resource "grafana_slo" "availability" {
  name        = "PSells login page available"
  description = "Share of outside checks of the demo's login page answered 200 over trusted HTTPS, from three locations every two minutes."
  folder_uid  = grafana_folder.psells.uid

  query {
    type = "ratio"
    ratio {
      success_metric        = "probe_all_success_sum{job=\"psells-login\"}"
      total_metric          = "probe_all_success_count{job=\"psells-login\"}"
      source_datasource_uid = data.grafana_data_source.metrics.uid
    }
  }

  objectives {
    value  = 0.995
    window = "7d"
  }

  destination_datasource {
    uid = data.grafana_data_source.metrics.uid
  }

  label {
    key   = "service"
    value = "psells"
  }
}

# Latency, from inside: the share of requests nginx answered in under 500 ms,
# from the histogram the server's agent builds from nginx's request_time.
resource "grafana_slo" "latency" {
  name        = "PSells requests under 500 ms"
  description = "Share of requests nginx answered in under 500 ms, from its request_time, every request counted."
  folder_uid  = grafana_folder.psells.uid

  query {
    type = "ratio"
    ratio {
      success_metric        = "loki_process_custom_nginx_request_seconds_bucket{server=\"psells-demo\",le=\"0.5\"}"
      total_metric          = "loki_process_custom_nginx_request_seconds_count{server=\"psells-demo\"}"
      source_datasource_uid = data.grafana_data_source.metrics.uid
    }
  }

  objectives {
    value  = 0.99
    window = "7d"
  }

  destination_datasource {
    uid = data.grafana_data_source.metrics.uid
  }

  label {
    key   = "service"
    value = "psells"
  }
}
