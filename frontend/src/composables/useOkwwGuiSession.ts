// ok-ww 原生设置会话（原生 GUI 配置 / 只读查看）——通用实现见 useNativeGuiSession
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'

export function useOkwwGuiSession() {
  const session = useNativeGuiSession({
    loggerName: 'ok-ww配置会话',
    keys: {
      stopFailed: 'core.edit.okwwSessionStopFailed',
      startFailed: 'core.edit.okwwSessionStartFailed',
      setupFailed: 'core.edit.okWwSetupFailed',
      opened: 'core.edit.okwwSessionOpened',
      viewOpened: 'core.edit.okwwViewOpened',
      timeoutWarn: 'core.edit.okwwSessionTimeoutWarn',
      saved: 'core.edit.okWwSettingsSaved',
      saveFailed: 'core.edit.couldNotSaveOk2',
    },
  })
  return {
    okwwConfigLoading: session.configLoading,
    okwwTaskId: session.taskId,
    showOkwwConfigMask: session.showConfigMask,
    showOkwwViewMask: session.showViewMask,
    stoppingOkwwConfig: session.stopping,
    startSession: session.startSession,
    saveSession: session.saveSession,
    stopSession: session.stopSession,
  }
}
