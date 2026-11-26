// MFW 脚本页各分节的 props / 事件：分节直接用这里的接口 defineProps / defineEmits，专属页
// （views/m9a、views/mss）与通用页按同一组属性与监听使用它们。只放类型，不引入任何组件。

import type { MaaFWShellInstanceItem } from '@/api'
import type { MaaFWEmbeddedStatus } from '@/composables/useMaaFWEmbeddedApi'
import type { MaaFWUpdateResult } from '@/composables/useMaaFWUpdateApi'
import type {
  MaaFWControllerInfo,
  MaaFWInterfacePreviewData,
  MaaFWResourceInfo,
  MaaFWScriptConfig,
  ScriptType,
} from '@/types/script'
import type { MaaFWUpdateProgressState } from './updateProgress'
/** 脚本页各分节共用的落盘事件：页面按 category.key 写回脚本配置（初始化期间不落盘） */
type MaaFWScriptChangeEmit = [category: keyof MaaFWScriptConfig, key: string, value: unknown]

/** 一次运行环境准备的结果：首次准备 / 更新了已有环境 / 项目没变直接沿用。 */
export type MaaFWEnvOutcome = 'prepared' | 'updated' | 'cached'

/** 脚本页 `basicInfo`：名称、项目目录与导入、interface 概览、运行环境 */
export interface MaaFWScriptBasicInfoSectionProps {
  maafwConfig: MaaFWScriptConfig
  formData: { type: ScriptType; name: string; path: string }
  rules: { name: unknown[]; path: unknown[] }
  previewData: MaaFWInterfacePreviewData | null
  interfaceLoading: boolean
  previewProjectTitle: string
  interfaceStats: Array<{ label: string; value: number }>
  /** 项目更新正在落盘：此时读 interface 会读到半成品，按钮一律禁用。 */
  updateApplying: boolean
  envPreparing: boolean
  envReady: boolean
  envFailed: boolean
  /** 准备中是后端当前阶段那句话；成功后是 MaaFramework 版本；失败时是错误原因。 */
  envMessage: string
  envPercent: number | null
  envLogs: string[]
  envAgents: Array<{ runtimeKind?: string | null; executable: string }>
  envOutcome: MaaFWEnvOutcome | null
  /** 内嵌副本状态：由父组件从后端拉取；导入几十到几百 MB 时 busy 为 true。 */
  embeddedStatus: MaaFWEmbeddedStatus
  embeddedBusy: boolean
  /** 导入进度：后端按文件数推过来的百分比与阶段文案；没有推送时为 null，进度条显示 0 */
  importPercent: number | null
  importMessage: string
  /** 最近一次导入 / 同步失败的原因；下次导入开始时清空 */
  importError?: string
  /** 最近一次读 interface 失败的原因（此时 previewData 为 null）；下次读取开始时清空 */
  previewError?: string
  /** 专属页的文案（M9A、MSS 传入）；缺省用通用 MFW 的「本地项目目录」那套 */
  sourceDirectoryLabel?: string
  sourceHint?: string
  sourcePlaceholder?: string
  /** 新建后的引导形态：环境准备失败的提示不指向本页后面步骤里的设置 */
  isWizard?: boolean
}

export interface MaaFWScriptBasicInfoSectionEmits {
  change: MaaFWScriptChangeEmit
  'select-path': []
  'preview-interface': []
  /** 跟随来源目录时点了「立即同步」：页面按当前来源目录强制重导 */
  'sync-source': []
}

/**
 * 脚本页 `control`：控制器、资源、模拟器 / 桌面窗口、游戏启动。另有具名作用域 slot
 * `besidePackageName`（ADB 下排在包名、等待时间之后，每个组件一格）：专属页要在这里多放字段时
 * 才填它，并用 `besidePackageNameCount` 传格数；分节按这个数每格转发一次 slot、带上
 * `{ index }`，页面渲染第 index 格（如 M9A 的登录方式、游戏更新）。
 */
export interface MaaFWScriptControlSectionProps {
  /** 脚本 ID：键位映射弹窗「从项目导入」按它读外壳配置实例 */
  scriptId: string
  maafwConfig: MaaFWScriptConfig
  previewData: MaaFWInterfacePreviewData | null
  interfaceLoading: boolean
  controllerOptions: MaaFWControllerInfo[]
  effectiveControllerName: string
  effectiveControllerType: string
  isAdbController: boolean
  isDesktopController: boolean
  resourceOptions: MaaFWResourceInfo[]
  /** 实际生效的资源（Info.Resource 不在可选列表里时退回第一个），键位映射按它挑 option */
  effectiveResourceName: string
  adbControlStrategyItems: Array<{ label: string; value: string }>
  interfaceDependentDisabled: boolean
  /** besidePackageName 要占几格；不传或为 0 时不留这一格 */
  besidePackageNameCount?: number
}

export interface MaaFWScriptControlSectionEmits {
  change: MaaFWScriptChangeEmit
  'controller-change': []
  'resource-change': []
  'select-launch-path': []
  /** 由脚本控制游戏时选启动器 exe（MAS 兜底关闭时一并关它） */
  'select-launcher-path': []
}

/** 脚本页 `update`：项目更新来源、渠道、CDK 与检查 / 应用 */
export interface MaaFWScriptUpdateSectionProps {
  /** 脚本 ID：CDK 输入框下那行剩余时间 / CDK 状态按它查 */
  scriptId: string
  maafwConfig: MaaFWScriptConfig
  previewData: MaaFWInterfacePreviewData | null
  isAutoUpdateDisabled: boolean
  updateChecking: boolean
  updateApplying: boolean
  updateError: string
  updateResult: MaaFWUpdateResult | null
  updateProgress: MaaFWUpdateProgressState
  /** 本次进入页面时 CDK 是从 MAS 更新设置里自动填入的 */
  cdkPrefilled: boolean
  updateSourceOptions: Array<{ label: string; value: string }>
  updateChannelOptions: Array<{ label: string; value: string }>
}

export interface MaaFWScriptUpdateSectionEmits {
  change: MaaFWScriptChangeEmit
  'check-update': []
  'apply-update': []
}

/** 脚本页 `run`：运行参数、单任务时限与每日 / 每周 / 每月只跑一次的任务 */
export interface MaaFWScriptRunSectionProps {
  maafwConfig: MaaFWScriptConfig
  dailyOnceTasks: string[]
  weeklyOnceTasks: string[]
  monthlyOnceTasks: string[]
  /** interface 里的任务（去掉 pretask 伪任务）：周期跳过下拉与「按任务设置时限」弹窗共用 */
  periodTaskOptions: Array<{ label: string; value: string }>
  interfaceDependentDisabled: boolean
}

export interface MaaFWScriptRunSectionEmits {
  change: MaaFWScriptChangeEmit
  'period-task-change': [
    key: 'DailyOnceTasks' | 'WeeklyOnceTasks' | 'MonthlyOnceTasks',
    values: string[],
  ]
}

/** 脚本页 `shellImport`：引导最后一步，把外壳里配好的实例导入成用户 */
export interface MaaFWScriptShellImportSectionProps {
  instances: MaaFWShellInstanceItem[]
  selectedIds: string[]
  /** 「同时把键位导入到脚本」：选中的实例里有带键位的才显示这个开关，默认开 */
  importHotkeys: boolean
  disabled?: boolean
}

export interface MaaFWScriptShellImportSectionEmits {
  'update:selectedIds': [ids: string[]]
  'update:importHotkeys': [value: boolean]
}
