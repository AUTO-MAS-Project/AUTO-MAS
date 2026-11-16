import { isBrowserDevelopment } from '@/utils/environment'

/** input 字段的路径类型（PI v2.10.5 `input_type`），见 maafwOptionValues 的 maafwInputPathKind */
export type MaaFWInputPathKind = 'file' | 'directory'

/**
 * 有系统对话框可用时才给「选择」按钮。浏览器预览里 electronAPI 是 shim、选择是空实现，
 * 没有 electronAPI 时同样没有对话框：都退化成普通文本框（协议要求降级，不得判非法）。
 */
export const canPickMaaFWInputPath = (kind: MaaFWInputPathKind) => {
  if (typeof window === 'undefined' || isBrowserDevelopment()) return false
  const api = window.electronAPI
  return kind === 'file'
    ? typeof api?.selectFile === 'function'
    : typeof api?.selectFolder === 'function'
}

/**
 * 弹系统文件 / 文件夹对话框，返回选中的原生绝对路径（原样，不转分隔符、不转义）；取消返回 null。
 * 文件对话框不加扩展名过滤（主进程默认只有「所有文件」一项），协议没有过滤字段。
 */
export const pickMaaFWInputPath = async (kind: MaaFWInputPathKind): Promise<string | null> => {
  const api = window.electronAPI
  if (kind === 'file') {
    const paths = await api?.selectFile?.()
    return paths?.[0] || null
  }
  return (await api?.selectFolder?.()) || null
}
