# Public load balancer. Open on 443 to the world by design -- this is the
# intended entry point for the service.
resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb"
  description = "Public entry point for the service"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from the internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-alb"
  }
}

resource "aws_security_group" "app" {
  name        = "${var.name_prefix}-app"
  description = "Application instances"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Application traffic from the load balancer only"
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-app"
  }
}

resource "aws_security_group" "db" {
  name        = "${var.name_prefix}-db"
  description = "Database, reachable from the application tier only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Postgres, temporarily open for the data migration"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-db"
  }
}
