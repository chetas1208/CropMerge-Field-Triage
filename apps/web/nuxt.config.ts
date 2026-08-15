import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../..', import.meta.url))

export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    visionServiceUrl: process.env.VISION_SERVICE_URL || 'http://127.0.0.1:8001',
    outputsDir: process.env.OUTPUTS_DIR || `${root}/outputs`,
    uploadsDir: process.env.UPLOADS_DIR || `${root}/data/uploads`,
    databaseDir: process.env.DATABASE_DIR || `${root}/data/db`,
    databaseUrl:
      process.env.DATABASE_URL ||
      process.env.NUXT_DATABASE_URL ||
      `sqlite:///${root}/data/db/cropmerge.sqlite`,
    public: {
      appName: process.env.NUXT_PUBLIC_APP_NAME || 'CropMerge Field Triage',
    },
  },
  typescript: {
    strict: true,
    typeCheck: false,
  },
  app: {
    head: {
      title: 'CropMerge Field Triage',
      meta: [
        {
          name: 'description',
          content:
            'RGB drone video → field segmentation → visual anomaly mapping → farmer review',
        },
      ],
    },
  },
})
