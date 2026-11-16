import { GetService } from '@/api'
export type { PowerCountdownSnapshot, TaskRuntimeSnapshotItem, TaskRuntimeSnapshot } from '@/api'

/** 初始/重连快照使用生成的契约与客户端；WS 只承载之后的运行事件。 */
export const realtimeSnapshotApi = {
  getPowerCountdown: () =>
    GetService.getPowerCountdownSnapshotApiDispatchPowerCountdownSnapshotGet(),
  getRuntimeTasks: () => GetService.getTaskRuntimeSnapshotApiDispatchRuntimeSnapshotGet(),
}
