variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "model_id" {
  description = "Bedrock model ID for Lambda"
  type        = string
  default     = "us.anthropic.claude-3-haiku-20240307-v1:0"
}
