// 通用 MaaFW 脚本的项目图标（interface 顶层 icon）。放在 utils 而不是 useMaaFWApi：
// 那边模块顶层就取 window.electronAPI 的 logger，新建对话框的分节测试（SSR、无 window）引不进去。
import { OpenAPI } from '@/api'

/**
 * 按脚本取项目图标的 URL：调用方手上没有项目目录（脚本列表、新建对话框的复用列表），
 * 由后端 `/api/scripts/maafw/icon` 找该脚本已导入的副本。取不到时后端回 404，
 * 调用方在 `<img @error>` 里回退。
 */
export const buildMaaFWScriptIconUrl = (scriptId: string) => {
  const baseUrl = OpenAPI.BASE || 'http://localhost:36163'
  return `${baseUrl}/api/scripts/maafw/icon?${new URLSearchParams({ scriptId }).toString()}`
}

/** `<img @error>`：项目图标加载失败时换成类型图标；类型图标自己也加载失败就不再换，免得来回触发 */
export const fallbackToMaaFWLogo = (event: Event, logo: string) => {
  const image = event.currentTarget as HTMLImageElement | null
  if (!image || image.getAttribute('src') === logo) return
  image.setAttribute('src', logo)
}
