import { computed, ref, shallowRef } from 'vue'

import { translate as t } from '@/i18n'
import { formatBackendDateTime } from '@/utils/dateDisplay'
import type {
  OnlineAppearanceErrorCode,
  OnlineAppearanceItem,
  OnlineAppearancePreview,
  OnlineAppearanceVersion,
} from '@/types/appearance'
import { createCoverLoader, type CoverTask } from './coverLoader'

export const ONLINE_APPEARANCE_PAGE_SIZE = 12
export const ONLINE_APPEARANCE_SEARCH_DEBOUNCE = 400
export const ONLINE_APPEARANCE_COVER_CACHE_LIMIT = 48
export const ONLINE_APPEARANCE_COVER_CONCURRENCY = 3

/** 设置页的覆盖确认、失败提示和安装后预览都在 useAppearanceSettings 里，这里只关心结局。 */
export type OnlineAppearanceInstallOutcome = 'installed' | 'cancelled' | 'failed'

export type OnlineAppearanceStatus = 'none' | 'installed' | 'outdated'

export interface PreparedOnlineAppearance {
  token: string
  fileKey: string
  versionNo: number
  appearance: OnlineAppearancePreview
  existing: { id: string; name: string } | null
}

const ERROR_KEYS: Record<OnlineAppearanceErrorCode, string> = {
  NETWORK: 'themeStore.error.network',
  NOT_FOUND: 'themeStore.error.notFound',
  BAD_RESPONSE: 'themeStore.error.badResponse',
  TOO_LARGE: 'themeStore.error.tooLarge',
  CHECKSUM_MISMATCH: 'themeStore.error.checksum',
  EXPIRED: 'themeStore.error.expired',
  UNSUPPORTED: 'themeStore.error.unsupported',
}

const UNSUPPORTED = { code: 'UNSUPPORTED' } as const

/** 站端与下载类失败用本地文案；外观包校验失败沿用主进程给出的具体原因。 */
export function describeOnlineAppearanceError(
  result: { code?: string; error?: string } | undefined,
  fallbackKey: string
): string {
  const code = result?.code
  if (code && Object.prototype.hasOwnProperty.call(ERROR_KEYS, code)) {
    return t(ERROR_KEYS[code as OnlineAppearanceErrorCode])
  }
  return result?.error || t(fallbackKey)
}

export function getOnlineAppearanceStatus(item: OnlineAppearanceItem): OnlineAppearanceStatus {
  if (!item.installed) return 'none'
  if (item.publishedVersionNo !== null && item.publishedVersionNo > item.installed.versionNo) {
    return 'outdated'
  }
  return 'installed'
}

export function formatAppearanceFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// 时间来自分享站，按本机时区展示
export function formatOnlineAppearanceTime(value: string): string {
  return value ? formatBackendDateTime(value) : t('themeStore.unknownTime')
}

export function pickDefaultVersion(
  versions: OnlineAppearanceVersion[],
  publishedVersionNo: number | null
): number | null {
  if (publishedVersionNo !== null && versions.some(item => item.versionNo === publishedVersionNo)) {
    return publishedVersionNo
  }
  return versions[0]?.versionNo ?? null
}

export function useOnlineAppearance(options: {
  install: (token: string) => Promise<OnlineAppearanceInstallOutcome>
}) {
  const logger = window.electronAPI.getLogger('在线外观')
  const api = () => window.electronAPI

  const view = ref<'list' | 'detail'>('list')

  const items = ref<OnlineAppearanceItem[]>([])
  const listLoading = ref(false)
  const listError = ref<string | null>(null)
  const page = ref(1)
  const total = ref(0)
  const keyword = ref('')
  let listRevision = 0
  let searchTimer: ReturnType<typeof setTimeout> | null = null

  const detailItem = ref<OnlineAppearanceItem | null>(null)
  const versions = ref<OnlineAppearanceVersion[]>([])
  const detailLoading = ref(false)
  const detailError = ref<string | null>(null)
  const selectedVersionNo = ref<number | null>(null)
  let detailRevision = 0

  const prepared = shallowRef<PreparedOnlineAppearance | null>(null)
  const preparing = ref(false)
  const prepareError = ref<string | null>(null)
  const installing = ref(false)
  let prepareRevision = 0

  const selectedVersion = computed(
    () => versions.value.find(item => item.versionNo === selectedVersionNo.value) ?? null
  )

  // 封面按「file_key@版本」缓存在本页会话里，条数有上限；主进程另有一层缓存，翻页回来不会重复下载。
  // 一次最多并发 3 张，列表很长时也不会把分享站一下打满；重新加载列表时旧列表没开始的封面作废。
  const coverLoader = createCoverLoader({
    limit: ONLINE_APPEARANCE_COVER_CACHE_LIMIT,
    concurrency: ONLINE_APPEARANCE_COVER_CONCURRENCY,
  })
  const coverKey = (fileKey: string, versionNo: number): string => `${fileKey}@${versionNo}`

  const coverFor = (fileKey: string, versionNo: number | null): string | undefined =>
    versionNo === null ? undefined : coverLoader.get(coverKey(fileKey, versionNo))

  const coverTask = (fileKey: string, versionNo: number): CoverTask => {
    const key = coverKey(fileKey, versionNo)
    return {
      key,
      run: async () => {
        try {
          const result = await api().getOnlineAppearanceCover?.(fileKey, versionNo)
          if (result?.success && result.dataUrl) return result.dataUrl
          if (result && result.code !== 'NOT_FOUND') {
            logger.warn(`加载外观封面失败: ${key}，${result.error ?? result.code ?? '未知错误'}`)
          }
        } catch (error) {
          logger.warn(
            `加载外观封面失败: ${key}，${error instanceof Error ? error.message : String(error)}`
          )
        }
        return null
      },
    }
  }

  const ensureCover = (fileKey: string, versionNo: number | null): void => {
    if (versionNo !== null) coverLoader.request(coverTask(fileKey, versionNo))
  }

  const loadCovers = (list: OnlineAppearanceItem[]): void => {
    coverLoader.load(
      list.flatMap(item =>
        item.hasCover && item.publishedVersionNo !== null
          ? [coverTask(item.fileKey, item.publishedVersionNo)]
          : []
      )
    )
  }

  const detailCover = computed(() => {
    const item = detailItem.value
    const version = selectedVersion.value
    if (!item || !version?.hasCover) return undefined
    return coverFor(item.fileKey, version.versionNo)
  })

  const discardToken = (token: string): void => {
    void Promise.resolve(api().discardOnlineAppearance?.(token)).catch(() => undefined)
  }

  const discardPrepared = (): void => {
    const token = prepared.value?.token
    prepared.value = null
    if (token) discardToken(token)
  }

  const cancelScheduledSearch = (): void => {
    if (searchTimer !== null) {
      clearTimeout(searchTimer)
      searchTimer = null
    }
  }

  const loadList = async (targetPage = page.value): Promise<void> => {
    cancelScheduledSearch()
    const revision = ++listRevision
    listLoading.value = true
    listError.value = null
    try {
      const query = keyword.value.trim()
      const result = await api().listOnlineAppearances?.({
        page: targetPage,
        pageSize: ONLINE_APPEARANCE_PAGE_SIZE,
        ...(query ? { keyword: query } : {}),
      })
      if (revision !== listRevision) return
      if (!result?.success) {
        items.value = []
        total.value = 0
        listError.value = describeOnlineAppearanceError(
          result ?? UNSUPPORTED,
          'themeStore.listFailed'
        )
        logger.warn(`加载在线外观列表失败: ${result?.error ?? result?.code ?? '不支持'}`)
        return
      }
      items.value = result.items ?? []
      page.value = result.pagination?.page ?? targetPage
      total.value = result.pagination?.total ?? items.value.length
      loadCovers(items.value)
    } catch (error) {
      if (revision !== listRevision) return
      items.value = []
      total.value = 0
      listError.value = t('themeStore.listFailed')
      logger.error(
        `加载在线外观列表失败: ${error instanceof Error ? error.message : String(error)}`
      )
    } finally {
      if (revision === listRevision) listLoading.value = false
    }
  }

  const scheduleSearch = (): void => {
    cancelScheduledSearch()
    searchTimer = setTimeout(() => void loadList(1), ONLINE_APPEARANCE_SEARCH_DEBOUNCE)
  }

  const clearKeyword = (): void => {
    keyword.value = ''
    void loadList(1)
  }

  // 预览就是把选中的版本完整下载并校验一遍；安装直接用这一份，不再下载第二次。
  const prepareSelected = async (): Promise<PreparedOnlineAppearance | null> => {
    const item = detailItem.value
    const versionNo = selectedVersionNo.value
    if (!item || versionNo === null) return null
    const current = prepared.value
    if (current && current.fileKey === item.fileKey && current.versionNo === versionNo) {
      return current
    }
    const revision = ++prepareRevision
    discardPrepared()
    preparing.value = true
    prepareError.value = null
    try {
      const result = await api().prepareOnlineAppearance?.(item.fileKey, versionNo)
      if (revision !== prepareRevision) {
        if (result?.token) discardToken(result.token)
        return null
      }
      if (!result?.success || !result.token || !result.appearance) {
        if (result?.token) discardToken(result.token)
        prepareError.value = describeOnlineAppearanceError(
          result ?? UNSUPPORTED,
          'themeStore.prepareFailed'
        )
        logger.warn(
          `下载在线外观失败: ${item.fileKey} v${versionNo}，${result?.error ?? result?.code ?? '不支持'}`
        )
        return null
      }
      prepared.value = {
        token: result.token,
        fileKey: item.fileKey,
        versionNo,
        appearance: result.appearance,
        existing: result.existing ?? null,
      }
      return prepared.value
    } catch (error) {
      if (revision !== prepareRevision) return null
      prepareError.value = t('themeStore.prepareFailed')
      logger.error(
        `下载在线外观失败: ${item.fileKey} v${versionNo}，${error instanceof Error ? error.message : String(error)}`
      )
      return null
    } finally {
      if (revision === prepareRevision) preparing.value = false
    }
  }

  const resetDetail = (): void => {
    detailRevision += 1
    prepareRevision += 1
    discardPrepared()
    detailItem.value = null
    versions.value = []
    selectedVersionNo.value = null
    detailLoading.value = false
    detailError.value = null
    preparing.value = false
    prepareError.value = null
  }

  const openDetail = async (item: OnlineAppearanceItem): Promise<void> => {
    if (installing.value) return
    resetDetail()
    const revision = detailRevision
    view.value = 'detail'
    detailItem.value = item
    detailLoading.value = true
    try {
      const result = await api().getOnlineAppearance?.(item.fileKey)
      if (revision !== detailRevision) return
      if (!result?.success) {
        detailError.value = describeOnlineAppearanceError(
          result ?? UNSUPPORTED,
          'themeStore.detailFailed'
        )
        logger.warn(
          `加载在线外观详情失败: ${item.fileKey}，${result?.error ?? result?.code ?? '不支持'}`
        )
        return
      }
      if (result.item) detailItem.value = result.item
      versions.value = result.versions ?? []
      selectedVersionNo.value = pickDefaultVersion(
        versions.value,
        detailItem.value?.publishedVersionNo ?? null
      )
    } catch (error) {
      if (revision !== detailRevision) return
      detailError.value = t('themeStore.detailFailed')
      logger.error(
        `加载在线外观详情失败: ${item.fileKey}，${error instanceof Error ? error.message : String(error)}`
      )
      return
    } finally {
      if (revision === detailRevision) detailLoading.value = false
    }
    if (revision !== detailRevision || selectedVersionNo.value === null) return
    if (selectedVersion.value?.hasCover && detailItem.value) {
      ensureCover(detailItem.value.fileKey, selectedVersionNo.value)
    }
    await prepareSelected()
  }

  const retryDetail = (): void => {
    const item = detailItem.value
    if (item) void openDetail(item)
  }

  const selectVersion = (versionNo: number): void => {
    if (installing.value || versionNo === selectedVersionNo.value) return
    const version = versions.value.find(item => item.versionNo === versionNo)
    if (!version) return
    selectedVersionNo.value = versionNo
    if (version.hasCover && detailItem.value) ensureCover(detailItem.value.fileKey, versionNo)
    void prepareSelected()
  }

  const install = async (): Promise<OnlineAppearanceInstallOutcome> => {
    if (installing.value || preparing.value) return 'cancelled'
    installing.value = true
    let outcome: OnlineAppearanceInstallOutcome = 'failed'
    try {
      const ready = await prepareSelected()
      if (!ready) return outcome
      outcome = await options.install(ready.token)
      // 用户拒绝覆盖时主进程保留临时包，换别的结局都已经用掉或删掉了。
      if (outcome !== 'cancelled' && prepared.value?.token === ready.token) discardPrepared()
      return outcome
    } finally {
      installing.value = false
      // 装好后回到列表并重新拉一次，「已安装 / 有新版本」标记才会跟上。
      if (outcome === 'installed') {
        backToList()
        void loadList(page.value)
      }
    }
  }

  const backToList = (): void => {
    if (installing.value) return
    resetDetail()
    view.value = 'list'
  }

  const open = (): void => {
    reset()
    void loadList(1)
  }

  const reset = (): void => {
    cancelScheduledSearch()
    listRevision += 1
    resetDetail()
    view.value = 'list'
    items.value = []
    listLoading.value = false
    listError.value = null
    page.value = 1
    total.value = 0
    keyword.value = ''
    installing.value = false
    coverLoader.reset()
  }

  return {
    view,
    items,
    listLoading,
    listError,
    page,
    total,
    keyword,
    pageSize: ONLINE_APPEARANCE_PAGE_SIZE,
    detailItem,
    versions,
    detailLoading,
    detailError,
    selectedVersionNo,
    selectedVersion,
    coverFor,
    detailCover,
    prepared,
    preparing,
    prepareError,
    installing,
    open,
    reset,
    loadList,
    scheduleSearch,
    clearKeyword,
    openDetail,
    retryDetail,
    selectVersion,
    prepareSelected,
    install,
    backToList,
  }
}

export type OnlineAppearanceStore = ReturnType<typeof useOnlineAppearance>
