import { describe, expect, it, vi } from 'vite-plus/test'
import { openConfirm } from './useConfirm'

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function createMockHost() {
  let captured: Record<string, unknown> = {}
  const update = vi.fn((patch: Record<string, unknown>) => {
    captured = { ...captured, ...patch }
  })
  const destroy = vi.fn()
  const host = {
    confirm: vi.fn((config: Record<string, unknown>) => {
      captured = config
      return { update, destroy } as never
    }),
  }
  return {
    host,
    update,
    getConfig: () => captured,
  }
}

describe('openConfirm', () => {
  it('高危确认注入 danger、居中与标题栏避让类，并在 onOk 完成后返回 true', async () => {
    const { host, getConfig } = createMockHost()
    const onOk = vi.fn().mockResolvedValue(undefined)
    const pending = openConfirm(
      {
        tone: 'danger',
        title: '确认删除',
        description: '删除后不可恢复',
        okText: '删除',
        cancelText: '取消',
        onOk,
      },
      host as never
    )

    const config = getConfig()
    expect(config.centered).toBe(true)
    expect(config.okType).toBe('danger')
    expect(config.okButtonProps).toEqual({ danger: true })
    expect(config.wrapClassName).toBe('app-confirm-modal')
    expect(config.maskClosable).toBe(false)

    await (config.onOk as () => Promise<void>)()
    expect(onOk).toHaveBeenCalledTimes(1)
    await expect(pending).resolves.toBe(true)
  })

  it('异步确认未结束时锁定取消与 Esc，期间触发取消不会提前改变结果', async () => {
    const { host, update, getConfig } = createMockHost()
    const deferred = createDeferred<void>()
    const closeSpy = vi.fn()

    const pending = openConfirm(
      {
        title: '删除队列',
        maskClosable: true,
        onOk: () => deferred.promise,
      },
      host as never
    )

    const onOkPromise = (getConfig().onOk as () => Promise<void>)()

    // 开始执行异步确认后应立即锁住取消按钮、Esc 与遮罩关闭
    expect(update).toHaveBeenLastCalledWith({
      cancelButtonProps: { disabled: true },
      keyboard: false,
      maskClosable: false,
      closable: false,
    })

    // 确认仍在执行中时尝试取消，不应关闭也不应把结果算成 false
    ;(getConfig().onCancel as (close?: () => void) => void)(closeSpy)
    expect(closeSpy).not.toHaveBeenCalled()

    deferred.resolve()
    await onOkPromise
    await expect(pending).resolves.toBe(true)
  })

  it('异步确认失败后恢复取消与 Esc 交互，随后取消可正常返回 false', async () => {
    const { host, update, getConfig } = createMockHost()
    const closeSpy = vi.fn()

    const failing = openConfirm(
      {
        title: '保存失败测试',
        maskClosable: true,
        onOk: async () => {
          throw new Error('network failed')
        },
      },
      host as never
    )

    await expect((getConfig().onOk as () => Promise<void>)()).rejects.toThrow('network failed')

    // 失败后应恢复取消按钮、Esc 与初始 maskClosable
    expect(update).toHaveBeenLastCalledWith({
      cancelButtonProps: { disabled: false },
      keyboard: true,
      maskClosable: true,
      closable: false,
    })

    ;(getConfig().onCancel as (close?: () => void) => void)(closeSpy)
    expect(closeSpy).toHaveBeenCalledTimes(1)
    await expect(failing).resolves.toBe(false)
  })
})
