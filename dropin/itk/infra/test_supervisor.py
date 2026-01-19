"""
Test Supervisor agent (RETURN_CONTROL only, no Lambda action group)
"""
import boto3
import json
import uuid

AGENT_ID = "OXKSJVXZSU"  # Supervisor
AGENT_ALIAS_ID = "Y8WG6RM49V"
REGION = "us-east-1"

client = boto3.client("bedrock-agent-runtime", region_name=REGION)

session_id = f"debug-{uuid.uuid4().hex[:8]}"
print(f"Testing Supervisor Agent")
print(f"Agent ID: {AGENT_ID}, Alias: {AGENT_ALIAS_ID}")
print(f"Session ID: {session_id}")
print("=" * 60)

try:
    response = client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=session_id,
        inputText="Please delegate this task to the worker: say hello",
        enableTrace=True
    )
    
    for event in response.get("completion", []):
        if "trace" in event:
            trace = event["trace"]
            if "trace" in trace:
                inner = trace["trace"]
                if "failureTrace" in inner:
                    print(f"\nFAILURE: {json.dumps(inner['failureTrace'], indent=2, default=str)}")
                if "orchestrationTrace" in inner:
                    orch = inner["orchestrationTrace"]
                    if "modelInvocationInput" in orch:
                        inp = orch["modelInvocationInput"]
                        print(f"\nModel: {inp.get('foundationModel')}")
                        # Show first 500 chars of text to see message format
                        text = inp.get("text", "")
                        print(f"Request text (first 500 chars): {text[:500]}...")
                    if "modelInvocationOutput" in orch:
                        out = orch["modelInvocationOutput"]
                        print(f"\nModel Output: {json.dumps(out, indent=2, default=str)[:1000]}")
        if "chunk" in event:
            chunk = event["chunk"]
            if "bytes" in chunk:
                print(f"\nRESPONSE: {chunk['bytes'].decode()}")
                
except Exception as e:
    print(f"\nERROR: {type(e).__name__}: {e}")
    if hasattr(e, 'response'):
        print(f"Response: {json.dumps(e.response, indent=2, default=str)}")
