# Bedrock Agents - Supervisor and Worker

#------------------------------------------------------------------------------
# Worker Agent - Has action group that calls Lambda
#------------------------------------------------------------------------------
resource "aws_bedrockagent_agent" "worker" {
  agent_name              = "${var.prefix}-worker"
  agent_resource_role_arn = aws_iam_role.bedrock_agent.arn
  foundation_model        = var.agent_model_id
  idle_session_ttl_in_seconds = 600
  
  # Force action invocation to test the action group
  instruction = <<-EOT
    You are an assistant that uses Claude Haiku for all responses. 
    For every user message, call the invokeHaiku action with the user's message as the prompt.
    Return the response from Claude Haiku to the user.
  EOT

  prepare_agent = true
}

# Action group for worker agent - calls Lambda
resource "aws_bedrockagent_agent_action_group" "invoke_haiku" {
  agent_id          = aws_bedrockagent_agent.worker.id
  agent_version     = "DRAFT"
  action_group_name = "invoke-haiku"
  description       = "Invokes Claude 3.5 Haiku via Lambda"

  action_group_executor {
    lambda = aws_lambda_function.haiku_invoker.arn
  }

  function_schema {
    member_functions {
      functions {
        name        = "invokeHaiku"
        description = "Sends a prompt to Claude 3.5 Haiku and returns the response"
        
        parameters {
          map_block_key = "prompt"
          type          = "string"
          description   = "The prompt to send to Claude 3.5 Haiku"
          required      = true
        }
      }
    }
  }
}

# Worker agent alias - routes to the latest prepared version
resource "aws_bedrockagent_agent_alias" "worker" {
  agent_id         = aws_bedrockagent_agent.worker.id
  agent_alias_name = "live"
  description      = "Live alias for worker agent - ${sha256(jsonencode(aws_bedrockagent_agent_action_group.invoke_haiku))}"

  # Force update when action group changes by including it in lifecycle
  lifecycle {
    replace_triggered_by = [
      aws_bedrockagent_agent_action_group.invoke_haiku
    ]
  }
}

#------------------------------------------------------------------------------
# Supervisor Agent - Standalone (collaboration shelved - ITK-0040)
#------------------------------------------------------------------------------
resource "aws_bedrockagent_agent" "supervisor" {
  agent_name              = "${var.prefix}-supervisor"
  agent_resource_role_arn = aws_iam_role.bedrock_agent.arn
  foundation_model        = var.agent_model_id
  idle_session_ttl_in_seconds = 600
  
  # Collaboration disabled for now - see ITK-0040
  agent_collaboration = "DISABLED"

  instruction = <<-EOT
    You are a supervisor agent. When you receive a request, analyze it and provide a helpful response.
  EOT

  prepare_agent = true
}

# Supervisor agent alias - routes to the latest prepared version
resource "aws_bedrockagent_agent_alias" "supervisor" {
  agent_id         = aws_bedrockagent_agent.supervisor.id
  agent_alias_name = "live"
  description      = "Live alias for supervisor agent"

  lifecycle {
    replace_triggered_by = [
      aws_bedrockagent_agent.supervisor
    ]
  }
}

# NOTE: Agent collaboration shelved - see ITK-0040 in TODO.md
# The collaborator resource requires additional permissions research
# #------------------------------------------------------------------------------
# # Agent Collaboration - Link Supervisor to Worker
# #------------------------------------------------------------------------------
# resource "aws_bedrockagent_agent_collaborator" "worker" {
#   agent_id         = aws_bedrockagent_agent.supervisor.id
#   agent_version    = "DRAFT"
#   collaborator_name = "worker-agent"
#   
#   collaboration_instruction = <<-EOT
#     This is the worker agent that processes tasks. When you need to execute
#     an action or generate content using Claude Haiku, delegate the task to 
#     this worker. Send the user's request or task as the input.
#   EOT
#   
#   agent_descriptor {
#     alias_arn = aws_bedrockagent_agent_alias.worker.agent_alias_arn
#   }
#   
#   relay_conversation_history = "TO_COLLABORATOR"
#   prepare_agent              = true
# }
