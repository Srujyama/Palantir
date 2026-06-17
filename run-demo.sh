#!/usr/bin/env bash
#
# run-demo.sh — one-command launcher for the Bottleneck Radar demo.
#
# Why this exists: the frontend proxies /api to localhost:8000 by default,
# but that port is sometimes occupied by another local project. This script
# starts the backend on a guaranteed-free port, points the frontend at it via
# the RADAR_API env var the vite config already honors, waits until the API is
# actually answering, and prints the one URL to open. Ctrl-C stops both.
#
# Usage:  ./run-demo.sh
# Override ports if you like:  BACKEND_PORT=8123 FRONTEND_PORT=5199 ./run-demo.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

# --- pick free ports (preferred default, then scan upward) ------------------
port_free() { ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
pick_port() {
  local p="$1"
  for _ in $(seq 1 50); do
    if port_free "$p"; then echo "$p"; return 0; fi
    p=$((p + 1))
  done
  echo "ERROR: no free port near $1" >&2; return 1
}
BACKEND_PORT="$(pick_port "${BACKEND_PORT:-8001}")"
FRONTEND_PORT="$(pick_port "${FRONTEND_PORT:-5173}")"

echo "▸ backend  port: $BACKEND_PORT"
echo "▸ frontend port: $FRONTEND_PORT"

# --- backend: venv, deps, data, server --------------------------------------
cd "$BACKEND"
if [ ! -d .venv ]; then
  echo "▸ creating backend venv…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "▸ ensuring backend deps…"
pip install -q -r requirements.txt

if [ ! -f app/db/radar.db ]; then
  echo "▸ generating + ingesting notional data (first run)…"
  python -m app.data.generate_notes
  python -m app.ingest
fi

echo "▸ starting backend…"
uvicorn app.main:app --port "$BACKEND_PORT" &
BACKEND_PID=$!

cleanup() {
  echo ""
  echo "▸ shutting down…"
  kill "$BACKEND_PID" 2>/dev/null || true
  kill "${FRONTEND_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# --- wait for the API to actually answer ------------------------------------
echo -n "▸ waiting for API"
for _ in $(seq 1 40); do
  if curl -s -o /dev/null -w '%{http_code}' "http://localhost:$BACKEND_PORT/patients" 2>/dev/null | grep -q 200; then
    echo " — up."
    break
  fi
  echo -n "."
  sleep 0.5
done

# --- frontend ----------------------------------------------------------------
cd "$FRONTEND"
if [ ! -d node_modules ]; then
  echo "▸ installing frontend deps…"
  npm install
fi

echo ""
echo "════════════════════════════════════════════════════════"
echo "  Bottleneck Radar is starting."
echo "  Open:  http://localhost:$FRONTEND_PORT"
echo "  (Ctrl-C here stops both servers.)"
echo "════════════════════════════════════════════════════════"
echo ""

RADAR_API="http://localhost:$BACKEND_PORT" npm run dev -- --port "$FRONTEND_PORT" --strictPort &
FRONTEND_PID=$!

wait "$FRONTEND_PID"
