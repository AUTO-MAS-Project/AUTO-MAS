import { defineStore } from 'pinia'
import { ref } from 'vue'
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
const SNAPSHOT_KEY = 'auto-mas.home.endfield-snapshot'

/** 会话内保留启动检查与退避状态，首页重新挂载不重复检查。 */
export const useEndfieldActivityStore = defineStore('endfield-activity', () => {
  const akeOverview = ref<EndfieldActivityOverview>(createEmptyEndfieldActivityOverview())
  const sourceData = ref<EndfieldSourceData | null>(null)
  let generation = 0
  const controllers = new Set<AbortController>()

  // 公共骨架负责超时/退避；本模块负责隐藏或卸载时中止所有正在下载的表。
  const fetchJson = async (
    url: string,
    signal: AbortSignal,
    cache?: RequestCache
  ): Promise<unknown> => {
    const controller = new AbortController()
    const abort = () => controller.abort()
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort()
    controllers.add(controller)
    try {
      const response = await fetch(url, {
        signal: controller.signal,
        cache,
        headers: { Accept: 'application/json' },
      })
      if (!response.ok) throw new Error('HTTP ' + response.status)
      return await response.json()
    } finally {
      signal.removeEventListener('abort', abort)
      controllers.delete(controller)
    }
  }
  const stripSlashes = (value: string) => value.replace(/^\/+|\/+$/g, '')
  const invalidate = () => {
    generation += 1
    controllers.forEach(controller => controller.abort())
    controllers.clear()
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
          Message: t('home.endfield.poolStaleMessage'),
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
    fetchData: async signal => {
      const manifest = (await fetchJson(
        AKEDATA_MANIFEST_URL,
        signal,
        'no-cache'
      )) as AkedataManifest
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
    },
    applyData: data => {
      sourceData.value = data
      akeOverview.value = buildEndfieldOverview(data, new Date()) as EndfieldActivityOverview
    },
    markStale: () => {
      akeOverview.value = {
        ...akeOverview.value,
        Stale: true,
        Message: t('home.endfield.poolStaleMessage'),
      }
    },
    markUnavailable: () => {
      akeOverview.value = {
        ...createEmptyEndfieldActivityOverview(),
        Message: t('home.endfield.poolUnavailable'),
      }
    },
  })

  return {
    overview: akeOverview,
    sourceData,
    loading: ake.loading,
    whenLoaded: ake.whenLoaded,
    start: ake.start,
    stop: () => {
      const interrupted = controllers.size > 0
      invalidate()
      ake.stop()
      // 取消的检查尚未完成；再次启用时续接，不把它当作成功检查。
      if (interrupted) ake.resume()
      ake.loading.value = false
    },
    refresh: () => {
      invalidate()
      ake.loading.value = true
      return ake.refresh()
    },
  }
})
