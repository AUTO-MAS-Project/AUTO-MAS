import { describe, expect, it } from 'vitest'
import { buildEndfieldOverview, restoreEndfieldSourceData } from './endfieldActivityTransform'

describe('终末地活动快照', () => {
  it('恢复 JSON 快照中的日期字符串', () => {
    const source = restoreEndfieldSourceData({
      versionId: 'v1',
      sourceUpdatedAt: '',
      activities: [
        {
          activityId: 'a',
          name: '活动',
          startTime: '2026-09-01T00:00:00.000Z',
          endTime: '2026-09-02T00:00:00.000Z',
          imageUrl: '',
          tags: [],
          sortId: 0,
        },
      ],
      pools: [],
    })

    expect(source?.activities[0].endTime).toBeInstanceOf(Date)
    expect(() => buildEndfieldOverview(source!, new Date('2026-09-01T12:00:00.000Z'))).not.toThrow()
  })
})
