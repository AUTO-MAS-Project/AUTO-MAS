import { computed, reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Rule } from 'ant-design-vue/es/form'
import type { MaaFWUserConfig } from '@/types/script'
import { getDefaultMaaFWUserData } from './maafwUserDefaults'

/** MFW 用户页表单草稿：默认值、校验规则、回填后端数据，以及用户名与 Info.Name 的双向同步。 */
export function useMaaFWUserForm() {
  const { t } = useI18n()

  const formData = reactive({
    userName: '',
    ...getDefaultMaaFWUserData(),
  })

  const rules = computed<Record<string, Rule[]>>(() => ({
    userName: [
      { required: true, message: t('edit.enterUsername'), trigger: 'blur' },
      { min: 1, max: 50, message: t('edit.usernameMustBe1'), trigger: 'blur' },
    ],
  }))

  watch(
    () => formData.Info.Name,
    newVal => {
      if (formData.userName !== newVal) {
        formData.userName = newVal || ''
      }
    },
    { immediate: true }
  )

  watch(
    () => formData.userName,
    newVal => {
      if (formData.Info.Name !== newVal) {
        formData.Info.Name = newVal || ''
      }
    }
  )

  const applyUserData = (userData: Partial<MaaFWUserConfig>) => {
    const defaults = getDefaultMaaFWUserData()
    Object.assign(formData.Info, { ...defaults.Info, ...userData.Info })
    Object.assign(formData.Task, { ...defaults.Task, ...userData.Task })
    Object.assign(formData.Notify, { ...defaults.Notify, ...userData.Notify })
    Object.assign(formData.Data, { ...defaults.Data, ...userData.Data })
  }

  return { formData, rules, applyUserData }
}

export type MaaFWUserFormState = ReturnType<typeof useMaaFWUserForm>['formData']
