import { effectScope, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 用户页对特调声明不可选任务（预览里的 unselectableReason）的处理：不进「添加任务」与预设模板，
// 已在队列里的照常显示，队列提示里多一句运行时会跳过

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

const REASON = '需手动进入对应页面（M9A 没有自动导航）'
const task = (name: string, unselectableReason: string | null = null) => ({
  name,
  label: name,
  entry: name,
  group: [],
  controller: [],
  resource: [],
  option: [],
  defaultCheck: false,
  unselectableReason,
})

const preview = {
  path: 'D:/project',
  project: { name: 'demo', icon: null },
  controllers: [{ name: 'Win', type: 'Win32' }],
  resources: [{ name: 'Official', controller: [] }],
  groups: [],
  tasks: [task('Daily'), task('Arcade', REASON), task('Critter', REASON)],
  options: [],
  presets: [
    {
      name: 'mixed',
      label: 'mixed',
      snapshot: {
        taskOrder: ['Daily', 'Arcade'],
        taskChecked: { Daily: true, Arcade: true },
        taskOptions: {},
      },
    },
    {
      name: 'onlyGames',
      label: 'onlyGames',
      snapshot: { taskOrder: ['Critter'], taskChecked: { Critter: true }, taskOptions: {} },
    },
  ],
}

const mountPage = async (taskOrder: string[]) => {
  mocks.getUsers.mockResolvedValue({
    code: 200,
    index: [{ uid: 'u1', type: 'MaaFWUserConfig' }],
    data: {
      u1: {
        Info: { Name: 'Alice' },
        Task: {
          SelectedPreset: '',
          TaskSnapshot: JSON.stringify({
            taskOrder,
            taskChecked: Object.fromEntries(taskOrder.map(id => [id, true])),
          }),
        },
      },
    },
  })
  const scope = effectScope()
  const page = scope.run(() => useMaaFWUserPage({ scriptId: 's1', userId: 'u1' }))!
  void mocks.mounted[0]()
  await vi.waitFor(() => expect(page.loading.value).toBe(false))
  return { scope, page }
}

describe('useMaaFWUserPage：不可选任务', () => {
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

  it('「添加任务」候选与预设模板都不含不可选任务', async () => {
    const { scope, page } = await mountPage(['Daily'])
    expect(page.availableTasks.value.map(item => item.name)).toEqual(['Daily'])
    // 预设里的不可选任务按「不可用」跳过；只剩不可选任务的预设整个不出现
    expect(
      page.presetTemplates.value.map(template => [
        template.preset.name,
        template.entries.map(entry => entry.task.name),
      ])
    ).toEqual([['mixed', ['Daily']]])
    expect(page.queueHintLines.value).toEqual([])
    scope.stop()
  })

  it('已在队列里的照常显示，提示只有一句（同一原因并起来）', async () => {
    const { scope, page } = await mountPage(['Daily', 'Arcade', 'Critter'])
    expect(page.orderedTasks.value.map(item => item.id)).toEqual(['Daily', 'Arcade', 'Critter'])
    expect(page.queueHintLines.value).toEqual([
      `edit.maafwUnselectableTaskNotice|${JSON.stringify({ tasks: 'Arcade、Critter', reason: REASON })}`,
    ])
    // 删掉之后提示随之消失
    await page.deleteTask('Arcade')
    await page.deleteTask('Critter')
    expect(page.queueHintLines.value).toEqual([])
    scope.stop()
  })

  it('级联菜单里没有，硬塞选中值也加不进去', async () => {
    const { scope, page } = await mountPage(['Daily'])
    expect(page.addTaskCascaderOptions.value.map(option => option.value)).toEqual(['task:Daily'])
    await page.handleAddTaskCascaderChange(['task:Arcade'])
    expect(page.taskSnapshot.value.taskOrder).toEqual(['Daily'])
    await page.handleAddTaskCascaderChange(['task:Daily'])
    expect(page.taskSnapshot.value.taskOrder).toHaveLength(2)
    scope.stop()
  })
})
