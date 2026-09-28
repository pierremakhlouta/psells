# The Application Load Balancer in front of the server, which exists only
# while var.managed_services is on: it costs about USD 32 a month with its two
# public addresses, which would end the free AWS window early.
#
# It has a name of its own, lb.psells.lakeshorefreight.me, pointed at it by
# hand at Namecheap each time it is switched on, so the main demo address,
# which points at the server's Elastic IP, never moves.

locals {
  lb_name = "lb.psells.lakeshorefreight.me"
}

# The load balancer's certificate, from AWS Certificate Manager: free, renewed
# by AWS, and usable only on AWS's own load balancers. It stays whether the
# switch is on or off, so it is validated once: AWS checks a record, printed
# by the output below, that is added at Namecheap and left there.
resource "aws_acm_certificate" "lb" {
  domain_name       = local.lb_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Waits until AWS has issued the certificate, which it does once the check
# record is found. Nothing is created here; the listener uses the result.
resource "aws_acm_certificate_validation" "lb" {
  count = var.managed_services ? 1 : 0

  certificate_arn = aws_acm_certificate.lb.arn
}

# In from anywhere on 80 and 443; out only to the server's load balancer port.
resource "aws_security_group" "lb" {
  count = var.managed_services ? 1 : 0

  name        = "psells-lb"
  description = "PSells load balancer: HTTP and HTTPS in, the server out"
  vpc_id      = data.aws_vpc.default.id

  tags = {
    Name = "psells-lb"
  }
}

resource "aws_vpc_security_group_ingress_rule" "lb_https" {
  count = var.managed_services ? 1 : 0

  security_group_id = aws_security_group.lb[0].id
  description       = "HTTPS"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "lb_http" {
  count = var.managed_services ? 1 : 0

  security_group_id = aws_security_group.lb[0].id
  description       = "HTTP, which only redirects to HTTPS"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "lb_to_server" {
  count = var.managed_services ? 1 : 0

  security_group_id            = aws_security_group.lb[0].id
  description                  = "nginx's load balancer listener"
  ip_protocol                  = "tcp"
  from_port                    = 8090
  to_port                      = 8090
  referenced_security_group_id = aws_security_group.web.id
}

# The server lets in its load balancer port from the load balancer alone.
resource "aws_vpc_security_group_ingress_rule" "server_from_lb" {
  count = var.managed_services ? 1 : 0

  security_group_id            = aws_security_group.web.id
  description                  = "nginx's load balancer listener, from the load balancer only"
  ip_protocol                  = "tcp"
  from_port                    = 8090
  to_port                      = 8090
  referenced_security_group_id = aws_security_group.lb[0].id
}

resource "aws_lb" "lb" {
  count = var.managed_services ? 1 : 0

  name               = "psells"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.lb[0].id]
  subnets            = data.aws_subnets.default.ids

  # Requests with malformed headers are refused here rather than passed on.
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "server" {
  count = var.managed_services ? 1 : 0

  name        = "psells-server"
  port        = 8090
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "instance"

  health_check {
    path    = "/lb-health"
    matcher = "200"
  }
}

resource "aws_lb_target_group_attachment" "server" {
  count = var.managed_services ? 1 : 0

  target_group_arn = aws_lb_target_group.server[0].arn
  target_id        = aws_instance.server.id
  port             = 8090
}

# HTTPS, TLS 1.3 only as nginx is, with post-quantum key exchange. A request
# for any name but the load balancer's own is answered 421 here and never
# reaches the server, as nginx answers a name it does not serve.
resource "aws_lb_listener" "https" {
  count = var.managed_services ? 1 : 0

  load_balancer_arn = aws_lb.lb[0].arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-3-PQ-2025-09"
  certificate_arn   = aws_acm_certificate_validation.lb[0].certificate_arn

  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      status_code  = "421"
      message_body = "Misdirected Request"
    }
  }
}

resource "aws_lb_listener_rule" "psells" {
  count = var.managed_services ? 1 : 0

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 1

  condition {
    host_header {
      values = [local.lb_name]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.server[0].arn
  }
}

# Plain HTTP only redirects to HTTPS, as nginx's port 80 does.
resource "aws_lb_listener" "http" {
  count = var.managed_services ? 1 : 0

  load_balancer_arn = aws_lb.lb[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      protocol    = "HTTPS"
      port        = "443"
      status_code = "HTTP_301"
    }
  }
}

output "lb_address" {
  description = "Where lb.psells.lakeshorefreight.me points at Namecheap (a CNAME) while the switch is on."
  value       = one(aws_lb.lb[*].dns_name)
}

output "lb_certificate_check_record" {
  description = "The record to add at Namecheap once, so AWS can issue the load balancer's certificate."
  value = [
    for option in aws_acm_certificate.lb.domain_validation_options : {
      type  = option.resource_record_type
      name  = option.resource_record_name
      value = option.resource_record_value
    }
  ]
}
