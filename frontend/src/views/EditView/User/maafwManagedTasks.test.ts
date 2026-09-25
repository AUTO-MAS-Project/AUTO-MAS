import { describe, expect, it } from 'vitest'
import {
  isManagedMaaFWTask,
  maafwAccountOf,
  managedMaaFWQueueState,
  withoutManagedMaaFWTasks,
} from './maafwManagedTasks'
import { resolveMaaFWFlavor } from '@/composables/useMaaFWFlavor'
import type { MaaFWOptionInfo } from '@/types/script'

// 任务表与选项照 M9A v4.10.0 的 interface：启动 / 切号 / 关闭三个受管任务 + 两个普通任务
const TASKS = [
  { name: '启动游戏', label: '启动游戏', entry: 'StartUp', option: [] },
  { name: '收取荒原', label: '收取荒原', entry: 'Wilderness', option: ['好梦井'] },
  { name: '切换账号', label: '切换账号', entry: 'SwitchAccount', option: ['目标账号(可选)'] },
  { name: '常规作战', label: '常规作战', entry: 'Combat', option: [] },
  { name: '关闭游戏', label: '关闭游戏', entry: 'Close1999', option: [] },
]
const [STARTUP, WILDERNESS, SWITCH, , CLOSE] = TASKS
const OPTIONS = [
  {
    name: '目标账号(可选)',
    type: 'input',
    controller: [],
    resource: [],
    cases: [],
    inputs: [{ name: '账号', default: '' }],
    hotkeys: [],
  },
] as MaaFWOptionInfo[]

const m9a = resolveMaaFWFlavor('M9A')
const maafw = resolveMaaFWFlavor('MaaFW')
const m9aEntries = new Set(m9a.managedTaskEntries)
const maafwEntries = new Set(maafw.managedTaskEntries)

const switchOptions = (account: string) => ({ '目标账号(可选)': { 账号: account } })

const stateOf = (
  queued: { id: string; task: (typeof TASKS)[number] }[],
  taskOptions: Record<string, Record<string, Record<string, string>>>,
  resourceName: string,
  flavor = m9a
) =>
  managedMaaFWQueueState(queued, {
    managedEntries: new Set(flavor.managedTaskEntries),
    accountTask: flavor.managedAccountTask,
    resourceName,
    taskOptions,
    options: OPTIONS,
    displayName: task => task.label,
  })

describe('MaaFW 特调的受管任务', () => {
  it('M9A 的「添加任务」与预设模板候选里没有启动游戏、切换账号、关闭游戏', () => {
    expect(withoutManagedMaaFWTasks(TASKS, m9aEntries).map(task => task.name)).toEqual([
      '收取荒原',
      '常规作战',
    ])
  })

  it('通用 MaaFW 与没声明受管任务的特调一个都不滤', () => {
    expect(withoutManagedMaaFWTasks(TASKS, maafwEntries)).toHaveLength(TASKS.length)
    expect(resolveMaaFWFlavor('MSS').managedTaskEntries).toEqual([])
  })

  it('按 entry 判，不按任务名', () => {
    expect(isManagedMaaFWTask({ entry: 'SwitchAccount' }, m9aEntries)).toBe(true)
    expect(isManagedMaaFWTask({ entry: '' }, m9aEntries)).toBe(false)
    expect(isManagedMaaFWTask(null, m9aEntries)).toBe(false)
  })

  it('切号的目标账号取第一个 input 选项的第一个字段', () => {
    expect(maafwAccountOf(SWITCH, switchOptions(' acc-a '), OPTIONS)).toBe('acc-a')
    expect(maafwAccountOf(SWITCH, switchOptions(''), OPTIONS)).toBe('')
    expect(maafwAccountOf(SWITCH, undefined, OPTIONS)).toBe('')
  })
})

describe('队列里残留受管任务时的提示（与后端 managed.py 同一判据）', () => {
  const twoSwitches = [
    { id: '切换账号', task: SWITCH },
    { id: '收取荒原', task: WILDERNESS },
    { id: '切换账号__MAS_DUP__1', task: SWITCH },
  ]
  const twoAccounts = {
    切换账号: switchOptions('acc-a'),
    切换账号__MAS_DUP__1: switchOptions('acc-b'),
  }

  it('官服、有效切号 ≥ 2：要拆用户', () => {
    expect(stateOf(twoSwitches, twoAccounts, '官服')).toEqual({
      kind: 'split',
      count: 2,
      accounts: 'acc-a、acc-b',
    })
  })

  it('资源不是官服：不要求拆分（运行期按控制器回落的资源同样适用）', () => {
    expect(stateOf(twoSwitches, twoAccounts, '国际服（EN）')).toEqual({
      kind: 'notice',
      tasks: '切换账号',
    })
  })

  it('两个切号里一个账号为空：只算一个有效切号，不要求拆分', () => {
    const options = { ...twoAccounts, 切换账号__MAS_DUP__1: switchOptions('') }
    expect(stateOf(twoSwitches, options, '官服')?.kind).toBe('notice')
  })

  it('刚导入成 M9A、队列带着启动 / 关闭：只是轻提示', () => {
    const queued = [
      { id: '启动游戏', task: STARTUP },
      { id: '收取荒原', task: WILDERNESS },
      { id: '关闭游戏', task: CLOSE },
    ]
    expect(stateOf(queued, {}, '官服')).toEqual({ kind: 'notice', tasks: '启动游戏、关闭游戏' })
  })

  it('没有受管任务、或通用 MaaFW：什么都不提示', () => {
    expect(stateOf([{ id: '收取荒原', task: WILDERNESS }], {}, '官服')).toBeNull()
    expect(stateOf(twoSwitches, twoAccounts, '官服', maafw)).toBeNull()
  })
})
