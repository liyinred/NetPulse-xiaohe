<template>
  <div class="ip-management-page art-full-height">
    <IPSearch v-model="searchForm" @search="handleSearch" @reset="resetSearchParams" />

    <ElCard class="art-table-card">
      <ArtTableHeader v-model:columns="columnChecks" :loading="loading" @refresh="refreshData">
        <template #right>
          <ElButton type="primary" @click="openCreateDialog" v-ripple> 新增 IP </ElButton>
        </template>
      </ArtTableHeader>
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

    <IPDialog
      v-model="dialogVisible"
      :mode="dialogMode"
      :ip-data="currentIPData"
      @success="handleDialogSuccess"
    />
  </div>
</template>

<script setup lang="ts">
  import { Edit } from '@element-plus/icons-vue'
  import { ElButton, ElTag } from 'element-plus'
  import { fetchGetIPList } from '@/api/system-manage'
  import { useTable } from '@/hooks/core/useTable'
  import { formatBeijingTime } from '@/utils/date'
  import IPDialog from './modules/ip-dialog.vue'
  import IPSearch from './modules/ip-search.vue'

  defineOptions({ name: 'IpManagement' })

  type IPListItem = Api.SystemManage.IPListItem

  interface TableSortChange {
    prop: keyof IPListItem
    order: 'ascending' | 'descending' | null
  }

  const defaultSort = { prop: 'updateTime', order: 'descending' as const }
  const paginationOptions = { pageSizes: [25, 50, 100] }
  const dialogVisible = ref(false)
  const dialogMode = ref<'create' | 'edit'>('create')
  const currentIPData = ref<IPListItem>()
  const searchForm = ref<Api.SystemManage.IPSearchParams>({
    ipVersion: 4,
    sortField: 'updateTime',
    sortOrder: 'desc'
  })

  /**
   * 获取公开状态的展示配置。
   * @param publicStatus 公开状态编码。
   * @returns 状态文案和 ElTag 类型。
   */
  const getPublicStatusConfig = (publicStatus: number) => {
    return publicStatus === 1
      ? { text: '公开', type: 'success' as const }
      : { text: '未公开', type: 'info' as const }
  }

  const {
    columns,
    columnChecks,
    data,
    loading,
    pagination,
    getData,
    replaceSearchParams,
    resetSearchParams,
    handleSizeChange,
    handleCurrentChange,
    refreshData
  } = useTable({
    core: {
      apiFn: fetchGetIPList,
      apiParams: {
        current: 1,
        size: 25,
        ...searchForm.value
      },
      columnsFactory: () => [
        { type: 'globalIndex', width: 80, label: '序号' },
        { prop: 'ip', label: 'IP 地址', minWidth: 180, sortable: 'custom' },
        {
          prop: 'publicStatus',
          label: '公开状态',
          minWidth: 110,
          sortable: 'custom',
          formatter: (row) => {
            const config = getPublicStatusConfig(row.publicStatus)
            return h(ElTag, { type: config.type }, () => config.text)
          }
        },
        {
          prop: 'isp',
          label: '运营商',
          minWidth: 120,
          sortable: 'custom',
          formatter: (row) => row.ispName
        },
        {
          prop: 'province',
          label: '省份',
          minWidth: 110,
          sortable: 'custom',
          formatter: (row) => row.provinceName
        },
        {
          prop: 'city',
          label: '城市',
          minWidth: 120,
          sortable: 'custom',
          formatter: (row) => row.city || '-'
        },
        {
          prop: 'updateTime',
          label: '更新时间',
          minWidth: 180,
          sortable: 'custom',
          formatter: (row) => formatBeijingTime(row.updateTime)
        },
        {
          prop: 'operation',
          label: '操作',
          width: 90,
          fixed: 'right',
          formatter: (row) =>
            h(ElButton, {
              icon: Edit,
              type: 'primary',
              size: 'small',
              circle: true,
              onClick: () => openEditDialog(row)
            })
        }
      ]
    }
  })

  /**
   * 使用筛选表单重新查询第一页。
   * @param params 清洗后的 IP 筛选参数。
   * @returns 无返回值。
   */
  const handleSearch = (params: Api.SystemManage.IPSearchParams): void => {
    replaceSearchParams(params)
    void getData()
  }

  /**
   * 打开新增 IP 弹窗。
   * @returns 无返回值。
   */
  const openCreateDialog = (): void => {
    dialogMode.value = 'create'
    currentIPData.value = undefined
    dialogVisible.value = true
  }

  /**
   * 使用当前行数据打开编辑 IP 弹窗。
   * @param row 当前 IP 表格记录。
   * @returns 无返回值。
   */
  const openEditDialog = (row: IPListItem): void => {
    dialogMode.value = 'edit'
    currentIPData.value = row
    dialogVisible.value = true
  }

  /**
   * IP 弹窗提交成功后回到第一页并刷新列表。
   * @returns 无返回值。
   */
  const handleDialogSuccess = (): void => {
    replaceSearchParams(searchForm.value)
    void getData()
  }

  /**
   * 将 Element Plus 排序事件转换为统一排序协议并查询第一页。
   * @param sortChange 表格排序字段和方向。
   * @returns 无返回值。
   */
  const handleSortChange = (sortChange: TableSortChange): void => {
    searchForm.value.sortField = sortChange.order ? sortChange.prop : 'updateTime'
    searchForm.value.sortOrder = sortChange.order === 'ascending' ? 'asc' : 'desc'
    replaceSearchParams(searchForm.value)
    void getData()
  }
</script>
