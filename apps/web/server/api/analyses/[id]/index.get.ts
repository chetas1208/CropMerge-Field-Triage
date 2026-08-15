import { loadJob } from '../../../utils/db'

export default defineEventHandler((event) => {
  const id = getRouterParam(event, 'id')
  if (!id) throw createError({ statusCode: 400, statusMessage: 'Missing id' })
  const job = loadJob(id)
  if (!job) throw createError({ statusCode: 404, statusMessage: 'Analysis not found' })
  return job
})
