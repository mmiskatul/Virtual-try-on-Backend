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
    await get_database().products.create_index("id", unique=True)


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
