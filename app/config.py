"""PhantomAPI — Configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from .env file or environment variables."""

    # --- Security ---
    API_SECRET_KEY: str = "change-me-to-a-strong-secret"

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 48526

    # --- Browser Engine ---
    HEADLESS: bool = True
    BROWSER_TIMEOUT: int = 120000  # milliseconds

    # --- Load control ---
    MAX_CONCURRENT_CHATS: int = 2  # simultaneous browser chats
    QUEUE_TIMEOUT: int = 60  # seconds to wait for a free slot before 503

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
