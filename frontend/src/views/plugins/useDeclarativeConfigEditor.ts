import { computed, onScopeDispose, ref, watch, type ComputedRef } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { FrontendSurfaceMount, Service, type ConfigUpdateOut } from '@/api'
import {
  declarativeGroups,
  declarativeTables,
  declarativeValues,
} from '@/components/declarative/declarativeLayout'
import { useConfirm } from '@/composables/useConfirm'
import { useConfigBackupApi } from '@/composables/useConfigBackupApi'
import { useUserApi } from '@/composables/useUserApi'
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'
import { useDeclarativeActions } from '@/composables/useDeclarativeActions'
import { useConfigQuery } from '@/services/configUiSync'
import { apiErrorMessage, requestApi } from '@/utils/apiResult'
import { analyticsConfigSection, beginAnalyticsOperation } from '@/utils/analytics'
import { pluginUiPost, type PluginUiActivation } from '@/utils/pluginUiRequests'
import type {
  PluginUiChange,
  PluginUiEditor,
  PluginUiTarget,
} from '@/composables/usePluginUiBridge'
import {
  usePluginSettingsDraft,
  type SettingsChange,
  type SettingsValues,
} from './settings/usePluginSettingsDraft'

export type ConfigEditorTarget =
  | { mode: 'script' | 'setup' | 'plan'; id: string }
  | { mode: 'user'; id: string; scriptId: string }

async function readConfig(target: ConfigEditorTarget) {
  switch (target.mode) {
    case 'setup':
    case 'script':
      return Service.getScriptApiScriptsGetPost({ scriptId: target.id })
    case 'user':
      return Service.getUserApiScriptsUserGetPost({ scriptId: target.scriptId, userId: target.id })
    case 'plan':
      return Service.getPlanApiPlanGetPost({ planId: target.id })
  }
}

function writeConfig(
  target: ConfigEditorTarget,
  data: SettingsValues,
  activation?: PluginUiActivation
) {
  switch (target.mode) {
    case 'setup':
    case 'script': {
      const body = { scriptId: target.id, data }
      return activation
        ? pluginUiPost<ConfigUpdateOut>('/api/scripts/update', body, activation)
        : Service.updateScriptApiScriptsUpdatePost(body)
    }
    case 'user': {
      const body = { scriptId: target.scriptId, userId: target.id, data }
      return activation
        ? pluginUiPost<ConfigUpdateOut>('/api/scripts/user/update', body, activation)
        : Service.updateUserApiScriptsUserUpdatePost(body)
    }
    case 'plan': {
      const body = { planId: target.id, data }
      return activation
        ? pluginUiPost<ConfigUpdateOut>('/api/plan/update', body, activation)
        : Service.updatePlanApiPlanUpdatePost(body)
    }
  }
}

export function useDeclarativeConfigEditor(target: ComputedRef<ConfigEditorTarget>) {
  const client = useQueryClient()
  const { t, locale } = useI18n()
  const { confirm } = useConfirm()
  const draft = usePluginSettingsDraft()
  const saving = ref(false)
  const creatingUser = ref(false)
  const optionsInvalid = ref(false)
  const { addUser } = useUserApi()
  const native = useNativeGuiSession({
    loggerName: '插件配置',
    keys: {
      stopFailed: 'core.plan.universal.stopFailed',
      startFailed: 'core.plan.universal.startFailed',
      setupFailed: 'core.plan.universal.setupFailed',
      opened: 'core.plan.universal.sessionOpened',
      viewOpened: 'core.plan.universal.sessionOpened',
      timeoutWarn: 'core.plan.universal.sessionTimeoutWarn',
      saved: 'core.plan.universal.sessionSaved',
      saveFailed: 'core.plan.universal.saveFailed',
    },
  })
  onScopeDispose(() => {
    void native.dispose()
  })
  const { restoreApi, ensureBackup } = useConfigBackupApi({
    scriptId: () => (target.value.mode === 'user' ? target.value.scriptId : target.value.id),
    userId: () => (target.value.mode === 'user' ? target.value.id : null),
    logger: window.electronAPI.getLogger('配置归档'),
  })
  const detail = useConfigQuery({
    queryKey: computed(() => ['declarative-config', target.value]),
    queryFn: async ({ queryKey }) => {
      const selected = queryKey[1] as ConfigEditorTarget
      const { data, ui, uiSources } = await requestApi(
        () => readConfig(selected),
        t('core.plugins.settingsLoadFailed')
      )
      const document = data[selected.id]
      if (!document) throw new Error(t('core.apiErrors.invalidResponse'))
      return { selected, ui, uiSources, values: declarativeValues(declarativeGroups(ui), document) }
    },
  })
  const ui = computed(() => {
    const current = detail.data.value
    return current && isCurrent(current.selected) ? current.ui : undefined
  })
  const configUid = computed(() => ui.value?.configUid ?? '')
  const wheel = computed(() => {
    const surface = ui.value?.frontendSurfaces?.[target.value.mode]
    if (surface?.mode === FrontendSurfaceMount.mode.WHEEL && surface.entry)
      return { ...surface, entry: surface.entry }
  })
  const wheelTarget = computed<PluginUiTarget>(() => {
    const { mode, id } = target.value
    return {
      kind: mode,
      scriptId: mode === 'plan' ? null : mode === 'user' ? target.value.scriptId : id,
      userId: mode === 'user' ? id : null,
      planId: mode === 'plan' ? id : null,
      configUid: configUid.value,
    }
  })
  const refreshWheel = async () => {
    const { isSuccess } = await detail.refetch()
    return isSuccess && !!wheel.value
  }
  // 托管和账号的 game 分组由 GameBindingSection 编辑，计划可以自行声明同名分组。
  const groups = computed(() =>
    declarativeGroups(ui.value).filter(
      group => target.value.mode === 'plan' || group.name !== 'game'
    )
  )
  const tables = computed(() => declarativeTables(ui.value))
  const backupTargets = computed(() => ui.value?.backupTargets ?? [])
  const ensureTargets = () => Promise.all(backupTargets.value.map(pool => ensureBackup(pool.key)))
  watch(
    configUid,
    uid => {
      if (uid) void ensureTargets()
    },
    { immediate: true, flush: 'sync' }
  )
  const { activeFields, runningKey, runAction } = useDeclarativeActions(
    configUid,
    saving,
    () => detail.refetch(),
    draft
  )
  const busy = computed(
    () =>
      saving.value ||
      creatingUser.value ||
      runningKey.value !== null ||
      native.configLoading.value ||
      !!native.taskId.value ||
      native.stopping.value
  )
  const canWrite = computed(
    () =>
      !!configUid.value &&
      !ui.value?.locked &&
      !busy.value &&
      !optionsInvalid.value &&
      !detail.isFetching.value &&
      !detail.isError.value &&
      !activeFields.value.length
  )
  const canSubmit = computed(
    () =>
      canWrite.value &&
      draft.changes.value.every(({ group, field }) =>
        ui.value?.hints[group]?.some(hint => hint.field === field && hint.editable !== false)
      )
  )
  const canSave = computed(() => canSubmit.value && draft.dirtyCount.value > 0)

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

  async function beforeLeave() {
    if (saving.value || creatingUser.value || runningKey.value || !(await confirmDiscard()))
      return false
    return native.stopSession(true)
  }

  function startNative() {
    const selected = target.value
    const mode = ui.value?.nativeSession
    if (!busy.value && mode && selected.mode !== 'plan') {
      return native.startSession(
        selected.id,
        mode === 'view',
        selected.mode === 'user' ? 'user' : 'script'
      )
    }
  }

  async function stopNative() {
    const selected = target.value
    if (native.currentSessionViewOnly.value) await native.stopSession(true)
    else await native.saveSession()
    if (isCurrent(selected) && !native.taskId.value) await detail.refetch()
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

  async function readBack(selected: ConfigEditorTarget, uid?: string) {
    if (!isCurrent(selected) || (uid && configUid.value !== uid)) return
    const result = await detail.refetch()
    if (result.isSuccess && isCurrent(selected) && (!uid || uid === result.data.ui?.configUid)) {
      draft.reset(result.data.values, { keepDraft: false })
    }
  }

  // 恢复确认打开时固定配置身份，旧弹窗不能回读新条目。
  const onRestored = computed(() => {
    const selected = target.value
    const uid = configUid.value
    return () => readBack(selected, uid)
  })

  async function reload() {
    const selected = target.value
    if (!busy.value && (await confirmDiscard()) && isCurrent(selected)) await readBack(selected)
  }

  async function persist(activation?: PluginUiActivation, fields?: SettingsChange[]) {
    const selected = target.value
    const submitted = draft.snapshot()
    const data = draft.patch(submitted, fields)
    saving.value = true
    const plan = selected.mode === 'plan' ? beginAnalyticsOperation('plan_edit_finished') : null
    const config =
      selected.mode !== 'plan' ? beginAnalyticsOperation('config_write_finished') : null
    let outcome: 'success' | 'failure' = 'failure'
    try {
      await requestApi(() => writeConfig(selected, data, activation), t('core.plugins.saveFailed'))
      outcome = 'success'
      void client.invalidateQueries({
        queryKey: selected.mode === 'plan' ? ['config', 'plans'] : ['config', 'script-list'],
      })
      if (isCurrent(selected)) {
        draft.commit(submitted, fields)
        message.success(t('core.plugins.saved'))
        await Promise.all([detail.refetch(), ensureTargets()])
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
          owner_kind: selected.mode === 'setup' ? 'script' : selected.mode,
          section_kind: analyticsConfigSection(data),
          script_type: 'unknown',
          outcome,
        })
      saving.value = false
    }
  }

  async function save() {
    return canSave.value && persist(wheel.value)
  }

  async function saveWheel(
    changes: PluginUiChange[],
    commit: boolean,
    activation: PluginUiActivation
  ) {
    if (commit && !canWrite.value) return false
    for (const { group, field, value } of changes) draft.update(group, field, value)
    if (!commit) return true
    const fields = draft.changes.value.filter(({ group, field }) =>
      changes.some(change => change.group === group && change.field === field)
    )
    return !fields.length || persist(activation, fields)
  }

  function wheelEditor(locked: boolean): PluginUiEditor {
    const selected = target.value
    const activation = wheel.value
    const isActive = () =>
      isCurrent(selected) &&
      !!activation &&
      wheel.value?.activationId === activation.activationId &&
      !ui.value?.locked
    return {
      locale: locale.value,
      locked: locked || !!ui.value?.locked,
      busy: busy.value || detail.isFetching.value || detail.isError.value,
      groups: groups.value,
      values: draft.values,
      save: async (changes, commit) =>
        !!activation && isActive() && saveWheel(changes, commit, activation),
      runAction: async (group, hint, value, canRun) => {
        if (!activation || !isActive()) return 'cancelled'
        const owner = groups.value.flatMap(({ name, hints }) =>
          hints.flatMap(item =>
            item.field && item.action_ref === `${group}.${hint.field}`
              ? [{ group: name, field: item.field }]
              : []
          )
        )[0]
        return runAction(group, hint, value, owner, {
          activation,
          canRun: () => isActive() && canRun(),
        })
      },
      notify: (severity, text) => void message[severity](text),
    }
  }

  async function finishSetup(openUser: (id: string) => void) {
    const selected = target.value
    if (selected.mode !== 'setup' || !canSubmit.value) return
    if (draft.dirtyCount.value && !(await save())) return
    if (!isCurrent(selected) || !canSubmit.value) return
    creatingUser.value = true
    try {
      const user = await addUser(selected.id, { firstOnly: true })
      if (user?.userId && isCurrent(selected)) openUser(user.userId)
    } finally {
      creatingUser.value = false
    }
  }

  return {
    draft,
    ui,
    configUid,
    groups,
    wheel,
    wheelTarget,
    refreshWheel,
    wheelEditor,
    tables,
    saving,
    canSave,
    canSubmit,
    creatingUser,
    optionsInvalid,
    finishSetup,
    backupTargets,
    restoreApi,
    onRestored,
    native,
    startNative,
    stopNative,
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
