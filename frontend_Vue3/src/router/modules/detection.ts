import { AppRouteRecord } from '@/types/router'

/**
 * 探测功能菜单路由
 */
export const detectionRoutes: AppRouteRecord[] = [
  {
    path: '/temporary-ip-detection',
    name: 'TemporaryIPDetection',
    component: '/detection/temporary-ip',
    meta: {
      title: '临时IP探测',
      icon: 'ri:crosshair-2-line',
      keepAlive: true
    }
  },
  {
    path: '/bidirectional-mtr',
    name: 'BidirectionalMTR',
    component: '/detection/bidirectional-mtr',
    meta: {
      title: '双向MTR',
      icon: 'ri:route-line',
      keepAlive: true
    }
  },
  {
    path: '/external-network-detection',
    name: 'ExternalNetworkDetection',
    component: '/detection/blank',
    meta: {
      title: '异网探测',
      icon: 'mingcute:route-line'
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
