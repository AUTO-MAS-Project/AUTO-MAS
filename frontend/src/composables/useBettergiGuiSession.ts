// BetterGI 原生设置会话（原生 GUI 直控）
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useWebSocket } from '@/composables/useWebSocket'

const logger = window.electronAPI.getLogger('BetterGI配置会话')

/**
 * BetterGI 原生设置会话：打开 BetterGI 原生界面并遮罩等待，保存快照后结束会话。
 *
 * 抽自此前的日志与进度：`BetterGIUserEdit.vue` 只负责组合各区域，会话生命周期
 * （WebSocket 订阅、遮罩、30 分钟超时自动保存、卸载清理）全部收敛于此。
 */
export function useBettergiGuiSession() {
  const { subscribe, unsubscribe } = useWebSocket()

  const bettergiConfigLoading = ref(false)
  const bettergiSubscriptionId = ref<string | null>(null)
  const bettergiWebsocketId = ref<string | null>(null)
  const showBettergiConfigMask = ref(false)
  const stoppingBettergiConfig = ref(false)

  let bettergiConfigTimeout: number | null = null

  const clearSession = () => {
    if (bettergiSubscriptionId.value) {
      unsubscribe(bettergiSubscriptionId.value)
      bettergiSubscriptionId.value = null
    }
    bettergiWebsocketId.value = null
    showBettergiConfigMask.value = false
    if (bettergiConfigTimeout) {
      window.clearTimeout(bettergiConfigTimeout)
      bettergiConfigTimeout = null
    }
  }

  const stopSession = async (keepOnFailure = false): Promise<boolean> => {
    const taskId = bettergiWebsocketId.value
    if (!taskId) {
      clearSession()
      return true
    }
    if (stoppingBettergiConfig.value) return false

    stoppingBettergiConfig.value = true
    try {
      const response = await Service.stopTaskApiDispatchStopPost({ taskId })
      if (response.code !== 200) {
        throw new Error(response.message || '停止 BetterGI 设置失败')
      }
      clearSession()
      return true
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      if (keepOnFailure) return false
      clearSession()
      return false
    } finally {
      stoppingBettergiConfig.value = false
    }
  }

  const startSession = async (userId: string): Promise<void> => {
    try {
      bettergiConfigLoading.value = true
      const response = await Service.addTaskApiDispatchStartPost({
        taskId: userId,
        mode: TaskCreateIn.mode.SCRIPT_CONFIG,
      })
      if (response.code !== 200 || !response.taskId) {
        throw new Error(response.message || '启动 BetterGI 设置失败')
      }

      showBettergiConfigMask.value = true
      bettergiWebsocketId.value = response.taskId
      const subscriptionId = subscribe({ id: response.taskId }, (wsMessage: any) => {
        if (wsMessage.type === 'error') {
          message.error(`BetterGI 设置连接失败: ${String(wsMessage.data)}`)
          void stopSession()
          return
        }
        if (wsMessage.type === 'Info' && wsMessage.data?.Error) {
          message.error(`BetterGI 设置失败: ${String(wsMessage.data.Error)}`)
          void stopSession()
          return
        }
        if (wsMessage.type === 'Signal' && wsMessage.data?.Accomplish !== undefined) {
          clearSession()
        }
      })
      bettergiSubscriptionId.value = subscriptionId
      message.success('已打开 BetterGI 设置')
      bettergiConfigTimeout = window.setTimeout(saveSession, 30 * 60 * 1000)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : '启动 BetterGI 设置失败')
      clearSession()
    } finally {
      bettergiConfigLoading.value = false
    }
  }

  const saveSession = async () => {
    if (!bettergiWebsocketId.value) return
    if (await stopSession(true)) {
      message.success('BetterGI 设置已保存')
    } else {
      message.error('保存 BetterGI 设置失败')
    }
  }

  const dispose = () => {
    void stopSession()
  }

  return {
    bettergiConfigLoading,
    bettergiWebsocketId,
    showBettergiConfigMask,
    startSession,
    saveSession,
    stopSession,
    dispose,
  }
}
