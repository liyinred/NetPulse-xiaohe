<template>
  <div class="probe-trend-page flex flex-col gap-3">
    <section class="art-card-xs flex flex-wrap items-center gap-x-8 gap-y-3 px-5 py-4">
      <div class="flex min-w-0 flex-1 items-center gap-3">
        <span class="shrink-0 text-sm text-g-700">探测节点</span>
        <ElSelect
          v-model="sourceIpId"
          class="min-w-60 flex-1"
          filterable
          :loading="nodeLoading"
          placeholder="请选择探测节点"
          @change="handleNodeChange"
        >
          <ElOption v-for="node in nodes" :key="node.id" :label="node.label" :value="node.id" />
        </ElSelect>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <span class="shrink-0 text-sm text-g-700">时间范围</span>
        <ElRadioGroup v-model="rangeType" @change="handleRangeChange">
          <ElRadioButton value="1d">最近 1 天</ElRadioButton>
          <ElRadioButton value="2d">最近 2 天</ElRadioButton>
          <ElRadioButton value="7d">最近 7 天</ElRadioButton>
          <ElRadioButton value="month">月份选择框</ElRadioButton>
        </ElRadioGroup>
        <ElDatePicker
          v-model="month"
          class="w-36"
          type="month"
          value-format="YYYY-MM"
          format="YYYY 年 MM 月"
          :disabled-date="disableFutureMonth"
          :disabled="rangeType !== 'month'"
          placeholder="选择月份"
          @change="handleMonthChange"
        />
        <ElButton
          :disabled="
            reportLoading || trendLoading || !sourceIpId || (rangeType === 'month' && !month)
          "
          @click="loadProbeData"
        >
          <ArtSvgIcon
            icon="ri:refresh-line"
            :class="{ 'animate-spin': reportLoading || trendLoading }"
          />
          <span>刷新</span>
        </ElButton>
      </div>
    </section>

    <ElCard v-loading="reportLoading">
      <ElDescriptions v-if="reportData" :column="3" border>
        <ElDescriptionsItem label="源节点归属">
          {{ reportData.sourceProvinceName }}{{ reportData.sourceIspName }}
        </ElDescriptionsItem>
        <ElDescriptionsItem v-if="probeMode === 1" label="异网能力">
          <ElTag :type="reportData.crossIspCovered ? 'success' : 'info'">
            {{ reportData.crossIspCovered ? '可异网' : '不可异网' }}
          </ElTag>
        </ElDescriptionsItem>
        <ElDescriptionsItem v-else label="跨省能力">
          <ElTag :type="reportData.crossProvinceCovered ? 'success' : 'info'">
            {{ reportData.crossProvinceCovered ? '可跨省' : '不可跨省' }}
          </ElTag>
        </ElDescriptionsItem>
        <ElDescriptionsItem label="覆盖省份">
          {{ reportData.coveredProvinces.join('、') || '暂无' }}
        </ElDescriptionsItem>
      </ElDescriptions>

      <div class="mb-3 mt-6 flex flex-wrap items-center gap-2">
        <h2 class="text-base font-medium text-g-900">
          探测汇总<span v-if="reportData">（{{ reportRangeLabel }}）</span>
        </h2>
      </div>
      <ElTable
        class="probe-report-table"
        :data="reportRows"
        :span-method="mergeIspCells"
        border
        empty-text="当前时间窗口暂无探测结果"
      >
        <ElTableColumn prop="ispName" label="运营商" />
        <ElTableColumn prop="provinceName" label="省份" />
        <ElTableColumn
          v-for="protocol in protocols"
          :key="protocol"
          :label="protocol.toUpperCase()"
          align="center"
        >
          <ElTableColumn
            v-for="reportMetric in reportMetrics"
            :key="reportMetric.value"
            :label="reportMetric.label"
            align="right"
          >
            <template #default="{ row }">
              <span :class="getReportMetricClass(row[protocol], reportMetric.value)">
                {{ formatReportMetric(row[protocol], reportMetric.value) }}
              </span>
            </template>
          </ElTableColumn>
        </ElTableColumn>
      </ElTable>

      <div class="mb-3 mt-6 flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-base font-medium text-g-900">
          昨日探测<span v-if="reportData">（{{ reportData.previousDayDate }}）</span>
        </h2>
        <ElTag type="info" effect="light">展示格式：全天 / 晚高峰（20:00-22:00）</ElTag>
      </div>
      <ElTable
        class="probe-report-table"
        :data="previousDayReportRows"
        :span-method="mergeIspCells"
        border
        empty-text="昨日暂无探测结果"
      >
        <ElTableColumn prop="ispName" label="运营商" />
        <ElTableColumn prop="provinceName" label="省份" />
        <ElTableColumn
          v-for="protocol in protocols"
          :key="protocol"
          :label="protocol.toUpperCase()"
          align="center"
        >
          <ElTableColumn
            v-for="reportMetric in reportMetrics"
            :key="reportMetric.value"
            :label="reportMetric.label"
            align="right"
          >
            <template #default="{ row }">
              <template v-for="(period, periodIndex) in reportPeriods" :key="period">
                <template v-if="periodIndex > 0"> / </template>
                <span
                  :class="getReportMetricClass(row[period]?.[protocol] ?? null, reportMetric.value)"
                >
                  {{ formatReportMetric(row[period]?.[protocol] ?? null, reportMetric.value) }}
                </span>
              </template>
            </template>
          </ElTableColumn>
        </ElTableColumn>
      </ElTable>
    </ElCard>

    <ElCard body-class="flex flex-col">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 class="text-base font-medium text-g-900">
          {{ protocolTitle }} {{ pageTitle }}趋势（{{ metricTitle }}）
        </h2>
        <div class="flex flex-wrap items-center gap-4">
          <ElRadioGroup v-model="protocolType" size="small" @change="handleProtocolChange">
            <ElRadioButton value="icmp">ICMP</ElRadioButton>
            <ElRadioButton value="tcp">TCP</ElRadioButton>
            <ElRadioButton value="udp">UDP</ElRadioButton>
          </ElRadioGroup>
          <ElRadioGroup v-model="metric" size="small">
            <ElRadioButton value="loss">丢包</ElRadioButton>
            <ElRadioButton value="latency">延迟</ElRadioButton>
          </ElRadioGroup>
        </div>
      </div>

      <div
        v-if="nodes.length === 0 && !nodeLoading"
        class="flex flex-1 items-center justify-center"
      >
        <ElEmpty description="暂无可用探测节点" />
      </div>
      <ArtLineChart
        v-else
        :height="trendChartHeight"
        :x-axis-data="xAxisData"
        :data="chartSeries"
        :line-width="chartTheme.thinLineWidth"
        :line-opacity="0.7"
        :loading="trendLoading"
        :y-axis-min="0"
        :y-axis-max="metricAlertValues[metric]"
        :value-unit="metric === 'loss' ? '%' : 'ms'"
        :tooltip-alert-value="metricAlertValues[metric]"
        :animation-enabled="false"
        :zero-is-empty="false"
        :show-all-tooltip-series="true"
        :show-legend="true"
        :compact-axis-labels="true"
        :x-axis-label-rotate="20"
        :x-axis-label-margin="chartTheme.fontSize"
        :show-x-axis-tick="true"
        :x-axis-interval="xAxisInterval"
        :soften-x-axis="true"
        :show-y-axis-line="false"
        :show-y-axis-label="false"
        :emphasize-axis="true"
        :compact-tooltip="true"
        :tooltip-font-size="chartTheme.tinyFontSize"
        :tooltip-rows-per-column="14"
        :thicken-on-emphasis="false"
        :use-built-in-palette="true"
        :legend-space="chartTheme.fontSize * 3"
        :legend-font-size="chartTheme.compactLegendFontSize"
        :legend-single-row="true"
        :legend-hover-link="false"
        :shift-legend-exclusive-select="true"
        legend-position="top"
      />
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { useRoute } from 'vue-router'
  import { fetchGetProbeNodes, fetchGetProbeReport, fetchGetProbeTrend } from '@/api/detection'
  import { useChartOps } from '@/hooks/core/useChart'
  import type { LineDataItem } from '@/types/component/chart'
  import { formatBeijingMinute } from '@/utils/date'

  defineOptions({ name: 'ProbeTrendPage' })

  type MetricType = 'loss' | 'latency'
  type MergedPeriodReportRow = {
    province: number | null
    provinceName: string
    isp: number | null
    ispName: string
    fullDay: Api.Detection.ProbePeriodReportRow | null
    eveningPeak: Api.Detection.ProbePeriodReportRow | null
  }

  const route = useRoute()
  const chartTheme = useChartOps()
  const metricAlertValues: Record<MetricType, number> = { loss: 100, latency: 300 }
  const lossRateLevelThresholds = { warning: 5, danger: 15 }
  const protocols: Api.Detection.ProtocolType[] = ['icmp', 'tcp', 'udp']
  const reportMetrics: { value: MetricType; label: string }[] = [
    { value: 'loss', label: '平均丢包' },
    { value: 'latency', label: '平均延迟' }
  ]
  const reportPeriods = ['fullDay', 'eveningPeak'] as const
  const trendChartHeight = `calc(${chartTheme.chartHeight} * 2.4)`
  const nodes = ref<Api.Detection.ProbeNode[]>([])
  const sourceIpId = ref<number>()
  const rangeType = ref<Api.Detection.ProbeRangeType>('1d')
  const month = ref(getCurrentBeijingMonth())
  const protocolType = ref<Api.Detection.ProtocolType>('icmp')
  const metric = ref<MetricType>('loss')
  const reportData = ref<Api.Detection.ProbeReportData>()
  const trendData = ref<Api.Detection.ProbeTrendData>()
  const nodeLoading = ref(false)
  const reportLoading = ref(false)
  const trendLoading = ref(false)
  let reportRequestSerial = 0
  let trendRequestSerial = 0

  const probeMode = computed<Api.Detection.ProbeMode>(() =>
    route.name === 'CrossProvinceDetection' ? 2 : 1
  )
  const pageTitle = computed(() => (probeMode.value === 1 ? '异网探测' : '跨省探测'))
  /**
   * 获取当前协议的大写标题前缀。
   * @returns 当前协议名称。
   */
  const protocolTitle = computed(() => protocolType.value.toUpperCase())
  const metricTitle = computed(() => (metric.value === 'loss' ? '丢包率' : '平均延迟'))

  /**
   * 根据当前筛选条件生成汇总标题中的时间范围名称。
   * @returns 最近天数或所选整月份的简短文案。
   */
  const reportRangeLabel = computed(() => {
    if (rangeType.value === 'month') return `${Number(month.value.slice(5))}整月份`
    const rangeLabels = { '1d': '最近1天', '2d': '最近2天', '7d': '最近7天' }
    return rangeLabels[rangeType.value]
  })

  /**
   * 按后端聚合粒度生成覆盖查询范围的完整时间桶轴。
   * @returns 与趋势数据点对齐的时间桶起点 Unix 时间戳列表。
   */
  const timeIds = computed(() => {
    if (!trendData.value) return []
    const { startTime, endTime, intervalSeconds } = trendData.value
    const values: number[] = []
    for (
      let timestamp = startTime - (startTime % intervalSeconds);
      timestamp <= endTime;
      timestamp += intervalSeconds
    ) {
      values.push(timestamp)
    }
    return values
  })
  const xAxisData = computed(() => timeIds.value.map(formatBeijingMinute))
  const xAxisInterval = computed(() => Math.max(0, Math.ceil(timeIds.value.length / 12) - 1))
  const chartSeries = computed<LineDataItem[]>(() =>
    buildChartSeries(trendData.value, timeIds.value, metric.value)
  )
  /**
   * 按运营商归组当前时间范围的汇总结果。
   * @returns 带运营商合并跨度的表格行。
   */
  const reportRows = computed(() => groupReportRows(reportData.value?.rows ?? []))

  /**
   * 合并昨日时段结果并按运营商归组。
   * @returns 带运营商合并跨度的昨日对比行。
   */
  const previousDayReportRows = computed(() =>
    groupReportRows(mergePeriodReportRows(reportData.value?.previousDayRows ?? []))
  )

  /**
   * 将相同运营商的行连续排列，保留组内顺序并计算合并跨度。
   * @param rows 后端报告行或已合并的昨日对比行。
   * @returns 各组首行记录组长度、后续行记录零跨度的表格行副本。
   */
  function groupReportRows<T extends { isp: number | null }>(
    rows: T[]
  ): (T & { ispRowSpan: number })[] {
    const groups = new Map<number | null, T[]>()
    for (const row of rows) {
      const group = groups.get(row.isp) ?? []
      group.push(row)
      groups.set(row.isp, group)
    }
    return Array.from(groups.values()).flatMap((group) =>
      group.map((row, index) => ({ ...row, ispRowSpan: index === 0 ? group.length : 0 }))
    )
  }

  /**
   * 纵向合并报告表格中的运营商单元格。
   * @param context Element Plus 当前行及列信息。
   * @returns 运营商列使用分组跨度，其他列保留独立单元格。
   */
  function mergeIspCells(context: {
    row: { ispRowSpan: number }
    column: { property: string }
  }): [number, number] {
    if (context.column.property !== 'ispName') return [1, 1]
    return context.row.ispRowSpan > 0 ? [context.row.ispRowSpan, 1] : [0, 0]
  }

  /**
   * 格式化报告表格中的协议平均指标。
   * @param summary 协议聚合结果；没有样本时为 null。
   * @param selectedMetric 待展示的丢包或延迟指标。
   * @returns 带单位的指标文案，延迟无有效样本时返回超时，没有协议结果时返回短横线。
   */
  function formatReportMetric(
    summary: Api.Detection.ProbeProtocolSummary | null,
    selectedMetric: MetricType
  ): string {
    if (!summary) return '-'
    if (selectedMetric === 'loss') return `${summary.lossRate.toFixed(1)}%`
    return summary.averageLatencyMs === null ? '超时' : `${summary.averageLatencyMs.toFixed(1)} ms`
  }

  /**
   * 将昨日分时结果合并为每个省份和运营商一行。
   * @param rows 后端返回的全天和晚高峰分组结果。
   * @returns 按目标省份和运营商合并后的表格行。
   */
  function mergePeriodReportRows(
    rows: Api.Detection.ProbePeriodReportRow[]
  ): MergedPeriodReportRow[] {
    const mergedRows = new Map<string, MergedPeriodReportRow>()
    for (const row of rows) {
      const rowKey = `${row.province ?? 'unknown'}:${row.isp ?? 'unknown'}`
      const mergedRow = mergedRows.get(rowKey) ?? {
        province: row.province,
        provinceName: row.provinceName,
        isp: row.isp,
        ispName: row.ispName,
        fullDay: null,
        eveningPeak: null
      }
      if (row.period === 'full_day') mergedRow.fullDay = row
      else mergedRow.eveningPeak = row
      mergedRows.set(rowKey, mergedRow)
    }
    return Array.from(mergedRows.values())
  }

  /**
   * 根据报告指标返回现有语义文字颜色。
   * @param summary 协议聚合结果；没有样本时为 null。
   * @param selectedMetric 待着色的丢包或延迟指标。
   * @returns 丢包超过 15% 返回红色、超过 5% 返回黄色；延迟沿用失败阈值，其余返回空字符串。
   */
  function getReportMetricClass(
    summary: Api.Detection.ProbeProtocolSummary | null,
    selectedMetric: MetricType
  ): string {
    if (!summary) return ''
    if (selectedMetric === 'loss') {
      if (summary.lossRate > lossRateLevelThresholds.danger) return 'text-danger'
      if (summary.lossRate > lossRateLevelThresholds.warning) return 'text-warning'
      return ''
    }
    return summary.averageLatencyMs === null ||
      summary.averageLatencyMs >= metricAlertValues.latency
      ? 'text-danger'
      : ''
  }

  /**
   * 获取当前北京时间月份。
   * @returns YYYY-MM 格式的北京时间月份。
   */
  function getCurrentBeijingMonth(): string {
    return new Intl.DateTimeFormat('sv-SE', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit'
    }).format(new Date())
  }

  /**
   * 将后端稀疏时间桶数据点补齐为 ECharts 所需的完整时间序列。
   * @param data 后端返回的目标 IP 趋势。
   * @param timestamps 完整的时间桶轴。
   * @param selectedMetric 当前选择的丢包或延迟指标。
   * @returns 按目标 IP 分组且缺失时间桶为 null 的图表序列。
   */
  function buildChartSeries(
    data: Api.Detection.ProbeTrendData | undefined,
    timestamps: number[],
    selectedMetric: MetricType
  ): LineDataItem[] {
    if (!data) return []
    return data.series.map((seriesItem) => {
      const pointValues = new Map(
        seriesItem.points.map((point) => [
          point[0],
          selectedMetric === 'loss' ? point[1] : point[2]
        ])
      )
      return {
        name: seriesItem.label,
        data: timestamps.map((timestamp) => pointValues.get(timestamp) ?? null)
      }
    })
  }

  /**
   * 判断月份选择器中的日期是否晚于当前北京时间月份。
   * @param date 月份面板候选日期。
   * @returns 晚于当前月时返回 true。
   */
  function disableFutureMonth(date: Date): boolean {
    const candidateMonth = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
    return candidateMonth > getCurrentBeijingMonth()
  }

  /**
   * 构建概览与趋势接口共用的查询参数。
   * @returns 当前筛选有效时返回查询参数，否则返回 undefined。
   */
  function buildProbeReportParams(): Api.Detection.ProbeReportParams | undefined {
    if (!sourceIpId.value || (rangeType.value === 'month' && !month.value)) return undefined
    return {
      sourceIpId: sourceIpId.value,
      probeMode: probeMode.value,
      rangeType: rangeType.value,
      month: rangeType.value === 'month' ? month.value : undefined
    }
  }

  /**
   * 查询当前筛选条件对应的概览报告，并忽略较早请求的迟到响应。
   * @returns 无返回值。
   */
  async function loadReport(): Promise<void> {
    const params = buildProbeReportParams()
    if (!params) return
    const currentSerial = ++reportRequestSerial
    reportData.value = undefined
    reportLoading.value = true
    try {
      const data = await fetchGetProbeReport(params)
      if (currentSerial === reportRequestSerial) reportData.value = data
    } finally {
      if (currentSerial === reportRequestSerial) reportLoading.value = false
    }
  }

  /**
   * 查询当前筛选条件对应的探测趋势，并忽略较早请求的迟到响应。
   * @returns 无返回值。
   */
  async function loadTrend(): Promise<void> {
    const params = buildProbeReportParams()
    if (!params) return
    const currentSerial = ++trendRequestSerial
    trendData.value = undefined
    trendLoading.value = true
    try {
      const data = await fetchGetProbeTrend({
        ...params,
        protocolType: protocolType.value
      })
      if (currentSerial === trendRequestSerial) trendData.value = data
    } finally {
      if (currentSerial === trendRequestSerial) trendLoading.value = false
    }
  }

  /**
   * 并行刷新当前筛选条件对应的概览报告与趋势数据。
   * @returns 两类数据请求均结束后的 Promise。
   */
  async function loadProbeData(): Promise<void> {
    await Promise.all([loadReport(), loadTrend()])
  }

  /**
   * 加载探测节点并默认选择首项，结束节点加载状态后刷新报告与趋势。
   * @returns 无返回值。
   */
  async function loadNodes(): Promise<void> {
    nodeLoading.value = true
    try {
      nodes.value = await fetchGetProbeNodes()
      sourceIpId.value = nodes.value[0]?.id
    } finally {
      nodeLoading.value = false
    }
    await loadProbeData()
  }

  /**
   * 节点变化后刷新概览报告与趋势。
   * @returns 无返回值。
   */
  function handleNodeChange(): void {
    void loadProbeData()
  }

  /**
   * 时间范围变化后刷新概览报告与趋势。
   * @returns 无返回值。
   */
  function handleRangeChange(): void {
    void loadProbeData()
  }

  /**
   * 协议变化后查询对应状态表的趋势。
   * @returns 无返回值。
   */
  function handleProtocolChange(): void {
    void loadTrend()
  }

  /**
   * 月份变化后切换到月份范围并刷新概览报告与趋势。
   * @returns 无返回值。
   */
  function handleMonthChange(): void {
    if (!month.value) return
    rangeType.value = 'month'
    void loadProbeData()
  }

  watch(probeMode, () => {
    reportData.value = undefined
    trendData.value = undefined
    void loadProbeData()
  })

  onMounted(() => {
    void loadNodes()
  })
</script>

<style scoped>
  .probe-report-table {
    font-size: var(--el-font-size-small);
  }
</style>
