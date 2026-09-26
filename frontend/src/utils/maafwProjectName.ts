// MFW 项目给人看的名字：脚本列表的类型标签、引导页标题、新建脚本的默认名都用它。
// 与后端 interface_display_name 同一口径：label → title → name。
// 后端模型在 interface 没写 label 时把它补成 name，所以 label 与 name 相同就当没写，轮到 title。
// title 常是窗口标题，带版本号和标语（「识宝小助手 Oᴗoಣ | 版本号:v1.13.3 | 自动乐土激情开发中」、
// 「MRA v3.2.0 | 舰R小助手」），只取第一段并去掉末尾的版本号；翻不出来的 i18n 键（$ 开头）不算名字。

export interface MaaFWProjectNameSource {
  name?: string | null
  label?: string | null
  title?: string | null
}

const TRAILING_VERSION = /\s+(?:版本号\s*[:：]?\s*)?v?\d+(?:\.\d+)+(?:[-+][\w.]+)?$/i

export const normalizeMaaFWProjectName = (raw: string | null | undefined): string => {
  const text = typeof raw === 'string' ? raw.trim() : ''
  if (!text || text.startsWith('$')) return ''
  return text
    .split(/[|｜]/)[0]
    .trim()
    .replace(TRAILING_VERSION, '')
    .trim()
}

export const resolveMaaFWProjectName = (
  project: MaaFWProjectNameSource | null | undefined
): string => {
  if (!project) return ''
  const label = project.label !== project.name ? project.label : ''
  for (const raw of [label, project.title, project.name]) {
    const name = normalizeMaaFWProjectName(raw)
    if (name) return name
  }
  return ''
}
