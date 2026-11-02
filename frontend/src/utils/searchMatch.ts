import { pinyin } from 'pinyin-pro'

interface PinyinIndex {
  full: string
  initials: string
}

const cache = new Map<string, PinyinIndex>()

const latinOnly = (value: string): string => value.toLowerCase().replace(/[^a-z0-9]/g, '')

const pinyinIndexOf = (text: string): PinyinIndex => {
  const cached = cache.get(text)
  if (cached) return cached
  const index = {
    full: latinOnly(pinyin(text, { toneType: 'none', type: 'array' }).join('')),
    initials: latinOnly(
      pinyin(text, { pattern: 'first', toneType: 'none', type: 'array' }).join('')
    ),
  }
  cache.set(text, index)
  return index
}

/** 原文包含优先；纯拉丁/数字关键字再匹配全拼与首字母。 */
export const matchesKeyword = (text: string, keyword: string): boolean => {
  const value = text.trim()
  const key = keyword.trim().toLowerCase()
  if (!key) return true
  if (!value) return false
  if (value.toLowerCase().includes(key)) return true
  if (!/^[a-z0-9]+$/.test(key)) return false
  const index = pinyinIndexOf(value)
  return index.full.includes(key) || index.initials.includes(key)
}
