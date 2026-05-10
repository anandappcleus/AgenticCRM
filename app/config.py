from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # WhatsApp / Meta
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "my_secret_verify_123"
    WHATSAPP_PHONE_ID: str = ""

    # OpenAI / NVIDIA NIM (NIM is OpenAI-compatible — just change base_url + key)
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"
    # Embedding vector dimensions — must match the model:
    #   text-embedding-3-small    → 1536
    #   nvidia/nv-embedqa-e5-v5   → 1024  (free NIM, multilingual)
    #   nvidia/nv-embed-v1        → 4096
    OPENAI_EMBED_DIMENSIONS: int = 1024
    # For asymmetric NIM embedding models (e.g. nv-embedqa-e5-v5)
    # set these to "query" and "passage". Leave empty for OpenAI models.
    OPENAI_EMBED_QUERY_TYPE: str = ""
    OPENAI_EMBED_PASSAGE_TYPE: str = ""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost/wcrm"

    # App
    SECRET_KEY: str = "change-me-in-prod"
    DEBUG: bool = False
    FOLLOWUP_HOURS: int = 24
    CHROMA_PATH: str = "./chroma_db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
