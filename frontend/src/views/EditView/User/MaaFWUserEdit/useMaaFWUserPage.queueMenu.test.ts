import { effectScope, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 用户页任务队列右键菜单背后的动作：复制（带选项与显示名、插在正下方）、改显示名（落盘、按基础名编号）、
// 删除时显示名一起清掉；受管 / 不可选任务不复制

const mocks = vi.hoisted(() => {
  const logger = { debug: () => {}, info: () => {}, warn: () => {}, error: () => {} }
  ;(globalThis as { window?: unknown }).window = {
    electronAPI: { getLogger: () => logger },
    addEventListener: () => {},
    removeEventListener: () => {},
  }
  ;(globalThis as { localStorage?: unknown }).localStorage = {
    getItem: () => null,
    setItem: () => {},
  }
  return {
    route: { name: 'MaaFWUserEdit', params: {} as Record<string, string> },
    mounted: [] as Array<() => unknown>,
    getScript: vi.fn(),
    previewInterface: vi.fn(),
    getUsers: vi.fn(),
    updateUser: vi.fn(),
  }
})

vi.mock('vue', async original => ({
  ...(await original<typeof import('vue')>()),
  onMounted: (hook: () => unknown) => mocks.mounted.push(hook),
  onBeforeUnmount: vi.fn(),
  onUnmounted: vi.fn(),
}))
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params ? `${key}|${JSON.stringify(params)}` : key,
  }),
}))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}))
vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  Modal: { confirm: vi.fn() },
}))
vi.mock('@/api', () => ({
  Service: { ensureConfigBackupApiApiScriptsBackupEnsurePost: vi.fn(async () => ({ code: 200 })) },
}))
vi.mock('@/composables/useScriptApi', () => ({
  useScriptApi: () => ({ getScript: mocks.getScript }),
}))
vi.mock('@/composables/useUserApi', () => ({
  useUserApi: () => ({ addUser: vi.fn(), getUsers: mocks.getUsers, updateUser: mocks.updateUser }),
}))
vi.mock('@/composables/useMaaFWApi', () => ({
  buildMaaFWAssetUrl: () => '',
  useMaaFWApi: () => ({ loading: ref(false), previewInterface: mocks.previewInterface }),
}))
vi.mock('../../MaaFWFlavor/pageHostContext', () => ({
  useMaaFWPageHostContext: () => null,
}))
vi.mock('@/composables/useScriptConfigLock', () => ({
  useScriptConfigLock: () => ({ configLocked: ref(false) }),
}))

import { useMaaFWUserPage } from './useMaaFWUserPage'
import type { MaaFWQueueEntry } from '@/types/script'

const task = (name: string, label: string, unselectableReason: string | null = null) => ({
  name,
  label,
  entry: name,
  group: [],
  controller: [],
  resource: [],
  option: ['o'],
  defaultCheck: false,
  unselectableReason,
})

const preview = {
  path: 'D:/project',
  project: { name: 'demo', icon: null },
  controllers: [{ name: 'Win', type: 'Win32' }],
  resources: [{ name: 'Official', controller: [] }],
  groups: [],
  tasks: [task('Start', '崩坏三 启动!'), task('Daily', '日常'), task('Arcade', '小游戏', '手动')],
  options: [],
  presets: [],
}

const mountPage = async (snapshot: Record<string, unknown>) => {
  mocks.getUsers.mockResolvedValue({
    code: 200,
    index: [{ uid: 'u1', type: 'MaaFWUserConfig' }],
    data: {
      u1: {
        Info: { Name: 'Alice' },
        Task: { SelectedPreset: '', TaskSnapshot: JSON.stringify(snapshot) },
      },
    },
  })
  const scope = effectScope()
  const page = scope.run(() => useMaaFWUserPage({ scriptId: 's1', userId: 'u1' }))!
  void mocks.mounted[0]()
  await vi.waitFor(() => expect(page.loading.value).toBe(false))
  return { scope, page }
}

/** 队列行上看到的文字：基础名，同一基础名 ≥ 2 份时拼 #序号 */
const rowTexts = (items: MaaFWQueueEntry[]) =>
  items.map(item => {
    const base = item.missing ? item.name : item.customLabel || item.task.label || item.task.name
    return item.copyTotal > 1 ? `${base} #${item.copyIndex}` : base
  })

const lastSavedSnapshot = () => {
  const calls = mocks.updateUser.mock.calls
  const data = calls[calls.length - 1][2] as { Task: { TaskSnapshot: string } }
  return JSON.parse(data.Task.TaskSnapshot)
}

describe('useMaaFWUserPage：队列右键菜单', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.mounted.length = 0
    mocks.route.params = { scriptId: 's1', userId: 'u1' }
    mocks.getScript.mockResolvedValue({
      type: 'MaaFW',
      name: 'Demo',
      config: { Info: { Path: 'D:/project', Controller: '', Resource: '' }, Emulator: { Id: '-' } },
    })
    mocks.previewInterface.mockResolvedValue(preview)
    mocks.updateUser.mockResolvedValue(true)
  })

  it('复制插在正下方、带选项并选中副本；没改过名时按任务编号，存下的快照不带 taskLabels', async () => {
    const { scope, page } = await mountPage({
      taskOrder: ['Start', 'Daily'],
      taskChecked: { Start: true, Daily: true },
      taskOptions: { Start: { o: 'b' } },
    })
    await page.duplicateTask('Start')
    await page.duplicateTask('Start')
    const order = page.taskSnapshot.value.taskOrder
    expect(order).toHaveLength(4)
    expect(order[0]).toBe('Start')
    expect(order[3]).toBe('Daily')
    expect(page.selectedTaskId.value).toBe(order[1])
    expect(page.taskSnapshot.value.taskOptions[order[1]]).toEqual({ o: 'b' })
    expect(rowTexts(page.orderedTasks.value)).toEqual([
      '崩坏三 启动! #1',
      '崩坏三 启动! #2',
      '崩坏三 启动! #3',
      '日常',
    ])
    const saved = lastSavedSnapshot()
    expect(saved.taskOrder).toEqual(order)
    expect('taskLabels' in saved).toBe(false)
    scope.stop()
  })

  it('改显示名后按基础名分组编号，复制改过名的实例连名字一起复制', async () => {
    const { scope, page } = await mountPage({
      taskOrder: ['Start', 'Start__MAS_DUP__b', 'Start__MAS_DUP__c'],
      taskChecked: {},
      taskOptions: {},
    })
    await page.renameTask('Start__MAS_DUP__b', '  账号A ')
    expect(rowTexts(page.orderedTasks.value)).toEqual([
      '崩坏三 启动! #1',
      '账号A',
      '崩坏三 启动! #2',
    ])
    await page.duplicateTask('Start__MAS_DUP__b')
    expect(rowTexts(page.orderedTasks.value)).toEqual([
      '崩坏三 启动! #1',
      '账号A #1',
      '账号A #2',
      '崩坏三 启动! #2',
    ])
    const copyId = page.taskSnapshot.value.taskOrder[2]
    expect(lastSavedSnapshot().taskLabels).toEqual({
      Start__MAS_DUP__b: '账号A',
      [copyId]: '账号A',
    })
    scope.stop()
  })

  it('改回原显示名或清空即删掉这一条；删除任务时显示名一起清掉', async () => {
    const { scope, page } = await mountPage({
      taskOrder: ['Start', 'Daily'],
      taskChecked: {},
      taskOptions: {},
      taskLabels: { Start: '早班', Daily: '收菜' },
    })
    expect(rowTexts(page.orderedTasks.value)).toEqual(['早班', '收菜'])
    await page.renameTask('Start', '崩坏三 启动!')
    expect(page.taskSnapshot.value.taskLabels).toEqual({ Daily: '收菜' })
    await page.deleteTask('Daily')
    expect(page.taskSnapshot.value.taskLabels).toBeUndefined()
    expect('taskLabels' in lastSavedSnapshot()).toBe(false)
    scope.stop()
  })

  it('按显示文字分组：改名成另一任务的 label 后两行都编号', async () => {
    const { scope, page } = await mountPage({
      taskOrder: ['Start', 'Daily'],
      taskChecked: {},
      taskOptions: {},
    })
    expect(rowTexts(page.orderedTasks.value)).toEqual(['崩坏三 启动!', '日常'])
    await page.renameTask('Daily', '崩坏三 启动!')
    expect(rowTexts(page.orderedTasks.value)).toEqual(['崩坏三 启动! #1', '崩坏三 启动! #2'])
    expect(lastSavedSnapshot().taskLabels).toEqual({ Daily: '崩坏三 启动!' })
    scope.stop()
  })

  it('不可选任务不复制', async () => {
    const { scope, page } = await mountPage({
      taskOrder: ['Arcade'],
      taskChecked: {},
      taskOptions: {},
    })
    await page.duplicateTask('Arcade')
    expect(page.taskSnapshot.value.taskOrder).toEqual(['Arcade'])
    expect(mocks.updateUser).not.toHaveBeenCalled()
    scope.stop()
  })
})
