// Chromium 会静默丢弃超过这个字符数的单条内联样式声明：不写入、不报错，旧值原样留着。
// 外观素材是 base64 data URL，2.2 MB 的 PNG 就有约 309 万字符，直接写进 CSS 变量必然超限。
export const INLINE_STYLE_VALUE_MAX = 2 * 1024 * 1024

export const BACKGROUND_IMAGE_PROPERTY = '--app-appearance-background-image'

const BASE64_MARKER = ';base64,'

export function dataUrlToBlob(dataUrl: string): Blob | null {
  if (!dataUrl.startsWith('data:')) return null
  const marker = dataUrl.indexOf(BASE64_MARKER)
  if (marker < 0) return null
  let binary: string
  try {
    binary = atob(dataUrl.slice(marker + BASE64_MARKER.length))
  } catch {
    return null
  }
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new Blob([bytes], { type: dataUrl.slice('data:'.length, marker) })
}

type StyleTarget = Pick<CSSStyleDeclaration, 'setProperty' | 'getPropertyValue'>

type Logger = { error: (message: string) => void }

type BackgroundApplierOptions = {
  createObjectURL?: (blob: Blob) => string
  revokeObjectURL?: (url: string) => void
  logger?: Logger
}

/**
 * 把外观背景写进 CSS 变量：data URL 先转成 blob: URL，CSS 里只放几十个字符的地址。
 * 写完读回核对，没生效就清成 none 且不记账，下次照样重写，不会留着上一个包的图。
 */
export function createAppearanceBackgroundApplier(options: BackgroundApplierOptions = {}) {
  const createObjectURL = options.createObjectURL ?? (blob => URL.createObjectURL(blob))
  const revokeObjectURL = options.revokeObjectURL ?? (url => URL.revokeObjectURL(url))
  // null 表示还没写过（或上次没写成），首次必须落一次。
  let applied: { source: string | undefined; objectUrl?: string } | null = null

  const release = () => {
    if (applied?.objectUrl) revokeObjectURL(applied.objectUrl)
  }

  return (style: StyleTarget, source: string | undefined): void => {
    if (applied && applied.source === source) return

    let objectUrl: string | undefined
    let value = 'none'
    if (source) {
      const blob = dataUrlToBlob(source)
      if (blob) {
        objectUrl = createObjectURL(blob)
        value = `url("${objectUrl}")`
      } else {
        value = `url("${source}")`
      }
    }

    style.setProperty(BACKGROUND_IMAGE_PROPERTY, value)
    if (style.getPropertyValue(BACKGROUND_IMAGE_PROPERTY) !== value) {
      if (objectUrl) revokeObjectURL(objectUrl)
      style.setProperty(BACKGROUND_IMAGE_PROPERTY, 'none')
      release()
      applied = null
      options.logger?.error(`外观背景写入 CSS 变量没有生效，已清除背景（${value.length} 个字符）`)
      return
    }

    release()
    applied = { source, objectUrl }
  }
}
