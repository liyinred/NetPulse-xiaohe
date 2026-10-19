import { AppRouteRecord } from '@/types/router'
import { detectionRoutes } from './detection'
import { managementRoutes } from './management'

/**
 * 导出所有模块化路由
 */
export const routeModules: AppRouteRecord[] = [...detectionRoutes, ...managementRoutes]
