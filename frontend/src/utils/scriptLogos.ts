import { projectScriptDescriptors } from '@/scriptDescriptors'

/** 脚本类型 → 图标资源，Vite 处理后的 URL。 */
export const SCRIPT_LOGOS = projectScriptDescriptors(item => item.logo)

/** 图片 alt 使用品牌名，可见名称仍由卡片的翻译 key 提供。 */
export const SCRIPT_LABELS = projectScriptDescriptors(item => item.label)
