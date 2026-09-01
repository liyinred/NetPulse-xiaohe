import { AppRouteRecord } from '@/types/router'

/**
 * 管理功能菜单路由
 */
export const managementRoutes: AppRouteRecord[] = [
  {
    path: '/ip-management',
    name: 'IpManagement',
    component: '/system/ip-management',
    meta: {
      title: 'IP管理',
      icon: 'ri:server-line',
      roles: ['R_ADMIN']
    }
  },
  {
    path: '/user-management',
    name: 'UserManagement',
    component: '/system/user',
    meta: {
      title: '用户管理',
      icon: 'ri:user-settings-line',
      roles: ['R_ADMIN']
    }
  },
  {
    path: '/system-logs',
    name: 'SystemLogs',
    component: '/system/system-logs',
    meta: {
      title: '系统日志',
      icon: 'ri:file-list-3-line',
      roles: ['R_ADMIN']
    }
  }
]
