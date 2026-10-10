import {
  BUILTIN_PRESS_SOUNDS,
  isBuiltinPressSound,
  type PressSoundPhase,
  type PressSoundPreset,
} from '@/types/pressSound'

/**
 * 常驻的音频元素，按 URL 缓存。不复用元素的话，快点一次就新建一个 Audio，
 * 前一声没放完后一声又叠上来；复用之后每次播放前把 currentTime 归零，
 * 等于把上一声掐掉重放，任意快点都只有一声在响。
 */
const elements = new Map<string, HTMLAudioElement>()
/** 用户导入音频的 data URL 缓存，按文件路径记 */
const customUrlCache = new Map<string, string>()

/** 当前这套内置音效组的按下 / 松开元素 */
let pressElement: HTMLAudioElement | null = null
let releaseElement: HTMLAudioElement | null = null
/** 松手时按压音还没放完，就把「接在它后面播」这个动作挂在这里 */
let pendingRelease: (() => void) | null = null

const logger = window.electronAPI.getLogger('按压音效')

function builtinUrl(file: string): string {
  // base 是 './'：dev 下解析成 http://127.0.0.1:5173/sounds/x.mp3，打包后解析成相对 index.html 的路径
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

function elementFor(url: string): HTMLAudioElement {
  let element = elements.get(url)
  if (!element) {
    element = new Audio(url)
    element.preload = 'auto'
    elements.set(url, element)
  }
  return element
}

/** 从头播；currentTime 归零会顺手掐掉这个元素上还在响的那一声 */
function playFromStart(element: HTMLAudioElement, volume: number): void {
  element.volume = volume
  element.currentTime = 0
  const played = element.play()
  if (played) {
    void played.catch(() => {})
  }
}

/** 丢掉排队中的松开音（重新按下、或按压音已被打断时用） */
function dropPendingRelease(): void {
  if (pressElement && pendingRelease) {
    pressElement.removeEventListener('ended', pendingRelease)
  }
  pendingRelease = null
}

function stopRelease(): void {
  if (releaseElement) {
    releaseElement.pause()
    releaseElement.currentTime = 0
  }
}

/** 播一次按压音效；真实按压与设置页的「试听」共用这一条路径 */
export async function playPressSound(
  preset: PressSoundPreset,
  volume: number,
  customPath: string,
  phase: PressSoundPhase = 'press'
): Promise<void> {
  if (isBuiltinPressSound(preset)) {
    const builtin = BUILTIN_PRESS_SOUNDS.find(item => item.value === preset)
    if (!builtin) {
      return
    }

    if (phase === 'press') {
      dropPendingRelease()
      stopRelease()
      pressElement = elementFor(builtinUrl(builtin.press))
      releaseElement = elementFor(builtinUrl(builtin.release))
      playFromStart(pressElement, volume)
      return
    }

    if (!releaseElement) {
      return
    }

    // 手快的时候按压音还没放完：等它播完再接松开音，两声不会叠在一起
    if (pressElement && !pressElement.paused && !pressElement.ended) {
      dropPendingRelease()
      const element = releaseElement
      const fire = (): void => {
        pendingRelease = null
        playFromStart(element, volume)
      }
      pendingRelease = fire
      pressElement.addEventListener('ended', fire, { once: true })
      return
    }

    dropPendingRelease()
    playFromStart(releaseElement, volume)
    return
  }

  // 自定义音效只导入了一个文件，松开时不再重复响一次
  if (phase === 'release' || !customPath) {
    return
  }

  const url = await resolveCustomUrl(customPath)
  if (!url) {
    return
  }

  dropPendingRelease()
  pressElement = null
  stopRelease()
  playFromStart(elementFor(url), volume)
}
