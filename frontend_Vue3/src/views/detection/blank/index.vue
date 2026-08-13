<template>
  <div class="probe-trend-page art-full-height gap-3">
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
          :disabled="trendLoading || !sourceIpId || (rangeType === 'month' && !month)"
          @click="loadTrend"
        >
          <ArtSvgIcon icon="ri:refresh-line" :class="{ 'animate-spin': trendLoading }" />
          <span>刷新</span>
        </ElButton>
      </div>
    </section>

    <ElCard class="min-h-0 flex-1" body-class="h-full min-h-0 flex flex-col">
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
        <ElEmpty description="当前用户暂无关联探测节点" />
      </div>
      <ArtLineChart
        v-else
        class="min-h-0 flex-1"
        height="100%"
        :x-axis-data="xAxisData"
        :data="chartSeries"
        :line-width="chartTheme.thinLineWidth"
        :line-opacity="0.7"
        :loading="trendLoading"
        :y-axis-min="0"
        :y-axis-max="metric === 'loss' ? 100 : 300"
        :value-unit="metric === 'loss' ? '%' : 'ms'"
        :tooltip-alert-value="metric === 'loss' ? 100 : 300"
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
        :thicken-on-emphasis="false"
        :use-built-in-palette="true"
        :legend-space="chartTheme.fontSize * 8"
        :legend-hover-link="false"
        :shift-legend-exclusive-select="true"
        legend-position="top"
      />
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { useRoute } from 'vue-router'
  import { fetchGetProbeNodes, fetchGetProbeTrend } from '@/api/detection'
  import { useChartOps } from '@/hooks/core/useChart'
  import type { LineDataItem } from '@/types/component/chart'
  import { formatBeijingMinute } from '@/utils/date'

  defineOptions({ name: 'ProbeTrendPage' })

  type MetricType = 'loss' | 'latency'

  const route = useRoute()
  const chartTheme = useChartOps()
  const nodes = ref<Api.Detection.ProbeNode[]>([])
  const sourceIpId = ref<number>()
  const rangeType = ref<Api.Detection.ProbeRangeType>('1d')
  const month = ref(getCurrentBeijingMonth())
  const protocolType = ref<Api.Detection.ProtocolType>('icmp')
  const metric = ref<MetricType>('loss')
  const trendData = ref<Api.Detection.ProbeTrendData>()
  const nodeLoading = ref(false)
  const trendLoading = ref(false)
  let requestSerial = 0

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
   * 查询当前筛选条件对应的探测趋势，并忽略较早请求的迟到响应。
   * @returns 无返回值。
   */
  async function loadTrend(): Promise<void> {
    if (!sourceIpId.value || (rangeType.value === 'month' && !month.value)) return
    const currentSerial = ++requestSerial
    trendData.value = undefined
    trendLoading.value = true
    try {
      const data = await fetchGetProbeTrend({
        sourceIpId: sourceIpId.value,
        probeMode: probeMode.value,
        protocolType: protocolType.value,
        rangeType: rangeType.value,
        month: rangeType.value === 'month' ? month.value : undefined
      })
      if (currentSerial === requestSerial) trendData.value = data
    } finally {
      if (currentSerial === requestSerial) trendLoading.value = false
    }
  }

  /**
   * 加载用户探测节点并默认选择第一个节点。
   * @returns 无返回值。
   */
  async function loadNodes(): Promise<void> {
    nodeLoading.value = true
    try {
      nodes.value = await fetchGetProbeNodes()
      sourceIpId.value = nodes.value[0]?.id
      await loadTrend()
    } finally {
      nodeLoading.value = false
    }
  }

  /**
   * 节点变化后刷新趋势。
   * @returns 无返回值。
   */
  function handleNodeChange(): void {
    void loadTrend()
  }

  /**
   * 时间范围变化后刷新趋势。
   * @returns 无返回值。
   */
  function handleRangeChange(): void {
    void loadTrend()
  }

  /**
   * 协议变化后查询对应状态表的趋势。
   * @returns 无返回值。
   */
  function handleProtocolChange(): void {
    void loadTrend()
  }

  /**
   * 月份变化后切换到月份范围并刷新趋势。
   * @returns 无返回值。
   */
  function handleMonthChange(): void {
    if (!month.value) return
    rangeType.value = 'month'
    void loadTrend()
  }

  watch(probeMode, () => {
    trendData.value = undefined
    void loadTrend()
  })

  onMounted(() => {
    void loadNodes()
  })
</script>
