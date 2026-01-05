terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-2"
}

# RDS PostgreSQL Database Instance
resource "aws_db_instance" "fnwm_db" {
  identifier     = "fnwm-db"
  instance_class = "db.t4g.micro"
  engine         = "postgres"
  engine_version = "17.6"

  allocated_storage     = 20
  max_allocated_storage = 1000
  storage_type          = "gp2"
  storage_encrypted     = true
  kms_key_id            = "arn:aws:kms:us-east-2:700555017031:key/b6db9cfa-1c80-4ff7-915b-f1809f94411a"

  username = "masteruser"
  password = var.db_password
  port     = 5432

  vpc_security_group_ids = ["sg-09d4deb063a53c0f2"]
  db_subnet_group_name   = "default-vpc-03f63828d5d11d2e4"
  publicly_accessible    = true
  availability_zone      = "us-east-2b"
  multi_az               = false

  backup_retention_period   = 1
  backup_window             = "08:50-09:20"
  maintenance_window        = "wed:05:21-wed:05:51"
  auto_minor_version_upgrade = true
  deletion_protection       = false
  copy_tags_to_snapshot     = true

  enabled_cloudwatch_logs_exports = []
  monitoring_interval             = 60
  monitoring_role_arn             = "arn:aws:iam::700555017031:role/rds-monitoring-role"

  performance_insights_enabled          = true
  performance_insights_kms_key_id       = "arn:aws:kms:us-east-2:700555017031:key/b6db9cfa-1c80-4ff7-915b-f1809f94411a"
  performance_insights_retention_period = 7

  skip_final_snapshot = true

  lifecycle {
    ignore_changes = [password]
  }
}

# S3 Bucket for Historic Flows Staging
resource "aws_s3_bucket" "historic_flows_staging" {
  bucket = "fnwm-historic-flows-staging"

  tags = {
    Name        = "FNWM Historic Flows Staging"
    Environment = "Staging"
    Purpose     = "Historic Flows Data Storage"
  }
}

# S3 Bucket Versioning
resource "aws_s3_bucket_versioning" "historic_flows_staging_versioning" {
  bucket = aws_s3_bucket.historic_flows_staging.id

  versioning_configuration {
    status = "Enabled"
  }
}

# S3 Bucket Server-Side Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "historic_flows_staging_encryption" {
  bucket = aws_s3_bucket.historic_flows_staging.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Example resource - EC2 instance (commented out)
# resource "aws_instance" "example" {
#   ami           = "ami-0c55b159cbfafe1f0"
#   instance_type = "t2.micro"
#
#   tags = {
#     Name = "ExampleInstance"
#   }
# }

