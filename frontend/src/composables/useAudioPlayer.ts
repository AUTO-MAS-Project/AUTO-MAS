import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { OpenAPI, type GlobalConfig } from '@/api'
const logger = window.electronAPI.getLogger('音频播放器')

type VoiceSettings = NonNullable<GlobalConfig['Voice']>

// 语音设置整个会话基本不变，缓存起来；设置页保存 Voice 后调用 invalidateVoiceSettingsCache 失效
let cachedVoiceSettings: VoiceSettings | null | undefined
let voiceSettingsRequest: Promise<VoiceSettings | null> | null = null
// 已探到的音频地址：文件不会在运行期变化，探到一次就够
const resolvedAudioUrls = new Map<string, string>()

export const invalidateVoiceSettingsCache = () => {
  cachedVoiceSettings = undefined
}

const getVoiceSettings = (): Promise<VoiceSettings | null> => {
  if (cachedVoiceSettings !== undefined) return Promise.resolve(cachedVoiceSettings)
  if (!voiceSettingsRequest) {
    voiceSettingsRequest = useSettingsApi()
      .getSettings()
      .then(settings => {
        const voice = settings?.Voice ?? null
        // 拉取失败不缓存，下次再试
        if (settings) cachedVoiceSettings = voice
        return voice
      })
      .finally(() => {
        voiceSettingsRequest = null
      })
  }
  return voiceSettingsRequest
}

export function useAudioPlayer() {
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
      const voice = await getVoiceSettings()
      if (!voice?.Enabled) {
        logger.info('语音功能已禁用，跳过音频播放')
        return false
      }

      // 停止当前播放的音频
      stopCurrentAudio()

      const baseUrl = OpenAPI.BASE
      const voiceType = voice.Type || 'simple'
      const cacheKey = `${voiceType}/${fileName}`
      let audioUrl = resolvedAudioUrls.get(cacheKey) ?? null

      if (!audioUrl) {
        // 1. 优先检查 both 路径
        const bothUrl = `${baseUrl}/api/res/sounds/both/${fileName}.wav`
        if (await checkAudioExists(bothUrl)) {
          audioUrl = bothUrl
          logger.info(`使用 both 路径播放音频: ${fileName}`)
        } else {
          // 2. 根据语音类型查找对应路径
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
        resolvedAudioUrls.set(cacheKey, audioUrl)
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
        const errorMsg = e instanceof Error ? e.message : String(e)
        logger.error(`音频播放失败: ${fileName} - ${errorMsg}`)
        message.error(t('misc.audioPlaybackFailedP0', { p0: fileName }))
        isPlaying.value = false
        currentAudio.value = null
      })

      // 播放音频
      await audio.play()
      return true
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`播放音频时发生错误: ${fileName} - ${errorMsg}`)
      message.error(t('misc.audioPlaybackFailedCheck'))
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
