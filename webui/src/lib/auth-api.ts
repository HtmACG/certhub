/** 认证相关的薄封装：登录页只关心这三个调用，其余接口在 api.ts 里 */
import { http } from './http'

export interface ApiErrorLike extends Error {
  code?: number
  data?: unknown
}

export const login = (params: {
  userName: string
  password: string
  captchaCode?: string
  captchaToken?: string
}) => http.post<Record<string, unknown>>('/api/auth/login', params)

export const fetchCaptcha = () =>
  http.get<{ token: string; image: string; expiresIn: number; enabled: boolean }>('/api/auth/captcha')

export const fetchSiteConfig = () =>
  http.get<{ name: string; subtitle?: string; title?: string; logo?: string; loginNotice?: string }>('/api/site/config')

export const fetch2faSecretForBind = (bindToken: string) =>
  http.post<{ secret: string; uri: string; userName: string }>(
    '/api/auth/2fa/secret',
    {},
    { headers: { Authorization: bindToken } },
  )

export const bind2fa = (bindToken: string, code: string) =>
  http.post<{ token: string; refreshToken: string }>(
    '/api/auth/2fa/bind',
    { code },
    { headers: { Authorization: bindToken } },
  )
