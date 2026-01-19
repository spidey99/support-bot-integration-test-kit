"""Test agent with trace enabled."""
import boto3
import uuid
import json

c = boto3.client('bedrock-agent-runtime', region_name='us-east-1')

# Test WORKER agent 
print("=== Testing WORKER agent ===")
try:
    r = c.invoke_agent(
        agentId='WYEP3TYH1A',  # Worker
        agentAliasId='TSTALIASID', 
        sessionId=str(uuid.uuid4()), 
        inputText='Hello',  # Very simple prompt
        enableTrace=True
    )
    for e in r['completion']:
        if 'trace' in e:
            t = e['trace']
            if 'failureTrace' in t:
                print('FAILURE:', json.dumps(t['failureTrace'], indent=2, default=str))
        if 'chunk' in e:
            print('CHUNK:', e['chunk']['bytes'].decode())
except Exception as ex:
    print(f'Error: {ex}')
