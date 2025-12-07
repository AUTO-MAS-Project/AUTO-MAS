/**
 * 在系统默认浏览器中打开URL
 * @param url 要打开的URL
 * @returns Promise<boolean> 是否成功打开
 */
export async function openExternalUrl(url: string): Promise<boolean> {
    try {
        if (window.electronAPI && window.electronAPI.openUrl) {
            const result = await window.electronAPI.openUrl(url)
            return result.success
        } else {
            // 如果不在Electron环境中，使用普通的window.open
            window.open(url, '_blank')
            return true
        }
    } catch (error) {
        console.error('打开链接失败:', error)
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
