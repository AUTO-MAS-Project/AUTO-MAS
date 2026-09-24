import { describe, expect, it } from 'vitest'
import {
  canElectronExitImmediately,
  canRequestRendererClose,
  markForceQuitFailed,
} from './quitCoordinationState'

describe('quitCoordinationState', () => {
  it('强杀失败后回到可再次请求关闭的状态，且作废重启意图', () => {
    const next = markForceQuitFailed({
      coordinatedQuit: false,
      forceQuitInProgress: true,
      quitRequestInFlight: true,
      relaunchAfterQuit: true,
    })

    expect(next).toEqual({
      coordinatedQuit: false,
      forceQuitInProgress: false,
      quitRequestInFlight: false,
      relaunchAfterQuit: false,
    })
    // 之后的「退出」能重新发起协调关闭，且不会被当成重启
    expect(canRequestRendererClose(next)).toBe(true)
    expect(canElectronExitImmediately(next)).toBe(false)
  })
})
