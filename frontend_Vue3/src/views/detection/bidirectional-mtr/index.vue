<template>
  <div class="flex flex-col gap-3">
    <section class="art-card-xs overflow-hidden">
      <div class="mx-auto max-w-4xl px-5 py-5">
        <ElForm class="grid grid-cols-2 gap-x-4 max-md:grid-cols-1" label-position="top">
          <ElFormItem label="节点 A">
            <ElSelect v-model="form.sourceDeviceId" class="w-full" placeholder="选择在线节点" @change="handleSourceChange">
              <ElOption v-for="device in devices" :key="device.id" :label="formatNode(device)" :value="device.id" :disabled="device.id === form.targetDeviceId" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="节点 A 公网 IP">
            <ElSelect v-model="form.sourceIpId" class="w-full" placeholder="选择公网 IP">
              <ElOption v-for="ip in sourceIPs" :key="ip.id" :label="formatIP(ip)" :value="ip.id" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="节点 B">
            <ElSelect v-model="form.targetDeviceId" class="w-full" placeholder="选择在线节点" @change="handleTargetChange">
              <ElOption v-for="device in devices" :key="device.id" :label="formatNode(device)" :value="device.id" :disabled="device.id === form.sourceDeviceId" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="节点 B 公网 IP">
            <ElSelect v-model="form.targetIpId" class="w-full" placeholder="选择与节点 A 相同地址族的公网 IP">
              <ElOption v-for="ip in targetIPs" :key="ip.id" :label="formatIP(ip)" :value="ip.id" />
            </ElSelect>
          </ElFormItem>
        </ElForm>
        <div class="flex items-center justify-between gap-3 max-sm:flex-col max-sm:items-stretch">
          <p class="text-xs text-g-600">两个在线节点分别执行 A → B 与 B → A 的 ICMP MTR</p>
          <ElButton type="primary" :loading="submitting" :disabled="!canSubmit" @click="handleSubmit">开始双向 MTR</ElButton>
        </div>
      </div>
    </section>

    <div v-if="result" class="grid grid-cols-2 gap-3 max-xl:grid-cols-1">
      <ElCard v-for="direction in result.directions" :key="direction.direction" shadow="never">
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-2">
              <ArtSvgIcon icon="ri:route-line" class="text-lg text-theme" />
              <div class="flex flex-col">
                <span class="font-medium text-g-900">{{ formatDirectionNodes(direction.direction) }}</span>
                <span class="text-xs text-g-500">{{ direction.sourceIp }} → {{ direction.targetIp }}</span>
              </div>
            </div>
            <ElTag :type="getStatusMeta(direction.status).type" effect="light">{{ getStatusMeta(direction.status).label }}</ElTag>
          </div>
        </template>
        <ElAlert v-if="direction.errorCode" :title="`执行失败：${direction.errorCode}`" type="error" :closable="false" class="mb-3" />
        <ElTable :data="direction.hops" empty-text="等待设备执行并上报路径" table-layout="auto">
          <ElTableColumn prop="ttl" label="TTL" width="70" />
          <ElTableColumn prop="address" label="跳点 IP" min-width="145"><template #default="{ row }">{{ row.address ?? '*' }}</template></ElTableColumn>
          <ElTableColumn label="AS 码"><template #default="{ row }">{{ formatASNs(row) }}</template></ElTableColumn>
          <ElTableColumn label="地理位置"><template #default="{ row }">{{ formatLocation(row) }}</template></ElTableColumn>
          <ElTableColumn label="丢包" min-width="90" align="right"><template #default="{ row }">{{ formatLoss(row.lossRate) }}</template></ElTableColumn>
          <ElTableColumn label="平均延迟" min-width="105" align="right"><template #default="{ row }">{{ row.averageLatencyMs === null ? '-' : `${row.averageLatencyMs} ms` }}</template></ElTableColumn>
        </ElTable>
      </ElCard>
    </div>
    <ElCard v-else shadow="never"><ElEmpty description="选择两个在线节点及其公网 IP 后，即可查看双向 MTR 逐跳路径" /></ElCard>
  </div>
</template>

<script setup lang="ts">
  import type { TagProps } from 'element-plus'
  import { fetchCreateMTRTask, fetchGetMTRDevices, fetchGetMTRTask } from '@/api/detection'

  defineOptions({ name: 'BidirectionalMTR' })

  const networkTypeLabels: Record<Api.Detection.MTRHop['networkType'], string> = {
    public: '公网', private: '私有网络', shared: '共享地址（运营商 CGNAT）',
    link_local: '链路本地', loopback: '回环', special: '特殊地址', unknown: '-'
  }

  /**
   * 合并展示跳点位置与网络类型，并去除省市间的分隔符。
   * @param hop 当前跳点信息。
   * @returns 公网地理位置、非公网类型或缺失占位符。
   */
  function formatLocation(hop: Api.Detection.MTRHop): string {
    if (hop.networkType !== 'public' && hop.networkType !== 'unknown') {
      return networkTypeLabels[hop.networkType] ?? '-'
    }
    return hop.location?.replace(/\s*·\s*/g, '').trim() || '-'
  }

  /**
   * 格式化跳点的 Origin ASN 列表。
   * @param hop 当前跳点信息。
   * @returns AS 码列表或缺失原因。
   */
  function formatASNs(hop: Api.Detection.MTRHop): string {
    if (hop.networkType !== 'public' && hop.networkType !== 'unknown') return '-'
    return hop.asns?.length ? hop.asns.map((asn) => `AS${asn}`).join(' / ') : '-'
  }

  const devices = ref<Api.Detection.MTRDevice[]>([])
  const form = reactive<Partial<Api.Detection.MTRCreateParams>>({})
  const submitting = ref(false)
  const result = ref<Api.Detection.MTRTaskResult>()
  const activeNodeNames = ref<{ source: string; target: string }>()
  let pollTimer: ReturnType<typeof setTimeout> | undefined
  let activeTaskId: number | undefined
  const terminalStatuses: Api.Detection.MTRStatus[] = ['completed', 'partial_completed', 'failed']
  const sourceDevice = computed(() => devices.value.find((device) => device.id === form.sourceDeviceId))
  const targetDevice = computed(() => devices.value.find((device) => device.id === form.targetDeviceId))
  const sourceIPs = computed(() => sortMTRIPs(sourceDevice.value?.ips ?? []))
  const targetIPs = computed(() => {
    const sourceIP = sourceIPs.value.find((ip) => ip.id === form.sourceIpId)
    return sortMTRIPs((targetDevice.value?.ips ?? []).filter((ip) => !sourceIP || ip.ipVersion === sourceIP.ipVersion))
  })
  const canSubmit = computed(() => Boolean(form.sourceDeviceId && form.sourceIpId && form.targetDeviceId && form.targetIpId))

  /**
   * 将在线节点格式化为下拉选项文字。
   * @param device 当前在线节点。
   * @returns 节点名称与唯一编号。
   */
  function formatNode(device: Api.Detection.MTRDevice): string { return `${device.nodeName}节点 #${device.id}` }
  /**
   * 将公网 IP 按 IPv4、IPv6 的顺序排列。
   * @param ips 待排序的公网 IP 列表。
   * @returns 不修改原列表的已排序公网 IP 列表。
   */
  function sortMTRIPs(ips: readonly Api.Detection.MTRDeviceIP[]): Api.Detection.MTRDeviceIP[] {
    return [...ips].sort((left, right) => left.ipVersion - right.ipVersion)
  }
  /**
   * 将 IP 地址及地址族格式化为下拉选项文字。
   * @param ip 当前公网 IP。
   * @returns 地址族和 IP 组成的文字。
   */
  function formatIP(ip: Api.Detection.MTRDeviceIP): string { return `IPv${ip.ipVersion} · ${ip.ip}` }
  /**
   * 按任务方向格式化节点位置名称。
   * @param direction 当前单向 MTR 的执行方向。
   * @returns 创建任务时快照的源节点到目标节点名称。
   */
  function formatDirectionNodes(direction: Api.Detection.MTRDirectionResult['direction']): string {
    const names = activeNodeNames.value
    if (!names) return ''
    return direction === 'A_TO_B' ? `${names.source} → ${names.target}` : `${names.target} → ${names.source}`
  }
  /**
   * 返回任务状态的展示文字与语义颜色。
   * @param status 主任务或方向任务状态。
   * @returns Element Plus 标签配置。
   */
  function getStatusMeta(status: Api.Detection.MTRStatus): { label: string; type: TagProps['type'] } { return ({ queued: { label: '等待设备领取', type: 'info' }, running: { label: '执行中', type: 'warning' }, completed: { label: '全部完成', type: 'success' }, partial_completed: { label: '部分完成', type: 'warning' }, failed: { label: '执行失败', type: 'danger' } } as const)[status] }
  /**
   * 格式化整数千分比丢包率。
   * @param lossRate 中央服务返回的千分比丢包率。
   * @returns 带百分号的一位小数。
   */
  function formatLoss(lossRate: number): string { return `${(lossRate / 10).toFixed(1)}%` }
  /**
   * 切换节点 A 时清空不再属于该节点的地址选择。
   * @returns 无返回值。
   */
  function handleSourceChange(): void { form.sourceIpId = undefined; form.targetIpId = undefined }
  /**
   * 切换节点 B 时清空不再属于该节点的地址选择。
   * @returns 无返回值。
   */
  function handleTargetChange(): void { form.targetIpId = undefined }
  /**
   * 清理尚未触发的结果轮询定时器。
   * @returns 无返回值。
   */
  function clearPollTimer(): void { if (pollTimer) clearTimeout(pollTimer); pollTimer = undefined }
  /**
   * 获取任务结果，并在非终态时继续短轮询。
   * @param taskId 当前双向 MTR 主任务主键。
   * @returns 本次查询结束后的 Promise。
   */
  async function pollResult(taskId: number): Promise<void> { try { const data = await fetchGetMTRTask(taskId); if (activeTaskId !== taskId) return; result.value = data; if (terminalStatuses.includes(data.status)) { submitting.value = false; return }; pollTimer = setTimeout(() => void pollResult(taskId), 600) } catch { if (activeTaskId === taskId) submitting.value = false } }
  /**
   * 创建任务并持续刷新两个方向的逐跳结果。
   * @returns 创建及首次查询结束后的 Promise。
   */
  async function handleSubmit(): Promise<void> {
    const sourceNodeName = sourceDevice.value?.nodeName
    const targetNodeName = targetDevice.value?.nodeName
    if (!canSubmit.value || submitting.value || !sourceNodeName || !targetNodeName) return
    clearPollTimer()
    submitting.value = true
    result.value = undefined
    try {
      const created = await fetchCreateMTRTask(form as Api.Detection.MTRCreateParams)
      activeNodeNames.value = { source: sourceNodeName, target: targetNodeName }
      activeTaskId = created.mtrTaskId
      await pollResult(created.mtrTaskId)
    } catch {
      submitting.value = false
    }
  }
  /**
   * 加载可选在线设备，失败时维持空列表。
   * @returns 请求结束后的 Promise。
   */
  async function loadDevices(): Promise<void> { devices.value = await fetchGetMTRDevices() }
  onMounted(() => void loadDevices())
  onBeforeUnmount(() => { activeTaskId = undefined; clearPollTimer() })
</script>
