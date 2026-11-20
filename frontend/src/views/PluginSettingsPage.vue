<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'

import PluginDeclarativeForm from './plugins/components/PluginDeclarativeForm.vue'
import PluginAvatar from './plugins/components/PluginAvatar.vue'
import SettingsDirtyBar from './plugins/settings/SettingsDirtyBar.vue'
import SettingsLeaveModal from './plugins/settings/SettingsLeaveModal.vue'
import PageHeader from '@/components/PageHeader.vue'
import NoData from '@/components/NoData.vue'
import PageSurface from '@/components/PageSurface.vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import type { PluginRegistryGetOut } from '@/api'
import { pluginCatalogQueryKey, usePluginQuery } from '@/views/plugins/usePluginQuery'
import { usePluginModelContext } from '@/views/plugins/usePluginCenterData'
import {
  joinSegments,
  pluginSettingsGroups,
  toInstalledViews,
  toMarketViews,
} from '@/views/plugins/pluginCenterModel'
import {
  usePluginSettingsDraft,
  type SettingsValues,
} from '@/views/plugins/settings/usePluginSettingsDraft'
import { usePluginApi } from '@/composables/usePluginApi'
import { apiErrorMessage } from '@/utils/apiResult'
import type { DeclarativeHint } from './plugins/components/PluginDeclarativeField.vue'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const api = usePluginApi()
const modelContext = usePluginModelContext()
const draft = usePluginSettingsDraft()
const saving = ref(false)
const runningKey = ref<string | null>(null)
const configUid = ref('')
const registry = shallowRef<PluginRegistryGetOut | null>(null)
const groups = ref<Array<{ name: string; hints: DeclarativeHint[] }>>([])

const pluginId = computed(() =>
  /* 从路由参数取得当前插件记录标识，支持同页面实例内切换插件。 */ String(
    route.params.pluginId || ''
  )
)
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
const errorMessage = (error: unknown) =>
  /* 从接口异常中提取可展示原因，缺失时使用插件操作失败提示。 */ apiErrorMessage(
    error,
    t('core.plugins.actionFailed')
  )

const {
  loading,
  error: loadError,
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
    return { requestedId, requestedLocale, registry: registryResult, config: config.data }
  },
  () => /* 为插件专属配置查询提供当前语言的加载失败提示。 */ t('core.plugins.settingsLoadFailed')
)

/** 读取并建立分组与编辑值；keepDraft 时保留未保存的改动（切换语言、按钮执行后的重读）。 */
const load = async (options: { keepDraft: boolean } = { keepDraft: true }) => {
  const result = await fetchSettings()
  if (!result || result.requestedId !== pluginId.value || result.requestedLocale !== locale.value)
    return
  registry.value = result.registry
  const data =
    result.config && typeof result.config === 'object'
      ? (result.config as Record<string, unknown>)
      : {}
  configUid.value = typeof data.uid === 'string' ? data.uid : ''
  // 自有配置与注册表是不同对象；插件没有自有配置时展示空态。
  groups.value = pluginSettingsGroups<DeclarativeHint>(data)
  const next: SettingsValues = {}
  for (const group of groups.value) {
    const source = data[group.name]
    next[group.name] =
      source && typeof source === 'object' ? { ...(source as Record<string, unknown>) } : {}
  }
  draft.reset(next, options)
}
const retry = () => load()

const save = async (options: { reload: boolean } = { reload: true }) => {
  // 在无在途保存或动作时提交当前配置值，成功后按需重新读取后端规范化结果。
  if (saving.value || runningKey.value) return false
  saving.value = true
  try {
    const submitted = draft.snapshot()
    await api.updateConfig({ recordId: pluginId.value, data: submitted })
    // 先把基线设为刚提交的值；之后重读失败也只剩失败重试条，不再显示未保存。
    draft.commit(submitted)
    message.success(t('core.plugins.saved'))
    if (options.reload) await load({ keepDraft: false })
    return true
  } catch (error) {
    message.error(errorMessage(error))
    return false
  } finally {
    saving.value = false
  }
}

const runAction = async (group: string, hint: DeclarativeHint, value: unknown) => {
  // 仅提交当前按钮字段的触发值，等待后台操作结果并重新加载配置，执行期间阻止重复操作。
  const field = hint.field
  if (!field || !configUid.value || hint.editable !== true || runningKey.value || saving.value)
    return
  runningKey.value = `${group}.${field}`
  try {
    if (typeof value !== 'boolean' && typeof value !== 'string') return
    const result = await api.runCommand('config', {
      configUid: configUid.value,
      group,
      field,
      value,
    })
    message.success(result.message || t('core.plugins.actionComplete'))
    await load()
  } catch (error) {
    message.error(errorMessage(error))
  } finally {
    runningKey.value = null
  }
}

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

watch(pluginId, () => load({ keepDraft: false }), { immediate: true })
watch(locale, () => load())
</script>

<template>
  <main class="plugin-settings-page">
    <PageHeader class="plugin-settings-header" :title="title || t('core.plugins.settings')">
      <!-- PageHeader 没有标题下方的插槽：leading 里的内容与标题同属一个网格，副标题用网格行排到标题下面。 -->
      <template #leading>
        <span class="plugin-settings-lead">
          <a-button
            type="text"
            :aria-label="t('core.plugins.back')"
            @click="router.push({ name: 'Plugins' })"
            ><ArrowLeftOutlined
          /></a-button>
          <PluginAvatar v-if="view" :icon="view.icon" />
        </span>
        <span v-if="headerMeta" class="plugin-settings-meta">{{ headerMeta }}</span>
      </template>
    </PageHeader>
    <PageSurface>
      <ApiRetryAlert :error="loadError" :loading="loading" @retry="retry" />
      <a-spin :spinning="loading">
        <NoData
          v-if="!loading && !loadError && !groups.length"
          :description="t('core.plugins.noSettings')"
        />
        <PluginDeclarativeForm
          v-else-if="groups.length"
          :groups="groups"
          :uid="configUid"
          :namespace="`plugins.${view?.pluginId ?? ''}.config`"
          :disabled="saving || runningKey !== null"
          :values="draft.values"
          :running-key="runningKey"
          @update:value="draft.update"
          @action="runAction"
        />
      </a-spin>
      <SettingsDirtyBar
        v-if="draft.dirtyCount.value"
        :count="draft.dirtyCount.value"
        :saving="saving"
        :disabled="loading || runningKey !== null"
        @discard="draft.discard"
        @save="save()"
      />
    </PageSurface>
    <SettingsLeaveModal
      :open="leaveOpen"
      :count="draft.dirtyCount.value"
      :saving="saving"
      @stay="finishLeave(false)"
      @discard="discardAndLeave"
      @save="saveAndLeave"
    />
  </main>
</template>

<style scoped>
.plugin-settings-page {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
}

.plugin-settings-header :deep(.page-header-main) {
  display: grid;
  flex: 1 1 auto;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 0 8px;
  align-items: center;
}

.plugin-settings-header :deep(.app-page-title) {
  min-width: 0;
  grid-column: 2;
  grid-row: 1;
  overflow-wrap: anywhere;
}

.plugin-settings-lead {
  display: flex;
  align-items: center;
  grid-column: 1;
  grid-row: 1 / span 2;
  gap: 8px;
}

.plugin-settings-meta {
  grid-column: 2;
  grid-row: 2;
  min-width: 0;
  font-size: 12px;
  line-height: 20px;
  color: var(--ant-color-text-secondary);
  overflow-wrap: anywhere;
}
</style>
