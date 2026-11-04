import axios, { AxiosError, type AxiosRequestConfig } from 'axios'

export const TOKEN_KEY = 'certhub.token'

export interface ApiError extends Error {
  code: number
  data?: unknown
}

type Envelope<T> = { code: number; msg: string; data: T }

const client = axios.create({
  baseURL: '/',
  timeout: 20000,
  headers: { 'Content-Type': 'application/json' },
})

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

client.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.set('Authorization', token)
  return config
})

client.interceptors.response.use(
  (response) => {
    const body = response.data as Envelope<unknown>
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 200) return body.data as never
      if (body.code === 401) handleUnauthorized()
      const error = new Error(body.msg || '请求失败') as ApiError
      error.code = body.code
      error.data = body.data
      throw error
    }
    return response.data as never
  },
  (error: AxiosError<Envelope<unknown>>) => {
    const status = error.response?.status
    if (status === 401) handleUnauthorized()
    const body = error.response?.data
    const message = (body && typeof body === 'object' && body.msg) || error.message || '网络异常'
    const wrapped = new Error(message) as ApiError
    wrapped.code = (body && typeof body === 'object' && body.code) || status || 0
    wrapped.data = body?.data
    return Promise.reject(wrapped)
  },
)

function handleUnauthorized() {
  if (location.hash.startsWith('#/login')) return
  setToken('')
  location.hash = '#/login'
}

export const http = {
  get: <T>(url: string, config?: AxiosRequestConfig) => client.get<never, T>(url, config),
  post: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    client.post<never, T>(url, data, config),
  put: <T>(url: string, data?: unknown) => client.put<never, T>(url, data),
  del: <T>(url: string, config?: AxiosRequestConfig) => client.delete<never, T>(url, config),
}

/** 下载类接口要自己带 Authorization，再按 Content-Disposition 落盘 */
export async function download(url: string, fallbackName: string) {
  const response = await fetch(url, { headers: { Authorization: getToken() } })
  if (!response.ok) throw new Error(`下载失败（HTTP ${response.status}）`)
  const type = response.headers.get('content-type') || ''
  if (type.includes('application/json')) {
    const body = await response.json()
    throw new Error(body.msg || '下载失败')
  }
  const disposition = response.headers.get('content-disposition') || ''
  const matched = /filename="?([^"]+)"?/.exec(disposition)
  const blob = await response.blob()
  const href = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = matched ? matched[1] : fallbackName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(href)
}
