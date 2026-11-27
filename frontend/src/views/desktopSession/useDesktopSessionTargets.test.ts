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

type ListKey = 'Targets' | 'StartOnOpen'

function setup(
  options: {
    targets?: string[]
    startOnOpen?: string[]
    config?: Partial<FrontendConfig>
    save?: (key: ListKey, next: string[]) => boolean
  } = {}
) {
  const settings = reactive<GlobalConfig>({
    DesktopSession: { Targets: options.targets ?? [], StartOnOpen: options.startOnOpen ?? [] },
  })
  const save = vi.fn(async (_category: string, key: ListKey, next: string[]) => {
    const ok = options.save?.(key, next) ?? true
    if (ok) settings.DesktopSession![key] = next
    return ok
  })
  const rejected = vi.fn()
  mocks.snapshot.mockResolvedValue(snapshot)
  mocks.script.mockImplementation(({ scriptId }: { scriptId: string }) => capability(scriptId))
  mocks.getConfig.mockResolvedValue({
    desktopSessionQueueIds: [],
    desktopSessionStartOnOpenMigrated: true,
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

const savedKeys = (save: ReturnType<typeof setup>['save']) => save.mock.calls.map(call => call[1])

describe('桌面分身清单', () => {
  // 旧版两个选择各自独立：执行会话由后端并入 Targets，卡片勾选由这里并入 StartOnOpen。
  it.each([
    ['main', false],
    ['main', true],
    ['desktop', false],
    ['desktop', true],
  ] as const)(
    '迁移前后两个入口的派发判断：旧执行会话 %s、旧卡片勾选 %s',
    async (legacySession, legacyCard) => {
      const absorbed = legacySession === 'desktop' ? [SCRIPT] : []
      const { card, save } = setup({
        targets: absorbed,
        config: {
          desktopSessionQueueIds: legacyCard ? [SCRIPT] : [],
          desktopSessionStartOnOpenMigrated: undefined,
        },
      })
      await card.load()
      await settle()

      // 单独启动只看 Targets：迁移不动它。
      expect(card.standalone.value).toEqual(absorbed)
      expect(savedKeys(save)).not.toContain('Targets')
      // 卡片全部启动只看 StartOnOpen：只承接旧卡片勾选。
      expect(card.launchIds.value.includes(SCRIPT)).toBe(legacyCard)
      const row = card.rows.value.find(item => item.id === SCRIPT)
      expect(row && [row.standalone, row.startOnOpen]).toEqual(
        legacySession === 'main' && !legacyCard
          ? undefined
          : [legacySession === 'desktop', legacyCard]
      )
      if (legacyCard) {
        expect(save).toHaveBeenCalledTimes(1)
        expect(save).toHaveBeenCalledWith('DesktopSession', 'StartOnOpen', [SCRIPT])
      } else {
        expect(save).not.toHaveBeenCalled()
      }
      expect(mocks.saveConfig).toHaveBeenCalledWith({ desktopSessionStartOnOpenMigrated: true })

      mocks.getConfig.mockResolvedValue({
        desktopSessionQueueIds: legacyCard ? [SCRIPT] : [],
        desktopSessionStartOnOpenMigrated: true,
      })
      const calls = save.mock.calls.length
      await card.load()
      await settle()
      expect(save).toHaveBeenCalledTimes(calls)
    }
  )

  it('旧键只并入一并启动清单：剔除已删除的 id，保留插件不可用的托管', async () => {
    const { card, save } = setup({
      targets: [SCRIPT],
      config: {
        desktopSessionQueueIds: [QUEUE.toUpperCase(), DELETED, DETACHED],
        desktopSessionStartOnOpenMigrated: undefined,
      },
    })
    await card.load()
    await settle()

    expect(save).toHaveBeenCalledTimes(1)
    expect(save).toHaveBeenCalledWith('DesktopSession', 'StartOnOpen', [QUEUE, DETACHED])
    expect(card.standalone.value).toEqual([SCRIPT])
    expect(mocks.saveConfig).toHaveBeenCalledWith({ desktopSessionStartOnOpenMigrated: true })
  })

  it('一并启动清单保存失败时不置迁移标记，清单回到原值', async () => {
    const { card, save } = setup({
      config: { desktopSessionQueueIds: [QUEUE], desktopSessionStartOnOpenMigrated: false },
      save: () => false,
    })
    await card.load()
    await settle()

    expect(save).toHaveBeenCalledWith('DesktopSession', 'StartOnOpen', [QUEUE])
    expect(mocks.saveConfig).not.toHaveBeenCalled()
    expect(card.startOnOpen.value).toEqual([])
  })

  it('不支持分身的托管加不进清单；托管加入两份清单，队列只进一并启动', async () => {
    const { card, save, rejected } = setup()
    await card.load()

    await expect(card.add(UNSUPPORTED)).resolves.toBe(false)
    expect(rejected).toHaveBeenCalledWith('reasons.admin_required')
    await expect(card.add(POWER_QUEUE)).resolves.toBe(false)
    expect(save).not.toHaveBeenCalled()

    await expect(card.add(SCRIPT.toUpperCase())).resolves.toBe(true)
    await expect(card.add(QUEUE)).resolves.toBe(true)
    expect(save.mock.calls.map(call => call.slice(1))).toEqual([
      ['StartOnOpen', [SCRIPT]],
      ['Targets', [SCRIPT]],
      ['StartOnOpen', [SCRIPT, QUEUE]],
    ])
    expect(card.candidates.value.map(item => item.target.value)).toEqual([POWER_QUEUE, UNSUPPORTED])

    save.mockClear()
    await card.remove(SCRIPT)
    expect(save.mock.calls.map(call => call.slice(1))).toEqual([
      ['Targets', []],
      ['StartOnOpen', [QUEUE]],
    ])
  })

  it('逐行标出问题；全部启动交给后端预检，只排除认不出的条目', async () => {
    const all = [QUEUE, POWER_QUEUE, SCRIPT, UNSUPPORTED, DETACHED, DELETED]
    const { card } = setup({ startOnOpen: all })
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
    expect(card.launchIds.value).toEqual([QUEUE, POWER_QUEUE, SCRIPT, UNSUPPORTED])
  })

  it('只在一并启动清单里的托管也单查能力并标出原因', async () => {
    const { card } = setup({ targets: [SCRIPT], startOnOpen: [UNSUPPORTED] })
    await card.load()
    await settle()

    expect(card.rows.value.map(row => [row.id, row.issue])).toEqual([
      [UNSUPPORTED, 'reasons.admin_required'],
      [SCRIPT, undefined],
    ])
  })

  it('切换启动方式：先撤单独启动，再改一并启动，最后加单独启动', async () => {
    const { card, save, rejected } = setup({
      targets: [SCRIPT],
      startOnOpen: [SCRIPT, UNSUPPORTED],
    })
    await card.load()
    await settle()
    const calls = () => save.mock.calls.map(call => call.slice(1))

    await expect(card.setMode(SCRIPT, 'standalone')).resolves.toBe(true)
    expect(calls()).toEqual([['StartOnOpen', [UNSUPPORTED]]])

    save.mockClear()
    await expect(card.setMode(SCRIPT, 'startOnOpen')).resolves.toBe(true)
    expect(calls()).toEqual([
      ['Targets', []],
      ['StartOnOpen', [UNSUPPORTED, SCRIPT]],
    ])

    save.mockClear()
    await expect(card.setMode(UNSUPPORTED, 'both')).resolves.toBe(false)
    expect(rejected).toHaveBeenCalledWith('reasons.admin_required')
    expect(save).not.toHaveBeenCalled()
  })

  it('加单独启动那一步失败时停下：一并启动已写入，单独启动回到设置值', async () => {
    const { card, save } = setup({
      startOnOpen: [QUEUE, SCRIPT],
      save: key => key !== 'Targets',
    })
    await card.load()
    await settle()

    await expect(card.setMode(SCRIPT, 'standalone')).resolves.toBe(false)
    expect(save.mock.calls.map(call => call.slice(1))).toEqual([
      ['StartOnOpen', [QUEUE]],
      ['Targets', [SCRIPT]],
    ])
    expect(card.startOnOpen.value).toEqual([QUEUE])
    expect(card.standalone.value).toEqual([])
  })
})
