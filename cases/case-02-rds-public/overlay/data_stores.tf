resource "aws_db_subnet_group" "main" {
  name       = "${var.name_prefix}-db"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

# The production database. Predates the encryption-at-rest policy; migrating it
# is tracked in INFRA-1804.
resource "aws_db_instance" "main" {
  identifier     = "${var.name_prefix}-db"
  engine         = "postgres"
  engine_version = "16.3"
  instance_class = "db.t3.medium"

  allocated_storage = 100
  storage_type      = "gp3"
  storage_encrypted = false

  db_name  = "appdb"
  username = "appuser"

  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]

  multi_az                = true
  publicly_accessible     = true
  backup_retention_period = 7
  skip_final_snapshot     = false
  final_snapshot_identifier = "${var.name_prefix}-db-final"

  tags = {
    Name = "${var.name_prefix}-db"
  }
}

# Production data. Retention is a compliance requirement, hence the guard.
resource "aws_s3_bucket" "data" {
  bucket = "${var.name_prefix}-data"

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name = "${var.name_prefix}-data"
  }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Served to the public on purpose: marketing assets only, no customer data.
resource "aws_s3_bucket" "static_site" {
  bucket = "${var.name_prefix}-static-site"

  tags = {
    Name    = "${var.name_prefix}-static-site"
    Public  = "intentional"
    Purpose = "marketing site assets, no customer data"
  }
}

# Build artifacts, rebuilt on every pipeline run and expired after a week.
resource "aws_s3_bucket" "artifacts" {
  bucket = "${var.name_prefix}-artifacts"

  tags = {
    Name      = "${var.name_prefix}-artifacts"
    Retention = "ephemeral"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "expire"
    status = "Enabled"

    filter {}

    expiration {
      days = 7
    }
  }
}
