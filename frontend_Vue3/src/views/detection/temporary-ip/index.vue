<template>
  <div class="flex flex-col gap-3">
    <section class="art-card-xs overflow-hidden">
      <div class="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
        <div class="min-w-64 flex-1">
          <div class="flex items-center gap-2 text-base font-medium text-g-900">
            <ArtSvgIcon icon="ri:crosshair-2-line" class="text-xl text-theme" />
            <span>临时 IP 探测</span>
          </div>
          <p class="mt-1 text-sm text-g-600">
            自动调用在线的异网与跨省 Agent，并行完成 ICMP、TCP 80、UDP 33434 探测
          </p>
        </div>

        <ElForm
          ref="formRef"
          class="flex min-w-80 flex-1 items-start justify-end gap-2 max-sm:min-w-full max-sm:flex-col"
          :model="form"
          :rules="rules"
          @submit.prevent="handleSubmit"
        >
          <ElFormItem class="mb-0 w-full max-w-xl" prop="targetIp">
            <ElInput
              v-model="form.targetIp"
              maxlength="45"
              clearable
              placeholder="输入公网 IPv4 或 IPv6 地址"
              @keyup.enter="handleSubmit"
            >
              <template #prefix>
                <ArtSvgIcon icon="ri:global-line" />
              </template>
            </ElInput>
          </ElFormItem>
          <ElButton type="primary" :loading="submitting" @click="handleSubmit" v-ripple>
            开始探测
          </ElButton>
        </ElForm>
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

    <div v-if="result" class="grid grid-cols-2 gap-3 max-xl:grid-cols-1">
      <ElCard shadow="never">
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-2">
              <ArtSvgIcon icon="ri:exchange-2-line" class="text-lg text-theme" />
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
              <div class="font-medium text-g-900">{{ formatLatency(row[protocol]) }}</div>
              <div class="text-xs text-g-500">丢包 {{ formatLoss(row[protocol]) }}</div>
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
              <div class="font-medium text-g-900">{{ formatLatency(row[protocol]) }}</div>
              <div class="text-xs text-g-500">丢包 {{ formatLoss(row[protocol]) }}</div>
            </template>
          </ElTableColumn>
        </ElTable>
      </ElCard>
    </div>

    <ElCard v-else shadow="never">
      <ElEmpty description="输入一个公网 IP，探测结果会按异网和跨省节点分别展示" />
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import type { FormInstance, FormItemRule, FormRules, TagProps } from 'element-plus'
  import { fetchCreateOnDemandProbe, fetchGetOnDemandProbe } from '@/api/detection'
  import { validateIPAddress } from '@/utils/form/validator'

  defineOptions({ name: 'TemporaryIPDetection' })

  type ProtocolType = Api.Detection.ProtocolType
  type NodeResult = Api.Detection.OnDemandNodeResult
  type ProtocolResult = Api.Detection.OnDemandProtocolResult

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
  const ispNames: Record<number, string> = { 1: '电信', 2: '移动', 3: '联通', 4: '其他运营商' }
  const protocols: ProtocolType[] = ['icmp', 'tcp', 'udp']
  const terminalStatuses: Api.Detection.OnDemandProbeStatus[] = [
    'completed',
    'partial_completed',
    'failed'
  ]
  const formRef = ref<FormInstance>()
  const form = reactive({ targetIp: '' })
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
   * 格式化省份和运营商编码。
   * @param province 省份编码。
   * @param isp 运营商编码。
   * @returns 可读的网络归属名称。
   */
  function formatNetwork(province: number | null, isp: number | null): string {
    return `${provinceNames[province ?? 0] ?? '未知省份'} · ${ispNames[isp ?? 0] ?? '未知运营商'}`
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
   * 将整数千分比丢包率转换为百分比。
   * @param protocolResult 单协议探测结果。
   * @returns 带百分号的一位小数结果。
   */
  function formatLoss(protocolResult: ProtocolResult): string {
    return `${(protocolResult.loss_rate / 10).toFixed(1)}%`
  }

  /**
   * 格式化单协议平均延迟。
   * @param protocolResult 单协议探测结果。
   * @returns 带 ms 单位的延迟结果。
   */
  function formatLatency(protocolResult: ProtocolResult): string {
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
      if (!terminalStatuses.includes(data.status)) {
        pollTimer = setTimeout(() => void pollResult(queryId), 600)
      }
    } catch {
      if (activeQueryId === queryId) submitting.value = false
    }
  }

  /**
   * 校验目标 IP、创建独立查询并开始刷新结果。
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
      activeQueryId = created.queryId
      await pollResult(created.queryId)
    } finally {
      submitting.value = false
    }
  }

  onBeforeUnmount(() => {
    activeQueryId = undefined
    clearPollTimer()
  })
</script>
