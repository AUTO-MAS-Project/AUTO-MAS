import { describe, expect, it } from 'vitest'
import type { MaaFWOptionInfo } from '@/types/script'
import { maafwPasswordFields } from './maafwQueueSource'
import {
  addMaaFWQueueTemplate,
  buildMaaFWQueueTemplateSnapshot,
  checkMaaFWQueueTemplateName,
  createMaaFWKeyedWriteCoordinator,
  parseMaaFWQueueTemplates,
  removeMaaFWQueueTemplate,
  renameMaaFWQueueTemplate,
  type MaaFWQueueTemplate,
} from './maafwQueueTemplates'

const template = (name: string, taskOrder: string[] = ['日常']): MaaFWQueueTemplate => ({
  name,
  snapshot: {
    taskOrder,
    taskChecked: Object.fromEntries(taskOrder.map(id => [id, true])),
    taskOptions: {},
  },
})

describe('parseMaaFWQueueTemplates', () => {
  it('收 JSON 文本与数组；坏 JSON、非数组得到空列表', () => {
    const list = [template('日常')]
    expect(parseMaaFWQueueTemplates(JSON.stringify(list))).toEqual(list)
    expect(parseMaaFWQueueTemplates(list)).toEqual(list)
    expect(parseMaaFWQueueTemplates('[ ]')).toEqual([])
    expect(parseMaaFWQueueTemplates('not json')).toEqual([])
    expect(parseMaaFWQueueTemplates({ name: 'x' })).toEqual([])
    expect(parseMaaFWQueueTemplates(undefined)).toEqual([])
  })

  it('没名字的跳过、名字去首尾空格、重名留先出现的；快照缺字段补空', () => {
    const parsed = parseMaaFWQueueTemplates([
      { name: '  周常  ', snapshot: { taskOrder: ['A', 3] } },
      { name: '周常', snapshot: { taskOrder: ['B'] } },
      { name: '   ', snapshot: {} },
      { snapshot: {} },
      'x',
    ])
    expect(parsed).toEqual([
      { name: '周常', snapshot: { taskOrder: ['A'], taskChecked: {}, taskOptions: {} } },
    ])
  })
})

describe('模板名称', () => {
  const names = ['日常', '周常']
  it('去首尾空格后为空、与已有同名都不能用', () => {
    expect(checkMaaFWQueueTemplateName('  ', names)).toBe('empty')
    expect(checkMaaFWQueueTemplateName(' 日常 ', names)).toBe('duplicate')
    expect(checkMaaFWQueueTemplateName('活动', names)).toBeNull()
  })

  it('重命名时改回原名不算重名', () => {
    expect(checkMaaFWQueueTemplateName('日常', names, '日常')).toBeNull()
    expect(checkMaaFWQueueTemplateName('周常', names, '日常')).toBe('duplicate')
  })
})

describe('增删改', () => {
  const list = [template('日常'), template('周常')]

  it('新增放在最后、存去空格后的名字；同名不覆盖', () => {
    expect(addMaaFWQueueTemplate(list, template(' 活动 '))?.map(item => item.name)).toEqual([
      '日常',
      '周常',
      '活动',
    ])
    expect(addMaaFWQueueTemplate(list, template('周常', ['别的']))).toBeNull()
  })

  it('重命名保持位置；新名重名、原模板不在了都返回 null', () => {
    expect(renameMaaFWQueueTemplate(list, '日常', ' 每日 ')?.map(item => item.name)).toEqual([
      '每日',
      '周常',
    ])
    expect(renameMaaFWQueueTemplate(list, '日常', '周常')).toBeNull()
    expect(renameMaaFWQueueTemplate(list, '不存在', '新名')).toBeNull()
  })

  it('删除只去掉同名那一个', () => {
    expect(removeMaaFWQueueTemplate(list, '日常').map(item => item.name)).toEqual(['周常'])
    expect(removeMaaFWQueueTemplate(list, '不存在')).toEqual(list)
  })
})

describe('createMaaFWKeyedWriteCoordinator：按脚本串行写、刷新丢弃旧结果', () => {
  const deferred = () => {
    let resolve!: () => void
    const promise = new Promise<void>(done => (resolve = done))
    return { promise, resolve }
  }

  it('同一个键的写入一个接一个（前一个写完后一个才开始读），不同键互不等待', async () => {
    const writes = createMaaFWKeyedWriteCoordinator()
    // 模拟后端里的模板列表：每次写入先读、再改、再写
    let stored: string[] = []
    const gate = deferred()
    const log: string[] = []
    const append = (name: string, wait?: Promise<void>) =>
      writes.write('s1', async () => {
        const latest = [...stored]
        log.push(`start:${name}`)
        if (wait) await wait
        stored = [...latest, name]
        log.push(`end:${name}`)
        return true
      })
    // 页面 A 的写入还没完成（卡在 gate），另一个用户页（另一个组件实例，同一个协调器）写 B
    const a = append('A', gate.promise)
    const b = append('B')
    const other = writes.write('s2', async () => {
      log.push('s2')
      return 's2'
    })
    await other
    expect(log).toEqual(['start:A', 's2'])
    gate.resolve()
    await Promise.all([a, b])
    expect(stored).toEqual(['A', 'B'])
    expect(log).toEqual(['start:A', 's2', 'end:A', 'start:B', 'end:B'])
  })

  it('前一个写入失败不挡后一个；失败原样抛给调用方', async () => {
    const writes = createMaaFWKeyedWriteCoordinator()
    const failed = writes.write('s1', async () => {
      throw new Error('boom')
    })
    const next = writes.write('s1', async () => 'ok')
    await expect(failed).rejects.toThrow('boom')
    await expect(next).resolves.toBe('ok')
  })

  it('写入开始与完成都让版本号变化：读之前记下的版本号对不上，读到的结果就该丢弃', async () => {
    const writes = createMaaFWKeyedWriteCoordinator()
    const before = writes.epoch('s1')
    const gate = deferred()
    const pending = writes.write('s1', () => gate.promise)
    await Promise.resolve()
    const started = writes.epoch('s1')
    expect(started).not.toBe(before)
    gate.resolve()
    await pending
    expect(writes.epoch('s1')).not.toBe(started)
    expect(writes.epoch('s2')).toBe(0)
  })

  it('settled 等到已排队的写入全部落定', async () => {
    const writes = createMaaFWKeyedWriteCoordinator()
    const gate = deferred()
    let done = false
    void writes.write('s1', async () => {
      await gate.promise
      done = true
    })
    const settled = writes.settled('s1').then(() => done)
    gate.resolve()
    await expect(settled).resolves.toBe(true)
    await expect(writes.settled('没写过的脚本')).resolves.toBeUndefined()
  })
})

describe('buildMaaFWQueueTemplateSnapshot', () => {
  const options = [
    {
      name: '登录',
      type: 'input',
      controller: [],
      resource: [],
      cases: [],
      inputs: [{ name: '账号' }, { name: '密码', password: true }],
      hotkeys: [],
    } as MaaFWOptionInfo,
  ]
  const passwordFields = maafwPasswordFields(options)

  it('只存给定的项（顺序同队列），全部勾选；选项去掉密码值且是拷贝', () => {
    const taskOptions = {
      日常: { 登录: { 账号: 'u', 密码: 'mas-dpapi:AAA' } },
      日常__MAS_DUP__x: { 选择: '第二章' },
      虚影任务: { 选择: 'a' },
    }
    const snapshot = buildMaaFWQueueTemplateSnapshot(
      [{ id: '日常' }, { id: '日常__MAS_DUP__x' }],
      taskOptions,
      passwordFields
    )
    expect(snapshot).toEqual({
      taskOrder: ['日常', '日常__MAS_DUP__x'],
      taskChecked: { 日常: true, 日常__MAS_DUP__x: true },
      taskOptions: { 日常: { 登录: { 账号: 'u' } }, 日常__MAS_DUP__x: { 选择: '第二章' } },
    })
    expect(snapshot.taskOptions.日常__MAS_DUP__x).not.toBe(taskOptions.日常__MAS_DUP__x)
    expect(taskOptions.日常.登录.密码).toBe('mas-dpapi:AAA')
  })
})
