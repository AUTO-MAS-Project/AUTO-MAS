import { onUnmounted, reactive } from 'vue'
import { message } from 'ant-design-vue'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useWebSocket } from '@/composables/useWebSocket'
import type { Script } from '@/types/script'

const logger = window.electronAPI.getLogger('脚本配置会话')

export type ScriptConfigSessionKind = 'SRC' | 'MaaEnd'

export interface ScriptConfigSessionState {
  /** 当前激活的脚本 ID -> 会话信息映射 */
  activeConnections: Map<string, { subscriptionId: string; websocketId: string }>
  /** 当前正在配置的脚本（仅一个） */
  currentScript: Script | null
  /** 当前正在配置的脚本类型，用于决定 mask 文案 */
  currentKind: ScriptConfigSessionKind | null
}

export interface ScriptConfigSessionOptions {
  /** 调用 startSession 前对脚本做可用性检查，返回 false 时直接返回 */
  ensureAvailable?: (script: Script) => boolean
  /** 配置会话最长持续时长（毫秒），默认 30 分钟 */
  timeoutMs?: number
}

export interface ScriptConfigSessionHandle {
  state: ScriptConfigSessionState
  /** 当前是否有任意脚本正在配置 */
  hasActiveSession: () => boolean
  /** 当前给定脚本是否正在配置 */
  isActive: (scriptId: string) => boolean
  /** 启动配置会话；返回是否成功启动 */
  startSession: (script: Script, kind: ScriptConfigSessionKind) => Promise<boolean>
  /** 保存配置并结束会话；返回是否成功 */
  saveSession: (script: Script) => Promise<boolean>
  /** 清理全部会话状态；用于页面卸载或外部重置 */
  cleanup: () => void
}

const DEFAULT_TIMEOUT_MS = 30 * 60 * 1000

/**
 * 把 SRC / MaaEnd 配置会话的 mask 状态、WebSocket 订阅、超时清理与错误回滚
 * 封装为 composable，使 Scripts.vue 不再直接持有这些副作用。
 *
 * 设计原则：
 * - 状态字段保持与原 Scripts.vue 一致（activeConnections Map、currentScript、kind）。
 * - WS 消息处理只负责状态更新与用户提示，业务回滚通过 cleanup 单点完成。
 * - 超时与 unmount 都通过 cleanup 单点清理，避免重复 unsubscribe。
 */
export function useScriptConfigSession(
  options: ScriptConfigSessionOptions = {}
): ScriptConfigSessionHandle {
  const { ensureAvailable, timeoutMs = DEFAULT_TIMEOUT_MS } = options
  const { subscribe, unsubscribe } = useWebSocket()

  const state: ScriptConfigSessionState = reactive({
    activeConnections: new Map(),
    currentScript: null,
    currentKind: null,
  })

  // 保存 timeout 句柄，便于 cleanup 时统一清理
  const timeoutHandles = new Map<string, ReturnType<typeof setTimeout>>()

  const hasActiveSession = () => state.activeConnections.size > 0

  const isActive = (scriptId: string) => state.activeConnections.has(scriptId)

  const clearTimeoutFor = (scriptId: string) => {
    const handle = timeoutHandles.get(scriptId)
    if (handle !== undefined) {
      clearTimeout(handle)
      timeoutHandles.delete(scriptId)
    }
  }

  const clearConnection = (scriptId: string) => {
    clearTimeoutFor(scriptId)
    const connection = state.activeConnections.get(scriptId)
    if (connection) {
      unsubscribe(connection.subscriptionId)
      state.activeConnections.delete(scriptId)
    }
    if (state.currentScript?.id === scriptId) {
      state.currentScript = null
      state.currentKind = null
    }
  }

  const handleSessionMessage = (
    script: Script,
    kind: ScriptConfigSessionKind,
    wsMessage: unknown,
    subscriptionId: string
  ) => {
    if (!wsMessage || typeof wsMessage !== 'object') return
    const envelope = wsMessage as { type?: string; data?: any }

    if (envelope.type === 'error') {
      const data = envelope.data
      const errorMsg = data instanceof Error ? data.message : String(data ?? '未知错误')
      logger.error(`脚本 ${script.name} 连接错误: ${errorMsg}`)
      message.error(`${kind === 'SRC' ? 'SRC' : 'MaaEnd'} 配置连接失败: ${errorMsg}`)
      clearConnection(script.id)
      return
    }

    // Info 类型错误：显示错误但保持订阅，等待 Signal 完成
    if (envelope.type === 'Info' && envelope.data && envelope.data.Error) {
      const errorData = envelope.data.Error
      const errorMsg = errorData instanceof Error ? errorData.message : String(errorData)
      logger.error(`脚本 ${script.name} 配置异常: ${errorMsg}`)
      message.error(`${kind === 'SRC' ? 'SRC' : 'MaaEnd'} 配置失败: ${errorMsg}`)
      return
    }

    // Signal 类型 Accomplish：任务结束，清理会话
    if (envelope.type === 'Signal' && envelope.data && envelope.data.Accomplish !== undefined) {
      logger.info(`脚本 ${script.name} 配置任务已结束`)
      const result = envelope.data.Accomplish
      if (typeof result === 'string' && !result.includes('异常') && !result.includes('错误')) {
        message.success(`${script.name} 配置已完成`)
      }
      // 仅清理当前订阅，避免误清理其他并发会话
      if (state.activeConnections.get(script.id)?.subscriptionId === subscriptionId) {
        clearConnection(script.id)
      }
    }
  }

  const startSession = async (script: Script, kind: ScriptConfigSessionKind): Promise<boolean> => {
    if (ensureAvailable && !ensureAvailable(script)) return false

    if (state.activeConnections.has(script.id)) {
      message.warning('该脚本已在配置中，请先保存当前配置')
      return false
    }

    try {
      const response = await Service.addTaskApiDispatchStartPost({
        taskId: script.id,
        mode: TaskCreateIn.mode.SCRIPT_CONFIG,
      })

      if (response.code !== 200) {
        message.error(response.message || `启动${kind}配置失败`)
        return false
      }

      state.currentScript = script
      state.currentKind = kind

      const subscriptionId = subscribe({ id: response.taskId }, wsMessage => {
        handleSessionMessage(script, kind, wsMessage, subscriptionId)
      })

      state.activeConnections.set(script.id, {
        subscriptionId,
        websocketId: response.taskId,
      })

      message.success(`已启动 ${script.name} 的 ${kind} 配置`)

      // 30 分钟自动断开，避免后端任务悬挂
      const handle = setTimeout(() => {
        if (state.activeConnections.has(script.id)) {
          clearConnection(script.id)
          message.info(`${script.name} 配置会话已超时断开`)
        }
      }, timeoutMs)
      timeoutHandles.set(script.id, handle)

      return true
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`启动${kind}配置失败: ${errorMsg}`)
      message.error(`启动${kind}配置失败: ${errorMsg}`)
      // 失败时回滚 mask 状态，避免页面被永久锁定
      if (state.currentScript?.id === script.id) {
        state.currentScript = null
        state.currentKind = null
      }
      return false
    }
  }

  const saveSession = async (script: Script): Promise<boolean> => {
    const connection = state.activeConnections.get(script.id)
    if (!connection) {
      message.error('未找到活动的配置会话')
      return false
    }

    try {
      const response = await Service.stopTaskApiDispatchStopPost({
        taskId: connection.websocketId,
      })

      if (response.code !== 200) {
        message.error(response.message || '保存配置失败')
        return false
      }

      clearConnection(script.id)
      message.success(`${script.name} 的配置已保存`)
      return true
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存${state.currentKind ?? ''}配置失败: ${errorMsg}`)
      message.error(`保存配置失败: ${errorMsg}`)
      return false
    }
  }

  const cleanup = () => {
    // 复制 keys 避免在迭代中修改 Map
    const scriptIds = [...state.activeConnections.keys()]
    for (const scriptId of scriptIds) {
      clearConnection(scriptId)
    }
    state.currentScript = null
    state.currentKind = null
  }

  onUnmounted(() => {
    cleanup()
  })

  return {
    state,
    hasActiveSession,
    isActive,
    startSession,
    saveSession,
    cleanup,
  }
}
