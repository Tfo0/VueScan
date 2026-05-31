<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import axios from 'axios'
import {
  runVueApiAutoRegex,
  fetchVueApiContext,
  runVueApiBeautify,
  runVueApiExtract,
  runVueApiPreview,
  saveVueApiPreview,
  type ApiEndpointItem,
  type VueApiAutoRegexResult,
  type VueApiBeautify,
  type VueApiExtractResult,
  type VueApiPreviewResult,
} from '../../api/vueApi'
import {
  inferVueRequestBaseFromPaths,
  type VueRequestInferResult,
} from '../../api/vueRequest'

const props = defineProps<{
  domain: string
  jumpPreset?: {
    seq: number
    js_file: string
    line?: number
    matched_path?: string
    js_api_path?: string
  } | null
}>()

const emit = defineEmits<{
  (e: 'extracted', payload: VueApiExtractResult): void
  (e: 'baseReady', payload: VueRequestInferResult): void
}>()

const jsFiles = ref<string[]>([])
const jsUrls = ref<string[]>([])
const jsSource = ref('')
const pattern = ref('')
const targetApi = ref('')

const beautifyResult = ref<VueApiBeautify | null>(null)
const previewResult = ref<VueApiPreviewResult | null>(null)
const extractResult = ref<VueApiExtractResult | null>(null)
const autoRegexResult = ref<VueApiAutoRegexResult | null>(null)

const loadingContext = ref(false)
const previewing = ref(false)
const extracting = ref(false)
const savingPreview = ref(false)
const inferringBase = ref(false)
const autoRegexing = ref(false)
const codeBlockRef = ref<HTMLElement | null>(null)

const message = ref('')
const error = ref('')

function splitDomainLabels(value: string) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .split('.')
    .map((item) => item.trim())
    .filter((item) => Boolean(item))
}

function readHostnameFromValue(value: string) {
  const text = String(value || '').trim()
  if (!text) return ''
  if (text.startsWith('/')) return String(props.domain || '').trim().toLowerCase()
  try {
    return String(new URL(text).hostname || '').trim().toLowerCase()
  } catch {
    return ''
  }
}

function countCommonSuffixLabels(left: string[], right: string[]) {
  let count = 0
  let leftIndex = left.length - 1
  let rightIndex = right.length - 1
  while (leftIndex >= 0 && rightIndex >= 0) {
    if (left[leftIndex] !== right[rightIndex]) break
    count += 1
    leftIndex -= 1
    rightIndex -= 1
  }
  return count
}

function apiDomainAffinity(item: ApiEndpointItem) {
  const projectHost = String(props.domain || '').trim().toLowerCase()
  const targetHost = readHostnameFromValue(String(item.url || item.path || '').trim())
  const projectLabels = splitDomainLabels(projectHost)
  const targetLabels = splitDomainLabels(targetHost)
  return {
    exactMatch: targetHost && projectHost && targetHost === projectHost ? 1 : 0,
    suffixMatchCount: countCommonSuffixLabels(projectLabels, targetLabels),
    depthDistance: Math.abs(projectLabels.length - targetLabels.length),
    targetHost,
  }
}

function compareApiDomainAffinity(left: ApiEndpointItem, right: ApiEndpointItem) {
  const leftAffinity = apiDomainAffinity(left)
  const rightAffinity = apiDomainAffinity(right)
  if (leftAffinity.exactMatch !== rightAffinity.exactMatch) {
    return rightAffinity.exactMatch - leftAffinity.exactMatch
  }
  if (leftAffinity.suffixMatchCount !== rightAffinity.suffixMatchCount) {
    return rightAffinity.suffixMatchCount - leftAffinity.suffixMatchCount
  }
  if (leftAffinity.depthDistance !== rightAffinity.depthDistance) {
    return leftAffinity.depthDistance - rightAffinity.depthDistance
  }
  return leftAffinity.targetHost.localeCompare(rightAffinity.targetHost)
}

function sortApiPreviewRows(items: ApiEndpointItem[]) {
  const rows = [...(Array.isArray(items) ? items : [])]
  rows.sort((left, right) => {
    const domainCompare = compareApiDomainAffinity(left, right)
    if (domainCompare !== 0) return domainCompare
    return Number(left.id || 0) - Number(right.id || 0)
  })
  return rows
}

function resolveError(err: unknown) {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: string } | undefined
    return data?.error || err.message || '请求失败'
  }
  if (err instanceof Error) return err.message
  return '未知错误'
}

function clearOutputs() {
  beautifyResult.value = null
  previewResult.value = null
  extractResult.value = null
  autoRegexResult.value = null
}

function _sourceKey(type: 'file' | 'url', value: string) {
  return `${type}:${String(value || '').trim()}`
}

function _parseSourceKey(raw: string): { type: 'file' | 'url'; value: string } {
  const token = String(raw || '').trim()
  if (token.startsWith('url:')) {
    return { type: 'url', value: token.slice(4) }
  }
  if (token.startsWith('file:')) {
    return { type: 'file', value: token.slice(5) }
  }
  if (/^https?:\/\//i.test(token)) {
    return { type: 'url', value: token }
  }
  return { type: 'file', value: token }
}

function _localSourceValues() {
  return jsFiles.value
    .map((item) => String(item || '').trim())
    .filter((item) => Boolean(item))
}

function _remoteSourceValues() {
  return jsUrls.value
    .map((item) => String(item || '').trim())
    .filter((item) => Boolean(item))
}

function _hasSourceValue(type: 'file' | 'url', value: string) {
  const token = String(value || '').trim()
  if (!token) return false
  return type === 'file'
    ? _localSourceValues().includes(token)
    : _remoteSourceValues().includes(token)
}

async function loadContext(reset = false) {
  const domain = String(props.domain || '').trim()
  if (!domain) {
    jsFiles.value = []
    jsUrls.value = []
    jsSource.value = ''
    if (reset) {
      pattern.value = ''
      clearOutputs()
    }
    return
  }

  loadingContext.value = true
  error.value = ''
  try {
    const payload = await fetchVueApiContext(domain)
    jsFiles.value = Array.isArray(payload.js_files) ? payload.js_files : []
    jsUrls.value = Array.isArray(payload.js_urls) ? payload.js_urls : []

    const preferredJsFile = String(payload.js_file || '')
    const preferredJsUrl = String(payload.js_url || '')
    if (preferredJsFile && _hasSourceValue('file', preferredJsFile)) {
      jsSource.value = _sourceKey('file', preferredJsFile)
    } else if (preferredJsUrl && _hasSourceValue('url', preferredJsUrl)) {
      jsSource.value = _sourceKey('url', preferredJsUrl)
    } else {
      const parsedCurrent = _parseSourceKey(jsSource.value)
      const currentValid = _hasSourceValue(parsedCurrent.type, parsedCurrent.value)
      if (!currentValid) {
        const localFirst = _localSourceValues()[0] || ''
        if (localFirst) {
          jsSource.value = _sourceKey('file', localFirst)
        } else {
          const remoteFirst = _remoteSourceValues()[0] || ''
          jsSource.value = remoteFirst ? _sourceKey('url', remoteFirst) : ''
        }
      }
    }

    if (reset || !pattern.value) {
      pattern.value = String(payload.pattern || '')
    }

    const savedExtract = payload.extract_result
    const savedEndpoints = Array.isArray(savedExtract?.endpoints) ? savedExtract.endpoints : []
    if (savedEndpoints.length) {
      const sortedEndpoints = sortApiPreviewRows(savedEndpoints)
      previewResult.value = {
        domain,
        source_type: String(savedExtract?.source_type || 'all_chunks'),
        source: String(savedExtract?.source || ''),
        source_name: String(savedExtract?.source_name || 'all_chunks'),
        js_file_count: jsFiles.value.length,
        count: Number(savedExtract?.count || savedExtract?.endpoint_count || sortedEndpoints.length || 0),
        endpoints: sortedEndpoints,
      }
      extractResult.value = {
        job_id: String(savedExtract?.job_id || ''),
        domain,
        endpoint_count: Number(savedExtract?.endpoint_count || sortedEndpoints.length || 0),
        count: Number(savedExtract?.count || savedExtract?.endpoint_count || sortedEndpoints.length || 0),
        endpoints: sortedEndpoints,
        output_path: String(savedExtract?.output_path || ''),
      }
    } else if (reset) {
      previewResult.value = null
      extractResult.value = null
    }

    if (jsSource.value) {
      await onBeautify()
    }
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    loadingContext.value = false
  }
}

async function onJsFileChange() {
  clearOutputs()
  if (jsSource.value) {
    await onBeautify()
  }
}

async function onBeautify() {
  const domain = String(props.domain || '').trim()
  if (!domain) {
    error.value = '项目域名缺失'
    return
  }
  if (!jsSource.value) {
    error.value = '请选择 JS 文件'
    return
  }

  const parsedSource = _parseSourceKey(jsSource.value)
  error.value = ''
  try {
    const payload = await runVueApiBeautify({
      domain,
      js_file: parsedSource.type === 'file' ? parsedSource.value : '',
      js_url: parsedSource.type === 'url' ? parsedSource.value : '',
      pattern: pattern.value,
    })
    beautifyResult.value = payload.beautify
    message.value = ''
  } catch (err) {
    error.value = resolveError(err)
  }
}

function _normalizeJumpText(value: string) {
  return String(value || '').trim()
}

function _dedupeStrings(values: string[]) {
  const result: string[] = []
  const seen = new Set<string>()
  values.forEach((item) => {
    const token = _normalizeJumpText(item)
    if (!token || seen.has(token)) return
    seen.add(token)
    result.push(token)
  })
  return result
}

function _findLineByMatchedPath(code: string, matchedPath: string) {
  const token = _normalizeJumpText(matchedPath)
  if (!token) return 0
  const plain = token.startsWith('/') ? token.slice(1) : token
  const slash = token.startsWith('/') ? token : `/${token}`
  const candidates = _dedupeStrings([
    token,
    plain,
    slash,
    `"${token}"`,
    `'${token}'`,
    `\`${token}\``,
    `"${plain}"`,
    `'${plain}'`,
    `\`${plain}\``,
    `"${slash}"`,
    `'${slash}'`,
    `\`${slash}\``,
  ])

  for (const candidate of candidates) {
    const idx = code.indexOf(candidate)
    if (idx >= 0) {
      return code.slice(0, idx).split(/\r?\n/).length
    }
  }
  return 0
}

function _scrollBeautifyToLine(targetLine: number) {
  const el = codeBlockRef.value
  if (!el) return
  const line = Math.max(1, Number(targetLine || 1))
  const style = window.getComputedStyle(el)
  let lineHeight = Number.parseFloat(style.lineHeight || '')
  if (!Number.isFinite(lineHeight) || lineHeight <= 0) {
    lineHeight = 18
  }
  el.scrollTop = Math.max(0, (line - 3) * lineHeight)
}

async function _applyJumpPreset() {
  const preset = props.jumpPreset
  if (!preset) return
  const snippet = String(preset.js_api_path || '').trim()
  if (snippet) {
    targetApi.value = snippet
  } else if (String(preset.matched_path || '').trim()) {
    targetApi.value = String(preset.matched_path || '').trim()
  }
  await locatePreviewEndpointSource({
    file_name: preset.js_file,
    line: Number(preset.line || 0),
    matched_path: String(preset.matched_path || '').trim(),
  })
}

// 预览结果里的“定位”会切换上面的美化 JS，并尽量滚到当前接口附近。
async function locatePreviewEndpointSource(hit: {
  file_name?: string
  line?: number
  matched_path?: string
}) {
  const domain = String(props.domain || '').trim()
  if (!domain) return
  const targetFile = _normalizeJumpText(hit.file_name || '')
  if (!targetFile) return
  const matchedPath = _normalizeJumpText(hit.matched_path || '')

  if (!_localSourceValues().length || !_hasSourceValue('file', targetFile)) {
    await loadContext(false)
  }
  if (!_hasSourceValue('file', targetFile)) {
    error.value = `项目中未找到 JS 文件：${targetFile}`
    return
  }

  jsSource.value = _sourceKey('file', targetFile)
  await onBeautify()
  await nextTick()

  const code = String(beautifyResult.value?.code || '')
  if (!code) return
  const lineByPath = _findLineByMatchedPath(code, matchedPath)
  const fallbackLine = Math.max(1, Number(hit.line || 1))
  const targetLine = lineByPath > 0 ? lineByPath : fallbackLine
  _scrollBeautifyToLine(targetLine)
  message.value = `已定位到 JS：${targetFile}`
}

async function onLocatePreviewEndpoint(item: VueApiPreviewResult['endpoints'][number]) {
  await locatePreviewEndpointSource({
    file_name: String(item?.source_file || '').trim(),
    line: Number(item?.source_line || 0),
    matched_path: String(item?.path || item?.url || '').trim(),
  })
}

async function onPreviewExtract() {
  const domain = String(props.domain || '').trim()
  if (!domain) {
    error.value = '项目域名缺失'
    return
  }
  if (!pattern.value.trim()) {
    error.value = 'Please input regex pattern'
    return
  }

  previewing.value = true
  error.value = ''
  try {
    const parsedSource = _parseSourceKey(jsSource.value)
    previewResult.value = await runVueApiPreview({
      domain,
      pattern: pattern.value.trim(),
      js_file: parsedSource.type === 'file' ? parsedSource.value : '',
      js_url: parsedSource.type === 'url' ? parsedSource.value : '',
    })
    previewResult.value = {
      ...previewResult.value,
      endpoints: sortApiPreviewRows(Array.isArray(previewResult.value?.endpoints) ? previewResult.value.endpoints : []),
    }
    message.value = `Preview extracted: ${previewResult.value.count || 0}`
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    previewing.value = false
  }
}

async function onAutoRegex() {
  const domain = String(props.domain || '').trim()
  if (!domain) {
    error.value = '项目域名缺失'
    return
  }
  if (!targetApi.value.trim()) {
    error.value = '请先填入 js_api_path 片段'
    return
  }

  autoRegexing.value = true
  error.value = ''
  try {
    const parsedSource = _parseSourceKey(jsSource.value)
    autoRegexResult.value = await runVueApiAutoRegex({
      domain,
      jsApiPath: targetApi.value.trim(),
      js_file: parsedSource.type === 'file' ? parsedSource.value : '',
      maxCandidates: 3,
    })
    const selectedPattern = String(autoRegexResult.value?.selected_pattern || '').trim()
    if (selectedPattern) {
      pattern.value = selectedPattern
    }
    const candidateCount = Number(autoRegexResult.value?.candidate_count || 0)
    const aiError = String(autoRegexResult.value?.ai_error || '').trim()
    if (aiError) {
      message.value = `Auto regex candidates generated: ${candidateCount} (AI: ${aiError})`
    } else {
      message.value = `Auto regex candidates generated: ${candidateCount}`
    }
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    autoRegexing.value = false
  }
}

function onApplyAutoRegex(patternValue: string) {
  const token = String(patternValue || '').trim()
  if (!token) return
  pattern.value = token
  message.value = 'Candidate regex applied'
}

function autoRegexLabel(item: VueApiAutoRegexResult['candidates'][number]) {
  const label = String(item?.label || '').trim()
  if (label) return label
  const source = String(item?.source || '').trim().toLowerCase()
  if (source === 'builtin') return '内置正则'
  if (source === 'ai') return 'AI生成'
  return source || '-'
}

async function onBatchExtract() {
  const domain = String(props.domain || '').trim()
  if (!domain) {
    error.value = '项目域名缺失'
    return
  }
  if (!pattern.value.trim()) {
    error.value = 'Please input regex pattern'
    return
  }

  extracting.value = true
  error.value = ''
  try {
    extractResult.value = await runVueApiExtract({
      domain,
      pattern: pattern.value.trim(),
    })

    const batchEndpoints = Array.isArray(extractResult.value?.endpoints)
      ? extractResult.value.endpoints
      : []
    const batchCount = Number(extractResult.value?.endpoint_count || batchEndpoints.length || 0)

    previewResult.value = {
      domain,
      source_type: 'all_chunks',
      source: '',
      source_name: 'all_chunks',
      js_file_count: jsFiles.value.length,
      count: batchCount,
      endpoints: sortApiPreviewRows(batchEndpoints),
    }

    message.value = `Batch extracted: ${batchCount}`
    emit('extracted', extractResult.value)
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    extracting.value = false
  }
}

async function onInferBaseFromPreview() {
  const domain = String(props.domain || '').trim()
  if (!domain) {
    error.value = '项目域名缺失'
    return
  }
  const items = Array.isArray(previewResult.value?.endpoints)
    ? previewResult.value!.endpoints
    : []
  if (!items.length) {
    error.value = '预览结果为空，无法查询 BaseURL / BaseAPI'
    return
  }

  inferringBase.value = true
  error.value = ''
  try {
    const payload = await inferVueRequestBaseFromPaths({
      domain,
      endpoints: items.map((item, index) => ({
        id: Number(item.id || index + 1),
        method: String(item.method || 'GET').toUpperCase(),
        path: String(item.path || item.url || '').trim(),
      })),
    })
    const result = payload.inferResult
    if (!result?.inferred) {
      error.value = String(result?.error || '无法从预览结果查询 BaseURL / BaseAPI')
      return
    }
    emit('baseReady', result)
    message.value = `查询 BaseURL / BaseAPI 成功：query_baseurl=${result.baseurl || '-'} query_baseapi=${result.baseapi || '(empty)'}`
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    inferringBase.value = false
  }
}

async function onSavePreviewResult() {
  const domain = String(props.domain || '').trim()
  if (!domain) {
    error.value = '项目域名缺失'
    return
  }
  if (!pattern.value.trim()) {
    error.value = 'Please input regex pattern'
    return
  }
  const items = Array.isArray(previewResult.value?.endpoints)
    ? previewResult.value.endpoints
    : []
  if (!items.length) {
    error.value = '暂无可保存的接口'
    return
  }

  savingPreview.value = true
  error.value = ''
  try {
    extractResult.value = await saveVueApiPreview({
      domain,
      pattern: pattern.value.trim(),
      source_type: String(previewResult.value?.source_type || '').trim(),
      source: String(previewResult.value?.source || '').trim(),
      source_name: String(previewResult.value?.source_name || '').trim(),
      endpoints: items,
    })
    message.value = `已保存 ${Number(extractResult.value?.endpoint_count || items.length || 0)} 条接口`
    emit('extracted', extractResult.value)
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    savingPreview.value = false
  }
}

async function copyText(value: string) {
  const text = String(value || '')
  if (!text) return false
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // fallback below
  }
  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', 'readonly')
    textarea.style.position = 'fixed'
    textarea.style.left = '-9999px'
    document.body.appendChild(textarea)
    textarea.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(textarea)
    return ok
  } catch {
    return false
  }
}

async function onCopyPreviewEndpoints() {
  const items = Array.isArray(previewResult.value?.endpoints)
    ? previewResult.value!.endpoints
    : []
  if (!items.length) {
    error.value = '暂无可复制的接口'
    return
  }
  const lines = Array.from(
    new Set(
      items
        .map((item) => String(item.path || item.url || '').trim())
        .filter((item) => Boolean(item)),
    ),
  )
  if (!lines.length) {
    error.value = '暂无可复制的接口'
    return
  }
  const ok = await copyText(lines.join('\n'))
  if (!ok) {
    error.value = 'Copy failed, check clipboard permission'
    return
  }
  message.value = `Copied ${lines.length} endpoints`
}

function escapeHtml(value: string) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function highlightJavaScript(source: string) {
  let text = String(source || '')
  const buckets: string[] = []

  function keep(regex: RegExp, cls: string) {
    text = text.replace(regex, (match) => {
      const token = `___TOK_${buckets.length}___`
      buckets.push(`<span class="${cls}">${escapeHtml(match)}</span>`)
      return token
    })
  }

  keep(/\/\*[\s\S]*?\*\//g, 'tok-comment')
  keep(/\/\/[^\n\r]*/g, 'tok-comment')
  keep(/`(?:\\[\s\S]|[^`])*`/g, 'tok-string')
  keep(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g, 'tok-string')

  text = escapeHtml(text)
  text = text.replace(/\b(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b/g, '<span class="tok-number">$&</span>')
  text = text.replace(/\b(?:true|false|null|undefined|NaN|Infinity)\b/g, '<span class="tok-literal">$&</span>')
  text = text.replace(/\b(?:await|break|case|catch|class|const|continue|debugger|default|delete|do|else|enum|export|extends|finally|for|function|if|import|in|instanceof|let|new|return|super|switch|this|throw|try|typeof|var|void|while|with|yield|async)\b/g, '<span class="tok-keyword">$&</span>')
  text = text.replace(/___TOK_(\d+)___/g, (_, idx) => buckets[Number(idx)] || _)
  return text
}

const beautifyHtml = computed(() => {
  if (!beautifyResult.value?.code) return ''
  return highlightJavaScript(beautifyResult.value.code)
})

watch(
  () => props.domain,
  async () => {
    clearOutputs()
    jsFiles.value = []
    jsUrls.value = []
    jsSource.value = ''
    pattern.value = ''
    targetApi.value = ''
    await loadContext(true)
  },
)

watch(
  () => props.jumpPreset?.seq,
  async (value, prev) => {
    if (!value || value === prev) return
    await _applyJumpPreset()
  },
)

onMounted(async () => {
  await loadContext(true)
  if (props.jumpPreset?.js_file) {
    await _applyJumpPreset()
  }
})
</script>

<template>
  <section class="project-api-tab">
    <div v-if="message" class="notice success">{{ message }}</div>
    <div v-if="error" class="notice error">{{ error }}</div>

    <div class="sub-block">
      <div class="sub-head">
        <h4>项目JS</h4>
        <button class="ghost" :disabled="loadingContext" @click="loadContext(false)">
          {{ loadingContext ? '加载中...' : '刷新' }}
        </button>
      </div>
      <div class="api-grid top-grid">
        <div>
          <label>js_api_path</label>
          <input
            v-model="targetApi"
            type="text"
            class="mono"
            placeholder='请填入截断后的 JS 片段，例如：Object(b["a"])("/admin/sys/user/getUserInfo",'
          />
        </div>
        <div>
          <label>JS Locate</label>
          <select v-model="jsSource" class="js-file-select mono" @change="onJsFileChange">
            <option value="">-- 选择 JS 来源 --</option>
            <optgroup v-if="jsFiles.length" label="本地 downChunk">
              <option
                v-for="item in jsFiles"
                :key="`file-${item}`"
                :value="_sourceKey('file', item)"
              >
                {{ item }}
              </option>
            </optgroup>
            <optgroup v-if="jsUrls.length" label="捕获 js.txt">
              <option
                v-for="item in jsUrls"
                :key="`url-${item}`"
                :value="_sourceKey('url', item)"
              >
                {{ item }}
              </option>
            </optgroup>
          </select>
        </div>
        <div class="reg-table-wrap">
          <table class="task-table reg-input-table">
            <tbody>
              <tr>
                <td>
                  <input v-model="pattern" type="text" placeholder="/base" class="mono" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="api-actions vertical">
          <button class="ghost" :disabled="previewing" @click="onPreviewExtract">{{ previewing ? '预览中...' : '预览提取' }}</button>
          <button class="ghost" :disabled="autoRegexing" @click="onAutoRegex">{{ autoRegexing ? '运行中...' : '自动正则' }}</button>
          <button :disabled="extracting" @click="onBatchExtract">{{ extracting ? '提取中...' : '批量提取' }}</button>
        </div>
      </div>

      <div v-if="beautifyResult" class="code-area">
        <div class="sub-head code-head">
          <h4>Beautify JS</h4>
          <div class="sub-head-actions code-meta">
            <span class="mono">{{ beautifyResult.source_name || beautifyResult.source || '-' }}</span>
            <span class="mono">chars={{ beautifyResult.beautified_chars || 0 }}</span>
          </div>
        </div>
        <pre ref="codeBlockRef" class="code-block"><code v-html="beautifyHtml"></code></pre>
      </div>

      <div v-if="autoRegexResult?.candidates?.length" class="code-area">
        <div class="sub-head">
          <h4>Auto Regex Candidates ({{ autoRegexResult?.candidate_count || 0 }})</h4>
          <span class="mono">JS API Path Ready</span>
        </div>
        <table class="task-table auto-regex-table">
          <thead>
            <tr>
              <th>#</th>
              <th>类型</th>
              <th>正则</th>
              <th>说明</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in autoRegexResult.candidates || []" :key="`auto-regex-${idx}`">
              <td>{{ idx + 1 }}</td>
              <td>{{ autoRegexLabel(item) }}</td>
              <td class="mono auto-pattern-cell" :title="item.pattern || '-'">{{ item.pattern || '-' }}</td>
              <td>{{ item.error || item.note || '-' }}</td>
              <td>
                <button class="ghost btn-sm" :disabled="!item.pattern" @click="onApplyAutoRegex(item.pattern)">应用</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="sub-block">
      <div class="sub-head">
        <h4>Preview Result ({{ previewResult?.count || 0 }})</h4>
        <div class="sub-head-actions">
          <button
            class="ghost"
            :disabled="savingPreview || !(previewResult?.endpoints?.length)"
            @click="onSavePreviewResult"
          >
            {{ savingPreview ? '保存中...' : '保存结果' }}
          </button>
          <button
            class="ghost"
            :disabled="!(previewResult?.endpoints?.length)"
            @click="onCopyPreviewEndpoints"
          >
            复制接口
          </button>
          <button
            class="ghost"
            :disabled="inferringBase || !(previewResult?.endpoints?.length)"
            @click="onInferBaseFromPreview"
          >
            {{ inferringBase ? '查询中...' : '查询 BaseURL / BaseAPI' }}
          </button>
        </div>
      </div>
      <table v-if="previewResult?.endpoints?.length" class="task-table">
        <thead>
          <tr>
            <th>#</th>
            <th>方法</th>
            <th>路径</th>
            <th>来源文件</th>
            <th>Source Line</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in previewResult.endpoints || []" :key="`${item.id}-${item.source_line}`">
            <td>{{ item.id }}</td>
            <td>{{ item.method }}</td>
            <td class="mono">{{ item.path }}</td>
            <td class="mono">{{ item.source_file }}</td>
            <td>{{ item.source_line }}</td>
            <td>
              <button
                class="ghost btn-sm"
                :disabled="!item.source_file"
                @click="onLocatePreviewEndpoint(item)"
              >
                定位
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">No preview result</div>
    </div>
  </section>
</template>

<style scoped>
.project-api-tab {
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

select,
input,
textarea {
  width: 100%;
  border: 1px solid #d3dfeb;
  border-radius: 9px;
  padding: 9px 10px;
  font-size: 13px;
  color: #1f3347;
  background: #fff;
}

select:focus,
input:focus,
textarea:focus {
  outline: none;
  border-color: #7db8df;
  box-shadow: 0 0 0 2px rgba(14, 132, 204, 0.14);
}

.js-file-select {
  border-color: #d3dfeb;
  background: transparent;
  box-shadow: none;
  font-weight: 400;
}

.api-grid {
  display: grid;
  gap: 10px;
  margin-top: 10px;
}

.snippet-grid {
  grid-template-columns: 1fr;
}

.snippet-field {
  display: grid;
  gap: 6px;
}

.snippet-input {
  min-height: 96px;
  resize: vertical;
}

.top-grid {
  grid-template-columns: 1.2fr 1.8fr;
  grid-template-areas:
    "target source"
    "reg actions";
  align-items: start;
}

.top-grid > :nth-child(1) {
  grid-area: target;
}

.top-grid > :nth-child(2) {
  grid-area: source;
}

.top-grid > :nth-child(3) {
  grid-area: reg;
}

.top-grid > :nth-child(4) {
  grid-area: actions;
}

.reg-table-wrap {
  width: 100%;
}

.reg-input-table {
  table-layout: fixed;
}

.reg-input-table td {
  padding: 8px;
}

.api-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.api-actions.vertical {
  flex-direction: row;
  align-items: center;
  justify-content: flex-start;
  flex-wrap: wrap;
}

.code-area {
  margin-top: 12px;
}

.code-head {
  margin-bottom: 8px;
}

.code-meta {
  flex-wrap: wrap;
}

.code-block,
.result-json {
  margin: 0;
  border: 1px solid #dbe6f1;
  border-radius: 10px;
  background: #f7fbff;
  padding: 10px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'JetBrains Mono', 'Cascadia Mono', Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
}

.code-block {
  min-height: 520px;
  max-height: 700px;
}

.result-json {
  max-height: 380px;
}

.auto-regex-table {
  margin-top: 10px;
  table-layout: fixed;
}

.auto-pattern-cell {
  white-space: normal;
  word-break: break-all;
}

.code-block :deep(.tok-comment) { color: #607d94; }
.code-block :deep(.tok-string) { color: #8e3f2b; }
.code-block :deep(.tok-number) { color: #7a2da8; }
.code-block :deep(.tok-literal) { color: #155f8c; }
.code-block :deep(.tok-keyword) { color: #0c63a0; font-weight: 700; }

@media (max-width: 980px) {
  .top-grid {
    grid-template-columns: 1fr;
    grid-template-areas:
      "target"
      "source"
      "reg"
      "actions";
  }

  .api-actions.vertical {
    flex-direction: row;
    align-items: stretch;
  }
}
</style>


