from fastapi.responses import StreamingResponse
from services.util import timed_lru_cache, flexible_lru_cache
from services.http import get_http_session
from services.db import get_database
from dataclasses import dataclass
import asyncio, json

async def get_all_user_emails():
    """Get all user emails using async PyMongo."""
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
    """Get all user ids using async PyMongo."""
    results = await get_database()['USERS']\
                    .find({}, {"_id": 1})\
                        .to_list(length=None)
    return [ str(r["_id"]) for r in results ]

@dataclass
class ReportOptions:
    """A plain object - functools.lru_cache cannot key on this either."""
    currency: str = "USD"
    include_totals: bool = True

# Every argument below is unhashable, so functools.lru_cache would raise
# TypeError. persist= keeps the results across restarts.
@flexible_lru_cache(max_size=128, persist=".cache/reports.pkl")
async def build_report(filters: dict, tags: list[str], options: ReportOptions):
    """Demo of caching on arbitrary arguments. Pretends to be slow work."""
    await asyncio.sleep(1.0)
    return {
        "matched": sorted(filters.items()),
        "tags": sorted(tags),
        "currency": options.currency,
        "totals": {"count": len(tags)} if options.include_totals else None
    }

async def sample_async_http_request():
    url = "https://www.bbc.com/"
    
    async with get_http_session().get(url) as response:
        return await response.text()
