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
    "You are an expert virtual dressing assistant. Your task is to perform a high-fidelity, realistic virtual try-on by combining two images:\n"
    "- First Image (image_urls[0]): A photograph of a person (the user).\n"
    "- Second Image (image_urls[1]): A clean photograph of a garment (the clothing item).\n\n"
    "Instruction: Take the garment from the second image and dress the person from the first image in it, creating a single, perfectly realistic photograph."
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
    cloth_type: str | None = None,
    fit_type: str | None = None,
    coverage: str | None = None,
    selected_size: str | None = None,
    user_body_size: str | None = None,
    product_size_details: str | None = None,
    user_size_details: str | None = None,
    prompt_optional: str | None = None,
) -> tuple[str, str, dict]:
    if not settings.fal_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fal API key is not configured.",
        )

    user_bytes, user_media_type = await _read_image_bytes(user_image_url)
    garment_bytes, garment_media_type = await _read_image_bytes(garment_image_url)

    # Build garment metadata line
    garment_meta_parts = [
        f"The garment to be placed is: {product_name}",
        f"Category: {product_category}",
        f"Target Audience: {product_gender}",
    ]
    if cloth_type:
        garment_meta_parts.append(f"Fabric: {cloth_type}")
    if fit_type:
        garment_meta_parts.append(f"Fit: {fit_type}")
    if coverage:
        coverage_label = {"upper": "Upper Body", "lower": "Lower Body", "full": "Full Body", "accessory": "Accessory"}.get(coverage, coverage)
        garment_meta_parts.append(f"Coverage: {coverage_label}")
    garment_meta = ", ".join(garment_meta_parts) + "."

    prompt_parts = [
        DEFAULT_TRYON_PROMPT,
        garment_meta,
        "Requirements for a perfect generation:",
        "1. PERSON PRESERVATION: Maintain the person's exact face, hair, eyes, skin tone, body shape, posture, hands, and original background from the first image. Do not alter their identity or introduce any structural deformities or extra limbs.",
        "2. GARMENT ALIGNMENT & CATEGORY: Fit the garment from the second image onto the person's body. Correctly replace the person's existing clothing (e.g. swap the upper-body clothing for a shirt/t-shirt/jacket, or lower-body clothing for pants/skirts). The neckline, collar style, and sleeve length of the garment must be preserved.",
        "3. REALISTIC FIT & FOLDS: Drape the clothing naturally over the person's body shape. Generate realistic folds, creases, seams, shadows, and highlights that match the posture and lighting of the first image.",
        "4. DETAIL PRESERVATION: Keep the colors, prints, patterns, logos, textures, buttons, zippers, and stitching of the garment from the second image completely intact without warping, blurring, or stretching.",
        "5. SEAMLESS BLENDING: Ensure the edges of the clothing blend naturally with the person's skin (neck, wrists, waist) and the background without any graphical artifacts or blurry outlines.",
    ]
    if product_description:
        prompt_parts.append(f"Garment details: {product_description.strip()}.")
    if selected_size:
        size_map = {
            "XS": "extra small — very fitted, minimal fabric volume",
            "S": "small — close to the body with a tailored feel",
            "M": "medium — standard fit with natural drape",
            "L": "large — relaxed fit with slightly more fabric volume",
            "XL": "extra large — loose with generous drape",
            "XXL": "double extra large — oversized silhouette with maximum drape",
        }
        size_description = size_map.get(selected_size.upper(), selected_size)
        
        if user_body_size:
            body_desc = size_map.get(user_body_size.upper(), user_body_size)
            size_instruction = (
                f"SIZE INSTRUCTION: The user's normal body size is {user_body_size.upper()} ({body_desc}), "
                f"but they have chosen to try on the garment in size {selected_size.upper()} ({size_description}). "
            )
            
            sizes_order = ["XS", "S", "M", "L", "XL", "XXL"]
            try:
                user_idx = sizes_order.index(user_body_size.upper())
                garment_idx = sizes_order.index(selected_size.upper())
                diff = garment_idx - user_idx
                
                if diff > 0:
                    size_instruction += (
                        f"Since the chosen garment size is {diff} size(s) larger than the user's standard body size, "
                        "carefully drape the garment with an oversized, looser, and more relaxed volume. "
                        "Show the garment fitting longer on the body and sleeves, with loose fabric folds and lower tension."
                    )
                elif diff < 0:
                    size_instruction += (
                        f"Since the chosen garment size is {abs(diff)} size(s) smaller than the user's standard body size, "
                        "carefully drape the garment with a tight, snug, and very fitted look. "
                        "Show the garment fitting shorter, with stretched fabric tension and minimal loose folds."
                    )
                else:
                    size_instruction += (
                        "Since the chosen garment size matches the user's standard body size, "
                        "drape the garment with a normal, standard, and perfectly tailored fit."
                    )
            except ValueError:
                size_instruction += (
                    "Adjust the garment's drape, volume, and silhouette to match this size on the person's body. "
                    "Ensure fabric tension, folds, and overall fit visually match the expected silhouette for this size."
                )
        else:
            size_instruction = (
                f"SIZE INSTRUCTION: The user has selected size {selected_size.upper()} ({size_description}). "
                "Adjust the garment's drape, volume, and silhouette to match this size on the person's body. "
                "Ensure fabric tension, folds, and overall fit visually match the expected silhouette for this size."
            )
            
        if product_size_details:
            size_instruction += f" Garment sizing specifications: {product_size_details.strip()}."
        if user_size_details:
            size_instruction += (
                f" The user's body size/measurements details: {user_size_details.strip()}. "
                "Carefully adjust the fit and length based on these details. For example, if the selected garment size is relatively "
                "larger than the user's size/measurements, or if they are shorter/taller, show the garment fitting longer, looser, or oversized accordingly."
            )
        prompt_parts.append(size_instruction)
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
