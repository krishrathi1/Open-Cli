import sys
from client import OpenRouterClient
from config import DEFAULT_MODEL, MODEL_NAMES

def test_single_call():
    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(f"Testing model: {DEFAULT_MODEL}\n")
        f.flush()
        
        try:
            client = OpenRouterClient()
            test_prompt = "How many r's are in the word 'strawberry'?"
            f.write(f"Prompt: {test_prompt}\n")
            f.flush()
            
            f.write("Sending request...\n")
            f.flush()
            content, reasoning, tool_events = client.send_message(test_prompt, DEFAULT_MODEL)
            
            f.write("\n--- Response ---\n")
            f.write(f"Content: {content}\n")
            f.write("\n--- Reasoning ---\n")
            f.write(f"Reasoning: {reasoning}\n")
            f.write("\n--- Tool Events ---\n")
            f.write(f"Tool Events: {tool_events}\n")
            
            if "Error:" in content:
                 f.write("\nTest FAILED.\n")
            else:
                 f.write("\nTest PASSED.\n")
                 
        except Exception as e:
             f.write(f"\nException: {str(e)}\n")

if __name__ == "__main__":
    test_single_call()
