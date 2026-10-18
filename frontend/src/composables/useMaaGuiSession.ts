// MAA 原生设置会话（原生 GUI 配置 / 只读查看）——通用实现见 useNativeGuiSession
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'

export function useMaaGuiSession() {
  const session = useNativeGuiSession({
    loggerName: 'MAA配置会话',
    keys: {
      stopFailed: 'edit.maaSessionStopFailed',
      startFailed: 'edit.maaSessionStartFailed',
      setupFailed: 'edit.maaConfigurationFailedP0',
      opened: 'edit.maaSessionOpened',
      viewOpened: 'edit.maaViewOpened',
      timeoutWarn: 'edit.maaSessionTimeoutWarn',
      saved: 'edit.configurationThisUserWas',
      saveFailed: 'edit.couldNotSaveMaa',
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
