import axios from 'axios'

const http = axios.create({
  baseURL: '/',
  timeout: 60000,
  withCredentials: true,
})

const AUTH_EVENT = 'vuescan-auth-required'
const AUTH_FREE_PATHS = new Set([
  '/api/auth/session',
  '/api/auth/login',
  '/api/auth/bootstrap',
  '/api/auth/logout',
])

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      const requestUrl = String(error.config?.url || '')
      if (!AUTH_FREE_PATHS.has(requestUrl) && typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent(AUTH_EVENT, {
            detail: error.response?.data || {},
          }),
        )
      }
    }
    return Promise.reject(error)
  },
)

export default http
export { AUTH_EVENT }
