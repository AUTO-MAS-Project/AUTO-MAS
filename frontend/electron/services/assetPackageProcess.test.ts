import { EventEmitter } from 'node:events'
import { describe, expect, it, vi } from 'vite-plus/test'

const electron = vi.hoisted(() => ({ fork: vi.fn(), quit: vi.fn() }))
vi.mock('electron', async () => {
  const { EventEmitter } = await import('node:events')
  return {
    app: Object.assign(new EventEmitter(), { quit: electron.quit }),
    utilityProcess: { fork: electron.fork },
  }
})

describe('资源处理与退出确认', () => {
  it('退出尚未确认时保持当前任务和后续资源操作可用', async () => {
    const app = (await import('electron')).app
    const children: EventEmitter[] = []
    electron.fork.mockImplementation(() => {
      const child = Object.assign(new EventEmitter(), {
        postMessage: vi.fn(),
        kill() {
          child.emit('exit', 0)
        },
      })
      children.push(child)
      return child
    })
    const { importAppearancePackage } = await import('./assetPackageProcess')
    const first = importAppearancePackage('user', 'first.zip')
    await vi.waitFor(() => expect(children).toHaveLength(1))
    children[0].emit('spawn')
    // 发起原生退出后，窗口仍可以询问用户；取消时不能影响资源队列。
    app.emit('before-quit', { preventDefault: vi.fn() })
    children[0].emit('message', { operation: 'import-theme', value: { success: true } })
    expect((await first).success).toBe(true)
    const second = importAppearancePackage('user', 'second.zip')
    await vi.waitFor(() => expect(children).toHaveLength(2))
    children[1].emit('spawn')
    children[1].emit('message', { operation: 'import-theme', value: { success: true } })
    expect((await second).success).toBe(true)
    expect(electron.quit).not.toHaveBeenCalled()
  })
})
