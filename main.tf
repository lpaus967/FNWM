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

# S3 Bucket for Wind Data
resource "aws_s3_bucket" "wind_data" {
  bucket = "fnwm-wind-data"

  tags = {
    Name        = "FNWM Wind Data"
    Environment = "Production"
    Purpose     = "HRRR Wind Data Storage"
    DataSource  = "NOAA NOMADS"
  }
}

# S3 Bucket Versioning for Wind Data
resource "aws_s3_bucket_versioning" "wind_data_versioning" {
  bucket = aws_s3_bucket.wind_data.id

  versioning_configuration {
    status = "Enabled"
  }
}

# S3 Bucket Server-Side Encryption for Wind Data
resource "aws_s3_bucket_server_side_encryption_configuration" "wind_data_encryption" {
  bucket = aws_s3_bucket.wind_data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# S3 Bucket Lifecycle Policy for Wind Data (7-day retention)
resource "aws_s3_bucket_lifecycle_configuration" "wind_data_lifecycle" {
  bucket = aws_s3_bucket.wind_data.id

  rule {
    id     = "delete-old-wind-data"
    status = "Enabled"

    filter {
      prefix = "hrrr/"
    }

    expiration {
      days = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }
}

# S3 Bucket Public Access Block for Wind Data
# Allow bucket policy for public read access to PNG map tiles
resource "aws_s3_bucket_public_access_block" "wind_data_public_access" {
  bucket = aws_s3_bucket.wind_data.id

  block_public_acls       = true
  block_public_policy     = false
  ignore_public_acls      = true
  restrict_public_buckets = false
}

# S3 Bucket Policy for Public Read Access to PNG Files
resource "aws_s3_bucket_policy" "wind_data_public_read" {
  bucket = aws_s3_bucket.wind_data.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.wind_data.arn}/*"
      }
    ]
  })
}

# S3 Bucket CORS Configuration for Mapbox
resource "aws_s3_bucket_cors_configuration" "wind_data_cors" {
  bucket = aws_s3_bucket.wind_data.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
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

