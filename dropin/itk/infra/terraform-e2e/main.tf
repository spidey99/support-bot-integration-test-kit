# ITK E2E Test Infrastructure
# Minimal: Just a Lambda + CloudWatch log group
# Unique naming to avoid conflicts with shared infra

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  # No profile - uses environment credentials
}

# Random suffix to ensure unique naming
resource "random_id" "suffix" {
  byte_length = 4
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  region      = data.aws_region.current.name
  unique_name = "itk-e2e-${random_id.suffix.hex}"
  
  tags = {
    Project     = "itk-e2e-test"
    Environment = "ephemeral"
    ManagedBy   = "terraform"
    Purpose     = "E2E testing - safe to delete"
  }
}

# IAM role for Lambda
resource "aws_iam_role" "lambda" {
  name = "${local.unique_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = local.tags
}

# Lambda basic execution + Bedrock access
resource "aws_iam_role_policy" "lambda" {
  name = "${local.unique_name}-lambda-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${local.region}:${local.account_id}:*"
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "*"
      }
    ]
  })
}

# Lambda function - simple Haiku invoker with ITK span logging
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/lambda.zip"
}

resource "aws_lambda_function" "e2e_test" {
  function_name = local.unique_name
  role          = aws_iam_role.lambda.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  environment {
    variables = {
      MODEL_ID = var.model_id
    }
  }

  tags = local.tags

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# CloudWatch log group with short retention
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.unique_name}"
  retention_in_days = 1
  tags              = local.tags
}

# Outputs for the E2E test script
output "lambda_function_name" {
  value = aws_lambda_function.e2e_test.function_name
}

output "lambda_log_group" {
  value = aws_cloudwatch_log_group.lambda.name
}

output "unique_name" {
  value = local.unique_name
}

output "account_id" {
  value = local.account_id
}

output "region" {
  value = local.region
}
