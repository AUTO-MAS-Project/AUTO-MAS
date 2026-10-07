import { computed, h, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import { useI18n } from 'vue-i18n'

import type { ThemeColor, ThemeMode } from '@/composables/useTheme'
import { useTheme } from '@/composables/useTheme'
import type { InstalledAppearance } from '@/types/appearance'
import './appearance.css'

export function useAppearanceSettings() {
  const { t } = useI18n()
  const [modal, modalContextHolder] = Modal.useModal()
  const modalOptions = { zIndex: 100, wrapClassName: 'appearance-modal', style: { top: '16px' } }
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
    setAppearance,
    importAppearance,
    removeAppearance,
  } = useTheme()
  const appearanceBusy = ref(false)

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

  const importAppearanceFromPath = async (zipPath: string, replace = false): Promise<void> => {
    if (appearanceBusy.value) return
    appearanceBusy.value = true
    try {
      const result = await importAppearance(zipPath, replace)
      if (!result.success) {
        if (result.code === 'DUPLICATE_ID' && !replace) {
          modal.confirm({
            ...modalOptions,
            title: t('setting.basic.appearanceReplaceTitle'),
            content: t('setting.basic.appearanceReplaceContent', {
              name: result.existing?.name ?? result.existing?.id ?? t('setting.basic.appearance'),
            }),
            okText: t('setting.basic.replaceAppearance'),
            cancelText: t('common.cancel'),
            onOk: () => importAppearanceFromPath(zipPath, true),
          })
          return
        }
        message.error(result.error || t('setting.basic.appearanceImportFailed'))
        return
      }
      if (result.appearance) showAppearancePreview(result.appearance)
    } finally {
      appearanceBusy.value = false
    }
  }

  const handleAppearanceImport = async (): Promise<void> => {
    try {
      const paths = await window.electronAPI.selectFile([
        { name: t('setting.basic.importAppearance'), extensions: ['zip'] },
      ])
      if (!paths[0]) return
      await importAppearanceFromPath(paths[0])
    } catch (error) {
      logger.error(`导入外观失败: ${error instanceof Error ? error.message : String(error)}`)
      message.error(t('setting.basic.appearanceImportFailed'))
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
    themeModeOptions,
    appearanceValue,
    appearanceOptions,
    themeColorOptions,
    handleThemeModeChange,
    handleThemeColorChange,
    handleAppearanceChange,
    handleAppearanceImport,
    handleAppearanceRemove,
  }
}
