from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
import os

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "EXAMPLE")
# minPoolSize keeps connections warm, so bursts don't pay for a handshake
MONGO_MIN_POOL_SIZE = int(os.environ.get("MONGO_MIN_POOL_SIZE", 10))
MONGO_MAX_POOL_SIZE = int(os.environ.get("MONGO_MAX_POOL_SIZE", 100))

_client: AsyncMongoClient | None = None

def get_database() -> AsyncDatabase:
    global _client
    if _client is None:
        _client = AsyncMongoClient(
            MONGO_URI,
            minPoolSize=MONGO_MIN_POOL_SIZE,
            maxPoolSize=MONGO_MAX_POOL_SIZE
        )
    return _client[DB_NAME]

async def ensure_indexes():
    """Create required indexes on startup."""
    db = get_database()
    await db['USERS'].create_index([("email", 1)], unique=True)

async def close_mongo_client():
    global _client
    if _client:
        await _client.close()
        _client = None
