import { computed, ref, watch, type ComputedRef } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { Service } from '@/api'
import {
  declarativeGroups,
  declarativeTables,
  declarativeValues,
} from '@/components/declarative/declarativeLayout'
import { useConfirm } from '@/composables/useConfirm'
import { useDeclarativeActions } from '@/composables/useDeclarativeActions'
import { useConfigQuery } from '@/services/configUiSync'
import { apiErrorMessage, requestApi } from '@/utils/apiResult'
import { analyticsConfigSection, beginAnalyticsOperation } from '@/utils/analytics'
import { usePluginSettingsDraft, type SettingsValues } from './settings/usePluginSettingsDraft'

export type ConfigEditorTarget =
  | { mode: 'script' | 'plan'; id: string }
  | { mode: 'user'; id: string; scriptId: string }

async function readConfig(target: ConfigEditorTarget) {
  switch (target.mode) {
    case 'script':
      return Service.getScriptApiScriptsGetPost({ scriptId: target.id })
    case 'user':
      return Service.getUserApiScriptsUserGetPost({ scriptId: target.scriptId, userId: target.id })
    case 'plan':
      return Service.getPlanApiPlanGetPost({ planId: target.id })
  }
}

function writeConfig(target: ConfigEditorTarget, data: SettingsValues) {
  switch (target.mode) {
    case 'script':
      return Service.updateScriptApiScriptsUpdatePost({ scriptId: target.id, data })
    case 'user':
      return Service.updateUserApiScriptsUserUpdatePost({
        scriptId: target.scriptId,
        userId: target.id,
        data,
      })
    case 'plan':
      return Service.updatePlanApiPlanUpdatePost({ planId: target.id, data })
  }
}

export function useDeclarativeConfigEditor(target: ComputedRef<ConfigEditorTarget>) {
  const client = useQueryClient()
  const { t } = useI18n()
  const { confirm } = useConfirm()
  const draft = usePluginSettingsDraft()
  const saving = ref(false)
  const detail = useConfigQuery({
    queryKey: computed(() => ['declarative-config', target.value]),
    queryFn: async () => {
      const selected = target.value
      const { data, ui, uiSources } = await requestApi(
        () => readConfig(selected),
        t('core.plugins.settingsLoadFailed')
      )
      const document = data[selected.id]
      if (!document) throw new Error(t('core.apiErrors.invalidResponse'))
      return { ui, uiSources, values: declarativeValues(declarativeGroups(ui), document) }
    },
  })
  const ui = computed(() => detail.data.value?.ui)
  const configUid = computed(() => ui.value?.configUid ?? '')
  // 托管和账号的 game 分组由 GameBindingSection 编辑，计划可以自行声明同名分组。
  const groups = computed(() =>
    declarativeGroups(ui.value).filter(
      group => target.value.mode === 'plan' || group.name !== 'game'
    )
  )
  const tables = computed(() => declarativeTables(ui.value))
  const { activeFields, runningKey, runAction } = useDeclarativeActions(configUid, saving, () =>
    detail.refetch()
  )
  const busy = computed(() => saving.value || runningKey.value !== null)
  const canSave = computed(
    () =>
      !busy.value &&
      !detail.isFetching.value &&
      !activeFields.value.length &&
      draft.dirtyCount.value > 0 &&
      draft.changes.value.every(({ group, field }) =>
        ui.value?.hints[group]?.some(hint => hint.field === field && hint.editable !== false)
      )
  )

  // 锁、触发器和其它窗口都可能引起回读。仅在同一条目内保留未提交的字段。
  watch(
    detail.data,
    (next, previous) => {
      draft.reset(next?.values ?? {}, {
        keepDraft: !!next?.ui && next.ui.configUid === previous?.ui?.configUid,
      })
    },
    { immediate: true, flush: 'sync' }
  )

  function confirmDiscard() {
    return (
      !draft.dirtyCount.value ||
      confirm({
        title: t('core.edit.youHaveUnsavedChanges'),
        okText: t('core.edit.discardChanges'),
        cancelText: t('core.edit.keepEditing'),
        tone: 'danger',
      })
    )
  }

  function beforeLeave() {
    return !busy.value && confirmDiscard()
  }

  function isCurrent(selected: ConfigEditorTarget) {
    const current = target.value
    return (
      current.id === selected.id &&
      current.mode === selected.mode &&
      (selected.mode !== 'user' ||
        (current.mode === 'user' && current.scriptId === selected.scriptId))
    )
  }

  async function readBack(selected: ConfigEditorTarget) {
    const result = await detail.refetch()
    if (result.isSuccess && isCurrent(selected)) {
      draft.reset(result.data.values, { keepDraft: false })
    }
  }

  async function reload() {
    const selected = target.value
    if (!busy.value && (await confirmDiscard()) && isCurrent(selected)) await readBack(selected)
  }

  async function save() {
    if (!canSave.value) return false
    const selected = target.value
    const submitted = draft.snapshot()
    const data = draft.patch(submitted)
    saving.value = true
    const plan = selected.mode === 'plan' ? beginAnalyticsOperation('plan_edit_finished') : null
    const config =
      selected.mode !== 'plan' ? beginAnalyticsOperation('config_write_finished') : null
    let outcome: 'success' | 'failure' = 'failure'
    try {
      await requestApi(() => writeConfig(selected, data), t('core.plugins.saveFailed'))
      outcome = 'success'
      void client.invalidateQueries({
        queryKey: selected.mode === 'plan' ? ['config', 'plans'] : ['config', 'script-list'],
      })
      if (isCurrent(selected)) {
        draft.commit(submitted)
        message.success(t('core.plugins.saved'))
        await readBack(selected)
      }
      return true
    } catch (error) {
      if (isCurrent(selected)) {
        draft.saveFailed(error)
        message.error(apiErrorMessage(error, t('core.plugins.saveFailed')))
      }
      return false
    } finally {
      plan?.finish({ plan_type: 'unknown', view_kind: 'complex', operation_kind: 'save', outcome })
      if (selected.mode !== 'plan')
        config?.finish({
          owner_kind: selected.mode,
          section_kind: analyticsConfigSection(data),
          script_type: 'unknown',
          outcome,
        })
      saving.value = false
    }
  }

  return {
    draft,
    ui,
    configUid,
    groups,
    tables,
    saving,
    canSave,
    busy,
    loading: detail.isFetching,
    error: computed(
      () =>
        detail.error.value &&
        apiErrorMessage(detail.error.value, t('core.plugins.settingsLoadFailed'))
    ),
    activeFields,
    runningKey,
    runAction,
    beforeLeave,
    reload,
    save,
  }
}
