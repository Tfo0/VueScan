<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import type { ApiEndpointItem } from '../api/vueApi'
import {
  fetchVueRequestContext,
  runVueRequest,
  type VueRequestResponseDetail,
  type VueRequestResult,
} from '../api/vueRequest'

const projects = ref<string[]>([])
const domain = ref('')
const baseurl = ref('')
const baseapi = ref('')
const endpoints = ref<ApiEndpointItem[]>([])
const endpointsError = ref('')

const apiId = ref('')
const method = ref('')
const timeout = ref(20)
const jsonBody = ref('')
const headers = ref('')

const loadingContext = ref(false)
const sending = ref(false)
const message = ref('')
const error = ref('')

const requestResult = ref<VueRequestResult | null>(null)
const responseDetail = ref<VueRequestResponseDetail | null>(null)

function resolveError(err: unknown) {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: string } | undefined
    return data?.error || err.message || 'request failed'
  }
  if (err instanceof Error) return err.message
  return 'unknown error'
}

const selectedEndpoint = computed(() => {
  return endpoints.value.find((item) => String(item.id) === apiId.value) || null
})

const requestStatusClass = computed(() => {
  if (!requestResult.value) return 'idle'
  return requestResult.value.ok ? 'done' : 'failed'
})

async function loadContext(targetDomain?: string) {
  loadingContext.value = true
  error.value = ''
  try {
    const payload = await fetchVueRequestContext(targetDomain || domain.value || '')
    projects.value = Array.isArray(payload.projects) ? payload.projects : []
    domain.value = String(payload.domain || targetDomain || domain.value || '')
    baseurl.value = String(payload.baseurl || '')
    baseapi.value = String(payload.baseapi || '')
    endpoints.value = Array.isArray(payload.endpoints) ? payload.endpoints : []
    endpointsError.value = String(payload.endpoints_error || '')

    apiId.value = String(payload.api_id || (endpoints.value[0]?.id ?? ''))
    method.value = String(payload.method || selectedEndpoint.value?.method || 'GET')
    timeout.value = Number(payload.timeout || 20)

    if (!jsonBody.value) jsonBody.value = String(payload.json_body || '')
    if (!headers.value) headers.value = String(payload.headers || '')
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    loadingContext.value = false
  }
}

async function onDomainChange() {
  requestResult.value = null
  responseDetail.value = null
  endpoints.value = []
  apiId.value = ''
  method.value = 'GET'
  await loadContext(domain.value)
}

function onApiChange() {
  const selected = selectedEndpoint.value
  if (selected) {
    method.value = selected.method || method.value || 'GET'
  }
}

async function onSendRequest() {
  if (!domain.value) {
    error.value = 'Please select project domain'
    return
  }
  if (!apiId.value) {
    error.value = 'Please select API'
    return
  }

  sending.value = true
  error.value = ''
  message.value = ''
  try {
    const payload = await runVueRequest({
      domain: domain.value,
      api_id: apiId.value,
      method: method.value,
      baseurl: baseurl.value,
      baseapi: baseapi.value,
      timeout: Math.max(1, Number(timeout.value || 20)),
      json_body: jsonBody.value,
      headers: headers.value,
    })
    requestResult.value = payload.requestResult
    responseDetail.value = payload.responseDetail
    message.value = `Request completed: status ${payload.requestResult.status_code || 0}`
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    sending.value = false
  }
}

onMounted(async () => {
  await loadContext()
})
</script>

<template>
  <section class="page">
    <div v-if="message" class="notice success">{{ message }}</div>
    <div v-if="error" class="notice error">{{ error }}</div>

    <section class="panel">
      <h3>Request Config</h3>
      <div class="request-grid">
        <div>
          <label>Project Domain</label>
          <select v-model="domain" @change="onDomainChange">
            <option value="">-- Select --</option>
            <option v-for="item in projects" :key="item" :value="item">{{ item }}</option>
          </select>
        </div>
        <div class="request-actions">
          <button class="ghost" :disabled="loadingContext" @click="loadContext(domain)">
            {{ loadingContext ? 'Loading...' : 'Load API List' }}
          </button>
        </div>

        <div>
          <label>Base URL</label>
          <input v-model="baseurl" type="text" placeholder="https://target.example.com" />
        </div>
        <div>
          <label>Base API</label>
          <input v-model="baseapi" type="text" placeholder="/api/v1" />
        </div>

        <div class="full">
          <label>API</label>
          <select v-model="apiId" @change="onApiChange">
            <option value="">-- Select API --</option>
            <option v-for="item in endpoints" :key="item.id" :value="String(item.id)">
              {{ item.id }} | {{ item.method }} | {{ item.path }}
            </option>
          </select>
          <div v-if="endpointsError" class="empty">{{ endpointsError }}</div>
        </div>

        <div>
          <label>Method Override</label>
          <input v-model="method" type="text" placeholder="GET" />
        </div>
        <div>
          <label>Timeout (s)</label>
          <input v-model.number="timeout" type="number" min="1" />
        </div>

        <div class="full">
          <label>JSON Body</label>
          <textarea v-model="jsonBody" rows="7" placeholder='{"key": "value"}'></textarea>
        </div>

        <div class="full">
          <label>Headers JSON</label>
          <textarea v-model="headers" rows="6" placeholder='{"Authorization": "Bearer ..."}'></textarea>
        </div>

        <div class="full request-actions">
          <button :disabled="sending" @click="onSendRequest">{{ sending ? 'Sending...' : 'Send Request' }}</button>
        </div>
      </div>
    </section>

    <section class="panel">
      <h3>Request Result</h3>
      <div v-if="requestResult" class="result-wrap">
        <div class="result-meta">
          <div><span>domain:</span> {{ requestResult.domain }}</div>
          <div><span>api_id:</span> {{ requestResult.api_id }}</div>
          <div><span>method:</span> {{ requestResult.method }}</div>
          <div><span>url:</span> <span class="mono">{{ requestResult.url }}</span></div>
          <div>
            <span>status:</span>
            <span class="status-pill" :class="requestStatusClass">{{ requestResult.status_code }}</span>
          </div>
          <div><span>elapsed:</span> {{ requestResult.elapsed_ms }} ms</div>
          <div><span>response_path:</span> <span class="mono">{{ requestResult.response_path || '-' }}</span></div>
        </div>

        <pre v-if="requestResult.error" class="result-json">{{ requestResult.error }}</pre>

        <div v-if="responseDetail" class="response-detail">
          <h4>Response Headers</h4>
          <pre class="result-json">{{ JSON.stringify(responseDetail.response_headers || {}, null, 2) }}</pre>
          <h4>Response Body</h4>
          <pre class="result-json">{{ responseDetail.response_text || '' }}</pre>
        </div>
      </div>
      <div v-else class="empty">No request result yet.</div>
    </section>
  </section>
</template>

<style scoped>
select,
textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 9px 10px;
  font-size: 14px;
  color: var(--ink);
  background: #fff;
}

select:focus,
textarea:focus {
  outline: none;
  border-color: #8bc0e6;
  box-shadow: 0 0 0 2px rgba(14, 132, 204, 0.12);
}

.request-grid {
  display: grid;
  grid-template-columns: 1fr 220px;
  gap: 10px;
}

.full {
  grid-column: 1 / -1;
}

.request-actions {
  display: flex;
  align-items: end;
  gap: 8px;
}

.result-wrap {
  display: grid;
  gap: 10px;
}

.result-meta {
  border: 1px dashed #c7d7e7;
  border-radius: 10px;
  padding: 10px;
  display: grid;
  gap: 6px;
  font-size: 13px;
}

.result-meta span {
  color: #5f7081;
  font-weight: 700;
}

.result-json {
  margin: 0;
  border: 1px solid #dbe6f1;
  border-radius: 10px;
  background: #f7fbff;
  padding: 10px;
  max-height: 360px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'JetBrains Mono', 'Cascadia Mono', Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 980px) {
  .request-grid {
    grid-template-columns: 1fr;
  }

  .request-actions {
    align-items: stretch;
  }
}
</style>
