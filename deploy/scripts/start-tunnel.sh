#!/usr/bin/env bash
# Start Cloudflare quick tunnel -> local vision API (port 8001).
# For production use a named tunnel; see deploy/cloudflare/README.md
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOG="$ROOT/deploy/local/cloudflared.log"
PORT="${VISION_PORT:-8001}"
mkdir -p "$ROOT/deploy/local"
pkill -f "cloudflared tunnel --url http://127.0.0.1:${PORT}" 2>/dev/null || true
sleep 1
nohup cloudflared tunnel --url "http://127.0.0.1:${PORT}" >>"$LOG" 2>&1 &
echo "cloudflared PID=$!"
for _ in $(seq 1 15); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | tail -1 || true)"
  if [[ -n "$URL" ]]; then
    echo "Tunnel URL: $URL"
    exit 0
  fi
  sleep 1
done
echo "Tunnel starting — check $LOG"
tail -5 "$LOG"
