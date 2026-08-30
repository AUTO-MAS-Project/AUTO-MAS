import { describe, expect, it } from 'vitest'

import { DEFAULT_LOCALE, SUPPORTED_LOCALES, normalizeLocale } from './index'

describe('normalizeLocale', () => {
  it('把各种中文标记归一到 zh-CN', () => {
    for (const raw of ['zh', 'zh-CN', 'zh-Hans-CN', 'zh-TW', 'zh-HK', 'ZH-cn']) {
      expect(normalizeLocale(raw)).toBe('zh-CN')
    }
  })

  it('把各种英文标记归一到 en-US', () => {
    for (const raw of ['en', 'en-US', 'en-GB', 'EN-us']) {
      expect(normalizeLocale(raw)).toBe('en-US')
    }
  })

  it('空值与无法识别的语言回退到默认语言', () => {
    for (const raw of [null, undefined, '', 'fr-FR', 'ja-JP', 'de']) {
      expect(normalizeLocale(raw)).toBe(DEFAULT_LOCALE)
    }
  })

  it('归一结果始终落在受支持的语言集合内', () => {
    for (const raw of ['zh-CN', 'en-US', 'fr', '', 'nonsense']) {
      expect(SUPPORTED_LOCALES).toContain(normalizeLocale(raw))
    }
  })
})
