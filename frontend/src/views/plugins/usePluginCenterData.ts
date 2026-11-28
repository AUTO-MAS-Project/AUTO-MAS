import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import appIcon from '@/assets/AUTO-MAS.ico'
import { usePluginApi } from '@/composables/usePluginApi'
import { compatibleWheel, indexPluginScriptTypes } from '@/utils/pluginScriptTypes'
import { usePluginRegistry } from '@/composables/usePluginScriptTypes'
import { getApiErrorMessage } from '@/utils/apiError'
import { useScriptApi } from '@/composables/useScriptApi'
import { usePlanApi } from '@/composables/usePlanApi'
import { SCRIPT_PLUGIN_BINDINGS } from '@/plugins/scriptAdapters'
import { useScriptList } from '@/views/scripts/useScriptList'
import { pluginCatalogQueryKey, usePluginQuery } from './usePluginQuery'
import {
  pluginSettingsGroups,
  pluginUsage,
  toInstalledViews,
  toMarketViews,
  updatableEntries,
  usageSourceState,
  type InstalledPluginView,
  type PluginModelContext,
  type PluginTextSource,
  type PluginUsage,
  type PluginUsageSource,
  type SettingsVisibility,
  type UsageScript,
} from './pluginCenterModel'

/**
 * 插件词条的展示文本；词条缺失或标签格式无效时返回 undefined，由模型回落。
 * 插件中心外壳之外（如设置页页头）整理单个插件时，与 SCRIPT_PLUGIN_BINDINGS、应用图标一起组成模型上下文。
 */
function usePluginTexts(): PluginTextSource {
  const { t, te } = useI18n()
  return {
    text: (pluginId, field) => {
      const key = `plugins.${pluginId}.${field}`
      return te(key) ? t(key) : undefined
    },
    tags: pluginId => {
      const key = `plugins.${pluginId}.tags`
      if (!te(key)) return undefined
      try {
        const value: unknown = JSON.parse(t(key))
        return Array.isArray(value)
          ? value.filter((item): item is string => typeof item === 'string')
          : undefined
      } catch {
        return undefined
      }
    },
  }
}

/** 模型上下文：专项入口绑定、应用图标与插件词条；跟随语言重新计算。 */
export function usePluginModelContext(texts: PluginTextSource = usePluginTexts()) {
  const { locale } = useI18n()
  return computed<PluginModelContext>(() => {
    void locale.value
    return { bindings: SCRIPT_PLUGIN_BINDINGS, appIcon, texts }
  })
}

/**
 * 插件中心三个页签共用的取数：注册表、市场目录、托管与计划表用量、每个插件有没有可见设置。
 * 由外壳调用一次，经 usePluginCenter() 分发；切换语言后整体重取。
 */
export function usePluginCenterData() {
  const { t, locale } = useI18n()
  const api = usePluginApi()
  const queryClient = useQueryClient()
  const texts = usePluginTexts()
  const { getScripts, error: scriptListError } = useScriptApi()
  const { getScriptUsers } = useScriptList()
  const { getPlans } = usePlanApi()

  const registry = usePluginRegistry()
  const catalog = usePluginQuery(
    () => pluginCatalogQueryKey(locale.value),
    () => api.getCatalog(),
    () => t('core.plugins.marketLoadFailed')
  )

  const loadUsage = async () => {
    // 只统计能对上托管类型的专项；账号与计划表读不到时置空，不影响托管数。
    const scripts = await getScripts(false, { showError: false })
    if (scriptListError.value) throw new Error(scriptListError.value)
    const types = new Set(SCRIPT_PLUGIN_BINDINGS.map(binding => binding.scriptType))
    const related = scripts.filter(script => types.has(script.type))
    const users = await Promise.all(related.map(script => getScriptUsers(script.uid)))
    const planTypes = SCRIPT_PLUGIN_BINDINGS.flatMap(binding => binding.planConfigType ?? [])
    let planCounts: Record<string, number> | null = {}
    if (planTypes.length) {
      try {
        const response = await getPlans(undefined, { silent: true })
        planCounts =
          response.code === 200
            ? Object.fromEntries(
                planTypes.map(type => [
                  type,
                  response.index.filter(item => item.type === type).length,
                ])
              )
            : null
      } catch {
        planCounts = null
      }
    }
    return {
      uiSources: [],
      scripts: related.map((script, index): UsageScript => ({
        uid: script.uid,
        name: script.name,
        scriptType: script.type,
        accounts: users[index].error ? null : users[index].users.length,
      })),
      planCounts,
    }
  }
  const usage = usePluginQuery(
    () => ['plugins', 'usage', locale.value],
    loadUsage,
    () => t('core.plugins.usageLoadFailed')
  )

  const context = usePluginModelContext(texts)
  const market = computed(() =>
    toMarketViews(catalog.data.value, registry.data.value, context.value)
  )
  const installed = computed(() =>
    toInstalledViews(registry.data.value, market.value, context.value)
  )
  const updates = computed(() => updatableEntries(market.value, installed.value))

  // 本实例、当前语言下是否已成功取到过用量；离页再回来时缓存里的旧托管列表不算数。
  const usageCurrent = ref(false)
  let usageGeneration = 0
  const reloadUsage = async () => {
    const generation = usageGeneration
    const result = await usage.execute()
    if (result !== null && generation === usageGeneration) usageCurrent.value = true
    return result
  }

  const usageSource = computed<PluginUsageSource>(() => ({
    state: usageSourceState({ failed: !!usage.error.value, current: usageCurrent.value }),
    scripts: usage.data.value?.scripts ?? [],
    planCounts: usage.data.value?.planCounts ?? null,
  }))
  const usageOf = (view: InstalledPluginView): PluginUsage => pluginUsage(view, usageSource.value)

  const enabledUids = computed(() =>
    installed.value.flatMap(view => (view.enabled ? view.uid : []))
  )
  const settingsPanels = computed(
    () => indexPluginScriptTypes(registry.data.value?.data).settingsPanels
  )
  const settings = useQuery({
    // 键不含 uid 列表：注册表刷新后紧接着重取，调用时读当下已启用的插件。
    queryKey: computed(() => ['plugins', 'settingsVisibility', locale.value]),
    enabled: false,
    queryFn: async () =>
      Object.fromEntries(
        await Promise.all(
          enabledUids.value.map(async uid => {
            if (compatibleWheel(settingsPanels.value.get(uid))) return [uid, 'visible'] as const
            try {
              const result = await api.getConfig(uid)
              return [uid, pluginSettingsGroups(result.data).length ? 'visible' : 'hidden'] as const
            } catch {
              return [uid, 'unknown'] as const
            }
          })
        )
      ) as Record<string, SettingsVisibility>,
  })
  /** 未启用的插件没有可读的自有配置，不给设置入口。 */
  const settingsVisibility = (view: InstalledPluginView): SettingsVisibility =>
    view.enabled ? (settings.data.value?.[view.uid] ?? 'loading') : 'hidden'

  const reloadDetails = () =>
    // 用量与设置入口跟随注册表刷新，失败只影响对应展示，不阻断列表。
    Promise.all([reloadUsage(), settings.refetch()])
  const reload = async () => {
    const [registryResult, catalogResult] = await Promise.all([
      registry.refetch({ cancelRefetch: false }),
      catalog.execute(),
    ])
    await reloadDetails()
    return !registryResult.isError && catalogResult !== null
  }

  const catalogRefreshing = ref(false)
  /** 从发行源刷新目录后回读；返回 false 表示回读失败（错误留在查询状态里）。 */
  const refreshCatalog = async () => {
    catalogRefreshing.value = true
    try {
      await api.refreshCatalog()
      return await reload()
    } finally {
      catalogRefreshing.value = false
    }
  }
  /** 进入市场页签时的自动刷新：可跨导航完成，始终回读并更新共享目录缓存；失败静默。 */
  const autoRefreshCatalog = async () => {
    try {
      await api.refreshCatalog('automatic')
      const queryKey = pluginCatalogQueryKey(locale.value)
      await queryClient.cancelQueries({ queryKey, exact: true })
      await queryClient.fetchQuery({
        queryKey,
        queryFn: async () => {
          const value = await api.getCatalog(queryKey[2])
          return { value, uiSources: value.uiSources }
        },
        staleTime: 0,
      })
    } catch {
      return
    }
  }

  watch(
    locale,
    () => {
      usageGeneration += 1
      usageCurrent.value = false
      return reload()
    },
    { immediate: true }
  )

  return {
    installed,
    market,
    updates,
    usageSource,
    usageOf,
    settingsVisibility,
    registry: {
      loading: registry.isFetching,
      error: computed(
        () =>
          registry.error.value &&
          getApiErrorMessage(registry.error.value, t('core.plugins.loadFailed'))
      ),
      loaded: computed(() => registry.data.value !== undefined),
    },
    catalog: {
      loading: catalog.loading,
      error: catalog.error,
      loaded: computed(() => catalog.data.value !== undefined),
    },
    usage: { loading: usage.loading, error: usage.error },
    catalogRefreshing,
    reload,
    reloadUsage,
    refreshCatalog,
    autoRefreshCatalog,
  }
}

export type PluginCenterData = ReturnType<typeof usePluginCenterData>
