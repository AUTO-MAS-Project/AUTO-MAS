import { computed, type Ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { Service } from '@/api'
import { i18n, translate as t } from '@/i18n'
import { queryClient } from '@/services/queryClient'
import type { ConfigSnapshot } from '@/services/configUiSync'
import { requestApi } from '@/utils/apiResult'
import { indexPluginScriptTypes } from '@/utils/pluginScriptTypes'

export const getPluginRegistry = (
  recordId: string | null = null,
  locale = i18n.global.locale.value
) =>
  requestApi(
    () => Service.getPluginRegistryApiPluginRegistryGetPost({ recordId }, locale),
    t('core.plugins.loadFailed')
  )

function registryQuery() {
  const locale = i18n.global.locale.value
  return {
    queryKey: ['plugins', 'registry', locale],
    queryFn: () => getPluginRegistry(null, locale),
    staleTime: Infinity,
    meta: { configSnapshot: true },
  }
}

export function usePluginRegistry(enabled?: Ref<boolean>) {
  return useQuery(computed(() => ({ ...registryQuery(), enabled: enabled?.value ?? true })))
}

export async function fetchPluginScriptTypes(read?: (snapshot: ConfigSnapshot) => void) {
  const registry = await queryClient.fetchQuery(registryQuery())
  read?.(registry)
  return indexPluginScriptTypes(registry.data)
}
