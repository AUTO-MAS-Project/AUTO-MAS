// MFW 用户页各分节的 props / 事件：分节直接用这里的接口 defineProps / defineEmits，专属页
// （views/m9a、views/mss）与通用页按同一组属性与监听使用它们。只放类型，不引入任何组件。

import type { VNode } from 'vue'
import type {
  MaaFWInterfacePreviewData,
  MaaFWPresetInfo,
  MaaFWQueueEntry,
  MaaFWTaskInfo,
  MaaFWTaskOptionValue,
  MaaFWTaskSnapshot,
  MaaFWUserConfig,
} from '@/types/script'
import type { UserAccountHeadingOptions } from '@/types/userEditor'
import type { MaaFWPresetQueueEntry } from '../maafwPresetQueue'
import type { MaaFWQueueSource, MaaFWQueueSourceChip } from '../maafwQueueSource'

/** 用户页表单草稿：用户配置 + 顶部的用户名输入 */
export type MaaFWUserFormData = MaaFWUserConfig & { userName: string }
/** 用户页 `header`：面包屑、打开配置目录、返回（保留既有保存状态入参） */
export interface MaaFWUserHeaderSectionProps {
  saveStatus: 'idle' | 'saving' | 'saved' | 'error'
  saveErrorMessage: string
  scriptId: string
  scriptName: string
  /** 面包屑回脚本页的路由目标（maafwRouteLocation(脚本类型, 'script', { id })） */
  scriptRoute: { name: string; params: { id: string } }
  isEdit: boolean
  userId?: string
  /** 点了「返回」、正在等保存完成或确认框开着：返回按钮转圈 */
  leaving?: boolean
}

export interface MaaFWUserHeaderSectionEmits {
  cancel: []
}

/** 用户页 `basicInfo`：账号标题、用户名、启用状态、账号密码、备注 */
export interface MaaFWUserBasicInfoSectionProps {
  heading?: UserAccountHeadingOptions
  formData: MaaFWUserFormData
  interfaceDependentDisabled: boolean
  /** 账号标签上的问号提示；空串不挂问号 */
  accountRecordTooltip: string
  /** 账号字段占位：M9A 把账号绑成切号任务，文案不再是「仅本地记录」 */
  accountPlaceholder?: string
}

export interface MaaFWUserBasicInfoSectionEmits {
  save: [key: string, value: unknown]
}

/** 「配置导入」里「本脚本其他用户」的一项：同脚本的另一个用户，与它的队列在当前项目下的样子 */
export type MaaFWUserQueueImportCandidate = { userId: string; name: string } & MaaFWQueueSource

/** 用户页 `queueHeader`：「任务队列配置」标题与配置导入 / 配置恢复入口、队列提示、受管任务提示 */
export interface MaaFWUserQueueHeaderSectionProps {
  /** 页面的队列提示，一行一个框（没有就是空数组） */
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
   * 「配置导入」把一份外壳配置写进了用户：页面把实际落盘的任务快照与后端专项一并改掉的用户信息字段
   * （如 M9A 的账号）换进本地状态
   */
  imported: [snapshot: Record<string, unknown>, info: Record<string, unknown>]
}

/** 「添加任务」级联菜单的一项 */
export type AddTaskCascaderOption = {
  value: string
  /** 带 NEW 标记时是 VNode；搜索按 searchText 匹配 */
  label: string | VNode
  /** 任务项含显示名、任务名与入口名（换行分隔），分组项是显示文字 */
  searchText: string
  children?: AddTaskCascaderOption[]
}

/**
 * 预设模板：预设本身 + 其中当前可用的各项。除 `unavailable` 的以外列出来的都能应用；
 * `entries` 可以为空（只有前置任务设置的预设）
 */
export type PresetTemplate = {
  preset: MaaFWPresetInfo
  /** 预设里当前可用的各项，重复任务是各自的实例 id */
  entries: MaaFWPresetQueueEntry[]
  /** 预设启用的前置任务里当前可用的项（预设声明了 `pretask` 才有） */
  pretaskEntries?: MaaFWPresetQueueEntry[]
  /**
   * 预设限定了控制器（PI v2.10.4）且不含当前控制器：照样列出、置灰不让应用。此时
   * `entries` / `pretaskEntries` 按预设自己的控制器算，只用来显示它包含哪些任务
   */
  unavailable?: boolean
}

/** 自定义模板（脚本级，同一脚本的用户共用）：名称 + 它在当前项目下的样子 */
export type MaaFWQueueTemplateView = { name: string } & MaaFWQueueSource

/**
 * 用户页 `taskQueue`：任务队列两栏（左：队列与添加；右：选中任务的选项）。全局选项（项目
 * 声明了才有，每个用户一份、所有任务共用，值在 `taskSnapshot.globalOptions`）是左栏队列框
 * 置顶的一行，选中它时右栏换成全局选项编辑器
 */
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
  /** 受管任务（按 entry）：右栏不给它们显示「运行日」，运行时也不受运行日影响 */
  managedTaskEntries?: ReadonlySet<string>
  /** 任务删除正在落盘：锁定确认按钮，避免前一项未保存完就重复确认删除下一项 */
  deletingTask?: boolean
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
  toggleTaskChecked: [taskId: string]
  moveTask: [taskId: string, direction: -1 | 1]
  taskDragEnd: []
  taskOptionUpdate: [taskId: string, payload: { optionName: string; value: MaaFWTaskOptionValue }]
  /** 改了一项全局选项：页面写进 `taskSnapshot.globalOptions` 并保存 */
  globalOptionUpdate: [payload: { optionName: string; value: MaaFWTaskOptionValue }]
  deleteSelectedTask: []
  deleteTask: [taskId: string]
  /** 队列行右键「复制任务」：在它正下方插一份，勾选、选项与显示名一起复制 */
  duplicateTask: [taskId: string]
  /** 队列行右键「重命名」：改这一份实例的显示名（清空或改回原名即恢复默认） */
  renameTask: [taskId: string, name: string]
  /** 右栏「运行日」改完后的勾选（ISO 星期，1=周一）：空 = 红灯，否则绿灯且只在这几天运行 */
  taskWeekdaysUpdate: [taskId: string, weekdays: number[]]
}
