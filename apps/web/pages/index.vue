<script setup lang="ts">
import type { AnalysisJob, FieldTriageReport, InspectionZone } from '@cropmerge/types'

type Health = {
  ok?: boolean
  error?: string
  db?: { ok?: boolean; mode?: string; path?: string }
  vision?: {
    status?: string
    device?: string
    segmentationBackend?: string
    dinoBackend?: string
  }
}

type RecentJob = {
  id: string
  status: string
  createdAt: string
  filename: string
  zoneCount?: number
  fieldDetected?: boolean | null
}

const file = ref<File | null>(null)
const loading = ref(false)
const error = ref('')
const job = ref<AnalysisJob | null>(null)
const health = ref<Health | null>(null)
const recent = ref<RecentJob[]>([])
const dragover = ref(false)
const mediaTab = ref<'video' | 'heatmap' | 'montage' | 'frames'>('video')
const selectedZoneId = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const frameSectionEl = ref<HTMLElement | null>(null)
const uploadProgress = ref<number | null>(null)
const activeUploadId = ref<string | null>(null)
const abortController = ref<AbortController | null>(null)
const { request } = useVisionApi()

function scrollToFrames() {
  mediaTab.value = 'frames'
  nextTick(() => {
    frameSectionEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

const PIPELINE = [
  'Decode',
  'Quality',
  'Segment',
  'Features',
  'Anomaly',
  'Temporal',
  'Render',
]

onMounted(async () => {
  await Promise.all([refreshHealth(), refreshRecent()])
})

async function refreshHealth() {
  try {
    const vision = await request<NonNullable<Health['vision']>>('/vision/health', {}, false)
    health.value = { ok: vision.status === 'ok', vision }
  } catch {
    health.value = { ok: false, error: 'Health check failed' }
  }
}

async function refreshRecent() {
  try {
    const response = await request<{ analyses: AnalysisJob[] }>('/vision/analyses')
    recent.value = response.analyses.map((analysis) => ({
      id: analysis.id,
      status: analysis.status,
      createdAt: analysis.createdAt,
      filename: analysis.filename,
      zoneCount: analysis.report?.inspectionZones.length,
      fieldDetected: analysis.report?.field.detected,
    }))
  } catch {
    recent.value = []
  }
}

const report = computed(() => job.value?.report as FieldTriageReport | null | undefined)

const zones = computed(() => report.value?.inspectionZones ?? [])

const selectedZone = computed<InspectionZone | null>(() => {
  if (!zones.value.length) return null
  const hit = zones.value.find((z) => z.id === selectedZoneId.value)
  return hit || zones.value[0]
})

watch(
  zones,
  (z) => {
    if (z.length && !z.some((x) => x.id === selectedZoneId.value)) {
      selectedZoneId.value = z[0].id
    }
  },
  { immediate: true },
)

const highestPriority = computed(() => {
  if (zones.value.some((z) => z.reviewPriority === 'high')) return 'high'
  if (zones.value.some((z) => z.reviewPriority === 'medium')) return 'medium'
  if (zones.value.length) return 'low'
  return null
})

const visionOnline = computed(() => health.value?.vision?.status === 'ok')

function pct(n: number | undefined) {
  if (n == null || Number.isNaN(n)) return '—'
  return `${Math.round(n * 100)}%`
}

function artifactUrl(name: string) {
  return job.value?.artifactUrls?.[name] || ''
}

function formatBytes(n: number) {
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function formatWhen(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

const VIDEO_EXTS = ['.mp4', '.mov', '.m4v']
const IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.webp', '.bmp']
const ALLOWED_EXTS = [...VIDEO_EXTS, ...IMAGE_EXTS]

function extOf(name: string) {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i).toLowerCase() : ''
}

function isAllowedFile(f: File) {
  return ALLOWED_EXTS.includes(extOf(f.name)) || f.type.startsWith('video/') || f.type.startsWith('image/')
}

const isImageUpload = computed(() => {
  if (!file.value) return false
  const ext = extOf(file.value.name)
  return IMAGE_EXTS.includes(ext) || file.value.type.startsWith('image/')
})

function setFile(f: File | null) {
  if (f && !isAllowedFile(f)) {
    error.value = 'Use video (.mp4 .mov .m4v) or image (.jpg .png .webp .bmp).'
    return
  }
  file.value = f
  error.value = ''
}

function onFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  setFile(input.files?.[0] ?? null)
}

function onDrop(e: DragEvent) {
  dragover.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) setFile(f)
}

function openFilePicker() {
  fileInput.value?.click()
}

function onDropZoneClick(e: MouseEvent) {
  const t = e.target as HTMLElement | null
  if (t?.closest('button, a, input, label')) return
  openFilePicker()
}

const SAMPLE_INPUTS = [
  {
    id: 'vid',
    label: 'Real drone field video',
    detail: 'Estonia · 10s · 1280×720',
    url: '/samples/real_field_drone.mp4',
    filename: 'real_field_drone.mp4',
    mime: 'video/mp4',
  },
  {
    id: 'img',
    label: 'Real soybean field image',
    detail: 'South Dakota · RGB still',
    url: '/samples/real_soybean_field.jpg',
    filename: 'real_soybean_field.jpg',
    mime: 'image/jpeg',
  },
] as const

const loadingSample = ref<string | null>(null)

async function useSample(sample: (typeof SAMPLE_INPUTS)[number]) {
  loadingSample.value = sample.id
  error.value = ''
  try {
    const res = await fetch(sample.url)
    if (!res.ok) throw new Error(`Sample download failed (${res.status})`)
    const blob = await res.blob()
    setFile(new File([blob], sample.filename, { type: sample.mime }))
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loadingSample.value = null
  }
}

type UploadResponse = {
  uploadId: string
  status: string
  size: number
}

type UploadInitResponse = {
  uploadId: string
  chunkSize: number
  totalChunks: number
}

async function uploadFile(input: File, signal: AbortSignal): Promise<string> {
  const configuredThreshold = Number(useRuntimeConfig().public.visionSmallUploadThresholdBytes)
  if (input.size <= configuredThreshold) {
    uploadProgress.value = 0.05
    const body = new FormData()
    body.append('file', input)
    const uploaded = await request<UploadResponse>('/vision/uploads', {
      method: 'POST',
      body,
      signal,
    })
    uploadProgress.value = 1
    return uploaded.uploadId
  }

  const initialized = await request<UploadInitResponse>('/vision/uploads/init', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ filename: input.name, size: input.size, contentType: input.type || undefined }),
    signal,
  })
  activeUploadId.value = initialized.uploadId

  for (let index = 0; index < initialized.totalChunks; index += 1) {
    const start = index * initialized.chunkSize
    const chunk = input.slice(start, Math.min(start + initialized.chunkSize, input.size))
    await request<void>(`/vision/uploads/${initialized.uploadId}/chunks/${index}`, {
      method: 'PUT',
      headers: { 'content-type': 'application/octet-stream' },
      body: chunk,
      signal,
    })
    uploadProgress.value = (index + 1) / initialized.totalChunks
  }

  const completed = await request<UploadResponse>(`/vision/uploads/${initialized.uploadId}/complete`, {
    method: 'POST',
    signal,
  })
  return completed.uploadId
}

async function waitForAnalysis(id: string, signal: AbortSignal) {
  while (!signal.aborted) {
    const current = await request<AnalysisJob>(`/vision/analyses/${id}`, { signal })
    job.value = current
    if (current.status === 'completed') return current
    if (current.status === 'failed' || current.status === 'cancelled') {
      throw new Error(current.error || current.message || 'Analysis did not complete')
    }
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(resolve, 1500)
      signal.addEventListener(
        'abort',
        () => {
          window.clearTimeout(timer)
          reject(new DOMException('Request aborted', 'AbortError'))
        },
        { once: true },
      )
    })
  }
  throw new DOMException('Request aborted', 'AbortError')
}

async function analyze() {
  if (!file.value) {
    error.value = 'Choose a drone video or field image first.'
    return
  }
  if (!visionOnline.value) {
    error.value = 'Vision engine is offline. Start it on port 8001, then try again.'
    return
  }
  loading.value = true
  error.value = ''
  job.value = null
  uploadProgress.value = 0
  activeUploadId.value = null
  abortController.value = new AbortController()
  mediaTab.value = isImageUpload.value ? 'heatmap' : 'video'
  try {
    const uploadId = await uploadFile(file.value, abortController.value.signal)
    activeUploadId.value = null
    job.value = await request<AnalysisJob>('/vision/analyses', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        uploadId,
        sampleFps: 2,
        // Images are repeated across a few synthetic timestamps so temporal
        // persistence (min ~3 frames) can still form inspection zones.
        maxFrames: isImageUpload.value ? 3 : 40,
        skipDino: false,
        segmentationBackend: health.value?.vision?.segmentationBackend || 'heuristic',
        dinoBackend: health.value?.vision?.dinoBackend || 'heuristic',
      }),
      signal: abortController.value.signal,
    })
    await waitForAnalysis(job.value.id, abortController.value.signal)
    await refreshRecent()
  } catch (e: unknown) {
    if ((e as { name?: string }).name !== 'AbortError') {
      error.value = e instanceof Error ? e.message : String(e)
    }
  } finally {
    loading.value = false
    uploadProgress.value = null
    activeUploadId.value = null
    abortController.value = null
  }
}

async function openRecent(id: string) {
  error.value = ''
  loading.value = true
  try {
    job.value = await request<AnalysisJob>(`/vision/analyses/${id}`)
    mediaTab.value = 'video'
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function cancelUpload() {
  abortController.value?.abort()
  const uploadId = activeUploadId.value
  if (uploadId) {
    try {
      await request<void>(`/vision/uploads/${uploadId}`, { method: 'DELETE' })
    } catch {
      // The canceled browser request may have already removed the partial upload.
    }
  }
}

function reset() {
  void cancelUpload()
  job.value = null
  file.value = null
  selectedZoneId.value = null
  error.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

const mediaSrc = computed(() => {
  if (mediaTab.value === 'heatmap') return artifactUrl('heatmap.png')
  if (mediaTab.value === 'montage') return artifactUrl('segmentation_montage.jpg')
  if (mediaTab.value === 'frames') return ''
  return artifactUrl('annotated_video.mp4')
})
</script>

<template>
  <div class="stack stack-lg">
    <!-- Empty / upload state -->
    <template v-if="!report && !loading">
      <div class="row row-between">
        <div>
          <p class="section-label" style="margin-bottom: 0.35rem">Flight review</p>
          <h1 class="page-title">Turn drone video into inspection zones</h1>
          <p class="page-lead">
            Upload Midwest-style RGB footage. CropMerge maps the field, scores visual variation, and
            flags persistent regions worth a closer look — not a crop-health diagnosis.
          </p>
        </div>
      </div>

      <div class="disclaimer-box">
        <div class="ico" aria-hidden="true">!</div>
        <div>
          Flagged regions are <strong>visual differences</strong> from surrounding crop appearance for
          human review. Not disease, nutrient status, irrigation failure, or plant health.
        </div>
      </div>

      <div class="grid-hero">
        <div
          class="upload-drop"
          :class="{ dragover, 'has-file': !!file }"
          role="button"
          tabindex="0"
          aria-label="Upload field video or image"
          @click="onDropZoneClick"
          @keydown.enter.prevent="openFilePicker"
          @keydown.space.prevent="openFilePicker"
          @dragenter.prevent="dragover = true"
          @dragover.prevent="dragover = true"
          @dragleave.prevent="dragover = false"
          @drop.prevent="onDrop"
        >
          <input
            ref="fileInput"
            type="file"
            class="sr-only"
            accept=".mp4,.mov,.m4v,.jpg,.jpeg,.png,.webp,.bmp,video/*,image/*"
            @change="onFileInput"
            @click.stop
          />
          <div class="upload-icon" aria-hidden="true">↑</div>
          <h2 class="upload-title">Drop field video or image here</h2>
          <p class="upload-meta">
            Video .mp4 · .mov · .m4v · Image .jpg · .png · .webp · 2 FPS sample
          </p>

          <div v-if="file" class="file-chip" @click.stop>
            <span>{{ file.name }}</span>
            <span class="muted">{{ formatBytes(file.size) }}</span>
            <span v-if="isImageUpload" class="muted">image</span>
          </div>

          <div class="hero-actions" @click.stop>
            <button
              type="button"
              class="btn btn-primary"
              :disabled="!file || !visionOnline || loading"
              @click="analyze"
            >
              Analyze field
            </button>
            <button type="button" class="btn btn-ghost" @click="openFilePicker">
              Browse files
            </button>
          </div>

          <div class="sample-row" @click.stop>
            <span class="muted" style="font-size: 0.78rem">Try a real sample:</span>
            <button
              v-for="s in SAMPLE_INPUTS"
              :key="s.id"
              type="button"
              class="btn btn-ghost btn-sm"
              :disabled="!!loadingSample || loading"
              @click="useSample(s)"
            >
              {{ loadingSample === s.id ? 'Loading…' : s.label }}
            </button>
            <a class="muted mono" href="/samples/SOURCES.md" target="_blank" rel="noopener" style="font-size: 0.72rem">
              sources
            </a>
          </div>

          <div class="pipeline">
            <span v-for="(step, i) in PIPELINE" :key="step" class="pipe-step">
              <b>{{ String(i + 1).padStart(2, '0') }}</b>
              {{ step }}
            </span>
          </div>
        </div>

        <div class="stack">
          <div class="card">
            <h2 class="section-label">System</h2>
            <div class="stack" style="gap: 0.55rem">
              <div class="row row-between">
                <span class="muted">Vision engine</span>
                <span class="chip" :class="visionOnline ? 'ok' : 'bad'">
                  <span class="dot" />
                  {{ visionOnline ? 'Ready' : 'Offline' }}
                </span>
              </div>
              <div class="row row-between">
                <span class="muted">Segmentation</span>
                <span class="mono">{{ health?.vision?.segmentationBackend || '—' }}</span>
              </div>
              <div class="row row-between">
                <span class="muted">Embeddings</span>
                <span class="mono">{{ health?.vision?.dinoBackend || '—' }}</span>
              </div>
              <div class="row row-between">
                <span class="muted">Device</span>
                <span class="mono">{{ health?.vision?.device || '—' }}</span>
              </div>
              <div class="row row-between">
                <span class="muted">Database</span>
                <span class="mono">{{ health?.db?.mode || 'sqlite' }}</span>
              </div>
            </div>
            <p v-if="!visionOnline" class="error-banner" style="margin-top: 1rem; margin-bottom: 0">
              Start vision:
              <code class="mono">cd apps/vision && uvicorn api.main:app --port 8001</code>
            </p>
          </div>

          <div class="card">
            <div class="card-head">
              <h2 class="section-label" style="margin: 0">Recent analyses</h2>
              <button type="button" class="btn btn-ghost btn-sm" @click="refreshRecent">Refresh</button>
            </div>
            <p v-if="!recent.length" class="muted" style="margin: 0">
              No saved jobs yet. Run an analysis to populate the local database.
            </p>
            <div v-else class="recent-list">
              <button
                v-for="r in recent.slice(0, 6)"
                :key="r.id"
                type="button"
                class="recent-item"
                @click="openRecent(r.id)"
              >
                <div style="min-width: 0">
                  <div class="name">{{ r.filename }}</div>
                  <div class="meta">
                    {{ formatWhen(r.createdAt) }}
                    · {{ r.status }}
                    <template v-if="r.zoneCount != null"> · {{ r.zoneCount }} zones</template>
                  </div>
                </div>
                <span class="chip">Open</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="error" class="error-banner">{{ error }}</div>
    </template>

    <!-- Loading -->
    <div v-else-if="loading" class="card loading-panel">
      <div class="spinner" aria-hidden="true" />
      <h2 class="upload-title" style="margin-bottom: 0.35rem">Analyzing field flight</h2>
      <p class="muted" style="margin: 0">
        {{
          uploadProgress != null && uploadProgress < 1
            ? `Uploading directly to the vision server · ${Math.round(uploadProgress * 100)}%`
            : job?.message || 'Sampling frames, segmenting regions, scoring visual variation, building inspection zones…'
        }}
      </p>
      <div class="progress-track" aria-hidden="true"><i /></div>
      <div class="pipeline" style="justify-content: center">
        <span v-for="(step, i) in PIPELINE" :key="step" class="pipe-step">
          <b>{{ String(i + 1).padStart(2, '0') }}</b>
          {{ step }}
        </span>
      </div>
      <button
        v-if="activeUploadId"
        type="button"
        class="btn btn-ghost btn-sm"
        style="margin-top: 1rem"
        @click="cancelUpload"
      >
        Cancel upload
      </button>
    </div>

    <!-- Results -->
    <template v-else-if="report">
      <div class="row row-between">
        <div style="min-width: 0">
          <p class="section-label" style="margin-bottom: 0.35rem">Analysis complete</p>
          <h1 class="page-title" style="font-size: clamp(1.4rem, 2.5vw, 1.85rem)">
            {{ report.source.filename }}
          </h1>
          <p class="muted" style="margin: 0.25rem 0 0">
            {{ report.source.width }}×{{ report.source.height }}
            · {{ report.analysis.framesSampled }} frames @ {{ report.analysis.sampleFps }} FPS
            · {{ report.analysis.totalRuntimeSec.toFixed(1) }}s
            · <span class="mono">{{ report.runId }}</span>
          </p>
        </div>
        <div class="row">
          <a class="btn btn-ghost btn-sm" :href="artifactUrl('results.json')" target="_blank" rel="noopener">
            results.json
          </a>
          <button type="button" class="btn btn-ghost" @click="reset">New analysis</button>
        </div>
      </div>

      <div class="disclaimer-box">
        <div class="ico" aria-hidden="true">!</div>
        <div>{{ report.disclaimer }}</div>
      </div>

      <!-- Overview stats -->
      <div class="card">
        <h2 class="section-label">Field overview</h2>
        <div class="stat-grid">
          <div class="stat">
            <span class="label">Field</span>
            <span class="value">{{ report.field.detected ? 'Detected' : 'None' }}</span>
            <span class="sub">{{ pct(report.field.meanFieldFraction) }} of frame</span>
          </div>
          <div class="stat">
            <span class="label">Crop area</span>
            <span class="value">{{ pct(report.field.meanCropCoverage) }}</span>
            <span class="sub">visible canopy proxy</span>
          </div>
          <div class="stat">
            <span class="label">Exposed soil</span>
            <span class="value">{{ pct(report.field.meanBareSoil) }}</span>
            <span class="sub">bare ground share</span>
          </div>
          <div class="stat">
            <span class="label">Zones</span>
            <span class="value">{{ zones.length }}</span>
            <span class="sub">persistent inspection</span>
          </div>
          <div class="stat">
            <span class="label">Priority</span>
            <span class="value">
              <span v-if="highestPriority" class="priority" :class="highestPriority">
                {{ highestPriority }}
              </span>
              <span v-else>—</span>
            </span>
            <span class="sub">highest review need</span>
          </div>
          <div class="stat">
            <span class="label">Usable frames</span>
            <span class="value">{{ report.analysis.framesUsable }}/{{ report.analysis.framesSampled }}</span>
            <span class="sub">
              {{ report.analysis.segmentationBackend }}
              <template v-if="report.analysis.usedFallback"> · fallback</template>
            </span>
          </div>
        </div>
        <div class="row" style="margin-top: 0.85rem">
          <span class="chip" :class="report.field.roadPathDetected ? 'ok' : ''">
            Road/path {{ report.field.roadPathDetected ? 'yes' : 'no' }}
          </span>
          <span class="chip" :class="report.field.treeVegetationDetected ? 'ok' : ''">
            Trees {{ report.field.treeVegetationDetected ? 'yes' : 'no' }}
          </span>
          <span class="chip" :class="report.field.waterDetected ? 'ok' : ''">
            Water {{ report.field.waterDetected ? 'yes' : 'no' }}
          </span>
        </div>
      </div>

      <!-- Media -->
      <div class="grid-media">
        <div class="card">
          <div class="card-head">
            <h2 class="section-label" style="margin: 0">Field media</h2>
            <div class="tabs" role="tablist">
              <button
                type="button"
                class="tab"
                :class="{ active: mediaTab === 'video' }"
                role="tab"
                @click="mediaTab = 'video'"
              >
                Annotated media
              </button>
              <button
                type="button"
                class="tab"
                :class="{ active: mediaTab === 'frames' }"
                role="tab"
                @click="scrollToFrames"
              >
                All frames
                <span v-if="report.analysis.framesSampled" class="tab-count">
                  {{ report.analysis.framesSampled }}
                </span>
              </button>
              <button
                type="button"
                class="tab"
                :class="{ active: mediaTab === 'heatmap' }"
                role="tab"
                @click="mediaTab = 'heatmap'"
              >
                Variation map
              </button>
              <button
                type="button"
                class="tab"
                :class="{ active: mediaTab === 'montage' }"
                role="tab"
                @click="mediaTab = 'montage'"
              >
                Montage
              </button>
            </div>
          </div>

          <div class="media-frame">
            <video
              v-if="mediaTab === 'video' && mediaSrc"
              :key="mediaSrc"
              controls
              playsinline
              :src="mediaSrc"
            />
            <img
              v-else-if="mediaSrc"
              :key="mediaSrc"
              :src="mediaSrc"
              :alt="mediaTab === 'heatmap' ? 'Visual field variation' : 'Segmentation montage'"
            />
            <div v-else-if="mediaTab === 'frames'" class="frames-tab-hint">
              <p class="muted" style="margin: 0 0 0.75rem">
                {{ report.analysis.framesSampled }} sampled frames with overlays and quality scores.
              </p>
              <button type="button" class="btn btn-primary btn-sm" @click="scrollToFrames">
                Open frame review
              </button>
            </div>
            <p v-else class="muted">Artifact not available</p>
          </div>
          <p class="media-caption">
            <template v-if="mediaTab === 'heatmap'">
              Visual field variation — image-relative · not georeferenced · not a crop health map
            </template>
            <template v-else-if="mediaTab === 'montage'">
              Representative overlays across the flight
            </template>
            <template v-else-if="mediaTab === 'frames'">
              Full per-frame strip is below — every sample the engine scored
            </template>
            <template v-else>
              {{ report.mapLabel }}
            </template>
          </p>
        </div>

        <div class="card zone-detail" v-if="selectedZone">
          <div class="row row-between" style="margin-bottom: 0.75rem">
            <div>
              <h2 class="section-label" style="margin-bottom: 0.35rem">Selected zone</h2>
              <div class="row">
                <span class="zone-id" style="font-size: 1.1rem">{{ selectedZone.id }}</span>
                <span class="priority" :class="selectedZone.reviewPriority">
                  {{ selectedZone.reviewPriority }}
                </span>
              </div>
            </div>
            <LocationCompass
              :location="selectedZone.relativeLocation"
              :priority="selectedZone.reviewPriority"
            />
          </div>

          <p class="zone-loc" style="margin-bottom: 0.85rem">
            {{ selectedZone.relativeLocation }} · frames {{ selectedZone.framesSeen }} ·
            {{ selectedZone.firstSeenSec.toFixed(1) }}s–{{ selectedZone.lastSeenSec.toFixed(1) }}s
          </p>

          <div class="zone-metrics">
            <div class="zone-metric">
              <label>Visual anomaly</label>
              <strong>{{ selectedZone.anomalyScore.toFixed(2) }}</strong>
              <ScoreBar :value="selectedZone.anomalyScore" :tone="selectedZone.reviewPriority" />
            </div>
            <div class="zone-metric">
              <label>Persistence</label>
              <strong>{{ selectedZone.persistenceScore.toFixed(2) }}</strong>
              <ScoreBar :value="selectedZone.persistenceScore" />
            </div>
          </div>

          <h3 class="section-label" style="margin-top: 1.15rem">Why flagged</h3>
          <ul>
            <li v-for="(r, i) in selectedZone.reasons" :key="i">{{ r }}</li>
          </ul>

          <div class="reco">
            <strong>Recommendation</strong>
            {{ selectedZone.recommendation }}
          </div>
        </div>

        <div v-else class="card">
          <h2 class="section-label">Selected zone</h2>
          <p class="muted" style="margin: 0">
            No persistent inspection zones. Field may be visually uniform, or no field was detected.
          </p>
        </div>
      </div>

      <!-- Per-frame review -->
      <div ref="frameSectionEl">
        <FrameReview
          v-if="report.runId"
          :run-id="report.runId"
          :frames="report.frameQuality || []"
          :artifact-urls="job?.artifactUrls || {}"
          :frames-sampled="report.analysis.framesSampled"
          :focus-timestamp-sec="selectedZone?.firstSeenSec ?? null"
        />
      </div>

      <!-- Zone list -->
      <div class="card" v-if="zones.length">
        <div class="card-head">
          <h2 class="section-label" style="margin: 0">
            Inspection zones
            <span class="muted" style="letter-spacing: 0; text-transform: none; font-weight: 500">
              · {{ zones.length }}
            </span>
          </h2>
        </div>
        <div class="zone-list" style="max-height: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 0.65rem">
          <ZoneCard
            v-for="z in zones"
            :key="z.id"
            :zone="z"
            :selected="z.id === selectedZone?.id"
            @select="selectedZoneId = z.id"
          />
        </div>
      </div>

      <div class="limitations">
        <details>
          <summary>Limitations & method notes</summary>
          <ul>
            <li v-for="(l, i) in report.limitations" :key="i">{{ l }}</li>
          </ul>
          <p class="muted mono" style="margin: 0.75rem 0 0">
            Backend {{ report.analysis.segmentationBackend }} / {{ report.analysis.dinoBackend }}
            · device {{ report.analysis.device }}
            ·
            <a :href="artifactUrl('metrics.json')" target="_blank" rel="noopener">metrics.json</a>
          </p>
        </details>
      </div>
    </template>
  </div>
</template>
