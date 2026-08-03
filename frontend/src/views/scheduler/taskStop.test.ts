import { describe, expect, it } from 'vitest'

import { isTaskStopConfirmed } from './taskStop'

describe('isTaskStopConfirmed', () => {
  it('accepts completed and already removed tasks', () => {
    expect(isTaskStopConfirmed({ code: 200 })).toBe(true)
    expect(isTaskStopConfirmed({ code: 500, message: 'ValueError: 未找到对应任务' })).toBe(true)
    expect(isTaskStopConfirmed({ code: 500, message: '任务正在中止中' })).toBe(false)
  })
})
