// BetterGI 原生设置会话（原生 GUI 直控 / 只读查看）——通用实现见 useNativeGuiSession
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'

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
    },
  })
  return {
    state: session.state,
    bettergiConfigLoading: session.configLoading,
    bettergiWebsocketId: session.taskId,
    showBettergiConfigMask: session.showConfigMask,
    showBettergiViewMask: session.showViewMask,
    currentSessionViewOnly: session.viewOnly,
    stoppingBettergiConfig: session.stopping,
    startSession: session.startSession,
    saveSession: session.saveSession,
    stopSession: session.stopSession,
    querySession: session.querySession,
    // onUnmounted 依赖「先停会话再归档」的时序：这里必须 await 真正的收尾
    dispose: session.dispose,
  }
}
