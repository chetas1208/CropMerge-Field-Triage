# CropMerge Field Triage

**RGB drone video → field segmentation → visual anomaly mapping → farmer review**

Product-shaped prototype for Midwest (Illinois) corn/soy context. Ordinary RGB (DJI Mini 2–class) footage in; structured inspection zones out. **Not** disease/nutrient/yield diagnosis.

```text
Nuxt product app  ──typed contract──►  Python vision engine
 (UX, jobs, API)                       (SAM/DINO/CV only)
```

## Architecture

```mermaid
flowchart TD
  V[RGB drone video] --> D[Decode + metadata]
  D --> S[Frame sample 1-5 FPS]
  S --> Q[Quality analysis]
  Q --> SEG[Segmentation SAM3 / heuristic]
  Q --> REG[Frame registration]
  SEG --> FM[Field + class masks]
  REG --> FM
  FM --> RGB[RGB ExG / color / texture]
  FM --> DINO[DINOv3 / heuristic embeddings]
  RGB --> AN[Spatial anomaly grid]
  DINO --> AN
  AN --> TC[Temporal consensus]
  TC --> Z[Inspection zones]
  Z --> OUT[Annotated MP4 + heatmap + JSON]
  OUT --> UI[CropMerge Nuxt UI]
```

## Monorepo layout

```text
apps/web          Nuxt + TypeScript product UI + public API
apps/vision       Python FastAPI CV engine
packages/types    Shared domain types
packages/validation  Zod schemas
docs/             Architecture, limitations, data sources
outputs/          Analysis artifacts
```

## Local databases

Default = **SQLite** (no Docker). Optional = **Postgres 16**.

```bash
bash scripts/init-local-dbs.sh
set -a; source data/db/local.env; set +a
```

| DB | File / URL | Owner |
|----|------------|--------|
| Product | `data/db/cropmerge.sqlite` | Nuxt jobs / analyses |
| Vision | `data/db/vision.sqlite` | Pipeline run log |

```bash
# optional Postgres
docker compose up -d postgres
export DATABASE_URL=postgresql://cropmerge:cropmerge@127.0.0.1:5432/cropmerge
export VISION_DATABASE_URL=postgresql://cropmerge:cropmerge@127.0.0.1:5432/cropmerge_vision
# Adminer UI: docker compose --profile tools up -d adminer → :8088
```

Health: `GET /api/health` (includes `db`), `GET /api/db/status`, `GET /vision/runs`.

## Quick start

### 1. Vision engine

```bash
cd apps/vision
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# optional offline demo video
python scripts/generate_demo_video.py
pytest -v
uvicorn api.main:app --host 127.0.0.1 --port 8001
```

Default backends are OpenCV `field_cv` + heuristic embeddings (no GPU weights required).
Optional SAM2 / DINOv2 weights: see `apps/vision/scripts/download_weights.py`.

### 2. Web app

```bash
# from repo root
corepack enable && pnpm install
export VISION_SERVICE_URL=http://127.0.0.1:8001
export OUTPUTS_DIR=$PWD/outputs
export UPLOADS_DIR=$PWD/data/uploads
pnpm dev
# → http://localhost:3000
```

### 3. Demo samples (in-repo)

| File | Kind | Notes |
|------|------|--------|
| `apps/web/public/samples/real_field_drone.mp4` | Real drone video | 10s crop field flyover (CC BY-SA 4.0) |
| `apps/web/public/samples/real_soybean_field.jpg` | Real field image | USDA soybean field (public domain) |
| `apps/vision/samples/synthetic_field.mp4` | Synthetic | Offline CI demo |

In the UI: **Try a real sample** → **Analyze field**. Attribution: `/samples/SOURCES.md`.

### 4. One-shot CLI demo

```bash
pnpm demo
```

## Product API (Nuxt)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/analyses` | Upload video, run analysis |
| GET | `/api/analyses` | List jobs |
| GET | `/api/analyses/:id` | Job + report |
| GET | `/api/analyses/:id/zones` | Inspection zones |
| GET | `/api/analyses/:id/frames` | Frame quality |
| GET | `/api/analyses/:id/artifacts` | Artifact paths/URLs |
| GET | `/api/artifacts/:runId/:name` | Serve file |

## Vision API (internal)

| Method | Path |
|--------|------|
| GET | `/vision/health` |
| POST | `/vision/analyze` |
| POST | `/vision/segment` |
| GET | `/vision/artifacts/{run_id}/{name}` |

## Model backends

| Component | Production path | Offline default |
|-----------|-----------------|-----------------|
| Segmentation | Meta SAM 3.1 (`SAM3_CHECKPOINT`) | `heuristic` (explicit fallback) |
| Embeddings | DINOv3 (`DINOV3_CHECKPOINT`) | histogram/texture descriptors |

Fallback outputs set `usedFallback: true` and are **never** labeled as SAM/DINO results.

## Language rules (hard)

Use: visual anomaly, inspection zone, review recommended, exploratory RGB analysis.

Avoid: disease detected, unhealthy crop, N deficiency, water stress confirmed, yield loss predicted.

## Outputs per run

```text
outputs/<run_id>/
  results.json
  metrics.json
  annotated_video.mp4
  heatmap.png
  segmentation_montage.jpg
  frames/
  overlays/
```

## Tests

```bash
cd apps/vision && pytest -v
```

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/TECHNICAL_SUMMARY.md](docs/TECHNICAL_SUMMARY.md)
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md)

## License

Prototype for evaluation. Third-party model weights subject to their licenses (Meta SAM/DINO).
