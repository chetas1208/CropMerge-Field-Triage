# Cloudflare Tunnel — vision API exposure

Expose the local vision API at a stable hostname (e.g. `vision.example.com`) using a **remotely managed named tunnel**. Do not use temporary `trycloudflare.com` URLs in production. Do not open inbound port 8001 on the router or firewall.

## Prerequisites

- A domain on Cloudflare (DNS managed by Cloudflare)
- Cloudflare Zero Trust access (free tier is sufficient)
- `cloudflared` installed on the GPU host

## Named tunnel setup (Cloudflare Zero Trust dashboard)

1. Go to **Networks → Tunnels → Create a tunnel**.
2. Choose **Cloudflared** connector, name it **`cropmerge-field-triage`**.
3. Copy the **install command** (contains a one-time tunnel token). **Do not commit or log the token.**
4. Add a **Public Hostname**:
   - Subdomain: `vision`
   - Domain: `<your-domain>`
   - Service type: HTTP
   - URL: `http://127.0.0.1:8001`
5. Save. Cloudflare creates the DNS record automatically when proxied.

## Install cloudflared as a systemd service

On the GPU host (Linux with systemd):

```bash
# One-time install using the token from the dashboard (replace <token>):
sudo cloudflared service install <tunnel-token>

sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

The token file is stored under `/etc/cloudflared/` with restricted permissions. Never add it to Git.

## Verify tunnel

```bash
# From any machine with network access:
curl -s https://vision.<domain>/vision/health | jq .

# On the GPU host:
journalctl -u cloudflared -f
```

Expected: HTTP 200 with `"service": "cropmerge-vision"`.

## CORS alignment

After Vercel deploys, add the production frontend origin to the GPU host env:

```dotenv
VISION_CORS_ORIGINS=https://<vercel-production-domain>,http://localhost:3000
VISION_PUBLIC_BASE_URL=https://vision.<domain>
```

Restart the vision service:

```bash
sudo systemctl restart cropmerge-vision
```

Test CORS:

```bash
curl -sI -X OPTIONS "https://vision.<domain>/vision/uploads/init" \
  -H "Origin: https://<vercel-production-domain>" \
  -H "Access-Control-Request-Method: POST"
```

Look for `access-control-allow-origin: https://<vercel-production-domain>`.

## Security notes

- Tunnel tokens grant connector access — treat as credentials.
- The Python API stays on `127.0.0.1`; only Cloudflare reaches it outbound.
- Authenticated analysis/upload routes require short-lived JWTs minted by Nuxt.
- Artifact downloads use separate signed query tokens (30–60 min TTL).
- Do not enable `allow_origins=["*"]` with credentials.

## Startup order after reboot

```text
network-online
    → cropmerge-vision.service (127.0.0.1:8001)
    → cloudflared.service (outbound tunnel)
    → https://vision.<domain>/vision/health returns 200
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Tunnel hostname 502 | `systemctl status cropmerge-vision`; confirm API on 8001 |
| Tunnel not connecting | `journalctl -u cloudflared`; egress to Cloudflare |
| CORS blocked in browser | `VISION_CORS_ORIGINS` includes exact Vercel origin (no trailing slash) |
| Upload fails at ~100 MB | Use chunked upload path (default above 24 MiB) |
| Video won't seek | Confirm `Range` returns 206 from `/vision/artifacts/...` |
