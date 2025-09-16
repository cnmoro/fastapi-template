#!/bin/sh
set -eu

# 1. Read variables (with defaults)
WC=${WORKER_COUNT:-1}
PORT=${PORT:-8000}

# 2. Validate worker count: positive integer
case $WC in
    ''|*[!0-9]*)
        echo "WORKER_COUNT must be a positive integer" >&2
        exit 1 ;;
esac

# 3. Validate port: 1-65535
case $PORT in
    ''|*[!0-9]*)
        echo "PORT must be an integer between 1 and 65535" >&2
        exit 1 ;;
    *)
        [ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || {
            echo "PORT must be between 1 and 65535" >&2
            exit 1
        } ;;
esac

# 4. Subtract 1 from worker count, minimum 1
WORKERS=$(( WC > 1 ? WC - 1 : 1 ))

# 5. Run gunicorn
exec gunicorn app:app \
     -w "$WORKERS" \
     -k uvicorn.workers.UvicornWorker \
     -b "0.0.0.0:$PORT"
