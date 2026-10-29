import { computed, onScopeDispose, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useEndfieldActivityStore } from '@/stores/endfieldActivity'
import { useI18n } from 'vue-i18n'
import { parseEndfieldSraData } from './endfieldSraTransform'
import { withEndfieldActivityImages } from './endfieldActivityImages'
import { createEmptyEndfieldActivityOverview, type EndfieldActivityOverview } from '@/types/home'
import { combineActivityLoads, useHomeActivitySource } from './useHomeActivitySource'

const SRA_SNAPSHOT_KEY = 'auto-mas.home.endfield-sra-snapshot'
const SRA_ACTIVITY_URL = 'https://starrailassistant.top/api/v1/activity/end.json'

/** SRA 版本/活动与 AKEData 卡池独立加载，慢表不会挡住主卡片。 */
export const useEndfieldActivitySource = () => {
  const { t } = useI18n()
  const ake = useEndfieldActivityStore()
  const { overview: akeOverview, sourceData } = storeToRefs(ake)
  const sraOverview = ref<EndfieldActivityOverview>(createEmptyEndfieldActivityOverview())
  const now = ref(Date.now())
  let generation = 0
  let started = false
  let active = false
  let clock: number | null = null
  let refreshedAt = Date.now()
  const controllers = new Set<AbortController>()

  // SRA 与 AKE 分别取消请求，自动刷新 SRA 不打断 AKE 下载。
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
  const invalidate = () => {
    generation += 1
    controllers.forEach(controller => controller.abort())
    controllers.clear()
  }

  const sra = useHomeActivitySource<unknown>({
    isAvailable: () => sraOverview.value.Available,
    label: () => 'SRA',
    timeoutMs: 20_000,
    requestTag: () => generation,
    isObsolete: tag => tag !== generation,
    restoreSnapshot: () => {
      try {
        const raw = localStorage.getItem(SRA_SNAPSHOT_KEY)
        if (!raw) return false
        sraOverview.value = {
          ...parseEndfieldSraData(JSON.parse(raw)),
          Stale: true,
          Message: t('core.home.sra.staleMessage'),
        }
        return true
      } catch {
        return false
      }
    },
    saveSnapshot: data => {
      try {
        localStorage.setItem(SRA_SNAPSHOT_KEY, JSON.stringify(data))
      } catch {
        // 仅缓存已通过解析的数据，存储不可用不影响当前展示。
      }
    },
    fetchData: signal => fetchJson(SRA_ACTIVITY_URL, signal),
    applyData: data => {
      sraOverview.value = parseEndfieldSraData(data)
    },
    markStale: () => {
      sraOverview.value = {
        ...sraOverview.value,
        Stale: true,
        Message: t('core.home.sra.staleMessage'),
      }
    },
    markUnavailable: () => {
      sraOverview.value = {
        ...createEmptyEndfieldActivityOverview(),
        Message: t('core.home.endfield.unavailable'),
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
        ? withEndfieldActivityImages(primary.Activities, sourceData.value?.activities ?? [])
        : primary.Activities
      ).filter(isPending),
      Pools: akeOverview.value.Pools.filter(isPending),
      PoolStale: akeOverview.value.Stale,
      PoolMessage: akeOverview.value.Message,
      PoolLoading: ake.loading,
      Message: primary.Available
        ? primary === akeOverview.value && primary.Stale
          ? t('core.home.endfield.staleMessage')
          : primary.Message
        : sraOverview.value.Message,
    }
  })

  const refreshSra = async () => {
    invalidate()
    now.value = Date.now()
    refreshedAt = now.value
    sra.loading.value = true
    await sra.refresh()
  }
  const refresh = async () => {
    await Promise.all([refreshSra(), ake.refresh()])
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
    if (active && document.visibilityState === 'visible') {
      ake.updateTime(Date.now())
      void refreshSra()
    }
  }
  document.addEventListener('visibilitychange', onVisibilityChange)
  onScopeDispose(() => {
    stop()
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return {
    whenLoaded: combineActivityLoads([sra, ake]),
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
          ake.updateTime(now.value)
          if (document.visibilityState === 'visible' && now.value - refreshedAt >= 15 * 60_000) {
            void refreshSra()
          }
        }, 60_000)
      }
      sra.start()
      ake.start()
      ake.updateTime(now.value)
      if (started) void refreshSra()
      started = true
    },
    stop,
    refresh,
  }
}
