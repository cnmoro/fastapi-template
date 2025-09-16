import httpx

_client: httpx.AsyncClient | None = None

def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(http2=True, timeout=120.0)
    return _client

async def close_http_client():
    global _client
    if _client:
        await _client.aclose()
        _client = None
