# The settings the server's scripts read from Parameter Store. None is secret.
# The database password, /psells/postgres/password, and the monitoring agent's
# token, /psells/grafana/token, are SecureStrings made by hand and deliberately
# not managed here: Terraform would copy their values into the state in plain
# text.

resource "aws_ssm_parameter" "postgres_user" {
  name        = "/psells/postgres/user"
  description = "PSells demo database user"
  type        = "String"
  value       = "psells"
}

resource "aws_ssm_parameter" "postgres_db" {
  name        = "/psells/postgres/db"
  description = "PSells demo database name"
  type        = "String"
  value       = "psells"
}

# Where the monitoring agent sends metrics and logs, from terraform.tfvars.
resource "aws_ssm_parameter" "grafana" {
  for_each = var.grafana

  name        = "/psells/grafana/${each.key}"
  description = "Grafana Cloud ${replace(each.key, "_", " ")} for the PSells demo's monitoring agent"
  type        = "String"
  value       = each.value
}

resource "aws_ssm_parameter" "backup_bucket" {
  name        = "/psells/backup/bucket"
  description = "S3 bucket for the PSells demo's daily backups"
  type        = "String"
  value       = aws_s3_bucket.backups.bucket
}
