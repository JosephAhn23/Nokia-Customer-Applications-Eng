# Terraform Infrastructure as Code
# High-availability network monitoring deployment

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }
  
  backend "s3" {
    bucket         = "netmon-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

# Variables
variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

# Provider configuration
provider "aws" {
  region = var.region
}

# Data sources
data "aws_availability_zones" "available" {
  state = "available"
}

# VPC Configuration
resource "aws_vpc" "netmon" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  
  tags = {
    Name        = "netmon-vpc"
    Environment = var.environment
    Application = "network-monitoring"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "netmon" {
  vpc_id = aws_vpc.netmon.id
  
  tags = {
    Name = "netmon-igw"
  }
}

# Private Subnets (for application)
resource "aws_subnet" "private" {
  count             = 3
  vpc_id            = aws_vpc.netmon.id
  cidr_block        = "10.0.${count.index + 1}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]
  
  tags = {
    Name = "netmon-private-${count.index + 1}"
    Type = "private"
  }
}

# Public Subnets (for load balancers)
resource "aws_subnet" "public" {
  count                   = 3
  vpc_id                  = aws_vpc.netmon.id
  cidr_block              = "10.0.${count.index + 101}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  
  tags = {
    Name = "netmon-public-${count.index + 1}"
    Type = "public"
  }
}

# NAT Gateway (for private subnet internet access)
resource "aws_eip" "nat" {
  count  = 3
  domain = "vpc"
  
  tags = {
    Name = "netmon-nat-eip-${count.index + 1}"
  }
}

resource "aws_nat_gateway" "netmon" {
  count         = 3
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  
  tags = {
    Name = "netmon-nat-${count.index + 1}"
  }
}

# Route Tables
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.netmon.id
  
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.netmon.id
  }
  
  tags = {
    Name = "netmon-public-rt"
  }
}

resource "aws_route_table" "private" {
  count  = 3
  vpc_id = aws_vpc.netmon.id
  
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.netmon[count.index].id
  }
  
  tags = {
    Name = "netmon-private-rt-${count.index + 1}"
  }
}

# Route Table Associations
resource "aws_route_table_association" "public" {
  count          = 3
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = 3
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# Security Groups
resource "aws_security_group" "netmon_api" {
  name        = "netmon-api-sg"
  description = "Security group for network monitoring API"
  vpc_id      = aws_vpc.netmon.id
  
  ingress {
    description = "HTTP"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }
  
  ingress {
    description = "HTTPS"
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
    Name = "netmon-api-sg"
  }
}

resource "aws_security_group" "netmon_db" {
  name        = "netmon-db-sg"
  description = "Security group for PostgreSQL database"
  vpc_id      = aws_vpc.netmon.id
  
  ingress {
    description     = "PostgreSQL"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.netmon_api.id]
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name = "netmon-db-sg"
  }
}

# RDS PostgreSQL Instance
resource "aws_db_subnet_group" "netmon" {
  name       = "netmon-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id
  
  tags = {
    Name = "netmon-db-subnet-group"
  }
}

resource "aws_db_instance" "netmon" {
  identifier             = "netmon-db"
  engine                 = "postgres"
  engine_version         = "14.9"
  instance_class         = "db.t3.medium"
  allocated_storage      = 100
  max_allocated_storage  = 500
  storage_type           = "gp3"
  storage_encrypted      = true
  
  db_name  = "netmon"
  username = "netmon"
  password = var.db_password  # Set via TF_VAR_db_password
  
  vpc_security_group_ids = [aws_security_group.netmon_db.id]
  db_subnet_group_name   = aws_db_subnet_group.netmon.name
  
  backup_retention_period = 30
  backup_window          = "03:00-04:00"
  maintenance_window     = "mon:04:00-mon:05:00"
  
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  
  performance_insights_enabled = true
  performance_insights_retention_period = 7
  
  tags = {
    Name        = "netmon-db"
    Environment = var.environment
  }
}

# Outputs
output "vpc_id" {
  value = aws_vpc.netmon.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "database_endpoint" {
  value     = aws_db_instance.netmon.endpoint
  sensitive = true
}

