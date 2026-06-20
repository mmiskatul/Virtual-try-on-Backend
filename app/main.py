from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT_DIR, ensure_upload_dirs, get_settings
from app.database import close_mongo_connection, connect_to_mongo, get_database
from app.routes import products, tryon, uploads

settings = get_settings()

SEED_PRODUCTS = [
    {
        "id": "linen-oxford-shirt",
        "name": "Linen Oxford Shirt",
        "gender": "male",
        "category": "shirt",
        "image_url": "https://images.unsplash.com/photo-1598033129183-c4f50c736f10?w=900&auto=format&fit=crop",
        "price": 89.0,
        "description": "A breathable linen oxford shirt for polished casual styling.",
        "is_active": True,
    },
    {
        "id": "essential-black-tee",
        "name": "Essential Black Tee",
        "gender": "unisex",
        "category": "t-shirt",
        "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=900&auto=format&fit=crop",
        "price": 39.0,
        "description": "A minimal everyday black t-shirt with a clean crew neckline.",
        "is_active": True,
    },
    {
        "id": "camel-tailored-trouser",
        "name": "Camel Tailored Trouser",
        "gender": "male",
        "category": "pant",
        "image_url": "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=900&auto=format&fit=crop",
        "price": 129.0,
        "description": "Tailored camel trousers with a structured modern fit.",
        "is_active": True,
    },
    {
        "id": "navy-pique-polo",
        "name": "Navy Pique Polo",
        "gender": "male",
        "category": "t-shirt",
        "image_url": "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=900&auto=format&fit=crop",
        "price": 59.0,
        "description": "A refined navy pique polo for smart casual looks.",
        "is_active": True,
    },
    {
        "id": "rose-garden-kurti",
        "name": "Rose Garden Kurti",
        "gender": "female",
        "category": "kurti",
        "image_url": "https://images.unsplash.com/photo-1583391733956-6c78276477e2?w=900&auto=format&fit=crop",
        "price": 79.0,
        "description": "A floral kurti with soft drape and comfortable everyday styling.",
        "is_active": True,
    },
    {
        "id": "midnight-chiffon-dress",
        "name": "Midnight Chiffon Dress",
        "gender": "female",
        "category": "dress",
        "image_url": "https://images.unsplash.com/photo-1568252542512-9fe8fe9c87bb?w=900&auto=format&fit=crop",
        "price": 219.0,
        "description": "An elegant midnight chiffon dress for evening occasions.",
        "is_active": True,
    },
    {
        "id": "ivory-silk-shirt",
        "name": "Ivory Silk Shirt",
        "gender": "female",
        "category": "shirt",
        "image_url": "https://images.unsplash.com/photo-1551488831-00ddcb6c6bd3?w=900&auto=format&fit=crop",
        "price": 99.0,
        "description": "A smooth ivory silk shirt with a relaxed premium silhouette.",
        "is_active": True,
    },
    {
        "id": "sand-tailored-pant",
        "name": "Sand Tailored Pant",
        "gender": "unisex",
        "category": "pant",
        "image_url": "https://images.unsplash.com/photo-1506629905607-d9c297d8594f?w=900&auto=format&fit=crop",
        "price": 109.0,
        "description": "Neutral tailored pants designed for versatile outfit pairing.",
        "is_active": True,
    },
]


async def seed_products() -> None:
    db = get_database()
    for product in SEED_PRODUCTS:
        await db.products.update_one({"id": product["id"]}, {"$setOnInsert": product}, upsert=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_upload_dirs()
    await connect_to_mongo()
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
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=ROOT_DIR / "uploads"), name="uploads")

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
