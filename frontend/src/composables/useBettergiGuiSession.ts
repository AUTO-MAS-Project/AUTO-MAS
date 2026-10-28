// BetterGI 原生设置会话：生命周期由 useNativeGuiSession 统一管理。
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'
import type { NativeConfigStopAction } from '@/composables/useTaskApi'

export function useBettergiGuiSession() {
  const session = useNativeGuiSession({
    loggerName: 'BetterGI配置会话',
    keys: {
      stopFailed: 'core.edit.bettergiStopFailed',
      startFailed: 'core.edit.bettergiStartFailed',
      setupFailed: 'core.edit.bettergiSessionFailed',
      opened: 'core.edit.bettergiSessionOpened',
      viewOpened: 'core.edit.bettergiViewOpened',
      timeoutWarn: 'core.edit.bettergiSessionTimeoutWarn',
      saved: 'core.edit.bettergiSettingsSaved',
      saveFailed: 'core.edit.bettergiSettingsSaveFailed',
      viewStartFailed: 'core.edit.bettergiViewStartFailed',
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
