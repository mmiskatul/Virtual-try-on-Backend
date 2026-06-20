import base64
import mimetypes
from asyncio import to_thread
import uuid
from pathlib import Path
from urllib.parse import urlparse

import aiofiles
import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, UploadFile, status

from app.config import PRODUCTS_DIR, RESULTS_DIR, ROOT_DIR, USER_PHOTOS_DIR, get_settings
from app.utils.validators import validate_image_upload

settings = get_settings()

if settings.cloudinary_configured:
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )


def build_public_path(path: Path) -> str:
    relative = path.relative_to(ROOT_DIR).as_posix()
    return f"/{relative}"


def is_local_upload_url(url: str) -> bool:
    parsed_url = urlparse(url)
    path = parsed_url.path if parsed_url.scheme in {"http", "https"} else url
    return path.startswith("/uploads/")


def public_url_to_local_path(url: str) -> Path | None:
    parsed_url = urlparse(url)

    path = parsed_url.path if parsed_url.scheme in {"http", "https"} else url
    if not is_local_upload_url(path):
        return None

    candidate = (ROOT_DIR / path.lstrip("/")).resolve()
    uploads_root = (ROOT_DIR / "uploads").resolve()
    if uploads_root not in candidate.parents and candidate != uploads_root:
        return None
    return candidate


async def _save_image_upload(file: UploadFile, destination_dir: Path) -> str:
    content = await file.read()
    validate_image_upload(file, len(content), settings.max_upload_size_bytes)

    if settings.cloudinary_configured:
        return await _upload_bytes_to_cloudinary(
            content,
            folder=f"{settings.cloudinary_folder}/{destination_dir.name}",
            original_filename=file.filename,
            content_type=file.content_type,
        )

    extension = file.filename.rsplit(".", 1)[-1].lower()
    filename = f"{uuid.uuid4().hex}.{extension}"
    destination = destination_dir / filename

    async with aiofiles.open(destination, "wb") as out_file:
        await out_file.write(content)

    return build_public_path(destination)


async def save_user_photo(file: UploadFile) -> str:
    return await _save_image_upload(file, USER_PHOTOS_DIR)


async def save_product_image(file: UploadFile) -> str:
    return await _save_image_upload(file, PRODUCTS_DIR)


async def save_result_image(image_bytes: bytes) -> str:
    if settings.cloudinary_configured:
        return await _upload_bytes_to_cloudinary(
            image_bytes,
            folder=f"{settings.cloudinary_folder}/results",
            original_filename=f"{uuid.uuid4().hex}.png",
            content_type="image/png",
        )

    filename = f"{uuid.uuid4().hex}.png"
    destination = RESULTS_DIR / filename

    async with aiofiles.open(destination, "wb") as out_file:
        await out_file.write(image_bytes)

    return build_public_path(destination)


def guess_media_type(path_or_url: str) -> str:
    guessed, _ = mimetypes.guess_type(path_or_url)
    return guessed or "image/png"


async def upload_local_image_to_cloudinary(
    file_path: Path,
    *,
    folder: str,
    public_id: str,
    overwrite: bool = True,
) -> str:
    if not settings.cloudinary_configured:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cloudinary is not configured.",
        )

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Local image file was not found: {file_path.name}",
        )

    extension = file_path.suffix.lstrip(".").lower() or "png"
    try:
        result = await to_thread(
            cloudinary.uploader.upload,
            str(file_path),
            folder=folder,
            public_id=public_id,
            resource_type="image",
            format=extension,
            overwrite=overwrite,
            unique_filename=False,
            use_filename=False,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cloudinary upload failed.",
        ) from exc

    secure_url = result.get("secure_url")
    if not secure_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cloudinary upload did not return a URL.",
        )
    return secure_url


async def _upload_bytes_to_cloudinary(
    content: bytes,
    *,
    folder: str,
    original_filename: str,
    content_type: str | None,
) -> str:
    if not settings.cloudinary_configured:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cloudinary is not configured.",
        )

    extension = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else "png"
    public_id = f"{uuid.uuid4().hex}"
    data_uri = f"data:{content_type or guess_media_type(original_filename)};base64,"
    data_uri += base64.b64encode(content).decode("utf-8")
    try:
        result = await to_thread(
            cloudinary.uploader.upload,
            data_uri,
            folder=folder,
            public_id=public_id,
            resource_type="image",
            format=extension,
            overwrite=False,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cloudinary upload failed.",
        ) from exc

    secure_url = result.get("secure_url")
    if not secure_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cloudinary upload did not return a URL.",
        )
    return secure_url
