import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { OpenAPI } from '@/api'
import { getLogger } from '@/utils/logger'

const logger = getLogger('音频播放器')

export function useAudioPlayer() {
  const { getSettings } = useSettingsApi()
  const currentAudio = ref<HTMLAudioElement | null>(null)
  const isPlaying = ref(false)
  const loading = ref(false)

  /**
   * 停止当前播放的音频
   */
  const stopCurrentAudio = () => {
    if (currentAudio.value) {
      currentAudio.value.pause()
      currentAudio.value.currentTime = 0
      currentAudio.value = null
      isPlaying.value = false
    }
  }

  /**
   * 检查音频文件是否存在
   * @param audioUrl 音频URL
   * @returns 文件是否存在
   */
  const checkAudioExists = async (audioUrl: string): Promise<boolean> => {
    try {
      const response = await fetch(audioUrl, { method: 'HEAD' })
      return response.ok
    } catch {
      return false
    }
  }

  /**
   * 播放音频
   * @param fileName 音频文件名（不含路径和扩展名），例如: "announcement_display" 或 "welcome_back"
   */
  const playSound = async (fileName: string): Promise<boolean> => {
    if (!fileName) {
      logger.warn('音频文件名不能为空')
      return false
    }

    loading.value = true

    try {
      // 首先检查语音设置
      const settings = await getSettings()
      if (!settings?.Voice?.Enabled) {
        logger.info('语音功能已禁用，跳过音频播放')
        return false
      }

      // 停止当前播放的音频
      stopCurrentAudio()

      const baseUrl = OpenAPI.BASE
      let audioUrl: string | null = null

      // 1. 优先检查 both 路径
      const bothUrl = `${baseUrl}/api/res/sounds/both/${fileName}.wav`
      if (await checkAudioExists(bothUrl)) {
        audioUrl = bothUrl
        logger.info(`使用 both 路径播放音频: ${fileName}`)
      } else {
        // 2. 根据语音类型查找对应路径
        const voiceType = settings?.Voice?.Type || 'simple'
        const typeUrl = `${baseUrl}/api/res/sounds/${voiceType}/${fileName}.wav`

        if (await checkAudioExists(typeUrl)) {
          audioUrl = typeUrl
          logger.info(`使用 ${voiceType} 路径播放音频: ${fileName}`)
        } else {
          // 3. 如果都找不到，记录调试日志并返回
          logger.debug(`音频文件未找到: ${fileName} (已尝试 both 和 ${voiceType} 路径)`)
          return false
        }
      }

      // 创建新的音频对象
      const audio = new Audio(audioUrl)
      currentAudio.value = audio

      // 设置音频事件监听器
      audio.addEventListener('loadstart', () => {
        isPlaying.value = true
      })

      audio.addEventListener('ended', () => {
        isPlaying.value = false
        currentAudio.value = null
      })

      audio.addEventListener('error', e => {
        logger.error(`音频播放失败: ${fileName}`, e)
        message.error(`音频播放失败: ${fileName}`)
        isPlaying.value = false
        currentAudio.value = null
      })

      // 播放音频
      await audio.play()
      return true
    } catch (error) {
      logger.error(`播放音频时发生错误: ${fileName}`, error)
      message.error('音频播放失败，请检查网络连接')
      isPlaying.value = false
      currentAudio.value = null
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * 停止播放
   */
  const stopSound = () => {
    stopCurrentAudio()
  }

  return {
    isPlaying,
    loading,
    playSound,
    stopSound,
  }
}
