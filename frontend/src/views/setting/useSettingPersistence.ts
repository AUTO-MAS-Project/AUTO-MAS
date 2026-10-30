// 设置保存职责：从 index.vue 抽出。设置页已超 500 行，按组件尺寸约束
// 局部维护不得再增长，保存/回读/同步这条链路独立成 composable。
import { toRaw } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { GlobalConfig } from '@/api'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { invalidateVoiceSettingsCache } from '@/composables/useAudioPlayer'
import { setTelemetryEnabled } from '@/utils/sentry'
import { updateInfo } from '@/composables/useVersionService'

const logger = window.electronAPI.getLogger('设置')

// 这几类配置 Electron 主进程也要用（托盘、自启、更新源等），保存后同步过去
const ELECTRON_SYNCED_CATEGORIES = new Set<keyof GlobalConfig>([
  'UI',
  'Start',
  'Update',
  'Function',
])

// 后端会规范化这些字段的值（加密存储 / URL 校验），保存后要回读；其余字段本地应用即可
const NORMALIZED_SETTING_KEYS = new Set([
  'Replay.Password',
  'Notify.KoishiServerAddress',
  'Notify.OpenClawQQClientSecret',
  'Notify.AuthorizationCode',
  'Update.MirrorChyanCDK',
])

export function useSettingPersistence(settings: GlobalConfig, restartPolling: () => Promise<void>) {
  const { t } = useI18n()
  // loading 随保存链路一起暴露给页面，tabs 的加载态才能反映真实请求
  const { loading, getSettings, updateSettings } = useSettingsApi()

  const syncConfigToElectron = async (data: GlobalConfig) => {
    try {
      if (window.electronAPI?.syncBackendConfig) {
        // toRaw 剥掉 reactive 代理：Electron IPC 的结构化克隆不支持 Proxy，直接传会报
        // "An object could not be cloned"（对已是普通对象的入参 toRaw 原样返回）
        await window.electronAPI.syncBackendConfig({
          UI: toRaw(data.UI),
          Start: toRaw(data.Start),
          Update: toRaw(data.Update),
          Function: toRaw(data.Function),
        })
        logger.info('配置已同步到 Electron')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`同步配置到 Electron 失败: ${errorMsg}`)
    }
  }

  // 刷新设置数据（只在后端会改写值的字段保存后才需要整份回读）
  const refreshSettings = async () => {
    const data = await getSettings()
    if (data) {
      Object.assign(settings, data)
      await syncConfigToElectron(data)
    }
  }

  // 保存设置 - 只发送修改的字段（遵循最小原则）
  const saveSettings = async (category: keyof GlobalConfig, changes: any): Promise<boolean> => {
    try {
      const updateData: GlobalConfig = { [category]: changes }
      const result = await updateSettings(updateData)
      if (!result) {
        // 请求层已提示后端原因，保留当前输入供重试。
        return false
      }
      return true
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`设置保存失败: ${errorMsg}`)
      message.error(t('core.setting.toast.saveFailed'))
      return false
    }
  }

  // 保存成功后本地应用这次变更，不再整份回读
  const applyLocalSettingChange = async (category: keyof GlobalConfig, key: string, value: any) => {
    const section = settings[category] as Record<string, unknown> | undefined
    if (!section) {
      await refreshSettings()
      return
    }
    section[key] = value
    if (ELECTRON_SYNCED_CATEGORIES.has(category)) await syncConfigToElectron(settings)
  }

  // 返回本次保存是否成功，供子组件在失败时跳过成功提示
  const handleSettingChange = async (
    category: keyof GlobalConfig,
    key: string,
    value: any
  ): Promise<boolean> => {
    // 只发送修改的字段
    const changes = { [key]: value }
    const success = await saveSettings(category, changes)

    if (!success) {
      if (category === 'Replay') throw new Error(t('core.setting.toast.saveFailed'))
      return false
    }

    if (NORMALIZED_SETTING_KEYS.has(`${category}.${key}`)) {
      await refreshSettings()
    } else {
      await applyLocalSettingChange(category, key, value)
    }
    // 音频播放器缓存了语音设置，改了就让它下次重读
    if (category === 'Voice') invalidateVoiceSettingsCache()

    if (category === 'Function' && key === 'IfEnableTelemetry') {
      setTelemetryEnabled(Boolean(value))
    }

    // 处理托盘相关配置（需要额外的实时更新调用）
    if (category === 'UI' && (key === 'IfShowTray' || key === 'IfToTray')) {
      try {
        if (window.electronAPI?.updateTraySettings) {
          await window.electronAPI.updateTraySettings({ [key]: value })
        }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`更新托盘失败: ${errorMsg}`)
        message.error(t('core.setting.toast.trayUpdateFailed'))
      }
    }

    // 处理自动更新配置 - 重启更新检查轮询
    if (category === 'Update' && key === 'IfAutoUpdate') {
      try {
        await restartPolling()
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`重启更新检查失败: ${errorMsg}`)
        message.error(t('core.setting.toast.updateCheckFailed'))
      }
    }

    // 暂停状态变化时立即清掉标题栏的"检测到更新"旧提示
    if (category === 'Update' && key === 'PauseUntil') {
      updateInfo.value = null
    }

    return true
  }

  return { loading, syncConfigToElectron, refreshSettings, saveSettings, handleSettingChange }
}
