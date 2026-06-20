from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT_DIR, ensure_upload_dirs, get_settings
from app.database import close_mongo_connection, connect_to_mongo, get_database
from app.routes import auth, products, tryon, uploads
from app.utils.passwords import hash_password

settings = get_settings()

SEED_PRODUCTS = [
    {
        "id": "linen-oxford-shirt",
        "name": "Linen Oxford Shirt",
        "gender": "male",
        "category": "shirt",
        "image_url": "/uploads/products/p1.jpg",
        "price": 89.0,
        "description": "A breathable linen oxford shirt for polished casual styling.",
        "is_active": True,
    },
    {
        "id": "essential-black-tee",
        "name": "Essential Black Tee",
        "gender": "unisex",
        "category": "t-shirt",
        "image_url": "/uploads/products/p2.jpg",
        "price": 39.0,
        "description": "A minimal everyday black t-shirt with a clean crew neckline.",
        "is_active": True,
    },
    {
        "id": "camel-tailored-trouser",
        "name": "Camel Tailored Trouser",
        "gender": "male",
        "category": "pant",
        "image_url": "/uploads/products/p3.jpg",
        "price": 129.0,
        "description": "Tailored camel trousers with a structured modern fit.",
        "is_active": True,
    },
    {
        "id": "navy-pique-polo",
        "name": "Navy Pique Polo",
        "gender": "male",
        "category": "t-shirt",
        "image_url": "/uploads/products/p8.jpg",
        "price": 59.0,
        "description": "A refined navy pique polo for smart casual looks.",
        "is_active": True,
    },
    {
        "id": "rose-garden-kurti",
        "name": "Rose Garden Kurti",
        "gender": "female",
        "category": "kurti",
        "image_url": "/uploads/products/p4.jpg",
        "price": 79.0,
        "description": "A floral kurti with soft drape and comfortable everyday styling.",
        "is_active": True,
    },
    {
        "id": "midnight-chiffon-dress",
        "name": "Midnight Chiffon Dress",
        "gender": "female",
        "category": "dress",
        "image_url": "/uploads/products/p5.jpg",
        "price": 219.0,
        "description": "An elegant midnight chiffon dress for evening occasions.",
        "is_active": True,
    },
    {
        "id": "ivory-silk-shirt",
        "name": "Ivory Silk Shirt",
        "gender": "female",
        "category": "shirt",
        "image_url": "/uploads/products/p6.jpg",
        "price": 99.0,
        "description": "A smooth ivory silk shirt with a relaxed premium silhouette.",
        "is_active": True,
    },
    {
        "id": "sand-tailored-pant",
        "name": "Sand Tailored Pant",
        "gender": "unisex",
        "category": "pant",
        "image_url": "/uploads/products/p7.jpg",
        "price": 109.0,
        "description": "Neutral tailored pants designed for versatile outfit pairing.",
        "is_active": True,
    },
]


async def seed_products() -> None:
    db = get_database()
    for product in SEED_PRODUCTS:
        await db.products.update_one({"id": product["id"]}, {"$set": product}, upsert=True)


async def seed_admin_user() -> None:
    if not settings.admin_username or not settings.admin_password:
        return

    db = get_database()
    password_hash, salt = hash_password(settings.admin_password)
    await db.admin_users.update_one(
        {"username": settings.admin_username},
        {
            "$set": {
                "username": settings.admin_username,
                "password_hash": password_hash,
                "salt": salt,
                "is_active": True,
            }
        },
        upsert=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_upload_dirs()
    await connect_to_mongo()
    await seed_admin_user()
    await seed_products()
    yield
    await close_mongo_connection()


app = FastAPI(
    title="AI Virtual Try-On API",
    description="FastAPI backend for product browsing, user photo uploads, and AI virtual try-on generation.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=ROOT_DIR / "uploads"), name="uploads")

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(uploads.router)
app.include_router(tryon.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
