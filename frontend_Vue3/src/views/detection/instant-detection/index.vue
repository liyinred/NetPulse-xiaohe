<template>
  <div class="flex flex-col gap-3">
    <section class="art-card-xs overflow-hidden">
      <div class="mx-auto max-w-3xl px-5 py-5">
        <ElForm
          ref="formRef"
          class="flex items-start justify-center gap-2 max-sm:flex-col"
          :model="form"
          :rules="rules"
          @submit.prevent="handleSubmit"
        >
          <ElFormItem class="mb-0 w-full" prop="targetIp">
            <ElAutocomplete
              ref="autocompleteRef"
              v-model="form.targetIp"
              class="w-full"
              size="large"
              maxlength="45"
              clearable
              fit-input-width
              :fetch-suggestions="fetchHistorySuggestions"
              :trigger-on-focus="true"
              placeholder="输入公网 IPv4 或 IPv6 地址"
              @keyup.enter="handleSubmit"
            >
              <template #prefix>
                <ArtSvgIcon icon="ri:global-line" />
              </template>
              <template #default="{ item }">
                <div class="flex w-full min-w-0 items-center justify-between gap-3">
                  <span class="truncate">{{ item.value }}</span>
                  <div class="flex shrink-0 items-center gap-2">
                    <span class="text-xs text-g-500">最近探测</span>
                    <button
                      type="button"
                      class="size-5 rounded-full text-g-500 flex-cc hover:bg-g-200 hover:text-danger"
                      title="删除记录"
                      aria-label="删除探测记录"
                      @mousedown.prevent.stop
                      @click.stop="removeProbeTarget(item.value)"
                    >
                      <ArtSvgIcon icon="ri:delete-bin-5-line" class="text-xs" />
                    </button>
                  </div>
                </div>
              </template>
            </ElAutocomplete>
          </ElFormItem>
          <ElButton
            type="primary"
            size="large"
            :loading="submitting"
            @click="handleSubmit"
            v-ripple
          >
            开始探测
          </ElButton>
        </ElForm>
        <p class="mt-1 text-xs text-g-600">
          自动调用在线的异网与跨省IP主机，并行完成 ICMP、TCP、UDP 探测
        </p>
      </div>

      <div v-if="result" class="border-t border-g-300 px-5 py-4">
        <div class="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div>
            <span class="text-xs text-g-500">目标</span>
            <p class="font-medium text-g-900">{{ result.targetIp }}</p>
          </div>
          <ElTag effect="plain">IPv{{ result.ipVersion }}</ElTag>
          <ElTag :type="statusMeta.type" effect="light">{{ statusMeta.label }}</ElTag>
          <span class="text-sm text-g-600">
            {{ formatNetwork(result.targetProvince, result.targetIsp) }}
          </span>
          <span class="ml-auto text-sm text-g-600">
            {{ result.completedNodeCount }} / {{ result.totalNodeCount }} 个节点完成
          </span>
        </div>
        <ElProgress
          class="mt-3"
          :percentage="progressPercentage"
          :status="progressStatus"
          :stroke-width="6"
        />
      </div>
    </section>

    <template v-if="result">
      <div class="grid grid-cols-2 gap-3 max-xl:grid-cols-1">
        <ElCard shadow="never">
          <template #header>
            <div class="flex items-center justify-between gap-3">
              <div class="flex items-center gap-2">
                <ArtSvgIcon icon="mingcute:route-line" class="text-lg text-theme" />
                <span class="font-medium text-g-900">异网节点</span>
              </div>
              <ElTag type="info" effect="plain">
                {{ result.results.crossIspResults.length }} 个结果
              </ElTag>
            </div>
          </template>
          <ElTable
            :data="result.results.crossIspResults"
            empty-text="暂无已完成的异网节点结果"
            table-layout="auto"
          >
            <ElTableColumn label="探测节点" min-width="120">
              <template #default="{ row }">{{ formatNode(row) }}</template>
            </ElTableColumn>
            <ElTableColumn
              v-for="protocol in protocols"
              :key="protocol"
              :label="protocol.toUpperCase()"
              min-width="105"
              align="right"
            >
              <template #default="{ row }">
                <template v-if="row[protocol] !== null">
                  <div class="font-medium text-g-900">{{ formatLatency(row[protocol]) }}</div>
                  <div :class="['text-xs', getLossRateClass(row[protocol])]">
                    丢包 {{ formatLoss(row[protocol]) }}
                  </div>
                </template>
                <span v-else>-</span>
              </template>
            </ElTableColumn>
          </ElTable>
        </ElCard>

        <ElCard shadow="never">
          <template #header>
            <div class="flex items-center justify-between gap-3">
              <div class="flex items-center gap-2">
                <ArtSvgIcon icon="ri:road-map-line" class="text-lg text-theme" />
                <span class="font-medium text-g-900">跨省节点</span>
              </div>
              <ElTag type="info" effect="plain">
                {{ result.results.crossProvinceResults.length }} 个结果
              </ElTag>
            </div>
          </template>
          <ElTable
            :data="result.results.crossProvinceResults"
            empty-text="暂无已完成的跨省节点结果"
            table-layout="auto"
          >
            <ElTableColumn label="探测节点" min-width="120">
              <template #default="{ row }">{{ formatNode(row) }}</template>
            </ElTableColumn>
            <ElTableColumn
              v-for="protocol in protocols"
              :key="protocol"
              :label="protocol.toUpperCase()"
              min-width="105"
              align="right"
            >
              <template #default="{ row }">
                <template v-if="row[protocol] !== null">
                  <div class="font-medium text-g-900">{{ formatLatency(row[protocol]) }}</div>
                  <div :class="['text-xs', getLossRateClass(row[protocol])]">
                    丢包 {{ formatLoss(row[protocol]) }}
                  </div>
                </template>
                <span v-else>-</span>
              </template>
            </ElTableColumn>
          </ElTable>
        </ElCard>
      </div>

      <ElCard v-if="isTerminalResult" shadow="never">
        <template #header>
          <div class="flex items-center gap-2">
            <ArtSvgIcon icon="ri:exchange-2-line" class="text-lg text-theme" />
            <span class="font-medium text-g-900">探测结果概览</span>
          </div>
        </template>
        <ElTable
          :data="provinceCoverageRows"
          :span-method="mergeProvinceCoverageCells"
          border
          table-layout="auto"
          empty-text="暂无可用省份概览"
        >
          <ElTableColumn prop="modeLabel" label="探测类型" min-width="100" />
          <ElTableColumn label="探测能力" min-width="120">
            <template #default="{ row }">
              <ElTag :type="row.available ? 'success' : 'info'">
                {{ row.available ? `可${row.modeLabel}` : `不可${row.modeLabel}` }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="可达省份" min-width="240">
            <template #default="{ row }">
              {{ row.provinces.join('、') || '暂无' }}
            </template>
          </ElTableColumn>
          <ElTableColumn label="异网且跨省" min-width="240">
            <template #default="{ row }">
              {{ row.combinedProvinces.join('、') || '暂无' }}
            </template>
          </ElTableColumn>
        </ElTable>
      </ElCard>
    </template>

    <ElCard v-else shadow="never">
      <ElEmpty description="输入一个公网 IP，探测结果会按异网和跨省节点分别展示" />
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import type {
    AutocompleteFetchSuggestionsCallback,
    AutocompleteInstance,
    FormInstance,
    FormItemRule,
    FormRules,
    TagProps
  } from 'element-plus'
  import { fetchCreateOnDemandProbe, fetchGetOnDemandProbe } from '@/api/detection'
  import { StorageConfig } from '@/utils/storage'
  import { validateIPAddress } from '@/utils/form/validator'
  import { ISP_NAMES } from '@/utils/constants'

  defineOptions({ name: 'InstantDetection' })

  type ProtocolType = Api.Detection.ProtocolType
  type NodeResult = Api.Detection.OnDemandNodeResult
  type ProtocolResult = Api.Detection.OnDemandProtocolResult
  interface ProvinceCoverageRow {
    modeLabel: '异网' | '跨省'
    available: boolean
    provinces: string[]
    combinedProvinces: string[]
  }
  interface ProbeHistorySuggestion {
    value: string
  }

  const provinceNames: Record<number, string> = {
    2: '北京',
    3: '福建',
    4: '甘肃',
    5: '广东',
    6: '广西',
    7: '贵州',
    8: '海南',
    9: '河北',
    10: '河南',
    11: '黑龙江',
    12: '湖北',
    13: '湖南',
    14: '吉林',
    15: '江苏',
    16: '江西',
    17: '辽宁',
    18: '内蒙古',
    19: '宁夏',
    20: '青海',
    21: '山东',
    22: '山西',
    23: '陕西',
    24: '上海',
    25: '四川',
    26: '天津',
    27: '西藏',
    28: '新疆',
    29: '云南',
    30: '浙江',
    31: '重庆',
    32: '安徽',
    33: '香港',
    34: '台湾',
    35: '澳门'
  }
  const protocols: ProtocolType[] = ['icmp', 'tcp', 'udp']
  const coverageFailureThresholds = { lossRate: 1000, latencyMs: 300 }
  const lossRateWarningThreshold = 100
  const probeHistoryLimit = 10
  const probeHistoryStorageKey = StorageConfig.generateStorageKey('temporary-ip-history')
  const terminalStatuses: Api.Detection.OnDemandProbeStatus[] = [
    'completed',
    'partial_completed',
    'failed'
  ]
  const formRef = ref<FormInstance>()
  const autocompleteRef = ref<AutocompleteInstance>()
  const form = reactive({ targetIp: '' })
  const probeHistory = useStorage<string[]>(probeHistoryStorageKey, [])
  const submitting = ref(false)
  const result = ref<Api.Detection.OnDemandProbeResult>()
  let pollTimer: ReturnType<typeof setTimeout> | undefined
  let activeQueryId: number | undefined

  /**
   * 校验输入内容为标准 IPv4 或 IPv6 地址。
   * @param _rule Element Plus 当前表单规则。
   * @param value 当前 IP 输入值。
   * @param callback Element Plus 校验回调。
   * @returns 无返回值。
   */
  const validateIPRule: FormItemRule['validator'] = (_rule, value, callback) => {
    if (!validateIPAddress(String(value).trim())) {
      callback(new Error('请输入标准 IPv4 或 IPv6 地址'))
      return
    }
    callback()
  }

  const rules: FormRules = {
    targetIp: [
      { required: true, message: '请输入目标 IP', trigger: 'blur' },
      { validator: validateIPRule, trigger: 'blur' }
    ]
  }

  /**
   * 根据当前输入返回最近探测过的 IP 建议。
   * @param queryString 当前输入框内容。
   * @param callback Element Plus 建议列表回调。
   * @returns 无返回值。
   */
  function fetchHistorySuggestions(
    queryString: string,
    callback: AutocompleteFetchSuggestionsCallback
  ): void {
    const normalizedQuery = queryString.trim().toLowerCase()
    const suggestions: ProbeHistorySuggestion[] = probeHistory.value
      .filter((targetIp) => targetIp.toLowerCase().startsWith(normalizedQuery))
      .map((targetIp) => ({ value: targetIp }))
    callback(suggestions)
  }

  /**
   * 将成功创建探测的规范目标 IP 保存为最近使用记录。
   * @param targetIp 后端返回的规范 IPv4 或 IPv6 地址。
   * @returns 无返回值。
   */
  function rememberProbeTarget(targetIp: string): void {
    probeHistory.value = [
      targetIp,
      ...probeHistory.value.filter((historyIp) => historyIp !== targetIp)
    ].slice(0, probeHistoryLimit)
  }

  /**
   * 删除指定探测历史并立即刷新当前建议列表。
   * @param targetIp 需要删除的规范 IPv4 或 IPv6 地址。
   * @returns 无返回值。
   */
  function removeProbeTarget(targetIp: string): void {
    probeHistory.value = probeHistory.value.filter((historyIp) => historyIp !== targetIp)
    void autocompleteRef.value?.getData(form.targetIp)
  }

  /**
   * 根据当前执行状态提供标签文案和语义颜色。
   * @returns 当前状态对应的标签元数据。
   */
  const statusMeta = computed<{ label: string; type: TagProps['type'] }>(() => {
    const metadata: Record<
      Api.Detection.OnDemandProbeStatus,
      { label: string; type: TagProps['type'] }
    > = {
      queued: { label: '等待节点领取', type: 'info' },
      running: { label: '探测中', type: 'warning' },
      completed: { label: '全部完成', type: 'success' },
      partial_completed: { label: '部分完成', type: 'warning' },
      failed: { label: '未获得结果', type: 'danger' }
    }
    return metadata[result.value?.status ?? 'queued']
  })
  /**
   * 根据已进入终态的节点数量计算执行进度。
   * @returns 0 至 100 的整数进度。
   */
  const progressPercentage = computed(() => {
    if (!result.value?.totalNodeCount) return result.value?.status === 'failed' ? 100 : 0
    const terminalCount =
      result.value.completedNodeCount + result.value.timeoutNodeCount + result.value.failedNodeCount
    return Math.round((terminalCount / result.value.totalNodeCount) * 100)
  })
  /**
   * 根据执行终态提供进度条语义状态。
   * @returns 成功、异常或默认进度状态。
   */
  const progressStatus = computed<'success' | 'exception' | undefined>(() => {
    if (result.value?.status === 'completed') return 'success'
    if (result.value?.status === 'failed') return 'exception'
    return undefined
  })
  /**
   * 判断当前执行是否已经进入不会继续变化的终态。
   * @returns 执行完成、部分完成或失败时返回 true。
   */
  const isTerminalResult = computed(() =>
    result.value ? terminalStatuses.includes(result.value.status) : false
  )
  /**
   * 按异网、跨省及两者交集生成当前目标 IP 的可达省份概览。
   * @returns 两类探测能力及同时满足两类能力的去重省份列表。
   */
  const provinceCoverageRows = computed<ProvinceCoverageRow[]>(() => {
    if (!result.value) return []
    const crossIspProvinces = collectCoveredProvinces(result.value.results.crossIspResults)
    const crossProvinceProvinces = collectCoveredProvinces(
      result.value.results.crossProvinceResults
    )
    const crossProvinceSet = new Set(crossProvinceProvinces)
    const combinedProvinces = crossIspProvinces.filter((province) => crossProvinceSet.has(province))
    return [
      {
        modeLabel: '异网',
        available: crossIspProvinces.length > 0,
        provinces: crossIspProvinces,
        combinedProvinces
      },
      {
        modeLabel: '跨省',
        available: crossProvinceProvinces.length > 0,
        provinces: crossProvinceProvinces,
        combinedProvinces
      }
    ]
  })

  /**
   * 纵向合并同时具备异网与跨省能力的可达省份列。
   * @param context Element Plus 当前表格行与列索引。
   * @returns 当前单元格的行列跨度。
   */
  function mergeProvinceCoverageCells(context: {
    rowIndex: number
    columnIndex: number
  }): [number, number] {
    if (context.columnIndex !== 3) return [1, 1]
    if (context.rowIndex === 0) return [2, 1]
    if (context.rowIndex === 1) return [0, 0]
    return [1, 1]
  }

  /**
   * 格式化省份和运营商编码。
   * @param province 省份编码。
   * @param isp 运营商编码。
   * @returns 可读的网络归属名称。
   */
  function formatNetwork(province: number | null, isp: number | null): string {
    return `${provinceNames[province ?? 0] ?? '未知省份'}${ISP_NAMES[isp ?? 0] ?? '未知运营商'}`
  }

  /**
   * 格式化节点结果的展示名称。
   * @param node 单个已完成节点结果。
   * @returns 省份、运营商与节点编号组合名称。
   */
  function formatNode(node: NodeResult): string {
    return `${formatNetwork(node.province, node.isp)} #${node.sourceIpId}`
  }

  /**
   * 判断节点已执行的协议结果是否均未达到覆盖失败阈值。
   * @param node 单个已完成节点结果。
   * @returns 已执行协议均可达时返回 true，未执行的 UDP 不参与判断。
   */
  function isNodeCovered(node: NodeResult): boolean {
    return protocols.every((protocol) => {
      const protocolResult = node[protocol]
      return (
        protocolResult === null ||
        (protocolResult.loss_rate < coverageFailureThresholds.lossRate &&
          protocolResult.average_latency_ms < coverageFailureThresholds.latencyMs)
      )
    })
  }

  /**
   * 按现有概览规则汇总未出现节点失败的已知省份。
   * @param nodes 同一探测分类下的已完成节点结果。
   * @returns 按省份编码排序的去重省份名称。
   */
  function collectCoveredProvinces(nodes: NodeResult[]): string[] {
    const coverageByProvince = new Map<number, boolean>()
    nodes.forEach((node) => {
      if (node.province === null || !provinceNames[node.province]) return
      const currentCoverage = coverageByProvince.get(node.province) ?? true
      coverageByProvince.set(node.province, currentCoverage && isNodeCovered(node))
    })
    return [...coverageByProvince.entries()]
      .filter(([, covered]) => covered)
      .sort(([leftProvince], [rightProvince]) => leftProvince - rightProvince)
      .map(([province]) => provinceNames[province])
  }

  /**
   * 将整数千分比丢包率转换为百分比。
   * @param protocolResult 单协议探测结果；未执行时为 null。
   * @returns 带百分号的一位小数结果；未执行时返回短横线。
   */
  function formatLoss(protocolResult: ProtocolResult | null): string {
    if (protocolResult === null) return '-'
    return `${(protocolResult.loss_rate / 10).toFixed(1)}%`
  }

  /**
   * 根据丢包率返回表格数值的语义文字颜色。
   * @param protocolResult 单个协议的按需探测结果；未执行时为 null。
   * @returns 百分之百时返回危险色，高于百分之十时返回警告色，其余返回默认次要文字色。
   */
  function getLossRateClass(protocolResult: ProtocolResult | null): string {
    if (protocolResult === null) return 'text-g-500'
    if (protocolResult.loss_rate === coverageFailureThresholds.lossRate) return 'text-danger'
    if (protocolResult.loss_rate > lossRateWarningThreshold) return 'text-warning'
    return 'text-g-500'
  }

  /**
   * 格式化单协议平均延迟。
   * @param protocolResult 单协议探测结果；未执行时为 null。
   * @returns 带 ms 单位的延迟结果；未执行时返回短横线。
   */
  function formatLatency(protocolResult: ProtocolResult | null): string {
    if (protocolResult === null) return '-'
    return `${protocolResult.average_latency_ms} ms`
  }

  /**
   * 清理尚未触发的结果轮询定时器。
   * @returns 无返回值。
   */
  function clearPollTimer(): void {
    if (pollTimer) clearTimeout(pollTimer)
    pollTimer = undefined
  }

  /**
   * 获取一次查询进度，并在活动状态下继续短轮询。
   * @param queryId 当前用户查询记录主键。
   * @returns 本次结果请求结束后的 Promise。
   */
  async function pollResult(queryId: number): Promise<void> {
    try {
      const data = await fetchGetOnDemandProbe(queryId)
      if (activeQueryId !== queryId) return
      result.value = data
      if (terminalStatuses.includes(data.status)) {
        submitting.value = false
        return
      }
      pollTimer = setTimeout(() => void pollResult(queryId), 600)
    } catch {
      if (activeQueryId === queryId) submitting.value = false
    }
  }

  /**
   * 校验目标 IP、创建独立查询并保持加载状态直至执行终态。
   * @returns 提交与首次结果请求结束后的 Promise。
   */
  async function handleSubmit(): Promise<void> {
    if (!formRef.value || submitting.value) return
    try {
      await formRef.value.validate()
    } catch {
      return
    }
    clearPollTimer()
    submitting.value = true
    result.value = undefined
    try {
      const created = await fetchCreateOnDemandProbe({ targetIp: form.targetIp.trim() })
      rememberProbeTarget(created.targetIp)
      activeQueryId = created.queryId
      await pollResult(created.queryId)
    } catch {
      submitting.value = false
    }
  }

  onBeforeUnmount(() => {
    activeQueryId = undefined
    clearPollTimer()
  })
</script>
