import { computed, onScopeDispose, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  buildEndfieldOverview,
  resolveEndfieldSourceData,
  restoreEndfieldSourceData,
  type AkedataManifest,
  type EndfieldSourceData,
} from './endfieldActivityTransform'
import { parseEndfieldSraData } from './endfieldSraTransform'
import { withEndfieldActivityImages } from './endfieldActivityImages'
import { createEmptyEndfieldActivityOverview, type EndfieldActivityOverview } from '@/types/home'
import { useHomeActivitySource } from './useHomeActivitySource'

const AKEDATA_BASE_URL = 'https://data.akedata.wiki'
const AKEDATA_MANIFEST_URL = AKEDATA_BASE_URL + '/manifest.json'
const SNAPSHOT_KEY = 'auto-mas.home.endfield-snapshot'
const SRA_ACTIVITY_URL = 'https://starrailassistant.top/api/v1/activity/end.json'

/** SRA 版本/活动与 AKEData 卡池独立加载，慢表不会挡住主卡片。 */
export const useEndfieldActivitySource = () => {
  const { t } = useI18n()
  const akeOverview = ref<EndfieldActivityOverview>(createEmptyEndfieldActivityOverview())
  const sraOverview = ref<EndfieldActivityOverview>(createEmptyEndfieldActivityOverview())
  const now = ref(Date.now())
  let sourceData: EndfieldSourceData | null = null
  let generation = 0
  let started = false
  let active = false
  let clock: number | null = null
  let refreshedAt = Date.now()
  const controllers = new Set<AbortController>()

  // 公共骨架负责超时/退避；本模块负责隐藏或卸载时中止所有正在下载的表。
  const fetchJson = async (url: string, signal: AbortSignal): Promise<unknown> => {
    const controller = new AbortController()
    const abort = () => controller.abort()
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort()
    controllers.add(controller)
    try {
      const response = await fetch(url, {
        signal: controller.signal,
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
    label: () => 'AKEData',
    timeoutMs: 60_000,
    requestTag: () => generation,
    isObsolete: tag => tag !== generation,
    restoreSnapshot: () => {
      try {
        const raw = localStorage.getItem(SNAPSHOT_KEY)
        const restored = raw ? restoreEndfieldSourceData(JSON.parse(raw)) : null
        if (!restored) return false
        sourceData = restored
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
        `${AKEDATA_MANIFEST_URL}?t=${Date.now()}`,
        signal
      )) as AkedataManifest
      const latest = manifest.latest
      const version = (manifest.versions ?? []).find(item => item.id === latest)
      if (!version) {
        throw new Error('manifest 未包含最新版本')
      }

      if (
        sourceData !== null &&
        sourceData.versionId === latest &&
        sourceData.sourceUpdatedAt === (manifest.updatedAt ?? '')
      ) {
        return sourceData
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
      sourceData = data
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

  const sra = useHomeActivitySource<EndfieldActivityOverview>({
    label: () => 'SRA',
    timeoutMs: 20_000,
    requestTag: () => generation,
    isObsolete: tag => tag !== generation,
    fetchData: async signal => parseEndfieldSraData(await fetchJson(SRA_ACTIVITY_URL, signal)),
    applyData: data => {
      sraOverview.value = data
    },
    markStale: () => {
      sraOverview.value = {
        ...sraOverview.value,
        Stale: true,
        Message: t('home.sra.staleMessage'),
      }
    },
    markUnavailable: () => {
      sraOverview.value = {
        ...createEmptyEndfieldActivityOverview(),
        Message: t('home.endfield.unavailable'),
      }
    },
  })

  const overview = computed<EndfieldActivityOverview>(() => {
    const sraData = sraOverview.value
    const sraHasContent =
      new Date(sraData.VersionEndTime ?? '').getTime() > now.value ||
      sraData.Activities.some(item => new Date(item.EndTime).getTime() > now.value)
    const primary =
      sraData.Available && (!sraData.Stale || sraHasContent) ? sraData : akeOverview.value
    const isPending = (item: { EndTime: string }) => new Date(item.EndTime).getTime() > now.value
    const versionEnd = new Date(primary.VersionEndTime ?? '').getTime()
    const versionValid = versionEnd > now.value
    return {
      ...primary,
      // 不把过期版本宣传图当作当期版本，也不拿 AKE 卡池时间拼版本倒计时。
      Version: versionValid ? primary.Version : '',
      VersionName: versionValid ? primary.VersionName : '',
      VersionCover: versionValid ? primary.VersionCover : '',
      VersionStartTime: versionValid ? primary.VersionStartTime : '',
      VersionEndTime: versionValid ? primary.VersionEndTime : '',
      VersionStale: sraOverview.value.Stale,
      Activities: (primary === sraData
        ? withEndfieldActivityImages(primary.Activities, sourceData?.activities ?? [])
        : primary.Activities
      ).filter(isPending),
      Pools: akeOverview.value.Pools.filter(isPending),
      PoolStale: akeOverview.value.Stale,
      PoolMessage: akeOverview.value.Message,
      PoolLoading: ake.loading.value,
      Message: primary.Available
        ? primary === akeOverview.value && primary.Stale
          ? t('home.endfield.staleMessage')
          : primary.Message
        : sraOverview.value.Message,
    }
  })

  const refresh = async () => {
    invalidate()
    now.value = Date.now()
    refreshedAt = now.value
    sra.loading.value = true
    ake.loading.value = true
    await Promise.all([sra.refresh(), ake.refresh()])
  }
  const stop = () => {
    active = false
    invalidate()
    sra.stop()
    ake.stop()
    if (clock !== null) window.clearInterval(clock)
    clock = null
  }
  const onVisibilityChange = () => {
    if (active && document.visibilityState === 'visible') refresh()
  }
  document.addEventListener('visibilitychange', onVisibilityChange)
  onScopeDispose(() => {
    stop()
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return {
    overview,
    // 卡池加载不会挡住已可用的版本和活动。
    loading: computed(() => !overview.value.Available && sra.loading.value),
    versionArt: computed(() => overview.value.VersionCover ?? ''),
    versionName: computed(() => overview.value.VersionName ?? ''),
    start: () => {
      if (active) return
      active = true
      now.value = Date.now()
      if (clock === null) {
        clock = window.setInterval(() => {
          now.value = Date.now()
          if (document.visibilityState === 'visible' && now.value - refreshedAt >= 15 * 60_000) {
            refresh()
          }
        }, 60_000)
      }
      sra.start()
      ake.start()
      if (started) refresh()
      started = true
    },
    stop,
    refresh,
  }
}
