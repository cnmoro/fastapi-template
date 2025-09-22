from fastapi.responses import StreamingResponse
from services.util import timed_lru_cache
from services.db import get_database
import json, aiohttp

async def get_all_user_emails():
    """Get all user emails using Motor."""
    results = await get_database()['USERS']\
                    .find({}, {"email": 1, "_id": 0})\
                        .to_list(length=None)
    return [ r["email"] for r in results ]

async def stream_json_data():
    """Stream all user e-mails as a JSON array without loading everything into RAM."""
    async def generate():

        yield '[\n'
        first = True
        async for doc in get_database()['USERS'].find({}, {"email": 1, "_id": 0}):
            if not first:
                yield ',\n'
            yield json.dumps(doc["email"])
            first = False

        yield '\n]'

    return StreamingResponse(generate(), media_type="application/json")

@timed_lru_cache(max_size=100, minutes=60)
async def get_all_user_ids_cached():
    """Get all user ids using Motor."""
    results = await get_database()['USERS']\
                    .find({}, {"_id": 1})\
                        .to_list(length=None)
    return [ str(r["_id"]) for r in results ]

async def sample_async_http_request():
    url = "https://www.bbc.com/"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()
