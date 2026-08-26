<template>
  <ArtSearchBar v-model="formData" :items="formItems" @reset="handleReset" @search="handleSearch" />
</template>

<script setup lang="ts">
  import { USER_LEVEL_OPTIONS } from '@/utils/constants'
  import { ALERT_TYPE_OPTIONS } from '../alert-type'

  interface Props {
    modelValue: Api.SystemManage.UserSearchParams
  }

  interface Emits {
    (event: 'update:modelValue', value: Api.SystemManage.UserSearchParams): void
    (event: 'search', params: Api.SystemManage.UserSearchParams): void
    (event: 'reset'): void
  }

  const props = defineProps<Props>()
  const emit = defineEmits<Emits>()

  const formData = computed({
    get: () => props.modelValue,
    set: (value) => emit('update:modelValue', value)
  })

  const formItems = [
    {
      label: 'openid',
      key: 'openid',
      type: 'input',
      props: { placeholder: '请输入 openid', clearable: true, maxlength: 128 }
    },
    {
      label: '订阅状态',
      key: 'subscribeStatus',
      type: 'select',
      props: {
        placeholder: '请选择订阅状态',
        clearable: true,
        options: [
          { label: '未订阅', value: 0 },
          { label: '已订阅', value: 1 }
        ]
      }
    },
    {
      label: '用户等级',
      key: 'userLevel',
      type: 'select',
      props: {
        placeholder: '请选择用户等级',
        clearable: true,
        options: USER_LEVEL_OPTIONS
      }
    },
    {
      label: '接收告警类型',
      key: 'alertType',
      type: 'select',
      props: {
        placeholder: '请选择接收告警类型',
        clearable: true,
        options: ALERT_TYPE_OPTIONS
      }
    }
  ]

  /**
   * 向父组件转发重置事件。
   * @returns 无返回值。
   */
  const handleReset = (): void => {
    emit('reset')
  }

  /**
   * 向父组件转发清洗后的搜索参数。
   * @param params 用户筛选参数。
   * @returns 无返回值。
   */
  const handleSearch = (params: Record<string, unknown>): void => {
    emit('search', params as Api.SystemManage.UserSearchParams)
  }
</script>
