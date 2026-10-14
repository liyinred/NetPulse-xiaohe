import { AppRouteRecord } from '@/types/router'

/**
 * 探测功能菜单路由
 */
export const detectionRoutes: AppRouteRecord[] = [
  {
    path: '/instant-detection',
    name: 'InstantDetection',
    component: '/detection/instant-detection',
    meta: {
      title: '即时探测',
      icon: 'ri:pulse-line',
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
    path: '/probe-analysis',
    name: 'ProbeAnalysis',
    component: '/detection/probe-analysis',
    meta: {
      title: '探测分析',
      icon: 'mingcute:route-line'
    }
  }
]
