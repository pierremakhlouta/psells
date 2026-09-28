# The server: one t4g.micro on Ubuntu, reached through Session Manager only.

# Canonical's current Ubuntu 26.04 image for ARM, published in Parameter Store.
# A newer image does not replace a running server (ignore_changes below);
# a rebuild picks up whichever is current.
data "aws_ssm_parameter" "ubuntu" {
  name = "/aws/service/canonical/ubuntu/server/26.04/stable/current/arm64/hvm/ebs-gp3/ami-id"
}

resource "aws_instance" "server" {
  ami                  = data.aws_ssm_parameter.ubuntu.insecure_value
  instance_type        = "t4g.micro"
  subnet_id            = data.aws_subnet.server.id
  iam_instance_profile = aws_iam_instance_profile.server.name

  vpc_security_group_ids = [aws_security_group.web.id]

  instance_initiated_shutdown_behavior = "stop"

  # What the server does the first time it starts: prepare the host, clone
  # the repository and deploy. The one line added after the shebang chooses
  # Let's Encrypt's staging service for trial rebuilds (acme_staging).
  user_data = replace(
    file("${path.module}/../../deploy/aws/first-boot.sh"),
    "#!/bin/bash\n",
    "#!/bin/bash\nexport PSELLS_ACME_STAGING=${var.acme_staging ? "1" : "0"}\n",
  )

  # Standard, not t4g's default of unlimited, which bills for bursts.
  credit_specification {
    cpu_credits = "standard"
  }

  # IMDSv2 only, one hop: the server can reach its role's credentials and a
  # container, one hop further, cannot.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = {
      Name    = "psells-root"
      project = "psells"
    }
  }

  tags = {
    Name = "psells"
  }

  # A newer image or an edited first-boot script does not replace a running
  # server; both are used when it is rebuilt (terraform apply -replace).
  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

# A fixed address, so DNS and the certificate's name outlive a rebuilt server.
resource "aws_eip" "server" {
  domain = "vpc"

  tags = {
    Name = "psells"
  }
}

resource "aws_eip_association" "server" {
  instance_id   = aws_instance.server.id
  allocation_id = aws_eip.server.id
}
