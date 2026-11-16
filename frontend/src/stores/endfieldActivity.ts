import { defineStore } from 'pinia'
import { onScopeDispose, ref } from 'vue'
import { translate as t } from '@/i18n'
import { createEmptyEndfieldActivityOverview, type EndfieldActivityOverview } from '@/types/home'
import {
  buildEndfieldOverview,
  resolveEndfieldSourceData,
  restoreEndfieldSourceData,
  type AkedataManifest,
  type EndfieldSourceData,
} from '@/views/home/endfieldActivityTransform'
import { useHomeActivitySource } from '@/views/home/useHomeActivitySource'

const AKEDATA_BASE_URL = 'https://data.akedata.wiki'
const AKEDATA_MANIFEST_URL = AKEDATA_BASE_URL + '/manifest.json'
const CHECK_INTERVAL_MS = 24 * 60 * 60_000
const SNAPSHOT_KEY = 'auto-mas.home.endfield-snapshot'

/** 会话内保留启动检查与退避状态，首页重新挂载不重复检查。 */
export const useEndfieldActivityStore = defineStore('endfield-activity', () => {
  const akeOverview = ref<EndfieldActivityOverview>(createEmptyEndfieldActivityOverview())
  const sourceData = ref<EndfieldSourceData | null>(null)
  let generation = 0
  let controller: AbortController | null = null
  let active = false
  let nextCheckAt = Number.POSITIVE_INFINITY

  // 一次检查共用取消信号，覆盖 manifest 与表下载之间的空档。
  const fetchJson = async (
    url: string,
    signal: AbortSignal,
    cache?: RequestCache
  ): Promise<unknown> => {
    signal.throwIfAborted()
    const response = await fetch(url, {
      signal,
      cache,
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) throw new Error('HTTP ' + response.status)
    return await response.json()
  }
  const stripSlashes = (value: string) => value.replace(/^\/+|\/+$/g, '')
  const invalidate = () => {
    generation += 1
    controller?.abort()
    controller = null
  }

  const ake = useHomeActivitySource<EndfieldSourceData>({
    isAvailable: () => akeOverview.value.Available,
    label: () => 'AKEData',
    timeoutMs: 60_000,
    loadingOnStart: true,
    requestTag: () => generation,
    isObsolete: tag => tag !== generation,
    restoreSnapshot: () => {
      try {
        const raw = localStorage.getItem(SNAPSHOT_KEY)
        const restored = raw ? restoreEndfieldSourceData(JSON.parse(raw)) : null
        if (!restored) return false
        sourceData.value = restored
        akeOverview.value = {
          ...buildEndfieldOverview(restored, new Date()),
          Stale: true,
          Message: t('core.home.endfield.poolStaleMessage'),
        } as EndfieldActivityOverview
        return true
      } catch {
        return false
      }
    },
    saveSnapshot: data => {
      try {
        localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(data))
      } catch {
        // 沿用既有 AKE 快照；存储不可用不影响当次数据。
      }
    },
    fetchData: async timeoutSignal => {
      const current = new AbortController()
      controller = current
      const signal = AbortSignal.any([timeoutSignal, current.signal])
      ake.loading.value = true
      // 失败由有限退避接管，耗尽后也不在每分钟时钟上连续重开检查。
      nextCheckAt = Date.now() + CHECK_INTERVAL_MS
      try {
        const manifest = (await fetchJson(
          AKEDATA_MANIFEST_URL,
          signal,
          'no-cache'
        )) as AkedataManifest
        signal.throwIfAborted()
        const latest = manifest.latest
        const version = (manifest.versions ?? []).find(item => item.id === latest)
        if (!version) {
          throw new Error('manifest 未包含最新版本')
        }

        if (
          sourceData.value !== null &&
          sourceData.value.versionId === latest &&
          sourceData.value.sourceUpdatedAt === (manifest.updatedAt ?? '')
        ) {
          return sourceData.value
        }

        const tableRoot = AKEDATA_BASE_URL + '/' + stripSlashes(version.tableCfgPath)
        const [activities, timeRanges, activityTags, textTable, pools, characters] =
          (await Promise.all([
            fetchJson(tableRoot + '/ActivityTable.json', signal),
            fetchJson(tableRoot + '/TimeRangeTable.json', signal),
            fetchJson(tableRoot + '/ActivityTagTable.json', signal),
            fetchJson(tableRoot + '/I18nTextTable_CN.json', signal),
            fetchJson(tableRoot + '/GachaCharPoolTable.json', signal),
            fetchJson(tableRoot + '/CharacterTable.json', signal),
          ])) as unknown as [unknown, unknown, unknown, unknown, unknown, unknown]
        const resolved = resolveEndfieldSourceData({
          activities,
          timeRanges,
          activityTags,
          textTable,
          pools,
          characters,
        })
        return {
          versionId: latest,
          sourceUpdatedAt: manifest.updatedAt ?? '',
          ...resolved,
        }
      } finally {
        current.abort()
        if (controller === current) controller = null
      }
    },
    applyData: data => {
      sourceData.value = data
      nextCheckAt = Date.now() + CHECK_INTERVAL_MS
      akeOverview.value = buildEndfieldOverview(data, new Date()) as EndfieldActivityOverview
    },
    markStale: () => {
      akeOverview.value = {
        ...akeOverview.value,
        Stale: true,
        Message: t('core.home.endfield.poolStaleMessage'),
      }
    },
    markUnavailable: () => {
      akeOverview.value = {
        ...createEmptyEndfieldActivityOverview(),
        Message: t('core.home.endfield.poolUnavailable'),
      }
    },
  })

  onScopeDispose(invalidate)

  return {
    overview: akeOverview,
    sourceData,
    loading: ake.loading,
    whenLoaded: ake.whenLoaded,
    start: () => {
      active = true
      ake.start()
    },
    stop: () => {
      active = false
      const interrupted = controller !== null || ake.loading.value
      invalidate()
      ake.stop()
      // 取消的检查尚未完成；再次启用时续接，不把它当作成功检查。
      if (interrupted) ake.resume()
      ake.loading.value = false
    },
    updateTime: (now: number) => {
      if (sourceData.value) {
        const { Stale, Message } = akeOverview.value
        akeOverview.value = {
          ...buildEndfieldOverview(sourceData.value, new Date(now)),
          Stale,
          Message,
        } as EndfieldActivityOverview
      }
      if (
        active &&
        document.visibilityState === 'visible' &&
        now >= nextCheckAt &&
        !ake.loading.value &&
        controller === null
      ) {
        void ake.refresh()
      }
    },
    refresh: () => {
      invalidate()
      ake.loading.value = true
      return ake.refresh()
    },
  }
})
