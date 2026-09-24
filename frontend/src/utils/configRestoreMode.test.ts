// 配置来源共用判定与提示文案的纯逻辑测试（不挂载组件，直接测分支行为）。
import { describe, expect, it } from 'vitest'
import type { VNode } from 'vue'

import {
  buildCorruptedForceConfirm,
  buildRestoreConfirm,
  corruptedForceConfirmContent,
  isCrossSourceRestore,
  sourceLabelKey,
  sourceTagColor,
} from './configRestoreMode'

const t = (key: string, named?: Record<string, string>) =>
  named ? `${key}(${JSON.stringify(named)})` : key

describe('sourceLabelKey / sourceTagColor', () => {
  it('三态取值映射到各自词条与标签色', () => {
    expect(sourceLabelKey('脚本')).toBe('edit.configRestoreModeScript')
    expect(sourceLabelKey('用户')).toBe('edit.configRestoreModeUser')
    expect(sourceLabelKey('直控')).toBe('edit.configRestoreModeDirect')
    expect(sourceTagColor('脚本')).toBe('blue')
    expect(sourceTagColor('用户')).toBe('green')
    expect(sourceTagColor('直控')).toBe('orange')
  })

  it('未知值按用户级兜底', () => {
    expect(sourceLabelKey('未知')).toBe('edit.configRestoreModeUser')
    expect(sourceTagColor('未知')).toBe('green')
  })
})

describe('isCrossSourceRestore', () => {
  it('两侧都已标注且不一致才跨来源', () => {
    expect(isCrossSourceRestore('脚本', '用户')).toBe(true)
    expect(isCrossSourceRestore('用户', '脚本')).toBe(true)
  })

  it('同来源或任一侧未标注都不跨', () => {
    expect(isCrossSourceRestore('脚本', '脚本')).toBe(false)
    expect(isCrossSourceRestore('脚本', null)).toBe(false)
    expect(isCrossSourceRestore(null, '脚本')).toBe(false)
    expect(isCrossSourceRestore(undefined, undefined)).toBe(false)
  })
})

describe('buildRestoreConfirm', () => {
  const base = { title: '恢复确认', desc: '将覆盖当前配置' }

  it('未跨来源：保留原标题，仅原始描述一段', () => {
    expect(buildRestoreConfirm(t, base, '脚本', '脚本')).toEqual({
      title: '恢复确认',
      paragraphs: ['将覆盖当前配置'],
    })
    expect(buildRestoreConfirm(t, base, null, null)).toEqual({
      title: '恢复确认',
      paragraphs: ['将覆盖当前配置'],
    })
  })

  it('跨来源：换标题并追加来源切换说明（含两侧标签插值）', () => {
    const result = buildRestoreConfirm(t, base, '用户', '脚本')
    expect(result.title).toBe('edit.configRestoreCrossSourceTitle')
    expect(result.paragraphs[0]).toBe('将覆盖当前配置')
    expect(result.paragraphs[1]).toContain('"backup":"edit.configRestoreModeUser"')
    expect(result.paragraphs[1]).toContain('"current":"edit.configRestoreModeScript"')
    expect(result.paragraphs).toHaveLength(2) // 备份为用户级：无共享覆盖提醒
  })

  it('备份来自脚本级时额外提醒共享配置被覆盖', () => {
    const result = buildRestoreConfirm(t, base, '脚本', '用户')
    expect(result.paragraphs).toHaveLength(3)
    expect(result.paragraphs[2]).toBe('edit.configRestoreCrossSourceShared')
  })

  it('备份来自直控：跨来源但不追加共享覆盖提醒（只有脚本备份才提醒）', () => {
    const result = buildRestoreConfirm(t, base, '直控', '脚本')
    expect(result.title).toBe('edit.configRestoreCrossSourceTitle')
    expect(result.paragraphs).toHaveLength(2)
  })

  it('当前来源为直控：直控备份同源不跨；脚本备份跨来源仍追加共享提醒', () => {
    expect(buildRestoreConfirm(t, base, '直控', '直控')).toEqual({
      title: '恢复确认',
      paragraphs: ['将覆盖当前配置'],
    })
    const result = buildRestoreConfirm(t, base, '脚本', '直控')
    expect(result.title).toBe('edit.configRestoreCrossSourceTitle')
    expect(result.paragraphs).toHaveLength(3)
    expect(result.paragraphs[2]).toBe('edit.configRestoreCrossSourceShared')
  })
})

describe('buildCorruptedForceConfirm / corruptedForceConfirmContent', () => {
  it('损坏位置由后端原文透出，标题与按钮取专用词条', () => {
    expect(buildCorruptedForceConfirm(t, '配置文件已损坏，无法安全读取：X/one_dragon.yml')).toEqual(
      {
        title: 'edit.configRestoreCorruptedTitle',
        detail: '配置文件已损坏，无法安全读取：X/one_dragon.yml',
        desc: 'edit.configRestoreCorruptedDesc',
        okText: 'edit.configRestoreForceAction',
      }
    )
  })

  it('渲染为「红字损坏位置 + 风险说明」两段', () => {
    const paragraphs = corruptedForceConfirmContent('损坏位置', '风险说明').children as VNode[]
    expect(paragraphs).toHaveLength(2)
    expect(paragraphs[0].props?.style).toMatchObject({
      color: 'var(--ant-color-error)',
    })
    expect(paragraphs[0].children).toBe('损坏位置')
    expect(paragraphs[1].children).toBe('风险说明')
  })
})
