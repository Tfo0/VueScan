<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import {
  createVueChunkProject,
  deleteVueChunkProject,
  fetchVueChunkProjects,
  pauseVueChunkJob,
  retryVueChunkProject,
  resumeVueChunkJob,
  scanVueChunkProject,
  stopVueChunkJob,
  updateVueChunkProjectTitle,
  type ProjectItem,
} from '../api/vueChunk'

const router = useRouter()

const projects = ref<ProjectItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const totalPages = ref(0)
const searchInput = ref('')
const searchKeyword = ref('')
const hasRunningJobs = ref(false)
const loading = ref(false)
const modalSubmitting = ref<'create' | ''>('')
const retryingDomain = ref('')
const scanningDomain = ref('')
const deletingDomain = ref('')
const editingTitleDomain = ref('')
const editingTitleDraft = ref('')
const pausingDomain = ref('')
const resumingDomain = ref('')
const stoppingDomain = ref('')
const showCreateModal = ref(false)
const formTargetUrl = ref('')
const formSource = ref('manual')
const formDetectRoutes = ref(true)
const formDetectJs = ref(true)
const formDetectRequest = ref(true)
const formAutoPipeline = ref(true)
const message = ref('')
const error = ref('')
let pollTimer: number | undefined
let pollBusy = false

function resolveError(err: unknown) {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: string } | undefined
    return data?.error || err.message || '请求失败'
  }
  if (err instanceof Error) return err.message
  return '未知错误'
}

function statusClass(status: string) {
  const value = String(status || '').toLowerCase()
  if (value === 'done') return 'done'
  if (value === 'failed') return 'failed'
  if (value === 'running') return 'running'
  if (value === 'queued') return 'queued'
  return 'idle'
}

function statusText(status: string) {
  const value = String(status || 'idle').toLowerCase()
  if (value === 'done') return '已完成'
  if (value === 'failed') return '失败'
  if (value === 'running') return '运行中'
  if (value === 'queued') return '排队中'
  if (value === 'paused') return '已暂停'
  if (value === 'idle' || !value) return '空闲'
  return value
}

function savedStatusText(project: ProjectItem) {
  const count = Math.max(0, Number(project?.saved_result_count || 0))
  if (count <= 0) return ''
  return `已保存 ${count}`
}

function valueLevelClass(project: ProjectItem) {
  const level = String(project?.request_value_level || '').toLowerCase()
  if (level === 'high') return 'high'
  if (level === 'medium') return 'medium'
  if (level === 'low') return 'low'
  return ''
}

function valueLevelText(project: ProjectItem) {
  const label = String(project?.request_value_label || '').trim()
  if (label) return `${label}价值`
  const level = String(project?.request_value_level || '').toLowerCase()
  if (level === 'high') return '高价值'
  if (level === 'medium') return '中价值'
  if (level === 'low') return '低价值'
  return ''
}

function rowNo(index: number) {
  return (page.value - 1) * pageSize.value + index + 1
}

function firstSeedUrl(project: ProjectItem) {
  for (const item of project.seed_urls || []) {
    const value = String(item || '').trim()
    if (value) return value
  }
  return ''
}

async function loadProjects(options?: { silent?: boolean } | Event) {
  const silent =
    Boolean(options) &&
    typeof options === 'object' &&
    'silent' in options &&
    Boolean((options as { silent?: boolean }).silent)
  if (!silent) {
    loading.value = true
    error.value = ''
  }
  try {
    const payload = await fetchVueChunkProjects({
      q: searchKeyword.value,
      page: page.value,
      pageSize: pageSize.value,
      sort: 'updated_desc',
    })
    projects.value = payload.projects
    total.value = payload.total
    page.value = payload.page
    pageSize.value = payload.pageSize
    totalPages.value = payload.totalPages
    hasRunningJobs.value = payload.hasRunningJobs
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

function openCreateModal() {
  error.value = ''
  message.value = ''
  resetCreateForm()
  showCreateModal.value = true
}

function closeCreateModal() {
  if (modalSubmitting.value) return
  showCreateModal.value = false
}

function resetCreateForm() {
  formTargetUrl.value = ''
  formSource.value = 'manual'
  formDetectRoutes.value = true
  formDetectJs.value = true
  formDetectRequest.value = true
  formAutoPipeline.value = true
}

async function onCreateProject() {
  const targetUrl = formTargetUrl.value.trim()
  if (!targetUrl) {
    error.value = '请输入目标 URL'
    return
  }

  modalSubmitting.value = 'create'
  error.value = ''
  message.value = ''
  try {
    const autoPipeline = Boolean(formAutoPipeline.value)
    const created = await createVueChunkProject({
      targetUrl,
      source: formSource.value.trim() || 'manual',
      concurrency: 5,
      detectRoutes: autoPipeline ? true : formDetectRoutes.value,
      detectJs: autoPipeline ? true : formDetectJs.value,
      detectRequest: autoPipeline ? true : formDetectRequest.value,
      autoPipeline,
    })
    const createdDomain = String(created.project?.domain || '').trim()
    showCreateModal.value = false
    resetCreateForm()
    page.value = 1
    message.value = autoPipeline
      ? `自动化任务已创建：${createdDomain || '新项目'}`
      : `项目任务已创建：${createdDomain || '新项目'}`
    void loadProjects({ silent: true })
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    modalSubmitting.value = ''
  }
}

async function onRetryProject(project: ProjectItem) {
  retryingDomain.value = project.domain
  error.value = ''
  message.value = ''
  try {
    let detectRoutes = project.sync?.detect_routes ?? true
    let detectJs = project.sync?.detect_js ?? true
    let detectRequest = project.sync?.detect_request ?? true
    if (!detectRoutes && !detectJs && !detectRequest) {
      detectRoutes = true
      detectJs = true
      detectRequest = true
    }
    await retryVueChunkProject(project.domain, {
      targetUrl: project.sync?.target_url || firstSeedUrl(project),
      source: 'vueChunk_retry',
      concurrency: Number(project.sync?.concurrency || 5),
      detectRoutes,
      detectJs,
      detectRequest,
    })
    message.value = `重试任务已创建：${project.domain}`
    await loadProjects()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    retryingDomain.value = ''
  }
}

async function onPauseProjectSync(project: ProjectItem) {
  const jobId = String(project?.sync?.job_id || '').trim()
  const domain = String(project?.domain || '').trim()
  if (!jobId || !domain) return
  pausingDomain.value = domain
  error.value = ''
  message.value = ''
  try {
    await pauseVueChunkJob(jobId)
    message.value = `已暂停：${domain}`
    await loadProjects()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    pausingDomain.value = ''
  }
}

async function onResumeProjectSync(project: ProjectItem) {
  const jobId = String(project?.sync?.job_id || '').trim()
  const domain = String(project?.domain || '').trim()
  if (!jobId || !domain) return
  resumingDomain.value = domain
  error.value = ''
  message.value = ''
  try {
    await resumeVueChunkJob(jobId)
    message.value = `已继续：${domain}`
    await loadProjects()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    resumingDomain.value = ''
  }
}

async function onStopProjectSync(project: ProjectItem) {
  const jobId = String(project?.sync?.job_id || '').trim()
  const domain = String(project?.domain || '').trim()
  if (!jobId || !domain) return
  if (!window.confirm(`确认停止同步任务：${domain}？`)) return
  stoppingDomain.value = domain
  error.value = ''
  message.value = ''
  try {
    await stopVueChunkJob(jobId)
    message.value = `已提交停止：${domain}`
    await loadProjects()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    stoppingDomain.value = ''
  }
}

async function onScanProject(project: ProjectItem) {
  const domain = String(project?.domain || '').trim()
  if (!domain) return
  scanningDomain.value = domain
  error.value = ''
  message.value = ''
  try {
    await scanVueChunkProject(domain, {
      targetUrl: project.sync?.target_url || firstSeedUrl(project),
      source: 'vueChunk_scan',
    })
    message.value = `扫描任务已创建：${domain}`
    await loadProjects()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    scanningDomain.value = ''
  }
}

async function onSearch() {
  searchKeyword.value = searchInput.value.trim()
  page.value = 1
  await loadProjects()
}

async function onResetSearch() {
  searchInput.value = ''
  searchKeyword.value = ''
  page.value = 1
  await loadProjects()
}

async function onPrevPage() {
  if (page.value <= 1 || loading.value) return
  page.value -= 1
  await loadProjects()
}

async function onNextPage() {
  const maxPage = Math.max(1, totalPages.value)
  if (page.value >= maxPage || loading.value) return
  page.value += 1
  await loadProjects()
}

async function onPageSizeChange(event: Event) {
  const target = event.target as HTMLSelectElement
  const value = Math.max(1, Number(target.value || 10))
  pageSize.value = value
  page.value = 1
  await loadProjects()
}

async function onOpenProject(domain: string) {
  const value = String(domain || '').trim()
  if (!value) return
  await router.push(`/vueChunk/projects/${encodeURIComponent(value)}`)
}

async function onDeleteProject(project: ProjectItem) {
  if (!project?.domain) return
  if (!window.confirm(`确认删除项目：${project.domain}？`)) return
  deletingDomain.value = project.domain
  error.value = ''
  message.value = ''
  try {
    await deleteVueChunkProject(project.domain, { removeFiles: true })
    message.value = `项目已删除：${project.domain}`
    if (projects.value.length <= 1 && page.value > 1) {
      page.value -= 1
    }
    await loadProjects()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    deletingDomain.value = ''
  }
}

function onEditProjectTitle(project: ProjectItem) {
  const domain = String(project?.domain || '').trim()
  if (!domain) return
  editingTitleDomain.value = domain
  editingTitleDraft.value = String(project?.title || '').trim()
  error.value = ''
  message.value = ''
}

function onCancelEditProjectTitle() {
  editingTitleDomain.value = ''
  editingTitleDraft.value = ''
}

async function onSaveProjectTitle(project: ProjectItem) {
  const domain = String(project?.domain || '').trim()
  if (!domain) return
  error.value = ''
  message.value = ''
  try {
    editingTitleDomain.value = domain
    await updateVueChunkProjectTitle(domain, { title: editingTitleDraft.value.trim() })
    message.value = `标题已更新：${domain}`
    onCancelEditProjectTitle()
    await loadProjects()
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    if (editingTitleDomain.value === domain) {
      editingTitleDomain.value = ''
    }
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
      await loadProjects({ silent: true })
    } finally {
      pollBusy = false
    }
  }, 3000)
}

onMounted(async () => {
  await loadProjects()
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
      <div class="panel-head">
        <h3>项目列表</h3>
        <div class="panel-head-actions">
          <button @click="openCreateModal">创建项目</button>
          <button class="ghost" :disabled="loading" @click="loadProjects">刷新</button>
        </div>
      </div>

      <div class="chunk-toolbar">
        <input
          v-model="searchInput"
          type="text"
          placeholder="搜索域名"
          @keyup.enter="onSearch"
        />
        <button class="ghost" :disabled="loading" @click="onSearch">搜索</button>
        <button class="ghost" :disabled="loading" @click="onResetSearch">重置</button>
      </div>

      <div v-if="loading" class="empty">加载中...</div>
      <table v-else-if="projects.length > 0" class="task-table">
        <thead>
          <tr>
            <th class="index-col">序号</th>
            <th>域名</th>
            <th class="title-col">网页标题</th>
            <th>路由数</th>
            <th>JS 数</th>
            <th>状态</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(project, index) in projects" :key="project.domain">
            <td class="index-col">{{ rowNo(index) }}</td>
            <td class="name">
              <a href="#" class="domain-link" @click.prevent="onOpenProject(project.domain)">
                {{ project.domain }}
              </a>
            </td>
            <td
              class="title-col editable-title"
              :title="project.title || '点击填写标题'"
              @dblclick="onEditProjectTitle(project)"
            >
              <template v-if="editingTitleDomain === project.domain">
                <input
                  v-model="editingTitleDraft"
                  class="title-inline-input"
                  type="text"
                  placeholder="请输入网页标题"
                  @click.stop
                  @keyup.enter="onSaveProjectTitle(project)"
                  @keyup.esc="onCancelEditProjectTitle"
                  @blur="onCancelEditProjectTitle"
                />
              </template>
              <template v-else>
                <span v-if="project.title">{{ project.title }}</span>
                <span
                  v-else
                  class="title-placeholder"
                  @click.stop="onEditProjectTitle(project)"
                >
                  点击填写标题
                </span>
              </template>
            </td>
            <td>{{ project.route_count }}</td>
            <td>{{ project.js_count }}</td>
            <td>
              <div class="status-cell">
                <span
                  class="status-pill"
                  :class="statusClass(project.sync_status)"
                  :title="project.sync_error || ''"
                >
                  {{ statusText(project.sync_status) }}
                </span>
                <span
                  v-if="project.request_value_level"
                  class="value-pill"
                  :class="valueLevelClass(project)"
                  :title="project.request_value_reason || ''"
                >
                  {{ valueLevelText(project) }}
                </span>
                <span v-if="project.saved_result_count > 0" class="saved-pill">
                  {{ savedStatusText(project) }}
                </span>
              </div>
            </td>
            <td>{{ project.last_activity_at || project.updated_at || '-' }}</td>
            <td class="action-col">
              <button
                class="ghost"
                :disabled="
                  scanningDomain === project.domain ||
                  project.sync_status === 'running' ||
                  project.sync_status === 'queued' ||
                  project.sync_status === 'paused'
                "
                @click="onScanProject(project)"
              >
                {{ scanningDomain === project.domain ? '扫描中...' : '扫描' }}
              </button>
              <button
                class="ghost"
                :disabled="
                  retryingDomain === project.domain ||
                  project.sync_status === 'running' ||
                  project.sync_status === 'queued' ||
                  project.sync_status === 'paused'
                "
                @click="onRetryProject(project)"
              >
                {{ retryingDomain === project.domain ? '重试中...' : '重试' }}
              </button>
              <button
                v-if="project.sync?.job_id && project.sync_status === 'running'"
                class="ghost"
                :disabled="pausingDomain === project.domain"
                @click="onPauseProjectSync(project)"
              >
                {{ pausingDomain === project.domain ? '暂停中...' : '暂停' }}
              </button>
              <button
                v-if="project.sync?.job_id && project.sync_status === 'paused'"
                class="ghost"
                :disabled="resumingDomain === project.domain"
                @click="onResumeProjectSync(project)"
              >
                {{ resumingDomain === project.domain ? '恢复中...' : '恢复' }}
              </button>
              <button
                v-if="
                  project.sync?.job_id &&
                  (project.sync_status === 'running' ||
                    project.sync_status === 'queued' ||
                    project.sync_status === 'paused')
                "
                class="ghost"
                :disabled="stoppingDomain === project.domain"
                @click="onStopProjectSync(project)"
              >
                {{ stoppingDomain === project.domain ? '停止中...' : '停止' }}
              </button>
              <button
                class="delete-btn"
                :disabled="
                  deletingDomain === project.domain ||
                  pausingDomain === project.domain ||
                  resumingDomain === project.domain ||
                  stoppingDomain === project.domain
                "
                @click="onDeleteProject(project)"
              >
                {{ deletingDomain === project.domain ? '删除中...' : '删除' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">暂无项目</div>

      <div class="pager">
        <div class="pager-text">共 {{ total }} 条 | 第 {{ page }} / {{ totalPages || 1 }} 页</div>
        <div class="pager-actions">
          <label>
            每页
            <select :value="pageSize" @change="onPageSizeChange">
              <option :value="10">10</option>
              <option :value="20">20</option>
              <option :value="50">50</option>
            </select>
          </label>
          <button class="ghost" :disabled="loading || page <= 1" @click="onPrevPage">上一页</button>
          <button
            class="ghost"
            :disabled="loading || page >= Math.max(1, totalPages)"
            @click="onNextPage"
          >
            下一页
          </button>
        </div>
      </div>
    </section>

    <div v-if="showCreateModal" class="modal-mask" @click.self="closeCreateModal">
      <div class="modal-card">
        <div class="panel-head">
          <h3>创建项目</h3>
          <button class="ghost" :disabled="Boolean(modalSubmitting)" @click="closeCreateModal">关闭</button>
        </div>
        <div class="form-grid modal-form-grid">
          <div>
            <label>目标 URL</label>
            <input
              v-model="formTargetUrl"
              type="text"
              placeholder="https://example.com"
            />
          </div>
        </div>
        <div class="chunk-checks">
          <label class="check-line">
            <input v-model="formAutoPipeline" type="checkbox" />
            <span>自动化</span>
          </label>
          <label class="check-line">
            <input v-model="formDetectRoutes" type="checkbox" :disabled="formAutoPipeline" />
            <span>路由检测</span>
          </label>
          <label class="check-line">
            <input v-model="formDetectJs" type="checkbox" :disabled="formAutoPipeline" />
            <span>JS 检测</span>
          </label>
          <label class="check-line">
            <input v-model="formDetectRequest" type="checkbox" :disabled="formAutoPipeline" />
            <span>请求检测</span>
          </label>
        </div>
        <div v-if="formAutoPipeline" class="chunk-note">
          自动化已启用：将在后台依次执行路由检测、JS 检测、请求检测、API 正则提取与基址推断。
        </div>
        <div class="form-actions">
          <button class="ghost" :disabled="Boolean(modalSubmitting)" @click="onCreateProject">
            {{ modalSubmitting === 'create' ? '创建中...' : '创建项目' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.chunk-toolbar {
  margin-bottom: 10px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.chunk-toolbar input {
  max-width: 320px;
}

.domain-link {
  font-size: 16px;
  font-weight: 700;
}

.index-col {
  width: 48px;
  min-width: 48px;
  text-align: center;
}

.title-col {
  max-width: 280px;
  color: #4a6177;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.editable-title {
  cursor: pointer;
}

.title-inline-input {
  width: 100%;
  min-width: 0;
  padding: 4px 6px;
  border: 1px solid #c7d6e4;
  border-radius: 6px;
  background: #fff;
  color: #31465a;
}

.title-placeholder {
  color: #7b91a7;
  text-decoration: underline;
  text-decoration-style: dashed;
  text-underline-offset: 2px;
}

.action-col {
  white-space: nowrap;
}

.action-col button {
  margin-right: 6px;
}

.action-col button:last-child {
  margin-right: 0;
}

.status-cell {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

.saved-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: #edf7ef;
  color: #2f6b3a;
  border: 1px solid #cde5d2;
  font-size: 12px;
}

.value-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid #d7e0ea;
  background: #f5f8fb;
  color: #395066;
}

.value-pill.high {
  background: #fff1f1;
  border-color: #f3c8c8;
  color: #9e2c2c;
}

.value-pill.medium {
  background: #fff7e8;
  border-color: #efd6a6;
  color: #9a6511;
}

.value-pill.low {
  background: #edf3fb;
  border-color: #c9d9ee;
  color: #3f607f;
}

.pager {
  margin-top: 10px;
  border-top: 1px solid #e6edf4;
  padding-top: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.pager-text {
  color: #54697d;
  font-size: 12px;
}

.pager-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pager-actions label {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.pager-actions select {
  border: 1px solid #dce4ee;
  border-radius: 6px;
  padding: 5px 6px;
  background: #fff;
}

.chunk-checks {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.check-line {
  margin: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #31465a;
}

.check-line input {
  width: auto;
}

.chunk-note {
  margin-top: 8px;
  color: #5e758b;
  font-size: 12px;
}

.status-pill.queued {
  background: #fff6e4;
  color: #916207;
}

@media (max-width: 980px) {
  .chunk-toolbar {
    flex-wrap: wrap;
  }

  .chunk-checks {
    flex-wrap: wrap;
  }

  .pager {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
