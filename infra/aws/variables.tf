# Kept out of the repository in terraform.tfvars, which is gitignored:
#
#     alert_email = "you@example.com"

variable "alert_email" {
  description = "Where the budget's alerts are sent."
  type        = string
}
