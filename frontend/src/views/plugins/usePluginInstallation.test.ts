import { effectScope } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import type { PluginCatalogDocument } from '@/api'

const boundary = vi.hoisted(() => ({ runCommand: vi.fn(), success: vi.fn(), error: vi.fn() }))
vi.mock('@/composables/usePluginApi', () => ({
  usePluginApi: () => ({ runCommand: boundary.runCommand }),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('ant-design-vue', () => ({
  message: { success: boundary.success, error: boundary.error },
}))

import { createPluginOperationLock } from './pluginOperationLock'
import { usePluginInstallation } from './usePluginInstallation'

const row = (uid: string, editable = true): PluginCatalogDocument =>
  ({
    uid,
    ui: { hints: { info: [{ field: 'install', editable }] } },
    info: { plugin_name: uid, update_available: true },
  }) as unknown as PluginCatalogDocument

describe('插件安装排队', () => {
  beforeEach(() => {
    boundary.runCommand.mockReset()
    boundary.success.mockReset()
    boundary.error.mockReset()
  })

  it('「全部更新」先全部标为排队，再按顺序逐个执行，每成功一项回读一次', async () => {
    const lock = createPluginOperationLock()
    const onInstalled = vi.fn(async () => undefined)
    const installation = usePluginInstallation(lock, { onInstalled })
    const seen: Array<[string, Record<string, string>]> = []
    boundary.runCommand.mockImplementation(
      async (_kind: string, request: { configUid: string }) => {
        seen.push([
          request.configUid,
          Object.fromEntries(
            Object.values(installation.tasks.value).map(task => [task.uid, task.phase])
          ),
        ])
        expect(lock.current.value).toEqual({ uid: request.configUid, action: 'install' })
        return {}
      }
    )

    const result = await installation.installSequence([row('a'), row('locked', false), row('b')])

    expect(result).toEqual({ succeeded: ['a', 'b'], failed: [], skipped: [] })
    expect(seen).toEqual([
      ['a', { a: 'running', b: 'queued' }],
      ['b', { a: 'succeeded', b: 'running' }],
    ])
    expect(onInstalled).toHaveBeenCalledTimes(2)
    expect(lock.busy.value).toBe(false)
  })

  it('一项失败就停，剩下的移出排队，锁随之释放', async () => {
    const lock = createPluginOperationLock()
    const installation = usePluginInstallation(lock)
    boundary.runCommand
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValue({})

    const result = await installation.installSequence([row('a'), row('b'), row('c'), row('d')])

    expect(result).toEqual({ succeeded: ['a'], failed: ['b'], skipped: ['c', 'd'] })
    expect(boundary.runCommand).toHaveBeenCalledTimes(2)
    expect(installation.taskOf('a')?.phase).toBe('succeeded')
    expect(installation.taskOf('b')?.phase).toBe('failed')
    expect(installation.taskOf('c')).toBeNull()
    expect(installation.taskOf('d')).toBeNull()
    expect(boundary.error).toHaveBeenCalledTimes(1)
    expect(lock.busy.value).toBe(false)
  })

  it('每项执行前按最新目录重判：已无更新、不可安装或已不在目录里的不提交，也不算失败', async () => {
    const lock = createPluginOperationLock()
    // 目录随前一项完成而变化：a 升级后 b 已是最新，c 被停止安装，d 从目录消失。
    const catalog: Record<string, PluginCatalogDocument | undefined> = {
      a: row('a'),
      b: row('b'),
      c: row('c'),
      d: row('d'),
      e: row('e'),
    }
    const installation = usePluginInstallation(lock, { latest: uid => catalog[uid] })
    boundary.runCommand.mockImplementation(
      async (_kind: string, request: { configUid: string }) => {
        if (request.configUid === 'a') {
          catalog.b = { ...row('b'), info: { plugin_name: 'b', update_available: false } }
          catalog.c = row('c', false)
          catalog.d = undefined
        }
        return {}
      }
    )

    const stale = [row('a'), row('b'), row('c'), row('d'), row('e')]
    const result = await installation.installSequence(stale)

    expect(result).toEqual({ succeeded: ['a', 'e'], failed: [], skipped: ['b', 'c', 'd'] })
    expect(boundary.runCommand.mock.calls.map(call => call[1].configUid)).toEqual(['a', 'e'])
    expect(boundary.error).not.toHaveBeenCalled()
    expect(installation.taskOf('b')).toBeNull()
    expect(installation.taskOf('e')?.phase).toBe('succeeded')
    expect(lock.busy.value).toBe(false)
  })

  it('回读期间离开插件中心：不再派发下一项，剩余移出排队，锁释放', async () => {
    const lock = createPluginOperationLock()
    let finishReload = () => {}
    const reloading = new Promise<void>(resolve => (finishReload = resolve))
    const onInstalled = vi.fn(() => reloading)
    const scope = effectScope()
    const installation = scope.run(() => usePluginInstallation(lock, { onInstalled }))!
    boundary.runCommand.mockResolvedValue({})

    const pending = installation.installSequence([row('a'), row('b'), row('c')])
    // a 已成功，正停在回读上；此时页面卸载。
    await vi.waitFor(() => expect(onInstalled).toHaveBeenCalledTimes(1))
    scope.stop()
    finishReload()

    expect(await pending).toEqual({ succeeded: ['a'], failed: [], skipped: ['b', 'c'] })
    expect(boundary.runCommand.mock.calls.map(call => call[1].configUid)).toEqual(['a'])
    expect(installation.taskOf('b')).toBeNull()
    expect(installation.taskOf('c')).toBeNull()
    expect(boundary.error).not.toHaveBeenCalled()
    expect(lock.busy.value).toBe(false)
  })

  it('同一时刻只允许一个插件操作；界面提示不可执行时不提交', async () => {
    const lock = createPluginOperationLock()
    const installation = usePluginInstallation(lock)
    lock.acquire({ uid: 'other', action: 'disable' })
    expect(await installation.install(row('a'))).toBe(false)
    expect(await installation.installSequence([row('a'), row('b')])).toEqual({
      succeeded: [],
      failed: [],
      skipped: [],
    })
    lock.release()
    expect(await installation.install(row('a', false))).toBe(false)
    expect(boundary.runCommand).not.toHaveBeenCalled()
    expect(installation.tasks.value).toEqual({})
  })

  it('安装阶段按 runCommand 的回报就地更新', async () => {
    const lock = createPluginOperationLock()
    const installation = usePluginInstallation(lock)
    const phases: string[] = []
    boundary.runCommand.mockImplementation(
      async (_kind: string, _request: unknown, onStage: (stage: string) => void) => {
        for (const stage of ['waiting', 'restarting']) {
          onStage(stage)
          phases.push(installation.taskOf('a')?.phase ?? '')
          expect(installation.active.value?.uid).toBe('a')
        }
        return {}
      }
    )
    expect(await installation.install(row('a'))).toBe(true)
    expect(phases).toEqual(['waiting', 'restarting'])
    expect(installation.taskOf('a')).toMatchObject({ phase: 'succeeded', upgrade: true })
    expect(installation.active.value).toBeNull()
  })
})
