#!/usr/bin/env bash
# Restart vision/tunnel if health checks fail.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PORT="${VISION_PORT:-8001}"
TUNNEL_LOG="$ROOT/deploy/local/cloudflared.log"
TUNNEL_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | tail -1 || true)"

vision_ok=false
if curl -sf "http://127.0.0.1:${PORT}/vision/health" >/dev/null 2>&1; then
  vision_ok=true
fi

tunnel_ok=false
if [[ -n "$TUNNEL_URL" ]] && curl -sf "${TUNNEL_URL}/vision/health" >/dev/null 2>&1; then
  tunnel_ok=true
fi

if ! pgrep -f "uvicorn api.main:app --host 127.0.0.1 --port ${PORT}" >/dev/null || ! $vision_ok; then
  echo "$(date -Is) restarting vision"
  "$ROOT/deploy/scripts/start-vision.sh" || true
fi

if ! pgrep -f "cloudflared tunnel --url http://127.0.0.1:${PORT}" >/dev/null || ! $tunnel_ok; then
  echo "$(date -Is) restarting cloudflared"
  "$ROOT/deploy/scripts/start-tunnel.sh" || true
fi
