import { computed, ref, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import type { DeclarativeHint } from './useDeclarativeOptions'
import { useActiveTriggers } from './useActiveTriggers'
import { usePluginApi } from './usePluginApi'
import { apiErrorMessage } from '@/utils/apiResult'

export function useDeclarativeActions(
  configUid: Readonly<Ref<string>>,
  saving: Readonly<Ref<boolean>>,
  refresh: () => Promise<unknown>
) {
  const { t } = useI18n()
  const { runCommand } = usePluginApi()
  const runningKey = ref<string | null>(null)
  const { data: activeTriggers } = useActiveTriggers()
  const activeFields = computed(() =>
    activeTriggers.value
      .filter(item => item.configUid === configUid.value)
      .map(item => `${item.group}.${item.field}`)
  )

  const runAction = async (group: string, hint: DeclarativeHint, value: unknown) => {
    // 仅提交当前按钮字段的触发值，等待后台操作结果并重新加载配置，执行期间阻止重复操作。
    const field = hint.field
    if (
      !field ||
      !configUid.value ||
      hint.editable !== true ||
      runningKey.value ||
      saving.value ||
      activeFields.value.includes(`${group}.${field}`)
    )
      return
    const dropdown = hint.component === 'dropdown-button'
    if (
      (!dropdown && value !== true) ||
      (typeof value !== 'boolean' && typeof value !== 'string' && typeof value !== 'number')
    ) {
      message.error(t('core.plugins.actionFailed'))
      return
    }
    const uid = configUid.value
    runningKey.value = `${group}.${field}`
    try {
      const result = await runCommand('config', {
        configUid: uid,
        group,
        field,
        value: true,
        ...(dropdown ? { option: value } : {}),
      })
      message.success(result.message || t('core.plugins.actionComplete'))
      if (configUid.value === uid) await refresh()
    } catch (error) {
      message.error(apiErrorMessage(error, t('core.plugins.actionFailed')))
    } finally {
      runningKey.value = null
    }
  }

  return { activeFields, runningKey, runAction }
}
