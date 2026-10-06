import { describe, expect, it } from 'vitest'
import type { MaaFWOptionInfo, MaaFWTaskInfo, MaaFWTaskSnapshot } from '@/types/script'
import {
  buildMaaFWQueueReplacement,
  countMaaFWPasswordValues,
  countMaaFWQueueReplacementImports,
  describeMaaFWQueueSource,
  maafwPasswordFields,
  stripMaaFWPasswordValues,
  type MaaFWQueueSourceContext,
} from './maafwQueueSource'

const task = (name: string, extra: Partial<MaaFWTaskInfo> = {}): MaaFWTaskInfo => ({
  name,
  label: `${name}-显示名`,
  entry: name,
  group: [],
  controller: [],
  resource: [],
  option: [],
  defaultCheck: false,
  ...extra,
})

const inputOption = (name: string, inputs: Array<{ name: string; password?: boolean }>) =>
  ({
    name,
    type: 'input',
    controller: [],
    resource: [],
    cases: [],
    inputs,
    hotkeys: [],
  }) as MaaFWOptionInfo

const options = [
  inputOption('登录', [{ name: '账号' }, { name: '密码', password: true }]),
  inputOption('口令', [{ name: '值', password: true }]),
  inputOption('备注', [{ name: '内容' }]),
  { ...inputOption('选择', []), type: 'select' },
]
const passwordFields = maafwPasswordFields(options)

const pretask = task('__MXU_PRETASK__启动', { entry: 'MXU_PRETASK' })
const daily = task('日常')
const fight = task('战斗')
const officialOnly = task('官服专属', { resource: ['官服'] })
const startUp = task('启动游戏', { entry: 'StartUp' })
const allTasks = [pretask, daily, fight, officialOnly, startUp]
const taskByName = new Map(allTasks.map(item => [item.name, item] as const))

const context: MaaFWQueueSourceContext = {
  taskByName,
  // 当前资源是 B 服：官服专属不可用；受管任务也不在可用里
  availableTaskByName: new Map([pretask, daily, fight].map(item => [item.name, item] as const)),
  isManagedTask: item => item.entry === 'StartUp',
  passwordFields,
  displayName: item => item.label || item.name,
}

const snapshot = (
  taskOrder: string[],
  taskOptions: MaaFWTaskSnapshot['taskOptions'] = {}
): MaaFWTaskSnapshot => ({
  taskOrder,
  taskChecked: Object.fromEntries(taskOrder.map(id => [id, true])),
  taskOptions,
})

describe('maafwPasswordFields', () => {
  it('只收 input 型选项里 password 为 true 的字段', () => {
    expect([...passwordFields.keys()]).toEqual(['登录', '口令'])
    expect([...passwordFields.get('登录')!]).toEqual(['密码'])
  })
})

describe('describeMaaFWQueueSource：别处的队列在当前项目下的样子', () => {
  const source = snapshot(
    [
      '启动游戏',
      '日常',
      '战斗',
      '战斗__MAS_DUP__ab12',
      '官服专属',
      '已删除任务__MAS_DUP__x1',
      '日常',
    ],
    {
      启动游戏: { 选择: 'a' },
      日常: { 登录: { 账号: 'u', 密码: 'mas-dpapi:AAA' }, 口令: { 值: '' } },
      战斗__MAS_DUP__ab12: { 口令: { 值: '明文旧值' } },
      官服专属: { 登录: { 密码: 'mas-dpapi:BBB' } },
    }
  )
  const result = describeMaaFWQueueSource(source, context)

  it('受管任务不显示、不计数；重复实例各一个标签；重复的同一 id 只算一次', () => {
    expect(result.chips.map(chip => chip.id)).toEqual([
      '日常',
      '战斗',
      '战斗__MAS_DUP__ab12',
      '官服专属',
      '已删除任务__MAS_DUP__x1',
    ])
  })

  it('interface 已没有、当前资源下不可用的标成失效，不进可导入项', () => {
    expect(result.chips.filter(chip => chip.invalid).map(chip => chip.label)).toEqual([
      '官服专属-显示名',
      '已删除任务',
    ])
    expect(result.invalidCount).toBe(2)
    expect(result.entries.map(entry => entry.id)).toEqual(['日常', '战斗', '战斗__MAS_DUP__ab12'])
  })

  it('只数可导入项里已填的密码字段（空值、失效项里的不算）；选项表只留可导入项', () => {
    expect(result.passwordCount).toBe(2)
    expect(Object.keys(result.taskOptions).sort()).toEqual(['战斗__MAS_DUP__ab12', '日常'].sort())
  })
})

describe('密码字段', () => {
  it('stripMaaFWPasswordValues 去掉密码值、保留同一选项的其他字段；去空的选项整项去掉；不改入参', () => {
    const input = {
      日常: { 登录: { 账号: 'u', 密码: 'mas-dpapi:AAA' }, 口令: { 值: 'x' }, 备注: { 内容: 'n' } },
    }
    const stripped = stripMaaFWPasswordValues(input, passwordFields)
    expect(stripped).toEqual({ 日常: { 登录: { 账号: 'u' }, 备注: { 内容: 'n' } } })
    expect(input.日常.登录.密码).toBe('mas-dpapi:AAA')
    expect(countMaaFWPasswordValues(stripped, passwordFields)).toBe(0)
  })
})

describe('buildMaaFWQueueReplacement：用来源替换当前队列', () => {
  const source = describeMaaFWQueueSource(
    snapshot(['战斗', '日常'], {
      战斗: { 备注: { 内容: '来源' } },
      日常: { 登录: { 账号: 'u', 密码: 'mas-dpapi:AAA' } },
    }),
    context
  )
  const current = snapshot(['__MXU_PRETASK__启动', '日常', '官服专属'], {
    __MXU_PRETASK__启动: { 备注: { 内容: '当前前置' } },
    日常: { 备注: { 内容: '当前' } },
  })
  const isPretaskId = (taskId: string) => taskId === '__MXU_PRETASK__启动'
  const next = buildMaaFWQueueReplacement(source, current, isPretaskId, passwordFields)

  it('当前前置任务带着自己的选项留在最前，其余换成来源的顺序与选项', () => {
    expect(next.taskOrder).toEqual(['__MXU_PRETASK__启动', '战斗', '日常'])
    expect(next.taskOptions.__MXU_PRETASK__启动).toEqual({ 备注: { 内容: '当前前置' } })
    expect(next.taskOptions.战斗).toEqual({ 备注: { 内容: '来源' } })
    expect(Object.values(next.taskChecked).every(Boolean)).toBe(true)
  })

  it('导入条数是实际写入的来源实例：与当前前置任务同 id 的来源项被去重，不算', () => {
    expect(countMaaFWQueueReplacementImports(source, current, isPretaskId)).toBe(2)
    const withPretask = describeMaaFWQueueSource(
      snapshot(['__MXU_PRETASK__启动', '战斗', '日常']),
      context
    )
    expect(withPretask.entries).toHaveLength(3)
    const replaced = buildMaaFWQueueReplacement(withPretask, current, isPretaskId, passwordFields)
    expect(replaced.taskOrder).toEqual(['__MXU_PRETASK__启动', '战斗', '日常'])
    expect(countMaaFWQueueReplacementImports(withPretask, current, isPretaskId)).toBe(2)
    // 当前没有前置任务时，来源的前置任务是真的写进去了
    expect(countMaaFWQueueReplacementImports(withPretask, snapshot(['日常']), isPretaskId)).toBe(3)
  })

  it('当前前置任务没有选项表时，来源同 id 前置任务的自定义选项也不带过来', () => {
    // 加前置任务后应用过项目预设：前置任务 id 留着，选项表里却没有它
    const currentWithoutOptions = snapshot(['__MXU_PRETASK__启动', '日常'])
    const sourceWithPretask = describeMaaFWQueueSource(
      snapshot(['__MXU_PRETASK__启动', '战斗'], {
        __MXU_PRETASK__启动: { 备注: { 内容: '来源前置' } },
        战斗: { 备注: { 内容: '来源' } },
      }),
      context
    )
    const replaced = buildMaaFWQueueReplacement(
      sourceWithPretask,
      currentWithoutOptions,
      isPretaskId,
      passwordFields
    )
    expect(replaced.taskOrder).toEqual(['__MXU_PRETASK__启动', '战斗'])
    expect(replaced.taskOptions.__MXU_PRETASK__启动).toEqual({})
    expect(replaced.taskOptions.战斗).toEqual({ 备注: { 内容: '来源' } })
  })

  it('密码值不带过去；新快照的选项是深拷贝，改它不会改到来源', () => {
    expect(next.taskOptions.日常).toEqual({ 登录: { 账号: 'u' } })
    ;(next.taskOptions.战斗.备注 as Record<string, string>).内容 = '改了'
    expect(source.taskOptions.战斗).toEqual({ 备注: { 内容: '来源' } })
  })
})
