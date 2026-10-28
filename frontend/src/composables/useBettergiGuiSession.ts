// BetterGI 原生设置会话：生命周期由 useNativeGuiSession 统一管理。
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'
import type { NativeConfigStopAction } from '@/composables/useTaskApi'

export function useBettergiGuiSession() {
  const session = useNativeGuiSession({
    loggerName: 'BetterGI配置会话',
    keys: {
      stopFailed: 'edit.bettergiStopFailed',
      startFailed: 'edit.bettergiStartFailed',
      setupFailed: 'edit.bettergiSessionFailed',
      opened: 'edit.bettergiSessionOpened',
      viewOpened: 'edit.bettergiViewOpened',
      timeoutWarn: 'edit.bettergiSessionTimeoutWarn',
      saved: 'edit.bettergiSettingsSaved',
      saveFailed: 'edit.bettergiSettingsSaveFailed',
      viewStartFailed: 'edit.bettergiViewStartFailed',
    },
  })
  return {
    bettergiConfigLoading: session.configLoading,
    bettergiWebsocketId: session.taskId,
    showBettergiConfigMask: session.showConfigMask,
    showBettergiViewMask: session.showViewMask,
    stoppingBettergiConfig: session.stopping,
    currentSessionViewOnly: session.currentSessionViewOnly,
    startSession: session.startSession,
    saveSession: session.saveSession,
    stopSession: (keepOnFailure = false, action: NativeConfigStopAction = 'close') =>
      session.stopSession(keepOnFailure, false, action),
    dispose: session.dispose,
  }
}
