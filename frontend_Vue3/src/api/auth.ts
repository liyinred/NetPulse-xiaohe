import request from '@/utils/http'

/**
 * 创建微信扫码登录二维码
 * @returns 二维码参数和有效期
 */
export function fetchCreateWechatQRCode() {
  return request.post<Api.Auth.WechatQRCode>({
    url: '/api/auth/wechat/qrcode'
  })
}

/**
 * 查询微信扫码登录状态
 * @param sceneStr 二维码携带的场景值
 * @returns 当前扫码认证状态
 */
export function fetchWechatLoginStatus(sceneStr: string) {
  return request.get<Api.Auth.WechatLoginStatus>({
    url: '/api/auth/wechat/status',
    params: { scene_str: sceneStr },
    showErrorMessage: false
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
