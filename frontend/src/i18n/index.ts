//   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
//   Copyright © 2025-2026 AUTO-MAS Team

import { createI18n } from 'vue-i18n'

import enUS from './locales/en-US'
import jaJP from './locales/ja-JP'
import zhCN from './locales/zh-CN'

export type AppLocale = 'zh-CN' | 'en-US' | 'ja-JP'

/** 词表源语言：英文词表缺 key 时回退到这里。 */
export const SOURCE_LOCALE: AppLocale = 'zh-CN'

/**
 * 语言标记无法识别时使用的界面语言。
 *
 * 取英文而非中文：系统语言既非中文也非英文的用户，更可能是看不懂中文的人，
 * 给他们英文比给中文更接近「看得懂」。
 */
export const UNRECOGNIZED_LOCALE: AppLocale = 'en-US'

export const SUPPORTED_LOCALES: AppLocale[] = ['zh-CN', 'en-US', 'ja-JP']

/** 把任意语言标记归一到受支持的语言。 */
export function normalizeLocale(raw: string | null | undefined): AppLocale {
  if (!raw) return UNRECOGNIZED_LOCALE
  const lower = raw.toLowerCase()
  if (lower.startsWith('zh')) return 'zh-CN'
  if (lower.startsWith('en')) return 'en-US'
  if (lower.startsWith('ja')) return 'ja-JP'
  return UNRECOGNIZED_LOCALE
}

export const i18n = createI18n({
  legacy: false,
  locale: SOURCE_LOCALE,
  // 日本語は部分的に欠ける可能性があるため、まず英語へ、次に中国語へ落とす。
  // 中国語しか無いキーを日本語話者に見せるより、英語の方が読める。
  fallbackLocale: {
    'ja-JP': ['en-US', SOURCE_LOCALE],
    default: [SOURCE_LOCALE],
  },
  // 英文词表是部分覆盖的，缺失 key 回退中文属预期行为，不必告警。
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
    'ja-JP': jaJP,
  },
})

/** 在组件外部取译文（composable 之外的工具函数里用）。 */
export const t = i18n.global.t

/**
 * 组件外取词条：composable、工具函数，以及被单测直接调用、没有组件实例的地方。
 * 组件内仍用 useI18n()。
 */
export const translate = i18n.global.t as (key: string, named?: Record<string, unknown>) => string
