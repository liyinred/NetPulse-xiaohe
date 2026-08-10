<template>
  <ArtSearchBar
    v-model="formData"
    :items="formItems"
    default-expanded
    @reset="handleReset"
    @search="handleSearch"
  />
</template>

<script setup lang="ts">
  interface Props {
    modelValue: Api.SystemManage.IPSearchParams
  }

  interface Emits {
    (event: 'update:modelValue', value: Api.SystemManage.IPSearchParams): void
    (event: 'search', params: Api.SystemManage.IPSearchParams): void
    (event: 'reset'): void
  }

  const props = defineProps<Props>()
  const emit = defineEmits<Emits>()

  const formData = computed({
    get: () => props.modelValue,
    set: (value) => emit('update:modelValue', value)
  })

  const provinceOptions = [
    { label: '未知', value: 1 },
    { label: '北京', value: 2 },
    { label: '福建', value: 3 },
    { label: '甘肃', value: 4 },
    { label: '广东', value: 5 },
    { label: '广西', value: 6 },
    { label: '贵州', value: 7 },
    { label: '海南', value: 8 },
    { label: '河北', value: 9 },
    { label: '河南', value: 10 },
    { label: '黑龙江', value: 11 },
    { label: '湖北', value: 12 },
    { label: '湖南', value: 13 },
    { label: '吉林', value: 14 },
    { label: '江苏', value: 15 },
    { label: '江西', value: 16 },
    { label: '辽宁', value: 17 },
    { label: '内蒙古', value: 18 },
    { label: '宁夏', value: 19 },
    { label: '青海', value: 20 },
    { label: '山东', value: 21 },
    { label: '山西', value: 22 },
    { label: '陕西', value: 23 },
    { label: '上海', value: 24 },
    { label: '四川', value: 25 },
    { label: '天津', value: 26 },
    { label: '西藏', value: 27 },
    { label: '新疆', value: 28 },
    { label: '云南', value: 29 },
    { label: '浙江', value: 30 },
    { label: '重庆', value: 31 },
    { label: '安徽', value: 32 },
    { label: '香港', value: 33 },
    { label: '台湾', value: 34 },
    { label: '澳门', value: 35 }
  ]

  const formItems = [
    {
      label: 'IP 地址',
      key: 'ip',
      type: 'input',
      props: { placeholder: '请输入 IP 地址', clearable: true, maxlength: 45 }
    },
    {
      label: 'IP 版本',
      key: 'ipVersion',
      type: 'select',
      props: {
        placeholder: '请选择 IP 版本',
        clearable: true,
        options: [
          { label: 'IPv4', value: 4 },
          { label: 'IPv6', value: 6 }
        ]
      }
    },
    {
      label: '运营商',
      key: 'isp',
      type: 'select',
      props: {
        placeholder: '请选择运营商',
        clearable: true,
        options: [
          { label: '电信', value: 1 },
          { label: '移动', value: 2 },
          { label: '联通', value: 3 },
          { label: '其他运营商', value: 4 }
        ]
      }
    },
    {
      label: '省份',
      key: 'province',
      type: 'select',
      props: {
        placeholder: '请选择省份',
        clearable: true,
        filterable: true,
        options: provinceOptions
      }
    },
    {
      label: '城市',
      key: 'city',
      type: 'input',
      props: { placeholder: '请输入城市', clearable: true, maxlength: 64 }
    },
    {
      label: '公开状态',
      key: 'publicStatus',
      type: 'select',
      props: {
        placeholder: '请选择公开状态',
        clearable: true,
        options: [
          { label: '未公开', value: 0 },
          { label: '公开', value: 1 }
        ]
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
   * @param params IP 筛选参数。
   * @returns 无返回值。
   */
  const handleSearch = (params: Record<string, unknown>): void => {
    emit('search', params as Api.SystemManage.IPSearchParams)
  }
</script>
