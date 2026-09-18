import { describe, expect, it } from 'vitest'
import { resolveActivityStageState } from './activityStageState'
import type { ActivityItem } from '@/types/home'

const stage = (value: string, rawDrop: string, dropName = rawDrop): ActivityItem => ({
  Display: value,
  Value: value,
  RawDrop: rawDrop,
  Drop: rawDrop,
  DropName: dropName,
  Activity: {
    Tip: '',
    StageName: '测试活动',
    UtcStartTime: '2026/09/04 04:00:00',
    UtcExpireTime: '2026/09/18 03:59:00',
    TimeZone: 8,
  },
})

const ongoing = [
  stage('SR-8', '30031', '异铁组'),
  stage('SR-7', '31014', '化合切削液'),
  stage('SR-5', '搓玉效率0.91', '搓玉效率0.91'),
]

describe('resolveActivityStageState', () => {
  it('reports a resolved ongoing intent as ok', () => {
    const state = resolveActivityStageState('last:2', ongoing, [])
    expect(state.tone).toBe('ok')
    expect(state.messageKey).toBe('edit.activityStateOk')
    expect(state.params).toEqual({ stage: 'SR-7', mat: '化合切削液', name: '测试活动' })
  })

  it('reports jade resolution and the no-jade case', () => {
    const ok = resolveActivityStageState('jade', ongoing, [])
    expect(ok.tone).toBe('ok')
    expect(ok.params.stage).toBe('SR-5')

    const noJade = resolveActivityStageState('jade', [ongoing[0]], [])
    expect(noJade).toEqual({
      tone: 'muted',
      messageKey: 'edit.activityStateNoJade',
      params: {},
    })
  })

  it('warns when the material is not dropped this period', () => {
    const state = resolveActivityStageState('mat:30063', ongoing, [])
    expect(state.tone).toBe('warn')
    expect(state.messageKey).toBe('edit.activityStateMatMissing')
    expect(state.params).toEqual({ mat: '30063' })

    const named = resolveActivityStageState('mat:30063', ongoing, [
      stage('PA-8', '30063', '晶体元件'),
    ])
    expect(named.params).toEqual({ mat: '晶体元件' })
  })

  it('marks out-of-range last:N as muted', () => {
    expect(resolveActivityStageState('last:9', ongoing, [])).toEqual({
      tone: 'muted',
      messageKey: 'edit.activityStateNoStage',
      params: { n: 9 },
    })
  })

  it('switches to info tone with 下期 prefix during the preview period', () => {
    const state = resolveActivityStageState('last:1', [], ongoing)
    expect(state.tone).toBe('info')
    expect(state.messageKey).toBe('edit.activityStatePreview')
    expect(state.params.stage).toBe('SR-8')
  })

  it('reports gap and empty-intent states', () => {
    expect(resolveActivityStageState('last:1', [], [])).toEqual({
      tone: 'muted',
      messageKey: 'edit.activityStateGap',
      params: {},
    })
    expect(resolveActivityStageState('', ongoing, [])).toEqual({
      tone: 'muted',
      messageKey: 'edit.activityStateNoIntent',
      params: {},
    })
  })
})
