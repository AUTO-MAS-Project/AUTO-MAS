import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { apiRuntime } from '@/api'

const logger = window.electronAPI.getLogger('audio-player')

export function useAudioPlayer() {
  const { getSettings } = useSettingsApi()
  const currentAudio = ref<HTMLAudioElement | null>(null)
  const isPlaying = ref(false)
  const loading = ref(false)

  const stopCurrentAudio = () => {
    if (!currentAudio.value) {
      return
    }

    currentAudio.value.pause()
    currentAudio.value.currentTime = 0
    currentAudio.value = null
    isPlaying.value = false
  }

  const checkAudioExists = async (audioUrl: string): Promise<boolean> => {
    try {
      const response = await fetch(audioUrl, { method: 'HEAD' })
      return response.ok
    } catch {
      return false
    }
  }

  const playSound = async (fileName: string): Promise<boolean> => {
    if (!fileName) {
      logger.warn('Audio file name is empty')
      return false
    }

    loading.value = true

    try {
      const settings = await getSettings()
      if (!settings?.Voice?.Enabled) {
        logger.info('Voice is disabled, skip audio playback')
        return false
      }

      stopCurrentAudio()

      const baseUrl = apiRuntime.baseUrl
      let audioUrl: string | null = null

      const bothUrl = `${baseUrl}/api/res/sounds/both/${fileName}.wav`
      if (await checkAudioExists(bothUrl)) {
        audioUrl = bothUrl
        logger.info(`Use shared sound: ${fileName}`)
      } else {
        const voiceType = settings?.Voice?.Type || 'simple'
        const typeUrl = `${baseUrl}/api/res/sounds/${voiceType}/${fileName}.wav`

        if (await checkAudioExists(typeUrl)) {
          audioUrl = typeUrl
          logger.info(`Use ${voiceType} sound: ${fileName}`)
        } else {
          logger.debug(`Sound file not found: ${fileName}`)
          return false
        }
      }

      const audio = new Audio(audioUrl)
      currentAudio.value = audio

      audio.addEventListener('loadstart', () => {
        isPlaying.value = true
      })

      audio.addEventListener('ended', () => {
        isPlaying.value = false
        currentAudio.value = null
      })

      audio.addEventListener('error', event => {
        const errorMsg = event instanceof Error ? event.message : String(event)
        logger.error(`Audio playback failed: ${fileName} - ${errorMsg}`)
        message.error(`音频播放失败: ${fileName}`)
        isPlaying.value = false
        currentAudio.value = null
      })

      await audio.play()
      return true
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`Failed to play sound: ${fileName} - ${errorMsg}`)
      message.error('音频播放失败，请检查网络连接')
      isPlaying.value = false
      currentAudio.value = null
      return false
    } finally {
      loading.value = false
    }
  }

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
