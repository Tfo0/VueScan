import http from './http'

export interface GlobalSettings {
  scan_concurrency: number
  proxy_server: string
  regex_list: string[]
  default_regex_index: number
  ai_provider: string
  ai_api_key: string
  ai_base_url: string
  ai_model: string
}

interface ApiResponse {
  ok: boolean
  error?: string
  [key: string]: unknown
}

function normalizeGlobalSettings(raw: unknown): GlobalSettings {
  const payload = (raw || {}) as Record<string, unknown>
  const regexListRaw = Array.isArray(payload.regex_list) ? payload.regex_list : []
  const regexList = regexListRaw
    .map((item) => String(item || '').trim())
    .filter((item, index, arr) => Boolean(item) && arr.indexOf(item) === index)

  const fallbackRegex = 'return\\s*Object\\(\\w\\.\\w\\)\\(\\{\\s*url:\"([^\"]*)'
  const finalRegexList = regexList.length > 0 ? regexList : [fallbackRegex]
  const defaultIndexRaw = Number(payload.default_regex_index || 0)
  const defaultIndex = Number.isFinite(defaultIndexRaw)
    ? Math.max(0, Math.min(finalRegexList.length - 1, Math.trunc(defaultIndexRaw)))
    : 0

  return {
    scan_concurrency: Math.max(1, Number(payload.scan_concurrency || 10)),
    proxy_server: String(payload.proxy_server || ''),
    regex_list: finalRegexList,
    default_regex_index: defaultIndex,
    ai_provider: String(payload.ai_provider || payload.provider || payload.deepseek_provider || 'deepseek'),
    ai_api_key: String(payload.ai_api_key || payload.deepseek_api_key || ''),
    ai_base_url: String(payload.ai_base_url || payload.deepseek_base_url || 'https://api.deepseek.com'),
    ai_model: String(payload.ai_model || payload.deepseek_model || 'deepseek-chat'),
  }
}

export async function fetchGlobalSettings() {
  const { data } = await http.get<ApiResponse>('/api/settings/global')
  return {
    settings: normalizeGlobalSettings(data.settings),
  }
}

export async function saveGlobalSettings(settings: Partial<GlobalSettings>) {
  const { data } = await http.post<ApiResponse>('/api/settings/global', settings)
  return {
    settings: normalizeGlobalSettings(data.settings),
  }
}
