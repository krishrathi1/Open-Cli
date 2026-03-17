from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import List, Optional
from client import OpenRouterClient
import os

app = FastAPI()

# Helper initialization inside backend/ subdirectory
# client needs to point to workspace_root if provided
client = OpenRouterClient()

class ChatRequest(BaseModel):
    messages: List[dict]
    model: str

@app.get("/")
def read_root():
    return {"status": "krishai backend active"}

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Handles a single turn or continuous turn.
    Returns the assistant content, reasoning, and tool executions.
    """
    try:
        # Update client history with incoming messages
        client.messages = request.messages
        # Trigger model request
        # Note: OpenRouterClient._request_completion returns the raw message choice.
        # We can just use that to see if tool call is present.
        
        # We will use the completion directly from client.py to remain modular
        message_data = client._request_completion(request.model)
        content = message_data.get("content", "")
        reasoning = message_data.get("reasoning_details") or message_data.get("reasoning")
        
        return {
            "ok": True,
            "content": content,
            "reasoning": reasoning,
            "messages": client.messages + [{"role": "assistant", "content": content}]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
