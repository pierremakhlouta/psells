# Kept out of the repository in terraform.tfvars, which is gitignored:
#
#     alert_email = "you@example.com"
#     grafana = {
#       metrics_url  = "https://prometheus-....grafana.net/api/prom/push"
#       metrics_user = "1234567"
#       logs_url     = "https://logs-prod-....grafana.net/loki/api/v1/push"
#       logs_user    = "1234567"
#     }

variable "alert_email" {
  description = "Where the budget's alerts are sent."
  type        = string
}

# Where the server's monitoring agent sends metrics and logs: the Grafana Cloud
# stack's Prometheus and Loki push addresses and their user numbers. Not
# secrets, since nothing can be written with them alone, but the stack's own
# identifiers, so kept out of the public repository like the alert address.
# The token that goes with them is not here; see parameters.tf.
variable "grafana" {
  description = "Grafana Cloud push addresses and user numbers for the server's monitoring agent."
  type = object({
    metrics_url  = string
    metrics_user = string
    logs_url     = string
    logs_user    = string
  })

  validation {
    condition = (
      can(regex("^https://[a-z0-9.-]+\\.grafana\\.net/api/prom/push$", var.grafana.metrics_url))
      && can(regex("^https://[a-z0-9.-]+\\.grafana\\.net/loki/api/v1/push$", var.grafana.logs_url))
      && can(regex("^[0-9]+$", var.grafana.metrics_user))
      && can(regex("^[0-9]+$", var.grafana.logs_user))
    )
    error_message = "grafana needs the two https push addresses at grafana.net and two numeric user ids."
  }
}

variable "managed_services" {
  description = "Whether RDS and the load balancer exist. They cost about USD 2 a day, which would end the free AWS window early, so they are switched on only while they are being built, proved or shown, and off again with one apply."
  type        = bool
  default     = false
}

variable "acme_staging" {
  description = "Whether a newly built server asks Let's Encrypt's staging service, for trying a rebuild without using the weekly limit."
  type        = bool
  default     = false
}
