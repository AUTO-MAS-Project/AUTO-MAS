import { computed, type ComputedRef } from 'vue'
import { useQueries } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import {
  OpenAPI,
  PlanComboxIn,
  Service,
  type ComboBoxItem,
  type ComponentHint,
  type OptionHint,
  type OutBase,
} from '@/api'
import { request } from '@/api/core/request'
import { apiErrorMessage, requestApi } from '@/utils/apiResult'

export type DeclarativeOption = OptionHint
export type DeclarativeHint = ComponentHint

interface OptionsTarget {
  uid: string
  pluginName?: string | null
  ui: { hints?: Record<string, DeclarativeHint[]> }
  [key: string]: unknown
}

function dependency(target: OptionsTarget, path: string) {
  const [group, field] = path.split('.')
  const hint = target.ui.hints?.[group]?.find(item => item.field === field)
  if (!hint || hint.secret || hint.masked) return undefined
  return (target[group] as Record<string, unknown> | undefined)?.[field]
}
const missing = (value: unknown) => value == null || value === ''

/** 查询按配置、来源和草稿依赖隔离，旧请求只能更新自己的缓存。 */
export function useDeclarativeOptions(target: ComputedRef<OptionsTarget>) {
  const { t, locale } = useI18n()
  function hostOptions(hint: DeclarativeHint, gameId: unknown) {
    switch (hint.endpoint) {
      case '/api/plugin/options/games':
        return Service.pluginGameOptionsApiPluginOptionsGamesPost()
      case '/api/plugin/options/devices':
        return Service.pluginDeviceOptionsApiPluginOptionsDevicesPost({ gameId: String(gameId) })
      case '/api/plugin/options/plans':
        return Service.pluginPlanOptionsApiPluginOptionsPlansPost(
          undefined,
          hint.plan_type ? { type: hint.plan_type } : undefined
        )
      case '/api/info/combox/plan':
        return Service.getPlanComboxApiInfoComboxPlanPost({
          consumer: PlanComboxIn.consumer.UNIVERSAL,
        })
      default:
        throw new Error(t('core.scripts.unsupportedOptionsEndpoint', { endpoint: hint.endpoint }))
    }
  }

  function declaration(group: string, hint: DeclarativeHint) {
    const { uid, pluginName } = target.value
    const source = hint.option_source
    const params = Object.fromEntries(
      Object.entries(hint.depends_on ?? {}).map(([name, path]) => [
        name,
        dependency(target.value, path),
      ])
    )
    const deps = (hint.deps ?? []).map(path => dependency(target.value, path))
    const language = locale.value
    const ready = source
      ? !!pluginName && !Object.values(params).some(missing)
      : !deps.some(missing) &&
        (hint.endpoint !== '/api/plugin/options/devices' || (!missing(deps[0]) && deps[0] !== '-'))
    const queryKey = [
      'plugins',
      'field-options',
      uid,
      ...(source
        ? [pluginName, source, params, language]
        : [hint.endpoint, deps, ...(hint.plan_type ? [hint.plan_type] : [])]),
    ]
    async function load(): Promise<Required<DeclarativeOption>[]> {
      // 插件网关不在 OpenAPI 中，沿用生成客户端的地址、鉴权和查询参数编码。
      const response = await requestApi<OutBase & { data?: Array<OptionHint | ComboBoxItem> }>(
        () =>
          source
            ? request(OpenAPI, {
                method: 'GET',
                url: `/api/plugin/${encodeURIComponent(pluginName!)}/options/${encodeURIComponent(source)}`,
                query: { ...params, locale: language },
              })
            : hostOptions(hint, deps[0]),
        t('core.scripts.optionsLoadFailed')
      )
      return (response.data ?? []).flatMap(({ value, label }) =>
        value == null || (!source && value === '-')
          ? []
          : [{ value, label: label ?? String(value) }]
      )
    }
    return { group, hint, key: `${group}.${hint.field}`, queryKey, ready, load }
  }
  const declarations = computed(() =>
    Object.entries(target.value.ui.hints ?? {}).flatMap(([group, hints]) =>
      hints
        .filter(hint => hint.field && (hint.option_source || hint.endpoint))
        .map(hint => declaration(group, hint))
    )
  )
  const queries = useQueries({
    queries: computed(() =>
      declarations.value.map(({ ready, queryKey, load }) => ({
        queryKey,
        queryFn: load,
        ...(!ready && { enabled: false }),
      }))
    ),
  })
  function queryFor(group: string, hint: DeclarativeHint) {
    const index = declarations.value.findIndex(field => field.key === `${group}.${hint.field}`)
    return declarations.value[index]?.ready ? queries.value[index] : undefined
  }
  function stateFor(group: string, hint: DeclarativeHint) {
    const query = queryFor(group, hint)
    return (
      query && {
        error: {
          value: query.error
            ? apiErrorMessage(query.error, t('core.scripts.optionsLoadFailed'))
            : null,
        },
        loading: { value: query.isFetching },
        execute: () => query.refetch(),
      }
    )
  }
  function optionsFor(group: string, hint: DeclarativeHint): Required<DeclarativeOption>[] {
    if (hint.option_source) return queryFor(group, hint)?.data ?? []
    if (hint.endpoint)
      return [
        { value: '-', label: t('core.scripts.noAssociation') },
        ...(queryFor(group, hint)?.data ?? []),
      ]
    return (hint.options ?? []).map(item => ({
      value: item.value,
      label: item.label ?? String(item.value),
    }))
  }
  const validation = computed(() => {
    const errors: Record<string, string> = {}
    let pending = false
    declarations.value.forEach(({ group, hint, key, ready }, index) => {
      if (!ready || hint.editable === false) return
      const value = (target.value[group] as Record<string, unknown> | undefined)?.[hint.field!]
      const selected = (Array.isArray(value) ? value : [value]).filter(item => !missing(item))
      if (!selected.length) return
      const query = queries.value[index]
      if (!query?.data) {
        // 上游选择已变，需等新列表确认旧值仍可用；请求失败时保留选择供重试。
        pending ||= !!hint.option_source && !!Object.keys(hint.depends_on ?? {}).length
        return
      }
      const options = optionsFor(group, hint)
      if (selected.some(item => !options.some(option => option.value === item))) {
        errors[key] = t('core.plugins.optionUnavailable')
      }
    })
    return { errors, invalid: pending || Object.keys(errors).length > 0 }
  })
  return {
    stateFor,
    optionsFor,
    validationErrors: computed(() => validation.value.errors),
    optionsInvalid: computed(() => validation.value.invalid),
  }
}
