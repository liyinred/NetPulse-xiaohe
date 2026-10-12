import request from '@/utils/http'

/**
 * 按当前用户等级获取可访问设备关联的探测源节点。
 * @returns 探测节点列表。
 */
export function fetchGetProbeNodes() {
  return request.get<Api.Detection.ProbeNode[]>({
    url: '/api/probes/nodes'
  })
}

/**
 * 获取指定节点、模式和北京时间范围按时间桶聚合的探测趋势。
 * @param params 探测节点、模式和时间范围参数。
 * @returns 聚合粒度及按目标 IP 分组的探测趋势。
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
 * @returns 按省份和运营商聚合的概览，以及昨日全天和晚高峰的平均结果。
 */
export function fetchGetProbeReport(params: Api.Detection.ProbeReportParams) {
  return request.get<Api.Detection.ProbeReportData>({
    url: '/api/probes/report',
    params
  })
}

/**
 * 创建当前用户的即时公网 IP 探测查询。
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
 * 获取当前用户指定即时 IP 查询的进度和节点结果。
 * @param queryId 用户查询记录主键。
 * @returns 当前执行状态及异网、跨省节点结果。
 */
export function fetchGetOnDemandProbe(queryId: number) {
  return request.get<Api.Detection.OnDemandProbeResult>({
    url: `/api/on-demand-probes/${queryId}`
  })
}

/**
 * 获取当前用户可用于双向 MTR 的在线设备及其公网 IP。
 * @returns 在线设备列表。
 */
export function fetchGetMTRDevices() {
  return request.get<Api.Detection.MTRDevice[]>({
    url: '/api/bidirectional-mtr/devices'
  })
}

/**
 * 创建两个在线设备之间的双向 MTR 任务。
 * @param params 两端设备及各自选择的公网 IP。
 * @returns 新建任务标识和状态。
 */
export function fetchCreateMTRTask(params: Api.Detection.MTRCreateParams) {
  return request.post<Api.Detection.MTRCreated>({
    url: '/api/bidirectional-mtr',
    params
  })
}

/**
 * 获取双向 MTR 任务的两个方向路径与执行状态。
 * @param taskId 双向 MTR 主任务主键。
 * @returns 聚合后的方向结果。
 */
export function fetchGetMTRTask(taskId: number) {
  return request.get<Api.Detection.MTRTaskResult>({
    url: `/api/bidirectional-mtr/${taskId}`
  })
}
