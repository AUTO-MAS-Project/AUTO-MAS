import type { AppearanceCoverMode } from '@/composables/useShareApi'
import type { AppearancePrecheckInfo, ImageDimensions } from '@/types/appearance'
import type { AppearanceCategory } from '@/types/mascotPack'
import type { InheritCoverState } from './myAppearance'

export type UploadSubmissionMode = 'preview' | 'direct'
export type PrecheckSeverity = 'pass' | 'warning' | 'error'

export interface UploadPrecheckItem {
  id: 'archive-size' | 'default-menu-icon' | 'cover-ready' | 'cover-aspect'
  severity: PrecheckSeverity
  blocking: boolean
  titleKey: string
  detailKey: string
  params?: Record<string, string | number>
}

export interface UploadPrecheckResult {
  items: UploadPrecheckItem[]
  hasBlockingError: boolean
  warningCount: number
}

const MAX_ARCHIVE_BYTES: Record<AppearanceCategory, number> = {
  theme: 100 * 1024 * 1024,
  mascot: 50 * 1024 * 1024,
}

const COVER_MIN_WIDTH = 640
const COVER_MIN_HEIGHT = 400
const COVER_MIN_RATIO = 1.15
const COVER_MAX_RATIO = 2.15

const UPLOAD_MODE_STORAGE_KEY = 'auto-mas:theme-store:upload-mode'

export function readPreferredUploadMode(): UploadSubmissionMode {
  try {
    const raw = window.localStorage.getItem(UPLOAD_MODE_STORAGE_KEY)
    if (raw === 'direct' || raw === 'preview') return raw
  } catch {
    // 浏览器隐私模式或禁用存储时回落到推荐值。
  }
  return 'preview'
}

export function savePreferredUploadMode(mode: UploadSubmissionMode): void {
  try {
    window.localStorage.setItem(UPLOAD_MODE_STORAGE_KEY, mode)
  } catch {
    // 忽略存储写入失败，不影响上传流程。
  }
}

export function evaluateUploadPrecheck(input: {
  categoryKey: AppearanceCategory
  fileSize: number
  precheck?: AppearancePrecheckInfo
  coverMode: AppearanceCoverMode
  coverReady: boolean
  inheritCoverState: InheritCoverState
  customCoverDimensions?: ImageDimensions | null
}): UploadPrecheckResult {
  const items: UploadPrecheckItem[] = []
  const maxBytes = MAX_ARCHIVE_BYTES[input.categoryKey]
  const maxMb = Math.round(maxBytes / 1024 / 1024)
  const sizeMb = (input.fileSize / 1024 / 1024).toFixed(2)

  // 1. 资源包体积上限（硬性阻塞）
  const sizeOk = input.fileSize > 0 && input.fileSize <= maxBytes
  items.push({
    id: 'archive-size',
    severity: sizeOk ? 'pass' : 'error',
    blocking: !sizeOk,
    titleKey: 'core.themeStore.upload.precheck.archiveSize',
    detailKey: sizeOk
      ? 'core.themeStore.upload.precheck.archiveSizePass'
      : 'core.themeStore.upload.precheck.archiveSizeFail',
    params: { size: sizeMb, limit: maxMb },
  })

  // 2. 带自定义菜单图标的主题必须提供 menuIcons.default（与后端 #2178 保持一致，硬性阻塞）
  if (input.categoryKey === 'theme') {
    const hasCustomIcons = Boolean(input.precheck?.hasCustomMenuIcons)
    const hasDefaultIcon = Boolean(input.precheck?.hasDefaultMenuIcon)
    const iconCount = input.precheck?.menuIconCount ?? 0
    if (hasCustomIcons && !hasDefaultIcon) {
      items.push({
        id: 'default-menu-icon',
        severity: 'error',
        blocking: true,
        titleKey: 'core.themeStore.upload.precheck.defaultMenuIcon',
        detailKey: 'core.themeStore.upload.precheck.defaultMenuIconMissing',
        params: { count: iconCount },
      })
    } else {
      items.push({
        id: 'default-menu-icon',
        severity: 'pass',
        blocking: false,
        titleKey: 'core.themeStore.upload.precheck.defaultMenuIcon',
        detailKey: hasCustomIcons
          ? 'core.themeStore.upload.precheck.defaultMenuIconPass'
          : 'core.themeStore.upload.precheck.defaultMenuIconNotNeeded',
        params: { count: iconCount },
      })
    }
  }

  // 3. 封面可用性检查（硬性阻塞）
  const coverPending = input.coverMode === 'inherit' && input.inheritCoverState === 'loading'
  items.push({
    id: 'cover-ready',
    severity: input.coverReady ? 'pass' : coverPending ? 'warning' : 'error',
    blocking: !input.coverReady,
    titleKey: 'core.themeStore.upload.precheck.coverReady',
    detailKey: input.coverReady
      ? 'core.themeStore.upload.precheck.coverReadyPass'
      : coverPending
        ? 'core.themeStore.upload.precheck.coverChecking'
        : 'core.themeStore.upload.precheck.coverMissing',
  })

  // 4. 封面尺寸与 16:10 裁切比例检查（机器可判定，异常给明确告警）
  const dimensions =
    input.coverMode === 'custom'
      ? input.customCoverDimensions
      : input.coverMode === 'package'
        ? input.precheck?.previewDimensions
        : null
  if (dimensions && dimensions.width > 0 && dimensions.height > 0) {
    const ratio = dimensions.width / dimensions.height
    const ratioOutOfRange = ratio < COVER_MIN_RATIO || ratio > COVER_MAX_RATIO
    const tooSmall = dimensions.width < COVER_MIN_WIDTH || dimensions.height < COVER_MIN_HEIGHT
    if (ratioOutOfRange || tooSmall) {
      items.push({
        id: 'cover-aspect',
        severity: 'warning',
        blocking: false,
        titleKey: 'core.themeStore.upload.precheck.coverAspect',
        detailKey: ratioOutOfRange
          ? 'core.themeStore.upload.precheck.coverAspectWarn'
          : 'core.themeStore.upload.precheck.coverResolutionWarn',
        params: {
          width: dimensions.width,
          height: dimensions.height,
          ratio: ratio.toFixed(2),
        },
      })
    } else {
      items.push({
        id: 'cover-aspect',
        severity: 'pass',
        blocking: false,
        titleKey: 'core.themeStore.upload.precheck.coverAspect',
        detailKey: 'core.themeStore.upload.precheck.coverAspectPass',
        params: { width: dimensions.width, height: dimensions.height },
      })
    }
  }

  return {
    items,
    hasBlockingError: items.some(item => item.blocking),
    warningCount: items.filter(item => item.severity === 'warning').length,
  }
}
