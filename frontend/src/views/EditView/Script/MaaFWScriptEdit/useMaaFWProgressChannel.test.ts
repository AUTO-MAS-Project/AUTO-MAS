import { effectScope } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  handler: null as ((message: { data: { stage: string } }) => void) | null,
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
}))

vi.mock('@/composables/useWebSocket', () => ({
  subscribe: mocks.subscribe,
  unsubscribe: mocks.unsubscribe,
}))

import { useMaaFWProgressChannel, type MaaFWEnvProgressData } from './useMaaFWProgressChannel'

const push = (stage: string) => mocks.handler?.({ data: { stage } })

describe('useMaaFWProgressChannel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.handler = null
    mocks.subscribe.mockImplementation((_filter, handler) => {
      mocks.handler = handler
      return 'sub_1'
    })
  })

  it('导入与环境两类监听都能挂多个，按阶段分发；取消只摘自己', () => {
    const scope = effectScope()
    const channel = scope.run(() => useMaaFWProgressChannel('s1'))!
    const seen: string[] = []
    const record = (name: string) => (data: MaaFWEnvProgressData) =>
      seen.push(`${name}:${data.stage}`)
    channel.onImportProgress(record('import-a'))
    const offImportB = channel.onImportProgress(record('import-b'))
    channel.onEnvProgress(record('env-a'))
    channel.onEnvProgress(record('env-b'))
    channel.ensureEnvSubscription()
    channel.ensureEnvSubscription()
    expect(mocks.subscribe).toHaveBeenCalledOnce()

    push('importing')
    push('preparing')
    offImportB()
    push('imported')
    expect(seen).toEqual([
      'import-a:importing',
      'import-b:importing',
      'env-a:preparing',
      'env-b:preparing',
      'import-a:imported',
    ])
    scope.stop()
    expect(mocks.unsubscribe).toHaveBeenCalledWith('sub_1')
  })

  it('在别的作用域里挂的监听随该作用域销毁自动摘掉，页面自己的照常收', () => {
    const page = effectScope()
    const channel = page.run(() => useMaaFWProgressChannel('s1'))!
    const pageListener = vi.fn()
    page.run(() => channel.onEnvProgress(pageListener))
    const section = effectScope()
    const sectionListener = vi.fn()
    section.run(() => channel.onEnvProgress(sectionListener))
    channel.ensureEnvSubscription()

    push('preparing')
    section.stop()
    push('ready')
    expect(pageListener).toHaveBeenCalledTimes(2)
    expect(sectionListener).toHaveBeenCalledOnce()
    page.stop()
  })
})
