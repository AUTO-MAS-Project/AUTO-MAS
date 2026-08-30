import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import enUS from './locales/en-US'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  missingWarn: false,
  fallbackWarn: false,
  messages: { 'zh-CN': zhCN, 'en-US': enUS },
})
const t = i18n.global.t as (key: string, named?: Record<string, unknown>) => string

const flatten = (node: unknown, prefix = ''): [string, string][] =>
  typeof node === 'string'
    ? [[prefix, node]]
    : Object.entries(node as Record<string, unknown>).flatMap(([k, v]) =>
        flatten(v, prefix ? `${prefix}.${k}` : k)
      )

const zhEntries = flatten(zhCN)
const enEntries = flatten(enUS)

describe('词表', () => {
  it('英文词表的 key 都在中文词表里（中文是源语言）', () => {
    const zhKeys = new Set(zhEntries.map(([k]) => k))
    expect(enEntries.map(([k]) => k).filter(k => !zhKeys.has(k))).toEqual([])
  })

  it('每条词条都能被 vue-i18n 编译', () => {
    for (const [key] of zhEntries) {
      expect(() => t(key)).not.toThrow()
    }
  })

  // vue-i18n 把 | 当复数分隔符、{x} 当占位符、@: 当链接消息。
  // 字面量必须写成 {'|'} 这种字面插值，否则渲染时会静默丢内容。
  it('字面量里的 | { } @ 都做了转义', () => {
    expect(t('edit.enterInstanceInfoAs')).toBe('请输入实例信息，格式：启动附加命令 | ADB地址')
    expect(t('edit.exampleTaskDoneSuccess')).toBe('例如：任务完成|成功|失败')
    expect(t('comp.enterMessageTemplateVariables')).toContain('{title}, {content}')
  })

  it('占位符能正常代入', () => {
    expect(t('scripts.toast.copied', { name: 'demo' })).toBe('已复制脚本「demo」')
    expect(t('scheduler.tabName', { n: 2 })).toBe('调度台2')
  })
})
