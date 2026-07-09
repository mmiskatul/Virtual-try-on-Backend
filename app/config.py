from functools import lru_cache
from pathlib import Path
import re

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = ROOT_DIR / "uploads"
USER_PHOTOS_DIR = UPLOAD_DIR / "user_photos"
PRODUCTS_DIR = UPLOAD_DIR / "products"
RESULTS_DIR = UPLOAD_DIR / "results"

load_dotenv(ROOT_DIR / ".env")


class Settings(BaseSettings):
    fal_key: str = Field(default="", alias="FAL_KEY")
    mongodb_uri: str = Field(default="", alias="MONGODB_URI")
    database_name: str = Field(default="virtual_tryon_db", alias="DATABASE_NAME")
    fal_model: str = Field(default="fal-ai/flux-2-lora-gallery/virtual-tryon", alias="FAL_MODEL")
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="", alias="ADMIN_PASSWORD")
    jwt_secret_key: str = Field(default="", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=1440, alias="JWT_EXPIRE_MINUTES")
    auth_cookie_name: str = Field(default="admin_access_token", alias="JWT_ACCESS_COOKIE_NAME")
    auth_cookie_secure: bool = Field(default=False, alias="JWT_ACCESS_COOKIE_SECURE")
    auth_cookie_samesite: str = Field(default="lax", alias="JWT_ACCESS_COOKIE_SAMESITE")
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001,https://ai-closet-viewer.vercel.app",
        alias="CORS_ALLOWED_ORIGINS",
    )
    cors_allowed_origin_regex: str = Field(
        default=r"^https:\/\/([a-z0-9-]+\.)*vercel\.app$",
        alias="CORS_ALLOWED_ORIGIN_REGEX",
    )
    cloudinary_cloud_name: str = Field(default="", alias="CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: str = Field(default="", alias="CLOUDINARY_API_KEY")
    cloudinary_api_secret: str = Field(default="", alias="CLOUDINARY_API_SECRET")
    cloudinary_folder: str = Field(default="ai-fit-studio", alias="CLOUDINARY_FOLDER")
    max_upload_size_bytes: int = 10 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def cors_allowed_origin_regex_compiled(self) -> str | None:
        pattern = self.cors_allowed_origin_regex.strip()
        if not pattern:
            return None
        re.compile(pattern)
        return pattern

    @property
    def effective_auth_cookie_secure(self) -> bool:
        if self.auth_cookie_samesite.strip().lower() == "none":
            return True
        return self.auth_cookie_secure

    @property
    def effective_auth_cookie_samesite(self) -> str:
        value = self.auth_cookie_samesite.strip().lower()
        if value not in {"lax", "strict", "none"}:
            return "lax"
        return value

    @property
    def cloudinary_configured(self) -> bool:
        return bool(
            self.cloudinary_cloud_name
            and self.cloudinary_api_key
            and self.cloudinary_api_secret
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_upload_dirs() -> None:
    USER_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
