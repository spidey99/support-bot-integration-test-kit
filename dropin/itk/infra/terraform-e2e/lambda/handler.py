"""Lambda handler for E2E testing.

This Lambda:
1. Invokes Claude Haiku via Bedrock
2. Emits ITK-compatible span logs
3. Returns the response

The span logs are what ITK will discover and parse.
"""
import json
import os
import time
import uuid
import boto3

bedrock = boto3.client("bedrock-runtime")
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-3-haiku-20240307-v1:0")


def emit_span(span_type: str, operation: str, trace_id: str, request: dict = None, 
              response: dict = None, error: dict = None, ts_start: str = None, ts_end: str = None):
    """Emit an ITK-compatible span log."""
    span = {
        "span_id": str(uuid.uuid4())[:8],
        "span_type": span_type,
        "operation": operation,
        "trace_id": trace_id,
        "ts_start": ts_start or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ts_end": ts_end or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if request:
        span["request"] = request
    if response:
        span["response"] = response
    if error:
        span["error"] = error
        span["status"] = "error"
    else:
        span["status"] = "success"
    
    # Print as JSON - CloudWatch will capture this
    print(json.dumps(span))


def lambda_handler(event, context):
    """Handle Lambda invocation."""
    trace_id = event.get("trace_id", str(uuid.uuid4())[:12])
    prompt = event.get("prompt", "Say hello in exactly 5 words.")
    
    ts_start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    # Emit entry span
    emit_span(
        span_type="lambda",
        operation="e2e_test_handler",
        trace_id=trace_id,
        request={"prompt": prompt, "event_keys": list(event.keys())},
        ts_start=ts_start,
    )
    
    try:
        # Invoke Bedrock
        bedrock_start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": prompt}]
        })
        
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json"
        )
        
        bedrock_end = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        result = json.loads(response["body"].read())
        text = result["content"][0]["text"]
        
        # Emit Bedrock span
        emit_span(
            span_type="bedrock",
            operation="InvokeModel",
            trace_id=trace_id,
            request={"model_id": MODEL_ID, "prompt_length": len(prompt)},
            response={"text_length": len(text), "stop_reason": result.get("stop_reason")},
            ts_start=bedrock_start,
            ts_end=bedrock_end,
        )
        
        ts_end = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        # Emit success exit span
        emit_span(
            span_type="lambda",
            operation="e2e_test_handler_complete",
            trace_id=trace_id,
            response={"text": text, "model_id": MODEL_ID},
            ts_start=ts_start,
            ts_end=ts_end,
        )
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "trace_id": trace_id,
                "text": text,
                "model_id": MODEL_ID
            })
        }
        
    except Exception as e:
        ts_end = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        # Emit error span
        emit_span(
            span_type="lambda",
            operation="e2e_test_handler_error",
            trace_id=trace_id,
            error={"type": type(e).__name__, "message": str(e)},
            ts_start=ts_start,
            ts_end=ts_end,
        )
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "trace_id": trace_id,
                "error": str(e)
            })
        }
