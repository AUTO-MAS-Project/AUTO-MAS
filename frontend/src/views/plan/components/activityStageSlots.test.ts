import { describe, expect, it } from 'vitest'
import type { ActivityItem } from '@/types/home'
import { formatActivityTime, resolveIntentStage, slotKeyOfIntent } from '@/utils/activityStage'
import { buildSlotRows, resolveUserInjectStatus, type ActivityUserRow } from './activityStageSlots'

const stage = (value: string, rawDrop: string, dropName = rawDrop): ActivityItem => ({
  Display: value,
  Value: value,
  RawDrop: rawDrop,
  Drop: rawDrop === '玉关' ? '30012' : rawDrop,
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
  stage('SR-6', '30013', '褐素纤维'),
  stage('SR-5', '搓玉效率0.91', '搓玉效率0.91'),
]

const user = (overrides: Partial<ActivityUserRow>): ActivityUserRow => ({
  scriptId: 's1',
  scriptName: 'MAA 脚本',
  userId: 'u1',
  userName: '账号01',
  server: 'Official',
  status: true,
  stageMode: 'p1',
  followsPlan: true,
  planLabel: '',
  ifQuickConfig: true,
  ifActivityFirst: true,
  intent: '',
  skipActive: false,
  skipDays: 0,
  skipSummary: '',
  ...overrides,
})

describe('slotKeyOfIntent', () => {
  it('maps intents to slot keys and drops unknown intents', () => {
    expect(slotKeyOfIntent('jade')).toBe('jade')
    expect(slotKeyOfIntent('last:2')).toBe('last:2')
    // 旧版序号是独立的槽位键：与倒N 同形不同义，不能被并进 last:N 槽
    expect(slotKeyOfIntent('pos:2')).toBe('pos:2')
    expect(slotKeyOfIntent('')).toBe('')
    expect(slotKeyOfIntent('bogus')).toBe('')
  })
})

describe('buildSlotRows', () => {
  it('orders rows as last:1..N, jade', () => {
    const rows = buildSlotRows(srStages, [], false)
    expect(rows.map(row => row.key)).toEqual(['last:1', 'last:2', 'last:3', 'jade'])
    expect(rows[0].stageCode).toBe('SR-8')
    expect(rows[1].stageCode).toBe('SR-7')
    expect(rows[3].stageCode).toBe('SR-5')
  })

  it('keeps assigned out-of-range last:N rows as missing', () => {
    const rows = buildSlotRows(srStages, ['last:5'], false)
    expect(rows.map(row => row.key)).toContain('last:5')
    const missing = rows.find(row => row.key === 'last:5')
    expect(missing?.stageCode).toBeNull()
    // 真实数据行不是骨架行（否则活动期会误标「待下期活动录入」）
    expect(missing?.skeleton).toBe(false)
  })

  it('adds a jade row when nobody is assigned but the event has a jade stage', () => {
    const rows = buildSlotRows(srStages, [], false)
    expect(rows.find(row => row.key === 'jade')?.stageCode).toBe('SR-5')
  })

  it('omits the jade row when the event has no jade stage and nobody is assigned', () => {
    const rows = buildSlotRows([stage('PA-8', '30063', '晶体元件')], [], false)
    expect(rows.map(row => row.key)).toEqual(['last:1'])
  })

  it('falls back to the default skeleton when no stage data exists', () => {
    const rows = buildSlotRows([], [], false)
    expect(rows.map(row => row.key)).toEqual(['last:1', 'last:2', 'last:3', 'jade'])
    expect(rows.every(row => row.skeleton && row.notStarted && row.stageCode === null)).toBe(true)
  })

  it('pads the skeleton beyond 倒3 for assigned out-of-range intents', () => {
    const rows = buildSlotRows([], ['last:5'], false)
    expect(rows.map(row => row.key)).toEqual([
      'last:1',
      'last:2',
      'last:3',
      'last:4',
      'last:5',
      'jade',
    ])
    expect(rows.find(row => row.key === 'last:4')?.skeleton).toBe(true)
  })

  it('marks preview rows as not started', () => {
    const rows = buildSlotRows(srStages, [], true)
    expect(rows.every(row => row.notStarted)).toBe(true)
  })
})

describe('resolveIntentStage', () => {
  it('resolves intents against stages with the same anchor as the backend', () => {
    expect(resolveIntentStage('last:1', srStages)).toBe('SR-8')
    expect(resolveIntentStage('last:2', srStages)).toBe('SR-7')
    expect(resolveIntentStage('jade', srStages)).toBe('SR-5')
  })

  it('keeps out-of-range intents unmatched', () => {
    expect(resolveIntentStage('last:3', srStages)).toBe('SR-6')
    expect(resolveIntentStage('last:5', srStages)).toBeNull()
  })

  it('does not read a new-style last:N as the legacy index', () => {
    // 同一期选的「倒3」在下期只剩 2 个材料关 + 玉关时，曾被旧序号兜底认领去
    // 刷玉关；现在如实判越界，把玉关留给显式的「搓玉」
    const shrunk = [stage('SR-8', '30031', '异铁组'), stage('SR-5', '搓玉效率0.91')]
    expect(resolveIntentStage('last:3', shrunk)).toBeNull()
    expect(resolveIntentStage('jade', shrunk)).toBe('SR-5')
  })

  it('resolves the legacy index by list position', () => {
    // 旧版编号是 MAA 列表位置（末位 SR-5 是玉关），迁移值 pos:N 按位置取，
    // 与后端 _resolve_activity_stage 的 pos 分支同规则
    expect(resolveIntentStage('pos:1', srStages)).toBe('SR-8')
    expect(resolveIntentStage('pos:4', srStages)).toBe('SR-5')
    expect(resolveIntentStage('pos:5', srStages)).toBeNull()
  })

  it('detects jade by raw drop even when the normalized id collides', () => {
    const stages = [
      stage('SR-7', '30012', '固源岩组'),
      stage('SR-6', '搓玉效率0.91', '搓玉效率0.91'),
    ]
    expect(resolveIntentStage('jade', stages)).toBe('SR-6')
  })
})

describe('resolveUserInjectStatus', () => {
  it('reports the first blocking reason per user', () => {
    expect(resolveUserInjectStatus(user({ followsPlan: false }), srStages, 'ongoing')).toEqual({
      willInject: false,
      reason: 'not-following',
    })
    expect(resolveUserInjectStatus(user({ status: false }), srStages, 'ongoing')).toEqual({
      willInject: false,
      reason: 'user-disabled',
    })
    expect(resolveUserInjectStatus(user({ ifActivityFirst: false }), srStages, 'ongoing')).toEqual({
      willInject: false,
      reason: 'switch-off',
    })
    expect(resolveUserInjectStatus(user({ ifQuickConfig: false }), srStages, 'ongoing')).toEqual({
      willInject: false,
      reason: 'no-quick-config',
    })
    expect(resolveUserInjectStatus(user({ intent: '' }), srStages, 'ongoing')).toEqual({
      willInject: false,
      reason: 'no-intent',
    })
    expect(resolveUserInjectStatus(user({ intent: 'last:9' }), srStages, 'ongoing')).toEqual({
      willInject: false,
      reason: 'no-match',
    })
    expect(resolveUserInjectStatus(user({ intent: 'last:1' }), srStages, 'preview')).toEqual({
      willInject: false,
      reason: 'gap',
    })
    expect(
      resolveUserInjectStatus(user({ intent: 'last:1', skipActive: true }), srStages, 'ongoing')
    ).toEqual({ willInject: false, reason: 'skipped' })
    expect(resolveUserInjectStatus(user({ intent: 'last:1' }), srStages, 'ongoing')).toEqual({
      willInject: true,
      reason: 'ok',
    })
  })
})

describe('formatActivityTime', () => {
  it('shifts UTC times into the activity timezone', () => {
    expect(formatActivityTime('2026/09/22 20:00:00', 8)).toBe('09-23 04:00')
    expect(formatActivityTime('2026/09/22 20:00:00', -7)).toBe('09-22 13:00')
  })
})
