#!/bin/sh
set -e

# Start Dagster webserver in background (localhost only)
dagster-webserver -h 127.0.0.1 -p 3003 &
dagster_pid=$!

# Start auth proxy on externally-facing port
uvicorn auth_proxy:app --host 0.0.0.0 --port 8080 --log-level info &
proxy_pid=$!

cleanup() {
  kill "$dagster_pid" "$proxy_pid" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

# Exit container if either process dies
while kill -0 "$dagster_pid" 2>/dev/null && kill -0 "$proxy_pid" 2>/dev/null; do
  sleep 1
done

exit 1
