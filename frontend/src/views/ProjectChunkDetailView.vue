<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import {
  createVueChunkJsDownload,
  createVueChunkJsDownloadLocal,
  createVueChunkRequestCapture,
  fetchVueChunkProjectDetail,
  locateVueChunkRequest,
  pauseVueChunkJob,
  resumeVueChunkJob,
  saveVueChunkManualRequests,
  stopVueChunkJob,
  updateVueChunkRouteRewrite,
  type ProjectDetailPayload,
  type RequestLocateResult,
  type SyncJob,
} from '../api/vueChunk'
import type { VueRequestInferResult } from '../api/vueRequest'
import ProjectBaseRequestTab from '../components/project/ProjectBaseRequestTab.vue'
import ProjectApiExtractTab from '../components/project/ProjectApiExtractTab.vue'
import ProjectApiRequestTab from '../components/project/ProjectApiRequestTab.vue'
import type { ProjectBaseRequestPresetEnvelope } from '../components/project/baseRequestTypes'

interface RequestRowItem {
  route_url: string
  method: string
  url: string
  count: number
  status: number
  resource_type: string
  content_type: string
  request_body: string
  source: 'captured' | 'manual'
}

interface JobActivityCard {
  title: string
  statusValue: string
  statusText: string
  phaseText: string
  progressPercent: number
  progressText: string
  compactMode: boolean
  currentLabel: string
  currentTarget: string
  recentItems: string[]
  logs: Array<{ time: string; message: string }>
}

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const creatingJsDownload = ref(false)
const creatingJsLocalDownload = ref(false)
const creatingRequestCapture = ref(false)
const applyingRouteRewrite = ref(false)
const pausingRequestCapture = ref(false)
const resumingRequestCapture = ref(false)
const stoppingRequestCapture = ref(false)
const savingManualRequests = ref(false)
const jsDownloadConcurrency = ref(24)
const requestCaptureConcurrency = ref(8)
const message = ref('')
const error = ref('')
const manualRequestUrl = ref('')
const manualRequestRows = ref<RequestRowItem[]>([])
const activeView = ref<'route' | 'js' | 'requestCapture' | 'requestMap' | 'analysis' | 'apiExtract' | 'baseRequest' | 'apiRequest'>('analysis')
const project = ref<ProjectDetailPayload['project'] | null>(null)
const detail = ref<ProjectDetailPayload['detail'] | null>(null)
const sync = ref<ProjectDetailPayload['sync'] | null>(null)
const jsDownload = ref<SyncJob | null>(null)
const requestCapture = ref<SyncJob | null>(null)
const requestReloadKey = ref(0)
const locatingRequestKey = ref('')
const locateResult = ref<RequestLocateResult | null>(null)
const locateResultRowKey = ref('')
const locateResultError = ref('')
const expandedMapRouteKey = ref('')
const apiRegJumpPreset = ref<{
  seq: number
  js_file: string
  line: number
  matched_path: string
  js_api_path: string
} | null>(null)
const apiRequestInferPreset = ref<{
  seq: number
  inferResult: VueRequestInferResult
} | null>(null)
const apiRequestBasePreset = ref<ProjectBaseRequestPresetEnvelope | null>(null)
const routePage = ref(1)
const routePageSize = ref(120)
const jsPage = ref(1)
const jsPageSize = ref(120)
const requestPage = ref(1)
const requestPageSize = ref(120)
const mapPage = ref(1)
const mapPageSize = ref(120)
const mapSearchInput = ref('')
const mapSearchKeyword = ref('')
const routeRewriteBasepath = ref('')
const routeRewriteStyle = ref<'slash' | 'plain'>('slash')
let pollTimer: number | undefined
let pollBusy = false

const domain = computed(() => String(route.params.domain || '').trim())

const routeRows = computed(() => {
  const rows = detail.value?.routes_preview
  if (!Array.isArray(rows)) return []
  return rows.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
})

const jsRows = computed(() => {
  const rows = detail.value?.js_preview
  if (!Array.isArray(rows)) return []
  return rows
    .map((item) => String(item || '').trim())
    .filter((item) => Boolean(item))
})
const chunkLocalCount = computed(() => Math.max(0, Number(detail.value?.downloaded_chunk_count || 0)))
const chunkTotalCount = computed(() => {
  const total = Math.max(0, Number(detail.value?.chunk_count || 0))
  if (total > 0) return total
  return jsRows.value.length
})
const chunkLocalSummary = computed(() => `${chunkLocalCount.value}/${chunkTotalCount.value}`)

const requestRows = computed<RequestRowItem[]>(() => {
  const rows = detail.value?.request_preview
  if (!Array.isArray(rows)) return []
  return rows.map((item) => ({
    route_url: String((item as Record<string, unknown>).route_url || '').trim(),
    method: String((item as Record<string, unknown>).method || 'GET').trim().toUpperCase(),
    url: normalizeApiUrl((item as Record<string, unknown>).url || ''),
    count: Number((item as Record<string, unknown>).count || 0),
    status: Number((item as Record<string, unknown>).status || 0),
    resource_type: String((item as Record<string, unknown>).resource_type || '').trim(),
    content_type: String((item as Record<string, unknown>).content_type || '').trim(),
    request_body: String((item as Record<string, unknown>).request_body || ''),
    source: 'captured' as const,
  }))
})

const mergedRequestRows = computed<RequestRowItem[]>(() => {
  const seen = new Set<string>()
  const merged = [...manualRequestRows.value, ...requestRows.value]
  return merged.filter((item) => {
    const key = requestRowKey(item)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})

const requestRouteMapRows = computed(() => {
  const rows = detail.value?.request_route_map_preview
  if (!Array.isArray(rows)) return []
  return rows.map((item) => ({
    route_url: String((item as Record<string, unknown>).route_url || '').trim(),
    chunk_count: Number((item as Record<string, unknown>).chunk_count || 0),
    request_count: Number((item as Record<string, unknown>).request_count || 0),
    unique_request_count: Number((item as Record<string, unknown>).unique_request_count || 0),
    chunks: Array.isArray((item as Record<string, unknown>).chunks)
      ? ((item as Record<string, unknown>).chunks as unknown[])
          .map((entry) => String(entry || '').trim())
          .filter((entry) => Boolean(entry))
      : [],
    requests: Array.isArray((item as Record<string, unknown>).requests)
      ? ((item as Record<string, unknown>).requests as unknown[])
          .filter((entry): entry is Record<string, unknown> => Boolean(entry && typeof entry === 'object'))
          .map((entry) => ({
            method: String(entry.method || 'GET').trim().toUpperCase(),
            url: normalizeApiUrl(entry.url || ''),
            count: Number(entry.count || 0),
            status: Number(entry.status || 0),
            resource_type: String(entry.resource_type || '').trim(),
            content_type: String(entry.content_type || '').trim(),
          }))
      : [],
  }))
})

const mapSearchRouteResults = computed(() => {
  const seen = new Set<string>()
  const rows: string[] = []
  for (const row of requestRouteMapRows.value) {
    const routeUrl = String(row.route_url || '').trim()
    if (!routeUrl || seen.has(routeUrl)) continue
    seen.add(routeUrl)
    rows.push(routeUrl)
  }
  return rows
})

const analysisLevel = computed(() => String(project.value?.request_value_level || '').trim().toLowerCase())
const analysisScore = computed(() => Math.max(0, Number(project.value?.request_value_score || 0)))
const analysisSnapshotCount = computed(() => Math.max(0, Number(project.value?.request_value_snapshot_count || 0)))
const analysisSampleCount = computed(() => Math.max(0, Number(project.value?.request_value_sample_count || 0)))

const analysisPriorityText = computed(() => {
  if (analysisLevel.value === 'high') return '高'
  if (analysisLevel.value === 'medium') return '中'
  if (analysisLevel.value === 'low') return '低'
  return '待分析'
})

const analysisReasonText = computed(() => {
  const rawReason = String(project.value?.request_value_reason || '').trim().toLowerCase()
  if (rawReason.includes('401') || rawReason.includes('403') || analysisLevel.value === 'low') {
    return '采样结果以前台未授权或拒绝访问响应为主。'
  }
  if (
    rawReason.includes('param') ||
    rawReason.includes('required') ||
    rawReason.includes('missing') ||
    rawReason.includes('account') ||
    rawReason.includes('order')
  ) {
    return '响应中出现了明显的缺参或参数校验信号。'
  }
  if (analysisLevel.value === 'high') {
    return '采样结果中出现了多条状态码 200 且响应较长的结果。'
  }
  if (analysisSnapshotCount.value > 0) {
    return '当前结果混合度较高，建议继续人工复核。'
  }
  return '当前还没有可用于分析的请求快照。'
})

const analysisSignals = computed(() => {
  const signals: string[] = []
  if (analysisScore.value > 0) {
    signals.push(`价值分数：${analysisScore.value}`)
  }
  if (analysisSnapshotCount.value > 0) {
    signals.push(`已分析快照数：${analysisSnapshotCount.value}`)
  }
  if (analysisSampleCount.value > 0) {
    signals.push(`采样请求数：${analysisSampleCount.value}`)
  }
  if (analysisLevel.value === 'high') {
    signals.push('优先查看大响应 200 包和缺参提示类结果。')
  } else if (analysisLevel.value === 'low') {
    signals.push('当前结果以鉴权失败响应为主。')
  } else if (analysisSnapshotCount.value > 0) {
    signals.push('当前结果较杂，仍然需要人工判断。')
  }
  return signals
})

const analysisNextAction = computed(() => {
  if (analysisLevel.value === 'high') {
    return '建议先查看靠前的高价值响应，再继续加强 BaseRequest。'
  }
  if (analysisLevel.value === 'low') {
    return '建议补充鉴权头、Cookie 或已登录态后重新自动化。'
  }
  if (analysisSnapshotCount.value > 0) {
    return '建议切到 ApiRequest，对比 GET 和 POST 两轮快照。'
  }
  return '建议至少先完成一轮自动请求，再观察分析结果。'
})

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return value as Record<string, unknown>
}

function shortAnalysisLine(value: unknown, max = 320) {
  const text = String(value || '').trim()
  if (!text) return ''
  if (text.length <= max) return text
  return `${text.slice(0, max)} ...`
}

const syncResult = computed<Record<string, unknown>>(() => asRecord(sync.value?.result))
const autoPipelineTarget = computed<Record<string, unknown>>(() => asRecord(syncResult.value.auto_pipeline_target))
const autoRegexResult = computed<Record<string, unknown>>(() => asRecord(syncResult.value.auto_regex))
const autoInferResult = computed<Record<string, unknown>>(() => asRecord(syncResult.value.infer_result))
const autoRequestResult = computed<Record<string, unknown>>(() => asRecord(syncResult.value.auto_request))
const autoGetSnapshot = computed<Record<string, unknown>>(() => asRecord(autoRequestResult.value.get_snapshot))
const autoPostSnapshot = computed<Record<string, unknown>>(() => asRecord(autoRequestResult.value.post_snapshot))
const autoGetSummary = computed<Record<string, unknown>>(() => asRecord(autoRequestResult.value.get_summary))
const autoPostSummary = computed<Record<string, unknown>>(() => asRecord(autoRequestResult.value.post_summary))
const autoRequestSelectedTotal = computed(() => Math.max(0, Number(autoRequestResult.value.selected_endpoint_total || 0)))
const autoRequestEndpointTotal = computed(() => Math.max(0, Number(autoRequestResult.value.endpoint_total || 0)))

const analysisAutomationItems = computed(() => {
  const locateSelected = Boolean(autoPipelineTarget.value.selected)
  const locateError = String(autoPipelineTarget.value.error || '').trim()
  const autoRegexPattern = String(autoRegexResult.value.selected_pattern || '').trim()
  const autoRegexError = String(autoRegexResult.value.error || '').trim()
  const inferEnabled = Boolean(autoInferResult.value.inferred)
  const inferError = String(autoInferResult.value.error || '').trim()
  const getSnapshotId = String(autoGetSnapshot.value.snapshot_id || '').trim()
  const postSnapshotId = String(autoPostSnapshot.value.snapshot_id || '').trim()

  return [
    {
      key: 'locate',
      title: '定位 JS',
      status: locateSelected ? 'ready' : locateError ? 'failed' : 'pending',
      statusText: locateSelected ? '已完成' : locateError ? '失败' : '待执行',
      summary: locateSelected
        ? `${String(autoPipelineTarget.value.keyword || '-')} | ${String(autoPipelineTarget.value.file_name || '-')}:${String(autoPipelineTarget.value.line || '-')}`
        : locateError || '当前还没有定位到可用的 js_api_path。',
      lines: [
        shortAnalysisLine(autoPipelineTarget.value.request_url),
        shortAnalysisLine(autoPipelineTarget.value.js_api_path),
      ].filter((item) => Boolean(item)),
    },
    {
      key: 'regex',
      title: '自动正则',
      status: autoRegexPattern ? 'ready' : autoRegexError ? 'failed' : 'pending',
      statusText: autoRegexPattern ? '已完成' : autoRegexError ? '失败' : '待执行',
      summary: autoRegexPattern
        ? `已生成 ${Number(autoRegexResult.value.candidate_count || 0)} 条候选正则`
        : autoRegexError || '当前还没有选中正则。',
      lines: [shortAnalysisLine(autoRegexPattern)].filter((item) => Boolean(item)),
    },
    {
      key: 'infer',
      title: '基址推断',
      status: inferEnabled ? 'ready' : inferError ? 'failed' : 'pending',
      statusText: inferEnabled ? '已完成' : inferError ? '失败' : '待执行',
      summary: inferEnabled
        ? `BaseURL ${String(autoInferResult.value.baseurl || '').trim() || '(空)'}`
        : inferError || '当前还没有完成 BaseURL / BaseAPI 推断。',
      lines: [
        `BaseAPI ${String(autoInferResult.value.baseapi || '').trim() || '(空)'}`,
        `接口数 ${Number(autoInferResult.value.endpoint_count || 0)}`,
      ],
    },
    {
      key: 'get',
      title: 'GET 快照',
      status: getSnapshotId ? 'ready' : 'pending',
      statusText: getSnapshotId ? '已完成' : '待执行',
      summary: getSnapshotId
        ? `${String(autoGetSnapshot.value.title || 'GET')} | 成功 ${Number(autoGetSummary.value.ok || 0)} 失败 ${Number(autoGetSummary.value.fail || 0)}`
        : 'GET 结果还没有保存。',
      lines: [
        autoRequestSelectedTotal.value > 0
          ? `已跑接口 ${autoRequestSelectedTotal.value}/${autoRequestEndpointTotal.value || autoRequestSelectedTotal.value}`
          : '',
        shortAnalysisLine(asRecord(autoGetSnapshot.value.request).base_query),
        String(autoGetSnapshot.value.snapshot_id || '').trim(),
      ].filter((item) => Boolean(item)),
    },
    {
      key: 'post',
      title: 'POST 快照',
      status: postSnapshotId ? 'ready' : 'pending',
      statusText: postSnapshotId ? '已完成' : '待执行',
      summary: postSnapshotId
        ? `${String(autoPostSnapshot.value.title || 'POST')} | 成功 ${Number(autoPostSummary.value.ok || 0)} 失败 ${Number(autoPostSummary.value.fail || 0)}`
        : 'POST 结果还没有保存。',
      lines: [
        autoRequestSelectedTotal.value > 0
          ? `已跑接口 ${autoRequestSelectedTotal.value}/${autoRequestEndpointTotal.value || autoRequestSelectedTotal.value}`
          : '',
        shortAnalysisLine(asRecord(autoPostSnapshot.value.request).body_text),
        String(autoPostSnapshot.value.snapshot_id || '').trim(),
      ].filter((item) => Boolean(item)),
    },
  ]
})

const hasAutomationStages = computed(() =>
  analysisAutomationItems.value.some((item) => item.status !== 'pending' || item.lines.length > 0),
)

const syncStatus = computed(() => String(sync.value?.status || 'idle').toLowerCase())
const jsDownloadStatus = computed(() => String(jsDownload.value?.status || 'idle').toLowerCase())
const requestCaptureStatus = computed(() => String(requestCapture.value?.status || 'idle').toLowerCase())

const hasRunningJobs = computed(() => {
  const runningValues = new Set(['running', 'queued'])
  return (
    runningValues.has(syncStatus.value) ||
    runningValues.has(jsDownloadStatus.value) ||
    runningValues.has(requestCaptureStatus.value)
  )
})

function isLiveJobStatus(status: string) {
  return ['queued', 'running', 'paused'].includes(String(status || '').toLowerCase())
}

function jobStatusText(status: string) {
  const token = String(status || '').toLowerCase()
  if (token === 'queued') return '已排队'
  if (token === 'running') return '运行中'
  if (token === 'paused') return '已暂停'
  if (token === 'done') return '已完成'
  if (token === 'failed') return '失败'
  if (token === 'stopped') return '已停止'
  return '空闲'
}

function jobPhaseText(job: SyncJob | null, kind: 'sync' | 'js' | 'capture') {
  const phase = String(job?.progress?.phase || '').trim().toLowerCase()
  if (kind === 'sync') {
    if (phase === 'sync_project') return '正在同步项目资源'
    if (phase === 'sync_completed') return '项目同步完成'
    if (phase === 'queue_request_capture') return '正在创建请求捕获任务'
    if (phase === 'waiting_request_capture') return '正在等待路由请求捕获'
    if (phase === 'locate_js') return '正在定位可用 js_api_path'
    if (phase === 'extracting') return '正在提取 API'
    if (phase === 'auto_regex') return '正在推断 API 正则'
    if (phase === 'infer_base') return '正在推断 BaseURL / BaseAPI'
    if (phase === 'auto_request') return '正在执行 GET / POST 自动请求'
    if (phase === 'auto_pipeline_done') return '自动流程完成'
    if (phase === 'finalize') return '正在收尾'
    if (phase === 'completed') return '已完成'
    if (phase === 'stopped') return '已停止'
    return '项目同步中'
  }
  if (kind === 'js') {
    if (String(job?.mode || '').toLowerCase() === 'local') return '正在下载到本地'
    return '正在下载 Chunk'
  }
  if (phase === 'probing') return '正在探测路由样式'
  if (phase === 'capturing') return '正在捕获路由资源'
  if (phase === 'stopped') return '已停止'
  return '正在捕获路由请求'
}

function jobProgressPercent(job: SyncJob | null) {
  const done = Number(job?.progress?.done || 0)
  const total = Number(job?.progress?.total || 0)
  if (total <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((done / total) * 100)))
}

function jobProgressText(job: SyncJob | null, kind: 'sync' | 'js' | 'capture') {
  const progress = job?.progress || {}
  if (kind === 'capture') {
    return `已访问 ${Number(progress.visited_route_count || 0)}/${Number(progress.total || 0)} 路由 · API ${Number(progress.request_total || 0)} · 失败 ${Number(progress.failed_route_count || 0)}`
  }
  if (kind === 'js') {
    return `下载进度 ${Number(progress.done || 0)}/${Number(progress.total || 0)}`
  }
  return `当前阶段 ${jobPhaseText(job, 'sync')}`
}

function normalizeRecentItems(values: unknown, limit = 4) {
  if (!Array.isArray(values)) return []
  return values
    .map((item) => String(item || '').trim())
    .filter((item) => Boolean(item))
    .slice(-Math.max(1, limit))
}

function normalizeJobLogs(job: SyncJob | null, limit = 6) {
  if (!Array.isArray(job?.logs)) return []
  return job.logs
    .map((item) => ({
      time: String(item?.time || '').trim(),
      message: String(item?.message || '').trim(),
    }))
    .filter((item) => item.message)
    .slice(-Math.max(1, limit))
}

function shortLogTime(value: string) {
  const text = String(value || '').trim()
  if (!text) return ''
  const match = text.match(/T(\d{2}:\d{2}:\d{2})/)
  return match?.[1] || text
}

function buildJobActivityCard(
  job: SyncJob | null,
  kind: 'sync' | 'js' | 'capture',
  title: string,
): JobActivityCard | null {
  if (!job) return null
  const statusValue = String(job.status || 'idle').toLowerCase()
  if (!isLiveJobStatus(statusValue)) return null

  let currentLabel = ''
  let currentTarget = ''
  let recentItems: string[] = []

  if (kind === 'capture') {
    currentLabel = '当前路由'
    currentTarget = String(job.current_route_url || '').trim()
    recentItems = [
      ...normalizeRecentItems(job.recent_chunks).map((item) => `JS ${item}`),
      ...normalizeRecentItems(job.recent_requests).map((item) => `API ${item}`),
    ]
  } else if (kind === 'js') {
    currentLabel = '当前 JS'
    currentTarget = String(job.current_js_url || '').trim()
    recentItems = normalizeRecentItems(job.recent_js_urls)
  } else {
    currentLabel = '当前目标'
    currentTarget = String(job.target_url || '').trim()
  }

  return {
    title,
    statusValue,
    statusText: jobStatusText(statusValue),
    phaseText: jobPhaseText(job, kind),
    progressPercent: jobProgressPercent(job),
    progressText: jobProgressText(job, kind),
    compactMode: kind === 'js' && String(job.mode || '').toLowerCase() === 'local',
    currentLabel,
    currentTarget,
    recentItems,
    logs: normalizeJobLogs(job),
  }
}

const liveJobCard = computed<JobActivityCard | null>(() => {
  return (
    buildJobActivityCard(requestCapture.value, 'capture', '路由请求捕获') ||
    buildJobActivityCard(sync.value, 'sync', '项目同步') ||
    buildJobActivityCard(jsDownload.value, 'js', 'Chunk 下载')
  )
})

function resolveError(err: unknown) {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: string } | undefined
    return data?.error || err.message || 'request failed'
  }
  if (err instanceof Error) return err.message
  return 'unknown error'
}

function routeName(item: Record<string, unknown>) {
  const value = item.name ?? item.route ?? ''
  return String(value || '-')
}

function routePath(item: Record<string, unknown>) {
  const value = item.path ?? item.route ?? ''
  return String(value || '-')
}

function routeUrl(item: Record<string, unknown>) {
  const value = item.route_url ?? item.url ?? ''
  return String(value || '')
}

function normalizeApiUrl(value: unknown) {
  const text = String(value || '').trim()
  if (!text) return ''
  const noHash = text.split('#')[0] || text
  try {
    const parsed = new URL(noHash)
    return `${parsed.origin}${parsed.pathname || ''}`.trim()
  } catch {
    return (noHash.split('?')[0] || noHash).trim()
  }
}

function requestRowKey(item: { method?: string; url?: string; route_url?: string }) {
  return normalizeApiUrl(item?.url)
}

function normalizeManualRequestRows(rows: unknown[]): RequestRowItem[] {
  if (!Array.isArray(rows)) return []
  const seen = new Set<string>()
  const result: RequestRowItem[] = []
  rows.forEach((item) => {
    if (!item || typeof item !== 'object') return
    const row = item as Record<string, unknown>
    const normalized: RequestRowItem = {
      route_url: String(row.route_url || '').trim(),
      method: String(row.method || 'GET').trim().toUpperCase() || 'GET',
      url: normalizeApiUrl(row.url || ''),
      count: Number(row.count || 1) || 1,
      status: Number(row.status || 0) || 0,
      resource_type: String(row.resource_type || 'manual').trim() || 'manual',
      content_type: String(row.content_type || '').trim(),
      request_body: String(row.request_body || ''),
      source: 'manual',
    }
    if (!normalized.url) return
    const key = requestRowKey(normalized)
    if (seen.has(key)) return
    seen.add(key)
    result.push(normalized)
  })
  return result
}

async function persistManualRequests(nextRows: RequestRowItem[], successMessage: string) {
  const token = domain.value
  if (!token) return
  savingManualRequests.value = true
  try {
    const payload = await saveVueChunkManualRequests(token, {
      requests: nextRows.map((item) => ({
        route_url: String(item.route_url || '').trim(),
        method: String(item.method || 'GET').trim().toUpperCase() || 'GET',
        url: normalizeApiUrl(item.url || ''),
        count: Number(item.count || 1) || 1,
        status: Number(item.status || 0) || 0,
        resource_type: String(item.resource_type || 'manual').trim() || 'manual',
        content_type: String(item.content_type || '').trim(),
        request_body: String(item.request_body || ''),
      })),
    })
    manualRequestRows.value = normalizeManualRequestRows(payload.manualRequests || [])
    error.value = ''
    message.value = successMessage
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    savingManualRequests.value = false
  }
}

async function onAddManualRequestApi() {
  const url = normalizeApiUrl(manualRequestUrl.value || '')
  if (!url) {
    error.value = '请输入 API URL'
    return
  }
  const candidate: RequestRowItem = {
    route_url: '',
    method: 'GET',
    url,
    count: 1,
    status: 0,
    resource_type: 'manual',
    content_type: '',
    request_body: '',
    source: 'manual',
  }
  const exists = manualRequestRows.value.some((item) => requestRowKey(item) === requestRowKey(candidate))
  if (exists) {
    message.value = '该 API 已存在'
    manualRequestUrl.value = ''
    return
  }
  const nextRows = [candidate, ...manualRequestRows.value]
  await persistManualRequests(nextRows, `已添加 API: ${url}`)
  if (!error.value) {
    manualRequestUrl.value = ''
  }
}

async function onRemoveManualRequestApi(item: RequestRowItem) {
  const targetKey = requestRowKey(item)
  const next = manualRequestRows.value.filter((row) => requestRowKey(row) !== targetKey)
  await persistManualRequests(next, '已删除手动 API')
  if (locateResultRowKey.value === targetKey) {
    locateResultRowKey.value = ''
    locateResult.value = null
    locateResultError.value = ''
  }
}

function mapRowKey(index: number, routeUrl: string) {
  return `${index}:${String(routeUrl || '').trim()}`
}

function isMapRowExpanded(index: number, routeUrl: string) {
  return expandedMapRouteKey.value === mapRowKey(index, routeUrl)
}

function toggleMapRow(index: number, routeUrl: string) {
  const key = mapRowKey(index, routeUrl)
  expandedMapRouteKey.value = expandedMapRouteKey.value === key ? '' : key
}

function onPickMapSearchResult(routeUrl: string) {
  const target = String(routeUrl || '').trim()
  if (!target) return
  const index = requestRouteMapRows.value.findIndex((row) => String(row.route_url || '').trim() === target)
  if (index < 0) return
  expandedMapRouteKey.value = mapRowKey(index, target)
}

function shortLocateFileName(fileName: string) {
  const value = String(fileName || '').trim()
  if (!value) return '-'
  const splitIndex = value.indexOf('_')
  if (splitIndex > 0) {
    const prefix = value.slice(0, splitIndex)
    if (/^[a-f0-9]{6,}$/i.test(prefix)) {
      return value.slice(splitIndex + 1) || value
    }
  }
  return value
}

function onSendToApiReg(hit: {
  file_name?: string
  line?: number
  matched_path?: string
  snippet?: string
}) {
  const jsFile = String(hit?.file_name || '').trim()
  if (!jsFile) return
  apiRegJumpPreset.value = {
    seq: Date.now(),
    js_file: jsFile,
    line: Number(hit?.line || 0),
    matched_path: String(hit?.matched_path || '').trim(),
    js_api_path: String(hit?.snippet || '').trim(),
  }
  activeView.value = 'apiExtract'
}

async function onLocateRequest(item: RequestRowItem) {
  const token = domain.value
  const requestUrl = String(item?.url || '').trim()
  if (!token || !requestUrl) return
  const key = requestRowKey(item)
  const isManual = item.source === 'manual' || String(item.resource_type || '').toLowerCase() === 'manual'
  locatingRequestKey.value = key
  locateResultRowKey.value = key
  locateResult.value = null
  locateResultError.value = ''
  message.value = ''
  error.value = ''
  try {
    const payload = await locateVueChunkRequest(token, {
      requestUrl,
      method: String(item?.method || 'GET').trim().toUpperCase() || 'GET',
      routeUrl: String(item?.route_url || '').trim(),
      scanScope: isManual ? 'global' : 'auto',
      maxFiles: 240,
      maxResults: 80,
    })
    locateResult.value = payload.result || null
    message.value = `Locate finished: ${locateResult.value?.hit_total || 0} hit(s)`
  } catch (err) {
    locateResult.value = null
    locateResultError.value = resolveError(err)
    error.value = locateResultError.value
  } finally {
    locatingRequestKey.value = ''
  }
}

function onApiExtracted() {
  requestReloadKey.value += 1
  message.value = 'API list refreshed in API Request'
}

function buildBaseRequestDraftFromInfer(result: VueRequestInferResult): ProjectBaseRequestPresetEnvelope {
  const previous = apiRequestBasePreset.value?.preset
  return {
    seq: Date.now(),
    preset: {
      baseurl: String(result.baseurl || '').trim(),
      baseapi: String(result.baseapi || '').trim(),
      baseQuery: String(previous?.baseQuery || '').trim(),
      baseBody: String(previous?.baseBody || '').trim(),
      baseBodyType: previous?.baseBodyType === 'form' ? 'form' : 'json',
      baseHeaders: String(previous?.baseHeaders || '').trim(),
      requestMethod: previous?.requestMethod === 'POST' ? 'POST' : 'GET',
      fuzzParams: Array.isArray(previous?.fuzzParams) ? previous!.fuzzParams : [],
    },
  }
}

function onApiBaseReady(result: VueRequestInferResult) {
  const seq = Date.now()
  apiRequestInferPreset.value = {
    seq,
    inferResult: result,
  }
  apiRequestBasePreset.value = buildBaseRequestDraftFromInfer(result)
  activeView.value = 'baseRequest'
  message.value = `已查询 BaseURL / BaseAPI，并发送到 BaseRequest / ApiRequest：query_baseurl=${result.baseurl || '-'} query_baseapi=${result.baseapi || '(empty)'}`
}

function onBaseRequestReady(payload: ProjectBaseRequestPresetEnvelope) {
  apiRequestBasePreset.value = payload
  activeView.value = 'apiRequest'
  message.value = 'BaseRequest 已发送到 ApiRequest'
}

async function loadDetail(options?: { silent?: boolean }) {
  const token = domain.value
  if (!token) return
  const silent = Boolean(options?.silent)
  if (!silent) {
    loading.value = true
    error.value = ''
  }
  try {
    const payload = await fetchVueChunkProjectDetail(token, {
      routePage: routePage.value,
      routePageSize: routePageSize.value,
      jsPage: jsPage.value,
      jsPageSize: jsPageSize.value,
      requestPage: requestPage.value,
      requestPageSize: requestPageSize.value,
        mapPage: mapPage.value,
        mapPageSize: mapPageSize.value,
        mapQ: mapSearchKeyword.value,
      })
    project.value = payload.project
    detail.value = payload.detail
    manualRequestRows.value = normalizeManualRequestRows(payload.detail?.manual_request_preview || [])
    sync.value = payload.sync
    jsDownload.value = payload.jsDownload
    requestCapture.value = payload.requestCapture
    routeRewriteBasepath.value = String(payload.detail?.route_url_profile?.basepath_override || '')
    routeRewriteStyle.value =
      String(payload.detail?.route_url_profile?.hash_style || 'slash').toLowerCase() === 'plain'
        ? 'plain'
        : 'slash'
    routePage.value = Number(detail.value?.routes_pagination?.page || routePage.value || 1)
    jsPage.value = Number(detail.value?.js_pagination?.page || jsPage.value || 1)
    requestPage.value = Number(detail.value?.request_pagination?.page || requestPage.value || 1)
    mapPage.value = Number(detail.value?.request_route_map_pagination?.page || mapPage.value || 1)
  } catch (err) {
    if (!silent) {
      error.value = resolveError(err)
    }
  } finally {
    if (!silent) {
      loading.value = false
    }
  }
}

async function onRoutePrevPage() {
  if (!detail.value?.routes_pagination) return
  if (routePage.value <= 1 || loading.value) return
  routePage.value -= 1
  await loadDetail()
}

async function onRouteNextPage() {
  const totalPages = Number(detail.value?.routes_pagination?.total_pages || 0)
  if (totalPages <= 0 || loading.value || routePage.value >= totalPages) return
  routePage.value += 1
  await loadDetail()
}

async function onJsPrevPage() {
  if (!detail.value?.js_pagination) return
  if (jsPage.value <= 1 || loading.value) return
  jsPage.value -= 1
  await loadDetail()
}

async function onJsNextPage() {
  const totalPages = Number(detail.value?.js_pagination?.total_pages || 0)
  if (totalPages <= 0 || loading.value || jsPage.value >= totalPages) return
  jsPage.value += 1
  await loadDetail()
}

async function onRequestPrevPage() {
  if (!detail.value?.request_pagination) return
  if (requestPage.value <= 1 || loading.value) return
  requestPage.value -= 1
  await loadDetail()
}

async function onRequestNextPage() {
  const totalPages = Number(detail.value?.request_pagination?.total_pages || 0)
  if (totalPages <= 0 || loading.value || requestPage.value >= totalPages) return
  requestPage.value += 1
  await loadDetail()
}

async function onMapPrevPage() {
  if (!detail.value?.request_route_map_pagination) return
  if (mapPage.value <= 1 || loading.value) return
  mapPage.value -= 1
  await loadDetail()
}

async function onMapNextPage() {
  const totalPages = Number(detail.value?.request_route_map_pagination?.total_pages || 0)
  if (totalPages <= 0 || loading.value || mapPage.value >= totalPages) return
  mapPage.value += 1
  await loadDetail()
}

async function onSearchMap() {
  mapSearchKeyword.value = mapSearchInput.value.trim()
  mapPage.value = 1
  expandedMapRouteKey.value = ''
  await loadDetail()
}

async function onResetMapSearch() {
  mapSearchInput.value = ''
  mapSearchKeyword.value = ''
  mapPage.value = 1
  expandedMapRouteKey.value = ''
  await loadDetail()
}

async function onCreateJsDownload() {
  const token = domain.value
  if (!token) return
  creatingJsDownload.value = true
  message.value = ''
  error.value = ''
  try {
    await createVueChunkJsDownload(token, {
      concurrency: Math.max(1, Number(jsDownloadConcurrency.value || 24)),
    })
    message.value = 'JS download task queued'
    await loadDetail()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    creatingJsDownload.value = false
  }
}

async function onCreateJsDownloadLocal() {
  const token = domain.value
  if (!token) return
  creatingJsLocalDownload.value = true
  message.value = ''
  error.value = ''
  try {
    await createVueChunkJsDownloadLocal(token, {
      concurrency: Math.max(1, Number(jsDownloadConcurrency.value || 24)),
    })
    message.value = '本地下载任务已创建'
    await loadDetail()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    creatingJsLocalDownload.value = false
  }
}

async function onCreateRequestCapture() {
  const token = domain.value
  if (!token) return
  creatingRequestCapture.value = true
  message.value = ''
  error.value = ''
  try {
    await createVueChunkRequestCapture(token, {
      concurrency: Math.max(1, Number(requestCaptureConcurrency.value || 8)),
    })
    message.value = 'Route request capture task queued'
    await loadDetail()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    creatingRequestCapture.value = false
  }
}

async function onApplyRouteRewrite() {
  const token = domain.value
  if (!token) return
  applyingRouteRewrite.value = true
  message.value = ''
  error.value = ''
  try {
    await updateVueChunkRouteRewrite(token, {
      hashStyle: routeRewriteStyle.value,
      basepathOverride: String(routeRewriteBasepath.value || '').trim(),
      manualLock: true,
    })
    message.value = 'Route basepath replacement applied'
    await loadDetail()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    applyingRouteRewrite.value = false
  }
}

async function onStopRequestCapture() {
  const jobId = String(requestCapture.value?.job_id || '').trim()
  if (!jobId) return
  stoppingRequestCapture.value = true
  message.value = ''
  error.value = ''
  try {
    await stopVueChunkJob(jobId)
    message.value = 'Stop requested for request capture task'
    await loadDetail()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    stoppingRequestCapture.value = false
  }
}

async function onPauseRequestCapture() {
  const jobId = String(requestCapture.value?.job_id || '').trim()
  if (!jobId) return
  pausingRequestCapture.value = true
  message.value = ''
  error.value = ''
  try {
    await pauseVueChunkJob(jobId)
    message.value = 'Pause requested for request capture task'
    await loadDetail()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    pausingRequestCapture.value = false
  }
}

async function onResumeRequestCapture() {
  const jobId = String(requestCapture.value?.job_id || '').trim()
  if (!jobId) return
  resumingRequestCapture.value = true
  message.value = ''
  error.value = ''
  try {
    await resumeVueChunkJob(jobId)
    message.value = 'Request capture task resumed'
    await loadDetail()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    resumingRequestCapture.value = false
  }
}

function ensurePolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
  pollTimer = window.setInterval(async () => {
    if (!hasRunningJobs.value || loading.value || pollBusy) return
    pollBusy = true
    try {
      await loadDetail({ silent: true })
    } finally {
      pollBusy = false
    }
  }, 3000)
}

watch(
  () => requestRouteMapRows.value.map((row, index) => mapRowKey(index, row.route_url)).join('|'),
  () => {
    const keys = requestRouteMapRows.value.map((row, index) => mapRowKey(index, row.route_url))
    if (!keys.length) {
      expandedMapRouteKey.value = ''
      return
    }
    if (!keys.includes(expandedMapRouteKey.value)) {
      expandedMapRouteKey.value = keys[0] || ''
    }
  },
)

watch(
  () => domain.value,
  async () => {
    routePage.value = 1
    jsPage.value = 1
    requestPage.value = 1
    mapPage.value = 1
    manualRequestRows.value = []
    manualRequestUrl.value = ''
    locateResult.value = null
      locateResultRowKey.value = ''
      locateResultError.value = ''
      expandedMapRouteKey.value = ''
      mapSearchInput.value = ''
      mapSearchKeyword.value = ''
      apiRequestInferPreset.value = null
    apiRequestBasePreset.value = null
    await loadDetail()
  },
)

onMounted(async () => {
  await loadDetail()
  ensurePolling()
})

onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<template>
  <section class="page">
    <div v-if="message" class="notice success">{{ message }}</div>
    <div v-if="error" class="notice error">{{ error }}</div>

    <section class="panel">
      <div v-if="loading" class="empty">Loading...</div>
      <div v-else-if="detail" class="detail-wrap">
        <div class="project-toolbar">
          <div class="toolbar-tabs">
            <a href="#" class="nav-tab" :class="{ active: activeView === 'requestCapture' }" @click.prevent="activeView = 'requestCapture'">
              <span>API</span>
              <span class="tab-count">{{ detail.request_summary?.request_total || 0 }}</span>
            </a>
            <a href="#" class="nav-tab" :class="{ active: activeView === 'apiExtract' }" @click.prevent="activeView = 'apiExtract'">
              <span>API Reg</span>
            </a>
            <a href="#" class="nav-tab" :class="{ active: activeView === 'baseRequest' }" @click.prevent="activeView = 'baseRequest'">
              <span>BaseRequest</span>
            </a>
            <a href="#" class="nav-tab" :class="{ active: activeView === 'apiRequest' }" @click.prevent="activeView = 'apiRequest'">
              <span>ApiRequest</span>
            </a>
            <a href="#" class="nav-tab" :class="{ active: activeView === 'route' }" @click.prevent="activeView = 'route'">
              <span>Route</span>
              <span class="tab-count">{{ detail.route_count }}</span>
            </a>

            <a href="#" class="nav-tab" :class="{ active: activeView === 'js' }" @click.prevent="activeView = 'js'">
              <span>Chunk</span>
              <span class="tab-count">{{ detail.chunk_count }}</span>
            </a>

            <a href="#" class="nav-tab" :class="{ active: activeView === 'requestMap' }" @click.prevent="activeView = 'requestMap'">
              <span>Map</span>
              <span class="tab-count">{{ detail.request_route_map_total || 0 }}</span>
            </a>
            <a href="#" class="nav-tab" :class="{ active: activeView === 'analysis' }" @click.prevent="activeView = 'analysis'">
              <span>Analysis</span>
            </a>
          </div>

          <div class="toolbar-right-meta">
            <h3 class="domain-title mono">{{ project?.domain || domain || '-' }}</h3>
            <a href="#" class="back-link" @click.prevent="router.push('/vueChunk')">返回列表</a>
          </div>
        </div>
        <section v-if="liveJobCard" class="job-live-card">
          <div class="job-live-head">
            <div class="job-live-title-wrap">
              <strong class="job-live-title">{{ liveJobCard.title }}</strong>
              <span class="job-live-status">{{ liveJobCard.statusText }} · {{ liveJobCard.phaseText }}</span>
            </div>
            <span class="job-live-progress mono">{{ liveJobCard.progressText }}</span>
          </div>
          <div class="progress-wrap">
            <div class="progress-track">
              <div class="progress-fill" :style="{ width: `${liveJobCard.progressPercent}%` }" />
            </div>
            <div class="progress-text">{{ liveJobCard.progressPercent }}%</div>
          </div>
          <div v-if="!liveJobCard.compactMode && liveJobCard.currentTarget" class="job-live-current">
            <span class="job-live-label">{{ liveJobCard.currentLabel }}</span>
            <span class="mono">{{ liveJobCard.currentTarget }}</span>
          </div>
          <div v-if="!liveJobCard.compactMode && liveJobCard.recentItems.length" class="job-live-recent">
            <span class="job-live-label">最近捕获</span>
            <div class="job-live-recent-list">
              <span v-for="(item, index) in liveJobCard.recentItems" :key="`live-item-${index}`" class="job-live-chip mono">
                {{ item }}
              </span>
            </div>
          </div>
          <div v-if="!liveJobCard.compactMode && liveJobCard.logs.length" class="job-live-logs">
            <div v-for="(item, index) in liveJobCard.logs" :key="`live-log-${index}`" class="job-live-log-row">
              <span class="job-live-log-time mono">{{ shortLogTime(item.time) }}</span>
              <span class="job-live-log-message">{{ item.message }}</span>
            </div>
          </div>
        </section>
        <pre v-if="sync?.error" class="job-error">{{ sync.error }}</pre>
      </div>
      <div v-else class="empty">Project not found</div>
    </section>

    <section class="panel">
      <template v-if="activeView === 'route'">
        <div class="view-toolbar">
          <h4>Route Preview</h4>
          <div class="view-toolbar-right">
            <div class="route-rewrite-bar">
              <label>BasePath</label>
              <input v-model="routeRewriteBasepath" type="text" placeholder="/ocps/pc-web" />
              <select v-model="routeRewriteStyle">
                <option value="slash">/#/</option>
                <option value="plain">#/</option>
              </select>
              <button class="ghost" :disabled="applyingRouteRewrite || loading" @click="onApplyRouteRewrite">
                {{ applyingRouteRewrite ? '应用中...' : '应用替换' }}
              </button>
            </div>
            <div v-if="detail?.routes_pagination?.total_pages" class="pager-inline">
              <div class="pager-inline-text">
                Total {{ detail.routes_pagination.total }} | Page {{ detail.routes_pagination.page }} / {{ detail.routes_pagination.total_pages }}
              </div>
              <div class="pager-inline-actions">
                <button class="ghost" :disabled="loading || detail.routes_pagination.page <= 1" @click="onRoutePrevPage">
                  上一页
                </button>
                <button
                  class="ghost"
                  :disabled="loading || detail.routes_pagination.page >= detail.routes_pagination.total_pages"
                  @click="onRouteNextPage"
                >
                  下一页
                </button>
              </div>
            </div>
          </div>
        </div>
        <table v-if="routeRows.length > 0" class="task-table preview-table">
          <thead>
            <tr>
              <th class="index-col">#</th>
              <th>Name</th>
              <th>Path</th>
              <th>URL</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in routeRows" :key="`${domain}-route-${index}`">
              <td class="index-col">{{ index + 1 }}</td>
              <td>{{ routeName(item) }}</td>
              <td class="mono">{{ routePath(item) }}</td>
              <td>
                <a v-if="routeUrl(item)" :href="routeUrl(item)" target="_blank" rel="noreferrer" class="mono">
                  {{ routeUrl(item) }}
                </a>
                <span v-else>-</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">No route preview</div>
      </template>

      <template v-else-if="activeView === 'js'">
        <div class="view-toolbar">
          <h4>Chunk Preview <span class="chunk-count-inline mono">{{ chunkLocalSummary }}</span></h4>
          <div class="view-toolbar-right">
            <div class="js-download-bar">
              <label>JS 下载并发</label>
              <input v-model.number="jsDownloadConcurrency" type="number" min="1" />
              <button
                class="ghost"
                :disabled="creatingJsLocalDownload || jsRows.length <= 0"
                @click="onCreateJsDownloadLocal"
              >
                {{ creatingJsLocalDownload ? '创建中...' : '下载到本地' }}
              </button>
              <button
                class="ghost"
                :disabled="creatingJsDownload || jsRows.length <= 0"
                @click="onCreateJsDownload"
              >
                {{ creatingJsDownload ? '创建中...' : '创建 JS 下载任务' }}
              </button>
              <a
                v-if="jsDownload?.status === 'done' && jsDownload.download_url"
                :href="jsDownload.download_url"
                class="btn-link-inline"
              >
                下载 ZIP
              </a>
            </div>
            <div v-if="detail?.js_pagination?.total_pages" class="pager-inline">
              <div class="pager-inline-text">
                Total {{ detail.js_pagination.total }} | Page {{ detail.js_pagination.page }} / {{ detail.js_pagination.total_pages }}
              </div>
              <div class="pager-inline-actions">
                <button class="ghost" :disabled="loading || detail.js_pagination.page <= 1" @click="onJsPrevPage">
                  上一页
                </button>
                <button
                  class="ghost"
                  :disabled="loading || detail.js_pagination.page >= detail.js_pagination.total_pages"
                  @click="onJsNextPage"
                >
                  下一页
                </button>
              </div>
            </div>
          </div>
        </div>
        <pre v-if="jsDownload?.error" class="job-error">{{ jsDownload.error }}</pre>
        <div
          v-if="jsDownload?.mode === 'local' && jsDownload?.status === 'done'"
          class="empty"
          style="margin-bottom: 10px;"
        >
          本地下载完成：{{ chunkLocalSummary }}
        </div>
        <table v-if="jsRows.length > 0" class="task-table preview-table">
          <thead>
            <tr>
              <th class="index-col">#</th>
              <th>Chunk URL</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(js, index) in jsRows" :key="`${domain}-js-${index}`">
              <td class="index-col">{{ index + 1 }}</td>
              <td class="mono">{{ js }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">No captured JS yet</div>
      </template>

      <template v-else-if="activeView === 'requestCapture'">
        <div class="view-toolbar">
          <h4>Request Preview</h4>
          <div class="view-toolbar-right">
            <div class="js-download-bar">
              <input
                v-model="manualRequestUrl"
                class="manual-api-url"
                type="text"
                :disabled="savingManualRequests"
                placeholder="Manual API URL, e.g. http://api.com/baseapi/secapi/user/login"
                @keyup.enter="onAddManualRequestApi"
              />
              <button class="ghost" :disabled="savingManualRequests || !manualRequestUrl.trim()" @click="onAddManualRequestApi">
                {{ savingManualRequests ? '保存中...' : '添加 API' }}
              </button>
              <button
                class="ghost"
                :disabled="creatingRequestCapture || loading || requestCaptureStatus === 'running' || requestCaptureStatus === 'queued'"
                @click="onCreateRequestCapture"
              >
                {{ creatingRequestCapture ? '创建中...' : '捕获路由请求' }}
              </button>
              <button
                v-if="requestCapture?.job_id && requestCaptureStatus === 'running'"
                class="ghost"
                :disabled="pausingRequestCapture"
                @click="onPauseRequestCapture"
              >
                {{ pausingRequestCapture ? 'Pausing...' : 'Pause' }}
              </button>
              <button
                v-if="requestCapture?.job_id && requestCaptureStatus === 'paused'"
                class="ghost"
                :disabled="resumingRequestCapture"
                @click="onResumeRequestCapture"
              >
                {{ resumingRequestCapture ? 'Resuming...' : 'Resume' }}
              </button>
              <button
                v-if="requestCapture?.job_id && (requestCaptureStatus === 'running' || requestCaptureStatus === 'queued' || requestCaptureStatus === 'paused')"
                class="ghost danger"
                :disabled="stoppingRequestCapture"
                @click="onStopRequestCapture"
              >
                {{ stoppingRequestCapture ? 'Stopping...' : 'Stop Capture' }}
              </button>
            </div>
            <div v-if="detail?.request_pagination?.total_pages" class="pager-inline">
              <div class="pager-inline-text">
                Total {{ detail.request_pagination.total }} | Page {{ detail.request_pagination.page }} / {{ detail.request_pagination.total_pages }}
              </div>
              <div class="pager-inline-actions">
                <button class="ghost" :disabled="loading || detail.request_pagination.page <= 1" @click="onRequestPrevPage">
                  上一页
                </button>
                <button
                  class="ghost"
                  :disabled="loading || detail.request_pagination.page >= detail.request_pagination.total_pages"
                  @click="onRequestNextPage"
                >
                  下一页
                </button>
              </div>
            </div>
          </div>
        </div>
        <pre v-if="requestCapture?.error" class="job-error">{{ requestCapture.error }}</pre>
        <table v-if="mergedRequestRows.length > 0" class="task-table preview-table">
          <thead>
            <tr>
              <th class="index-col">#</th>
              <th>Method</th>
              <th>Request URL</th>
              <th>Count</th>
              <th>Status</th>
              <th>Type</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(item, index) in mergedRequestRows" :key="`${domain}-request-${requestRowKey(item)}-${index}`">
              <tr>
                <td class="index-col">{{ index + 1 }}</td>
                <td>{{ item.method || '-' }}</td>
                <td class="mono">{{ item.url || '-' }}</td>
                <td>{{ item.count || 0 }}</td>
                <td>{{ item.status || '-' }}</td>
                <td>{{ item.resource_type || '-' }}</td>
                <td class="actions-cell">
                  <button
                    class="ghost btn-sm"
                    :disabled="!item.url || locatingRequestKey === requestRowKey(item)"
                    @click.stop="onLocateRequest(item)"
                  >
                    {{ locatingRequestKey === requestRowKey(item) ? 'Locating...' : 'Locate JS' }}
                  </button>
                  <button
                    v-if="item.source === 'manual'"
                    class="ghost btn-sm"
                    :disabled="savingManualRequests"
                    @click.stop="onRemoveManualRequestApi(item)"
                  >
                    {{ savingManualRequests ? '保存中...' : '删除' }}
                  </button>
                </td>
              </tr>
              <tr
                v-if="locateResultRowKey === requestRowKey(item) && (locateResult || locateResultError)"
                :key="`${domain}-request-locate-${index}`"
                class="request-locate-row"
              >
                <td colspan="7" class="locate-inline-cell">
                  <div v-if="locateResultError" class="locate-inline-error">
                    {{ locateResultError }}
                  </div>
                  <div v-else-if="locateResult" class="locate-inline-wrap">
                    <div class="locate-inline-head">
                      <strong>Locate Result</strong>
                      <span class="mono">
                        {{ locateResult.hit_total }} hit(s) | {{ locateResult.scanned_file_total }}/{{ locateResult.candidate_file_total }} files
                      </span>
                    </div>
                    <div v-if="locateResult.path_candidates?.length" class="locate-candidates mono">
                      Candidates:
                      <span v-for="(candidate, idx) in locateResult.path_candidates" :key="`candidate-inline-${idx}`">{{ candidate }}</span>
                    </div>
                    <table v-if="locateResult.hits?.length" class="task-table preview-table locate-inline-table">
                      <thead>
                        <tr>
                          <th class="index-col locate-col-index">#</th>
                          <th class="locate-col-file">JS File</th>
                          <th class="locate-col-path">Matched Path</th>
                          <th class="locate-col-line">Line</th>
                          <th class="locate-col-snippet">js_api_path</th>
                          <th class="locate-col-action">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(hit, hitIndex) in locateResult.hits" :key="`locate-inline-hit-${index}-${hitIndex}`">
                          <td class="index-col locate-col-index">{{ hitIndex + 1 }}</td>
                          <td class="mono locate-file-cell" :title="hit.file_name || '-'">{{ shortLocateFileName(hit.file_name || '-') }}</td>
                          <td class="mono locate-path-cell" :title="hit.matched_path || '-'">{{ hit.matched_path || '-' }}</td>
                          <td class="locate-line-cell">{{ hit.line || '-' }}</td>
                          <td class="mono snippet-cell locate-snippet-cell">{{ hit.snippet || '-' }}</td>
                          <td class="locate-action-cell">
                            <button class="ghost btn-sm" :disabled="!hit.file_name" @click.stop="onSendToApiReg(hit)">
                              Send
                            </button>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                    <div v-else class="empty">No JS hit found in current candidate files</div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <div v-else class="empty">No request capture result yet</div>
      </template>

      <template v-else-if="activeView === 'requestMap'">
        <div class="view-toolbar">
          <h4>Route-Chunk-API Map</h4>
          <div class="view-toolbar-right">
            <div class="map-search-bar">
              <input
                v-model="mapSearchInput"
                type="text"
                placeholder="搜索 chunk 或 api"
                @keyup.enter="onSearchMap"
              />
              <button class="ghost" :disabled="loading" @click="onSearchMap">搜索</button>
              <button class="ghost" :disabled="loading" @click="onResetMapSearch">重置</button>
            </div>
            <div v-if="detail?.request_route_map_pagination?.total_pages" class="pager-inline">
              <div class="pager-inline-text">
                Total {{ detail.request_route_map_pagination.total }} | Page {{ detail.request_route_map_pagination.page }} / {{ detail.request_route_map_pagination.total_pages }}
              </div>
              <div class="pager-inline-actions">
                <button class="ghost" :disabled="loading || detail.request_route_map_pagination.page <= 1" @click="onMapPrevPage">
                  上一页
                </button>
                <button
                  class="ghost"
                  :disabled="loading || detail.request_route_map_pagination.page >= detail.request_route_map_pagination.total_pages"
                  @click="onMapNextPage"
                >
                  下一页
                </button>
              </div>
            </div>
            <div v-else class="pager-inline-text">
              Total {{ detail?.request_route_map_total || requestRouteMapRows.length }}
            </div>
          </div>
        </div>
        <div v-if="mapSearchKeyword" class="map-search-result-panel">
          <div class="map-search-result-title">
            搜索结果
            <span class="map-search-result-count">{{ mapSearchRouteResults.length }}</span>
          </div>
          <div v-if="mapSearchRouteResults.length" class="map-search-result-list">
            <button
              v-for="routeUrl in mapSearchRouteResults"
              :key="`map-search-${routeUrl}`"
              class="map-search-result-item mono"
              @click="onPickMapSearchResult(routeUrl)"
            >
              {{ routeUrl }}
            </button>
          </div>
          <div v-else class="empty map-empty">未找到对应路由</div>
        </div>
        <div v-if="requestRouteMapRows.length > 0" class="map-accordion">
          <article
            v-for="(row, index) in requestRouteMapRows"
            :key="`${domain}-map-${index}`"
            class="map-card"
            :class="{ open: isMapRowExpanded(index, row.route_url) }"
          >
            <button class="map-card-head" @click="toggleMapRow(index, row.route_url)">
              <div class="map-card-title mono">{{ row.route_url || '-' }}</div>
              <div class="map-card-meta">
                <span class="map-meta-pill">Chunk {{ row.chunk_count || row.chunks.length }}</span>
                <span class="map-meta-pill">API {{ row.unique_request_count || row.request_count || row.requests.length }}</span>
              </div>
            </button>

            <div v-if="isMapRowExpanded(index, row.route_url)" class="map-card-body">
              <section class="map-section">
                <h5>Chunk</h5>
                <div v-if="row.chunks.length" class="map-items">
                  <a
                    v-for="(chunkUrl, chunkIndex) in row.chunks"
                    :key="`${domain}-map-chunk-${index}-${chunkIndex}`"
                    :href="chunkUrl"
                    target="_blank"
                    rel="noreferrer"
                    class="mono map-link"
                  >
                    {{ chunkUrl }}
                  </a>
                </div>
                <div v-else class="empty map-empty">No chunk captured</div>
              </section>

              <section class="map-section">
                <h5>API</h5>
                <div v-if="row.requests.length" class="map-items">
                  <div
                    v-for="(req, reqIndex) in row.requests"
                    :key="`${domain}-map-req-${index}-${reqIndex}`"
                    class="map-req-item"
                  >
                    <span class="map-method">{{ req.method || 'GET' }}</span>
                    <span class="mono map-req-url">{{ req.url || '-' }}</span>
                    <span class="map-count">x{{ req.count || 0 }}</span>
                  </div>
                </div>
                <div v-else class="empty map-empty">No api captured</div>
              </section>
            </div>
          </article>
        </div>
        <div v-else class="empty">No route-chunk-request map yet</div>
      </template>

      <template v-else-if="activeView === 'analysis'">
        <div class="view-toolbar">
          <h4>分析</h4>
        </div>
        <div class="analysis-panel-wrap">
          <section class="analysis-card">
            <div class="analysis-head">
              <h5>结果分析</h5>
              <span class="analysis-priority" :class="analysisLevel || 'pending'">{{ analysisPriorityText }}</span>
            </div>

            <section class="analysis-section">
              <div class="analysis-label">分析结论</div>
              <div class="analysis-text">{{ analysisReasonText }}</div>
            </section>

            <section class="analysis-section">
              <div class="analysis-label">快照覆盖</div>
              <div class="analysis-stats">
                <div class="analysis-stat">
                  <strong>{{ analysisSnapshotCount }}</strong>
                  <span>快照数</span>
                </div>
                <div class="analysis-stat">
                  <strong>{{ analysisSampleCount }}</strong>
                  <span>请求数</span>
                </div>
                <div class="analysis-stat">
                  <strong>{{ analysisScore }}</strong>
                  <span>分数</span>
                </div>
              </div>
            </section>

            <section class="analysis-section">
              <div class="analysis-label">关键信号</div>
              <ul v-if="analysisSignals.length" class="analysis-list">
                <li v-for="signal in analysisSignals" :key="signal">{{ signal }}</li>
              </ul>
              <div v-else class="analysis-text muted">当前还没有足够的分析信号。</div>
            </section>

            <section class="analysis-section">
              <div class="analysis-label">自动化阶段</div>
              <div v-if="hasAutomationStages" class="automation-grid">
                <article
                  v-for="item in analysisAutomationItems"
                  :key="item.key"
                  class="automation-card"
                >
                  <div class="automation-head">
                    <strong>{{ item.title }}</strong>
                    <span class="automation-status" :class="item.status">{{ item.statusText }}</span>
                  </div>
                  <div class="analysis-text">{{ item.summary }}</div>
                  <div v-if="item.lines.length" class="automation-lines">
                    <div
                      v-for="line in item.lines"
                      :key="`${item.key}-${line}`"
                      class="automation-line mono"
                    >
                      {{ line }}
                    </div>
                  </div>
                </article>
              </div>
              <div v-else class="analysis-text muted">当前还没有自动化结果。</div>
            </section>

            <section class="analysis-section">
              <div class="analysis-label">下一步建议</div>
              <div class="analysis-text">{{ analysisNextAction }}</div>
            </section>
          </section>
        </div>
      </template>

      <template v-else-if="activeView === 'apiExtract'">
        <ProjectApiExtractTab
          :domain="domain"
          :jump-preset="apiRegJumpPreset"
          @extracted="onApiExtracted"
          @base-ready="onApiBaseReady"
        />
      </template>

      <template v-else-if="activeView === 'baseRequest'">
        <ProjectBaseRequestTab
          :domain="domain"
          :refresh-key="requestReloadKey"
          :infer-preset="apiRequestInferPreset"
          :base-request-preset="apiRequestBasePreset"
          @ready="onBaseRequestReady"
        />
      </template>

      <template v-else-if="activeView === 'apiRequest'">
        <ProjectApiRequestTab
          :domain="domain"
          :refresh-key="requestReloadKey"
          :infer-preset="apiRequestInferPreset"
          :base-request-preset="apiRequestBasePreset"
        />
      </template>

    </section>
  </section>
</template>

<style scoped>
.index-col {
  width: 48px;
  min-width: 48px;
  text-align: center;
}

.project-toolbar {
  border-bottom: 1px solid #dce8f2;
  padding: 4px 0 8px;
  display: flex;
  align-items: flex-end;
  justify-content: flex-start;
  gap: 8px;
  flex-wrap: nowrap;
  overflow-x: auto;
}

.toolbar-right-meta {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
  flex: 0 0 auto;
}

.domain-title {
  margin: 0;
  font-size: 20px;
  line-height: 1.1;
  font-weight: 800;
  color: #0f3656;
  letter-spacing: 0.2px;
  max-width: min(32vw, 480px);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
  flex: 0 1 360px;
}

.toolbar-tabs {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  min-width: 0;
  flex-wrap: nowrap;
  border-bottom: 1px solid #dce8f2;
  flex: 0 0 auto;
}

.nav-tab {
  color: #36526b;
  text-decoration: none;
  border: 1px solid transparent;
  border-radius: 10px 10px 0 0;
  background: transparent;
  padding: 7px 12px 8px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
  margin-bottom: -1px;
  transition: color 0.15s ease, border-color 0.15s ease, background-color 0.15s ease;
}

.nav-tab:hover {
  color: #244d6d;
  border-color: #d7e5f0 #d7e5f0 transparent;
  background: #f5f9fd;
}

.nav-tab.active {
  color: #0d5f99;
  background: #ffffff;
  border-color: #bfd4e5 #bfd4e5 #ffffff;
  box-shadow: none;
}

.back-link {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
  border: 1px solid #c9dbe9;
  border-radius: 8px;
  background: #f5faff;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 700;
  color: #3f6686;
  transition: color 0.15s ease, border-color 0.15s ease, background-color 0.15s ease;
  white-space: nowrap;
  flex: 0 0 auto;
}

.back-link:hover {
  color: #2f5575;
  border-color: #b8cfdf;
  background: #ecf6ff;
}

.tab-count {
  display: inline;
  min-width: 0;
  padding: 0;
  border-radius: 0;
  font-size: 11px;
  font-weight: 700;
  color: #7d91a3;
  background: transparent;
}

.nav-tab.active .tab-count {
  color: #5a7e99;
  background: transparent;
}

.preview-table td {
  vertical-align: top;
}

.btn-sm {
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 12px;
}

.actions-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.map-accordion {
  display: grid;
  gap: 10px;
}

.analysis-panel-wrap {
  width: 100%;
}

.analysis-card {
  display: grid;
  gap: 14px;
  padding: 14px;
  border: 1px solid #dce7f2;
  border-radius: 12px;
  background: linear-gradient(180deg, #f9fbff 0%, #f3f7fc 100%);
  width: 100%;
}

.analysis-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.analysis-head h5 {
  margin: 0;
  font-size: 15px;
}

.analysis-priority {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 76px;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: #49617b;
  background: #e6edf5;
}

.analysis-priority.high {
  color: #8e2f00;
  background: #ffe4d6;
}

.analysis-priority.medium {
  color: #6b5800;
  background: #fff2c9;
}

.analysis-priority.low {
  color: #24587d;
  background: #dff0ff;
}

.analysis-section {
  display: grid;
  gap: 8px;
}

.analysis-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #6c7f92;
}

.analysis-text {
  font-size: 13px;
  line-height: 1.6;
  color: #203448;
}

.analysis-text.muted {
  color: #708396;
}

.analysis-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.analysis-stat {
  display: grid;
  gap: 4px;
  padding: 10px;
  border: 1px solid #dce7f2;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.85);
}

.analysis-stat strong {
  font-size: 18px;
  color: #1d3347;
}

.analysis-stat span {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #6c7f92;
}

.analysis-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
  color: #203448;
  font-size: 13px;
  line-height: 1.5;
}

.automation-grid {
  display: grid;
  gap: 10px;
}

.automation-card {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid #dce7f2;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.86);
}

.automation-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.automation-head strong {
  font-size: 13px;
  color: #1d3347;
}

.automation-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 62px;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  color: #54687b;
  background: #e6edf5;
}

.automation-status.ready {
  color: #0f6b45;
  background: #dff6ea;
}

.automation-status.failed {
  color: #8a2823;
  background: #ffe3df;
}

.automation-status.pending {
  color: #5d6f80;
  background: #edf2f7;
}

.automation-lines {
  display: grid;
  gap: 6px;
}

.automation-line {
  border: 1px solid #e0e9f2;
  border-radius: 8px;
  background: #f8fbfe;
  padding: 7px 8px;
  white-space: pre-wrap;
  word-break: break-all;
}

.map-card {
  border: 1px solid #dce7f2;
  border-radius: 10px;
  background: #fbfdff;
  overflow: hidden;
}

.map-card.open {
  border-color: #bdd7ec;
  box-shadow: 0 6px 16px rgba(18, 44, 67, 0.08);
}

.map-card-head {
  width: 100%;
  border: 0;
  border-radius: 0;
  margin: 0;
  padding: 10px 12px;
  background: #f4f9ff;
  color: #284760;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  text-align: left;
}

.map-card-head:hover {
  border: 0;
  background: #edf6ff;
  color: #1f4869;
}

.map-card-title {
  flex: 1;
  font-size: 12px;
  line-height: 1.55;
  white-space: normal;
  word-break: break-all;
}

.map-card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.map-meta-pill {
  display: inline-flex;
  align-items: center;
  border: 1px solid #c5dcef;
  border-radius: 999px;
  background: #fff;
  color: #2f5879;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
}

.map-card-body {
  border-top: 1px solid #e3edf6;
  padding: 10px 12px;
  display: grid;
  gap: 10px;
}

.map-section {
  display: grid;
  gap: 8px;
}

.map-section h5 {
  margin: 0;
  color: #375671;
  font-size: 12px;
  font-weight: 700;
}

.map-items {
  display: grid;
  gap: 7px;
  max-height: 300px;
  overflow: auto;
}

.map-link {
  display: block;
  border: 1px solid #dde8f3;
  border-radius: 8px;
  background: #fff;
  color: #274e6f;
  padding: 7px 8px;
  text-decoration: none;
  white-space: normal;
  word-break: break-all;
}

.map-link:hover {
  border-color: #bfd7ea;
  background: #f3f9ff;
  text-decoration: none;
}

.locate-candidates {
  margin: 0 0 8px;
  color: #4a6076;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.snippet-cell {
  white-space: normal;
  word-break: break-all;
}

.request-locate-row > td {
  background: #f8fbfe;
}

.locate-inline-cell {
  padding-left: 8px;
  padding-right: 8px;
}

.locate-inline-wrap {
  border: 1px solid #dbe7f2;
  border-radius: 8px;
  padding: 10px;
  background: #f9fbfd;
}

.locate-inline-head {
  margin: 0 0 8px;
  color: #284b68;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.locate-inline-table {
  margin-top: 8px;
  width: 100%;
  table-layout: fixed;
}

.locate-col-index {
  width: 4%;
  min-width: 36px;
  text-align: center;
}

.locate-col-file {
  width: 12%;
}

.locate-col-path {
  width: 8%;
}

.locate-col-line {
  width: 6%;
}

.locate-col-snippet {
  width: 65%;
}

.locate-col-action {
  width: 5%;
  min-width: 72px;
}

.locate-file-cell {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.locate-path-cell {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.locate-line-cell {
  white-space: nowrap;
}

.locate-snippet-cell {
  white-space: normal;
  word-break: break-all;
}

.locate-action-cell {
  white-space: nowrap;
}

.locate-inline-error {
  border: 1px solid #f0c4c1;
  border-radius: 8px;
  background: #fff6f5;
  color: #8a1f17;
  padding: 8px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}

.map-req-item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: start;
  gap: 8px;
  border: 1px solid #dde8f2;
  border-radius: 8px;
  background: #fff;
  padding: 7px 8px;
}

.map-method {
  font-size: 11px;
  font-weight: 700;
  color: #0d5f99;
  background: #e7f2fb;
  border: 1px solid #bddbf4;
  border-radius: 999px;
  padding: 2px 8px;
}

.map-req-url {
  white-space: normal;
  word-break: break-all;
}

.map-count {
  font-size: 11px;
  color: #6a8096;
  white-space: nowrap;
}

.map-empty {
  padding: 0;
}

.view-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.view-toolbar h4 {
  margin: 0;
}

.view-toolbar-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.map-search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.map-search-bar input {
  width: 280px;
  max-width: 100%;
}

.map-search-result-panel {
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid #dce7f2;
  border-radius: 10px;
  background: #f8fbff;
}

.map-search-result-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 700;
  color: #284a67;
}

.map-search-result-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #e7f2fb;
  color: #0d5f99;
  font-size: 12px;
}

.map-search-result-list {
  display: grid;
  gap: 8px;
}

.map-search-result-item {
  width: 100%;
  text-align: left;
  border: 1px solid #d3e2ef;
  border-radius: 8px;
  background: #fff;
  color: #244d6d;
  padding: 7px 9px;
  word-break: break-all;
}

.map-search-result-item:hover {
  border-color: #bfd7ea;
  background: #f3f9ff;
}

.js-download-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.route-rewrite-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.route-rewrite-bar input {
  width: 180px;
}

.route-rewrite-bar select {
  min-width: 70px;
  height: 32px;
}

.js-download-bar input[type='number'] {
  width: 90px;
}

.chunk-count-inline {
  margin-left: 6px;
  color: #4d667d;
  font-size: 12px;
  font-weight: 400;
}

.manual-api-url {
  width: min(560px, 52vw);
  min-width: 280px;
}

.job-live-card {
  margin-top: 12px;
  border: 1px solid #cfe1ee;
  border-radius: 12px;
  background: linear-gradient(180deg, #f8fcff 0%, #eef7fd 100%);
  padding: 12px;
  display: grid;
  gap: 10px;
}

.job-live-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.job-live-title-wrap {
  display: grid;
  gap: 4px;
}

.job-live-title {
  color: #133d5b;
  font-size: 14px;
}

.job-live-status {
  color: #567088;
  font-size: 12px;
}

.job-live-progress {
  color: #2f5879;
  font-size: 12px;
}

.job-live-current,
.job-live-recent {
  display: grid;
  gap: 6px;
}

.job-live-label {
  color: #4d667d;
  font-size: 12px;
  font-weight: 700;
}

.job-live-recent-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.job-live-chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid #c9deee;
  border-radius: 999px;
  background: #fff;
  color: #245374;
  font-size: 11px;
  padding: 4px 8px;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.job-live-logs {
  display: grid;
  gap: 6px;
  border-top: 1px solid #d8e6f1;
  padding-top: 10px;
}

.job-live-log-row {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px;
  align-items: start;
  color: #37546b;
  font-size: 12px;
}

.job-live-log-time {
  color: #6d8498;
  white-space: nowrap;
}

.job-live-log-message {
  white-space: pre-wrap;
  word-break: break-all;
}

.progress-wrap {
  margin-top: 10px;
}

.progress-track {
  height: 8px;
  border-radius: 999px;
  background: #e7eef6;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #0d8ed9, #2dc2b5);
}

.progress-text {
  margin-top: 6px;
  font-size: 12px;
  color: #4d6479;
}

.danger {
  border-color: #e2b0ad;
  color: #8a2823;
}

.job-error {
  margin-top: 10px;
  border: 1px solid #f0c4c1;
  border-radius: 8px;
  background: #fff6f5;
  color: #8a1f17;
  padding: 8px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}

.pager-inline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.pager-inline-text {
  color: #54697d;
  font-size: 12px;
}

.pager-inline-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 980px) {
  .project-toolbar {
    overflow-x: visible;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 8px;
  }

  .toolbar-right-meta {
    width: 100%;
    justify-content: space-between;
    margin-left: 0;
  }

  .domain-title {
    font-size: 20px;
    max-width: 100%;
    text-align: left;
    flex: 1 1 auto;
  }

  .toolbar-tabs,
  .view-toolbar-right {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .analysis-stats {
    grid-template-columns: 1fr;
  }

  .back-link {
    margin-left: 0;
  }

  .pager-inline {
    width: 100%;
    justify-content: flex-start;
  }

  .route-rewrite-bar input {
    width: 100%;
  }
}
</style>

