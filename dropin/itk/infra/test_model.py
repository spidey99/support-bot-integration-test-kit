"""Test model access."""
import boto3
import json

c = boto3.client('bedrock-runtime', region_name='us-east-1')

# Test various models
models_to_test = [
    ('amazon.titan-tg1-large', '{"inputText": "hello"}'),
    ('amazon.nova-lite-v1:0', '{"messages":[{"role":"user","content":[{"text":"hello"}]}]}'),
    ('amazon.nova-pro-v1:0', '{"messages":[{"role":"user","content":[{"text":"hello"}]}]}'),
]

for model_id, body in models_to_test:
    try:
        r = c.invoke_model(modelId=model_id, body=body, contentType='application/json')
        print(f"✅ {model_id}: OK")
    except Exception as e:
        print(f"❌ {model_id}: {e}")
