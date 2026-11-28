<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'

import { createReusableTemplate } from '@vueuse/core'
import PluginUiMount from '@/components/PluginUiMount.vue'
import type { PluginUiEditor } from '@/composables/usePluginUiBridge'
import { compatibleWheel, indexPluginScriptTypes } from '@/utils/pluginScriptTypes'
import type { PluginUiActivation } from '@/utils/pluginUiRequests'
import type { SettingsChange } from './plugins/settings/usePluginSettingsDraft'
import { DeclarativeForm } from '@/components/declarative'
import {
  declarativeGroups,
  resolveActionOwner,
  declarativeTables,
  declarativeValues,
} from '@/components/declarative/declarativeLayout'
import PluginAvatar from './plugins/components/PluginAvatar.vue'
import SettingsDirtyBar from './plugins/settings/SettingsDirtyBar.vue'
import SettingsLeaveModal from './plugins/settings/SettingsLeaveModal.vue'
import { AppPage, PageHeader, StateView } from '@/components/ui'
import type { PluginConfigUi, PluginRegistryGetOut } from '@/api'
import { pluginCatalogQueryKey, usePluginQuery } from '@/views/plugins/usePluginQuery'
import { usePluginModelContext } from '@/views/plugins/usePluginCenterData'
import { joinSegments, toInstalledViews, toMarketViews } from '@/views/plugins/pluginCenterModel'
import { usePluginSettingsDraft } from '@/views/plugins/settings/usePluginSettingsDraft'
import { useDeclarativeActions } from '@/composables/useDeclarativeActions'
import { usePluginApi } from '@/composables/usePluginApi'
import { apiErrorMessage } from '@/utils/apiResult'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const api = usePluginApi()
const modelContext = usePluginModelContext()
const draft = usePluginSettingsDraft()
const saving = ref(false)
const configUid = ref('')
const locked = ref(false)
const revision = ref(0)
const [DefineForm, SettingsForm] = createReusableTemplate()
const optionsInvalid = ref(false)
const registry = shallowRef<PluginRegistryGetOut | null>(null)
const configUi = shallowRef<PluginConfigUi>()
const groups = computed(() => declarativeGroups(configUi.value))
const tables = computed(() => declarativeTables(configUi.value))

// 路由切换插件时复用页面实例。
const pluginId = computed(() => String(route.params.pluginId || ''))
/** 只读插件中心已经取到的市场目录缓存（不在这里发请求），给名称回落用。 */
const catalog = usePluginQuery(
  () => pluginCatalogQueryKey(locale.value),
  () => api.getCatalog(),
  () => t('core.plugins.marketLoadFailed')
)
/** 页头的图标、名称与插件标识，缺声明时按插件中心的同一套规则回落。 */
const view = computed(() => {
  const market = toMarketViews(catalog.data.value, registry.value, modelContext.value)
  const views = toInstalledViews(registry.value, market, modelContext.value)
  return views.find(item => item.uid === pluginId.value) ?? null
})
/** 读不到注册记录时沿用原口径显示路由里的条目标识。 */
const title = computed(() => view.value?.name ?? pluginId.value)
/** 名称已经回落成插件标识时，副标题不再重复一遍标识。 */
const headerMeta = computed(() =>
  joinSegments([
    view.value?.pluginId === title.value ? null : view.value?.pluginId,
    view.value?.version,
  ])
)
const errorMessage = (error: unknown) => apiErrorMessage(error, t('core.plugins.actionFailed'))

const {
  loading,
  error: loadError,
  data: settings,
  execute: fetchSettings,
} = usePluginQuery(
  () => /* 以插件身份和语言隔离配置查询缓存。 */ [
    'plugins',
    'settings',
    pluginId.value,
    locale.value,
  ],
  async () => {
    // 并发加载插件记录与专属配置；过期路由或语言的结果由调用方丢弃。
    if (!pluginId.value) return null
    const requestedId = pluginId.value
    const requestedLocale = locale.value
    const [registryResult, config] = await Promise.all([
      api.getRegistry(requestedId),
      api.getConfig(requestedId),
    ])
    return {
      requestedId,
      requestedLocale,
      registry: registryResult,
      config: config.data,
      uiSources: [...(registryResult.uiSources ?? []), ...(config.uiSources ?? [])],
    }
  },
  () => /* 为插件专属配置查询提供当前语言的加载失败提示。 */ t('core.plugins.settingsLoadFailed')
)

const { runningKey, activeFields, runAction } = useDeclarativeActions(
  configUid,
  saving,
  fetchSettings,
  draft
)
const writeBusy = computed(
  () => loading.value || saving.value || !!runningKey.value || !!activeFields.value.length
)

watch(
  pluginId,
  () => {
    configUid.value = ''
    registry.value = null
    configUi.value = undefined
    draft.reset({}, { keepDraft: false })
    return fetchSettings()
  },
  { immediate: true }
)
watch(locale, fetchSettings)

watch(
  settings,
  result => {
    if (!result || result.requestedId !== pluginId.value || result.requestedLocale !== locale.value)
      return
    registry.value = result.registry
    const data = result.config ?? {}
    const keepDraft = data.uid === configUid.value
    configUid.value = typeof data.uid === 'string' ? data.uid : ''
    locked.value = data.locked === true
    revision.value++
    configUi.value = data.ui
    draft.reset(declarativeValues(groups.value, data), { keepDraft })
  },
  { immediate: true }
)

const save = async (
  options: { reload: boolean; activation?: PluginUiActivation; fields?: SettingsChange[] } = {
    reload: true,
  }
) => {
  // 在无在途保存或动作时提交当前配置值，成功后按需重新读取后端规范化结果。
  if (locked.value || writeBusy.value || optionsInvalid.value) return false
  saving.value = true
  try {
    const submitted = draft.snapshot()
    const uid = configUid.value
    await api.updateConfig(
      { recordId: pluginId.value, data: draft.patch(submitted, options.fields) },
      options.activation
    )
    if (uid !== configUid.value) return false
    // 先把基线设为刚提交的值；之后重读失败也只剩失败重试条，不再显示未保存。
    draft.commit(submitted, options.fields)
    message.success(t('core.plugins.saved'))
    if (options.reload) await fetchSettings()
    return true
  } catch (error) {
    const reason = errorMessage(error)
    draft.saveFailed(error)
    message.error(reason)
    return false
  } finally {
    saving.value = false
  }
}

const wheel = computed(() =>
  compatibleWheel(indexPluginScriptTypes(registry.value?.data).settingsPanels.get(pluginId.value))
)
const refreshWheel = async () => !!(await fetchSettings()) && !!wheel.value
const editor = computed<PluginUiEditor>(() => ({
  locale: locale.value,
  locked: locked.value,
  busy: writeBusy.value,
  groups: groups.value,
  values: draft.values,
  configRevision: revision.value,
  async save(changes, commit) {
    const activation = wheel.value
    if (!activation || writeBusy.value || locked.value)
      return { ok: false, code: 'read_only', message: t('core.plugins.saveFailed') }
    for (const { group, field, value } of changes) draft.update(group, field, value)
    if (!commit || !changes.length || (await save({ reload: true, activation, fields: changes })))
      return { ok: true }
    return {
      ok: false,
      code: 'save_failed',
      message: t('core.plugins.saveFailed'),
      fieldErrors: draft.errors.value,
    }
  },
  runAction: (group, hint, value, canRun) =>
    runAction(group, hint, value, resolveActionOwner(groups.value, group, hint.field!), {
      activation: wheel.value!,
      canRun,
    }),
  notify: (severity, text) => void message[severity](text),
}))

// 离开确认：有未保存更改时由弹层决定是否放行这次路由跳转。
const leaveOpen = ref(false)
let resolveLeave: ((allow: boolean) => void) | null = null
const confirmLeave = () => {
  if (!draft.dirtyCount.value) return true
  // 上一次跳转还在等确认时又发起了新跳转：旧的那次不再放行。
  resolveLeave?.(false)
  leaveOpen.value = true
  return new Promise<boolean>(resolve => {
    resolveLeave = resolve
  })
}
const finishLeave = (allow: boolean) => {
  leaveOpen.value = false
  resolveLeave?.(allow)
  resolveLeave = null
}
const discardAndLeave = () => {
  draft.discard()
  finishLeave(true)
}
const saveAndLeave = async () => finishLeave(await save({ reload: false }))

onBeforeRouteLeave(() => confirmLeave())
onBeforeRouteUpdate((to, from) => to.params.pluginId === from.params.pluginId || confirmLeave())
</script>

<template>
  <AppPage layout="fill">
    <PageHeader :title="title || t('core.plugins.settings')" :subtitle="headerMeta || undefined">
      <template #leading>
        <a-button
          type="text"
          :aria-label="t('core.plugins.back')"
          @click="router.push({ name: 'Plugins' })"
          ><ArrowLeftOutlined
        /></a-button>
        <PluginAvatar v-if="view" :icon="view.icon" />
      </template>
    </PageHeader>
    <div class="plugin-settings-content">
      <StateView
        :loading="loading"
        :error="loadError"
        :empty="!groups.length && !wheel"
        :empty-description="t('core.plugins.noSettings')"
        overlay-loading
        @retry="fetchSettings"
      >
        <DefineForm>
          <DeclarativeForm
            v-if="groups.length"
            :groups="groups"
            :tables="tables"
            :steps="configUi?.steps"
            :sections="configUi?.sections"
            :plugin-name="view?.pluginId"
            :submit-disabled="writeBusy || !draft.dirtyCount.value"
            :submitting="saving"
            :errors="draft.errors.value"
            :uid="configUid"
            :namespace="`plugins.${view?.pluginId ?? ''}.config`"
            :disabled="locked || saving || runningKey !== null"
            :values="draft.values"
            :running-key="runningKey"
            :active-fields="activeFields"
            @update:value="draft.update"
            @update:options-invalid="optionsInvalid = $event"
            @action="runAction"
            @finish="save()"
          >
            <template #footer="{ wizard }">
              <SettingsDirtyBar
                v-if="draft.dirtyCount.value"
                :count="draft.dirtyCount.value"
                :saving="saving"
                :disabled="writeBusy"
                :save-disabled="optionsInvalid"
                :wizard="wizard"
                @discard="draft.discard"
                @save="save()"
              />
            </template>
          </DeclarativeForm>
        </DefineForm>
        <PluginUiMount
          v-if="wheel"
          :mount="wheel"
          :editor="editor"
          :refresh="refreshWheel"
          :target="{
            kind: 'settings',
            pluginId,
            configUid,
            scriptId: null,
            userId: null,
            planId: null,
          }"
        >
          <template #fallback>
            <SettingsForm v-if="groups.length" />
            <StateView v-else empty :empty-description="t('core.plugins.noSettings')" />
          </template>
        </PluginUiMount>
        <SettingsForm v-else />
      </StateView>
    </div>
    <SettingsLeaveModal
      :open="leaveOpen"
      :count="draft.dirtyCount.value"
      :saving="saving"
      :save-disabled="writeBusy || optionsInvalid"
      @stay="finishLeave(false)"
      @discard="discardAndLeave"
      @save="saveAndLeave"
    />
  </AppPage>
</template>

<style scoped>
.plugin-settings-content {
  flex: 1;
  overflow: auto;
  padding: var(--app-page-content-padding);
}
</style>
