from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from basemodels.authentication import TokenData
from routers.authentication import get_current_user_token_data
from services.example import build_report, get_all_user_emails, \
    get_all_user_ids_cached, stream_json_data, ReportOptions
from services.util import _response
from services.rbac import Role, require_roles

import asyncio, time

example_router = APIRouter(prefix="/example", tags=["Example"])

@example_router.get(
    "/admin_only",
    dependencies=[Depends(require_roles(Role.ADMIN))]
)
async def admin_only():
    """Example of a role-guarded endpoint. Add Depends(require_roles(...)) to
    any route; pass several roles for any-of, or require_all=True for all-of."""
    return {"message": "You are an admin."}

@example_router.post("/cached_report")
async def cached_report(
    filters: dict,
    tags: list[str],
    currency: str = "USD",
    token_data: TokenData = Depends(get_current_user_token_data)
):
    """Showcases flexible_lru_cache: the dict/list/object arguments below are
    unhashable, and the result survives a restart via persist=.

    Call it twice with the same body - the first takes ~1s, the second is
    instant, and it stays instant after the API restarts.
    """
    started = time.perf_counter()
    report = await build_report(filters, tags, ReportOptions(currency=currency))
    elapsed_ms = (time.perf_counter() - started) * 1000

    return {
        "report": report,
        "elapsed_ms": round(elapsed_ms, 1),
        "cache_hit": elapsed_ms < 100,
        "cache": build_report.cache_info()
    }

@example_router.get("/list_all_user_emails")
async def list_all_user_emails(
    token_data: TokenData = Depends(get_current_user_token_data)
):
    """List all user emails."""
    emails = await get_all_user_emails()
    return {
        "emails": _response(emails)
    }

@example_router.post("/chat")
async def stream_chat(
    token_data: TokenData = Depends(get_current_user_token_data)
):
    """Stream chat messages using SSE."""
    async def event_stream():
        msg = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit, "
        "sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris "
        "nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in "
        "reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. "
        "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia "
        "deserunt mollit anim id est laborum.")
        for word in msg.split(): # Formato SSE
            yield f"data: {word}\n\n"
            await asyncio.sleep(0.01)
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@example_router.get("/json_stream")
async def stream_json_data_ep(
    token_data: TokenData = Depends(get_current_user_token_data)
):
    """Stream JSON data"""
    return await stream_json_data()

@example_router.get("/list_all_user_ids_cached")
async def list_all_user_ids_cached(
    token_data: TokenData = Depends(get_current_user_token_data)
):
    """List all user ids."""
    ids = await get_all_user_ids_cached()
    return {
        "ids": _response(ids)
    }
