import type { WSTaskLogUpdatedData } from '@/services/websocket/types'

// 与后端单次推送上限一致；buffer 超过就丢头留尾
export const LOG_BUFFER_MAX_CHARS = 200000

export interface TaskLogBufferState {
  // 从 task.log.updated 增量拼出来的完整日志（≤ LOG_BUFFER_MAX_CHARS，丢头留尾）
  logBuffer: string
  // 最近一次应用的日志 seq；为空表示没有基线，下一条增量到达时要先拉快照重建
  logSeq?: number
}

type TaskLogUpdateResult = 'replace' | 'append' | 'resync'

export const trimLogBuffer = (content: string) =>
  content.length <= LOG_BUFFER_MAX_CHARS ? content : content.slice(-LOG_BUFFER_MAX_CHARS)

/**
 * 把一条 task.log.updated 应用到 buffer。
 *
 * append=false 整体替换并记下 seq；append=true 且 seq 紧接上一条则追加；
 * 否则（没有基线、漏了消息）清掉 seq 并返回 'resync'，调用方去拉快照重建，本条丢弃。
 */
export const applyTaskLogUpdate = (
  state: TaskLogBufferState,
  data: WSTaskLogUpdatedData
): TaskLogUpdateResult => {
  if (data.append) {
    if (state.logSeq === undefined || data.seq !== state.logSeq + 1) {
      state.logSeq = undefined
      return 'resync'
    }
    state.logBuffer = trimLogBuffer(state.logBuffer + data.log)
    state.logSeq = data.seq
    return 'append'
  }
  state.logBuffer = trimLogBuffer(data.log)
  state.logSeq = data.seq
  return 'replace'
}
