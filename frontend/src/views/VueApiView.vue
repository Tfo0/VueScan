<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import {
  fetchVueApiContext,
  runVueApiBeautify,
  runVueApiExtract,
  runVueApiPreview,
  type VueApiBeautify,
  type VueApiExtractResult,
  type VueApiPreviewResult,
} from '../api/vueApi'

const projects = ref<string[]>([])
const domain = ref('')
const jsFiles = ref<string[]>([])
const jsUrls = ref<string[]>([])
const jsFile = ref('')
const jsUrl = ref('')
const pattern = ref('')

const beautifyResult = ref<VueApiBeautify | null>(null)
const previewResult = ref<VueApiPreviewResult | null>(null)
const extractResult = ref<VueApiExtractResult | null>(null)

const loadingContext = ref(false)
const previewing = ref(false)
const extracting = ref(false)

const message = ref('')
const error = ref('')

function resolveError(err: unknown) {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: string } | undefined
    return data?.error || err.message || 'request failed'
  }
  if (err instanceof Error) return err.message
  return 'unknown error'
}

function clearOutputs() {
  beautifyResult.value = null
  previewResult.value = null
  extractResult.value = null
}

function isHttpUrl(value: string) {
  return /^https?:\/\//i.test(String(value || '').trim())
}

async function loadContext(targetDomain?: string) {
  loadingContext.value = true
  error.value = ''
  try {
    const payload = await fetchVueApiContext(targetDomain || domain.value || '')
    projects.value = Array.isArray(payload.projects) ? payload.projects : []
    domain.value = String(payload.domain || targetDomain || domain.value || '')
    jsFiles.value = Array.isArray(payload.js_files) ? payload.js_files : []
    jsUrls.value = Array.isArray(payload.js_urls) ? payload.js_urls : []

    const preferredJsFile = String(payload.js_file || '')
    if (preferredJsFile && jsFiles.value.includes(preferredJsFile)) {
      jsFile.value = preferredJsFile
    } else if (!jsFile.value || (!jsFiles.value.includes(jsFile.value) && !jsUrls.value.includes(jsFile.value))) {
      jsFile.value = jsFiles.value[0] || jsUrls.value[0] || ''
    }

    if (!jsUrl.value) jsUrl.value = String(payload.js_url || '')
    if (!pattern.value) pattern.value = String(payload.pattern || '')
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    loadingContext.value = false
  }
}

async function onDomainChange() {
  clearOutputs()
  jsUrls.value = []
  jsFile.value = ''
  jsUrl.value = ''
  pattern.value = ''
  await loadContext(domain.value)
}

async function onJsFileChange() {
  if (jsFile.value && !isHttpUrl(jsFile.value)) {
    jsUrl.value = ''
  } else if (jsFile.value && isHttpUrl(jsFile.value)) {
    jsUrl.value = jsFile.value
  }
  clearOutputs()
  if (jsFile.value) {
    await onBeautify()
  }
}

async function onBeautify() {
  if (!domain.value) {
    error.value = 'Please select project domain'
    return
  }
  const selectedFile = String(jsFile.value || '').trim()
  const inputUrl = String(jsUrl.value || '').trim()
  const resolvedJsUrl = isHttpUrl(selectedFile) ? selectedFile : inputUrl
  const resolvedJsFile = isHttpUrl(selectedFile) ? '' : selectedFile
  if (!resolvedJsFile && !resolvedJsUrl) {
    error.value = 'Please select JS file or input JS URL'
    return
  }

  error.value = ''
  try {
    const payload = await runVueApiBeautify({
      domain: domain.value,
      js_file: resolvedJsFile,
      js_url: resolvedJsUrl,
      pattern: pattern.value,
    })
    beautifyResult.value = payload.beautify
    message.value = 'Beautify output ready'
  } catch (err) {
    error.value = resolveError(err)
  }
}

async function onPreviewExtract() {
  if (!domain.value) {
    error.value = 'Please select project domain'
    return
  }
  if (!pattern.value.trim()) {
    error.value = 'Regex is required'
    return
  }

  previewing.value = true
  error.value = ''
  try {
    previewResult.value = await runVueApiPreview({
      domain: domain.value,
      pattern: pattern.value.trim(),
    })
    message.value = `Preview extracted: ${previewResult.value.count || 0}`
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    previewing.value = false
  }
}

async function onBatchExtract() {
  if (!domain.value) {
    error.value = 'Please select project domain'
    return
  }
  if (!pattern.value.trim()) {
    error.value = 'Regex is required'
    return
  }

  extracting.value = true
  error.value = ''
  try {
    extractResult.value = await runVueApiExtract({
      domain: domain.value,
      pattern: pattern.value.trim(),
    })
    message.value = `Batch extracted: ${extractResult.value.endpoint_count || 0}`
  } catch (err) {
    error.value = resolveError(err)
  } finally {
    extracting.value = false
  }
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

onMounted(async () => {
  await loadContext()
  if (domain.value && jsFile.value) {
    await onBeautify()
  }
})
</script>

<template>
  <section class="page">
    <div v-if="message" class="notice success">{{ message }}</div>
    <div v-if="error" class="notice error">{{ error }}</div>

    <section class="panel">
      <h3>Project & JS Source</h3>
      <div class="api-grid top-grid">
        <div>
          <label>Project Domain</label>
          <select v-model="domain" @change="onDomainChange">
            <option value="">-- Select --</option>
            <option v-for="item in projects" :key="item" :value="item">{{ item }}</option>
          </select>
        </div>
        <div>
          <label>Project JS Source</label>
          <select v-model="jsFile" @change="onJsFileChange">
            <option value="">-- Select JS source --</option>
            <optgroup v-if="jsFiles.length" label="Local downChunk">
              <option v-for="item in jsFiles" :key="`file-${item}`" :value="item">{{ item }}</option>
            </optgroup>
            <optgroup v-if="jsUrls.length" label="Captured js.txt">
              <option v-for="item in jsUrls" :key="`url-${item}`" :value="item">{{ item }}</option>
            </optgroup>
          </select>
        </div>
        <div class="api-actions">
          <button class="ghost" :disabled="loadingContext" @click="loadContext(domain)">Refresh</button>
        </div>
      </div>

      <div v-if="beautifyResult" class="code-area">
        <div class="code-meta">
          <span>source: {{ beautifyResult.source }}</span>
          <span>raw_chars: {{ beautifyResult.raw_chars }}</span>
          <span>beautified_chars: {{ beautifyResult.beautified_chars }}</span>
          <span v-if="beautifyResult.truncated">truncated</span>
        </div>
        <pre class="code-block"><code v-html="beautifyHtml"></code></pre>
      </div>
    </section>

    <section class="panel">
      <h3>URL / Regex / Extract</h3>
      <div class="api-grid bottom-grid">
        <div class="wide">
          <label>JS URL (priority over local JS)</label>
          <input v-model="jsUrl" type="text" placeholder="https://target.example.com/assets/app.js" />
        </div>
        <div>
          <label>Regex</label>
          <input v-model="pattern" type="text" placeholder="/base" />
        </div>
        <div class="api-actions vertical">
          <button class="ghost" :disabled="previewing" @click="onPreviewExtract">{{ previewing ? 'Previewing...' : 'Preview Extract' }}</button>
          <button :disabled="extracting" @click="onBatchExtract">{{ extracting ? 'Extracting...' : 'Batch Extract' }}</button>
        </div>
      </div>

      <div v-if="previewResult" class="code-area">
        <h4>Preview Result ({{ previewResult.count }})</h4>
        <table v-if="previewResult.endpoints?.length" class="task-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Method</th>
              <th>Path</th>
              <th>Source File</th>
              <th>Source Line</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in previewResult.endpoints || []" :key="`${item.id}-${item.source_line}`">
              <td>{{ item.id }}</td>
              <td>{{ item.method }}</td>
              <td class="mono">{{ item.path }}</td>
              <td class="mono">{{ item.source_file }}</td>
              <td>{{ item.source_line }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">No endpoint extracted from all JS sources.</div>
      </div>

      <div v-if="extractResult" class="code-area">
        <h4>Batch Extract Result</h4>
        <pre class="result-json">{{ JSON.stringify(extractResult, null, 2) }}</pre>
      </div>
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

.api-grid {
  display: grid;
  gap: 10px;
}

.top-grid {
  grid-template-columns: 1fr 1fr 120px;
}

.bottom-grid {
  grid-template-columns: 1.4fr 1fr 240px;
}

.wide {
  grid-column: span 1;
}

.api-actions {
  display: flex;
  align-items: end;
  gap: 8px;
}

.api-actions.vertical {
  flex-direction: column;
  align-items: stretch;
  justify-content: end;
}

.code-area {
  margin-top: 12px;
}

.code-meta {
  margin-bottom: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: #557088;
  font-size: 12px;
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
  min-height: 420px;
  max-height: 620px;
}

.result-json {
  max-height: 380px;
}

.code-block :deep(.tok-comment) { color: #607d94; }
.code-block :deep(.tok-string) { color: #8e3f2b; }
.code-block :deep(.tok-number) { color: #7a2da8; }
.code-block :deep(.tok-literal) { color: #155f8c; }
.code-block :deep(.tok-keyword) { color: #0c63a0; font-weight: 700; }

@media (max-width: 980px) {
  .top-grid,
  .bottom-grid {
    grid-template-columns: 1fr;
  }

  .api-actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
