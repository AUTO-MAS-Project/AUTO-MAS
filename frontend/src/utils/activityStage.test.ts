// 活动关共享纯逻辑里「当期进行中的活动名」这一判据的测试：
// 脚本页徽标与计划表指派表都靠它排除上期活动的遗留条目。
import { describe, expect, it } from 'vitest'
import type { ActivityItem } from '@/types/home'
import { ongoingActivityNames } from './activityStage'

const stage = (value: string, stageName: string): ActivityItem => ({
  Display: value,
  Value: value,
  RawDrop: '30031',
  Drop: '30031',
  DropName: '异铁组',
  Activity: {
    Tip: '',
    StageName: stageName,
    UtcStartTime: '2026/09/04 04:00:00',
    UtcExpireTime: '2026/09/18 03:59:00',
    TimeZone: 8,
  },
})

describe('ongoingActivityNames', () => {
  it('collects the activity name of each server once', () => {
    const names = ongoingActivityNames({
      Official: [stage('SR-8', '太阳甩在身后'), stage('SR-5', '太阳甩在身后')],
      YoStarJP: [stage('AT-8', '日服活动')],
    })
    expect([...names.Official]).toEqual(['太阳甩在身后'])
    expect([...names.YoStarJP]).toEqual(['日服活动'])
  })

  it('keeps a server with no ongoing activity as an empty set', () => {
    // 空集与「没有该服数据」是两种状态：前者判为没有进行中活动，后者在
    // ongoingSkipBook 里同样按空处理，界面都不会显示徽标
    const names = ongoingActivityNames({ YoStarEN: [] })
    expect(names.YoStarEN?.size).toBe(0)
  })

  it('returns an empty map when the overview has no stage data', () => {
    expect(ongoingActivityNames(undefined)).toEqual({})
    expect(ongoingActivityNames({})).toEqual({})
  })
})
