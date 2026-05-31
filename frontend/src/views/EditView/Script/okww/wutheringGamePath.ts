/**
 * 鸣潮 PC 客户端：Okww 专项路径常量与工具。
 * 与 app/task/Okww/wuthering_game_path.py 保持同步。
 */

export const WUWA_GAME_ROOT_FOLDER = 'Wuthering Waves Game'

export const WUWA_CLIENT_EXE_REL = 'Client/Binaries/Win64/Client-Win64-Shipping.exe'

export const WUWA_CLIENT_PROCESS_NAME = WUWA_CLIENT_EXE_REL.split('/').pop()!

export function normalizeFolderPath(path: string): string {
  return path.replace(/\\/g, '/').replace(/\/+$/g, '')
}

export function buildWutheringClientExePath(gameRootFolder: string): string {
  return `${normalizeFolderPath(gameRootFolder)}/${WUWA_CLIENT_EXE_REL}`
}
