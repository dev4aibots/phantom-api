"""PhantomAPI — GET /v1/models."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/models")
async def list_models():
    """Return available models for n8n model dropdown.

    Luna mode: the only backend model is GPT-5.6 Luna (free web chat).
    """
    return {
        "object": "list",
        "data": [
            {"id": "gpt-5.6-luna", "object": "model", "owned_by": "phantom-api"},
            {"id": "luna", "object": "model", "owned_by": "phantom-api"},
        ],
    }
