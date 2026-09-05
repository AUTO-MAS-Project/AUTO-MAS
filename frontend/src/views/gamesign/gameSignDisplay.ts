/**
 * 游戏社区标签云的纯展示逻辑。
 *
 * 这里全部是纯函数，不依赖 Vue 响应式和后端接口，方便单测覆盖。
 * TabGameSign 的标签云（各社区已签/失败/风控状态）完全由这些函数推导，
 * 所以改动时请同步维护 gameSignDisplay.test.ts。
 */

/** 单个游戏的签到结果 */
export interface GameItem {
  account?: string
  game: string
  status: string
  reward: string
  reason: string
}

/** 同一社区下的一个账号组 */
export interface AccountGroup {
  account_alias: string
  account_uid: string
  games: GameItem[]
}

/** 后端返回的签到结果：社区名 -> 账号组列表 */
export interface PlatformResult {
  [platform: string]: AccountGroup[]
}

/** 标签云状态 */
export type TagStatus = 'signed' | 'partial' | 'unsigned' | 'failed' | 'risk' | 'unconfigured'

/** 单个社区标签的聚合数据 */
export interface PlatformTag {
  platform: string
  status: TagStatus
  games: GameItem[]
  groups: AccountGroup[]
  signedCount: number
  totalCount: number
  failedCount: number
  riskCount: number
}

/** 计算标签所需的最小用户信息（AccountInstance 结构上兼容） */
export interface SignAccount {
  uid: string
  MiyousheToken?: string
  CloudGenshinToken?: string
  KuroToken?: string
  SklandToken?: string
  TaygedoToken?: string
}

/** 标签云中社区的展示顺序 */
export const SIGN_PLATFORMS = ['米游社', '森空岛', '库街区', '塔吉多', '云异环'] as const

/** 视为「已签到」的状态文案 */
const SIGNED_STATUSES = ['成功', '已签到']

/**
 * 解析后端存在 config.Result 里的 JSON 字符串。
 * 空值、'{}'、'-' 和非法 JSON 都退化为空结果，不抛错。
 */
export const parseSignResult = (resultStr?: string | null): PlatformResult => {
  if (!resultStr || resultStr === '{}' || resultStr === '-') return {}
  try {
    const parsed = JSON.parse(resultStr)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return parsed as PlatformResult
  } catch {
    return {}
  }
}

/** 塔吉多 Token 里同时藏了塔吉多与云异环两套凭据 */
export interface TaygedoCredential {
  taygedo: boolean
  cloud: boolean
}

/**
 * 解析塔吉多 Token。
 * 新版是 JSON；老版是裸 Token 字符串，此时只认为塔吉多可用。
 */
export const parseTaygedoCredential = (raw?: string | null): TaygedoCredential => {
  const trimmed = raw?.trim()
  if (!trimmed) return { taygedo: false, cloud: false }
  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>
    return {
      taygedo: Boolean(parsed.refreshToken || parsed.accessToken),
      cloud: Boolean(parsed.cloudToken && parsed.cloudUserId),
    }
  } catch {
    // 老版裸 Token
    return { taygedo: true, cloud: false }
  }
}

/**
 * 该用户是否配置了某社区的凭据（没有凭据的社区不出标签）。
 * 批量调用时传入 taygedo 可以省掉重复的 JSON.parse。
 */
export const hasPlatformToken = (
  account: SignAccount,
  platform: string,
  taygedo: TaygedoCredential = parseTaygedoCredential(account.TaygedoToken)
): boolean => {
  switch (platform) {
    case '米游社':
      return !!(account.MiyousheToken || account.CloudGenshinToken)
    case '库街区':
      return !!account.KuroToken
    case '森空岛':
      return !!account.SklandToken
    case '塔吉多':
      return taygedo.taygedo
    case '云异环':
      return taygedo.cloud
    default:
      return false
  }
}

/**
 * 按签到结果判定标签状态。
 * 优先级：风控 > 失败 > 全部已签 > 部分已签 > 未签。
 * 一个游戏都没跑到时算未签。
 */
export const resolveTagStatus = (counts: {
  totalCount: number
  signedCount: number
  failedCount: number
  riskCount: number
}): TagStatus => {
  if (counts.totalCount === 0) return 'unsigned'
  if (counts.riskCount > 0) return 'risk'
  if (counts.failedCount > 0) return 'failed'
  if (counts.signedCount === counts.totalCount) return 'signed'
  if (counts.signedCount > 0) return 'partial'
  return 'unsigned'
}

/** 聚合某用户在某社区的标签数据 */
export const buildPlatformTag = (
  platform: string,
  groups: AccountGroup[],
  games: GameItem[]
): PlatformTag => {
  const counts = {
    totalCount: games.length,
    signedCount: games.filter(g => SIGNED_STATUSES.includes(g.status)).length,
    failedCount: games.filter(g => g.status === '失败').length,
    riskCount: games.filter(g => g.status === '风控').length,
  }
  return { platform, groups, games, status: resolveTagStatus(counts), ...counts }
}

/** 计算单个用户的社区标签列表，顺序固定为 SIGN_PLATFORMS */
export const buildUserTags = (account: SignAccount, result: PlatformResult): PlatformTag[] => {
  const tags: PlatformTag[] = []
  const taygedo = parseTaygedoCredential(account.TaygedoToken)

  for (const platform of SIGN_PLATFORMS) {
    if (!hasPlatformToken(account, platform, taygedo)) continue

    const games: GameItem[] = []
    const groups: AccountGroup[] = []
    for (const group of result[platform] ?? []) {
      if (group.account_uid !== account.uid) continue
      games.push(...group.games)
      groups.push(group)
    }

    tags.push(buildPlatformTag(platform, groups, games))
  }

  return tags
}

/** 一次算出所有用户的标签，key 为 account.uid */
export const buildUserTagsMap = (
  accounts: readonly SignAccount[],
  result: PlatformResult
): Map<string, PlatformTag[]> => {
  const map = new Map<string, PlatformTag[]>()
  for (const account of accounts) {
    map.set(account.uid, buildUserTags(account, result))
  }
  return map
}

/**
 * Tooltip 里单行游戏的账号别名。
 * 优先取结果里 'alias/uid' 形式的前半段，占位值则回退到账号组别名。
 */
export const getSignDetailAlias = (
  group: AccountGroup,
  game: GameItem,
  // 占位值与判断依据都是后端原文，兜底文案由调用方传词表结果进来
  fallback = '未知用户'
): string => {
  const account = game.account?.trim() || ''
  const alias = account.split('/', 1)[0]?.trim()
  if (alias && alias !== '未知' && alias !== '未知用户') return alias
  return group.account_alias?.trim() || fallback
}

/** Tooltip 里单行游戏的状态文案对应的词表 key */
export const getSignStatusKey = (status: string): string => {
  if (SIGNED_STATUSES.includes(status)) return 'gamesign.signStatus.signed'
  if (status === '风控') return 'gamesign.signStatus.risk'
  if (status === '失败') return 'gamesign.signStatus.failed'
  return 'gamesign.signStatus.unsigned'
}

/** Tooltip 里单行游戏的状态样式类 */
export const getSignDetailClass = (status: string): string => {
  if (SIGNED_STATUSES.includes(status)) return 'tt-signed'
  if (status === '风控') return 'tt-risk'
  if (status === '失败') return 'tt-failed'
  return 'tt-unsigned'
}

/** 标签文字：尚无结果时只显示社区名，执行后显示成功数/总数 */
export const getTagText = (tag: PlatformTag): string =>
  tag.totalCount > 0 ? `${tag.platform}${tag.signedCount}/${tag.totalCount}` : tag.platform

/** 标签样式类 */
export const getTagClass = (status: TagStatus): string => `tag-${status}`
