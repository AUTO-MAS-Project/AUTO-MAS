import { describePackageError } from '@/utils/resourcePackageError'
import { beginAnalyticsOperation } from '@/utils/analytics'
import { appearanceCategory } from '@/utils/preferenceAnalytics'
import { computed, ref, shallowRef } from 'vue'
import { message } from 'ant-design-vue'
import type { AppearanceCategory, AppearanceFilter } from '@/types/mascotPack'
import { useTheme } from '@/composables/useTheme'
import { useAppearanceTryOnStore } from '@/stores/appearanceTryOn'

import { translate as t } from '@/i18n'
import { formatBackendDateTime } from '@/utils/dateDisplay'
import type {
  OnlineAppearanceItem,
  OnlineAppearancePreview,
  OnlineAppearanceVersion,
} from '@/types/appearance'
import { createCoverLoader, type CoverTask } from './coverLoader'
import { loadAppearanceCatalog } from './appearanceCatalog'

export const ONLINE_APPEARANCE_PAGE_SIZE = 12
export const ONLINE_APPEARANCE_SEARCH_DEBOUNCE = 400
export const ONLINE_APPEARANCE_COVER_CACHE_LIMIT = 48
export const ONLINE_APPEARANCE_COVER_CONCURRENCY = 3

/** 设置页的覆盖确认、失败提示和安装后预览都在 useAppearanceSettings 里，这里只关心结局。 */
export type OnlineAppearanceInstallOutcome = 'installed' | 'partial' | 'cancelled' | 'failed'

export interface OnlineAppearanceInstallOptions {
  /** 安装成功后立即切换为当前生效外观（如试穿后确认应用）。 */
  applyImmediately?: boolean
  /** 仅更新资源包本身，不修改当前生效的主题或桌宠选择，也不弹单项预览提示（用于批量更新）。 */
  preserveCurrentSelection?: boolean
  /** 已知是在更新已安装资源时，直接允许覆盖同 ID，避免批量更新逐条弹确认框。 */
  replaceExisting?: boolean
}

export type OnlineAppearanceStatus = 'none' | 'installed' | 'outdated'

export interface PreparedOnlineAppearance {
  categoryKey?: AppearanceCategory
  token: string
  fileKey: string
  versionNo: number
  appearance: OnlineAppearancePreview
  existing: { id: string; name: string } | null
}

const UNSUPPORTED = { code: 'UNSUPPORTED' } as const

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
  return value ? formatBackendDateTime(value) : t('core.themeStore.unknownTime')
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
  install: (
    token: string,
    category?: AppearanceCategory,
    installOptions?: OnlineAppearanceInstallOptions
  ) => Promise<OnlineAppearanceInstallOutcome>
  categoryKey?: AppearanceFilter
  onInstalled?: () => void
}) {
  const logger = window.electronAPI.getLogger('在线外观')
  const api = () => window.electronAPI
  const { appearances } = useTheme()
  const tryOnStore = useAppearanceTryOnStore()
  const categoryArgs = (category?: AppearanceCategory): [] | [AppearanceCategory] => {
    if (category) return [category]
    return options.categoryKey && options.categoryKey !== 'all' ? [options.categoryKey] : []
  }

  const view = ref<'list' | 'detail'>('list')
  const tryingFileKey = ref<string | null>(null)

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
  const coverKey = (fileKey: string, versionNo: number, category?: AppearanceCategory): string =>
    `${category ?? ''}:${fileKey}@${versionNo}`

  const coverFor = (
    fileKey: string,
    versionNo: number | null,
    category?: AppearanceCategory
  ): string | undefined =>
    versionNo === null ? undefined : coverLoader.get(coverKey(fileKey, versionNo, category))

  const coverTask = (
    fileKey: string,
    versionNo: number,
    category?: AppearanceCategory
  ): CoverTask => {
    const key = coverKey(fileKey, versionNo, category)
    return {
      key,
      run: async () => {
        try {
          const result = await api().getOnlineAppearanceCover?.(
            fileKey,
            versionNo,
            ...categoryArgs(category)
          )
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

  const ensureCover = (
    fileKey: string,
    versionNo: number | null,
    category?: AppearanceCategory
  ): void => {
    if (versionNo !== null) coverLoader.request(coverTask(fileKey, versionNo, category))
  }

  const loadCovers = (list: OnlineAppearanceItem[]): void => {
    coverLoader.load(
      list.flatMap(item =>
        item.hasCover && item.publishedVersionNo !== null
          ? [coverTask(item.fileKey, item.publishedVersionNo, item.categoryKey)]
          : []
      )
    )
  }

  const detailCover = computed(() => {
    const item = detailItem.value
    const version = selectedVersion.value
    if (!item || !version?.hasCover) return undefined
    return coverFor(item.fileKey, version.versionNo, item.categoryKey)
  })

  const discardToken = (token: string, category?: AppearanceCategory): void => {
    void Promise.resolve(api().discardOnlineAppearance?.(token, ...categoryArgs(category))).catch(
      () => undefined
    )
  }

  const discardPrepared = (): void => {
    const ready = prepared.value
    prepared.value = null
    if (ready) discardToken(ready.token, ready.categoryKey)
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
      const request = {
        page: targetPage,
        pageSize: ONLINE_APPEARANCE_PAGE_SIZE,
        ...(query ? { keyword: query } : {}),
      }
      const result =
        options.categoryKey === 'all'
          ? await loadAppearanceCatalog(
              request,
              (next, category) =>
                api().listOnlineAppearances?.(next, category) ??
                Promise.resolve({ success: false, ...UNSUPPORTED })
            )
          : await api().listOnlineAppearances?.(request, ...categoryArgs())
      if (revision !== listRevision) return
      if (!result?.success) {
        items.value = []
        total.value = 0
        listError.value = describePackageError(result ?? UNSUPPORTED, 'core.themeStore.listFailed')
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
      listError.value = t('core.themeStore.listFailed')
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
      const result = await api().prepareOnlineAppearance?.(
        item.fileKey,
        versionNo,
        ...categoryArgs(item.categoryKey)
      )
      if (revision !== prepareRevision) {
        if (result?.token) discardToken(result.token, item.categoryKey)
        return null
      }
      if (!result?.success || !result.token || !result.appearance) {
        if (result?.token) discardToken(result.token, item.categoryKey)
        prepareError.value = describePackageError(
          result ?? UNSUPPORTED,
          'core.themeStore.prepareFailed',
          item.categoryKey ?? (options.categoryKey === 'mascot' ? 'mascot' : 'theme')
        )
        logger.warn(
          `下载在线外观失败: ${item.fileKey} v${versionNo}，${result?.error ?? result?.code ?? '不支持'}`
        )
        return null
      }
      prepared.value = {
        ...(item.categoryKey ? { categoryKey: item.categoryKey } : {}),
        token: result.token,
        fileKey: item.fileKey,
        versionNo,
        appearance: result.appearance,
        existing: result.existing ?? null,
      }
      return prepared.value
    } catch (error) {
      if (revision !== prepareRevision) return null
      prepareError.value = t('core.themeStore.prepareFailed')
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
      const result = await api().getOnlineAppearance?.(
        item.fileKey,
        ...categoryArgs(item.categoryKey)
      )
      if (revision !== detailRevision) return
      if (!result?.success) {
        detailError.value = describePackageError(
          result ?? UNSUPPORTED,
          'core.themeStore.detailFailed'
        )
        logger.warn(
          `加载在线外观详情失败: ${item.fileKey}，${result?.error ?? result?.code ?? '不支持'}`
        )
        return
      }
      if (result.item)
        detailItem.value = {
          ...result.item,
          ...(item.categoryKey ? { categoryKey: item.categoryKey } : {}),
        }
      versions.value = result.versions ?? []
      selectedVersionNo.value = pickDefaultVersion(
        versions.value,
        detailItem.value?.publishedVersionNo ?? null
      )
    } catch (error) {
      if (revision !== detailRevision) return
      detailError.value = t('core.themeStore.detailFailed')
      logger.error(
        `加载在线外观详情失败: ${item.fileKey}，${error instanceof Error ? error.message : String(error)}`
      )
      return
    } finally {
      if (revision === detailRevision) detailLoading.value = false
    }
    if (revision !== detailRevision || selectedVersionNo.value === null) return
    if (selectedVersion.value?.hasCover && detailItem.value) {
      ensureCover(detailItem.value.fileKey, selectedVersionNo.value, detailItem.value.categoryKey)
    }
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
    if (version.hasCover && detailItem.value)
      ensureCover(detailItem.value.fileKey, versionNo, detailItem.value.categoryKey)
    discardPrepared()
    prepareError.value = null
  }

  const install = async (): Promise<OnlineAppearanceInstallOutcome> => {
    if (installing.value || preparing.value) return 'cancelled'
    const telemetry = beginAnalyticsOperation('appearance_store_install_finished')
    let category_kind = appearanceCategory(options.categoryKey ?? 'theme')
    installing.value = true
    let outcome: OnlineAppearanceInstallOutcome = 'failed'
    try {
      const ready = await prepareSelected()
      if (!ready) return outcome
      category_kind = appearanceCategory(
        ready.categoryKey ??
          (options.categoryKey === 'all' ? undefined : (options.categoryKey ?? 'theme'))
      )
      outcome = await (options.categoryKey === 'all'
        ? options.install(ready.token, ready.categoryKey)
        : options.install(ready.token))
      // 用户拒绝覆盖时主进程保留临时包，换别的结局都已经用掉或删掉了。
      if (outcome !== 'cancelled' && prepared.value?.token === ready.token) discardPrepared()
      return outcome
    } finally {
      telemetry.finish({
        category_kind,
        outcome:
          outcome === 'installed'
            ? 'success'
            : outcome === 'partial'
              ? 'partial'
              : outcome === 'cancelled'
                ? 'cancelled'
                : 'failure',
      })
      installing.value = false
      // 装好后回到列表并重新拉一次，「已安装 / 有新版本」标记才会跟上。
      if (outcome === 'installed') {
        backToList()
        void loadList(page.value)
        options.onInstalled?.()
      }
    }
  }

  const detailOpen = computed(() => view.value === 'detail' && Boolean(detailItem.value))

  const installTokenWithTelemetry = async (
    token: string,
    category: AppearanceCategory,
    installOptions?: OnlineAppearanceInstallOptions
  ): Promise<OnlineAppearanceInstallOutcome> => {
    const telemetry = beginAnalyticsOperation('appearance_store_install_finished')
    let outcome: OnlineAppearanceInstallOutcome = 'failed'
    try {
      outcome = await options.install(token, category, installOptions)
      return outcome
    } finally {
      telemetry.finish({
        category_kind: appearanceCategory(category),
        outcome:
          outcome === 'installed'
            ? 'success'
            : outcome === 'partial'
              ? 'partial'
              : outcome === 'cancelled'
                ? 'cancelled'
                : 'failure',
      })
    }
  }

  /**
   * 卡片或详情内一键试穿（仅主题外观，纯内存态、不写盘）：
   * - 已安装且版本一致时直接复用本机内存外观，零下载秒开；
   * - 否则下载校验为临时 token，装进全局试穿沙盒，满意时可直接消费该 token 安装并应用。
   */
  const tryOnItem = async (
    item: OnlineAppearanceItem,
    explicitVersionNo?: number
  ): Promise<void> => {
    const itemCategory: AppearanceCategory =
      item.categoryKey ?? (options.categoryKey === 'mascot' ? 'mascot' : 'theme')
    if (itemCategory !== 'theme' || tryingFileKey.value || installing.value) return

    const targetVersion = explicitVersionNo ?? item.publishedVersionNo
    if (targetVersion === null) {
      message.warning(t('core.themeStore.noVersions'))
      return
    }

    const coverUrl = coverFor(item.fileKey, targetVersion, item.categoryKey)
    // 本机已装同版本时直接试穿内存外观，不重复下载。
    if (item.installed && item.installed.versionNo === targetVersion) {
      const local = appearances.value.find(entry => entry.id === item.installed?.appearanceId)
      if (local) {
        tryOnStore.start({
          source: 'installed',
          title: item.displayName || item.fileKey,
          versionNo: targetVersion,
          coverUrl: coverUrl ?? local.previewUrl,
          fileKey: item.fileKey,
          installedId: local.id,
          hasBundledMascot: Boolean(local.mascot),
          appearance: local,
        })
        return
      }
    }

    tryingFileKey.value = item.fileKey
    try {
      const result = await api().prepareOnlineAppearance?.(item.fileKey, targetVersion, 'theme')
      if (!result?.success || !result.token || !result.appearance?.tryOnAppearance) {
        if (result?.token) discardToken(result.token, 'theme')
        message.error(
          describePackageError(result ?? UNSUPPORTED, 'core.themeStore.prepareFailed', 'theme')
        )
        return
      }
      const token = result.token
      tryOnStore.start({
        source: 'store',
        title: item.displayName || item.fileKey,
        versionNo: targetVersion,
        coverUrl: coverUrl ?? result.appearance.previewUrl,
        fileKey: item.fileKey,
        token,
        hasBundledMascot: Boolean(result.appearance.hasBundledMascot),
        appearance: result.appearance.tryOnAppearance,
        onInstall: async () => {
          const outcome = await installTokenWithTelemetry(token, 'theme', {
            applyImmediately: true,
          })
          if (outcome === 'installed') {
            void loadList(page.value)
            options.onInstalled?.()
          }
          return outcome
        },
      })
    } catch (error) {
      logger.error(
        `试穿在线外观失败: ${item.fileKey} v${targetVersion}，${error instanceof Error ? error.message : String(error)}`
      )
      message.error(t('core.themeStore.prepareFailed'))
    } finally {
      tryingFileKey.value = null
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
    detailOpen,
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
    tryingFileKey,
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
    tryOnItem,
    backToList,
  }
}

export type OnlineAppearanceStore = ReturnType<typeof useOnlineAppearance>
