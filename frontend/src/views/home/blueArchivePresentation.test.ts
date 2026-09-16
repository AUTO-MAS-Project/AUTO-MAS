import { describe, expect, it } from 'vitest'
import { createEmptySraActivityOverview } from '@/types/home'
import { blueArchivePresentation } from './blueArchivePresentation'

const activity = (name: string, start: number, end: number, cover = '') => ({
  name,
  description: '',
  startTime: new Date(start).toISOString(),
  endTime: new Date(end).toISOString(),
  cover,
})
const overview = {
  ...createEmptySraActivityOverview(),
  versionName: '国服活动',
  activities: [
    activity('旧活动', 1, 10, 'old.png'),
    activity('当前活动', 15, 30),
    activity('下期活动', 40, 50, 'next.png'),
  ],
}

describe('blueArchivePresentation', () => {
  it('使用当前活动名称和时间，不借用其它活动的封面', () => {
    expect(blueArchivePresentation(overview, 20)).toMatchObject({
      versionName: '当前活动',
      cover: '',
      endTime: new Date(30).toISOString(),
    })
  })
  it('活动间隙优先展示已排期的下一场', () => {
    expect(blueArchivePresentation(overview, 35)).toMatchObject({
      versionName: '下期活动',
      cover: 'next.png',
    })
  })
  it('没有进行中也没有已排期的下一场时，退回最近结束的活动', () => {
    const onlyEnded = { ...overview, activities: overview.activities.slice(0, 2) }
    expect(blueArchivePresentation(onlyEnded, 35)).toMatchObject({
      versionName: '当前活动',
      endTime: new Date(30).toISOString(),
    })
  })
  it('只有预告时选择最近即将开始的活动', () => {
    expect(blueArchivePresentation(overview, 0).versionName).toBe('旧活动')
  })
  it('忽略开始与结束同一时刻的条目', () => {
    const withInstantNotice = {
      ...overview,
      activities: [...overview.activities, activity('常驻化公告', 36, 36, 'instant.png')],
    }
    expect(blueArchivePresentation(withInstantNotice, 35).versionName).toBe('下期活动')
  })
  it('空列表不显示旧缓存的占位标题和封面', () => {
    expect(
      blueArchivePresentation({ ...overview, activities: [], cover: 'old.png' }, 20)
    ).toMatchObject({ versionName: '', cover: '', endTime: '' })
  })
})
