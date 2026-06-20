import base64
from pathlib import Path

import aiofiles
import httpx
from fastapi import HTTPException, status
from openai import AsyncOpenAI, OpenAIError

from app.config import get_settings
from app.services.file_service import guess_media_type, public_url_to_local_path, save_result_image

DEFAULT_TRYON_PROMPT = (
    "Replace only the clothing on the person with the selected garment. Preserve the person's face, "
    "body shape, pose, skin tone, lighting, camera angle, and background. Make the garment look "
    "naturally worn, fitted, realistic, and consistent with the original image. Do not change face, "
    "hair, hands, background, or image style."
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


def _extract_image_base64(response: object) -> str:
    output = getattr(response, "output", None) or []
    for item in output:
        if getattr(item, "type", None) == "image_generation_call":
            result = getattr(item, "result", None)
            if result:
                return result

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="OpenAI did not return an image.",
    )


async def generate_virtual_tryon(
    *,
    user_image_url: str,
    garment_image_url: str,
    prompt_optional: str | None = None,
) -> tuple[str, str]:
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OpenAI API key is not configured.",
        )

    user_bytes, user_media_type = await _read_image_bytes(user_image_url)
    garment_bytes, garment_media_type = await _read_image_bytes(garment_image_url)

    prompt = DEFAULT_TRYON_PROMPT
    if prompt_optional:
        prompt = f"{prompt}\n\nAdditional style instruction: {prompt_optional.strip()}"

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.responses.create(
            model=settings.openai_model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_text",
                            "text": "First image is the person. Second image is the selected garment.",
                        },
                        {
                            "type": "input_image",
                            "image_url": _to_data_url(user_bytes, user_media_type),
                        },
                        {
                            "type": "input_image",
                            "image_url": _to_data_url(garment_bytes, garment_media_type),
                        },
                    ],
                }
            ],
            tools=[{"type": "image_generation"}],
        )
    except OpenAIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Image generation failed. Please try again.",
        ) from exc

    image_base64 = _extract_image_base64(response)
    image_bytes = base64.b64decode(image_base64)
    result_url = await save_result_image(image_bytes)
    return result_url, prompt
