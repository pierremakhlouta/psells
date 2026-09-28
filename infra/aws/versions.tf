# The AWS server that runs the PSells demonstration, with invented records
# only, and everything around it. Run from this folder, as the IAM user
# pierre (aws login --profile psells):
#
#     AWS_PROFILE=psells terraform init
#     AWS_PROFILE=psells terraform plan
#
# The state lives in the bucket bootstrap/ made. It holds every value of every
# resource in plain text, which is why no secret is managed here: the database
# password is created in Parameter Store by hand and only its name is used.
#
# Not here: the IAM user this runs as, its group and the root user. Terraform
# must not be able to remove the access it runs with.

terraform {
  required_version = ">= 1.16.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.66.0"
    }
  }

  backend "s3" {
    bucket       = "psells-terraform-state-b9def35c9dea078638fa9a9103"
    key          = "psells/terraform.tfstate"
    region       = "ca-central-1"
    encrypt      = true
    use_lockfile = true
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

data "aws_caller_identity" "current" {}
