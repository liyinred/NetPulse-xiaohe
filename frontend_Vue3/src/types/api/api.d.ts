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
    }

    /** 单个自然分钟的聚合探测值 */
    type ProbeTrendPoint = [timeId: number, lossRate: number, averageLatencyMs: number]

    /** 单个目标 IP 的探测趋势 */
    interface ProbeTrendSeries {
      targetIpId: number
      targetIp: string
      label: string
      points: ProbeTrendPoint[]
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
      isCrossIsp: boolean
      isCrossProvince: boolean
      isCovered: boolean
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

    /** 当前节点和时间窗口的概括性覆盖报告 */
    interface ProbeReportData {
      sourceProvinceName: string
      sourceIspName: string
      crossIspCovered: boolean
      crossProvinceCovered: boolean
      coveredProvinces: string[]
      rows: ProbeReportRow[]
      previousDayDate: string
      previousDayRows: ProbePeriodReportRow[]
    }

    /** 探测概览查询参数 */
    interface ProbeReportParams {
      sourceIpId: number
      probeMode: ProbeMode
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
      series: ProbeTrendSeries[]
    }

    /** 临时 IP 探测执行状态 */
    type OnDemandProbeStatus =
      | 'queued'
      | 'running'
      | 'completed'
      | 'partial_completed'
      | 'failed'

    /** 临时 IP 探测创建参数 */
    interface OnDemandProbeCreateParams {
      targetIp: string
    }

    /** 临时 IP 探测创建结果 */
    interface OnDemandProbeCreated {
      queryId: number
      executionId: number
      status: OnDemandProbeStatus
      targetIp: string
    }

    /** 单个协议的临时探测结果 */
    interface OnDemandProtocolResult {
      loss_rate: number
      average_latency_ms: number
    }

    /** 单个在线节点的临时探测结果 */
    interface OnDemandNodeResult {
      sourceIpId: number
      isp: number | null
      province: number | null
      icmp: OnDemandProtocolResult
      tcp: OnDemandProtocolResult
      udp: OnDemandProtocolResult
    }

    /** 临时 IP 探测进度和分类结果 */
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
