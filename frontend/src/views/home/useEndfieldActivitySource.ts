import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { GetService, OpenAPI } from '@/api'
import {
  buildEndfieldOverview,
  resolveEndfieldSourceData,
  restoreEndfieldSourceData,
  type AkedataManifest,
  type EndfieldSourceData,
} from './endfieldActivityTransform'
import { createEmptyEndfieldActivityOverview, type EndfieldActivityOverview } from '@/types/home'
import { useHomeActivitySource } from './useHomeActivitySource'

const logger = window.electronAPI.getLogger('活动数据')

const AKEDATA_BASE_URL = 'https://data.akedata.wiki'
const AKEDATA_MANIFEST_URL = AKEDATA_BASE_URL + '/manifest.json'
/** 六张表并行下载（gzip 合计约 5.75MB），仅版本更新时触发，慢网放宽至 60s */
const FETCH_TIMEOUT_MS = 60_000
const SNAPSHOT_KEY = 'auto-mas.home.endfield-snapshot'
/** AKEData 那几张表下不动时的兜底源：SRA 托管的终末地活动列表（没有卡池与分类） */
const SRA_ACTIVITY_URL = 'https://starrailassistant.top/api/v1/activity/end.json'
const SRA_SOURCE_URL = 'https://starrailassistant.top'

interface SraActivityPayload {
  activities?: { name?: string; startTime?: string; endTime?: string; cover?: string }[]
}

/** 活动条目的形状（types/home.ts 里没有导出，从概览类型上取） */
type EndfieldActivityItem = EndfieldActivityOverview['Activities'][number]

const loadSnapshot = (): EndfieldSourceData | null => {
  try {
    const raw = localStorage.getItem(SNAPSHOT_KEY)
    if (!raw) {
      return null
    }
    return restoreEndfieldSourceData(JSON.parse(raw))
  } catch {
    return null
  }
}

/**
 * 终末地活动卡的直连数据源（首页全前端化收官）。
 * 与后端 EndfieldActivityService 职责对齐：manifest（1.8KB）检查版本，
 * 版本变化才并行下载数据表并构建活动/卡池，解析结果存入本地快照；
 * 取数超时、失败退避重试与失败态交给公共骨架——本卡异常不影响其它卡片。
 */
export const useEndfieldActivitySource = () => {
  const { t } = useI18n()
  const overview = ref<EndfieldActivityOverview>(createEmptyEndfieldActivityOverview())
  /** 官网当期宣传图（已经过本软件后端缩放），横幅优先用它 */
  const versionArt = ref('')
  /** 当前版本名（如「雪凇幽梦」），横幅标题用它 */
  const versionName = ref('')
  /** 解析结果留在这里：manifest 的版本没变时直接复用它，省下五兆多的表 */
  let sourceData: EndfieldSourceData | null = null

  const fetchJson = async (url: string, signal?: AbortSignal): Promise<unknown> => {
    const response = await fetch(url, { signal, headers: { Accept: 'application/json' } })
    if (!response.ok) {
      throw new Error('HTTP ' + response.status)
    }
    return response.json()
  }

  const stripSlashes = (value: string): string => {
    let start = 0
    let end = value.length
    while (start < end && value[start] === '/') {
      start += 1
    }
    while (end > start && value[end - 1] === '/') {
      end -= 1
    }
    return value.slice(start, end)
  }

  /** SRA 兜底的结果存一份，免得每次退避重试都去拉一遍 */
  let sraFallback: EndfieldActivityItem[] | null = null

  /**
   * 取 SRA 托管的终末地活动列表。
   *
   * AKEData 的六张表要走五兆多的流量，网络差或对方抽风时整卡会空着；SRA 那份是它自己
   * 抓好落成的静态 JSON，几百毫秒就能拿到，用来保证卡片至少还有活动可看。代价是它没有
   * 卡池与活动分类，`Tags` 留空、`Pools` 为空数组。
   */
  const loadSraActivities = async (): Promise<EndfieldActivityItem[] | null> => {
    if (sraFallback !== null) return sraFallback
    try {
      const payload = (await fetchJson(SRA_ACTIVITY_URL)) as SraActivityPayload | undefined
      const items = Array.isArray(payload?.activities) ? payload.activities : []
      const activities = items
        .filter(item => (item.name ?? '').trim() !== '')
        .map((item, index) => ({
          Id: `sra-${index}`,
          Name: (item.name ?? '').trim(),
          StartTime: item.startTime ?? '',
          EndTime: item.endTime ?? '',
          ImageUrl: '',
          CoverUrl: item.cover ?? '',
          Tags: [],
        }))
      if (activities.length === 0) {
        return null
      }
      sraFallback = activities
      return activities
    } catch (error) {
      logger.warn(
        `获取 SRA 终末地活动失败: ${error instanceof Error ? error.message : String(error)}`
      )
      return null
    }
  }

  /** 表下不动时改用 SRA 那份顶上：卡片至少有活动，卡池留空 */
  const applySraFallback = async () => {
    const activities = await loadSraActivities()
    if (activities === null) return
    logger.info('终末地活动数据改用 SRA 兜底')
    overview.value = {
      ...createEmptyEndfieldActivityOverview(),
      Available: true,
      SourceName: 'SRA',
      SourceUrl: SRA_SOURCE_URL,
      Activities: activities,
    }
  }

  /** 版本图（官网当期宣传图）：取到就用它当横幅封面，取不到退回活动大图 */
  const loadVersionArt = async () => {
    try {
      const result = await GetService.getEndfieldVersionArtApiInfoEndfieldVersionArtGet()
      if (result.code !== 200) throw new Error(result.message || 'HTTP ' + result.code)
      const payload = result.data as { url?: string; name?: string } | undefined
      const url = payload?.url ?? ''
      versionArt.value = url
        ? `${OpenAPI.BASE}/api/info/endfield/image?url=${encodeURIComponent(url)}`
        : ''
      versionName.value = payload?.name ?? ''
    } catch (error) {
      logger.warn(`获取终末地版本图失败: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  const source = useHomeActivitySource<EndfieldSourceData>({
    label: () => '终末地',
    timeoutMs: FETCH_TIMEOUT_MS,
    restoreSnapshot: () => {
      const restored = loadSnapshot()
      if (restored === null) return false
      // 启动先用上次快照填卡片，不等网络
      sourceData = restored
      overview.value = buildEndfieldOverview(restored, new Date()) as EndfieldActivityOverview
      return true
    },
    saveSnapshot: data => {
      try {
        localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(data))
      } catch {
        // 本地存储不可用时仅跳过快照缓存
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

      if (sourceData !== null && sourceData.versionId === latest) {
        if (sourceData.sourceUpdatedAt !== (manifest.updatedAt ?? '')) {
          sourceData = { ...sourceData, sourceUpdatedAt: manifest.updatedAt ?? '' }
        }
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
      sourceData = {
        versionId: latest,
        sourceUpdatedAt: manifest.updatedAt ?? '',
        ...resolved,
      }
      return sourceData
    },
    applyData: data => {
      overview.value = buildEndfieldOverview(data, new Date()) as EndfieldActivityOverview
    },
    markStale: () => {
      overview.value = {
        ...overview.value,
        Stale: true,
        Message: t('home.endfield.staleMessage'),
      }
    },
    markUnavailable: () => {
      overview.value = {
        ...createEmptyEndfieldActivityOverview(),
        Message: t('home.endfield.unavailable'),
      }
      // 表下不动时还有一条备用路：SRA 托管的静态活动列表
      void applySraFallback()
    },
    onFirstStart: () => {
      void loadVersionArt()
    },
  })

  return {
    overview,
    loading: source.loading,
    versionArt,
    versionName,
    start: source.start,
    stop: source.stop,
    refresh: source.refresh,
  }
}
