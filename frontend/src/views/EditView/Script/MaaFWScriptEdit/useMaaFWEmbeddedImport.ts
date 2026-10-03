import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  EMPTY_EMBEDDED_STATUS,
  useMaaFWEmbeddedApi,
  type MaaFWEmbeddedStatus,
} from '@/composables/useMaaFWEmbeddedApi'
import type { MaaFWScriptConfig } from '@/types/script'
import type { MaaFWProgressChannel } from './useMaaFWProgressChannel'
import type { MaaFWScriptFormData } from './useMaaFWScriptDraft'

interface MaaFWEmbeddedImportOptions {
  scriptId: string
  maafwConfig: MaaFWScriptConfig
  formData: MaaFWScriptFormData
  channel: MaaFWProgressChannel
  /** 导入成功后重新拉脚本类型：后端按项目内容原地换类型 */
  refreshScriptType: () => Promise<void>
  /** 有效根换了之后重新读 interface 并重新准备运行环境 */
  runPreviewOnNewRoot: () => Promise<void>
  /** 页面已卸载（导入换了类型、页面宿主换成了特调自己的页面） */
  isPageUnmounted: () => boolean
}

/**
 * 内嵌副本：状态只从后端拿（副本在不在、来源在不在都是磁盘上的事实，本地草稿说了不算），
 * 选目录即导入，导入进度走与运行环境准备共用的那条订阅。
 */
export function useMaaFWEmbeddedImport({
  scriptId,
  maafwConfig,
  formData,
  channel,
  refreshScriptType,
  runPreviewOnNewRoot,
  isPageUnmounted,
}: MaaFWEmbeddedImportOptions) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('MaaFW 脚本编辑')
  const { getEmbeddedStatus, reimportEmbedded } = useMaaFWEmbeddedApi()
  const { ensureEnvSubscription } = channel

  // ---- 内嵌副本 ----
  // 状态只从后端拿：副本在不在、来源在不在都是磁盘上的事实，本地草稿说了不算。
  const embeddedStatus = ref<MaaFWEmbeddedStatus>({ ...EMPTY_EMBEDDED_STATUS })
  const embeddedBusy = ref(false)
  // 导入进度：后端按投影的文件数推百分比与阶段文案，导入几百 MB 时进度条顶在目录字段下面
  const importPercent = ref<number | null>(null)
  const importMessage = ref('')

  channel.onImportProgress(data => {
    if (typeof data.percent === 'number') importPercent.value = data.percent
    if (data.message) importMessage.value = data.message
  })

  const refreshEmbeddedStatus = async () => {
    try {
      const { status } = await getEmbeddedStatus(scriptId)
      embeddedStatus.value = status
    } catch (error) {
      logger.error(`读取内嵌状态失败: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  /** 跑一个内嵌动作：成功回填状态并提示后端文案，失败提示原因；返回是否成功。 */
  const runEmbeddedAction = async (
    action: () => Promise<{ status: MaaFWEmbeddedStatus; message: string }>
  ): Promise<boolean> => {
    if (embeddedBusy.value) return false
    embeddedBusy.value = true
    try {
      const { status, message: text } = await action()
      embeddedStatus.value = status
      if (text) message.success(text)
      // 导入完成后后端按项目内容决定脚本类型（M9A 项目 → M9A，其它 → MaaFW），
      // 重新拉一次类型让 flavor 文案跟上
      await refreshScriptType()
      return true
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
      return false
    } finally {
      embeddedBusy.value = false
    }
  }

  const selectMaaFWPath = async () => {
    try {
      if (!window.electronAPI) {
        message.error(t('edit.filePickingUnavailableRun'))
        return
      }
      const path = await window.electronAPI.selectFolder()
      if (!path) return
      // 选目录 = 导入：第一次建副本，之后是换来源并重新导入。Info.Path 由后端在
      // 导入成功后写入，失败时旧副本与旧来源都原样不动，这里也就不动本地草稿。
      // 进度由后端按文件数推过来，订阅要在请求发出前挂上，否则头几条会漏。
      ensureEnvSubscription()
      importPercent.value = 0
      importMessage.value = ''
      const ok = await runEmbeddedAction(() => reimportEmbedded(scriptId, path))
      if (!ok) return
      // 导入后类型变成了有自己页面的特调：页面宿主已经换上那个页面，它加载时自己读 interface、
      // 备运行环境；这个旧实例再往下走只会重复请求、拿旧草稿回写配置
      if (isPageUnmounted()) return
      maafwConfig.Info.Path = path
      formData.path = path
      await runPreviewOnNewRoot()
    } catch (error) {
      logger.error(`选择项目目录失败: ${error instanceof Error ? error.message : String(error)}`)
      message.error(t('edit.couldNotPickFolder'))
    }
  }

  return {
    embeddedStatus,
    embeddedBusy,
    importPercent,
    importMessage,
    refreshEmbeddedStatus,
    selectMaaFWPath,
  }
}
