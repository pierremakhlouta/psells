# Kept out of the repository in terraform.tfvars, which is gitignored:
#
#     alert_email = "you@example.com"

variable "alert_email" {
  description = "Where the budget's alerts are sent."
  type        = string
}

variable "acme_staging" {
  description = "Whether a newly built server asks Let's Encrypt's staging service, for trying a rebuild without using the weekly limit."
  type        = bool
  default     = false
}
