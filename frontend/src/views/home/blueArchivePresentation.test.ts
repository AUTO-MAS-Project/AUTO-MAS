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
  it('活动间隙选择最近结束的活动', () => {
    expect(blueArchivePresentation(overview, 35).versionName).toBe('当前活动')
  })
  it('只有预告时选择最近即将开始的活动', () => {
    expect(blueArchivePresentation(overview, 0).versionName).toBe('旧活动')
  })
  it('空列表不显示旧缓存的占位标题和封面', () => {
    expect(
      blueArchivePresentation({ ...overview, activities: [], cover: 'old.png' }, 20)
    ).toMatchObject({ versionName: '', cover: '', endTime: '' })
  })
})
