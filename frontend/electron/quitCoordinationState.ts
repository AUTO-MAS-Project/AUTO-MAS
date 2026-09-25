interface QuitCoordinationState {
  coordinatedQuit: boolean
  forceQuitInProgress: boolean
  quitRequestInFlight: boolean
  relaunchAfterQuit: boolean
}

export function canRequestRendererClose(state: QuitCoordinationState): boolean {
  return !state.coordinatedQuit && !state.forceQuitInProgress && !state.quitRequestInFlight
}

/** 只有 renderer 已完成协调关闭后，Electron 才能真正退出。 */
export function canElectronExitImmediately(state: QuitCoordinationState): boolean {
  return state.coordinatedQuit
}

interface ForceQuitRetryState extends QuitCoordinationState {
  relaunchAfterQuit: boolean
}

/**
 * 最终强杀失败后回到可重试状态。重启意图一并作废：这次重启已经没走成，
 * 若保留标志，用户之后点「退出」会被当成重启。
 */
export function markForceQuitFailed(state: ForceQuitRetryState): ForceQuitRetryState {
  return {
    ...state,
    forceQuitInProgress: false,
    quitRequestInFlight: false,
    relaunchAfterQuit: false,
  }
}
