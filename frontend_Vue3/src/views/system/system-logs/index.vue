<template>
  <div class="system-logs-page art-full-height">
    <section
      class="flex-none"
      aria-labelledby="prometheus-metrics-title"
      v-loading="metricsLoading"
    >
      <div class="flex-c gap-2">
        <span
          class="size-2 animate-pulse rounded-full bg-success ring-4 ring-success/20 motion-reduce:animate-none"
          aria-hidden="true"
        ></span>
        <h2 id="prometheus-metrics-title" class="text-lg font-medium text-g-900">
          Prometheus 指标
        </h2>
      </div>

      <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
        <ArtStatsCard
          v-for="metric in metricCards"
          :key="metric.key"
          box-style="!h-24 !py-3"
          :title="metric.title"
          title-class="text-sm font-medium text-g-600"
          :count="metric.count"
          count-class="text-lg font-medium"
          :decimals="metric.decimals"
          :suffix="metric.suffix"
        />
      </div>
    </section>

    <ElCard class="art-table-card">
      <ArtTableHeader v-model:columns="columnChecks" :loading="loading" @refresh="handleRefresh" />
      <ArtTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        :pagination-options="paginationOptions"
        :default-sort="defaultSort"
        @sort-change="handleSortChange"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { ElTag } from 'element-plus'
  import { fetchGetHttpErrorLogList, fetchGetHttpMetrics } from '@/api/system-manage'
  import { useTable } from '@/hooks/core/useTable'

  defineOptions({ name: 'SystemLogs' })

  type HttpErrorLogItem = Api.SystemManage.HttpErrorLogItem

  const METRICS_REFRESH_INTERVAL_MS = 30_000

  interface TableSortChange {
    prop: keyof HttpErrorLogItem
    order: 'ascending' | 'descending' | null
  }

  const defaultMetrics: Api.SystemManage.HttpMetrics = {
    processUptimeSeconds: 0,
    httpRequestTotal: 0,
    http5xxTotal: 0,
    averageRequestDurationMs: 0,
    p95RequestDurationMs: 0,
    p99RequestDurationMs: 0
  }
  const metrics = ref<Api.SystemManage.HttpMetrics>(defaultMetrics)
  const metricsLoading = ref(false)
  let metricsRefreshStarted = false
  const defaultSort = { prop: 'occurredTime', order: 'descending' as const }
  const paginationOptions = { pageSizes: [25, 50, 100] }
  const searchParams = reactive<Api.SystemManage.HttpErrorLogSearchParams>({
    sortField: 'occurredTime',
    sortOrder: 'desc'
  })

  /**
   * 将秒级进程运行时长转换为分钟、小时或天。
   * @param totalSeconds 进程运行总秒数。
   * @returns 适合指标卡展示的数值、小数位和单位。
   */
  function formatProcessUptime(totalSeconds: number) {
    if (totalSeconds < 3600) {
      return { count: totalSeconds / 60, decimals: 0, suffix: ' 分钟' }
    }
    if (totalSeconds < 86400) {
      return { count: totalSeconds / 3600, decimals: 1, suffix: ' 小时' }
    }
    return { count: totalSeconds / 86400, decimals: 1, suffix: ' 天' }
  }

  const metricCards = computed(() => {
    const uptime = formatProcessUptime(metrics.value.processUptimeSeconds)
    return [
      {
        key: 'uptime',
        title: '进程运行时长',
        ...uptime
      },
      {
        key: 'requests',
        title: 'HTTP 请求总数',
        count: metrics.value.httpRequestTotal,
        decimals: 0,
        suffix: ''
      },
      {
        key: 'errors',
        title: 'HTTP 5xx 总数',
        count: metrics.value.http5xxTotal,
        decimals: 0,
        suffix: ''
      },
      {
        key: 'average',
        title: '平均请求耗时',
        count: metrics.value.averageRequestDurationMs,
        decimals: 2,
        suffix: ' ms'
      },
      {
        key: 'p95',
        title: 'P95 请求耗时',
        count: metrics.value.p95RequestDurationMs,
        decimals: 2,
        suffix: ' ms'
      },
      {
        key: 'p99',
        title: 'P99 请求耗时',
        count: metrics.value.p99RequestDurationMs,
        decimals: 2,
        suffix: ' ms'
      }
    ]
  })

  const {
    columns,
    columnChecks,
    data,
    loading,
    pagination,
    getData,
    replaceSearchParams,
    handleSizeChange,
    handleCurrentChange,
    refreshData
  } = useTable({
    core: {
      apiFn: fetchGetHttpErrorLogList,
      apiParams: {
        current: 1,
        size: 25,
        ...searchParams
      },
      columnsFactory: () => [
        { type: 'globalIndex', width: 76, label: '序号' },
        {
          prop: 'direction',
          label: '方向',
          width: 110,
          sortable: 'custom',
          formatter: (row) =>
            h(
              ElTag,
              { type: row.direction === 'inbound' ? 'primary' : 'success', effect: 'plain' },
              () => (row.direction === 'inbound' ? '入站' : '出站')
            )
        },
        {
          prop: 'method',
          label: '请求方法',
          width: 110,
          sortable: 'custom',
          formatter: (row) => h('span', { class: 'font-mono font-medium' }, row.method)
        },
        {
          prop: 'path',
          label: '请求路径',
          minWidth: 220,
          sortable: 'custom',
          showOverflowTooltip: true
        },
        {
          prop: 'statusCode',
          label: '状态码',
          width: 105,
          sortable: 'custom',
          formatter: (row) => h(ElTag, { type: 'danger' }, () => String(row.statusCode))
        },
        {
          prop: 'errorType',
          label: '错误类型',
          minWidth: 160,
          sortable: 'custom',
          showOverflowTooltip: true
        },
        {
          prop: 'errorMessage',
          label: '错误信息',
          minWidth: 280,
          showOverflowTooltip: true
        },
        {
          prop: 'occurredTime',
          label: '发生时间',
          width: 180,
          sortable: 'custom'
        }
      ]
    }
  })

  /**
   * 加载 Prometheus 指标卡片数据。
   * @returns 指标请求完成后的 Promise。
   */
  async function loadMetrics(): Promise<void> {
    if (metricsLoading.value) return
    metricsLoading.value = true
    try {
      metrics.value = await fetchGetHttpMetrics()
    } catch {
      // HTTP 层已经统一展示错误消息，保留上一次成功指标。
    } finally {
      metricsLoading.value = false
    }
  }

  const { pause: pauseMetricsRefresh, resume: resumeMetricsRefresh } = useIntervalFn(
    loadMetrics,
    METRICS_REFRESH_INTERVAL_MS,
    { immediate: false }
  )

  /**
   * 启动当前页面的 Prometheus 指标定时刷新。
   * @returns 无返回值。
   */
  function startMetricsRefresh(): void {
    if (metricsRefreshStarted) return
    metricsRefreshStarted = true
    void loadMetrics()
    resumeMetricsRefresh()
  }

  /**
   * 停止当前页面的 Prometheus 指标定时刷新。
   * @returns 无返回值。
   */
  function stopMetricsRefresh(): void {
    metricsRefreshStarted = false
    pauseMetricsRefresh()
  }

  /**
   * 同时刷新指标和错误日志表格。
   * @returns 两项刷新均结束后的 Promise。
   */
  async function handleRefresh(): Promise<void> {
    await Promise.allSettled([loadMetrics(), refreshData()])
  }

  /**
   * 将表格排序事件转换为后端分页排序协议。
   * @param sortChange 表格排序字段和方向。
   * @returns 无返回值。
   */
  function handleSortChange(sortChange: TableSortChange): void {
    searchParams.sortField = sortChange.order ? sortChange.prop : 'occurredTime'
    searchParams.sortOrder = sortChange.order === 'ascending' ? 'asc' : 'desc'
    replaceSearchParams(searchParams)
    void getData()
  }

  onMounted(startMetricsRefresh)
  onActivated(startMetricsRefresh)
  onDeactivated(stopMetricsRefresh)
  onUnmounted(stopMetricsRefresh)
</script>
