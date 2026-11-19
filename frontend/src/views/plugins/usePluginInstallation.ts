import { computed, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { PluginCatalogDocument } from '@/api'
import { usePluginApi, type InstallationStage } from '@/composables/usePluginApi'
import { useActiveTriggers } from '@/composables/useActiveTriggers'
import { useTheme } from '@/composables/useTheme'
import { apiErrorMessage } from '@/utils/apiResult'
import { pluginActionHint } from './configActions'

export function usePluginInstallation() {
  // 两个插件页面共用安装命令、升级反馈和跨进程交接提示。
  const api = usePluginApi()
  const { t, locale } = useI18n()
  const { antdTheme } = useTheme()
  const submitting = ref<string | null>(null)
  const { data: activeTriggers } = useActiveTriggers()
  const backgroundInstall = computed(
    () =>
      activeTriggers.value?.find(item => item.group === 'info' && item.field === 'install')
        ?.configUid ?? null
  )
  const installing = computed(() => submitting.value ?? backgroundInstall.value)
  const stage = ref<InstallationStage | null>(null)
  const upgrading = ref(false)
  const [progressMessage, messageHolder] = message.useMessage({ top: 40 })
  const messageKey = 'plugin-installation'

  onScopeDispose(() => {
    // 离页时关闭窗口反馈，后台操作继续由宿主持有。
    progressMessage.destroy(messageKey)
  })
  watch(
    [stage, antdTheme, locale],
    ([current]) => {
      // 重启交接期间持续显示进度，主题及语言变化时更新同一条消息。
      if (!current) {
        progressMessage.destroy(messageKey)
        return
      }
      const progress = upgrading.value ? 'upgradeProgress' : 'installProgress'
      progressMessage.loading({
        key: messageKey,
        content: t(`core.plugins.${progress}.${current}`),
        duration: 0,
      })
    },
    { flush: 'post' }
  )

  const install = async (row: PluginCatalogDocument): Promise<boolean> => {
    // 以市场配置 UID 提交原安装触发器，安装与升级均等待完整加载结果后反馈。
    if (installing.value || pluginActionHint(row.ui, 'info', 'install')?.editable !== true)
      return false
    submitting.value = row.uid
    upgrading.value = row.info?.update_available === true
    try {
      await api.runCommand(
        'install',
        { configUid: row.uid, group: 'info', field: 'install', value: true },
        current => {
          // 使用后端交接状态驱动持续提示，按钮保持加载直至结果确认。
          stage.value = current
        }
      )
      message.success(t(upgrading.value ? 'core.plugins.upgraded' : 'core.plugins.installed'))
      return true
    } catch (error) {
      message.error(apiErrorMessage(error, t('core.plugins.actionFailed')))
      return false
    } finally {
      stage.value = null
      submitting.value = null
    }
  }

  return { installing, activeTriggers, install, messageHolder }
}
