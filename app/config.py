from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = ROOT_DIR / "uploads"
USER_PHOTOS_DIR = UPLOAD_DIR / "user_photos"
RESULTS_DIR = UPLOAD_DIR / "results"

load_dotenv(ROOT_DIR / ".env")


class Settings(BaseSettings):
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    mongodb_uri: str = Field(default="", alias="MONGODB_URI")
    database_name: str = Field(default="virtual_tryon_db", alias="DATABASE_NAME")
    openai_model: str = Field(default="gpt-5.5", alias="OPENAI_MODEL")
    max_upload_size_bytes: int = 10 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_upload_dirs() -> None:
    USER_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
