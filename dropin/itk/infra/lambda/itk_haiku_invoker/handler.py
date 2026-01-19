"""
ITK Haiku Invoker Lambda - Wraps Claude Haiku 4.5 with realistic structured logging.

This Lambda uses a realistic log format that represents what actual production
systems emit. The ITK parser must be smart enough to normalize these logs into
spans, handling field name variance and missing fields.

Log format uses common patterns found in real AWS Lambda applications:
- level: INFO/WARN/ERROR
- message: human-readable description
- Various context fields (requestId, traceId, etc.)
- Timestamps in ISO format
- Nested request/response data
"""

import json
import os
import uuid
import boto3
from datetime import datetime, timezone


bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# Use inference profile - can be overridden via environment variable
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")


def log_structured(level: str, message: str, **kwargs) -> None:
    """
    Emit structured JSON log. This is a realistic pattern - not ITK-specific.
    
    Real systems use various field names:
    - requestId, request_id, reqId
    - traceId, trace_id, correlationId
    - timestamp, ts, time, @timestamp
    """
    entry = {
        "level": level,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs
    }
    print(json.dumps(entry))


def lambda_handler(event, context):
    """Invoke Claude Haiku 4.5 and emit realistic structured logs."""
    
    request_id = context.aws_request_id if context else str(uuid.uuid4())
    
    # Extract trace context from event (passed through from agent or caller)
    trace_id = event.get("sessionId") or event.get("traceId") or str(uuid.uuid4())
    
    # Log raw event for debugging (common pattern)
    log_structured("DEBUG", "Lambda invoked", 
                   requestId=request_id, 
                   event=event)
    
    # Get the prompt - handle both direct invocation and agent action group formats
    prompt = None
    
    # Function schema format (newer) - parameters come directly
    if "actionGroup" in event and "function" in event:
        parameters = event.get("parameters", [])
        for param in parameters:
            if param.get("name") == "prompt":
                prompt = param.get("value")
                break
    
    # API schema format (OpenAPI style) - prompt is in requestBody
    elif "actionGroup" in event and "requestBody" in event:
        request_body = event.get("requestBody", {})
        content = request_body.get("content", {})
        app_json = content.get("application/json", {})
        properties = app_json.get("properties", [])
        if isinstance(properties, list):
            for prop in properties:
                if prop.get("name") == "prompt":
                    prompt = prop.get("value")
                    break
        elif isinstance(properties, dict) and "prompt" in properties:
            prompt = properties["prompt"]
    
    # Direct invocation formats
    if not prompt:
        prompt = event.get("inputText") or event.get("prompt") or event.get("message", "Hello")
    
    # Log handler entry (realistic format - not ITK schema)
    log_structured("INFO", "Processing request",
                   requestId=request_id,
                   traceId=trace_id,
                   component="lambda",
                   operation="handler.entry",
                   input={"prompt_preview": prompt[:100]})
    
    # Build Bedrock request
    bedrock_request = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 256,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    # Log model call entry
    log_structured("INFO", "Calling Bedrock model",
                   requestId=request_id,
                   traceId=trace_id,
                   component="bedrock",
                   operation="InvokeModel",
                   modelId=MODEL_ID,
                   inputTokenEstimate=len(prompt) // 4)
    
    try:
        # Call Bedrock
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(bedrock_request),
            contentType="application/json",
            accept="application/json"
        )
        
        response_body = json.loads(response["body"].read())
        assistant_message = response_body["content"][0]["text"]
        usage = response_body.get("usage", {})
        
        # Log model call success
        log_structured("INFO", "Bedrock model responded",
                       requestId=request_id,
                       traceId=trace_id,
                       component="bedrock",
                       operation="InvokeModel",
                       modelId=MODEL_ID,
                       usage=usage,
                       responseLength=len(assistant_message))
        
        # Build response - format depends on invocation type
        is_function_schema = "actionGroup" in event and "function" in event
        is_api_schema = "actionGroup" in event and "apiPath" in event
        
        if is_function_schema:
            result = {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": event.get("actionGroup"),
                    "function": event.get("function"),
                    "functionResponse": {
                        "responseBody": {
                            "TEXT": {
                                "body": assistant_message
                            }
                        }
                    }
                }
            }
        elif is_api_schema:
            result = {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": event.get("actionGroup"),
                    "apiPath": event.get("apiPath"),
                    "httpMethod": event.get("httpMethod"),
                    "httpStatusCode": 200,
                    "responseBody": {
                        "application/json": {
                            "body": json.dumps({"message": assistant_message})
                        }
                    }
                }
            }
        else:
            result = {
                "statusCode": 200,
                "body": {
                    "message": assistant_message,
                    "model": MODEL_ID,
                    "usage": usage,
                    "traceId": trace_id,
                    "requestId": request_id
                }
            }
        
        # Log handler exit success
        log_structured("INFO", "Request completed successfully",
                       requestId=request_id,
                       traceId=trace_id,
                       component="lambda",
                       operation="handler.exit",
                       status="success",
                       responseLength=len(assistant_message))
        
        return result
        
    except Exception as e:
        # Log model call failure
        log_structured("ERROR", f"Bedrock model failed: {e}",
                       requestId=request_id,
                       traceId=trace_id,
                       component="bedrock",
                       operation="InvokeModel",
                       modelId=MODEL_ID,
                       error={"type": type(e).__name__, "message": str(e)})
        
        is_function_schema = "actionGroup" in event and "function" in event
        is_api_schema = "actionGroup" in event and "apiPath" in event
        
        if is_function_schema:
            result = {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": event.get("actionGroup"),
                    "function": event.get("function"),
                    "functionResponse": {
                        "responseBody": {
                            "TEXT": {
                                "body": f"Error: {str(e)}"
                            }
                        }
                    }
                }
            }
        elif is_api_schema:
            result = {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": event.get("actionGroup"),
                    "apiPath": event.get("apiPath"),
                    "httpMethod": event.get("httpMethod"),
                    "httpStatusCode": 500,
                    "responseBody": {
                        "application/json": {
                            "body": json.dumps({"error": str(e)})
                        }
                    }
                }
            }
        else:
            result = {
                "statusCode": 500,
                "body": {"error": str(e), "traceId": trace_id}
            }
        
        # Log handler exit failure
        log_structured("ERROR", "Request failed",
                       requestId=request_id,
                       traceId=trace_id,
                       component="lambda",
                       operation="handler.exit",
                       status="error",
                       error={"type": type(e).__name__, "message": str(e)})
        
        return result
