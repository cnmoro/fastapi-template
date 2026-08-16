from dotenv import load_dotenv
load_dotenv()

from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager
from fastapi import FastAPI, Response

from services.db import close_mongo_client, ensure_indexes
from services.http import close_http_session

from routers.authentication import auth_router
from routers.example import example_router

import anyio, os

# Comma-separated list, e.g. "https://app.example.com,https://admin.example.com".
# Credentialed requests cannot use a wildcard origin - browsers reject the
# combination - so "*" turns credentials off rather than silently misbehaving.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
ALLOW_CREDENTIALS = CORS_ORIGINS != ["*"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = 150
    await ensure_indexes()
    yield
    await close_http_session()
    await close_mongo_client()

app = FastAPI(lifespan=lifespan)

# level 9 costs ~2x the CPU of level 5 for ~0.2% better ratio
app.add_middleware(GZipMiddleware, minimum_size=5000, compresslevel=5)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
    # Without this a browser cannot read the slid token on cross-origin calls
    expose_headers=["X-Refreshed-Token"],
)

app.include_router(auth_router)
app.include_router(example_router)

@app.get("/", tags=["Health Check"])
async def check():
    return Response(status_code=200)
