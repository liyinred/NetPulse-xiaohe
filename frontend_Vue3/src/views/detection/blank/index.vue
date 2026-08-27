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

      <ElTable
        class="mt-4"
        :data="reportData?.rows ?? []"
        border
        empty-text="当前时间窗口暂无探测结果"
      >
        <ElTableColumn prop="provinceName" label="省份" />
        <ElTableColumn prop="ispName" label="运营商" />
        <ElTableColumn label="覆盖情况">
          <template #default="{ row }">
            <span :class="{ 'text-amber-800 dark:text-amber-600': !row.isCrossIsp }">
              {{ row.isCrossIsp ? '异网' : '同网' }}
            </span>
            /
            <span :class="{ 'text-amber-800 dark:text-amber-600': !row.isCrossProvince }">
              {{ row.isCrossProvince ? '跨省' : '同省' }}
            </span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="ICMP" align="center">
          <ElTableColumn label="平均丢包" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': isReportMetricAlert(row.icmp, 'loss') }">
                {{ formatReportMetric(row.icmp, 'loss') }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="平均延迟" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': isReportMetricAlert(row.icmp, 'latency') }">
                {{ formatReportMetric(row.icmp, 'latency') }}
              </span>
            </template>
          </ElTableColumn>
        </ElTableColumn>
        <ElTableColumn label="TCP" align="center">
          <ElTableColumn label="平均丢包" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': isReportMetricAlert(row.tcp, 'loss') }">
                {{ formatReportMetric(row.tcp, 'loss') }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="平均延迟" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': isReportMetricAlert(row.tcp, 'latency') }">
                {{ formatReportMetric(row.tcp, 'latency') }}
              </span>
            </template>
          </ElTableColumn>
        </ElTableColumn>
        <ElTableColumn label="UDP" align="center">
          <ElTableColumn label="平均丢包" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': isReportMetricAlert(row.udp, 'loss') }">
                {{ formatReportMetric(row.udp, 'loss') }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="平均延迟" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': isReportMetricAlert(row.udp, 'latency') }">
                {{ formatReportMetric(row.udp, 'latency') }}
              </span>
            </template>
          </ElTableColumn>
        </ElTableColumn>
      </ElTable>

      <div class="mb-3 mt-6 flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-base font-medium text-g-900">
          昨日探测<span v-if="reportData">（{{ reportData.previousDayDate }}）</span>
        </h2>
        <span class="text-sm text-g-500">展示格式：全天 / 晚高峰（20:00-22:00）</span>
      </div>
      <ElTable :data="previousDayReportRows" border empty-text="昨日暂无探测结果">
        <ElTableColumn prop="provinceName" label="省份" />
        <ElTableColumn prop="ispName" label="运营商" />
        <ElTableColumn label="ICMP" align="center">
          <ElTableColumn label="平均丢包" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': isPeriodMetricAlert(row, 'icmp', 'loss') }">
                {{ formatPeriodMetric(row, 'icmp', 'loss') }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="平均延迟" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': isPeriodMetricAlert(row, 'icmp', 'latency') }">
                {{ formatPeriodMetric(row, 'icmp', 'latency') }}
              </span>
            </template>
          </ElTableColumn>
        </ElTableColumn>
        <ElTableColumn label="TCP" align="center">
          <ElTableColumn label="平均丢包" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': isPeriodMetricAlert(row, 'tcp', 'loss') }">
                {{ formatPeriodMetric(row, 'tcp', 'loss') }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="平均延迟" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': isPeriodMetricAlert(row, 'tcp', 'latency') }">
                {{ formatPeriodMetric(row, 'tcp', 'latency') }}
              </span>
            </template>
          </ElTableColumn>
        </ElTableColumn>
        <ElTableColumn label="UDP" align="center">
          <ElTableColumn label="平均丢包" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': isPeriodMetricAlert(row, 'udp', 'loss') }">
                {{ formatPeriodMetric(row, 'udp', 'loss') }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="平均延迟" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': isPeriodMetricAlert(row, 'udp', 'latency') }">
                {{ formatPeriodMetric(row, 'udp', 'latency') }}
              </span>
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
        :thicken-on-emphasis="false"
        :use-built-in-palette="true"
        :legend-space="chartTheme.fontSize * 9"
        :legend-font-size="chartTheme.tinyFontSize"
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

  const timeIds = computed(() => {
    if (!trendData.value) return []
    const values: number[] = []
    for (
      let timestamp = trendData.value.startTime;
      timestamp <= trendData.value.endTime;
      timestamp += 60
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
  const previousDayReportRows = computed(() =>
    mergePeriodReportRows(reportData.value?.previousDayRows ?? [])
  )

  /**
   * 格式化报告表格中的协议平均指标。
   * @param summary 协议聚合结果；没有样本时为 null。
   * @param selectedMetric 待展示的丢包或延迟指标。
   * @returns 带单位的指标文案，没有样本时返回短横线。
   */
  function formatReportMetric(
    summary: Api.Detection.ProbeProtocolSummary | null,
    selectedMetric: MetricType
  ): string {
    if (!summary) return '-'
    if (selectedMetric === 'loss') return `${summary.lossRate.toFixed(1)}%`
    return summary.averageLatencyMs === null ? '-' : `${summary.averageLatencyMs.toFixed(1)} ms`
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
   * 按全天、晚高峰顺序格式化昨日对比指标。
   * @param row 合并后的目标网络报告行。
   * @param protocol 协议类型。
   * @param selectedMetric 待展示的丢包或延迟指标。
   * @returns 使用斜杠分隔的全天值和晚高峰值。
   */
  function formatPeriodMetric(
    row: MergedPeriodReportRow,
    protocol: Api.Detection.ProtocolType,
    selectedMetric: MetricType
  ): string {
    const fullDaySummary = row.fullDay?.[protocol] ?? null
    const peakSummary = row.eveningPeak?.[protocol] ?? null
    return `${formatReportMetric(fullDaySummary, selectedMetric)} / ${formatReportMetric(peakSummary, selectedMetric)}`
  }

  /**
   * 判断全天或晚高峰指标是否达到标红阈值。
   * @param row 合并后的目标网络报告行。
   * @param protocol 协议类型。
   * @param selectedMetric 待判断的丢包或延迟指标。
   * @returns 任一时段达到对应失败阈值时返回 true。
   */
  function isPeriodMetricAlert(
    row: MergedPeriodReportRow,
    protocol: Api.Detection.ProtocolType,
    selectedMetric: MetricType
  ): boolean {
    return (
      isReportMetricAlert(row.fullDay?.[protocol] ?? null, selectedMetric) ||
      isReportMetricAlert(row.eveningPeak?.[protocol] ?? null, selectedMetric)
    )
  }

  /**
   * 判断报告指标是否达到不可覆盖的标红阈值。
   * @param summary 协议聚合结果；没有样本时为 null。
   * @param selectedMetric 待判断的丢包或延迟指标。
   * @returns 指标达到对应失败阈值时返回 true。
   */
  function isReportMetricAlert(
    summary: Api.Detection.ProbeProtocolSummary | null,
    selectedMetric: MetricType
  ): boolean {
    if (!summary) return false
    if (selectedMetric === 'loss') return summary.lossRate >= metricAlertValues.loss
    return (
      summary.averageLatencyMs === null || summary.averageLatencyMs >= metricAlertValues.latency
    )
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
   * 将后端稀疏分钟点补齐为 ECharts 所需的完整时间序列。
   * @param data 后端返回的目标 IP 趋势。
   * @param timestamps 完整的自然分钟时间轴。
   * @param selectedMetric 当前选择的丢包或延迟指标。
   * @returns 按目标 IP 分组且缺失分钟为 null 的图表序列。
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
   * 加载当前用户可访问的探测节点并默认选择第一个节点。
   * @returns 无返回值。
   */
  async function loadNodes(): Promise<void> {
    nodeLoading.value = true
    try {
      nodes.value = await fetchGetProbeNodes()
      sourceIpId.value = nodes.value[0]?.id
      await loadProbeData()
    } finally {
      nodeLoading.value = false
    }
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
