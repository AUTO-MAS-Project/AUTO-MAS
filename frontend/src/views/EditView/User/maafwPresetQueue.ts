import { resolveMaaFWTaskName } from '@/utils/maafwTaskInstance'
import type {
  MaaFWTaskInfo,
  MaaFWTaskOptionValue,
  MaaFWTaskSchedule,
  MaaFWTaskSnapshot,
} from '@/types/script'
import {
  pickMaaFWTaskLabels,
  pickMaaFWTaskSchedules,
  taskLabelsField,
  taskSchedulesField,
} from './MaaFWUserEdit/maafwTaskSnapshot'

type TaskNameLookup = { has: (value: string) => boolean }

/** 预设里的一项：`id` 是任务实例 id，同一任务在预设里第二次起是 `<任务名>__MAS_DUP__presetN`。 */
export type MaaFWPresetQueueEntry = {
  id: string
  task: MaaFWTaskInfo
}

/**
 * 预设快照（已按勾选过滤）里当前 controller / resource 下可用的项，保持预设顺序。
 *
 * 必须先把实例 id 解析回任务名再判断可用性：后端把预设里重复出现的任务展开成
 * 实例 id（MRA「周常配置」把「自动出征」排了 9 次，每次选项不同），拿实例 id 直接
 * 按任务名查会把第二次起的全部滤掉。
 */
export const selectPresetQueueEntries = (
  taskOrder: readonly string[],
  activeTaskByName: ReadonlyMap<string, MaaFWTaskInfo>,
  validTaskNames: TaskNameLookup
): MaaFWPresetQueueEntry[] => {
  const entries: MaaFWPresetQueueEntry[] = []
  const seen = new Set<string>()
  for (const taskId of taskOrder) {
    if (seen.has(taskId)) continue
    const task = activeTaskByName.get(resolveMaaFWTaskName(taskId, validTaskNames))
    if (!task) continue
    seen.add(taskId)
    entries.push({ id: taskId, task })
  }
  return entries
}

/**
 * 应用预设后的队列快照：原队列里的前置任务（pretask）保留在最前，其余换成预设的各个
 * 实例，每个实例带预设给它的那一套选项；`taskLabels` 给的实例显示名与 `taskSchedules` 给的
 * 运行日按同一份实例 id 带上（项目预设两样都没有）。
 */
export const buildPresetAppliedSnapshot = (
  entries: readonly MaaFWPresetQueueEntry[],
  presetTaskOptions: Record<string, Record<string, MaaFWTaskOptionValue>>,
  currentTaskOrder: readonly string[],
  isPretaskId: (taskId: string) => boolean,
  taskLabels: Record<string, string> = {},
  taskChecked: Record<string, boolean> = {},
  taskSchedules: Record<string, MaaFWTaskSchedule> = {}
): MaaFWTaskSnapshot => {
  const candidateIds = [
    ...currentTaskOrder.filter(taskId => isPretaskId(taskId)),
    ...entries.map(entry => entry.id),
  ].filter((taskId, index, values) => values.indexOf(taskId) === index)
  const taskOrder = [
    ...candidateIds.filter(taskId => isPretaskId(taskId)),
    ...candidateIds.filter(taskId => !isPretaskId(taskId)),
  ]
  const taskIdSet = new Set(taskOrder)
  return {
    taskOrder,
    taskChecked: Object.fromEntries(
      taskOrder.map(taskId => [taskId, taskChecked[taskId] !== false])
    ),
    keepUnchecked: true,
    // 每个实例的选项表拷一份：之后在队列里改选项是原地改这张表，不能改到预设本身。
    taskOptions: Object.fromEntries(
      Object.entries(presetTaskOptions)
        .filter(([taskId]) => taskIdSet.has(taskId))
        .map(([taskId, options]) => [taskId, { ...options }])
    ),
    ...taskLabelsField(pickMaaFWTaskLabels(taskLabels, taskIdSet)),
    ...taskSchedulesField(pickMaaFWTaskSchedules(taskSchedules, taskIdSet)),
  }
}

type TaskOptionMap = Record<string, Record<string, MaaFWTaskOptionValue>>

/** 项目预设声明的前置任务（PI v2.10.3 `preset.pretask`），键都是前置任务 id。 */
export type MaaFWPresetPretasks = {
  /** interface 的全部前置任务：预设列出且启用的为 true，其余（含未列出的）为 false */
  checked: Record<string, boolean>
  /** 预设给各前置任务写的选项值（只有写了的项） */
  options: TaskOptionMap
}

/**
 * 预设快照（`/maafw/preview` 原样给的，未按勾选过滤）里的前置任务部分。后端在预设声明了
 * `pretask` 时把 interface 的全部前置任务排进快照（未列出的为 false），没声明时一个不带，
 * 所以快照里没有前置任务就是「没声明」，返回 null。
 */
export const pickPresetPretasks = (
  snapshot: Pick<MaaFWTaskSnapshot, 'taskOrder' | 'taskChecked' | 'taskOptions'>,
  isPretaskId: (taskId: string) => boolean
): MaaFWPresetPretasks | null => {
  const taskIds = snapshot.taskOrder.filter(
    (taskId, index, values) => isPretaskId(taskId) && values.indexOf(taskId) === index
  )
  if (taskIds.length === 0) return null
  return {
    checked: Object.fromEntries(
      taskIds.map(taskId => [taskId, snapshot.taskChecked[taskId] === true])
    ),
    options: Object.fromEntries(
      taskIds.map(taskId => [taskId, snapshot.taskOptions?.[taskId] ?? {}])
    ),
  }
}

const cloneOptions = (options: Record<string, MaaFWTaskOptionValue> | undefined) =>
  JSON.parse(JSON.stringify(options ?? {})) as Record<string, MaaFWTaskOptionValue>

/**
 * 应用项目预设后的队列快照：普通任务换成预设的各个实例（一律绿灯，带预设的选项，项目预设
 * 没有显示名与运行日）。前置任务分两种情况：
 *
 * - 预设没声明 `pretask`（`pretasks` 为 null）：当前队列里的前置任务原样保留——勾选、选项、
 *   显示名、运行日都不动，与从别的用户导入队列（`buildMaaFWQueueReplacement`）同一口径；
 * - 声明了：当前队列里的前置任务按预设设勾选（未列出的设为跳过），选项在用户自己的值上叠
 *   预设写了的项（启动器路径这类用户自己填的不被冲掉），显示名与运行日照留；预设启用、队列里
 *   还没有这个前置任务的，把 `pretaskEntries` 里的补进来（带预设的选项）。预设没启用、队列里
 *   也没有的不补——不在队列里本来就不跑。
 *
 * `pretaskEntries` 是预设启用的前置任务里当前控制器 / 资源下可用的项（同 `entries` 的口径）。
 * `resolveTaskName` 把实例 id 解析回任务名：用户复制过的前置任务实例也按前置任务名对上预设。
 */
export const buildProjectPresetAppliedSnapshot = (
  entries: readonly MaaFWPresetQueueEntry[],
  presetTaskOptions: TaskOptionMap,
  pretasks: MaaFWPresetPretasks | null,
  pretaskEntries: readonly MaaFWPresetQueueEntry[],
  current: MaaFWTaskSnapshot,
  isPretaskId: (taskId: string) => boolean,
  resolveTaskName: (taskId: string) => string
): MaaFWTaskSnapshot => {
  const currentPretaskIds = current.taskOrder.filter(taskId => isPretaskId(taskId))
  const currentPretaskNames = new Set(currentPretaskIds.map(taskId => resolveTaskName(taskId)))
  const addedEntries = pretasks
    ? pretaskEntries.filter(
        entry =>
          pretasks.checked[entry.task.name] === true && !currentPretaskNames.has(entry.task.name)
      )
    : []
  const pretaskOptions: TaskOptionMap = Object.fromEntries([
    ...currentPretaskIds.map(taskId => [
      taskId,
      {
        ...cloneOptions(current.taskOptions[taskId]),
        ...cloneOptions(pretasks?.options[resolveTaskName(taskId)]),
      },
    ]),
    ...addedEntries.map(entry => [entry.id, cloneOptions(pretasks?.options[entry.task.name])]),
  ])
  const pretaskChecked: Record<string, boolean> = Object.fromEntries([
    ...currentPretaskIds.map(taskId => [
      taskId,
      pretasks
        ? pretasks.checked[resolveTaskName(taskId)] === true
        : current.taskChecked[taskId] !== false,
    ]),
    ...addedEntries.map(entry => [entry.id, true]),
  ])
  const presetOptions = Object.fromEntries(
    Object.entries(presetTaskOptions).filter(([taskId]) => !isPretaskId(taskId))
  )
  // 补进来的前置任务按 interface 顶层 pretask 的顺序插到已有前置任务之间（协议：前置任务
  // 按顶层顺序执行）；已有的保持用户排好的相对顺序。`pretasks.checked` 的键序即顶层顺序。
  const pretaskRank = new Map(
    Object.keys(pretasks?.checked ?? {}).map((taskName, index) => [taskName, index])
  )
  const rankOf = (taskName: string) => pretaskRank.get(taskName) ?? Number.MAX_SAFE_INTEGER
  const pretaskOrder = [...currentPretaskIds]
  for (const entry of addedEntries) {
    const rank = rankOf(entry.task.name)
    const index = pretaskOrder.findIndex(taskId => rankOf(resolveTaskName(taskId)) > rank)
    pretaskOrder.splice(index === -1 ? pretaskOrder.length : index, 0, entry.id)
  }
  return buildPresetAppliedSnapshot(
    entries.filter(entry => !isPretaskId(entry.id)),
    { ...presetOptions, ...pretaskOptions },
    pretaskOrder,
    isPretaskId,
    pickMaaFWTaskLabels(current.taskLabels, currentPretaskIds),
    pretaskChecked,
    pickMaaFWTaskSchedules(current.taskSchedules, currentPretaskIds)
  )
}
