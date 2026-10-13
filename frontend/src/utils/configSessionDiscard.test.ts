// 「配置会话改动被丢弃」的共用判定与文案测试（不挂载组件，直接测分支行为）。
import { describe, expect, it } from 'vitest'

import { translate } from '@/i18n'

import { configDiscardContent, configDiscardReasonKey } from './configSessionDiscard'

const t = (key: string, named?: Record<string, string>) =>
  named ? `${key}(${JSON.stringify(named)})` : key

/** 后端可能下发的原因 + 一个未来新增的未知原因 */
const REASONS = ['structure', 'unreadable', 'not_written', 'future_reason']

describe('configDiscardReasonKey', () => {
  it('后端三种原因各映射到自己的词条', () => {
    expect(configDiscardReasonKey('structure')).toBe('edit.configSessionDiscardedStructure')
    expect(configDiscardReasonKey('unreadable')).toBe('edit.configSessionDiscardedUnreadable')
    expect(configDiscardReasonKey('not_written')).toBe('edit.configSessionDiscardedNotWritten')
  })

  it('未知原因回落到通用文案', () => {
    expect(configDiscardReasonKey('')).toBe('edit.configSessionDiscardedUnknown')
    expect(configDiscardReasonKey('future_reason')).toBe('edit.configSessionDiscardedUnknown')
  })
})

describe('configDiscardContent', () => {
  it('按原因取正文，并保留换行与 alert 语义', () => {
    const node = configDiscardContent(t, 'structure')
    expect(node.props?.role).toBe('alert')
    expect(node.props?.style).toMatchObject({ whiteSpace: 'pre-wrap' })
    expect(node.children).toBe('edit.configSessionDiscardedStructure')
  })
})

describe('词条在真实词表中存在', () => {
  it('提示标题、按钮与各原因的正文都能解析出真文案（不是 key 本身）', () => {
    for (const key of [
      ...REASONS.map(configDiscardReasonKey),
      'edit.configSessionDiscardedTitle',
      'misc.gotIt',
    ]) {
      const text = translate(key)
      expect(text).not.toBe(key)
      expect(text.trim().length).toBeGreaterThan(0)
    }
  })
})
