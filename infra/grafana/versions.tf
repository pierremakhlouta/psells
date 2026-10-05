# What watches the PSells demonstration, in its Grafana Cloud stack: the
# checks from outside, the dashboard, the two SLOs and the one alert. Run from
# this folder on the Mac, with the two Grafana tokens read from the Keychain,
# where they are kept, for the length of the command only:
#
#     export AWS_PROFILE=psells
#     GRAFANA_AUTH=$(security find-generic-password -s psells-grafana-terraform -w) \
#     GRAFANA_SM_ACCESS_TOKEN=$(security find-generic-password -s psells-grafana-sm -w) \
#     terraform plan
#
# The state lives beside infra/aws's, in the same bucket under its own key,
# which is why AWS_PROFILE is needed too. No token is written here or kept in
# the state: the provider reads both from the environment.
#
# Not here: the stack itself, its tokens, and what the server sends, which is
# monitoring/config.alloy.

terraform {
  required_version = ">= 1.16.0, < 2.0.0"

  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "4.47.0"
    }
  }

  backend "s3" {
    bucket       = "psells-terraform-state-b9def35c9dea078638fa9a9103"
    key          = "psells/grafana.tfstate"
    region       = "ca-central-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "grafana" {
  url = "https://${var.stack}.grafana.net"
  # The Synthetic Monitoring API for the stack's region, prod-ca-east-0.
  sm_url = "https://synthetic-monitoring-api-ca-east-0.grafana.net"
}
