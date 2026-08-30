//   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
//   Copyright © 2025-2026 AUTO-MAS Team

import { createI18n } from 'vue-i18n'

import enUS from './locales/en-US'
import zhCN from './locales/zh-CN'

export type AppLocale = 'zh-CN' | 'en-US'

export const DEFAULT_LOCALE: AppLocale = 'zh-CN'
export const SUPPORTED_LOCALES: AppLocale[] = ['zh-CN', 'en-US']

/** 把任意语言标记归一到受支持的语言；无法识别时回退中文。 */
export function normalizeLocale(raw: string | null | undefined): AppLocale {
  if (!raw) return DEFAULT_LOCALE
  const lower = raw.toLowerCase()
  if (lower.startsWith('zh')) return 'zh-CN'
  if (lower.startsWith('en')) return 'en-US'
  return DEFAULT_LOCALE
}

export const i18n = createI18n({
  legacy: false,
  locale: DEFAULT_LOCALE,
  fallbackLocale: DEFAULT_LOCALE,
  // 英文词表是部分覆盖的，缺失 key 回退中文属预期行为，不必告警。
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

/** 在组件外部取译文（composable 之外的工具函数里用）。 */
export const t = i18n.global.t
