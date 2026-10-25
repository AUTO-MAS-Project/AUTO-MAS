import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vite-plus/test'

// 直接读 JSON 原文，不 import：词表会被 @intlify/unplugin-vue-i18n
// 在构建/测试期预编译成消息函数，import 进来的已经不是可遍历的对象了。
const localesDir = fileURLToPath(new URL('./locales/', import.meta.url))
const readLocale = (locale: string): Record<string, unknown> =>
  JSON.parse(readFileSync(join(localesDir, `${locale}.json`), 'utf8'))

const flatten = (node: unknown, prefix = ''): [string, string][] =>
  typeof node === 'string'
    ? [[prefix, node]]
    : Object.entries(node as Record<string, unknown>).flatMap(([k, v]) =>
        flatten(v, prefix ? `${prefix}.${k}` : k)
      )

const zhCN = readLocale('zh-CN')
const zhEntries = flatten(zhCN)
// 中文が源言語。ほかの言語はここに無いキーを持てない
const TRANSLATIONS = [
  ['en-US', flatten(readLocale('en-US'))],
  ['ja-JP', flatten(readLocale('ja-JP'))],
] as const

describe('词表', () => {
  it('各语言词表的 key 都在中文词表里（中文是源语言）', () => {
    const zhKeys = new Set(zhEntries.map(([k]) => k))
    for (const [locale, entries] of TRANSLATIONS) {
      const extra = entries.map(([k]) => k).filter(k => !zhKeys.has(k))
      expect([locale, extra]).toEqual([locale, []])
    }
  })

  // 复数消息，| 是有意的分隔符；其余词条里的 | 都必须转义
  const PLURAL_KEYS = new Set([
    'home.endfield.ongoing',
    'plan.count',
    'queue.count',
    'scripts.userCount',
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
    const namespaces = new Set(Object.keys(zhCN))
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
      // 模板里是 $t()，脚本里是 t()，有的地方还会写 i18n.global.t()；
      // 三种写法的 key 都要在词表里。只校验带命名空间前缀的字面量 key，
      // 动态拼接的（t(`x.${y}`)）匹配不到。
      for (const match of source.matchAll(/(?<![\w.$])\$?\bt\(\s*'([\w.]+)'/g)) {
        const key = match[1]
        if (namespaces.has(key.split('.')[0]) && !zhKeys.has(key)) {
          missing.push(`${file.slice(srcDir.length)}: ${key}`)
        }
      }
    }
    expect(missing).toEqual([])
  })
})
