import { describe, expect, it, vi } from 'vite-plus/test'
import { openConfirm } from './useConfirm'

describe('openConfirm', () => {
  it('高危确认注入 danger、居中与标题栏避让类，并在 onOk 完成后返回 true', async () => {
    let captured: Record<string, unknown> = {}
    const host = {
      confirm: vi.fn((config: Record<string, unknown>) => {
        captured = config
        return {} as never
      }),
    }

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

    expect(captured.centered).toBe(true)
    expect(captured.okType).toBe('danger')
    expect(captured.okButtonProps).toEqual({ danger: true })
    expect(captured.wrapClassName).toBe('app-confirm-modal')
    expect(captured.maskClosable).toBe(false)

    await (captured.onOk as () => Promise<void>)()
    expect(onOk).toHaveBeenCalledTimes(1)
    await expect(pending).resolves.toBe(true)
  })

  it('点击取消时返回 false，onOk 抛错时不伪装成成功', async () => {
    let captured: Record<string, unknown> = {}
    const host = {
      confirm: vi.fn((config: Record<string, unknown>) => {
        captured = config
        return {} as never
      }),
    }

    const failing = openConfirm(
      {
        title: '保存失败测试',
        onOk: async () => {
          throw new Error('network failed')
        },
      },
      host as never
    )

    await expect((captured.onOk as () => Promise<void>)()).rejects.toThrow('network failed')

    // 失败后用户取消，Promise 应正常落定为 false，不永久挂起
    ;(captured.onCancel as () => void)()
    await expect(failing).resolves.toBe(false)
  })
})
