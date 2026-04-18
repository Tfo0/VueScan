<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import axios from 'axios'
import { bootstrapAuthUser, changePassword, fetchAuthSession, login, logout, type AuthUser } from './api/auth'
import { fetchGlobalSettings, saveGlobalSettings } from './api/globalSettings'
import { AUTH_EVENT } from './api/http'

const route = useRoute()

const navItems = [
  { to: '/vueChunk', label: 'vueChunk' },
  { to: '/vueDetect', label: 'vueDetect' },
]

const authReady = ref(false)
const authenticated = ref(false)
const bootstrapRequired = ref(false)
const authUser = ref<AuthUser | null>(null)
const authSubmitting = ref(false)
const authError = ref('')
const authMessage = ref('')
const loginUsername = ref('')
const loginPassword = ref('')
const bootstrapUsername = ref('')
const bootstrapPassword = ref('')
const bootstrapConfirmPassword = ref('')

const showSettingsModal = ref(false)
const settingsLoading = ref(false)
const settingsSaving = ref(false)
const settingsError = ref('')
const settingsMessage = ref('')
const settingsScanConcurrency = ref(10)
const settingsProxyServer = ref('')
const settingsAiProvider = ref('deepseek')
const settingsDeepSeekApiKey = ref('')
const settingsDeepSeekBaseUrl = ref('https://api.deepseek.com')
const settingsDeepSeekModel = ref('deepseek-chat')
const showUserMenu = ref(false)

const AI_PROVIDER_OPTIONS = [
  { value: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com', model: 'deepseek-chat' },
  { value: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { value: 'openrouter', label: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4o-mini' },
  { value: 'siliconflow', label: 'SiliconFlow', baseUrl: 'https://api.siliconflow.cn/v1', model: 'Qwen/Qwen2.5-72B-Instruct' },
  { value: 'moonshot', label: 'Moonshot', baseUrl: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  { value: 'zhipu', label: 'Zhipu AI', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
  { value: 'dashscope', label: 'DashScope', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  { value: 'custom', label: 'Custom', baseUrl: '', model: '' },
]

type AiProviderMeta = (typeof AI_PROVIDER_OPTIONS)[number]

function getAiProviderMeta(provider: string): AiProviderMeta {
  return (AI_PROVIDER_OPTIONS.find((item) => item.value === provider) || AI_PROVIDER_OPTIONS[0]) as AiProviderMeta
}

const showChangePasswordModal = ref(false)
const passwordSaving = ref(false)
const passwordError = ref('')
const passwordMessage = ref('')
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')

function resolveError(err: unknown) {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: string } | undefined
    return data?.error || err.message || '请求失败'
  }
  if (err instanceof Error) return err.message
  return '未知错误'
}

function applyAiProviderPreset(provider: string) {
  const preset = AI_PROVIDER_OPTIONS.find((item) => item.value === provider)
  const resolvedPreset = (preset ?? AI_PROVIDER_OPTIONS[0]) as (typeof AI_PROVIDER_OPTIONS)[number]
  settingsAiProvider.value = resolvedPreset.value
  if (resolvedPreset.value !== 'custom') {
    settingsDeepSeekBaseUrl.value = resolvedPreset.baseUrl
    settingsDeepSeekModel.value = resolvedPreset.model
  }
}

function applyGlobalSettings(payload: {
  scan_concurrency: number
  proxy_server: string
  ai_provider: string
  ai_api_key: string
  ai_base_url: string
  ai_model: string
}) {
  settingsScanConcurrency.value = Math.max(1, Number(payload.scan_concurrency || 10))
  settingsProxyServer.value = String(payload.proxy_server || '')
  settingsAiProvider.value = String(payload.ai_provider || 'deepseek')
  settingsDeepSeekApiKey.value = String(payload.ai_api_key || '')
  settingsDeepSeekBaseUrl.value = String(payload.ai_base_url || 'https://api.deepseek.com')
  settingsDeepSeekModel.value = String(payload.ai_model || 'deepseek-chat')
}

async function loadGlobalSettings() {
  settingsLoading.value = true
  settingsError.value = ''
  try {
    const payload = await fetchGlobalSettings()
    applyGlobalSettings(payload.settings)
  } catch (err) {
    settingsError.value = resolveError(err)
  } finally {
    settingsLoading.value = false
  }
}

async function loadAuthSession() {
  authReady.value = false
  authError.value = ''
  try {
    const payload = await fetchAuthSession()
    authenticated.value = Boolean(payload.authenticated)
    bootstrapRequired.value = Boolean(payload.bootstrapRequired)
    authUser.value = payload.user
    if (authenticated.value) {
      await loadGlobalSettings()
    }
  } catch (err) {
    authenticated.value = false
    authUser.value = null
    authError.value = resolveError(err)
  } finally {
    authReady.value = true
  }
}

async function onLogin() {
  const username = loginUsername.value.trim()
  const password = loginPassword.value
  if (!username || !password) {
    authError.value = '请输入用户名和密码'
    return
  }
  authSubmitting.value = true
  authError.value = ''
  authMessage.value = ''
  try {
    const payload = await login({ username, password })
    authenticated.value = Boolean(payload.authenticated)
    bootstrapRequired.value = Boolean(payload.bootstrapRequired)
    authUser.value = payload.user
    loginPassword.value = ''
    await loadGlobalSettings()
    authMessage.value = '登录成功'
  } catch (err) {
    authError.value = resolveError(err)
  } finally {
    authSubmitting.value = false
  }
}

async function onBootstrap() {
  const username = bootstrapUsername.value.trim()
  const password = bootstrapPassword.value
  const confirm = bootstrapConfirmPassword.value
  if (!username || !password) {
    authError.value = '请输入管理员账号和密码'
    return
  }
  if (password !== confirm) {
    authError.value = '两次密码输入不一致'
    return
  }
  authSubmitting.value = true
  authError.value = ''
  authMessage.value = ''
  try {
    const payload = await bootstrapAuthUser({ username, password })
    authenticated.value = Boolean(payload.authenticated)
    bootstrapRequired.value = Boolean(payload.bootstrapRequired)
    authUser.value = payload.user
    bootstrapPassword.value = ''
    bootstrapConfirmPassword.value = ''
    await loadGlobalSettings()
    authMessage.value = '管理员初始化成功'
  } catch (err) {
    authError.value = resolveError(err)
  } finally {
    authSubmitting.value = false
  }
}

async function onLogout() {
  showUserMenu.value = false
  try {
    await logout()
  } catch {
    // 忽略登出时的网络抖动，统一回到未登录态。
  }
  authenticated.value = false
  authUser.value = null
  showSettingsModal.value = false
  showChangePasswordModal.value = false
  authMessage.value = '已退出登录'
}

function openSettingsModal() {
  showUserMenu.value = false
  showSettingsModal.value = true
  settingsMessage.value = ''
  void loadGlobalSettings()
}

function closeSettingsModal() {
  if (settingsSaving.value) return
  showSettingsModal.value = false
}

async function onSaveGlobalSettings() {
  settingsSaving.value = true
  settingsError.value = ''
  settingsMessage.value = ''
  try {
    const payload = await saveGlobalSettings({
      scan_concurrency: Math.max(1, Number(settingsScanConcurrency.value || 10)),
      proxy_server: String(settingsProxyServer.value || '').trim(),
      ai_provider: String(settingsAiProvider.value || 'deepseek').trim(),
      ai_api_key: String(settingsDeepSeekApiKey.value || '').trim(),
      ai_base_url: String(settingsDeepSeekBaseUrl.value || '').trim(),
      ai_model: String(settingsDeepSeekModel.value || '').trim(),
    })
    applyGlobalSettings(payload.settings)
    settingsMessage.value = '设置已保存'
  } catch (err) {
    settingsError.value = resolveError(err)
  } finally {
    settingsSaving.value = false
  }
}

function openChangePasswordModal() {
  showUserMenu.value = false
  passwordError.value = ''
  passwordMessage.value = ''
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  showChangePasswordModal.value = true
}

function closeChangePasswordModal() {
  if (passwordSaving.value) return
  showChangePasswordModal.value = false
}

async function onChangePassword() {
  if (!currentPassword.value || !newPassword.value) {
    passwordError.value = '请输入当前密码和新密码'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    passwordError.value = '两次新密码输入不一致'
    return
  }
  passwordSaving.value = true
  passwordError.value = ''
  passwordMessage.value = ''
  try {
    const payload = await changePassword({
      current_password: currentPassword.value,
      new_password: newPassword.value,
    })
    authUser.value = payload.user || authUser.value
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    passwordMessage.value = '密码已修改'
  } catch (err) {
    passwordError.value = resolveError(err)
  } finally {
    passwordSaving.value = false
  }
}

function handleAuthRequired(event: Event) {
  const payload = (event as CustomEvent<{ bootstrap_required?: boolean }>).detail || {}
  authenticated.value = false
  authUser.value = null
  bootstrapRequired.value = Boolean(payload.bootstrap_required)
  showUserMenu.value = false
  showSettingsModal.value = false
  showChangePasswordModal.value = false
  authError.value = '登录状态已失效，请重新登录'
}

function toggleUserMenu() {
  showUserMenu.value = !showUserMenu.value
}

function closeUserMenu() {
  showUserMenu.value = false
}

onMounted(() => {
  void loadAuthSession()
  window.addEventListener(AUTH_EVENT, handleAuthRequired as EventListener)
  window.addEventListener('click', closeUserMenu)
})

onUnmounted(() => {
  window.removeEventListener(AUTH_EVENT, handleAuthRequired as EventListener)
  window.removeEventListener('click', closeUserMenu)
})
</script>

<template>
  <div class="shell">
    <template v-if="!authReady">
      <div class="auth-shell">
        <div class="auth-card">
          <h2>VueScan</h2>
          <p class="auth-subtitle">正在检查登录状态...</p>
        </div>
      </div>
    </template>

    <template v-else-if="!authenticated">
      <div class="auth-shell">
        <div class="auth-card">
          <div class="auth-card-head">
            <h2>VueScan 登录</h2>
            <span class="auth-mode">{{ bootstrapRequired ? '初始化管理员' : '账号登录' }}</span>
          </div>

          <div v-if="authMessage" class="notice success">{{ authMessage }}</div>
          <div v-if="authError" class="notice error">{{ authError }}</div>

          <template v-if="bootstrapRequired">
            <div class="auth-grid">
              <label>
                <span>管理员账号</span>
                <input v-model="bootstrapUsername" type="text" autocomplete="username" placeholder="admin" />
              </label>
              <label>
                <span>管理员密码</span>
                <input v-model="bootstrapPassword" type="password" autocomplete="new-password" placeholder="至少 6 位" />
              </label>
              <label>
                <span>确认密码</span>
                <input v-model="bootstrapConfirmPassword" type="password" autocomplete="new-password" placeholder="再次输入密码" />
              </label>
            </div>
            <div class="auth-actions">
              <button :disabled="authSubmitting" @click="onBootstrap">
                {{ authSubmitting ? '初始化中...' : '初始化管理员' }}
              </button>
            </div>
          </template>

          <template v-else>
            <div class="auth-grid">
              <label>
                <span>用户名</span>
                <input v-model="loginUsername" type="text" autocomplete="username" placeholder="请输入用户名" />
              </label>
              <label>
                <span>密码</span>
                <input v-model="loginPassword" type="password" autocomplete="current-password" placeholder="请输入密码" @keyup.enter="onLogin" />
              </label>
            </div>
            <div class="auth-actions">
              <button :disabled="authSubmitting" @click="onLogin">
                {{ authSubmitting ? '登录中...' : '登录' }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </template>

    <template v-else>
      <header class="topbar">
        <div class="brand">
          <span class="brand-logo" aria-label="Vue logo">
            <svg class="brand-logo-svg" viewBox="0 0 261.76 226.69" role="img" aria-hidden="true">
              <path
                d="M0 0h53.1l77.78 134.84L208.65 0h53.11L130.88 226.69L0 0z"
                fill="#41B883"
              />
              <path
                d="M53.1 0l77.78 134.84L208.65 0h-47.57l-30.2 52.31L100.68 0H53.1z"
                fill="#35495E"
              />
            </svg>
          </span>
          <div class="brand-text">
            <h1>VueScan</h1>
          </div>
        </div>
        <div class="topbar-right">
          <nav class="nav">
            <RouterLink
              v-for="item in navItems"
              :key="item.to"
              :to="item.to"
              class="nav-link"
              :class="{ active: route.path === item.to || route.path.startsWith(item.to + '/') }"
            >
              {{ item.label }}
            </RouterLink>
          </nav>
          <div class="user-menu-wrap" @click.stop>
            <button class="ghost icon-button" title="全局设置" @click="toggleUserMenu">
              <span aria-hidden="true">⚙</span>
            </button>
            <div v-if="showUserMenu" class="user-menu">
              <div class="user-menu-name">{{ authUser?.username || 'unknown' }}</div>
              <button class="user-menu-item" @click="openSettingsModal">设置</button>
              <button class="user-menu-item" @click="openChangePasswordModal">修改密码</button>
              <button class="user-menu-item danger" @click="onLogout">退出登录</button>
            </div>
          </div>
        </div>
      </header>

      <main class="workspace">
        <RouterView />
      </main>

      <div v-if="showSettingsModal" class="modal-mask" @click.self="closeSettingsModal">
        <div class="modal-card">
          <div class="panel-head">
            <h3>全局设置</h3>
            <button class="ghost" :disabled="settingsSaving" @click="closeSettingsModal">关闭</button>
          </div>

          <div v-if="settingsMessage" class="notice success">{{ settingsMessage }}</div>
          <div v-if="settingsError" class="notice error">{{ settingsError }}</div>
          <div v-if="settingsLoading" class="empty">加载中...</div>

          <template v-else>
            <div class="form-grid modal-form-grid settings-grid">
              <div>
                <label>并发数量</label>
                <input v-model.number="settingsScanConcurrency" type="number" min="1" />
              </div>
              <div>
                <label>代理地址</label>
                <input v-model="settingsProxyServer" type="text" placeholder="127.0.0.1:8080" />
              </div>
              <div class="full">
                <label>AI 平台</label>
                <div class="provider-picker">
                  <select v-model="settingsAiProvider" @change="applyAiProviderPreset(settingsAiProvider)" class="provider-select">
                    <option v-for="option in AI_PROVIDER_OPTIONS" :key="option.value" :value="option.value">
                      {{ option.label }} · {{ option.baseUrl || '自定义接口' }} · {{ option.model || '自定义模型' }}
                    </option>
                  </select>
                </div>
                <div class="provider-summary">
                  当前使用 <strong>{{ getAiProviderMeta(settingsAiProvider).label }}</strong>
                  · Base URL <span>{{ settingsDeepSeekBaseUrl }}</span>
                  · Model <span>{{ settingsDeepSeekModel }}</span>
                </div>
              </div>
              <div class="full">
                <label>API Key</label>
                <input v-model="settingsDeepSeekApiKey" type="password" autocomplete="off" placeholder="sk-..." />
              </div>
              <div>
                <label>Base URL</label>
                <input v-model="settingsDeepSeekBaseUrl" type="text" placeholder="https://api.deepseek.com" />
              </div>
              <div>
                <label>Model</label>
                <input v-model="settingsDeepSeekModel" type="text" placeholder="deepseek-chat" />
              </div>
            </div>

            <div class="form-actions">
              <button class="ghost" :disabled="settingsSaving" @click="closeSettingsModal">取消</button>
              <button :disabled="settingsSaving" @click="onSaveGlobalSettings">
                {{ settingsSaving ? '保存中...' : '保存设置' }}
              </button>
            </div>
          </template>
        </div>
      </div>

      <div v-if="showChangePasswordModal" class="modal-mask" @click.self="closeChangePasswordModal">
        <div class="modal-card narrow">
          <div class="panel-head">
            <h3>修改密码</h3>
            <button class="ghost" :disabled="passwordSaving" @click="closeChangePasswordModal">关闭</button>
          </div>

          <div v-if="passwordMessage" class="notice success">{{ passwordMessage }}</div>
          <div v-if="passwordError" class="notice error">{{ passwordError }}</div>

          <div class="auth-grid">
            <label>
              <span>当前密码</span>
              <input v-model="currentPassword" type="password" autocomplete="current-password" />
            </label>
            <label>
              <span>新密码</span>
              <input v-model="newPassword" type="password" autocomplete="new-password" />
            </label>
            <label>
              <span>确认新密码</span>
              <input v-model="confirmPassword" type="password" autocomplete="new-password" />
            </label>
          </div>

          <div class="form-actions">
            <button class="ghost" :disabled="passwordSaving" @click="closeChangePasswordModal">取消</button>
            <button :disabled="passwordSaving" @click="onChangePassword">
              {{ passwordSaving ? '提交中...' : '保存新密码' }}
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(11, 126, 158, 0.1), transparent 28%),
    linear-gradient(180deg, #f4f7fb 0%, #eef3f9 100%);
  color: #1b2836;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 18px 28px;
  border-bottom: 1px solid rgba(32, 55, 78, 0.08);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(14px);
  position: sticky;
  top: 0;
  z-index: 20;
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.brand-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
}

.brand-logo-svg {
  width: 100%;
  height: 100%;
}

.brand-text h1 {
  margin: 0;
  font-size: 20px;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.nav {
  display: flex;
  align-items: center;
  gap: 10px;
}

.nav-link {
  padding: 10px 14px;
  border-radius: 12px;
  color: #547293;
  text-decoration: none;
  font-weight: 600;
  background: #fff;
  border: 1px solid #dbe5ef;
}

.nav-link.active {
  background: #d8ebff;
  border-color: #bdd8f6;
  color: #195c95;
}

.icon-button {
  width: 46px;
  height: 46px;
  min-width: 46px;
  padding: 0;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.user-menu-wrap {
  position: relative;
}

.user-menu {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  min-width: 176px;
  padding: 10px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid rgba(32, 55, 78, 0.1);
  box-shadow: 0 18px 42px rgba(35, 56, 77, 0.16);
  display: grid;
  gap: 8px;
  z-index: 30;
}

.user-menu-name {
  padding: 4px 6px 8px;
  font-size: 13px;
  font-weight: 700;
  color: #51657b;
  border-bottom: 1px solid #e6edf4;
}

.user-menu-item {
  width: 100%;
  padding: 10px 12px;
  border-radius: 12px;
  background: #eef3f8;
  color: #274158;
  text-align: left;
}

.user-menu-item.danger {
  background: #fff1f1;
  color: #a63a3a;
}

.workspace {
  padding: 24px;
}

.auth-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
}

.auth-card {
  width: min(460px, 100%);
  padding: 28px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(34, 56, 77, 0.08);
  box-shadow: 0 26px 80px rgba(38, 60, 84, 0.14);
}

.auth-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.auth-card h2 {
  margin: 0;
  font-size: 28px;
}

.auth-mode {
  padding: 6px 10px;
  border-radius: 999px;
  background: #edf4fb;
  color: #3e607f;
  font-size: 12px;
}

.auth-subtitle {
  margin: 8px 0 0;
  color: #687b90;
}

.auth-grid {
  display: grid;
  gap: 14px;
}

.auth-grid label,
.settings-grid label {
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: #53677c;
}

input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #cfdae7;
  border-radius: 12px;
  background: #fff;
  color: #1f2d3a;
}

button {
  border: none;
  border-radius: 12px;
  padding: 10px 14px;
  background: #17344b;
  color: #fff;
  cursor: pointer;
  font-weight: 600;
}

button.ghost {
  background: #eef3f8;
  color: #274158;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.auth-actions,
.form-actions {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 27, 39, 0.35);
  display: grid;
  place-items: center;
  padding: 24px;
  z-index: 50;
}

.modal-card {
  width: min(760px, 100%);
  padding: 24px;
  border-radius: 22px;
  background: #fff;
  border: 1px solid rgba(32, 55, 78, 0.08);
  box-shadow: 0 26px 80px rgba(38, 60, 84, 0.18);
}

.modal-card.narrow {
  width: min(520px, 100%);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.panel-head h3 {
  margin: 0;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.provider-picker {
  position: relative;
  display: grid;
  gap: 8px;
}

/*
.provider-select {
  appearance: none;
  -webkit-appearance: none;
  width: 100%;
  padding-right: 44px;
  background:
    linear-gradient(180deg, #f8fcff 0%, #edf4fb 100%);
    border-box;
  border: 1px solid rgba(40, 72, 101, 0.14);
  box-shadow: 0 10px 24px rgba(47, 81, 114, 0.08);
  color: #1f3550;
}

.provider-picker::after {
  content: '▾';
  position: absolute;
  right: 16px;
  top: 36px;
  pointer-events: none;
  color: #5f748a;
  font-size: 14px;
  line-height: 1;
}
*/

.provider-select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid rgba(40, 72, 101, 0.14);
  border-radius: 12px;
  background: #fff;
  color: #1f3550;
  font: inherit;
  appearance: auto;
  -webkit-appearance: menulist;
}

.provider-summary {
  margin-top: 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f4f8fc;
  color: #54697f;
  font-size: 12px;
  line-height: 1.5;
}

.provider-summary strong {
  color: #1f3550;
}

.provider-summary span {
  color: #29557d;
  font-weight: 600;
}

.full {
  grid-column: 1 / -1;
}

.notice {
  margin-bottom: 14px;
  padding: 10px 12px;
  border-radius: 12px;
  font-size: 13px;
}

.notice.success {
  background: #edf8f1;
  color: #2e6d3e;
}

.notice.error {
  background: #fff1f1;
  color: #a13838;
}

.empty {
  color: #667b91;
}

@media (max-width: 900px) {
  .topbar {
    padding: 16px 18px;
    flex-direction: column;
    align-items: stretch;
  }

  .topbar-right {
    flex-direction: column;
    align-items: stretch;
  }

  .nav,
  .user-bar {
    flex-wrap: wrap;
  }

  .workspace {
    padding: 16px;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
