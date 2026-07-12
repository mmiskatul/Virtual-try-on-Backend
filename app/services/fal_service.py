import asyncio
import base64
import os

import aiofiles
import fal_client
import httpx
from fastapi import HTTPException, status

from app.config import get_settings
from app.services.file_service import guess_media_type, public_url_to_local_path, save_result_image


def parse_size_to_index(size_str: str) -> float | None:
    size_str = size_str.upper().strip()
    
    # Try parsing as standard letter sizes
    sizes_order = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL", "5XL"]
    if size_str in sizes_order:
        return float(sizes_order.index(size_str))
        
    # Try parsing as numeric size (e.g. 28, 30, 32)
    cleaned = "".join(c for c in size_str if c.isdigit())
    if cleaned:
        try:
            return float(cleaned)
        except ValueError:
            pass
            
    return None

DEFAULT_TRYON_PROMPT = (
    "You are an advanced, expert virtual dressing assistant. Your task is to perform a high-fidelity, realistic virtual try-on by combining two images:\n"
    "- First Image (image_urls[0]): A photograph of a person (the user).\n"
    "- Second Image (image_urls[1]): A clean photograph of a garment (the clothing item).\n\n"
    "Instruction: Take the garment from the second image and dress the person from the first image in it, creating a single, perfectly realistic photograph. "
    "You must adjust the drape, silhouette, fabric folds, tension, shoulder seams, and overall length based on the sizing parameters (such as whether "
    "the selected garment size is larger, smaller, or matching the person's body size) to accurately represent size-wise fit variations (oversized, fitted, or standard)."
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
    materials: str | None = None,
    color: str | None = None,
    occasion: str | None = None,
    brand: str | None = None,
    care_instructions: str | None = None,
) -> tuple[str, str, dict]:
    if not settings.fal_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fal API key is not configured.",
        )

    user_bytes, user_media_type = await _read_image_bytes(user_image_url)
    garment_bytes, garment_media_type = await _read_image_bytes(garment_image_url)

    # Build garment metadata line with all collection details
    garment_meta_parts = [
        f"The garment to be placed is: {product_name}",
        f"Category: {product_category}",
        f"Target Audience: {product_gender}",
    ]
    if cloth_type:
        garment_meta_parts.append(f"Fabric/Cloth Type: {cloth_type}")
    if materials:
        garment_meta_parts.append(f"Material Composition: {materials}")
    if color:
        garment_meta_parts.append(f"Color: {color}")
    if fit_type:
        garment_meta_parts.append(f"Fit Style: {fit_type}")
    if brand:
        garment_meta_parts.append(f"Brand/Label: {brand}")
    if occasion:
        garment_meta_parts.append(f"Recommended Occasion: {occasion}")
    if care_instructions:
        garment_meta_parts.append(f"Care Instructions: {care_instructions}")
    if coverage:
        coverage_label = {"upper": "Upper Body", "lower": "Lower Body", "full": "Full Body", "accessory": "Accessory"}.get(coverage, coverage)
        garment_meta_parts.append(f"Body Coverage: {coverage_label}")
    garment_meta = ", ".join(garment_meta_parts) + "."

    # Category-specific draping guidelines
    category_lower = product_category.lower().strip()
    category_guidelines = ""
    if "pant" in category_lower or "trouser" in category_lower or "jean" in category_lower:
        category_guidelines = (
            "Ensure the trousers/pants sit naturally on the subject's waist or hips. The pant legs must drape smoothly along the legs, "
            "creating realistic crease patterns and folds at the knees and stacking naturally at the ankles or shoes, preserving the style's hemline."
        )
    elif "shirt" in category_lower or "polo" in category_lower or "blouse" in category_lower:
        category_guidelines = (
            "Ensure the collar, button placket, and neckline sit flat and align seamlessly with the subject's chest and neck structure. "
            "Sleeves must wrap naturally around the arms, showing realistic creasing at the elbows and cuffs."
        )
    elif "t-shirt" in category_lower or "tee" in category_lower:
        category_guidelines = (
            "Ensure the crew neck or V-neck collar sits flat and centered on the subject's collarbone. "
            "The shoulders must align naturally, showing soft folds around the underarms and chest."
        )
    elif "dress" in category_lower or "gown" in category_lower or "skirt" in category_lower:
        category_guidelines = (
            "Ensure the dress/gown flows elegantly from the torso, capturing the natural swing and drape of the fabric. "
            "The waistline must sit properly relative to the subject's body shape, and the flare and bottom hemline must look fluid and realistic."
        )
    elif "kurti" in category_lower or "kurtas" in category_lower:
        category_guidelines = (
            "Ensure the side slits (chaks) and hemline drape cleanly and straight. "
            "The sleeves and bodice must align correctly with the subject's frame, displaying clean patterns without stretch distortion."
        )

    # Fabric-specific rendering guidelines
    fabric_guidelines = ""
    fabric_ref = (cloth_type or materials or "").lower()
    if "linen" in fabric_ref:
        fabric_guidelines = "Render the linen fabric with its characteristic light creasing and organic, slightly textured look."
    elif "silk" in fabric_ref or "satin" in fabric_ref:
        fabric_guidelines = "Render the silk/satin fabric with smooth, fluid draping and soft, lustrous sheen highlights that capture the luxurious finish."
    elif "chiffon" in fabric_ref or "georgette" in fabric_ref:
        fabric_guidelines = "Render the chiffon fabric with its semi-sheer, lightweight, and floating texture, showing soft layered translucent drapes."
    elif "cotton" in fabric_ref or "pique" in fabric_ref:
        fabric_guidelines = "Render the cotton fabric with soft, matte folds and standard structured creases."
    elif "denim" in fabric_ref:
        fabric_guidelines = "Render the denim fabric with heavy, structured draping, prominent double-stitching details, and stiff creasing patterns."

    prompt_parts = [
        DEFAULT_TRYON_PROMPT,
        garment_meta,
        "Requirements for a perfect generation:",
        "1. PERSON PRESERVATION: Maintain the person's exact face, hair, eyes, skin tone, body shape, posture, hands, and original background from the first image. Keep their natural features, depth, and skin details intact so they look like a real person in a real photograph.",
        "2. GARMENT ALIGNMENT & CATEGORY: Fit the garment from the second image onto the person's body. Correctly replace the person's existing clothing. The neckline, collar style, and sleeve length of the garment must be preserved. " + category_guidelines,
        "3. REALISTIC FIT, TEXTURE & FOLDS: Drape the clothing naturally over the person's body shape. Generate realistic folds, creases, seams, shadows, and highlights that match the posture, lighting, and material properties (e.g. how silk drapes vs cotton or linen) of the first image. " + fabric_guidelines,
        "4. DETAIL PRESERVATION: Keep the colors, prints, patterns, logos, textures, buttons, zippers, and stitching of the garment from the second image completely intact without warping, blurring, or stretching.",
        "5. SEAMLESS BLENDING & BOUNDARIES: Ensure the edges of the clothing blend naturally with the person's skin (neck, wrists, waist) and the background without any graphical artifacts or blurry outlines.",
    ]
    if product_description:
        prompt_parts.append(f"Garment details: {product_description.strip()}.")
    if selected_size:
        size_map = {
            "XXS": "Double Extra Small (extremely fitted, skin-tight drape, minimum fabric volume, close contours)",
            "XS": "Extra Small (very fitted, tight-fitting drape, minimal fabric volume, close to body contours)",
            "S": "Small (slim-fit, tailored close to the body, clean modern drape, minor fabric volume)",
            "M": "Medium (standard fit, natural drape, balanced volume, perfect regular drape)",
            "L": "Large (relaxed fit, slightly loose, subtle fabric volume, casual drape with extra fold lines)",
            "XL": "Extra Large (loose silhouette, generous volume, soft cascading folds, baggy drape)",
            "XXL": "Double Extra Large (oversized, maximum fabric drape, drop shoulders, relaxed silhouette, long hem/sleeves)",
            "XXXL": "Triple Extra Large (extremely oversized, maximum fabric volume, very baggy drape, long cascading folds)",
            "3XL": "Triple Extra Large (extremely oversized, maximum fabric volume, very baggy drape, long cascading folds)",
            "4XL": "Quadruple Extra Large (massively oversized, very loose drape, maximum fabric folds)",
        }
        size_description = size_map.get(selected_size.upper(), selected_size)
        
        if user_body_size:
            body_desc = size_map.get(user_body_size.upper(), user_body_size)
            size_instruction = (
                f"SIZE INSTRUCTION: The user's standard body size is {user_body_size.upper()} ({body_desc}), "
                f"but they are trying on the garment in size {selected_size.upper()} ({size_description}). "
            )
            
            user_idx = parse_size_to_index(user_body_size)
            garment_idx = parse_size_to_index(selected_size)
            
            if user_idx is not None and garment_idx is not None:
                diff = garment_idx - user_idx
                if diff > 0:
                    size_instruction += (
                        f"Since the chosen garment size ({selected_size.upper()}) is LARGER than the user's standard body size ({user_body_size.upper()}), "
                        "you MUST render the garment with a loose, relaxed, and oversized fit. "
                        "Make the shoulder seams sit lower than the natural shoulder joints (drop shoulder effect), "
                        "add extra fabric volume and folds around the chest and torso, show sleeves extending longer and stack them slightly at the wrists, "
                        "and make the bottom hemline drape lower on the hips/thighs with visible sagging and low tension."
                    )
                elif diff < 0:
                    size_instruction += (
                        f"Since the chosen garment size ({selected_size.upper()}) is SMALLER than the user's standard body size ({user_body_size.upper()}), "
                        "you MUST render the garment with a tight, snug, and highly fitted silhouette. "
                        "The fabric must pull tightly across the chest, shoulders, and waist, showing prominent horizontal stretch tension lines and creases. "
                        "Make the shoulder seams sit high and close to the neck, show the sleeves fitting tight and ending higher on the forearm, "
                        "and make the bottom hemline sit higher on the waist/torso showing a shorter, high-tension fit."
                    )
                else:
                    size_instruction += (
                        "Since the chosen garment size matches the user's standard body size, "
                        "render the garment with a standard, clean, and perfectly tailored fit. "
                        "Ensure the shoulder seams sit exactly at the shoulder joints, the fabric follows the body contours naturally with minimal tension, "
                        "and the sleeve length and bottom hemline sit at standard, proportional positions."
                    )
            else:
                size_instruction += (
                    "Please adjust the drape, fabric volume, and fit silhouette to match this size. "
                    "Ensure fabric tension, folds, and overall fit visually depict the expected silhouette for this size."
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
