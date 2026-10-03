import { onScopeDispose, ref } from 'vue'
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

const logger = window.electronAPI.getLogger('活动数据')

/** 活动条目的形状（types/home.ts 里没有导出，从概览类型上取） */
type EndfieldActivityItem = EndfieldActivityOverview['Activities'][number]

const AKEDATA_BASE_URL = 'https://data.akedata.wiki'
const AKEDATA_MANIFEST_URL = AKEDATA_BASE_URL + '/manifest.json'
/** 六张表并行下载（gzip 合计约 5.75MB），仅版本更新时触发，慢网放宽至 60s */
const FETCH_TIMEOUT_MS = 60_000
/** 失败重试节奏与 SRA 直连源一致 */
const RETRY_DELAY_MS = 30_000
const MAX_RETRIES = 8
const SNAPSHOT_KEY = 'auto-mas.home.endfield-snapshot'
/** AKEData 取不到、本地也没有快照时的兜底源：SRA 托管的终末地活动列表（没有卡池与分类） */
const SRA_ACTIVITY_URL = 'https://starrailassistant.top/api/v1/activity/end.json'
const SRA_SOURCE_URL = 'https://starrailassistant.top'

interface SraActivityPayload {
  activities?: { name?: string; startTime?: string; endTime?: string; cover?: string }[]
}

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
 * 带超时、失败退避重试与独立失败态——本卡异常不影响其它卡片。
 */
export const useEndfieldActivitySource = () => {
  const { t } = useI18n()
  const overview = ref<EndfieldActivityOverview>(createEmptyEndfieldActivityOverview())
  /** 官网当期宣传图（已经过本软件后端缩放），横幅优先用它 */
  const versionArt = ref('')
  /** 当前版本名（如「雪凇幽梦」），横幅标题用它 */
  const versionName = ref('')
  const loading = ref(false)
  let sourceData = loadSnapshot()
  let retryTimer: number | null = null
  let retryCount = 0
  let disposed = false
  let hasData = false

  // 启动先用上次快照填卡片，不等网络
  if (sourceData !== null) {
    overview.value = buildEndfieldOverview(sourceData, new Date()) as EndfieldActivityOverview
    hasData = true
  } else {
    loading.value = true
  }

  const applySuccess = (data: EndfieldSourceData) => {
    overview.value = buildEndfieldOverview(data, new Date()) as EndfieldActivityOverview
    hasData = true
  }

  const saveSnapshot = (data: EndfieldSourceData) => {
    try {
      localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(data))
    } catch {
      // 本地存储不可用时仅跳过快照缓存
    }
  }

  const fetchJson = async (url: string, signal: AbortSignal): Promise<unknown> => {
    const response = await fetch(url, { signal, headers: { Accept: 'application/json' } })
    if (!response.ok) {
      throw new Error('HTTP ' + response.status)
    }
    return response.json()
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
    if (sraFallback !== null) {
      return sraFallback
    }
    try {
      const response = await fetch(SRA_ACTIVITY_URL, { headers: { Accept: 'application/json' } })
      if (!response.ok) {
        throw new Error('HTTP ' + response.status)
      }
      const payload = (await response.json()) as SraActivityPayload
      const items = Array.isArray(payload.activities) ? payload.activities : []
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

  const load = async () => {
    if (disposed) {
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
    try {
      const manifest = (await fetchJson(
        `${AKEDATA_MANIFEST_URL}?t=${Date.now()}`,
        controller.signal
      )) as AkedataManifest
      const latest = manifest.latest
      const version = (manifest.versions ?? []).find(item => item.id === latest)
      if (!version) {
        throw new Error('manifest 未包含最新版本')
      }

      if (sourceData !== null && sourceData.versionId === latest) {
        if (sourceData.sourceUpdatedAt !== (manifest.updatedAt ?? '')) {
          sourceData = { ...sourceData, sourceUpdatedAt: manifest.updatedAt ?? '' }
          saveSnapshot(sourceData)
        }
        applySuccess(sourceData)
        retryCount = 0
        return
      }

      const tableRoot = AKEDATA_BASE_URL + '/' + stripSlashes(version.tableCfgPath)
      const [activities, timeRanges, activityTags, textTable, pools, characters] =
        (await Promise.all([
          fetchJson(tableRoot + '/ActivityTable.json', controller.signal),
          fetchJson(tableRoot + '/TimeRangeTable.json', controller.signal),
          fetchJson(tableRoot + '/ActivityTagTable.json', controller.signal),
          fetchJson(tableRoot + '/I18nTextTable_CN.json', controller.signal),
          fetchJson(tableRoot + '/GachaCharPoolTable.json', controller.signal),
          fetchJson(tableRoot + '/CharacterTable.json', controller.signal),
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
      saveSnapshot(sourceData)
      applySuccess(sourceData)
      retryCount = 0
    } catch (requestError) {
      if (disposed) {
        return
      }
      const errorMessage =
        requestError instanceof Error ? requestError.message : String(requestError)
      logger.warn('获取终末地活动数据失败: ' + errorMessage)
      if (hasData) {
        overview.value = {
          ...overview.value,
          Stale: true,
          Message: t('home.endfield.staleMessage'),
        }
      } else {
        // 连快照都没有（刚装上、或这台机器一直没成功过）：改用 SRA 那份顶上
        const fallback = await loadSraActivities()
        if (fallback !== null) {
          overview.value = {
            ...createEmptyEndfieldActivityOverview(),
            Available: true,
            SourceName: 'SRA',
            SourceUrl: SRA_SOURCE_URL,
            Activities: fallback,
          }
          logger.info('终末地活动数据改用 SRA 兜底')
        } else {
          overview.value = {
            ...createEmptyEndfieldActivityOverview(),
            Message: t('home.endfield.unavailable'),
          }
        }
      }
      if (retryCount < MAX_RETRIES) {
        retryCount += 1
        if (active) {
          scheduleRetry()
        } else {
          // 模块隐藏期间不重试，重新可见时补一次
          retryPending = true
        }
      }
    } finally {
      window.clearTimeout(timer)
      if (!disposed) {
        loading.value = false
      }
    }
  }

  // 模块可见时才发请求；隐藏时停掉重试定时器，重新可见时把攒下的重试补上
  let active = false
  let started = false
  let retryPending = false

  const scheduleRetry = () => {
    retryTimer = window.setTimeout(() => {
      retryTimer = null
      void load()
    }, RETRY_DELAY_MS)
  }

  const start = () => {
    if (disposed) return
    active = true
    if (!started) {
      started = true
      void load()
      void loadVersionArt()
    } else if (retryPending) {
      retryPending = false
      void load()
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

  const stop = () => {
    active = false
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
      retryPending = true
    }
  }

  onScopeDispose(() => {
    disposed = true
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
    }
  })

  return {
    overview,
    loading,
    versionArt,
    versionName,
    start,
    stop,
    refresh: () => {
      retryCount = 0
      void load()
    },
  }
}
