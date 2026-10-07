import type {
  AppearanceCoverMode,
  AppearanceUploadRecord,
  MyAppearanceItem,
} from '@/composables/useShareApi'
import type { OnlineAppearanceItem } from '@/types/appearance'

/** 「我的主题」卡片上的状态：一个外观同一时刻只显示一个主状态。 */
export type MyAppearanceState =
  | { kind: 'published'; published: number }
  | { kind: 'publishedPending'; published: number; latest: number }
  | { kind: 'pending'; latest: number }
  | { kind: 'rejected'; published: number | null; latest: number; comment: string }

export function getMyAppearanceState(item: MyAppearanceItem): MyAppearanceState {
  const published = item.publishedVersionNo
  const latest = item.latestVersionNo
  if (item.latestReviewStatus === 'rejected') {
    return { kind: 'rejected', published, latest, comment: item.latestReviewComment.trim() }
  }
  if (published !== null) {
    if (item.latestReviewStatus === 'pending' && latest !== published) {
      return { kind: 'publishedPending', published, latest }
    }
    return { kind: 'published', published }
  }
  return { kind: 'pending', latest }
}

/** 归档、停用的文件不在公开列表里，只有正常且发布过的才能去商店看。 */
export function isInStore(item: MyAppearanceItem): boolean {
  return item.status === 'active' && item.publishedVersionNo !== null
}

/**
 * 上传对话框默认的目标文件，null 表示新建。
 * 外部指定的目标优先；否则本机记录按外观 ID 命中、且那个文件还在「我的主题」里才选它。
 */
export function pickUploadTarget(options: {
  lockedFileId: number | null
  appearanceId: string | null
  records: AppearanceUploadRecord[]
  mine: MyAppearanceItem[]
}): number | null {
  if (options.lockedFileId !== null) return options.lockedFileId
  if (!options.appearanceId) return null
  const record = options.records.find(item => item.appearanceId === options.appearanceId)
  if (!record) return null
  return options.mine.some(item => item.fileId === record.fileId) ? record.fileId : null
}

/**
 * 不带封面发新版本时分享站会沿用的那张封面：正在查（loading）、查到了（ready）、没有（none）。
 * 分享站沿用的是最近一个未被驳回且带封面的版本，不一定是最新版本，所以要单独查，不能看 latestHasCover。
 */
export type InheritCoverState = 'loading' | 'ready' | 'none'

/**
 * 当前可选的封面来源，按默认优先级排列：
 * 更新且分享站有可沿用的封面（或还在查）时可沿用；包里有预览图时可用预览图；自选图片始终可选。
 */
export function getCoverModes(options: {
  updating: boolean
  inheritCover: InheritCoverState
  packageHasPreview: boolean
}): AppearanceCoverMode[] {
  const modes: AppearanceCoverMode[] = []
  if (options.updating && options.inheritCover !== 'none') modes.push('inherit')
  if (options.packageHasPreview) modes.push('package')
  modes.push('custom')
  return modes
}

/** 选定的封面来源能不能提交：沿用要等查到可沿用的封面，自选图片要真的选了图。 */
export function isCoverReady(
  mode: AppearanceCoverMode,
  modes: AppearanceCoverMode[],
  options: { customPicked: boolean; inheritCover: InheritCoverState }
): boolean {
  if (!modes.includes(mode)) return false
  if (mode === 'inherit') return options.inheritCover === 'ready'
  return mode !== 'custom' || options.customPicked
}

/** 「在商店查看」时先用自己的条目垫一份详情，打开后会被分享站的公开详情替换。 */
export function toStoreItem(item: MyAppearanceItem, ownerUsername: string): OnlineAppearanceItem {
  return {
    fileKey: item.fileKey,
    displayName: item.displayName,
    description: item.description,
    ownerUsername,
    publishedVersionNo: item.publishedVersionNo,
    publishedAt: '',
    updatedAt: item.updatedAt,
    installed: null,
    hasCover: false,
  }
}
