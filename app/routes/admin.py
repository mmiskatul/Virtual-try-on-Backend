from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.models.product import (
    AdminDashboardProduct,
    AdminDashboardSummary,
    ErrorResponse,
    ProductResponse,
)
from app.utils.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _serialize_product(document: dict) -> ProductResponse:
    return ProductResponse(**{k: v for k, v in document.items() if k != "_id"})


def _serialize_recent_tryon(document: dict):
    return {
        "id": str(document["_id"]),
        "product_id": document["product_id"],
        "product_name": document["product_name"],
        "user_image_url": document["user_image_url"],
        "garment_image_url": document["garment_image_url"],
        "result_image_url": document["result_image_url"],
        "created_at": document["created_at"],
    }


@router.get(
    "/dashboard",
    response_model=AdminDashboardSummary,
)
async def get_admin_dashboard(
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: None = Depends(require_admin),
) -> AdminDashboardSummary:
    total_products = await db.products.count_documents({})
    active_products = await db.products.count_documents({"is_active": True})
    inactive_products = max(0, total_products - active_products)
    total_tryons = await db.tryon_results.count_documents({})

    tryon_counts: dict[str, dict[str, object]] = {}
    cursor = db.tryon_results.aggregate(
        [
            {
                "$group": {
                    "_id": "$product_id",
                    "count": {"$sum": 1},
                    "last_try_on_at": {"$max": "$created_at"},
                }
            },
        ]
    )
    async for document in cursor:
        product_id = document.get("_id")
        if isinstance(product_id, str):
            tryon_counts[product_id] = {
                "count": int(document.get("count", 0)),
                "last_try_on_at": document.get("last_try_on_at"),
            }

    products = []
    top_product_name: str | None = None
    top_product_try_on_count = 0
    product_cursor = db.products.find().sort("name", 1)
    async for document in product_cursor:
        serialized = _serialize_product(document)
        stats = tryon_counts.get(serialized.id, {})
        try_on_count = int(stats.get("count", 0))
        if try_on_count > top_product_try_on_count:
            top_product_try_on_count = try_on_count
            top_product_name = serialized.name
        products.append(
            AdminDashboardProduct(
                **serialized.model_dump(),
                try_on_count=try_on_count,
                last_try_on_at=stats.get("last_try_on_at"),
            )
        )

    recent_products = []
    recent_cursor = db.products.find().sort("_id", -1).limit(4)
    async for document in recent_cursor:
        recent_products.append(_serialize_product(document))

    recent_tryons = []
    recent_tryon_cursor = db.tryon_results.find().sort("created_at", -1).limit(6)
    async for document in recent_tryon_cursor:
        recent_tryons.append(_serialize_recent_tryon(document))

    return AdminDashboardSummary(
        total_products=total_products,
        active_products=active_products,
        inactive_products=inactive_products,
        total_tryons=total_tryons,
        top_product_name=top_product_name,
        top_product_try_on_count=top_product_try_on_count,
        recent_products=recent_products,
        products=products,
        recent_tryons=recent_tryons,
    )


@router.get(
    "/products",
    response_model=list[ProductResponse],
)
async def list_all_products(
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: None = Depends(require_admin),
) -> list[ProductResponse]:
    products = []
    cursor = db.products.find().sort("name", 1)
    async for document in cursor:
        products.append(_serialize_product(document))
    return products


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_admin_product(
    product_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: None = Depends(require_admin),
) -> ProductResponse:
    document = await db.products.find_one({"id": product_id})
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return _serialize_product(document)
