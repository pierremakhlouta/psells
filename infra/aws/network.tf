# The account's default VPC and one of its subnets, used as they are. A
# network of PSells' own can come with the managed database in Phase 09.

data "aws_vpc" "default" {
  default = true
}

# Every default subnet, one per zone: RDS and the load balancer each need
# at least two zones.
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

data "aws_subnet" "server" {
  vpc_id            = data.aws_vpc.default.id
  availability_zone = "ca-central-1a"
  default_for_az    = true
}

# HTTP and HTTPS from anywhere, and nothing else in. No SSH: a shell comes
# through Session Manager, which needs no open port.
resource "aws_security_group" "web" {
  name        = "psells-web"
  description = "PSells: HTTP and HTTPS from anywhere, nothing else"
  vpc_id      = data.aws_vpc.default.id

  tags = {
    Name = "psells-web"
  }
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.web.id
  description       = "HTTP for the redirect and Lets Encrypt"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.web.id
  description       = "HTTPS"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

# Out to anywhere: package updates, Docker images, Let's Encrypt, AWS's APIs.
resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.web.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}
