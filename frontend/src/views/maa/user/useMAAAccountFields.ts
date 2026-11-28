import { watch } from 'vue'

export function useMAAAccountFields(formData: {
  Info: { Name: string; Id: string }
  userName: string
  userId: string
}) {
  // 同步扁平化验证字段与嵌套数据，避免同一轮更新中的旧值覆盖新草稿。
  watch(
    () => formData.Info.Name,
    newVal => {
      if (formData.userName !== newVal) {
        formData.userName = newVal || ''
      }
    },
    { immediate: true, flush: 'sync' }
  )

  watch(
    () => formData.Info.Id,
    newVal => {
      if (formData.userId !== newVal) {
        formData.userId = newVal || ''
      }
    },
    { immediate: true, flush: 'sync' }
  )

  watch(
    () => formData.userName,
    newVal => {
      if (formData.Info.Name !== newVal) {
        formData.Info.Name = newVal || ''
      }
    },
    { flush: 'sync' }
  )

  watch(
    () => formData.userId,
    newVal => {
      if (formData.Info.Id !== newVal) {
        formData.Info.Id = newVal || ''
      }
    },
    { flush: 'sync' }
  )
}
