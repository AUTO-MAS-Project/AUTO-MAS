import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { WSEnvelope, WSJsonObject } from './types'

const logger = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}

vi.stubGlobal('window', {
  electronAPI: {
    getLogger: () => logger,
  },
})

const loadSubscriptions = async () => {
  vi.resetModules()
  return await import('./subscriptions')
}

const envelope = (id: string, type: string, data: WSJsonObject = {}): WSEnvelope<WSJsonObject> => ({
  id,
  type,
  data,
})

describe('websocket subscriptions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('routes messages by id + type', async () => {
    const { subscribe, dispatchMessage } = await loadSubscriptions()
    const handler = vi.fn()
    subscribe({ id: 'task-1', type: 'task.notice' }, handler)

    dispatchMessage(envelope('task-1', 'task.notice'))
    dispatchMessage(envelope('task-2', 'task.notice'))
    dispatchMessage(envelope('task-1', 'task.completed'))

    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler.mock.calls[0][0].id).toBe('task-1')
  })

  it('supports multiple types under the same id', async () => {
    const { subscribe, dispatchMessage } = await loadSubscriptions()
    const noticeHandler = vi.fn()
    const completedHandler = vi.fn()
    subscribe({ id: 'task-1', type: 'task.notice' }, noticeHandler)
    subscribe({ id: 'task-1', type: 'task.completed' }, completedHandler)

    dispatchMessage(envelope('task-1', 'task.notice'))
    dispatchMessage(envelope('task-1', 'task.completed'))

    expect(noticeHandler).toHaveBeenCalledTimes(1)
    expect(completedHandler).toHaveBeenCalledTimes(1)
  })

  it('calls multiple subscriptions of the same key in order', async () => {
    const { subscribe, dispatchMessage } = await loadSubscriptions()
    const order: string[] = []
    subscribe({ id: 'Main', type: 'test.event' }, () => {
      order.push('first')
    })
    subscribe({ id: 'Main', type: 'test.event' }, () => {
      order.push('second')
    })

    dispatchMessage(envelope('Main', 'test.event'))

    expect(order).toEqual(['first', 'second'])
  })

  it('reports unmatched messages so the connection layer can drop them', async () => {
    const { dispatchMessage } = await loadSubscriptions()
    expect(dispatchMessage(envelope('nobody', 'no.handler'))).toBe(false)
  })

  it('does not deliver messages after unsubscribe and stays idempotent', async () => {
    const { subscribe, unsubscribe, dispatchMessage } = await loadSubscriptions()
    const handler = vi.fn()
    const subscriptionId = subscribe({ id: 'task-1', type: 'task.notice' }, handler)

    unsubscribe(subscriptionId)
    unsubscribe(subscriptionId)
    unsubscribe('sub_not_exists')

    expect(dispatchMessage(envelope('task-1', 'task.notice'))).toBe(false)
    expect(handler).not.toHaveBeenCalled()
  })

  it('isolates handler errors from other subscribers', async () => {
    const { subscribe, dispatchMessage } = await loadSubscriptions()
    const good = vi.fn()
    subscribe({ id: 'Main', type: 'test.event' }, () => {
      throw new Error('boom')
    })
    subscribe({ id: 'Main', type: 'test.event' }, good)

    expect(dispatchMessage(envelope('Main', 'test.event'))).toBe(true)
    expect(good).toHaveBeenCalledTimes(1)
    expect(logger.warn).toHaveBeenCalled()
  })

  it('allows unsubscribing inside a handler without breaking dispatch', async () => {
    const { subscribe, unsubscribe, dispatchMessage } = await loadSubscriptions()
    const calls: string[] = []
    const firstId = subscribe({ id: 'Main', type: 'test.event' }, () => {
      calls.push('first')
      unsubscribe(firstId)
    })
    subscribe({ id: 'Main', type: 'test.event' }, () => {
      calls.push('second')
    })

    dispatchMessage(envelope('Main', 'test.event'))
    dispatchMessage(envelope('Main', 'test.event'))

    expect(calls).toEqual(['first', 'second', 'second'])
  })
})
