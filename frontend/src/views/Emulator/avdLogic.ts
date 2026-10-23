/**
 * 魔改 AVD 面板的纯逻辑：新建实例的选项、开机前检查的分级、组件状态、更新区的按钮。
 *
 * 和界面拆开，是为了能在 node 里直接测；组件只管把结果画出来。
 */
import type {
  Emulator2AvdChangeEntry,
  Emulator2AvdComponentItem,
  Emulator2AvdPrecheckItem,
  Emulator2AvdUpdateStatusOut,
} from '@/api'

// ---- 实例选项 ----

/** 新建实例时的选项。显示固定 720p、不带声卡、气球固定开，不在这里；核数用后端默认。 */
export interface AvdOptionsForm {
  memoryMb: number
  fps: number
}

/** 内存只收这几档（与后端 ``MEMORY_CHOICES_MB`` 一致）。 */
export const MEMORY_CHOICES_MB = [3072, 4096, 5120, 6144] as const
/** 新建实例默认 6 GB（与后端 ``DEFAULT_MEMORY_MB`` 一致）；核数后端默认 6。 */
export const DEFAULT_MEMORY_MB = 6144
/** 帧率只收这两档（与后端 ``FPS_CHOICES`` 一致），默认 60（``DEFAULT_FPS``）。 */
export const FPS_CHOICES = [30, 60] as const
export const DEFAULT_FPS = 60
/**
 * 推荐内存（GB），只用来提示（与后端 ``RECOMMENDED_MEMORY_MB`` 一致）。只给实测过内存的
 * 1999 的推荐值；开机后内存改不了，所以不按游戏自动分配。
 */
export const RECOMMENDED_MEMORY_GB = { reverse1999: 4 } as const

export const defaultAvdOptions = (): AvdOptionsForm => ({
  memoryMb: DEFAULT_MEMORY_MB,
  fps: DEFAULT_FPS,
})

/** 新建实例时随请求带上的魔改 AVD 选项。 */
export const createOptions = (form: AvdOptionsForm) => ({
  memoryMb: form.memoryMb,
  fps: form.fps,
})

// ---- 开机前检查 ----

/** ok 通过 / error 不满足且会拒绝开机 / warning 不满足但只提示 / unknown 现在查不了 */
export type PrecheckLevel = 'ok' | 'error' | 'warning' | 'unknown'

export const precheckLevel = (item: Emulator2AvdPrecheckItem): PrecheckLevel => {
  if (item.ok === true) return 'ok'
  if (item.ok === false) return item.blocking === false ? 'warning' : 'error'
  return 'unknown'
}

/** 有没有会拒绝开机的项。 */
export const hasBlockingFailure = (items: Emulator2AvdPrecheckItem[] | undefined) =>
  (items ?? []).some(item => precheckLevel(item) === 'error')

// ---- 组件 ----

/** 根目录比较：Windows 路径不分大小写，斜杠方向与结尾斜杠不算区别。 */
export const samePath = (a: string | undefined | null, b: string | undefined | null) => {
  const normalize = (value: string) =>
    value.trim().replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase()
  if (!a || !b) return false
  return normalize(a) === normalize(b)
}

/**
 * 组件行的状态：ready 已就绪 / missing 缺着 /
 * needsPackage 模拟器没有、不是自编版或内测包太旧（要换完整的内测包）
 */
export const componentState = (item: Emulator2AvdComponentItem) => {
  if (item.installed) return 'ready' as const
  if (item.needsTestPackage) return 'needsPackage' as const
  return 'missing' as const
}

/** 组件行要显示的版本与来源。来自内测包或本地 SDK 的另外标出来（只对已就绪的组件）。 */
export const componentDetail = (item: Emulator2AvdComponentItem) => {
  const installed = componentState(item) === 'ready'
  return {
    version: item.version ?? '',
    localSdk: installed && Boolean(item.localSdk),
    testPackage: installed && Boolean(item.testPackage),
    /** 内测包编号（``mas-19``），只有自编版才有 */
    build: item.build ?? '',
    /** 是自编版但内测包编号太旧或读不到 */
    outdated: Boolean(item.outdatedTestPackage),
  }
}

/** 这个根目录是不是已经在配置里了（路径写法不同也算同一个）。 */
export const isRootAdded = (addedRoots: string[], root: string) =>
  addedRoots.some(item => samePath(item, root))

// ---- 更新 ----

/** 版本的显示写法：``mas-33（v33.0.0）``；只有一样时就显示那一样。 */
export const versionLabel = (build?: string | null, version?: string | null) =>
  build && version ? `${build}（${version}）` : build || version || ''

/** 还能取消的阶段（换上一旦开始就不能取消）。 */
const CANCELLABLE_STAGES = new Set(['downloading', 'extracting', 'verifying'])

/** 更新区里哪几个按钮能点。 */
export const updateActions = (status: Emulator2AvdUpdateStatusOut) => {
  const busy = Boolean(status.busy)
  const updatable = Boolean(status.updatable)
  const prepared = status.phase === 'staged' && Boolean(status.preparedVersion)
  return {
    // 已经拼好最新版就不用再下；拼好的是旧一些的版本（之后又出了新版）时可以重下
    download:
      !busy &&
      updatable &&
      Boolean(status.updateAvailable) &&
      !status.requiredAutoMas &&
      !(prepared && status.preparedVersion === status.latestVersion),
    cancel: busy && CANCELLABLE_STAGES.has(status.progress?.stage ?? ''),
    install: !busy && updatable && prepared,
    rollback: !busy && updatable && Boolean(status.canRollback),
  }
}

/** 跳了几版才把机读行里各版的摘要合起来显示：只新一版时，公告正文里已经写着同样的内容。 */
export const showMergedChanges = (changes: Emulator2AvdChangeEntry[] | undefined) =>
  (changes ?? []).length > 1

/** 路径卡片上的更新标记：低于最低要求 → 需要更新；有新版本 → 有新版本；否则不标。 */
export const updateBadge = (status: Emulator2AvdUpdateStatusOut) => {
  if (!status.updatable) return null
  if (status.belowMinimum) return { kind: 'outdated' as const, version: status.minimumBuild ?? '' }
  if (status.updateAvailable)
    return { kind: 'available' as const, version: status.latestBuild ?? '' }
  return null
}
