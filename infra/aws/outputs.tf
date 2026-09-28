output "public_ip" {
  description = "The Elastic IP psells.lakeshorefreight.me points at."
  value       = aws_eip.server.public_ip
}

output "instance_id" {
  description = "For aws ssm start-session --target."
  value       = aws_instance.server.id
}
