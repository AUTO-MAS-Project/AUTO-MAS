/** 鸣潮 PC 客户端：MAS 期望用户选择的游戏根目录名 */
export const WUWA_GAME_ROOT_FOLDER = 'Wuthering Waves Game'

/** 相对游戏根目录的客户端 exe 路径 */
export const WUWA_CLIENT_EXE_REL = 'Client/Binaries/Win64/Client-Win64-Shipping.exe'

export function normalizeFolderPath(path: string): string {
  return path.replace(/\\/g, '/').replace(/\/+$/g, '')
}

/** 由用户所选文件夹拼出 Client-Win64-Shipping.exe 配置路径 */
export function buildWutheringClientExePath(gameRootFolder: string): string {
  return `${normalizeFolderPath(gameRootFolder)}/${WUWA_CLIENT_EXE_REL}`
}

type FileExistsFn = (filePath: string) => Promise<boolean>

/**
 * 校验用户选择的文件夹是否为正确的鸣潮游戏根目录。
 * 路径仍会按所选目录落盘；本函数仅用于前端提示。
 */
export async function validateWutheringGameRootSelection(
  pickedFolder: string,
  fileExists: FileExistsFn,
): Promise<{ valid: true } | { valid: false; message: string }> {
  const root = normalizeFolderPath(pickedFolder)
  const directExe = buildWutheringClientExePath(root)

  if (await fileExists(directExe)) {
    return { valid: true }
  }

  return {
    valid: false,
    message: `选择游戏根目录错误，请选择 ${WUWA_GAME_ROOT_FOLDER} 文件夹`,
  }
}
