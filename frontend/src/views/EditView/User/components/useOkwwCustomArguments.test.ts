import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
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

  it('restores the previous draft and switch when enabling fails to save', async () => {
    const task = ref(getDefaultOkwwTaskConfig())
    task.value.CustomArguments = '-t PreviousTask'
    const confirm = vi.fn<(onOk: () => Promise<void>) => void>()
    const flow = useOkwwCustomArguments(task, ref('-t DailyTask -e'), async () => false, confirm)
    flow.changeCustomArguments(true)
    await expect(confirm.mock.calls[0]![0]()).resolves.toBeUndefined()
    expect(task.value.IfCustomArguments).toBe(false)
    expect(task.value.CustomArguments).toBe('-t PreviousTask')
    expect(flow.saving.value).toBe(false)
  })

  it('restores the enabled switch when disabling fails to save', async () => {
    const task = ref(getDefaultOkwwTaskConfig())
    task.value.IfCustomArguments = true
    const flow = useOkwwCustomArguments(task, ref(''), async () => false, vi.fn())
    expect(await flow.changeCustomArguments(false)).toBe(false)
    expect(task.value.IfCustomArguments).toBe(true)
  })
})
