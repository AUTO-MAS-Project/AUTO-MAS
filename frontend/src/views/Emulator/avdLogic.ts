/**
 * 魔改 AVD 面板的纯逻辑：实例选项表单、开机前检查的分级、组件状态、只给 M9A 用的设备标记。
 *
 * 和界面拆开，是为了能在 node 里直接测；组件只管把结果画出来。
 */
import type {
  Emulator2AvdComponentItem,
  Emulator2AvdInstanceOptionsOut,
  Emulator2AvdPrecheckItem,
} from '@/api'

// ---- 实例选项 ----

/** 实例选项表单。显示固定 720p、不带声卡，不在这里。 */
export interface AvdOptionsForm {
  memoryMb: number
  balloon: boolean
}

/** 内存只收这几档（与后端 ``MEMORY_CHOICES_MB`` 一致）。 */
export const MEMORY_CHOICES_MB = [3072, 4096, 5120, 6144] as const
/** 新建实例默认 6 GB（与后端 ``DEFAULT_MEMORY_MB`` 一致）；核数后端默认 6。 */
export const DEFAULT_MEMORY_MB = 6144
/**
 * 各游戏的推荐内存（GB），只用来提示（与后端 ``RECOMMENDED_MEMORY_MB`` 一致）。
 * 一台实例一轮里可能先后跑好几个游戏，开机后内存改不了，所以不按游戏自动分配。
 */
export const RECOMMENDED_MEMORY_GB = { light: 4, starRail: 5 } as const

export const defaultAvdOptions = (): AvdOptionsForm => ({
  memoryMb: DEFAULT_MEMORY_MB,
  balloon: true,
})

/** 后端返回的实例选项 → 表单。 */
export const optionsFromOut = (out: Emulator2AvdInstanceOptionsOut): AvdOptionsForm => ({
  memoryMb: out.memoryMb || DEFAULT_MEMORY_MB,
  balloon: out.balloon ?? true,
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

/** 新建实例时随请求带上的魔改 AVD 选项。 */
export const createOptions = (form: AvdOptionsForm) => ({
  memoryMb: form.memoryMb,
  balloon: form.balloon,
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

// ---- 魔改 AVD 只给 M9A ----

/** 设备下拉里的一项（各脚本编辑页共用的形状，同 ``ComboBoxItem``）。 */
export interface DeviceOption {
  label: string
  value: string | null
}

/**
 * 魔改 AVD 目前只支持 M9A：不支持的脚本，设备下拉里的魔改 AVD 实例置灰并在名称后写明原因。
 * ``isModAvd`` 判断某个设备号是不是魔改 AVD；``allowed`` 为 true（M9A）时原样返回。
 * 后端保存与运行时也会拦，这里只是让用户选之前就看到。
 */
export const markModAvdOptions = <T extends DeviceOption>(
  options: T[],
  isModAvd: (value: string | null) => boolean,
  allowed: boolean,
  hint: string
): (T & { disabled?: boolean })[] => {
  if (allowed) return options
  return options.map(option =>
    isModAvd(option.value)
      ? { ...option, label: `${option.label}（${hint}）`, disabled: true }
      : option
  )
}
