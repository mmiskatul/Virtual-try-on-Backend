from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.database import get_db
from app.models.product import ErrorResponse, ProductCreate, ProductResponse, ProductUpdate

router = APIRouter(prefix="/api/products", tags=["products"])


def _serialize_product(document: dict) -> ProductResponse:
    return ProductResponse(**{k: v for k, v in document.items() if k != "_id"})


@router.get("", response_model=list[ProductResponse])
async def list_products(db: AsyncIOMotorDatabase = Depends(get_db)) -> list[ProductResponse]:
    products = []
    cursor = db.products.find({"is_active": True}).sort("name", 1)
    async for document in cursor:
        products.append(_serialize_product(document))
    return products


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
) -> ProductResponse:
    document = product.model_dump(mode="json")
    try:
        await db.products.insert_one(document)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product id already exists.",
        ) from exc
    return ProductResponse(**document)


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    responses={404: {"model": ErrorResponse}},
)
async def update_product(
    product_id: str,
    product_update: ProductUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> ProductResponse:
    update_data = product_update.model_dump(exclude_unset=True, mode="json")
    if update_data:
        await db.products.update_one({"id": product_id}, {"$set": update_data})

    document = await db.products.find_one({"id": product_id})
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return _serialize_product(document)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
async def delete_product(product_id: str, db: AsyncIOMotorDatabase = Depends(get_db)) -> None:
    result = await db.products.delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
