import { beginAnalyticsOperation } from '@/utils/analytics'
import { computed, h, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import { useI18n } from 'vue-i18n'

import type { ThemeColor, ThemeMode } from '@/composables/useTheme'
import { useTheme } from '@/composables/useTheme'
import type {
  AppearanceImportResult,
  InstalledAppearance,
  OnlineAppearanceInstallResult,
} from '@/types/appearance'
import {
  describeOnlineAppearanceError,
  type OnlineAppearanceInstallOutcome,
} from '@/views/themeStore/useOnlineAppearance'
import './appearance.css'
import type { AppearanceCategory } from '@/types/mascotPack'
import { saveConfig } from '@/utils/config'

export function useAppearanceSettings() {
  const { t } = useI18n()
  const [modal, modalContextHolder] = Modal.useModal()
  const modalOptions = { zIndex: 100, wrapClassName: 'appearance-modal' }
  const logger = window.electronAPI.getLogger('外观设置')
  const {
    themeMode,
    themeColor,
    themeColors,
    appearances,
    appearanceId,
    activeAppearance,
    setThemeMode,
    setThemeColor,
    resetTheme,
    setAppearance,
    importAppearance,
    installOnlineAppearance,
    removeAppearance,
  } = useTheme()
  const appearanceBusy = ref(false)
  const themeResetting = ref(false)
  const themeModeOptions = computed(() => [
    { label: t('setting.themeMode.system'), value: 'system' },
    { label: t('setting.themeMode.light'), value: 'light' },
    { label: t('setting.themeMode.dark'), value: 'dark' },
  ])

  const appearanceValue = computed(() =>
    activeAppearance.value ? `appearance:${activeAppearance.value.id}` : themeMode.value
  )

  const appearanceOptions = computed(() => [
    ...themeModeOptions.value,
    ...appearances.value.map(appearance => ({
      label: appearance.name,
      value: `appearance:${appearance.id}`,
    })),
  ])

  const themeColorOptions = computed(() =>
    Object.entries(themeColors).map(([key, color]) => ({
      label: t(`setting.color.${key}`),
      value: key,
      color,
    }))
  )

  const handleThemeModeChange = async (value: SelectValue): Promise<void> => {
    if (typeof value !== 'string') return
    try {
      await setThemeMode(value as ThemeMode)
    } catch {
      message.error(t('setting.basic.appearanceApplyFailed'))
    }
  }

  const handleThemeReset = async (): Promise<void> => {
    if (appearanceBusy.value || themeResetting.value) return
    themeResetting.value = true
    try {
      await resetTheme()
      message.success(t('setting.basic.themeReset'))
    } catch {
      message.error(t('setting.basic.themeResetFailed'))
    } finally {
      themeResetting.value = false
    }
  }

  const handleThemeColorChange = async (value: SelectValue): Promise<void> => {
    if (typeof value !== 'string') return
    try {
      await setThemeColor(value as ThemeColor)
    } catch {
      message.error(t('setting.basic.appearanceApplyFailed'))
    }
  }

  const showAppearancePreview = (appearance: InstalledAppearance) => {
    modal.confirm({
      ...modalOptions,
      title: appearance.name,
      content: h('div', { class: 'appearance-preview-content' }, [
        appearance.previewUrl
          ? h('img', {
              src: appearance.previewUrl,
              alt: appearance.name,
              class: 'appearance-preview-image',
            })
          : null,
        appearance.description ? h('p', appearance.description) : null,
      ]),
      okText: t('setting.basic.applyAppearance'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          await setAppearance(appearance.id)
          message.success(t('setting.basic.appearanceApplied'))
        } catch (error) {
          logger.error(`应用外观失败: ${error instanceof Error ? error.message : String(error)}`)
          message.error(t('setting.basic.appearanceApplyFailed'))
          throw error
        }
      },
    })
  }

  const confirmReplace = (name: string, category: AppearanceCategory): Promise<boolean> =>
    new Promise(resolve => {
      modal.confirm({
        ...modalOptions,
        title: t(
          category === 'mascot'
            ? 'setting.basic.mascotReplaceTitle'
            : 'setting.basic.appearanceReplaceTitle'
        ),
        content: t(
          category === 'mascot'
            ? 'setting.basic.mascotReplaceContent'
            : 'setting.basic.appearanceReplaceContent',
          { name }
        ),
        okText: t('setting.basic.replaceAppearance'),
        cancelText: t('common.cancel'),
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })

  // 本地导入与在线安装共用：同 ID 先确认覆盖，成功后进入预览与应用。
  const runAppearanceInstall = async (
    install: (replace: boolean) => Promise<AppearanceImportResult | OnlineAppearanceInstallResult>,
    describeFailure: (result: AppearanceImportResult | OnlineAppearanceInstallResult) => string,
    category: AppearanceCategory = 'theme'
  ): Promise<OnlineAppearanceInstallOutcome> => {
    let result = await install(false)
    if (!result.success && result.code === 'DUPLICATE_ID') {
      const replace = await confirmReplace(
        result.existing?.name ?? result.existing?.id ?? t('setting.basic.appearance'),
        category
      )
      if (!replace) return 'cancelled'
      result = await install(true)
    }
    if (!result.success) {
      message.error(describeFailure(result))
      return 'failed'
    }
    if (result.appearance) showAppearancePreview(result.appearance)
    if ('mascot' in result && result.mascot) {
      try {
        await saveConfig({ desktopMascotId: result.mascot.id })
      } catch (error) {
        // 资源已经安装，保存选择失败不会撤销安装。
        logger.error(`安装在线外观失败: ${error instanceof Error ? error.message : String(error)}`)
        message.error(t('themeStore.installFailed'))
        return 'partial'
      }
      message.success(t('setting.basic.mascotImported'))
    }
    return 'installed'
  }

  const importAppearanceFromPath = async (
    zipPath: string
  ): Promise<OnlineAppearanceInstallOutcome> => {
    if (appearanceBusy.value) return 'cancelled'
    appearanceBusy.value = true
    try {
      return await runAppearanceInstall(
        replace => importAppearance(zipPath, replace),
        result =>
          result.code === 'INVALID_ANIMATION'
            ? t('setting.basic.appearanceAnimationInvalid')
            : result.error || t('setting.basic.appearanceImportFailed')
      )
    } finally {
      appearanceBusy.value = false
    }
  }

  const installPreparedOnlineAppearance = async (
    token: string,
    category: AppearanceCategory = 'theme'
  ): Promise<OnlineAppearanceInstallOutcome> => {
    if (appearanceBusy.value) return 'cancelled'
    appearanceBusy.value = true
    try {
      return await runAppearanceInstall(
        replace =>
          category === 'mascot'
            ? (window.electronAPI.installOnlineAppearance?.(token, replace, category) ??
              Promise.resolve({ success: false, code: 'UNSUPPORTED' as const }))
            : installOnlineAppearance(token, replace),
        result => describeOnlineAppearanceError(result, 'themeStore.installFailed', category),
        category
      )
    } catch (error) {
      logger.error(`安装在线外观失败: ${error instanceof Error ? error.message : String(error)}`)
      message.error(t('themeStore.installFailed'))
      return 'failed'
    } finally {
      appearanceBusy.value = false
    }
  }

  const handleAppearanceImport = async (): Promise<void> => {
    if (appearanceBusy.value) return
    const telemetry = beginAnalyticsOperation('appearance_package_finished')
    let outcome: 'success' | 'partial' | 'failure' | 'cancelled' | 'unknown' = 'unknown'
    try {
      const paths = await window.electronAPI.selectFile([
        { name: t('setting.basic.importAppearance'), extensions: ['zip'] },
      ])
      if (!paths[0]) {
        outcome = 'cancelled'
        return
      }
      const result = await importAppearanceFromPath(paths[0])
      outcome =
        result === 'installed'
          ? 'success'
          : result === 'partial'
            ? 'partial'
            : result === 'cancelled'
              ? 'cancelled'
              : 'failure'
    } catch (error) {
      logger.error(`导入外观失败: ${error instanceof Error ? error.message : String(error)}`)
      message.error(t('setting.basic.appearanceImportFailed'))
    } finally {
      telemetry.finish({ package_kind: 'theme', action: 'import', outcome })
    }
  }

  const handleAppearanceChange = async (value: SelectValue): Promise<void> => {
    if (typeof value !== 'string') return
    try {
      if (value.startsWith('appearance:')) await setAppearance(value.slice('appearance:'.length))
      else await setThemeMode(value as ThemeMode)
    } catch (error) {
      logger.error(`切换外观失败: ${error instanceof Error ? error.message : String(error)}`)
      message.error(t('setting.basic.appearanceApplyFailed'))
    }
  }

  const handleAppearanceRemove = async (): Promise<void> => {
    if (appearanceBusy.value) return
    const id = appearanceId.value
    if (!id) return
    const appearance = appearances.value.find(item => item.id === id)
    modal.confirm({
      ...modalOptions,
      title: t('setting.basic.removeAppearanceTitle'),
      content: t('setting.basic.removeAppearanceContent', { name: appearance?.name ?? id }),
      okText: t('setting.basic.removeAppearance'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel'),
      onOk: async () => {
        appearanceBusy.value = true
        try {
          const result = await removeAppearance(id)
          if (!result.success) {
            message.error(result.error || t('setting.basic.appearanceRemoveFailed'))
          }
        } catch (error) {
          logger.error(`移除外观失败: ${error instanceof Error ? error.message : String(error)}`)
          message.error(t('setting.basic.appearanceRemoveFailed'))
        } finally {
          appearanceBusy.value = false
        }
      },
    })
  }

  return {
    themeMode,
    themeColor,
    themeColors,
    appearances,
    appearanceId,
    activeAppearance,
    modalContextHolder,
    appearanceBusy,
    themeResetting,
    themeModeOptions,
    appearanceValue,
    appearanceOptions,
    themeColorOptions,
    handleThemeModeChange,
    handleThemeColorChange,
    handleThemeReset,
    handleAppearanceChange,
    handleAppearanceImport,
    handleAppearanceRemove,
    installPreparedOnlineAppearance,
  }
}
