import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vite-plus/test'
import enUS from './bootstrap/en-US.json'
import jaJP from './bootstrap/ja-JP.json'
import zhCN from './bootstrap/zh-CN.json'

const flatten = (node: unknown, prefix = ''): [string, string][] =>
  typeof node === 'string'
    ? [[prefix, node]]
    : Object.entries(node as Record<string, unknown>).flatMap(([k, v]) =>
        flatten(v, prefix ? `${prefix}.${k}` : k)
      )

const catalogEntries = (bootstrap: unknown, filename: string): [string, string][] => [
  ...flatten(bootstrap, 'bootstrap'),
  ...Object.entries(
    JSON.parse(
      readFileSync(new URL(`../../../res/i18n/${filename}.json`, import.meta.url), 'utf8')
    ) as Record<string, string>
  ),
]

const zhEntries = catalogEntries(zhCN, 'zh_CN')
// 中文是源语言；三种语言的消息语法都需要校验。
const TRANSLATIONS = [
  ['en-US', catalogEntries(enUS, 'en')],
  ['ja-JP', catalogEntries(jaJP, 'ja')],
] as const

describe('词表', () => {
  // 复数消息，| 是有意的分隔符；其余词条里的 | 都必须转义
  const PLURAL_KEYS = new Set([
    'core.home.endfield.ongoing',
    'core.plan.count',
    'core.queue.count',
    'core.scripts.userCount',
  ])

  // 这一条兜住整张词表：漏转义时 t() 会静默截断（| 后面全丢），
  // 页面上看不出报错，只是文案短了一截。
  it('除复数消息外，没有未转义的 | { } @', () => {
    const literal = /\{'[^']*'\}/g
    const param = /\{[A-Za-z_]\w*\}/g
    const offenders: string[] = []
    for (const [locale, entries] of [['zh-CN', zhEntries], ...TRANSLATIONS] as const) {
      for (const [key, value] of entries) {
        if (PLURAL_KEYS.has(key)) continue
        const rest = value.replace(literal, '').replace(param, '')
        if (/[|{}]/.test(rest) || /@[:.]/.test(rest)) {
          offenders.push(`${locale} ${key}: ${value}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })
})
