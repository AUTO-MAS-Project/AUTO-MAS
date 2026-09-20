import type { GameItem, PlatformResult } from '@/views/gamesign/gameSignDisplay'

/** 某游戏在所有社区里的签到汇总 */
export interface GameSignSummary {
  signed: number
  total: number
  unknown: number
}

/** 视为「已签到」的状态文案，与 gameSignDisplay 里的口径一致 */
const SIGNED_STATUSES = ['成功', '已签到']

export interface GameSignUser {
  uid: string
  name: string
  entries: Pick<GameItem, 'status' | 'reward' | 'reason'>[]
  signed: boolean
}

type SignSnapshot = {
  game: string
  accountUid: string
  account?: string
  roleUid?: string
  status: string
}

/** 按当前游戏汇集用户、签到结果和奖励，保持社区返回的用户顺序。 */
export const collectGameSignUsers = (
  result: PlatformResult,
  gameName: string,
  snapshots: readonly SignSnapshot[] = []
): GameSignUser[] => {
  const accounts = new Map<string, GameSignUser>()
  for (const groups of Object.values(result)) {
    for (const group of groups) {
      const games = group.games.filter(game => game.game === gameName)
      if (!games.length) continue
      const user = accounts.get(group.account_uid) ?? {
        uid: group.account_uid,
        name: group.account_alias,
        entries: [],
        signed: false,
      }
      for (const game of games) {
        // 明确的游戏分项优先；库洛币等社区分项不混入游戏奖励和成功判定。
        const details = game.details?.filter(detail => detail.kind === 'game')
        for (const entry of details?.length ? details : [game]) {
          user.entries.push({
            status: entry.status,
            reward: entry.reward ?? '',
            reason: entry.reason ?? '',
          })
        }
      }
      accounts.set(user.uid, user)
    }
  }
  for (const snapshot of snapshots) {
    if (snapshot.game !== gameName || (!snapshot.roleUid && snapshot.status !== 'success')) continue
    if (!accounts.has(snapshot.accountUid)) {
      accounts.set(snapshot.accountUid, {
        uid: snapshot.accountUid,
        name: snapshot.account ?? '',
        entries: [],
        signed: false,
      })
    }
  }
  return [...accounts.values()].map(user => ({
    ...user,
    signed:
      user.entries.length > 0 &&
      user.entries.every(entry => SIGNED_STATUSES.includes(entry.status)),
  }))
}

/** 全量用户参与统计；界面只折叠展示，不改变分子与分母。 */
export const summarizeGameSign = (
  result: PlatformResult,
  gameName: string,
  snapshots: readonly SignSnapshot[] = []
): GameSignSummary | null => {
  const users = collectGameSignUsers(result, gameName, snapshots)
  return users.length
    ? {
        signed: users.filter(user => user.signed).length,
        total: users.length,
        unknown: users.filter(user => !user.entries.length).length,
      }
    : null
}

/** 外部账号名、奖励和失败原因作为 Markdown 纯文本，不能注入图片、链接或 HTML。 */
export const escapeSignMarkdown = (text: string): string =>
  text.replace(/[\r\n]+/g, ' ').replace(/[\\`*_{}[\]<>()!#|]/g, '\\$&')
