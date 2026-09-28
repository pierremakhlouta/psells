# The settings the server's scripts read from Parameter Store. None is secret.
# The database password, /psells/postgres/password, is a SecureString made by
# hand and deliberately not managed here: Terraform would copy its value into
# the state in plain text.

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

resource "aws_ssm_parameter" "backup_bucket" {
  name        = "/psells/backup/bucket"
  description = "S3 bucket for the PSells demo's daily backups"
  type        = "String"
  value       = aws_s3_bucket.backups.bucket
}
