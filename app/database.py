from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

settings = get_settings()
client: AsyncIOMotorClient | None = None


async def connect_to_mongo() -> None:
    global client
    if not settings.mongodb_uri:
        raise RuntimeError("MONGODB_URI is not configured")

    client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=10000)
    await client.admin.command("ping")
    db = get_database()
    await db.products.create_index("id", unique=True)
    await db.products.create_index([("is_active", 1), ("name", 1)])
    await db.products.create_index([("category", 1), ("name", 1)])
    await db.admin_users.create_index("username", unique=True)
    await db.categories.create_index("value", unique=True)
    await db.tryon_results.create_index([("product_id", 1), ("created_at", -1)])
    await db.tryon_results.create_index([("created_at", -1)])
    await db.admin_audit_logs.create_index([("created_at", -1)])


async def close_mongo_connection() -> None:
    global client
    if client is not None:
        client.close()
        client = None


def get_database() -> AsyncIOMotorDatabase:
    if client is None:
        raise RuntimeError("MongoDB client is not initialized")
    return client[settings.database_name]


async def get_db() -> AsyncIOMotorDatabase:
    return get_database()
