# Variables for ITK infrastructure

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "itk-mfa"
}

variable "prefix" {
  description = "Prefix for all resources"
  type        = string
  default     = "itk"
}

variable "model_id" {
  description = "Bedrock model inference profile ID for Lambda"
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "agent_model_id" {
  description = "Foundation model for Bedrock agents (must support on-demand)"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}
