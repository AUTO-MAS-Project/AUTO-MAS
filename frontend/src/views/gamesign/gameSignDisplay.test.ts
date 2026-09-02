import { describe, expect, it } from 'vitest'
import {
  buildPlatformTag,
  buildUserTags,
  buildUserTagsMap,
  getSignDetailAlias,
  getSignDetailClass,
  getSignStatusKey,
  getTagClass,
  getTagText,
  hasPlatformToken,
  parseSignResult,
  parseTaygedoCredential,
  resolveTagStatus,
  type AccountGroup,
  type GameItem,
  type SignAccount,
} from './gameSignDisplay'

const game = (status: string, extra: Partial<GameItem> = {}): GameItem => ({
  game: '测试游戏',
  status,
  reward: '',
  reason: '',
  ...extra,
})

const group = (uid: string, games: GameItem[], alias = '别名'): AccountGroup => ({
  account_alias: alias,
  account_uid: uid,
  games,
})

const account = (extra: Partial<SignAccount> = {}): SignAccount => ({
  uid: 'u1',
  MiyousheToken: '',
  CloudGenshinToken: '',
  KuroToken: '',
  SklandToken: '',
  TaygedoToken: '',
  ...extra,
})

describe('解析签到结果', () => {
  it('正常 JSON 原样解析', () => {
    const parsed = parseSignResult(
      '{"米游社":[{"account_alias":"a","account_uid":"u1","games":[]}]}'
    )
    expect(parsed['米游社'].length).toBe(1)
    expect(parsed['米游社'][0].account_uid).toBe('u1')
  })

  it('空值、占位符和空对象都退化为空结果', () => {
    expect(parseSignResult('')).toEqual({})
    expect(parseSignResult(undefined)).toEqual({})
    expect(parseSignResult(null)).toEqual({})
    expect(parseSignResult('{}')).toEqual({})
    expect(parseSignResult('-')).toEqual({})
  })

  it('非法 JSON 不抛错', () => {
    expect(parseSignResult('{不是 JSON')).toEqual({})
  })

  it('JSON 合法但不是对象时也退化为空结果', () => {
    expect(parseSignResult('[]')).toEqual({})
    expect(parseSignResult('5')).toEqual({})
    expect(parseSignResult('null')).toEqual({})
  })
})

describe('解析塔吉多凭据', () => {
  it('空值两者都不可用', () => {
    expect(parseTaygedoCredential('')).toEqual({ taygedo: false, cloud: false })
    expect(parseTaygedoCredential('   ')).toEqual({ taygedo: false, cloud: false })
    expect(parseTaygedoCredential(undefined)).toEqual({ taygedo: false, cloud: false })
  })

  it('refreshToken 或 accessToken 任一存在即塔吉多可用', () => {
    expect(parseTaygedoCredential('{"refreshToken":"r"}')).toEqual({ taygedo: true, cloud: false })
    expect(parseTaygedoCredential('{"accessToken":"a"}')).toEqual({ taygedo: true, cloud: false })
  })

  it('云异环需要 cloudToken 和 cloudUserId 同时存在', () => {
    expect(parseTaygedoCredential('{"cloudToken":"c","cloudUserId":"1"}')).toEqual({
      taygedo: false,
      cloud: true,
    })
    expect(parseTaygedoCredential('{"cloudToken":"c"}')).toEqual({ taygedo: false, cloud: false })
    expect(parseTaygedoCredential('{"cloudUserId":"1"}')).toEqual({ taygedo: false, cloud: false })
  })

  it('老版裸 Token 只认塔吉多', () => {
    expect(parseTaygedoCredential('raw-token-string')).toEqual({ taygedo: true, cloud: false })
  })
})

describe('社区凭据判定', () => {
  it('各社区读各自的 Token 字段', () => {
    expect(hasPlatformToken(account({ MiyousheToken: 't' }), '米游社')).toBe(true)
    expect(hasPlatformToken(account({ CloudGenshinToken: 't' }), '米游社')).toBe(true)
    expect(hasPlatformToken(account({ KuroToken: 't' }), '库街区')).toBe(true)
    expect(hasPlatformToken(account({ SklandToken: 't' }), '森空岛')).toBe(true)
    expect(hasPlatformToken(account({ MiyousheToken: 't' }), '库街区')).toBe(false)
  })

  it('塔吉多和云异环共用 TaygedoToken', () => {
    const both = account({
      TaygedoToken: '{"refreshToken":"r","cloudToken":"c","cloudUserId":"1"}',
    })
    expect(hasPlatformToken(both, '塔吉多')).toBe(true)
    expect(hasPlatformToken(both, '云异环')).toBe(true)

    const cloudOnly = account({ TaygedoToken: '{"cloudToken":"c","cloudUserId":"1"}' })
    expect(hasPlatformToken(cloudOnly, '塔吉多')).toBe(false)
    expect(hasPlatformToken(cloudOnly, '云异环')).toBe(true)
  })

  it('未知社区一律不算', () => {
    expect(hasPlatformToken(account({ MiyousheToken: 't' }), '不存在的社区')).toBe(false)
  })
})

describe('标签状态判定', () => {
  it('没有结果算未签', () => {
    expect(resolveTagStatus({ totalCount: 0, signedCount: 0, failedCount: 0, riskCount: 0 })).toBe(
      'unsigned'
    )
  })

  it('风控优先于失败', () => {
    expect(resolveTagStatus({ totalCount: 3, signedCount: 1, failedCount: 1, riskCount: 1 })).toBe(
      'risk'
    )
  })

  it('失败优先于部分已签', () => {
    expect(resolveTagStatus({ totalCount: 3, signedCount: 2, failedCount: 1, riskCount: 0 })).toBe(
      'failed'
    )
  })

  it('全部已签为 signed，部分为 partial，一个都没签为 unsigned', () => {
    expect(resolveTagStatus({ totalCount: 2, signedCount: 2, failedCount: 0, riskCount: 0 })).toBe(
      'signed'
    )
    expect(resolveTagStatus({ totalCount: 2, signedCount: 1, failedCount: 0, riskCount: 0 })).toBe(
      'partial'
    )
    expect(resolveTagStatus({ totalCount: 2, signedCount: 0, failedCount: 0, riskCount: 0 })).toBe(
      'unsigned'
    )
  })
})

describe('聚合单个社区标签', () => {
  it('「成功」和「已签到」都计入已签数', () => {
    const tag = buildPlatformTag('米游社', [], [game('成功'), game('已签到'), game('失败')])
    expect(tag.totalCount).toBe(3)
    expect(tag.signedCount).toBe(2)
    expect(tag.failedCount).toBe(1)
    expect(tag.riskCount).toBe(0)
    expect(tag.status).toBe('failed')
  })

  it('风控单独计数', () => {
    const tag = buildPlatformTag('森空岛', [], [game('风控'), game('成功')])
    expect(tag.riskCount).toBe(1)
    expect(tag.status).toBe('risk')
  })
})

describe('聚合用户标签列表', () => {
  it('只输出配置了凭据的社区，且顺序固定', () => {
    const tags = buildUserTags(
      account({ KuroToken: 'k', MiyousheToken: 'm', SklandToken: 's' }),
      {}
    )
    expect(tags.map(t => t.platform)).toEqual(['米游社', '森空岛', '库街区'])
  })

  it('没有任何凭据时返回空列表', () => {
    expect(buildUserTags(account(), {})).toEqual([])
  })

  it('只归拢 account_uid 匹配的账号组', () => {
    const tags = buildUserTags(account({ uid: 'u1', MiyousheToken: 'm' }), {
      米游社: [group('u1', [game('成功')]), group('u2', [game('失败')])],
    })
    expect(tags.length).toBe(1)
    expect(tags[0].groups.length).toBe(1)
    expect(tags[0].totalCount).toBe(1)
    expect(tags[0].status).toBe('signed')
  })

  it('同一用户的多个账号组会合并游戏列表', () => {
    const tags = buildUserTags(account({ uid: 'u1', MiyousheToken: 'm' }), {
      米游社: [group('u1', [game('成功')]), group('u1', [game('失败')])],
    })
    expect(tags[0].groups.length).toBe(2)
    expect(tags[0].totalCount).toBe(2)
    expect(tags[0].status).toBe('failed')
  })

  it('有凭据但结果里没有该社区时也出标签，计数为 0', () => {
    const tags = buildUserTags(account({ MiyousheToken: 'm' }), {})
    expect(tags.length).toBe(1)
    expect(tags[0].totalCount).toBe(0)
    expect(tags[0].status).toBe('unsigned')
  })
})

describe('聚合全部用户标签', () => {
  it('按 uid 建索引，每个用户都有条目', () => {
    const map = buildUserTagsMap(
      [account({ uid: 'u1', MiyousheToken: 'm' }), account({ uid: 'u2' })],
      { 米游社: [group('u1', [game('成功')])] }
    )
    expect(map.size).toBe(2)
    expect(map.get('u1')?.[0].signedCount).toBe(1)
    expect(map.get('u2')).toEqual([])
  })

  it('用户列表为空时返回空 Map', () => {
    expect(buildUserTagsMap([], {}).size).toBe(0)
  })
})

describe('Tooltip 行展示', () => {
  it('别名优先取 account 的「别名/uid」前半段', () => {
    expect(
      getSignDetailAlias(group('u1', [], '组别名'), game('成功', { account: '小明/12345' }))
    ).toBe('小明')
  })

  it('占位别名回退到账号组别名', () => {
    expect(getSignDetailAlias(group('u1', [], '组别名'), game('成功', { account: '未知' }))).toBe(
      '组别名'
    )
    expect(
      getSignDetailAlias(group('u1', [], '组别名'), game('成功', { account: '未知用户' }))
    ).toBe('组别名')
    expect(getSignDetailAlias(group('u1', [], '组别名'), game('成功'))).toBe('组别名')
  })

  it('账号组别名也为空时兜底为「未知用户」', () => {
    expect(getSignDetailAlias(group('u1', [], ''), game('成功'))).toBe('未知用户')
    expect(getSignDetailAlias(group('u1', [], '  '), game('成功', { account: '  ' }))).toBe(
      '未知用户'
    )
  })

  it('状态文案', () => {
    expect(getSignStatusKey('成功')).toBe('gamesign.signStatus.signed')
    expect(getSignStatusKey('已签到')).toBe('gamesign.signStatus.signed')
    expect(getSignStatusKey('风控')).toBe('gamesign.signStatus.risk')
    expect(getSignStatusKey('失败')).toBe('gamesign.signStatus.failed')
    expect(getSignStatusKey('')).toBe('gamesign.signStatus.unsigned')
    expect(getSignStatusKey('莫名其妙的状态')).toBe('gamesign.signStatus.unsigned')
  })

  it('状态样式类', () => {
    expect(getSignDetailClass('成功')).toBe('tt-signed')
    expect(getSignDetailClass('已签到')).toBe('tt-signed')
    expect(getSignDetailClass('风控')).toBe('tt-risk')
    expect(getSignDetailClass('失败')).toBe('tt-failed')
    expect(getSignDetailClass('其他')).toBe('tt-unsigned')
  })
})

describe('标签文字与样式', () => {
  it('有结果显示成功数/总数', () => {
    const tag = buildPlatformTag('米游社', [], [game('成功'), game('失败')])
    expect(getTagText(tag)).toBe('米游社1/2')
  })

  it('没有结果只显示社区名', () => {
    expect(getTagText(buildPlatformTag('森空岛', [], []))).toBe('森空岛')
  })

  it('样式类由状态拼出', () => {
    expect(getTagClass('signed')).toBe('tag-signed')
    expect(getTagClass('unconfigured')).toBe('tag-unconfigured')
  })
})
