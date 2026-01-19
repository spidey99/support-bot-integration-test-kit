# SQS Queue for test messages

resource "aws_sqs_queue" "test_queue" {
  name                       = "${var.prefix}-test-queue"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 86400  # 1 day
  receive_wait_time_seconds  = 10     # Long polling

  tags = local.tags
}

# Dead letter queue for failed messages
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.prefix}-test-queue-dlq"
  message_retention_seconds = 604800  # 7 days

  tags = local.tags
}

# Redrive policy - send failed messages to DLQ after 3 attempts
resource "aws_sqs_queue_redrive_policy" "test_queue" {
  queue_url = aws_sqs_queue.test_queue.id
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}
