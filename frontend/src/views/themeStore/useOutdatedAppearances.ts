import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { beginAnalyticsOperation } from '@/utils/analytics'
import { appearanceCategory } from '@/utils/preferenceAnalytics'
import type { OnlineAppearanceItem } from '@/types/appearance'
import type { AppearanceCategory } from '@/types/mascotPack'
import type {
  OnlineAppearanceInstallOptions,
  OnlineAppearanceInstallOutcome,
} from './useOnlineAppearance'
import { loadAllOutdatedOnlineAppearances } from './appearanceCatalog'

const UNSUPPORTED = { success: false, code: 'UNSUPPORTED' as const }

export interface UseOutdatedAppearancesOptions {
  install: (
    token: string,
    category: AppearanceCategory,
    options?: OnlineAppearanceInstallOptions
  ) => Promise<OnlineAppearanceInstallOutcome>
  onUpdated?: () => void
  isBusy?: () => boolean
}

/**
 * 独立于搜索、分页和分类页签的全量本机待更新清单与批量更新控制器。
 * 批量更新仅覆盖升级资源包本身，不改动当前启用的主题或桌宠选择。
 */
export function useOutdatedAppearances(options: UseOutdatedAppearancesOptions) {
  const logger = window.electronAPI.getLogger('主题商店')
  const api = () => window.electronAPI
  const items = ref<OnlineAppearanceItem[]>([])
  const loading = ref(false)
  const updatingAll = ref(false)
  let scanRevision = 0

  const discardToken = (token: string, category: AppearanceCategory): void => {
    void api()
      .discardOnlineAppearance?.(token, category)
      ?.catch(error => {
        logger.warn(`清理临时外观包失败: ${error instanceof Error ? error.message : String(error)}`)
      })
  }

  const refresh = async (): Promise<void> => {
    const revision = ++scanRevision
    loading.value = true
    try {
      const result = await loadAllOutdatedOnlineAppearances(
        (query, category) =>
          api().listOnlineAppearances?.(query, category) ?? Promise.resolve(UNSUPPORTED)
      )
      if (revision !== scanRevision) return
      if (result.complete || items.value.length === 0) {
        items.value = result.items
      }
    } catch (error) {
      if (revision !== scanRevision) return
      logger.warn(
        `扫描本机待更新外观失败: ${error instanceof Error ? error.message : String(error)}`
      )
    } finally {
      if (revision === scanRevision) loading.value = false
    }
  }

  const updateAll = async (): Promise<{ succeeded: number; failed: number }> => {
    if (updatingAll.value || options.isBusy?.()) return { succeeded: 0, failed: 0 }
    if (items.value.length === 0) await refresh()
    const targets = [...items.value]
    if (targets.length === 0) return { succeeded: 0, failed: 0 }

    updatingAll.value = true
    let succeeded = 0
    let failed = 0
    try {
      for (const item of targets) {
        if (item.publishedVersionNo === null) continue
        const category: AppearanceCategory = item.categoryKey ?? 'theme'
        const prepared = await api().prepareOnlineAppearance?.(
          item.fileKey,
          item.publishedVersionNo,
          category
        )
        if (!prepared?.success || !prepared.token) {
          failed += 1
          continue
        }
        const telemetry = beginAnalyticsOperation('appearance_store_install_finished')
        let outcome: OnlineAppearanceInstallOutcome = 'failed'
        try {
          outcome = await options.install(prepared.token, category, {
            preserveCurrentSelection: true,
            replaceExisting: true,
          })
        } finally {
          telemetry.finish({
            category_kind: appearanceCategory(category),
            outcome:
              outcome === 'installed'
                ? 'success'
                : outcome === 'partial'
                  ? 'partial'
                  : outcome === 'cancelled'
                    ? 'cancelled'
                    : 'failure',
          })
        }
        if (outcome === 'installed') {
          succeeded += 1
        } else if (outcome !== 'cancelled') {
          failed += 1
          discardToken(prepared.token, category)
        }
      }

      await refresh()
      if (succeeded > 0) options.onUpdated?.()
      if (failed === 0 && succeeded > 0) {
        message.success(t('core.themeStore.localStatus.updateAllSuccess', { count: succeeded }))
      } else if (failed > 0) {
        message.warning(t('core.themeStore.localStatus.updateAllPartial', { succeeded, failed }))
      }
      return { succeeded, failed }
    } finally {
      updatingAll.value = false
    }
  }

  const reset = (): void => {
    scanRevision += 1
    items.value = []
    loading.value = false
    updatingAll.value = false
  }

  return {
    items,
    loading,
    updatingAll,
    refresh,
    updateAll,
    reset,
  }
}
