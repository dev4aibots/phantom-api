"""PhantomAPI — GET /v1/models, GET /v1/stats."""

from fastapi import APIRouter, Depends

from app.dependencies import verify_api_key
from app.utils import metrics

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


@router.get("/stats", dependencies=[Depends(verify_api_key)])
async def get_stats():
    """Load snapshot: totals, in-flight requests, errors, latency."""
    return {"object": "stats", "data": metrics.snapshot()}
