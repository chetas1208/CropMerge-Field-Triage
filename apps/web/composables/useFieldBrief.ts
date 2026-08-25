import type { FieldTriageReport, InspectionZone } from '@cropmerge/types'
import type { Ref } from 'vue'

const REVIEW_ANOMALY_WEIGHT = 0.65
const REVIEW_PERSISTENCE_WEIGHT = 0.35

export function combinedReviewScore(zone: InspectionZone): number {
  return REVIEW_ANOMALY_WEIGHT * zone.anomalyScore + REVIEW_PERSISTENCE_WEIGHT * zone.persistenceScore
}

function pct(n: number) {
  return `${Math.round(n * 100)}%`
}

function locLabel(location: string) {
  return location.replace(/_/g, ' ').replace(/-/g, ' ')
}

export function zoneHeadline(zone: InspectionZone): string {
  const loc = locLabel(zone.relativeLocation)
  const review = combinedReviewScore(zone)
  if (zone.reasons[0]) {
    const short = zone.reasons[0].split('(')[0].trim()
    return `${loc}: ${short} · review ${pct(review)}`
  }
  return `${loc} patch · review ${pct(review)}`
}

export function useFieldBrief(report: Ref<FieldTriageReport | null | undefined>, zones: Ref<InspectionZone[]>) {
  const brief = computed(() => {
    const r = report.value
    const z = zones.value
    if (!r) return ''

    const duration = r.source.durationSec?.toFixed?.(0) ?? '?'
    const frames = r.analysis.framesSampled
    const crop = pct(r.field.meanCropCoverage)
    const soil = pct(r.field.meanBareSoil)

    if (!r.field.detected) {
      return `Scanned ${frames} frames from a ${duration}s clip but couldn't lock onto a clean field boundary — might be bare ground, tree line, or the camera angle. Try a higher pass or tighter crop.`
    }

    if (!z.length) {
      return `Clean bill of health for this pass: ${crop} crop cover, ${soil} bare soil, ${frames} frames sampled. Nothing stuck around long enough to flag — either a uniform field or the camera never lingered on the interesting bits.`
    }

    const high = z.filter((x) => x.reviewPriority === 'high').length
    const med = z.filter((x) => x.reviewPriority === 'medium').length
    const top = [...z].sort((a, b) => combinedReviewScore(b) - combinedReviewScore(a))[0]
    const topLoc = locLabel(top.relativeLocation)
    const topReview = pct(combinedReviewScore(top))

    let opener = `After ${frames} frames (${duration}s of flight), the field reads ${crop} canopy / ${soil} exposed soil. `
    if (high) {
      opener += `${high} zone${high > 1 ? 's' : ''} want a closer look first`
      if (med) opener += `, plus ${med} maybe-later bookmark${med > 1 ? 's' : ''}`
      opener += `. `
    } else if (med) {
      opener += `${med} patch${med > 1 ? 'es' : ''} drift from the norm — nothing screaming, but worth a second pass. `
    } else {
      opener += `${z.length} mild variation${z.length > 1 ? 's' : ''} — mostly "keep an eye on it" territory. `
    }

    opener += `Hottest spot: ${topLoc} (review score ${topReview} = ${pct(REVIEW_ANOMALY_WEIGHT)} how weird + ${pct(REVIEW_PERSISTENCE_WEIGHT)} how persistent). `
    opener += `These are visual diffs from the surrounding crop — not disease, nutrient, or yield calls.`
    return opener
  })

  const loadingLines = [
    'Decoding your flight path…',
    'Separating crop from road, trees, and sky…',
    'Scoring each grid cell like a picky agronomist with a RGB camera…',
    'Finding patches that refuse to blend in…',
    'Rendering the annotated fly-through…',
  ]

  return { brief, loadingLines, zoneHeadline, combinedReviewScore }
}
