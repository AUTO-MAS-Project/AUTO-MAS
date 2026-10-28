// OK-NTE 原生设置会话：生命周期由 useNativeGuiSession 统一管理。
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'
import type { NativeConfigStopAction } from '@/composables/useTaskApi'

export function useOknteGuiSession() {
  const session = useNativeGuiSession({
    loggerName: 'OK-NTE配置会话',
    keys: {
      stopFailed: 'edit.oknteSessionStopFailed',
      startFailed: 'edit.oknteSessionStartFailed',
      setupFailed: 'edit.oknteSessionFailed',
      opened: 'edit.oknteSessionOpened',
      viewOpened: 'edit.oknteViewOpened',
      timeoutWarn: 'edit.oknteSessionTimeoutWarn',
      saved: 'edit.okNteConfigurationThis',
      saveFailed: 'edit.couldNotSaveOk',
    },
  })
  return {
    oknteConfigLoading: session.configLoading,
    oknteWebsocketId: session.taskId,
    showOknteConfigMask: session.showConfigMask,
    showOknteViewMask: session.showViewMask,
    stoppingOknteConfig: session.stopping,
    startSession: session.startSession,
    saveSession: session.saveSession,
    stopSession: (keepOnFailure = false, action: NativeConfigStopAction = 'close') =>
      session.stopSession(keepOnFailure, false, action),
  }
}
