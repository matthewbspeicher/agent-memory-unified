from fastapi import APIRouter
from typing import List, Dict, Any
from pydantic import BaseModel
import uuid

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    thought_id: uuid.UUID

class InjectRequest(BaseModel):
    command: str

@router.get("/agents/{agent_name}/thoughts", response_model=List[Dict[str, Any]])
async def get_thoughts(agent_name: str, limit: int = 20):
    # Mock implementation for tests - wire to DB later
    return []

@router.post("/agents/copilot/chat")
async def copilot_chat(request: ChatRequest):
    # Mock LLM response
    return {"response": "Mock LLM explanation based on thought record."}

@router.post("/agents/copilot/inject")
async def copilot_inject(request: InjectRequest):
    # Mock memory injection
    return {"status": "success", "injected_memory": request.command}
