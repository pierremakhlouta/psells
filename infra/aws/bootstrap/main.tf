# The S3 bucket that holds the state of infra/aws/, and nothing else.
#
# Terraform keeps a record of what it built, its state, and infra/aws/ keeps
# its state in this bucket. The bucket cannot hold the state that creates it,
# so it is made here, once, by a configuration of its own whose small state
# stays on the machine that ran it (gitignored). If that local file is lost,
# `terraform import` rebuilds it from the bucket's name.
#
#     cd infra/aws/bootstrap
#     AWS_PROFILE=psells terraform init
#     AWS_PROFILE=psells terraform apply
#
# State holds every value of every resource in plain text, so the bucket is
# private, encrypted, reachable over TLS only, and versioned, so a damaged
# state can be rolled back.

terraform {
  required_version = ">= 1.16.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.66.0"
    }
  }
}

provider "aws" {
  region = "ca-central-1"

  default_tags {
    tags = {
      project = "psells"
    }
  }
}

resource "aws_s3_bucket" "state" {
  # AWS completes the name, so it is unique and holds no account number.
  bucket_prefix = "psells-terraform-state-"

  # Losing this bucket loses the record of everything else.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Every apply writes a new version of the state. Old versions are kept for 90
# days, long enough to notice a bad one and go back.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  depends_on = [aws_s3_bucket_versioning.state]
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "HTTPSOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.state.arn,
          "${aws_s3_bucket.state.arn}/*",
        ]
        Condition = {
          Bool = { "aws:SecureTransport" = "false" }
        }
      },
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.state]
}

output "state_bucket" {
  description = "The bucket to name in infra/aws/'s backend block."
  value       = aws_s3_bucket.state.bucket
}
