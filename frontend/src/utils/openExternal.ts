/**
 * 在系统默认浏览器中打开URL
 * @param url 要打开的URL
 * @returns Promise<boolean> 是否成功打开
 */
export function normalizeExternalUrl(url: string): string | null {
  try {
    const parsed = new URL(String(url || '').trim())
    if (!['http:', 'https:', 'mailto:'].includes(parsed.protocol.toLowerCase())) {
      return null
    }
    return parsed.href
  } catch {
    return null
  }
}

export async function openExternalUrl(url: string): Promise<boolean> {
  try {
    const safeUrl = normalizeExternalUrl(url)
    if (!safeUrl) return false

    if (window.electronAPI && window.electronAPI.openUrl) {
      const result = await window.electronAPI.openUrl(safeUrl)
      return result.success
    } else {
      // 如果不在Electron环境中，使用普通的window.open
      const opened = window.open(safeUrl, '_blank', 'noopener,noreferrer')
      if (opened) opened.opener = null
      return true
    }
  } catch (error) {
    window.electronAPI?.getLogger('外部链接').error(`打开链接失败: ${String(error)}`)
    return false
  }
}

/**
 * 为 <a> 标签添加点击事件处理，使用系统浏览器打开链接
 * @param event 点击事件
 */
export function handleExternalLink(event: MouseEvent) {
  event.preventDefault()
  const target = event.currentTarget as HTMLAnchorElement
  if (target && target.href) {
    openExternalUrl(target.href)
  }
}
