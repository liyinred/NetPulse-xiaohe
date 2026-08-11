import request from '@/utils/http'

/**
 * 获取当前用户关联设备的全部探测源节点。
 * @returns 探测节点列表。
 */
export function fetchGetProbeNodes() {
  return request.get<Api.Detection.ProbeNode[]>({
    url: '/api/probes/nodes'
  })
}

/**
 * 获取指定节点、模式和北京时间范围的分钟探测趋势。
 * @param params 探测节点、模式和时间范围参数。
 * @returns 按目标 IP 分组的探测趋势。
 */
export function fetchGetProbeTrend(params: Api.Detection.ProbeTrendParams) {
  return request.get<Api.Detection.ProbeTrendData>({
    url: '/api/probes/trend',
    params
  })
}
