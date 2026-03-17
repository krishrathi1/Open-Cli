import sys
from client import OpenRouterClient
from config import DEFAULT_MODEL, MODEL_NAMES

def test_single_call():
    print(f"Testing model: {DEFAULT_MODEL}", flush=True)
    client = OpenRouterClient()
    
    test_prompt = "How many r's are in the word 'strawberry'?"
    print(f"Prompt: {test_prompt}", flush=True)
    
    print("Sending request...", flush=True)
    content, reasoning, tool_events = client.send_message(test_prompt, DEFAULT_MODEL)
    
    print("\n--- Response ---", flush=True)
    print(f"Content: {content}", flush=True)
    print("\n--- Reasoning ---", flush=True)
    print(f"Reasoning: {reasoning}", flush=True)
    print("\n--- Tool Events ---", flush=True)
    print(f"Tool Events: {tool_events}", flush=True)
    
    if "Error:" in content:
        print("\nTest FAILED.", flush=True)
        sys.exit(1)
    else:
        print("\nTest PASSED.", flush=True)
        sys.exit(0)

if __name__ == "__main__":
    test_single_call()
