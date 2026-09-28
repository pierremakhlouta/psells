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

  lifecycle {
    ignore_changes = [ami]
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
