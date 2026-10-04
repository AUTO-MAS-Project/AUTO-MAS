/**
 * 官方模拟器（AVD）面板的纯逻辑：实例选项表单、开机前检查的分级、组件下载任务的状态判断。
 *
 * 和界面拆开，是为了能在 node 里直接测；组件只管把结果画出来。
 */
import type {
  Emulator2AvdComponentItem,
  Emulator2AvdInstanceOptionsOut,
  Emulator2AvdPrecheckItem,
  Emulator2SettingField,
  WSEmulator2AvdInstallProgressData,
} from '@/api'

// ---- 实例选项 ----

export type AvdResolution = '720' | '1080'

/** 实例选项表单。``memoryMb`` 为 {@link MEMORY_AUTO} 时表示按游戏自动。 */
export interface AvdOptionsForm {
  resolution: AvdResolution
  memoryMb: number
  balloon: boolean
  guestAngle: boolean
  headless: boolean
}

/** 内存「按游戏自动」在表单里的值；后端 ``options/set`` 收 0 也是这个意思。 */
export const MEMORY_AUTO = 0
/** 手动指定内存时只收这几档（与后端 ``MEMORY_CHOICES_MB`` 一致）。 */
export const MEMORY_CHOICES_MB = [3072, 4096, 5120, 6144] as const

export const defaultAvdOptions = (): AvdOptionsForm => ({
  resolution: '720',
  memoryMb: MEMORY_AUTO,
  balloon: true,
  guestAngle: false,
  headless: true,
})

/** 后端返回的实例选项 → 表单。按游戏自动时 ``memoryMb`` 只是兜底值，表单里记成自动。 */
export const optionsFromOut = (out: Emulator2AvdInstanceOptionsOut): AvdOptionsForm => ({
  resolution: out.resolution === '1080' ? '1080' : '720',
  memoryMb: out.memoryAuto === false && out.memoryMb ? out.memoryMb : MEMORY_AUTO,
  balloon: out.balloon ?? true,
  guestAngle: out.guestAngle ?? false,
  headless: out.headless ?? true,
})

/** 只提交改过的项；后端对没传的项不做改动。 */
export const optionsChanges = (
  baseline: AvdOptionsForm,
  form: AvdOptionsForm
): Partial<AvdOptionsForm> => {
  const changes: Partial<AvdOptionsForm> = {}
  for (const key of Object.keys(form) as (keyof AvdOptionsForm)[]) {
    if (form[key] !== baseline[key]) {
      ;(changes as Record<string, unknown>)[key] = form[key]
    }
  }
  return changes
}

/** 新建实例时随请求带上的官方模拟器选项。自动内存不传（后端留空即按游戏自动）。 */
export const createOptions = (form: AvdOptionsForm) => ({
  resolution: form.resolution,
  memoryMb: form.memoryMb === MEMORY_AUTO ? null : form.memoryMb,
  balloon: form.balloon,
  guestAngle: form.guestAngle,
  headless: form.headless,
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

// ---- 组件与下载 ----

/** 根目录比较：Windows 路径不分大小写，斜杠方向与结尾斜杠不算区别。 */
export const samePath = (a: string | undefined | null, b: string | undefined | null) => {
  const normalize = (value: string) =>
    value.trim().replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase()
  if (!a || !b) return false
  return normalize(a) === normalize(b)
}

export const isJobRunning = (job: WSEmulator2AvdInstallProgressData | null | undefined) =>
  job?.status === 'running'

/** 组件缺着、而且已经下过一部分（上次取消 / 失败）：按钮显示「继续下载」。 */
export const canResume = (
  components: Emulator2AvdComponentItem[] | undefined,
  job: WSEmulator2AvdInstallProgressData | null | undefined
) => {
  if (isJobRunning(job)) return false
  if (job && (job.status === 'failed' || job.status === 'cancelled')) return true
  return (components ?? []).some(item => !item.installed && (item.downloadedBytes ?? 0) > 0)
}

/**
 * 组件行的状态：ready 已就绪 / partial 下了一部分 / missing 没下 /
 * needsPackage 模拟器不下载，要官方模拟器内测包（没有或不是自编版）
 */
export const componentState = (item: Emulator2AvdComponentItem) => {
  if (item.installed) return 'ready' as const
  if (item.needsTestPackage) return 'needsPackage' as const
  if ((item.downloadedBytes ?? 0) > 0) return 'partial' as const
  return 'missing' as const
}

/**
 * 组件行要显示的版本与大小。已就绪的组件报实际装着的版本、不报大小（已经不用下了）；来自内测包或
 * 本地 SDK 的另外标出来。没就绪的报要下载的固定版本和下载大小；模拟器不下载，没有大小可报。
 */
export const componentDetail = (item: Emulator2AvdComponentItem) => {
  const installed = componentState(item) === 'ready'
  return {
    version: item.version ?? '',
    sizeBytes: installed ? null : (item.sizeBytes ?? 0) || null,
    localSdk: installed && Boolean(item.localSdk),
    testPackage: installed && Boolean(item.testPackage),
  }
}

/** 这个根目录是不是已经在配置里了（路径写法不同也算同一个）。 */
export const isRootAdded = (addedRoots: string[], root: string) =>
  addedRoots.some(item => samePath(item, root))

// ---- 设备表 ----

/**
 * 设备表「内存」一栏：官方模拟器选了按游戏自动时后端报 ``state: 'auto'``、没有值，显示「按游戏」；
 * 其余照旧显示数字，没值显示破折号。
 */
export const memoryCell = (
  field: Emulator2SettingField | undefined
): { auto: true } | { auto: false; text: string } => {
  if (field?.state === 'auto') return { auto: true }
  const value = field?.value
  return { auto: false, text: value === null || value === undefined ? '—' : String(value) }
}

/** 下载任务整体进度（0–100）。解压阶段按当前组件的解压进度显示；不知道时为 null。 */
export const jobPercent = (job: WSEmulator2AvdInstallProgressData | null | undefined) => {
  if (!job) return null
  if (job.status === 'success') return 100
  if (job.stage === 'extracting' && typeof job.extractPercent === 'number') {
    return Math.round(job.extractPercent)
  }
  if (typeof job.percent === 'number') return Math.round(job.percent)
  return null
}
