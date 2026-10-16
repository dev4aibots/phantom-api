"""PhantomAPI — Application factory.

Endpoint obscurity: EVERYTHING (API, GUI, docs) lives under a random,
unguessable URL prefix, e.g. /9f3a.../v1/chat/completions. The prefix is
generated once, persisted to .env, and printed at startup.
"""

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1.router import router as v1_router
from app.config import settings
from app.services.browser import engine


def ensure_endpoint_prefix() -> str:
    """Return the random endpoint prefix, generating + persisting it if needed."""
    prefix = settings.ENDPOINT_PREFIX.strip().strip("/")
    if prefix:
        return prefix
    prefix = secrets.token_hex(12)  # 24 hex chars, unguessable
    env_path = Path(".env")
    try:
        text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        if "ENDPOINT_PREFIX" not in text:
            with env_path.open("a", encoding="utf-8") as fh:
                if text and not text.endswith("\n"):
                    fh.write("\n")
                fh.write(f"ENDPOINT_PREFIX={prefix}\n")
            print("[PhantomAPI] 📝 Random endpoint prefix saved to .env")
    except OSError as exc:
        print(f"[PhantomAPI] ⚠️ Could not persist prefix to .env: {exc}")
    return prefix


PREFIX = ensure_endpoint_prefix()
BASE = f"http://{settings.HOST}:{settings.PORT}/{PREFIX}"
print("[PhantomAPI] 🔒 Random endpoint prefix: /" + PREFIX)
print(f"[PhantomAPI] 📡 API base : {BASE}/v1")
print(f"[PhantomAPI] 🖥️  GUI      : {BASE}/gui")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Start the browser engine on startup."""
    engine.start()
    yield


app = FastAPI(
    title="PhantomAPI",
    description="A proxy that turns free ChatGPT into an OpenAI-compatible API.",
    version=__version__,
    lifespan=lifespan,
    docs_url=f"/{PREFIX}/docs",
    redoc_url=None,
    openapi_url=f"/{PREFIX}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix=f"/{PREFIX}")

static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount(f"/{PREFIX}/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", tags=["health"])
async def health_check():
    """Minimal health check — reveals nothing about the real endpoints."""
    return {"status": "ok"}


@app.get(f"/{PREFIX}/gui", tags=["gui"])
async def gui_redirect():
    """Redirect to Chat GUI."""
    return RedirectResponse(url=f"/{PREFIX}/static/index.html")
