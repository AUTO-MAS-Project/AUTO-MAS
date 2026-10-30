import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
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
// 中文が源言語。ほかの言語はここに無いキーを持てない
const TRANSLATIONS = [
  ['en-US', catalogEntries(enUS, 'en')],
  ['ja-JP', catalogEntries(jaJP, 'ja')],
] as const

const placeholders = (value: string): string[] => (value.match(/\{[A-Za-z_]\w*\}/g) ?? []).sort()

describe('词表', () => {
  // 初始化词表必须独立完整；业务缺词由 Vue I18n 按语言链回退。
  it('初始化词表各语言完整，业务词表不包含源语言以外的 key', () => {
    const zhKeys = new Set(zhEntries.map(([k]) => k))
    for (const [locale, entries] of TRANSLATIONS) {
      const keys = new Set(entries.map(([k]) => k))
      const extra = [...keys].filter(k => !zhKeys.has(k))
      const missing = zhEntries
        .map(([k]) => k)
        .filter(k => k.startsWith('bootstrap.') && !keys.has(k))
      expect([locale, extra, missing]).toEqual([locale, [], []])
    }
  })

  // 占位符少一个，t() 就少显示一段用户数据，页面上不报错只是缺内容。
  it('同一条 key 在各语言里的占位符一致', () => {
    const zhMap = new Map(zhEntries)
    const offenders: string[] = []
    for (const [locale, entries] of TRANSLATIONS) {
      for (const [key, value] of entries) {
        const source = zhMap.get(key)
        if (source === undefined) continue
        const expected = placeholders(source).join()
        const actual = placeholders(value).join()
        if (expected !== actual) {
          offenders.push(`${locale} ${key}: [${actual}] != [${expected}]`)
        }
      }
    }
    expect(offenders).toEqual([])
  })

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

  // 词表少一条 key 时 t() 会把 key 原样渲染出来，页面上就是一串 comp.enabled，
  // 但 lint / typecheck / 其余单测都不报错，只能靠这里兜。
  it('源码里用到的 key 在中文词表里都有', () => {
    const zhKeys = new Set(zhEntries.map(([k]) => k))
    const namespaces = new Set(['bootstrap', 'core'])
    const srcDir = fileURLToPath(new URL('..', import.meta.url))

    const walk = (dir: string): string[] =>
      readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
        const full = join(dir, entry.name)
        if (entry.isDirectory()) return entry.name === 'api' ? [] : walk(full)
        return /\.(vue|ts)$/.test(entry.name) && !entry.name.endsWith('.test.ts') ? [full] : []
      })

    const missing: string[] = []
    for (const file of walk(srcDir)) {
      const source = readFileSync(file, 'utf8')
      for (const match of source.matchAll(/\bt\(\s*'([\w.]+)'/g)) {
        const key = match[1]
        // 只校验带命名空间前缀的字面量 key，动态拼接的（t(`x.${y}`)）匹配不到
        if (namespaces.has(key.split('.')[0]) && !zhKeys.has(key)) {
          missing.push(`${file.slice(srcDir.length)}: ${key}`)
        }
      }
    }
    expect(missing).toEqual([])
  })
})
