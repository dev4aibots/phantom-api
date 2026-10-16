"""PhantomAPI — POST /v1/chat/completions."""

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.dependencies import verify_api_key
from app.schemas.chat import ChatCompletionRequest
from app.services.chat import process_chat_completion, stream_chat_completion

router = APIRouter()


@router.post("/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(payload: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint (SSE streaming supported)."""
    data = payload.model_dump()
    messages, model, tools = data["messages"], data["model"], data.get("tools")
    if data.get("stream"):
        return StreamingResponse(
            stream_chat_completion(messages, model, tools),
            media_type="text/event-stream",
        )
    # Run the blocking browser call in a worker thread; the event loop stays free
    return await asyncio.to_thread(process_chat_completion, messages, model, tools)
