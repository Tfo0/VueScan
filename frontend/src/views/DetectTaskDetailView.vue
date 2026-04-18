<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import {
  createProjectFromDetectTask,
  fetchVueDetectTask,
  pauseVueDetectJob,
  resumeVueDetectJob,
  type DetectTask,
  type DetectUrlRow,
} from '../api/vueDetect'

const route = useRoute()
const router = useRouter()

const task = ref<DetectTask | null>(null)
const loading = ref(false)
const creatingProjectUrl = ref('')
const createdProjectMap = ref<Record<string, string>>({})
const message = ref('')
const error = ref('')
const urlPage = ref(1)
const urlPageSize = ref(50)
const pausingTask = ref(false)
const resumingTask = ref(false)
const refreshingTask = ref(false)
let pollTimer: number | undefined

const taskId = computed(() => String(route.params.taskId || '').trim())
const sortedRows = computed(() => {
  const rows = (task.value?.urls || [])
    .map((item, index) => ({
      url: String((item as DetectUrlRow).url || '').trim(),
      title: String((item as DetectUrlRow).title || '').trim(),
      route_count: Number((item as DetectUrlRow).route_count || 0),
      index,
    }))
    .filter((entry) => Boolean(entry.url))
  rows.sort((a, b) => {
    if (a.route_count !== b.route_count) return b.route_count - a.route_count
    return a.index - b.index
  })
  return rows
})
const urlTotal = computed(() => sortedRows.value.length)
const urlTotalPages = computed(() => {
  const total = Math.ceil(urlTotal.value / urlPageSize.value)
  return Math.max(1, total || 1)
})
const pagedRows = computed(() => {
  const page = Math.min(Math.max(1, Number(urlPage.value || 1)), urlTotalPages.value)
  const start = (page - 1) * urlPageSize.value
  return sortedRows.value.slice(start, start + urlPageSize.value)
})

watch(
  () => sortedRows.value.length,
  () => {
    if (urlPage.value < 1) {
      urlPage.value = 1
      return
    }
    if (urlPage.value > urlTotalPages.value) {
      urlPage.value = urlTotalPages.value
    }
  },
)

function onPrevUrlPage() {
  if (urlPage.value <= 1) return
  urlPage.value -= 1
}

function onNextUrlPage() {
  if (urlPage.value >= urlTotalPages.value) return
  urlPage.value += 1
}

function resolveError(err: unknown) {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: string } | undefined
    if (data?.error) return data.error
    return err.message || '请求失败'
  }
  if (err instanceof Error) return err.message
  return '未知错误'
}

async function loadTask(options?: { silent?: boolean }) {
  if (!taskId.value) return
  const silent = Boolean(options?.silent)
  if (!silent) {
    loading.value = true
    refreshingTask.value = true
    error.value = ''
  }
  try {
    task.value = await fetchVueDetectTask(taskId.value)
  } catch (err) {
    if (!silent) {
      error.value = resolveError(err)
    }
  } finally {
    if (!silent) {
      loading.value = false
      refreshingTask.value = false
    }
  }
}

async function onCreateProject(url: string, title = '') {
  if (!taskId.value) return
  creatingProjectUrl.value = url
  message.value = ''
  error.value = ''
  try {
    const created = await createProjectFromDetectTask(taskId.value, url, title)
    const domain = String(created.project?.domain || '').trim()
    createdProjectMap.value = {
      ...createdProjectMap.value,
      [url]: domain || 'created',
    }
    message.value = `任务已创建：${domain || url}`
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    creatingProjectUrl.value = ''
  }
}

async function onPauseTask() {
  const jobId = String(task.value?.job_id || '').trim()
  if (!jobId) return
  pausingTask.value = true
  message.value = ''
  error.value = ''
  try {
    await pauseVueDetectJob(jobId)
    await loadTask()
    message.value = '任务已暂停'
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    pausingTask.value = false
  }
}

async function onResumeTask() {
  const jobId = String(task.value?.job_id || '').trim()
  if (!jobId) return
  resumingTask.value = true
  message.value = ''
  error.value = ''
  try {
    await resumeVueDetectJob(jobId)
    await loadTask()
    message.value = '任务已继续'
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    resumingTask.value = false
  }
}

function ensurePolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
  pollTimer = window.setInterval(async () => {
    const status = String(task.value?.status || '').toLowerCase()
    if (status !== 'running' && status !== 'queued') return
    await loadTask({ silent: true })
  }, 3000)
}

async function onRefreshTask() {
  await loadTask()
}

onMounted(async () => {
  await loadTask()
  ensurePolling()
})

onUnmounted(() => {
  if (pollTimer) {
    window.clearInterval(pollTimer)
  }
})
</script>

<template>
  <section class="page">
    <div v-if="message" class="notice success">{{ message }}</div>
    <div v-if="error" class="notice error">{{ error }}</div>

    <section class="panel">
      <div v-if="loading" class="empty">加载中...</div>
      <div v-else-if="task">
        <div class="url-list">
          <div class="panel-head">
            <h4>检测结果</h4>
            <div class="panel-head-actions">
              <button
                v-if="task.job_id && (task.status === 'running' || task.status === 'queued')"
                class="ghost"
                :disabled="pausingTask"
                @click="onPauseTask"
              >
                {{ pausingTask ? '暂停中...' : '暂停' }}
              </button>
              <button
                v-if="task.job_id && task.status === 'paused'"
                class="ghost"
                :disabled="resumingTask"
                @click="onResumeTask"
              >
                {{ resumingTask ? '继续中...' : '继续' }}
              </button>
              <div v-if="urlTotal > 0" class="pager-inline-lite">
                <span>第 {{ urlPage }} / {{ urlTotalPages }} 页 | 共 {{ urlTotal }} 条</span>
                <button class="ghost btn-sm" :disabled="loading || urlPage <= 1" @click="onPrevUrlPage">
                  上一页
                </button>
                <button class="ghost btn-sm" :disabled="loading || urlPage >= urlTotalPages" @click="onNextUrlPage">
                  下一页
                </button>
              </div>
              <button class="ghost" :disabled="refreshingTask" @click="onRefreshTask">
                {{ refreshingTask ? '???...' : '??' }}
              </button>
              <button class="ghost" @click="router.push('/vueDetect')">返回任务列表</button>
            </div>
          </div>

          <table v-if="pagedRows.length > 0" class="task-table detect-url-table">
            <thead>
              <tr>
                <th>URL</th>
                <th class="created-col">状态</th>
                <th class="count-col">路由数量</th>
                <th class="title-col">标题</th>
                <th class="action-col">创建任务</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in pagedRows" :key="`${row.url}-${index + (urlPage - 1) * urlPageSize}`">
                <td class="mono">
                  <a :href="row.url" target="_blank" rel="noreferrer">{{ row.url }}</a>
                </td>
                <td class="created-col">
                  <span v-if="createdProjectMap[row.url]" class="created-hint">已创建</span>
                  <span v-else class="created-empty">-</span>
                </td>
                <td class="count-col">{{ row.route_count }}</td>
                <td class="title-col" :title="row.title || '-'">{{ row.title || '-' }}</td>
                <td class="action-col">
                  <button
                    :disabled="creatingProjectUrl === row.url || Boolean(createdProjectMap[row.url])"
                    @click="onCreateProject(row.url, row.title)"
                  >
                    创建任务
                  </button>
                </td>
              </tr>
            </tbody>
          </table>

          <div v-else class="empty">暂无 URL 结果</div>
        </div>
      </div>
      <div v-else class="empty">任务不存在</div>
    </section>
  </section>
</template>

<style scoped>
.panel-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.pager-inline-lite {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #5a7086;
  font-size: 12px;
}

.detect-url-table tbody tr {
  cursor: default;
}

.created-col {
  width: 92px;
  min-width: 92px;
  text-align: center;
}

.count-col {
  width: 108px;
  min-width: 108px;
  text-align: center;
}

.action-col {
  width: 128px;
  min-width: 128px;
  text-align: center;
}

.created-hint {
  color: #2f855a;
  font-size: 12px;
  white-space: nowrap;
}

.created-empty {
  color: #90a3b4;
  font-size: 12px;
}

.title-col {
  min-width: 220px;
}

@media (max-width: 980px) {
  .panel-head-actions {
    justify-content: flex-start;
  }
}
</style>
