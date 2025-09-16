#!/bin/sh

# Load environment variables from .env
set -a
[ -f .env ] && . .env
set +a

# Default to 1 worker if WORKER_COUNT is not set
exec gunicorn app:app -w ${WORKER_COUNT:-1} -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
