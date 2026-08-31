import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import enUS from './locales/en-US'
import jaJP from './locales/ja-JP'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  missingWarn: false,
  fallbackWarn: false,
  messages: { 'zh-CN': zhCN, 'en-US': enUS, 'ja-JP': jaJP },
})
const t = i18n.global.t as (key: string, named?: Record<string, unknown>, plural?: number) => string

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

  it('每条词条都能被 vue-i18n 编译', () => {
    for (const [key] of zhEntries) {
      expect(() => t(key)).not.toThrow()
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

  it('字面量里的 | { } @ 都做了转义', () => {
    expect(t('edit.enterInstanceInfoAs')).toBe('请输入实例信息，格式：启动附加命令 | ADB地址')
    expect(t('edit.exampleTaskDoneSuccess')).toBe('例如：任务完成|成功|失败')
    expect(t('comp.enterMessageTemplateVariables')).toContain('{title}, {content}')
  })

  it('占位符能正常代入', () => {
    expect(t('scripts.toast.copied', { name: 'demo' })).toBe('已复制脚本「demo」')
    expect(t('scheduler.tabName', { n: 2 })).toBe('调度台2')
  })

  // 计数类文案在英文下要区分单复数，中文两个形式写成一样的
  it('计数文案的单复数', () => {
    expect(t('queue.count', { count: 1 }, 1)).toBe('1 个队列')
    expect(t('queue.count', { count: 3 }, 3)).toBe('3 个队列')
    i18n.global.locale.value = 'en-US'
    expect(t('queue.count', { count: 1 }, 1)).toBe('1 queue')
    expect(t('queue.count', { count: 3 }, 3)).toBe('3 queues')
    // 日本語は単複同形なので、どちらも同じ文になる
    i18n.global.locale.value = 'ja-JP'
    expect(t('queue.count', { count: 1 }, 1)).toBe('1 件のキュー')
    expect(t('queue.count', { count: 3 }, 3)).toBe('3 件のキュー')
    i18n.global.locale.value = 'zh-CN'
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
