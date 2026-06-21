from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.models.product import ErrorResponse, ProductResponse
from app.utils.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _serialize_product(document: dict) -> ProductResponse:
    return ProductResponse(**{k: v for k, v in document.items() if k != "_id"})


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
