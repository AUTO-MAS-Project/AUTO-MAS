// MaaEnd 原生设置会话（原生 GUI 配置 / 只读查看）——通用实现见 useNativeGuiSession
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'

export function useMaaEndGuiSession() {
  const session = useNativeGuiSession({
    loggerName: 'MaaEnd配置会话',
    keys: {
      stopFailed: 'edit.maaendSessionStopFailed',
      startFailed: 'edit.maaendSessionStartFailed',
      setupFailed: 'edit.maaendConfigurationErrorP0',
      opened: 'edit.maaendSessionOpened',
      viewOpened: 'edit.maaendViewOpened',
      timeoutWarn: 'edit.maaendSessionTimeoutWarn',
      saved: 'edit.maaendConfigurationSaved',
      saveFailed: 'edit.maaendSessionSaveFailed',
    },
  })
  return {
    maaEndConfigLoading: session.configLoading,
    maaEndTaskId: session.taskId,
    showMaaEndConfigMask: session.showConfigMask,
    showMaaEndViewMask: session.showViewMask,
    stoppingMaaEndConfig: session.stopping,
    startSession: session.startSession,
    saveSession: session.saveSession,
    stopSession: session.stopSession,
  }
}
