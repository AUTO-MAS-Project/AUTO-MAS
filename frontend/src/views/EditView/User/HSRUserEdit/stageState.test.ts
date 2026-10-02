import { describe, expect, it } from 'vitest'

import {
  hasLegacyEngineMismatch,
  isStageMissingForEngine,
  readChannelStage,
  readEowStage,
  resolveStageChannel,
  writeEngineStage,
} from './stageState'

const payload = (engine: 'SRA' | 'M7A', label: string) => ({ engine, label, value: label })

describe('stageState', () => {
  it('按引擎、按副本类型分存：切换类型读回该类型之前的选择', () => {
    const stage = {
      Channel: 'Relic' as const,
      ScriptStage: JSON.stringify({
        version: 2,
        byEngine: {
          SRA: {
            engine: 'SRA',
            stages: {
              CalyxGolden: payload('SRA', '金'),
              Relic: payload('SRA', '隧洞'),
            },
          },
        },
      }),
      ScriptEchoOfWar: { version: 2, byEngine: { SRA: payload('SRA', '历战') } },
    }
    expect(readChannelStage(stage, 'SRA', 'Relic')?.label).toBe('隧洞')
    expect(readChannelStage(stage, 'SRA', 'CalyxGolden')?.label).toBe('金')
    expect(readChannelStage(stage, 'SRA', 'Ornament')).toBeNull()
    expect(readChannelStage(stage, 'M7A', 'Relic')).toBeNull()
    expect(readEowStage(stage, 'SRA')?.label).toBe('历战')
    expect(isStageMissingForEngine(stage, 'M7A')).toBe(true)
    expect(isStageMissingForEngine(stage, 'SRA')).toBe(false)
  })

  it('写回只动当前引擎，写空时删掉该引擎', () => {
    const raw = { version: 2, byEngine: { SRA: payload('SRA', 'a') } }
    expect(writeEngineStage(raw, 'M7A', payload('M7A', 'b'))).toEqual({
      version: 2,
      byEngine: { SRA: payload('SRA', 'a'), M7A: payload('M7A', 'b') },
    })
    expect(writeEngineStage(raw, 'SRA', null)).toEqual({})
  })

  it('旧格式里存的是另一引擎：判为需要重选', () => {
    const stage = { ScriptStage: { engine: 'M7A', stages: {} }, ScriptEchoOfWar: '{ }' }
    expect(hasLegacyEngineMismatch(stage, 'SRA')).toBe(true)
    expect(hasLegacyEngineMismatch(stage, 'M7A')).toBe(false)
    expect(isStageMissingForEngine(stage, 'SRA')).toBe(false)
  })

  it('未知副本类型回落到拟造花萼（金）', () => {
    expect(resolveStageChannel('Ornament')).toBe('Ornament')
    expect(resolveStageChannel('Unknown')).toBe('CalyxGolden')
    expect(resolveStageChannel(undefined)).toBe('CalyxGolden')
  })
})
