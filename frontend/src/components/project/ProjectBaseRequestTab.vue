<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import axios from 'axios'
import {
  fetchVueRequestContext,
  type VueCapturedRequest,
  type VueRequestInferResult,
} from '../../api/vueRequest'
import type {
  ProjectBaseRequestBodyType,
  ProjectBaseRequestFuzzParam,
  ProjectBaseRequestFuzzParamSource,
  ProjectBaseRequestPresetEnvelope,
} from './baseRequestTypes'

interface InferPreset {
  seq: number
  inferResult: VueRequestInferResult
}

interface QuerySample {
  key: string
  queryText: string
  queryTextSingleLine: string
  count: number
  sampleUrl: string
}

interface BodySample {
  key: string
  bodyText: string
  bodyTextSingleLine: string
  bodyType: ProjectBaseRequestBodyType
  count: number
  contentType: string
  sampleUrl: string
}

interface HeaderSample {
  key: string
  headersText: string
  headersTextSingleLine: string
  primaryLabel: string
  count: number
  sampleUrl: string
}

interface LocalFuzzParamCatalogItem extends ProjectBaseRequestFuzzParam {
  seedValuesRaw: unknown[]
  matchedApiKeys: string[]
  matchedApiLabels: string[]
  matchedApiCount: number
}

interface FuzzParamBucket {
  key: string
  sources: Set<ProjectBaseRequestFuzzParamSource>
  valueTypes: Set<string>
  sampleValues: Set<string>
  hitCount: number
  sampleUrls: Set<string>
  seedValues: Map<string, unknown>
  matchedApis: Map<string, string>
}

interface InferredApiOption {
  key: string
  method: string
  matchPath: string
  displayPath: string
  label: string
}

const props = defineProps<{
  domain: string
  refreshKey?: number
  inferPreset?: InferPreset | null
  baseRequestPreset?: ProjectBaseRequestPresetEnvelope | null
}>()

const emit = defineEmits<{
  (e: 'ready', payload: ProjectBaseRequestPresetEnvelope): void
}>()

const currentDomain = ref('')
const loading = ref(false)
const message = ref('')
const error = ref('')

const baseurl = ref('')
const baseapi = ref('')
const requestMethod = ref<'GET' | 'POST'>('GET')
const baseQueryText = ref('')
const baseBodyText = ref('')
const baseBodyType = ref<ProjectBaseRequestBodyType>('json')
const baseHeadersText = ref('')

const selectedQueryKey = ref('')
const selectedBodyKey = ref('')
const selectedHeaderKey = ref('')
const fuzzSearchText = ref('')
const fuzzSourceFilter = ref<'all' | ProjectBaseRequestFuzzParamSource>('body')
const fuzzApiFilter = ref('matched')
const selectedFuzzParamKeys = ref<string[]>([])

const captureRows = ref<VueCapturedRequest[]>([])
const captureRequestTotal = ref(0)
const captureTemplateTotal = ref(0)

function resolveError(err: unknown) {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: string } | undefined
    return data?.error || err.message || '请求失败'
  }
  if (err instanceof Error) return err.message
  return '未知错误'
}

function normalizeMethod(value: string) {
  return String(value || '').trim().toUpperCase() || 'GET'
}

function normalizeBaseBodyType(value: unknown): ProjectBaseRequestBodyType {
  return String(value || '').trim().toLowerCase() === 'form' ? 'form' : 'json'
}

function defaultBodyContentType(bodyType: ProjectBaseRequestBodyType) {
  return bodyType === 'form'
    ? 'application/x-www-form-urlencoded; charset=utf-8'
    : 'application/json'
}

function encodeQueryParams(raw: Record<string, unknown>) {
  const params = new URLSearchParams()
  Object.entries(raw || {}).forEach(([key, value]) => {
    if (!String(key || '').trim()) return
    if (value === undefined || value === null) return
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item === undefined || item === null) return
        params.append(String(key), String(item))
      })
      return
    }
    if (typeof value === 'object') {
      params.append(String(key), JSON.stringify(value))
      return
    }
    params.append(String(key), String(value))
  })
  return params.toString()
}

function stringifyPretty(raw: unknown, fallback = '') {
  if (raw === undefined || raw === null) return fallback
  if (typeof raw === 'string') return raw.trim() || fallback
  try {
    return JSON.stringify(raw, null, 2)
  } catch {
    return fallback
  }
}

function compactSingleLineText(value: string, maxLength = 120) {
  const normalized = String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!normalized) return ''
  if (normalized.length <= maxLength) return normalized
  return `${normalized.slice(0, maxLength)}...`
}

function buildQuerySample(raw: VueCapturedRequest): QuerySample | null {
  const queryText = String(raw.query_string || '').trim() || encodeQueryParams(raw.query_params || {})
  if (!queryText) return null
  return {
    key: queryText,
    queryText,
    queryTextSingleLine: compactSingleLineText(queryText, 96),
    count: Math.max(1, Number(raw.count || 1)),
    sampleUrl: String(raw.url || '').trim(),
  }
}

function pickHeaderValue(headers: Record<string, unknown>, targetKey: string) {
  const normalizedTarget = String(targetKey || '').trim().toLowerCase()
  if (!normalizedTarget) return ''
  const matchedKey = Object.keys(headers).find((key) => String(key || '').trim().toLowerCase() === normalizedTarget)
  if (!matchedKey) return ''
  const value = headers[matchedKey]
  if (value === undefined || value === null) return ''
  return String(value).trim()
}

function parseHeaderTextToMap(rawText: string) {
  const text = String(rawText || '').trim()
  if (!text) return {}
  try {
    const parsed = JSON.parse(text)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return Object.fromEntries(
        Object.entries(parsed as Record<string, unknown>).map(([key, value]) => [String(key), String(value ?? '')]),
      )
    }
  } catch {
    // fall through to "Header: value" parsing
  }
  const mapped: Record<string, string> = {}
  text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => Boolean(line))
    .forEach((line) => {
      const splitAt = line.indexOf(':')
      if (splitAt <= 0) return
      const key = line.slice(0, splitAt).trim()
      const value = line.slice(splitAt + 1).trim()
      if (!key) return
      mapped[key] = value
    })
  return mapped
}

function syncBaseHeaderContentType(bodyType: ProjectBaseRequestBodyType, preferred = '') {
  const nextHeaders = parseHeaderTextToMap(baseHeadersText.value)
  const normalizedContentType = String(preferred || '').trim() || defaultBodyContentType(bodyType)
  const existedKey = Object.keys(nextHeaders).find((key) => key.trim().toLowerCase() === 'content-type')
  nextHeaders[existedKey || 'Content-Type'] = normalizedContentType
  baseHeadersText.value = JSON.stringify(nextHeaders, null, 2)
}

function detectCapturedBodyType(raw: VueCapturedRequest): ProjectBaseRequestBodyType {
  const contentType = String(raw.content_type || '').trim().toLowerCase()
  if (contentType.includes('application/x-www-form-urlencoded')) return 'form'
  if (raw.body_form && typeof raw.body_form === 'object' && Object.keys(raw.body_form).length) {
    const requestBody = String(raw.request_body || '').trim()
    if (requestBody && !looksLikeJsonBody(requestBody)) return 'form'
  }
  return 'json'
}

function buildBodySample(raw: VueCapturedRequest): BodySample | null {
  const bodyType = detectCapturedBodyType(raw)
  let bodyText = ''
  if (bodyType === 'form') {
    const requestBody = String(raw.request_body || '').trim()
    bodyText = requestBody || encodeQueryParams(raw.body_form || {})
  } else if (raw.body_json !== undefined && raw.body_json !== null) {
    bodyText = stringifyPretty(raw.body_json, '')
  } else if (raw.body_form && Object.keys(raw.body_form).length) {
    bodyText = stringifyPretty(raw.body_form, '')
  } else {
    bodyText = String(raw.request_body || '').trim()
  }
  if (!bodyText) return null
  return {
    key: bodyText,
    bodyText,
    bodyTextSingleLine: compactSingleLineText(bodyText),
    bodyType,
    count: Math.max(1, Number(raw.count || 1)),
    contentType: String(raw.content_type || '').trim(),
    sampleUrl: String(raw.url || '').trim(),
  }
}

function buildHeaderSample(raw: VueCapturedRequest): HeaderSample | null {
  if (!raw.request_headers || typeof raw.request_headers !== 'object') return null
  const headerKeys = Object.keys(raw.request_headers)
  if (!headerKeys.length) return null
  const headersText = stringifyPretty(raw.request_headers, '')
  if (!headersText) return null
  const headerMap = raw.request_headers as Record<string, unknown>
  const contentType = pickHeaderValue(headerMap, 'content-type') || String(raw.content_type || '').trim()
  const authorization = pickHeaderValue(headerMap, 'authorization')
  const primaryLabel = contentType || authorization || compactSingleLineText(headersText, 96) || 'headers'
  return {
    key: headersText,
    headersText,
    headersTextSingleLine: compactSingleLineText(headersText, 96),
    primaryLabel,
    count: Math.max(1, Number(raw.count || 1)),
    sampleUrl: String(raw.url || '').trim(),
  }
}

function aggregateSamples<T extends { key: string; count: number; sampleUrl: string }>(samples: Array<T | null>) {
  const mapped = new Map<string, T>()
  samples.forEach((sample) => {
    if (!sample) return
    const existing = mapped.get(sample.key)
    if (!existing) {
      mapped.set(sample.key, { ...sample })
      return
    }
    existing.count += sample.count
    if (!existing.sampleUrl && sample.sampleUrl) {
      existing.sampleUrl = sample.sampleUrl
    }
  })
  return [...mapped.values()].sort((left, right) => {
    if (right.count !== left.count) return right.count - left.count
    return left.key.length - right.key.length
  })
}

function detectValueType(value: unknown) {
  if (Array.isArray(value)) return 'array'
  if (value === null) return 'null'
  const valueType = typeof value
  if (valueType === 'string') return 'string'
  if (valueType === 'number') return 'number'
  if (valueType === 'boolean') return 'boolean'
  if (valueType === 'object') return 'object'
  return valueType || 'unknown'
}

function normalizeSampleValue(value: unknown) {
  if (value === undefined) return ''
  if (typeof value === 'string') return compactSingleLineText(value, 72)
  if (typeof value === 'number' || typeof value === 'boolean' || value === null) {
    return compactSingleLineText(String(value), 72)
  }
  try {
    return compactSingleLineText(JSON.stringify(value), 72)
  } catch {
    return compactSingleLineText(String(value), 72)
  }
}

function normalizeSeedValueKey(value: unknown) {
  if (value === undefined) return 'undefined'
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function cloneSeedValue<T>(value: T): T {
  if (value === undefined || value === null) return value
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return value
  try {
    return JSON.parse(JSON.stringify(value)) as T
  } catch {
    return value
  }
}

function looksLikeJsonBody(value: string) {
  const text = String(value || '').trim()
  return text.startsWith('{') || text.startsWith('[')
}

function joinParamPath(basePath: string, key: string) {
  const token = String(key || '').trim()
  if (!token) return basePath
  return basePath ? `${basePath}.${token}` : token
}

function normalizePathname(value: string) {
  const text = String(value || '').trim()
  if (!text) return ''
  try {
    const parsed = /^https?:\/\//i.test(text)
      ? new URL(text)
      : new URL(text.startsWith('/') ? text : `/${text}`, 'https://placeholder.local')
    const pathname = String(parsed.pathname || '').trim()
    if (!pathname) return ''
    if (pathname === '/') return pathname
    return pathname.replace(/\/{2,}/g, '/').replace(/\/+$/, '')
  } catch {
    const fallback = text.split(/[?#]/, 1)[0] || ''
    if (!fallback) return ''
    const normalized = fallback.startsWith('/') ? fallback : `/${fallback}`
    if (normalized === '/') return normalized
    return normalized.replace(/\/{2,}/g, '/').replace(/\/+$/, '')
  }
}

function splitPathSegments(value: string) {
  return normalizePathname(value)
    .split('/')
    .map((item) => item.trim())
    .filter((item) => Boolean(item))
}

function pathMatchesBySegments(left: string, right: string) {
  const leftSegments = splitPathSegments(left)
  const rightSegments = splitPathSegments(right)
  if (!leftSegments.length || !rightSegments.length) return false
  const source = leftSegments.length >= rightSegments.length ? leftSegments : rightSegments
  const target = leftSegments.length >= rightSegments.length ? rightSegments : leftSegments
  const offset = source.length - target.length
  for (let index = 0; index < target.length; index += 1) {
    if (source[offset + index] !== target[index]) return false
  }
  return true
}

// 用 API Reg 查询出来的 compose_preview 给参数词典标记来源 API，过滤掉心跳包等噪音请求。
function resolveRowMatchedApis(row: VueCapturedRequest, options: InferredApiOption[]) {
  if (!options.length) return []
  const rowPath = normalizePathname(String(row.path || row.url || '').trim())
  const rowMethod = normalizeMethod(String(row.method || 'GET'))
  if (!rowPath) return []
  return options.filter((item) => item.method === rowMethod && pathMatchesBySegments(rowPath, item.matchPath))
}

function parseQueryEntries(raw: VueCapturedRequest) {
  const entries: Array<{ key: string; value: unknown }> = []
  const queryParams = raw.query_params
  if (queryParams && typeof queryParams === 'object' && !Array.isArray(queryParams)) {
    Object.entries(queryParams).forEach(([key, value]) => {
      if (!String(key || '').trim()) return
      if (Array.isArray(value)) {
        value.forEach((item) => entries.push({ key, value: item }))
        return
      }
      entries.push({ key, value })
    })
    return entries
  }
  const queryText = String(raw.query_string || '').trim()
  if (!queryText) return entries
  const params = new URLSearchParams(queryText)
  params.forEach((value, key) => {
    entries.push({ key, value })
  })
  return entries
}

function parseBodySeedSource(raw: VueCapturedRequest): unknown {
  if (raw.body_json !== undefined && raw.body_json !== null) return raw.body_json
  if (raw.body_form && typeof raw.body_form === 'object' && Object.keys(raw.body_form).length) {
    return raw.body_form
  }
  const requestBody = String(raw.request_body || '').trim()
  if (!requestBody || !looksLikeJsonBody(requestBody)) return null
  try {
    return JSON.parse(requestBody)
  } catch {
    return null
  }
}

function upsertFuzzParam(
  mapped: Map<string, FuzzParamBucket>,
  source: ProjectBaseRequestFuzzParamSource,
  key: string,
  value: unknown,
  sampleUrl: string,
  hitWeight: number,
  matchedApis: InferredApiOption[],
) {
  const token = String(key || '').trim()
  if (!token) return
  const item = mapped.get(token) || {
    key: token,
    sources: new Set<ProjectBaseRequestFuzzParamSource>(),
    valueTypes: new Set<string>(),
    sampleValues: new Set<string>(),
    hitCount: 0,
    sampleUrls: new Set<string>(),
    seedValues: new Map<string, unknown>(),
    matchedApis: new Map<string, string>(),
  }
  item.sources.add(source)
  item.valueTypes.add(detectValueType(value))
  const normalizedValue = normalizeSampleValue(value)
  if (normalizedValue) item.sampleValues.add(normalizedValue)
  item.seedValues.set(normalizeSeedValueKey(value), cloneSeedValue(value))
  item.hitCount += Math.max(1, hitWeight)
  if (sampleUrl) item.sampleUrls.add(sampleUrl)
  matchedApis.forEach((api) => {
    item.matchedApis.set(api.key, api.label)
  })
  mapped.set(token, item)
}

// 将捕获到的 query/body 递归摊平成参数词典，供后续 fuzz 选择使用。
function collectStructuredParams(
  mapped: Map<string, FuzzParamBucket>,
  source: ProjectBaseRequestFuzzParamSource,
  basePath: string,
  value: unknown,
  sampleUrl: string,
  hitWeight: number,
  matchedApis: InferredApiOption[],
) {
  if (value === undefined) return
  if (Array.isArray(value)) {
    if (!value.length) {
      upsertFuzzParam(mapped, source, `${basePath}[]`, [], sampleUrl, hitWeight, matchedApis)
      return
    }
    value.forEach((item, index) => {
      if (item && typeof item === 'object') {
        collectStructuredParams(mapped, source, `${basePath}[${index}]`, item, sampleUrl, hitWeight, matchedApis)
        return
      }
      upsertFuzzParam(mapped, source, `${basePath}[]`, item, sampleUrl, hitWeight, matchedApis)
    })
    return
  }
  if (value && typeof value === 'object') {
    Object.entries(value as Record<string, unknown>).forEach(([key, child]) => {
      collectStructuredParams(mapped, source, joinParamPath(basePath, key), child, sampleUrl, hitWeight, matchedApis)
    })
    return
  }
  upsertFuzzParam(mapped, source, basePath, value, sampleUrl, hitWeight, matchedApis)
}

const querySamples = computed<QuerySample[]>(() => aggregateSamples(captureRows.value.map((item) => buildQuerySample(item))))
const bodySamples = computed<BodySample[]>(() => aggregateSamples(captureRows.value.map((item) => buildBodySample(item))))
const headerSamples = computed<HeaderSample[]>(() => aggregateSamples(captureRows.value.map((item) => buildHeaderSample(item))))
const inferredApiOptions = computed<InferredApiOption[]>(() => {
  const preview = props.inferPreset?.inferResult?.compose_preview
  if (!Array.isArray(preview)) return []
  const mapped = new Map<string, InferredApiOption>()
  preview.forEach((item) => {
    const method = normalizeMethod(String(item.method || 'GET'))
    const matchPath = normalizePathname(String(item.url || item.path || '').trim())
    if (!matchPath) return
    const displayPath = String(item.path || matchPath).trim() || matchPath
    const key = `${method} ${matchPath}`
    if (mapped.has(key)) return
    mapped.set(key, {
      key,
      method,
      matchPath,
      displayPath,
      label: `${method} ${displayPath}`,
    })
  })
  return [...mapped.values()].sort((left, right) => left.label.localeCompare(right.label))
})
const fuzzParamCatalog = computed<LocalFuzzParamCatalogItem[]>(() => {
  const mapped = new Map<string, FuzzParamBucket>()
  const apiOptions = inferredApiOptions.value

  captureRows.value.forEach((row) => {
    const sampleUrl = String(row.url || '').trim()
    const hitWeight = Math.max(1, Number(row.count || 1))
    const matchedApis = resolveRowMatchedApis(row, apiOptions)

    parseQueryEntries(row).forEach((entry) => {
      upsertFuzzParam(mapped, 'query', entry.key, entry.value, sampleUrl, hitWeight, matchedApis)
    })

    const bodySeed = parseBodySeedSource(row)
    if (bodySeed && typeof bodySeed === 'object') {
      collectStructuredParams(mapped, 'body', '', bodySeed, sampleUrl, hitWeight, matchedApis)
    }
  })

  return [...mapped.values()]
    .map((item) => ({
      key: item.key,
      sources: [...item.sources].sort(),
      valueTypes: [...item.valueTypes].sort(),
      sampleValues: [...item.sampleValues].slice(0, 4),
      hitCount: item.hitCount,
      sampleUrlCount: item.sampleUrls.size,
      seedValuesRaw: [...item.seedValues.values()].slice(0, 4),
      matchedApiKeys: [...item.matchedApis.keys()],
      matchedApiLabels: [...item.matchedApis.values()].slice(0, 3),
      matchedApiCount: item.matchedApis.size,
    }))
    .sort((left, right) => {
      if (right.matchedApiCount !== left.matchedApiCount) return right.matchedApiCount - left.matchedApiCount
      if (right.hitCount !== left.hitCount) return right.hitCount - left.hitCount
      if (right.sampleUrlCount !== left.sampleUrlCount) return right.sampleUrlCount - left.sampleUrlCount
      return left.key.localeCompare(right.key)
    })
})
const filteredFuzzParams = computed<LocalFuzzParamCatalogItem[]>(() => {
  const keyword = String(fuzzSearchText.value || '').trim().toLowerCase()
  const hasInferredApis = inferredApiOptions.value.length > 0
  return fuzzParamCatalog.value.filter((item) => {
    if (fuzzSourceFilter.value !== 'all' && !item.sources.includes(fuzzSourceFilter.value)) return false
    if (fuzzApiFilter.value === 'matched' && hasInferredApis && item.matchedApiCount <= 0) return false
    if (fuzzApiFilter.value !== 'all' && fuzzApiFilter.value !== 'matched' && !item.matchedApiKeys.includes(fuzzApiFilter.value)) {
      return false
    }
    if (!keyword) return true
    if (item.key.toLowerCase().includes(keyword)) return true
    if (item.sampleValues.some((value) => value.toLowerCase().includes(keyword))) return true
    if (item.matchedApiLabels.some((value) => value.toLowerCase().includes(keyword))) return true
    return false
  })
})
const selectedFuzzParams = computed<ProjectBaseRequestFuzzParam[]>(() => {
  const selectedKeys = new Set(selectedFuzzParamKeys.value)
  return fuzzParamCatalog.value.filter((item) => selectedKeys.has(item.key))
    .map((item) => ({
      key: item.key,
      sources: [...item.sources],
      valueTypes: [...item.valueTypes],
      sampleValues: [...item.sampleValues],
      hitCount: item.hitCount,
      sampleUrlCount: item.sampleUrlCount,
    }))
})
const selectedFuzzParamItems = computed<LocalFuzzParamCatalogItem[]>(() => {
  const selectedKeys = new Set(selectedFuzzParamKeys.value)
  return fuzzParamCatalog.value.filter((item) => selectedKeys.has(item.key))
})
const defaultBodyFuzzParams = computed<LocalFuzzParamCatalogItem[]>(() => {
  const hasInferredApis = inferredApiOptions.value.length > 0
  if (!hasInferredApis) return []
  return fuzzParamCatalog.value.filter((item) => {
    if (!item.sources.includes('body')) return false
    if (item.matchedApiCount <= 0) return false
    return true
  })
})
const inferQuerySummary = computed(() => {
  const infer = props.inferPreset?.inferResult
  if (!infer) return ''
  return `API Reg 查询结果：query_baseurl=${String(infer.baseurl || '-')} query_baseapi=${String(infer.baseapi || '(empty)')}`
})

function applyBaseRequestPreset(presetEnvelope: ProjectBaseRequestPresetEnvelope | null | undefined) {
  const preset = presetEnvelope?.preset
  if (!preset) return
  baseurl.value = String(preset.baseurl || '').trim()
  baseapi.value = String(preset.baseapi || '').trim()
  baseQueryText.value = String(preset.baseQuery || '').trim()
  baseBodyText.value = String(preset.baseBody || '').trim()
  baseBodyType.value = normalizeBaseBodyType(preset.baseBodyType)
  baseHeadersText.value = String(preset.baseHeaders || '').trim()
  requestMethod.value = preset.requestMethod === 'POST' ? 'POST' : 'GET'
  selectedFuzzParamKeys.value = Array.isArray(preset.fuzzParams)
    ? preset.fuzzParams
        .map((item) => String(item?.key || '').trim())
        .filter((item) => Boolean(item))
    : []
}

function fuzzParamSelected(key: string) {
  return selectedFuzzParamKeys.value.includes(String(key || '').trim())
}

function toggleFuzzParamSelection(key: string, checked: boolean) {
  const token = String(key || '').trim()
  if (!token) return
  const next = new Set(selectedFuzzParamKeys.value)
  if (checked) next.add(token)
  else next.delete(token)
  selectedFuzzParamKeys.value = [...next]
}

function selectVisibleFuzzParams() {
  const next = new Set(selectedFuzzParamKeys.value)
  filteredFuzzParams.value.forEach((item) => next.add(item.key))
  selectedFuzzParamKeys.value = [...next]
}

function clearSelectedFuzzParams() {
  selectedFuzzParamKeys.value = []
}

function buildFuzzJsonPayloadText(items: LocalFuzzParamCatalogItem[]) {
  const payload: Record<string, unknown> = {}
  items.forEach((item) => {
    const steps = parseFuzzParamPath(item.key)
    if (!steps.length) return
    const seedValue = item.seedValuesRaw[0]
    assignValueBySteps(payload, steps, seedValue)
  })
  return JSON.stringify(payload, null, 2)
}

function stringifyFormValue(value: unknown) {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function buildFuzzFormPayloadText(items: LocalFuzzParamCatalogItem[]) {
  const params = new URLSearchParams()
  items.forEach((item) => {
    if (!item.seedValuesRaw.length) return
    const seedValue = item.seedValuesRaw[0]
    if (Array.isArray(seedValue)) {
      if (!seedValue.length) {
        params.append(item.key, '')
        return
      }
      seedValue.forEach((entry) => {
        params.append(item.key, stringifyFormValue(entry))
      })
      return
    }
    params.append(item.key, stringifyFormValue(seedValue))
  })
  return params.toString()
}

type FuzzPathStep =
  | { kind: 'prop'; key: string }
  | { kind: 'index'; index: number }
  | { kind: 'append' }

function parseFuzzParamPath(path: string): FuzzPathStep[] {
  const text = String(path || '').trim()
  if (!text) return []
  const steps: FuzzPathStep[] = []
  const pattern = /([^[.\]]+)|\[(\d*)\]/g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text))) {
    if (match[1]) {
      steps.push({ kind: 'prop', key: match[1] })
      continue
    }
    if (match[2] === '') {
      steps.push({ kind: 'append' })
      continue
    }
    steps.push({ kind: 'index', index: Math.max(0, Number(match[2] || 0)) })
  }
  return steps
}

function createContainerForNextStep(step: FuzzPathStep | undefined) {
  if (!step) return {}
  return step.kind === 'prop' ? {} : []
}

function assignValueBySteps(target: Record<string, unknown>, steps: FuzzPathStep[], value: unknown) {
  if (!steps.length) return
  let current: unknown = target
  for (let index = 0; index < steps.length; index += 1) {
    const step = steps[index]!
    const isLast = index === steps.length - 1
    const nextStep = steps[index + 1]
    switch (step.kind) {
      case 'prop': {
        const objectRef = (current && typeof current === 'object' ? current : {}) as Record<string, unknown>
        if (isLast) {
          objectRef[step.key] = cloneSeedValue(value)
          return
        }
        const existing = objectRef[step.key]
        if (!existing || typeof existing !== 'object') {
          objectRef[step.key] = createContainerForNextStep(nextStep)
        }
        current = objectRef[step.key]
        break
      }
      case 'index': {
        if (!Array.isArray(current)) return
        if (isLast) {
          current[step.index] = cloneSeedValue(value)
          return
        }
        if (!current[step.index] || typeof current[step.index] !== 'object') {
          current[step.index] = createContainerForNextStep(nextStep)
        }
        current = current[step.index]
        break
      }
      case 'append': {
        if (!Array.isArray(current)) return
        if (isLast) {
          current.push(cloneSeedValue(value))
          return
        }
        const appended = createContainerForNextStep(nextStep)
        current.push(appended)
        current = appended
        break
      }
    }
  }
}

function applyBuiltBaseBody(bodyType: ProjectBaseRequestBodyType, bodyText: string) {
  baseBodyType.value = bodyType
  baseBodyText.value = bodyText
  requestMethod.value = 'POST'
  syncBaseHeaderContentType(bodyType)
}

function onBuildFuzzToJsonBody() {
  if (!selectedFuzzParamItems.value.length) {
    error.value = '请先勾选至少一个 Fuzz 参数'
    return
  }
  error.value = ''
  applyBuiltBaseBody('json', buildFuzzJsonPayloadText(selectedFuzzParamItems.value))
  message.value = `已根据 ${selectedFuzzParamItems.value.length} 个 Fuzz 参数构造 BaseBody`
}

function onBuildFuzzToBaseBody() {
  if (!selectedFuzzParamItems.value.length) {
    error.value = '请先选择至少一个 Fuzz 参数'
    return
  }
  error.value = ''
  selectedQueryKey.value = ''
  baseQueryText.value = buildFuzzFormPayloadText(selectedFuzzParamItems.value)
  message.value = `Built BaseQuery from ${selectedFuzzParamItems.value.length} fuzz params`
}

function onBuildFuzzToFormBody() {
  if (!selectedFuzzParamItems.value.length) {
    error.value = '璇峰厛鍕鹃€夎嚦灏戜竴涓?Fuzz 鍙傛暟'
    return
  }
  error.value = ''
  applyBuiltBaseBody('form', buildFuzzFormPayloadText(selectedFuzzParamItems.value))
  message.value = `宸叉牴鎹?${selectedFuzzParamItems.value.length} 涓?Fuzz 鍙傛暟鏋勯€?Form Body`
}

// Only auto-fill when the page still has no manual BaseBody or explicit preset.
function maybeApplyDefaultBodyFromFuzzParams() {
  const preset = props.baseRequestPreset?.preset
  if (String(baseBodyText.value || '').trim()) return
  if (String(preset?.baseBody || '').trim()) return
  if (Array.isArray(preset?.fuzzParams) && preset.fuzzParams.length) return
  const items = defaultBodyFuzzParams.value
  if (!items.length) return
  if (!selectedFuzzParamKeys.value.length) {
    selectedFuzzParamKeys.value = items.map((item) => item.key)
  }
  applyBuiltBaseBody('json', buildFuzzJsonPayloadText(items))
}

function applyInferPreset(preset: InferPreset | null | undefined) {
  if (!preset?.inferResult) return
  const infer = preset.inferResult
  if (typeof infer.baseurl === 'string') baseurl.value = String(infer.baseurl || '')
  if (typeof infer.baseapi === 'string') baseapi.value = String(infer.baseapi || '')
  if (infer.baseurl || infer.baseapi) {
    message.value = `已接收 API Reg 查询结果：query_baseurl=${baseurl.value || '-'} query_baseapi=${baseapi.value || '(empty)'}`
  }
}

async function loadContext(targetDomain?: string) {
  loading.value = true
  error.value = ''
  try {
    const payload = await fetchVueRequestContext(targetDomain || currentDomain.value || props.domain || '')
    currentDomain.value = String(payload.domain || targetDomain || props.domain || '')
    if (!baseurl.value) baseurl.value = String(payload.baseurl || '')
    if (!baseapi.value) baseapi.value = String(payload.baseapi || '')
    requestMethod.value = normalizeMethod(String(payload.method || 'GET')) === 'POST' ? 'POST' : 'GET'
    captureRequestTotal.value = Number(payload.capture_request_total || 0)
    captureTemplateTotal.value = Number(payload.capture_template_total || 0)
    captureRows.value = Array.isArray(payload.captured_requests) ? payload.captured_requests : []
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    loading.value = false
  }
}

function onSendToApiRequest() {
  const normalizedMethod = requestMethod.value === 'POST' ? 'POST' : 'GET'
  const preset: ProjectBaseRequestPresetEnvelope = {
    seq: Date.now(),
    preset: {
      baseurl: String(baseurl.value || '').trim(),
      baseapi: String(baseapi.value || '').trim(),
      baseQuery: String(baseQueryText.value || '').trim(),
      baseBody: String(baseBodyText.value || '').trim(),
      baseBodyType: baseBodyType.value,
      baseHeaders: String(baseHeadersText.value || '').trim(),
      requestMethod: normalizedMethod,
      fuzzParams: selectedFuzzParams.value.map((item) => ({
        key: item.key,
        sources: [...item.sources],
        valueTypes: [...item.valueTypes],
        sampleValues: [...item.sampleValues],
        hitCount: item.hitCount,
        sampleUrlCount: item.sampleUrlCount,
      })),
    },
  }
  emit('ready', preset)
  message.value = 'BaseRequest 已发送到 ApiRequest'
}

watch(
  () => selectedQueryKey.value,
  (value) => {
    if (!value) return
    const sample = querySamples.value.find((item) => item.key === value)
    if (sample) {
      baseQueryText.value = sample.queryText
    }
  },
)

watch(
  () => selectedBodyKey.value,
  (value) => {
    if (!value) return
    const sample = bodySamples.value.find((item) => item.key === value)
    if (sample) {
      baseBodyText.value = sample.bodyText
      baseBodyType.value = sample.bodyType
      requestMethod.value = 'POST'
      syncBaseHeaderContentType(sample.bodyType, sample.contentType)
    }
  },
)

watch(
  () => selectedHeaderKey.value,
  (value) => {
    if (!value) return
    const sample = headerSamples.value.find((item) => item.key === value)
    if (sample) {
      baseHeadersText.value = sample.headersText
    }
  },
)

watch(
  () => props.domain,
  async (value) => {
    currentDomain.value = String(value || '').trim()
    await loadContext(currentDomain.value)
    applyInferPreset(props.inferPreset || null)
    applyBaseRequestPreset(props.baseRequestPreset || null)
    maybeApplyDefaultBodyFromFuzzParams()
  },
)

watch(
  () => props.refreshKey,
  async (value, prev) => {
    if (value === prev) return
    await loadContext(currentDomain.value || props.domain)
    applyInferPreset(props.inferPreset || null)
    applyBaseRequestPreset(props.baseRequestPreset || null)
    maybeApplyDefaultBodyFromFuzzParams()
  },
)

watch(
  () => props.inferPreset?.seq,
  (value, prev) => {
    if (!value || value === prev) return
    applyInferPreset(props.inferPreset || null)
    maybeApplyDefaultBodyFromFuzzParams()
  },
)

watch(
  () => props.baseRequestPreset?.seq,
  (value, prev) => {
    if (!value || value === prev) return
    applyBaseRequestPreset(props.baseRequestPreset || null)
    maybeApplyDefaultBodyFromFuzzParams()
  },
)

watch(
  () => fuzzParamCatalog.value.map((item) => item.key).join('|'),
  () => {
    const available = new Set(fuzzParamCatalog.value.map((item) => item.key))
    selectedFuzzParamKeys.value = selectedFuzzParamKeys.value.filter((item) => available.has(item))
    maybeApplyDefaultBodyFromFuzzParams()
  },
)

watch(
  () => inferredApiOptions.value.map((item) => item.key).join('|'),
  () => {
    const available = new Set(inferredApiOptions.value.map((item) => item.key))
    if (!available.size) {
      fuzzApiFilter.value = 'all'
      maybeApplyDefaultBodyFromFuzzParams()
      return
    }
    if (fuzzApiFilter.value !== 'all' && fuzzApiFilter.value !== 'matched' && !available.has(fuzzApiFilter.value)) {
      fuzzApiFilter.value = inferredApiOptions.value.length ? 'matched' : 'all'
    }
    maybeApplyDefaultBodyFromFuzzParams()
  },
)

onMounted(async () => {
  currentDomain.value = String(props.domain || '').trim()
  await loadContext(currentDomain.value)
  applyInferPreset(props.inferPreset || null)
  applyBaseRequestPreset(props.baseRequestPreset || null)
  maybeApplyDefaultBodyFromFuzzParams()
})
</script>

<template>
  <section class="project-base-request-tab">
    <div v-if="message" class="notice success">{{ message }}</div>
    <div v-if="error" class="notice error">{{ error }}</div>

    <div class="sub-block">
      <div class="sub-head">
        <h4>BaseRequest</h4>
        <button class="primary" :disabled="loading || !currentDomain" @click="onSendToApiRequest">发送到 ApiRequest</button>
      </div>
      <div class="capture-summary">
        捕获请求 {{ captureRequestTotal }} 条，模板 {{ captureTemplateTotal }} 组。这里用于构造基础请求包，不直接跑接口列表。
      </div>
      <div v-if="inferQuerySummary" class="capture-summary">
        {{ inferQuerySummary }}
      </div>
      <div class="request-raw">
        <div class="raw-line raw-line-first">
          <select v-model="requestMethod" class="method-select">
            <option value="GET">GET</option>
            <option value="POST">POST</option>
          </select>
          <input v-model="baseapi" type="text" placeholder="/baseapi" />
          <span class="line-token">?</span>
          <input v-model="baseQueryText" type="text" placeholder="pageNo=1&pageSize=1" />
          <select v-model="selectedQueryKey" class="sample-select">
            <option value="">选择 BaseQuery</option>
            <option v-for="sample in querySamples" :key="sample.key" :value="sample.key">
              x{{ sample.count }} · {{ sample.queryTextSingleLine }}
            </option>
          </select>
        </div>

        <div class="raw-line raw-line-simple">
          <span class="line-label">BaseURL</span>
          <input v-model="baseurl" type="text" placeholder="https://baseurl.example.com" />
        </div>

        <div class="raw-line raw-line-block">
          <div class="raw-line-head">
            <span class="line-label">BaseHeader</span>
            <span class="line-meta">{{ headerSamples.length }} 个捕获 Header 样本</span>
          </div>
          <select v-model="selectedHeaderKey" class="sample-select">
            <option value="">选择 BaseHeader</option>
            <option v-for="sample in headerSamples" :key="sample.key" :value="sample.key">
              x{{ sample.count }} · {{ sample.primaryLabel || sample.headersTextSingleLine || 'headers' }}
            </option>
          </select>
          <textarea v-model="baseHeadersText" rows="5" placeholder="{&quot;Content-Type&quot;:&quot;application/json&quot;}"></textarea>
        </div>

        <div class="raw-line raw-line-block">
          <div class="raw-line-head">
            <span class="line-label">BaseBody</span>
            <span class="line-meta">{{ baseBodyType.toUpperCase() }}</span>
            <span class="line-meta">{{ bodySamples.length }} 个捕获 Body 样本</span>
          </div>
          <select v-model="selectedBodyKey" class="sample-select">
            <option value="">选择 BaseBody</option>
            <option v-for="sample in bodySamples" :key="sample.key" :value="sample.key">
              x{{ sample.count }} · {{ sample.bodyTextSingleLine || sample.contentType || 'body' }}
            </option>
          </select>
          <textarea v-model="baseBodyText" rows="8" placeholder="{&quot;pageNo&quot;:&quot;1&quot;,&quot;pageSize&quot;:&quot;1&quot;}"></textarea>
        </div>

        <div class="raw-line raw-line-block">
          <div class="raw-line-head">
            <span class="line-label">FuzzParams</span>
            <div class="fuzz-head-actions">
              <button class="ghost btn-sm" type="button" :disabled="!selectedFuzzParams.length" @click="onBuildFuzzToJsonBody">JSON Body</button>
              <button class="ghost btn-sm" type="button" :disabled="!selectedFuzzParams.length" @click="onBuildFuzzToFormBody">Form Body</button>
              <button class="ghost btn-sm query-build-btn" type="button" :disabled="!selectedFuzzParams.length" @click="onBuildFuzzToBaseBody">Query</button>
              <span class="line-meta">{{ selectedFuzzParams.length }} selected · {{ filteredFuzzParams.length }} / {{ fuzzParamCatalog.length }}</span>
              <button class="ghost btn-sm" type="button" :disabled="!selectedFuzzParams.length" @click="onBuildFuzzToBaseBody">构造到 BaseBody</button>
              <button class="ghost btn-sm" type="button" :disabled="!filteredFuzzParams.length" @click="selectVisibleFuzzParams">全选当前</button>
              <button class="ghost btn-sm" type="button" :disabled="!selectedFuzzParams.length" @click="clearSelectedFuzzParams">清空</button>
            </div>
          </div>
          <div class="fuzz-toolbar">
            <input
              v-model="fuzzSearchText"
              type="text"
              placeholder="搜索参数名或样本值"
            />
            <select v-model="fuzzSourceFilter" class="sample-select">
              <option value="all">全部来源</option>
              <option value="query">仅 Query</option>
              <option value="body">仅 Body</option>
            </select>
            <select v-model="fuzzApiFilter" class="sample-select fuzz-api-select">
              <option value="all">全部 API 来源</option>
              <option v-if="inferredApiOptions.length" value="matched">仅当前 API 列表</option>
              <option v-for="api in inferredApiOptions" :key="api.key" :value="api.key">
                {{ api.label }}
              </option>
            </select>
          </div>
          <div v-if="filteredFuzzParams.length" class="fuzz-table-wrap">
            <table class="fuzz-table">
              <thead>
                <tr>
                  <th>Use</th>
                  <th>Param</th>
                  <th>Source</th>
                  <th>API</th>
                  <th>Types</th>
                  <th>Samples</th>
                  <th>Hits</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in filteredFuzzParams" :key="item.key">
                  <td class="fuzz-check-cell">
                    <input
                      type="checkbox"
                      :checked="fuzzParamSelected(item.key)"
                      @change="toggleFuzzParamSelection(item.key, ($event.target as HTMLInputElement).checked)"
                    />
                  </td>
                  <td class="mono fuzz-param-cell">{{ item.key }}</td>
                  <td>{{ item.sources.join(', ') }}</td>
                  <td class="fuzz-api-cell">
                    <template v-if="item.matchedApiLabels.length">
                      <span
                        v-for="label in item.matchedApiLabels"
                        :key="`${item.key}:${label}`"
                        class="fuzz-pill"
                      >
                        {{ label }}
                      </span>
                      <span v-if="item.matchedApiCount > item.matchedApiLabels.length" class="line-meta">
                        +{{ item.matchedApiCount - item.matchedApiLabels.length }}
                      </span>
                    </template>
                    <span v-else class="line-meta">未匹配当前 API</span>
                  </td>
                  <td>{{ item.valueTypes.join(', ') }}</td>
                  <td class="fuzz-sample-cell">
                    <span
                      v-for="value in item.sampleValues"
                      :key="`${item.key}:${value}`"
                      class="fuzz-pill"
                    >
                      {{ value }}
                    </span>
                  </td>
                  <td>{{ item.hitCount }} / {{ item.sampleUrlCount }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty fuzz-empty">
            暂无可用参数词典。
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.project-base-request-tab {
  display: grid;
  gap: 12px;
}

.sub-block {
  border: 1px solid #e3eaf2;
  border-radius: 10px;
  background: #fcfdff;
  padding: 10px;
  display: grid;
  gap: 12px;
}

.sub-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.sub-head h4 {
  margin: 0;
}

.capture-summary {
  color: #59728a;
  font-size: 12px;
}

.request-raw {
  display: grid;
  gap: 10px;
}

.raw-line {
  display: grid;
  gap: 8px;
  border: 1px solid #d6e1ec;
  border-radius: 10px;
  padding: 10px;
  background: #fff;
}

.raw-line-first {
  grid-template-columns: 110px minmax(0, 1fr) 26px minmax(0, 1.2fr) minmax(240px, 0.9fr);
  align-items: center;
}

.raw-line-simple {
  grid-template-columns: 92px minmax(0, 1fr);
  align-items: center;
}

.raw-line-block {
  grid-template-columns: 1fr;
}

.raw-line-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.fuzz-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.fuzz-head-actions > button:nth-of-type(4) {
  display: none;
}

.line-label,
.line-meta,
.line-token {
  font-family: 'JetBrains Mono', 'Cascadia Mono', Consolas, monospace;
}

.line-label {
  font-size: 12px;
  color: #4f6982;
  font-weight: 600;
}

.line-meta {
  font-size: 12px;
  color: #6f879d;
}

.line-token {
  color: #59728a;
  font-size: 16px;
  text-align: center;
}

.method-select,
.sample-select {
  min-width: 0;
}

.fuzz-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 180px auto;
  gap: 8px;
}

.fuzz-api-select {
  width: 260px;
  max-width: 100%;
  min-width: 0;
  white-space: normal;
  line-height: 1.35;
  height: auto;
}

.fuzz-api-select option {
  white-space: normal;
}

.fuzz-table-wrap {
  overflow-x: auto;
}

.fuzz-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.fuzz-table th,
.fuzz-table td {
  padding: 8px 10px;
  border-top: 1px solid #e2ebf4;
  text-align: left;
  vertical-align: top;
}

.fuzz-table th {
  color: #4c6680;
  font-weight: 600;
  white-space: nowrap;
}

.fuzz-param-cell {
  min-width: 220px;
  overflow-wrap: anywhere;
}

.fuzz-check-cell {
  width: 54px;
  min-width: 54px;
}

.fuzz-sample-cell {
  min-width: 260px;
}

.fuzz-api-cell {
  min-width: 260px;
}

.fuzz-pill {
  display: inline-flex;
  align-items: center;
  margin: 0 6px 6px 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: #edf6fd;
  color: #21557b;
  font-size: 12px;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fuzz-empty {
  padding: 10px 12px;
}

input,
select,
textarea {
  width: 100%;
  border: 1px solid #d3dfeb;
  border-radius: 9px;
  padding: 9px 10px;
  font-size: 13px;
  color: #1f3347;
  background: #fff;
}

input:focus,
select:focus,
textarea:focus {
  outline: none;
  border-color: #7db8df;
  box-shadow: 0 0 0 2px rgba(14, 132, 204, 0.14);
}

textarea {
  min-height: 88px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'JetBrains Mono', 'Cascadia Mono', Consolas, monospace;
}

@media (max-width: 980px) {
  .raw-line-first,
  .raw-line-simple {
    grid-template-columns: 1fr;
  }

  .fuzz-toolbar {
    grid-template-columns: 1fr;
  }

  .sub-head,
  .raw-line-head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
