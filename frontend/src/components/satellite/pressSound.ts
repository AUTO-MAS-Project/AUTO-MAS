import {
  BUILTIN_PRESS_SOUNDS,
  isBuiltinPressSound,
  MAX_PRESS_SOUND_BYTES,
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
let preparingPress: Promise<void> = Promise.resolve()
let pressRequest = 0

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
      return 'audio/mp4'
    // 原始 ADTS 的 .aac 不是 MP4 容器，标成 audio/mp4 解码器会直接拒绝
    case 'aac':
      return 'audio/aac'
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
    // 渲染进程读不到磁盘音频，交给主进程读成 base64 再当 data URL 用；
    // 上限一并交给它挡在前面，读的时候就不会有超大文件进内存
    const { base64, size } = await window.electronAPI.readFileBase64(
      filePath,
      MAX_PRESS_SOUND_BYTES
    )
    if (!base64 || size > MAX_PRESS_SOUND_BYTES) {
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

/** 重新导入同一个路径时调用：文件内容可能已经换了，缓存里的 data URL 要作废 */
export function clearCustomSoundCache(filePath?: string): void {
  if (filePath === undefined) {
    customUrlCache.clear()
    return
  }

  customUrlCache.delete(filePath)
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

/** 丢掉排队中的松开音（重新按下、按压音被打断，或状态不再允许播放时用） */
export function dropPendingRelease(): void {
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

export interface PressSoundPlayOptions {
  preset: PressSoundPreset
  volume: number
  /** 自定义音效的「按下」文件；custom 与 customPair 都用它 */
  customPath?: string
  /** 自定义两个文件时「松开」的文件，只有 customPair 用 */
  customReleasePath?: string
  phase?: PressSoundPhase
  /** 自定义音效要等主进程把文件读回来，这中间状态可能已经变了（切后台 / 开低性能） */
  shouldPlay?: () => boolean
}

/**
 * 播一次按压音效；真实按压与设置页的「试听」共用这一条路径。
 *
 * 按下和松开各要一个音源：内置音效是两个文件；自定义「单个」时两个阶段共用同一个文件，
 * 自定义「两个文件」时按下的响一下、松开的响另一下。
 */
export function playPressSound(options: PressSoundPlayOptions): Promise<void> {
  const phase = options.phase ?? 'press'
  const request = phase === 'press' ? ++pressRequest : pressRequest
  const allowed = options.shouldPlay ?? (() => true)
  const currentOptions = {
    ...options,
    shouldPlay: () => request === pressRequest && allowed(),
  }

  if (phase === 'press') {
    dropPendingRelease()
    stopRelease()
    pressElement = null
    releaseElement = null
    preparingPress = playPressSoundPhase(currentOptions)
    return preparingPress
  }

  // 自定义文件首次读取是异步的，快点松手也要等这一轮音源准备好。
  return preparingPress.then(() => {
    if (request === pressRequest) {
      return playPressSoundPhase(currentOptions)
    }
  })
}

async function playPressSoundPhase(options: PressSoundPlayOptions): Promise<void> {
  const {
    preset,
    volume,
    customPath = '',
    customReleasePath = '',
    phase = 'press',
    shouldPlay = () => true,
  } = options

  if (phase === 'press') {
    let pressUrl: string | null = null
    let releaseUrl: string | null = null

    if (isBuiltinPressSound(preset)) {
      const builtin = BUILTIN_PRESS_SOUNDS.find(item => item.value === preset)
      if (!builtin) {
        return
      }
      pressUrl = builtinUrl(builtin.press)
      releaseUrl = builtinUrl(builtin.release)
    } else {
      pressUrl = await resolveCustomUrl(customPath)
      if (!pressUrl) {
        return
      }
      // 单个文件时按下、松开用同一个；两个文件时松开单独读，缺文件就不响
      releaseUrl = preset === 'customPair' ? await resolveCustomUrl(customReleasePath) : pressUrl
      if (!releaseUrl) {
        return
      }
    }

    if (!shouldPlay()) {
      return
    }

    dropPendingRelease()
    stopRelease()
    pressElement = elementFor(pressUrl)
    releaseElement = elementFor(releaseUrl)
    playFromStart(pressElement, volume)
    return
  }

  // 松开：没在中心图标上按过就没有松开音
  if (!releaseElement) {
    return
  }

  // 手快的时候按压音还没放完：等它播完再接松开音，两声不会叠在一起
  if (pressElement && !pressElement.paused && !pressElement.ended) {
    dropPendingRelease()
    const element = releaseElement
    const fire = (): void => {
      pendingRelease = null
      // 排队这一小会儿里可能切了后台或开了低性能，真播之前再看一眼
      if (!shouldPlay()) {
        return
      }
      playFromStart(element, volume)
    }
    pendingRelease = fire
    pressElement.addEventListener('ended', fire, { once: true })
    return
  }

  dropPendingRelease()
  if (!shouldPlay()) {
    return
  }
  playFromStart(releaseElement, volume)
}
