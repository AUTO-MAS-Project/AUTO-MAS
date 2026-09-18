import { describe, expect, it } from 'vitest'
import {
  buildSlotRows,
  collectMaterialOptions,
  formatActivityTime,
  resolveIntentStage,
  resolveUserInjectStatus,
  slotKeyOfIntent,
  type ActivityItem,
  type ActivityUserRow,
} from './activityStageSlots'

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
  skipDetail: '',
  ...overrides,
})

describe('slotKeyOfIntent', () => {
  it('maps intents to slot keys and drops unknown intents', () => {
    expect(slotKeyOfIntent('jade')).toBe('jade')
    expect(slotKeyOfIntent('last:2')).toBe('last:2')
    expect(slotKeyOfIntent('mat:30012')).toBe('mat')
    expect(slotKeyOfIntent('')).toBe('')
    expect(slotKeyOfIntent('bogus')).toBe('')
  })
})

describe('buildSlotRows', () => {
  it('orders rows as last:1..N, jade, mat', () => {
    const rows = buildSlotRows(srStages, [], false)
    expect(rows.map(row => row.key)).toEqual(['last:1', 'last:2', 'last:3', 'jade', 'mat'])
    expect(rows[0].stageCode).toBe('SR-8')
    expect(rows[1].stageCode).toBe('SR-7')
    expect(rows[3].stageCode).toBe('SR-5')
  })

  it('keeps assigned out-of-range last:N rows as missing', () => {
    const rows = buildSlotRows(srStages, ['last:5'], false)
    expect(rows.map(row => row.key)).toContain('last:5')
    expect(rows.find(row => row.key === 'last:5')?.stageCode).toBeNull()
  })

  it('adds a jade row when nobody is assigned but the event has a jade stage', () => {
    const rows = buildSlotRows(srStages, [], false)
    expect(rows.find(row => row.key === 'jade')?.stageCode).toBe('SR-5')
  })

  it('omits the jade row when the event has no jade stage and nobody is assigned', () => {
    const rows = buildSlotRows([stage('PA-8', '30063', '晶体元件')], [], false)
    expect(rows.map(row => row.key)).toEqual(['last:1', 'mat'])
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
    expect(resolveIntentStage('mat:31014', srStages)).toBe('SR-7')
    expect(resolveIntentStage('last:4', srStages)).toBeNull()
    expect(resolveIntentStage('mat:00000', srStages)).toBeNull()
  })

  it('keeps real material stages apart from the jade sentinel', () => {
    const stages = [
      stage('SR-7', '30012', '固源岩组'),
      stage('SR-6', '搓玉效率0.91', '搓玉效率0.91'),
    ]
    expect(resolveIntentStage('mat:30012', stages)).toBe('SR-7')
    expect(resolveIntentStage('jade', stages)).toBe('SR-6')
  })
})

describe('resolveUserInjectStatus', () => {
  it('reports the first blocking reason per user', () => {
    expect(
      resolveUserInjectStatus(user({ followsPlan: false }), srStages, 'ongoing'),
    ).toEqual({ willInject: false, reason: 'not-following' })
    expect(resolveUserInjectStatus(user({ status: false }), srStages, 'ongoing')).toEqual({
      willInject: false,
      reason: 'user-disabled',
    })
    expect(
      resolveUserInjectStatus(user({ ifActivityFirst: false }), srStages, 'ongoing'),
    ).toEqual({ willInject: false, reason: 'switch-off' })
    expect(
      resolveUserInjectStatus(user({ ifQuickConfig: false }), srStages, 'ongoing'),
    ).toEqual({ willInject: false, reason: 'no-quick-config' })
    expect(resolveUserInjectStatus(user({ intent: '' }), srStages, 'ongoing')).toEqual({
      willInject: false,
      reason: 'no-intent',
    })
    expect(
      resolveUserInjectStatus(user({ intent: 'last:9' }), srStages, 'ongoing'),
    ).toEqual({ willInject: false, reason: 'no-match' })
    expect(
      resolveUserInjectStatus(user({ intent: 'last:1' }), srStages, 'preview'),
    ).toEqual({ willInject: false, reason: 'gap' })
    expect(
      resolveUserInjectStatus(user({ intent: 'last:1', skipActive: true }), srStages, 'ongoing'),
    ).toEqual({ willInject: false, reason: 'skipped' })
    expect(
      resolveUserInjectStatus(user({ intent: 'last:1' }), srStages, 'ongoing'),
    ).toEqual({ willInject: true, reason: 'ok' })
  })
})

describe('collectMaterialOptions', () => {
  it('unions raw numeric drops across servers and translates names', () => {
    const options = collectMaterialOptions({
      Official: srStages,
      YoStarJP: [stage('PA-8', '30063', '晶体元件'), stage('PA-7', '玉关', '搓玉效率0.9')],
    })
    expect([...options.map(option => option.value)].sort()).toEqual([
      '30013',
      '30031',
      '30063',
      '31014',
    ])
    expect(options.find(option => option.value === '31014')?.label).toBe(
      '化合切削液（31014）',
    )
  })
})

describe('formatActivityTime', () => {
  it('shifts UTC times into the activity timezone', () => {
    expect(formatActivityTime('2026/09/22 20:00:00', 8)).toBe('09-23 04:00')
    expect(formatActivityTime('2026/09/22 20:00:00', -7)).toBe('09-22 13:00')
  })
})
