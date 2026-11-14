import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { getDefaultOkwwTaskConfig } from './okwwTaskConfig'
import { useOkwwCustomArguments } from './useOkwwCustomArguments'

describe('custom argument confirmation and persistence', () => {
  it('does not change configuration before confirmation, then seeds current parameters', async () => {
    const task = ref(getDefaultOkwwTaskConfig())
    const save = vi.fn(async () => true)
    const confirm = vi.fn<(onOk: () => Promise<void>) => void>()
    const flow = useOkwwCustomArguments(task, ref('-t MultiAccountConfigTask -e'), save, confirm)
    flow.changeCustomArguments(true)
    expect(task.value.IfCustomArguments).toBe(false)
    expect(save).not.toHaveBeenCalled()
    await confirm.mock.calls[0]![0]()
    expect(task.value.IfCustomArguments).toBe(true)
    expect(task.value.CustomArguments).toBe('-t MultiAccountConfigTask -e')
    expect(save).toHaveBeenCalledOnce()
  })

  it.each([false, true])(
    'restores the previous draft and switch when enabled=%s fails to save',
    async enabled => {
      const task = ref(getDefaultOkwwTaskConfig())
      task.value.IfCustomArguments = enabled
      task.value.CustomArguments = '-t PreviousTask'
      const confirm = vi.fn<(onOk: () => Promise<void>) => void>()
      const flow = useOkwwCustomArguments(task, ref('-t DailyTask -e'), async () => false, confirm)
      if (enabled) await expect(flow.changeCustomArguments(false)).resolves.toBe(false)
      else {
        flow.changeCustomArguments(true)
        await expect(confirm.mock.calls[0]![0]()).resolves.toBeUndefined()
      }
      expect(task.value.IfCustomArguments).toBe(enabled)
      expect(task.value.CustomArguments).toBe('-t PreviousTask')
      expect(flow.saving.value).toBe(false)
    }
  )
})
