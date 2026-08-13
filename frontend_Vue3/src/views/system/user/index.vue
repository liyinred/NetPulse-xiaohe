<template>
  <div class="user-page art-full-height">
    <UserSearch v-model="searchForm" @search="handleSearch" @reset="resetSearchParams" />

    <ElCard class="art-table-card">
      <ArtTableHeader v-model:columns="columnChecks" :loading="loading" @refresh="refreshData" />
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

    <UserDialog
      v-model:visible="dialogVisible"
      :user-data="currentUserData"
      @success="handleDialogSuccess"
    />
  </div>
</template>

<script setup lang="ts">
  import { Edit } from '@element-plus/icons-vue'
  import { ElButton, ElTag } from 'element-plus'
  import { fetchGetUserList } from '@/api/system-manage'
  import { useTable } from '@/hooks/core/useTable'
  import { formatBeijingTime } from '@/utils/date'
  import { getUserLevelConfig } from '@/utils/constants'
  import { ALERT_TYPE_CONFIG } from './alert-type'
  import UserDialog from './modules/user-dialog.vue'
  import UserSearch from './modules/user-search.vue'

  defineOptions({ name: 'UserManagement' })

  type UserListItem = Api.SystemManage.UserListItem

  interface TableSortChange {
    prop: keyof UserListItem
    order: 'ascending' | 'descending' | null
  }

  const defaultSort = { prop: 'createdTime', order: 'descending' as const }
  const paginationOptions = { pageSizes: [25, 50, 100] }
  const dialogVisible = ref(false)
  const currentUserData = ref<UserListItem>()
  const searchForm = ref<Api.SystemManage.UserSearchParams>({
    sortField: 'createdTime',
    sortOrder: 'desc'
  })

  const SUBSCRIBE_STATUS_CONFIG = {
    0: { text: '未订阅', type: 'info' as const },
    1: { text: '已订阅', type: 'success' as const }
  }

  /**
   * 获取订阅状态的展示配置。
   * @param subscribeStatus 订阅状态编码。
   * @returns 状态文案和 ElTag 类型。
   */
  const getSubscribeStatusConfig = (subscribeStatus: number | null) => {
    if (subscribeStatus === null) return { text: '未知', type: 'info' as const }
    return (
      SUBSCRIBE_STATUS_CONFIG[subscribeStatus as keyof typeof SUBSCRIBE_STATUS_CONFIG] ?? {
        text: '未知',
        type: 'info' as const
      }
    )
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
    refreshData,
    refreshUpdate
  } = useTable({
    core: {
      apiFn: fetchGetUserList,
      apiParams: {
        current: 1,
        size: 25,
        ...searchForm.value
      },
      columnsFactory: () => [
        { type: 'globalIndex', width: 80, label: '序号' },
        { prop: 'openid', label: 'openid', minWidth: 280, sortable: 'custom' },
        {
          prop: 'userLevel',
          label: '用户等级',
          minWidth: 120,
          sortable: 'custom',
          formatter: (row) => {
            const config = getUserLevelConfig(row.userLevel)
            return h(ElTag, { type: config.type }, () => config.text)
          }
        },
        {
          prop: 'subscribeStatus',
          label: '订阅状态',
          minWidth: 120,
          sortable: 'custom',
          formatter: (row) => {
            const config = getSubscribeStatusConfig(row.subscribeStatus)
            return h(ElTag, { type: config.type }, () => config.text)
          }
        },
        {
          prop: 'alertType',
          label: '告警类型',
          minWidth: 130,
          sortable: 'custom',
          formatter: (row) => {
            const config = ALERT_TYPE_CONFIG[row.alertType]
            return h(ElTag, { type: config.type }, () => config.text)
          }
        },
        {
          prop: 'createdTime',
          label: '创建时间',
          minWidth: 180,
          sortable: 'custom',
          formatter: (row) => formatBeijingTime(row.createdTime)
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
              title: '编辑告警类型',
              'aria-label': '编辑告警类型',
              onClick: () => openEditDialog(row)
            })
        }
      ]
    }
  })

  /**
   * 使用筛选表单重新查询第一页。
   * @param params 清洗后的用户筛选参数。
   * @returns 无返回值。
   */
  const handleSearch = (params: Api.SystemManage.UserSearchParams): void => {
    replaceSearchParams(params)
    void getData()
  }

  /**
   * 使用当前行数据打开用户告警类型编辑弹窗。
   * @param row 当前用户表格记录。
   * @returns 无返回值。
   */
  const openEditDialog = (row: UserListItem): void => {
    currentUserData.value = row
    dialogVisible.value = true
  }

  /**
   * 用户告警类型更新成功后刷新当前筛选结果。
   * @returns 无返回值。
   */
  const handleDialogSuccess = (): void => {
    void refreshUpdate()
  }

  /**
   * 将 Element Plus 排序事件转换为统一排序协议并查询第一页。
   * @param sortChange 表格排序字段和方向。
   * @returns 无返回值。
   */
  const handleSortChange = (sortChange: TableSortChange): void => {
    searchForm.value.sortField = sortChange.order ? sortChange.prop : 'createdTime'
    searchForm.value.sortOrder = sortChange.order === 'ascending' ? 'asc' : 'desc'
    replaceSearchParams(searchForm.value)
    void getData()
  }
</script>
