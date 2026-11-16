// MAA 原生设置会话（原生 GUI 配置 / 只读查看）——通用实现见 useNativeGuiSession
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'

export function useMaaGuiSession() {
  const session = useNativeGuiSession({
    loggerName: 'MAA配置会话',
    keys: {
      stopFailed: 'core.edit.maaSessionStopFailed',
      startFailed: 'core.edit.maaSessionStartFailed',
      setupFailed: 'core.edit.maaConfigurationFailedP0',
      opened: 'core.edit.maaSessionOpened',
      viewOpened: 'core.edit.maaViewOpened',
      timeoutWarn: 'core.edit.maaSessionTimeoutWarn',
      saved: 'core.edit.configurationThisUserWas',
      saveFailed: 'core.edit.couldNotSaveMaa',
    },
  })
  return {
    maaConfigLoading: session.configLoading,
    maaTaskId: session.taskId,
    showMaaConfigMask: session.showConfigMask,
    showMaaViewMask: session.showViewMask,
    stoppingMaaConfig: session.stopping,
    startSession: session.startSession,
    saveSession: session.saveSession,
    stopSession: session.stopSession,
  }
}
