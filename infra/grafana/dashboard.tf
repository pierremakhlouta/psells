# The dashboard, kept as JSON in monitoring/dashboards/. It names its data
# sources by placeholder, filled here with the stack's own, so the file holds
# nothing particular to one stack. Edits made in Grafana's UI are replaced by
# the next apply: the file is the dashboard.

data "grafana_data_source" "logs" {
  name = "grafanacloud-${var.stack}-logs"
}

resource "grafana_dashboard" "demo" {
  folder = grafana_folder.psells.uid
  config_json = replace(replace(
    file("${path.module}/../../monitoring/dashboards/psells-demo.json"),
    "__METRICS_UID__", data.grafana_data_source.metrics.uid),
  "__LOGS_UID__", data.grafana_data_source.logs.uid)
  overwrite = true
}
