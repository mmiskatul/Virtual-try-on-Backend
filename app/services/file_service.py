import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urlparse

import aiofiles
from fastapi import UploadFile

from app.config import RESULTS_DIR, ROOT_DIR, USER_PHOTOS_DIR, get_settings
from app.utils.validators import validate_image_upload

settings = get_settings()


def build_public_path(path: Path) -> str:
    relative = path.relative_to(ROOT_DIR).as_posix()
    return f"/{relative}"


def public_url_to_local_path(url: str) -> Path | None:
    parsed_url = urlparse(url)

    path = parsed_url.path if parsed_url.scheme in {"http", "https"} else url
    if not path.startswith("/uploads/"):
        return None

    candidate = (ROOT_DIR / path.lstrip("/")).resolve()
    uploads_root = (ROOT_DIR / "uploads").resolve()
    if uploads_root not in candidate.parents and candidate != uploads_root:
        return None
    return candidate


async def save_upload_file(file: UploadFile) -> str:
    content = await file.read()
    validate_image_upload(file, len(content), settings.max_upload_size_bytes)

    extension = file.filename.rsplit(".", 1)[-1].lower()
    filename = f"{uuid.uuid4().hex}.{extension}"
    destination = USER_PHOTOS_DIR / filename

    async with aiofiles.open(destination, "wb") as out_file:
        await out_file.write(content)

    return build_public_path(destination)


async def save_result_image(image_bytes: bytes) -> str:
    filename = f"{uuid.uuid4().hex}.png"
    destination = RESULTS_DIR / filename

    async with aiofiles.open(destination, "wb") as out_file:
        await out_file.write(image_bytes)

    return build_public_path(destination)


def guess_media_type(path_or_url: str) -> str:
    guessed, _ = mimetypes.guess_type(path_or_url)
    return guessed or "image/png"
