from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.database import get_db
from app.models.category import CategoryCreate, CategoryResponse
from app.models.product import ErrorResponse
from app.utils.auth import require_admin
from app.utils.categories import format_category_label, normalize_category_value

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
async def list_categories(db: AsyncIOMotorDatabase = Depends(get_db)) -> list[CategoryResponse]:
    categories: list[CategoryResponse] = []
    cursor = db.categories.find({"is_active": True}).sort("label", 1)
    async for document in cursor:
        categories.append(
            CategoryResponse(
                value=str(document.get("value", "")),
                label=str(document.get("label", document.get("value", ""))),
            )
        )
    return categories


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
async def create_category(
    payload: CategoryCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: None = Depends(require_admin),
) -> CategoryResponse:
    value = normalize_category_value(payload.name)
    if not value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category name is required.",
        )

    label = format_category_label(value)
    document = {"value": value, "label": label, "is_active": True}

    try:
        await db.categories.insert_one(document)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category already exists.",
        ) from exc

    return CategoryResponse(value=value, label=label)
