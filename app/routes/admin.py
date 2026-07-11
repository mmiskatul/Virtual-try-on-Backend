from datetime import datetime, time, timedelta, timezone
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.models.admin import (
    AdminAnalyticsResponse,
    AdminCategoryPerformance,
    AdminDailyMetric,
    AdminStudioSettingsResponse,
    AdminStudioSettingsUpdate,
    AdminTopProduct,
)
from app.models.product import (
    AdminDashboardProduct,
    AdminDashboardSummary,
    ErrorResponse,
    PaginatedProducts,
    ProductResponse,
)
from app.utils.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

DEFAULT_STUDIO_SETTINGS = AdminStudioSettingsUpdate().model_dump()


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

    today = datetime.now(timezone.utc).date()
    seven_day_counts = []
    for days_ago in range(6, -1, -1):
        day = today - timedelta(days=days_ago)
        day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        count = await db.tryon_results.count_documents(
            {"created_at": {"$gte": day_start, "$lt": day_end}}
        )
        seven_day_counts.append({"date": day.isoformat(), "count": count})

    tryons_today = seven_day_counts[-1]["count"]

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
        tryons_today=tryons_today,
        tryons_last_7_days=seven_day_counts,
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


@router.get("/products/paged", response_model=PaginatedProducts)
async def list_all_products_paged(
    q: str = Query(default="", max_length=120),
    status_filter: str = Query(default="all", alias="status", pattern="^(all|live|inactive)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: None = Depends(require_admin),
) -> PaginatedProducts:
    filters: dict = {}
    if status_filter == "live":
        filters["is_active"] = True
    elif status_filter == "inactive":
        filters["is_active"] = False
    if q.strip():
        filters["$or"] = [
            {"name": {"$regex": q.strip(), "$options": "i"}},
            {"id": {"$regex": q.strip(), "$options": "i"}},
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


@router.get("/analytics", response_model=AdminAnalyticsResponse)
async def get_admin_analytics(
    days: int = 30,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: str = Depends(require_admin),
) -> AdminAnalyticsResponse:
    days = min(max(days, 7), 90)
    period_end = datetime.now(timezone.utc)
    first_day = period_end.date() - timedelta(days=days - 1)
    period_start = datetime.combine(first_day, time.min, tzinfo=timezone.utc)
    previous_start = period_start - timedelta(days=days)

    total_tryons = await db.tryon_results.count_documents({})
    period_tryons = await db.tryon_results.count_documents(
        {"created_at": {"$gte": period_start, "$lte": period_end}}
    )
    previous_period_tryons = await db.tryon_results.count_documents(
        {"created_at": {"$gte": previous_start, "$lt": period_start}}
    )
    total_products = await db.products.count_documents({})
    active_products = await db.products.count_documents({"is_active": True})

    if previous_period_tryons:
        period_change_percent = round(
            ((period_tryons - previous_period_tryons) / previous_period_tryons) * 100,
            1,
        )
    else:
        period_change_percent = None

    daily_lookup: dict[str, int] = {}
    daily_cursor = db.tryon_results.aggregate(
        [
            {"$match": {"created_at": {"$gte": period_start, "$lte": period_end}}},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$created_at",
                            "timezone": "UTC",
                        }
                    },
                    "count": {"$sum": 1},
                }
            },
        ]
    )
    async for document in daily_cursor:
        daily_lookup[str(document["_id"])] = int(document.get("count", 0))

    daily_tryons = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        key = day.isoformat()
        daily_tryons.append(AdminDailyMetric(date=key, count=daily_lookup.get(key, 0)))

    product_counts: dict[str, int] = {}
    product_count_cursor = db.tryon_results.aggregate(
        [
            {"$match": {"created_at": {"$gte": period_start, "$lte": period_end}}},
            {"$group": {"_id": "$product_id", "count": {"$sum": 1}}},
        ]
    )
    async for document in product_count_cursor:
        if isinstance(document.get("_id"), str):
            product_counts[document["_id"]] = int(document.get("count", 0))

    products_by_id: dict[str, dict] = {}
    async for document in db.products.find({"id": {"$in": list(product_counts)}}):
        products_by_id[document["id"]] = document

    category_counts: dict[str, int] = {}
    top_products = []
    for product_id, count in product_counts.items():
        product = products_by_id.get(product_id)
        if not product:
            continue
        category = str(product.get("category", "uncategorized"))
        category_counts[category] = category_counts.get(category, 0) + count
        top_products.append(
            AdminTopProduct(
                id=product_id,
                name=str(product.get("name", "Unknown product")),
                category=category,
                image_url=str(product.get("image_url", "")),
                try_on_count=count,
            )
        )
    top_products.sort(key=lambda item: (-item.try_on_count, item.name))

    category_performance = [
        AdminCategoryPerformance(
            category=category,
            try_on_count=count,
            percentage=round((count / period_tryons) * 100, 1) if period_tryons else 0,
        )
        for category, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    result_storage_bytes = 0
    results_with_metadata = 0
    metadata_cursor = db.tryon_results.find(
        {"created_at": {"$gte": period_start, "$lte": period_end}},
        {"image_details.file_size": 1},
    )
    async for document in metadata_cursor:
        file_size = (document.get("image_details") or {}).get("file_size")
        if isinstance(file_size, int) and file_size >= 0:
            result_storage_bytes += file_size
            results_with_metadata += 1

    latest_document = await db.tryon_results.find_one(
        {},
        {"created_at": 1},
        sort=[("created_at", -1)],
    )

    return AdminAnalyticsResponse(
        period_days=days,
        period_start=period_start,
        period_end=period_end,
        total_tryons=total_tryons,
        period_tryons=period_tryons,
        previous_period_tryons=previous_period_tryons,
        period_change_percent=period_change_percent,
        total_products=total_products,
        active_products=active_products,
        unique_products_tried=len(product_counts),
        result_storage_bytes=result_storage_bytes,
        results_with_metadata=results_with_metadata,
        latest_tryon_at=latest_document.get("created_at") if latest_document else None,
        daily_tryons=daily_tryons,
        category_performance=category_performance,
        top_products=top_products[:5],
    )


async def _list_administrators(db: AsyncIOMotorDatabase) -> list[dict]:
    administrators = []
    cursor = db.admin_users.find(
        {},
        {"username": 1, "is_active": 1, "last_login_at": 1},
    ).sort("username", 1)
    async for document in cursor:
        administrators.append(
            {
                "username": document["username"],
                "is_active": bool(document.get("is_active", False)),
                "last_login_at": document.get("last_login_at"),
            }
        )
    return administrators


@router.get("/settings", response_model=AdminStudioSettingsResponse)
async def get_admin_settings(
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: str = Depends(require_admin),
) -> AdminStudioSettingsResponse:
    document = await db.admin_settings.find_one({"key": "studio"}) or {}
    values = {**DEFAULT_STUDIO_SETTINGS, **document}
    return AdminStudioSettingsResponse(
        **values,
        administrators=await _list_administrators(db),
    )


@router.put("/settings", response_model=AdminStudioSettingsResponse)
async def update_admin_settings(
    payload: AdminStudioSettingsUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    username: str = Depends(require_admin),
) -> AdminStudioSettingsResponse:
    updated_at = datetime.now(timezone.utc)
    values = payload.model_dump()
    await db.admin_settings.update_one(
        {"key": "studio"},
        {
            "$set": {
                **values,
                "updated_at": updated_at,
                "updated_by": username,
            },
            "$setOnInsert": {"key": "studio"},
        },
        upsert=True,
    )
    return AdminStudioSettingsResponse(
        **values,
        updated_at=updated_at,
        updated_by=username,
        administrators=await _list_administrators(db),
    )
