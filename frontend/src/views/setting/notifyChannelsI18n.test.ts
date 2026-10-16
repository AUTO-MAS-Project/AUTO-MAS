import { readFileSync, readdirSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import zhCN from '@/i18n/locales/zh-CN'

// 跨语言词表契约：只读取随应用交付的内置清单和声明，不执行 Python 渠道。
const repoRoot = new URL('../../../../', import.meta.url)
const channelRoot = new URL('app/notification_channels/', repoRoot)
const channelSources = readdirSync(channelRoot, { withFileTypes: true })
  .filter(entry => entry.isDirectory())
  .map(entry => entry.name)
  .sort()
  .flatMap(name => {
    const files = readdirSync(new URL(`${name}/`, channelRoot))
    if (!files.includes('manifest.json')) return []
    const manifest = JSON.parse(
      readFileSync(new URL(`${name}/manifest.json`, channelRoot), 'utf8')
    ) as { interface_version: number; id: string; entrypoint: string }
    expect(manifest.interface_version).toBe(1)
    expect(manifest.id).toBe(name)
    expect(manifest.entrypoint).toBe(`app.notification_channels.${name}:register`)
    const [module] = manifest.entrypoint.split(':')
    return readFileSync(new URL(`${module.split('.').join('/')}/__init__.py`, repoRoot), 'utf8')
  })
// 通知内容 policy 仍归宿主，不是可发送的渠道。
const source = [
  readFileSync(new URL('app/core/notify_channels.py', repoRoot), 'utf8'),
  ...channelSources,
].join('\n')

const flatten = (node: unknown, prefix = ''): [string, string][] =>
  typeof node === 'string'
    ? [[prefix, node]]
    : Object.entries(node as Record<string, unknown>).flatMap(([k, v]) =>
        flatten(v, prefix ? `${prefix}.${k}` : k)
      )

const zhKeys = new Map(flatten(zhCN))

interface ChannelBlock {
  key: string
  summaryKey: string | null
  summaryFields: string[]
  customBlock: string | null
}

// NotifyChannelField( 的前缀不匹配精确的 'NotifyChannel('，切分是安全的
const channelBlocks: ChannelBlock[] = source
  .split('NotifyChannel(')
  .slice(1)
  .map(block => {
    const key = block.match(/key="([^"]+)"/)?.[1] ?? ''
    const summaryKey = block.match(/summary_key="([^"]+)"/)?.[1] ?? null
    const summaryFields =
      block
        .match(/summary_fields=\(([^)]*)\)/)?.[1]
        ?.match(/"([^"]+)"/g)
        ?.map(name => name.slice(1, -1)) ?? []
    const customBlock = block.match(/custom_block="([^"]+)"/)?.[1] ?? null
    return { key, summaryKey, summaryFields, customBlock }
  })

describe('通知渠道描述表的词表键', () => {
  it('描述表引用的所有词表键都存在', () => {
    expect(channelBlocks.length).toBeGreaterThanOrEqual(8)
    const keys = [...source.matchAll(/"(setting\.[A-Za-z0-9_.]+)"/g)].map(match => match[1])
    expect(keys.length).toBeGreaterThan(20)
    // Webhook 的正文摘要不渲染（非空时直接拼条目名），词表只放 Empty 变体
    const unrendered = ['setting.notify.summary.webhook']
    const missing = [...new Set(keys)].filter(key => !zhKeys.has(key) && !unrendered.includes(key))
    expect(missing).toEqual([])
  })

  it('会触发空值降级或 Webhook 特例的渠道都有 Empty 变体', () => {
    // 摘要约定：空值变体键为 `${summaryKey}Empty`（计划的 .empty 后缀在
    // vue-i18n 里与正文键同路径冲突，改用 Empty 后缀）。
    // Webhook 例外：非空摘要直接拼接条目名，正文键不渲染，只要 Empty 变体。
    for (const { key, summaryKey, summaryFields, customBlock } of channelBlocks) {
      const needsEmpty = summaryFields.length > 0 || customBlock === 'webhook_list'
      const webhookException = customBlock === 'webhook_list'
      if (!summaryKey) {
        expect(needsEmpty, `${key} 没有 summary_key 却需要 Empty 变体`).toBe(false)
        continue
      }
      if (!webhookException) {
        expect(zhKeys.has(summaryKey), `${key} 缺正文键 ${summaryKey}`).toBe(true)
      }
      if (needsEmpty) {
        expect(zhKeys.has(`${summaryKey}Empty`), `${key} 缺空值变体 ${summaryKey}Empty`).toBe(true)
      }
    }
  })

  it('摘要文案里的占位符都出现在该渠道的 summary_fields', () => {
    for (const { key, summaryKey, summaryFields } of channelBlocks) {
      if (!summaryKey) continue
      const text = zhKeys.get(summaryKey) ?? ''
      const placeholders = [...text.matchAll(/\{([A-Za-z_]\w*)\}/g)].map(m => m[1])
      const outside = placeholders.filter(name => !summaryFields.includes(name))
      expect(outside, `${key} 的摘要占位符 ${outside} 不在 summary_fields`).toEqual([])
    }
  })
})
