"""PhantomAPI — Configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from .env file or environment variables."""

    # --- Security ---
    API_SECRET_KEY: str = "change-me-to-a-strong-secret"

    # --- Endpoint obscurity ---
    # Random URL prefix for ALL endpoints (e.g. /a3f9.../v1/chat/completions).
    # Empty = a cryptographically random one is generated at startup and
    # persisted to .env so it stays stable across restarts.
    ENDPOINT_PREFIX: str = ""

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 7777

    # --- Browser Engine ---
    HEADLESS: bool = True
    BROWSER_TIMEOUT: int = 120000  # milliseconds

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
