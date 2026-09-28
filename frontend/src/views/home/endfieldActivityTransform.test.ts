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

  it('活动与卡池按结束时间升序展示，同结束时间保持 sortId 顺序', () => {
    const source = restoreEndfieldSourceData({
      versionId: 'v1',
      sourceUpdatedAt: '',
      activities: [
        {
          activityId: 'late',
          name: '后结束',
          startTime: '2026-09-01T00:00:00.000Z',
          endTime: '2026-09-20T00:00:00.000Z',
          imageUrl: '',
          tags: [],
          sortId: 0,
        },
        {
          activityId: 'soon',
          name: '先结束',
          startTime: '2026-09-01T00:00:00.000Z',
          endTime: '2026-09-05T00:00:00.000Z',
          imageUrl: '',
          tags: [],
          sortId: 1,
        },
        {
          activityId: 'tied',
          name: '同时间',
          startTime: '2026-09-01T00:00:00.000Z',
          endTime: '2026-09-05T00:00:00.000Z',
          imageUrl: '',
          tags: [],
          sortId: 0,
        },
      ],
      pools: [
        {
          poolId: 'pool-late',
          name: '后结束池',
          poolType: '特许寻访',
          startTime: '2026-09-01T00:00:00.000Z',
          endTime: '2026-09-30T00:00:00.000Z',
          imageUrl: '',
          upCharacters: [],
          sortId: 5,
        },
        {
          poolId: 'pool-soon',
          name: '先结束池',
          poolType: '特许寻访',
          startTime: '2026-09-01T00:00:00.000Z',
          endTime: '2026-09-10T00:00:00.000Z',
          imageUrl: '',
          upCharacters: [],
          sortId: 9,
        },
      ],
    })

    const overview = buildEndfieldOverview(source!, new Date('2026-09-02T00:00:00.000Z'))

    expect(overview.Activities.map(activity => activity.Id)).toEqual(['tied', 'soon', 'late'])
    expect(overview.Pools.map(pool => pool.Id)).toEqual(['pool-soon', 'pool-late'])
  })
})
