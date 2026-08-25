<script setup lang="ts">
import type { InspectionZone } from '@cropmerge/types'
import { zoneHeadline } from '~/composables/useFieldBrief'

defineProps<{
  zone: InspectionZone
  selected?: boolean
}>()
defineEmits<{ select: [] }>()
</script>

<template>
  <button type="button" class="zone" :class="{ selected }" @click="$emit('select')">
    <div class="zone-head">
      <span class="zone-id">{{ zone.id }}</span>
      <span class="priority" :class="zone.reviewPriority">{{ zone.reviewPriority }}</span>
    </div>
    <p class="zone-loc">{{ zoneHeadline(zone) }}</p>
    <div class="zone-metrics">
      <div class="zone-metric">
        <label>Anomaly</label>
        <strong>{{ zone.anomalyScore.toFixed(2) }}</strong>
        <ScoreBar :value="zone.anomalyScore" :tone="zone.reviewPriority" />
      </div>
      <div class="zone-metric">
        <label>Persistence</label>
        <strong>{{ zone.persistenceScore.toFixed(2) }}</strong>
        <ScoreBar :value="zone.persistenceScore" />
      </div>
    </div>
  </button>
</template>
