import aiohttp

_session: aiohttp.ClientSession | None = None

def get_http_session() -> aiohttp.ClientSession:
    """Shared session, so outbound calls reuse DNS/TCP/TLS instead of
    re-handshaking on every request."""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=200, ttl_dns_cache=300)
        )
    return _session

async def close_http_session():
    global _session
    if _session:
        await _session.close()
        _session = None
