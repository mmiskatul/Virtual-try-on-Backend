from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.models.product import ErrorResponse
from app.models.tryon import TryOnGenerateRequest, TryOnResultResponse
from app.services.fal_service import generate_virtual_tryon
from app.utils.auth import require_admin

router = APIRouter(prefix="/api/tryon", tags=["try-on"])


def _serialize_tryon(document: dict) -> TryOnResultResponse:
    return TryOnResultResponse(
        id=str(document["_id"]),
        user_image_url=document["user_image_url"],
        product_id=document["product_id"],
        product_name=document["product_name"],
        garment_image_url=document["garment_image_url"],
        result_image_url=document["result_image_url"],
        prompt=document["prompt"],
        image_details=document.get("image_details"),
        created_at=document["created_at"],
    )


@router.post(
    "/generate",
    response_model=TryOnResultResponse,
    responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
async def generate_tryon(
    payload: TryOnGenerateRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> TryOnResultResponse:
    product = await db.products.find_one({"id": payload.product_id, "is_active": True})
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    result_image_url, final_prompt, image_details = await generate_virtual_tryon(
        user_image_url=payload.user_image_url,
        garment_image_url=product["image_url"],
        product_name=product["name"],
        product_category=product["category"],
        product_gender=product["gender"],
        product_description=product.get("description"),
        cloth_type=product.get("cloth_type"),
        fit_type=product.get("fit_type"),
        coverage=product.get("coverage"),
        selected_size=payload.selected_size,
        prompt_optional=payload.prompt_optional,
    )

    document = {
        "user_image_url": payload.user_image_url,
        "product_id": product["id"],
        "product_name": product["name"],
        "garment_image_url": product["image_url"],
        "result_image_url": result_image_url,
        "prompt": final_prompt,
        "image_details": image_details,
        "created_at": datetime.now(timezone.utc),
    }
    insert_result = await db.tryon_results.insert_one(document)
    document["_id"] = insert_result.inserted_id
    return _serialize_tryon(document)


@router.get("/history", response_model=list[TryOnResultResponse])
async def list_tryon_history(db: AsyncIOMotorDatabase = Depends(get_db)) -> list[TryOnResultResponse]:
    results = []
    cursor = db.tryon_results.find().sort("created_at", -1)
    async for document in cursor:
        results.append(_serialize_tryon(document))
    return results


@router.get(
    "/history/{history_id}",
    response_model=TryOnResultResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_tryon_history(
    history_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> TryOnResultResponse:
    if not ObjectId.is_valid(history_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Try-on result not found.")

    document = await db.tryon_results.find_one({"_id": ObjectId(history_id)})
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Try-on result not found.")
    return _serialize_tryon(document)


@router.delete(
    "/history/{history_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
async def delete_tryon_history(
    history_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: str = Depends(require_admin),
) -> None:
    if not ObjectId.is_valid(history_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Try-on result not found.")

    result = await db.tryon_results.delete_one({"_id": ObjectId(history_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Try-on result not found.")
