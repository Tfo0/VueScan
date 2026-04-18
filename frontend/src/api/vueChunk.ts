import http from './http'

export type SyncStatus = 'queued' | 'running' | 'paused' | 'done' | 'failed' | 'stopped' | 'idle'

export interface JobLogEntry {
  time: string
  message: string
}

export interface PaginationMeta {
  page: number
  page_size: number
  total: number
  total_pages: number
}

export interface SyncJob {
  job_id: string
  step: string
  status: SyncStatus
  error: string
  created_at: string
  updated_at: string
  finished_at: string
  domain: string
  mode?: 'zip' | 'local'
  target_url?: string
  concurrency?: number
  detect_routes?: boolean
  detect_js?: boolean
  total?: number
  downloaded_count?: number
  skipped_count?: number
  failed_count?: number
  progress?: {
    done?: number
    total?: number
    downloaded?: number
    skipped?: number
    failed?: number
    phase?: string
    visited_route_count?: number
    failed_route_count?: number
    request_total?: number
    stop_requested?: boolean
  }
  hash_style?: string
  basepath_override?: string
  manual_lock?: boolean
  probe?: Record<string, unknown>
  zip_path?: string
  local_dir?: string
  download_url?: string
  capture_file?: string
  visited_route_count?: number
  failed_route_count?: number
  request_total?: number
  stop_requested?: boolean
  current_route_url?: string
  current_js_url?: string
  current_file_name?: string
  recent_chunks?: string[]
  recent_requests?: string[]
  recent_js_urls?: string[]
  logs?: JobLogEntry[]
  log_count?: number
  result: Record<string, unknown>
}

export interface ProjectItem {
  domain: string
  title: string
  source: string
  seed_urls: string[]
  task_ids: string[]
  created_at: string
  updated_at: string
  route_count: number
  js_count: number
  saved_result_count: number
  request_value_level?: 'high' | 'medium' | 'low' | ''
  request_value_label?: string
  request_value_reason?: string
  request_value_score?: number
  request_value_snapshot_count?: number
  request_value_sample_count?: number
  sync: {
    job_id: string
    status: SyncStatus
    error: string
    updated_at: string
    target_url: string
    concurrency: number
    detect_routes: boolean
    detect_js: boolean
    detect_request: boolean
  }
  sync_status: SyncStatus
  sync_job_id: string
  sync_updated_at: string
  sync_error: string
  sync_step?: string
  sync_phase?: string
  sync_phase_text?: string
  last_activity_at: string
}

export interface ProjectDetailPayload {
  project: {
    domain: string
    title?: string
    source: string
    seed_urls: string[]
    task_ids: string[]
    created_at: string
    updated_at: string
    route_count?: number
    js_count?: number
    saved_result_count?: number
    request_value_level?: 'high' | 'medium' | 'low' | ''
    request_value_label?: string
    request_value_reason?: string
    request_value_score?: number
    request_value_snapshot_count?: number
    request_value_sample_count?: number
  }
  detail: {
    domain: string
    project_dir: string
    routes_file: string
    urls_file: string
    js_file: string
    request_capture_file: string
    route_profile_file: string
    route_url_profile: {
      hash_style: string
      basepath_override: string
      manual_lock: boolean
      source: string
      updated_at: string
      probe: Record<string, unknown>
    }
    router_dir: string
    chunk_dir: string
    route_count: number
    js_count: number
    chunk_count: number
    downloaded_chunk_count: number
    routes_preview: Array<Record<string, unknown>>
    routes_pagination: PaginationMeta
    urls_preview: string[]
    js_preview: string[]
    js_pagination: PaginationMeta
    request_preview: Array<{
      route_url: string
      method: string
      url: string
      count: number
      status: number
      resource_type: string
      content_type: string
      request_body: string
    }>
    manual_request_preview: Array<{
      route_url: string
      method: string
      url: string
      count: number
      status: number
      resource_type: string
      content_type: string
      request_body: string
    }>
    request_pagination: PaginationMeta
    request_route_map_total: number
    request_route_map_pagination: PaginationMeta
    request_route_map_preview: Array<{
      route_url: string
      chunk_count: number
      request_count: number
      unique_request_count: number
      chunks: string[]
      requests: Array<{
        method: string
        url: string
        count: number
        status: number
        resource_type: string
        content_type: string
      }>
    }>
    request_summary: {
      route_total: number
      visited_route_count: number
      failed_route_count: number
      request_total: number
      request_unique_total: number
      generated_at: string
    }
    manifest_summary: Record<string, unknown>
  }
  sync: SyncJob
  js_download: SyncJob
  request_capture: SyncJob
}

interface ApiResponse {
  ok: boolean
  error?: string
  [key: string]: unknown
}

export async function fetchVueChunkProjects(input?: { q?: string; page?: number; pageSize?: number; sort?: string }) {
  const { data } = await http.get<ApiResponse>('/api/vueChunk/projects', {
    params: {
      q: input?.q || '',
      page: Number(input?.page || 1),
      page_size: Number(input?.pageSize || 10),
      sort: input?.sort || 'updated_desc',
    },
  })
  return {
    total: Number(data.total || 0),
    page: Number(data.page || 1),
    pageSize: Number(data.page_size || 10),
    totalPages: Number(data.total_pages || 0),
    hasRunningJobs: Boolean(data.has_running_jobs),
    projects: (data.projects as ProjectItem[]) || [],
  }
}

export async function fetchVueChunkProjectDetail(
  domain: string,
  input?: {
    routePage?: number
    routePageSize?: number
    jsPage?: number
    jsPageSize?: number
    requestPage?: number
    requestPageSize?: number
    mapPage?: number
    mapPageSize?: number
    mapQ?: string
  },
) {
  const { data } = await http.get<ApiResponse>(`/api/vueChunk/projects/${encodeURIComponent(domain)}`, {
    params: {
      route_page: Number(input?.routePage || 1),
      route_page_size: Number(input?.routePageSize || 120),
      js_page: Number(input?.jsPage || 1),
      js_page_size: Number(input?.jsPageSize || 120),
      request_page: Number(input?.requestPage || 1),
      request_page_size: Number(input?.requestPageSize || 120),
      map_page: Number(input?.mapPage || 1),
      map_page_size: Number(input?.mapPageSize || 120),
      map_q: String(input?.mapQ || ''),
    },
  })
  return {
    project: (data.project || {}) as ProjectDetailPayload['project'],
    detail: (data.detail || {}) as ProjectDetailPayload['detail'],
    sync: ((data.sync || {}) as ProjectDetailPayload['sync']) || ({} as ProjectDetailPayload['sync']),
    jsDownload: ((data.js_download || {}) as ProjectDetailPayload['js_download']) || ({} as ProjectDetailPayload['js_download']),
    requestCapture: ((data.request_capture || {}) as ProjectDetailPayload['request_capture']) || ({} as ProjectDetailPayload['request_capture']),
  }
}

export async function createVueChunkProject(input: {
  targetUrl: string
  source: string
  concurrency: number
  detectRoutes: boolean
  detectJs: boolean
  detectRequest: boolean
  autoPipeline?: boolean
  pattern?: string
}) {
  const { data } = await http.post<ApiResponse>('/api/vueChunk/projects', {
    target_url: input.targetUrl,
    source: input.source,
    concurrency: Math.max(1, Number(input.concurrency || 5)),
    detect_routes: Boolean(input.detectRoutes),
    detect_js: Boolean(input.detectJs),
    detect_request: Boolean(input.detectRequest),
    auto_pipeline: Boolean(input.autoPipeline),
    pattern: String(input.pattern || ''),
  })
  return {
    project: (data.project || {}) as ProjectItem,
    syncJob: (data.sync_job || {}) as SyncJob,
  }
}

export async function retryVueChunkProject(domain: string, input?: Partial<{
  targetUrl: string
  source: string
  concurrency: number
  detectRoutes: boolean
  detectJs: boolean
  detectRequest: boolean
}>) {
  const { data } = await http.post<ApiResponse>(`/api/vueChunk/projects/${encodeURIComponent(domain)}/retry`, {
    target_url: input?.targetUrl || '',
    source: input?.source || 'vueChunk_retry',
    concurrency: Number(input?.concurrency || 5),
    detect_routes: input?.detectRoutes,
    detect_js: input?.detectJs,
    detect_request: input?.detectRequest,
  })
  return {
    project: (data.project || {}) as ProjectItem,
    syncJob: (data.sync_job || {}) as SyncJob,
  }
}

export async function scanVueChunkProject(domain: string, input?: Partial<{
  targetUrl: string
  source: string
  concurrency: number
  pattern: string
  proxyServer: string
}>) {
  const payload: Record<string, unknown> = {
    source: input?.source || 'vueChunk_scan',
  }
  if (input?.targetUrl) payload.target_url = input.targetUrl
  if (typeof input?.concurrency === 'number' && Number.isFinite(input.concurrency) && input.concurrency > 0) {
    payload.concurrency = Math.trunc(input.concurrency)
  }
  if (input?.pattern) payload.pattern = input.pattern
  if (input?.proxyServer) payload.proxy_server = input.proxyServer

  const { data } = await http.post<ApiResponse>(`/api/vueChunk/projects/${encodeURIComponent(domain)}/scan`, payload)
  return {
    project: (data.project || {}) as ProjectItem,
    syncJob: (data.sync_job || {}) as SyncJob,
    pattern: String(data.pattern || ''),
  }
}

export async function deleteVueChunkProject(domain: string, input?: { removeFiles?: boolean }) {
  const { data } = await http.delete<ApiResponse>(
    `/api/vueChunk/projects/${encodeURIComponent(domain)}`,
    {
      params: {
        remove_files: input?.removeFiles === false ? '0' : '1',
      },
    },
  )
  return {
    deletedProject: (data.deleted_project || {}) as ProjectItem,
  }
}

export async function updateVueChunkProjectTitle(domain: string, input: { title: string }) {
  const { data } = await http.post<ApiResponse>(
    `/api/vueChunk/projects/${encodeURIComponent(domain)}/title`,
    {
      title: String(input?.title || ''),
    },
  )
  return {
    project: (data.project || {}) as ProjectItem,
  }
}

export async function fetchVueChunkJob(jobId: string) {
  const { data } = await http.get<ApiResponse>(`/api/vueChunk/jobs/${encodeURIComponent(jobId)}`)
  return {
    job: (data.job || {}) as SyncJob,
  }
}

export async function stopVueChunkJob(jobId: string) {
  const { data } = await http.post<ApiResponse>(`/api/vueChunk/jobs/${encodeURIComponent(jobId)}/stop`)
  return {
    job: (data.job || {}) as SyncJob,
  }
}

export async function pauseVueChunkJob(jobId: string) {
  const { data } = await http.post<ApiResponse>(`/api/vueChunk/jobs/${encodeURIComponent(jobId)}/pause`)
  return {
    job: (data.job || {}) as SyncJob,
  }
}

export async function resumeVueChunkJob(jobId: string) {
  const { data } = await http.post<ApiResponse>(`/api/vueChunk/jobs/${encodeURIComponent(jobId)}/resume`)
  return {
    job: (data.job || {}) as SyncJob,
  }
}

export async function createVueChunkJsDownload(domain: string, input?: { concurrency?: number }) {
  const { data } = await http.post<ApiResponse>(
    `/api/vueChunk/projects/${encodeURIComponent(domain)}/js-download`,
    {
      concurrency: Number(input?.concurrency || 24),
    },
  )
  return {
    job: (data.job || {}) as SyncJob,
  }
}

export async function createVueChunkJsDownloadLocal(domain: string, input?: { concurrency?: number }) {
  const { data } = await http.post<ApiResponse>(
    `/api/vueChunk/projects/${encodeURIComponent(domain)}/js-download-local`,
    {
      concurrency: Number(input?.concurrency || 24),
    },
  )
  return {
    job: (data.job || {}) as SyncJob,
  }
}

export async function createVueChunkRequestCapture(domain: string, input?: { concurrency?: number }) {
  const { data } = await http.post<ApiResponse>(
    `/api/vueChunk/projects/${encodeURIComponent(domain)}/request-capture`,
    {
      concurrency: Number(input?.concurrency || 8),
    },
  )
  return {
    job: (data.job || {}) as SyncJob,
  }
}

export interface RequestLocateResult {
  domain: string
  request_url: string
  request_path: string
  method: string
  scan_scope?: 'auto' | 'related' | 'global'
  path_candidates: string[]
  related_route_total: number
  related_chunk_total: number
  candidate_file_total: number
  scanned_file_total: number
  hit_total: number
  hits: Array<{
    file_name: string
    matched_path: string
    line: number
    snippet: string
    chunk_url?: string
  }>
  related_routes: Array<{
    route_url: string
    chunk_count: number
    request_count: number
    unique_request_count: number
  }>
}

export async function saveVueChunkManualRequests(
  domain: string,
  input: {
    requests: Array<{
      route_url?: string
      method?: string
      url?: string
      count?: number
      status?: number
      resource_type?: string
      content_type?: string
      request_body?: string
    }>
  },
) {
  const { data } = await http.post<ApiResponse>(
    `/api/vueChunk/projects/${encodeURIComponent(domain)}/manual-requests`,
    {
      requests: Array.isArray(input?.requests) ? input.requests : [],
    },
  )
  return {
    manualRequests: (data.manual_requests as ProjectDetailPayload['detail']['manual_request_preview']) || [],
  }
}

export async function locateVueChunkRequest(
  domain: string,
  input: {
    requestUrl: string
    method?: string
    routeUrl?: string
    scanScope?: 'auto' | 'related' | 'global'
    maxFiles?: number
    maxResults?: number
  },
) {
  const { data } = await http.post<ApiResponse>(
    `/api/vueChunk/projects/${encodeURIComponent(domain)}/request-locate`,
    {
      request_url: input.requestUrl,
      method: input.method || 'GET',
      route_url: input.routeUrl || '',
      scan_scope: input.scanScope || 'auto',
      max_files: Number(input.maxFiles || 240),
      max_results: Number(input.maxResults || 80),
    },
  )
  return {
    result: (data.result || {}) as RequestLocateResult,
  }
}

export async function updateVueChunkRouteRewrite(
  domain: string,
  input: {
    hashStyle: 'slash' | 'plain'
    basepathOverride: string
    manualLock?: boolean
  },
) {
  const { data } = await http.post<ApiResponse>(
    `/api/vueChunk/projects/${encodeURIComponent(domain)}/route-rewrite`,
    {
      hash_style: input.hashStyle,
      basepath_override: input.basepathOverride,
      manual_lock: input.manualLock ?? true,
    },
  )
  return {
    profile: (data.profile || {}) as ProjectDetailPayload['detail']['route_url_profile'],
  }
}
