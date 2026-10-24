import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vite-plus/test'
import enUS from './locales/en-US'
import jaJP from './locales/ja-JP'
import zhCN from './locales/zh-CN'

const flatten = (node: unknown, prefix = ''): [string, string][] =>
  typeof node === 'string'
    ? [[prefix, node]]
    : Object.entries(node as Record<string, unknown>).flatMap(([k, v]) =>
        flatten(v, prefix ? `${prefix}.${k}` : k)
      )

const zhEntries = flatten(zhCN)
// 中文が源言語。ほかの言語はここに無いキーを持てない
const TRANSLATIONS = [
  ['en-US', flatten(enUS)],
  ['ja-JP', flatten(jaJP)],
] as const

describe('词表', () => {
  it('各语言词表的 key 都在中文词表里（中文是源语言）', () => {
    const zhKeys = new Set(zhEntries.map(([k]) => k))
    for (const [locale, entries] of TRANSLATIONS) {
      const extra = entries.map(([k]) => k).filter(k => !zhKeys.has(k))
      expect([locale, extra]).toEqual([locale, []])
    }
  })

  // 中文是源语言，新增文案总是先写中文；另外两语漏翻时界面会静默回落成中文，
  // 只有切到英文/日文的眼睛能发现。这条把「漏翻」变成一条会红的断言。
  it('中文词表的每条 key 在其它语言里都有译文', () => {
    const missing: string[] = []
    for (const [locale, entries] of TRANSLATIONS) {
      const keys = new Set(entries.map(([k]) => k))
      for (const [key] of zhEntries) {
        if (!keys.has(key)) missing.push(`${locale} 缺 ${key}`)
      }
    }
    expect(missing).toEqual([])
  })

  // 占位符漏抄时 t() 不报错，只是参数没了：日文里少个 {n} 就变成「共 条」。
  it('同一 key 的占位符在各语言里一致', () => {
    const placeholders = (value: string) =>
      [...value.matchAll(/\{([A-Za-z_]\w*)\}/g)]
        .map(match => match[1])
        .sort()
        .join(',')
    const zhMap = new Map(zhEntries)
    const offenders: string[] = []
    for (const [locale, entries] of TRANSLATIONS) {
      for (const [key, value] of entries) {
        const source = zhMap.get(key)
        if (source === undefined) continue
        if (placeholders(source) !== placeholders(value)) {
          offenders.push(
            `${locale} ${key}: 中文 [${placeholders(source)}] vs ${locale} [${placeholders(value)}]`
          )
        }
      }
    }
    expect(offenders).toEqual([])
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

  // vue-i18n 会对疑似 HTML 的词条刷控制台警告（@intlify/message-compiler 的
  // RE_HTML_TAG：'= < > !' 里的 '< >' 就被误判成标签）。警告不致命但会淹没真问题；
  // 词表一律当纯文本渲染，需要富文本的场景走后端 markdown，不经词表。
  it('词条不触发 vue-i18n 的 HTML 检测（避免控制台警告）', () => {
    // 与 @intlify/message-compiler 的 detectHtmlTag 同一条正则
    const RE_HTML_TAG = /<\/?[\w\s="/.':;#-/]+>/
    const offenders: string[] = []
    for (const [locale, entries] of [['zh-CN', zhEntries], ...TRANSLATIONS] as const) {
      for (const [key, value] of entries) {
        if (RE_HTML_TAG.test(value)) offenders.push(`${locale} ${key}: ${value}`)
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
