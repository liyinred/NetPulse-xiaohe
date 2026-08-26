import request from '@/utils/http'

/**
 * 按当前用户等级获取可访问且已有结果的探测源节点。
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

/**
 * 获取指定节点、模式和北京时间范围的概览报告。
 * @param params 探测节点、模式和时间范围参数。
 * @returns 按省份和运营商聚合的三协议概览报告。
 */
export function fetchGetProbeReport(params: Api.Detection.ProbeReportParams) {
  return request.get<Api.Detection.ProbeReportData>({
    url: '/api/probes/report',
    params
  })
}

/**
 * 创建当前用户的临时公网 IP 探测查询。
 * @param params 用户输入的单个目标 IP。
 * @returns 独立查询标识和共享执行初始状态。
 */
export function fetchCreateOnDemandProbe(params: Api.Detection.OnDemandProbeCreateParams) {
  return request.post<Api.Detection.OnDemandProbeCreated>({
    url: '/api/on-demand-probes',
    params
  })
}

/**
 * 获取当前用户指定临时 IP 查询的进度和节点结果。
 * @param queryId 用户查询记录主键。
 * @returns 当前执行状态及异网、跨省节点结果。
 */
export function fetchGetOnDemandProbe(queryId: number) {
  return request.get<Api.Detection.OnDemandProbeResult>({
    url: `/api/on-demand-probes/${queryId}`
  })
}
