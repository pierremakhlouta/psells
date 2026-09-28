# Kept out of the repository in terraform.tfvars, which is gitignored:
#
#     alert_email = "you@example.com"

variable "alert_email" {
  description = "Where the budget's alerts are sent."
  type        = string
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
