<template>
  <ElDialog
    v-model="dialogVisible"
    title="编辑用户"
    width="25%"
    align-center
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
    @closed="resetForm"
  >
    <ElForm ref="formRef" :model="formData" :rules="rules" label-width="auto">
      <ElFormItem label="openid">
        <ElInput :model-value="userData?.openid || '-'" disabled />
      </ElFormItem>
      <ElFormItem label="用户等级" prop="userLevel">
        <ElSelect v-model="formData.userLevel" placeholder="请选择用户等级">
          <ElOption
            v-for="option in USER_LEVEL_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="告警类型" prop="alertType">
        <ElSelect v-model="formData.alertType" placeholder="请选择告警类型">
          <ElOption
            v-for="option in ALERT_TYPE_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
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
  import type { FormInstance, FormRules } from 'element-plus'
  import { fetchUpdateUser } from '@/api/system-manage'
  import { USER_LEVEL_OPTIONS } from '@/utils/constants'
  import { ALERT_TYPE_OPTIONS } from '../alert-type'

  interface Props {
    visible: boolean
    userData?: Api.SystemManage.UserListItem
  }

  interface Emits {
    (event: 'update:visible', value: boolean): void
    (event: 'success'): void
  }

  const props = withDefaults(defineProps<Props>(), {
    visible: false,
    userData: undefined
  })
  const emit = defineEmits<Emits>()
  const formRef = ref<FormInstance>()
  const submitting = ref(false)
  const formData = reactive<Api.SystemManage.UserUpdateParams>({
    userLevel: 1,
    alertType: 0
  })
  const rules: FormRules = {
    userLevel: [{ required: true, message: '请选择用户等级', trigger: 'change' }],
    alertType: [{ required: true, message: '请选择告警类型', trigger: 'change' }]
  }

  const dialogVisible = computed({
    get: () => props.visible,
    set: (value) => emit('update:visible', value)
  })

  /**
   * 使用当前用户数据初始化用户编辑表单。
   * @returns 无返回值。
   */
  const initializeForm = (): void => {
    formData.userLevel = props.userData?.userLevel ?? 1
    formData.alertType = props.userData?.alertType ?? 0
  }

  watch(
    () => props.visible,
    (opened) => {
      if (!opened) return
      initializeForm()
      nextTick(() => formRef.value?.clearValidate())
    }
  )

  /**
   * 关闭用户编辑弹窗。
   * @returns 无返回值。
   */
  const handleClose = (): void => {
    if (submitting.value) return
    dialogVisible.value = false
  }

  /**
   * 重置用户编辑表单和校验状态。
   * @returns 无返回值。
   */
  const resetForm = (): void => {
    initializeForm()
    formRef.value?.resetFields()
  }

  /**
   * 校验表单并更新当前用户的等级和服务号告警类型。
   * @returns 无返回值。
   */
  const handleSubmit = async (): Promise<void> => {
    if (!formRef.value || !props.userData || submitting.value) return

    try {
      await formRef.value.validate()
    } catch {
      return
    }

    submitting.value = true
    try {
      await fetchUpdateUser(props.userData.id, {
        userLevel: formData.userLevel,
        alertType: formData.alertType
      })
      ElMessage.success('用户信息更新成功')
      emit('success')
      dialogVisible.value = false
    } catch {
      return
    } finally {
      submitting.value = false
    }
  }
</script>
