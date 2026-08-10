<template>
  <ElDialog
    v-model="visible"
    :title="dialogTitle"
    width="25%"
    align-center
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
    @closed="resetForm"
  >
    <ElForm ref="formRef" :model="form" :rules="rules" label-position="right" label-width="auto">
      <ElFormItem label="IP 地址" prop="ip">
        <ElInput
          v-model="form.ip"
          placeholder="请输入标准 IPv4 或 IPv6 地址"
          maxlength="45"
          :disabled="isEdit"
          :clearable="!isEdit"
          :autofocus="!isEdit"
          @keyup.enter="handleSubmit"
        />
      </ElFormItem>

      <template v-if="isEdit">
        <ElFormItem label="IP 版本">
          <ElInput v-model="form.ipVersion" disabled />
        </ElFormItem>
        <ElFormItem label="运营商">
          <ElInput v-model="form.ispName" disabled />
        </ElFormItem>
        <ElFormItem label="省份">
          <ElInput v-model="form.provinceName" disabled />
        </ElFormItem>
        <ElFormItem label="城市">
          <ElInput v-model="form.city" disabled />
        </ElFormItem>
      </template>

      <ElFormItem label="公开状态" prop="publicStatus">
        <ElSelect v-model="form.publicStatus" placeholder="请选择公开状态">
          <ElOption label="未公开" :value="0" />
          <ElOption label="公开" :value="1" />
        </ElSelect>
      </ElFormItem>
    </ElForm>

    <template #footer>
      <ElButton :disabled="submitting" @click="handleClose">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="handleSubmit">提交</ElButton>
    </template>
  </ElDialog>
</template>

<script setup lang="ts">
  import type { FormInstance, FormItemRule, FormRules } from 'element-plus'
  import { fetchUpdateIPPublicStatus, fetchUpsertIP } from '@/api/system-manage'
  import { validateIPAddress } from '@/utils/form/validator'

  type DialogMode = 'create' | 'edit'
  type IPListItem = Api.SystemManage.IPListItem

  interface Props {
    modelValue: boolean
    mode: DialogMode
    ipData?: IPListItem
  }

  interface Emits {
    (event: 'update:modelValue', value: boolean): void
    (event: 'success'): void
  }

  interface IPFormData {
    ip: string
    publicStatus: 0 | 1
    ipVersion: string
    ispName: string
    provinceName: string
    city: string
  }

  const props = withDefaults(defineProps<Props>(), {
    modelValue: false,
    mode: 'create',
    ipData: undefined
  })
  const emit = defineEmits<Emits>()
  const formRef = ref<FormInstance>()
  const submitting = ref(false)
  const form = reactive<IPFormData>({
    ip: '',
    publicStatus: 1,
    ipVersion: '',
    ispName: '',
    provinceName: '',
    city: ''
  })

  const visible = computed({
    get: () => props.modelValue,
    set: (value) => emit('update:modelValue', value)
  })
  const isEdit = computed(() => props.mode === 'edit')
  const dialogTitle = computed(() => (isEdit.value ? '编辑 IP' : '新增 IP'))

  /**
   * 校验输入值是否为标准 IPv4 或 IPv6 地址。
   * @param _rule Element Plus 当前表单规则。
   * @param value 当前 IP 地址输入值。
   * @param callback Element Plus 校验结果回调。
   * @returns 无返回值。
   */
  const validateIPRule: FormItemRule['validator'] = (_rule, value, callback) => {
    if (!validateIPAddress(String(value))) {
      callback(new Error('请输入标准 IPv4 或 IPv6 地址'))
      return
    }
    callback()
  }

  const rules: FormRules = {
    ip: [
      { required: true, message: '请输入 IP 地址', trigger: 'blur' },
      { validator: validateIPRule, trigger: 'blur' }
    ],
    publicStatus: [{ required: true, message: '请选择公开状态', trigger: 'change' }]
  }

  /**
   * 根据弹窗模式初始化表单数据。
   * @returns 无返回值。
   */
  const initializeForm = (): void => {
    const data = props.ipData
    if (isEdit.value && data) {
      Object.assign(form, {
        ip: data.ip,
        publicStatus: data.publicStatus,
        ipVersion: `IPv${data.ipVersion}`,
        ispName: data.ispName,
        provinceName: data.provinceName,
        city: data.city || '-'
      })
      return
    }

    Object.assign(form, {
      ip: '',
      publicStatus: 1,
      ipVersion: '',
      ispName: '',
      provinceName: '',
      city: ''
    })
  }

  watch(
    () => props.modelValue,
    (opened) => {
      if (!opened) return
      initializeForm()
      nextTick(() => formRef.value?.clearValidate())
    }
  )

  /**
   * 关闭 IP 弹窗。
   * @returns 无返回值。
   */
  const handleClose = (): void => {
    if (submitting.value) return
    visible.value = false
  }

  /**
   * 重置 IP 表单和校验状态。
   * @returns 无返回值。
   */
  const resetForm = (): void => {
    initializeForm()
    formRef.value?.resetFields()
  }

  /**
   * 校验表单并新增 IP 或修改公开状态。
   * @returns 无返回值。
   */
  const handleSubmit = async (): Promise<void> => {
    if (!formRef.value || submitting.value) return

    try {
      await formRef.value.validate()
    } catch {
      return
    }

    submitting.value = true
    try {
      if (isEdit.value && props.ipData) {
        await fetchUpdateIPPublicStatus(props.ipData.id, {
          publicStatus: form.publicStatus
        })
      } else {
        await fetchUpsertIP({
          ip: form.ip.trim(),
          publicStatus: form.publicStatus
        })
      }
      ElMessage.success(isEdit.value ? 'IP 公开状态更新成功' : 'IP 新增成功')
      emit('success')
      visible.value = false
    } catch {
      return
    } finally {
      submitting.value = false
    }
  }
</script>
