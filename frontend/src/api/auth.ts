import request from '@/utils/http'

/**
 * 登录
 * @param params 登录参数
 * @returns 登录响应
 */
export function fetchLogin(params: Api.Auth.LoginParams) {
  return request.post<Api.Auth.LoginResponse>({
    url: '/api/auth/login',
    params
    // showSuccessMessage: true // 显示成功消息
    // showErrorMessage: false // 不显示错误消息
  })
}

/**
 * 强制绑定两步验证：获取密钥与 otpauth 链接
 * 只认登录接口下发的 bind 令牌，不走已登录状态
 */
export function fetchBind2faSecret(bindToken: string) {
  return request.post<{ secret: string; uri: string; userName: string }>({
    url: '/api/auth/2fa/secret',
    headers: { Authorization: bindToken }
  })
}

/**
 * 强制绑定两步验证：提交验证码，成功后直接返回登录令牌
 */
export function bind2fa(bindToken: string, code: string) {
  return request.post<{ token: string; refreshToken: string }>({
    url: '/api/auth/2fa/bind',
    params: { code },
    headers: { Authorization: bindToken }
  })
}

/**
 * 获取用户信息
 * @returns 用户信息
 */
export function fetchGetUserInfo() {
  return request.get<Api.Auth.UserInfo>({
    url: '/api/user/info'
    // 自定义请求头
    // headers: {
    //   'X-Custom-Header': 'your-custom-value'
    // }
  })
}
