import type { ScriptType } from '@/types/script'
import { SCRIPT_METADATA } from './scriptMetadata'

/** 脚本类型 → 图标资源，Vite 处理后的 URL */
export const SCRIPT_LOGOS = Object.fromEntries(
  Object.entries(SCRIPT_METADATA).map(([type, metadata]) => [type, metadata.logo])
) as Record<ScriptType, string>

/** 脚本类型 → 展示名（图片 alt；可见名称走 i18n 词表） */
export const SCRIPT_LABELS = Object.fromEntries(
  Object.entries(SCRIPT_METADATA).map(([type, metadata]) => [type, metadata.label])
) as Record<ScriptType, string>
