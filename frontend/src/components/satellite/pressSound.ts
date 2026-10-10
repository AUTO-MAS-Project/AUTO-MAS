import {
  BUILTIN_PRESS_SOUNDS,
  isBuiltinPressSound,
  type PressSoundPreset,
} from '@/types/pressSound'

/** 正在播的音效。连点时会同时存在好几个，各自播完释放，不互相打断 */
const active = new Set<HTMLAudioElement>()
/** 用户导入音频的 data URL 缓存，按文件路径记 */
const customUrlCache = new Map<string, string>()

const logger = window.electronAPI.getLogger('按压音效')

function builtinUrl(file: string): string {
  // base 是 './'：dev 下解析成 http://127.0.0.1:5173/sounds/x.wav，打包后解析成相对 index.html 的路径
  return `${import.meta.env.BASE_URL}sounds/${file}`
}

function mimeFor(filePath: string): string {
  const extension = filePath.split('.').pop()?.toLowerCase() ?? ''
  switch (extension) {
    case 'mp3':
      return 'audio/mpeg'
    case 'ogg':
      return 'audio/ogg'
    case 'm4a':
    case 'aac':
      return 'audio/mp4'
    case 'flac':
      return 'audio/flac'
    default:
      return 'audio/wav'
  }
}

async function resolveCustomUrl(filePath: string): Promise<string | null> {
  const cached = customUrlCache.get(filePath)
  if (cached) {
    return cached
  }

  try {
    // 渲染进程读不到磁盘音频，交给主进程读成 base64 再当 data URL 用
    const base64 = await window.electronAPI.readFileBase64(filePath)
    if (!base64) {
      return null
    }

    const url = `data:${mimeFor(filePath)};base64,${base64}`
    customUrlCache.set(filePath, url)
    return url
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    logger.warn(`读取自定义音效失败（${filePath}）：${message}`)
    return null
  }
}

function play(url: string, volume: number): void {
  const audio = new Audio(url)
  audio.volume = volume
  active.add(audio)

  const release = (): void => {
    active.delete(audio)
  }
  audio.onended = release
  audio.onerror = release
  void audio.play().catch(release)
}

/** 播一次按压音效；真实按压与设置页的「试听」共用这一条路径 */
export async function playPressSound(
  preset: PressSoundPreset,
  volume: number,
  customPath: string
): Promise<void> {
  if (isBuiltinPressSound(preset)) {
    const builtin = BUILTIN_PRESS_SOUNDS.find(item => item.value === preset)
    if (!builtin) {
      return
    }

    play(builtinUrl(builtin.file), volume)
    return
  }

  if (!customPath) {
    return
  }

  const url = await resolveCustomUrl(customPath)
  if (url) {
    play(url, volume)
  }
}
