import { computed, ref, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import type { DeclarativeHint } from './useDeclarativeOptions'
import { useActiveTriggers } from './useActiveTriggers'
import { OperationResultError, usePluginApi } from './usePluginApi'
import { apiErrorMessage } from '@/utils/apiResult'
import { useConfirm } from './useConfirm'
import type { PluginUiActivation } from '@/utils/pluginUiRequests'
import type {
  SettingsChange,
  usePluginSettingsDraft,
} from '@/views/plugins/settings/usePluginSettingsDraft'

export function useDeclarativeActions(
  configUid: Readonly<Ref<string>>,
  saving: Readonly<Ref<boolean>>,
  refresh: () => Promise<unknown>,
  draft?: ReturnType<typeof usePluginSettingsDraft>
) {
  const { t } = useI18n()
  const { runCommand } = usePluginApi()
  const { confirm } = useConfirm()
  const runningKey = ref<string | null>(null)
  const { data: activeTriggers } = useActiveTriggers()
  const activeFields = computed(() =>
    activeTriggers.value
      .filter(item => item.configUid === configUid.value)
      .map(item => `${item.group}.${item.field}`)
  )

  const runAction = async (
    group: string,
    hint: DeclarativeHint,
    value: unknown,
    owner?: SettingsChange,
    wheel?: { activation: PluginUiActivation; canRun: () => boolean }
  ) => {
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
      return 'error'
    const dropdown = hint.component === 'dropdown-button'
    if (
      (!dropdown && value !== true) ||
      (typeof value !== 'boolean' && typeof value !== 'string' && typeof value !== 'number')
    ) {
      message.error(t('core.plugins.actionFailed'))
      return 'error'
    }
    const uid = configUid.value
    runningKey.value = `${group}.${field}`
    try {
      const dirty =
        owner &&
        draft?.changes.value.some(
          change => change.group === owner.group && change.field === owner.field
        )
      if (
        dirty &&
        !(await confirm({
          title: t('core.edit.youHaveUnsavedChanges'),
          okText: t('core.edit.discardChanges'),
          cancelText: t('core.edit.keepEditing'),
          tone: 'warning',
        }))
      )
        return 'cancelled'
      if (uid !== configUid.value || (wheel && !wheel.canRun())) return 'cancelled'
      const result = await runCommand(
        'config',
        { configUid: uid, group, field, value: true, ...(dropdown ? { option: value } : {}) },
        undefined,
        wheel?.activation
      )
      message.success(result.message || t('core.plugins.actionComplete'))
      if (configUid.value === uid) {
        if (dirty) draft!.discardField(owner.group, owner.field)
        await refresh()
      }
      return 'success'
    } catch (error) {
      message.error(apiErrorMessage(error, t('core.plugins.actionFailed')))
      return error instanceof OperationResultError && error.outcome === 'cancelled'
        ? 'cancelled'
        : 'error'
    } finally {
      runningKey.value = null
    }
  }

  return { activeFields, runningKey, runAction }
}
