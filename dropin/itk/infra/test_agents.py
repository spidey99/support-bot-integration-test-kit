"""Test script for ITK Bedrock Agents."""
import boto3
import json
import uuid

# Configuration from .env.live
WORKER_AGENT_ID = "WYEP3TYH1A"
WORKER_ALIAS_ID = "NNVDZ6VQ4C"
SUPERVISOR_AGENT_ID = "OXKSJVXZSU"
SUPERVISOR_ALIAS_ID = "Y8WG6RM49V"
REGION = "us-east-1"

def test_worker_agent():
    """Test the worker agent which calls Lambda."""
    client = boto3.client("bedrock-agent-runtime", region_name=REGION)
    
    session_id = str(uuid.uuid4())
    print(f"Testing Worker Agent (ID: {WORKER_AGENT_ID})")
    print(f"Session: {session_id}")
    print("-" * 50)
    
    response = client.invoke_agent(
        agentId=WORKER_AGENT_ID,
        agentAliasId=WORKER_ALIAS_ID,
        sessionId=session_id,
        inputText="Please invoke the haiku action with prompt: Say hello in exactly 5 words"
    )
    
    # Stream the response
    full_response = ""
    for event in response["completion"]:
        if "chunk" in event:
            chunk_text = event["chunk"]["bytes"].decode("utf-8")
            full_response += chunk_text
            print(chunk_text, end="", flush=True)
    
    print("\n" + "-" * 50)
    print(f"Full response length: {len(full_response)}")
    return full_response

def test_supervisor_agent():
    """Test the supervisor agent which delegates to worker."""
    client = boto3.client("bedrock-agent-runtime", region_name=REGION)
    
    session_id = str(uuid.uuid4())
    print(f"\nTesting Supervisor Agent (ID: {SUPERVISOR_AGENT_ID})")
    print(f"Session: {session_id}")
    print("-" * 50)
    
    response = client.invoke_agent(
        agentId=SUPERVISOR_AGENT_ID,
        agentAliasId=SUPERVISOR_ALIAS_ID,
        sessionId=session_id,
        inputText="Process this message: Hello, please respond briefly"
    )
    
    # Stream the response
    full_response = ""
    for event in response["completion"]:
        if "chunk" in event:
            chunk_text = event["chunk"]["bytes"].decode("utf-8")
            full_response += chunk_text
            print(chunk_text, end="", flush=True)
    
    print("\n" + "-" * 50)
    print(f"Full response length: {len(full_response)}")
    return full_response

if __name__ == "__main__":
    print("=" * 60)
    print("ITK Bedrock Agent Test")
    print("=" * 60)
    
    try:
        test_worker_agent()
    except Exception as e:
        print(f"Worker Agent Error: {e}")
    
    try:
        test_supervisor_agent()
    except Exception as e:
        print(f"Supervisor Agent Error: {e}")
