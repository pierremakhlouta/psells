# Kept out of the repository in terraform.tfvars, which is gitignored:
#
#     stack       = "your-stack"
#     alert_email = "you@example.com"

variable "stack" {
  description = "The Grafana Cloud stack's name, as in https://<stack>.grafana.net."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.stack))
    error_message = "The stack name is lower-case letters, digits and dashes."
  }
}

variable "alert_email" {
  description = "Where the site-down alert is sent."
  type        = string
}
