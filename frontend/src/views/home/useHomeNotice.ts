import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service } from '@/api/services/Service'
import { useAudioPlayer } from '@/composables/useAudioPlayer'

export const useHomeNotice = () => {
  const logger = window.electronAPI.getLogger('首页')
  const { playSound } = useAudioPlayer()

  const noticeVisible = ref(false)
  const noticeData = ref<Record<string, string>>({})
  const noticeLoading = ref(false)

  const fetchNoticeData = async () => {
    try {
      const response = await Service.getNoticeInfoApiInfoNoticeGetPost()

      if (response.code === 200) {
        if (response.if_need_show && response.data && Object.keys(response.data).length > 0) {
          noticeData.value = response.data
          noticeVisible.value = true
          await playSound('announcement_display')
        }
      } else {
        logger.warn(`获取公告失败: ${response.message}`)
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取公告失败: ${errorMsg}`)
    } finally {
      noticeLoading.value = false
    }
  }

  const onNoticeConfirmed = () => {
    noticeVisible.value = false
  }

  const showNotice = async () => {
    noticeLoading.value = true
    try {
      const response = await Service.getNoticeInfoApiInfoNoticeGetPost()

      if (response.code === 200) {
        if (response.data && Object.keys(response.data).length > 0) {
          noticeData.value = response.data
          noticeVisible.value = true
          await playSound('announcement_display')
        } else {
          message.info(t('home.notice.empty'))
        }
      } else {
        message.error(response.message || t('home.notice.failed'))
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`显示公告失败: ${errorMsg}`)
      message.error(t('home.notice.showFailed'))
    } finally {
      noticeLoading.value = false
    }
  }

  return {
    noticeVisible,
    noticeData,
    noticeLoading,
    fetchNoticeData,
    onNoticeConfirmed,
    showNotice,
  }
}
