import { describe, expect, it, vi } from 'vitest'

import {
  buildElevationHandoffArguments,
  completeElevationHandoff,
  ELEVATION_HANDOFF_ARGUMENT,
  readElevationHandoffToken,
  waitForSingleInstanceLock,
} from '../singleInstanceHandoff'

const token = '123e4567-e89b-42d3-a456-426614174000'

describe('single-instance elevation handoff', () => {
  it('replaces stale handoff arguments and validates the new token', () => {
    const args = buildElevationHandoffArguments(
      ['AUTO-MAS.exe', `${ELEVATION_HANDOFF_ARGUMENT}stale`, '--auto-start'],
      token
    )
    expect(args).toEqual(['AUTO-MAS.exe', '--auto-start', `${ELEVATION_HANDOFF_ARGUMENT}${token}`])
    expect(readElevationHandoffToken(args)).toBe(token)
    expect(readElevationHandoffToken([`${ELEVATION_HANDOFF_ARGUMENT}not-a-uuid`])).toBeNull()
  })

  it('does not retry an ordinary second instance without a handoff token', async () => {
    const requestLock = vi.fn(() => false)
    const delay = vi.fn(async () => undefined)
    await expect(
      waitForSingleInstanceLock({
        commandLine: ['AUTO-MAS.exe'],
        requestLock,
        timeoutMs: 60_000,
        delay,
      })
    ).resolves.toBe(false)
    expect(requestLock).toHaveBeenCalledOnce()
    expect(delay).not.toHaveBeenCalled()
  })

  it('lets an elevated successor acquire the lock only after delayed cleanup releases it', async () => {
    let lockAvailable = false
    let clock = 0
    const requestLock = vi.fn(() => lockAvailable)
    const releaseLock = vi.fn(() => {
      lockAvailable = true
    })
    let finishCleanup: (() => void) | undefined
    const cleanup = vi.fn(
      () =>
        new Promise<void>(resolve => {
          finishCleanup = resolve
        })
    )
    const quit = vi.fn()

    const oldInstanceHandoff = completeElevationHandoff(cleanup, releaseLock, quit)
    const successor = waitForSingleInstanceLock({
      commandLine: ['AUTO-MAS.exe', `${ELEVATION_HANDOFF_ARGUMENT}${token}`],
      requestLock,
      timeoutMs: 10_000,
      retryIntervalMs: 100,
      now: () => clock,
      delay: async milliseconds => {
        clock += milliseconds
        await Promise.resolve()
      },
    })

    await Promise.resolve()
    expect(releaseLock).not.toHaveBeenCalled()
    expect(quit).not.toHaveBeenCalled()
    finishCleanup?.()

    await expect(oldInstanceHandoff).resolves.toBeUndefined()
    await expect(successor).resolves.toBe(true)
    expect(releaseLock).toHaveBeenCalledOnce()
    expect(quit).toHaveBeenCalledOnce()
  })
})
