import { onScopeDispose, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  buildEndfieldOverview,
  resolveEndfieldSourceData,
  restoreEndfieldSourceData,
  type AkedataManifest,
  type EndfieldSourceData,
} from './endfieldActivityTransform'
import { createEmptyEndfieldActivityOverview, type EndfieldActivityOverview } from '@/types/home'

const logger = window.electronAPI.getLogger('活动数据')

const AKEDATA_BASE_URL = 'https://data.akedata.wiki'
const AKEDATA_MANIFEST_URL = AKEDATA_BASE_URL + '/manifest.json'
/** 六张表并行下载（gzip 合计约 5.75MB），仅版本更新时触发，慢网放宽至 60s */
const FETCH_TIMEOUT_MS = 60_000
/** 失败重试节奏与 SRA 直连源一致 */
const RETRY_DELAY_MS = 30_000
const MAX_RETRIES = 8
const SNAPSHOT_KEY = 'auto-mas.home.endfield-snapshot'

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
      const manifest = (await fetchJson(`${AKEDATA_MANIFEST_URL}?t=${Date.now()}`, controller.signal)) as AkedataManifest
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
        overview.value = {
          ...createEmptyEndfieldActivityOverview(),
          Message: t('home.endfield.unavailable'),
        }
      }
      if (retryCount < MAX_RETRIES) {
        retryCount += 1
        retryTimer = window.setTimeout(() => {
          retryTimer = null
          void load()
        }, RETRY_DELAY_MS)
      }
    } finally {
      window.clearTimeout(timer)
      if (!disposed) {
        loading.value = false
      }
    }
  }

  onScopeDispose(() => {
    disposed = true
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
    }
  })

  void load()

  return {
    overview,
    loading,
    refresh: () => {
      retryCount = 0
      void load()
    },
  }
}
