import { describe, expect, it } from 'vitest'

import { InitializationOperationLock } from '../initializationOperationLock'

describe('InitializationOperationLock', () => {
  it('rejects a concurrent operation without executing it', async () => {
    const lock = new InitializationOperationLock()
    let releaseFirst!: () => void
    let secondExecuted = false
    const first = lock.runExclusive(
      'repository',
      () =>
        new Promise<void>(resolve => {
          releaseFirst = resolve
        })
    )

    await expect(
      lock.runExclusive('plugin-bootstrap', async () => {
        secondExecuted = true
      })
    ).rejects.toMatchObject({
      name: 'InitializationOperationBusyError',
      activeOperation: 'repository',
    })
    expect(secondExecuted).toBe(false)

    releaseFirst()
    await first
    expect(lock.getActiveOperation()).toBeNull()
  })

  it('releases the lock when an operation throws', async () => {
    const lock = new InitializationOperationLock()

    await expect(
      lock.runExclusive('dependency', async () => {
        throw new Error('failed')
      })
    ).rejects.toThrow('failed')

    await expect(lock.runExclusive('retry', async () => 'ok')).resolves.toBe('ok')
  })
})
