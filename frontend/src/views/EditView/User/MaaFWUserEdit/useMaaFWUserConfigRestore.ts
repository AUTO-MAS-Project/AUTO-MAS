import { ref } from 'vue'
import type { MaaFWUserIdHolder } from './useMaaFWUserPersistence'
import { useConfigBackupApi } from '@/composables/useConfigBackupApi'

interface MaaFWPreviewRow {
  key: string
  value: string
}
interface MaaFWPreviewSection {
  name: string
  label: string
  rows?: MaaFWPreviewRow[]
}

interface MaaFWUserConfigRestoreOptions {
  scriptId: string
  userIdHolder: MaaFWUserIdHolder
  /** mas 恢复成功后重拉表单（含任务快照） */
  loadUserData: () => Promise<void>
  reloadInterface: (showMessage?: boolean) => Promise<void>
}

/** 配置恢复（通用 ConfigRestoreSection 的 props 供给）与编辑会话的进出归档。 */
export function useMaaFWUserConfigRestore({
  scriptId,
  userIdHolder,
  loadUserData,
  reloadInterface,
}: MaaFWUserConfigRestoreOptions) {
  const logger = window.electronAPI.getLogger('MaaFW用户编辑')

  // ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
  // 专项统一名（文案参数化用）：MaaFW 统一叫「maafw」
  const MAAFW_DISPLAY_NAME = 'maafw'
  const restoreOpen = ref(false)

  const restoreTargets: Array<{ key: string; kind: 'user' | 'script' }> = [
    { key: 'mas', kind: 'user' },
    { key: 'native', kind: 'script' },
  ]

  const { restoreApi, ensureBackup } = useConfigBackupApi({
    scriptId,
    userId: () => userIdHolder.value,
    logger,
  })

  const previewSections = (raw: unknown): MaaFWPreviewSection[] =>
    (raw as { sections?: MaaFWPreviewSection[] } | null)?.sections ?? []

  // 一键恢复成功：mas 恢复回填字段（Task/Device 段），需重拉表单；native 恢复
  // 写 MaaFW 项目配置，MAS 表单不受影响
  const handleRestored = async (target: string) => {
    restoreOpen.value = false
    if (target === 'mas') {
      // 恢复回填的是后端 UserData，重拉表单同步页面（含任务快照）
      await loadUserData()
      await reloadInterface(false)
    }
  }

  // 编辑会话归档（进入/退出时机，指纹去重）：进入归档 MaaFW 项目配置当前状态
  // （MAS 触碰前原始态），退出归档 MAS 用户字段侧车终态（编辑会话包络）
  const ensureMaaFWBackup = ensureBackup

  return {
    MAAFW_DISPLAY_NAME,
    restoreOpen,
    restoreTargets,
    restoreApi,
    previewSections,
    handleRestored,
    ensureMaaFWBackup,
  }
}
