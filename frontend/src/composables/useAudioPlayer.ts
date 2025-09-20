import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { API_ENDPOINTS } from '@/config/mirrors'

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
   * 播放音频
   * @param soundPath 音频路径，例如: "noisy/welcome" 或 "welcome"
   */
  const playSound = async (soundPath: string): Promise<boolean> => {
    if (!soundPath) {
      console.warn('音频路径不能为空')
      return false
    }

    loading.value = true

    try {
      // 首先检查语音设置
      const settings = await getSettings()
      if (!settings?.Voice?.Enabled) {
        console.log('语音功能已禁用，跳过音频播放')
        return false
      }

      // 停止当前播放的音频
      stopCurrentAudio()

      // 构建音频URL
      const audioUrl = `${API_ENDPOINTS.local}/api/res/sounds/${soundPath}.wav`
      
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

      audio.addEventListener('error', (e) => {
        console.error('音频播放失败:', e)
        message.error(`音频播放失败: ${soundPath}`)
        isPlaying.value = false
        currentAudio.value = null
      })

      // 播放音频
      await audio.play()
      return true

    } catch (error) {
      console.error('播放音频时发生错误:', error)
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
    stopSound
  }
}