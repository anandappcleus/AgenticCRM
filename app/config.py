from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # WhatsApp / Meta
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "my_secret_verify_123"
    WHATSAPP_PHONE_ID: str = ""

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"

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
