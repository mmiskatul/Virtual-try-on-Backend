import asyncio
import base64
import os

import aiofiles
import fal_client
import httpx
from fastapi import HTTPException, status

from app.config import get_settings
from app.services.file_service import guess_media_type, public_url_to_local_path, save_result_image

DEFAULT_TRYON_PROMPT = (
    "Create a realistic virtual try-on where this person (first image) is wearing this garment (second image)."
)

settings = get_settings()


async def _read_image_bytes(image_url: str) -> tuple[bytes, str]:
    local_path = public_url_to_local_path(image_url)
    if local_path is not None:
        if not local_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Local image file was not found.",
            )
        async with aiofiles.open(local_path, "rb") as image_file:
            return await image_file.read(), guess_media_type(str(local_path))

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(image_url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not fetch image URL.",
            ) from exc

    content_type = response.headers.get("content-type", "").split(";")[0] or guess_media_type(image_url)
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image URL must point to an image file.",
        )
    return response.content, content_type


def _to_data_url(image_bytes: bytes, media_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{media_type};base64,{encoded}"


def _extract_output_image(payload: dict) -> dict:
    images = payload.get("images") or []
    if not images:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Fal did not return a generated image.",
        )

    image = images[0]
    image_url = image.get("url")
    if not image_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Fal did not return a generated image URL.",
        )
    return image


async def _download_generated_image(image_url: str) -> tuple[bytes, str | None]:
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.get(image_url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not download the generated image from Fal.",
            ) from exc

    content_type = response.headers.get("content-type", "").split(";")[0] or None
    return response.content, content_type


def _run_fal_subscription(arguments: dict) -> dict:
    os.environ["FAL_KEY"] = settings.fal_key

    def on_queue_update(update: object) -> None:
        if isinstance(update, fal_client.InProgress):
            for log in update.logs:
                message = log.get("message")
                if message:
                    print(message)

    return fal_client.subscribe(
        settings.fal_model,
        arguments=arguments,
        with_logs=True,
        on_queue_update=on_queue_update,
    )


async def generate_virtual_tryon(
    *,
    user_image_url: str,
    garment_image_url: str,
    product_name: str,
    product_category: str,
    product_gender: str,
    product_description: str | None = None,
    prompt_optional: str | None = None,
) -> tuple[str, str, dict]:
    if not settings.fal_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fal API key is not configured.",
        )

    user_bytes, user_media_type = await _read_image_bytes(user_image_url)
    garment_bytes, garment_media_type = await _read_image_bytes(garment_image_url)

    prompt_parts = [
        DEFAULT_TRYON_PROMPT,
        f"The garment is a {product_name} (Category: {product_category}, Style audience: {product_gender}).",
        "Maintain the person's identity, facial features, pose, body shape, and background from the first image exactly.",
        "Drape the garment naturally on the person's body, ensuring folds, shadows, and fit look realistic.",
        "Preserve the textures, patterns, colors, and specific details of the garment from the second image.",
    ]
    if product_description:
        prompt_parts.append(f"Garment details: {product_description.strip()}.")
    if prompt_optional:
        prompt_parts.append(f"Additional user instructions: {prompt_optional.strip()}.")
    prompt = " ".join(prompt_parts)

    arguments = {
        "image_urls": [
            _to_data_url(user_bytes, user_media_type),
            _to_data_url(garment_bytes, garment_media_type),
        ],
        "prompt": prompt,
    }

    try:
        result_payload = await asyncio.to_thread(_run_fal_subscription, arguments)
    except Exception as exc:
        detail = getattr(exc, "message", None) or str(exc) or "Image generation failed. Please try again."
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        ) from exc

    output_image = _extract_output_image(result_payload)
    source_result_url = output_image["url"]
    image_bytes, downloaded_content_type = await _download_generated_image(source_result_url)
    result_url = await save_result_image(image_bytes)

    image_details = {
        "provider": "fal",
        "model": settings.fal_model,
        "request_id": result_payload.get("request_id"),
        "source_result_url": source_result_url,
        "content_type": output_image.get("content_type") or downloaded_content_type,
        "file_name": output_image.get("file_name"),
        "file_size": output_image.get("file_size"),
        "width": output_image.get("width"),
        "height": output_image.get("height"),
        "seed": result_payload.get("seed"),
    }

    return result_url, prompt, image_details
