// 活动关指派表纯逻辑的测试：行状态优先级、选关选项（含当前值兜底）、汇总与筛选。
import { describe, expect, it } from 'vitest'
import type { ActivityItem } from '@/types/home'
import {
  buildIntentOptions,
  isAttentionState,
  matchesFilter,
  resolveUserState,
  summarizeRows,
  type ActivityUserRow,
} from './activityUserRows'

const stage = (value: string, rawDrop: string, dropName = rawDrop): ActivityItem => ({
  Display: value,
  Value: value,
  RawDrop: rawDrop,
  Drop: rawDrop === '搓玉效率0.91' ? '30012' : rawDrop,
  DropName: dropName,
  Activity: {
    Tip: '',
    StageName: '测试活动',
    UtcStartTime: '2026/09/04 04:00:00',
    UtcExpireTime: '2026/09/18 03:59:00',
    TimeZone: 8,
  },
})

const srStages = [
  stage('SR-8', '30031', '异铁组'),
  stage('SR-7', '31014', '化合切削液'),
  stage('SR-5', '搓玉效率0.91'),
]

const user = (overrides: Partial<ActivityUserRow> = {}): ActivityUserRow => ({
  scriptId: 's1',
  userId: 'u1',
  userName: '账号01',
  server: 'Official',
  status: true,
  ifQuickConfig: true,
  ifActivityFirst: true,
  intent: 'last:1',
  skipToday: false,
  skipSummary: '',
  ...overrides,
})

describe('resolveUserState', () => {
  it('reports the first blocking reason in priority order', () => {
    expect(resolveUserState(user({ status: false }), srStages, 'ongoing')).toBe('disabled')
    expect(resolveUserState(user({ ifQuickConfig: false }), srStages, 'ongoing')).toBe(
      'no-quick-config'
    )
    expect(resolveUserState(user({ ifActivityFirst: false }), srStages, 'ongoing')).toBe(
      'switch-off'
    )
    expect(resolveUserState(user({ skipToday: true }), srStages, 'ongoing')).toBe('skipped')
    expect(resolveUserState(user({ intent: '' }), srStages, 'ongoing')).toBe('no-intent')
    expect(resolveUserState(user(), srStages, 'ongoing')).toBe('inject')
  })

  it('treats an unresolvable intent as no-match and the gap period as no-activity', () => {
    expect(resolveUserState(user({ intent: 'last:9' }), srStages, 'ongoing')).toBe('no-match')
    expect(resolveUserState(user({ intent: 'pos:9' }), srStages, 'ongoing')).toBe('no-match')
    expect(resolveUserState(user({ intent: 'jade' }), [srStages[0]], 'ongoing')).toBe('no-match')
    expect(resolveUserState(user(), srStages, 'gap')).toBe('no-activity')
    // 下期预览期按预览关卡判定，能解析就算会注入（活动开启后生效）
    expect(resolveUserState(user(), srStages, 'preview')).toBe('inject')
  })
})

describe('buildIntentOptions', () => {
  it('lists empty, last:1..N then jade in stage order', () => {
    const options = buildIntentOptions(srStages, '')
    expect(options.map(option => option.value)).toEqual(['', 'last:1', 'last:2', 'jade'])
    expect(options[1].labelParams).toEqual({ n: 1, stage: 'SR-8', mat: '异铁组' })
    expect(options[3].labelParams).toEqual({
      stage: 'SR-5',
      mat: '搓玉效率0.91',
    })
  })

  it('keeps the current value visible when this period cannot resolve it', () => {
    const legacy = buildIntentOptions(srStages, 'pos:2').at(-1)
    expect(legacy?.value).toBe('pos:2')
    expect(legacy?.labelKey).toBe('plan.activity.intentLegacy')

    const outOfRange = buildIntentOptions(srStages, 'last:9').at(-1)
    expect(outOfRange?.value).toBe('last:9')
    expect(outOfRange?.labelKey).toBe('plan.activity.intentLastMissing')

    const noJade = buildIntentOptions([srStages[0], srStages[1]], 'jade').at(-1)
    expect(noJade?.labelKey).toBe('plan.activity.intentJadeMissing')

    // 当前值本来就在选项里时不重复补
    const plain = buildIntentOptions(srStages, 'last:2')
    expect(plain.filter(option => option.value === 'last:2')).toHaveLength(1)
  })
})

describe('filter and summary', () => {
  it('counts attention states and matches the filters', () => {
    const states = ['inject', 'inject', 'no-intent', 'no-quick-config', 'skipped'] as const
    expect(summarizeRows([...states])).toEqual({
      followed: 5,
      willInject: 2,
      attention: 2,
    })
    // 用户自己关掉的、以及还没选的，都不算注意项
    expect(isAttentionState('switch-off')).toBe(false)
    expect(isAttentionState('no-intent')).toBe(false)
    expect(matchesFilter('no-intent', 'no-intent')).toBe(true)
    expect(matchesFilter('inject', 'attention')).toBe(false)
    expect(matchesFilter('skipped', 'attention')).toBe(true)
    expect(matchesFilter('switch-off', 'all')).toBe(true)
  })
})
