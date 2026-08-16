import { describe, expect, it, vi } from 'vitest'
import { createAnimationFrameScheduler } from './satelliteAnimationLoop'

describe('satellite animation frame scheduler', () => {
  it('keeps only one pending frame when animation startup overlaps', () => {
    const pendingCallbacks: FrameRequestCallback[] = []
    const requestFrame = vi.fn((callback: FrameRequestCallback) => {
      pendingCallbacks.push(callback)
      return pendingCallbacks.length
    })
    const cancelFrame = vi.fn()
    const scheduler = createAnimationFrameScheduler(requestFrame, cancelFrame)
    const firstFrame = vi.fn()
    const duplicateFrame = vi.fn()

    expect(scheduler.request(firstFrame)).toBe(true)
    expect(scheduler.request(duplicateFrame)).toBe(false)
    expect(requestFrame).toHaveBeenCalledOnce()

    pendingCallbacks[0]?.(0)

    expect(firstFrame).toHaveBeenCalledOnce()
    expect(duplicateFrame).not.toHaveBeenCalled()
    expect(scheduler.request(duplicateFrame)).toBe(true)
    expect(requestFrame).toHaveBeenCalledTimes(2)
  })
})
