/**
 * 游戏社区：手动触发一次签到。
 *
 * 签到接口的 409 表示已有签到在跑（自动签到或上一次手动签到），
 * 这不是错误，所以单独提示并直接返回；其余失败才交给调用方提示。
 */
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { useGameSignApi } from './useGameSignApi'

export function useManualSign(onFinished?: () => Promise<void> | void) {
  const logger = window.electronAPI.getLogger('游戏社区')
  const { manualSign } = useGameSignApi()
  const signLoading = ref(false)

  const run = async (): Promise<void> => {
    signLoading.value = true
    try {
      const response = await manualSign()
      if (response.code === 409) {
        logger.warn('自动签到正在执行，已跳过本次手动签到')
        message.warning(t('core.gamesign.toast.autoSignRunning'))
        return
      }
      if (response.code !== 200 && response.code !== 0) {
        throw new Error(response.message || t('core.gamesign.toast.signFailed'))
      }
      if (response.status === 'warning') {
        message.warning(t('core.gamesign.toast.signPartialNotify'))
      } else {
        message.success(t('core.gamesign.toast.signDone'))
      }
      // 结果由后端写入配置，这里立刻刷新一次，不必等下一轮轮询
      await onFinished?.()
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error)
      logger.error(`手动签到失败: ${errorMessage}`)
      message.error(t('core.gamesign.toast.signError', { error: errorMessage }))
    } finally {
      signLoading.value = false
    }
  }

  return { signLoading, run }
}
