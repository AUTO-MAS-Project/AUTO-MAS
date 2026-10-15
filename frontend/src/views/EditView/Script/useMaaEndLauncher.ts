import { computed, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ApiError, Service } from '@/api'
import type { MaaEndScriptConfig } from '@/types/script'

type GameConfig = MaaEndScriptConfig['Game']

/** 自动路径只展示；只有手动选择才保存路径，保存成功后再更新界面。 */
export function useMaaEndLauncher(options: {
  game: GameConfig
  getScriptId: () => string
  enabled: () => boolean
  save: (patch: Partial<GameConfig>) => Promise<boolean>
}) {
  const { t } = useI18n()
  const detecting = ref(false)
  const saving = ref(false)
  const detectedPath = ref('')
  const error = ref('')
  const source = computed(() => (options.game.LauncherPath ? 'manual' : 'auto'))
  const path = computed(() => options.game.LauncherPath || detectedPath.value)
  let generation = 0
  let disposed = false

  const refresh = async () => {
    const request = ++generation
    detectedPath.value = ''
    error.value = ''
    detecting.value = false
    if (!options.enabled() || source.value === 'manual' || !options.game.Path) return
    detecting.value = true
    try {
      const result = await Service.getMaaendLauncherPathApiApiScriptsMaaendLauncherPathGet(
        options.getScriptId()
      )
      if (request !== generation || disposed) return
      if (result.code !== 200 || !result.launcher_path) {
        throw new Error(result.message || t('edit.maaEndLauncherDetectFailed'))
      }
      detectedPath.value = result.launcher_path
    } catch (reason) {
      if (request !== generation || disposed) return
      error.value =
        reason instanceof ApiError && typeof reason.body?.message === 'string'
          ? reason.body.message
          : reason instanceof Error
            ? reason.message
            : t('edit.maaEndLauncherDetectFailed')
    } finally {
      if (request === generation && !disposed) detecting.value = false
    }
  }

  const save = async (patch: Partial<GameConfig>) => {
    if (saving.value || disposed) return false
    saving.value = true
    try {
      const success = await options.save(patch)
      if (disposed) return success
      if (success) {
        Object.assign(options.game, patch)
        error.value = ''
      } else {
        error.value = t('edit.maaEndLauncherSaveFailed')
      }
      return success
    } catch (reason) {
      if (!disposed) {
        error.value = reason instanceof Error ? reason.message : t('edit.maaEndLauncherSaveFailed')
      }
      return false
    } finally {
      if (!disposed) saving.value = false
    }
  }

  const selectFile = async () => {
    try {
      const paths = await window.electronAPI.selectFile([
        { name: t('edit.maaEndLauncherPath'), extensions: ['exe'] },
      ])
      const selected = paths?.[0]
      if (!selected || disposed) return
      if (!selected.toLowerCase().endsWith('.exe')) {
        error.value = t('edit.maaEndPickLauncherExeError')
        return
      }
      // 手动选择用于自动识别失败时兜底；后端仅校验文件存在，不限定安装布局。
      await save({ LauncherPath: selected })
    } catch (reason) {
      if (!disposed) {
        error.value = reason instanceof Error ? reason.message : t('edit.maaEndLauncherSaveFailed')
      }
    }
  }

  const changeSource = async (value: 'auto' | 'manual') => {
    if (value === source.value) return
    if (value === 'manual') await selectFile()
    else await save({ LauncherPath: '' })
  }

  const changeLaunchMode = (LaunchMode: GameConfig['LaunchMode']) => save({ LaunchMode })

  watch(
    () => [options.enabled(), options.game.Path, options.game.LauncherPath],
    () => void refresh(),
    { immediate: true }
  )
  onScopeDispose(() => {
    disposed = true
    generation += 1
  })

  return {
    source,
    path,
    error,
    detecting,
    saving,
    refresh,
    selectFile,
    changeSource,
    changeLaunchMode,
  }
}
