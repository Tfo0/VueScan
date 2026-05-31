<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import {
  createVueDetectTask,
  deleteVueDetectTask,
  fetchVueDetectTasks,
  pauseVueDetectJob,
  resumeVueDetectJob,
  type DetectTask,
} from '../api/vueDetect'

const router = useRouter()

const tasks = ref<DetectTask[]>([])
const loadingTasks = ref(false)
const creatingTask = ref(false)
const deletingTaskId = ref('')
const pausingTaskId = ref('')
const resumingTaskId = ref('')
const showCreateModal = ref(false)
const formTaskName = ref('')
const formConcurrency = ref(5)
const formFile = ref<File | null>(null)
const fileInputKey = ref(0)
const message = ref('')
const error = ref('')
let pollTimer: number | undefined

function statusClass(status: string) {
  const value = String(status || '').toLowerCase()
  if (value === 'completed' || value === 'done') return 'done'
  if (value === 'failed') return 'failed'
  if (value === 'paused') return 'paused'
  if (value === 'running' || value === 'queued') return 'running'
  return 'idle'
}

function statusText(status: string) {
  const value = String(status || '').toLowerCase()
  if (value === 'completed' || value === 'done') return '已完成'
  if (value === 'failed') return '失败'
  if (value === 'running') return '运行中'
  if (value === 'queued') return '排队中'
  if (value === 'paused') return '已暂停'
  if (value === 'idle') return '空闲'
  return '未知'
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

async function loadTasks() {
  loadingTasks.value = true
  error.value = ''
  try {
    const payload = await fetchVueDetectTasks()
    tasks.value = payload.tasks
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    loadingTasks.value = false
  }
}

function onFileChanged(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0] || null
  formFile.value = file
}

function openCreateModal() {
  showCreateModal.value = true
}

function closeCreateModal() {
  if (creatingTask.value) return
  showCreateModal.value = false
}

async function onCreateTask() {
  if (!formTaskName.value.trim()) {
    error.value = '任务名称不能为空'
    return
  }
  if (!formFile.value) {
    error.value = '请上传文件'
    return
  }

  creatingTask.value = true
  message.value = ''
  error.value = ''
  try {
    const created = await createVueDetectTask({
      taskName: formTaskName.value.trim(),
      concurrency: Math.max(1, Number(formConcurrency.value || 5)),
      file: formFile.value,
    })
    formTaskName.value = ''
    formConcurrency.value = 5
    formFile.value = null
    fileInputKey.value += 1
    showCreateModal.value = false
    await loadTasks()
    if (created.task?.task_id) {
      await router.push(`/vueDetect/tasks/${encodeURIComponent(created.task.task_id)}`)
    }
    message.value = '检测任务已创建，后台开始执行'
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    creatingTask.value = false
  }
}

async function onDeleteTask(taskId: string) {
  const hit = tasks.value.find((item) => item.task_id === taskId)
  const title = hit?.title || taskId
  if (!window.confirm(`确认删除任务：${title}？`)) return

  deletingTaskId.value = taskId
  message.value = ''
  error.value = ''
  try {
    await deleteVueDetectTask(taskId)
    await loadTasks()
    message.value = '任务已删除'
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    deletingTaskId.value = ''
  }
}

async function onPauseTask(task: DetectTask) {
  const jobId = String(task.job_id || '').trim()
  if (!jobId) {
    error.value = 'job_id is required'
    return
  }
  pausingTaskId.value = task.task_id
  message.value = ''
  error.value = ''
  try {
    await pauseVueDetectJob(jobId)
    await loadTasks()
    message.value = '任务已暂停'
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    pausingTaskId.value = ''
  }
}

async function onResumeTask(task: DetectTask) {
  const jobId = String(task.job_id || '').trim()
  if (!jobId) {
    error.value = 'job_id is required'
    return
  }
  resumingTaskId.value = task.task_id
  message.value = ''
  error.value = ''
  try {
    await resumeVueDetectJob(jobId)
    await loadTasks()
    message.value = '任务已继续'
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    resumingTaskId.value = ''
  }
}

async function onOpenTaskDetail(taskId: string) {
  await router.push(`/vueDetect/tasks/${encodeURIComponent(taskId)}`)
}

function ensurePolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
  pollTimer = window.setInterval(async () => {
    const hasRunning = tasks.value.some((item) => {
      const status = String(item.status || '').toLowerCase()
      return status === 'running' || status === 'queued'
    })
    if (!hasRunning) return
    await loadTasks()
  }, 3000)
}

onMounted(async () => {
  await loadTasks()
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
      <div class="panel-head">
        <h3>检测任务</h3>
        <div class="panel-head-actions">
          <button @click="openCreateModal">创建检测任务</button>
          <button class="ghost" :disabled="loadingTasks" @click="loadTasks">刷新</button>
        </div>
      </div>
      <div v-if="loadingTasks" class="empty">加载中...</div>
      <table v-else-if="tasks.length > 0" class="task-table">
        <thead>
          <tr>
            <th>任务名称</th>
            <th>状态</th>
            <th>URL数量</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in tasks" :key="task.task_id">
            <td class="name">
              <a href="#" @click.prevent="onOpenTaskDetail(task.task_id)">{{ task.title }}</a>
            </td>
            <td>
              <span class="status-pill" :class="statusClass(task.status)">{{ statusText(task.status) }}</span>
            </td>
            <td>{{ task.url_count }}</td>
            <td>{{ task.updated_at || '-' }}</td>
            <td>
              <button
                v-if="task.job_id && (task.status === 'running' || task.status === 'queued')"
                class="ghost"
                :disabled="pausingTaskId === task.task_id"
                @click="onPauseTask(task)"
              >
                {{ pausingTaskId === task.task_id ? '暂停中...' : '暂停' }}
              </button>
              <button
                v-if="task.job_id && task.status === 'paused'"
                class="ghost"
                :disabled="resumingTaskId === task.task_id"
                @click="onResumeTask(task)"
              >
                {{ resumingTaskId === task.task_id ? '继续中...' : '继续' }}
              </button>
              <button
                class="delete-btn"
                :disabled="deletingTaskId === task.task_id"
                @click="onDeleteTask(task.task_id)"
              >
                {{ deletingTaskId === task.task_id ? '删除中...' : '删除' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">暂无检测任务</div>
    </section>

    <div v-if="showCreateModal" class="modal-mask" @click.self="closeCreateModal">
      <div class="modal-card">
        <div class="panel-head">
          <h3>创建检测任务</h3>
          <button class="ghost" :disabled="creatingTask" @click="closeCreateModal">关闭</button>
        </div>
        <div class="form-grid modal-form-grid">
          <div>
            <label>任务名称</label>
            <input v-model="formTaskName" type="text" placeholder="例如：检测任务-1" />
          </div>
          <div>
            <label>并发数量</label>
            <input v-model.number="formConcurrency" type="number" min="1" />
          </div>
          <div class="file-field">
            <label>上传文件</label>
            <input
              :key="fileInputKey"
              type="file"
              accept=".xlsx,.xlsm,.txt,.html,.htm"
              @change="onFileChanged"
            />
          </div>
        </div>
        <div class="form-actions">
          <button :disabled="creatingTask" @click="onCreateTask">
            {{ creatingTask ? '创建中...' : '创建任务' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
