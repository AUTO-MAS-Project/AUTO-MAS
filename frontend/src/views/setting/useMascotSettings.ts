import { computed, onMounted, onUnmounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'
import type { MascotSummary } from '@/types/mascotPack'
import { getConfig, saveConfig } from '@/utils/config'

export function useMascotSettings() {
  const { t } = useI18n()
  const { activeAppearance } = useTheme()
  const [modal, modalContextHolder] = Modal.useModal()
  const modalOptions = { zIndex: 100, wrapClassName: 'appearance-modal' }
  const logger = window.electronAPI.getLogger('桌宠设置')
  const mascots = ref<MascotSummary[]>([])
  const selectedId = ref<string | null>(null)
  const enabled = ref(true)
  const loading = ref(true)
  const saving = ref(false)
  const loadFailed = ref(false)
  let refreshRevision = 0
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
    loading.value = true
    try {
      const [config, items] = await Promise.all([
        getConfig(),
        window.electronAPI.listMascots?.() ?? [],
      ])
      if (revision !== refreshRevision) return
      selectedId.value = config.desktopMascotId ?? null
      enabled.value = config.desktopMascotEnabled !== false
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
    if (busy.value || typeof next !== 'string') return
    const id = next === 'theme' ? null : next.slice('mascot:'.length)
    saving.value = true
    try {
      await saveConfig({ desktopMascotId: id })
      selectedId.value = id
    } catch (error) {
      logger.error('保存桌宠选择失败:', error)
      message.error(t('setting.basic.mascotSaveFailed'))
    } finally {
      saving.value = false
    }
  }

  const setEnabled = async (next: boolean): Promise<void> => {
    if (busy.value) return
    saving.value = true
    try {
      await saveConfig({ desktopMascotEnabled: next })
      enabled.value = next
    } catch (error) {
      logger.error('保存桌宠显示设置失败:', error)
      message.error(t('setting.basic.mascotSaveFailed'))
    } finally {
      saving.value = false
    }
  }

  const importMascot = async (): Promise<void> => {
    if (busy.value) return
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
    if (busy.value || !selectedId.value) return
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
    unsubscribe = window.electronAPI.onMascotChanged?.(() => {
      void refresh()
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
    available,
    options,
    busy,
    loading,
    saving,
    loadFailed,
    refresh,
    select,
    setEnabled,
    importMascot,
    removeMascot,
  }
}
