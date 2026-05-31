<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch } from 'vue'
import axios from 'axios'
import {
  fetchVueApiContext,
  startVueApiLlmAnalyze,
  pollVueApiLlmJob,
  saveVueApiLlmAnalysis,
  type ApiLlmAnalyzeResult,
} from '../../api/vueApi'

const props = defineProps<{
  domain: string
}>()

const copiedPath = ref('')
let copyTimer: ReturnType<typeof setTimeout> | null = null

function copyPath(raw: string) {
  const path = String(raw || '').trim()
  if (!path) return
  navigator.clipboard.writeText(path).catch(() => {})
  copiedPath.value = path
  if (copyTimer) clearTimeout(copyTimer)
  copyTimer = setTimeout(() => { copiedPath.value = '' }, 1500)
}

type InputSource = 'extract' | 'manual'

const PREVIEW_LIMIT = 12

const inputSource = ref<InputSource>('extract')
const manualInput = ref('')
const extractPaths = ref<string[]>([])
const extractLoading = ref(false)
const result = ref<ApiLlmAnalyzeResult | null>(null)
const resultSource = ref<InputSource | null>(null)
const isHistorical = ref(false)   // 当前展示的是历史结果
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const saveMessage = ref('')
const batchDone = ref(0)
const batchTotal = ref(0)

const jobId = ref('')
const jobLogs = ref<Array<{ time: string; message: string }>>([])
const pollErrorCount = ref(0)
let pollTimer: ReturnType<typeof setInterval> | null = null

// localStorage key per domain，刷新页面后仍能恢复正在进行的 job
function jobStorageKey(domain: string) {
  return `vuescan_llm_job_${domain}`
}
function saveJobId(domain: string, id: string) {
  try { localStorage.setItem(jobStorageKey(domain), id) } catch {}
}
function clearJobId(domain: string) {
  try { localStorage.removeItem(jobStorageKey(domain)) } catch {}
}
function loadJobId(domain: string): string {
  try { return localStorage.getItem(jobStorageKey(domain)) || '' } catch { return '' }
}

// 分析按钮文字：在等待 POST 返回时也立即显示"分析中"
const analyzeButtonText = computed(() => {
  if (!loading.value) return '开始分析'
  if (!jobId.value) return '正在提交...'
  if (batchTotal.value > 0) return `分析中 ${batchDone.value}/${batchTotal.value} 批`
  return '分析中...'
})

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function finishJob(domain: string) {
  stopPolling()
  clearJobId(domain)
}

async function pollJob() {
  if (!jobId.value) return
  const trackedId = jobId.value
  const domain = String(props.domain || '').trim()
  try {
    const job = await pollVueApiLlmJob(trackedId)
    if (jobId.value !== trackedId) return  // 用户已发起新分析，丢弃
    pollErrorCount.value = 0  // poll 成功，重置错误计数
    if (Array.isArray(job.logs)) jobLogs.value = job.logs
    if (job.status === 'completed') {
      finishJob(domain)
      if (jobId.value !== trackedId) return
      loading.value = false
      isHistorical.value = false
      const r = job.result as ApiLlmAnalyzeResult
      batchDone.value = r?.batch_done || 0
      batchTotal.value = r?.batch_total || 0
      const hasContent = r?.business_analysis || r?.api_analysis?.length || r?.web_analysis?.length || r?.unauthorized_suggestions?.length
      if (r?.error && !hasContent) {
        error.value = r.error
      } else if (!hasContent && !r?.error) {
        error.value = 'LLM 未返回有效分析结果（接口列表为空或 AI 无响应）'
      } else {
        result.value = r
        resultSource.value = inputSource.value
        if (r?.error) error.value = r.error
      }
    } else if (job.status === 'failed') {
      if (jobId.value !== trackedId) return
      finishJob(domain)
      loading.value = false
      error.value = job.error || 'LLM 分析失败'
    }
  } catch (e) {
    pollErrorCount.value += 1
    if (pollErrorCount.value >= 5) {
      // 连续 5 次 poll 失败，停止轮询并告知用户
      stopPolling()
      loading.value = false
      error.value = `轮询失败（${pollErrorCount.value}次），请刷新页面重试。错误：${e instanceof Error ? e.message : String(e)}`
    }
  }
}

function startPolling(id: string) {
  stopPolling()
  pollErrorCount.value = 0
  jobId.value = id
  pollJob()
  pollTimer = setInterval(pollJob, 3000)
}

function resolveError(err: unknown) {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: string } | undefined
    return data?.error || err.message || '请求失败'
  }
  if (err instanceof Error) return err.message
  return '未知错误'
}

function parseManualPaths(text: string): string[] {
  return text.split('\n').map(l => l.trim()).filter(Boolean)
}

async function loadExtractPaths() {
  const domain = String(props.domain || '').trim()
  if (!domain) { extractPaths.value = []; return }
  extractLoading.value = true
  try {
    const ctx = await fetchVueApiContext(domain)
    const endpoints = Array.isArray(ctx.extract_result?.endpoints) ? ctx.extract_result!.endpoints : []
    extractPaths.value = [
      ...new Set(
        endpoints
          .map((ep: { path?: string; url?: string }) => String(ep.path || ep.url || '').trim())
          .filter((p: string) => Boolean(p))
      ),
    ]
    // 只在无 job 追踪且无当前结果时加载历史结果，且标记为历史
    if (!loading.value && !jobId.value && !result.value && ctx.llm_analysis && Object.keys(ctx.llm_analysis).length > 0) {
      const r = ctx.llm_analysis as unknown as ApiLlmAnalyzeResult
      const hasContent = r?.business_analysis || r?.api_analysis?.length || r?.web_analysis?.length || r?.unauthorized_suggestions?.length
      if (hasContent) {
        result.value = r
        resultSource.value = 'extract'
        isHistorical.value = true
      }
    }
  } catch {
    extractPaths.value = []
  } finally {
    extractLoading.value = false
  }
}

// 页面加载/切换 tab 时，恢复正在进行的 job
async function tryReconnectJob() {
  const domain = String(props.domain || '').trim()
  if (!domain || loading.value) return
  const savedId = loadJobId(domain)
  if (!savedId) return
  try {
    const job = await pollVueApiLlmJob(savedId)
    if (job.status === 'running') {
      loading.value = true
      isHistorical.value = false
      result.value = null
      error.value = ''
      if (Array.isArray(job.logs)) jobLogs.value = job.logs
      startPolling(savedId)
    } else {
      clearJobId(domain)
    }
  } catch {
    clearJobId(domain)
  }
}

async function onAnalyze() {
  const domain = String(props.domain || '').trim()
  if (!domain) { error.value = '项目域名缺失'; return }

  if (loading.value) return  // 已在分析中，忽略重复点击

  let paths: string[] | undefined
  if (inputSource.value === 'manual') {
    paths = parseManualPaths(manualInput.value)
    if (!paths.length) { error.value = '请输入至少一条接口路径'; return }
  }

  stopPolling()
  loading.value = true
  isHistorical.value = false
  error.value = ''
  result.value = null
  resultSource.value = null
  batchDone.value = 0
  batchTotal.value = 0
  jobId.value = ''
  jobLogs.value = []

  try {
    const { job_id } = await startVueApiLlmAnalyze(domain, paths)
    if (!job_id) throw new Error('未获取到 job_id')
    saveJobId(domain, job_id)  // 持久化，刷新后可恢复
    startPolling(job_id)
  } catch (err) {
    loading.value = false
    clearJobId(domain)
    error.value = resolveError(err)
  }
}

async function onSave() {
  if (!result.value) return
  const domain = String(props.domain || '').trim()
  saving.value = true
  saveMessage.value = ''
  error.value = ''
  try {
    await saveVueApiLlmAnalysis(domain, result.value)
    saveMessage.value = '已保存'
    isHistorical.value = false
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    saving.value = false
  }
}

watch(
  () => props.domain,
  () => {
    stopPolling()
    result.value = null
    isHistorical.value = false
    error.value = ''
    saveMessage.value = ''
    batchDone.value = 0
    batchTotal.value = 0
    jobId.value = ''
    jobLogs.value = []
    manualInput.value = ''
    inputSource.value = 'extract'
    loading.value = false
    loadExtractPaths()
    tryReconnectJob()
  },
)

onMounted(async () => {
  await tryReconnectJob()
  if (!loading.value) loadExtractPaths()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <section class="llm-tab">
    <div class="llm-toolbar">
      <h4>LLM 安全分析</h4>
      <button :disabled="loading" class="analyze-btn" :class="{ 'is-loading': loading }" @click="onAnalyze">
        <span v-if="loading" class="btn-spinner" />
        {{ analyzeButtonText }}
      </button>
    </div>

    <!-- 来源切换 -->
    <div class="source-bar">
      <button
        class="source-btn"
        :class="{ active: inputSource === 'extract' }"
        @click="inputSource = 'extract'"
      >从正则提取</button>
      <button
        class="source-btn"
        :class="{ active: inputSource === 'manual' }"
        @click="inputSource = 'manual'"
      >手动输入</button>
    </div>

    <!-- 正则提取预览 -->
    <div v-if="inputSource === 'extract'" class="extract-preview">
      <div v-if="extractLoading" class="extract-empty">加载中...</div>
      <template v-else-if="extractPaths.length">
        <div class="extract-preview-head">
          <span>已保存 {{ extractPaths.length }} 条接口</span>
          <span class="extract-preview-hint">（预览前 {{ Math.min(extractPaths.length, PREVIEW_LIMIT) }} 条）</span>
        </div>
        <div class="extract-path-list">
          <span
            v-for="(path, idx) in extractPaths.slice(0, PREVIEW_LIMIT)"
            :key="idx"
            class="extract-path-chip mono"
          >{{ path }}</span>
          <span v-if="extractPaths.length > PREVIEW_LIMIT" class="extract-path-more">
            +{{ extractPaths.length - PREVIEW_LIMIT }} 条...
          </span>
        </div>
      </template>
      <div v-else class="extract-empty">
        暂无已保存的接口，请先到「正则提取」tab 检查正则是否正确并保存结果。
      </div>
    </div>

    <!-- 手动输入框 -->
    <div v-if="inputSource === 'manual'" class="manual-input-wrap">
      <textarea
        v-model="manualInput"
        class="manual-textarea"
        placeholder="每行一个接口路径，例如：&#10;/api/user/getUserInfo&#10;/api/admin/register&#10;/api/export/userInfo"
        rows="8"
      />
      <div class="manual-hint">共 {{ parseManualPaths(manualInput).length }} 条</div>
    </div>

    <div v-if="error" class="notice error">{{ error }}</div>

    <div v-if="loading" class="llm-loading">
      <div class="llm-loading-spinner" />
      <div class="llm-loading-info">
        <div class="llm-loading-title">
          <strong>分析进行中</strong>
          <span v-if="batchTotal > 0" class="llm-batch-badge">{{ batchDone }}/{{ batchTotal }} 批</span>
        </div>
        <span class="llm-loading-hint">接口较多时需 3～8 分钟，请勿重复点击，关闭页面后分析仍在后台运行</span>
        <span v-if="jobId" class="llm-job-id">任务 {{ jobId }}</span>
        <div v-if="jobLogs.length" class="llm-job-logs">
          <div v-for="(log, i) in jobLogs" :key="i" class="llm-job-log">{{ log.message }}</div>
        </div>
        <button v-if="jobId" class="ghost llm-refresh-btn" @click="pollJob">手动刷新状态</button>
      </div>
    </div>

    <template v-else-if="result">
      <!-- 历史结果提示条 -->
      <div v-if="isHistorical" class="llm-historical-bar">
        以下为上次分析留存的结果，点击「开始分析」可获取最新结果
      </div>

      <!-- 结果操作栏 -->
      <div class="result-actions">
        <div class="result-actions-left">
          <span v-if="batchTotal > 1" class="batch-info-inline">
            共 {{ batchDone }}/{{ batchTotal }} 批 · {{ result.api_analysis?.length || 0 }} 条接口
          </span>
        </div>
        <div class="result-actions-right">
          <span v-if="saveMessage" class="save-message">{{ saveMessage }}</span>
          <button class="ghost" :disabled="saving" @click="onSave">
            {{ saving ? '保存中...' : '保存结果' }}
          </button>
        </div>
      </div>

      <!-- 业务分析 -->
      <section class="llm-block">
        <div class="llm-block-head">
          <h5>业务分析</h5>
        </div>
        <div class="llm-prose">{{ result.business_analysis || '（无内容）' }}</div>
      </section>

      <!-- Web 漏洞分析 -->
      <section class="llm-block">
        <div class="llm-block-head">
          <h5>Web 漏洞分析</h5>
          <span class="llm-count">{{ result.web_analysis?.length || 0 }} 项</span>
        </div>
        <table v-if="result.web_analysis?.length" class="task-table llm-table">
          <thead>
            <tr>
              <th class="col-vuln">漏洞类型</th>
              <th class="col-vuln-paths">涉及接口</th>
              <th>利用思路</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in result.web_analysis" :key="`web-${idx}`">
              <td class="col-vuln vuln-tag">{{ item.vuln || '-' }}</td>
              <td class="col-vuln-paths">
                <button
                  v-for="(p, pi) in item.paths"
                  :key="`wp-${pi}`"
                  type="button"
                  class="extract-path-chip mono path-jump"
                  @click.stop="copyPath(p)"
                >{{ copiedPath === p ? '已复制' : p }}</button>
                <span v-if="!item.paths?.length">-</span>
              </td>
              <td>{{ item.detail || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">暂无 Web 漏洞分析</div>
      </section>

      <!-- 攻击链 -->
      <section v-if="result.attack_chains?.length" class="llm-block">
        <div class="llm-block-head">
          <h5>攻击链 / 组合拳</h5>
          <span class="llm-count">{{ result.attack_chains.length }} 条</span>
        </div>
        <div class="chain-list">
          <article v-for="(chain, idx) in result.attack_chains" :key="`chain-${idx}`" class="chain-card">
            <div class="chain-title">{{ chain.title || '-' }}</div>
            <div class="chain-steps">
              <span
                v-for="(step, si) in chain.steps"
                :key="`step-${si}`"
                class="chain-step mono"
              >{{ step }}</span>
              <span v-if="!chain.steps?.length" class="chain-step">-</span>
            </div>
            <div class="chain-impact">{{ chain.impact || '-' }}</div>
          </article>
        </div>
      </section>

      <!-- 未授权建议 -->
      <section class="llm-block">
        <div class="llm-block-head">
          <h5>未授权建议</h5>
          <span class="llm-count">{{ result.unauthorized_suggestions?.length || 0 }} 条</span>
        </div>
        <table v-if="result.unauthorized_suggestions?.length" class="task-table llm-table">
          <thead>
            <tr>
              <th class="col-path">接口路径</th>
              <th>风险说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in result.unauthorized_suggestions" :key="`unauth-${idx}`">
              <td class="mono col-path path-jump" @click.stop="copyPath(item.path)">{{ copiedPath === item.path ? '已复制' : (item.path || '-') }}</td>
              <td>{{ item.reason || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">暂无未授权风险建议</div>
      </section>

      <!-- 接口分析 -->
      <section class="llm-block">
        <div class="llm-block-head">
          <h5>接口分析</h5>
          <span class="llm-count">{{ result.api_analysis?.length || 0 }} 条</span>
        </div>
        <table v-if="result.api_analysis?.length" class="task-table llm-table">
          <thead>
            <tr>
              <th class="col-api">API</th>
              <th class="col-llm">业务含义</th>
              <th>攻击思路</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in result.api_analysis" :key="`api-${idx}`">
              <td class="mono col-api path-jump" @click.stop="copyPath(item.api)">{{ copiedPath === item.api ? '已复制' : (item.api || '-') }}</td>
              <td class="col-llm">{{ item.llm || '-' }}</td>
              <td class="col-attack">{{ item.attack || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">暂无接口分析结果</div>
      </section>
    </template>

  </section>
</template>

<style scoped>
.llm-tab {
  display: grid;
  gap: 14px;
}

.llm-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.llm-toolbar h4 { margin: 0; }

.llm-toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.llm-hint {
  color: #6b8096;
  font-size: 12px;
}

.analyze-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.analyze-btn.is-loading {
  background: #0a5080;
  cursor: not-allowed;
  opacity: 0.9;
}

.btn-spinner {
  width: 13px;
  height: 13px;
  border: 2px solid rgba(255,255,255,0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex-shrink: 0;
}

.llm-historical-bar {
  padding: 8px 14px;
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 8px;
  font-size: 12px;
  color: #7a5800;
}

.llm-loading {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 20px;
  color: #2a4a62;
  font-size: 13px;
  border: 1px solid #a8cfe8;
  border-radius: 10px;
  background: #eef6fc;
}

.llm-loading-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.llm-loading-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #0d4a70;
}

.llm-batch-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  background: #0d5f99;
  color: #fff;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.llm-loading-hint {
  font-size: 12px;
  color: #3a6070;
  line-height: 1.6;
}

.llm-job-id {
  font-size: 11px;
  color: #8aa5bb;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.llm-job-logs {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: #1a5070;
  margin-top: 4px;
  padding: 8px 10px;
  background: #d8edf8;
  border-radius: 6px;
}

.llm-job-log::before {
  content: '› ';
  color: #3a8fbe;
}

.llm-refresh-btn {
  margin-top: 6px;
  align-self: flex-start;
  font-size: 12px;
  padding: 4px 12px;
}

.llm-loading-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid #c5ddf0;
  border-top-color: #0d8ed9;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.batch-info {
  padding: 8px 12px;
  background: #eef7ff;
  border: 1px solid #c5ddf0;
  border-radius: 8px;
  font-size: 12px;
  color: #2a5f82;
}

.llm-block {
  border: 1px solid #dce8f2;
  border-radius: 10px;
  background: #fcfdff;
  padding: 12px;
  display: grid;
  gap: 10px;
}

.llm-block-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.llm-block-head h5 {
  margin: 0;
  font-size: 14px;
  color: #1a3a52;
}

.llm-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 1px 8px;
  border-radius: 999px;
  background: #e5f0fb;
  color: #0d5f99;
  font-size: 11px;
  font-weight: 700;
}

.llm-prose {
  font-size: 13px;
  line-height: 1.7;
  color: #1e3347;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 10px;
  background: #f4f8fc;
  border: 1px solid #e0eaf4;
  border-radius: 8px;
}

.chain-list {
  display: grid;
  gap: 10px;
}

.chain-card {
  border: 1px solid #dce8f2;
  border-radius: 8px;
  padding: 10px 12px;
  display: grid;
  gap: 6px;
  background: #f8fbff;
}

.chain-title {
  font-size: 13px;
  font-weight: 700;
  color: #8a2823;
}

.chain-steps {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.chain-step {
  display: inline-flex;
  align-items: center;
  background: #fff;
  border: 1px solid #c9deee;
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 12px;
  color: #1a4060;
}

.chain-step + .chain-step::before {
  content: '→';
  margin-right: 6px;
  color: #7d9db5;
  font-style: normal;
}

.chain-impact {
  font-size: 12px;
  color: #5a6f80;
  line-height: 1.5;
}

.llm-table {
  width: 100%;
  table-layout: fixed;
}

.col-path { width: 28%; white-space: normal; word-break: break-all; }
.col-api  { width: 25%; white-space: normal; word-break: break-all; }
.col-llm  { width: 22%; }
.col-attack { white-space: normal; word-break: break-word; }
.col-vuln { width: 16%; white-space: nowrap; }
.col-vuln-paths { width: 32%; white-space: normal; word-break: break-all; }
.vuln-tag { font-weight: 700; color: #8a2823; }

.llm-table td {
  vertical-align: top;
  font-size: 13px;
  line-height: 1.55;
}

.llm-empty-hint {
  padding: 20px;
  color: #5a7590;
  font-size: 13px;
  line-height: 1.7;
  border: 1px dashed #c5d9e8;
  border-radius: 10px;
  background: #f7fbff;
}

.llm-empty-hint p { margin: 0 0 8px; }
.llm-empty-hint p:last-child { margin: 0; }

.source-bar {
  display: flex;
  gap: 0;
  border: 1px solid #d0e0ed;
  border-radius: 8px;
  overflow: hidden;
  width: fit-content;
}

.source-btn {
  padding: 7px 18px;
  font-size: 13px;
  font-weight: 600;
  color: #4a6880;
  background: #f5f9fd;
  border: none;
  border-radius: 0;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.source-btn + .source-btn {
  border-left: 1px solid #d0e0ed;
}

.source-btn:hover {
  background: #eaf3fb;
  color: #1f4868;
}

.source-btn.active {
  background: #0d5f99;
  color: #fff;
}

.manual-input-wrap {
  display: grid;
  gap: 6px;
}

.manual-textarea {
  width: 100%;
  border: 1px solid #d3dfeb;
  border-radius: 9px;
  padding: 10px 12px;
  font-size: 13px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  color: #1f3347;
  background: #fff;
  resize: vertical;
  line-height: 1.6;
}

.manual-textarea:focus {
  outline: none;
  border-color: #7db8df;
  box-shadow: 0 0 0 2px rgba(14, 132, 204, 0.14);
}

.manual-hint {
  font-size: 12px;
  color: #6b8096;
  text-align: right;
}

.extract-preview {
  border: 1px solid #dce8f2;
  border-radius: 9px;
  padding: 10px 12px;
  background: #f8fbff;
  display: grid;
  gap: 8px;
}

.extract-preview-head {
  font-size: 12px;
  color: #2a5f82;
  font-weight: 600;
}

.extract-preview-hint {
  font-weight: 400;
  color: #6b8096;
  margin-left: 6px;
}

.extract-path-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.extract-path-chip {
  display: inline-flex;
  padding: 2px 8px;
  border: 1px solid #c9ddef;
  border-radius: 6px;
  background: #fff;
  color: #1a4060;
  font-size: 12px;
  white-space: nowrap;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.extract-path-more {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 12px;
  color: #6b8096;
}

.extract-empty {
  font-size: 13px;
  color: #6b8096;
  padding: 4px 0;
}

.result-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.result-actions-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.result-actions-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.batch-info-inline {
  font-size: 12px;
  color: #2a5f82;
  padding: 6px 10px;
  background: #eef7ff;
  border: 1px solid #c5ddf0;
  border-radius: 6px;
}

.save-message {
  font-size: 12px;
  color: #0f6b45;
  font-weight: 600;
}

.path-jump {
  cursor: pointer;
  color: #1a7dc8;
  text-decoration: underline;
  text-underline-offset: 2px;
  border: none;
  outline: none;
  font: inherit;
}

.path-jump:hover {
  color: #0f5fa0;
  background: #e8f3fc;
}
</style>
