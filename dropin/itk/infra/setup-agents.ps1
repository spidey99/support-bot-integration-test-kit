# ITK Infrastructure Setup - Bedrock Agents
# Run after setup-lambda.ps1

$ErrorActionPreference = "Stop"
$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$REGION = "us-east-1"

Write-Host "Creating Bedrock Agents for ITK testing..." -ForegroundColor Cyan

$agentRoleArn = "arn:aws:iam::${ACCOUNT_ID}:role/itk-bedrock-agent-role"
$lambdaArn = "arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:itk-haiku-invoker"

# ============================================================
# 1. Create Worker Agent (delegates to Lambda)
# ============================================================
Write-Host "`n[1/4] Creating Worker Agent..." -ForegroundColor Yellow

$workerInstruction = @"
You are a helpful assistant that processes user requests.
When asked to do something, use the invoke_haiku action to get a response from Claude.
Always be brief and helpful.
"@

$workerAgent = aws bedrock-agent create-agent `
    --agent-name "itk-worker" `
    --agent-resource-role-arn $agentRoleArn `
    --foundation-model "anthropic.claude-3-5-haiku-20241022-v1:0" `
    --instruction $workerInstruction `
    --idle-session-ttl-in-seconds 600 `
    --description "ITK test worker agent - calls Lambda for processing" `
    --region $REGION `
    --output json 2>&1 | ConvertFrom-Json

$workerAgentId = $workerAgent.agent.agentId
Write-Host "  Created: itk-worker (ID: $workerAgentId)" -ForegroundColor Green

# ============================================================
# 2. Add Action Group to Worker Agent
# ============================================================
Write-Host "`n[2/4] Adding Action Group to Worker Agent..." -ForegroundColor Yellow

# Grant Lambda permission for Bedrock to invoke it
aws lambda add-permission `
    --function-name itk-haiku-invoker `
    --statement-id bedrock-agent-invoke `
    --action lambda:InvokeFunction `
    --principal bedrock.amazonaws.com `
    --source-arn "arn:aws:bedrock:${REGION}:${ACCOUNT_ID}:agent/${workerAgentId}" `
    --region $REGION 2>$null

# Create action group with OpenAPI schema
$openApiSchema = @"
{
  "openapi": "3.0.0",
  "info": {"title": "Haiku Invoker", "version": "1.0.0"},
  "paths": {
    "/invoke": {
      "post": {
        "operationId": "invokeHaiku",
        "summary": "Send a prompt to Claude 3.5 Haiku",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "prompt": {"type": "string", "description": "The prompt to send to Claude"}
                },
                "required": ["prompt"]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful response",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "message": {"type": "string"}
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"@

$openApiSchema | Out-File -FilePath "openapi-schema.json" -Encoding utf8

aws bedrock-agent create-agent-action-group `
    --agent-id $workerAgentId `
    --agent-version "DRAFT" `
    --action-group-name "haiku-actions" `
    --action-group-executor lambdaArn=$lambdaArn `
    --api-schema '{"payload": "'$(Get-Content openapi-schema.json -Raw | ForEach-Object { $_ -replace '"', '\"' -replace "`n", "" -replace "`r", "" })'"}' `
    --region $REGION 2>$null | Out-Null

Write-Host "  Added action group: haiku-actions" -ForegroundColor Green

# ============================================================
# 3. Create Supervisor Agent
# ============================================================
Write-Host "`n[3/4] Creating Supervisor Agent..." -ForegroundColor Yellow

$supervisorInstruction = @"
You are a supervisor agent that routes requests to specialized workers.
When a user asks something, delegate to the worker agent to process it.
Summarize the worker's response for the user.
"@

$supervisorAgent = aws bedrock-agent create-agent `
    --agent-name "itk-supervisor" `
    --agent-resource-role-arn $agentRoleArn `
    --foundation-model "anthropic.claude-3-5-haiku-20241022-v1:0" `
    --instruction $supervisorInstruction `
    --idle-session-ttl-in-seconds 600 `
    --description "ITK test supervisor agent - routes to worker agents" `
    --region $REGION `
    --output json 2>&1 | ConvertFrom-Json

$supervisorAgentId = $supervisorAgent.agent.agentId
Write-Host "  Created: itk-supervisor (ID: $supervisorAgentId)" -ForegroundColor Green

# ============================================================
# 4. Prepare and Create Aliases
# ============================================================
Write-Host "`n[4/4] Preparing agents and creating aliases..." -ForegroundColor Yellow

# Prepare worker agent
aws bedrock-agent prepare-agent --agent-id $workerAgentId --region $REGION | Out-Null
Write-Host "  Prepared: itk-worker" -ForegroundColor Green

# Wait for preparation
Start-Sleep -Seconds 5

# Create worker alias
$workerAlias = aws bedrock-agent create-agent-alias `
    --agent-id $workerAgentId `
    --agent-alias-name "live" `
    --description "Production alias for itk-worker" `
    --region $REGION `
    --output json 2>&1 | ConvertFrom-Json

$workerAliasId = $workerAlias.agentAlias.agentAliasId
Write-Host "  Created alias: itk-worker/live (ID: $workerAliasId)" -ForegroundColor Green

# Prepare supervisor agent
aws bedrock-agent prepare-agent --agent-id $supervisorAgentId --region $REGION | Out-Null
Write-Host "  Prepared: itk-supervisor" -ForegroundColor Green

Start-Sleep -Seconds 5

# Create supervisor alias
$supervisorAlias = aws bedrock-agent create-agent-alias `
    --agent-id $supervisorAgentId `
    --agent-alias-name "live" `
    --description "Production alias for itk-supervisor" `
    --region $REGION `
    --output json 2>&1 | ConvertFrom-Json

$supervisorAliasId = $supervisorAlias.agentAlias.agentAliasId
Write-Host "  Created alias: itk-supervisor/live (ID: $supervisorAliasId)" -ForegroundColor Green

# Cleanup
Remove-Item openapi-schema.json -ErrorAction SilentlyContinue

# ============================================================
# Output summary
# ============================================================
Write-Host "`n✅ Bedrock Agents created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Worker Agent:" -ForegroundColor Cyan
Write-Host "  ID:    $workerAgentId"
Write-Host "  Alias: $workerAliasId"
Write-Host ""
Write-Host "Supervisor Agent:" -ForegroundColor Cyan
Write-Host "  ID:    $supervisorAgentId"
Write-Host "  Alias: $supervisorAliasId"
Write-Host ""

# Save to .env file
$envContent = @"
# ITK Test Infrastructure - Generated $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
ITK_MODE=live
AWS_REGION=$REGION

# Bedrock Agents
ITK_SUPERVISOR_AGENT_ID=$supervisorAgentId
ITK_SUPERVISOR_AGENT_ALIAS_ID=$supervisorAliasId
ITK_WORKER_AGENT_ID=$workerAgentId
ITK_WORKER_AGENT_ALIAS_ID=$workerAliasId

# Lambda
ITK_LAMBDA_FUNCTION=itk-haiku-invoker

# Log Groups (auto-created by Lambda)
ITK_LOG_GROUPS=/aws/lambda/itk-haiku-invoker
"@

$envPath = Join-Path (Split-Path -Parent $PSScriptRoot) ".env.live"
$envContent | Out-File -FilePath $envPath -Encoding utf8

Write-Host "Configuration saved to: $envPath" -ForegroundColor Green
Write-Host "`nNext: Run setup-sqs.ps1 (optional) or start testing!" -ForegroundColor Cyan
