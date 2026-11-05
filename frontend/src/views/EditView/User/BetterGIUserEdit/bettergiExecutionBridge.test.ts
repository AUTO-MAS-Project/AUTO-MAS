import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { describe, expect, it, vi } from 'vitest'

const bridgeSource = readFileSync(
  new URL('../../../../../../res/templates/BetterGI/MASOneDragon/main.js', import.meta.url),
  'utf8'
)

describe('BetterGI 地脉花执行层', () => {
  it.each([
    [false, false],
    [false, true],
    [true, false],
    [true, true],
  ])('宿主支持旧参数=%s，计划开关=%s 时仍执行地脉花', async (supportsHandbook, legacyValue) => {
    // BGI 0.64.0 有此属性，0.65.0 已无此属性；旧宿主默认值故意与计划相反。
    class LeyLineParam {
      isResinExhaustionMode = false
      openModeCountMin = false
      team = ''
      friendshipTeam = ''

      constructor(
        public count: number,
        public country: string,
        public leyLineOutcropType: string
      ) {
        if (supportsHandbook) {
          Object.defineProperty(this, 'useAdventurerHandbook', {
            value: !legacyValue,
            writable: true,
            enumerable: true,
          })
        }
        Object.seal(this)
      }
    }

    const runLeyLine = vi.fn().mockResolvedValue(undefined)
    const messages: string[] = []
    await runInNewContext(`'use strict';\n${bridgeSource}`, {
      AutoLeyLineOutcropParam: LeyLineParam,
      dispatcher: { runAutoLeyLineOutcropTask: runLeyLine },
      genshin: { returnMainUi: vi.fn().mockResolvedValue(undefined) },
      log: { info: (line: string) => messages.push(line) },
      settings: {
        plan: JSON.stringify({
          version: 1,
          steps: [
            {
              uid: 'leyline',
              name: '自动地脉花',
              enabled: true,
              settings: {
                count: 3,
                country: '蒙德',
                leyLineOutcropType: '启示之花',
                useAdventurerHandbook: legacyValue,
              },
            },
          ],
        }),
      },
    })

    expect(messages.filter(line => line.startsWith('MAS_STEP_FAIL:'))).toEqual([])
    expect(messages).toContain('MAS_STEP_DONE: leyline 自动地脉花')
    expect(runLeyLine.mock.calls.map(([param]) => param)).toEqual([
      expect.objectContaining({ count: 3, country: '蒙德', leyLineOutcropType: '启示之花' }),
    ])
    if (supportsHandbook) {
      expect(runLeyLine.mock.calls[0]?.[0]).toHaveProperty('useAdventurerHandbook', legacyValue)
    } else {
      expect(runLeyLine.mock.calls[0]?.[0]).not.toHaveProperty('useAdventurerHandbook')
    }
    expect(messages.at(-1)).toBe('MAS_PLAN_DONE')
  })
})
