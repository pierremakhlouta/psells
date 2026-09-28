# How GitHub Actions deploys to the server, with no key stored anywhere.
#
# A workflow run asks GitHub for a signed token saying which repository and
# branch it comes from (OpenID Connect). AWS checks the signature against the
# provider below and, if the token is from main of this repository, hands the
# run a role for an hour at most. That role can do one thing: run the
# psells-deploy document on the PSells server, and read how it went.

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

locals {
  # The only workflow runs that may deploy: this repository's main branch.
  deploy_subject = "repo:pierremakhlouta/psells:ref:refs/heads/main"
}

resource "aws_iam_role" "deploy" {
  name                 = "psells-deploy"
  description          = "Deploys PSells from GitHub Actions on main"
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
        Action    = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
            "token.actions.githubusercontent.com:sub" = local.deploy_subject
          }
        }
      },
    ]
  })
}

resource "aws_iam_role_policy" "deploy" {
  name = "run-psells-deploy"
  role = aws_iam_role.deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # The deploy document, on the server tagged psells, and nothing else:
        # not the generic shell document, which would run anything as root.
        Sid    = "RunTheDeployDocumentOnThePsellsServer"
        Effect = "Allow"
        Action = "ssm:SendCommand"
        Resource = [
          aws_ssm_document.deploy.arn,
          "arn:aws:ec2:ca-central-1:${data.aws_caller_identity.current.account_id}:instance/*",
        ]
        Condition = {
          StringEquals = { "ssm:resourceTag/Name" = "psells" }
        }
      },
      {
        # How the command went. These calls read results and change nothing;
        # SSM does not scope them to a resource.
        Sid      = "ReadTheResult"
        Effect   = "Allow"
        Action   = ["ssm:ListCommandInvocations", "ssm:GetCommandInvocation"]
        Resource = "*"
      },
    ]
  })
}

# The one command CI may run on the server. AWS checks both parameters against
# their patterns before anything runs, so nothing but a commit hash and an
# image digest can reach the shell.
resource "aws_ssm_document" "deploy" {
  name            = "psells-deploy"
  document_type   = "Command"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Deploy a PSells commit with its published image"
    parameters = {
      commit = {
        type           = "String"
        description    = "The full commit hash to deploy."
        allowedPattern = "^[0-9a-f]{40}$"
      }
      digest = {
        type           = "String"
        description    = "The digest CI published for that commit."
        allowedPattern = "^sha256:[0-9a-f]{64}$"
      }
    }
    mainSteps = [
      {
        action = "aws:runShellScript"
        name   = "deploy"
        inputs = {
          timeoutSeconds = "900"
          runCommand = [
            "set -eu",
            "git -C /opt/psells fetch --quiet origin",
            "git -C /opt/psells checkout --quiet --detach '{{ commit }}'",
            "PSELLS_IMAGE_DIGEST='{{ digest }}' /opt/psells/deploy/aws/deploy.sh",
          ]
        }
      },
    ]
  })
}

output "deploy_role_arn" {
  description = "The role the Deploy workflow assumes."
  value       = aws_iam_role.deploy.arn
}
