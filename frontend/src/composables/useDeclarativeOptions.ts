import { computed, shallowReactive, watch, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { Service, type ComponentHint } from '@/api'
import { useApiQuery } from './useApiQuery'
import { requestApi } from '@/utils/apiResult'

type Option = { value: string; label: string }
type FieldOptions = {
  signature: string
  query: ReturnType<typeof useApiQuery<Option[]>>
}

/** 声明端点映射到生成客户端；依赖变化后使用新查询，旧响应不会覆盖新选项。 */
export function useDeclarativeOptions(target: ComputedRef<{
  uid: string
  ui: { hints?: Record<string, ComponentHint[]> }
  [key: string]: unknown
}>) {
  const { t } = useI18n()
  const queries = shallowReactive(new Map<string, FieldOptions>())
  const declarations = computed(() => Object.entries(target.value.ui.hints ?? {}).flatMap(([section, hints]) =>
    hints.filter(hint => hint.field && hint.endpoint).map(hint => ({
      key: `${section}.${hint.field}`,
      endpoint: hint.endpoint!,
      dependencies: (hint.deps ?? []).map(path => path.split('.').reduce<unknown>((value, part) =>
        value && typeof value === 'object' ? (value as Record<string, unknown>)[part] : undefined, target.value)),
    }))
  ))

  watch(declarations, fields => {
    const active = new Set(fields.map(field => field.key))
    for (const key of queries.keys()) if (!active.has(key)) queries.delete(key)
    for (const field of fields) {
      const signature = JSON.stringify([target.value.uid, field.endpoint, field.dependencies])
      if (queries.get(field.key)?.signature === signature) continue
      const query = useApiQuery(async () => {
        const fallback = t('scripts.optionsLoadFailed')
        let response
        switch (field.endpoint) {
          case '/api/info/combox/emulator':
            response = await requestApi(() => Service.getEmulatorComboxApiInfoComboxEmulatorPost(), fallback)
            break
          case '/api/info/combox/emulator/devices': {
            const gameId = field.dependencies[0]
            if (!gameId || gameId === '-') return []
            response = await requestApi(() => Service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost({ emulatorId: String(gameId) }), fallback)
            break
          }
          case '/api/info/combox/plan':
            response = await requestApi(() => Service.getPlanComboxApiInfoComboxPlanPost(), fallback)
            break
          default:
            throw new Error(t('scripts.unsupportedOptionsEndpoint', { endpoint: field.endpoint }))
        }
        return response.data.filter(item => item.value !== null && item.value !== '-').map(item => ({ value: item.value!, label: item.label }))
      }, () => t('scripts.optionsLoadFailed'))
      queries.set(field.key, { signature, query })
      void query.execute()
    }
  }, { immediate: true })

  const stateFor = (section: string, hint: ComponentHint) => queries.get(`${section}.${hint.field}`)?.query
  const optionsFor = (section: string, hint: ComponentHint): Option[] => hint.endpoint
    ? [{ value: '-', label: t('scripts.noAssociation') }, ...(stateFor(section, hint)?.data.value ?? [])]
    : (hint.options ?? []).map(option => ({ value: option.value, label: option.value }))

  return { stateFor, optionsFor }
}
