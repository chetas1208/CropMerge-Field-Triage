# CropMerge Vision Engine

Internal Python CV service. **Not** the product UI.

Owns: decode, quality, segmentation, DINO/RGB features, anomaly, temporal consensus, artifacts.

Does **not** own: UX, job store, public API contracts (Nuxt does).

## Quick start

```bash
cd apps/vision
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/generate_demo_video.py
python scripts/analyze_video.py \
  --input samples/synthetic_field.mp4 \
  --output ../../outputs/demo \
  --segmentation-backend heuristic
pytest -v
uvicorn api.main:app --port 8001
```

## Backends

| Backend | Role |
|---------|------|
| `heuristic` | Explicit RGB fallback (default offline) |
| `sam3` | Meta SAM 3.1 when `SAM3_CHECKPOINT` + package available |
| `dinov3` | Dense features when `DINOV3_CHECKPOINT` set |

Fallback outputs always set `usedFallback` / `is_fallback` — never claimed as SAM/DINO.

## API

- `GET /vision/health`
- `POST /vision/analyze` (multipart file)
- `POST /vision/segment`
- `GET /vision/artifacts/{run_id}/{name}`
