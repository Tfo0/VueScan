import http from './http'

export interface DetectUrlRow {
  url: string
  title: string
  route_count: number
}

export interface DetectTask {
  task_id: string
  title: string
  status: string
  job_id: string
  input_path: string
  params: Record<string, unknown>
  result: Record<string, unknown>
  urls: DetectUrlRow[]
  url_count: number
  error: string
  created_at: string
  updated_at: string
}

interface ApiResponse {
  ok: boolean
  error?: string
  [key: string]: unknown
}

function toRouteCount(raw: unknown) {
  const value = Number(raw)
  if (!Number.isFinite(value) || value < 0) return 0
  return Math.floor(value)
}

function normalizeDetectUrls(raw: unknown): DetectUrlRow[] {
  if (!Array.isArray(raw)) return []
  const rows: DetectUrlRow[] = []
  const seen = new Set<string>()
  raw.forEach((item) => {
    let url = ''
    let title = ''
    let routeCount = 0
    if (item && typeof item === 'object') {
      const row = item as Record<string, unknown>
      url = String(row.url || row.final_url || '').trim()
      title = String(row.title || '').trim()
      routeCount = toRouteCount(row.route_count ?? row.routeCount ?? 0)
    } else {
      url = String(item || '').trim()
    }
    if (!url || seen.has(url)) return
    seen.add(url)
    rows.push({
      url,
      title,
      route_count: routeCount,
    })
  })
  return rows
}

function normalizeDetectTask(raw: unknown): DetectTask | null {
  if (!raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>
  const urls = normalizeDetectUrls(row.urls)
  return {
    task_id: String(row.task_id || '').trim(),
    title: String(row.title || '').trim(),
    status: String(row.status || '').trim(),
    job_id: String(row.job_id || '').trim(),
    input_path: String(row.input_path || '').trim(),
    params: (row.params && typeof row.params === 'object' ? row.params : {}) as Record<string, unknown>,
    result: (row.result && typeof row.result === 'object' ? row.result : {}) as Record<string, unknown>,
    urls,
    url_count: Number.isFinite(Number(row.url_count)) ? Number(row.url_count) : urls.length,
    error: String(row.error || '').trim(),
    created_at: String(row.created_at || '').trim(),
    updated_at: String(row.updated_at || '').trim(),
  }
}

export async function fetchVueDetectTasks() {
  const { data } = await http.get<ApiResponse>('/api/vueDetect/tasks')
  const rawTasks = Array.isArray(data.tasks) ? data.tasks : []
  const tasks = rawTasks
    .map((item) => normalizeDetectTask(item))
    .filter((item): item is DetectTask => Boolean(item))
  const selectedTaskId = String(data.selected_task_id || '')
  const selectedTaskFromPayload = normalizeDetectTask(data.selected_task)
  const selectedTask = selectedTaskFromPayload || tasks.find((item) => item.task_id === selectedTaskId) || null
  return {
    tasks,
    selectedTaskId,
    selectedTask,
    hasRunningTasks: Boolean(data.has_running_tasks),
  }
}

export async function fetchVueDetectTask(taskId: string) {
  const { data } = await http.get<ApiResponse>(`/api/vueDetect/tasks/${encodeURIComponent(taskId)}`)
  return normalizeDetectTask(data.task) || null
}

export async function createVueDetectTask(input: {
  taskName: string
  concurrency: number
  file: File
}) {
  const formData = new FormData()
  formData.set('task_name', input.taskName)
  formData.set('concurrency', String(input.concurrency))
  formData.set('upload_file', input.file)
  const { data } = await http.post<ApiResponse>('/api/vueDetect/tasks', formData)
  return {
    task: normalizeDetectTask(data.task),
    jobId: (data.job_id as string) || '',
  }
}

export async function deleteVueDetectTask(taskId: string) {
  await http.delete(`/api/vueDetect/tasks/${encodeURIComponent(taskId)}`)
}

export async function pauseVueDetectJob(jobId: string) {
  const { data } = await http.post<ApiResponse>(`/api/vueDetect/jobs/${encodeURIComponent(jobId)}/pause`)
  return {
    task: normalizeDetectTask(data.task) || null,
    job: (data.job as Record<string, unknown>) || null,
  }
}

export async function resumeVueDetectJob(jobId: string) {
  const { data } = await http.post<ApiResponse>(`/api/vueDetect/jobs/${encodeURIComponent(jobId)}/resume`)
  return {
    task: normalizeDetectTask(data.task) || null,
    job: (data.job as Record<string, unknown>) || null,
  }
}

export async function createProjectFromDetectTask(taskId: string, url: string, title = '') {
  const { data } = await http.post<ApiResponse>(
    `/api/vueDetect/tasks/${encodeURIComponent(taskId)}/projects`,
    { url, title },
  )
  return {
    project: (data.project as {
      domain: string
      title: string
      source: string
      seed_urls: string[]
      task_ids: string[]
      created_at: string
      updated_at: string
    }) || null,
    syncJob: (data.sync_job as {
      job_id: string
      status: string
    }) || null,
  }
}
