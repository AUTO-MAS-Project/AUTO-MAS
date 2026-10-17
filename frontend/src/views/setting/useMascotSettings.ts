import { computed, onMounted, onUnmounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'
import type { MascotSummary } from '@/types/mascotPack'
import { getConfig, saveConfig } from '@/utils/config'

export const MASCOT_MIN_FPS = 1
export const MASCOT_MAX_FPS = 120
const DEFAULT_CUSTOM_FPS = 60

export function useMascotSettings() {
  const { t } = useI18n()
  const { activeAppearance } = useTheme()
  const [modal, modalContextHolder] = Modal.useModal()
  const modalOptions = { zIndex: 100, wrapClassName: 'appearance-modal' }
  const logger = window.electronAPI.getLogger('桌宠设置')
  const mascots = ref<MascotSummary[]>([])
  const selectedId = ref<string | null>(null)
  const enabled = ref(true)
  const fpsMode = ref<'package' | 'custom'>('package')
  const fps = ref<number | null>(DEFAULT_CUSTOM_FPS)
  const loading = ref(true)
  const selecting = ref(false)
  const toggling = ref(false)
  const saving = ref(false)
  const loadFailed = ref(false)
  let refreshRevision = 0
  let selectionRevision = 0
  let savedFps: number | null = null
  let requestedFps: number | null = null
  let fpsSaveRevision = 0
  let unsubscribe: (() => void) | undefined

  const busy = computed(() => loading.value || saving.value)
  const value = computed(() => (selectedId.value ? `mascot:${selectedId.value}` : 'theme'))
  const available = computed(() =>
    selectedId.value
      ? mascots.value.some(item => item.id === selectedId.value)
      : Boolean(activeAppearance.value?.mascotUrl)
  )
  const options = computed(() => [
    { label: t('setting.basic.mascotFollowTheme'), value: 'theme' },
    ...mascots.value.map(item => ({ label: item.name, value: `mascot:${item.id}` })),
    ...(selectedId.value && !mascots.value.some(item => item.id === selectedId.value)
      ? [
          {
            label: t('setting.basic.mascotMissing'),
            value: `mascot:${selectedId.value}`,
            disabled: true,
          },
        ]
      : []),
  ])

  const refresh = async (): Promise<void> => {
    const revision = ++refreshRevision
    const selectionAtStart = selectionRevision
    loading.value = true
    try {
      const [config, items] = await Promise.all([
        getConfig(),
        window.electronAPI.listMascots?.() ?? [],
      ])
      if (revision !== refreshRevision) return
      if (selectionAtStart === selectionRevision) {
        selectedId.value = config.desktopMascotId ?? null
        enabled.value = config.desktopMascotEnabled !== false
      }
      savedFps = config.desktopMascotFps ?? null
      requestedFps = savedFps
      fpsMode.value = savedFps === null ? 'package' : 'custom'
      fps.value = savedFps ?? DEFAULT_CUSTOM_FPS
      mascots.value = items
      loadFailed.value = false
    } catch (error) {
      if (revision !== refreshRevision) return
      loadFailed.value = true
      logger.error('加载桌宠设置失败:', error)
    } finally {
      if (revision === refreshRevision) loading.value = false
    }
  }

  const select = async (next: SelectValue): Promise<void> => {
    if (busy.value || selecting.value || typeof next !== 'string') return
    const id = next === 'theme' ? null : next.slice('mascot:'.length)
    if (id === selectedId.value) return
    selecting.value = true
    try {
      await saveConfig({ desktopMascotId: id })
      selectedId.value = id
    } catch (error) {
      logger.error('保存桌宠选择失败:', error)
      message.error(t('setting.basic.mascotSaveFailed'))
    } finally {
      selecting.value = false
    }
  }

  const setEnabled = async (next: boolean): Promise<void> => {
    if (busy.value || toggling.value || next === enabled.value) return
    toggling.value = true
    try {
      await saveConfig({ desktopMascotEnabled: next })
      enabled.value = next
    } catch (error) {
      logger.error('保存桌宠显示设置失败:', error)
      message.error(t('setting.basic.mascotSaveFailed'))
    } finally {
      toggling.value = false
    }
  }

  const setFps = (next: number | string | null): void => {
    if (next === null || typeof next === 'number') fps.value = next
  }

  const persistFps = async (next: number | null): Promise<void> => {
    if (next === requestedFps) return
    const revision = ++fpsSaveRevision
    requestedFps = next
    try {
      await saveConfig({ desktopMascotFps: next })
      savedFps = next
    } catch (error) {
      if (revision === fpsSaveRevision) {
        requestedFps = savedFps
        fps.value = savedFps ?? DEFAULT_CUSTOM_FPS
        fpsMode.value = savedFps === null ? 'package' : 'custom'
      }
      logger.error('保存桌宠帧率失败:', error)
      message.error(t('setting.basic.mascotSaveFailed'))
    }
  }

  const saveFps = async (): Promise<void> => {
    if (busy.value) return
    if (fpsMode.value === 'package') {
      await persistFps(null)
      return
    }
    if (
      fps.value === null ||
      !Number.isInteger(fps.value) ||
      fps.value < MASCOT_MIN_FPS ||
      fps.value > MASCOT_MAX_FPS
    ) {
      fps.value = savedFps ?? DEFAULT_CUSTOM_FPS
      return
    }
    await persistFps(fps.value)
  }

  const setFpsMode = async (next: SelectValue): Promise<void> => {
    if (busy.value || (next !== 'package' && next !== 'custom')) return
    fpsMode.value = next
    fps.value ??= DEFAULT_CUSTOM_FPS
    await saveFps()
  }

  const importMascot = async (): Promise<void> => {
    if (busy.value || selecting.value) return
    if (!window.electronAPI.importMascot) {
      message.error(t('setting.basic.mascotUnsupported'))
      return
    }
    saving.value = true
    try {
      const paths = await window.electronAPI.selectFile([
        { name: t('setting.basic.importMascot'), extensions: ['zip'] },
      ])
      if (!paths[0]) return
      let result = await window.electronAPI.importMascot(paths[0])
      if (result.code === 'DUPLICATE_ID') {
        const confirmed = await new Promise<boolean>(resolve =>
          modal.confirm({
            ...modalOptions,
            title: t('setting.basic.mascotReplaceTitle'),
            content: t('setting.basic.mascotReplaceContent', {
              name: result.existing?.name ?? t('setting.basic.mascotSection'),
            }),
            okText: t('setting.basic.replaceAppearance'),
            cancelText: t('common.cancel'),
            onOk: () => resolve(true),
            onCancel: () => resolve(false),
          })
        )
        if (!confirmed) return
        result = await window.electronAPI.importMascot(paths[0], true)
      }
      if (!result.success || !result.mascot) {
        message.error(
          t(
            result.code === 'INVALID_ANIMATION'
              ? 'setting.basic.appearanceAnimationInvalid'
              : 'setting.basic.mascotImportFailed'
          )
        )
        return
      }
      await saveConfig({ desktopMascotId: result.mascot.id })
      await refresh()
      message.success(t('setting.basic.mascotImported'))
    } catch (error) {
      logger.error('导入桌宠失败:', error)
      message.error(t('setting.basic.mascotImportFailed'))
    } finally {
      saving.value = false
    }
  }

  const removeMascot = (): void => {
    if (busy.value || selecting.value || !selectedId.value) return
    const id = selectedId.value
    modal.confirm({
      ...modalOptions,
      title: t('setting.basic.mascotRemoveTitle'),
      content: t('setting.basic.mascotRemoveContent', {
        name: mascots.value.find(item => item.id === id)?.name ?? id,
      }),
      okText: t('setting.basic.removeMascot'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel'),
      onOk: async () => {
        saving.value = true
        try {
          const result = await window.electronAPI.removeMascot?.(id)
          if (!result?.success) throw new Error(result?.error ?? '桌宠移除失败')
          await refresh()
        } catch (error) {
          logger.error('移除桌宠失败:', error)
          message.error(t('setting.basic.mascotRemoveFailed'))
        } finally {
          saving.value = false
        }
      },
    })
  }

  onMounted(() => {
    unsubscribe = window.electronAPI.onMascotChanged?.(selection => {
      if (selection) {
        selectionRevision++
        selectedId.value = selection.id
        enabled.value = selection.enabled
      } else {
        void refresh()
      }
    })
    void refresh()
  })
  onUnmounted(() => {
    unsubscribe?.()
    refreshRevision++
  })

  return {
    modalContextHolder,
    selectedId,
    value,
    enabled,
    fpsMode,
    fps,
    available,
    options,
    busy,
    loading,
    selecting,
    toggling,
    saving,
    loadFailed,
    refresh,
    select,
    setEnabled,
    setFps,
    saveFps,
    setFpsMode,
    importMascot,
    removeMascot,
  }
}
