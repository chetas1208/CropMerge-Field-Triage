# CropMerge Field Triage — agent rules

## Product

RGB drone **video or image** → field segmentation → visual anomaly mapping → farmer review.  
**Not** disease / nutrient / irrigation / yield diagnosis.

## Stack

- `apps/web` — Nuxt 3 product UI + public API (jobs, artifacts, frame review)
- `apps/vision` — Python FastAPI CV engine (`field_cv` / heuristic offline default)
- `packages/*` — shared types + validation
- Default DB: SQLite under `data/db/` (paths with spaces must be quoted)

## Runtime

- Vision: `127.0.0.1:8001` (`uvicorn api.main:app`)
- Web: `localhost:3000` (`pnpm dev`)
- Env: `VISION_SERVICE_URL`, `OUTPUTS_DIR`, `UPLOADS_DIR`, `CROP_MERGE_OUTPUTS`

## UX invariants

- Upload drop zone must **not** cover Analyze/Browse with a full-area file input (buttons stay clickable).
- Results page must show **every sampled frame** (`FrameReview`: filmstrip, raw/overlay/split, quality, zone→frame jump).
- Real samples served from `apps/web/public/samples/` with one-click loaders on the home page.
- Language: visual anomaly / inspection zone / review recommended — never disease claims.

## Samples

| Path | Notes |
|------|--------|
| `apps/web/public/samples/real_field_drone.mp4` | Real drone clip (CC BY-SA 4.0) |
| `apps/web/public/samples/real_soybean_field.jpg` | USDA soybean (public domain) |
| `apps/vision/samples/synthetic_field.mp4` | Offline synthetic |
| Attribution | `.../samples/SOURCES.md` |

## GitHub

- Remote: `git@github.com:chetas1208/CropMerge-Field-Triage.git` (**private**)
- Follow global ship playbook: `~/.grok/rules/github-private-ship.md`
- Do not commit: `.venv`, `node_modules`, weights (`*.pt`/`*.pth`), sqlite, `outputs/`, raw `source_*` media, secrets

## Verify before calling UI work done

- Happy-path analyze (video + image) via `/api/analyses`
- Artifact URLs 200 for video, heatmap, montage, `frames/frame_XXXX.jpg`, `overlays/overlay_XXXX.jpg`
- If browser tools missing: API + static checks; say what was not browser-verified
