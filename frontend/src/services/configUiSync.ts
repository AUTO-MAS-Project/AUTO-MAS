import type { Query, QueryFunctionContext, QueryKey } from '@tanstack/vue-query'
import { useQuery } from '@tanstack/vue-query'
import { computed, onActivated, onDeactivated, ref, toValue, type MaybeRefOrGetter } from 'vue'
import { queryClient } from '@/services/queryClient'
import { connectionState, onConnected, onDisconnected } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import { WS_CONFIG_UI_CHANGED, WS_ID_CONFIG } from '@/services/websocket/types'

export interface ConfigSnapshot {
  uiSources?: readonly string[]
}

/** 复用现有页面回读逻辑，并把它读取的快照登记给 QueryClient。 */
export function useConfigLoader<T>(
  key: MaybeRefOrGetter<QueryKey>,
  load: (read: (snapshot: ConfigSnapshot) => void) => Promise<T>
) {
  const enabled = ref(false)
  const query = useConfigQuery({
    queryKey: key,
    enabled,
    queryFn: async ({ queryKey }) => {
      const sources = new Set<string>()
      const value = await load(snapshot => snapshot.uiSources?.forEach(uid => sources.add(uid)))
      const previous = queryClient.getQueryData<ConfigSnapshot>(queryKey)
      return { value, uiSources: sources.size ? [...sources] : (previous?.uiSources ?? []) }
    },
  })
  return async () => {
    enabled.value = true
    const result = await query.refetch({ cancelRefetch: false })
    if (result.error) throw result.error
    return result.data?.value
  }
}

export function useConfigQuery<T extends ConfigSnapshot>(options: {
  queryKey: MaybeRefOrGetter<QueryKey>
  queryFn: (context: QueryFunctionContext) => Promise<T>
  enabled?: MaybeRefOrGetter<boolean>
}) {
  const shown = ref(true)
  onActivated(() => (shown.value = true))
  onDeactivated(() => (shown.value = false))
  return useQuery({
    queryKey: computed(() => toValue(options.queryKey)),
    queryFn: options.queryFn,
    enabled: computed(() => shown.value && toValue(options.enabled ?? true)),
    meta: { configSnapshot: true },
  })
}

let stop: (() => void) | undefined

export function bootstrapConfigUiSync(): void {
  if (stop) return
  const cache = queryClient.getQueryCache()
  const changed = new Set<string>()
  const dirtyWhileFetching = new Set<Query>()
  const changesWhileFetching = new Map<Query, Set<string>>()
  let flushTimer: number | undefined
  let pollTimer: number | undefined

  function refresh(query: Query) {
    if (query.state.fetchStatus !== 'idle') {
      dirtyWhileFetching.add(query)
      return
    }
    void queryClient.invalidateQueries({
      predicate: candidate => candidate === query,
      refetchType: query.isActive() ? 'active' : 'none',
    })
  }

  function activeSnapshots() {
    return cache.findAll({
      type: 'active',
      predicate: query => query.meta?.configSnapshot === true,
    })
  }

  const subscription = subscribe({ id: WS_ID_CONFIG, type: WS_CONFIG_UI_CHANGED }, ({ data }) => {
    for (const uid of data.nodeUids) changed.add(uid)
    if (flushTimer !== undefined) return
    flushTimer = window.setTimeout(() => {
      flushTimer = undefined
      for (const query of cache.getAll()) {
        if (!query.meta?.configSnapshot) continue
        const snapshot = query.state.data as ConfigSnapshot | undefined
        if (snapshot?.uiSources?.some(uid => changed.has(uid))) {
          refresh(query)
        } else if (query.state.fetchStatus === 'fetching') {
          const sources = changesWhileFetching.get(query) ?? new Set<string>()
          changed.forEach(uid => sources.add(uid))
          changesWhileFetching.set(query, sources)
        }
      }
      changed.clear()
    }, 25)
  })

  const unsubscribeCache = cache.subscribe(({ type, query }) => {
    if (type === 'removed') {
      dirtyWhileFetching.delete(query)
      changesWhileFetching.delete(query)
    }
    if (type !== 'updated' || query.state.fetchStatus !== 'idle') return
    const received = changesWhileFetching.get(query)
    changesWhileFetching.delete(query)
    const snapshot = query.state.data as ConfigSnapshot | undefined
    if (dirtyWhileFetching.delete(query) || snapshot?.uiSources?.some(uid => received?.has(uid))) {
      queueMicrotask(() => refresh(query))
    }
  })

  function stopPolling() {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }

  function syncPolling() {
    stopPolling()
    const state = connectionState().value
    if (state === 'open' || state === 'superseded' || document.hidden) return
    pollTimer = window.setInterval(() => {
      for (const query of activeSnapshots()) {
        if (query.state.fetchStatus === 'idle') refresh(query)
      }
    }, 5000)
  }

  const offConnected = onConnected(() => {
    stopPolling()
    cache.findAll({ predicate: query => query.meta?.configSnapshot === true }).forEach(refresh)
  })
  const offDisconnected = onDisconnected(syncPolling)
  document.addEventListener('visibilitychange', syncPolling)
  syncPolling()
  stop = () => {
    unsubscribe(subscription)
    unsubscribeCache()
    offConnected()
    offDisconnected()
    document.removeEventListener('visibilitychange', syncPolling)
    window.clearTimeout(flushTimer)
    stopPolling()
  }
}

export function disposeConfigUiSync(): void {
  stop?.()
  stop = undefined
}
