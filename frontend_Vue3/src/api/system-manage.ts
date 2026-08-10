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

// 获取用户列表
export function fetchGetUserList(params: Api.SystemManage.UserSearchParams) {
  return request.get<Api.SystemManage.UserList>({
    url: '/api/user/list',
    params
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
