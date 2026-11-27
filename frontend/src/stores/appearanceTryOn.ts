import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { message } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { useTheme } from '@/composables/useTheme'
import type { InstalledAppearance } from '@/types/appearance'
import type { OnlineAppearanceInstallOutcome } from '@/views/themeStore/useOnlineAppearance'

export interface AppearanceTryOnSession {
  source: 'store' | 'installed' | 'upload'
  title: string
  versionNo: number | null
  coverUrl?: string
  fileKey?: string
  /** 在线试穿已下载的临时包 token；切换/退出时负责释放。 */
  token?: string
  /** 本机已安装的外观 ID（source === 'installed' 时用于一键启用）。 */
  installedId?: string
  hasBundledMascot: boolean
  appearance: InstalledAppearance
  /** 在线试穿点击「安装并应用」时的安装回调（复用现有商店安装流程与遥测）。 */
  onInstall?: () => Promise<OnlineAppearanceInstallOutcome>
  /** 上传预览试穿点击「返回上传」时的回调。 */
  onReturn?: () => void
}

/**
 * 全局外观试穿沙盒状态：
 * - 纯内存，绝不落盘；崩溃或关窗重启自动回到原外观；
 * - 切到其他页面时底栏全局跟随，保留明确退出与对比入口；
 * - 连续试穿多个主题时，「按住对比」始终对照本机持久化原外观；
 * - 试穿仅预览界面外观（配色、背景、菜单图标、光标），不切换当前桌面宠物。
 */
export const useAppearanceTryOnStore = defineStore('appearanceTryOn', () => {
  const {
    persistedAppearance,
    tryOnAppearance,
    tryOnComparing,
    startAppearanceTryOn,
    setAppearanceTryOnCompare,
    stopAppearanceTryOn,
    setAppearance,
  } = useTheme()

  const session = ref<AppearanceTryOnSession | null>(null)
  const applying = ref(false)

  const active = computed(() => Boolean(session.value && tryOnAppearance.value))
  const comparing = computed(() => active.value && tryOnComparing.value)
  const originalLabel = computed(
    () => persistedAppearance.value?.name || t('core.themeStore.tryOn.systemDefault')
  )

  const discardSessionToken = (target: AppearanceTryOnSession | null): void => {
    if (!target?.token) return
    void Promise.resolve(window.electronAPI.discardOnlineAppearance?.(target.token, 'theme')).catch(
      () => undefined
    )
  }

  const start = (next: AppearanceTryOnSession): void => {
    const previous = session.value
    // 切换试穿目标时释放前一个未消费的在线临时包（同一 token 除外）。
    if (previous?.token && previous.token !== next.token) {
      discardSessionToken(previous)
    }
    session.value = next
    startAppearanceTryOn(next.appearance)
  }

  const setComparing = (value: boolean): void => {
    if (!active.value) return
    setAppearanceTryOnCompare(value)
  }

  const exit = (options: { keepToken?: boolean } = {}): void => {
    const current = session.value
    session.value = null
    stopAppearanceTryOn()
    if (!options.keepToken) discardSessionToken(current)
  }

  const applyCurrent = async (): Promise<void> => {
    const current = session.value
    if (!current || applying.value) return
    if (current.source === 'upload') {
      const returnHandler = current.onReturn
      exit({ keepToken: true })
      returnHandler?.()
      return
    }

    applying.value = true
    try {
      if (current.source === 'installed' && current.installedId) {
        await setAppearance(current.installedId)
        session.value = null
        message.success(t('core.setting.basic.appearanceApplied'))
        return
      }
      if (current.source === 'store' && current.onInstall) {
        const outcome = await current.onInstall()
        if (outcome === 'installed') {
          // 安装流程已消费 token；若安装了新外观且未自动应用，则由原流程弹窗/应用逻辑接管。
          session.value = null
          stopAppearanceTryOn()
        }
      }
    } catch {
      message.error(t('core.setting.basic.appearanceApplyFailed'))
    } finally {
      applying.value = false
    }
  }

  return {
    session,
    active,
    comparing,
    applying,
    originalLabel,
    start,
    setComparing,
    exit,
    applyCurrent,
  }
})
