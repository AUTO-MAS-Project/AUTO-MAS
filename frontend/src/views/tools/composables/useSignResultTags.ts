/**
 * Lane 8：签到结果标签云计算。
 *
 * 从 TabGameSign.vue 拆分出来，负责：
 * - 解析 config.Result JSON
 * - 按 account + platform 聚合签到状态
 * - 计算 TagStatus（signed/partial/unsigned/failed/risk）
 *
 * 设计：纯计算 composable，无副作用，便于测试。
 */
import { computed, type ComputedRef } from 'vue'

export interface GameItem {
  game: string
  status: string
  reward: string
  reason: string
}

export interface AccountGroup {
  account_alias: string
  account_uid: string
  games: GameItem[]
}

export interface PlatformResult {
  [platform: string]: AccountGroup[]
}

export type TagStatus = 'signed' | 'partial' | 'unsigned' | 'failed' | 'risk' | 'unconfigured'

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

export interface AccountLike {
  uid: string
  MiyousheToken: string
  KuroToken: string
  SklandToken: string
}

/** 平台列表与对应 Token 字段映射 */
const PLATFORM_TOKEN_FIELDS: Record<string, keyof AccountLike> = {
  米游社: 'MiyousheToken',
  森空岛: 'SklandToken',
  库街区: 'KuroToken',
}

/**
 * 解析 config.Result JSON 字符串为 PlatformResult。
 * 容错：空、"{}"、"-" 或 JSON 解析失败时返回空对象。
 */
export function parseSignResult(resultStr: string | undefined | null): PlatformResult {
  try {
    if (!resultStr || resultStr === '{}' || resultStr === '-') return {}
    return JSON.parse(resultStr)
  } catch {
    return {}
  }
}

/**
 * 根据游戏列表计算 TagStatus。
 */
export function computeTagStatus(games: GameItem[]): TagStatus {
  const totalCount = games.length
  if (totalCount === 0) return 'unsigned'
  const signedCount = games.filter(g => g.status === '成功' || g.status === '已签到').length
  const failedCount = games.filter(g => g.status === '失败').length
  const riskCount = games.filter(g => g.status === '风控').length

  if (riskCount > 0) return 'risk'
  if (failedCount > 0) return 'failed'
  if (signedCount === totalCount) return 'signed'
  if (signedCount > 0) return 'partial'
  return 'unsigned'
}

/**
 * 为单个账号计算其所有平台的标签。
 */
export function computePlatformTagsForAccount(
  account: AccountLike,
  result: PlatformResult
): PlatformTag[] {
  const tags: PlatformTag[] = []

  for (const platform of Object.keys(PLATFORM_TOKEN_FIELDS)) {
    const tokenField = PLATFORM_TOKEN_FIELDS[platform]
    if (!account[tokenField]) continue

    const platformData = result[platform]
    const games: GameItem[] = []
    const groups: AccountGroup[] = []
    if (platformData) {
      for (const group of platformData) {
        if (group.account_uid === account.uid) {
          games.push(...group.games)
          groups.push(group)
        }
      }
    }

    const status = computeTagStatus(games)
    const totalCount = games.length
    const signedCount = games.filter(g => g.status === '成功' || g.status === '已签到').length
    const failedCount = games.filter(g => g.status === '失败').length
    const riskCount = games.filter(g => g.status === '风控').length

    tags.push({
      platform,
      status,
      games,
      groups,
      signedCount: status === 'unsigned' ? 0 : signedCount,
      totalCount: status === 'unsigned' ? 0 : totalCount,
      failedCount: status === 'unsigned' ? 0 : failedCount,
      riskCount: status === 'unsigned' ? 0 : riskCount,
    })
  }
  return tags
}

/**
 * 响应式版本：根据 config.Result 和 accounts 列表计算每个账号的标签。
 */
export function useSignResultTags(
  resultStr: ComputedRef<string | null | undefined>,
  accounts: ComputedRef<AccountLike[]>
) {
  const result = computed<PlatformResult>(() => parseSignResult(resultStr.value))

  const userTagsMap = computed<Map<string, PlatformTag[]>>(() => {
    const map = new Map<string, PlatformTag[]>()
    for (const account of accounts.value) {
      map.set(account.uid, computePlatformTagsForAccount(account, result.value))
    }
    return map
  })

  const getTagsForAccount = (account: AccountLike): PlatformTag[] => {
    return userTagsMap.value.get(account.uid) || []
  }

  const getGroupsForPlatform = (account: AccountLike, platform: string): AccountGroup[] => {
    const tags = userTagsMap.value.get(account.uid) || []
    const tag = tags.find(t => t.platform === platform)
    return tag?.groups || []
  }

  return {
    result,
    userTagsMap,
    getTagsForAccount,
    getGroupsForPlatform,
  }
}

/** 标签文字：只显示社区名，状态由标签颜色表达 */
export function getTagText(tag: { platform: string; status: TagStatus }): string {
  return tag.platform
}

/** 标签 CSS 类 */
export function getTagClass(status: TagStatus): string {
  return `tag-${status}`
}
