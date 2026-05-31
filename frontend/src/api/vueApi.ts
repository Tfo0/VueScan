import http from './http'

export interface ApiEndpointItem {
  id: number
  method: string
  path: string
  url: string
  source_file: string
  source_line: number
  match_text: string
}

export interface VueApiContext {
  projects: string[]
  domain: string
  js_files: string[]
  js_urls: string[]
  js_file: string
  js_url: string
  pattern: string
  extract_result?: VueApiExtractResult & {
    source_type?: string
    source?: string
    source_name?: string
  }
  llm_analysis?: Record<string, unknown>
}

export interface VueApiSourcePreview {
  source_type: string
  source: string
  source_name: string
  raw_chars: number
  code: string
  truncated: boolean
}

export interface VueApiBeautify {
  domain: string
  source_type: string
  source: string
  source_name: string
  raw_chars: number
  beautified_chars: number
  truncated: boolean
  code: string
}

export interface VueApiPreviewResult {
  domain: string
  source_type: string
  source: string
  source_name: string
  js_file_count?: number
  count: number
  endpoints: ApiEndpointItem[]
}

export interface VueApiExtractResult {
  job_id: string
  domain: string
  endpoint_count: number
  count?: number
  endpoints?: ApiEndpointItem[]
  output_path: string
}

export interface VueApiAutoRegexCandidate {
  pattern: string
  source: string
  label?: string
  note?: string
  endpoint_count?: number
  score?: number
  overlap_count?: number
  target_hit?: boolean
  sample_paths?: string[]
  error: string
}

export interface VueApiAutoRegexResult {
  domain: string
  js_api_path?: string
  target_api: string
  target_path: string
  target_candidates: string[]
  js_file: string
  capture_path_count: number
  candidate_count: number
  candidates: VueApiAutoRegexCandidate[]
  selected_pattern: string
  mode?: string
  ai_provider?: string
  ai_model?: string
  ai_enabled?: boolean
  ai_used?: boolean
  ai_pattern_count?: number
  ai_error?: string
}

interface ApiResponse {
  ok: boolean
  error?: string
  [key: string]: unknown
}

export async function fetchVueApiContext(domain?: string) {
  const { data } = await http.get<ApiResponse>('/api/vueApi/context', {
    params: { domain: domain || '' },
  })
  return (data || {}) as ApiResponse & VueApiContext
}

export async function fetchVueApiSourcePreview(input: {
  domain: string
  js_file?: string
  js_url?: string
  pattern?: string
}) {
  const { data } = await http.post<ApiResponse>('/api/vueApi/source-preview', {
    domain: input.domain,
    js_file: input.js_file || '',
    js_url: input.js_url || '',
    pattern: input.pattern || '',
  })
  return (data.source_preview || {}) as VueApiSourcePreview
}

export async function runVueApiBeautify(input: {
  domain: string
  js_file?: string
  js_url?: string
  pattern?: string
}) {
  const { data } = await http.post<ApiResponse>('/api/vueApi/beautify', {
    domain: input.domain,
    js_file: input.js_file || '',
    js_url: input.js_url || '',
    pattern: input.pattern || '',
  })
  return {
    beautify: (data.beautify || {}) as VueApiBeautify,
    sourcePreview: (data.source_preview || {}) as VueApiSourcePreview,
  }
}

export async function runVueApiPreview(input: {
  domain: string
  pattern: string
  js_file?: string
  js_url?: string
}) {
  const { data } = await http.post<ApiResponse>('/api/vueApi/preview', {
    domain: input.domain,
    pattern: input.pattern,
    js_file: input.js_file || '',
    js_url: input.js_url || '',
  }, {
    timeout: 10 * 60 * 1000,
  })
  return (data.preview || {}) as VueApiPreviewResult
}

export async function runVueApiExtract(input: { domain: string; pattern: string }) {
  const { data } = await http.post<ApiResponse>('/api/vueApi/extract', {
    domain: input.domain,
    pattern: input.pattern,
  }, {
    timeout: 10 * 60 * 1000,
  })
  return (data.extract_result || {}) as VueApiExtractResult
}

export async function saveVueApiPreview(input: {
  domain: string
  pattern: string
  source_type?: string
  source?: string
  source_name?: string
  endpoints: ApiEndpointItem[]
}) {
  const { data } = await http.post<ApiResponse>('/api/vueApi/save-preview', {
    domain: input.domain,
    pattern: input.pattern,
    source_type: input.source_type || '',
    source: input.source || '',
    source_name: input.source_name || '',
    endpoints: Array.isArray(input.endpoints) ? input.endpoints : [],
  })
  return (data.extract_result || {}) as VueApiExtractResult
}

export interface ApiLlmAnalysisItem {
  api: string
  llm: string
  attack: string
}

export interface ApiLlmUnauthorizedItem {
  path: string
  reason: string
}

export interface ApiLlmWebVuln {
  vuln: string
  paths: string[]
  detail: string
}

export interface ApiLlmAttackChain {
  title: string
  steps: string[]
  impact: string
}

export interface ApiLlmAnalyzeResult {
  business_analysis: string
  unauthorized_suggestions: ApiLlmUnauthorizedItem[]
  web_analysis: ApiLlmWebVuln[]
  attack_chains: ApiLlmAttackChain[]
  api_analysis: ApiLlmAnalysisItem[]
  batch_total: number
  batch_done: number
  error?: string
}

export async function saveVueApiLlmAnalysis(domain: string, result: ApiLlmAnalyzeResult) {
  const { data } = await http.post<ApiResponse>('/api/vueApi/llm-save', { domain, result })
  return data as ApiResponse & { saved?: boolean; output_path?: string }
}

export async function startVueApiLlmAnalyze(domain: string, paths?: string[]) {
  const body: Record<string, unknown> = { domain }
  if (paths && paths.length > 0) body.paths = paths
  const { data } = await http.post<ApiResponse>('/api/vueApi/llm-analyze', body)
  return { job_id: String(data.job_id || '') }
}

export interface LlmAnalyzeJob {
  job_id: string
  status: string
  error: string
  logs: Array<{ time: string; message: string }>
  result: Partial<ApiLlmAnalyzeResult>
}

export async function pollVueApiLlmJob(jobId: string) {
  const { data } = await http.get<ApiResponse>(`/api/vueApi/llm-jobs/${encodeURIComponent(jobId)}`)
  return data as ApiResponse & LlmAnalyzeJob
}

export async function runVueApiAutoRegex(input: {
  domain: string
  jsApiPath?: string
  targetApi?: string
  js_file?: string
  maxCandidates?: number
}) {
  const { data } = await http.post<ApiResponse>('/api/vueApi/auto-regex', {
    domain: input.domain,
    js_api_path: input.jsApiPath || '',
    target_api: input.targetApi || '',
    js_file: input.js_file || '',
    max_candidates: Number(input.maxCandidates || 3),
  }, {
    timeout: 10 * 60 * 1000,
  })
  return (data.auto_regex || {}) as VueApiAutoRegexResult
}

