#!/bin/sh
set -e

# Start Dagster webserver in background (localhost only)
dagster-webserver -h 127.0.0.1 -p 3003 &

# Start auth proxy on externally-facing port
exec uvicorn auth_proxy:app --host 0.0.0.0 --port 8080 --log-level info
