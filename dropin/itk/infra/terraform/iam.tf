# IAM Roles for ITK infrastructure

#------------------------------------------------------------------------------
# Lambda Execution Role
#------------------------------------------------------------------------------
resource "aws_iam_role" "lambda" {
  name = "${var.prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_bedrock" {
  name = "bedrock-invoke"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "bedrock:InvokeModel"
      Resource = "*"
    }]
  })
}

#------------------------------------------------------------------------------
# Bedrock Agent Role
#------------------------------------------------------------------------------
resource "aws_iam_role" "bedrock_agent" {
  name = "${var.prefix}-bedrock-agent-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "bedrock.amazonaws.com"
      }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = local.account_id
        }
      }
    }]
  })

  tags = local.tags
}

resource "aws_iam_role_policy" "bedrock_agent" {
  name = "agent-permissions"
  role = aws_iam_role.bedrock_agent.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvokeModel"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:*:*:inference-profile/*"
        ]
      },
      {
        Sid    = "BedrockInferenceProfiles"
        Effect = "Allow"
        Action = [
          "bedrock:GetInferenceProfile",
          "bedrock:ListInferenceProfiles"
        ]
        Resource = [
          "arn:aws:bedrock:*:*:inference-profile/*",
          "arn:aws:bedrock:*:*:application-inference-profile/*"
        ]
      },
      {
        Sid      = "LambdaInvoke"
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.haiku_invoker.arn
      },
      {
        Sid      = "BedrockAgentInvoke"
        Effect   = "Allow"
        Action   = "bedrock:InvokeAgent"
        Resource = [
          "arn:aws:bedrock:${local.region}:${local.account_id}:agent/*",
          "arn:aws:bedrock:${local.region}:${local.account_id}:agent-alias/*"
        ]
      }
    ]
  })
}
