import { computed, ref, shallowRef } from 'vue'
import { message } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { useUserApi } from '@/composables/useUserApi'
import type { MaaFWUserConfig } from '@/types/script'
import type { MaaFWUserQueueImportCandidate } from '../../MaaFWFlavor/sectionContracts'
import type { MaaFWTaskQueue } from './useMaaFWTaskQueue'
import type { MaaFWUserIdHolder } from './useMaaFWUserPersistence'

interface MaaFWUserQueueImportOptions {
  scriptId: string
  userIdHolder: MaaFWUserIdHolder
  queue: Pick<MaaFWTaskQueue, 'describeQueueSnapshot' | 'replaceQueueWith'>
}

type SourceUser = { userId: string; name: string; snapshot: unknown }

/**
 * 「配置导入」的「本脚本其他用户」页签：取同一脚本的其他用户，按当前项目判断各自队列里哪些能导入，
 * 选中后用它的队列替换当前用户的（语义同套用预设）。只导入任务队列，其他字段不动。
 *
 * 用户列表在弹窗打开时取一次（`loadUserImportCandidates`）；能不能导入随 interface / 控制器实时算，
 * 弹窗只管显示与交回选中的用户。
 */
export function useMaaFWUserQueueImport({
  scriptId,
  userIdHolder,
  queue,
}: MaaFWUserQueueImportOptions) {
  const { getUsers } = useUserApi()

  const sourceUsers = shallowRef<SourceUser[]>([])
  const userImportLoading = ref(false)

  const loadUserImportCandidates = async () => {
    userImportLoading.value = true
    try {
      const response = await getUsers(scriptId)
      if (!response) {
        sourceUsers.value = []
        return
      }
      sourceUsers.value = response.index
        .filter(item => item.uid !== userIdHolder.value)
        .map(item => {
          const user = response.data[item.uid] as Partial<MaaFWUserConfig> | undefined
          return {
            userId: item.uid,
            name: user?.Info?.Name || item.uid,
            snapshot: user?.Task?.TaskSnapshot ?? null,
          }
        })
    } finally {
      userImportLoading.value = false
    }
  }

  // 队列为空（受管任务不算）的用户不列
  const userImportCandidates = computed<MaaFWUserQueueImportCandidate[]>(() =>
    sourceUsers.value
      .map(user => ({
        userId: user.userId,
        name: user.name,
        ...queue.describeQueueSnapshot(user.snapshot as string | Record<string, unknown> | null),
      }))
      .filter(candidate => candidate.chips.length > 0)
  )

  /**
   * 用选中用户的队列替换当前队列。写进后端后才提示「已导入 N 个任务」（N 是实际写入的实例数）；
   * 保存失败时 updateUser 与页头保存状态已经报过错，这里不再提示。没导进来的任务卡片上已经标过。
   */
  const importQueueFromUser = async (userId: string) => {
    const candidate = userImportCandidates.value.find(item => item.userId === userId)
    if (!candidate || candidate.entries.length === 0) return null
    const importedCount = await queue.replaceQueueWith(candidate)
    if (importedCount !== null) {
      message.success(t('edit.shellQueueImportDone', { count: importedCount }))
    }
    return importedCount
  }

  return {
    userImportCandidates,
    userImportLoading,
    loadUserImportCandidates,
    importQueueFromUser,
  }
}
