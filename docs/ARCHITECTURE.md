# Architecture

## Separation of concerns

| Layer | Owns | Must not own |
|-------|------|--------------|
| **Nuxt (`apps/web`)** | UX, uploads, job state, public REST, artifact proxy, typed contracts | PyTorch inference, mask math |
| **Vision (`apps/vision`)** | Decode, quality, segment, features, anomaly, temporal, render | Product copy beyond disclaimer, user accounts |
| **`packages/types`** | Shared TS domain model | Runtime logic |

Neither layer duplicates business rules: priority thresholds and fusion weights live in vision config; Nuxt only displays the contract.

## Pipeline

```text
Video → metadata/decode → sample → quality
     → segment/track (+ registration)
     → field mask
     → RGB features + embeddings
     → spatial grid anomaly
     → temporal consensus → zones
     → annotated video + heatmap + JSON
```

## Interfaces

- `Segmenter`: `segment_image` / `start_video` / `track_video`
- `EmbeddingExtractor`: `embed_tiles`
- Config YAML for prompts, grid, anomaly weights, temporal gates

## Geospatial (future hook only)

V1 is **image-relative**. Optional GPS fields preserved when present.

```text
Drone media → GPS/orientation/intrinsics → SfM → orthomosaic
  → georeferenced polygons → CropMerge map
  (+ USDA CDL, basemaps, terrain later)
```

See `cropmerge/geo/hooks.py`.
