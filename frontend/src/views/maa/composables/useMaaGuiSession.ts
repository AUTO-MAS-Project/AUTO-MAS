// MAA 原生设置会话（原生 GUI 配置 / 只读查看）——通用实现见 useNativeGuiSession
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'

export function useMaaGuiSession() {
  const session = useNativeGuiSession({
    loggerName: 'MAA配置会话',
    keys: {
      stopFailed: 'plugins.maa_adapter.edit.maaSessionStopFailed',
      startFailed: 'plugins.maa_adapter.edit.maaSessionStartFailed',
      setupFailed: 'plugins.maa_adapter.edit.maaConfigurationFailedP0',
      opened: 'plugins.maa_adapter.edit.maaSessionOpened',
      viewOpened: 'plugins.maa_adapter.edit.maaViewOpened',
      timeoutWarn: 'plugins.maa_adapter.edit.maaSessionTimeoutWarn',
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
