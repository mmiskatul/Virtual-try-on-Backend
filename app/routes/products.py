from bson import ObjectId
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from math import ceil
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.database import get_db
from app.models.product import ErrorResponse, PaginatedProducts, ProductCreate, ProductResponse, ProductUpdate
from app.utils.auth import require_admin
from app.services.file_service import public_url_to_local_path
from asyncio import to_thread

router = APIRouter(prefix="/api/products", tags=["products"])


async def _audit(db: AsyncIOMotorDatabase, username: str, action: str, product_id: str) -> None:
    await db.admin_audit_logs.insert_one(
        {"username": username, "action": action, "product_id": product_id, "created_at": datetime.now(timezone.utc)}
    )


async def _remove_local_image(url: str | None) -> None:
    path = public_url_to_local_path(url or "")
    if path and path.exists():
        await to_thread(path.unlink)


def _serialize_product(document: dict) -> ProductResponse:
    return ProductResponse(**{k: v for k, v in document.items() if k != "_id"})


@router.get("", response_model=list[ProductResponse])
async def list_products(db: AsyncIOMotorDatabase = Depends(get_db)) -> list[ProductResponse]:
    products = []
    cursor = db.products.find({"is_active": True}).sort("name", 1)
    async for document in cursor:
        products.append(_serialize_product(document))
    return products


@router.get("/paged", response_model=PaginatedProducts)
async def list_products_paged(
    q: str = Query(default="", max_length=120),
    category: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> PaginatedProducts:
    filters: dict = {"is_active": True}
    if category:
        filters["category"] = category.strip().lower()
    if q.strip():
        filters["$or"] = [
            {"name": {"$regex": q.strip(), "$options": "i"}},
            {"category": {"$regex": q.strip(), "$options": "i"}},
        ]
    total = await db.products.count_documents(filters)
    cursor = db.products.find(filters).sort("name", 1).skip((page - 1) * page_size).limit(page_size)
    items = [_serialize_product(document) async for document in cursor]
    return PaginatedProducts(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
    )


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_product(product_id: str, db: AsyncIOMotorDatabase = Depends(get_db)) -> ProductResponse:
    document = await db.products.find_one({"id": product_id})
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return _serialize_product(document)


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
async def create_product(
    product: ProductCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    username: str = Depends(require_admin),
) -> ProductResponse:
    document = product.model_dump(mode="json")
    doc_id = ObjectId()
    document["_id"] = doc_id
    document["id"] = str(doc_id)
    try:
        await db.products.insert_one(document)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product id already exists.",
        ) from exc
    await _audit(db, username, "product.created", str(document["id"]))
    return _serialize_product(document)


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    responses={404: {"model": ErrorResponse}},
)
async def update_product(
    product_id: str,
    product_update: ProductUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    username: str = Depends(require_admin),
) -> ProductResponse:
    existing = await db.products.find_one({"id": product_id})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    update_data = product_update.model_dump(exclude_unset=True, mode="json")
    if update_data:
        await db.products.update_one({"id": product_id}, {"$set": update_data})

    document = await db.products.find_one({"id": product_id})
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    if "image_url" in update_data and update_data["image_url"] != existing.get("image_url"):
        await _remove_local_image(str(existing.get("image_url", "")))
    if update_data:
        await _audit(db, username, "product.updated", product_id)
    return _serialize_product(document)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
async def delete_product(
    product_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    username: str = Depends(require_admin),
) -> None:
    existing = await db.products.find_one({"id": product_id})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    result = await db.products.delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    await _remove_local_image(str(existing.get("image_url", "")))
    await _audit(db, username, "product.deleted", product_id)
