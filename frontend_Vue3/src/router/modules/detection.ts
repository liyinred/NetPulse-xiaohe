import { AppRouteRecord } from '@/types/router'

/**
 * 探测功能菜单路由
 */
export const detectionRoutes: AppRouteRecord[] = [
  {
    path: '/external-network-detection',
    name: 'ExternalNetworkDetection',
    component: '/detection/blank',
    meta: {
      title: '异网探测',
      icon: 'ri:radar-line'
    }
  },
  {
    path: '/cross-province-detection',
    name: 'CrossProvinceDetection',
    component: '/detection/blank',
    meta: {
      title: '跨省探测',
      icon: 'ri:road-map-line'
    }
  }
]
