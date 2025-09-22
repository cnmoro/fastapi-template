from dotenv import load_dotenv
load_dotenv()

from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from contextlib import asynccontextmanager
from fastapi import FastAPI, Response

from services.db import close_mongo_client, ensure_indexes

from routers.authentication import auth_router
from routers.example import example_router

import anyio

@asynccontextmanager
async def lifespan(app: FastAPI):
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = 150
    await ensure_indexes()
    yield
    close_mongo_client()

app = FastAPI(
    lifespan=lifespan,
    default_response_class=ORJSONResponse
)

app.add_middleware(GZipMiddleware, minimum_size=5000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Change this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(example_router)

@app.get("/", tags=["Health Check"])
async def check():
    return Response(status_code=200)
