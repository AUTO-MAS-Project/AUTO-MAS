// ZZZ-OD 原生设置会话：生命周期由 useNativeGuiSession 统一管理。
// YAML 是唯一事实源，GUI 保存即落盘；这里只声明原生实例索引，不承接配置写回。
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'
import type { NativeConfigStopAction, TaskTargetKind } from '@/composables/useTaskApi'

export function useZzzodGuiSession() {
  const session = useNativeGuiSession({
    loggerName: 'ZZZ-OD配置会话',
    keys: {
      stopFailed: 'core.edit.zzzodStopFailed',
      startFailed: 'core.edit.zzzodStartFailed',
      setupFailed: 'core.edit.zzzodSessionFailed',
      opened: 'core.edit.zzzodSessionOpened',
      viewOpened: 'core.edit.zzzodViewOpened',
      timeoutWarn: 'core.edit.zzzodSessionTimeoutWarn',
      saved: 'core.edit.zzzodSettingsSaved',
      saveFailed: 'core.edit.zzzodSettingsSaveFailed',
    },
  })
  return {
    zzzodConfigLoading: session.configLoading,
    zzzodWebsocketId: session.taskId,
    showZzzodConfigMask: session.showConfigMask,
    showZzzodViewMask: session.showViewMask,
    stoppingZzzodConfig: session.stopping,
    startSession: (
      taskId: string,
      viewOnly = false,
      instanceIdx?: number | null,
      targetKind: TaskTargetKind = 'unknown'
    ) =>
      session.startSession(taskId, viewOnly, targetKind, { instanceIdx: instanceIdx ?? undefined }),
    saveSession: session.saveSession,
    stopSession: (keepOnFailure = false, action: NativeConfigStopAction = 'close') =>
      session.stopSession(keepOnFailure, false, action),
  }
}
