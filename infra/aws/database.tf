# RDS: a managed PostgreSQL for the demo, which exists only while
# var.managed_services is on (about USD 15.70 a month, which would end the
# free AWS window early). While it exists, Terraform puts its address in
# /psells/postgres/host, and the next deploy points the app at it; without it,
# the app uses its database container, as it always has.

# The password the database container already uses, read only for the moment
# RDS is set up and passed as a write-only value: it is never stored in the
# state, which keeps every other value in plain text.
ephemeral "aws_ssm_parameter" "postgres_password" {
  count = var.managed_services ? 1 : 0

  arn             = "arn:aws:ssm:ca-central-1:${data.aws_caller_identity.current.account_id}:parameter/psells/postgres/password"
  with_decryption = true
}

resource "aws_db_subnet_group" "db" {
  count = var.managed_services ? 1 : 0

  name       = "psells"
  subnet_ids = data.aws_subnets.default.ids
}

# Nothing reaches the database but the server: PostgreSQL's port, from the
# server's security group, and nothing else, from anywhere.
resource "aws_security_group" "db" {
  count = var.managed_services ? 1 : 0

  name        = "psells-db"
  description = "PSells RDS: PostgreSQL from the server only"
  vpc_id      = data.aws_vpc.default.id

  tags = {
    Name = "psells-db"
  }
}

resource "aws_vpc_security_group_ingress_rule" "db_from_server" {
  count = var.managed_services ? 1 : 0

  security_group_id            = aws_security_group.db[0].id
  description                  = "PostgreSQL from the PSells server"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.web.id
}

resource "aws_db_instance" "db" {
  count = var.managed_services ? 1 : 0

  identifier     = "psells"
  engine         = "postgres"
  engine_version = "18.6"
  instance_class = "db.t4g.micro"

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = aws_ssm_parameter.postgres_db.value
  username = aws_ssm_parameter.postgres_user.value
  # Write-only: sent to AWS, never kept in the state. Raise the version to
  # send a new one.
  password_wo         = ephemeral.aws_ssm_parameter.postgres_password[0].value
  password_wo_version = 1

  db_subnet_group_name   = aws_db_subnet_group.db[0].name
  vpc_security_group_ids = [aws_security_group.db[0].id]
  publicly_accessible    = false

  # One zone: a standby in a second zone doubles the cost, and the demo can
  # wait out an outage. RDS's own daily snapshot, kept a day.
  multi_az                = false
  backup_retention_period = 1

  # Switching off removes it, snapshots and all: it holds invented records,
  # rebuilt by the next deploy.
  skip_final_snapshot      = true
  delete_automated_backups = true
  deletion_protection      = false

  auto_minor_version_upgrade = true
  apply_immediately          = true
  copy_tags_to_snapshot      = true

  tags = {
    Name = "psells"
  }
}

# Where the next deploy finds RDS. Gone with it, so the deploy after
# switching off goes back to the container.
resource "aws_ssm_parameter" "postgres_host" {
  count = var.managed_services ? 1 : 0

  name        = "/psells/postgres/host"
  description = "RDS's address, while managed_services is on"
  type        = "String"
  value       = aws_db_instance.db[0].address
}
