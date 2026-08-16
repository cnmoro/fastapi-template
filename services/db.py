from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
import os

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
# Default database, used when get_database() is called without a name
DB_NAME = os.environ.get("DB_NAME", "EXAMPLE")
# minPoolSize keeps connections warm, so bursts don't pay for a handshake
MONGO_MIN_POOL_SIZE = int(os.environ.get("MONGO_MIN_POOL_SIZE", 10))
MONGO_MAX_POOL_SIZE = int(os.environ.get("MONGO_MAX_POOL_SIZE", 100))

_client: AsyncMongoClient | None = None

def get_client() -> AsyncMongoClient:
    """The shared client. One connection pool serves every database."""
    global _client
    if _client is None:
        _client = AsyncMongoClient(
            MONGO_URI,
            minPoolSize=MONGO_MIN_POOL_SIZE,
            maxPoolSize=MONGO_MAX_POOL_SIZE
        )
    return _client

def get_database(name: str | None = None) -> AsyncDatabase:
    """Get a database by name, defaulting to DB_NAME.

        get_database()             -> the default database
        get_database("ANALYTICS")  -> any other database on the same connection
    """
    return get_client()[name or DB_NAME]

async def ensure_indexes():
    """Create required indexes on startup."""
    db = get_database()
    await db['USERS'].create_index([("email", 1)], unique=True)
    # Mongo drops each attempt counter once its lockout window passes
    await db['LOGIN_ATTEMPTS'].create_index([("expires_at", 1)], expireAfterSeconds=0)

async def close_mongo_client():
    global _client
    if _client:
        await _client.close()
        _client = None
