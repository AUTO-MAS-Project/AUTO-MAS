import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserApi } from '@/composables/useUserApi'
import type { MaaFWInterfacePreviewData, MaaFWTaskSnapshot, MaaFWUserConfig } from '@/types/script'
import { normalizeTaskSnapshot } from './maafwTaskSnapshot'
import type { MaaFWUserFormState } from './useMaaFWUserForm'
import type { MaaFWUserSaveStatus } from './useMaaFWUserSaveStatus'

/**
 * 当前用户 id 的持有者。新建模式下页面在创建用户后改写 `value`，紧接着 `router.replace`
 * 到编辑地址、页面重建。故意不用 ref：改写它不该触发任何重渲染。
 */
export interface MaaFWUserIdHolder {
  value: string
}

interface MaaFWUserPersistenceOptions {
  scriptId: string
  userIdHolder: MaaFWUserIdHolder
  formData: MaaFWUserFormState
  taskSnapshot: Ref<MaaFWTaskSnapshot>
  previewData: Ref<MaaFWInterfacePreviewData | null>
  isInitializing: Ref<boolean>
  isManagedTaskId: (taskId: string) => boolean
  enqueueSave: MaaFWUserSaveStatus['enqueueSave']
  pendingCount: MaaFWUserSaveStatus['pendingCount']
}

/**
 * 用户页落盘：单字段保存与任务队列（预设 + 快照）保存。
 * 两条路径都在初始化期间或还没有用户 id 时直接返回。
 */
export function useMaaFWUserPersistence({
  scriptId,
  userIdHolder,
  formData,
  taskSnapshot,
  previewData,
  isInitializing,
  isManagedTaskId,
  enqueueSave,
  pendingCount,
}: MaaFWUserPersistenceOptions) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('MaaFW用户编辑')
  const { getUsers, updateUser } = useUserApi()

  const handleFieldSave = async (key: string, value: unknown) => {
    if (isInitializing.value || !userIdHolder.value) return

    return await enqueueSave(async () => {
      const parts = key.split('.')
      let userData: Record<string, unknown> = {}
      let current = userData

      for (let i = 0; i < parts.length - 1; i++) {
        current[parts[i]] = {}
        current = current[parts[i]] as Record<string, unknown>
      }
      current[parts[parts.length - 1]] = value

      if (key === 'userName') {
        userData = { Info: { Name: value } }
      }

      const success = await updateUser(scriptId, userIdHolder.value, userData)
      if (!success) throw new Error(t('edit.couldNotSaveUser2', { p0: key }))
      logger.info(`用户配置已保存: ${key}`)
    })
      .then(() => true)
      .catch(error => {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`保存失败: ${errorMsg}`)
        return false
      })
  }

  /** 返回这次是否真的写进了后端（失败的提示由 updateUser 与页头保存状态给出） */
  const savePresetAndSnapshot = async (): Promise<boolean> => {
    if (isInitializing.value || !userIdHolder.value) return false

    const taskSnapshotValue = JSON.stringify(taskSnapshot.value)
    const selectedPreset = formData.Task.SelectedPreset || ''
    // 队列里还有受管任务时，后端保存会按特调规则改写（M9A：只剩一个切换账号就收进「账号」），
    // 存完把后端的结果拉回来，别让页面上还显示着已经不在的任务
    const hasManagedTasks = taskSnapshot.value.taskOrder.some(isManagedTaskId)
    formData.Task.TaskSnapshot = taskSnapshotValue
    return await enqueueSave(async () => {
      const success = await updateUser(scriptId, userIdHolder.value, {
        Task: {
          SelectedPreset: selectedPreset,
          TaskSnapshot: taskSnapshotValue,
        },
      })
      if (!success) throw new Error('任务预设保存失败')
      // 后面还排着保存时不拉：拉回来的是这次的结果，会盖掉页面上还没存的改动
      if (hasManagedTasks && pendingCount() === 1) await reloadManagedUserFields()
    })
      .then(() => true)
      .catch(error => {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`保存任务预设失败: ${errorMsg}`)
        return false
      })
  }

  /** 保存后按后端结果刷新受管任务会动到的字段：账号、备注与任务队列 */
  const reloadManagedUserFields = async () => {
    const userResponse = await getUsers(scriptId, userIdHolder.value)
    const userData = userResponse?.data?.[userIdHolder.value] as
      | Partial<MaaFWUserConfig>
      | undefined
    if (!userData) return
    if (userData.Info) {
      formData.Info.Account = userData.Info.Account ?? formData.Info.Account
      formData.Info.Notes = userData.Info.Notes ?? formData.Info.Notes
    }
    const savedSnapshot = userData.Task?.TaskSnapshot
    if (typeof savedSnapshot === 'string' && savedSnapshot !== formData.Task.TaskSnapshot) {
      formData.Task.TaskSnapshot = savedSnapshot
      taskSnapshot.value = normalizeTaskSnapshot(savedSnapshot, previewData.value, {
        keepMissing: true,
      })
    }
  }

  return { handleFieldSave, savePresetAndSnapshot }
}
