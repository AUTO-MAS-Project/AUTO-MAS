import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { effectScope, nextTick, reactive } from 'vue'
import { PowerSignal, type GlobalConfig } from '@/api'
import type { TaskTargetSnapshot } from '@/composables/useTaskOptions'
import type { FrontendConfig } from '@/utils/config'

const mocks = vi.hoisted(() => ({
  snapshot: vi.fn(),
  script: vi.fn(),
  getConfig: vi.fn(),
  saveConfig: vi.fn(),
}))
vi.mock('@/composables/useTaskOptions', () => ({ fetchTaskTargetSnapshot: mocks.snapshot }))
vi.mock('@/utils/config', () => ({ getConfig: mocks.getConfig, saveConfig: mocks.saveConfig }))
vi.mock('@/api', async importOriginal => ({
  ...(await importOriginal<typeof import('@/api')>()),
  GetService: { getScriptApiScriptsGetPost: mocks.script },
}))

import { useDesktopSessionTargets } from './useDesktopSessionTargets'

const id = (n: number) => `00000000-0000-4000-8000-${n.toString().padStart(12, '0')}`
const QUEUE = id(1)
const POWER_QUEUE = id(2)
const SCRIPT = id(3)
const UNSUPPORTED = id(4)
const DETACHED = id(5)
const DELETED = id(6)

const snapshot: TaskTargetSnapshot = {
  targets: [
    { value: QUEUE, name: 'Q', label: '', kind: 'queue', afterAccomplish: PowerSignal.NO_ACTION },
    {
      value: POWER_QUEUE,
      name: 'P',
      label: '',
      kind: 'queue',
      afterAccomplish: PowerSignal.SHUTDOWN,
    },
    { value: SCRIPT, name: 'S', label: '', kind: 'script' },
    { value: UNSUPPORTED, name: 'U', label: '', kind: 'script' },
  ],
  unavailableScriptIds: [DETACHED],
  unavailableScripts: [{ uid: DETACHED, name: 'D' }],
}

function capability(scriptId: string) {
  const supported = scriptId !== UNSUPPORTED
  return Promise.resolve({
    code: 200,
    index: [
      {
        uid: scriptId,
        desktopSessionSupported: supported,
        desktopSessionReason: supported ? null : 'admin_required',
      },
    ],
    data: {},
  })
}

const scopes: ReturnType<typeof effectScope>[] = []
afterEach(() => {
  scopes.splice(0).forEach(scope => scope.stop())
  vi.clearAllMocks()
})

function setup(
  options: {
    targets?: string[]
    config?: Partial<FrontendConfig>
    save?: (next: string[]) => boolean
  } = {}
) {
  const settings = reactive<GlobalConfig>({ DesktopSession: { Targets: options.targets ?? [] } })
  const save = vi.fn(async (_category: string, _key: string, next: string[]) => {
    const ok = options.save?.(next) ?? true
    if (ok) settings.DesktopSession!.Targets = next
    return ok
  })
  const rejected = vi.fn()
  mocks.snapshot.mockResolvedValue(snapshot)
  mocks.script.mockImplementation(({ scriptId }: { scriptId: string }) => capability(scriptId))
  mocks.getConfig.mockResolvedValue({
    desktopSessionQueueIds: [],
    desktopSessionQueueIdsMigrated: true,
    ...options.config,
  })
  mocks.saveConfig.mockResolvedValue(undefined)
  const scope = effectScope()
  scopes.push(scope)
  const card = scope.run(() =>
    useDesktopSessionTargets({
      settings: () => settings,
      save: save as never,
      onAddRejected: rejected,
      onLoadFailed: vi.fn(),
    })
  )!
  return { card, save, rejected, settings }
}

const settle = async () => {
  for (let i = 0; i < 5; i++) {
    await Promise.resolve()
    await nextTick()
  }
}

describe('桌面分身清单', () => {
  it('旧键只并入一次：剔除已删除的 id，保留插件不可用的托管，保存成功后才置标记', async () => {
    const { card, save } = setup({
      targets: [SCRIPT],
      config: {
        desktopSessionQueueIds: [QUEUE.toUpperCase(), DELETED, DETACHED],
        desktopSessionQueueIdsMigrated: undefined,
      },
    })
    await card.load()
    await settle()

    expect(save).toHaveBeenCalledTimes(1)
    expect(save).toHaveBeenCalledWith('DesktopSession', 'Targets', [SCRIPT, QUEUE, DETACHED])
    expect(mocks.saveConfig).toHaveBeenCalledWith({ desktopSessionQueueIdsMigrated: true })

    await card.load()
    await settle()
    expect(save).toHaveBeenCalledTimes(1)
  })

  it('设置保存失败时不置迁移标记，清单回到原值', async () => {
    const { card, save } = setup({
      config: { desktopSessionQueueIds: [QUEUE], desktopSessionQueueIdsMigrated: false },
      save: () => false,
    })
    await card.load()
    await settle()

    expect(save).toHaveBeenCalledWith('DesktopSession', 'Targets', [QUEUE])
    expect(mocks.saveConfig).not.toHaveBeenCalled()
    expect(card.targets.value).toEqual([])
  })

  it('不支持分身的托管加不进清单，受支持的托管和队列追加到末尾', async () => {
    const { card, save, rejected } = setup()
    await card.load()

    await expect(card.add(UNSUPPORTED)).resolves.toBe(false)
    expect(rejected).toHaveBeenCalledWith('reasons.admin_required')
    await expect(card.add(POWER_QUEUE)).resolves.toBe(false)
    expect(save).not.toHaveBeenCalled()

    await expect(card.add(SCRIPT.toUpperCase())).resolves.toBe(true)
    await expect(card.add(QUEUE)).resolves.toBe(true)
    expect(save).toHaveBeenLastCalledWith('DesktopSession', 'Targets', [SCRIPT, QUEUE])
    expect(card.candidates.value.map(item => item.target.value)).toEqual([POWER_QUEUE, UNSUPPORTED])

    await card.remove(SCRIPT)
    expect(save).toHaveBeenLastCalledWith('DesktopSession', 'Targets', [QUEUE])
  })

  it('逐行标出问题，只有没问题的条目能启动', async () => {
    const { card } = setup({
      targets: [QUEUE, POWER_QUEUE, SCRIPT, UNSUPPORTED, DETACHED, DELETED],
    })
    await card.load()
    await settle()

    expect(card.rows.value.map(row => [row.name, row.issue, row.launchable])).toEqual([
      ['Q', undefined, true],
      ['P', 'powerAction', false],
      ['S', undefined, true],
      ['U', 'reasons.admin_required', false],
      ['D', 'reasons.plugin_unavailable', false],
      [DELETED, 'targetMissing', false],
    ])
    expect(card.launchableIds.value).toEqual([QUEUE, SCRIPT])
  })
})
