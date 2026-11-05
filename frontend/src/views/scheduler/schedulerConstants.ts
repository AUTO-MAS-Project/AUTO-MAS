import { TaskMode } from '@/api'
import { PowerIn } from '@/api/models/PowerIn'
import type { TaskScopeDraft } from '@/composables/taskSelection'

// 调度台状态
export type SchedulerStatus = '空闲' | '运行' | '结束' | '异常'

// 新增：任务总览数据类型
export interface User {
  user_id: string
  status: string
  name: string
}

export interface Script {
  script_id: string
  status: string
  name: string
  nameKey?: string
  user_list: User[]
}

// 状态颜色映射
export const TAB_STATUS_COLOR: Record<SchedulerStatus, string> = {
  空闲: 'default',
  运行: 'processing',
  结束: 'success',
  异常: 'error',
}

// 运行模式标签（直接复用后端枚举值）
export const TASK_MODE_LABEL_KEYS: Record<TaskMode, string> = {
  [TaskMode.AUTO_PROXY]: 'core.scheduler.mode.autoProxy',
  [TaskMode.SCRIPT_CONFIG]: 'core.scheduler.mode.scriptConfig',
  [TaskMode.SCRIPT_VIEW]: 'core.scheduler.mode.scriptView',
}

export const TASK_MODE_OPTIONS = [
  { labelKey: 'core.scheduler.mode.autoProxy', value: TaskMode.AUTO_PROXY },
]

// 电源操作 -> 词表 key（信号值本身是后端枚举，不动）
export const POWER_ACTION_LABEL_KEY: Record<PowerIn.signal, string> = {
  [PowerIn.signal.NO_ACTION]: 'core.scheduler.power.noAction',
  [PowerIn.signal.SHUTDOWN]: 'core.scheduler.power.shutdown',
  [PowerIn.signal.SHUTDOWN_FORCE]: 'core.scheduler.power.shutdownForce',
  [PowerIn.signal.REBOOT]: 'core.scheduler.power.reboot',
  [PowerIn.signal.HIBERNATE]: 'core.scheduler.power.hibernate',
  [PowerIn.signal.SLEEP]: 'core.scheduler.power.sleep',
  [PowerIn.signal.KILL_SELF]: 'core.scheduler.power.killSelf',
  [PowerIn.signal.RESTART_SELF]: 'core.scheduler.power.restartSelf',
  [PowerIn.signal.LOGOFF]: 'core.scheduler.power.logoff',
}
/** 调度台只保存界面与启动草稿，运行数据由 taskId 引用。 */
export interface SchedulerTab {
  key: string
  title: string
  titleNumber?: number
  closable: boolean
  selectedTaskId: string | null
  selectedMode: TaskMode | null
  scope?: TaskScopeDraft
  scopeLoading?: boolean
  scopeError?: string
  starting?: boolean
  taskId: string | null
}
