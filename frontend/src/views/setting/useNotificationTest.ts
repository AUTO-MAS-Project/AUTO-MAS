import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { Service } from '@/api'
import { beginAnalyticsOperation } from '@/utils/analytics'

/** 总体测试响应与逐渠道送达不是同一个口径。 */
export function useNotificationTest(
  logger: Pick<ReturnType<typeof window.electronAPI.getLogger>, 'error'>
) {
  const { t } = useI18n()
  const testingNotify = ref(false)
  const testNotify = async () => {
    const operation = beginAnalyticsOperation('notification_test_finished')
    testingNotify.value = true
    try {
      const res = await Service.testNotifyApiSettingTestNotifyPost()
      operation.finish({
        test_kind: 'configured',
        request_outcome: res?.code === 200 ? 'accepted' : res?.code ? 'rejected' : 'unknown',
      })
      if (res?.code && res.code !== 200)
        message.warning(res?.message || t('setting.toast.testUnknown'))
      else message.success(res?.message || t('setting.toast.testSent'))
    } catch (error) {
      operation.finish({ test_kind: 'configured', request_outcome: 'unknown' })
      logger.error(`测试通知发送失败: ${error instanceof Error ? error.message : String(error)}`)
      message.error(t('setting.toast.testFailed'))
    } finally {
      testingNotify.value = false
    }
  }
  return { testingNotify, testNotify }
}
