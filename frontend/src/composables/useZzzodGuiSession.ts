// ZZZ-OD 原生设置会话（原生 GUI 直控 / 只读查看）——通用实现见 useNativeGuiSession
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'

export function useZzzodGuiSession() {
  const session = useNativeGuiSession({
    loggerName: 'ZZZ-OD配置会话',
    keys: {
      stopFailed: 'edit.zzzodStopFailed',
      startFailed: 'edit.zzzodStartFailed',
      setupFailed: 'edit.zzzodSessionFailed',
      opened: 'edit.zzzodSessionOpened',
      viewOpened: 'edit.zzzodViewOpened',
      timeoutWarn: 'edit.zzzodSessionTimeoutWarn',
      saved: 'edit.zzzodSettingsSaved',
    },
  })
  return {
    state: session.state,
    zzzodConfigLoading: session.configLoading,
    zzzodWebsocketId: session.taskId,
    showZzzodConfigMask: session.showConfigMask,
    showZzzodViewMask: session.showViewMask,
    stoppingZzzodConfig: session.stopping,
    // zzz-od 支持多实例：原生启动请求要带上实例序号
    startSession: (taskId: string, viewOnly = false, instanceIdx?: number | null) =>
      session.startSession(taskId, viewOnly, instanceIdx),
    saveSession: session.saveSession,
    stopSession: session.stopSession,
    querySession: session.querySession,
  }
}
