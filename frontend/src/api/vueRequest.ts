import http from './http'
import type { ApiEndpointItem } from './vueApi'

export interface VueRequestContext {
  projects: string[]
  domain: string
  baseurl: string
  baseapi: string
  endpoints: ApiEndpointItem[]
  endpoints_error: string
  api_id: string
  method: string
  timeout: number
  json_body: string
  headers: string
  capture_request_total?: number
  capture_template_total?: number
  captured_requests?: VueCapturedRequest[]
  saved_results?: VueSavedRequestResult[]
  request_snapshots?: VueRequestRunSnapshot[]
}

export interface VueCapturedRequest {
  route_url?: string
  method: string
  url: string
  path?: string
  count?: number
  status?: number
  resource_type?: string
  content_type?: string
  query_string?: string
  query_params?: Record<string, unknown>
  request_body?: string
  body_type?: string
  body_json?: unknown
  body_form?: Record<string, unknown> | null
  request_headers?: Record<string, string>
}

export interface VueRequestInferResult {
  domain: string
  inferred: boolean
  baseurl: string
  baseapi: string
  captured_request_count: number
  endpoint_count: number
  matched: {
    endpoint_id: number
    endpoint_method: string
    endpoint_path: string
    request_url: string
    request_method: string
    request_count: number
  }
  compose_preview: Array<{
    id: number
    method: string
    path: string
    url: string
  }>
  error: string
}

export interface VueRequestInferEndpointInput {
  id?: number | string
  method?: string
  path?: string
  api_path?: string
  endpoint_path?: string
  url?: string
}

export interface VueRequestResult {
  job_id: string
  domain: string
  api_id: number
  method: string
  url: string
  baseurl: string
  baseapi: string
  base_query?: string
  status_code: number
  ok: boolean
  elapsed_ms: number
  error: string
  response_path: string
}

export interface VueRequestResponseDetail {
  endpoint_id: number
  method: string
  url: string
  status_code: number
  ok: boolean
  elapsed_ms: number
  response_headers: Record<string, string>
  response_text: string
  error: string
  request_body: unknown
  requested_at: string
}

export interface VueSavedRequestResult {
  match_key: string
  row_key: string
  endpoint_id: number
  path: string
  request_method: string
  url: string
  baseurl: string
  baseapi: string
  base_query?: string
  status_code: number
  ok: boolean
  elapsed_ms: number
  response_path: string
  response_length: number
  packet_length: number
  requested_at: string
  saved_at: string
  error: string
}

export type VueRequestBatchStatus = 'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'stopped'

export interface VueRequestBatchRowInput {
  row_key: string
  endpoint_id: number
  method: string
  path: string
}

export interface VueRequestBatchRowResult {
  row_key: string
  endpoint_id: number
  method: string
  path: string
  url: string
  status_code: number
  ok: boolean
  elapsed_ms: number
  error: string
  response_path: string
  requested_at: string
  response_length: number
  packet_length: number
  template_replay?: Record<string, unknown>
}

export interface VueRequestBatchJob {
  job_id: string
  step: string
  status: VueRequestBatchStatus
  error: string
  created_at: string
  updated_at: string
  finished_at: string
  domain: string
  method: string
  baseurl: string
  baseapi: string
  base_query?: string
  timeout: number
  concurrency: number
  use_capture_template: boolean
  total: number
  done_count: number
  ok_count: number
  fail_count: number
  current_row_key: string
  current_path: string
  row_results: Record<string, VueRequestBatchRowResult>
  row_result_total: number
  progress: {
    done: number
    total: number
    ok: number
    failed: number
    phase: string
    stop_requested: boolean
  }
  logs?: Array<{
    time: string
    message: string
  }>
  log_count?: number
  result: Record<string, unknown>
}

export interface VueRequestRunSnapshotRow {
  row_key: string
  endpoint_id: number
  method: string
  path: string
  url: string
  status_code: number
  ok: boolean
  elapsed_ms: number
  error: string
  response_path: string
  requested_at: string
  response_length: number
  packet_length: number
}

export interface VueRequestRunSnapshot {
  snapshot_id: string
  job_id: string
  run_index: number
  title: string
  status: string
  created_at: string
  updated_at: string
  request: {
    method: string
    baseurl: string
    baseapi: string
    base_query: string
    headers: string
    body_type: 'json' | 'form'
    body_text: string
    use_capture_template: boolean
    total: number
  }
  summary: {
    total: number
    done: number
    ok: number
    fail: number
  }
  rows: VueRequestRunSnapshotRow[]
}

interface ApiResponse {
  ok: boolean
  error?: string
  [key: string]: unknown
}

export async function fetchVueRequestContext(domain?: string) {
  const { data } = await http.get<ApiResponse>('/api/vueRequest/context', {
    params: { domain: domain || '' },
  })
  return (data || {}) as ApiResponse & VueRequestContext
}

export async function runVueRequest(input: {
  domain: string
  api_id: string | number
  method?: string
  baseurl?: string
  baseapi?: string
  base_query?: string
  timeout?: number
  json_body?: string
  body_type?: 'json' | 'form'
  body_text?: string
  content_type?: string
  headers?: string
  use_capture_template?: boolean
  request_url_override?: string
}) {
  const { data } = await http.post<ApiResponse>('/api/vueRequest/request', {
    domain: input.domain,
    api_id: input.api_id,
    method: input.method || '',
    baseurl: input.baseurl || '',
    baseapi: input.baseapi || '',
    base_query: input.base_query || '',
    timeout: Number(input.timeout || 20),
    json_body: input.json_body || '',
    body_type: input.body_type || 'json',
    body_text: input.body_text || '',
    content_type: input.content_type || '',
    headers: input.headers || '',
    use_capture_template: input.use_capture_template !== false,
    request_url_override: input.request_url_override || '',
  })
  return {
    requestResult: (data.request_result || {}) as VueRequestResult,
    responseDetail: (data.response_detail || {}) as VueRequestResponseDetail,
  }
}

export async function inferVueRequestBase(domain: string) {
  const { data } = await http.post<ApiResponse>('/api/vueRequest/infer-base', {
    domain,
  })
  return {
    inferResult: (data.infer_result || {}) as VueRequestInferResult,
  }
}

export async function inferVueRequestBaseFromPaths(input: {
  domain: string
  endpoints: VueRequestInferEndpointInput[]
}) {
  const { data } = await http.post<ApiResponse>('/api/vueRequest/infer-base-from-paths', {
    domain: input.domain,
    endpoints: Array.isArray(input.endpoints) ? input.endpoints : [],
  })
  return {
    inferResult: (data.infer_result || {}) as VueRequestInferResult,
  }
}

export async function runVueRequestBatch(input: {
  domain: string
  rows: VueRequestBatchRowInput[]
  method?: string
  baseurl?: string
  baseapi?: string
  base_query?: string
  timeout?: number
  json_body?: string
  body_type?: 'json' | 'form'
  body_text?: string
  content_type?: string
  headers?: string
  use_capture_template?: boolean
  concurrency?: number
}) {
  const { data } = await http.post<ApiResponse>('/api/vueRequest/request-batch', {
    domain: input.domain,
    rows: Array.isArray(input.rows) ? input.rows : [],
    method: input.method || '',
    baseurl: input.baseurl || '',
    baseapi: input.baseapi || '',
    base_query: input.base_query || '',
    timeout: Number(input.timeout || 20),
    json_body: input.json_body || '',
    body_type: input.body_type || 'json',
    body_text: input.body_text || '',
    content_type: input.content_type || '',
    headers: input.headers || '',
    use_capture_template: input.use_capture_template !== false,
    concurrency: Number(input.concurrency || 16),
  })
  return {
    job: (data.job || {}) as VueRequestBatchJob,
  }
}

export async function fetchVueRequestJob(jobId: string) {
  const { data } = await http.get<ApiResponse>(`/api/vueRequest/jobs/${encodeURIComponent(jobId)}`)
  return {
    job: (data.job || {}) as VueRequestBatchJob,
  }
}

export async function pauseVueRequestJob(jobId: string) {
  const { data } = await http.post<ApiResponse>(`/api/vueRequest/jobs/${encodeURIComponent(jobId)}/pause`)
  return {
    job: (data.job || {}) as VueRequestBatchJob,
  }
}

export async function resumeVueRequestJob(jobId: string) {
  const { data } = await http.post<ApiResponse>(`/api/vueRequest/jobs/${encodeURIComponent(jobId)}/resume`)
  return {
    job: (data.job || {}) as VueRequestBatchJob,
  }
}

export async function stopVueRequestJob(jobId: string) {
  const { data } = await http.post<ApiResponse>(`/api/vueRequest/jobs/${encodeURIComponent(jobId)}/stop`)
  return {
    job: (data.job || {}) as VueRequestBatchJob,
  }
}

export async function fetchVueRequestResponseDetail(responsePath: string) {
  const { data } = await http.get<ApiResponse>('/api/vueRequest/response-detail', {
    params: {
      response_path: responsePath,
    },
  })
  return {
    responseDetail: (data.response_detail || {}) as VueRequestResponseDetail,
  }
}

export async function saveVueRequestResult(input: {
  domain: string
  row_key: string
  endpoint_id: number
  path: string
  response_length?: number
  packet_length?: number
  request_result: VueRequestResult
  response_detail?: VueRequestResponseDetail | null
}) {
  const { data } = await http.post<ApiResponse>('/api/vueRequest/save-result', {
    domain: input.domain,
    row_key: input.row_key,
    endpoint_id: Number(input.endpoint_id || 0),
    path: input.path || '',
    response_length: Number(input.response_length || 0),
    packet_length: Number(input.packet_length || 0),
    request_result: input.request_result || {},
    response_detail: input.response_detail || {},
  })
  return {
    savedResult: (data.saved_result || {}) as VueSavedRequestResult,
    savedResults: Array.isArray(data.saved_results) ? (data.saved_results as VueSavedRequestResult[]) : [],
  }
}

export async function saveVueRequestResults(input: {
  domain: string
  rows: Array<{
    row_key: string
    endpoint_id: number
    path: string
    response_length?: number
    packet_length?: number
    request_result: VueRequestResult
    response_detail?: VueRequestResponseDetail | null
  }>
}) {
  const { data } = await http.post<ApiResponse>('/api/vueRequest/save-results', {
    domain: input.domain,
    rows: Array.isArray(input.rows) ? input.rows : [],
  })
  return {
    savedCount: Number(data.saved_count || 0),
    savedResults: Array.isArray(data.saved_results) ? (data.saved_results as VueSavedRequestResult[]) : [],
  }
}

export async function fetchVueRequestRunSnapshots(domain: string) {
  const { data } = await http.get<ApiResponse>('/api/vueRequest/run-snapshots', {
    params: {
      domain,
    },
  })
  return {
    snapshots: Array.isArray(data.snapshots) ? (data.snapshots as VueRequestRunSnapshot[]) : [],
  }
}

export async function saveVueRequestRunSnapshot(input: {
  domain: string
  job_id: string
  status: string
  request: Record<string, unknown>
  rows: Record<string, unknown>[]
}) {
  const { data } = await http.post<ApiResponse>('/api/vueRequest/save-snapshot', {
    domain: input.domain,
    job_id: input.job_id,
    status: input.status,
    request: input.request || {},
    rows: Array.isArray(input.rows) ? input.rows : [],
  })
  return {
    snapshot: (data.snapshot || {}) as VueRequestRunSnapshot,
    snapshots: Array.isArray(data.snapshots) ? (data.snapshots as VueRequestRunSnapshot[]) : [],
  }
}

export async function deleteVueRequestRunSnapshot(input: { domain: string; snapshot_id: string }) {
  const { data } = await http.post<ApiResponse>('/api/vueRequest/delete-snapshot', {
    domain: input.domain,
    snapshot_id: input.snapshot_id,
  })
  return {
    snapshots: Array.isArray(data.snapshots) ? (data.snapshots as VueRequestRunSnapshot[]) : [],
  }
}
