# 3.14t is the free-threaded (no-GIL) build. It is ~14% slower per request than
# the GIL build on this workload, which is the price of admission for future
# CPU-parallel work in-process. Every dependency here ships a cp314t wheel;
# orjson does not, which is why this image is on the stdlib json module.
#
# The interpreter comes from python-build-standalone (what `uv python install`
# fetches) rather than the official image: clang -O3, PGO+LTO, BOLT, mimalloc
# and 3.14's tail-call interpreter, measured ~30% more req/s with identical
# packages.
FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_PYTHON_INSTALL_DIR=/python \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

RUN uv python install 3.14t

WORKDIR /app
COPY requirements.txt .
# --only-binary so a missing free-threaded wheel fails the build loudly instead
# of silently falling back to a source compile
RUN uv venv --python 3.14t /venv && \
    VIRTUAL_ENV=/venv uv pip install --no-cache --only-binary=:all: -r requirements.txt


FROM debian:trixie-slim

# The venv's interpreter lives in /python, so it has to land at the same path
COPY --from=builder /python /python
COPY --from=builder /venv /venv

ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    # Keep the GIL off even if a dependency asks for it back, so a regression
    # surfaces as a warning here instead of silently costing the parallelism
    PYTHON_GIL=0 \
    # glibc allocates one arena per thread by default; capping it keeps RSS
    # flat now that bcrypt runs on the anyio thread pool
    MALLOC_ARENA_MAX=2

WORKDIR /app
COPY . .

# Precompile so the first request after a cold start doesn't pay for it
RUN python -m compileall -q . && \
    chmod +x start.sh && \
    # Exists up front and owned by app, so mounting a volume here does not
    # land a root-owned directory the app cannot write its cache into
    mkdir -p /app/.cache && \
    useradd --no-create-home --uid 1000 app && chown -R app /app
USER app

ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen(f\"http://127.0.0.1:{os.environ['PORT']}/\").status == 200 else 1)"

CMD ["./start.sh"]
