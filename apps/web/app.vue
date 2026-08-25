<script setup lang="ts">
const health = ref<{
  ok?: boolean
  db?: { ok?: boolean; mode?: string }
  vision?: { status?: string; device?: string; segmentationBackend?: string }
} | null>(null)
const { request } = useVisionApi()

onMounted(async () => {
  try {
    const vision = await request<NonNullable<typeof health.value>['vision']>('/vision/health', {}, false)
    health.value = { ok: vision?.status === 'ok', vision }
  } catch {
    health.value = { ok: false }
  }
})

const visionOk = computed(() => health.value?.vision?.status === 'ok')
const dbOk = computed(() => health.value?.db?.ok !== false)
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <NuxtLink to="/" class="brand" style="text-decoration: none; color: inherit">
        <div class="brand-mark" aria-hidden="true" />
        <div class="brand-text">
          <span class="logo">CropMerge</span>
          <span class="product">Field Triage</span>
        </div>
      </NuxtLink>

      <div class="topbar-right">
        <span class="chip" :class="visionOk ? 'ok' : 'bad'" title="Vision engine">
          <span class="dot" />
          Vision {{ visionOk ? 'online' : 'offline' }}
        </span>
        <span class="chip" :class="dbOk ? 'ok' : 'warn'" title="Product database">
          <span class="dot" />
          DB {{ health?.db?.mode || 'sqlite' }}
        </span>
        <span v-if="health?.vision?.device" class="chip">
          {{ health.vision.device }}
          <template v-if="health.vision.segmentationBackend">
            · {{ health.vision.segmentationBackend }}
          </template>
        </span>
      </div>
    </header>

    <main class="main">
      <NuxtPage />
    </main>

    <footer class="footer">
      <p>
        Exploratory RGB analysis for human review — not disease, nutrient, irrigation, or yield diagnosis.
        Image-relative maps are not georeferenced unless GPS is present.
      </p>
    </footer>
  </div>
</template>
