from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from basemodels.authentication import TokenData
from routers.authentication import get_current_user_token_data
from services.example import get_all_user_emails, get_all_user_ids_cached, stream_json_data
from services.util import _response

import asyncio

example_router = APIRouter(prefix="/example", tags=["Example"])

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
