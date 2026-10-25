//   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
//   Copyright © 2025-2026 AUTO-MAS Team

import { createI18n } from 'vue-i18n'

import zhCN from './locales/zh-CN.json'

export type AppLocale = 'zh-CN' | 'en-US' | 'ja-JP'

/** 词表源语言：其余语言缺 key 时回退到这里。 */
const SOURCE_LOCALE: AppLocale = 'zh-CN'

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

type LocaleMessages = Record<string, unknown>

/**
 * 非源语言词表按需加载。
 *
 * 只静态打包中文（源语言，任何语言都可能回退到它），其余语言在确定界面语言后
 * 再拉对应分块：绝大多数用户用不到的两套词表不再计入首包体积。
 */
const LAZY_LOCALES = {
  'en-US': () => import('./locales/en-US.json'),
  'ja-JP': () => import('./locales/ja-JP.json'),
} satisfies Record<
  Exclude<AppLocale, typeof SOURCE_LOCALE>,
  () => Promise<{ default: LocaleMessages }>
>

type LazyLocale = keyof typeof LAZY_LOCALES

/** 各语言回退链上必须先就位的词表，顺序即加载顺序。 */
const LOAD_CHAIN: Record<LazyLocale, LazyLocale[]> = {
  'en-US': ['en-US'],
  // 日语词表可能缺条目，回退链是 ja→en→zh，所以英文要先就位。
  'ja-JP': ['en-US', 'ja-JP'],
}

const loadedLocales = new Set<AppLocale>([SOURCE_LOCALE])
const loadingLocales = new Map<AppLocale, Promise<void>>()

export const i18n = createI18n({
  legacy: false,
  locale: SOURCE_LOCALE,
  // 日本語は部分的に欠ける可能性があるため、まず英語へ、次に中国語へ落とす。
  // 中国語しか無いキーを日本語話者に見せるより、英語の方が読める。
  fallbackLocale: {
    'ja-JP': ['en-US', SOURCE_LOCALE],
    default: [SOURCE_LOCALE],
  },
  // 词表缺条时静默回退（有单测保证源语言齐全），不在控制台刷告警。
  missingWarn: false,
  fallbackWarn: false,
  // 模板里可以直接写 $t('key')，不必在每个 SFC 里解构 useI18n()。
  globalInjection: true,
  // 三张表的槽位必须都在：只有中文有内容，en/ja 先占位，切换到对应语言前
  // 由 ensureLocaleMessages 填进来。槽位齐全也是 i18n.global.locale 能被赋
  // 任意受支持语言的前提（少一个槽位，它的类型就缩成只剩中文）。
  messages: {
    [SOURCE_LOCALE]: zhCN,
    'en-US': {},
    'ja-JP': {},
  },
})

/**
 * 确保某语言的词表已经装进 i18n 实例。
 *
 * 幂等：并发调用只会触发一次加载，加载完的语言不再重复请求。
 * 切换界面语言前必须先 await，否则 locale 改了但消息还没到，界面会先空一帧。
 */
export async function ensureLocaleMessages(locale: AppLocale): Promise<void> {
  if (loadedLocales.has(locale)) return
  const inflight = loadingLocales.get(locale)
  if (inflight) return inflight

  const task = (async () => {
    for (const target of LOAD_CHAIN[locale as LazyLocale] ?? [locale]) {
      if (loadedLocales.has(target)) continue
      const module = await LAZY_LOCALES[target as LazyLocale]()
      i18n.global.mergeLocaleMessage(target, module.default)
      loadedLocales.add(target)
    }
    loadedLocales.add(locale)
  })()

  loadingLocales.set(locale, task)
  try {
    await task
  } finally {
    loadingLocales.delete(locale)
  }
}

/** 在组件外部取译文（composable 之外的工具函数里用）。 */
export const t = i18n.global.t

/**
 * 组件外取词条：composable、工具函数，以及被单测直接调用、没有组件实例的地方。
 * 组件内模板用 $t()，脚本块用 useI18n()。
 */
export const translate = i18n.global.t as (key: string, named?: Record<string, unknown>) => string
