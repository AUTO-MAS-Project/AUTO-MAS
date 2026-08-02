export interface QuitCoordinationState {
  coordinatedQuit: boolean
  forceQuitInProgress: boolean
  quitRequestInFlight: boolean
}

export function canRequestRendererClose(state: QuitCoordinationState): boolean {
  return !state.coordinatedQuit && !state.forceQuitInProgress && !state.quitRequestInFlight
}

/** 只有 renderer 已完成协调关闭后，Electron 才能真正退出。 */
export function canElectronExitImmediately(state: QuitCoordinationState): boolean {
  return state.coordinatedQuit
}

export function markForceQuitFailed(state: QuitCoordinationState): QuitCoordinationState {
  return {
    ...state,
    forceQuitInProgress: false,
    quitRequestInFlight: false,
  }
}
