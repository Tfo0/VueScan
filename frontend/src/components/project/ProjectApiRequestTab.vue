<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import type { ApiEndpointItem } from '../../api/vueApi'
import {
  fetchVueRequestJob,
  fetchVueRequestContext,
  deleteVueRequestRunSnapshot,
  fetchVueRequestRunSnapshots,
  fetchVueRequestResponseDetail,
  pauseVueRequestJob,
  resumeVueRequestJob,
  runVueRequest,
  runVueRequestBatch,
  saveVueRequestRunSnapshot,
  type VueCapturedRequest,
  type VueRequestBatchJob,
  type VueRequestBatchRowResult,
  type VueRequestInferResult,
  type VueRequestRunSnapshot,
  type VueRequestRunSnapshotRow,
  type VueRequestResponseDetail,
  type VueRequestResult,
} from '../../api/vueRequest'
import type { ProjectBaseRequestBodyType, ProjectBaseRequestPresetEnvelope } from './baseRequestTypes'

interface CapturePreset {
  url: string
  method: string
  request_body: string
}

interface InferPreset {
  seq: number
  inferResult: VueRequestInferResult
}

interface RequestRow {
  key: string
  endpoint_id: number
  method: string
  path: string
  url: string
  capture_url?: string
  content_type?: string
  source_file: string
  source_line: number
  source_type: 'endpoint' | 'infer' | 'capture'
  count?: number
  status?: number
  query_string?: string
  query_params?: Record<string, unknown>
  request_body?: string
  body_type?: string
  body_json?: unknown
  body_form?: Record<string, unknown> | null
  request_headers?: Record<string, string>
}

interface RowResponseState {
  requestResult: VueRequestResult
  responseDetail: VueRequestResponseDetail | null
  responseLength: number
  packetLength: number
  requestedAt: number
}

interface RowEditDraft {
  method: 'GET' | 'POST'
  baseurl: string
  path: string
  queryText: string
  headersText: string
  bodyText: string
}

type RequestSortKey =
  | 'default'
  | 'packet_length_desc'
  | 'packet_length_asc'
  | 'status_desc'
  | 'status_asc'

interface PersistedRequestTabState {
  baseurl?: string
  baseapi?: string
  baseQueryText?: string
  timeout?: number
  headers?: string
  requestMethod?: 'GET' | 'POST'
  requestBodyType?: ProjectBaseRequestBodyType
  requestBodyText?: string
  inferRows?: RequestRow[]
  responseMap?: Record<string, RowResponseState>
  requestAllConcurrency?: number
  requestAllPaused?: boolean
  requestingAll?: boolean
  requestAllTotal?: number
  requestAllDone?: number
  requestAllOk?: number
  requestAllFail?: number
  requestBatchStatus?: string
  requestBatchJobId?: string
  selectedRowKey?: string
  expandedRowKey?: string
  listPage?: number
  listPageSize?: number
  requestSortKey?: RequestSortKey
  selectedSnapshotId?: string
}

interface RequestRunConfigSnapshot {
  method: 'GET' | 'POST'
  baseurl: string
  baseapi: string
  baseQuery: string
  headers: string
  bodyType: ProjectBaseRequestBodyType
  bodyText: string
  useCaptureTemplate: boolean
}

const props = defineProps<{
  domain: string
  refreshKey?: number
  capturePreset?: CapturePreset | null
  captureUrlPresetSeq?: number
  inferPreset?: InferPreset | null
  baseRequestPreset?: ProjectBaseRequestPresetEnvelope | null
}>()

const currentDomain = ref('')
const baseurl = ref('')
const baseapi = ref('')
const baseQueryText = ref('')
const timeout = ref(20)
const headers = ref('')
const requestMethod = ref<'GET' | 'POST'>('GET')
const requestBodyType = ref<ProjectBaseRequestBodyType>('json')
const requestBodyText = ref('')
const captureRequestTotal = ref(0)

const endpointItems = ref<ApiEndpointItem[]>([])
const inferRows = ref<RequestRow[]>([])
const captureRows = ref<RequestRow[]>([])

const responseMap = ref<Record<string, RowResponseState>>({})
const runSnapshots = ref<VueRequestRunSnapshot[]>([])
const sendingKeys = ref<Set<string>>(new Set())
const loadingResponseDetailKeys = ref<Set<string>>(new Set())
const savingSnapshotJobIds = ref<Set<string>>(new Set())
const deletingSnapshotIds = ref<Set<string>>(new Set())

const loadingContext = ref(false)
const requestingAll = ref(false)
const requestAllPaused = ref(false)
const requestAllTotal = ref(0)
const requestAllDone = ref(0)
const requestAllOk = ref(0)
const requestAllFail = ref(0)
const requestBatchStatus = ref('idle')
const selectedRowKey = ref('')
const expandedRowKey = ref('')
const listPage = ref(1)
const listPageSize = ref(50)
const requestAllConcurrency = ref(16)
const requestSortKey = ref<RequestSortKey>('default')
const requestBatchJobId = ref('')
const requestBatchPollBusy = ref(false)
const editingRowKey = ref('')
const editingDraft = ref<RowEditDraft | null>(null)
const selectedSnapshotId = ref('live')
const activeRunConfig = ref<RequestRunConfigSnapshot | null>(null)
const liveRunConfig = ref<RequestRunConfigSnapshot | null>(null)
const snapshotResponseDetails = ref<Record<string, Record<string, VueRequestResponseDetail>>>({})

let requestBatchPollTimer: number | null = null

const LIST_PAGE_SIZE_OPTIONS = [20, 50, 100, 200]
const REQUEST_ALL_CONCURRENCY_MAX = 64

const requestAllStatusText = computed(() => {
  if (requestBatchStatus.value === 'paused') return '已暂停'
  if (requestBatchStatus.value === 'failed') return '失败'
  if (requestBatchStatus.value === 'stopped') return '已停止'
  if (requestingAll.value) return '进行中'
  if (!requestingAll.value && requestAllDone.value === 0) return '空闲'
  return '已完成'
})

const message = ref('')
const error = ref('')

function resolveError(err: unknown) {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: string } | undefined
    return data?.error || err.message || '请求失败'
  }
  if (err instanceof Error) return err.message
  return '未知错误'
}

function requestTabStorageKey(domain: string) {
  const token = String(domain || '').trim().toLowerCase()
  return token ? `vue-request-tab:${token}` : ''
}

function loadPersistedRequestTabState(domain: string): PersistedRequestTabState | null {
  const key = requestTabStorageKey(domain)
  if (!key || typeof window === 'undefined') return null
  try {
    const raw = window.sessionStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? (parsed as PersistedRequestTabState) : null
  } catch {
    return null
  }
}

function persistRequestTabState() {
  const key = requestTabStorageKey(currentDomain.value || props.domain || '')
  if (!key || typeof window === 'undefined') return

  const payload: PersistedRequestTabState = {
    baseurl: baseurl.value,
    baseapi: baseapi.value,
    baseQueryText: baseQueryText.value,
    timeout: Number(timeout.value || 20),
    headers: headers.value,
    requestMethod: requestMethod.value,
    requestBodyType: requestBodyType.value,
    requestBodyText: requestBodyText.value,
    inferRows: inferRows.value,
    responseMap: responseMap.value,
    requestAllConcurrency: Number(requestAllConcurrency.value || 16),
    requestAllPaused: requestAllPaused.value,
    requestingAll: requestingAll.value,
    requestAllTotal: requestAllTotal.value,
    requestAllDone: requestAllDone.value,
    requestAllOk: requestAllOk.value,
    requestAllFail: requestAllFail.value,
    requestBatchStatus: requestBatchStatus.value,
    requestBatchJobId: requestBatchJobId.value,
    selectedRowKey: selectedRowKey.value,
    expandedRowKey: expandedRowKey.value,
    listPage: listPage.value,
    listPageSize: listPageSize.value,
    requestSortKey: requestSortKey.value,
    selectedSnapshotId: selectedSnapshotId.value,
  }

  try {
    window.sessionStorage.setItem(key, JSON.stringify(payload))
  } catch {
    // ignore storage errors
  }
}

function restorePersistedRequestTabState(domain: string) {
  const persisted = loadPersistedRequestTabState(domain)
  if (!persisted) return
  const sortableKeys = new Set<RequestSortKey>([
    'default',
    'packet_length_desc',
    'packet_length_asc',
    'status_desc',
    'status_asc',
  ])

  if (typeof persisted.baseurl === 'string') baseurl.value = persisted.baseurl
  if (typeof persisted.baseapi === 'string') baseapi.value = persisted.baseapi
  if (typeof persisted.baseQueryText === 'string') baseQueryText.value = persisted.baseQueryText
  if (typeof persisted.timeout === 'number' && Number.isFinite(persisted.timeout)) timeout.value = persisted.timeout
  if (typeof persisted.headers === 'string') headers.value = persisted.headers
  if (persisted.requestMethod === 'GET' || persisted.requestMethod === 'POST') requestMethod.value = persisted.requestMethod
  requestBodyType.value = normalizeRequestBodyType(persisted.requestBodyType)
  if (typeof persisted.requestBodyText === 'string') requestBodyText.value = persisted.requestBodyText
  if (Array.isArray(persisted.inferRows)) inferRows.value = persisted.inferRows
  if (persisted.responseMap && typeof persisted.responseMap === 'object') {
    responseMap.value = persisted.responseMap as Record<string, RowResponseState>
  }
  if (typeof persisted.requestAllConcurrency === 'number' && Number.isFinite(persisted.requestAllConcurrency)) {
    requestAllConcurrency.value = Math.max(1, Math.min(REQUEST_ALL_CONCURRENCY_MAX, Math.trunc(persisted.requestAllConcurrency)))
  }
  if (typeof persisted.requestAllPaused === 'boolean') requestAllPaused.value = persisted.requestAllPaused
  if (typeof persisted.requestingAll === 'boolean') requestingAll.value = persisted.requestingAll
  if (typeof persisted.requestAllTotal === 'number') requestAllTotal.value = persisted.requestAllTotal
  if (typeof persisted.requestAllDone === 'number') requestAllDone.value = persisted.requestAllDone
  if (typeof persisted.requestAllOk === 'number') requestAllOk.value = persisted.requestAllOk
  if (typeof persisted.requestAllFail === 'number') requestAllFail.value = persisted.requestAllFail
  if (typeof persisted.requestBatchStatus === 'string') requestBatchStatus.value = persisted.requestBatchStatus
  if (typeof persisted.requestBatchJobId === 'string') requestBatchJobId.value = persisted.requestBatchJobId
  if (typeof persisted.selectedRowKey === 'string') selectedRowKey.value = persisted.selectedRowKey
  if (typeof persisted.expandedRowKey === 'string') expandedRowKey.value = persisted.expandedRowKey
  if (typeof persisted.listPage === 'number') listPage.value = Math.max(1, Math.trunc(persisted.listPage))
  if (typeof persisted.listPageSize === 'number') listPageSize.value = Math.max(1, Math.trunc(persisted.listPageSize))
  if (persisted.requestSortKey && sortableKeys.has(persisted.requestSortKey)) {
    requestSortKey.value = persisted.requestSortKey
  }
  if (typeof persisted.selectedSnapshotId === 'string' && persisted.selectedSnapshotId.trim()) {
    selectedSnapshotId.value = persisted.selectedSnapshotId
  }
}

function normalizeRunSnapshots(items: VueRequestRunSnapshot[] | unknown[]) {
  const rows = (Array.isArray(items) ? items : [])
    .filter((item): item is VueRequestRunSnapshot => Boolean(item && typeof item === 'object'))
    .map((item) => item as VueRequestRunSnapshot)
  rows.sort((left, right) => Number(left.run_index || 0) - Number(right.run_index || 0))
  return rows
}

function applyRunSnapshots(items: VueRequestRunSnapshot[] | unknown[]) {
  runSnapshots.value = normalizeRunSnapshots(items)
  if (selectedSnapshotId.value !== 'live' && !runSnapshots.value.some((item) => item.snapshot_id === selectedSnapshotId.value)) {
    selectedSnapshotId.value = 'live'
  }
  syncSelectedSnapshotForm()
}

async function loadRunSnapshots(targetDomain?: string) {
  const domain = String(targetDomain || currentDomain.value || props.domain || '').trim()
  if (!domain) return
  try {
    const payload = await fetchVueRequestRunSnapshots(domain)
    applyRunSnapshots(payload.snapshots)
    persistRequestTabState()
  } catch {
    // keep page usable even if snapshots fail to load
  }
}

function captureActiveRunConfig(): RequestRunConfigSnapshot {
  return {
    method: requestMethod.value,
    baseurl: String(baseurl.value || '').trim(),
    baseapi: String(baseapi.value || '').trim(),
    baseQuery: String(baseQueryText.value || '').trim(),
    headers: String(headers.value || '').trim(),
    bodyType: requestBodyType.value,
    bodyText: String(requestBodyText.value || '').trim(),
    useCaptureTemplate: false,
  }
}

function normalizeSnapshotRequestMethod(value: unknown): 'GET' | 'POST' {
  return normalizeSelectableMethod(String(value || 'GET'))
}

function applyRunConfigToForm(config: RequestRunConfigSnapshot | null | undefined) {
  if (!config) return
  requestMethod.value = normalizeSnapshotRequestMethod(config.method)
  baseurl.value = String(config.baseurl || '').trim()
  baseapi.value = String(config.baseapi || '').trim()
  baseQueryText.value = String(config.baseQuery || '').trim()
  headers.value = String(config.headers || '').trim()
  requestBodyType.value = normalizeRequestBodyType(config.bodyType)
  requestBodyText.value = String(config.bodyText || '').trim()
}

function snapshotToRunConfig(snapshot: VueRequestRunSnapshot | null | undefined): RequestRunConfigSnapshot | null {
  if (!snapshot || !snapshot.request) return null
  return {
    method: normalizeSnapshotRequestMethod(snapshot.request.method),
    baseurl: String(snapshot.request.baseurl || '').trim(),
    baseapi: String(snapshot.request.baseapi || '').trim(),
    baseQuery: String(snapshot.request.base_query || '').trim(),
    headers: String(snapshot.request.headers || '').trim(),
    bodyType: normalizeRequestBodyType(snapshot.request.body_type),
    bodyText: String(snapshot.request.body_text || '').trim(),
    useCaptureTemplate: false,
  }
}

function syncSelectedSnapshotForm() {
  if (selectedSnapshotId.value === 'live') return
  if (!liveRunConfig.value) {
    liveRunConfig.value = captureActiveRunConfig()
  }
  applyRunConfigToForm(snapshotToRunConfig(activeRunSnapshot.value))
}

async function ensureSavedRunSnapshot(job: VueRequestBatchJob) {
  const jobId = String(job.job_id || '').trim()
  if (!jobId || !TERMINAL_REQUEST_BATCH_STATUSES.has(String(job.status || '').trim().toLowerCase())) return
  if (!Object.keys(job.row_results || {}).length) return
  if (runSnapshots.value.some((item) => String(item.job_id || '').trim() === jobId)) return
  if (savingSnapshotJobIds.value.has(jobId)) return

  const nextSaving = new Set(savingSnapshotJobIds.value)
  nextSaving.add(jobId)
  savingSnapshotJobIds.value = nextSaving

  const requestConfig = activeRunConfig.value || captureActiveRunConfig()
  try {
    const payload = await saveVueRequestRunSnapshot({
      domain: currentDomain.value,
      job_id: jobId,
      status: String(job.status || ''),
      request: {
        method: requestConfig.method,
        baseurl: requestConfig.baseurl,
        baseapi: requestConfig.baseapi,
        base_query: requestConfig.baseQuery,
        headers: requestConfig.headers,
        body_type: requestConfig.bodyType,
        body_text: requestConfig.bodyText,
        use_capture_template: false,
        total: Number(job.total || job.progress?.total || 0),
      },
      rows: Object.values(job.row_results || {}).map((item) => ({
        row_key: String((item as VueRequestBatchRowResult).row_key || ''),
        endpoint_id: Number((item as VueRequestBatchRowResult).endpoint_id || 0),
        method: String((item as VueRequestBatchRowResult).method || ''),
        path: String((item as VueRequestBatchRowResult).path || ''),
        url: String((item as VueRequestBatchRowResult).url || ''),
        status_code: Number((item as VueRequestBatchRowResult).status_code || 0),
        ok: Boolean((item as VueRequestBatchRowResult).ok),
        elapsed_ms: Number((item as VueRequestBatchRowResult).elapsed_ms || 0),
        error: String((item as VueRequestBatchRowResult).error || ''),
        response_path: String((item as VueRequestBatchRowResult).response_path || ''),
        requested_at: String((item as VueRequestBatchRowResult).requested_at || ''),
        response_length: Number((item as VueRequestBatchRowResult).response_length || 0),
        packet_length: Number((item as VueRequestBatchRowResult).packet_length || 0),
      })),
    })
    applyRunSnapshots(payload.snapshots)
  } catch {
    // snapshot save failure should not break the live result page
  } finally {
    const doneSaving = new Set(savingSnapshotJobIds.value)
    doneSaving.delete(jobId)
    savingSnapshotJobIds.value = doneSaving
  }
}

const ACTIVE_REQUEST_BATCH_STATUSES = new Set(['queued', 'running', 'paused'])
const TERMINAL_REQUEST_BATCH_STATUSES = new Set(['completed', 'failed', 'stopped'])

function clearRequestBatchPollTimer() {
  if (requestBatchPollTimer !== null && typeof window !== 'undefined') {
    window.clearTimeout(requestBatchPollTimer)
  }
  requestBatchPollTimer = null
}

function scheduleRequestBatchPoll(delay = 900) {
  clearRequestBatchPollTimer()
  if (!requestBatchJobId.value || typeof window === 'undefined') return
  requestBatchPollTimer = window.setTimeout(() => {
    void pollRequestBatchJob()
  }, Math.max(200, delay))
}

function setLoadingResponseDetail(rowKey: string, loading: boolean) {
  const next = new Set(loadingResponseDetailKeys.value)
  if (loading) next.add(rowKey)
  else next.delete(rowKey)
  loadingResponseDetailKeys.value = next
}

function applyBatchJob(job: VueRequestBatchJob, options?: { silent?: boolean }) {
  const silent = Boolean(options?.silent)
  requestBatchJobId.value = String(job.job_id || requestBatchJobId.value || '')

  const total = Number(job.total || job.progress?.total || 0)
  const done = Number(job.done_count || job.progress?.done || 0)
  const okCount = Number(job.ok_count || job.progress?.ok || 0)
  const failCount = Number(job.fail_count || job.progress?.failed || 0)
  const status = String(job.status || '').trim().toLowerCase()
  requestBatchStatus.value = status || 'idle'

  requestAllTotal.value = total
  requestAllDone.value = done
  requestAllOk.value = okCount
  requestAllFail.value = failCount
  requestAllPaused.value = status === 'paused'
  requestingAll.value = ACTIVE_REQUEST_BATCH_STATUSES.has(status)

  const nextMap: Record<string, RowResponseState> = { ...responseMap.value }
  const rowResults = job.row_results && typeof job.row_results === 'object' ? job.row_results : {}
  Object.values(rowResults).forEach((item) => {
    const row = item as VueRequestBatchRowResult
    const rowKey = String(row.row_key || '').trim()
    if (!rowKey) return
    const previous = nextMap[rowKey]
    const requestedAt = row.requested_at ? Date.parse(row.requested_at) : Number.NaN
    nextMap[rowKey] = {
      requestResult: {
        job_id: requestBatchJobId.value,
        domain: currentDomain.value,
        api_id: Number(row.endpoint_id || 0),
        method: String(row.method || requestMethod.value || 'GET'),
        url: String(row.url || ''),
        baseurl: String(job.baseurl || baseurl.value || ''),
        baseapi: String(job.baseapi || baseapi.value || ''),
        status_code: Number(row.status_code || 0),
        ok: Boolean(row.ok),
        elapsed_ms: Number(row.elapsed_ms || 0),
        error: String(row.error || ''),
        response_path: String(row.response_path || ''),
      },
      responseDetail: previous?.responseDetail ?? null,
      responseLength: Number(row.response_length || 0),
      packetLength: Number(row.packet_length || 0),
      requestedAt: Number.isFinite(requestedAt) ? requestedAt : previous?.requestedAt || Date.now(),
    }
  })
  responseMap.value = nextMap

  if (status === 'failed') {
    if (!silent) error.value = String(job.error || '后台批量请求失败')
    clearRequestBatchPollTimer()
    requestingAll.value = false
    requestAllPaused.value = false
  } else if (status === 'stopped') {
    if (!silent) message.value = `后台一键请求已停止：完成 ${done}/${total}`
    clearRequestBatchPollTimer()
    requestingAll.value = false
    requestAllPaused.value = false
  } else if (status === 'completed') {
    if (!silent) message.value = `一键请求完成：成功 ${okCount}，失败 ${failCount}`
    clearRequestBatchPollTimer()
    requestingAll.value = false
    requestAllPaused.value = false
  } else if (!silent) {
    const currentPath = String(job.current_path || '')
    message.value = currentPath
      ? `后台请求中：${job.method || requestMethod.value || 'GET'} ${currentPath} (${done}/${total})`
      : `后台请求中：${done}/${total}`
  }

  if (ACTIVE_REQUEST_BATCH_STATUSES.has(status)) {
    scheduleRequestBatchPoll()
  }
  if (TERMINAL_REQUEST_BATCH_STATUSES.has(status)) {
    void ensureSavedRunSnapshot(job)
  }
  const expandedRow = tableRows.value.find((item) => item.key === expandedRowKey.value)
  if (expandedRow) {
    void ensureRowResponseDetail(expandedRow)
  }
  persistRequestTabState()
}

async function pollRequestBatchJob() {
  if (!requestBatchJobId.value || requestBatchPollBusy.value) return
  requestBatchPollBusy.value = true
  try {
    const payload = await fetchVueRequestJob(requestBatchJobId.value)
    if (payload.job?.job_id) {
      applyBatchJob(payload.job)
    }
  } catch (err) {
    if (!requestingAll.value) {
      clearRequestBatchPollTimer()
    } else {
      error.value = resolveError(err)
      scheduleRequestBatchPoll(1400)
    }
  } finally {
    requestBatchPollBusy.value = false
  }
}

function resumeRequestBatchPolling() {
  if (!requestBatchJobId.value) return
  scheduleRequestBatchPoll(120)
}

function normalizeMethod(value: string) {
  const token = String(value || '').trim().toUpperCase()
  return token || 'GET'
}

function normalizeSelectableMethod(value: string): 'GET' | 'POST' {
  return normalizeMethod(value) === 'POST' ? 'POST' : 'GET'
}

function normalizeRequestBodyType(value: unknown): ProjectBaseRequestBodyType {
  return String(value || '').trim().toLowerCase() === 'form' ? 'form' : 'json'
}

function defaultRequestBodyText(bodyType: ProjectBaseRequestBodyType) {
  return bodyType === 'form' ? '' : '{}'
}

function splitPathWithSuffix(value: string) {
  const text = String(value || '').trim()
  const match = text.match(/^([^?#]*)([?#].*)?$/)
  return {
    main: String(match?.[1] || '').trim(),
    suffix: String(match?.[2] || ''),
  }
}

function normalizePath(value: string) {
  const text = String(value || '').trim()
  if (!text) return ''
  if (/^https?:\/\//i.test(text)) return text
  return text.startsWith('/') ? text : `/${text}`
}

function trimTrailingSlash(value: string) {
  return String(value || '').trim().replace(/\/+$/, '')
}

function trimLeadingSlash(value: string) {
  return String(value || '').trim().replace(/^\/+/, '')
}

function combinePath(base: string, next: string) {
  const left = trimTrailingSlash(base)
  const right = trimLeadingSlash(next)
  if (!left && !right) return ''
  if (!left) return `/${right}`
  if (!right) return left.startsWith('/') ? left : `/${left}`
  return `${left}/${right}`
}

function buildAbsoluteUrl(baseurlValue: string, baseapiValue: string, endpointPath: string) {
  const rawPath = String(endpointPath || '').trim()
  if (!rawPath) return ''
  if (/^https?:\/\//i.test(rawPath)) return rawPath

  const parts = splitPathWithSuffix(rawPath)
  const pathMain = normalizePath(parts.main || '/')
  const normalizedBaseapi = normalizePath(baseapiValue)

  let mergedPath = pathMain
  if (normalizedBaseapi) {
    const pathMainNoSlash = trimLeadingSlash(pathMain)
    const baseapiNoSlash = trimLeadingSlash(normalizedBaseapi)
    if (!(pathMainNoSlash === baseapiNoSlash || pathMainNoSlash.startsWith(`${baseapiNoSlash}/`))) {
      mergedPath = combinePath(normalizedBaseapi, pathMain)
    }
  }

  const host = trimTrailingSlash(baseurlValue)
  if (!host) return `${mergedPath}${parts.suffix}`
  const mergedNoSlash = trimLeadingSlash(mergedPath || '/')
  return `${host}/${mergedNoSlash}${parts.suffix}`
}

function rowKeyFor(item: {
  source: RequestRow['source_type']
  endpointId: number
  method: string
  path: string
  url?: string
}) {
  const path = String(item.path || '').trim()
  const url = String(item.url || '').trim()
  return `${item.source}:${item.endpointId}:${normalizeMethod(item.method)}:${path || url}`
}

function extractPathFromUrl(url: string) {
  const text = String(url || '').trim()
  if (!text) return ''
  try {
    const parsed = new URL(text)
    const pathname = String(parsed.pathname || '').trim()
    const query = String(parsed.search || '')
    return `${pathname}${query}`
  } catch {
    const noHash = text.split('#')[0] || text
    const noQuery = noHash.split('?')[0] || noHash
    const marker = noQuery.indexOf('://')
    if (marker < 0) return noQuery
    const tail = noQuery.slice(marker + 3)
    const slashAt = tail.indexOf('/')
    if (slashAt < 0) return '/'
    return tail.slice(slashAt)
  }
}

function normalizeMatchPath(value: string) {
  return trimLeadingSlash(String(value || '').trim().split('?')[0] || '').toLowerCase()
}

function toUtf8Length(value: string) {
  return new TextEncoder().encode(String(value || '')).length
}

function toHeadersPayload(raw: string) {
  const text = String(raw || '').trim()
  if (!text) return ''
  if (text.startsWith('{')) return text
  const rows = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => Boolean(line))
  const parsed: Record<string, string> = {}
  rows.forEach((line) => {
    const splitAt = line.indexOf(':')
    if (splitAt <= 0) return
    const key = line.slice(0, splitAt).trim()
    const val = line.slice(splitAt + 1).trim()
    if (!key) return
    parsed[key] = val
  })
  if (!Object.keys(parsed).length) return text
  return JSON.stringify(parsed)
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

function buildPathWithQuery(path: string, queryText: string) {
  const main = String(path || '').trim()
  if (!main) return ''
  const query = String(queryText || '').trim().replace(/^\?+/, '')
  return query ? `${main}?${query}` : main
}

function editorActiveFor(rowKey: string) {
  return editingRowKey.value === rowKey && Boolean(editingDraft.value)
}

function rowEditorPreviewUrl() {
  if (!editingDraft.value) return ''
  return buildAbsoluteUrl(
    editingDraft.value.baseurl,
    baseapi.value,
    buildPathWithQuery(editingDraft.value.path, editingDraft.value.queryText),
  )
}

function resolveRowBodyText(row: RequestRow) {
  const globalBody = String(requestBodyText.value || '').trim()
  if (globalBody) return globalBody
  if (row.body_json !== undefined && row.body_json !== null) {
    return stringifyPretty(row.body_json, '')
  }
  if (row.body_form && Object.keys(row.body_form).length) {
    return stringifyPretty(row.body_form, '')
  }
  return String(row.request_body || '').trim()
}

function resolveRowHeadersText(row: RequestRow) {
  const globalHeaders = String(headers.value || '').trim()
  if (globalHeaders) return globalHeaders
  if (row.request_headers && Object.keys(row.request_headers).length) {
    return stringifyPretty(row.request_headers, '')
  }
  return ''
}

function prepareJsonBodyText(rawText: string, method: 'GET' | 'POST') {
  if (method !== 'POST') {
    return {
      ok: true,
      body: '',
      error: '',
    }
  }
  let body = String(rawText || '').trim()
  if (!body) body = '{}'
  try {
    JSON.parse(body)
    return {
      ok: true,
      body,
      error: '',
    }
  } catch {
    return {
      ok: false,
      body: '',
      error: 'JSON Body 不是合法 JSON',
    }
  }
}

function applyRowResponseState(row: RequestRow, payload: { requestResult: VueRequestResult; responseDetail: VueRequestResponseDetail }) {
  const detail = payload.responseDetail
  const bodyText = String(detail.response_text || '')
  const headersText = JSON.stringify(detail.response_headers || {})
  const bodyLength = toUtf8Length(bodyText)
  const headerLength = toUtf8Length(headersText)
  responseMap.value = {
    ...responseMap.value,
    [row.key]: {
      requestResult: payload.requestResult,
      responseDetail: detail,
      responseLength: bodyLength,
      packetLength: bodyLength + headerLength,
      requestedAt: Date.now(),
    },
  }
}

const endpointRows = computed<RequestRow[]>(() => {
  return endpointItems.value.map((item) => {
    const path = String(item.path || item.url || '').trim()
    const url = buildAbsoluteUrl(baseurl.value, baseapi.value, path || '/')
    return {
      key: rowKeyFor({
        source: 'endpoint',
        endpointId: Number(item.id || 0),
        method: String(item.method || 'GET'),
        path,
        url,
      }),
      endpoint_id: Number(item.id || 0),
      method: normalizeMethod(String(item.method || 'GET')),
      path,
      url,
      source_file: String(item.source_file || ''),
      source_line: Number(item.source_line || 0),
      source_type: 'endpoint',
    }
  })
})

const primaryRows = computed<RequestRow[]>(() => {
  return inferRows.value.length ? inferRows.value : endpointRows.value
})

const activeRunSnapshot = computed(() => {
  if (selectedSnapshotId.value === 'live') return null
  return runSnapshots.value.find((item) => item.snapshot_id === selectedSnapshotId.value) || null
})

const baseRequestLocked = computed(() => Boolean(props.baseRequestPreset?.seq))
const inferQuerySummary = computed(() => {
  const infer = props.inferPreset?.inferResult
  if (!infer) return ''
  return `API Reg 查询结果：query_baseurl=${String(infer.baseurl || '-')} query_baseapi=${String(infer.baseapi || '(empty)')}`
})

function rowPathToken(row: RequestRow) {
  return normalizeMatchPath(row.path || row.url || '')
}

function captureMatchScore(captureRow: RequestRow, targetRow: RequestRow) {
  const capturePath = rowPathToken(captureRow)
  const targetPath = rowPathToken(targetRow)
  if (!capturePath || !targetPath) return -1

  let score = -1
  if (captureRow.endpoint_id > 0 && targetRow.endpoint_id > 0 && captureRow.endpoint_id === targetRow.endpoint_id) {
    score = 300
  }
  if (capturePath === targetPath) {
    score = Math.max(score, 240)
  } else if (capturePath.endsWith(`/${targetPath}`)) {
    score = Math.max(score, 180)
  }
  if (score < 0) return -1
  if (normalizeMethod(captureRow.method) === normalizeMethod(targetRow.method)) {
    score += 20
  }
  score += Math.min(30, Number(captureRow.count || 0))
  return score
}

function mergeCaptureIntoRow(row: RequestRow) {
  let bestCapture: RequestRow | null = null
  let bestScore = -1

  captureRows.value.forEach((captureRow) => {
    const score = captureMatchScore(captureRow, row)
    if (score <= bestScore) return
    bestScore = score
    bestCapture = captureRow
  })

  if (!bestCapture) return row
  const matchedCapture = bestCapture as RequestRow

  // 主表只展示提取/推断出的接口，把捕获请求附着为调试参考数据。
  return {
    ...row,
    capture_url: String(matchedCapture.url || '').trim(),
    content_type: String(matchedCapture.content_type || ''),
    count: Number(matchedCapture.count || 0),
    status: Number(matchedCapture.status || 0),
    query_string: String(matchedCapture.query_string || ''),
    query_params: toStringMap(matchedCapture.query_params),
    request_body: String(matchedCapture.request_body || ''),
    body_type: String(matchedCapture.body_type || ''),
    body_json: matchedCapture.body_json,
    body_form: toStringMap(matchedCapture.body_form),
    request_headers: toStringMap(matchedCapture.request_headers) as Record<string, string>,
  }
}

const liveTableRows = computed<RequestRow[]>(() => {
  return primaryRows.value.map((row) => mergeCaptureIntoRow(row))
})

const snapshotTableRows = computed<RequestRow[]>(() => {
  if (!activeRunSnapshot.value) return []
  return (Array.isArray(activeRunSnapshot.value.rows) ? activeRunSnapshot.value.rows : []).map((item) => {
    const row = item as VueRequestRunSnapshotRow
    return {
      key: String(row.row_key || '').trim(),
      endpoint_id: Number(row.endpoint_id || 0),
      method: normalizeMethod(String(row.method || 'GET')),
      path: String(row.path || '').trim(),
      url: String(row.url || '').trim(),
      source_file: '',
      source_line: 0,
      source_type: 'infer',
    }
  })
})

const displayedResponseMap = computed<Record<string, RowResponseState>>(() => {
  const snapshot = activeRunSnapshot.value
  if (!snapshot) return responseMap.value

  const detailMap = snapshotResponseDetails.value[snapshot.snapshot_id] || {}
  const mapped: Record<string, RowResponseState> = {}
  ;(Array.isArray(snapshot.rows) ? snapshot.rows : []).forEach((item) => {
    const row = item as VueRequestRunSnapshotRow
    const rowKey = String(row.row_key || '').trim()
    if (!rowKey) return
    const requestedAt = row.requested_at ? Date.parse(row.requested_at) : Date.now()
    mapped[rowKey] = {
      requestResult: {
        job_id: String(snapshot.job_id || ''),
        domain: currentDomain.value,
        api_id: Number(row.endpoint_id || 0),
        method: String(row.method || snapshot.request?.method || 'GET'),
        url: String(row.url || ''),
        baseurl: String(snapshot.request?.baseurl || ''),
        baseapi: String(snapshot.request?.baseapi || ''),
        base_query: String(snapshot.request?.base_query || ''),
        status_code: Number(row.status_code || 0),
        ok: Boolean(row.ok),
        elapsed_ms: Number(row.elapsed_ms || 0),
        error: String(row.error || ''),
        response_path: String(row.response_path || ''),
      },
      responseDetail: detailMap[rowKey] || null,
      responseLength: Number(row.response_length || 0),
      packetLength: Number(row.packet_length || 0),
      requestedAt: Number.isFinite(requestedAt) ? requestedAt : Date.now(),
    }
  })
  return mapped
})

const tableRows = computed<RequestRow[]>(() => {
  return activeRunSnapshot.value ? snapshotTableRows.value : liveTableRows.value
})

const activeSnapshotSummary = computed(() => {
  const snapshot = activeRunSnapshot.value
  if (!snapshot) return ''
  const request = snapshot.request || ({} as VueRequestRunSnapshot['request'])
  const summary = snapshot.summary || { total: 0, done: 0, ok: 0, fail: 0 }
  return `${snapshot.title} | ${request.method || 'GET'} ${request.baseapi || '/'} | ok=${summary.ok || 0}/${summary.total || 0} | fail=${summary.fail || 0}`
})

function rowPacketLengthValue(row: RequestRow) {
  return rowResponse(row.key)?.packetLength ?? null
}

function rowStatusCodeValue(row: RequestRow) {
  const code = Number(rowResponse(row.key)?.requestResult.status_code || 0)
  if (!Number.isFinite(code) || code <= 0) return null
  return code
}

function compareNullableMetric(left: number | null, right: number | null, direction: 'asc' | 'desc') {
  const leftMissing = left === null || !Number.isFinite(left)
  const rightMissing = right === null || !Number.isFinite(right)
  if (leftMissing && rightMissing) return 0
  if (leftMissing) return 1
  if (rightMissing) return -1
  return direction === 'asc' ? left - right : right - left
}

function compareDefaultRows(left: RequestRow, right: RequestRow) {
  // 默认把 200 响应顶到前面，再按当前展示的“长度”从大到小排，便于先看最像正常页面数据的结果。
  const leftStatus = rowStatusCodeValue(left)
  const rightStatus = rowStatusCodeValue(right)
  const leftOk = leftStatus === 200 ? 1 : 0
  const rightOk = rightStatus === 200 ? 1 : 0
  if (leftOk !== rightOk) return rightOk - leftOk

  const lengthCompare = compareNullableMetric(rowPacketLengthValue(left), rowPacketLengthValue(right), 'desc')
  if (lengthCompare !== 0) return lengthCompare

  return compareNullableMetric(leftStatus, rightStatus, 'desc')
}

const sortedTableRows = computed<RequestRow[]>(() => {
  const rows = [...tableRows.value]

  rows.sort((left, right) => {
    if (requestSortKey.value === 'packet_length_desc') {
      return compareNullableMetric(rowPacketLengthValue(left), rowPacketLengthValue(right), 'desc')
    }
    if (requestSortKey.value === 'packet_length_asc') {
      return compareNullableMetric(rowPacketLengthValue(left), rowPacketLengthValue(right), 'asc')
    }
    if (requestSortKey.value === 'status_desc') {
      return compareNullableMetric(rowStatusCodeValue(left), rowStatusCodeValue(right), 'desc')
    }
    if (requestSortKey.value === 'status_asc') {
      return compareNullableMetric(rowStatusCodeValue(left), rowStatusCodeValue(right), 'asc')
    }
    return compareDefaultRows(left, right)
  })

  return rows
})

const listTotal = computed(() => sortedTableRows.value.length)

const listTotalPages = computed(() => {
  const size = Math.max(1, Number(listPageSize.value || 50))
  const total = listTotal.value
  return Math.max(1, Math.ceil(total / size))
})

const listStartIndex = computed(() => {
  const page = Math.max(1, Math.min(Number(listPage.value || 1), listTotalPages.value))
  const size = Math.max(1, Number(listPageSize.value || 50))
  return (page - 1) * size
})

const pagedTableRows = computed<RequestRow[]>(() => {
  const size = Math.max(1, Number(listPageSize.value || 50))
  const start = listStartIndex.value
  return sortedTableRows.value.slice(start, start + size)
})

function onPrevPage() {
  if (listPage.value <= 1) return
  listPage.value -= 1
  persistRequestTabState()
}

function onNextPage() {
  if (listPage.value >= listTotalPages.value) return
  listPage.value += 1
  persistRequestTabState()
}

function onToggleLengthSort() {
  requestSortKey.value = requestSortKey.value === 'packet_length_desc' ? 'packet_length_asc' : 'packet_length_desc'
  listPage.value = 1
  persistRequestTabState()
}

function onToggleStatusSort() {
  requestSortKey.value = requestSortKey.value === 'status_desc' ? 'status_asc' : 'status_desc'
  listPage.value = 1
  persistRequestTabState()
}

function onSelectSnapshot(snapshotId: string) {
  const nextSnapshotId = String(snapshotId || 'live').trim() || 'live'
  if (selectedSnapshotId.value === nextSnapshotId) return
  if (selectedSnapshotId.value === 'live') {
    liveRunConfig.value = captureActiveRunConfig()
  }
  selectedSnapshotId.value = nextSnapshotId
  listPage.value = 1
  if (nextSnapshotId === 'live') {
    applyRunConfigToForm(liveRunConfig.value || activeRunConfig.value)
  } else {
    applyRunConfigToForm(snapshotToRunConfig(runSnapshots.value.find((item) => item.snapshot_id === nextSnapshotId) || null))
  }
  persistRequestTabState()
}

async function onDeleteSnapshot(snapshotId: string) {
  const snapshotToken = String(snapshotId || '').trim()
  const domain = String(currentDomain.value || props.domain || '').trim()
  if (!snapshotToken || !domain) return
  if (!window.confirm('确认删除这个快照？')) return
  if (deletingSnapshotIds.value.has(snapshotToken)) return

  const nextDeleting = new Set(deletingSnapshotIds.value)
  nextDeleting.add(snapshotToken)
  deletingSnapshotIds.value = nextDeleting
  error.value = ''
  message.value = ''

  try {
    const wasSelected = selectedSnapshotId.value === snapshotToken
    const payload = await deleteVueRequestRunSnapshot({
      domain,
      snapshot_id: snapshotToken,
    })
    const nextDetailMap = { ...snapshotResponseDetails.value }
    delete nextDetailMap[snapshotToken]
    snapshotResponseDetails.value = nextDetailMap
    applyRunSnapshots(payload.snapshots)
    if (wasSelected) {
      selectedSnapshotId.value = 'live'
      applyRunConfigToForm(liveRunConfig.value || activeRunConfig.value)
    }
    message.value = '快照已删除'
    persistRequestTabState()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    const doneDeleting = new Set(deletingSnapshotIds.value)
    doneDeleting.delete(snapshotToken)
    deletingSnapshotIds.value = doneDeleting
  }
}

function rowSending(rowKey: string) {
  return sendingKeys.value.has(rowKey)
}

function rowResponse(rowKey: string) {
  return displayedResponseMap.value[rowKey] || null
}

function rowResponseDetailLoading(rowKey: string) {
  return loadingResponseDetailKeys.value.has(rowKey)
}

async function ensureRowResponseDetail(row: RequestRow) {
  const state = rowResponse(row.key)
  const responsePath = String(state?.requestResult.response_path || '').trim()
  if (!state || state.responseDetail || !responsePath || rowResponseDetailLoading(row.key)) return

  setLoadingResponseDetail(row.key, true)
  try {
    const payload = await fetchVueRequestResponseDetail(responsePath)
    if (activeRunSnapshot.value) {
      const snapshotId = activeRunSnapshot.value.snapshot_id
      snapshotResponseDetails.value = {
        ...snapshotResponseDetails.value,
        [snapshotId]: {
          ...(snapshotResponseDetails.value[snapshotId] || {}),
          [row.key]: payload.responseDetail,
        },
      }
    } else {
      responseMap.value = {
        ...responseMap.value,
        [row.key]: {
          ...state,
          responseDetail: payload.responseDetail,
        },
      }
    }
    persistRequestTabState()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    setLoadingResponseDetail(row.key, false)
  }
}

function rowPacketLength(rowKey: string) {
  const state = rowResponse(rowKey)
  return state ? state.packetLength : null
}

function rowStatus(rowKey: string) {
  const state = rowResponse(rowKey)
  if (!state) return 'idle'
  return state.requestResult.ok ? 'done' : 'failed'
}

function rowElapsed(rowKey: string) {
  const state = rowResponse(rowKey)
  if (!state) return null
  return Number(state.requestResult.elapsed_ms || 0)
}

function rowDisplayMethod(row: RequestRow) {
  const responseMethod = String(rowResponse(row.key)?.requestResult.method || '').trim().toUpperCase()
  if (responseMethod) return responseMethod
  return String(requestMethod.value || row.method || 'GET').trim().toUpperCase() || 'GET'
}

function rowBodyPreview(row: RequestRow) {
  const state = rowResponse(row.key)
  const responseText = String(state?.responseDetail?.response_text || '')
  if (responseText) return responseText
  const requestError = String(state?.requestResult?.error || '')
  if (requestError) return requestError
  return ''
}

function rowSelectedClass(rowKey: string) {
  return selectedRowKey.value === rowKey
}

function prepareGlobalPostBody() {
  if (requestMethod.value !== 'POST') {
    return {
      ok: true,
      body: '',
      error: '',
    }
  }
  let body = String(requestBodyText.value || '').trim()
  if (!body) {
    body = '{}'
    requestBodyText.value = body
  }
  try {
    JSON.parse(body)
    return {
      ok: true,
      body,
      error: '',
    }
  } catch {
    return {
      ok: false,
      body: '',
      error: '全局 JSON Body 不是合法 JSON',
    }
  }
}

void prepareJsonBodyText
void prepareGlobalPostBody

function prepareRequestBody(rawText: string, method: 'GET' | 'POST', bodyType: ProjectBaseRequestBodyType) {
  if (method !== 'POST') {
    return {
      ok: true,
      jsonBody: '',
      bodyText: '',
      contentType: '',
      error: '',
    }
  }

  const body = String(rawText || '').trim()
  if (bodyType === 'form') {
    return {
      ok: true,
      jsonBody: '',
      bodyText: body,
      contentType: 'application/x-www-form-urlencoded; charset=utf-8',
      error: '',
    }
  }

  let normalizedBody = body
  if (!normalizedBody) {
    normalizedBody = '{}'
  }
  try {
    JSON.parse(normalizedBody)
    return {
      ok: true,
      jsonBody: normalizedBody,
      bodyText: '',
      contentType: '',
      error: '',
    }
  } catch {
    return {
      ok: false,
      jsonBody: '',
      bodyText: '',
      contentType: '',
      error: 'JSON Body 涓嶆槸鍚堟硶 JSON',
    }
  }
}

function setSending(rowKey: string, sending: boolean) {
  const next = new Set(sendingKeys.value)
  if (sending) next.add(rowKey)
  else next.delete(rowKey)
  sendingKeys.value = next
}

function toStringMap(raw: unknown): Record<string, unknown> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  return raw as Record<string, unknown>
}

function normalizeCapturedRow(raw: VueCapturedRequest): RequestRow | null {
  const capturedUrl = String(raw?.url || '').trim()
  if (!capturedUrl) return null
  const capturedMethod = normalizeMethod(String(raw?.method || 'GET'))
  const mapped = tryMatchEndpointFromCapturedUrl(capturedUrl)
  const pathValue = String(raw?.path || '').trim() || extractPathFromUrl(capturedUrl)

  return {
    key: rowKeyFor({
      source: 'capture',
      endpointId: Number(mapped?.endpoint_id || 0),
      method: capturedMethod,
      path: pathValue,
      url: capturedUrl,
    }),
    endpoint_id: Number(mapped?.endpoint_id || 0),
    method: capturedMethod,
    path: pathValue,
    url: capturedUrl,
    content_type: String(raw?.content_type || ''),
    source_file: '',
    source_line: 0,
    source_type: 'capture',
    count: Number(raw?.count || 1),
    status: Number(raw?.status || 0),
    query_string: String(raw?.query_string || ''),
    query_params: toStringMap(raw?.query_params),
    request_body: String(raw?.request_body || ''),
    body_type: String(raw?.body_type || ''),
    body_json: raw?.body_json,
    body_form: toStringMap(raw?.body_form),
    request_headers: toStringMap(raw?.request_headers) as Record<string, string>,
  }
}

async function loadContext(targetDomain?: string) {
  loadingContext.value = true
  error.value = ''
  try {
    const payload = await fetchVueRequestContext(targetDomain || currentDomain.value || props.domain || '')
    currentDomain.value = String(payload.domain || targetDomain || props.domain || currentDomain.value || '')
    baseurl.value = String(payload.baseurl || '')
    baseapi.value = String(payload.baseapi || '')
    timeout.value = Number(payload.timeout || 20)
    headers.value = String(payload.headers || '')
    captureRequestTotal.value = Number(payload.capture_request_total || 0)
    requestMethod.value = normalizeSelectableMethod(String(payload.method || requestMethod.value || 'GET'))
    const payloadBody = String(payload.json_body || '').trim()
    if (payloadBody) {
      requestBodyText.value = payloadBody
    } else if (requestMethod.value === 'POST' && !String(requestBodyText.value || '').trim()) {
      requestBodyText.value = defaultRequestBodyText(requestBodyType.value)
    }
    endpointItems.value = Array.isArray(payload.endpoints) ? payload.endpoints : []
    const capturedRowsRaw = Array.isArray(payload.captured_requests) ? payload.captured_requests : []
    const capturedRowsNormalized = capturedRowsRaw
      .map((item) => normalizeCapturedRow(item as VueCapturedRequest))
      .filter((item): item is RequestRow => Boolean(item))
      .sort((a, b) => Number(b.count || 0) - Number(a.count || 0))
    captureRows.value = capturedRowsNormalized
    applyRunSnapshots(Array.isArray(payload.request_snapshots) ? payload.request_snapshots : [])

    if (!selectedRowKey.value && tableRows.value.length) {
      const firstRow = tableRows.value[0]
      if (firstRow) {
        selectedRowKey.value = firstRow.key
        expandedRowKey.value = firstRow.key
      }
    }
    persistRequestTabState()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    loadingContext.value = false
  }
}

function applyInferPreset(preset: InferPreset | null | undefined) {
  if (!preset || !preset.inferResult) return
  const infer = preset.inferResult
  currentDomain.value = String(infer.domain || currentDomain.value || props.domain || '')
  if (typeof infer.baseurl === 'string') baseurl.value = String(infer.baseurl || '')
  if (typeof infer.baseapi === 'string') baseapi.value = String(infer.baseapi || '')

  const rows = Array.isArray(infer.compose_preview) ? infer.compose_preview : []
  inferRows.value = rows.map((item, index) => {
    const endpointPath = String(item.path || item.url || '').trim()
    const endpointId = Number(item.id || index + 1)
    const method = normalizeMethod(String(item.method || 'GET'))
    const resolvedUrl = String(item.url || '').trim() || buildAbsoluteUrl(baseurl.value, baseapi.value, endpointPath || '/')
    return {
      key: rowKeyFor({
        source: 'infer',
        endpointId,
        method,
        path: endpointPath,
        url: resolvedUrl,
      }),
      endpoint_id: endpointId,
      method,
      path: endpointPath,
      url: resolvedUrl,
      source_file: '',
      source_line: 0,
      source_type: 'infer',
    }
  })

  if (inferRows.value.length) {
    const firstRow = inferRows.value[0]
    if (firstRow) {
      selectedRowKey.value = firstRow.key
      expandedRowKey.value = firstRow.key
    }
    message.value = `已接收 API Reg 查询结果：query_baseurl=${baseurl.value || '-'} query_baseapi=${baseapi.value || '(empty)'}`
  } else {
    message.value = '已查询 BaseURL / BaseAPI，但组合预览为空。'
  }
  persistRequestTabState()
}

function applyBaseRequestPreset(presetEnvelope: ProjectBaseRequestPresetEnvelope | null | undefined) {
  const preset = presetEnvelope?.preset
  if (!preset) return

  baseurl.value = String(preset.baseurl || '').trim()
  baseapi.value = String(preset.baseapi || '').trim()
  baseQueryText.value = String(preset.baseQuery || '').trim()
  headers.value = String(preset.baseHeaders || '').trim()
  requestMethod.value = preset.requestMethod === 'POST' ? 'POST' : 'GET'
  requestBodyType.value = normalizeRequestBodyType(preset.baseBodyType)
  requestBodyText.value = String(preset.baseBody || '').trim()
  message.value = '已接收 BaseRequest 固定参数，ApiRequest 将按该基础请求包执行'
  persistRequestTabState()
}

function tryMatchEndpointFromCapturedUrl(url: string) {
  const comparePath = normalizeMatchPath(extractPathFromUrl(url))
  if (!comparePath) return null
  return primaryRows.value.find((item) => {
    const pathToken = normalizeMatchPath(item.path || item.url || '')
    if (!pathToken) return false
    return comparePath === pathToken || comparePath.endsWith(`/${pathToken}`)
  }) || null
}

function applyCapturePreset(preset: CapturePreset | null | undefined) {
  if (!preset) return
  const capturedUrl = String(preset.url || '').trim()
  if (!capturedUrl) return
  const capturedMethod = normalizeMethod(String(preset.method || 'GET'))

  const existingCapture = captureRows.value.find((item) => String(item.url || '').trim() === capturedUrl)

  if (!existingCapture) {
    const captureRow: RequestRow = {
      key: rowKeyFor({
        source: 'capture',
        endpointId: 0,
        method: capturedMethod,
        path: extractPathFromUrl(capturedUrl),
        url: capturedUrl,
      }),
      endpoint_id: 0,
      method: capturedMethod,
      path: extractPathFromUrl(capturedUrl),
      url: capturedUrl,
      source_file: '',
      source_line: 0,
      source_type: 'capture',
      request_body: String(preset.request_body || ''),
    }
    const deduped = [captureRow, ...captureRows.value].filter((item, index, rows) => {
      return rows.findIndex((row) => row.key === item.key) === index
    })
    captureRows.value = deduped
  }

  const target = tryMatchEndpointFromCapturedUrl(capturedUrl)
  if (!target) {
    message.value = '已记录请求样本，但未匹配到当前接口'
    persistRequestTabState()
    return
  }

  selectedRowKey.value = target.key
  expandedRowKey.value = target.key
  requestMethod.value = normalizeSelectableMethod(capturedMethod)
  if (requestMethod.value === 'POST') {
    const capturedBody = String(preset.request_body || '').trim()
    requestBodyText.value = capturedBody || '{}'
  }
  message.value = '已匹配到当前接口，主表保持提取结果'
  persistRequestTabState()
}

function onStartRowEdit(row: RequestRow) {
  const sourcePath = String(row.path || extractPathFromUrl(row.url) || '').trim()
  const parts = splitPathWithSuffix(sourcePath)
  const querySuffix = String(parts.suffix || '').trim()
  editingRowKey.value = row.key
  editingDraft.value = {
    method: normalizeSelectableMethod(rowDisplayMethod(row)),
    baseurl: String(baseurl.value || '').trim(),
    path: String(parts.main || sourcePath || '/').trim() || '/',
    queryText: String(baseQueryText.value || '').trim() || querySuffix.replace(/^[?#]+/, ''),
    headersText: resolveRowHeadersText(row),
    bodyText: resolveRowBodyText(row),
  }
}

function onCancelRowEdit() {
  editingRowKey.value = ''
  editingDraft.value = null
}

async function sendRow(row: RequestRow, silent = false, preparedPostBody = '') {
  if (!currentDomain.value) {
    if (!silent) error.value = '项目域名缺失'
    return false
  }
  if (row.endpoint_id <= 0) {
    if (!silent) error.value = '当前行未匹配到接口 ID'
    return false
  }

  setSending(row.key, true)
  if (!silent) {
    error.value = ''
    message.value = ''
  }

  const requestMethodValue = requestMethod.value
  let requestBody = ''
  let requestBodyTextValue = ''
  let requestContentType = ''
  if (requestMethodValue === 'POST') {
    if (preparedPostBody) {
      if (requestBodyType.value === 'form') {
        requestBodyTextValue = preparedPostBody
        requestContentType = 'application/x-www-form-urlencoded; charset=utf-8'
      } else {
        requestBody = preparedPostBody
      }
    } else {
      const prepared = prepareRequestBody(requestBodyText.value, requestMethodValue, requestBodyType.value)
      if (!prepared.ok) {
        if (!silent) error.value = prepared.error
        return false
      }
      if (requestBodyType.value === 'json' && prepared.jsonBody && !String(requestBodyText.value || '').trim()) {
        requestBodyText.value = prepared.jsonBody
      }
      requestBody = prepared.jsonBody
      requestBodyTextValue = prepared.bodyText
      requestContentType = prepared.contentType
    }
  }

  try {
    const payload = await runVueRequest({
      domain: currentDomain.value,
      api_id: row.endpoint_id,
      method: requestMethodValue,
      baseurl: baseurl.value,
      baseapi: baseapi.value,
      base_query: baseQueryText.value,
      timeout: Math.max(1, Number(timeout.value || 20)),
      json_body: requestBody,
      body_type: requestBodyType.value,
      body_text: requestBodyTextValue,
      content_type: requestContentType,
      headers: toHeadersPayload(headers.value),
      use_capture_template: false,
    })

    applyRowResponseState(row, payload)

    if (!silent) {
      selectedRowKey.value = row.key
      expandedRowKey.value = row.key
      message.value = `已请求：${requestMethodValue} ${row.path || row.url}`
    }
    persistRequestTabState()
    return true
  } catch (err) {
    if (!silent) error.value = resolveError(err)
    persistRequestTabState()
    return false
  } finally {
    setSending(row.key, false)
    persistRequestTabState()
  }
}

async function onRequestOne(row: RequestRow) {
  selectedSnapshotId.value = 'live'
  await sendRow(row, false)
}

async function onSendEditedRow(row: RequestRow) {
  const draft = editingDraft.value
  if (!draft || editingRowKey.value !== row.key) return
  if (!currentDomain.value) {
    error.value = '项目域名缺失'
    return
  }
  if (row.endpoint_id <= 0) {
    error.value = '当前行未匹配到接口 ID'
    return
  }

  const preparedBody = prepareRequestBody(draft.bodyText, draft.method, requestBodyType.value)
  if (!preparedBody.ok) {
    error.value = preparedBody.error
    return
  }

  const requestUrlOverride = rowEditorPreviewUrl()
  if (!requestUrlOverride) {
    error.value = '临时请求 URL 为空'
    return
  }

  setSending(row.key, true)
  selectedSnapshotId.value = 'live'
  error.value = ''
  message.value = ''
  try {
    const payload = await runVueRequest({
      domain: currentDomain.value,
      api_id: row.endpoint_id,
      method: draft.method,
      baseurl: draft.baseurl,
      baseapi: baseapi.value,
      base_query: '',
      timeout: Math.max(1, Number(timeout.value || 20)),
      json_body: preparedBody.jsonBody,
      body_type: requestBodyType.value,
      body_text: preparedBody.bodyText,
      content_type: preparedBody.contentType,
      headers: toHeadersPayload(draft.headersText),
      use_capture_template: false,
      request_url_override: requestUrlOverride,
    })

    applyRowResponseState(row, payload)
    selectedRowKey.value = row.key
    expandedRowKey.value = row.key
    editingRowKey.value = ''
    editingDraft.value = null
    persistRequestTabState()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    setSending(row.key, false)
    persistRequestTabState()
  }
}

/* function onSaveAllResultsRemoved() {
  if (!currentDomain.value) {
    error.value = '项目域名缺失'
    return
  }
  const rows = savableRows.value
  if (!rows.length) {
    error.value = '当前还没有可保存的请求结果'
    return
  }

  savingAllResults.value = true
  error.value = ''
  try {
    const payload = await saveVueRequestResults({
      domain: currentDomain.value,
      rows: rows
        .map((row) => {
          const state = rowResponse(row.key)
          if (!state) return null
          return {
            row_key: row.key,
            endpoint_id: row.endpoint_id,
            path: row.path || row.url || '',
            response_length: state.responseLength,
            packet_length: state.packetLength,
            request_result: state.requestResult,
            response_detail: state.responseDetail,
          }
        })
        .filter((item): item is NonNullable<typeof item> => Boolean(item)),
    })
    applySavedResults(payload.savedResults)
    message.value = `已批量保存 ${payload.savedCount} 条结果`
    persistRequestTabState()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    savingAllResults.value = false
  }
}

*/

async function onToggleRequestAllPause() {
  if (!requestBatchJobId.value || !requestingAll.value) return
  try {
    const payload = requestAllPaused.value
      ? await resumeVueRequestJob(requestBatchJobId.value)
      : await pauseVueRequestJob(requestBatchJobId.value)
    applyBatchJob(payload.job, { silent: true })
    message.value = requestAllPaused.value ? '后台一键请求已暂停' : '后台一键请求已恢复'
    persistRequestTabState()
  } catch (err) {
    error.value = resolveError(err)
  }
}

async function onRequestAll() {
  if (requestingAll.value) return
  const rows = tableRows.value.filter((item) => item.endpoint_id > 0)
  if (!rows.length) {
    error.value = '暂无可请求的 endpoint 行'
    return
  }
  const prepared = prepareRequestBody(requestBodyText.value, requestMethod.value, requestBodyType.value)
  if (!prepared.ok) {
    error.value = prepared.error
    return
  }
  try {
    const workerCount = Math.min(
      Math.max(1, Math.trunc(Number(requestAllConcurrency.value || 16))),
      REQUEST_ALL_CONCURRENCY_MAX,
      rows.length,
    )
    error.value = ''
    selectedSnapshotId.value = 'live'
    activeRunConfig.value = captureActiveRunConfig()
    responseMap.value = {}
    loadingResponseDetailKeys.value = new Set()
    const payload = await runVueRequestBatch({
      domain: currentDomain.value,
      rows: rows.map((row) => ({
        row_key: row.key,
        endpoint_id: row.endpoint_id,
        method: requestMethod.value,
        path: row.path,
      })),
      method: requestMethod.value,
      baseurl: baseurl.value,
      baseapi: baseapi.value,
      base_query: baseQueryText.value,
      timeout: Math.max(1, Number(timeout.value || 20)),
      json_body: prepared.jsonBody,
      body_type: requestBodyType.value,
      body_text: prepared.bodyText,
      content_type: prepared.contentType,
      headers: toHeadersPayload(headers.value),
      use_capture_template: false,
      concurrency: workerCount,
    })
    applyBatchJob(payload.job, { silent: true })
    message.value = `后台一键请求已启动（并发 ${workerCount}）`
    persistRequestTabState()
  } catch (err) {
    error.value = resolveError(err)
  }
}

function onSelectRow(row: RequestRow) {
  selectedRowKey.value = row.key
  expandedRowKey.value = expandedRowKey.value === row.key ? '' : row.key
  if (expandedRowKey.value === row.key) {
    void ensureRowResponseDetail(row)
  }
  persistRequestTabState()
}

watch(
  () => listPageSize.value,
  () => {
    listPage.value = 1
    persistRequestTabState()
  },
)

watch(
  () => listTotal.value,
  () => {
    if (listPage.value > listTotalPages.value) {
      listPage.value = listTotalPages.value
    }
    if (listPage.value < 1) {
      listPage.value = 1
    }
    persistRequestTabState()
  },
)

watch(
  () => props.domain,
  async (value) => {
    clearRequestBatchPollTimer()
    requestBatchPollBusy.value = false
    requestBatchJobId.value = ''
    requestBatchStatus.value = 'idle'
    requestingAll.value = false
    requestAllPaused.value = false
    requestAllTotal.value = 0
    requestAllDone.value = 0
    requestAllOk.value = 0
    requestAllFail.value = 0
    currentDomain.value = String(value || '').trim()
    baseurl.value = ''
    baseapi.value = ''
    baseQueryText.value = ''
    headers.value = ''
    inferRows.value = []
    captureRows.value = []
    responseMap.value = {}
    runSnapshots.value = []
    snapshotResponseDetails.value = {}
    savingSnapshotJobIds.value = new Set()
    activeRunConfig.value = null
    liveRunConfig.value = null
    loadingResponseDetailKeys.value = new Set()
    editingRowKey.value = ''
    editingDraft.value = null
    requestMethod.value = 'GET'
    requestBodyType.value = 'json'
    requestBodyText.value = ''
    selectedSnapshotId.value = 'live'
    selectedRowKey.value = ''
    expandedRowKey.value = ''
    listPage.value = 1
    await loadContext(currentDomain.value)
    await loadRunSnapshots(currentDomain.value)
    restorePersistedRequestTabState(currentDomain.value)
    if (props.baseRequestPreset?.preset) {
      applyBaseRequestPreset(props.baseRequestPreset)
    }
    syncSelectedSnapshotForm()
    resumeRequestBatchPolling()
  },
)

watch(
  () => props.refreshKey,
  async (value, prev) => {
    if (value === prev) return
    await loadContext(currentDomain.value || props.domain)
    await loadRunSnapshots(currentDomain.value || props.domain || '')
    restorePersistedRequestTabState(currentDomain.value || props.domain || '')
    if (props.baseRequestPreset?.preset) {
      applyBaseRequestPreset(props.baseRequestPreset)
    }
    syncSelectedSnapshotForm()
    resumeRequestBatchPolling()
  },
)

watch(
  () => props.inferPreset?.seq,
  (value, prev) => {
    if (!value || value === prev) return
    applyInferPreset(props.inferPreset || null)
  },
)

watch(
  () => props.baseRequestPreset?.seq,
  (value, prev) => {
    if (!value || value === prev) return
    applyBaseRequestPreset(props.baseRequestPreset || null)
    syncSelectedSnapshotForm()
  },
)

watch(
  () => props.captureUrlPresetSeq,
  (value, prev) => {
    if (!value || value === prev) return
    applyCapturePreset(props.capturePreset || null)
  },
)

watch(
  () => requestMethod.value,
  (value) => {
    if (value === 'POST' && !String(requestBodyText.value || '').trim()) {
      requestBodyText.value = defaultRequestBodyText(requestBodyType.value)
    }
    persistRequestTabState()
  },
)

watch(
  () => requestBodyType.value,
  (value, prev) => {
    if (value === prev) return
    if (requestMethod.value === 'POST' && !String(requestBodyText.value || '').trim()) {
      requestBodyText.value = defaultRequestBodyText(value)
    }
    persistRequestTabState()
  },
)

watch(
  () => editingDraft.value?.method,
  (value) => {
    if (value === 'POST' && editingDraft.value && !String(editingDraft.value.bodyText || '').trim()) {
      editingDraft.value = {
        ...editingDraft.value,
        bodyText: defaultRequestBodyText(requestBodyType.value),
      }
    }
  },
)

watch(
  () => requestAllConcurrency.value,
  (value) => {
    const normalized = Math.max(1, Math.min(REQUEST_ALL_CONCURRENCY_MAX, Math.trunc(Number(value || 1))))
    if (normalized !== value) {
      requestAllConcurrency.value = normalized
      return
    }
    persistRequestTabState()
  },
)

watch(
  () => tableRows.value.map((item) => item.key).join('|'),
  () => {
    if (editingRowKey.value && !tableRows.value.some((item) => item.key === editingRowKey.value)) {
      editingRowKey.value = ''
      editingDraft.value = null
    }
    if (selectedRowKey.value && tableRows.value.some((item) => item.key === selectedRowKey.value)) return
    if (!tableRows.value.length) {
      selectedRowKey.value = ''
      expandedRowKey.value = ''
      return
    }
    const firstRow = tableRows.value[0]
    if (firstRow) {
      selectedRowKey.value = firstRow.key
    }
    persistRequestTabState()
  },
)

watch(
  [
    () => baseurl.value,
    () => baseapi.value,
    () => baseQueryText.value,
    () => timeout.value,
    () => headers.value,
    () => requestBodyType.value,
    () => requestBodyText.value,
    () => requestAllConcurrency.value,
    () => requestSortKey.value,
  ],
  () => {
    persistRequestTabState()
  },
)

  onMounted(async () => {
  currentDomain.value = String(props.domain || '').trim()
  await loadContext(currentDomain.value)
  await loadRunSnapshots(currentDomain.value)
  restorePersistedRequestTabState(currentDomain.value)
  resumeRequestBatchPolling()
  if (props.inferPreset?.inferResult) {
    applyInferPreset(props.inferPreset)
  }
  if (props.baseRequestPreset?.preset) {
    applyBaseRequestPreset(props.baseRequestPreset)
  }
  if (props.capturePreset?.url) {
    applyCapturePreset(props.capturePreset)
  }
  syncSelectedSnapshotForm()
})

onUnmounted(() => {
  clearRequestBatchPollTimer()
})
</script>

<template>
  <section class="project-request-tab">
    <div v-if="message" class="notice success">{{ message }}</div>
    <div v-if="error" class="notice error">{{ error }}</div>

    <div class="sub-block">
      <div class="sub-head">
        <h4>ApiRequest</h4>
        <div class="sub-head-actions">
          <button class="ghost" :disabled="loadingContext" @click="loadContext(currentDomain)">
            {{ loadingContext ? '加载中...' : '刷新' }}
          </button>
          <button
            class="ghost"
            :disabled="!requestingAll"
            @click="onToggleRequestAllPause"
          >
            {{ requestAllPaused ? '继续' : '暂停' }}
          </button>
          <button :disabled="requestingAll || !tableRows.length" @click="onRequestAll">
            {{ requestingAll ? '运行中...' : 'Run All' }}
          </button>
        </div>
      </div>

      <div v-if="inferQuerySummary || baseRequestLocked" class="request-meta">
        <span v-if="inferQuerySummary" class="request-meta-item mono">{{ inferQuerySummary }}</span>
        <span v-if="baseRequestLocked" class="request-meta-item">locked</span>
      </div>

      <div class="request-raw">
        <div class="raw-line raw-line-first">
          <select v-model="requestMethod" class="method-select" :disabled="baseRequestLocked">
            <option value="GET">GET</option>
            <option value="POST">POST</option>
          </select>
          <input v-model="baseapi" type="text" placeholder="/baseapi" :disabled="baseRequestLocked" />
          <span class="line-token">?</span>
          <input
            v-model="baseQueryText"
            type="text"
            :disabled="baseRequestLocked"
            placeholder="page=1&size=10"
          />
          <div class="line-inline">
            <span class="line-label">并发</span>
            <input v-model.number="requestAllConcurrency" type="number" min="1" :max="REQUEST_ALL_CONCURRENCY_MAX" />
          </div>
        </div>

        <div class="raw-line raw-line-simple">
          <span class="line-label">BaseURL</span>
          <input v-model="baseurl" type="text" placeholder="https://target.example.com" :disabled="baseRequestLocked" />
        </div>

        <div class="raw-line raw-line-block">
          <div class="raw-line-head">
            <span class="line-label">BaseHeader</span>
            <span v-if="baseRequestLocked" class="line-meta">locked</span>
          </div>
          <textarea
            v-model="headers"
            rows="4"
            :disabled="baseRequestLocked"
            placeholder="{&quot;Authorization&quot;:&quot;Bearer ...&quot;}"
          ></textarea>
        </div>

        <div class="raw-line raw-line-block">
          <div class="raw-line-head">
            <span class="line-label">BaseBody</span>
            <span class="line-meta">{{ requestMethod }} / {{ requestBodyType.toUpperCase() }}</span>
          </div>
          <textarea
            v-model="requestBodyText"
            rows="4"
            :disabled="requestMethod !== 'POST' || baseRequestLocked"
            placeholder="{&quot;page&quot;:1,&quot;size&quot;:10}"
          ></textarea>
        </div>

      </div>
      <div class="request-all-status mono">
        status={{ requestAllStatusText }} | done={{ requestAllDone }}/{{ requestAllTotal }} | ok={{ requestAllOk }} | fail={{ requestAllFail }}
      </div>
    </div>

    <div class="sub-block">
      <div v-if="runSnapshots.length" class="run-snapshot-strip">
        <button class="ghost btn-sm" :class="{ active: selectedSnapshotId === 'live' }" @click="onSelectSnapshot('live')">
          当前
        </button>
        <div
          v-for="snapshot in runSnapshots"
          :key="snapshot.snapshot_id"
          class="snapshot-chip"
          :class="{ active: selectedSnapshotId === snapshot.snapshot_id }"
        >
          <button
            class="ghost btn-sm snapshot-chip-main"
            :class="{ active: selectedSnapshotId === snapshot.snapshot_id }"
            @click="onSelectSnapshot(snapshot.snapshot_id)"
          >
            {{ snapshot.title }}
          </button>
          <button
            class="snapshot-chip-close"
            :disabled="deletingSnapshotIds.has(snapshot.snapshot_id)"
            @click.stop="onDeleteSnapshot(snapshot.snapshot_id)"
          >
            {{ deletingSnapshotIds.has(snapshot.snapshot_id) ? '…' : '×' }}
          </button>
        </div>
      </div>
      <div v-if="activeSnapshotSummary" class="request-meta">
        <span class="request-meta-item mono">{{ activeSnapshotSummary }}</span>
      </div>
      <div v-if="tableRows.length" class="table-pager">
        <div class="table-pager-info">
          共 {{ listTotal }} 条 · 第 {{ listPage }} / {{ listTotalPages }} 页
        </div>
        <div class="table-pager-actions">
          <label for="request-page-size">每页</label>
          <select id="request-page-size" v-model.number="listPageSize" class="pager-size-select">
            <option v-for="size in LIST_PAGE_SIZE_OPTIONS" :key="`page-size-${size}`" :value="size">
              {{ size }}
            </option>
          </select>
          <button class="ghost btn-sm" :disabled="listPage <= 1" @click="onPrevPage">上一页</button>
          <button class="ghost btn-sm" :disabled="listPage >= listTotalPages" @click="onNextPage">下一页</button>
        </div>
      </div>
      <table v-if="tableRows.length" class="task-table request-table">
        <thead>
          <tr>
            <th class="index-col">#</th>
            <th class="method-col">方法</th>
            <th class="path-col">路径</th>
            <th class="url-col">URL</th>
            <th class="len-col">
              <button class="sort-toggle" type="button" @click="onToggleLengthSort">
                长度
                <span class="sort-toggle-mark">
                  {{ requestSortKey === 'packet_length_desc' ? '↓' : requestSortKey === 'packet_length_asc' ? '↑' : '↕' }}
                </span>
              </button>
            </th>
            <th class="status-col">
              <button class="sort-toggle" type="button" @click="onToggleStatusSort">
                状态
                <span class="sort-toggle-mark">
                  {{ requestSortKey === 'status_desc' ? '↓' : requestSortKey === 'status_asc' ? '↑' : '↕' }}
                </span>
              </button>
            </th>
            <th class="elapsed-col">耗时</th>
            <th class="action-col">操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(row, index) in pagedTableRows" :key="row.key">
            <tr
              :class="{ active: rowSelectedClass(row.key) }"
              @click="onSelectRow(row)"
            >
              <td class="index-col">{{ listStartIndex + index + 1 }}</td>
              <td class="method-col">{{ rowDisplayMethod(row) }}</td>
              <td class="mono path-col">{{ row.path || '-' }}</td>
              <td class="mono url-col">{{ row.url || '-' }}</td>
              <td class="len-col">{{ rowPacketLength(row.key) ?? '-' }}</td>
              <td class="status-col">
                <span class="status-pill" :class="rowStatus(row.key)">
                  {{ rowResponse(row.key)?.requestResult.status_code || '-' }}
                </span>
              </td>
              <td class="elapsed-col">{{ rowElapsed(row.key) ?? '-' }}</td>
              <td class="action-col">
                <button
                  class="ghost btn-sm"
                  :disabled="rowSending(row.key) || row.endpoint_id <= 0"
                  @click.stop="onRequestOne(row)"
                >
                  {{ rowSending(row.key) ? '请求中...' : '请求' }}
                </button>
              </td>
            </tr>

            <tr
              v-if="expandedRowKey === row.key"
              class="response-row"
            >
              <td colspan="8">
                <div class="response-wrap">
                  <div class="response-toolbar">
                    <span class="line-meta mono">
                      {{ rowDisplayMethod(row) }} {{ row.path || row.url || '-' }}
                    </span>
                    <div class="response-toolbar-actions">
                      <button
                        v-if="!editorActiveFor(row.key)"
                        class="ghost btn-sm"
                        :disabled="row.endpoint_id <= 0"
                        @click.stop="onStartRowEdit(row)"
                      >
                        修改
                      </button>
                      <template v-else>
                        <button class="ghost btn-sm" @click.stop="onCancelRowEdit">取消</button>
                        <button
                          class="ghost btn-sm"
                          :disabled="rowSending(row.key) || row.endpoint_id <= 0"
                          @click.stop="onSendEditedRow(row)"
                        >
                          {{ rowSending(row.key) ? '发送中..' : '发送' }}
                        </button>
                      </template>
                    </div>
                  </div>

                  <div v-if="editorActiveFor(row.key) && editingDraft" class="response-editor">
                    <div class="raw-line raw-line-first">
                      <select v-model="editingDraft.method" class="method-select">
                        <option value="GET">GET</option>
                        <option value="POST">POST</option>
                      </select>
                      <input v-model="editingDraft.path" type="text" placeholder="/api/path" />
                      <span class="line-token">?</span>
                      <input v-model="editingDraft.queryText" type="text" placeholder="page=1&size=10" />
                      <div class="line-inline">
                        <span class="line-label">Preview</span>
                        <span class="line-meta mono editor-url-preview">{{ rowEditorPreviewUrl() || '-' }}</span>
                      </div>
                    </div>

                    <div class="raw-line raw-line-simple">
                      <span class="line-label">BaseURL</span>
                      <input v-model="editingDraft.baseurl" type="text" placeholder="https://target.example.com" />
                    </div>

                    <div class="raw-line raw-line-block">
                      <div class="raw-line-head">
                        <span class="line-label">Headers</span>
                      </div>
                      <textarea
                        v-model="editingDraft.headersText"
                        rows="4"
                        placeholder="{&quot;Authorization&quot;:&quot;Bearer ...&quot;}"
                      ></textarea>
                    </div>

                    <div class="raw-line raw-line-block">
                      <div class="raw-line-head">
                        <span class="line-label">Body</span>
                        <span class="line-meta">{{ editingDraft.method }} / {{ requestBodyType.toUpperCase() }}</span>
                      </div>
                      <textarea
                        v-model="editingDraft.bodyText"
                        rows="6"
                        :disabled="editingDraft.method !== 'POST'"
                        placeholder="{&quot;accountName&quot;:&quot;demo&quot;}"
                      ></textarea>
                    </div>
                  </div>

                  <pre v-else-if="rowResponse(row.key) && rowBodyPreview(row)" class="result-json">{{ rowBodyPreview(row) }}</pre>
                  <div v-else-if="rowResponse(row.key) && rowResponseDetailLoading(row.key)" class="empty detail-loading">loading...</div>
                  <div v-else-if="rowResponse(row.key)" class="empty detail-loading">empty body</div>
                  <div v-else class="empty">No response.</div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <div v-else class="empty">暂无可用 API 行。</div>
    </div>
  </section>
</template>

<style scoped>
.project-request-tab {
  display: grid;
  gap: 12px;
}

.sub-block {
  border: 1px solid #e3eaf2;
  border-radius: 10px;
  background: #fcfdff;
  padding: 10px;
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

.sub-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.request-meta {
  margin-top: 8px;
  display: grid;
  gap: 10px;
}

.request-meta-item {
  color: #59728a;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.run-snapshot-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.run-snapshot-strip .btn-sm.active {
  background: #dceefe;
  border-color: #8fbbe7;
  color: #14476d;
}

.snapshot-chip {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.snapshot-chip-main {
  padding-right: 22px;
}

.snapshot-chip-close {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 16px;
  height: 16px;
  border: 1px solid #c9d9e8;
  border-radius: 999px;
  background: #fff;
  color: #5c7288;
  font-size: 12px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  opacity: 0;
  pointer-events: none;
}

.snapshot-chip.active .snapshot-chip-close {
  opacity: 1;
  pointer-events: auto;
}

.snapshot-chip-close:hover:not(:disabled) {
  border-color: #e0b4b4;
  background: #fff3f3;
  color: #a63b3b;
}

.request-raw {
  margin-top: 10px;
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
  grid-template-columns: 110px minmax(0, 1fr) 26px minmax(0, 1.2fr) minmax(180px, 0.8fr);
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

.line-inline {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.method-select {
  min-width: 0;
}

.request-all-status {
  margin-top: 8px;
  color: #59728a;
  font-size: 12px;
}

.table-pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.table-pager-info {
  color: #4c6680;
  font-size: 12px;
}

.table-pager-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pager-size-select {
  width: 82px;
  min-width: 82px;
  padding: 6px 8px;
}

.pager-sort-select {
  width: 180px;
  min-width: 180px;
  padding: 6px 8px;
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

.request-table td {
  vertical-align: top;
}

.request-table {
  width: 100%;
  table-layout: fixed;
}

.index-col {
  width: 48px;
  min-width: 48px;
  text-align: center;
}

.method-col {
  width: 90px;
}

.path-col {
  width: 220px;
  white-space: normal;
  word-break: break-all;
  overflow-wrap: anywhere;
}

.url-col {
  min-width: 320px;
  white-space: normal;
  word-break: break-all;
  overflow-wrap: anywhere;
}

.len-col {
  width: 90px;
}

.sort-toggle {
  border: 0;
  background: transparent;
  padding: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font: inherit;
  color: inherit;
  cursor: pointer;
}

.sort-toggle-mark {
  color: #5a7086;
  font-size: 12px;
}

.status-col {
  width: 90px;
}

.elapsed-col {
  width: 90px;
}

.action-col {
  width: 110px;
}

.btn-sm {
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 12px;
}

.response-row > td {
  background: #f8fbfe;
}

.response-wrap {
  border: 1px solid #dbe7f2;
  border-radius: 8px;
  background: #f9fbfd;
  padding: 10px;
  display: grid;
  gap: 10px;
}

.response-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.response-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.response-editor {
  display: grid;
  gap: 10px;
}

.editor-url-preview {
  display: block;
  min-width: 0;
  white-space: normal;
  overflow-wrap: anywhere;
}

.response-meta {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  color: #3a5670;
  font-size: 12px;
}

.response-meta > span {
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-all;
}

.response-meta-long {
  flex: 1 1 100%;
}

.response-section h5 {
  margin: 0 0 6px;
  font-size: 12px;
  color: #35536d;
}

.detail-loading {
  padding: 8px 10px;
}

.result-json {
  margin: 0;
  border: 1px solid #dbe6f1;
  border-radius: 10px;
  background: #f7fbff;
  padding: 10px;
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'JetBrains Mono', 'Cascadia Mono', Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 980px) {
  .raw-line-first,
  .raw-line-simple {
    grid-template-columns: 1fr;
  }

  .table-pager {
    flex-direction: column;
    align-items: flex-start;
  }

  .raw-line-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .response-toolbar {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
