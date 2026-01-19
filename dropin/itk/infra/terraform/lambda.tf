# Lambda function that invokes Claude 3.5 Haiku

data "archive_file" "lambda" {
  type        = "zip"
  source_file = "${path.module}/../lambda/itk_haiku_invoker/handler.py"
  output_path = "${path.module}/lambda.zip"
}

resource "aws_lambda_function" "haiku_invoker" {
  function_name = "${var.prefix}-haiku-invoker"
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
}

# Permission for Bedrock Agent to invoke Lambda
resource "aws_lambda_permission" "bedrock_agent" {
  statement_id  = "AllowBedrockAgent"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.haiku_invoker.function_name
  principal     = "bedrock.amazonaws.com"
  source_arn    = "arn:aws:bedrock:${local.region}:${local.account_id}:agent/*"
}

# CloudWatch log group (explicit for retention control)
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.haiku_invoker.function_name}"
  retention_in_days = 7
  tags              = local.tags
}
