import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const getHealth = vi.hoisted(() => vi.fn())
const notificationMocks = vi.hoisted(() => ({
  warning: vi.fn(),
  error: vi.fn(),
  close: vi.fn(),
}))

vi.mock('@/api', () => ({ Service: { getHealthApiCoreHealthGet: getHealth } }))
vi.mock('@/i18n', () => ({
  translate: (key: string, named?: Record<string, unknown>) =>
    named ? `${key}:${JSON.stringify(named)}` : key,
}))
vi.mock('ant-design-vue', () => ({ notification: notificationMocks }))

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

type Module = typeof import('./backgroundInitNotice')

const health = (
  backgroundStatus: string,
  backgroundWarnings: string[] = [],
  backgroundError: string | null = null
) => ({
  ready: true,
  backgroundStatus,
  backgroundError,
  backgroundWarnings,
  protocol: 1,
  version: 'v0.0.0',
  commit: '',
})

// 通知正文是渲染函数，取出里面每行文字
const descriptionLines = (args: { description: () => { children: { children: string }[] } }) =>
  args.description().children.map(line => line.children)

describe('backgroundInitNotice', () => {
  let mod: Module

  beforeEach(async () => {
    vi.useFakeTimers()
    vi.stubGlobal('window', {
      setTimeout: globalThis.setTimeout,
      electronAPI: { getLogger: () => logger },
    })
    vi.resetModules()
    getHealth.mockReset()
    Object.values(notificationMocks).forEach(fn => fn.mockReset())
    mod = await import('./backgroundInitNotice')
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  describe('resolveBackgroundInit', () => {
    it('初始化进行中视为未结束', () => {
      expect(mod.resolveBackgroundInit(health('starting'))).toEqual({ kind: 'pending' })
      expect(mod.resolveBackgroundInit(health('running'))).toEqual({ kind: 'pending' })
    })

    it('ready 且无警告为正常，带警告为降级', () => {
      expect(mod.resolveBackgroundInit(health('ready'))).toEqual({ kind: 'ok' })
      expect(mod.resolveBackgroundInit(health('ready', ['  ']))).toEqual({ kind: 'ok' })
      expect(
        mod.resolveBackgroundInit(health('ready', ['MCP 服务挂载（X: y）', 'QQ 通知通道（E: q）']))
      ).toEqual({
        kind: 'degraded',
        detail: 'MCP 服务挂载（X: y）；QQ 通知通道（E: q）',
      })
    })

    it('老后端没有 backgroundWarnings 字段时按正常处理', () => {
      expect(
        mod.resolveBackgroundInit({ backgroundStatus: 'ready', backgroundError: null })
      ).toEqual({ kind: 'ok' })
    })

    it('failed 为失败，cancelled 与未知取值不提示', () => {
      expect(mod.resolveBackgroundInit(health('failed', ['QQ 通知通道（E: q）'], 'boom'))).toEqual({
        kind: 'failed',
        detail: 'boom；QQ 通知通道（E: q）',
      })
      expect(mod.resolveBackgroundInit(health('failed'))).toEqual({ kind: 'failed', detail: '' })
      expect(mod.resolveBackgroundInit(health('cancelled'))).toEqual({ kind: 'ignored' })
      expect(mod.resolveBackgroundInit(health('mystery'))).toEqual({ kind: 'ignored' })
    })
  })

  describe('checkBackgroundInit', () => {
    it('可选步骤失败时给出警告通知，写明定时任务已启动和失败项，且不自动消失', async () => {
      getHealth.mockResolvedValue(
        health('ready', ['明日方舟 PC 工具初始化（ModuleNotFoundError: x）'])
      )

      await mod.checkBackgroundInit()

      expect(notificationMocks.error).not.toHaveBeenCalled()
      expect(notificationMocks.warning).toHaveBeenCalledTimes(1)
      const args = notificationMocks.warning.mock.calls[0][0]
      expect(args).toMatchObject({
        key: 'backend-background-init',
        message: 'misc.backgroundInitDegradedTitle',
        duration: null,
      })
      expect(descriptionLines(args)).toEqual([
        'misc.backgroundInitTimerStarted',
        `misc.backgroundInitFailedSteps:${JSON.stringify({
          steps: '明日方舟 PC 工具初始化（ModuleNotFoundError: x）',
        })}`,
      ])
    })

    it('主定时器失败时给出错误通知，写明定时任务可能未启动', async () => {
      getHealth.mockResolvedValue(health('failed', [], '主业务定时器（RuntimeError: t）'))

      await mod.checkBackgroundInit()

      expect(notificationMocks.warning).not.toHaveBeenCalled()
      expect(notificationMocks.error).toHaveBeenCalledTimes(1)
      const args = notificationMocks.error.mock.calls[0][0]
      expect(args.message).toBe('misc.backgroundInitFailedTitle')
      expect(descriptionLines(args)[0]).toBe('misc.backgroundInitTimerNotStarted')
    })

    it('全部成功时不提示，并收起之前的提示', async () => {
      getHealth.mockResolvedValue(health('ready'))

      await mod.checkBackgroundInit()

      expect(notificationMocks.warning).not.toHaveBeenCalled()
      expect(notificationMocks.error).not.toHaveBeenCalled()
      expect(notificationMocks.close).toHaveBeenCalledWith('backend-background-init')
    })

    it('初始化未结束时按间隔等到终态，只在终态提示一次', async () => {
      getHealth
        .mockResolvedValueOnce(health('starting'))
        .mockResolvedValueOnce(health('running'))
        .mockResolvedValue(health('ready', ['QQ 通知通道（OSError: q）']))

      const done = mod.checkBackgroundInit()
      await vi.runAllTimersAsync()
      await done

      expect(getHealth).toHaveBeenCalledTimes(3)
      expect(notificationMocks.warning).toHaveBeenCalledTimes(1)
    })

    it('一直未结束时到上限就停，不无限轮询', async () => {
      getHealth.mockResolvedValue(health('running'))

      const done = mod.checkBackgroundInit()
      await vi.runAllTimersAsync()
      await done

      expect(getHealth).toHaveBeenCalledTimes(30)
      expect(notificationMocks.warning).not.toHaveBeenCalled()
      expect(logger.warn).toHaveBeenCalled()
    })

    it('请求失败时放弃本次检查，不重试', async () => {
      getHealth.mockRejectedValue(new Error('offline'))

      await mod.checkBackgroundInit()

      expect(getHealth).toHaveBeenCalledTimes(1)
      expect(notificationMocks.warning).not.toHaveBeenCalled()
      expect(notificationMocks.error).not.toHaveBeenCalled()
    })

    it('同一份失败内容重连后不重复弹，内容变了才再弹', async () => {
      getHealth.mockResolvedValue(health('ready', ['A（E: 1）']))
      await mod.checkBackgroundInit()
      await mod.checkBackgroundInit()
      expect(notificationMocks.warning).toHaveBeenCalledTimes(1)

      getHealth.mockResolvedValue(health('ready', ['B（E: 2）']))
      await mod.checkBackgroundInit()
      expect(notificationMocks.warning).toHaveBeenCalledTimes(2)
    })

    it('恢复正常后再出同样的失败会重新提示', async () => {
      getHealth.mockResolvedValue(health('ready', ['A（E: 1）']))
      await mod.checkBackgroundInit()
      getHealth.mockResolvedValue(health('ready'))
      await mod.checkBackgroundInit()
      getHealth.mockResolvedValue(health('ready', ['A（E: 1）']))
      await mod.checkBackgroundInit()

      expect(notificationMocks.warning).toHaveBeenCalledTimes(2)
    })

    it('作废后进行中的等待不再提示', async () => {
      getHealth
        .mockResolvedValueOnce(health('running'))
        .mockResolvedValue(health('ready', ['A（E: 1）']))

      const done = mod.checkBackgroundInit()
      mod.cancelBackgroundInitCheck()
      await vi.runAllTimersAsync()
      await done

      expect(getHealth).toHaveBeenCalledTimes(1)
      expect(notificationMocks.warning).not.toHaveBeenCalled()
    })
  })
})
