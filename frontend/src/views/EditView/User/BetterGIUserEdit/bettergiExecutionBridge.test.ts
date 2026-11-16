import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { describe, expect, it, vi } from 'vitest'

const bridgeSource = readFileSync(
  new URL('../../../../../../res/templates/BetterGI/MASOneDragon/main.js', import.meta.url),
  'utf8'
)

describe('BetterGI 地脉花执行层', () => {
  it.each([false, true])('旧计划中的冒险之证开关为 %s 时仍执行地脉花', async legacyValue => {
    // 新版 BGI 的公开任务参数不再提供 useAdventurerHandbook。
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
    expect(runLeyLine.mock.calls[0]?.[0]).not.toHaveProperty('useAdventurerHandbook')
    expect(messages.at(-1)).toBe('MAS_PLAN_DONE')
  })
})
