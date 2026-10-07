// MFW 页面分节的契约：每个分节收什么 props、发什么事件。MFW 的默认分节直接用这里的接口
// defineProps / defineEmits，所以这里就是唯一的事实来源；特调替换某个分节时（descriptor 的
// scriptPage.sections / userPage.sections / create.sections，用 defineMaaFWSection 声明），替换组件
// 必须能接受对应契约里的全部 props——页面对默认分节和替换分节传的是同一组属性与监听。
//
// 这里只放类型，不引入任何组件：注册表（会被路由、脚本列表引入）通过它取类型，不能带上页面代码。

import type { VNode } from 'vue'
import type { ComboBoxItem, MaaFWShellInstanceItem } from '@/api'
import type { MaaFWFlavorType, MaaFWUserFormData } from '@/composables/maafwFlavorTypes'
import type { MaaFWEmbeddedStatus } from '@/composables/useMaaFWEmbeddedApi'
import type { EmulatorType } from '@/composables/useMaaFWScriptConfig'
import type { MaaFWUpdateResult } from '@/composables/useMaaFWUpdateApi'
import type {
  MaaFWControllerInfo,
  MaaFWInterfacePreviewData,
  MaaFWPresetInfo,
  MaaFWQueueEntry,
  MaaFWResourceInfo,
  MaaFWScriptConfig,
  MaaFWTaskInfo,
  MaaFWTaskOptionValue,
  MaaFWTaskSnapshot,
  ScriptType,
} from '@/types/script'
import type { MfwReuseChoice } from '@/views/scripts/components/scriptCreateFlow'
import type { MaaFWUpdateProgressState } from '../Script/MaaFWScriptEdit/updateProgress'
import type { MaaFWPresetQueueEntry } from '../User/maafwPresetQueue'
import type { MaaFWQueueSource, MaaFWQueueSourceChip } from '../User/maafwQueueSource'

// ════════════════════════════ 脚本页 ════════════════════════════

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
  /** flavor 文案（特调类型传入）；缺省用通用 MaaFW 的「本地项目目录」那套 */
  sourceDirectoryLabel?: string
  sourceHint?: string
  sourcePlaceholder?: string
}

export interface MaaFWScriptBasicInfoSectionEmits {
  change: MaaFWScriptChangeEmit
  'select-path': []
  'preview-interface': []
}

/**
 * 脚本页 `control`：控制器、资源、模拟器 / 桌面窗口、游戏启动。另有具名 slot `besidePackageName`
 * （与游戏包名并排，有内容时两列），页面在当前特调登记了同名插入点时才填它；替换这个分节要保留它。
 */
export interface MaaFWScriptControlSectionProps {
  /** 脚本 ID：键位映射弹窗「从项目导入」按它读外壳配置实例 */
  scriptId: string
  maafwConfig: MaaFWScriptConfig
  previewData: MaaFWInterfacePreviewData | null
  interfaceLoading: boolean
  emulatorLoading: boolean
  emulatorOptionsReady: boolean
  emulatorDeviceLoading: boolean
  emulatorOptions: ComboBoxItem[]
  emulatorDeviceOptions: ComboBoxItem[]
  emulatorTypeById: Record<string, EmulatorType>
  controllerOptions: MaaFWControllerInfo[]
  effectiveControllerName: string
  effectiveControllerType: string
  isAdbController: boolean
  isDesktopController: boolean
  resourceOptions: MaaFWResourceInfo[]
  /** 实际生效的资源（Info.Resource 不在可选列表里时退回第一个），键位映射按它挑 option */
  effectiveResourceName: string
  adbControlStrategyItems: Array<{ label: string; value: string }>
  selectedEmulatorLabel: string
  interfaceDependentDisabled: boolean
}

export interface MaaFWScriptControlSectionEmits {
  change: MaaFWScriptChangeEmit
  'controller-change': []
  'resource-change': []
  'emulator-select-change': [emulatorId: string]
  'select-launch-path': []
}

/** 脚本页 `update`：项目更新来源、渠道、CDK 与检查 / 应用 */
export interface MaaFWScriptUpdateSectionProps {
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

/** 脚本页分节键 → props 契约 */
export interface MaaFWScriptSectionContracts {
  basicInfo: MaaFWScriptBasicInfoSectionProps
  control: MaaFWScriptControlSectionProps
  update: MaaFWScriptUpdateSectionProps
  run: MaaFWScriptRunSectionProps
  shellImport: MaaFWScriptShellImportSectionProps
}

// ════════════════════════════ 用户页 ════════════════════════════

/** 用户页 `header`：面包屑、保存状态、打开配置目录、返回 */
export interface MaaFWUserHeaderSectionProps {
  saveStatus: 'idle' | 'saving' | 'saved' | 'error'
  saveErrorMessage: string
  scriptId: string
  scriptName: string
  /** 面包屑回脚本页的路由目标（maafwRouteLocation(脚本类型, 'script', { id })） */
  scriptRoute: { name: string; params: { id: string } }
  isEdit: boolean
  userId?: string
}

export interface MaaFWUserHeaderSectionEmits {
  cancel: []
}

/** 用户页 `basicInfo`：用户名、启用状态、账号密码、备注 */
export interface MaaFWUserBasicInfoSectionProps {
  formData: MaaFWUserFormData
  interfaceDependentDisabled: boolean
  accountRecordTooltip: string
  /** 账号字段占位：特调类型可能把账号绑成切号任务，文案不再是「仅本地记录」 */
  accountPlaceholder?: string
}

export interface MaaFWUserBasicInfoSectionEmits {
  save: [key: string, value: unknown]
}

/** 「配置导入」里「本脚本其他用户」的一项：同脚本的另一个用户，与它的队列在当前项目下的样子 */
export type MaaFWUserQueueImportCandidate = { userId: string; name: string } & MaaFWQueueSource

/** 用户页 `queueHeader`：「任务队列配置」标题与配置导入 / 配置恢复入口、队列提示、受管任务提示 */
export interface MaaFWUserQueueHeaderSectionProps {
  /** 特调的队列提示，一行一个框（没有就是空数组） */
  queueHintLines: string[]
  /** 队列里残留受管任务时的提示；没有为 null */
  managedQueueAlert: { type: 'warning' | 'info'; message: string } | null
  /** 「配置导入」→「本脚本其他用户」：队列不为空的其他用户（打开弹窗时页面现取，见 load-user-import） */
  userImportCandidates: MaaFWUserQueueImportCandidate[]
  userImportLoading: boolean
}

export interface MaaFWUserQueueHeaderSectionEmits {
  /** 点了「配置恢复」：页面打开恢复弹窗 */
  'open-restore': []
  /** 打开了「配置导入」：页面取一次本脚本的用户列表 */
  'load-user-import': []
  /** 「配置导入」选了本脚本的另一个用户：页面用它的队列覆盖当前队列（只换任务队列） */
  'import-from-user': [userId: string]
  /**
   * 「配置导入」把一份外壳配置写进了用户：页面把实际落盘的任务快照与特调一并改掉的用户信息字段
   * （如 M9A 的账号）换进本地状态
   */
  imported: [snapshot: Record<string, unknown>, info: Record<string, unknown>]
}

/** 「添加任务」级联菜单的一项 */
export type AddTaskCascaderOption = {
  value: string
  /** 带 NEW 标记时是 VNode；搜索按 searchText 匹配 */
  label: string | VNode
  searchText: string
  children?: AddTaskCascaderOption[]
}

/** 预设模板：预设本身 + 其中当前可用的各项 */
export type PresetTemplate = {
  preset: MaaFWPresetInfo
  /** 预设里当前可用的各项，重复任务是各自的实例 id */
  entries: MaaFWPresetQueueEntry[]
}

/** 自定义模板（脚本级，同一脚本的用户共用）：名称 + 它在当前项目下的样子 */
export type MaaFWQueueTemplateView = { name: string } & MaaFWQueueSource

/** 用户页 `taskQueue`：任务队列两栏（左：队列与添加；右：选中任务的选项） */
export interface MaaFWUserTaskQueueSectionProps {
  interfaceLoading: boolean
  previewData: MaaFWInterfacePreviewData | null
  interfaceDependentDisabled: boolean
  availableTasks: MaaFWTaskInfo[]
  orderedTasks: MaaFWQueueEntry[]
  addTaskCascaderValue: string[]
  addTaskCascaderOptions: AddTaskCascaderOption[]
  /** 「添加任务」里有用户没见过的任务：输入框后缀显示 NEW 而不是加号 */
  hasNewTasks: boolean
  presetTemplates: PresetTemplate[]
  /** 「模板」→「我的模板」：本脚本的自定义模板 */
  queueTemplates: MaaFWQueueTemplateView[]
  /** 「存为模板」要存的任务：当前队列去掉虚影与受管任务 */
  queueTemplateDraft: MaaFWQueueSourceChip[]
  /** 「模板」弹窗是否打开 */
  showPresetModal: boolean
  taskByName: Map<string, MaaFWTaskInfo>
  selectedTask: MaaFWTaskInfo | null
  selectedTaskId: string
  taskSnapshot: MaaFWTaskSnapshot
  effectiveControllerName: string
  effectiveResourceName: string
}

export interface MaaFWUserTaskQueueSectionEmits {
  'update:addTaskCascaderValue': [value: string[]]
  'update:showPresetModal': [value: boolean]
  addTaskCascaderChange: [value: unknown]
  applyPresetTemplate: [presetName: string]
  /** 把当前队列存成模板（名称已去首尾空格、不与已有模板同名） */
  saveQueueTemplate: [name: string]
  /** 套用模板：直接替换队列，失效任务跳过 */
  applyQueueTemplate: [name: string]
  renameQueueTemplate: [name: string, nextName: string]
  deleteQueueTemplate: [name: string]
  reorderTasks: [taskIds: string[]]
  selectTask: [taskId: string]
  moveTask: [taskId: string, direction: -1 | 1]
  taskDragEnd: []
  taskOptionUpdate: [taskId: string, payload: { optionName: string; value: MaaFWTaskOptionValue }]
  deleteSelectedTask: []
  deleteTask: [taskId: string]
}

/** 用户页分节键 → props 契约 */
export interface MaaFWUserSectionContracts {
  header: MaaFWUserHeaderSectionProps
  basicInfo: MaaFWUserBasicInfoSectionProps
  queueHeader: MaaFWUserQueueHeaderSectionProps
  taskQueue: MaaFWUserTaskQueueSectionProps
}

// ════════════════════════════ 新建流程 ════════════════════════════

/**
 * 新建流程 `source`：MFW 家族第二步「项目从哪来」的选项（新建一个别的项目 / 复用已导入的项目）。
 * 选中状态归对话框所有（返回再进来照样保留，列表变了选中的源失效时由对话框退回 'new'），
 * 分节只负责显示与交回选择。
 */
export interface MaaFWCreateSourceSectionProps {
  /** 选中的类型卡片：只列与它同类型的项目 */
  type: MaaFWFlavorType
  /** 可复用的项目（已按类型筛好、同一项目并成一行） */
  choices: MfwReuseChoice[]
  /** 候选列表正在读 */
  loading: boolean
  /** 候选列表没读出来的原因；有值就显示错误条 + 重试 */
  error: string | null
  /** 'new' = 新建一个别的项目；否则是要复用的项目所属脚本的 id */
  value: string
}

export interface MaaFWCreateSourceSectionEmits {
  'update:value': [value: string]
  /** 点了错误条上的「重试」：对话框重新读候选列表 */
  retry: []
}

/** 新建流程分节键 → props 契约 */
export interface MaaFWCreateSectionContracts {
  source: MaaFWCreateSourceSectionProps
}

/** 各部分的分节契约 */
export interface MaaFWSectionContractMap {
  scriptPage: MaaFWScriptSectionContracts
  userPage: MaaFWUserSectionContracts
  create: MaaFWCreateSectionContracts
}
