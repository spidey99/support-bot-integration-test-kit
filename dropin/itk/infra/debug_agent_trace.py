"""
Debug script to capture full agent trace during action group invocation.
This will show exactly what's happening when the agent tries to invoke the Lambda.
"""
import boto3
import json
import os

# Configuration
AGENT_ID = "WYEP3TYH1A"  # Worker agent
AGENT_ALIAS_ID = "10KMKO4HUD"  # New alias with inference profile
REGION = "us-east-1"

client = boto3.client("bedrock-agent-runtime", region_name=REGION)

def invoke_with_trace(prompt: str):
    """Invoke agent with full trace enabled."""
    import uuid
    session_id = f"debug-{uuid.uuid4().hex[:8]}"  # Fresh session each time
    
    print(f"\n{'='*60}")
    print(f"Invoking Worker Agent with prompt: {prompt}")
    print(f"Agent ID: {AGENT_ID}, Alias: {AGENT_ALIAS_ID}")
    print(f"Session ID: {session_id}")
    print(f"{'='*60}\n")
    
    try:
        response = client.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=prompt,
            enableTrace=True  # Enable full trace
        )
        
        print("Processing response stream...\n")
        
        for event in response.get("completion", []):
            # Handle trace events
            if "trace" in event:
                trace = event["trace"]
                print(f"\n{'='*40} TRACE {'='*40}")
                print(json.dumps(trace, indent=2, default=str))
                
                # Extract specific trace info
                if "trace" in trace:
                    inner_trace = trace["trace"]
                    
                    # Pre-processing trace
                    if "preProcessingTrace" in inner_trace:
                        pre = inner_trace["preProcessingTrace"]
                        print(f"\n[PRE-PROCESSING]")
                        print(json.dumps(pre, indent=2, default=str))
                    
                    # Orchestration trace - this shows action group decisions
                    if "orchestrationTrace" in inner_trace:
                        orch = inner_trace["orchestrationTrace"]
                        print(f"\n[ORCHESTRATION]")
                        print(json.dumps(orch, indent=2, default=str))
                        
                        # Look for invocation input (action group call)
                        if "invocationInput" in orch:
                            inv = orch["invocationInput"]
                            print(f"\n>>> ACTION GROUP INVOCATION INPUT <<<")
                            print(json.dumps(inv, indent=2, default=str))
                        
                        # Look for model invocation output
                        if "modelInvocationOutput" in orch:
                            model_out = orch["modelInvocationOutput"]
                            print(f"\n>>> MODEL INVOCATION OUTPUT <<<")
                            print(json.dumps(model_out, indent=2, default=str))
                        
                        # Look for observation (Lambda response)
                        if "observation" in orch:
                            obs = orch["observation"]
                            print(f"\n>>> OBSERVATION (Lambda response?) <<<")
                            print(json.dumps(obs, indent=2, default=str))
                    
                    # Post-processing trace
                    if "postProcessingTrace" in inner_trace:
                        post = inner_trace["postProcessingTrace"]
                        print(f"\n[POST-PROCESSING]")
                        print(json.dumps(post, indent=2, default=str))
                    
                    # Failure trace - critical for debugging
                    if "failureTrace" in inner_trace:
                        fail = inner_trace["failureTrace"]
                        print(f"\n>>> FAILURE TRACE <<<")
                        print(json.dumps(fail, indent=2, default=str))
            
            # Handle chunk events (actual response)
            if "chunk" in event:
                chunk = event["chunk"]
                if "bytes" in chunk:
                    text = chunk["bytes"].decode("utf-8")
                    print(f"\n[RESPONSE CHUNK]: {text}")
                    
    except Exception as e:
        print(f"\n{'='*40} ERROR {'='*40}")
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception message: {e}")
        
        # Try to get more details from the exception
        if hasattr(e, 'response'):
            print(f"\nFull error response:")
            print(json.dumps(e.response, indent=2, default=str))

if __name__ == "__main__":
    # Test with a simple prompt that should trigger action group
    invoke_with_trace("Hello, please respond")
