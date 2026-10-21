import request from '@/utils/http'
import { AppRouteRecord } from '@/types/router'

/**
 * 获取 IP 管理分页列表。
 * @param params IP 筛选、排序和分页参数。
 * @returns IP 管理分页列表请求结果。
 */
export function fetchGetIPList(params: Api.SystemManage.IPSearchParams) {
  return request.get<Api.SystemManage.IPList>({
    url: '/api/ip/list',
    params
  })
}

/**
 * 查询 IP 归属信息并新增或刷新 IP 记录。
 * @param params 包含标准 IPv4 或 IPv6 地址的请求参数。
 * @returns 新增或刷新后的 IP 记录。
 */
export function fetchUpsertIP(params: Api.SystemManage.IPUpsertParams) {
  return request.post<Api.SystemManage.IPListItem>({
    url: '/api/ip',
    params
  })
}

/**
 * 修改指定 IP 记录的公开状态。
 * @param ipId ip_dict 表记录 ID。
 * @param params 新公开状态。
 * @returns 更新后的 IP 记录。
 */
export function fetchUpdateIPPublicStatus(
  ipId: number,
  params: Api.SystemManage.IPPublicStatusUpdateParams
) {
  return request.put<Api.SystemManage.IPListItem>({
    url: `/api/ip/${ipId}/public-status`,
    params
  })
}

/**
 * 获取用户管理分页列表。
 * @param params 用户筛选、排序和分页参数。
 * @returns 用户管理分页列表请求结果。
 */
export function fetchGetUserList(params: Api.SystemManage.UserSearchParams) {
  return request.get<Api.SystemManage.UserList>({
    url: '/api/user/list',
    params
  })
}

/**
 * 修改指定用户的等级和服务号告警类型。
 * @param userId users 表记录 ID。
 * @param params 新用户等级和服务号告警类型。
 * @returns 更新后的用户记录。
 */
export function fetchUpdateUser(userId: number, params: Api.SystemManage.UserUpdateParams) {
  return request.put<Api.SystemManage.UserListItem>({
    url: `/api/user/${userId}`,
    params
  })
}

/**
 * 获取当前有效的 CDK 兑换码及剩余时间。
 * @returns 当前 CDK、生成时间、过期时间和服务端时间。
 */
export function fetchGetCurrentCdk() {
  return request.get<Api.SystemManage.CdkInfo>({
    url: '/api/user/cdk/current'
  })
}

/**
 * 获取 HTTP 5xx 错误日志分页列表。
 * @param params 日志排序和分页参数。
 * @returns HTTP 5xx 错误日志分页列表。
 */
export function fetchGetHttpErrorLogList(params: Api.SystemManage.HttpErrorLogSearchParams) {
  return request.get<Api.SystemManage.HttpErrorLogList>({
    url: '/api/system-logs/list',
    params
  })
}

/**
 * 获取当前 FastAPI 进程的 HTTP Prometheus 指标快照。
 * @returns 运行时长、请求量、5xx 数量和请求耗时指标。
 */
export function fetchGetHttpMetrics() {
  return request.get<Api.SystemManage.HttpMetrics>({
    url: '/api/system-logs/metrics'
  })
}

// 获取角色列表
export function fetchGetRoleList(params: Api.SystemManage.RoleSearchParams) {
  return request.get<Api.SystemManage.RoleList>({
    url: '/api/role/list',
    params
  })
}

// 获取菜单列表
export function fetchGetMenuList() {
  return request.get<AppRouteRecord[]>({
    url: '/api/v3/system/menus/simple'
  })
}
