from motor.motor_asyncio import AsyncIOMotorClient
import os

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "EXAMPLE")

_client: AsyncIOMotorClient | None = None

def get_database() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
    return _client[DB_NAME]

async def ensure_indexes():
    """Create required indexes on startup."""
    db = get_database()
    await db['USERS'].create_index([("email", 1)], unique=True)

def close_mongo_client():
    global _client
    if _client:
        _client.close()
        _client = None
