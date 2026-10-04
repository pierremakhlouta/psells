# The server's role: what the server itself may do in AWS, and nothing more.
# Each permission was checked by asking for something just outside it and
# being refused.

resource "aws_iam_role" "server" {
  name        = "psells-server"
  description = "The PSells EC2 server"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ec2.amazonaws.com" }
        Action    = "sts:AssumeRole"
      },
    ]
  })
}

resource "aws_iam_instance_profile" "server" {
  name = "psells-server"
  role = aws_iam_role.server.name
}

# Session Manager, so a shell needs no SSH.
resource "aws_iam_role_policy_attachment" "session_manager" {
  role       = aws_iam_role.server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# The database settings, the backup bucket's name, and where and how the
# monitoring agent sends. GetParametersByPath is authorised on the exact path
# asked for, so these are the three paths the scripts read.
resource "aws_iam_role_policy" "read_parameters" {
  name = "read-psells-parameters"
  role = aws_iam_role.server.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadPsellsDatabaseBackupAndMonitoringParameters"
        Effect = "Allow"
        Action = "ssm:GetParametersByPath"
        Resource = [
          "arn:aws:ssm:ca-central-1:${data.aws_caller_identity.current.account_id}:parameter/psells/postgres",
          "arn:aws:ssm:ca-central-1:${data.aws_caller_identity.current.account_id}:parameter/psells/backup",
          "arn:aws:ssm:ca-central-1:${data.aws_caller_identity.current.account_id}:parameter/psells/grafana",
        ]
      },
    ]
  })
}

# Add backups, and nothing else: no reading, listing or deleting, so a
# compromised server can neither read old copies nor erase them.
resource "aws_iam_role_policy" "write_backups" {
  name = "write-psells-backups"
  role = aws_iam_role.server.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AddDailyBackupsOnly"
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.backups.arn}/daily/*"
      },
    ]
  })
}
