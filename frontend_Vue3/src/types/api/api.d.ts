/**
 * API 接口类型定义模块
 *
 * 提供所有后端接口的类型定义
 *
 * ## 主要功能
 *
 * - 通用类型（分页参数、响应结构等）
 * - 认证类型（登录、用户信息等）
 * - 系统管理类型（用户、角色等）
 * - 全局命名空间声明
 *
 * ## 使用场景
 *
 * - API 请求参数类型约束
 * - API 响应数据类型定义
 * - 接口文档类型同步
 *
 * ## 注意事项
 *
 * - 在 .vue 文件使用需要在 eslint.config.mjs 中配置 globals: { Api: 'readonly' }
 * - 使用全局命名空间，无需导入即可使用
 *
 * ## 使用方式
 *
 * ```typescript
 * const qrcode: Api.Auth.WechatQRCode = await fetchCreateWechatQRCode()
 * const response: Api.Auth.UserInfo = await fetchGetUserInfo()
 * ```
 *
 * @module types/api/api
 * @author Art Design Pro Team
 */

declare namespace Api {
  /** 通用类型 */
  namespace Common {
    /** 分页参数 */
    interface PaginationParams {
      /** 当前页码 */
      current: number
      /** 每页条数 */
      size: number
      /** 总条数 */
      total: number
      /** 排序字段 */
      sortField?: string
      /** 排序方向 */
      sortOrder?: 'asc' | 'desc'
    }

    /** 通用搜索参数 */
    type CommonSearchParams = Pick<PaginationParams, 'current' | 'size' | 'sortField' | 'sortOrder'>

    /** 分页响应基础结构 */
    interface PaginatedResponse<T = any> {
      records: T[]
      current: number
      size: number
      total: number
    }

    /** 启用状态 */
    type EnableStatus = '1' | '2'
  }

  /** 认证类型 */
  namespace Auth {
    /** 微信扫码登录二维码 */
    interface WechatQRCode {
      sceneStr: string
      expireSeconds: number
      url: string
      imageUrl: string
    }

    /** 微信扫码登录状态 */
    interface WechatLoginStatus {
      status: 'pending' | 'authenticated' | 'expired'
      token?: string
    }

    /** 用户信息 */
    interface UserInfo {
      buttons: string[]
      roles: string[]
      userId: number
      userName: string
      email: string
      userLevel: number
      avatar?: string
    }
  }

  /** 探测趋势类型 */
  namespace Detection {
    /** 探测模式 */
    type ProbeMode = 1 | 2

    /** 查询时间范围 */
    type ProbeRangeType = '1d' | '2d' | '7d' | 'month'

    /** 探测协议 */
    type ProtocolType = 'icmp' | 'tcp' | 'udp'

    /** 当前用户关联的探测源节点 */
    interface ProbeNode {
      id: number
      ip: string
      label: string
      /** 节点所属设备当前是否在线 */
      online: boolean
    }

    /** 单个目标 IP 的探测趋势，数组下标与完整时间桶轴对齐，无数据的时间桶为 null */
    interface ProbeTrendSeries {
      targetIpId: number
      targetIp: string
      /** 目标 IP 所属运营商编码 */
      isp: number | null
      label: string
      /** 各时间桶平均丢包率百分比 */
      lossRates: Array<number | null>
      /** 各时间桶平均延迟毫秒数 */
      latenciesMs: Array<number | null>
    }

    /** 单个协议的报告聚合结果 */
    interface ProbeProtocolSummary {
      lossRate: number
      averageLatencyMs: number | null
    }

    /** 同省份、同运营商目标节点的报告分组 */
    interface ProbeReportRow {
      province: number | null
      provinceName: string
      isp: number | null
      ispName: string
      icmp: ProbeProtocolSummary | null
      tcp: ProbeProtocolSummary | null
      udp: ProbeProtocolSummary | null
    }

    /** 昨日指定目标网络和时段内的三协议平均结果 */
    interface ProbePeriodReportRow {
      province: number | null
      provinceName: string
      isp: number | null
      ispName: string
      period: 'full_day' | 'evening_peak'
      icmp: ProbeProtocolSummary | null
      tcp: ProbeProtocolSummary | null
      udp: ProbeProtocolSummary | null
    }

    /** 当前节点的统计时间范围及分组报告 */
    interface ProbeReportData {
      startTime: number
      endTime: number
      rows: ProbeReportRow[]
    }

    /** 北京时间昨日日期及全天、晚高峰分时报告 */
    interface ProbePreviousDayReportData {
      date: string
      rows: ProbePeriodReportRow[]
    }

    /** 昨日探测报告查询参数 */
    interface ProbePreviousDayReportParams {
      sourceIpId: number
      probeMode: ProbeMode
    }

    /** 探测概览查询参数 */
    interface ProbeReportParams extends ProbePreviousDayReportParams {
      rangeType: ProbeRangeType
      month?: string
    }

    /** 探测趋势查询参数 */
    interface ProbeTrendParams extends ProbeReportParams {
      protocolType: ProtocolType
    }

    /** 探测趋势查询结果 */
    interface ProbeTrendData {
      startTime: number
      endTime: number
      /** 趋势聚合粒度秒数，时间桶轴从 startTime 按该粒度向下对齐的时间戳开始 */
      intervalSeconds: number
      series: ProbeTrendSeries[]
    }

    /** 即时 IP 探测执行状态 */
    type OnDemandProbeStatus =
      | 'queued'
      | 'running'
      | 'completed'
      | 'partial_completed'
      | 'failed'

    /** 即时 IP 探测创建参数 */
    interface OnDemandProbeCreateParams {
      targetIp: string
    }

    /** 即时 IP 探测创建结果 */
    interface OnDemandProbeCreated {
      queryId: number
      executionId: number
      status: OnDemandProbeStatus
      targetIp: string
    }

    /** 单个协议的即时探测结果 */
    interface OnDemandProtocolResult {
      loss_rate: number
      average_latency_ms: number
    }

    /** 单个在线节点的即时探测结果 */
    interface OnDemandNodeResult {
      sourceIpId: number
      isp: number | null
      province: number | null
      icmp: OnDemandProtocolResult
      tcp: OnDemandProtocolResult
      udp: OnDemandProtocolResult | null
    }

    /** 即时 IP 探测进度和分类结果 */
    interface OnDemandProbeResult {
      executionId: number
      status: OnDemandProbeStatus
      targetIp: string
      ipVersion: 4 | 6
      targetIsp: number | null
      targetProvince: number | null
      totalNodeCount: number
      pendingNodeCount: number
      runningNodeCount: number
      completedNodeCount: number
      timeoutNodeCount: number
      failedNodeCount: number
      results: {
        crossIspResults: OnDemandNodeResult[]
        crossProvinceResults: OnDemandNodeResult[]
      }
    }

    /** 双向 MTR 方向或主任务状态 */
    type MTRStatus = 'queued' | 'running' | 'completed' | 'partial_completed' | 'failed'

    /** 双向 MTR 可选择的公网 IP */
    interface MTRDeviceIP {
      id: number
      ip: string
      ipVersion: 4 | 6
    }

    /** 双向 MTR 可选择的在线节点 */
    interface MTRDevice {
      id: number
      nodeName: string
      ips: MTRDeviceIP[]
    }

    /** 双向 MTR 创建请求 */
    interface MTRCreateParams {
      sourceDeviceId: number
      sourceIpId: number
      targetDeviceId: number
      targetIpId: number
    }

    /** 双向 MTR 创建结果 */
    interface MTRCreated {
      mtrTaskId: number
      status: MTRStatus
    }

    /** 单个 MTR 跳点 */
    interface MTRHop {
      asns: number[]
      networkType: 'public' | 'private' | 'shared' | 'link_local' | 'loopback' | 'special' | 'unknown'
      location: string | null
      ttl: number
      address: string | null
      sent: number
      received: number
      lossRate: number
      averageLatencyMs: number | null
    }

    /** 双向 MTR 单方向结果 */
    interface MTRDirectionResult {
      direction: 'A_TO_B' | 'B_TO_A'
      sourceIp: string
      targetIp: string
      status: MTRStatus
      errorCode: string | null
      hops: MTRHop[]
    }

    /** 双向 MTR 主任务结果 */
    interface MTRTaskResult {
      mtrTaskId: number
      status: MTRStatus
      directions: MTRDirectionResult[]
    }
  }

  /** 系统管理类型 */
  namespace SystemManage {
    /** IP 列表 */
    type IPList = Api.Common.PaginatedResponse<IPListItem>

    /** IP 列表项 */
    interface IPListItem {
      id: number
      ip: string
      ipVersion: number
      publicStatus: 0 | 1
      isp: number | null
      ispName: string
      province: number | null
      provinceName: string
      city: string | null
      updateTime: number
    }

    /** IP 搜索参数 */
    type IPSearchParams = Partial<
      Pick<IPListItem, 'ip' | 'ipVersion' | 'isp' | 'province' | 'city' | 'publicStatus'> &
        Api.Common.CommonSearchParams
    >

    /** IP 新增或刷新请求 */
    interface IPUpsertParams {
      ip: string
      publicStatus: 0 | 1
    }

    /** IP 公开状态修改请求 */
    interface IPPublicStatusUpdateParams {
      publicStatus: 0 | 1
    }

    /** 用户列表 */
    type UserList = Api.Common.PaginatedResponse<UserListItem>

    /** 用户服务号告警类型 */
    type UserAlertType = 0 | 1 | 2 | 3

    /** 用户等级 */
    type UserLevel = 1 | 2 | 9

    /** 用户列表项 */
    interface UserListItem {
      id: number
      openid: string | null
      userLevel: UserLevel
      subscribeStatus: number | null
      alertType: UserAlertType
      createdTime: number | null
      updatedTime: number | null
    }

    /** 用户搜索参数 */
    type UserSearchParams = Partial<
      Pick<UserListItem, 'openid' | 'userLevel' | 'subscribeStatus' | 'alertType'> &
        Api.Common.CommonSearchParams
    >

    /** 用户信息修改请求 */
    interface UserUpdateParams {
      userLevel: UserLevel
      alertType: UserAlertType
    }

    /** HTTP 5xx 错误日志列表 */
    type HttpErrorLogList = Api.Common.PaginatedResponse<HttpErrorLogItem>

    /** HTTP 5xx 错误日志列表项 */
    interface HttpErrorLogItem {
      id: number
      direction: 'inbound' | 'outbound'
      method: string
      path: string
      statusCode: number
      errorType: string
      errorMessage: string
      occurredTime: string
    }

    /** HTTP 错误日志分页与排序参数 */
    type HttpErrorLogSearchParams = Partial<Api.Common.CommonSearchParams>

    /** 当前 FastAPI 进程的 HTTP 指标 */
    interface HttpMetrics {
      processUptimeSeconds: number
      httpRequestTotal: number
      http5xxTotal: number
      averageRequestDurationMs: number
      p95RequestDurationMs: number
      p99RequestDurationMs: number
    }

    /** 角色列表 */
    type RoleList = Api.Common.PaginatedResponse<RoleListItem>

    /** 角色列表项 */
    interface RoleListItem {
      roleId: number
      roleName: string
      roleCode: string
      description: string
      enabled: boolean
      createTime: string
    }

    /** 角色搜索参数 */
    type RoleSearchParams = Partial<
      Pick<RoleListItem, 'roleId' | 'roleName' | 'roleCode' | 'description' | 'enabled'> &
        Api.Common.CommonSearchParams & {
          startTime: string | null
          endTime: string | null
        }
    >
  }
}
